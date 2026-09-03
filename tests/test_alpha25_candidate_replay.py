import hashlib
import json
from pathlib import Path

import pytest

from knowmat.alpha25.candidate_replay import (
    CandidateReplayError,
    assert_cache_only_replay,
    build_candidate_replay_manifest,
    stage_candidate_replay_cache,
)


def _write_task(cache_dir: Path, name: str = "combined_abcd.json") -> Path:
    cache_dir.mkdir(parents=True, exist_ok=True)
    response = cache_dir / name
    response.write_text(
        json.dumps({"axis": "combined", "anchors": [], "facts": []}) + "\n",
        encoding="utf-8",
    )
    response_hash = hashlib.sha256(response.read_bytes()).hexdigest()
    identity = response.with_name(response.name + ".identity")
    identity.write_text(
        json.dumps(
            {
                "cache_record_type": "alpha25_task_identity",
                "version": 1,
                "task_identity": {
                    "task_id": "combined:unit-1",
                    "unit_id": "unit-1",
                    "axis": "combined",
                    "evidence_sha256": "evidence-hash",
                },
                "response_sha256": response_hash,
            }
        )
        + "\n",
        encoding="utf-8",
    )
    return response


def test_candidate_replay_manifest_and_stage_are_content_addressed(tmp_path):
    source = tmp_path / "source-paper" / "v11" / "02_alpha25_tasks"
    _write_task(source)

    first = build_candidate_replay_manifest(source.parent.parent)
    second = stage_candidate_replay_cache(
        source.parent.parent,
        tmp_path / "output-paper" / "v11" / "02_alpha25_tasks",
    )

    assert first == second
    assert first["response_count"] == 1
    assert len(first["content_sha256"]) == 64
    assert first["responses"][0]["task_id"] == "combined:unit-1"


def test_candidate_replay_rejects_missing_identity_and_corruption(tmp_path):
    cache = tmp_path / "cache"
    response = _write_task(cache)
    response.with_name(response.name + ".identity").unlink()
    with pytest.raises(CandidateReplayError, match="Missing task identity"):
        build_candidate_replay_manifest(cache)

    response = _write_task(cache)
    response.write_text("{}\n", encoding="utf-8")
    with pytest.raises(CandidateReplayError, match="hash mismatch"):
        build_candidate_replay_manifest(cache)


def test_candidate_replay_rejects_nonempty_destination(tmp_path):
    source = tmp_path / "source"
    _write_task(source)
    destination = tmp_path / "destination"
    destination.mkdir()
    (destination / "user-file.txt").write_text("preserve", encoding="utf-8")

    with pytest.raises(CandidateReplayError, match="not empty"):
        stage_candidate_replay_cache(source, destination)
    assert (destination / "user-file.txt").read_text() == "preserve"


def test_cache_only_replay_requires_all_cached_and_zero_provider_time(tmp_path):
    source = tmp_path / "source"
    _write_task(source)
    manifest = build_candidate_replay_manifest(source)
    coverage = {
        "task_count": 1,
        "states": {"cached": 1},
        "provider_call_elapsed_sum": 0.0,
    }

    assert_cache_only_replay(coverage, manifest, manifest)

    with pytest.raises(CandidateReplayError, match="executed"):
        assert_cache_only_replay(
            {**coverage, "states": {"succeeded": 1}}, manifest, manifest
        )
    with pytest.raises(CandidateReplayError, match="provider time"):
        assert_cache_only_replay(
            {**coverage, "provider_call_elapsed_sum": 0.1}, manifest, manifest
        )
