import json

import pytest

from knowmat.ocr_manifest import (
    OCRManifestError,
    freeze_ocr_baseline,
    verify_ocr_record,
    verify_ocr_baseline,
)
from knowmat.orchestrator import verify_selected_ocr_input


def _paper(root, stem, text="OCR text"):
    pdf = root / f"{stem}.pdf"
    pdf.write_bytes(b"%PDF fresh")
    paper_dir = root / stem
    paper_dir.mkdir()
    (paper_dir / f"{stem}.md").write_text(text, encoding="utf-8")
    (paper_dir / f"{stem}.json").write_text(
        json.dumps([{"text": text}]), encoding="utf-8"
    )
    return pdf


def test_freeze_requires_every_pdf_to_be_fresh_in_current_run(tmp_path):
    first = _paper(tmp_path, "first")
    second = _paper(tmp_path, "second")

    with pytest.raises(OCRManifestError, match="complete fresh run"):
        freeze_ocr_baseline(
            tmp_path,
            [first, second],
            baseline_name="new-local",
            backend={"kind": "local", "engine": "paddleocr-vl"},
            fresh_pdf_paths=[first],
        )


def test_frozen_manifest_verifies_and_detects_mutation(tmp_path):
    first = _paper(tmp_path, "first")
    second = _paper(tmp_path, "second")
    manifest_path = tmp_path / "baseline.json"
    frozen = freeze_ocr_baseline(
        tmp_path,
        [first, second],
        baseline_name="new-local",
        backend={"kind": "local", "engine": "paddleocr-vl"},
        fresh_pdf_paths=[first, second],
        output_path=manifest_path,
    )

    verified = verify_ocr_baseline(manifest_path, tmp_path)
    assert verified["baseline_id"] == frozen["baseline_id"]
    assert verified["record_count"] == 2
    record = verify_ocr_record(verified, tmp_path / "first" / "first.md", tmp_path)
    assert record["paper_key"] == "first"

    (tmp_path / "first" / "first.md").write_text("changed", encoding="utf-8")
    with pytest.raises(OCRManifestError, match="changed"):
        verify_ocr_baseline(manifest_path, tmp_path)


def test_empty_ocr_artifact_cannot_freeze(tmp_path):
    pdf = _paper(tmp_path, "empty", text="")

    with pytest.raises(OCRManifestError, match="empty OCR Markdown"):
        freeze_ocr_baseline(
            tmp_path,
            [pdf],
            baseline_name="bad",
            backend={"kind": "local"},
            fresh_pdf_paths=[pdf],
        )


def test_pipeline_preflight_verifies_source_markdown_not_output_copy(tmp_path):
    pdf = _paper(tmp_path, "paper")
    manifest_path = tmp_path / "baseline.json"
    frozen = freeze_ocr_baseline(
        tmp_path,
        [pdf],
        baseline_name="fresh",
        backend={"kind": "paddleocr_api"},
        fresh_pdf_paths=[pdf],
        output_path=manifest_path,
    )
    source_md = tmp_path / "paper" / "paper.md"

    verify_selected_ocr_input(
        str(source_md),
        ocr_baseline_id=frozen["baseline_id"],
        ocr_manifest_path=str(manifest_path),
    )

    parser_copy = tmp_path / "output" / "paper_final_output.md"
    parser_copy.parent.mkdir()
    parser_copy.write_text(source_md.read_text(encoding="utf-8"), encoding="utf-8")
    with pytest.raises(OCRManifestError, match="not part of the frozen baseline"):
        verify_selected_ocr_input(
            str(parser_copy),
            ocr_baseline_id=frozen["baseline_id"],
            ocr_manifest_path=str(manifest_path),
        )
