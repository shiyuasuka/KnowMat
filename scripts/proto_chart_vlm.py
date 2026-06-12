#!/usr/bin/env python3
"""原型:折线图 → CSV 数字化 (VLM-digitized) 的端到端手测脚本。

流程:
  1. 用 PaddleOCR API 跑一篇 PDF → 落地 images/ 裁剪图 + {stem}.json
  2. 按 image_path 里的 chart_box / image_box token 做第一级分流
  3. 在 chart 裁剪图上调 VLM(ernie-4.5-turbo-vl):
       a) 分类闸门:是否是简单可数字化的折线/散点图?
       b) 若是 → 输出 CSV
  4. 打印 '> [Figure N VLM-digitized]:' 注入块,供人工评审

只读 + 写 data/raw/<stem>/,不改任何管线代码。
"""

from __future__ import annotations

import base64
import json
import os
import re
import sys
from pathlib import Path

# 让脚本能 import knowmat
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from knowmat.env_loader import load_project_dotenv  # noqa: E402

load_project_dotenv()


def run_ocr(pdf_path: Path, out_root: Path) -> tuple[Path, list[dict]]:
    """跑 PaddleOCR API,落地 md+json+images,返回 (json_path, ocr_items)。

    若已有缓存的 {stem}.json 则直接复用,避免重复消耗 API 额度。
    """
    from knowmat.pdf.paddleocr_api_client import PaddleOCRAPIClient
    from knowmat.pdf.paddleocr_api_result_converter import convert_paddleocr_api_to_knowmat

    stem = pdf_path.stem
    paper_dir = out_root / stem
    json_path = paper_dir / f"{stem}.json"
    if json_path.is_file():
        print(f"[OCR] 复用缓存: {json_path}")
        return json_path, json.loads(json_path.read_text("utf-8"))

    token = os.getenv("PADDLEOCR_API_TOKEN", "").strip()
    base_url = os.getenv("PADDLEOCR_API_URL", "").strip() or None
    if not token:
        raise SystemExit("缺少 PADDLEOCR_API_TOKEN")

    images_dir = paper_dir / "images"
    images_dir.mkdir(parents=True, exist_ok=True)

    client = PaddleOCRAPIClient(token, base_url) if base_url else PaddleOCRAPIClient(token)
    print(f"[OCR] 提交 {pdf_path.name} (chart 识别保持默认 off,我们自己用 VLM 数字化)...")
    job = client.upload_and_parse(pdf_path, model="PaddleOCR-VL-1.5", timeout_sec=600)
    jsonl_url = job.get("resultUrl", {}).get("jsonUrl", "")
    pages = client.download_jsonl(jsonl_url)

    md_text, _meta, ocr_items = convert_paddleocr_api_to_knowmat(pages, str(pdf_path), images_dir)
    (paper_dir / f"{stem}.md").write_text(md_text, encoding="utf-8")
    json_path.write_text(json.dumps(ocr_items, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[OCR] 完成: {len(ocr_items)} items → {json_path}")
    return json_path, ocr_items


def triage(ocr_items: list[dict]) -> dict[str, list[dict]]:
    """第一级分流:按 image_path 里的 box token 分桶。"""
    buckets = {"chart": [], "image": [], "other": []}
    for item in ocr_items:
        data = item.get("data") or {}
        path = str(data.get("image_path") or "")
        if not path:
            continue
        name = Path(path).name
        if "chart_box" in name:
            buckets["chart"].append(item)
        elif "image_box" in name:
            buckets["image"].append(item)
        else:
            buckets["other"].append(item)
    return buckets


# ── 第二级:VLM 分类闸门 + CSV 数字化 ──────────────────────────────────

_VLM_PROMPT = """You are a scientific chart reader. Look at this cropped figure image.

STEP 1 — Classify. Output exactly one of these enum values for "type":
  line      : line chart / scatter plot with continuous numeric X and Y axes
  bar       : bar / column chart or histogram (categorical or binned X axis)
  xrd       : diffraction pattern / spectrum (intensity vs 2-theta, sharp peaks)
  micrograph: SEM/TEM/optical image, photo, schematic, or map (NOT a data plot)
  other     : phase diagram, flowchart, unreadable, or none of the above

STEP 2 — Read the chart according to its type. Two DIFFERENT contracts:

  IF type == "bar":
    Digitize to CSV (these have discrete, directly-readable values).
    - One CSV table, first row = header.
    - Encode variable + unit in each header (e.g. "Lamellar_Thickness_nm").
    - Each series = its own column; preserve series labels.
    - One row per bar / bin. Read the bar heights off the Y axis.
    Put the CSV in "csv". Leave "line_summary" empty.

  IF type == "line":
    DO NOT output a per-point CSV. Reading exact point coordinates off a
    continuous curve produces fabricated, evenly-spaced, over-smoothed data.
    Instead extract ONLY what is reliably visible, into "line_summary":
    - x_axis / y_axis : variable + unit (e.g. "Temperature (C)")
    - series          : list of curve labels (e.g. ["theta=0", "theta=45"])
    - per series: monotonic (true/false), start point [x,y], end point [x,y],
      and any local extrema (peaks/valleys) as [x,y] with a label.
    - ONLY include numbers you can actually read from axis ticks. Use null
      for anything you cannot read. NEVER invent intermediate points.
    Leave "csv" empty.

  IF type in (xrd, micrograph, other): set digitizable=false, leave both empty.

confidence = how readable/reliable your extraction is (0.0-1.0).

Return STRICT JSON only (no markdown fences, no prose, no <think>):
{
  "type": "line|bar|xrd|micrograph|other",
  "digitizable": true/false,
  "confidence": 0.0,
  "reason": "one short sentence",
  "csv": "",
  "line_summary": {
    "x_axis": "", "y_axis": "",
    "series": [
      {"label": "", "monotonic": true,
       "start": [null, null], "end": [null, null],
       "extrema": [{"point": [null, null], "kind": "peak|valley", "note": ""}]}
    ]
  }
}
For bar charts, output "line_summary": null. For non-data images, both null."""



def _b64(p: Path) -> str:
    return base64.b64encode(p.read_bytes()).decode("utf-8")


def digitize_chart(img_path: Path, caption: str = "") -> dict:
    """单次 VLM 调用:分类 + (若可行) CSV 数字化。返回解析后的 dict。"""
    from openai import OpenAI

    api_key = (os.getenv("VLM_API_KEY") or os.getenv("LLM_API_KEY") or "").strip()
    base_url = (os.getenv("VLM_BASE_URL") or os.getenv("LLM_BASE_URL") or "").strip()
    model = (os.getenv("VLM_MODEL") or os.getenv("LLM_MODEL") or "").strip()
    client = OpenAI(api_key=api_key, base_url=base_url)

    user_text = _VLM_PROMPT
    if caption:
        user_text = f"Caption: {caption}\n\n{user_text}"

    resp = client.chat.completions.create(
        model=model,
        messages=[{
            "role": "user",
            "content": [
                {"type": "image_url",
                 "image_url": {"url": f"data:image/jpeg;base64,{_b64(img_path)}"}},
                {"type": "text", "text": user_text},
            ],
        }],
        max_tokens=2048,
        temperature=0.1,
    )
    raw = (resp.choices[0].message.content or "").strip()
    raw = re.sub(r"<think>.*?</think>", "", raw, flags=re.S | re.I).strip()
    raw = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw).strip()
    try:
        return json.loads(raw)
    except Exception:
        m = re.search(r"\{.*\}", raw, re.S)
        if m:
            try:
                return json.loads(m.group(0))
            except Exception:
                pass
        return {"type": "parse_error", "digitizable": False, "confidence": 0.0,
                "reason": "JSON parse failed", "csv": "", "_raw": raw[:500]}


def figure_num_of(item: dict) -> str:
    return str((item.get("data") or {}).get("figure_num") or "")


def caption_of(item: dict) -> str:
    return str((item.get("data") or {}).get("caption") or "")


if __name__ == "__main__":
    pdf_name = sys.argv[1] if len(sys.argv) > 1 else "李希海_增材制造-Effect_of_b.pdf"
    pdf_path = ROOT / "data" / "raw" / pdf_name
    if not pdf_path.is_file():
        raise SystemExit(f"PDF 不存在: {pdf_path}")

    json_path, items = run_ocr(pdf_path, ROOT / "data" / "raw")
    buckets = triage(items)
    print("\n=== 第一级分流(按 box token) ===")
    for k, v in buckets.items():
        print(f"  {k:6s}: {len(v)} 个带 image_path 的 item")

    print("\n=== 第二级:VLM 分类闸门 + CSV 数字化 (仅 chart 桶) ===")
    paper_dir = ROOT / "data" / "raw" / pdf_path.stem
    results = []
    inject_blocks = []
    for item in buckets["chart"]:
        data = item.get("data") or {}
        img_path = Path(data.get("image_path", ""))
        if not img_path.is_file():
            continue
        fnum = figure_num_of(item)
        cap = caption_of(item)
        print(f"\n--- {img_path.name}  (Figure {fnum or '?'}) ---")
        r = digitize_chart(img_path, caption=cap)
        r["_image"] = img_path.name
        r["_figure_num"] = fnum
        results.append(r)
        print(f"  type={r.get('type')}  digitizable={r.get('digitizable')}  "
              f"conf={r.get('confidence')}")
        print(f"  reason: {r.get('reason')}")

        label = f"Figure {fnum}" if fnum else "Figure"
        block = None
        if r.get("type") == "bar" and r.get("csv", "").strip():
            block = f"> [{label} VLM-digitized]:\n{r['csv'].strip()}"
            print("  --- CSV (bar) ---")
            for line in r["csv"].strip().splitlines():
                print(f"    {line}")
        elif r.get("type") == "line" and isinstance(r.get("line_summary"), dict):
            ls = r["line_summary"]
            lines = [f"chart_type: line (estimated from pixels — key points & trend only)"]
            lines.append(f"x_axis: {ls.get('x_axis')}")
            lines.append(f"y_axis: {ls.get('y_axis')}")
            for s in ls.get("series") or []:
                lines.append(
                    f"series {s.get('label')}: monotonic={s.get('monotonic')}, "
                    f"start={s.get('start')}, end={s.get('end')}, "
                    f"extrema={s.get('extrema')}"
                )
            block = f"> [{label} VLM-digitized]:\n" + "\n".join(lines)
            print("  --- LINE SUMMARY ---")
            for line in lines:
                print(f"    {line}")

        if block:
            inject_blocks.append(block)


    # 落地完整结果 + 注入块预览
    (paper_dir / "_vlm_charts.json").write_text(
        json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    preview = "\n\n".join(inject_blocks)
    (paper_dir / "_inject_preview.md").write_text(preview, encoding="utf-8")
    print(f"\n\n=== 汇总 ===")
    print(f"  chart 桶 {len(buckets['chart'])} 张 → 可数字化 {len(inject_blocks)} 张")
    type_counts = {}
    for r in results:
        type_counts[r.get("type")] = type_counts.get(r.get("type"), 0) + 1
    print(f"  类型分布: {type_counts}")
    print(f"  完整结果 → {paper_dir / '_vlm_charts.json'}")
    print(f"  注入块预览 → {paper_dir / '_inject_preview.md'}")
