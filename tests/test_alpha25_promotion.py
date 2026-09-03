from copy import deepcopy

from knowmat.alpha25.contracts import (
    CompositionFact,
    InventoryAnchor,
    ProcessingFact,
    PropertyFact,
    StructureFact,
)
from knowmat.alpha25.promotion import (
    PromotionDecision,
    PromotionIssue,
    build_owner_graph,
    build_promotion_records,
    deduplicate_source_assertions,
    deduplicate_cross_chunk_source_spans,
    group_source_assertions,
    promote_axis_facts,
    resolve_record_owner,
)
from knowmat.alpha25.claim_quality import filter_composition_precision_facts


def _property(
    *,
    sample: str = "A1",
    name: str = "yield strength",
    value: str = "900",
    unit: str = "MPa",
    condition: str = "650 °C",
    evidence: str = "A1 had a yield strength of 900 MPa at 650 °C.",
    confidence: float = 0.8,
    candidate_id: str = "temporary",
    evidence_unit_id: str = "prose-L000010-L000010-deadbeef",
) -> PropertyFact:
    return PropertyFact(
        sample_id_raw=sample,
        evidence_unit_id=evidence_unit_id,
        data={
            "property_id_candidate": candidate_id,
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
            "confidence": confidence,
        },
        source_evidence=[evidence],
        confidence=confidence,
    )


def _anchor(
    sample: str,
    *,
    material: str | None = None,
    state: str | None = None,
    role: str = "Target",
    evidence: str | None = None,
) -> InventoryAnchor:
    return InventoryAnchor(
        sample_id_raw=sample,
        material_name_raw=material,
        state_raw=state,
        role=role,
        data_nature=(
            "Experimental" if role == "Target" else "Literature_Experimental"
        ),
        source_evidence=[evidence or sample],
        confidence=0.9,
    )


def _structure(
    *,
    sample: str = "A1",
    evidence: str = "A1 contained fine gamma-prime precipitates.",
    entities: list[dict] | None = None,
    features: list[dict] | None = None,
    structure_kind: str = "precipitate",
    source_type: str = "reported",
) -> StructureFact:
    return StructureFact(
        sample_id_raw=sample,
        fact_type="structure_observation",
        evidence_unit_id="prose-L000001-L000001-structure",
        data={
            "observation_id": "temporary",
            "structure_kind": structure_kind,
            "material_state": "not_reported",
            "sample_id": sample,
            "source_type": source_type,
            "original": evidence,
            "simplified": evidence,
            "entities": entities
            if entities is not None
            else [
                {
                    "name_raw": "gamma-prime precipitates",
                    "entity_type": "precipitate",
                    "role": "reported",
                    "features": [],
                    "raw_expression": "gamma-prime precipitates",
                }
            ],
            "features": features or [],
            "source_evidence": [evidence],
        },
        source_evidence=[evidence],
        confidence=0.8,
    )


def _characterization(
    *,
    sample: str = "A1",
    method: str = "SEM",
    method_class: str | None = None,
    evidence: str = "A1 was examined by SEM.",
) -> StructureFact:
    return StructureFact(
        sample_id_raw=sample,
        fact_type="characterization",
        evidence_unit_id="prose-L000001-L000001-characterization",
        data={
            "characterization_id": "temporary",
            "method_raw": method,
            "method_class": method if method_class is None else method_class,
            "source_evidence": [evidence],
        },
        source_evidence=[evidence],
        confidence=0.8,
    )


def _processing(
    *,
    sample: str = "A1",
    process: str = "laser powder bed fusion",
    evidence: str = "A1 was fabricated by laser powder bed fusion.",
    parameters: list[dict] | None = None,
) -> ProcessingFact:
    return ProcessingFact(
        sample_id_raw=sample,
        fact_type="process_stage",
        evidence_unit_id="prose-L000001-L000001-processing",
        data={
            "candidate_stage_id": "temporary",
            "stage_index_candidate": 1,
            "process_name_raw": process,
            "process_code_candidate": "A2.AM.PBF_L",
            "process_role_candidate": "primary_forming",
            "parameters_raw": parameters or [],
            "source_evidence": [evidence],
            "confidence": 0.8,
        },
        source_evidence=[evidence],
        confidence=0.8,
    )


def _composition(
    *,
    sample: str = "A1",
    component: str = "Al",
    value: str = "47.86 ± 0.5",
    unit: str = "at.%",
    evidence: str = "A1 contained 47.86 ± 0.5 at.% Al.",
    region: str | None = None,
) -> CompositionFact:
    data = {
        "observation_id": "temporary",
        "source_type": "measured",
        "material_state": "not_reported",
        "sample_id": sample,
        "basis": "atomic_fraction",
        "component_type": "elemental",
        "components": [
            {
                "name_raw": component,
                "value_kind": "uncertainty",
                "value_raw": value,
                "unit_raw": unit,
                "data_nature": "reported",
            }
        ],
        "measurement": "EDS",
        "raw_expression": evidence,
        "data_source": "text",
        "source_evidence": [evidence],
        "note": None,
    }
    if region is not None:
        data["region"] = region
    return CompositionFact(
        sample_id_raw=sample,
        fact_type="composition_observation",
        evidence_unit_id="prose-L000001-L000001-composition",
        data=data,
        source_evidence=[evidence],
        confidence=0.9,
    )


def test_composition_precision_gate_isolates_qualitative_and_placeholder_components():
    fact = _composition(
        evidence=(
            "A1 contained 47.86 ± 0.5 at.% Al; Mo was present and Ti was not reported."
        )
    )
    fact.data["components"] = [
        fact.data["components"][0],
        {
            "name_raw": "Mo",
            "value_kind": "categorical",
            "value_raw": "present",
            "unit_raw": "",
            "data_nature": "reported",
        },
        {
            "name_raw": "Ti",
            "value_kind": "categorical",
            "value_raw": "not reported",
            "unit_raw": "",
            "data_nature": "reported",
        },
    ]

    result = filter_composition_precision_facts([fact])

    assert len(result.accepted) == 1
    assert [row["name_raw"] for row in result.accepted[0].data["components"]] == [
        "Al"
    ]
    assert [issue.actual["reason"] for issue in result.issues] == [
        "qualitative_or_comparative_component",
        "placeholder_or_unknown_kind",
    ]


def test_generic_structure_carrier_entity_is_quarantined_but_atomic_feature_survives():
    evidence = (
        "No defects were found in any sample, confirming the material is fully dense."
    )
    fact = _structure(
        sample="WAAM Ti64",
        evidence=evidence,
        entities=[
            {
                "name_raw": "material",
                "entity_type": "other",
                "role": "reported",
                "features": [],
                "raw_expression": "material",
            }
        ],
        features=[
            {
                "feature_name_raw": "porosity",
                "value_kind": "categorical",
                "value_raw": "No defects",
                "data_nature": "reported",
                "source_evidence": [evidence],
            }
        ],
    )

    result = promote_axis_facts(
        [_anchor("WAAM Ti64")], [fact], source_text=evidence
    )

    assert len(result.accepted) == 1
    assert result.accepted[0].data["entities"] == []
    assert result.accepted[0].data["features"][0]["feature_name_raw"] == "porosity"
    assert any(
        issue.code == "promotion_structure_generic_entity_quarantined"
        and issue.actual["reason"] == "generic_entity_only_projection"
        for issue in result.issues
    )


def test_specific_structure_entity_containing_generic_word_is_preserved():
    evidence = "A matrix material layer was observed at the interface."
    fact = _structure(
        evidence=evidence,
        entities=[
            {
                "name_raw": "matrix material layer",
                "entity_type": "layer",
                "role": "reported",
                "features": [],
                "raw_expression": "matrix material layer",
            }
        ],
    )

    result = promote_axis_facts([_anchor("A1")], [fact], source_text=evidence)

    assert len(result.accepted) == 1
    assert result.accepted[0].data["entities"][0]["name_raw"] == (
        "matrix material layer"
    )
    assert not any(
        issue.code == "promotion_structure_generic_entity_quarantined"
        for issue in result.issues
    )


def test_table_yes_entity_is_normalized_to_presence_feature():
    evidence = "| 617B | No | Yes |"
    fact = _structure(
        sample="617B",
        evidence=evidence,
        entities=[
            {
                "name_raw": "Carbide",
                "raw_expression": "Yes",
                "features": [],
            }
        ],
        features=[
            {
                "feature_name_raw": "Boride presence",
                "value_kind": "categorical",
                "value_raw": "No",
                "data_nature": "reported",
                "source_evidence": [evidence],
            }
        ],
    )

    result = promote_axis_facts([_anchor("617B")], [fact], source_text=evidence)

    assert len(result.accepted) == 1
    assert result.accepted[0].data["entities"] == []
    assert {
        (feature["feature_name_raw"], feature["value_raw"])
        for feature in result.accepted[0].data["features"]
    } == {("Boride presence", "No"), ("Carbide presence", "Yes")}
    assert any(
        issue.code == "promotion_structure_table_binary_entity_normalized"
        for issue in result.issues
    )


def test_cited_reference_table_structure_fact_routes_by_row_citation():
    evidence = "| Tytko [21] | 2012 | 617B | No | Yes |"
    fact = _structure(
        sample="617B",
        evidence=evidence,
        entities=[],
        features=[
            {
                "feature_name_raw": "Boride presence",
                "value_kind": "categorical",
                "value_raw": "No",
                "data_nature": "reported",
                "source_evidence": [evidence],
            }
        ],
    )
    anchors = [
        _anchor("617B"),
        _anchor(
            "617B [21] [reference]",
            material="617B",
            state="literature-reported",
            role="Reference",
            evidence=evidence,
        ),
    ]

    result = promote_axis_facts(anchors, [fact], source_text=evidence)

    assert len(result.accepted) == 1
    assert result.accepted[0].sample_id_raw == "617B [21] [reference]"
    assert any(
        issue.code == "promotion_cited_table_reference_owner_reassigned"
        for issue in result.issues
    )


def test_cited_reference_table_routes_unique_sibling_when_base_label_repeats():
    evidence = "| Blavette [32] | 1996 | Astroloy | Yes | Yes |"
    fact = _structure(
        sample="Astroloy",
        evidence=evidence,
        entities=[],
        features=[
            {
                "feature_name_raw": "Carbide presence",
                "value_kind": "categorical",
                "value_raw": "Yes",
                "data_nature": "reported",
                "source_evidence": [evidence],
            }
        ],
    )
    anchors = [
        _anchor("Astroloy"),
        _anchor("Astroloy", state="boron-containing superalloy"),
        _anchor(
            "Astroloy [32] [reference]",
            material="Astroloy",
            state="literature-reported",
            role="Reference",
            evidence=evidence,
        ),
        _anchor(
            "Astroloy [33] [reference]",
            material="Astroloy",
            state="literature-reported",
            role="Reference",
            evidence="| Letellier [33] | 1994 | Astroloy | No | No |",
        ),
    ]
    fact.data["material_state"] = "boron-containing superalloy"

    result = promote_axis_facts(anchors, [fact], source_text=evidence)

    assert len(result.accepted) == 1
    assert result.accepted[0].sample_id_raw == "Astroloy [32] [reference]"


def test_citation_cropped_reference_row_routes_by_exact_unique_cell_projection():
    evidence = "| Astroloy | Yes | Yes |"
    fact = _structure(
        sample="Astroloy",
        evidence=evidence,
        entities=[],
        features=[
            {
                "feature_name_raw": "Carbide presence",
                "value_kind": "categorical",
                "value_raw": "Yes",
                "data_nature": "reported",
                "source_evidence": [evidence],
            }
        ],
    )
    anchors = [
        _anchor("Astroloy"),
        _anchor("Astroloy", state="boron-containing superalloy"),
        _anchor(
            "Astroloy [32] [reference]",
            material="Astroloy",
            state="literature-reported",
            role="Reference",
            evidence="Blavette [32] | 1996 | Astroloy | 0.11 | Yes | Yes | Yes",
        ),
        _anchor(
            "Astroloy [33] [reference]",
            material="Astroloy",
            state="literature-reported",
            role="Reference",
            evidence="Letellier [33] | 1994 | Astroloy | 0.11 | Yes | No | No",
        ),
    ]
    fact.data["material_state"] = "boron-containing superalloy"

    result = promote_axis_facts(anchors, [fact], source_text=evidence)

    assert len(result.accepted) == 1
    assert result.accepted[0].sample_id_raw == "Astroloy [32] [reference]"
    assert result.accepted[0].data["material_state"] == "literature-reported"
    assert any(
        issue.code == "promotion_cited_table_reference_owner_reassigned"
        for issue in result.issues
    )


def test_citation_cropped_row_prefers_exact_suffix_over_loose_subsequence():
    evidence = "| N18 | No | No |"
    fact = _structure(
        sample="N18",
        evidence=evidence,
        entities=[],
        features=[
            {
                "feature_name_raw": "Boride presence",
                "value_kind": "categorical",
                "value_raw": "No",
                "data_nature": "reported",
                "source_evidence": [evidence],
            },
            {
                "feature_name_raw": "Carbide presence",
                "value_kind": "categorical",
                "value_raw": "No",
                "data_nature": "reported",
                "source_evidence": [evidence],
            },
        ],
    )
    fact.data["material_state"] = "boron-containing superalloy"
    anchors = [
        _anchor("N18"),
        _anchor("N18", state="boron-containing superalloy"),
        _anchor(
            "N18 [28] [reference]",
            material="N18",
            state="literature-reported",
            role="Reference",
            evidence="Lemarchand [28] | 2002 | N18 | 0.083 | Yes | No | No",
        ),
        _anchor(
            "N18 [29] [reference]",
            material="N18",
            state="literature-reported",
            role="Reference",
            evidence="Cadel [29] | 2002 | N18 | 0.083 | No | Yes | No",
        ),
    ]

    result = promote_axis_facts(anchors, [fact], source_text=evidence)

    assert len(result.accepted) == 1
    assert result.accepted[0].sample_id_raw == "N18 [28] [reference]"
    assert result.accepted[0].data["material_state"] == "literature-reported"


def test_citation_cropped_reference_row_never_guesses_between_identical_rows():
    evidence = "| Astroloy | Yes | No | No |"
    fact = _structure(
        sample="Astroloy",
        evidence=evidence,
        entities=[],
        features=[
            {
                "feature_name_raw": "Carbide presence",
                "value_kind": "categorical",
                "value_raw": "No",
                "data_nature": "reported",
                "source_evidence": [evidence],
            }
        ],
    )
    anchors = [
        _anchor("Astroloy"),
        _anchor(
            "Astroloy [33] [reference]",
            material="Astroloy",
            state="literature-reported",
            role="Reference",
            evidence="Letellier [33] | 1994 | Astroloy | 0.11 | Yes | No | No",
        ),
        _anchor(
            "Astroloy [34] [reference]",
            material="Astroloy",
            state="literature-reported",
            role="Reference",
            evidence="Letellier [34] | 1993 | Astroloy | 0.11 | Yes | No | No",
        ),
    ]

    result = promote_axis_facts(anchors, [fact], source_text=evidence)

    assert not any(
        issue.code == "promotion_cited_table_reference_owner_reassigned"
        for issue in result.issues
    )
    assert all(
        accepted.sample_id_raw not in {
            "Astroloy [33] [reference]",
            "Astroloy [34] [reference]",
        }
        for accepted in result.accepted
    )


def test_composition_precision_gate_keeps_balance_and_explicit_formula():
    fact = _composition(evidence="A1 nominal composition was Ti6Al4V with balance Fe.")
    fact.data["components"] = [
        {
            "name_raw": "Fe",
            "value_kind": "categorical",
            "value_raw": "Balance",
            "unit_raw": "",
            "data_nature": "reported",
        },
        {
            "name_raw": "nominal formula",
            "value_kind": "categorical",
            "value_raw": "Ti6Al4V",
            "unit_raw": "",
            "data_nature": "reported",
        },
    ]

    result = filter_composition_precision_facts([fact])

    assert not result.issues
    assert [row["value_kind"] for row in result.accepted[0].data["components"]] == [
        "balance",
        "categorical",
    ]


def test_composition_precision_gate_rejects_sentence_and_derived_descriptor():
    fact = _composition(
        evidence=(
            "CrB2 particles with diameters of ~10 μm were used as starting "
            "reinforcing particles; the aluminium equivalent was 9.31."
        )
    )
    fact.data["components"] = [
        {
            "name_raw": "CrB₂",
            "value_kind": "scalar",
            "value_raw": "Micron-sized CrB₂ with diameters of ~10 μm were used",
            "unit_raw": "unknown",
        },
        {
            "name_raw": "aluminium equivalent",
            "value_kind": "scalar",
            "value_raw": "9.31",
            "unit_raw": "unknown",
        },
    ]

    result = filter_composition_precision_facts([fact])

    assert not result.accepted
    assert [issue.actual["reason"] for issue in result.issues] == [
        "numeric_value_not_literal_amount",
        "non_atomic_descriptor_without_composition_unit",
    ]


def test_composition_precision_gate_blocks_unbound_numeric_projection():
    fact = _composition(evidence="A1 contained 47.86 ± 0.5 at.% Al.")
    fact.data["components"] = [
        fact.data["components"][0],
        {
            "name_raw": "Mo",
            "value_kind": "scalar",
            "value_raw": "2.5",
            "unit_raw": "at.%",
            "data_nature": "reported",
        },
    ]

    result = filter_composition_precision_facts([fact])

    assert len(result.accepted) == 1
    assert [row["name_raw"] for row in result.accepted[0].data["components"]] == [
        "Al"
    ]
    assert result.issues[0].actual["reason"] == "numeric_literal_not_in_component_evidence"


def test_composition_precision_gate_does_not_retype_trend_with_delay_number():
    """A number inside qualitative trend prose is not a composition amount."""

    evidence = (
        "Al wt% declines with increasing heat accumulation with wall height "
        "in the case of a 0 s delay."
    )
    fact = _composition(evidence=evidence)
    fact.data["components"] = [
        {
            "name_raw": "aluminum",
            "value_kind": "categorical",
            "value_raw": (
                "declines with increasing heat accumulation with wall height "
                "in the case of a 0 s delay"
            ),
            "unit_raw": "wt%",
            "data_nature": "reported",
        }
    ]

    result = filter_composition_precision_facts([fact])

    assert result.accepted == []
    assert [issue.actual["reason"] for issue in result.issues] == [
        "qualitative_or_comparative_component"
    ]


def test_composition_precision_gate_keeps_categorical_numeric_literal_with_unit():
    fact = _composition(
        value="48",
        unit="wt%",
        evidence="A1 contained 48 wt% Al.",
    )
    fact.data["components"][0]["value_kind"] = "categorical"

    result = filter_composition_precision_facts([fact])

    assert len(result.accepted) == 1
    assert result.accepted[0].data["components"][0]["value_kind"] == "scalar"
    assert result.issues == []


def test_composition_precision_gate_isolates_named_qualitative_trend():
    fact = _composition(
        value="higher",
        unit=None,
        evidence=(
            "CMSX-4 displays the strongest hardening effect due to the higher "
            "Ta and Ti concentrations in gamma prime."
        ),
    )
    fact.data["components"][0].update(
        {
            "name_raw": "Ta concentration in gamma prime",
            "value_kind": "categorical",
            "value_raw": "higher",
            "unit_raw": "",
        }
    )

    result = filter_composition_precision_facts([fact])

    assert result.accepted == []
    assert result.issues[0].actual["reason"] == (
        "qualitative_or_comparative_component"
    )


def test_composition_precision_gate_isolates_comparative_scalar_text():
    fact = _composition(
        value="about 64% lower than EBAM",
        unit="relative",
        evidence="The iron content was about 64% lower than EBAM.",
    )
    fact.data["components"][0]["value_kind"] = "scalar"

    result = filter_composition_precision_facts([fact])

    assert result.accepted == []
    assert result.issues[0].actual["reason"] == (
        "qualitative_or_comparative_component"
    )


def test_prose_owner_mismatch_is_quarantined_for_composition_and_processing():
    composition = _composition(
        sample="A2",
        evidence="A1 contained 47.86 ± 0.5 at.% Al.",
    )
    processing = _processing(
        sample="A2",
        evidence="A1 was fabricated by laser powder bed fusion.",
    )

    composition_result = promote_axis_facts(
        [_anchor("A1"), _anchor("A2")],
        [composition],
        source_text="A1 contained 47.86 ± 0.5 at.% Al.",
    )
    processing_result = promote_axis_facts(
        [_anchor("A1"), _anchor("A2")],
        [processing],
        source_text="A1 was fabricated by laser powder bed fusion.",
    )

    assert not composition_result.accepted
    assert any(
        issue.code == "promotion_evidence_explicit_owner_mismatch_quarantined"
        for issue in composition_result.issues
    )
    assert not processing_result.accepted
    assert any(
        issue.code == "promotion_evidence_explicit_owner_mismatch_quarantined"
        for issue in processing_result.issues
    )


def test_cited_comparison_table_value_moves_to_existing_reference_sibling():
    evidence = (
        "| Properties | Wrought | WAAM |\n"
        "| Vickers Hardness (HV) | 322 [ASTM F_{136}] | 332 [39] |"
    )
    fact = _property(
        sample="Wrought",
        name="Vickers Hardness",
        value="322",
        unit="HV",
        condition="",
        evidence=evidence,
    )
    fact.data["data_source"] = "table"
    fact.data["raw_note"] = "[ASTM F_{136}]"
    result = promote_axis_facts(
        [
            _anchor("Wrought", role="Target"),
            _anchor(
                "Wrought [37] [reference]",
                role="Reference",
            ),
        ],
        [fact],
        source_text=evidence,
    )

    assert len(result.accepted) == 1
    assert result.accepted[0].sample_id_raw == "Wrought [37] [reference]"
    assert any(
        issue.code == "promotion_cited_table_reference_owner_reassigned"
        for issue in result.issues
    )


def test_treatment_prefixed_processing_owner_without_literal_evidence_is_isolated():
    evidence = (
        "We annealed the as-built copper nanocomposites at 1173 K for 6 h."
    )
    fact = _processing(
        sample="annealed Cu-B4C composite",
        process="annealing",
        evidence=evidence,
        parameters=[
            {
                "parameter_name_raw": "temperature",
                "value_raw": "1173",
                "unit_raw": "K",
                "source_evidence": [evidence],
            },
            {
                "parameter_name_raw": "duration",
                "value_raw": "6",
                "unit_raw": "h",
                "source_evidence": [evidence],
            },
        ],
    )
    result = promote_axis_facts(
        [_anchor("annealed Cu-B4C composite")],
        [fact],
        source_text=evidence,
    )

    assert len(result.accepted) == 1
    assert result.accepted[0].data["entities"][0]["features"] == []
    assert any(
        issue.code == "promotion_processing_state_label_unbound_quarantined"
        for issue in result.issues
    )


def test_generic_treatment_stage_label_is_not_treated_as_a_new_material_owner():
    evidence = "with an optimum sintering temperature of 1280 °C and time of 4 h"
    fact = _processing(
        sample="sintered sample",
        process="sintering",
        evidence=evidence,
        parameters=[
            {
                "parameter_name_raw": "sintering temperature",
                "value_raw": "1280",
                "unit_raw": "°C",
                "source_evidence": [evidence],
            },
            {
                "parameter_name_raw": "time",
                "value_raw": "4",
                "unit_raw": "h",
                "source_evidence": [evidence],
            },
        ],
    )
    result = promote_axis_facts(
        [_anchor("sintered sample")], [fact], source_text=evidence
    )

    assert len(result.accepted) == 1
    assert not any(
        issue.code == "promotion_processing_state_label_unbound_quarantined"
        for issue in result.issues
    )


def test_processing_parameter_coordinate_routes_generic_owner_to_existing_state():
    evidence = (
        "with an optimum sintering temperature of 1280 °C and time of 4 h"
    )
    fact = _processing(
        sample="sintered sample",
        process="sintering",
        evidence=evidence,
        parameters=[
            {
                "parameter_name_raw": "sintering temperature",
                "value_raw": "1280",
                "unit_raw": "°C",
                "source_evidence": [evidence],
            },
            {
                "parameter_name_raw": "time",
                "value_raw": "4",
                "unit_raw": "h",
                "source_evidence": [evidence],
            },
        ],
    )
    state = _anchor(
        "sintered sample [sintered at 1280 °C]", state="sintered at 1280 °C"
    )
    result = promote_axis_facts(
        [_anchor("sintered sample"), state], [fact], source_text=evidence
    )

    assert len(result.accepted) == 1
    assert result.accepted[0].sample_id_raw == state.sample_id_raw
    assert any(
        issue.code == "promotion_processing_parameter_state_owner_reassigned"
        for issue in result.issues
    )


def test_source_numeric_unit_conflict_is_quarantined_without_conversion():
    fact = _processing(
        sample="A1",
        evidence="A1 was fabricated with a layer thickness of 50 μm.",
        parameters=[
            {
                "parameter_name_raw": "layer thickness",
                "value_raw": "50",
                "unit_raw": "mm",
                "source_evidence": [
                    "A1 was fabricated with a layer thickness of 50 μm."
                ],
            }
        ],
    )

    result = promote_axis_facts(
        [_anchor("A1")],
        [fact],
        source_text="A1 was fabricated with a layer thickness of 50 μm.",
    )

    assert not result.accepted
    issue = next(
        issue
        for issue in result.issues
        if issue.code == "promotion_source_unit_conflict_quarantined"
    )
    assert issue.actual["declared_unit"] == "mm"
    assert issue.actual["source_units"] == ["um"]


def test_non_tensile_property_source_unit_conflict_is_quarantined():
    evidence = "The fine rosette regions reached a microscopic compressive strength of 0.33 GPa."
    fact = _property(
        sample="Al9Ti2Fe2Co2Ni2 alloy",
        name="microscopic compressive strength",
        value="0.33",
        unit="MPa",
        condition="fine rosette regions",
        evidence=evidence,
    )

    result = promote_axis_facts(
        [_anchor("Al9Ti2Fe2Co2Ni2 alloy")], [fact], source_text=evidence
    )

    assert result.accepted == ()
    issue = next(
        issue
        for issue in result.issues
        if issue.code == "promotion_source_unit_conflict_quarantined"
    )
    assert issue.actual["declared_unit"] == "mpa"
    assert issue.actual["source_units"] == ["gpa"]


def test_numeric_comparative_structure_projection_is_isolated():
    fact = _structure(
        sample="A1",
        entities=[],
        evidence=(
            "A1 showed a percent increase relative to 300 s delay (topmost "
            "layer) of 32.9%."
        ),
        features=[
            {
                "feature_name_raw": "percent increase relative to 300 s delay (topmost layer)",
                "value_kind": "scalar",
                "value_raw": "32.9",
                "unit_raw": "%",
                "source_evidence": [
                    "A1 showed a percent increase relative to 300 s delay (topmost layer) of 32.9%."
                ],
            }
        ],
    )

    result = promote_axis_facts(
        [_anchor("A1")],
        [fact],
        source_text=fact.source_evidence[0],
    )

    assert not result.accepted
    assert any(
        issue.code == "promotion_structure_comparative_numeric_projection_quarantined"
        for issue in result.issues
    )


def test_qualitative_comparison_marked_as_inequality_is_isolated():
    evidence = (
        "WAAM had lower amounts of continuous alpha because of the lower cooling rate."
    )
    fact = _structure(
        sample="WAAM",
        evidence=evidence,
        entities=[],
        features=[
            {
                "feature_name_raw": "amount",
                "value_kind": "inequality",
                "value_raw": "lower amounts of continuous alpha",
                "data_nature": "reported",
            }
        ],
    )

    result = promote_axis_facts([_anchor("WAAM")], [fact], source_text=evidence)

    assert result.accepted == ()
    issue = next(
        issue
        for issue in result.issues
        if issue.code
        == "promotion_structure_comparative_text_without_magnitude_quarantined"
    )
    assert issue.actual["removed"] == fact.data["features"][0]


def test_unresolved_structure_formula_variable_is_isolated():
    evidence = (
        "The relation h = l_Gbar = x d gives a coefficient x for the HA1065 specimen."
    )
    fact = _structure(
        sample="HA1065",
        evidence=evidence,
        entities=[],
        features=[
            {
                "feature_name_raw": "area-weighted grain diameter",
                "value_kind": "scalar",
                "value_raw": "d",
                "data_nature": "calculated",
            }
        ],
    )

    result = promote_axis_facts(
        [_anchor("HA1065")], [fact], source_text=evidence
    )

    assert result.accepted == ()
    assert any(
        issue.code == "promotion_structure_unresolved_variable_quarantined"
        for issue in result.issues
    )


def test_formula_coefficient_structure_projection_is_isolated():
    evidence = "Using h = l_Gbar = x d, the coefficient x was 0.30 for HA1065."
    fact = _structure(
        sample="HA1065",
        evidence=evidence,
        entities=[],
        features=[
            {
                "feature_name_raw": "coefficient x",
                "value_kind": "scalar",
                "value_raw": "0.30",
                "data_nature": "calculated",
            }
        ],
    )

    result = promote_axis_facts(
        [_anchor("HA1065")], [fact], source_text=evidence
    )

    assert result.accepted == ()
    assert any(
        issue.code == "promotion_structure_derived_feature_quarantined"
        for issue in result.issues
    )


def test_feedstock_particle_size_is_not_promoted_as_structure():
    evidence = (
        "The particle size of the pre-alloyed powder was determined by a "
        "Mastersizer analyzer and ranged from 24.2 to 58.2 micrometers."
    )
    fact = _structure(
        sample="CCIMA powder",
        evidence=evidence,
        entities=[],
        features=[
            {
                "feature_name_raw": "particle size range size",
                "value_kind": "range",
                "value_raw": "24.2 to 58.2",
                "unit_raw": "micrometers",
                "data_nature": "reported",
            }
        ],
    )

    result = promote_axis_facts(
        [_anchor("CCIMA powder")], [fact], source_text=evidence
    )

    assert result.accepted == ()
    assert any(
        issue.code == "promotion_structure_feedstock_particle_projection_quarantined"
        for issue in result.issues
    )


def test_literal_lattice_parameter_and_schmid_factor_are_preserved():
    lattice_evidence = "A1 Al3Ti has a lattice parameter a = 0.384 nm."
    lattice = _structure(
        sample="A1",
        evidence=lattice_evidence,
        entities=[],
        features=[
            {
                "feature_name_raw": "a lattice parameter",
                "value_kind": "scalar",
                "value_raw": "0.384",
                "unit_raw": "nm",
                "data_nature": "reported",
            }
        ],
    )
    schmid_evidence = "A1 had a mean Schmid factor of 0.3449 for Z samples."
    schmid = _structure(
        sample="A1",
        evidence=schmid_evidence,
        structure_kind="texture",
        entities=[],
        features=[
            {
                "feature_name_raw": "mean Schmid factor Z samples",
                "value_kind": "scalar",
                "value_raw": "0.3449",
                "data_nature": "calculated",
            }
        ],
    )

    result = promote_axis_facts(
        [_anchor("A1")], [lattice, schmid],
        source_text=f"{lattice_evidence} {schmid_evidence}",
    )

    assert result.accepted == (lattice, schmid)
    assert not any(
        issue.code in {
            "promotion_structure_unresolved_variable_quarantined",
            "promotion_structure_derived_feature_quarantined",
        }
        for issue in result.issues
    )


def test_v205_structure_relation_keeps_atomic_result_and_quarantines_denominator():
    evidence = (
        "The Laves phase volume fraction was 1.2 vol% per 0.1 at.% Al loss."
    )
    fact = _structure(
        sample="A1",
        evidence=evidence,
        entities=[],
        features=[
            {
                "feature_name_raw": "Laves phase volume fraction",
                "value_kind": "scalar",
                "value_raw": "1.2",
                "unit_raw": "vol%",
                "data_nature": "reported",
            },
            {
                "feature_name_raw": "Al loss increment",
                "value_kind": "scalar",
                "value_raw": "0.1",
                "unit_raw": "at.%",
                "data_nature": "reported",
            },
        ],
    )

    result = promote_axis_facts([_anchor("A1")], [fact], source_text=evidence)

    assert len(result.accepted) == 1
    assert [
        row["feature_name_raw"] for row in result.accepted[0].data["features"]
    ] == ["Laves phase volume fraction"]
    issue = next(
        row
        for row in result.issues
        if row.code == "structure_assertion_projection_quarantined"
    )
    assert issue.actual["removed"]["feature_name_raw"] == "Al loss increment"
    assert issue.actual["reason"] == "relational_denominator_fragment"
    assert issue.actual["decision_key"].startswith("structure-v205:")


def test_v205_structure_fraction_keeps_atomic_fraction_not_size_threshold_operand():
    evidence = "Over 60% of the grains measured less than 5 μm."
    fact = _structure(
        sample="A1",
        evidence=evidence,
        entities=[],
        features=[
            {
                "feature_name_raw": "fraction of grains below 5 μm",
                "value_kind": "inequality",
                "value_raw": ">60%",
                "unit_raw": "%",
                "data_nature": "reported",
            },
            {
                "feature_name_raw": "size threshold",
                "value_kind": "inequality",
                "value_raw": "<5",
                "unit_raw": "μm",
                "data_nature": "reported",
            },
        ],
    )

    result = promote_axis_facts([_anchor("A1")], [fact], source_text=evidence)

    assert len(result.accepted) == 1
    assert [row["value_raw"] for row in result.accepted[0].data["features"]] == [
        ">60%"
    ]
    assert any(
        row.code == "structure_assertion_projection_quarantined"
        and row.actual["reason"] == "relational_threshold_fragment"
        for row in result.issues
    )


def test_v205_structure_process_condition_is_not_an_observed_feature():
    evidence = "Sintered above 1260 °C, NbC peaks were detected."
    fact = _structure(
        sample="A1",
        evidence=evidence,
        entities=[],
        features=[
            {
                "feature_name_raw": "formation temperature condition",
                "value_kind": "inequality",
                "value_raw": "above 1260 °C",
                "unit_raw": "°C",
                "data_nature": "reported",
            }
        ],
    )

    result = promote_axis_facts([_anchor("A1")], [fact], source_text=evidence)

    assert result.accepted == ()
    assert any(
        row.code == "structure_assertion_projection_quarantined"
        and row.actual["reason"] == "process_condition_fragment"
        for row in result.issues
    )


def test_v205_structure_atomicity_preserves_literal_grain_size_and_lattice_parameter():
    evidence = (
        "A1 had grain sizes below 10 μm and an a lattice parameter of 0.384 nm."
    )
    fact = _structure(
        sample="A1",
        evidence=evidence,
        entities=[],
        features=[
            {
                "feature_name_raw": "grain size",
                "value_kind": "inequality",
                "value_raw": "<10",
                "unit_raw": "μm",
                "data_nature": "reported",
            },
            {
                "feature_name_raw": "a lattice parameter",
                "value_kind": "scalar",
                "value_raw": "0.384",
                "unit_raw": "nm",
                "data_nature": "reported",
            },
        ],
    )

    result = promote_axis_facts([_anchor("A1")], [fact], source_text=evidence)

    assert result.accepted == (fact,)
    assert not any(
        row.code == "structure_assertion_projection_quarantined"
        for row in result.issues
    )


def test_structure_negative_literal_nonphysical_value_is_quarantined():
    evidence = "The Cu-12%-ANP sample had a grain size of -390 nm."
    fact = _structure(
        sample="Cu-12%-ANP",
        evidence=evidence,
        entities=[],
        features=[
            {
                "feature_name_raw": "grain size",
                "value_kind": "scalar",
                "value_raw": "-390",
                "unit_raw": "nm",
                "data_nature": "reported",
            }
        ],
    )

    result = promote_axis_facts(
        [_anchor("Cu-12%-ANP")], [fact], source_text=evidence
    )

    assert result.accepted == ()
    issue = next(
        row
        for row in result.issues
        if row.code == "promotion_structure_nonphysical_value_quarantined"
    )
    removed = issue.actual["removed"]
    assert removed.get("value_raw") == "-390"


def test_structure_signed_orientation_is_not_caught_by_nonphysical_gate():
    evidence = "The build orientation was -45 degrees."
    fact = _structure(
        sample="A1",
        evidence=evidence,
        entities=[],
        features=[
            {
                "feature_name_raw": "build orientation",
                "value_kind": "scalar",
                "value_raw": "-45",
                "unit_raw": "degrees",
                "data_nature": "reported",
            }
        ],
    )

    result = promote_axis_facts([_anchor("A1")], [fact], source_text=evidence)

    assert not any(
        row.code == "promotion_structure_nonphysical_value_quarantined"
        for row in result.issues
    )


def test_v205_structure_atomicity_switch_off_preserves_relational_operand(
    monkeypatch,
):
    monkeypatch.setenv("KNOWMAT2_ALPHA25_STRUCTURE_ASSERTION_ATOMICITY_V205", "0")
    evidence = "The Laves phase increased 1.2 vol% per 0.1 at.% Al loss."
    fact = _structure(
        sample="A1",
        evidence=evidence,
        entities=[],
        features=[
            {
                "feature_name_raw": "Al loss increment",
                "value_kind": "scalar",
                "value_raw": "0.1",
                "unit_raw": "at.%",
                "data_nature": "reported",
            }
        ],
    )

    result = promote_axis_facts([_anchor("A1")], [fact], source_text=evidence)

    assert result.accepted == (fact,)
    assert not any(
        row.code == "structure_assertion_projection_quarantined"
        for row in result.issues
    )


def test_crystallographic_orientation_relationship_is_preserved():
    evidence = "A1 showed a cube-cube orientation relationship between gamma and gamma-prime."
    fact = _structure(
        sample="A1",
        evidence=evidence,
        entities=[],
        features=[
            {
                "feature_name_raw": "orientation relationship",
                "value_kind": "categorical",
                "value_raw": "cube-cube",
                "data_nature": "reported",
            }
        ],
    )

    result = promote_axis_facts([_anchor("A1")], [fact], source_text=evidence)

    assert result.accepted == (fact,)
    assert not any(
        issue.code == "promotion_structure_derived_feature_quarantined"
        for issue in result.issues
    )


def test_structure_numeric_local_region_without_coordinate_is_isolated():
    evidence = "At the fracture surface, the fine-grain diameter was 120 nm."
    fact = _structure(
        sample="A1",
        evidence=evidence,
        entities=[],
        features=[
            {
                "feature_name_raw": "fine-grain diameter",
                "value_kind": "scalar",
                "value_raw": "120",
                "unit_raw": "nm",
                "data_nature": "reported",
            }
        ],
    )

    result = promote_axis_facts([_anchor("A1")], [fact], source_text=evidence)

    assert result.accepted == ()
    assert any(
        issue.code == "promotion_structure_region_coordinate_missing_quarantined"
        for issue in result.issues
    )


def test_structure_numeric_local_region_coordinate_is_preserved():
    evidence = "At the fracture surface, the fine-grain diameter was 120 nm."
    fact = _structure(
        sample="A1",
        evidence=evidence,
        entities=[],
        features=[
            {
                "feature_name_raw": "fine-grain diameter",
                "value_kind": "scalar",
                "value_raw": "120",
                "unit_raw": "nm",
                "region": "fracture surface",
                "data_nature": "reported",
            }
        ],
    )

    result = promote_axis_facts([_anchor("A1")], [fact], source_text=evidence)

    assert result.accepted == (fact,)
    assert not any(
        issue.code == "promotion_structure_region_coordinate_missing_quarantined"
        for issue in result.issues
    )


def test_qualitative_structure_effect_and_threshold_projections_are_isolated():
    evidence = (
        "Thermal stress influences variant selection, and a 10 degree "
        "misorientation threshold was used as the selection criterion."
    )
    fact = _structure(
        sample="A1",
        entities=[],
        evidence=evidence,
        features=[
            {
                "feature_name_raw": "thermal stress effect",
                "value_kind": "text",
                "value_raw": "thermal stress influences variant selection",
                "source_evidence": [evidence],
            },
            {
                "feature_name_raw": "misorientation threshold criterion",
                "value_kind": "text",
                "value_raw": "threshold criterion",
                "source_evidence": [evidence],
            },
        ],
    )

    result = promote_axis_facts([_anchor("A1")], [fact], source_text=evidence)

    assert result.accepted == ()
    assert sum(
        issue.code == "promotion_structure_comparative_projection_quarantined"
        for issue in result.issues
    ) == 1
    assert any(
        issue.code == "promotion_structure_feature_unsupported"
        and issue.actual["removed"] == fact.data["features"][1]
        for issue in result.issues
    )


def test_qualitative_structure_value_must_be_grounded_in_one_local_sentence():
    """Do not assemble a qualitative feature from unrelated chunk sentences."""

    evidence = (
        "The alloy contained a bimodal grain structure. "
        "The precipitates were uniformly distributed in the matrix."
    )
    fact = _structure(
        sample="A1",
        evidence=evidence,
        entities=[],
        features=[
            {
                "feature_name_raw": "grain structure",
                "value_kind": "text",
                "value_raw": "bimodal uniformly distributed",
                "source_evidence": [evidence],
            }
        ],
    )

    result = promote_axis_facts([_anchor("A1")], [fact], source_text=evidence)

    assert result.accepted == ()
    assert any(
        issue.code == "promotion_structure_feature_unsupported"
        and issue.actual["removed"] == fact.data["features"][0]
        for issue in result.issues
    )


def test_qualitative_structure_value_in_one_sentence_remains_eligible():
    evidence = "The alloy contained a bimodal grain structure with uniform distribution."
    fact = _structure(
        sample="A1",
        evidence=evidence,
        entities=[],
        features=[
            {
                "feature_name_raw": "grain structure",
                "value_kind": "text",
                "value_raw": "bimodal grain structure with uniform distribution",
                "source_evidence": [evidence],
            }
        ],
    )

    result = promote_axis_facts([_anchor("A1")], [fact], source_text=evidence)

    assert result.accepted == (fact,)


def test_comparative_adjectives_and_feedstock_descriptors_are_isolated():
    """Reject qualitative comparison/ powder metadata despite direct verbs."""

    evidence = (
        "The phase structure showed a weaker texture intensity in the PBF-EB samples. "
        "Finer, more agglomerated powder particles are seen in powder used for binder "
        "jetting fabrication."
    )
    fact = _structure(
        sample="PBF-EB",
        evidence=evidence,
        entities=[],
        features=[
            {
                "feature_name_raw": "texture intensity",
                "value_kind": "categorical",
                "value_raw": "weaker",
                "source_evidence": [
                    "The phase structure showed a weaker texture intensity in the PBF-EB samples."
                ],
            },
            {
                "feature_name_raw": "particle shape",
                "value_kind": "categorical",
                "value_raw": "finer, more agglomerated",
                "source_evidence": [
                    "Finer, more agglomerated powder particles are seen in powder used for binder jetting fabrication."
                ],
            },
        ],
    )

    result = promote_axis_facts([_anchor("PBF-EB")], [fact], source_text=evidence)

    assert result.accepted == ()
    assert sum(
        issue.code == "promotion_structure_comparative_projection_quarantined"
        for issue in result.issues
    ) == 2


def test_comparative_precipitate_size_is_not_rescued_by_direct_presence_verb():
    evidence = (
        "The gamma precipitates appear less dense but are generally larger as compared "
        "to the as-sintered condition."
    )
    fact = _structure(
        sample="HIP1",
        evidence=evidence,
        entities=[],
        features=[
            {
                "feature_name_raw": "gamma precipitate size",
                "value_kind": "categorical",
                "value_raw": "generally larger as compared to the as-sintered condition",
                "source_evidence": [evidence],
            }
        ],
    )

    result = promote_axis_facts([_anchor("HIP1")], [fact], source_text=evidence)

    assert result.accepted == ()
    assert any(
        issue.code == "promotion_structure_comparative_projection_quarantined"
        for issue in result.issues
    )


def test_treatment_outcome_is_not_published_as_structure_feature():
    evidence = "The aging treatment partially relieved the residual strain of the as-printed alloy."
    fact = _structure(
        sample="As-printed",
        evidence=evidence,
        entities=[],
        features=[
            {
                "feature_name_raw": "residual strain",
                "value_kind": "categorical",
                "value_raw": "partially relieved by aging treatment",
                "source_evidence": [evidence],
            }
        ],
    )

    result = promote_axis_facts([_anchor("As-printed")], [fact], source_text=evidence)

    assert result.accepted == ()
    assert any(
        issue.code == "promotion_structure_comparative_projection_quarantined"
        for issue in result.issues
    )


def test_promotion_record_is_stable_across_order_confidence_and_generated_ids():
    first = _property(confidence=0.6, candidate_id="prop_a")
    second = _property(confidence=0.99, candidate_id="prop_b")

    forward = build_promotion_records(
        [first, second], task_ids=["task-a", "task-b"]
    )
    reverse = build_promotion_records(
        [second, first], task_ids=["task-b", "task-a"]
    )

    assert [row.claim_id for row in forward] == [
        row.claim_id for row in reversed(reverse)
    ]
    assert forward[0].claim_id == forward[1].claim_id
    assert forward[0].source_order == 0
    assert forward[1].source_order == 1
    assert forward[0].task_id == "task-a"
    assert forward[0].evidence_unit_id == first.evidence_unit_id


def test_promotion_record_id_changes_for_scientific_identity_fields():
    baseline = _property()
    variants = [
        _property(sample="A2"),
        _property(value="901"),
        _property(condition="700 °C"),
        _property(evidence="A1 had a yield strength of 900 MPa after aging."),
    ]

    baseline_id = build_promotion_records([baseline])[0].claim_id

    assert all(
        build_promotion_records([variant])[0].claim_id != baseline_id
        for variant in variants
    )


def test_promotion_record_preserves_original_fact_and_normalizes_evidence():
    fact = _property(
        evidence="  A1  HAD a yield strength of 900 MPa at 650 °C.  "
    )

    record = build_promotion_records([fact])[0]

    assert record.fact is fact
    assert record.evidence == tuple(fact.source_evidence)
    assert record.normalized_evidence == (
        "a1 had a yield strength of 900 mpa at 650 °c.",
    )
    assert record.explicit_owner == "A1"
    assert record.owner_candidates == ("A1",)
    assert record.risk_codes == ()


def test_task_id_sequence_must_cover_every_fact():
    facts = [_property(), _property(value="901")]

    try:
        build_promotion_records(facts, task_ids=["only-one"])
    except ValueError as exc:
        assert "task_ids" in str(exc)
    else:  # pragma: no cover - documents the required failure mode.
        raise AssertionError("expected a provenance length error")


def test_promotion_decision_is_strict_and_immutable():
    decision = PromotionDecision(
        action="merge",
        candidate_ids=("claim-a", "claim-b"),
        survivor_id="claim-a",
        rule="same_source_assertion",
    )

    assert decision.action == "merge"
    assert decision.candidate_ids == ("claim-a", "claim-b")
    try:
        decision.action = "accept"
    except (AttributeError, TypeError):
        pass
    else:  # pragma: no cover - frozen dataclass contract.
        raise AssertionError("promotion decisions must be immutable")


def test_promotion_issue_retains_complete_removed_and_survivor_payloads():
    loser = _property(candidate_id="coarse", evidence="A1 had YS 900 MPa.")
    survivor = _property(
        candidate_id="rich",
        value="900 ± 20",
        evidence="A1 had YS 900 ± 20 MPa at 650 °C.",
    )
    after = survivor.model_copy(deep=True)
    after.source_evidence.append(loser.source_evidence[0])
    issue = PromotionIssue(
        code="promotion_richer_assertion_survived",
        sample_id_raw="A1",
        message="A less complete projection was merged.",
        evidence=[*loser.source_evidence, *survivor.source_evidence],
        expected={"decision": "one richer survivor"},
        actual={
            "removed": loser.model_dump(),
            "survivor_before": survivor.model_dump(),
            "survivor_after": after.model_dump(),
        },
        suggested_action="Review only if these are independent assertions.",
    )

    payload = issue.to_dict()

    assert payload["code"] == "promotion_richer_assertion_survived"
    assert payload["path"] == "items.A1"
    assert payload["actual"]["removed"] == loser.model_dump()
    assert payload["actual"]["survivor_before"] == survivor.model_dump()
    assert payload["actual"]["survivor_after"] == after.model_dump()
    assert payload["evidence"] == [
        *loser.source_evidence,
        *survivor.source_evidence,
    ]


def test_build_records_does_not_mutate_candidate_payload():
    fact = _property()
    before = deepcopy(fact.model_dump())

    build_promotion_records([fact], task_ids=["task-a"])

    assert fact.model_dump() == before


def test_exact_and_contained_evidence_share_one_source_assertion():
    source = "A1 had a yield strength of 900 MPa at 650 °C."
    full = _property(evidence=source)
    contained = _property(evidence="yield strength of 900 MPa at 650 °C")
    records = build_promotion_records([full, contained])

    groups = group_source_assertions(records, source_text=source)

    assert len(groups) == 1
    assert groups[0].source_kind == "prose"
    assert groups[0].source_block_key.startswith("prose:L000001-L000001")
    assert groups[0].records == tuple(records)


def test_identical_text_repeated_in_two_paragraphs_is_not_synthetically_joined():
    sentence = "A1 had a yield strength of 900 MPa at 650 °C."
    source = f"{sentence}\n\n{sentence}"
    first = _property(evidence=sentence, evidence_unit_id="prose-first")
    second = _property(evidence=sentence, evidence_unit_id="prose-second")

    groups = group_source_assertions(
        build_promotion_records([first, second]), source_text=source
    )

    assert len(groups) == 2
    assert all(group.ambiguous_source for group in groups)


def test_multi_column_table_keeps_distinct_owner_value_assertions():
    source = "\n".join(
        [
            "| Property | A1 | A2 |",
            "|---|---:|---:|",
            "| Yield strength (MPa) | 900 | 850 |",
        ]
    )
    evidence = [
        "| Property | A1 | A2 |",
        "| Yield strength (MPa) | 900 | 850 |",
    ]
    first = _property(
        sample="A1", value="900", evidence=evidence[0]
    )
    first.source_evidence = evidence
    first.data["source_evidence"] = evidence
    second = _property(
        sample="A2", value="850", evidence=evidence[0]
    )
    second.source_evidence = evidence
    second.data["source_evidence"] = evidence

    groups = group_source_assertions(
        build_promotion_records([first, second]), source_text=source
    )

    assert len(groups) == 2
    assert {group.projection_owner for group in groups} == {"A1", "A2"}
    assert {group.source_block_key for group in groups} == {
        groups[0].source_block_key
    }
    assert all(group.source_kind == "table" for group in groups)


def test_explicit_shared_owner_sentence_retains_one_projection_per_owner():
    source = "A1 and A2 both had a yield strength of 900 MPa at 650 °C."
    facts = [
        _property(sample="A1", evidence=source),
        _property(sample="A2", evidence=source),
    ]

    groups = group_source_assertions(
        build_promotion_records(facts), source_text=source
    )

    assert len(groups) == 2
    assert {group.projection_owner for group in groups} == {"A1", "A2"}
    assert len({group.source_block_key for group in groups}) == 1


def test_similar_claims_in_distinct_source_blocks_remain_independent():
    source = (
        "A1 had a yield strength of 900 MPa at 650 °C.\n\n"
        "After a repeat test, A1 again had a yield strength of 900 MPa at 650 °C."
    )
    facts = [
        _property(evidence="A1 had a yield strength of 900 MPa at 650 °C."),
        _property(
            evidence=(
                "After a repeat test, A1 again had a yield strength of "
                "900 MPa at 650 °C."
            )
        ),
    ]

    groups = group_source_assertions(
        build_promotion_records(facts), source_text=source
    )

    assert len(groups) == 2
    assert len({group.source_block_key for group in groups}) == 2


def test_source_assertion_duplicate_merges_into_richer_evidence_with_audit():
    source = "A1 had a yield strength of 900 MPa at 650 °C."
    full = _property(evidence=source, candidate_id="full")
    contained = _property(
        evidence="yield strength of 900 MPa at 650 °C",
        candidate_id="contained",
    )

    result = deduplicate_source_assertions([contained, full], source_text=source)

    assert len(result.accepted) == 1
    survivor = result.accepted[0]
    assert survivor.data["property_id_candidate"] == "full"
    assert survivor.source_evidence == [
        source,
        "yield strength of 900 MPa at 650 °C",
    ]
    assert survivor.data["source_evidence"] == survivor.source_evidence
    assert [issue.code for issue in result.issues] == [
        "promotion_assertion_duplicate_merged"
    ]
    issue = result.issues[0]
    assert issue.actual["removed"] == contained.model_dump()
    assert issue.actual["survivor_before"] == full.model_dump()
    assert issue.actual["survivor_after"] == survivor.model_dump()


def test_dedup_preserves_multi_column_and_independent_prose_assertions():
    table = "\n".join(
        [
            "| Property | A1 | A2 |",
            "|---|---:|---:|",
            "| Yield strength (MPa) | 900 | 850 |",
        ]
    )
    header = "| Property | A1 | A2 |"
    row = "| Yield strength (MPa) | 900 | 850 |"
    first = _property(sample="A1", value="900", evidence=header)
    first.source_evidence = [header, row]
    first.data["source_evidence"] = [header, row]
    second = _property(sample="A2", value="850", evidence=header)
    second.source_evidence = [header, row]
    second.data["source_evidence"] = [header, row]

    table_result = deduplicate_source_assertions(
        [first, second], source_text=table
    )

    assert table_result.accepted == (first, second)
    assert table_result.issues == ()

    sentence = "A1 had a yield strength of 900 MPa at 650 °C."
    prose_result = deduplicate_source_assertions(
        [
            _property(evidence=sentence, evidence_unit_id="first"),
            _property(evidence=sentence, evidence_unit_id="second"),
        ],
        source_text=f"{sentence}\n\n{sentence}",
    )

    assert len(prose_result.accepted) == 2
    assert prose_result.issues == ()


def test_source_assertion_dedup_is_input_permutation_deterministic():
    source = "A1 had a yield strength of 900 MPa at 650 °C."
    full = _property(evidence=source, candidate_id="full")
    contained = _property(
        evidence="yield strength of 900 MPa at 650 °C",
        candidate_id="contained",
    )

    forward = deduplicate_source_assertions([full, contained], source_text=source)
    reverse = deduplicate_source_assertions([contained, full], source_text=source)

    assert [fact.model_dump() for fact in forward.accepted] == [
        fact.model_dump() for fact in reverse.accepted
    ]
    assert [issue.to_dict() for issue in forward.issues] == [
        issue.to_dict() for issue in reverse.issues
    ]


def test_owner_graph_resolves_explicit_state_without_broadcasting_base():
    graph = build_owner_graph(
        [
            _anchor("Alloy A", material="Alloy A"),
            _anchor("Alloy A", material="Alloy A", state="as-built"),
            _anchor("Alloy A", material="Alloy A", state="aged"),
        ]
    )
    base = build_promotion_records(
        [
            _property(
                sample="Alloy A",
                evidence="Alloy A had a yield strength of 900 MPa at 650 °C.",
            )
        ]
    )[0]
    aged_fact = _property(
        sample="Alloy A",
        evidence="The aged Alloy A had a yield strength of 900 MPa at 650 °C.",
    )
    aged_fact.data["material_state"] = "aged"
    aged = build_promotion_records([aged_fact])[0]

    base_resolution = resolve_record_owner(base, graph)
    aged_resolution = resolve_record_owner(aged, graph)

    assert len(base_resolution.owner_ids) == 1
    assert graph.display_label(base_resolution.owner_ids[0]) == "Alloy A"
    assert base_resolution.risk_codes == ()
    assert len(aged_resolution.owner_ids) == 1
    assert graph.display_label(aged_resolution.owner_ids[0]) == "Alloy A [aged]"
    assert aged_resolution.risk_codes == ()


def test_owner_graph_recovers_bracketed_sample_state_and_lineage():
    graph = build_owner_graph(
        [
            _anchor("EBAM Ti-6Al-4V", material="Ti-6Al-4V"),
            _anchor("EBAM [as-built]", material="Ti-6Al-4V"),
        ]
    )

    state_child = next(node for node in graph.nodes if node.state_raw == "as-built")
    base = next(node for node in graph.nodes if not node.state_raw)

    assert state_child.sample_id_raw == "EBAM [as-built]"
    # The compact state-child label and expanded base label are joined only
    # because their material name and role/data nature agree.
    assert state_child.material_name_raw == base.material_name_raw


def test_processing_parameter_routes_to_bracketed_as_built_owner():
    evidence = "EBAM specimens were built on the machine with a layer thickness of 100 um."
    fact = _processing(
        sample="EBAM Ti-6Al-4V",
        evidence=evidence,
        parameters=[
            {
                "parameter_name_raw": "layer thickness",
                "value_raw": "100",
                "unit_raw": "um",
                "source_evidence": [evidence],
            }
        ],
    )

    result = promote_axis_facts(
        [
            _anchor("EBAM Ti-6Al-4V", material="Ti-6Al-4V"),
            _anchor("EBAM [as-built]", material="Ti-6Al-4V"),
        ],
        [fact],
        source_text=evidence,
    )

    assert len(result.accepted) == 1
    assert result.accepted[0].sample_id_raw == "EBAM [as-built]"
    assert any(
        issue.code == "promotion_processing_implicit_state_owner_reassigned"
        for issue in result.issues
    )


def test_generic_owner_without_base_anchor_is_ambiguous_not_broadcast():
    graph = build_owner_graph(
        [
            _anchor("Alloy A", material="Alloy A", state="as-built"),
            _anchor("Alloy A", material="Alloy A", state="aged"),
        ]
    )
    record = build_promotion_records(
        [
            _property(
                sample="Alloy A",
                evidence="Alloy A had a yield strength of 900 MPa.",
                condition="",
            )
        ]
    )[0]

    resolution = resolve_record_owner(record, graph)

    assert resolution.owner_ids == ()
    assert resolution.candidate_owner_ids == tuple(
        sorted(node.owner_id for node in graph.nodes)
    )
    assert resolution.risk_codes == ("ambiguous_owner",)


def test_state_named_in_evidence_selects_one_existing_child_owner():
    graph = build_owner_graph(
        [
            _anchor("Alloy A", material="Alloy A", state="as-built"),
            _anchor("Alloy A", material="Alloy A", state="aged"),
        ]
    )
    fact = _property(
        sample="Alloy A",
        evidence="The aged Alloy A had a yield strength of 900 MPa.",
        condition="",
    )
    fact.data["material_state"] = "aged"
    record = build_promotion_records([fact])[0]

    resolution = resolve_record_owner(record, graph)

    assert len(resolution.owner_ids) == 1
    assert graph.display_label(resolution.owner_ids[0]) == "Alloy A [aged]"
    assert resolution.risk_codes == ()


def test_structure_material_state_routes_to_unique_existing_state_owner():
    anchors = [
        _anchor("A1", material="alloy A"),
        _anchor("A1-aged", material="alloy A", state="aged"),
    ]
    evidence = "The aged alloy A contained fine gamma-prime precipitates."
    fact = _structure(sample="alloy A", evidence=evidence)
    fact.data["material_state"] = "aged"
    fact.data["sample_id"] = "alloy A"

    result = promote_axis_facts(anchors, [fact], source_text=evidence)

    assert len(result.accepted) == 1
    routed = result.accepted[0]
    assert isinstance(routed, StructureFact)
    assert routed.sample_id_raw == "A1-aged"
    assert routed.data["sample_id"] == "A1-aged"
    assert [issue.code for issue in result.issues] == [
        "promotion_structure_state_owner_reassigned"
    ]
    issue = result.issues[0]
    assert issue.actual["before"] == fact.model_dump()
    assert issue.actual["after"] == routed.model_dump()
    assert issue.expected["coordinate_kind"] == "material_state"


def test_structure_source_state_routes_when_extractor_lost_material_state():
    """A prose state coordinate must not remain on the generic base owner."""

    evidence = "In the as-built condition, Alloy A contained fine gamma-prime precipitates."
    fact = _structure(sample="Alloy A", evidence=evidence)
    anchors = [
        _anchor("Alloy A", material="alloy A"),
        _anchor("Alloy A [as-built]", material="alloy A", state="as-built"),
        _anchor("Alloy A [aged]", material="alloy A", state="aged"),
    ]

    result = promote_axis_facts(anchors, [fact], source_text=evidence)

    assert len(result.accepted) == 1
    routed = result.accepted[0]
    assert isinstance(routed, StructureFact)
    assert routed.sample_id_raw == "Alloy A [as-built]"
    assert routed.data["sample_id"] == "Alloy A [as-built]"
    assert routed.data["material_state"] == "as-built"
    assert [issue.code for issue in result.issues] == [
        "promotion_structure_source_state_owner_reassigned"
    ]


def test_structure_source_state_routes_to_owner_label_suffix_coordinate():
    """Inventory rows may encode a grounded state in Sample_ID only."""

    evidence = (
        "The fracture surface of samples built using binder jetting showed "
        "un-sintered powder particles within fracture micro-voids."
    )
    fact = _structure(
        sample="Inconel 625",
        evidence=evidence,
        entities=[
            {
                "name_raw": "un-sintered powder particles",
                "entity_type": "defect",
                "role": "reported",
                "features": [],
                "raw_expression": "un-sintered powder particles within fracture micro-voids",
            }
        ],
    )
    fact.data["material_state"] = "fracture surface"
    anchors = [
        _anchor("binder jetting powder", material="Inconel 625"),
        _anchor("binder jetting fracture surface", material="Inconel 625"),
        _anchor("Inconel 625", material="Inconel 625"),
    ]

    result = promote_axis_facts(anchors, [fact], source_text=evidence)

    assert len(result.accepted) == 1
    routed = result.accepted[0]
    assert isinstance(routed, StructureFact)
    assert routed.sample_id_raw == "binder jetting fracture surface"
    assert any(
        issue.code == "promotion_structure_source_state_owner_reassigned"
        for issue in result.issues
    )


def test_structure_source_state_ambiguity_is_quarantined_without_collective_grammar():
    evidence = "The as-built and aged conditions contained fine gamma-prime precipitates."
    fact = _structure(sample="Alloy A", evidence=evidence)
    anchors = [
        _anchor("Alloy A", material="alloy A"),
        _anchor("Alloy A [as-built]", material="alloy A", state="as-built"),
        _anchor("Alloy A [aged]", material="alloy A", state="aged"),
    ]

    result = promote_axis_facts(anchors, [fact], source_text=evidence)

    assert result.accepted == ()
    issue = next(
        issue
        for issue in result.issues
        if issue.code == "promotion_structure_source_state_ambiguous_quarantined"
    )
    assert set(issue.actual["matched_states"]) == {
        "Alloy A [as-built]",
        "Alloy A [aged]",
    }
    assert issue.actual["removed"] == fact.model_dump()


def test_structure_source_state_collective_assertion_is_not_broadcast_filtered():
    evidence = "Both as-built and aged conditions contained fine gamma-prime precipitates."
    fact = _structure(sample="Alloy A", evidence=evidence)
    anchors = [
        _anchor("Alloy A", material="alloy A"),
        _anchor("Alloy A [as-built]", material="alloy A", state="as-built"),
        _anchor("Alloy A [aged]", material="alloy A", state="aged"),
    ]

    result = promote_axis_facts(anchors, [fact], source_text=evidence)

    # The explicit shared assertion remains eligible for the existing shared
    # owner handling; this new gate must not erase a legitimate collective
    # statement merely because it names two states.
    assert len(result.accepted) == 1
    assert not any(
        issue.code == "promotion_structure_source_state_ambiguous_quarantined"
        for issue in result.issues
    )


def test_composition_material_state_routes_to_unique_existing_state_owner():
    evidence = "A1 fracture surface contained 47.86 ± 0.5 at.% Al."
    fact = _composition(sample="A1", evidence=evidence)
    fact.data["material_state"] = "fracture surface"
    anchors = [
        _anchor("A1", material="alloy A"),
        _anchor(
            "A1",
            material="alloy A",
            state="HIPed and tensile-fractured",
            evidence="A1 fracture surface",
        ),
    ]

    result = promote_axis_facts(anchors, [fact], source_text=evidence)

    assert len(result.accepted) == 1
    routed = result.accepted[0]
    assert isinstance(routed, CompositionFact)
    assert routed.sample_id_raw == "A1"
    assert routed.data["sample_id"] == "A1"
    assert routed.data["material_state"] == "HIPed and tensile-fractured"
    assert [issue.code for issue in result.issues].count(
        "promotion_composition_state_owner_reassigned"
    ) == 1


def test_composition_material_state_does_not_jump_when_two_states_share_a_cue():
    evidence = "A1 fracture surface contained 47.86 ± 0.5 at.% Al."
    fact = _composition(sample="A1", evidence=evidence)
    fact.data["material_state"] = "fracture surface"
    anchors = [
        _anchor("A1", material="alloy A"),
        _anchor("A1", material="alloy A", state="fracture surface"),
        _anchor(
            "A1",
            material="alloy A",
            state="HIPed and tensile-fractured",
        ),
    ]

    result = promote_axis_facts(anchors, [fact], source_text=evidence)

    assert result.accepted[0].sample_id_raw == "A1"
    assert not any(
        issue.code == "promotion_composition_state_owner_reassigned"
        for issue in result.issues
    )


def test_structure_material_state_route_requires_source_grounding():
    anchors = [_anchor("A1", state="aged")]
    evidence = "A1 contained fine gamma-prime precipitates."
    fact = _structure(sample="A1", evidence=evidence)
    fact.data["material_state"] = "aged"

    result = promote_axis_facts(anchors, [fact], source_text=evidence)

    assert len(result.accepted) == 1
    assert result.accepted[0].sample_id_raw == "A1"
    assert not any(
        issue.code == "promotion_structure_state_owner_reassigned"
        for issue in result.issues
    )


def test_structure_material_state_normalizes_to_existing_state_label():
    anchors = [
        _anchor(
            "A1",
            state="interrupted at 1% strain at 1030 °C and 230 MPa",
        )
    ]
    evidence = (
        "| A1 | 1% creep strain | 0.327 |\n"
        "Fine gamma-prime precipitates were observed in A1."
    )
    fact = _structure(
        sample="A1",
        evidence=evidence,
        entities=[
            {
                "name_raw": "gamma-prime precipitates",
                "entity_type": "precipitate",
                "role": "reported",
                "features": [],
                "raw_expression": "gamma-prime precipitates",
                "source_evidence": [
                    "Fine gamma-prime precipitates were observed in A1."
                ],
            }
        ],
    )
    fact.data["material_state"] = "1% creep strain"

    result = promote_axis_facts(anchors, [fact], source_text=evidence)

    assert len(result.accepted) == 1
    routed = result.accepted[0]
    assert isinstance(routed, StructureFact)
    assert routed.sample_id_raw == "A1"
    assert routed.data["material_state"] == (
        "interrupted at 1% strain at 1030 °C and 230 MPa"
    )
    issue = next(
        issue
        for issue in result.issues
        if issue.code == "promotion_structure_state_owner_reassigned"
    )
    assert issue.expected["state_normalized_to_existing_owner"] is True


def test_structure_state_does_not_jump_to_unrelated_global_owner():
    anchors = [
        _anchor("A1", state="aged"),
        _anchor("B1", state="fracture surface"),
    ]
    evidence = "The fracture surface showed fine gamma-prime precipitates."
    fact = _structure(sample="unresolved structure", evidence=evidence)
    fact.data["material_state"] = "fracture surface"

    result = promote_axis_facts(anchors, [fact], source_text=evidence)

    assert not any(
        issue.code == "promotion_structure_state_owner_reassigned"
        for issue in result.issues
    )
    assert all(
        issue.actual.get("after", {}).get("sample_id_raw")
        != "B1"
        for issue in result.issues
        if isinstance(issue.actual, dict)
    )


def test_explicit_shared_owner_grammar_is_recorded_without_combined_item():
    graph = build_owner_graph([_anchor("A1"), _anchor("A2")])
    sentence = "A1 and A2 both had a yield strength of 900 MPa."
    record = build_promotion_records(
        [_property(sample="A1", evidence=sentence, condition="")]
    )[0]

    resolution = resolve_record_owner(record, graph)

    assert len(resolution.owner_ids) == 1
    assert graph.display_label(resolution.owner_ids[0]) == "A1"
    assert {
        graph.display_label(owner_id)
        for owner_id in resolution.explicit_shared_owner_ids
    } == {"A1", "A2"}
    assert resolution.risk_codes == ()


def test_noncore_table_value_mismatch_is_quarantined_by_owner_column():
    source = "\n".join(
        [
            "| Density [g/cm^3] | #1 | #2 | Average |",
            "|---|---:|---:|---:|",
            "| As-sintered | 8.401 | 8.394 | 8.398 |",
            "| Std. | 0.013 | 0.024 | 0.011 |",
        ]
    )
    evidence = source.splitlines()
    facts = []
    for sample in ("#1", "#2"):
        fact = _property(
            sample=sample,
            name="Density",
            value="8.401 ± 0.013",
            unit="g/cm^3",
            condition="",
            evidence=evidence[0],
        )
        fact.source_evidence = evidence
        fact.data["source_evidence"] = evidence
        fact.data["data_source"] = "table"
        facts.append(fact)

    result = promote_axis_facts(
        [_anchor("#1"), _anchor("#2")], facts, source_text=source
    )

    assert [fact.sample_id_raw for fact in result.accepted] == ["#1"]
    assert [
        issue.code
        for issue in result.issues
        if issue.code == "promotion_table_owner_value_ambiguous_quarantined"
    ] == ["promotion_table_owner_value_ambiguous_quarantined"]


def test_numeric_structure_table_value_mismatch_is_quarantined_by_owner_column():
    source = "\n".join(
        [
            "| Grain size (µm) | A1 | A2 |",
            "|---|---:|---:|",
            "| Average | 55 | 70 |",
        ]
    )
    evidence = source.splitlines()
    facts = []
    for sample in ("A1", "A2"):
        fact = _structure(
            sample=sample,
            evidence="\n".join(evidence),
            entities=[],
            features=[
                {
                    "feature_name_raw": "grain size",
                    "value_kind": "scalar",
                    "value_raw": "55",
                    "unit_raw": "µm",
                    "source_evidence": evidence,
                }
            ],
        )
        fact.data["source_evidence"] = evidence
        fact.source_evidence = evidence
        facts.append(fact)

    result = promote_axis_facts(
        [_anchor("A1"), _anchor("A2")], facts, source_text=source
    )

    assert [fact.sample_id_raw for fact in result.accepted] == ["A1"]
    assert any(
        issue.code == "promotion_table_owner_value_ambiguous_quarantined"
        for issue in result.issues
    )


def test_structure_table_value_must_match_metric_row_not_only_owner_column():
    source = "\n".join(
        [
            "| Parameter | A1 | A2 |",
            "|---|---:|---:|",
            "| Area fraction (%) | 42.3 | 57.7 |",
            "| Average grain diameter (µm) | 7.34 | 42.3 |",
        ]
    )
    evidence = source.splitlines()
    fact = _structure(
        sample="A2",
        evidence="\n".join(evidence),
        entities=[],
        features=[
            {
                "feature_name_raw": "area fraction of O phase",
                "value_kind": "scalar",
                "value_raw": "42.3",
                "unit_raw": "%",
                "data_nature": "reported",
                "source_evidence": evidence,
            }
        ],
    )
    fact.data["source_evidence"] = evidence
    fact.source_evidence = evidence

    result = promote_axis_facts(
        [_anchor("A1"), _anchor("A2")], [fact], source_text=source
    )

    assert result.accepted == ()
    issue = next(
        issue
        for issue in result.issues
        if issue.code == "promotion_table_owner_value_ambiguous_quarantined"
    )
    assert issue.actual["reason"] == "structure_feature_value_row_label_mismatch"
    assert issue.actual["structure_feature_coordinate"]["value_rows"] == [1, 2]


def test_structure_table_grain_size_alias_matches_average_grain_diameter_row():
    source = "\n".join(
        [
            "| Parameter | A1 | A2 |",
            "|---|---:|---:|",
            "| Average grain diameter (µm) | 7.34 | 42.3 |",
        ]
    )
    evidence = source.splitlines()
    fact = _structure(
        sample="A2",
        evidence="\n".join(evidence),
        entities=[],
        features=[
            {
                "feature_name_raw": "grain size",
                "value_kind": "scalar",
                "value_raw": "42.3",
                "unit_raw": "µm",
                "data_nature": "reported",
                "source_evidence": evidence,
            }
        ],
    )
    fact.data["source_evidence"] = evidence
    fact.source_evidence = evidence

    result = promote_axis_facts(
        [_anchor("A1"), _anchor("A2")], [fact], source_text=source
    )

    assert result.accepted == (fact,)
    assert not any(
        issue.code == "promotion_table_owner_value_ambiguous_quarantined"
        for issue in result.issues
    )


def test_respectively_without_literal_owner_coordinate_is_quarantined_even_when_values_repeat():
    evidence = (
        "Both alloys were aged at 1030 °C for 0.5 h and 2 h, respectively."
    )
    parameter = {
        "parameter_name_raw": "duration",
        "value_raw": "0.5",
        "unit_raw": "h",
        "source_evidence": [evidence],
    }
    facts = [
        _processing(sample="T0", evidence=evidence, parameters=[parameter]),
        _processing(sample="T5", evidence=evidence, parameters=[parameter]),
    ]

    result = promote_axis_facts(
        [_anchor("T0"), _anchor("T5")], facts, source_text=evidence
    )

    assert result.accepted == ()
    assert sum(
        issue.code == "promotion_respectively_mapping_ambiguous_quarantined"
        for issue in result.issues
    ) == 2


def test_core_tensile_source_literal_owner_is_reassigned():
    evidence = "A1 had an ultimate tensile strength of 900 MPa."
    fact = _property(
        sample="A2",
        name="ultimate tensile strength",
        value="900",
        condition="",
        evidence=evidence,
    )

    result = promote_axis_facts(
        [_anchor("A1"), _anchor("A2")], [fact], source_text=evidence
    )

    assert len(result.accepted) == 1
    assert result.accepted[0].sample_id_raw == "A1"
    assert any(
        issue.code == "promotion_tensile_source_owner_reassigned"
        for issue in result.issues
    )


def test_comparator_owner_does_not_replace_declared_tensile_owner():
    evidence = (
        "Upon post-annealing at 600 °C for 8 h, σ0.2 and σu reach "
        "1723 ± 37 MPa and 2153 ± 24 MPa, approximately 24% higher "
        "than the values for the as-built samples, respectively."
    )
    fact = _property(
        sample="as-annealed",
        name="ultimate tensile strength (σu)",
        value="2153 ± 24",
        condition="RT",
        evidence=evidence,
    )

    result = promote_axis_facts(
        [
            _anchor("as-built", material="EHEA", state="as-built"),
            _anchor("as-annealed", material="EHEA", state="as-annealed"),
        ],
        [fact],
        source_text=evidence,
    )

    assert len(result.accepted) == 1
    assert result.accepted[0].sample_id_raw == "as-annealed"
    assert not any(
        issue.code == "promotion_tensile_source_owner_reassigned"
        for issue in result.issues
    )


def test_v204_complete_source_assertion_recovers_short_quote_owner_coordinates():
    source = (
        "L70 had YS: 404 ± 5 MPa and UTS: 556 ± 11 MPa, whereas L90 had "
        "YS: 394 ± 15 MPa and UTS: 456 ± 4 MPa."
    )
    facts = [
        _property(
            sample="L70",
            name="YS",
            value="404 ± 5",
            condition="",
            evidence="YS: 404 ± 5 MPa",
        ),
        _property(
            sample="L70",
            name="UTS",
            value="556 ± 11",
            condition="",
            evidence="UTS: 556 ± 11 MPa",
        ),
        _property(
            sample="L90",
            name="YS",
            value="394 ± 15",
            condition="",
            evidence="YS: 394 ± 15 MPa",
        ),
        _property(
            sample="L90",
            name="UTS",
            value="456 ± 4",
            condition="",
            evidence="UTS: 456 ± 4 MPa",
        ),
    ]

    result = promote_axis_facts(
        [_anchor("L70"), _anchor("L90")], facts, source_text=source
    )

    assert {
        (row.sample_id_raw, row.data["property_name_raw"], row.data["value_raw"])
        for row in result.accepted
    } == {
        ("L70", "YS", "404 ± 5"),
        ("L70", "UTS", "556 ± 11"),
        ("L90", "YS", "394 ± 15"),
        ("L90", "UTS", "456 ± 4"),
    }
    assert sum(
        issue.code == "tensile_assertion_coordinate_recovered"
        for issue in result.issues
    ) == 4
    assert not any(
        issue.code == "promotion_core_tensile_owner_ambiguous_quarantined"
        for issue in result.issues
    )
    assert all(
        str(row.data["property_id_candidate"]).startswith("tensile-assertion:")
        for row in result.accepted
    )


def test_v204_complete_source_assertion_reassigns_wrong_short_quote_owner():
    source = "A1 had a YS of 900 MPa, whereas A2 had a YS of 700 MPa."
    fact = _property(
        sample="A2",
        name="yield strength",
        value="900",
        condition="",
        evidence="YS of 900 MPa",
    )

    result = promote_axis_facts(
        [_anchor("A1"), _anchor("A2")], [fact], source_text=source
    )

    assert len(result.accepted) == 1
    assert result.accepted[0].sample_id_raw == "A1"
    issue = next(
        row
        for row in result.issues
        if row.code == "tensile_coordinate_owner_reassigned"
    )
    assert issue.actual["before"]["sample_id_raw"] == "A2"
    assert issue.actual["after"]["sample_id_raw"] == "A1"


def test_v204_ambiguous_complete_source_assertion_remains_quarantined():
    source = "A1 and A2 were tested. The reported yield strength was 900 MPa."
    fact = _property(
        sample="A1",
        name="yield strength",
        value="900",
        condition="",
        evidence="yield strength was 900 MPa",
    )

    result = promote_axis_facts(
        [_anchor("A1"), _anchor("A2")], [fact], source_text=source
    )

    assert result.accepted == ()
    assert any(
        issue.code == "tensile_assertion_coordinate_ambiguous"
        for issue in result.issues
    )
    assert any(
        issue.code == "promotion_core_tensile_owner_ambiguous_quarantined"
        for issue in result.issues
    )


def test_v204_source_assertion_switch_off_restores_v203_owner_quarantine(
    monkeypatch,
):
    monkeypatch.setenv(
        "KNOWMAT2_ALPHA25_TENSILE_ASSERTION_COORDINATES_V204", "0"
    )
    source = (
        "L70 had YS: 404 ± 5 MPa, whereas L90 had YS: 394 ± 15 MPa."
    )
    fact = _property(
        sample="L70",
        name="YS",
        value="404 ± 5",
        condition="",
        evidence="YS: 404 ± 5 MPa",
    )

    result = promote_axis_facts(
        [_anchor("L70"), _anchor("L90")], [fact], source_text=source
    )

    assert result.accepted == ()
    assert any(
        issue.code == "promotion_core_tensile_owner_ambiguous_quarantined"
        for issue in result.issues
    )


def test_v204_result_protocol_switch_off_does_not_publish_assertion_coordinate(
    monkeypatch,
):
    monkeypatch.setenv(
        "KNOWMAT2_ALPHA25_TENSILE_RESULT_PROTOCOL_BINDING_V204", "0"
    )
    source = (
        "L70 had YS: 404 ± 5 MPa, whereas L90 had YS: 394 ± 15 MPa."
    )
    fact = _property(
        sample="L70",
        name="YS",
        value="404 ± 5",
        condition="",
        evidence="YS: 404 ± 5 MPa",
    )

    result = promote_axis_facts(
        [_anchor("L70"), _anchor("L90")], [fact], source_text=source
    )

    assert len(result.accepted) == 1
    assert result.accepted[0].data["property_id_candidate"] == (
        fact.data["property_id_candidate"]
    )


def test_v204_direct_owner_assertion_publishes_protocol_coordinate():
    source = (
        "A1 had an ultimate tensile strength of 900 MPa.\n\n"
        "Rate controlled tensile tests at 5 mm/min were performed."
    )
    fact = _property(
        sample="A1",
        name="ultimate tensile strength",
        value="900",
        condition="",
        evidence="A1 had an ultimate tensile strength of 900 MPa.",
    )

    result = promote_axis_facts(
        [_anchor("A1"), _anchor("A2")], [fact], source_text=source
    )

    assert len(result.accepted) == 1
    assert str(result.accepted[0].data["property_id_candidate"]).startswith(
        "tensile-assertion:"
    )
    assert any(
        issue.code == "tensile_assertion_coordinate_recovered"
        for issue in result.issues
    )


def test_v204_source_assertion_binds_only_literal_result_temperature():
    source = (
        "Tensile properties at 800 °C of L70 (YS: 404 ± 5 MPa, Fig. "
        "7d) are better than L90 (YS: 394 ± 15 MPa)."
    )
    fact = _property(
        sample="Alloy",
        name="YS",
        value="394 ± 15",
        condition="",
        evidence="YS: 394 ± 15 MPa",
    )

    result = promote_axis_facts(
        [_anchor("Alloy"), _anchor("L70"), _anchor("L90")],
        [fact],
        source_text=source,
    )

    assert len(result.accepted) == 1
    assert result.accepted[0].sample_id_raw == "L90"
    assert result.accepted[0].data["test_condition_raw"] == "800 °c"
    assert any(
        issue.code == "tensile_result_protocol_bound"
        for issue in result.issues
    )


def test_v204_result_protocol_switch_off_keeps_recovered_value_unconditioned(
    monkeypatch,
):
    monkeypatch.setenv(
        "KNOWMAT2_ALPHA25_TENSILE_RESULT_PROTOCOL_BINDING_V204", "0"
    )
    source = (
        "Tensile properties at 800 °C of L70 (YS: 404 ± 5 MPa, Fig. "
        "7d) are better than L90 (YS: 394 ± 15 MPa)."
    )
    fact = _property(
        sample="Alloy",
        name="YS",
        value="394 ± 15",
        condition="",
        evidence="YS: 394 ± 15 MPa",
    )

    result = promote_axis_facts(
        [_anchor("Alloy"), _anchor("L70"), _anchor("L90")],
        [fact],
        source_text=source,
    )

    assert len(result.accepted) == 1
    assert result.accepted[0].sample_id_raw == "L90"
    assert not result.accepted[0].data.get("test_condition_raw")
    assert not any(
        issue.code == "tensile_result_protocol_bound"
        for issue in result.issues
    )


def test_v204_fanout_guard_switch_off_restores_v203_quarantine(monkeypatch):
    monkeypatch.setenv(
        "KNOWMAT2_ALPHA25_TENSILE_COORDINATE_FANOUT_GUARD_V204", "0"
    )
    source = (
        "L70 had YS: 404 ± 5 MPa, whereas L90 had YS: 394 ± 15 MPa."
    )
    facts = [
        _property(
            sample="L70",
            name="YS",
            value="404 ± 5",
            condition="",
            evidence="YS: 404 ± 5 MPa",
        ),
        _property(
            sample="L90",
            name="YS",
            value="394 ± 15",
            condition="",
            evidence="YS: 394 ± 15 MPa",
        ),
    ]

    result = promote_axis_facts(
        [_anchor("L70"), _anchor("L90")], facts, source_text=source
    )

    assert result.accepted == ()
    assert sum(
        issue.code == "promotion_source_block_property_fanout_quarantined"
        for issue in result.issues
    ) == 2


def test_v205_unique_material_owner_reassigns_process_only_tensile_owner():
    evidence = (
        "The LPBF-fabricated Inconel 625 tensile specimen had a yield strength "
        "of 900 MPa."
    )
    fact = _property(
        sample="LPBF",
        name="yield strength",
        value="900",
        unit="MPa",
        condition="",
        evidence=evidence,
    )
    anchors = [
        _anchor("LPBF", material="Inconel 625"),
        _anchor("Inconel 625 tensile specimen", material="Inconel 625"),
    ]

    result = promote_axis_facts(anchors, [fact], source_text=evidence)

    assert len(result.accepted) == 1
    assert result.accepted[0].sample_id_raw == "Inconel 625 tensile specimen"
    issue = next(
        row for row in result.issues if row.code == "tensile_process_owner_reassigned"
    )
    assert issue.actual["before"] == fact.model_dump()
    assert issue.actual["after"] == result.accepted[0].model_dump()
    assert issue.actual["selected_owner"] == "Inconel 625 tensile specimen"
    assert issue.actual["decision_key"].startswith("tensile-assertion-decision:")


def test_v205_explicit_orientation_routes_coarse_tensile_owner():
    evidence = "LPBF specimens in the Z orientation had a UTS of 840 ± 20 MPa."
    fact = _property(
        sample="LPBF",
        name="ultimate tensile strength",
        value="840 ± 20",
        condition="Z orientation",
        evidence=evidence,
    )

    result = promote_axis_facts(
        [_anchor("LPBF"), _anchor("LPBF / X"), _anchor("LPBF / Z")],
        [fact],
        source_text=evidence,
    )

    assert len(result.accepted) == 1
    assert result.accepted[0].sample_id_raw == "LPBF / Z"
    assert str(result.accepted[0].data["property_id_candidate"]).startswith(
        "tensile-process-owner-v205:"
    )
    issue = next(
        row for row in result.issues if row.code == "tensile_process_owner_reassigned"
    )
    assert issue.actual["coordinate"] == {
        "kind": "explicit_orientation_owner",
        "orientation": "Z",
        "owner_base": "lpbf",
    }
    assert issue.actual["before"] == fact.model_dump()
    assert issue.actual["after"] == result.accepted[0].model_dump()


def test_v205_explicit_orientation_routes_coarse_owner_with_state_anchors():
    evidence = "LPBF specimens in the Z orientation had a UTS of 840 ± 20 MPa."
    fact = _property(
        sample="LPBF",
        name="UTS",
        value="840 ± 20",
        condition="Z orientation",
        evidence=evidence,
    )

    result = promote_axis_facts(
        [
            _anchor("LPBF", state="X orientation"),
            _anchor("LPBF", state="Z orientation"),
            _anchor("LPBF / X"),
            _anchor("LPBF / Z"),
        ],
        [fact],
        source_text=evidence,
    )

    assert len(result.accepted) == 1
    assert result.accepted[0].sample_id_raw == "LPBF / Z"
    assert any(
        row.code == "tensile_process_owner_reassigned" for row in result.issues
    )


def test_v205_unique_source_sentence_restores_omitted_orientation_prefix():
    source = (
        "Based on specimens fabricated in the X orientation, LPBF samples had "
        "the highest ultimate tensile strength (0.91 ± 0.03 GPa) with binder "
        "jetting displaying the lowest UTS (0.71 ± 0.02 GPa)."
    )
    fact = _property(
        sample="LPBF",
        name="ultimate tensile strength",
        value="0.91 ± 0.03",
        unit="GPa",
        condition="",
        evidence=(
            "LPBF samples had the highest ultimate tensile strength "
            "(0.91 ± 0.03 GPa)"
        ),
    )

    result = promote_axis_facts(
        [_anchor("LPBF"), _anchor("LPBF / X"), _anchor("LPBF / Z")],
        [fact],
        source_text=source,
    )

    assert len(result.accepted) == 1
    assert result.accepted[0].sample_id_raw == "LPBF / X"
    issue = next(
        row for row in result.issues if row.code == "tensile_process_owner_reassigned"
    )
    assert issue.actual["coordinate"]["orientation_source_kind"] == (
        "bounded_source_sentence"
    )
    assert issue.actual["coordinate"]["orientation"] == "X"
    assert issue.actual["coordinate"]["orientation_source_sentence"] == (
        source.casefold()
    )


def test_v205_source_sentence_orientation_pairs_enumerated_owner_values():
    source = (
        "Specimens produced in the X orientation achieved corresponding values "
        "of 62% ± 1.99% for LPBF, 59% ± 2.14% for binder jetting, and "
        "44% ± 4.95% for EPBF."
    )
    facts = [
        _property(
            sample="LPBF",
            name="elongation",
            value="62% ± 1.99%",
            unit="%",
            condition="",
            evidence="62% ± 1.99% for LPBF",
        ),
        _property(
            sample="binder jetting powder",
            name="elongation",
            value="59% ± 2.14%",
            unit="%",
            condition="",
            evidence="59% ± 2.14% for binder jetting",
        ),
        _property(
            sample="EPBF",
            name="elongation",
            value="44% ± 4.95%",
            unit="%",
            condition="",
            evidence="44% ± 4.95% for EPBF",
        ),
    ]
    anchors = [
        _anchor("LPBF"),
        _anchor("LPBF / X"),
        _anchor("LPBF / Z"),
        _anchor("binder jetting powder"),
        _anchor("Binder Jetting / X"),
        _anchor("Binder Jetting / Z"),
        _anchor("EPBF"),
        _anchor("EPBF / X"),
        _anchor("EPBF / Z"),
    ]

    result = promote_axis_facts(anchors, facts, source_text=source)

    assert {row.sample_id_raw for row in result.accepted} == {
        "LPBF / X",
        "Binder Jetting / X",
        "EPBF / X",
    }
    assert sum(
        row.code == "tensile_process_owner_reassigned" for row in result.issues
    ) == 3


def test_v205_source_sentence_orientation_requires_owner_value_local_evidence():
    source = (
        "Specimens produced in the X orientation achieved 62% ± 1.99% for "
        "LPBF and 44% ± 4.95% for EPBF."
    )
    fact = _property(
        sample="LPBF",
        name="elongation",
        value="62% ± 1.99%",
        unit="%",
        condition="",
        evidence="The elongation was 62% ± 1.99%.",
    )

    result = promote_axis_facts(
        [_anchor("LPBF"), _anchor("LPBF / X"), _anchor("LPBF / Z")],
        [fact],
        source_text=source,
    )

    assert result.accepted == ()
    assert not any(
        row.code.startswith("tensile_process_owner_") for row in result.issues
    )


def test_v205_source_sentence_orientation_fails_closed_on_repeated_quote():
    evidence = "LPBF reached a UTS of 0.91 ± 0.03 GPa"
    source = (
        "For specimens in the X orientation, "
        f"{evidence}. For specimens in the Z orientation, {evidence}."
    )
    fact = _property(
        sample="LPBF",
        name="UTS",
        value="0.91 ± 0.03",
        unit="GPa",
        condition="",
        evidence=evidence,
    )

    result = promote_axis_facts(
        [_anchor("LPBF"), _anchor("LPBF / X"), _anchor("LPBF / Z")],
        [fact],
        source_text=source,
    )

    assert result.accepted == (fact,)
    assert not any(
        row.code.startswith("tensile_process_owner_") for row in result.issues
    )


def test_v205_unique_source_sentence_restores_omitted_tensile_temperature():
    evidence = (
        "The UTS of the PBF-EB samples was slightly lower at 803 MPa, but "
        "the EL increased to 3 %"
    )
    source = f"{evidence}, when tested at 650 °C."
    fact = _property(
        sample="PBF-EB",
        name="ultimate tensile strength",
        value="803",
        unit="MPa",
        condition="",
        evidence=evidence,
    )

    result = promote_axis_facts(
        [_anchor("PBF-EB")], [fact], source_text=source
    )

    assert len(result.accepted) == 1
    assert result.accepted[0].data["test_condition_raw"] == "650 °c"
    issue = next(
        row
        for row in result.issues
        if row.code == "tensile_source_sentence_temperature_bound"
    )
    assert issue.severity == "info"
    assert issue.actual["before"] == fact.model_dump()
    assert issue.actual["after"] == result.accepted[0].model_dump()
    assert issue.actual["temperature"] == "650 °c"
    assert issue.actual["decision_key"].startswith("property-condition-v205:")


def test_v205_source_sentence_temperature_fails_closed_on_multiple_temperatures():
    evidence = "PBF-EB samples reached a UTS of 803 MPa"
    source = (
        f"At room temperature and 650 °C, {evidence} under two protocols."
    )
    fact = _property(
        sample="PBF-EB",
        name="UTS",
        value="803",
        condition="",
        evidence=evidence,
    )

    result = promote_axis_facts(
        [_anchor("PBF-EB")], [fact], source_text=source
    )

    assert result.accepted == (fact,)
    assert not any(
        row.code == "tensile_source_sentence_temperature_bound"
        for row in result.issues
    )


def test_v205_source_sentence_temperature_fails_closed_on_repeated_quote():
    evidence = "PBF-EB samples reached a UTS of 803 MPa"
    source = f"{evidence} at 650 °C. {evidence} at 700 °C."
    fact = _property(
        sample="PBF-EB",
        name="UTS",
        value="803",
        condition="",
        evidence=evidence,
    )

    result = promote_axis_facts(
        [_anchor("PBF-EB")], [fact], source_text=source
    )

    assert result.accepted == (fact,)
    assert not any(
        row.code == "tensile_source_sentence_temperature_bound"
        for row in result.issues
    )


def test_v205_source_sentence_temperature_switch_off_restores_prior_behavior(
    monkeypatch,
):
    monkeypatch.setenv(
        "KNOWMAT2_ALPHA25_PROPERTY_PROVENANCE_CONDITION_SEPARATION_V205", "0"
    )
    evidence = "PBF-EB samples reached a UTS of 803 MPa"
    source = f"{evidence} at 650 °C."
    fact = _property(
        sample="PBF-EB",
        name="UTS",
        value="803",
        condition="",
        evidence=evidence,
    )

    result = promote_axis_facts(
        [_anchor("PBF-EB")], [fact], source_text=source
    )

    assert result.accepted == (fact,)
    assert not any(
        row.code == "tensile_source_sentence_temperature_bound"
        for row in result.issues
    )


def test_v205_explicit_orientation_strips_only_generic_owner_role_suffix():
    evidence = (
        "Binder jetting powder tested in the Z orientation had a yield "
        "strength of 390 ± 20 MPa."
    )
    fact = _property(
        sample="binder jetting powder",
        value="390 ± 20",
        condition="Z orientation",
        evidence=evidence,
    )

    result = promote_axis_facts(
        [
            _anchor("binder jetting powder"),
            _anchor("Binder Jetting / X"),
            _anchor("Binder Jetting / Z"),
        ],
        [fact],
        source_text=evidence,
    )

    assert len(result.accepted) == 1
    assert result.accepted[0].sample_id_raw == "Binder Jetting / Z"


def test_v205_orientation_owner_fails_closed_when_coordinate_is_ambiguous():
    evidence = "LPBF specimens in the Z orientation had a UTS of 840 MPa."
    fact = _property(
        sample="LPBF",
        name="UTS",
        value="840",
        condition="Z orientation",
        evidence=evidence,
    )

    result = promote_axis_facts(
        [_anchor("LPBF"), _anchor("LPBF / Z"), _anchor("LPBF Z direction")],
        [fact],
        source_text=evidence,
    )

    assert result.accepted == (fact,)
    issue = next(
        row for row in result.issues if row.code == "tensile_process_owner_ambiguous"
    )
    assert issue.actual["reason"] == "ambiguous_explicit_orientation_owner"


def test_v205_orientation_owner_requires_explicit_coordinate():
    evidence = "LPBF specimens had a UTS of 840 MPa."
    fact = _property(
        sample="LPBF", name="UTS", value="840", condition="", evidence=evidence
    )

    result = promote_axis_facts(
        [_anchor("LPBF"), _anchor("LPBF / X"), _anchor("LPBF / Z")],
        [fact],
        source_text=evidence,
    )

    assert len(result.accepted) == 1
    assert result.accepted[0].sample_id_raw == "LPBF"
    assert not any(
        row.code.startswith("tensile_process_owner_") for row in result.issues
    )


def test_v205_orientation_owner_does_not_reroute_table_coordinate():
    evidence = "| Technology | Orientation | UTS (MPa) |\n| LPBF | Z | 842 ± 29 |"
    fact = _property(
        sample="LPBF",
        name="UTS",
        value="842 ± 29",
        condition="Z orientation",
        evidence=evidence,
    )

    result = promote_axis_facts(
        [_anchor("LPBF"), _anchor("LPBF / Z")], [fact], source_text=evidence
    )

    assert len(result.accepted) == 1
    assert result.accepted[0].sample_id_raw == "LPBF"
    assert not any(
        row.code.startswith("tensile_process_owner_") for row in result.issues
    )


def test_v205_process_label_is_preserved_when_source_uses_it_as_sample_designation():
    evidence = "LPBF samples had a yield strength of 900 MPa."
    fact = _property(
        sample="LPBF",
        value="900",
        condition="",
        evidence=evidence,
    )

    result = promote_axis_facts(
        [_anchor("LPBF"), _anchor("Inconel 625 tensile specimen")],
        [fact],
        source_text=evidence,
    )

    assert result.accepted == (fact,)
    assert not any(
        row.code.startswith("tensile_process_owner_") for row in result.issues
    )


def test_v205_process_owner_remains_unchanged_when_material_coordinate_is_ambiguous():
    evidence = (
        "The LPBF-fabricated A1 and A2 tensile specimens had a yield strength "
        "of 900 MPa."
    )
    fact = _property(
        sample="LPBF",
        value="900",
        condition="",
        evidence=evidence,
    )

    result = promote_axis_facts(
        [_anchor("LPBF"), _anchor("A1"), _anchor("A2")],
        [fact],
        source_text=evidence,
    )

    assert all(row.sample_id_raw == "LPBF" for row in result.accepted)
    issue = next(
        row for row in result.issues if row.code == "tensile_process_owner_ambiguous"
    )
    assert issue.actual["before"] == fact.model_dump()
    assert issue.actual["reason"] in {
        "ambiguous_material_coordinate",
        "no_unique_material_coordinate",
    }


def test_v205_unique_material_owner_does_not_touch_noncore_property():
    evidence = "The LPBF-fabricated A1 specimen had a hardness of 420 HV."
    fact = _property(
        sample="LPBF",
        name="hardness",
        value="420",
        unit="HV",
        condition="",
        evidence=evidence,
    )

    result = promote_axis_facts(
        [_anchor("LPBF"), _anchor("A1")], [fact], source_text=evidence
    )

    assert result.accepted == (fact,)
    assert not any(
        row.code.startswith("tensile_process_owner_") for row in result.issues
    )


def test_v205_unique_material_owner_switch_off_restores_v204_process_owner(
    monkeypatch,
):
    monkeypatch.setenv(
        "KNOWMAT2_ALPHA25_UNIQUE_MATERIAL_OWNER_CONVERGENCE_V205", "0"
    )
    evidence = (
        "The LPBF-fabricated Inconel 625 tensile specimen had a yield strength "
        "of 900 MPa."
    )
    fact = _property(
        sample="LPBF",
        value="900",
        condition="",
        evidence=evidence,
    )

    result = promote_axis_facts(
        [
            _anchor("LPBF", material="Inconel 625"),
            _anchor("Inconel 625 tensile specimen", material="Inconel 625"),
        ],
        [fact],
        source_text=evidence,
    )

    assert all(row.sample_id_raw == "LPBF" for row in result.accepted)
    assert not any(
        row.code.startswith("tensile_process_owner_") for row in result.issues
    )


def test_v204_parenthesized_owner_pairs_prevent_cross_owner_tensile_swap():
    source = (
        "Yield and ultimate tensile strengths increased from 486.0 and "
        "781.2 MPa (CoCrNi) to 887.2 and 1165.2 MPa "
        "(CoCrNi(Al0.6TiFe)0.5)."
    )
    facts = [
        _property(
            sample="CoCrNi",
            name="ultimate tensile strength",
            value="781.2",
            condition="",
            evidence="781.2 MPa (CoCrNi)",
        ),
        _property(
            sample="CoCrNi(Al0.6TiFe)0.5",
            name="ultimate tensile strength",
            value="1165.2",
            condition="",
            evidence="1165.2 MPa (CoCrNi(Al0.6TiFe)0.5)",
        ),
    ]

    result = promote_axis_facts(
        [_anchor("CoCrNi"), _anchor("CoCrNi(Al0.6TiFe)0.5")],
        facts,
        source_text=source,
    )

    assert {
        (row.sample_id_raw, row.data["value_raw"]) for row in result.accepted
    } == {
        ("CoCrNi", "781.2"),
        ("CoCrNi(Al0.6TiFe)0.5", "1165.2"),
    }
    assert not any(
        issue.code == "promotion_source_block_property_fanout_quarantined"
        for issue in result.issues
    )


def test_processed_tensile_result_is_not_promoted_to_powder_owner():
    evidence = "The sintered sample had an ultimate tensile strength of 612 MPa."
    fact = _property(
        sample="alloy 625 powder",
        name="ultimate tensile strength",
        value="612",
        condition="",
        evidence=evidence,
    )
    anchors = [
        _anchor(
            "alloy 625 powder",
            material="alloy 625",
            state="as-received powder",
        ),
        _anchor(
            "sintered sample",
            material="alloy 625",
            state="sintered",
        ),
    ]

    result = promote_axis_facts(anchors, [fact], source_text=evidence)

    assert len(result.accepted) == 1
    assert result.accepted[0].sample_id_raw == "sintered sample"
    assert any(
        issue.code == "promotion_tensile_source_owner_reassigned"
        for issue in result.issues
    )


def test_tensile_source_unit_conflict_is_quarantined_without_relabeling():
    evidence = "The reference reported a UTS of 0.33 GPa for the EPBF specimen."
    fact = _property(
        sample="EPBF specimen",
        name="ultimate tensile strength",
        value="0.33",
        unit="MPa",
        condition="",
        evidence=evidence,
    )

    result = promote_axis_facts(
        [_anchor("EPBF specimen")], [fact], source_text=evidence
    )

    assert result.accepted == ()
    issue = next(
        issue
        for issue in result.issues
        if issue.code == "promotion_tensile_source_unit_conflict_quarantined"
    )
    assert issue.actual["declared_unit"] == "mpa"
    assert issue.actual["source_units"] == ["gpa"]
    assert issue.actual["removed"]["data"]["value_raw"] == "0.33"


def test_tensile_embedded_source_unit_matching_unit_raw_is_preserved():
    evidence = "The reference reported a UTS of 0.33 GPa for the EPBF specimen."
    fact = _property(
        sample="EPBF specimen",
        name="ultimate tensile strength",
        value="0.33 GPa",
        unit="GPa",
        condition="",
        evidence=evidence,
    )

    result = promote_axis_facts(
        [_anchor("EPBF specimen")], [fact], source_text=evidence
    )

    # A current experimental owner cannot be validated by a citation cue plus
    # an embedded value unit.  The complete candidate remains in the audit.
    assert result.accepted == ()
    assert any(
        issue.code == "promotion_external_current_tensile_projection_quarantined"
        for issue in result.issues
    )


def test_unresolved_composite_tensile_state_bundle_is_quarantined_as_a_group():
    evidence = (
        "The average yield strength, ultimate tensile strength, and elongation "
        "after HIP2 + HT2 were 1000 MPa, 1105 MPa, and 3.1%, respectively."
    )
    facts = [
        _property(
            sample="MAR M247",
            name="yield strength",
            value="1000",
            unit="MPa",
            condition="room temperature",
            evidence=evidence,
        ),
        _property(
            sample="MAR M247",
            name="ultimate tensile strength",
            value="1105",
            unit="MPa",
            condition="room temperature",
            evidence=evidence,
        ),
        _property(
            sample="MAR M247",
            name="elongation",
            value="3.1",
            unit="%",
            condition="room temperature",
            evidence=evidence,
        ),
    ]
    for fact in facts:
        fact.data["material_state"] = "HIP2 + HT2"

    result = promote_axis_facts(
        [
            _anchor("MAR M247"),
            _anchor("HT2"),
            _anchor("MAR M247 [as-sintered]", state="as-sintered"),
            _anchor("MAR M247 [HIP conditions]", state="HIP conditions"),
        ],
        facts,
        source_text=evidence,
    )

    assert result.accepted == ()
    bundle_issues = [
        issue
        for issue in result.issues
        if issue.code == "promotion_tensile_state_bundle_ambiguous_quarantined"
    ]
    assert len(bundle_issues) == 3
    assert all(issue.actual["state_coordinate"] == "HIP2 + HT2" for issue in bundle_issues)


def test_reference_and_target_with_same_material_name_remain_distinct():
    graph = build_owner_graph(
        [
            _anchor("A1", material="Alloy A", role="Target"),
            _anchor("A1 literature", material="Alloy A", role="Reference"),
        ]
    )
    record = build_promotion_records(
        [_property(sample="A1", evidence="A1 had a yield strength of 900 MPa.")]
    )[0]

    resolution = resolve_record_owner(record, graph)

    assert len(resolution.owner_ids) == 1
    assert graph.node(resolution.owner_ids[0]).role == "Target"


def test_same_sample_state_role_merges_material_descriptors_as_aliases():
    graph = build_owner_graph(
        [
            _anchor("A1", material="Alloy A"),
            _anchor("A1", material="as-deposited Alloy A specimen"),
        ]
    )
    record = build_promotion_records(
        [_property(sample="A1", evidence="A1 had a yield strength of 900 MPa.")]
    )[0]

    resolution = resolve_record_owner(record, graph)

    assert len(graph.nodes) == 1
    assert len(resolution.owner_ids) == 1
    assert set(graph.node(resolution.owner_ids[0]).aliases) == {
        "A1",
        "Alloy A",
        "as-deposited Alloy A specimen",
    }
    assert resolution.risk_codes == ()


def test_structure_gate_quarantines_ungrounded_entity_and_feature_payloads():
    evidence = "A1 contained fine gamma-prime precipitates."
    fact = _structure(
        evidence=evidence,
        entities=[
            {
                "name_raw": "gamma-prime precipitates",
                "entity_type": "precipitate",
                "features": [],
                "raw_expression": "gamma-prime precipitates",
            },
            {
                "name_raw": "beta phase",
                "entity_type": "phase",
                "features": [],
                "raw_expression": "beta phase",
            },
        ],
        features=[
            {
                "feature_name_raw": "size",
                "value_kind": "text",
                "value_raw": "fine",
                "data_nature": "reported",
            },
            {
                "feature_name_raw": "volume fraction",
                "value_kind": "scalar",
                "value_raw": "42%",
                "unit_raw": "%",
                "data_nature": "reported",
            },
        ],
    )

    result = promote_axis_facts([_anchor("A1")], [fact], source_text=evidence)

    assert len(result.accepted) == 1
    cleaned = result.accepted[0]
    assert [row["name_raw"] for row in cleaned.data["entities"]] == [
        "gamma-prime precipitates"
    ]
    assert cleaned.data["features"] == []
    assert {issue.code for issue in result.issues} == {
        "promotion_structure_entity_unsupported",
        "promotion_structure_feature_unsupported",
        "promotion_structure_qualitative_projection_quarantined",
    }
    assert all("removed" in issue.actual for issue in result.issues)


def test_structure_entity_keeps_numeric_and_negated_features_only():
    evidence = "A1 had 42% gamma-prime; no cracks were observed."
    fact = _structure(
        evidence=evidence,
        entities=[
            {
                "name_raw": "gamma-prime",
                "entity_type": "precipitate",
                "features": [
                    {
                        "feature_name_raw": "volume fraction",
                        "value_kind": "scalar",
                        "value_raw": "42%",
                        "unit_raw": "%",
                        "data_nature": "reported",
                    },
                    {
                        "feature_name_raw": "description",
                        "value_kind": "text",
                        "value_raw": "gamma-prime",
                        "data_nature": "reported",
                    },
                    {
                        "feature_name_raw": "crack presence",
                        "value_kind": "categorical",
                        "value_raw": "no cracks were observed",
                        "data_nature": "reported",
                    },
                ],
                "raw_expression": "gamma-prime",
            }
        ],
        features=[],
    )

    result = promote_axis_facts([_anchor("A1")], [fact], source_text=evidence)

    assert len(result.accepted) == 1
    features = result.accepted[0].data["entities"][0]["features"]
    assert [row["feature_name_raw"] for row in features] == [
        "volume fraction",
        "crack presence",
    ]
    assert [issue.code for issue in result.issues] == [
        "promotion_structure_qualitative_projection_quarantined"
    ]


def test_negated_structure_entity_shadow_is_quarantined_but_negative_feature_survives():
    evidence = "No cracks were observed in A1 after heat treatment."
    fact = _structure(
        evidence=evidence,
        entities=[
            {
                "name_raw": "cracks",
                "entity_type": "defect",
                "role": "reported",
                "features": [],
                "raw_expression": evidence,
                "source_evidence": [evidence],
            }
        ],
        features=[
            {
                "feature_name_raw": "crack presence",
                "value_kind": "categorical",
                "value_raw": "No cracks were observed",
                "data_nature": "reported",
                "source_evidence": [evidence],
            }
        ],
    )

    result = promote_axis_facts([_anchor("A1")], [fact], source_text=evidence)

    assert len(result.accepted) == 1
    assert result.accepted[0].data["entities"] == []
    assert result.accepted[0].data["features"] == fact.data["features"]
    assert [issue.code for issue in result.issues] == [
        "promotion_structure_negated_entity_quarantined"
    ]
    issue = result.issues[0]
    assert issue.actual["removed"] == fact.data["entities"][0]
    assert issue.actual["survivor_after"]["data"]["features"] == fact.data["features"]
    assert issue.actual["reason"] == "negated_entity_was_not_positive_presence"


def test_absent_table_entity_is_quarantined_without_removing_positive_sibling():
    evidence = "| Alloy | Boride | Carbide |\n| A1 | Yes | No |"
    fact = _structure(
        evidence=evidence,
        entities=[
            {
                "name_raw": "Boride",
                "entity_type": "phase",
                "role": "reported",
                "features": [],
                "raw_expression": "Yes",
                "source_evidence": evidence.splitlines(),
            },
            {
                "name_raw": "Carbide",
                "entity_type": "phase",
                "role": "absent",
                "features": [],
                "raw_expression": "Carbide",
                "source_evidence": evidence.splitlines(),
            },
        ],
        features=[],
    )

    result = promote_axis_facts([_anchor("A1")], [fact], source_text=evidence)

    assert len(result.accepted) == 1
    assert result.accepted[0].data["entities"] == []
    assert [
        (row["feature_name_raw"], row["value_raw"])
        for row in result.accepted[0].data["features"]
    ] == [("Boride presence", "Yes")]
    assert [issue.code for issue in result.issues] == [
        "promotion_structure_table_binary_entity_normalized",
        "promotion_structure_negated_entity_quarantined",
    ]
    assert result.issues[1].actual["removed"] == fact.data["entities"][1]


def test_negated_entity_only_observation_is_fully_audited_when_quarantined():
    evidence = "No cell boundaries are observed in the microstructure of A1."
    fact = _structure(
        evidence=evidence,
        entities=[
            {
                "name_raw": "cell boundaries",
                "entity_type": "feature",
                "role": "reported",
                "features": [],
                "raw_expression": evidence,
                "source_evidence": [evidence],
            }
        ],
        features=[],
    )

    result = promote_axis_facts([_anchor("A1")], [fact], source_text=evidence)

    assert result.accepted == ()
    assert [issue.code for issue in result.issues] == [
        "promotion_structure_negated_entity_quarantined",
        "promotion_structure_observation_quarantined",
    ]
    assert result.issues[0].actual["removed"] == fact.data["entities"][0]
    assert result.issues[1].actual["removed"] == fact.model_dump()


def test_generic_nonatomic_structure_entity_requires_atomic_payload():
    evidence = "A1 showed a matrix description with a width of 2 μm."
    unsupported = _structure(
        evidence=evidence,
        entities=[
            {
                "name_raw": "matrix description",
                "entity_type": "other",
                "features": [],
                "raw_expression": "matrix description",
            }
        ],
        features=[],
    )
    supported = _structure(
        evidence=evidence,
        entities=[
            {
                "name_raw": "matrix description",
                "entity_type": "other",
                "features": [
                    {
                        "feature_name_raw": "width",
                        "value_kind": "scalar",
                        "value_raw": "2",
                        "unit_raw": "μm",
                        "data_nature": "reported",
                    }
                ],
                "raw_expression": "matrix description",
            }
        ],
        features=[],
    )

    rejected = promote_axis_facts(
        [_anchor("A1")], [unsupported], source_text=evidence
    )
    accepted = promote_axis_facts(
        [_anchor("A1")], [supported], source_text=evidence
    )

    assert rejected.accepted == ()
    assert {issue.code for issue in rejected.issues} == {
        "promotion_structure_nonatomic_entity_quarantined",
        "promotion_structure_observation_quarantined",
    }
    assert accepted.accepted == (supported,)


def test_direct_qualitative_structure_feature_can_be_retained_when_opted_in(monkeypatch):
    monkeypatch.setenv("KNOWMAT2_ALPHA25_STRUCTURE_QUALITATIVE_DIRECT_V206", "1")
    evidence = "A1 contained a bimodal distribution of columnar and equiaxed grains."
    fact = _structure(
        evidence=evidence,
        entities=[
            {
                "name_raw": "grains",
                "entity_type": "grain",
                "features": [
                    {
                        "feature_name_raw": "morphology",
                        "value_kind": "categorical",
                        "value_raw": "columnar and equiaxed",
                        "data_nature": "reported",
                    }
                ],
                "raw_expression": "columnar and equiaxed grains",
            }
        ],
    )

    result = promote_axis_facts([_anchor("A1")], [fact], source_text=evidence)

    assert len(result.accepted) == 1
    assert result.accepted[0].data["entities"][0]["features"]
    assert not any(
        issue.code == "promotion_structure_qualitative_projection_quarantined"
        for issue in result.issues
    )


def test_direct_qualitative_feature_keeps_nonatomic_entity_when_opted_in(monkeypatch):
    """A direct qualitative payload must not be discarded by the parent gate."""

    monkeypatch.setenv("KNOWMAT2_ALPHA25_STRUCTURE_QUALITATIVE_DIRECT_V206", "1")
    evidence = "A1 microstructure consists of a lamellar morphology."
    fact = _structure(
        evidence=evidence,
        entities=[
            {
                "name_raw": "microstructure",
                "entity_type": "morphology",
                "features": [
                    {
                        "feature_name_raw": "morphology",
                        "value_kind": "categorical",
                        "value_raw": "lamellar",
                        "data_nature": "reported",
                    }
                ],
                "raw_expression": "lamellar morphology",
            }
        ],
    )

    result = promote_axis_facts([_anchor("A1")], [fact], source_text=evidence)

    assert len(result.accepted) == 1
    assert result.accepted[0].data["entities"][0]["features"]
    assert not any(
        issue.code == "promotion_structure_nonatomic_entity_quarantined"
        for issue in result.issues
    )


def test_direct_qualitative_structure_comparison_stays_quarantined(monkeypatch):
    monkeypatch.setenv("KNOWMAT2_ALPHA25_STRUCTURE_QUALITATIVE_DIRECT_V206", "1")
    evidence = "A1 had finer grains than A2."
    fact = _structure(
        sample="A1",
        evidence=evidence,
        entities=[
            {
                "name_raw": "grains",
                "entity_type": "grain",
                "features": [
                    {
                        "feature_name_raw": "grain size",
                        "value_kind": "categorical",
                        "value_raw": "finer than A2",
                        "data_nature": "reported",
                    }
                ],
                "raw_expression": "grains",
            }
        ],
    )

    result = promote_axis_facts(
        [_anchor("A1"), _anchor("A2")], [fact], source_text=evidence
    )

    assert len(result.accepted) == 1
    assert result.accepted[0].data["entities"][0]["features"] == []
    assert any(
        issue.code == "promotion_structure_feature_unsupported"
        for issue in result.issues
    )


def test_cross_chunk_source_span_duplicate_is_merged():
    evidence = "A1 contained fine gamma-prime precipitates."
    clipped = "contained fine gamma-prime precipitates."
    first = _structure(evidence=evidence)
    second = _structure(evidence=clipped)
    second = second.model_copy(
        deep=True,
        update={"evidence_unit_id": "prose-L000002-L000002-structure"},
    )

    result = deduplicate_cross_chunk_source_spans(
        [first, second], source_text=evidence
    )

    assert len(result.accepted) == 1
    assert any(
        issue.code == "promotion_cross_chunk_duplicate_merged"
        for issue in result.issues
    )


def test_unique_source_block_recovers_characterization_result_alias(monkeypatch):
    monkeypatch.setenv(
        "KNOWMAT2_ALPHA25_CHARACTERIZATION_SOURCE_BLOCK_RECOVERY_V206", "1"
    )
    method_evidence = "A1 was characterized by SEM using a Zeiss microscope."
    result_evidence = "SEM images of A1 reveal a bimodal grain structure."
    fact = _characterization(
        sample="A1",
        method="SEM",
        method_class="SEM",
        evidence=result_evidence,
    )

    result = promote_axis_facts(
        [_anchor("A1")],
        [fact],
        source_text=f"{method_evidence}\n\n{result_evidence}",
    )

    assert len(result.accepted) == 1
    assert method_evidence.casefold() in {
        row.casefold() for row in result.accepted[0].source_evidence
    }
    assert any(
        issue.code == "promotion_characterization_source_block_method_recovered"
        for issue in result.issues
    )


def test_missing_structure_entity_type_is_not_promoted_as_implicit_other():
    evidence = "A1 showed an untyped matrix description."
    fact = _structure(
        evidence=evidence,
        entities=[
            {
                "name_raw": "untyped matrix description",
                "features": [],
                "raw_expression": "untyped matrix description",
            }
        ],
        features=[],
    )

    result = promote_axis_facts([_anchor("A1")], [fact], source_text=evidence)

    assert result.accepted == ()
    assert {issue.code for issue in result.issues} == {
        "promotion_structure_nonatomic_entity_quarantined",
        "promotion_structure_observation_quarantined",
    }


def test_unknown_entity_is_recovered_from_source_literal_instead_of_deleted():
    evidence = "A1 contained cuboidal γ′ precipitates."
    fact = _structure(
        evidence=evidence,
        entities=[
            {
                "name_raw": "unknown_entity",
                "canonical_name": "unknown_entity",
                "entity_type": "precipitate",
                "features": [],
                "raw_expression": "γ′ precipitates",
            }
        ],
    )

    result = promote_axis_facts([_anchor("A1")], [fact], source_text=evidence)

    assert len(result.accepted) == 1
    entity = result.accepted[0].data["entities"][0]
    assert entity["name_raw"] == "γ′ precipitates"
    assert entity.get("canonical_name") is None
    assert [issue.code for issue in result.issues] == [
        "promotion_structure_entity_name_recovered"
    ]
    assert result.issues[0].actual["before"]["name_raw"] == "unknown_entity"
    assert result.issues[0].actual["after"]["name_raw"] == "γ′ precipitates"


def test_negated_structure_entity_is_not_positive_when_sibling_feature_proves_removal():
    evidence = "After HIP treatment, the cracks in A1 were completely annihilated."
    fact = _structure(
        evidence=evidence,
        entities=[
            {
                "name_raw": "cracks",
                "entity_type": "defect",
                "role": "reported",
                "features": [],
                "raw_expression": "cracks",
                "source_evidence": [evidence],
            }
        ],
        features=[
            {
                "feature_name_raw": "crack state",
                "value_kind": "categorical",
                "value_raw": "completely annihilated",
                "data_nature": "reported",
                "source_evidence": [evidence],
            }
        ],
    )

    result = promote_axis_facts([_anchor("A1")], [fact], source_text=evidence)

    assert len(result.accepted) == 1
    assert result.accepted[0].data["entities"] == []
    assert result.accepted[0].data["features"] == fact.data["features"]
    assert [issue.code for issue in result.issues] == [
        "promotion_structure_negated_entity_quarantined"
    ]
    assert result.issues[0].actual["reason"] == "negated_sibling_feature"


def test_prose_disappearance_does_not_promote_listed_entities_as_present():
    evidence = (
        "Increasing temperature led to the disappearance of Laves/carbide "
        "and chromium oxide peaks."
    )
    fact = _structure(
        evidence=evidence,
        entities=[
            {
                "name_raw": "Laves/carbide",
                "entity_type": "intermetallic",
                "features": [],
            },
            {
                "name_raw": "chromium oxide",
                "entity_type": "oxide",
                "features": [],
            },
        ],
        features=[
            {
                "feature_name_raw": "peak disappearance",
                "value_kind": "categorical",
                "value_raw": "disappearance",
                "data_nature": "reported",
                "source_evidence": [evidence],
            }
        ],
    )

    result = promote_axis_facts([_anchor("A1")], [fact], source_text=evidence)

    assert len(result.accepted) == 1
    assert result.accepted[0].data["entities"] == []
    assert result.accepted[0].data["features"] == fact.data["features"]
    negated = [
        issue
        for issue in result.issues
        if issue.code == "promotion_structure_negated_entity_quarantined"
    ]
    assert len(negated) == 2
    assert {issue.actual["reason"] for issue in negated} == {
        "entity_local_prose_negation"
    }


def test_unrelated_no_difference_clause_keeps_positive_structure_entities():
    evidence = (
        "There was no distinct difference between A1 and A2 surface oxides, "
        "which were mainly chromium oxide and aluminium oxide."
    )
    fact = _structure(
        evidence=evidence,
        entities=[
            {
                "name_raw": "chromium oxide",
                "entity_type": "oxide",
                "features": [],
            },
            {
                "name_raw": "aluminium oxide",
                "entity_type": "oxide",
                "features": [],
            },
        ],
        features=[],
    )

    result = promote_axis_facts([_anchor("A1")], [fact], source_text=evidence)

    assert result.accepted == (fact,)
    assert not any(
        issue.code == "promotion_structure_negated_entity_quarantined"
        for issue in result.issues
    )


def test_partial_or_process_dissolution_does_not_erase_present_entity():
    cases = [
        ("The partial annihilation of dislocations reduced KAM.", "dislocations"),
        (
            "Anodic dissolution of the surrounding FCC matrix occurred locally.",
            "FCC matrix",
        ),
        ("The vast majority of pores is removed after HIP.", "pores"),
    ]

    for evidence, entity_name in cases:
        fact = _structure(
            evidence=evidence,
            entities=[
                {
                    "name_raw": entity_name,
                    "entity_type": "phase",
                    "features": [],
                }
            ],
            features=[],
        )

        result = promote_axis_facts(
            [_anchor("A1")], [fact], source_text=evidence
        )

        assert result.accepted == (fact,)
        assert not any(
            issue.code == "promotion_structure_negated_entity_quarantined"
            for issue in result.issues
        )


def test_entity_local_negative_predicates_do_not_become_positive_presence():
    cases = [
        (
            "Network segregation phases are completely dissolved after heat treatment.",
            "network segregation phases",
            "completely dissolved",
        ),
        (
            "Gamma-prime phase and carbide precipitates were small or non-existent.",
            "gamma-prime phase",
            "small or non-existent",
        ),
    ]

    for evidence, entity_name, value in cases:
        fact = _structure(
            evidence=evidence,
            entities=[
                {
                    "name_raw": entity_name,
                    "entity_type": "phase",
                    "features": [],
                }
            ],
            features=[
                {
                    "feature_name_raw": "existence state",
                    "value_kind": "categorical",
                    "value_raw": value,
                    "data_nature": "reported",
                    "source_evidence": [evidence],
                }
            ],
        )

        result = promote_axis_facts(
            [_anchor("A1")], [fact], source_text=evidence
        )

        assert len(result.accepted) == 1
        assert result.accepted[0].data["entities"] == []
        assert any(
            issue.code == "promotion_structure_negated_entity_quarantined"
            and issue.actual["reason"] == "entity_local_prose_negation"
            for issue in result.issues
        )


def test_characterization_aliases_merge_across_chunks_for_one_owner():
    method_evidence = (
        "A1 was characterized by scanning electron microscopy "
        "(SEM, Zeiss Supra 55)."
    )
    result_evidence = "SEM-BSE images of A1 reveal the pore distribution."
    source = f"{method_evidence}\n\n{result_evidence}"
    formal = _characterization(
        method="scanning electron microscopy (SEM, Zeiss Supra 55)",
        evidence=method_evidence,
    )
    result_mention = _characterization(
        method="SEM-BSE",
        evidence=result_evidence,
    )

    result = promote_axis_facts(
        [_anchor("A1")],
        [formal, result_mention],
        source_text=source,
    )

    assert len(result.accepted) == 1
    survivor = result.accepted[0]
    assert survivor.data["method_raw"] == formal.data["method_raw"]
    assert survivor.source_evidence == [method_evidence, result_evidence]
    merged = [
        issue
        for issue in result.issues
        if issue.code == "promotion_characterization_alias_merged"
    ]
    assert len(merged) == 1
    assert merged[0].actual["removed"] == result_mention.model_dump()


def test_characterization_result_analysis_does_not_compete_with_method_declaration():
    method_evidence = (
        "EDS measurements were performed using an Oxford X-Max detector."
    )
    analysis_evidence = (
        "EDS analysis presented in Fig. 9 confirms an aluminium-rich oxide."
    )
    mapping_evidence = "The EDS mapping shows zirconium at the grain boundary."
    source = "\n\n".join(
        [method_evidence, analysis_evidence, mapping_evidence]
    )
    formal = _characterization(
        method="EDS (Oxford X-Max detector)",
        method_class="EDS",
        evidence=method_evidence,
    )
    analysis = _characterization(
        method="EDS analysis",
        method_class="EDS",
        evidence=analysis_evidence,
    )
    mapping = _characterization(
        method="EDS mapping",
        method_class="EDS",
        evidence=mapping_evidence,
    )

    result = promote_axis_facts(
        [_anchor("A1")],
        [formal, analysis, mapping],
        source_text=source,
    )

    assert len(result.accepted) == 1
    survivor = result.accepted[0]
    assert survivor.data["method_raw"] == formal.data["method_raw"]
    assert survivor.source_evidence == [
        method_evidence,
        analysis_evidence,
        mapping_evidence,
    ]
    assert sum(
        issue.code == "promotion_characterization_alias_merged"
        for issue in result.issues
    ) == 2


def test_characterization_aliases_merge_across_source_types_for_one_state():
    method_evidence = (
        "A1 was characterized by scanning electron microscopy "
        "(SEM, Zeiss Supra 55)."
    )
    result_evidence = "SEM-BSE images of A1 reveal the pore distribution."
    source = f"{method_evidence}\n\n{result_evidence}"
    formal = _characterization(
        method="scanning electron microscopy (SEM, Zeiss Supra 55)",
        evidence=method_evidence,
    )
    formal.data["source_type"] = "method"
    result_mention = _characterization(
        method="SEM-BSE",
        evidence=result_evidence,
    )
    result_mention.data["source_type"] = "reported"

    result = promote_axis_facts(
        [_anchor("A1")],
        [formal, result_mention],
        source_text=source,
    )

    assert len(result.accepted) == 1
    assert result.accepted[0].data["method_raw"] == formal.data["method_raw"]
    assert result.accepted[0].source_evidence == [
        method_evidence,
        result_evidence,
    ]
    assert [
        issue.code
        for issue in result.issues
        if issue.code == "promotion_characterization_alias_merged"
    ] == ["promotion_characterization_alias_merged"]


def test_v205_characterization_event_separates_simulation_from_experimental_caption():
    formal_evidence = "Atomic-resolution HAADF-STEM simulations were performed."
    simulation_result_evidence = (
        "HAADF-STEM simulations confirm the ordered phase transformation."
    )
    experimental_caption_evidence = (
        "High-resolution experimental HAADF-STEM image of ordering in A1."
    )
    formal = _characterization(
        method="atomic-resolution HAADF-STEM simulations",
        method_class="STEM simulation",
        evidence=formal_evidence,
    )
    simulation_result = _characterization(
        method="HAADF-STEM",
        method_class="STEM",
        evidence=simulation_result_evidence,
    )
    experimental_caption = _characterization(
        method="HAADF-STEM",
        method_class="electron microscopy",
        evidence=experimental_caption_evidence,
    )
    source = "\n\n".join(
        [formal_evidence, simulation_result_evidence, experimental_caption_evidence]
    )

    result = promote_axis_facts(
        [_anchor("A1")],
        [formal, simulation_result, experimental_caption],
        source_text=source,
    )

    assert len(result.accepted) == 1
    assert result.accepted[0].data["method_raw"] == formal.data["method_raw"]
    assert result.accepted[0].source_evidence == [
        formal_evidence,
        simulation_result_evidence,
    ]
    projection = next(
        row
        for row in result.issues
        if row.code == "characterization_event_projection_quarantined"
    )
    assert projection.actual["removed"] == experimental_caption.model_dump()
    assert projection.actual["reason"] == "event_kind_coordinate_conflict"
    assert any(
        row.code == "characterization_event_alias_merged"
        and row.actual["removed"] == simulation_result.model_dump()
        for row in result.issues
    )


def test_v205_characterization_line_scan_caption_does_not_hitchhike_on_eds_event():
    formal_evidence = "A1 was examined by EDS using a Bruker detector."
    caption_evidence = "Integrated EDS line scan of the area denoted by the box."
    formal = _characterization(
        method="EDS",
        method_class="EDS",
        evidence=formal_evidence,
    )
    caption = _characterization(
        method="EDS line scan",
        method_class="spectroscopy",
        evidence=caption_evidence,
    )

    result = promote_axis_facts(
        [_anchor("A1")],
        [formal, caption],
        source_text=f"{formal_evidence}\n\n{caption_evidence}",
    )

    assert result.accepted == (formal,)
    assert any(
        row.code == "characterization_event_projection_quarantined"
        and row.actual["removed"] == caption.model_dump()
        for row in result.issues
    )


def test_v205_characterization_alias_is_ambiguous_between_two_formal_events():
    first_evidence = "A1 was examined by SEM using a Zeiss microscope."
    second_evidence = "A1 was independently examined by SEM using a Tescan microscope."
    caption_evidence = "SEM images show the pore distribution in A1."
    first = _characterization(method="SEM Zeiss", evidence=first_evidence)
    second = _characterization(method="SEM Tescan", evidence=second_evidence)
    caption = _characterization(method="SEM images", evidence=caption_evidence)

    result = promote_axis_facts(
        [_anchor("A1")],
        [first, second, caption],
        source_text="\n\n".join(
            [first_evidence, second_evidence, caption_evidence]
        ),
    )

    assert result.accepted == (first, second)
    issue = next(
        row
        for row in result.issues
        if row.code == "characterization_event_coordinate_ambiguous"
    )
    assert issue.actual["removed"] == caption.model_dump()
    assert issue.actual["formal_event_count"] == 2


def test_v205_characterization_event_switch_off_restores_v204_family_alias(
    monkeypatch,
):
    monkeypatch.setenv(
        "KNOWMAT2_ALPHA25_CHARACTERIZATION_EVENT_ATOMICITY_V205", "0"
    )
    formal_evidence = "Atomic-resolution HAADF-STEM simulations were performed."
    caption_evidence = "Experimental HAADF-STEM image of ordering in A1."
    formal = _characterization(
        method="HAADF-STEM simulations",
        method_class="STEM simulation",
        evidence=formal_evidence,
    )
    caption = _characterization(
        method="HAADF-STEM",
        method_class="STEM",
        evidence=caption_evidence,
    )

    result = promote_axis_facts(
        [_anchor("A1")],
        [formal, caption],
        source_text=f"{formal_evidence}\n\n{caption_evidence}",
    )

    assert len(result.accepted) == 1
    assert result.accepted[0].source_evidence == [formal_evidence, caption_evidence]
    assert not any(
        row.code.startswith("characterization_event_") for row in result.issues
    )


def test_caption_shaped_characterization_projection_is_quarantined():
    evidence = "KAM maps of A1 reveal the residual-stress distribution."
    fact = _characterization(
        method="KAM maps",
        method_class="EBSD",
        evidence=evidence,
    )

    result = promote_axis_facts([_anchor("A1")], [fact], source_text=evidence)

    assert result.accepted == ()
    assert [issue.code for issue in result.issues] == [
        "promotion_characterization_unasserted_result_quarantined"
    ]
    assert result.issues[0].actual["removed"] == fact.model_dump()


def test_direct_imaging_setup_is_preserved_as_characterization():
    evidence = (
        "Samples for EBSD analysis were cut from the TD-ND plane and imaged "
        "with a Zeiss Gemini Sigma 500VP scanning electron microscope."
    )
    fact = _characterization(
        method="scanning electron microscope",
        method_class="SEM",
        evidence=evidence,
    )

    result = promote_axis_facts([_anchor("A1")], [fact], source_text=evidence)

    assert result.accepted == (fact,)
    assert result.issues == ()


def test_compact_instrument_method_declaration_is_preserved():
    evidence = "transmission electron microscopy (TEM, Tecnai G2 F30)"
    fact = _characterization(
        method="transmission electron microscopy (TEM, Tecnai G2 F30)",
        method_class="TEM",
        evidence=evidence,
    )

    result = promote_axis_facts([_anchor("A1")], [fact], source_text=evidence)

    assert result.accepted == (fact,)
    assert result.issues == ()


def test_passive_identification_and_evaluation_methods_are_preserved():
    rows = [
        _characterization(
            method="X-ray diffractometer (XRD; Bruker D8)",
            method_class="XRD",
            evidence=(
                "The phase components were identified by an X-ray diffractometer "
                "(XRD; Bruker D8)."
            ),
        ),
        _characterization(
            sample="PBF-LB",
            method="kernel average misorientation (KAM)",
            method_class="EBSD",
            evidence=(
                "The local mis-orientations of PBF-LB samples were evaluated "
                "by using the kernel average misorientation (KAM) approach."
            ),
        ),
    ]
    source = "\n\n".join(row.source_evidence[0] for row in rows)

    result = promote_axis_facts([_anchor("A1"), _anchor("PBF-LB")], rows, source_text=source)

    assert result.accepted == tuple(rows)


def test_compact_result_caption_without_setup_remains_quarantined():
    evidence = "(c) high-magnification TEM bright field images of A1 sample."
    fact = _characterization(
        method="TEM bright field imaging",
        method_class="TEM",
        evidence=evidence,
    )

    result = promote_axis_facts([_anchor("A1")], [fact], source_text=evidence)

    assert result.accepted == ()
    assert any(
        issue.code == "promotion_characterization_unasserted_result_quarantined"
        for issue in result.issues
    )


def test_source_owner_method_recovery_adds_only_single_owner_declaration(monkeypatch):
    monkeypatch.setenv(
        "KNOWMAT2_ALPHA25_CHARACTERIZATION_SOURCE_METHOD_RECOVERY_V229", "1"
    )
    source = "A1 was examined by SEM using a Zeiss microscope."
    result = promote_axis_facts([_anchor("A1")], [], source_text=source)

    assert len(result.accepted) == 1
    assert result.accepted[0].data["method_class"] == "SEM"
    assert any(
        issue.code == "promotion_characterization_source_method_recovered"
        for issue in result.issues
    )


def test_source_owner_method_recovery_skips_multi_owner_sentence(monkeypatch):
    monkeypatch.setenv(
        "KNOWMAT2_ALPHA25_CHARACTERIZATION_SOURCE_METHOD_RECOVERY_V229", "1"
    )
    source = "A1 and A2 were examined by SEM using a Zeiss microscope."
    result = promote_axis_facts([_anchor("A1"), _anchor("A2")], [], source_text=source)

    assert result.accepted == ()


def test_characterization_method_row_in_markdown_table_is_preserved():
    evidence = "| SEM | Zeiss Supra 55 |"
    source = "| Method | Instrument |\n|---|---|\n" + evidence
    fact = _characterization(
        method="SEM",
        method_class="SEM",
        evidence=evidence,
    )

    result = promote_axis_facts([_anchor("A1")], [fact], source_text=source)

    assert result.accepted == (fact,)
    assert result.issues == ()


def test_characterization_instrument_and_condition_subfields_are_quarantined():
    evidence = (
        "XRD was performed on a PANalytical Empyrean diffractometer at 40 kV."
    )
    facts = [
        _characterization(
            method="XRD instrument",
            method_class="XRD",
            evidence=evidence,
        ),
        _characterization(
            method="XRD condition",
            method_class="XRD",
            evidence=evidence,
        ),
    ]

    result = promote_axis_facts([_anchor("A1")], facts, source_text=evidence)

    assert result.accepted == ()
    assert sum(
        issue.code == "promotion_characterization_non_method_quarantined"
        for issue in result.issues
    ) == 2
    removed = [
        issue.actual["removed"]
        for issue in result.issues
        if issue.code == "promotion_characterization_non_method_quarantined"
    ]
    assert all(any(row == fact.model_dump() for fact in facts) for row in removed)


def test_characterization_result_with_observation_state_is_not_absorbed():
    method_evidence = "A1 was characterized by TEM using a Talos F200X."
    state_evidence = "TEM images of A1 after heat treatment reveal twins."
    source = f"{method_evidence}\n\n{state_evidence}"
    formal = _characterization(
        method="TEM (Talos F200X)",
        method_class="TEM",
        evidence=method_evidence,
    )
    state_result = _characterization(
        method="TEM",
        method_class="TEM",
        evidence=state_evidence,
    )

    result = promote_axis_facts(
        [_anchor("A1")],
        [formal, state_result],
        source_text=source,
    )

    assert result.accepted == (formal,)
    assert not any(
        issue.code == "promotion_characterization_alias_merged"
        for issue in result.issues
    )
    assert any(
        issue.code
        == "promotion_characterization_unasserted_result_quarantined"
        and issue.actual["removed"] == state_result.model_dump()
        for issue in result.issues
    )


def test_multimodal_characterization_result_is_not_absorbed_by_one_family():
    method_evidence = "A1 was characterized by TEM using a Talos F200X."
    multimodal_evidence = "TEM coupled with SAED identified the ordered phase."
    source = f"{method_evidence}\n\n{multimodal_evidence}"
    formal = _characterization(
        method="TEM (Talos F200X)",
        method_class="TEM",
        evidence=method_evidence,
    )
    multimodal = _characterization(
        method="TEM coupled with SAED",
        method_class="diffraction",
        evidence=multimodal_evidence,
    )

    result = promote_axis_facts(
        [_anchor("A1")],
        [formal, multimodal],
        source_text=source,
    )

    assert result.accepted == (formal,)
    assert not any(
        issue.code == "promotion_characterization_alias_merged"
        for issue in result.issues
    )
    assert any(
        issue.code
        == "promotion_characterization_unasserted_result_quarantined"
        and issue.actual["removed"] == multimodal.model_dump()
        for issue in result.issues
    )


def test_characterization_same_method_for_distinct_owners_is_preserved():
    first_evidence = "A1 was characterized by SEM."
    second_evidence = "A2 was characterized by SEM."
    source = f"{first_evidence}\n\n{second_evidence}"
    first = _characterization(sample="A1", evidence=first_evidence)
    second = _characterization(sample="A2", evidence=second_evidence)

    result = promote_axis_facts(
        [_anchor("A1"), _anchor("A2")],
        [first, second],
        source_text=source,
    )

    assert result.accepted == (first, second)
    assert not any(
        issue.code == "promotion_characterization_alias_merged"
        for issue in result.issues
    )


def test_tensile_owner_state_conflict_reassigns_to_existing_base_owner():
    evidence = (
        "H230AM tensile strength after 200 h thermal exposure at 900 °C "
        "was 204 MPa."
    )
    fact = _property(
        sample="H230AM [after thermal exposure at 900 °C for 500 h]",
        name="tensile strength",
        value="204",
        unit="MPa",
        condition="900 °C; 200 h thermal exposure",
        evidence=evidence,
    )
    anchors = [
        _anchor("H230AM", material="H230AM"),
        _anchor(
            "H230AM [after thermal exposure at 900 °C for 500 h]",
            material="H230AM",
            state="after thermal exposure at 900 °C for 500 h",
        ),
    ]

    result = promote_axis_facts(anchors, [fact], source_text=evidence)

    assert len(result.accepted) == 1
    assert result.accepted[0].sample_id_raw == "H230AM"
    assert result.accepted[0].data["test_condition_raw"] == fact.data[
        "test_condition_raw"
    ]
    assert [issue.code for issue in result.issues] == [
        "promotion_tensile_owner_state_conflict_reassigned"
    ]
    issue = result.issues[0]
    assert issue.actual["before"] == fact.model_dump()
    assert issue.actual["after"] == result.accepted[0].model_dump()
    assert issue.actual["conflict_dimension"] == "duration"


def test_tensile_matching_owner_state_is_not_reassigned():
    evidence = (
        "H230AM tensile strength after 500 h thermal exposure at 900 °C "
        "was 200 MPa."
    )
    fact = _property(
        sample="H230AM [after thermal exposure at 900 °C for 500 h]",
        name="tensile strength",
        value="200",
        unit="MPa",
        condition="900 °C; 500 h thermal exposure",
        evidence=evidence,
    )
    anchors = [
        _anchor("H230AM", material="H230AM"),
        _anchor(
            "H230AM [after thermal exposure at 900 °C for 500 h]",
            material="H230AM",
            state="after thermal exposure at 900 °C for 500 h",
        ),
    ]

    result = promote_axis_facts(anchors, [fact], source_text=evidence)

    assert result.accepted == (fact,)
    assert not any(
        issue.code == "promotion_tensile_owner_state_conflict_reassigned"
        for issue in result.issues
    )


def test_structure_fact_with_no_supported_atomic_payload_is_quarantined():
    evidence = "Fig. 3 shows the representative micrograph of A1."
    fact = _structure(
        evidence=evidence,
        entities=[
            {
                "name_raw": "sigma phase",
                "entity_type": "phase",
                "features": [],
                "raw_expression": "sigma phase",
            }
        ],
        features=[],
    )

    result = promote_axis_facts([_anchor("A1")], [fact], source_text=evidence)

    assert result.accepted == ()
    assert [issue.code for issue in result.issues][-1] == (
        "promotion_structure_observation_quarantined"
    )
    assert result.issues[-1].actual["removed"] == fact.model_dump()


def test_comparative_structure_projection_isolated_but_numeric_fact_survives():
    evidence = (
        "The CL sample has a larger grain size than the PL sample, while the "
        "average grain size was 1.52 µm."
    )
    fact = _structure(
        sample="CL",
        evidence=evidence,
        structure_kind="grain_structure",
        entities=[],
        features=[
            {
                "feature_name_raw": "grain size comparison",
                "value_kind": "text",
                "value_raw": "larger than the PL sample",
                "data_nature": "reported",
            },
            {
                "feature_name_raw": "average grain size",
                "value_kind": "scalar",
                "value_raw": "1.52",
                "unit_raw": "µm",
                "data_nature": "reported",
            },
        ],
    )

    result = promote_axis_facts([_anchor("CL")], [fact], source_text=evidence)

    assert len(result.accepted) == 1
    assert [row["feature_name_raw"] for row in result.accepted[0].data["features"]] == [
        "average grain size"
    ]
    assert [issue.code for issue in result.issues] == [
        "promotion_structure_comparative_projection_quarantined"
    ]
    assert result.issues[0].actual["removed"]["feature_name_raw"] == (
        "grain size comparison"
    )


def test_comparator_only_structure_entity_isolated_without_erasing_primary_entity():
    evidence = (
        "The volume fraction of ZrC phases in H230AM is much higher than that "
        "of the M6C in H230."
    )
    fact = _structure(
        sample="H230",
        evidence=evidence,
        entities=[
            {
                "name_raw": "ZrC phases",
                "entity_type": "phase",
                "features": [],
                "raw_expression": "ZrC phases",
            },
            {
                "name_raw": "M6C",
                "entity_type": "phase",
                "features": [],
                "raw_expression": "M6C",
            },
        ],
        features=[],
    )

    result = promote_axis_facts([_anchor("H230")], [fact], source_text=evidence)

    assert len(result.accepted) == 1
    assert [row["name_raw"] for row in result.accepted[0].data["entities"]] == [
        "ZrC phases"
    ]
    assert any(
        issue.code
        == "promotion_structure_comparative_entity_projection_quarantined"
        for issue in result.issues
    )


def test_numeric_comparative_structure_feature_is_not_quarantined():
    evidence = "The average grain size increased from 0.91 to 1.52 µm."
    fact = _structure(
        sample="CL",
        evidence=evidence,
        structure_kind="grain_structure",
        entities=[],
        features=[
            {
                "feature_name_raw": "average grain size",
                "value_kind": "scalar",
                "value_raw": "1.52",
                "unit_raw": "µm",
                "data_nature": "reported",
            }
        ],
    )

    result = promote_axis_facts([_anchor("CL")], [fact], source_text=evidence)

    assert result.accepted == (fact,)
    assert not any(
        issue.code == "promotion_structure_comparative_projection_quarantined"
        for issue in result.issues
    )


def test_textual_structure_variation_projection_is_quarantined():
    evidence = (
        "A prolonged delay of 300 s decreased the variations in the melt pool "
        "length from 100.5% to 0.4%."
    )
    fact = _structure(
        sample="A1",
        evidence=evidence,
        entities=[],
        features=[
            {
                "feature_name_raw": "melt pool length variation",
                "value_kind": "text",
                "value_raw": "100.5% to 0.4%",
                "data_nature": "reported",
            }
        ],
    )

    result = promote_axis_facts([_anchor("A1")], [fact], source_text=evidence)

    assert result.accepted == ()
    issue = next(
        issue
        for issue in result.issues
        if issue.code == "promotion_structure_comparative_projection_quarantined"
    )
    assert issue.actual["removed"] == fact.data["features"][0]


def test_structure_method_only_value_is_quarantined_with_full_audit():
    evidence = (
        "The volume fraction and sizes were measured using polishing and imaging "
        "methods developed by Smith et al."
    )
    fact = _structure(
        evidence=evidence,
        entities=[],
        features=[
            {
                "feature_name_raw": "volume fraction and sizes",
                "value_kind": "text",
                "value_raw": "measured using the polishing and imaging methods",
                "data_nature": "reported",
            }
        ],
    )

    result = promote_axis_facts([_anchor("A1")], [fact], source_text=evidence)

    assert result.accepted == ()
    issue = next(
        issue
        for issue in result.issues
        if issue.code == "promotion_structure_method_only_value_quarantined"
    )
    assert issue.actual["removed"]["value_raw"].startswith("measured using")
    assert issue.evidence == [evidence]


def test_structure_unit_only_value_is_quarantined_without_losing_measurement():
    evidence = (
        "The average grain size using the line intercept method for this "
        "material was 27 µm."
    )
    numeric = {
        "feature_name_raw": "average grain size",
        "value_kind": "scalar",
        "value_raw": "27",
        "unit_raw": "µm",
        "data_nature": "reported",
    }
    unit_only = {
        "feature_name_raw": "grain size unit",
        "value_kind": "categorical",
        "value_raw": "µm",
        "data_nature": "reported",
    }
    fact = _structure(
        evidence=evidence,
        entities=[],
        features=[numeric, unit_only],
    )

    result = promote_axis_facts([_anchor("A1")], [fact], source_text=evidence)

    assert len(result.accepted) == 1
    assert result.accepted[0].data["features"] == [numeric]
    issue = next(
        issue
        for issue in result.issues
        if issue.code == "promotion_structure_unit_only_value_quarantined"
    )
    assert issue.actual == {
        "removed": unit_only,
        "reason": "standalone_measurement_unit_is_not_an_observation",
    }
    assert issue.evidence == [evidence]


def test_feedstock_table_metric_cannot_be_projected_as_precipitate_structure():
    evidence = (
        "| Technology | Mass (g) | Flow rate (s/50g) | Particle size distribution (µm) |\n"
        "| Binder Jetting | 23 | 12 | 7-24 |"
    )
    fact = _structure(
        evidence=evidence,
        entities=[],
        features=[
            {
                "feature_name_raw": "precipitate size",
                "value_kind": "range",
                "value_raw": "7-24",
                "unit_raw": "µm",
                "data_nature": "reported",
            }
        ],
    )

    result = promote_axis_facts([_anchor("A1")], [fact], source_text=evidence)

    assert result.accepted == ()
    assert any(
        issue.code == "promotion_structure_table_axis_mismatch_quarantined"
        and issue.actual["reason"] == "feedstock_table_projected_as_structure"
        for issue in result.issues
    )


def test_comparative_composition_field_is_not_promoted_as_structure():
    evidence = "The iron content was about 64% higher for the EBAM material."
    fact = _structure(
        sample="EBAM",
        evidence=evidence,
        entities=[],
        features=[
            {
                "feature_name_raw": "iron content",
                "value_kind": "inequality",
                "value_raw": "about 64% higher for the EBAM material",
                "data_nature": "reported",
            }
        ],
    )

    result = promote_axis_facts([_anchor("EBAM")], [fact], source_text=evidence)

    assert result.accepted == ()
    assert any(
        issue.code == "promotion_structure_composition_projection_quarantined"
        and issue.actual["reason"]
        == "comparative_composition_field_projected_as_structure"
        for issue in result.issues
    )


def test_inferential_structure_entity_is_quarantined_without_direct_assertion():
    evidence = (
        "The lath microstructure was likely a massive martensite phase."
    )
    fact = _structure(
        evidence=evidence,
        entities=[
            {
                "name_raw": "massive martensite phase",
                "entity_type": "phase",
                "role": "reported",
                "features": [],
                "raw_expression": "massive martensite phase",
                "source_evidence": [evidence],
            }
        ],
        features=[],
        structure_kind="transformation",
    )

    result = promote_axis_facts(
        [_anchor("A1")], [fact], source_text=evidence
    )

    assert result.accepted == ()
    assert any(
        issue.code == "promotion_structure_inferential_projection_quarantined"
        and issue.actual["reason"] == "inferential_entity_without_direct_assertion"
        for issue in result.issues
    )
    assert any(
        issue.actual["removed"]["name_raw"] == "massive martensite phase"
        and issue.evidence == [evidence]
        for issue in result.issues
        if issue.code == "promotion_structure_inferential_projection_quarantined"
    )


def test_inferential_had_clause_does_not_authorize_following_transformation_entity():
    evidence = (
        "Both EBAM and WAAM materials had very low beta contents suggesting "
        "a martensitic transformation took place."
    )
    fact = _structure(
        sample="EBAM",
        evidence=evidence,
        entities=[
            {
                "name_raw": "martensitic transformation",
                "entity_type": "transformation",
                "role": "reported",
                "features": [],
                "raw_expression": "martensitic transformation",
                "source_evidence": [evidence],
            }
        ],
        features=[],
        structure_kind="transformation",
    )

    result = promote_axis_facts([_anchor("EBAM")], [fact], source_text=evidence)

    assert result.accepted == ()
    assert any(
        issue.code == "promotion_structure_inferential_projection_quarantined"
        and issue.actual["reason"] == "inferential_entity_without_direct_assertion"
        for issue in result.issues
    )


def test_structure_noun_forms_do_not_count_as_direct_entity_assertions():
    evidence = (
        "In the initial microstructure shown in Fig. 1, the sharper corners "
        "of cubical gamma-prime precipitates were measured in alloy T5."
    )
    fact = _structure(
        sample="T5",
        evidence=evidence,
        entities=[
            {
                "name_raw": "gamma-prime",
                "entity_type": "precipitate",
                "role": "reported",
                "features": [],
                "raw_expression": "gamma-prime",
                "source_evidence": [evidence],
            }
        ],
        features=[],
        structure_kind="phase_assemblage",
    )

    result = promote_axis_facts([_anchor("T5")], [fact], source_text=evidence)

    assert result.accepted == ()
    assert any(
        issue.code == "promotion_structure_unasserted_entity_quarantined"
        and issue.actual["reason"] == "entity_without_direct_assertion"
        for issue in result.issues
    )


def test_structure_had_clause_with_short_object_span_is_direct():
    evidence = "The as-built sample had fine acicular martensitic grains."
    fact = _structure(
        sample="A1",
        evidence=evidence,
        entities=[
            {
                "name_raw": "acicular martensitic grains",
                "entity_type": "grain",
                "role": "reported",
                "features": [],
                "raw_expression": "acicular martensitic grains",
                "source_evidence": [evidence],
            }
        ],
        features=[],
        structure_kind="morphology",
    )

    result = promote_axis_facts([_anchor("A1")], [fact], source_text=evidence)

    assert result.accepted == (fact,)


def test_bare_element_structure_entity_is_isolated_as_composition_projection():
    evidence = (
        "The alloying elements were partitioned between the gamma matrix and "
        "gamma-prime precipitates; W showed no evident preference for either phase."
    )
    fact = _structure(
        sample="T5",
        evidence=evidence,
        entities=[
            {
                "name_raw": "W",
                "entity_type": "phase",
                "role": "reported",
                "features": [],
                "raw_expression": "W",
                "source_evidence": [evidence],
            }
        ],
        features=[],
    )

    result = promote_axis_facts([_anchor("T5")], [fact], source_text=evidence)

    assert result.accepted == ()
    assert any(
        issue.code == "promotion_structure_element_projection_quarantined"
        and issue.actual["reason"] == "bare_element_token_in_structure"
        for issue in result.issues
    )


def test_hypothetical_structure_feature_isolated_without_direct_observation():
    evidence = "Densely populated amorphous nanoparticles can be deployed inside grains."
    fact = _structure(
        sample="A1",
        evidence=evidence,
        entities=[],
        features=[
            {
                "feature_name_raw": "distribution",
                "value_kind": "categorical",
                "value_raw": "densely populated",
                "data_nature": "reported",
                "source_evidence": [evidence],
            }
        ],
    )

    result = promote_axis_facts([_anchor("A1")], [fact], source_text=evidence)

    assert result.accepted == ()
    assert any(
        issue.code == "promotion_structure_inferential_projection_quarantined"
        and issue.actual["reason"] == "inferential_feature_without_direct_assertion"
        for issue in result.issues
    )


def test_structure_method_and_figure_artifact_values_are_isolated():
    cases = [
        (
            "The internal defects were observed using optical microscopy.",
            "internal defects",
            "observed using optical microscopy",
            "promotion_structure_method_only_value_quarantined",
        ),
        (
            "SEM images of fatigue fracture surfaces of sample A1.",
            "fatigue fracture surface",
            "SEM images of fatigue fracture surfaces",
            "promotion_structure_figure_artifact_quarantined",
        ),
    ]
    for evidence, name, value, code in cases:
        fact = _structure(
            sample="A1",
            evidence=evidence,
            entities=[],
            features=[
                {
                    "feature_name_raw": name,
                    "value_kind": "categorical",
                    "value_raw": value,
                    "data_nature": "reported",
                    "source_evidence": [evidence],
                }
            ],
        )
        result = promote_axis_facts([_anchor("A1")], [fact], source_text=evidence)
        assert result.accepted == ()
        assert any(issue.code == code for issue in result.issues)


def test_unrelated_direct_clause_does_not_authorize_comparator_phase_entity():
    evidence = (
        "The gamma phase and the coarse lamellar region are primarily responsible "
        "for deformation, while the beta phase and ultrafine lamellar grain are "
        "barely deformed at 1023 K."
    )
    fact = _structure(
        sample="R1",
        evidence=evidence,
        entities=[
            {
                "name_raw": "beta phase",
                "entity_type": "phase",
                "role": "reported",
                "features": [],
                "raw_expression": "beta phase",
                "source_evidence": [evidence],
            }
        ],
        features=[],
    )

    result = promote_axis_facts([_anchor("R1")], [fact], source_text=evidence)

    assert result.accepted == ()
    assert any(
        issue.code == "promotion_structure_unasserted_entity_quarantined"
        for issue in result.issues
    )


def test_direct_structure_entity_survives_inferential_sentence():
    evidence = (
        "Fine Widmanstatten alpha platelets were observed in the EBAM material; "
        "the martensitic phase is also possible at high build temperature."
    )
    fact = _structure(
        evidence=evidence,
        entities=[
            {
                "name_raw": "Widmanstatten alpha platelets",
                "entity_type": "phase",
                "role": "reported",
                "features": [],
                "raw_expression": "Widmanstatten alpha platelets",
                "source_evidence": [evidence],
            }
        ],
        features=[],
        structure_kind="phase_assemblage",
    )

    result = promote_axis_facts(
        [_anchor("A1")], [fact], source_text=evidence
    )

    assert result.accepted
    assert result.accepted[0].data["entities"][0]["name_raw"] == (
        "Widmanstatten alpha platelets"
    )
    assert not any(
        issue.code == "promotion_structure_inferential_projection_quarantined"
        for issue in result.issues
    )


def test_numeric_structure_feature_survives_inferential_sentence():
    evidence = "The grain size was likely 10 µm based on the image analysis."
    fact = _structure(
        evidence=evidence,
        entities=[],
        features=[
            {
                "feature_name_raw": "grain size",
                "value_kind": "scalar",
                "value_raw": "10",
                "unit_raw": "µm",
                "source_evidence": [evidence],
            }
        ],
        structure_kind="grain_structure",
    )

    result = promote_axis_facts(
        [_anchor("A1")], [fact], source_text=evidence
    )

    assert result.accepted
    assert result.accepted[0].data["features"][0]["value_raw"] == "10"
    assert not any(
        issue.code == "promotion_structure_inferential_projection_quarantined"
        for issue in result.issues
    )


def test_bare_structure_entity_mention_is_quarantined_without_assertion():
    evidence = "γ/M23C6 (boron-free alloy)"
    fact = _structure(
        evidence=evidence,
        entities=[
            {
                "name_raw": "γ/M23C6",
                "entity_type": "interface",
                "role": "reported",
                "features": [],
                "raw_expression": "γ/M23C6",
                "source_evidence": [evidence],
            }
        ],
        features=[],
        structure_kind="interface",
    )

    result = promote_axis_facts([_anchor("A1")], [fact], source_text=evidence)

    assert result.accepted == ()
    assert any(
        issue.code == "promotion_structure_unasserted_entity_quarantined"
        and issue.actual["reason"] == "entity_without_direct_assertion"
        for issue in result.issues
    )
    assert any(
        issue.code == "promotion_structure_unasserted_observation_quarantined"
        for issue in result.issues
    )


def test_direct_structure_change_entity_survives_without_observation_verb():
    evidence = "The α/α₂ phase gradually decreased with increasing recycling number."
    fact = _structure(
        evidence=evidence,
        entities=[
            {
                "name_raw": "α/α₂ phase",
                "entity_type": "phase",
                "role": "decreasing",
                "features": [],
                "raw_expression": "α/α₂ phase",
                "source_evidence": [evidence],
            }
        ],
        features=[],
        structure_kind="phase_assemblage",
    )

    result = promote_axis_facts([_anchor("A1")], [fact], source_text=evidence)

    assert result.accepted
    assert result.accepted[0].data["entities"][0]["name_raw"] == "α/α₂ phase"
    assert not any(
        issue.code == "promotion_structure_unasserted_entity_quarantined"
        for issue in result.issues
    )


def test_comparative_adjective_does_not_assert_bare_structure_entity():
    evidence = (
        "Anisotropy was an effect of texture and the different orientation "
        "distribution of the transformed alpha phase between the X, Y, and Z directions."
    )
    fact = _structure(
        sample="A1",
        evidence=evidence,
        entities=[
            {
                "name_raw": "transformed alpha phase",
                "entity_type": "phase",
                "role": "phase_constituent",
                "features": [],
                "raw_expression": "transformed alpha phase",
                "source_evidence": [evidence],
            }
        ],
        features=[],
        structure_kind="phase_assemblage",
    )

    result = promote_axis_facts([_anchor("A1")], [fact], source_text=evidence)

    assert result.accepted == ()
    assert any(
        issue.code == "promotion_structure_unasserted_entity_quarantined"
        and issue.actual["reason"] == "entity_without_direct_assertion"
        for issue in result.issues
    )


def test_direct_structure_assertion_variants_survive_bare_mention_gate():
    cases = [
        (
            "LSHR presented the formation of W-rich γ phase along SESFs.",
            "W-rich γ phase",
            "W-rich γ phase",
        ),
        (
            "The SAED graph confirms the dominance of FCC phase.",
            "FCC phase",
            "FCC phase",
        ),
        (
            "The BCC phase grows to 2 µm and surrounds the FCC matrix.",
            "FCC phase",
            "surrounds the FCC matrix",
        ),
        (
            "Ductile failure was detailed by ductile dimple fracture.",
            "ductile dimple fracture",
            "ductile dimple fracture",
        ),
    ]

    for evidence, name_raw, raw_expression in cases:
        fact = _structure(
            evidence=evidence,
            entities=[
                {
                    "name_raw": name_raw,
                    "entity_type": "phase",
                    "role": "reported",
                    "features": [],
                    "raw_expression": raw_expression,
                    "source_evidence": [evidence],
                }
            ],
            features=[],
            structure_kind="phase_assemblage",
        )

        result = promote_axis_facts(
            [_anchor("A1")], [fact], source_text=evidence
        )

        assert result.accepted
        assert not any(
            issue.code == "promotion_structure_unasserted_entity_quarantined"
            for issue in result.issues
        )


def test_table_structure_entity_is_not_subject_to_bare_mention_gate():
    evidence = "| Phase | α/α₂ |"
    fact = _structure(
        evidence=evidence,
        entities=[
            {
                "name_raw": "α/α₂",
                "entity_type": "phase",
                "role": "reported",
                "features": [],
                "raw_expression": "α/α₂",
                "source_evidence": [evidence],
            }
        ],
        features=[],
        structure_kind="phase_assemblage",
    )

    result = promote_axis_facts([_anchor("A1")], [fact], source_text=evidence)

    assert result.accepted == (fact,)


def test_exact_structure_projection_is_routed_to_named_owner_and_deduplicated():
    evidence = "A1 contained fine gamma-prime precipitates."
    facts = [
        _structure(sample="A1", evidence=evidence),
        _structure(sample="A2", evidence=evidence),
    ]

    result = promote_axis_facts(
        [_anchor("A1"), _anchor("A2")], facts, source_text=evidence
    )

    assert [fact.sample_id_raw for fact in result.accepted] == ["A1"]
    assert {issue.code for issue in result.issues} == {
        "promotion_owner_reassigned",
        "promotion_assertion_duplicate_merged",
    }
    reassigned = next(
        issue for issue in result.issues if issue.code == "promotion_owner_reassigned"
    )
    assert reassigned.actual["before"]["sample_id_raw"] == "A2"
    assert reassigned.actual["after"]["sample_id_raw"] == "A1"


def test_explicit_shared_structure_assertion_preserves_each_named_owner():
    evidence = "A1 and A2 both contained fine gamma-prime precipitates."
    facts = [
        _structure(sample="A1", evidence=evidence),
        _structure(sample="A2", evidence=evidence),
    ]

    result = promote_axis_facts(
        [_anchor("A1"), _anchor("A2")], facts, source_text=evidence
    )

    assert {fact.sample_id_raw for fact in result.accepted} == {"A1", "A2"}
    assert not any(
        issue.code == "promotion_cross_owner_projection_quarantined"
        for issue in result.issues
    )


def test_cross_owner_projection_keeps_named_pair_but_quarantines_third_copy():
    evidence = "A1 and A2 contained fine gamma-prime precipitates."
    facts = [
        _structure(sample="A1", evidence=evidence),
        _structure(sample="A2", evidence=evidence),
        _structure(sample="A3", evidence=evidence),
    ]

    result = promote_axis_facts(
        [_anchor("A1"), _anchor("A2"), _anchor("A3")],
        facts,
        source_text=evidence,
    )

    assert [fact.sample_id_raw for fact in result.accepted] == ["A1", "A2"]
    assert [issue.code for issue in result.issues] == [
        "promotion_cross_owner_projection_quarantined"
    ]
    assert result.issues[0].actual["removed"] == facts[2].model_dump()
    assert result.issues[0].expected["explicit_owners"] == ["a1", "a2"]


def test_ambiguous_shared_structure_without_owner_isolated_for_review():
    evidence = "Fine gamma-prime precipitates were observed."
    facts = [
        _structure(sample="A1", evidence=evidence),
        _structure(sample="A2", evidence=evidence),
    ]

    result = promote_axis_facts(
        [_anchor("A1"), _anchor("A2")], facts, source_text=evidence
    )

    assert result.accepted == ()
    assert [issue.code for issue in result.issues].count(
        "promotion_ambiguous_shared_assertion_quarantined"
    ) >= 2


def test_collective_owner_grammar_preserves_shared_processing_assertion():
    evidence = "The same heat treatment was applied to all three alloys."
    facts = [
        _processing(sample="A1", process="heat treatment", evidence=evidence),
        _processing(sample="A2", process="heat treatment", evidence=evidence),
        _processing(sample="A3", process="heat treatment", evidence=evidence),
    ]

    result = promote_axis_facts(
        [_anchor("A1"), _anchor("A2"), _anchor("A3")],
        facts,
        source_text=evidence,
    )

    assert [row.sample_id_raw for row in result.accepted] == ["A1", "A2", "A3"]
    assert not any(
        issue.code.startswith("promotion_cross_owner")
        or issue.code == "promotion_ambiguous_shared_assertion_quarantined"
        for issue in result.issues
    )


def test_composition_exact_evidence_projection_quarantines_only_unnamed_owner():
    evidence = (
        "The hatch melt sample with addition of Y2O3 nanoparticles exhibits "
        "many lack-of-fusion defects."
    )
    wrong_copy = _composition(
        sample="multi-spot melt sample",
        component="Y2O3 nanoparticles",
        value="addition",
        unit="not_reported",
        evidence=evidence,
    )
    grounded = _composition(
        sample="hatch melt sample",
        component="Y2O3 nanoparticles",
        value="addition",
        unit="not_reported",
        evidence=evidence,
    )

    result = promote_axis_facts(
        [
            _anchor("multi-spot melt sample"),
            _anchor("hatch melt sample"),
        ],
        [wrong_copy, grounded],
        source_text=evidence,
    )

    assert result.accepted == (grounded,)
    assert [issue.code for issue in result.issues] == [
        "promotion_composition_cross_owner_projection_quarantined"
    ]
    issue = result.issues[0]
    assert issue.actual["removed"] == wrong_copy.model_dump()
    assert issue.actual["copied_owner"] == "multi-spot melt sample"
    assert issue.expected["source_explicit_owner"] == "hatch melt sample"
    assert issue.expected["exact_normalized_evidence"] is True
    assert issue.expected["audit_preserved"] is True


def test_composition_explicit_both_owners_are_preserved():
    evidence = "A1 and A2 both contained 2 wt.% TiB2."
    facts = [
        _composition(
            sample=sample,
            component="TiB2",
            value="2",
            unit="wt.%",
            evidence=evidence,
        )
        for sample in ("A1", "A2")
    ]

    result = promote_axis_facts(
        [_anchor("A1"), _anchor("A2")],
        facts,
        source_text=evidence,
    )

    assert [row.sample_id_raw for row in result.accepted] == ["A1", "A2"]
    assert not any(
        issue.code
        == "promotion_composition_cross_owner_projection_quarantined"
        for issue in result.issues
    )


def test_composition_table_owner_columns_with_equal_values_are_preserved():
    header = "| Component | A1 | A2 |"
    row = "| TiB2 (wt.%) | 2 | 2 |"
    source = "\n".join([header, row])
    facts = [
        _composition(
            sample=sample,
            component="TiB2",
            value="2",
            unit="wt.%",
            evidence=row,
        )
        for sample in ("A1", "A2")
    ]
    for fact in facts:
        fact.source_evidence = [header, row]
        fact.data["source_evidence"] = [header, row]
        fact.data["data_source"] = "table"

    result = promote_axis_facts(
        [_anchor("A1"), _anchor("A2")],
        facts,
        source_text=source,
    )

    assert result.accepted == tuple(facts)
    assert not any(
        issue.code
        == "promotion_composition_cross_owner_projection_quarantined"
        for issue in result.issues
    )


def test_composition_table_owner_row_value_mismatch_is_quarantined():
    source = "\n".join(
        [
            "| Alloy | Al (wt.%) | Ti (wt.%) |",
            "|---|---:|---:|",
            "| A1 | 6 | Balance |",
            "| A2 | 8 | Balance |",
        ]
    )
    fact = _composition(
        sample="A1",
        component="Al",
        value="8",
        unit="wt.%",
        evidence="\n".join([source.splitlines()[0], source.splitlines()[2]]),
    )
    fact.data["components"] = [
        {
            "name_raw": "Al",
            "value_kind": "scalar",
            "value_raw": "8",
            "unit_raw": "wt.%",
            "data_nature": "reported",
        }
    ]
    fact.data["data_source"] = "table"
    fact.source_evidence = source.splitlines()
    fact.data["source_evidence"] = source.splitlines()

    result = promote_axis_facts(
        [_anchor("A1"), _anchor("A2")], [fact], source_text=source
    )

    assert result.accepted == ()
    issue = next(
        issue
        for issue in result.issues
        if issue.code == "promotion_composition_table_owner_value_ambiguous_quarantined"
    )
    assert issue.actual["reason"] == "component_value_bound_to_other_owner_row"
    assert issue.actual["removed"] == fact.model_dump()


def test_composition_table_owner_row_value_coordinate_is_preserved():
    source = "\n".join(
        [
            "| Alloy | Al (wt.%) | Ti (wt.%) |",
            "|---|---:|---:|",
            "| A1 | 6 | Balance |",
            "| A2 | 8 | Balance |",
        ]
    )
    fact = _composition(
        sample="A1",
        component="Al",
        value="6",
        unit="wt.%",
        evidence="\n".join([source.splitlines()[0], source.splitlines()[2]]),
    )
    fact.data["components"] = [
        {
            "name_raw": "Al",
            "value_kind": "scalar",
            "value_raw": "6",
            "unit_raw": "wt.%",
            "data_nature": "reported",
        }
    ]
    fact.data["data_source"] = "table"
    fact.source_evidence = source.splitlines()
    fact.data["source_evidence"] = source.splitlines()

    result = promote_axis_facts(
        [_anchor("A1"), _anchor("A2")], [fact], source_text=source
    )

    assert result.accepted == (fact,)
    assert not any(
        issue.code == "promotion_composition_table_owner_value_ambiguous_quarantined"
        for issue in result.issues
    )


def test_composition_table_header_only_evidence_still_checks_owner_value_row():
    source = "\n".join(
        [
            "| Alloy | Al (wt.%) | Ti (wt.%) |",
            "|---|---:|---:|",
            "| A1 | 6 | Balance |",
            "| A2 | 8 | Balance |",
        ]
    )
    # The chunk response retained only the table header, but the structured
    # value is still source-grounded.  It must not bypass the row coordinate
    # check and attach A2's value to A1.
    header = source.splitlines()[0]
    fact = _composition(
        sample="A1",
        component="Al",
        value="8",
        unit="wt.%",
        evidence=header,
    )
    fact.data["components"] = [
        {
            "name_raw": "Al",
            "value_kind": "scalar",
            "value_raw": "8",
            "unit_raw": "wt.%",
            "data_nature": "reported",
        }
    ]
    fact.data["data_source"] = "table"

    result = promote_axis_facts(
        [_anchor("A1"), _anchor("A2")], [fact], source_text=source
    )

    assert result.accepted == ()
    issue = next(
        issue
        for issue in result.issues
        if issue.code == "promotion_composition_table_owner_value_ambiguous_quarantined"
    )
    assert issue.actual["reason"] == "component_value_bound_to_other_owner_row"


def test_prose_explicit_owner_mismatch_is_quarantined_even_with_different_payload():
    evidence = "A1 exhibited fine gamma-prime precipitates after aging."
    fact = _structure(sample="A2", evidence=evidence)

    result = promote_axis_facts(
        [_anchor("A1"), _anchor("A2")], [fact], source_text=evidence
    )

    assert result.accepted == ()
    assert [issue.code for issue in result.issues] == [
        "promotion_evidence_explicit_owner_mismatch_quarantined"
    ]
    issue = result.issues[0]
    assert issue.actual["removed"] == fact.model_dump()
    assert issue.actual["copied_owner"] == "A2"
    assert issue.expected["source_explicit_owner"] == "A1"
    assert issue.expected["audit_preserved"] is True


def test_prose_explicit_owner_mismatch_keeps_noncore_property_audit_safe():
    evidence = "A1 had a hardness of 420 HV after aging."
    fact = _property(
        sample="A2",
        name="hardness",
        value="420",
        unit="HV",
        condition="",
        evidence=evidence,
    )

    result = promote_axis_facts(
        [_anchor("A1"), _anchor("A2")], [fact], source_text=evidence
    )

    assert result.accepted == ()
    assert [issue.code for issue in result.issues] == [
        "promotion_evidence_explicit_owner_mismatch_quarantined"
    ]


def test_prose_owner_implicit_fact_is_preserved_for_review():
    evidence = "The aged samples exhibited fine gamma-prime precipitates."
    fact = _structure(sample="A2", evidence=evidence)

    result = promote_axis_facts(
        [_anchor("A1"), _anchor("A2")], [fact], source_text=evidence
    )

    assert result.accepted == (fact,)
    assert result.issues == ()


def test_table_owner_mismatch_is_deferred_without_cell_coordinates():
    header = "| Feature | A1 | A2 |"
    row = "| Precipitates | fine gamma-prime precipitates | fine gamma-prime precipitates |"
    source = "\n".join([header, row])
    fact = _structure(sample="A2", evidence=row)
    fact.source_evidence = [header, row]
    fact.data["source_evidence"] = [header, row]

    result = promote_axis_facts(
        [_anchor("A1"), _anchor("A2")], [fact], source_text=source
    )

    assert result.accepted == (fact,)
    assert not any(
        issue.code == "promotion_evidence_explicit_owner_mismatch_quarantined"
        for issue in result.issues
    )


def test_shared_owner_prose_is_preserved_without_broadcast_deletion():
    evidence = "A1 and A2 both exhibited fine gamma-prime precipitates."
    facts = [
        _structure(sample="A1", evidence=evidence),
        _structure(sample="A2", evidence=evidence),
    ]

    result = promote_axis_facts(
        [_anchor("A1"), _anchor("A2")], facts, source_text=evidence
    )

    assert result.accepted == tuple(facts)
    assert not any(
        issue.code == "promotion_evidence_explicit_owner_mismatch_quarantined"
        for issue in result.issues
    )


def test_numeric_condition_mention_is_not_treated_as_material_owner():
    evidence = "Hardness increased from 149 ± 12 to 191 ± 7 HV with 120 s delay."
    fact = _property(
        sample="single wall",
        name="hardness",
        value="191 ± 7",
        unit="HV",
        condition="",
        evidence=evidence,
    )

    result = promote_axis_facts(
        [_anchor("single wall"), _anchor("120 s")], [fact], source_text=evidence
    )

    assert result.accepted == (fact,)
    assert not any(
        issue.code == "promotion_evidence_explicit_owner_mismatch_quarantined"
        for issue in result.issues
    )


def test_generic_sample_descriptor_is_not_treated_as_material_owner():
    evidence = "The BSE images show the wall samples with a basal texture."
    fact = _characterization(sample="Wall 1", method="BSE", evidence=evidence)

    result = promote_axis_facts(
        [_anchor("Wall 1"), _anchor("wall samples")], [fact], source_text=evidence
    )

    assert result.accepted == ()
    assert any(
        issue.code
        == "promotion_characterization_unasserted_result_quarantined"
        and issue.actual["removed"] == fact.model_dump()
        for issue in result.issues
    )


def test_composition_sample_range_scope_is_preserved_without_middle_owner_name():
    evidence = "Samples A1-A3 all contained 2 wt.% TiB2."
    facts = [
        _composition(
            sample=sample,
            component="TiB2",
            value="2",
            unit="wt.%",
            evidence=evidence,
        )
        for sample in ("A1", "A2", "A3")
    ]

    result = promote_axis_facts(
        [_anchor("A1"), _anchor("A2"), _anchor("A3")],
        facts,
        source_text=evidence,
    )

    assert result.accepted == tuple(facts)
    assert not any(
        issue.code
        == "promotion_composition_cross_owner_projection_quarantined"
        for issue in result.issues
    )


def test_composition_sample_list_scope_is_preserved():
    evidence = "Samples A1, A2, and A3 each contained 2 wt.% TiB2."
    facts = [
        _composition(
            sample=sample,
            component="TiB2",
            value="2",
            unit="wt.%",
            evidence=evidence,
        )
        for sample in ("A1", "A2", "A3")
    ]

    result = promote_axis_facts(
        [_anchor("A1"), _anchor("A2"), _anchor("A3")],
        facts,
        source_text=evidence,
    )

    assert result.accepted == tuple(facts)
    assert not any(
        issue.code
        == "promotion_composition_cross_owner_projection_quarantined"
        for issue in result.issues
    )


def test_composition_different_evidence_or_values_are_not_cross_owner_deduped():
    first_evidence = "A1 contained 2 wt.% TiB2."
    second_evidence = "A2 independently contained 2 wt.% TiB2."
    shared_evidence = "A1 contained 3 wt.% TiB2."
    facts = [
        _composition(
            sample="A1",
            component="TiB2",
            value="2",
            unit="wt.%",
            evidence=first_evidence,
        ),
        _composition(
            sample="A2",
            component="TiB2",
            value="2",
            unit="wt.%",
            evidence=second_evidence,
        ),
        _composition(
            sample="A1",
            component="TiB2",
            value="3",
            unit="wt.%",
            evidence=shared_evidence,
        ),
        _composition(
            sample="A2",
            component="TiB2",
            value="4",
            unit="wt.%",
            evidence=shared_evidence,
        ),
    ]
    source = " ".join([first_evidence, second_evidence, shared_evidence])

    result = promote_axis_facts(
        [_anchor("A1"), _anchor("A2")],
        facts,
        source_text=source,
    )

    # The fourth candidate reuses the shared ``A1 ... 3 wt.%`` evidence while
    # claiming ``A2 ... 4 wt.%``.  Composition precision promotion now treats
    # that unbound number as a projection and preserves it only in the audit.
    assert result.accepted == tuple(facts[:3])
    assert any(
        issue.code == "composition_component_precision_quarantined"
        and issue.sample_id_raw == "A2"
        and issue.actual["reason"] == "numeric_literal_not_in_component_evidence"
        for issue in result.issues
    )
    assert not any(
        issue.code
        == "promotion_composition_cross_owner_projection_quarantined"
        for issue in result.issues
    )


def test_composition_bracketed_owner_base_mention_preserves_shared_fact():
    evidence = "GA as well as WA contained 0.2 wt.% oxygen."
    facts = [
        _composition(
            sample=sample,
            component="oxygen",
            value="0.2",
            unit="wt.%",
            evidence=evidence,
        )
        for sample in ("GA [GA powder]", "WA")
    ]

    result = promote_axis_facts(
        [_anchor("GA [GA powder]"), _anchor("WA")],
        facts,
        source_text=evidence,
    )

    assert result.accepted == tuple(facts)
    assert not any(
        issue.code
        == "promotion_composition_cross_owner_projection_quarantined"
        for issue in result.issues
    )


def test_structure_exact_evidence_projection_quarantines_only_unnamed_owner():
    evidence = (
        "Sigma precipitation inhibited B2 phase grain growth in the PBF-EB "
        "samples."
    )
    source = "PBF-LB samples were also examined in this section. " + evidence
    entity = {
        "name_raw": "B2 phase",
        "entity_type": "phase",
        "features": [],
        "raw_expression": "B2 phase",
    }
    grounded = _structure(
        sample="PBF-EB",
        evidence=evidence,
        entities=[entity],
        features=[],
        structure_kind="phase_assemblage",
    )
    wrong_copy = _structure(
        sample="PBF-LB",
        evidence=evidence,
        entities=[entity],
        features=[],
        structure_kind="phase_assemblage",
    )

    result = promote_axis_facts(
        [_anchor("PBF-EB"), _anchor("PBF-LB")],
        [grounded, wrong_copy],
        source_text=source,
    )

    assert result.accepted == (grounded,)
    issue = next(
        issue
        for issue in result.issues
        if issue.code
        == "promotion_structure_exact_evidence_owner_projection_quarantined"
    )
    assert issue.actual["removed"] == wrong_copy.model_dump()
    assert issue.expected["source_explicit_owner"] == "PBF-EB"
    assert issue.expected["audit_preserved"] is True


def test_structure_bracketed_owner_base_mention_preserves_shared_fact():
    evidence = (
        "B2 phase was observed in EPBF as well as non-heat treated LPBF."
    )
    source = (
        "LPBF [non-heat treated] denotes the non-heat treated LPBF condition. "
        + evidence
    )
    entity = {
        "name_raw": "B2 phase",
        "entity_type": "phase",
        "features": [],
        "raw_expression": "B2 phase",
    }
    facts = [
        _structure(
            sample=sample,
            evidence=evidence,
            entities=[entity],
            features=[],
            structure_kind="phase_assemblage",
        )
        for sample in ("EPBF", "LPBF [non-heat treated]")
    ]

    result = promote_axis_facts(
        [_anchor("EPBF"), _anchor("LPBF [non-heat treated]")],
        facts,
        source_text=source,
    )

    assert result.accepted == tuple(facts)
    assert not any(
        issue.code
        == "promotion_structure_exact_evidence_owner_projection_quarantined"
        for issue in result.issues
    )


def test_processing_region_observations_do_not_become_process_stages():
    facts = [
        _processing(
            process="casting",
            evidence=(
                "In cast regions, all samples consisted of nearly equiaxed grains."
            ),
        ),
        _processing(
            process="laser surface remelting",
            evidence=(
                "Fine intergranular phases were left in laser glazing regions."
            ),
        ),
        _processing(
            process="laser glazing",
            evidence=(
                "SEM and EBSD characterizations were performed at laser glazing "
                "regions and cast regions."
            ),
        ),
    ]

    result = promote_axis_facts(
        [_anchor("A1")],
        facts,
        source_text="\n\n".join(
            evidence for fact in facts for evidence in fact.source_evidence
        ),
    )

    assert result.accepted == ()
    assert [issue.code for issue in result.issues] == [
        "promotion_processing_observation_projection_quarantined",
        "promotion_processing_observation_projection_quarantined",
        "promotion_processing_observation_projection_quarantined",
    ]
    assert [issue.actual["removed"] for issue in result.issues] == [
        fact.model_dump() for fact in facts
    ]


def test_explicit_process_events_survive_processing_observation_gate():
    facts = [
        _processing(process="casting", evidence="The five ingots were cast."),
        _processing(
            process="laser glazing",
            evidence="The polished cylinders were laser-glazed on the top surface.",
        ),
        _processing(
            process="laser surface remelting",
            evidence="The specimen surface was remelted with a fiber laser.",
        ),
        _processing(
            process="laser powder bed fusion",
            evidence="The alloy was fabricated by laser powder bed fusion.",
        ),
    ]

    result = promote_axis_facts(
        [_anchor("A1")],
        facts,
        source_text="\n\n".join(
            evidence for fact in facts for evidence in fact.source_evidence
        ),
    )

    assert result.accepted == tuple(facts)
    assert not any(
        issue.code == "promotion_processing_observation_projection_quarantined"
        for issue in result.issues
    )


def test_explicit_process_parameters_preserve_processing_stage():
    evidence = "Table 2. Processing parameters of laser glazing: power 300 W."
    fact = _processing(
        process="laser glazing",
        evidence=evidence,
        parameters=[
            {
                "parameter_name_raw": "laser power",
                "value_raw": "300",
                "unit_raw": "W",
                "source_evidence": "power 300 W",
            }
        ],
    )

    result = promote_axis_facts([_anchor("A1")], [fact], source_text=evidence)

    assert result.accepted == (fact,)
    assert not any(
        issue.code == "promotion_processing_observation_projection_quarantined"
        for issue in result.issues
    )


def test_tex_sample_list_and_both_grammar_preserve_shared_assertions():
    characterization_evidence = (
        "TEM analysis was performed on S_{0}, S_{15}, and S_{70}."
    )
    characterization_facts = [
        _characterization(sample=sample, method="TEM", evidence=characterization_evidence)
        for sample in ("S0", "S15", "S70")
    ]

    characterization = promote_axis_facts(
        [_anchor("S0"), _anchor("S15"), _anchor("S70")],
        characterization_facts,
        source_text=characterization_evidence,
    )

    assert characterization.accepted == tuple(characterization_facts)
    assert characterization.issues == ()

    property_evidence = "Both S_{15} and S_{70} had grain sizes below 10 μm."
    property_facts = [
        _property(
            sample=sample,
            name="average grain size",
            value="<10",
            unit="μm",
            condition="",
            evidence=property_evidence,
        )
        for sample in ("S15", "S70")
    ]

    properties = promote_axis_facts(
        [_anchor("S15"), _anchor("S70")],
        property_facts,
        source_text=property_evidence,
    )

    assert properties.accepted == tuple(property_facts)
    assert properties.issues == ()


def test_enumerated_plural_alloy_caption_preserves_shared_heat_treatment():
    evidence = (
        "Backscattered SEM images showing fully heat treated boron-free, low, "
        "medium and high boron alloys are given in Fig. 1."
    )
    facts = [
        _processing(sample=sample, process="heat treatment", evidence=evidence)
        for sample in (
            "boron-free alloy",
            "low boron alloy",
            "medium boron alloy",
            "high boron alloy",
        )
    ]

    result = promote_axis_facts(
        [_anchor(fact.sample_id_raw) for fact in facts],
        facts,
        source_text=evidence,
    )

    assert result.accepted == tuple(facts)
    assert result.issues == ()


def test_unowned_processing_group_is_preserved_when_no_owner_can_be_proved():
    evidence = "The laser power was 300 W."
    facts = [
        _processing(sample="A1", evidence=evidence),
        _processing(sample="A2", evidence=evidence),
    ]

    result = promote_axis_facts(
        [_anchor("A1"), _anchor("A2")], facts, source_text=evidence
    )

    assert result.accepted == tuple(facts)
    assert result.issues == ()


def test_multi_owner_processing_table_preserves_one_fact_per_named_column():
    source = "\n".join(
        [
            "| Parameter | A1 | A2 |",
            "|---|---:|---:|",
            "| Laser power (W) | 300 | 300 |",
        ]
    )
    evidence = "| Laser power (W) | 300 | 300 |"
    facts = [
        _processing(sample="A1", evidence=evidence),
        _processing(sample="A2", evidence=evidence),
    ]

    result = promote_axis_facts(
        [_anchor("A1"), _anchor("A2")], facts, source_text=source
    )

    assert result.accepted == tuple(facts)
    assert result.issues == ()


def test_processing_table_filters_sibling_owner_parameter_projection():
    source = "\n".join(
        [
            "| Process Variables | Wall 1 | Wall 2 | Wall 3 |",
            "|---|---:|---:|---:|",
            "| Laser Power (W) | 5000 | 5000 | 5000 |",
            "| Interlayer Delay (s) | 0 | 120 | 300 |",
        ]
    )
    evidence = source.splitlines()
    parameters = [
        {
            "parameter_name_raw": "Laser Power",
            "value_raw": "5000",
            "unit_raw": "W",
            "source_evidence": "Laser Power (W) | 5000",
        },
        {
            "parameter_name_raw": "Interlayer Delay",
            "value_raw": "0",
            "unit_raw": "s",
            "source_evidence": "Interlayer Delay (s) | 0",
        },
    ]
    fact = _processing(
        sample="Wall 2",
        evidence="The process variables used for the deposition of the walls; Wall 2",
        parameters=parameters,
    )
    fact.source_evidence = [evidence[0], "Wall 2"]
    fact.data["source_evidence"] = [evidence[0], "Wall 2"]

    result = promote_axis_facts(
        [_anchor("Wall 1"), _anchor("Wall 2"), _anchor("Wall 3")],
        [fact],
        source_text=source,
    )

    assert len(result.accepted) == 1
    kept = result.accepted[0].data["parameters_raw"]
    assert [(row["parameter_name_raw"], row["value_raw"]) for row in kept] == [
        ("Laser Power", "5000")
    ]
    issue = next(
        issue
        for issue in result.issues
        if issue.code == "promotion_processing_table_parameter_projection_filtered"
    )
    assert issue.actual["removed_parameters"][0]["parameter_name_raw"] == (
        "Interlayer Delay"
    )
    assert issue.actual["parameter_coordinates"][0]["target_cell"] == "120"


def test_processing_row_table_filters_value_from_other_owner_row():
    source = "\n".join(
        [
            "| Sample | Laser Power (W) | Scan Speed (mm/s) |",
            "|---|---:|---:|",
            "| A1 | 300 | 1000 |",
            "| A2 | 400 | 1200 |",
        ]
    )
    evidence = source.splitlines()
    parameters = [
        {
            "parameter_name_raw": "Laser Power",
            "value_raw": "400",
            "unit_raw": "W",
            "source_evidence": [evidence[3]],
        },
        {
            "parameter_name_raw": "Scan Speed",
            "value_raw": "1000",
            "unit_raw": "mm/s",
            "source_evidence": [evidence[3]],
        },
    ]
    fact = _processing(
        sample="A1",
        evidence="\n".join(evidence),
        parameters=parameters,
    )
    fact.source_evidence = evidence
    fact.data["source_evidence"] = evidence

    result = promote_axis_facts(
        [_anchor("A1"), _anchor("A2")], [fact], source_text=source
    )

    assert len(result.accepted) == 1
    kept = result.accepted[0].data["parameters_raw"]
    assert [(row["parameter_name_raw"], row["value_raw"]) for row in kept] == [
        ("Scan Speed", "1000")
    ]
    assert any(
        issue.code == "promotion_processing_table_parameter_projection_filtered"
        for issue in result.issues
    )


def test_processing_column_table_filters_value_from_other_owner_column():
    """A column-table value copied from a sibling owner is isolated."""
    source = "\n".join(
        [
            "| Parameter | A1 | A2 |",
            "|---|---:|---:|",
            "| Laser Power (W) | 300 | 400 |",
        ]
    )
    fact = _processing(
        sample="A1",
        evidence=source,
        parameters=[
            {
                "parameter_name_raw": "Laser Power",
                "value_raw": "400",
                "unit_raw": "W",
                "source_evidence": ["Laser Power (W) | 300 | 400"],
            }
        ],
    )

    result = promote_axis_facts(
        [_anchor("A1"), _anchor("A2")], [fact], source_text=source
    )

    assert result.accepted == ()
    issue = next(
        issue
        for issue in result.issues
        if issue.code == "promotion_processing_table_parameter_projection_filtered"
    )
    assert issue.actual["removed_parameters"][0]["value_raw"] == "400"
    assert issue.actual["parameter_coordinates"][0]["target_cell"] == "300"


def test_relative_tensile_delta_in_evidence_is_not_absolute_result():
    evidence = (
        "The 4-1 sample increased the Pareto front by 1.2% in terms of TE "
        "and 69.3 MPa in terms of UTS."
    )
    fact = _property(
        sample="4-1",
        name="UTS",
        value="69.3",
        unit="MPa",
        condition="",
        evidence=evidence,
    )

    result = promote_axis_facts(
        [_anchor("4-1")], [fact], source_text=evidence
    )

    assert result.accepted == ()
    issue = next(
        issue
        for issue in result.issues
        if issue.code == "promotion_property_comparative_projection_quarantined"
    )
    assert issue.actual["reason"] == "relative_core_tensile_evidence_delta"


def test_structure_value_before_comparison_cue_is_not_rebound_to_comparator():
    evidence = (
        "The fine precipitates in the columnar grains increased to 72 ± 21 nm, "
        "which was a growth of 71% compared to those in the AF sample."
    )
    fact = _structure(
        sample="AF",
        evidence=evidence,
        entities=[],
        features=[
            {
                "feature_name_raw": "precipitate size",
                "value_kind": "scalar",
                "value_raw": "72 ± 21 nm",
                "data_nature": "reported",
            }
        ],
    )

    result = promote_axis_facts(
        [_anchor("AF")], [fact], source_text=evidence
    )

    assert result.accepted == ()
    issue = next(
        issue
        for issue in result.issues
        if issue.code
        == "promotion_structure_comparative_numeric_projection_quarantined"
    )
    assert issue.actual["reason"] == "owner_comparator_side_numeric_projection"


def test_structure_value_on_comparator_side_is_retained_when_it_is_the_value_subject():
    evidence = (
        "The α2-phase fraction of L70 was 50%, considerably higher than the "
        "L90 value of 12%."
    )
    fact = _structure(
        sample="L90",
        evidence=evidence,
        entities=[],
        features=[
            {
                "feature_name_raw": "α2-phase fraction",
                "value_kind": "scalar",
                "value_raw": "12%",
                "data_nature": "reported",
            }
        ],
    )

    result = promote_axis_facts(
        [_anchor("L70"), _anchor("L90")], [fact], source_text=evidence
    )

    assert len(result.accepted) == 1
    retained = result.accepted[0]
    assert retained.data["features"][0]["feature_name_raw"] == "α2-phase fraction"
    assert retained.data["features"][0]["value_raw"] == "12%"
    assert not any(
        issue.code == "promotion_structure_comparative_numeric_projection_quarantined"
        for issue in result.issues
    )


def test_coordinated_owner_ellipsis_preserves_each_shared_projection():
    evidence = (
        "XRD characterization was performed on sintered WA and GA "
        "nickel-based alloy 625 samples."
    )
    facts = [
        _characterization(
            sample="WA nickel-based alloy 625",
            method="XRD",
            evidence=evidence,
        ),
        _characterization(
            sample="GA nickel-based alloy 625",
            method="XRD",
            evidence=evidence,
        ),
    ]

    result = promote_axis_facts(
        [_anchor(fact.sample_id_raw) for fact in facts],
        facts,
        source_text=evidence,
    )

    assert result.accepted == tuple(facts)
    assert result.issues == ()


def test_unique_source_owner_reassigns_wrong_projection_before_deduplication():
    evidence = "Ti-6Al-4V wire was examined by SEM."
    facts = [
        _characterization(sample="Wall 1", evidence=evidence),
        _characterization(sample="Wall 2", evidence=evidence),
    ]

    result = promote_axis_facts(
        [
            _anchor("Ti-6Al-4V wire"),
            _anchor("Wall 1"),
            _anchor("Wall 2"),
        ],
        facts,
        source_text=evidence,
    )

    assert len(result.accepted) == 1
    assert result.accepted[0].sample_id_raw == "Ti-6Al-4V wire"
    assert {issue.code for issue in result.issues} == {
        "promotion_owner_reassigned",
        "promotion_assertion_duplicate_merged",
    }
    reassigned = [
        issue for issue in result.issues if issue.code == "promotion_owner_reassigned"
    ]
    assert len(reassigned) == 2
    assert {issue.actual["before"]["sample_id_raw"] for issue in reassigned} == {
        "Wall 1",
        "Wall 2",
    }
    assert {
        issue.actual["after"]["sample_id_raw"] for issue in reassigned
    } == {"Ti-6Al-4V wire"}


def test_single_letter_anchor_is_not_inferred_from_an_indefinite_article():
    evidence = "A FIB sampling analysis was conducted on Specimen II and Specimen III."
    facts = [
        _characterization(sample="Specimen II", method="FIB", evidence=evidence),
        _characterization(sample="Specimen III", method="FIB", evidence=evidence),
    ]

    result = promote_axis_facts(
        [_anchor("A"), _anchor("Specimen II"), _anchor("Specimen III")],
        facts,
        source_text=evidence,
    )

    assert result.accepted == tuple(facts)
    assert not any(
        issue.code == "promotion_owner_reassigned" for issue in result.issues
    )


def test_characterization_requires_a_source_literal_method_and_merges_aliases():
    source = "A1 was examined by scanning electron microscopy (SEM)."
    facts = [
        _characterization(method="SEM", evidence=source),
        _characterization(method="scanning electron microscopy", evidence=source),
        _characterization(method="TEM", evidence=source),
    ]

    result = promote_axis_facts([_anchor("A1")], facts, source_text=source)

    assert len(result.accepted) == 1
    assert result.accepted[0].data["method_raw"] == (
        "scanning electron microscopy"
    )
    assert {issue.code for issue in result.issues} == {
        "promotion_characterization_alias_merged",
        "promotion_characterization_class_normalized",
        "promotion_characterization_method_unsupported",
    }


def test_generic_characterization_alias_yields_to_specific_cited_method():
    source = "A1 was examined by scanning electron microscopy (SEM)."
    facts = [
        _characterization(method="microscopy", evidence=source),
        _characterization(method="SEM", evidence=source),
    ]

    result = promote_axis_facts([_anchor("A1")], facts, source_text=source)

    assert len(result.accepted) == 1
    assert result.accepted[0].data["method_raw"] == "SEM"
    assert [issue.code for issue in result.issues] == [
        "promotion_characterization_alias_merged"
    ]
    assert result.issues[0].actual["removed"] == facts[0].model_dump()


def test_generic_characterization_class_is_normalized_from_one_explicit_modality():
    source = "A1 was examined by scanning electron microscopy (SEM)."
    fact = _characterization(
        method="SEM", method_class="microscopy", evidence=source
    )

    result = promote_axis_facts([_anchor("A1")], [fact], source_text=source)

    assert len(result.accepted) == 1
    assert result.accepted[0].data["method_raw"] == "SEM"
    assert result.accepted[0].data["method_class"] == "SEM"
    assert [issue.code for issue in result.issues] == [
        "promotion_characterization_class_normalized"
    ]
    issue = result.issues[0]
    assert issue.actual["before"] == fact.model_dump()
    assert issue.actual["after"] == result.accepted[0].model_dump()
    assert issue.actual["reason"] == "single_source_explicit_modality"


def test_multi_modality_characterization_keeps_provider_class_unchanged():
    source = "A1 was examined by combined TEM/STEM imaging."
    fact = _characterization(
        method="TEM/STEM", method_class="microscopy", evidence=source
    )

    result = promote_axis_facts([_anchor("A1")], [fact], source_text=source)

    assert result.accepted == (fact,)
    assert result.issues == ()


def test_specific_characterization_class_alias_is_canonicalized_losslessly():
    source = "A1 was examined by electron backscatter diffraction (EBSD)."
    fact = _characterization(
        method="electron backscatter diffraction (EBSD)",
        method_class="electron_backscatter_diffraction",
        evidence=source,
    )

    result = promote_axis_facts([_anchor("A1")], [fact], source_text=source)

    assert len(result.accepted) == 1
    assert result.accepted[0].data["method_class"] == "EBSD"
    assert [issue.code for issue in result.issues] == [
        "promotion_characterization_class_normalized"
    ]


def test_characterization_accepts_carried_out_measurement_declaration():
    source = (
        "The XRD measurement was carried out using a Bruker D8 instrument."
    )
    fact = _characterization(method="XRD", evidence=source)

    result = promote_axis_facts([_anchor("A1")], [fact], source_text=source)

    assert result.accepted == (fact,)
    assert result.issues == ()


def test_characterization_accepts_method_used_to_acquire_result():
    source = "A1 was examined by SEM, which was used to characterize the powder."
    fact = _characterization(method="SEM", evidence=source)

    result = promote_axis_facts([_anchor("A1")], [fact], source_text=source)

    assert result.accepted == (fact,)
    assert result.issues == ()


def test_high_resolution_characterization_class_is_not_collapsed_to_parent():
    source = "A1 was examined by high-resolution TEM (HRTEM)."
    fact = _characterization(
        method="HRTEM", method_class="HRTEM", evidence=source
    )

    result = promote_axis_facts([_anchor("A1")], [fact], source_text=source)

    assert result.accepted == (fact,)
    assert result.issues == ()


def test_characterization_projection_is_routed_to_named_owner_and_deduplicated():
    source = "Alloy was examined by EBSD."
    facts = [
        _characterization(sample="Alloy", method="EBSD", evidence=source),
        _characterization(sample="Alloy as-built", method="EBSD", evidence=source),
    ]

    result = promote_axis_facts(
        [_anchor("Alloy"), _anchor("Alloy as-built")],
        facts,
        source_text=source,
    )

    assert result.accepted == (facts[0],)
    assert {issue.code for issue in result.issues} == {
        "promotion_owner_reassigned",
        "promotion_assertion_duplicate_merged",
    }
    reassigned = next(
        issue for issue in result.issues if issue.code == "promotion_owner_reassigned"
    )
    assert reassigned.actual["before"] == facts[1].model_dump()
    assert reassigned.actual["after"]["sample_id_raw"] == "Alloy"


def test_characterization_with_ambiguous_material_state_is_quarantined():
    anchors = [
        _anchor("Alloy", material="Alloy", state="as-built"),
        _anchor("Alloy", material="Alloy", state="aged"),
    ]
    source = "Alloy was examined by EBSD."
    fact = _characterization(sample="Alloy", method="EBSD", evidence=source)

    result = promote_axis_facts(anchors, [fact], source_text=source)

    assert result.accepted == ()
    assert [issue.code for issue in result.issues] == [
        "promotion_ambiguous_owner_quarantined"
    ]
    assert result.issues[0].actual["removed"] == fact.model_dump()


def test_wrong_axis_test_control_is_quarantined_but_material_result_survives():
    source = (
        "Tensile tests used a crosshead speed of 1 mm/min. "
        "A1 had a yield strength of 900 MPa."
    )
    control = _property(
        name="crosshead speed",
        value="1",
        unit="mm/min",
        condition="",
        evidence="Tensile tests used a crosshead speed of 1 mm/min.",
    )
    result_fact = _property(
        name="yield strength",
        value="900",
        unit="MPa",
        condition="",
        evidence="A1 had a yield strength of 900 MPa.",
    )

    result = promote_axis_facts(
        [_anchor("A1")], [control, result_fact], source_text=source
    )

    assert result.accepted == (result_fact,)
    assert [issue.code for issue in result.issues] == [
        "property_non_result_quarantined"
    ]
    assert result.issues[0].actual["removed"] == control.model_dump()


def test_characterization_strain_conditions_are_audited_outside_properties():
    mapping = _property(
        name="deformation - strain mapping after tensile strain",
        value="3",
        unit="% strain",
        condition="after tensile strain of 3%",
        evidence=(
            "Strain mapping analysis of grains in A1 after tensile strain of 3%."
        ),
    )
    mapping.data["test_method_raw"] = "HR-EBSD"
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
    strength = _property(
        name="yield strength",
        value="900",
        unit="MPa",
        condition="",
        evidence="A1 had a yield strength of 900 MPa.",
    )
    source = " ".join(
        fact.source_evidence[0] for fact in (mapping, microscopy, strength)
    )

    result = promote_axis_facts(
        [_anchor("A1")], [mapping, microscopy, strength], source_text=source
    )

    assert result.accepted == (strength,)
    assert [issue.code for issue in result.issues] == [
        "property_non_result_quarantined",
        "property_non_result_quarantined",
    ]
    assert [issue.actual["removed"] for issue in result.issues] == [
        mapping.model_dump(),
        microscopy.model_dump(),
    ]
    assert [issue.actual["gate_actual"]["reason"] for issue in result.issues] == [
        "characterization_strain_condition",
        "characterization_strain_condition",
    ]


def test_wrong_axis_process_and_geometry_values_do_not_enter_properties():
    facts = [
        _property(
            name="Melt Pool Width",
            value="10.2",
            unit="mm",
            condition="",
            evidence="The melt pool width was 10.2 mm.",
        ),
        _property(
            name="Cooling Rate",
            value="80",
            unit="K/s",
            condition="",
            evidence="The cooling rate was 80 K/s.",
        ),
    ]
    source = " ".join(fact.source_evidence[0] for fact in facts)

    result = promote_axis_facts([_anchor("A1")], facts, source_text=source)

    assert result.accepted == ()
    assert [issue.code for issue in result.issues] == [
        "property_non_result_quarantined",
        "property_non_result_quarantined",
    ]
    assert [issue.actual["removed"] for issue in result.issues] == [
        fact.model_dump() for fact in facts
    ]


def test_process_energy_density_and_test_temperature_do_not_enter_properties():
    facts = [
        _property(
            name="ED",
            value="4.0",
            unit="J/mm²",
            condition="",
            evidence="The applied ED was 4.0 J/mm².",
        ),
        _property(
            name="creep test",
            value="760",
            unit="°C",
            condition="",
            evidence="The creep test was conducted at 760 °C.",
        ),
    ]
    source = " ".join(fact.source_evidence[0] for fact in facts)

    result = promote_axis_facts([_anchor("A1")], facts, source_text=source)

    assert result.accepted == ()
    assert [issue.code for issue in result.issues] == [
        "property_non_result_quarantined",
        "property_non_result_quarantined",
    ]
    assert [issue.actual["removed"] for issue in result.issues] == [
        fact.model_dump() for fact in facts
    ]


def test_structural_metrics_are_audited_outside_properties_without_broad_geometry_loss():
    structural = [
        ("average fitted ellipse aspect ratio", "2", ""),
        ("average equivalent circle diameter", "37.9", "μm"),
        ("Schmid factor (SF) frequency in range 0.4–0.5", "54.80", "%"),
        ("LAGB fraction", "8.15", "%"),
        ("β₀/B₂ phase content", "4.6", "%"),
        ("volume fraction of DINL", "0.08", "%"),
    ]
    facts = [
        _property(
            name=name,
            value=value,
            unit=unit,
            condition="",
            evidence=f"The {name} was {value} {unit}.",
        )
        for name, value, unit in structural
    ]
    valid = _property(
        name="critical thickness",
        value="0.515",
        unit="mm",
        condition="",
        evidence="The critical thickness was 0.515 mm.",
    )
    source = " ".join(fact.source_evidence[0] for fact in [*facts, valid])

    result = promote_axis_facts(
        [_anchor("A1")], [*facts, valid], source_text=source
    )

    assert result.accepted == (valid,)
    assert [issue.code for issue in result.issues] == [
        "property_non_result_quarantined"
    ] * len(facts)
    assert [issue.actual["removed"] for issue in result.issues] == [
        fact.model_dump() for fact in facts
    ]


def test_wrong_axis_electrochemical_controls_and_measurement_metadata_are_quarantined():
    facts = [
        _property(
            name="cathodic reduction potential",
            value="-0.8",
            unit="V_SCE",
            condition="",
            evidence="An initial cathodic reduction at -0.8 V_SCE was used.",
        ),
        _property(
            name="potentiostatic hold potential",
            value="0.15",
            unit="V_SCE",
            condition="",
            evidence="A potentiostatic hold at 0.15 V_SCE was used.",
        ),
        _property(
            name="crystallographic orientation misorientation",
            value="15",
            unit="degree",
            condition="",
            evidence="The orientation threshold used a 15 degree misorientation.",
        ),
        _property(
            name="pyrometer measurement precision",
            value="5",
            unit="°C",
            condition="",
            evidence="The pyrometer measurement precision was 5 °C.",
        ),
    ]
    source = " ".join(fact.source_evidence[0] for fact in facts)

    result = promote_axis_facts([_anchor("A1")], facts, source_text=source)

    assert result.accepted == ()
    assert [issue.code for issue in result.issues] == [
        "property_non_result_quarantined",
        "property_non_result_quarantined",
        "property_non_result_quarantined",
        "property_non_result_quarantined",
    ]


def test_unbound_property_condition_is_removed_without_dropping_grounded_value():
    evidence = "A1 had a yield strength of 900 MPa."
    fact = _property(condition="650 °C", evidence=evidence)

    result = promote_axis_facts([_anchor("A1")], [fact], source_text=evidence)

    assert len(result.accepted) == 1
    assert result.accepted[0].data["test_condition_raw"] == ""
    assert [issue.code for issue in result.issues] == [
        "promotion_unbound_condition_quarantined"
    ]
    assert result.issues[0].actual["before"]["test_condition_raw"] == "650 °C"
    assert result.issues[0].actual["after"]["test_condition_raw"] == ""


def test_quantified_comparative_tensile_is_quarantined_from_properties():
    evidence = "The aged sample retained 74% of its room-temperature yield strength."
    fact = _property(
        name="yield strength retention",
        value="74",
        unit="%",
        condition="",
        evidence=evidence,
    )

    result = promote_axis_facts([_anchor("A1")], [fact], source_text=evidence)

    assert result.accepted == ()
    assert [issue.code for issue in result.issues] == [
        "promotion_comparative_tensile_quarantined"
    ]
    assert result.issues[0].actual["removed"] == fact.model_dump()


def test_numeric_tensile_difference_is_not_promoted_as_absolute_strength():
    evidence = (
        "The YS of the CL sample exceeds that of the PL sample by 57.3 MPa."
    )
    fact = _property(
        sample="CL",
        name="yield strength",
        value="57.3",
        unit="MPa",
        condition="",
        evidence=evidence,
    )

    result = promote_axis_facts([_anchor("CL")], [fact], source_text=evidence)

    assert result.accepted == ()
    assert "promotion_comparative_tensile_quarantined" in {
        issue.code for issue in result.issues
    }
    assert any(
        issue.actual.get("removed", {}).get("data", {}).get("value_raw") == "57.3"
        for issue in result.issues
        if isinstance(issue.actual, dict)
    )


def test_numeric_tensile_delta_above_named_comparators_is_quarantined():
    evidence = (
        "For the LPBF specimen in the X orientation, yield strength was "
        "0.03 GPa above EPBF and 0.07 GPa above binder jetting."
    )
    fact = _property(
        sample="LPBF / X",
        name="yield strength",
        value="0.03 GPa above EPBF and 0.07 GPa above binder jetting",
        unit="GPa",
        condition="X orientation",
        evidence=evidence,
    )

    result = promote_axis_facts(
        [_anchor("LPBF / X")], [fact], source_text=evidence
    )

    assert result.accepted == ()
    issue = next(
        row
        for row in result.issues
        if row.code == "promotion_property_comparative_projection_quarantined"
    )
    assert issue.actual["reason"] == "relative_core_tensile_delta"
    assert issue.actual["removed"] == fact.model_dump()


def test_absolute_tensile_threshold_above_numeric_value_is_retained():
    evidence = (
        "The LPBF specimen in the X orientation had yield strength above "
        "0.80 GPa."
    )
    fact = _property(
        sample="LPBF / X",
        name="yield strength",
        value="above 0.80",
        unit="GPa",
        condition="X orientation",
        evidence=evidence,
    )

    result = promote_axis_facts(
        [_anchor("LPBF / X")], [fact], source_text=evidence
    )

    assert result.accepted == (fact,)


def test_numeric_tensile_result_after_decreased_to_is_kept():
    evidence = "The YS decreased to 587 MPa after heat treatment of CL."
    fact = _property(
        sample="CL",
        name="yield strength",
        value="587",
        unit="MPa",
        condition="",
        evidence=evidence,
    )

    result = promote_axis_facts([_anchor("CL")], [fact], source_text=evidence)

    assert result.accepted == (fact,)
    assert result.issues == ()


def test_numeric_tensile_attached_to_comparison_target_is_quarantined():
    evidence = (
        "The as-annealed sample achieved 1090 MPa and 3.0 ± 0.14% elongation "
        "compared to the as-built samples."
    )
    fact = _property(
        sample="as-built",
        name="elongation",
        value="3.0 ± 0.14",
        unit="%",
        condition="",
        evidence=evidence,
    )

    result = promote_axis_facts(
        [
            _anchor("as-built", material="AlCoCrFeNi2.1", state="as-built"),
            _anchor("as-annealed", material="AlCoCrFeNi2.1", state="600 °C for 8 h"),
        ],
        [fact],
        source_text=evidence,
    )

    assert result.accepted == ()
    assert [issue.code for issue in result.issues] == [
        "promotion_comparative_owner_projection_quarantined"
    ]
    assert result.issues[0].actual["reason"] == (
        "declared_owner_occurs_after_comparison_cue"
    )
    assert result.issues[0].actual["removed"] == fact.model_dump()


def test_numeric_tensile_subject_before_comparator_is_retained():
    evidence = (
        "The as-built sample had 1388 MPa yield strength compared to the "
        "as-annealed sample."
    )
    fact = _property(
        sample="as-built",
        name="yield strength",
        value="1388",
        unit="MPa",
        condition="",
        evidence=evidence,
    )

    result = promote_axis_facts(
        [
            _anchor("as-built", material="AlCoCrFeNi2.1", state="as-built"),
            _anchor("as-annealed", material="AlCoCrFeNi2.1", state="600 °C for 8 h"),
        ],
        [fact],
        source_text=evidence,
    )

    assert len(result.accepted) == 1
    assert not any(
        issue.code == "promotion_comparative_owner_projection_quarantined"
        for issue in result.issues
    )


def test_generic_comparative_property_is_quarantined_from_properties():
    evidence = (
        "The creep lifetime improvement of H230AM was 672% compared with H230."
    )
    fact = _property(
        sample="H230AM",
        name="creep lifetime improvement",
        value="672%",
        unit="%",
        condition="",
        evidence=evidence,
    )

    result = promote_axis_facts([_anchor("H230AM")], [fact], source_text=evidence)

    assert result.accepted == ()
    assert [issue.code for issue in result.issues] == [
        "promotion_property_comparative_projection_quarantined"
    ]
    assert result.issues[0].actual["reason"] == "comparative_property_name"
    assert result.issues[0].actual["removed"] == fact.model_dump()


def test_strengthening_index_comparison_is_quarantined_from_properties():
    evidence = (
        "Alloy T0 displays stronger solid solution strengthening effect than "
        "CMSX-4 but weaker effect than T5."
    )
    fact = _property(
        sample="T0",
        name="solid solution strengthening index I_SSS",
        value="stronger than CMSX-4 but weaker than T5",
        unit="",
        condition="",
        evidence=evidence,
    )

    result = promote_axis_facts([_anchor("T0")], [fact], source_text=evidence)

    assert result.accepted == ()
    assert any(
        issue.code == "promotion_property_comparative_projection_quarantined"
        for issue in result.issues
    )


def test_qualitative_comparative_value_is_quarantined_even_for_generic_strength():
    """Do not materialize adjective-only strength comparisons as Properties."""

    evidence = (
        "The EBAM material had superior strength and comparable ductility "
        "to the wrought material."
    )
    fact = _property(
        sample="EBAM",
        name="strength",
        value="superior",
        unit="",
        condition="",
        evidence=evidence,
    )

    result = promote_axis_facts([_anchor("EBAM")], [fact], source_text=evidence)

    assert result.accepted == ()
    assert [issue.code for issue in result.issues] == [
        "promotion_property_comparative_projection_quarantined"
    ]
    assert result.issues[0].actual["reason"] == "comparative_value_literal"
    assert result.issues[0].actual["removed"] == fact.model_dump()


def test_process_rate_table_projection_is_quarantined_from_properties():
    header = "| Process | Rate (nm/s) |"
    row = "| Cr diffusion during phase transformation | 0.6 |"
    evidence = [header, row]
    fact = _property(
        sample="A1",
        name="Cr diffusion during phase transformation",
        value="0.6",
        unit="nm/s",
        condition="",
        evidence=header,
    )
    fact.source_evidence = evidence
    fact.data["source_evidence"] = evidence

    result = promote_axis_facts(
        [_anchor("A1")], [fact], source_text="\n".join(evidence)
    )

    assert result.accepted == ()
    assert [issue.code for issue in result.issues] == [
        "promotion_property_comparative_projection_quarantined"
    ]
    assert result.issues[0].actual["reason"] == "non_result_parameter_table"


def test_porosity_count_requires_and_retains_complete_specimen_relation():
    evidence = "Specimens with porosity = 2 of 164; total samples inspected = 164."
    numerator = _structure(
        sample="A1",
        evidence=evidence,
        entities=[],
        features=[
            {
                "feature_name_raw": "specimens with porosity",
                "value_kind": "scalar",
                "value_raw": "2",
                "data_nature": "reported",
            }
        ],
        structure_kind="porosity",
    )
    denominator = _structure(
        sample="A1",
        evidence=evidence,
        entities=[],
        features=[
            {
                "feature_name_raw": "total samples inspected",
                "value_kind": "scalar",
                "value_raw": "164",
                "data_nature": "reported",
            }
        ],
        structure_kind="porosity",
    )

    result = promote_axis_facts(
        [_anchor("A1")], [numerator, denominator], source_text=evidence
    )

    assert len(result.accepted) == 1
    assert result.accepted[0].data["features"][0]["value_raw"] == "2 of 164"
    codes = [issue.code for issue in result.issues]
    assert "promotion_structure_count_relation_completed" in codes
    assert "promotion_structure_count_metadata_quarantined" in codes


def test_fit_parameter_table_and_model_label_do_not_become_properties():
    header = "| Fit parameter | Horizontal sample | Vertical sample |"
    row = "| E (GPa) | 113.8 | 113.5 |"
    fit_fact = _property(
        sample="A1",
        name="E",
        value="113.8",
        unit="GPa",
        condition="",
        evidence=header,
    )
    fit_fact.source_evidence = [header, row]
    fit_fact.data["source_evidence"] = [header, row]
    model_fact = _property(
        sample="A1",
        name="Young/Voigt model",
        value="113.8",
        unit="GPa",
        condition="",
        evidence="Young/Voigt model was used to calculate an elastic modulus.",
    )

    result = promote_axis_facts(
        [_anchor("A1")], [fit_fact, model_fact], source_text="\n".join([header, row])
    )

    assert result.accepted == ()
    assert [issue.code for issue in result.issues] == [
        "promotion_property_metadata_quarantined",
        "promotion_property_metadata_quarantined",
    ]


def test_relative_density_remains_an_absolute_dimensionless_material_result():
    evidence = "The relative density of A1 reached 99.2%."
    fact = _property(
        sample="A1",
        name="relative density",
        value="99.2",
        unit="%",
        condition="",
        evidence=evidence,
    )

    result = promote_axis_facts([_anchor("A1")], [fact], source_text=evidence)

    assert result.accepted == (fact,)
    assert result.issues == ()


def test_absolute_inequality_property_is_not_mistaken_for_a_comparison_projection():
    evidence = "A1 achieved a tensile strength of more than one gigapascal."
    fact = _property(
        sample="A1",
        name="tensile strength",
        value="more than one gigapascal",
        unit="GPa",
        condition="",
        evidence=evidence,
    )

    result = promote_axis_facts([_anchor("A1")], [fact], source_text=evidence)

    assert result.accepted == (fact,)
    assert result.issues == ()


def test_unitless_property_is_quarantined_but_dimensionless_ontology_survives():
    unsupported = _property(
        name="strengthening response",
        value="4.9",
        unit="",
        condition="",
        evidence="A1 had a strengthening response of 4.9.",
    )
    stress_exponent = _property(
        name="stress exponent",
        value="4.9",
        unit="",
        condition="",
        evidence="The stress exponent of A1 was 4.9.",
    )
    source = "A1 had a strengthening response of 4.9. The stress exponent of A1 was 4.9."

    result = promote_axis_facts(
        [_anchor("A1")], [unsupported, stress_exponent], source_text=source
    )

    assert result.accepted == (stress_exponent,)
    assert [issue.code for issue in result.issues] == [
        "promotion_unitless_property_quarantined"
    ]
    assert result.issues[0].actual["removed"] == unsupported.model_dump()


def test_inline_unit_keeps_direct_core_tensile_for_existing_unit_recovery():
    evidence = "A1 had a uniform elongation of 7.2% ± 0.4%."
    fact = _property(
        name="uniform elongation",
        value="7.2% ± 0.4%",
        unit="",
        condition="",
        evidence=evidence,
    )

    result = promote_axis_facts([_anchor("A1")], [fact], source_text=evidence)

    assert result.accepted == (fact,)
    assert result.issues == ()


def test_conflicting_core_tensile_values_from_one_assertion_are_quarantined():
    evidence = "A1 yield strength: 900 or 950 MPa (column identity unclear)."
    facts = [
        _property(value="900", condition="", evidence=evidence),
        _property(value="950", condition="", evidence=evidence),
    ]

    result = promote_axis_facts([_anchor("A1")], facts, source_text=evidence)

    assert result.accepted == ()
    assert len(result.issues) == 2
    assert {issue.code for issue in result.issues} == {
        "promotion_tensile_value_conflict_quarantined"
    }
    assert {issue.actual["removed"]["data"]["value_raw"] for issue in result.issues} == {
        "900",
        "950",
    }


def test_promotion_preserves_original_fact_order_for_materialization_stability():
    yield_evidence = "A1 had a yield strength of 850 MPa."
    uts_evidence = "A1 had an ultimate tensile strength of 900 MPa."
    source = f"{yield_evidence}\n\n{uts_evidence}"
    facts = [
        _property(
            name="ultimate tensile strength",
            value="900",
            condition="",
            evidence=uts_evidence,
        ),
        _property(value="850", condition="", evidence=yield_evidence),
    ]

    result = promote_axis_facts([_anchor("A1")], facts, source_text=source)

    assert [fact.data["property_name_raw"] for fact in result.accepted] == [
        "ultimate tensile strength",
        "yield strength",
    ]


def test_core_tensile_explicit_base_owner_is_retained_without_state_coordinate():
    anchors = [
        _anchor("Alloy A", material="Alloy A", state="as-built"),
        _anchor("Alloy A", material="Alloy A", state="aged"),
    ]
    evidence = "Alloy A had a yield strength of 900 MPa."
    fact = _property(sample="Alloy A", condition="", evidence=evidence)

    result = promote_axis_facts(anchors, [fact], source_text=evidence)

    assert result.accepted == (fact,)
    assert not any(
        issue.code == "promotion_core_tensile_owner_ambiguous_quarantined"
        for issue in result.issues
    )


def test_noncore_property_ambiguity_is_quarantined_without_broadcast():
    anchors = [
        _anchor("Alloy A", material="Alloy A", state="as-built"),
        _anchor("Alloy A", material="Alloy A", state="aged"),
    ]
    evidence = "Alloy A had a hardness of 420 HV."
    fact = _property(
        sample="Alloy A",
        name="hardness",
        value="420",
        unit="HV",
        condition="",
        evidence=evidence,
    )

    result = promote_axis_facts(anchors, [fact], source_text=evidence)

    assert result.accepted == ()
    assert [issue.code for issue in result.issues] == [
        "promotion_ambiguous_owner_quarantined"
    ]


def test_prose_composition_ambiguity_is_quarantined_without_base_owner():
    anchors = [
        _anchor("Alloy A", material="Alloy A", state="as-built"),
        _anchor("Alloy A", material="Alloy A", state="aged"),
    ]
    evidence = "Alloy A contained 2 wt.% TiB2."
    fact = _composition(sample="Alloy A", component="TiB2", value="2", unit="wt.%", evidence=evidence)

    result = promote_axis_facts(anchors, [fact], source_text=evidence)

    assert result.accepted == ()
    assert [issue.code for issue in result.issues] == [
        "promotion_ambiguous_owner_quarantined"
    ]


def test_prose_processing_ambiguity_is_quarantined_without_base_owner():
    anchors = [
        _anchor("Alloy A", material="Alloy A", state="as-built"),
        _anchor("Alloy A", material="Alloy A", state="aged"),
    ]
    evidence = "Alloy A was fabricated by laser powder bed fusion."
    fact = _processing(sample="Alloy A", evidence=evidence)

    result = promote_axis_facts(anchors, [fact], source_text=evidence)

    assert result.accepted == ()
    # Route/event assertions without numeric parameters remain under the
    # existing generic owner gate; the new processing gate only polices
    # state-sensitive parameter projections.
    assert [
        issue.code
        for issue in result.issues
        if issue.code == "promotion_ambiguous_owner_quarantined"
    ] == ["promotion_ambiguous_owner_quarantined"]


def test_quantitative_structure_feature_dominates_redundant_entity_presence():
    evidence = "A1 contained 42% gamma-prime precipitates."
    fact = _structure(
        evidence=evidence,
        entities=[
            {
                "name_raw": "gamma-prime precipitates",
                "entity_type": "precipitate",
                "features": [],
                "raw_expression": "gamma-prime precipitates",
            }
        ],
        features=[
            {
                "feature_name_raw": "gamma-prime precipitate volume fraction",
                "value_kind": "scalar",
                "value_raw": "42%",
                "unit_raw": "%",
                "data_nature": "reported",
            }
        ],
    )

    result = promote_axis_facts([_anchor("A1")], [fact], source_text=evidence)

    assert len(result.accepted) == 1
    assert result.accepted[0].data["entities"] == []
    assert result.accepted[0].data["features"] == fact.data["features"]
    assert [issue.code for issue in result.issues] == [
        "promotion_structure_entity_presence_shadow_quarantined"
    ]
    assert result.issues[0].actual["removed"] == fact.data["entities"][0]
    assert result.issues[0].actual["survivor_after"]["data"]["features"] == (
        fact.data["features"]
    )


def test_structure_entity_is_preserved_without_entity_named_quantitative_feature():
    evidence = "A1 contained gamma-prime precipitates at a volume fraction of 42%."
    fact = _structure(
        evidence=evidence,
        entities=[
            {
                "name_raw": "gamma-prime precipitates",
                "entity_type": "precipitate",
                "features": [],
                "raw_expression": "gamma-prime precipitates",
            }
        ],
        features=[
            {
                "feature_name_raw": "volume fraction",
                "value_kind": "scalar",
                "value_raw": "42%",
                "unit_raw": "%",
                "data_nature": "reported",
            }
        ],
    )

    result = promote_axis_facts([_anchor("A1")], [fact], source_text=evidence)

    assert result.accepted == (fact,)
    assert not any(
        issue.code == "promotion_structure_entity_presence_shadow_quarantined"
        for issue in result.issues
    )


def test_location_only_structure_context_is_quarantined_with_complete_audit():
    evidence = "The observation was made in the top region of A1."
    fact = _structure(
        evidence=evidence,
        entities=[],
        features=[
            {
                "feature_name_raw": "location",
                "value_kind": "categorical",
                "value_raw": "top region",
                "data_nature": "reported",
            }
        ],
    )

    result = promote_axis_facts([_anchor("A1")], [fact], source_text=evidence)

    assert result.accepted == ()
    assert [issue.code for issue in result.issues] == [
        "promotion_structure_context_quarantined"
    ]
    assert result.issues[0].actual["removed"] == fact.model_dump()


def test_reported_morphology_is_not_treated_as_location_only_context():
    evidence = "A1 showed a cellular morphology."
    fact = _structure(
        evidence=evidence,
        entities=[],
        features=[
            {
                "feature_name_raw": "morphology",
                "value_kind": "categorical",
                "value_raw": "cellular morphology",
                "data_nature": "reported",
            }
        ],
    )

    result = promote_axis_facts([_anchor("A1")], [fact], source_text=evidence)

    assert result.accepted == (fact,)
    assert result.issues == ()


def test_adjacent_table_standard_deviation_is_absorbed_into_reported_mean():
    header = "| Density [g/cm^3] | #1 | #2 |"
    mean_row = "| As-sintered | 8.401 | 8.394 |"
    std_row = "| Std. | 0.013 | 0.024 |"
    source = "\n".join([header, mean_row, std_row])
    mean = _property(
        sample="#1",
        name="Density",
        value="8.401",
        unit="g/cm^3",
        condition="",
        evidence=mean_row,
    )
    shadow = _property(
        sample="#1",
        name="Density Std.",
        value="0.013",
        unit="g/cm^3",
        condition="",
        evidence=std_row,
    )
    for fact, row in ((mean, mean_row), (shadow, std_row)):
        fact.source_evidence = [header, row]
        fact.data["source_evidence"] = [header, row]
        fact.data["data_source"] = "table"
        fact.data["material_state"] = "As-sintered"

    result = promote_axis_facts(
        [_anchor("#1")], [mean, shadow], source_text=source
    )

    assert len(result.accepted) == 1
    assert result.accepted[0].data["property_name_raw"] == "Density"
    assert result.accepted[0].data["value_raw"] == "8.401 ± 0.013"
    assert result.accepted[0].source_evidence == [header, mean_row, std_row]
    assert [issue.code for issue in result.issues] == [
        "promotion_property_statistical_shadow_absorbed"
    ]
    assert result.issues[0].actual["removed"] == shadow.model_dump()
    assert result.issues[0].actual["survivor_before"] == mean.model_dump()
    assert (
        result.issues[0].actual["survivor_after"]
        == result.accepted[0].model_dump()
    )


def test_unbound_table_standard_deviation_is_quarantined_not_promoted():
    header = "| Density [g/cm^3] | #1 |"
    std_row = "| Std. | 0.013 |"
    source = "\n".join([header, std_row])
    shadow = _property(
        sample="#1",
        name="Density standard deviation",
        value="0.013",
        unit="g/cm^3",
        condition="",
        evidence=std_row,
    )
    shadow.source_evidence = [header, std_row]
    shadow.data["source_evidence"] = [header, std_row]
    shadow.data["data_source"] = "table"

    result = promote_axis_facts([_anchor("#1")], [shadow], source_text=source)

    assert result.accepted == ()
    assert [issue.code for issue in result.issues] == [
        "promotion_property_statistical_shadow_quarantined"
    ]
    assert result.issues[0].actual["removed"] == shadow.model_dump()


def test_direct_uncertainty_property_is_not_treated_as_statistical_shadow():
    evidence = "A1 density was 8.401 ± 0.013 g/cm^3."
    fact = _property(
        name="Density",
        value="8.401 ± 0.013",
        unit="g/cm^3",
        condition="",
        evidence=evidence,
    )

    result = promote_axis_facts([_anchor("A1")], [fact], source_text=evidence)

    assert result.accepted == (fact,)
    assert result.issues == ()


def test_composition_claim_dominates_same_assertion_property_axis_copy():
    evidence = "A1 contained 47.86 ± 0.5 at.% Al."
    composition = _composition(evidence=evidence)
    copied_property = _property(
        name="Al content",
        value="47.86 ± 0.5",
        unit="at.%",
        condition="",
        evidence="47.86 ± 0.5 at.% Al",
    )

    result = promote_axis_facts(
        [_anchor("A1")],
        [composition, copied_property],
        source_text=evidence,
    )

    assert result.accepted == (composition,)
    assert [issue.code for issue in result.issues] == [
        "promotion_wrong_axis_duplicate_quarantined"
    ]
    assert result.issues[0].actual["removed"] == copied_property.model_dump()
    assert result.issues[0].actual["dominant"] == composition.model_dump()


def test_structure_feature_dominates_same_assertion_property_axis_copy():
    evidence = "A1 had a random grain distribution and maximum texture index of 2.56."
    structure = _structure(
        evidence=evidence,
        entities=[
            {
                "name_raw": "grain distribution",
                "entity_type": "grain",
                "features": [],
                "raw_expression": "grain distribution",
            }
        ],
        features=[
            {
                "feature_name_raw": "texture index",
                "value_kind": "scalar",
                "value_raw": "2.56",
                "unit_raw": "",
                "data_nature": "reported",
            }
        ],
    )
    copied_property = _property(
        name="maximum texture index",
        value="2.56",
        unit="",
        condition="",
        evidence="maximum texture index of 2.56",
    )

    result = promote_axis_facts(
        [_anchor("A1")],
        [structure, copied_property],
        source_text=evidence,
    )

    assert result.accepted == (structure,)
    assert [issue.code for issue in result.issues] == [
        "promotion_wrong_axis_duplicate_quarantined"
    ]
    assert result.issues[0].actual["dominant"] == structure.model_dump()


def test_wrong_axis_property_completes_unitless_structure_before_quarantine():
    evidence = "A1 had recrystallized grains ranging from 10 to 90 \\mum in size."
    structure = _structure(
        evidence=evidence,
        entities=[],
        features=[
            {
                "feature_name_raw": "grain size",
                "value_kind": "range",
                "value_raw": "10 to 90",
                "source_evidence": [evidence],
            }
        ],
        structure_kind="grain_structure",
    )
    property_copy = _property(
        name="grain size",
        value="10 to 90",
        unit="µm",
        condition="",
        evidence=evidence,
    )

    result = promote_axis_facts(
        [_anchor("A1")],
        [structure, property_copy],
        source_text=evidence,
    )

    assert len(result.accepted) == 1
    assert isinstance(result.accepted[0], StructureFact)
    assert result.accepted[0].data["features"][0]["unit_raw"] == "µm"
    issue = next(
        issue
        for issue in result.issues
        if issue.code == "promotion_wrong_axis_structure_unit_completed"
    )
    assert issue.actual["removed"] == property_copy.model_dump()
    assert issue.actual["dominant_before"] == structure.model_dump()
    assert issue.actual["dominant_after"] == result.accepted[0].model_dump()


def test_wrong_axis_structure_unit_completion_rejects_value_conflict():
    evidence = "A1 grains ranged from 10 to 90 \\mum; A1 pores ranged from 20 to 40 \\mum."
    structure = _structure(
        evidence=evidence,
        entities=[],
        features=[
            {
                "feature_name_raw": "grain size",
                "value_kind": "range",
                "value_raw": "10 to 90",
                "source_evidence": [evidence],
            }
        ],
        structure_kind="grain_structure",
    )
    property_fact = _property(
        name="grain size",
        value="20 to 40",
        unit="µm",
        condition="",
        evidence=evidence,
    )

    result = promote_axis_facts(
        [_anchor("A1")],
        [structure, property_fact],
        source_text=evidence,
    )

    assert result.accepted == (structure, property_fact)
    assert not any(
        issue.code == "promotion_wrong_axis_structure_unit_completed"
        for issue in result.issues
    )


def test_cross_axis_claim_with_different_owner_is_preserved():
    evidence = "A1 contained 47.86 ± 0.5 at.% Al; A2 contained the same amount."
    composition = _composition(sample="A1", evidence=evidence)
    property_fact = _property(
        sample="A2",
        name="Al content",
        value="47.86 ± 0.5",
        unit="at.%",
        condition="",
        evidence=evidence,
    )

    result = promote_axis_facts(
        [_anchor("A1"), _anchor("A2")],
        [composition, property_fact],
        source_text=evidence,
    )

    assert result.accepted == (composition, property_fact)
    assert not any(
        issue.code == "promotion_wrong_axis_duplicate_quarantined"
        for issue in result.issues
    )


def test_strict_structure_atomic_subset_is_absorbed_by_richer_observation():
    evidence = "A1 exhibited SISF with W segregation."
    subset = _structure(
        evidence=evidence,
        entities=[
            {
                "name_raw": "SISF",
                "entity_type": "defect",
                "features": [],
                "raw_expression": "SISF",
            }
        ],
        features=[],
    )
    richer = _structure(
        evidence=evidence,
        entities=[
            {
                "name_raw": "SISF",
                "entity_type": "defect",
                "features": [],
                "raw_expression": "SISF",
            },
            {
                "name_raw": "W segregation",
                "entity_type": "segregation",
                "features": [],
                "raw_expression": "W segregation",
            },
        ],
        features=[],
    )

    result = promote_axis_facts(
        [_anchor("A1")], [subset, richer], source_text=evidence
    )

    assert len(result.accepted) == 1
    assert len(result.accepted[0].data["entities"]) == 2
    assert [issue.code for issue in result.issues] == [
        "promotion_richer_assertion_survived"
    ]
    assert result.issues[0].actual["removed"] == subset.model_dump()


def test_structure_subset_from_independent_assertion_is_not_absorbed():
    first_evidence = "A1 exhibited SISF."
    second_evidence = "A later region exhibited SISF with W segregation."
    subset = _structure(evidence=first_evidence)
    subset.data["entities"][0].update(
        {
            "name_raw": "SISF",
            "entity_type": "defect",
            "raw_expression": "SISF",
        }
    )
    richer = _structure(
        evidence=second_evidence,
        entities=[
            {
                "name_raw": "SISF",
                "entity_type": "defect",
                "features": [],
                "raw_expression": "SISF",
            },
            {
                "name_raw": "W segregation",
                "entity_type": "segregation",
                "features": [],
                "raw_expression": "W segregation",
            },
        ],
        features=[],
    )
    source = f"{first_evidence}\n\n{second_evidence}"

    result = promote_axis_facts(
        [_anchor("A1")], [subset, richer], source_text=source
    )

    assert len(result.accepted) == 2
    assert not any(
        issue.code == "promotion_richer_assertion_survived"
        for issue in result.issues
    )


def test_structure_feature_with_unit_absorbs_unitless_same_assertion_shadow():
    evidence = "A1 had recrystallized grains ranging from 10 to 90 \\mum in size."
    unitless = _structure(
        evidence=evidence,
        entities=[],
        features=[
            {
                "feature_name_raw": "grain size",
                "value_kind": "range",
                "value_raw": "10 to 90",
                "source_evidence": [evidence],
            }
        ],
        structure_kind="grain_structure",
        source_type="cited",
    )
    complete = _structure(
        evidence="recrystallized grains ranging from 10 to 90 \\mum in size",
        entities=[],
        features=[
            {
                "feature_name_raw": "grain size",
                "value_kind": "range",
                "value_raw": "10 to 90",
                "unit_raw": "µm",
                "source_evidence": [
                    "recrystallized grains ranging from 10 to 90 \\mum in size"
                ],
            }
        ],
        structure_kind="grain_structure",
        source_type="reported",
    )

    result = promote_axis_facts(
        [_anchor("A1", role="Reference")],
        [unitless, complete],
        source_text=evidence,
    )

    assert len(result.accepted) == 1
    assert result.accepted[0].data["features"][0]["unit_raw"] == "µm"
    issue = next(
        issue
        for issue in result.issues
        if issue.code == "promotion_structure_unit_shadow_merged"
    )
    assert issue.actual["removed"] == unitless.model_dump()
    assert issue.actual["survivor_before"] == complete.model_dump()
    assert issue.actual["survivor_after"] == result.accepted[0].model_dump()


def test_structure_unit_shadow_gate_preserves_distinct_values_and_blocks():
    first_evidence = "A1 grains were 10 to 90 \\mum in size."
    second_evidence = "A later region had grains 20 to 40 \\mum in size."
    first = _structure(
        evidence=first_evidence,
        entities=[],
        features=[
            {
                "feature_name_raw": "grain size",
                "value_kind": "range",
                "value_raw": "10 to 90",
                "source_evidence": [first_evidence],
            }
        ],
        structure_kind="grain_structure",
    )
    second = _structure(
        evidence=second_evidence,
        entities=[],
        features=[
            {
                "feature_name_raw": "grain size",
                "value_kind": "range",
                "value_raw": "20 to 40",
                "unit_raw": "µm",
                "source_evidence": [second_evidence],
            }
        ],
        structure_kind="grain_structure",
    )

    result = promote_axis_facts(
        [_anchor("A1")],
        [first, second],
        source_text=f"{first_evidence}\n\n{second_evidence}",
    )

    assert result.accepted == (first, second)
    assert not any(
        issue.code == "promotion_structure_unit_shadow_merged"
        for issue in result.issues
    )


def test_prose_owner_value_gate_quarantines_swapped_structure_value():
    evidence = (
        "The average grain sizes of H230 and H230AM after heat treatment "
        "were 13.2 µm and 10.9 µm."
    )
    h230_wrong = _structure(
        sample="H230",
        evidence=evidence,
        entities=[],
        features=[
            {
                "feature_name_raw": "average grain size",
                "value_kind": "scalar",
                "value_raw": "10.9",
                "unit_raw": "µm",
                "source_evidence": [evidence],
            }
        ],
        structure_kind="grain_structure",
    )
    h230am_wrong = _structure(
        sample="H230AM",
        evidence=evidence,
        entities=[],
        features=[
            {
                "feature_name_raw": "average grain size",
                "value_kind": "scalar",
                "value_raw": "13.2",
                "unit_raw": "µm",
                "source_evidence": [evidence],
            }
        ],
        structure_kind="grain_structure",
    )

    result = promote_axis_facts(
        [_anchor("H230"), _anchor("H230AM")],
        [h230_wrong, h230am_wrong],
        source_text=evidence,
    )

    assert result.accepted == ()
    issues = [
        issue
        for issue in result.issues
        if issue.code == "promotion_prose_owner_value_mismatch_quarantined"
    ]
    assert len(issues) == 2
    assert {issue.actual["removed"]["sample_id_raw"] for issue in issues} == {
        "H230",
        "H230AM",
    }


def test_prose_owner_value_gate_isolates_unqualified_ordered_pairs():
    evidence = (
        "The average grain sizes of H230 and H230AM after heat treatment "
        "were 13.2 µm and 10.9 µm."
    )
    facts = [
        _structure(
            sample="H230",
            evidence=evidence,
            entities=[],
            features=[
                {
                    "feature_name_raw": "average grain size",
                    "value_kind": "scalar",
                    "value_raw": "13.2",
                    "unit_raw": "µm",
                    "source_evidence": [evidence],
                }
            ],
            structure_kind="grain_structure",
        ),
        _structure(
            sample="H230AM",
            evidence=evidence,
            entities=[],
            features=[
                {
                    "feature_name_raw": "average grain size",
                    "value_kind": "scalar",
                    "value_raw": "10.9",
                    "unit_raw": "µm",
                    "source_evidence": [evidence],
                }
            ],
            structure_kind="grain_structure",
        ),
    ]
    result = promote_axis_facts(
        [_anchor("H230"), _anchor("H230AM")], facts, source_text=evidence
    )
    # The sentence lists two owners and two values, but does not provide a
    # source-local pair or an explicit ``respectively`` mapping.  Order alone
    # is not a safe coordinate for the materializer, so both projections are
    # isolated for audit/review.
    assert result.accepted == ()
    assert sum(
        issue.code == "promotion_source_block_structure_fanout_quarantined"
        for issue in result.issues
    ) == 2


def test_prose_owner_value_gate_does_not_touch_markdown_table_bindings():
    evidence = (
        "| Sample | Grain size (µm) |\n"
        "| H230 | 13.2 |\n"
        "| H230AM | 10.9 |"
    )
    facts = [
        _structure(
            sample="H230",
            evidence=evidence,
            entities=[],
            features=[
                {
                    "feature_name_raw": "grain size",
                    "value_kind": "scalar",
                    "value_raw": "13.2",
                    "unit_raw": "µm",
                    "source_evidence": [evidence],
                }
            ],
            structure_kind="grain_structure",
        ),
        _structure(
            sample="H230AM",
            evidence=evidence,
            entities=[],
            features=[
                {
                    "feature_name_raw": "grain size",
                    "value_kind": "scalar",
                    "value_raw": "10.9",
                    "unit_raw": "µm",
                    "source_evidence": [evidence],
                }
            ],
            structure_kind="grain_structure",
        ),
    ]

    result = promote_axis_facts(
        [_anchor("H230"), _anchor("H230AM")],
        facts,
        source_text=evidence,
    )

    assert result.accepted == tuple(facts)
    assert not any(
        issue.code == "promotion_prose_owner_value_mismatch_quarantined"
        for issue in result.issues
    )


def _porosity_property(
    *,
    sample: str,
    value: str,
    evidence: str,
    method: str = "",
    condition: str = "",
) -> PropertyFact:
    fact = _property(
        sample=sample,
        name="porosity",
        value=value,
        unit="%",
        condition=condition,
        evidence=evidence,
    )
    fact.data["test_method_raw"] = method
    fact.data["data_source"] = "table" if evidence.lstrip().startswith("|") else "text"
    return fact


def test_same_numbered_table_prose_property_duplicate_keeps_richer_prose():
    prose = "Table 2 indicates that the porosity is 0.27% for CL."
    table_row = "| CL | 17,411 | 0.27% | 352,904 |"
    source = f"""
{prose}

Table 2. Porosity size and distribution in the alloys.

| Sample | Quantity | Porosity | Maximum size (µm3) |
| --- | --- | --- | --- |
{table_row}
| PL | 4068 | 0.21% | 405,469 |
"""
    table_fact = _porosity_property(
        sample="CL", value="0.27%", evidence=table_row
    )
    prose_fact = _porosity_property(
        sample="CL", value="0.27%", evidence=prose, method="CT"
    )

    result = promote_axis_facts(
        [_anchor("CL"), _anchor("PL")],
        [table_fact, prose_fact],
        source_text=source,
    )

    properties = [
        fact
        for fact in result.accepted
        if isinstance(fact, PropertyFact)
        and fact.data.get("property_name_raw") == "porosity"
    ]
    assert len(properties) == 1
    assert properties[0].data["test_method_raw"] == "CT"
    assert properties[0].source_evidence == [prose, table_row]
    issue = next(
        row
        for row in result.issues
        if row.code == "promotion_same_table_property_duplicate_merged"
    )
    assert issue.actual["removed"] == table_fact.model_dump()
    assert issue.actual["survivor_before"] == prose_fact.model_dump()
    assert issue.actual["survivor_after"] == properties[0].model_dump()
    relation = issue.actual["source_relation"]
    assert relation["table_number"] == "2"
    assert relation["unique_table_coordinate"]["cell"] == "0.27%"
    assert issue.actual["comparison"]["owner_invented"] is False


def test_same_table_property_merge_v201_can_be_disabled_for_shadow_ab(monkeypatch):
    prose = "Table 2 indicates that the porosity is 0.27% for CL."
    table_row = "| CL | 17,411 | 0.27% | 352,904 |"
    source = f"""
{prose}

Table 2. Porosity size and distribution in the alloys.

| Sample | Quantity | Porosity | Maximum size (µm3) |
| --- | --- | --- | --- |
{table_row}
"""
    table_fact = _porosity_property(
        sample="CL", value="0.27%", evidence=table_row
    )
    prose_fact = _porosity_property(
        sample="CL", value="0.27%", evidence=prose, method="CT"
    )
    monkeypatch.setenv(
        "KNOWMAT2_ALPHA25_SAME_TABLE_PROPERTY_MERGE_V201", "0"
    )

    result = promote_axis_facts(
        [_anchor("CL")], [table_fact, prose_fact], source_text=source
    )

    properties = [
        fact for fact in result.accepted if isinstance(fact, PropertyFact)
    ]
    assert len(properties) == 2
    assert not any(
        row.code == "promotion_same_table_property_duplicate_merged"
        for row in result.issues
    )


def test_same_table_wrong_axis_property_copy_keeps_structure_table_carrier():
    prose = "Table 2 indicates that the porosity is 0.27% for CL."
    table_row = "| CL | 17,411 | 0.27% | 352,904 |"
    source = f"""
{prose}

Table 2. Porosity size and distribution in the alloys.

| Sample | Quantity | Porosity | Maximum size (µm3) |
| --- | --- | --- | --- |
{table_row}
"""
    property_fact = _porosity_property(
        sample="CL", value="0.27%", evidence=prose, method="CT"
    )
    structure_fact = _structure(
        sample="CL",
        evidence=table_row,
        entities=[],
        structure_kind="porosity",
        features=[
            {
                "feature_name_raw": "Porosity",
                "value_kind": "scalar",
                "value_raw": "0.27%",
                "data_nature": "reported",
                "source_evidence": [table_row],
            }
        ],
    )

    result = promote_axis_facts(
        [_anchor("CL")],
        [property_fact, structure_fact],
        source_text=source,
    )

    assert not any(isinstance(fact, PropertyFact) for fact in result.accepted)
    survivor = next(
        fact for fact in result.accepted if isinstance(fact, StructureFact)
    )
    assert survivor.source_evidence == [prose, table_row]
    issue = next(
        row
        for row in result.issues
        if row.code
        == "promotion_same_table_wrong_axis_property_duplicate_quarantined"
    )
    assert issue.actual["removed"] == property_fact.model_dump()
    assert issue.actual["survivor_before"] == structure_fact.model_dump()
    assert issue.actual["survivor_after"] == survivor.model_dump()
    assert issue.actual["source_relation"]["table_number"] == "2"
    assert (
        issue.actual["source_relation"]["unique_table_coordinate"]["cell"]
        == "0.27%"
    )
    assert issue.actual["comparison"]["owner_invented"] is False


def test_same_table_wrong_axis_property_copy_requires_unique_explicit_relation(
    monkeypatch,
):
    table_row = "| CL | 0.27% | 0.27% |"
    prose = "The measured porosity was 0.27% for CL."
    source = f"""
{prose}

Table 2. Replicate porosity values.

| Sample | First porosity | Second porosity |
| --- | --- | --- |
{table_row}
"""
    property_fact = _porosity_property(
        sample="CL", value="0.27%", evidence=prose, method="CT"
    )
    structure_fact = _structure(
        sample="CL",
        evidence=table_row,
        entities=[],
        structure_kind="porosity",
        features=[
            {
                "feature_name_raw": "Porosity",
                "value_kind": "scalar",
                "value_raw": "0.27%",
                "data_nature": "reported",
                "source_evidence": [table_row],
            }
        ],
    )

    implicit = promote_axis_facts(
        [_anchor("CL")],
        [property_fact, structure_fact],
        source_text=source,
    )
    assert property_fact in implicit.accepted
    assert not any(
        row.code
        == "promotion_same_table_wrong_axis_property_duplicate_quarantined"
        for row in implicit.issues
    )

    cited = property_fact.model_copy(
        deep=True,
        update={
            "source_evidence": ["Table 2 reports porosity of 0.27% for CL."],
            "data": {
                **property_fact.data,
                "source_evidence": [
                    "Table 2 reports porosity of 0.27% for CL."
                ],
            },
        },
    )
    cited_source = source.replace(prose, cited.source_evidence[0])
    multiple_cells = promote_axis_facts(
        [_anchor("CL")],
        [cited, structure_fact],
        source_text=cited_source,
    )
    assert cited in multiple_cells.accepted
    assert not any(
        row.code
        == "promotion_same_table_wrong_axis_property_duplicate_quarantined"
        for row in multiple_cells.issues
    )

    unique_source = cited_source.replace(table_row, "| CL | 0.27% | 1.4% |")
    unique_structure = structure_fact.model_copy(
        deep=True,
        update={
            "source_evidence": ["| CL | 0.27% | 1.4% |"],
            "data": {
                **structure_fact.data,
                "source_evidence": ["| CL | 0.27% | 1.4% |"],
            },
        },
    )
    monkeypatch.setenv(
        "KNOWMAT2_ALPHA25_SAME_TABLE_PROPERTY_MERGE_V201", "0"
    )
    disabled = promote_axis_facts(
        [_anchor("CL")],
        [cited, unique_structure],
        source_text=unique_source,
    )
    assert cited in disabled.accepted
    assert not any(
        row.code
        == "promotion_same_table_wrong_axis_property_duplicate_quarantined"
        for row in disabled.issues
    )


def test_same_table_property_merge_requires_exact_value_and_explicit_citation():
    table_row = "| CL | 17,411 | 0.27% | 352,904 |"
    source = f"""
The measured porosity was 0.28% for CL.

Table 2. Porosity size and distribution in the alloys.

| Sample | Quantity | Porosity | Maximum size (µm3) |
| --- | --- | --- | --- |
{table_row}
"""
    table_fact = _porosity_property(
        sample="CL", value="0.27%", evidence=table_row
    )
    prose_fact = _porosity_property(
        sample="CL",
        value="0.28%",
        evidence="The measured porosity was 0.28% for CL.",
        method="CT",
    )

    result = promote_axis_facts(
        [_anchor("CL")], [table_fact, prose_fact], source_text=source
    )

    assert table_fact in result.accepted
    assert prose_fact in result.accepted
    assert not any(
        row.code == "promotion_same_table_property_duplicate_merged"
        for row in result.issues
    )


def test_same_table_property_merge_noops_on_condition_conflict_or_equal_richness():
    prose = "Table 2 indicates that the porosity is 0.27% for CL."
    table_row = "| CL | 17,411 | 0.27% | 352,904 |"
    source = f"""
{prose}

Table 2. Porosity size and distribution in the alloys.

| Sample | Quantity | Porosity | Maximum size (µm3) |
| --- | --- | --- | --- |
{table_row}
"""
    table_fact = _porosity_property(
        sample="CL",
        value="0.27%",
        evidence=table_row,
        method="CT",
        condition="as-built",
    )
    prose_fact = _porosity_property(
        sample="CL",
        value="0.27%",
        evidence=prose,
        method="CT",
        condition="after HIP",
    )

    conflicted = promote_axis_facts(
        [_anchor("CL")], [table_fact, prose_fact], source_text=source
    )
    assert not any(
        row.code == "promotion_same_table_property_duplicate_merged"
        for row in conflicted.issues
    )

    table_fact.data["test_condition_raw"] = ""
    prose_fact.data["test_condition_raw"] = ""
    equal = promote_axis_facts(
        [_anchor("CL")], [table_fact, prose_fact], source_text=source
    )
    assert not any(
        row.code == "promotion_same_table_property_duplicate_merged"
        for row in equal.issues
    )


def test_same_table_property_merge_never_touches_core_tensile():
    prose = "Table 2 reports a yield strength of 900 MPa for A1."
    table_row = "| A1 | 900 MPa |"
    source = f"""
{prose}

Table 2. Tensile properties.

| Sample | Yield strength |
| --- | --- |
{table_row}
"""
    table_fact = _property(
        sample="A1", value="900", evidence=table_row, condition=""
    )
    prose_fact = _property(
        sample="A1", value="900", evidence=prose, condition=""
    )

    result = promote_axis_facts(
        [_anchor("A1")], [table_fact, prose_fact], source_text=source
    )

    assert not any(
        row.code == "promotion_same_table_property_duplicate_merged"
        for row in result.issues
    )


def test_same_table_property_merge_is_permutation_invariant():
    prose = "Table 2 indicates that the porosity is 0.27% for CL."
    table_row = "| CL | 17,411 | 0.27% | 352,904 |"
    source = f"""
{prose}

Table 2. Porosity size and distribution in the alloys.

| Sample | Quantity | Porosity | Maximum size (µm3) |
| --- | --- | --- | --- |
{table_row}
"""
    table_fact = _porosity_property(
        sample="CL", value="0.27%", evidence=table_row
    )
    prose_fact = _porosity_property(
        sample="CL", value="0.27%", evidence=prose, method="CT"
    )

    forward = promote_axis_facts(
        [_anchor("CL")], [table_fact, prose_fact], source_text=source
    )
    reverse = promote_axis_facts(
        [_anchor("CL")], [prose_fact, table_fact], source_text=source
    )

    assert [fact.model_dump() for fact in forward.accepted] == [
        fact.model_dump() for fact in reverse.accepted
    ]
    forward_issue = next(
        row
        for row in forward.issues
        if row.code == "promotion_same_table_property_duplicate_merged"
    )
    reverse_issue = next(
        row
        for row in reverse.issues
        if row.code == "promotion_same_table_property_duplicate_merged"
    )
    assert forward_issue.to_dict() == reverse_issue.to_dict()


def test_same_table_property_merge_noops_for_multiple_value_cells_or_independent_measurement():
    table_row = "| CL | 0.27% | 0.27% |"
    prose = (
        "Table 2 is cited, but an independently measured porosity of 0.27% "
        "was obtained for CL."
    )
    source = f"""
{prose}

Table 2. Replicate porosity values.

| Sample | First porosity | Second porosity |
| --- | --- | --- |
{table_row}
"""
    table_fact = _porosity_property(
        sample="CL", value="0.27%", evidence=table_row
    )
    prose_fact = _porosity_property(
        sample="CL", value="0.27%", evidence=prose, method="CT"
    )

    result = promote_axis_facts(
        [_anchor("CL")], [table_fact, prose_fact], source_text=source
    )

    assert not any(
        row.code == "promotion_same_table_property_duplicate_merged"
        for row in result.issues
    )


def test_prose_owner_value_gate_quarantines_swapped_core_tensile_values():
    evidence = "The yield strengths of A1 and A2 were 900 MPa and 800 MPa."
    facts = [
        _property(
            sample="A1",
            name="yield strength",
            value="800",
            unit="MPa",
            condition="",
            evidence=evidence,
        ),
        _property(
            sample="A2",
            name="yield strength",
            value="900",
            unit="MPa",
            condition="",
            evidence=evidence,
        ),
    ]

    result = promote_axis_facts(
        [_anchor("A1"), _anchor("A2")], facts, source_text=evidence
    )

    assert result.accepted == ()
    issues = [
        issue
        for issue in result.issues
        if issue.code == "promotion_prose_owner_value_mismatch_quarantined"
    ]
    assert len(issues) == 2
    assert {issue.actual["removed"]["sample_id_raw"] for issue in issues} == {
        "A1",
        "A2",
    }


def test_prose_owner_value_gate_preserves_ordered_core_tensile_values():
    evidence = "The yield strengths of A1 and A2 were 900 MPa and 800 MPa."
    facts = [
        _property(
            sample="A1",
            name="yield strength",
            value="900",
            unit="MPa",
            condition="",
            evidence=evidence,
        ),
        _property(
            sample="A2",
            name="yield strength",
            value="800",
            unit="MPa",
            condition="",
            evidence=evidence,
        ),
    ]

    result = promote_axis_facts(
        [_anchor("A1"), _anchor("A2")], facts, source_text=evidence
    )

    assert result.accepted == tuple(facts)
    assert not any(
        issue.code == "promotion_prose_owner_value_mismatch_quarantined"
        for issue in result.issues
    )


def test_condition_label_is_bound_only_when_source_literal_and_discriminative():
    evidence = "The yield strength at 800 °C was 900 MPa."
    fact = _property(
        sample="A1",
        value="900",
        condition="",
        evidence=evidence,
    )
    fact.data["condition_label_raw"] = "800 °C"

    result = promote_axis_facts([_anchor("A1")], [fact], source_text=evidence)

    assert len(result.accepted) == 1
    assert result.accepted[0].data["test_condition_raw"] == "800 °C"
    assert any(issue.code == "promotion_condition_label_bound" for issue in result.issues)


def test_condition_label_routes_generic_fact_to_existing_state_owner():
    evidence = (
        "The hardness values for 0 s delay and 300 s delay were 334 HV and "
        "346 HV, respectively."
    )
    facts = [
        _property(
            sample="Ti_{64}",
            name="Vickers microhardness",
            value="334",
            unit="HV",
            condition="",
            evidence=evidence,
        ),
        _property(
            sample="Ti_{64}",
            name="Vickers microhardness",
            value="346",
            unit="HV",
            condition="",
            evidence=evidence,
        ),
    ]
    facts[0].data["condition_label_raw"] = "0 s delay"
    facts[1].data["condition_label_raw"] = "300 s delay"
    anchors = [
        _anchor("Ti_{64}", material="Ti_{64}"),
        _anchor("0 s Delay", material="Ti_{64}", state="0 s Delay"),
        _anchor("300 s Delay", material="Ti_{64}", state="300 s Delay"),
    ]

    result = promote_axis_facts(anchors, facts, source_text=evidence)

    assert [row.sample_id_raw for row in result.accepted] == [
        "0 s Delay",
        "300 s Delay",
    ]
    assert all(row.data["test_condition_raw"] for row in result.accepted)
    assert sum(
        issue.code == "promotion_condition_owner_reassigned"
        for issue in result.issues
    ) == 2


def test_condition_route_does_not_use_same_material_as_lineage_when_owner_is_explicit():
    evidence = "A1 had a hardness of 334 HV after HIPed treatment."
    fact = _property(
        sample="A1",
        name="Vickers microhardness",
        value="334",
        unit="HV",
        condition="HIPed",
        evidence=evidence,
    )
    result = promote_axis_facts(
        [
            _anchor("A1", material="Ti-6Al-4V"),
            _anchor("A2", material="Ti-6Al-4V", state="HIPed"),
        ],
        [fact],
        source_text=evidence,
    )

    assert len(result.accepted) == 1
    assert result.accepted[0].sample_id_raw == "A1"
    assert not any(
        issue.code == "promotion_condition_owner_reassigned"
        for issue in result.issues
    )


def test_bare_condition_cannot_jump_between_same_material_sample_ids():
    evidence = "The hardness under HIPed treatment was 334 HV."
    fact = _property(
        sample="A1",
        name="Vickers microhardness",
        value="334",
        unit="HV",
        condition="HIPed",
        evidence=evidence,
    )
    result = promote_axis_facts(
        [
            _anchor("A1", material="Ti-6Al-4V"),
            _anchor("A2", material="Ti-6Al-4V", state="HIPed"),
        ],
        [fact],
        source_text=evidence,
    )

    assert len(result.accepted) == 1
    assert result.accepted[0].sample_id_raw == "A1"
    assert not any(
        issue.code == "promotion_condition_owner_reassigned"
        for issue in result.issues
    )


def test_condition_route_keeps_explicit_sample_lineage_for_bracketed_state():
    evidence = "A [HIPed] had a hardness of 334 HV at 800 °C."
    fact = _property(
        sample="A",
        name="Vickers microhardness",
        value="334",
        unit="HV",
        condition="HIPed",
        evidence=evidence,
    )
    result = promote_axis_facts(
        [
            _anchor("A", material="Alloy A"),
            _anchor("A [HIPed]", material="Alloy A", state="HIPed"),
        ],
        [fact],
        source_text=evidence,
    )

    assert len(result.accepted) == 1
    assert result.accepted[0].sample_id_raw == "A [HIPed]"


def test_long_method_condition_is_reduced_to_source_literal_coordinates():
    evidence = (
        "A1 had a yield strength of 900 MPa at 800 °C. "
        "Dog-bone specimens with a 5 mm gauge length were tested on an Instron "
        "machine at a strain rate of 5 × 10^-3 s^-1; tests were repeated three times."
    )
    fact = _property(
        sample="A1",
        name="yield strength",
        value="900",
        unit="MPa",
        condition=(
            "A1 had a yield strength of 900 MPa at 800 °C. Dog-bone specimens "
            "with a 5 mm gauge length were tested on an Instron "
            "machine at a strain rate of 5 × 10^-3 s^-1; tests were repeated three times."
        ),
        evidence=evidence,
    )

    result = promote_axis_facts([_anchor("A1")], [fact], source_text=evidence)

    assert len(result.accepted) == 1
    condition = result.accepted[0].data["test_condition_raw"]
    assert "800" in condition
    assert "°C" in condition
    assert "strain rate" not in condition.lower()
    assert "Instron" not in condition
    assert "gauge length" not in condition
    issue = next(
        issue
        for issue in result.issues
        if issue.code == "promotion_condition_method_context_trimmed"
    )
    assert issue.actual["before"] == fact.model_dump()
    assert issue.actual["after"] == result.accepted[0].model_dump()


def test_long_method_condition_without_coordinate_is_cleared_but_value_survives():
    evidence = (
        "A1 had a yield strength of 900 MPa. Dog-bone specimens were polished, "
        "mounted, and tested on an Instron machine; measurements were repeated "
        "three times for reproducibility."
    )
    fact = _property(
        sample="A1",
        name="yield strength",
        value="900",
        unit="MPa",
        condition=(
            "Dog-bone specimens were polished, mounted, and tested on an Instron "
            "machine; measurements were repeated three times for reproducibility."
        ),
        evidence=evidence,
    )

    result = promote_axis_facts([_anchor("A1")], [fact], source_text=evidence)

    assert len(result.accepted) == 1
    assert result.accepted[0].data["value_raw"] == "900"
    assert result.accepted[0].data["test_condition_raw"] == ""
    assert any(
        issue.code == "promotion_condition_method_context_trimmed"
        and issue.actual["reason"] == "no_source_literal_coordinate_survived"
        for issue in result.issues
    )


def test_v205_locator_only_condition_is_removed_without_dropping_property():
    evidence = (
        "A1 had a yield strength of 900 MPa. The result is listed in Table 3."
    )
    fact = _property(
        sample="A1",
        value="900",
        condition="Table 3",
        evidence=evidence,
    )

    result = promote_axis_facts([_anchor("A1")], [fact], source_text=evidence)

    assert len(result.accepted) == 1
    assert result.accepted[0].data["test_condition_raw"] == ""
    issue = next(
        row
        for row in result.issues
        if row.code == "property_provenance_locator_removed_from_condition"
    )
    assert issue.actual["before"] == fact.model_dump()
    assert issue.actual["after"] == result.accepted[0].model_dump()
    assert issue.actual["removed_locators"] == ["Table 3"]
    assert issue.actual["decision_key"].startswith("property-condition-v205:")


def test_v205_locator_and_duplicate_condition_segments_preserve_science():
    evidence = (
        "At room temperature, A1 had a yield strength of 900 MPa; the result "
        "is summarized in Table 3."
    )
    fact = _property(
        sample="A1",
        value="900",
        condition="room temperature | Table 3 | room temperature",
        evidence=evidence,
    )

    result = promote_axis_facts([_anchor("A1")], [fact], source_text=evidence)

    assert len(result.accepted) == 1
    assert result.accepted[0].data["test_condition_raw"] == "room temperature"
    codes = [row.code for row in result.issues]
    assert "property_provenance_locator_removed_from_condition" in codes
    assert "property_condition_duplicate_segment_removed" in codes
    assert all(
        row.actual["decision_key"].startswith("property-condition-v205:")
        for row in result.issues
        if row.code
        in {
            "property_provenance_locator_removed_from_condition",
            "property_condition_duplicate_segment_removed",
        }
    )


def test_v205_placeholder_and_method_only_condition_segments_are_removed():
    evidence = "A1 had a yield strength of 900 MPa in a tensile test."
    fact = _property(
        sample="A1",
        value="900",
        condition=(
            "not_reported | not_reported | Method: tensile test; "
            "Condition: not_reported"
        ),
        evidence=evidence,
    )

    result = promote_axis_facts([_anchor("A1")], [fact], source_text=evidence)

    assert len(result.accepted) == 1
    assert result.accepted[0].data["test_condition_raw"] == ""
    issue = next(
        row
        for row in result.issues
        if row.code == "property_condition_placeholder_removed"
    )
    assert issue.actual["before"] == fact.model_dump()
    assert issue.actual["after"] == result.accepted[0].model_dump()
    assert issue.actual["removed_segments"] == [
        "not_reported",
        "not_reported",
        "Method: tensile test",
        "Condition: not_reported",
    ]
    assert issue.actual["decision_key"].startswith("property-condition-v205:")


def test_v205_single_placeholder_condition_is_audited_and_cleared():
    evidence = "A1 had a yield strength of 900 MPa."
    fact = _property(
        sample="A1",
        value="900",
        condition="not_reported",
        evidence=evidence,
    )

    result = promote_axis_facts([_anchor("A1")], [fact], source_text=evidence)

    assert len(result.accepted) == 1
    assert result.accepted[0].data["test_condition_raw"] == ""
    issue = next(
        row
        for row in result.issues
        if row.code == "property_condition_placeholder_removed"
    )
    assert issue.actual["removed_segments"] == ["not_reported"]


def test_v205_placeholder_cleanup_preserves_scientific_condition_segments():
    evidence = (
        "At 650 °C and a strain rate of 1e-3 s^-1, A1 had a yield strength "
        "of 700 MPa in a tensile test."
    )
    fact = _property(
        sample="A1",
        value="700",
        condition=(
            "Method: tensile test | Condition: not_reported | 650 °C | "
            "strain rate of 1e-3 s^-1"
        ),
        evidence=evidence,
    )

    result = promote_axis_facts([_anchor("A1")], [fact], source_text=evidence)

    assert len(result.accepted) == 1
    assert result.accepted[0].data["test_condition_raw"] == (
        "650 °C; strain rate of 1e-3 s^-1"
    )
    assert any(
        row.code == "property_condition_placeholder_removed"
        for row in result.issues
    )


def test_v205_condition_separation_preserves_distinct_scientific_dimensions():
    evidence = (
        "At room temperature and a strain rate of 1e-3 s^-1, the A1 specimen "
        "in the vertical direction had a yield strength of 900 MPa, as "
        "reported in Fig. 8."
    )
    fact = _property(
        sample="A1",
        value="900",
        condition=(
            "room temperature; strain rate of 1e-3 s^-1; vertical direction; "
            "Fig. 8"
        ),
        evidence=evidence,
    )

    result = promote_axis_facts([_anchor("A1")], [fact], source_text=evidence)

    assert len(result.accepted) == 1
    condition = result.accepted[0].data["test_condition_raw"]
    assert condition == (
        "room temperature; strain rate of 1e-3 s^-1; vertical direction"
    )
    assert any(
        row.code == "property_provenance_locator_removed_from_condition"
        for row in result.issues
    )


def test_v205_condition_separation_switch_off_restores_v204_locator(
    monkeypatch,
):
    monkeypatch.setenv(
        "KNOWMAT2_ALPHA25_PROPERTY_PROVENANCE_CONDITION_SEPARATION_V205", "0"
    )
    evidence = (
        "A1 had a yield strength of 900 MPa. The result is listed in Table 3."
    )
    fact = _property(
        sample="A1",
        value="900",
        condition="Table 3",
        evidence=evidence,
    )

    result = promote_axis_facts([_anchor("A1")], [fact], source_text=evidence)

    assert len(result.accepted) == 1
    assert result.accepted[0].data["test_condition_raw"] == "Table 3"
    assert not any(
        row.code.startswith("property_provenance_")
        or row.code.startswith("property_condition_duplicate_")
        for row in result.issues
    )


def test_ambiguous_respectively_values_with_one_metric_are_quarantined():
    evidence = "The fracture-location ranges were 1.10 and 0.96 mm, respectively."
    facts = [
        _property(
            sample="Ti-6Al-4V",
            name="fracture location variation range",
            value="1.10",
            unit="mm",
            condition="",
            evidence=evidence,
        ),
        _property(
            sample="Ti-6Al-4V",
            name="fracture location variation range",
            value="0.96",
            unit="mm",
            condition="",
            evidence=evidence,
        ),
    ]

    result = promote_axis_facts([_anchor("Ti-6Al-4V")], facts, source_text=evidence)

    assert result.accepted == ()
    assert sum(
        issue.code == "promotion_respectively_mapping_ambiguous_quarantined"
        for issue in result.issues
    ) == 2


def test_same_metric_prose_value_fanout_without_coordinate_is_quarantined():
    evidence = (
        "The introduction of a 300 s delay led to an approximately 4% increase "
        "in hardness, with values rising from 334 HV to 346 HV."
    )
    facts = [
        _property(
            sample="Ti64",
            name="Vickers microhardness",
            value="334",
            unit="HV",
            condition="",
            evidence=evidence,
        ),
        _property(
            sample="Ti64",
            name="Vickers microhardness",
            value="346",
            unit="HV",
            condition="",
            evidence=evidence,
        ),
    ]

    result = promote_axis_facts([_anchor("Ti64")], facts, source_text=evidence)

    assert result.accepted == ()
    issues = [
        issue
        for issue in result.issues
        if issue.code == "promotion_property_value_fanout_ambiguous_quarantined"
    ]
    assert len(issues) == 2
    assert all(issue.actual["removed"] for issue in issues)


def test_cross_chunk_same_metric_fanout_is_quarantined_by_shared_prose_block():
    source = (
        "A1 showed hardness of 334 HV in one condition, while another condition "
        "showed hardness of 346 HV after testing."
    )
    facts = [
        _property(
            sample="A1",
            name="Vickers microhardness",
            value="334",
            unit="HV",
            condition="",
            evidence="A1 showed hardness of 334 HV in one condition",
        ),
        _property(
            sample="A1",
            name="Vickers microhardness",
            value="346",
            unit="HV",
            condition="",
            evidence="hardness of 346 HV after testing",
        ),
    ]

    result = promote_axis_facts([_anchor("A1")], facts, source_text=source)

    assert result.accepted == ()
    issues = [
        issue
        for issue in result.issues
        if issue.code == "promotion_source_block_property_fanout_quarantined"
    ]
    assert len(issues) == 2
    assert all(issue.actual["source_block"]["start_line"] == 1 for issue in issues)


def test_cross_chunk_same_value_non_core_property_fanout_is_quarantined():
    """A same-valued copy across owners is still an unbound projection."""

    source = (
        "A1 and A2 were evaluated under different conditions; the reported "
        "Vickers microhardness was 334 HV."
    )
    facts = [
        _property(
            sample="A1",
            name="Vickers microhardness",
            value="334",
            unit="HV",
            condition="",
            evidence="the reported Vickers microhardness was 334 HV",
            evidence_unit_id="prose-L000001-L000001-a1",
        ),
        _property(
            sample="A2",
            name="Vickers microhardness",
            value="334",
            unit="HV",
            condition="",
            evidence="Vickers microhardness was 334 HV",
            evidence_unit_id="prose-L000001-L000001-a2",
        ),
    ]

    result = promote_axis_facts(
        [_anchor("A1"), _anchor("A2")], facts, source_text=source
    )

    assert result.accepted == ()
    issues = [
        issue
        for issue in result.issues
        if issue.code == "promotion_source_block_property_same_value_fanout_quarantined"
    ]
    assert len(issues) == 2


def test_cross_chunk_same_value_core_tensile_same_owner_is_quarantined_by_source_block():
    """A repeated scalar under one owner is still isolated when evidence differs."""

    source = (
        "The sample had a yield strength of 900 MPa. The same sample was "
        "reported with a yield strength of 900 MPa."
    )
    facts = [
        _property(
            sample="A1",
            name="yield strength",
            value="900",
            unit="MPa",
            condition="",
            evidence="The sample had a yield strength of 900 MPa.",
        ),
        _property(
            sample="A1",
            name="yield strength",
            value="900",
            unit="MPa",
            condition="",
            evidence="same sample was reported with a yield strength of 900 MPa.",
        ),
    ]

    result = promote_axis_facts([_anchor("A1")], facts, source_text=source)

    assert result.accepted == ()
    issues = [
        issue
        for issue in result.issues
        if issue.code == "promotion_source_block_property_same_value_fanout_quarantined"
    ]
    assert len(issues) == 2
    assert all(issue.actual["same_value"] is True for issue in issues)
    assert all(issue.actual["conflict_set"] for issue in issues)


def test_cross_chunk_same_value_core_tensile_is_quarantined_without_coordinate():
    """An unqualified same-value core-tensile broadcast is not safe."""

    source = (
        "A1 and A2 were evaluated under different conditions; the reported "
        "yield strength was 900 MPa."
    )
    facts = [
        _property(
            sample="A1",
            name="yield strength",
            value="900",
            unit="MPa",
            condition="",
            evidence="the reported yield strength was 900 MPa",
            evidence_unit_id="prose-L000001-L000001-a1",
        ),
        _property(
            sample="A2",
            name="yield strength",
            value="900",
            unit="MPa",
            condition="",
            evidence="yield strength was 900 MPa",
            evidence_unit_id="prose-L000001-L000001-a2",
        ),
    ]

    result = promote_axis_facts(
        [_anchor("A1"), _anchor("A2")], facts, source_text=source
    )

    assert result.accepted == ()
    issues = [
        issue
        for issue in result.issues
        if issue.code == "promotion_core_tensile_owner_ambiguous_quarantined"
    ]
    assert len(issues) == 2


def test_cross_chunk_fanout_preserves_explicit_owner_pairs():
    source = "A1 had hardness of 334 HV, while A2 had hardness of 346 HV."
    facts = [
        _property(
            sample="A1",
            name="Vickers microhardness",
            value="334",
            condition="",
            evidence="A1 had hardness of 334 HV",
        ),
        _property(
            sample="A2",
            name="Vickers microhardness",
            value="346",
            condition="",
            evidence="A2 had hardness of 346 HV",
        ),
    ]

    result = promote_axis_facts(
        [_anchor("A1"), _anchor("A2")], facts, source_text=source
    )

    assert len(result.accepted) == 2
    assert not any(
        issue.code == "promotion_source_block_property_fanout_quarantined"
        for issue in result.issues
    )


def test_cross_chunk_tensile_fanout_preserves_direct_and_physical_owner_envelope():
    source = (
        "AP-Alloy had a yield strength (YS) of 548 MPa. Subsequent thermal "
        "treatment gives a YS of 748 MPa. This superior performance belongs "
        "to HT-Alloy."
    )
    facts = [
        _property(
            sample="AP-Alloy",
            name="YS",
            value="548",
            unit="MPa",
            condition="",
            evidence="AP-Alloy had a yield strength (YS) of 548 MPa",
        ),
        _property(
            sample="HT-Alloy",
            name="YS",
            value="748",
            unit="MPa",
            condition="",
            evidence="Subsequent thermal treatment gives a YS of 748 MPa",
        ),
    ]
    anchors = [
        _anchor("AP-Alloy", material="Alloy", state="as-printed"),
        _anchor(
            "HT-Alloy",
            material="HT-Alloy",
            state="HT",
            evidence="HT-Alloy shows superior mechanical performance.",
        ),
        _anchor(
            "HT-Alloy",
            material="Alloy matrix",
            state="wall region",
            evidence="The HT-Alloy wall region contains the matrix.",
        ),
    ]

    result = promote_axis_facts(anchors, facts, source_text=source)

    assert {
        (row.sample_id_raw, row.data["value_raw"])
        for row in result.accepted
    } == {("AP-Alloy", "548"), ("HT-Alloy", "748")}
    assert not any(
        issue.code == "promotion_source_block_property_fanout_quarantined"
        for issue in result.issues
    )


def test_cross_chunk_tensile_envelope_without_block_owner_still_fails_closed():
    source = (
        "AP-Alloy had a yield strength (YS) of 548 MPa. Subsequent thermal "
        "treatment gives a YS of 748 MPa."
    )
    facts = [
        _property(
            sample="AP-Alloy",
            name="YS",
            value="548",
            unit="MPa",
            condition="",
            evidence="AP-Alloy had a yield strength (YS) of 548 MPa",
        ),
        _property(
            sample="HT-Alloy",
            name="YS",
            value="748",
            unit="MPa",
            condition="",
            evidence="Subsequent thermal treatment gives a YS of 748 MPa",
        ),
    ]
    anchors = [
        _anchor("AP-Alloy", material="Alloy", state="as-printed"),
        _anchor(
            "HT-Alloy",
            material="HT-Alloy",
            state="HT",
            evidence="HT-Alloy shows superior mechanical performance.",
        ),
        _anchor(
            "HT-Alloy",
            material="Alloy matrix",
            state="wall region",
            evidence="The HT-Alloy wall region contains the matrix.",
        ),
    ]

    result = promote_axis_facts(anchors, facts, source_text=source)

    assert result.accepted == ()
    assert sum(
        issue.code == "promotion_source_block_property_fanout_quarantined"
        for issue in result.issues
    ) == 2


def test_cross_chunk_fanout_preserves_distinct_grounded_conditions():
    source = (
        "The hardness at 0 s delay was 334 HV, while at 300 s delay it was 346 HV."
    )
    facts = [
        _property(
            sample="A1",
            name="Vickers microhardness",
            value="334",
            condition="0 s delay",
            evidence="hardness at 0 s delay was 334 HV",
        ),
        _property(
            sample="A1",
            name="Vickers microhardness",
            value="346",
            condition="300 s delay",
            evidence="at 300 s delay it was 346 HV",
        ),
    ]

    result = promote_axis_facts([_anchor("A1")], facts, source_text=source)

    assert len(result.accepted) == 2
    assert not any(
        issue.code == "promotion_source_block_property_fanout_quarantined"
        for issue in result.issues
    )


def test_cross_chunk_fanout_preserves_temperature_state_owner_coordinates():
    source = (
        "The fracture strain increased to 45.0% for the 1290 °C and then "
        "declined to 35.6% for the 1300 °C sample."
    )
    facts = [
        _property(
            sample="1290 °C sample",
            name="fracture strain",
            value="45.0",
            unit="%",
            condition="",
            evidence="The fracture strain increased to 45.0% for the 1290 °C",
        ),
        _property(
            sample="1300 °C sample",
            name="fracture strain",
            value="35.6",
            unit="%",
            condition="",
            evidence="declined to 35.6% for the 1300 °C sample",
        ),
    ]

    result = promote_axis_facts(
        [_anchor("1290 °C sample"), _anchor("1300 °C sample")],
        facts,
        source_text=source,
    )

    assert len(result.accepted) == 2
    assert not any(
        issue.code == "promotion_source_block_property_fanout_quarantined"
        for issue in result.issues
    )


def test_cross_chunk_fanout_does_not_reinterpret_table_or_collective_rows():
    table = "| Sample | Hardness (HV) |\n| --- | --- |\n| A1 | 334 |\n| A2 | 346 |"
    table_facts = [
        _property(sample="A1", name="Vickers microhardness", value="334", condition="", evidence="| A1 | 334 |"),
        _property(sample="A2", name="Vickers microhardness", value="346", condition="", evidence="| A2 | 346 |"),
    ]
    table_result = promote_axis_facts(
        [_anchor("A1"), _anchor("A2")], table_facts, source_text=table
    )
    assert len(table_result.accepted) == 2
    assert not any(
        issue.code == "promotion_source_block_property_fanout_quarantined"
        for issue in table_result.issues
    )

    collective = "Both A1 and A2 showed hardness values of 334 HV and 346 HV."
    collective_facts = [
        _property(sample="A1", name="Vickers microhardness", value="334", condition="", evidence="Both A1 and A2 showed hardness values of 334 HV and 346 HV."),
        _property(sample="A2", name="Vickers microhardness", value="346", condition="", evidence="Both A1 and A2 showed hardness values of 334 HV and 346 HV."),
    ]
    collective_result = promote_axis_facts(
        [_anchor("A1"), _anchor("A2")], collective_facts, source_text=collective
    )
    assert len(collective_result.accepted) == 2
    assert not any(
        issue.code == "promotion_source_block_property_fanout_quarantined"
        for issue in collective_result.issues
    )


def test_cross_chunk_structure_feature_fanout_without_coordinate_is_quarantined():
    source = (
        "A1 showed an average grain size of 10 um in one region, while another "
        "region showed an average grain size of 20 um."
    )
    facts = [
        _structure(
            sample="A1",
            evidence="A1 showed an average grain size of 10 um in one region",
            entities=[],
            features=[
                {
                    "feature_name_raw": "average grain size",
                    "value_kind": "scalar",
                    "value_raw": "10",
                    "unit_raw": "um",
                    "data_nature": "reported",
                    "source_evidence": [
                        "A1 showed an average grain size of 10 um in one region"
                    ],
                }
            ],
        ),
        _structure(
            sample="A1",
            evidence="another region showed an average grain size of 20 um",
            entities=[],
            features=[
                {
                    "feature_name_raw": "average grain size",
                    "value_kind": "scalar",
                    "value_raw": "20",
                    "unit_raw": "um",
                    "data_nature": "reported",
                    "source_evidence": [
                        "another region showed an average grain size of 20 um"
                    ],
                }
            ],
        ),
    ]

    result = promote_axis_facts([_anchor("A1")], facts, source_text=source)

    assert result.accepted == ()
    assert sum(
        issue.code == "promotion_source_block_structure_fanout_quarantined"
        for issue in result.issues
    ) == 2


def test_structure_region_coordinate_gate_is_per_feature_not_sibling_rescue():
    """A bound local feature must not authorize an unbound sibling value."""

    source = (
        "A1 showed an average grain size of 10 um in the top region and "
        "an average grain size of 20 um in another region."
    )
    fact = _structure(
        sample="A1",
        evidence=source,
        entities=[],
        features=[
            {
                "feature_name_raw": "average grain size",
                "value_kind": "scalar",
                "value_raw": "10",
                "unit_raw": "um",
                "region": "top region",
                "data_nature": "reported",
                "source_evidence": ["A1 showed an average grain size of 10 um in the top region"],
            },
            {
                "feature_name_raw": "average grain size",
                "value_kind": "scalar",
                "value_raw": "20",
                "unit_raw": "um",
                "data_nature": "reported",
                "source_evidence": ["an average grain size of 20 um in another region"],
            },
        ],
    )

    result = promote_axis_facts([_anchor("A1")], [fact], source_text=source)

    assert len(result.accepted) == 1
    assert [feature["value_raw"] for feature in result.accepted[0].data["features"]] == [
        "10"
    ]
    issue = next(
        issue
        for issue in result.issues
        if issue.code == "promotion_structure_region_coordinate_missing_quarantined"
    )
    assert issue.actual["removed"]["value_raw"] == "20"
    assert issue.actual["reason"] == "local_region_coordinate_missing"


def test_cross_chunk_structure_feature_fanout_preserves_explicit_owner_pairs():
    source = "A1 showed grain size of 10 um, while A2 showed grain size of 20 um."
    facts = [
        _structure(
            sample="A1",
            evidence="A1 showed grain size of 10 um",
            entities=[],
            features=[
                {
                    "feature_name_raw": "grain size",
                    "value_kind": "scalar",
                    "value_raw": "10",
                    "unit_raw": "um",
                    "data_nature": "reported",
                    "source_evidence": ["A1 showed grain size of 10 um"],
                }
            ],
        ),
        _structure(
            sample="A2",
            evidence="A2 showed grain size of 20 um",
            entities=[],
            features=[
                {
                    "feature_name_raw": "grain size",
                    "value_kind": "scalar",
                    "value_raw": "20",
                    "unit_raw": "um",
                    "data_nature": "reported",
                    "source_evidence": ["A2 showed grain size of 20 um"],
                }
            ],
        ),
    ]

    result = promote_axis_facts(
        [_anchor("A1"), _anchor("A2")], facts, source_text=source
    )

    assert len(result.accepted) == 2
    assert not any(
        issue.code == "promotion_source_block_structure_fanout_quarantined"
        for issue in result.issues
    )


def test_structure_entity_only_collective_range_fanout_is_quarantined():
    evidence = (
        "For samples #1-#3, the laser glazing regions mainly consisted of "
        "columnar grains."
    )
    entities = [
        {
            "name_raw": "columnar grains",
            "entity_type": "grain_population",
            "role": "morphology",
            "features": [],
            "raw_expression": "columnar grains",
        }
    ]
    facts = [
        _structure(sample="#1", evidence=evidence, entities=entities),
        _structure(sample="#2", evidence=evidence, entities=entities),
    ]

    result = promote_axis_facts(
        [_anchor("#1"), _anchor("#2"), _anchor("#3")], facts, source_text=evidence
    )

    assert result.accepted == ()
    assert sum(
        issue.code == "promotion_structure_collective_range_fanout_quarantined"
        for issue in result.issues
    ) == 2


def test_structure_collective_both_assertion_remains_eligible():
    evidence = "Both A1 and A2 contained columnar grains."
    entities = [
        {
            "name_raw": "columnar grains",
            "entity_type": "grain_population",
            "role": "morphology",
            "features": [],
            "raw_expression": "columnar grains",
        }
    ]
    facts = [
        _structure(sample="A1", evidence=evidence, entities=entities),
        _structure(sample="A2", evidence=evidence, entities=entities),
    ]

    result = promote_axis_facts(
        [_anchor("A1"), _anchor("A2")], facts, source_text=evidence
    )

    assert len(result.accepted) == 2
    assert not any(
        issue.code == "promotion_structure_collective_range_fanout_quarantined"
        for issue in result.issues
    )


def test_structure_code_range_fanout_is_quarantined():
    evidence = "R45-R70 powders exhibited semi-molten agglomerates."
    entities = [
        {
            "name_raw": "semi-molten agglomerates",
            "entity_type": "particle",
            "role": "reported",
            "features": [],
            "raw_expression": "semi-molten agglomerates",
        }
    ]
    facts = [
        _structure(sample="R45", evidence=evidence, entities=entities),
        _structure(sample="R70", evidence=evidence, entities=entities),
    ]

    result = promote_axis_facts(
        [_anchor("R45"), _anchor("R70")], facts, source_text=evidence
    )

    assert result.accepted == ()
    assert sum(
        issue.code == "promotion_structure_collective_range_fanout_quarantined"
        for issue in result.issues
    ) == 2


def test_cross_chunk_processing_parameter_fanout_without_coordinate_is_quarantined():
    source = "The laser power was 200 W in one condition, and the laser power was 300 W in another condition."
    facts = [
        _processing(
            sample="A1",
            evidence="The laser power was 200 W in one condition",
            parameters=[
                {
                    "parameter_name_raw": "laser power",
                    "value_raw": "200",
                    "unit_raw": "W",
                    "source_evidence": [
                        "The laser power was 200 W in one condition"
                    ],
                }
            ],
        ),
        _processing(
            sample="A1",
            evidence="and the laser power was 300 W in another condition",
            parameters=[
                {
                    "parameter_name_raw": "laser power",
                    "value_raw": "300",
                    "unit_raw": "W",
                    "source_evidence": [
                        "and the laser power was 300 W in another condition"
                    ],
                }
            ],
        ),
    ]

    result = promote_axis_facts([_anchor("A1")], facts, source_text=source)

    assert result.accepted == ()
    assert sum(
        issue.code == "promotion_source_block_processing_fanout_quarantined"
        for issue in result.issues
    ) == 2


def test_cross_chunk_processing_parameter_fanout_preserves_grounded_conditions():
    source = "The laser power at 0 s delay was 200 W, while at 120 s delay it was 300 W."
    facts = [
        _processing(
            sample="A1",
            evidence="The laser power at 0 s delay was 200 W",
            parameters=[
                {
                    "parameter_name_raw": "laser power",
                    "value_raw": "200",
                    "unit_raw": "W",
                    "condition_label_raw": "0 s delay",
                    "source_evidence": [
                        "The laser power at 0 s delay was 200 W"
                    ],
                }
            ],
        ),
        _processing(
            sample="A1",
            evidence="while at 120 s delay it was 300 W",
            parameters=[
                {
                    "parameter_name_raw": "laser power",
                    "value_raw": "300",
                    "unit_raw": "W",
                    "condition_label_raw": "120 s delay",
                    "source_evidence": [
                        "while at 120 s delay it was 300 W"
                    ],
                }
            ],
        ),
    ]

    result = promote_axis_facts([_anchor("A1")], facts, source_text=source)

    assert len(result.accepted) == 2
    assert not any(
        issue.code == "promotion_source_block_processing_fanout_quarantined"
        for issue in result.issues
    )


def test_processing_generic_base_owner_is_quarantined_when_state_children_exist():
    evidence = "The laser power was 300 W."
    fact = _processing(
        sample="Alloy A",
        evidence=evidence,
        parameters=[
            {
                "parameter_name_raw": "laser power",
                "value_raw": "300",
                "unit_raw": "W",
                "source_evidence": evidence,
            }
        ],
    )
    result = promote_axis_facts(
        [
            _anchor(
                "Alloy A",
                material="Alloy A",
                state="as-built",
                evidence="The as-built Alloy A shows its mechanical performance.",
            ),
            _anchor(
                "Alloy A",
                material="Alloy A",
                state="HIPed",
                evidence="The HIPed Alloy A shows its mechanical performance.",
            ),
        ],
        [fact],
        source_text=evidence,
    )

    assert result.accepted == ()
    issue = next(
        issue
        for issue in result.issues
        if issue.code == "promotion_processing_owner_ambiguous_quarantined"
    )
    assert issue.actual["removed"] == fact.model_dump()
    assert set(issue.actual["candidate_states"]) == {"HIPed", "as-built"}


def test_processing_literal_owner_is_reassigned_to_existing_state_owner():
    evidence = "The as-built Alloy A specimens used a laser power of 300 W."
    fact = _processing(
        sample="Alloy A",
        evidence=evidence,
        parameters=[
            {
                "parameter_name_raw": "laser power",
                "value_raw": "300",
                "unit_raw": "W",
                "source_evidence": evidence,
            }
        ],
    )
    result = promote_axis_facts(
        [
            _anchor("Alloy A", material="Alloy A", state="as-built"),
            _anchor("Alloy A", material="Alloy A", state="HIPed"),
        ],
        [fact],
        source_text=evidence,
    )

    assert len(result.accepted) == 1
    assert result.accepted[0].sample_id_raw == "Alloy A"
    assert not any(
        issue.code == "promotion_processing_owner_ambiguous_quarantined"
        for issue in result.issues
    )


def test_processing_parameter_isolated_when_value_belongs_to_contrast_owner():
    evidence = (
        "Porosity was substantially reduced after sintering to 1300 °C for "
        "gas atomized Inconel 625 powder, in contrast to persistent porosity "
        "for water atomized powder."
    )
    fact = _processing(
        sample="water atomized powder",
        process="sintering",
        evidence=evidence,
        parameters=[
            {
                "parameter_name_raw": "sintering temperature",
                "value_raw": "1300",
                "unit_raw": "°C",
                "source_evidence": evidence,
            }
        ],
    )
    result = promote_axis_facts(
        [
            _anchor("gas atomized Inconel 625", material="Inconel 625"),
            _anchor("water atomized powder", material="Inconel 625"),
        ],
        [fact],
        source_text=evidence,
    )

    assert all(
        parameter.get("value_raw") != "1300"
        for accepted in result.accepted
        for parameter in accepted.data.get("parameters_raw", [])
    )
    issue = next(
        issue
        for issue in result.issues
        if issue.code
        == "promotion_processing_parameter_owner_value_projection_quarantined"
    )
    assert issue.actual["removed_parameter"]["value_raw"] == "1300"
    assert issue.actual["candidate_owners"] == ["water atomized powder"]
    assert issue.actual["source_owners"] == [
        "gas atomized Inconel 625",
        "water atomized powder",
    ]


def test_processing_parameter_stays_with_owner_on_contrast_side():
    evidence = (
        "Porosity was substantially reduced after sintering to 1300 °C for "
        "gas atomized Inconel 625 powder, in contrast to persistent porosity "
        "for water atomized powder."
    )
    fact = _processing(
        sample="gas atomized Inconel 625",
        process="sintering",
        evidence=evidence,
        parameters=[
            {
                "parameter_name_raw": "sintering temperature",
                "value_raw": "1300",
                "unit_raw": "°C",
                "source_evidence": evidence,
            }
        ],
    )
    result = promote_axis_facts(
        [
            _anchor("gas atomized Inconel 625", material="Inconel 625"),
            _anchor("water atomized powder", material="Inconel 625"),
        ],
        [fact],
        source_text=evidence,
    )

    assert len(result.accepted) == 1
    assert result.accepted[0].data["parameters_raw"][0]["value_raw"] == "1300"
    assert not any(
        issue.code
        == "promotion_processing_parameter_owner_value_projection_quarantined"
        for issue in result.issues
    )


def test_processing_suffix_evidence_recovers_owner_from_complete_source_sentence():
    source = (
        "The H230AM samples were produced by LPBF using a laser power of "
        "300 W and a scanning speed of 1100 mm/s."
    )
    fact = _processing(
        sample="H230",
        process="laser powder bed fusion",
        evidence="laser power of 300 W",
        parameters=[
            {
                "parameter_name_raw": "laser power",
                "value_raw": "300",
                "unit_raw": "W",
                "source_evidence": "laser power of 300 W",
            }
        ],
    )
    result = promote_axis_facts(
        [
            _anchor("H230", material="Haynes 230"),
            _anchor("H230AM", material="Haynes 230"),
        ],
        [fact],
        source_text=source,
    )

    assert len(result.accepted) == 1
    assert result.accepted[0].sample_id_raw == "H230AM"
    assert result.accepted[0].data["parameters_raw"][0]["value_raw"] == "300"
    assert any(
        issue.code == "promotion_processing_source_context_owner_reassigned"
        for issue in result.issues
    )


def test_processing_post_annealing_does_not_rebind_to_comparator_state():
    source = (
        "Upon post-annealing at 600 °C for 8 h, the tensile strength was "
        "higher than the values for the as-built samples, respectively."
    )
    fact = _processing(
        sample="as-annealed",
        process="post-annealing",
        evidence="post-annealing at 600 °C for 8 h",
        parameters=[
            {
                "parameter_name_raw": "temperature",
                "value_raw": "600",
                "unit_raw": "°C",
                "source_evidence": "post-annealing at 600 °C for 8 h",
            },
            {
                "parameter_name_raw": "time",
                "value_raw": "8",
                "unit_raw": "h",
                "source_evidence": "post-annealing at 600 °C for 8 h",
            },
        ],
    )
    result = promote_axis_facts(
        [
            _anchor("as-built", material="EHEA", state="as-built"),
            _anchor("as-annealed", material="EHEA", state="as-annealed"),
        ],
        [fact],
        source_text=source,
    )

    assert all(item.sample_id_raw != "as-built" for item in result.accepted)
    assert not any(
        issue.code == "promotion_processing_source_context_owner_reassigned"
        for issue in result.issues
    )


def test_core_tensile_literal_state_survives_generic_sibling_gate():
    evidence = "The HIPed Alloy A had a yield strength of 900 MPa."
    fact = _property(
        sample="Alloy A",
        name="yield strength",
        value="900",
        condition="HIPed",
        evidence=evidence,
    )
    result = promote_axis_facts(
        [
            _anchor("Alloy A", material="Alloy A", state="as-built"),
            _anchor("Alloy A", material="Alloy A", state="HIPed"),
        ],
        [fact],
        source_text=evidence,
    )

    assert len(result.accepted) == 1
    assert result.accepted[0].sample_id_raw == "Alloy A"
    assert not any(
        issue.code == "promotion_core_tensile_owner_ambiguous_quarantined"
        for issue in result.issues
    )


def test_core_tensile_explicit_base_owner_survives_state_siblings():
    evidence = "Alloy A had a yield strength of 900 MPa."
    fact = _property(
        sample="Alloy A",
        name="yield strength",
        value="900",
        condition="",
        evidence=evidence,
    )
    result = promote_axis_facts(
        [
            _anchor("Alloy A", material="Alloy A", state="as-built"),
            _anchor("Alloy A", material="Alloy A", state="HIPed"),
        ],
        [fact],
        source_text=evidence,
    )

    assert result.accepted == (fact,)
    assert not any(
        issue.code == "promotion_core_tensile_owner_ambiguous_quarantined"
        for issue in result.issues
    )


def test_core_tensile_same_physical_owner_envelope_survives_duplicate_graph_nodes():
    evidence = "Subsequent thermal treatment gives a YS of 748 MPa."
    fact = _property(
        sample="HT-Alloy",
        name="yield strength",
        value="748",
        condition="",
        evidence=evidence,
    )
    result = promote_axis_facts(
        [
            _anchor(
                "HT-Alloy",
                material="Alloy matrix",
                state="wall region",
                evidence="The wall region of HT-Alloy contained the matrix.",
            ),
            _anchor(
                "HT-Alloy",
                material="HT-Alloy",
                state="HT",
                evidence="HT-Alloy shows superior mechanical performance.",
            ),
            _anchor(
                "HT-Alloy",
                material="HT-Alloy",
                state="deformed",
                evidence="The deformed HT-Alloy was examined by TEM.",
            ),
            _anchor("AP-Alloy", material="Alloy", state="as-printed"),
        ],
        [fact],
        source_text=(
            "The AP-Alloy had lower strength. "
            "Subsequent thermal treatment gives a YS of 748 MPa. "
            "This superior mechanical performance belongs to HT-Alloy."
        ),
    )

    assert len(result.accepted) == 1
    recovered = result.accepted[0]
    assert recovered.sample_id_raw == fact.sample_id_raw
    assert recovered.data["value_raw"] == fact.data["value_raw"]
    assert recovered.data["unit_raw"] == fact.data["unit_raw"]
    assert recovered.data["property_id_candidate"].startswith(
        "physical-owner-envelope:"
    )
    issue = next(
        row
        for row in result.issues
        if row.code == "tensile_physical_owner_envelope_recovered"
    )
    assert issue.actual["physical_owner"] == "HT-Alloy"
    assert len(issue.actual["candidate_owner_ids"]) == 3
    assert issue.actual["owner_role"] == "Target"
    assert issue.actual["owner_data_nature"] == "Experimental"


def test_core_tensile_same_sample_state_siblings_without_result_anchor_fail_closed():
    evidence = "The reported yield strength was 900 MPa."
    fact = _property(
        sample="Alloy A",
        name="yield strength",
        value="900",
        condition="",
        evidence=evidence,
    )
    result = promote_axis_facts(
        [
            _anchor("Alloy A", material="Alloy A", state="as-built"),
            _anchor("Alloy A", material="Alloy A", state="HIPed"),
            _anchor("Alloy B", material="Alloy B", state="as-built"),
        ],
        [fact],
        source_text=evidence,
    )

    assert result.accepted == ()
    assert any(
        issue.code == "promotion_core_tensile_owner_ambiguous_quarantined"
        for issue in result.issues
    )
    assert not any(
        issue.code == "tensile_physical_owner_envelope_recovered"
        for issue in result.issues
    )


def test_core_tensile_distinct_candidate_samples_do_not_form_physical_envelope():
    evidence = "The reported yield strength was 900 MPa."
    fact = _property(
        sample="shared alloy",
        name="yield strength",
        value="900",
        condition="",
        evidence=evidence,
    )
    result = promote_axis_facts(
        [
            _anchor(
                "A1",
                material="shared alloy",
                state="HT",
                evidence="A1 shows superior mechanical performance.",
            ),
            _anchor(
                "A2",
                material="shared alloy",
                state="HT",
                evidence="A2 shows superior mechanical performance.",
            ),
        ],
        [fact],
        source_text=evidence,
    )

    assert result.accepted == ()
    assert any(
        issue.code == "promotion_core_tensile_owner_ambiguous_quarantined"
        for issue in result.issues
    )


def test_core_tensile_mixed_role_candidate_nodes_do_not_form_physical_envelope():
    evidence = "The reported yield strength was 900 MPa."
    fact = _property(
        sample="HT-Alloy",
        name="yield strength",
        value="900",
        condition="",
        evidence=evidence,
    )
    result = promote_axis_facts(
        [
            _anchor(
                "HT-Alloy",
                material="HT-Alloy",
                state="HT",
                evidence="HT-Alloy shows superior mechanical performance.",
            ),
            InventoryAnchor(
                sample_id_raw="HT-Alloy",
                material_name_raw="HT-Alloy",
                state_raw="literature state",
                role="Reference",
                data_nature="Literature_Experimental",
                source_evidence=[
                    "A literature HT-Alloy shows superior mechanical performance."
                ],
                confidence=0.9,
            ),
            _anchor("AP-Alloy", material="Alloy", state="as-printed"),
        ],
        [fact],
        source_text=evidence,
    )

    assert result.accepted == ()
    assert any(
        issue.code == "promotion_core_tensile_owner_ambiguous_quarantined"
        for issue in result.issues
    )


def test_explicitly_calculated_core_tensile_stays_out_of_formal_properties():
    evidence = "The YS in the wall is calculated as 1140.2 MPa."
    fact = _property(
        sample="HT-Alloy",
        name="calculated YS in the wall",
        value="1140.2",
        condition="",
        evidence=evidence,
    )
    fact.data["origin"] = "calculated"
    result = promote_axis_facts(
        [
            _anchor(
                "HT-Alloy",
                material="HT-Alloy",
                state="HT",
                evidence="HT-Alloy shows superior mechanical performance.",
            ),
            _anchor(
                "HT-Alloy",
                material="Alloy matrix",
                state="wall region",
                evidence="The wall region of HT-Alloy contained the matrix.",
            ),
            _anchor("AP-Alloy", material="Alloy", state="as-printed"),
        ],
        [fact],
        source_text=evidence,
    )

    assert result.accepted == ()
    issue = next(
        row
        for row in result.issues
        if row.code == "promotion_comparative_tensile_quarantined"
    )
    assert issue.actual["reason"] == "explicit_nonexperimental_origin"


def test_core_tensile_structured_state_survives_when_evidence_omits_sample_label():
    evidence = (
        "The average yield strength after HIP2 + HT2 was 1000 MPa."
    )
    fact = _property(
        sample="Alloy A",
        name="yield strength",
        value="1000",
        condition="",
        evidence=evidence,
    )
    fact.data["material_state"] = "HIP2 + HT2"
    result = promote_axis_facts(
        [
            _anchor("Alloy A", material="Alloy A", state="as-built"),
            _anchor("Alloy A", material="Alloy A", state="HIP2 + HT2"),
        ],
        [fact],
        source_text=evidence,
    )

    assert len(result.accepted) == 1
    assert not any(
        issue.code == "promotion_core_tensile_owner_ambiguous_quarantined"
        for issue in result.issues
    )


def test_core_tensile_source_sentence_state_continuation_restores_short_quote():
    source = (
        "At RT, as-built samples exhibit a yield strength of 1388 ± 10 MPa, "
        "an ultimate tensile strength of 1731 ± 31 MPa, and a uniform "
        "elongation of 3.9 ± 0.3 %."
    )
    facts = [
        _property(
            sample="as-built",
            name="ultimate tensile strength",
            value="1731 ± 31",
            unit="MPa",
            condition="",
            evidence="an ultimate tensile strength of 1731 ± 31 MPa",
        ),
        _property(
            sample="as-built",
            name="uniform elongation",
            value="3.9 ± 0.3",
            unit="%",
            condition="",
            evidence="a uniform elongation of 3.9 ± 0.3 %",
        ),
    ]
    result = promote_axis_facts(
        [
            _anchor("as-built", material="Alloy A", state="as-built"),
            _anchor("aged", material="Alloy A", state="aged"),
        ],
        facts,
        source_text=source,
    )

    assert [fact.data["value_raw"] for fact in result.accepted] == [
        "1731 ± 31",
        "3.9 ± 0.3",
    ]
    assert all(
        fact.data["material_state"] == "as-built"
        for fact in result.accepted
    )
    recovery_issues = [
        issue
        for issue in result.issues
        if issue.code == "tensile_source_sentence_state_owner_recovered"
    ]
    assert len(recovery_issues) == 2
    assert all(
        issue.actual["selected_state"] == "as-built"
        and issue.evidence == [issue.actual["source_sentence"]]
        and "1731 ± 31 mpa" in issue.actual["source_sentence"]
        for issue in recovery_issues
    )


def test_core_tensile_source_sentence_longest_state_alias_restores_direct_value():
    source = (
        "The CL sample exhibits an ultimate tensile strength (UTS) of "
        "471.86 ± 2.07 MPa, yield strength of 448.97 ± 4.15 MPa, and "
        "elongation of 4.82 ± 0.36 %."
    )
    fact = _property(
        sample="CL",
        name="ultimate tensile strength (UTS)",
        value="471.86 ± 2.07",
        unit="MPa",
        condition="",
        evidence="ultimate tensile strength (UTS) of 471.86 ± 2.07 MPa",
    )
    result = promote_axis_facts(
        [
            _anchor("CL", material="Alloy A", state="CL"),
            _anchor("CL", material="Alloy A", state="CL sample"),
            _anchor("CL", material="Alloy A", state="as-built"),
            _anchor("PL", material="Alloy A", state="PL sample"),
        ],
        [fact],
        source_text=source,
    )

    assert len(result.accepted) == 1
    assert result.accepted[0].data["material_state"] == "CL sample"
    issue = next(
        issue
        for issue in result.issues
        if issue.code == "tensile_source_sentence_state_owner_recovered"
    )
    assert issue.actual["selected_state"] == "CL sample"


def test_core_tensile_source_sentence_state_continuation_rejects_derived_value():
    source = (
        "Experimental data reveal that the YS of the CL sample exceeds that "
        "of the PL sample by 57.3 MPa."
    )
    fact = _property(
        sample="CL",
        name="YS difference",
        value="57.3",
        unit="MPa",
        condition="",
        evidence="the YS of the CL sample exceeds that of the PL sample by 57.3 MPa",
    )
    result = promote_axis_facts(
        [
            _anchor("CL", material="Alloy A", state="CL sample"),
            _anchor("PL", material="Alloy A", state="PL sample"),
        ],
        [fact],
        source_text=source,
    )

    assert not any(
        issue.code == "tensile_source_sentence_state_owner_recovered"
        for issue in result.issues
    )


def test_core_tensile_source_sentence_state_continuation_prefers_uncertainty_value(
    monkeypatch,
):
    monkeypatch.setenv(
        "KNOWMAT2_ALPHA25_TENSILE_ASSERTION_COORDINATES_V204", "0"
    )
    source = (
        "The room temperature elongation of 4.82% in the CL sample was high. "
        "The CL sample exhibits an elongation of 4.82 ± 0.36 %."
    )
    scalar = _property(
        sample="CL",
        name="elongation",
        value="4.82",
        unit="%",
        condition="room temperature",
        evidence="The room temperature elongation of 4.82% in the CL sample",
    )
    uncertainty = _property(
        sample="CL",
        name="elongation",
        value="4.82 ± 0.36",
        unit="%",
        condition="room temperature",
        evidence="an elongation of 4.82 ± 0.36 %",
    )
    result = promote_axis_facts(
        [
            _anchor("CL", material="Alloy A", state="CL sample"),
            _anchor("PL", material="Alloy A", state="PL sample"),
        ],
        [scalar, uncertainty],
        source_text=source,
    )

    recovered_values = [
        (issue.actual["after"] or {}).get("data", {}).get("value_raw")
        for issue in result.issues
        if issue.code == "tensile_source_sentence_state_owner_recovered"
    ]
    assert recovered_values == ["4.82 ± 0.36"]
    assert "4.82" not in recovered_values


def test_core_tensile_source_sentence_state_continuation_does_not_duplicate_peer():
    source = (
        "A UTS of 612 MPa may be obtained for the sample sintered at 1280 °C. "
        "The 1280 °C sample showed the highest UTS of 612 MPa."
    )
    generic = _property(
        sample="Alloy 625",
        name="UTS",
        value="612",
        unit="MPa",
        condition="",
        evidence="A UTS of 612 MPa",
    )
    explicit = _property(
        sample="1280 °C sample",
        name="UTS",
        value="612",
        unit="MPa",
        condition="sintered at 1280 °C",
        evidence=(
            "The 1280 °C sample showed the highest UTS of 612 MPa"
        ),
    )
    result = promote_axis_facts(
        [
            _anchor(
                "Alloy 625",
                material="Alloy 625",
                state="sintered at 1280 °C",
            ),
            _anchor(
                "1280 °C sample",
                material="Alloy 625",
                state="sintered at 1280 °C",
            ),
        ],
        [generic, explicit],
        source_text=source,
    )

    recovered = [
        issue
        for issue in result.issues
        if issue.code == "tensile_source_sentence_state_owner_recovered"
    ]
    assert not any(
        issue.actual["before"]["sample_id_raw"] == "Alloy 625"
        for issue in recovered
    )


def test_core_tensile_source_sentence_state_continuation_fails_closed():
    anchors = [
        _anchor("Alloy A", material="Alloy A", state="as-built"),
        _anchor("Alloy A", material="Alloy A", state="aged"),
        # An exact duplicate anchor must not itself create ambiguity.
        _anchor("Alloy A", material="Alloy A", state="as-built"),
    ]
    cases = [
        (
            "Both as-built and aged samples had an ultimate tensile strength "
            "of 900 MPa.",
            "ultimate tensile strength of 900 MPa",
            "ultimate tensile strength",
            "MPa",
        ),
        (
            "The as-built sample had a yield strength of 900 MPa.",
            "900 MPa",
            "ultimate tensile strength",
            "MPa",
        ),
        (
            "The as-built sample had an ultimate tensile strength of 900 GPa.",
            "ultimate tensile strength of 900 GPa",
            "ultimate tensile strength",
            "MPa",
        ),
        (
            "The as-built sample had an ultimate tensile strength of 900 MPa. "
            "The as-built sample again had an ultimate tensile strength of 900 MPa.",
            "ultimate tensile strength of 900 MPa",
            "ultimate tensile strength",
            "MPa",
        ),
    ]
    for source, evidence, name, unit in cases:
        fact = _property(
            sample="Alloy A",
            name=name,
            value="900",
            unit=unit,
            condition="",
            evidence=evidence,
        )
        result = promote_axis_facts(
            anchors,
            [fact],
            source_text=source,
        )
        assert not any(
            issue.code == "tensile_source_sentence_state_owner_recovered"
            for issue in result.issues
        ), source

    table = "| State | UTS (MPa) |\n| as-built | 900 |"
    table_fact = _property(
        sample="Alloy A",
        name="ultimate tensile strength",
        value="900",
        unit="MPa",
        condition="",
        evidence=table,
    )
    table_result = promote_axis_facts(
        anchors,
        [table_fact],
        source_text=table,
    )
    assert not any(
        issue.code == "tensile_source_sentence_state_owner_recovered"
        for issue in table_result.issues
    )

    generic_source = (
        "The formed workpiece had an ultimate tensile strength of 900 MPa."
    )
    generic_fact = _property(
        sample="Alloy A",
        name="ultimate tensile strength",
        value="900",
        unit="MPa",
        condition="",
        evidence="ultimate tensile strength of 900 MPa",
    )
    generic_result = promote_axis_facts(
        [
            _anchor("Alloy A", material="Alloy A", state="formed workpiece"),
            _anchor("Alloy B", material="Alloy B", state="formed workpiece"),
        ],
        [generic_fact],
        source_text=generic_source,
    )
    assert not any(
        issue.code == "tensile_source_sentence_state_owner_recovered"
        for issue in generic_result.issues
    )


def test_same_material_different_sample_ids_are_not_lineage_siblings():
    evidence = "A1 had a yield strength of 900 MPa."
    fact = _property(sample="A1", evidence=evidence)
    result = promote_axis_facts(
        [
            _anchor("A1", material="Ti-6Al-4V", state="as-built"),
            _anchor("A2", material="Ti-6Al-4V", state="HIPed"),
        ],
        [fact],
        source_text=evidence,
    )

    assert len(result.accepted) == 1
    assert result.accepted[0].sample_id_raw == "A1"
    assert not any(
        issue.code == "promotion_core_tensile_owner_ambiguous_quarantined"
        for issue in result.issues
    )


def test_html_tensile_row_coordinate_quarantines_value_copied_to_other_owner():
    source = (
        "<table><tr><th>Sample</th><th>UTS (MPa)</th></tr>"
        "<tr><td>A1</td><td>900 ± 10</td></tr>"
        "<tr><td>A2</td><td>850 ± 10</td></tr></table>"
    )
    fact = _property(
        sample="A1",
        name="ultimate tensile strength",
        value="850 ± 10",
        unit="MPa",
        condition="",
        evidence=source,
    )
    result = promote_axis_facts(
        [_anchor("A1"), _anchor("A2")], [fact], source_text=source
    )

    assert result.accepted == ()
    assert any(
        issue.code == "promotion_table_owner_condition_ambiguous_quarantined"
        for issue in result.issues
    )
    issue = next(
        issue
        for issue in result.issues
        if issue.code == "promotion_table_owner_condition_ambiguous_quarantined"
    )
    assert issue.actual["reason"] == "value_bound_to_other_owner_row"


def test_v202_structured_column_owner_preserves_one_rowspan_cell(monkeypatch):
    monkeypatch.setenv("KNOWMAT2_ALPHA25_SOURCE_COORDINATE_PRECISION_V202", "1")
    source = (
        "<table><tr><td>Properties</td><td>WLAM</td><td>WEBAM</td></tr>"
        '<tr><td rowspan="2">Yield Strength (MPa)</td>'
        '<td rowspan="2">825–835 [43]</td><td>846 [44]</td></tr>'
        "<tr><td>956 [45]</td></tr></table>"
    )
    evidence = (
        "| Properties | WLAM | WEBAM |\n"
        "| Yield Strength (MPa) | 825–835 [43] | 956 [45] |"
    )
    fact = _property(
        sample="WLAM",
        name="Yield Strength",
        value="825–835",
        unit="MPa",
        condition="",
        evidence=evidence,
    )
    fact.data["data_source"] = "table"
    fact.data["raw_note"] = "[43]"

    result = promote_axis_facts(
        [_anchor("WLAM"), _anchor("WEBAM")], [fact], source_text=source
    )

    assert result.accepted == (fact,)
    assert not any(
        issue.code == "promotion_table_owner_condition_ambiguous_quarantined"
        for issue in result.issues
    )


def test_same_metric_prose_value_fanout_with_grounded_conditions_survives():
    evidence = (
        "The hardness values for 0 s delay and 300 s delay were 334 HV and "
        "346 HV, respectively."
    )
    facts = [
        _property(
            sample="Ti64",
            name="Vickers microhardness",
            value="334",
            unit="HV",
            condition="0 s delay",
            evidence=evidence,
        ),
        _property(
            sample="Ti64",
            name="Vickers microhardness",
            value="346",
            unit="HV",
            condition="300 s delay",
            evidence=evidence,
        ),
    ]

    result = promote_axis_facts([_anchor("Ti64")], facts, source_text=evidence)

    assert len(result.accepted) == 2
    assert not any(
        issue.code == "promotion_property_value_fanout_ambiguous_quarantined"
        for issue in result.issues
    )


def test_numeric_condition_grounding_does_not_match_suffix_of_larger_number():
    evidence = (
        "The hardness values rose from 334 HV to 346 HV after a 300 s delay."
    )
    facts = [
        _property(
            sample="Ti64",
            name="Vickers microhardness",
            value="334",
            unit="HV",
            condition="0 s delay",
            evidence=evidence,
        ),
        _property(
            sample="Ti64",
            name="Vickers microhardness",
            value="346",
            unit="HV",
            condition="300 s delay",
            evidence=evidence,
        ),
    ]

    result = promote_axis_facts([_anchor("Ti64")], facts, source_text=evidence)

    assert result.accepted == ()
    assert sum(
        issue.code == "promotion_property_value_fanout_ambiguous_quarantined"
        for issue in result.issues
    ) == 2


def test_respectively_condition_pair_routes_generic_owner_to_existing_states():
    evidence = (
        "The fracture-location ranges were 1.10 and 0.96 mm for delays of "
        "0 and 120 s, respectively."
    )
    facts = [
        _property(
            sample="Ti-6Al-4V",
            name="fracture location variation range",
            value="1.10",
            unit="mm",
            condition="delay of 0 s",
            evidence=evidence,
        ),
        _property(
            sample="Ti-6Al-4V",
            name="fracture location variation range",
            value="0.96",
            unit="mm",
            condition="delay of 120 s",
            evidence=evidence,
        ),
    ]
    anchors = [
        _anchor("Ti-6Al-4V", material="Ti-6Al-4V"),
        _anchor("0 s Delay", state="0 s Delay"),
        _anchor("120 s Delay", state="120 s Delay"),
    ]

    result = promote_axis_facts(anchors, facts, source_text=evidence)

    assert {
        row.data["value_raw"]: row.sample_id_raw for row in result.accepted
    } == {
        "1.10": "0 s Delay",
        "0.96": "120 s Delay",
    }
    assert sum(
        issue.code == "promotion_respectively_state_owner_reassigned"
        for issue in result.issues
    ) == 2


def test_respectively_condition_pair_does_not_route_when_state_mapping_is_tied():
    evidence = (
        "The fracture-location ranges were 1.10 and 0.96 mm for delays of "
        "0 and 120 s, respectively."
    )
    facts = [
        _property(
            sample="Ti-6Al-4V",
            name="fracture location variation range",
            value="1.10",
            unit="mm",
            condition="delay of 0 s",
            evidence=evidence,
        ),
        _property(
            sample="Ti-6Al-4V",
            name="fracture location variation range",
            value="0.96",
            unit="mm",
            condition="delay of 120 s",
            evidence=evidence,
        ),
    ]
    anchors = [
        _anchor("Ti-6Al-4V", material="Ti-6Al-4V"),
        _anchor("0 s Delay A", state="0 s Delay"),
        _anchor("0 s Delay B", state="0 s Delay"),
        _anchor("120 s Delay", state="120 s Delay"),
    ]

    result = promote_axis_facts(anchors, facts, source_text=evidence)

    assert all(row.sample_id_raw == "Ti-6Al-4V" for row in result.accepted)
    assert not any(
        issue.code == "promotion_respectively_state_owner_reassigned"
        for issue in result.issues
    )


def test_identical_comparative_property_projection_to_two_owners_is_quarantined():
    evidence = (
        "The phase fraction in Alloy-A (42.3 %) was approximately six times "
        "more than that in Alloy-B (7.34 %)."
    )
    facts = [
        _property(
            sample="Alloy-A",
            name="phase fraction",
            value="42.3",
            unit="%",
            condition="",
            evidence=evidence,
        ),
        _property(
            sample="Alloy-B",
            name="phase fraction",
            value="42.3",
            unit="%",
            condition="",
            evidence=evidence,
        ),
    ]

    result = promote_axis_facts(
        [_anchor("Alloy-A"), _anchor("Alloy-B")], facts, source_text=evidence
    )

    assert result.accepted == ()
    assert sum(
        issue.code == "promotion_comparative_owner_duplicate_quarantined"
        for issue in result.issues
    ) == 2


def test_collective_comparative_property_projection_is_preserved():
    evidence = "Both Alloy-A and Alloy-B showed higher hardness of 300 HV."
    facts = [
        _property(
            sample="Alloy-A",
            name="hardness",
            value="300",
            unit="HV",
            condition="",
            evidence=evidence,
        ),
        _property(
            sample="Alloy-B",
            name="hardness",
            value="300",
            unit="HV",
            condition="",
            evidence=evidence,
        ),
    ]

    result = promote_axis_facts(
        [_anchor("Alloy-A"), _anchor("Alloy-B")], facts, source_text=evidence
    )

    assert len(result.accepted) == 2
    assert not any(
        issue.code == "promotion_comparative_owner_duplicate_quarantined"
        for issue in result.issues
    )


def test_distinct_values_in_comparative_owner_projection_are_preserved():
    evidence = "The phase fractions of Alloy-A and Alloy-B were 42.3 and 7.34 %, respectively."
    facts = [
        _property(
            sample="Alloy-A",
            name="phase fraction",
            value="42.3",
            unit="%",
            condition="",
            evidence=evidence,
        ),
        _property(
            sample="Alloy-B",
            name="phase fraction",
            value="7.34",
            unit="%",
            condition="",
            evidence=evidence,
        ),
    ]

    result = promote_axis_facts(
        [_anchor("Alloy-A"), _anchor("Alloy-B")], facts, source_text=evidence
    )

    assert len(result.accepted) == 2
    assert not any(
        issue.code == "promotion_comparative_owner_duplicate_quarantined"
        for issue in result.issues
    )


def test_same_metric_table_values_are_left_to_table_coordinate_gate():
    source = (
        "| Property | A1 | A2 |\n"
        "|---|---:|---:|\n"
        "| Hardness (HV) | 334 | 346 |"
    )
    facts = [
        _property(
            sample="A1",
            name="Hardness",
            value="334",
            unit="HV",
            condition="",
            evidence=source,
        ),
        _property(
            sample="A2",
            name="Hardness",
            value="346",
            unit="HV",
            condition="",
            evidence=source,
        ),
    ]

    result = promote_axis_facts(
        [_anchor("A1"), _anchor("A2")], facts, source_text=source
    )

    assert len(result.accepted) == 2
    assert not any(
        issue.code == "promotion_property_value_fanout_ambiguous_quarantined"
        for issue in result.issues
    )


def test_respectively_different_property_names_remain_atomic():
    evidence = "The yield strength and elongation were 900 MPa and 20%, respectively."
    facts = [
        _property(
            sample="A1",
            name="yield strength",
            value="900",
            unit="MPa",
            condition="",
            evidence=evidence,
        ),
        _property(
            sample="A1",
            name="elongation",
            value="20",
            unit="%",
            condition="",
            evidence=evidence,
        ),
    ]

    result = promote_axis_facts([_anchor("A1")], facts, source_text=evidence)

    assert {
        row.data["property_name_raw"] for row in result.accepted
    } == {"yield strength", "elongation"}
    assert {
        row.data["value_raw"] for row in result.accepted
    } == {"900", "20"}
    assert not any(
        issue.code == "promotion_respectively_mapping_ambiguous_quarantined"
        for issue in result.issues
    )


def test_explicit_treatment_condition_is_bound_from_same_tensile_assertion():
    evidence = (
        "Subsequent thermal treatment (800 °C/4 h) leads to an ultimate tensile "
        "strength of 1148 MPa and a ductility of 28 %."
    )
    fact = _property(
        sample="HT-HEA",
        name="ductility",
        value="28",
        unit="%",
        condition="",
        evidence=evidence,
    )

    result = promote_axis_facts([_anchor("HT-HEA")], [fact], source_text=evidence)

    assert len(result.accepted) == 1
    assert "800 °C/4 h" in result.accepted[0].data["test_condition_raw"]
    issue = next(
        issue
        for issue in result.issues
        if issue.code == "promotion_explicit_treatment_condition_bound"
    )
    assert issue.actual["before"] == fact.model_dump()
    assert issue.actual["after"] == result.accepted[0].model_dump()


def test_owner_state_treatment_is_separated_from_tensile_condition():
    evidence = (
        "GA sample sintered at 1285 °C and aged at 745 °C for 20 h had an "
        "ultimate tensile strength of 718 MPa."
    )
    fact = _property(
        sample="GA sample sintered at 1285 °C and aged at 745 °C for 20 h",
        name="ultimate tensile strength",
        value="718",
        condition="sintered at 1285 °C and aged at 745 °C for 20 h",
        evidence=evidence,
    )
    result = promote_axis_facts(
        [
            _anchor(
                "GA sample sintered at 1285 °C and aged at 745 °C for 20 h",
                state="sintered at 1285 °C and aged at 745 °C for 20 h",
            )
        ],
        [fact],
        source_text=evidence,
    )

    assert len(result.accepted) == 1
    assert result.accepted[0].data["material_state"] == (
        "sintered at 1285 °C and aged at 745 °C for 20 h"
    )
    assert result.accepted[0].data["test_condition_raw"] == ""
    assert any(
        issue.code == "promotion_preparation_condition_separated"
        for issue in result.issues
    )


def test_feedstock_composition_on_processed_owner_is_quarantined_without_anchor():
    evidence = (
        "A gas-atomized alloy powder, comprising Al-3.89Cu-1.22Li-0.98Sc-0.43Zr "
        "(wt%), was employed as the feedstock for the LPBF process."
    )
    fact = _composition(sample="HT", evidence=evidence)

    result = promote_axis_facts([_anchor("HT")], [fact], source_text=evidence)

    assert result.accepted == ()
    issue = next(
        issue
        for issue in result.issues
        if issue.code == "promotion_feedstock_owner_mismatch_quarantined"
    )
    assert issue.actual["removed"] == fact.model_dump()


def test_explicit_sample_named_as_powder_keeps_composition_owner():
    evidence = "Chemical compositions of H230 powder are listed in Table 1."
    fact = _composition(sample="H230", evidence=evidence)

    result = promote_axis_facts([_anchor("H230")], [fact], source_text=evidence)

    # A table-heading mention alone does not ground the emitted numeric
    # component.  Keep the owner auditable, but isolate the unbound value.
    assert result.accepted == ()
    assert any(
        issue.code == "composition_component_precision_quarantined"
        and issue.actual["reason"] == "numeric_literal_not_in_component_evidence"
        for issue in result.issues
    )
    assert not any(
        issue.code.startswith("promotion_feedstock_owner_")
        for issue in result.issues
    )


def test_feedstock_context_does_not_quarantine_material_identity():
    """Feedstock wording must not remove a material identity fact."""

    evidence = (
        "The gas-atomized alloy powder was employed as the feedstock for the LPBF process."
    )
    fact = CompositionFact(
        sample_id_raw="AF",
        fact_type="material_identity",
        evidence_unit_id="prose-L000001-L000001-identity",
        data={
            "material_family": "nickel-based alloy",
            "material_name_raw": "AF",
            "designation_raw": "AF",
            "feedstock_form": "gas-atomized powder",
        },
        source_evidence=[evidence],
        confidence=0.9,
    )

    result = promote_axis_facts([_anchor("AF")], [fact], source_text=evidence)

    assert result.accepted == (fact,)
    assert not any(
        issue.code.startswith("promotion_feedstock_owner_")
        for issue in result.issues
    )


def test_tensile_table_unique_row_coordinate_is_preserved():
    source = (
        "| Samples | Yield strength (MPa) | Elongation (%) |\n"
        "|---|---:|---:|\n"
        "| AF-RT | 482 ± 1 | 9 ± 1 |\n"
        "| AF-200 C | 402 ± 14 | 11 ± 2 |"
    )
    evidence = "| AF-RT | 482 ± 1 | 9 ± 1 |"
    fact = _property(sample="AF", value="482 ± 1", condition="RT", evidence=evidence)

    result = promote_axis_facts([_anchor("AF")], [fact], source_text=source)

    assert result.accepted == (fact,)
    assert not any(
        issue.code == "promotion_table_owner_condition_ambiguous_quarantined"
        for issue in result.issues
    )


def test_tensile_table_unique_value_selects_one_row_for_shared_base_owner():
    source = (
        "| Samples | Yield strength (MPa) | Elongation (%) |\n"
        "|---|---:|---:|\n"
        "| AF-RT | 482 ± 1 | 9 ± 1 |\n"
        "| AF-200 C | 402 ± 14 | 11 ± 2 |"
    )
    evidence = "| AF-200 C | 402 ± 14 | 11 ± 2 |"
    fact = _property(sample="AF", value="402 ± 14", condition="", evidence=evidence)
    anchors = [_anchor("AF", state="RT"), _anchor("AF", state="200 C")]

    result = promote_axis_facts(anchors, [fact], source_text=source)

    assert result.accepted == (fact,)
    assert not any(
        issue.code == "promotion_table_owner_condition_ambiguous_quarantined"
        for issue in result.issues
    )


def test_tensile_table_repeated_value_across_owner_columns_is_quarantined():
    source = (
        "| Property | A1 | A2 |\n"
        "|---|---:|---:|\n"
        "| Yield strength (MPa) | 900 | 900 |"
    )
    evidence = "| Yield strength (MPa) | 900 | 900 |"
    fact = _property(sample="A1", value="900", condition="", evidence=evidence)

    result = promote_axis_facts(
        [_anchor("A1"), _anchor("A2")], [fact], source_text=source
    )

    assert result.accepted == ()
    issue = next(
        issue
        for issue in result.issues
        if issue.code == "promotion_table_owner_condition_ambiguous_quarantined"
    )
    assert issue.actual["removed"] == fact.model_dump()
    assert len(issue.actual["all_owner_value_hits"]) == 2
    assert issue.expected["broadcast"] is False


def test_tensile_table_unique_owner_column_value_is_preserved():
    source = (
        "| Property | A1 | A2 |\n"
        "|---|---:|---:|\n"
        "| Yield strength (MPa) | 900 | 800 |"
    )
    evidence = "| Yield strength (MPa) | 900 | 800 |"
    fact = _property(sample="A1", value="900", condition="", evidence=evidence)

    result = promote_axis_facts(
        [_anchor("A1"), _anchor("A2")], [fact], source_text=source
    )

    assert result.accepted == (fact,)


def test_tensile_table_condition_column_routes_truncated_row_to_state_owner():
    """A numeric-only evidence row can retain its source table condition."""

    source = (
        "| Properties | 0 s Delay | 120 s Delay | 300 s Delay |\n"
        "| --- | --- | --- | --- |\n"
        "| Avg. YS (MPa) | 817 ± 8.7 | 859.7 ± 9.2 | 825.3 ± 3.1 |"
    )
    evidence = "| Avg. YS (MPa) | 817 ± 8.7 | 859.7 ± 9.2 | 825.3 ± 3.1 |"
    fact = _property(
        sample="Ti64",
        value="825.3 ± 3.1",
        condition="300 s Delay",
        evidence=evidence,
    )
    anchors = [
        _anchor("Ti64", material="Ti64"),
        _anchor("0 s Delay", material="Ti64", state="0 s Delay"),
        _anchor("120 s Delay", material="Ti64", state="120 s Delay"),
        _anchor("300 s Delay", material="Ti64", state="300 s Delay"),
    ]

    result = promote_axis_facts(anchors, [fact], source_text=source)

    assert len(result.accepted) == 1
    assert result.accepted[0].sample_id_raw == "300 s Delay"
    assert result.accepted[0].data["test_condition_raw"] == "300 s Delay"
    assert any(
        issue.code == "promotion_tensile_table_condition_owner_reassigned"
        for issue in result.issues
    )


def test_tensile_table_condition_column_recovers_dropped_condition_and_owner():
    """A value-only row can recover its unique physical condition column."""

    source = (
        "| Properties | 0 s Delay | 120 s Delay | 300 s Delay |\n"
        "| --- | --- | --- | --- |\n"
        "| Avg. YS (MPa) | 817 ± 8.7 | 859.7 ± 9.2 | 825.3 ± 3.1 |"
    )
    evidence = "| Avg. YS (MPa) | 817 ± 8.7 | 859.7 ± 9.2 | 825.3 ± 3.1 |"
    fact = _property(
        sample="Ti64",
        value="825.3 ± 3.1",
        condition="",
        evidence=evidence,
    )
    anchors = [
        _anchor("Ti64", material="Ti64"),
        _anchor("0 s Delay", material="Ti64", state="0 s Delay"),
        _anchor("120 s Delay", material="Ti64", state="120 s Delay"),
        _anchor("300 s Delay", material="Ti64", state="300 s Delay"),
    ]

    result = promote_axis_facts(anchors, [fact], source_text=source)

    assert len(result.accepted) == 1
    assert result.accepted[0].sample_id_raw == "300 s Delay"
    assert result.accepted[0].data["test_condition_raw"] == "300 s Delay"
    issue = next(
        issue
        for issue in result.issues
        if issue.code == "promotion_tensile_table_condition_owner_inferred"
    )
    assert issue.actual["selected_owner"] == "300 s Delay"
    assert issue.actual["condition_header"] == "300 s Delay"


def test_two_level_tensile_table_uses_test_specimen_as_literal_condition_coordinate():
    """A compact HT/aging label in ``test_specimen_raw`` is table evidence."""

    source = (
        "|  | A | A | B | B |\n"
        "|  | HT | 200 h | HT | 200 h |\n"
        "| UTS (MPa) | 900 | 800 | 700 | 600 |"
    )
    evidence = "| UTS (MPa) | 900 | 800 | 700 | 600 |"
    fact = _property(sample="A", value="900", condition="", evidence=evidence)
    fact.data["data_source"] = "table"
    fact.data["test_specimen_raw"] = "HT"

    result = promote_axis_facts(
        [_anchor("A", material="A"), _anchor("B", material="B")],
        [fact],
        source_text=source,
    )

    assert result.accepted == (fact,)
    assert not any(
        issue.code == "promotion_table_owner_condition_ambiguous_quarantined"
        for issue in result.issues
    )


def test_two_level_table_does_not_rescue_bare_tensile_strength_label():
    """A generic summary label stays quarantined despite a repeated header."""

    source = (
        "|  | A | A | B | B |\n"
        "|  | HT | 200 h | HT | 200 h |\n"
        "| Tensile strength (MPa) | 900 | 900 | 700 | 600 |"
    )
    evidence = "| Tensile strength (MPa) | 900 | 900 | 700 | 600 |"
    fact = _property(
        sample="A", name="Tensile strength", value="900", condition="", evidence=evidence
    )
    fact.data["data_source"] = "table"
    fact.data["test_specimen_raw"] = "HT"

    result = promote_axis_facts(
        [_anchor("A", material="A"), _anchor("B", material="B")],
        [fact],
        source_text=source,
    )

    assert result.accepted == ()
    assert any(
        issue.code == "promotion_table_owner_condition_ambiguous_quarantined"
        for issue in result.issues
    )


def test_tensile_table_condition_column_quarantines_value_from_wrong_column():
    source = (
        "| Properties | 0 s Delay | 120 s Delay | 300 s Delay |\n"
        "| --- | --- | --- | --- |\n"
        "| Avg. YS (MPa) | 817 ± 8.7 | 859.7 ± 9.2 | 825.3 ± 3.1 |"
    )
    evidence = "| Avg. YS (MPa) | 817 ± 8.7 | 859.7 ± 9.2 | 825.3 ± 3.1 |"
    fact = _property(
        sample="Ti64",
        value="825.3 ± 3.1",
        condition="0 s Delay",
        evidence=evidence,
    )
    anchors = [
        _anchor("Ti64", material="Ti64"),
        _anchor("0 s Delay", material="Ti64", state="0 s Delay"),
        _anchor("120 s Delay", material="Ti64", state="120 s Delay"),
        _anchor("300 s Delay", material="Ti64", state="300 s Delay"),
    ]

    result = promote_axis_facts(anchors, [fact], source_text=source)

    assert result.accepted == ()
    issue = next(
        issue
        for issue in result.issues
        if issue.code == "promotion_table_owner_condition_ambiguous_quarantined"
    )
    assert issue.actual["reason"] == "value_bound_to_other_condition_column"
    assert issue.actual["condition_binding"]["condition_columns"] == [1]


def test_tensile_table_condition_match_does_not_confuse_zero_and_three_hundred():
    source = (
        "| Properties | 0 s Delay | 300 s Delay |\n"
        "| --- | --- | --- |\n"
        "| Avg. YS (MPa) | 817 ± 8.7 | 825.3 ± 3.1 |"
    )
    evidence = "| Avg. YS (MPa) | 817 ± 8.7 | 825.3 ± 3.1 |"
    fact = _property(
        sample="Ti64",
        value="825.3 ± 3.1",
        condition="0 s Delay",
        evidence=evidence,
    )

    result = promote_axis_facts(
        [_anchor("Ti64", material="Ti64")], [fact], source_text=source
    )

    assert result.accepted == ()
    assert any(
        issue.code == "promotion_table_owner_condition_ambiguous_quarantined"
        and issue.actual["reason"] == "value_bound_to_other_condition_column"
        for issue in result.issues
    )


def test_tensile_feedstock_condition_is_isolated_but_value_survives():
    evidence = (
        "A1 had a yield strength of 900 MPa; gas-atomized powder was used as feedstock."
    )
    fact = _property(
        sample="A1",
        value="900",
        condition="gas-atomized powder",
        evidence=evidence,
    )

    result = promote_axis_facts([_anchor("A1")], [fact], source_text=evidence)

    assert len(result.accepted) == 1
    assert result.accepted[0].data["value_raw"] == "900"
    assert result.accepted[0].data["test_condition_raw"] == ""
    issue = next(
        issue
        for issue in result.issues
        if issue.code == "promotion_tensile_condition_scope_quarantined"
    )
    assert issue.actual["before"] == fact.model_dump()
    assert issue.actual["after"] == result.accepted[0].model_dump()


def test_external_reference_condition_is_not_attached_to_current_experiment():
    evidence = (
        "A1 had a yield strength of 900 MPa. "
        "A reference simulation at 700 °C predicted 950 MPa."
    )
    fact = _property(sample="A1", value="900", condition="700 °C", evidence=evidence)

    result = promote_axis_facts([_anchor("A1")], [fact], source_text=evidence)

    assert len(result.accepted) == 1
    assert result.accepted[0].data["test_condition_raw"] == ""
    assert any(
        issue.code == "promotion_tensile_condition_scope_quarantined"
        for issue in result.issues
    )


def test_tensile_source_gate_does_not_touch_composition():
    evidence = "A1 contained 47.86 ± 0.5 at.% Al."
    fact = _composition(sample="A1", evidence=evidence)

    result = promote_axis_facts([_anchor("A1")], [fact], source_text=evidence)

    assert result.accepted == (fact,)
    assert not any("tensile" in issue.code for issue in result.issues)


def test_external_composition_subject_is_quarantined_without_losing_current_value():
    source = (
        "Pyczak et al. [34] reported that in the Ni-based alloys with "
        "10–30 vol.% Cr, Cr2O3 was observed as external scales, which are "
        "both expected to form in our sintered parts with 21.2 wt.% of Cr [34]."
    )
    external = _composition(
        sample="alloy 625 [sintered]",
        component="Cr",
        value="10–30",
        unit="vol.%",
        evidence="in the Ni-based alloys with 10–30 vol.% Cr",
    )
    external.data.update(
        {
            "material_state": "sintered",
            "basis": "vol%",
            "note": "range reported in literature for Ni-based alloys",
        }
    )
    external.data["components"][0]["value_kind"] = "range"
    current = _composition(
        sample="alloy 625 [sintered]",
        component="Cr",
        value="21.2",
        unit="wt.%",
        evidence="our sintered parts with 21.2 wt.% of Cr",
    )
    current.data.update({"material_state": "sintered", "basis": "wt%"})
    current.data["components"][0]["value_kind"] = "scalar"

    result = promote_axis_facts(
        [
            _anchor(
                "alloy 625 [sintered]",
                material="alloy 625",
                state="sintered",
            )
        ],
        [external, current],
        source_text=source,
    )

    assert result.accepted == (current,)
    issue = next(
        issue
        for issue in result.issues
        if issue.code == "promotion_external_composition_subject_quarantined"
    )
    assert issue.actual["before"] == external.model_dump()
    assert issue.actual["after"] is None
    assert issue.actual["removed_component"] == external.data["components"][0]
    assert issue.actual["decision_class"] == "attributed_literature_chemistry"
    assert "Pyczak et al." in issue.actual["matched_source_sentence"]
    assert issue.actual["value_local_proposition"] == external.source_evidence[0]
    assert issue.actual["current_source_guard"] is False
    assert issue.actual["owner_invented"] is False


def test_general_solid_solubility_limits_are_not_current_composition():
    evidence = (
        "the transition metal elements have very low solid solubility in Al: "
        "Ti < 0.05 at%, Fe < 0.04 at%, Co < 0.05 at%, Ni < 0.04 at%."
    )
    source = "In general, " + evidence
    fact = _composition(
        sample="Al92Ti2Fe2Co2Ni2",
        component="Ti",
        value="<0.05",
        unit="at%",
        evidence=evidence,
    )
    fact.data.update(
        {
            "material_state": "as-printed",
            "basis": "at%",
            "note": "equilibrium solid solubility of transition metals in Al",
        }
    )
    fact.data["components"] = [
        {
            "name_raw": name,
            "value_kind": "inequality",
            "value_raw": value,
            "unit_raw": "at%",
            "data_nature": "reported",
        }
        for name, value in (
            ("Ti", "<0.05"),
            ("Fe", "<0.04"),
            ("Co", "<0.05"),
            ("Ni", "<0.04"),
        )
    ]

    result = promote_axis_facts(
        [_anchor("Al92Ti2Fe2Co2Ni2", state="as-printed")],
        [fact],
        source_text=source,
    )

    assert result.accepted == ()
    issues = [
        issue
        for issue in result.issues
        if issue.code == "promotion_external_composition_subject_quarantined"
    ]
    assert [issue.actual["removed_component"]["name_raw"] for issue in issues] == [
        "Ti",
        "Fe",
        "Co",
        "Ni",
    ]
    assert {issue.actual["decision_class"] for issue in issues} == {
        "general_reference_constraint"
    }
    assert all(issue.actual["after"] is None for issue in issues)


def test_measured_apt_matrix_composition_survives_reference_constraint_note():
    evidence = (
        "APT measured 0.20 at% Ti, 0.30 at% Fe, 0.03 at% Co and 0.09 at% Ni "
        "in the A1 matrix."
    )
    fact = _composition(
        sample="A1",
        component="Ti",
        value="0.20",
        unit="at%",
        evidence=evidence,
    )
    fact.data["note"] = "measured values compared with equilibrium solid solubility"
    fact.data["components"][0]["value_kind"] = "scalar"

    result = promote_axis_facts([_anchor("A1")], [fact], source_text=evidence)

    assert result.accepted == (fact,)
    assert not any(
        issue.code == "promotion_external_composition_subject_quarantined"
        for issue in result.issues
    )


def test_external_composition_gate_filters_only_disproven_component():
    external_evidence = "Smith et al. reported 10–30 vol.% Cr for reference alloys."
    current_evidence = "A1 contained 58 wt.% Ni."
    source = external_evidence + " " + current_evidence
    fact = _composition(
        sample="A1",
        component="Cr",
        value="10–30",
        unit="vol.%",
        evidence=external_evidence,
    )
    fact.source_evidence.append(current_evidence)
    fact.data.update(
        {
            "basis": "wt%",
            "source_evidence": [external_evidence, current_evidence],
            "note": "Cr range reported in literature; Ni measured in current sample",
        }
    )
    fact.data["components"] = [
        {
            "name_raw": "Cr",
            "value_kind": "range",
            "value_raw": "10–30",
            "unit_raw": "vol.%",
            "data_nature": "reported",
        },
        {
            "name_raw": "Ni",
            "value_kind": "scalar",
            "value_raw": "58",
            "unit_raw": "wt.%",
            "data_nature": "reported",
        },
    ]

    result = promote_axis_facts([_anchor("A1")], [fact], source_text=source)

    assert len(result.accepted) == 1
    assert result.accepted[0].data["components"] == [fact.data["components"][1]]
    issue = next(
        issue
        for issue in result.issues
        if issue.code == "promotion_external_composition_subject_quarantined"
    )
    assert issue.actual["before"] == fact.model_dump()
    assert issue.actual["after"] == result.accepted[0].model_dump()
    assert issue.actual["removed_component"] == fact.data["components"][0]


def test_current_composition_with_citation_and_general_language_survives():
    evidence = "In general, A1 contained 47.86 at.% Al in the measured region [34]."
    fact = _composition(
        sample="A1",
        component="Al",
        value="47.86",
        unit="at.%",
        evidence=evidence,
    )
    fact.data["note"] = "value discussed with literature reference"
    fact.data["components"][0]["value_kind"] = "scalar"

    result = promote_axis_facts([_anchor("A1")], [fact], source_text=evidence)

    assert result.accepted == (fact,)
    assert not any(
        issue.code == "promotion_external_composition_subject_quarantined"
        for issue in result.issues
    )


def test_external_composition_gate_is_noop_for_table_reference_and_ambiguity():
    table_evidence = "| A1 | Cr | 10–30 | vol.% | [34] |"
    table_fact = _composition(
        sample="A1",
        component="Cr",
        value="10–30",
        unit="vol.%",
        evidence=table_evidence,
    )
    table_fact.data["note"] = "literature range"
    reference_evidence = "Smith et al. reported 10–30 vol.% Cr."
    reference_fact = _composition(
        sample="Smith alloy [reference]",
        component="Cr",
        value="10–30",
        unit="vol.%",
        evidence=reference_evidence,
    )
    reference_fact.data["note"] = "literature range"
    ambiguous_fact = _composition(
        sample="A2",
        component="Cr",
        value="10–30",
        unit="vol.%",
        evidence=reference_evidence,
    )
    ambiguous_fact.data["note"] = "literature range"
    repeated_source = reference_evidence + " " + reference_evidence

    table_result = promote_axis_facts(
        [_anchor("A1")], [table_fact], source_text=table_evidence
    )
    reference_result = promote_axis_facts(
        [_anchor("Smith alloy [reference]", role="Reference")],
        [reference_fact],
        source_text=reference_evidence,
    )
    ambiguous_result = promote_axis_facts(
        [_anchor("A2")], [ambiguous_fact], source_text=repeated_source
    )
    missing_source_result = promote_axis_facts(
        [_anchor("A2")], [ambiguous_fact], source_text=""
    )

    assert table_fact in table_result.accepted
    assert reference_fact in reference_result.accepted
    assert ambiguous_fact in ambiguous_result.accepted
    assert ambiguous_fact in missing_source_result.accepted
    assert not any(
        issue.code == "promotion_external_composition_subject_quarantined"
        for result in (
            table_result,
            reference_result,
            ambiguous_result,
            missing_source_result,
        )
        for issue in result.issues
    )


def test_cited_previous_work_projection_is_quarantined_without_owner_literal():
    evidence = "Previous work [26] reported fine gamma-prime precipitates in the alloy."
    fact = _structure(sample="A1", evidence=evidence)

    result = promote_axis_facts([_anchor("A1")], [fact], source_text=evidence)

    assert any(
        issue.code == "promotion_external_source_projection_quarantined"
        for issue in result.issues
    )
    issue = next(
        issue
        for issue in result.issues
        if issue.code == "promotion_external_source_projection_quarantined"
    )
    assert issue.actual["removed"] == fact.model_dump()
    assert issue.expected["external_projection"] is False


def test_cited_sentence_with_literal_current_owner_is_preserved():
    evidence = "A1 showed fine gamma-prime precipitates; previous work [26] is cited for context."
    fact = _structure(sample="A1", evidence=evidence)

    result = promote_axis_facts([_anchor("A1")], [fact], source_text=evidence)

    assert fact in result.accepted
    assert not any(
        issue.code == "promotion_external_source_projection_quarantined"
        for issue in result.issues
    )


def test_author_year_citation_is_quarantined_from_current_target():
    evidence = (
        "The gamma-prime precipitates in AM-fabricated Inconel 718 are "
        "50~120 μm (Hosseini and Popovich, 2019)."
    )
    fact = _structure(
        sample="A1",
        evidence=evidence,
        entities=[],
        features=[
            {
                "feature_name_raw": "grain size",
                "value_kind": "range",
                "value_raw": "50~120",
                "unit_raw": "μm",
                "data_nature": "reported",
                "source_evidence": [evidence],
            }
        ],
    )

    result = promote_axis_facts([_anchor("A1")], [fact], source_text=evidence)

    assert result.accepted == ()
    issue = next(
        issue
        for issue in result.issues
        if issue.code == "promotion_external_source_projection_quarantined"
    )
    assert "2019" in issue.actual["external_cue"]


def test_cited_tensile_value_without_owner_literal_is_quarantined():
    evidence = "Cast alloy 625 [11] had a UTS of 710 MPa with 48% elongation."
    fact = _property(
        sample="alloy 625 powder",
        name="ultimate tensile strength",
        value="710",
        unit="MPa",
        condition="",
        evidence=evidence,
    )

    # No inventory anchor is available for the generic owner, so the older
    # graph-resolved external-source gate cannot identify this as a projection.
    result = promote_axis_facts([], [fact], source_text=evidence)

    assert result.accepted == ()
    issue = next(
        issue
        for issue in result.issues
        if issue.code == "promotion_unbound_external_tensile_quarantined"
    )
    assert issue.actual["removed"] == fact.model_dump()


def test_cited_tensile_subject_does_not_rescue_current_owner_substring():
    evidence = "cast alloy 625 [11] had a UTS of 710 MPa with 48% elongation"
    facts = [
        _property(
            sample="cast alloy 625",
            name="UTS",
            value="710",
            unit="MPa",
            condition="",
            evidence=evidence,
            candidate_id="cited-uts",
            evidence_unit_id="cited-uts",
        ),
        _property(
            sample="cast alloy 625",
            name="elongation",
            value="48",
            unit="%",
            condition="",
            evidence=evidence,
            candidate_id="cited-elongation",
            evidence_unit_id="cited-elongation",
        ),
    ]

    result = promote_axis_facts(
        [_anchor("alloy 625", material="alloy 625")],
        facts,
        source_text=evidence,
    )

    assert result.accepted == ()
    issues = [
        issue
        for issue in result.issues
        if issue.code
        == "promotion_external_current_tensile_projection_quarantined"
    ]
    assert [issue.actual["removed"]["data"]["value_raw"] for issue in issues] == [
        "710",
        "48",
    ]
    assert all(
        issue.actual["removed"]["sample_id_raw"] == "alloy 625"
        for issue in issues
    )
    assert all(
        issue.actual["reason"]
        == "external_comparator_subject_on_current_owner"
        for issue in issues
    )
    assert all(issue.actual["matched_source_sentence"] == evidence for issue in issues)
    assert all(issue.actual["value_local_proposition"] == evidence for issue in issues)
    assert all(
        issue.actual["external_subject"] == "cast alloy 625 [11]"
        for issue in issues
    )
    assert all(issue.actual["subject_cue"] == "[11]" for issue in issues)
    assert all(
        issue.actual["embedded_owner_literal"] == "alloy 625"
        for issue in issues
    )
    assert all(issue.actual["owner_invented"] is False for issue in issues)


def test_numeric_tensile_value_owned_by_uncited_comparator_is_quarantined():
    evidence = "comparable to those of cast TNM alloys (700–800 MPa)"
    owner = "44–4 alloy rods [fabricated by the EBM]"
    fact = _property(
        sample="cast TNM alloys",
        name="ultimate tensile strength",
        value="700–800 MPa",
        unit="MPa",
        condition="",
        evidence=evidence,
    )

    result = promote_axis_facts(
        [
            _anchor(
                owner,
                material="44–4 alloy",
                state="fabricated by the EBM",
            )
        ],
        [fact],
        source_text=evidence,
    )

    assert result.accepted == ()
    issue = next(
        issue
        for issue in result.issues
        if issue.code == "promotion_unbound_external_tensile_quarantined"
    )
    assert issue.actual["removed"] == fact.model_dump()
    assert issue.actual["reason"] == "external_comparator_without_reference_owner"
    assert issue.actual["matched_source_sentence"] == evidence
    assert issue.actual["value_local_proposition"] == evidence
    assert issue.actual["external_subject"] == "cast tnm alloys"
    assert issue.actual["subject_cue"] == "comparable to those of"
    assert issue.actual["embedded_owner_literal"] is None
    assert issue.actual["owner_invented"] is False


def test_higher_than_comparator_value_has_clean_audit_subject():
    evidence = "higher than those of cast 48–2–2 (~450 MPa)"
    fact = _property(
        sample="cast 48–2–2 alloys",
        name="ultimate tensile strength",
        value="~450",
        unit="MPa",
        condition="",
        evidence=evidence,
    )

    result = promote_axis_facts(
        [_anchor("44–4 alloy rods", material="44–4 alloy")],
        [fact],
        source_text=evidence,
    )

    assert result.accepted == ()
    issue = next(
        row
        for row in result.issues
        if row.code == "promotion_unbound_external_tensile_quarantined"
    )
    assert issue.actual["reason"] == "external_comparator_without_reference_owner"
    assert issue.actual["external_subject"] == "cast 48 2 2"
    assert issue.actual["subject_cue"] == "higher than"


def test_direct_author_attributed_tensile_subject_overrides_collective_escape():
    evidence = (
        "Yan et al. presented that the yield stress of high-Nb-containing "
        "TiAl alloys with the fully lamellar structure is approximately "
        "900 MPa at 1023 K"
    )
    fact = _property(
        sample="44–4 alloy rods",
        name="yield stress",
        value="approximately 900",
        unit="MPa",
        condition="1023 K",
        evidence=evidence,
    )

    result = promote_axis_facts(
        [_anchor("44–4 alloy rods", material="44–4 alloy")],
        [fact],
        source_text=evidence,
    )

    assert result.accepted == ()
    issue = next(
        row
        for row in result.issues
        if row.code
        == "promotion_external_current_tensile_projection_quarantined"
    )
    assert issue.actual["removed"] == fact.model_dump()
    assert issue.actual["reason"] == "external_comparator_subject_on_current_owner"
    assert issue.actual["matched_source_sentence"] == evidence
    assert issue.actual["value_local_proposition"] == evidence
    assert issue.actual["external_subject"] == (
        "high-nb-containing tial alloys with the fully lamellar structure"
    )
    assert issue.actual["subject_cue"] == "yan et al. presented"
    assert issue.actual["embedded_owner_literal"] is None
    assert issue.actual["owner_invented"] is False


def test_current_collective_tensile_result_without_author_attribution_survives():
    evidence = (
        "The 44–4 alloy rods exhibit an elongation of approximately 40% "
        "at 1023 K."
    )
    fact = _property(
        sample="44–4 alloy rods",
        name="elongation",
        value="approximately 40",
        unit="%",
        condition="1023 K",
        evidence=evidence,
    )

    result = promote_axis_facts(
        [_anchor("44–4 alloy rods", material="44–4 alloy")],
        [fact],
        source_text=evidence,
    )

    assert result.accepted == (fact,)
    assert not any(
        row.code
        == "promotion_external_current_tensile_projection_quarantined"
        for row in result.issues
    )


def test_collective_tensile_value_without_owner_pair_is_quarantined():
    source = (
        "R1, R2 and R5 rods at RT exceeded 700 MPa (773 MPa for R1). "
        "At 1023 K, the strength reaches 644 MPa and elongations are "
        "approximately 40%."
    )
    fact = _property(
        sample="R1",
        name="ultimate tensile strength",
        value="644",
        unit="MPa",
        condition="1023 K",
        evidence="At 1023 K, the strength reaches 644 MPa.",
    )

    result = promote_axis_facts(
        [
            _anchor("R1", material="44-4 alloy"),
            _anchor("R2", material="44-4 alloy"),
            _anchor("R5", material="44-4 alloy"),
        ],
        [fact],
        source_text=source,
    )

    assert result.accepted == ()
    issue = next(
        row
        for row in result.issues
        if row.code == "promotion_collective_tensile_owner_quarantined"
    )
    assert issue.actual["removed"] == fact.model_dump()
    assert issue.actual["reason"] == "collective_value_without_bounded_owner_pair"
    assert issue.actual["source_block"]["text"] == source.lower()
    assert set(issue.actual["candidate_owners"]) == {"R1"}
    assert set(issue.actual["source_named_owners"]) == {"R1", "R2", "R5"}
    assert issue.actual["owner_invented"] is False
    assert issue.evidence == [fact.source_evidence[0]]


def test_collective_tensile_explicit_owner_value_pair_is_retained():
    source = (
        "R1, R2 and R5 rods at RT exceeded 700 MPa (773 MPa for R1). "
        "At 1023 K, the strength reaches 644 MPa."
    )
    fact = _property(
        sample="R1",
        name="ultimate tensile strength",
        value="773",
        unit="MPa",
        condition="RT",
        evidence="773 MPa for R1",
    )

    result = promote_axis_facts(
        [_anchor("R1", material="44-4 alloy"), _anchor("R2", material="44-4 alloy"), _anchor("R5", material="44-4 alloy")],
        [fact],
        source_text=source,
    )

    assert len(result.accepted) == 1
    assert result.accepted[0].data["value_raw"] == "773"
    assert not any(
        row.code == "promotion_collective_tensile_owner_quarantined"
        for row in result.issues
    )


def test_collective_tensile_comparison_without_owner_isolated_at_publish():
    source = (
        "R1, R2 and R5 rods were tested at 1023 K. All the samples exhibited "
        "elongations of approximately 40%, compared with cast alloys."
    )
    fact = _property(
        sample="R1",
        name="elongation",
        value="approximately 40",
        unit="%",
        condition="1023 K",
        evidence=(
            "All the samples exhibited elongations of approximately 40%, "
            "compared with cast alloys."
        ),
    )

    result = promote_axis_facts(
        [
            _anchor("R1", material="44-4 alloy"),
            _anchor("R2", material="44-4 alloy"),
            _anchor("R5", material="44-4 alloy"),
        ],
        [fact],
        source_text=source,
    )

    assert result.accepted == ()
    assert any(
        issue.code == "promotion_collective_ownerless_projection_quarantined"
        for issue in result.issues
    )


def test_collective_tensile_table_and_noncore_property_are_untouched():
    source = (
        "R1, R2 and R5 rods were tested.\n"
        "| Sample | UTS | Condition |\n"
        "| R1 | 773 | RT |"
    )
    table_fact = _property(
        sample="R1",
        name="ultimate tensile strength",
        value="773",
        unit="MPa",
        condition="RT",
        evidence="| R1 | 773 | RT |",
    )
    hardness = _property(
        sample="R1",
        name="hardness",
        value="300",
        unit="HV",
        condition="",
        evidence="The rods reached a hardness of 300 HV.",
    )

    result = promote_axis_facts(
        [_anchor("R1", material="44-4 alloy"), _anchor("R2", material="44-4 alloy"), _anchor("R5", material="44-4 alloy")],
        [table_fact, hardness],
        source_text=source,
    )

    assert {row.data["property_name_raw"] for row in result.accepted} == {
        "ultimate tensile strength",
        "hardness",
    }
    assert not any(
        row.code == "promotion_collective_tensile_owner_quarantined"
        for row in result.issues
    )


def test_exact_tensile_value_quarantines_same_owner_nested_threshold():
    threshold_evidence = "exceed 700 MPa (773 MPa for R1)"
    exact_evidence = "773 MPa for R1"
    source_text = (
        "The ultimate tensile strengths of these rods at RT exceed 700 MPa "
        "(773 MPa for R1) and are higher than those of cast alloys."
    )
    threshold = _property(
        sample="R1",
        name="ultimate tensile strength",
        value=">700",
        unit="MPa",
        condition="RT",
        evidence=threshold_evidence,
        candidate_id="threshold",
        evidence_unit_id="threshold",
    )
    exact = _property(
        sample="R1",
        name="ultimate tensile strength",
        value="773 MPa",
        unit="MPa",
        condition="RT",
        evidence=exact_evidence,
        confidence=0.95,
        candidate_id="exact",
        evidence_unit_id="exact",
    )

    result = promote_axis_facts(
        [_anchor("R1", material="44–4 alloy")],
        [threshold, exact],
        source_text=source_text,
    )

    assert [row.data["value_raw"] for row in result.accepted] == ["773 MPa"]
    issue = next(
        row
        for row in result.issues
        if row.code == "promotion_tensile_dominated_threshold_quarantined"
    )
    assert issue.actual["removed"]["data"]["value_raw"] == ">700"
    assert issue.actual["survivor"]["data"]["value_raw"] == "773 MPa"
    assert issue.actual["owner"] == "R1"
    assert issue.actual["tensile_family"] == "uts"
    assert issue.actual["operator"] == ">"
    assert issue.actual["bound"] == 700.0
    assert issue.actual["scalar"] == 773.0
    assert issue.actual["relation_satisfied"] is True
    assert issue.actual["bounded_source_proposition"] == threshold_evidence
    assert issue.actual["nested_owner_value_phrase"] == exact_evidence
    assert issue.actual["unique_survivor"] is True
    assert issue.actual["owner_invented"] is False


def test_tensile_threshold_relation_operators_are_respected():
    cases = (
        (">700", "773", True),
        (">=773", "773", True),
        ("<800", "773", True),
        ("<=773", "773", True),
        (">773", "773", False),
        ("<773", "773", False),
    )
    for index, (bound, scalar, dominated) in enumerate(cases):
        threshold_evidence = f"R1 had UTS {bound} MPa ({scalar} MPa for R1)"
        exact_evidence = f"{scalar} MPa for R1"
        source_text = (
            f"The ultimate tensile strength of R1 at RT was {bound} MPa "
            f"({scalar} MPa for R1) in the reported result."
        )
        threshold = _property(
            sample="R1",
            name="UTS",
            value=bound,
            unit="MPa",
            condition="RT",
            evidence=threshold_evidence,
            candidate_id=f"threshold-{index}",
            evidence_unit_id=f"threshold-{index}",
        )
        exact = _property(
            sample="R1",
            name="UTS",
            value=scalar,
            unit="MPa",
            condition="RT",
            evidence=exact_evidence,
            candidate_id=f"exact-{index}",
            evidence_unit_id=f"exact-{index}",
        )

        result = promote_axis_facts(
            [_anchor("R1", material="44–4 alloy")],
            [threshold, exact],
            source_text=source_text,
        )

        values = [row.data["value_raw"] for row in result.accepted]
        assert (bound not in values) is dominated


def test_lone_or_cross_owner_tensile_threshold_is_preserved():
    threshold_evidence = "The 44–4 alloy rods exceed 700 MPa"
    threshold = _property(
        sample="44–4 alloy rods",
        name="ultimate tensile strength",
        value=">700",
        unit="MPa",
        condition="RT",
        evidence=threshold_evidence,
        candidate_id="group-threshold",
        evidence_unit_id="group-threshold",
    )
    exact = _property(
        sample="R1",
        name="ultimate tensile strength",
        value="773",
        unit="MPa",
        condition="RT",
        evidence="773 MPa for R1",
        candidate_id="r1-exact",
        evidence_unit_id="r1-exact",
    )

    lone = promote_axis_facts(
        [_anchor("44–4 alloy rods", material="44–4 alloy")],
        [threshold],
        source_text=threshold_evidence,
    )
    cross_owner = promote_axis_facts(
        [
            _anchor("44–4 alloy rods", material="44–4 alloy"),
            _anchor("R1", material="44–4 alloy"),
        ],
        [threshold, exact],
        source_text=f"{threshold_evidence}. 773 MPa for R1.",
    )

    assert any(row.data["value_raw"] == ">700" for row in lone.accepted)
    assert {row.data["value_raw"] for row in cross_owner.accepted} == {
        ">700",
        "773",
    }
    assert not any(
        row.code == "promotion_tensile_dominated_threshold_quarantined"
        for row in (*lone.issues, *cross_owner.issues)
    )


def test_condition_or_unit_mismatch_protects_tensile_threshold():
    threshold_evidence = "R1 exceeded 700 MPa (773 MPa for R1) at RT"
    threshold = _property(
        sample="R1",
        name="ultimate tensile strength",
        value=">700",
        unit="MPa",
        condition="RT",
        evidence=threshold_evidence,
        candidate_id="threshold",
        evidence_unit_id="threshold",
    )
    condition_mismatch = _property(
        sample="R1",
        name="ultimate tensile strength",
        value="773",
        unit="MPa",
        condition="1023 K",
        evidence="773 MPa for R1 at 1023 K",
        candidate_id="condition-mismatch",
        evidence_unit_id="condition-mismatch",
    )
    unit_mismatch = _property(
        sample="R1",
        name="ultimate tensile strength",
        value="773",
        unit="GPa",
        condition="RT",
        evidence="773 GPa for R1 at RT",
        candidate_id="unit-mismatch",
        evidence_unit_id="unit-mismatch",
    )

    for exact in (condition_mismatch, unit_mismatch):
        result = promote_axis_facts(
            [_anchor("R1", material="44–4 alloy")],
            [threshold, exact],
            source_text="\n".join(
                [threshold_evidence, *exact.source_evidence]
            ),
        )
        assert any(row.data["value_raw"] == ">700" for row in result.accepted)


def test_same_owner_independent_tensile_assertions_are_not_collapsed():
    threshold = _property(
        sample="R1",
        name="ultimate tensile strength",
        value=">700",
        unit="MPa",
        condition="RT",
        evidence="R1 exceeded 700 MPa at RT",
        candidate_id="threshold",
        evidence_unit_id="threshold",
    )
    exact = _property(
        sample="R1",
        name="ultimate tensile strength",
        value="773",
        unit="MPa",
        condition="RT",
        evidence="A separate R1 test reached 773 MPa at RT",
        candidate_id="separate-exact",
        evidence_unit_id="separate-exact",
    )

    result = promote_axis_facts(
        [_anchor("R1", material="44–4 alloy")],
        [threshold, exact],
        source_text=(
            "R1 exceeded 700 MPa at RT. "
            "A separate R1 test reached 773 MPa at RT."
        ),
    )

    assert not any(
        row.code == "promotion_tensile_dominated_threshold_quarantined"
        for row in result.issues
    )


def test_multiple_exact_tensile_survivors_leave_threshold_unchanged():
    threshold_evidence = (
        "R1 exceeded 700 MPa (773 MPa for R1 and 758 MPa for R1)"
    )
    threshold = _property(
        sample="R1",
        name="ultimate tensile strength",
        value=">700",
        unit="MPa",
        condition="RT",
        evidence=threshold_evidence,
        candidate_id="threshold",
        evidence_unit_id="threshold",
    )
    exact_rows = [
        _property(
            sample="R1",
            name="ultimate tensile strength",
            value=value,
            unit="MPa",
            condition="RT",
            evidence=f"{value} MPa for R1",
            candidate_id=f"exact-{index}",
            evidence_unit_id=f"exact-{index}",
        )
        for index, value in enumerate(("773", "758"))
    ]

    result = promote_axis_facts(
        [_anchor("R1", material="44–4 alloy")],
        [threshold, *exact_rows],
        source_text=threshold_evidence,
    )

    assert not any(
        row.code == "promotion_tensile_dominated_threshold_quarantined"
        for row in result.issues
    )


def test_approximate_range_or_subtype_mismatch_does_not_dominate_threshold():
    cases = (
        ("ultimate tensile strength", "~773"),
        ("ultimate tensile strength", "770–776"),
        ("uniform elongation", "12"),
    )
    for index, (exact_name, exact_value) in enumerate(cases):
        unit = "%" if "elongation" in exact_name else "MPa"
        threshold_name = (
            "total elongation" if "elongation" in exact_name else exact_name
        )
        threshold_value = ">10" if unit == "%" else ">700"
        threshold_evidence = (
            f"R1 had {threshold_name} {threshold_value} {unit} "
            f"({exact_value} {unit} for R1)"
        )
        threshold = _property(
            sample="R1",
            name=threshold_name,
            value=threshold_value,
            unit=unit,
            condition="RT",
            evidence=threshold_evidence,
            candidate_id=f"threshold-{index}",
            evidence_unit_id=f"threshold-{index}",
        )
        exact = _property(
            sample="R1",
            name=exact_name,
            value=exact_value,
            unit=unit,
            condition="RT",
            evidence=f"{exact_value} {unit} for R1",
            candidate_id=f"exact-{index}",
            evidence_unit_id=f"exact-{index}",
        )

        result = promote_axis_facts(
            [_anchor("R1", material="44–4 alloy")],
            [threshold, exact],
            source_text=(
                f"The reported result for R1 at RT was {threshold_evidence}."
            ),
        )

        assert not any(
            row.code == "promotion_tensile_dominated_threshold_quarantined"
            for row in result.issues
        )


def test_tensile_threshold_dominance_is_input_order_deterministic():
    threshold_evidence = "exceed 700 MPa (773 MPa for R1)"
    source_text = (
        "The ultimate tensile strengths of these rods at RT exceed 700 MPa "
        "(773 MPa for R1)."
    )
    threshold = _property(
        sample="R1",
        name="ultimate tensile strength",
        value=">700",
        unit="MPa",
        condition="RT",
        evidence=threshold_evidence,
        candidate_id="threshold",
        evidence_unit_id="threshold",
    )
    exact = _property(
        sample="R1",
        name="ultimate tensile strength",
        value="773",
        unit="MPa",
        condition="RT",
        evidence="773 MPa for R1",
        candidate_id="exact",
        evidence_unit_id="exact",
    )

    signatures = []
    for facts in ([threshold, exact], [exact, threshold]):
        result = promote_axis_facts(
            [_anchor("R1", material="44–4 alloy")],
            facts,
            source_text=source_text,
        )
        issue = next(
            row
            for row in result.issues
            if row.code == "promotion_tensile_dominated_threshold_quarantined"
        )
        signatures.append(
            (
                tuple(row.data["value_raw"] for row in result.accepted),
                issue.actual["removed"]["data"]["value_raw"],
                issue.actual["survivor"]["data"]["value_raw"],
                issue.actual["bounded_source_proposition"],
            )
        )

    assert signatures[0] == signatures[1]


def test_identical_unresolved_owner_envelope_can_prove_threshold_dominance():
    threshold_evidence = "exceed 700 MPa (773 MPa for R1)"
    threshold = _property(
        sample="R1",
        name="UTS",
        value=">700",
        unit="MPa",
        condition="RT",
        evidence=threshold_evidence,
        candidate_id="threshold",
        evidence_unit_id="threshold",
    )
    exact = _property(
        sample="R1",
        name="UTS",
        value="773",
        unit="MPa",
        condition="RT",
        evidence="773 MPa for R1",
        candidate_id="exact",
        evidence_unit_id="exact",
    )

    result = promote_axis_facts(
        [
            _anchor("R1", material="44–4 alloy", state="state A"),
            _anchor("R1", material="44–4 alloy", state="state B"),
        ],
        [threshold, exact],
        source_text=(
            "The UTS of R1 at RT exceeds 700 MPa (773 MPa for R1)."
        ),
    )

    assert [row.data["value_raw"] for row in result.accepted] == ["773"]
    issue = next(
        row
        for row in result.issues
        if row.code == "promotion_tensile_dominated_threshold_quarantined"
    )
    assert issue.actual["owner_id"] is None
    assert issue.actual["owner_coordinate_kind"] == (
        "identical_candidate_envelope"
    )
    assert len(issue.actual["owner_candidate_ids"]) == 2
    assert issue.actual["owner_role"] == "Target"
    assert issue.actual["owner_data_nature"] == "Experimental"


def test_experimental_tensile_restatement_merges_into_direct_same_owner_result():
    direct = _property(
        sample="HT-Alloy",
        name="YS",
        value="~748",
        unit="MPa",
        condition="",
        evidence="HT-Alloy had a YS of 748 MPa.",
        candidate_id="direct",
    )
    restatement = _property(
        sample="HT-Alloy",
        name="experimental YS from tensile tests",
        value="~748.0 MPa",
        unit="MPa",
        condition="",
        evidence=(
            "The estimate is close to the experimental value from the tensile "
            "tests (748.0 MPa)."
        ),
        candidate_id="restatement",
    )

    result = promote_axis_facts(
        [_anchor("HT-Alloy")],
        [restatement, direct],
        source_text=(
            "HT-Alloy had a YS of 748 MPa. The estimate is close to the "
            "experimental value from the tensile tests (748.0 MPa)."
        ),
    )

    assert len(result.accepted) == 1
    survivor = result.accepted[0]
    assert survivor.data["property_name_raw"] == "YS"
    assert survivor.data["value_raw"] == "~748"
    assert survivor.source_evidence == [
        "HT-Alloy had a YS of 748 MPa.",
        (
            "The estimate is close to the experimental value from the tensile "
            "tests (748.0 MPa)."
        ),
    ]
    issue = next(
        row
        for row in result.issues
        if row.code == "core_tensile_experimental_restatement_shadow_quarantined"
    )
    assert issue.actual["removed"]["data"]["property_id_candidate"] == (
        "restatement"
    )
    assert issue.actual["survivor_after"]["data"]["property_id_candidate"] == (
        "direct"
    )


def test_experimental_tensile_restatement_with_different_condition_is_not_merged():
    direct = _property(
        sample="HT-Alloy",
        name="YS",
        value="748",
        unit="MPa",
        condition="RT",
        evidence="At RT, HT-Alloy had a YS of 748 MPa.",
        candidate_id="direct",
    )
    restatement = _property(
        sample="HT-Alloy",
        name="experimental YS from tensile tests",
        value="748.0",
        unit="MPa",
        condition="650 °C",
        evidence=(
            "At 650 °C, the estimate is close to the experimental value from "
            "the tensile tests (748.0 MPa)."
        ),
        candidate_id="restatement",
    )

    result = promote_axis_facts(
        [_anchor("HT-Alloy")],
        [restatement, direct],
        source_text=(
            "At RT, HT-Alloy had a YS of 748 MPa. At 650 °C, the estimate is "
            "close to the experimental value from the tensile tests "
            "(748.0 MPa)."
        ),
    )

    assert len(result.accepted) == 2
    assert not any(
        row.code == "core_tensile_experimental_restatement_shadow_quarantined"
        for row in result.issues
    )


def test_experimental_tensile_restatement_merges_across_physical_owner_nodes():
    direct = _property(
        sample="HT-Alloy",
        name="YS",
        value="748",
        unit="MPa",
        condition="",
        evidence="HT-Alloy shows significant increases in YS (~748 MPa).",
        candidate_id="direct",
    )
    restatement = _property(
        sample="HT-Alloy",
        name="experimental YS from tensile tests",
        value="748.0",
        unit="MPa",
        condition="",
        evidence=(
            "The estimate is close to the experimental value from the tensile "
            "tests (~748.0 MPa)."
        ),
        candidate_id="restatement",
    )
    anchors = [
        _anchor("AP-Alloy", material="Alloy", state="as-printed"),
        _anchor(
            "HT-Alloy",
            material="HT-Alloy",
            state="HT",
            evidence="HT-Alloy shows superior mechanical performance.",
        ),
        _anchor(
            "HT-Alloy",
            material="Alloy matrix",
            state="wall region",
            evidence="The HT-Alloy wall region contains the matrix.",
        ),
    ]

    result = promote_axis_facts(
        anchors,
        [restatement, direct],
        source_text=(
            "HT-Alloy shows significant increases in YS (~748 MPa). The "
            "estimate is close to the experimental value from the tensile "
            "tests (~748.0 MPa)."
        ),
    )

    assert len(result.accepted) == 1
    assert result.accepted[0].data["property_id_candidate"] == "direct"
    issue = next(
        row
        for row in result.issues
        if row.code == "core_tensile_experimental_restatement_shadow_quarantined"
    )
    assert issue.actual["owner_coordinate"].startswith(
        "physical_owner_envelope_"
    )


def test_unconditioned_restatement_merges_into_unique_richer_direct_result():
    direct = _property(
        sample="HT-Alloy",
        name="YS",
        value="748",
        unit="MPa",
        condition="ambient-temperature",
        evidence="HT-Alloy had a YS of 748 MPa at ambient temperature.",
        candidate_id="direct",
    )
    restatement = _property(
        sample="HT-Alloy",
        name="experimental YS from tensile tests",
        value="748.0",
        unit="MPa",
        condition="",
        evidence=(
            "The estimate is close to the experimental value from the tensile "
            "tests (748.0 MPa)."
        ),
        candidate_id="restatement",
    )

    result = promote_axis_facts(
        [_anchor("HT-Alloy")],
        [restatement, direct],
        source_text=(
            "HT-Alloy had a YS of 748 MPa at ambient temperature. The estimate "
            "is close to the experimental value from the tensile tests "
            "(748.0 MPa)."
        ),
    )

    assert len(result.accepted) == 1
    assert result.accepted[0].data["property_id_candidate"] == "direct"
    issue = next(
        row
        for row in result.issues
        if row.code == "core_tensile_experimental_restatement_shadow_quarantined"
    )
    assert issue.actual["condition"] == ""
    assert issue.actual["survivor_condition"] == "ambient temperature"


def test_generic_paired_tensile_summary_merges_into_unique_richer_table_specimen():
    summary = (
        "Ti-6Al-4V alloys with ultimate tensile strength and total elongation "
        "of 1190 MPa and 16.5%, respectively, are produced."
    )
    table_row = "| 3-2 | 2 | 43.85 | 1190 ± 12.4 | 16.5 ± 1.3 |"
    generic_uts = _property(
        sample="Ti-6Al-4V",
        name="ultimate tensile strength",
        value="1190",
        unit="MPa",
        condition="",
        evidence=summary,
        candidate_id="generic-uts",
        evidence_unit_id="generic-uts",
    )
    generic_te = _property(
        sample="Ti-6Al-4V",
        name="total elongation",
        value="16.5",
        unit="%",
        condition="",
        evidence=summary,
        candidate_id="generic-te",
        evidence_unit_id="generic-te",
    )
    table_uts = _property(
        sample="3-2",
        name="ultimate tensile strength",
        value="1190 ± 12.4",
        unit="MPa",
        condition="",
        evidence=table_row,
        candidate_id="table-uts",
        evidence_unit_id="table-uts",
    )
    table_uts.data["data_source"] = "table"
    table_te = _property(
        sample="3-2",
        name="total elongation",
        value="16.5 ± 1.3",
        unit="%",
        condition="",
        evidence=table_row,
        candidate_id="table-te",
        evidence_unit_id="table-te",
    )
    table_te.data["data_source"] = "table"

    result = promote_axis_facts(
        [
            _anchor("Ti-6Al-4V", material="Ti-6Al-4V alloy"),
            _anchor("3-2", material="Ti-6Al-4V"),
        ],
        [generic_uts, generic_te, table_uts, table_te],
        source_text=f"{summary}\n\n{table_row}",
    )

    assert {
        (row.sample_id_raw, row.data["value_raw"])
        for row in result.accepted
    } == {
        ("3-2", "1190 ± 12.4"),
        ("3-2", "16.5 ± 1.3"),
    }
    issues = [
        row
        for row in result.issues
        if row.code == "core_tensile_generic_summary_shadow_quarantined"
    ]
    assert len(issues) == 2
    for issue in issues:
        assert issue.actual["generic_summary"] is True
        assert issue.actual["material_lineage"] == "ti 6al 4v"
        assert issue.actual["unique_survivor"] is True
        assert issue.actual["owner_invented"] is False
        assert issue.actual["removed"]["sample_id_raw"] == "Ti-6Al-4V"
        assert issue.actual["survivor_before"]["sample_id_raw"] == "3-2"
        assert issue.actual["survivor_after"]["sample_id_raw"] == "3-2"
        merged_evidence = issue.actual["survivor_after"]["source_evidence"]
        assert merged_evidence[0] == table_row
        assert summary in merged_evidence


def test_generic_summary_requires_one_exact_source_bound_state_anchor():
    summary = (
        "Ti alloy samples with ultimate tensile strength and total elongation "
        "of 1190 MPa and 16.5%, respectively, were produced."
    )
    generic = _property(
        sample="Ti alloy",
        name="ultimate tensile strength",
        value="1190",
        unit="MPa",
        condition="",
        evidence=summary,
        candidate_id="generic",
        evidence_unit_id="generic",
    )
    table_row = "| 3-2 | 1190 ± 12.4 MPa |"
    survivor = _property(
        sample="3-2",
        name="ultimate tensile strength",
        value="1190 ± 12.4",
        unit="MPa",
        condition="",
        evidence=table_row,
        candidate_id="table",
        evidence_unit_id="table",
    )
    survivor.data["data_source"] = "table"
    source_bound = _anchor(
        "Ti alloy",
        material="Ti alloy",
        state="produced with selected parameters",
        evidence=summary,
    )
    competing = _anchor(
        "Ti alloy",
        material="Ti alloy",
        state="as-built",
        evidence="The as-built Ti alloy samples contained martensite.",
    ).model_copy(update={"data_nature": "Literature_Experimental"})

    unique = promote_axis_facts(
        [source_bound, competing, _anchor("3-2", material="Ti alloy")],
        [generic, survivor],
        source_text=f"{summary}\n\n{table_row}",
    )

    issue = next(
        row
        for row in unique.issues
        if row.code == "core_tensile_generic_summary_shadow_quarantined"
    )
    assert len(issue.actual["generic_owner_ids"]) == 1
    assert issue.actual["owner_invented"] is False

    duplicate_source_anchors = [
        _anchor(
            "Ti alloy",
            material="Ti alloy",
            state=state,
            evidence=summary,
        )
        for state in ("state A", "state B")
    ]
    ambiguous = promote_axis_facts(
        [*duplicate_source_anchors, _anchor("3-2", material="Ti alloy")],
        [generic, survivor],
        source_text=f"{summary}\n\n{table_row}",
    )

    assert any(
        row.sample_id_raw == "Ti alloy"
        and row.data.get("value_raw") == "1190"
        for row in ambiguous.accepted
    )
    assert not any(
        row.code == "core_tensile_generic_summary_shadow_quarantined"
        for row in ambiguous.issues
    )


def test_generic_tensile_summary_requires_one_survivor_and_not_an_average():
    summary = (
        "Ti alloy samples with ultimate tensile strength and total elongation "
        "of 1190 MPa and 16.5%, respectively, were produced."
    )
    generic = _property(
        sample="Ti alloy",
        name="ultimate tensile strength",
        value="1190",
        unit="MPa",
        condition="",
        evidence=summary,
        candidate_id="generic",
        evidence_unit_id="generic",
    )
    survivors = []
    for sample in ("3-2", "4-1"):
        row = f"| {sample} | 1190 ± 12.4 MPa |"
        survivor = _property(
            sample=sample,
            name="ultimate tensile strength",
            value="1190 ± 12.4",
            unit="MPa",
            condition="",
            evidence=row,
            candidate_id=f"table-{sample}",
            evidence_unit_id=f"table-{sample}",
        )
        survivor.data["data_source"] = "table"
        survivors.append(survivor)

    ambiguous = promote_axis_facts(
        [
            _anchor("Ti alloy", material="Ti alloy"),
            _anchor("3-2", material="Ti alloy"),
            _anchor("4-1", material="Ti alloy"),
        ],
        [generic, *survivors],
        source_text="\n\n".join(
            [summary, *(row.source_evidence[0] for row in survivors)]
        ),
    )

    average_evidence = (
        "The Ti alloy samples had an average ultimate tensile strength of "
        "1190 MPa."
    )
    average = _property(
        sample="Ti alloy",
        name="ultimate tensile strength",
        value="1190",
        unit="MPa",
        condition="",
        evidence=average_evidence,
        candidate_id="average",
        evidence_unit_id="average",
    )
    independent_average = promote_axis_facts(
        [
            _anchor("Ti alloy", material="Ti alloy"),
            _anchor("3-2", material="Ti alloy"),
        ],
        [average, survivors[0]],
        source_text=f"{average_evidence}\n\n{survivors[0].source_evidence[0]}",
    )

    assert generic in ambiguous.accepted
    assert average in independent_average.accepted
    assert not any(
        row.code == "core_tensile_generic_summary_shadow_quarantined"
        for row in (*ambiguous.issues, *independent_average.issues)
    )


def test_generic_tensile_summary_preserves_condition_or_lineage_mismatch():
    summary = (
        "Ti alloy samples with ultimate tensile strength and total elongation "
        "of 1190 MPa and 16.5%, respectively, were produced."
    )
    generic = _property(
        sample="Ti alloy",
        name="ultimate tensile strength",
        value="1190",
        unit="MPa",
        condition="room temperature",
        evidence=summary,
        candidate_id="generic",
        evidence_unit_id="generic",
    )
    table_row = "| 3-2 | 1190 ± 12.4 MPa at 650 °C |"
    survivor = _property(
        sample="3-2",
        name="ultimate tensile strength",
        value="1190 ± 12.4",
        unit="MPa",
        condition="650 °C",
        evidence=table_row,
        candidate_id="table",
        evidence_unit_id="table",
    )
    survivor.data["data_source"] = "table"

    condition_mismatch = promote_axis_facts(
        [
            _anchor("Ti alloy", material="Ti alloy"),
            _anchor("3-2", material="Ti alloy"),
        ],
        [generic, survivor],
        source_text=f"{summary}\n\n{table_row}",
    )
    lineage_mismatch = promote_axis_facts(
        [
            _anchor("Ti alloy", material="Ti alloy"),
            _anchor("3-2", material="Ni alloy"),
        ],
        [generic, survivor.model_copy(deep=True, update={"data": {
            **survivor.data,
            "test_condition_raw": "room temperature",
        }})],
        source_text=f"{summary}\n\n{table_row}",
    )

    assert any(
        row.sample_id_raw == "Ti alloy"
        and row.data.get("value_raw") == "1190"
        for row in condition_mismatch.accepted
    )
    assert any(
        row.sample_id_raw == "Ti alloy"
        and row.data.get("value_raw") == "1190"
        for row in lineage_mismatch.accepted
    )


def test_ownerless_tensile_group_extrema_are_quarantined_with_full_audit():
    te_evidence = (
        "the highest TE in the alloys with a UTS of ~1060 MPa was 14%"
    )
    uts_evidence = (
        "the highest UTS among alloys with ~18% of TE was 945 MPa"
    )
    te = _property(
        sample="Table 1 combinations",
        name="TE",
        value="14%",
        unit="%",
        condition="",
        evidence=te_evidence,
        candidate_id="frontier-te",
        evidence_unit_id="frontier-te",
    )
    uts = _property(
        sample="Table 1 combinations",
        name="UTS",
        value="945 MPa",
        unit="MPa",
        condition="",
        evidence=uts_evidence,
        candidate_id="frontier-uts",
        evidence_unit_id="frontier-uts",
    )

    result = promote_axis_facts(
        [_anchor("Table 1 combinations", material="Ti alloy")],
        [te, uts],
        source_text=f"{te_evidence}. {uts_evidence}.",
    )

    assert result.accepted == ()
    issues = [
        row
        for row in result.issues
        if row.code == "promotion_tensile_group_extremum_quarantined"
    ]
    assert len(issues) == 2
    for issue in issues:
        assert issue.actual["removed"]["sample_id_raw"] == (
            "Table 1 combinations"
        )
        assert issue.actual["extremum_cue"] == "highest"
        assert issue.actual["collective_scope"]
        assert issue.actual["companion_tensile_family"]
        assert issue.actual["named_owner_ids"] == []
        assert issue.actual["owner_invented"] is False


def test_group_extremum_gate_preserves_named_table_or_unconstrained_results():
    cases = []
    named_evidence = (
        "Sample A had the highest UTS among the alloys with ~18% TE at 945 MPa."
    )
    named = _property(
        sample="Sample A",
        name="UTS",
        value="945",
        unit="MPa",
        condition="",
        evidence=named_evidence,
        candidate_id="named",
        evidence_unit_id="named",
    )
    cases.append(([_anchor("Sample A", material="Ti alloy")], named, named_evidence))

    unconstrained_evidence = "The highest UTS among the alloys was 945 MPa."
    unconstrained = _property(
        sample="Ti alloys",
        name="UTS",
        value="945",
        unit="MPa",
        condition="",
        evidence=unconstrained_evidence,
        candidate_id="unconstrained",
        evidence_unit_id="unconstrained",
    )
    cases.append(([_anchor("Ti alloys", material="Ti alloy")], unconstrained, unconstrained_evidence))

    table_evidence = "| Sample | UTS maximum | TE |\n| A | 945 MPa | 18% |"
    table = _property(
        sample="Sample A",
        name="UTS maximum",
        value="945",
        unit="MPa",
        condition="",
        evidence="| A | 945 MPa | 18% |",
        candidate_id="table",
        evidence_unit_id="table",
    )
    table.data["data_source"] = "table"
    cases.append(([_anchor("Sample A", material="Ti alloy")], table, table_evidence))

    for anchors, fact, source_text in cases:
        result = promote_axis_facts(anchors, [fact], source_text=source_text)
        assert fact in result.accepted
        assert not any(
            row.code == "promotion_tensile_group_extremum_quarantined"
            for row in result.issues
        )


def test_new_tensile_precision_gates_are_semantically_input_order_deterministic():
    summary = (
        "Ti alloy samples with ultimate tensile strength and total elongation "
        "of 1190 MPa and 16.5%, respectively, were produced."
    )
    table_row = "| 3-2 | 1190 ± 12.4 MPa |"
    generic = _property(
        sample="Ti alloy",
        name="UTS",
        value="1190",
        unit="MPa",
        condition="",
        evidence=summary,
        candidate_id="generic",
        evidence_unit_id="generic",
    )
    survivor = _property(
        sample="3-2",
        name="UTS",
        value="1190 ± 12.4",
        unit="MPa",
        condition="",
        evidence=table_row,
        candidate_id="table",
        evidence_unit_id="table",
    )
    survivor.data["data_source"] = "table"
    extremum_evidence = (
        "the highest UTS among alloys with ~18% TE was 945 MPa"
    )
    extremum = _property(
        sample="Table 1 combinations",
        name="UTS",
        value="945",
        unit="MPa",
        condition="",
        evidence=extremum_evidence,
        candidate_id="frontier",
        evidence_unit_id="frontier",
    )
    anchors = [
        _anchor("Ti alloy", material="Ti alloy"),
        _anchor("3-2", material="Ti alloy"),
        _anchor("Table 1 combinations", material="Ti alloy"),
    ]
    source_text = f"{summary}\n\n{extremum_evidence}\n\n{table_row}"

    signatures = []
    for facts in ([generic, survivor, extremum], [extremum, survivor, generic]):
        result = promote_axis_facts(anchors, facts, source_text=source_text)
        accepted = sorted(
            (row.sample_id_raw, row.data.get("value_raw"))
            for row in result.accepted
        )
        issues = sorted(
            (
                row.code,
                row.actual["removed"]["sample_id_raw"],
                row.actual["removed"]["data"]["value_raw"],
            )
            for row in result.issues
            if row.code in {
                "core_tensile_generic_summary_shadow_quarantined",
                "promotion_tensile_group_extremum_quarantined",
            }
        )
        signatures.append((accepted, issues))

    assert signatures[0] == signatures[1]


def test_current_tensile_subject_with_trailing_citation_is_preserved():
    evidence = "Alloy 625 had a UTS of 780 MPa in this study [11]."
    fact = _property(
        sample="alloy 625",
        name="ultimate tensile strength",
        value="780",
        unit="MPa",
        condition="",
        evidence=evidence,
    )

    result = promote_axis_facts(
        [_anchor("alloy 625", material="alloy 625")],
        [fact],
        source_text=evidence,
    )

    assert result.accepted == (fact,)
    assert not any(
        issue.code
        == "promotion_external_current_tensile_projection_quarantined"
        for issue in result.issues
    )


def test_current_and_comparator_tensile_values_are_filtered_value_locally():
    evidence = (
        "The binder-jet alloy 625 reached a UTS of 780 MPa, compared with "
        "cast alloy 625 [11] at 710 MPa."
    )
    current = _property(
        sample="alloy 625",
        name="ultimate tensile strength",
        value="780",
        unit="MPa",
        condition="",
        evidence=evidence,
        candidate_id="current-uts",
        evidence_unit_id="current-uts",
    )
    comparator = _property(
        sample="cast alloy 625",
        name="ultimate tensile strength",
        value="710",
        unit="MPa",
        condition="",
        evidence=evidence,
        candidate_id="comparator-uts",
        evidence_unit_id="comparator-uts",
    )

    result = promote_axis_facts(
        [_anchor("alloy 625", material="alloy 625")],
        [current, comparator],
        source_text=evidence,
    )

    assert result.accepted == (current,)
    issue = next(
        issue
        for issue in result.issues
        if issue.code
        == "promotion_unbound_external_tensile_quarantined"
    )
    assert issue.actual["removed"]["data"] == comparator.model_dump()["data"]
    assert issue.actual["removed"]["sample_id_raw"] == "cast alloy 625"
    assert issue.actual["reason"] == "external_comparator_without_reference_owner"
    assert issue.actual["value_local_proposition"] == (
        "compared with cast alloy 625 [11] at 710 MPa"
    )
    assert issue.actual["external_subject"] == "cast alloy 625 [11]"
    assert issue.actual["embedded_owner_literal"] is None


def test_ambiguous_repeated_tensile_value_is_left_to_existing_owner_gate():
    evidence = (
        "Alloy 625 reached a UTS of 710 MPa, while cast alloy 625 [11] also "
        "reached a UTS of 710 MPa."
    )
    fact = _property(
        sample="alloy 625",
        name="ultimate tensile strength",
        value="710",
        unit="MPa",
        condition="",
        evidence=evidence,
    )

    result = promote_axis_facts(
        [_anchor("alloy 625", material="alloy 625")],
        [fact],
        source_text=evidence,
    )

    assert result.accepted == (fact,)
    assert not any(
        issue.code
        == "promotion_external_current_tensile_projection_quarantined"
        for issue in result.issues
    )


def test_direct_author_tensile_uses_unique_existing_rich_reference_anchor():
    evidence = (
        "Mostafaei et al. reported values of UTS and YS of 612 MPa "
        "and 327 MPa, respectively."
    )
    owner = "binder jetting as-sintered (Mostafaei et al., 2016b)"
    fact = _property(
        sample=owner,
        name="ultimate tensile strength",
        value="612",
        unit="MPa",
        condition="",
        evidence=evidence,
    )
    anchor = _anchor(
        owner,
        material="Inconel 625",
        state="as-sintered",
        role="Reference",
        evidence=f"for binder jetting as-sintered parts, {evidence}",
    )

    result = promote_axis_facts([anchor], [fact], source_text=evidence)

    assert result.accepted == (fact,)
    assert not any(
        issue.code == "promotion_unbound_external_tensile_quarantined"
        for issue in result.issues
    )


def test_direct_author_tensile_does_not_use_reference_anchor_without_same_assertion():
    evidence = "Mostafaei et al. reported a UTS of 612 MPa."
    owner = "binder jetting as-sintered (Mostafaei et al., 2016b)"
    fact = _property(
        sample=owner,
        name="ultimate tensile strength",
        value="612",
        unit="MPa",
        condition="",
        evidence=evidence,
    )
    anchor = _anchor(
        owner,
        material="Inconel 625",
        state="as-sintered",
        role="Reference",
        evidence="Mostafaei et al. reported porosity after sintering.",
    )

    result = promote_axis_facts([anchor], [fact], source_text=evidence)

    assert result.accepted == ()
    assert any(
        issue.code == "promotion_unbound_external_tensile_quarantined"
        for issue in result.issues
    )


def test_literal_author_year_tensile_uses_exact_existing_reference_anchor():
    evidence = "ductility of 33% ± 1% (Marchese et al., 2018)"
    owner = "LPBF as-fabricated (Marchese et al., 2018)"
    fact = _property(
        sample=owner,
        name="ductility",
        value="33 ± 1",
        unit="%",
        condition="",
        evidence=evidence,
    )
    anchor = _anchor(
        owner,
        material="Inconel 625",
        state="as-fabricated",
        role="Reference",
        evidence=(
            "The as-fabricated values included UTS of 1041 ± 36 MPa and "
            + evidence
        ),
    )

    result = promote_axis_facts([anchor], [fact], source_text=evidence)

    assert result.accepted == (fact,)
    assert not any(
        issue.code == "promotion_unbound_external_tensile_quarantined"
        for issue in result.issues
    )


def test_cited_tensile_multi_state_reference_without_coordinate_is_quarantined():
    evidence = (
        "Mostafaei et al. reported values of UTS, YS, and strain "
        "of 612 MPa, 327 MPa, and 41%."
    )
    fact = _property(
        sample="Mostafaei et al., 2016b",
        name="yield strength",
        value="327 MPa",
        unit="MPa",
        condition="",
        evidence=evidence,
    )
    anchors = [
        _anchor(
            "Mostafaei et al., 2016b",
            role="Reference",
            state="solutionizing treatment",
        ),
        _anchor(
            "Mostafaei et al., 2016b",
            role="Reference",
            state="binder jetting as-sintered",
        ),
        _anchor(
            "Mostafaei et al., 2016b",
            role="Reference",
            state="aged condition",
        ),
    ]

    result = promote_axis_facts(anchors, [fact], source_text=evidence)

    assert result.accepted == ()
    issue = next(
        issue
        for issue in result.issues
        if issue.code == "promotion_unbound_external_tensile_quarantined"
    )
    assert issue.actual["reason"] == "external_prose_without_owner_coordinate"
    assert issue.actual["owner_candidates"] == [
        "Mostafaei et al., 2016b",
        "Mostafaei et al., 2016b",
        "Mostafaei et al., 2016b",
    ]


def test_cited_tensile_condition_routes_to_unique_reference_treatment_state():
    evidence = (
        "UTS, YS and elongation were 697 MPa, 329 MPa, and 30%, "
        "following aging for 60 h at 745 °C (Mostafaei et al., 2016b)."
    )
    fact = _property(
        sample="Mostafaei et al., 2016b",
        name="yield strength",
        value="329",
        unit="MPa",
        condition="aging for 60 h at 745 °C",
        evidence=evidence,
    )
    anchors = [
        _anchor(
            "Mostafaei et al., 2016b",
            role="Reference",
            state="solutionizing treatment",
        ),
        _anchor(
            "Mostafaei et al., 2016b",
            role="Reference",
            state="binder jetting as-sintered",
        ),
        _anchor(
            "Mostafaei et al., 2016b",
            role="Reference",
            state="aged condition",
        ),
    ]

    result = promote_axis_facts(anchors, [fact], source_text=evidence)

    assert len(result.accepted) == 1
    assert result.accepted[0].sample_id_raw == "Mostafaei et al., 2016b"
    assert result.accepted[0].data["material_state"] == "aged condition"
    assert any(
        issue.code == "promotion_external_tensile_reference_state_reassigned"
        for issue in result.issues
    )


def test_table_value_on_existing_state_sibling_is_not_kept_on_base_owner():
    source = (
        "| Sample | Density (g/cm3) |\n"
        "| --- | --- |\n"
        "| A1 | 8.40 |\n"
        "| A1 [HIPed] | 8.55 |"
    )
    fact = _property(
        sample="A1",
        name="density",
        value="8.55",
        unit="g/cm3",
        condition="",
        evidence=source,
    )
    result = promote_axis_facts(
        [
            _anchor("A1", material="Alloy A"),
            _anchor("A1 [HIPed]", material="Alloy A", state="HIPed"),
        ],
        [fact],
        source_text=source,
    )

    assert result.accepted == ()
    issue = next(
        issue
        for issue in result.issues
        if issue.code == "promotion_table_owner_value_ambiguous_quarantined"
    )
    assert issue.actual["reason"] == "value_bound_to_existing_state_sibling"
    assert issue.actual["state_sibling_value_hits"][0]["owner"] == "A1 [HIPed]"


def test_table_owner_row_condition_suffix_preserves_unique_value():
    source = (
        "| Samples | yield strength (MPa) | Elongation (%) |\n"
        "| --- | --- | --- |\n"
        "| AF-RT | 482 | 9 |\n"
        "| AF-250 $ \\mathring{A} $ $ \\mathring{C} $ | 355 | 16 |"
    )
    evidence = (
        "| Samples | yield strength (MPa) | Elongation (%) |\n"
        "| AF-250 $ \\mathring{A} $ $ \\mathring{C} $ | 355 | 16 |"
    )
    fact_rt = _property(
        sample="AF",
        name="elongation",
        value="9",
        unit="%",
        condition="RT",
        evidence="| Samples | yield strength (MPa) | Elongation (%) |\n| AF-RT | 482 | 9 |",
    )
    fact_250 = _property(
        sample="AF",
        name="elongation",
        value="16",
        unit="%",
        condition="250 °C",
        evidence=evidence,
    )

    result = promote_axis_facts(
        [_anchor("AF")], [fact_rt, fact_250], source_text=source
    )

    assert result.accepted == (fact_rt, fact_250)
    assert not any(
        issue.code == "promotion_table_owner_condition_ambiguous_quarantined"
        for issue in result.issues
    )


def test_unasserted_process_stage_from_sample_label_is_quarantined():
    evidence = "as-built EBAM Ti-6Al-4V sample"
    fact = _processing(
        sample="EBAM",
        process="electron beam additive manufacturing",
        evidence=evidence,
    )

    result = promote_axis_facts([_anchor("EBAM")], [fact], source_text=evidence)

    assert result.accepted == ()
    issue = next(
        issue
        for issue in result.issues
        if issue.code == "promotion_processing_stage_unasserted_quarantined"
    )
    assert issue.actual["reason"] == "process_stage_without_source_assertion"
    assert issue.actual["removed"] == fact.model_dump()


def test_process_stage_with_only_grounded_process_noun_is_quarantined():
    evidence = "EBAM samples showed a lower cooling rate than the wrought material."
    fact = _processing(
        sample="EBAM",
        process="electron beam additive manufacturing",
        evidence=evidence,
    )

    result = promote_axis_facts([_anchor("EBAM")], [fact], source_text=evidence)

    assert result.accepted == ()
    issue = next(
        issue
        for issue in result.issues
        if issue.code == "promotion_processing_stage_unasserted_quarantined"
    )
    assert issue.actual["reason"] == "process_stage_without_source_assertion"
    assert issue.actual["removed"] == fact.model_dump()


def test_qualitative_comparative_process_parameter_from_result_is_quarantined():
    evidence = (
        "The WAAM material did not show significant anisotropy, likely due to "
        "the higher cooling rate."
    )
    fact = _processing(
        sample="WAAM",
        process="WAAM",
        evidence=evidence,
        parameters=[
            {
                "parameter_name_raw": "cooling rate",
                "value_raw": "higher",
                "unit_raw": "",
                "source_evidence": [evidence],
            }
        ],
    )

    result = promote_axis_facts([_anchor("WAAM")], [fact], source_text=evidence)

    assert result.accepted == ()
    assert any(
        issue.code == "promotion_processing_result_or_hypothetical_stage_quarantined"
        for issue in result.issues
    )


def test_explicit_process_event_survives_unasserted_stage_gate():
    evidence = "EBAM specimens were built in a vacuum chamber."
    fact = _processing(
        sample="EBAM",
        process="electron beam additive manufacturing",
        evidence=evidence,
    )

    result = promote_axis_facts([_anchor("EBAM")], [fact], source_text=evidence)

    assert result.accepted == (fact,)
    assert not any(
        issue.code == "promotion_processing_stage_unasserted_quarantined"
        for issue in result.issues
    )


def test_processing_result_explanation_is_not_promoted_as_stage():
    evidence = (
        "The high build temperature of the EBAM process usually results in "
        "decomposition of the metastable phase."
    )
    fact = _processing(
        sample="EBAM",
        process="electron beam additive manufacturing",
        evidence=evidence,
    )

    result = promote_axis_facts([_anchor("EBAM")], [fact], source_text=evidence)

    assert result.accepted == ()
    issue = next(
        issue
        for issue in result.issues
        if issue.code
        == "promotion_processing_result_or_hypothetical_stage_quarantined"
    )
    assert issue.actual["reason"] == "result_explanation_not_process_event"
    assert issue.actual["removed"] == fact.model_dump()


def test_zero_duration_post_heat_treatment_row_is_quarantined():
    evidence = "| 5-2 | 0 | 100.0 | 1214 ± 21.5 | 8.64 ± 1.4 |"
    parameter = {
        "parameter_name_raw": "Heating Time",
        "value_raw": "0",
        "unit_raw": "h",
        "source_evidence": evidence,
    }
    fact = _processing(
        sample="5-2",
        process="Post-HT",
        evidence=evidence,
        parameters=[parameter],
    )

    result = promote_axis_facts([_anchor("5-2")], [fact], source_text=evidence)

    assert result.accepted == ()
    issue = next(
        issue
        for issue in result.issues
        if issue.code == "promotion_processing_zero_duration_stage_quarantined"
    )
    assert issue.actual == {
        "removed": fact.model_dump(),
        "reason": "zero_duration_encodes_treatment_not_applied",
    }
    assert issue.evidence == [evidence]


def test_nonzero_or_direct_zero_hold_heat_treatment_is_preserved():
    nonzero_evidence = "| 5-1 | 2 | 41.66 | 1207 ± 10.2 | 12.9 ± 1.2 |"
    nonzero = _processing(
        sample="5-1",
        process="Post-HT",
        evidence=nonzero_evidence,
        parameters=[
            {
                "parameter_name_raw": "Heating Time",
                "value_raw": "2",
                "unit_raw": "h",
                "source_evidence": nonzero_evidence,
            }
        ],
    )
    direct_evidence = "A1 was heat-treated at 900 °C with a zero-hour hold."
    direct = _processing(
        sample="A1",
        process="heat treatment",
        evidence=direct_evidence,
        parameters=[
            {
                "parameter_name_raw": "hold time",
                "value_raw": "0",
                "unit_raw": "h",
                "source_evidence": direct_evidence,
            }
        ],
    )

    result = promote_axis_facts(
        [_anchor("5-1"), _anchor("A1")],
        [nonzero, direct],
        source_text=f"{nonzero_evidence}\n{direct_evidence}",
    )

    assert result.accepted == (nonzero, direct)
    assert not any(
        issue.code == "promotion_processing_zero_duration_stage_quarantined"
        for issue in result.issues
    )


def test_specimen_preparation_processing_stage_is_quarantined():
    evidence = (
        "All samples were prepared by sectioning the walls transverse to the "
        "scan direction to fit a 32 mm mount using wire-cut EDM."
    )
    fact = _processing(
        sample="Ti wall structures",
        process="wire-cut EDM",
        evidence=evidence,
    )

    result = promote_axis_facts(
        [_anchor("Ti wall structures")], [fact], source_text=evidence
    )

    assert result.accepted == ()
    issue = next(
        issue
        for issue in result.issues
        if issue.code == "promotion_processing_specimen_preparation_quarantined"
    )
    assert issue.actual["reason"] == "specimen_preparation_protocol_not_material_process"
    assert issue.actual["removed"] == fact.model_dump()


def test_adjectival_heat_treated_state_is_not_a_processing_event():
    evidence = (
        "APT reconstructions showing alloying element maps in heat-treated "
        "alloys T0 and T5."
    )
    fact = _processing(
        sample="T0",
        process="heat treatment",
        evidence=evidence,
    )

    result = promote_axis_facts(
        [_anchor("T0"), _anchor("T5")], [fact], source_text=evidence
    )

    assert result.accepted == ()
    assert any(
        issue.code == "promotion_processing_stage_unasserted_quarantined"
        for issue in result.issues
    )


def test_specimen_polishing_preparation_stage_is_quarantined():
    evidence = (
        "The samples were mounted in phenolic powder and polished for "
        "metallographic analysis according to a three-step procedure."
    )
    fact = _processing(
        sample="Ti wall structures",
        process="metallographic preparation",
        evidence=evidence,
    )

    result = promote_axis_facts(
        [_anchor("Ti wall structures")], [fact], source_text=evidence
    )

    assert result.accepted == ()
    assert any(
        issue.code == "promotion_processing_specimen_preparation_quarantined"
        for issue in result.issues
    )


def test_material_processing_event_survives_specimen_preparation_gate():
    evidence = (
        "The polished cylinders were laser-glazed on the top surface before "
        "microstructural examination."
    )
    fact = _processing(
        sample="A1",
        process="laser glazing",
        evidence=evidence,
    )

    result = promote_axis_facts([_anchor("A1")], [fact], source_text=evidence)

    assert result.accepted == (fact,)
    assert not any(
        issue.code == "promotion_processing_specimen_preparation_quarantined"
        for issue in result.issues
    )


def test_specimen_preparation_table_stage_remains_coordinate_eligible():
    evidence = "| Preparation | Sectioned and polished specimens |"
    fact = _processing(
        sample="A1",
        process="specimen preparation",
        evidence=evidence,
    )

    result = promote_axis_facts([_anchor("A1")], [fact], source_text=evidence)

    assert result.accepted == (fact,)
    assert not any(
        issue.code == "promotion_processing_specimen_preparation_quarantined"
        for issue in result.issues
    )


def test_mechanical_test_protocol_stage_is_quarantined():
    evidence = "S-S curves of R5, R2 and R1 tensile-deformed at 1023 K."
    facts = [
        _processing(sample=sample, process="tensile test", evidence=evidence)
        for sample in ("R1", "R2", "R5")
    ]

    result = promote_axis_facts(
        [_anchor("R1"), _anchor("R2"), _anchor("R5")],
        facts,
        source_text=evidence,
    )

    assert result.accepted == ()
    assert sum(
        issue.code == "promotion_processing_test_protocol_quarantined"
        for issue in result.issues
    ) == 3


def test_mechanical_test_protocol_gate_preserves_material_fabrication_sentence():
    evidence = (
        "The tensile samples were directly printed using the optimized laser "
        "power of 200 W and scanning speed of 900 mm/s."
    )
    fact = _processing(
        sample="A1",
        process="laser powder bed fusion",
        evidence=evidence,
    )

    result = promote_axis_facts([_anchor("A1")], [fact], source_text=evidence)

    assert result.accepted == (fact,)
    assert not any(
        issue.code == "promotion_processing_test_protocol_quarantined"
        for issue in result.issues
    )


def test_processing_hypothetical_treatment_is_not_promoted_as_stage():
    evidence = (
        "The fatigue life could approach the wrought condition if a hot "
        "isostatic pressing (HIP) step is added."
    )
    fact = _processing(sample="A1", process="hot isostatic pressing", evidence=evidence)

    result = promote_axis_facts([_anchor("A1")], [fact], source_text=evidence)

    assert result.accepted == ()
    issue = next(
        issue
        for issue in result.issues
        if issue.code
        == "promotion_processing_result_or_hypothetical_stage_quarantined"
    )
    assert issue.actual["reason"] == "hypothetical_process_step"


def test_processing_metadata_parameter_isolated_but_event_and_numeric_survive():
    evidence = (
        "EBAM specimens were built on a Sciaky EBAM 110 machine, with a "
        "layer thickness of 500 um."
    )
    fact = _processing(
        sample="EBAM",
        process="electron beam additive manufacturing",
        evidence=evidence,
        parameters=[
            {
                "parameter_name_raw": "equipment",
                "value_raw": "Sciaky EBAM 110 machine",
                "unit_raw": "",
                "source_evidence": [evidence],
            },
            {
                "parameter_name_raw": "layer thickness",
                "value_raw": "500",
                "unit_raw": "um",
                "source_evidence": [evidence],
            },
        ],
    )

    result = promote_axis_facts([_anchor("EBAM")], [fact], source_text=evidence)

    assert len(result.accepted) == 1
    assert [
        row["parameter_name_raw"]
        for row in result.accepted[0].data["parameters_raw"]
    ] == ["layer thickness"]
    issue = next(
        issue
        for issue in result.issues
        if issue.code == "promotion_processing_metadata_parameter_quarantined"
    )
    assert issue.actual["removed"]["parameter_name_raw"] == "equipment"
    assert issue.actual["before"] == fact.model_dump()


def test_processing_qualified_environment_metadata_isolated_but_table_remains_eligible():
    prose = (
        "EBAM specimens were built; the EBAM printing environment was a vacuum "
        "build chamber."
    )
    fact = _processing(
        sample="EBAM",
        process="electron beam additive manufacturing",
        evidence=prose,
        parameters=[
            {
                "parameter_name_raw": "printing environment",
                "value_raw": "vacuum build chamber",
                "unit_raw": "",
                "source_evidence": [prose],
            }
        ],
    )

    result = promote_axis_facts([_anchor("EBAM")], [fact], source_text=prose)

    assert len(result.accepted) == 1
    assert result.accepted[0].data["parameters_raw"] == []
    issue = next(
        issue
        for issue in result.issues
        if issue.code == "promotion_processing_metadata_parameter_quarantined"
    )
    assert issue.actual["removed"]["parameter_name_raw"] == "printing environment"


def test_processing_table_metadata_parameter_remains_coordinate_eligible():
    evidence = "| Equipment | Sciaky EBAM 110 machine |"
    fact = _processing(
        sample="EBAM",
        process="electron beam additive manufacturing",
        evidence=evidence,
        parameters=[
            {
                "parameter_name_raw": "equipment",
                "value_raw": "Sciaky EBAM 110 machine",
                "unit_raw": "",
                "source_evidence": [evidence],
            }
        ],
    )

    result = promote_axis_facts([_anchor("EBAM")], [fact], source_text=evidence)

    assert result.accepted == (fact,)
    assert not any(
        issue.code == "promotion_processing_metadata_parameter_quarantined"
        for issue in result.issues
    )


def test_processing_narrative_parameter_isolated_from_formal_ledger():
    evidence = (
        "HT2 aimed to realize a bi-modular size distribution in the alloy."
    )
    fact = _processing(
        sample="HT2",
        process="heat treatment",
        evidence=evidence,
        parameters=[
            {
                "parameter_name_raw": "raw_unmapped_parameter",
                "value_raw": "realize a bi-modular size distribution",
                "unit_raw": "",
                "source_evidence": [evidence],
            }
        ],
    )

    result = promote_axis_facts([_anchor("HT2")], [fact], source_text=evidence)

    assert result.accepted == ()
    issue = next(
        issue
        for issue in result.issues
        if issue.code == "promotion_processing_narrative_parameter_quarantined"
    )
    assert issue.actual["removed"]["value_raw"] == (
        "realize a bi-modular size distribution"
    )
    assert issue.actual["reason"] == "prose_narrative_parameter_without_coordinate"


def test_processing_unitless_categorical_parameter_is_not_narrative_projection():
    evidence = "The specimens were cooled in air after sintering."
    fact = _processing(
        sample="A1",
        process="sintering",
        evidence=evidence,
        parameters=[
            {
                "parameter_name_raw": "cooling approach",
                "value_raw": "air cooling",
                "unit_raw": "",
                "source_evidence": [evidence],
            }
        ],
    )

    result = promote_axis_facts([_anchor("A1")], [fact], source_text=evidence)

    assert len(result.accepted) == 1
    assert result.accepted[0].data["parameters_raw"]
    assert not any(
        issue.code == "promotion_processing_narrative_parameter_quarantined"
        for issue in result.issues
    )


def test_structure_generalization_entity_is_quarantined_without_local_payload():
    evidence = "Typically, columnar grains are observed in EBAM deposits."
    fact = _structure(
        sample="A1",
        evidence=evidence,
        entities=[
            {
                "name_raw": "columnar grains",
                "entity_type": "grain",
                "role": "reported",
                "features": [],
                "raw_expression": "columnar grains",
            }
        ],
    )

    result = promote_axis_facts([_anchor("A1")], [fact], source_text=evidence)

    assert result.accepted == ()
    issue = next(
        issue
        for issue in result.issues
        if issue.code == "promotion_structure_generalization_projection_quarantined"
    )
    assert issue.actual["removed"] == fact.data["entities"][0]
    assert issue.actual["reason"] == "generic_generalization_without_local_payload"


def test_structure_direct_entity_survives_generalization_gate():
    evidence = "A1 contained columnar grains in the build direction."
    fact = _structure(
        sample="A1",
        evidence=evidence,
        entities=[
            {
                "name_raw": "columnar grains",
                "entity_type": "grain",
                "role": "reported",
                "features": [],
                "raw_expression": "columnar grains",
            }
        ],
    )

    result = promote_axis_facts([_anchor("A1")], [fact], source_text=evidence)

    assert result.accepted == (fact,)
    assert not any(
        issue.code == "promotion_structure_generalization_projection_quarantined"
        for issue in result.issues
    )


def test_structure_generalization_with_numeric_local_payload_survives():
    evidence = "Typically, grains with an average size of 20 um were observed."
    fact = _structure(
        sample="A1",
        evidence=evidence,
        entities=[
            {
                "name_raw": "grains",
                "entity_type": "grain",
                "role": "reported",
                "features": [],
                "raw_expression": "grains",
            }
        ],
    )

    result = promote_axis_facts([_anchor("A1")], [fact], source_text=evidence)

    assert result.accepted == (fact,)


def test_structure_figure_locator_projection_is_quarantined():
    evidence = (
        "The yellow dashed line was used to distinguish the continuous and "
        "discontinuous regions."
    )
    fact = _structure(
        sample="A1",
        evidence=evidence,
        entities=[],
        features=[
            {
                "feature_name_raw": "region delineation",
                "value_kind": "categorical",
                "value_raw": "yellow dashed line used to distinguish regions",
                "data_nature": "reported",
            }
        ],
    )

    result = promote_axis_facts([_anchor("A1")], [fact], source_text=evidence)

    assert result.accepted == ()
    issue = next(
        issue
        for issue in result.issues
        if issue.code == "promotion_structure_procedural_projection_quarantined"
    )
    assert issue.actual["reason"] == "procedural_or_figure_locator_only"


def test_direct_structure_observation_survives_figure_presentation_gate():
    evidence = (
        "The lamellar L12 nanorods were clearly observed in the DP region "
        "in the dark-field TEM image."
    )
    fact = _structure(
        sample="A1",
        evidence=evidence,
        entities=[
            {
                "name_raw": "lamellar L12 nanorods",
                "entity_type": "precipitate",
                "role": "reported",
                "features": [],
                "raw_expression": "lamellar L12 nanorods",
            }
        ],
    )

    result = promote_axis_facts([_anchor("A1")], [fact], source_text=evidence)

    assert result.accepted == (fact,)
    assert not any(
        issue.code == "promotion_structure_procedural_projection_quarantined"
        for issue in result.issues
    )


def test_repeated_structure_table_metrics_without_feature_coordinates_are_isolated():
    source = (
        "| Parameter | T5 / 1030 C/0.5h | T5 / 1030 C/2h |\n"
        "| gamma-prime volume fraction (%) | 70.4 | 69.6 |\n"
        "| gamma-prime volume fraction (%) | 75.7 | 74.3 |"
    )
    evidence_rows = [
        "| Parameter | T5 / 1030 C/2h |",
        "| gamma-prime volume fraction (%) | 70.4 |",
        "| gamma-prime volume fraction (%) | 74.3 |",
    ]
    evidence = "\n".join(evidence_rows)
    base_fact = _structure(
        sample="T5 [1030 C/2h]",
        evidence=evidence,
        entities=[],
        features=[
            {
                "feature_name_raw": "gamma-prime volume fraction",
                "value_kind": "scalar",
                "value_raw": "70.4",
                "unit_raw": "%",
                "data_nature": "reported",
            },
            {
                "feature_name_raw": "gamma-prime volume fraction",
                "value_kind": "scalar",
                "value_raw": "74.3",
                "unit_raw": "%",
                "data_nature": "reported",
            },
        ],
    )
    base_fact = base_fact.model_copy(
        deep=True,
        update={
            "source_evidence": evidence_rows,
            "data": {
                **base_fact.data,
                "material_state": "1030 C/2h",
                "source_evidence": evidence_rows,
            },
        },
    )

    result = promote_axis_facts(
        [_anchor("T5 [1030 C/2h]")], [base_fact], source_text=source
    )

    assert len(result.accepted) == 1
    assert [
        row["value_raw"] for row in result.accepted[0].data["features"]
    ] == ["74.3"]
    issue = next(
        issue
        for issue in result.issues
        if issue.code == "promotion_structure_table_feature_projection_filtered"
    )
    assert issue.actual["reason"] == "sibling_column_value_projection"


def test_repeated_structure_html_table_metrics_are_also_isolated():
    source = (
        "<table><tr><th>Parameter</th><th>T5 / 1030 C/0.5h</th>"
        "<th>T5 / 1030 C/2h</th></tr>"
        "<tr><td>gamma-prime volume fraction (%)</td><td>70.4</td><td>69.6</td></tr>"
        "<tr><td>gamma-prime volume fraction (%)</td><td>75.7</td><td>74.3</td></tr>"
        "</table>"
    )
    rows = [
        "| Parameter | T5 / 1030 C/2h |",
        "| gamma-prime volume fraction (%) | 70.4 |",
        "| gamma-prime volume fraction (%) | 74.3 |",
    ]
    base_fact = _structure(
        sample="T5 [1030 C/2h]",
        evidence=rows[0],
        entities=[],
        features=[
            {
                "feature_name_raw": "gamma-prime volume fraction",
                "value_kind": "scalar",
                "value_raw": "70.4",
                "unit_raw": "%",
                "data_nature": "reported",
            },
            {
                "feature_name_raw": "gamma-prime volume fraction",
                "value_kind": "scalar",
                "value_raw": "74.3",
                "unit_raw": "%",
                "data_nature": "reported",
            },
        ],
    )
    base_fact = base_fact.model_copy(
        deep=True,
        update={"data": {**base_fact.data, "material_state": "1030 C/2h"}},
    )
    fact = base_fact.model_copy(
        deep=True,
        update={
            "source_evidence": rows,
            "data": {**base_fact.data, "source_evidence": rows},
        },
    )

    result = promote_axis_facts(
        [_anchor("T5 [1030 C/2h]")], [fact], source_text=source
    )

    assert len(result.accepted) == 1
    assert [
        row["value_raw"] for row in result.accepted[0].data["features"]
    ] == ["74.3"]
    assert any(
        issue.code == "promotion_structure_table_feature_projection_filtered"
        for issue in result.issues
    )


def test_prose_multi_owner_processing_requires_local_owner_payload_binding():
    source = "A1 and B1 were investigated. The laser power was 300 W."
    parameter = {
        "parameter_name_raw": "laser power",
        "value_raw": "300",
        "unit_raw": "W",
        "condition_label_raw": "",
        "source_evidence": [source],
    }
    fact = _processing(sample="A1", evidence=source, parameters=[parameter])

    result = promote_axis_facts(
        [_anchor("A1"), _anchor("B1")], [fact], source_text=source
    )

    assert result.accepted == ()
    issue = next(
        issue
        for issue in result.issues
        if issue.code == "promotion_prose_multi_owner_atomicity_quarantined"
    )
    assert issue.actual["reason"] == "multi_owner_without_local_payload_binding"
    assert issue.actual["removed"]["sample_id_raw"] == "A1"


def test_prose_multi_owner_processing_keeps_local_owner_payload_binding():
    source = "A1 used a laser power of 300 W. B1 used a laser power of 200 W."
    parameter = {
        "parameter_name_raw": "laser power",
        "value_raw": "300",
        "unit_raw": "W",
        "condition_label_raw": "",
        "source_evidence": [source],
    }
    fact = _processing(sample="A1", evidence=source, parameters=[parameter])

    result = promote_axis_facts(
        [_anchor("A1"), _anchor("B1")], [fact], source_text=source
    )

    assert len(result.accepted) == 1
    assert not any(
        issue.code == "promotion_prose_multi_owner_atomicity_quarantined"
        for issue in result.issues
    )


def test_prose_multi_owner_property_wrong_value_owner_isolated():
    source = "A1 had hardness of 900 HV. B1 had hardness of 700 HV."
    fact = _property(
        sample="A1",
        name="hardness",
        value="700",
        unit="HV",
        condition="",
        evidence=source,
    )

    result = promote_axis_facts(
        [_anchor("A1"), _anchor("B1")], [fact], source_text=source
    )

    assert result.accepted == ()
    assert any(
        issue.code == "promotion_prose_multi_owner_atomicity_quarantined"
        for issue in result.issues
    )


def test_prose_multi_owner_structure_wrong_value_owner_isolated():
    source = "A1 had a grain size of 10 um. B1 had a grain size of 20 um."
    fact = _structure(
        sample="A1",
        evidence=source,
        entities=[],
        features=[
            {
                "feature_name_raw": "grain size",
                "canonical_name": "grain_size",
                "value_kind": "scalar",
                "value_raw": "20",
                "unit_raw": "um",
                "data_nature": "reported",
                "source_evidence": [source],
            }
        ],
    )

    result = promote_axis_facts(
        [_anchor("A1"), _anchor("B1")], [fact], source_text=source
    )

    assert result.accepted == ()
    assert any(
        issue.code == "promotion_prose_multi_owner_atomicity_quarantined"
        for issue in result.issues
    )


def test_collective_structure_result_is_not_attached_to_one_owner():
    source = (
        "R1, R2 and R5 rods were examined. All samples exhibited a grain size "
        "of approximately 40 nm."
    )
    fact = _structure(
        sample="R1",
        evidence="All samples exhibited a grain size of approximately 40 nm.",
        entities=[],
        features=[
            {
                "feature_name_raw": "grain size",
                "value_kind": "scalar",
                "value_raw": "approximately 40",
                "unit_raw": "nm",
                "data_nature": "reported",
            }
        ],
    )

    result = promote_axis_facts(
        [
            _anchor("R1", material="44-4 alloy"),
            _anchor("R2", material="44-4 alloy"),
            _anchor("R5", material="44-4 alloy"),
        ],
        [fact],
        source_text=source,
    )

    assert result.accepted == ()
    assert any(
        issue.code == "promotion_collective_ownerless_projection_quarantined"
        for issue in result.issues
    )


def test_collective_structure_explicit_owner_pair_is_retained():
    source = "R1 and R2 were examined. R1 exhibited a grain size of 40 nm."
    fact = _structure(
        sample="R1",
        evidence="R1 exhibited a grain size of 40 nm.",
        entities=[],
        features=[
            {
                "feature_name_raw": "grain size",
                "value_kind": "scalar",
                "value_raw": "40",
                "unit_raw": "nm",
                "data_nature": "reported",
            }
        ],
    )

    result = promote_axis_facts(
        [_anchor("R1"), _anchor("R2")], [fact], source_text=source
    )

    assert result.accepted == (fact,)
    assert not any(
        issue.code == "promotion_collective_ownerless_projection_quarantined"
        for issue in result.issues
    )


def test_collective_noncore_property_result_is_not_attached_to_one_owner():
    source = (
        "The laser absorptivity of more than 70% was measured for composite "
        "powders at 8 and 12 vol.% B4C."
    )
    fact = _property(
        sample="Cu-12%-ANP",
        name="laser absorptivity",
        value=">70",
        unit="%",
        condition="",
        evidence=source,
    )

    result = promote_axis_facts(
        [
            _anchor("Cu-8%-ANP", material="Cu-8%-ANP"),
            _anchor("Cu-12%-ANP", material="Cu-12%-ANP"),
        ],
        [fact],
        source_text=source,
    )

    assert result.accepted == ()
    issue = next(
        issue
        for issue in result.issues
        if issue.code == "promotion_collective_ownerless_projection_quarantined"
    )
    assert issue.actual["candidate_owner"] == "Cu-12%-ANP"
    assert issue.actual["reason"] == "collective_assertion_without_local_owner_coordinate"


def test_collective_noncore_property_with_explicit_owner_is_preserved():
    source = "Cu-12%-ANP powder showed laser absorptivity above 70%."
    fact = _property(
        sample="Cu-12%-ANP",
        name="laser absorptivity",
        value=">70",
        unit="%",
        condition="",
        evidence=source,
    )

    result = promote_axis_facts(
        [
            _anchor("Cu-8%-ANP", material="Cu-8%-ANP"),
            _anchor("Cu-12%-ANP", material="Cu-12%-ANP"),
        ],
        [fact],
        source_text=source,
    )

    assert result.accepted == (fact,)
    assert not any(
        issue.code == "promotion_collective_ownerless_projection_quarantined"
        for issue in result.issues
    )


def test_collective_noncore_property_does_not_borrow_paragraph_owner():
    source = (
        "We measured the laser absorptivity of our initial Cu-B₄C powder "
        "mixtures with different microparticle fractions, revealing a "
        "surprisingly high laser absorptivity of more than 70% for composite "
        "powders (8 and 12 vol.%) at a wavelength of 1064 nm."
    )
    fact = _property(
        sample="Cu-B₄C",
        name="laser absorptivity",
        value=">70",
        unit="%",
        condition="wavelength of 1064 nm",
        evidence=source,
    )

    result = promote_axis_facts(
        [
            _anchor("Cu-B₄C"),
            _anchor("Cu-8%-ANP"),
            _anchor("Cu-12%-ANP"),
        ],
        [fact],
        source_text=source,
    )

    assert result.accepted == ()
    assert any(
        issue.code == "promotion_collective_ownerless_projection_quarantined"
        for issue in result.issues
    )


def test_region_scoped_property_without_owner_isolated():
    evidence = "certain regions have flow stresses exceeding 900 MPa"
    fact = _property(
        sample="Alloy-A",
        name="flow stress",
        value=">900",
        unit="MPa",
        condition="certain regions",
        evidence=evidence,
    )

    result = promote_axis_facts(
        [_anchor("Alloy-A"), _anchor("Alloy-B")], [fact], source_text=evidence
    )

    assert result.accepted == ()
    issue = next(
        row
        for row in result.issues
        if row.code == "promotion_region_scoped_owner_ambiguous_quarantined"
    )
    assert issue.actual["coordinate"] == "certain regions"
    assert issue.actual["removed"]["data"]["value_raw"] == ">900"


def test_region_scoped_property_with_explicit_owner_is_preserved():
    evidence = "Alloy-A fine rosette region has a flow stress exceeding 900 MPa"
    fact = _property(
        sample="Alloy-A",
        name="flow stress",
        value=">900",
        unit="MPa",
        condition="fine rosette region",
        evidence=evidence,
    )

    result = promote_axis_facts(
        [_anchor("Alloy-A"), _anchor("Alloy-B")], [fact], source_text=evidence
    )

    assert len(result.accepted) == 1
    assert not any(
        issue.code == "promotion_region_scoped_owner_ambiguous_quarantined"
        for issue in result.issues
    )


def test_melt_pool_boundary_property_without_owner_isolated():
    evidence = "Hard melt pool boundaries were associated with Young's modulus of 145 GPa."
    fact = _property(
        sample="Alloy-A",
        name="Young's modulus",
        value="145",
        unit="GPa",
        condition="melt pool boundaries",
        evidence=evidence,
    )

    result = promote_axis_facts(
        [_anchor("Alloy-A"), _anchor("Alloy-B")], [fact], source_text=evidence
    )

    assert result.accepted == ()
    assert any(
        issue.code == "promotion_region_scoped_owner_ambiguous_quarantined"
        for issue in result.issues
    )


def test_melt_pool_interior_property_with_explicit_owner_is_preserved():
    evidence = "Alloy-A melt pool interiors showed a Young's modulus of 148 GPa."
    fact = _property(
        sample="Alloy-A",
        name="Young's modulus",
        value="148",
        unit="GPa",
        condition="melt pool interiors",
        evidence=evidence,
    )

    result = promote_axis_facts(
        [_anchor("Alloy-A"), _anchor("Alloy-B")], [fact], source_text=evidence
    )

    assert len(result.accepted) == 1
    assert not any(
        issue.code == "promotion_region_scoped_owner_ambiguous_quarantined"
        for issue in result.issues
    )


def test_tensile_test_temperature_projected_as_property_is_quarantined():
    evidence = (
        "Quasi-static uniaxial tensile tests at room temperature and 600 °C "
        "were conducted at an initial strain rate of 1.0 × 10^-3 s^-1."
    )
    fact = _property(
        sample="A1",
        name="quasi-static uniaxial tensile test",
        value="600",
        unit="°C",
        condition="",
        evidence=evidence,
    )

    result = promote_axis_facts([_anchor("A1")], [fact], source_text=evidence)

    assert result.accepted == ()
    assert any(
        issue.code == "property_non_result_quarantined"
        for issue in result.issues
    )


def test_tensile_test_rate_projected_as_property_is_quarantined():
    evidence = "Rate controlled tensile tests at 5 mm/min were performed."
    fact = _property(
        sample="A1",
        name="tensile test rate",
        value="5",
        unit="mm/min",
        condition="",
        evidence=evidence,
    )

    result = promote_axis_facts([_anchor("A1")], [fact], source_text=evidence)

    assert result.accepted == ()
    assert any(
        issue.code == "property_non_result_quarantined"
        for issue in result.issues
    )


def test_build_orientation_projected_as_structure_is_quarantined():
    evidence = "EPBF samples fabricated in the Z orientation showed dimples."
    fact = _structure(
        sample="EPBF",
        evidence=evidence,
        entities=[],
        features=[
            {
                "feature_name_raw": "build_orientation",
                "value_kind": "categorical",
                "value_raw": "Z orientation",
                "data_nature": "reported",
            }
        ],
    )

    result = promote_axis_facts([_anchor("EPBF")], [fact], source_text=evidence)

    assert result.accepted == ()
    issue = next(
        issue
        for issue in result.issues
        if issue.code == "promotion_structure_process_coordinate_quarantined"
    )
    assert issue.actual["reason"] == "build_or_printing_orientation_is_not_structure"


def test_regression_coefficient_is_not_projected_as_grain_diameter():
    evidence = "The coefficient x for HA1065 and HA1100 is 0.30 and 0.32, respectively."
    fact = _structure(
        sample="HA1065",
        evidence=evidence,
        entities=[],
        features=[
            {
                "feature_name_raw": "area-weighted grain diameter",
                "value_kind": "scalar",
                "value_raw": "x = 0.30",
                "data_nature": "reported",
            }
        ],
    )

    result = promote_axis_facts([_anchor("HA1065")], [fact], source_text=evidence)

    assert result.accepted == ()
    issue = next(
        issue
        for issue in result.issues
        if issue.code == "promotion_structure_derived_feature_quarantined"
    )
    assert issue.actual["reason"] == "regression_coefficient_projected_as_physical_size"


def test_explicitly_derived_numeric_structure_fraction_is_preserved():
    evidence = (
        "The volume fraction of L12 particles within the aged alloy can be "
        "calculated to be ~37%."
    )
    fact = _structure(
        sample="aged alloy",
        evidence=evidence,
        entities=[],
        features=[
            {
                "feature_name_raw": "L12 volume fraction",
                "value_kind": "scalar",
                "value_raw": "~37%",
                "unit_raw": "%",
                "data_nature": "reported",
            }
        ],
    )

    result = promote_axis_facts([_anchor("aged alloy")], [fact], source_text=evidence)

    assert len(result.accepted) == 1
    assert result.accepted[0].data["features"][0]["value_raw"] == "~37%"
    assert not any(
        row.code == "promotion_structure_derived_feature_quarantined"
        for row in result.issues
    )


def test_formula_text_structure_feature_is_isolated():
    evidence = (
        "The lattice mismatch was calculated according to the equation "
        "δ = 2(a_L12 - a_FCC)/(a_L12 + a_FCC)."
    )
    fact = _structure(
        sample="A1",
        evidence=evidence,
        entities=[],
        features=[
            {
                "feature_name_raw": "lattice mismatch",
                "value_kind": "text",
                "value_raw": "δ = 2(a_L12 - a_FCC)/(a_L12 + a_FCC)",
                "data_nature": "reported",
            }
        ],
    )

    result = promote_axis_facts([_anchor("A1")], [fact], source_text=evidence)

    assert result.accepted == ()
    assert any(
        row.code == "promotion_structure_derived_feature_quarantined"
        and row.actual["reason"]
        == "formula_expression_not_observed_structure_value"
        for row in result.issues
    )


def test_causal_structure_explanation_is_isolated():
    evidence = (
        "The partial annihilation of dislocations was caused by the aging "
        "heat treatment."
    )
    fact = _structure(
        sample="aged alloy",
        evidence=evidence,
        entities=[],
        features=[
            {
                "feature_name_raw": "partial annihilation of dislocations",
                "value_kind": "text",
                "value_raw": "partial annihilation of dislocations caused by aging",
                "data_nature": "reported",
            }
        ],
    )

    result = promote_axis_facts([_anchor("aged alloy")], [fact], source_text=evidence)

    assert result.accepted == ()
    assert any(
        row.code == "promotion_structure_inferential_projection_quarantined"
        and row.actual["reason"] == "causal_explanation_projected_as_observation"
        for row in result.issues
    )


def test_elemental_depletion_structure_projection_is_isolated():
    evidence = "The L12 phase was severely Cr-depleted."
    fact = _structure(
        sample="aged alloy",
        evidence=evidence,
        entities=[],
        features=[
            {
                "feature_name_raw": "Cr content",
                "value_kind": "categorical",
                "value_raw": "severely Cr-depleted",
                "data_nature": "reported",
            }
        ],
    )

    result = promote_axis_facts([_anchor("aged alloy")], [fact], source_text=evidence)

    assert result.accepted == ()
    assert any(
        row.code == "promotion_structure_composition_projection_quarantined"
        for row in result.issues
    )


def test_same_value_structure_fanout_without_coordinate_is_isolated():
    evidence = "A1 and A2 had an average grain size of 10 μm."
    rows = [
        _structure(
            sample=sample,
            evidence=evidence,
            entities=[],
            features=[
                {
                    "feature_name_raw": "average grain size",
                    "value_kind": "scalar",
                    "value_raw": "10",
                    "unit_raw": "μm",
                    "data_nature": "reported",
                }
            ],
        )
        for sample in ("A1", "A2")
    ]

    result = promote_axis_facts(
        [_anchor("A1"), _anchor("A2")], rows, source_text=evidence
    )

    assert result.accepted == ()
    assert sum(
        row.code == "promotion_source_block_structure_same_value_fanout_quarantined"
        for row in result.issues
    ) == 2


def test_collective_same_value_structure_assertion_is_preserved():
    evidence = "Both A1 and A2 had an average grain size of 10 μm."
    rows = [
        _structure(
            sample=sample,
            evidence=evidence,
            entities=[],
            features=[
                {
                    "feature_name_raw": "average grain size",
                    "value_kind": "scalar",
                    "value_raw": "10",
                    "unit_raw": "μm",
                    "data_nature": "reported",
                }
            ],
        )
        for sample in ("A1", "A2")
    ]

    result = promote_axis_facts(
        [_anchor("A1"), _anchor("A2")], rows, source_text=evidence
    )

    assert len(result.accepted) == 2
    assert not any(
        row.code == "promotion_source_block_structure_same_value_fanout_quarantined"
        for row in result.issues
    )


def test_powder_particle_size_comparison_is_not_a_grain_measurement():
    evidence = (
        "Equiaxed grains with sizes comparable to the used D50 powder particle "
        "size, 15–20 μm, are obtained."
    )
    fact = _structure(
        sample="A1",
        evidence=evidence,
        entities=[],
        features=[
            {
                "feature_name_raw": "grain size",
                "value_kind": "range",
                "value_raw": "15–20",
                "unit_raw": "μm",
                "data_nature": "reported",
            }
        ],
    )

    result = promote_axis_facts([_anchor("A1")], [fact], source_text=evidence)

    assert result.accepted == ()
    issue = next(
        issue
        for issue in result.issues
        if issue.code
        == "promotion_structure_indirect_comparison_projection_quarantined"
    )
    assert issue.actual["reason"] == "powder_particle_size_projected_as_grain_measurement"


def test_global_precision_gate_keeps_direct_numeric_property():
    evidence = "A1 had a yield strength of 900 MPa at 650 °C."
    fact = _property(sample="A1", evidence=evidence)
    result = promote_axis_facts([_anchor("A1")], [fact], source_text=evidence)
    assert len(result.accepted) == 1
    assert not any(
        issue.code == "global_precision_source_local_payload_quarantined"
        for issue in result.issues
    )


def test_global_precision_gate_leaves_composition_untouched():
    fact = CompositionFact(
        sample_id_raw="A1",
        fact_type="material_identity",
        data={
            "material_family": "alloy",
            "material_name_raw": "A1",
            "designation_raw": "A1",
            "feedstock_form": None,
        },
        source_evidence=["A1"],
        confidence=0.8,
    )
    result = promote_axis_facts([_anchor("A1")], [fact], source_text="A1")
    assert len(result.accepted) == 1


def test_global_precision_gate_accepts_parameter_local_processing_evidence():
    parent_evidence = "A1 was fabricated by laser powder bed fusion."
    source_text = (
        parent_evidence
        + " The laser power was 300 W. The scan speed was 1100 mm/s."
    )
    fact = _processing(
        sample="A1",
        evidence=parent_evidence,
        parameters=[
            {
                "parameter_name_raw": "laser power",
                "value_raw": "300",
                "unit_raw": "W",
                "source_evidence": "The laser power was 300 W.",
            },
            {
                "parameter_name_raw": "scan speed",
                "value_raw": "1100",
                "unit_raw": "mm/s",
                "source_evidence": "The scan speed was 1100 mm/s.",
            },
        ],
    )

    result = promote_axis_facts([_anchor("A1")], [fact], source_text=source_text)

    assert len(result.accepted) == 1
    assert not any(
        issue.code == "global_precision_source_local_payload_quarantined"
        for issue in result.issues
    )


def test_global_precision_gate_stays_fail_closed_without_parameter_evidence():
    parent_evidence = "A1 was fabricated by laser powder bed fusion."
    fact = _processing(
        sample="A1",
        evidence=parent_evidence,
        parameters=[
            {
                "parameter_name_raw": "laser power",
                "value_raw": "300",
                "unit_raw": "W",
            }
        ],
    )

    result = promote_axis_facts([_anchor("A1")], [fact], source_text=parent_evidence)

    assert result.accepted == ()
    assert any(
        issue.code == "global_precision_source_local_payload_quarantined"
        for issue in result.issues
    )
