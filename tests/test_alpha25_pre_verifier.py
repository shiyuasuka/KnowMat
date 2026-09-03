from __future__ import annotations

import json

import pytest

from knowmat.alpha25.pre_verifier import (
    PreVerifierDigestMismatch,
    build_pre_verifier_manifest,
    write_and_gate_pre_verifier_manifest,
)


def test_candidate_digest_is_order_independent_and_records_source_tasks(tmp_path):
    task_dir = tmp_path / "tasks"
    task_dir.mkdir()
    (task_dir / "a.json").write_text('{"value":1}\n', encoding="utf-8")
    facts = [
        {"axis": "properties", "value": 900},
        {"axis": "structure", "value": "alpha"},
    ]

    first = build_pre_verifier_manifest(
        facts,
        source_text="literal source",
        task_cache_dir=task_dir,
        planner_config={"bundle_chars": 6000},
        feature_switches={"promotion": True},
    )
    second = build_pre_verifier_manifest(
        reversed(facts),
        source_text="literal source",
        task_cache_dir=task_dir,
        planner_config={"bundle_chars": 6000},
        feature_switches={"promotion": True},
    )

    assert first["candidate_digest"] == second["candidate_digest"]
    assert first["candidate_count"] == 2
    assert first["task_cache_files"][0]["path"] == "a.json"
    assert first["source_sha256"]


def test_expected_digest_mismatch_is_persisted_then_fails_closed(tmp_path):
    control = tmp_path / "control" / "paper" / "v11"
    control.mkdir(parents=True)
    (control / "pre_verifier_manifest.json").write_text(
        json.dumps({"candidate_digest": "expected"}), encoding="utf-8"
    )
    output = tmp_path / "verified" / "paper" / "v11" / "pre_verifier_manifest.json"

    with pytest.raises(PreVerifierDigestMismatch):
        write_and_gate_pre_verifier_manifest(
            {"candidate_digest": "actual"},
            output_path=output,
            expected_root=tmp_path / "control",
            paper_key="paper",
        )

    written = json.loads(output.read_text(encoding="utf-8"))
    assert written["candidate_digest_matches_expected"] is False
    assert written["expected_candidate_digest"] == "expected"


def test_expected_digest_match_is_explicit_in_audit(tmp_path):
    control = tmp_path / "control" / "paper" / "v11"
    control.mkdir(parents=True)
    (control / "pre_verifier_manifest.json").write_text(
        json.dumps({"candidate_digest": "same"}), encoding="utf-8"
    )
    output = tmp_path / "verified.json"

    result = write_and_gate_pre_verifier_manifest(
        {"candidate_digest": "same"},
        output_path=output,
        expected_root=tmp_path / "control",
        paper_key="paper",
    )

    assert result["candidate_digest_matches_expected"] is True
