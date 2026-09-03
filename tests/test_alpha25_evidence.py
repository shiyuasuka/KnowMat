from knowmat.alpha25.contracts import InventoryResponse, MultiAxisResponse
from knowmat.alpha25.evidence import (
    evidence_is_grounded,
    gate_task_response,
    normalize_evidence_text,
    recover_format_mismatch_records,
    render_table_evidence,
    unique_ordered_table_row_projection,
)


def _response(evidence: str) -> InventoryResponse:
    return InventoryResponse.model_validate(
        {
            "anchors": [
                {
                    "sample_id_raw": "A1",
                    "material_name_raw": "A1 alloy",
                    "state_raw": None,
                    "role": "Target",
                    "data_nature": "Experimental",
                    "source_evidence": [evidence],
                    "confidence": 0.9,
                }
            ]
        }
    )


def test_normalized_literal_evidence_accepts_ocr_line_breaks_and_symbols():
    source = "The micro-\nstructure width was 12 µm – 14 µm."
    evidence = "The microstructure width was 12 μm - 14 μm."

    assert evidence_is_grounded(evidence, source)
    assert normalize_evidence_text("12 µm") == normalize_evidence_text("12 μm")


def test_rendered_latex_presentation_matches_visible_table_value():
    source = r"Ultimate Tensile Strength (MPa): $ 1061 \pm 27.5 $"

    assert evidence_is_grounded("1061 ± 27.5", source)


def test_rendered_latex_greek_and_degree_match_visible_prose():
    source = r"PF in the $ (0001)_{\alpha} $ direction at 1050 ^\circC"

    assert evidence_is_grounded("(0001)_α direction at 1050 °C", source)


def test_mathring_ocr_table_condition_matches_rendered_row():
    source = r"""
| Samples | yield strength (MPa) | Elongation (%) |
| --- | --- | --- |
| AF-200  $ \mathring{A} $  $ \mathring{C} $ | 402  $ \pm $ 14 | 11  $ \pm $ 2 |
"""

    assert evidence_is_grounded(
        "AF-200 Å °C | 402 ± 14 | 11 ± 2",
        source,
    )


def test_mathring_normalization_is_narrow_and_does_not_accept_other_letters():
    source = "| Sample | Value |\n| --- | --- |\n| B | 10 |"

    assert not evidence_is_grounded("B̊ | 10", source)
    assert not evidence_is_grounded(r"\mathring{B} | 10", source)


def test_latex_symbol_spacing_around_punctuation_is_presentation_only():
    source = r"The values ( $ \sigma_y $ ), $ \sigma_{uts} $ and $ \varepsilon_f $ were 1067.6 MPa."
    evidence = r"The values (σ_y), \sigma_{uts} and \varepsilon_f were 1067.6 MPa."

    assert evidence_is_grounded(evidence, source)


def test_latex_varepsilon_matches_rendered_unicode_epsilon():
    source = r"fracture elongation ( $ \varepsilon_f $ ) was 9.1 \pm 1.1 %"
    evidence = "fracture elongation (ε_f) was 9.1 ± 1.1 %"

    assert evidence_is_grounded(evidence, source)


def test_compact_markdown_table_evidence_can_skip_intervening_rows():
    source = r"""
| Properties | 0 s Delay | 120 s Delay |
| --- | --- | --- |
| Yield Stress (MPa) | $ 817 \pm 8.68 $ | $ 859.7 \pm 9.17 $ |
| UTS (MPa) | $ 914.9 \pm 10.89 $ | $ 959 \pm 5.31 $ |
| % Elongation | $ 14.5 \pm 5.17 $ | $ 7.5 \pm 2.09 $ |
"""
    evidence = r"""
| Properties | 0 s Delay | 120 s Delay |
| --- | --- | --- |
| UTS (MPa) | $ 914.9 \pm 10.89 $ | $ 959 \pm 5.31 $ |
"""

    assert evidence_is_grounded(evidence, source)


def test_html_table_row_evidence_is_grounded_by_source_cells():
    source = """
<table><tr><td>Properties</td><td>HT</td><td>200 h</td></tr>
<tr><td>Tensile strength / MPa</td><td>220</td><td>204</td></tr>
<tr><td>Elongation / %</td><td>45</td><td>56</td></tr></table>
"""

    assert evidence_is_grounded(
        "| Tensile strength / MPa | 220 | 204 |", source
    )


def test_table_fallback_does_not_combine_rows_from_different_tables():
    source = """
| Properties | A | B |
| --- | --- | --- |
| UTS (MPa) | 900 | 910 |

| Properties | A | B |
| --- | --- | --- |
| Elongation (%) | 10 | 11 |
"""
    evidence = """
| UTS (MPa) | 900 | 910 |
| Elongation (%) | 10 | 11 |
"""

    assert not evidence_is_grounded(evidence, source)


def test_line_locator_requires_copied_evidence_body():
    source = "The yield strength was 800 MPa."

    assert evidence_is_grounded("paper.md:L12 | The yield strength was 800 MPa.", source)
    assert not evidence_is_grounded("paper.md:L12", source)


def test_semantic_paraphrase_is_rejected():
    result = gate_task_response(
        _response("A1 exhibited very high strength."),
        evidence_unit_id="unit-1",
        evidence_text="The ultimate tensile strength of A1 was 900 MPa.",
    )

    assert not result.complete
    assert result.accepted == []
    assert result.issues[0].code == "ungrounded_source_evidence"


def test_unique_prose_ellipsis_completion_recovers_core_tensile_evidence():
    source = (
        "Upon post-annealing at 600 °C for 8 h, σ0.2 and σu reach "
        "1723 ± 37 MPa and 2153 ± 24 MPa, approximately 24% higher "
        "than the values for the as-built samples, respectively."
    )
    evidence = (
        "σu reach ... 2153 ± 24 MPa, approximately 24% higher than "
        "the values for the as-built samples"
    )
    response = _property_response(
        evidence, owner="as-annealed", value="2153 ± 24"
    )
    response.facts[0].data["data_source"] = "text"

    result = gate_task_response(
        response,
        evidence_unit_id="unique-prose-ellipsis",
        evidence_text=source,
    )

    assert result.complete is True
    assert result.issues == []
    assert [issue.code for issue in result.audit_issues] == [
        "evidence_unique_prose_ellipsis_recovered"
    ]
    accepted = result.accepted[0]
    assert accepted.source_evidence == [source]
    assert accepted.data["source_evidence"] == [source]
    assert result.audit_issues[0].actual["before_evidence"] == evidence
    assert result.audit_issues[0].actual["after_evidence"] == source


def test_prose_ellipsis_completion_rejects_ambiguous_source_sentences():
    evidence = "σu reach ... 2153 ± 24 MPa"
    source = (
        "After route A, σu reach 1723 MPa and 2153 ± 24 MPa. "
        "After route B, σu reach 1800 MPa and 2153 ± 24 MPa."
    )

    result = gate_task_response(
        _property_response(
            evidence, owner="as-annealed", value="2153 ± 24"
        ),
        evidence_unit_id="ambiguous-prose-ellipsis",
        evidence_text=source,
    )

    assert result.complete is False
    assert result.accepted == []
    assert result.audit_issues == []
    assert result.issues[0].code == "ungrounded_source_evidence"


def test_prose_ellipsis_completion_requires_record_value_in_source_sentence():
    evidence = "σu reach ... 2153 ± 24 MPa"
    source = "Upon annealing, σu reach 1723 MPa and 2153 ± 24 MPa."

    result = gate_task_response(
        _property_response(evidence, owner="as-annealed", value="999"),
        evidence_unit_id="wrong-value-prose-ellipsis",
        evidence_text=source,
    )

    assert result.complete is False
    assert result.accepted == []
    assert result.audit_issues == []


def test_prose_ellipsis_completion_does_not_recover_inventory_anchor():
    evidence = "A1 ... alloy"
    result = gate_task_response(
        _response(evidence),
        evidence_unit_id="anchor-prose-ellipsis",
        evidence_text="A1 experimental alloy was fabricated.",
    )

    assert result.complete is False
    assert result.accepted == []
    assert result.audit_issues == []


def test_table_evidence_is_deterministic_source_rendering():
    rendered = render_table_evidence(
        ["Sample", "UTS (MPa)", "Elongation (%)"],
        ["A1", "900", "12"],
        caption="Table 2 Mechanical properties",
        footnotes=["Mean values"],
    )

    assert rendered == (
        "Table 2 Mechanical properties | Sample: A1 | UTS (MPa): 900 | "
        "Elongation (%): 12 | Mean values"
    )


def test_nested_candidate_evidence_is_gated_not_only_fact_wrapper():
    from knowmat.alpha25.contracts import AxisResponse, PropertyFact

    response = AxisResponse(
        axis="properties",
        facts=[
            PropertyFact(
                sample_id_raw="A",
                data={
                    "property_id_candidate": "temporary",
                    "property_name_raw": "yield strength",
                    "value_raw": "900",
                    "unit_raw": "MPa",
                    "test_method_raw": "",
                    "test_standard_raw": "",
                    "test_condition_raw": "",
                    "test_specimen_raw": "",
                    "raw_note": "",
                    "data_source": "text",
                    "source_evidence": ["invented nested quote"],
                    "confidence": 0.9,
                },
                source_evidence=["yield strength was 900 MPa"],
                confidence=0.9,
            )
        ],
    )

    result = gate_task_response(
        response,
        evidence_unit_id="u1",
        evidence_text="A yield strength was 900 MPa.",
    )

    assert result.complete is False
    assert len(result.rejected) == 1


def test_combined_anchor_and_fact_records_share_the_literal_evidence_gate():
    response = MultiAxisResponse.model_validate(
        {
            "anchors": [
                {
                    "sample_id_raw": "A1",
                    "role": "Target",
                    "data_nature": "Experimental",
                    "source_evidence": ["A1 alloy"],
                    "confidence": 0.9,
                }
            ],
            "facts": [],
        }
    )

    accepted = gate_task_response(
        response, evidence_unit_id="u1", evidence_text="The A1 alloy was printed."
    )
    rejected = gate_task_response(
        response, evidence_unit_id="u1", evidence_text="The B1 alloy was printed."
    )

    assert [row.sample_id_raw for row in accepted.accepted] == ["A1"]
    assert rejected.complete is False


def _property_response(evidence: str, *, owner: str = "1-1", value: str = "1061 ± 27.5"):
    return MultiAxisResponse.model_validate(
        {
            "anchors": [],
            "facts": [
                {
                    "sample_id_raw": owner,
                    "axis": "properties",
                    "fact_type": "property",
                    "data": {
                        "property_id_candidate": "temporary",
                        "property_name_raw": "Ultimate Tensile Strength",
                        "value_raw": value,
                        "unit_raw": "MPa",
                        "test_method_raw": "tensile test",
                        "test_standard_raw": "",
                        "test_condition_raw": "",
                        "test_specimen_raw": "",
                        "raw_note": "",
                        "data_source": "table",
                        "source_evidence": [evidence],
                        "confidence": 0.95,
                    },
                    "source_evidence": [evidence],
                    "confidence": 0.95,
                }
            ],
        }
    )


def test_unique_ordered_projection_recovers_cropped_wide_html_row_with_audit():
    source = r"""
<table><tr><td>Iteration</td><td>Sample</td><td>Power</td><td>Speed</td><td>Temp</td><td>Time</td><td>VED</td><td>UTS</td><td>TE</td></tr>
<tr><td>1</td><td>1-1</td><td>250</td><td>1100</td><td>900</td><td>2</td><td>94.69</td><td>$ 1061 \pm 27.5 $</td><td>$ 18.3 \pm 1.5 $</td></tr></table>
"""
    evidence = r"| 1-1 | 2 | 94.69 | $ 1061 \pm 27.5 $ | $ 18.3 \pm 1.5 $ |"

    result = gate_task_response(
        _property_response(evidence),
        evidence_unit_id="wide-table",
        evidence_text=source,
    )

    assert result.complete is True
    assert len(result.accepted) == 1
    assert result.issues == []
    assert [issue.code for issue in result.audit_issues] == [
        "evidence_unique_ordered_projection_recovered"
    ]
    projection = result.audit_issues[0].actual["projection"]
    assert projection["distinct_match_count"] == 1
    assert "<tr>" in projection["source_row"]


def test_full_paper_format_recovery_requires_explicit_owner():
    source = r"""
<table><tr><td>Iteration</td><td>Sample</td><td>Power</td><td>UTS</td></tr>
<tr><td>1</td><td>1-1</td><td>250</td><td>$ 1061 \pm 27.5 $</td></tr></table>
"""
    evidence = "| 1-1 | 250 | $ 1061 \pm 27.5 $ |"
    response = _property_response(evidence, owner="1-1", value="1061 ± 27.5")
    record = response.facts[0]

    recovered, audits = recover_format_mismatch_records([record], source)

    assert recovered == [record]
    assert [issue.code for issue in audits] == [
        "evidence_format_mismatch_recovered"
    ]


def test_full_paper_format_recovery_accepts_deterministic_composite_projection():
    """Recover a compact value-only serialization from planner source views."""

    source = r"""
<table><tr><th>Sample</th><th>Power</th><th>Speed</th><th>UTS</th></tr>
<tr><td>A1</td><td>250</td><td>1100</td><td>1061</td></tr></table>
"""
    # This two-cell serialization is intentionally too short for the ordered
    # table-row fallback.  Each literal cell is nevertheless present in the
    # same deterministic planner projection, so recovery is safe.
    response = _property_response("A1 | 1061", owner="A1", value="1061")

    recovered, audits = recover_format_mismatch_records(
        [response.facts[0]], source
    )

    assert recovered == [response.facts[0]]
    assert [issue.code for issue in audits] == [
        "evidence_format_mismatch_recovered"
    ]


def test_full_paper_format_recovery_rejects_cross_projection_composite():
    source = """
Sample A1 had a UTS of 1061 MPa.

Sample B1 had a UTS of 900 MPa.
"""
    response = _property_response("A1 | 900", owner="A1", value="900")

    recovered, audits = recover_format_mismatch_records(
        [response.facts[0]], source
    )

    assert recovered == []
    assert audits == []


def test_full_paper_format_recovery_rejects_ownerless_projection():
    source = r"""
<table><tr><td>Iteration</td><td>Sample</td><td>Power</td><td>UTS</td></tr>
<tr><td>1</td><td>1-1</td><td>250</td><td>$ 1061 \pm 27.5 $</td></tr></table>
"""
    evidence = "| unknown | 250 | $ 1061 \pm 27.5 $ |"
    response = _property_response(evidence, owner="unknown", value="1061 ± 27.5")

    recovered, audits = recover_format_mismatch_records([response.facts[0]], source)

    assert recovered == []
    assert audits == []


def test_structured_table_cell_recovers_multilevel_header_property_with_audit(
    monkeypatch,
):
    monkeypatch.setenv(
        "KNOWMAT2_ALPHA25_STRUCTURED_TABLE_CELL_RECOVERY_V202", "1"
    )
    source = r"""
<table>
<tr><td colspan="2" rowspan="2">Iteration and Sample Number</td><td colspan="2">Printing Parameters</td><td colspan="2">Measured Properties</td></tr>
<tr><td>Heating Time (h)</td><td>Volumetric Energy Density ( $ J/mm^{3} $)</td><td>Ultimate Tensile Strength (MPa)</td><td>Total Elongation (%)</td></tr>
<tr><td>1</td><td>1-1</td><td>2</td><td>94.69</td><td>$ 1061 \pm 27.5 $</td><td>$ 18.3 \pm 1.5 $</td></tr>
</table>
"""
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
    response = _property_response(evidence[0])
    response.facts[0].source_evidence = evidence
    response.facts[0].data["source_evidence"] = evidence

    result = gate_task_response(
        response,
        evidence_unit_id="multilevel-table",
        evidence_text=source,
    )

    assert result.complete is True
    assert result.issues == []
    assert [issue.code for issue in result.audit_issues] == [
        "evidence_unique_ordered_projection_recovered",
        "evidence_structured_table_cell_recovered",
    ]
    coordinate = result.audit_issues[1].actual["coordinate"]
    assert coordinate["logical_row"] == 2
    assert coordinate["logical_column"] == 4
    assert coordinate["header_path"] == [
        "measured properties",
        "ultimate tensile strength (mpa)",
    ]


def test_structured_table_cell_switch_off_preserves_v201_rejection(monkeypatch):
    monkeypatch.setenv(
        "KNOWMAT2_ALPHA25_STRUCTURED_TABLE_CELL_RECOVERY_V202", "0"
    )
    source = r"""
<table><tr><td rowspan="2">Sample</td><td>Measured Properties</td></tr>
<tr><td>Ultimate Tensile Strength (MPa)</td></tr>
<tr><td>1-1</td><td>$ 1061 \pm 27.5 $</td></tr></table>
"""
    evidence = [
        "| Sample | Measured Properties / Ultimate Tensile Strength (MPa) |",
        "| 1-1 | $ 1061 \\pm 27.5 $ |",
    ]
    response = _property_response(evidence[0])
    response.facts[0].source_evidence = evidence
    response.facts[0].data["source_evidence"] = evidence

    result = gate_task_response(
        response,
        evidence_unit_id="switch-off",
        evidence_text=source,
    )

    assert result.complete is False
    assert result.audit_issues == []
    assert result.issues[0].code == "ungrounded_source_evidence"


def test_ordered_projection_rejects_ambiguous_distinct_source_rows():
    source = r"""
| Iteration | Sample | Power | Time | VED | UTS | TE |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | A1 | 250 | 2 | 94.69 | 1061 | 18.3 |
| 2 | A1 | 300 | 2 | 94.69 | 1061 | 18.3 |
"""
    evidence = "| A1 | 2 | 94.69 | 1061 | 18.3 |"

    result = gate_task_response(
        _property_response(evidence, owner="A1", value="1061"),
        evidence_unit_id="ambiguous-table",
        evidence_text=source,
    )

    assert result.complete is False
    assert result.accepted == []
    assert result.issues[0].code == "evidence_projection_ambiguous_quarantined"
    assert result.issues[0].actual["projection"]["distinct_match_count"] == 2


def test_ordered_projection_requires_owner_and_structured_value_coordinates():
    source = (
        "| Iteration | Sample | Power | Time | VED | UTS |\n"
        "| --- | --- | --- | --- | --- | --- |\n"
        "| 1 | A1 | 250 | 2 | 94.69 | 1061 |"
    )
    evidence = "| A1 | 2 | 94.69 | 1061 |"

    wrong_owner = gate_task_response(
        _property_response(evidence, owner="B1", value="1061"),
        evidence_unit_id="wrong-owner",
        evidence_text=source,
    )
    wrong_value = gate_task_response(
        _property_response(evidence, owner="A1", value="999"),
        evidence_unit_id="wrong-value",
        evidence_text=source,
    )

    assert wrong_owner.complete is False
    assert wrong_value.complete is False
    assert wrong_owner.issues[0].code == "ungrounded_source_evidence"
    assert wrong_value.issues[0].code == "ungrounded_source_evidence"


def test_ordered_projection_needs_three_cells_and_preserves_cell_order():
    source = "| Sample | Time | UTS |\n| --- | --- | --- |\n| A1 | 2 | 1061 |"

    too_short = unique_ordered_table_row_projection("| A1 | 1061 |", source)
    reversed_cells = unique_ordered_table_row_projection("| A1 | 1061 | 2 |", source)

    assert too_short.status == "too_few_cells"
    assert reversed_cells.status == "not_found"


def test_repeated_identical_source_rows_count_as_one_distinct_projection():
    source = """
| Sample | Time | UTS |
| --- | --- | --- |
| A1 | 2 | 1061 |

| Sample | Time | UTS |
| --- | --- | --- |
| A1 | 2 | 1061 |
"""

    decision = unique_ordered_table_row_projection("| A1 | 2 | 1061 |", source)

    assert decision.status == "matched"
    assert decision.distinct_match_count == 1


def test_ordered_projection_does_not_invent_process_stage_semantics():
    source = r"""
<table><tr><td>Sample</td><td>Power</td><td>Time</td><td>VED</td><td>UTS</td><td>TE</td></tr>
<tr><td>1-1</td><td>250</td><td>2</td><td>94.69</td><td>$ 1061 \pm 27.5 $</td><td>$ 18.3 \pm 1.5 $</td></tr></table>
"""
    evidence = r"| 1-1 | 2 | 94.69 | $ 1061 \pm 27.5 $ | $ 18.3 \pm 1.5 $ |"
    response = MultiAxisResponse.model_validate(
        {
            "anchors": [],
            "facts": [
                {
                    "sample_id_raw": "1-1",
                    "axis": "processing",
                    "fact_type": "process_stage",
                    "data": {
                        "candidate_stage_id": "temporary",
                        "stage_index_candidate": 0,
                        "process_name_raw": "LPBF",
                        "process_code_candidate": None,
                        "process_role_candidate": None,
                        "parameters_raw": [
                            {
                                "parameter_name_raw": "Volumetric Energy Density",
                                "value_raw": "94.69",
                                "unit_raw": "J/mm^3",
                                "source_evidence": evidence,
                                "confidence": 0.95,
                            }
                        ],
                        "source_evidence": [evidence],
                        "confidence": 0.95,
                    },
                    "source_evidence": [evidence],
                    "confidence": 0.95,
                }
            ],
        }
    )

    result = gate_task_response(
        response,
        evidence_unit_id="cropped-process-row",
        evidence_text=source,
    )

    assert result.complete is False
    assert result.accepted == []
    assert result.issues[0].code == "ungrounded_source_evidence"
    assert result.issues[0].actual["projection"]["status"] == "matched"


def test_ordered_projection_uses_same_table_caption_and_headers_for_process_semantics():
    source = r"""
Table 1 | Combinations of LPBF process parameters and post-HT conditions.
<table><tr><td>Sample</td><td>Laser Power</td><td>Heating Time</td><td>Volumetric Energy Density</td><td>UTS</td></tr>
<tr><td>1-1</td><td>250</td><td>2</td><td>94.69</td><td>$ 1061 \pm 27.5 $</td></tr></table>
"""
    evidence = r"| 1-1 | 2 | 94.69 | $ 1061 \pm 27.5 $ |"

    def stage(process: str, parameter: str, value: str, unit: str) -> dict:
        return {
            "sample_id_raw": "1-1",
            "axis": "processing",
            "fact_type": "process_stage",
            "data": {
                "candidate_stage_id": "temporary",
                "stage_index_candidate": 0,
                "process_name_raw": process,
                "process_code_candidate": None,
                "process_role_candidate": None,
                "parameters_raw": [
                    {
                        "parameter_name_raw": parameter,
                        "value_raw": value,
                        "unit_raw": unit,
                        "source_evidence": evidence,
                        "confidence": 0.95,
                    }
                ],
                "source_evidence": [evidence],
                "confidence": 0.95,
            },
            "source_evidence": [evidence],
            "confidence": 0.95,
        }

    response = MultiAxisResponse.model_validate(
        {
            "anchors": [],
            "facts": [
                stage("LPBF", "Volumetric Energy Density", "94.69", "J/mm^3"),
                stage("Post-HT", "Heating Time", "2", "h"),
            ],
        }
    )

    result = gate_task_response(
        response,
        evidence_unit_id="caption-bound-process-row",
        evidence_text=source,
    )

    assert result.complete is True
    assert len(result.accepted) == 2
    assert {
        row.actual["record"]["data"]["process_name_raw"]
        for row in result.audit_issues
    } == {"LPBF", "Post-HT"}


def test_ordered_projection_accepts_literal_process_stage_semantics():
    source = r"""
<table><tr><td>Sample</td><td>Process</td><td>Power</td><td>Time</td><td>VED</td><td>UTS</td></tr>
<tr><td>1-1</td><td>LPBF</td><td>250</td><td>2</td><td>94.69</td><td>$ 1061 \pm 27.5 $</td></tr></table>
"""
    evidence = r"| 1-1 | LPBF | 2 | 94.69 | $ 1061 \pm 27.5 $ |"
    response = MultiAxisResponse.model_validate(
        {
            "anchors": [],
            "facts": [
                {
                    "sample_id_raw": "1-1",
                    "axis": "processing",
                    "fact_type": "process_stage",
                    "data": {
                        "candidate_stage_id": "temporary",
                        "stage_index_candidate": 0,
                        "process_name_raw": "LPBF",
                        "process_code_candidate": None,
                        "process_role_candidate": None,
                        "parameters_raw": [
                            {
                                "parameter_name_raw": "Volumetric Energy Density",
                                "value_raw": "94.69",
                                "unit_raw": "J/mm^3",
                                "source_evidence": evidence,
                                "confidence": 0.95,
                            }
                        ],
                        "source_evidence": [evidence],
                        "confidence": 0.95,
                    },
                    "source_evidence": [evidence],
                    "confidence": 0.95,
                }
            ],
        }
    )

    result = gate_task_response(
        response,
        evidence_unit_id="cropped-process-row-with-semantics",
        evidence_text=source,
    )

    assert result.complete is True
    assert len(result.accepted) == 1
    assert result.audit_issues[0].code == (
        "evidence_unique_ordered_projection_recovered"
    )
