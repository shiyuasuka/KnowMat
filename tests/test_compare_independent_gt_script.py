from __future__ import annotations

import importlib.util
import hashlib
import json
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = REPO_ROOT / "scripts" / "compare_independent_gt.py"
SPEC = importlib.util.spec_from_file_location("compare_independent_gt_script", MODULE_PATH)
assert SPEC and SPEC.loader
module = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(module)


def _write_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value), encoding="utf-8")


def test_adjudicated_claim_root_requires_passed_materialization(tmp_path: Path) -> None:
    _write_json(tmp_path / "corpus_summary.json", {"validation": {"status": "failed"}})
    with pytest.raises(ValueError, match="has not passed"):
        module._expert_claims_root(tmp_path, use_adjudicated=True)

    _write_json(tmp_path / "corpus_summary.json", {"validation": {"status": "passed"}})
    variant, path = module._expert_claims_root(tmp_path, use_adjudicated=True)
    assert variant == "adjudicated"
    assert path == tmp_path / "adjudicated"


def test_adjudication_summary_aggregates_numeric_tags(tmp_path: Path) -> None:
    for index, value in ((1, 2), (2, 3)):
        _write_json(
            tmp_path / "adjudicated" / f"paper_{index:03d}" / "adjudication.json",
            {
                "systems": {
                    "business_gt": {"confirmed_correct": value, "wrong_owner": 1},
                    "final_v5": {"confirmed_correct": value + 1, "duplicate_claim": value},
                }
            },
        )
    summary = module._adjudication_summary(tmp_path, ["paper_001", "paper_002"])
    assert summary["totals"]["business_gt"]["confirmed_correct"] == 5
    assert summary["totals"]["business_gt"]["wrong_owner"] == 2
    assert summary["totals"]["final_v5"]["confirmed_correct"] == 7
    assert summary["totals"]["final_v5"]["duplicate_claim"] == 5


def test_verify_blind_seal_checks_digest_and_size(tmp_path: Path) -> None:
    artifact = tmp_path / "artifact.json"
    artifact.write_text("{}\n", encoding="utf-8")
    digest = hashlib.sha256(artifact.read_bytes()).hexdigest()
    seal = {
        "artifacts": [
            {
                "path": "artifact.json",
                "sha256": digest,
                "size": artifact.stat().st_size,
            }
        ]
    }
    assert module._verify_blind_seal(seal, tmp_path)["status"] == "passed"
    artifact.write_text("changed\n", encoding="utf-8")
    failed = module._verify_blind_seal(seal, tmp_path)
    assert failed["status"] == "failed"
    assert failed["mismatch_count"] == 1
