from knowmat.alpha25.planner import (
    build_evidence_units,
    classify_axes,
    fact_signal_score,
    plan_axis_tasks,
    plan_combined_axis_tasks,
    plan_inventory_tasks,
    needs_inventory,
    split_task_once,
)


def test_axis_classifier_uses_only_current_evidence_signals():
    axes = classify_axes(
        "The alloy was annealed at 800 °C. Its grain size and yield strength were measured."
    )

    assert axes == ("processing", "structure", "properties")


def test_wide_dense_table_is_pre_split_by_columns_and_rows():
    rows = "\n".join(
        f"| Property {index} | {index} | {index + 1} | {index + 2} | {index + 3} |"
        for index in range(5)
    )
    paper = f"""Table 2 Mechanical properties
| Variable | S1 | S2 | S3 | S4 |
|---|---:|---:|---:|---:|
{rows}

Values are means.
"""

    units = build_evidence_units(paper, table_columns=2, table_rows=2)
    tables = [unit for unit in units if unit.kind == "table"]

    assert len(tables) == 6
    assert all(int(unit.metadata["sample_columns"]) <= 2 for unit in tables)
    assert all(int(unit.metadata["data_rows"]) <= 2 for unit in tables)
    assert all("Table 2 Mechanical properties" in unit.text for unit in tables)
    assert all("Values are means." in unit.text for unit in tables)
    assert {anchor for unit in tables for anchor in unit.sample_anchors} == {
        "S1",
        "S2",
        "S3",
        "S4",
    }


def test_row_oriented_table_uses_sample_rows_not_metric_headers():
    paper = """Table 1 Tensile properties
| Sample | YS (MPa) | Elongation (%) |
|---|---:|---:|
| AF | 900 | 8 |
| HT sample | 850 | 12 |
"""

    tables = [
        unit
        for unit in build_evidence_units(paper, table_columns=2, table_rows=8)
        if unit.kind == "table"
    ]

    assert len(tables) == 1
    assert tables[0].sample_anchors == ("AF", "HT sample")


def test_fit_parameter_table_does_not_treat_orientations_as_material_samples():
    paper = """Table 2 Fitting parameters
| Fit parameter | Horizontal sample | Vertical sample |
|---|---:|---:|
| E (GPa) | 113.8 | 113.5 |
| sigma_f (MPa) | 1143.7 | 1270.1 |
| b | -0.0499 | -0.0607 |
"""

    tables = [unit for unit in build_evidence_units(paper) if unit.kind == "table"]

    assert len(tables) == 1
    assert tables[0].sample_anchors == ()


def test_material_state_rows_are_inferred_when_first_header_names_family():
    paper = """Table 2 Corrosion properties
| Al5Ti5 HEAs | E_corr (mV) | E_pit (mV) |
|---|---:|---:|
| As-printed | -336 | 355 |
| Aged | -311 | 477 |
"""

    tables = [unit for unit in build_evidence_units(paper) if unit.kind == "table"]

    assert tables[0].sample_anchors == ("As-printed", "Aged")


def test_test_specimen_numbers_are_not_material_anchors():
    paper = """Table 5 Stress-life data for failure specimens
| Crack initiation location | Specimen number | Fatigue life | Stress amplitude (MPa) |
|---|---:|---:|---:|
| Surface | 1 | 1.68e6 | 536.78 |
| Interior | 2 | 4.50e7 | 536.78 |
"""

    tables = [unit for unit in build_evidence_units(paper) if unit.kind == "table"]

    assert tables[0].sample_anchors == ()


def test_compact_numbered_sample_rows_are_preserved_as_inventory_anchors():
    paper = """Table 1 Designed compositions
| Sample | Cu (wt%) | Li (wt%) |
|---|---:|---:|
| #1 | 4.0 | 1.2 |
| #2 | 4.0 | 1.3 |
"""

    tables = [unit for unit in build_evidence_units(paper) if unit.kind == "table"]

    assert {anchor for unit in tables for anchor in unit.sample_anchors} == {"#1", "#2"}


def test_html_multirow_table_finds_nonfirst_sample_id_column():
    paper = """Table 1 Process combinations and tensile properties
<table><tr><td rowspan="2" colspan="2">Iteration and Sample Number</td><td colspan="2">Printing Parameters</td><td>Measured Property</td></tr><tr><td>Laser Power (W)</td><td>Scan Speed (mm/s)</td><td>UTS (MPa)</td></tr><tr><td rowspan="2">1</td><td>1-1</td><td>250</td><td>1100</td><td>1061</td></tr><tr><td>1-2</td><td>250</td><td>1150</td><td>1065</td></tr><tr><td>2</td><td>2-1</td><td>200</td><td>2000</td><td>1221</td></tr></table>
"""

    tables = [unit for unit in build_evidence_units(paper) if unit.kind == "table"]

    assert {anchor for unit in tables for anchor in unit.sample_anchors} == {
        "1-1",
        "1-2",
        "2-1",
    }
    assert all(unit.metadata["row_sample_column"] == 1 for unit in tables)


def test_html_colspan_condition_headers_are_items_but_comments_are_not():
    paper = """Table 2 Properties of walls made with distinct delay conditions
<table><tr><td>Properties</td><td colspan="2">0 s Delay</td><td colspan="2">120 s Delay</td><td>Comments</td></tr><tr><td>Yield strength (MPa)</td><td colspan="2">817</td><td colspan="2">860</td><td>delay increased strength</td></tr></table>
"""

    tables = [unit for unit in build_evidence_units(paper) if unit.kind == "table"]

    assert {anchor for unit in tables for anchor in unit.sample_anchors} == {
        "0 s Delay",
        "120 s Delay",
    }


def test_html_numeric_method_identifier_stays_in_multirow_header():
    paper = r"""Grain size of GA and WA alloy samples.
<table><tr><td rowspan="3">Sintering temperature [^\circC]</td><td colspan="4">Grain size [\mum]</td></tr><tr><td colspan="2">GA</td><td colspan="2">WA</td></tr><tr><td>Imagej analysis</td><td>ASTM E-112-13</td><td>Imagej analysis</td><td>ASTM E-112-13</td></tr><tr><td>1225</td><td>39</td><td>5.5</td><td>80</td><td>3.5</td></tr><tr><td>1240</td><td>45</td><td>5.0</td><td>83</td><td>3.5</td></tr></table>
"""

    tables = [
        unit
        for unit in build_evidence_units(
            paper, table_columns=8, table_rows=12, structure_table_cells=36
        )
        if unit.kind == "table"
    ]

    assert len(tables) == 1
    assert tables[0].metadata["data_rows"] == 2
    assert "GA / Imagej analysis" in tables[0].text
    assert "GA / ASTM E-112-13" in tables[0].text


def test_processing_temperature_rows_cross_material_series_into_state_anchors():
    paper = r"""Grain and pore sizes of the WA and GA powder alloy 625 sintered samples.
<table><tr><td rowspan="3">Sintering temperature [^\circC]</td><td colspan="4">Grain size [\mum]</td></tr><tr><td colspan="2">GA</td><td colspan="2">WA</td></tr><tr><td>Imagej analysis</td><td>ASTM E-112-13</td><td>Imagej analysis</td><td>ASTM E-112-13</td></tr><tr><td>1225</td><td>39</td><td>5.5</td><td>80</td><td>3.5</td></tr><tr><td>1240</td><td>45</td><td>5.0</td><td>83</td><td>3.5</td></tr></table>
"""

    tables = [unit for unit in build_evidence_units(paper) if unit.kind == "table"]
    anchors = {
        (anchor.sample_id_raw, anchor.state_raw)
        for unit in tables
        for anchor in unit.state_anchors
    }

    assert anchors == {
        ("GA", "sintered at 1225 °C"),
        ("GA", "sintered at 1240 °C"),
        ("WA", "sintered at 1225 °C"),
        ("WA", "sintered at 1240 °C"),
    }
    assert all(
        all(
            evidence in unit.text
            for evidence in anchor.source_evidence
        )
        for unit in tables
        for anchor in unit.state_anchors
    )

    tasks = plan_combined_axis_tasks(tables)
    assert {
        (anchor.sample_id_raw, anchor.state_raw)
        for task in tasks
        for anchor in task.state_anchors
    } == anchors


def test_test_temperature_rows_do_not_create_material_state_anchors():
    paper = r"""Tensile properties of GA and WA alloy samples.
<table><tr><td>Tensile test temperature [^\circC]</td><td>GA</td><td>WA</td></tr><tr><td>25</td><td>900</td><td>850</td></tr><tr><td>650</td><td>700</td><td>620</td></tr></table>
"""

    tables = [unit for unit in build_evidence_units(paper) if unit.kind == "table"]

    assert tables
    assert all(not unit.state_anchors for unit in tables)


def test_generic_numeric_row_dimension_does_not_create_state_anchors():
    paper = r"""Thermal response of GA and WA alloy samples.
<table><tr><td>Temperature [^\circC]</td><td>GA</td><td>WA</td></tr><tr><td>25</td><td>1.0</td><td>1.1</td></tr><tr><td>650</td><td>2.0</td><td>2.1</td></tr></table>
"""

    tables = [unit for unit in build_evidence_units(paper) if unit.kind == "table"]

    assert tables
    assert all(not unit.state_anchors for unit in tables)


def test_metric_only_table_headers_do_not_become_sample_anchors():
    paper = """Table 1 Process settings
| Process | Hatch distance (mm) | Layer thickness (μm) |
|---|---:|---:|
| LPBF | 0.1 | 30 |
"""

    tables = [unit for unit in build_evidence_units(paper) if unit.kind == "table"]

    assert tables[0].sample_anchors == ("LPBF",)


def test_process_variable_table_uses_material_columns_not_metric_rows():
    paper = """Table 1 Process variables
| Process Variables | Wall 1 | Wall 2 |
|---|---:|---:|
| Laser Power (W) | 5000 | 5000 |
| Interlayer Delay (s) | 0 | 120 |
"""

    tables = [unit for unit in build_evidence_units(paper) if unit.kind == "table"]

    assert tables[0].sample_anchors == ("Wall 1", "Wall 2")


def test_step_purpose_table_uses_heat_treatment_rows_not_stage_columns():
    paper = """Table 2 Applied heat treatments
| Step Purpose | 1 Solution treatment | 2 Age hardening |
|---|---:|---:|
| HT1 | 1250 °C, 4 h | 700 °C, 24 h |
| HT2 | 1250 °C, 4 h | 1000 °C, 12 h |
"""

    tables = [unit for unit in build_evidence_units(paper) if unit.kind == "table"]

    assert tables[0].sample_anchors == ("HT1", "HT2")


def test_square_relation_matrix_is_one_unit_without_material_anchors():
    paper = """Table 3 Pairwise variant relationships
| | A | B | C |
|---|---:|---:|---:|
| A | 1 | 2 | 3 |
| B | 2 | 1 | 4 |
| C | 3 | 4 | 1 |
"""

    tables = [
        unit
        for unit in build_evidence_units(paper, table_columns=2, table_rows=2)
        if unit.kind == "table"
    ]

    assert len(tables) == 1
    assert tables[0].sample_anchors == ()
    assert tables[0].metadata["relation_matrix"] is True


def test_feedstock_table_columns_anchor_the_owning_process_sample():
    paper = """Table 1 Feedstock composition
| Element | WAAM Feedstock Ti-6Al-4V Grade 23 | EBAM Feedstock Ti-6Al-4V Grade 5 |
|---|---:|---:|
| Al | 6.75 | 7.5 |
| V | 4.5 | 4.5 |
"""

    tables = [unit for unit in build_evidence_units(paper) if unit.kind == "table"]

    assert tables[0].sample_anchors == ("WAAM", "EBAM")


def test_prose_units_do_not_use_overlap_and_plan_only_detected_axes():
    paper = "## Processing\nThe sample was annealed at 800 °C.\n\n## Results\nYield strength was 900 MPa."

    units = build_evidence_units(paper, max_prose_chars=1000)
    tasks = plan_axis_tasks(units)

    assert {task.axis for task in tasks} == {"processing", "properties"}
    assert len({task.task_id for task in tasks}) == len(tasks)


def test_failed_task_splits_only_once():
    paper = "Yield strength was 900 MPa.\n\n" * 80
    task = plan_axis_tasks(build_evidence_units(paper, max_prose_chars=6000))[0]

    children = split_task_once(task)

    assert len(children) == 2
    assert all(child.parent_task_id == task.task_id for child in children)
    assert all(split_task_once(child) == [] for child in children)
    assert all(child.output_token_budget == task.output_token_budget for child in children)


def test_parse_failure_can_use_an_explicit_deeper_split_cap():
    paper = "Yield strength was 900 MPa.\n\n" * 160
    task = plan_axis_tasks(build_evidence_units(paper, max_prose_chars=12000))[0]

    children = split_task_once(task, max_depth=2, min_chars=200)
    grandchildren = split_task_once(children[0], max_depth=2, min_chars=200)

    assert children
    assert grandchildren
    assert all(grandchild.split_depth == 2 for grandchild in grandchildren)
    assert all(
        split_task_once(grandchild, max_depth=2, min_chars=200) == []
        for grandchild in grandchildren
    )


def test_failure_split_rejects_an_edge_paragraph_break_and_stays_balanced():
    paper = (
        "Sample A had a yield strength of 900 MPa and elongation of 12%. " * 45
        + "\n\nTable 1 Tensile properties"
    )
    task = plan_axis_tasks(
        build_evidence_units(paper, max_prose_chars=6000),
        axis_max_chars={"properties": 5000},
    )[0]

    children = split_task_once(task, max_depth=1, min_chars=200)

    assert len(children) == 2
    assert max(len(child.evidence_text) for child in children) <= int(
        len(task.evidence_text) * 0.67
    )


def test_inventory_is_planned_only_for_source_named_labels():
    named = build_evidence_units("Sample A1 was annealed at 800 °C.")[0]
    generic = build_evidence_units("The alloy was annealed at 800 °C.")[0]

    assert needs_inventory(named) is True
    assert needs_inventory(generic) is False


def test_inventory_ignores_titlecase_words_and_measurement_acronyms():
    title = build_evidence_units(
        "Materials Science enables alloy design. The samples were examined by TEM. "
        "UTS, YS, and TE were measured."
    )[0]
    named = build_evidence_units("The H230AM samples were annealed.")[0]

    assert needs_inventory(title) is False
    assert needs_inventory(named) is True


def test_inventory_skips_prose_that_only_repeats_deterministic_table_labels():
    paper = """Table 1 Process combinations
| Sample | Laser power (W) |
|---|---:|
| 1-1 | 250 |
| 1-2 | 275 |

Samples 1-1 and 1-2 were selected for tensile testing.
"""

    units = build_evidence_units(paper)

    assert {anchor for unit in units for anchor in unit.sample_anchors} == {
        "1-1",
        "1-2",
    }
    assert plan_inventory_tasks(units) == []


def test_inventory_keeps_prose_when_it_introduces_a_label_absent_from_tables():
    paper = """Table 1 Process combinations
| Sample | Laser power (W) |
|---|---:|
| 1-1 | 250 |

Samples 1-1 and 2-1 were selected for tensile testing.
"""

    inventory = plan_inventory_tasks(build_evidence_units(paper))

    assert len(inventory) == 1
    assert "2-1" in inventory[0].evidence_text


def test_inventory_does_not_treat_figure_ranges_as_new_sample_labels():
    paper = """Table 1 Process combinations
| Sample | Laser power (W) |
|---|---:|
| 1-1 | 250 |

Sample 1-1 is discussed in Supplementary Figs. 3-7.
"""

    assert plan_inventory_tasks(build_evidence_units(paper)) == []


def test_small_heading_sections_are_coalesced_by_axis_without_overlap():
    paper = "\n\n".join(
        f"## Section {index}\nSample A{index} was annealed and its yield strength measured."
        for index in range(1, 5)
    )

    units = build_evidence_units(paper, max_prose_chars=6000)
    inventory = plan_inventory_tasks(units, max_chars=6000)
    tasks = plan_axis_tasks(units, max_chars=6000)

    assert len(units) == 4
    assert len(inventory) == 1
    assert len([task for task in tasks if task.axis == "processing"]) == 1
    assert len([task for task in tasks if task.axis == "properties"]) == 1
    assert inventory[0].evidence_text.count("Sample A") == 4


def test_combined_axis_planner_assigns_each_evidence_unit_once():
    paper = """## Processing
Sample A was annealed at 800 °C.

## Results
Sample A had fine grains and yield strength of 900 MPa.

Table 1 Properties
| Sample | UTS (MPa) | Elongation (%) |
|---|---:|---:|
| A | 950 | 12 |
"""
    units = build_evidence_units(
        paper, max_prose_chars=8000, table_columns=4, table_rows=12
    )

    tasks = plan_combined_axis_tasks(units, max_chars=8000)

    assert {task.axis for task in tasks} == {"combined"}
    assert len(tasks) == 2
    assert sum("annealed at 800 °C" in task.evidence_text for task in tasks) == 1
    assert sum("| A | 950 | 12 |" in task.evidence_text for task in tasks) == 1
    assert max(task.output_token_budget for task in tasks) == 4216


def test_dense_combined_table_starts_at_recovery_budget():
    rows = "\n".join(
        f"| S{index} | {900 + index} | {10 + index} | {100 + index} | {20 + index} |"
        for index in range(1, 8)
    )
    paper = f"""Table 1 Properties
| Sample | UTS | Elongation | YS | Hardness |
|---|---:|---:|---:|---:|
{rows}
"""
    units = build_evidence_units(
        paper, max_prose_chars=8000, table_columns=4, table_rows=12
    )

    tasks = plan_combined_axis_tasks(units, max_chars=8000)

    assert any(task.output_token_budget == 12288 for task in tasks)
    assert all(len(task.evidence_text) <= 8000 for task in tasks)


def test_combined_prose_caps_semantic_units_before_output_overflow():
    paper = "\n\n".join(
        f"## Section {index}\nSample A{index} had a measured strength of {800 + index} MPa."
        for index in range(1, 8)
    )
    units = build_evidence_units(paper, max_prose_chars=8000)

    tasks = plan_combined_axis_tasks(
        units, max_chars=8000, max_units_per_task=4
    )

    assert len(tasks) == 2
    assert all(task.evidence_text.count("## Section") <= 4 for task in tasks)
    assert sum(task.evidence_text.count("measured strength") for task in tasks) == 7


def test_combined_prose_default_packs_up_to_eight_semantic_units():
    paper = "\n\n".join(
        f"## Section {index}\nSample A{index} had a measured strength of {800 + index} MPa."
        for index in range(1, 9)
    )
    units = build_evidence_units(paper, max_prose_chars=8000)

    tasks = plan_combined_axis_tasks(units, max_chars=8000)

    assert len(tasks) == 1
    assert tasks[0].evidence_text.count("## Section") == 8
    assert len(tasks[0].evidence_text) <= 8000


def test_long_sparse_combined_prose_keeps_normal_output_budget():
    paper = "\n\n".join(
        f"## Section {index}\nSample A{index} had measured strength and "
        + ("supporting experimental context. " * 75)
        for index in range(1, 5)
    )
    units = build_evidence_units(paper, max_prose_chars=8000)

    tasks = plan_combined_axis_tasks(units, max_chars=8000, max_units_per_task=4)

    assert any(len(task.evidence_text) >= 4000 for task in tasks)
    assert all(task.output_token_budget == 4096 for task in tasks)


def test_fact_dense_four_thousand_character_prose_starts_at_recovery_budget():
    sentence = "Sample A had fine precipitates and yield strength of 900 MPa. "
    paper = sentence * 70
    units = build_evidence_units(paper, max_prose_chars=8000)

    tasks = plan_combined_axis_tasks(
        units, max_chars=8000, dense_fact_signals=18, dense_max_chars=4000
    )

    assert len(tasks) >= 2
    assert max(len(task.evidence_text) for task in tasks) <= 4000
    assert any(task.output_token_budget == 12288 for task in tasks)
    assert all(
        task.output_token_budget == 12288
        for task in tasks
        if len(task.evidence_text) >= 3000
    )


def test_sparse_combined_prose_can_use_eight_thousand_character_capacity():
    paper = (
        "Sample A had measured strength. "
        + "Supporting experimental context without another reported value. " * 120
    )
    units = build_evidence_units(paper, max_prose_chars=8000)

    tasks = plan_combined_axis_tasks(
        units,
        max_chars=6000,
        dense_fact_signals=18,
        sparse_fact_signals=4,
        sparse_max_chars=8000,
    )

    assert len(tasks) == 1
    assert 6000 < len(tasks[0].evidence_text) <= 8000
    assert tasks[0].output_token_budget == 4096


def test_five_row_four_metric_table_starts_at_recovery_budget():
    rows = "\n".join(
        f"| S{index} | {900 + index} | {10 + index} | {100 + index} | {20 + index} |"
        for index in range(1, 6)
    )
    paper = f"""Table 1 Properties
| Sample | UTS | Elongation | YS | Hardness |
|---|---:|---:|---:|---:|
{rows}
"""
    units = build_evidence_units(
        paper, max_prose_chars=8000, table_columns=4, table_rows=12
    )

    tasks = plan_combined_axis_tasks(units, max_chars=8000)

    assert any(task.kind == "table" for task in tasks)
    assert any(task.output_token_budget == 12288 for task in tasks)


def test_dense_structure_table_is_row_bounded_before_provider_call():
    rows = "\n".join(
        f"| {1200 + index * 10} | {40 + index} | {80 + index} | "
        f"{4 + index / 10:.1f} | {3 + index / 10:.1f} |"
        for index in range(7)
    )
    paper = f"""Table 1 Grain size
| Temperature | Grain size GA | Grain size WA | Pore size GA | Pore size WA |
|---|---:|---:|---:|---:|
{rows}
"""

    units = build_evidence_units(
        paper,
        max_prose_chars=8000,
        table_columns=4,
        table_rows=12,
        structure_table_cells=16,
    )
    table_units = [unit for unit in units if unit.kind == "table"]
    table_units.sort(key=lambda unit: unit.metadata["column_start"])

    assert len(table_units) == 2
    assert all(
        unit.metadata["data_rows"] * unit.metadata["sample_columns"] <= 16
        for unit in table_units
    )


def test_short_wide_table_projection_can_use_eight_columns():
    headers = " | ".join(f"Metric {index}" for index in range(1, 13))
    separator = " | ".join("---:" for _ in range(12))
    rows = "\n".join(
        "| S{} | {} |".format(
            row,
            " | ".join(str(row * 100 + column) for column in range(1, 13)),
        )
        for row in range(1, 5)
    )
    paper = f"""Table 1 Properties
| Sample | {headers} |
|---|{separator}|
{rows}
"""

    units = build_evidence_units(
        paper,
        max_prose_chars=8000,
        table_columns=8,
        table_rows=12,
        table_cells=36,
        table_min_columns=4,
        table_max_chars=8000,
    )
    table_units = [unit for unit in units if unit.kind == "table"]
    table_units.sort(key=lambda unit: unit.metadata["column_start"])

    assert len(table_units) == 2
    assert [unit.metadata["sample_columns"] for unit in table_units] == [8, 4]
    assert all(
        unit.metadata["data_rows"] * unit.metadata["sample_columns"] <= 36
        for unit in table_units
    )
    assert all(len(unit.text) <= 8000 for unit in table_units)


def test_tall_wide_table_falls_back_to_four_columns_before_llm_call():
    headers = " | ".join(f"Metric {index}" for index in range(1, 13))
    separator = " | ".join("---:" for _ in range(12))
    rows = "\n".join(
        "| S{} | {} |".format(
            row,
            " | ".join(str(row * 100 + column) for column in range(1, 13)),
        )
        for row in range(1, 10)
    )
    paper = f"""Table 1 Properties
| Sample | {headers} |
|---|{separator}|
{rows}
"""

    units = build_evidence_units(
        paper,
        max_prose_chars=8000,
        table_columns=8,
        table_rows=12,
        table_cells=36,
        table_min_columns=4,
        table_max_chars=8000,
    )
    table_units = [unit for unit in units if unit.kind == "table"]

    assert len(table_units) == 3
    assert [unit.metadata["sample_columns"] for unit in table_units] == [4, 4, 4]
    assert all(unit.metadata["projection_cells"] == 36 for unit in table_units)


def test_text_heavy_table_reduces_rows_to_respect_character_ceiling():
    rows = "\n".join(
        f"| S{index} | observation-{index}-" + ("long-text " * 35) + "|"
        for index in range(1, 9)
    )
    paper = f"""Table 1 Material properties
| Sample | Observation |
|---|---|
{rows}
"""

    units = build_evidence_units(
        paper,
        max_prose_chars=8000,
        table_columns=8,
        table_rows=12,
        table_cells=36,
        table_min_columns=4,
        table_max_chars=1200,
        table_context_chars=0,
    )
    table_units = [unit for unit in units if unit.kind == "table"]

    assert len(table_units) > 1
    assert all(len(unit.text) <= 1200 for unit in table_units)
    combined = "\n".join(unit.text for unit in table_units)
    assert all(combined.count(f"observation-{index}-") == 1 for index in range(1, 9))


def test_dense_composition_table_keeps_normal_row_window():
    rows = "\n".join(
        f"| S{index} | {50 + index} | {20 + index} | {10 + index} | balance |"
        for index in range(7)
    )
    paper = f"""Table 1 Chemical composition
| Sample | Ni wt% | Cr wt% | Fe wt% | Co wt% |
|---|---:|---:|---:|---:|
{rows}
"""

    units = build_evidence_units(
        paper,
        max_prose_chars=8000,
        table_columns=4,
        table_rows=12,
        structure_table_cells=16,
    )

    assert len([unit for unit in units if unit.kind == "table"]) == 1


def test_single_dense_section_is_pre_split_to_axis_limit():
    paper = "Sample A1 had a yield strength of 900 MPa. " * 300
    units = build_evidence_units(paper, max_prose_chars=20000)

    tasks = plan_axis_tasks(
        units,
        max_chars=7000,
        axis_max_chars={"properties": 3500},
    )
    property_tasks = [task for task in tasks if task.axis == "properties"]

    assert len(property_tasks) > 1
    assert max(len(task.evidence_text) for task in property_tasks) <= 3500
    assert sum(task.evidence_text.count("yield strength") for task in property_tasks) == 300


def test_combined_long_semantic_unit_is_pre_split_to_six_thousand_chars():
    paper = "Sample A had fine precipitates and yield strength of 900 MPa. " * 140
    units = build_evidence_units(paper, max_prose_chars=8000)

    tasks = plan_combined_axis_tasks(units, max_chars=6000)

    assert len(tasks) >= 2
    assert max(len(task.evidence_text) for task in tasks) <= 6000
    assert sum(task.evidence_text.count("yield strength") for task in tasks) == 140


def test_combined_moderate_units_do_not_merge_past_dense_capacity():
    section = (
        "Sample A had fine precipitates and yield strength of 900 MPa under "
        "carefully documented experimental conditions. " * 28
    )
    paper = f"## First\n{section}\n\n## Second\n{section}"
    units = build_evidence_units(paper, max_prose_chars=8000)

    assert len(units) == 2
    assert all(fact_signal_score(unit.text) < 60 for unit in units)
    assert sum(fact_signal_score(unit.text) for unit in units) >= 60

    tasks = plan_combined_axis_tasks(
        units,
        max_chars=8000,
        dense_fact_signals=60,
        dense_max_chars=6000,
    )

    assert len(tasks) == 2
    assert max(len(task.evidence_text) for task in tasks) <= 6000
    assert sum(task.evidence_text.count("yield strength") for task in tasks) == 56
