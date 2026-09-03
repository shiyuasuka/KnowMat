#!/usr/bin/env python3
"""Compare KnowMat v11 outputs with the eight reviewed alpha.6 examples.

The frozen alpha.6 evaluator is authoritative for process/tensile semantics.
This wrapper adds coverage counts for the composition and structure axes and
produces one report even when only a subset of papers has completed.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
ALPHA6_ROOT = REPO_ROOT / "material-extracor-v11.0.0-alpha.6"
sys.path.insert(0, str(ALPHA6_ROOT))

from scripts.evaluate_v11 import canonical_projection, compare_projection  # noqa: E402


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _title_key(value: str | None) -> str:
    return re.sub(r"[^a-z0-9]+", "", (value or "").casefold())


def _axis_counts(document: dict[str, Any]) -> dict[str, int]:
    items = document.get("items") or []
    extracted = [item.get("Extracted_Data") or {} for item in items]
    return {
        "items": len(items),
        "process_stages": sum(
            len(((row.get("Processing") or {}).get("Process_Route") or {}).get("stages") or [])
            for row in extracted
        ),
        "process_parameters": sum(
            len(stage.get("parameters") or [])
            for row in extracted
            for stage in (
                ((row.get("Processing") or {}).get("Process_Route") or {}).get("stages") or []
            )
        ),
        "properties": sum(len(row.get("Properties") or []) for row in extracted),
        "composition_observations": sum(
            len((row.get("Composition") or {}).get("Composition_Observations") or [])
            for row in extracted
        ),
        "structure_observations": sum(
            len((row.get("Structure") or {}).get("Structure_Observations") or [])
            for row in extracted
        ),
    }


def _count_recall(expected: int, actual: int) -> float:
    if expected == 0:
        return 1.0
    return min(actual, expected) / expected


def _count_alignment(expected: int, actual: int) -> float:
    """Symmetric count agreement: both omissions and over-extraction are penalized."""
    if expected == actual == 0:
        return 1.0
    return min(actual, expected) / max(actual, expected)


def _find_documents(runs_root: Path) -> dict[str, Path]:
    candidates: list[Path] = []
    candidates.extend(runs_root.rglob("final.json"))
    candidates.extend(runs_root.rglob("*_normalized.json"))
    indexed: dict[str, Path] = {}
    for path in sorted(candidates, key=lambda row: (row.name != "final.json", len(row.parts))):
        try:
            document = _read_json(path)
        except (OSError, json.JSONDecodeError):
            continue
        title = (document.get("Paper_Metadata") or {}).get("title")
        key = _title_key(title)
        if key and key not in indexed:
            indexed[key] = path
    return indexed


def _validation_for(document_path: Path) -> dict[str, Any] | None:
    search_roots = [document_path.parent, *document_path.parents[:4]]
    seen: set[Path] = set()
    for root in search_roots:
        if root in seen or not root.is_dir():
            continue
        seen.add(root)
        for path in root.rglob("*_issues.json"):
            try:
                value = _read_json(path)
            except (OSError, json.JSONDecodeError):
                continue
            if isinstance(value.get("issues"), list):
                return {
                    "state": value.get("state"),
                    "fatal_count": value.get("fatal_count", 0),
                    "review_count": value.get("review_count", 0),
                    "path": str(path),
                }
    return None


def _manifest_rows(examples_root: Path) -> list[dict[str, Any]]:
    manifest = _read_json(examples_root / "manifest.json")
    return manifest.get("papers", []) if isinstance(manifest, dict) else manifest


def evaluate(examples_root: Path, runs_root: Path) -> dict[str, Any]:
    actual_by_title = _find_documents(runs_root)
    paper_reports: list[dict[str, Any]] = []
    matched_reports: list[dict[str, Any]] = []

    for row in _manifest_rows(examples_root):
        expected_path = examples_root / str(row["directory"]) / row["files"]["final_json"]
        actual_path = actual_by_title.get(_title_key(row.get("title")))
        report: dict[str, Any] = {
            "number": row.get("number"),
            "title": row.get("title"),
            "expected_path": str(expected_path),
            "actual_path": str(actual_path) if actual_path else None,
            "status": "not_run" if actual_path is None else "evaluated",
        }
        if actual_path is not None:
            expected = _read_json(expected_path)
            actual = _read_json(actual_path)
            expected_counts = _axis_counts(expected)
            actual_counts = _axis_counts(actual)
            count_recall = {
                key: _count_recall(expected_counts[key], actual_counts[key])
                for key in expected_counts
            }
            count_alignment = {
                key: _count_alignment(expected_counts[key], actual_counts[key])
                for key in expected_counts
            }
            report.update(
                schema_version=(actual.get("Rule_Metadata") or {}).get("schema_version"),
                schema_matches=(actual.get("Rule_Metadata") or {}).get("schema_version")
                == "material_extraction_v11.3.0",
                strict_metrics=compare_projection(
                    canonical_projection(expected), canonical_projection(actual)
                ),
                expected_counts=expected_counts,
                actual_counts=actual_counts,
                count_recall=count_recall,
                count_alignment=count_alignment,
                mean_axis_count_recall=sum(count_recall.values()) / len(count_recall),
                mean_axis_count_alignment=sum(count_alignment.values()) / len(count_alignment),
                validation=_validation_for(actual_path),
            )
            matched_reports.append(report)
        paper_reports.append(report)

    recall_keys = list(_axis_counts({}).keys())
    aggregate_recall = {
        key: (
            sum(report["count_recall"][key] for report in matched_reports)
            / len(matched_reports)
            if matched_reports
            else 0.0
        )
        for key in recall_keys
    }
    aggregate_alignment = {
        key: (
            sum(report["count_alignment"][key] for report in matched_reports)
            / len(matched_reports)
            if matched_reports
            else 0.0
        )
        for key in recall_keys
    }
    return {
        "report_version": "knowmat_v11_alpha6_example_validation_v1",
        "expected_schema_version": "material_extraction_v11.3.0",
        "papers_total": len(paper_reports),
        "papers_evaluated": len(matched_reports),
        "papers_not_run": len(paper_reports) - len(matched_reports),
        "papers_promotable": sum(
            (report.get("validation") or {}).get("state") in {"passed", "passed_with_review"}
            for report in matched_reports
        ),
        "schema_match_rate": (
            sum(bool(report.get("schema_matches")) for report in matched_reports)
            / len(matched_reports)
            if matched_reports
            else 0.0
        ),
        "mean_axis_count_recall": aggregate_recall,
        "mean_axis_count_alignment": aggregate_alignment,
        "papers": paper_reports,
    }


def _markdown(report: dict[str, Any]) -> str:
    lines = [
        "# KnowMat v11 alpha.6 示例对齐验证",
        "",
        f"- 已评估：{report['papers_evaluated']}/{report['papers_total']}",
        f"- 可提升为 final.json：{report['papers_promotable']}/{report['papers_evaluated']}",
        f"- schema 一致率：{report['schema_match_rate']:.1%}",
        "",
        "| # | 论文 | 状态 | item | 工艺 | 参数 | 性能 | 成分 | 组织 | fatal/review |",
        "|---:|---|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    keys = (
        "items",
        "process_stages",
        "process_parameters",
        "properties",
        "composition_observations",
        "structure_observations",
    )
    for paper in report["papers"]:
        if paper["status"] != "evaluated":
            values = ["-"] * len(keys)
            validation = "-"
        else:
            values = [
                f"{paper['actual_counts'][key]}/{paper['expected_counts'][key]}" for key in keys
            ]
            check = paper.get("validation") or {}
            validation = f"{check.get('fatal_count', '?')}/{check.get('review_count', '?')}"
        lines.append(
            "| "
            + " | ".join(
                [
                    str(paper["number"]),
                    paper["title"],
                    paper["status"],
                    *values,
                    validation,
                ]
            )
            + " |"
        )
    lines.extend(
        [
            "",
            "> 数量列格式为 `KnowMat/示例`。严格的工艺节点、边、参数和拉伸语义指标见 JSON 报告中的 `strict_metrics`。",
            "",
        ]
    )
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--examples", type=Path, required=True)
    parser.add_argument("--runs", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    report = evaluate(args.examples.resolve(), args.runs.resolve())
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    markdown_path = args.output.with_suffix(".md")
    markdown_path.write_text(_markdown(report), encoding="utf-8")
    print(json.dumps({
        "json": str(args.output),
        "markdown": str(markdown_path),
        "papers_evaluated": report["papers_evaluated"],
        "papers_promotable": report["papers_promotable"],
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
