"""Fresh OCR baseline freezing and mutation verification."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable


MANIFEST_SCHEMA = "knowmat_ocr_baseline_v1"
DEFAULT_MANIFEST_DIR = ".knowmat_ocr_baselines"


class OCRManifestError(RuntimeError):
    pass


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def manifest_path(input_root: Path, name_or_path: str | Path) -> Path:
    raw = Path(name_or_path).expanduser()
    if raw.is_absolute() or raw.parent != Path(".") or raw.suffix == ".json":
        return raw.resolve() if raw.is_absolute() else (Path.cwd() / raw).resolve()
    return (input_root / DEFAULT_MANIFEST_DIR / f"{raw.name}.json").resolve()


def _relative(path: Path, root: Path) -> str:
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        raise OCRManifestError(f"OCR artifact is outside the input root: {path}") from None


def _read_structured(path: Path) -> Any:
    if not path.is_file() or path.stat().st_size == 0:
        raise OCRManifestError(f"Missing or empty OCR structured artifact: {path}")
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise OCRManifestError(f"Invalid OCR structured JSON {path}: {exc}") from exc
    if not isinstance(value, (list, dict)):
        raise OCRManifestError(f"OCR structured artifact must be a list/object: {path}")
    if not value:
        raise OCRManifestError(f"OCR structured artifact contains no records: {path}")
    return value


def _record_for_pdf(pdf_path: Path, input_root: Path) -> dict[str, Any]:
    stem = pdf_path.stem
    paper_dir = input_root / stem
    md_path = paper_dir / f"{stem}.md"
    json_path = paper_dir / f"{stem}.json"
    if not pdf_path.is_file() or pdf_path.stat().st_size == 0:
        raise OCRManifestError(f"Missing or empty PDF: {pdf_path}")
    if not md_path.is_file() or md_path.stat().st_size == 0:
        raise OCRManifestError(f"Missing or empty OCR Markdown: {md_path}")
    if not md_path.read_text(encoding="utf-8", errors="replace").strip():
        raise OCRManifestError(f"OCR Markdown contains no text: {md_path}")
    _read_structured(json_path)
    return {
        "paper_key": stem,
        "pdf_path": _relative(pdf_path, input_root),
        "pdf_sha256": sha256_file(pdf_path),
        "pdf_size": pdf_path.stat().st_size,
        "ocr_markdown_path": _relative(md_path, input_root),
        "ocr_markdown_sha256": sha256_file(md_path),
        "ocr_markdown_size": md_path.stat().st_size,
        "ocr_json_path": _relative(json_path, input_root),
        "ocr_json_sha256": sha256_file(json_path),
        "ocr_json_size": json_path.stat().st_size,
        "status": "success",
    }


def _baseline_digest(
    *, name: str, backend: dict[str, Any], records: list[dict[str, Any]]
) -> str:
    payload = {
        "schema_version": MANIFEST_SCHEMA,
        "baseline_name": name,
        "backend": backend,
        "records": records,
    }
    return hashlib.sha256(
        json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
    ).hexdigest()


def freeze_ocr_baseline(
    input_root: Path,
    pdf_paths: Iterable[Path],
    *,
    baseline_name: str,
    backend: dict[str, Any],
    fresh_pdf_paths: Iterable[Path],
    output_path: Path | None = None,
) -> dict[str, Any]:
    """Freeze only artifacts proven to have completed in the current OCR run."""

    root = input_root.resolve()
    pdfs = sorted({path.resolve() for path in pdf_paths}, key=lambda row: row.name.casefold())
    fresh = {path.resolve() for path in fresh_pdf_paths}
    if not pdfs:
        raise OCRManifestError("Cannot freeze an empty OCR baseline")
    if fresh != set(pdfs):
        missing = sorted(path.name for path in set(pdfs) - fresh)
        extra = sorted(path.name for path in fresh - set(pdfs))
        raise OCRManifestError(
            "OCR baseline is not a complete fresh run; "
            f"missing_current_run={missing}, unexpected={extra}"
        )
    records = [_record_for_pdf(path, root) for path in pdfs]
    if len({row["paper_key"] for row in records}) != len(records):
        raise OCRManifestError("Duplicate PDF stems cannot be represented in one OCR baseline")
    baseline_id = _baseline_digest(name=baseline_name, backend=backend, records=records)
    now = datetime.now(timezone.utc).isoformat()
    document = {
        "schema_version": MANIFEST_SCHEMA,
        "baseline_name": baseline_name,
        "baseline_id": baseline_id,
        "status": "frozen",
        "created_at": now,
        "frozen_at": now,
        "input_root": str(root),
        "backend": dict(backend),
        "record_count": len(records),
        "records": records,
    }
    target = output_path or manifest_path(root, baseline_name)
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_suffix(target.suffix + ".tmp")
    temporary.write_text(
        json.dumps(document, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    temporary.replace(target)
    return document


def load_ocr_manifest(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise OCRManifestError(f"OCR baseline manifest not found: {path}") from None
    except json.JSONDecodeError as exc:
        raise OCRManifestError(f"Invalid OCR baseline manifest {path}: {exc}") from exc
    if not isinstance(value, dict) or value.get("schema_version") != MANIFEST_SCHEMA:
        raise OCRManifestError(f"Unsupported OCR baseline manifest: {path}")
    if value.get("status") != "frozen":
        raise OCRManifestError(f"OCR baseline is not frozen: {path}")
    return value


def verify_ocr_baseline(
    manifest_file: Path, input_root: Path | None = None
) -> dict[str, Any]:
    """Verify every PDF, Markdown, and structured OCR artifact by hash."""

    document = load_ocr_manifest(manifest_file)
    root = (input_root or Path(str(document.get("input_root") or ""))).resolve()
    records = document.get("records") or []
    if not isinstance(records, list) or len(records) != document.get("record_count"):
        raise OCRManifestError("OCR baseline record count is inconsistent")
    for record in records:
        if not isinstance(record, dict) or record.get("status") != "success":
            raise OCRManifestError("OCR baseline contains an unsuccessful record")
        for prefix in ("pdf", "ocr_markdown", "ocr_json"):
            relative = record.get(f"{prefix}_path")
            expected_hash = record.get(f"{prefix}_sha256")
            expected_size = record.get(f"{prefix}_size")
            path = root / str(relative or "")
            if not path.is_file():
                raise OCRManifestError(f"Frozen OCR artifact is missing: {path}")
            if path.stat().st_size != expected_size:
                raise OCRManifestError(f"Frozen OCR artifact size changed: {path}")
            actual = sha256_file(path)
            if actual != expected_hash:
                raise OCRManifestError(f"Frozen OCR artifact hash changed: {path}")
    expected_id = _baseline_digest(
        name=str(document.get("baseline_name") or ""),
        backend=dict(document.get("backend") or {}),
        records=records,
    )
    if expected_id != document.get("baseline_id"):
        raise OCRManifestError("OCR baseline identity digest is inconsistent")
    return document


def verify_ocr_record(
    document: dict[str, Any], markdown_path: Path, input_root: Path | None = None
) -> dict[str, Any]:
    """Verify the one frozen record used by a pending extraction call."""

    root = (input_root or Path(str(document.get("input_root") or ""))).resolve()
    target = markdown_path.resolve()
    for record in document.get("records", []) or []:
        candidate = (root / str(record.get("ocr_markdown_path") or "")).resolve()
        if candidate != target:
            continue
        for prefix in ("pdf", "ocr_markdown", "ocr_json"):
            path = root / str(record.get(f"{prefix}_path") or "")
            if not path.is_file():
                raise OCRManifestError(f"Frozen OCR artifact is missing: {path}")
            if path.stat().st_size != record.get(f"{prefix}_size"):
                raise OCRManifestError(f"Frozen OCR artifact size changed: {path}")
            if sha256_file(path) != record.get(f"{prefix}_sha256"):
                raise OCRManifestError(f"Frozen OCR artifact hash changed: {path}")
        return record
    raise OCRManifestError(f"OCR Markdown is not part of the frozen baseline: {target}")


def markdown_paths(document: dict[str, Any], input_root: Path) -> list[Path]:
    return [
        input_root.resolve() / record["ocr_markdown_path"]
        for record in document.get("records", [])
    ]
