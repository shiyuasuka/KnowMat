from knowmat.evaluation.alpha25_gt import (
    _result_path,
    audit_fact_evidence,
    compare_document,
    digitized_figure_evidence,
)


def _item(sample, evidence, value="900"):
    return {
        "Sample_ID": sample,
        "Role": "Target",
        "Data_Nature": "Experimental",
        "Extracted_Data": {
            "Composition": {"Composition_Observations": []},
            "Processing": {"Process_Route": {"stages": []}},
            "Structure": {"Structure_Observations": [], "Characterization": []},
            "Properties": [
                {
                    "Property_Name": "Yield Strength",
                    "Value": value,
                    "Unit": "MPa",
                    "source_evidence": [evidence],
                }
            ],
        },
    }


def test_gt_evidence_audit_separates_supported_and_unsupported():
    source = "Sample A had a yield strength of 900 MPa."
    assert (
        audit_fact_evidence(
            {"source_evidence": ["yield strength of 900 MPa"]}, source
        )
        == "supported"
    )
    assert (
        audit_fact_evidence(
            {"source_evidence": ["yield strength exceeded one gigapascal"]}, source
        )
        == "unsupported"
    )


def test_gt_evidence_audit_accepts_mathring_ocr_table_condition():
    source = r"""
| Samples | yield strength (MPa) | Elongation (%) |
| --- | --- | --- |
| AF-200  $ \mathring{A} $  $ \mathring{C} $ | 402  $ \pm $ 14 | 11  $ \pm $ 2 |
"""

    assert (
        audit_fact_evidence(
            {"source_evidence": ["AF-200 Å °C | 402 ± 14 | 11 ± 2"]}, source
        )
        == "supported"
    )


def test_evidence_audit_accepts_deterministic_table_projection_as_format_mismatch():
    source = """Table 1. Composition

| Sample | Al | V | Ti | Cr | Fe |
| --- | ---: | ---: | ---: | ---: | ---: |
| A | 6 | 4 | Bal. | 0.1 | 0.2 |
"""

    assert (
        audit_fact_evidence({"source_evidence": ["| A | Bal. | 0.1 |"]}, source)
        == "format_mismatch"
    )


def test_evidence_audit_uses_production_four_column_table_projection():
    source = """<table><tr><td>Location</td><td>Specimen</td><td>Life</td><td>Stress</td><td>Limit</td><td>Size</td></tr>
<tr><td>Surface</td><td>1</td><td>1.68e6</td><td>536.78</td><td>492.32</td><td>442.38</td></tr></table>"""

    assert (
        audit_fact_evidence(
            {
                "source_evidence": [
                    "| 1 | Surface | 1.68e6 | 536.78 | 492.32 |"
                ]
            },
            source,
        )
        == "format_mismatch"
    )


def test_evidence_audit_treats_projected_markdown_delimiter_as_format_mismatch():
    source = """<table><tr><td>Sample</td><td>YS</td><td>UTS</td></tr>
<tr><td>A</td><td>900</td><td>1000</td></tr></table>"""

    assert (
        audit_fact_evidence(
            {"source_evidence": ["| --- | --- | --- | --- | --- |"]},
            source,
        )
        == "format_mismatch"
    )


def test_evidence_audit_marks_joined_grounded_quotes_as_format_mismatch():
    source = "Power was 250 W. Scan speed was 1100 mm/s."

    assert (
        audit_fact_evidence(
            {"source_evidence": ["Power was 250 W | Scan speed was 1100 mm/s"]},
            source,
        )
        == "format_mismatch"
    )


def test_evidence_audit_accepts_html_tex_subscript_equivalence():
    source = "tested at 0.15 V<sub>SCE</sub> for 7200 s"

    assert (
        audit_fact_evidence(
            {"source_evidence": ["tested at 0.15 V_{SCE} for 7200 s"]}, source
        )
        == "format_mismatch"
    )


def test_document_comparison_allows_only_explicit_digitized_chart_evidence():
    source = "Sample A was tested."
    chart = """> [Figure 2 VLM-digitized | line chart]:
series: series_1; kind=trend; n_points=3; key_points=start=(0,1);end=(2,3)

> [Figure 3 AI Description]: invented strength was 999 MPa
"""
    extracted = {
        "items": [
            _item(
                "Sample A",
                "series: series_1; kind=trend; n_points=3; key_points=start=(0,1);end=(2,3)",
            ),
            _item("Sample B", "invented strength was 999 MPa", "999"),
        ]
    }

    derived = digitized_figure_evidence(chart)
    report = compare_document(
        extracted,
        {"items": []},
        source,
        extracted_source_text=source + "\n\n" + derived,
    )

    assert "VLM-digitized" in derived
    assert "AI Description" not in derived
    assert report["extracted_evidence_audit"]["supported"] == 1
    assert report["extracted_evidence_audit"]["unsupported"] == 1


def test_document_comparison_uses_only_source_supported_gt_facts():
    source = "Sample A had a yield strength of 900 MPa."
    extracted = {"items": [_item("Sample A", "yield strength of 900 MPa")]}
    gt = {
        "items": [
            {
                **_item("A", "yield strength of 900 MPa"),
                "Extracted_Data": {
                    **_item("A", "yield strength of 900 MPa")["Extracted_Data"],
                    "Properties": [
                        _item("A", "yield strength of 900 MPa")["Extracted_Data"]["Properties"][0],
                        _item("A", "invented unsupported quote", "1200")["Extracted_Data"]["Properties"][0],
                    ],
                },
            }
        ]
    }

    report = compare_document(extracted, gt, source)

    assert report["gt_evidence_audit"]["supported"] == 1
    assert report["gt_evidence_audit"]["unsupported"] == 1
    assert report["axes"]["properties"]["supported_gt"] == 1
    assert report["axes"]["properties"]["matched"] == 1
    assert report["core_tensile"]["matched"] == 1


def test_unique_fact_metrics_do_not_penalize_cross_item_gt_copies():
    source = "Samples A and B had a yield strength of 900 MPa."
    extracted = {"items": [_item("Sample A", "yield strength of 900 MPa")]}
    gt = {
        "items": [
            _item("Sample A", "yield strength of 900 MPa"),
            _item("Sample B", "yield strength of 900 MPa"),
        ]
    }

    report = compare_document(extracted, gt, source)

    assert report["axes"]["properties"]["supported_gt"] == 2
    assert report["axes"]["properties"]["recall"] == 0.5
    assert report["unique_axes"]["properties"]["supported_gt"] == 1
    assert report["unique_axes"]["properties"]["matched"] == 1
    assert report["unique_axes"]["properties"]["recall"] == 1.0


def test_document_comparison_does_not_call_unsupported_extraction_an_extra():
    source = "Sample A had a yield strength of 900 MPa."
    extracted = {"items": [_item("Sample A", "invented unsupported quote")]}
    gt = {"items": [_item("A", "yield strength of 900 MPa")]}

    report = compare_document(extracted, gt, source)

    assert report["extracted_evidence_audit"]["unsupported"] == 1
    assert len(report["disagreements"]["unsupported_extracted_facts"]) == 1
    assert report["disagreements"]["source_supported_extras"] == []
    assert report["axes"]["properties"]["supported_extracted"] == 0
    assert report["axes"]["properties"]["matched"] == 0


def test_result_path_finds_production_sanitized_directory(tmp_path):
    paper_key = "A paper: with spaces"
    safe_key = "A_paper_with_spaces"
    output = tmp_path / safe_key / f"{safe_key}_extraction.json"
    output.parent.mkdir()
    output.write_text("{}", encoding="utf-8")

    assert _result_path(tmp_path, paper_key) == output
