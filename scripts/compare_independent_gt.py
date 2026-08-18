#!/usr/bin/env python3
"""Compare sealed GPT expert GT, business GT, and final v5 at claim level."""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from typing import Any

from knowmat.evaluation.independent_gt_comparison import (
    AXES,
    compare_claim_sets,
    flatten_v11,
    issue_candidates,
    load_expert_claims,
    summarize_counts,
    title_key,
)


def _load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"Expected JSON object: {path}")
    return value


def _business_index(root: Path) -> dict[str, Path]:
    result: dict[str, Path] = {}
    for path in root.glob("*.json"):
        document = _load(path)
        metadata = document.get("Paper_Metadata") or {}
        title = metadata.get("Paper_Title") or path.stem
        result[title_key(title)] = path
    return result


def _v5_index(root: Path) -> dict[str, Path]:
    result: dict[str, Path] = {}
    for path in root.glob("*/final.json"):
        document = _load(path)
        metadata = document.get("Paper_Metadata") or {}
        source_text = str(metadata.get("source_text") or "")
        title = source_text.removesuffix("_final_output.md") or path.parent.name.replace("_", " ")
        result[title_key(title)] = path
    return result


def _aggregate(papers: dict[str, Any], system: str) -> dict[str, Any]:
    result: dict[str, Any] = {"modes": {}, "unique_modes": {}}

    def metric(row: dict[str, int]) -> dict[str, Any]:
        precision = row["matched"] / row["system"] if row["system"] else (1.0 if not row["expert"] else 0.0)
        recall = row["matched"] / row["expert"] if row["expert"] else (1.0 if not row["system"] else 0.0)
        f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
        return {**row, "precision": round(precision, 6), "recall": round(recall, 6), "f1": round(f1, 6)}

    for scope in ("modes", "unique_modes"):
        for mode in ("loose", "strict"):
            axes: dict[str, dict[str, int]] = {axis: {"matched": 0, "system": 0, "expert": 0} for axis in AXES}
            core = {"matched": 0, "system": 0, "expert": 0}
            for paper in papers.values():
                paper_report = paper[system]["comparison"][scope][mode]
                for axis in AXES:
                    for key in axes[axis]:
                        axes[axis][key] += int(paper_report["axes"][axis][key])
                for key in core:
                    core[key] += int(paper_report["core_tensile"][key])
            axis_metrics = {axis: metric(row) for axis, row in axes.items()}
            micro = metric({key: sum(row[key] for row in axes.values()) for key in ("matched", "system", "expert")})
            macro = {key: round(sum(axis_metrics[axis][key] for axis in AXES) / len(AXES), 6) for key in ("precision", "recall", "f1")}
            result[scope][mode] = {"axes": axis_metrics, "micro": micro, "macro": macro, "core_tensile": metric(core)}
    return result


def _render(report: dict[str, Any]) -> str:
    lines = [
        "# GPT-5.6-sol independent expert GT vs business GT vs final v5",
        "",
        f"- Blind seal: `{report['blind_seal']['sealed_at']}`",
        f"- Blind manifest SHA-256: `{report['blind_seal']['manifest_sha256']}`",
        f"- Independent expert claims: `{report['blind_seal']['claim_count']}`",
        f"- Papers: `{report['paper_count']}/30`",
        "- Loose match = same axis + compatible scientific semantic + compatible value/unit.",
        "- Strict match = loose match + compatible material owner/state/region + test condition.",
        "- These are pre-adjudication metrics; source-supported extras are reviewed before the final factual verdict.",
        "",
    ]
    for scope, label in (("unique_modes", "Unique scientific claims"), ("modes", "Raw item assignments")):
      for mode in ("strict", "loose"):
        lines.extend([f"## {label}: {mode} metrics", "", "| System | Axis | Matched | System | Expert | Precision | Recall | F1 |", "|---|---|---:|---:|---:|---:|---:|---:|"])
        for system in ("business_gt", "final_v5"):
            rows = report["aggregate"][system][scope][mode]
            for axis in AXES:
                row = rows["axes"][axis]
                lines.append(f"| {system} | {axis} | {row['matched']} | {row['system']} | {row['expert']} | {row['precision']:.3f} | {row['recall']:.3f} | {row['f1']:.3f} |")
            row = rows["micro"]
            lines.append(f"| {system} | **micro** | {row['matched']} | {row['system']} | {row['expert']} | {row['precision']:.3f} | {row['recall']:.3f} | {row['f1']:.3f} |")
            core = rows["core_tensile"]
            lines.append(f"| {system} | **unique core tensile** | {core['matched']} | {core['system']} | {core['expert']} | {core['precision']:.3f} | {core['recall']:.3f} | {core['f1']:.3f} |")
        lines.append("")
    lines.extend(["## Adjudication queue", "", "| System | Issue code | Count |", "|---|---|---:|"])
    for system, counts in report["issue_summary"].items():
        for code, count in sorted(counts.items()):
            lines.append(f"| {system} | `{code}` | {count} |")
    lines.extend(["", "Per-paper issue payloads are stored in the JSON report and comparison-work directory. Final correctness conclusions are added only after evidence adjudication.", ""])
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--independent-root", type=Path, default=Path("data/gt/gpt56sol-independent-expert-20260818"))
    parser.add_argument("--business-root", type=Path, default=Path("data/gt/papers-native-ids-with-pdf-ocr-images-20260809"))
    parser.add_argument("--v5-root", type=Path, default=Path("data/output-alpha25-prompt-v5-final30-quality-gates-final-v5-20260818"))
    parser.add_argument("--output", type=Path, default=Path("reports/gpt56sol_independent_gt_vs_business_vs_v5_20260818.json"))
    parser.add_argument("--work-dir", type=Path, default=Path("data/gt/gpt56sol-independent-expert-20260818/comparison_work"))
    args = parser.parse_args()

    seal_path = args.independent_root / "blind_seal.json"
    if not seal_path.is_file():
        raise SystemExit("blind_seal.json is required before comparison")
    seal = _load(seal_path)
    manifest = _load(args.independent_root / "blind_input_manifest.json")
    business_index = _business_index(args.business_root)
    v5_index = _v5_index(args.v5_root)
    args.work_dir.mkdir(parents=True, exist_ok=True)
    papers: dict[str, Any] = {}
    missing: list[dict[str, str]] = []

    for record in manifest["papers"]:
        paper_id, key = record["paper_id"], record["paper_key"]
        business_path = business_index.get(title_key(key))
        v5_path = v5_index.get(title_key(key))
        if not business_path or not v5_path:
            missing.append({"paper_id": paper_id, "paper_key": key, "business": str(business_path or "missing"), "v5": str(v5_path or "missing")})
            continue
        expert = load_expert_claims(args.independent_root / "papers" / paper_id / "expert_claims.jsonl")
        business = flatten_v11(_load(business_path), source="business_gt", paper_key=key)
        v5 = flatten_v11(_load(v5_path), source="final_v5", paper_key=key)
        paper_result: dict[str, Any] = {
            "paper_id": paper_id, "paper_key": key,
            "claim_counts": {"expert": summarize_counts(expert), "business_gt": summarize_counts(business), "final_v5": summarize_counts(v5)},
        }
        work_payload: dict[str, Any] = {"paper_id": paper_id, "paper_key": key, "expert_claims": expert}
        for system_name, claims in (("business_gt", business), ("final_v5", v5)):
            comparison = compare_claim_sets(claims, expert)
            issues = issue_candidates(claims, expert, comparison)
            paper_result[system_name] = {"comparison": comparison, "issue_counts": dict(__import__("collections").Counter(row["code"] for row in issues))}
            work_payload[system_name] = {"claims": claims, "issues": issues}
        papers[paper_id] = paper_result
        (args.work_dir / f"{paper_id}.json").write_text(json.dumps(work_payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    aggregate = {system: _aggregate(papers, system) for system in ("business_gt", "final_v5")}
    issue_summary = {
        system: dict(sum((__import__("collections").Counter(paper[system]["issue_counts"]) for paper in papers.values()), __import__("collections").Counter()))
        for system in ("business_gt", "final_v5")
    }
    report = {
        "schema_version": "knowmat_independent_gt_three_way_comparison_v1",
        "blind_seal": {
            "path": str(seal_path), "sealed_at": seal["sealed_at"],
            "manifest_sha256": seal["blind_input_manifest"]["sha256"],
            "claim_count": seal["validation_summary"]["claim_count"],
            "chart_csv_count": seal["validation_summary"]["chart_csv_count"],
        },
        "paper_count": len(papers), "missing": missing, "aggregate": aggregate,
        "issue_summary": issue_summary, "papers": papers,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    args.output.with_suffix(".md").write_text(_render(report), encoding="utf-8")
    csv_path = args.output.with_name(args.output.stem + "_per_paper_axis.csv")
    with csv_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["paper_id", "paper_key", "system", "mode", "axis", "matched", "system_count", "expert_count", "precision", "recall", "f1"])
        writer.writeheader()
        for paper in papers.values():
            for system in ("business_gt", "final_v5"):
                for scope in ("unique_modes", "modes"):
                    for mode in ("strict", "loose"):
                        for axis in AXES:
                            row = paper[system]["comparison"][scope][mode]["axes"][axis]
                            scope_name = "unique" if scope == "unique_modes" else "raw"
                            writer.writerow({"paper_id": paper["paper_id"], "paper_key": paper["paper_key"], "system": system, "mode": f"{scope_name}_{mode}", "axis": axis, "matched": row["matched"], "system_count": row["system"], "expert_count": row["expert"], "precision": row["precision"], "recall": row["recall"], "f1": row["f1"]})
    print(json.dumps({"status": "ok" if not missing else "missing", "papers": len(papers), "missing": missing, "output": str(args.output), "csv": str(csv_path)}, ensure_ascii=False, indent=2))
    return 0 if not missing else 2


if __name__ == "__main__":
    raise SystemExit(main())
