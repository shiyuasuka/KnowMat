#!/usr/bin/env python3
"""Materialize the post-unblinding expert GT without modifying the blind seal."""

from __future__ import annotations

import argparse
import importlib.util
import json
import shutil
from collections import Counter
from pathlib import Path
from typing import Any, Iterable


COPIED_ARTIFACTS = ("expert_gt.json", "curve_audit.json", "issues.json")


def _load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"Expected JSON object: {path}")
    return value


def _jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _write_jsonl(path: Path, rows: Iterable[dict[str, Any]]) -> None:
    path.write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows), encoding="utf-8")


def _rejected(root: Path) -> set[tuple[str, str]]:
    path = root / "adjudicated" / "post_adjudication_review.json"
    if not path.is_file():
        return set()
    review = _load(path)
    return {(row["paper_id"], row["claim_id"]) for row in review.get("rejected_amendments") or []}


def apply_amendments(
    claims: list[dict[str, Any]],
    amendments: list[dict[str, Any]],
    *,
    paper_id: str,
    rejected: set[tuple[str, str]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Apply accepted overlays and return materialized claims plus audit rows."""

    order = [row["claim_id"] for row in claims]
    by_id = {row["claim_id"]: row for row in claims}
    if len(order) != len(by_id):
        raise ValueError(f"duplicate sealed claim ID in {paper_id}")
    audit: list[dict[str, Any]] = []
    for amendment_index, amendment in enumerate(amendments, start=1):
        action = amendment["action"]
        corrected = amendment.get("corrected_claim")
        amendment_claim_id = (corrected or {}).get("claim_id") or amendment.get("sealed_claim_id")
        if (paper_id, amendment_claim_id) in rejected:
            continue
        sealed_id = amendment.get("sealed_claim_id")
        before: dict[str, Any] | None = None
        after: dict[str, Any] | None = None
        if action == "add":
            if not isinstance(corrected, dict):
                raise ValueError(f"{paper_id} add amendment lacks corrected_claim")
            claim_id = corrected["claim_id"]
            if claim_id in by_id:
                raise ValueError(f"{paper_id} add duplicates {claim_id}")
            by_id[claim_id] = corrected
            order.append(claim_id)
            after = corrected
        elif action == "replace":
            if not sealed_id or sealed_id not in by_id or not isinstance(corrected, dict):
                raise ValueError(f"{paper_id} invalid replace amendment for {sealed_id!r}")
            if corrected.get("claim_id") != sealed_id:
                raise ValueError(f"{paper_id} replacement changed claim ID {sealed_id}")
            before = by_id[sealed_id]
            by_id[sealed_id] = corrected
            after = corrected
        elif action == "remove":
            if not sealed_id or sealed_id not in by_id:
                raise ValueError(f"{paper_id} invalid remove amendment for {sealed_id!r}")
            before = by_id.pop(sealed_id)
            order.remove(sealed_id)
        else:
            raise ValueError(f"{paper_id} unknown amendment action: {action!r}")
        audit.append(
            {
                "audit_id": f"post_unblind_{paper_id}_{amendment_index:04d}",
                "paper_key": (after or before or {})["paper_key"],
                "phase": "adjudication",
                "actor": "gpt56sol_post_unblind_adjudication",
                "action": {"add": "create", "replace": "update", "remove": "delete"}[action],
                "target_type": "claim",
                "target_id": amendment_claim_id,
                "before": before,
                "after": after,
                "reason": amendment["reason"],
                "evidence": [amendment["evidence_quote"]],
            }
        )
    return [by_id[claim_id] for claim_id in order], audit


def _validator_module(repo_root: Path) -> Any:
    path = repo_root / "scripts" / "independent_gt.py"
    spec = importlib.util.spec_from_file_location("independent_gt_materializer", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Cannot import validator: {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=Path("."))
    parser.add_argument("--output-root", type=Path, default=Path("data/gt/gpt56sol-independent-expert-20260818"))
    args = parser.parse_args()
    repo_root = args.repo_root.resolve()
    root = (repo_root / args.output_root).resolve()
    manifest = _load(root / "blind_input_manifest.json")
    seal = _load(root / "blind_seal.json")
    rejected = _rejected(root)
    accepted_amendments: list[dict[str, Any]] = []
    paper_summaries: list[dict[str, Any]] = []
    validator = _validator_module(repo_root)
    contract_schemas = {
        artifact: validator._load_schema(repo_root, filename)
        for artifact, filename in validator.ARTIFACT_SCHEMAS.items()
    }
    v11_schema = validator._read_json(repo_root / validator.V11_SCHEMA)
    validation_reports: list[dict[str, Any]] = []

    for paper in manifest["papers"]:
        paper_id = paper["paper_id"]
        sealed_dir = root / "papers" / paper_id
        adjudicated_dir = root / "adjudicated" / paper_id
        adjudication_path = adjudicated_dir / "adjudication.json"
        if not adjudication_path.is_file():
            raise ValueError(f"missing adjudication: {paper_id}")
        adjudication = _load(adjudication_path)
        sealed_claims = _jsonl(sealed_dir / "expert_claims.jsonl")
        materialized, audit_rows = apply_amendments(
            sealed_claims,
            adjudication.get("expert_gt_amendments") or [],
            paper_id=paper_id,
            rejected=rejected,
        )
        adjudicated_dir.mkdir(parents=True, exist_ok=True)
        _write_jsonl(adjudicated_dir / "expert_claims.jsonl", materialized)
        for name in COPIED_ARTIFACTS:
            shutil.copyfile(sealed_dir / name, adjudicated_dir / name)
        original_audit = _jsonl(sealed_dir / "annotation_audit.jsonl")
        _write_jsonl(adjudicated_dir / "annotation_audit.jsonl", [*original_audit, *audit_rows])

        accepted_ids = {row["target_id"] for row in audit_rows}
        for amendment in adjudication.get("expert_gt_amendments") or []:
            corrected = amendment.get("corrected_claim") or {}
            amendment_id = corrected.get("claim_id") or amendment.get("sealed_claim_id")
            if amendment_id in accepted_ids:
                accepted_amendments.append({"paper_id": paper_id, **amendment})
        paper_summaries.append(
            {
                "paper_id": paper_id,
                "paper_key": paper["paper_key"],
                "sealed_claim_count": len(sealed_claims),
                "adjudicated_claim_count": len(materialized),
                "accepted_amendment_count": len(audit_rows),
                "rejected_amendment_count": sum(
                    (paper_id, (row.get("corrected_claim") or {}).get("claim_id") or row.get("sealed_claim_id")) in rejected
                    for row in adjudication.get("expert_gt_amendments") or []
                ),
            }
        )
        paper_for_validation = {**paper, "output_dir": str(adjudicated_dir.relative_to(repo_root))}
        validation_reports.append(
            validator._validate_paper(
                paper_for_validation,
                repo_root,
                False,
                contract_schemas,
                v11_schema,
            )
        )

    _write_jsonl(root / "adjudicated" / "amendments.jsonl", accepted_amendments)
    finding_count = sum(len(row["findings"]) for row in validation_reports)
    actions = Counter(row["action"] for row in accepted_amendments)
    summary = {
        "schema_version": "knowmat_adjudicated_expert_gt_summary_v1",
        "blind_seal_path": str((root / "blind_seal.json").relative_to(repo_root)),
        "blind_manifest_sha256": seal["blind_input_manifest"]["sha256"],
        "sealed_claim_count": seal["validation_summary"]["claim_count"],
        "adjudicated_claim_count": sum(row["adjudicated_claim_count"] for row in paper_summaries),
        "accepted_amendment_count": len(accepted_amendments),
        "accepted_actions": dict(actions),
        "rejected_amendment_count": len(rejected),
        "papers": paper_summaries,
        "validation": {
            "status": "passed" if finding_count == 0 else "failed",
            "papers_checked": len(validation_reports),
            "papers_passed": sum(not row["findings"] for row in validation_reports),
            "finding_count": finding_count,
            "reports": validation_reports,
        },
        "post_materialization_review": str(
            (root / "adjudicated" / "post_materialization_review.json").relative_to(repo_root)
        ),
        "sealed_artifacts_modified": False,
    }
    (root / "corpus_summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({key: summary[key] for key in ("sealed_claim_count", "adjudicated_claim_count", "accepted_amendment_count", "accepted_actions", "rejected_amendment_count", "validation") if key != "validation"} | {"validation": summary["validation"]["status"]}, ensure_ascii=False, indent=2))
    return 0 if finding_count == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
