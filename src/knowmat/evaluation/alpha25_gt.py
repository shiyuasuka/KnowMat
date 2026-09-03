"""Offline, source-aware alpha25 comparison against AI-generated GT."""

from __future__ import annotations

import json
import math
import os
import re
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

from knowmat.alpha25.evidence import evidence_body, normalize_evidence_text
from knowmat.alpha25.planner import build_evidence_units
from knowmat.ocr_manifest import load_ocr_manifest, verify_ocr_baseline


AXES = ("composition", "processing", "structure", "characterization", "properties")
_UNIQUE_FACT_IGNORED_FIELDS = {
    "Item_ID",
    "candidate_stage_id",
    "characterization_id",
    "confidence",
    "entity_id",
    "observation_id",
    "property_id_candidate",
    "sample_id",
    "sample_id_raw",
    "stage_index",
    "stage_index_candidate",
    "stage_scope",
    "stage_uid",
}


def _fold(value: Any) -> str:
    return re.sub(r"[^a-z0-9]+", " ", str(value or "").casefold()).strip()


def _tokens(value: Any) -> set[str]:
    return {token for token in _fold(value).split() if len(token) > 1}


def _json_text(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)


def _source_evidence(value: Any) -> list[str]:
    rows: list[str] = []
    if isinstance(value, dict):
        for key, child in value.items():
            if key == "source_evidence":
                if isinstance(child, str):
                    child = [child]
                if isinstance(child, list):
                    rows.extend(str(row) for row in child if str(row).strip())
            else:
                rows.extend(_source_evidence(child))
    elif isinstance(value, list):
        for child in value:
            rows.extend(_source_evidence(child))
    return list(dict.fromkeys(rows))


def _loose_evidence_match(evidence: str, source_text: str) -> bool:
    needle = re.sub(r"[^a-z0-9]+", "", _fold(evidence_body(evidence)))
    haystack = re.sub(r"[^a-z0-9]+", "", _fold(source_text))
    return len(needle) >= 12 and needle in haystack


def _compact_evidence(value: str) -> str:
    """Fold presentation-only HTML/TeX differences for source auditing."""

    without_html = re.sub(r"</?[A-Za-z][^>]*>", "", str(value or ""))
    return re.sub(r"[^a-z0-9]+", "", without_html.casefold())


_DIGITIZED_FIGURE_BLOCK = re.compile(
    r"(?ms)^> \[Figure[^\n\]]*VLM-digitized[^\n\]]*\]:\s*\n"
    r".*?(?=\n\s*\n|\Z)"
)


def digitized_figure_evidence(text: str) -> str:
    """Return only deterministic chart blocks from an enriched result Markdown."""

    return "\n\n".join(_DIGITIZED_FIGURE_BLOCK.findall(str(text or "")))


@dataclass(frozen=True)
class EvidenceAuditCorpus:
    """Pre-normalized OCR plus deterministic table projections for one paper."""

    source: str
    projected: tuple[str, ...]
    compact_source: str
    compact_projected: tuple[str, ...]


def build_evidence_audit_corpus(source_text: str) -> EvidenceAuditCorpus:
    """Build the same source-derived table views that production may assign.

    Production's evidence gate accepts literal evidence from a bounded table
    projection, not only from the original Markdown row.  Reconstructing those
    views here prevents a deterministic ``header: value`` rendering from being
    mislabeled as a hallucination while still forbidding semantic paraphrases.
    """

    source = str(source_text or "")
    projected: list[str] = []
    try:
        # Reconstruct the same deterministic table/prose views used by the
        # production Alpha25 planner.  Auditing with planner.py's legacy helper
        # defaults (2 columns × 10 rows) falsely labels literal evidence from
        # the production 4 × 12 projection as unsupported.
        prose_chars = int(os.getenv("KNOWMAT2_ALPHA25_PROSE_CHARS", "8000"))
        table_columns = int(
            os.getenv("KNOWMAT2_ALPHA25_TABLE_COLUMNS", "4")
        )
        table_rows = int(os.getenv("KNOWMAT2_ALPHA25_TABLE_ROWS", "12"))
        context_chars = int(
            os.getenv("KNOWMAT2_ALPHA25_TABLE_CONTEXT_CHARS", "600")
        )
        projection_settings = {(table_columns, table_rows), (2, 10)}
        units = [
            unit
            for columns, rows in sorted(projection_settings)
            for unit in build_evidence_units(
                source,
                max_prose_chars=prose_chars,
                table_columns=columns,
                table_rows=rows,
                table_context_chars=context_chars,
            )
        ]
    except Exception:
        units = []
    for unit in units:
        for value in (unit.text, unit.source_text):
            normalized = normalize_evidence_text(value)
            if normalized:
                projected.append(normalized)
    projected = list(dict.fromkeys(projected))
    normalized_source = normalize_evidence_text(source)
    return EvidenceAuditCorpus(
        source=normalized_source,
        projected=tuple(projected),
        compact_source=_compact_evidence(normalized_source),
        compact_projected=tuple(_compact_evidence(value) for value in projected),
    )


def _evidence_row_status(
    evidence: str, corpus: EvidenceAuditCorpus, *, allow_composite: bool = True
) -> str:
    needle = normalize_evidence_text(evidence_body(evidence))
    if not needle:
        return "unsupported"
    if needle in corpus.source:
        return "supported"
    if any(needle in source for source in corpus.projected):
        return "format_mismatch"
    markdown_delimiter = re.fullmatch(
        r"\|?\s*:?-{3,}:?\s*(?:\|\s*:?-{3,}:?\s*)+\|?",
        needle,
    )
    if markdown_delimiter and any(
        re.search(
            r"\|?\s*:?-{3,}:?\s*(?:\|\s*:?-{3,}:?\s*)+\|?",
            projected,
        )
        for projected in corpus.projected
    ):
        # HTML/OCR tables are deterministically projected to Markdown. A pure
        # alignment row carries no factual content, and its column count may
        # differ after bounded projection; classify that serialization artifact
        # as a format mismatch rather than an unsupported extracted fact.
        return "format_mismatch"
    compact = _compact_evidence(needle)
    if len(compact) >= 12 and (
        compact in corpus.compact_source
        or any(compact in source for source in corpus.compact_projected)
    ):
        return "format_mismatch"
    if allow_composite and " | " in needle:
        # Alpha25 normalization stores parameter evidence as one string. When
        # several already-gated quotes or two inputs of a derived parameter are
        # joined, the composite is not a literal source substring even though
        # every part is. Treat that deterministic serialization as a format
        # mismatch, not an unsupported fact.
        parts = list(
            dict.fromkeys(part.strip(" |").strip() for part in needle.split(" | "))
        )
        parts = [part for part in parts if part]
        if len(parts) >= 2:
            statuses = [
                _evidence_row_status(part, corpus, allow_composite=False)
                for part in parts
            ]
            if all(status in {"supported", "format_mismatch"} for status in statuses):
                return "format_mismatch"
    return "unsupported"


def audit_fact_evidence(
    fact: dict[str, Any],
    source_text: str,
    *,
    corpus: EvidenceAuditCorpus | None = None,
) -> str:
    evidence = _source_evidence(fact)
    if not evidence:
        return "ambiguous"
    audit_corpus = corpus or build_evidence_audit_corpus(source_text)
    statuses = [_evidence_row_status(row, audit_corpus) for row in evidence]
    if all(status == "supported" for status in statuses):
        return "supported"
    if all(status in {"supported", "format_mismatch"} for status in statuses):
        return "format_mismatch"
    return "unsupported"


def axis_records(item: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    extracted = item.get("Extracted_Data") or {}
    composition = extracted.get("Composition") or {}
    processing = extracted.get("Processing") or {}
    route = processing.get("Process_Route") or {}
    structure = extracted.get("Structure") or {}
    return {
        "composition": [
            row
            for row in composition.get("Composition_Observations", []) or []
            if isinstance(row, dict)
        ],
        "processing": [
            row
            for row in (route.get("stages") or route.get("candidate_stages") or [])
            if isinstance(row, dict)
        ],
        "structure": [
            row
            for row in structure.get("Structure_Observations", []) or []
            if isinstance(row, dict)
        ],
        "characterization": [
            row
            for row in structure.get("Characterization", []) or []
            if isinstance(row, dict)
        ],
        "properties": [
            row for row in extracted.get("Properties", []) or [] if isinstance(row, dict)
        ],
    }


def _item_signal(item: dict[str, Any]) -> set[str]:
    extracted = item.get("Extracted_Data") or {}
    composition = extracted.get("Composition") or {}
    identity = composition.get("Material_Identity") or {}
    processing = (extracted.get("Processing") or {}).get("Process_Route") or {}
    stages = processing.get("stages") or processing.get("candidate_stages") or []
    values = [
        item.get("Sample_ID"),
        item.get("Role"),
        item.get("Data_Nature"),
        identity,
        [
            (row.get("process_code"), row.get("process_name"), row.get("process_name_raw"))
            for row in stages
            if isinstance(row, dict)
        ],
        composition.get("Composition_Observations"),
    ]
    return _tokens(_json_text(values))


def _similarity(left: set[str], right: set[str]) -> float:
    if not left or not right:
        return 0.0
    return len(left & right) / len(left | right)


def match_items(
    extracted_items: list[dict[str, Any]], gt_items: list[dict[str, Any]]
) -> tuple[list[tuple[int, int, float]], list[int], list[int]]:
    candidates: list[tuple[float, int, int]] = []
    for left_index, left in enumerate(extracted_items):
        left_signal = _item_signal(left)
        for right_index, right in enumerate(gt_items):
            score = _similarity(left_signal, _item_signal(right))
            if score:
                candidates.append((score, left_index, right_index))
    matches: list[tuple[int, int, float]] = []
    used_left: set[int] = set()
    used_right: set[int] = set()
    for score, left_index, right_index in sorted(candidates, reverse=True):
        if score < 0.08 or left_index in used_left or right_index in used_right:
            continue
        matches.append((left_index, right_index, score))
        used_left.add(left_index)
        used_right.add(right_index)
    return (
        matches,
        [index for index in range(len(extracted_items)) if index not in used_left],
        [index for index in range(len(gt_items)) if index not in used_right],
    )


def _numbers(value: Any) -> set[str]:
    return set(re.findall(r"[-+]?\d+(?:\.\d+)?", _json_text(value)))


def _fact_similarity(left: dict[str, Any], right: dict[str, Any]) -> float:
    left_tokens = _tokens(_json_text(left))
    right_tokens = _tokens(_json_text(right))
    token_score = _similarity(left_tokens, right_tokens)
    left_numbers = _numbers(left)
    right_numbers = _numbers(right)
    if left_numbers and right_numbers and not (left_numbers & right_numbers):
        return 0.0
    number_bonus = 0.25 if left_numbers & right_numbers else 0.0
    return min(1.0, token_score + number_bonus)


def match_facts(
    extracted: list[dict[str, Any]], gt: list[dict[str, Any]]
) -> tuple[int, list[int], list[int]]:
    candidates = [
        (_fact_similarity(left, right), left_index, right_index)
        for left_index, left in enumerate(extracted)
        for right_index, right in enumerate(gt)
    ]
    used_left: set[int] = set()
    used_right: set[int] = set()
    for score, left_index, right_index in sorted(candidates, reverse=True):
        if score < 0.18 or left_index in used_left or right_index in used_right:
            continue
        used_left.add(left_index)
        used_right.add(right_index)
    return (
        len(used_left),
        [index for index in range(len(extracted)) if index not in used_left],
        [index for index in range(len(gt)) if index not in used_right],
    )


def _unique_fact_value(value: Any) -> Any:
    """Remove assignment/runner metadata while preserving factual content."""

    if isinstance(value, dict):
        return {
            key: _unique_fact_value(child)
            for key, child in value.items()
            if key not in _UNIQUE_FACT_IGNORED_FIELDS
        }
    if isinstance(value, list):
        return [_unique_fact_value(child) for child in value]
    return value


def deduplicate_fact_assignments(
    records: Iterable[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Collapse exact cross-item copies for a content-level GT comparison."""

    unique: list[dict[str, Any]] = []
    seen: set[str] = set()
    for record in records:
        signature = _json_text(_unique_fact_value(record))
        if signature in seen:
            continue
        seen.add(signature)
        unique.append(record)
    return unique


_CORE_TENSILE_ALIASES = {
    "ultimate tensile strength": "uts",
    "ultimate strength": "uts",
    "engineering uts": "uts",
    "uts": "uts",
    "yield strength": "ys",
    "yield stress": "ys",
    "engineering yield strength": "ys",
    "ys": "ys",
    "elongation": "el",
    "total elongation": "el",
    "uniform elongation": "el",
    "elongation at fracture": "el",
    "elongation to failure": "el",
}


def _core_tensile_kind(record: dict[str, Any]) -> str | None:
    origin = _fold(record.get("Observation_Origin"))
    decision = _fold(record.get("semantic_decision"))
    if origin and origin != "direct experiment":
        return None
    if decision and decision != "accept core tensile":
        return None
    candidates = (
        record.get("Canonical_Property"),
        record.get("canonical_property"),
        record.get("Property_Subtype"),
        record.get("property_subtype"),
        record.get("Property_Name_Raw"),
        record.get("property_name_raw"),
        record.get("Property_Name"),
    )
    for value in candidates:
        folded = _fold(value).replace("engineering ", "")
        if folded in _CORE_TENSILE_ALIASES:
            return _CORE_TENSILE_ALIASES[folded]
        if "ultimate tensile strength" in folded:
            return "uts"
        if "yield strength" in folded or "yield stress" in folded:
            return "ys"
        if "elongation" in folded:
            return "el"
    return None


def _core_value_signature(record: dict[str, Any]) -> tuple[str, str, tuple[float, ...]]:
    raw_value_object = record.get("Value")
    value = raw_value_object
    if not isinstance(value, dict):
        value = record.get("value") if isinstance(record.get("value"), dict) else {}
    value_kind = _fold(value.get("value_kind") or record.get("value_kind") or "scalar")
    unit = _fold(
        value.get("canonical_unit")
        or value.get("unit_raw")
        or record.get("canonical_unit")
        or record.get("Unit")
        or record.get("unit_raw")
    )
    numeric: list[float] = []
    for key in ("value_num", "canonical_value", "bound_value", "value_min", "value_max"):
        candidate = value.get(key)
        if isinstance(candidate, (int, float)) and not isinstance(candidate, bool):
            numeric.append(float(candidate))
    if not numeric:
        raw = (
            value.get("value_raw")
            or record.get("value_raw")
            or (raw_value_object if not isinstance(raw_value_object, dict) else None)
        )
        if value_kind == "scalar":
            match = re.search(r"[-+]?\d+(?:\.\d+)?(?:[eE][-+]?\d+)?", str(raw or ""))
            if match:
                numeric.append(float(match.group(0)))
    return value_kind, unit, tuple(numeric)


def _close_number(left: float, right: float) -> bool:
    return math.isclose(left, right, rel_tol=1e-4, abs_tol=1e-6)


def _core_tensile_similarity(left: dict[str, Any], right: dict[str, Any]) -> float:
    left_kind = _core_tensile_kind(left)
    right_kind = _core_tensile_kind(right)
    if not left_kind or left_kind != right_kind:
        return 0.0
    left_value_kind, left_unit, left_numbers = _core_value_signature(left)
    right_value_kind, right_unit, right_numbers = _core_value_signature(right)
    if left_value_kind and right_value_kind and left_value_kind != right_value_kind:
        return 0.0
    if left_unit and right_unit and left_unit != right_unit:
        return 0.0
    if left_numbers and right_numbers:
        if len(left_numbers) != len(right_numbers) or not all(
            _close_number(a, b) for a, b in zip(left_numbers, right_numbers)
        ):
            return 0.0
    elif left_numbers != right_numbers:
        return 0.0
    token_score = _similarity(_tokens(_json_text(left)), _tokens(_json_text(right)))
    return 0.8 + min(0.2, token_score)


def match_core_tensile(
    extracted: list[dict[str, Any]], gt: list[dict[str, Any]]
) -> tuple[int, list[int], list[int]]:
    left = [(index, row) for index, row in enumerate(extracted) if _core_tensile_kind(row)]
    right = [(index, row) for index, row in enumerate(gt) if _core_tensile_kind(row)]
    candidates = [
        (_core_tensile_similarity(left_row, right_row), left_index, right_index)
        for left_index, left_row in left
        for right_index, right_row in right
    ]
    used_left: set[int] = set()
    used_right: set[int] = set()
    for score, left_index, right_index in sorted(candidates, reverse=True):
        if score <= 0 or left_index in used_left or right_index in used_right:
            continue
        used_left.add(left_index)
        used_right.add(right_index)
    return (
        len(used_left),
        [index for index, _ in left if index not in used_left],
        [index for index, _ in right if index not in used_right],
    )


def _metrics(
    matched: int,
    extracted_count: int,
    gt_count: int,
    *,
    supported_extracted: int | None = None,
) -> dict[str, Any]:
    supported_count = extracted_count if supported_extracted is None else supported_extracted
    precision = matched / supported_count if supported_count else (1.0 if not gt_count else 0.0)
    recall = matched / gt_count if gt_count else (1.0 if not extracted_count else 0.0)
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    raw_precision = (
        matched / extracted_count if extracted_count else (1.0 if not gt_count else 0.0)
    )
    return {
        "matched": matched,
        "extracted": extracted_count,
        "supported_extracted": supported_count,
        "supported_gt": gt_count,
        "precision": round(precision, 6),
        "raw_precision": round(raw_precision, 6),
        "recall": round(recall, 6),
        "f1": round(f1, 6),
    }


def compare_document(
    extracted_document: dict[str, Any],
    gt_document: dict[str, Any],
    source_text: str,
    *,
    extracted_source_text: str | None = None,
) -> dict[str, Any]:
    extracted_items = [
        row for row in extracted_document.get("items", []) or [] if isinstance(row, dict)
    ]
    gt_items = [row for row in gt_document.get("items", []) or [] if isinstance(row, dict)]
    item_matches, unmatched_extracted_items, unmatched_gt_items = match_items(
        extracted_items, gt_items
    )
    gt_corpus = build_evidence_audit_corpus(source_text)
    extracted_audit_text = extracted_source_text or source_text
    extracted_corpus = build_evidence_audit_corpus(extracted_audit_text)

    def audit_items(
        items: list[dict[str, Any]],
        audit_text: str,
        audit_corpus: EvidenceAuditCorpus,
    ) -> tuple[
        dict[tuple[int, str], list[tuple[dict[str, Any], str]]],
        Counter[str],
    ]:
        audited: dict[tuple[int, str], list[tuple[dict[str, Any], str]]] = {}
        counts: Counter[str] = Counter()
        for item_index, item in enumerate(items):
            for axis, records in axis_records(item).items():
                rows: list[tuple[dict[str, Any], str]] = []
                for record in records:
                    status = audit_fact_evidence(
                        record, audit_text, corpus=audit_corpus
                    )
                    counts[status] += 1
                    rows.append((record, status))
                audited[(item_index, axis)] = rows
        return audited, counts

    audited_extracted, extracted_evidence_counts = audit_items(
        extracted_items, extracted_audit_text, extracted_corpus
    )
    audited_gt, gt_evidence_counts = audit_items(gt_items, source_text, gt_corpus)

    supported_statuses = {"supported", "format_mismatch"}

    def supported_rows(
        audited: dict[tuple[int, str], list[tuple[dict[str, Any], str]]],
        item_index: int,
        axis: str,
    ) -> list[dict[str, Any]]:
        return [
            record
            for record, status in audited.get((item_index, axis), [])
            if status in supported_statuses
        ]

    axis_totals = {}
    for axis in AXES:
        extracted_count = sum(
            len(audited_extracted.get((index, axis), []))
            for index in range(len(extracted_items))
        )
        supported_extracted_count = sum(
            len(supported_rows(audited_extracted, index, axis))
            for index in range(len(extracted_items))
        )
        supported_gt_count = sum(
            len(supported_rows(audited_gt, index, axis))
            for index in range(len(gt_items))
        )
        axis_totals[axis] = {
            "matched": 0,
            "extracted": extracted_count,
            "supported_extracted": supported_extracted_count,
            "supported_gt": supported_gt_count,
        }

    core_totals = {
        "matched": 0,
        "extracted": sum(
            bool(_core_tensile_kind(record))
            for index in range(len(extracted_items))
            for record, _status in audited_extracted.get((index, "properties"), [])
        ),
        "supported_extracted": sum(
            bool(_core_tensile_kind(record))
            for index in range(len(extracted_items))
            for record in supported_rows(audited_extracted, index, "properties")
        ),
        "supported_gt": sum(
            bool(_core_tensile_kind(record))
            for index in range(len(gt_items))
            for record in supported_rows(audited_gt, index, "properties")
        ),
    }
    unique_axis_metrics: dict[str, dict[str, Any]] = {}
    for axis in AXES:
        extracted_unique = deduplicate_fact_assignments(
            record
            for index in range(len(extracted_items))
            for record in supported_rows(audited_extracted, index, axis)
        )
        gt_unique = deduplicate_fact_assignments(
            record
            for index in range(len(gt_items))
            for record in supported_rows(audited_gt, index, axis)
        )
        matched, _extra, _miss = match_facts(extracted_unique, gt_unique)
        unique_axis_metrics[axis] = _metrics(
            matched,
            len(extracted_unique),
            len(gt_unique),
            supported_extracted=len(extracted_unique),
        )
    extracted_unique_core = deduplicate_fact_assignments(
        record
        for index in range(len(extracted_items))
        for record in supported_rows(audited_extracted, index, "properties")
        if _core_tensile_kind(record)
    )
    gt_unique_core = deduplicate_fact_assignments(
        record
        for index in range(len(gt_items))
        for record in supported_rows(audited_gt, index, "properties")
        if _core_tensile_kind(record)
    )
    unique_core_matched, _unique_core_extra, _unique_core_miss = match_core_tensile(
        extracted_unique_core, gt_unique_core
    )
    disagreements: dict[str, list[dict[str, Any]]] = {
        "extraction_misses": [],
        "source_supported_extras": [],
        "unsupported_extracted_facts": [],
        "semantic_ambiguity": [],
        "likely_gt_defects": [],
    }

    for item_index, item in enumerate(extracted_items):
        for axis in AXES:
            for record_index, (record, status) in enumerate(
                audited_extracted.get((item_index, axis), [])
            ):
                if status in supported_statuses:
                    continue
                disagreements["unsupported_extracted_facts"].append(
                    {
                        "item_index": item_index,
                        "sample_id": item.get("Sample_ID"),
                        "axis": axis,
                        "record_index": record_index,
                        "evidence_status": status,
                        "fact": record,
                    }
                )

    for left_index, right_index, score in item_matches:
        for axis in AXES:
            extracted_records = supported_rows(audited_extracted, left_index, axis)
            gt_records = supported_rows(audited_gt, right_index, axis)
            matched, extra_indices, miss_indices = match_facts(
                extracted_records, gt_records
            )
            axis_totals[axis]["matched"] += matched
            disagreements["source_supported_extras"].extend(
                {
                    "item_index": left_index,
                    "axis": axis,
                    "fact": extracted_records[index],
                }
                for index in extra_indices
            )
            disagreements["extraction_misses"].extend(
                {
                    "item_index": right_index,
                    "axis": axis,
                    "fact": gt_records[index],
                }
                for index in miss_indices
            )
        extracted_core = [
            row
            for row in supported_rows(audited_extracted, left_index, "properties")
            if _core_tensile_kind(row)
        ]
        gt_core = [
            row
            for row in supported_rows(audited_gt, right_index, "properties")
            if _core_tensile_kind(row)
        ]
        core_matched, _core_extra, _core_miss = match_core_tensile(
            extracted_core, gt_core
        )
        core_totals["matched"] += core_matched
        if score < 0.15:
            disagreements["semantic_ambiguity"].append(
                {"extracted_item": left_index, "gt_item": right_index, "score": score}
            )

    for index in unmatched_extracted_items:
        for axis in AXES:
            disagreements["source_supported_extras"].extend(
                {
                    "unmatched_item": index,
                    "sample_id": extracted_items[index].get("Sample_ID"),
                    "axis": axis,
                    "fact": record,
                }
                for record in supported_rows(audited_extracted, index, axis)
            )
    for index in unmatched_gt_items:
        for axis in AXES:
            disagreements["extraction_misses"].extend(
                {
                    "unmatched_item": index,
                    "sample_id": gt_items[index].get("Sample_ID"),
                    "axis": axis,
                    "fact": record,
                }
                for record in supported_rows(audited_gt, index, axis)
            )
    if gt_evidence_counts["unsupported"] or gt_evidence_counts["ambiguous"]:
        disagreements["likely_gt_defects"].append(dict(gt_evidence_counts))

    supported_extracted_items = sum(
        any(
            supported_rows(audited_extracted, index, axis)
            for axis in AXES
        )
        for index in range(len(extracted_items))
    )
    supported_gt_items = sum(
        any(supported_rows(audited_gt, index, axis) for axis in AXES)
        for index in range(len(gt_items))
    )
    tolerance = max(2, math.ceil(0.3 * supported_gt_items))

    return {
        "item_counts": {
            "extracted": len(extracted_items),
            "gt": len(gt_items),
            "supported_extracted": supported_extracted_items,
            "supported_gt": supported_gt_items,
            "matched": len(item_matches),
            "unmatched_extracted": len(unmatched_extracted_items),
            "unmatched_gt": len(unmatched_gt_items),
            "tolerance": tolerance,
            "within_tolerance": abs(
                supported_extracted_items - supported_gt_items
            )
            <= tolerance,
        },
        "extracted_evidence_audit": dict(extracted_evidence_counts),
        "gt_evidence_audit": dict(gt_evidence_counts),
        "axes": {
            axis: _metrics(
                values["matched"],
                values["extracted"],
                values["supported_gt"],
                supported_extracted=values["supported_extracted"],
            )
            for axis, values in axis_totals.items()
        },
        "core_tensile": _metrics(
            core_totals["matched"],
            core_totals["extracted"],
            core_totals["supported_gt"],
            supported_extracted=core_totals["supported_extracted"],
        ),
        "unique_axes": unique_axis_metrics,
        "unique_core_tensile": _metrics(
            unique_core_matched,
            len(extracted_unique_core),
            len(gt_unique_core),
            supported_extracted=len(extracted_unique_core),
        ),
        "disagreements": disagreements,
    }


def _load_object(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"Expected JSON object: {path}")
    return value


def _result_path(results_root: Path, paper_key: str) -> Path | None:
    safe_key = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", paper_key).strip(". ")
    safe_key = re.sub(r"[_\s]+", "_", safe_key) or "unnamed"
    candidates = (
        results_root / paper_key / "final.json",
        results_root / paper_key / f"{paper_key}_extraction.json",
        results_root / safe_key / "final.json",
        results_root / safe_key / f"{safe_key}_extraction.json",
        results_root / f"{paper_key}.json",
    )
    return next((path for path in candidates if path.is_file()), None)


def _result_digitized_evidence(result_path: Path) -> str:
    """Load only source-traceable digitized blocks beside a production result."""

    txt_parse = result_path.parent / "txt_parse"
    markdown_paths = sorted(txt_parse.glob("*_final_output.md"))
    if not markdown_paths:
        return ""
    text = markdown_paths[0].read_text(encoding="utf-8", errors="replace")
    return digitized_figure_evidence(text)


def evaluate_corpus(
    *, manifest_path: Path, results_root: Path, gt_root: Path
) -> dict[str, Any]:
    manifest = verify_ocr_baseline(manifest_path)
    input_root = Path(manifest["input_root"])
    papers: dict[str, Any] = {}
    missing: list[dict[str, str]] = []
    for record in manifest["records"]:
        key = record["paper_key"]
        result_path = _result_path(results_root, key)
        gt_path = gt_root / f"{key}.json"
        if result_path is None or not gt_path.is_file():
            missing.append(
                {
                    "paper_key": key,
                    "result": str(result_path or "missing"),
                    "gt": str(gt_path if gt_path.is_file() else "missing"),
                }
            )
            continue
        source_text = (input_root / record["ocr_markdown_path"]).read_text(
            encoding="utf-8", errors="replace"
        )
        chart_evidence = _result_digitized_evidence(result_path)
        extracted_source_text = (
            source_text + "\n\n" + chart_evidence if chart_evidence else source_text
        )
        papers[key] = compare_document(
            _load_object(result_path),
            _load_object(gt_path),
            source_text,
            extracted_source_text=extracted_source_text,
        )

    corpus_axes: dict[str, dict[str, int]] = {
        axis: {
            "matched": 0,
            "extracted": 0,
            "supported_extracted": 0,
            "supported_gt": 0,
        }
        for axis in AXES
    }
    corpus_core = {
        "matched": 0,
        "extracted": 0,
        "supported_extracted": 0,
        "supported_gt": 0,
    }
    corpus_unique_axes: dict[str, dict[str, int]] = {
        axis: {
            "matched": 0,
            "extracted": 0,
            "supported_extracted": 0,
            "supported_gt": 0,
        }
        for axis in AXES
    }
    corpus_unique_core = {
        "matched": 0,
        "extracted": 0,
        "supported_extracted": 0,
        "supported_gt": 0,
    }
    extracted_evidence: Counter[str] = Counter()
    gt_evidence: Counter[str] = Counter()
    item_totals: Counter[str] = Counter()
    papers_within_item_tolerance = 0
    for report in papers.values():
        for axis in AXES:
            for key in corpus_axes[axis]:
                corpus_axes[axis][key] += int(report["axes"][axis][key])
        for key in corpus_core:
            corpus_core[key] += int(report["core_tensile"][key])
        for axis in AXES:
            for key in corpus_unique_axes[axis]:
                corpus_unique_axes[axis][key] += int(
                    report["unique_axes"][axis][key]
                )
        for key in corpus_unique_core:
            corpus_unique_core[key] += int(report["unique_core_tensile"][key])
        extracted_evidence.update(report.get("extracted_evidence_audit", {}))
        gt_evidence.update(report.get("gt_evidence_audit", {}))
        for key in ("extracted", "gt", "supported_extracted", "supported_gt"):
            item_totals[key] += int(report["item_counts"].get(key, 0))
        papers_within_item_tolerance += bool(
            report["item_counts"].get("within_tolerance")
        )

    axis_metrics = {
        axis: _metrics(
            values["matched"],
            values["extracted"],
            values["supported_gt"],
            supported_extracted=values["supported_extracted"],
        )
        for axis, values in corpus_axes.items()
    }
    macro_axes = ("composition", "processing", "structure", "properties")
    macro_recall = (
        sum(axis_metrics[axis]["recall"] for axis in macro_axes) / len(macro_axes)
    )
    core_metrics = _metrics(
        corpus_core["matched"],
        corpus_core["extracted"],
        corpus_core["supported_gt"],
        supported_extracted=corpus_core["supported_extracted"],
    )
    unique_axis_metrics = {
        axis: _metrics(
            values["matched"],
            values["extracted"],
            values["supported_gt"],
            supported_extracted=values["supported_extracted"],
        )
        for axis, values in corpus_unique_axes.items()
    }
    unique_macro_recall = sum(
        unique_axis_metrics[axis]["recall"] for axis in macro_axes
    ) / len(macro_axes)
    unique_core_metrics = _metrics(
        corpus_unique_core["matched"],
        corpus_unique_core["extracted"],
        corpus_unique_core["supported_gt"],
        supported_extracted=corpus_unique_core["supported_extracted"],
    )
    supported_gt_items = int(item_totals["supported_gt"])
    item_delta_ratio = (
        abs(int(item_totals["supported_extracted"]) - supported_gt_items)
        / supported_gt_items
        if supported_gt_items
        else (0.0 if not item_totals["supported_extracted"] else 1.0)
    )
    return {
        "ocr_baseline_id": manifest["baseline_id"],
        "paper_count": len(papers),
        "missing": missing,
        "items": {
            **dict(item_totals),
            "papers_within_tolerance": papers_within_item_tolerance,
            "paper_target": 24,
            "corpus_delta_ratio": round(item_delta_ratio, 6),
        },
        "extracted_evidence_audit": dict(extracted_evidence),
        "gt_evidence_audit": dict(gt_evidence),
        "axes": axis_metrics,
        "core_tensile": core_metrics,
        "unique_axes": unique_axis_metrics,
        "unique_core_tensile": unique_core_metrics,
        "acceptance": {
            "all_extracted_facts_grounded": not (
                extracted_evidence["unsupported"]
                or extracted_evidence["ambiguous"]
            ),
            "core_tensile_f1_at_least_0_90": core_metrics["f1"] >= 0.90,
            "four_axis_macro_recall_at_least_0_85": macro_recall >= 0.85,
            "four_axis_macro_recall": round(macro_recall, 6),
            "unique_four_axis_macro_recall": round(unique_macro_recall, 6),
            "unique_core_tensile_f1": unique_core_metrics["f1"],
            "papers_within_item_tolerance_at_least_24": (
                papers_within_item_tolerance >= 24
            ),
            "corpus_item_delta_within_15_percent": item_delta_ratio <= 0.15,
        },
        "papers": papers,
    }


def render_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# Alpha25 source-aware GT comparison",
        "",
        f"- OCR baseline: `{report.get('ocr_baseline_id')}`",
        f"- Compared papers: {report.get('paper_count', 0)}",
        f"- Missing pairs: {len(report.get('missing', []))}",
        f"- Extracted evidence audit: `{report.get('extracted_evidence_audit', {})}`",
        f"- GT evidence audit: `{report.get('gt_evidence_audit', {})}`",
        f"- Core tensile F1: `{report.get('core_tensile', {}).get('f1', 0):.3f}`",
        f"- Four-axis macro recall: `{report.get('acceptance', {}).get('four_axis_macro_recall', 0):.3f}`",
        f"- Unique-fact core tensile F1: `{report.get('unique_core_tensile', {}).get('f1', 0):.3f}`",
        f"- Unique-fact four-axis macro recall: `{report.get('acceptance', {}).get('unique_four_axis_macro_recall', 0):.3f}`",
        f"- Item tolerance papers: `{report.get('items', {}).get('papers_within_tolerance', 0)}/30`",
        "",
        "| Axis | Matched | Extracted | Supported extracted | Supported GT | Precision | Recall | F1 |",
        "|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for axis in AXES:
        row = report["axes"][axis]
        lines.append(
            f"| {axis} | {row['matched']} | {row['extracted']} | "
            f"{row['supported_extracted']} | {row['supported_gt']} | "
            f"{row['precision']:.3f} | {row['recall']:.3f} | {row['f1']:.3f} |"
        )
    lines.extend(
        [
            "",
            "## Cross-item unique facts",
            "",
            "| Axis | Matched | Extracted | Supported GT | Precision | Recall | F1 |",
            "|---|---:|---:|---:|---:|---:|---:|",
        ]
    )
    for axis in AXES:
        row = report["unique_axes"][axis]
        lines.append(
            f"| {axis} | {row['matched']} | {row['supported_extracted']} | "
            f"{row['supported_gt']} | {row['precision']:.3f} | "
            f"{row['recall']:.3f} | {row['f1']:.3f} |"
        )
    return "\n".join(lines) + "\n"
