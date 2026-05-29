"""Pipeline C: CLIP alignment + VLM figure description → enriched _final.md.

Public API
----------
enrich_paper_text(paper_id, raw_dir, vlm_workers=1) -> str | None
    Full enrichment: load raw OCR → CLIP align → VLM describe → inject into text.
"""

from __future__ import annotations

import json
import re
import threading as _threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Dict, List, Optional


# ── CLIP singleton ────────────────────────────────────────────────────────────

_CLIP_ALIGNER = None
_CLIP_ALIGNER_LOCK = _threading.Lock()


def _get_clip_aligner(top_k: int = 5):
    """Return a process-wide singleton CLIP aligner (thread-safe, lazy-loaded).

    Sharing one instance across all enrichment threads avoids loading the
    ~600 MB model N times when max-enrich-concurrent > 1.
    """
    global _CLIP_ALIGNER
    if _CLIP_ALIGNER is None:
        with _CLIP_ALIGNER_LOCK:
            if _CLIP_ALIGNER is None:
                from knowmat.image_text_alignment import ImageTextAligner
                _CLIP_ALIGNER = ImageTextAligner(
                    model="clip",
                    device="cpu",
                    top_k=top_k,
                    min_score=0.0,
                    batch_size=32,
                    caption_blend=0.0,
                    save_dataset=False,
                )
    return _CLIP_ALIGNER


# ── CLIP alignment ────────────────────────────────────────────────────────────

def run_clip_alignment(
    ocr_items: List[Dict],
    paper_id: str,
    paper_dir: str,
    top_k: int = 5,
) -> List[Dict]:
    """Run CLIP image-text alignment; return top-k related sentences per figure."""
    aligner = _get_clip_aligner(top_k)
    alignments = aligner.align(ocr_items, paper_id=paper_id, output_dir=paper_dir)

    results = []
    for alignment in alignments:
        sentences = [
            {"text": s.text, "score": s.score, "rank": i + 1}
            for i, s in enumerate(alignment.related_sentences[:top_k])
        ]
        results.append({
            "figure_num": alignment.figure_num,
            "image_path": alignment.image_path,
            "caption": alignment.caption,
            "related_sentences": sentences,
        })
    return results


# ── VLM description ───────────────────────────────────────────────────────────

def run_vlm_description(
    img_path: Path,
    caption: str,
    figure_num: str,
    related_sentences: List[str],
) -> Dict:
    """Call VLM with CLIP context to generate a figure description (Approach C)."""
    from knowmat.pdf.figure_describer import describe_figure_image_with_context

    if not img_path.is_file():
        return {"figure_num": figure_num, "description": "", "error": "image not found"}

    t0 = time.time()
    desc = describe_figure_image_with_context(
        img_path, caption=caption, related_sentences=related_sentences
    )
    return {
        "figure_num": figure_num,
        "description": desc,
        "elapsed_sec": round(time.time() - t0, 1),
    }


def _describe_figure_panels(
    all_paths: List[Path],
    caption: str,
    figure_num: str,
    related_sentences: List[str],
) -> str:
    """Describe all image panels of a figure.

    Single-panel figures: one VLM call.
    Multi-panel figures: one call per panel, labelled [Sub-image i/N].
    """
    valid = [p for p in all_paths if p.is_file()]
    if not valid:
        return ""

    if len(valid) == 1:
        return run_vlm_description(valid[0], caption, figure_num, related_sentences).get("description", "")

    panel_descs: List[str] = []
    for i, path in enumerate(valid, start=1):
        desc = run_vlm_description(path, caption, figure_num, related_sentences).get("description", "")
        if desc:
            panel_descs.append(f"[Sub-image {i}/{len(valid)}]: {desc}")
    return "\n\n".join(panel_descs)


# ── OCR item merging ──────────────────────────────────────────────────────────

def _merge_ocr_figures(ocr_items: List[Dict]) -> tuple:
    """Pair split image-file and caption items from PaddleOCR output.

    PaddleOCR emits each figure as two separate records:
      A) image item  — has image_path, empty figure_num and caption
      B) caption item — has figure_num + caption, empty image_path

    All A-items accumulated before a B-item belong to that figure
    (handles multi-panel figures).

    Returns:
      merged_ocr_items : pairs replaced by unified items with both
                         image_path and caption/figure_num
      figure_map       : {figure_num: {image_path, caption,
                                       all_image_paths, page}}
    """
    merged: List[Dict] = []
    figure_map: Dict[str, Dict] = {}
    pending_img_paths: List[str] = []

    for item in ocr_items:
        is_fig = item.get("typer") == "image" or item.get("block_label") == "figure"
        if not is_fig:
            merged.append(item)
            continue

        data = item.get("data", {})
        img_path = data.get("image_path", "")
        figure_num = data.get("figure_num", "")
        caption = data.get("caption", "")

        if img_path and not figure_num and not caption:
            pending_img_paths.append(img_path)
        elif figure_num or caption:
            all_paths = list(pending_img_paths)
            primary = all_paths[0] if all_paths else ""
            merged.append({
                "typer": "image",
                "data": {
                    "image_path": primary,
                    "caption": caption,
                    "figure_num": figure_num,
                    "_all_image_paths": all_paths,
                },
                "page": item.get("page"),
                "block_label": "figure",
            })
            if figure_num:
                figure_map[figure_num] = {
                    "figure_num": figure_num,
                    "caption": caption,
                    "image_path": primary,
                    "all_image_paths": all_paths,
                    "page": item.get("page"),
                }
            pending_img_paths = []
        else:
            merged.append(item)

    for orphan in pending_img_paths:
        merged.append({
            "typer": "image",
            "data": {"image_path": orphan, "caption": "", "figure_num": ""},
            "block_label": "figure",
        })

    return merged, figure_map


# ── Text injection ────────────────────────────────────────────────────────────

def inject_descriptions_into_text(
    paper_text: str,
    figures: List[Dict],
    descriptions: Dict[str, str],
) -> str:
    """Inject VLM figure descriptions into paper markdown text."""
    for item in figures:
        data = item.get("data", {})
        figure_num = data.get("figure_num", "")
        desc = descriptions.get(figure_num, "")
        if not desc or not figure_num:
            continue

        label = f"Figure {figure_num}"
        description_block = f"> [{label} AI Description]: {desc}\n\n"

        if description_block.strip() in paper_text:
            continue

        pattern = re.compile(
            r"((?:Fig\.?\s*|Figure\s*)" + re.escape(str(figure_num)) + r"[\s\.\:])",
            re.IGNORECASE,
        )
        match = pattern.search(paper_text)
        if match:
            line_start = paper_text.rfind("\n", 0, match.start()) + 1
            insert_pos = line_start if line_start < match.start() else match.start()
            paper_text = paper_text[:insert_pos] + description_block + paper_text[insert_pos:]
        else:
            paper_text = paper_text + "\n\n" + description_block

    return paper_text


def _clean_html(text: str) -> str:
    """Strip decorative HTML tags; preserve table and formula markup."""
    text = re.sub(r'</?div[^>]*>', '', text)
    text = re.sub(r'</?span[^>]*>', '', text)
    text = re.sub(r'</?p[^>]*>', '', text)
    text = re.sub(r'<br\s*/?>', '\n', text)
    text = re.sub(r'<img[^>]*/?>', '', text)
    text = re.sub(r'<a[^>]*>(.*?)</a>', r'\1', text)
    text = re.sub(r'</?sup>', '', text)
    text = re.sub(r'</?sub>', '', text)
    text = re.sub(r'\n{3,}', '\n\n', text)
    return text


# ── Main public function ──────────────────────────────────────────────────────

def enrich_paper_text(
    paper_id: str,
    raw_dir: Path,
    vlm_workers: int = 1,
) -> Optional[str]:
    """Full enrichment pipeline: load raw OCR → CLIP align → VLM describe → inject.

    Pipeline C steps:
      1. _merge_ocr_figures()  — pair split image-file + caption items so
                                  CLIP can embed the images and VLM has a path
      2. CLIP alignment        — find top-5 body sentences per figure
      3. VLM description       — generate AI description per figure (all panels)
      4. inject + clean        — insert '> [Figure N AI Description]: …'
                                  before each figure mention in the markdown

    Returns the enriched text, or None if source files are missing.
    """
    paper_dir = raw_dir / paper_id
    md_path = paper_dir / f"{paper_id}.md"
    json_path = paper_dir / f"{paper_id}.json"

    if not md_path.exists() or not json_path.exists():
        print(f"  [{paper_id}] Missing .md or .json in {paper_dir}")
        return None

    paper_text = md_path.read_text(encoding="utf-8")
    ocr_items = json.loads(json_path.read_text(encoding="utf-8"))

    merged_ocr_items, figure_map = _merge_ocr_figures(ocr_items)

    if not figure_map:
        print(f"  [{paper_id}] No named figures found, returning cleaned text")
        return _clean_html(paper_text)

    figures = [
        {
            "typer": "image",
            "data": {
                "image_path": fd["image_path"],
                "caption": fd["caption"],
                "figure_num": fd["figure_num"],
                "_all_image_paths": fd["all_image_paths"],
            },
            "page": fd.get("page"),
            "block_label": "figure",
        }
        for fd in figure_map.values()
    ]

    print(f"  [{paper_id}] CLIP alignment ({len(figures)} named figures)...")
    try:
        alignment_results = run_clip_alignment(merged_ocr_items, paper_id, str(paper_dir))
    except Exception as exc:
        print(f"  [{paper_id}] CLIP alignment failed: {exc}, proceeding without context")
        alignment_results = []

    alignment_by_fig: Dict[str, List[str]] = {}
    for ar in alignment_results:
        sentences = [s["text"] for s in ar.get("related_sentences", [])[:5]]
        if ar.get("figure_num"):
            alignment_by_fig[ar["figure_num"]] = sentences
            print(
                f"  [{paper_id}] CLIP fig {ar['figure_num']}: "
                f"{len(sentences)} related sentences"
            )

    print(f"  [{paper_id}] VLM descriptions (workers={vlm_workers})...")
    vlm_tasks: List[tuple] = []
    for fig in figures:
        data = fig.get("data", {})
        all_paths = [Path(p) for p in data.get("_all_image_paths", []) if p]
        if not all_paths:
            img_str = data.get("image_path", "")
            all_paths = [Path(img_str)] if img_str else []
        caption = data.get("caption", "")
        figure_num = data.get("figure_num", "")
        related = alignment_by_fig.get(figure_num, [])
        primary = all_paths[0] if all_paths else Path("")
        vlm_tasks.append((primary, caption, figure_num, related, all_paths))

    descriptions: Dict[str, str] = {}

    def _run_task(task: tuple) -> tuple:
        primary, caption, figure_num, related, all_paths = task
        desc = _describe_figure_panels(all_paths, caption, figure_num, related)
        return figure_num, desc

    if vlm_workers <= 1:
        for task in vlm_tasks:
            fnum, desc = _run_task(task)
            if desc and fnum:
                descriptions[fnum] = desc
    else:
        with ThreadPoolExecutor(max_workers=vlm_workers) as pool:
            futures = {pool.submit(_run_task, task): task[2] for task in vlm_tasks}
            for future in as_completed(futures):
                fnum_key = futures[future]
                try:
                    fnum, desc = future.result()
                    if desc and fnum:
                        descriptions[fnum] = desc
                except Exception as exc:
                    print(f"  [{paper_id}] VLM failed for fig {fnum_key}: {exc}")

    for attempt in range(1, 4):
        failed_tasks = [
            task for task in vlm_tasks
            if task[2]
            and task[2] not in descriptions
            and any(p.is_file() for p in task[4])
        ]
        if not failed_tasks:
            break
        delay = 5 * (2 ** (attempt - 1))
        print(
            f"  [{paper_id}] Retry {attempt}/3: "
            f"{len(failed_tasks)} figures, delay={delay}s..."
        )
        for task in failed_tasks:
            time.sleep(delay)
            try:
                fnum, desc = _run_task(task)
                if desc and fnum:
                    descriptions[fnum] = desc
            except Exception as exc:
                print(f"  [{paper_id}] VLM retry failed for fig {task[2]}: {exc}")

    print(f"  [{paper_id}] Got {len(descriptions)}/{len(vlm_tasks)} descriptions")

    enriched_text = inject_descriptions_into_text(paper_text, figures, descriptions)
    return _clean_html(enriched_text)
