import json

from knowmat.alpha25.contracts import (
    InventoryAnchor,
    ProcessingFact,
    PropertyFact,
    StructureFact,
)
from knowmat.alpha25.verification_client import VerificationClient, VerifierRoleConfig
from knowmat.alpha25.verification_pipeline import verify_paper_candidates
from knowmat.alpha25.verification_risk import classify_verification_risks


def _anchor(owner: str) -> InventoryAnchor:
    return InventoryAnchor(
        sample_id_raw=owner,
        role="Target",
        data_nature="Experimental",
        source_evidence=[owner],
        confidence=0.9,
    )


def _structure(owner: str, evidence: str) -> StructureFact:
    return StructureFact(
        sample_id_raw=owner,
        fact_type="structure_observation",
        data={
            "observation_id": "temporary",
            "structure_kind": "precipitate",
            "material_state": "not_reported",
            "sample_id": owner,
            "source_type": "reported",
            "original": evidence,
            "simplified": evidence,
            "entities": [
                {
                    "name_raw": "gamma precipitates",
                    "role": "precipitates",
                    "raw_expression": "gamma precipitates",
                    "features": [],
                }
            ],
            "features": [
                {
                    "feature_name_raw": "size",
                    "value_kind": "scalar",
                    "value_raw": "50",
                    "unit_raw": "nm",
                    "data_nature": "reported",
                }
            ],
            "source_evidence": [evidence],
        },
        source_evidence=[evidence],
        confidence=0.9,
    )


def _config(role: str) -> VerifierRoleConfig:
    return VerifierRoleConfig(
        role=role,
        model=f"{role}-model",
        endpoint="https://example.invalid/v1",
    )


def _property(owner: str, value: str, evidence: str, *, condition: str = ""):
    return PropertyFact(
        sample_id_raw=owner,
        fact_type="property",
        data={
            "property_id_candidate": "temporary",
            "property_name_raw": "yield strength",
            "value_raw": value,
            "unit_raw": "MPa",
            "test_method_raw": "tensile",
            "test_standard_raw": "",
            "test_condition_raw": condition,
            "test_specimen_raw": "",
            "raw_note": "",
            "data_source": "text",
            "source_evidence": [evidence],
            "confidence": 0.9,
        },
        source_evidence=[evidence],
        confidence=0.9,
    )


def test_literal_single_owner_structure_bypasses_verifier():
    fact = _structure(
        "Sample A", "Sample A contained gamma precipitates of size 50 nm."
    )

    decision = classify_verification_risks([fact], [_anchor("Sample A")])[0]

    assert decision.route_to_verifier is False
    assert decision.severity == "none"
    assert decision.risk_codes == ()


def test_mixed_nonliteral_structure_payload_routes_to_verifier():
    fact = _structure(
        "Sample A", "Sample B contained gamma precipitates of size 50 nm."
    )
    fact.data["entities"][0]["name_raw"] = "unsupported phase"
    fact.source_evidence.append("Additional characterization context was reported.")
    fact.data["source_evidence"].append(
        "Additional characterization context was reported."
    )

    decision = classify_verification_risks(
        [fact], [_anchor("Sample A"), _anchor("Sample B")]
    )[0]

    assert decision.route_to_verifier is True
    assert decision.severity == "hard"
    assert "owner_not_literal" in decision.risk_codes
    assert "nonliteral_payload_field" in decision.risk_codes


def test_comparative_value_with_unstated_owner_routes_to_verifier():
    fact = _structure(
        "LPBF",
        "compared to the fusion technologies with an average grain diameter "
        "of 57 µm, measured using the line intercept method.",
    )
    fact.data["entities"] = []
    fact.data["features"] = [
        {
            "feature_name_raw": "average grain diameter",
            "value_kind": "scalar",
            "value_raw": "57",
            "unit_raw": "µm",
            "data_nature": "reported",
        }
    ]

    decision = classify_verification_risks(
        [fact], [_anchor("LPBF"), _anchor("Binder Jetting")]
    )[0]

    assert decision.route_to_verifier is True
    assert decision.severity == "hard"
    assert "owner_not_literal" in decision.risk_codes
    assert "comparative_owner_projection" in decision.risk_codes


def test_state_label_misclassified_as_process_routes_to_verifier():
    evidence = "The as-printed and aged alloys were compared."
    fact = ProcessingFact(
        sample_id_raw="as-printed",
        fact_type="process_stage",
        data={
            "candidate_stage_id": "temporary",
            "stage_index_candidate": 0,
            "process_name_raw": "as-printed",
            "process_code_candidate": None,
            "process_role_candidate": None,
            "parameters_raw": [],
            "source_evidence": [evidence],
            "confidence": 0.4,
        },
        source_evidence=[evidence],
        confidence=0.4,
    )

    decision = classify_verification_risks([fact], [])[0]

    assert "state_as_process" in decision.risk_codes
    assert "low_confidence" in decision.risk_codes
    assert decision.severity == "hard"


def test_same_payload_with_separate_literal_owner_sentences_is_not_hard_risk():
    evidence_a = "Sample A contained gamma precipitates of size 50 nm."
    evidence_b = "Sample B contained gamma precipitates of size 50 nm."
    facts = [_structure("Sample A", evidence_a), _structure("Sample B", evidence_b)]

    decisions = classify_verification_risks(
        facts, [_anchor("Sample A"), _anchor("Sample B")]
    )

    assert all(
        "cross_owner_duplicate_payload" in decision.risk_codes
        for decision in decisions
    )
    assert all(decision.severity != "hard" for decision in decisions)


def test_respectively_mapping_with_incompatible_owner_value_projection_is_hard():
    evidence = (
        "Sample A and Sample B had yield strengths of 900 and 800 MPa, "
        "respectively."
    )
    projected = _property("Sample A", "800", evidence)

    decision = classify_verification_risks(
        [projected], [_anchor("Sample A"), _anchor("Sample B")]
    )[0]

    assert decision.severity == "hard"
    assert "respectively_mapping_ambiguous" in decision.risk_codes


def test_explicit_collective_same_value_mapping_is_not_hard():
    evidence = "Both Sample A and Sample B had a yield strength of 900 MPa."
    facts = [
        _property("Sample A", "900", evidence),
        _property("Sample B", "900", evidence),
    ]

    decisions = classify_verification_risks(
        facts, [_anchor("Sample A"), _anchor("Sample B")]
    )

    assert all(decision.severity != "hard" for decision in decisions)
    assert all(
        "explicit_collective_mapping" in decision.risk_codes
        for decision in decisions
    )


def test_source_locator_or_qualitative_scalar_property_is_hard():
    locator = _property(
        "Sample A",
        "digitized from Fig. 10",
        "Sample A yield strength was digitized from Fig. 10.",
    )
    qualitative = _property(
        "Sample A",
        "higher than Sample B",
        "Sample A had higher yield strength than Sample B.",
    )

    decisions = classify_verification_risks(
        [locator, qualitative], [_anchor("Sample A"), _anchor("Sample B")]
    )

    assert [row.severity for row in decisions] == ["hard", "hard"]
    assert "source_locator_scalar" in decisions[0].risk_codes
    assert "qualitative_scalar_projection" in decisions[1].risk_codes


def test_direct_literal_core_tensile_with_unique_owner_bypasses():
    evidence = "Sample A had a yield strength of 900 ± 10 MPa at room temperature."
    fact = _property("Sample A", "900 ± 10", evidence, condition="room temperature")

    decision = classify_verification_risks([fact], [_anchor("Sample A")])[0]

    assert decision.severity == "none"
    assert decision.route_to_verifier is False


def test_literal_composite_owner_alias_is_not_treated_as_conflicting_entity():
    evidence = "In the X orientation, LPBF reached a yield strength of 900 MPa."
    fact = _property("LPBF / X", "900", evidence)

    decision = classify_verification_risks(
        [fact], [_anchor("LPBF"), _anchor("LPBF / X")]
    )[0]

    assert decision.severity == "none"
    assert "owner_conflicts_with_literal_entity" not in decision.risk_codes
    assert "comparative_owner_projection" not in decision.risk_codes


def test_short_owner_alias_does_not_match_inside_sample_word():
    evidence = "| Sample | Laser power (W) |\n| PL | 800 |"
    fact = ProcessingFact(
        sample_id_raw="PL",
        fact_type="process_stage",
        data={
            "candidate_stage_id": "temporary",
            "stage_index_candidate": 0,
            "process_name_raw": "LPBF",
            "process_code_candidate": None,
            "process_role_candidate": None,
            "parameters_raw": [
                {
                    "parameter_name_raw": "laser power",
                    "value_raw": "800",
                    "unit_raw": "W",
                }
            ],
            "source_evidence": evidence.splitlines(),
            "confidence": 1.0,
        },
        source_evidence=evidence.splitlines(),
        confidence=1.0,
    )

    decision = classify_verification_risks(
        [fact], [_anchor("PL"), _anchor("CL")]
    )[0]

    assert decision.severity == "none"
    assert "multi_owner_evidence" not in decision.risk_codes
    assert "owner_not_literal" not in decision.risk_codes


def test_direct_latex_unit_table_row_bypasses_verifier():
    evidence = (
        "| Sample | Exposure time ($ \\mu $s) | Layer thickness ($ \\mu $m) |\n"
        "| PL | 50 | 30 |"
    )
    fact = ProcessingFact(
        sample_id_raw="PL",
        fact_type="process_stage",
        data={
            "candidate_stage_id": "temporary",
            "stage_index_candidate": 0,
            "process_name_raw": "LPBF",
            "process_code_candidate": None,
            "process_role_candidate": None,
            "parameters_raw": [
                {
                    "parameter_name_raw": "exposure time",
                    "value_raw": "50",
                    "unit_raw": "µs",
                },
                {
                    "parameter_name_raw": "layer thickness",
                    "value_raw": "30",
                    "unit_raw": "µm",
                },
            ],
            "source_evidence": evidence.splitlines(),
            "confidence": 1.0,
        },
        source_evidence=evidence.splitlines(),
        confidence=1.0,
    )

    decision = classify_verification_risks(
        [fact], [_anchor("PL"), _anchor("CL")]
    )[0]

    assert decision.route_to_verifier is False
    assert decision.severity == "none"
    assert "nonliteral_payload_field" not in decision.risk_codes


def test_collective_owner_with_unlinked_payload_is_hard():
    evidence = "Both samples were fabricated with a 67° interlayer rotation."
    fact = ProcessingFact(
        sample_id_raw="CL",
        fact_type="process_stage",
        data={
            "candidate_stage_id": "temporary",
            "stage_index_candidate": 0,
            "process_name_raw": "LPBF",
            "process_code_candidate": None,
            "process_role_candidate": None,
            "parameters_raw": [
                {
                    "parameter_name_raw": "interlayer rotation",
                    "value_raw": "67",
                    "unit_raw": "°",
                },
                {
                    "parameter_name_raw": "laser mode",
                    "value_raw": "continuous",
                    "unit_raw": "",
                },
            ],
            "source_evidence": [evidence],
            "confidence": 0.95,
        },
        source_evidence=[evidence],
        confidence=0.95,
    )

    decision = classify_verification_risks(
        [fact], [_anchor("PL"), _anchor("CL")]
    )[0]

    assert decision.severity == "hard"
    assert "collective_payload_projection" in decision.risk_codes


def test_literal_source_text_fragment_does_not_consume_verifier_budget():
    evidence = "EPBF and LPBF samples were cut from the plate before HIPing."
    fact = ProcessingFact(
        sample_id_raw="not_reported",
        fact_type="process_text",
        data={"original": evidence, "simplified": evidence},
        source_evidence=[evidence],
        confidence=0.9,
    )

    decision = classify_verification_risks(
        [fact], [_anchor("EPBF"), _anchor("LPBF")]
    )[0]

    assert decision.severity == "none"
    assert decision.route_to_verifier is False


def test_processing_respectively_parameter_mapping_is_hard_condition_risk():
    evidence = (
        "Sample A was treated at 800 and 1000 °C for 1 and 2 h, respectively."
    )
    fact = ProcessingFact(
        sample_id_raw="Sample A",
        fact_type="process_stage",
        data={
            "candidate_stage_id": "temporary",
            "stage_index_candidate": 0,
            "process_name_raw": "heat treatment",
            "process_code_candidate": None,
            "process_role_candidate": None,
            "parameters_raw": [
                {
                    "parameter_name_raw": "temperature",
                    "value_raw": "1000",
                    "unit_raw": "°C",
                },
                {
                    "parameter_name_raw": "time",
                    "value_raw": "1",
                    "unit_raw": "h",
                },
            ],
            "source_evidence": [evidence],
            "confidence": 0.9,
        },
        source_evidence=[evidence],
        confidence=0.9,
    )

    decision = classify_verification_risks([fact], [_anchor("Sample A")])[0]

    assert decision.severity == "hard"
    assert "respectively_condition_mapping_ambiguous" in decision.risk_codes


def test_nonliteral_structure_region_in_comparative_evidence_is_hard():
    evidence = (
        "Sample A showed 50 and 100 nm grains in the boundary and bulk regions, "
        "respectively."
    )
    fact = _structure("Sample A", evidence)
    fact.data["region"] = "heat-affected zone"
    fact.data["features"][0]["value_raw"] = "100"

    decision = classify_verification_risks([fact], [_anchor("Sample A")])[0]

    assert decision.severity == "hard"
    assert "multi_condition_projection" in decision.risk_codes


def test_nonliteral_structure_state_in_multi_state_evidence_is_hard():
    evidence = (
        "Sample A showed 50 and 100 nm grains in the as-built and aged states, "
        "respectively."
    )
    fact = _structure("Sample A", evidence)
    fact.data["material_state"] = "solution-treated"
    fact.data["features"][0]["value_raw"] = "100"

    decision = classify_verification_risks([fact], [_anchor("Sample A")])[0]

    assert decision.severity == "hard"
    assert "multi_condition_projection" in decision.risk_codes


def test_pipeline_calls_provider_only_for_risk_routed_fact(tmp_path):
    low = _structure(
        "Sample A", "Sample A contained gamma precipitates of size 50 nm."
    )
    high = _structure(
        "Sample A", "Sample B contained gamma precipitates of size 50 nm."
    )
    high.data["entities"][0]["name_raw"] = "unsupported phase"
    high.source_evidence.append("Additional characterization context was reported.")
    high.data["source_evidence"].append(
        "Additional characterization context was reported."
    )
    calls = []

    def invoke(_config, _system, user):
        payload = json.loads(user)
        calls.append([row["assertion_id"] for row in payload["assertions"]])
        return {
            "protocol_version": payload["protocol_version"],
            "bundle_id": payload["bundle_id"],
            "decisions": [
                {
                    "assertion_id": row["assertion_id"],
                    "decision": "accept",
                    "evidence_ids": row["evidence_ids"],
                    "reason_code": "SOURCE_SUPPORTED",
                    "rationale": "The isolated assertion is source-supported.",
                    "merge_member_ids": [],
                    "survivor_assertion_id": None,
                    "reassignment": None,
                }
                for row in payload["assertions"]
            ],
        }, {"provider_calls": 1}

    client = VerificationClient(
        _config("primary"),
        _config("fallback"),
        cache_dir=tmp_path,
        invoke_json=invoke,
    )
    result = verify_paper_candidates(
        [_anchor("Sample A"), _anchor("Sample B")],
        [low, high],
        source_text=" ".join([*low.source_evidence, *high.source_evidence]),
        task_ids=["low-task", "high-task"],
        client=client,
        recovery_enabled=False,
        bypass_axes=("composition", "properties"),
        risk_routing_enabled=True,
    )

    assert len(calls) == 1
    assert len(calls[0]) == 1
    assert result.accepted == (low, high)
    assert result.task_ids == ("low-task", "high-task")
    assert result.metrics["risk_routing_enabled"] is True
    assert result.metrics["risk_routed_fact_count"] == 1
    assert result.metrics["deterministic_low_risk_bypass_count"] == 1
