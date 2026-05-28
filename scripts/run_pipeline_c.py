#!/usr/bin/env python3
"""KnowMat 2.0 主抽取流水线 (方案C: VLM+CLIP enrichment + LLM extraction).

支持两种模式:
  1. 从 data/raw/ 全流程: CLIP对齐 → VLM图片描述(2048 tokens) → 文本enrichment → LLM抽取
  2. 从已有的 _final.md 文件直接抽取 (--extraction-only, 跳过VLM)

Usage:
    # 全流程: 从data/raw重新跑VLM+抽取 (默认)
    python scripts/run_pipeline_c.py --workers 4
    python scripts/run_pipeline_c.py --only 1-s2.0-S100503022300 3-2016-acta_牛津-Reed组

    # 只重跑LLM抽取 (跳过VLM, 使用已有_final.md)
    python scripts/run_pipeline_c.py --extraction-only --workers 4

    # 只对比不重新跑
    python scripts/run_pipeline_c.py --analyze-only
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_PROJECT_ROOT / "src"))

from knowmat.env_loader import load_project_dotenv

load_project_dotenv(override=False)

# ─── Directories ───────────────────────────────────────────────────────────────
RAW_DIR = _PROJECT_ROOT / "data" / "raw"
OUTPUT_DIR = _PROJECT_ROOT / "data" / "extraction_output"
BASELINE_DIR = _PROJECT_ROOT / "516反馈" / "export_v10.8_75papers"
LEGACY_ENRICHED_DIR = _PROJECT_ROOT / "data" / "comparison_results" / "extraction_C"


# ─── VLM + CLIP Enrichment ────────────────────────────────────────────────────

def _get_clip_aligner(top_k: int = 5):
    """Get shared CLIP aligner instance."""
    from knowmat.image_text_alignment import ImageTextAligner
    return ImageTextAligner(
        model="clip",
        device="cpu",
        top_k=top_k,
        min_score=0.0,
        batch_size=32,
        caption_blend=0.0,
        save_dataset=False,
    )


def run_clip_alignment(ocr_items: List[Dict], paper_id: str, paper_dir: str, top_k: int = 5) -> List[Dict]:
    """Run CLIP image-text alignment to find related sentences for each figure."""
    aligner = _get_clip_aligner(top_k)
    alignments = aligner.align(ocr_items, paper_id=paper_id, output_dir=paper_dir)

    results = []
    for alignment in alignments:
        sentences = [{"text": s.text, "score": s.score, "rank": i + 1}
                     for i, s in enumerate(alignment.related_sentences[:top_k])]
        results.append({
            "figure_num": alignment.figure_num,
            "image_path": alignment.image_path,
            "caption": alignment.caption,
            "related_sentences": sentences,
        })
    return results


def run_vlm_description(
    img_path: Path,
    caption: str,
    figure_num: str,
    related_sentences: List[str],
) -> Dict:
    """Run VLM with CLIP context to generate figure description (Approach C)."""
    from knowmat.pdf.figure_describer import describe_figure_image_with_context

    if not img_path.is_file():
        return {"figure_num": figure_num, "description": "", "error": "image not found"}

    t0 = time.time()
    desc = describe_figure_image_with_context(
        img_path, caption=caption, related_sentences=related_sentences
    )
    elapsed = time.time() - t0
    return {
        "figure_num": figure_num,
        "description": desc,
        "elapsed_sec": round(elapsed, 1),
    }


def inject_descriptions_into_text(
    paper_text: str,
    figures: List[Dict],
    descriptions: Dict[str, str],
) -> str:
    """Inject VLM figure descriptions into paper text."""
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
    """Strip decorative HTML tags but preserve table and formula markup."""
    # Remove div/span/p tags (alignment wrappers, empty containers)
    text = re.sub(r'</?div[^>]*>', '', text)
    text = re.sub(r'</?span[^>]*>', '', text)
    text = re.sub(r'</?p[^>]*>', '', text)
    # Remove <br> / <br/>
    text = re.sub(r'<br\s*/?>', '\n', text)
    # Remove <img> tags (images are handled via AI Description)
    text = re.sub(r'<img[^>]*/?>', '', text)
    # Remove <a> tags but keep inner text
    text = re.sub(r'<a[^>]*>(.*?)</a>', r'\1', text)
    # Remove <sup>/<sub> tags but keep content (formulas use $ notation)
    text = re.sub(r'</?sup>', '', text)
    text = re.sub(r'</?sub>', '', text)
    # Remove empty lines caused by removed tags
    text = re.sub(r'\n{3,}', '\n\n', text)
    return text


def enrich_paper_text(
    paper_id: str,
    raw_dir: Path,
    vlm_workers: int = 2,
) -> Optional[str]:
    """Full enrichment pipeline: load raw OCR → CLIP align → VLM describe → inject into text.

    Returns the enriched paper text, or None on failure.
    """
    paper_dir = raw_dir / paper_id
    md_path = paper_dir / f"{paper_id}.md"
    json_path = paper_dir / f"{paper_id}.json"

    if not md_path.exists() or not json_path.exists():
        print(f"  [{paper_id}] Missing .md or .json in {paper_dir}")
        return None

    paper_text = md_path.read_text(encoding="utf-8")
    ocr_items = json.loads(json_path.read_text(encoding="utf-8"))

    # Find figure items
    figures = [item for item in ocr_items
               if item.get("typer") == "image" or item.get("block_label") == "figure"]
    # Deduplicate by figure_num (keep first occurrence with a valid figure_num)
    seen_figs = set()
    unique_figures = []
    for fig in figures:
        fnum = fig.get("data", {}).get("figure_num", "")
        if fnum and fnum not in seen_figs:
            seen_figs.add(fnum)
            unique_figures.append(fig)
        elif not fnum:
            unique_figures.append(fig)
    figures = unique_figures

    if not figures:
        print(f"  [{paper_id}] No figures found, returning cleaned text")
        return _clean_html(paper_text)

    # Step 1: CLIP alignment
    print(f"  [{paper_id}] CLIP alignment ({len(figures)} figures)...")
    try:
        alignment_results = run_clip_alignment(ocr_items, paper_id, str(paper_dir))
    except Exception as exc:
        print(f"  [{paper_id}] CLIP alignment failed: {exc}, proceeding without context")
        alignment_results = []

    # Build alignment lookup
    alignment_by_fig: Dict[str, List[str]] = {}
    for ar in alignment_results:
        sentences = [s["text"] for s in ar.get("related_sentences", [])[:5]]
        if ar.get("figure_num"):
            alignment_by_fig[ar["figure_num"]] = sentences

    # Step 2: VLM descriptions (parallel)
    print(f"  [{paper_id}] VLM descriptions (workers={vlm_workers})...")
    vlm_tasks = []
    for fig in figures:
        data = fig.get("data", {})
        img_path = Path(data.get("image_path", ""))
        caption = data.get("caption", "")
        figure_num = data.get("figure_num", "")
        related = alignment_by_fig.get(figure_num, [])
        vlm_tasks.append((img_path, caption, figure_num, related))

    descriptions: Dict[str, str] = {}
    if vlm_workers <= 1:
        for img_path, caption, figure_num, related in vlm_tasks:
            r = run_vlm_description(img_path, caption, figure_num, related)
            if r.get("description"):
                descriptions[r["figure_num"]] = r["description"]
    else:
        with ThreadPoolExecutor(max_workers=vlm_workers) as pool:
            futures = {
                pool.submit(run_vlm_description, img_path, caption, figure_num, related): figure_num
                for img_path, caption, figure_num, related in vlm_tasks
            }
            for future in as_completed(futures):
                try:
                    r = future.result()
                    if r.get("description") and r.get("figure_num"):
                        descriptions[r["figure_num"]] = r["description"]
                except Exception as exc:
                    fnum = futures[future]
                    print(f"  [{paper_id}] VLM failed for fig {fnum}: {exc}")

    # Retry round: serial retry for figures that got empty descriptions
    failed_tasks = [
        (img_path, caption, figure_num, related)
        for img_path, caption, figure_num, related in vlm_tasks
        if figure_num and figure_num not in descriptions and img_path.is_file()
    ]
    if failed_tasks:
        print(f"  [{paper_id}] Retrying {len(failed_tasks)} failed VLM descriptions (serial, 5s delay)...")
        for img_path, caption, figure_num, related in failed_tasks:
            time.sleep(5)
            r = run_vlm_description(img_path, caption, figure_num, related)
            if r.get("description") and r.get("figure_num"):
                descriptions[r["figure_num"]] = r["description"]

    print(f"  [{paper_id}] Got {len(descriptions)}/{len(vlm_tasks)} descriptions")

    # Step 3: Inject into text + clean HTML
    enriched_text = inject_descriptions_into_text(paper_text, figures, descriptions)
    enriched_text = _clean_html(enriched_text)

    return enriched_text


# ─── Core Extraction ──────────────────────────────────────────────────────────

def extract_single_paper(paper_text: str, paper_id: str) -> Dict[str, Any]:
    """Run LLM extraction on enriched paper text."""
    from knowmat.extractors import extraction_extractor, CompositionList
    from knowmat.prompt_generator import generate_system_prompt, generate_user_prompt

    system_prompt = generate_system_prompt(routing_supplements="")
    user_prompt = generate_user_prompt(paper_text)

    input_chars = len(system_prompt) + len(user_prompt)
    print(f"  [{paper_id}] LLM extraction starting (~{input_chars // 3} tokens)...")

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
        {"role": "user", "content": "Provide your response using the tool."},
    ]

    t0 = time.time()
    try:
        result = extraction_extractor.invoke({"messages": messages})
    except Exception as exc:
        print(f"  [{paper_id}] Structured extraction failed ({time.time() - t0:.1f}s): {exc}")
        full_prompt = system_prompt + "\n\n" + user_prompt + "\n\nProvide your response using the tool."
        try:
            result = extraction_extractor.invoke(full_prompt)
        except Exception as exc2:
            print(f"  [{paper_id}] Fallback also failed ({time.time() - t0:.1f}s): {exc2}")
            return {"compositions": []}

    elapsed = time.time() - t0
    responses = (result or {}).get("responses") or []
    if not responses:
        print(f"  [{paper_id}] LLM returned no responses ({elapsed:.1f}s)")
        return {"compositions": []}

    print(f"  [{paper_id}] LLM extraction done ({elapsed:.1f}s)")
    response = responses[0]
    if isinstance(response, CompositionList):
        return json.loads(response.model_dump_json())
    return response


def convert_to_target_schema(raw_data: Dict[str, Any], paper_text: str, paper_id: str = "") -> Dict[str, Any]:
    """Convert CompositionList format to target schema."""
    from knowmat.schema_converter import SchemaConverter
    converter = SchemaConverter()
    return converter.convert(raw_data, source_path=paper_id, paper_text=paper_text)


# ─── Baseline Loading ─────────────────────────────────────────────────────────

def load_baseline_map() -> Dict[str, Path]:
    bl_map: Dict[str, Path] = {}
    manifest_path = BASELINE_DIR / "_manifest.json"
    if manifest_path.exists():
        manifest = json.loads(manifest_path.read_bytes().decode("utf-8-sig"))
        for entry in manifest:
            pid = entry.get("paper_id") or entry.get("paper_base", "")
            group = entry.get("group", "")
            if pid and group:
                candidate = BASELINE_DIR / group / pid / "extracted.json"
                if candidate.exists():
                    bl_map[pid] = candidate
    return bl_map


# ─── Metrics ──────────────────────────────────────────────────────────────────

def get_items(data: Dict) -> List[Dict]:
    if not data:
        return []
    return data.get("items") or []


def count_properties(items: List[Dict]) -> int:
    total = 0
    for it in items:
        ed = it.get("Extracted_Data") or {}
        total += len(ed.get("Properties") or [])
        total += len(it.get("Properties_Info") or [])
    return total


def fuzzy_match_sample_ids(pred_ids: set, gold_ids: set) -> int:
    def normalize(s):
        return re.sub(r'[/_\-\s,]+', '_', s.lower().strip()).strip('_')

    pred_norm = {normalize(p): p for p in pred_ids}
    gold_norm = {normalize(g): g for g in gold_ids}

    matched = 0
    used_gold = set()
    for pn in pred_norm:
        for gn in gold_norm:
            if gn in used_gold:
                continue
            if pn == gn or pn in gn or gn in pn:
                matched += 1
                used_gold.add(gn)
                break
    return matched


# ─── Paper Discovery ──────────────────────────────────────────────────────────

def discover_papers_raw(raw_dir: Path, only: Optional[List[str]] = None) -> List[str]:
    """Find papers in data/raw/ that have .md + .json."""
    paper_ids = []
    if not raw_dir.exists():
        return paper_ids
    for d in sorted(raw_dir.iterdir()):
        if d.is_dir():
            md = d / f"{d.name}.md"
            js = d / f"{d.name}.json"
            if md.exists() and js.exists():
                paper_ids.append(d.name)
    if only:
        paper_ids = [p for p in paper_ids if p in only]
    return paper_ids


def discover_papers_enriched(source_dir: Path, only: Optional[List[str]] = None) -> List[str]:
    """Find papers with existing _final.md files."""
    paper_ids = []
    if not source_dir.exists():
        return paper_ids
    for d in sorted(source_dir.iterdir()):
        if d.is_dir():
            md = d / f"{d.name}_final.md"
            if md.exists():
                paper_ids.append(d.name)
    if only:
        paper_ids = [p for p in paper_ids if p in only]
    return paper_ids


# ─── Process Single Paper ─────────────────────────────────────────────────────

def process_paper_full(
    pid: str,
    raw_dir: Path,
    output_dir: Path,
    vlm_workers: int = 2,
    skip_existing: bool = False,
    retry_empty: bool = False,
) -> Optional[Dict[str, Any]]:
    """Full pipeline: VLM enrichment + LLM extraction."""
    out_dir = output_dir / pid
    out_json = out_dir / f"{pid}_extraction.json"

    if skip_existing and out_json.exists():
        try:
            data = json.loads(out_json.read_text(encoding="utf-8"))
            items = data.get("items") or []
            if not retry_empty or len(items) > 0:
                return {"paper_id": pid, "data": data, "skipped": True}
        except Exception:
            pass

    t0 = time.time()

    # Step 1: VLM+CLIP enrichment
    enriched_text = enrich_paper_text(pid, raw_dir, vlm_workers=vlm_workers)
    if enriched_text is None:
        return None

    # Save enriched text
    out_dir.mkdir(parents=True, exist_ok=True)
    final_md_path = out_dir / f"{pid}_final.md"
    final_md_path.write_text(enriched_text, encoding="utf-8")

    # Step 2: LLM extraction
    raw_data = extract_single_paper(enriched_text, pid)
    elapsed = time.time() - t0

    # Step 3: Schema conversion
    try:
        converted = convert_to_target_schema(raw_data, enriched_text, paper_id=pid)
    except Exception as exc:
        print(f"  [{pid}] Schema conversion failed: {exc}")
        converted = {"items": []}

    # Save results
    with open(out_json, "w", encoding="utf-8") as f:
        json.dump(converted, f, ensure_ascii=False, indent=2)

    raw_path = out_dir / f"{pid}_raw.json"
    with open(raw_path, "w", encoding="utf-8") as f:
        json.dump(raw_data, f, ensure_ascii=False, indent=2)

    n_items = len(get_items(converted))
    n_props = count_properties(get_items(converted))
    print(f"  [{pid}] Done in {elapsed:.1f}s: {n_items} items, {n_props} props")

    return {"paper_id": pid, "data": converted, "skipped": False, "elapsed": elapsed}


def process_paper_extraction_only(
    pid: str,
    source_dir: Path,
    output_dir: Path,
    skip_existing: bool = False,
    retry_empty: bool = False,
) -> Optional[Dict[str, Any]]:
    """Extraction-only: read existing _final.md, run LLM extraction."""
    out_dir = output_dir / pid
    out_json = out_dir / f"{pid}_extraction.json"

    if skip_existing and out_json.exists():
        try:
            data = json.loads(out_json.read_text(encoding="utf-8"))
            items = data.get("items") or []
            if not retry_empty or len(items) > 0:
                return {"paper_id": pid, "data": data, "skipped": True}
        except Exception:
            pass

    md_path = source_dir / pid / f"{pid}_final.md"
    if not md_path.exists():
        print(f"  [{pid}] _final.md not found")
        return None

    paper_text = md_path.read_text(encoding="utf-8")

    t0 = time.time()
    raw_data = extract_single_paper(paper_text, pid)
    elapsed = time.time() - t0

    try:
        converted = convert_to_target_schema(raw_data, paper_text, paper_id=pid)
    except Exception as exc:
        print(f"  [{pid}] Schema conversion failed: {exc}")
        converted = {"items": []}

    out_dir.mkdir(parents=True, exist_ok=True)
    with open(out_json, "w", encoding="utf-8") as f:
        json.dump(converted, f, ensure_ascii=False, indent=2)

    raw_path = out_dir / f"{pid}_raw.json"
    with open(raw_path, "w", encoding="utf-8") as f:
        json.dump(raw_data, f, ensure_ascii=False, indent=2)

    n_items = len(get_items(converted))
    n_props = count_properties(get_items(converted))
    print(f"  [{pid}] Done in {elapsed:.1f}s: {n_items} items, {n_props} props")

    return {"paper_id": pid, "data": converted, "skipped": False, "elapsed": elapsed}


# ─── Analysis Report ──────────────────────────────────────────────────────────

def generate_report(results: List[Dict], bl_map: Dict[str, Path], output_dir: Path, failed: List[str]):
    """Generate comparison report against baseline."""
    print(f"\n{'='*110}")
    print("KnowMat 2.0 Pipeline C — Extraction Report")
    print(f"{'='*110}")
    print(f"{'Paper':<35} │ {'C':>5} {'BL':>5} {'Δ':>4} │ {'C-Props':>7} {'BL-Props':>8} │ {'ID-Match':>8} │ {'Status'}")
    print(f"{'─'*35}─┼{'─'*16}─┼{'─'*17}─┼{'─'*9}─┼{'─'*8}")

    total_c_items = 0
    total_bl_items = 0
    total_c_props = 0
    total_bl_props = 0
    total_matches = 0
    total_gold = 0
    papers_better = 0
    papers_worse = 0
    papers_equal = 0

    for r in sorted(results, key=lambda x: x["paper_id"]):
        pid = r["paper_id"]
        c_data = r["data"]
        c_items = get_items(c_data)
        c_n = len(c_items)
        c_props = count_properties(c_items)

        bl_path = bl_map.get(pid)
        if bl_path:
            bl_data = json.loads(bl_path.read_text(encoding="utf-8"))
            bl_items = bl_data.get("items") or []
            bl_n = len(bl_items)
            bl_props = count_properties(bl_items)
        else:
            bl_items = []
            bl_n = 0
            bl_props = 0

        c_ids = {it.get("Sample_ID", "") for it in c_items if it.get("Sample_ID")}
        bl_ids = {it.get("Sample_ID", "") for it in bl_items if it.get("Sample_ID")}
        matches = fuzzy_match_sample_ids(c_ids, bl_ids) if bl_ids else 0
        match_str = f"{matches}/{len(bl_ids)}" if bl_ids else "N/A"

        delta = c_n - bl_n
        if delta > 0:
            status = "↑"
            papers_better += 1
        elif delta < 0:
            status = "↓"
            papers_worse += 1
        else:
            status = "="
            papers_equal += 1

        total_c_items += c_n
        total_bl_items += bl_n
        total_c_props += c_props
        total_bl_props += bl_props
        total_matches += matches
        total_gold += len(bl_ids)

        label = pid[:33]
        print(f"  {label:<33} │ {c_n:>5} {bl_n:>5} {delta:>+4} │ {c_props:>7} {bl_props:>8} │ {match_str:>8} │ {status}")

    print(f"{'─'*35}─┼{'─'*16}─┼{'─'*17}─┼{'─'*9}─┼{'─'*8}")
    total_delta = total_c_items - total_bl_items
    overall_match = f"{total_matches}/{total_gold}" if total_gold else "N/A"
    print(f"  {'TOTAL':<33} │ {total_c_items:>5} {total_bl_items:>5} {total_delta:>+4} │ {total_c_props:>7} {total_bl_props:>8} │ {overall_match:>8} │")

    print(f"\n{'─'*60}")
    print("Summary Metrics:")
    print(f"{'─'*60}")
    print(f"  Papers processed:    {len(results)}")
    print(f"  Papers failed:       {len(failed)}")
    if total_gold > 0:
        recall = total_matches / total_gold
        print(f"  Item ID recall:      {recall:.1%} ({total_matches}/{total_gold})")
    item_ratio = total_c_items / total_bl_items if total_bl_items else 0
    print(f"  Item ratio (C/BL):   {item_ratio:.2f} (target ≥ 0.9)")
    prop_ratio = total_c_props / total_bl_props if total_bl_props else 0
    print(f"  Prop ratio (C/BL):   {prop_ratio:.2f}")
    print(f"  Papers C > BL:       {papers_better}")
    print(f"  Papers C = BL:       {papers_equal}")
    print(f"  Papers C < BL:       {papers_worse}")

    if failed:
        print(f"\n  Failed: {', '.join(failed[:10])}")
        if len(failed) > 10:
            print(f"          ... and {len(failed)-10} more")

    summary = {
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "total_papers": len(results),
        "failed_papers": failed,
        "metrics": {
            "C_total_items": total_c_items,
            "BL_total_items": total_bl_items,
            "C_total_properties": total_c_props,
            "BL_total_properties": total_bl_props,
            "item_ratio": round(item_ratio, 3),
            "property_ratio": round(prop_ratio, 3),
            "item_id_matches": total_matches,
            "item_id_gold": total_gold,
            "item_id_recall": round(total_matches / total_gold, 3) if total_gold else None,
        },
        "comparison": {
            "papers_better": papers_better,
            "papers_equal": papers_equal,
            "papers_worse": papers_worse,
        },
    }
    summary_path = output_dir / "pipeline_report.json"
    with open(summary_path, "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)
    print(f"\n  Report saved: {summary_path}")


# ─── Main ─────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="KnowMat 2.0 Pipeline C — 主抽取流水线",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # 全流程 (从 data/raw/ 重新跑 VLM + 抽取)
  python scripts/run_pipeline_c.py --workers 4

  # 只跑指定论文
  python scripts/run_pipeline_c.py --only 1-s2.0-S100503022300

  # 只重跑LLM抽取 (复用已有VLM描述)
  python scripts/run_pipeline_c.py --extraction-only --workers 4

  # 跳过已有结果, 只重跑失败的
  python scripts/run_pipeline_c.py --skip-existing --retry-empty

  # 只看对比报告
  python scripts/run_pipeline_c.py --analyze-only
""",
    )
    parser.add_argument("--workers", type=int, default=1, help="并发数 (VLM调用 & LLM抽取)")
    parser.add_argument("--vlm-workers", type=int, default=2, help="单篇论文内VLM并发数")
    parser.add_argument("--only", nargs="+", default=None, help="只处理指定论文ID")
    parser.add_argument("--skip-existing", action="store_true", help="跳过已有结果的论文")
    parser.add_argument("--retry-empty", action="store_true", help="重新处理之前结果为0的论文")
    parser.add_argument("--extraction-only", action="store_true",
                        help="只跑LLM抽取, 跳过VLM (需要已有_final.md)")
    parser.add_argument("--enrich-only", action="store_true",
                        help="只跑CLIP+VLM图片描述生成_final.md, 不跑LLM抽取")
    parser.add_argument("--analyze-only", action="store_true", help="只生成对比报告, 不重新处理")
    parser.add_argument("--raw-dir", default=None, help="原始OCR数据目录 (默认: data/raw)")
    parser.add_argument("--source-dir", default=None,
                        help="enriched文本源目录, 用于--extraction-only (默认: data/comparison_results/extraction_C)")
    parser.add_argument("--output-dir", default=None, help="输出目录 (默认: data/extraction_output)")
    args = parser.parse_args()

    raw_dir = Path(args.raw_dir) if args.raw_dir else RAW_DIR
    source_dir = Path(args.source_dir) if args.source_dir else LEGACY_ENRICHED_DIR
    output_dir = Path(args.output_dir) if args.output_dir else OUTPUT_DIR
    output_dir.mkdir(parents=True, exist_ok=True)

    # ── Load baseline ──
    bl_map = load_baseline_map()

    # ── Analyze-only mode ──
    if args.analyze_only:
        paper_ids = discover_papers_enriched(output_dir, only=args.only)
        if not paper_ids:
            paper_ids = discover_papers_raw(raw_dir, only=args.only)
        results = []
        for pid in paper_ids:
            out_json = output_dir / pid / f"{pid}_extraction.json"
            if out_json.exists():
                data = json.loads(out_json.read_text(encoding="utf-8"))
                results.append({"paper_id": pid, "data": data, "skipped": True})
        generate_report(results, bl_map, output_dir, failed=[])
        return

    # ── Extraction-only mode ──
    if args.extraction_only:
        paper_ids = discover_papers_enriched(source_dir, only=args.only)
        if not paper_ids:
            print(f"No papers with _final.md found in {source_dir}")
            sys.exit(1)

        print(f"KnowMat 2.0 Pipeline C — Extraction Only")
        print(f"Source: {source_dir}")
        print(f"Output: {output_dir}")
        print(f"Papers: {len(paper_ids)}")
        print(f"Baseline: {len(bl_map)} papers")
        print()

        results = []
        failed = []

        if args.workers <= 1:
            for pid in paper_ids:
                try:
                    r = process_paper_extraction_only(pid, source_dir, output_dir, args.skip_existing, args.retry_empty)
                    if r:
                        results.append(r)
                except Exception as exc:
                    print(f"  [{pid}] FAILED: {exc}")
                    failed.append(pid)
        else:
            with ThreadPoolExecutor(max_workers=args.workers) as pool:
                futures = {
                    pool.submit(process_paper_extraction_only, pid, source_dir, output_dir,
                                args.skip_existing, args.retry_empty): pid
                    for pid in paper_ids
                }
                for future in as_completed(futures):
                    pid = futures[future]
                    try:
                        r = future.result()
                        if r:
                            results.append(r)
                    except Exception as exc:
                        print(f"  [{pid}] FAILED: {exc}")
                        failed.append(pid)

        generate_report(results, bl_map, output_dir, failed)
        return

    # ── Enrich-only mode (CLIP + VLM, no LLM extraction) ──
    if args.enrich_only:
        paper_ids = discover_papers_raw(raw_dir, only=args.only)
        if not paper_ids:
            print(f"No papers found in {raw_dir}")
            sys.exit(1)

        print(f"KnowMat 2.0 Pipeline C — Enrich Only (CLIP + VLM)")
        print(f"Raw source: {raw_dir}")
        print(f"Output: {output_dir}")
        print(f"Papers: {len(paper_ids)}")
        print(f"VLM workers/paper: {args.vlm_workers}")
        print()

        done = 0
        failed = []
        for pid in paper_ids:
            try:
                out_dir = output_dir / pid
                final_md_path = out_dir / f"{pid}_final.md"
                if args.skip_existing and final_md_path.exists():
                    done += 1
                    continue
                enriched_text = enrich_paper_text(pid, raw_dir, vlm_workers=args.vlm_workers)
                if enriched_text:
                    out_dir.mkdir(parents=True, exist_ok=True)
                    final_md_path.write_text(enriched_text, encoding="utf-8")
                    done += 1
                else:
                    failed.append(pid)
            except Exception as exc:
                print(f"  [{pid}] FAILED: {exc}")
                failed.append(pid)

        print(f"\nEnrichment complete: {done}/{len(paper_ids)} papers")
        if failed:
            print(f"Failed ({len(failed)}): {', '.join(failed[:10])}")
        return

    # ── Full pipeline mode (from data/raw/) ──
    paper_ids = discover_papers_raw(raw_dir, only=args.only)
    if not paper_ids:
        print(f"No papers found in {raw_dir}")
        sys.exit(1)

    print(f"KnowMat 2.0 Pipeline C — Full Pipeline (VLM+CLIP → LLM)")
    print(f"Raw source: {raw_dir}")
    print(f"Output: {output_dir}")
    print(f"Papers: {len(paper_ids)}")
    print(f"VLM workers/paper: {args.vlm_workers}")
    print(f"Baseline: {len(bl_map)} papers")
    print()

    results = []
    failed = []

    # Full pipeline runs sequentially per paper (VLM is parallelized within each paper)
    for pid in paper_ids:
        try:
            r = process_paper_full(
                pid, raw_dir, output_dir,
                vlm_workers=args.vlm_workers,
                skip_existing=args.skip_existing,
                retry_empty=args.retry_empty,
            )
            if r:
                results.append(r)
        except Exception as exc:
            print(f"  [{pid}] FAILED: {exc}")
            failed.append(pid)

    generate_report(results, bl_map, output_dir, failed)


if __name__ == "__main__":
    main()
