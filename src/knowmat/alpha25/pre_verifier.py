"""Reproducibility gate for post-promotion, pre-verifier candidates."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Iterable, Mapping

from knowmat.alpha25.verification_contracts import canonical_json


class PreVerifierDigestMismatch(RuntimeError):
    """Raised before provider calls when a control candidate digest differs."""


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _wire_fact(value: Any) -> Any:
    method = getattr(value, "model_dump", None)
    if callable(method):
        return method(mode="json")
    if isinstance(value, Mapping):
        return dict(value)
    raise TypeError("pre-verifier facts must be models or mappings")


def build_pre_verifier_manifest(
    facts: Iterable[Any],
    *,
    source_text: str,
    task_cache_dir: Path | None,
    planner_config: Mapping[str, Any],
    feature_switches: Mapping[str, Any],
) -> dict[str, Any]:
    """Hash immutable promoted candidates and record all replay authorities."""

    fact_payloads = [_wire_fact(row) for row in facts]
    fact_payloads.sort(key=canonical_json)
    candidate_payload = {"facts": fact_payloads}
    tasks = []
    if task_cache_dir is not None and task_cache_dir.is_dir():
        for path in sorted(
            row for row in task_cache_dir.rglob("*") if row.is_file()
        ):
            tasks.append(
                {
                    "path": str(path.relative_to(task_cache_dir)),
                    "sha256": _sha256_file(path),
                }
            )
    manifest = {
        "schema_version": "alpha25_pre_verifier_manifest_v1",
        "candidate_digest": _sha256_bytes(
            canonical_json(candidate_payload).encode("utf-8")
        ),
        "candidate_count": len(fact_payloads),
        "source_sha256": _sha256_bytes(source_text.encode("utf-8")),
        "task_cache_files": tasks,
        "task_cache_digest": _sha256_bytes(
            canonical_json(tasks).encode("utf-8")
        ),
        "planner_config": dict(planner_config),
        "feature_switches": dict(feature_switches),
    }
    manifest["reproducibility_digest"] = _sha256_bytes(
        canonical_json(manifest).encode("utf-8")
    )
    return manifest


def _expected_manifest(path: Path, paper_key: str) -> dict[str, Any]:
    target = path
    if path.is_dir():
        candidates = (
            path / paper_key / "v11" / "pre_verifier_manifest.json",
            path / paper_key / "pre_verifier_manifest.json",
            path / f"{paper_key}.json",
        )
        target = next((row for row in candidates if row.is_file()), candidates[0])
    value = json.loads(target.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("expected pre-verifier manifest must be a JSON object")
    if "candidate_digest" in value:
        return value
    papers = value.get("papers")
    if isinstance(papers, list):
        for row in papers:
            if not isinstance(row, dict):
                continue
            if str(row.get("paper") or row.get("paper_key") or row.get("output_name")) == paper_key:
                nested = row.get("pre_verifier_manifest")
                return nested if isinstance(nested, dict) else row
    digests = value.get("candidate_digests")
    if isinstance(digests, dict) and paper_key in digests:
        return {"candidate_digest": str(digests[paper_key])}
    raise KeyError(f"no expected pre-verifier digest for {paper_key}")


def write_and_gate_pre_verifier_manifest(
    manifest: Mapping[str, Any],
    *,
    output_path: Path,
    expected_root: Path | None,
    paper_key: str,
) -> dict[str, Any]:
    """Persist the audit record and abort before API use on digest mismatch."""

    payload = dict(manifest)
    expected_digest = None
    if expected_root is not None:
        expected = _expected_manifest(expected_root, paper_key)
        expected_digest = str(expected.get("candidate_digest") or "")
        payload["expected_candidate_digest"] = expected_digest
        payload["candidate_digest_matches_expected"] = (
            expected_digest == str(payload.get("candidate_digest") or "")
        )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    if expected_digest is not None and not payload[
        "candidate_digest_matches_expected"
    ]:
        raise PreVerifierDigestMismatch(
            "pre-verifier candidate digest differs from the matching control"
        )
    return payload


__all__ = [
    "PreVerifierDigestMismatch",
    "build_pre_verifier_manifest",
    "write_and_gate_pre_verifier_manifest",
]
