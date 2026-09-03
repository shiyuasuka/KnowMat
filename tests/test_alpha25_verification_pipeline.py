import json

from knowmat.alpha25.contracts import CompositionFact, PropertyFact
from knowmat.alpha25.verification_client import (
    FIELD_SYSTEM_PROMPT,
    RECOVERY_SYSTEM_PROMPT,
    VerificationClient,
    VerifierRoleConfig,
)
from knowmat.alpha25.verification_contracts import FIELD_VERIFICATION_PROTOCOL_VERSION
from knowmat.alpha25.verification_pipeline import verify_paper_candidates


def _property(evidence: str) -> PropertyFact:
    return PropertyFact(
        sample_id_raw="Sample A",
        evidence_unit_id="unit-a",
        data={
            "property_id_candidate": "temporary",
            "property_name_raw": "yield strength",
            "value_raw": "900",
            "unit_raw": "MPa",
            "test_method_raw": "tensile",
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


def _composition(evidence: str) -> CompositionFact:
    return CompositionFact(
        sample_id_raw="Sample A",
        fact_type="material_identity",
        data={
            "material_family": "alloy",
            "material_name_raw": "Sample A",
            "designation_raw": "Sample A",
            "feedstock_form": None,
        },
        source_evidence=[evidence],
        confidence=0.9,
    )


def _config(role):
    return VerifierRoleConfig(
        role=role,
        model=f"{role}-model",
        endpoint="https://example.invalid/v1",
    )


def test_pipeline_preserves_composition_and_quarantines_noncomposition(tmp_path):
    source = "Sample A alloy was stronger than the reference."
    composition = _composition("Sample A alloy")
    projected = _property(source)

    def invoke(_config, system, user):
        assert system != RECOVERY_SYSTEM_PROMPT
        payload = json.loads(user)
        assertion = payload["assertions"][0]
        return {
            "protocol_version": payload["protocol_version"],
            "bundle_id": payload["bundle_id"],
            "decisions": [
                {
                    "assertion_id": assertion["assertion_id"],
                    "decision": "quarantine",
                    "evidence_ids": [payload["evidence"][0]["evidence_id"]],
                    "reason_code": "NON_LITERAL_SCALAR",
                    "rationale": "No literal numeric value is present.",
                    "merge_member_ids": [],
                    "survivor_assertion_id": None,
                    "reassignment": None,
                }
            ],
        }, {"provider_calls": 1}

    client = VerificationClient(
        _config("primary"),
        _config("fallback"),
        cache_dir=tmp_path,
        invoke_json=invoke,
    )
    result = verify_paper_candidates(
        [],
        [composition, projected],
        source_text=source,
        task_ids=["composition-task", "property-task"],
        client=client,
        recovery_enabled=False,
    )
    assert [row.model_dump() for row in result.accepted] == [composition.model_dump()]
    assert result.task_ids == ("composition-task",)
    assert result.metrics["composition_bypass_count"] == 1
    assert result.metrics["provider_calls"] == 1
    assert result.audit_records[0]["decision"] == "quarantine"


def test_pipeline_unlocated_fact_is_unresolved_without_provider_call(tmp_path):
    source = "Different source."
    fact = _property("Missing evidence.")

    def invoke(*_args):
        raise AssertionError("ungrounded assertions must not reach a provider")

    client = VerificationClient(
        _config("primary"),
        _config("fallback"),
        cache_dir=tmp_path,
        invoke_json=invoke,
    )
    result = verify_paper_candidates(
        [],
        [fact],
        source_text=source,
        task_ids=["property-task"],
        client=client,
        recovery_enabled=False,
    )
    assert result.accepted == (fact,)
    assert result.metrics["provider_calls"] == 0
    assert result.metrics["preserved_unresolved_assertions"] == 1
    assert result.audit_records[0]["reason_code"] == "SOURCE_EVIDENCE_NOT_LOCATED"
    assert result.audit_records[0]["after"] is not None
    assert result.issues[0]["code"] == "verifier_unresolved_preserved"


def test_field_pipeline_isolates_unlocated_hard_risk_without_provider_call(tmp_path):
    source = "Different source."
    evidence = "Sample A yield strength was higher than Sample B."
    fact = _property(evidence)
    data = dict(fact.data)
    data["value_raw"] = "higher than Sample B"
    fact = fact.model_copy(update={"data": data})

    def invoke(*_args):
        raise AssertionError("ungrounded assertions must not reach a provider")

    client = VerificationClient(
        _config("primary"),
        _config("fallback"),
        cache_dir=tmp_path,
        invoke_json=invoke,
        field_level=True,
    )
    result = verify_paper_candidates(
        [],
        [fact],
        source_text=source,
        task_ids=["property-task"],
        client=client,
        recovery_enabled=False,
        bypass_axes=("composition",),
        risk_routing_enabled=True,
    )

    assert result.accepted == ()
    assert result.task_ids == ()
    assert result.metrics["provider_calls"] == 0
    assert result.metrics["field_isolated_assertion_count"] == 1
    assert result.audit_records[0]["protocol_version"] == (
        FIELD_VERIFICATION_PROTOCOL_VERSION
    )
    assert result.audit_records[0]["after"] is None
    assert result.audit_records[0]["formal_action"] == "isolate"
    assert result.issues[0]["code"] == "verifier_technical_failure_isolated"


def test_configured_property_axis_bypasses_verifier_unchanged(tmp_path):
    source = "Sample A had a yield strength of 900 MPa."
    fact = _property(source)

    def invoke(*_args):
        raise AssertionError("a protected property must not reach the verifier")

    client = VerificationClient(
        _config("primary"),
        _config("fallback"),
        cache_dir=tmp_path,
        invoke_json=invoke,
    )
    result = verify_paper_candidates(
        [],
        [fact],
        source_text=source,
        task_ids=["property-task"],
        client=client,
        recovery_enabled=False,
        bypass_axes=("composition", "properties"),
    )

    assert result.accepted == (fact,)
    assert result.task_ids == ("property-task",)
    assert result.metrics["protected_axes"] == ["composition", "properties"]
    assert result.metrics["protected_axis_bypass_count"] == 1
    assert result.metrics["provider_calls"] == 0


def test_pipeline_bisects_only_after_both_roles_fail_a_multi_assertion_bundle(tmp_path):
    first = "Sample A had a yield strength of 900 MPa."
    second = "Sample B had a yield strength of 800 MPa."
    facts = [_property(first), _property(second)]
    second_data = dict(facts[1].data)
    second_data["value_raw"] = "800"
    facts[1] = facts[1].model_copy(
        update={"sample_id_raw": "Sample B", "data": second_data}
    )
    calls = []

    def invoke(config, _system, user):
        payload = json.loads(user)
        calls.append((config.role, len(payload["assertions"])))
        if len(payload["assertions"]) > 1:
            raise RuntimeError("provider timeout")
        assertion = payload["assertions"][0]
        return {
            "protocol_version": payload["protocol_version"],
            "bundle_id": payload["bundle_id"],
            "decisions": [
                {
                    "assertion_id": assertion["assertion_id"],
                    "decision": "accept",
                    "evidence_ids": assertion["evidence_ids"],
                    "reason_code": "SOURCE_SUPPORTED",
                    "rationale": "The isolated assertion is literal.",
                    "merge_member_ids": [],
                    "survivor_assertion_id": None,
                    "reassignment": None,
                }
            ],
        }, {"provider_calls": 1}

    client = VerificationClient(
        _config("primary"),
        _config("fallback"),
        cache_dir=tmp_path,
        invoke_json=invoke,
    )
    result = verify_paper_candidates(
        [],
        facts,
        source_text=first + " " + second,
        task_ids=["task-a", "task-b"],
        client=client,
        max_bundle_assertions=2,
        recovery_enabled=False,
    )

    assert len(result.accepted) == 2
    assert calls == [("primary", 2), ("fallback", 2), ("primary", 1), ("primary", 1)]
    assert result.metrics["split_retry_count"] == 1
    assert result.metrics["attempt_unresolved_bundles"] == 1
    assert result.metrics["unresolved_bundles"] == 0
    assert result.metrics["verification_bundle_count"] == 1
    assert result.metrics["verification_leaf_bundle_count"] == 2


def test_pipeline_does_not_bisect_grounding_or_contract_failures(tmp_path):
    first = "Sample A had a yield strength of 900 MPa."
    second = "Sample B had a yield strength of 800 MPa."
    facts = [_property(first), _property(second)]
    second_data = dict(facts[1].data)
    second_data["value_raw"] = "800"
    facts[1] = facts[1].model_copy(
        update={"sample_id_raw": "Sample B", "data": second_data}
    )
    calls = []

    def invoke(config, _system, user):
        payload = json.loads(user)
        calls.append((config.role, len(payload["assertions"])))
        return {
            "protocol_version": payload["protocol_version"],
            "bundle_id": payload["bundle_id"],
            "decisions": [
                {
                    "assertion_id": row["assertion_id"],
                    "decision": "accept",
                    "evidence_ids": ["invented-evidence"],
                    "reason_code": "BAD_GROUNDING",
                    "rationale": "The citation is intentionally invalid.",
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
        [],
        facts,
        source_text=first + " " + second,
        task_ids=["task-a", "task-b"],
        client=client,
        max_bundle_assertions=2,
        recovery_enabled=False,
    )

    assert calls == [("primary", 2), ("fallback", 2)]
    assert result.metrics["unresolved_bundles"] == 1
    assert result.metrics["split_retry_count"] == 0
    assert result.metrics["split_retry_eligible"] == 0
    assert result.metrics["attempt_unresolved_bundles"] == 1
    assert result.metrics["unresolved_bundles"] == 1
    assert result.metrics["verification_bundle_count"] == 1
    assert result.metrics["verification_leaf_bundle_count"] == 1


def test_pipeline_preflight_splits_before_provider_call(tmp_path):
    first = "Sample A had a yield strength of 900 MPa."
    second = "Sample B had a yield strength of 800 MPa."
    facts = [_property(first), _property(second)]
    second_data = dict(facts[1].data)
    second_data["value_raw"] = "800"
    facts[1] = facts[1].model_copy(
        update={"sample_id_raw": "Sample B", "data": second_data}
    )
    calls = []

    def invoke(config, _system, user):
        payload = json.loads(user)
        calls.append((config.role, len(payload["assertions"])))
        assert len(payload["assertions"]) == 1
        assertion = payload["assertions"][0]
        return {
            "protocol_version": payload["protocol_version"],
            "bundle_id": payload["bundle_id"],
            "decisions": [
                {
                    "assertion_id": assertion["assertion_id"],
                    "decision": "accept",
                    "evidence_ids": assertion["evidence_ids"],
                    "reason_code": "SOURCE_SUPPORTED",
                    "rationale": "The isolated assertion is literal.",
                    "merge_member_ids": [],
                    "survivor_assertion_id": None,
                    "reassignment": None,
                }
            ],
        }, {"provider_calls": 1}

    client = VerificationClient(
        _config("primary"),
        _config("fallback"),
        cache_dir=tmp_path,
        invoke_json=invoke,
    )
    result = verify_paper_candidates(
        [],
        facts,
        source_text=first + " " + second,
        task_ids=["task-a", "task-b"],
        client=client,
        max_bundle_assertions=2,
        preflight_split_assertions=1,
        recovery_enabled=False,
    )

    assert len(result.accepted) == 2
    assert calls == [("primary", 1), ("primary", 1)]
    assert result.metrics["preflight_split_count"] == 1
    assert result.metrics["split_retry_count"] == 0
    assert result.metrics["attempt_unresolved_bundles"] == 0
    assert result.metrics["unresolved_bundles"] == 0
    assert result.metrics["verification_bundle_count"] == 1
    assert result.metrics["verification_leaf_bundle_count"] == 2


def test_field_pipeline_routes_only_hard_property_with_risk_metadata(tmp_path):
    source = (
        "Sample A yield strength was higher than Sample B; "
        "no numeric MPa value was reported."
    )
    fact = _property(source)
    data = dict(fact.data)
    data["value_raw"] = "higher than Sample B"
    fact = fact.model_copy(update={"data": data})
    calls = []

    def invoke(config, system, user):
        payload = json.loads(user)
        calls.append((config.role, system))
        assertion = payload["assertions"][0]
        assert assertion["risk_severity"] == "hard"
        assert "qualitative_scalar_projection" in assertion["risk_codes"]
        fields = []
        for field in payload["required_fields"][assertion["assertion_id"]]:
            fields.append(
                {
                    "field": field,
                    "verdict": "not_proven" if field == "owner" else "supported",
                    "evidence_ids": assertion["evidence_ids"],
                    "selected_entity_id": None,
                    "selected_text": None,
                }
            )
        return {
            "protocol_version": FIELD_VERIFICATION_PROTOCOL_VERSION,
            "bundle_id": payload["bundle_id"],
            "decisions": [
                {
                    "assertion_id": assertion["assertion_id"],
                    "fields": fields,
                    "reason_code": "OWNER_NOT_PROVEN",
                    "rationale": "The source does not uniquely prove the asserted owner.",
                }
            ],
        }, {"provider_calls": 1}

    client = VerificationClient(
        _config("primary"),
        _config("fallback"),
        cache_dir=tmp_path,
        invoke_json=invoke,
        field_level=True,
    )
    result = verify_paper_candidates(
        [],
        [fact],
        source_text=source,
        task_ids=["property-task"],
        client=client,
        recovery_enabled=False,
        bypass_axes=("composition",),
        risk_routing_enabled=True,
    )

    assert result.accepted == ()
    assert calls == [("primary", FIELD_SYSTEM_PROMPT)]
    assert result.metrics["risk_severity_counts"] == {"hard": 1}
    assert result.metrics["field_hard_assertion_count"] == 1
    assert result.metrics["field_secondary_skipped_count"] == 1
    assert result.issues[0]["code"] == "verifier_hard_risk_isolated"


def test_field_pipeline_enforces_precision_configuration_invariants(tmp_path):
    source = "Sample A yield strength was higher than Sample B."
    fact = _property(source)
    data = dict(fact.data)
    data["value_raw"] = "higher than Sample B"
    fact = fact.model_copy(update={"data": data})
    calls = []

    def invoke(config, _system, user):
        payload = json.loads(user)
        calls.append(config.role)
        assertion = payload["assertions"][0]
        return {
            "protocol_version": FIELD_VERIFICATION_PROTOCOL_VERSION,
            "bundle_id": payload["bundle_id"],
            "decisions": [
                {
                    "assertion_id": assertion["assertion_id"],
                    "fields": [
                        {
                            "field": field,
                            "verdict": "not_proven",
                            "evidence_ids": assertion["evidence_ids"],
                            "selected_entity_id": None,
                            "selected_text": None,
                        }
                        for field in payload["required_fields"][
                            assertion["assertion_id"]
                        ]
                    ],
                    "reason_code": "MAPPING_NOT_PROVEN",
                    "rationale": "The comparative mapping is not source-proven.",
                }
            ],
        }, {"provider_calls": 1}

    client = VerificationClient(
        _config("primary"),
        _config("fallback"),
        cache_dir=tmp_path,
        invoke_json=invoke,
        field_level=True,
    )
    result = verify_paper_candidates(
        [],
        [fact],
        source_text=source,
        task_ids=["property-task"],
        client=client,
        max_bundle_assertions=12,
        max_bundle_source_chars=12000,
        recovery_enabled=True,
        bypass_axes=("composition", "properties"),
        risk_routing_enabled=False,
    )

    assert calls == ["primary"]
    assert result.accepted == ()
    assert result.metrics["protected_axes"] == ["composition"]
    assert result.metrics["risk_routing_enabled"] is True
    assert result.metrics["recovered_fact_count"] == 0
