from knowmat.alpha25.contracts import PropertyFact
from knowmat.alpha25.source_coordinates import (
    dense_tensile_table_decisions,
    discrete_tensile_sidecars,
    logical_tables,
    resolve_structured_table_record,
    resolve_tensile_assertion_coordinate,
)


def _property(
    owner: str = "1-1",
    *,
    name: str = "Ultimate Tensile Strength",
    value: str = "1061 ± 27.5",
    unit: str = "MPa",
) -> PropertyFact:
    evidence = [
        (
            "| Iteration and Sample Number | Printing Parameters / Heating Time (h) | "
            "Printing Parameters / Volumetric Energy Density ( $ J/mm^{3} $) | "
            "Measured Properties / Ultimate Tensile Strength (MPa) | "
            "Measured Properties / Total Elongation (%) |"
        ),
        (
            "| 1-1 | 2 | 94.69 | $ 1061 \\pm 27.5 $ | "
            "$ 18.3 \\pm 1.5 $ |"
        ),
    ]
    return PropertyFact(
        sample_id_raw=owner,
        fact_type="property",
        data={
            "property_id_candidate": "temporary",
            "property_name_raw": name,
            "value_raw": value,
            "unit_raw": unit,
            "test_method_raw": "tensile tests",
            "test_standard_raw": "",
            "test_condition_raw": "",
            "test_specimen_raw": "",
            "raw_note": "",
            "data_source": "table",
            "source_evidence": evidence,
            "confidence": 0.95,
        },
        source_evidence=evidence,
        confidence=0.95,
    )


HTML_TABLE = r"""
<table>
  <tr><td colspan="2" rowspan="2">Iteration and Sample Number</td><td colspan="2">Printing Parameters</td><td colspan="2">Measured Properties</td></tr>
  <tr><td>Heating Time (h)</td><td>Volumetric Energy Density ( $ J/mm^{3} $)</td><td>Ultimate Tensile Strength (MPa)</td><td>Total Elongation (%)</td></tr>
  <tr><td>1</td><td>1-1</td><td>2</td><td>94.69</td><td>$ 1061 \pm 27.5 $</td><td>$ 18.3 \pm 1.5 $</td></tr>
</table>
"""


def test_logical_html_table_expands_spans_and_retains_header_origins():
    tables = logical_tables(HTML_TABLE)

    assert len(tables) == 1
    table = tables[0]
    assert table.header_row_count == 2
    assert len(table.rows) == 3
    assert len(table.rows[0]) == 6
    assert table.rows[0][0].origin == table.rows[1][1].origin
    assert table.header_path(4) == (
        "measured properties",
        "ultimate tensile strength (mpa)",
    )


def test_structured_table_record_resolves_one_multilevel_header_cell():
    decision = resolve_structured_table_record(_property(), HTML_TABLE)

    assert decision.status == "matched"
    assert decision.block_index == 0
    assert decision.logical_row == 2
    assert decision.logical_column == 4
    assert decision.header_path == (
        "measured properties",
        "ultimate tensile strength (mpa)",
    )
    assert decision.owner_cell["text"] == "1-1"
    assert decision.value_cell["text"] == "1061 ± 27.5"
    assert decision.decision_key.startswith("table-cell:")


def test_structured_table_record_fails_closed_for_wrong_owner():
    decision = resolve_structured_table_record(_property("other-sample"), HTML_TABLE)

    assert decision.status == "not_found"
    assert decision.decision_key == ""


def test_structured_table_record_rejects_duplicate_table_blocks_as_ambiguous():
    decision = resolve_structured_table_record(
        _property(), f"{HTML_TABLE}\n{HTML_TABLE}"
    )

    assert decision.status == "ambiguous"
    assert decision.distinct_match_count == 2


def test_structured_table_record_resolves_column_owner_and_rowspan_property():
    source = r"""
<table>
<tr><td>Properties</td><td>Wrought</td><td>WAAM</td></tr>
<tr><td rowspan="2">Yield Strength (MPa)</td><td>948 [37]</td><td>$ 856 \pm 16 $ [39]</td></tr>
<tr><td>880 [38]</td><td>710 [40]</td></tr>
</table>
"""
    evidence = [
        "| Properties | Wrought | WAAM |",
        "| Yield Strength (MPa) | 880 [38] | 710 [40] |",
    ]
    fact = _property(
        "Wrought", name="Yield Strength", value="880", unit="MPa"
    ).model_copy(
        update={
            "source_evidence": evidence,
            "data": {
                **_property().data,
                "property_name_raw": "Yield Strength",
                "value_raw": "880",
                "unit_raw": "MPa",
                "raw_note": "[38]",
                "source_evidence": evidence,
            },
        }
    )

    decision = resolve_structured_table_record(fact, source)

    assert decision.status == "matched"
    assert decision.logical_row == 2
    assert decision.logical_column == 1
    assert decision.header_path == ("yield strength (mpa)",)
    assert decision.owner_path == ("wrought",)
    assert decision.value_cell["text"] == "880 [38]"


def test_structured_column_owner_requires_cell_local_citation():
    source = r"""
<table><tr><td>Properties</td><td>Wrought</td></tr>
<tr><td>Yield Strength (MPa)</td><td>880 [38]</td></tr></table>
"""
    evidence = ["| Properties | Wrought |", "| Yield Strength (MPa) | 880 [38] |"]
    fact = _property(
        "Wrought", name="Yield Strength", value="880", unit="MPa"
    ).model_copy(
        update={
            "source_evidence": evidence,
            "data": {
                **_property().data,
                "property_name_raw": "Yield Strength",
                "value_raw": "880",
                "unit_raw": "MPa",
                "raw_note": "[99]",
                "source_evidence": evidence,
            },
        }
    )

    decision = resolve_structured_table_record(fact, source)

    assert decision.status == "not_found"


def test_structured_table_record_supports_markdown_table_equivalent():
    source = r"""
| Sample | Ultimate Tensile Strength (MPa) | Total Elongation (%) |
| --- | --- | --- |
| 1-1 | $ 1061 \pm 27.5 $ | $ 18.3 \pm 1.5 $ |
"""
    fact = _property()
    evidence = [
        "| Sample | Ultimate Tensile Strength (MPa) | Total Elongation (%) |",
        "| 1-1 | $ 1061 \\pm 27.5 $ | $ 18.3 \\pm 1.5 $ |",
    ]
    fact = fact.model_copy(
        update={
            "source_evidence": evidence,
            "data": {**fact.data, "source_evidence": evidence},
        }
    )

    decision = resolve_structured_table_record(fact, source)

    assert decision.status == "matched"
    assert decision.table_kind == "markdown"
    assert decision.logical_column == 1


def test_discrete_tensile_sidecar_parses_bounded_categorical_rows(tmp_path):
    sidecar = tmp_path / "figure_16_digitized.csv"
    sidecar.write_text(
        "Condition,Orientation,Yield_Strength_0.2%_MPa,"
        "Ultimate_Tensile_Strength_MPa,Elongation_%\n"
        "As-sintered + HT2,Horizontal,910,1010,2.1\n"
        "As-sintered + HT2,Vertical,920,995,1.9\n",
        encoding="utf-8",
    )
    source = "> [Figure 16 VLM-digitized | bar chart]:\ndata_csv: figure_16_digitized.csv"

    decisions = discrete_tensile_sidecars(source, tmp_path)

    assert len(decisions) == 1
    decision = decisions[0]
    assert decision.status == "eligible"
    assert decision.row_count == 2
    assert decision.column_count == 5
    assert decision.nonempty_cell_count == 10
    assert decision.content_sha256
    first = decision.rows[0]
    assert first.condition == "As-sintered + HT2"
    assert first.orientation == "Horizontal"
    assert [(cell.property_name, cell.value_raw, cell.unit_raw) for cell in first.properties] == [
        ("0.2% Yield Strength", "910", "MPa"),
        ("Ultimate Tensile Strength", "1010", "MPa"),
        ("Elongation", "2.1", "%"),
    ]


def test_continuous_curve_sidecar_is_mandatory_noop(tmp_path):
    (tmp_path / "figure_13_digitized.csv").write_text(
        "series,kind,x,y\ncurve_1,trend,0,0\ncurve_1,trend,1,100\n",
        encoding="utf-8",
    )
    source = "data_csv: figure_13_digitized.csv"

    decision = discrete_tensile_sidecars(source, tmp_path)[0]

    assert decision.status == "continuous"
    assert decision.rows == ()
    assert "series_kind_xy" in decision.reason


def test_sidecar_path_traversal_and_external_symlink_fail_closed(tmp_path):
    outside = tmp_path.parent / "outside-v202.csv"
    outside.write_text(
        "Condition,Ultimate_Tensile_Strength_MPa\nHT2,1010\n",
        encoding="utf-8",
    )
    (tmp_path / "linked.csv").symlink_to(outside)
    source = "data_csv: ../outside-v202.csv\ndata_csv: linked.csv"

    decisions = discrete_tensile_sidecars(source, tmp_path)

    assert [decision.status for decision in decisions] == ["rejected", "rejected"]
    assert all(decision.rows == () for decision in decisions)
    assert {decision.reason for decision in decisions} == {
        "unsafe_sidecar_path",
        "sidecar_resolves_outside_source_dir",
    }


def test_sidecar_missing_unit_and_oversized_shapes_are_not_promoted(tmp_path):
    (tmp_path / "missing_unit.csv").write_text(
        "Condition,Ultimate_Tensile_Strength\nHT2,1010\n",
        encoding="utf-8",
    )
    oversized_rows = ["Condition,Ultimate_Tensile_Strength_MPa"]
    oversized_rows.extend(f"HT2-{index},{1000 + index}" for index in range(33))
    (tmp_path / "oversized.csv").write_text(
        "\n".join(oversized_rows) + "\n", encoding="utf-8"
    )
    source = "data_csv: missing_unit.csv\ndata_csv: oversized.csv"

    decisions = discrete_tensile_sidecars(source, tmp_path)

    assert decisions[0].status == "not_applicable"
    assert decisions[0].reason == "no_explicit_core_tensile_header_with_unit"
    assert decisions[1].status == "continuous"
    assert decisions[1].reason == "categorical_shape_cap_exceeded"


def test_v203_dense_markdown_tensile_table_enumerates_unique_target_cells():
    source = """
| Sample | Yield Strength (MPa) | UTS (MPa) | Total Elongation (%) |
| --- | --- | --- | --- |
| Ti64-H | 486 | 781 | 12.0 |
"""

    decisions = dense_tensile_table_decisions(
        source,
        {"Ti64-H": ("Ti64-H", "Ti-6Al-4V heat treated")},
    )

    assert len(decisions) == 1
    assert decisions[0].status == "eligible"
    cells = decisions[0].cells
    assert [
        (cell.owner, cell.property_name, cell.value_raw, cell.unit_raw)
        for cell in cells
    ] == [
        ("Ti64-H", "Yield Strength", "486", "MPa"),
        ("Ti64-H", "Ultimate Tensile Strength", "781", "MPa"),
        ("Ti64-H", "Total Elongation", "12.0", "%"),
    ]
    assert len({cell.decision_key for cell in cells}) == 3
    assert all(
        cell.decision_key.startswith("dense-table-cell:") for cell in cells
    )
    assert all(cell.source_coordinate_key.startswith("table-cell:") for cell in cells)


def test_v203_dense_html_multilevel_header_retains_source_coordinates():
    source = """
<table>
  <tr><th rowspan="2">Sample</th><th colspan="3">Tensile properties</th></tr>
  <tr><th>YS (MPa)</th><th>Ultimate tensile strength [MPa]</th><th>Elongation (%)</th></tr>
  <tr><td>Ti64-H</td><td>486 ± 4</td><td>781</td><td>12–14</td></tr>
</table>
"""

    decision = dense_tensile_table_decisions(
        source, {"Ti64-H": ("Ti64-H",)}
    )[0]

    assert decision.status == "eligible"
    assert len(decision.cells) == 3
    assert decision.cells[0].table_kind == "html"
    assert decision.cells[0].source_rows
    assert decision.cells[0].value_cell["source_row"] == 2


def test_v203_dense_row_owner_must_precede_property_columns():
    source = """
| Material | UTS (MPa) | Process |
| --- | --- | --- |
| This work | 803 | PBF-EB |
"""

    decision = dense_tensile_table_decisions(
        source, {"PBF-EB": ("PBF-EB",)}
    )[0]

    assert decision.status == "rejected"
    assert decision.cells == ()
    assert decision.reason == "no_unique_target_owner"


def test_v203_dense_orientation_header_requires_explicit_specimen_ledger():
    source = """
<table>
  <tr><th rowspan="2">Property</th><th colspan="2">WAAM</th></tr>
  <tr><th>X</th><th>Z</th></tr>
  <tr><td>UTS (MPa)</td><td>951</td><td>898</td></tr>
</table>
"""

    decision = dense_tensile_table_decisions(
        source,
        {
            "WAAM / X": ("WAAM / X",),
            "WAAM / Z": ("WAAM / Z",),
        },
    )[0]

    assert decision.status == "rejected"
    assert decision.cells == ()
    assert decision.reason == "orientation_header_requires_explicit_specimen_owner"


def test_v203_dense_reference_standard_column_is_not_a_target_owner():
    source = """
<table>
  <tr><th>Property</th><th>Wrought (AMS 4928)</th></tr>
  <tr><td>UTS (MPa)</td><td>930</td></tr>
</table>
"""

    decision = dense_tensile_table_decisions(
        source, {"Wrought (AMS 4928)": ("Wrought (AMS 4928)",)}
    )[0]

    assert decision.cells == ()
    assert decision.status != "eligible"


def test_v203_dense_table_fails_closed_for_ambiguous_owner_alias():
    source = """
| Sample | UTS (MPa) |
| --- | --- |
| HT | 781 |
"""

    decision = dense_tensile_table_decisions(
        source,
        {"Ti64-H": ("HT",), "Ti64-V": ("HT",)},
    )[0]

    assert decision.status == "rejected"
    assert decision.cells == ()
    assert decision.reason == "ambiguous_target_owner_alias"


def test_v203_dense_table_requires_explicit_unit_and_target_owner():
    missing_unit = """
| Sample | UTS |
| --- | --- |
| Ti64-H | 781 |
"""
    cited_reference = """
| Material | UTS (MPa) |
| --- | --- |
| Literature alloy [12] | 900 [12] |
"""

    missing_unit_decision = dense_tensile_table_decisions(
        missing_unit, {"Ti64-H": ("Ti64-H",)}
    )[0]
    reference_decision = dense_tensile_table_decisions(
        cited_reference, {"Ti64-H": ("Ti64-H",)}
    )[0]

    assert missing_unit_decision.status == "not_applicable"
    assert missing_unit_decision.cells == ()
    assert reference_decision.status == "rejected"
    assert reference_decision.cells == ()
    assert reference_decision.reason == "no_unique_target_owner"


def test_v203_dense_table_decisions_are_stable_under_owner_mapping_order():
    source = """
| Sample | UTS (MPa) |
| --- | --- |
| Ti64-H | 781 |
"""

    first = dense_tensile_table_decisions(
        source, {"Ti64-V": ("Ti64-V",), "Ti64-H": ("Ti64-H",)}
    )
    second = dense_tensile_table_decisions(
        source, {"Ti64-H": ("Ti64-H",), "Ti64-V": ("Ti64-V",)}
    )

    assert [row.to_dict() for row in first] == [row.to_dict() for row in second]


def test_v204_tensile_assertion_resolves_single_owner_multi_property_bundle():
    source = (
        "The AP-HEA exhibits a YS of ~548 MPa, an ultimate tensile strength "
        "of ~835 MPa, and a fracture elongation of ~30 %."
    )
    owners = {
        "owner-ap": ("AP-HEA",),
        "owner-ht": ("HT-HEA",),
    }

    yield_decision = resolve_tensile_assertion_coordinate(
        property_name="YS",
        value_raw="~548",
        unit_raw="MPa",
        evidence=("a YS of ~548 MPa",),
        source_text=source,
        owner_aliases=owners,
    )
    elongation_decision = resolve_tensile_assertion_coordinate(
        property_name="fracture elongation",
        value_raw="~30",
        unit_raw="%",
        evidence=("fracture elongation of ~30 %",),
        source_text=source,
        owner_aliases=owners,
    )

    assert yield_decision.status == "matched"
    assert yield_decision.coordinate is not None
    assert yield_decision.coordinate.owner_key == "owner-ap"
    assert yield_decision.coordinate.property_name == "Yield Strength"
    assert yield_decision.coordinate.value_raw == "~548"
    assert yield_decision.coordinate.unit_raw == "MPa"
    assert yield_decision.coordinate.assertion_type == "direct"
    assert yield_decision.coordinate.source_coordinate_key.startswith(
        "tensile-assertion:"
    )
    assert elongation_decision.status == "matched"
    assert elongation_decision.coordinate is not None
    assert elongation_decision.coordinate.owner_key == "owner-ap"


def test_v204_tensile_assertion_maps_two_owner_value_bundles_without_fanout():
    source = (
        "L70 had YS: 404 ± 5 MPa and UTS: 556 ± 11 MPa, whereas L90 had "
        "YS: 394 ± 15 MPa and UTS: 456 ± 4 MPa."
    )
    owners = {"owner-l70": ("L70",), "owner-l90": ("L90",)}

    l70 = resolve_tensile_assertion_coordinate(
        property_name="UTS",
        value_raw="556 ± 11",
        unit_raw="MPa",
        evidence=("UTS: 556 ± 11 MPa",),
        source_text=source,
        owner_aliases=owners,
    )
    l90 = resolve_tensile_assertion_coordinate(
        property_name="UTS",
        value_raw="456 ± 4",
        unit_raw="MPa",
        evidence=("UTS: 456 ± 4 MPa",),
        source_text=source,
        owner_aliases=owners,
    )

    assert l70.status == "matched"
    assert l70.coordinate is not None
    assert l70.coordinate.owner_key == "owner-l70"
    assert l90.status == "matched"
    assert l90.coordinate is not None
    assert l90.coordinate.owner_key == "owner-l90"
    assert l70.coordinate.bundle_key == l90.coordinate.bundle_key
    assert l70.coordinate.source_coordinate_key != l90.coordinate.source_coordinate_key


def test_v204_tensile_assertion_maps_property_value_respectively_sequence():
    source = (
        "For HT-HEA, the YS and UTS respectively increased to ~748 MPa and "
        "~1148 MPa."
    )
    owners = {"owner-ht": ("HT-HEA",)}

    yield_decision = resolve_tensile_assertion_coordinate(
        property_name="YS",
        value_raw="~748",
        unit_raw="MPa",
        evidence=("YS and UTS respectively increased to ~748 MPa and ~1148 MPa",),
        source_text=source,
        owner_aliases=owners,
    )
    uts_decision = resolve_tensile_assertion_coordinate(
        property_name="UTS",
        value_raw="~1148",
        unit_raw="MPa",
        evidence=("YS and UTS respectively increased to ~748 MPa and ~1148 MPa",),
        source_text=source,
        owner_aliases=owners,
    )

    assert yield_decision.status == "matched"
    assert uts_decision.status == "matched"
    assert yield_decision.coordinate is not None
    assert uts_decision.coordinate is not None
    assert yield_decision.coordinate.assertion_type == "ordered"
    assert uts_decision.coordinate.assertion_type == "ordered"
    assert yield_decision.coordinate.owner_key == "owner-ht"
    assert uts_decision.coordinate.owner_key == "owner-ht"


def test_v204_tensile_assertion_allows_only_adjacent_unique_continuation():
    source = (
        "The LPBF alloy had a yield strength of 482 ± 1 MPa. "
        "Its ultimate tensile strength was 539 ± 1 MPa and elongation was "
        "8.8 ± 0.7 %."
    )
    owners = {"owner-lpbf": ("LPBF alloy",)}

    decision = resolve_tensile_assertion_coordinate(
        property_name="ultimate tensile strength",
        value_raw="539 ± 1",
        unit_raw="MPa",
        evidence=("ultimate tensile strength was 539 ± 1 MPa",),
        source_text=source,
        owner_aliases=owners,
    )

    assert decision.status == "matched"
    assert decision.coordinate is not None
    assert decision.coordinate.owner_key == "owner-lpbf"
    assert decision.coordinate.assertion_type == "continuation"
    assert decision.coordinate.source_text.startswith("the lpbf alloy")


def test_v204_tensile_assertion_fails_closed_for_ambiguous_owner_or_value_scope():
    ambiguous_owner = (
        "A1 and A2 were tested. The reported yield strength was 900 MPa."
    )
    mismatched_order = (
        "For A1 and A2, the yield strengths were 900 MPa, respectively."
    )
    owners = {"owner-a1": ("A1",), "owner-a2": ("A2",)}

    first = resolve_tensile_assertion_coordinate(
        property_name="yield strength",
        value_raw="900",
        unit_raw="MPa",
        evidence=("yield strength was 900 MPa",),
        source_text=ambiguous_owner,
        owner_aliases=owners,
    )
    second = resolve_tensile_assertion_coordinate(
        property_name="yield strength",
        value_raw="900",
        unit_raw="MPa",
        evidence=("yield strengths were 900 MPa",),
        source_text=mismatched_order,
        owner_aliases=owners,
    )

    assert first.status == "ambiguous"
    assert first.coordinate is None
    assert second.status == "ambiguous"
    assert second.coordinate is None


def test_v204_tensile_assertion_requires_literal_numeric_value_and_unit():
    source = "A1 had higher strength and similar ductility than A2."
    owners = {"owner-a1": ("A1",), "owner-a2": ("A2",)}

    decision = resolve_tensile_assertion_coordinate(
        property_name="yield strength",
        value_raw="higher",
        unit_raw="MPa",
        evidence=(source,),
        source_text=source,
        owner_aliases=owners,
    )

    assert decision.status == "not_found"
    assert decision.coordinate is None


def test_v204_tensile_assertion_decision_is_owner_mapping_order_stable():
    source = "A1 had an ultimate tensile strength of 900 ± 5 MPa."
    kwargs = {
        "property_name": "UTS",
        "value_raw": "900 ± 5",
        "unit_raw": "MPa",
        "evidence": ("ultimate tensile strength of 900 ± 5 MPa",),
        "source_text": source,
    }

    first = resolve_tensile_assertion_coordinate(
        **kwargs,
        owner_aliases={"owner-a2": ("A2",), "owner-a1": ("A1",)},
    )
    second = resolve_tensile_assertion_coordinate(
        **kwargs,
        owner_aliases={"owner-a1": ("A1",), "owner-a2": ("A2",)},
    )

    assert first.to_dict() == second.to_dict()


def test_v204_tensile_assertion_prefers_complete_owner_alias_over_suffix_alias():
    source = "The AP-HEA had a yield strength of 548 MPa."

    decision = resolve_tensile_assertion_coordinate(
        property_name="yield strength",
        value_raw="548",
        unit_raw="MPa",
        evidence=("yield strength of 548 MPa",),
        source_text=source,
        owner_aliases={"owner-generic": ("HEA",), "owner-ap": ("AP-HEA",)},
    )

    assert decision.status == "matched"
    assert decision.coordinate is not None
    assert decision.coordinate.owner_key == "owner-ap"


def test_v204_tensile_assertion_preserves_escaped_percent_value():
    source = (
        "The newly developed alloy LPBF sample showed a high yield strength of "
        "482 ± 1 MPa and good elongation of 8.8 ± 0.7\\%."
    )

    decision = resolve_tensile_assertion_coordinate(
        property_name="elongation",
        value_raw="8.8 ± 0.7",
        unit_raw="%",
        evidence=("elongation of 8.8 ± 0.7%",),
        source_text=source,
        owner_aliases={"owner-lpbf": ("LPBF sample",)},
    )

    assert decision.status == "matched"
    assert decision.coordinate is not None
    assert decision.coordinate.owner_key == "owner-lpbf"
    assert decision.coordinate.value_raw == "8.8 ± 0.7"
    assert decision.coordinate.unit_raw == "%"


def test_v204_tensile_assertion_binds_literal_result_temperature_across_fig_split():
    source = (
        "Tensile properties at 800 °C of the multi-spot sample L70 "
        "(YS: 404 ± 5 MPa, UTS: 556 ± 11 MPa, EL: 17.0 ± 3.1 %, Fig. "
        "7d to f) are generally better than the L90 counterpart "
        "(YS: 394 ± 15 MPa, UTS: 456 ± 4 MPa, EL: 18.4 ± 4.6 %)."
    )
    owners = {"owner-l70": ("L70",), "owner-l90": ("L90",)}

    l70 = resolve_tensile_assertion_coordinate(
        property_name="YS",
        value_raw="404 ± 5",
        unit_raw="MPa",
        evidence=("YS: 404 ± 5 MPa",),
        source_text=source,
        owner_aliases=owners,
    )
    l90 = resolve_tensile_assertion_coordinate(
        property_name="YS",
        value_raw="394 ± 15",
        unit_raw="MPa",
        evidence=("YS: 394 ± 15 MPa",),
        source_text=source,
        owner_aliases=owners,
    )

    assert l70.status == "matched"
    assert l90.status == "matched"
    assert l70.coordinate is not None
    assert l90.coordinate is not None
    assert l70.coordinate.condition_raw == "800 °c"
    assert l90.coordinate.condition_raw == "800 °c"


def test_v204_tensile_assertion_never_binds_preparation_temperature_as_test_temperature():
    source = (
        "A1 was heat treated at 800 °C for 4 h and then exhibited a yield "
        "strength of 900 MPa."
    )

    decision = resolve_tensile_assertion_coordinate(
        property_name="yield strength",
        value_raw="900",
        unit_raw="MPa",
        evidence=("yield strength of 900 MPa",),
        source_text=source,
        owner_aliases={"owner-a1": ("A1",)},
    )

    assert decision.status == "matched"
    assert decision.coordinate is not None
    assert decision.coordinate.condition_raw == ""


def test_v204_tensile_assertion_does_not_choose_between_two_result_temperatures():
    source = (
        "A1 had a yield strength of 900 MPa in tests at 25 °C and 800 °C."
    )

    decision = resolve_tensile_assertion_coordinate(
        property_name="yield strength",
        value_raw="900",
        unit_raw="MPa",
        evidence=("yield strength of 900 MPa",),
        source_text=source,
        owner_aliases={"owner-a1": ("A1",)},
    )

    assert decision.status == "matched"
    assert decision.coordinate is not None
    assert decision.coordinate.condition_raw == ""


def test_v204_tensile_assertion_does_not_bind_sample_state_temperature():
    source = "The 1280 °C sample showed a UTS of 612 MPa."

    decision = resolve_tensile_assertion_coordinate(
        property_name="ultimate tensile strength",
        value_raw="612",
        unit_raw="MPa",
        evidence=("UTS of 612 MPa",),
        source_text=source,
        owner_aliases={"owner-1280": ("1280 °C sample",)},
    )

    assert decision.status == "matched"
    assert decision.coordinate is not None
    assert decision.coordinate.owner_key == "owner-1280"
    assert decision.coordinate.condition_raw == ""


def test_v204_tensile_assertion_does_not_jump_over_an_intervening_comparison_clause():
    source = (
        "The CoCrNi alloy demonstrates an ultimate tensile strength of 781 MPa "
        "and an elongation at failure of 42.2%, while the "
        "CoCrNi(Al0.6TiFe)0.5 alloy demonstrates an ultimate tensile strength "
        "of 1165.2 MPa."
    )
    owners = {
        "owner-base": ("CoCrNi",),
        "owner-alloyed": ("CoCrNi(Al0.6TiFe)0.5",),
    }

    decision = resolve_tensile_assertion_coordinate(
        property_name="ultimate tensile strength",
        value_raw="781",
        unit_raw="MPa",
        evidence=("ultimate tensile strength of 781 MPa",),
        source_text=source,
        owner_aliases=owners,
    )

    assert decision.status == "matched"
    assert decision.coordinate is not None
    assert decision.coordinate.owner_key == "owner-base"


def test_v204_tensile_assertion_accepts_only_direct_parenthesized_following_owner():
    source = (
        "Yield and ultimate tensile strengths increased from 486.0 and "
        "781.2 MPa (CoCrNi) to 887.2 and 1165.2 MPa "
        "(CoCrNi(Al0.6TiFe)0.5)."
    )
    owners = {
        "owner-base": ("CoCrNi",),
        "owner-alloyed": ("CoCrNi(Al0.6TiFe)0.5",),
    }

    base = resolve_tensile_assertion_coordinate(
        property_name="ultimate tensile strength",
        value_raw="781.2",
        unit_raw="MPa",
        evidence=("781.2 MPa (CoCrNi)",),
        source_text=source,
        owner_aliases=owners,
    )
    alloyed = resolve_tensile_assertion_coordinate(
        property_name="ultimate tensile strength",
        value_raw="1165.2",
        unit_raw="MPa",
        evidence=("1165.2 MPa (CoCrNi(Al0.6TiFe)0.5)",),
        source_text=source,
        owner_aliases=owners,
    )

    assert base.status == "matched"
    assert alloyed.status == "matched"
    assert base.coordinate is not None
    assert alloyed.coordinate is not None
    assert base.coordinate.owner_key == "owner-base"
    assert alloyed.coordinate.owner_key == "owner-alloyed"
