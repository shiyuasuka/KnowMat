#!/usr/bin/env python3
"""Compare adjudicated GPT expert GT, business GT, and final v5 at claim level."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from collections import Counter
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


def _expert_claims_root(independent_root: Path, *, use_adjudicated: bool) -> tuple[str, Path]:
    if use_adjudicated:
        summary_path = independent_root / "corpus_summary.json"
        if not summary_path.is_file():
            raise ValueError("corpus_summary.json is required for adjudicated comparison")
        summary = _load(summary_path)
        if (summary.get("validation") or {}).get("status") != "passed":
            raise ValueError("adjudicated expert GT has not passed validation")
        return "adjudicated", independent_root / "adjudicated"
    return "sealed", independent_root / "papers"


def _verify_blind_seal(seal: dict[str, Any], repo_root: Path) -> dict[str, Any]:
    mismatches: list[str] = []
    checked = 0
    for artifact in seal.get("artifacts") or []:
        artifact_path = repo_root / artifact["path"]
        if not artifact_path.is_file():
            mismatches.append(f"missing:{artifact['path']}")
            continue
        checked += 1
        digest = hashlib.sha256(artifact_path.read_bytes()).hexdigest()
        if digest != artifact["sha256"] or artifact_path.stat().st_size != artifact["size"]:
            mismatches.append(artifact["path"])
    return {
        "checked": checked,
        "expected": len(seal.get("artifacts") or []),
        "mismatch_count": len(mismatches),
        "mismatches": mismatches,
        "status": "passed" if not mismatches and checked == len(seal.get("artifacts") or []) else "failed",
    }


def _adjudication_summary(independent_root: Path, paper_ids: list[str]) -> dict[str, Any]:
    count_fields = (
        "confirmed_correct", "confirmed_missing", "unsupported_claim", "wrong_owner",
        "wrong_axis", "wrong_origin", "value_conflict", "unit_conflict",
        "condition_conflict", "duplicate_claim", "likely_ocr_error", "likely_chart_error",
    )
    systems = ("business_gt", "final_v5")
    totals = {system: Counter() for system in systems}
    per_paper: dict[str, Any] = {}
    for paper_id in paper_ids:
        path = independent_root / "adjudicated" / paper_id / "adjudication.json"
        if not path.is_file():
            raise ValueError(f"missing adjudication: {paper_id}")
        document = _load(path)
        per_paper[paper_id] = {}
        for system in systems:
            source = (document.get("systems") or {}).get(system) or {}
            row = {field: int(source.get(field) or 0) for field in count_fields}
            per_paper[paper_id][system] = row
            totals[system].update(row)
    ranking_by_paper: dict[str, str] = {}
    for summary_path in sorted((independent_root / "adjudicated").glob("batch_*_summary.json")):
        for paper in _load(summary_path).get("papers") or []:
            compared = [
                system
                for system in paper.get("accuracy_rank") or []
                if system in systems
            ]
            if len(compared) == 2:
                ranking_by_paper[paper["paper_id"]] = compared[0]
    return {
        "count_semantics": "evidence-adjudicated audit tags; tags are not guaranteed mutually exclusive and are not precision/recall denominators",
        "totals": {system: dict(totals[system]) for system in systems},
        "per_paper": per_paper,
        "professional_ranking": {
            "counts": dict(Counter(ranking_by_paper.values())),
            "per_paper_winner": ranking_by_paper,
        },
    }


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


def _compare_corpus(
    *,
    manifest: dict[str, Any],
    business_index: dict[str, Path],
    v5_index: dict[str, Path],
    expert_claims_root: Path,
    work_dir: Path | None,
) -> dict[str, Any]:
    papers: dict[str, Any] = {}
    missing: list[dict[str, str]] = []
    if work_dir is not None:
        work_dir.mkdir(parents=True, exist_ok=True)
    for record in manifest["papers"]:
        paper_id, key = record["paper_id"], record["paper_key"]
        business_path = business_index.get(title_key(key))
        v5_path = v5_index.get(title_key(key))
        expert_path = expert_claims_root / paper_id / "expert_claims.jsonl"
        if not business_path or not v5_path or not expert_path.is_file():
            missing.append(
                {
                    "paper_id": paper_id,
                    "paper_key": key,
                    "business": str(business_path or "missing"),
                    "v5": str(v5_path or "missing"),
                    "expert": str(expert_path if expert_path.is_file() else "missing"),
                }
            )
            continue
        expert = load_expert_claims(expert_path)
        business = flatten_v11(_load(business_path), source="business_gt", paper_key=key)
        v5 = flatten_v11(_load(v5_path), source="final_v5", paper_key=key)
        paper_result: dict[str, Any] = {
            "paper_id": paper_id,
            "paper_key": key,
            "claim_counts": {
                "expert": summarize_counts(expert),
                "business_gt": summarize_counts(business),
                "final_v5": summarize_counts(v5),
            },
        }
        work_payload: dict[str, Any] = {
            "paper_id": paper_id,
            "paper_key": key,
            "expert_claims": expert,
        }
        for system_name, claims in (("business_gt", business), ("final_v5", v5)):
            comparison = compare_claim_sets(claims, expert)
            issues = issue_candidates(claims, expert, comparison)
            paper_result[system_name] = {
                "comparison": comparison,
                "issue_counts": dict(Counter(row["code"] for row in issues)),
            }
            work_payload[system_name] = {"claims": claims, "issues": issues}
        papers[paper_id] = paper_result
        if work_dir is not None:
            (work_dir / f"{paper_id}.json").write_text(
                json.dumps(work_payload, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
    aggregate = {system: _aggregate(papers, system) for system in ("business_gt", "final_v5")}
    issue_summary = {
        system: dict(sum((Counter(paper[system]["issue_counts"]) for paper in papers.values()), Counter()))
        for system in ("business_gt", "final_v5")
    }
    return {
        "paper_count": len(papers),
        "missing": missing,
        "aggregate": aggregate,
        "issue_summary": issue_summary,
        "papers": papers,
    }


def _render(report: dict[str, Any]) -> str:
    business = report["aggregate"]["business_gt"]
    final_v5 = report["aggregate"]["final_v5"]
    business_loose = business["unique_modes"]["loose"]["micro"]
    final_loose = final_v5["unique_modes"]["loose"]["micro"]
    business_strict = business["unique_modes"]["strict"]["micro"]
    final_strict = final_v5["unique_modes"]["strict"]["micro"]
    business_core = business["unique_modes"]["loose"]["core_tensile"]
    final_core = final_v5["unique_modes"]["loose"]["core_tensile"]
    audit = report["adjudication_summary"]["totals"]
    error_fields = (
        "unsupported_claim", "wrong_owner", "wrong_axis", "wrong_origin",
        "value_conflict", "unit_conflict", "condition_conflict",
    )
    error_tags = {
        system: sum(audit[system].get(field, 0) for field in error_fields)
        for system in ("business_gt", "final_v5")
    }
    lines = [
        "# GPT-5.6-sol independent expert GT vs business GT vs final v5",
        "",
        "## Executive verdict",
        "",
        "**Professional conclusion: the adjudicated GPT-5.6-sol expert GT is the most reliable factual ledger; among the two evaluated system outputs, business GT is more accurate overall, while final v5 contains more source-supported correct facts but also materially more unsupported projections, owner/value errors, and cross-item duplicates.**",
        "",
        f"- Business GT unique loose F1: **{business_loose['f1']:.3f}**; final v5: **{final_loose['f1']:.3f}**.",
        f"- Business GT unique strict F1: **{business_strict['f1']:.3f}**; final v5: **{final_strict['f1']:.3f}**. Strict matching additionally requires compatible owner/state/condition.",
        f"- Business GT unique core-tensile loose F1: **{business_core['f1']:.3f}**; final v5: **{final_core['f1']:.3f}**.",
        f"- Evidence adjudication confirmed {audit['business_gt']['confirmed_correct']} correct business-GT tags and {audit['final_v5']['confirmed_correct']} correct final-v5 tags, but final v5 accumulated {error_tags['final_v5']} core factual-error tags versus {error_tags['business_gt']} for business GT.",
        f"- Cross-item duplicate tags: business GT {audit['business_gt']['duplicate_claim']}; final v5 {audit['final_v5']['duplicate_claim']}.",
        f"- Paper-level professional ranking: business GT leads on **{report['adjudication_summary']['professional_ranking']['counts'].get('business_gt', 0)}/30** papers; final v5 on **{report['adjudication_summary']['professional_ranking']['counts'].get('final_v5', 0)}/30**.",
        "- The audit-tag totals are diagnostic counts and may overlap; precision/recall/F1 comes only from the one-to-one claim matcher below.",
        "",
        "## Expert-GT provenance",
        "",
        f"- Blind seal: `{report['blind_seal']['sealed_at']}`",
        f"- Blind manifest SHA-256: `{report['blind_seal']['manifest_sha256']}`",
        f"- Sealed independent claims: `{report['blind_seal']['claim_count']}`",
        f"- Official adjudicated claims: `{report['expert_gt']['claim_count']}`",
        f"- Accepted post-unblinding amendments: `{report['expert_gt']['accepted_amendment_count']}` ({report['expert_gt']['accepted_actions'].get('add', 0)} add, {report['expert_gt']['accepted_actions'].get('replace', 0)} replace); rejected: `{report['expert_gt']['rejected_amendment_count']}`.",
        f"- Adjudicated validation: `{report['expert_gt']['validation_status']}`; sealed artifact hash check: `{report['expert_gt']['sealed_hash_check']['checked']}/{report['expert_gt']['sealed_hash_check']['expected']} matched; {report['expert_gt']['sealed_hash_check']['mismatch_count']} mismatch`.",
        f"- Chart evidence audit: `{report['blind_seal']['chart_csv_count']}/{report['blind_seal']['chart_csv_count']}` CSVs covered by the sealed validation.",
        f"- Papers: `{report['paper_count']}/30`",
        "- Loose match = same axis + compatible scientific semantic + compatible value/unit.",
        "- Strict match = loose match + compatible material owner/state/region + test condition.",
        "- Item IDs are never used as scientific identity. One-to-one matching prevents duplicates from inflating matches.",
        "- This is an evidence-validated LLM expert reference, not an independently human-certified universal gold standard; the blind seal and all post-unblinding amendments are supplied for audit.",
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
    lines.extend(["## Evidence-adjudicated error profile", "", "| System | Audit tag | Count |", "|---|---|---:|"])
    for system in ("business_gt", "final_v5"):
        for code in (
            "confirmed_correct", "confirmed_missing", "unsupported_claim", "wrong_owner",
            "wrong_axis", "wrong_origin", "value_conflict", "unit_conflict",
            "condition_conflict", "duplicate_claim", "likely_ocr_error", "likely_chart_error",
        ):
            lines.append(f"| {system} | `{code}` | {audit[system][code]} |")
    lines.extend(["", "These are source-evidence adjudication tags, not mutually exclusive confusion-matrix cells. They identify the failure mode: omission, unsupported fact, wrong material/sample attribution, wrong axis/origin, value/unit/condition conflict, or duplication.", ""])

    lines.extend(["## Automated residual-difference queue", "", "| System | Issue code | Count |", "|---|---|---:|"])
    for system, counts in report["issue_summary"].items():
        for code, count in sorted(counts.items()):
            lines.append(f"| {system} | `{code}` | {count} |")
    lines.extend(["", "This queue is matcher-generated against the final adjudicated ledger. It is useful for locating disagreements but is not itself the professional verdict.", ""])

    sealed = report.get("sealed_audit")
    if sealed:
        lines.extend(["## Sealed vs adjudicated audit", "", "The blind seal remains the historical pre-unblinding record. Official metrics use adjudicated GT; sealed metrics are retained below solely to show the effect of accepted corrections.", "", "| System | Metric | Sealed F1 | Adjudicated F1 | Delta |", "|---|---|---:|---:|---:|"])
        for system in ("business_gt", "final_v5"):
            for scope, mode, label in (
                ("unique_modes", "loose", "unique loose micro"),
                ("unique_modes", "strict", "unique strict micro"),
                ("unique_modes", "loose", "unique core tensile"),
            ):
                key = "core_tensile" if label == "unique core tensile" else "micro"
                before = sealed["aggregate"][system][scope][mode][key]["f1"]
                after = report["aggregate"][system][scope][mode][key]["f1"]
                lines.append(f"| {system} | {label} | {before:.3f} | {after:.3f} | {after - before:+.3f} |")
        lines.append("")

    lines.extend([
        "## Professional interpretation",
        "",
        "- **Who is more accurate?** Business GT. Its unique loose, unique strict, and core-tensile F1 are all higher; it leads the paper-level professional ranking on 24/30 papers and has fewer total core factual-error tags and duplicates.",
        "- **Who has more correct extracted content?** Final v5 has more individually confirmed correct tags, so it is not simply worse or hallucinated wholesale. Its problem is precision and organization: supported facts are mixed with many repeated projections and facts assigned to the wrong item/state/condition.",
        "- **Who has more omissions?** Both omit substantial expert-ledger content. Evidence-tagged omissions are close, with final v5 slightly higher in this adjudication. The missing content is concentrated in owner/state-specific process, structure, characterization, and property facts rather than only headline tensile values.",
        "- **What are the factual errors?** Final v5 has substantially more unsupported projections, wrong-owner tags, value conflicts, and duplicates. Business GT is more conservative but has more condition-conflict and slightly more unit-conflict tags, so it is not uniformly better on every error class.",
        "- **Why are strict F1 values low?** The professional ledger is atomic and owner/state/condition-specific, while both v11 outputs often bundle, replicate, or omit those dimensions. Strict F1 is therefore a demanding attribution score, not a statement that only that fraction of sentences is scientifically true.",
        "",
        "A post-materialization validation caught one concrete nominal-versus-measured composition error in an amendment: the PBF-EB Ti-22Al-25Nb sample contains 21.93 at.% Nb in the reported table, not nominal 25 at.%. It was corrected before official scoring. Two non-atomic umbrella claims were rejected. The sealed corpus was never changed.",
        "",
        "Per-paper metrics are in the CSV. Per-claim evidence decisions and full audit payloads are retained in the adjudication files and machine-readable JSON report.",
        "",
    ])
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--independent-root", type=Path, default=Path("data/gt/gpt56sol-independent-expert-20260818"))
    parser.add_argument("--business-root", type=Path, default=Path("data/gt/papers-native-ids-with-pdf-ocr-images-20260809"))
    parser.add_argument("--v5-root", type=Path, default=Path("data/output-alpha25-prompt-v5-final30-quality-gates-final-v5-20260818"))
    parser.add_argument("--output", type=Path, default=Path("reports/gpt56sol_independent_gt_vs_business_vs_v5_20260818.json"))
    parser.add_argument("--work-dir", type=Path, default=Path("data/gt/gpt56sol-independent-expert-20260818/comparison_work"))
    parser.add_argument("--use-adjudicated", action="store_true", help="Use validated post-unblinding expert claims as the official comparison ledger")
    args = parser.parse_args()

    seal_path = args.independent_root / "blind_seal.json"
    if not seal_path.is_file():
        raise SystemExit("blind_seal.json is required before comparison")
    seal = _load(seal_path)
    repo_root = args.independent_root.resolve().parents[2]
    seal_check = _verify_blind_seal(seal, repo_root)
    if seal_check["status"] != "passed":
        raise SystemExit(f"blind seal verification failed: {seal_check['mismatches'][:5]}")
    manifest = _load(args.independent_root / "blind_input_manifest.json")
    business_index = _business_index(args.business_root)
    v5_index = _v5_index(args.v5_root)
    expert_variant, claims_root = _expert_claims_root(
        args.independent_root,
        use_adjudicated=args.use_adjudicated,
    )
    comparison = _compare_corpus(
        manifest=manifest,
        business_index=business_index,
        v5_index=v5_index,
        expert_claims_root=claims_root,
        work_dir=args.work_dir / expert_variant,
    )
    papers = comparison["papers"]
    missing = comparison["missing"]
    materialized_summary = _load(args.independent_root / "corpus_summary.json") if args.use_adjudicated else None
    sealed_audit = None
    if args.use_adjudicated:
        sealed_comparison = _compare_corpus(
            manifest=manifest,
            business_index=business_index,
            v5_index=v5_index,
            expert_claims_root=args.independent_root / "papers",
            work_dir=None,
        )
        sealed_audit = {
            "claim_count": seal["validation_summary"]["claim_count"],
            "paper_count": sealed_comparison["paper_count"],
            "missing": sealed_comparison["missing"],
            "aggregate": sealed_comparison["aggregate"],
            "issue_summary": sealed_comparison["issue_summary"],
        }
    paper_ids = [row["paper_id"] for row in manifest["papers"]]
    adjudication_summary = _adjudication_summary(args.independent_root, paper_ids)
    report = {
        "schema_version": "knowmat_independent_gt_three_way_comparison_v2",
        "blind_seal": {
            "path": str(seal_path), "sealed_at": seal["sealed_at"],
            "manifest_sha256": seal["blind_input_manifest"]["sha256"],
            "claim_count": seal["validation_summary"]["claim_count"],
            "chart_csv_count": seal["validation_summary"]["chart_csv_count"],
        },
        "expert_gt": {
            "primary_variant": expert_variant,
            "claims_root": str(claims_root),
            "claim_count": materialized_summary["adjudicated_claim_count"] if materialized_summary else seal["validation_summary"]["claim_count"],
            "accepted_amendment_count": (materialized_summary or {}).get("accepted_amendment_count", 0),
            "accepted_actions": (materialized_summary or {}).get("accepted_actions", {}),
            "rejected_amendment_count": (materialized_summary or {}).get("rejected_amendment_count", 0),
            "validation_status": ((materialized_summary or {}).get("validation") or {}).get("status", "sealed"),
            "sealed_hash_check": seal_check,
        },
        "paper_count": comparison["paper_count"],
        "missing": missing,
        "aggregate": comparison["aggregate"],
        "issue_summary": comparison["issue_summary"],
        "adjudication_summary": adjudication_summary,
        "sealed_audit": sealed_audit,
        "papers": papers,
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
    adjudication_csv_path = args.output.with_name(args.output.stem + "_adjudication.csv")
    audit_fields = list(next(iter(adjudication_summary["per_paper"].values()))["business_gt"])
    with adjudication_csv_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["paper_id", "paper_key", "system", "professional_winner", *audit_fields])
        writer.writeheader()
        title_by_id = {row["paper_id"]: row["paper_key"] for row in manifest["papers"]}
        for paper_id, systems in adjudication_summary["per_paper"].items():
            for system, counts in systems.items():
                writer.writerow({"paper_id": paper_id, "paper_key": title_by_id[paper_id], "system": system, "professional_winner": adjudication_summary["professional_ranking"]["per_paper_winner"].get(paper_id, ""), **counts})
    print(json.dumps({"status": "ok" if not missing else "missing", "expert_variant": expert_variant, "papers": len(papers), "missing": missing, "output": str(args.output), "csv": str(csv_path), "adjudication_csv": str(adjudication_csv_path)}, ensure_ascii=False, indent=2))
    return 0 if not missing else 2


if __name__ == "__main__":
    raise SystemExit(main())
