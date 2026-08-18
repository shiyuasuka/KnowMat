from knowmat.alpha25.claim_quality import (
    deduplicate_axis_facts,
    deduplicate_axis_facts_with_audit,
    filter_axis_facts,
)
from knowmat.alpha25.contracts import (
    CompositionFact,
    ProcessingFact,
    PropertyFact,
    StructureFact,
)


def _property(
    *,
    name: str = "yield strength",
    value: str = "900",
    unit: str = "MPa",
    evidence: str = "A1 had a yield strength of 900 MPa.",
    condition: str = "",
) -> PropertyFact:
    return PropertyFact(
        sample_id_raw="A1",
        data={
            "property_id_candidate": "temporary",
            "property_name_raw": name,
            "value_raw": value,
            "unit_raw": unit,
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


def _composition(
    *,
    value: str,
    unit: str | None,
    evidence: str,
    value_kind: str = "scalar",
    source_type: str = "provided",
) -> CompositionFact:
    return CompositionFact(
        sample_id_raw="A1",
        fact_type="composition_observation",
        data={
            "observation_id": "temporary",
            "source_type": source_type,
            "material_state": "not_reported",
            "sample_id": "A1",
            "basis": "at%" if unit else "unknown",
            "component_type": "elemental",
            "components": [
                {
                    "name_raw": "Nb",
                    "value_kind": value_kind,
                    "value_raw": value,
                    "unit_raw": unit,
                    "data_nature": "reported",
                }
            ],
            "measurement": None,
            "raw_expression": evidence,
            "data_source": "text",
            "source_evidence": [evidence],
            "note": None,
        },
        source_evidence=[evidence],
        confidence=0.8,
    )


def test_placeholder_property_is_quarantined_before_materialization():
    result = filter_axis_facts(
        [_property(value="not_reported", unit="", evidence="Tensile results are listed.")]
    )

    assert result.accepted == []
    assert [issue.code for issue in result.issues] == ["fact_placeholder_value"]


def test_numeric_property_value_and_unit_must_be_in_its_evidence():
    result = filter_axis_facts(
        [_property(value="950", evidence="A1 had a yield strength of 900 MPa.")]
    )

    assert result.accepted == []
    assert [issue.code for issue in result.issues] == ["fact_value_not_grounded"]


def test_numeric_condition_is_deferred_without_evidence_unit_provenance():
    result = filter_axis_facts(
        [_property(condition="tested at 650 °C")]
    )

    assert len(result.accepted) == 1
    assert result.issues == []


def test_table_header_and_body_quotes_jointly_ground_value_and_unit():
    evidence = "| Sample | Nb (at.%) |\n| A1 | 21.93 |"
    result = filter_axis_facts(
        [_composition(value="21.93", unit="at.%", evidence=evidence, source_type="measured")],
        mode="strict",
    )

    assert len(result.accepted) == 1
    assert result.issues == []


def test_alloy_designation_does_not_prove_measured_composition():
    result = filter_axis_facts(
        [
            _composition(
                value="25",
                unit="at.%",
                evidence="Ti-22Al-25Nb alloy",
                source_type="measured",
            )
        ],
        mode="strict",
    )

    assert result.accepted == []
    assert result.issues[0].code in {
        "fact_unit_not_grounded",
        "composition_source_type_unsupported",
    }


def test_structural_presence_phrase_is_not_a_composition_amount():
    result = filter_axis_facts(
        [
            _composition(
                value="appears within the passive film",
                unit=None,
                evidence="Al2O3 appears within the passive film.",
                value_kind="categorical",
            )
        ],
        mode="strict",
    )

    assert result.accepted == []
    assert [issue.code for issue in result.issues] == [
        "fact_quarantined_wrong_axis"
    ]


def test_semantic_property_aliases_deduplicate_and_union_evidence():
    first = _property(name="UTS", value="1000", evidence="A1 UTS was 1000 MPa.")
    second = _property(
        name="ultimate tensile strength",
        value="1000",
        evidence="The ultimate tensile strength of A1 was 1000 MPa.",
    )

    merged = deduplicate_axis_facts([first, second])

    assert len(merged) == 1
    assert merged[0].source_evidence == [
        "A1 UTS was 1000 MPa.",
        "The ultimate tensile strength of A1 was 1000 MPa.",
    ]


def test_semantic_property_duplicate_keeps_complete_issue_audit():
    first = _property(name="UTS", value="1000", evidence="A1 UTS was 1000 MPa.")
    second = _property(
        name="ultimate tensile strength",
        value="1000",
        evidence="The ultimate tensile strength of A1 was 1000 MPa.",
    )

    result = deduplicate_axis_facts_with_audit([first, second])

    assert len(result.accepted) == 1
    assert [issue.code for issue in result.issues] == ["semantic_duplicate_merged"]
    assert result.issues[0].actual["removed_duplicate"] == second.model_dump()
    assert result.issues[0].actual["surviving_fact_before_merge"] == first.model_dump()


def test_empty_structure_region_is_removed_with_audit_in_safe_mode():
    evidence = "The boundary separated the continuous precipitation region."
    fact = StructureFact(
        sample_id_raw="A1",
        fact_type="structure_observation",
        data={
            "observation_id": "temporary",
            "structure_kind": "phase",
            "material_state": "not_reported",
            "sample_id": "A1",
            "source_type": "measured",
            "original": evidence,
            "simplified": evidence,
            "entities": [
                {
                    "entity_id": "temporary",
                    "entity_type": "region",
                    "role": "reported",
                    "name_raw": "CP region",
                    "features": [],
                    "raw_expression": "continuous precipitation region",
                    "source_evidence": [evidence],
                }
            ],
            "features": [],
            "source_evidence": [evidence],
        },
        source_evidence=[evidence],
        confidence=0.8,
    )

    result = filter_axis_facts([fact], mode="safe")

    assert result.accepted[0].data["entities"] == []
    assert [issue.code for issue in result.issues] == [
        "structure_context_entity_removed"
    ]


def test_equal_values_with_different_conditions_are_not_deduplicated():
    room = _property(value="900", condition="25 °C", evidence="A1 was 900 MPa at 25 °C.")
    hot = _property(value="900", condition="650 °C", evidence="A1 was 900 MPa at 650 °C.")

    assert len(deduplicate_axis_facts([room, hot])) == 2


def test_process_parameter_value_is_checked_without_rejecting_stage():
    fact = ProcessingFact(
        sample_id_raw="A1",
        fact_type="process_stage",
        data={
            "candidate_stage_id": "tmp",
            "stage_index_candidate": 1,
            "process_name_raw": "laser powder bed fusion",
            "process_code_candidate": None,
            "process_role_candidate": "primary_forming",
            "parameters_raw": [
                {
                    "parameter_name_raw": "laser power",
                    "value_raw": "275",
                    "unit_raw": "W",
                    "source_evidence": "laser power was 250 W",
                }
            ],
            "source_evidence": ["A1 was produced by laser powder bed fusion at 250 W."],
            "confidence": 0.8,
        },
        source_evidence=["A1 was produced by laser powder bed fusion at 250 W."],
        confidence=0.8,
    )

    result = filter_axis_facts([fact], mode="strict")

    assert len(result.accepted) == 1
    assert result.accepted[0].data["parameters_raw"] == []
    assert [issue.code for issue in result.issues] == ["fact_value_not_grounded"]


def test_safe_mode_defers_composition_and_processing_provenance_gates():
    composition = _composition(
        value="25",
        unit="at.%",
        evidence="Ti-22Al-25Nb alloy",
        source_type="measured",
    )
    processing = ProcessingFact(
        sample_id_raw="A1",
        fact_type="process_stage",
        data={
            "candidate_stage_id": "tmp",
            "stage_index_candidate": 1,
            "process_name_raw": "laser powder bed fusion",
            "process_code_candidate": None,
            "process_role_candidate": "primary_forming",
            "parameters_raw": [
                {
                    "parameter_name_raw": "laser power",
                    "value_raw": "275",
                    "unit_raw": "W",
                    "source_evidence": "laser power was 250 W",
                }
            ],
            "source_evidence": ["A1 was produced at 250 W."],
            "confidence": 0.8,
        },
        source_evidence=["A1 was produced at 250 W."],
        confidence=0.8,
    )

    result = filter_axis_facts([composition, processing], mode="safe")

    assert result.accepted == [composition, processing]
    assert result.issues == []


def test_off_mode_is_lossless_and_skips_property_deduplication():
    first = _property(name="UTS", value="1000", evidence="A1 UTS was 1000 MPa.")
    second = _property(
        name="ultimate tensile strength",
        value="1000",
        evidence="A1 ultimate tensile strength was 1000 MPa.",
    )

    filtered = filter_axis_facts([first, second], mode="off")

    assert filtered.accepted == [first, second]
    assert filtered.issues == []
    assert deduplicate_axis_facts(filtered.accepted, mode="off") == [first, second]
