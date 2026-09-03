import hashlib
import json
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace

import pytest

from knowmat.alpha25.contracts import (
    AxisResponse,
    ContractRejection,
    InventoryAnchor,
    InventoryResponse,
    MultiAxisResponse,
    ProcessingFact,
    PropertyFact,
)
from knowmat.nodes.extraction import (
    V11IncompleteCoverageError,
    V11RawResponseError,
    V11TaskCacheMissError,
    _extract_alpha25_tasks,
    _figure_enrichment_enabled,
    _figure_prose_fallback_enabled,
    _alpha25_task_cache_path,
    _deterministic_table_anchors,
    _invoke_alpha25_task_json,
    _is_quota_error,
    _quota_reset_epoch,
)
from knowmat.alpha25.planner import (
    TableStateAnchor,
    build_evidence_units,
    plan_combined_axis_tasks,
)


@pytest.fixture(autouse=True)
def _use_legacy_axis_scoped_strategy_for_axis_specific_regressions(monkeypatch):
    """Keep existing failure-path tests focused on their named single axis."""

    monkeypatch.setenv("KNOWMAT2_ALPHA25_TASK_STRATEGY", "axis_scoped")


def test_alpha25_tasks_materialize_axis_facts_without_full_item_calls(
    monkeypatch, tmp_path
):
    paper = "Sample A was annealed at 800 °C. Its yield strength was 900 MPa."
    paper_path = tmp_path / "paper.md"
    paper_path.write_text(paper, encoding="utf-8")
    calls = []
    materialize_calls = []

    def fake_invoke(_system, _user, *, axis, output_token_budget):
        calls.append((axis, output_token_budget))
        if axis == "inventory":
            return InventoryResponse(
                anchors=[
                    InventoryAnchor(
                        sample_id_raw="Sample A",
                        role="Target",
                        data_nature="Experimental",
                        source_evidence=["Sample A"],
                        confidence=0.9,
                    )
                ]
            )
        if axis == "processing":
            return AxisResponse(
                axis="processing",
                facts=[
                    ProcessingFact(
                        sample_id_raw="Sample A",
                        fact_type="process_stage",
                        data={
                            "candidate_stage_id": "temporary",
                            "stage_index_candidate": 1,
                            "process_name_raw": "annealed",
                            "process_code_candidate": None,
                            "process_role_candidate": "post_process",
                            "parameters_raw": [],
                            "source_evidence": ["annealed at 800 °C"],
                            "confidence": 0.9,
                        },
                        source_evidence=["annealed at 800 °C"],
                        confidence=0.9,
                    )
                ],
            )
        if axis == "properties":
            evidence = "yield strength was 900 MPa"
            return AxisResponse(
                axis="properties",
                facts=[
                    PropertyFact(
                        sample_id_raw="Sample A",
                        data={
                            "property_id_candidate": "temporary",
                            "property_name_raw": "yield strength",
                            "value_raw": "900",
                            "unit_raw": "MPa",
                            "test_method_raw": "",
                            "test_standard_raw": "",
                            "test_condition_raw": "",
                            "test_specimen_raw": "",
                            "raw_note": "",
                            "data_source": "text",
                            "source_evidence": [evidence],
                            "confidence": 0.9,
                        },
                        source_evidence=[evidence],
                        confidence=0.9,
                    )
                ],
            )
        raise AssertionError(axis)

    monkeypatch.setattr(
        "knowmat.nodes.extraction._invoke_alpha25_task_json", fake_invoke
    )
    from knowmat.alpha25.materialize import materialize_candidate

    def capture_materialize(*args, **kwargs):
        materialize_calls.append(kwargs.get("source_dir"))
        return materialize_candidate(*args, **kwargs)

    monkeypatch.setattr(
        "knowmat.nodes.extraction.materialize_candidate", capture_materialize
    )

    document, coverage = _extract_alpha25_tasks(
        "SYSTEM",
        paper,
        {
            "base_material": "Metals",
            "application": "Structural",
            "research_paradigm": "Experimental",
        },
        paper_text_path=paper_path,
        ocr_baseline_id="baseline-test",
    )

    assert [axis for axis, _ in calls] == ["inventory", "processing", "properties"]
    assert materialize_calls == [tmp_path]
    assert coverage["complete"] is True
    assert coverage["ocr_baseline_id"] == "baseline-test"
    assert len(document["items"]) == 1
    extracted = document["items"][0]["Extracted_Data"]
    assert len(extracted["Processing"]["Process_Route"]["candidate_stages"]) == 1
    assert len(extracted["Properties"]) == 1


def test_default_combined_strategy_materializes_all_axes_in_one_fact_call(monkeypatch):
    paper = "Sample A was annealed at 800 °C. Its yield strength was 900 MPa."
    calls = []

    def fake_invoke(_system, _user, *, axis, output_token_budget):
        calls.append((axis, output_token_budget))
        assert axis == "combined"
        property_evidence = "yield strength was 900 MPa"
        return MultiAxisResponse(
            anchors=[
                InventoryAnchor(
                    sample_id_raw="Sample A",
                    role="Target",
                    data_nature="Experimental",
                    source_evidence=["Sample A"],
                    confidence=0.9,
                )
            ],
            facts=[
                ProcessingFact(
                    sample_id_raw="Sample A",
                    fact_type="process_stage",
                    data={
                        "candidate_stage_id": "temporary",
                        "stage_index_candidate": 1,
                        "process_name_raw": "annealed",
                        "process_code_candidate": None,
                        "process_role_candidate": "post_process",
                        "parameters_raw": [],
                        "source_evidence": ["annealed at 800 °C"],
                        "confidence": 0.9,
                    },
                    source_evidence=["annealed at 800 °C"],
                    confidence=0.9,
                ),
                PropertyFact(
                    sample_id_raw="Sample A",
                    data={
                        "property_id_candidate": "temporary",
                        "property_name_raw": "yield strength",
                        "value_raw": "900",
                        "unit_raw": "MPa",
                        "test_method_raw": "",
                        "test_standard_raw": "",
                        "test_condition_raw": "",
                        "test_specimen_raw": "",
                        "raw_note": "",
                        "data_source": "text",
                        "source_evidence": [property_evidence],
                        "confidence": 0.9,
                    },
                    source_evidence=[property_evidence],
                    confidence=0.9,
                ),
            ]
        )

    monkeypatch.delenv("KNOWMAT2_ALPHA25_TASK_STRATEGY", raising=False)
    monkeypatch.setattr(
        "knowmat.nodes.extraction._invoke_alpha25_task_json", fake_invoke
    )

    document, coverage = _extract_alpha25_tasks(
        "SYSTEM", paper, {}, ocr_baseline_id="baseline-test"
    )

    assert calls == [("combined", 4096)]
    assert coverage["complete"] is True
    assert coverage["unified_inventory"] is True
    assert coverage["initial_inventory_task_count"] == 0
    assert len(document["items"]) == 1
    extracted = document["items"][0]["Extracted_Data"]
    assert len(extracted["Processing"]["Process_Route"]["candidate_stages"]) == 1
    assert len(extracted["Properties"]) == 1


def test_precision_promotion_is_audited_without_changing_document_schema(monkeypatch):
    paper = "Sample A had a yield strength of 900 MPa."

    def fake_invoke(_system, _user, *, axis, output_token_budget):
        assert axis == "combined"
        evidence = "Sample A had a yield strength of 900 MPa."
        return MultiAxisResponse(
            anchors=[
                InventoryAnchor(
                    sample_id_raw="Sample A",
                    role="Target",
                    data_nature="Experimental",
                    source_evidence=["Sample A"],
                    confidence=0.9,
                )
            ],
            facts=[
                PropertyFact(
                    sample_id_raw="Sample A",
                    data={
                        "property_id_candidate": "temporary",
                        "property_name_raw": "yield strength",
                        "value_raw": "900",
                        "unit_raw": "MPa",
                        "test_method_raw": "tensile",
                        "test_standard_raw": "",
                        "test_condition_raw": "650 °C",
                        "test_specimen_raw": "",
                        "raw_note": "",
                        "data_source": "text",
                        "source_evidence": [evidence],
                        "confidence": 0.9,
                    },
                    source_evidence=[evidence],
                    confidence=0.9,
                )
            ],
    )

    monkeypatch.delenv("KNOWMAT2_ALPHA25_TASK_STRATEGY", raising=False)
    # Precision-first promotion is enabled by default; an explicit "0" remains
    # available for high-recall diagnostic replays.
    monkeypatch.delenv("KNOWMAT2_ALPHA25_PROMOTION_ENABLED", raising=False)
    monkeypatch.setattr(
        "knowmat.nodes.extraction._invoke_alpha25_task_json", fake_invoke
    )

    document, coverage = _extract_alpha25_tasks("SYSTEM", paper, {})

    assert set(document) == {"Paper_Metadata", "Paper_Routing", "items"}
    assert coverage["promotion_enabled"] is True
    assert coverage["promotion_input_fact_count"] == 1
    assert coverage["promotion_accepted_fact_count"] == 1
    assert coverage["promotion_issue_count"] == 1
    assert coverage["materialization_issues"][0]["code"] == (
        "promotion_unbound_condition_quarantined"
    )
    assert "promotion" not in document


def test_combined_contract_rejection_is_counted_without_retrying_valid_siblings(
    monkeypatch, tmp_path,
):
    paper = "Sample A had a yield strength of 900 MPa and a stress-strain curve."
    calls = []

    def fake_invoke(_system, _user, *, axis, output_token_budget):
        calls.append((axis, output_token_budget))
        return MultiAxisResponse(
            anchors=[
                InventoryAnchor(
                    sample_id_raw="Sample A",
                    role="Target",
                    data_nature="Experimental",
                    source_evidence=["Sample A"],
                    confidence=0.9,
                )
            ],
            facts=[
                PropertyFact(
                    sample_id_raw="Sample A",
                    data={
                        "property_id_candidate": "temporary",
                        "property_name_raw": "yield strength",
                        "value_raw": "900",
                        "unit_raw": "MPa",
                        "test_method_raw": "",
                        "test_standard_raw": "",
                        "test_condition_raw": "",
                        "test_specimen_raw": "",
                        "raw_note": "",
                        "data_source": "text",
                        "source_evidence": ["yield strength of 900 MPa"],
                        "confidence": 0.9,
                    },
                    source_evidence=["yield strength of 900 MPa"],
                    confidence=0.9,
                )
            ],
            contract_rejections=[
                ContractRejection(
                    fact_index=1,
                    axis="properties",
                    fact_type="property",
                    source_evidence=["stress-strain curve"],
                    message="property data is missing value_raw",
                )
            ],
        )

    monkeypatch.setenv("KNOWMAT2_ALPHA25_TASK_STRATEGY", "combined_axes")
    monkeypatch.setattr(
        "knowmat.nodes.extraction._invoke_alpha25_task_json", fake_invoke
    )

    document, coverage = _extract_alpha25_tasks(
        "SYSTEM",
        paper,
        {},
        cache_dir=tmp_path,
        ocr_baseline_id="baseline-test",
    )

    assert len(calls) == 1
    assert coverage["complete"] is True
    assert coverage["retry_task_count"] == 0
    assert coverage["rejected_facts"] == 1
    assert coverage["evidence_issues"][0]["code"] == "invalid_fact_contract"
    assert len(document["items"][0]["Extracted_Data"]["Properties"]) == 1

    _, cached_coverage = _extract_alpha25_tasks(
        "SYSTEM",
        paper,
        {},
        cache_dir=tmp_path,
        ocr_baseline_id="baseline-test",
    )
    assert len(calls) == 1
    assert cached_coverage["states"]["cached"] == 1
    assert cached_coverage["rejected_facts"] == 1
    assert cached_coverage["evidence_issues"][0]["code"] == "invalid_fact_contract"


def test_alpha25_coverage_separates_provider_queue_and_call_time(monkeypatch):
    import knowmat.nodes.extraction as extraction

    def fake_invoke(_system, _user, *, axis, output_token_budget):
        extraction._record_alpha25_request_timing(
            queue_seconds=0.25,
            call_seconds=0.75,
        )
        return MultiAxisResponse(
            anchors=[
                InventoryAnchor(
                    sample_id_raw="Sample A",
                    role="Target",
                    data_nature="Experimental",
                    source_evidence=["Sample A"],
                    confidence=0.9,
                )
            ],
            facts=[
                PropertyFact(
                    sample_id_raw="Sample A",
                    data={
                        "property_id_candidate": "temporary",
                        "property_name_raw": "yield strength",
                        "value_raw": "900",
                        "unit_raw": "MPa",
                        "test_method_raw": "",
                        "test_standard_raw": "",
                        "test_condition_raw": "",
                        "test_specimen_raw": "",
                        "raw_note": "",
                        "data_source": "text",
                        "source_evidence": ["yield strength of 900 MPa"],
                        "confidence": 0.9,
                    },
                    source_evidence=["yield strength of 900 MPa"],
                    confidence=0.9,
                )
            ],
        )

    monkeypatch.delenv("KNOWMAT2_ALPHA25_TASK_STRATEGY", raising=False)
    monkeypatch.setattr(extraction, "_invoke_alpha25_task_json", fake_invoke)

    document, coverage = _extract_alpha25_tasks(
        "SYSTEM",
        "Sample A had a yield strength of 900 MPa.",
        {},
        ocr_baseline_id="baseline-test",
    )

    assert len(document["items"]) == 1
    assert coverage["provider_queue_elapsed_sum"] == pytest.approx(0.25)
    assert coverage["provider_queue_elapsed_p95"] == pytest.approx(0.25)
    assert coverage["provider_call_elapsed_sum"] == pytest.approx(0.75)
    assert coverage["provider_call_elapsed_p95"] == pytest.approx(0.75)
    assert coverage["records"][0]["provider_queue_seconds"] == pytest.approx(0.25)
    assert coverage["records"][0]["provider_call_seconds"] == pytest.approx(0.75)


def test_structured_table_state_anchors_are_source_backed_inventory():
    paper = r"""Grain sizes of the WA and GA powder alloy sintered samples.
<table><tr><td>Sintering temperature [^\circC]</td><td>GA grain size</td><td>WA grain size</td></tr><tr><td>1225</td><td>39</td><td>80</td></tr><tr><td>1240</td><td>45</td><td>83</td></tr></table>
"""
    unit = next(
        unit for unit in build_evidence_units(paper) if unit.kind == "table"
    )

    anchors = _deterministic_table_anchors(unit)

    assert {
        (anchor.sample_id_raw, anchor.state_raw) for anchor in anchors
    } == {
        ("GA", "sintered at 1225 °C"),
        ("GA", "sintered at 1240 °C"),
        ("WA", "sintered at 1225 °C"),
        ("WA", "sintered at 1240 °C"),
    }
    assert all(
        all(evidence in unit.text for evidence in anchor.source_evidence)
        for anchor in anchors
    )


def test_reference_table_rows_create_citation_specific_reference_anchors():
    paper = """Summary of published studies.

| Reference | Year | Alloy | Boride | Carbide |
| --- | --- | --- | --- | --- |
| Tytko [21] | 2012 | 617B | No | Yes |
| Blavette [32] | 1996 | Astroloy | Yes | Yes |
| Letellier [33] | 1994 | Astroloy | No | No |
"""
    units = [unit for unit in build_evidence_units(paper) if unit.kind == "table"]

    anchors = [
        anchor
        for unit in units
        for anchor in _deterministic_table_anchors(unit)
    ]

    references = {
        (anchor.sample_id_raw, anchor.role, anchor.data_nature)
        for anchor in anchors
        if anchor.role == "Reference"
    }
    assert (
        "617B [21] [reference]",
        "Reference",
        "Literature_Experimental",
    ) in references
    assert (
        "Astroloy [32] [reference]",
        "Reference",
        "Literature_Experimental",
    ) in references
    assert (
        "Astroloy [33] [reference]",
        "Reference",
        "Literature_Experimental",
    ) in references


def test_structured_table_anchors_participate_in_task_cache_identity(tmp_path):
    paper = r"""Grain sizes of the WA and GA powder alloy sintered samples.
<table><tr><td>Sintering temperature [^\circC]</td><td>GA grain size</td><td>WA grain size</td></tr><tr><td>1225</td><td>39</td><td>80</td></tr></table>
"""
    task = plan_combined_axis_tasks(build_evidence_units(paper))[0]
    changed = replace(
        task,
        state_anchors=(
            TableStateAnchor(
                sample_id_raw="GA",
                state_raw="sintered at 1300 °C",
                source_evidence=("GA", r"Sintering temperature [^\circC]", "1300"),
            ),
        ),
    )

    original_path = _alpha25_task_cache_path(
        tmp_path,
        task=task,
        system_prompt="SYSTEM",
        user_prompt="USER",
        ocr_baseline_id="baseline",
    )
    changed_path = _alpha25_task_cache_path(
        tmp_path,
        task=changed,
        system_prompt="SYSTEM",
        user_prompt="USER",
        ocr_baseline_id="baseline",
    )

    assert original_path != changed_path


def test_ungrounded_short_task_is_filtered_reported_and_cached(monkeypatch, tmp_path):
    paper = "Sample A had a yield strength of 900 MPa."
    calls = []

    def partly_grounded(_system, _user, *, axis, output_token_budget):
        calls.append(axis)
        if axis == "inventory":
            return InventoryResponse(anchors=[])
        return AxisResponse(
            axis="properties",
            facts=[
                PropertyFact(
                    sample_id_raw="Sample A",
                    data={
                        "property_id_candidate": "grounded",
                        "property_name_raw": "yield strength",
                        "value_raw": "900",
                        "unit_raw": "MPa",
                        "test_method_raw": "",
                        "test_standard_raw": "",
                        "test_condition_raw": "",
                        "test_specimen_raw": "",
                        "raw_note": "",
                        "data_source": "text",
                        "source_evidence": ["yield strength of 900 MPa"],
                        "confidence": 0.9,
                    },
                    source_evidence=["yield strength of 900 MPa"],
                    confidence=0.9,
                ),
                PropertyFact(
                    sample_id_raw="Sample A",
                    data={
                        "property_id_candidate": "temporary",
                        "property_name_raw": "yield strength",
                        "value_raw": "900",
                        "unit_raw": "MPa",
                        "test_method_raw": "",
                        "test_standard_raw": "",
                        "test_condition_raw": "",
                        "test_specimen_raw": "",
                        "raw_note": "",
                        "data_source": "text",
                        "source_evidence": ["invented evidence"],
                        "confidence": 0.9,
                    },
                    source_evidence=["invented evidence"],
                    confidence=0.9,
                )
            ],
        )

    monkeypatch.setattr(
        "knowmat.nodes.extraction._invoke_alpha25_task_json", partly_grounded
    )

    document, coverage = _extract_alpha25_tasks(
        "SYSTEM", paper, {}, cache_dir=tmp_path, ocr_baseline_id="baseline"
    )

    assert coverage["complete"] is True
    assert coverage["rejected_facts"] == 1
    assert coverage["evidence_issues"]
    assert len(document["items"]) == 1
    assert len(document["items"][0]["Extracted_Data"]["Properties"]) == 1

    first_call_count = len(calls)
    monkeypatch.setenv("KNOWMAT2_ALPHA25_CACHE_ONLY", "1")
    _, cached_coverage = _extract_alpha25_tasks(
        "SYSTEM", paper, {}, cache_dir=tmp_path, ocr_baseline_id="baseline"
    )
    assert len(calls) == first_call_count
    assert cached_coverage["states"]["cached"] == 2


def test_alpha25_cache_only_miss_never_calls_provider(monkeypatch, tmp_path):
    paper = "Sample A had a yield strength of 900 MPa."
    monkeypatch.setenv("KNOWMAT2_ALPHA25_CACHE_ONLY", "1")
    monkeypatch.setattr(
        "knowmat.nodes.extraction._invoke_alpha25_task_json",
        lambda *_args, **_kwargs: pytest.fail("provider must not be called"),
    )

    with pytest.raises(V11TaskCacheMissError, match="cache-only replay missing"):
        _extract_alpha25_tasks(
            "SYSTEM",
            paper,
            {},
            cache_dir=tmp_path,
            ocr_baseline_id="baseline",
        )


def test_alpha25_identity_sidecar_persists_source_scope_without_changing_cache_key(
    monkeypatch, tmp_path
):
    paper = "Sample A had a yield strength of 900 MPa."

    def empty_response(_system, _user, *, axis, output_token_budget):
        del output_token_budget
        if axis == "combined":
            return MultiAxisResponse(anchors=[], facts=[])
        return AxisResponse(axis=axis, facts=[])

    monkeypatch.setenv("KNOWMAT2_ALPHA25_TASK_STRATEGY", "combined_axes")
    monkeypatch.setattr(
        "knowmat.nodes.extraction._invoke_alpha25_task_json", empty_response
    )
    _extract_alpha25_tasks(
        "SYSTEM", paper, {}, cache_dir=tmp_path, ocr_baseline_id="baseline"
    )

    response_path = next(tmp_path.glob("*.json"))
    sidecar_path = response_path.with_name(response_path.name + ".identity")
    identity = json.loads(sidecar_path.read_text(encoding="utf-8"))
    source_scope = identity["task_source_scope"]

    assert identity["version"] == 2
    assert source_scope["text"] == paper
    assert source_scope["sha256"] == hashlib.sha256(paper.encode()).hexdigest()

    monkeypatch.setenv("KNOWMAT2_ALPHA25_CACHE_ONLY", "1")
    _extract_alpha25_tasks(
        "SYSTEM", paper, {}, cache_dir=tmp_path, ocr_baseline_id="baseline"
    )
    assert next(tmp_path.glob("*.json")) == response_path


def test_frozen_baseline_disables_generative_figure_enrichment_by_default(monkeypatch):
    monkeypatch.delenv("KNOWMAT2_ALPHA25_ENABLE_FIGURE_ENRICHMENT", raising=False)

    assert _figure_enrichment_enabled({"ocr_manifest_path": "baseline.json"}) is False
    assert _figure_enrichment_enabled({}) is True

    monkeypatch.setenv("KNOWMAT2_ALPHA25_ENABLE_FIGURE_ENRICHMENT", "1")
    assert _figure_enrichment_enabled({"ocr_manifest_path": "baseline.json"}) is True


def test_frozen_alpha25_figure_enrichment_is_chart_only_by_default(monkeypatch):
    monkeypatch.delenv("KNOWMAT2_ALPHA25_FIGURE_PROSE_FALLBACK", raising=False)

    assert _figure_prose_fallback_enabled({"ocr_manifest_path": "baseline.json"}) is False
    assert _figure_prose_fallback_enabled({}) is True

    monkeypatch.setenv("KNOWMAT2_ALPHA25_FIGURE_PROSE_FALLBACK", "1")
    assert _figure_prose_fallback_enabled({"ocr_manifest_path": "baseline.json"}) is True


def test_glm_account_usage_quota_is_classified_with_absolute_reset_time():
    exc = RuntimeError(
        "AccountQuotaExceeded: You have exceeded the 5-hour usage quota. "
        "It will reset at 2026-08-17 22:11:13 +0800 CST."
    )

    assert _is_quota_error(exc) is True
    assert _quota_reset_epoch(exc) == 1786975873.0


def test_alpha25_quota_window_waits_and_retries_same_request(monkeypatch):
    import knowmat.nodes.extraction as extraction

    clock = {"now": 1786975863.0}
    sleeps = []

    class FakeResponse:
        content = '{"axis":"properties","facts":[]}'
        response_metadata = {}

    class FakeLLM:
        calls = 0

        def bind(self, **_kwargs):
            return self

        def invoke(self, _messages):
            self.calls += 1
            if self.calls == 1:
                raise RuntimeError(
                    "AccountQuotaExceeded: usage quota; reset at "
                    "2026-08-17 22:11:13 +0800 CST"
                )
            return FakeResponse()

    llm = FakeLLM()

    def fake_sleep(seconds):
        sleeps.append(seconds)
        clock["now"] += seconds

    monkeypatch.setattr(extraction, "_ALPHA25_QUOTA_RESUME_EPOCH", 0.0)
    monkeypatch.setattr(extraction, "get_llm", lambda **_kwargs: llm)
    monkeypatch.setattr(extraction.time, "time", lambda: clock["now"])
    monkeypatch.setattr(extraction.time, "sleep", fake_sleep)
    monkeypatch.setenv("KNOWMAT2_ALPHA25_QUOTA_GRACE_SECONDS", "0")
    monkeypatch.setenv("KNOWMAT2_ALPHA25_QUOTA_MAX_WAIT_SECONDS", "60")

    response = _invoke_alpha25_task_json(
        "SYSTEM",
        "USER",
        axis="properties",
        output_token_budget=4096,
    )

    assert response.axis == "properties"
    assert llm.calls == 2
    assert sleeps == [10.0]


def test_alpha25_provider_calls_share_one_process_wide_concurrency_limit(monkeypatch):
    import knowmat.nodes.extraction as extraction

    lock = threading.Lock()
    active = 0
    maximum_active = 0

    class FakeResponse:
        content = '{"axis":"properties","facts":[]}'
        response_metadata = {}

    class FakeLLM:
        def bind(self, **_kwargs):
            return self

        def invoke(self, _messages):
            nonlocal active, maximum_active
            with lock:
                active += 1
                maximum_active = max(maximum_active, active)
            try:
                time.sleep(0.02)
                return FakeResponse()
            finally:
                with lock:
                    active -= 1

    monkeypatch.setattr(extraction, "_ALPHA25_ACTIVE_REQUESTS", 0)
    monkeypatch.setattr(extraction, "get_llm", lambda **_kwargs: FakeLLM())
    monkeypatch.setenv("KNOWMAT2_ALPHA25_GLOBAL_CONCURRENCY", "2")

    def invoke(index):
        return _invoke_alpha25_task_json(
            "SYSTEM",
            f"USER {index}",
            axis="properties",
            output_token_budget=4096,
        )

    with ThreadPoolExecutor(max_workers=8) as pool:
        responses = list(pool.map(invoke, range(8)))

    assert all(response.axis == "properties" for response in responses)
    assert maximum_active == 2
    assert extraction._ALPHA25_ACTIVE_REQUESTS == 0


def test_alpha25_shared_task_pool_is_process_wide_and_work_conserving(monkeypatch):
    import knowmat.nodes.extraction as extraction

    monkeypatch.setenv("KNOWMAT2_ALPHA25_GLOBAL_CONCURRENCY", "2")
    first = extraction._alpha25_shared_task_pool()
    second = extraction._alpha25_shared_task_pool()
    lock = threading.Lock()
    release = threading.Event()
    active = 0
    maximum_active = 0

    def task():
        nonlocal active, maximum_active
        with lock:
            active += 1
            maximum_active = max(maximum_active, active)
        try:
            release.wait(timeout=1)
        finally:
            with lock:
                active -= 1

    futures = [first.submit(task) for _ in range(6)]
    deadline = time.monotonic() + 1
    while maximum_active < 2 and time.monotonic() < deadline:
        time.sleep(0.005)
    release.set()
    for future in futures:
        future.result(timeout=1)

    assert first is second
    assert maximum_active == 2


def test_truncated_axis_task_retries_same_evidence_with_larger_budget_before_split(
    monkeypatch,
    tmp_path,
):
    paper = "Sample A had a yield strength of 900 MPa."
    calls = []
    property_attempts = 0

    def truncated_then_complete(system, user, *, axis, output_token_budget):
        nonlocal property_attempts
        calls.append((axis, output_token_budget, user))
        if axis == "inventory":
            return InventoryResponse(
                anchors=[
                    InventoryAnchor(
                        sample_id_raw="Sample A",
                        role="Target",
                        data_nature="Experimental",
                        source_evidence=["Sample A"],
                        confidence=0.9,
                    )
                ]
            )
        if axis == "properties":
            property_attempts += 1
            if property_attempts == 1:
                raise V11RawResponseError(
                    "output_truncated",
                    finish_reason="length",
                    content='{"axis":"properties","facts":[',
                )
            evidence = "yield strength of 900 MPa"
            return AxisResponse(
                axis="properties",
                facts=[
                    PropertyFact(
                        sample_id_raw="Sample A",
                        data={
                            "property_id_candidate": "temporary",
                            "property_name_raw": "yield strength",
                            "value_raw": "900",
                            "unit_raw": "MPa",
                            "test_method_raw": "",
                            "test_standard_raw": "",
                            "test_condition_raw": "",
                            "test_specimen_raw": "",
                            "raw_note": "",
                            "data_source": "text",
                            "source_evidence": [evidence],
                            "confidence": 0.9,
                        },
                        source_evidence=[evidence],
                        confidence=0.9,
                    )
                ],
            )
        raise AssertionError(axis)

    monkeypatch.setenv("KNOWMAT2_ALPHA25_RETRY_OUTPUT_TOKENS", "8192")
    monkeypatch.setenv("KNOWMAT2_ALPHA25_FAILURE_SPLIT_DEPTH", "2")
    monkeypatch.setattr(
        "knowmat.nodes.extraction._invoke_alpha25_task_json",
        truncated_then_complete,
    )

    document, coverage = _extract_alpha25_tasks(
        "SYSTEM", paper, {}, cache_dir=tmp_path, ocr_baseline_id="baseline"
    )

    property_calls = [call for call in calls if call[0] == "properties"]
    assert [call[1] for call in property_calls] == [3500, 8192]
    assert property_calls[0][2] == property_calls[1][2]
    assert coverage["complete"] is True
    assert coverage["states"]["split"] == 1
    assert not any("-s1" in row["task_id"] for row in coverage["records"])
    assert any(
        row["task_id"].endswith("-budget8192")
        for row in coverage["records"]
    )
    assert len(document["items"]) == 1
    assert len(document["items"][0]["Extracted_Data"]["Properties"]) == 1

    live_call_count = len(calls)
    monkeypatch.setenv("KNOWMAT2_ALPHA25_CACHE_ONLY", "1")
    replayed, replay_coverage = _extract_alpha25_tasks(
        "SYSTEM", paper, {}, cache_dir=tmp_path, ocr_baseline_id="baseline"
    )

    assert len(calls) == live_call_count
    assert replay_coverage["complete"] is True
    assert replay_coverage["states"]["split"] == 1
    assert replayed == document


def test_truncated_structure_task_retries_large_budget_before_splitting(
    monkeypatch,
):
    paper = (
        "Sample A microstructure contained fine grains and alpha laths. "
        + "Fine grains and alpha laths were visible in the microstructure. " * 8
        + "\n\nSample A retained a grain structure after processing."
    )
    calls = []
    structure_attempts = 0

    def truncated_structure(_system, _user, *, axis, output_token_budget):
        nonlocal structure_attempts
        calls.append((axis, output_token_budget))
        if axis == "inventory":
            return InventoryResponse(
                anchors=[
                    InventoryAnchor(
                        sample_id_raw="Sample A",
                        role="Target",
                        data_nature="Experimental",
                        source_evidence=["Sample A"],
                        confidence=0.9,
                    )
                ]
            )
        if axis == "structure":
            structure_attempts += 1
            if structure_attempts == 1:
                raise V11RawResponseError(
                    "output_truncated",
                    finish_reason="length",
                    content='{"axis":"structure","facts":[',
                )
            return AxisResponse(axis="structure", facts=[])
        return AxisResponse(axis=axis, facts=[])

    monkeypatch.setenv("KNOWMAT2_ALPHA25_RETRY_OUTPUT_TOKENS", "8192")
    monkeypatch.setenv("KNOWMAT2_ALPHA25_FAILURE_SPLIT_DEPTH", "2")
    monkeypatch.setattr(
        "knowmat.nodes.extraction._invoke_alpha25_task_json", truncated_structure
    )

    # Empty structure leaves intentionally produce no materialized item, but the
    # exception occurs only after coverage has completed and calls are observable.
    try:
        _extract_alpha25_tasks("SYSTEM", paper, {}, ocr_baseline_id="baseline")
    except ValueError as exc:
        assert "produced no evidence-backed items" in str(exc)

    structure_calls = [call for call in calls if call[0] == "structure"]
    assert structure_calls == [("structure", 4096), ("structure", 8192)]


def test_transient_structure_timeout_splits_evidence_but_fails_closed(monkeypatch):
    paper = (
        "Sample A microstructure contained fine grains and alpha laths. "
        + "Fine grains were visible in the microstructure. " * 10
    )
    structure_calls = 0

    def timeout_structure(_system, _user, *, axis, output_token_budget):
        nonlocal structure_calls
        if axis == "inventory":
            return InventoryResponse(anchors=[])
        if axis == "structure":
            structure_calls += 1
            raise TimeoutError("request timed out")
        return AxisResponse(axis=axis, facts=[])

    monkeypatch.setenv("KNOWMAT2_ALPHA25_FAILURE_SPLIT_DEPTH", "3")
    monkeypatch.setattr(
        "knowmat.nodes.extraction._invoke_alpha25_task_json", timeout_structure
    )

    with pytest.raises(V11IncompleteCoverageError):
        _extract_alpha25_tasks("SYSTEM", paper, {}, ocr_baseline_id="baseline")

    # Timeout leaves no trustworthy response.  Retry on progressively smaller
    # source slices up to the configured split depth so a later successful call
    # can recover coverage; with this always-failing stub the four leaf calls
    # still fail closed rather than being accepted as facts.
    assert structure_calls == 7


def test_retry_task_ceiling_bounds_content_failure_fanout(monkeypatch):
    paper = "Sample A had a fine-grained microstructure. " * 80
    structure_calls = 0

    def always_truncated(_system, _user, *, axis, output_token_budget):
        nonlocal structure_calls
        if axis == "inventory":
            return InventoryResponse(anchors=[])
        if axis == "structure":
            structure_calls += 1
            raise V11RawResponseError(
                "output_truncated",
                finish_reason="length",
                content='{"axis":"structure","facts":[',
            )
        return AxisResponse(axis=axis, facts=[])

    monkeypatch.setenv("KNOWMAT2_ALPHA25_RETRY_OUTPUT_TOKENS", "8192")
    monkeypatch.setenv("KNOWMAT2_ALPHA25_FAILURE_SPLIT_DEPTH", "3")
    monkeypatch.setenv("KNOWMAT2_ALPHA25_MAX_RETRY_TASKS", "1")
    monkeypatch.setattr(
        "knowmat.nodes.extraction._invoke_alpha25_task_json", always_truncated
    )

    with pytest.raises(V11IncompleteCoverageError):
        _extract_alpha25_tasks("SYSTEM", paper, {}, ocr_baseline_id="baseline")

    # Three initial structure leaves plus exactly one permitted retry.
    assert structure_calls == 4


def test_inventory_receives_repeated_deterministic_table_labels_as_known_context(
    monkeypatch,
):
    paper = """Table 1 Process combinations
| Sample | Laser power (W) |
|---|---:|
| 1-1 | 250 |

Samples 1-1 and 2-1 were selected. Sample 2-1 had yield strength 900 MPa.
"""
    calls = []

    def fake_invoke(_system, user, *, axis, output_token_budget):
        calls.append((axis, user))
        if axis == "inventory":
            return InventoryResponse(
                anchors=[
                    InventoryAnchor(
                        sample_id_raw="2-1",
                        role="Target",
                        data_nature="Experimental",
                        source_evidence=["2-1"],
                        confidence=0.9,
                    )
                ]
            )
        if axis == "properties" and "yield strength 900 MPa" in user:
            evidence = "yield strength 900 MPa"
            return AxisResponse(
                axis="properties",
                facts=[
                    PropertyFact(
                        sample_id_raw="2-1",
                        data={
                            "property_id_candidate": "temporary",
                            "property_name_raw": "yield strength",
                            "value_raw": "900",
                            "unit_raw": "MPa",
                            "test_method_raw": "",
                            "test_standard_raw": "",
                            "test_condition_raw": "",
                            "test_specimen_raw": "",
                            "raw_note": "",
                            "data_source": "text",
                            "source_evidence": [evidence],
                            "confidence": 0.9,
                        },
                        source_evidence=[evidence],
                        confidence=0.9,
                    )
                ],
            )
        return AxisResponse(axis=axis, facts=[])

    monkeypatch.setenv("KNOWMAT2_ALPHA25_TABLE_CONTEXT_CHARS", "0")
    monkeypatch.setattr(
        "knowmat.nodes.extraction._invoke_alpha25_task_json", fake_invoke
    )

    document, coverage = _extract_alpha25_tasks(
        "SYSTEM", paper, {}, ocr_baseline_id="baseline"
    )

    inventory_prompts = [user for axis, user in calls if axis == "inventory"]
    assert len(inventory_prompts) == 1
    assert '"sample_id_raw": "1-1"' in inventory_prompts[0]
    assert coverage["complete"] is True
    assert {item["Sample_ID"] for item in document["items"]} == {"2-1"}
