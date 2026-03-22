"""
PDF parsing node using PaddleOCR-VL, with optional legacy PaddleOCR fallback.

Legacy mode still runs PP-StructureV3 (layout seed + :func:`route_and_reocr` refinement).
"""

from __future__ import annotations

import json
import logging
import os
import shutil
import tempfile
from concurrent.futures import Future, ThreadPoolExecutor
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from knowmat.pdf.blocks import block_to_item, sanitize_ocr_items_vl_artifacts, text_to_paragraph_items
from knowmat.pdf.block_filter import filter_figure_internal_fragments
from knowmat.pdf.doi_extractor import extract_doi_from_pdf_metadata, extract_first_doi
from knowmat.pdf.html_cleaner import convert_html_to_markdown
from knowmat.pdf.ocr_cache import (
    cache_signature_key,
    md5_file_digest,
    ocr_cache_bucket,
    pages_key_for_cache,
    parse_pages_argument,
    save_ocr_cache,
    try_load_ocr_cache,
)
from knowmat.pdf.ocr_engine import (
    create_ocr_engine,
    default_model_dir,
    ensure_paddle_device_from_env,
    normalize_lines,
    paddleocr_raw_to_lines,
    run_ocr_batch,
    run_ocr_sequential,
    supports_batch_predict,
    try_release_paddle_gpu_memory,
)
from knowmat.pdf.table_structure import (
    reocr_chem_formula_blocks,
    release_ppstructurev3_pipeline,
    route_and_reocr,
    seed_legacy_complex_items_from_ppstructurev3,
)
from knowmat.pdf.section_normalizer import (
    normalize_alloy_strings,
    normalize_leading_masthead_and_title,
    normalize_plain_author_superscripts,
    repair_keywords_abstract_two_column_ocr,
    strip_references_section,
    structure_sections,
)
from knowmat.pdf.formula_formatter import format_formula_text
from knowmat.app_config import settings
from knowmat.states import KnowMatState

logger = logging.getLogger(__name__)

# Defaults (override with OCR_MAX_RENDER_WORKERS, OCR_HEADER_LINES, OCR_FOOTER_LINES, etc.).
_DEFAULT_MAX_RENDER_WORKERS = 4
_DEFAULT_OCR_MAX_WORKERS = 1
_DEFAULT_OCR_HEADER_LINES = 5
_DEFAULT_OCR_FOOTER_LINES = 3
_DEFAULT_OCR_LOW_CONFIDENCE = 0.5

_LAYOUT_NOISE_LABELS = frozenset(
    {
        "header",
        "footer",
        "header_image",
        "footer_image",
        "aside_text",
        "number",
        "footnote",
    }
)

_SIDEBAR_X_FRAC = 0.15
_HEADER_Y_FRAC = 0.08
_FOOTER_Y_FRAC = 0.92


def _env_truthy(name: str) -> bool:
    v = os.getenv(name, "").strip().lower()
    return v in ("1", "true", "yes", "on")


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)).strip())
    except ValueError:
        return default


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, str(default)).strip())
    except ValueError:
        return default


def _chunked(seq: List[Any], size: int) -> List[List[Any]]:
    if size <= 0:
        return [seq]
    return [seq[i : i + size] for i in range(0, len(seq), size)]


def _build_ocr_quality_report(
    ocr_items: List[Dict[str, Any]],
    pp_status: Dict[str, Any],
    low_threshold: float,
) -> Dict[str, Any]:
    confidences: List[float] = []
    low_pages: set[int] = set()
    for it in ocr_items:
        c = it.get("confidence")
        if c is not None and isinstance(c, (int, float)):
            confidences.append(float(c))
            p = int(it.get("page", 0) or 0)
            if float(c) < low_threshold and p > 0:
                low_pages.add(p)
    tables = sum(1 for it in ocr_items if it.get("typer") == "table")
    formulas = sum(1 for it in ocr_items if it.get("typer") == "formula")
    avg_conf: Optional[float] = None
    if confidences:
        avg_conf = sum(confidences) / len(confidences)
    return {
        "ocr_avg_confidence": avg_conf,
        "ocr_low_confidence_pages": sorted(low_pages),
        "table_count": tables,
        "formula_count": formulas,
        "ppstructure_status": pp_status.get("ppstructure_status"),
        "ppstructure_detail": pp_status.get("ppstructure_detail"),
        "ppstructure_replacements": pp_status.get("ppstructure_replacements", 0),
    }


def _env_low_confidence_action() -> str:
    v = os.getenv("KNOWMAT_OCR_LOW_CONF_ACTION", "none").strip().lower()
    if v in ("none", "tag", "drop"):
        return v
    return "none"


def _apply_ocr_low_confidence_policy(
    items: List[Dict[str, Any]],
    threshold: float,
    action: str,
) -> List[Dict[str, Any]]:
    """Apply ``OCR_LOW_CONFIDENCE_THRESHOLD`` to ``paragraph`` items only (tables/formulas unchanged)."""
    if action == "none" or not items:
        return items
    out: List[Dict[str, Any]] = []
    for it in items:
        if it.get("typer") != "paragraph":
            out.append(it)
            continue
        conf = it.get("confidence")
        if conf is None or not isinstance(conf, (int, float)):
            out.append(it)
            continue
        if float(conf) >= threshold:
            out.append(it)
            continue
        if action == "drop":
            logger.debug(
                "Dropped paragraph below OCR_LOW_CONFIDENCE_THRESHOLD on page %s",
                it.get("page"),
            )
            continue
        tagged = dict(it)
        tagged["low_confidence"] = True
        txt = tagged.get("text") or ""
        prefix = "[Low confidence text] "
        if txt and not txt.startswith(prefix):
            tagged["text"] = prefix + txt
        out.append(tagged)
    return out


def _render_page(args: Tuple[str, int, int, str]) -> Path:
    import fitz  # type: ignore

    pdf_path_str, page_idx, dpi, image_dir_str = args
    image_dir = Path(image_dir_str)
    pdf_stem = Path(pdf_path_str).stem
    image_path = image_dir / f"{pdf_stem}-page-{page_idx:04d}.png"

    doc = fitz.open(pdf_path_str)
    try:
        page = doc[page_idx - 1]
        page.get_pixmap(dpi=dpi, alpha=False).save(str(image_path))
    finally:
        doc.close()
    return image_path


def _save_ocr_json(raw: Any, dest: Path) -> None:
    with open(dest, "w", encoding="utf-8") as f:
        json.dump(raw, f, ensure_ascii=False, indent=2, default=str)


def _export_tables_to_csv(ocr_items: List[Dict[str, Any]], tables_dir: Path) -> None:
    """Export structured table items to CSV files for traceability."""
    import csv

    table_items = [it for it in ocr_items if it.get("typer") == "table"]
    if not table_items:
        return

    tables_dir.mkdir(parents=True, exist_ok=True)
    counters: Dict[int, int] = {}
    for item in table_items:
        page = item.get("page", 0)
        counters[page] = counters.get(page, 0) + 1
        n = counters[page]
        data = item.get("data", {})
        structured = data if isinstance(data, dict) and "rows" in data else None
        if structured is None:
            continue
        rows = structured.get("rows", [])
        columns = [c["name"] for c in structured.get("columns", [])]
        if not rows or not columns:
            continue
        csv_path = tables_dir / f"page{page:04d}-table{n:02d}.csv"
        try:
            with open(csv_path, "w", newline="", encoding="utf-8") as fh:
                writer = csv.DictWriter(fh, fieldnames=columns, extrasaction="ignore")
                writer.writeheader()
                writer.writerows(rows)
        except OSError as exc:
            logger.warning("Failed to write table CSV %s: %s", csv_path, exc)


def _extract_pdf_with_paddleocrvl(
    pdf_path: str,
    output_dir: str,
    model_dir: Path,
    save_intermediate: bool = True,
    page_indices: Optional[List[int]] = None,
) -> Tuple[str, Dict[str, Any], List[Dict[str, Any]]]:
    try:
        import fitz  # type: ignore
    except ImportError as exc:
        raise ImportError("PyMuPDF is required for PaddleOCR parsing. Install with: pip install pymupdf") from exc

    pdf = Path(pdf_path)
    out_dir = Path(output_dir)
    temp_pdf_ctx = None
    work_pdf = pdf
    if not all(ord(c) < 128 for c in pdf_path):
        temp_pdf_ctx = tempfile.TemporaryDirectory()
        work_pdf = Path(temp_pdf_ctx.name) / "source.pdf"
        shutil.copy2(pdf_path, work_pdf)

    temp_dir = None
    if save_intermediate:
        image_dir = out_dir / "page_images"
        raw_dir = out_dir / "ocr_raw"
        image_dir.mkdir(parents=True, exist_ok=True)
        raw_dir.mkdir(parents=True, exist_ok=True)
    else:
        temp_dir = tempfile.TemporaryDirectory()
        image_dir = Path(temp_dir.name)
        raw_dir = None

    max_render_workers = _env_int("OCR_MAX_RENDER_WORKERS", _DEFAULT_MAX_RENDER_WORKERS)
    header_lines = _env_int("OCR_HEADER_LINES", _DEFAULT_OCR_HEADER_LINES)
    footer_lines = _env_int("OCR_FOOTER_LINES", _DEFAULT_OCR_FOOTER_LINES)
    low_conf_thr = _env_float("OCR_LOW_CONFIDENCE_THRESHOLD", _DEFAULT_OCR_LOW_CONFIDENCE)
    pages_per_release = _env_int("OCR_PAGES_PER_RELEASE", 0)

    engine: Any = None
    backend = ""
    try:
        engine, backend = create_ocr_engine(model_dir=model_dir)

        doc = fitz.open(str(work_pdf))
        total_pages = len(doc)
        if total_pages <= 0:
            doc.close()
            return "", {"backend": backend, "pages": 0, "ocr_items": 0}, []

        if page_indices is None:
            selected_pages = list(range(1, total_pages + 1))
        else:
            selected_pages = sorted({p for p in page_indices if 1 <= p <= total_pages})
            if not selected_pages:
                doc.close()
                raise ValueError("No valid pages in ocr_pages range for this PDF.")

        if 1 in selected_pages:
            first_page_pymupdf_text = doc[0].get_text("text")
        else:
            first_page_pymupdf_text = doc[selected_pages[0] - 1].get_text("text")
        doc.close()

        render_dpi = _env_int("OCR_RENDER_DPI", 300)
        if render_dpi < 72 or render_dpi > 600:
            logger.warning("OCR_RENDER_DPI=%s out of range [72,600]; using 300.", render_dpi)
            render_dpi = 300

        render_args = [(str(work_pdf), idx, render_dpi, str(image_dir)) for idx in selected_pages]
        num_workers = min(max_render_workers, max(1, os.cpu_count() or 1), len(selected_pages))
        with ThreadPoolExecutor(max_workers=num_workers) as render_pool:
            image_paths: List[Path] = list(render_pool.map(_render_page, render_args))

        page_blocks: List[str] = []
        page_level_meta: List[Dict[str, Any]] = []
        ocr_items: List[Dict[str, Any]] = []
        first_page_full_text = first_page_pymupdf_text
        bg_futures: List[Future[Any]] = []
        vl_results: List[Any] = []

        batch_size = max(1, _env_int("OCR_BATCH_SIZE", 2))
        raw_results: List[Any] = []

        if pages_per_release > 0:
            logger.info(
                "OCR_PAGES_PER_RELEASE=%d: running inference in segments with GPU memory release between segments.",
                pages_per_release,
            )
            for chunk_paths in _chunked(image_paths, pages_per_release):
                if supports_batch_predict(engine):
                    bs = min(batch_size, len(chunk_paths))
                    raw_results.extend(run_ocr_batch(engine, chunk_paths, bs))
                else:
                    raw_results.extend(run_ocr_sequential(engine, chunk_paths))
                try_release_paddle_gpu_memory()
        else:
            if supports_batch_predict(engine):
                logger.info(
                    "Using batch OCR inference (batch_size=%d) for %d pages...",
                    batch_size,
                    len(image_paths),
                )
                raw_results = run_ocr_batch(engine, image_paths, batch_size)
                logger.info("✓ OCR batch inference completed.")
            else:
                max_ocr_workers = _env_int("OCR_MAX_WORKERS", _DEFAULT_OCR_MAX_WORKERS)
                if max_ocr_workers > 1:
                    logger.warning(
                        "OCR_MAX_WORKERS=%d ignored: shared OCR engine is not safe for concurrent inference; using sequential mode.",
                        max_ocr_workers,
                    )
                logger.info("Using sequential OCR inference for %d pages...", len(image_paths))
                raw_results = run_ocr_sequential(engine, image_paths)
                logger.info("✓ OCR sequential inference completed.")

        with ThreadPoolExecutor(max_workers=2) as bg_io_pool:
            try:
                for page_idx, raw in zip(selected_pages, raw_results):
                    if raw is not None and raw_dir is not None:
                        dest = raw_dir / f"page-{page_idx:04d}.json"
                        bg_futures.append(bg_io_pool.submit(_save_ocr_json, raw, dest))

                    if backend == "paddleocrvl":
                        if raw is not None:
                            if isinstance(raw, list):
                                vl_results.extend(raw)
                            else:
                                vl_results.append(raw)
                    else:
                        lines = normalize_lines(paddleocr_raw_to_lines(raw))
                        if not lines:
                            doc = fitz.open(str(work_pdf))
                            try:
                                fallback = doc[page_idx - 1].get_text("text")
                            finally:
                                doc.close()
                            lines = [x.strip() for x in fallback.splitlines() if x.strip()]

                        page_text = convert_html_to_markdown("\n".join(lines).strip())
                        page_blocks.append(f"## Page {page_idx}\n\n{page_text}")
                        page_level_meta.append(
                            {
                                "page": page_idx,
                                "header_text": "\n".join(lines[:header_lines]),
                                "footer_text": "\n".join(lines[-footer_lines:])
                                if len(lines) >= footer_lines
                                else "",
                                "line_count": len(lines),
                            }
                        )
                    if page_idx == selected_pages[0]:
                        first_page_full_text = (
                            first_page_pymupdf_text
                            if backend == "paddleocrvl"
                            else page_text + "\n" + first_page_pymupdf_text
                        )
            finally:
                for fut in bg_futures:
                    fut.result()

            if backend == "paddleocrvl" and vl_results:
                logger.info("Starting restructure_pages for layout analysis...")
                try:
                    _ignore_labels = list(_LAYOUT_NOISE_LABELS)
                    restructure_kwargs: Dict[str, Any] = {
                        "merge_tables": True,
                        "relevel_titles": True,
                        # False keeps one restructure result per OCR page; True returns a single
                        # merged page and breaks zip(selected_pages, restructured) (wrong meta/blocks).
                        "concatenate_pages": False,
                    }
                    try:
                        restructured = engine.restructure_pages(
                            vl_results, markdown_ignore_labels=_ignore_labels, **restructure_kwargs
                        )
                    except TypeError:
                        restructured = engine.restructure_pages(vl_results, **restructure_kwargs)
                    restructured = list(restructured)
                    logger.info("✓ restructure_pages completed: %d pages", len(restructured))
                except (RuntimeError, ValueError, TypeError) as exc:
                    logger.warning("restructure_pages failed for %s: %s", pdf, exc, exc_info=True)
                    restructured = []

                if len(restructured) != len(selected_pages):
                    logger.warning(
                        "restructure_pages returned %d page(s) but %d page(s) were OCR'd; aligning by position.",
                        len(restructured),
                        len(selected_pages),
                    )

                for pdf_page, res in zip(selected_pages, restructured):
                    try:
                        md_info = res._to_markdown(pretty=True, show_formula_number=False)
                        page_text = md_info.get("markdown_texts", "")
                    except (AttributeError, TypeError, KeyError) as exc:
                        logger.warning("_to_markdown failed for page %d of %s: %s", pdf_page, pdf, exc)
                        page_text = ""
                    page_text = convert_html_to_markdown(page_text)
                    if page_text:
                        page_blocks.append(page_text)

                    lines = [ln for ln in page_text.splitlines() if ln.strip()]
                    page_level_meta.append(
                        {
                            "page": pdf_page,
                            "header_text": "\n".join(lines[:header_lines]),
                            "footer_text": "\n".join(lines[-footer_lines:])
                            if len(lines) >= footer_lines
                            else "",
                            "line_count": len(lines),
                        }
                    )

                    try:
                        blocks = res["parsing_res_list"]
                    except (KeyError, TypeError, IndexError):
                        blocks = getattr(res, "parsing_res_list", [])
                    for block in blocks or []:
                        blabel = (
                            block.get("block_label")
                            if isinstance(block, dict)
                            else getattr(block, "block_label", None)
                        )
                        bbox = (
                            block.get("block_bbox")
                            if isinstance(block, dict)
                            else getattr(block, "block_bbox", None)
                        )
                        is_noise = blabel in _LAYOUT_NOISE_LABELS
                        
                        # Filter out general layout noise based on bbox position for header/footer
                        if bbox is not None and len(bbox) == 4:
                            _, y0, _, y1 = bbox
                            # Use typical PDF dimensions (e.g. 842 points height) as heuristic if needed
                            # but simple fractional check works if we assume 1.0 is max
                            # Since we don't have page height here, we rely primarily on blabel
                            pass
                            
                        item = block_to_item(block)
                        if item:
                            item["page"] = pdf_page
                            if bbox is not None:
                                item["bbox"] = bbox
                            if blabel is not None:
                                item["block_label"] = blabel
                            if is_noise:
                                item["is_layout_noise"] = True
                            ocr_items.append(item)

        merged = "\n\n".join(page_blocks).strip()
        if not ocr_items and merged:
            ocr_items = text_to_paragraph_items(merged)
        if backend == "paddleocr":
            seeded = seed_legacy_complex_items_from_ppstructurev3(selected_pages, image_paths)
            if seeded:
                ocr_items.extend(seeded)

        if ocr_items:
            try:
                ocr_items, n_removed = filter_figure_internal_fragments(ocr_items)
                if n_removed:
                    logger.info("Removed %d figure-internal fragment(s) from %s", n_removed, pdf)
            except Exception as exc:
                logger.warning("filter_figure_internal_fragments failed: %s", exc, exc_info=True)

        lc_action = _env_low_confidence_action()
        if ocr_items and lc_action != "none":
            ocr_items = _apply_ocr_low_confidence_policy(ocr_items, low_conf_thr, lc_action)

        pp_report: Dict[str, Any] = {
            "ppstructure_status": "not_applicable",
            "ppstructure_detail": "",
            "ppstructure_replacements": 0,
        }
        if ocr_items:
            logger.info("Starting PP-StructureV3 refinement for tables and formulas...")
            page_images_map: Dict[int, Path] = dict(zip(selected_pages, image_paths))
            reocr_work_dir = out_dir if save_intermediate else Path(image_dir)
            try:
                ocr_items, pp_report = route_and_reocr(
                    ocr_items,
                    str(work_pdf),
                    page_images_map,
                    engine,
                    reocr_work_dir,
                )
                logger.info("✓ PP-StructureV3 table/formula refinement completed.")
            except Exception as exc:
                logger.warning("route_and_reocr failed: %s", exc, exc_info=True)
                pp_report = {
                    "ppstructure_status": "failed",
                    "ppstructure_detail": str(exc),
                    "ppstructure_replacements": 0,
                }
            # Release GPU memory after PP-StructureV3 refinement to reduce peak usage
            # This is especially important for 8GB VRAM cards when processing PDFs with many tables/formulas
            try_release_paddle_gpu_memory()
            
            if not _env_truthy("KNOWMAT_SKIP_CHEM_REOCR"):
                try:
                    ocr_items = reocr_chem_formula_blocks(
                        ocr_items,
                        str(work_pdf),
                        page_images_map,
                        engine,
                        reocr_work_dir,
                    )
                    logger.info("✓ Chemical formula re-OCR completed.")
                except Exception as exc:
                    logger.warning("reocr_chem_formula_blocks failed: %s", exc, exc_info=True)
                # Release GPU memory after chemical formula re-OCR
                try_release_paddle_gpu_memory()
            else:
                logger.info("KNOWMAT_SKIP_CHEM_REOCR set: skipping chemical formula crop re-OCR.")

        doi = extract_doi_from_pdf_metadata(str(work_pdf)) or extract_first_doi(first_page_full_text)

        if save_intermediate and raw_dir is not None:
            tables_dir = out_dir / "tables"
            _export_tables_to_csv(ocr_items, tables_dir)

        quality = _build_ocr_quality_report(ocr_items, pp_report, low_conf_thr)

        metadata = {
            "backend": backend,
            "model_dir": str(model_dir),
            "pages": len(selected_pages),
            "image_dir": str(image_dir),
            "ocr_raw_dir": str(raw_dir) if raw_dir is not None else None,
            "doi": doi,
            "page_level_metadata": page_level_meta,
            "ocr_items": len(ocr_items),
            "ocr_quality": quality,
        }
        return merged, metadata, ocr_items
    finally:
        # Release OCR engine resources
        if engine is not None:
            # PaddleOCR-VL's close() can tear down the CUDA context such that the next PDF
            # still hits Place(undefined:0) inside Paddle despite set_device("gpu:0"). Skip
            # close by default; opt in with KNOWMAT_PADDLEOCR_VL_EXPLICIT_CLOSE=1 if you need
            # aggressive native cleanup between PDFs.
            skip_vl_close = backend == "paddleocrvl" and not _env_truthy(
                "KNOWMAT_PADDLEOCR_VL_EXPLICIT_CLOSE"
            )
            if skip_vl_close:
                logger.debug(
                    "Skipping PaddleOCR-VL engine.close() between PDFs (set "
                    "KNOWMAT_PADDLEOCR_VL_EXPLICIT_CLOSE=1 to force close)."
                )
            else:
                if hasattr(engine, "close"):
                    try:
                        engine.close()
                        logger.debug("OCR engine closed via close() method")
                    except Exception as e:
                        logger.debug("OCR engine close() failed (non-critical): %s", e)
                elif hasattr(engine, "destroy"):
                    try:
                        engine.destroy()
                        logger.debug("OCR engine destroyed via destroy() method")
                    except Exception as e:
                        logger.debug("OCR engine destroy() failed (non-critical): %s", e)
            del engine
            engine = None
        # Release PP-StructureV3 pipeline
        release_ppstructurev3_pipeline()
        # Release Paddle GPU memory
        try_release_paddle_gpu_memory()
        # After close()/pipeline drop/empty_cache, Paddle may leave Place(undefined:0); fix for next PDF.
        ensure_paddle_device_from_env()
        # Cleanup temporary directories
        if temp_dir is not None:
            temp_dir.cleanup()
        if temp_pdf_ctx is not None:
            temp_pdf_ctx.cleanup()


def _read_txt_file(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return path.read_text(encoding="utf-8", errors="ignore")


def _finalize_pdf_parse(
    source_path: Path,
    parse_output_dir: Path,
    save_intermediate: bool,
    extracted_text: str,
    metadata: Dict[str, Any],
    _ocr_items: List[Dict[str, Any]],
) -> Dict[str, Any]:
    if _ocr_items:
        sanitize_ocr_items_vl_artifacts(_ocr_items)

    structured_text = normalize_leading_masthead_and_title(extracted_text)
    structured_text = structure_sections(structured_text)
    structured_text = repair_keywords_abstract_two_column_ocr(structured_text)
    structured_text = normalize_plain_author_superscripts(structured_text)
    structured_text = normalize_alloy_strings(structured_text)
    structured_text = format_formula_text(structured_text)
    cleaned_text = (
        strip_references_section(structured_text)
        if settings.trim_references_section
        else structured_text
    )
    doi_from_ocr = metadata.get("doi")
    if doi_from_ocr and doi_from_ocr not in cleaned_text:
        cleaned_text = f"DOI: {doi_from_ocr}\n\n{cleaned_text}"

    pdf_name = source_path.stem
    if save_intermediate:
        final_md_path = parse_output_dir / f"{pdf_name}_final_output.md"
        with open(final_md_path, "w", encoding="utf-8") as f:
            f.write(cleaned_text)
        print(f"Saved final markdown output to: {final_md_path}")

    doc_meta = {
        "backend": metadata.get("backend", "paddleocrvl"),
        "model_dir": metadata.get("model_dir"),
        "pages": metadata.get("pages"),
        "doi": doi_from_ocr,
        "page_level_metadata": metadata.get("page_level_metadata"),
        "ocr_quality": metadata.get("ocr_quality"),
    }
    if save_intermediate:
        meta_path = parse_output_dir / f"{pdf_name}_parse_metadata.json"
        with open(meta_path, "w", encoding="utf-8") as f:
            json.dump(metadata, f, ensure_ascii=False, indent=2)
        print(f"Saved parser metadata to: {meta_path}")
    return {
        "paper_text": cleaned_text,
        "document_metadata": doc_meta,
        "metadata": doc_meta,
        "ocr_items": _ocr_items or text_to_paragraph_items(cleaned_text),
    }


def parse_pdf_with_paddleocrvl(state: KnowMatState) -> dict:
    input_path = state.get("pdf_path")
    if not input_path:
        raise ValueError("No input file path provided in state for parse_pdf_with_paddleocrvl node.")
    save_intermediate = bool(state.get("save_intermediate", True))
    output_dir = state.get("output_dir", ".")
    source_path = Path(input_path)
    suffix = source_path.suffix.lower()

    if suffix in (".txt", ".md"):
        parse_output_dir = Path(output_dir) / "txt_parse" if save_intermediate else Path(output_dir)
        if save_intermediate:
            parse_output_dir.mkdir(parents=True, exist_ok=True)

        raw_text = _read_txt_file(source_path)
        md_text = convert_html_to_markdown(raw_text)
        md_text = normalize_leading_masthead_and_title(md_text)
        md_text = structure_sections(md_text)
        md_text = repair_keywords_abstract_two_column_ocr(md_text)
        md_text = normalize_plain_author_superscripts(md_text)
        md_text = normalize_alloy_strings(md_text)
        md_text = format_formula_text(md_text)
        cleaned_text = (
            strip_references_section(md_text) if settings.trim_references_section else md_text
        )
        stem = source_path.stem

        doi = extract_first_doi(cleaned_text[:5000])
        if doi and doi not in cleaned_text:
            cleaned_text = f"DOI: {doi}\n\n{cleaned_text}"

        if save_intermediate:
            final_md_path = parse_output_dir / f"{stem}_final_output.md"
            with open(final_md_path, "w", encoding="utf-8") as f:
                f.write(cleaned_text)
            print(f"Saved txt parsed output to: {final_md_path}")

        doc_meta: Dict[str, Any] = {"backend": "txt-direct", "source_file": str(source_path), "doi": doi}
        if save_intermediate:
            meta_path = parse_output_dir / f"{stem}_parse_metadata.json"
            with open(meta_path, "w", encoding="utf-8") as f:
                json.dump(doc_meta, f, ensure_ascii=False, indent=2)
            print(f"Saved parser metadata to: {meta_path}")
        return {
            "paper_text": cleaned_text,
            "document_metadata": doc_meta,
            "metadata": doc_meta,
            "ocr_items": text_to_paragraph_items(cleaned_text),
        }

    if suffix != ".pdf":
        raise ValueError(
            f"Unsupported file type: {source_path.suffix}. Only .pdf, .txt, and .md are supported."
        )
    parse_output_dir = Path(output_dir) / "paddleocrvl_parse" if save_intermediate else Path(output_dir)
    if save_intermediate:
        parse_output_dir.mkdir(parents=True, exist_ok=True)
    model_dir = default_model_dir()

    try:
        import fitz  # type: ignore
    except ImportError as exc:
        raise RuntimeError("PyMuPDF is required for PDF parsing.") from exc

    doc = fitz.open(str(source_path))
    total_pages = len(doc)
    doc.close()

    raw_pages = state.get("ocr_pages")
    if raw_pages is None:
        raw_pages = os.getenv("KNOWMAT_OCR_PAGES", "")
    pages_spec = (raw_pages or "").strip()
    if pages_spec:
        selected_pages = parse_pages_argument(pages_spec, total_pages)
        if not selected_pages:
            raise ValueError("No valid pages in --ocr-pages / ocr_pages for this PDF.")
    else:
        selected_pages = list(range(1, total_pages + 1))

    render_dpi = _env_int("OCR_RENDER_DPI", 300)
    if render_dpi < 72 or render_dpi > 600:
        render_dpi = 300
    vl_version = os.getenv("PADDLEOCRVL_VERSION", "1.5").strip() or "1.5"
    # PP-StructureV3 精修始终参与；缓存键固定为完整 VL+Structure 管线
    skip_pp = False
    skip_chem = _env_truthy("KNOWMAT_SKIP_CHEM_REOCR")
    pages_key = pages_key_for_cache(selected_pages, total_pages)
    digest = md5_file_digest(source_path)
    sig = cache_signature_key(
        digest,
        render_dpi=render_dpi,
        vl_version=vl_version,
        pages_key=pages_key,
        skip_ppstructure=skip_pp,
        skip_chem_reocr=skip_chem,
    )
    cache_bucket = ocr_cache_bucket(Path(output_dir), sig)
    skip_cache_read = bool(state.get("ocr_skip_cached", False)) or _env_truthy(
        "KNOWMAT_OCR_SKIP_CACHED"
    )
    no_cache_write = _env_truthy("KNOWMAT_OCR_NO_CACHE_WRITE")

    if not skip_cache_read:
        cached = try_load_ocr_cache(cache_bucket)
        if cached is not None:
            logger.info("Loaded OCR result from cache: %s", cache_bucket)
            return _finalize_pdf_parse(
                source_path,
                parse_output_dir,
                save_intermediate,
                cached["extracted_text"],
                cached["metadata"],
                list(cached.get("ocr_items") or []),
            )

    try:
        extracted_text, metadata, _ocr_items = _extract_pdf_with_paddleocrvl(
            str(source_path),
            str(parse_output_dir),
            model_dir,
            save_intermediate=save_intermediate,
            page_indices=selected_pages,
        )
        result = _finalize_pdf_parse(
            source_path,
            parse_output_dir,
            save_intermediate,
            extracted_text,
            metadata,
            _ocr_items,
        )
        if not no_cache_write:
            try:
                save_ocr_cache(
                    cache_bucket,
                    {
                        "extracted_text": extracted_text,
                        "metadata": metadata,
                        "ocr_items": _ocr_items,
                    },
                )
            except OSError as exc:
                logger.warning("Could not write OCR cache to %s: %s", cache_bucket, exc)
        return result
    except Exception as exc:
        raise RuntimeError(f"Failed to parse PDF with PaddleOCR-VL: {str(exc)}") from exc
