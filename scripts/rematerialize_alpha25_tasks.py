#!/usr/bin/env python3
"""Rebuild Alpha25 outputs from cached task responses without provider calls."""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import sys
import unicodedata
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

from knowmat.alpha25.contracts import InventoryAnchor, parse_task_response  # noqa: E402
from knowmat.alpha25.evidence import (  # noqa: E402
    gate_task_response,
    structured_table_cell_recovery_v202_enabled,
)
from knowmat.alpha25.materialize import materialize_candidate  # noqa: E402
from knowmat.alpha25.materialize import (  # noqa: E402
    dense_tensile_table_completion_v203_enabled,
    discrete_chart_sidecar_v202_enabled,
    global_tensile_scope_v201_enabled,
    owner_state_condition_v202_enabled,
    property_coordinate_quarantine_v203_enabled,
    source_coordinate_precision_v202_enabled,
)
from knowmat.alpha25.property_context import (  # noqa: E402
    tensile_protocol_ledger_v203_enabled,
)
from knowmat.alpha25.promotion import (  # noqa: E402
    promote_axis_facts,
    same_table_property_merge_v201_enabled,
)
from knowmat.alpha25.planner import build_evidence_units  # noqa: E402
from knowmat.evaluation.alpha25_gt import (  # noqa: E402
    audit_fact_evidence,
    build_evidence_audit_corpus,
)
from knowmat.nodes.extraction import _deterministic_table_anchors  # noqa: E402
from knowmat.nodes.v11_normalize import normalize_v11  # noqa: E402


def _read_object(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"Expected JSON object: {path}")
    return value


def _paper_text_path(paper_root: Path) -> Path:
    candidates = sorted((paper_root / "txt_parse").glob("*_final_output.md"))
    if not candidates:
        raise FileNotFoundError(f"No parsed source Markdown under {paper_root}")
    return candidates[0]


def _candidate_path(paper_root: Path) -> Path:
    candidates = sorted((paper_root / "v11" / "03_extract").glob("*_candidate.json"))
    if not candidates:
        raise FileNotFoundError(f"No Alpha25 candidate under {paper_root}")
    return candidates[0]


def _compact_owner_text(value: Any) -> str:
    text = unicodedata.normalize("NFKC", str(value or "")).casefold()
    return re.sub(r"[^a-z0-9]+", "", text)


def _recovery_has_explicit_owner(record: Any) -> bool:
    """Require an owner-bearing quote before recovering a rejected fact."""

    owner = str(getattr(record, "sample_id_raw", "") or "").strip()
    owner_key = _compact_owner_text(owner)
    if not owner_key:
        return False
    for raw in getattr(record, "source_evidence", []) or []:
        row = unicodedata.normalize("NFKC", str(raw or ""))
        # Short sample codes use literal token boundaries to avoid treating a
        # prefix such as CoCrNi as the owner of CoCrNiAl.
        if len(owner_key) < 8 and re.search(
            rf"(?i)(?<![A-Za-z0-9]){re.escape(owner)}(?![A-Za-z0-9])",
            row,
        ):
            return True
        row_key = _compact_owner_text(row)
        if len(owner_key) >= 8 and owner_key in row_key:
            return True
    return False


def rebuild_paper(paper_root: Path, output_root: Path) -> dict[str, Any]:
    task_paths = sorted((paper_root / "v11" / "02_alpha25_tasks").glob("*.json"))
    if not task_paths:
        raise FileNotFoundError(f"No Alpha25 task caches under {paper_root}")

    source_path = _paper_text_path(paper_root)
    source_text = source_path.read_text(encoding="utf-8", errors="replace")
    old_candidate = _read_object(_candidate_path(paper_root))
    accepted_anchors: list[InventoryAnchor] = []
    accepted_facts: list[Any] = []
    accepted_fact_task_ids: list[str] = []
    rejected = 0
    invalid = 0
    evidence_issues: list[dict[str, Any]] = []
    audit_corpus = build_evidence_audit_corpus(source_text)
    recover_rejected = os.getenv(
        "KNOWMAT2_ALPHA25_RECOVER_REJECTED", "0"
    ).strip().casefold() in {"1", "true", "yes", "on"}
    recover_unsupported = os.getenv(
        "KNOWMAT2_ALPHA25_RECOVER_UNSUPPORTED", "0"
    ).strip().casefold() in {"1", "true", "yes", "on"}

    evidence_units = build_evidence_units(source_text)
    projected_evidence = "\n\n".join(
        value
        for unit in evidence_units
        for value in (unit.text, unit.source_text)
        if value
    )
    audit_text = source_text + "\n\n" + projected_evidence
    for unit in evidence_units:
        accepted_anchors.extend(_deterministic_table_anchors(unit))

    for task_path in task_paths:
        payload = _read_object(task_path)
        axis = str(payload.get("axis") or "").strip()
        if not axis:
            invalid += 1
            continue
        response = parse_task_response(axis, payload)
        gate = gate_task_response(
            response,
            evidence_unit_id=f"offline:{task_path.name}",
            evidence_text=audit_text,
            structured_source_text=source_text,
        )
        evidence_issues.extend(issue.to_dict() for issue in gate.audit_issues)
        evidence_issues.extend(issue.to_dict() for issue in gate.issues)
        contract_rejections = list(
            getattr(response, "contract_rejections", []) or []
        )
        evidence_issues.extend(
            {
                **rejection.model_dump(),
                "severity": "review",
                "path": f"evidence_gate.offline:{task_path.name}.contract",
                "evidence_unit_id": f"offline:{task_path.name}",
                "evidence_index": -1,
                "evidence": (
                    rejection.source_evidence[0]
                    if rejection.source_evidence
                    else ""
                ),
                "expected": {"alpha25_contract_valid": True},
                "actual": rejection.model_dump(),
                "suggested_action": (
                    "Review the complete rejected contract row in the paper audit."
                ),
            }
            for rejection in contract_rejections
        )
        recovered = []
        if recover_rejected:
            recoverable_statuses = {"format_mismatch"}
            if recover_unsupported:
                recoverable_statuses.add("unsupported")
            recovered = [
                record
                for record in gate.rejected
                if audit_fact_evidence(
                    record.model_dump(), source_text, corpus=audit_corpus
                )
                in recoverable_statuses
                and _recovery_has_explicit_owner(record)
            ]
        rejected += len(gate.rejected) - len(recovered)
        rejected += len(contract_rejections)
        for record in [*gate.accepted, *recovered]:
            if isinstance(record, InventoryAnchor):
                accepted_anchors.append(record)
            elif hasattr(record, "fact_type"):
                accepted_facts.append(record)
                accepted_fact_task_ids.append(task_path.name)

    promotion_enabled = os.getenv(
        "KNOWMAT2_ALPHA25_PROMOTION_ENABLED", "1"
    ).strip().casefold() in {"1", "true", "yes", "on"}
    if promotion_enabled:
        promotion = promote_axis_facts(
            accepted_anchors,
            accepted_facts,
            source_text=source_text,
            task_ids=accepted_fact_task_ids,
        )
        promoted_facts = list(promotion.accepted)
        promotion_issues = [issue.to_dict() for issue in promotion.issues]
    else:
        promoted_facts = accepted_facts
        promotion_issues = []

    materialized = materialize_candidate(
        accepted_anchors,
        promoted_facts,
        paper_metadata=old_candidate.get("Paper_Metadata") or {},
        paper_routing=old_candidate.get("Paper_Routing") or {},
        source_text=source_text,
        source_dir=source_path.parent,
    )
    paper_output = output_root / paper_root.name
    # Keep the exact extraction evidence beside the rematerialized candidate.
    # The GT evaluator audits quotes against ``txt_parse/*_final_output.md`` in
    # the results tree; omitting this directory made grounded chart/table facts
    # look unsupported even though the source run contained their literal text.
    source_txt_parse = paper_root / "txt_parse"
    output_txt_parse = paper_output / "txt_parse"
    if source_txt_parse.is_dir():
        shutil.copytree(source_txt_parse, output_txt_parse, dirs_exist_ok=True)
    copied_source_path = output_txt_parse / source_path.name
    v203_gates = {
        "tensile_protocol_ledger": tensile_protocol_ledger_v203_enabled(),
        "dense_tensile_table_completion": (
            dense_tensile_table_completion_v203_enabled()
        ),
        "property_coordinate_quarantine": (
            property_coordinate_quarantine_v203_enabled()
        ),
    }
    normalized = normalize_v11(
        {
            "final_data": materialized.document,
            "output_dir": str(paper_output),
            "paper_text_path": str(
                copied_source_path if copied_source_path.is_file() else source_path
            ),
            "alpha25_coverage": {
                "complete": True,
                "task_count": len(task_paths),
                "rejected_facts": rejected,
                "recover_rejected": recover_rejected,
                "recover_unsupported": recover_unsupported,
                "recovery_requires_explicit_owner": True,
                "materialization_issues": [
                    *evidence_issues,
                    *promotion_issues,
                    *(issue.to_dict() for issue in materialized.issues),
                ],
                "promotion_enabled": promotion_enabled,
                "v201_gates": {
                    "global_tensile_scope": (
                        global_tensile_scope_v201_enabled()
                    ),
                    "same_table_property_merge": (
                        same_table_property_merge_v201_enabled()
                    ),
                },
                "v202_gates": {
                    "structured_table_cell_recovery": (
                        structured_table_cell_recovery_v202_enabled()
                    ),
                    "discrete_chart_sidecar": (
                        discrete_chart_sidecar_v202_enabled()
                    ),
                    "owner_state_condition": (
                        owner_state_condition_v202_enabled()
                    ),
                    "source_coordinate_precision": (
                        source_coordinate_precision_v202_enabled()
                    ),
                },
                **({"v203_gates": v203_gates} if any(v203_gates.values()) else {}),
                "promotion_input_fact_count": len(accepted_facts),
                "promotion_accepted_fact_count": len(promoted_facts),
                "promotion_issue_count": len(promotion_issues),
            },
        }
    )
    final_data = normalized.get("final_data") or {}
    paper_output.mkdir(parents=True, exist_ok=True)
    if normalized.get("v11_promotable"):
        (paper_output / "final.json").write_text(
            json.dumps(final_data, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

    validation = normalized.get("v11_validation") or {}
    return {
        "paper": paper_root.name,
        "task_cache_count": len(task_paths),
        "accepted_anchors": len(accepted_anchors),
        "accepted_facts": len(accepted_facts),
        "promoted_facts": len(promoted_facts),
        "promotion_issue_count": len(promotion_issues),
        "v201_global_tensile_scope": global_tensile_scope_v201_enabled(),
        "v201_same_table_property_merge": (
            same_table_property_merge_v201_enabled()
        ),
        "v202_structured_table_cell_recovery": (
            structured_table_cell_recovery_v202_enabled()
        ),
        "v202_discrete_chart_sidecar": discrete_chart_sidecar_v202_enabled(),
        "v202_owner_state_condition": owner_state_condition_v202_enabled(),
        "v202_source_coordinate_precision": (
            source_coordinate_precision_v202_enabled()
        ),
        **(
            {
                "v203_tensile_protocol_ledger": v203_gates[
                    "tensile_protocol_ledger"
                ],
                "v203_dense_tensile_table_completion": v203_gates[
                    "dense_tensile_table_completion"
                ],
                "v203_property_coordinate_quarantine": v203_gates[
                    "property_coordinate_quarantine"
                ],
            }
            if any(v203_gates.values())
            else {}
        ),
        "rejected_rows": rejected,
        "invalid_cache_files": invalid,
        "materialized_items": len(materialized.document.get("items", []) or []),
        "normalized_items": len(final_data.get("items", []) or []),
        "fatal_count": int(validation.get("fatal_count") or 0),
        "review_count": int(validation.get("review_count") or 0),
        "materialization_issue_count": len(promotion_issues) + len(materialized.issues),
        "promotable": bool(normalized.get("v11_promotable")),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runs-root", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--only", nargs="*", default=[])
    args = parser.parse_args()

    requested = set(args.only)
    paper_roots = sorted(
        path.parent.parent
        for path in args.runs_root.glob("*/v11/02_alpha25_tasks")
        if path.is_dir()
        and (not requested or path.parent.parent.name in requested)
    )
    if not paper_roots:
        parser.error(f"No Alpha25 task caches found under {args.runs_root}")
    args.output_root.mkdir(parents=True, exist_ok=True)

    rows: list[dict[str, Any]] = []
    failures: list[dict[str, str]] = []
    for paper_root in paper_roots:
        try:
            row = rebuild_paper(paper_root, args.output_root)
        except Exception as exc:
            failures.append({"paper": paper_root.name, "error": str(exc)})
            print(f"ERROR {paper_root.name}: {exc}")
            continue
        rows.append(row)
        print(
            f"{row['paper']}: tasks={row['task_cache_count']} "
            f"facts={row['accepted_facts']} items={row['normalized_items']} "
            f"fatal/review={row['fatal_count']}/{row['review_count']}"
        )

    summary = {"papers": rows, "failures": failures}
    summary_path = args.output_root / "rematerialize_summary.json"
    summary_path.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"Saved summary to {summary_path}")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
