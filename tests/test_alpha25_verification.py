import pytest

from knowmat.alpha25.contracts import (
    InventoryAnchor,
    ProcessingFact,
    PropertyFact,
    StructureFact,
)
from knowmat.alpha25.verification import (
    VerificationGroundingError,
    apply_field_consensus,
    _source_supports_quote,
    preserve_failed_bundle_result,
    required_scientific_fields,
    unresolved_bundle_result,
    validate_and_apply_bundle,
    validate_compact_review_response,
    validate_field_response,
    validate_recovery_response,
)
from knowmat.alpha25.verification_contracts import (
    COMPACT_REVIEW_PROTOCOL_VERSION,
    CompactReviewDecision,
    CompactReviewResponse,
    FIELD_VERIFICATION_PROTOCOL_VERSION,
    FieldVerificationDecision,
    FieldVerificationResponse,
    ReassignmentPatch,
    RecoveryProposal,
    RecoveryRequest,
    RecoveryResponse,
    VerificationDecision,
    VerificationResponse,
    ScientificFieldVerdict,
)
from knowmat.alpha25.verification_inventory import (
    build_verification_bundles,
    build_verification_inventory,
)


def _property(owner: str, value: str, evidence: str, *, condition: str = "") -> PropertyFact:
    return PropertyFact(
        sample_id_raw=owner,
        evidence_unit_id="unit-properties",
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
            "confidence": 0.8,
        },
        source_evidence=[evidence],
        confidence=0.8,
    )


def _anchor(owner: str, evidence: str) -> InventoryAnchor:
    return InventoryAnchor(
        sample_id_raw=owner,
        role="Target",
        data_nature="Experimental",
        source_evidence=[evidence],
        confidence=0.9,
    )


def _processing(owner: str, evidence: str) -> ProcessingFact:
    return ProcessingFact(
        sample_id_raw=owner,
        evidence_unit_id="unit-processing",
        fact_type="process_stage",
        data={
            "candidate_stage_id": "temporary",
            "stage_index_candidate": 0,
            "process_name_raw": "laser powder bed fusion",
            "process_code_candidate": None,
            "process_role_candidate": "primary_forming",
            "parameters_raw": [
                {
                    "parameter_name_raw": "laser power",
                    "value_raw": "400",
                    "unit_raw": "W",
                    "source_evidence": evidence,
                }
            ],
            "source_evidence": [evidence],
            "confidence": 0.9,
        },
        source_evidence=[evidence],
        confidence=0.9,
    )


def _structure(owner: str, evidence: str) -> StructureFact:
    return StructureFact(
        sample_id_raw=owner,
        evidence_unit_id="unit-structure",
        fact_type="structure_observation",
        data={
            "observation_id": "temporary",
            "structure_kind": "grain",
            "material_state": "as-built",
            "sample_id": owner,
            "source_type": "reported",
            "original": evidence,
            "simplified": evidence,
            "region": "melt-pool boundary",
            "entities": [],
            "features": [
                {
                    "feature_name_raw": "grain size",
                    "value_kind": "scalar",
                    "value_raw": "2.3",
                    "unit_raw": "µm",
                    "data_nature": "reported",
                }
            ],
            "source_evidence": [evidence],
        },
        source_evidence=[evidence],
        confidence=0.9,
    )


def _case(facts, source, anchors=None):
    inventory = build_verification_inventory(
        anchors or [],
        facts,
        source_text=source,
        task_ids=[f"task-{index}" for index in range(len(facts))],
    )
    bundle = build_verification_bundles(
        inventory, source_text=source, context_radius=200
    )[0]
    return inventory, bundle


def _evidence_ids(bundle):
    return [row.evidence_id for row in bundle.evidence]


def _with_risk(bundle, severity, *codes):
    return bundle.model_copy(
        update={
            "assertions": [
                row.model_copy(
                    update={
                        "risk_severity": severity,
                        "risk_codes": list(codes),
                    }
                )
                for row in bundle.assertions
            ]
        }
    )


def _field_response(bundle, *, verdict="supported", owner_target=None):
    decisions = []
    for assertion in bundle.assertions:
        fields = []
        for field in ("semantic", "value", "unit", "owner"):
            row_verdict = verdict if field == "owner" and owner_target else "supported"
            fields.append(
                ScientificFieldVerdict(
                    field=field,
                    verdict=row_verdict,
                    evidence_ids=_evidence_ids(bundle),
                    selected_entity_id=(
                        owner_target.entity_id
                        if field == "owner" and owner_target is not None
                        else None
                    ),
                    selected_text=(
                        owner_target.sample_id_raw
                        if field == "owner" and owner_target is not None
                        else None
                    ),
                )
            )
        decisions.append(
            FieldVerificationDecision(
                assertion_id=assertion.assertion_id,
                fields=fields,
                reason_code=(
                    "OWNER_REASSIGNMENT" if owner_target else "ALL_FIELDS_SUPPORTED"
                ),
                rationale="Field-level source review completed.",
            )
        )
    return FieldVerificationResponse(
        protocol_version=FIELD_VERIFICATION_PROTOCOL_VERSION,
        bundle_id=bundle.bundle_id,
        decisions=decisions,
    )


def test_accept_passes_candidate_unchanged_and_has_full_audit():
    source = "Sample A had a yield strength of 900 MPa."
    fact = _property("Sample A", "900", source)
    inventory, bundle = _case([fact], source, [_anchor("Sample A", "Sample A")])
    assertion = bundle.assertions[0]
    response = VerificationResponse(
        bundle_id=bundle.bundle_id,
        decisions=[
            VerificationDecision(
                assertion_id=assertion.assertion_id,
                decision="accept",
                evidence_ids=_evidence_ids(bundle),
                reason_code="SOURCE_SUPPORTED",
                rationale="The owner, value, and unit are literal.",
            )
        ],
    )
    result = validate_and_apply_bundle(bundle, response, inventory)
    assert [row.model_dump() for row in result.accepted] == [fact.model_dump()]
    assert result.audit_records[0]["before"] == fact.model_dump(mode="json")
    assert result.audit_records[0]["after"] == fact.model_dump(mode="json")
    assert result.issues == ()


def test_accept_completes_only_linked_candidate_evidence_citations():
    first = "Sample A had a yield strength of 900 MPa."
    second = "The tensile result was measured at room temperature."
    source = first + " " + second
    fact = _property("Sample A", "900", first)
    payload = fact.model_dump()
    payload["source_evidence"] = [first, second]
    payload["data"]["source_evidence"] = [first, second]
    fact = PropertyFact.model_validate(payload)
    inventory, bundle = _case([fact], source, [_anchor("Sample A", "Sample A")])
    assertion = bundle.assertions[0]
    first_id = next(row.evidence_id for row in bundle.evidence if row.text == first)
    response = VerificationResponse(
        bundle_id=bundle.bundle_id,
        decisions=[
            VerificationDecision(
                assertion_id=assertion.assertion_id,
                decision="accept",
                evidence_ids=[first_id],
                reason_code="SOURCE_SUPPORTED",
                rationale="The decisive value span is literal.",
            )
        ],
    )

    result = validate_and_apply_bundle(bundle, response, inventory)

    assert result.accepted == (fact,)
    assert {row["text"] for row in result.audit_records[0]["evidence"]} == {
        first,
        second,
    }


def test_quarantine_and_unresolved_never_enter_formal_facts():
    source = "Sample A was described as stronger than Sample B."
    fact = _property("Sample A", "900", source)
    inventory, bundle = _case([fact], source)
    assertion = bundle.assertions[0]
    response = VerificationResponse(
        bundle_id=bundle.bundle_id,
        decisions=[
            VerificationDecision(
                assertion_id=assertion.assertion_id,
                decision="quarantine",
                evidence_ids=_evidence_ids(bundle),
                reason_code="NON_LITERAL_SCALAR",
                rationale="The source contains no 900 MPa scalar.",
            )
        ],
    )
    result = validate_and_apply_bundle(bundle, response, inventory)
    assert result.accepted == ()
    assert result.issues[0]["code"] == "verifier_quarantine"

    unresolved = unresolved_bundle_result(
        bundle,
        inventory,
        reason_code="VERIFIERS_FAILED",
        rationale="Both configured verifier roles failed.",
        fallback_used=True,
    )
    assert unresolved.accepted == ()
    assert unresolved.audit_records[0]["fallback_used"] is True


def test_role_failure_preserves_candidate_but_marks_it_unresolved_for_review():
    source = "Sample A had a yield strength of 900 MPa."
    fact = _property("Sample A", "900", source)
    inventory, bundle = _case([fact], source)

    result = preserve_failed_bundle_result(
        bundle,
        inventory,
        reason_code="VERIFIERS_FAILED",
        rationale="Both configured verifier roles failed.",
        fallback_used=True,
    )

    assert result.accepted == (fact,)
    assert result.audit_records[0]["decision"] == "unresolved"
    assert result.audit_records[0]["before"] == fact.model_dump(mode="json")
    assert result.audit_records[0]["after"] == fact.model_dump(mode="json")
    assert result.issues[0]["code"] == "verifier_unresolved_preserved"


def test_latex_unit_variant_is_valid_literal_evidence():
    assert _source_supports_quote(
        "The grain size was 1.49 µm in the XOY plane.",
        "The grain size was 1.49 \\mum in the XOY plane.",
    )
    assert _source_supports_quote(
        "The σ phase was present.",
        "The \\sigmaphase was present.",
    )


def test_reassign_owner_is_restricted_to_literal_inventory_entity():
    source = "Sample A and Sample B were tested. Sample B had a yield strength of 900 MPa."
    fact = _property(
        "Sample A", "900", "Sample B had a yield strength of 900 MPa."
    )
    inventory, bundle = _case(
        [fact], source, [_anchor("Sample A", "Sample A"), _anchor("Sample B", "Sample B")]
    )
    assertion = bundle.assertions[0]
    entity_b = next(row for row in bundle.entities if row.sample_id_raw == "Sample B")
    valid = VerificationResponse(
        bundle_id=bundle.bundle_id,
        decisions=[
            VerificationDecision(
                assertion_id=assertion.assertion_id,
                decision="reassign",
                evidence_ids=_evidence_ids(bundle),
                reason_code="OWNER_CORRECTED",
                rationale="The result sentence names Sample B.",
                reassignment=ReassignmentPatch(
                    entity_id=entity_b.entity_id, sample_id_raw="Sample B"
                ),
            )
        ],
    )
    result = validate_and_apply_bundle(bundle, valid, inventory)
    assert result.accepted[0].sample_id_raw == "Sample B"
    assert result.accepted[0].data["value_raw"] == "900"
    assert result.accepted[0].data["unit_raw"] == "MPa"

    invented = valid.model_copy(
        update={
            "decisions": [
                valid.decisions[0].model_copy(
                    update={
                        "reassignment": ReassignmentPatch(sample_id_raw="Sample C")
                    }
                )
            ]
        }
    )
    with pytest.raises(VerificationGroundingError, match="not literal"):
        validate_and_apply_bundle(bundle, invented, inventory)


def test_merge_requires_all_members_and_preserves_provenance_union():
    first = "Sample A had a yield strength of 900 MPa."
    second = "Table 2 also reports Sample A yield strength as 900 MPa."
    source = first + " " + second
    facts = [_property("Sample A", "900", first), _property("Sample A", "900", second)]
    inventory, bundle = _case(facts, source, [_anchor("Sample A", "Sample A")])
    members = [row.assertion_id for row in bundle.assertions]
    survivor = members[0]
    decisions = [
        VerificationDecision(
            assertion_id=assertion_id,
            decision="merge",
            evidence_ids=_evidence_ids(bundle),
            reason_code="EXACT_DUPLICATE",
            rationale="Both records report one owner/property/value/unit fact.",
            merge_member_ids=members,
            survivor_assertion_id=survivor,
        )
        for assertion_id in members
    ]
    result = validate_and_apply_bundle(
        bundle,
        VerificationResponse(bundle_id=bundle.bundle_id, decisions=decisions),
        inventory,
    )
    assert len(result.accepted) == 1
    assert set(result.accepted[0].source_evidence) == {first, second}
    assert len(result.audit_records) == 2

    incomplete = VerificationResponse(bundle_id=bundle.bundle_id, decisions=decisions[:1])
    with pytest.raises(VerificationGroundingError, match="decide every"):
        validate_and_apply_bundle(bundle, incomplete, inventory)


def test_unknown_evidence_id_invalidates_entire_bundle_before_application():
    source = "Sample A had a yield strength of 900 MPa."
    fact = _property("Sample A", "900", source)
    inventory, bundle = _case([fact], source)
    assertion = bundle.assertions[0]
    response = VerificationResponse(
        bundle_id=bundle.bundle_id,
        decisions=[
            VerificationDecision(
                assertion_id=assertion.assertion_id,
                decision="accept",
                evidence_ids=["invented-evidence"],
                reason_code="SOURCE_SUPPORTED",
                rationale="Invented citation.",
            )
        ],
    )
    with pytest.raises(VerificationGroundingError, match="unknown evidence"):
        validate_and_apply_bundle(bundle, response, inventory)


def test_accept_cannot_use_unrelated_bundle_evidence_for_a_property():
    first = "Sample A had a yield strength of 900 MPa."
    second = "Sample B had a yield strength of 800 MPa."
    inventory, bundle = _case(
        [_property("Sample A", "900", first), _property("Sample B", "800", second)],
        first + " " + second,
    )
    decisions = []
    for assertion in bundle.assertions:
        unrelated = next(
            row.evidence_id
            for row in bundle.evidence
            if "800 MPa" in row.text and assertion.sample_id_raw == "Sample A"
            or "900 MPa" in row.text and assertion.sample_id_raw == "Sample B"
        )
        decisions.append(
            VerificationDecision(
                assertion_id=assertion.assertion_id,
                decision="accept",
                evidence_ids=[unrelated],
                reason_code="SOURCE_SUPPORTED",
                rationale="Wrong evidence on purpose.",
            )
        )
    with pytest.raises(VerificationGroundingError, match="source_evidence"):
        validate_and_apply_bundle(
            bundle,
            VerificationResponse(bundle_id=bundle.bundle_id, decisions=decisions),
            inventory,
        )


def test_recovery_requires_literal_value_unit_owner_and_evidence():
    source = "Sample B had an elongation of 12 %."
    inventory = build_verification_inventory([], [], source_text=source)
    request = RecoveryRequest(
        request_id="recovery-1",
        evidence=list(inventory.recovery_evidence),
        source_char_count=sum(len(row.text) for row in inventory.recovery_evidence),
    )
    candidate = _property("Sample B", "12", source).model_dump(mode="json")
    candidate["data"]["property_name_raw"] = "elongation"
    candidate["data"]["unit_raw"] = "%"
    proposal = RecoveryProposal(
        proposal_id="proposal-1",
        axis="properties",
        candidate=candidate,
        evidence_ids=[request.evidence[0].evidence_id],
        reason_code="UNCOVERED_LITERAL_FACT",
    )
    recovered = validate_recovery_response(
        request, RecoveryResponse(proposals=[proposal])
    )
    assert recovered[0].data["value_raw"] == "12"

    hallucinated = proposal.model_copy(
        update={
            "candidate": {
                **candidate,
                "data": {**candidate["data"], "value_raw": "99"},
            }
        }
    )
    with pytest.raises(VerificationGroundingError, match="value is not literal"):
        validate_recovery_response(
            request, RecoveryResponse(proposals=[hallucinated])
        )


def test_accept_allows_ordered_table_projection_inside_exact_task_scope():
    source = "| Sample | Yield strength | Elongation |\n| A | 900 MPa | 12 % |"
    projected = "Sample | Yield strength | A | 900 MPa"
    fact = _property("A", "900", projected)
    inventory = build_verification_inventory(
        [],
        [fact],
        source_text=source,
        task_ids=["table-task"],
        task_source_scopes={"table-task": source},
    )
    bundle = build_verification_bundles(inventory, source_text=source)[0]
    assertion = bundle.assertions[0]
    response = VerificationResponse(
        bundle_id=bundle.bundle_id,
        decisions=[
            VerificationDecision(
                assertion_id=assertion.assertion_id,
                decision="accept",
                evidence_ids=[row.evidence_id for row in bundle.evidence],
                reason_code="TABLE_COORDINATE_SUPPORTED",
                rationale="The ordered source table cells prove one row value.",
            )
        ],
    )
    result = validate_and_apply_bundle(bundle, response, inventory)
    assert result.accepted == (fact,)


def test_field_response_requires_every_asserted_field_and_known_evidence():
    source = "Sample A had a yield strength of 900 MPa."
    fact = _property("Sample A", "900", source)
    inventory, raw_bundle = _case([fact], source, [_anchor("Sample A", "Sample A")])
    bundle = _with_risk(raw_bundle, "hard", "multi_owner_ambiguous")
    incomplete = FieldVerificationResponse(
        bundle_id=bundle.bundle_id,
        decisions=[
            FieldVerificationDecision(
                assertion_id=bundle.assertions[0].assertion_id,
                fields=[
                    ScientificFieldVerdict(
                        field="owner",
                        verdict="supported",
                        evidence_ids=_evidence_ids(bundle),
                    )
                ],
                reason_code="INCOMPLETE_FIELDS",
                rationale="Missing fields on purpose.",
            )
        ],
    )
    with pytest.raises(VerificationGroundingError, match="field coverage"):
        validate_field_response(bundle, incomplete)

    valid = _field_response(bundle)
    invented = valid.model_copy(
        update={
            "decisions": [
                valid.decisions[0].model_copy(
                    update={
                        "fields": [
                            row.model_copy(update={"evidence_ids": ["invented"]})
                            if row.field == "owner"
                            else row
                            for row in valid.decisions[0].fields
                        ]
                    }
                )
            ]
        }
    )
    with pytest.raises(VerificationGroundingError, match="unknown evidence"):
        validate_field_response(bundle, invented)


def test_field_grounding_accepts_latex_unicode_unit_presentation_equivalence():
    source = "Sample A was preheated to 150^\\circC using 30 $ \\mu $m layers."
    fact = _processing("Sample A", source)
    fact.data["parameters_raw"] = [
        {
            "parameter_name_raw": "preheat temperature",
            "value_raw": "150",
            "unit_raw": "°C",
            "source_evidence": source,
        },
        {
            "parameter_name_raw": "layer thickness",
            "value_raw": "30",
            "unit_raw": "µm",
            "source_evidence": source,
        },
    ]
    inventory, raw_bundle = _case(
        [fact], source, [_anchor("Sample A", "Sample A")]
    )
    bundle = _with_risk(raw_bundle, "hard", "presentation_test")

    decisions = validate_field_response(bundle, _field_response(bundle))

    assert set(decisions) == {bundle.assertions[0].assertion_id}


def test_field_grounding_accepts_latex_plus_minus_presentation_equivalence():
    source = r"Sample A had a yield strength of 1222 \pm 56 MPa."
    copied = "Sample A had a yield strength of 1222 ± 56 MPa."
    fact = _property("Sample A", "1222 ± 56", copied)
    inventory, raw_bundle = _case(
        [fact], source, [_anchor("Sample A", "Sample A")]
    )
    bundle = _with_risk(raw_bundle, "hard", "presentation_test")

    decisions = validate_field_response(bundle, _field_response(bundle))

    assert set(decisions) == {bundle.assertions[0].assertion_id}
    cited = next(
        row
        for row in inventory.evidence
        if row.evidence_id == bundle.assertions[0].evidence_ids[0]
    )
    assert r"1222 \pm 56 MPa" in cited.text


@pytest.mark.parametrize(
    ("fact", "source", "expected_fields"),
    [
        (
            _processing(
                "Sample A",
                "Sample A was made by laser powder bed fusion at 400 W.",
            ),
            "Sample A was made by laser powder bed fusion at 400 W.",
            ("semantic", "value", "unit", "owner"),
        ),
        (
            _structure(
                "Sample A",
                "As-built Sample A had 2.3 µm grains at the melt-pool boundary.",
            ),
            "As-built Sample A had 2.3 µm grains at the melt-pool boundary.",
            ("semantic", "value", "unit", "owner", "state", "condition"),
        ),
    ],
)
def test_required_fields_cover_nested_processing_and_structure_science(
    fact,
    source,
    expected_fields,
):
    _inventory, bundle = _case(
        [fact], source, [_anchor("Sample A", "Sample A")]
    )

    assert required_scientific_fields(bundle.assertions[0]) == expected_fields


def test_nested_values_and_units_must_be_grounded_for_supported_verdicts():
    evidence = "Sample A was made by laser powder bed fusion."
    fact = _processing("Sample A", evidence)
    _inventory, bundle = _case(
        [fact], evidence, [_anchor("Sample A", "Sample A")]
    )
    assertion = bundle.assertions[0]
    evidence_ids = _evidence_ids(bundle)
    response = FieldVerificationResponse(
        protocol_version=FIELD_VERIFICATION_PROTOCOL_VERSION,
        bundle_id=bundle.bundle_id,
        decisions=[
            FieldVerificationDecision(
                assertion_id=assertion.assertion_id,
                fields=[
                    ScientificFieldVerdict(
                        field=field,
                        verdict="supported",
                        evidence_ids=evidence_ids,
                    )
                    for field in required_scientific_fields(assertion)
                ],
                reason_code="ALL_FIELDS_SUPPORTED",
                rationale="Every aggregate field is claimed as source-supported.",
            )
        ],
    )

    with pytest.raises(
        VerificationGroundingError,
        match="supported value is not literal",
    ):
        validate_field_response(bundle, response)


def test_structure_region_cannot_be_reassigned_through_property_condition_slot():
    source = (
        "As-built Sample A had 2.3 µm grains at the melt-pool boundary and bulk."
    )
    fact = _structure("Sample A", source)
    _inventory, bundle = _case(
        [fact], source, [_anchor("Sample A", "Sample A")]
    )
    assertion = bundle.assertions[0]
    evidence_ids = _evidence_ids(bundle)
    response = FieldVerificationResponse(
        protocol_version=FIELD_VERIFICATION_PROTOCOL_VERSION,
        bundle_id=bundle.bundle_id,
        decisions=[
            FieldVerificationDecision(
                assertion_id=assertion.assertion_id,
                fields=[
                    ScientificFieldVerdict(
                        field=field,
                        verdict=("contradicted" if field == "condition" else "supported"),
                        evidence_ids=evidence_ids,
                        selected_text=("bulk" if field == "condition" else None),
                    )
                    for field in required_scientific_fields(assertion)
                ],
                reason_code="REGION_CORRECTION_PROPOSED",
                rationale="A different literal region was proposed.",
            )
        ],
    )

    with pytest.raises(
        VerificationGroundingError,
        match="no mutable test_condition_raw",
    ):
        validate_field_response(bundle, response)


def test_hard_risk_requires_two_fully_supported_roles():
    source = "Sample A had a yield strength of 900 MPa."
    fact = _property("Sample A", "900", source)
    inventory, raw_bundle = _case([fact], source, [_anchor("Sample A", "Sample A")])
    bundle = _with_risk(raw_bundle, "hard", "multi_owner_ambiguous")
    supported = _field_response(bundle)

    accepted = apply_field_consensus(
        bundle,
        inventory,
        primary_response=supported,
        secondary_response=supported,
    )
    assert accepted.accepted == (fact,)
    assert accepted.issues == ()

    owner_not_proven = supported.model_copy(
        update={
            "decisions": [
                supported.decisions[0].model_copy(
                    update={
                        "fields": [
                            row.model_copy(update={"verdict": "not_proven"})
                            if row.field == "owner"
                            else row
                            for row in supported.decisions[0].fields
                        ]
                    }
                )
            ]
        }
    )
    isolated = apply_field_consensus(
        bundle,
        inventory,
        primary_response=supported,
        secondary_response=owner_not_proven,
    )
    assert isolated.accepted == ()
    assert isolated.issues[0]["code"] == "verifier_hard_risk_isolated"
    assert isolated.audit_records[0]["risk_severity"] == "hard"


def test_compact_review_support_is_revalidated_against_every_required_field():
    source = r"Sample A had a yield strength of 1222 \pm 56 MPa."
    copied = "Sample A had a yield strength of 1222 ± 56 MPa."
    fact = _property("Sample A", "1222 ± 56", copied)
    inventory, raw_bundle = _case(
        [fact], source, [_anchor("Sample A", "Sample A")]
    )
    bundle = _with_risk(raw_bundle, "hard", "owner_not_literal")
    assertion = bundle.assertions[0]
    compact = CompactReviewResponse(
        protocol_version=COMPACT_REVIEW_PROTOCOL_VERSION,
        bundle_id=bundle.bundle_id,
        decisions=[
            CompactReviewDecision(
                assertion_id=assertion.assertion_id,
                verdict="all_fields_supported",
                evidence_ids=_evidence_ids(bundle),
                reason_code="ALL_FIELDS_SUPPORTED",
            )
        ],
    )

    decisions = validate_compact_review_response(bundle, compact)
    result = apply_field_consensus(
        bundle,
        inventory,
        primary_response=_field_response(bundle),
        secondary_response=None,
        secondary_compact_response=compact,
    )

    assert set(decisions) == {assertion.assertion_id}
    assert result.accepted == (fact,)
    assert result.audit_records[0]["secondary_compact_review"]["verdict"] == (
        "all_fields_supported"
    )


def test_compact_review_rejects_unknown_evidence_and_unasserted_failed_field():
    source = "Sample A had a yield strength of 900 MPa."
    fact = _property("Sample A", "900", source)
    _inventory, raw_bundle = _case(
        [fact], source, [_anchor("Sample A", "Sample A")]
    )
    bundle = _with_risk(raw_bundle, "hard", "owner_not_literal")
    assertion = bundle.assertions[0]

    unknown = CompactReviewResponse(
        bundle_id=bundle.bundle_id,
        decisions=[
            CompactReviewDecision(
                assertion_id=assertion.assertion_id,
                verdict="all_fields_supported",
                evidence_ids=["invented-evidence"],
                reason_code="ALL_FIELDS_SUPPORTED",
            )
        ],
    )
    with pytest.raises(VerificationGroundingError, match="unknown evidence"):
        validate_compact_review_response(bundle, unknown)

    unasserted = CompactReviewResponse(
        bundle_id=bundle.bundle_id,
        decisions=[
            CompactReviewDecision(
                assertion_id=assertion.assertion_id,
                verdict="not_proven",
                evidence_ids=_evidence_ids(bundle),
                failed_fields=["state"],
                reason_code="STATE_NOT_PROVEN",
            )
        ],
    )
    with pytest.raises(VerificationGroundingError, match="failed_fields"):
        validate_compact_review_response(bundle, unasserted)


def test_primary_nonpositive_hard_skips_compact_review_and_isolates():
    source = "Sample A had a yield strength of 900 MPa."
    fact = _property("Sample A", "900", source)
    inventory, raw_bundle = _case(
        [fact], source, [_anchor("Sample A", "Sample A")]
    )
    bundle = _with_risk(raw_bundle, "hard", "owner_not_literal")
    primary = _field_response(bundle)
    primary = primary.model_copy(
        update={
            "decisions": [
                primary.decisions[0].model_copy(
                    update={
                        "fields": [
                            row.model_copy(update={"verdict": "not_proven"})
                            if row.field == "owner"
                            else row
                            for row in primary.decisions[0].fields
                        ]
                    }
                )
            ]
        }
    )

    result = apply_field_consensus(
        bundle,
        inventory,
        primary_response=primary,
        secondary_response=None,
        secondary_skipped_assertion_ids={bundle.assertions[0].assertion_id},
    )

    assert result.accepted == ()
    audit = result.audit_records[0]
    assert audit["secondary_compact_review"]["decision"] == "skipped"
    assert audit["secondary_compact_review"]["reason_code"] == (
        "SECONDARY_SKIPPED_PRIMARY_NONPOSITIVE"
    )
    assert result.issues[0]["code"] == "verifier_hard_risk_isolated"


def test_hard_risk_reassignment_requires_exact_same_target_consensus():
    source = "Sample A and Sample B were tested. Sample B had a yield strength of 900 MPa."
    fact = _property("Sample A", "900", "Sample B had a yield strength of 900 MPa.")
    inventory, raw_bundle = _case(
        [fact],
        source,
        [_anchor("Sample A", "Sample A"), _anchor("Sample B", "Sample B")],
    )
    bundle = _with_risk(raw_bundle, "hard", "owner_conflicts_with_literal_entity")
    entity_a = next(row for row in bundle.entities if row.sample_id_raw == "Sample A")
    entity_b = next(row for row in bundle.entities if row.sample_id_raw == "Sample B")
    to_b = _field_response(bundle, verdict="contradicted", owner_target=entity_b)

    reassigned = apply_field_consensus(
        bundle,
        inventory,
        primary_response=to_b,
        secondary_response=to_b,
    )
    assert reassigned.accepted[0].sample_id_raw == "Sample B"
    assert reassigned.issues[0]["code"] == "verifier_owner_reassigned"

    to_a = _field_response(bundle, verdict="contradicted", owner_target=entity_a)
    disagreed = apply_field_consensus(
        bundle,
        inventory,
        primary_response=to_b,
        secondary_response=to_a,
    )
    assert disagreed.accepted == ()
    assert disagreed.issues[0]["code"] == "verifier_hard_risk_isolated"


def test_condition_reassignment_uses_condition_specific_issue_code():
    source = "Sample A had a yield strength of 900 MPa at 900 °C."
    fact = _property("Sample A", "900", source, condition="800 °C")
    inventory, raw_bundle = _case(
        [fact], source, [_anchor("Sample A", "Sample A")]
    )
    bundle = _with_risk(raw_bundle, "hard", "multi_condition_projection")
    assertion = bundle.assertions[0]
    evidence_ids = _evidence_ids(bundle)
    response = FieldVerificationResponse(
        protocol_version=FIELD_VERIFICATION_PROTOCOL_VERSION,
        bundle_id=bundle.bundle_id,
        decisions=[
            FieldVerificationDecision(
                assertion_id=assertion.assertion_id,
                fields=[
                    ScientificFieldVerdict(
                        field=field,
                        verdict=("contradicted" if field == "condition" else "supported"),
                        evidence_ids=evidence_ids,
                        selected_text=("900 °C" if field == "condition" else None),
                    )
                    for field in required_scientific_fields(assertion)
                ],
                reason_code="CONDITION_REASSIGNMENT",
                rationale="Both reviewers selected the literal test condition.",
            )
        ],
    )

    result = apply_field_consensus(
        bundle,
        inventory,
        primary_response=response,
        secondary_response=response,
    )

    assert result.accepted[0].data["test_condition_raw"] == "900 °C"
    assert result.issues[0]["code"] == "verifier_condition_reassigned"


def test_soft_failure_preserves_but_hard_technical_failure_isolates():
    source = "Sample A had a yield strength of 900 MPa."
    fact = _property("Sample A", "900", source)
    inventory, raw_bundle = _case([fact], source, [_anchor("Sample A", "Sample A")])

    soft = _with_risk(raw_bundle, "soft", "low_confidence")
    soft_result = apply_field_consensus(
        soft,
        inventory,
        primary_response=None,
        secondary_response=None,
        primary_error="timeout",
        secondary_error="truncated",
    )
    assert soft_result.accepted == (fact,)
    assert soft_result.issues[0]["code"] == "verifier_soft_risk_preserved"

    hard = _with_risk(raw_bundle, "hard", "multi_owner_ambiguous")
    hard_result = apply_field_consensus(
        hard,
        inventory,
        primary_response=None,
        secondary_response=None,
        primary_error="timeout",
        secondary_error="truncated",
    )
    assert hard_result.accepted == ()
    assert hard_result.issues[0]["code"] == "verifier_technical_failure_isolated"
