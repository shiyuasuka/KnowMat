from knowmat.alpha25.contracts import PropertyFact
from knowmat.alpha25.source_coordinates import (
    dense_tensile_table_decisions,
    discrete_tensile_sidecars,
    logical_tables,
    resolve_structured_table_record,
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
