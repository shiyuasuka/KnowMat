from pathlib import Path
from types import SimpleNamespace
import sys

from knowmat.app_config import settings
from knowmat.nodes.extraction import extract_data
from knowmat.nodes.paddleocrvl_parse_pdf import _persist_figure_images
from knowmat.pdf.figure_describer import inject_figure_descriptions
from knowmat.pdf.figure_describer import (
    _call_vlm_with_negative_cache,
    _existing_chart_context_chars,
    _vlm_call_with_pool,
)


def test_persist_figure_images_merges_split_items_and_saves_crop(tmp_path: Path, monkeypatch):
    captured: dict = {}

    def fake_crop(pdf_path, page_idx, bbox, dpi, out_path):
        captured["pdf_path"] = pdf_path
        captured["page_idx"] = page_idx
        captured["bbox"] = bbox
        captured["dpi"] = dpi
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_bytes(b"fake-figure")
        return out_path

    monkeypatch.setattr(
        "knowmat.nodes.paddleocrvl_parse_pdf._crop_page_image",
        fake_crop,
    )

    items = [
        {
            "typer": "image",
            "page": 7,
            "data": {"image_path": "imgs/img_in_image_box_300_600_900_1200.jpg"},
        },
        {
            "typer": "image",
            "page": 7,
            "data": {"caption": "Figure 1. SEM image of precipitates."},
        },
        {
            "typer": "image",
            "page": 7,
            "data": {"caption": "Table 1. Not a figure caption."},
        },
    ]

    out = _persist_figure_images(
        items,
        "paper.pdf",
        tmp_path / "_ocr_cache" / "sig" / "figures",
        render_dpi=300,
    )

    first = out[0]["data"]
    assert first["figure_num"] == "1"
    assert first["caption"] == "SEM image of precipitates."
    assert Path(first["image_path"]).is_file()
    assert Path(first["image_path"]).name == "page0007-figure1.jpg"
    assert captured["bbox"] == [72.0, 144.0, 216.0, 288.0]


def test_inject_figure_descriptions_links_split_items(tmp_path: Path, monkeypatch):
    figure_path = tmp_path / "page0007-figure1.jpg"
    figure_path.write_bytes(b"fake-image")

    monkeypatch.setattr(
        "knowmat.pdf.figure_describer.describe_figure_image",
        lambda image_path, caption="": "<think>internal chain</think>Synthetic description.",
    )

    text = "Figure 1. SEM image of precipitates."
    items = [
        {
            "typer": "image",
            "page": 7,
            "data": {"image_path": str(figure_path)},
        },
        {
            "typer": "image",
            "page": 7,
            "data": {"caption": "Figure 1. SEM image of precipitates."},
        },
    ]

    enriched = inject_figure_descriptions(text, items)
    assert enriched.startswith("> [Figure 1 AI Description]: Synthetic description.")
    assert enriched.count("Figure 1 AI Description") == 1
    assert "<think>" not in enriched

    enriched_again = inject_figure_descriptions(enriched, items)
    assert enriched_again.count("Figure 1 AI Description") == 1


def test_inject_chart_uses_pdf_code_result_without_vlm_key(tmp_path: Path, monkeypatch):
    image_path = tmp_path / "img_in_chart_box_0_0_200_200.jpg"
    image_path.write_bytes(b"fake-chart")
    source_pdf = tmp_path / "paper.pdf"
    source_pdf.write_bytes(b"fake-pdf")
    code_result = {
        "type": "line_multi",
        "method": "pdf_vector",
        "x_axis": "Temperature (C)",
        "y_axis": "Strength (MPa)",
        "n_series": 1,
        "series": [
            {
                "label": "series_1",
                "kind": "trend",
                "csv": "Temperature_C,Strength_MPa\n20,100\n800,390",
                "n_points": 2,
                "method": "pdf_vector",
            }
        ],
    }
    captured = {}

    def fake_region(pdf, page, bbox, **kwargs):
        captured.update(pdf=pdf, page=page, bbox=bbox, kwargs=kwargs)
        return code_result

    monkeypatch.setattr(
        "knowmat.pdf.chart_digitizer.digitize_line_chart_region", fake_region
    )
    monkeypatch.setattr(
        "knowmat.pdf.chart_digitizer.digitize_chart_image",
        lambda *_args, **_kwargs: None,
    )
    monkeypatch.setattr(
        "knowmat.pdf.figure_describer.describe_figure_image",
        lambda *_args, **_kwargs: "should not be used",
    )
    text = "Figure 2. Strength versus temperature."
    items = [
        {
            "typer": "image",
            "page": 3,
            "bbox": [10.0, 20.0, 210.0, 220.0],
            "data": {
                "image_path": str(image_path),
                "figure_num": "2",
                "caption": "Strength versus temperature.",
            },
        }
    ]

    enriched = inject_figure_descriptions(text, items, source_pdf=str(source_pdf))

    assert "pure-code PDF vector extraction" in enriched
    assert "coordinate_source: pure_code" in enriched
    assert "20,100" in enriched and "800,390" in enriched
    assert captured["page"] == 3
    assert captured["bbox"] == [10.0, 20.0, 210.0, 220.0]


def test_multiple_charts_share_one_hard_paper_context_budget(
    tmp_path: Path, monkeypatch
):
    source_pdf = tmp_path / "paper.pdf"
    source_pdf.write_bytes(b"fake-pdf")
    items = []
    captions = []
    for figure_num in range(1, 6):
        image_path = tmp_path / f"img_in_chart_box_{figure_num}_0_200_200.jpg"
        image_path.write_bytes(b"fake-chart")
        caption = f"Figure {figure_num}. Strength curve {figure_num}."
        captions.append(caption)
        items.append(
            {
                "typer": "image",
                "page": figure_num,
                "bbox": [0.0, 0.0, 200.0, 200.0],
                "data": {
                    "image_path": str(image_path),
                    "figure_num": str(figure_num),
                    "caption": f"Strength curve {figure_num}.",
                },
            }
        )

    rows = ["Temperature_C,Strength_MPa"]
    rows.extend(f"{point},{1000 + point}" for point in range(100))
    code_result = {
        "type": "line_multi",
        "method": "pdf_vector",
        "x_axis": "Temperature (C)",
        "y_axis": "Strength (MPa)",
        "coordinate_source": "pure_code",
        "n_series": 4,
        "series": [
            {
                "label": f"alloy_{index}",
                "kind": "trend",
                "csv": "\n".join(rows),
                "n_points": 100,
                "method": "pdf_vector",
            }
            for index in range(4)
        ],
    }

    class _NoopAligner:
        def __init__(self, **_kwargs):
            pass

        def align(self, *_args, **_kwargs):
            return []

    monkeypatch.setitem(
        sys.modules,
        "knowmat.image_text_alignment.aligner",
        SimpleNamespace(ImageTextAligner=_NoopAligner),
    )
    monkeypatch.setattr(
        "knowmat.pdf.chart_digitizer.digitize_line_chart_region",
        lambda *_args, **_kwargs: code_result,
    )
    monkeypatch.setattr(
        "knowmat.pdf.chart_digitizer.digitize_chart_image",
        lambda *_args, **_kwargs: None,
    )
    monkeypatch.setattr(settings, "chart_context_max_chars_per_figure", 600)
    monkeypatch.setattr(settings, "chart_context_max_chars_per_paper", 900)
    monkeypatch.setattr(settings, "chart_context_max_series", 3)

    enriched = inject_figure_descriptions(
        "\n\n".join(captions),
        items,
        source_pdf=str(source_pdf),
        csv_dir=str(tmp_path),
    )

    assert _existing_chart_context_chars(enriched) <= 900
    assert 1 <= enriched.count("VLM-digitized") < 5
    assert "context_truncated: paper_chart_context_budget" in enriched
    assert len(list(tmp_path.glob("figure_*_digitized.csv"))) == 5


def test_raster_line_fallback_is_classification_gated_and_reuses_calibration(
    tmp_path: Path, monkeypatch
):
    image_path = tmp_path / "img_in_chart_box_0_0_200_200.jpg"
    image_path.write_bytes(b"fake-chart")
    source_pdf = tmp_path / "paper.pdf"
    source_pdf.write_bytes(b"fake-pdf")
    captured = {}
    code_result = {
        "type": "line_multi",
        "method": "code",
        "x_axis": "Temperature (C)",
        "y_axis": "Strength (MPa)",
        "n_series": 2,
        "series": [
            {
                "label": "series_1",
                "kind": "trend",
                "csv": "Temperature_C,Strength_MPa\n20,100\n800,390",
                "n_points": 2,
                "method": "code",
            },
            {
                "label": "series_2",
                "kind": "trend",
                "csv": "Temperature_C,Strength_MPa\n20,120\n800,410",
                "n_points": 2,
                "method": "code",
            },
        ],
    }
    semantic = {
        "type": "line",
        "confidence": 0.9,
        "reason": "two readable line series",
        "axis_calibration": {
            "x_ref": [
                {"value": 0, "pixel_x": 10},
                {"value": 1000, "pixel_x": 190},
            ],
            "y_ref": [
                {"value": 0, "pixel_y": 190},
                {"value": 500, "pixel_y": 10},
            ],
        },
        "line_summary": {
            "x_axis": "Temperature (C)",
            "y_axis": "Strength (MPa)",
            "series": [{"label": "A"}, {"label": "B"}],
        },
    }

    class _NoopAligner:
        def __init__(self, **_kwargs):
            pass

        def align(self, *_args, **_kwargs):
            return []

    monkeypatch.setitem(
        sys.modules,
        "knowmat.image_text_alignment.aligner",
        SimpleNamespace(ImageTextAligner=_NoopAligner),
    )
    monkeypatch.setattr(
        "knowmat.pdf.chart_digitizer.digitize_line_chart_region",
        lambda *_args, **_kwargs: None,
    )
    monkeypatch.setattr(
        "knowmat.pdf.chart_digitizer.digitize_chart_image",
        lambda *_args, **_kwargs: semantic,
    )

    def fake_raster(image, **kwargs):
        captured["image"] = image
        captured.update(kwargs)
        return code_result

    monkeypatch.setattr(
        "knowmat.pdf.chart_digitizer.digitize_line_chart_multi", fake_raster
    )
    text = "Figure 5. Strength versus temperature."
    items = [
        {
            "typer": "image",
            "page": 1,
            "data": {
                "image_path": str(image_path),
                "figure_num": "5",
                "caption": "Strength versus temperature.",
            },
        }
    ]

    enriched = inject_figure_descriptions(
        text,
        items,
        source_pdf=str(source_pdf),
        csv_dir=str(tmp_path),
    )

    assert captured["image"] == image_path
    assert captured["axis_calibration"]["x_axis"] == "Temperature (C)"
    assert captured["axis_calibration"]["y_axis"] == "Strength (MPa)"
    assert captured["allow_axis_calibration_vlm"] is False
    assert "series: A" in enriched and "series: B" in enriched
    assert "data_csv: figure_5_digitized.csv" in enriched


def test_raster_line_fallback_rejects_low_confidence_classification(
    tmp_path: Path, monkeypatch
):
    image_path = tmp_path / "img_in_chart_box_0_0_200_200.jpg"
    image_path.write_bytes(b"fake-chart")
    source_pdf = tmp_path / "paper.pdf"
    source_pdf.write_bytes(b"fake-pdf")
    raster_calls = 0

    class _NoopAligner:
        def __init__(self, **_kwargs):
            pass

        def align(self, *_args, **_kwargs):
            return []

    monkeypatch.setitem(
        sys.modules,
        "knowmat.image_text_alignment.aligner",
        SimpleNamespace(ImageTextAligner=_NoopAligner),
    )
    monkeypatch.setattr(
        "knowmat.pdf.chart_digitizer.digitize_line_chart_region",
        lambda *_args, **_kwargs: None,
    )
    monkeypatch.setattr(
        "knowmat.pdf.chart_digitizer.digitize_chart_image",
        lambda *_args, **_kwargs: {
            "type": "line",
            "confidence": 0.69,
            "axis_calibration": {
                "x_ref": [
                    {"value": 0, "pixel_x": 10},
                    {"value": 1, "pixel_x": 190},
                ],
                "y_ref": [
                    {"value": 0, "pixel_y": 190},
                    {"value": 1, "pixel_y": 10},
                ],
            },
            "line_summary": {"series": [{"label": "A"}]},
        },
    )

    def unexpected_raster(*_args, **_kwargs):
        nonlocal raster_calls
        raster_calls += 1
        return None

    monkeypatch.setattr(
        "knowmat.pdf.chart_digitizer.digitize_line_chart_multi",
        unexpected_raster,
    )
    monkeypatch.setattr(
        "knowmat.pdf.figure_describer.describe_figure_image",
        lambda *_args, **_kwargs: "Fallback prose.",
    )

    enriched = inject_figure_descriptions(
        "Figure 6. Strength versus temperature.",
        [
            {
                "typer": "image",
                "page": 1,
                "data": {
                    "image_path": str(image_path),
                    "figure_num": "6",
                    "caption": "Strength versus temperature.",
                },
            }
        ],
        source_pdf=str(source_pdf),
    )

    assert raster_calls == 0
    assert "Figure 6 AI Description" in enriched
    assert "VLM-digitized" not in enriched


def test_raster_line_fallback_rejects_one_calibration_for_multiple_panels(
    tmp_path: Path, monkeypatch
):
    image_path = tmp_path / "img_in_chart_box_0_0_200_200.jpg"
    image_path.write_bytes(b"fake-multi-panel-chart")
    source_pdf = tmp_path / "paper.pdf"
    source_pdf.write_bytes(b"fake-pdf")
    raster_calls = 0

    monkeypatch.setattr(
        "knowmat.pdf.chart_digitizer.digitize_line_chart_region",
        lambda *_args, **_kwargs: None,
    )
    monkeypatch.setattr(
        "knowmat.pdf.chart_digitizer.digitize_chart_image",
        lambda *_args, **_kwargs: {
            "type": "line",
            "confidence": 0.95,
            "axis_calibration": {
                "x_ref": [
                    {"value": 0, "pixel_x": 10},
                    {"value": 1000, "pixel_x": 190},
                ],
                "y_ref": [
                    {"value": 0, "pixel_y": 190},
                    {"value": 500, "pixel_y": 10},
                ],
            },
            "line_summary": {
                "x_axis": "Laser power (top-left panel; other panels: scan speed)",
                "y_axis": "UTS (top row) / elongation (bottom row)",
                "series": [{"label": "A"}],
            },
        },
    )

    def unexpected_raster(*_args, **_kwargs):
        nonlocal raster_calls
        raster_calls += 1
        return None

    monkeypatch.setattr(
        "knowmat.pdf.chart_digitizer.digitize_line_chart_multi",
        unexpected_raster,
    )

    original = "Figure 2. Multi-panel process-property maps."
    enriched = inject_figure_descriptions(
        original,
        [
            {
                "typer": "image",
                "page": 1,
                "data": {
                    "image_path": str(image_path),
                    "figure_num": "2",
                    "caption": "Multi-panel process-property maps.",
                },
            }
        ],
        source_pdf=str(source_pdf),
        include_prose_fallback=False,
    )

    assert raster_calls == 0
    assert enriched == original
    assert "VLM-digitized" not in enriched


def test_generic_pdf_figure_does_not_call_chart_vlm_when_code_fails(tmp_path: Path, monkeypatch):
    image_path = tmp_path / "page0001-figure4.jpg"
    image_path.write_bytes(b"fake-micrograph")
    source_pdf = tmp_path / "paper.pdf"
    source_pdf.write_bytes(b"fake-pdf")
    chart_vlm_calls = 0

    monkeypatch.setattr(
        "knowmat.pdf.chart_digitizer.digitize_line_chart_region",
        lambda *_args, **_kwargs: None,
    )

    def chart_vlm(*_args, **_kwargs):
        nonlocal chart_vlm_calls
        chart_vlm_calls += 1
        return None

    monkeypatch.setattr("knowmat.pdf.chart_digitizer.digitize_chart_image", chart_vlm)
    monkeypatch.setattr(
        "knowmat.pdf.figure_describer.describe_figure_image",
        lambda *_args, **_kwargs: "Microstructure description.",
    )
    text = "Figure 4. SEM microstructure."
    items = [
        {
            "typer": "image",
            "page": 1,
            "bbox": [10.0, 20.0, 210.0, 220.0],
            "data": {
                "image_path": str(image_path),
                "figure_num": "4",
                "caption": "SEM microstructure.",
            },
        }
    ]

    enriched = inject_figure_descriptions(text, items, source_pdf=str(source_pdf))

    assert "Figure 4 AI Description" in enriched
    assert chart_vlm_calls == 0


def test_chart_only_enrichment_does_not_fall_back_to_generic_figure_prose(
    tmp_path: Path, monkeypatch
):
    image_path = tmp_path / "page0001-figure4.jpg"
    image_path.write_bytes(b"fake-micrograph")
    source_pdf = tmp_path / "paper.pdf"
    source_pdf.write_bytes(b"fake-pdf")

    monkeypatch.setattr(
        "knowmat.pdf.chart_digitizer.digitize_line_chart_region",
        lambda *_args, **_kwargs: None,
    )

    def unexpected_prose(*_args, **_kwargs):
        raise AssertionError("chart-only enrichment must not call prose VLM")

    monkeypatch.setattr(
        "knowmat.pdf.figure_describer.describe_figure_image", unexpected_prose
    )

    original = "Figure 4. SEM microstructure."
    enriched = inject_figure_descriptions(
        original,
        [
            {
                "typer": "image",
                "page": 1,
                "bbox": [10.0, 20.0, 210.0, 220.0],
                "data": {
                    "image_path": str(image_path),
                    "figure_num": "4",
                    "caption": "SEM microstructure.",
                },
            }
        ],
        source_pdf=str(source_pdf),
        include_prose_fallback=False,
    )

    assert enriched == original
    assert "AI Description" not in enriched


def test_vlm_empty_content_stops_after_two_total_attempts(monkeypatch, tmp_path):
    calls = 0

    class FakeCompletions:
        def create(self, **_kwargs):
            nonlocal calls
            calls += 1
            return SimpleNamespace(
                choices=[SimpleNamespace(message=SimpleNamespace(content=""))]
            )

    class FakeOpenAI:
        def __init__(self, **_kwargs):
            self.chat = SimpleNamespace(completions=FakeCompletions())

    class FakePool:
        def all_keys(self):
            return ["key-1"]

    monkeypatch.setitem(sys.modules, "openai", SimpleNamespace(OpenAI=FakeOpenAI))
    monkeypatch.setattr("knowmat.pdf.figure_describer._get_vlm_pool", lambda: FakePool())

    content = _vlm_call_with_pool(
        "https://example.test/v1",
        {"model": "test-vlm", "messages": []},
        tmp_path / "figure.jpg",
    )

    assert content == ""
    assert calls == 2


def test_vlm_negative_cache_skips_identical_request(monkeypatch, tmp_path):
    image_path = tmp_path / "figure.jpg"
    image_path.write_bytes(b"same-image")
    cache_dir = tmp_path / "cache"
    monkeypatch.setenv("KNOWMAT2_VLM_NEGATIVE_CACHE_DIR", str(cache_dir))
    calls = 0

    def empty_call(*_args, **_kwargs):
        nonlocal calls
        calls += 1
        return ""

    monkeypatch.setattr(
        "knowmat.pdf.figure_describer._vlm_call_with_pool", empty_call
    )
    kwargs = {"model": "test-vlm", "messages": [{"role": "user", "content": "P"}]}

    assert _call_vlm_with_negative_cache("https://example.test/v1", kwargs, image_path) == ""
    assert _call_vlm_with_negative_cache("https://example.test/v1", kwargs, image_path) == ""
    assert calls == 1

    changed = {**kwargs, "messages": [{"role": "user", "content": "changed"}]}
    assert _call_vlm_with_negative_cache("https://example.test/v1", changed, image_path) == ""
    assert calls == 2


def test_vlm_valid_response_is_not_negative_cached(monkeypatch, tmp_path):
    image_path = tmp_path / "figure.jpg"
    image_path.write_bytes(b"valid-image")
    monkeypatch.setenv(
        "KNOWMAT2_VLM_NEGATIVE_CACHE_DIR", str(tmp_path / "cache")
    )
    calls = 0

    def valid_call(*_args, **_kwargs):
        nonlocal calls
        calls += 1
        return "valid description"

    monkeypatch.setattr(
        "knowmat.pdf.figure_describer._vlm_call_with_pool", valid_call
    )
    kwargs = {"model": "test-vlm", "messages": []}

    assert _call_vlm_with_negative_cache(None, kwargs, image_path) == "valid description"
    assert _call_vlm_with_negative_cache(None, kwargs, image_path) == "valid description"
    assert calls == 2


def test_vlm_validated_positive_response_is_cached(monkeypatch, tmp_path):
    image_path = tmp_path / "figure.jpg"
    image_path.write_bytes(b"valid-chart-image")
    monkeypatch.setenv(
        "KNOWMAT2_VLM_NEGATIVE_CACHE_DIR", str(tmp_path / "cache")
    )
    monkeypatch.setenv("KNOWMAT2_VLM_POSITIVE_CACHE_TTL_SECONDS", "600")
    calls = 0

    def valid_call(*_args, **_kwargs):
        nonlocal calls
        calls += 1
        return '{"type":"line","confidence":0.9}'

    monkeypatch.setattr(
        "knowmat.pdf.figure_describer._vlm_call_with_pool", valid_call
    )
    kwargs = {"model": "test-vlm", "messages": []}
    validator = lambda raw: raw.startswith("{") and raw.endswith("}")

    assert _call_vlm_with_negative_cache(
        None, kwargs, image_path, positive_validator=validator
    ).startswith("{")
    assert _call_vlm_with_negative_cache(
        None, kwargs, image_path, positive_validator=validator
    ).startswith("{")
    assert calls == 1


def test_vlm_invalid_positive_response_is_not_cached(monkeypatch, tmp_path):
    image_path = tmp_path / "figure.jpg"
    image_path.write_bytes(b"invalid-chart-image")
    monkeypatch.setenv(
        "KNOWMAT2_VLM_NEGATIVE_CACHE_DIR", str(tmp_path / "cache")
    )
    monkeypatch.setenv("KNOWMAT2_VLM_POSITIVE_CACHE_TTL_SECONDS", "600")
    calls = 0

    def invalid_call(*_args, **_kwargs):
        nonlocal calls
        calls += 1
        return "not-json"

    monkeypatch.setattr(
        "knowmat.pdf.figure_describer._vlm_call_with_pool", invalid_call
    )
    kwargs = {"model": "test-vlm", "messages": []}

    assert _call_vlm_with_negative_cache(
        None, kwargs, image_path, positive_validator=lambda _raw: False
    ) == "not-json"
    assert _call_vlm_with_negative_cache(
        None, kwargs, image_path, positive_validator=lambda _raw: False
    ) == "not-json"
    assert calls == 2


def test_extract_data_persists_enriched_markdown(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(settings, "figure_description_enabled", True)
    monkeypatch.setattr(
        "knowmat.pdf.figure_describer.inject_figure_descriptions",
        lambda text, items, *args, **kwargs: text.replace(
            "Figure 1. SEM image of precipitates.",
            "> [Figure 1 AI Description]: Synthetic description.\n\nFigure 1. SEM image of precipitates.",
        ),
    )

    candidate = {
                        "Paper_Metadata": {"title": "paper"},
                        "Paper_Routing": {
                            "base_material": "Metals",
                            "application": "Structural",
                            "research_paradigm": "Experimental",
                        },
                        "items": [
                            {
                                "Item_ID": "item_001",
                                "Sample_ID": "sample_001",
                                "Role": "Target",
                                "Data_Nature": "Experimental",
                                "base_material": "Metals",
                                "application": "Structural",
                                "research_paradigm": "Experimental",
                                "Extracted_Data": {
                                    "Composition": {
                                        "Composition_Text": {
                                            "original": "not reported",
                                            "simplified": "not reported",
                                        },
                                        "Composition_Observations": [],
                                    },
                                    "Processing": {
                                        "Process_Text": {
                                            "original": "not reported",
                                            "simplified": "not reported",
                                        },
                                        "Process_Route": {
                                            "candidate_stages": [
                                                {
                                                    "candidate_stage_id": "cand_001",
                                                    "stage_index_candidate": 1,
                                                    "process_name_raw": "not reported",
                                                    "process_code_candidate": "UNKNOWN",
                                                    "process_role_candidate": "unknown",
                                                    "parameters_raw": [],
                                                    "source_evidence": ["not reported"],
                                                    "confidence": 0.1,
                                                }
                                            ]
                                        },
                                    },
                                    "Structure": {
                                        "Structure_Text": {"original": None, "simplified": None},
                                        "structure_status": "not_reported",
                                        "Structure_Observations": [],
                                    },
                                    "Properties": [],
                                },
                            }
                        ],
                    }

    monkeypatch.setattr(
        "knowmat.nodes.extraction._extract_alpha25_tasks",
        lambda *_args, **_kwargs: (
            candidate,
            {"complete": True, "task_count": 1, "rejected_facts": 0},
        ),
    )

    md_path = tmp_path / "paper_final_output.md"
    original = "Figure 1. SEM image of precipitates."
    md_path.write_text(original, encoding="utf-8")

    result = extract_data(
        {
            "paper_text": original,
            "paper_text_path": str(md_path),
            "ocr_items": [
                {
                    "typer": "image",
                    "page": 1,
                    "data": {
                        "image_path": str(tmp_path / "page0001-figure1.jpg"),
                        "figure_num": "1",
                        "caption": "SEM image of precipitates.",
                    },
                }
            ],
        }
    )

    persisted = md_path.read_text(encoding="utf-8")
    assert "Figure 1 AI Description" in persisted
    assert result["paper_text"] == persisted
