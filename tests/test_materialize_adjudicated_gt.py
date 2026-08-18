from __future__ import annotations

import importlib.util
import ast
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = REPO_ROOT / "scripts" / "materialize_adjudicated_gt.py"
SPEC = importlib.util.spec_from_file_location("materialize_adjudicated_gt", MODULE_PATH)
assert SPEC and SPEC.loader
module = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(module)


def test_materializer_source_has_no_unbound_json_boolean_literals() -> None:
    tree = ast.parse(MODULE_PATH.read_text(encoding="utf-8"))
    unbound_json_literals = {
        node.id
        for node in ast.walk(tree)
        if isinstance(node, ast.Name) and node.id in {"true", "false", "null"}
    }
    assert unbound_json_literals == set()


def _claim(claim_id: str, value: float = 1.0) -> dict:
    return {
        "claim_id": claim_id,
        "paper_key": "paper",
        "axis": "Properties",
        "owner": {"material_id": "m1", "material_name": "alloy", "sample_id": "s1", "state": None, "region": None, "orientation": None, "role": "Target"},
        "semantic_key": "yield_strength",
        "name_raw": "yield strength",
        "value": {"kind": "scalar", "raw": str(value), "number": value, "min": None, "max": None, "operator": None, "bound": None, "stddev": None, "text": None},
        "unit_raw": "MPa",
        "condition": {"raw": None, "temperature_raw": None, "time_raw": None, "rate_raw": None, "environment_raw": None, "details": {}},
        "origin": "author_experiment",
        "evidence": [],
        "confidence": 1.0,
        "review_status": "accepted",
        "notes": None,
    }


def _amend(action: str, *, sealed: str | None, corrected: dict | None) -> dict:
    return {"action": action, "sealed_claim_id": sealed, "corrected_claim": corrected, "reason": "evidence adjudication", "evidence_quote": "source quote", "evidence_locator": "line 1"}


def test_apply_add_replace_remove_and_rejection() -> None:
    replacement = _claim("clm_0001", 2.0)
    added = _claim("clm_9001", 3.0)
    rejected = _claim("clm_9002", 4.0)
    claims, audit = module.apply_amendments(
        [_claim("clm_0001"), _claim("clm_0002")],
        [
            _amend("replace", sealed="clm_0001", corrected=replacement),
            _amend("remove", sealed="clm_0002", corrected=None),
            _amend("add", sealed=None, corrected=added),
            _amend("add", sealed=None, corrected=rejected),
        ],
        paper_id="paper_001",
        rejected={("paper_001", "clm_9002")},
    )
    assert [row["claim_id"] for row in claims] == ["clm_0001", "clm_9001"]
    assert claims[0]["value"]["number"] == 2.0
    assert [row["action"] for row in audit] == ["update", "delete", "create"]


def test_apply_rejects_duplicate_add() -> None:
    with pytest.raises(ValueError, match="duplicates"):
        module.apply_amendments(
            [_claim("clm_0001")],
            [_amend("add", sealed=None, corrected=_claim("clm_0001"))],
            paper_id="paper_001",
            rejected=set(),
        )
