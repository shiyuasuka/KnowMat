import json
from types import SimpleNamespace

import pytest

from knowmat.nodes.v11_normalize import _prepare_candidate, normalize_v11


def _candidate():
    return {
        "Paper_Metadata": {"title": "Example"},
        "Paper_Routing": {
            "base_material": "Metals",
            "application": "Structural",
            "research_paradigm": "Experimental",
        },
        "items": [
            {
                "Item_ID": "item_001",
                "Sample_ID": "A",
                "Role": "Target",
                "Data_Nature": "Experimental",
                "base_material": "Metals",
                "application": "Structural",
                "research_paradigm": "Experimental",
                "Extracted_Data": {
                    "Composition": {
                        "Composition_Text": {
                            "original": "not_reported",
                            "simplified": "not_reported",
                        },
                        "Composition_Observations": [],
                    },
                    "Processing": {
                        "Process_Text": {
                            "original": "not_reported",
                            "simplified": "not_reported",
                        },
                        "Process_Route": {
                            "candidate_stages": [],
                            "candidate_edges": [],
                        },
                    },
                    "Structure": {
                        "Structure_Text": {"original": None, "simplified": None},
                        "structure_status": "not_reported",
                        "Structure_Observations": [],
                    },
                    "Properties": [],
                },
            }
        ],
    }


def test_prepare_candidate_maps_internal_digitized_source_to_public_image_enum():
    candidate = _candidate()
    candidate["items"][0]["Extracted_Data"]["Properties"] = [
        {
            "property_name_raw": "Yield Strength",
            "value_raw": "910",
            "unit_raw": "MPa",
            "data_source": "image_digitized",
        }
    ]

    prepared = _prepare_candidate(candidate, "paper.md")

    prop = prepared["items"][0]["Extracted_Data"]["Properties"][0]
    assert prop["data_source"] == "image"
    assert candidate["items"][0]["Extracted_Data"]["Properties"][0][
        "data_source"
    ] == "image_digitized"


def test_normalize_invokes_alpha25_with_current_ocr_source(monkeypatch, tmp_path):
    source = tmp_path / "paper.md"
    source.write_text("Example OCR", encoding="utf-8")
    output = tmp_path / "paper-output"
    captured = {}

    def fake_run(command, **kwargs):
        captured["command"] = command
        captured["cwd"] = kwargs["cwd"]
        paper_id = command[command.index("--paper-id") + 1]
        validate_dir = command[command.index("--output-dir") + 1]
        from pathlib import Path

        target = Path(validate_dir)
        target.mkdir(parents=True, exist_ok=True)
        (target / f"{paper_id}_normalized.json").write_text(
            json.dumps({**_candidate(), "Rule_Metadata": {"skill_version": "11.0.0-alpha.25"}}),
            encoding="utf-8",
        )
        (target / f"{paper_id}_issues.json").write_text(
            json.dumps({"state": "passed", "fatal_count": 0, "review_count": 0}),
            encoding="utf-8",
        )
        (target / f"{paper_id}_run_metadata.json").write_text(
            json.dumps({"promotable": True}), encoding="utf-8"
        )
        return SimpleNamespace(returncode=0, stdout="passed", stderr="")

    monkeypatch.setattr("knowmat.nodes.v11_normalize.subprocess.run", fake_run)

    result = normalize_v11(
        {
            "latest_extracted_data": _candidate(),
            "paper_text_path": str(source),
            "output_dir": str(output),
            "alpha25_coverage": {"complete": True, "task_count": 2, "rejected_facts": 0},
            "ocr_baseline_id": "baseline-1",
        }
    )

    assert "material-extractor-alpha25-20260804" in str(captured["cwd"])
    assert captured["command"][captured["command"].index("--source-text") + 1] == str(source)
    assert result["v11_promotable"] is True
    assert result["v11_run_metadata"]["coverage_complete"] is True
    assert result["v11_run_metadata"]["ocr_baseline_id"] == "baseline-1"
    quality_audit = json.loads((output / "quality_audit.json").read_text())
    assert quality_audit["schema_version"] == "knowmat_quality_audit_v1"
    assert quality_audit["record_count"] == 0


def test_materialization_audit_is_merged_into_existing_issues(monkeypatch, tmp_path):
    source = tmp_path / "paper.md"
    source.write_text("Example OCR", encoding="utf-8")
    output = tmp_path / "paper-output"

    def fake_run(command, **_kwargs):
        paper_id = command[command.index("--paper-id") + 1]
        validate_dir = command[command.index("--output-dir") + 1]
        from pathlib import Path

        target = Path(validate_dir)
        target.mkdir(parents=True, exist_ok=True)
        (target / f"{paper_id}_normalized.json").write_text(
            json.dumps(
                {
                    **_candidate(),
                    "Rule_Metadata": {"skill_version": "11.0.0-alpha.25"},
                }
            ),
            encoding="utf-8",
        )
        (target / f"{paper_id}_issues.json").write_text(
            json.dumps(
                {
                    "state": "passed",
                    "review_required": False,
                    "fatal_count": 0,
                    "review_count": 0,
                    "issues": [],
                }
            ),
            encoding="utf-8",
        )
        (target / f"{paper_id}_issues.md").write_text(
            "# v11 run issues\n", encoding="utf-8"
        )
        (target / f"{paper_id}_run_metadata.json").write_text(
            json.dumps({"promotable": True}), encoding="utf-8"
        )
        return SimpleNamespace(returncode=0, stdout="passed", stderr="")

    monkeypatch.setattr("knowmat.nodes.v11_normalize.subprocess.run", fake_run)
    before_property = {
        "property_name_raw": "yield strength",
        "value_raw": "900",
        "unit_raw": "MPa",
        "test_condition_raw": "RT",
    }
    after_property = {
        **before_property,
        "test_condition_raw": (
            "RT; Tensile tests were performed at room temperature according "
            "to ASTM E8 at 1 × 10^-3 s^-1."
        ),
    }
    audit_issue = {
        "code": "property_test_context_augmented",
        "severity": "review",
        "path": "items.R1.Properties",
        "message": "A partial test condition was safely augmented.",
        "evidence": [{"line_start": 3, "line_end": 3}],
        "expected": {"overwrite_existing_condition": False},
        "actual": {
            "before": before_property,
            "after": after_property,
            "selected_owner": "R1",
            "rejected_candidates": [
                {"text": "Tensile tests were performed at 650 °C."}
            ],
        },
        "suggested_action": "Review the source line span.",
    }

    result = normalize_v11(
        {
            "latest_extracted_data": _candidate(),
            "paper_text_path": str(source),
            "output_dir": str(output),
            "alpha25_coverage": {
                "complete": True,
                "task_count": 2,
                "rejected_facts": 0,
                "materialization_issues": [audit_issue],
            },
        }
    )

    validation = result["v11_validation"]
    assert validation["state"] == "passed_with_review"
    assert validation["review_count"] == 1
    assert validation["issues"] == [audit_issue]
    issue_path = next((output / "v11" / "04_validate").glob("*_issues.json"))
    assert json.loads(issue_path.read_text(encoding="utf-8"))["issues"] == [audit_issue]
    markdown_path = next((output / "v11" / "04_validate").glob("*_issues.md"))
    markdown = markdown_path.read_text(encoding="utf-8")
    assert "property_test_context_augmented" in markdown
    assert '"test_condition_raw": "RT"' in markdown
    assert '"overwrite_existing_condition": false' in markdown
    assert "Tensile tests were performed at 650 °C." in markdown


def test_incomplete_coverage_never_reaches_alpha25_runner(monkeypatch, tmp_path):
    source = tmp_path / "paper.md"
    source.write_text("Example OCR", encoding="utf-8")
    monkeypatch.setattr(
        "knowmat.nodes.v11_normalize.subprocess.run",
        lambda *_args, **_kwargs: pytest.fail("runner must not be called"),
    )

    with pytest.raises(RuntimeError, match="incomplete task coverage"):
        normalize_v11(
            {
                "latest_extracted_data": _candidate(),
                "paper_text_path": str(source),
                "output_dir": str(tmp_path / "output"),
                "alpha25_coverage": {"complete": False},
            }
        )


def test_minimal_candidate_runs_through_checked_in_alpha25(tmp_path):
    source = tmp_path / "paper.md"
    source.write_text("Example OCR with no extractable quantitative facts.", encoding="utf-8")

    result = normalize_v11(
        {
            "latest_extracted_data": _candidate(),
            "paper_text_path": str(source),
            "output_dir": str(tmp_path / "actual-alpha25"),
            "alpha25_coverage": {
                "complete": True,
                "task_count": 1,
                "rejected_facts": 0,
            },
            "ocr_baseline_id": "test-baseline",
        }
    )

    assert result["final_data"]["Rule_Metadata"]["skill_version"] == "11.0.0-alpha.25"
    assert result["v11_validation"]["fatal_count"] == 0
    assert result["v11_promotable"] is True


def test_negative_composition_percent_ocr_sign_is_corrected_with_audit(tmp_path):
    source = tmp_path / "paper.md"
    source.write_text(
        "The maximum concentration of Co inside the nanolayer can reach "
        "-50.64 ± 1.23 at. %.",
        encoding="utf-8",
    )
    candidate = _candidate()
    candidate["items"][0]["Extracted_Data"]["Composition"] = {
        "Composition_Text": {
            "original": "Co: -50.64 ± 1.23 at. %",
            "simplified": "Co: -50.64 ± 1.23 at. %",
        },
        "Composition_Observations": [
            {
                "observation_id": "comp_obs_001",
                "raw_expression": "Co: -50.64 ± 1.23 at. %",
                "basis": "at%",
                "component_type": "elemental",
                "source_type": "provided",
                "data_source": "text",
                "source_evidence": [
                    "The maximum concentration of Co inside the nanolayer can reach -50.64 ± 1.23 at. %."
                ],
                "components": [
                    {
                        "name_raw": "Co",
                        "canonical_name": "Co",
                        "unit_raw": "at. %",
                        "canonical_unit": "at%",
                        "value_raw": "-50.64 ± 1.23",
                        "value": -50.64,
                        "value_kind": "scalar",
                        "value_stddev": 1.23,
                        "data_nature": "reported",
                    }
                ],
            }
        ],
    }

    result = normalize_v11(
        {
            "latest_extracted_data": candidate,
            "paper_text_path": str(source),
            "output_dir": str(tmp_path / "negative-percent"),
            "alpha25_coverage": {
                "complete": True,
                "task_count": 1,
                "rejected_facts": 0,
            },
        }
    )

    composition = result["final_data"]["items"][0]["Extracted_Data"]["Composition"]
    component = composition["Composition_Observations"][0]["components"][0]
    assert component["value"] == 50.64
    assert component["value_raw"] == "-50.64 ± 1.23"
    assert result["v11_validation"]["fatal_count"] == 0
    audit_path = next(
        (tmp_path / "negative-percent" / "v11" / "04_validate").glob(
            "*_normalization_log.json"
        )
    )
    audit = json.loads(audit_path.read_text(encoding="utf-8"))
    assert any(
        row.get("rule_id") == "composition.negative_percentage_sign_corrected_v1"
        for row in audit
    )


def test_bare_tensile_method_is_normalized_as_direct_core_tensile(tmp_path):
    evidence = "The tensile yield strength of sample A was 900 MPa."
    source = tmp_path / "paper.md"
    source.write_text(evidence, encoding="utf-8")
    candidate = _candidate()
    candidate["items"][0]["Extracted_Data"]["Properties"] = [
        {
            "property_id_candidate": "prop_001",
            "property_name_raw": "yield strength",
            "value_raw": "900",
            "unit_raw": "MPa",
            # Compact extractors commonly emit the explicit method class as
            # this bare value. It is method metadata, not a property-name
            # inference, and must remain sufficient for the frozen tensile
            # rules to recognize a direct uniaxial experiment.
            "test_method_raw": "tensile",
            "test_standard_raw": "",
            "test_condition_raw": "",
            "test_specimen_raw": "",
            "raw_note": "",
            "data_source": "text",
            "source_evidence": [evidence],
            "confidence": 0.95,
        }
    ]

    result = normalize_v11(
        {
            "latest_extracted_data": candidate,
            "paper_text_path": str(source),
            "output_dir": str(tmp_path / "bare-tensile"),
            "alpha25_coverage": {
                "complete": True,
                "task_count": 1,
                "rejected_facts": 0,
            },
            "ocr_baseline_id": "test-baseline",
        }
    )

    prop = result["final_data"]["items"][0]["Extracted_Data"]["Properties"][0]
    assert prop["Test_Condition"]["test_method_raw"] == "tensile"
    assert prop["Test_Condition"]["test_method_class"] == "uniaxial_tensile"
    assert prop["Observation_Origin"] == "direct_experiment"
    assert prop["semantic_decision"] == "accept_core_tensile"


def test_orientation_is_not_inferred_from_evidence_when_condition_is_missing(
    tmp_path,
):
    evidence = "The horizontal specimen had a fatigue strength of 500 MPa."
    source = tmp_path / "paper.md"
    source.write_text(evidence, encoding="utf-8")
    candidate = _candidate()
    candidate["items"][0]["Extracted_Data"]["Properties"] = [
        {
            "property_id_candidate": "prop_001",
            "property_name_raw": "fatigue strength",
            "value_raw": "500",
            "unit_raw": "MPa",
            "test_method_raw": "fatigue",
            "test_standard_raw": "",
            "test_condition_raw": "",
            "test_specimen_raw": "",
            "raw_note": "",
            "data_source": "text",
            "source_evidence": [evidence],
            "confidence": 0.95,
        }
    ]

    result = normalize_v11(
        {
            "latest_extracted_data": candidate,
            "paper_text_path": str(source),
            "output_dir": str(tmp_path / "missing-condition-orientation"),
            "alpha25_coverage": {
                "complete": True,
                "task_count": 1,
                "rejected_facts": 0,
            },
            "ocr_baseline_id": "test-baseline",
        }
    )

    prop = result["final_data"]["items"][0]["Extracted_Data"]["Properties"][0]
    condition = prop["Test_Condition"]
    assert result["v11_validation"]["fatal_count"] == 0
    assert condition["condition_status"] == "not_reported"
    assert "orientation_raw" not in condition
    assert "Orientation" not in condition


def test_bare_tensile_method_does_not_override_non_direct_provenance(tmp_path):
    literature_evidence = (
        "A previous study reported a tensile yield strength of 700 MPa."
    )
    analytical_evidence = (
        "The tensile yield strength was estimated as 800 MPa using an analytical model."
    )
    source = tmp_path / "paper.md"
    source.write_text(
        literature_evidence + "\n" + analytical_evidence,
        encoding="utf-8",
    )
    candidate = _candidate()

    def property_candidate(
        property_id: str,
        value: str,
        evidence: str,
        *,
        data_nature: str,
        raw_note: str = "",
    ):
        return {
            "property_id_candidate": property_id,
            "property_name_raw": "yield strength",
            "value_raw": value,
            "unit_raw": "MPa",
            "test_method_raw": "tensile",
            "test_standard_raw": "",
            "test_condition_raw": "",
            "test_specimen_raw": "",
            "raw_note": raw_note,
            "data_source": "text",
            "data_nature": data_nature,
            "source_evidence": [evidence],
            "confidence": 0.95,
        }

    candidate["items"][0]["Extracted_Data"]["Properties"] = [
        property_candidate(
            "prop_001",
            "700",
            literature_evidence,
            data_nature="Literature_Experimental",
        ),
        property_candidate(
            "prop_002",
            "800",
            analytical_evidence,
            data_nature="Computed",
            raw_note="estimated using an analytical model",
        ),
    ]

    result = normalize_v11(
        {
            "latest_extracted_data": candidate,
            "paper_text_path": str(source),
            "output_dir": str(tmp_path / "non-direct-tensile"),
            "alpha25_coverage": {
                "complete": True,
                "task_count": 1,
                "rejected_facts": 0,
            },
            "ocr_baseline_id": "test-baseline",
        }
    )

    properties = result["final_data"]["items"][0]["Extracted_Data"]["Properties"]
    assert [prop["Observation_Origin"] for prop in properties] == [
        "literature_experimental",
        "analytical_estimate",
    ]
    assert all(
        prop["semantic_decision"] == "reject_non_direct_tensile"
        for prop in properties
    )
