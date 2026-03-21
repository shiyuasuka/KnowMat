"""PP-StructureV3 / TSR layout routing and accurate table/formula replacement.

This module sits between the page-level PaddleOCR-VL pass and the final
``ocr_items`` list.

Accurate strategy:
1. Run :class:`paddleocr.PPStructureV3` on a page image to obtain
   ``parsing_res_list`` (region label + bbox + block content).
2. Directly replace the corresponding ``ocr_items`` entries for
   ``table``/``chart`` and ``display_formula``/``formula``/``inline_formula``.

The module degrades gracefully: if PP-StructureV3 is unavailable, it returns
the original items unchanged.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# Labels that PP-Structure / PaddleOCR-VL may return for layout regions.
_TABLE_LABELS = frozenset({"table", "chart"})
_FORMULA_LABELS = frozenset({"display_formula", "formula", "inline_formula"})
_FIGURE_LABELS = frozenset({"image", "figure", "figure_title", "seal"})

# A small cache to avoid re-loading PP-StructureV3 models per page.
_PPSTRUCTUREV3_PIPELINE: Optional[Any] = None

# StarRiver-like markdown ignore labels (best-effort).
_PPV3_MARKDOWN_IGNORE_LABELS = [
    "number",
    "footnote",
    "header",
    "header_image",
    "footer",
    "footer_image",
    "aside_text",
]

# Minimum area (pixels²) for a region to be worth re-OCR-ing.
_MIN_REGION_AREA = 4000

# DPI used for the high-resolution crop re-render.
_CROP_DPI = 400


def release_ppstructurev3_pipeline() -> None:
    """Drop the cached PP-StructureV3 instance so GPU weights can be freed between PDFs."""
    global _PPSTRUCTUREV3_PIPELINE
    _PPSTRUCTUREV3_PIPELINE = None


def _bbox_area(bbox: List[float]) -> float:
    """Return area of an [x0, y0, x1, y1] bounding box."""
    if len(bbox) < 4:
        return 0.0
    return max(0.0, bbox[2] - bbox[0]) * max(0.0, bbox[3] - bbox[1])


def _crop_page_image(
    pdf_path: str,
    page_idx: int,
    bbox: List[float],
    dpi: int,
    out_path: Path,
) -> Optional[Path]:
    """Render a sub-region of a PDF page at *dpi* and save to *out_path*.

    ``bbox`` is in the coordinate space of a 72-DPI render (PDF points).
    Returns *out_path* on success, None on failure.
    """
    try:
        import fitz  # type: ignore
    except ImportError:
        logger.debug("PyMuPDF not available; skipping crop re-render.")
        return None

    try:
        doc = fitz.open(pdf_path)
        page = doc[page_idx - 1]
        scale = dpi / 72.0
        clip = fitz.Rect(bbox[0], bbox[1], bbox[2], bbox[3])
        mat = fitz.Matrix(scale, scale)
        pix = page.get_pixmap(matrix=mat, clip=clip, alpha=False)
        pix.save(str(out_path))
        doc.close()
        return out_path
    except Exception as exc:
        logger.warning("Crop render failed (page=%d bbox=%s): %s", page_idx, bbox, exc)
        return None


def _run_ocr_on_image(engine: Any, image_path: Path) -> Optional[str]:
    """Run OCR engine on a single image and return extracted text."""
    img = str(image_path)
    raw = None
    try:
        if hasattr(engine, "predict"):
            try:
                raw = engine.predict(img)
            except TypeError:
                raw = engine.predict(input=img)
        elif hasattr(engine, "ocr"):
            try:
                raw = engine.ocr(img, cls=True)
            except TypeError:
                raw = engine.ocr(img)
        elif callable(engine):
            raw = engine(img)
    except Exception as exc:
        logger.warning("Re-OCR failed for %s: %s", image_path, exc)
        return None

    if raw is None:
        return None

    # Extract text from raw result (handles both PaddleOCR and PaddleOCRVL).
    texts: List[str] = []
    _collect_text(raw, texts)
    return "\n".join(texts) if texts else None


def _collect_text(obj: Any, out: List[str]) -> None:
    if obj is None:
        return
    if isinstance(obj, str):
        t = obj.strip()
        if t:
            out.append(t)
        return
    if isinstance(obj, dict):
        for key in ("text", "rec_text", "ocr_text", "content", "transcription"):
            val = obj.get(key)
            if isinstance(val, str) and val.strip():
                out.append(val.strip())
        for val in obj.values():
            _collect_text(val, out)
        return
    if isinstance(obj, (list, tuple)):
        for item in obj:
            _collect_text(item, out)


def _get_ppstructurev3_pipeline() -> Optional[Any]:
    """Get or create a cached PPStructureV3 pipeline instance."""
    global _PPSTRUCTUREV3_PIPELINE
    if _PPSTRUCTUREV3_PIPELINE is not None:
        return _PPSTRUCTUREV3_PIPELINE

    try:
        from paddleocr import PPStructureV3  # type: ignore
    except ImportError:
        logger.debug("paddleocr.PPStructureV3 is not installed.")
        return None

    # Best-effort alignment with StarRiver-like model settings.
    try:
        _PPSTRUCTUREV3_PIPELINE = PPStructureV3(
            use_region_detection=True,
            use_table_recognition=True,
            use_formula_recognition=True,
            use_chart_recognition=False,
            use_seal_recognition=True,
            format_block_content=True,
            markdown_ignore_labels=_PPV3_MARKDOWN_IGNORE_LABELS,
        )
    except TypeError:
        # Different PaddleOCR versions may have different constructor signatures.
        _PPSTRUCTUREV3_PIPELINE = PPStructureV3()
    except Exception as exc:
        logger.debug("PP-StructureV3 initialization failed: %s", exc)
        return None

    return _PPSTRUCTUREV3_PIPELINE


def _run_ppstructurev3_page_regions(
    pipeline: Any,
    image_path: Path,
) -> Optional[List[Dict[str, Any]]]:
    """Run PP-StructureV3 on one page image and return region list."""
    try:
        output = pipeline.predict(input=str(image_path))
    except Exception as exc:
        logger.debug("PP-StructureV3 predict failed for %s: %s", image_path, exc)
        return None

    res0 = None
    if isinstance(output, list) and output:
        res0 = output[0]
    else:
        res0 = output

    parsing_res_list = getattr(res0, "parsing_res_list", None)
    if parsing_res_list is None and isinstance(res0, dict):
        parsing_res_list = res0.get("parsing_res_list")
    if not parsing_res_list:
        return None

    regions: List[Dict[str, Any]] = []
    for blk in parsing_res_list:
        if not isinstance(blk, dict):
            continue
        blabel = blk.get("block_label") or blk.get("label") or ""
        bbox = blk.get("block_bbox") or blk.get("bbox") or []
        if not blabel or not bbox or len(bbox) < 4:
            continue
        regions.append({"label": blabel, "bbox": bbox, "block": blk})
    return regions


def route_and_reocr(
    ocr_items: List[Dict[str, Any]],
    _pdf_path: str,
    page_images: Dict[int, Path],
    _engine: Any,
    _work_dir: Path,
) -> List[Dict[str, Any]]:
    """Run PP-StructureV3 and directly replace table/formula blocks."""
    if not ocr_items:
        return ocr_items

    pipeline = _get_ppstructurev3_pipeline()
    if pipeline is None:
        return ocr_items

    # Group items by page for efficient processing.
    pages_with_complex: Dict[int, List[int]] = {}
    for i, item in enumerate(ocr_items):
        typer = item.get("typer", "")
        if typer in ("table", "formula"):
            page = item.get("page", 0)
            pages_with_complex.setdefault(page, []).append(i)

    if not pages_with_complex:
        return ocr_items

    from .blocks import block_to_item

    for page_idx, item_indices in pages_with_complex.items():
        page_img = page_images.get(page_idx)
        if page_img is None or not page_img.exists():
            continue

        regions = _run_ppstructurev3_page_regions(pipeline, page_img) or []
        if not regions:
            continue

        for ii in item_indices:
            item = ocr_items[ii]
            item_bbox = item.get("bbox")
            item_typer = item.get("typer", "")

            if item_bbox is None or _bbox_area(item_bbox) < _MIN_REGION_AREA:
                continue

            best_region = _find_best_matching_region(item_bbox, regions, item_typer)
            if not best_region:
                continue

            pp_block = best_region.get("block")
            if not isinstance(pp_block, dict):
                continue

            new_item = block_to_item(pp_block)
            if not new_item:
                continue

            new_item["page"] = page_idx
            new_item["bbox"] = best_region.get("bbox")
            new_item["block_label"] = best_region.get("label")

            # Preserve confidence from the original PaddleOCR-VL item when
            # PP-StructureV3 doesn't provide one.
            if "confidence" not in new_item and item.get("confidence") is not None:
                new_item["confidence"] = item["confidence"]

            new_item["reocr_source"] = "ppstructurev3_replace"
            ocr_items[ii] = new_item

    return ocr_items


def reocr_chem_formula_blocks(
    ocr_items: List[Dict[str, Any]],
    pdf_path: str,
    page_images: Dict[int, Path],
    engine: Any,
    work_dir: Path,
) -> List[Dict[str, Any]]:
    """Re-OCR paragraph blocks that appear to contain chemical formulas.

    Detects paragraph items whose text matches an element-number pattern
    (e.g. ``Ti42Hf21``) and re-runs OCR on the corresponding bbox crop at
    higher DPI to improve subscript / decimal accuracy.

    Parameters are the same as :func:`route_and_reocr`.
    """
    import re

    # Lightweight element pattern for detection (does not need to be exhaustive).
    _ELEM_PAT = re.compile(
        r"\b(?:Ti|Hf|Nb|Ta|Mo|Zr|Al|V|Cr|Mn|Fe|Co|Ni|Cu|W|Si|C|N|B|Re|Ru|Pd|Pt|Au|Ag)"
        r"\d+(?:[.,]\d+)?"
    )

    crops_dir = work_dir / "chem_crops"
    modified = 0

    for i, item in enumerate(ocr_items):
        if item.get("typer") != "paragraph":
            continue
        text = item.get("text", "")
        if not _ELEM_PAT.search(text):
            continue
        bbox = item.get("bbox")
        if not bbox or _bbox_area(bbox) < _MIN_REGION_AREA:
            continue

        page = item.get("page", 0)
        page_img = page_images.get(page)
        if page_img is None or not page_img.exists():
            continue

        crops_dir.mkdir(parents=True, exist_ok=True)
        crop_path = crops_dir / f"chem-page{page:04d}-item{i:04d}.png"
        rendered = _crop_page_image(pdf_path, page, bbox, _CROP_DPI, crop_path)
        if rendered is None:
            continue

        reocr_text = _run_ocr_on_image(engine, rendered)
        if reocr_text and reocr_text.strip():
            item["text"] = reocr_text.strip()
            item["reocr_source"] = "chem_crop_reocr"
            modified += 1

    if modified:
        logger.info("Re-OCR'd %d chemical formula paragraph block(s).", modified)
    return ocr_items


def _find_best_matching_region(
    item_bbox: List[float],
    regions: List[Dict[str, Any]],
    item_typer: str,
) -> Optional[Dict[str, Any]]:
    """Find the PP-Structure region that best overlaps with *item_bbox*."""
    target_labels = _TABLE_LABELS if item_typer == "table" else _FORMULA_LABELS
    best: Optional[Dict[str, Any]] = None
    best_iou = 0.0

    for region in regions:
        if region.get("label", "").lower() not in target_labels:
            continue
        rbbox = region.get("bbox", [])
        if len(rbbox) < 4:
            continue
        iou = _bbox_iou(item_bbox, rbbox)
        if iou > best_iou:
            best_iou = iou
            best = region

    return best if best_iou > 0.1 else None


def _bbox_iou(a: List[float], b: List[float]) -> float:
    """Compute Intersection-over-Union for two [x0,y0,x1,y1] boxes."""
    ix0 = max(a[0], b[0])
    iy0 = max(a[1], b[1])
    ix1 = min(a[2], b[2])
    iy1 = min(a[3], b[3])
    inter = max(0.0, ix1 - ix0) * max(0.0, iy1 - iy0)
    if inter <= 0.0:
        return 0.0
    area_a = _bbox_area(a)
    area_b = _bbox_area(b)
    union = area_a + area_b - inter
    return inter / union if union > 0 else 0.0
