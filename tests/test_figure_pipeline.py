from pathlib import Path

from knowmat.app_config import settings
from knowmat.nodes.extraction import extract_data
from knowmat.nodes.paddleocrvl_parse_pdf import _persist_figure_images
from knowmat.pdf.figure_describer import inject_figure_descriptions


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


def test_extract_data_persists_enriched_markdown(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(settings, "figure_description_enabled", True)
    monkeypatch.setattr(
        "knowmat.pdf.figure_describer.inject_figure_descriptions",
        lambda text, items, *args, **kwargs: text.replace(
            "Figure 1. SEM image of precipitates.",
            "> [Figure 1 AI Description]: Synthetic description.\n\nFigure 1. SEM image of precipitates.",
        ),
    )

    class DummyExtractor:
        def invoke(self, *_args, **_kwargs):
            return {"responses": [{}]}

    monkeypatch.setattr("knowmat.nodes.extraction.extraction_extractor", DummyExtractor())

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
