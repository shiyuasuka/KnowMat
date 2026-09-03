from pathlib import Path

import pytest

from knowmat.pdf.vector_chart_digitizer import (
    _fit_axis,
    _parse_number,
    digitize_vector_pdf,
)
from knowmat.pdf.chart_digitizer import digitize_line_chart_multi
from knowmat.pdf.chart_digitizer import (
    digitize_line_chart_region,
    format_digitized_block,
    merge_line_semantics,
    validate_axis_calibration,
)


ROOT = Path(__file__).resolve().parents[1]
MANUAL = ROOT / "曲线图带人工标注"


def test_parse_exponent_tick_tokens():
    assert _parse_number("10") == 10.0
    assert _parse_number("−1.5") == -1.5
    assert _parse_number("1,200") == 1200.0
    assert _parse_number("10^3") is None


def test_fit_axis_selects_log_scale_for_decades():
    model = _fit_axis([(0.0, 1.0), (10.0, 10.0), (20.0, 100.0)], "x")
    assert model is not None
    assert model.scale == "log10"
    assert abs(model.map(15.0) - 31.6227766) < 1e-5


@pytest.mark.parametrize(
    ("figure", "trend_count"),
    [
        ("Figure_3.2.1.1", 4),
        ("Figure_3.3.1.5", 4),
        ("Figure_3.3.1.6", 4),
        ("Figure_3.3.7.1.2", 4),
        ("Figure_3.5.1.2", 4),
    ],
)
def test_vector_pdf_extracts_short_and_bezier_trends(figure: str, trend_count: int):
    pdf = MANUAL / figure / f"{figure}.pdf"
    if not pdf.is_file():
        pytest.skip(f"benchmark fixture missing: {pdf}")
    result = digitize_vector_pdf(pdf)
    assert result is not None
    assert result["method"] == "pdf_vector"
    trends = [s for s in result["series"] if str(s.get("kind", "")).startswith("trend")]
    assert len(trends) == trend_count
    assert all(s["n_points"] >= 2 for s in trends)


def test_raster_only_chart_uses_code_fallback_without_vlm():
    pdf = MANUAL / "Figure_3.3.1.1" / "Figure_3.3.1.1.pdf"
    if not pdf.is_file():
        pytest.skip(f"benchmark fixture missing: {pdf}")
    result = digitize_vector_pdf(pdf)
    assert result is not None
    assert result["method"] == "raster_code"
    assert result["n_series"] == 8
    assert all(s["method"] == "raster_code" for s in result["series"])


def test_vector_pdf_extracts_error_bar_endpoints_separately():
    """Dual-axis error bars stay on the marker panel's calibration model."""

    pdf = MANUAL / "Figure_3.2.1.11" / "Figure_3.2.1.11.pdf"
    if not pdf.is_file():
        pytest.skip(f"benchmark fixture missing: {pdf}")
    result = digitize_vector_pdf(pdf)
    assert result is not None
    spreads = [s for s in result["series"] if s.get("kind") == "spread"]
    assert len(spreads) == 8  # four marker groups × upper/lower
    assert {str(s["label"]).rsplit(" ", 1)[-1] for s in spreads} == {"upper", "lower"}
    assert all(s["n_points"] >= 4 for s in spreads)


@pytest.mark.parametrize(
    ("figure", "boundary_count"),
    [("Figure_3.2.1.6", 4), ("Figure_3.3.1.3", 12)],
)
def test_vector_pdf_keeps_filled_region_boundaries(figure: str, boundary_count: int):
    pdf = MANUAL / figure / f"{figure}.pdf"
    if not pdf.is_file():
        pytest.skip(f"benchmark fixture missing: {pdf}")
    result = digitize_vector_pdf(pdf)
    assert result is not None
    boundaries = [s for s in result["series"] if s.get("kind") == "boundary"]
    assert len(boundaries) == boundary_count
    assert all(s["n_points"] >= 3 for s in boundaries)
    if figure == "Figure_3.2.1.6":
        assert [s["label"] for s in boundaries] == ["Fty", "Ftu", "RA", "e"]


def test_public_line_entrypoint_works_without_vlm_key(monkeypatch):
    pdf = MANUAL / "Figure_3.5.1.2" / "Figure_3.5.1.2.pdf"
    if not pdf.is_file():
        pytest.skip(f"benchmark fixture missing: {pdf}")
    for name in ("VLM_API_KEY", "LLM_API_KEY", "OPENAI_API_KEY"):
        monkeypatch.delenv(name, raising=False)
    result = digitize_line_chart_multi(pdf)
    assert result is not None
    assert result["method"] == "pdf_vector"
    assert result["n_series"] >= 2
    assert all(s["method"] == "pdf_vector" for s in result["series"])


def test_raster_entrypoint_reuses_classification_axis_calibration(
    tmp_path: Path, monkeypatch
):
    cv2 = pytest.importorskip("cv2")
    np = pytest.importorskip("numpy")
    image = np.full((300, 420, 3), 255, dtype=np.uint8)
    cv2.rectangle(image, (40, 20), (390, 270), (0, 0, 0), 2)
    cv2.line(image, (50, 240), (380, 60), (0, 0, 230), 4)
    cv2.line(image, (50, 70), (380, 220), (230, 0, 0), 4)
    chart = tmp_path / "two-series.png"
    assert cv2.imwrite(str(chart), image)

    def unexpected_axis_call(*_args, **_kwargs):
        raise AssertionError("combined classification/calibration should avoid a second VLM call")

    monkeypatch.setattr(
        "knowmat.pdf.chart_digitizer._read_axis_calibration", unexpected_axis_call
    )
    result = digitize_line_chart_multi(
        chart,
        max_series=4,
        axis_calibration={
            "x_axis": "Temperature (C)",
            "y_axis": "Strength (MPa)",
            "x_ref": [
                {"value": 0, "pixel_x": 40},
                {"value": 1000, "pixel_x": 390},
            ],
            "y_ref": [
                {"value": 0, "pixel_y": 270},
                {"value": 500, "pixel_y": 20},
            ],
        },
    )

    assert result is not None
    assert result["n_series"] == 2
    assert result["x_axis"] == "Temperature (C)"
    assert result["y_axis"] == "Strength (MPa)"
    assert all(series["n_points"] >= 2 for series in result["series"])
    assert result["method"] == "raster_code"
    assert result["coordinate_source"] == "pure_code"
    assert result["value_source"] == "image_digitized"
    block = format_digitized_block(result, "raster", csv_dir=str(tmp_path))
    assert "estimated from pixels" in block
    assert "value_source: image_digitized" in block


@pytest.mark.parametrize(
    "calibration",
    [
        {
            "x_ref": [{"value": 0, "pixel_x": 10}],
            "y_ref": [
                {"value": 0, "pixel_y": 100},
                {"value": 1, "pixel_y": 10},
            ],
        },
        {
            "x_ref": [
                {"value": 0, "pixel_x": 10},
                {"value": 1, "pixel_x": 10},
            ],
            "y_ref": [
                {"value": 0, "pixel_y": 100},
                {"value": 1, "pixel_y": 10},
            ],
        },
        {
            "x_ref": [
                {"value": 0, "pixel_x": 10},
                {"value": 2, "pixel_x": 20},
                {"value": 1, "pixel_x": 30},
            ],
            "y_ref": [
                {"value": 0, "pixel_y": 100},
                {"value": 1, "pixel_y": 10},
            ],
        },
        {
            "x_ref": [
                {"value": 0, "pixel_x": 10},
                {"value": float("inf"), "pixel_x": 20},
            ],
            "y_ref": [
                {"value": 0, "pixel_y": 100},
                {"value": 1, "pixel_y": 10},
            ],
        },
    ],
)
def test_axis_calibration_rejects_unsafe_mappings(calibration):
    assert validate_axis_calibration(calibration) is None


def test_pdf_region_entrypoint_preserves_vector_content_without_vlm(monkeypatch, tmp_path):
    pdf = MANUAL / "Figure_3.5.1.2" / "Figure_3.5.1.2.pdf"
    if not pdf.is_file():
        pytest.skip(f"benchmark fixture missing: {pdf}")
    for name in ("VLM_API_KEY", "LLM_API_KEY", "OPENAI_API_KEY"):
        monkeypatch.delenv(name, raising=False)

    import fitz

    # Put the standalone fixture inside a larger synthetic paper page so the
    # production clip -> temporary vector PDF path is exercised (not the
    # standalone full-page shortcut).
    wrapped_pdf = tmp_path / "paper-with-chart-region.pdf"
    with fitz.open(pdf) as source_doc, fitz.open() as wrapped_doc:
        rect = source_doc[0].rect
        page = wrapped_doc.new_page(width=rect.width + 100, height=rect.height + 100)
        target = fitz.Rect(50, 50, 50 + rect.width, 50 + rect.height)
        page.show_pdf_page(target, source_doc, 0)
        wrapped_doc.save(wrapped_pdf)
    result = digitize_line_chart_region(
        wrapped_pdf,
        1,
        [50.0, 50.0, float(50 + rect.width), float(50 + rect.height)],
    )

    assert result is not None
    assert result["method"] == "pdf_vector"
    assert result["n_series"] >= 2
    assert all(s["method"] == "pdf_vector" for s in result["series"])


def test_pdf_region_entrypoint_keeps_standalone_raster_code_fallback(monkeypatch):
    pdf = MANUAL / "Figure_3.3.1.1" / "Figure_3.3.1.1.pdf"
    if not pdf.is_file():
        pytest.skip(f"benchmark fixture missing: {pdf}")
    for name in ("VLM_API_KEY", "LLM_API_KEY", "OPENAI_API_KEY"):
        monkeypatch.delenv(name, raising=False)

    import fitz

    with fitz.open(pdf) as doc:
        rect = doc[0].rect
    result = digitize_line_chart_region(
        pdf,
        1,
        [float(rect.x0), float(rect.y0), float(rect.x1), float(rect.y1)],
    )

    assert result is not None
    assert result["method"] == "raster_code"
    assert result["n_series"] == 8


def test_pdf_region_entrypoint_rejects_invalid_page_and_bbox():
    pdf = MANUAL / "Figure_3.5.1.2" / "Figure_3.5.1.2.pdf"
    if not pdf.is_file():
        pytest.skip(f"benchmark fixture missing: {pdf}")
    assert digitize_line_chart_region(pdf, 999, [0, 0, 100, 100]) is None
    assert digitize_line_chart_region(pdf, 1, [100, 100, 10, 10]) is None
    assert digitize_line_chart_region(pdf, 1, None) is None


def test_optional_vlm_semantics_cannot_change_code_coordinates():
    code = {
        "type": "line_multi",
        "method": "pdf_vector",
        "x_axis": "Temperature (C)",
        "y_axis": "Strength (MPa)",
        "n_series": 2,
        "series": [
            {
                "label": "series_1",
                "kind": "trend",
                "csv": "Temperature_C,Strength_MPa\n20,100\n800,390",
                "n_points": 2,
                "method": "pdf_vector",
            },
            {
                "label": "series_2",
                "kind": "trend",
                "csv": "Temperature_C,Strength_MPa\n20,120\n800,410",
                "n_points": 2,
                "method": "pdf_vector",
            },
        ],
    }
    malicious_vlm = {
        "type": "line",
        "confidence": 0.7,
        "csv": "x,y\n0,999999",
        "line_summary": {
            "x_axis": "wrong X",
            "y_axis": "wrong Y",
            "series": [
                {"label": "alloy A", "start": [0, 999], "end": [1, 999]},
                {"label": "alloy B", "start": [0, -999], "end": [1, -999]},
            ],
        },
    }
    before = [
        (s["csv"], s["n_points"], s["kind"], s["method"])
        for s in code["series"]
    ]

    merged = merge_line_semantics(code, malicious_vlm)

    after = [
        (s["csv"], s["n_points"], s["kind"], s["method"])
        for s in merged["series"]
    ]
    assert after == before
    assert [s["label"] for s in merged["series"]] == ["alloy A", "alloy B"]
    assert merged["x_axis"] == "Temperature (C)"
    assert merged["y_axis"] == "Strength (MPa)"
    assert merged["semantic_axes"] == {"x_axis": "wrong X", "y_axis": "wrong Y"}
    assert merged["coordinate_source"] == "pure_code"


def _dense_line_result(series_count: int = 4, points_per_series: int = 80):
    series = []
    for series_index in range(series_count):
        rows = ["Temperature_C,Strength_MPa"]
        rows.extend(
            f"{point},{1000 + series_index * 100 + point}"
            for point in range(points_per_series)
        )
        series.append(
            {
                "label": f"alloy_{series_index + 1}",
                "kind": "trend",
                "csv": "\n".join(rows),
                "n_points": points_per_series,
                "method": "pdf_vector",
            }
        )
    return {
        "type": "line_multi",
        "method": "pdf_vector",
        "x_axis": "Temperature (C)",
        "y_axis": "Strength (MPa)",
        "coordinate_source": "pure_code",
        "n_series": series_count,
        "series": series,
    }


def test_line_context_keeps_complete_sidecar_but_bounds_markdown(tmp_path: Path):
    result = _dense_line_result(series_count=4, points_per_series=80)

    block = format_digitized_block(
        result,
        figure_num="7",
        csv_dir=str(tmp_path),
        context_max_chars=700,
        context_max_series=2,
    )

    assert len(block) <= 700
    assert "context_detail: bounded_key_points" in block
    assert "data_csv: figure_7_digitized.csv" in block
    assert "full_data_externalized: true" in block
    assert "context_omitted_series:" in block
    assert "key_points=" in block
    sidecar = tmp_path / "figure_7_digitized.csv"
    assert sidecar.is_file()
    assert len(sidecar.read_text(encoding="utf-8").splitlines()) == 1 + 4 * 80
    assert len(sidecar.read_text(encoding="utf-8")) > len(block) * 5


def test_line_context_never_inlines_dense_csv_when_sidecar_write_fails(
    monkeypatch,
):
    result = _dense_line_result(series_count=5, points_per_series=100)
    monkeypatch.setattr(
        "knowmat.pdf.chart_digitizer._write_csv_file", lambda *_args, **_kwargs: None
    )

    block = format_digitized_block(
        result,
        figure_num="8",
        csv_dir="/unwritable",
        context_max_chars=640,
        context_max_series=3,
    )

    assert len(block) <= 640
    assert "data_csv: unavailable" in block
    assert "full_data_externalized: false" in block
    assert "context_omitted_series:" in block
    assert block.count("\n") < 20
    assert "99,1499" not in block


def test_negative_tensile_series_is_quarantined_after_full_csv_is_preserved(
    tmp_path: Path,
):
    result = {
        "type": "line_multi",
        "method": "pdf_vector",
        "x_axis": "Temperature (K)",
        "y_axis": "Tensile strength (MPa)",
        "coordinate_source": "pure_code",
        "series": [
            {
                "label": "valid",
                "kind": "trend",
                "csv": "Temperature_K,Strength_MPa\n300,520\n1000,310",
                "n_points": 2,
            },
            {
                "label": "invalid",
                "kind": "trend",
                "csv": "Temperature_K,Strength_MPa\n300,-50\n1000,295",
                "n_points": 2,
            },
        ],
    }

    block = format_digitized_block(result, "10", csv_dir=str(tmp_path))

    assert "series: valid" in block
    assert "series: invalid" not in block
    assert "quality_quarantine:" in block
    assert '"series":["invalid"]' in block
    sidecar = tmp_path / "figure_10_digitized.csv"
    csv_text = sidecar.read_text(encoding="utf-8")
    assert "invalid,trend,300,-50" in csv_text


def test_vlm_only_line_points_are_never_formatted_as_extraction_context(tmp_path: Path):
    result = {
        "type": "line",
        "confidence": 1.0,
        "line_summary": {
            "x_axis": "Temperature (C)",
            "y_axis": "Strength (MPa)",
            "series": [
                {
                    "label": f"series_{index}",
                    "start": [0, index],
                    "end": [1000, index + 1],
                    "extrema": [],
                }
                for index in range(100)
            ],
        },
    }

    assert format_digitized_block(result, "9", csv_dir=str(tmp_path)) == ""
    assert not list(tmp_path.glob("*.csv"))
