from knowmat.alpha25.contracts import AxisResponse, InventoryAnchor, InventoryResponse, PropertyFact
from knowmat.alpha25.verification_pipeline import PaperVerificationResult
from knowmat.nodes.extraction import _extract_alpha25_tasks


def test_hierarchical_verification_is_wired_before_materialization(monkeypatch, tmp_path):
    paper = "Sample A had a yield strength of 900 MPa."
    evidence = paper
    observed = {}

    def fake_invoke(_system, _user, *, axis, output_token_budget):
        del output_token_budget
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
        return AxisResponse(axis=axis, facts=[])

    def fake_verify(anchors, facts, **kwargs):
        rows = list(facts)
        observed["anchors"] = list(anchors)
        observed["facts"] = rows
        observed["source_text"] = kwargs["source_text"]
        observed["field_level"] = kwargs["client"].field_level
        observed["bypass_axes"] = kwargs["bypass_axes"]
        observed["risk_routing_enabled"] = kwargs["risk_routing_enabled"]
        observed["recovery_enabled"] = kwargs["recovery_enabled"]
        return PaperVerificationResult(
            accepted=tuple(rows),
            task_ids=tuple(kwargs["task_ids"]),
            audit_records=(
                {
                    "assertion_id": "assertion-1",
                    "bundle_id": "bundle-1",
                    "decision": "accept",
                    "reason_code": "SOURCE_SUPPORTED",
                },
            ),
            issues=(),
            metrics={
                "verification_assertion_count": 1,
                "verification_bundle_count": 1,
                "accepted_fact_count": 1,
                "recovered_fact_count": 0,
                "provider_calls": 1,
                "fallback_calls": 0,
                "unresolved_bundles": 0,
                "wall_seconds": 0.1,
            },
        )

    monkeypatch.setenv("KNOWMAT2_ALPHA25_HIERARCHICAL_VERIFICATION", "1")
    monkeypatch.setenv("KNOWMAT2_ALPHA25_VERIFIER_FIELD_LEVEL", "1")
    monkeypatch.setenv("KNOWMAT2_ALPHA25_TASK_STRATEGY", "axis_scoped")
    monkeypatch.setenv("KNOWMAT2_ALPHA25_PROMOTION_ENABLED", "0")
    monkeypatch.setattr("knowmat.nodes.extraction._invoke_alpha25_task_json", fake_invoke)
    monkeypatch.setattr("knowmat.nodes.extraction.verify_paper_candidates", fake_verify)

    document, coverage = _extract_alpha25_tasks(
        "SYSTEM",
        paper,
        {},
        cache_dir=tmp_path / "02_alpha25_tasks",
        ocr_baseline_id="baseline",
    )

    assert observed["source_text"] == paper
    assert len(observed["anchors"]) == 1
    assert len(observed["facts"]) == 1
    assert observed["field_level"] is True
    assert observed["bypass_axes"] == ("composition",)
    assert observed["risk_routing_enabled"] is True
    assert observed["recovery_enabled"] is False
    assert document["items"][0]["Sample_ID"] == "Sample A"
    assert coverage["hierarchical_verification_enabled"] is True
    assert coverage["verification_provider_calls"] == 1
    assert coverage["quality_audit_records"][0]["decision"] == "accept"
