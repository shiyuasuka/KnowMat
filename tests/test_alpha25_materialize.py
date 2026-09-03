import pytest

from knowmat.alpha25.contracts import (
    CompositionFact,
    InventoryAnchor,
    ProcessingFact,
    PropertyFact,
    StructureFact,
)
from knowmat.alpha25.materialize import (
    _IdentityIndex,
    _build_identity_index,
    _deduplicate_tensile_precision_evidence,
    _fact_has_table_coordinate,
    _tensile_precision_complete_table,
    _expand_distinct_state_anchors,
    _recover_numeric_tensile_context_owners,
    _claim_quality_mode,
    _source_microanalysis_state_map,
    _dense_source_local_states,
    _state_composite_discriminator,
    _quarantine_unsupported_formula_identity_projections,
    _sanitize_property,
    _merge_condition_preserving_existing,
    _recover_structure_table_feature_coordinates,
    _recover_unowned_process_table_facts,
    _recover_processing_table_parameters,
    _deduplicate_process_stages,
    is_plausible_material_identity,
    materialize_candidate,
)


def test_dense_source_local_states_resolve_each_explicit_owner():
    source = (
        "As-built WAAM and as-built EBAM tensile specimens were tested in X and Y "
        "directions."
    )
    resolved = _dense_source_local_states(source, ("WAAM", "EBAM"))

    assert resolved["waam"][0] == "as-built"
    assert resolved["ebam"][0] == "as-built"
    assert resolved["waam"][1]
    assert resolved["ebam"][1]


def test_processing_table_rows_are_recovered_only_for_cited_family():
    source = """
| Delay Time | 3.75 seconds |
| --- | --- |
| Feed Rate | Infill: 200 mm/min (7.9 IPM)\\nPerimeter: 150 mm/min (5.9 IPM) |
| Hatch Spacing | 5 mm (0.2 in) |
Table 2: WAAM processing parameters.
"""
    stage = {
        "process_name_raw": "WAAM",
        "parameters_raw": [],
        "source_evidence": ["Table 2: WAAM processing parameters."],
    }

    params, audits = _recover_processing_table_parameters(stage, source_text=source)

    names = {row["parameter_name_raw"] for row in params}
    assert {"Delay Time", "Infill Feed Rate", "Perimeter Feed Rate", "Hatch Spacing"} <= names
    assert audits and audits[0]["reason"] == "candidate omitted source-literal processing-table rows"


def test_processing_table_rows_do_not_cross_bind_to_other_family():
    source = """
| Beam Current | 150 mA |
| --- | --- |
Table 3: EBAM processing parameters.
"""
    stage = {
        "process_name_raw": "WAAM",
        "parameters_raw": [],
        "source_evidence": ["Table 3: EBAM processing parameters."],
    }

    params, audits = _recover_processing_table_parameters(stage, source_text=source)

    assert params == []
    assert audits == []


@pytest.mark.parametrize(
    ("existing", "proposed", "expected"),
    [
        ("200 h", "200 h; 900 °C", "200 h\n\n900 °C"),
        ("200 h; 900 °C", "900 \\mathring{C}", "200 h; 900 °C"),
        ("", "900 °C", "900 °C"),
        ("200 h", "", "200 h"),
    ],
)
def test_condition_merge_preserves_source_local_value(
    existing: str, proposed: str, expected: str
):
    assert _merge_condition_preserving_existing(existing, proposed) == expected
from knowmat.alpha25.property_context import PropertyContextIndex


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


def test_sanitize_sidecar_coordinate_does_not_reappend_to_condition():
    row = {
        "property_name_raw": "Ultimate Tensile Strength",
        "value_raw": "1000",
        "data_source": "image_digitized",
        "test_specimen_raw": "X",
        "test_condition_raw": "tensile test",
        "source_evidence": ["data_csv: figure_1_digitized.csv"],
    }

    sanitized = _sanitize_property(row)

    assert sanitized is not None
    assert sanitized["test_specimen_raw"] == "X"
    assert sanitized["test_condition_raw"] == "tensile test"


def test_logical_table_coordinate_rebinds_existing_state_owner_without_changing_value():
    source = r"""
<table>
<tr><td rowspan="2"></td><td colspan="3">H230AM</td></tr>
<tr><td>HT</td><td>200 h</td><td>500 h</td></tr>
<tr><td>Tensile strength / MPa</td><td>220</td><td>204</td><td>200</td></tr>
</table>
"""
    evidence = [
        "Tensile strength / MPa | 220 | 204 | 200",
        '<tr><td rowspan="2"></td><td colspan="3">H230AM</td></tr>',
        "<tr><td>Tensile strength / MPa</td><td>220</td><td>204</td><td>200</td></tr>",
    ]
    fact = _raw_property(
        "H230AM", "Tensile strength", "220", evidence[0]
    ).model_copy(
        update={
            "source_evidence": evidence,
            "data": {
                **_raw_property("H230AM", "Tensile strength", "220", evidence[0]).data,
                "unit_raw": "MPa",
                "data_source": "table",
                "source_evidence": evidence,
            },
        }
    )
    anchors = [
        _anchor("H230AM"),
        _anchor("H230AM [heat treated]", state="heat treated"),
    ]

    result = materialize_candidate(anchors, [fact], source_text=source)

    properties = [
        prop
        for item in result.document["items"]
        for prop in item["Extracted_Data"]["Properties"]
    ]
    assert [(item["Sample_ID"], prop["value_raw"]) for item in result.document["items"] for prop in item["Extracted_Data"]["Properties"]] == [
        ("H230AM [heat treated]", "220")
    ]
    assert properties[0]["unit_raw"] == "MPa"
    assert any(issue.code == "property_table_coordinate_rebound" for issue in result.issues)


def test_logical_table_owner_variant_rebinds_to_existing_state_sibling():
    source = (
        "| Samples | Yield strength (MPa) | Elongation (%) |\n"
        "| --- | --- | --- |\n"
        "| AF-RT | 482 | 9 |\n"
        "| AF-200 °C | 402 | 11 |"
    )
    evidence = [
        "| Samples | Yield strength (MPa) | Elongation (%) |",
        "| AF-200 °C | 402 | 11 |",
    ]
    fact = _raw_property("AF", "Elongation", "11", evidence[1]).model_copy(
        update={
            "source_evidence": evidence,
            "data": {
                **_raw_property("AF", "Elongation", "11", evidence[1]).data,
                "unit_raw": "%",
                "test_condition_raw": "200 °C",
                "data_source": "table",
                "source_evidence": evidence,
            },
        }
    )
    anchors = [
        _anchor("AF"),
        _anchor("AF", state="as-built"),
        _anchor("AF", state="heat treated at 200 °C"),
    ]

    result = materialize_candidate(anchors, [fact], source_text=source)

    properties = [
        (
            item["Sample_ID"],
            prop["value_raw"],
            prop.get("test_condition_raw"),
        )
        for item in result.document["items"]
        for prop in item["Extracted_Data"]["Properties"]
    ]
    assert properties == [("AF [heat treated at 200 °C]", "11", "200 °C")]
    assert any(
        issue.code == "property_table_owner_variant_rebound"
        for issue in result.issues
    )


def test_compact_rt_table_owner_gets_source_backed_test_coordinate():
    source = (
        "| Samples | Yield strength (MPa) | Elongation (%) |\n"
        "| --- | --- | --- |\n"
        "| HT-RT | 595 ± 14 | 2 ± 1 |"
    )
    evidence = [
        "| Samples | Yield strength (MPa) | Elongation (%) |",
        "| HT-RT | 595 ± 14 | 2 ± 1 |",
    ]
    template = _raw_property("HT", "Yield strength", "595 ± 14", evidence[1])
    fact = template.model_copy(
        update={
            "source_evidence": evidence,
            "data": {
                **template.data,
                "unit_raw": "MPa",
                "test_condition_raw": "RT",
                "data_source": "table",
                "source_evidence": evidence,
            },
        }
    )

    result = materialize_candidate(
        [_anchor("HT", state="heat-treated")], [fact], source_text=source
    )

    rows = [
        (item["Sample_ID"], prop["value_raw"], prop.get("test_condition_raw"))
        for item in result.document["items"]
        for prop in item["Extracted_Data"]["Properties"]
    ]
    assert rows == [("HT-RT", "595 ± 14", "room temperature")]
    assert any(
        issue.code == "property_table_compact_test_owner_recovered"
        for issue in result.issues
    )


def _process_stage(
    sample: str,
    process_name: str,
    *,
    parameter_name: str = "Laser Power",
    value: str = "5000",
    unit: str = "W",
    condition: str | None = None,
) -> ProcessingFact:
    evidence = f"{process_name}: {parameter_name} {value} {unit}".strip()
    parameter = {
        "parameter_name_raw": parameter_name,
        "value_raw": value,
        "unit_raw": unit,
        "source_evidence": evidence,
    }
    if condition is not None:
        parameter["condition_label_raw"] = condition
    return ProcessingFact(
        sample_id_raw=sample,
        fact_type="process_stage",
        data={
            "candidate_stage_id": "temporary",
            "stage_index_candidate": 0,
            "process_name_raw": process_name,
            "process_code_candidate": None,
            "process_role_candidate": None,
            "parameters_raw": [parameter],
            "source_evidence": [evidence],
            "confidence": 0.95,
        },
        source_evidence=[evidence],
        confidence=0.95,
    )


def _coupled_power_stage(
    sample: str, process_name: str, *, condition: str | None = None
) -> ProcessingFact:
    fact = _process_stage(sample, process_name, condition=condition)
    fact.data["parameters_raw"].append(
        {
            "parameter_name_raw": "Wire Power",
            "value_raw": "300",
            "unit_raw": "W",
            "source_evidence": f"{process_name}: Wire Power 300 W",
        }
    )
    return fact


def test_unowned_process_table_fact_recovers_unique_caption_owner():
    source = (
        "Table 2: WAAM processing parameters.\n"
        "| Delay Time | 3.75 seconds |\n"
        "| Feed Rate | 200 mm/min |"
    )
    fact = _process_stage("not_reported", "WAAM", value="3.75", unit="seconds")
    fact = fact.model_copy(
        update={
            "source_evidence": [
                "Table 2: WAAM processing parameters.",
                "| Delay Time | 3.75 seconds |",
                "| Feed Rate | 200 mm/min |",
            ],
            "data": {
                **fact.data,
                "parameters_raw": [
                    {
                        "parameter_name_raw": "Delay Time",
                        "value_raw": "3.75",
                        "unit_raw": "seconds",
                    },
                ],
            },
        }
    )
    index = _build_identity_index([_anchor("WAAM"), _anchor("EBAM")], [fact])
    recovered, issues = _recover_unowned_process_table_facts(index, [fact])
    assert recovered[0].sample_id_raw == "WAAM"
    assert [issue.code for issue in issues] == ["process_table_owner_recovered"]


def test_unowned_process_table_fact_does_not_guess_multi_owner_caption():
    fact = _process_stage("not_reported", "WAAM", value="3.75", unit="seconds")
    fact = fact.model_copy(
        update={
            "source_evidence": [
                "Table 2: WAAM and EBAM processing parameters.",
                "| Delay Time | 3.75 seconds |",
            ],
            "data": {**fact.data, "parameters_raw": [{"parameter_name_raw": "Delay Time", "value_raw": "3.75", "unit_raw": "seconds"}]},
        }
    )
    index = _build_identity_index([_anchor("WAAM"), _anchor("EBAM")], [fact])
    recovered, issues = _recover_unowned_process_table_facts(index, [fact])
    assert recovered[0].sample_id_raw == "not_reported"
    assert issues == []


def test_overlapping_process_stage_chunks_merge_compatible_parameters():
    first = _process_stage("WAAM", "WAAM deposition", value="500", unit="W")
    second = _process_stage("WAAM", "WAAM build", value="500", unit="W")
    second.data["parameters_raw"].append(
        {
            "parameter_name_raw": "Travel Speed",
            "value_raw": "10",
            "unit_raw": "mm/s",
            "source_evidence": "WAAM: Travel Speed 10 mm/s",
        }
    )
    # Make the source spans overlap while retaining the richer second chunk.
    overlap_evidence = list(first.source_evidence) + [
        "WAAM: Travel Speed 10 mm/s"
    ]
    second = second.model_copy(
        update={
            "source_evidence": overlap_evidence,
            "data": {**second.data, "source_evidence": overlap_evidence},
        }
    )
    merged, issues = _deduplicate_process_stages(
        [first.data, second.data], sample_id="WAAM"
    )
    assert len(merged) == 1
    assert len(merged[0]["parameters_raw"]) == 2
    assert [issue.code for issue in issues] == ["process_stage_duplicate_merged"]


def _characterization(
    sample: str,
    method_raw: str,
    method_class: str,
    *,
    evidence: str | None = None,
    **extra: object,
) -> StructureFact:
    source = evidence or f"{method_raw} was used."
    return StructureFact(
        sample_id_raw=sample,
        fact_type="characterization",
        data={
            "characterization_id": "temporary",
            "method_raw": method_raw,
            "method_class": method_class,
            "source_evidence": [source],
            **extra,
        },
        source_evidence=[source],
        confidence=0.95,
    )


def _raw_property(
    sample: str,
    name: str,
    value: str,
    evidence: str,
    *,
    source: str = "text",
) -> PropertyFact:
    return PropertyFact(
        sample_id_raw=sample,
        fact_type="property",
        data={
            "property_id_candidate": "temporary",
            "property_name_raw": name,
            "value_raw": value,
            "unit_raw": "",
            "test_method_raw": "",
            "test_standard_raw": "",
            "test_condition_raw": "",
            "test_specimen_raw": "",
            "raw_note": "",
            "data_source": source,
            "source_evidence": [evidence],
            "confidence": 0.9,
        },
        source_evidence=[evidence],
        confidence=0.9,
    )


def test_numbered_table_columns_bind_to_one_material_state_without_items():
    source = (
        "Specific density measurements of different cuboids made from MAR-M247.\n"
        "| Density [g/cm3] | #1 | #2 | Average |\n"
        "| --- | --- | --- | --- |\n"
        "| As-sintered | 8.401 | 8.394 | 8.398 |\n"
        "| After HIP1 | 8.569 | 8.545 | 8.557 |"
    )
    base = InventoryAnchor(
        sample_id_raw="MAR M247",
        material_name_raw="MAR-M247",
        state_raw=None,
        role="Target",
        data_nature="Experimental",
        source_evidence=["MAR-M247 cuboids"],
        confidence=0.95,
    )
    as_sintered = base.model_copy(
        update={
            "sample_id_raw": "MAR M247",
            "state_raw": "as-sintered",
            "source_evidence": ["MAR-M247 as-sintered cuboids"],
        }
    )
    column_anchors = [_anchor("#1"), _anchor("#2")]
    facts = []
    for owner, value, state in (
        ("#1", "8.401", "As-sintered"),
        ("#2", "8.394", "As-sintered"),
        ("#1", "8.569", "After HIP1"),
        ("#2", "8.545", "After HIP1"),
    ):
        fact = _raw_property(owner, "Density", value, source, source="table")
        fact.data["material_state"] = state
        facts.append(fact)

    result = materialize_candidate(
        [base, as_sintered, *column_anchors], facts, source_text=source
    )
    sample_ids = [item["Sample_ID"] for item in result.document["items"]]
    assert all(not sample_id.lstrip().startswith("#") for sample_id in sample_ids)
    assert any("as-sintered" in sample_id.casefold() for sample_id in sample_ids)
    assert any("hip1" in sample_id.casefold() for sample_id in sample_ids)
    assert not any(issue.code == "table_column_owner_ambiguous" for issue in result.issues)
    assert sum(issue.code == "table_column_owner_reconciled" for issue in result.issues) == 4


def test_numbered_table_column_remains_when_source_declares_independent_sample():
    source = (
        "The #1 sample was machined separately from #2.\n"
        "| Density | #1 | #2 |\n"
        "| --- | --- | --- |\n"
        "| As-sintered | 8.40 | 8.41 |"
    )
    fact = _raw_property(
        "#1", "Density", "8.40", source, source="table"
    )
    fact.data["material_state"] = "As-sintered"
    result = materialize_candidate([_anchor("#1"), _anchor("#2")], [fact], source_text=source)
    assert any(item["Sample_ID"] == "#1" for item in result.document["items"])
    assert not any(issue.code == "table_column_label_not_material" for issue in result.issues)


def test_numbered_table_column_isolated_when_material_owner_is_not_unique():
    source = (
        "MAR-M247 and IN718 cuboids were measured.\n"
        "| Density | #1 | #2 |\n"
        "| --- | --- | --- |\n"
        "| After HIP1 | 8.40 | 8.41 |"
    )
    fact = _raw_property("#1", "Density", "8.40", source, source="table")
    fact.data["material_state"] = "After HIP1"
    anchors = [
        InventoryAnchor(
            sample_id_raw="MAR-M247",
            material_name_raw="MAR-M247",
            state_raw=None,
            role="Target",
            data_nature="Experimental",
            source_evidence=["MAR-M247 cuboids"],
            confidence=0.9,
        ),
        InventoryAnchor(
            sample_id_raw="IN718",
            material_name_raw="IN718",
            state_raw=None,
            role="Target",
            data_nature="Experimental",
            source_evidence=["IN718 cuboids"],
            confidence=0.9,
        ),
        _anchor("#1"),
    ]
    result = materialize_candidate(anchors, [fact], source_text=source)
    assert not any(item["Sample_ID"] == "#1" for item in result.document["items"])
    issue = next(
        issue for issue in result.issues if issue.code == "table_column_owner_ambiguous"
    )
    assert issue.actual["fact"]["sample_id_raw"] == "#1"


def test_numbered_table_columns_ignore_short_process_alias_with_material_descriptor():
    """A process code must not compete with the material owner of a table."""

    source = (
        "Specific density measurements of MAR-M247 cuboids made by Binder Jetting.\n"
        "| Density [g/cm3] | #1 | #2 | Average |\n"
        "| --- | --- | --- | --- |\n"
        "| As-sintered | 8.401 | 8.394 | 8.398 |"
    )
    fact = _raw_property(
        "#1", "Density", "8.401", source, source="table"
    )
    fact.data["material_state"] = "As-sintered"
    anchors = [
        InventoryAnchor(
            sample_id_raw="MAR-M247",
            material_name_raw="MAR-M247 superalloy",
            state_raw=None,
            role="Target",
            data_nature="Experimental",
            source_evidence=["MAR-M247 cuboids"],
            confidence=0.9,
        ),
        InventoryAnchor(
            sample_id_raw="BJ",
            material_name_raw="MAR-M247",
            state_raw="HIP and HT2 conditions",
            role="Reference",
            data_nature="Literature_Experimental",
            source_evidence=["average tensile properties ... in the BJ specimens"],
            confidence=0.95,
        ),
        _anchor("#1"),
    ]

    result = materialize_candidate(anchors, [fact], source_text=source)

    assert not any(item["Sample_ID"] == "#1" for item in result.document["items"])
    assert any("MAR-M247" in item["Sample_ID"] for item in result.document["items"])
    assert not any(
        issue.code == "table_column_owner_ambiguous" for issue in result.issues
    )
    assert any(
        issue.code == "table_column_owner_reconciled" for issue in result.issues
    )


def test_unoriented_tensile_average_isolated_when_directional_context_exists():
    source = (
        "No significant anisotropy was observed between horizontally and vertically "
        "built specimens. Independent of build direction, the average yield strength "
        "after HIP2 + HT2 was 1000 MPa."
    )
    fact = _raw_property(
        "MAR M247",
        "yield strength",
        "1000",
        "Independent of build direction, the average yield strength after HIP2 + HT2 was 1000 MPa.",
    )
    fact.data.update(
        {
            "unit_raw": "MPa",
            "material_state": "HIP2 + HT2",
            "data_source": "text",
        }
    )
    result = materialize_candidate([_anchor("MAR M247")], [fact], source_text=source)
    assert not any(
        str(prop.get("Property_Name_Raw") or prop.get("property_name_raw") or "").casefold()
        == "yield strength"
        for item in result.document["items"]
        for prop in item["Extracted_Data"]["Properties"]
    )
    assert any(
        issue.code == "tensile_average_without_orientation" for issue in result.issues
    )


def test_generic_table_value_is_reassigned_to_unique_owner_column():
    table = (
        "| Property | Alloy-A | Alloy-B |\n"
        "| Hardness (GPa) | 2.1 | 3.4 |"
    )
    result = materialize_candidate(
        [_anchor("Alloy-A"), _anchor("Alloy-B")],
        [_raw_property("Alloy-A", "Hardness (GPa)", "3.4", table, source="table")],
        source_text=table,
    )

    items = result.document["items"]
    assert len(items) == 1
    assert items[0]["Sample_ID"] == "Alloy-B"
    property_row = items[0]["Extracted_Data"]["Properties"][0]
    assert property_row["value_raw"] == "3.4"
    assert any(
        issue.code == "source_table_generic_owner_recovered"
        for issue in result.issues
    )


def test_unique_literal_evidence_owner_overrides_conflicting_short_owner():
    evidence = (
        "The yield strength, ultimate tensile strength, uniform elongation and "
        "fracture elongation of the N_{1}-LAG material are 775 MPa, 945 MPa, 38% "
        "and 70%, respectively."
    )
    fact = _tensile_property(
        "N1", evidence=evidence, value="775", name="yield strength"
    )

    result = materialize_candidate([_anchor("N1"), _anchor("N1-LAG")], [fact])

    items = {
        row["Sample_ID"]: row
        for row in result.document["items"]
    }
    assert "N1" not in items
    assert len(items["N1-LAG"]["Extracted_Data"]["Properties"]) == 1
    issue = next(
        row
        for row in result.issues
        if row.code == "fact_owner_evidence_reconciled"
    )
    assert issue.actual["before_owner"] == "N1"
    assert issue.actual["after_owner"] == "N1-LAG"
    assert issue.actual["facts"][0]["sample_id_raw"] == "N1"


def test_multiple_literal_evidence_owners_do_not_override_declared_owner():
    evidence = (
        "N1-LAG compared with N1-HOMO showed different yield-strength values; "
        "the reported value was 775 MPa and the comparison is reported for context."
    )
    fact = _tensile_property(
        "N1", evidence=evidence, value="775", name="yield strength"
    )

    result = materialize_candidate(
        [_anchor("N1"), _anchor("N1-LAG"), _anchor("N1-HOMO")], [fact]
    )

    items = {
        row["Sample_ID"]: row
        for row in result.document["items"]
    }
    assert len(items["N1"]["Extracted_Data"]["Properties"]) == 1
    assert "N1-LAG" not in items
    assert "N1-HOMO" not in items
    assert not any(row.code == "fact_owner_evidence_reconciled" for row in result.issues)
    issue = next(
        row
        for row in result.issues
        if row.code == "fact_owner_evidence_ambiguous"
    )
    assert issue.actual["declared_owner"] == "N1"
    assert set(issue.actual["evidence_owner_candidates"]) == {"N1-LAG", "N1-HOMO"}


def test_tensile_comparator_owner_does_not_override_declared_result_owner():
    evidence = (
        "Upon post-annealing at 600 °C for 8 h, σ0.2 and σu reach "
        "1723 ± 37 MPa and 2153 ± 24 MPa, approximately 24% higher "
        "than the values for the as-built samples, respectively."
    )
    fact = _tensile_property(
        "as-annealed",
        condition="RT",
        evidence=evidence,
        value="2153 ± 24",
    )
    anchors = [
        _material_anchor("AlCoCrFeNi2.1", material="AlCoCrFeNi2.1"),
        _material_anchor(
            "as-built", material="AlCoCrFeNi2.1", state="as-built"
        ),
        _material_anchor(
            "as-annealed", material="AlCoCrFeNi2.1", state="as-annealed"
        ),
    ]

    result = materialize_candidate(anchors, [fact], source_text=evidence)

    properties = [
        (item["Sample_ID"], prop["value_raw"])
        for item in result.document["items"]
        for prop in item["Extracted_Data"]["Properties"]
    ]
    assert properties == [("as-annealed", "2153 ± 24")]
    assert not any(
        row.code == "fact_owner_evidence_reconciled" for row in result.issues
    )


def test_unique_literal_evidence_owner_reassigns_direct_structure_observation():
    evidence = "N1-LAG contained fine carbides after processing."
    fact = _structure_fact("N1", evidence)
    result = materialize_candidate([_anchor("N1"), _anchor("N1-LAG")], [fact])

    items = {row["Sample_ID"]: row for row in result.document["items"]}
    assert "N1" not in items
    assert len(items["N1-LAG"]["Extracted_Data"]["Structure"]["Structure_Observations"]) == 1
    issue = next(
        row
        for row in result.issues
        if row.code == "promotion_explicit_evidence_owner_reassigned"
    )
    assert issue.actual["binding_kind"] == "structure_entity_observation"
    assert issue.actual["before_owner"] == "N1"
    assert issue.actual["after_owner"] == "N1-LAG"


def test_unique_literal_evidence_owner_reassigns_direct_characterization_method():
    evidence = "EBSD was performed on N1-LAG to measure the texture."
    fact = _characterization("N1", "EBSD", "EBSD", evidence=evidence)
    result = materialize_candidate([_anchor("N1"), _anchor("N1-LAG")], [fact])

    items = {row["Sample_ID"]: row for row in result.document["items"]}
    assert "N1" not in items
    assert items["N1-LAG"]["Extracted_Data"]["Structure"]["Characterization"]
    issue = next(
        row
        for row in result.issues
        if row.code == "promotion_explicit_evidence_owner_reassigned"
    )
    assert issue.actual["binding_kind"] == "characterization_method_direct_assertion"


def test_direct_owner_reassignment_rejects_comparison_and_table_spans():
    comparison = "N1-LAG had finer carbides than the reference sample."
    comparison_fact = _structure_fact("N1", comparison)
    table = "| Sample | Structure |\n| N1-LAG | fine carbides |"
    table_fact = _structure_fact("N1", table)
    anchors = [_anchor("N1"), _anchor("N1-LAG")]

    comparison_result = materialize_candidate(anchors, [comparison_fact])
    assert not any(
        issue.code == "promotion_explicit_evidence_owner_reassigned"
        for issue in comparison_result.issues
    )

    table_result = materialize_candidate(anchors, [table_fact], source_text=table)
    assert not any(
        issue.code == "promotion_explicit_evidence_owner_reassigned"
        for issue in table_result.issues
    )


def test_characterization_prefers_material_over_process_context_alias():
    evidence = (
        "Formation of twins was characterized by SEM for the Inconel 625 alloy "
        "processed by Binder Jetting after sintering."
    )
    fact = _characterization(
        "Binder Jetting", "SEM", "SEM", evidence=evidence
    )
    result = materialize_candidate(
        [_anchor("Binder Jetting"), _anchor("Inconel 625")], [fact]
    )

    assert [row["Sample_ID"] for row in result.document["items"]] == [
        "Inconel 625"
    ]
    issue = next(
        row
        for row in result.issues
        if row.code == "promotion_explicit_evidence_owner_reassigned"
    )
    assert issue.actual["before_owner"] == "Binder Jetting"
    assert issue.actual["after_owner"] == "Inconel 625"
    assert issue.evidence[0]["process_context_preference"] is True


def test_shared_owner_prose_without_literal_owner_is_quarantined():
    evidence = "The samples exhibited high hardness after processing."
    result = materialize_candidate(
        [_anchor("Alloy-A"), _anchor("Alloy-B")],
        [
            _raw_property("Alloy-A", "hardness", "high", evidence),
            _raw_property("Alloy-B", "hardness", "high", evidence),
        ],
        source_text=evidence,
    )

    assert result.document["items"] == []
    assert sum(
        issue.code == "shared_owner_projection_quarantined"
        for issue in result.issues
    ) == 2


def test_explicit_multi_owner_prose_is_preserved():
    evidence = "Alloy-A and Alloy-B both exhibited high hardness after processing."
    result = materialize_candidate(
        [_anchor("Alloy-A"), _anchor("Alloy-B")],
        [
            _raw_property("Alloy-A", "hardness", "high", evidence),
            _raw_property("Alloy-B", "hardness", "high", evidence),
        ],
        source_text=evidence,
    )

    assert {item["Sample_ID"] for item in result.document["items"]} == {
        "Alloy-A",
        "Alloy-B",
    }
    assert not any(
        issue.code == "shared_owner_projection_quarantined"
        for issue in result.issues
    )


def test_latex_owner_variant_is_treated_as_explicit_owner_evidence():
    evidence = (
        "CoCrNi(Al_{0}.6TiFe)0.4 and CoCrNi(Al_{0}.6TiFe)0.5 both "
        "exhibited high hardness after processing."
    )
    result = materialize_candidate(
        [_anchor("CoCrNi(Al0.6TiFe)0.4"), _anchor("CoCrNi(Al0.6TiFe)0.5")],
        [
            _raw_property("CoCrNi(Al0.6TiFe)0.4", "hardness", "high", evidence),
            _raw_property("CoCrNi(Al0.6TiFe)0.5", "hardness", "high", evidence),
        ],
    )

    assert {
        item["Sample_ID"] for item in result.document["items"]
    } == {"CoCrNi(Al0.6TiFe)0.4", "CoCrNi(Al0.6TiFe)0.5"}
    assert not any(
        issue.code == "shared_owner_projection_quarantined"
        for issue in result.issues
    )


def test_near_duplicate_shared_owner_prose_is_quarantined():
    left = "The samples exhibited high hardness after processing."
    right = "The samples exhibited high hardness after processing and testing."
    result = materialize_candidate(
        [_anchor("Alloy-A"), _anchor("Alloy-B")],
        [
            _raw_property("Alloy-A", "hardness", "high", left),
            _raw_property("Alloy-B", "hardness", "high", right),
        ],
    )

    assert result.document["items"] == []
    near_duplicate_issues = [
        issue
        for issue in result.issues
        if issue.code == "shared_owner_projection_quarantined"
        and issue.evidence.get("near_duplicate_evidence") is True
    ]
    assert len(near_duplicate_issues) == 2


def test_precision_first_owner_dedup_quarantines_same_property_fanout(monkeypatch):
    """Precision profile isolates identical cross-owner comparison copies."""

    monkeypatch.setenv("KNOWMAT2_ALPHA25_PRECISION_FIRST_OWNER_DEDUP_V207", "1")
    evidence = "Alloy-A had lower hardness than Alloy-B (500 MPa)."
    result = materialize_candidate(
        [_anchor("Alloy-A"), _anchor("Alloy-B")],
        [
            _raw_property("Alloy-A", "hardness", "500", evidence),
            _raw_property("Alloy-B", "hardness", "500", evidence),
        ],
        source_text=evidence,
    )

    assert result.document["items"] == []
    assert sum(
        issue.code == "precision_first_owner_projection_quarantined"
        for issue in result.issues
    ) == 2


def test_semantic_generic_owner_projection_is_quarantined_across_paraphrased_chunks():
    """Paraphrased generic chunk context must not become two owner claims."""

    left = "The samples exhibited a bimodal grain structure after processing."
    right = "Specimens showed a bimodal grain structure following processing and testing."
    result = materialize_candidate(
        [_anchor("Alloy-A"), _anchor("Alloy-B")],
        [_structure_fact("Alloy-A", left), _structure_fact("Alloy-B", right)],
    )

    assert result.document["items"] == []
    assert sum(
        issue.code == "shared_owner_semantic_projection_quarantined"
        for issue in result.issues
    ) == 2


def test_singleton_generic_qualitative_structure_owner_is_quarantined():
    """One routed owner is not enough when the source assertion is generic."""

    evidence = "The samples exhibited a bimodal grain structure after processing."
    result = materialize_candidate(
        [_anchor("Alloy-A"), _anchor("Alloy-B")],
        [_structure_fact("Alloy-A", evidence)],
        source_text=evidence,
    )

    assert result.document["items"] == []
    issue = next(
        row
        for row in result.issues
        if row.code == "qualitative_owner_binding_unresolved_quarantined"
    )
    assert issue.actual["reason"] == "owner_absent_from_qualitative_assertion"
    assert issue.actual["fact"]["sample_id_raw"] == "Alloy-A"


def test_singleton_owner_named_in_qualitative_structure_evidence_is_retained():
    evidence = "Alloy-A exhibited a bimodal grain structure after processing."
    result = materialize_candidate(
        [_anchor("Alloy-A"), _anchor("Alloy-B")],
        [_structure_fact("Alloy-A", evidence)],
        source_text=evidence,
    )

    assert len(result.document["items"]) == 1
    assert result.document["items"][0]["Sample_ID"] == "Alloy-A"
    assert not any(
        row.code == "qualitative_owner_binding_unresolved_quarantined"
        for row in result.issues
    )


def test_unique_owner_in_same_source_paragraph_recovers_omitted_subject():
    """A chunk predicate may omit its subject when the paragraph has one owner."""

    source = (
        "Alloy-A specimens were examined after processing. "
        "The samples exhibited carbides with a bimodal grain structure."
    )
    fact = _structure_fact("Alloy-A", "The samples exhibited carbides with a bimodal grain structure.")
    result = materialize_candidate(
        [_anchor("Alloy-A"), _anchor("Alloy-B")], [fact], source_text=source
    )

    assert [item["Sample_ID"] for item in result.document["items"]] == ["Alloy-A"]
    assert any(
        row.code == "qualitative_owner_binding_source_context_recovered"
        for row in result.issues
    )
    assert not any(
        row.code == "qualitative_owner_binding_unresolved_quarantined"
        for row in result.issues
    )


def test_one_off_formula_ocr_owner_redirects_to_composition_supported_owner():
    source = (
        "The Al92Ti2Fe2Co2Ni2 alloy was fabricated by LPBF. "
        "Al92Ti2Fe2Co2Ni2 was then tested in compression. "
        "A custom-made Al₉Ti₂Fe₂Co₂Ni₂ alloy was fabricated by LPBF."
    )
    canonical = _anchor("Al92Ti2Fe2Co2Ni2")
    candidate = _anchor("Al₉Ti₂Fe₂Co₂Ni₂", state="LPBF")
    composition = _composition_fact(
        "Al92Ti2Fe2Co2Ni2",
        "Al92Ti2Fe2Co2Ni2",
        "Al92Ti2Fe2Co2Ni2 nominal composition",
    )

    filtered, redirects, issues = _quarantine_unsupported_formula_identity_projections(
        [canonical, candidate],
        [composition],
        source_text=source,
    )

    assert [row.sample_id_raw for row in filtered] == ["Al92Ti2Fe2Co2Ni2"]
    assert redirects == {"Al₉Ti₂Fe₂Co₂Ni₂": "Al92Ti2Fe2Co2Ni2"}
    assert [issue.code for issue in issues] == [
        "unsupported_material_identity_projection_quarantined"
    ]
    assert issues[0].actual["candidate_anchor"]["sample_id_raw"] == (
        "Al₉Ti₂Fe₂Co₂Ni₂"
    )


def test_formula_identity_gate_collapses_duplicate_canonical_presentations():
    """Repeated canonical labels from separate chunks must not create ambiguity."""

    source = (
        "Al92Ti2Fe2Co2Ni2 was fabricated by LPBF. "
        "Al92Ti2Fe2Co2Ni2 was tested in compression. "
        "A custom-made Al₉Ti₂Fe₂Co₂Ni₂ alloy was fabricated by LPBF."
    )
    canonical = _anchor("Al92Ti2Fe2Co2Ni2")
    canonical_with_basis = canonical.model_copy(
        update={"sample_id_raw": "Al₉₂Ti₂Fe₂Co₂Ni₂ (at.%)"}
    )
    candidate = _anchor("Al₉Ti₂Fe₂Co₂Ni₂", state="LPBF")
    composition = _composition_fact(
        "Al92Ti2Fe2Co2Ni2",
        "Al92Ti2Fe2Co2Ni2",
        "Al92Ti2Fe2Co2Ni2 nominal composition",
    )

    filtered, redirects, issues = _quarantine_unsupported_formula_identity_projections(
        [canonical, canonical_with_basis, candidate],
        [composition],
        source_text=source,
    )

    assert [row.sample_id_raw for row in filtered] == [
        "Al92Ti2Fe2Co2Ni2",
        "Al₉₂Ti₂Fe₂Co₂Ni₂ (at.%)",
    ]
    assert redirects == {"Al₉Ti₂Fe₂Co₂Ni₂": "Al92Ti2Fe2Co2Ni2"}
    assert [issue.code for issue in issues] == [
        "unsupported_material_identity_projection_quarantined"
    ]


def test_formula_identity_redirect_routes_candidate_facts_to_canonical_item():
    source = (
        "The Al92Ti2Fe2Co2Ni2 alloy was fabricated by LPBF. "
        "Al92Ti2Fe2Co2Ni2 was then tested in compression. "
        "A custom-made Al₉Ti₂Fe₂Co₂Ni₂ alloy was fabricated by LPBF."
    )
    composition = _composition_fact(
        "Al92Ti2Fe2Co2Ni2",
        "Al92Ti2Fe2Co2Ni2",
        "Al92Ti2Fe2Co2Ni2 nominal composition",
    )
    result = materialize_candidate(
        [_anchor("Al92Ti2Fe2Co2Ni2"), _anchor("Al₉Ti₂Fe₂Co₂Ni₂", state="LPBF")],
        [composition, _raw_property(
            "Al₉Ti₂Fe₂Co₂Ni₂", "compressive strength", ">800",
            "A custom-made Al₉Ti₂Fe₂Co₂Ni₂ alloy was fabricated by LPBF.",
        )],
        source_text=source,
    )

    assert [item["Sample_ID"] for item in result.document["items"]] == [
        "Al92Ti2Fe2Co2Ni2"
    ]
    assert result.document["items"][0]["Extracted_Data"]["Properties"][0][
        "value_raw"
    ] == ">800"
    assert any(
        issue.code == "unsupported_material_identity_projection_quarantined"
        for issue in result.issues
    )


def test_formula_identity_gate_preserves_distinct_or_table_backed_candidate():
    source = (
        "Al92Ti2Fe2Co2Ni2 and Al90Ti2Fe4Co2Ni2 are distinct alloys. "
        "| Sample | Composition |\n| Al90Ti2Fe4Co2Ni2 | nominal |"
    )
    canonical = _anchor("Al92Ti2Fe2Co2Ni2")
    distinct = _anchor("Al90Ti2Fe4Co2Ni2")
    table_backed = distinct.model_copy(
        update={"sample_id_raw": "Al90Ti2Fe4Co2Ni2", "source_evidence": [
            "| Sample | Composition |",
            "| Al90Ti2Fe4Co2Ni2 | nominal |",
        ]}
    )
    composition = _composition_fact(
        "Al92Ti2Fe2Co2Ni2",
        "Al92Ti2Fe2Co2Ni2",
        "Al92Ti2Fe2Co2Ni2 nominal composition",
    )

    filtered, redirects, issues = _quarantine_unsupported_formula_identity_projections(
        [canonical, distinct, table_backed],
        [composition],
        source_text=source,
    )

    assert len(filtered) == 3
    assert redirects == {}
    assert issues == []


def test_characterization_presentation_aliases_are_merged_with_audit():
    result = materialize_candidate(
        [_anchor("A")],
        [
            _characterization("A", "TEM", "TEM", evidence="TEM image A."),
            _characterization(
                "A",
                "Transmission Electron Microscopy (TEM)",
                "TEM",
                evidence="Transmission electron microscopy image B.",
            ),
        ],
    )

    rows = result.document["items"][0]["Extracted_Data"]["Structure"][
        "Characterization"
    ]
    assert len(rows) == 1
    assert rows[0]["method_raw"] == "Transmission Electron Microscopy (TEM)"
    assert rows[0]["source_evidence"] == [
        "Transmission electron microscopy image B.",
        "TEM image A.",
    ]
    issue = next(
        row
        for row in result.issues
        if row.code == "characterization_method_alias_merged"
    )
    assert issue.expected["technique_family"] == "tem"
    assert issue.actual["removed_alias"]["method_raw"] == "TEM"
    assert issue.actual["survivor_after_merge"] == rows[0] | {
        "characterization_id": "temporary"
    }


def test_bare_characterization_alias_is_not_absorbed_by_detailed_mode():
    result = materialize_candidate(
        [_anchor("A")],
        [
            _characterization("A", "SEM", "SEM", evidence="SEM overview."),
            _characterization(
                "A",
                "SEM with backscattered detector",
                "SEM",
                evidence="BSE detail.",
            ),
        ],
    )

    rows = result.document["items"][0]["Extracted_Data"]["Structure"][
        "Characterization"
    ]
    assert [row["method_raw"] for row in rows] == [
        "SEM",
        "SEM with backscattered detector",
    ]
    assert not any(
        row.code == "characterization_method_alias_merged" for row in result.issues
    )


def test_figure_only_characterization_is_quarantined_but_instrument_is_kept():
    result = materialize_candidate(
        [_anchor("A")],
        [
            _characterization(
                "A",
                "TEM",
                "TEM",
                evidence="Figure 1 shows TEM results of A.",
            ),
            _characterization(
                "A",
                "TEM with FEI Talos device",
                "TEM",
                evidence="TEM instrument FEI Talos device was used for A.",
            ),
        ],
    )

    rows = result.document["items"][0]["Extracted_Data"]["Structure"][
        "Characterization"
    ]
    assert [row["method_raw"] for row in rows] == ["TEM with FEI Talos device"]
    assert any(
        issue.code == "characterization_figure_observation_quarantined"
        for issue in result.issues
    )


def test_explicit_image_acquisition_is_kept_even_with_result_language():
    evidence = (
        "Atomic-resolution HAADF-STEM images were taken on multiple faults; "
        "the resulting images show the ordered structure."
    )
    fact = _characterization(
        "A",
        "HAADF-STEM imaging",
        "STEM",
        evidence=evidence,
    )

    result = materialize_candidate([_anchor("A")], [fact])

    rows = result.document["items"][0]["Extracted_Data"]["Structure"][
        "Characterization"
    ]
    assert [row["method_raw"] for row in rows] == ["HAADF-STEM imaging"]
    assert not any(
        issue.code == "characterization_figure_observation_quarantined"
        for issue in result.issues
    )


def test_characterization_alias_with_generic_provider_class_is_not_merged():
    result = materialize_candidate(
        [_anchor("A")],
        [
            _characterization("A", "SEM", "microscopy"),
            _characterization(
                "A", "Scanning Electron Microscopy (SEM)", "SEM"
            ),
        ],
    )

    rows = result.document["items"][0]["Extracted_Data"]["Structure"][
        "Characterization"
    ]
    assert len(rows) == 2
    assert not any(
        row.code == "characterization_method_alias_merged" for row in result.issues
    )


def test_bare_characterization_alias_is_not_merged_with_two_detailed_modes():
    result = materialize_candidate(
        [_anchor("A")],
        [
            _characterization("A", "SEM", "SEM"),
            _characterization("A", "SEM with backscattered detector", "SEM"),
            _characterization("A", "SEM with secondary electron detector", "SEM"),
        ],
    )

    rows = result.document["items"][0]["Extracted_Data"]["Structure"][
        "Characterization"
    ]
    assert len(rows) == 3
    assert not any(
        row.code == "characterization_method_alias_merged" for row in result.issues
    )


def test_characterization_aliases_with_different_states_are_not_merged():
    result = materialize_candidate(
        [_anchor("A")],
        [
            _characterization("A", "EBSD", "EBSD", material_state="as-built"),
            _characterization(
                "A",
                "Electron Backscatter Diffraction (EBSD)",
                "EBSD",
                material_state="aged",
            ),
        ],
    )

    rows = result.document["items"][0]["Extracted_Data"]["Structure"][
        "Characterization"
    ]
    assert len(rows) == 2
    assert not any(
        row.code == "characterization_method_alias_merged" for row in result.issues
    )


def test_unique_process_environment_is_bound_only_within_same_process_family():
    source = (
        "The walls were produced by LHW-DED. The printing of the walls was "
        "performed in an inert argon atmosphere. The walls were subsequently "
        "aged at 700 °C for 4 h."
    )
    result = materialize_candidate(
        [_anchor("Wall 1")],
        [
            _coupled_power_stage("Wall 1", "LHW-DED deposition"),
            _process_stage(
                "Wall 1",
                "aging",
                parameter_name="temperature",
                value="700",
                unit="°C",
            ),
        ],
        source_text=source,
    )

    stages = result.document["items"][0]["Extracted_Data"]["Processing"][
        "Process_Route"
    ]["candidate_stages"]
    deposition = next(row for row in stages if row["process_name_raw"] == "LHW-DED deposition")
    aging = next(row for row in stages if row["process_name_raw"] == "aging")
    assert {
        row["condition_label_raw"] for row in deposition["parameters_raw"]
    } == {"LHW-DED deposition in inert argon atmosphere"}
    assert "condition_label_raw" not in aging["parameters_raw"][0]
    issue = next(
        row for row in result.issues if row.code == "process_environment_context_recovered"
    )
    assert issue.actual["process_family"] == "additive_manufacturing"
    assert issue.actual["environment_key"] == "argon"
    assert issue.expected["cross_family_broadcast"] is False


def test_process_environment_is_not_inferred_when_same_family_has_two_atmospheres():
    source = (
        "One set was printed under argon atmosphere. A second set was printed "
        "under vacuum."
    )
    result = materialize_candidate(
        [_anchor("A")],
        [_coupled_power_stage("A", "laser printing")],
        source_text=source,
    )

    parameter = result.document["items"][0]["Extracted_Data"]["Processing"][
        "Process_Route"
    ]["candidate_stages"][0]["parameters_raw"][0]
    assert "condition_label_raw" not in parameter
    assert not any(
        row.code == "process_environment_context_recovered" for row in result.issues
    )


def test_process_environment_preserves_existing_event_local_atmosphere():
    source = "The samples were printed under an argon atmosphere."
    result = materialize_candidate(
        [_anchor("A")],
        [_coupled_power_stage("A", "laser printing", condition="local vacuum")],
        source_text=source,
    )

    parameter = result.document["items"][0]["Extracted_Data"]["Processing"][
        "Process_Route"
    ]["candidate_stages"][0]["parameters_raw"][0]
    assert parameter["condition_label_raw"] == "local vacuum"
    assert not any(
        row.code == "process_environment_context_recovered" for row in result.issues
    )


def test_process_environment_is_not_broadcast_over_single_energy_stage():
    source = "All printing processes were carried out in an argon atmosphere."
    result = materialize_candidate(
        [_anchor("A")],
        [_process_stage("A", "LPBF")],
        source_text=source,
    )

    parameter = result.document["items"][0]["Extracted_Data"]["Processing"][
        "Process_Route"
    ]["candidate_stages"][0]["parameters_raw"][0]
    assert "condition_label_raw" not in parameter
    assert not any(
        row.code == "process_environment_context_recovered" for row in result.issues
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
    value: str = "900",
    name: str = "ultimate tensile strength",
    unit: str = "MPa",
    data_source: str = "text",
) -> PropertyFact:
    return PropertyFact(
        sample_id_raw=sample,
        data={
            "property_id_candidate": "temp",
            "property_name_raw": name,
            "value_raw": value,
            "unit_raw": unit,
            "test_method_raw": "tensile tests",
            "test_standard_raw": None,
            "test_condition_raw": condition,
            "test_specimen_raw": None,
            "raw_note": None,
            "data_source": data_source,
            "source_evidence": [evidence],
            "confidence": 0.9,
        },
        source_evidence=[evidence],
        confidence=0.9,
    )


def _literature_state_anchor(
    sample: str, state: str, evidence: str
) -> InventoryAnchor:
    return InventoryAnchor(
        sample_id_raw=sample,
        material_name_raw="Inconel 625",
        state_raw=state,
        role="Reference",
        data_nature="Literature_Experimental",
        source_evidence=[evidence],
        confidence=0.9,
    )


def test_unique_reference_anchor_assertion_recovers_same_author_state_owner():
    lpbf_assertion = (
        "The reported UTS, YS, and elongation values averaged ~0.90 GPa, "
        "~0.37 GPa, and 58%, respectively, for LPBF printed specimens that "
        "had undergone HIPing at 0.1 GPa and 1120 °C for 4 h."
    )
    epbf_assertion = (
        "EPBF printed specimens subjected to the same HIPing schedule were "
        "reported to have a UTS of 0.33 GPa, YS of 0.77 GPa, and elongation "
        "of 69% by the same study."
    )
    anchors = [
        _anchor("LPBF"),
        _literature_state_anchor(
            "Amato et al.",
            "LPBF HIPed at 0.1 GPa and 1120 °C for 4 h",
            lpbf_assertion,
        ),
        _literature_state_anchor(
            "Amato et al.",
            "EPBF HIPed at 0.1 GPa and 1120 °C for 4 h",
            epbf_assertion,
        ),
    ]
    fact = _tensile_property(
        "Amato et al.",
        name="UTS",
        value="~0.90",
        unit="GPa",
        evidence=lpbf_assertion,
    )

    result = materialize_candidate(anchors, [fact], source_text=lpbf_assertion)

    assert len(result.document["items"]) == 1
    item = result.document["items"][0]
    assert item["Sample_ID"].startswith("Inconel 625")
    assert item["Role"] == "Reference"
    assert item["Data_Nature"] == "Literature_Experimental"
    assert "LPBF HIPed at 0.1 GPa and 1120 °C for 4 h" in item["Sample_ID"]
    assert item["Extracted_Data"]["Properties"][0]["value_raw"] == "~0.90"
    issue = next(
        row
        for row in result.issues
        if row.code == "reference_assertion_state_owner_reassigned"
    )
    assert issue.actual["declared_owner"] == "Amato et al."
    assert issue.actual["selected_role"] == "Reference"
    assert issue.actual["owner_invented"] is False
    assert len(issue.actual["candidate_owners"]) == 2
    assert not any(
        row.code == "numeric_tensile_owner_recovered"
        for row in result.issues
    )


def test_repeated_reference_assertion_across_states_fails_closed():
    assertion = (
        "The reported UTS was 0.90 GPa for printed specimens after the "
        "shared HIP treatment at 1120 °C for 4 h."
    )
    anchors = [
        _anchor("LPBF"),
        _literature_state_anchor("Amato et al.", "LPBF HIPed", assertion),
        _literature_state_anchor("Amato et al.", "EPBF HIPed", assertion),
    ]
    fact = _tensile_property(
        "Amato et al.", value="0.90", unit="GPa", evidence=assertion
    )

    result = materialize_candidate(anchors, [fact], source_text=assertion)

    assert result.document["items"] == []
    assert any(
        row.code == "reference_assertion_state_owner_ambiguous"
        for row in result.issues
    )
    assert not any(
        row.code == "reference_assertion_state_owner_reassigned"
        for row in result.issues
    )


def test_ambiguous_reference_owner_cannot_route_to_target_by_process_word():
    fact_evidence = (
        "LPBF specimens had an ultimate tensile strength of 0.90 GPa after "
        "the reported treatment."
    )
    anchors = [
        _anchor("LPBF"),
        _literature_state_anchor(
            "Amato et al.",
            "LPBF HIPed",
            "Amato et al. defined one LPBF literature state for comparison.",
        ),
        _literature_state_anchor(
            "Amato et al.",
            "EPBF HIPed",
            "Amato et al. defined one EPBF literature state for comparison.",
        ),
    ]
    fact = _tensile_property(
        "Amato et al.", value="0.90", unit="GPa", evidence=fact_evidence
    )

    result = materialize_candidate(anchors, [fact], source_text=fact_evidence)

    assert result.document["items"] == []
    issue = next(
        row
        for row in result.issues
        if row.code == "reference_assertion_state_owner_ambiguous"
    )
    assert issue.actual["reason"] == "reference_state_assertion_not_unique"
    assert len(issue.actual["candidate_owners"]) == 2
    assert not any(
        row.code == "numeric_tensile_owner_recovered"
        for row in result.issues
    )


def test_direct_target_tensile_result_is_unchanged_by_reference_assertion_gate():
    target_evidence = "LPBF had an ultimate tensile strength of 1.05 GPa."
    reference_evidence = (
        "Amato et al. reported an ultimate tensile strength of 0.90 GPa for "
        "LPBF specimens after HIPing."
    )
    anchors = [
        _anchor("LPBF"),
        _literature_state_anchor(
            "Amato et al.", "LPBF HIPed", reference_evidence
        ),
        _literature_state_anchor(
            "Amato et al.",
            "EPBF HIPed",
            "Amato et al. reported 0.33 GPa for EPBF specimens after HIPing.",
        ),
    ]
    fact = _tensile_property(
        "LPBF", value="1.05", unit="GPa", evidence=target_evidence
    )

    result = materialize_candidate(anchors, [fact], source_text=target_evidence)

    assert len(result.document["items"]) == 1
    item = result.document["items"][0]
    assert item["Sample_ID"] == "LPBF"
    assert item["Role"] == "Target"
    assert item["Extracted_Data"]["Properties"][0]["value_raw"] == "1.05"


def test_reference_assertion_state_recovery_is_anchor_order_invariant():
    lpbf_assertion = (
        "The literature UTS was 0.90 GPa for LPBF printed specimens after "
        "HIPing at 1120 °C for 4 h."
    )
    epbf_assertion = (
        "The literature UTS was 0.33 GPa for EPBF printed specimens after "
        "HIPing at 1120 °C for 4 h."
    )
    anchors = [
        _anchor("LPBF"),
        _literature_state_anchor("Amato et al.", "LPBF HIPed", lpbf_assertion),
        _literature_state_anchor("Amato et al.", "EPBF HIPed", epbf_assertion),
    ]
    fact = _tensile_property(
        "Amato et al.", value="0.90", unit="GPa", evidence=lpbf_assertion
    )

    forward = materialize_candidate(anchors, [fact], source_text=lpbf_assertion)
    reversed_result = materialize_candidate(
        list(reversed(anchors)), [fact], source_text=lpbf_assertion
    )

    assert forward.document == reversed_result.document
    forward_issue = next(
        row.to_dict()
        for row in forward.issues
        if row.code == "reference_assertion_state_owner_reassigned"
    )
    reversed_issue = next(
        row.to_dict()
        for row in reversed_result.issues
        if row.code == "reference_assertion_state_owner_reassigned"
    )
    assert forward_issue == reversed_issue


def test_unique_paper_level_tensile_context_adds_v203_protocol_dimensions(monkeypatch):
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
    assert prop["test_condition_raw"].startswith(
        "at a strain rate of 5 × 10^-3 s^-1"
    )
    assert "Instron 1361 testing machine" in prop["test_condition_raw"]
    assert "gauge length of 5 mm" in prop["test_condition_raw"]
    assert "repeated at least three times" in prop["test_condition_raw"]
    issue = next(
        row for row in result.issues if row.code == "property_test_context_recovered"
    )
    assert issue.actual["before"]["test_condition_raw"] is None
    assert issue.actual["after"]["test_condition_raw"] == (
        "at a strain rate of 5 × 10^-3 s^-1"
    )
    assert issue.evidence[0]["line_start"] == 3
    ledger_issue = next(
        row for row in result.issues if row.code == "tensile_protocol_ledger_bound"
    )
    assert ledger_issue.actual["after"]["test_condition_raw"] == prop[
        "test_condition_raw"
    ]
    assert set(ledger_issue.actual["decision"]["contributed_dimensions"]) >= {
        "equipment",
        "specimen",
        "replicates",
    }


def test_condition_projection_drops_equipment_between_temperature_and_rate():
    source = (
        "## Tensile testing\n\n"
        "Tensile tests were performed at 650 °C on an Instron 5565 at a strain "
        "rate of 1 × 10^-3 s^-1.\n"
    )

    result = materialize_candidate(
        [_anchor("A")], [_tensile_property()], source_text=source
    )

    condition = result.document["items"][0]["Extracted_Data"]["Properties"][0][
        "test_condition_raw"
    ]
    assert condition == "at 650 °C; at a strain rate of 1 × 10^-3 s^-1"
    assert "Instron" not in condition


def test_method_without_condition_dimension_is_not_recovered():
    source = (
        "## Tensile testing\n\n"
        "Dog-bone tensile specimens were extracted and tested using an Instron "
        "5565 with DIC. All tests were repeated three times.\n"
    )

    result = materialize_candidate(
        [_anchor("A")], [_tensile_property()], source_text=source
    )

    prop = result.document["items"][0]["Extracted_Data"]["Properties"][0]
    assert prop["test_condition_raw"] in (None, "")
    assert not any(
        issue.code == "property_test_context_recovered" for issue in result.issues
    )


def test_tensile_loading_experiment_recovers_compact_rate_fragment():
    method = (
        "A uniaxial tensile loading experiment was executed utilizing a MTS "
        "E45 servo-hydraulic testing system integrated with a digital image "
        "correlation (DIC) system. A camera captured strain images at 2 Hz. "
        "Testing coupons were extracted by EDM, with tests conducted at a "
        "nominal strain rate of 0.6 mm min^-1."
    )

    result = materialize_candidate(
        [_anchor("A")],
        [_tensile_property()],
        source_text=f"## Mechanical testing\n\n{method}\n",
    )

    prop = result.document["items"][0]["Extracted_Data"]["Properties"][0]
    assert prop["test_condition_raw"].startswith(
        "at a nominal strain rate of 0.6 mm min^-1"
    )
    assert "MTS E45 servo-hydraulic testing system" in prop["test_condition_raw"]
    assert "digital image correlation" in prop["test_condition_raw"]
    assert "strain images" not in prop["test_condition_raw"]
    issue = next(
        row for row in result.issues if row.code == "property_test_context_recovered"
    )
    assert issue.evidence[0]["heading"] == "Mechanical testing"
    assert issue.evidence[0]["discriminators"]["rate"] == ("strain:0.6:",)


def test_adjacent_tensile_specimen_sentence_contributes_standard_and_rate():
    method = (
        "Eighteen tensile test coupons were excised from three deposited walls. "
        "The number of coupons tested from each wall was 6. "
        "Each tensile specimen was tested according to ASTM E8-15a at a strain "
        "rate of 0.005 min^-1."
    )
    results_note = (
        "The tensile tests were conducted on six specimens. Slightly different "
        "testing practices were used after yielding with the extensometer removed."
    )
    source = f"## Tensile testing\n\n{method}\n\n## Results\n\n{results_note}\n"

    result = materialize_candidate(
        [_anchor("A")], [_tensile_property()], source_text=source
    )

    prop = result.document["items"][0]["Extracted_Data"]["Properties"][0]
    assert prop["test_condition_raw"] == (
        "according to ASTM E8-15a at a strain rate of 0.005 min^-1"
    )
    assert "ASTM E8-15a" in prop["test_condition_raw"]
    assert "0.005 min^-1" in prop["test_condition_raw"]
    assert "extensometer removed" not in prop["test_condition_raw"]


def test_two_complete_tensile_events_in_one_paragraph_remain_distinct():
    source = (
        "## Tensile testing\n\n"
        "Quasistatic tensile tests were performed at room temperature at a "
        "strain rate of 1 × 10^-3 s^-1. High-temperature tensile tests were "
        "performed at 650 °C at a strain rate of 2 × 10^-3 s^-1.\n"
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


@pytest.mark.parametrize(
    "source",
    [
        "During tensile loading, the alloy exhibited a yield strength of 900 MPa.",
        "Figure 5 shows the tensile loading direction and engineering stress-strain curve.",
        "The tensile strength increased from 800 MPa to 900 MPa.",
    ],
)
def test_tensile_loading_result_phrases_do_not_create_protocol(source):
    result = materialize_candidate(
        [_anchor("A")], [_tensile_property()], source_text=source
    )

    prop = result.document["items"][0]["Extracted_Data"]["Properties"][0]
    assert prop["test_condition_raw"] in (None, "")
    assert not any(
        row.code == "property_test_context_recovered" for row in result.issues
    )


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
        issue.code in {
            "property_test_context_recovered",
            "property_test_context_augmented",
        }
        for issue in result.issues
    )


@pytest.mark.parametrize("name", ["TE", "EAB"])
def test_tensile_abbreviation_participates_in_core_tensile_semantics(name):
    evidence = (
        "The yield strength was 482 MPa, the ultimate tensile strength was "
        f"539 MPa, and the {name} was 12.5%."
    )
    yield_fact = _tensile_property("Alloy-A", evidence=evidence)
    yield_fact.data["property_name_raw"] = "yield strength"
    yield_fact.data["value_raw"] = "482"
    uts_fact = _tensile_property("Alloy-A", evidence=evidence)
    uts_fact.data["value_raw"] = "539"
    fact = _tensile_property("not_reported", evidence=evidence)
    fact.data["property_name_raw"] = name
    fact.data["value_raw"] = "12.5"
    fact.data["unit_raw"] = "%"

    result = materialize_candidate(
        [_anchor("Alloy-A")], [yield_fact, uts_fact, fact]
    )

    properties = result.document["items"][0]["Extracted_Data"]["Properties"]
    assert len(properties) == 3
    assert any(row["property_name_raw"] == name for row in properties)
    issue = next(
        row for row in result.issues if row.code == "numeric_tensile_owner_recovered"
    )
    assert issue.actual["before_owner"] == "not_reported"
    assert issue.actual["after_owner"] == "Alloy-A"


def test_relative_tensile_property_does_not_join_absolute_tensile_bundle():
    evidence = (
        "Alloy-A had a yield strength of 482 MPa and an elongation reduced by 40%."
    )
    yield_fact = _tensile_property("Alloy-A", evidence=evidence)
    yield_fact.data["property_name_raw"] = "yield strength"
    yield_fact.data["value_raw"] = "482"
    relative = _tensile_property(
        "not_reported", evidence="The elongation was reduced by 40%."
    )
    relative.data["property_name_raw"] = "elongation relative change"
    relative.data["value_raw"] = "reduced by 40%"
    relative.data["unit_raw"] = "%"

    result = materialize_candidate(
        [_anchor("Alloy-A"), _anchor("Alloy-B")], [yield_fact, relative]
    )

    assert any(issue.code == "unresolved_sample_alias" for issue in result.issues)
    assert not any(
        issue.code == "numeric_tensile_owner_recovered"
        and issue.actual.get("before_owner") == "not_reported"
        for issue in result.issues
    )


@pytest.mark.parametrize("existing", ["RT", "room temperature", "ambient temperature"])
def test_partial_compatible_tensile_condition_is_augmented_with_compact_fragments(existing):
    protocol = (
        "Tensile tests were performed at room temperature according to ASTM E8 "
        "at a strain rate of 1 × 10^-3 s^-1 using an Instron 5565."
    )
    source = f"## Tensile testing\n\n{protocol}\n"

    result = materialize_candidate(
        [_anchor("A")],
        [_tensile_property(condition=existing)],
        source_text=source,
    )

    prop = result.document["items"][0]["Extracted_Data"]["Properties"][0]
    assert prop["test_condition_raw"].startswith(existing)
    assert prop["test_condition_raw"] == (
        f"{existing}\n\naccording to ASTM E8 "
        "at a strain rate of 1 × 10^-3 s^-1"
    )
    assert "Instron" not in prop["test_condition_raw"]
    issue = next(
        row for row in result.issues if row.code == "property_test_context_augmented"
    )
    assert issue.actual["before"]["test_condition_raw"] == existing
    assert issue.actual["after"]["test_condition_raw"] == prop["test_condition_raw"]
    assert issue.expected["overwrite_existing_condition"] is False


def test_partial_condition_selects_only_compatible_protocol_for_augmentation():
    source = "\n\n".join(
        [
            "## Tensile testing",
            "Tensile tests were performed at room temperature at a strain rate of 1 × 10^-3 s^-1.",
            "Tensile tests were performed at 650 °C at a strain rate of 2 × 10^-3 s^-1.",
        ]
    )

    result = materialize_candidate(
        [_anchor("A")],
        [_tensile_property(condition="RT")],
        source_text=source,
    )

    condition = result.document["items"][0]["Extracted_Data"]["Properties"][0][
        "test_condition_raw"
    ]
    assert condition == "RT\n\nat a strain rate of 1 × 10^-3 s^-1"
    assert "650 °C" not in condition
    issue = next(
        row for row in result.issues if row.code == "property_test_context_augmented"
    )
    assert len(issue.actual["rejected_candidates"]) == 1


@pytest.mark.parametrize("existing", ["RT", "600 °C"])
def test_multi_temperature_protocol_adds_only_shared_literal_details(existing):
    source = (
        "## Mechanical testing\n\n"
        "The quasi-static uniaxial tensile tests at room temperature and "
        "600 ^\\circC were conducted on an Instron 5565 testing machine at an "
        "initial strain rate of 1.0 × 10^-3 s^-1 with a video extensometer. "
        "The direction of testing was perpendicular to the building direction. "
        "All tests were repeated at least three times.\n"
    )

    result = materialize_candidate(
        [_anchor("A")],
        [_tensile_property(condition=existing)],
        source_text=source,
    )

    prop = result.document["items"][0]["Extracted_Data"]["Properties"][0]
    condition = prop["test_condition_raw"]
    assert condition.startswith(existing)
    assert "strain rate of 1.0 × 10^-3 s^-1" in condition
    assert "initial strain rate of 1.0 × 10^-3 s^-1" in condition
    assert "perpendicular to the building direction" in condition
    assert "room temperature and 600" not in condition
    issue = next(
        row for row in result.issues if row.code == "property_test_context_augmented"
    )
    assert issue.actual["accepted_source_fragments"][0].startswith(
        "at an initial strain rate of 1.0 × 10^-3 s^-1"
    )
    assert all(
        "room temperature" not in fragment and "600" not in fragment
        for fragment in issue.actual["accepted_source_fragments"]
    )


def test_unqualified_property_does_not_inherit_multi_temperature_matrix():
    source = (
        "## Mechanical testing\n\n"
        "Uniaxial tensile tests at room temperature and 600 °C were conducted "
        "on an Instron 5565 at a strain rate of 1 × 10^-3 s^-1.\n"
    )

    result = materialize_candidate(
        [_anchor("A")], [_tensile_property()], source_text=source
    )

    prop = result.document["items"][0]["Extracted_Data"]["Properties"][0]
    assert prop["test_condition_raw"] in (None, "")
    issue = next(
        row for row in result.issues if row.code == "ambiguous_property_test_context"
    )
    assert "multi-temperature" in issue.actual["reason"]


def test_existing_condition_without_safe_compatible_protocol_is_preserved_and_reviewed():
    source = (
        "## Tensile testing\n\n"
        "Tensile tests were performed at 650 °C at a strain rate of 2 × 10^-3 s^-1.\n"
    )

    result = materialize_candidate(
        [_anchor("A")],
        [_tensile_property(condition="room temperature")],
        source_text=source,
    )

    prop = result.document["items"][0]["Extracted_Data"]["Properties"][0]
    assert prop["test_condition_raw"] == "room temperature"
    issue = next(
        row for row in result.issues if row.code == "ambiguous_property_test_context"
    )
    assert "conflicts" in issue.actual["reason"]


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
    assert prop["test_condition_raw"].startswith("at 650 °C at a strain rate of 2 × 10^-3 s^-1")


def test_selected_owner_disambiguates_multiple_tensile_protocols():
    source = "\n\n".join(
        [
            "## Tensile testing",
            "Alloy-A tensile tests were performed at room temperature at a strain rate of 1 × 10^-3 s^-1.",
            "Alloy-B tensile tests were performed at 650 °C at a strain rate of 2 × 10^-3 s^-1.",
        ]
    )
    fact = _tensile_property(
        "Alloy-A",
        evidence="Alloy-A had an ultimate tensile strength of 900 MPa.",
    )

    result = materialize_candidate(
        [_anchor("Alloy-A"), _anchor("Alloy-B")],
        [fact],
        source_text=source,
    )

    prop = result.document["items"][0]["Extracted_Data"]["Properties"][0]
    assert prop["test_condition_raw"] == "at room temperature at a strain rate of 1 × 10^-3 s^-1"
    assert "Alloy-B" not in prop["test_condition_raw"]
    issue = next(
        row for row in result.issues if row.code == "property_test_context_recovered"
    )
    assert issue.actual["selected_owner"] == "Alloy-A"
    assert len(issue.actual["rejected_candidates"]) == 1


def test_multi_owner_property_does_not_inherit_unbound_paper_level_protocol():
    """A shared Methods protocol must not be copied to an owner-free result."""

    source = (
        "## Tensile testing\n\n"
        "Quasistatic uniaxial tensile tests were conducted in an Instron 3344 "
        "at a constant strain rate of 5 × 10^-4 s^-1.\n"
    )
    fact = _tensile_property(
        "Alloy-B",
        evidence="Alloy-B shows a tensile modulus of approximately 100 GPa.",
        value="100",
        name="tensile modulus",
        unit="GPa",
    )

    result = materialize_candidate(
        [_anchor("Alloy-A"), _anchor("Alloy-B")], [fact], source_text=source
    )

    prop = next(
        row
        for row in result.document["items"]
        if row["Sample_ID"] == "Alloy-B"
    )["Extracted_Data"]["Properties"][0]
    assert prop["test_condition_raw"] in (None, "")
    issue = next(
        row for row in result.issues if row.code == "ambiguous_property_test_context"
    )
    assert "property-local" in issue.actual["reason"]


def test_multi_owner_core_tensile_owner_free_protocol_is_audited():
    """Shared Methods context is isolated without a local owner coordinate."""

    source = (
        "## Tensile testing\n\n"
        "Quasistatic uniaxial tensile tests were conducted in an Instron 3344 "
        "at a constant strain rate of 5 × 10^-4 s^-1.\n"
    )
    fact = _tensile_property(
        "Alloy-B",
        evidence="The alloy showed an ultimate tensile strength of 900 MPa.",
    )

    result = materialize_candidate(
        [_anchor("Alloy-A"), _anchor("Alloy-B")], [fact], source_text=source
    )

    issue = next(
        row
        for row in result.issues
        if row.code == "property_test_context_shared_scope_quarantined"
    )
    assert issue.actual["owner_evidence_in_property"] is False
    prop = next(
        row
        for row in result.document["items"]
        if row["Sample_ID"] == "Alloy-B"
    )["Extracted_Data"]["Properties"][0]
    assert prop["test_condition_raw"] in (None, "")


def test_multi_owner_core_tensile_owner_value_does_not_inherit_shared_protocol():
    """Owner+value alone is not a safe protocol coordinate in a multi-owner paper."""

    source = (
        "## Tensile testing\n\n"
        "Quasistatic uniaxial tensile tests were conducted in an Instron 3344 "
        "at a constant strain rate of 5 × 10^-4 s^-1.\n"
    )
    fact = _tensile_property(
        "Alloy-B",
        evidence="Alloy-B showed an ultimate tensile strength of 900 MPa.",
    )

    result = materialize_candidate(
        [_anchor("Alloy-A"), _anchor("Alloy-B")], [fact], source_text=source
    )

    prop = next(
        row
        for row in result.document["items"]
        if row["Sample_ID"] == "Alloy-B"
    )["Extracted_Data"]["Properties"][0]
    assert prop["test_condition_raw"] in (None, "")
    issue = next(
        row
        for row in result.issues
        if row.code == "property_test_context_shared_scope_quarantined"
    )
    assert issue.actual["owner_evidence_in_property"] is False


def test_physical_owner_coordinate_binds_one_shared_tensile_protocol():
    source = (
        "## Tensile testing\n\n"
        "Quasistatic uniaxial tensile tests were conducted in an Instron 3344 "
        "at a constant strain rate of 5 × 10^-4 s^-1 at room temperature.\n"
    )
    fact = _tensile_property(
        "Alloy-B",
        evidence="The treated alloy had an ultimate tensile strength of 900 MPa.",
    )
    fact.data["property_id_candidate"] = "physical-owner-envelope:abc"
    fact.data["test_specimen_raw"] = "vertical to build direction"
    duplicate = _tensile_property(
        "Alloy-B",
        evidence="The treated alloy showed an ultimate tensile strength of 900 MPa.",
    )

    result = materialize_candidate(
        [_anchor("Alloy-A"), _anchor("Alloy-B")],
        [duplicate, fact],
        source_text=source,
    )

    prop = next(
        row
        for item in result.document["items"]
        if item["Sample_ID"] == "Alloy-B"
        for row in item["Extracted_Data"]["Properties"]
    )
    assert "room temperature" in prop["test_condition_raw"]
    issue = next(
        row
        for row in result.issues
        if row.code
        in {
            "tensile_physical_owner_protocol_recovered",
            "tensile_physical_owner_protocol_bound",
        }
    )
    assert issue.actual["decision_key"] == "physical-owner-envelope:abc"
    assert not any(
        row.code == "property_test_context_shared_scope_quarantined"
        for row in result.issues
    )


def test_shared_scope_quarantine_isolates_specimen_from_not_reported_condition():
    """An unbound X/Z token must not become normalized condition detail."""

    source = (
        "## Tensile testing\n\n"
        "Quasistatic uniaxial tensile tests were conducted in an Instron 3344 "
        "at a constant strain rate of 5 × 10^-4 s^-1.\n"
    )
    fact = _tensile_property(
        "Alloy-B",
        evidence="The alloy showed an ultimate tensile strength of 900 MPa.",
    )
    fact.data["test_specimen_raw"] = "X"
    fact.data["raw_note"] = "X"
    fact.data["orientation_raw"] = "X orientation"

    result = materialize_candidate(
        [_anchor("Alloy-A"), _anchor("Alloy-B")], [fact], source_text=source
    )

    prop = next(
        row
        for item in result.document["items"]
        if item["Sample_ID"] == "Alloy-B"
        for row in item["Extracted_Data"]["Properties"]
    )
    assert prop["test_condition_raw"] in (None, "")
    assert prop["test_specimen_raw"] == ""
    assert prop.get("orientation_raw", "") == ""
    issue = next(
        row
        for row in result.issues
        if row.code == "property_test_specimen_shared_scope_quarantined"
    )
    assert issue.actual["before"]["test_specimen_raw"] == "X"
    assert issue.actual["after"]["test_specimen_raw"] == ""
    assert issue.actual["before"]["orientation_raw"] == "X orientation"
    assert issue.actual["after"]["orientation_raw"] == ""


def test_unique_table_owner_and_explicit_all_tests_scope_recovers_shared_protocol():
    method = (
        "Dog-bone tensile specimens were extracted from the as-built samples. "
        "The specimens were subjected to uniaxial tensile tests at a strain "
        "rate of 5 × 10^-3 s^-1 using an Instron 1361 machine. "
        "Precise strains were measured using digital image correlation. "
        "All tensile tests were repeated at least three times."
    )
    table = r"""
<table><tr><td>Iteration</td><td>Sample</td><td>Power</td><td>Time</td><td>VED</td><td>UTS</td><td>TE</td></tr>
<tr><td>1</td><td>1-1</td><td>250</td><td>2</td><td>94.69</td><td>$ 1061 \pm 27.5 $</td><td>$ 18.3 \pm 1.5 $</td></tr>
<tr><td>1</td><td>1-2</td><td>300</td><td>2</td><td>90.57</td><td>$ 1065 \pm 17.0 $</td><td>$ 16.3 \pm 2.0 $</td></tr></table>
"""
    evidence = r"| 1-1 | 2 | 94.69 | $ 1061 \pm 27.5 $ | $ 18.3 \pm 1.5 $ |"
    fact = _table_tensile_property(
        "1-1", "1061 ± 27.5", evidence, name="UTS"
    )

    result = materialize_candidate(
        [_anchor("1-1"), _anchor("1-2")],
        [fact],
        source_text=f"## Tensile test\n\n{method}\n\n{table}",
    )

    prop = next(
        item
        for item in result.document["items"]
        if item["Sample_ID"] == "1-1"
    )["Extracted_Data"]["Properties"][0]
    assert "5 × 10^-3 s^-1" in prop["test_condition_raw"]
    issue = next(
        row
        for row in result.issues
        if row.code == "property_test_context_table_owner_recovered"
    )
    assert issue.actual["explicit_global_tensile_scope"] is True
    assert issue.actual["unique_table_projection"]["distinct_match_count"] == 1
    assert not any(
        row.code == "property_test_context_shared_scope_quarantined"
        for row in result.issues
    )


def test_unique_table_owner_and_per_material_replicates_recover_shared_protocol():
    method = (
        "Uniaxial tensile tests were conducted at a constant crosshead rate "
        "of 1 mm/min using an Instron testing machine. "
        "At least three samples were tested for each material."
    )
    table = """
| Iteration | Material | Power | Time | VED | UTS (MPa) |
| --- | --- | --- | --- | --- | --- |
| 1 | Alloy-A | 250 | 2 | 94.69 | 901 |
| 1 | Alloy-B | 300 | 2 | 90.57 | 875 |
"""
    fact = _table_tensile_property(
        "Alloy-A", "901", "| Alloy-A | 2 | 94.69 | 901 |", name="UTS"
    )

    result = materialize_candidate(
        [_anchor("Alloy-A"), _anchor("Alloy-B")],
        [fact],
        source_text=f"## Tensile testing\n\n{method}\n\n{table}",
    )

    prop = next(
        item
        for item in result.document["items"]
        if item["Sample_ID"] == "Alloy-A"
    )["Extracted_Data"]["Properties"][0]
    assert "1 mm/min" in prop["test_condition_raw"]
    assert "Instron testing machine" in prop["test_condition_raw"]
    assert "At least three samples were tested" in prop["test_condition_raw"]
    issue = next(
        row
        for row in result.issues
        if row.code == "property_test_context_table_owner_recovered"
    )
    assert issue.actual["global_scope_evidence"] == [
        "At least three samples were tested for each material."
    ]
    assert issue.actual["owner_role"] == "Target"
    assert issue.actual["owner_invented"] is False


def test_global_tensile_scope_v201_can_be_disabled_for_shadow_ab(monkeypatch):
    method = (
        "Uniaxial tensile tests were conducted at a constant crosshead rate "
        "of 1 mm/min using an Instron testing machine. "
        "At least three samples were tested for each material."
    )
    table = """
| Iteration | Material | Power | Time | VED | UTS (MPa) |
| --- | --- | --- | --- | --- | --- |
| 1 | Alloy-A | 250 | 2 | 94.69 | 901 |
| 1 | Alloy-B | 300 | 2 | 90.57 | 875 |
"""
    fact = _table_tensile_property(
        "Alloy-A", "901", "| Alloy-A | 2 | 94.69 | 901 |", name="UTS"
    )
    monkeypatch.setenv("KNOWMAT2_ALPHA25_GLOBAL_TENSILE_SCOPE_V201", "off")
    monkeypatch.setenv("KNOWMAT2_ALPHA25_TENSILE_PROTOCOL_LEDGER_V203", "off")
    monkeypatch.setenv(
        "KNOWMAT2_ALPHA25_DENSE_TENSILE_TABLE_COMPLETION_V203", "off"
    )

    result = materialize_candidate(
        [_anchor("Alloy-A"), _anchor("Alloy-B")],
        [fact],
        source_text=f"## Tensile testing\n\n{method}\n\n{table}",
    )

    prop = next(
        item
        for item in result.document["items"]
        if item["Sample_ID"] == "Alloy-A"
    )["Extracted_Data"]["Properties"][0]
    assert prop["test_condition_raw"] in (None, "")
    assert any(
        row.code == "property_test_context_shared_scope_quarantined"
        for row in result.issues
    )
    assert not any(
        row.code == "property_test_context_table_owner_recovered"
        for row in result.issues
    )


def test_fatigue_all_specimens_cue_does_not_authorize_tensile_protocol():
    method = (
        "Uniaxial tensile tests were conducted at a constant crosshead rate "
        "of 1 mm/min using an Instron testing machine. "
        "For fatigue testing, all the specimens were loaded at 20 Hz."
    )
    table = """
| Iteration | Material | Power | Time | VED | UTS (MPa) |
| --- | --- | --- | --- | --- | --- |
| 1 | Alloy-A | 250 | 2 | 94.69 | 901 |
| 1 | Alloy-B | 300 | 2 | 90.57 | 875 |
"""
    fact = _table_tensile_property(
        "Alloy-A", "901", "| Alloy-A | 2 | 94.69 | 901 |", name="UTS"
    )

    result = materialize_candidate(
        [_anchor("Alloy-A"), _anchor("Alloy-B")],
        [fact],
        source_text=f"## Mechanical testing\n\n{method}\n\n{table}",
    )

    prop = next(
        item
        for item in result.document["items"]
        if item["Sample_ID"] == "Alloy-A"
    )["Extracted_Data"]["Properties"][0]
    assert prop["test_condition_raw"] in (None, "")
    assert not any(
        row.code == "property_test_context_table_owner_recovered"
        for row in result.issues
    )
    assert any(
        row.code == "property_test_context_shared_scope_quarantined"
        for row in result.issues
    )


def test_unique_table_owner_does_not_inherit_protocol_without_all_tests_scope():
    method = (
        "One tensile specimen was subjected to a tensile test at a strain "
        "rate of 5 × 10^-3 s^-1 using an Instron 1361 machine."
    )
    table = """
| Iteration | Sample | Power | Time | VED | UTS |
| --- | --- | --- | --- | --- | --- |
| 1 | A1 | 250 | 2 | 94.69 | 1061 |
| 1 | A2 | 300 | 2 | 90.57 | 1065 |
"""
    fact = _table_tensile_property(
        "A1", "1061", "| A1 | 2 | 94.69 | 1061 |", name="UTS"
    )

    result = materialize_candidate(
        [_anchor("A1"), _anchor("A2")],
        [fact],
        source_text=f"## Tensile test\n\n{method}\n\n{table}",
    )

    prop = next(
        item
        for item in result.document["items"]
        if item["Sample_ID"] == "A1"
    )["Extracted_Data"]["Properties"][0]
    assert prop["test_condition_raw"] in (None, "")
    assert any(
        row.code == "property_test_context_shared_scope_quarantined"
        for row in result.issues
    )
    assert not any(
        row.code == "property_test_context_table_owner_recovered"
        for row in result.issues
    )


def test_multi_owner_core_tensile_local_protocol_discriminator_is_allowed():
    """A value quote carrying the rate remains bound to the shared protocol."""

    source = (
        "## Tensile testing\n\n"
        "Quasistatic uniaxial tensile tests were conducted in an Instron 3344 "
        "at a constant strain rate of 5 × 10^-4 s^-1.\n"
    )
    fact = _tensile_property(
        "Alloy-B",
        evidence=(
            "Alloy-B showed an ultimate tensile strength of 900 MPa at a "
            "constant strain rate of 5 × 10^-4 s^-1."
        ),
    )

    result = materialize_candidate(
        [_anchor("Alloy-A"), _anchor("Alloy-B")], [fact], source_text=source
    )

    prop = next(
        row
        for row in result.document["items"]
        if row["Sample_ID"] == "Alloy-B"
    )["Extracted_Data"]["Properties"][0]
    assert prop["test_condition_raw"] == (
        "at a constant strain rate of 5 × 10^-4 s^-1"
    )


def test_qualified_state_accepts_protocol_named_by_its_base_owner():
    source = (
        "Alloy-A tensile tests were performed at room temperature at "
        "a strain rate of 2.5 × 10^-4 s^-1."
    )
    fact = _tensile_property("Alloy-A [solution treated]")

    result = materialize_candidate(
        [_anchor("Alloy-A", "as-built"), _anchor("Alloy-A", "solution treated")],
        [fact],
        source_text=source,
    )

    item = result.document["items"][0]
    assert item["Sample_ID"] == "Alloy-A [solution treated]"
    prop = item["Extracted_Data"]["Properties"][0]
    assert prop["test_condition_raw"] == (
        "at room temperature at a strain rate of 2.5 × 10^-4 s^-1"
    )
    issue = next(
        row for row in result.issues if row.code == "property_test_context_recovered"
    )
    assert "Alloy-A" in issue.actual["owner_labels"]


def test_protocol_explicitly_owned_by_another_material_is_not_inherited():
    source = (
        "## Tensile testing\n\n"
        "Alloy-B tensile tests were performed at 650 °C at a strain rate of "
        "2 × 10^-3 s^-1.\n"
    )
    fact = _tensile_property(
        "Alloy-A",
        evidence="Alloy-A had an ultimate tensile strength of 900 MPa.",
    )

    result = materialize_candidate(
        [_anchor("Alloy-A"), _anchor("Alloy-B")],
        [fact],
        source_text=source,
    )

    item = next(row for row in result.document["items"] if row["Sample_ID"] == "Alloy-A")
    prop = item["Extracted_Data"]["Properties"][0]
    assert prop["test_condition_raw"] in (None, "")
    issue = next(
        row for row in result.issues if row.code == "ambiguous_property_test_context"
    )
    assert issue.actual["selected_owner"] == "Alloy-A"
    assert "different material owner" in issue.actual["reason"]


def test_test_temperature_does_not_select_a_material_preparation_state():
    anchors = [
        _anchor("A", "solution treated at 650 °C"),
        _anchor("A", "aged at 900 °C"),
    ]
    fact = _tensile_property(
        "A",
        condition="tested at 650 °C at a strain rate of 1 × 10^-3 s^-1",
        evidence="A had an ultimate tensile strength of 900 MPa.",
    )

    result = materialize_candidate(anchors, [fact])

    assert [row["Sample_ID"] for row in result.document["items"]] == ["A"]
    prop = result.document["items"][0]["Extracted_Data"]["Properties"][0]
    assert prop["test_condition_raw"].startswith("tested at 650 °C")
    assert not any(
        issue.code == "fact_owner_state_reconciled" for issue in result.issues
    )


def test_tensile_preparation_condition_isolated_from_formal_test_condition():
    fact = _tensile_property(
        "A [sintered at 1280 °C]",
        condition="sintered at 1280 °C",
        value="612",
        evidence="A [sintered at 1280 °C] showed a UTS of 612 MPa.",
    )

    result = materialize_candidate(
        [_anchor("A"), _anchor("A", "sintered at 1280 °C")], [fact]
    )

    prop = result.document["items"][0]["Extracted_Data"]["Properties"][0]
    assert prop["test_condition_raw"] == ""
    issue = next(
        row
        for row in result.issues
        if row.code == "tensile_preparation_condition_isolated"
    )
    assert issue.actual["before"]["data"]["test_condition_raw"] == (
        "sintered at 1280 °C"
    )
    assert issue.actual["after"]["data"]["test_condition_raw"] == ""


def test_bare_temperature_isolated_when_named_sample_is_source_proven_sintered():
    source = (
        "Samples were sintered at 1280, 1290 and 1300 °C for 4 h. "
        "Rate controlled tensile tests at 5 mm/min were performed on the samples."
    )
    fact = _tensile_property(
        "1280 °C sample",
        condition="1280 °c",
        value="612",
        evidence="the 1280 °C sample showing the highest UTS of 612 MPa",
    )

    result = materialize_candidate([_anchor("1280 °C sample")], [fact], source_text=source)

    prop = result.document["items"][0]["Extracted_Data"]["Properties"][0]
    assert "1280" not in prop["test_condition_raw"]
    assert "5 mm/min" in prop["test_condition_raw"]
    assert any(
        row.code == "tensile_preparation_condition_isolated"
        and row.actual["reason"] == "source_preparation_temperature_for_named_sample"
        for row in result.issues
    )


def test_bare_tensile_test_temperature_is_not_isolated_without_preparation_evidence():
    fact = _tensile_property(
        "A",
        condition="650 °C",
        evidence="A had a UTS of 900 MPa at 650 °C.",
    )

    result = materialize_candidate([_anchor("A")], [fact])

    prop = result.document["items"][0]["Extracted_Data"]["Properties"][0]
    assert prop["test_condition_raw"] == "650 °C"
    assert not any(
        row.code == "tensile_preparation_condition_isolated" for row in result.issues
    )


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
    assert prop["test_condition_raw"] == "at 5 mm/min"


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
    assert condition == "at a strain rate of 1 × 10^-3 s^-1"
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


def test_shared_tensile_matrix_keeps_source_owner_qualifier_in_condition():
    source = (
        "## Tensile testing\n\n"
        "Eighteen tensile test coupons were excised from walls made with 0, 120, "
        "and 300 s interlayer delays. Each tensile specimen was tested according "
        "to ASTM E8-15a at a strain rate of 0.005 min^-1.\n"
    )
    table = (
        "| Properties | 0 s Delay | 120 s Delay | 300 s Delay |\n"
        "| --- | --- | --- | --- |\n"
        "| UTS (MPa) | 915 | 959 | 928 |"
    )
    facts = [
        _tensile_property("Ti-6Al-4V", evidence=table, data_source="table"),
        _tensile_property(
            "Ti-6Al-4V", evidence=table, value="928", data_source="table"
        ),
    ]
    facts[0].data["test_specimen_raw"] = "0 s Delay"
    facts[1].data["test_specimen_raw"] = "300 s Delay"
    index = PropertyContextIndex(source)
    for fact, owner in zip(facts, ("0 s Delay", "300 s Delay")):
        decision = index.recover(
            fact.data,
            owner_role="Target",
            owner_labels=(owner,),
            other_owner_labels=(
                "0 s Delay" if owner != "0 s Delay" else "300 s Delay",
                "120 s Delay",
            ),
        )
        assert decision.condition_raw.startswith(f"{owner};")
        assert decision.owner_qualifier == owner


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


def test_cited_non_tensile_property_cell_recovers_independent_reference_owner():
    evidence = (
        "| Properties | Wrought | WAAM |\n"
        "| Vickers Hardness (HV) | 322 [ASTM F_{136}] | 332 [39] |"
    )
    fact = _raw_property(
        "Wrought",
        "Vickers Hardness",
        "322",
        evidence,
        source="table",
    )
    fact.data["unit_raw"] = "HV"

    reference = InventoryAnchor(
        sample_id_raw="Wrought [37] [reference]",
        material_name_raw=None,
        state_raw=None,
        role="Reference",
        data_nature="Literature_Experimental",
        source_evidence=["Wrought [37]"],
        confidence=0.9,
    )
    result = materialize_candidate([_anchor("Wrought"), reference], [fact])

    assert len(result.document["items"]) == 1
    item = result.document["items"][0]
    assert item["Sample_ID"] == "Wrought [37] [reference]"
    assert item["Role"] == "Reference"
    assert item["Data_Nature"] == "Literature_Experimental"
    properties = item["Extracted_Data"]["Properties"]
    assert properties[0]["property_name_raw"] == "Vickers Hardness"
    issue = next(
        row
        for row in result.issues
        if row.code == "reference_property_owner_recovered"
    )
    assert issue.actual["before_owner"] == "Wrought"
    assert issue.actual["after_owner"] == "Wrought [37] [reference]"


def test_reference_property_is_not_routed_back_to_target_by_generic_table_recovery():
    """A citation-recovered fact must remain on the independent reference item."""

    evidence = (
        "| Properties | Wrought | WAAM |\n"
        "| Vickers Hardness (HV) | 322 [ASTM F_{136}] | 332 [39] |"
    )
    target_fact = _raw_property(
        "Wrought", "Vickers Hardness", "322", evidence, source="table"
    )
    target_fact.data["unit_raw"] = "HV"
    # The model can emit the same table coordinate again after a chunk boundary,
    # already carrying the explicit reference presentation from an earlier
    # recovery.  The later generic table pass must not move that row to Target.
    reference_fact = target_fact.model_copy(
        deep=True, update={"sample_id_raw": "Wrought [37] [reference]"}
    )
    reference_anchor = InventoryAnchor(
        sample_id_raw="Wrought [37] [reference]",
        material_name_raw=None,
        state_raw=None,
        role="Reference",
        data_nature="Literature_Experimental",
        source_evidence=["Wrought [37]"],
        confidence=0.9,
    )

    result = materialize_candidate(
        [_anchor("Wrought"), reference_anchor],
        [target_fact, reference_fact],
        source_text=evidence,
    )

    items = {item["Sample_ID"]: item for item in result.document["items"]}
    assert "Wrought" not in items
    assert "Wrought [37] [reference]" in items
    assert any(
        row.get("value_raw") == "322"
        for row in items["Wrought [37] [reference]"]["Extracted_Data"][
            "Properties"
        ]
    )
    assert not any(
        issue.code == "source_table_generic_owner_recovered"
        and issue.actual.get("before_owner") == "Wrought [37] [reference]"
        for issue in result.issues
    )


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


def _cropped_microanalysis_fact(
    *,
    location: str = "Point 1",
    components: tuple[tuple[str, str], ...] = (
        ("Ni", "60.49"),
        ("Cr", "21.51"),
        ("C", "0.42"),
    ),
    measurement: str = "fracture surface Point 1",
    evidence: str | None = None,
) -> CompositionFact:
    row = evidence or (
        f"{location} [wt.-%] | "
        + " | ".join(value for _, value in components)
    )
    fact = _composition_fact(
        "alloy A [sintered]",
        "alloy A [sintered]",
        row,
    )
    fact.data.update(
        {
            "source_type": "measured",
            "material_state": "sintered",
            "basis": "wt%",
            "components": [
                {
                    "name_raw": name,
                    "canonical_name": None,
                    "value_kind": "scalar",
                    "value_raw": value,
                    "value": None,
                    "unit_raw": "wt.-%",
                    "canonical_unit": None,
                    "data_nature": "reported",
                }
                for name, value in components
            ],
            "measurement": measurement,
            "raw_expression": (
                f"{location} [wt.-%]: "
                + ", ".join(f"{name} {value}" for name, value in components)
            ),
            "data_source": "table",
            "source_evidence": [row],
        }
    )
    return fact.model_copy(update={"source_evidence": [row]})


def _microanalysis_table_source(
    *,
    marker: str = "EDS elemental analysis",
    temperature: int = 1280,
    ni: str = "60.49",
) -> str:
    return (
        "## Fractography\n\n"
        f"Fig. 12. Fracture surface with corresponding {marker} results of "
        f"the sintered sample at {temperature} °C for 4 h.\n\n"
        "Compositional analysis in wt.% of the points on the fracture surface.\n\n"
        "| Element | Ni | Cr | C | O |\n"
        "| --- | --- | --- | --- | --- |\n"
        f"| Point 1 [wt.-%] | {ni} | 21.51 | 0.42 | 1.43 |\n"
        "| Point 2 [wt.-%] | 37.04 | 11.46 | 33.97 | - |"
    )


def _microanalysis_table_anchors() -> list[InventoryAnchor]:
    return [
        InventoryAnchor(
            sample_id_raw="alloy A [sintered]",
            material_name_raw="alloy A",
            state_raw="sintered",
            role="Target",
            data_nature="Experimental",
            source_evidence=["alloy A sintered samples"],
            confidence=0.9,
        ),
        InventoryAnchor(
            sample_id_raw="sample sintered at 1280 °C",
            material_name_raw="alloy A",
            state_raw="sintered at 1280 °C for 4 h",
            role="Target",
            data_nature="Experimental",
            source_evidence=["sample sintered at 1280 °C for 4 h"],
            confidence=0.95,
        ),
    ]


def test_cropped_microanalysis_table_envelope_recovers_location_owner_and_state():
    main = _cropped_microanalysis_fact()
    oxygen = _cropped_microanalysis_fact(
        components=(("O", "1.43"),),
        measurement="EDS on fracture surface",
        evidence="Point 1 [wt.-%] | 1.43",
    )

    result = materialize_candidate(
        _microanalysis_table_anchors(),
        [main, oxygen],
        source_text=_microanalysis_table_source(),
    )

    populated = [
        item
        for item in result.document["items"]
        if item["Extracted_Data"]["Composition"]["Composition_Observations"]
    ]
    assert [item["Sample_ID"] for item in populated] == [
        "sample sintered at 1280 °C"
    ]
    observations = populated[0]["Extracted_Data"]["Composition"][
        "Composition_Observations"
    ]
    assert [row["sample_id"] for row in observations] == ["Point 1", "Point 1"]
    assert {row["material_state"] for row in observations} == {
        "sintered at 1280 °C for 4 h"
    }
    assert {component["name_raw"] for row in observations for component in row["components"]} == {
        "Ni",
        "Cr",
        "C",
        "O",
    }
    assert observations[0]["measurement"] == "fracture surface Point 1"
    assert observations[1]["measurement"] == "EDS on fracture surface"
    assert all("_microanalysis_owner_recovered" not in row for row in observations)

    issue = next(
        row
        for row in result.issues
        if row.code == "microanalysis_table_envelope_owner_recovered"
    )
    assert issue.actual["before_owner"] == "alloy A [sintered]"
    assert issue.actual["after_owner"] == "sample sintered at 1280 °C"
    assert issue.actual["observation_location"] == "Point 1"
    assert issue.actual["after_state"] == "sintered at 1280 °C for 4 h"
    assert issue.actual["facts"] == [main.model_dump(), oxygen.model_dump()]
    assert issue.actual["table_header"] == ["Element", "Ni", "Cr", "C", "O"]
    assert issue.actual["source_row"] == [
        "Point 1 [wt.-%]",
        "60.49",
        "21.51",
        "0.42",
        "1.43",
    ]
    assert {row["component"] for row in issue.actual["component_matches"]} == {
        "Ni",
        "Cr",
        "C",
        "O",
    }


@pytest.mark.parametrize(
    ("facts", "source_text", "anchors"),
    [
        (
            [_cropped_microanalysis_fact()],
            _microanalysis_table_source(marker="point measurements"),
            _microanalysis_table_anchors(),
        ),
        (
            [_cropped_microanalysis_fact(components=(("Ni", "61.00"),))],
            _microanalysis_table_source(),
            _microanalysis_table_anchors(),
        ),
        (
            [_cropped_microanalysis_fact()],
            _microanalysis_table_source(),
            [
                *_microanalysis_table_anchors(),
                InventoryAnchor(
                    sample_id_raw="second sample sintered at 1280 °C",
                    material_name_raw="alloy B",
                    state_raw="sintered at 1280 °C for 4 h",
                    role="Target",
                    data_nature="Experimental",
                    source_evidence=["second sample sintered at 1280 °C for 4 h"],
                    confidence=0.95,
                ),
            ],
        ),
        (
            [_cropped_microanalysis_fact()],
            (
                "## Mechanical test\n\n"
                "The sintered sample at 1280 °C for 4 h was tested.\n\n"
                "| Point | Stress | Strain |\n"
                "| --- | --- | --- |\n"
                "| Point 1 | 60.49 | 21.51 |"
            ),
            _microanalysis_table_anchors(),
        ),
    ],
    ids=("missing_eds_marker", "value_mismatch", "ambiguous_owner", "non_eds_table"),
)
def test_unsafe_cropped_microanalysis_table_envelopes_are_not_rerouted(
    facts: list[CompositionFact],
    source_text: str,
    anchors: list[InventoryAnchor],
):
    result = materialize_candidate(anchors, facts, source_text=source_text)

    populated = [
        item
        for item in result.document["items"]
        if item["Extracted_Data"]["Composition"]["Composition_Observations"]
    ]
    assert [item["Sample_ID"] for item in populated] == ["alloy A [sintered]"]
    assert not any(
        row.code == "microanalysis_table_envelope_owner_recovered"
        for row in result.issues
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


def _numeric_eds_fact(
    location: str = "3",
    *,
    evidence: str | None = None,
    component_count: int = 2,
    measurement: str = "EDS point analysis",
) -> CompositionFact:
    table = evidence or (
        "| Selected area for EDS point analysis |  |  |\n"
        "| --- | --- | --- |\n"
        "|  | 3 | 4 |\n"
        "| C | 0 | 2.3 |\n"
        "| Ni | 61.7 | 2.7 |"
    )
    components = [
        {
            "name_raw": "C",
            "value_kind": "scalar",
            "value_raw": "0",
            "unit_raw": "wt%",
            "data_nature": "reported",
        },
        {
            "name_raw": "Ni",
            "value_kind": "scalar",
            "value_raw": "61.7",
            "unit_raw": "wt%",
            "data_nature": "reported",
        },
    ][:component_count]
    return CompositionFact(
        sample_id_raw=location,
        fact_type="composition_observation",
        data={
            "observation_id": "temporary",
            "source_type": "measured",
            "material_state": "not_reported",
            "sample_id": location,
            "basis": "wt%",
            "component_type": "elemental",
            "components": components,
            "measurement": measurement,
            "raw_expression": "C 0, Ni 61.7 wt%",
            "data_source": "table",
            "source_evidence": [table],
            "note": None,
        },
        source_evidence=[table],
        confidence=0.9,
    )


def _state_anchor(sample: str, temperature: int) -> InventoryAnchor:
    return InventoryAnchor(
        sample_id_raw=sample,
        material_name_raw="alloy 625",
        state_raw=f"sintered at {temperature} °C",
        role="Target",
        data_nature="Experimental",
        source_evidence=[f"{sample} sample sintered at {temperature} °C"],
        confidence=0.95,
    )


def test_numeric_microanalysis_row_routes_to_unique_source_state_owner():
    fact = _numeric_eds_fact()
    source = (
        "EDS analysis of the GA sample sintered at 1300 °C showed that "
        "Point 3 represented the matrix.\n"
        + fact.source_evidence[0]
    )

    result = materialize_candidate(
        [_state_anchor("GA", 1225), _state_anchor("GA", 1300)],
        [fact],
        source_text=source,
    )

    assert [item["Sample_ID"] for item in result.document["items"]] == [
        "GA [sintered at 1300 °C]"
    ]
    observation = result.document["items"][0]["Extracted_Data"]["Composition"][
        "Composition_Observations"
    ][0]
    assert observation["sample_id"] == "Point 3"
    assert observation["material_state"] == "sintered at 1300 °C"
    assert "_microanalysis_owner_recovered" not in observation
    issue = next(
        row
        for row in result.issues
        if row.code == "numeric_microanalysis_owner_recovered"
    )
    assert issue.actual["before_owner"] == "3"
    assert issue.actual["after_owner"] == "GA [sintered at 1300 °C]"
    assert issue.actual["observation_location"] == "Point 3"
    assert issue.actual["facts"] == [fact.model_dump()]
    assert any("Point 3 represented the matrix" in row for row in issue.evidence)


@pytest.mark.parametrize(
    ("fact", "source"),
    [
        (
            _numeric_eds_fact(
                evidence=(
                    "| Selected area for EDS point analysis |  |\n"
                    "| --- | --- |\n"
                    "|  | 4 |\n"
                    "| C | 2.3 |\n"
                    "| Ni | 2.7 |"
                )
            ),
            (
                "EDS analysis of the GA sample sintered at 1300 °C showed "
                "that Point 3 represented the matrix.\n"
                "| Selected area for EDS point analysis |  |\n"
                "| --- | --- |\n"
                "|  | 4 |\n"
                "| C | 2.3 |\n"
                "| Ni | 2.7 |"
            ),
        ),
        (
            _numeric_eds_fact(component_count=1),
            (
                "EDS analysis of the GA sample sintered at 1300 °C showed "
                "that Point 3 represented the matrix.\n"
                "| Selected area for EDS point analysis |  |  |\n"
                "| --- | --- | --- |\n"
                "|  | 3 | 4 |\n"
                "| C | 0 | 2.3 |\n"
                "| Ni | 61.7 | 2.7 |"
            ),
        ),
        (
            _numeric_eds_fact(measurement="fatigue specimen analysis"),
            (
                "Fatigue tests on the GA sample sintered at 1300 °C used "
                "Specimen 3.\n"
                "| Specimen | Stress | Life |\n"
                "| 3 | 536.78 | 1.68e6 |"
            ),
        ),
        (
            _numeric_eds_fact(
                evidence=(
                    "| Mechanical test point | 3 | 4 |\n"
                    "| --- | --- | --- |\n"
                    "| Stress | 500 | 525 |\n"
                    "| Strain | 0.1 | 0.2 |"
                )
            ),
            (
                "The GA sample sintered at 1300 °C was mechanically tested.\n"
                "| Mechanical test point | 3 | 4 |\n"
                "| --- | --- | --- |\n"
                "| Stress | 500 | 525 |\n"
                "| Strain | 0.1 | 0.2 |"
            ),
        ),
    ],
    ids=(
        "missing_numeric_header",
        "single_element",
        "fatigue_table",
        "non_eds_numeric_table",
    ),
)
def test_unsafe_numeric_rows_remain_unresolved(
    fact: CompositionFact, source: str
):
    result = materialize_candidate(
        [_state_anchor("GA", 1225), _state_anchor("GA", 1300)],
        [fact],
        source_text=source,
    )

    assert result.document["items"] == []
    assert any(row.code == "unresolved_sample_alias" for row in result.issues)
    assert not any(
        row.code == "numeric_microanalysis_owner_recovered"
        for row in result.issues
    )


def test_numeric_microanalysis_conflicting_source_owners_remain_unresolved():
    fact = _numeric_eds_fact()
    source = (
        "EDS analysis of the GA sample sintered at 1300 °C showed Point 3.\n"
        "EDS analysis of the WA sample sintered at 1300 °C showed Point 3.\n"
        + fact.source_evidence[0]
    )

    result = materialize_candidate(
        [
            _state_anchor("GA", 1225),
            _state_anchor("GA", 1300),
            _state_anchor("WA", 1225),
            _state_anchor("WA", 1300),
        ],
        [fact],
        source_text=source,
    )

    assert result.document["items"] == []
    assert any(row.code == "unresolved_sample_alias" for row in result.issues)
    assert not any(
        row.code == "numeric_microanalysis_owner_recovered"
        for row in result.issues
    )


def test_numeric_microanalysis_multiple_compatible_targets_remain_unresolved():
    fact = _numeric_eds_fact()
    source = (
        "EDS analysis of the GA sample sintered at 1300 °C showed Point 3.\n"
        + fact.source_evidence[0]
    )

    result = materialize_candidate(
        [
            InventoryAnchor(
                sample_id_raw="GA",
                material_name_raw="alloy 625",
                state_raw="as-sintered at 1300 °C",
                role="Target",
                data_nature="Experimental",
                source_evidence=["GA was as-sintered at 1300 °C"],
                confidence=0.95,
            ),
            InventoryAnchor(
                sample_id_raw="GA",
                material_name_raw="alloy 625",
                state_raw="directly sintered at 1300 °C",
                role="Target",
                data_nature="Experimental",
                source_evidence=["GA was directly sintered at 1300 °C"],
                confidence=0.95,
            ),
        ],
        [fact],
        source_text=source,
    )

    assert result.document["items"] == []
    assert any(row.code == "unresolved_sample_alias" for row in result.issues)
    assert not any(
        row.code == "numeric_microanalysis_owner_recovered"
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


def test_structure_placeholder_canonical_name_does_not_hide_literal_entity():
    fact = _structure_fact("A", "The alloy contained α + β phases")
    fact.data["entities"][0].update(
        {
            "name_raw": "α + β",
            "canonical_name": "unknown_entity",
            "raw_expression": "α + β",
        }
    )

    result = materialize_candidate([_anchor("A")], [fact])

    entity = result.document["items"][0]["Extracted_Data"]["Structure"][
        "Structure_Observations"
    ][0]["entities"][0]
    assert entity["name_raw"] == "α + β"
    assert entity["canonical_name"] is None


def test_qualitative_comparison_structure_is_not_projected_to_both_owners():
    evidence = "Alloy-A had larger alpha colonies than Alloy-B."
    result = materialize_candidate(
        [_anchor("Alloy-A"), _anchor("Alloy-B")],
        [
            _structure_fact("Alloy-A", evidence),
            _structure_fact("Alloy-B", evidence),
        ],
    )

    assert result.document["items"] == []
    assert sum(
        issue.code == "multi_owner_qualitative_projection_quarantined"
        for issue in result.issues
    ) == 2


def test_qualitative_comparison_characterization_is_isolated_with_audit():
    evidence = "EBSD measurements in Alloy-A were finer than Alloy-B."
    result = materialize_candidate(
        [_anchor("Alloy-A"), _anchor("Alloy-B")],
        [
            _characterization("Alloy-A", "EBSD", "EBSD", evidence=evidence),
            _characterization("Alloy-B", "EBSD", "EBSD", evidence=evidence),
        ],
    )

    assert result.document["items"] == []
    assert sum(
        issue.code == "multi_owner_qualitative_projection_quarantined"
        for issue in result.issues
    ) == 2


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


def test_table_phase_analysis_point_cannot_own_sigma_property():
    phase_row = "| D | $ \\sigma $ | 18.6 | 2.4 |"
    phase_anchor = InventoryAnchor(
        sample_id_raw="D",
        material_name_raw="σ",
        state_raw="not_reported",
        role="Target",
        data_nature="Experimental",
        source_evidence=[phase_row],
        confidence=0.9,
    )
    fatigue = _raw_property(
        "Specimen I",
        "stress amplitude",
        "534",
        "The stress amplitude was σ_a = 534 MPa.",
    )
    fatigue.data["unit_raw"] = "MPa"

    result = materialize_candidate(
        [
            InventoryAnchor(
                sample_id_raw="GH4169",
                material_name_raw="GH4169",
                state_raw="heat-treated",
                role="Target",
                data_nature="Experimental",
                source_evidence=["heat-treated GH4169"],
                confidence=0.95,
            ),
            phase_anchor,
        ],
        [
            _structure_fact("GH4169", "GH4169 contained fine grains"),
            _structure_fact("D", phase_row),
            fatigue,
        ],
    )

    assert [item["Sample_ID"] for item in result.document["items"]] == ["GH4169"]
    extracted = result.document["items"][0]["Extracted_Data"]
    assert extracted["Properties"] == []
    assert len(extracted["Structure"]["Structure_Observations"]) == 1
    assert any(
        issue.code == "non_material_item_removed"
        and issue.sample_id_raw == "D"
        for issue in result.issues
    )
    assert any(
        issue.code == "unresolved_sample_alias"
        and issue.sample_id_raw == "Specimen I"
        for issue in result.issues
    )


def test_single_letter_material_sample_with_alloy_table_row_is_preserved():
    row = "| A | Al-10Si-Mg alloy | 534 MPa |"
    anchor = InventoryAnchor(
        sample_id_raw="A",
        material_name_raw="Al-10Si-Mg alloy",
        state_raw="as-built",
        role="Target",
        data_nature="Experimental",
        source_evidence=[row],
        confidence=0.9,
    )
    fact = _raw_property("A", "yield strength", "534", row, source="table")
    fact.data["unit_raw"] = "MPa"

    result = materialize_candidate([anchor], [fact])

    assert [item["Sample_ID"] for item in result.document["items"]] == ["A"]
    properties = result.document["items"][0]["Extracted_Data"]["Properties"]
    assert [(row["property_name_raw"], row["value_raw"]) for row in properties] == [
        ("yield strength", "534")
    ]
    assert not any(
        issue.code == "non_material_item_removed" for issue in result.issues
    )


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


def test_inventory_delay_header_matches_interlayer_delay_state():
    anchor = InventoryAnchor(
        sample_id_raw="120 s Delay",
        material_name_raw="Ti-6Al-4V wall",
        state_raw="120 s interlayer delay",
        role="Target",
        data_nature="Experimental",
        source_evidence=["wall with a 120 s interlayer delay"],
        confidence=0.95,
    )
    fact = _tensile_property(
        "120 s Delay",
        name="yield strength",
        value="859.7 ± 9.17",
        evidence=(
            "| Properties | 120 s Delay |\n"
            "| Yield Stress (MPa) | 859.7 ± 9.17 |"
        ),
        data_source="table",
    )

    result = materialize_candidate([anchor], [fact])

    assert [item["Sample_ID"] for item in result.document["items"]] == [
        "120 s Delay"
    ]
    assert result.document["items"][0]["Extracted_Data"]["Properties"][0][
        "value_raw"
    ] == "859.7 ± 9.17"
    assert not any(
        issue.code == "unresolved_sample_alias" for issue in result.issues
    )


def test_dense_compact_delay_owner_matches_spaced_literal_header():
    anchor = InventoryAnchor(
        sample_id_raw="120s Delay",
        material_name_raw="Ti-6Al-4V wall",
        state_raw="120 s interlayer delay",
        role="Target",
        data_nature="Experimental",
        source_evidence=["wall with a 120 s interlayer delay"],
        confidence=0.95,
    )
    fact = _tensile_property(
        "120s Delay",
        name="yield strength",
        value="859.7 ± 9.17",
        evidence=(
            "| Properties | 120 s Delay |\n"
            "| Yield Stress (MPa) | 859.7 ± 9.17 |"
        ),
        data_source="table",
    )
    fact.data["property_id_candidate"] = "dense-table-cell:test-coordinate"
    fact.data["raw_note"] = "120 s Delay"

    result = materialize_candidate([anchor], [fact])

    assert len(result.document["items"]) == 1
    assert len(result.document["items"][0]["Extracted_Data"]["Properties"]) == 1
    assert not any(
        issue.code
        == "metric_state_owner_without_literal_coordinate_quarantined"
        for issue in result.issues
    )


def test_interlayer_delay_states_do_not_merge_across_numeric_qualifiers():
    delays = ("0", "120", "300")
    anchors = [
        InventoryAnchor(
            sample_id_raw=f"{delay} s Delay",
            material_name_raw="Ti-6Al-4V wall",
            state_raw=f"{delay} s interlayer delay",
            role="Target",
            data_nature="Experimental",
            source_evidence=[f"wall with a {delay} s interlayer delay"],
            confidence=0.95,
        )
        for delay in delays
    ]
    facts = [
        _structure_fact(
            f"{delay} s Delay",
            f"The {delay} s Delay wall contained fine grains",
        )
        for delay in delays
    ]

    result = materialize_candidate(anchors, facts)

    assert [item["Sample_ID"] for item in result.document["items"]] == [
        "0 s Delay",
        "120 s Delay",
        "300 s Delay",
    ]
    assert all(
        len(item["Extracted_Data"]["Structure"]["Structure_Observations"]) == 1
        for item in result.document["items"]
    )


def test_experimental_delay_anchor_wins_same_owner_nature_tie_for_tensile():
    anchors = [
        InventoryAnchor(
            sample_id_raw="120 s Delay",
            material_name_raw="Ti-6Al-4V wall",
            state_raw="120 s interlayer delay",
            role="Target",
            data_nature=data_nature,
            source_evidence=[evidence],
            confidence=0.95,
        )
        for data_nature, evidence in (
            ("Computed", "Energy balance over build (120 s Delay)"),
            ("Experimental", "wall with a 120 s interlayer delay"),
        )
    ]
    fact = _tensile_property(
        "120 s Delay",
        name="UTS",
        value="959 ± 5.31",
        evidence="| Properties | 120 s Delay |\n| UTS (MPa) | 959 ± 5.31 |",
        data_source="table",
    )

    result = materialize_candidate(anchors, [fact])

    assert len(result.document["items"]) == 1
    assert result.document["items"][0]["Sample_ID"] == "120 s Delay"
    assert result.document["items"][0]["Data_Nature"] == "Experimental"
    assert len(result.document["items"][0]["Extracted_Data"]["Properties"]) == 1


def test_metric_delay_state_rejects_nonliteral_cross_chunk_structure_projection():
    anchors = [
        InventoryAnchor(
            sample_id_raw=f"{delay} s Delay",
            material_name_raw="Ti-6Al-4V wall",
            state_raw=f"{delay} s interlayer delay",
            role="Target",
            data_nature="Experimental",
            source_evidence=[f"wall with a {delay} s interlayer delay"],
            confidence=0.95,
        )
        for delay in ("0", "300")
    ]
    facts = [
        _structure_fact(
            "0 s Delay",
            "The scalloping was evident for the scenario of the shortest delay.",
        ),
        _structure_fact(
            "300 s Delay",
            "The longer delay produced uniform cooling rates along the wall height.",
        ),
    ]

    result = materialize_candidate(anchors, facts)

    assert result.document["items"] == []
    quarantines = [
        issue
        for issue in result.issues
        if issue.code
        == "metric_state_owner_without_literal_coordinate_quarantined"
    ]
    assert len(quarantines) == 2
    assert all(issue.actual["fact"] for issue in quarantines)
    assert all(not issue.actual["retained_targets"] for issue in quarantines)


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


def test_state_backed_measured_observation_keeps_analytical_owner():
    """Do not fold an exact fracture-surface composition row into its base sample."""

    base = _anchor("Binder Jetting")
    observation_anchor = InventoryAnchor(
        sample_id_raw="binder jetting fracture surface",
        material_name_raw=None,
        state_raw="fracture surface",
        role="Target",
        data_nature="Experimental",
        source_evidence=["Chemical composition of binder jetting fracture surface"],
        confidence=0.95,
    )
    evidence = (
        "| Element | Ni | Cr | Mo |\n"
        "| Wt (%) | 54.21 | 32.34 | 4.57 |"
    )
    fact = CompositionFact(
        sample_id_raw="binder jetting fracture surface",
        fact_type="composition_observation",
        data={
            "source_type": "measured",
            "basis": "wt%",
            "component_type": "elemental",
            "components": [
                {"name_raw": "Ni", "value_kind": "scalar", "value_raw": "54.21", "unit_raw": "wt%"}
            ],
            "material_state": "fracture surface",
            "sample_id": "binder jetting fracture surface",
            "data_source": "table",
            "observation_id": "temporary",
            "raw_expression": "Ni 54.21 wt%",
            "measurement": None,
            "note": None,
            "source_evidence": [evidence],
            "confidence": 0.95,
        },
        source_evidence=[evidence],
        confidence=0.95,
    )

    result = materialize_candidate([base, observation_anchor], [fact], source_text=evidence)

    items = {item["Sample_ID"]: item for item in result.document["items"]}
    assert "binder jetting fracture surface" in items
    assert "Binder Jetting" not in items
    assert items["binder jetting fracture surface"]["Extracted_Data"][
        "Composition"
    ]["Composition_Observations"]


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


def test_composite_state_codes_keep_same_sample_states_distinct():
    """HIP/HT composite coordinates must not collapse to one base sample."""

    first_state = "HIP2 + HT2"
    second_state = "as-sintered + HIP2 + HT2"
    first = _tensile_property(
        "MAR M247",
        evidence=f"MAR M247 {first_state} had a UTS of 1115 MPa.",
        value="1115",
    )
    first.data["material_state"] = first_state
    second = _tensile_property(
        "MAR M247",
        evidence=f"MAR M247 {second_state} had a UTS of 1025 MPa.",
        value="1025",
    )
    second.data["material_state"] = second_state
    anchors = [
        InventoryAnchor(
            sample_id_raw="MAR M247",
            material_name_raw="MAR-M247 superalloy",
            state_raw=state,
            role="Target",
            data_nature="Experimental",
            source_evidence=[f"MAR M247 {state}"],
            confidence=0.9,
        )
        for state in (first_state, second_state)
    ]

    result = materialize_candidate(anchors, [first, second])

    values_by_owner = {
        item["Sample_ID"]: [
            row["value_raw"] for row in item["Extracted_Data"]["Properties"]
        ]
        for item in result.document["items"]
    }
    assert values_by_owner == {
        f"MAR M247 [{first_state}]": ["1115"],
        f"MAR M247 [{second_state}]": ["1025"],
    }
    assert not any(
        issue.code == "shared_fact_routed" for issue in result.issues
    )


def test_numbered_hip_states_keep_independent_owner_coordinates():
    """HIP1/HIP2 must not collapse through the broad ``hip`` descriptor."""

    anchors = [
        InventoryAnchor(
            sample_id_raw="MAR-M247",
            material_name_raw="MAR-M247",
            state_raw=state,
            role="Target",
            data_nature="Experimental",
            source_evidence=[f"MAR-M247 specimens in {state}"],
            confidence=0.95,
        )
        for state in ("HIP1", "HIP2")
    ]

    expanded, aliases = _expand_distinct_state_anchors(anchors)
    displays = {row.sample_id_raw for row in expanded}
    assert displays == {
        "MAR-M247",
        "MAR-M247 [HIP1]",
        "MAR-M247 [HIP2]",
    }
    assert aliases["MAR-M247"] == displays - {"MAR-M247"}
    assert _state_composite_discriminator("HIP1") == ("hip1",)
    assert _state_composite_discriminator("HIP2") == ("hip2",)

    # The full identity index must retain the two generated state owners as
    # separate canonical targets after cross-chunk alias reconciliation.
    index = _build_identity_index(anchors, [])
    hip1 = index.resolve_exact("MAR-M247 [HIP1]")
    hip2 = index.resolve_exact("MAR-M247 [HIP2]")
    assert len(hip1) == len(hip2) == 1
    assert hip1 != hip2


def test_numbered_heat_treatment_states_keep_all_four_coordinates_distinct():
    anchors = [
        InventoryAnchor(
            sample_id_raw="MAR-M247",
            material_name_raw="MAR-M247",
            state_raw=f"HT{number}",
            role="Target",
            data_nature="Experimental",
            source_evidence=[f"MAR-M247 after HT{number}"],
            confidence=0.95,
        )
        for number in range(1, 5)
    ]

    expanded, _ = _expand_distinct_state_anchors(anchors)
    assert {
        row.sample_id_raw for row in expanded
    } == {
        "MAR-M247",
        *(f"MAR-M247 [HT{number}]" for number in range(1, 5)),
    }


def test_processing_table_values_stay_with_numbered_hip_owner():
    """Distinct HIP table columns are coordinates, not shared projections."""

    source = (
        "| Cycle | HIP1 | HIP2 |\n"
        "| --- | --- | --- |\n"
        "| Pressure | 1000 bar | 1500 bar |\n"
        "| Temperature | 1120 ^\\circC | 1180 ^\\circC |\n"
        "| Holding time | 4 h | 4 h |"
    )
    table_rows = [
        "| Pressure | 1000 bar | 1500 bar |",
        "| Temperature | 1120 ^\\circC | 1180 ^\\circC |",
        "| Holding time | 4 h | 4 h |",
    ]

    def process(owner: str, pressure: str, temperature: str) -> ProcessingFact:
        parameters = [
            {
                "parameter_name_raw": "Pressure",
                "value_raw": pressure,
                "unit_raw": "bar",
                "source_evidence": table_rows[0],
            },
            {
                "parameter_name_raw": "Temperature",
                "value_raw": temperature,
                "unit_raw": "^\\circC",
                "source_evidence": table_rows[1],
            },
            {
                "parameter_name_raw": "Holding time",
                "value_raw": "4 h",
                "unit_raw": "h",
                "source_evidence": table_rows[2],
            },
        ]
        return ProcessingFact(
            sample_id_raw=owner,
            fact_type="process_stage",
            data={
                "candidate_stage_id": "temporary",
                "stage_index_candidate": 0,
                "process_name_raw": "HIP",
                "process_code_candidate": None,
                "process_role_candidate": None,
                "parameters_raw": parameters,
                "source_evidence": table_rows,
                "confidence": 0.95,
            },
            source_evidence=table_rows,
            confidence=0.95,
        )

    anchors = [
        InventoryAnchor(
            sample_id_raw=sample,
            material_name_raw="MAR-M247",
            state_raw=state,
            role="Target",
            data_nature="Experimental",
            source_evidence=[f"MAR-M247 {state}"],
            confidence=0.95,
        )
        for sample, state in (
            ("MAR-M247", "HIP1"),
            ("MAR-M247", "HIP2"),
            ("HIP1", "HIP1"),
            ("HIP2", "HIP2"),
        )
    ]
    result = materialize_candidate(
        anchors,
        [process("HIP1", "1000 bar", "1120 ^\\circC"), process("HIP2", "1500 bar", "1180 ^\\circC")],
        source_text=source,
    )

    values = {}
    for item in result.document["items"]:
        pressure = [
            parameter["value_raw"]
            for stage in item["Extracted_Data"]["Processing"]["Process_Route"][
                "candidate_stages"
            ]
            for parameter in stage.get("parameters_raw", [])
            if parameter.get("parameter_name_raw") == "Pressure"
        ]
        if pressure:
            values[item["Sample_ID"]] = pressure
    assert values == {"HIP1": ["1000 bar"], "HIP2": ["1500 bar"]}
    assert not any(
        issue.code == "shared_owner_projection_quarantined" for issue in result.issues
    )


def test_numeric_tensile_table_row_recovers_unique_material_and_state_owner():
    evidence = (
        "| Samples | Yield stress [MPa] | UTS [MPa] | Elongation [%] |\n"
        "| WA sample sintered at 1270 °C | 287 ± 11 | 386 ± 15 | 11.6 ± 2.2 |"
    )
    fact = _tensile_property(
        "WA sample sintered at 1270 °C",
        evidence=evidence,
    )
    fact.data["property_name_raw"] = "yield stress"
    fact.data["value_raw"] = "287 ± 11"
    fact.data["data_source"] = "table"

    result = materialize_candidate(
        [
            _anchor("WA", "sintered at 1270 °C"),
            _anchor("GA", "sintered at 1270 °C"),
        ],
        [fact],
    )

    assert [row["Sample_ID"] for row in result.document["items"]] == [
        "WA [sintered at 1270 °C]"
    ]
    prop = result.document["items"][0]["Extracted_Data"]["Properties"][0]
    assert prop["value_raw"] == "287 ± 11"
    issue = next(
        row for row in result.issues if row.code == "numeric_tensile_owner_recovered"
    )
    assert issue.actual["before_owner"] == "WA sample sintered at 1270 °C"
    assert issue.actual["after_owner"] == "WA [sintered at 1270 °C]"
    assert issue.actual["rule"] == "complete_table_row_owner_state"
    assert issue.actual["fact"] == fact.model_dump()


def test_dense_source_table_cells_complete_both_target_owner_columns():
    prose = "The UTS increased from 890 MPa to 900 MPa for the second alloy."
    table = (
        "| Property | Alloy-A | Alloy-B |\n"
        "| --- | --- | --- |\n"
        "| UTS (MPa) | 890.0 ± 1.0 | 900.0 ± 1.0 |"
    )
    fact = _tensile_property(
        "not_reported",
        evidence=prose,
        value="900",
        name="UTS",
        data_source="text",
    )
    result = materialize_candidate(
        [_material_anchor("Alloy-A"), _material_anchor("Alloy-B")],
        [fact],
        source_text=f"## Results\n\n{prose}\n\n{table}\n",
    )
    assert [row["Sample_ID"] for row in result.document["items"]] == [
        "Alloy-A",
        "Alloy-B",
    ]
    assert [
        row["Extracted_Data"]["Properties"][0]["value_raw"]
        for row in result.document["items"]
    ] == ["890.0 ± 1.0", "900.0 ± 1.0"]
    assert len(
        [
            row
            for row in result.issues
            if row.code == "dense_tensile_table_cell_recovered"
        ]
    ) == 2
    issue = next(
        row for row in result.issues if row.code == "numeric_tensile_owner_recovered"
    )
    assert issue.actual["rule"] == "source_table_value_owner"
    assert issue.actual["after_owner"] == "Alloy-B"


def test_dense_leading_percent_cell_enriches_latex_existing_fact_once():
    table = (
        '<table><tr><td></td><td colspan="2">LPBF</td></tr>'
        '<tr><td></td><td>X</td><td>Z</td></tr>'
        '<tr><td>% Elongation (at break)</td>'
        '<td>62.34 \\pm 1.98</td><td>56.3 \\pm 6.24</td></tr></table>'
    )
    existing = _tensile_property(
        "LPBF / X",
        name="% Elongation (at break)",
        value=r"62.34 \pm 1.98",
        unit="%",
        data_source="table",
        evidence=table,
    )

    result = materialize_candidate(
        [_material_anchor("LPBF / X"), _material_anchor("LPBF / Z")],
        [existing],
        source_text=table,
    )

    values = [
        (item["Sample_ID"], prop["value_raw"])
        for item in result.document["items"]
        for prop in item["Extracted_Data"]["Properties"]
    ]
    assert values == [
        ("LPBF / X", r"62.34 \pm 1.98"),
        ("LPBF / Z", "56.3 ± 6.24"),
    ]
    x_audit = next(
        row
        for row in result.issues
        if row.code == "dense_tensile_table_cell_recovered"
        and row.sample_id_raw == "LPBF / X"
    )
    assert x_audit.actual["reason"] == "existing_coordinate_enriched"


def test_dense_orientation_table_recovers_explicit_elastic_modulus_cells():
    table = (
        '<table><tr><td></td><td colspan="2">LPBF</td></tr>'
        '<tr><td></td><td>X</td><td>Z</td></tr>'
        '<tr><td>Modulus of elasticity (GPa)</td>'
        '<td>0.561 \\pm 0.014</td><td>0.539 \\pm 0.058</td></tr></table>'
    )

    result = materialize_candidate(
        [_material_anchor("LPBF / X"), _material_anchor("LPBF / Z")],
        [],
        source_text=table,
    )

    properties = [
        (
            item["Sample_ID"],
            prop["property_name_raw"],
            prop["value_raw"],
            prop["test_condition_raw"],
            prop["test_specimen_raw"],
        )
        for item in result.document["items"]
        for prop in item["Extracted_Data"]["Properties"]
    ]
    assert properties == [
        ("LPBF / X", "Elastic Modulus", "0.561 ± 0.014", "", "X"),
        ("LPBF / Z", "Elastic Modulus", "0.539 ± 0.058", "", "Z"),
    ]
    assert sum(
        row.code == "dense_tensile_table_cell_recovered"
        for row in result.issues
    ) == 2


def test_dense_elastic_modulus_cells_bind_one_explicit_global_tensile_protocol():
    source = (
        "Tensile testing was performed on all samples fabricated by LPBF. "
        "Specimens were tested using a strain rate of 0.005 mm/min/min.\n"
        '<table><tr><td></td><td colspan="2">LPBF</td></tr>'
        '<tr><td></td><td>X</td><td>Z</td></tr>'
        '<tr><td>Modulus of elasticity (GPa)</td>'
        '<td>0.561 \\pm 0.014</td><td>0.539 \\pm 0.058</td></tr></table>'
    )

    result = materialize_candidate(
        [_material_anchor("LPBF / X"), _material_anchor("LPBF / Z")],
        [],
        source_text=source,
    )

    properties = [
        prop
        for item in result.document["items"]
        for prop in item["Extracted_Data"]["Properties"]
    ]
    assert len(properties) == 2
    assert {
        prop["test_condition_raw"] for prop in properties
    } == {"strain rate of 0.005 mm/min/min"}
    assert sum(
        row.code == "dense_tensile_protocol_recovered"
        for row in result.issues
    ) == 2


def test_dense_core_tensile_cells_bind_one_explicit_global_tensile_protocol():
    source = (
        "Tensile testing was performed on all six samples fabricated with all "
        "three technologies. Specimens were tested using a strain rate of "
        "0.005 mm/min/min.\n"
        '<table><tr><td></td><td colspan="2">LPBF</td></tr>'
        '<tr><td></td><td>X</td><td>Z</td></tr>'
        '<tr><td>UTS (MPa)</td><td>906</td><td>842</td></tr></table>'
    )

    result = materialize_candidate(
        [_material_anchor("LPBF / X"), _material_anchor("LPBF / Z")],
        [],
        source_text=source,
    )

    properties = [
        prop
        for item in result.document["items"]
        for prop in item["Extracted_Data"]["Properties"]
    ]
    assert len(properties) == 2
    assert {
        prop["test_condition_raw"] for prop in properties
    } == {"strain rate of 0.005 mm/min/min"}
    assert sum(
        row.code == "dense_tensile_protocol_recovered"
        for row in result.issues
    ) == 2
    assert not any(
        row.code == "property_test_context_shared_scope_quarantined"
        for row in result.issues
    )
    assert not any(
        row.code == "property_test_context_shared_scope_audit"
        for row in result.issues
    )


def test_dense_core_tensile_protocol_requires_explicit_global_scope():
    source = (
        "Tensile tests were performed using a strain rate of 0.005 mm/min/min.\n"
        '<table><tr><td></td><td colspan="2">LPBF</td></tr>'
        '<tr><td></td><td>X</td><td>Z</td></tr>'
        '<tr><td>UTS (MPa)</td><td>906</td><td>842</td></tr></table>'
    )

    result = materialize_candidate(
        [_material_anchor("LPBF / X"), _material_anchor("LPBF / Z")],
        [],
        source_text=source,
    )

    properties = [
        prop
        for item in result.document["items"]
        for prop in item["Extracted_Data"]["Properties"]
    ]
    assert len(properties) == 2
    assert all(not prop["test_condition_raw"] for prop in properties)
    assert not any(
        row.code == "dense_tensile_protocol_recovered"
        for row in result.issues
    )


def test_dense_core_tensile_protocol_fails_closed_for_two_global_events():
    source = (
        "Tensile testing was performed on all samples at a strain rate of "
        "0.005 mm/min/min.\n"
        "A second set of tensile tests was performed on all samples at a "
        "strain rate of 5 mm/min.\n"
        '<table><tr><td></td><td colspan="2">LPBF</td></tr>'
        '<tr><td></td><td>X</td><td>Z</td></tr>'
        '<tr><td>UTS (MPa)</td><td>906</td><td>842</td></tr></table>'
    )

    result = materialize_candidate(
        [_material_anchor("LPBF / X"), _material_anchor("LPBF / Z")],
        [],
        source_text=source,
    )

    properties = [
        prop
        for item in result.document["items"]
        for prop in item["Extracted_Data"]["Properties"]
    ]
    assert len(properties) == 2
    assert all(not prop["test_condition_raw"] for prop in properties)
    assert not any(
        row.code == "dense_tensile_protocol_recovered"
        for row in result.issues
    )


def test_dense_core_tensile_protocol_is_not_applied_to_reference_owner():
    source = (
        "Tensile testing was performed on all samples. Specimens were tested "
        "using a strain rate of 0.005 mm/min/min.\n"
        "The reference alloy had an ultimate tensile strength of 900 MPa."
    )
    reference = _tensile_property(
        "Reference alloy",
        evidence="The reference alloy had an ultimate tensile strength of 900 MPa.",
    )
    reference.data["property_id_candidate"] = "dense-table-cell:reference"

    result = materialize_candidate(
        [
            InventoryAnchor(
                sample_id_raw="Reference alloy",
                material_name_raw="Reference alloy",
                state_raw=None,
                role="Reference",
                data_nature="Literature_Experimental",
                source_evidence=[
                    "The reference alloy had an ultimate tensile strength of 900 MPa."
                ],
                confidence=0.9,
            )
        ],
        [reference],
        source_text=source,
    )

    prop = result.document["items"][0]["Extracted_Data"]["Properties"][0]
    assert prop["test_condition_raw"] is None
    assert not any(
        row.code == "dense_tensile_protocol_recovered"
        for row in result.issues
    )


def test_global_protocol_is_not_projected_to_uncoordinated_core_tensile_prose():
    source = (
        "Tensile testing was performed on all samples. Specimens were tested "
        "using a strain rate of 0.005 mm/min/min. "
        "Alloy A had an ultimate tensile strength of 900 MPa."
    )
    fact = _tensile_property(
        "Alloy A",
        evidence="Alloy A had an ultimate tensile strength of 900 MPa.",
    )

    result = materialize_candidate(
        [_material_anchor("Alloy A"), _material_anchor("Alloy B")],
        [fact],
        source_text=source,
    )

    prop = next(
        prop
        for item in result.document["items"]
        if item["Sample_ID"] == "Alloy A"
        for prop in item["Extracted_Data"]["Properties"]
    )
    assert prop["test_condition_raw"] is None
    assert not any(
        row.code == "dense_tensile_protocol_recovered"
        for row in result.issues
    )


def test_dense_orientation_table_recovers_global_material_state_owner_coordinates():
    source = (
        "Inconel 625 round bars were built by LPBF in horizontal (X) and "
        "vertical (Z) directions.\n"
        "## 3.2. Post-processing\n\n"
        "All as-fabricated cylindrical samples underwent post-fabrication hot "
        "isostatic pressing (HIPing) for 3 h at 1163 °C and 102 MPa. HIPed "
        "samples were then machined to the required specifications.\n"
        "Tensile testing was performed on all samples fabricated by LPBF. "
        "Specimens were tested using a strain rate of 0.005 mm/min/min.\n"
        "Average mechanical properties of all samples after tensile testing.\n"
        '<table><tr><td></td><td colspan="2">LPBF</td></tr>'
        '<tr><td></td><td>X</td><td>Z</td></tr>'
        '<tr><td>UTS (GPa)</td><td>0.906 \\pm 0.028</td>'
        '<td>0.842 \\pm 0.029</td></tr></table>'
    )
    anchors = [
        InventoryAnchor(
            sample_id_raw="Inconel 625",
            material_name_raw="Inconel 625",
            state_raw=None,
            role="Target",
            data_nature="Experimental",
            source_evidence=["Inconel 625 round bars were built by LPBF"],
            confidence=0.98,
        ),
        _anchor("LPBF / X"),
        _anchor("LPBF / Z"),
    ]
    x_fact = _tensile_property(
        "LPBF / X",
        name="Ultimate Tensile Strength",
        value=r"0.906 \pm 0.028",
        unit="GPa",
        condition="X orientation\n\nstrain rate of 0.005 mm/min/min",
        data_source="table",
        evidence=source,
    )
    z_fact = _tensile_property(
        "LPBF / Z",
        name="Ultimate Tensile Strength",
        value=r"0.842 \pm 0.029",
        unit="GPa",
        condition="Z orientation\n\nstrain rate of 0.005 mm/min/min",
        data_source="table",
        evidence=source,
    )

    result = materialize_candidate(
        anchors,
        [x_fact, z_fact],
        source_text=source,
    )

    assert [item["Sample_ID"] for item in result.document["items"]] == [
        "Inconel 625 / LPBF tensile specimen [HIPed] / X",
        "Inconel 625 / LPBF tensile specimen [HIPed] / Z",
    ]
    for item in result.document["items"]:
        # Owner enrichment must not synthesize Composition-axis content.
        assert item["Extracted_Data"]["Composition"] == {
            "Composition_Text": {
                "original": "not_reported",
                "simplified": "not_reported",
            },
            "Composition_Observations": [],
        }
        prop = item["Extracted_Data"]["Properties"][0]
        assert prop["test_condition_raw"] == "strain rate of 0.005 mm/min/min"
        assert prop["test_specimen_raw"] in {"X", "Z"}
    assert sum(
        issue.code == "dense_tensile_owner_context_reconciled"
        for issue in result.issues
    ) == 2
    assert any(
        issue.code == "dense_tensile_orientation_condition_reconciled"
        for issue in result.issues
    )


def test_dense_orientation_owner_context_fails_closed_for_multiple_materials():
    source = (
        "All as-fabricated samples underwent HIPing. Tensile testing was "
        "performed on all samples.\n"
        '<table><tr><td></td><td colspan="2">LPBF</td></tr>'
        '<tr><td></td><td>X</td><td>Z</td></tr>'
        '<tr><td>UTS (MPa)</td><td>906</td><td>842</td></tr></table>'
    )
    anchors = [
        InventoryAnchor(
            sample_id_raw=material,
            material_name_raw=material,
            state_raw=None,
            role="Target",
            data_nature="Experimental",
            source_evidence=[material],
            confidence=0.98,
        )
        for material in ("Inconel 625", "Haynes 282")
    ]
    anchors.extend((_anchor("LPBF / X"), _anchor("LPBF / Z")))

    result = materialize_candidate(anchors, [], source_text=source)

    assert [item["Sample_ID"] for item in result.document["items"]] == [
        "LPBF / X",
        "LPBF / Z",
    ]
    issue = next(
        row
        for row in result.issues
        if row.code == "dense_tensile_owner_context_ambiguous"
    )
    assert issue.actual["material_candidates"] == ["Haynes 282", "Inconel 625"]
    assert issue.actual["owner_reassigned"] is False


def test_dense_delay_table_collapses_case_and_spacing_owner_aliases():
    table = """
| Properties | 0 s Delay | 120 s Delay | 300 s Delay |
| --- | --- | --- | --- |
| Yield Stress (MPa) | 817 ± 8.68 | 859.7 ± 9.17 | 825.3 ± 3.10 |
| UTS (MPa) | 914.9 ± 10.89 | 959 ± 5.31 | 927.5 ± 5.86 |
| % Elongation | 14.5 ± 5.17 | 7.5 ± 2.09 | 14.83 ± 1.33 |
"""
    anchors = [
        InventoryAnchor(
            sample_id_raw=sample,
            material_name_raw="Ti-6Al-4V",
            state_raw=state,
            role="Target",
            data_nature="Experimental",
            source_evidence=[sample],
            confidence=0.95,
        )
        for sample, state in (
            ("0s Delay", "as-built"),
            ("0 s Delay", "as-deposited"),
            ("120s Delay", "as-built"),
            ("120 s Delay", "as-deposited"),
            ("300s Delay", "as-built"),
            ("300 s Delay", "as-deposited"),
        )
    ]

    result = materialize_candidate(anchors, [], source_text=table)

    properties = [
        (item["Sample_ID"], prop["property_name_raw"], prop["value_raw"])
        for item in result.document["items"]
        for prop in item["Extracted_Data"]["Properties"]
    ]
    assert len(properties) == 9
    assert {owner for owner, _name, _value in properties} == {
        "0 s Delay",
        "120 s Delay",
        "300 s Delay",
    }
    assert sum(
        row.code == "dense_tensile_table_cell_recovered"
        for row in result.issues
    ) == 9


def test_source_table_owner_precedes_generic_sibling_consensus():
    """A unique table coordinate must beat a generic same-block consensus."""

    index = _IdentityIndex()
    base = index.add_primary("Ti-6Al-4V")
    assert base is not None
    index.anchors[base] = []
    for label in ("Ti-6Al-4V-0", "Ti-6Al-4V-120", "Ti-6Al-4V-300"):
        target = index.add_primary(label)
        assert target is not None
        index.anchors[target] = []
        index.state_family_base[target] = base
        index.labels[target][label] += 1

    evidence = (
        "The yield strength was 859 MPa and the ultimate tensile strength was "
        "914 MPa."
    )
    source_text = (
        evidence
        + "\n\n| Property | Ti-6Al-4V-0 | Ti-6Al-4V-120 | Ti-6Al-4V-300 |\n"
        "| --- | --- | --- | --- |\n"
        "| Yield Strength (MPa) | 817 ± 8.68 | 859.7 ± 9.17 | 825.3 ± 3.10 |"
    )
    yield_fact = _tensile_property(
        "Ti-6Al-4V", name="yield strength", value="859", evidence=evidence
    )
    uts_fact = _tensile_property(
        "Ti-6Al-4V",
        name="ultimate tensile strength",
        value="914",
        evidence=evidence,
    )

    recovered, issues = _recover_numeric_tensile_context_owners(
        index, [yield_fact, uts_fact], source_text
    )

    yield_after = next(row for row in recovered if row.data["value_raw"] == "859")
    assert yield_after.sample_id_raw == "Ti-6Al-4V-120"
    issue = next(
        row
        for row in issues
        if row.actual.get("fact", {}).get("data", {}).get("value_raw") == "859"
    )
    assert issue.actual["rule"] == "source_table_value_owner"


def test_static_tensile_owner_audit_uses_proven_family_on_state_key_collision():
    """An existing primary state key must not break static-owner recovery."""

    index = _IdentityIndex()
    base = index.add_primary("N1")
    state_owner = index.add_primary("N1-CR")
    assert base is not None and state_owner is not None
    index.anchors[base] = [
        InventoryAnchor(
            sample_id_raw="N1",
            material_name_raw="N1 alloy",
            state_raw="CR",
            role="Target",
            data_nature="Experimental",
            source_evidence=["N1 alloy in the CR state"],
            confidence=0.9,
        )
    ]
    index.anchors[state_owner] = [
        InventoryAnchor(
            sample_id_raw="N1-CR",
            material_name_raw="N1-CR",
            state_raw=None,
            role="Target",
            data_nature="Experimental",
            source_evidence=["N1-CR sheet"],
            confidence=0.9,
        )
    ]
    protocol = (
        "The N1 alloy in the CR state was tested in room-temperature tensile "
        "tests at a strain rate of 1e-3 s-1."
    )
    evidence = "The tensile results show a yield strength of 775 MPa."
    fact = _tensile_property(
        "not_reported",
        name="yield strength",
        value="775",
        evidence=evidence,
    )

    recovered, issues = _recover_numeric_tensile_context_owners(
        index,
        [fact],
        f"{protocol}\n\n## Results\n\n{evidence}",
    )

    assert recovered[0].sample_id_raw == "N1-CR"
    issue = next(
        row for row in issues if row.code == "numeric_tensile_owner_recovered"
    )
    assert issue.actual["rule"] == "unique_current_study_static_tensile_protocol"
    assert issue.evidence["owner_family"] == "N1"
    assert issue.evidence["owner_labels"] == ["N1"]


def test_source_table_rounding_merges_condition_qualified_prose_projection():
    """An integer prose headline is folded into its precise table statistic."""

    index = _IdentityIndex()
    base = index.add_primary("Ti-6Al-4V")
    owner = index.add_primary("Ti-6Al-4V-120")
    assert base is not None and owner is not None
    index.anchors[base] = []
    index.anchors[owner] = [
        InventoryAnchor(
            sample_id_raw="Ti-6Al-4V-120",
            material_name_raw="Ti-6Al-4V",
            state_raw="120 s Delay",
            role="Target",
            data_nature="Experimental",
            source_evidence=["120 s Delay"],
            confidence=0.9,
        )
    ]
    index.state_family_base[owner] = base
    index.labels[owner]["Ti-6Al-4V-120"] += 1
    index.labels[owner]["120 s Delay"] += 1
    index.add_alias("120 s Delay", owner)

    prose = _tensile_property(
        "120 s Delay",
        name="yield strength",
        value="859",
        condition="interlayer delay: 120 s",
        evidence="The yield strength increased to 859 MPa.",
    )
    table = _table_tensile_property(
        "120 s Delay",
        "859.7 ± 9.17",
        (
            "| Properties | 0 s Delay | 120 s Delay | 300 s Delay |\n"
            "| --- | --- | --- | --- |\n"
            "| Yield Stress (MPa) | 817 ± 8.68 | 859.7 ± 9.17 | 825.3 ± 3.10 |"
        ),
        name="Yield Stress (MPa)",
    )

    recovered, issues = _deduplicate_tensile_precision_evidence(
        index,
        [prose, table],
        source_text="\n".join(table.source_evidence),
    )

    assert [row.data["value_raw"] for row in recovered] == ["859.7 ± 9.17"]
    assert any(
        row.code == "tensile_precision_duplicate_merged"
        and row.actual["removed_fact"]["data"]["value_raw"] == "859"
        for row in issues
    )


def _table_tensile_property(
    sample: str,
    value: str,
    evidence: str,
    *,
    name: str = "yield strength",
    data_source: str = "table",
    test_standard: str | None = None,
) -> PropertyFact:
    fact = _tensile_property(sample, evidence=evidence)
    fact.data.update(
        {
            "property_name_raw": name,
            "value_raw": value,
            "unit_raw": "%" if "elongation" in name.casefold() else "MPa",
            "data_source": data_source,
            "test_standard_raw": test_standard,
        }
    )
    return fact


def _material_anchor(
    sample: str,
    *,
    material: str = "Ti-6Al-4V",
    state: str | None = None,
) -> InventoryAnchor:
    return InventoryAnchor(
        sample_id_raw=sample,
        material_name_raw=material,
        state_raw=state,
        role="Target",
        data_nature="Experimental",
        source_evidence=[sample],
        confidence=0.9,
    )


def _reference_material_anchor(
    sample: str,
    *,
    material: str,
    evidence: str,
    state: str | None = None,
) -> InventoryAnchor:
    return InventoryAnchor(
        sample_id_raw=sample,
        material_name_raw=material,
        state_raw=state,
        role="Reference",
        data_nature="Literature_Experimental",
        source_evidence=[evidence],
        confidence=0.9,
    )


def _same_owner_complete_tensile_bundle(
    sample: str,
    values: tuple[str, str, str],
    *,
    evidence: str,
    evidence_unit_id: str,
    condition: str | None = "room temperature",
    elongation_name: str = "elongation",
) -> list[PropertyFact]:
    rows: list[PropertyFact] = []
    for name, value, unit in zip(
        ("yield strength", "ultimate tensile strength", elongation_name),
        values,
        ("MPa", "MPa", "%"),
        strict=True,
    ):
        fact = _tensile_property(
            sample,
            condition=condition,
            evidence=evidence,
            value=value,
            name=name,
            unit=unit,
            data_source="text",
        )
        rows.append(
            fact.model_copy(update={"evidence_unit_id": evidence_unit_id})
        )
    return rows


def test_cited_tensile_value_cell_gets_independent_reference_owner():
    evidence = (
        "| Properties | Wrought | WAAM |\n"
        "| Yield Strength (MPa) | 948 [37] | 856 ± 16 [39] |"
    )
    fact = _table_tensile_property(
        "Wrought", "948", evidence, data_source="unknown"
    )

    result = materialize_candidate(
        [_material_anchor("Wrought", state="wrought")], [fact]
    )

    assert [row["Sample_ID"] for row in result.document["items"]] == [
        "Wrought [37] [reference]"
    ]
    item = result.document["items"][0]
    assert item["Role"] == "Reference"
    assert item["Data_Nature"] == "Literature_Experimental"
    assert item["Extracted_Data"]["Properties"][0]["value_raw"] == "948"
    issue = next(
        row
        for row in result.issues
        if row.code == "reference_tensile_owner_recovered"
    )
    assert issue.actual["before_owner"] == "Wrought"
    assert issue.actual["after_owner"] == "Wrought [37] [reference]"
    assert issue.actual["marker"] == "[37]"
    assert issue.actual["selected_column"] == 1
    assert issue.actual["fact"] == fact.model_dump()


def test_dense_cited_comparison_table_recovers_only_literal_table_scope(
    monkeypatch,
):
    monkeypatch.setenv("KNOWMAT2_ALPHA25_OWNER_STATE_CONDITION_V202", "1")
    monkeypatch.setenv(
        "KNOWMAT2_ALPHA25_SOURCE_COORDINATE_PRECISION_V202", "1"
    )
    table = (
        "| Properties | Wrought | WAAM | WLAM | WEBAM |\n"
        "| --- | --- | --- | --- | --- |\n"
        "| Yield Strength (MPa) | 948 [37] | 856 [39] | "
        "825 [43] | 846 [44] |"
    )
    source = (
        "All current-study tensile tests used ASTM E8 at 0.005 min^-1.\n\n"
        "Table 3. Mechanical properties of wrought and wire-feed AM samples.\n\n"
        f"{table}"
    )
    fact = _table_tensile_property(
        "Wrought", "948", table, data_source="unknown"
    )
    fact.data["raw_note"] = "[37]"

    result = materialize_candidate(
        [_material_anchor("Wrought", state="wrought")],
        [fact],
        source_text=source,
    )

    item = result.document["items"][0]
    prop = item["Extracted_Data"]["Properties"][0]
    assert item["Sample_ID"] == "Wrought [37] [reference]"
    assert prop["test_condition_raw"] == "Table 3"
    assert "ASTM E8" not in prop["test_condition_raw"]
    issue = next(
        row
        for row in result.issues
        if row.code == "reference_table_scope_recovered"
    )
    assert issue.actual["before"]["data"]["test_condition_raw"] is None
    assert issue.actual["after"]["data"]["test_condition_raw"] == "Table 3"
    assert issue.actual["scope"] == "Table 3"
    assert issue.actual["caption_raw"].startswith("Table 3.")
    assert set(issue.actual["reference_markers"]) == {
        "[37]",
        "[39]",
        "[43]",
        "[44]",
    }
    assert issue.actual["decision_key"].startswith(
        "reference-table-scope:table-cell:"
    )
    assert issue.expected["target_tensile_protocol_inherited"] is False


def test_single_cited_comparison_row_does_not_create_table_scope(monkeypatch):
    monkeypatch.setenv("KNOWMAT2_ALPHA25_OWNER_STATE_CONDITION_V202", "1")
    monkeypatch.setenv(
        "KNOWMAT2_ALPHA25_SOURCE_COORDINATE_PRECISION_V202", "1"
    )
    table = (
        "| Material | Yield strength (MPa) |\n"
        "| --- | --- |\n"
        "| Cast alloy 625 [6] | 350 |"
    )
    source = f"Table 2. Literature comparison.\n\n{table}"
    fact = _table_tensile_property("Cast alloy 625 [6]", "350", table)

    result = materialize_candidate(
        [_material_anchor("Cast alloy 625 [6]", material="Alloy 625")],
        [fact],
        source_text=source,
    )

    prop = result.document["items"][0]["Extracted_Data"]["Properties"][0]
    assert prop["test_condition_raw"] is None
    assert not any(
        row.code == "reference_table_scope_recovered" for row in result.issues
    )


@pytest.mark.parametrize(
    "source_factory",
    [
        lambda table: table,
        lambda table: (
            "Table 3. First caption.\n"
            "Table 3. Repeated caption.\n\n"
            f"{table}"
        ),
        lambda table: (
            "Table 3. Mechanical properties.\n\n"
            f"{table}\n\n"
            "Table 3. Mechanical properties.\n\n"
            f"{table}"
        ),
    ],
    ids=("missing_caption", "repeated_caption", "repeated_table"),
)
def test_ambiguous_dense_reference_table_scope_fails_closed(
    source_factory, monkeypatch
):
    monkeypatch.setenv("KNOWMAT2_ALPHA25_OWNER_STATE_CONDITION_V202", "1")
    monkeypatch.setenv(
        "KNOWMAT2_ALPHA25_SOURCE_COORDINATE_PRECISION_V202", "1"
    )
    table = (
        "| Properties | Wrought | WAAM | WLAM | WEBAM |\n"
        "| --- | --- | --- | --- | --- |\n"
        "| Yield Strength (MPa) | 948 [37] | 856 [39] | "
        "825 [43] | 846 [44] |"
    )
    fact = _table_tensile_property("Wrought", "948", table)
    fact.data["raw_note"] = "[37]"

    result = materialize_candidate(
        [_material_anchor("Wrought", state="wrought")],
        [fact],
        source_text=source_factory(table),
    )

    prop = result.document["items"][0]["Extracted_Data"]["Properties"][0]
    assert prop["test_condition_raw"] is None
    assert not any(
        row.code == "reference_table_scope_recovered" for row in result.issues
    )


def test_dense_reference_table_scope_never_overwrites_existing_condition(
    monkeypatch,
):
    monkeypatch.setenv("KNOWMAT2_ALPHA25_OWNER_STATE_CONDITION_V202", "1")
    monkeypatch.setenv(
        "KNOWMAT2_ALPHA25_SOURCE_COORDINATE_PRECISION_V202", "1"
    )
    table = (
        "| Properties | Wrought | WAAM | WLAM | WEBAM |\n"
        "| --- | --- | --- | --- | --- |\n"
        "| Yield Strength (MPa) | 948 [37] | 856 [39] | "
        "825 [43] | 846 [44] |"
    )
    fact = _table_tensile_property("Wrought", "948", table)
    fact.data["raw_note"] = "[37]"
    fact.data["test_condition_raw"] = "independently reported condition"

    result = materialize_candidate(
        [_material_anchor("Wrought", state="wrought")],
        [fact],
        source_text=f"Table 3. Mechanical properties.\n\n{table}",
    )

    prop = result.document["items"][0]["Extracted_Data"]["Properties"][0]
    assert prop["test_condition_raw"] == (
        "independently reported condition"
    )
    assert not any(
        row.code == "reference_table_scope_recovered" for row in result.issues
    )


def test_tensile_precision_table_projection_merges_into_richer_same_owner():
    prose = _tensile_property(
        "A", value="817", evidence="A had an ultimate tensile strength of 817 MPa"
    )
    table = _table_tensile_property(
        "A",
        "817 ± 8.68",
        "| Sample | Ultimate Tensile Strength (MPa) |\n| A | 817 ± 8.68 |",
        name="ultimate tensile strength",
    )

    result = materialize_candidate([_material_anchor("A")], [prose, table])

    properties = result.document["items"][0]["Extracted_Data"]["Properties"]
    assert len(properties) == 1
    assert properties[0]["value_raw"] == "817 ± 8.68"
    issue = next(
        row
        for row in result.issues
        if row.code == "tensile_precision_duplicate_merged"
    )
    assert issue.actual["removed_fact"]["data"]["value_raw"] == "817"
    assert issue.actual["survivor_after_merge"]["data"]["value_raw"] == "817 ± 8.68"


def test_tensile_precision_table_survivor_absorbs_multiple_prose_projections():
    direct = _tensile_property(
        "Sample-HOMO",
        value="358",
        name="yield strength",
        evidence="Sample-HOMO had a yield strength of 358 MPa.",
    )
    comparator = _tensile_property(
        "Sample-HOMO",
        value="358",
        name="yield strength",
        evidence="more than twice that of the Sample-HOMO material (358 MPa)",
    )
    comparator.data["raw_note"] = "reference material; less than half of Sample-LAG"
    table = _table_tensile_property(
        "Sample-HOMO",
        "358 ± 5",
        "| Sample | Yield strength (MPa) |\n| Sample-HOMO | 358 ± 5 |",
        name="Yield strength",
    )

    results = [
        materialize_candidate([_material_anchor("Sample-HOMO")], facts)
        for facts in (
            [direct, comparator, table],
            [table, comparator, direct],
        )
    ]

    for result in results:
        properties = result.document["items"][0]["Extracted_Data"]["Properties"]
        assert [row["value_raw"] for row in properties] == ["358 ± 5"]
        assert set(properties[0]["source_evidence"]) == {
            "Sample-HOMO had a yield strength of 358 MPa.",
            "more than twice that of the Sample-HOMO material (358 MPa)",
            "| Sample | Yield strength (MPa) |\n| Sample-HOMO | 358 ± 5 |",
        }
        issues = [
            row
            for row in result.issues
            if row.code == "tensile_precision_duplicate_merged"
        ]
        assert len(issues) == 2
        assert {
            row.actual["removed_fact"]["source_evidence"][0]
            for row in issues
        } == {
            "Sample-HOMO had a yield strength of 358 MPa.",
            "more than twice that of the Sample-HOMO material (358 MPa)",
        }


def test_literal_tensile_unit_recovery_enables_same_owner_precision_merge():
    prose = _tensile_property(
        "A",
        value="38%",
        name="uniform elongation",
        unit="",
        evidence="the uniform elongation remains at 38%",
    )
    table = _table_tensile_property(
        "A",
        "38 ± 4",
        "| Sample | Uniform elongation (%) |\n| A | 38 ± 4 |",
        name="Uniform elongation",
    )

    result = materialize_candidate([_material_anchor("A")], [prose, table])

    properties = result.document["items"][0]["Extracted_Data"]["Properties"]
    assert [row["value_raw"] for row in properties] == ["38 ± 4"]
    assert properties[0]["unit_raw"] == "%"
    assert set(properties[0]["source_evidence"]) == {
        "the uniform elongation remains at 38%",
        "| Sample | Uniform elongation (%) |\n| A | 38 ± 4 |",
    }
    unit_issue = next(
        row for row in result.issues if row.code == "literal_tensile_unit_recovered"
    )
    assert unit_issue.actual["before"]["data"]["unit_raw"] == ""
    assert unit_issue.actual["after"]["data"]["unit_raw"] == "%"
    assert any(
        row.code == "tensile_precision_duplicate_merged" for row in result.issues
    )


def test_literal_tensile_unit_recovery_handles_repeated_uncertainty_unit():
    fact = _tensile_property(
        "A",
        value="7.2% ± 0.4%",
        name="uniform elongation",
        unit="",
        evidence="A had a uniform elongation of 7.2% ± 0.4%.",
    )

    result = materialize_candidate([_material_anchor("A")], [fact])

    prop = result.document["items"][0]["Extracted_Data"]["Properties"][0]
    assert prop["value_raw"] == "7.2% ± 0.4%"
    assert prop["unit_raw"] == "%"
    assert any(
        row.code == "literal_tensile_unit_recovered" for row in result.issues
    )


@pytest.mark.parametrize(
    ("name", "value", "unit"),
    [
        ("uniform elongation", "7.2% ± 0.4 MPa", ""),
        ("uniform elongation", "more than 7.2%", ""),
        ("uniform elongation", "7.2%", "MPa"),
        ("yield strength", "358%", ""),
    ],
)
def test_literal_tensile_unit_recovery_protects_conflicts_and_qualifiers(
    name, value, unit
):
    fact = _tensile_property(
        "A", value=value, name=name, unit=unit, evidence=f"A reported {value}."
    )

    result = materialize_candidate([_material_anchor("A")], [fact])

    prop = result.document["items"][0]["Extracted_Data"]["Properties"][0]
    assert prop["unit_raw"] == unit
    assert not any(
        row.code == "literal_tensile_unit_recovered" for row in result.issues
    )


def test_tensile_precision_true_qualified_value_is_not_parenthetical_projection():
    qualified = _tensile_property(
        "Sample-HOMO",
        value="358",
        name="yield strength",
        evidence="Sample-HOMO had a yield strength of more than 358 MPa.",
    )
    qualified.data["raw_note"] = "lower bound"
    table = _table_tensile_property(
        "Sample-HOMO",
        "358 ± 5",
        "| Sample | Yield strength (MPa) |\n| Sample-HOMO | 358 ± 5 |",
        name="Yield strength",
    )

    result = materialize_candidate(
        [_material_anchor("Sample-HOMO")], [qualified, table]
    )

    properties = result.document["items"][0]["Extracted_Data"]["Properties"]
    assert {row["value_raw"] for row in properties} == {"358", "358 ± 5"}
    assert not any(
        row.code == "tensile_precision_duplicate_merged" for row in result.issues
    )


def test_tensile_exact_semantic_duplicate_merges_same_owner_and_condition():
    first = _tensile_property(
        "A",
        value="803",
        name="UTS",
        condition="650 °C",
        evidence="A had a UTS of 803 MPa at 650 °C.",
    )
    second = _tensile_property(
        "A",
        value="803",
        name="ultimate tensile strength",
        condition="650°C",
        evidence="The ultimate tensile strength of A was 803 MPa at 650°C.",
        data_source="unknown",
    )

    results = [
        materialize_candidate([_material_anchor("A")], facts)
        for facts in ([first, second], [second, first])
    ]

    for result in results:
        properties = result.document["items"][0]["Extracted_Data"]["Properties"]
        assert len(properties) == 1
        assert properties[0]["value_raw"] == "803"
        assert set(properties[0]["source_evidence"]) == {
            "A had a UTS of 803 MPa at 650 °C.",
            "The ultimate tensile strength of A was 803 MPa at 650°C.",
        }
        issue = next(
            row
            for row in result.issues
            if row.code == "tensile_exact_duplicate_merged"
        )
        assert issue.actual["removed_fact"]["data"]["value_raw"] == "803"
        assert issue.actual["survivor_after_merge"]["data"]["value_raw"] == "803"


def test_tensile_exact_semantic_duplicate_folds_tex_uncertainty_presentation():
    unicode_fact = _tensile_property(
        "A",
        value="17.0 ± 3.1",
        name="elongation",
        unit="%",
        condition="800 °C",
        evidence="A EL was 17.0 ± 3.1 % at 800 °C.",
    )
    tex_fact = _tensile_property(
        "A",
        value=r"17.0 \pm 3.1",
        name="tensile ductility",
        unit="%",
        condition="800 °C",
        evidence=r"A tensile ductility was 17.0 \pm 3.1 % at 800 °C.",
    )

    result = materialize_candidate(
        [_material_anchor("A")], [tex_fact, unicode_fact]
    )

    properties = result.document["items"][0]["Extracted_Data"]["Properties"]
    assert len(properties) == 1
    assert any(
        row.code == "tensile_exact_duplicate_merged" for row in result.issues
    )


def test_tensile_exact_semantic_duplicate_protects_scientific_distinctions():
    facts = [
        _tensile_property(
            "A",
            value="817",
            condition="700 °C",
            evidence="A had UTS 817 MPa at 700 °C.",
        ),
        _tensile_property(
            "A",
            value="817",
            condition="900 °C",
            evidence="A had UTS 817 MPa at 900 °C.",
        ),
        _tensile_property(
            "B", value="817", evidence="B had UTS 817 MPa."
        ),
        _tensile_property(
            "A",
            value="~817",
            evidence="A had approximately 817 MPa UTS.",
        ),
        _tensile_property(
            "A",
            value="38",
            name="uniform elongation",
            unit="%",
            evidence="A uniform elongation was 38%.",
        ),
        _tensile_property(
            "A",
            value="38",
            name="fracture elongation",
            unit="%",
            evidence="A fracture elongation was 38%.",
        ),
    ]

    result = materialize_candidate(
        [_material_anchor("A"), _material_anchor("B")], facts
    )

    properties = [
        prop
        for item in result.document["items"]
        for prop in item["Extracted_Data"]["Properties"]
    ]
    assert {
        prop["test_condition_raw"]
        for prop in properties
        if prop["value_raw"] == "817"
        and prop["property_name_raw"] == "ultimate tensile strength"
    } >= {"700 °C", "900 °C"}
    assert any(prop["value_raw"] == "~817" for prop in properties)
    assert not any(
        row.code == "tensile_precision_duplicate_merged"
        and row.actual["removed_fact"]["data"]["value_raw"] == "~817"
        for row in result.issues
    )
    assert {
        prop["property_name_raw"]
        for prop in properties
        if prop["value_raw"] == "38"
    } >= {"uniform elongation", "fracture elongation"}
    assert not any(
        row.code == "tensile_exact_duplicate_merged" for row in result.issues
    )


def test_tensile_same_information_prose_and_table_merge_only_as_exact_semantics():
    prose = _tensile_property("A", value="817", evidence="A had UTS 817 MPa")
    table = _table_tensile_property(
        "A",
        "817",
        "| Sample | UTS (MPa) |\n| A | 817 |",
        name="UTS",
    )

    result = materialize_candidate([_material_anchor("A")], [prose, table])

    properties = result.document["items"][0]["Extracted_Data"]["Properties"]
    assert len(properties) == 1
    assert set(properties[0]["source_evidence"]) == {
        "A had UTS 817 MPa",
        "| Sample | UTS (MPa) |\n| A | 817 |",
    }
    assert not any(
        row.code == "tensile_precision_duplicate_merged" for row in result.issues
    )
    assert any(
        row.code == "tensile_exact_duplicate_merged" for row in result.issues
    )


def test_tensile_precision_unique_table_owner_replaces_generic_projection():
    generic = _tensile_property(
        "Alloy-B",
        value="900",
        evidence="Alloy-B had an ultimate tensile strength of 900 MPa.",
    )
    table = _table_tensile_property(
        "Alloy-B sample as-built",
        "900 ± 5",
        "| Sample | UTS (MPa) |\n| Alloy-B sample as-built | 900 ± 5 |",
        name="UTS",
    )

    result = materialize_candidate(
        [
            _material_anchor("Alloy-B"),
            _material_anchor("Alloy-B", state="as-built"),
        ],
        [generic, table],
    )

    properties_by_owner = {
        row["Sample_ID"]: row["Extracted_Data"]["Properties"]
        for row in result.document["items"]
    }
    assert set(properties_by_owner) == {"Alloy-B"}
    assert properties_by_owner["Alloy-B"][0]["value_raw"] == "900 ± 5"
    assert any(
        row.code == "tensile_precision_duplicate_merged" for row in result.issues
    )


def test_tensile_precision_does_not_merge_conflicting_elongation_subtypes():
    total = _table_tensile_property(
        "A",
        "70 ± 5",
        "| Sample | Total Elongation (%) |\n| A | 70 ± 5 |",
        name="Total elongation",
    )
    fracture = _table_tensile_property(
        "A",
        "70",
        "A fracture elongation was 70%.",
        name="fracture elongation",
        data_source="text",
    )

    result = materialize_candidate([_material_anchor("A")], [total, fracture])

    properties = result.document["items"][0]["Extracted_Data"]["Properties"]
    assert len(properties) == 2
    assert not any(
        row.code == "tensile_precision_duplicate_merged" for row in result.issues
    )


def test_tensile_precision_does_not_merge_conflicting_explicit_conditions():
    first = _tensile_property(
        "A", value="817", evidence="A had UTS 817 MPa at 700 °C"
    )
    first.data["test_condition_raw"] = "700 °C"
    second = _table_tensile_property(
        "A",
        "817 ± 8.68",
        "| Sample | UTS (MPa) |\n| A | 817 ± 8.68 |",
        name="UTS",
    )
    second.data["test_condition_raw"] = "900 °C"

    result = materialize_candidate([_material_anchor("A")], [first, second])

    properties = result.document["items"][0]["Extracted_Data"]["Properties"]
    assert len(properties) == 2
    assert not any(
        row.code == "tensile_precision_duplicate_merged" for row in result.issues
    )


def test_tensile_precision_merges_uncertainty_compatible_rounded_table_value():
    prose = _tensile_property(
        "A",
        value="0.71 ± 0.02",
        name="UTS",
        unit="GPa",
        evidence="A had a UTS of 0.71 ± 0.02 GPa.",
    )
    table = _table_tensile_property(
        "A",
        "0.707 ± 0.012",
        "| Sample | UTS (GPa) |\n| A | 0.707 ± 0.012 |",
        name="UTS",
    )
    table.data["unit_raw"] = "GPa"
    result = materialize_candidate([_material_anchor("A")], [prose, table])

    properties = result.document["items"][0]["Extracted_Data"]["Properties"]
    assert [row["value_raw"] for row in properties] == ["0.707 ± 0.012"]
    issue = next(
        row
        for row in result.issues
        if row.code == "tensile_precision_duplicate_merged"
    )
    assert issue.expected["rule"] == "table_precision_over_projection"


def test_tensile_precision_merges_oriented_summary_into_matching_table_owner():
    base = _tensile_property(
        "Binder Jetting",
        condition="X orientation",
        value="0.71 ± 0.02",
        name="UTS",
        unit="GPa",
        evidence="Binder Jetting in the X orientation had UTS 0.71 ± 0.02 GPa.",
    )
    x_table = _table_tensile_property(
        "Binder Jetting / X",
        "0.707 ± 0.012",
        "| Property | Binder Jetting / X |\n| UTS (GPa) | 0.707 ± 0.012 |",
        name="UTS",
    )
    x_table.data["unit_raw"] = "GPa"
    z_table = _table_tensile_property(
        "Binder Jetting / Z",
        "0.744 ± 0.010",
        "| Property | Binder Jetting / Z |\n| UTS (GPa) | 0.744 ± 0.010 |",
        name="UTS",
    )
    z_table.data["unit_raw"] = "GPa"

    result = materialize_candidate(
        [
            _material_anchor("Binder Jetting", material="Alloy 625"),
            _material_anchor("Binder Jetting / X", material="Alloy 625"),
            _material_anchor("Binder Jetting / Z", material="Alloy 625"),
        ],
        [base, x_table, z_table],
    )

    properties = [
        (item["Sample_ID"], prop["value_raw"])
        for item in result.document["items"]
        for prop in item["Extracted_Data"]["Properties"]
    ]
    assert properties == [
        ("Binder Jetting", "0.707 ± 0.012"),
        ("Binder Jetting / Z", "0.744 ± 0.010"),
    ]
    issue = next(
        row
        for row in result.issues
        if row.code == "tensile_precision_duplicate_merged"
    )
    assert issue.actual["before_owner"] == "Binder Jetting"
    assert issue.actual["winner_source_owner"] == "Binder Jetting / X"
    assert issue.actual["after_owner"] == "Binder Jetting"
    assert issue.expected["rule"] == (
        "orientation_condition_owner_with_table_precision"
    )


def test_oriented_declared_owner_survives_coarse_evidence_reconciliation():
    prose = _tensile_property(
        "LPBF / Z",
        condition="Z orientation",
        value="0.84 ± 0.02",
        name="UTS",
        unit="GPa",
        evidence=(
            "For specimens fabricated in the Z orientation, LPBF displayed "
            "the highest UTS (0.84 ± 0.02 GPa)."
        ),
    )
    table = _table_tensile_property(
        "LPBF / Z",
        "0.842 ± 0.029",
        "| Property | LPBF / Z |\n| UTS (GPa) | 0.842 ± 0.029 |",
        name="UTS",
    )
    table.data["unit_raw"] = "GPa"
    x_table = _table_tensile_property(
        "LPBF / X",
        "0.906 ± 0.028",
        "| Property | LPBF / X |\n| UTS (GPa) | 0.906 ± 0.028 |",
        name="UTS",
    )
    x_table.data["unit_raw"] = "GPa"

    result = materialize_candidate(
        [
            _material_anchor("LPBF", material="Alloy 625"),
            _material_anchor("LPBF / X", material="Alloy 625"),
            _material_anchor("LPBF / Z", material="Alloy 625"),
        ],
        [prose, table, x_table],
    )

    properties = [
        (item["Sample_ID"], prop["value_raw"])
        for item in result.document["items"]
        for prop in item["Extracted_Data"]["Properties"]
    ]
    assert properties == [
        ("LPBF / X", "0.906 ± 0.028"),
        ("LPBF / Z", "0.842 ± 0.029"),
    ]
    assert any(
        row.code == "tensile_precision_duplicate_merged" for row in result.issues
    )
    assert not any(
        row.code == "fact_owner_evidence_reconciled" for row in result.issues
    )


def test_dense_oriented_cell_is_a_complete_precision_coordinate():
    fact = _tensile_property(
        "LPBF / Z",
        value="0.842 ± 0.029",
        name="Ultimate Tensile Strength",
        unit="GPa",
        data_source="table",
        evidence=(
            '<tr><td>UTS (GPa)</td><td>0.906 ± 0.028</td>'
            '<td>0.842 ± 0.029</td></tr>'
        ),
    )
    fact.data["property_id_candidate"] = "dense-table-cell:literal"
    fact.data["raw_note"] = "Z"
    fact.data["test_specimen_raw"] = "Z"

    binding = _tensile_precision_complete_table(fact)

    assert binding is not None
    assert binding["binding"] == "dense_table_cell_coordinate"
    assert binding["owner_cell"] == "Z"
    assert binding["value_cell"] == "0.842 ± 0.029"


def test_dense_table_coordinate_requires_complete_scientific_fields():
    fact = _tensile_property(
        "LPBF / Z",
        value="0.539 ± 0.058",
        name="Elastic Modulus",
        unit="GPa",
        data_source="table",
        evidence=(
            '<tr><td>Modulus of elasticity (GPa)</td>'
            '<td>0.561 ± 0.014</td><td>0.539 ± 0.058</td></tr>'
        ),
    )
    fact.data["property_id_candidate"] = "dense-table-cell:literal"
    fact.data["raw_note"] = "Z"

    assert _fact_has_table_coordinate(fact)

    missing_unit = fact.model_copy(
        update={"data": {**fact.data, "unit_raw": ""}}
    )
    assert not _fact_has_table_coordinate(missing_unit)

    unsupported_unit = fact.model_copy(
        update={"data": {**fact.data, "unit_raw": "ksi"}}
    )
    assert not _fact_has_table_coordinate(unsupported_unit)


def test_tensile_precision_merges_approximate_summary_into_exact_result():
    approximate = _tensile_property(
        "A",
        value="approximately 2.2 GPa",
        name="ultimate tensile strength",
        unit="GPa",
        condition="room temperature",
        evidence="A achieved an ultimate tensile strength of approximately 2.2 GPa.",
    )
    exact = _tensile_property(
        "A",
        value="2200",
        name="ultimate tensile strength",
        unit="MPa",
        condition="room temperature",
        evidence="The ultimate tensile strength of A reached 2200 MPa at room temperature.",
    )

    result = materialize_candidate([_material_anchor("A")], [approximate, exact])

    properties = result.document["items"][0]["Extracted_Data"]["Properties"]
    assert [row["value_raw"] for row in properties] == ["2200"]
    assert any(
        row.code == "core_tensile_approximate_shadow_quarantined"
        for row in result.issues
    )
    issue = next(
        row
        for row in result.issues
        if row.code == "core_tensile_approximate_shadow_quarantined"
    )
    assert issue.actual["removed_fact"] == approximate.model_dump()
    assert issue.actual["survivor_after_merge"]["data"]["value_raw"] == "2200"


def test_tensile_precision_merges_truncated_owner_into_unique_richer_table_owner():
    truncated = _tensile_property(
        "PBF-",
        value="803",
        name="ultimate tensile strength",
        condition='{"test_method_raw": "tensile"}',
        evidence="| PBF- | This work | 803 |",
    )
    precise = _table_tensile_property(
        "PBF-EB",
        "803 ± 30",
        "| Property | PBF-EB (650 °C) |\n| UTS (MPa) | 803 ± 30 |",
        name="UTS",
    )
    precise.data["test_condition_raw"] = "650 °C"

    result = materialize_candidate(
        [_material_anchor("PBF-"), _material_anchor("PBF-EB")],
        [
            _composition_fact("PBF-", "PBF-", "PBF- contains 1 wt% Zr."),
            truncated,
            precise,
        ],
    )

    properties = [
        (item["Sample_ID"], prop["value_raw"])
        for item in result.document["items"]
        for prop in item["Extracted_Data"]["Properties"]
    ]
    assert properties == [("PBF-EB", "803 ± 30")]
    assert [item["Sample_ID"] for item in result.document["items"]] == [
        "PBF-",
        "PBF-EB",
    ]
    incomplete_item = result.document["items"][0]
    assert incomplete_item["Extracted_Data"]["Properties"] == []
    assert incomplete_item["Extracted_Data"]["Composition"][
        "Composition_Observations"
    ]
    issue = next(
        row
        for row in result.issues
        if row.code == "property_incomplete_owner_quarantined"
    )
    assert issue.actual["reason"] == "dangling_owner_separator"
    assert issue.actual["fact"] == truncated.model_dump()


def test_condition_qualified_table_preserves_same_owner_exact_headline():
    headline = _tensile_property(
        "A",
        value="803",
        name="ultimate tensile strength",
        condition="650 °C",
        evidence="The UTS was 803 MPa at 650 °C.",
    )
    table = _table_tensile_property(
        "A",
        "803 ± 30",
        "| Property | A (650 °C) |\n| UTS (MPa) | 803 ± 30 |",
        name="UTS",
    )
    table.data["test_condition_raw"] = "650 °C"

    result = materialize_candidate(
        [_material_anchor("A")], [headline, table]
    )

    properties = result.document["items"][0]["Extracted_Data"]["Properties"]
    assert {row["value_raw"] for row in properties} == {"803", "803 ± 30"}
    assert not any(
        row.code == "tensile_precision_duplicate_merged"
        for row in result.issues
    )


def test_tensile_precision_same_owner_richer_value_needs_no_repeated_owner_quote():
    rounded = _tensile_property(
        "A",
        value="~748",
        name="yield strength",
        evidence="The experimental yield strength was approximately 748 MPa.",
    )
    precise = _tensile_property(
        "A",
        value="~748.0",
        name="yield strength",
        evidence="This is close to the experimental value of approximately 748.0 MPa.",
    )

    result = materialize_candidate(
        [_material_anchor("A")], [rounded, precise]
    )

    properties = result.document["items"][0]["Extracted_Data"]["Properties"]
    assert [row["value_raw"] for row in properties] == ["~748.0"]
    issue = next(
        row
        for row in result.issues
        if row.code == "tensile_precision_duplicate_merged"
    )
    assert issue.expected["rule"] == (
        "same_owner_richer_precision_over_projection"
    )


def test_tensile_precision_merges_same_owner_rounded_explicit_prose_value():
    rounded = _tensile_property(
        "A", value="781", name="UTS", evidence="A had a UTS of 781 MPa."
    )
    precise = _tensile_property(
        "A",
        value="781.2",
        name="ultimate tensile strength",
        evidence="The ultimate tensile strength of A was 781.2 MPa.",
    )

    result = materialize_candidate(
        [_material_anchor("A")], [rounded, precise]
    )

    properties = result.document["items"][0]["Extracted_Data"]["Properties"]
    assert [row["value_raw"] for row in properties] == ["781.2"]
    issue = next(
        row
        for row in result.issues
        if row.code == "tensile_precision_duplicate_merged"
    )
    assert issue.expected["rule"] == "explicit_prose_precision_over_projection"


def test_v205_orientation_coordinate_survives_short_prose_evidence():
    x_fact = _tensile_property(
        "LPBF / X",
        value="0.91 ± 0.03",
        unit="GPa",
        evidence=(
            "LPBF samples had the highest ultimate tensile strength "
            "(0.91 ± 0.03 GPa)"
        ),
    )
    x_fact.data["property_id_candidate"] = (
        "tensile-process-owner-v205:source-sentence"
    )
    z_fact = _tensile_property(
        "LPBF / Z",
        value="0.84 ± 0.02",
        unit="GPa",
        condition="Z orientation",
        evidence="LPBF in the Z orientation had a UTS of 0.84 ± 0.02 GPa.",
    )
    z_fact.data["property_id_candidate"] = "tensile-process-owner-v205:direct"

    result = materialize_candidate(
        [_material_anchor("LPBF"), _material_anchor("LPBF / X"), _material_anchor("LPBF / Z")],
        [x_fact, z_fact],
    )

    matching = [
        (item["Sample_ID"], prop["value_raw"])
        for item in result.document["items"]
        for prop in item["Extracted_Data"]["Properties"]
    ]
    assert matching == [
        ("LPBF / X", "0.91 ± 0.03"),
        ("LPBF / Z", "0.84 ± 0.02"),
    ]


def test_tensile_precision_protects_nonrounding_and_disjoint_uncertainty_values():
    facts = [
        _tensile_property(
            "A", value="781", name="UTS", evidence="A had UTS 781 MPa."
        ),
        _tensile_property(
            "A", value="781.6", name="UTS", evidence="A had UTS 781.6 MPa."
        ),
        _tensile_property(
            "A",
            value="0.71 ± 0.001",
            name="yield strength",
            unit="GPa",
            evidence="A had YS 0.71 ± 0.001 GPa.",
        ),
        _table_tensile_property(
            "A",
            "0.707 ± 0.001",
            "| Sample | YS (GPa) |\n| A | 0.707 ± 0.001 |",
            name="yield strength",
        ),
    ]
    facts[-1].data["unit_raw"] = "GPa"

    result = materialize_candidate([_material_anchor("A")], facts)

    properties = result.document["items"][0]["Extracted_Data"]["Properties"]
    assert len(properties) == 4
    assert not any(
        row.code == "tensile_precision_duplicate_merged" for row in result.issues
    )


def test_tensile_precision_selects_richest_record_from_same_winner_owner():
    prose = _tensile_property(
        "A", value="817", name="yield strength", evidence="A had YS 817 MPa"
    )
    rounded_table = _table_tensile_property(
        "A",
        "817 ± 8.7",
        "| Sample | Avg. YS (MPa) |\n| A | 817 ± 8.7 |",
        name="Avg. YS",
    )
    precise_table = _table_tensile_property(
        "A",
        "817 ± 8.68",
        "| Sample | Yield Stress (MPa) |\n| A | 817 ± 8.68 |",
        name="Yield Stress (MPa)",
    )

    result = materialize_candidate(
        [_material_anchor("A")], [prose, rounded_table, precise_table]
    )

    properties = result.document["items"][0]["Extracted_Data"]["Properties"]
    assert [row["value_raw"] for row in properties] == ["817 ± 8.68"]
    issues = [
        row
        for row in result.issues
        if row.code == "tensile_precision_duplicate_merged"
    ]
    assert len(issues) == 2
    assert {
        row.actual["removed_fact"]["data"]["value_raw"] for row in issues
    } == {"817", "817 ± 8.7"}


def test_tensile_precision_table_state_owner_replaces_same_uncertainty_base():
    condition = "sintered at 1285 °C and aged at 745 °C for 20 h"
    generic = _tensile_property(
        "GA",
        condition=condition,
        value="394 ± 15",
        name="yield strength",
        evidence="GA yield strength was 394 ± 15 MPa after sintering and aging.",
    )
    state_owner = f"GA [{condition}]"
    table = _table_tensile_property(
        state_owner,
        "394 ± 15",
        f"| Sample | Yield stress (MPa) |\n| {state_owner} | 394 ± 15 |",
        name="Yield stress",
    )

    result = materialize_candidate(
        [_anchor("GA", "as-built"), _anchor("GA", condition)],
        [generic, table],
    )

    matching = [
        (item["Sample_ID"], prop["value_raw"])
        for item in result.document["items"]
        for prop in item["Extracted_Data"]["Properties"]
        if prop["value_raw"] == "394 ± 15"
    ]
    assert matching == [(state_owner, "394 ± 15")]
    issue = next(
        row
        for row in result.issues
        if row.code == "tensile_precision_duplicate_merged"
    )
    assert issue.expected["rule"] == "qualified_state_over_base"
    assert issue.actual["loser_conditions"] == [condition]


def test_tensile_precision_complete_table_owner_replaces_unnamed_projection():
    projected = _tensile_property(
        "1-1",
        value="1130",
        evidence="The reported UTS and elongation pair was (1130 MPa, 17.6%).",
    )
    table = _table_tensile_property(
        "4-1",
        "1130 ± 13.0",
        "| Sample | UTS (MPa) |\n| 4-1 | 1130 ± 13.0 |",
        name="UTS",
    )

    result = materialize_candidate(
        [
            _material_anchor("1-1", material="alpha titanium alloy"),
            _material_anchor("4-1", material="alpha titanium alloy"),
        ],
        [projected, table],
    )

    matching = [
        (item["Sample_ID"], prop["value_raw"])
        for item in result.document["items"]
        for prop in item["Extracted_Data"]["Properties"]
    ]
    assert matching == [("4-1", "1130 ± 13.0")]
    issue = next(
        row
        for row in result.issues
        if row.code == "tensile_precision_duplicate_merged"
    )
    assert issue.actual["before_owner"] == "1-1"
    assert issue.actual["after_owner"] == "4-1"
    assert issue.expected["rule"] == "unique_table_record_over_rounded_projection"


def test_tensile_precision_explicit_prose_owner_replaces_unnamed_summary():
    generic_owner = "Alloy X [sintered]"
    specific_owner = "1280 °C sample"
    summary = _tensile_property(
        generic_owner,
        value="612",
        evidence="The optimum condition had the highest UTS of 612 MPa.",
    )
    explicit = _tensile_property(
        specific_owner,
        value="612",
        evidence="The 1280 °C sample showed the highest UTS of 612 MPa.",
    )

    result = materialize_candidate(
        [
            InventoryAnchor(
                sample_id_raw=generic_owner,
                material_name_raw="Alloy X",
                state_raw="sintered",
                role="Target",
                data_nature="Experimental",
                source_evidence=[generic_owner],
                confidence=0.9,
            ),
            InventoryAnchor(
                sample_id_raw=specific_owner,
                material_name_raw="Alloy X",
                state_raw="fully densified; sintered at 1280 °C",
                role="Target",
                data_nature="Experimental",
                source_evidence=[specific_owner],
                confidence=0.9,
            ),
        ],
        [summary, explicit],
    )

    matching = [
        (item["Sample_ID"], prop["value_raw"])
        for item in result.document["items"]
        for prop in item["Extracted_Data"]["Properties"]
    ]
    assert matching == [(specific_owner, "612")]
    issue = next(
        row
        for row in result.issues
        if row.code == "tensile_precision_duplicate_merged"
    )
    assert issue.expected["rule"] in {
        "explicit_state_owner_over_generic_projection",
        "explicit_prose_owner_over_unnamed_summary",
    }


def _inventory_linked_tensile_summary_facts(
    *,
    summary_owner: str = "Fe-base",
    winner_owner: str = "X-LAG",
    summary_evidence: str = (
        "The yield strength, ultimate tensile strength and uniform elongation "
        "were 775 MPa, 945 MPa and 38%, respectively."
    ),
    summary_condition: str | None = None,
    winner_condition: str | None = None,
) -> tuple[list[PropertyFact], list[PropertyFact]]:
    summary: list[PropertyFact] = []
    detailed: list[PropertyFact] = []
    table = (
        "| Sample | Yield strength (MPa) | UTS (MPa) | Uniform elongation (%) |\n"
        f"| {winner_owner} | 775 ± 6 | 945 ± 9 | 38 ± 4 |"
    )
    for name, value, precise, unit in zip(
        ("yield strength", "ultimate tensile strength", "uniform elongation"),
        ("775", "945", "38"),
        ("775 ± 6", "945 ± 9", "38 ± 4"),
        ("MPa", "MPa", "%"),
        strict=True,
    ):
        summary.append(
            _tensile_property(
                summary_owner,
                value=value,
                name=name,
                unit=unit,
                condition=summary_condition,
                evidence=summary_evidence,
            )
        )
        winner = _table_tensile_property(
            winner_owner,
            precise,
            table,
            name=name,
        )
        winner.data["test_condition_raw"] = winner_condition
        detailed.append(winner)
    return summary, detailed


def test_inventory_state_linked_complete_tensile_summary_merges():
    summary, detailed = _inventory_linked_tensile_summary_facts()
    result = materialize_candidate(
        [
            _material_anchor(
                "Fe-base", material="Fe-base HEA", state="X-LAG"
            ),
            _material_anchor("X-LAG", material="X alloy", state="LAG"),
        ],
        [*summary, *detailed],
    )

    items = {item["Sample_ID"]: item for item in result.document["items"]}
    assert "Fe-base" not in items or not items["Fe-base"]["Extracted_Data"][
        "Properties"
    ]
    assert {
        row["value_raw"]
        for row in items["X-LAG"]["Extracted_Data"]["Properties"]
    } == {"775 ± 6", "945 ± 9", "38 ± 4"}
    issue = next(
        row
        for row in result.issues
        if row.code == "inventory_state_tensile_summary_duplicate_merged"
    )
    assert issue.actual["before_owner"] == "Fe-base"
    assert issue.actual["after_owner"] == "X-LAG"
    assert issue.actual["owner_invented"] is False
    assert len(issue.actual["removed_bundle"]) == 3
    assert len(issue.actual["member_mappings"]) == 3


def test_inventory_state_linked_partial_tensile_summary_is_protected():
    summary, detailed = _inventory_linked_tensile_summary_facts()
    result = materialize_candidate(
        [
            _material_anchor(
                "Fe-base", material="Fe-base HEA", state="X-LAG"
            ),
            _material_anchor("X-LAG", material="X alloy", state="LAG"),
        ],
        [*summary[:2], *detailed],
    )

    items = {item["Sample_ID"]: item for item in result.document["items"]}
    assert len(items["Fe-base"]["Extracted_Data"]["Properties"]) == 2
    assert not any(
        row.code == "inventory_state_tensile_summary_duplicate_merged"
        for row in result.issues
    )


def test_inventory_state_linked_named_summary_owner_is_protected():
    summary, detailed = _inventory_linked_tensile_summary_facts(
        summary_evidence=(
            "Fe-base had yield strength, ultimate tensile strength and uniform "
            "elongation of 775 MPa, 945 MPa and 38%, respectively."
        )
    )
    result = materialize_candidate(
        [
            _material_anchor(
                "Fe-base", material="Fe-base HEA", state="X-LAG"
            ),
            _material_anchor("X-LAG", material="X alloy", state="LAG"),
        ],
        [*summary, *detailed],
    )

    items = {item["Sample_ID"]: item for item in result.document["items"]}
    assert len(items["Fe-base"]["Extracted_Data"]["Properties"]) == 3
    assert not any(
        row.code == "inventory_state_tensile_summary_duplicate_merged"
        for row in result.issues
    )


def test_inventory_state_linked_ambiguous_state_samples_are_protected():
    summary, detailed = _inventory_linked_tensile_summary_facts()
    result = materialize_candidate(
        [
            _material_anchor(
                "Fe-base", material="Fe-base HEA", state="X-LAG"
            ),
            _material_anchor(
                "Fe-base", material="Fe-base HEA", state="X-LH"
            ),
            _material_anchor("X-LAG", material="X alloy", state="LAG"),
            _material_anchor("X-LH", material="X alloy", state="LH"),
        ],
        [*summary, *detailed],
    )

    items = {item["Sample_ID"]: item for item in result.document["items"]}
    assert len(items["Fe-base"]["Extracted_Data"]["Properties"]) == 3
    assert not any(
        row.code == "inventory_state_tensile_summary_duplicate_merged"
        for row in result.issues
    )


def test_inventory_state_linked_condition_conflict_is_protected():
    summary, detailed = _inventory_linked_tensile_summary_facts(
        summary_condition="room temperature",
        winner_condition="650 °C",
    )
    result = materialize_candidate(
        [
            _material_anchor(
                "Fe-base", material="Fe-base HEA", state="X-LAG"
            ),
            _material_anchor("X-LAG", material="X alloy", state="LAG"),
        ],
        [*summary, *detailed],
    )

    items = {item["Sample_ID"]: item for item in result.document["items"]}
    assert len(items["Fe-base"]["Extracted_Data"]["Properties"]) == 3
    assert not any(
        row.code == "inventory_state_tensile_summary_duplicate_merged"
        for row in result.issues
    )


def _inventory_linked_surface_summary_facts(
    *, owner: str = "Fe-base", evidence_owner: str = ""
) -> list[PropertyFact]:
    rows = []
    prefix = f"{evidence_owner} " if evidence_owner else ""
    for name, value, unit in (
        ("surface microhardness", "2.9", "GPa"),
        ("surface roughness Ra", "0.55", "μm"),
        ("average friction coefficient", "0.48", ""),
    ):
        fact = _raw_property(
            owner,
            name,
            value,
            f"{prefix}{name} of {value} {unit}".strip(),
        )
        fact.data["unit_raw"] = unit
        rows.append(fact)
    return rows


def test_inventory_state_linked_property_summary_owner_is_reassigned():
    source = (
        "The X-LAG sample has a surface microhardness of 2.9 GPa, a surface "
        "roughness Ra of 0.55 μm and an average friction coefficient of 0.48."
    )
    result = materialize_candidate(
        [
            _material_anchor(
                "Fe-base", material="Fe-base HEA", state="X-LAG"
            ),
            _material_anchor("X-LAG", material="X alloy", state="LAG"),
        ],
        _inventory_linked_surface_summary_facts(),
        source_text=source,
    )

    items = {item["Sample_ID"]: item for item in result.document["items"]}
    assert "Fe-base" not in items or not items["Fe-base"]["Extracted_Data"][
        "Properties"
    ]
    assert len(items["X-LAG"]["Extracted_Data"]["Properties"]) == 3
    issue = next(
        row
        for row in result.issues
        if row.code == "inventory_state_property_summary_owner_reassigned"
    )
    assert issue.actual["before_owner"] == "Fe-base"
    assert issue.actual["after_owner"] == "X-LAG"
    assert issue.actual["reassigned_count"] == 3
    assert issue.actual["owner_invented"] is False


def test_inventory_state_linked_two_property_summary_is_protected():
    source = (
        "The X-LAG sample has a surface microhardness of 2.9 GPa and a surface "
        "roughness Ra of 0.55 μm."
    )
    result = materialize_candidate(
        [
            _material_anchor(
                "Fe-base", material="Fe-base HEA", state="X-LAG"
            ),
            _material_anchor("X-LAG", material="X alloy", state="LAG"),
        ],
        _inventory_linked_surface_summary_facts()[:2],
        source_text=source,
    )

    items = {item["Sample_ID"]: item for item in result.document["items"]}
    assert len(items["Fe-base"]["Extracted_Data"]["Properties"]) == 2
    assert not any(
        row.code == "inventory_state_property_summary_owner_reassigned"
        for row in result.issues
    )


def test_inventory_state_linked_explicit_property_summary_owner_is_protected():
    source = (
        "The X-LAG sample has a surface microhardness of 2.9 GPa, a surface "
        "roughness Ra of 0.55 μm and an average friction coefficient of 0.48."
    )
    result = materialize_candidate(
        [
            _material_anchor(
                "Fe-base", material="Fe-base HEA", state="X-LAG"
            ),
            _material_anchor("X-LAG", material="X alloy", state="LAG"),
        ],
        _inventory_linked_surface_summary_facts(evidence_owner="Fe-base"),
        source_text=source,
    )

    items = {item["Sample_ID"]: item for item in result.document["items"]}
    assert len(items["Fe-base"]["Extracted_Data"]["Properties"]) == 3
    assert not any(
        row.code == "inventory_state_property_summary_owner_reassigned"
        for row in result.issues
    )


def test_inventory_state_linked_multiowner_property_assertion_is_protected():
    source = (
        "The X-LAG and X-LH samples have a surface microhardness of 2.9 GPa, "
        "a surface roughness Ra of 0.55 μm and an average friction coefficient "
        "of 0.48."
    )
    result = materialize_candidate(
        [
            _material_anchor(
                "Fe-base", material="Fe-base HEA", state="X-LAG"
            ),
            _material_anchor("X-LAG", material="X alloy", state="LAG"),
            _material_anchor("X-LH", material="X alloy", state="LH"),
        ],
        _inventory_linked_surface_summary_facts(),
        source_text=source,
    )

    items = {item["Sample_ID"]: item for item in result.document["items"]}
    assert len(items["Fe-base"]["Extracted_Data"]["Properties"]) == 3
    assert not any(
        row.code == "inventory_state_property_summary_owner_reassigned"
        for row in result.issues
    )


def test_tensile_precision_compatible_state_condition_detail_can_merge():
    generic_owner = "Alloy X [sintered]"
    specific_owner = "1280 °C sample"
    summary = _tensile_property(
        generic_owner,
        value="612",
        condition="optimum sintering temperature of 1280 °C and time of 4 h",
        evidence="The optimum condition had the highest UTS of 612 MPa.",
    )
    explicit = _tensile_property(
        specific_owner,
        value="612",
        condition="fully densified; sintered at 1280 °C",
        evidence="The 1280 °C sample showed the highest UTS of 612 MPa.",
    )
    anchors = [
        InventoryAnchor(
            sample_id_raw=generic_owner,
            material_name_raw="Alloy X",
            state_raw="sintered",
            role="Target",
            data_nature="Experimental",
            source_evidence=[generic_owner],
            confidence=0.9,
        ),
        InventoryAnchor(
            sample_id_raw=specific_owner,
            material_name_raw="Alloy X",
            state_raw="fully densified; sintered at 1280 °C for 4 h",
            role="Target",
            data_nature="Experimental",
            source_evidence=[specific_owner],
            confidence=0.9,
        ),
    ]

    result = materialize_candidate(anchors, [summary, explicit])

    matching = [
        (item["Sample_ID"], prop["value_raw"])
        for item in result.document["items"]
        for prop in item["Extracted_Data"]["Properties"]
    ]
    assert matching == [(specific_owner, "612")]


def test_tensile_precision_unnamed_summary_with_two_prose_owners_is_protected():
    generic_owner = "Alloy X [sintered]"
    summary = _tensile_property(
        generic_owner,
        value="612",
        evidence="The optimum condition had the highest UTS of 612 MPa.",
    )
    owners = ["1280 °C sample", "1290 °C sample"]
    explicit = [
        _tensile_property(
            owner,
            value="612",
            evidence=f"The {owner} had an UTS of 612 MPa.",
        )
        for owner in owners
    ]
    anchors = [
        InventoryAnchor(
            sample_id_raw=generic_owner,
            material_name_raw="Alloy X",
            state_raw="sintered",
            role="Target",
            data_nature="Experimental",
            source_evidence=[generic_owner],
            confidence=0.9,
        ),
        *[
            InventoryAnchor(
                sample_id_raw=owner,
                material_name_raw="Alloy X",
                state_raw=f"sintered at {owner.removesuffix(' sample')}",
                role="Target",
                data_nature="Experimental",
                source_evidence=[owner],
                confidence=0.9,
            )
            for owner in owners
        ],
    ]

    result = materialize_candidate(anchors, [summary, *explicit])

    values = [
        prop["value_raw"]
        for item in result.document["items"]
        for prop in item["Extracted_Data"]["Properties"]
    ]
    assert values == ["612", "612", "612"]
    assert not any(
        row.code == "tensile_precision_duplicate_merged" for row in result.issues
    )


def test_tensile_precision_explicit_distinct_loser_owner_is_protected():
    explicit = _tensile_property(
        "1-1",
        value="1130",
        evidence="Sample 1-1 had an ultimate tensile strength of 1130 MPa.",
    )
    table = _table_tensile_property(
        "4-1",
        "1130 ± 13.0",
        "| Sample | UTS (MPa) |\n| 4-1 | 1130 ± 13.0 |",
        name="UTS",
    )

    result = materialize_candidate(
        [
            _material_anchor("1-1", material="alpha titanium alloy"),
            _material_anchor("4-1", material="alpha titanium alloy"),
        ],
        [explicit, table],
    )

    matching = [
        (item["Sample_ID"], prop["value_raw"])
        for item in result.document["items"]
        for prop in item["Extracted_Data"]["Properties"]
    ]
    assert matching == [("1-1", "1130"), ("4-1", "1130 ± 13.0")]
    assert not any(
        row.code == "tensile_precision_duplicate_merged" for row in result.issues
    )


def test_tensile_precision_two_distinct_precise_state_owners_are_protected():
    generic = _tensile_property(
        "A", value="900", evidence="A had an ultimate tensile strength of 900 MPa."
    )
    first = _table_tensile_property(
        "A [aged at 700 °C]",
        "900 ± 5",
        "| Sample | UTS (MPa) |\n| A [aged at 700 °C] | 900 ± 5 |",
        name="UTS",
    )
    second = _table_tensile_property(
        "A [aged at 800 °C]",
        "900 ± 5",
        "| Sample | UTS (MPa) |\n| A [aged at 800 °C] | 900 ± 5 |",
        name="UTS",
    )

    result = materialize_candidate(
        [
            _anchor("A", "as-built"),
            _anchor("A", "aged at 700 °C"),
            _anchor("A", "aged at 800 °C"),
        ],
        [generic, first, second],
    )

    values = [
        prop["value_raw"]
        for item in result.document["items"]
        for prop in item["Extracted_Data"]["Properties"]
        if prop["value_raw"] in {"900", "900 ± 5"}
    ]
    assert values.count("900") == 1
    assert values.count("900 ± 5") == 2
    assert not any(
        row.code == "tensile_precision_duplicate_merged" for row in result.issues
    )


def test_tensile_precision_table_value_absorbs_approximate_projection():
    approximate = _tensile_property(
        "A",
        value="~47",
        name="elongation",
        unit="%",
        evidence="A had an elongation of ~47%.",
    )
    precise = _table_tensile_property(
        "A",
        "47 ± 1",
        "| Sample | Elongation (%) |\n| A | 47 ± 1 |",
        name="elongation",
    )

    result = materialize_candidate([_material_anchor("A")], [approximate, precise])

    properties = result.document["items"][0]["Extracted_Data"]["Properties"]
    assert [row["value_raw"] for row in properties] == ["47 ± 1"]
    assert any(
        row.code == "core_tensile_approximate_shadow_quarantined"
        for row in result.issues
    )


def _source_block_survivor(
    sample: str = "A",
    *,
    condition: str = "650 °C",
    elongation_name: str = "elongation",
) -> tuple[list[PropertyFact], str]:
    source = (
        "| Property | A |\n"
        "| --- | --- |\n"
        "| YS (MPa) | 741 ± 24 |\n"
        "| UTS (MPa) | 803 ± 30 |\n"
        "| Elongation (%) | 3 ± 0.5 |"
    )
    evidence = (
        "| YS (MPa) | 741 ± 24 |",
        "| UTS (MPa) | 803 ± 30 |",
        "| Elongation (%) | 3 ± 0.5 |",
    )
    rows = _same_owner_complete_tensile_bundle(
        sample,
        ("741 ± 24", "803 ± 30", "3 ± 0.5"),
        evidence="placeholder",
        evidence_unit_id="",
        condition=condition,
        elongation_name=elongation_name,
    )
    return [
        fact.model_copy(
            update={
                "source_evidence": [row_evidence],
                "data": {
                    **fact.data,
                    "data_source": "text",
                    "source_evidence": [row_evidence],
                },
            }
        )
        for fact, row_evidence in zip(rows, evidence, strict=True)
    ], source


def test_source_block_complete_survivor_absorbs_single_member_projection():
    survivor, source = _source_block_survivor()
    loser = _tensile_property(
        "A",
        value="803",
        name="UTS",
        unit="MPa",
        condition="650 °C",
        evidence="The UTS at 650 °C was 803 MPa.",
    )

    result = materialize_candidate(
        [_material_anchor("A")], [loser, *survivor], source_text=source
    )

    properties = result.document["items"][0]["Extracted_Data"]["Properties"]
    assert {row["value_raw"] for row in properties} == {
        "741 ± 24",
        "803 ± 30",
        "3 ± 0.5",
    }
    issue = next(
        row
        for row in result.issues
        if row.code == "tensile_same_owner_bundle_member_duplicate_merged"
    )
    assert issue.actual["canonical_owner"] == "A"
    assert issue.actual["selected_semantic"] == "ultimate_tensile_strength"
    assert issue.actual["removed_fact"]["data"]["value_raw"] == "803"
    assert len(issue.actual["survivor_bundle_before_merge"]) == 3
    assert len(issue.actual["survivor_bundle_after_merge"]) == 3
    assert issue.evidence["survivor_source_binding"]["kind"] == "markdown_table"
    assert "The UTS at 650 °C was 803 MPa." in next(
        fact["source_evidence"]
        for fact in issue.actual["survivor_bundle_after_merge"]
        if fact["data"]["property_name_raw"] == "ultimate tensile strength"
    )


def test_absolute_result_in_comparative_prose_merges_into_richer_bundle():
    survivor, source = _source_block_survivor()
    evidence = (
        "The UTS of the A samples was slightly lower at 803 MPa, but the "
        "elongation increased to 3%."
    )
    loser = _tensile_property(
        "A",
        value="803",
        name="UTS",
        unit="MPa",
        condition="650 °C",
        evidence=evidence,
    )
    loser.data["raw_note"] = evidence

    result = materialize_candidate(
        [_material_anchor("A")], [loser, *survivor], source_text=source
    )

    properties = result.document["items"][0]["Extracted_Data"]["Properties"]
    assert {row["value_raw"] for row in properties} == {
        "741 ± 24",
        "803 ± 30",
        "3 ± 0.5",
    }
    issue = next(
        row
        for row in result.issues
        if row.code == "tensile_same_owner_bundle_member_duplicate_merged"
    )
    assert issue.actual["removed_fact"]["data"]["value_raw"] == "803"
    assert issue.actual["member_relation"]["precision_gains"][
        "uncertainty_added"
    ]


def test_prose_complete_survivor_absorbs_single_approximate_projection():
    source = (
        "At 650 °C, the measured YS was 741 ± 24 MPa, the UTS was "
        "803 ± 30 MPa, and elongation was 3 ± 0.5%."
    )
    survivor = _same_owner_complete_tensile_bundle(
        "A",
        ("741 ± 24", "803 ± 30", "3 ± 0.5"),
        evidence=source,
        evidence_unit_id="precise-prose",
        condition="650 °C",
    )
    fragments = (
        "the measured YS was 741 ± 24 MPa",
        "the UTS was 803 ± 30 MPa",
        "elongation was 3 ± 0.5%",
    )
    survivor = [
        fact.model_copy(
            update={
                "source_evidence": [fragment],
                "data": {**fact.data, "source_evidence": [fragment]},
            }
        )
        for fact, fragment in zip(survivor, fragments, strict=True)
    ]
    loser = _tensile_property(
        "A",
        value="around 3",
        name="elongation",
        unit="%",
        condition="650 °C",
        evidence="Elongation was around 3% at 650 °C.",
    )

    result = materialize_candidate(
        [_material_anchor("A")], [*survivor, loser], source_text=source
    )

    assert len(result.document["items"][0]["Extracted_Data"]["Properties"]) == 3
    issue = next(
        row
        for row in result.issues
        if row.code == "tensile_same_owner_bundle_member_duplicate_merged"
    )
    assert issue.actual["member_relation"]["precision_gains"][
        "approximation_removed"
    ]
    assert issue.evidence["survivor_source_binding"]["kind"] == "source_assertion"


def test_source_block_survivor_must_be_complete():
    survivor, source = _source_block_survivor()
    loser = _tensile_property(
        "A", value="803", name="UTS", unit="MPa", condition="650 °C"
    )

    result = materialize_candidate(
        [_material_anchor("A")], [loser, *survivor[:2]], source_text=source
    )

    assert not any(
        row.code == "tensile_same_owner_bundle_member_duplicate_merged"
        for row in result.issues
    )


def test_multi_assertion_projection_is_protected_after_exact_folding():
    survivor, source = _source_block_survivor()
    projections = [
        _tensile_property(
            "A",
            value="803",
            name="UTS",
            unit="MPa",
            condition="650 °C",
            evidence=evidence,
        )
        for evidence in (
            "The abstract reports a UTS of 803 MPa.",
            "The results report a UTS of 803 MPa.",
            "The conclusion reports a UTS of 803 MPa.",
        )
    ]

    result = materialize_candidate(
        [_material_anchor("A")], [*projections, *survivor], source_text=source
    )

    properties = result.document["items"][0]["Extracted_Data"]["Properties"]
    assert {row["value_raw"] for row in properties} == {
        "741 ± 24",
        "803 ± 30",
        "3 ± 0.5",
        "803",
    }
    assert not any(
        row.code == "tensile_same_owner_bundle_member_duplicate_merged"
        for row in result.issues
    )


def test_source_block_survivor_is_not_synthesized_across_paragraphs():
    survivor, _ = _source_block_survivor()
    source = "\n\n".join(
        [
            "The YS at 650 °C was 741 ± 24 MPa.",
            "The UTS at 650 °C was 803 ± 30 MPa.",
            "The elongation at 650 °C was 3 ± 0.5%.",
        ]
    )
    loser = _tensile_property(
        "A", value="803", name="UTS", unit="MPa", condition="650 °C"
    )

    result = materialize_candidate(
        [_material_anchor("A")], [loser, *survivor], source_text=source
    )

    assert not any(
        row.code == "tensile_same_owner_bundle_member_duplicate_merged"
        for row in result.issues
    )


def test_member_projection_rejects_multiple_complete_survivors():
    first, first_source = _source_block_survivor()
    second_source = first_source.replace("± 24", "± 20").replace("± 30", "± 25")
    second = [
        fact.model_copy(
            update={
                "source_evidence": [
                    fact.source_evidence[0]
                    .replace("± 24", "± 20")
                    .replace("± 30", "± 25")
                ],
                "data": {
                    **fact.data,
                    "value_raw": str(fact.data["value_raw"])
                    .replace("± 24", "± 20")
                    .replace("± 30", "± 25"),
                    "source_evidence": [
                        fact.source_evidence[0]
                        .replace("± 24", "± 20")
                        .replace("± 30", "± 25")
                    ],
                },
            }
        )
        for fact in first
    ]
    loser = _tensile_property(
        "A", value="803", name="UTS", unit="MPa", condition="650 °C"
    )

    result = materialize_candidate(
        [_material_anchor("A")],
        [loser, *first, *second],
        source_text=f"{first_source}\n\n{second_source}",
    )

    assert not any(
        row.code == "tensile_same_owner_bundle_member_duplicate_merged"
        for row in result.issues
    )


@pytest.mark.parametrize(
    ("loser_name", "loser_value"),
    [
        ("UTS", ">803"),
        ("UTS", "800–810"),
        ("UTS increase", "803"),
        ("UTS", "higher"),
    ],
)
def test_member_projection_protects_threshold_range_relative_and_qualitative(
    loser_name, loser_value
):
    survivor, source = _source_block_survivor()
    loser = _tensile_property(
        "A",
        value=loser_value,
        name=loser_name,
        unit="MPa",
        condition="650 °C",
        evidence=f"The reported result was {loser_value} MPa.",
    )

    result = materialize_candidate(
        [_material_anchor("A")], [loser, *survivor], source_text=source
    )

    assert not any(
        row.code == "tensile_same_owner_bundle_member_duplicate_merged"
        for row in result.issues
    )


def test_member_projection_rejects_condition_and_elongation_subtype_conflicts():
    survivor, source = _source_block_survivor(elongation_name="fracture elongation")
    wrong_condition = _tensile_property(
        "A", value="803", name="UTS", unit="MPa", condition="room temperature"
    )
    wrong_subtype = _tensile_property(
        "A", value="3", name="total elongation", unit="%", condition="650 °C"
    )

    result = materialize_candidate(
        [_material_anchor("A")],
        [wrong_condition, wrong_subtype, *survivor],
        source_text=source,
    )

    assert not any(
        row.code == "tensile_same_owner_bundle_member_duplicate_merged"
        for row in result.issues
    )


def test_member_projection_never_crosses_explicit_orientation_owners():
    survivor, source = _source_block_survivor(
        "A / Z", condition="Z orientation at 650 °C"
    )
    loser = _tensile_property(
        "A / X",
        value="803",
        name="UTS",
        unit="MPa",
        condition="X orientation at 650 °C",
    )

    result = materialize_candidate(
        [_material_anchor("A / X"), _material_anchor("A / Z")],
        [loser, *survivor],
        source_text=source,
    )

    assert not any(
        row.code == "tensile_same_owner_bundle_member_duplicate_merged"
        for row in result.issues
    )


def test_member_projection_dedup_is_input_order_deterministic():
    survivor, source = _source_block_survivor()
    losers = [
        _tensile_property(
            "A",
            value="803",
            name="UTS",
            unit="MPa",
            condition="650 °C",
            evidence="The UTS was 803 MPa.",
        ),
        _tensile_property(
            "A",
            value="3",
            name="elongation",
            unit="%",
            condition="650 °C",
            evidence="The elongation was 3%.",
        ),
    ]
    results = [
        materialize_candidate(
            [_material_anchor("A")], facts, source_text=source
        )
        for facts in (
            [*losers, *survivor],
            [*reversed(survivor), *reversed(losers)],
        )
    ]

    normalized_properties = []
    for result in results:
        properties = result.document["items"][0]["Extracted_Data"]["Properties"]
        normalized_properties.append(
            sorted(
                [
                    {
                        key: value
                        for key, value in row.items()
                        if key != "property_id_candidate"
                    }
                    for row in properties
                ],
                key=lambda row: row["property_name_raw"],
            )
        )
    assert normalized_properties[0] == normalized_properties[1]
    audits = [
        [
            issue.to_dict()
            for issue in result.issues
            if issue.code
            == "tensile_same_owner_bundle_member_duplicate_merged"
        ]
        for result in results
    ]
    assert audits[0] == audits[1]


@pytest.mark.parametrize(
    ("name", "value", "evidence"),
    [
        ("elongation", "45–49", "Elongation ranged from 45–49%."),
        ("elongation", "at least 47", "Elongation was at least 47%."),
        ("elongation increase", "47", "Elongation increased by 47% relative."),
    ],
)
def test_tensile_precision_range_threshold_and_relative_values_are_protected(
    name, value, evidence
):
    protected = _tensile_property(
        "A", value=value, name=name, unit="%", evidence=evidence
    )
    precise = _table_tensile_property(
        "A",
        "47 ± 1",
        "| Sample | Elongation (%) |\n| A | 47 ± 1 |",
        name="elongation",
    )

    result = materialize_candidate([_material_anchor("A")], [protected, precise])

    assert not any(
        row.code == "tensile_precision_duplicate_merged" for row in result.issues
    )
    assert any(
        prop["value_raw"] == value
        for item in result.document["items"]
        for prop in item["Extracted_Data"]["Properties"]
    )


def test_tensile_precision_survivor_is_stable_under_input_permutation():
    prose = _tensile_property(
        "A", value="959", name="ultimate tensile stress", evidence="A UTS was 959 MPa."
    )
    rounded = _table_tensile_property(
        "A",
        "959 ± 5.3",
        "| Sample | Avg. UTS (MPa) |\n| A | 959 ± 5.3 |",
        name="Avg. UTS",
    )
    precise = _table_tensile_property(
        "A",
        "959 ± 5.31",
        "| Sample | UTS (MPa) |\n| A | 959 ± 5.31 |",
        name="UTS (MPa)",
    )

    results = [
        materialize_candidate([_material_anchor("A")], facts)
        for facts in ([prose, rounded, precise], [precise, prose, rounded])
    ]

    for result in results:
        properties = result.document["items"][0]["Extracted_Data"]["Properties"]
        assert [row["value_raw"] for row in properties] == ["959 ± 5.31"]
        issues = [
            row
            for row in result.issues
            if row.code == "tensile_precision_duplicate_merged"
        ]
        assert {
            row.actual["removed_fact"]["data"]["value_raw"] for row in issues
        } == {"959", "959 ± 5.3"}


def test_numeric_citation_is_not_confused_with_digit_in_alloy_name():
    evidence = (
        "| Properties | Ti-6Al-4V | Current work |\n"
        "| Yield Strength (MPa) | 948 [6] | 900 |"
    )
    fact = _table_tensile_property("Ti-6Al-4V", "948", evidence)

    result = materialize_candidate(
        [_material_anchor("Ti-6Al-4V", material="Ti-6Al-4V")], [fact]
    )

    assert result.document["items"][0]["Sample_ID"] == (
        "Ti-6Al-4V [6] [reference]"
    )


def test_cited_tensile_facts_with_same_marker_share_one_reference_owner():
    yield_evidence = (
        "| Properties | WAAM | Current work |\n"
        "| Yield Strength (MPa) | 856 ± 16 [39] | 900 |"
    )
    uts_evidence = (
        "| Properties | WAAM | Current work |\n"
        "| Ultimate Tensile Strength (MPa) | 993 ± 15 [39] | 1020 |"
    )
    facts = [
        _table_tensile_property("WAAM", "856 ± 16", yield_evidence),
        _table_tensile_property(
            "WAAM", "993 ± 15", uts_evidence, name="ultimate tensile strength"
        ),
    ]

    result = materialize_candidate(
        [_material_anchor("WAAM", state="WAAM")], facts
    )

    assert [row["Sample_ID"] for row in result.document["items"]] == [
        "WAAM [39] [reference]"
    ]
    properties = result.document["items"][0]["Extracted_Data"]["Properties"]
    assert {row["value_raw"] for row in properties} == {"856 ± 16", "993 ± 15"}
    assert sum(
        row.code == "reference_tensile_owner_recovered" for row in result.issues
    ) == 2


def test_standard_qualified_table_owner_becomes_reference():
    evidence = (
        "| Material property | WAAM / Horizontal | Wrought (AMS 4928) |\n"
        "| Yield strength (MPa) | 842 ± 14 | 861 |"
    )
    fact = _table_tensile_property("Wrought (AMS 4928)", "861", evidence)

    result = materialize_candidate(
        [_material_anchor("Wrought (AMS 4928)", state="wrought")], [fact]
    )

    item = result.document["items"][0]
    assert item["Sample_ID"] == "Wrought (AMS 4928) [reference]"
    assert item["Role"] == "Reference"
    issue = next(
        row
        for row in result.issues
        if row.code == "reference_tensile_owner_recovered"
    )
    assert issue.actual["marker"] == "AMS 4928"
    assert issue.actual["marker_source"] == "header_cell"


def test_cited_row_label_gets_independent_reference_owner():
    evidence = (
        "| Material | Yield strength (MPa) | UTS (MPa) |\n"
        "| Cast alloy 625 [6] | 350 | 700 |"
    )
    fact = _table_tensile_property("Cast alloy 625 [6]", "350", evidence)

    result = materialize_candidate(
        [_material_anchor("Cast alloy 625 [6]", material="Alloy 625")], [fact]
    )

    item = result.document["items"][0]
    assert item["Sample_ID"] == "Cast alloy 625 [6] [reference]"
    assert item["Role"] == "Reference"
    issue = next(
        row
        for row in result.issues
        if row.code == "reference_tensile_owner_recovered"
    )
    assert issue.actual["marker_source"] == "owner_cell"
    assert issue.actual["selected_column"] == 1


def test_cited_tensile_row_stays_reference_when_target_retains_non_tensile_fact():
    evidence = (
        "| Material | Yield strength (MPa) | UTS (MPa) | Elongation (%) | Hardness (HV) |\n"
        "| Cast alloy [6] | 350 | 710 | 48 | 200 |"
    )
    facts = [
        _table_tensile_property("Cast alloy [6]", "350", evidence),
        _table_tensile_property(
            "Cast alloy [6]", "710", evidence, name="ultimate tensile strength"
        ),
        _table_tensile_property(
            "Cast alloy [6]", "48", evidence, name="elongation"
        ),
        _table_tensile_property(
            "Cast alloy [6]", "200", evidence, name="Vickers hardness"
        ),
    ]
    facts[-1].data["unit_raw"] = "HV"

    result = materialize_candidate(
        # Projected table anchors may preserve only the row label.  The
        # recovered Reference then uses that label as its material descriptor;
        # this must not redirect the citation-bearing Target into the Reference.
        [_material_anchor("Cast alloy [6]", material=None)], facts
    )

    by_role = {item["Role"]: item for item in result.document["items"]}
    assert set(by_role) == {"Target", "Reference"}
    assert {
        prop["property_name_raw"]
        for prop in by_role["Reference"]["Extracted_Data"]["Properties"]
    } == {"yield strength", "ultimate tensile strength", "elongation"}
    assert {
        prop["property_name_raw"]
        for prop in by_role["Target"]["Extracted_Data"]["Properties"]
    } == {"Vickers hardness"}


def test_same_literal_target_and_reference_labels_keep_cited_table_value_on_reference():
    evidence = (
        "| Samples | Yield stress [MPa] | UTS [MPa] |\n"
        "| Cast alloy 625 [6] | 350 | 710 |"
    )
    fact = _raw_property("Cast alloy 625 [6]", "UTS", "710", evidence).model_copy(
        update={
            "data": {
                **_raw_property("Cast alloy 625 [6]", "UTS", "710", evidence).data,
                "unit_raw": "MPa",
                "data_source": "table",
                "source_evidence": [evidence],
            }
        }
    )
    anchors = [
        InventoryAnchor(
            sample_id_raw="Cast alloy 625 [6]",
            material_name_raw="Alloy 625",
            state_raw=None,
            role="Target",
            data_nature="Experimental",
            source_evidence=["current work Cast alloy 625 [6]"],
            confidence=0.9,
        ),
        InventoryAnchor(
            sample_id_raw="Cast alloy 625 [6]",
            material_name_raw="Cast alloy 625",
            state_raw="literature-reported",
            role="Reference",
            data_nature="Literature_Experimental",
            source_evidence=[evidence],
            confidence=0.9,
        ),
    ]

    result = materialize_candidate(anchors, [fact], source_text=evidence)

    by_role = {item["Role"]: item for item in result.document["items"]}
    # The empty Target anchor is intentionally not materialized; the cited
    # value must nevertheless survive under a distinct Reference identity.
    assert set(by_role) == {"Reference"}
    assert by_role["Reference"]["Sample_ID"] == "Cast alloy 625 [6] [reference]"
    assert {
        prop["value_raw"]
        for prop in by_role["Reference"]["Extracted_Data"]["Properties"]
    } == {"710"}


def test_author_year_value_cell_gets_independent_reference_owner():
    evidence = (
        "| Property | LPBF | Current work |\n"
        "| Yield strength (MPa) | 370 (Amato et al., 2012) | 400 |"
    )
    fact = _table_tensile_property("LPBF", "370", evidence)

    result = materialize_candidate(
        [_material_anchor("LPBF", material="Inconel 625", state="HIPed")],
        [fact],
    )

    item = result.document["items"][0]
    assert item["Sample_ID"] == "LPBF Amato et al., 2012 [reference]"
    assert item["Role"] == "Reference"


def test_uncited_current_study_table_column_stays_target():
    evidence = (
        "| Properties | WAAM (this work) | Wrought |\n"
        "| Yield Strength (MPa) | 900 | 948 [37] |"
    )
    fact = _table_tensile_property("WAAM (this work)", "900", evidence)

    result = materialize_candidate(
        [_material_anchor("WAAM (this work)", state="as-built")], [fact]
    )

    assert result.document["items"][0]["Role"] == "Target"
    assert not any(
        row.code == "reference_tensile_owner_recovered" for row in result.issues
    )


def test_test_method_standard_does_not_create_reference_owner():
    evidence = (
        "| Properties | Alloy A |\n"
        "| Yield Strength (MPa) | 900 |"
    )
    fact = _table_tensile_property(
        "Alloy A", "900", evidence, test_standard="ASTM E8"
    )

    result = materialize_candidate([_material_anchor("Alloy A")], [fact])

    assert result.document["items"][0]["Role"] == "Target"
    assert not any(
        row.code == "reference_tensile_owner_recovered" for row in result.issues
    )


@pytest.mark.parametrize(
    ("evidence", "value"),
    [
        (
            "| Properties | Alloy A | Alloy A |\n"
            "| Yield Strength (MPa) | 900 [12] | 910 [13] |",
            "900",
        ),
        (
            "| Properties | Alloy A |\n"
            "| Yield Strength (MPa) | 910 [12] |",
            "900",
        ),
    ],
)
def test_ambiguous_or_value_mismatched_citation_stays_target(
    evidence: str, value: str
):
    fact = _table_tensile_property("Alloy A", value, evidence)

    result = materialize_candidate([_material_anchor("Alloy A")], [fact])

    assert all(row["Role"] == "Target" for row in result.document["items"])
    assert not any(
        row.code == "reference_tensile_owner_recovered" for row in result.issues
    )


def test_cited_non_tensile_table_fact_stays_target():
    evidence = "| Properties | Alloy A |\n| Vickers hardness | 332 [39] |"
    fact = _table_tensile_property(
        "Alloy A", "332", evidence, name="Vickers hardness"
    )
    fact.data["unit_raw"] = "HV"

    result = materialize_candidate([_material_anchor("Alloy A")], [fact])

    assert result.document["items"][0]["Role"] == "Target"
    assert not any(
        row.code == "reference_tensile_owner_recovered" for row in result.issues
    )


def test_cited_non_tensile_table_fact_uses_exact_numeric_reference_sibling():
    evidence = (
        "| Properties | WEBAM |\n"
        "| Vickers hardness (HV) | 319 [45] |"
    )
    fact = _table_tensile_property(
        "WEBAM", "319", evidence, name="Vickers hardness"
    )
    fact.data["unit_raw"] = "HV"
    existing_reference = InventoryAnchor(
        sample_id_raw="WEBAM [44] [reference]",
        material_name_raw="Ti-6Al-4V",
        state_raw=None,
        role="Reference",
        data_nature="Literature_Experimental",
        source_evidence=["WEBAM [44]"],
        confidence=0.9,
    )

    result = materialize_candidate(
        [_material_anchor("WEBAM", material="Ti-6Al-4V"), existing_reference],
        [fact],
    )

    assert len(result.document["items"]) == 1
    item = result.document["items"][0]
    assert item["Sample_ID"] == "WEBAM [45] [reference]"
    assert item["Role"] == "Reference"
    assert any(row.code == "reference_property_owner_recovered" for row in result.issues)


def test_cited_fact_splits_from_uncited_target_fact_on_same_item():
    cited_evidence = (
        "| Properties | WAAM | Current work |\n"
        "| Yield Strength (MPa) | 856 [39] | 900 |"
    )
    target_evidence = (
        "| Properties | WAAM |\n"
        "| Ultimate Tensile Strength (MPa) | 1020 |"
    )
    facts = [
        _table_tensile_property("WAAM", "856", cited_evidence),
        _table_tensile_property(
            "WAAM", "1020", target_evidence, name="ultimate tensile strength"
        ),
    ]

    result = materialize_candidate([_material_anchor("WAAM")], facts)

    assert {
        (row["Sample_ID"], row["Role"]): {
            prop["value_raw"] for prop in row["Extracted_Data"]["Properties"]
        }
        for row in result.document["items"]
    } == {
        ("WAAM", "Target"): {"1020"},
        ("WAAM [39] [reference]", "Reference"): {"856"},
    }


def test_prose_citation_continuation_recovers_adjacent_reference_bundles():
    attribution = (
        "Amato et al. reported an increase in strength after HIPing."
    )
    lpbf_evidence = (
        "The reported UTS, YS, and elongation values averaged 900 MPa, "
        "370 MPa, and 58%, respectively, for LPBF specimens."
    )
    epbf_evidence = (
        "EPBF specimens were reported to have a UTS of 330 MPa, YS of "
        "770 MPa, and elongation of 69% by the same study."
    )
    source_text = " ".join([attribution, lpbf_evidence, epbf_evidence])
    facts = [
        _table_tensile_property(
            "LPBF", "900", lpbf_evidence, name="UTS", data_source="text"
        ),
        _table_tensile_property(
            "LPBF", "370", lpbf_evidence, name="YS", data_source="text"
        ),
        _table_tensile_property(
            "LPBF", "58", lpbf_evidence, name="elongation", data_source="text"
        ),
        _table_tensile_property(
            "EPBF", "330", epbf_evidence, name="UTS", data_source="text"
        ),
        _table_tensile_property(
            "EPBF", "770", epbf_evidence, name="YS", data_source="text"
        ),
        _table_tensile_property(
            "EPBF", "69", epbf_evidence, name="elongation", data_source="text"
        ),
        _table_tensile_property(
            "LPBF",
            "910",
            "In the present work, LPBF had a UTS of 910 MPa.",
            name="UTS",
            data_source="text",
        ),
    ]

    result = materialize_candidate(
        [
            _material_anchor("LPBF", material="Inconel 625"),
            _material_anchor("EPBF", material="Inconel 625"),
            _reference_material_anchor(
                "LPBF Amato et al.",
                material="LPBF printed Inconel 625",
                state="HIPed",
                evidence=lpbf_evidence,
            ),
            _reference_material_anchor(
                "EPBF Amato et al.",
                material="EPBF printed Inconel 625",
                state="HIPed",
                evidence=epbf_evidence,
            ),
        ],
        facts,
        source_text=(
            source_text
            + "\n\nIn the present work, LPBF had a UTS of 910 MPa."
        ),
    )

    by_sample = {item["Sample_ID"]: item for item in result.document["items"]}
    assert {
        sample: (item["Role"], item["Data_Nature"])
        for sample, item in by_sample.items()
    } == {
        "LPBF": ("Target", "Experimental"),
        "LPBF Amato et al. [reference]": (
            "Reference",
            "Literature_Experimental",
        ),
        "EPBF Amato et al. [reference]": (
            "Reference",
            "Literature_Experimental",
        ),
    }
    assert {
        prop["value_raw"]
        for prop in by_sample["LPBF"]["Extracted_Data"]["Properties"]
    } == {"910"}
    assert {
        prop["value_raw"]
        for prop in by_sample["LPBF Amato et al. [reference]"]["Extracted_Data"][
            "Properties"
        ]
    } == {"900", "370", "58"}
    assert {
        prop["value_raw"]
        for prop in by_sample["EPBF Amato et al. [reference]"]["Extracted_Data"][
            "Properties"
        ]
    } == {"330", "770", "69"}
    issues = [
        issue
        for issue in result.issues
        if issue.code == "reference_tensile_prose_owner_recovered"
    ]
    assert len(issues) == 6
    assert {issue.actual["chain_type"] for issue in issues} == {
        "reported_values_continuation",
        "same_study_continuation",
    }
    assert {issue.actual["author_marker"] for issue in issues} == {
        "Amato et al."
    }
    assert all(issue.actual["source_paragraph"] == source_text for issue in issues)
    assert all(issue.actual["fact"]["sample_id_raw"] in {"LPBF", "EPBF"} for issue in issues)


def test_prose_citation_continuation_splits_same_author_reference_samples():
    attribution = (
        "Amato et al. reported an increase in strength after HIPing."
    )
    lpbf_evidence = "The reported UTS value was 900 MPa for LPBF specimens."
    epbf_evidence = (
        "EPBF specimens were reported to have a UTS of 330 MPa by the same study."
    )
    source_text = " ".join([attribution, lpbf_evidence, epbf_evidence])
    reference_anchors = [
        InventoryAnchor(
            sample_id_raw="Amato et al.",
            material_name_raw="LPBF printed Inconel 625",
            state_raw="HIPed",
            role="Reference",
            data_nature="Literature_Experimental",
            source_evidence=[attribution],
            confidence=0.85,
        ),
        InventoryAnchor(
            sample_id_raw="Amato et al.",
            material_name_raw="EPBF printed Inconel 625",
            state_raw="HIPed",
            role="Reference",
            data_nature="Literature_Experimental",
            source_evidence=[epbf_evidence],
            confidence=0.85,
        ),
    ]
    facts = [
        _table_tensile_property(
            "Amato et al.",
            "900",
            lpbf_evidence,
            name="UTS",
            data_source="text",
        ),
        _table_tensile_property(
            "Amato et al.",
            "330",
            epbf_evidence,
            name="UTS",
            data_source="text",
        ),
    ]

    result = materialize_candidate(
        [
            _material_anchor("LPBF", material="Inconel 625"),
            _material_anchor("EPBF", material="Inconel 625"),
            *reference_anchors,
        ],
        facts,
        source_text=source_text,
    )

    reference_items = {
        item["Sample_ID"]: item
        for item in result.document["items"]
        if item["Role"] == "Reference"
    }
    assert set(reference_items) == {
        "LPBF printed Inconel 625 Amato et al. [reference]",
        "EPBF printed Inconel 625 Amato et al. [reference]",
    }
    issues = [
        issue
        for issue in result.issues
        if issue.code == "reference_tensile_prose_owner_recovered"
    ]
    assert len(issues) == 2
    assert {issue.actual["before_owner_role"] for issue in issues} == {"reference"}
    assert {issue.actual["parent_selection_rule"] for issue in issues} == {
        "exact_anchor_evidence",
        "unique_material_discriminator",
    }


def test_prose_citation_continuation_recovers_fact_local_previous_work():
    antecedent = (
        "The alloy design concept was proposed in our previous work [22]."
    )
    evidence = (
        "Ultrahigh yield strength and uniform elongation of 1.34 GPa and "
        "13.9% were obtained in the prototype alloy."
    )
    fact = _table_tensile_property(
        "Prototype alloy",
        "1.34",
        evidence,
        name="yield strength",
        data_source="text",
    )
    fact.data["unit_raw"] = "GPa"
    fact.data["raw_note"] = "from previous work [22]"

    result = materialize_candidate(
        [
            _material_anchor("Prototype alloy", material="FeMnCoCrN"),
            _reference_material_anchor(
                "Prototype alloy [22]",
                material="FeMnCoCrN",
                evidence=antecedent,
            ),
        ],
        [fact],
        source_text=f"{antecedent} {evidence}",
    )

    item = result.document["items"][0]
    assert item["Sample_ID"] == "Prototype alloy [22] [reference]"
    assert item["Role"] == "Reference"
    issue = next(
        issue
        for issue in result.issues
        if issue.code == "reference_tensile_prose_owner_recovered"
    )
    assert issue.actual["chain_type"] == "previous_work_continuation"
    assert issue.actual["author_marker"] == "[22]"


def test_previous_work_continuation_collapses_duplicate_inventory_and_table_anchors():
    """A duplicate target anchor must not block a cited-prose owner split."""

    antecedent = (
        "The alloy design concept was proposed in our previous work [22]."
    )
    evidence = (
        "Ultrahigh yield strength and uniform elongation of 1.34 GPa and "
        "13.9% were obtained in the prototype alloy."
    )
    fact = _table_tensile_property(
        "Prototype alloy",
        "1.34",
        evidence,
        name="yield strength",
        data_source="text",
    )
    fact.data["unit_raw"] = "GPa"
    fact.data["raw_note"] = "from previous work [22]"

    # The extraction planner can contribute a label-only deterministic anchor
    # in addition to the richer inventory anchor for the same source item.
    # They must be collapsed before selecting a citation parent.
    anchors = [
        _material_anchor("Prototype alloy", material="FeMnCoCrN"),
        _material_anchor("Prototype alloy", material=""),
        _reference_material_anchor(
            "Prototype alloy [22]",
            material="FeMnCoCrN",
            evidence=antecedent,
        ),
    ]
    result = materialize_candidate(
        anchors,
        [fact],
        source_text=f"{antecedent} {evidence}",
    )

    assert result.document["items"][0]["Role"] == "Reference"
    assert result.document["items"][0]["Sample_ID"] == (
        "Prototype alloy [22] [reference]"
    )
    assert any(
        issue.code == "reference_tensile_prose_owner_recovered"
        for issue in result.issues
    )


@pytest.mark.parametrize(
    "raw_note",
    ["", "from previous work", "from previous work [23]"],
)
def test_previous_work_continuation_requires_matching_fact_local_citation(
    raw_note: str,
):
    antecedent = "The alloy design was proposed in our previous work [22]."
    evidence = "The reported yield strength was 1.34 GPa."
    fact = _table_tensile_property(
        "Prototype alloy",
        "1.34",
        evidence,
        name="yield strength",
        data_source="text",
    )
    fact.data["unit_raw"] = "GPa"
    fact.data["raw_note"] = raw_note

    result = materialize_candidate(
        [_material_anchor("Prototype alloy", material="FeMnCoCrN")],
        [fact],
        source_text=f"{antecedent} {evidence}",
    )

    assert result.document["items"][0]["Role"] == "Target"
    assert not any(
        issue.code == "reference_tensile_prose_owner_recovered"
        for issue in result.issues
    )


@pytest.mark.parametrize(
    "source_text",
    [
        (
            "Alpha et al. and Beta et al. reported different responses. "
            "The reported UTS value was 900 MPa for LPBF specimens."
        ),
        (
            "Alpha et al. reported the heat treatment. A separate observation "
            "was then discussed. The reported UTS value was 900 MPa for LPBF."
        ),
        (
            "Alpha et al. reported earlier results.\n\n"
            "The reported UTS value was 900 MPa for LPBF."
        ),
        (
            "Alpha et al. reported earlier results. The reported UTS value in "
            "the present work was 900 MPa for LPBF."
        ),
        "The reported UTS value was 900 MPa for LPBF.",
    ],
)
def test_prose_citation_continuation_protects_ambiguous_or_current_text(
    source_text: str,
):
    evidence = next(
        sentence
        for paragraph in source_text.splitlines()
        for sentence in paragraph.split(". ")
        if "UTS value" in sentence
    ).rstrip(".") + "."
    fact = _table_tensile_property(
        "LPBF", "900", evidence, name="UTS", data_source="text"
    )

    result = materialize_candidate(
        [_material_anchor("LPBF", material="Inconel 625")],
        [fact],
        source_text=source_text,
    )

    assert result.document["items"][0]["Role"] == "Target"
    assert not any(
        issue.code == "reference_tensile_prose_owner_recovered"
        for issue in result.issues
    )


def test_prose_citation_continuation_excludes_table_relative_and_reference_facts():
    attribution = "Alpha et al. reported the comparison."
    continuation = "The reported UTS value was 900 MPa for LPBF."
    source_text = f"{attribution} {continuation}"
    table = _table_tensile_property(
        "LPBF",
        "900",
        "| Property | LPBF |\n| UTS (MPa) | 900 |",
        name="UTS",
        data_source="table",
    )
    relative = _table_tensile_property(
        "LPBF",
        "50",
        continuation,
        name="UTS relative change",
        data_source="text",
    )
    reference = _table_tensile_property(
        "Published LPBF",
        "900",
        continuation,
        name="UTS",
        data_source="text",
    )
    reference_anchor = InventoryAnchor(
        sample_id_raw="Published LPBF",
        material_name_raw="Inconel 625",
        state_raw=None,
        role="Reference",
        data_nature="Literature_Experimental",
        source_evidence=[attribution],
        confidence=0.9,
    )

    result = materialize_candidate(
        [_material_anchor("LPBF", material="Inconel 625"), reference_anchor],
        [table, relative, reference],
        source_text=(
            source_text
            + "\n\n| Property | LPBF |\n| UTS (MPa) | 900 |"
        ),
    )

    assert not any(
        issue.code == "reference_tensile_prose_owner_recovered"
        for issue in result.issues
    )


def test_direct_author_tensile_sentence_routes_to_reference_and_clears_borrowed_context():
    evidence = (
        "Mostafaei et al. reported an ultimate tensile strength of 690 MPa "
        "for binder-jetted Alloy 625."
    )
    fact = _table_tensile_property(
        "Binder-jetted Alloy 625",
        "690",
        evidence,
        name="UTS",
        data_source="text",
    )
    fact.data["test_condition_raw"] = "room temperature"
    fact.data["test_specimen_raw"] = "ASTM E8 specimen"

    result = materialize_candidate(
        [
            _material_anchor("Binder-jetted Alloy 625", material="Alloy 625"),
            _reference_material_anchor(
                "Binder-jetted Alloy 625 (Mostafaei et al.)",
                material="Alloy 625",
                evidence=evidence,
            ),
        ],
        [fact],
        source_text=evidence,
    )

    item = result.document["items"][0]
    assert item["Role"] == "Reference"
    assert item["Sample_ID"] == (
        "Binder-jetted Alloy 625 (Mostafaei et al.) [reference]"
    )
    prop = item["Extracted_Data"]["Properties"][0]
    assert prop["test_condition_raw"] in {"", None}
    assert prop["test_specimen_raw"] in {"", None}
    issue = next(
        row
        for row in result.issues
        if row.code == "reference_tensile_direct_author_owner_recovered"
    )
    assert issue.actual["chain_type"] == "direct_author_attribution"
    assert issue.actual["cleared_unproven_context"] == {
        "test_condition_raw": "room temperature",
        "test_specimen_raw": "ASTM E8 specimen",
    }


def test_direct_author_tensile_without_existing_reference_anchor_stays_target():
    evidence = "Mostafaei et al. reported a UTS of 690 MPa for Alloy 625."
    fact = _table_tensile_property(
        "Alloy 625", "690", evidence, name="UTS", data_source="text"
    )

    result = materialize_candidate(
        [_material_anchor("Alloy 625", material="Alloy 625")],
        [fact],
        source_text=evidence,
    )

    assert result.document["items"][0]["Role"] == "Target"
    assert not any(
        row.code == "reference_tensile_direct_author_owner_recovered"
        for row in result.issues
    )


def test_paper007_rich_reference_owners_route_direct_and_pronoun_tensile_facts():
    direct = (
        "For binder jetting as-sintered parts, Mostafaei et al. reported "
        "values of UTS and YS of 612 MPa and 327 MPa, respectively."
    )
    continuation = (
        "They showed that following a solutionizing treatment, the strength "
        "decreased to 587 MPa."
    )
    aged_sentence = (
        "Finally, the UTS and elongation (reported as strain by this study) "
        "were 697 MPa and 30%, following aging for 60 h at 745 °C "
        "(Mostafaei et al., 2016b)."
    )
    as_fabricated_sentence = (
        "This was in contrast to the as-fabricated values that included UTS "
        "of 1041 ± 36 MPa and ductility of 33% ± 1% "
        "(Marchese et al., 2018)."
    )
    as_sintered = "binder jetting as-sintered (Mostafaei et al., 2016b)"
    solutionized = "binder jetting solutionized (Mostafaei et al., 2016b)"
    aged = "binder jetting aged (Mostafaei et al., 2016b)"
    as_fabricated = "LPBF as-fabricated (Marchese et al., 2018)"
    facts = [
        _table_tensile_property(
            as_sintered, "612", direct, name="UTS", data_source="text"
        ),
        _table_tensile_property(
            as_sintered, "327", direct, name="YS", data_source="text"
        ),
        _table_tensile_property(
            solutionized,
            "587",
            continuation,
            name="UTS",
            data_source="text",
        ),
        _table_tensile_property(
            aged,
            "697",
            "were 697 MPa and 30%",
            name="UTS",
            data_source="text",
        ),
        _table_tensile_property(
            as_fabricated,
            "1041 ± 36",
            "UTS of 1041 ± 36 MPa",
            name="UTS",
            data_source="text",
        ),
    ]
    anchors = [
        _reference_material_anchor(
            as_sintered,
            material="Inconel 625",
            state="as-sintered",
            evidence=direct,
        ),
        _reference_material_anchor(
            solutionized,
            material="Inconel 625",
            state="solutionizing treatment",
            evidence=continuation,
        ),
        _reference_material_anchor(
            aged,
            material="Inconel 625",
            state="aged",
            evidence=aged_sentence,
        ),
        _reference_material_anchor(
            as_fabricated,
            material="Inconel 625",
            state="as-fabricated",
            evidence=as_fabricated_sentence,
        ),
    ]

    result = materialize_candidate(
        anchors,
        facts,
        source_text=(
            f"{direct} {continuation} {aged_sentence} "
            f"{as_fabricated_sentence}"
        ),
    )

    by_sample = {item["Sample_ID"]: item for item in result.document["items"]}
    assert set(by_sample) == {
        f"{as_sintered} [reference]",
        f"{solutionized} [reference]",
        f"{aged} [reference]",
        f"{as_fabricated} [reference]",
    }
    assert {
        prop["value_raw"]
        for prop in by_sample[f"{as_sintered} [reference]"]["Extracted_Data"][
            "Properties"
        ]
    } == {"612", "327"}
    assert {
        prop["value_raw"]
        for prop in by_sample[f"{solutionized} [reference]"]["Extracted_Data"][
            "Properties"
        ]
    } == {"587"}
    assert {
        prop["value_raw"]
        for prop in by_sample[f"{aged} [reference]"]["Extracted_Data"][
            "Properties"
        ]
    } == {"697"}
    assert {
        prop["value_raw"]
        for prop in by_sample[f"{as_fabricated} [reference]"]["Extracted_Data"][
            "Properties"
        ]
    } == {"1041 ± 36"}
    assert {
        issue.code
        for issue in result.issues
        if issue.code.startswith("reference_tensile_")
    } >= {
        "reference_tensile_direct_author_owner_recovered",
        "reference_tensile_pronoun_continuation_owner_recovered",
        "reference_tensile_literal_citation_owner_recovered",
    }


def test_adjacent_they_showed_continues_one_direct_author_reference():
    antecedent = (
        "Marchese et al. reported mechanical properties for the WAAM alloy."
    )
    evidence = "They showed that the UTS reached 773 MPa after heat treatment."
    fact = _table_tensile_property(
        "WAAM alloy", "773", evidence, name="UTS", data_source="text"
    )

    result = materialize_candidate(
        [
            _material_anchor("WAAM alloy", material="Ti-6Al-4V"),
            _reference_material_anchor(
                "WAAM alloy (Marchese et al.)",
                material="Ti-6Al-4V",
                evidence=antecedent,
            ),
        ],
        [fact],
        source_text=f"{antecedent} {evidence}",
    )

    assert result.document["items"][0]["Role"] == "Reference"
    issue = next(
        row
        for row in result.issues
        if row.code == (
            "reference_tensile_pronoun_continuation_owner_recovered"
        )
    )
    assert issue.actual["author_marker"] == "Marchese et al."
    assert issue.actual["chain_type"] == "pronoun_continuation"


def test_literal_owner_plus_unique_numeric_citation_routes_prose_reference():
    evidence = (
        "The cast alloy 625 [11] exhibited an ultimate tensile strength of "
        "760 MPa."
    )
    fact = _table_tensile_property(
        "cast alloy 625", "760", evidence, name="UTS", data_source="text"
    )

    result = materialize_candidate(
        [
            _material_anchor("cast alloy 625", material="Alloy 625"),
            _reference_material_anchor(
                "cast alloy 625 [11]",
                material="Alloy 625",
                evidence=evidence,
            ),
        ],
        [fact],
        source_text=evidence,
    )

    item = result.document["items"][0]
    assert item["Role"] == "Reference"
    assert item["Sample_ID"] == "cast alloy 625 [11] [reference]"
    assert any(
        row.code == "reference_tensile_literal_citation_owner_recovered"
        for row in result.issues
    )


@pytest.mark.parametrize(
    "source_text,evidence",
    [
        (
            "Mostafaei et al. and Amato et al. reported UTS values of 690 MPa.",
            "Mostafaei et al. and Amato et al. reported UTS values of 690 MPa.",
        ),
        (
            "Mostafaei et al. reported prior results.\n\n"
            "They showed that the UTS was 690 MPa.",
            "They showed that the UTS was 690 MPa.",
        ),
        (
            "Mostafaei et al. reported the present study UTS of 690 MPa.",
            "Mostafaei et al. reported the present study UTS of 690 MPa.",
        ),
        (
            "The cast alloy 625 [11, 12] had a UTS of 690 MPa.",
            "The cast alloy 625 [11, 12] had a UTS of 690 MPa.",
        ),
    ],
)
def test_direct_reference_routing_fails_closed_on_ambiguity_or_scope_boundary(
    source_text: str, evidence: str
):
    fact = _table_tensile_property(
        "cast alloy 625", "690", evidence, name="UTS", data_source="text"
    )

    result = materialize_candidate(
        [_material_anchor("cast alloy 625", material="Alloy 625")],
        [fact],
        source_text=source_text,
    )

    assert result.document["items"][0]["Role"] == "Target"
    assert not any(
        row.code
        in {
            "reference_tensile_direct_author_owner_recovered",
            "reference_tensile_pronoun_continuation_owner_recovered",
            "reference_tensile_literal_citation_owner_recovered",
        }
        for row in result.issues
    )


def test_numeric_tensile_table_row_does_not_collapse_explicit_multiple_owners():
    evidence = (
        "| Samples | UTS [MPa] |\n"
        "| WA and GA samples sintered at 1270 °C | 386 ± 15 |"
    )
    fact = _tensile_property(
        "WA and GA samples sintered at 1270 °C",
        evidence=evidence,
    )
    fact.data["value_raw"] = "386 ± 15"
    fact.data["data_source"] = "table"

    result = materialize_candidate(
        [
            _anchor("WA", "sintered at 1270 °C"),
            _anchor("GA", "sintered at 1270 °C"),
        ],
        [fact],
    )

    assert result.document["items"] == []
    assert any(issue.code == "unresolved_sample_alias" for issue in result.issues)
    assert not any(
        issue.code == "numeric_tensile_owner_recovered" for issue in result.issues
    )


def test_numeric_tensile_standard_threshold_is_not_recovered_to_target():
    fact = _tensile_property(
        "ASTM F3056-14",
        evidence="minimum ultimate tensile strength required by ASTM F3056-14 was 0.485 GPa",
    )
    fact.data["value_raw"] = "0.485"
    fact.data["unit_raw"] = "GPa"
    fact.data["test_standard_raw"] = "ASTM F3056-14"

    result = materialize_candidate([_anchor("Alloy-A")], [fact])

    assert result.document["items"] == []
    assert any(issue.code == "unresolved_sample_alias" for issue in result.issues)
    assert not any(
        issue.code == "numeric_tensile_owner_recovered" for issue in result.issues
    )


def test_numeric_tensile_owner_recovers_from_two_resolved_sibling_semantics():
    evidence = (
        "The yield strength was 482 ± 1 MPa, the ultimate tensile strength was "
        "539 ± 1 MPa, and the elongation was 8.8 ± 0.7%."
    )
    yield_fact = _tensile_property("Alloy-A", evidence=evidence)
    yield_fact.data["property_name_raw"] = "yield strength"
    yield_fact.data["value_raw"] = "482 ± 1"
    uts_fact = _tensile_property("Alloy-A", evidence=evidence)
    uts_fact.data["value_raw"] = "539 ± 1"
    unresolved = _tensile_property("not_reported", evidence=evidence)
    unresolved.data["property_name_raw"] = "elongation"
    unresolved.data["value_raw"] = "8.8 ± 0.7"
    unresolved.data["unit_raw"] = "%"

    result = materialize_candidate(
        [_anchor("Alloy-A")], [yield_fact, uts_fact, unresolved]
    )

    assert [row["Sample_ID"] for row in result.document["items"]] == ["Alloy-A"]
    assert len(result.document["items"][0]["Extracted_Data"]["Properties"]) == 3
    issue = next(
        row for row in result.issues if row.code == "numeric_tensile_owner_recovered"
    )
    assert issue.actual["before_owner"] == "not_reported"
    assert issue.actual["after_owner"] == "Alloy-A"
    assert issue.actual["rule"] == "evidence_bundle_sibling_consensus"
    assert len(issue.actual["sibling_facts"]) == 2


def test_numeric_tensile_sibling_consensus_rejects_multiple_owners():
    evidence = (
        "The yield strength was 482 MPa, the ultimate tensile strength was "
        "539 MPa, and the elongation was 8.8%."
    )
    yield_fact = _tensile_property("Alloy-A", evidence=evidence)
    yield_fact.data["property_name_raw"] = "yield strength"
    yield_fact.data["value_raw"] = "482"
    uts_fact = _tensile_property("Alloy-B", evidence=evidence)
    uts_fact.data["value_raw"] = "539"
    unresolved = _tensile_property("not_reported", evidence=evidence)
    unresolved.data["property_name_raw"] = "elongation"
    unresolved.data["value_raw"] = "8.8"
    unresolved.data["unit_raw"] = "%"

    result = materialize_candidate(
        [_anchor("Alloy-A"), _anchor("Alloy-B")],
        [yield_fact, uts_fact, unresolved],
    )

    assert any(issue.code == "unresolved_sample_alias" for issue in result.issues)
    assert not any(
        issue.code == "numeric_tensile_owner_recovered"
        and issue.actual.get("before_owner") == "not_reported"
        for issue in result.issues
    )


def test_generic_tensile_bundle_duplicate_merges_into_resolved_owner():
    source = (
        "Alloy-A had an ultimate tensile strength of 900 MPa "
        "(UTS 900 MPa)."
    )
    resolved = _tensile_property("Alloy-A", evidence=source)
    generic_evidence = "ultimate tensile strength of 900 MPa"
    generic = _tensile_property("not_reported", evidence=generic_evidence)

    result = materialize_candidate(
        [_anchor("Alloy-A")], [generic, resolved], source_text=source
    )

    properties = result.document["items"][0]["Extracted_Data"]["Properties"]
    assert len(properties) == 1
    assert set(properties[0]["source_evidence"]) == {source, generic_evidence}
    issue = next(
        row for row in result.issues if row.code == "cross_item_duplicate_merged"
    )
    assert issue.actual["before_owner"] == "not_reported"
    assert issue.actual["after_owner"] == "Alloy-A"
    assert issue.actual["rule"] == "resolved_owner_over_generic_bundle_projection"


def test_complete_tensile_bundle_prefers_unique_coded_sample_over_generic_owner():
    generic_evidence = (
        "The YS, UTS and EL were measured as 404 MPa, 556 MPa and 17%, "
        "respectively."
    )

    def bundle(sample: str, values: tuple[str, str, str], evidence: str):
        rows = []
        for name, value, unit in zip(
            ("YS", "UTS", "EL"),
            values,
            ("MPa", "MPa", "%"),
            strict=True,
        ):
            fact = _tensile_property(sample, condition="800 °C", evidence=evidence)
            fact.data["property_name_raw"] = name
            fact.data["value_raw"] = value
            fact.data["unit_raw"] = unit
            rows.append(fact)
        return rows

    generic = bundle(
        "multi-spot melt sample", ("404", "556", "17"), generic_evidence
    )
    l70 = bundle(
        "L70",
        ("404", "556", "17"),
        "L70 tensile YS, UTS and EL were 404 MPa, 556 MPa and 17%.",
    )
    l70_elongation_alias = _tensile_property(
        "L70",
        name="tensile ductility",
        value="17",
        unit="%",
        condition="800 °C",
        evidence="L70 tensile ductility was 17% at 800 °C",
    )
    l90 = bundle(
        "L90",
        ("394", "456", "18.4"),
        "L90 tensile YS, UTS and EL were 394 MPa, 456 MPa and 18.4%.",
    )
    result = materialize_candidate(
        [
            _anchor("multi-spot melt sample"),
            _anchor("L70").model_copy(
                update={"material_name_raw": "multi-spot sample L70"}
            ),
            _anchor("L90").model_copy(
                update={"material_name_raw": "multi-spot sample L90"}
            ),
        ],
        [*generic, *l70, l70_elongation_alias, *l90],
    )

    items = {item["Sample_ID"]: item for item in result.document["items"]}
    assert (
        "multi-spot melt sample" not in items
        or items["multi-spot melt sample"]["Extracted_Data"]["Properties"] == []
    )
    assert len(items["L70"]["Extracted_Data"]["Properties"]) == 3
    assert len(items["L90"]["Extracted_Data"]["Properties"]) == 3
    issues = [
        row for row in result.issues if row.code == "cross_item_duplicate_merged"
    ]
    assert len(issues) == 3
    assert {row.actual["rule"] for row in issues} == {
        "specific_sample_bundle_over_generic_projection"
    }
    assert all(
        row.actual["before_owner"] == "multi-spot melt sample"
        and row.actual["after_owner"] == "L70"
        for row in issues
    )
    exact_issues = [
        row
        for row in result.issues
        if row.code == "tensile_exact_duplicate_merged"
    ]
    assert len(exact_issues) == 1
    assert set(
        exact_issues[0].actual["survivor_after_merge"]["source_evidence"]
        ) == {
            generic_evidence,
            "L70 tensile YS, UTS and EL were 404 MPa, 556 MPa and 17%.",
            "L70 tensile ductility was 17% at 800 °C",
        }


def test_complete_equal_tensile_bundles_for_unrelated_samples_are_preserved():
    def bundle(sample: str, descriptor: str):
        rows = []
        for name, value, unit in zip(
            ("yield strength", "ultimate tensile strength", "elongation"),
            ("404", "556", "17"),
            ("MPa", "MPa", "%"),
            strict=True,
        ):
            fact = _tensile_property(
                sample,
                condition="800 °C",
                evidence=(
                    f"{sample} {descriptor} tensile YS, UTS and elongation "
                    "were 404 MPa, 556 MPa and 17%."
                ),
            )
            fact.data["property_name_raw"] = name
            fact.data["value_raw"] = value
            fact.data["unit_raw"] = unit
            rows.append(fact)
        return rows

    result = materialize_candidate(
        [
            _anchor("A70").model_copy(update={"material_name_raw": "alloy alpha"}),
            _anchor("B90").model_copy(update={"material_name_raw": "alloy beta"}),
        ],
        [*bundle("A70", "alpha"), *bundle("B90", "beta")],
    )

    assert {
        item["Sample_ID"]: len(item["Extracted_Data"]["Properties"])
        for item in result.document["items"]
    } == {"A70": 3, "B90": 3}
    assert not any(
        row.code == "cross_item_duplicate_merged" for row in result.issues
    )


def test_numeric_tensile_owner_recovers_unique_current_study_prepared_state():
    evidence = "The 0.2% yield strength was measured as 1266 MPa."
    source = (
        "## Material and methods\n\n"
        "LPBF Alloy-A was solution annealed and double aged before testing.\n\n"
        "Quasi-static tensile tests were performed at room temperature. "
        + evidence
        + "\n\n## Fatigue\n\nUltrasonic fatigue tests were then conducted."
    )
    fact = _tensile_property("not_reported", evidence=evidence)
    fact.data["property_name_raw"] = "yield strength"
    fact.data["value_raw"] = "1266"

    result = materialize_candidate(
        [_anchor("Alloy-A", "solution annealed and double aged")],
        [fact],
        source_text=source,
    )

    assert [row["Sample_ID"] for row in result.document["items"]] == [
        "Alloy-A [solution annealed and double aged]"
    ]
    issue = next(
        row for row in result.issues if row.code == "numeric_tensile_owner_recovered"
    )
    assert issue.actual["rule"] == "unique_current_study_prepared_state"
    assert "fatigue" not in " ".join(issue.evidence["source_blocks"]).casefold()


def test_numeric_tensile_current_study_recovery_rejects_fatigue_result():
    evidence = "The ultrasonic fatigue strength was measured as 650 MPa."
    source = (
        "LPBF Alloy-A was solution annealed and double aged.\n\n" + evidence
    )
    fact = _tensile_property("not_reported", evidence=evidence)
    fact.data["property_name_raw"] = "ultimate tensile strength"
    fact.data["value_raw"] = "650"
    fact.data["test_method_raw"] = "ultrasonic fatigue"

    result = materialize_candidate(
        [_anchor("Alloy-A", "solution annealed and double aged")],
        [fact],
        source_text=source,
    )

    assert result.document["items"] == []
    assert any(issue.code == "unresolved_sample_alias" for issue in result.issues)
    assert not any(
        issue.code == "numeric_tensile_owner_recovered" for issue in result.issues
    )


def test_external_comparator_tensile_is_not_recovered_to_unique_current_owner():
    evidence = "comparable to those of cast TNM alloys (700–800 MPa)"
    owner = "44–4 alloy rods [fabricated by the EBM]"
    fact = _tensile_property(
        "cast TNM alloys",
        evidence=evidence,
        value="700–800 MPa",
    )
    source = (
        "Tensile tests were performed on the 44–4 alloy rods fabricated by "
        "the EBM process.\n\n"
        "The ultimate tensile strengths of these rods at RT exceed 700 MPa "
        "and are "
        + evidence
        + "."
    )

    result = materialize_candidate(
        [
            _material_anchor(
                owner,
                material="44–4 alloy",
                state="fabricated by the EBM",
            ),
            _reference_material_anchor(
                "cast TNM alloys",
                material="TNM",
                state="cast",
                evidence=evidence,
            ),
        ],
        [fact],
        source_text=source,
    )

    assert not any(
        property_row.get("value_raw") == "700–800 MPa"
        for item in result.document["items"]
        for property_row in item["Extracted_Data"]["Properties"]
    )
    issue = next(
        row
        for row in result.issues
        if row.code == "numeric_tensile_external_comparator_quarantined"
    )
    assert issue.actual["removed"] == fact.model_dump()
    assert issue.actual["reason"] == (
        "unresolved_comparator_not_eligible_for_current_protocol_recovery"
    )
    assert issue.evidence["value_local_evidence"] == evidence
    assert issue.evidence["comparator_cue"] == "comparable to those of"
    assert not any(
        row.code == "numeric_tensile_owner_recovered"
        and row.actual.get("fact", {}).get("data", {}).get("value_raw")
        == "700–800 MPa"
        for row in result.issues
    )


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


def test_property_does_not_borrow_state_from_separate_ownerless_table_note():
    anchors = [_anchor("A")]
    state_fact = _structure_fact(
        "A",
        "A after thermal exposure at 900 °C for 500 h contained coarse grains.",
    )
    state_fact.data["material_state"] = (
        "after thermal exposure at 900 °C for 500 h"
    )
    evidence = [
        "| Property | Value |\n| Tensile strength / MPa | 204 |",
        "Table 2. Tensile properties of A.",
        "* Values after thermal exposure at 900 °C for 200 h and 500 h.",
    ]
    fact = PropertyFact(
        sample_id_raw="A",
        data={
            "property_id_candidate": "temp",
            "property_name_raw": "tensile strength",
            "value_raw": "204",
            "unit_raw": "MPa",
            "test_method_raw": "tensile",
            "test_standard_raw": "",
            "test_condition_raw": "900 °C; 200 h thermal exposure",
            "test_specimen_raw": "",
            "raw_note": "",
            "data_source": "table",
            "source_evidence": evidence,
            "confidence": 0.95,
        },
        source_evidence=evidence,
        confidence=0.95,
    )

    result = materialize_candidate(anchors, [state_fact, fact])

    items = {row["Sample_ID"]: row for row in result.document["items"]}
    assert set(items) == {
        "A",
        "A [after thermal exposure at 900 °C for 500 h]",
    }
    assert (
        items["A"]["Extracted_Data"]["Properties"][0]["value_raw"]
        == "204"
    )
    assert (
        items["A [after thermal exposure at 900 °C for 500 h]"][
            "Extracted_Data"
        ]["Properties"]
        == []
    )


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


def test_reported_specimen_is_preserved_with_bound_tensile_protocol():
    evidence = "The X orientation specimen had a yield strength of 900 MPa."
    protocol = (
        "Tensile tests were performed at room temperature at a strain rate "
        "of 1 × 10^-3 s^-1."
    )
    fact = _tensile_property(
        "A",
        name="yield strength",
        value="900",
        unit="MPa",
        evidence=evidence,
    )
    fact.data["test_condition_raw"] = ""
    fact.data["test_specimen_raw"] = "X orientation"

    result = materialize_candidate(
        [_anchor("A")], [fact], source_text=f"{protocol}\n{evidence}"
    )
    prop = result.document["items"][0]["Extracted_Data"]["Properties"][0]

    assert "X orientation" in prop["test_condition_raw"]
    assert "strain rate of 1 × 10^-3 s^-1" in prop["test_condition_raw"]


def test_reported_specimen_is_not_duplicated_when_protocol_keeps_it():
    evidence = "The X orientation specimen had a yield strength of 900 MPa."
    fact = _tensile_property(
        "A",
        name="yield strength",
        value="900",
        unit="MPa",
        evidence=evidence,
    )
    fact.data["test_condition_raw"] = "X orientation; room temperature"
    fact.data["test_specimen_raw"] = "X orientation"

    result = materialize_candidate([_anchor("A")], [fact])
    condition = result.document["items"][0]["Extracted_Data"]["Properties"][0][
        "test_condition_raw"
    ]

    assert condition == "X orientation; room temperature"


def test_unreported_condition_and_specimen_are_empty_for_alpha25_normalizer():
    evidence = "A had a yield strength of 900 MPa."
    fact = PropertyFact(
        sample_id_raw="A",
        data={
            "property_id_candidate": "temp",
            "property_name_raw": "yield strength",
            "value_raw": "900",
            "unit_raw": "MPa",
            "test_method_raw": "tensile test",
            "test_standard_raw": "not_reported",
            "test_condition_raw": "not_reported",
            "test_specimen_raw": "not_reported",
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

    assert prop["test_condition_raw"] == ""
    assert prop["test_specimen_raw"] == ""
    assert prop["test_standard_raw"] == ""


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


def test_continuous_chart_summary_is_not_materialized_as_scalar_property():
    evidence = (
        "series: R1; kind=trend; n_points=10; "
        "key_points=start=(0.0,120.0);mid=(5.0,180.0);end=(10.0,160.0)"
    )
    fact = PropertyFact(
        sample_id_raw="Alloy-A",
        data={
            "property_id_candidate": "temp",
            "property_name_raw": "oxidation kinetics",
            "value_raw": "digitized trend curve; series: R1",
            "unit_raw": "",
            "test_method_raw": "",
            "test_standard_raw": "",
            "test_condition_raw": "",
            "test_specimen_raw": "",
            "raw_note": "",
            "data_source": "chart",
            "source_evidence": [evidence],
            "confidence": 0.9,
        },
        source_evidence=[evidence],
        confidence=0.9,
    )

    result = materialize_candidate([_anchor("Alloy-A")], [fact])

    assert result.document["items"] == []
    issue = next(
        issue
        for issue in result.issues
        if issue.code == "continuous_curve_property_quarantined"
    )
    assert issue.actual["reason"] == "continuous_curve_metadata_not_scalar_property"


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
            "source_evidence": ["L70 UTS: 556 ± 11 MPa"],
            "data": {
                **generic_property.data,
                "source_evidence": ["L70 UTS: 556 ± 11 MPa"],
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
    issue = next(
        row for row in result.issues if row.code == "cross_item_duplicate_merged"
    )
    assert issue.actual["before_owner"] == "multi-spot melt sample"
    assert issue.actual["after_owner"] == "L70"
    assert issue.actual["removed_fact"] == generic_property.model_dump()


def test_state_owner_dominates_unindependent_base_duplicate_with_audit():
    generic = _tensile_property(
        "A", evidence="The ultimate tensile strength was 900 MPa."
    )
    specific = _tensile_property(
        "A [aged at 700 °C]",
        evidence="A aged at 700 °C had an ultimate tensile strength of 900 MPa.",
    )

    result = materialize_candidate(
        [_anchor("A", "as-built"), _anchor("A", "aged at 700 °C")],
        [generic, specific],
    )

    assert [row["Sample_ID"] for row in result.document["items"]] == [
        "A [aged at 700 °C]"
    ]
    issue = next(
        row for row in result.issues if row.code == "cross_item_duplicate_merged"
    )
    assert issue.actual["removed_fact"] == generic.model_dump()
    assert issue.actual["survivor_before_merge"] == specific.model_dump()
    assert set(issue.actual["survivor_after_merge"]["source_evidence"]) == {
        "The ultimate tensile strength was 900 MPa.",
        "A aged at 700 °C had an ultimate tensile strength of 900 MPa.",
    }


def test_cross_item_duplicate_preserves_explicit_multi_owner_assertion():
    evidence = "Alloy-A and Alloy-B both had an ultimate tensile strength of 900 MPa."
    result = materialize_candidate(
        [_anchor("Alloy-A"), _anchor("Alloy-B")],
        [
            _tensile_property("Alloy-A", evidence=evidence),
            _tensile_property("Alloy-B", evidence=evidence),
        ],
    )

    assert [row["Sample_ID"] for row in result.document["items"]] == [
        "Alloy-A",
        "Alloy-B",
    ]
    assert not any(
        row.code == "cross_item_duplicate_merged" for row in result.issues
    )


def test_cross_item_duplicate_preserves_unrelated_equal_values():
    result = materialize_candidate(
        [_anchor("Alloy-A"), _anchor("Alloy-B")],
        [
            _tensile_property(
                "Alloy-A",
                evidence="Alloy-A had an ultimate tensile strength of 900 MPa.",
            ),
            _tensile_property(
                "Alloy-B",
                evidence="Alloy-B had an ultimate tensile strength of 900 MPa.",
            ),
        ],
    )

    assert [row["Sample_ID"] for row in result.document["items"]] == [
        "Alloy-A",
        "Alloy-B",
    ]
    assert not any(
        row.code == "cross_item_duplicate_merged" for row in result.issues
    )


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


def _table_analysis_composition(
    owner: str,
    *,
    source_type: str,
    measurement: str | None,
    values: tuple[str, str],
) -> CompositionFact:
    evidence = f"{owner} | {values[0]} | {values[1]}"
    return CompositionFact(
        sample_id_raw=owner,
        fact_type="composition_observation",
        data={
            "observation_id": "temporary",
            "source_type": source_type,
            "material_state": "not_reported",
            "sample_id": owner,
            "basis": "wt%",
            "component_type": "elemental",
            "components": [
                {
                    "name_raw": name,
                    "value_kind": "scalar",
                    "value_raw": value,
                    "unit_raw": "wt%",
                    "data_nature": "reported",
                }
                for name, value in zip(("Cr", "Mo"), values)
            ],
            "measurement": measurement,
            "raw_expression": evidence,
            "data_source": "table",
            "source_evidence": [evidence],
            "note": None,
        },
        source_evidence=[evidence],
        confidence=0.95,
    )


def test_metric_table_anchor_does_not_absorb_independent_material_descriptor():
    metric_owner = "Cr Diffusion (gamma phase transformation in ME3)"
    anchors = [
        InventoryAnchor(
            sample_id_raw="ME3",
            material_name_raw="ME3",
            state_raw=None,
            role="Target",
            data_nature="Experimental",
            source_evidence=["ME3 alloy"],
            confidence=0.95,
        ),
        InventoryAnchor(
            sample_id_raw=metric_owner,
            material_name_raw="ME3",
            state_raw="gamma phase transformation",
            role="Target",
            data_nature="Computed",
            source_evidence=[f"{metric_owner} | 0.6"],
            confidence=0.9,
        ),
    ]
    composition = _table_analysis_composition(
        "ME3",
        source_type="provided",
        measurement=None,
        values=("13", "3.7"),
    )
    rate = _raw_property(
        metric_owner,
        "Rate",
        "0.6",
        f"{metric_owner} | 0.6",
        source="table",
    )
    rate.data["unit_raw"] = "nm/s"

    result = materialize_candidate(anchors, [composition, rate])

    assert {row["Sample_ID"] for row in result.document["items"]} == {
        "ME3",
        metric_owner,
    }
    me3 = next(row for row in result.document["items"] if row["Sample_ID"] == "ME3")
    assert len(
        me3["Extracted_Data"]["Composition"]["Composition_Observations"]
    ) == 1


def test_powder_analysis_sources_recover_independent_target_and_reference_owners():
    base = InventoryAnchor(
        sample_id_raw="alloy 625 powder",
        material_name_raw="alloy 625",
        state_raw="vacuum-melted argon atomized powder",
        role="Target",
        data_nature="Experimental",
        source_evidence=["vacuum-melted argon atomized alloy 625 powder"],
        confidence=0.95,
    )
    eds_anchor = InventoryAnchor(
        sample_id_raw="EDS powder analysis",
        material_name_raw="alloy 625 powder",
        state_raw="powder",
        role="Target",
        data_nature="Experimental",
        source_evidence=["EDS powder analysis"],
        confidence=0.9,
    )
    manufacturer_anchor = InventoryAnchor(
        sample_id_raw="Manufacturer analysis",
        material_name_raw="alloy 625 powder",
        state_raw="powder",
        role="Reference",
        data_nature="Experimental",
        source_evidence=["Manufacturer analysis"],
        confidence=0.9,
    )
    facts = [
        _table_analysis_composition(
            "EDS powder analysis",
            source_type="measured",
            measurement="EDS",
            values=("21.01", "8.46"),
        ),
        _table_analysis_composition(
            "Manufacturer analysis",
            source_type="provided",
            measurement="Manufacturer analysis",
            values=("21.20", "8.91"),
        ),
    ]

    result = materialize_candidate(
        [base, eds_anchor, manufacturer_anchor], facts
    )

    assert {row["Sample_ID"] for row in result.document["items"]} == {
        "EDS powder analysis for alloy 625 powder",
        "Manufacturer analysis for alloy 625 powder",
    }
    by_role = {row["Role"]: row for row in result.document["items"]}
    assert set(by_role) == {"Target", "Reference"}
    assert all(
        row["material_state"] == "vacuum-melted argon atomized powder"
        for item in by_role.values()
        for row in item["Extracted_Data"]["Composition"][
            "Composition_Observations"
        ]
    )
    issues = [
        row for row in result.issues if row.code == "analysis_source_owner_recovered"
    ]
    assert len(issues) == 2
    assert all(row.actual["before_owner"] != row.actual["after_owner"] for row in issues)


def test_feedstock_state_display_includes_unique_material_descriptor():
    anchor = InventoryAnchor(
        sample_id_raw="GA",
        material_name_raw="nickel-based alloy 625",
        state_raw="as-received gas atomized powder",
        role="Target",
        data_nature="Experimental",
        source_evidence=["GA nickel-based alloy 625 powder"],
        confidence=0.95,
    )
    fact = _structure_fact("GA", "GA | 111.228 | 2.0779 | 3.5990")
    fact.data["material_state"] = "Powder"
    fact.data["features"] = [
        {
            "feature_name_raw": "Lattice parameter",
            "value_kind": "scalar",
            "value_raw": "3.5990",
            "data_nature": "reported",
        }
    ]
    fact.data["entities"] = []

    result = materialize_candidate([anchor], [fact])

    assert [row["Sample_ID"] for row in result.document["items"]] == [
        "GA nickel-based alloy 625 powder"
    ]
    assert any(
        row.code == "feedstock_owner_descriptor_recovered"
        for row in result.issues
    )


def test_structure_characterization_proxy_is_quarantined_with_full_audit():
    fact = _structure_fact(
        "1-1",
        "a3-d3 Contour pole figures of (0001)alpha corresponding to (a1-d1)",
    )
    fact.data.update(
        {
            "structure_kind": "texture",
            "entities": [{"name_raw": "(0001)alpha"}],
            "features": [
                {
                    "feature_name_raw": "characterization",
                    "value_kind": "categorical",
                    "value_raw": "Contour pole figures",
                    "data_nature": "reported",
                }
            ],
        }
    )

    result = materialize_candidate([_anchor("1-1")], [fact])

    assert result.document["items"] == []
    issue = next(
        row
        for row in result.issues
        if row.code == "structure_characterization_proxy_quarantined"
    )
    assert issue.actual["fact"] == fact.model_dump()


def test_reference_row_owner_is_not_reprojected_as_phase_presence():
    anchor = InventoryAnchor(
        sample_id_raw="gamma-Ni reference",
        material_name_raw="gamma-Ni",
        state_raw="Reference",
        role="Reference",
        data_nature="Literature_Experimental",
        source_evidence=["gamma-Ni reference"],
        confidence=0.95,
    )
    evidence = "gamma-Ni reference | - | 2.0675 | 3.581"
    fact = _structure_fact("gamma-Ni reference", evidence)
    fact.data.update(
        {
            "structure_kind": "phase_assemblage",
            "source_type": "cited",
            "entities": [
                {
                    "name_raw": "gamma-Ni",
                    "entity_type": "phase",
                    "role": "reported",
                    "raw_expression": "gamma-Ni",
                }
            ],
            "features": [
                {
                    "feature_name_raw": "d-spacing value for (111) plane",
                    "value_kind": "scalar",
                    "value_raw": "2.0675",
                    "data_nature": "reported",
                },
                {
                    "feature_name_raw": "Lattice parameter",
                    "value_kind": "scalar",
                    "value_raw": "3.581",
                    "data_nature": "reported",
                },
            ],
        }
    )

    result = materialize_candidate([anchor], [fact])

    observation = result.document["items"][0]["Extracted_Data"]["Structure"][
        "Structure_Observations"
    ][0]
    assert observation["entities"] == []
    assert len(observation["features"]) == 2
    issue = next(
        row
        for row in result.issues
        if row.code == "reference_owner_entity_projection_quarantined"
    )
    assert issue.actual["before"]["entities"] == fact.data["entities"]


def test_cross_chunk_text_composition_subset_merges_into_unique_table_observation():
    table_evidence = "| A1 | 4 | 1.25 | 0.4 | Bal. |"
    table = _composition_fact("A1", "A1", table_evidence)
    table.data.update(
        {
            "source_type": "nominal",
            "material_state": "ingot",
            "basis": "wt%",
            "data_source": "table",
            "raw_expression": "Cu 4, Li 1.25, Sc 0.4, Al Bal.",
            "components": [
                {
                    "name_raw": name,
                    "value_kind": kind,
                    "value_raw": value,
                    "unit_raw": "wt%",
                    "data_nature": "reported",
                }
                for name, kind, value in (
                    ("Cu", "scalar", "4"),
                    ("Li", "scalar", "1.25"),
                    ("Sc", "scalar", "0.4"),
                    ("Al", "balance", "Bal."),
                )
            ],
        }
    )
    text_evidence = "A1 has the nominal designation Al–4Cu–1.25Li–0.4Sc."
    text = _composition_fact("A1", "A1", text_evidence)
    text.data.update(
        {
            "source_type": "nominal",
            "basis": "wt%",
            "data_source": "text",
            "raw_expression": "Al–4Cu–1.25Li–0.4Sc",
            "components": [
                {
                    "name_raw": name,
                    "value_kind": "scalar",
                    "value_raw": value,
                    "unit_raw": "wt%",
                    "data_nature": "reported",
                }
                for name, value in (
                    ("Cu", "4"),
                    ("Li", "1.25"),
                    ("Sc", "0.4"),
                )
            ],
        }
    )

    result = materialize_candidate([_anchor("A1")], [table, text])

    observations = result.document["items"][0]["Extracted_Data"]["Composition"][
        "Composition_Observations"
    ]
    assert len(observations) == 1
    assert observations[0]["raw_expression"] == table.data["raw_expression"]
    assert observations[0]["source_evidence"] == [table_evidence, text_evidence]
    issue = next(
        row
        for row in result.issues
        if row.code == "composition_cross_source_exact_duplicate_merged"
    )
    assert issue.actual["removed"]["raw_expression"] == text.data["raw_expression"]
    assert issue.actual["survivor_after"]["source_evidence"] == [
        table_evidence,
        text_evidence,
    ]


def test_same_composition_values_with_different_measurement_origin_do_not_merge():
    evidence = "| A1 | Cr | 20 |"
    measured = _composition_fact("A1", "A1", evidence)
    measured.data.update(
        {
            "source_type": "measured",
            "basis": "wt%",
            "measurement": "EDS",
            "data_source": "table",
            "components": [
                {
                    "name_raw": "Cr",
                    "value_kind": "scalar",
                    "value_raw": "20",
                    "unit_raw": "wt%",
                    "data_nature": "reported",
                }
            ],
        }
    )
    nominal_evidence = "The nominal A1 composition contains 20 wt% Cr."
    nominal = _composition_fact("A1", "A1", nominal_evidence)
    nominal.data.update(
        {
            "source_type": "nominal",
            "basis": "wt%",
            "data_source": "text",
            "components": [
                {
                    "name_raw": "Cr",
                    "value_kind": "scalar",
                    "value_raw": "20",
                    "unit_raw": "wt%",
                    "data_nature": "reported",
                }
            ],
        }
    )

    result = materialize_candidate([_anchor("A1")], [measured, nominal])

    observations = result.document["items"][0]["Extracted_Data"]["Composition"][
        "Composition_Observations"
    ]
    assert len(observations) == 2
    assert not any(
        row.code == "composition_cross_source_exact_duplicate_merged"
        for row in result.issues
    )


def test_v202_discrete_sidecar_promotes_only_literal_tensile_cells(
    tmp_path, monkeypatch
):
    monkeypatch.setenv("KNOWMAT2_ALPHA25_DISCRETE_CHART_SIDECAR_V202", "1")
    monkeypatch.setenv("KNOWMAT2_ALPHA25_OWNER_STATE_CONDITION_V202", "1")
    (tmp_path / "figure_16_digitized.csv").write_text(
        "Condition,Orientation,Yield_Strength_0.2%_MPa,"
        "Ultimate_Tensile_Strength_MPa,Elongation_%\n"
        "As-sintered + HT2,Horizontal,910,1010,2.1\n"
        "As-sintered + HT2,Vertical,920,995,1.9\n",
        encoding="utf-8",
    )
    source = (
        "Hexagonal tensile specimens were manufactured in horizontal and "
        "vertical build orientations.\n"
        "Tensile tests at room temperature were performed at a strain rate "
        "of 400 MPa/min following ISO 6892-1:2019.\n\n"
        "> [Figure 16 VLM-digitized | bar chart]:\n"
        "data_csv: figure_16_digitized.csv\n"
        "The results of the tensile tests at room temperature are shown in Fig. 16."
    )
    base = InventoryAnchor(
        sample_id_raw="MAR M247",
        material_name_raw="MAR-M247",
        state_raw=None,
        role="Target",
        data_nature="Experimental",
        source_evidence=["MAR-M247 fabricated by Binder Jetting"],
        confidence=0.95,
    )

    result = materialize_candidate(
        [base, _anchor("HT2")], [], source_text=source, source_dir=tmp_path
    )

    properties = [
        (item["Sample_ID"], prop)
        for item in result.document["items"]
        for prop in item["Extracted_Data"]["Properties"]
    ]
    assert len(properties) == 6
    assert {prop["property_name_raw"] for _, prop in properties} == {
        "0.2% Yield Strength",
        "Ultimate Tensile Strength",
        "Elongation",
    }
    assert {prop["value_raw"] for _, prop in properties} == {
        "910",
        "1010",
        "2.1",
        "920",
        "995",
        "1.9",
    }
    assert all("as-sintered" in sample.casefold() for sample, _ in properties)
    assert all(
        "hexagonal tensile specimen" in sample.casefold()
        for sample, _ in properties
    )
    assert not any(sample == "HT2" for sample, _ in properties)
    assert {
        prop.get("test_specimen_raw") for _, prop in properties
    } == {"Horizontal", "Vertical"}
    assert all(
        "room temperature" in prop.get("test_condition_raw", "").casefold()
        and "400 MPa/min" in prop.get("test_condition_raw", "")
        and "ISO 6892-1:2019" in prop.get("test_condition_raw", "")
        for _, prop in properties
    )
    assert {prop.get("data_source") for _, prop in properties} == {
        "image_digitized"
    }
    recovered = [
        issue
        for issue in result.issues
        if issue.code == "discrete_chart_property_recovered"
    ]
    assert len(recovered) == 6
    assert all(issue.actual["owner_invented"] is False for issue in recovered)
    assert {issue.actual["source_kind"] for issue in recovered} == {
        "image_digitized"
    }
    assert sum(
        issue.actual["owner_created_from_source_literal"] is True
        for issue in recovered
    ) == 3
    protocol = [
        issue
        for issue in result.issues
        if issue.code == "tensile_protocol_coordinate_recovered"
    ]
    assert len(protocol) == 6
    assert {
        issue.actual["decision_key"] for issue in protocol
    } == {
        issue.actual["after"]["property_id_candidate"] for issue in protocol
    }


def test_v202_multi_owner_sidecar_matches_existing_materials_and_pairs_bounds(
    tmp_path, monkeypatch
):
    monkeypatch.setenv("KNOWMAT2_ALPHA25_DISCRETE_CHART_SIDECAR_V202", "1")
    monkeypatch.setenv("KNOWMAT2_ALPHA25_OWNER_STATE_CONDITION_V202", "1")
    (tmp_path / "figure_6_digitized.csv").write_text(
        "Material,Direction,Yield_Stress_MPa_median,"
        "Yield_Stress_MPa_lower,Yield_Stress_MPa_upper\n"
        "Wrought,X,975,965,985\n"
        "Wrought,Y,890,870,910\n"
        "Wrought,Z,930,930,930\n"
        "WAAM-AB,X,820,800,840\n"
        "WAAM-AB,Y,815,790,850\n"
        "WAAM-AB,Z,750,735,765\n"
        "EBAM-AB,X,910,895,920\n"
        "EBAM-AB,Y,905,890,925\n"
        "EBAM-AB,Z,810,795,825\n",
        encoding="utf-8",
    )
    source = (
        "The stress-strain curves for the mill annealed, as-built EBAM, and "
        "as-built WAAM conditions are shown in Figure 5.\n"
        "> [Figure 6 VLM-digitized | bar chart, estimated from pixels]:\n"
        "data_csv: figure_6_digitized.csv\n"
        "Figure 6: Box and whisker plots of mechanical properties of wrought, "
        "WAAM, and EBAM Ti-6Al-4V material."
    )
    anchors = [
        InventoryAnchor(
            sample_id_raw="Wrought",
            material_name_raw="Ti-6Al-4V",
            state_raw="mill annealed",
            role="Target",
            data_nature="Experimental",
            source_evidence=["mill annealed wrought Ti-6Al-4V"],
            confidence=0.95,
        ),
        InventoryAnchor(
            sample_id_raw="WAAM",
            material_name_raw="Ti-6Al-4V",
            state_raw="as-built WAAM",
            role="Target",
            data_nature="Experimental",
            source_evidence=["as-built WAAM Ti-6Al-4V"],
            confidence=0.95,
        ),
        InventoryAnchor(
            sample_id_raw="EBAM",
            material_name_raw="Ti-6Al-4V",
            state_raw="as-built EBAM",
            role="Target",
            data_nature="Experimental",
            source_evidence=["as-built EBAM Ti-6Al-4V"],
            confidence=0.95,
        ),
    ]
    anchors.extend(
        [
            anchors[0].model_copy(update={"state_raw": "wrought"}),
            anchors[1].model_copy(update={"state_raw": "as-built"}),
            anchors[2].model_copy(update={"state_raw": "as-built"}),
        ]
    )

    result = materialize_candidate(
        anchors, [], source_text=source, source_dir=tmp_path
    )

    properties = [
        (item["Sample_ID"], prop)
        for item in result.document["items"]
        for prop in item["Extracted_Data"]["Properties"]
    ]
    assert len(properties) == 18
    assert {prop["property_name_raw"] for _, prop in properties} == {
        "Yield Stress median",
        "Yield Stress lower-upper interval",
    }
    assert sum(
        prop["property_name_raw"] == "Yield Stress median"
        for _, prop in properties
    ) == 9
    assert sum(
        prop["property_name_raw"] == "Yield Stress lower-upper interval"
        for _, prop in properties
    ) == 9
    assert {prop.get("test_condition_raw") for _, prop in properties} == {
        "tensile test",
    }
    assert {tuple(issue.actual["property_cell"]["column_indexes"]) for issue in result.issues
            if issue.code == "discrete_chart_property_recovered"} == {
        (2,),
        (3, 4),
    }
    recovered = {
        issue.sample_id_raw
        for issue in result.issues
        if issue.code == "source_literal_owner_state_recovered"
    }
    assert recovered == {
        "WAAM-AB-X",
        "WAAM-AB-Y",
        "WAAM-AB-Z",
        "EBAM-AB-X",
        "EBAM-AB-Y",
        "EBAM-AB-Z",
    }


def test_v202_sidecar_ab_suffix_recovers_state_from_owner_local_source(
    tmp_path, monkeypatch
):
    """A bare upstream owner may safely receive an explicit source-local AB state."""

    monkeypatch.setenv("KNOWMAT2_ALPHA25_DISCRETE_CHART_SIDECAR_V202", "1")
    monkeypatch.setenv("KNOWMAT2_ALPHA25_OWNER_STATE_CONDITION_V202", "1")
    (tmp_path / "figure_6_digitized.csv").write_text(
        "Material,Direction,Yield_Stress_MPa\n"
        "WAAM-AB,X,820\n",
        encoding="utf-8",
    )
    source = (
        "The as-built WAAM tensile specimens were tested in the X direction.\n"
        "> [Figure 6 VLM-digitized | bar chart]:\n"
        "data_csv: figure_6_digitized.csv"
    )
    bare_owner = InventoryAnchor(
        sample_id_raw="WAAM",
        material_name_raw="Ti-6Al-4V",
        state_raw=None,
        role="Target",
        data_nature="Experimental",
        source_evidence=["WAAM tensile specimens"],
        confidence=0.95,
    )

    result = materialize_candidate(
        [bare_owner], [], source_text=source, source_dir=tmp_path
    )

    properties = [
        (item["Sample_ID"], prop)
        for item in result.document["items"]
        for prop in item["Extracted_Data"]["Properties"]
    ]
    assert len(properties) == 1
    assert properties[0][0] == "WAAM-AB-X"
    assert properties[0][1]["material_state"] == "as-built"
    assert any(
        issue.code == "source_literal_owner_state_recovered"
        and issue.actual["created_anchor"]["state_raw"] == "as-built"
        and source.splitlines()[0] in issue.actual["created_anchor"]["source_evidence"]
        for issue in result.issues
    )


def test_v202_sidecar_ab_suffix_without_local_state_fails_closed(tmp_path, monkeypatch):
    monkeypatch.setenv("KNOWMAT2_ALPHA25_DISCRETE_CHART_SIDECAR_V202", "1")
    monkeypatch.setenv("KNOWMAT2_ALPHA25_OWNER_STATE_CONDITION_V202", "1")
    (tmp_path / "figure_6_digitized.csv").write_text(
        "Material,Direction,Yield_Stress_MPa\nWAAM-AB,X,820\n",
        encoding="utf-8",
    )
    result = materialize_candidate(
        [_anchor("WAAM")],
        [],
        source_text="data_csv: figure_6_digitized.csv",
        source_dir=tmp_path,
    )
    assert sum(
        len(item["Extracted_Data"]["Properties"])
        for item in result.document["items"]
    ) == 0
    assert any(
        issue.code == "discrete_chart_sidecar_rejected"
        and issue.actual.get("owner_match_status") == "unknown"
        for issue in result.issues
    )


def test_v202_multi_owner_sidecar_unknown_or_ambiguous_material_fails_closed(
    tmp_path, monkeypatch
):
    monkeypatch.setenv("KNOWMAT2_ALPHA25_DISCRETE_CHART_SIDECAR_V202", "1")
    monkeypatch.setenv("KNOWMAT2_ALPHA25_OWNER_STATE_CONDITION_V202", "1")
    (tmp_path / "figure_6_digitized.csv").write_text(
        "Material,Direction,Yield_Stress_MPa_median,"
        "Yield_Stress_MPa_lower,Yield_Stress_MPa_upper\n"
        "Unknown,X,975,965,985\n"
        "Ti-6Al-4V,Y,890,870,910\n",
        encoding="utf-8",
    )
    anchors = [
        InventoryAnchor(
            sample_id_raw=sample,
            material_name_raw="Ti-6Al-4V",
            state_raw="as-built",
            role="Target",
            data_nature="Experimental",
            source_evidence=[sample],
            confidence=0.95,
        )
        for sample in ("WAAM", "EBAM")
    ]

    result = materialize_candidate(
        anchors,
        [],
        source_text="data_csv: figure_6_digitized.csv",
        source_dir=tmp_path,
    )

    assert sum(
        len(item["Extracted_Data"]["Properties"])
        for item in result.document["items"]
    ) == 0
    rejected = [
        issue
        for issue in result.issues
        if issue.code == "discrete_chart_sidecar_rejected"
        and issue.actual.get("literal_sidecar_row")
    ]
    assert len(rejected) == 2
    assert {issue.actual["owner_match_status"] for issue in rejected} == {
        "unknown",
        "ambiguous",
    }


def test_v202_continuous_sidecar_never_enters_properties(tmp_path, monkeypatch):
    monkeypatch.setenv("KNOWMAT2_ALPHA25_DISCRETE_CHART_SIDECAR_V202", "1")
    (tmp_path / "figure_13_digitized.csv").write_text(
        "series,kind,x,y\ncurve_1,trend,0,0\ncurve_1,trend,1,100\n",
        encoding="utf-8",
    )
    source = "data_csv: figure_13_digitized.csv"

    result = materialize_candidate(
        [_anchor("A")], [], source_text=source, source_dir=tmp_path
    )

    assert all(
        not item["Extracted_Data"]["Properties"]
        for item in result.document["items"]
    )
    issues = [
        issue
        for issue in result.issues
        if issue.code == "continuous_curve_sidecar_not_promoted"
    ]
    assert len(issues) == 1
    assert issues[0].actual["decision"]["rows"] == []


def test_v202_sidecar_switch_off_preserves_v201_materialization(
    tmp_path, monkeypatch
):
    monkeypatch.setenv("KNOWMAT2_ALPHA25_DISCRETE_CHART_SIDECAR_V202", "0")
    (tmp_path / "figure_16_digitized.csv").write_text(
        "Condition,Ultimate_Tensile_Strength_MPa\nHT2,1010\n",
        encoding="utf-8",
    )

    result = materialize_candidate(
        [_anchor("A")],
        [],
        source_text="data_csv: figure_16_digitized.csv",
        source_dir=tmp_path,
    )

    assert all(
        not item["Extracted_Data"]["Properties"]
        for item in result.document["items"]
    )
    assert not any("sidecar" in issue.code for issue in result.issues)


def test_v202_same_coordinate_exact_duplicate_has_one_audited_survivor(monkeypatch):
    monkeypatch.setenv("KNOWMAT2_ALPHA25_SOURCE_COORDINATE_PRECISION_V202", "1")
    first = _tensile_property(
        sample="A",
        name="Yield Strength",
        value="910",
        condition="room temperature",
        evidence="A,Horizontal,910",
    )
    first.data.update(
        {
            "property_id_candidate": "sidecar-cell:abc",
            "data_source": "image_digitized",
            "test_specimen_raw": "Horizontal",
        }
    )
    second = first.model_copy(deep=True)
    second.source_evidence = [*first.source_evidence, "figure_16_digitized.csv"]
    second.data["source_evidence"] = list(second.source_evidence)
    second.confidence = 0.95

    result = materialize_candidate([_anchor("A")], [first, second])

    properties = result.document["items"][0]["Extracted_Data"]["Properties"]
    assert len(properties) == 1
    issues = [
        issue
        for issue in result.issues
        if issue.code == "source_coordinate_duplicate_quarantined"
    ]
    assert len(issues) == 1
    assert issues[0].actual["decision_key"] == "sidecar-cell:abc"
    assert "figure_16_digitized.csv" in issues[0].actual["survivor_after"][
        "source_evidence"
    ]


def test_v202_same_coordinate_owner_or_value_conflict_quarantines_all(monkeypatch):
    monkeypatch.setenv("KNOWMAT2_ALPHA25_SOURCE_COORDINATE_PRECISION_V202", "1")
    first = _tensile_property(
        sample="A",
        name="Yield Strength",
        value="910",
        condition="room temperature",
        evidence="A,Horizontal,910",
    )
    first.data.update(
        {
            "property_id_candidate": "sidecar-cell:conflict",
            "data_source": "image_digitized",
            "test_specimen_raw": "Horizontal",
        }
    )
    conflicting = first.model_copy(
        deep=True, update={"sample_id_raw": "B"}
    )
    conflicting.data["value_raw"] = "999"

    result = materialize_candidate(
        [_anchor("A"), _anchor("B")], [first, conflicting]
    )

    assert sum(
        len(item["Extracted_Data"]["Properties"])
        for item in result.document["items"]
    ) == 0
    issues = [
        issue
        for issue in result.issues
        if issue.code == "source_coordinate_conflict_quarantined"
    ]
    assert len(issues) == 2
    assert all(
        issue.actual["decision_key"] == "sidecar-cell:conflict"
        for issue in issues
    )


def test_structure_table_recovery_splits_repeated_features_by_literal_region():
    source = (
        '<table><tr><th>Parameter</th><th>Location</th>'
        '<th colspan="2">T5</th></tr>'
        '<tr><th></th><th></th><th>Initial</th><th>1030 ^\\circC/2h</th></tr>'
        '<tr><td>\\gamma\' volume fraction (%)</td><td>D</td>'
        '<td>72.5 \\pm 0.9</td><td>69.6 \\pm 0.4</td></tr>'
        '<tr><td>\\gamma\' volume fraction (%)</td><td>ID</td>'
        '<td>78.1 \\pm 0.5</td><td>74.3 \\pm 0.7</td></tr>'
        '</table>'
    )
    evidence = [
        "| Parameter | T5 / 1030 ^\\circC/2h |",
        "| \\gamma' volume fraction (%) | 69.6 \\pm 0.4 |",
        "| \\gamma' volume fraction (%) | 74.3 \\pm 0.7 |",
    ]
    fact = StructureFact(
        sample_id_raw="T5",
        fact_type="structure_observation",
        data={
            "observation_id": "temporary",
            "structure_kind": "precipitate",
            "material_state": "1030 ^\\circC/2h",
            "sample_id": "T5",
            "source_type": "reported",
            "original": " | ".join(evidence),
            "simplified": " | ".join(evidence),
            "entities": [],
            "features": [
                {
                    "feature_name_raw": "\\gamma' volume fraction (%)",
                    "value_kind": "scalar",
                    "value_raw": "69.6 \\pm 0.4",
                    "data_nature": "reported",
                },
                {
                    "feature_name_raw": "\\gamma' volume fraction (%)",
                    "value_kind": "scalar",
                    "value_raw": "74.3 \\pm 0.7",
                    "data_nature": "reported",
                },
            ],
            "source_evidence": evidence,
        },
        source_evidence=evidence,
        confidence=0.9,
    )

    recovered, issues = _recover_structure_table_feature_coordinates(
        [fact], source
    )

    assert len(recovered) == 2
    assert {row.data["region_raw"] for row in recovered} == {"D", "ID"}
    assert {
        row.data["features"][0]["value_raw"] for row in recovered
    } == {"69.6 \\pm 0.4", "74.3 \\pm 0.7"}
    assert [row.code for row in issues] == ["structure_table_coordinate_recovered"]


def test_structure_table_recovery_fails_closed_when_region_mapping_is_not_unique():
    source = (
        '<table><tr><th>Parameter</th><th>Location</th><th>T5</th></tr>'
        '<tr><td>grain size</td><td>D</td><td>10</td></tr>'
        '<tr><td>grain size</td><td>ID</td><td>10</td></tr></table>'
    )
    evidence = ["| Parameter | T5 |", "| grain size | 10 |", "| grain size | 10 |"]
    fact = StructureFact(
        sample_id_raw="T5",
        fact_type="structure_observation",
        data={
            "observation_id": "temporary",
            "structure_kind": "grain",
            "material_state": "not_reported",
            "sample_id": "T5",
            "source_type": "reported",
            "original": " | ".join(evidence),
            "simplified": " | ".join(evidence),
            "entities": [],
            "features": [
                {
                    "feature_name_raw": "grain size",
                    "value_kind": "scalar",
                    "value_raw": "10",
                    "data_nature": "reported",
                },
                {
                    "feature_name_raw": "grain size",
                    "value_kind": "scalar",
                    "value_raw": "10",
                    "data_nature": "reported",
                },
            ],
            "source_evidence": evidence,
        },
        source_evidence=evidence,
        confidence=0.9,
    )

    recovered, issues = _recover_structure_table_feature_coordinates(
        [fact], source
    )

    assert recovered == [fact]
    assert [row.code for row in issues] == ["structure_table_coordinate_ambiguous"]


def test_structure_table_recovery_accepts_td_only_continuation_header_and_unit_suffixes():
    source = (
        '<table><tr><td rowspan="2">Parameter</td><td rowspan="2">Location</td>'
        '<td colspan="2">T5</td></tr><tr><td>Initial</td>'
        '<td>1030 ^\\circC/2h</td></tr>'
        '<tr><td rowspan="2">\\gamma\' volume fraction (%)</td><td>D</td>'
        '<td>72.5 \\pm 0.9</td><td>69.6 \\pm 0.4</td></tr>'
        '<tr><td>ID</td><td>78.1 \\pm 0.5</td><td>74.3 \\pm 0.7</td></tr>'
        '</table>'
    )
    fact = StructureFact(
        sample_id_raw="T5",
        fact_type="structure_observation",
        data={
            "observation_id": "temporary",
            "structure_kind": "precipitate",
            "material_state": "1030 ^\\circC/2h",
            "sample_id": "T5",
            "source_type": "reported",
            "original": "x",
            "simplified": "x",
            "entities": [],
            "features": [
                {
                    "feature_name_raw": "\\gamma' volume fraction",
                    "value_kind": "scalar",
                    "value_raw": "69.6 \\pm 0.4",
                    "data_nature": "reported",
                },
                {
                    "feature_name_raw": "\\gamma' volume fraction",
                    "value_kind": "scalar",
                    "value_raw": "74.3 \\pm 0.7",
                    "data_nature": "reported",
                },
            ],
            "source_evidence": ["x"],
        },
        source_evidence=["x"],
        confidence=0.9,
    )

    recovered, issues = _recover_structure_table_feature_coordinates([fact], source)

    assert {row.data["region_raw"] for row in recovered} == {"D", "ID"}
    assert [row.data["features"][0]["value_raw"] for row in recovered] == [
        "69.6 \\pm 0.4",
        "74.3 \\pm 0.7",
    ]
    assert [row.code for row in issues] == ["structure_table_coordinate_recovered"]


def test_process_route_state_is_not_promoted_to_synthetic_target_item():
    """LPBF/orientation context must stay on the fact, not become an owner."""
    anchor = InventoryAnchor(
        sample_id_raw="H230AM",
        material_name_raw="Haynes 230AM",
        role="Target",
        data_nature="Experimental",
        source_evidence=["H230AM samples were fabricated by LPBF; grain size was 10 um"],
        confidence=0.9,
    )
    fact = StructureFact(
        sample_id_raw="H230AM",
        fact_type="structure_observation",
        source_evidence=["H230AM samples were fabricated by LPBF; grain size was 10 um"],
        confidence=0.9,
        data={
            "observation_id": "temporary",
            "structure_kind": "grain_structure",
            "material_state": "LPBF",
            "sample_id": "H230AM",
            "source_type": "reported",
            "original": "H230AM samples were fabricated by LPBF; grain size was 10 um",
            "simplified": "H230AM samples were fabricated by LPBF; grain size was 10 um",
            "entities": [],
            "features": [
                {
                    "feature_name_raw": "grain size",
                    "value_kind": "scalar",
                    "value_raw": "10",
                    "unit_raw": "um",
                    "data_nature": "reported",
                }
            ],
            "source_evidence": ["H230AM samples were fabricated by LPBF; grain size was 10 um"],
        },
    )
    result = materialize_candidate([anchor], [fact], source_text=anchor.source_evidence[0])
    assert [item["Sample_ID"] for item in result.document["items"]] == ["H230AM"]
