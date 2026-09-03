import pytest
from pydantic import ValidationError

from knowmat.alpha25.verification_contracts import (
    AssertionEnvelope,
    COMPACT_REVIEW_PROTOCOL_VERSION,
    COMPACT_LABEL_REVIEW_PROTOCOL_VERSION,
    CompactReviewDecision,
    CompactReviewResponse,
    EvidenceSpan,
    FIELD_VERIFICATION_PROTOCOL_VERSION,
    FieldVerificationDecision,
    FieldVerificationResponse,
    ScientificFieldVerdict,
    InventoryEntity,
    ReassignmentPatch,
    VerificationBundle,
    VerificationDecision,
    VerificationResponse,
    parse_compact_label_array,
    stable_id,
)


def _evidence() -> EvidenceSpan:
    text = "Sample A had a yield strength of 900 MPa."
    return EvidenceSpan(
        evidence_id="ev_1",
        unit_id="unit-1",
        kind="assertion",
        text=text,
        start_char=0,
        end_char=len(text),
    )


def _assertion(assertion_id: str = "as_1") -> AssertionEnvelope:
    return AssertionEnvelope(
        assertion_id=assertion_id,
        axis="properties",
        fact_type="property",
        sample_id_raw="Sample A",
        task_id="task-1",
        evidence_unit_id="unit-1",
        evidence_ids=["ev_1"],
        candidate={"axis": "properties", "sample_id_raw": "Sample A"},
    )


def test_stable_id_is_order_invariant_and_has_no_external_identity():
    left = stable_id("assertion", {"axis": "properties", "data": {"b": 2, "a": 1}})
    right = stable_id("assertion", {"data": {"a": 1, "b": 2}, "axis": "properties"})
    assert left == right
    assert "glm" not in left.casefold()
    assert "paper" not in left.casefold()


def test_evidence_span_requires_literal_length_bounds():
    with pytest.raises(ValidationError, match="literal text length"):
        EvidenceSpan(
            evidence_id="ev_bad",
            kind="assertion",
            text="literal",
            start_char=1,
            end_char=20,
        )


def test_bundle_rejects_composition_and_unknown_evidence():
    assertion = _assertion().model_copy(update={"evidence_ids": ["missing"]})
    with pytest.raises(ValidationError, match="unknown evidence"):
        VerificationBundle(
            bundle_id="bundle-1",
            axis="properties",
            assertions=[assertion],
            evidence=[_evidence()],
            source_char_count=len(_evidence().text),
        )
    with pytest.raises(ValidationError):
        AssertionEnvelope(
            **{**_assertion().model_dump(), "axis": "composition"}
        )


def test_merge_and_reassignment_contracts_are_mutually_exclusive():
    merge = VerificationDecision(
        assertion_id="as_1",
        decision="merge",
        evidence_ids=["ev_1"],
        reason_code="EXACT_DUPLICATE",
        rationale="Both candidates copy the same literal source assertion.",
        merge_member_ids=["as_1", "as_2"],
        survivor_assertion_id="as_1",
    )
    assert merge.decision == "merge"

    reassignment = VerificationDecision(
        assertion_id="as_1",
        decision="reassign",
        evidence_ids=["ev_1"],
        reason_code="OWNER_CORRECTED",
        rationale="The source sentence explicitly names Sample B.",
        reassignment=ReassignmentPatch(
            entity_id="entity-b", sample_id_raw="Sample B"
        ),
    )
    assert reassignment.reassignment.sample_id_raw == "Sample B"

    with pytest.raises(ValidationError, match="merge cannot also reassign"):
        VerificationDecision.model_validate(
            {
                **merge.model_dump(),
                "reassignment": {"sample_id_raw": "Sample B"},
            }
        )


def test_non_unresolved_decision_requires_evidence_and_response_is_unique():
    with pytest.raises(ValidationError, match="accept requires cited evidence"):
        VerificationDecision(
            assertion_id="as_1",
            decision="accept",
            reason_code="SOURCE_SUPPORTED",
            rationale="Supported.",
        )
    decision = VerificationDecision(
        assertion_id="as_1",
        decision="accept",
        evidence_ids=["ev_1"],
        reason_code="SOURCE_SUPPORTED",
        rationale="Supported by the literal sentence.",
    )
    with pytest.raises(ValidationError, match="one primary decision"):
        VerificationResponse(
            bundle_id="bundle-1", decisions=[decision, decision]
        )


def test_inventory_entity_requires_source_evidence():
    with pytest.raises(ValidationError):
        InventoryEntity(
            entity_id="entity-a",
            sample_id_raw="Sample A",
            role="Target",
            data_nature="Experimental",
            evidence_ids=[],
        )


def test_field_verification_response_requires_unique_complete_field_rows():
    decision = FieldVerificationDecision(
        assertion_id="as_1",
        fields=[
            ScientificFieldVerdict(
                field="semantic",
                verdict="supported",
                evidence_ids=["ev_1"],
            ),
            ScientificFieldVerdict(
                field="value",
                verdict="supported",
                evidence_ids=["ev_1"],
            ),
            ScientificFieldVerdict(
                field="unit",
                verdict="supported",
                evidence_ids=["ev_1"],
            ),
            ScientificFieldVerdict(
                field="owner",
                verdict="supported",
                evidence_ids=["ev_1"],
            ),
        ],
        reason_code="ALL_FIELDS_SUPPORTED",
        rationale="Every asserted field is literal in the supplied evidence.",
    )
    response = FieldVerificationResponse(
        protocol_version=FIELD_VERIFICATION_PROTOCOL_VERSION,
        bundle_id="bundle-1",
        decisions=[decision],
    )
    assert response.decisions[0].fields[0].field == "semantic"

    with pytest.raises(ValidationError, match="one verdict per scientific field"):
        FieldVerificationDecision(
            assertion_id="as_1",
            fields=[decision.fields[0], decision.fields[0]],
            reason_code="DUPLICATE_FIELD",
            rationale="Duplicate field on purpose.",
        )


def test_field_verdict_restricts_correction_shape_and_protocol_version():
    corrected_owner = ScientificFieldVerdict(
        field="owner",
        verdict="contradicted",
        evidence_ids=["ev_1"],
        selected_entity_id="entity-b",
        selected_text="Sample B",
    )
    assert corrected_owner.selected_entity_id == "entity-b"

    with pytest.raises(ValidationError, match="correction target"):
        ScientificFieldVerdict(
            field="value",
            verdict="contradicted",
            evidence_ids=["ev_1"],
            selected_text="999",
        )
    with pytest.raises(ValidationError, match="supported field cannot select"):
        ScientificFieldVerdict(
            field="owner",
            verdict="supported",
            evidence_ids=["ev_1"],
            selected_entity_id="entity-a",
        )
    with pytest.raises(ValidationError, match="only a contradicted field"):
        ScientificFieldVerdict(
            field="owner",
            verdict="not_proven",
            evidence_ids=["ev_1"],
            selected_entity_id="entity-a",
        )
    with pytest.raises(ValidationError):
        FieldVerificationResponse(
            protocol_version="alpha25_hierarchical_verification_v1",
            bundle_id="bundle-1",
            decisions=[
                FieldVerificationDecision(
                    assertion_id="as_1",
                    fields=[corrected_owner],
                    reason_code="OWNER_CONTRADICTED",
                    rationale="The source names another supplied owner.",
                )
            ],
        )


def test_compact_review_contract_is_small_strict_and_protocol_isolated():
    decision = CompactReviewDecision(
        assertion_id="as_1",
        verdict="all_fields_supported",
        evidence_ids=["ev_1", "ev_1"],
        reason_code="ALL_FIELDS_SUPPORTED",
    )
    response = CompactReviewResponse(
        protocol_version=COMPACT_REVIEW_PROTOCOL_VERSION,
        bundle_id="bundle-1",
        decisions=[decision],
    )

    assert response.protocol_version != FIELD_VERIFICATION_PROTOCOL_VERSION
    assert response.decisions[0].evidence_ids == ["ev_1"]
    assert response.decisions[0].failed_fields == []
    assert set(response.decisions[0].model_dump()) == {
        "assertion_id",
        "verdict",
        "evidence_ids",
        "failed_fields",
        "reason_code",
    }

    with pytest.raises(ValidationError):
        CompactReviewDecision.model_validate(
            {**decision.model_dump(), "rationale": "not allowed"}
        )


def test_compact_review_contract_rejects_inconsistent_and_duplicate_decisions():
    with pytest.raises(ValidationError, match="failed_fields"):
        CompactReviewDecision(
            assertion_id="as_1",
            verdict="not_proven",
            evidence_ids=["ev_1"],
            reason_code="OWNER_NOT_PROVEN",
        )
    with pytest.raises(ValidationError, match="failed_fields"):
        CompactReviewDecision(
            assertion_id="as_1",
            verdict="all_fields_supported",
            evidence_ids=["ev_1"],
            failed_fields=["owner"],
            reason_code="INCONSISTENT_SUPPORT",
        )

    contradicted = CompactReviewDecision(
        assertion_id="as_1",
        verdict="contradicted",
        evidence_ids=["ev_1"],
        failed_fields=["condition", "owner", "condition"],
        reason_code="OWNER_CONTRADICTED",
    )
    assert contradicted.failed_fields == ["owner", "condition"]
    with pytest.raises(ValidationError, match="one compact decision"):
        CompactReviewResponse(
            bundle_id="bundle-1",
            decisions=[contradicted, contradicted],
        )


def test_compact_label_protocol_accepts_only_exact_cardinality_json_array():
    assert COMPACT_LABEL_REVIEW_PROTOCOL_VERSION != (
        COMPACT_REVIEW_PROTOCOL_VERSION
    )
    assert parse_compact_label_array('["S","C","N"]', label_count=3) == (
        "S",
        "C",
        "N",
    )

    for raw, message in (
        ('["S","C"]', "cardinality"),
        ('["S","C","N","S"]', "cardinality"),
        ('["S","X","N"]', "allowed labels"),
        ('{"labels":["S","C","N"]}', "JSON array"),
        ('analysis\n["S","C","N"]', "valid JSON"),
    ):
        with pytest.raises(ValueError, match=message):
            parse_compact_label_array(raw, label_count=3)


def test_assertion_envelope_carries_stable_source_only_risk_metadata():
    assertion = _assertion().model_copy(
        update={
            "risk_severity": "hard",
            "risk_codes": ["multi_owner_ambiguous", "owner_not_literal"],
        }
    )
    validated = AssertionEnvelope.model_validate(assertion.model_dump())
    assert validated.risk_severity == "hard"
    assert validated.risk_codes == [
        "multi_owner_ambiguous",
        "owner_not_literal",
    ]
    with pytest.raises(ValidationError):
        AssertionEnvelope.model_validate(
            {**validated.model_dump(), "risk_severity": "critical"}
        )
