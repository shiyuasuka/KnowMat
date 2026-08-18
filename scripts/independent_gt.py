#!/usr/bin/env python3
"""Prepare, validate, and seal the independent GPT-5.6-sol expert GT corpus."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import sys
import unicodedata
from typing import Any, Iterable

try:
    from jsonschema import Draft202012Validator
except ImportError:  # pragma: no cover
    Draft202012Validator = None  # type: ignore[assignment,misc]


EXPECTED_BASELINE_ID = "d3b79e0090ec2e436ceb328c6a08c728eb5c2343d061e4724bb14bcce441c347"
DEFAULT_BASELINE = Path("data/raw/.knowmat_ocr_baselines/alpha25-fresh-20260810.json")
DEFAULT_SOURCE_ROOT = Path("data/output-alpha25-prompt-v5-final30-20260818")
DEFAULT_OUTPUT_ROOT = Path("data/gt/gpt56sol-independent-expert-20260818")
V11_SCHEMA = Path(
    "material-extractor-alpha25-20260804/material-extractor/references/schema/"
    "material_extraction_v11.schema.json"
)
CONTRACT_ROOT = Path("schemas/independent_gt")
GUIDANCE_FILES = (
    "material-extractor-alpha25-20260804/material-extractor/SKILL.md",
    "material-extractor-alpha25-20260804/material-extractor/references/03-extract-system-prompt.md",
    "material-extractor-alpha25-20260804/material-extractor/references/03-extract-user-prompt.md",
    "material-extractor-alpha25-20260804/material-extractor/references/05-review.md",
    "material-extractor-alpha25-20260804/material-extractor/references/06-revise.md",
    "material-extractor-alpha25-20260804/material-extractor/references/07-evaluate.md",
    str(V11_SCHEMA),
)
ARTIFACT_SCHEMAS = {
    "expert_claims.jsonl": "claim.schema.json",
    "curve_audit.json": "curve_audit.schema.json",
    "issues.json": "issues.schema.json",
    "annotation_audit.jsonl": "annotation_audit.schema.json",
}
REQUIRED_PAPER_ARTIFACTS = (
    "expert_claims.jsonl",
    "expert_gt.json",
    "curve_audit.json",
    "issues.json",
    "annotation_audit.jsonl",
)


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _canonical_digest(value: Any) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _relative(path: Path, repo_root: Path) -> str:
    return str(path.resolve().relative_to(repo_root.resolve()))


def _file_record(path: Path, repo_root: Path) -> dict[str, Any]:
    return {
        "path": _relative(path, repo_root),
        "sha256": _sha256(path),
        "size": path.stat().st_size,
    }


def _title_key(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value).casefold()
    return "".join(char for char in normalized if char.isalnum())


def _enhanced_title(path: Path) -> str:
    suffix = "_final_output"
    stem = path.stem
    return stem[: -len(suffix)] if stem.endswith(suffix) else stem


def _load_schema(repo_root: Path, filename: str) -> dict[str, Any]:
    value = _read_json(repo_root / CONTRACT_ROOT / filename)
    if not isinstance(value, dict):
        raise ValueError(f"schema is not an object: {filename}")
    return value


def _schema_errors(instance: Any, schema: dict[str, Any]) -> list[str]:
    if Draft202012Validator is not None:
        validator = Draft202012Validator(schema)
        errors: list[str] = []
        for error in sorted(
            validator.iter_errors(instance), key=lambda row: list(row.absolute_path)
        ):
            location = "$"
            if error.absolute_path:
                location += "".join(
                    f"[{part}]" if isinstance(part, int) else f".{part}"
                    for part in error.absolute_path
                )
            errors.append(f"{location}: {error.message}")
        return errors
    return _fallback_schema_errors(instance, schema, schema, "$")


def _json_type_matches(value: Any, expected: str) -> bool:
    return {
        "null": value is None,
        "object": isinstance(value, dict),
        "array": isinstance(value, list),
        "string": isinstance(value, str),
        "number": isinstance(value, (int, float)) and not isinstance(value, bool),
        "integer": isinstance(value, int) and not isinstance(value, bool),
        "boolean": isinstance(value, bool),
    }.get(expected, True)


def _resolve_local_ref(root_schema: dict[str, Any], reference: str) -> dict[str, Any]:
    if not reference.startswith("#/"):
        raise ValueError(f"only local JSON Schema references are supported: {reference}")
    value: Any = root_schema
    for raw_part in reference[2:].split("/"):
        part = raw_part.replace("~1", "/").replace("~0", "~")
        value = value[part]
    if not isinstance(value, dict):
        raise ValueError(f"JSON Schema reference is not an object: {reference}")
    return value


def _fallback_schema_errors(
    instance: Any,
    schema: dict[str, Any],
    root_schema: dict[str, Any],
    path: str,
) -> list[str]:
    """Dependency-free validator for the subset used by the local contracts."""

    if "$ref" in schema:
        return _fallback_schema_errors(
            instance, _resolve_local_ref(root_schema, schema["$ref"]), root_schema, path
        )
    errors: list[str] = []
    for child in schema.get("allOf", []):
        errors.extend(_fallback_schema_errors(instance, child, root_schema, path))
    if "anyOf" in schema:
        alternatives = [
            _fallback_schema_errors(instance, child, root_schema, path)
            for child in schema["anyOf"]
        ]
        if all(alternative for alternative in alternatives):
            errors.append(f"{path}: value does not match any allowed schema")
            return errors
    if "oneOf" in schema:
        matches = sum(
            not _fallback_schema_errors(instance, child, root_schema, path)
            for child in schema["oneOf"]
        )
        if matches != 1:
            errors.append(f"{path}: value must match exactly one allowed schema")
            return errors
    if "not" in schema and not _fallback_schema_errors(
        instance, schema["not"], root_schema, path
    ):
        errors.append(f"{path}: value matches a forbidden schema")
        return errors
    if "if" in schema and not _fallback_schema_errors(
        instance, schema["if"], root_schema, path
    ):
        branch = schema.get("then")
        if isinstance(branch, dict):
            errors.extend(_fallback_schema_errors(instance, branch, root_schema, path))
    if "const" in schema and instance != schema["const"]:
        errors.append(f"{path}: expected constant {schema['const']!r}")
        return errors
    if "enum" in schema and instance not in schema["enum"]:
        errors.append(f"{path}: {instance!r} is not in the allowed enum")
        return errors
    expected_type = schema.get("type")
    if expected_type is not None:
        expected_types = [expected_type] if isinstance(expected_type, str) else expected_type
        if not any(_json_type_matches(instance, row) for row in expected_types):
            errors.append(f"{path}: expected type {expected_types}, got {type(instance).__name__}")
            return errors
    if isinstance(instance, dict):
        required = schema.get("required", [])
        for key in required:
            if key not in instance:
                errors.append(f"{path}: missing required property {key!r}")
        properties = schema.get("properties", {})
        for key, value in instance.items():
            child_path = f"{path}.{key}"
            if key in properties:
                errors.extend(
                    _fallback_schema_errors(value, properties[key], root_schema, child_path)
                )
            elif schema.get("additionalProperties") is False:
                errors.append(f"{child_path}: additional property is not allowed")
            elif isinstance(schema.get("additionalProperties"), dict):
                errors.extend(
                    _fallback_schema_errors(
                        value, schema["additionalProperties"], root_schema, child_path
                    )
                )
    if isinstance(instance, list):
        if len(instance) < schema.get("minItems", 0):
            errors.append(f"{path}: array has fewer than {schema['minItems']} items")
        if "maxItems" in schema and len(instance) > schema["maxItems"]:
            errors.append(f"{path}: array has more than {schema['maxItems']} items")
        if schema.get("uniqueItems"):
            encoded = [
                json.dumps(row, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
                for row in instance
            ]
            if len(encoded) != len(set(encoded)):
                errors.append(f"{path}: array items are not unique")
        item_schema = schema.get("items")
        if isinstance(item_schema, dict):
            for index, value in enumerate(instance):
                errors.extend(
                    _fallback_schema_errors(
                        value, item_schema, root_schema, f"{path}[{index}]"
                    )
                )
    if isinstance(instance, str):
        if len(instance) < schema.get("minLength", 0):
            errors.append(f"{path}: string is shorter than {schema['minLength']}")
        if "maxLength" in schema and len(instance) > schema["maxLength"]:
            errors.append(f"{path}: string is longer than {schema['maxLength']}")
        if "pattern" in schema and re.search(schema["pattern"], instance) is None:
            errors.append(f"{path}: string does not match {schema['pattern']!r}")
    if isinstance(instance, (int, float)) and not isinstance(instance, bool):
        if "minimum" in schema and instance < schema["minimum"]:
            errors.append(f"{path}: number is below minimum {schema['minimum']}")
        if "maximum" in schema and instance > schema["maximum"]:
            errors.append(f"{path}: number is above maximum {schema['maximum']}")
    return errors


def _jsonl(path: Path) -> tuple[list[dict[str, Any]], list[str]]:
    rows: list[dict[str, Any]] = []
    errors: list[str] = []
    for line_number, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not raw.strip():
            continue
        try:
            value = json.loads(raw)
        except json.JSONDecodeError as exc:
            errors.append(f"line {line_number}: invalid JSON: {exc}")
            continue
        if not isinstance(value, dict):
            errors.append(f"line {line_number}: record must be an object")
            continue
        value["__line_number__"] = line_number
        rows.append(value)
    return rows, errors


def _strip_line_number(value: dict[str, Any]) -> dict[str, Any]:
    return {key: row for key, row in value.items() if key != "__line_number__"}


def _normalized_text(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def _quote_supported(quote: str, source_text: str) -> bool:
    if len(re.sub(r"\W+", "", quote, flags=re.UNICODE)) < 4:
        return False
    return quote in source_text or _normalized_text(quote) in _normalized_text(source_text)


def _paper_sources(paper: dict[str, Any], repo_root: Path) -> dict[str, dict[str, Any]]:
    source_records = [paper["enhanced_markdown"], *paper.get("chart_csvs", [])]
    return {record["path"]: record for record in source_records}


def prepare(args: argparse.Namespace) -> int:
    repo_root = args.repo_root.resolve()
    baseline_path = (repo_root / args.baseline).resolve()
    source_root = (repo_root / args.source_root).resolve()
    output_root = (repo_root / args.output_root).resolve()

    baseline = _read_json(baseline_path)
    if baseline.get("baseline_id") != EXPECTED_BASELINE_ID:
        raise ValueError(
            f"unexpected baseline_id: {baseline.get('baseline_id')!r}; "
            f"expected {EXPECTED_BASELINE_ID}"
        )
    if baseline.get("record_count") != 30 or len(baseline.get("records", [])) != 30:
        raise ValueError("frozen baseline must contain exactly 30 records")
    if baseline.get("status") != "frozen":
        raise ValueError("OCR baseline is not frozen")

    enhanced_paths = sorted(source_root.glob("*/txt_parse/*_final_output.md"))
    if len(enhanced_paths) != 30:
        raise ValueError(f"expected 30 enhanced Markdown files, found {len(enhanced_paths)}")
    enhanced_index: dict[str, Path] = {}
    for path in enhanced_paths:
        key = _title_key(_enhanced_title(path))
        if key in enhanced_index:
            raise ValueError(f"duplicate normalized enhanced Markdown title: {path}")
        enhanced_index[key] = path

    guidance = []
    for relative_path in GUIDANCE_FILES:
        path = repo_root / relative_path
        if not path.is_file():
            raise FileNotFoundError(path)
        guidance.append(_file_record(path, repo_root))
    contracts = []
    for schema_filename in ARTIFACT_SCHEMAS.values():
        path = repo_root / CONTRACT_ROOT / schema_filename
        if not path.is_file():
            raise FileNotFoundError(path)
        contracts.append(_file_record(path, repo_root))

    sorted_records = sorted(baseline["records"], key=lambda row: _title_key(row["paper_key"]))
    papers: list[dict[str, Any]] = []
    used_enhanced: set[Path] = set()
    batch_names = ("batch_a", "batch_b", "batch_c")
    for index, record in enumerate(sorted_records, start=1):
        paper_key = record["paper_key"]
        enhanced = enhanced_index.get(_title_key(paper_key))
        if enhanced is None:
            raise ValueError(f"no enhanced Markdown mapped to paper: {paper_key}")
        used_enhanced.add(enhanced)
        charts = sorted(enhanced.parent.glob("figure_*_digitized.csv"))
        paper_id = f"paper_{index:03d}"
        batch_id = batch_names[(index - 1) // 10]
        pdf_path = repo_root / "data/raw" / record["pdf_path"]
        baseline_markdown_path = repo_root / "data/raw" / record["ocr_markdown_path"]
        baseline_json_path = repo_root / "data/raw" / record["ocr_json_path"]
        for path in (pdf_path, baseline_markdown_path, baseline_json_path):
            if not path.is_file():
                raise FileNotFoundError(path)
        if _sha256(pdf_path) != record["pdf_sha256"]:
            raise ValueError(f"PDF digest drift: {paper_key}")
        if _sha256(baseline_markdown_path) != record["ocr_markdown_sha256"]:
            raise ValueError(f"baseline Markdown digest drift: {paper_key}")
        if _sha256(baseline_json_path) != record["ocr_json_sha256"]:
            raise ValueError(f"baseline OCR JSON digest drift: {paper_key}")
        output_dir = output_root / "papers" / paper_id
        output_dir.mkdir(parents=True, exist_ok=True)
        papers.append(
            {
                "paper_id": paper_id,
                "paper_key": paper_key,
                "batch_id": batch_id,
                "output_dir": _relative(output_dir, repo_root),
                "pdf_metadata": _file_record(pdf_path, repo_root),
                "baseline_markdown": _file_record(baseline_markdown_path, repo_root),
                "baseline_ocr_json": _file_record(baseline_json_path, repo_root),
                "enhanced_markdown": _file_record(enhanced, repo_root),
                "chart_csvs": [_file_record(path, repo_root) for path in charts],
            }
        )
    if used_enhanced != set(enhanced_paths):
        extra = sorted(str(path) for path in set(enhanced_paths) - used_enhanced)
        raise ValueError(f"unmapped enhanced Markdown files: {extra}")

    chart_count = sum(len(paper["chart_csvs"]) for paper in papers)
    if chart_count != 95:
        raise ValueError(f"expected 95 chart CSV files, found {chart_count}")

    manifest: dict[str, Any] = {
        "schema_version": "knowmat_independent_gt_blind_input_v1",
        "created_at": _utc_now(),
        "model": args.model,
        "isolation": {
            "fork_turns": "none",
            "comparison_inputs_locked": True,
            "allowed_source_types": ["enhanced_markdown", "chart_csv", "paper_metadata"],
            "external_web_facts_allowed": False,
        },
        "ocr_baseline": {
            "path": _relative(baseline_path, repo_root),
            "sha256": _sha256(baseline_path),
            "baseline_id": baseline["baseline_id"],
            "status": baseline["status"],
            "record_count": baseline["record_count"],
        },
        "guidance_files": guidance,
        "contract_files": contracts,
        "paper_count": len(papers),
        "chart_csv_count": chart_count,
        "papers": papers,
    }
    manifest["content_digest"] = _canonical_digest(manifest)
    manifest_path = output_root / "blind_input_manifest.json"
    _write_json(manifest_path, manifest)

    batch_root = output_root / "batches"
    for batch_id in batch_names:
        batch_papers = [paper for paper in papers if paper["batch_id"] == batch_id]
        batch = {
            "schema_version": "knowmat_independent_gt_batch_v1",
            "model": args.model,
            "batch_id": batch_id,
            "paper_count": len(batch_papers),
            "blind_input_manifest": _relative(manifest_path, repo_root),
            "blind_input_manifest_sha256": _sha256(manifest_path),
            "guidance_files": guidance,
            "contract_files": contracts,
            "papers": batch_papers,
        }
        batch["content_digest"] = _canonical_digest(batch)
        _write_json(batch_root / f"{batch_id}.json", batch)

    print(
        json.dumps(
            {
                "status": "prepared",
                "manifest": _relative(manifest_path, repo_root),
                "papers": len(papers),
                "chart_csvs": chart_count,
                "batches": {name: 10 for name in batch_names},
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


def _validate_paper(
    paper: dict[str, Any],
    repo_root: Path,
    claims_only: bool,
    contract_schemas: dict[str, dict[str, Any]],
    v11_schema: dict[str, Any],
) -> dict[str, Any]:
    output_dir = repo_root / paper["output_dir"]
    findings: list[dict[str, str]] = []

    def finding(code: str, path: Path, message: str) -> None:
        findings.append({"code": code, "path": _relative(path, repo_root), "message": message})

    required = [name for name in REQUIRED_PAPER_ARTIFACTS if not claims_only or name != "expert_gt.json"]
    for name in required:
        path = output_dir / name
        if not path.is_file():
            finding("missing_artifact", path, "required paper artifact is missing")
    if findings:
        return {"paper_id": paper["paper_id"], "paper_key": paper["paper_key"], "findings": findings}

    sources = _paper_sources(paper, repo_root)
    source_text_cache: dict[str, str] = {}
    for source_path, record in sources.items():
        path = repo_root / source_path
        actual_digest = _sha256(path)
        if actual_digest != record["sha256"]:
            finding("input_digest_drift", path, f"expected {record['sha256']}, got {actual_digest}")
        source_text_cache[source_path] = path.read_text(encoding="utf-8", errors="replace")

    claims_path = output_dir / "expert_claims.jsonl"
    claims, jsonl_errors = _jsonl(claims_path)
    for message in jsonl_errors:
        finding("invalid_jsonl", claims_path, message)
    claim_ids: set[str] = set()
    signatures: dict[str, str] = {}
    claim_schema = contract_schemas["expert_claims.jsonl"]
    for claim in claims:
        line_number = claim["__line_number__"]
        clean_claim = _strip_line_number(claim)
        for message in _schema_errors(clean_claim, claim_schema):
            finding("claim_schema", claims_path, f"line {line_number}: {message}")
        claim_id = clean_claim.get("claim_id")
        if isinstance(claim_id, str):
            if claim_id in claim_ids:
                finding("duplicate_claim_id", claims_path, f"line {line_number}: {claim_id}")
            claim_ids.add(claim_id)
        if clean_claim.get("paper_key") != paper["paper_key"]:
            finding("paper_key_mismatch", claims_path, f"line {line_number}")
        owner = clean_claim.get("owner")
        if isinstance(owner, dict):
            owner_name = owner.get("material_name")
            if isinstance(owner_name, str):
                owner_key = _title_key(owner_name)
                paper_title_key = _title_key(paper["paper_key"])
                if owner_key and (
                    owner_key == paper_title_key
                    or (
                        len(owner_key) >= int(len(paper_title_key) * 0.65)
                        and owner_key in paper_title_key
                    )
                ):
                    finding(
                        "paper_title_used_as_material_owner",
                        claims_path,
                        f"line {line_number}: {owner_name!r}",
                    )
        semantic_key = clean_claim.get("semantic_key")
        if isinstance(semantic_key, str) and (
            re.match(
                r"^(composition|processing|structure|characterization|properties)\.",
                semantic_key,
            )
            or re.search(r"_report_[0-9]+$", semantic_key)
            or semantic_key in {"composition", "processing_fact"}
        ):
            finding(
                "non_atomic_semantic_key",
                claims_path,
                f"line {line_number}: {semantic_key!r}",
            )
        for evidence in clean_claim.get("evidence", []):
            if not isinstance(evidence, dict):
                continue
            source_path = evidence.get("path")
            if source_path not in sources:
                finding("forbidden_evidence_path", claims_path, f"line {line_number}: {source_path!r}")
                continue
            expected_digest = sources[source_path]["sha256"]
            if evidence.get("sha256") != expected_digest:
                finding("evidence_digest_mismatch", claims_path, f"line {line_number}: {source_path}")
            quote = evidence.get("quote")
            if not isinstance(quote, str) or not _quote_supported(
                quote, source_text_cache[source_path]
            ):
                finding("unsupported_evidence_quote", claims_path, f"line {line_number}: {source_path}")
        signature_payload = {
            "axis": clean_claim.get("axis"),
            "owner": clean_claim.get("owner"),
            "semantic_key": clean_claim.get("semantic_key"),
            "value": clean_claim.get("value"),
            "unit_raw": clean_claim.get("unit_raw"),
            "condition": clean_claim.get("condition"),
            "origin": clean_claim.get("origin"),
        }
        signature = _canonical_digest(signature_payload)
        if signature in signatures:
            finding(
                "duplicate_claim_signature",
                claims_path,
                f"line {line_number}: duplicates {signatures[signature]}",
            )
        elif isinstance(claim_id, str):
            signatures[signature] = claim_id

    curve_path = output_dir / "curve_audit.json"
    try:
        curve_audit = _read_json(curve_path)
    except (OSError, json.JSONDecodeError) as exc:
        finding("invalid_json", curve_path, str(exc))
        curve_audit = {}
    for message in _schema_errors(curve_audit, contract_schemas["curve_audit.json"]):
        finding("curve_schema", curve_path, message)
    if curve_audit.get("paper_key") != paper["paper_key"]:
        finding("paper_key_mismatch", curve_path, "curve audit paper_key differs from manifest")
    audited_csvs: set[str] = set()
    for series in curve_audit.get("series", []):
        if not isinstance(series, dict):
            continue
        csv_path = series.get("csv_path")
        if csv_path not in sources or sources[csv_path].get("path", "").endswith(".md"):
            finding("forbidden_curve_path", curve_path, repr(csv_path))
            continue
        audited_csvs.add(csv_path)
        if series.get("csv_sha256") != sources[csv_path]["sha256"]:
            finding("curve_digest_mismatch", curve_path, str(csv_path))
    expected_csvs = {record["path"] for record in paper.get("chart_csvs", [])}
    for missing_csv in sorted(expected_csvs - audited_csvs):
        finding("unaudited_chart_csv", curve_path, missing_csv)

    issues_path = output_dir / "issues.json"
    try:
        issues = _read_json(issues_path)
    except (OSError, json.JSONDecodeError) as exc:
        finding("invalid_json", issues_path, str(exc))
        issues = {}
    for message in _schema_errors(issues, contract_schemas["issues.json"]):
        finding("issues_schema", issues_path, message)
    if issues.get("paper_key") != paper["paper_key"]:
        finding("paper_key_mismatch", issues_path, "issues paper_key differs from manifest")

    audit_path = output_dir / "annotation_audit.jsonl"
    audit_rows, audit_errors = _jsonl(audit_path)
    for message in audit_errors:
        finding("invalid_jsonl", audit_path, message)
    for row in audit_rows:
        line_number = row["__line_number__"]
        clean_row = _strip_line_number(row)
        for message in _schema_errors(clean_row, contract_schemas["annotation_audit.jsonl"]):
            finding("audit_schema", audit_path, f"line {line_number}: {message}")
        if clean_row.get("paper_key") != paper["paper_key"]:
            finding("paper_key_mismatch", audit_path, f"line {line_number}")

    if not claims_only:
        expert_gt_path = output_dir / "expert_gt.json"
        try:
            expert_gt = _read_json(expert_gt_path)
        except (OSError, json.JSONDecodeError) as exc:
            finding("invalid_json", expert_gt_path, str(exc))
            expert_gt = {}
        for message in _schema_errors(expert_gt, v11_schema):
            finding("v11_schema", expert_gt_path, message)

    return {
        "paper_id": paper["paper_id"],
        "paper_key": paper["paper_key"],
        "claim_count": len(claims),
        "chart_csv_count": len(expected_csvs),
        "findings": findings,
    }


def validate(args: argparse.Namespace, *, emit: bool = True) -> tuple[int, dict[str, Any]]:
    repo_root = args.repo_root.resolve()
    output_root = (repo_root / args.output_root).resolve()
    manifest_path = output_root / "blind_input_manifest.json"
    manifest = _read_json(manifest_path)
    contract_schemas = {
        artifact: _load_schema(repo_root, schema_filename)
        for artifact, schema_filename in ARTIFACT_SCHEMAS.items()
    }
    v11_schema = _read_json(repo_root / V11_SCHEMA)
    papers = manifest["papers"]
    if getattr(args, "paper_id", None):
        papers = [paper for paper in papers if paper["paper_id"] == args.paper_id]
        if not papers:
            raise ValueError(f"paper_id not found: {args.paper_id}")
    reports = [
        _validate_paper(
            paper,
            repo_root,
            bool(args.claims_only),
            contract_schemas,
            v11_schema,
        )
        for paper in papers
    ]
    finding_count = sum(len(report["findings"]) for report in reports)
    result = {
        "status": "passed" if finding_count == 0 else "failed",
        "claims_only": bool(args.claims_only),
        "papers_checked": len(reports),
        "papers_passed": sum(not report["findings"] for report in reports),
        "finding_count": finding_count,
        "claim_count": sum(report.get("claim_count", 0) for report in reports),
        "chart_csv_count": sum(report.get("chart_csv_count", 0) for report in reports),
        "papers": reports,
    }
    if emit:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    return (0 if finding_count == 0 else 1), result


def seal(args: argparse.Namespace) -> int:
    repo_root = args.repo_root.resolve()
    output_root = (repo_root / args.output_root).resolve()
    seal_path = output_root / "blind_seal.json"
    if seal_path.exists():
        raise FileExistsError(f"blind seal already exists and will not be overwritten: {seal_path}")
    validation_args = argparse.Namespace(
        repo_root=repo_root,
        output_root=args.output_root,
        paper_id=None,
        claims_only=False,
    )
    exit_code, validation = validate(validation_args, emit=False)
    if exit_code:
        print(json.dumps(validation, ensure_ascii=False, indent=2))
        return exit_code
    manifest_path = output_root / "blind_input_manifest.json"
    manifest = _read_json(manifest_path)
    artifacts: list[dict[str, Any]] = []
    for paper in manifest["papers"]:
        paper_dir = repo_root / paper["output_dir"]
        for filename in REQUIRED_PAPER_ARTIFACTS:
            artifacts.append(_file_record(paper_dir / filename, repo_root))
    seal_value: dict[str, Any] = {
        "schema_version": "knowmat_independent_gt_blind_seal_v1",
        "sealed_at": _utc_now(),
        "model": manifest["model"],
        "isolation": manifest["isolation"],
        "blind_input_manifest": _file_record(manifest_path, repo_root),
        "validation_summary": {
            "papers_checked": validation["papers_checked"],
            "papers_passed": validation["papers_passed"],
            "claim_count": validation["claim_count"],
            "chart_csv_count": validation["chart_csv_count"],
            "finding_count": validation["finding_count"],
        },
        "artifacts": artifacts,
    }
    seal_value["content_digest"] = _canonical_digest(seal_value)
    _write_json(seal_path, seal_value)
    print(json.dumps({"status": "sealed", "path": _relative(seal_path, repo_root)}, indent=2))
    return 0


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=Path(__file__).resolve().parents[1])
    subparsers = parser.add_subparsers(dest="command", required=True)

    prepare_parser = subparsers.add_parser("prepare")
    prepare_parser.add_argument("--baseline", type=Path, default=DEFAULT_BASELINE)
    prepare_parser.add_argument("--source-root", type=Path, default=DEFAULT_SOURCE_ROOT)
    prepare_parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    prepare_parser.add_argument("--model", default="gpt-5.6-sol")
    prepare_parser.set_defaults(handler=prepare)

    validate_parser = subparsers.add_parser("validate")
    validate_parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    validate_parser.add_argument("--paper-id")
    validate_parser.add_argument("--claims-only", action="store_true")
    validate_parser.set_defaults(handler=lambda args: validate(args)[0])

    seal_parser = subparsers.add_parser("seal")
    seal_parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    seal_parser.set_defaults(handler=seal)
    return parser


def main(argv: Iterable[str] | None = None) -> int:
    args = _parser().parse_args(list(argv) if argv is not None else None)
    try:
        return int(args.handler(args))
    except (FileNotFoundError, ValueError, json.JSONDecodeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
