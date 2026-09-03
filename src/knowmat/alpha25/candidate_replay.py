"""Content-addressed replay of frozen Alpha25 task responses.

The replay contract stages only provider response caches.  The normal online
planner, evidence gate, promotion, verification, and materialization paths are
still executed, so a cache identity mismatch fails closed instead of silently
changing the candidate draw.
"""

from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path
from typing import Any, Mapping


REPLAY_SCHEMA_VERSION = "knowmat_alpha25_candidate_replay_v1"


class CandidateReplayError(RuntimeError):
    """Raised when a frozen task-response set is incomplete or inconsistent."""


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _read_object(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise CandidateReplayError(f"Invalid replay JSON: {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise CandidateReplayError(f"Replay JSON must be an object: {path}")
    return value


def task_cache_dir(root: Path) -> Path:
    """Resolve either a paper root or a direct Alpha25 task-cache directory."""

    candidate = root.expanduser().resolve()
    nested = candidate / "v11" / "02_alpha25_tasks"
    return nested if nested.is_dir() else candidate


def build_candidate_replay_manifest(root: Path) -> dict[str, Any]:
    """Validate and fingerprint one immutable Alpha25 response-cache set."""

    cache_dir = task_cache_dir(root)
    if not cache_dir.is_dir():
        raise CandidateReplayError(f"Missing Alpha25 task cache: {cache_dir}")
    responses = sorted(
        path
        for path in cache_dir.glob("*.json")
        if not path.name.endswith(".recovery.json")
    )
    if not responses:
        raise CandidateReplayError(f"No Alpha25 task responses under {cache_dir}")

    rows: list[dict[str, Any]] = []
    expected_files: set[str] = set()
    for response_path in responses:
        identity_path = response_path.with_name(response_path.name + ".identity")
        if not identity_path.is_file():
            raise CandidateReplayError(
                f"Missing task identity sidecar: {identity_path}"
            )
        identity = _read_object(identity_path)
        recorded_response_hash = str(identity.get("response_sha256") or "")
        response_hash = _sha256(response_path)
        if not recorded_response_hash or recorded_response_hash != response_hash:
            raise CandidateReplayError(
                "Task response hash mismatch: "
                f"{response_path.name} recorded={recorded_response_hash or '<missing>'} "
                f"actual={response_hash}"
            )
        task_identity = identity.get("task_identity")
        if not isinstance(task_identity, dict):
            raise CandidateReplayError(
                f"Missing task identity payload: {identity_path}"
            )
        rows.append(
            {
                "response_path": response_path.name,
                "response_sha256": response_hash,
                "identity_path": identity_path.name,
                "identity_sha256": _sha256(identity_path),
                "task_id": str(task_identity.get("task_id") or ""),
                "unit_id": str(task_identity.get("unit_id") or ""),
                "axis": str(task_identity.get("axis") or ""),
                "evidence_sha256": str(
                    task_identity.get("evidence_sha256") or ""
                ),
            }
        )
        expected_files.update({response_path.name, identity_path.name})

    recovery_markers = sorted(cache_dir.glob("*.recovery.json"))
    if recovery_markers:
        names = ", ".join(path.name for path in recovery_markers[:5])
        raise CandidateReplayError(
            "Frozen replay cannot contain unresolved recovery markers: " + names
        )
    unexpected = sorted(
        path.name
        for path in cache_dir.iterdir()
        if path.is_file() and path.name not in expected_files
    )
    if unexpected:
        raise CandidateReplayError(
            "Unexpected files in Alpha25 task cache: " + ", ".join(unexpected)
        )

    content = {
        "schema_version": REPLAY_SCHEMA_VERSION,
        "response_count": len(rows),
        "responses": rows,
    }
    content["content_sha256"] = hashlib.sha256(
        json.dumps(content, ensure_ascii=False, sort_keys=True).encode("utf-8")
    ).hexdigest()
    return content


def stage_candidate_replay_cache(
    source_root: Path,
    destination_root: Path,
) -> dict[str, Any]:
    """Copy a validated frozen cache into an empty destination task directory."""

    source_dir = task_cache_dir(source_root)
    destination_dir = destination_root.expanduser().resolve()
    if source_dir.resolve() == destination_dir:
        raise CandidateReplayError("Replay source and destination must differ")
    if destination_dir.exists() and any(destination_dir.iterdir()):
        raise CandidateReplayError(
            f"Replay destination task cache is not empty: {destination_dir}"
        )
    source_manifest = build_candidate_replay_manifest(source_dir)
    destination_dir.mkdir(parents=True, exist_ok=True)
    shutil.copytree(source_dir, destination_dir, dirs_exist_ok=True)
    destination_manifest = build_candidate_replay_manifest(destination_dir)
    if destination_manifest != source_manifest:
        raise CandidateReplayError("Staged candidate replay cache changed in transit")
    return source_manifest


def assert_cache_only_replay(
    coverage: Mapping[str, Any],
    staged_manifest: Mapping[str, Any],
    output_manifest: Mapping[str, Any],
) -> None:
    """Fail if extraction did anything other than consume the staged responses."""

    if dict(staged_manifest) != dict(output_manifest):
        raise CandidateReplayError("Output task cache differs from staged replay cache")
    response_count = int(staged_manifest.get("response_count") or 0)
    task_count = int(coverage.get("task_count") or 0)
    if task_count != response_count:
        raise CandidateReplayError(
            "Replay did not consume exactly the staged task set: "
            f"tasks={task_count} responses={response_count}"
        )
    states = coverage.get("states") or {}
    if not isinstance(states, Mapping):
        raise CandidateReplayError("Replay coverage has no task-state summary")
    disallowed = {
        str(state): int(count)
        for state, count in states.items()
        if str(state) not in {"cached", "split", "merged"} and int(count or 0)
    }
    if disallowed:
        raise CandidateReplayError(
            "Replay executed or left incomplete extraction tasks: "
            + json.dumps(disallowed, sort_keys=True)
        )
    cached = int(states.get("cached") or 0)
    if cached <= 0:
        raise CandidateReplayError("Replay reported no cached extraction tasks")
    if float(coverage.get("provider_call_elapsed_sum") or 0.0) != 0.0:
        raise CandidateReplayError("Replay unexpectedly recorded extraction provider time")
