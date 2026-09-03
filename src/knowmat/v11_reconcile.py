"""Generic, evidence-preserving reconciliation for v11 candidates.

This compatibility module deliberately contains no material, paper, process, or
sample-specific alias table.  New alpha25 extraction materializes compact facts in
``knowmat.alpha25.materialize``; legacy callers may still merge complete candidates
through the small wrappers below.
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from knowmat.alpha25.materialize import reconcile_candidate_documents


def reconcile_v11_candidates(candidates: list[dict[str, Any]]) -> dict[str, Any]:
    """Merge candidates by exact normalized source identity only."""

    return reconcile_candidate_documents(candidates)


def merge_canonical_v11_items(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Collapse exact duplicate item identities without guessing aliases."""

    if not items:
        return []
    candidate = {
        "Paper_Metadata": {},
        "Paper_Routing": {},
        "items": [deepcopy(item) for item in items],
    }
    return reconcile_candidate_documents([candidate])["items"]


__all__ = ["merge_canonical_v11_items", "reconcile_v11_candidates"]
