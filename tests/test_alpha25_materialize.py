import pytest

from knowmat.alpha25.contracts import (
    CompositionFact,
    InventoryAnchor,
    ProcessingFact,
    PropertyFact,
    StructureFact,
)
from knowmat.alpha25.materialize import (
    _claim_quality_mode,
    _source_microanalysis_state_map,
    is_plausible_material_identity,
    materialize_candidate,
)


def _anchor(sample: str, state: str | None = None) -> InventoryAnchor:
    return InventoryAnchor(
        sample_id_raw=sample,
        material_name_raw=None,
        state_raw=state,
        role="Target",
        data_nature="Experimental",
        source_evidence=[sample],
        confidence=0.9,
    )


def test_claim_quality_mode_defaults_to_safe_and_supports_three_levels(monkeypatch):
    monkeypatch.delenv("KNOWMAT2_ALPHA25_CLAIM_QUALITY", raising=False)
    assert _claim_quality_mode() == "safe"

    for value in ("1", "true", "safe", "unexpected-truthy-value"):
        monkeypatch.setenv("KNOWMAT2_ALPHA25_CLAIM_QUALITY", value)
        assert _claim_quality_mode() == "safe"

    for value in ("2", "strict", "experimental"):
        monkeypatch.setenv("KNOWMAT2_ALPHA25_CLAIM_QUALITY", value)
        assert _claim_quality_mode() == "strict"

    for value in ("0", "false", "off", "disabled"):
        monkeypatch.setenv("KNOWMAT2_ALPHA25_CLAIM_QUALITY", value)
        assert _claim_quality_mode() == "off"


def test_relative_quantity_reclassification_is_materialized_and_audited():
    evidence = (
        "| Melt Pool Length (mm) | 58.8% \\uparrow | 23.15 | "
        "0.4% \\downarrow | delay \\uparrow instability \\downarrow |"
    )
    fact = PropertyFact(
        sample_id_raw="A",
        data={
            "property_id_candidate": "temp",
            "property_name_raw": "Melt Pool Length",
            "value_raw": "0.4% \\downarrow",
            "unit_raw": "mm",
            "test_method_raw": None,
            "test_standard_raw": None,
            "test_condition_raw": None,
            "test_specimen_raw": None,
            "raw_note": None,
            "data_source": "table",
            "source_evidence": [evidence],
            "confidence": 0.9,
        },
        source_evidence=[evidence],
        confidence=0.9,
    )

    result = materialize_candidate([_anchor("A")], [fact])

    prop = result.document["items"][0]["Extracted_Data"]["Properties"][0]
    assert prop["property_name_raw"] == "Melt Pool Length relative change"
    assert prop["value_raw"] == "0.4% \\downarrow"
    assert prop["unit_raw"] == "%"
    issue = next(
        row
        for row in result.issues
        if row.code == "property_relative_quantity_reclassified"
    )
    assert issue.actual["before"]["unit_raw"] == "mm"
    assert issue.actual["after"]["unit_raw"] == "%"


def _tensile_property(
    sample: str = "A",
    *,
    condition: str | None = None,
    evidence: str = "A had an ultimate tensile strength of 900 MPa",
) -> PropertyFact:
    return PropertyFact(
        sample_id_raw=sample,
        data={
            "property_id_candidate": "temp",
            "property_name_raw": "ultimate tensile strength",
            "value_raw": "900",
            "unit_raw": "MPa",
            "test_method_raw": "tensile tests",
            "test_standard_raw": None,
            "test_condition_raw": condition,
            "test_specimen_raw": None,
            "raw_note": None,
            "data_source": "text",
            "source_evidence": [evidence],
            "confidence": 0.9,
        },
        source_evidence=[evidence],
        confidence=0.9,
    )


def test_unique_paper_level_tensile_context_is_recovered_verbatim(monkeypatch):
    monkeypatch.delenv("KNOWMAT2_ALPHA25_PROPERTY_CONTEXT_RECOVERY", raising=False)
    method = (
        "Dog-bone-shaped tensile test specimens with a gauge length of 5 mm "
        "were extracted from the as-built samples. The specimens were subjected "
        "to uniaxial tensile tests at a strain rate of 5 × 10^-3 s^-1 using an "
        "Instron 1361 testing machine. All tensile tests were repeated at least "
        "three times."
    )
    source = f"## Tensile test\n\n{method}\n"

    result = materialize_candidate(
        [_anchor("A")], [_tensile_property()], source_text=source
    )

    prop = result.document["items"][0]["Extracted_Data"]["Properties"][0]
    assert prop["test_condition_raw"] == method
    issue = next(
        row for row in result.issues if row.code == "property_test_context_recovered"
    )
    assert issue.actual["before"]["test_condition_raw"] is None
    assert issue.actual["after"]["test_condition_raw"] == method
    assert issue.evidence[0]["line_start"] == 3


def test_existing_property_condition_is_never_overwritten():
    source = (
        "## Tensile testing\n\n"
        "Tensile tests were performed at 650 °C at a strain rate of 1 × 10^-3 s^-1.\n"
    )

    result = materialize_candidate(
        [_anchor("A")],
        [_tensile_property(condition="room temperature")],
        source_text=source,
    )

    prop = result.document["items"][0]["Extracted_Data"]["Properties"][0]
    assert prop["test_condition_raw"] == "room temperature"
    assert not any(
        issue.code == "property_test_context_recovered" for issue in result.issues
    )


def test_incompatible_paper_level_tensile_contexts_remain_ambiguous():
    source = "\n\n".join(
        [
            "## Tensile testing",
            "Tensile tests were performed at room temperature at a strain rate of 1 × 10^-3 s^-1.",
            "Tensile tests were performed at 650 °C at a strain rate of 2 × 10^-3 s^-1.",
        ]
    )

    result = materialize_candidate(
        [_anchor("A")], [_tensile_property()], source_text=source
    )

    prop = result.document["items"][0]["Extracted_Data"]["Properties"][0]
    assert prop["test_condition_raw"] in (None, "")
    issue = next(
        row for row in result.issues if row.code == "ambiguous_property_test_context"
    )
    assert len(issue.evidence) == 2


def test_property_local_temperature_disambiguates_tensile_context():
    source = "\n\n".join(
        [
            "## Tensile testing",
            "Tensile tests were performed at room temperature at a strain rate of 1 × 10^-3 s^-1.",
            "Tensile tests were performed at 650 °C at a strain rate of 2 × 10^-3 s^-1.",
        ]
    )
    fact = _tensile_property(
        evidence="At 650 °C, A had an ultimate tensile strength of 900 MPa"
    )

    result = materialize_candidate([_anchor("A")], [fact], source_text=source)

    prop = result.document["items"][0]["Extracted_Data"]["Properties"][0]
    assert prop["test_condition_raw"].startswith("Tensile tests were performed at 650 °C")


def test_material_state_temperature_is_not_promoted_to_test_temperature():
    source = (
        "## Mechanical testing\n\n"
        "Rate controlled tensile tests at 5 mm/min were performed on samples "
        "sintered at 1280, 1290 and 1300 °C using an MTS 880.\n"
    )

    result = materialize_candidate(
        [_anchor("A")], [_tensile_property()], source_text=source
    )

    prop = result.document["items"][0]["Extracted_Data"]["Properties"][0]
    assert prop["test_condition_raw"] in (None, "")
    assert not any(
        issue.code == "property_test_context_recovered" for issue in result.issues
    )


def test_property_context_recovery_can_be_disabled(monkeypatch):
    monkeypatch.setenv("KNOWMAT2_ALPHA25_PROPERTY_CONTEXT_RECOVERY", "0")
    source = (
        "## Tensile testing\n\n"
        "Tensile tests were performed at room temperature at a strain rate of 1 × 10^-3 s^-1.\n"
    )

    result = materialize_candidate(
        [_anchor("A")], [_tensile_property()], source_text=source
    )

    prop = result.document["items"][0]["Extracted_Data"]["Properties"][0]
    assert prop["test_condition_raw"] in (None, "")


def test_core_tensile_abbreviation_receives_the_same_context_as_full_name():
    source = (
        "## Mechanical testing\n\n"
        "Rate controlled tensile tests at 5 mm/min were performed using an MTS 880.\n"
    )
    fact = _tensile_property()
    fact.data["property_name_raw"] = "UTS"

    result = materialize_candidate([_anchor("A")], [fact], source_text=source)

    prop = result.document["items"][0]["Extracted_Data"]["Properties"][0]
    assert prop["test_condition_raw"] == (
        "Rate controlled tensile tests at 5 mm/min were performed using an MTS 880."
    )


def test_fatigue_protocol_is_not_appended_to_tensile_condition():
    source = (
        "## Mechanical testing\n\n"
        "Tensile test samples were designed according to ASTM E8. "
        "The tensile tests were performed at a displacement rate of 1 mm/min. "
        "Strain controlled fatigue test samples were tested according to ASTM E606.\n"
    )

    result = materialize_candidate(
        [_anchor("A")], [_tensile_property()], source_text=source
    )

    condition = result.document["items"][0]["Extracted_Data"]["Properties"][0][
        "test_condition_raw"
    ]
    assert "ASTM E8" in condition
    assert "1 mm/min" in condition
    assert "fatigue" not in condition
    assert "E606" not in condition


def test_distinct_nearby_tensile_protocol_is_not_merged_by_proximity():
    source = "\n\n".join(
        [
            "## Mechanical testing",
            "Quasistatic tensile tests were performed at a strain rate of 1 × 10^-3 s^-1.",
            "In situ tensile tests were performed at a strain rate of 1 × 10^-3 s^-1 using synchrotron diffraction.",
        ]
    )

    result = materialize_candidate(
        [_anchor("A")], [_tensile_property()], source_text=source
    )

    condition = result.document["items"][0]["Extracted_Data"]["Properties"][0][
        "test_condition_raw"
    ]
    assert "Quasistatic tensile tests" in condition
    assert "synchrotron" not in condition


def test_unusual_tensile_properties_wording_remains_a_distinct_protocol():
    source = "\n\n".join(
        [
            "## Experimental procedure",
            "The RT tensile properties were conducted on a testing machine at a strain rate of 2.5 × 10^-4 s^-1.",
            "High-temperature tensile testing was performed at 650 °C at a strain rate of 1 × 10^-3 s^-1.",
        ]
    )

    result = materialize_candidate(
        [_anchor("A")], [_tensile_property()], source_text=source
    )

    prop = result.document["items"][0]["Extracted_Data"]["Properties"][0]
    assert prop["test_condition_raw"] in (None, "")
    assert any(
        issue.code == "ambiguous_property_test_context" for issue in result.issues
    )


def test_current_paper_table_value_without_citation_receives_context():
    source = (
        "## Tensile testing\n\n"
        "Tensile tests were performed according to the ASTM E8-15a standard "
        "at a strain rate of 0.005 min^-1.\n"
    )
    fact = _tensile_property(evidence="| Sample | UTS (MPa) |\n| A | 900 |")
    fact.data["data_source"] = "table"

    result = materialize_candidate([_anchor("A")], [fact], source_text=source)

    condition = result.document["items"][0]["Extracted_Data"]["Properties"][0][
        "test_condition_raw"
    ]
    assert "ASTM E8-15a" in condition


def test_unit_decorated_uts_abbreviation_receives_current_paper_context():
    source = (
        "## Tensile testing\n\n"
        "Tensile tests were performed at room temperature at a strain rate of 1 × 10^-3 s^-1.\n"
    )
    fact = _tensile_property(evidence="| Sample | UTS (MPa) |\n| A | 900 |")
    fact.data["property_name_raw"] = "UTS (MPa)"
    fact.data["data_source"] = "table"

    result = materialize_candidate([_anchor("A")], [fact], source_text=source)

    prop = result.document["items"][0]["Extracted_Data"]["Properties"][0]
    assert prop["property_name_raw"] == "UTS (MPa)"
    assert "room temperature" in prop["test_condition_raw"]


def test_reference_material_does_not_inherit_current_paper_tensile_context():
    source = (
        "## Tensile testing\n\n"
        "Tensile tests were performed at room temperature at a strain rate of 1 × 10^-3 s^-1.\n"
    )
    anchor = InventoryAnchor(
        sample_id_raw="literature alloy",
        material_name_raw="literature alloy",
        state_raw=None,
        role="Reference",
        data_nature="Literature_Experimental",
        source_evidence=["Literature alloy [12]"],
        confidence=0.9,
    )

    result = materialize_candidate(
        [anchor], [_tensile_property("literature alloy")], source_text=source
    )

    prop = result.document["items"][0]["Extracted_Data"]["Properties"][0]
    assert prop["test_condition_raw"] in (None, "")
    assert any(
        issue.code == "property_test_context_not_applied_to_reference"
        for issue in result.issues
    )


def test_external_reference_property_does_not_inherit_current_paper_context():
    source = (
        "## Tensile testing\n\n"
        "Tensile tests were performed at room temperature at a strain rate of 1 × 10^-3 s^-1.\n"
    )
    fact = _tensile_property()
    fact.data["data_source"] = "external_reference"

    result = materialize_candidate([_anchor("A")], [fact], source_text=source)

    prop = result.document["items"][0]["Extracted_Data"]["Properties"][0]
    assert prop["test_condition_raw"] in (None, "")
    assert any(
        issue.code == "property_test_context_not_applied_to_reference"
        for issue in result.issues
    )


def test_cited_comparison_table_value_does_not_inherit_current_paper_context():
    source = (
        "## Tensile testing\n\n"
        "Tensile tests were performed at room temperature at a strain rate of 1 × 10^-3 s^-1.\n"
    )
    evidence = (
        "| Properties | Current | WAAM | Wrought |\n"
        "| Yield Strength (MPa) | 900 | 856 [39] | 948 [37] |"
    )
    fact = _tensile_property("WAAM", evidence=evidence)
    fact.data["data_source"] = "table"
    fact.data["raw_note"] = "[39]"

    result = materialize_candidate([_anchor("WAAM")], [fact], source_text=source)

    prop = result.document["items"][0]["Extracted_Data"]["Properties"][0]
    assert prop["test_condition_raw"] in (None, "")
    issue = next(
        issue
        for issue in result.issues
        if issue.code == "property_test_context_not_applied_to_reference"
    )
    assert "bibliographic provenance" in issue.actual["reason"]


def test_citation_to_method_is_conservatively_left_unbound():
    source = (
        "## Tensile testing\n\n"
        "Tensile tests were performed at room temperature at a strain rate of 1 × 10^-3 s^-1.\n"
    )
    fact = _tensile_property(
        evidence="| Sample | Yield strength |\n| A | 900 MPa [12] |"
    )
    fact.data["data_source"] = "table"

    result = materialize_candidate([_anchor("A")], [fact], source_text=source)

    prop = result.document["items"][0]["Extracted_Data"]["Properties"][0]
    assert prop["test_condition_raw"] in (None, "")
    assert any(
        issue.code == "property_test_context_not_applied_to_reference"
        for issue in result.issues
    )


def _composition_fact(outer_sample: str, inner_sample: str, evidence: str):
    return CompositionFact(
        sample_id_raw=outer_sample,
        fact_type="composition_observation",
        data={
            "observation_id": "temporary",
            "source_type": "provided",
            "material_state": "not_reported",
            "sample_id": inner_sample,
            "basis": "wt%",
            "component_type": "elemental",
            "components": [
                {
                    "name_raw": "Zr",
                    "canonical_name": None,
                    "value_kind": "scalar",
                    "value_raw": "1",
                    "value": None,
                    "unit_raw": "wt%",
                    "canonical_unit": None,
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


def test_cited_nominal_composition_row_recovers_independent_reference_owner():
    label = "Nominal composition [18]"
    evidence = (
        "| Elements | Ni | Cr | Mo |\n"
        "| Nominal composition [18] | >58 | 20–23 | 8–10 |"
    )
    fact = _composition_fact(label, label, evidence)
    fact.data["source_type"] = "nominal"
    fact.data["data_source"] = "table"
    fact.data["components"] = [
        {
            "name_raw": name,
            "value_kind": kind,
            "value_raw": value,
            "unit_raw": "wt%",
            "data_nature": "reported",
        }
        for name, kind, value in (
            ("Ni", "inequality", ">58"),
            ("Cr", "range", "20–23"),
            ("Mo", "range", "8–10"),
        )
    ]

    # A real paper already has target samples in its global inventory.  That
    # authoritative inventory currently prevents this independently reported
    # literature row from creating a new owner.
    result = materialize_candidate([_anchor("GA")], [fact])

    assert len(result.document["items"]) == 1
    item = result.document["items"][0]
    assert item["Sample_ID"] == "Nominal composition [18] [reference]"
    assert item["Role"] == "Reference"
    assert item["Data_Nature"] == "Literature_Experimental"
    observations = item["Extracted_Data"]["Composition"][
        "Composition_Observations"
    ]
    assert [row["name_raw"] for row in observations[0]["components"]] == [
        "Ni",
        "Cr",
        "Mo",
    ]
    assert observations[0]["material_state"] == "nominal composition"
    issue = next(
        row
        for row in result.issues
        if row.code == "reference_composition_owner_recovered"
    )
    assert issue.actual["before_owner"] == label
    assert issue.actual["after_owner"] == item["Sample_ID"]
    assert issue.evidence == [evidence]


def test_uncited_nominal_composition_header_remains_unresolved():
    label = "Nominal composition"
    evidence = "| Nominal composition | >58 | 20–23 | 8–10 |"
    fact = _composition_fact(label, label, evidence)
    fact.data["source_type"] = "nominal"
    fact.data["data_source"] = "table"
    fact.data["components"] = [
        {
            "name_raw": name,
            "value_kind": "scalar",
            "value_raw": value,
            "unit_raw": "wt%",
            "data_nature": "reported",
        }
        for name, value in (("Ni", "58"), ("Cr", "20"), ("Mo", "8"))
    ]

    result = materialize_candidate([], [fact])

    assert result.document["items"] == []
    assert any(
        issue.code == "unresolved_sample_alias" for issue in result.issues
    )


def test_microanalysis_point_row_routes_to_unique_explicit_state_owner():
    evidence = "| Point | C | Cr |\n| Point 1 | 53.0 | 0.66 |"
    fact = _composition_fact("Point 1", "Point 1", evidence)
    fact.data.update(
        {
            "source_type": "measured",
            "data_source": "table",
            # The cached model state is deliberately wrong and absent from the
            # row evidence.  Source prose below is authoritative.
            "material_state": "sintered at 1290 °C",
            "measurement": "EDS point analysis",
            "components": [
                {
                    "name_raw": "C",
                    "value_kind": "scalar",
                    "value_raw": "53.0",
                    "unit_raw": "wt%",
                    "data_nature": "reported",
                },
                {
                    "name_raw": "Cr",
                    "value_kind": "scalar",
                    "value_raw": "0.66",
                    "unit_raw": "wt%",
                    "data_nature": "reported",
                },
            ],
        }
    )
    owner = InventoryAnchor(
        sample_id_raw="1280 °C sample",
        material_name_raw="alloy 625",
        state_raw="sintered at 1280 °C for 4 h",
        role="Target",
        data_nature="Experimental",
        source_evidence=["alloy 625 sample sintered at 1280 °C for 4 h"],
        confidence=0.95,
    )
    # These generic-alloy inventory rows create a competing generated state
    # owner.  The directly named source sample must win without collapsing the
    # distinct 1220 °C sibling or creating a duplicate 1280 °C item.
    generated_state_anchors = [
        InventoryAnchor(
            sample_id_raw="alloy 625",
            material_name_raw="alloy 625",
            state_raw=f"sintered at {temperature} °C",
            role="Target",
            data_nature="Experimental",
            source_evidence=[f"alloy 625 sintered at {temperature} °C"],
            confidence=0.9,
        )
        for temperature in (1220, 1280)
    ]

    source_text = (
        "The sample sintered at 1280 °C contained the feature at Point 1.\n"
        + evidence
    )
    result = materialize_candidate(
        [owner, *generated_state_anchors], [fact], source_text=source_text
    )

    assert [item["Sample_ID"] for item in result.document["items"]] == [
        "1280 °C sample"
    ]
    observation = result.document["items"][0]["Extracted_Data"]["Composition"][
        "Composition_Observations"
    ][0]
    assert observation["sample_id"] == "Point 1"
    assert observation["material_state"] == "sintered at 1280 °C for 4 h"
    assert "_microanalysis_owner_recovered" not in observation
    issue = next(
        row
        for row in result.issues
        if row.code == "microanalysis_location_owner_recovered"
    )
    assert issue.actual["before_owner"] == "Point 1"
    assert issue.actual["after_owner"] == "1280 °C sample"
    assert issue.actual["observation_location"] == "Point 1"
    assert issue.actual["state_corrections"][0]["before_state"] == (
        "sintered at 1290 °C"
    )
    assert issue.actual["state_corrections"][0]["after_state"] == (
        "sintered at 1280 °C for 4 h"
    )


def test_microanalysis_model_state_without_source_support_stays_unresolved():
    evidence = "| Point | C | Cr |\n| Point 1 | 53.0 | 0.66 |"
    fact = _composition_fact("Point 1", "Point 1", evidence)
    fact.data.update(
        {
            "source_type": "measured",
            "data_source": "table",
            "material_state": "sintered at 1280 °C",
            "components": [
                {
                    "name_raw": name,
                    "value_kind": "scalar",
                    "value_raw": value,
                    "unit_raw": "wt%",
                    "data_nature": "reported",
                }
                for name, value in (("C", "53.0"), ("Cr", "0.66"))
            ],
        }
    )
    owner = InventoryAnchor(
        sample_id_raw="1280 °C sample",
        material_name_raw="alloy 625",
        state_raw="sintered at 1280 °C",
        role="Target",
        data_nature="Experimental",
        source_evidence=["alloy 625 sample sintered at 1280 °C"],
        confidence=0.95,
    )

    result = materialize_candidate([owner], [fact], source_text=evidence)

    assert result.document["items"] == []
    assert any(row.code == "unresolved_sample_alias" for row in result.issues)
    assert not any(
        row.code == "microanalysis_location_owner_recovered"
        for row in result.issues
    )


def test_microanalysis_parallel_point_groups_follow_ordered_source_states():
    mapping = _source_microanalysis_state_map(
        "EDS analyses on samples sintered at 1290 and 1300 °C found bright "
        "spots at points 5 and 7. Points 6 and 8 were matrix."
    )

    assert {key: value[0] for key, value in mapping.items()} == {
        "point:5": "sintered at 1290 °C",
        "point:6": "sintered at 1290 °C",
        "point:7": "sintered at 1300 °C",
        "point:8": "sintered at 1300 °C",
    }


def test_microanalysis_point_row_stays_unresolved_without_unique_state_owner():
    evidence = "| Point | C | Cr |\n| Point 1 | 53.0 | 0.66 |"
    fact = _composition_fact("Point 1", "Point 1", evidence)
    fact.data.update(
        {
            "source_type": "measured",
            "data_source": "table",
            "material_state": "sintered at 1280 °C",
            "measurement": "EDS point analysis",
            "components": [
                {
                    "name_raw": "C",
                    "value_kind": "scalar",
                    "value_raw": "53.0",
                    "unit_raw": "wt%",
                    "data_nature": "reported",
                },
                {
                    "name_raw": "Cr",
                    "value_kind": "scalar",
                    "value_raw": "0.66",
                    "unit_raw": "wt%",
                    "data_nature": "reported",
                },
            ],
        }
    )
    anchors = [
        InventoryAnchor(
            sample_id_raw=sample,
            material_name_raw=material,
            state_raw="sintered at 1280 °C",
            role="Target",
            data_nature="Experimental",
            source_evidence=[f"{material} {sample} sintered at 1280 °C"],
            confidence=0.95,
        )
        for sample, material in (
            ("A1280", "alloy A"),
            ("B1280-4", "alloy B"),
        )
    ]

    result = materialize_candidate(
        anchors,
        [fact],
        source_text=(
            "The samples sintered at 1280 °C contained Point 1.\n" + evidence
        ),
    )

    assert result.document["items"] == []
    assert any(
        row.code == "unresolved_sample_alias" for row in result.issues
    )
    assert not any(
        row.code == "microanalysis_location_owner_recovered"
        for row in result.issues
    )


def test_non_material_headers_and_test_subsamples_cannot_anchor_items():
    rejected = [
        "Material property",
        "Phase",
        "Phases",
        "Location",
        "Experimental",
        "EDS powder analysis",
        "powder",
        "feedstocks",
        "Manufacturer analysis",
        "FIB-sample-A",
        "TEM lamella B",
        "Specimen III",
        "XRT specimen",
        "Point 1",
        "EDS Point 12",
        "DFT",
        "ASTM F3056-14",
        "beta phase",
        "needle-like nanoprecipitates",
        "coarse rosette region",
        "fine rosette region post-deformation",
        "failure specimens",
        "post-deformation micropillar",
        "white band",
        "horizontal",
        "vertical orientation",
        "not_reported [sintered at 1225 °C]",
        "-0.0499",
        "113.8",
        r"$ E_{corr} $ (mVSCE)",
        r"$ \\gamma' $",
    ]

    assert all(not is_plausible_material_identity(value) for value in rejected)
    assert is_plausible_material_identity("1-1")
    assert is_plausible_material_identity("#1")
    assert is_plausible_material_identity("120 s Delay")
    assert is_plausible_material_identity("WAAM Ti64 horizontal")


def test_cited_literature_composition_uses_current_paper_text_provenance():
    fact = _composition_fact(
        "reference alloy",
        "reference alloy",
        "the reference alloy contains 1 wt% Zr",
    )
    fact.data["data_source"] = "external_reference"

    result = materialize_candidate([_anchor("reference alloy")], [fact])

    observations = result.document["items"][0]["Extracted_Data"]["Composition"][
        "Composition_Observations"
    ]
    assert len(observations) == 1
    assert observations[0]["data_source"] == "text"
    assert observations[0]["source_evidence"] == [
        "the reference alloy contains 1 wt% Zr"
    ]


def test_mixed_mass_trace_and_atomic_composition_is_split_losslessly():
    evidence = "S0 contained 680 ppm O and 47.51 at.% Al"
    fact = _composition_fact("S0", "S0", evidence)
    fact.data["basis"] = "unknown"
    fact.data["components"] = [
        {
            "name_raw": "O",
            "value_kind": "scalar",
            "value_raw": "680",
            "unit_raw": "ppm",
            "data_nature": "reported",
        },
        {
            "name_raw": "Al",
            "value_kind": "scalar",
            "value_raw": "47.51",
            "unit_raw": "at.%",
            "data_nature": "reported",
        },
    ]

    result = materialize_candidate([_anchor("S0")], [fact])

    observations = result.document["items"][0]["Extracted_Data"]["Composition"][
        "Composition_Observations"
    ]
    assert [row["basis"] for row in observations] == ["mass_trace", "at%"]
    assert [row["components"][0]["name_raw"] for row in observations] == [
        "O",
        "Al",
    ]
    assert all(row["source_evidence"] == [evidence] for row in observations)


def _structure_fact(sample: str, evidence: str):
    return StructureFact(
        sample_id_raw=sample,
        fact_type="structure_observation",
        data={
            "observation_id": "temporary",
            "structure_kind": "phase",
            "material_state": "not_reported",
            "sample_id": sample,
            "source_type": "measured",
            "original": evidence,
            "simplified": evidence,
            "entities": [
                {
                    "entity_id": "temporary",
                    "entity_type": "phase",
                    "role": "reported",
                    "name_raw": "carbides",
                    "features": [],
                    "raw_expression": evidence,
                    "source_evidence": [evidence],
                }
            ],
            "features": [],
            "source_evidence": [evidence],
        },
        source_evidence=[evidence],
        confidence=0.8,
    )


def _identity_fact(outer_sample: str, designation: str, material_name: str):
    evidence = f"{material_name} ({designation})"
    return CompositionFact(
        sample_id_raw=outer_sample,
        fact_type="material_identity",
        data={
            "material_family": "alloy",
            "material_name_raw": material_name,
            "designation_raw": designation,
            "feedstock_form": None,
        },
        source_evidence=[evidence],
        confidence=0.8,
    )


def test_exact_aliases_and_state_variants_form_one_evidence_backed_item():
    anchors = [_anchor("Sample-A"), _anchor("sample A"), _anchor("Sample-A", "aged")]
    facts = [_composition_fact("SAMPLE A", "SAMPLE A", "Sample-A")]

    result = materialize_candidate(anchors, facts)

    assert len(result.document["items"]) == 1
    assert result.document["items"][0]["Sample_ID"] == "Sample-A"


def test_tex_and_unicode_greek_identity_presentations_merge():
    result = materialize_candidate(
        [_anchor(r"$ \gamma $-Ni reference"), _anchor("γ-Ni reference")],
        [
            _structure_fact(r"$ \gamma $-Ni reference", "gamma-Ni had fine grains"),
            _structure_fact("γ-Ni reference", "γ-Ni contained carbides"),
        ],
    )

    assert len(result.document["items"]) == 1
    assert len(
        result.document["items"][0]["Extracted_Data"]["Structure"][
            "Structure_Observations"
        ]
    ) == 2


def test_unreported_and_identity_restatement_do_not_create_state_items():
    anchors = [
        _anchor("Boron free"),
        _anchor("Boron free", "not_reported"),
        _anchor("Boron free", "Boron free"),
    ]
    facts = [
        _structure_fact("Boron free", "Boron free contained fine grains"),
    ]

    result = materialize_candidate(anchors, facts)

    assert [item["Sample_ID"] for item in result.document["items"]] == [
        "Boron free"
    ]


def test_shared_material_descriptor_merges_initialism_and_variant_suffixes():
    def variant_anchor(sample: str, state: str) -> InventoryAnchor:
        return InventoryAnchor(
            sample_id_raw=sample,
            material_name_raw="prototype nickel superalloy",
            state_raw=state,
            role="Target",
            data_nature="Experimental",
            source_evidence=[f"{sample} {state}"],
            confidence=0.9,
        )

    anchors = [
        variant_anchor("BF", "boron free – BF"),
        variant_anchor("Boron free", "Boron free"),
        variant_anchor("boron-free alloy", "fully heat treated"),
        variant_anchor("boron-free version", "boron-free"),
        variant_anchor("HB", "high boron – HB"),
        variant_anchor("high boron alloy", "fully heat treated"),
    ]
    facts = [
        _structure_fact("BF", "BF contained fine grains"),
        _structure_fact("Boron free", "Boron free contained carbides"),
        _structure_fact("boron-free alloy", "boron-free alloy was heat treated"),
        _structure_fact("HB", "HB contained coarse grains"),
        _structure_fact("high boron alloy", "high boron alloy contained borides"),
    ]

    result = materialize_candidate(anchors, facts)

    assert [item["Sample_ID"] for item in result.document["items"]] == ["BF", "HB"]
    assert [
        len(item["Extracted_Data"]["Structure"]["Structure_Observations"])
        for item in result.document["items"]
    ] == [3, 2]


def test_phase_rows_and_table_labels_cannot_create_material_items():
    anchors = [
        _anchor("S1"),
        InventoryAnchor(
            sample_id_raw="M5B3_row1",
            material_name_raw="M5B3",
            state_raw="boride precipitate",
            role="Target",
            data_nature="Experimental",
            source_evidence=["M5B3"],
            confidence=0.9,
        ),
        InventoryAnchor(
            sample_id_raw="Table 3",
            material_name_raw="M23C6",
            state_raw="carbide",
            role="Target",
            data_nature="Experimental",
            source_evidence=["Table 3 M23C6 carbide"],
            confidence=0.9,
        ),
    ]
    facts = [
        _structure_fact("S1", "S1 contained M5B3 and M23C6"),
        _structure_fact("M5B3_row1", "M5B3 was measured"),
        _structure_fact("Table 3", "Table 3 reports M23C6"),
    ]

    result = materialize_candidate(anchors, facts)

    assert [item["Sample_ID"] for item in result.document["items"]] == ["S1"]


def test_phase_formula_with_structural_material_suffix_cannot_anchor_item():
    anchors = [
        _anchor("S1"),
        # These simulate deterministic table anchors for the same row labels.
        # A provider anchor elsewhere proves the labels are structural entities,
        # so the deterministic copies must not recreate material items.
        _anchor("M23C6"),
        _anchor("M5B3_a"),
        InventoryAnchor(
            sample_id_raw="M23C6",
            material_name_raw="M23C6 carbide",
            state_raw="carbide phase",
            role="Target",
            data_nature="Experimental",
            source_evidence=["M23C6 carbide phase"],
            confidence=0.9,
        ),
        InventoryAnchor(
            sample_id_raw="M5B3_a",
            material_name_raw="M5B3_a boride phase",
            state_raw="boride precipitate",
            role="Target",
            data_nature="Experimental",
            source_evidence=["M5B3_a boride phase"],
            confidence=0.9,
        ),
    ]

    result = materialize_candidate(
        anchors,
        [
            _structure_fact("S1", "S1 contained M23C6 and M5B3 borides"),
            _structure_fact("M23C6", "M23C6 was a carbide phase"),
            _structure_fact("M5B3_a", "M5B3_a was a boride precipitate"),
        ],
    )

    assert [item["Sample_ID"] for item in result.document["items"]] == ["S1"]


def test_location_phase_and_matrix_rows_cannot_anchor_material_items():
    anchors = [
        _anchor("Alloy-A"),
        # Simulate a deterministic copy plus provider-classified table rows.
        _anchor("Alloy-A Interior FCC"),
        InventoryAnchor(
            sample_id_raw="Alloy-A Interior FCC",
            material_name_raw="Alloy-A Interior region FCC phase",
            state_raw="Interior",
            role="Target",
            data_nature="Experimental",
            source_evidence=["Interior | FCC"],
            confidence=0.9,
        ),
        InventoryAnchor(
            sample_id_raw="Alloy-A Wall BCC",
            material_name_raw="Alloy-A Wall BCC matrix",
            state_raw="Wall",
            role="Target",
            data_nature="Experimental",
            source_evidence=["Wall | BCC"],
            confidence=0.9,
        ),
    ]

    result = materialize_candidate(
        anchors,
        [
            _structure_fact("Alloy-A", "Alloy-A contained FCC and BCC regions"),
            _structure_fact("Alloy-A Interior FCC", "Interior | FCC"),
            _structure_fact("Alloy-A Wall BCC", "Wall | BCC"),
        ],
    )

    assert [item["Sample_ID"] for item in result.document["items"]] == [
        "Alloy-A"
    ]


def test_empty_region_entity_does_not_become_a_structure_presence_claim():
    evidence = "The boundary separated the continuous precipitation (CP) region."
    fact = _structure_fact("Alloy-A", evidence)
    fact.data["entities"] = [
        {
            "entity_id": "temporary",
            "entity_type": "region",
            "role": "continuous_precipitation_region",
            "name_raw": "CP region",
            "features": [],
            "raw_expression": "continuous precipitation (CP) region",
            "source_evidence": [evidence],
        }
    ]

    result = materialize_candidate([_anchor("Alloy-A")], [fact])

    assert result.document["items"] == []
    assert any(
        issue.code == "structure_context_entity_removed" for issue in result.issues
    )
    assert any(issue.code == "empty_item_removed" for issue in result.issues)


def test_tex_phase_formula_and_row_index_cannot_anchor_material_items():
    anchors = [
        _anchor("S1"),
        InventoryAnchor(
            sample_id_raw="M23C6",
            material_name_raw=r"M_{23}C_{6} carbide",
            state_raw="precipitate phase",
            role="Target",
            data_nature="Experimental",
            source_evidence=[r"M_{23}C_{6} carbide"],
            confidence=0.9,
        ),
        InventoryAnchor(
            sample_id_raw="M5B3_row1",
            material_name_raw=r"M_{5}B_{3} boride phase",
            state_raw="boride precipitate",
            role="Target",
            data_nature="Experimental",
            source_evidence=[r"M_{5}B_{3} boride phase"],
            confidence=0.9,
        ),
    ]

    result = materialize_candidate(
        anchors,
        [_structure_fact("S1", "S1 contained carbide and boride precipitates")],
    )

    assert [item["Sample_ID"] for item in result.document["items"]] == ["S1"]


def test_citation_only_sample_label_is_reassigned_to_reference_material():
    anchor = InventoryAnchor(
        sample_id_raw="Amato et al.",
        material_name_raw="Inconel 625",
        state_raw="LPBF HIPed",
        role="Reference",
        data_nature="Literature_Experimental",
        source_evidence=["Amato et al. reported HIPed Inconel 625"],
        confidence=0.9,
    )

    result = materialize_candidate(
        [anchor],
        [
            _structure_fact(
                "Amato et al.",
                "Amato et al. reported HIPed Inconel 625 with fine grains",
            )
        ],
    )

    assert [item["Sample_ID"] for item in result.document["items"]] == [
        "Inconel 625"
    ]
    assert result.document["items"][0]["Role"] == "Reference"
    assert result.document["items"][0]["Data_Nature"] == "Literature_Experimental"


def test_citation_anchor_without_a_material_owner_is_rejected():
    anchor = InventoryAnchor(
        sample_id_raw="Literature [12]",
        material_name_raw="Fatemi et al.",
        state_raw=None,
        role="Reference",
        data_nature="Literature_Experimental",
        source_evidence=["Literature [12]"],
        confidence=0.8,
    )

    result = materialize_candidate(
        [_anchor("S1"), anchor],
        [_structure_fact("S1", "S1 contained fine grains")],
    )

    assert [item["Sample_ID"] for item in result.document["items"]] == ["S1"]


def test_author_year_and_citation_qualified_reference_labels_use_material_owner():
    anchors = [
        InventoryAnchor(
            sample_id_raw=label,
            material_name_raw="Inconel 625",
            state_raw=state,
            role="Reference",
            data_nature="Literature_Experimental",
            source_evidence=[evidence],
            confidence=0.9,
        )
        for label, state, evidence in (
            (
                "Mostafaei et al., 2016a",
                "as-sintered",
                "Mostafaei et al., 2016a reported as-sintered Inconel 625",
            ),
            (
                "binder jetting aged (Mostafaei et al., 2017)",
                "aged",
                "binder jetting aged Inconel 625 was reported by Mostafaei et al., 2017",
            ),
            (
                "Blake 1985",
                "wrought",
                "Blake 1985 reported wrought Inconel 625",
            ),
        )
    ]
    facts = [
        _structure_fact(anchor.sample_id_raw, anchor.source_evidence[0])
        for anchor in anchors
    ]

    result = materialize_candidate(anchors, facts)

    sample_ids = [item["Sample_ID"] for item in result.document["items"]]
    assert set(sample_ids) == {
        "Inconel 625 [as-sintered]",
        "Inconel 625 [aged]",
        "Inconel 625 [wrought]",
    }
    assert all("Mostafaei" not in sample and "Blake" not in sample for sample in sample_ids)
    assert sum(
        len(
            item["Extracted_Data"]["Structure"]["Structure_Observations"]
        )
        for item in result.document["items"]
    ) == 3


def test_author_year_shape_is_not_rewritten_for_primary_experimental_sample():
    anchor = InventoryAnchor(
        sample_id_raw="Blake 1985",
        material_name_raw="prototype alloy",
        state_raw=None,
        role="Target",
        data_nature="Experimental",
        source_evidence=["Blake 1985 was the source sample label"],
        confidence=0.9,
    )

    result = materialize_candidate(
        [anchor],
        [_structure_fact("Blake 1985", "Blake 1985 contained fine grains")],
    )

    assert [item["Sample_ID"] for item in result.document["items"]] == [
        "Blake 1985"
    ]


def test_non_material_anchor_routes_to_existing_unique_material_owner():
    evidence = "the coarse rosette region of Al92Ti2Fe2Co2Ni2 had high strength"
    region = InventoryAnchor(
        sample_id_raw="coarse rosette region",
        material_name_raw="Al92Ti2Fe2Co2Ni2",
        state_raw="post-deformation micropillar",
        role="Target",
        data_nature="Experimental",
        source_evidence=[evidence],
        confidence=0.9,
    )

    result = materialize_candidate(
        [_anchor("Al92Ti2Fe2Co2Ni2"), region],
        [_structure_fact("coarse rosette region", evidence)],
    )

    assert [item["Sample_ID"] for item in result.document["items"]] == [
        "Al92Ti2Fe2Co2Ni2"
    ]
    assert len(
        result.document["items"][0]["Extracted_Data"]["Structure"][
            "Structure_Observations"
        ]
    ) == 1


def test_structural_entity_without_existing_material_owner_is_not_promoted():
    precipitate = InventoryAnchor(
        sample_id_raw="needle-like nanoprecipitates",
        material_name_raw="FeCoCrNiAl_x",
        state_raw="annealed",
        role="Target",
        data_nature="Experimental",
        source_evidence=["needle-like nanoprecipitates approached FeCoCrNiAl_x"],
        confidence=0.9,
    )

    result = materialize_candidate(
        [_anchor("EHEA"), precipitate],
        [
            _structure_fact("EHEA", "EHEA contained nanoprecipitates"),
            _structure_fact(
                "needle-like nanoprecipitates",
                "needle-like nanoprecipitates approached FeCoCrNiAl_x",
            ),
        ],
    )

    assert [item["Sample_ID"] for item in result.document["items"]] == ["EHEA"]


def test_unique_material_descriptor_anchor_redirects_to_its_short_code():
    anchors = [
        InventoryAnchor(
            sample_id_raw="BF",
            material_name_raw="Boron free",
            state_raw=None,
            role="Target",
            data_nature="Experimental",
            source_evidence=["Boron free (BF)"],
            confidence=0.95,
        ),
        InventoryAnchor(
            sample_id_raw="Boron free",
            material_name_raw=None,
            state_raw=None,
            role="Target",
            data_nature="Experimental",
            source_evidence=["Boron free alloy"],
            confidence=0.8,
        ),
    ]

    result = materialize_candidate(
        anchors,
        [
            _structure_fact("BF", "BF contained fine grains"),
            _structure_fact("Boron free", "Boron free alloy contained carbides"),
        ],
    )

    assert [item["Sample_ID"] for item in result.document["items"]] == ["BF"]
    observations = result.document["items"][0]["Extracted_Data"]["Structure"][
        "Structure_Observations"
    ]
    assert len(observations) == 2


def test_residual_alias_cannot_merge_reference_process_variant_into_target():
    anchors = [
        InventoryAnchor(
            sample_id_raw="Ti64",
            material_name_raw="Ti64",
            state_raw=None,
            role="Target",
            data_nature="Experimental",
            source_evidence=["Ti64 was deposited by WAAM"],
            confidence=0.95,
        ),
        InventoryAnchor(
            sample_id_raw="L-PBF Ti64",
            material_name_raw="L-PBF",
            state_raw="as-built",
            role="Reference",
            data_nature="Literature",
            source_evidence=["literature data for L-PBF Ti64"],
            confidence=0.9,
        ),
    ]

    result = materialize_candidate(
        anchors,
        [
            _structure_fact("Ti64", "Ti64 was deposited by WAAM"),
            _structure_fact("L-PBF Ti64", "L-PBF Ti64 had columnar grains"),
        ],
    )

    assert {item["Sample_ID"] for item in result.document["items"]} == {
        "Ti64",
        "L-PBF Ti64",
    }


def test_source_named_process_qualifier_reconciles_bare_target_alias():
    anchors = [
        InventoryAnchor(
            sample_id_raw="Ti64",
            material_name_raw="Ti64",
            state_raw=None,
            role="Target",
            data_nature="Experimental",
            source_evidence=["Ti64 material was deposited by the WAAM process"],
            confidence=0.95,
        ),
        InventoryAnchor(
            sample_id_raw="WAAM Ti64",
            material_name_raw="WAAM Ti64 wall",
            state_raw=None,
            role="Target",
            data_nature="Experimental",
            source_evidence=["WAAM Ti64 wall"],
            confidence=0.95,
        ),
        InventoryAnchor(
            sample_id_raw="L-PBF Ti64",
            material_name_raw="L-PBF",
            state_raw="as-built",
            role="Reference",
            data_nature="Literature",
            source_evidence=["literature data for L-PBF Ti64"],
            confidence=0.9,
        ),
    ]

    result = materialize_candidate(
        anchors,
        [
            _structure_fact("Ti64", "Ti64 was deposited by the WAAM process"),
            _structure_fact("L-PBF Ti64", "L-PBF Ti64 had columnar grains"),
        ],
    )

    assert {item["Sample_ID"] for item in result.document["items"]} == {
        "WAAM Ti64",
        "L-PBF Ti64",
    }


def test_material_class_suffix_is_not_treated_as_process_qualifier():
    anchors = [
        InventoryAnchor(
            sample_id_raw="Al5Ti5",
            material_name_raw="Al5Ti5",
            state_raw=None,
            role="Target",
            data_nature="Experimental",
            source_evidence=["Al5Ti5 HEA showed high corrosion resistance"],
            confidence=0.95,
        ),
        InventoryAnchor(
            sample_id_raw="Al5Ti5 HEA",
            material_name_raw="Al5Ti5 HEA",
            state_raw=None,
            role="Target",
            data_nature="Experimental",
            source_evidence=["Al5Ti5 HEA"],
            confidence=0.95,
        ),
    ]

    result = materialize_candidate(
        anchors,
        [
            _structure_fact("Al5Ti5", "Al5Ti5 contained fine grains"),
            _structure_fact("Al5Ti5 HEA", "Al5Ti5 HEA contained precipitates"),
        ],
    )

    assert {item["Sample_ID"] for item in result.document["items"]} == {
        "Al5Ti5",
        "Al5Ti5 HEA",
    }


def test_source_initialism_remains_display_label_when_long_name_is_more_frequent():
    anchors = [
        InventoryAnchor(
            sample_id_raw="BF",
            material_name_raw="Boron free",
            state_raw=None,
            role="Target",
            data_nature="Experimental",
            source_evidence=["Boron free (BF)"],
            confidence=0.95,
        ),
        *[
            InventoryAnchor(
                sample_id_raw="Boron free",
                material_name_raw=None,
                state_raw=None,
                role="Target",
                data_nature="Experimental",
                source_evidence=["Boron free alloy"],
                confidence=0.8,
            )
            for _ in range(3)
        ],
    ]

    result = materialize_candidate(
        anchors,
        [_structure_fact("Boron free", "Boron free alloy contained carbides")],
    )

    assert [item["Sample_ID"] for item in result.document["items"]] == ["BF"]


def test_unrelated_short_code_does_not_override_frequent_long_display_name():
    anchors = [
        InventoryAnchor(
            sample_id_raw="XZ",
            material_name_raw="Advanced powder",
            state_raw=None,
            role="Target",
            data_nature="Experimental",
            source_evidence=["XZ was the Advanced powder"],
            confidence=0.9,
        ),
        *[
            InventoryAnchor(
                sample_id_raw="Advanced powder",
                material_name_raw=None,
                state_raw=None,
                role="Target",
                data_nature="Experimental",
                source_evidence=["Advanced powder"],
                confidence=0.8,
            )
            for _ in range(2)
        ],
    ]

    result = materialize_candidate(
        anchors,
        [_structure_fact("Advanced powder", "Advanced powder contained fine grains")],
    )

    assert [item["Sample_ID"] for item in result.document["items"]] == [
        "Advanced powder"
    ]


def test_descriptor_anchor_is_not_redirected_when_shared_by_multiple_codes():
    descriptor = "prototype alloy"
    anchors = [
        InventoryAnchor(
            sample_id_raw=sample,
            material_name_raw=descriptor,
            state_raw=state,
            role="Target",
            data_nature="Experimental",
            source_evidence=[f"{sample} {descriptor} {state}"],
            confidence=0.9,
        )
        for sample, state in (("A1", "as-built"), ("A2", "aged"))
    ]
    anchors.append(_anchor(descriptor))

    result = materialize_candidate(
        anchors,
        [
            _structure_fact("A1", "A1 had fine grains"),
            _structure_fact("A2", "A2 had coarse grains"),
            _structure_fact(descriptor, "prototype alloy was examined"),
        ],
    )

    assert [item["Sample_ID"] for item in result.document["items"]] == ["A1", "A2"]


def test_forbidden_base_identity_cannot_bypass_filter_via_state_expansion():
    anchors = [
        _anchor("S1"),
        _anchor("FIB-sample-A", "fine-grain layer"),
        _anchor("Table 3 samples", "heat-treated"),
    ]
    facts = [
        _structure_fact("S1", "S1 contained fine grains"),
        _structure_fact("FIB-sample-A", "FIB-sample-A contained fine grains"),
        _structure_fact("Table 3 samples", "Table 3 samples were heat-treated"),
    ]

    result = materialize_candidate(anchors, facts)

    assert [item["Sample_ID"] for item in result.document["items"]] == ["S1"]


def test_inventory_declared_numeric_delay_states_remain_distinct_samples():
    anchors = [
        InventoryAnchor(
            sample_id_raw=delay,
            material_name_raw="Ti-6Al-4V wall",
            state_raw=delay.casefold(),
            role="Target",
            data_nature="Experimental",
            source_evidence=[f"Hardness map-{delay}"],
            confidence=0.9,
        )
        for delay in ("0 s Delay", "120 s Delay", "300 s Delay")
    ]
    # A weaker chunk may repeat the same source label without carrying the
    # inventory state. It must not veto the independently grounded state row.
    anchors.append(
        InventoryAnchor(
            sample_id_raw="120 s Delay",
            material_name_raw="Ti-6Al-4V wall",
            state_raw=None,
            role="Target",
            data_nature="Experimental",
            source_evidence=["120 s Delay wall"],
            confidence=0.7,
        )
    )

    result = materialize_candidate(
        anchors,
        [
            _structure_fact(delay, f"{delay} wall contained fine grains")
            for delay in ("0 s Delay", "120 s Delay", "300 s Delay")
        ],
    )

    assert [item["Sample_ID"] for item in result.document["items"]] == [
        "0 s Delay",
        "120 s Delay",
        "300 s Delay",
    ]


def test_bare_numeric_delay_header_still_cannot_create_material_item():
    result = materialize_candidate(
        [_anchor("Ti-6Al-4V")],
        [_structure_fact("120 s Delay", "120 s Delay")],
    )

    assert result.document["items"] == []
    assert any(issue.code == "unresolved_sample_alias" for issue in result.issues)


def test_free_text_state_descriptions_do_not_create_material_items():
    anchors = [
        _anchor("A", "block"),
        _anchor("A", "FCC"),
        _anchor("A", "LAAMed"),
        _anchor("A", "1030 °C/0.5h"),
    ]
    facts = [
        _structure_fact("A", "A block contained FCC"),
        _structure_fact("A", "A was LAAMed"),
    ]

    result = materialize_candidate(anchors, facts)

    assert [item["Sample_ID"] for item in result.document["items"]] == ["A"]


def test_tested_condition_does_not_create_material_state_item():
    anchors = [
        _anchor("A", "fatigue tested"),
        _anchor("A", "HCF"),
        _anchor("A", "creep tested"),
    ]
    facts = [
        _structure_fact("A", "A was examined after testing"),
    ]

    result = materialize_candidate(anchors, facts)

    assert [item["Sample_ID"] for item in result.document["items"]] == ["A"]


def test_structure_region_and_test_orientation_do_not_create_state_items():
    anchors = [
        _anchor("A", "as-built"),
        _anchor("A", "fracture surface"),
        _anchor("A", "horizontal orientation"),
    ]
    facts = [
        _structure_fact("A", "A fracture surface contained dimples"),
    ]

    result = materialize_candidate(anchors, facts)

    assert [item["Sample_ID"] for item in result.document["items"]] == ["A"]


def test_unclassified_temperature_duration_mentions_do_not_create_state_items():
    anchors = [
        _anchor("T0", "1030 °C/0.5h"),
        _anchor("T0", "1030 °C/2h"),
        _anchor("T0", "heat-treated"),
    ]

    result = materialize_candidate(
        anchors,
        [_structure_fact("T0", "T0 was heat-treated at 1030 °C")],
    )

    assert [item["Sample_ID"] for item in result.document["items"]] == ["T0"]


def test_post_test_observation_does_not_split_material_state():
    anchors = [
        _anchor("A", "as-built"),
        _anchor("A", "after creep test at 900 °C / 65 MPa"),
        _anchor("A", "creep-deformed"),
    ]

    result = materialize_candidate(
        anchors,
        [_structure_fact("A", "A was examined after the creep test")],
    )

    assert [item["Sample_ID"] for item in result.document["items"]] == ["A"]


def test_thermal_stabilization_routes_to_state_and_keeps_unqualified_base():
    def state_anchor(state: str) -> InventoryAnchor:
        return InventoryAnchor(
            sample_id_raw="Material-X",
            material_name_raw="prototype alloy",
            state_raw=state,
            role="Target",
            data_nature="Experimental",
            source_evidence=[f"Material-X {state}"],
            confidence=0.9,
        )

    evidence = "thermal-stabilized Material-X reached 900 MPa"
    prop = PropertyFact(
        sample_id_raw="Material-X",
        data={
            "property_id_candidate": "temp",
            "property_name_raw": "yield strength",
            "value_raw": "900",
            "unit_raw": "MPa",
            "test_method_raw": "tensile",
            "test_standard_raw": None,
            "test_condition_raw": "room temperature",
            "test_specimen_raw": None,
            "raw_note": None,
            "data_source": "text",
            "source_evidence": [evidence],
            "confidence": 0.9,
        },
        source_evidence=[evidence],
        confidence=0.9,
    )
    anchors = [
        state_anchor("as-printed"),
        state_anchor("thermal-stabilized"),
        state_anchor("pre-alloyed powder"),
        state_anchor("deformed sample"),
        state_anchor("deformed to 28 % plastic strain"),
    ]

    result = materialize_candidate(
        anchors,
        [prop, _structure_fact("Material-X", "Material-X contained ordered grains")],
    )

    items = {item["Sample_ID"]: item for item in result.document["items"]}
    assert set(items) == {"Material-X", "Material-X [thermal-stabilized]"}
    assert len(
        items["Material-X [thermal-stabilized]"]["Extracted_Data"]["Properties"]
    ) == 1
    assert all("deformed" not in sample.casefold() for sample in items)


def test_uppercase_source_code_is_not_rejected_as_element_symbol():
    result = materialize_candidate(
        [_anchor("CL"), _anchor("PL")],
        [
            _structure_fact("CL", "CL contained columnar grains"),
            _structure_fact("PL", "PL contained equiaxed grains"),
        ],
    )

    assert [item["Sample_ID"] for item in result.document["items"]] == ["CL", "PL"]


def test_comparison_mention_does_not_override_explicit_sample_owner():
    anchors = [_anchor("CL", "CL sample"), _anchor("PL", "PL sample")]
    fact = _structure_fact("PL", "PL had comparable strength to CL samples")

    result = materialize_candidate(anchors, [fact])

    assert [item["Sample_ID"] for item in result.document["items"]] == ["PL"]


def test_generic_variant_suffixes_merge_without_shared_material_descriptor():
    anchors = [
        _anchor("boron-free"),
        _anchor("boron-free alloy"),
        _anchor("boron-free version"),
    ]
    facts = [
        _structure_fact("boron-free", "boron-free contained fine grains"),
        _structure_fact("boron-free alloy", "boron-free alloy contained carbides"),
        _structure_fact("boron-free version", "boron-free version was compared"),
    ]

    result = materialize_candidate(anchors, facts)

    assert len(result.document["items"]) == 1
    assert len(
        result.document["items"][0]["Extracted_Data"]["Structure"][
            "Structure_Observations"
        ]
    ) == 3


def test_existing_base_absorbs_test_orientation_and_composition_column_labels():
    anchors = [
        _anchor("EPBF"),
        _anchor("EPBF / X"),
        _anchor("EPBF / Z"),
        _anchor("EPBF [X orientation]"),
        _anchor("T5"),
        _anchor("T5 (M)"),
        _anchor("T5 (N)"),
    ]
    facts = [
        _structure_fact("EPBF / X", "EPBF / X fractured"),
        _structure_fact("EPBF / Z", "EPBF / Z fractured"),
        _structure_fact("EPBF [X orientation]", "EPBF X orientation was tested"),
        _composition_fact("T5 (M)", "T5 (M)", "T5 measured composition"),
        _composition_fact("T5 (N)", "T5 (N)", "T5 nominal composition"),
    ]

    result = materialize_candidate(anchors, facts)

    assert [item["Sample_ID"] for item in result.document["items"]] == ["EPBF", "T5"]


def test_repeated_composition_source_labels_cannot_replace_base_state_owner():
    anchors = [
        _anchor("T5"),
        *[_anchor("$ T5 (M) $") for _ in range(6)],
        *[_anchor("$ T5 (N) $") for _ in range(6)],
    ]
    half_hour = _structure_fact("T5", "T5 at 1030 °C/0.5h had fine precipitates")
    half_hour.data["material_state"] = "1030 °C/0.5h"
    two_hours = _structure_fact("T5", "T5 at 1030 °C/2h had coarse precipitates")
    two_hours.data["material_state"] = "1030 °C/2h"

    result = materialize_candidate(anchors, [half_hour, two_hours])

    assert [item["Sample_ID"] for item in result.document["items"]] == [
        "T5 [1030 °C/0.5h]",
        "T5 [1030 °C/2h]",
    ]


def test_trailing_source_sample_code_routes_to_existing_identity():
    anchors = [_anchor("L70"), _anchor("multi-spot sample L70")]
    facts = [
        _structure_fact("L70", "L70 contained fine grains"),
        _structure_fact("multi-spot sample L70", "multi-spot sample L70 was measured"),
    ]

    result = materialize_candidate(anchors, facts)

    assert [item["Sample_ID"] for item in result.document["items"]] == ["L70"]


def test_shared_descriptor_reconciles_ocr_zero_and_generated_state_aliases():
    def anchor(sample: str, state: str) -> InventoryAnchor:
        return InventoryAnchor(
            sample_id_raw=sample,
            material_name_raw="prototype single-crystal alloy",
            state_raw=state,
            role="Target",
            data_nature="Experimental",
            source_evidence=[f"{sample} {state}"],
            confidence=0.9,
        )

    anchors = [
        anchor("T0", "heat-treated"),
        anchor("T0", "aged at 1030 °C"),
        anchor("TO (M)", "heat-treated"),
        anchor("TO (M)", "aged at 1030 °C"),
        anchor("TO (N)", "heat-treated"),
    ]
    facts = [
        _structure_fact("T0", "T0 was heat-treated"),
        _structure_fact("TO (M)", "TO measured composition was heat-treated"),
        _structure_fact("TO (N)", "TO nominal composition was heat-treated"),
    ]

    result = materialize_candidate(anchors, facts)

    sample_ids = [item["Sample_ID"] for item in result.document["items"]]
    assert len(sample_ids) == 1
    assert sum("heat-treated" in sample for sample in sample_ids) == 1
    observations = result.document["items"][0]["Extracted_Data"]["Structure"][
        "Structure_Observations"
    ]
    assert len(observations) == 3


def test_generic_sample_suffix_and_table_metric_are_not_separate_items():
    evidence = "AF sample had a yield strength of 900 MPa"
    prop = PropertyFact(
        sample_id_raw="AF sample",
        data={
            "property_id_candidate": "temp",
            "property_name_raw": "yield strength",
            "value_raw": "900",
            "unit_raw": "MPa",
            "test_method_raw": "tensile",
            "test_standard_raw": "",
            "test_condition_raw": "room temperature",
            "test_specimen_raw": "",
            "raw_note": "",
            "data_source": "table",
            "source_evidence": [evidence],
            "confidence": 0.9,
        },
        source_evidence=[evidence],
        confidence=0.9,
    )

    result = materialize_candidate(
        [_anchor("AF"), _anchor("AF sample"), _anchor("Elongation (%)")],
        [prop],
    )

    assert [item["Sample_ID"] for item in result.document["items"]] == ["AF"]


def test_non_material_presentation_suffixes_merge_only_into_existing_base():
    anchors = [
        _anchor("WAAM Ti64"),
        _anchor("WAAM Ti64 horizontal"),
        _anchor("WAAM Ti64 horizontal orientation"),
        _anchor("WAAM Ti64 oscillation build strategy"),
        _anchor("as built WAAM Ti64 (this study)"),
    ]
    facts = [
        _structure_fact(sample, f"{sample} had a reported feature")
        for sample in (
            "WAAM Ti64",
            "WAAM Ti64 horizontal",
            "WAAM Ti64 horizontal orientation",
            "WAAM Ti64 oscillation build strategy",
            "as built WAAM Ti64 (this study)",
        )
    ]

    result = materialize_candidate(anchors, facts)

    assert [row["Sample_ID"] for row in result.document["items"]] == [
        "WAAM Ti64",
        "WAAM Ti64 horizontal",
    ]
    counts = {
        row["Sample_ID"]: len(
            row["Extracted_Data"]["Structure"]["Structure_Observations"]
        )
        for row in result.document["items"]
    }
    assert counts == {"WAAM Ti64": 3, "WAAM Ti64 horizontal": 2}


def test_feedstock_presentation_suffixes_merge_conservatively():
    anchors = [
        _anchor("R30b"),
        _anchor("R30b powders"),
        _anchor("New"),
        _anchor("new powders"),
        _anchor("Al5Ti5 HEA"),
        _anchor("Al5Ti5 HEA powders"),
        _anchor("as-received powder"),
        _anchor("as-received powders"),
    ]
    facts = [
        _structure_fact(sample, f"{sample} had a reported morphology")
        for sample in (
            "R30b",
            "R30b powders",
            "New",
            "new powders",
            "Al5Ti5 HEA",
            "Al5Ti5 HEA powders",
            "as-received powder",
            "as-received powders",
        )
    ]

    result = materialize_candidate(anchors, facts)

    assert {item["Sample_ID"] for item in result.document["items"]} == {
        "R30b",
        "New",
        "Al5Ti5 HEA",
        "as-received powder",
    }
    assert all(
        len(item["Extracted_Data"]["Structure"]["Structure_Observations"]) == 2
        for item in result.document["items"]
    )


def test_feedstock_suffix_does_not_collapse_without_source_base_anchor():
    result = materialize_candidate(
        [_anchor("R30b powders")],
        [_structure_fact("R30b powders", "R30b powders were spherical")],
    )

    assert [item["Sample_ID"] for item in result.document["items"]] == [
        "R30b powders"
    ]


def test_shared_material_descriptor_does_not_become_third_state_item():
    descriptor = "Al-3.89Cu-1.22Li-0.98Sc-0.43Zr (wt%)"
    anchors = [
        InventoryAnchor(
            sample_id_raw=sample,
            material_name_raw=descriptor,
            state_raw=state,
            role="Target",
            data_nature="Experimental",
            source_evidence=[f"{sample} {descriptor}"],
            confidence=0.9,
        )
        for sample, state in (("AF", "as-fabricated"), ("HT", "heat-treated"))
    ]
    anchors.append(_anchor(descriptor))

    result = materialize_candidate(
        anchors,
        [
            _structure_fact("AF", "AF had fine grains"),
            _structure_fact("HT", "HT had coarse grains"),
            _structure_fact(descriptor, f"{descriptor} contained grains"),
        ],
    )

    assert [item["Sample_ID"] for item in result.document["items"]] == ["AF", "HT"]


def test_shared_descriptor_identity_fact_routes_to_existing_state_items():
    descriptor = "Al-3.89Cu-1.22Li-0.98Sc-0.43Zr (wt%)"
    anchors = [
        InventoryAnchor(
            sample_id_raw=sample,
            material_name_raw=descriptor,
            state_raw=state,
            role="Target",
            data_nature="Experimental",
            source_evidence=[f"{sample} {descriptor}"],
            confidence=0.9,
        )
        for sample, state in (("AF", "as-fabricated"), ("HT", "heat-treated"))
    ]

    result = materialize_candidate(
        anchors,
        [
            _identity_fact(descriptor, descriptor, "gas-atomized alloy powder"),
            _structure_fact("AF", "AF had fine grains"),
            _structure_fact("HT", "HT had coarse grains"),
        ],
    )

    assert [item["Sample_ID"] for item in result.document["items"]] == ["AF", "HT"]
    assert any(
        issue.code == "unresolved_sample_alias"
        and issue.sample_id_raw == descriptor
        for issue in result.issues
    )


def test_shared_material_descriptor_does_not_broadcast_non_identity_fact():
    descriptor = "Ti-6Al-4V"
    anchors = [
        InventoryAnchor(
            sample_id_raw=sample,
            material_name_raw=descriptor,
            state_raw=state,
            role="Target",
            data_nature="Experimental",
            source_evidence=[f"{sample} {descriptor}"],
            confidence=0.9,
        )
        for sample, state in (
            ("WAAM-H", "as-built horizontal"),
            ("WAAM-V", "as-built vertical"),
        )
    ]

    result = materialize_candidate(
        anchors,
        [
            _structure_fact(
                descriptor,
                "Ti-6Al-4V specimens were examined by optical microscopy",
            ),
            _structure_fact("WAAM-H", "WAAM-H had columnar grains"),
        ],
    )

    assert [row["Sample_ID"] for row in result.document["items"]] == ["WAAM-H"]
    observations = result.document["items"][0]["Extracted_Data"]["Structure"][
        "Structure_Observations"
    ]
    assert [row["original"] for row in observations] == [
        "WAAM-H had columnar grains"
    ]
    assert any(
        issue.code == "unresolved_sample_alias"
        and issue.sample_id_raw == descriptor
        for issue in result.issues
    )


def test_manufacturing_prefix_variant_of_shared_descriptor_is_not_a_new_item():
    shared_name = "LPBF-fabricated Al-Cu-Li-Sc-Zr alloy"
    anchors = [
        InventoryAnchor(
            sample_id_raw=sample,
            material_name_raw=shared_name,
            state_raw=state,
            role="Target",
            data_nature="Experimental",
            source_evidence=[f"{sample} {shared_name}"],
            confidence=0.9,
        )
        for sample, state in (("AF", "as-fabricated"), ("HT", "heat-treated"))
    ]

    result = materialize_candidate(
        anchors,
        [
            _identity_fact(
                "Al-Cu-Li-Sc-Zr alloy",
                "Al-Cu-Li-Sc-Zr alloy",
                "Al-Cu-Li-Sc-Zr alloy",
            ),
            _structure_fact("AF", "AF had fine grains"),
            _structure_fact("HT", "HT had coarse grains"),
        ],
    )

    assert [item["Sample_ID"] for item in result.document["items"]] == ["AF", "HT"]


def test_material_prefix_and_unique_state_prefix_variants_merge_anchor_identities():
    anchors = [
        InventoryAnchor(
            sample_id_raw=sample,
            material_name_raw="Ti-6Al-4V",
            state_raw=state,
            role="Target",
            data_nature="Experimental",
            source_evidence=[sample],
            confidence=0.9,
        )
        for sample, state in (
            ("WAAM", "deposit"),
            ("as-built WAAM", "as-built"),
            ("as-built WAAM Ti-6Al-4V", "as-built"),
        )
    ]

    result = materialize_candidate(
        anchors,
        [
            _structure_fact("WAAM", "WAAM had fine grains"),
            _structure_fact(
                "as-built WAAM Ti-6Al-4V",
                "as-built WAAM Ti-6Al-4V had acicular grains",
            ),
        ],
    )

    assert len(result.document["items"]) == 1


def test_feedstock_label_routes_to_named_process_sample_and_limits_are_rejected():
    result = materialize_candidate(
        [_anchor("WAAM"), _anchor("EBAM")],
        [
            _composition_fact(
                "WAAM Feedstock Ti-6Al-4V Grade 23",
                "WAAM Feedstock Ti-6Al-4V Grade 23",
                "WAAM feedstock contained 1 wt% Zr",
            ),
            _composition_fact(
                "Grade 23 Ti-6Al-4V Limits",
                "Grade 23 Ti-6Al-4V Limits",
                "Grade 23 Ti-6Al-4V Limits contained 1 wt% Zr",
            ),
            _structure_fact("EBAM", "EBAM had coarse grains"),
        ],
    )

    assert [item["Sample_ID"] for item in result.document["items"]] == ["EBAM", "WAAM"]
    waam = next(item for item in result.document["items"] if item["Sample_ID"] == "WAAM")
    assert len(
        waam["Extracted_Data"]["Composition"]["Composition_Observations"]
    ) == 1


def test_identity_only_reference_does_not_create_empty_material_item():
    result = materialize_candidate(
        [_anchor("Target-A")],
        [
            _structure_fact("Target-A", "Target-A had fine grains"),
            _identity_fact("IN625", "IN625", "IN625"),
        ],
    )

    assert [item["Sample_ID"] for item in result.document["items"]] == ["Target-A"]


def test_explicit_state_anchor_merges_unique_material_presentation_alias():
    anchors = [
        InventoryAnchor(
            sample_id_raw="mill annealed",
            material_name_raw="Ti-6Al-4V",
            state_raw="mill annealed",
            role="Reference",
            data_nature="Experimental",
            source_evidence=["mill annealed (wrought) Ti-6Al-4V"],
            confidence=0.9,
        ),
        InventoryAnchor(
            sample_id_raw="wrought Ti-6Al-4V",
            material_name_raw="Ti-6Al-4V",
            state_raw="mill annealed condition",
            role="Reference",
            data_nature="Experimental",
            source_evidence=["mill annealed (wrought) Ti-6Al-4V"],
            confidence=0.9,
        ),
    ]

    result = materialize_candidate(
        anchors,
        [
            _structure_fact("mill annealed", "mill annealed had equiaxed grains"),
            _structure_fact("wrought Ti-6Al-4V", "wrought Ti-6Al-4V had fine grains"),
        ],
    )

    assert len(result.document["items"]) == 1


def test_distinct_explicit_states_keep_unqualified_fact_on_one_base_item():
    anchors = [_anchor("A", "as-built"), _anchor("A", "aged"), _anchor("B")]

    result = materialize_candidate(
        anchors,
        [_composition_fact("A", "A", "A contained 1 wt% Zr")],
    )

    assert [row["Sample_ID"] for row in result.document["items"]] == ["A"]
    observations = result.document["items"][0]["Extracted_Data"]["Composition"][
        "Composition_Observations"
    ]
    assert len(observations) == 1


def test_unqualified_property_is_not_broadcast_across_explicit_states():
    evidence = "A had a yield strength of 900 MPa"
    fact = PropertyFact(
        sample_id_raw="A",
        data={
            "property_id_candidate": "temp",
            "property_name_raw": "yield strength",
            "value_raw": "900",
            "unit_raw": "MPa",
            "test_method_raw": "tensile",
            "test_standard_raw": None,
            "test_condition_raw": "",
            "test_specimen_raw": None,
            "raw_note": None,
            "data_source": "text",
            "source_evidence": [evidence],
            "confidence": 0.9,
        },
        source_evidence=[evidence],
        confidence=0.9,
    )

    result = materialize_candidate(
        [_anchor("A", "as-built"), _anchor("A", "aged")],
        [fact],
    )

    assert [row["Sample_ID"] for row in result.document["items"]] == ["A"]
    assert len(result.document["items"][0]["Extracted_Data"]["Properties"]) == 1


def test_state_evidence_narrows_a_base_label_to_the_matching_state():
    anchors = [_anchor("A", "as-built"), _anchor("A", "aged at 700 °C")]

    result = materialize_candidate(
        anchors,
        [
            _structure_fact("A", "A in the as-built condition had fine grains"),
            _structure_fact("A", "A aged at 700 °C had coarse grains"),
        ],
    )

    items = {row["Sample_ID"]: row for row in result.document["items"]}
    assert set(items) == {"A [as-built]", "A [aged at 700 °C]"}
    assert all(
        len(row["Extracted_Data"]["Structure"]["Structure_Observations"]) == 1
        for row in items.values()
    )
    assert sum(
        issue.code == "fact_owner_state_reconciled" for issue in result.issues
    ) == 2


def test_observation_local_numeric_states_create_unique_family_members():
    half_hour = _structure_fact("T0", "T0 at 1030 °C/0.5h had fine precipitates")
    half_hour.data["material_state"] = "1030 °C/0.5h"
    two_hours = _structure_fact("T0", "T0 at 1030 °C/2h had coarse precipitates")
    two_hours.data["material_state"] = "1030 °C/2h"

    result = materialize_candidate([_anchor("T0")], [half_hour, two_hours])

    assert [row["Sample_ID"] for row in result.document["items"]] == [
        "T0 [1030 °C/0.5h]",
        "T0 [1030 °C/2h]",
    ]
    assert sum(
        issue.code == "fact_owner_state_reconciled" for issue in result.issues
    ) == 2


def test_owner_state_audit_groups_facts_with_the_same_transition():
    first = _structure_fact("T0", "T0 at 1030 °C/0.5h had fine precipitates")
    first.data["material_state"] = "1030 °C/0.5h"
    second = _structure_fact("T0", "T0 at 1030 °C/0.5h had ordered precipitates")
    second.data["material_state"] = "1030 °C/0.5h"

    result = materialize_candidate([_anchor("T0")], [first, second])

    audits = [
        issue for issue in result.issues
        if issue.code == "fact_owner_state_reconciled"
    ]
    assert len(audits) == 1
    assert audits[0].actual["before_owner"] == "T0"
    assert audits[0].actual["after_owner"] == "T0 [1030 °C/0.5h]"
    assert len(audits[0].actual["facts"]) == 2
    assert len(audits[0].evidence) == 2


def test_unqualified_observation_state_does_not_invent_numeric_state_item():
    fact = _structure_fact("T0", "T0 was examined in the initial condition")
    fact.data["material_state"] = "Initial"

    result = materialize_candidate([_anchor("T0")], [fact])

    assert [row["Sample_ID"] for row in result.document["items"]] == ["T0"]
    assert not any(
        issue.code == "fact_owner_state_reconciled" for issue in result.issues
    )


def test_local_initial_state_is_not_replaced_by_post_test_table_sibling():
    initial = _structure_fact(
        "T0",
        "| State | Initial | 1% creep strain |\n| lattice | 0.3586 | 0.3595 |",
    )
    initial.data["material_state"] = "Initial state"
    creep = _structure_fact(
        "T0",
        "| State | Initial | 1% creep strain |\n| lattice | 0.3586 | 0.3595 |",
    )
    creep.data["material_state"] = "1% creep strain"

    result = materialize_candidate([_anchor("T0")], [initial, creep])

    assert [row["Sample_ID"] for row in result.document["items"]] == ["T0"]
    states = {
        row["material_state"]
        for row in result.document["items"][0]["Extracted_Data"]["Structure"][
            "Structure_Observations"
        ]
    }
    assert states == {"Initial state", "1% creep strain"}


def test_table_specimen_state_narrows_property_to_matching_state():
    anchors = [
        _anchor("A", "HT"),
        _anchor("A", "200 h thermal exposure"),
        _anchor("A", "500 h thermal exposure"),
    ]
    evidence = "Tensile strength / MPa | 220"
    fact = PropertyFact(
        sample_id_raw="A",
        data={
            "property_id_candidate": "temp",
            "property_name_raw": "tensile strength",
            "value_raw": "220",
            "unit_raw": "MPa",
            "test_method_raw": "tensile",
            "test_standard_raw": "",
            "test_condition_raw": "900 °C",
            "test_specimen_raw": "HT",
            "raw_note": "",
            "data_source": "table",
            "source_evidence": [evidence],
            "confidence": 0.95,
        },
        source_evidence=[evidence],
        confidence=0.95,
    )

    result = materialize_candidate(anchors, [fact])

    assert [row["Sample_ID"] for row in result.document["items"]] == ["A [HT]"]
    assert (
        result.document["items"][0]["Extracted_Data"]["Properties"][0]["value_raw"]
        == "220"
    )


def test_compact_table_duration_narrows_explicit_thermal_exposure_state():
    anchors = [
        _anchor("A", "thermal exposure at 900 °C for 200 h"),
        _anchor("A", "thermal exposure at 900 °C for 500 h"),
        _anchor("A", "200 h"),
        _anchor("A", "500 h"),
    ]
    evidence = "Tensile strength / MPa | 204"
    fact = PropertyFact(
        sample_id_raw="A",
        data={
            "property_id_candidate": "temp",
            "property_name_raw": "tensile strength",
            "value_raw": "204",
            "unit_raw": "MPa",
            "test_method_raw": "tensile",
            "test_standard_raw": "",
            "test_condition_raw": "900 °C",
            "test_specimen_raw": "200 h",
            "raw_note": "",
            "data_source": "table",
            "source_evidence": [evidence],
            "confidence": 0.95,
        },
        source_evidence=[evidence],
        confidence=0.95,
    )

    result = materialize_candidate(anchors, [fact])

    assert [row["Sample_ID"] for row in result.document["items"]] == [
        "A [thermal exposure at 900 °C for 200 h]"
    ]


def test_owner_qualified_cross_chunk_alias_routes_to_matching_state_only():
    anchors = [
        _anchor("WA", "sintered at 1225 °C"),
        _anchor("WA", "sintered at 1300 °C"),
        InventoryAnchor(
            sample_id_raw="WA powder alloy sintered samples",
            material_name_raw="alloy",
            state_raw="sintered",
            role="Target",
            data_nature="Experimental",
            source_evidence=["WA powder alloy sintered samples"],
            confidence=0.9,
        ),
    ]
    evidence = "WA powder alloy sintered samples | 1225 °C | 80 ± 25 µm"
    fact = PropertyFact(
        sample_id_raw="WA powder alloy sintered samples",
        data={
            "property_id_candidate": "temp",
            "property_name_raw": "grain size",
            "value_raw": "80 ± 25",
            "unit_raw": "µm",
            "test_method_raw": "",
            "test_standard_raw": "",
            "test_condition_raw": "sintered at 1225 °C",
            "test_specimen_raw": "",
            "raw_note": "",
            "data_source": "table",
            "source_evidence": [evidence],
            "confidence": 0.9,
        },
        source_evidence=[evidence],
        confidence=0.9,
    )

    result = materialize_candidate(anchors, [fact])

    assert [row["Sample_ID"] for row in result.document["items"]] == [
        "WA [sintered at 1225 °C]"
    ]


def test_shared_state_qualifier_is_narrowed_by_material_family():
    anchors = [
        _anchor("GA", "sintered at 1225 °C"),
        _anchor("GA", "sintered at 1300 °C"),
        _anchor("WA", "sintered at 1225 °C"),
        _anchor("WA", "sintered at 1300 °C"),
    ]
    evidence = "WA | sintering temperature 1225 °C | grain size 80 ± 25 µm"
    fact = PropertyFact(
        sample_id_raw="WA",
        data={
            "property_id_candidate": "temp",
            "property_name_raw": "grain size",
            "value_raw": "80 ± 25",
            "unit_raw": "µm",
            "test_method_raw": "",
            "test_standard_raw": "",
            "test_condition_raw": "sintering temperature 1225 °C",
            "test_specimen_raw": "",
            "raw_note": "",
            "data_source": "table",
            "source_evidence": [evidence],
            "confidence": 0.9,
        },
        source_evidence=[evidence],
        confidence=0.9,
    )

    result = materialize_candidate(anchors, [fact])

    assert [row["Sample_ID"] for row in result.document["items"]] == [
        "WA [sintered at 1225 °C]"
    ]


def test_base_descriptor_is_not_collapsed_into_one_of_its_generated_states():
    anchors = [
        _anchor("WA", "sintered at 1225 °C"),
        _anchor("WA", "sintered at 1300 °C"),
        InventoryAnchor(
            sample_id_raw="WA",
            material_name_raw="WA",
            state_raw=None,
            role="Target",
            data_nature="Experimental",
            source_evidence=["WA powder alloy"],
            confidence=0.9,
        ),
    ]
    evidence = "WA samples sintered at 1225 °C had grain sizes of 80 ± 25 µm"
    fact = _structure_fact("WA", evidence)
    fact.data["material_state"] = "sintered at 1225 °C"

    result = materialize_candidate(anchors, [fact])

    assert [row["Sample_ID"] for row in result.document["items"]] == [
        "WA [sintered at 1225 °C]"
    ]


def test_tex_and_abbreviated_state_mentions_merge_into_one_explicit_state():
    anchors = [
        _anchor("WA", "sintered at 1270 °C and aged at 745 °C for 20 h"),
        _anchor(
            "WA sample",
            r"sintered at 1270 ^\circC for 4 h and then aged at 745 ^\circC for 20 h",
        ),
    ]
    result = materialize_candidate(
        anchors,
        [
            _structure_fact(
                "WA",
                "WA sintered at 1270 °C and aged at 745 °C for 20 h had fine grains",
            ),
            _structure_fact(
                "WA sample",
                r"WA sample sintered at 1270 ^\circC for 4 h and then aged at "
                r"745 ^\circC for 20 h had fine precipitates",
            ),
        ],
    )

    assert len(result.document["items"]) == 1


def test_unique_inventory_state_label_routes_fact_to_long_material_identity():
    anchors = [
        InventoryAnchor(
            sample_id_raw="AlCoCrFeNi2.1 EHEA",
            material_name_raw="AlCoCrFeNi2.1 eutectic high-entropy alloy",
            state_raw="as-built (LPBF)",
            role="Target",
            data_nature="Experimental",
            source_evidence=["as-built AlCoCrFeNi2.1 EHEA"],
            confidence=0.9,
        ),
        InventoryAnchor(
            sample_id_raw="AlCoCrFeNi2.1 EHEA post-heat-treated",
            material_name_raw="AlCoCrFeNi2.1 eutectic high-entropy alloy",
            state_raw="post-heat-treated",
            role="Target",
            data_nature="Experimental",
            source_evidence=["post-heat-treated AlCoCrFeNi2.1 EHEA"],
            confidence=0.9,
        ),
    ]

    result = materialize_candidate(
        anchors,
        [
            _structure_fact("as-built", "the as-built sample had fine grains"),
            _structure_fact(
                "post-heat-treated",
                "the post-heat-treated sample had nanotwinned precipitates",
            ),
        ],
    )

    assert {row["Sample_ID"] for row in result.document["items"]} == {
        "AlCoCrFeNi2.1 EHEA",
        "AlCoCrFeNi2.1 EHEA post-heat-treated",
    }


def test_shared_state_label_remains_unresolved_instead_of_broadcasting():
    anchors = [
        _anchor("Alloy-A", "as-built"),
        _anchor("Alloy-B", "as-built"),
    ]

    result = materialize_candidate(
        anchors,
        [
            _structure_fact("Alloy-A", "Alloy-A had fine grains"),
            _structure_fact("as-built", "the as-built material contained pores"),
        ],
    )

    assert [row["Sample_ID"] for row in result.document["items"]] == ["Alloy-A"]
    assert any(
        issue.code == "unresolved_sample_alias" and issue.sample_id_raw == "as-built"
        for issue in result.issues
    )


def test_inner_observation_sample_overrides_element_outer_label():
    result = materialize_candidate(
        [_anchor("Alloy-1")],
        [_composition_fact("Zr", "Alloy-1", "Alloy-1 contained 1 wt% Zr")],
    )

    assert [row["Sample_ID"] for row in result.document["items"]] == ["Alloy-1"]
    observation = result.document["items"][0]["Extracted_Data"]["Composition"][
        "Composition_Observations"
    ][0]
    assert observation["sample_id"] == "Alloy-1"


def test_element_fact_without_sample_route_is_rejected_not_materialized():
    result = materialize_candidate(
        [_anchor("Alloy-1")],
        [
            _composition_fact("Alloy-1", "Alloy-1", "Alloy-1 contained Ni"),
            _composition_fact("Ni", "not_reported", "Ni was detected"),
        ],
    )

    assert [row["Sample_ID"] for row in result.document["items"]] == ["Alloy-1"]
    assert any(issue.code == "unresolved_element_sample" for issue in result.issues)


def test_anchor_material_name_builds_alias_without_merging_distinct_suffixes():
    anchors = [
        InventoryAnchor(
            sample_id_raw="A230",
            material_name_raw="Alloy 230",
            state_raw=None,
            role="Reference",
            data_nature="Experimental",
            source_evidence=["A230 (Alloy 230)"],
            confidence=0.9,
        ),
        InventoryAnchor(
            sample_id_raw="A230AM",
            material_name_raw="Alloy 230AM",
            state_raw=None,
            role="Target",
            data_nature="Experimental",
            source_evidence=["A230AM (Alloy 230AM)"],
            confidence=0.9,
        ),
    ]
    result = materialize_candidate(
        anchors,
        [
            _structure_fact("Alloy 230", "Alloy 230 contained coarse grains"),
            _structure_fact("Alloy 230AM", "Alloy 230AM contained fine grains"),
        ],
    )

    assert [row["Sample_ID"] for row in result.document["items"]] == [
        "A230",
        "A230AM",
    ]


def test_identity_alias_resolution_is_independent_of_cross_chunk_fact_order():
    result = materialize_candidate(
        [_anchor("A230")],
        [
            _identity_fact("not_reported", "Alloy 230", "Alloy 230 alloy"),
            _identity_fact("A230", "A230", "Alloy 230"),
            _structure_fact("Alloy 230", "Alloy 230 contained coarse grains"),
        ],
    )

    assert [row["Sample_ID"] for row in result.document["items"]] == ["A230"]


def test_material_identity_prefers_full_source_name_over_morphology_descriptor():
    anchor = InventoryAnchor(
        sample_id_raw="WA",
        material_name_raw="nickel-based alloy 625 WA powder",
        state_raw="as-received",
        role="Target",
        data_nature="Experimental",
        source_evidence=["SEM micrographs of nickel-based alloy 625 WA powder"],
        confidence=0.9,
    )
    morphology = CompositionFact(
        sample_id_raw="WA",
        fact_type="material_identity",
        data={
            "material_family": None,
            "material_name_raw": "irregular-shaped for WA powder",
            "designation_raw": None,
            "feedstock_form": "powder",
        },
        source_evidence=["WA powder was irregular-shaped"],
        confidence=0.8,
    )
    designation = CompositionFact(
        sample_id_raw="WA",
        fact_type="material_identity",
        data={
            "material_family": "nickel-based alloy",
            "material_name_raw": None,
            "designation_raw": "alloy 625",
            "feedstock_form": "WA powder",
        },
        source_evidence=["nickel-based alloy 625 powders: WA powder"],
        confidence=0.9,
    )

    result = materialize_candidate(
        [anchor],
        [morphology, designation, _structure_fact("WA", "WA contained fine grains")],
    )

    identity = result.document["items"][0]["Extracted_Data"]["Composition"][
        "Material_Identity"
    ]
    assert identity["material_name_raw"] == "nickel-based alloy 625 WA powder"
    issue = next(
        row
        for row in result.issues
        if row.code == "material_identity_descriptor_replaced"
    )
    assert issue.actual["before"]["material_name_raw"] == (
        "irregular-shaped for WA powder"
    )
    assert issue.actual["after"]["material_name_raw"] == (
        "nickel-based alloy 625 WA powder"
    )


def test_combined_sample_fact_is_attached_to_known_constituents_without_third_item():
    result = materialize_candidate(
        [_anchor("A230"), _anchor("A230AM")],
        [_structure_fact("A230 and A230AM", "A230 and A230AM contained carbides")],
    )

    assert [row["Sample_ID"] for row in result.document["items"]] == [
        "A230",
        "A230AM",
    ]
    assert all(
        len(row["Extracted_Data"]["Structure"]["Structure_Observations"]) == 1
        for row in result.document["items"]
    )
    assert any(issue.code == "shared_fact_routed" for issue in result.issues)


def test_numeric_designation_identity_does_not_invent_composition_values():
    result = materialize_candidate(
        [_anchor("A")],
        [
            _identity_fact("A", "Ti-6Al-4V", "Ti-6Al-4V alloy"),
            _structure_fact("A", "A was a Ti-6Al-4V alloy coupon"),
        ],
    )

    composition = result.document["items"][0]["Extracted_Data"]["Composition"]
    assert composition["Material_Identity"]["designation_raw"] == "Ti-6Al-4V"
    assert composition["Composition_Observations"] == []


def test_duplicate_properties_union_evidence_without_count_cap():
    base = {
        "property_id_candidate": "temp",
        "property_name_raw": "Yield strength",
        "value_raw": "900",
        "unit_raw": "MPa",
        "test_method_raw": "tensile",
        "test_standard_raw": "",
        "test_condition_raw": "room temperature",
        "test_specimen_raw": "",
        "raw_note": "",
        "data_source": "text",
        "source_evidence": ["yield strength was 900 MPa"],
        "confidence": 0.7,
    }
    first = PropertyFact(
        sample_id_raw="A",
        data=base,
        source_evidence=["yield strength was 900 MPa"],
        confidence=0.7,
    )
    second_data = {**base, "source_evidence": ["A showed a yield strength of 900 MPa"]}
    second = PropertyFact(
        sample_id_raw="A",
        data=second_data,
        source_evidence=["A showed a yield strength of 900 MPa"],
        confidence=0.9,
    )

    result = materialize_candidate([_anchor("A")], [first, second])
    properties = result.document["items"][0]["Extracted_Data"]["Properties"]

    assert len(properties) == 1
    assert properties[0]["property_id_candidate"] == "prop_001"
    assert len(properties[0]["source_evidence"]) == 2
    assert properties[0]["confidence"] == 0.9


def test_property_uses_validated_envelope_evidence_when_data_duplicate_is_scalar():
    evidence = (
        "the creep lifetime improved by 672 % at a stress of 45 MPa"
    )
    fact = PropertyFact(
        sample_id_raw="A",
        data={
            "property_id_candidate": "temp",
            "property_name_raw": "creep lifetime improvement",
            "value_raw": "672 %",
            "unit_raw": "%",
            "test_method_raw": "tensile creep test",
            "test_standard_raw": None,
            "test_condition_raw": "900 °C, 45 MPa",
            "test_specimen_raw": None,
            "raw_note": None,
            "data_source": "text",
            # Reproduce the provider variation observed in the live run: the
            # untyped data fragment duplicates the envelope list as a string.
            "source_evidence": evidence,
            "confidence": 0.1,
        },
        source_evidence=[evidence],
        confidence=0.9,
    )

    result = materialize_candidate([_anchor("A")], [fact])
    prop = result.document["items"][0]["Extracted_Data"]["Properties"][0]

    assert prop["source_evidence"] == [evidence]
    assert prop["confidence"] == 0.9


def test_reported_specimen_prevents_contradictory_not_reported_test_condition():
    evidence = "dog-bone specimens had a yield strength of 900 MPa"
    fact = PropertyFact(
        sample_id_raw="A",
        data={
            "property_id_candidate": "temp",
            "property_name_raw": "yield strength",
            "value_raw": "900",
            "unit_raw": "MPa",
            "test_method_raw": "tensile",
            "test_standard_raw": "",
            "test_condition_raw": "not_reported",
            "test_specimen_raw": "dog-bone specimens",
            "raw_note": "",
            "data_source": "text",
            "source_evidence": [evidence],
            "confidence": 0.8,
        },
        source_evidence=[evidence],
        confidence=0.8,
    )

    result = materialize_candidate([_anchor("A")], [fact])
    prop = result.document["items"][0]["Extracted_Data"]["Properties"][0]

    assert prop["test_condition_raw"] == "dog-bone specimens"


def test_processing_stage_ids_are_stable_after_generic_deduplication():
    stage = {
        "candidate_stage_id": "model-id",
        "stage_index_candidate": 8,
        "process_name_raw": "annealing",
        "process_code_candidate": None,
        "process_role_candidate": "post_process",
        "parameters_raw": [],
        "source_evidence": ["annealed at 800 °C"],
        "confidence": 0.8,
    }
    facts = [
        ProcessingFact(
            sample_id_raw="A",
            fact_type="process_stage",
            data=stage,
            source_evidence=["annealed at 800 °C"],
            confidence=0.8,
        )
    ]

    result = materialize_candidate([_anchor("A")], facts)
    stages = result.document["items"][0]["Extracted_Data"]["Processing"]["Process_Route"]["candidate_stages"]

    assert [row["candidate_stage_id"] for row in stages] == ["cand_001"]
    assert [row["stage_index_candidate"] for row in stages] == [1]


def test_provider_composition_keys_are_mechanically_canonicalized():
    fact = _composition_fact("A", "A", "A contained 2.1 wt% Co")
    fact.data.update(
        {
            "source_type": "experimental",
            "basis": "measured",
            "component_type": "element",
            "components": [
                {
                    "element": "Co",
                    "amount_value": 2.1,
                    "amount_unit": "wt%",
                    "amount_raw": "2.1",
                }
            ],
        }
    )

    result = materialize_candidate([_anchor("A")], [fact])
    observation = result.document["items"][0]["Extracted_Data"]["Composition"][
        "Composition_Observations"
    ][0]

    assert observation["source_type"] == "provided"
    assert observation["basis"] == "wt%"
    assert observation["component_type"] == "elemental"
    assert observation["components"][0] == {
        "name_raw": "Co",
        "canonical_name": None,
        "value_kind": "scalar",
        "value_raw": "2.1",
        "value": None,
        "unit_raw": "wt%",
        "canonical_unit": None,
        "data_nature": "reported",
    }


def test_qualitative_comparison_is_not_treated_as_numeric_inequality():
    fact = _composition_fact("A", "A", "A had limited Al content")
    fact.data["components"] = [
        {
            "name_raw": "Al",
            "value_kind": "inequality",
            "value_raw": "limited",
            "unit_raw": None,
            "data_nature": "reported",
        }
    ]

    result = materialize_candidate([_anchor("A")], [fact])
    component = result.document["items"][0]["Extracted_Data"]["Composition"][
        "Composition_Observations"
    ][0]["components"][0]

    assert component["value_kind"] == "categorical"
    assert component["value"] is None


def test_derived_composition_without_provenance_is_not_relabelled_or_emitted():
    reported = _composition_fact("A", "A", "A contained 1 wt% Zr")
    derived = _composition_fact("A", "A", "A was 0.2% higher than B")
    derived.data["components"] = [
        {
            "name_raw": "Zr",
            "value_kind": "scalar",
            "value_raw": "1.2",
            "unit_raw": "wt%",
            "data_nature": "derived",
        }
    ]

    result = materialize_candidate([_anchor("A")], [reported, derived])
    observations = result.document["items"][0]["Extracted_Data"]["Composition"][
        "Composition_Observations"
    ]

    assert len(observations) == 1
    assert observations[0]["components"][0]["data_nature"] == "reported"


def test_derived_structure_without_provenance_is_not_relabelled_or_emitted():
    fact = _structure_fact("A", "reported grains and a derived critical thickness")
    fact.data["features"] = [
        {
            "feature_name_raw": "critical thickness",
            "value_kind": "scalar",
            "value_raw": "0.515 mm",
            "data_nature": "derived",
            "source_evidence": ["their critical thickness is 0.515 mm"],
        },
        {
            "feature_name_raw": "grain morphology",
            "value_kind": "categorical",
            "value_raw": "columnar",
            "data_nature": "reported",
            "source_evidence": ["columnar grains were observed"],
        },
    ]

    result = materialize_candidate([_anchor("A")], [fact])
    features = result.document["items"][0]["Extracted_Data"]["Structure"][
        "Structure_Observations"
    ][0]["features"]

    assert [feature["feature_name_raw"] for feature in features] == [
        "grain morphology"
    ]
    assert features[0]["data_nature"] == "reported"


def test_derived_structure_with_provenance_is_preserved():
    fact = _structure_fact("A", "critical thickness calculated from t/d and d")
    fact.data["features"] = [
        {
            "feature_name_raw": "critical thickness",
            "value_kind": "scalar",
            "value_raw": "0.515 mm",
            "data_nature": "derived",
            "normalization": {
                "rule_id": "critical_thickness.v1",
                "formula": "t = (t/d) * d",
                "source_fields": ["critical_t_over_d", "grain_size"],
            },
            "source_evidence": ["critical t/d and grain size give 0.515 mm"],
        }
    ]

    result = materialize_candidate([_anchor("A")], [fact])
    feature = result.document["items"][0]["Extracted_Data"]["Structure"][
        "Structure_Observations"
    ][0]["features"][0]

    assert feature["data_nature"] == "derived"
    assert feature["normalization"]["rule_id"] == "critical_thickness.v1"


def test_provider_structure_keys_are_mechanically_canonicalized():
    fact = _structure_fact("A", "A contained fine ZrC particles")
    fact.data.update(
        {
            "structure_kind": "precipitate_particle",
            "source_type": "experimental",
            "entities": [
                {
                    "entity_type": "precipitate",
                    "phase_name_raw": "ZrC",
                    "source_evidence": "fine ZrC particles",
                }
            ],
            "features": [
                {
                    "feature_name": "size",
                    "value_raw": "fine",
                    "source_evidence": "fine ZrC particles",
                }
            ],
        }
    )

    result = materialize_candidate([_anchor("A")], [fact])
    observation = result.document["items"][0]["Extracted_Data"]["Structure"][
        "Structure_Observations"
    ][0]

    assert observation["structure_kind"] == "other"
    assert observation["source_type"] == "reported"
    assert observation["entities"][0]["name_raw"] == "ZrC"
    assert observation["features"][0]["feature_name_raw"] == "size"
    assert observation["features"][0]["value_kind"] == "text"


def test_structure_bounds_and_empty_observations_are_handled_deterministically():
    valid = _structure_fact("A", "particles were <20 nm and 166 ± 18 nm")
    valid.data["entities"] = [
        {
            "entity_type": "precipitate",
            "phase_name_raw": "particles",
            "source_evidence": "particles were <20 nm",
            "features": [
                {
                    "feature_name_raw": "particle size",
                    "value_kind": "inequality",
                    "value_raw": "<20 nm",
                    "source_evidence": "particles were <20 nm",
                }
            ],
        }
    ]
    valid.data["features"] = [
        {
            "feature_name_raw": "particle size",
            "value_kind": "range",
            "value_raw": "166 ± 18 nm",
            "source_evidence": "166 ± 18 nm",
        },
        {
            "feature_name_raw": "relative amount",
            "value_kind": "inequality",
            "value_raw": "much higher than the reference",
            "source_evidence": "much higher than the reference",
        },
    ]
    empty = _structure_fact("A", "microstructure images were collected")
    empty.data["entities"] = []
    empty.data["features"] = []

    result = materialize_candidate([_anchor("A")], [valid, empty])
    observations = result.document["items"][0]["Extracted_Data"]["Structure"][
        "Structure_Observations"
    ]

    assert len(observations) == 1
    nested = observations[0]["entities"][0]["features"][0]
    assert nested["qualifier"] == "<"
    assert nested["bound_value"] == 20.0
    top_level = observations[0]["features"][0]
    assert top_level["value_kind"] == "scalar"
    assert top_level["value"] == 166.0
    assert top_level["value_stddev"] == 18.0
    assert observations[0]["features"][1]["value_kind"] == "text"


def test_provider_process_parameter_and_edge_aliases_are_canonicalized():
    stage_rows = []
    for stage_id, index, name in (("s1", 1, "printing"), ("s2", 2, "annealing")):
        parameters = (
            [
                {
                    "parameter_name_raw": "temperature",
                    "value_raw": "800",
                    "unit_raw": "^\\circC",
                    "source_evidence": "printing at 800 °C",
                }
            ]
            if index == 1
            else "temperature: 800 °C; time: 1 h"
        )
        stage_rows.append(
            ProcessingFact(
                sample_id_raw="A",
                fact_type="process_stage",
                data={
                    "candidate_stage_id": stage_id,
                    "stage_index_candidate": index,
                    "process_name_raw": name,
                    "process_code_candidate": "MODEL_GUESS",
                    "process_role_candidate": "unspecified",
                    "parameters_raw": parameters,
                    "source_evidence": [f"{name} at 800 °C for 1 h"],
                    "confidence": 0.8,
                },
                source_evidence=[f"{name} at 800 °C for 1 h"],
                confidence=0.8,
            )
        )
    edge = ProcessingFact(
        sample_id_raw="A",
        fact_type="process_edge",
        data={
            "source_candidate_stage_id": "s1",
            "target_candidate_stage_id": "s2",
            "edge_type": "sequential",
            "source_evidence": "printing then annealing",
        },
        source_evidence=["printing then annealing"],
        confidence=0.8,
    )

    result = materialize_candidate([_anchor("A")], [*stage_rows, edge])
    route = result.document["items"][0]["Extracted_Data"]["Processing"][
        "Process_Route"
    ]

    assert all(stage["process_code_candidate"] is None for stage in route["candidate_stages"])
    assert route["candidate_stages"][0]["parameters_raw"][0][
        "parameter_name_raw"
    ] == "temperature"
    assert route["candidate_stages"][0]["parameters_raw"][0]["unit_raw"] == "°C"
    assert route["candidate_edges"] == []


def test_forbidden_test_slot_is_not_materialized_as_process_parameter():
    stage = ProcessingFact(
        sample_id_raw="A",
        fact_type="process_stage",
        data={
            "candidate_stage_id": "s1",
            "stage_index_candidate": 1,
            "process_name_raw": "powder recycling",
            "process_code_candidate": None,
            "process_role_candidate": "unspecified",
            "parameters_raw": [
                {
                    "parameter_name_raw": "number_of_cycles",
                    "value_raw": "30",
                    "unit_raw": "cycles",
                    "source_evidence": "powder after 30 cycles",
                },
                {
                    "parameter_name_raw": "total heating time",
                    "value_raw": "300",
                    "unit_raw": "h",
                    "source_evidence": "total heating time of 300 h",
                },
            ],
            "source_evidence": ["powder after 30 cycles; total heating time of 300 h"],
            "confidence": 0.8,
        },
        source_evidence=["powder after 30 cycles; total heating time of 300 h"],
        confidence=0.8,
    )

    result = materialize_candidate([_anchor("A")], [stage])
    parameters = result.document["items"][0]["Extracted_Data"]["Processing"][
        "Process_Route"
    ]["candidate_stages"][0]["parameters_raw"]

    assert [row["parameter_name_raw"] for row in parameters] == ["total heating time"]


def test_isolated_parallel_edge_falls_back_to_linear_stage_order():
    stages = []
    for stage_id, index, name in (("s1", 1, "PBF-LB"), ("s2", 2, "PBF-EB")):
        stages.append(
            ProcessingFact(
                sample_id_raw="A",
                fact_type="process_stage",
                data={
                    "candidate_stage_id": stage_id,
                    "stage_index_candidate": index,
                    "process_name_raw": name,
                    "process_code_candidate": None,
                    "process_role_candidate": "unspecified",
                    "parameters_raw": [],
                    "source_evidence": [name],
                    "confidence": 0.8,
                },
                source_evidence=[name],
                confidence=0.8,
            )
        )
    edge = ProcessingFact(
        sample_id_raw="A",
        fact_type="process_edge",
        data={
            "source_candidate_stage_id": "s1",
            "target_candidate_stage_id": "s2",
            "edge_type": "parallel",
            "source_evidence": "PBF-LB and PBF-EB",
        },
        source_evidence=["PBF-LB and PBF-EB"],
        confidence=0.8,
    )

    result = materialize_candidate([_anchor("A")], [*stages, edge])
    route = result.document["items"][0]["Extracted_Data"]["Processing"][
        "Process_Route"
    ]

    assert route["candidate_edges"] == []


def test_process_text_without_grounded_stage_is_not_promoted():
    process_text = ProcessingFact(
        sample_id_raw="A",
        fact_type="process_text",
        data={
            "original": "A was fully heat treated",
            "simplified": "full heat treatment",
        },
        source_evidence=["A was fully heat treated"],
        confidence=0.8,
    )

    result = materialize_candidate([_anchor("A")], [process_text])
    processing = result.document["items"][0]["Extracted_Data"]["Processing"]

    assert processing["Process_Text"] == {
        "original": "not_reported",
        "simplified": "not_reported",
    }
    assert processing["Process_Route"]["candidate_stages"] == []
    assert any(
        issue.code == "process_text_without_stage_discarded"
        for issue in result.issues
    )


def test_dataset_label_cannot_become_material_item():
    evidence = "the initial dataset contained 119 parameter combinations"
    fact = PropertyFact(
        sample_id_raw="initial dataset",
        data={
            "property_id_candidate": "temp",
            "property_name_raw": "number of combinations",
            "value_raw": "119",
            "unit_raw": None,
            "test_method_raw": None,
            "test_standard_raw": None,
            "test_condition_raw": None,
            "test_specimen_raw": None,
            "raw_note": None,
            "data_source": "text",
            "source_evidence": [evidence],
            "confidence": 0.9,
        },
        source_evidence=[evidence],
        confidence=0.9,
    )

    result = materialize_candidate(
        [_anchor("Alloy-A"), _anchor("initial dataset")],
        [_structure_fact("Alloy-A", "Alloy-A had fine grains"), fact],
    )

    assert [item["Sample_ID"] for item in result.document["items"]] == ["Alloy-A"]
    assert any(
        issue.code == "non_material_item_removed"
        and issue.sample_id_raw == "initial dataset"
        for issue in result.issues
    )


def test_comparison_only_reference_does_not_create_item():
    evidence = "Alloy-A was stronger than wrought Alloy-B"
    fact = PropertyFact(
        sample_id_raw="wrought Alloy-B",
        data={
            "property_id_candidate": "temp",
            "property_name_raw": "strength",
            "value_raw": "inferior to Alloy-A",
            "unit_raw": None,
            "test_method_raw": None,
            "test_standard_raw": None,
            "test_condition_raw": None,
            "test_specimen_raw": None,
            "raw_note": None,
            "data_source": "text",
            "source_evidence": [evidence],
            "confidence": 0.9,
        },
        source_evidence=[evidence],
        confidence=0.9,
    )
    reference = InventoryAnchor(
        sample_id_raw="wrought Alloy-B",
        material_name_raw="Alloy-B",
        state_raw="wrought",
        role="Reference",
        data_nature="Literature_Experimental",
        source_evidence=[evidence],
        confidence=0.9,
    )

    result = materialize_candidate(
        [_anchor("Alloy-A"), reference],
        [_structure_fact("Alloy-A", "Alloy-A had fine grains"), fact],
    )

    assert [item["Sample_ID"] for item in result.document["items"]] == ["Alloy-A"]
    assert any(
        issue.code == "reference_without_independent_fact_removed"
        for issue in result.issues
    )


def test_non_composition_energy_values_are_quarantined():
    evidence = "Zr and Al have similar oxygen affinity (Zr = -923 kJ/mol, Al = -924 kJ/mol)"
    fact = _composition_fact("Alloy-A", "Alloy-A", evidence)
    fact.data["basis"] = "unknown"
    fact.data["raw_expression"] = "Zr = -923 kJ/mol, Al = -924 kJ/mol"
    fact.data["components"] = [
        {
            "name_raw": "Zr",
            "value_kind": "scalar",
            "value_raw": "-923",
            "unit_raw": "kJ/mol",
            "data_nature": "reported",
        },
        {
            "name_raw": "Al",
            "value_kind": "scalar",
            "value_raw": "-924",
            "unit_raw": "kJ/mol",
            "data_nature": "reported",
        },
    ]

    result = materialize_candidate(
        [_anchor("Alloy-A")],
        [fact, _structure_fact("Alloy-A", "Alloy-A had fine grains")],
    )

    composition = result.document["items"][0]["Extracted_Data"]["Composition"]
    assert composition["Composition_Observations"] == []
    assert any(
        issue.code == "fact_quarantined_wrong_axis" for issue in result.issues
    )


def test_composition_unit_aliases_and_missing_unit_placeholders_are_retained():
    cases = [
        ("Ti-47Al-2Cr-2Nb", "Al", "47", "not_reported", "unknown"),
        ("Alloy-A contains 2 Wt (%) Cr", "Cr", "2", "Wt (%)", "wt%"),
        ("Alloy-A contains 3 At. (%) Nb", "Nb", "3", "At. (%)", "at%"),
        ("Alloy-A contains 4 wt-% Mo", "Mo", "4", "wt-%", "wt%"),
        ("Alloy-A contains 5 W% W", "W", "5", "W%", "wt%"),
    ]
    for evidence, component, value, unit, basis in cases:
        fact = _composition_fact("Alloy-A", "Alloy-A", evidence)
        fact.data["basis"] = basis
        fact.data["raw_expression"] = evidence
        fact.data["components"] = [
            {
                "name_raw": component,
                "value_kind": "scalar",
                "value_raw": value,
                "unit_raw": unit,
                "data_nature": "reported",
            }
        ]

        result = materialize_candidate([_anchor("Alloy-A")], [fact])

        observations = result.document["items"][0]["Extracted_Data"]["Composition"][
            "Composition_Observations"
        ]
        assert len(observations) == 1
        assert observations[0]["components"][0]["name_raw"] == component
        assert not any(
            issue.code == "fact_quarantined_wrong_axis" for issue in result.issues
        )


def test_phase_fraction_misfiled_as_composition_is_reclassified_to_structure():
    evidence = "the γ-phase content was 40 % for L70"
    fact = _composition_fact("L70", "L70", evidence)
    fact.data["basis"] = "unknown"
    fact.data["component_type"] = "phase"
    fact.data["raw_expression"] = "40 % γ-phase"
    fact.data["components"] = [
        {
            "name_raw": "γ-phase",
            "value_kind": "scalar",
            "value_raw": "40",
            "unit_raw": "%",
            "data_nature": "reported",
        }
    ]

    result = materialize_candidate([_anchor("L70")], [fact])

    extracted = result.document["items"][0]["Extracted_Data"]
    assert extracted["Composition"]["Composition_Observations"] == []
    feature = extracted["Structure"]["Structure_Observations"][0]["features"][0]
    assert feature["feature_name_raw"] == "γ-phase fraction"
    assert feature["value_raw"] == "40"
    assert any(issue.code == "fact_axis_reclassified" for issue in result.issues)


def test_grain_measurement_property_is_reclassified_to_structure():
    evidence = "the average equivalent circle diameter of grains was 16.0 µm"
    fact = PropertyFact(
        sample_id_raw="Alloy-A",
        data={
            "property_id_candidate": "temp",
            "property_name_raw": "average equivalent circle diameter of grains",
            "value_raw": "16.0",
            "unit_raw": "µm",
            "test_method_raw": None,
            "test_standard_raw": None,
            "test_condition_raw": None,
            "test_specimen_raw": None,
            "raw_note": None,
            "data_source": "text",
            "source_evidence": [evidence],
            "confidence": 0.9,
        },
        source_evidence=[evidence],
        confidence=0.9,
    )

    result = materialize_candidate([_anchor("Alloy-A")], [fact])

    item = result.document["items"][0]["Extracted_Data"]
    assert item["Properties"] == []
    observations = item["Structure"]["Structure_Observations"]
    assert len(observations) == 1
    assert observations[0]["features"][0]["value_raw"] == "16.0"
    assert any(issue.code == "fact_axis_reclassified" for issue in result.issues)


@pytest.mark.parametrize(
    ("property_name", "value", "unit"),
    [
        ("lattice parameter", "3.5990", "Å"),
        ("d-spacing value for (111) plane", "2.0779", "Å"),
        ("interplanar spacing", "0.208", "nm"),
        ("peak_position_for_crystallographic_planes_111", "51.026", "°2θ"),
        ("crystallographic_plane_111_2theta", "51.027", "°"),
    ],
)
def test_crystallographic_property_is_reclassified_to_structure(
    property_name: str, value: str, unit: str
):
    evidence = f"{property_name} was {value} {unit}"
    fact = PropertyFact(
        sample_id_raw="Alloy-A",
        data={
            "property_id_candidate": "temp",
            "property_name_raw": property_name,
            "value_raw": value,
            "unit_raw": unit,
            "test_method_raw": "XRD",
            "test_standard_raw": None,
            "test_condition_raw": None,
            "test_specimen_raw": None,
            "raw_note": None,
            "data_source": "table",
            "source_evidence": [evidence],
            "confidence": 0.9,
        },
        source_evidence=[evidence],
        confidence=0.9,
    )

    result = materialize_candidate([_anchor("Alloy-A")], [fact])

    extracted = result.document["items"][0]["Extracted_Data"]
    assert extracted["Properties"] == []
    observation = extracted["Structure"]["Structure_Observations"][0]
    assert observation["structure_kind"] == "phase_assemblage"
    assert observation["features"][0]["feature_name_raw"] == property_name
    assert observation["features"][0]["value_raw"] == value
    assert any(issue.code == "fact_axis_reclassified" for issue in result.issues)


def test_invalid_negative_tensile_chart_summary_is_quarantined():
    evidence = (
        "series: R1; kind=trend; n_points=10; "
        "key_points=start=(22.11,-50.0);mid=(36.95,561.1);end=(44.84,294.4)"
    )
    fact = PropertyFact(
        sample_id_raw="R1",
        data={
            "property_id_candidate": "temp",
            "property_name_raw": "tensile strength",
            "value_raw": "trend",
            "unit_raw": "MPa",
            "test_method_raw": "tensile",
            "test_standard_raw": None,
            "test_condition_raw": "1023 K",
            "test_specimen_raw": None,
            "raw_note": None,
            "data_source": "image",
            "source_evidence": [evidence],
            "confidence": 0.9,
        },
        source_evidence=[evidence],
        confidence=0.9,
    )

    source_text = "\n".join(
        [
            "> [Figure 10 VLM-digitized | line chart]",
            evidence,
            "context_omitted_series: 0",
            "data_csv: figure_10_digitized.csv",
            "full_data_externalized: true",
        ]
    )
    result = materialize_candidate([_anchor("R1")], [fact], source_text=source_text)

    assert result.document["items"] == []
    issue = next(
        issue for issue in result.issues if issue.code == "curve_series_quarantined"
    )
    assert issue.actual["data_csv"] == "figure_10_digitized.csv"


def test_source_labelled_orientation_siblings_remain_independent_items():
    anchors = [
        _anchor("EPBF"),
        _anchor("EPBF / X"),
        _anchor("EPBF / Z"),
    ]
    facts = [
        _structure_fact("EPBF / X", "EPBF / X had columnar grains"),
        _structure_fact("EPBF / Z", "EPBF / Z had equiaxed grains"),
    ]

    result = materialize_candidate(anchors, facts)

    assert [item["Sample_ID"] for item in result.document["items"]] == [
        "EPBF / X",
        "EPBF / Z",
    ]


def test_unique_qualified_sample_identity_owns_unqualified_cross_chunk_fact():
    evidence = "The Al concentration was 46.3 at.% in the multi-spot sample"
    fact = _composition_fact("multi-spot sample", "multi-spot sample", evidence)
    fact.data["basis"] = "at%"
    fact.data["raw_expression"] = "Al = 46.3 at.%"
    fact.data["components"] = [
        {
            "name_raw": "Al",
            "value_kind": "scalar",
            "value_raw": "46.3",
            "unit_raw": "at.%",
            "data_nature": "reported",
        }
    ]

    result = materialize_candidate(
        [
            _anchor("multi-spot melt sample"),
            _anchor("L70").model_copy(
                update={"material_name_raw": "multi-spot sample"}
            ),
            _anchor("L90").model_copy(
                update={"material_name_raw": "multi-spot sample"}
            ),
        ],
        [
            _structure_fact(
                "multi-spot melt sample", "multi-spot melt sample had fine grains"
            ),
            fact,
        ],
    )

    assert [item["Sample_ID"] for item in result.document["items"]] == [
        "multi-spot melt sample"
    ]
    observations = result.document["items"][0]["Extracted_Data"]["Composition"][
        "Composition_Observations"
    ]
    assert observations[0]["components"][0]["value_raw"] == "46.3"
    assert not any(
        issue.code == "unresolved_sample_alias"
        and issue.sample_id_raw == "multi-spot sample"
        for issue in result.issues
    )


def test_unqualified_cross_chunk_fact_stays_unresolved_for_two_qualified_samples():
    evidence = "The Al concentration was 46.3 at.% in the multi-spot sample"
    fact = _composition_fact("multi-spot sample", "multi-spot sample", evidence)
    fact.data["basis"] = "at%"
    fact.data["raw_expression"] = "Al = 46.3 at.%"
    fact.data["components"] = [
        {
            "name_raw": "Al",
            "value_kind": "scalar",
            "value_raw": "46.3",
            "unit_raw": "at.%",
            "data_nature": "reported",
        }
    ]

    result = materialize_candidate(
        [
            _anchor("multi-spot melt sample"),
            _anchor("multi-spot printed sample"),
        ],
        [
            _structure_fact(
                "multi-spot melt sample", "multi-spot melt sample had fine grains"
            ),
            _structure_fact(
                "multi-spot printed sample",
                "multi-spot printed sample had coarse grains",
            ),
            fact,
        ],
    )

    assert all(
        item["Extracted_Data"]["Composition"]["Composition_Observations"] == []
        for item in result.document["items"]
    )
    assert any(
        issue.code == "unresolved_sample_alias"
        and issue.sample_id_raw == "multi-spot sample"
        for issue in result.issues
    )


def test_qualified_alias_does_not_duplicate_fact_owned_by_specific_sample():
    evidence = "The Al concentration was 46.3 at.% in the multi-spot sample"
    composition = _composition_fact(
        "multi-spot sample", "multi-spot sample", evidence
    )
    composition.data["basis"] = "at%"
    composition.data["raw_expression"] = "Al = 46.3 at.%"
    composition.data["components"] = [
        {
            "name_raw": "Al",
            "value_kind": "scalar",
            "value_raw": "46.3",
            "unit_raw": "at.%",
            "data_nature": "reported",
        }
    ]
    generic_property = PropertyFact(
        sample_id_raw="multi-spot sample",
        data={
            "property_id_candidate": "temporary",
            "property_name_raw": "UTS",
            "value_raw": "556 ± 11",
            "unit_raw": "MPa",
            "test_method_raw": "tensile",
            "test_standard_raw": None,
            "test_condition_raw": "800 °C",
            "test_specimen_raw": None,
            "raw_note": None,
            "data_source": "text",
            "source_evidence": ["The UTS was measured as 556 ± 11 MPa"],
            "confidence": 0.97,
        },
        source_evidence=["The UTS was measured as 556 ± 11 MPa"],
        confidence=0.97,
    )
    specific_property = generic_property.model_copy(
        update={
            "sample_id_raw": "L70",
            "source_evidence": ["UTS: 556 ± 11 MPa"],
            "data": {
                **generic_property.data,
                "source_evidence": ["UTS: 556 ± 11 MPa"],
                "confidence": 0.95,
            },
            "confidence": 0.95,
        }
    )

    result = materialize_candidate(
        [
            _anchor("multi-spot melt sample"),
            _anchor("L70").model_copy(
                update={"material_name_raw": "multi-spot sample"}
            ),
            _anchor("L90").model_copy(
                update={"material_name_raw": "multi-spot sample"}
            ),
        ],
        [composition, generic_property, specific_property],
    )

    items = {item["Sample_ID"]: item for item in result.document["items"]}
    assert len(items["L70"]["Extracted_Data"]["Properties"]) == 1
    assert items["multi-spot melt sample"]["Extracted_Data"]["Properties"] == []
    observations = items["multi-spot melt sample"]["Extracted_Data"]["Composition"][
        "Composition_Observations"
    ]
    assert observations[0]["components"][0]["value_raw"] == "46.3"


def test_upstream_chart_quarantine_marker_becomes_materialization_issue():
    marker = (
        'quality_quarantine:{"code":"curve_series_quarantined",'
        '"series":["R1"],"reasons":["invalid"],"observed_min":-50,'
        '"observed_max":561,"data_csv":"figure_3_digitized.csv"}'
    )

    result = materialize_candidate(
        [_anchor("Alloy-A")],
        [_structure_fact("Alloy-A", "Alloy-A had fine grains")],
        source_text=marker,
    )

    issue = next(
        issue for issue in result.issues if issue.code == "curve_series_quarantined"
    )
    assert issue.actual["data_csv"] == "figure_3_digitized.csv"
    assert issue.actual["series"] == ["R1"]
