#!/usr/bin/env python3
"""Run Alpha25 extraction only from frozen Markdown and frozen routing.

This runner intentionally bypasses OCR, figure/VLM enrichment, routing LLMs,
evaluation agents, and manager agents.  It is used for isolated extraction
model trials where every non-extraction input must remain byte-identical.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

from knowmat.app_config import settings  # noqa: E402
from knowmat.alpha25.candidate_replay import (  # noqa: E402
    assert_cache_only_replay,
    build_candidate_replay_manifest,
    stage_candidate_replay_cache,
)
from knowmat.nodes.extraction import extract_data  # noqa: E402
from knowmat.nodes.subfield_detection import _build_routing_supplements  # noqa: E402
from knowmat.nodes.v11_normalize import normalize_v11  # noqa: E402


@dataclass(frozen=True)
class PaperSpec:
    paper_id: str
    paper_key: str
    source_path: Path
    source_sha256: str
    routing_paper_root: Path

    @property
    def output_name(self) -> str:
        return self.routing_paper_root.name


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _read_object(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"Expected JSON object: {path}")
    return value


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _relative_or_absolute(value: str, *, base: Path) -> Path:
    path = Path(value)
    return path if path.is_absolute() else (base / path).resolve()


def load_paper_specs(
    experiment_manifest_path: Path,
    *,
    pilot: bool,
    requested_ids: set[str],
) -> tuple[dict[str, Any], list[PaperSpec]]:
    """Resolve frozen source and routing paths without consulting any GT."""

    manifest = _read_object(experiment_manifest_path)
    base = REPO_ROOT
    papers = manifest.get("inputs", {}).get("papers", [])
    by_id = {
        str(row.get("paper_id")): row
        for row in papers
        if isinstance(row, dict) and row.get("paper_id")
    }
    selected = set(requested_ids)
    if pilot:
        selected.update(str(row) for row in manifest.get("pilot", {}).get("paper_ids", []))
    if not selected:
        selected = set(by_id)
    unknown = sorted(selected - set(by_id))
    if unknown:
        raise ValueError("Unknown paper IDs in selection: " + ", ".join(unknown))

    pilot_sources: dict[str, dict[str, Any]] = {}
    pilot_manifest_path = experiment_manifest_path.parent / "pilot_input_manifest.json"
    if pilot and pilot_manifest_path.is_file():
        pilot_manifest = _read_object(pilot_manifest_path)
        pilot_sources = {
            str(row.get("paper_id")): row
            for row in pilot_manifest.get("papers", [])
            if isinstance(row, dict) and row.get("paper_id")
        }

    specs: list[PaperSpec] = []
    for paper_id in sorted(selected):
        row = by_id[paper_id]
        enhanced = row.get("enhanced_markdown") or {}
        route_source = _relative_or_absolute(str(enhanced.get("path") or ""), base=base)
        if not route_source.is_file():
            raise FileNotFoundError(f"Missing frozen enhanced Markdown: {route_source}")
        source_path = route_source
        expected_sha = str(enhanced.get("sha256") or "")
        if paper_id in pilot_sources:
            pilot_row = pilot_sources[paper_id]
            source_path = _relative_or_absolute(str(pilot_row.get("staged") or ""), base=base)
            expected_sha = str(pilot_row.get("sha256") or expected_sha)
        if not source_path.is_file():
            raise FileNotFoundError(f"Missing frozen extraction input: {source_path}")
        actual_sha = _sha256(source_path)
        if not expected_sha or actual_sha != expected_sha:
            raise RuntimeError(
                f"Frozen input hash mismatch for {paper_id}: "
                f"expected={expected_sha or '<missing>'} actual={actual_sha}"
            )
        specs.append(
            PaperSpec(
                paper_id=paper_id,
                paper_key=str(row.get("paper_key") or source_path.stem),
                source_path=source_path,
                source_sha256=actual_sha,
                routing_paper_root=route_source.parent.parent,
            )
        )
    return manifest, specs


def _configure_effective_capabilities(
    manifest: dict[str, Any], capability_probe: dict[str, Any], model: str
) -> dict[str, str]:
    if capability_probe.get("status") != "ok":
        raise RuntimeError("Extraction capability probe did not succeed")
    if str(capability_probe.get("model") or "") != model:
        raise RuntimeError(
            "Capability probe model mismatch: "
            f"probe={capability_probe.get('model')} requested={model}"
        )
    safe_environment = manifest.get("provider", {}).get("safe_environment", {})
    applied: dict[str, str] = {}
    for key, value in safe_environment.items():
        if not str(key).startswith("KNOWMAT2_"):
            continue
        os.environ[str(key)] = str(value)
        applied[str(key)] = str(value)

    effective = capability_probe.get("effective") or {}
    thinking_mode = str(effective.get("thinking_mode") or "provider_default")
    response_format = str(effective.get("response_format") or "text")
    os.environ["KNOWMAT2_EXTRACTION_THINKING"] = thinking_mode
    applied["KNOWMAT2_EXTRACTION_THINKING"] = thinking_mode
    if response_format == "json_object":
        os.environ["KNOWMAT2_EXTRACTION_RESPONSE_FORMAT"] = "json_object"
        applied["KNOWMAT2_EXTRACTION_RESPONSE_FORMAT"] = "json_object"
    else:
        os.environ.pop("KNOWMAT2_EXTRACTION_RESPONSE_FORMAT", None)
        applied["KNOWMAT2_EXTRACTION_RESPONSE_FORMAT"] = "text"

    # This process performs no figure generation.  The frozen Markdown already
    # contains the approved chart context, so a second enrichment would violate
    # the isolated-model experiment.
    settings.figure_description_enabled = False
    return applied


def _copy_frozen_source(spec: PaperSpec, paper_output: Path) -> Path:
    source_dir = spec.source_path.parent
    output_txt_parse = paper_output / "txt_parse"
    shutil.copytree(source_dir, output_txt_parse, dirs_exist_ok=True)
    copied = output_txt_parse / spec.source_path.name
    canonical = output_txt_parse / f"{spec.paper_key}_final_output.md"
    if copied != canonical:
        shutil.copy2(copied, canonical)
    if _sha256(canonical) != spec.source_sha256:
        raise RuntimeError(f"Copied frozen input hash changed for {spec.paper_id}")
    return canonical


def _load_frozen_routing(spec: PaperSpec) -> tuple[dict[str, Any], dict[str, Any]]:
    route_path = spec.routing_paper_root / "v11" / "01_routing.json"
    payload = _read_object(route_path)
    routing = payload.get("routing")
    identity = payload.get("identity")
    if not isinstance(routing, dict) or not isinstance(identity, dict):
        raise ValueError(f"Invalid frozen routing payload: {route_path}")
    return payload, dict(routing)


def _task_audit(
    paper_output: Path,
    *,
    model: str,
    effective_capabilities: dict[str, Any],
) -> dict[str, Any]:
    task_dir = paper_output / "v11" / "02_alpha25_tasks"
    tasks = sorted(
        path
        for path in task_dir.glob("*.json")
        if not path.name.endswith(".recovery.json")
    )
    missing_identity: list[str] = []
    wrong_identity: list[dict[str, Any]] = []
    hashes: list[dict[str, str]] = []
    for task_path in tasks:
        identity_path = task_path.with_name(task_path.name + ".identity")
        if not identity_path.is_file():
            missing_identity.append(task_path.name)
            continue
        payload = _read_object(identity_path)
        task_identity = payload.get("task_identity") or {}
        llm = task_identity.get("llm") or {}
        actual = {
            "model": llm.get("model"),
            "thinking_mode": llm.get("thinking_mode"),
            "response_mode": llm.get("response_mode"),
        }
        expected = {
            "model": model,
            "thinking_mode": effective_capabilities.get("thinking_mode"),
            "response_mode": effective_capabilities.get("response_format"),
        }
        if actual != expected:
            wrong_identity.append(
                {"task": task_path.name, "expected": expected, "actual": actual}
            )
        response_sha = _sha256(task_path)
        if response_sha != str(payload.get("response_sha256") or ""):
            wrong_identity.append(
                {
                    "task": task_path.name,
                    "expected_response_sha256": payload.get("response_sha256"),
                    "actual_response_sha256": response_sha,
                }
            )
        hashes.append({"path": task_path.name, "sha256": response_sha})
    if not tasks:
        raise RuntimeError(f"No Alpha25 task responses written under {task_dir}")
    if missing_identity or wrong_identity:
        raise RuntimeError(
            "Task identity audit failed: "
            + json.dumps(
                {
                    "missing_identity": missing_identity,
                    "wrong_identity": wrong_identity,
                },
                ensure_ascii=False,
            )
        )
    return {
        "task_response_count": len(tasks),
        "identity_sidecar_count": len(tasks) - len(missing_identity),
        "all_identities_valid": True,
        "responses": hashes,
    }


def run_paper(
    spec: PaperSpec,
    *,
    output_root: Path,
    model: str,
    effective_capabilities: dict[str, Any],
    candidate_replay_root: Path | None = None,
) -> dict[str, Any]:
    started_at = _utc_now()
    started = time.monotonic()
    paper_output = output_root / spec.output_name
    task_dir = paper_output / "v11" / "02_alpha25_tasks"
    replay_source = (
        candidate_replay_root / spec.output_name
        if candidate_replay_root is not None
        else None
    )
    replay_manifest = None
    if replay_source is not None:
        replay_manifest = stage_candidate_replay_cache(replay_source, task_dir)
    elif task_dir.is_dir() and any(task_dir.iterdir()):
        raise RuntimeError(
            f"Refusing to mix an existing task cache into a fresh arm: {task_dir}"
        )
    paper_output.mkdir(parents=True, exist_ok=True)
    source_path = _copy_frozen_source(spec, paper_output)
    routing_payload, routing = _load_frozen_routing(spec)
    routing_path = paper_output / "v11" / "01_routing.json"
    routing_path.parent.mkdir(parents=True, exist_ok=True)
    routing_path.write_text(
        json.dumps(routing_payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    routing_supplements = _build_routing_supplements(routing)
    baseline_id = str(routing_payload.get("identity", {}).get("ocr_baseline_id") or "")
    if not baseline_id:
        raise RuntimeError(f"Frozen routing has no OCR baseline identity: {spec.paper_id}")

    state = {
        "pdf_path": str(source_path),
        "paper_text": source_path.read_text(encoding="utf-8", errors="strict"),
        "paper_text_path": str(source_path),
        "output_dir": str(paper_output),
        "paper_routing": routing,
        "routing_supplements": routing_supplements,
        "document_metadata": {"title": spec.paper_key},
        "ocr_baseline_id": baseline_id,
        "extraction_model": model,
    }
    extracted = extract_data(state)
    normalized = normalize_v11({**state, **extracted})
    final_data = normalized.get("final_data") or {}
    extraction_path = paper_output / f"{spec.output_name}_extraction.json"
    extraction_path.write_text(
        json.dumps(final_data, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    if normalized.get("v11_promotable"):
        (paper_output / "final.json").write_text(
            json.dumps(final_data, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    coverage = extracted.get("alpha25_coverage") or {}
    (paper_output / "extraction_coverage.json").write_text(
        json.dumps(coverage, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    task_audit = _task_audit(
        paper_output,
        model=model,
        effective_capabilities=effective_capabilities,
    )
    replay_audit = None
    if replay_manifest is not None:
        output_replay_manifest = build_candidate_replay_manifest(task_dir)
        assert_cache_only_replay(coverage, replay_manifest, output_replay_manifest)
        replay_audit = {
            "mode": "cache_only",
            "source_paper_root": str(replay_source),
            "source_content_sha256": replay_manifest["content_sha256"],
            "output_content_sha256": output_replay_manifest["content_sha256"],
            "response_count": replay_manifest["response_count"],
            "all_tasks_cache_only": True,
            "extraction_provider_calls": 0,
        }
    wall_seconds = time.monotonic() - started
    row = {
        "paper_id": spec.paper_id,
        "paper_key": spec.paper_key,
        "output_name": spec.output_name,
        "source_path": str(spec.source_path),
        "source_sha256": spec.source_sha256,
        "model": model,
        "effective_capabilities": effective_capabilities,
        "ocr_baseline_id": baseline_id,
        "started_at": started_at,
        "finished_at": _utc_now(),
        "wall_seconds": wall_seconds,
        "coverage": coverage,
        "task_audit": task_audit,
        "candidate_replay": replay_audit,
        "promotable": bool(normalized.get("v11_promotable")),
        "fatal_count": int((normalized.get("v11_validation") or {}).get("fatal_count") or 0),
        "review_count": int((normalized.get("v11_validation") or {}).get("review_count") or 0),
        "item_count": len(final_data.get("items", []) or []),
    }
    (paper_output / "extraction_run.json").write_text(
        json.dumps(row, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return row


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--experiment-manifest", type=Path, required=True)
    parser.add_argument("--capability-probe", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--model", required=True)
    parser.add_argument(
        "--candidate-replay-root",
        type=Path,
        help=(
            "Replay exact Alpha25 task responses from this prior run root. "
            "Extraction becomes cache-only and any cache miss is fatal."
        ),
    )
    parser.add_argument(
        "--hierarchical-verification",
        action="store_true",
        help="Enable paper-level candidate verification and bounded recovery.",
    )
    parser.add_argument(
        "--verifier-model",
        help="Primary verifier model role; interpreted only as runtime configuration.",
    )
    parser.add_argument(
        "--verifier-fallback-model",
        help="Fallback verifier model role; defaults to the extraction model.",
    )
    parser.add_argument(
        "--verifier-thinking",
        choices=("enabled", "disabled", "provider_default"),
        default="provider_default",
    )
    parser.add_argument(
        "--verifier-fallback-thinking",
        choices=("enabled", "disabled", "provider_default"),
        default=None,
        help="Optional fallback-role thinking capability; defaults to the primary setting.",
    )
    parser.add_argument(
        "--verifier-response-format",
        choices=("json_object", "text"),
        default="json_object",
    )
    parser.add_argument("--verifier-timeout", type=int, default=180)
    parser.add_argument(
        "--verifier-confirmation-timeout",
        type=int,
        default=None,
        help=(
            "Optional timeout only for singleton destructive confirmation; "
            "defaults to --verifier-timeout."
        ),
    )
    parser.add_argument(
        "--verifier-confirmation-max-tokens",
        type=int,
        default=1536,
        help=(
            "Maximum output tokens for singleton destructive confirmation; "
            "independent of model identity and capped by --verifier-max-tokens."
        ),
    )
    parser.add_argument("--verifier-max-tokens", type=int, default=4096)
    parser.add_argument("--verifier-workers", type=int, default=None)
    parser.add_argument("--verifier-transient-retries", type=int, default=0)
    parser.add_argument("--verifier-bundle-assertions", type=int, default=6)
    parser.add_argument("--verifier-bundle-chars", type=int, default=6000)
    parser.add_argument(
        "--verifier-bypass-axes",
        default="composition,properties",
        help="Comma-separated deterministic axes excluded from LLM verification.",
    )
    parser.add_argument(
        "--no-verifier-recovery",
        action="store_true",
        help="Disable only bounded omission recovery while retaining verification.",
    )
    parser.add_argument(
        "--no-verifier-destructive-consensus",
        action="store_true",
        help=(
            "Disable independent fallback-role confirmation of primary "
            "quarantine decisions."
        ),
    )
    parser.add_argument("--pilot", action="store_true")
    parser.add_argument("--only", nargs="*", default=[])
    parser.add_argument("--workers", type=int, default=1)
    parser.add_argument(
        "--provider-concurrency",
        type=int,
        default=None,
        help="Override only provider scheduling concurrency for a latency probe.",
    )
    parser.add_argument(
        "--request-timeout",
        type=int,
        default=None,
        help="Override only the extraction HTTP timeout in seconds.",
    )
    args = parser.parse_args()

    manifest_path = args.experiment_manifest.resolve()
    probe_path = args.capability_probe.resolve()
    manifest, specs = load_paper_specs(
        manifest_path,
        pilot=bool(args.pilot),
        requested_ids=set(args.only),
    )
    probe = _read_object(probe_path)
    applied_environment = _configure_effective_capabilities(manifest, probe, args.model)
    candidate_replay_root = (
        args.candidate_replay_root.expanduser().resolve()
        if args.candidate_replay_root is not None
        else None
    )
    if candidate_replay_root is not None:
        if not candidate_replay_root.is_dir():
            parser.error(f"Candidate replay root does not exist: {candidate_replay_root}")
        os.environ["KNOWMAT2_ALPHA25_CACHE_ONLY"] = "1"
        applied_environment["KNOWMAT2_ALPHA25_CACHE_ONLY"] = "1"
    if args.provider_concurrency is not None:
        concurrency = str(max(1, int(args.provider_concurrency)))
        os.environ["KNOWMAT2_ALPHA25_GLOBAL_CONCURRENCY"] = concurrency
        applied_environment["KNOWMAT2_ALPHA25_GLOBAL_CONCURRENCY"] = concurrency
    if args.request_timeout is not None:
        timeout = str(max(1, int(args.request_timeout)))
        os.environ["KNOWMAT2_EXTRACTION_TIMEOUT"] = timeout
        applied_environment["KNOWMAT2_EXTRACTION_TIMEOUT"] = timeout
    if args.hierarchical_verification:
        if not str(args.verifier_model or "").strip():
            parser.error("--verifier-model is required with --hierarchical-verification")
        verification_environment = {
            "KNOWMAT2_ALPHA25_HIERARCHICAL_VERIFICATION": "1",
            "KNOWMAT2_ALPHA25_VERIFIER_MODEL": str(args.verifier_model).strip(),
            "KNOWMAT2_ALPHA25_VERIFIER_FALLBACK_MODEL": str(
                args.verifier_fallback_model or args.model
            ).strip(),
            "KNOWMAT2_ALPHA25_VERIFIER_THINKING": args.verifier_thinking,
            "KNOWMAT2_ALPHA25_VERIFIER_RESPONSE_FORMAT": (
                args.verifier_response_format
            ),
            "KNOWMAT2_ALPHA25_VERIFIER_TIMEOUT": str(
                max(1, int(args.verifier_timeout))
            ),
            "KNOWMAT2_ALPHA25_VERIFIER_MAX_TOKENS": str(
                max(512, int(args.verifier_max_tokens))
            ),
            "KNOWMAT2_ALPHA25_VERIFIER_CONFIRMATION_MAX_TOKENS": str(
                max(512, int(args.verifier_confirmation_max_tokens))
            ),
            "KNOWMAT2_ALPHA25_VERIFIER_RECOVERY": (
                "0" if args.no_verifier_recovery else "1"
            ),
            "KNOWMAT2_ALPHA25_VERIFIER_DESTRUCTIVE_CONSENSUS": (
                "0" if args.no_verifier_destructive_consensus else "1"
            ),
            "KNOWMAT2_ALPHA25_VERIFIER_TRANSIENT_RETRIES": str(
                max(0, int(args.verifier_transient_retries))
            ),
            "KNOWMAT2_ALPHA25_VERIFIER_BUNDLE_ASSERTIONS": str(
                max(1, min(12, int(args.verifier_bundle_assertions)))
            ),
            "KNOWMAT2_ALPHA25_VERIFIER_BUNDLE_CHARS": str(
                max(1, min(12000, int(args.verifier_bundle_chars)))
            ),
            "KNOWMAT2_ALPHA25_VERIFIER_BYPASS_AXES": str(
                args.verifier_bypass_axes
            ).strip(),
        }
        if args.verifier_fallback_thinking is not None:
            verification_environment[
                "KNOWMAT2_ALPHA25_VERIFIER_FALLBACK_THINKING"
            ] = args.verifier_fallback_thinking
        if args.verifier_confirmation_timeout is not None:
            verification_environment[
                "KNOWMAT2_ALPHA25_VERIFIER_CONFIRMATION_TIMEOUT"
            ] = str(max(1, int(args.verifier_confirmation_timeout)))
        if args.verifier_workers is not None:
            verification_environment["KNOWMAT2_ALPHA25_VERIFIER_WORKERS"] = str(
                max(1, int(args.verifier_workers))
            )
        for key, value in verification_environment.items():
            os.environ[key] = value
            applied_environment[key] = value
    else:
        # The experiment manifest may have been captured from a verified arm.
        # The explicit CLI switch is authoritative for this runner.
        os.environ["KNOWMAT2_ALPHA25_HIERARCHICAL_VERIFICATION"] = "0"
        applied_environment["KNOWMAT2_ALPHA25_HIERARCHICAL_VERIFICATION"] = "0"
    effective_capabilities = dict(probe.get("effective") or {})

    output_root = args.output_root.resolve()
    output_root.mkdir(parents=True, exist_ok=True)
    if any(output_root.iterdir()):
        parser.error(
            f"Output root is not empty; use a new arm directory: {output_root}"
        )
    run_started_at = _utc_now()
    run_started = time.monotonic()
    print(
        f"Frozen Alpha25 extraction: papers={len(specs)} model={args.model} "
        f"workers={max(1, args.workers)} "
        f"hierarchical_verification={bool(args.hierarchical_verification)} "
        f"candidate_replay={candidate_replay_root is not None}"
    )
    print(
        "Effective capabilities: "
        + json.dumps(effective_capabilities, ensure_ascii=False, sort_keys=True)
    )

    rows: list[dict[str, Any]] = []
    failures: list[dict[str, str]] = []
    with ThreadPoolExecutor(max_workers=max(1, args.workers)) as pool:
        futures = {
            pool.submit(
                run_paper,
                spec,
                output_root=output_root,
                model=args.model,
                effective_capabilities=effective_capabilities,
                candidate_replay_root=candidate_replay_root,
            ): spec
            for spec in specs
        }
        for future in as_completed(futures):
            spec = futures[future]
            try:
                row = future.result()
            except Exception as exc:
                failures.append({"paper_id": spec.paper_id, "error": str(exc)})
                print(f"ERROR {spec.paper_id}: {exc}", flush=True)
                continue
            rows.append(row)
            print(
                f"DONE {spec.paper_id}: tasks={row['task_audit']['task_response_count']} "
                f"items={row['item_count']} wall={row['wall_seconds']:.1f}s "
                f"fatal/review={row['fatal_count']}/{row['review_count']}",
                flush=True,
            )

    rows.sort(key=lambda row: row["paper_id"])
    failures.sort(key=lambda row: row["paper_id"])
    result = {
        "schema_version": "knowmat_frozen_alpha25_extraction_run_v2",
        "experiment_manifest": str(manifest_path),
        "capability_probe": str(probe_path),
        "model": args.model,
        "hierarchical_verification": bool(args.hierarchical_verification),
        "candidate_replay_root": (
            str(candidate_replay_root) if candidate_replay_root is not None else None
        ),
        "verifier_roles": (
            {
                "primary": str(args.verifier_model).strip(),
                "fallback": str(args.verifier_fallback_model or args.model).strip(),
            }
            if args.hierarchical_verification
            else None
        ),
        "effective_capabilities": effective_capabilities,
        "applied_safe_environment": dict(sorted(applied_environment.items())),
        "pilot": bool(args.pilot),
        "paper_count": len(specs),
        "started_at": run_started_at,
        "finished_at": _utc_now(),
        "wall_seconds": time.monotonic() - run_started,
        "papers": rows,
        "failures": failures,
    }
    (output_root / "extraction_run_manifest.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(
        f"SUMMARY success={len(rows)}/{len(specs)} failures={len(failures)} "
        f"wall={result['wall_seconds']:.1f}s"
    )
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
