from knowmat.alpha25.claim_quality import (
    deduplicate_axis_facts,
    deduplicate_axis_facts_with_audit,
    filter_axis_facts,
    filter_composition_precision_facts,
    is_core_tensile_property_name,
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
    name: str = "Nb",
    raw_expression: str | None = None,
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
                    "name_raw": name,
                    "value_kind": value_kind,
                    "value_raw": value,
                    "unit_raw": unit,
                    "data_nature": "reported",
                }
            ],
            "measurement": None,
            "raw_expression": raw_expression or evidence,
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


def test_numeric_core_tensile_value_must_be_in_its_own_evidence():
    result = filter_axis_facts(
        [_property(value="950", evidence="A1 had a yield strength of 900 MPa.")]
    )

    assert result.accepted == []
    assert [issue.code for issue in result.issues] == [
        "core_tensile_value_not_in_local_evidence"
    ]
    assert result.issues[0].actual["reason"] == (
        "local_evidence_has_conflicting_numbers"
    )
    assert result.issues[0].actual["fact"]["data"]["value_raw"] == "950"


def test_core_tensile_number_is_rejected_when_local_evidence_has_no_number():
    fact = _property(
        name="Ultimate Tensile Strength",
        value="650",
        unit="MPa",
        evidence=(
            "BJP samples with optimal sintering conditions reach similar "
            "mechanical properties to conventionally processed samples."
        ),
    )

    result = filter_axis_facts([fact])

    assert result.accepted == []
    assert [issue.code for issue in result.issues] == [
        "core_tensile_value_not_in_local_evidence"
    ]
    assert result.issues[0].actual["reason"] == (
        "local_evidence_contains_no_numbers"
    )
    assert result.issues[0].actual["fact"] == fact.model_dump()


def test_numeric_condition_is_deferred_without_evidence_unit_provenance():
    result = filter_axis_facts(
        [_property(condition="tested at 650 °C")]
    )

    assert len(result.accepted) == 1
    assert result.issues == []


def test_source_locator_is_not_promoted_as_a_property_result():
    result = filter_axis_facts(
        [
            _property(
                name="tensile properties",
                value="Table 2",
                unit="",
                evidence="Table 2 Tensile properties of H230AM and H230 at 900 °C",
            )
        ]
    )

    assert result.accepted == []
    assert [issue.code for issue in result.issues] == [
        "property_non_result_quarantined"
    ]
    assert result.issues[0].actual["reason"] == "source_locator"


def test_digitized_figure_locator_without_value_is_quarantined():
    fact = _property(
        name="fatigue life Nf",
        value="digitized from Fig.10",
        unit="cycles",
        evidence=(
            "Eq. (16) can be used to fit the data of the specimens in Fig. 6(b), "
            "which was replotted in Fig. 10."
        ),
    )
    fact.data["data_source"] = "figure"

    result = filter_axis_facts([fact])

    assert result.accepted == []
    assert [issue.code for issue in result.issues] == [
        "property_non_result_quarantined"
    ]
    issue = result.issues[0]
    assert issue.actual["reason"] == "source_locator_placeholder"
    assert issue.actual["fact"] == fact.model_dump()


def test_numeric_figure_value_is_not_mistaken_for_a_locator_placeholder():
    fact = _property(
        name="fatigue life",
        value="1.2e5",
        unit="cycles",
        evidence="The digitized point in Fig. 10 has a fatigue life of 1.2e5 cycles.",
    )
    fact.data["data_source"] = "figure"

    result = filter_axis_facts([fact])

    assert result.accepted == [fact]
    assert result.issues == []


def test_independent_variable_trend_is_not_promoted_as_property_scalar():
    fact = _property(
        name="fatigue life",
        value="decreases as the t/d value decreases from 34.5 to 4.5",
        unit="cycles",
        evidence=(
            "The specimens exhibit a trend where N_f decreases as the t/d "
            "value decreases from 34.5 to 4.5."
        ),
    )

    result = filter_axis_facts([fact])

    assert result.accepted == []
    assert [issue.code for issue in result.issues] == [
        "property_non_result_quarantined"
    ]
    issue = result.issues[0]
    assert issue.actual["reason"] == "independent_variable_trend"
    assert issue.actual["fact"] == fact.model_dump()


def test_quantified_relative_property_is_not_mistaken_for_a_trend():
    fact = _property(
        name="fatigue life relative change",
        value="decreased by 40% as temperature increased from 25 to 650 °C",
        unit="%",
        evidence=(
            "Fatigue life decreased by 40% as temperature increased from "
            "25 to 650 °C."
        ),
    )

    result = filter_axis_facts([fact])

    assert len(result.accepted) == 1
    assert result.accepted[0].data["value_raw"] == fact.data["value_raw"]
    assert not any(
        issue.actual.get("reason") == "independent_variable_trend"
        for issue in result.issues
        if isinstance(issue.actual, dict)
    )


def test_dangling_hyphen_owner_is_deferred_to_axis_independent_materialization():
    fact = _property(
        name="elongation",
        value="3",
        unit="%",
        evidence="| This work | < 700 | 803 | 3 | 650 | PBF- |",
    ).model_copy(update={"sample_id_raw": "PBF-"})

    result = filter_axis_facts([fact])

    assert result.accepted == [fact]
    assert result.issues == []


def test_complete_hyphenated_owner_remains_eligible():
    fact = _property(
        name="elongation",
        value="3",
        unit="%",
        evidence="| This work | < 700 | 803 | 3 | 650 | PBF-EB |",
    ).model_copy(update={"sample_id_raw": "PBF-EB"})

    result = filter_axis_facts([fact])

    assert result.accepted == [fact]
    assert result.issues == []


def test_measurement_method_is_not_promoted_as_a_property_result():
    result = filter_axis_facts(
        [
            _property(
                name="relative density",
                value="measured by image method",
                unit="",
                evidence="The relative density is measured by image method.",
            )
        ]
    )

    assert result.accepted == []
    assert [issue.code for issue in result.issues] == [
        "property_non_result_quarantined"
    ]
    assert result.issues[0].actual["reason"] == "measurement_method"


def test_nonnumeric_test_protocol_is_not_promoted_as_a_property_result():
    result = filter_axis_facts(
        [
            _property(
                name="tensile test",
                value="six specimens",
                unit="not_reported",
                evidence="The tensile tests were conducted on six specimens.",
            )
        ]
    )

    assert result.accepted == []
    assert [issue.code for issue in result.issues] == [
        "property_non_result_quarantined"
    ]
    assert result.issues[0].actual["reason"] == "protocol_record"


def test_numeric_result_with_test_word_in_name_is_preserved():
    fact = _property(
        name="fatigue test result",
        value="1e6",
        unit="cycles",
        evidence="The fatigue test result was 1e6 cycles.",
    )

    result = filter_axis_facts([fact])

    assert result.accepted == [fact]
    assert result.issues == []


def test_numeric_test_control_parameter_is_not_promoted_as_material_property():
    result = filter_axis_facts(
        [
            _property(
                name="constant strain rate",
                value=r"5 \\times 10^{-4}",
                unit=r"s^{-1}",
                evidence=(
                    "Tensile tests were conducted at a constant strain rate of "
                    r"5 \\times 10^{-4} s^{-1}."
                ),
            )
        ]
    )

    assert result.accepted == []
    assert [issue.code for issue in result.issues] == [
        "property_non_result_quarantined"
    ]
    assert result.issues[0].actual["reason"] == "test_control_parameter"


def test_stress_relaxation_reload_rate_is_protocol_not_material_property():
    fact = _property(
        name="stress relaxation reload rate",
        value="50",
        unit="N/s",
        condition=(
            "strain rate 5 × 10^-4 s^-1; preset strains 1%, 2%, 3%, 4%; "
            "holding time 90 s"
        ),
        evidence=(
            "The specimen was reloaded to the stress level before stress "
            "relaxation at a constant rate (50 N/s)."
        ),
    )
    fact.data["test_method_raw"] = "multiple stress relaxation test"

    result = filter_axis_facts([fact])

    assert result.accepted == []
    assert [issue.code for issue in result.issues] == [
        "property_non_result_quarantined"
    ]
    assert result.issues[0].actual["reason"] == "test_control_parameter"
    assert result.issues[0].actual["fact"] == fact.model_dump()


def test_characterization_applied_strain_is_condition_not_material_property():
    strain_mapping = _property(
        name="deformation - strain mapping after tensile strain",
        value="3",
        unit="% strain",
        condition="after tensile strain of 3%",
        evidence=(
            "Strain mapping analysis of grains in A1 after tensile strain of 3%."
        ),
    )
    strain_mapping.data["test_method_raw"] = "HR-EBSD"
    microscopy = _property(
        name="deformation - TEM characterization of deformed microstructure",
        value="3",
        unit="% strain",
        condition="3% strain",
        evidence=(
            "Representative two-beam bright-field TEM image of the deformed "
            "A1 specimen (3% strain)."
        ),
    )
    microscopy.data["test_method_raw"] = "two-beam bright-field TEM"

    result = filter_axis_facts([strain_mapping, microscopy])

    assert result.accepted == []
    assert [issue.code for issue in result.issues] == [
        "property_non_result_quarantined",
        "property_non_result_quarantined",
    ]
    assert [issue.actual["reason"] for issue in result.issues] == [
        "characterization_strain_condition",
        "characterization_strain_condition",
    ]
    assert [issue.actual["fact"] for issue in result.issues] == [
        strain_mapping.model_dump(),
        microscopy.model_dump(),
    ]


def test_measured_residual_strain_and_relaxation_rate_are_preserved():
    residual_strain = _property(
        name="residual elastic strain",
        value="0.32",
        unit="% strain",
        condition="after tensile strain of 3%",
        evidence=(
            "After tensile strain of 3%, the residual elastic strain in A1 "
            "was 0.32%."
        ),
    )
    relaxation_response = _property(
        name="minimum stress relaxation rate",
        value="0.7",
        unit="MPa/s",
        condition="at 650 °C",
        evidence=(
            "The minimum stress relaxation rate of A1 was 0.7 MPa/s at 650 °C."
        ),
    )

    result = filter_axis_facts([residual_strain, relaxation_response])

    assert result.accepted == [residual_strain, relaxation_response]
    assert result.issues == []


def test_creep_test_stress_is_a_condition_not_a_material_property():
    result = filter_axis_facts(
        [
            _property(
                name="tension creep stress",
                value="85",
                unit="MPa",
                evidence="Creep tests were conducted at stresses of 45, 65 and 85 MPa.",
            )
        ]
    )

    assert result.accepted == []
    assert result.issues[0].actual["reason"] == "test_control_parameter"


def test_bare_tension_creep_test_is_a_protocol_not_a_material_property():
    result = filter_axis_facts(
        [
            _property(
                name="Tension creep test",
                value="45",
                unit="MPa",
                evidence=(
                    "The tension creep test of H230AM was artificially interrupted "
                    "at 45 MPa when the creep life reached 1500 h."
                ),
            )
        ]
    )

    assert result.accepted == []
    assert [issue.code for issue in result.issues] == [
        "property_non_result_quarantined"
    ]
    assert result.issues[0].actual["reason"] == "creep_test_protocol"


def test_interrupted_creep_test_event_is_not_promoted_as_creep_life():
    result = filter_axis_facts(
        [
            _property(
                name="tension creep life",
                value="artificially interrupted when the creep life reached 1500 h",
                unit="h",
                evidence=(
                    "The creep test was artificially interrupted when the creep "
                    "life reached 1500 h."
                ),
            )
        ]
    )

    assert result.accepted == []
    assert [issue.code for issue in result.issues] == [
        "property_non_result_quarantined"
    ]
    assert result.issues[0].actual["reason"] == (
        "creep_test_event_not_measured_life"
    )


def test_material_response_named_minimum_creep_strain_rate_is_preserved():
    fact = _property(
        name="minimum creep strain rate",
        value=r"1.36 \\times 10^{-7}",
        unit=r"s^{-1}",
        evidence=r"The minimum creep strain rate was 1.36 \\times 10^{-7} s^{-1}.",
    )

    result = filter_axis_facts([fact])

    assert result.accepted == [fact]
    assert result.issues == []


def test_reported_fatigue_stress_amplitude_is_preserved():
    fact = _property(
        name="stress amplitude",
        value="534",
        unit="MPa",
        evidence="The fatigue result was stress amplitude 534 MPa at 2.18e6 cycles.",
    )

    result = filter_axis_facts([fact])

    assert result.accepted == [fact]
    assert result.issues == []


def test_categorical_property_does_not_inherit_a_physical_unit():
    result = filter_axis_facts(
        [
            _property(
                name="wall width",
                value="progressively increases with wall height",
                unit="mm",
                evidence="The wall width progressively increases with wall height.",
            )
        ]
    )

    assert len(result.accepted) == 1
    assert result.accepted[0].data["unit_raw"] is None
    assert [issue.code for issue in result.issues] == [
        "property_categorical_unit_removed"
    ]
    assert result.issues[0].actual["before"]["unit_raw"] == "mm"
    assert result.issues[0].actual["after"]["unit_raw"] is None


def test_textual_number_preserves_its_physical_unit():
    fact = _property(
        name="tensile strength",
        value="more than one gigapascal",
        unit="GPa",
        evidence="The tensile strength was more than one gigapascal.",
    )

    result = filter_axis_facts([fact])

    assert result.accepted == [fact]
    assert result.issues == []


def test_core_tensile_inline_unit_reconciles_structured_unit_with_audit():
    result = filter_axis_facts(
        [
            _property(
                name="UTS",
                value="0.33 GPa",
                unit="MPa",
                evidence="The UTS was 0.33 GPa.",
            )
        ]
    )

    assert len(result.accepted) == 1
    assert result.accepted[0].data["value_raw"] == "0.33 GPa"
    assert result.accepted[0].data["unit_raw"] == "GPa"
    assert [issue.code for issue in result.issues] == [
        "property_source_unit_reconciled"
    ]
    issue = result.issues[0]
    assert issue.actual["before"]["unit_raw"] == "MPa"
    assert issue.actual["after"]["unit_raw"] == "GPa"
    assert issue.actual["reason"] == "source_local_inline_unit_mismatch"


def test_tensile_unit_is_not_borrowed_when_value_has_no_inline_unit():
    fact = _property(
        name="UTS",
        value="0.33",
        unit="MPa",
        evidence="The UTS was 0.33; the method used GPa for another measurement.",
    )

    result = filter_axis_facts([fact])

    assert result.accepted == [fact]
    assert result.issues == []


def test_tensile_inline_unit_is_not_reconciled_when_matching_value_has_conflicts():
    fact = _property(
        name="UTS",
        value="0.33",
        unit="MPa",
        evidence="The UTS values were 0.33 GPa and 0.33 MPa for two conditions.",
    )

    result = filter_axis_facts([fact])

    assert result.accepted == [fact]
    assert result.issues == []


def test_matching_tensile_inline_unit_does_not_create_reconciliation_issue():
    fact = _property(
        name="UTS",
        value="612 MPa",
        unit="MPa",
        evidence="The UTS was 612 MPa.",
    )

    result = filter_axis_facts([fact])

    assert result.accepted == [fact]
    assert result.issues == []


def test_qualitative_core_tensile_result_is_quarantined_with_complete_audit():
    fact = _property(
        name="yield strength",
        value="slightly lower than the AF sample",
        unit="MPa",
        evidence=(
            "The yield strength was slightly lower than that of the AF sample, "
            "while the elongation remained comparable."
        ),
    )

    result = filter_axis_facts([fact])

    assert result.accepted == []
    assert [issue.code for issue in result.issues] == [
        "qualitative_tensile_quarantined"
    ]
    issue = result.issues[0]
    assert issue.actual["reason"] == "qualitative_without_magnitude"
    assert issue.actual["fact"] == fact.model_dump()
    assert issue.evidence == fact.source_evidence
    assert issue.sample_id_raw == "A1"


def test_literal_leading_percent_property_label_recovers_numeric_tensile_unit():
    header = "| Properties | 0 s Delay | 120 s Delay | 300 s Delay |"
    row = (
        "| % Elongation | $ 14.5 \\pm 5.17 $ | "
        "$ 7.5 \\pm 2.09 $ | $ 14.83 \\pm 1.33 $ |"
    )
    fact = _property(
        name="% Elongation",
        value="14.5 ± 5.17",
        unit="",
        evidence=f"{header}\n{row}",
    )

    result = filter_axis_facts([fact])

    assert len(result.accepted) == 1
    assert result.accepted[0].data["unit_raw"] == "%"
    assert [issue.code for issue in result.issues] == [
        "property_name_unit_recovered"
    ]
    assert result.issues[0].actual["reason"] == (
        "source_local_property_label_unit"
    )


def test_un_evidenced_property_label_unit_does_not_rescue_numeric_tensile():
    fact = _property(
        name="% Elongation",
        value="14.5 ± 5.17",
        unit="",
        evidence="The reported value was 14.5 ± 5.17.",
    )

    result = filter_axis_facts([fact])

    assert result.accepted == []
    assert result.issues[0].code == "qualitative_tensile_quarantined"


def test_qualitative_ductility_and_anisotropy_are_core_tensile_claims():
    facts = [
        _property(
            name="ductility",
            value="similar",
            unit="not_reported",
            evidence="The ductility was similar for both orientations.",
        ),
        _property(
            name="tensile strength anisotropy",
            value="anisotropy",
            unit="not_reported",
            evidence="Clear tensile strength anisotropy was observed.",
        ),
        _property(
            name="UTS and TE",
            value="did not surpass the reference",
            unit="not_reported",
            evidence="The UTS and TE did not surpass the reference alloy.",
        ),
    ]

    result = filter_axis_facts(facts)

    assert result.accepted == []
    assert [issue.code for issue in result.issues] == [
        "qualitative_tensile_quarantined",
        "qualitative_tensile_quarantined",
        "qualitative_tensile_quarantined",
    ]


def test_te_and_eab_abbreviations_are_core_tensile_names():
    assert is_core_tensile_property_name("TE")
    assert is_core_tensile_property_name("EAB")


def test_qualitative_value_is_not_rescued_by_a_number_elsewhere_in_evidence():
    fact = _property(
        name="high-temperature tensile strength",
        value="excellent",
        unit="MPa",
        evidence=(
            "At 650 °C the alloy retained excellent high-temperature tensile "
            "strength after a 2 h exposure."
        ),
    )

    result = filter_axis_facts([fact])

    assert result.accepted == []
    assert result.issues[0].code == "qualitative_tensile_quarantined"


def test_chart_qualitative_tensile_is_not_rescued_by_sample_identifier_digits():
    fact = _property(
        name="yield strength",
        value="lower than the Grade 5 material",
        unit="not_reported",
        evidence="The yield strength was lower than the Grade 5 material.",
    )
    fact.data["data_source"] = "chart"

    result = filter_axis_facts([fact])

    assert result.accepted == []
    assert result.issues[0].code == "qualitative_tensile_quarantined"


def test_qualitative_tensile_is_not_rescued_by_coded_sample_names():
    result = filter_axis_facts(
        [
            _property(
                name="TE",
                value="between those of 1-1 and 2-1 samples",
                unit="not_reported",
                evidence="The TE was between those of 1-1 and 2-1 samples.",
            )
        ]
    )

    assert result.accepted == []
    assert result.issues[0].code == "qualitative_tensile_quarantined"


def test_quantified_tensile_relative_change_is_not_an_absolute_property():
    result = filter_axis_facts(
        [
            _property(
                name="elongation",
                value="reduced by 40%",
                unit="%",
                evidence="The elongation was reduced by 40%.",
            )
        ]
    )

    assert len(result.accepted) == 1
    data = result.accepted[0].data
    assert data["property_name_raw"] == "elongation relative change"
    assert data["value_raw"] == "reduced by 40%"
    assert data["unit_raw"] == "%"
    assert result.issues[0].code == "property_relative_quantity_reclassified"


def test_evidence_bound_improvement_is_not_an_absolute_elongation():
    result = filter_axis_facts(
        [
            _property(
                name="elongation",
                value="approximately 211%",
                unit="%",
                evidence=(
                    "The pulsed sample demonstrates an elongation improvement of "
                    "approximately 211% compared to the continuous sample."
                ),
            )
        ]
    )

    assert len(result.accepted) == 1
    data = result.accepted[0].data
    assert data["property_name_raw"] == "elongation relative change"
    assert data["value_raw"] == "approximately 211%"
    assert data["unit_raw"] == "%"
    assert result.issues[0].code == "property_relative_quantity_reclassified"
    assert result.issues[0].actual["reason"] == "evidence_bound_relative_change"


def test_evidence_bound_exceeds_by_is_a_dimensional_tensile_difference():
    result = filter_axis_facts(
        [
            _property(
                name="YS",
                value="57.3",
                unit="MPa",
                evidence=(
                    "Experimental data reveal that the YS of the CL sample exceeds "
                    "that of the PL sample by 57.3 MPa."
                ),
            )
        ]
    )

    assert len(result.accepted) == 1
    data = result.accepted[0].data
    assert data["property_name_raw"] == "YS difference"
    assert data["value_raw"] == "57.3"
    assert data["unit_raw"] == "MPa"
    assert result.issues[0].actual["reason"] == "evidence_bound_difference"


def test_evidence_bound_number_higher_than_is_a_tensile_difference():
    result = filter_axis_facts(
        [
            _property(
                name="theoretical YS",
                value="102.5",
                unit="MPa",
                evidence=(
                    "The theoretical YS of the PL sample should be approximately "
                    "102.5 MPa higher than that of the CL sample."
                ),
            )
        ]
    )

    assert result.accepted[0].data["property_name_raw"] == "theoretical YS difference"
    assert result.accepted[0].data["unit_raw"] == "MPa"


def test_parallel_pareto_increase_binds_each_tensile_difference_to_its_property():
    evidence = (
        "The 4-1 sample was able to increase the Pareto front by 1.2% in terms "
        "of TE and 69.3 MPa in terms of UTS compared to the training dataset."
    )
    result = filter_axis_facts(
        [
            _property(name="TE", value="1.2", unit="%", evidence=evidence),
            _property(name="UTS", value="69.3", unit="MPa", evidence=evidence),
        ]
    )

    assert [fact.data["property_name_raw"] for fact in result.accepted] == [
        "TE relative change",
        "UTS difference",
    ]
    assert [fact.data["unit_raw"] for fact in result.accepted] == ["%", "MPa"]


def test_discrepancy_within_percent_is_a_difference_not_absolute_elongation():
    result = filter_axis_facts(
        [
            _property(
                name="elongation discrepancy with H230",
                value="within 5 %",
                unit="",
                evidence="The discrepancy in elongation between these samples is within 5 %.",
            )
        ]
    )

    assert result.accepted[0].data["property_name_raw"] == (
        "elongation discrepancy with H230 difference"
    )
    assert result.accepted[0].data["unit_raw"] == ""
    assert result.issues[0].actual["reason"] == "evidence_bound_difference"


def test_absolute_terminal_value_after_from_to_remains_absolute_tensile_result():
    fact = _property(
        name="yield strength",
        value="600",
        unit="MPa",
        evidence="The yield strength increased from 500 to 600 MPa after aging.",
    )

    result = filter_axis_facts([fact])

    assert result.accepted == [fact]
    assert result.issues == []


def test_comparison_sentence_does_not_reclassify_a_separate_absolute_value():
    fact = _property(
        name="UTS",
        value="900",
        unit="MPa",
        evidence=(
            "The UTS was 900 MPa, which is higher than the reference value by "
            "75 MPa."
        ),
    )

    result = filter_axis_facts([fact])

    assert result.accepted == [fact]
    assert result.issues == []


def test_textual_tensile_magnitude_is_preserved():
    fact = _property(
        name="tensile strength",
        value="more than one gigapascal",
        unit="GPa",
        evidence="The tensile strength was more than one gigapascal.",
    )

    result = filter_axis_facts([fact])

    assert result.accepted == [fact]
    assert result.issues == []


def test_negative_absolute_tensile_magnitude_is_quarantined():
    result = filter_axis_facts(
        [
            _property(
                name="tensile strength",
                value="-1.6 GPa",
                unit="GPa",
                evidence="The alloy showed a high tensile strength (-1.6 GPa).",
            )
        ]
    )

    assert result.accepted == []
    assert result.issues[0].code == "physically_invalid_tensile_value"
    assert result.issues[0].actual["fact"]["value_raw"] == "-1.6 GPa"


def test_textual_ratio_is_reclassified_as_relative_tensile_property():
    fact = _property(
        name="total elongation",
        value="nearly three times that at room temperature",
        unit="not_reported",
        evidence=(
            "The total elongation was nearly three times that at room temperature."
        ),
    )

    result = filter_axis_facts([fact])

    assert len(result.accepted) == 1
    data = result.accepted[0].data
    assert data["property_name_raw"] == "total elongation relative ratio"
    assert data["value_raw"] == "nearly three times that at room temperature"
    assert data["unit_raw"] is None
    assert [issue.code for issue in result.issues] == [
        "property_relative_quantity_reclassified"
    ]
    assert result.issues[0].actual["reason"] == "textual_relative_ratio"


def test_directional_percentage_with_physical_unit_is_reclassified_as_relative_change():
    evidence = (
        "| Preheat Temp (C) | 39.3% \\uparrow | 242.3 | "
        "8.5% \\uparrow | delay \\uparrow heat buildup \\downarrow |"
    )
    result = filter_axis_facts(
        [
            _property(
                name="Preheat Temp",
                value="39.3% \\uparrow",
                unit="C",
                evidence=evidence,
            )
        ]
    )

    assert len(result.accepted) == 1
    data = result.accepted[0].data
    assert data["property_name_raw"] == "Preheat Temp relative change"
    assert data["value_raw"] == "39.3% \\uparrow"
    assert data["unit_raw"] == "%"
    assert [issue.code for issue in result.issues] == [
        "property_relative_quantity_reclassified"
    ]
    assert result.issues[0].actual["before"]["unit_raw"] == "C"
    assert result.issues[0].actual["after"]["unit_raw"] == "%"


def test_percentage_of_room_temperature_property_is_reclassified_as_retention():
    evidence = (
        "At 300 °C, the yield strength of the AF sample decreased to as low as "
        "37% of its room-temperature counterpart."
    )
    result = filter_axis_facts(
        [
            _property(
                name="yield strength",
                value="37%",
                unit="%",
                evidence=evidence,
            )
        ]
    )

    assert len(result.accepted) == 1
    data = result.accepted[0].data
    assert data["property_name_raw"] == "yield strength retention"
    assert data["value_raw"] == "37%"
    assert data["unit_raw"] == "%"
    assert [issue.code for issue in result.issues] == [
        "property_relative_quantity_reclassified"
    ]


def test_percentage_of_named_baseline_property_is_reclassified_as_retention():
    evidence = (
        "The AF sample retained approximately 83% of the room-temperature "
        "yield strength at 200 °C."
    )
    result = filter_axis_facts(
        [
            _property(
                name="yield strength",
                value="83%",
                unit="%",
                evidence=evidence,
            )
        ]
    )

    assert result.accepted[0].data["property_name_raw"] == "yield strength retention"
    assert [issue.code for issue in result.issues] == [
        "property_relative_quantity_reclassified"
    ]


def test_intrinsically_percent_properties_are_not_reclassified_without_a_baseline():
    facts = [
        _property(
            name="elongation",
            value="12%",
            unit="%",
            evidence="The elongation was 12%.",
        ),
        _property(
            name="relative density",
            value="99.5%",
            unit="%",
            evidence="The relative density reached 99.5%.",
        ),
        _property(
            name="porosity",
            value="0.4%",
            unit="%",
            evidence="The measured porosity was 0.4%.",
        ),
    ]

    result = filter_axis_facts(facts)

    assert result.accepted == facts
    assert result.issues == []


def test_already_relative_property_name_is_not_qualified_twice():
    fact = _property(
        name="yield strength retention",
        value="83%",
        unit="%",
        evidence=(
            "The yield strength retention was 83% of the room-temperature value."
        ),
    )

    result = filter_axis_facts([fact])

    assert result.accepted == [fact]
    assert result.issues == []


def test_existing_change_name_only_receives_percent_unit_without_duplicate_suffix():
    result = filter_axis_facts(
        [
            _property(
                name="average hardness increase",
                value="approximately 4%",
                unit="not_reported",
                evidence=(
                    "Approximately a 4% increase in average hardness was observed "
                    "when the interlayer delay increased from 0 to 300 s."
                ),
            )
        ]
    )

    assert result.accepted[0].data["property_name_raw"] == "average hardness increase"
    assert result.accepted[0].data["unit_raw"] == "%"
    assert [issue.code for issue in result.issues] == [
        "property_relative_quantity_reclassified"
    ]


def test_unrelated_change_word_in_evidence_does_not_reclassify_percent_property():
    fact = _property(
        name="elongation",
        value="12%",
        unit="not_reported",
        evidence=(
            "The elongation was 12% after the test temperature increased to 300 °C."
        ),
    )

    result = filter_axis_facts([fact])

    assert result.accepted == [fact]
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


def test_nominal_formula_subscripts_are_not_promoted_as_composition_scalars():
    evidence = "as-printed Al$_{92}$Ti$_{2}$Fe$_{2}$Co$_{2}$Ni$_{2}$"
    fact = CompositionFact(
        sample_id_raw="Al92Ti2Fe2Co2Ni2",
        fact_type="composition_observation",
        data={
            "observation_id": "temporary",
            "source_type": "nominal",
            "material_state": "as-printed",
            "sample_id": "Al92Ti2Fe2Co2Ni2",
            "basis": "at%",
            "component_type": "elemental",
            "components": [
                {
                    "name_raw": name,
                    "value_kind": "scalar",
                    "value_raw": value,
                    "unit_raw": "at%",
                    "data_nature": "reported",
                }
                for name, value in (
                    ("Al", "92"),
                    ("Ti", "2"),
                    ("Fe", "2"),
                    ("Co", "2"),
                    ("Ni", "2"),
                )
            ],
            "measurement": None,
            "raw_expression": "Al$_{92}$Ti$_{2}$Fe$_{2}$Co$_{2}$Ni$_{2}$",
            "data_source": "text",
            "source_evidence": [evidence],
            "note": None,
        },
        source_evidence=[evidence],
        confidence=0.9,
    )

    result = filter_composition_precision_facts([fact])

    assert result.accepted == []
    assert len(result.issues) == 5
    assert {issue.code for issue in result.issues} == {
        "composition_formula_subscript_quarantined"
    }


def test_measured_composition_percentages_survive_formula_gate():
    evidence = (
        "APT measured composition: 78.06% Al, 0.06% Ti, 5.45% Fe, "
        "7.53% Co and 8.90% Ni (at%)"
    )
    fact = CompositionFact(
        sample_id_raw="A1",
        fact_type="composition_observation",
        data={
            "observation_id": "temporary",
            "source_type": "measured",
            "material_state": "as-printed",
            "sample_id": "A1",
            "basis": "at%",
            "component_type": "elemental",
            "components": [
                {
                    "name_raw": "Al",
                    "value_kind": "scalar",
                    "value_raw": "78.06%",
                    "unit_raw": "at%",
                    "data_nature": "reported",
                }
            ],
            "measurement": "APT",
            "raw_expression": "78.06% Al",
            "data_source": "text",
            "source_evidence": [evidence],
            "note": None,
        },
        source_evidence=[evidence],
        confidence=0.9,
    )

    result = filter_composition_precision_facts([fact])

    assert result.accepted == [fact]
    assert result.issues == []


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


def test_semantic_property_aliases_preserve_distinct_elongation_subtypes():
    facts = [
        _property(
            name="uniform elongation",
            value="38",
            evidence="A1 uniform elongation was 38%.",
            unit="%",
        ),
        _property(
            name="fracture elongation",
            value="38",
            evidence="A1 fracture elongation was 38%.",
            unit="%",
        ),
        _property(
            name="total elongation",
            value="38",
            evidence="A1 total elongation was 38%.",
            unit="%",
        ),
    ]

    result = deduplicate_axis_facts_with_audit(facts)

    assert result.accepted == facts
    assert result.issues == []


def test_semantic_property_aliases_merge_same_fracture_elongation_subtype():
    first = _property(
        name="EAB",
        value="38",
        evidence="A1 EAB was 38%.",
        unit="%",
    )
    second = _property(
        name="elongation at fracture",
        value="38",
        evidence="A1 elongation at fracture was 38%.",
        unit="%",
    )

    result = deduplicate_axis_facts_with_audit([first, second])

    assert len(result.accepted) == 1
    assert [issue.code for issue in result.issues] == ["semantic_duplicate_merged"]


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
