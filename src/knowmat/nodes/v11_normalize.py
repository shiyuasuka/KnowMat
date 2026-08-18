"""Thin LangGraph adapter for alpha25 normalization and validation."""

from __future__ import annotations

import json
import logging
import subprocess
import sys
from copy import deepcopy
from pathlib import Path
from typing import Any, Dict

from knowmat.alpha25.package import load_alpha25_package
from knowmat.app_config import settings
from knowmat.states import KnowMatState


logger = logging.getLogger(__name__)

_ITEM_KEYS = {
    "Item_ID",
    "Sample_ID",
    "Role",
    "Data_Nature",
    "base_material",
    "application",
    "research_paradigm",
    "Extracted_Data",
}


def _prepare_candidate(candidate: Dict[str, Any], source_path: str) -> Dict[str, Any]:
    """Perform only evidence-neutral envelope cleanup before alpha25."""

    prepared = deepcopy(candidate)
    metadata = prepared.get("Paper_Metadata") or {}
    prepared["Paper_Metadata"] = {
        "title": metadata.get("title") or metadata.get("Paper_Title"),
        "doi": metadata.get("doi") if "doi" in metadata else metadata.get("DOI"),
        **({"authors": metadata["authors"]} if metadata.get("authors") else {}),
        "source_text": Path(source_path).name if source_path else metadata.get("source_text"),
    }
    prepared["Paper_Metadata"] = {
        key: value
        for key, value in prepared["Paper_Metadata"].items()
        if value is not None
    }
    if not prepared["Paper_Metadata"]:
        prepared["Paper_Metadata"] = {"title": "not_reported"}

    routing = prepared.get("Paper_Routing") or {}
    prepared["Paper_Routing"] = {
        key: routing.get(key)
        for key in ("base_material", "application", "research_paradigm")
    }
    prepared["items"] = [
        {key: deepcopy(value) for key, value in item.items() if key in _ITEM_KEYS}
        for item in prepared.get("items", [])
        if isinstance(item, dict)
    ]
    if not prepared["items"]:
        raise ValueError("alpha25 candidate contains no material items")
    return prepared


def _read_json_object(path: Path, label: str) -> Dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"Could not read alpha25 {label}: {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise RuntimeError(f"Alpha25 {label} is not a JSON object: {path}")
    return value


def _merge_materialization_issues(
    validation: Dict[str, Any], materialization_issues: Any
) -> Dict[str, Any]:
    """Merge deterministic quality-gate audit into the canonical issue report."""

    existing = [
        deepcopy(row)
        for row in validation.get("issues", []) or []
        if isinstance(row, dict)
    ]
    incoming: list[Dict[str, Any]] = []
    if isinstance(materialization_issues, list):
        for raw in materialization_issues:
            if not isinstance(raw, dict):
                continue
            row = deepcopy(raw)
            row.setdefault("severity", "review")
            row.setdefault("path", "materialization")
            row.setdefault("message", "A deterministic materialization action requires review.")
            for key in ("evidence", "expected", "actual", "suggested_action"):
                row.setdefault(key, None)
            incoming.append(row)

    merged: list[Dict[str, Any]] = []
    signatures: set[str] = set()
    for row in [*existing, *incoming]:
        signature = json.dumps(row, ensure_ascii=False, sort_keys=True, default=str)
        if signature in signatures:
            continue
        signatures.add(signature)
        merged.append(row)

    fatal_count = sum(row.get("severity") == "fatal" for row in merged)
    review_count = sum(row.get("severity") == "review" for row in merged)
    result = deepcopy(validation)
    result.update(
        {
            "state": (
                "failed"
                if fatal_count
                else "passed_with_review"
                if review_count
                else "passed"
            ),
            "review_required": review_count > 0,
            "fatal_count": fatal_count,
            "review_count": review_count,
            "issues": merged,
        }
    )
    return result


def _issues_markdown(report: Dict[str, Any]) -> str:
    lines = [
        "# v11 run issues",
        "",
        f"- State: `{report['state']}`",
        f"- Fatal issues: {report['fatal_count']}",
        f"- Review issues: {report['review_count']}",
        "",
    ]
    issues = report.get("issues", []) or []
    if not issues:
        return "\n".join([*lines, "No issues.", ""])
    for index, issue in enumerate(issues, start=1):
        lines.extend(
            [
                f"## {index}. {issue.get('code', 'unknown_issue')}",
                "",
                f"- Severity: `{issue.get('severity', 'review')}`",
                f"- Path: `{issue.get('path', 'materialization')}`",
                f"- Message: {issue.get('message', '')}",
                f"- Evidence: `{json.dumps(issue.get('evidence'), ensure_ascii=False)}`",
                f"- Expected: `{json.dumps(issue.get('expected'), ensure_ascii=False)}`",
                f"- Actual: `{json.dumps(issue.get('actual'), ensure_ascii=False)}`",
                "- Suggested action: `"
                + json.dumps(issue.get("suggested_action"), ensure_ascii=False)
                + "`",
                "",
            ]
        )
    return "\n".join(lines)


def normalize_v11(state: KnowMatState) -> Dict[str, Any]:
    """Persist a grounded candidate and invoke alpha25's deterministic runner."""

    candidate = state.get("final_data") or state.get("aggregated_data") or state.get(
        "latest_extracted_data", {}
    )
    if not isinstance(candidate, dict) or not isinstance(candidate.get("items"), list):
        return {}

    source_path = str(state.get("paper_text_path") or "")
    source_file = Path(source_path) if source_path else None
    if source_file is None or not source_file.is_file():
        raise RuntimeError(
            "Alpha25 normalization requires the current OCR Markdown source path"
        )
    if source_file.suffix.casefold() not in {".md", ".txt"}:
        raise RuntimeError(
            f"Alpha25 source text must be Markdown or text, got: {source_file}"
        )

    coverage = state.get("alpha25_coverage") or {}
    coverage_complete = bool(coverage.get("complete"))
    if coverage and not coverage_complete:
        raise RuntimeError("Refusing alpha25 normalization with incomplete task coverage")

    prepared = _prepare_candidate(candidate, str(source_file))
    output_root = Path(state.get("output_dir") or ".").resolve()
    paper_id = output_root.name or "paper"
    v11_root = output_root / "v11"
    candidate_dir = v11_root / "03_extract"
    validate_dir = v11_root / "04_validate"
    candidate_dir.mkdir(parents=True, exist_ok=True)
    candidate_path = candidate_dir / f"{paper_id}_candidate.json"
    candidate_path.write_text(
        json.dumps(prepared, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    package = load_alpha25_package(settings.alpha25_package_root)
    command = [
        sys.executable,
        str(Path(__file__).resolve().parent.parent / "alpha25" / "runner_compat.py"),
        "--package-root",
        str(package.root),
        str(candidate_path),
        "--paper-id",
        paper_id,
        "--repo-root",
        str(package.root),
        "--output-dir",
        str(validate_dir),
        "--source-text",
        str(source_file.resolve()),
    ]
    completed = subprocess.run(
        command,
        cwd=package.root,
        check=False,
        capture_output=True,
        text=True,
    )
    if completed.stderr.strip():
        logger.warning("alpha25 normalization stderr: %s", completed.stderr.strip())

    normalized_path = validate_dir / f"{paper_id}_normalized.json"
    issues_path = validate_dir / f"{paper_id}_issues.json"
    metadata_path = validate_dir / f"{paper_id}_run_metadata.json"
    if not normalized_path.is_file() or not issues_path.is_file():
        raise RuntimeError(
            "alpha25 normalization produced no readable result: "
            f"exit={completed.returncode}, stdout={completed.stdout.strip()}, "
            f"stderr={completed.stderr.strip()}"
        )

    normalized = _read_json_object(normalized_path, "normalized document")
    validation = _read_json_object(issues_path, "validation report")
    validation = _merge_materialization_issues(
        validation, coverage.get("materialization_issues")
    )
    issues_path.write_text(
        json.dumps(validation, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    issues_md_path = validate_dir / f"{paper_id}_issues.md"
    issues_md_path.write_text(
        _issues_markdown(validation), encoding="utf-8", newline="\n"
    )
    metadata = (
        _read_json_object(metadata_path, "run metadata")
        if metadata_path.is_file()
        else {}
    )
    metadata["coverage_complete"] = coverage_complete if coverage else None
    metadata["coverage_task_count"] = coverage.get("task_count")
    metadata["coverage_rejected_facts"] = coverage.get("rejected_facts")
    metadata["ocr_baseline_id"] = state.get("ocr_baseline_id")
    metadata = {key: value for key, value in metadata.items() if value is not None}

    status = str(validation.get("state") or "failed")
    promotable = (
        status in {"passed", "passed_with_review"}
        and int(validation.get("fatal_count") or 0) == 0
        and (not coverage or coverage_complete)
    )
    metadata.update(
        {
            "state": status,
            "promotable": promotable,
            "fatal_count": int(validation.get("fatal_count") or 0),
            "review_count": int(validation.get("review_count") or 0),
        }
    )
    metadata_path.write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    logger.warning(
        "[V11-NORMALIZE alpha25] state=%s fatal=%s review=%s coverage=%s",
        status,
        validation.get("fatal_count"),
        validation.get("review_count"),
        coverage_complete if coverage else "legacy-untracked",
    )
    return {
        "final_data": normalized,
        "v11_validation": validation,
        "v11_run_metadata": metadata,
        "v11_promotable": promotable,
    }


__all__ = ["normalize_v11"]
