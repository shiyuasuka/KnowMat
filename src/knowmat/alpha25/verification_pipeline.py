"""Paper-level orchestration for verification and one-pass recovery."""

from __future__ import annotations

import logging
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from typing import Any, Iterable, Mapping, Sequence

from knowmat.alpha25.contracts import AxisFact, InventoryAnchor
from knowmat.alpha25.verification_client import VerificationClient
from knowmat.alpha25.verification_inventory import (
    build_recovery_requests,
    build_verification_bundles,
    build_verification_inventory,
)


logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class PaperVerificationResult:
    accepted: tuple[AxisFact, ...]
    task_ids: tuple[str | None, ...]
    audit_records: tuple[dict[str, Any], ...]
    issues: tuple[dict[str, Any], ...]
    metrics: dict[str, Any]


def _sum_metrics(rows: Iterable[dict[str, Any]]) -> dict[str, Any]:
    integer_keys = (
        "provider_calls",
        "cache_hits",
        "primary_failures",
        "fallback_calls",
        "fallback_failures",
        "unresolved_bundles",
        "preserved_unresolved_assertions",
        "destructive_confirmation_calls",
        "destructive_confirmation_failures",
        "destructive_confirmation_skipped_count",
        "destructive_candidate_count",
        "confirmed_quarantine_count",
        "preserved_destructive_disagreement_count",
        "retry_count",
        "capability_fallback_count",
        "split_retry_count",
    )
    result: dict[str, Any] = {key: 0 for key in integer_keys}
    result.update({"elapsed_seconds": 0.0, "provider_call_seconds": 0.0})
    failures: dict[str, int] = {}
    for row in rows:
        for key in integer_keys:
            result[key] += int(row.get(key, 0))
        result["elapsed_seconds"] += float(row.get("elapsed_seconds", 0.0))
        result["provider_call_seconds"] += float(
            row.get("provider_call_seconds", 0.0)
        )
        for code, count in (row.get("failures_by_code") or {}).items():
            failures[str(code)] = failures.get(str(code), 0) + int(count)
    result["failures_by_code"] = dict(sorted(failures.items()))
    return result


def _preserved_without_request(
    assertion_id: str,
    *,
    candidate: dict[str, Any],
    sample_id_raw: str,
    axis: str,
    reason_code: str,
    after: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    audit = {
        "assertion_id": assertion_id,
        "bundle_id": "not_sent",
        "protocol_version": "alpha25_hierarchical_verification_v1",
        "decision": "unresolved",
        "reason_code": reason_code,
        "before": candidate,
        "after": after,
        "evidence": [],
        "verifier_role": "deterministic",
        "fallback_used": False,
        "cache_hit": False,
        "rationale": "The candidate could not be placed in a source-grounded bounded verifier request.",
    }
    issue = {
        "code": "verifier_unresolved_preserved",
        "severity": "review",
        "path": f"items.{sample_id_raw}.{axis}",
        "message": reason_code,
        "evidence": [],
        "expected": {"assertion_id": assertion_id, "bounded_source_evidence": True},
        "actual": {
            "assertion_id": assertion_id,
            "decision": "unresolved",
            "formal_output": "preserved_pending_review",
            "reason_code": reason_code,
        },
        "suggested_action": "Review the complete linked record in quality_audit.json.",
    }
    return audit, issue


def verify_paper_candidates(
    anchors: Iterable[InventoryAnchor],
    facts: Iterable[AxisFact],
    *,
    source_text: str,
    task_ids: Sequence[str | None] | None,
    task_source_scopes: Mapping[str, str] | None = None,
    client: VerificationClient,
    max_bundle_assertions: int = 12,
    max_bundle_source_chars: int = 12000,
    context_radius: int = 500,
    recovery_enabled: bool = True,
    max_recovery_assertions: int = 10,
    workers: int = 4,
    bypass_axes: Sequence[str] = ("composition",),
) -> PaperVerificationResult:
    """Run complete paper verification while preserving Composition exactly."""

    started = time.monotonic()
    fact_rows = list(facts)
    lineage = list(task_ids) if task_ids is not None else [None] * len(fact_rows)
    if len(lineage) != len(fact_rows):
        raise ValueError("task_ids must contain exactly one entry per fact")
    protected_axes = {str(axis).strip().casefold() for axis in bypass_axes}
    protected_axes.add("composition")
    verification_pairs = [
        (fact, task_id)
        for fact, task_id in zip(fact_rows, lineage)
        if fact.axis.casefold() not in protected_axes
    ]
    verification_facts = [row[0] for row in verification_pairs]
    verification_task_ids = [row[1] for row in verification_pairs]
    anchor_rows = list(anchors)
    inventory = build_verification_inventory(
        anchor_rows,
        verification_facts,
        source_text=source_text,
        task_ids=verification_task_ids,
        task_source_scopes=task_source_scopes,
    )
    bundles = build_verification_bundles(
        inventory,
        source_text=source_text,
        max_assertions=max_bundle_assertions,
        max_source_chars=max_bundle_source_chars,
        context_radius=context_radius,
    )

    def verify_with_bisection(bundle):
        """Localize a double-verifier failure without accepting a partial bundle."""

        parent = client.verify_bundle(bundle, inventory)
        attempt_metrics = [parent.metrics]
        if not int(parent.metrics.get("unresolved_bundles", 0)) or len(bundle.assertions) <= 1:
            return [parent], attempt_metrics, 0

        assertion_ids = {row.assertion_id for row in bundle.assertions}
        subset = type(inventory)(
            anchors=inventory.anchors,
            assertions=tuple(bundle.assertions),
            entities=inventory.entities,
            evidence=inventory.evidence,
            recovery_evidence=(),
            facts_by_assertion_id={
                assertion_id: inventory.facts_by_assertion_id[assertion_id]
                for assertion_id in assertion_ids
            },
            ungrounded_assertion_ids=(),
        )
        children = build_verification_bundles(
            subset,
            source_text=source_text,
            max_assertions=max(1, len(bundle.assertions) // 2),
            max_source_chars=max_bundle_source_chars,
            context_radius=context_radius,
        )
        child_ids = {
            row.assertion_id for child in children for row in child.assertions
        }
        if len(children) <= 1 or child_ids != assertion_ids:
            return [parent], attempt_metrics, 0

        leaves = []
        split_count = 1
        for child in children:
            child_leaves, child_metrics, child_splits = verify_with_bisection(child)
            leaves.extend(child_leaves)
            attempt_metrics.extend(child_metrics)
            split_count += child_splits
        return leaves, attempt_metrics, split_count

    bundle_results = []
    bundle_attempt_metrics: list[dict[str, Any]] = []
    split_retry_count = 0
    if bundles:
        # Capability discovery is intentionally serialized inside the client so
        # one rejected optional provider flag does not cause a request storm.
        # Seed it with the smallest real bundle instead of allowing an
        # arbitrarily large first bundle to block every worker behind the
        # discovery lock.
        ordered_bundles = sorted(
            bundles,
            key=lambda bundle: (
                sum(len(row.text) for row in bundle.evidence),
                len(bundle.assertions),
                bundle.bundle_id,
            ),
        )
        seed = ordered_bundles[0]
        seed_results, seed_metrics, seed_splits = verify_with_bisection(seed)
        bundle_results.extend(seed_results)
        bundle_attempt_metrics.extend(seed_metrics)
        split_retry_count += seed_splits
        seed_summary = _sum_metrics(seed_metrics)
        logger.warning(
            "Alpha25 verification progress: completed=1/%d bundle=%s "
            "calls=%d fallback=%d unresolved=%d splits=%d",
            len(ordered_bundles),
            seed.bundle_id,
            int(seed_summary.get("provider_calls", 0)),
            int(seed_summary.get("fallback_calls", 0)),
            sum(int(row.metrics.get("unresolved_bundles", 0)) for row in seed_results),
            seed_splits,
        )
        remaining = ordered_bundles[1:]
        with ThreadPoolExecutor(max_workers=max(1, min(workers, len(remaining)))) as pool:
            pending = {
                pool.submit(verify_with_bisection, bundle): bundle.bundle_id
                for bundle in remaining
            }
            completed = 1
            for future in as_completed(pending):
                results, attempt_metrics, splits = future.result()
                bundle_results.extend(results)
                bundle_attempt_metrics.extend(attempt_metrics)
                split_retry_count += splits
                completed += 1
                summary = _sum_metrics(attempt_metrics)
                logger.warning(
                    "Alpha25 verification progress: completed=%d/%d bundle=%s "
                    "calls=%d fallback=%d unresolved=%d splits=%d",
                    completed,
                    len(ordered_bundles),
                    pending[future],
                    int(summary.get("provider_calls", 0)),
                    int(summary.get("fallback_calls", 0)),
                    sum(int(row.metrics.get("unresolved_bundles", 0)) for row in results),
                    splits,
                )
    bundle_results.sort(
        key=lambda row: tuple(row.applied.decided_assertion_ids)
    )

    accepted_by_assertion: dict[str, AxisFact] = {}
    decided: set[str] = set()
    audits: list[dict[str, Any]] = []
    issues: list[dict[str, Any]] = []
    metric_rows: list[dict[str, Any]] = list(bundle_attempt_metrics)
    for result in bundle_results:
        audits.extend(result.applied.audit_records)
        issues.extend(result.applied.issues)
        decided.update(result.applied.decided_assertion_ids)
        accepted_by_assertion.update(
            zip(result.applied.accepted_assertion_ids, result.applied.accepted)
        )

    preserved_without_request_count = 0
    for assertion in inventory.assertions:
        if assertion.assertion_id in decided:
            continue
        reason = (
            "SOURCE_EVIDENCE_NOT_LOCATED"
            if assertion.assertion_id in inventory.ungrounded_assertion_ids
            else "EVIDENCE_EXCEEDS_BUNDLE_LIMIT"
        )
        fact = inventory.facts_by_assertion_id[assertion.assertion_id]
        accepted_by_assertion[assertion.assertion_id] = fact
        preserved_without_request_count += 1
        audit, issue = _preserved_without_request(
            assertion.assertion_id,
            candidate=assertion.candidate,
            sample_id_raw=assertion.sample_id_raw,
            axis=assertion.axis,
            reason_code=reason,
            after=fact.model_dump(mode="json"),
        )
        audits.append(audit)
        issues.append(issue)

    assertion_by_fact_object = {
        id(fact): assertion_id
        for assertion_id, fact in inventory.facts_by_assertion_id.items()
    }
    accepted: list[AxisFact] = []
    accepted_task_ids: list[str | None] = []
    assertion_by_id = {row.assertion_id: row for row in inventory.assertions}
    for fact, task_id in zip(fact_rows, lineage):
        if fact.axis.casefold() in protected_axes:
            accepted.append(fact)
            accepted_task_ids.append(task_id)
            continue
        assertion_id = assertion_by_fact_object.get(id(fact))
        if assertion_id and assertion_id in accepted_by_assertion:
            accepted.append(accepted_by_assertion[assertion_id])
            accepted_task_ids.append(assertion_by_id[assertion_id].task_id)

    recovery_count = 0
    if recovery_enabled:
        requests = build_recovery_requests(
            inventory,
            max_assertions=max_recovery_assertions,
            max_source_chars=max_bundle_source_chars,
        )
        recovery_results = []
        if requests:
            with ThreadPoolExecutor(
                max_workers=max(1, min(workers, len(requests)))
            ) as pool:
                pending = {
                    pool.submit(
                        client.recover_request,
                        request,
                        inventory,
                        source_text=source_text,
                    ): request.request_id
                    for request in requests
                }
                for future in as_completed(pending):
                    recovery_results.append((pending[future], future.result()))
        for _request_id, result in sorted(recovery_results):
            metric_rows.append(result.metrics)
            accepted.extend(result.applied.accepted)
            accepted_task_ids.extend([None] * len(result.applied.accepted))
            recovery_count += len(result.applied.accepted)
            audits.extend(result.applied.audit_records)
            issues.extend(result.applied.issues)

    metrics = _sum_metrics(metric_rows)
    metrics["preserved_unresolved_assertions"] = int(
        metrics.get("preserved_unresolved_assertions", 0)
    ) + preserved_without_request_count
    metrics["attempt_unresolved_bundles"] = int(
        metrics.get("unresolved_bundles", 0)
    )
    metrics["unresolved_bundles"] = sum(
        int(result.metrics.get("unresolved_bundles", 0))
        for result in bundle_results
    )
    metrics["split_retry_count"] = split_retry_count
    metrics.update(
        {
            "input_fact_count": len(fact_rows),
            "composition_bypass_count": sum(
                fact.axis == "composition" for fact in fact_rows
            ),
            "protected_axis_bypass_count": sum(
                fact.axis.casefold() in protected_axes for fact in fact_rows
            ),
            "protected_axes": sorted(protected_axes),
            "verification_assertion_count": len(inventory.assertions),
            "verification_bundle_count": len(bundles),
            "verification_leaf_bundle_count": len(bundle_results),
            "uncovered_recovery_evidence_count": len(inventory.recovery_evidence),
            "recovered_fact_count": recovery_count,
            "accepted_fact_count": len(accepted),
            "audit_record_count": len(audits),
            "issue_count": len(issues),
            "wall_seconds": time.monotonic() - started,
        }
    )
    audits.sort(
        key=lambda row: (
            str(row.get("assertion_id") or ""),
            str(row.get("decision") or ""),
            str(row.get("reason_code") or ""),
        )
    )
    issues.sort(
        key=lambda row: (
            str(row.get("code") or ""),
            str((row.get("actual") or {}).get("assertion_id") or ""),
        )
    )
    return PaperVerificationResult(
        accepted=tuple(accepted),
        task_ids=tuple(accepted_task_ids),
        audit_records=tuple(audits),
        issues=tuple(issues),
        metrics=metrics,
    )


__all__ = ["PaperVerificationResult", "verify_paper_candidates"]
