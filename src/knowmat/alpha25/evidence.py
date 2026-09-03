"""Strict evidence grounding for compact alpha25 facts."""

from __future__ import annotations

import os
import re
import unicodedata
from dataclasses import dataclass
from functools import lru_cache
from html import unescape
from typing import Any, Iterable, Mapping, Sequence

from knowmat.alpha25.contracts import (
    AxisResponse,
    GroundedModel,
    InventoryResponse,
    MultiAxisResponse,
)


_DASHES = str.maketrans({"−": "-", "–": "-", "—": "-", "‐": "-", "‑": "-"})
_LOCATOR = re.compile(
    r"^\s*(?:[^\n|:]{1,160}:)?L\d+(?:\s*[-–—]\s*L?\d+)?\s*(?:[:|]\s*)",
    re.IGNORECASE,
)
_LATEX_GREEK = {
    r"\alpha": "α",
    r"\beta": "β",
    r"\gamma": "γ",
    r"\delta": "δ",
    r"\epsilon": "ε",
    r"\varepsilon": "ε",
    r"\theta": "θ",
    r"\lambda": "λ",
    r"\mu": "μ",
    r"\sigma": "σ",
}

# A small subset of the OCR/LaTeX output seen in the source Markdown uses
# ``\mathring{A} \mathring{C}`` where the rendered table visibly contains
# ``Å °C``.  This is a presentation corruption, not a semantic rewrite: the
# model's copied row still carries the same owner, values, and condition.  Keep
# the rewrite explicit and narrow so arbitrary approximate/semantic evidence is
# never accepted by the literal evidence gate.
_LATEX_MATHRING = (
    (re.compile(r"\\mathring\s*\{?\s*A\s*\}?", re.IGNORECASE), "Å"),
    (re.compile(r"\\mathring\s*\{?\s*C\s*\}?", re.IGNORECASE), "°C"),
)


def structured_table_cell_recovery_v202_enabled() -> bool:
    """Return whether fail-closed logical table-cell recovery is enabled."""

    raw = os.getenv("KNOWMAT2_ALPHA25_STRUCTURED_TABLE_CELL_RECOVERY_V202", "1")
    return raw.strip().casefold() not in {
        "0",
        "false",
        "no",
        "off",
        "disabled",
    }


def normalize_evidence_text(value: str) -> str:
    """Normalize only presentation differences introduced by OCR."""

    text = unicodedata.normalize("NFKC", str(value or ""))
    text = text.replace("\u00ad", "").translate(_DASHES)
    text = text.replace("µ", "μ")
    # MinerU/PaddleOCR frequently retain LaTeX presentation in the assigned
    # source while an LLM copies the visibly equivalent rendered text. These
    # rewrites remove markup only; they preserve every symbol and numeric value.
    text = re.sub(r"\^\s*\{?\\circ\}?", "°", text)
    text = text.replace(r"\pm", "±")
    for pattern, replacement in _LATEX_MATHRING:
        text = pattern.sub(replacement, text)
    for latex, symbol in _LATEX_GREEK.items():
        text = text.replace(latex, symbol)
    # TeX subscripts are frequently preserved by MinerU/OCR in the source
    # (``Ti_{64}``, ``E_{{O}}``), while the model copies the visibly rendered
    # token (``Ti64``, ``EO``).  The underscore/braces here are presentation
    # markup, not scientific characters: remove only a syntactically explicit
    # subscript wrapper and retain every alphanumeric/symbolic payload.  Run
    # this after Greek replacement so ``\sigma_y`` and ``σ_y`` normalize alike.
    text = re.sub(
        r"(?P<base>[A-Za-z0-9α-ωΑ-Ω])\s*_\s*\{+\s*(?P<sub>[A-Za-z0-9.+\-]+)\s*\}+",
        r"\g<base>\g<sub>",
        text,
    )
    text = re.sub(
        r"(?P<base>[A-Za-z0-9α-ωΑ-Ω])\s*_\s*(?P<sub>[A-Za-z0-9])",
        r"\g<base>\g<sub>",
        text,
    )
    text = text.replace("$", "").replace("{", "").replace("}", "")
    # Renderers differ on whether a space is retained immediately inside
    # punctuation around LaTeX symbols, e.g. ``( σ_y )`` versus ``(σ_y)``.
    # Removing only these presentation spaces keeps literal words, numbers,
    # and operators unchanged while allowing a copied source quote to ground.
    text = re.sub(r"\s+([,.;:!?%\)\]\}])", r"\1", text)
    text = re.sub(r"([\(\[\{])\s+", r"\1", text)
    text = re.sub(r"(?<=\w)-\s*\n\s*(?=\w)", "", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip().casefold()


def evidence_body(value: str) -> str:
    """Strip an optional line locator while retaining the copied evidence body."""

    raw = str(value or "").strip()
    stripped = _LOCATOR.sub("", raw, count=1).strip()
    return stripped


def _evidence_is_grounded_prepared(
    evidence: str,
    source_text: str,
    *,
    normalized_source: str,
    source_blocks: Sequence[Sequence[tuple[str, ...]]] | None = None,
) -> bool:
    """Ground one quote against source values prepared once for a task."""

    needle = normalize_evidence_text(evidence_body(evidence))
    haystack = normalized_source
    if bool(needle) and needle in haystack:
        return True
    # Table extraction tasks commonly copy a header, separator, and one target
    # row while omitting intervening rows.  That representation is source
    # grounded when every copied row is present in the same source table, even
    # though the compact rendering is not one continuous substring.  Keep the
    # fallback table-only and require a single source-table block so prose
    # paraphrases and cross-table synthesis remain rejected.
    return _table_evidence_is_grounded(
        evidence_body(evidence), source_text, source_blocks=source_blocks
    )


def evidence_is_grounded(evidence: str, source_text: str) -> bool:
    """Return whether copied evidence is a normalized literal OCR substring."""

    return _evidence_is_grounded_prepared(
        evidence,
        source_text,
        normalized_source=normalize_evidence_text(source_text),
    )


def _normalize_table_cell(value: str) -> str:
    """Normalize one Markdown/HTML table cell without changing its content."""

    text = unescape(str(value or ""))
    text = re.sub(r"<[^>]+>", " ", text)
    return normalize_evidence_text(text).strip()


def _table_row_cells(row: str) -> tuple[str, ...]:
    """Return normalized cells for a pipe-delimited table row."""

    raw = str(row or "").strip()
    if "|" not in raw:
        return ()
    parts = raw.split("|")
    if raw.startswith("|"):
        parts = parts[1:]
    if raw.endswith("|"):
        parts = parts[:-1]
    return tuple(_normalize_table_cell(cell) for cell in parts)


def _is_table_separator(cells: Sequence[str]) -> bool:
    return bool(cells) and all(
        not cell or re.fullmatch(r":?-{2,}:?", cell) is not None
        for cell in cells
    )


def _markdown_table_blocks(text: str) -> list[list[tuple[str, ...]]]:
    blocks: list[list[tuple[str, ...]]] = []
    current: list[tuple[str, ...]] = []
    for line in str(text or "").splitlines():
        stripped = line.strip()
        if "|" in stripped and stripped.startswith("|") and stripped.endswith("|"):
            cells = _table_row_cells(stripped)
            if cells:
                current.append(cells)
            continue
        if current:
            blocks.append(current)
            current = []
    if current:
        blocks.append(current)
    return blocks


def _html_table_blocks(text: str) -> list[list[tuple[str, ...]]]:
    blocks: list[list[tuple[str, ...]]] = []
    for table in re.findall(r"<table\b[^>]*>.*?</table>", str(text or ""), flags=re.I | re.S):
        rows: list[tuple[str, ...]] = []
        for row in re.findall(r"<tr\b[^>]*>(.*?)</tr>", table, flags=re.I | re.S):
            cells = tuple(
                _normalize_table_cell(cell)
                for cell in re.findall(r"<t[dh]\b[^>]*>(.*?)</t[dh]>", row, flags=re.I | re.S)
            )
            if cells:
                rows.append(cells)
        if rows:
            blocks.append(rows)
    return blocks


def _table_evidence_rows(evidence: str) -> list[tuple[str, ...]]:
    rows: list[tuple[str, ...]] = []
    for line in str(evidence or "").splitlines():
        cells = _table_row_cells(line)
        if cells and not _is_table_separator(cells):
            rows.append(cells)
    # A compact one-line table row is also valid evidence.
    if not rows:
        cells = _table_row_cells(str(evidence or ""))
        if cells and not _is_table_separator(cells):
            rows.append(cells)
    return rows


def _table_evidence_is_grounded(
    evidence: str,
    source_text: str,
    *,
    source_blocks: Sequence[Sequence[tuple[str, ...]]] | None = None,
) -> bool:
    """Check compact table evidence against one Markdown/HTML source table."""

    if "|" not in str(evidence or ""):
        return False
    candidate_rows = _table_evidence_rows(evidence)
    if not candidate_rows:
        return False
    blocks = (
        list(source_blocks)
        if source_blocks is not None
        else [*_markdown_table_blocks(source_text), *_html_table_blocks(source_text)]
    )
    for block in blocks:
        source_rows = set(block)
        if all(row in source_rows for row in candidate_rows):
            return True
    return False


def _table_header_projection_is_grounded(
    evidence: str, source_text: str
) -> bool:
    """Accept a deterministic logical-table header rendered as one row.

    HTML tables with ``rowspan``/``colspan`` are routinely serialized by the
    model as a compact Markdown header (for example ``WAAM / Horizontal``),
    even though the OCR source stores ``WAAM`` and ``Horizontal`` in separate
    header cells. This verifies only the header tokens; values and all other
    fact evidence remain governed by the normal gates.
    """

    rows = _table_evidence_rows(evidence)
    if len(rows) != 1:
        return False
    cells = tuple(cell for cell in rows[0] if cell)
    if len(cells) < 2:
        return False
    if any(
        re.fullmatch(r"[<>≤≥~≈+\-−–—]?\s*\d+(?:\.\d+)?", cell)
        for cell in cells
    ):
        return False
    try:
        # Local import avoids the evidence <-> source_coordinates import cycle.
        from knowmat.alpha25.source_coordinates import logical_tables
    except Exception:
        return False
    for table in logical_tables(source_text):
        header_tokens: set[str] = set()
        header_paths: set[str] = set()
        for column in range(len(table.rows[0]) if table.rows else 0):
            path = tuple(value for value in table.header_path(column) if value)
            header_paths.add(normalize_evidence_text(" / ".join(path)))
            header_tokens.update(normalize_evidence_text(value) for value in path)
        if not header_tokens:
            continue
        matched = 0
        for cell in cells:
            normalized = normalize_evidence_text(cell)
            if normalized in header_tokens or normalized in header_paths:
                matched += 1
                continue
            pieces = tuple(
                normalize_evidence_text(piece)
                for piece in re.split(r"\s*/\s*", cell)
                if normalize_evidence_text(piece)
            )
            if len(pieces) >= 2 and all(piece in header_tokens for piece in pieces):
                matched += 1
        if matched == len(cells):
            return True
    return False


@dataclass(frozen=True)
class EvidenceIssue:
    code: str
    evidence_unit_id: str
    fact_index: int
    evidence_index: int
    evidence: str
    message: str
    severity: str = "review"
    expected: Any = None
    actual: Any = None
    suggested_action: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "severity": self.severity,
            "path": (
                f"evidence_gate.{self.evidence_unit_id}."
                f"facts[{self.fact_index}].source_evidence[{self.evidence_index}]"
            ),
            "evidence_unit_id": self.evidence_unit_id,
            "fact_index": self.fact_index,
            "evidence_index": self.evidence_index,
            "evidence": self.evidence,
            "message": self.message,
            "expected": self.expected,
            "actual": self.actual,
            "suggested_action": self.suggested_action,
        }


@dataclass(frozen=True)
class EvidenceGateResult:
    accepted: list[GroundedModel]
    rejected: list[GroundedModel]
    issues: list[EvidenceIssue]
    audit_issues: list[EvidenceIssue]

    @property
    def complete(self) -> bool:
        return not self.rejected


@dataclass(frozen=True)
class TableProjectionDecision:
    """One source-only decision for a cropped table evidence row."""

    status: str
    evidence_cells: tuple[str, ...] = ()
    source_cells: tuple[str, ...] = ()
    source_row: str = ""
    block_index: int | None = None
    row_index: int | None = None
    distinct_match_count: int = 0
    reason: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "evidence_cells": list(self.evidence_cells),
            "source_cells": list(self.source_cells),
            "source_row": self.source_row,
            "block_index": self.block_index,
            "row_index": self.row_index,
            "distinct_match_count": self.distinct_match_count,
            "reason": self.reason,
        }


@dataclass(frozen=True)
class ProseEllipsisDecision:
    """One unique literal source sentence completing explicit ellipsis evidence."""

    status: str
    fragments: tuple[str, ...] = ()
    source_sentence: str = ""
    distinct_match_count: int = 0
    reason: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "fragments": list(self.fragments),
            "source_sentence": self.source_sentence,
            "distinct_match_count": self.distinct_match_count,
            "reason": self.reason,
        }


_PROSE_ELLIPSIS = re.compile(r"(?:\.{3,}|…)")
_CORE_TENSILE_PROPERTY = re.compile(
    r"(?ix)\b(?:yield\s+(?:strength|stress)|"
    r"(?:ultimate\s+)?tensile\s+(?:strength|stress)|uts|"
    r"elongation|ductility)\b|[σε]"
)


def _source_prose_sentences(source_text: str) -> list[str]:
    """Return complete non-table prose sentences without semantic rewriting."""

    rows: list[str] = []
    for paragraph in re.split(r"\n\s*\n", str(source_text or "")):
        stripped = paragraph.strip()
        if not stripped or stripped.startswith("|") or "<table" in stripped.casefold():
            continue
        rows.extend(
            sentence.strip()
            for sentence in re.split(r"(?<=[.!?])\s+(?=[A-Z0-9$\\σε])", stripped)
            if sentence.strip()
        )
    return rows


def unique_ordered_prose_ellipsis_completion(
    evidence: str, source_text: str
) -> ProseEllipsisDecision:
    """Complete one explicit ellipsis only when one source sentence matches.

    The candidate fragments must occur literally, in order, in the same source
    sentence.  This is not fuzzy matching and does not infer omitted words.
    """

    raw = evidence_body(evidence)
    markers = list(_PROSE_ELLIPSIS.finditer(raw))
    if len(markers) != 1 or "|" in raw:
        return ProseEllipsisDecision(
            status="not_applicable",
            reason="evidence must contain exactly one prose ellipsis",
        )
    fragments = tuple(
        normalize_evidence_text(part).strip()
        for part in _PROSE_ELLIPSIS.split(raw)
        if normalize_evidence_text(part).strip()
    )
    if len(fragments) != 2 or any(len(fragment) < 6 for fragment in fragments):
        return ProseEllipsisDecision(
            status="too_weak",
            fragments=fragments,
            reason="both ordered literal fragments must be non-trivial",
        )

    matches: dict[str, str] = {}
    for sentence in _source_prose_sentences(source_text):
        normalized = normalize_evidence_text(sentence)
        position = 0
        matched = True
        for fragment in fragments:
            found = normalized.find(fragment, position)
            if found < 0:
                matched = False
                break
            position = found + len(fragment)
        if matched:
            matches.setdefault(normalized, sentence)
    if not matches:
        return ProseEllipsisDecision(
            status="not_found",
            fragments=fragments,
            reason="ordered fragments do not occur in one source sentence",
        )
    if len(matches) != 1:
        return ProseEllipsisDecision(
            status="ambiguous",
            fragments=fragments,
            distinct_match_count=len(matches),
            reason="ordered fragments match more than one source sentence",
        )
    sentence = next(iter(matches.values()))
    return ProseEllipsisDecision(
        status="matched",
        fragments=fragments,
        source_sentence=sentence,
        distinct_match_count=1,
        reason="one source sentence contains both literal fragments in order",
    )


def _prose_ellipsis_supports_record(
    record: GroundedModel, decision: ProseEllipsisDecision
) -> bool:
    """Require one direct core-tensile value/unit in the completed sentence."""

    if decision.status != "matched" or not decision.source_sentence:
        return False
    payload = record.model_dump()
    if payload.get("fact_type") != "property":
        return False
    data = payload.get("data")
    if not isinstance(data, Mapping):
        return False
    property_name = str(data.get("property_name_raw") or "")
    if not _CORE_TENSILE_PROPERTY.search(property_name):
        return False
    sentence = normalize_evidence_text(decision.source_sentence)
    values = _record_value_coordinates(payload)
    if not values or not all(
        _literal_coordinate_present(value, (sentence,)) for value in values
    ):
        return False
    unit = str(data.get("unit_raw") or "").strip()
    if not unit or not _literal_coordinate_present(unit, (sentence,)):
        return False
    semantic_support = normalize_evidence_text(
        " ".join([*decision.fragments, decision.source_sentence])
    )
    if re.search(r"(?i)yield", property_name):
        family = re.search(r"(?i)yield|[σ]_*0[._]?2|[σ]_*y", semantic_support)
    elif re.search(r"(?i)elongation|ductility", property_name):
        family = re.search(r"(?i)elongation|ductility|[ε]", semantic_support)
    else:
        family = re.search(
            r"(?i)ultimate\s+tensile|tensile\s+(?:strength|stress)|\buts\b|[σ]_*u",
            semantic_support,
        )
    return family is not None


def _replace_record_source_evidence(
    record: GroundedModel, replacements: Mapping[str, str]
) -> GroundedModel:
    """Replace only exact evidence-list entries in one validated record."""

    def visit(value: Any) -> Any:
        if isinstance(value, Mapping):
            return {
                key: (
                    [replacements.get(str(row), str(row)) for row in child]
                    if key == "source_evidence"
                    and isinstance(child, Sequence)
                    and not isinstance(child, (str, bytes))
                    else replacements.get(str(child), str(child))
                    if key == "source_evidence" and isinstance(child, str)
                    else visit(child)
                )
                for key, child in value.items()
            }
        if isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
            return [visit(child) for child in value]
        return value

    return record.__class__.model_validate(visit(record.model_dump()))


@dataclass(frozen=True)
class _SourceTableRow:
    block_index: int
    row_index: int
    raw: str
    cells: tuple[str, ...]
    is_header: bool = False


def _source_table_rows(source_text: str) -> list[_SourceTableRow]:
    """Return literal Markdown/HTML rows with stable source coordinates."""

    rows: list[_SourceTableRow] = []
    markdown_blocks: list[list[tuple[str, tuple[str, ...], bool]]] = []
    current: list[tuple[str, tuple[str, ...], bool]] = []
    for raw_line in str(source_text or "").splitlines():
        stripped = raw_line.strip()
        cells = _table_row_cells(stripped)
        if (
            cells
            and stripped.startswith("|")
            and stripped.endswith("|")
        ):
            current.append((stripped, cells, _is_table_separator(cells)))
            continue
        if current:
            markdown_blocks.append(current)
            current = []
    if current:
        markdown_blocks.append(current)

    for block_index, block in enumerate(markdown_blocks):
        separator_positions = {
            position for position, (_, _, separator) in enumerate(block) if separator
        }
        header_positions = {position - 1 for position in separator_positions if position > 0}
        for row_index, (raw, cells, separator) in enumerate(block):
            if separator:
                continue
            rows.append(
                _SourceTableRow(
                    block_index=block_index,
                    row_index=row_index,
                    raw=raw,
                    cells=cells,
                    is_header=row_index in header_positions,
                )
            )

    html_offset = len(markdown_blocks)
    for html_index, table_match in enumerate(
        re.finditer(r"<table\b[^>]*>.*?</table>", str(source_text or ""), flags=re.I | re.S)
    ):
        table = table_match.group(0)
        for row_index, row_match in enumerate(
            re.finditer(r"<tr\b[^>]*>.*?</tr>", table, flags=re.I | re.S)
        ):
            raw = row_match.group(0)
            cells = tuple(
                _normalize_table_cell(match.group(2))
                for match in re.finditer(
                    r"<(t[dh])\b[^>]*>(.*?)</t[dh]>",
                    raw,
                    flags=re.I | re.S,
                )
            )
            if not cells:
                continue
            rows.append(
                _SourceTableRow(
                    block_index=html_offset + html_index,
                    row_index=row_index,
                    raw=raw,
                    cells=cells,
                    is_header=bool(re.search(r"<th\b", raw, flags=re.I)),
                )
            )
    return rows


def _ordered_cell_projection(
    evidence_cells: Sequence[str], source_cells: Sequence[str]
) -> bool:
    """Return whether every non-empty evidence cell occurs in source order."""

    position = 0
    for evidence_cell in evidence_cells:
        if not evidence_cell:
            continue
        while position < len(source_cells) and source_cells[position] != evidence_cell:
            position += 1
        if position >= len(source_cells):
            return False
        position += 1
    return True


def unique_ordered_table_row_projection(
    evidence: str, source_text: str
) -> TableProjectionDecision:
    """Prove that one cropped evidence row identifies one distinct source row.

    This deliberately performs exact normalized cell comparison only.  It is
    not a fuzzy table matcher and never selects a row by position.
    """

    evidence_rows = _table_evidence_rows(evidence_body(evidence))
    if len(evidence_rows) != 1:
        return TableProjectionDecision(
            status="not_applicable",
            reason="evidence must contain exactly one non-separator table row",
        )
    evidence_cells = tuple(cell for cell in evidence_rows[0] if cell)
    if len(evidence_cells) < 3:
        return TableProjectionDecision(
            status="too_few_cells",
            evidence_cells=evidence_cells,
            reason="an ordered projection requires at least three non-empty cells",
        )

    matches = [
        row
        for row in _source_table_rows(source_text)
        if not row.is_header
        and _ordered_cell_projection(evidence_cells, row.cells)
    ]
    # Repeated literal copies of one normalized row are one distinct source
    # row; different rows that collapse to the same projection stay ambiguous.
    distinct: dict[tuple[str, ...], _SourceTableRow] = {}
    for row in matches:
        distinct.setdefault(row.cells, row)
    if not distinct:
        return TableProjectionDecision(
            status="not_found",
            evidence_cells=evidence_cells,
            reason="the ordered cells do not occur in one original table row",
        )
    if len(distinct) != 1:
        return TableProjectionDecision(
            status="ambiguous",
            evidence_cells=evidence_cells,
            distinct_match_count=len(distinct),
            reason="the ordered cells match more than one distinct original row",
        )
    matched = next(iter(distinct.values()))
    return TableProjectionDecision(
        status="matched",
        evidence_cells=evidence_cells,
        source_cells=matched.cells,
        source_row=matched.raw,
        block_index=matched.block_index,
        row_index=matched.row_index,
        distinct_match_count=1,
        reason="one distinct original row contains all evidence cells in order",
    )


def _literal_coordinate_present(value: Any, cells: Sequence[str]) -> bool:
    presentation = normalize_evidence_text(str(value or ""))
    if not presentation:
        return False
    for cell in cells:
        if presentation == cell:
            return True
        if len(presentation) >= 8 and presentation in cell:
            return True
        if re.search(
            rf"(?<![a-z0-9]){re.escape(presentation)}(?![a-z0-9])",
            cell,
        ):
            return True
    return False


def _record_value_coordinates(value: Any) -> list[str]:
    coordinates: list[str] = []
    if isinstance(value, Mapping):
        for key, child in value.items():
            folded = str(key).casefold()
            if folded == "source_evidence":
                continue
            if folded.endswith("value_raw") or folded in {
                "amount_raw",
                "amount_value",
                "fraction_value_raw",
            }:
                if child not in (None, "", [], {}):
                    coordinates.append(str(child).strip())
                continue
            coordinates.extend(_record_value_coordinates(child))
    elif isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        for child in value:
            coordinates.extend(_record_value_coordinates(child))
    return list(dict.fromkeys(row for row in coordinates if row))


@dataclass(frozen=True)
class FullSourceRecoveryCorpus:
    """Normalized full-paper text plus deterministic planner projections.

    Task prompts are intentionally bounded, so a quote copied from a table can
    be serialized as ``header: value`` even when that exact string is not in
    the original OCR.  The planner projection is source-derived and therefore
    safe to consult during the *recovery* pass, provided the candidate still
    has an explicit owner in the complete paper.
    """

    source: str
    projected: tuple[str, ...]
    compact_source: str
    compact_projected: tuple[str, ...]


def _compact_recovery_evidence(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", str(value or "").casefold())


@lru_cache(maxsize=8)
def _build_full_source_recovery_corpus_cached(
    source_text: str,
) -> FullSourceRecoveryCorpus:
    """Build the same bounded source projections used by Alpha25 planning.

    Keep this lazy and cached: the online extractor may inspect several
    rejected records from the same paper, and rebuilding all table projections
    for every record would make the recovery safety net unnecessarily slow.
    """

    source = str(source_text or "")
    projected: list[str] = []
    try:
        # Import lazily to avoid the planner -> materialize -> evidence import
        # cycle during module initialization.
        from knowmat.alpha25.planner import build_evidence_units

        prose_chars = int(os.getenv("KNOWMAT2_ALPHA25_PROSE_CHARS", "8000"))
        table_columns = int(os.getenv("KNOWMAT2_ALPHA25_TABLE_COLUMNS", "4"))
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
    return FullSourceRecoveryCorpus(
        source=normalized_source,
        projected=tuple(projected),
        compact_source=_compact_recovery_evidence(normalized_source),
        compact_projected=tuple(_compact_recovery_evidence(value) for value in projected),
    )


def _full_source_recovery_status(
    evidence: str,
    corpus: FullSourceRecoveryCorpus,
    *,
    allow_composite: bool = True,
) -> str:
    """Classify a quote using literal text and deterministic source views only."""

    needle = normalize_evidence_text(evidence_body(evidence))
    if not needle:
        return "unsupported"
    if needle in corpus.source:
        return "supported"
    if any(needle in value for value in corpus.projected):
        return "format_mismatch"
    compact = _compact_recovery_evidence(needle)
    if len(compact) >= 12 and (
        compact in corpus.compact_source
        or any(compact in value for value in corpus.compact_projected)
    ):
        return "format_mismatch"
    if allow_composite and " | " in needle:
        parts = [
            part.strip(" | ").strip()
            for part in dict.fromkeys(needle.split(" | "))
            if part.strip(" | ").strip()
        ]
        if len(parts) >= 2 and all(
            _full_source_recovery_status(part, corpus, allow_composite=False)
            in {"supported", "format_mismatch"}
            for part in parts
        ):
            return "format_mismatch"
    return "unsupported"


def _projection_contains_record_coordinates(
    record: GroundedModel, corpus: FullSourceRecoveryCorpus
) -> bool:
    """Require owner and scalar coordinates to co-occur in one source view."""

    payload = record.model_dump()
    owner = str(payload.get("sample_id_raw") or "").strip()
    if not owner:
        return False
    coordinates = _record_value_coordinates(payload)
    for projection in corpus.projected:
        # Prose planner units can contain several sentences.  Do not use the
        # whole paragraph as an owner/value join key: require co-occurrence in
        # one sentence for prose, while retaining the full-view check for
        # deterministic table/HTML projections.
        views = (
            re.split(r"(?<=[.!?])\s+", projection)
            if "|" not in projection and "<table" not in projection
            else (projection,)
        )
        for view in views:
            cells = (view,)
            owner_compact = _compact_recovery_evidence(owner)
            view_compact = _compact_recovery_evidence(view)
            owner_present = bool(owner_compact) and owner_compact in view_compact
            if owner_present and all(
                _literal_coordinate_present(value, cells) for value in coordinates
            ):
                return True
    return False


def _projection_table_context(
    decision: TableProjectionDecision, source_text: str
) -> str:
    """Return one matched table plus only its immediately preceding caption."""

    if decision.status != "matched" or not decision.source_row or not source_text:
        return ""
    row_position = source_text.find(decision.source_row)
    if row_position < 0:
        return ""
    html_start = source_text.rfind("<table", 0, row_position)
    html_end = source_text.find("</table>", row_position)
    if html_start >= 0 and html_end >= row_position:
        return source_text[max(0, html_start - 800) : html_end + len("</table>")]

    line_start = source_text.rfind("\n", 0, row_position) + 1
    block_start = line_start
    while block_start > 0:
        previous_end = block_start - 1
        previous_start = source_text.rfind("\n", 0, previous_end) + 1
        previous = source_text[previous_start:previous_end].strip()
        if not (previous.startswith("|") and previous.endswith("|")):
            break
        block_start = previous_start
    block_end = source_text.find("\n", row_position)
    block_end = len(source_text) if block_end < 0 else block_end
    while block_end < len(source_text):
        next_start = block_end + 1
        next_end = source_text.find("\n", next_start)
        next_end = len(source_text) if next_end < 0 else next_end
        following = source_text[next_start:next_end].strip()
        if not (following.startswith("|") and following.endswith("|")):
            break
        block_end = next_end
    return source_text[max(0, block_start - 800) : block_end]


def table_projection_supports_record(
    record: GroundedModel | Mapping[str, Any],
    decision: TableProjectionDecision,
    *,
    source_text: str = "",
) -> bool:
    """Require the candidate semantic coordinates in the projected evidence.

    Ordered row projection can restore columns omitted from a cropped table
    citation, but it must not manufacture the semantic kind of a fact.  In
    particular, a row containing only a sample id and numeric process
    parameters does not prove that the row itself is an LPBF (or any other)
    process stage.
    """

    if decision.status != "matched":
        return False
    payload = record.model_dump() if hasattr(record, "model_dump") else dict(record)
    owner = payload.get("sample_id_raw")
    if not owner or not _literal_coordinate_present(owner, decision.evidence_cells):
        return False
    if payload.get("fact_type") == "process_stage":
        data = payload.get("data")
        if not isinstance(data, Mapping):
            return False
        process_coordinates = [
            data.get("process_name_raw"),
            data.get("process_code_candidate"),
        ]
        evidence_names_process = any(
            coordinate
            and _literal_coordinate_present(coordinate, decision.evidence_cells)
            for coordinate in process_coordinates
        )
        if not evidence_names_process:
            table_context = _projection_table_context(decision, source_text)
            context_cells = (
                (normalize_evidence_text(table_context),) if table_context else ()
            )
            parameters = data.get("parameters_raw")
            parameter_names = [
                row.get("parameter_name_raw")
                for row in parameters or []
                if isinstance(row, Mapping)
                and str(row.get("parameter_name_raw") or "").strip()
            ]
            context_names_process = any(
                coordinate
                and _literal_coordinate_present(coordinate, context_cells)
                for coordinate in process_coordinates
            )
            context_names_parameters = bool(parameter_names) and all(
                _literal_coordinate_present(name, context_cells)
                for name in parameter_names
            )
            if not (context_names_process and context_names_parameters):
                return False
    values = _record_value_coordinates(payload)
    return all(
        _literal_coordinate_present(value, decision.evidence_cells)
        for value in values
    )


def gate_grounded_records(
    records: Sequence[GroundedModel],
    *,
    evidence_unit_id: str,
    evidence_text: str,
    shared_context: str = "",
    structured_source_text: str = "",
) -> EvidenceGateResult:
    """Accept a fact only when every evidence entry exists in assigned source text."""

    source = "\n\n".join(part for part in (evidence_text, shared_context) if part)
    structured_source = structured_source_text or source
    normalized_source = normalize_evidence_text(source)
    source_blocks = [*_markdown_table_blocks(source), *_html_table_blocks(source)]
    accepted: list[GroundedModel] = []
    rejected: list[GroundedModel] = []
    issues: list[EvidenceIssue] = []
    audit_issues: list[EvidenceIssue] = []
    for fact_index, record in enumerate(records):
        record_issues: list[EvidenceIssue] = []
        recovery_decisions: list[tuple[int, str, TableProjectionDecision]] = []
        prose_recovery_decisions: list[
            tuple[int, str, ProseEllipsisDecision]
        ] = []
        structured_recovery_decisions: list[tuple[int, str, Any]] = []
        structured_decision: Any = None
        evidence_rows = _all_source_evidence(record.model_dump())
        for evidence_index, evidence in enumerate(evidence_rows):
            if _evidence_is_grounded_prepared(
                evidence,
                source,
                normalized_source=normalized_source,
                source_blocks=source_blocks,
            ):
                continue
            prose_completion = unique_ordered_prose_ellipsis_completion(
                evidence, source
            )
            if _prose_ellipsis_supports_record(record, prose_completion):
                prose_recovery_decisions.append(
                    (evidence_index, evidence, prose_completion)
                )
                continue
            projection = unique_ordered_table_row_projection(evidence, source)
            if table_projection_supports_record(
                record, projection, source_text=source
            ):
                recovery_decisions.append((evidence_index, evidence, projection))
                continue
            if structured_table_cell_recovery_v202_enabled():
                if structured_decision is None:
                    # Keep the dependency local: source_coordinates reuses the
                    # literal normalization helpers in this module.
                    from knowmat.alpha25.source_coordinates import (
                        resolve_structured_table_record,
                    )

                    structured_decision = resolve_structured_table_record(
                        record, structured_source
                    )
                if structured_decision.status == "matched":
                    structured_recovery_decisions.append(
                        (evidence_index, evidence, structured_decision)
                    )
                    continue
            if projection.status == "ambiguous":
                code = "evidence_projection_ambiguous_quarantined"
                message = (
                    "Cropped table evidence matches more than one distinct original "
                    "row and cannot be assigned deterministically."
                )
            elif (
                structured_decision is not None
                and structured_decision.status == "ambiguous"
            ):
                code = "evidence_structured_table_cell_ambiguous"
                message = (
                    "The complete owner/property/unit/value relation resolves to "
                    "more than one structured table cell."
                )
            else:
                code = "ungrounded_source_evidence"
                message = (
                    "Evidence is not a literal OCR substring or a unique ordered "
                    "table-row projection of the assigned task source."
                )
            record_issues.append(
                EvidenceIssue(
                    code=code,
                    evidence_unit_id=evidence_unit_id,
                    fact_index=fact_index,
                    evidence_index=evidence_index,
                    evidence=evidence,
                    message=message,
                    expected={
                        "literal_source_match": True,
                        "or_unique_ordered_table_projection": True,
                        "owner_and_values_in_projection": True,
                    },
                    actual={
                        "record": record.model_dump(),
                        "projection": projection.to_dict(),
                        **(
                            {"structured_coordinate": structured_decision.to_dict()}
                            if structured_decision is not None
                            else {}
                        ),
                    },
                    suggested_action=(
                        "Review the preserved source row; restore only after one "
                        "owner/value coordinate is uniquely provable."
                    ),
                )
            )
        if record_issues:
            rejected.append(record)
            issues.extend(record_issues)
        else:
            accepted_record = (
                _replace_record_source_evidence(
                    record,
                    {
                        evidence: decision.source_sentence
                        for _, evidence, decision in prose_recovery_decisions
                    },
                )
                if prose_recovery_decisions
                else record
            )
            accepted.append(accepted_record)
            for evidence_index, evidence, decision in prose_recovery_decisions:
                audit_issues.append(
                    EvidenceIssue(
                        code="evidence_unique_prose_ellipsis_recovered",
                        severity="info",
                        evidence_unit_id=evidence_unit_id,
                        fact_index=fact_index,
                        evidence_index=evidence_index,
                        evidence=evidence,
                        message=(
                            "Explicit ellipsis evidence was replaced by the one "
                            "complete source sentence containing both literal "
                            "fragments in order."
                        ),
                        expected={
                            "explicit_ellipsis_count": 1,
                            "ordered_literal_fragments": True,
                            "distinct_source_sentence_count": 1,
                            "direct_core_tensile_value_unit": True,
                        },
                        actual={
                            "before_evidence": evidence,
                            "after_evidence": decision.source_sentence,
                            "before_record": record.model_dump(),
                            "after_record": accepted_record.model_dump(),
                            "decision": decision.to_dict(),
                        },
                        suggested_action=(
                            "No action is required unless the complete source "
                            "sentence is itself OCR-corrupted."
                        ),
                    )
                )
            for evidence_index, evidence, projection in recovery_decisions:
                audit_issues.append(
                    EvidenceIssue(
                        code="evidence_unique_ordered_projection_recovered",
                        severity="info",
                        evidence_unit_id=evidence_unit_id,
                        fact_index=fact_index,
                        evidence_index=evidence_index,
                        evidence=evidence,
                        message=(
                            "A cropped table evidence row was accepted because its "
                            "ordered cells identify one distinct original row."
                        ),
                        expected={
                            "minimum_nonempty_cells": 3,
                            "ordered_exact_cells": True,
                            "distinct_source_row_count": 1,
                            "owner_and_values_in_projection": True,
                        },
                        actual={
                            "record": record.model_dump(),
                            "projection": projection.to_dict(),
                        },
                        suggested_action=(
                            "No action is required unless the original table row "
                            "is itself OCR-corrupted."
                        ),
                    )
                )
            for evidence_index, evidence, decision in structured_recovery_decisions:
                audit_issues.append(
                    EvidenceIssue(
                        code="evidence_structured_table_cell_recovered",
                        severity="info",
                        evidence_unit_id=evidence_unit_id,
                        fact_index=fact_index,
                        evidence_index=evidence_index,
                        evidence=evidence,
                        message=(
                            "A synthetic multi-level table header was accepted "
                            "because one logical source cell proves the candidate."
                        ),
                        expected={
                            "table_block_count": 1,
                            "owner_coordinate_count": 1,
                            "property_unit_value_coordinate_count": 1,
                            "cross_cell_projection": False,
                        },
                        actual={
                            "record": record.model_dump(),
                            "coordinate": decision.to_dict(),
                        },
                        suggested_action=(
                            "No action is required unless the source table spans "
                            "are themselves OCR-corrupted."
                        ),
                    )
                )
    return EvidenceGateResult(
        accepted=accepted,
        rejected=rejected,
        issues=issues,
        audit_issues=audit_issues,
    )


def _all_source_evidence(value: Any) -> list[str]:
    rows: list[str] = []
    if isinstance(value, Mapping):
        for key, child in value.items():
            if key == "source_evidence":
                if isinstance(child, str):
                    child = [child]
                if isinstance(child, Sequence) and not isinstance(child, (str, bytes)):
                    rows.extend(str(row).strip() for row in child if str(row).strip())
            else:
                rows.extend(_all_source_evidence(child))
    elif isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        for child in value:
            rows.extend(_all_source_evidence(child))
    return list(dict.fromkeys(rows))


def gate_task_response(
    response: InventoryResponse | AxisResponse | MultiAxisResponse,
    *,
    evidence_unit_id: str,
    evidence_text: str,
    shared_context: str = "",
    structured_source_text: str = "",
) -> EvidenceGateResult:
    records: Sequence[GroundedModel]
    if isinstance(response, InventoryResponse):
        records = response.anchors
    elif isinstance(response, MultiAxisResponse):
        records = [*response.anchors, *response.facts]
    else:
        records = response.facts
    return gate_grounded_records(
        records,
        evidence_unit_id=evidence_unit_id,
        evidence_text=evidence_text,
        shared_context=shared_context,
        structured_source_text=structured_source_text,
    )


def recover_format_mismatch_records(
    records: Sequence[GroundedModel],
    source_text: str,
    *,
    corpus: FullSourceRecoveryCorpus | None = None,
) -> tuple[list[GroundedModel], list[EvidenceIssue]]:
    """Recover literal full-paper facts rejected only by task formatting.

    A bounded task may render a table row or prose ellipsis differently from
    the full OCR source.  Recover only when every evidence row is either a
    literal source match or a deterministic table/prose projection and the
    candidate's owner is explicitly present in the full source.  Semantic
    paraphrases, ownerless records, and unsupported rows remain rejected.
    """

    source = str(source_text or "")
    recovery_corpus = corpus or _build_full_source_recovery_corpus_cached(source)
    normalized_source = recovery_corpus.source
    compact_source = recovery_corpus.compact_source
    recovered: list[GroundedModel] = []
    audits: list[EvidenceIssue] = []
    for index, record in enumerate(records):
        payload = record.model_dump()
        owner = normalize_evidence_text(payload.get("sample_id_raw"))
        if not owner:
            continue
        owner_compact = re.sub(r"[^a-z0-9]+", "", owner)
        owner_present = (
            re.search(rf"(?<![a-z0-9]){re.escape(owner)}(?![a-z0-9])", normalized_source)
            is not None
            if len(owner_compact) < 8
            else owner_compact in compact_source
        )
        if not owner_present:
            continue
        rows = _all_source_evidence(payload)
        if not rows:
            continue
        row_modes: list[str] = []
        recoverable = True
        for row in rows:
            if evidence_is_grounded(row, source):
                row_modes.append("supported")
                continue
            # The planner's bounded table/prose serialization is deterministic
            # but may not be a contiguous substring of the complete OCR.  This
            # is the recovery path that previously lived only in the offline
            # evaluator (r247); keep it source-only and fail closed.
            source_status = _full_source_recovery_status(row, recovery_corpus)
            if source_status == "format_mismatch":
                normalized_row = normalize_evidence_text(evidence_body(row))
                # A pipe-delimited *table* projection is already checked by
                # the exact ordered-row path below.  For non-table composites
                # (``claim A | claim B``), require owner/value co-occurrence in
                # one deterministic source view so unrelated sentences cannot
                # be joined into a new fact.
                non_table_composite = (
                    " | " in normalized_row
                    and not normalized_row.lstrip().startswith("|")
                )
                if not non_table_composite or _projection_contains_record_coordinates(
                    record, recovery_corpus
                ):
                    row_modes.append("format_mismatch")
                    continue
            prose = unique_ordered_prose_ellipsis_completion(row, source)
            if _prose_ellipsis_supports_record(record, prose):
                row_modes.append("format_mismatch")
                continue
            projection = unique_ordered_table_row_projection(row, source)
            if table_projection_supports_record(record, projection, source_text=source):
                row_modes.append("format_mismatch")
                continue
            recoverable = False
            break
        if not recoverable or "format_mismatch" not in row_modes:
            continue
        recovered.append(record)
        audits.append(
            EvidenceIssue(
                code="evidence_format_mismatch_recovered",
                severity="info",
                evidence_unit_id="full-paper-recovery",
                fact_index=index,
                evidence_index=-1,
                evidence="\n".join(rows),
                message=(
                    "A task-local formatting mismatch was recovered because the "
                    "full paper contains deterministic literal evidence and the "
                    "record owner is explicitly present."
                ),
                expected={
                    "deterministic_full_source_support": True,
                    "explicit_source_owner": True,
                    "unsupported_semantic_paraphrase": False,
                },
                actual={"record": payload, "row_modes": row_modes},
                suggested_action=(
                    "No action is required unless the full-paper OCR source is corrupted."
                ),
            )
        )
    return recovered, audits


def render_table_evidence(
    headers: Sequence[str],
    row: Sequence[str],
    *,
    caption: str = "",
    footnotes: Iterable[str] = (),
) -> str:
    """Render a deterministic OCR-derived table record for model evidence copying."""

    pairs = [
        f"{str(header).strip()}: {str(value).strip()}"
        for header, value in zip(headers, row)
        if str(header).strip() or str(value).strip()
    ]
    parts = [str(caption).strip(), " | ".join(pairs)]
    parts.extend(str(note).strip() for note in footnotes)
    return " | ".join(part for part in parts if part)


def evidence_units_source(
    unit_ids: Iterable[str], units: Mapping[str, str]
) -> str:
    """Join only explicitly assigned evidence units."""

    return "\n\n".join(units[unit_id] for unit_id in unit_ids if unit_id in units)
