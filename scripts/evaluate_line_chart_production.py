#!/usr/bin/env python3
"""Exercise bounded line extraction on real PaddleOCR chart crops.

The default audit is offline: it reads existing PDFs/OCR JSON, never calls OCR
or a VLM, and reports vector coverage plus deterministic raster colour-split
coverage. With ``--with-vlm-calibration``, only deduplicated resolved chart
figures that failed vector extraction receive one classification/calibration
request; curve coordinates still come exclusively from code.
"""

from __future__ import annotations

import argparse
import json
import tempfile
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any

from knowmat.app_config import settings
from knowmat.pdf.chart_digitizer import (
    digitize_chart_image,
    digitize_line_chart_multi,
    digitize_line_chart_region,
    format_digitized_block,
    is_chart_crop,
    merge_line_semantics,
)
from knowmat.pdf.figure_items import (
    iter_resolved_figure_items,
    normalize_figure_ocr_items,
)
from knowmat.pdf.figure_describer import (
    _fit_chart_block_to_paper_budget,
    _has_ambiguous_multi_panel_axes,
)
from knowmat.pdf.line_chart_splitter import split_line_chart_by_color


def _read_ocr_items(path: Path) -> list[dict[str, Any]]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, list):
        raise ValueError(f"Expected OCR item list: {path}")
    return [item for item in value if isinstance(item, dict)]


def _chart_items(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    seen: set[tuple[int, str]] = set()
    for item in items:
        data = item.get("data") if isinstance(item.get("data"), dict) else {}
        image_path = str(data.get("image_path") or "").strip()
        if not image_path or not is_chart_crop(image_path):
            continue
        try:
            page = int(item.get("page") or 0)
        except (TypeError, ValueError):
            page = 0
        key = (page, image_path)
        if key in seen:
            continue
        seen.add(key)
        out.append(item)
    return out


def _resolved_chart_items(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Mirror the production figure resolver, then keep chart-box crops."""
    normalize_figure_ocr_items(items)
    resolved: list[dict[str, Any]] = []
    for item in iter_resolved_figure_items(items):
        data = item.get("data")
        if isinstance(data, dict) and is_chart_crop(str(data.get("image_path") or "")):
            resolved.append(item)
    return resolved


def _resolve_image_path(raw_path: str, paper_dir: Path) -> Path:
    raw = Path(str(raw_path or ""))
    candidates = [raw]
    if not raw.is_absolute():
        candidates.extend([paper_dir / raw, paper_dir / "images" / raw.name])
    else:
        candidates.append(paper_dir / "images" / raw.name)
    return next((path for path in candidates if path.is_file()), raw)


def _color_split_count(image_path: Path, max_series: int) -> int:
    if not image_path.is_file():
        return 0
    try:
        with tempfile.TemporaryDirectory(prefix="knowmat_color_scan_") as tmp:
            return len(
                split_line_chart_by_color(
                    image_path,
                    Path(tmp),
                    max_series=max_series,
                )
            )
    except Exception:
        return 0


def _int_setting(name: str, default: int, *, minimum: int = 0) -> int:
    try:
        return max(minimum, int(getattr(settings, name, default)))
    except (TypeError, ValueError):
        return default


def evaluate(
    input_root: Path,
    output_root: Path,
    *,
    scan_raster_colors: bool = True,
) -> dict[str, Any]:
    per_figure_limit = _int_setting(
        "chart_context_max_chars_per_figure", 2400, minimum=512
    )
    per_paper_limit = _int_setting(
        "chart_context_max_chars_per_paper", 12000
    )
    context_series_limit = _int_setting(
        "chart_context_max_series", 12, minimum=1
    )
    raster_series_limit = _int_setting("line_chart_max_series", 6, minimum=1)

    output_root.mkdir(parents=True, exist_ok=True)
    papers: list[dict[str, Any]] = []
    methods: Counter[str] = Counter()
    color_splittable = 0
    color_series = 0
    for pdf in sorted(input_root.glob("*.pdf")):
        paper_dir = input_root / pdf.stem
        json_path = paper_dir / f"{pdf.stem}.json"
        if not json_path.is_file():
            papers.append(
                {
                    "paper": pdf.stem,
                    "status": "missing_ocr_json",
                    "candidates": 0,
                    "digitized": 0,
                    "figures": [],
                }
            )
            continue

        candidates = _chart_items(_read_ocr_items(json_path))
        paper_output = output_root / pdf.stem
        blocks: list[str] = []
        figures: list[dict[str, Any]] = []
        for index, item in enumerate(candidates, start=1):
            data = item.get("data") if isinstance(item.get("data"), dict) else {}
            image_path = str(data.get("image_path") or "")
            figure_num = str(data.get("figure_num") or index)
            stable_figure_id = f"{figure_num}_{index}"
            result = digitize_line_chart_region(
                pdf,
                item.get("page", 0),
                item.get("bbox"),
                legacy_image_path=image_path,
                max_series=raster_series_limit,
            )
            if not result:
                split_count = (
                    _color_split_count(
                        _resolve_image_path(image_path, paper_dir),
                        raster_series_limit,
                    )
                    if scan_raster_colors
                    else 0
                )
                if split_count >= 2:
                    color_splittable += 1
                    color_series += split_count
                figures.append(
                    {
                        "candidate": index,
                        "page": item.get("page"),
                        "image": Path(image_path).name,
                        "status": "inconclusive_or_not_line",
                        "raster_color_series": split_count,
                    }
                )
                continue

            method = str(result.get("method") or "unknown")
            methods[method] += 1
            series = [
                row for row in result.get("series") or [] if isinstance(row, dict)
            ]
            point_count = sum(int(row.get("n_points") or 0) for row in series)
            block = format_digitized_block(
                result,
                stable_figure_id,
                csv_dir=str(paper_output),
                context_max_chars=per_figure_limit,
                context_max_series=context_series_limit,
            )
            blocks.append(block)
            csv_line = next(
                (line for line in block.splitlines() if line.startswith("data_csv:")),
                "",
            )
            csv_name = csv_line.partition(":")[2].strip()
            csv_path = paper_output / csv_name if csv_name else None
            omitted_line = next(
                (
                    line
                    for line in block.splitlines()
                    if line.startswith("context_omitted_series:")
                ),
                "context_omitted_series: 0",
            )
            figures.append(
                {
                    "candidate": index,
                    "page": item.get("page"),
                    "image": Path(image_path).name,
                    "status": "digitized",
                    "method": method,
                    "series": len(series),
                    "points": point_count,
                    "context_chars": len(block),
                    "context_omitted_series": int(
                        omitted_line.partition(":")[2].strip() or 0
                    ),
                    "csv": str(csv_path.relative_to(output_root))
                    if csv_path and csv_path.is_file()
                    else None,
                    "csv_bytes": csv_path.stat().st_size
                    if csv_path and csv_path.is_file()
                    else 0,
                }
            )

        remaining = per_paper_limit
        injected_chars = 0
        degraded_blocks = 0
        skipped_blocks = 0
        for block in blocks:
            bounded = _fit_chart_block_to_paper_budget(
                block, max(0, remaining - 2)
            )
            if not bounded:
                skipped_blocks += 1
                continue
            if bounded != block:
                degraded_blocks += 1
            used = len(bounded) + 2
            injected_chars += used
            remaining = max(0, remaining - used)

        digitized = sum(figure.get("status") == "digitized" for figure in figures)
        papers.append(
            {
                "paper": pdf.stem,
                "status": "ok",
                "candidates": len(candidates),
                "digitized": digitized,
                "inconclusive_or_not_line": len(candidates) - digitized,
                "series": sum(int(row.get("series") or 0) for row in figures),
                "points": sum(int(row.get("points") or 0) for row in figures),
                "sidecar_bytes": sum(
                    int(row.get("csv_bytes") or 0) for row in figures
                ),
                "standalone_context_chars": sum(len(block) for block in blocks),
                "production_context_chars": injected_chars,
                "degraded_context_blocks": degraded_blocks,
                "skipped_context_blocks": skipped_blocks,
                "context_within_budget": injected_chars <= per_paper_limit,
                "figures": figures,
            }
        )

    ok_papers = [paper for paper in papers if paper.get("status") == "ok"]
    digitized_figures = [
        figure
        for paper in ok_papers
        for figure in paper.get("figures") or []
        if figure.get("status") == "digitized"
    ]
    report = {
        "input_root": str(input_root),
        "output_root": str(output_root),
        "configuration": {
            "per_figure_context_chars": per_figure_limit,
            "per_paper_context_chars": per_paper_limit,
            "context_series": context_series_limit,
            "raster_series": raster_series_limit,
            "ocr_called": False,
            "vlm_called": False,
            "raster_color_scan": scan_raster_colors,
        },
        "summary": {
            "papers": len(papers),
            "papers_ok": len(ok_papers),
            "missing_ocr_json": len(papers) - len(ok_papers),
            "chart_candidates": sum(int(p.get("candidates") or 0) for p in ok_papers),
            "digitized": len(digitized_figures),
            "inconclusive_or_not_line": sum(
                int(p.get("inconclusive_or_not_line") or 0) for p in ok_papers
            ),
            "raster_color_splittable": color_splittable,
            "raster_color_series": color_series,
            "methods": dict(sorted(methods.items())),
            "series": sum(int(row.get("series") or 0) for row in digitized_figures),
            "points": sum(int(row.get("points") or 0) for row in digitized_figures),
            "sidecar_bytes": sum(
                int(row.get("csv_bytes") or 0) for row in digitized_figures
            ),
            "standalone_context_chars": sum(
                int(p.get("standalone_context_chars") or 0) for p in ok_papers
            ),
            "production_context_chars": sum(
                int(p.get("production_context_chars") or 0) for p in ok_papers
            ),
            "max_figure_context_chars": max(
                (int(row.get("context_chars") or 0) for row in digitized_figures),
                default=0,
            ),
            "max_paper_context_chars": max(
                (int(p.get("production_context_chars") or 0) for p in ok_papers),
                default=0,
            ),
            "papers_over_context_budget": sum(
                not bool(p.get("context_within_budget")) for p in ok_papers
            ),
            "degraded_context_blocks": sum(
                int(p.get("degraded_context_blocks") or 0) for p in ok_papers
            ),
            "skipped_context_blocks": sum(
                int(p.get("skipped_context_blocks") or 0) for p in ok_papers
            ),
        },
        "papers": papers,
    }
    return report


def evaluate_vlm_fallback(
    input_root: Path,
    output_root: Path,
    *,
    max_calls: int,
    workers: int,
) -> dict[str, Any]:
    """Evaluate the classification-gated raster fallback without OCR calls."""
    per_figure_limit = _int_setting(
        "chart_context_max_chars_per_figure", 2400, minimum=512
    )
    per_paper_limit = _int_setting(
        "chart_context_max_chars_per_paper", 12000
    )
    context_series_limit = _int_setting(
        "chart_context_max_series", 12, minimum=1
    )
    raster_series_limit = _int_setting("line_chart_max_series", 6, minimum=1)
    try:
        confidence_threshold = float(
            getattr(settings, "line_chart_classification_min_confidence", 0.7)
        )
    except (TypeError, ValueError):
        confidence_threshold = 0.7
    confidence_threshold = min(1.0, max(0.0, confidence_threshold))

    candidates: list[dict[str, Any]] = []
    missing_ocr_json = 0
    for pdf in sorted(input_root.glob("*.pdf")):
        paper_dir = input_root / pdf.stem
        json_path = paper_dir / f"{pdf.stem}.json"
        if not json_path.is_file():
            missing_ocr_json += 1
            continue
        items = _read_ocr_items(json_path)
        for index, item in enumerate(_resolved_chart_items(items), start=1):
            data = item.get("data") if isinstance(item.get("data"), dict) else {}
            image_path = _resolve_image_path(
                str(data.get("image_path") or ""), paper_dir
            )
            # Raster fallback is only relevant when the deterministic source
            # PDF region could not already recover a chart.
            vector_result = digitize_line_chart_region(
                pdf,
                item.get("page", 0),
                item.get("bbox"),
                legacy_image_path=image_path,
                max_series=raster_series_limit,
            )
            if vector_result:
                continue
            candidates.append(
                {
                    "paper": pdf.stem,
                    "candidate": index,
                    "page": item.get("page"),
                    "image_path": image_path,
                    "image": image_path.name,
                    "figure_num": str(data.get("figure_num") or index),
                    "caption": str(data.get("caption") or ""),
                }
            )

    call_limit = max(0, int(max_calls))
    selected = candidates[:call_limit] if call_limit else candidates
    skipped_for_limit = len(candidates) - len(selected)
    result_root = output_root / "vlm-raster"
    result_root.mkdir(parents=True, exist_ok=True)

    def _run(candidate: dict[str, Any]) -> dict[str, Any]:
        semantic = digitize_chart_image(
            candidate["image_path"],
            caption=candidate["caption"],
        )
        row = {
            key: value
            for key, value in candidate.items()
            if key != "image_path"
        }
        if not isinstance(semantic, dict):
            row["status"] = "classification_failed"
            return row
        chart_type = str(semantic.get("type") or "other")
        try:
            confidence = float(semantic.get("confidence") or 0.0)
        except (TypeError, ValueError):
            confidence = 0.0
        row.update(chart_type=chart_type, confidence=confidence)
        if chart_type != "line":
            row["status"] = f"classified_{chart_type}"
            return row
        if confidence < confidence_threshold:
            row["status"] = "line_below_confidence"
            return row
        if _has_ambiguous_multi_panel_axes(semantic):
            row["status"] = "line_ambiguous_multi_panel_axes"
            return row
        calibration = semantic.get("axis_calibration")
        if not isinstance(calibration, dict):
            row["status"] = "line_invalid_calibration"
            return row
        line_summary = semantic.get("line_summary")
        if isinstance(line_summary, dict):
            calibration = dict(calibration)
            calibration.setdefault("x_axis", line_summary.get("x_axis"))
            calibration.setdefault("y_axis", line_summary.get("y_axis"))
        raster = digitize_line_chart_multi(
            candidate["image_path"],
            caption=candidate["caption"],
            max_series=raster_series_limit,
            axis_calibration=calibration,
            allow_axis_calibration_vlm=False,
        )
        if not raster:
            row["status"] = "raster_inconclusive"
            return row
        merged = merge_line_semantics(raster, semantic)
        paper_output = result_root / candidate["paper"]
        stable_id = f"{candidate['figure_num']}_{candidate['candidate']}"
        block = format_digitized_block(
            merged,
            stable_id,
            csv_dir=str(paper_output),
            context_max_chars=per_figure_limit,
            context_max_series=context_series_limit,
        )
        series = [
            value
            for value in merged.get("series") or []
            if isinstance(value, dict)
        ]
        csv_line = next(
            (line for line in block.splitlines() if line.startswith("data_csv:")),
            "",
        )
        csv_name = csv_line.partition(":")[2].strip()
        csv_path = paper_output / csv_name if csv_name else None
        row.update(
            status="raster_digitized",
            calibration_valid=True,
            series=len(series),
            points=sum(int(value.get("n_points") or 0) for value in series),
            context_chars=len(block),
            context=block,
            csv=str(csv_path.relative_to(output_root))
            if csv_path and csv_path.is_file()
            else None,
            csv_bytes=csv_path.stat().st_size
            if csv_path and csv_path.is_file()
            else 0,
        )
        return row

    rows: list[dict[str, Any]] = []
    with ThreadPoolExecutor(max_workers=max(1, min(int(workers), 8))) as executor:
        futures = {
            executor.submit(_run, candidate): candidate for candidate in selected
        }
        for future in as_completed(futures):
            try:
                rows.append(future.result())
            except Exception as exc:
                candidate = futures[future]
                rows.append(
                    {
                        key: value
                        for key, value in candidate.items()
                        if key != "image_path"
                    }
                    | {
                        "status": "worker_failed",
                        "error": f"{type(exc).__name__}: {exc}",
                    }
                )
    rows.sort(key=lambda row: (str(row.get("paper")), int(row.get("candidate") or 0)))

    per_paper: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        if row.get("status") == "raster_digitized":
            per_paper.setdefault(str(row.get("paper")), []).append(row)
    paper_context_chars: dict[str, int] = {}
    for paper, paper_rows in per_paper.items():
        remaining = per_paper_limit
        used = 0
        for row in paper_rows:
            bounded = _fit_chart_block_to_paper_budget(
                str(row.pop("context", "")), max(0, remaining - 2)
            )
            row["production_context_chars"] = len(bounded) + 2 if bounded else 0
            row["context_degraded"] = bool(
                bounded and len(bounded) != int(row.get("context_chars") or 0)
            )
            used += int(row["production_context_chars"])
            remaining = max(0, per_paper_limit - used)
        paper_context_chars[paper] = used

    statuses = Counter(str(row.get("status") or "unknown") for row in rows)
    chart_types = Counter(str(row.get("chart_type") or "unknown") for row in rows)
    digitized = [row for row in rows if row.get("status") == "raster_digitized"]
    return {
        "configuration": {
            "ocr_called": False,
            "vlm_called": True,
            "confidence_threshold": confidence_threshold,
            "max_calls": call_limit,
            "workers": max(1, min(int(workers), 8)),
            "per_figure_context_chars": per_figure_limit,
            "per_paper_context_chars": per_paper_limit,
        },
        "summary": {
            "missing_ocr_json": missing_ocr_json,
            "resolved_vector_inconclusive_candidates": len(candidates),
            "classification_requests": len(selected),
            "skipped_for_call_limit": skipped_for_limit,
            "chart_types": dict(sorted(chart_types.items())),
            "statuses": dict(sorted(statuses.items())),
            "raster_digitized": len(digitized),
            "series": sum(int(row.get("series") or 0) for row in digitized),
            "points": sum(int(row.get("points") or 0) for row in digitized),
            "sidecar_bytes": sum(int(row.get("csv_bytes") or 0) for row in digitized),
            "max_figure_context_chars": max(
                (int(row.get("context_chars") or 0) for row in digitized),
                default=0,
            ),
            "max_paper_context_chars": max(paper_context_chars.values(), default=0),
            "papers_over_context_budget": sum(
                value > per_paper_limit for value in paper_context_chars.values()
            ),
        },
        "figures": rows,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=Path("data/raw"))
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--skip-raster-color-scan",
        action="store_true",
        help="Skip the offline deterministic color-split coverage scan.",
    )
    parser.add_argument(
        "--with-vlm-calibration",
        action="store_true",
        help="Run classification/calibration on resolved vector-inconclusive charts.",
    )
    parser.add_argument("--vlm-max-calls", type=int, default=150)
    parser.add_argument("--workers", type=int, default=4)
    args = parser.parse_args()
    report_path = args.output / "production_line_chart_report.json"
    previous_vlm_fallback = None
    if report_path.is_file() and not args.with_vlm_calibration:
        try:
            previous = json.loads(report_path.read_text(encoding="utf-8"))
            previous_vlm_fallback = previous.get("vlm_fallback")
        except (OSError, ValueError, TypeError):
            previous_vlm_fallback = None
    report = evaluate(
        args.input,
        args.output,
        scan_raster_colors=not args.skip_raster_color_scan,
    )
    if args.with_vlm_calibration:
        report["vlm_fallback"] = evaluate_vlm_fallback(
            args.input,
            args.output,
            max_calls=args.vlm_max_calls,
            workers=args.workers,
        )
    elif isinstance(previous_vlm_fallback, dict):
        report["vlm_fallback"] = previous_vlm_fallback
    report_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(report["summary"], ensure_ascii=False, indent=2))
    if "vlm_fallback" in report:
        print(json.dumps(report["vlm_fallback"]["summary"], ensure_ascii=False, indent=2))
    return 0 if report["summary"]["missing_ocr_json"] == 0 else 2


if __name__ == "__main__":
    raise SystemExit(main())
