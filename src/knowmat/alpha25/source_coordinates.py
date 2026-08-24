"""Deterministic source coordinates for structured Alpha25 evidence.

The helpers in this module are deliberately source-only.  They expand table
presentation spans into a logical grid, but they never infer a scientific
value, owner, unit, or property that is absent from the candidate and source.
"""

from __future__ import annotations

import csv
import hashlib
import json
import re
from dataclasses import dataclass, field
from html import unescape
from pathlib import Path
from typing import Any, Mapping, Sequence

from knowmat.alpha25.evidence import evidence_body, normalize_evidence_text


_TABLE = re.compile(r"<table\b[^>]*>.*?</table>", re.I | re.S)
_ROW = re.compile(r"<tr\b[^>]*>.*?</tr>", re.I | re.S)
_CELL = re.compile(r"<(t[dh])\b([^>]*)>(.*?)</t[dh]>", re.I | re.S)
_SPAN = re.compile(r"\b(rowspan|colspan)\s*=\s*['\"]?\s*(\d+)", re.I)
_TAG = re.compile(r"<[^>]+>")
_NUMBER = re.compile(r"^[~≈<>≤≥+\-−–—]?\s*\d")
_CSV_REFERENCE = re.compile(r"^\s*data_csv:\s*(\S+)\s*$", re.I | re.M)
_EXACT_NUMBER = re.compile(
    r"^[+\-−–—]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+\-]?\d+)?$"
)
_DENSE_NUMBER = r"[+\-−]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+\-]?\d+)?"
_DENSE_NUMERIC_CELL = re.compile(
    rf"^(?:[~≈<>≤≥]\s*)?{_DENSE_NUMBER}(?:\s*(?:±|\+/-)\s*"
    rf"{_DENSE_NUMBER}|\s*(?:[-–—]|to)\s*{_DENSE_NUMBER})?$",
    re.I,
)
_DENSE_REFERENCE_OWNER = re.compile(
    r"(?ix)(?:"
    r"\[[0-9,;\s-]+\]"
    r"|\b(?:reference|literature|specification|minimum)\b"
    r"|\b(?:AMS|ASTM|ISO|DIN|EN|JIS|GB/T|BS)\s*[-_/.:()]*\s*"
    r"(?=[A-Z-]*\d)[A-Z0-9./:()_-]+"
    r")"
)


@dataclass(frozen=True)
class LogicalCell:
    """One literal source cell, possibly occupying several logical slots."""

    text: str
    raw_text: str
    origin: tuple[int, int]
    row_span: int = 1
    column_span: int = 1
    is_header: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "text": self.text,
            "raw_text": self.raw_text,
            "source_row": self.origin[0],
            "source_cell": self.origin[1],
            "row_span": self.row_span,
            "column_span": self.column_span,
            "is_header": self.is_header,
        }


@dataclass(frozen=True)
class LogicalTable:
    """One Markdown or HTML table expanded to a rectangular logical grid."""

    block_index: int
    kind: str
    raw: str
    raw_rows: tuple[str, ...]
    rows: tuple[tuple[LogicalCell | None, ...], ...]
    header_row_count: int

    def header_path(self, column: int) -> tuple[str, ...]:
        path: list[str] = []
        seen_origins: set[tuple[int, int]] = set()
        for row in self.rows[: self.header_row_count]:
            if column >= len(row):
                continue
            cell = row[column]
            if cell is None or cell.origin in seen_origins or not cell.text:
                continue
            seen_origins.add(cell.origin)
            path.append(cell.text)
        return tuple(path)

    def row_cells(self, row_index: int) -> tuple[LogicalCell, ...]:
        if row_index < 0 or row_index >= len(self.rows):
            return ()
        cells: list[LogicalCell] = []
        seen: set[tuple[int, int]] = set()
        for cell in self.rows[row_index]:
            if cell is None or cell.origin in seen:
                continue
            seen.add(cell.origin)
            cells.append(cell)
        return tuple(cells)


@dataclass(frozen=True)
class SourceCoordinateDecision:
    """Fail-closed decision for one candidate-to-cell relation."""

    status: str
    table_kind: str = ""
    block_index: int | None = None
    logical_row: int | None = None
    logical_column: int | None = None
    header_path: tuple[str, ...] = ()
    owner_path: tuple[str, ...] = ()
    owner_cell: Mapping[str, Any] = field(default_factory=dict)
    value_cell: Mapping[str, Any] = field(default_factory=dict)
    source_rows: tuple[str, ...] = ()
    distinct_match_count: int = 0
    decision_key: str = ""
    reason: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "table_kind": self.table_kind,
            "block_index": self.block_index,
            "logical_row": self.logical_row,
            "logical_column": self.logical_column,
            "header_path": list(self.header_path),
            "owner_path": list(self.owner_path),
            "owner_cell": dict(self.owner_cell),
            "value_cell": dict(self.value_cell),
            "source_rows": list(self.source_rows),
            "distinct_match_count": self.distinct_match_count,
            "decision_key": self.decision_key,
            "reason": self.reason,
        }


@dataclass(frozen=True)
class _StructuredTableMatch:
    """Internal representation of one completely proven table coordinate."""

    logical_row: int
    logical_column: int
    owner_cell: LogicalCell
    value_cell: LogicalCell
    header_path: tuple[str, ...]
    owner_path: tuple[str, ...]
    source_row_indexes: tuple[int, ...]


@dataclass(frozen=True)
class DiscretePropertyCell:
    """One literal numeric tensile cell in a bounded categorical sidecar."""

    column_index: int
    header_raw: str
    property_name: str
    value_raw: str
    unit_raw: str
    decision_key: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "column_index": self.column_index,
            "header_raw": self.header_raw,
            "property_name": self.property_name,
            "value_raw": self.value_raw,
            "unit_raw": self.unit_raw,
            "decision_key": self.decision_key,
        }


@dataclass(frozen=True)
class DiscreteSidecarRow:
    """One source-literal condition/orientation result row."""

    row_index: int
    raw_row: str
    condition: str
    orientation: str
    properties: tuple[DiscretePropertyCell, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "row_index": self.row_index,
            "raw_row": self.raw_row,
            "condition": self.condition,
            "orientation": self.orientation,
            "properties": [cell.to_dict() for cell in self.properties],
        }


@dataclass(frozen=True)
class DiscreteSidecarDecision:
    """One bounded and auditable sidecar eligibility decision."""

    status: str
    reference: str
    resolved_path: str = ""
    content_sha256: str = ""
    row_count: int = 0
    column_count: int = 0
    nonempty_cell_count: int = 0
    rows: tuple[DiscreteSidecarRow, ...] = ()
    reason: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "reference": self.reference,
            "resolved_path": self.resolved_path,
            "content_sha256": self.content_sha256,
            "row_count": self.row_count,
            "column_count": self.column_count,
            "nonempty_cell_count": self.nonempty_cell_count,
            "rows": [row.to_dict() for row in self.rows],
            "reason": self.reason,
        }


@dataclass(frozen=True)
class DenseTensileCell:
    """One explicit Target core-tensile cell from a logical source table."""

    owner: str
    owner_literal: str
    property_name: str
    value_raw: str
    unit_raw: str
    orientation: str
    table_kind: str
    block_index: int
    logical_row: int
    logical_column: int
    header_path: tuple[str, ...]
    owner_cell: Mapping[str, Any]
    value_cell: Mapping[str, Any]
    source_rows: tuple[str, ...]
    source_coordinate_key: str
    decision_key: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "owner": self.owner,
            "owner_literal": self.owner_literal,
            "property_name": self.property_name,
            "value_raw": self.value_raw,
            "unit_raw": self.unit_raw,
            "orientation": self.orientation,
            "table_kind": self.table_kind,
            "block_index": self.block_index,
            "logical_row": self.logical_row,
            "logical_column": self.logical_column,
            "header_path": list(self.header_path),
            "owner_cell": dict(self.owner_cell),
            "value_cell": dict(self.value_cell),
            "source_rows": list(self.source_rows),
            "source_coordinate_key": self.source_coordinate_key,
            "decision_key": self.decision_key,
        }


@dataclass(frozen=True)
class DenseTensileTableDecision:
    """Auditable v203 eligibility decision for one logical source table."""

    status: str
    table_kind: str
    block_index: int
    cells: tuple[DenseTensileCell, ...] = ()
    reason: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "table_kind": self.table_kind,
            "block_index": self.block_index,
            "cells": [cell.to_dict() for cell in self.cells],
            "reason": self.reason,
        }


@dataclass(frozen=True)
class TensileAssertionCoordinate:
    """One source-literal core-tensile owner/property/value coordinate."""

    owner_key: str
    owner_literal: str
    property_family: str
    property_name: str
    value_raw: str
    unit_raw: str
    condition_raw: str
    assertion_type: str
    block_index: int
    line_start: int
    line_end: int
    source_text: str
    owner_span: tuple[int, int]
    property_span: tuple[int, int]
    value_span: tuple[int, int]
    bundle_key: str
    source_coordinate_key: str
    decision_key: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "owner_key": self.owner_key,
            "owner_literal": self.owner_literal,
            "property_family": self.property_family,
            "property_name": self.property_name,
            "value_raw": self.value_raw,
            "unit_raw": self.unit_raw,
            "condition_raw": self.condition_raw,
            "assertion_type": self.assertion_type,
            "block_index": self.block_index,
            "line_start": self.line_start,
            "line_end": self.line_end,
            "source_text": self.source_text,
            "owner_span": list(self.owner_span),
            "property_span": list(self.property_span),
            "value_span": list(self.value_span),
            "bundle_key": self.bundle_key,
            "source_coordinate_key": self.source_coordinate_key,
            "decision_key": self.decision_key,
        }


@dataclass(frozen=True)
class TensileAssertionDecision:
    """Fail-closed decision for one frozen tensile candidate."""

    status: str
    coordinate: TensileAssertionCoordinate | None = None
    candidates: tuple[TensileAssertionCoordinate, ...] = ()
    reason: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "coordinate": (
                self.coordinate.to_dict() if self.coordinate is not None else None
            ),
            "candidates": [row.to_dict() for row in self.candidates],
            "reason": self.reason,
        }


def _normalized_cell(value: str) -> str:
    return normalize_evidence_text(_TAG.sub(" ", unescape(str(value or ""))))


def _span_attributes(attributes: str) -> tuple[int, int]:
    values = {name.casefold(): int(value) for name, value in _SPAN.findall(attributes)}
    # Large corrupt spans can otherwise create an accidental memory amplifier.
    return min(max(values.get("rowspan", 1), 1), 64), min(
        max(values.get("colspan", 1), 1), 64
    )


def _infer_header_row_count(rows: Sequence[Sequence[LogicalCell | None]]) -> int:
    if not rows:
        return 0
    explicit = [
        index
        for index, row in enumerate(rows)
        if any(cell is not None and cell.is_header for cell in row)
    ]
    if explicit:
        return min(max(explicit) + 1, len(rows) - 1) if len(rows) > 1 else 1
    for index, row in enumerate(rows):
        distinct: dict[tuple[int, int], LogicalCell] = {}
        for cell in row:
            if cell is not None:
                distinct.setdefault(cell.origin, cell)
        numeric_cells = sum(bool(_NUMBER.search(cell.text)) for cell in distinct.values())
        if numeric_cells >= 2:
            return index
    return 1 if len(rows) > 1 else 0


def _rectangularize(
    rows: Sequence[Mapping[int, LogicalCell]],
) -> tuple[tuple[LogicalCell | None, ...], ...]:
    width = max((max(row, default=-1) + 1 for row in rows), default=0)
    return tuple(tuple(row.get(column) for column in range(width)) for row in rows)


def _html_logical_table(raw: str, block_index: int) -> LogicalTable | None:
    raw_rows = tuple(match.group(0) for match in _ROW.finditer(raw))
    if not raw_rows:
        return None
    active: dict[int, tuple[LogicalCell, int]] = {}
    expanded: list[dict[int, LogicalCell]] = []
    for row_index, raw_row in enumerate(raw_rows):
        occupied = {column: cell for column, (cell, _) in active.items()}
        next_active = {
            column: (cell, remaining - 1)
            for column, (cell, remaining) in active.items()
            if remaining > 1
        }
        column = 0
        for source_cell_index, match in enumerate(_CELL.finditer(raw_row)):
            while column in occupied:
                column += 1
            tag, attributes, inner = match.groups()
            row_span, column_span = _span_attributes(attributes)
            cell = LogicalCell(
                text=_normalized_cell(inner),
                raw_text=unescape(_TAG.sub(" ", inner)).strip(),
                origin=(row_index, source_cell_index),
                row_span=row_span,
                column_span=column_span,
                is_header=tag.casefold() == "th",
            )
            for offset in range(column_span):
                slot = column + offset
                if slot in occupied:
                    # An overlapping malformed span invalidates only this table.
                    return None
                occupied[slot] = cell
                if row_span > 1:
                    next_active[slot] = (cell, row_span - 1)
            column += column_span
        if not occupied:
            continue
        expanded.append(occupied)
        active = next_active
    rows = _rectangularize(expanded)
    if not rows:
        return None
    return LogicalTable(
        block_index=block_index,
        kind="html",
        raw=raw,
        raw_rows=raw_rows,
        rows=rows,
        header_row_count=_infer_header_row_count(rows),
    )


def _markdown_cells(raw: str) -> tuple[str, ...]:
    value = str(raw or "").strip()
    if not (value.startswith("|") and value.endswith("|")):
        return ()
    return tuple(_normalized_cell(cell) for cell in value[1:-1].split("|"))


def _markdown_separator(cells: Sequence[str]) -> bool:
    return bool(cells) and all(
        not cell or re.fullmatch(r":?-{2,}:?", cell) is not None for cell in cells
    )


def _markdown_logical_tables(source_text: str, offset: int) -> list[LogicalTable]:
    blocks: list[list[str]] = []
    current: list[str] = []
    for raw_line in str(source_text or "").splitlines():
        stripped = raw_line.strip()
        if stripped.startswith("|") and stripped.endswith("|"):
            current.append(stripped)
            continue
        if current:
            blocks.append(current)
            current = []
    if current:
        blocks.append(current)

    tables: list[LogicalTable] = []
    for local_index, raw_rows in enumerate(blocks):
        separator = next(
            (
                index
                for index, raw_row in enumerate(raw_rows)
                if _markdown_separator(_markdown_cells(raw_row))
            ),
            None,
        )
        logical_rows: list[dict[int, LogicalCell]] = []
        retained_rows: list[str] = []
        for source_row_index, raw_row in enumerate(raw_rows):
            cells = _markdown_cells(raw_row)
            if _markdown_separator(cells):
                continue
            logical_row_index = len(logical_rows)
            logical_rows.append(
                {
                    column: LogicalCell(
                        text=text,
                        raw_text=raw_row[1:-1].split("|")[column].strip(),
                        origin=(logical_row_index, column),
                        is_header=(
                            separator is not None and source_row_index < separator
                        ),
                    )
                    for column, text in enumerate(cells)
                }
            )
            retained_rows.append(raw_row)
        rows = _rectangularize(logical_rows)
        if not rows:
            continue
        header_count = (
            sum(1 for index in range(separator or 0))
            if separator is not None
            else _infer_header_row_count(rows)
        )
        tables.append(
            LogicalTable(
                block_index=offset + local_index,
                kind="markdown",
                raw="\n".join(raw_rows),
                raw_rows=tuple(retained_rows),
                rows=rows,
                header_row_count=header_count,
            )
        )
    return tables


def logical_tables(source_text: str) -> tuple[LogicalTable, ...]:
    """Parse every source table into stable logical cell coordinates."""

    html_tables = [
        table
        for index, match in enumerate(_TABLE.finditer(str(source_text or "")))
        if (table := _html_logical_table(match.group(0), index)) is not None
    ]
    markdown_tables = _markdown_logical_tables(source_text, len(html_tables))
    return tuple([*html_tables, *markdown_tables])


def _all_evidence(value: Any) -> list[str]:
    rows: list[str] = []
    if isinstance(value, Mapping):
        for key, child in value.items():
            if str(key).casefold() == "source_evidence":
                if isinstance(child, str):
                    child = [child]
                if isinstance(child, Sequence) and not isinstance(child, (str, bytes)):
                    rows.extend(str(row).strip() for row in child if str(row).strip())
            else:
                rows.extend(_all_evidence(child))
    elif isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        for child in value:
            rows.extend(_all_evidence(child))
    return list(dict.fromkeys(rows))


def _evidence_rows(payload: Mapping[str, Any]) -> tuple[tuple[str, ...], ...]:
    rows: list[tuple[str, ...]] = []
    for evidence in _all_evidence(payload):
        for line in evidence_body(evidence).splitlines() or [evidence]:
            cells = _markdown_cells(line.strip())
            if cells and not _markdown_separator(cells):
                rows.append(tuple(cell for cell in cells if cell))
    return tuple(dict.fromkeys(rows))


def _ordered_projection(needles: Sequence[str], haystack: Sequence[str]) -> bool:
    position = 0
    for needle in needles:
        while position < len(haystack) and haystack[position] != needle:
            position += 1
        if position >= len(haystack):
            return False
        position += 1
    return True


def _header_text(table: LogicalTable, column: int) -> str:
    return " / ".join(table.header_path(column))


def _property_header_matches(name: str, unit: str, header: str) -> bool:
    property_name = normalize_evidence_text(name)
    unit_name = normalize_evidence_text(unit)
    if not property_name or not unit_name or property_name not in header:
        return False
    if unit_name == "%":
        return "%" in header
    return re.search(
        rf"(?<![a-z0-9]){re.escape(unit_name)}(?![a-z0-9])", header
    ) is not None


def _owner_cells(table: LogicalTable, row_index: int, owner: str) -> tuple[LogicalCell, ...]:
    normalized_owner = normalize_evidence_text(owner)
    return tuple(
        cell for cell in table.row_cells(row_index) if cell.text == normalized_owner
    )


def _value_cell_matches(
    value: str,
    cell_text: str,
    data: Mapping[str, Any],
    *,
    require_cell_local_locator: bool,
) -> bool:
    """Match a value exactly, optionally after removing one local citation.

    Column-owner reference tables commonly store ``880 [38]`` in one cell
    while the provider returns ``value_raw=880`` and ``raw_note=[38]``.  The
    suffix is removable only when that same candidate carries the exact local
    citation or standard.  This deliberately rejects numeric substring
    matches such as ``80`` against ``880 [38]``.
    """

    normalized_value = normalize_evidence_text(value)
    normalized_cell = normalize_evidence_text(cell_text)
    if not normalized_value or not normalized_cell:
        return False
    if normalized_cell == normalized_value:
        return not require_cell_local_locator

    cell_brackets = tuple(re.findall(r"\[[^\[\]]+\]", normalized_cell))
    raw_note = normalize_evidence_text(str(data.get("raw_note") or ""))
    note_brackets = tuple(re.findall(r"\[[^\[\]]+\]", raw_note))
    standard = normalize_evidence_text(str(data.get("test_standard_raw") or ""))

    removable: list[str] = []
    for note in note_brackets:
        note_compact = re.sub(r"[^a-z0-9]+", "", note)
        for bracket in cell_brackets:
            bracket_compact = re.sub(r"[^a-z0-9]+", "", bracket)
            if note == bracket or (
                any(character.isalpha() for character in note)
                and note_compact
                and note_compact == bracket_compact
            ):
                removable.append(bracket)
    if standard:
        standard_compact = re.sub(r"[^a-z0-9]+", "", standard)
        for bracket in cell_brackets:
            bracket_compact = re.sub(r"[^a-z0-9]+", "", bracket)
            if standard in bracket or (
                standard_compact and standard_compact in bracket_compact
            ):
                removable.append(bracket)
        if standard in normalized_cell:
            removable.append(standard)

    for locator in dict.fromkeys(removable):
        residue = normalize_evidence_text(normalized_cell.replace(locator, " ", 1))
        if residue == normalized_value:
            return True
    return False


def _unique_cells(cells: Sequence[LogicalCell]) -> tuple[LogicalCell, ...]:
    return tuple({cell.origin: cell for cell in cells}.values())


def _row_owner_matches(
    payload: Mapping[str, Any],
    table: LogicalTable,
    *,
    owner: str,
    value: str,
    name: str,
    unit: str,
    evidence_rows: Sequence[Sequence[str]],
) -> list[_StructuredTableMatch]:
    matches: list[_StructuredTableMatch] = []
    for row_index in range(table.header_row_count, len(table.rows)):
        owner_cells = _unique_cells(_owner_cells(table, row_index, owner))
        if len(owner_cells) != 1:
            continue
        row_text = tuple(cell.text for cell in table.row_cells(row_index))
        for column, cell in enumerate(table.rows[row_index]):
            if cell is None or not _value_cell_matches(
                value, cell.text, payload["data"], require_cell_local_locator=False
            ):
                continue
            header_path = table.header_path(column)
            header = " / ".join(header_path)
            if not _property_header_matches(name, unit, header):
                continue
            data_supported = any(
                normalize_evidence_text(owner) in evidence_row
                and cell.text in evidence_row
                and len(evidence_row) >= 2
                and _ordered_projection(evidence_row, row_text)
                for evidence_row in evidence_rows
            )
            header_paths = tuple(
                _header_text(table, index) for index in range(len(table.rows[0]))
            )
            header_supported = any(
                header in evidence_row
                and _ordered_projection(evidence_row, header_paths)
                for evidence_row in evidence_rows
            )
            if data_supported and header_supported:
                matches.append(
                    _StructuredTableMatch(
                        logical_row=row_index,
                        logical_column=column,
                        owner_cell=owner_cells[0],
                        value_cell=cell,
                        header_path=header_path,
                        owner_path=(owner_cells[0].text,),
                        source_row_indexes=(row_index,),
                    )
                )
    return matches


def _column_owner_matches(
    payload: Mapping[str, Any],
    table: LogicalTable,
    *,
    owner: str,
    value: str,
    name: str,
    unit: str,
    evidence_rows: Sequence[Sequence[str]],
) -> list[_StructuredTableMatch]:
    """Resolve tables whose owners are columns and properties are rows."""

    normalized_owner = normalize_evidence_text(owner)
    if not normalized_owner or table.header_row_count <= 0:
        return []
    width = len(table.rows[0]) if table.rows else 0
    header_paths = tuple(_header_text(table, index) for index in range(width))
    matches: list[_StructuredTableMatch] = []
    for column in range(width):
        owner_cells = _unique_cells(
            tuple(
                table.rows[row_index][column]
                for row_index in range(table.header_row_count)
                if column < len(table.rows[row_index])
                and table.rows[row_index][column] is not None
                and table.rows[row_index][column].text == normalized_owner
            )
        )
        if len(owner_cells) != 1:
            continue
        header_supported = any(
            normalized_owner in evidence_row
            and _ordered_projection(evidence_row, header_paths)
            for evidence_row in evidence_rows
        )
        if not header_supported:
            continue
        for row_index in range(table.header_row_count, len(table.rows)):
            if column >= len(table.rows[row_index]):
                continue
            value_cell = table.rows[row_index][column]
            if value_cell is None or not _value_cell_matches(
                value,
                value_cell.text,
                payload["data"],
                require_cell_local_locator=True,
            ):
                continue
            property_cells = _unique_cells(
                tuple(
                    cell
                    for cell in table.row_cells(row_index)
                    if _property_header_matches(name, unit, cell.text)
                )
            )
            if len(property_cells) != 1:
                continue
            property_cell = property_cells[0]
            row_text = tuple(cell.text for cell in table.row_cells(row_index))
            data_supported = any(
                property_cell.text in evidence_row
                and value_cell.text in evidence_row
                and _ordered_projection(evidence_row, row_text)
                for evidence_row in evidence_rows
            )
            if not data_supported:
                continue
            physical_rows = tuple(
                dict.fromkeys((property_cell.origin[0], value_cell.origin[0]))
            )
            matches.append(
                _StructuredTableMatch(
                    logical_row=value_cell.origin[0],
                    logical_column=column,
                    owner_cell=owner_cells[0],
                    value_cell=value_cell,
                    header_path=(property_cell.text,),
                    owner_path=(owner_cells[0].text,),
                    source_row_indexes=physical_rows,
                )
            )
    return matches


def _record_matches_table(
    payload: Mapping[str, Any], table: LogicalTable
) -> list[_StructuredTableMatch]:
    data = payload.get("data")
    if not isinstance(data, Mapping):
        return []
    owner = str(payload.get("sample_id_raw") or "").strip()
    value = normalize_evidence_text(str(data.get("value_raw") or ""))
    name = str(data.get("property_name_raw") or "")
    unit = str(data.get("unit_raw") or "")
    if not owner or not value or not name or not unit:
        return []
    evidence_rows = _evidence_rows(payload)
    matches = [
        *_row_owner_matches(
            payload,
            table,
            owner=owner,
            value=value,
            name=name,
            unit=unit,
            evidence_rows=evidence_rows,
        ),
        *_column_owner_matches(
            payload,
            table,
            owner=owner,
            value=value,
            name=name,
            unit=unit,
            evidence_rows=evidence_rows,
        ),
    ]
    # A spanning value cell may occupy multiple slots. Treat its source origin,
    # not presentation width, as one scientific coordinate.
    distinct: dict[
        tuple[tuple[int, int], tuple[int, int], tuple[str, ...], tuple[str, ...]],
        _StructuredTableMatch,
    ] = {}
    for match in matches:
        distinct.setdefault(
            (
                match.owner_cell.origin,
                match.value_cell.origin,
                match.header_path,
                match.owner_path,
            ),
            match,
        )
    return list(distinct.values())


def _decision_key(table: LogicalTable, match: _StructuredTableMatch) -> str:
    payload = {
        "table_kind": table.kind,
        "block_index": table.block_index,
        "logical_row": match.logical_row,
        "logical_column": match.logical_column,
        "source_cell": list(match.value_cell.origin),
        "header_path": list(match.header_path),
        "owner_path": list(match.owner_path),
        "value": match.value_cell.text,
    }
    digest = hashlib.sha256(
        json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode(
            "utf-8"
        )
    ).hexdigest()
    return f"table-cell:{digest}"


def resolve_structured_table_record(
    record: Any, source_text: str
) -> SourceCoordinateDecision:
    """Resolve one existing Property candidate to exactly one source cell."""

    payload = record.model_dump() if hasattr(record, "model_dump") else dict(record)
    if payload.get("axis") != "properties" or payload.get("fact_type") != "property":
        return SourceCoordinateDecision(
            status="not_applicable", reason="only existing Property candidates are eligible"
        )
    candidates: list[
        tuple[LogicalTable, _StructuredTableMatch]
    ] = []
    for table in logical_tables(source_text):
        for match in _record_matches_table(payload, table):
            candidates.append((table, match))
    if not candidates:
        return SourceCoordinateDecision(
            status="not_found",
            reason=(
                "no table contains one evidence-supported owner/property/unit/value cell"
            ),
        )
    if len(candidates) != 1:
        return SourceCoordinateDecision(
            status="ambiguous",
            distinct_match_count=len(candidates),
            reason="more than one table cell satisfies the complete source coordinate",
        )
    table, match = candidates[0]
    row_indexes = tuple(
        dict.fromkeys((*range(table.header_row_count), *match.source_row_indexes))
    )
    source_rows = tuple(
        table.raw_rows[index]
        for index in row_indexes
        if 0 <= index < len(table.raw_rows)
    )
    return SourceCoordinateDecision(
        status="matched",
        table_kind=table.kind,
        block_index=table.block_index,
        logical_row=match.logical_row,
        logical_column=match.logical_column,
        header_path=match.header_path,
        owner_path=match.owner_path,
        owner_cell=match.owner_cell.to_dict(),
        value_cell=match.value_cell.to_dict(),
        source_rows=source_rows,
        distinct_match_count=1,
        decision_key=_decision_key(table, match),
        reason="one table cell proves the candidate owner, property, unit, and value",
    )


def _sidecar_rejection(reference: str, reason: str) -> DiscreteSidecarDecision:
    return DiscreteSidecarDecision(
        status="rejected", reference=reference, reason=reason
    )


def _safe_sidecar_path(
    source_dir: Path, reference: str
) -> tuple[Path | None, str | None]:
    raw = Path(str(reference or ""))
    if (
        not reference
        or raw.is_absolute()
        or ".." in raw.parts
        or raw.name in {"", ".", ".."}
    ):
        return None, "unsafe_sidecar_path"
    try:
        root = source_dir.resolve(strict=True)
    except (OSError, RuntimeError):
        return None, "invalid_source_dir"
    try:
        candidate = (root / raw).resolve(strict=True)
    except (OSError, RuntimeError):
        return None, "sidecar_missing_or_unreadable"
    if not candidate.is_relative_to(root):
        return None, "sidecar_resolves_outside_source_dir"
    if not candidate.is_file():
        return None, "sidecar_not_regular_file"
    return candidate, None


def _continuous_sidecar_reason(
    headers: Sequence[str], rows: Sequence[Sequence[str]]
) -> str | None:
    normalized = [normalize_evidence_text(header).replace(" ", "_") for header in headers]
    positions = {header: index for index, header in enumerate(normalized)}
    if {"series", "kind", "x", "y"} <= set(positions):
        kinds = {
            normalize_evidence_text(row[positions["kind"]])
            for row in rows
            if len(row) > positions["kind"]
        }
        if not kinds or kinds & {"trend", "curve", "line"}:
            return "series_kind_xy_continuous_shape"
    if len(rows) > 32 or len(headers) > 12:
        return "categorical_shape_cap_exceeded"
    nonempty = sum(bool(str(cell).strip()) for row in rows for cell in row)
    if nonempty > 192:
        return "categorical_shape_cap_exceeded"
    # Sampled trajectories without a kind column still expose repeated series
    # labels and x coordinates. They are not categorical result tables.
    if {"series", "x", "y"} <= set(positions):
        series_x = [
            (
                normalize_evidence_text(row[positions["series"]]),
                normalize_evidence_text(row[positions["x"]]),
            )
            for row in rows
            if len(row) > max(positions["series"], positions["x"])
        ]
        if len(series_x) > len({series for series, _ in series_x}):
            return "sampled_series_xy_continuous_shape"
    return None


def _tensile_header(header: str) -> tuple[str, str] | None:
    raw = str(header or "").strip()
    unit_match = re.search(r"(?:_|\s)(MPa|GPa|kPa|Pa|%)\s*$", raw, re.I)
    if unit_match is None:
        return None
    unit_token = unit_match.group(1)
    unit = "%" if unit_token == "%" else unit_token[0].upper() + unit_token[1:].lower()
    # Restore conventional pressure-unit capitalization.
    unit = {"Mpa": "MPa", "Gpa": "GPa", "Kpa": "kPa", "Pa": "Pa"}.get(
        unit, unit
    )
    semantic = re.sub(r"[_\-]+", " ", raw[: unit_match.start()])
    semantic = re.sub(r"\s+", " ", semantic).strip()
    folded = normalize_evidence_text(semantic)
    if "ultimate tensile strength" in folded or re.fullmatch(r"uts", folded):
        return "Ultimate Tensile Strength", unit
    if "yield strength" in folded or re.fullmatch(r"(?:0\.2 ?% ?)?ys", folded):
        return (
            "0.2% Yield Strength" if "0.2" in folded else "Yield Strength",
            unit,
        )
    if "elongation" in folded and unit == "%":
        return "Elongation", unit
    return None


def _sidecar_decision_key(
    content_hash: str, reference: str, row_index: int, column_index: int
) -> str:
    coordinate = f"{content_hash}:{reference}:{row_index}:{column_index}"
    return "sidecar-cell:" + hashlib.sha256(coordinate.encode("utf-8")).hexdigest()


def _parse_discrete_sidecar(
    reference: str, path: Path
) -> DiscreteSidecarDecision:
    try:
        raw_bytes = path.read_bytes()
        text = raw_bytes.decode("utf-8-sig")
    except (OSError, UnicodeError):
        return _sidecar_rejection(reference, "sidecar_missing_or_unreadable")
    content_hash = hashlib.sha256(raw_bytes).hexdigest()
    raw_lines = text.splitlines()
    if len(raw_lines) < 2:
        return DiscreteSidecarDecision(
            status="not_applicable",
            reference=reference,
            resolved_path=str(path),
            content_sha256=content_hash,
            reason="sidecar_has_no_data_rows",
        )
    try:
        parsed_lines = [next(csv.reader([line])) for line in raw_lines if line.strip()]
    except (csv.Error, StopIteration):
        return _sidecar_rejection(reference, "malformed_csv")
    if len(parsed_lines) < 2:
        return _sidecar_rejection(reference, "malformed_csv")
    headers = [str(value).strip() for value in parsed_lines[0]]
    rows = [[str(value).strip() for value in row] for row in parsed_lines[1:]]
    if not headers or any(len(row) != len(headers) for row in rows):
        return _sidecar_rejection(reference, "ragged_csv_rows")
    normalized_headers = [normalize_evidence_text(value) for value in headers]
    if len(set(normalized_headers)) != len(normalized_headers):
        return _sidecar_rejection(reference, "duplicate_csv_headers")
    row_count = len(rows)
    column_count = len(headers)
    nonempty = sum(bool(cell) for row in rows for cell in row)
    continuous = _continuous_sidecar_reason(headers, rows)
    if continuous is not None:
        return DiscreteSidecarDecision(
            status="continuous",
            reference=reference,
            resolved_path=str(path),
            content_sha256=content_hash,
            row_count=row_count,
            column_count=column_count,
            nonempty_cell_count=nonempty,
            reason=continuous,
        )
    property_columns = {
        column: parsed
        for column, header in enumerate(headers)
        if (parsed := _tensile_header(header)) is not None
    }
    if not property_columns:
        return DiscreteSidecarDecision(
            status="not_applicable",
            reference=reference,
            resolved_path=str(path),
            content_sha256=content_hash,
            row_count=row_count,
            column_count=column_count,
            nonempty_cell_count=nonempty,
            reason="no_explicit_core_tensile_header_with_unit",
        )
    condition_columns = [
        index
        for index, header in enumerate(normalized_headers)
        if header in {"condition", "state", "material state", "sample condition"}
    ]
    if len(condition_columns) != 1:
        return _sidecar_rejection(reference, "missing_or_ambiguous_condition_column")
    orientation_columns = [
        index
        for index, header in enumerate(normalized_headers)
        if header in {"orientation", "build orientation", "loading orientation"}
    ]
    if len(orientation_columns) > 1:
        return _sidecar_rejection(reference, "ambiguous_orientation_column")
    condition_column = condition_columns[0]
    orientation_column = orientation_columns[0] if orientation_columns else None
    recovered_rows: list[DiscreteSidecarRow] = []
    for row_index, row in enumerate(rows, start=1):
        condition = row[condition_column].strip()
        orientation = (
            row[orientation_column].strip() if orientation_column is not None else ""
        )
        if not condition or (orientation_column is not None and not orientation):
            return _sidecar_rejection(reference, "missing_row_condition_or_orientation")
        properties: list[DiscretePropertyCell] = []
        for column, (property_name, unit) in sorted(property_columns.items()):
            value = row[column].strip()
            if _EXACT_NUMBER.fullmatch(value) is None:
                return _sidecar_rejection(reference, "nonnumeric_tensile_cell")
            properties.append(
                DiscretePropertyCell(
                    column_index=column,
                    header_raw=headers[column],
                    property_name=property_name,
                    value_raw=value,
                    unit_raw=unit,
                    decision_key=_sidecar_decision_key(
                        content_hash, reference, row_index, column
                    ),
                )
            )
        recovered_rows.append(
            DiscreteSidecarRow(
                row_index=row_index,
                raw_row=raw_lines[row_index],
                condition=condition,
                orientation=orientation,
                properties=tuple(properties),
            )
        )
    return DiscreteSidecarDecision(
        status="eligible",
        reference=reference,
        resolved_path=str(path),
        content_sha256=content_hash,
        row_count=row_count,
        column_count=column_count,
        nonempty_cell_count=nonempty,
        rows=tuple(recovered_rows),
        reason="bounded_categorical_core_tensile_sidecar",
    )


def discrete_tensile_sidecars(
    source_text: str, source_dir: Path | str | None
) -> tuple[DiscreteSidecarDecision, ...]:
    """Return bounded categorical tensile sidecars referenced by one paper.

    The full CSV remains outside model context.  This function performs only
    local deterministic parsing beneath the caller-provided paper directory.
    """

    references = [match.group(1).strip() for match in _CSV_REFERENCE.finditer(source_text)]
    if not references:
        return ()
    counts = {reference: references.count(reference) for reference in set(references)}
    decisions: list[DiscreteSidecarDecision] = []
    for reference in dict.fromkeys(references):
        if counts[reference] != 1:
            decisions.append(_sidecar_rejection(reference, "duplicate_source_reference"))
            continue
        if source_dir is None:
            decisions.append(_sidecar_rejection(reference, "missing_source_dir"))
            continue
        path, reason = _safe_sidecar_path(Path(source_dir), reference)
        if path is None:
            decisions.append(_sidecar_rejection(reference, reason or "unsafe_sidecar_path"))
            continue
        decisions.append(_parse_discrete_sidecar(reference, path))
    return tuple(decisions)


def _dense_tensile_header(header: str) -> tuple[str, str] | None:
    """Resolve one explicit table header to a core tensile semantic and unit."""

    raw = re.sub(r"\s+", " ", str(header or "")).strip()
    unit_match = re.search(
        r"(?ix)(?:\(\s*|\[\s*|/\s*|\s+)"
        r"(MPa|GPa|kPa|Pa|ksi|%)\s*(?:\)|\])?\s*$",
        raw,
    )
    if unit_match is None:
        return None
    unit_token = unit_match.group(1)
    unit = {
        "mpa": "MPa",
        "gpa": "GPa",
        "kpa": "kPa",
        "pa": "Pa",
        "ksi": "ksi",
        "%": "%",
    }[unit_token.casefold()]
    semantic = normalize_evidence_text(raw[: unit_match.start()])
    semantic = re.sub(r"[^a-z0-9.%]+", " ", semantic).strip()
    if semantic in {"uts", "ts"} or "ultimate tensile strength" in semantic:
        return "Ultimate Tensile Strength", unit
    if semantic in {"ys", "0.2% ys", "0.2 ys"} or re.search(
        r"(?:^|\s)(?:0\.2%?\s+)?ys$|\byield (?:strength|stress)\b",
        semantic,
    ):
        return (
            "0.2% Yield Strength" if "0.2" in semantic else "Yield Strength",
            unit,
        )
    if unit == "%" and re.search(
        r"\b(?:total |uniform )?elongation\b|\b(?:eab|te|el)\b", semantic
    ):
        if "total" in semantic:
            return "Total Elongation", unit
        if "uniform" in semantic:
            return "Uniform Elongation", unit
        return "Elongation", unit
    return None


def _dense_numeric_value(cell: LogicalCell) -> str | None:
    value = unescape(_TAG.sub(" ", str(cell.raw_text or cell.text or "")))
    value = value.replace("$", "").replace("\\pm", "±")
    value = re.sub(r"\s+", " ", value).strip()
    return value if _DENSE_NUMERIC_CELL.fullmatch(value) is not None else None


def _dense_owner_alias_index(
    owner_aliases: Mapping[str, Sequence[str]],
) -> dict[str, tuple[str, ...]]:
    index: dict[str, set[str]] = {}
    for owner in sorted(str(value).strip() for value in owner_aliases if str(value).strip()):
        aliases = owner_aliases.get(owner, ())
        for alias in (owner, *aliases):
            normalized = normalize_evidence_text(str(alias or ""))
            if normalized:
                index.setdefault(normalized, set()).add(owner)
    return {alias: tuple(sorted(owners)) for alias, owners in sorted(index.items())}


def _dense_header_owner(
    header_path: Sequence[str],
    alias_index: Mapping[str, tuple[str, ...]],
) -> tuple[tuple[str, ...], str]:
    """Resolve the longest literal header path before a leaf-only alias.

    Multi-level tensile tables commonly encode a material and orientation as
    ``WAAM / Horizontal``.  Treating only the leaf as the owner collapses two
    physical specimens into one base item.  The complete source path wins when
    it names one inventory owner; leaf fallback remains available for ordinary
    single-row headers such as ``0 s Delay``.
    """

    raw_parts = tuple(str(value or "").strip() for value in header_path if value)
    candidates: list[tuple[str, str]] = []
    if raw_parts:
        for separator in (" / ", " "):
            literal = separator.join(raw_parts)
            candidates.append((normalize_evidence_text(literal), literal))
        candidates.extend(
            (normalize_evidence_text(value), value)
            for value in reversed(raw_parts)
        )
    for normalized, literal in candidates:
        owners = alias_index.get(normalized, ())
        if owners:
            return owners, literal
    return (), ""


def _dense_reference_owner(value: str) -> bool:
    """Reject a table header that explicitly declares reference provenance."""

    return _DENSE_REFERENCE_OWNER.search(str(value or "")) is not None


def _dense_orientation(cells: Sequence[LogicalCell], excluded: set[tuple[int, int]]) -> str:
    matches: list[str] = []
    for cell in cells:
        if cell.origin in excluded:
            continue
        normalized = normalize_evidence_text(cell.text)
        if re.fullmatch(
            r"(?:horizontal|vertical|transverse|longitudinal|parallel|"
            r"perpendicular|build direction|printing direction)",
            normalized,
        ):
            matches.append(cell.raw_text.strip() or cell.text)
    return matches[0] if len({_normalized_cell(value) for value in matches}) == 1 else ""


def _dense_orientation_header(header_path: Sequence[str]) -> bool:
    """Return whether a column path identifies a specimen only by orientation."""

    return any(
        re.fullmatch(
            r"(?:horizontal|vertical|transverse|longitudinal|parallel|"
            r"perpendicular|build direction|printing direction|x|y|z)",
            normalize_evidence_text(value),
        )
        is not None
        for value in header_path
    )


def _dense_source_rows(
    table: LogicalTable, owner_cell: LogicalCell, value_cell: LogicalCell
) -> tuple[str, ...]:
    indexes = tuple(
        dict.fromkeys(
            (
                *range(table.header_row_count),
                owner_cell.origin[0],
                value_cell.origin[0],
            )
        )
    )
    return tuple(
        table.raw_rows[index]
        for index in indexes
        if 0 <= index < len(table.raw_rows)
    )


def _dense_cell(
    table: LogicalTable,
    *,
    owner: str,
    owner_cell: LogicalCell,
    property_name: str,
    unit_raw: str,
    value_cell: LogicalCell,
    logical_row: int,
    logical_column: int,
    header_path: tuple[str, ...],
    orientation: str,
) -> DenseTensileCell | None:
    value_raw = _dense_numeric_value(value_cell)
    if value_raw is None:
        return None
    coordinate_match = _StructuredTableMatch(
        logical_row=logical_row,
        logical_column=logical_column,
        owner_cell=owner_cell,
        value_cell=value_cell,
        header_path=header_path,
        owner_path=(owner_cell.text,),
        source_row_indexes=tuple(
            dict.fromkeys((owner_cell.origin[0], value_cell.origin[0]))
        ),
    )
    source_coordinate_key = _decision_key(table, coordinate_match)
    digest = source_coordinate_key.removeprefix("table-cell:")
    return DenseTensileCell(
        owner=owner,
        owner_literal=owner_cell.raw_text.strip() or owner_cell.text,
        property_name=property_name,
        value_raw=value_raw,
        unit_raw=unit_raw,
        orientation=orientation,
        table_kind=table.kind,
        block_index=table.block_index,
        logical_row=logical_row,
        logical_column=logical_column,
        header_path=header_path,
        owner_cell=owner_cell.to_dict(),
        value_cell=value_cell.to_dict(),
        source_rows=_dense_source_rows(table, owner_cell, value_cell),
        source_coordinate_key=source_coordinate_key,
        decision_key=f"dense-table-cell:{digest}",
    )


def _row_owner_dense_cells(
    table: LogicalTable,
    alias_index: Mapping[str, tuple[str, ...]],
) -> tuple[list[DenseTensileCell], str | None, bool]:
    width = len(table.rows[0]) if table.rows else 0
    property_columns = {
        column: parsed
        for column in range(width)
        if (parsed := _dense_tensile_header(_header_text(table, column))) is not None
    }
    if not property_columns:
        return [], None, False
    cells: list[DenseTensileCell] = []
    saw_data_row = False
    first_property_column = min(property_columns)
    for row_index in range(table.header_row_count, len(table.rows)):
        row_cells = table.row_cells(row_index)
        owner_hits: list[tuple[LogicalCell, tuple[str, ...]]] = []
        for cell in row_cells:
            # In a row-owned table the owner must occur before the first
            # tensile result column.  A process/temperature/source column to
            # the right is metadata, not a material identity.
            if cell.origin[1] >= first_property_column:
                continue
            owners = alias_index.get(normalize_evidence_text(cell.text), ())
            if owners:
                owner_hits.append((cell, owners))
        if any(len(owners) > 1 for _, owners in owner_hits):
            return [], "ambiguous_target_owner_alias", True
        unique_hits = {
            (owner_cell.origin, owners[0]): owner_cell
            for owner_cell, owners in owner_hits
            if len(owners) == 1
        }
        owners = {owner for (_, owner) in unique_hits}
        if len(owners) > 1:
            return [], "multiple_target_owners_in_one_row", True
        if not owners:
            continue
        saw_data_row = True
        owner = next(iter(owners))
        owner_cell = next(
            cell
            for (origin, candidate_owner), cell in unique_hits.items()
            if candidate_owner == owner
        )
        if _dense_reference_owner(owner_cell.raw_text or owner_cell.text):
            continue
        for column, (property_name, unit_raw) in sorted(property_columns.items()):
            if column >= len(table.rows[row_index]):
                continue
            value_cell = table.rows[row_index][column]
            if value_cell is None or value_cell.origin == owner_cell.origin:
                continue
            if _dense_numeric_value(value_cell) is None:
                continue
            orientation = _dense_orientation(
                row_cells, {owner_cell.origin, value_cell.origin}
            )
            cell = _dense_cell(
                table,
                owner=owner,
                owner_cell=owner_cell,
                property_name=property_name,
                unit_raw=unit_raw,
                value_cell=value_cell,
                logical_row=row_index,
                logical_column=column,
                header_path=table.header_path(column),
                orientation=orientation,
            )
            if cell is not None:
                cells.append(cell)
    if cells:
        return cells, None, True
    return [], "no_numeric_target_tensile_cells" if saw_data_row else "no_unique_target_owner", True


def _column_owner_dense_cells(
    table: LogicalTable,
    alias_index: Mapping[str, tuple[str, ...]],
) -> tuple[list[DenseTensileCell], str | None, bool]:
    if table.header_row_count <= 0 or not table.rows:
        return [], None, False
    width = len(table.rows[0])
    column_owners: dict[int, tuple[str, LogicalCell]] = {}
    saw_orientation_owner = False
    for column in range(width):
        header_path = table.header_path(column)
        owners, owner_literal = _dense_header_owner(header_path, alias_index)
        if len(owners) > 1:
            return [], "ambiguous_target_owner_alias", True
        if len(owners) != 1 or _dense_reference_owner(owner_literal):
            continue
        # Orientation matrices need a separate, source-proven specimen
        # identity/state ledger.  Creating a material owner from the column
        # path alone raises loose recall but has repeatedly produced wrong-owner
        # strict claims.  Keep the complete table in audit and fail closed.
        if _dense_orientation_header(header_path):
            saw_orientation_owner = True
            continue
        owner_cell = next(
            (
                table.rows[row_index][column]
                for row_index in reversed(range(table.header_row_count))
                if table.rows[row_index][column] is not None
            ),
            None,
        )
        if owner_cell is not None:
            column_owners[column] = (owners[0], owner_cell)
    if not column_owners:
        return (
            [],
            (
                "orientation_header_requires_explicit_specimen_owner"
                if saw_orientation_owner
                else None
            ),
            saw_orientation_owner,
        )
    cells: list[DenseTensileCell] = []
    saw_property = False
    for row_index in range(table.header_row_count, len(table.rows)):
        row_cells = table.row_cells(row_index)
        property_hits = [
            (cell, parsed)
            for cell in row_cells
            if (parsed := _dense_tensile_header(cell.text)) is not None
        ]
        if len(property_hits) != 1:
            continue
        saw_property = True
        property_cell, (property_name, unit_raw) = property_hits[0]
        for column, (owner, owner_cell) in sorted(column_owners.items()):
            if column >= len(table.rows[row_index]):
                continue
            value_cell = table.rows[row_index][column]
            if value_cell is None or _dense_numeric_value(value_cell) is None:
                continue
            header_path = table.header_path(column)
            orientation = _dense_orientation(
                [
                    cell
                    for header_row in range(table.header_row_count)
                    if (cell := table.rows[header_row][column]) is not None
                ],
                set(),
            ) or _dense_orientation(
                row_cells, {property_cell.origin, value_cell.origin}
            )
            cell = _dense_cell(
                table,
                owner=owner,
                owner_cell=owner_cell,
                property_name=property_name,
                unit_raw=unit_raw,
                value_cell=value_cell,
                logical_row=row_index,
                logical_column=column,
                header_path=(property_cell.text, *header_path),
                orientation=orientation,
            )
            if cell is not None:
                cells.append(cell)
    if cells:
        return cells, None, True
    return [], "no_numeric_target_tensile_cells" if saw_property else None, saw_property


def dense_tensile_table_decisions(
    source_text: str,
    target_owner_aliases: Mapping[str, Sequence[str]],
) -> tuple[DenseTensileTableDecision, ...]:
    """Enumerate only uniquely owned, explicit Target core-tensile cells."""

    alias_index = _dense_owner_alias_index(target_owner_aliases)
    decisions: list[DenseTensileTableDecision] = []
    for table in logical_tables(source_text):
        row_cells, row_reason, row_applicable = _row_owner_dense_cells(
            table, alias_index
        )
        column_cells, column_reason, column_applicable = _column_owner_dense_cells(
            table, alias_index
        )
        cells_by_key = {
            cell.decision_key: cell for cell in (*row_cells, *column_cells)
        }
        cells = tuple(
            sorted(
                cells_by_key.values(),
                key=lambda cell: (
                    cell.logical_row,
                    cell.logical_column,
                    cell.owner.casefold(),
                    cell.decision_key,
                ),
            )
        )
        if cells:
            decisions.append(
                DenseTensileTableDecision(
                    status="eligible",
                    table_kind=table.kind,
                    block_index=table.block_index,
                    cells=cells,
                    reason="unique_explicit_target_core_tensile_cells",
                )
            )
            continue
        applicable = row_applicable or column_applicable
        reason = row_reason or column_reason
        decisions.append(
            DenseTensileTableDecision(
                status="rejected" if applicable and reason else "not_applicable",
                table_kind=table.kind,
                block_index=table.block_index,
                reason=reason or "no_explicit_core_tensile_header_with_unit",
            )
        )
    return tuple(decisions)


_ASSERTION_NUMBER = re.compile(
    r"(?<![A-Za-z0-9])[-+]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][-+]?\d+)?"
    r"(?![A-Za-z0-9])"
)
_ASSERTION_VALUE_WITH_UNIT = re.compile(
    r"(?ix)(?P<value>(?:[~≈<>≤≥]\s*)?"
    r"[-+]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][-+]?\d+)?"
    r"(?:\s*(?:±|\+/-)\s*[-+]?(?:\d+(?:\.\d*)?|\.\d+)"
    r"(?:[eE][-+]?\d+)?)?)\s*(?P<unit>gpa|mpa|\\?%)"
)
_ASSERTION_CONTINUATION = re.compile(
    r"(?ix)^\s*(?:its|their|this|these|the\s+(?:alloy|sample|specimen|material)|"
    r"(?:an?|the)\s+(?:yield|ultimate|tensile|fracture|uniform|total|elongation))\b"
)
_ASSERTION_TABLE_OR_SIDECAR = re.compile(
    r"(?ix)(?:^\s*\||<table\b|data_csv\s*:|vlm[- ]digitized|line[- ]chart)"
)
_ASSERTION_RESULT_TEMPERATURE = re.compile(
    r"(?ix)(?:\b(?:ambient|room)[\s-]+temperature\b|"
    r"(?<![a-z0-9])[-+]?(?:\d+(?:\.\d*)?|\.\d+)\s*°\s*c\b|"
    r"(?<![a-z0-9])[-+]?(?:\d+(?:\.\d*)?|\.\d+)\s*k\b)"
)
_ASSERTION_RESULT_SCOPE = re.compile(
    r"(?ix)\b(?:tensile|yield|ys|ultimate|uts|elongation|ductility|"
    r"stress[\s-]*strain)\b"
)
_ASSERTION_PREPARATION_SCOPE = re.compile(
    r"(?ix)\b(?:thermal|heat|solution)\s+(?:treatment|treated)|"
    r"\b(?:anneal(?:ed|ing)?|aging|aged|sinter(?:ed|ing)?|"
    r"homogeni[sz](?:ed|ing|ation))\b"
)
_ASSERTION_MATERIAL_STATE_TEMPERATURE_SUFFIX = re.compile(
    r"(?ix)^\s*(?:[-–—,:;/]\s*)?(?:samples?|specimens?|conditions?)\b"
)
_ASSERTION_FIGURE_SPLIT_CONTINUATION = re.compile(
    r"(?ix)^\s*(?:fig(?:ure)?\.?\s*)?\d+[a-z]?\b"
)

_ASSERTION_PROPERTY_PATTERNS: tuple[tuple[str, str, re.Pattern[str]], ...] = (
    (
        "yield_strength",
        "Yield Strength",
        re.compile(
            r"(?ix)(?:\b0\.2\s*%?\s*(?:offset\s*)?yield\s+(?:strengths?|stresses?)\b|"
            r"\byield\s+(?:strengths?|stresses?)\b|\bys\b|σ\s*[_\s]?0\.2\b|"
            r"sigma\s*[_\s]?0\.2\b)"
        ),
    ),
    (
        "ultimate_tensile_strength",
        "Ultimate Tensile Strength",
        re.compile(
            r"(?ix)(?:\bultimate\s+tensile\s+strengths?\b|\buts\b|"
            r"\btensile\s+strengths?\b|σ\s*[_\s]?u\b|sigma\s*[_\s]?u\b)"
        ),
    ),
    (
        "elongation",
        "Elongation",
        re.compile(
            r"(?ix)(?:\b(?:fracture|uniform|total|tensile)\s+elongation\b|"
            r"\belongation(?:\s+(?:at|to)\s+(?:break|failure|fracture))?\b|"
            r"\bductility\b|\bel\b)"
        ),
    ),
)


@dataclass(frozen=True)
class _AssertionSegment:
    block_index: int
    sentence_index: int
    line_start: int
    line_end: int
    text: str
    previous_text: str = ""


@dataclass(frozen=True)
class _AssertionOwnerMention:
    owner_key: str
    literal: str
    start: int
    end: int


@dataclass(frozen=True)
class _AssertionValueMention:
    raw: str
    unit: str
    start: int
    end: int


def _assertion_property_family(value: str) -> tuple[str, str] | None:
    normalized = normalize_evidence_text(value)
    matches = [
        (family, canonical)
        for family, canonical, pattern in _ASSERTION_PROPERTY_PATTERNS
        if pattern.search(normalized)
    ]
    unique = list(dict.fromkeys(matches))
    return unique[0] if len(unique) == 1 else None


def _assertion_property_mentions(
    text: str,
) -> tuple[tuple[str, str, int, int], ...]:
    rows: list[tuple[str, str, int, int]] = []
    for family, canonical, pattern in _ASSERTION_PROPERTY_PATTERNS:
        rows.extend(
            (family, canonical, match.start(), match.end())
            for match in pattern.finditer(text)
        )
    rows.sort(key=lambda row: (row[2], -(row[3] - row[2]), row[0]))
    deduplicated: list[tuple[str, str, int, int]] = []
    for row in rows:
        if deduplicated and row[0] == deduplicated[-1][0] and row[2] == deduplicated[-1][2]:
            if row[3] > deduplicated[-1][3]:
                deduplicated[-1] = row
            continue
        deduplicated.append(row)
    return tuple(deduplicated)


def _assertion_numeric_tokens(value: str) -> tuple[str, ...]:
    normalized = normalize_evidence_text(value)
    return tuple(match.group(0) for match in _ASSERTION_NUMBER.finditer(normalized))


def _assertion_unit(value: str) -> str:
    normalized = normalize_evidence_text(value).replace(" ", "")
    if "%" in normalized or normalized in {"pct", "percent"}:
        return "%"
    if "gpa" in normalized:
        return "GPa"
    if "mpa" in normalized:
        return "MPa"
    return ""


def _assertion_value_mentions(text: str) -> tuple[_AssertionValueMention, ...]:
    return tuple(
        _AssertionValueMention(
            raw=match.group("value").strip(),
            unit=_assertion_unit(match.group("unit")),
            start=match.start("value"),
            end=match.end("unit"),
        )
        for match in _ASSERTION_VALUE_WITH_UNIT.finditer(text)
    )


def _assertion_result_condition(text: str) -> str:
    """Return one literal tensile-result temperature, never a prep temperature."""

    if not _ASSERTION_RESULT_SCOPE.search(text):
        return ""
    literals: list[str] = []
    for match in _ASSERTION_RESULT_TEMPERATURE.finditer(text):
        local_prefix = text[max(0, match.start() - 72) : match.start()]
        if _ASSERTION_PREPARATION_SCOPE.search(local_prefix):
            continue
        # A temperature-qualified sample label names a processing state even when
        # the preparation verb was introduced outside this bounded sentence.
        # Only an immediately following state noun is rejected; a genuine
        # result such as ``tested at 800 °C`` remains eligible.
        local_suffix = text[match.end() : match.end() + 40]
        if _ASSERTION_MATERIAL_STATE_TEMPERATURE_SUFFIX.search(local_suffix):
            continue
        literal = re.sub(r"\s+", " ", match.group(0)).strip()
        if literal and literal not in literals:
            literals.append(literal)
    return literals[0] if len(literals) == 1 else ""


def _assertion_value_matches(
    mention: _AssertionValueMention,
    *,
    value_tokens: Sequence[str],
    unit: str,
) -> bool:
    if not value_tokens or mention.unit != unit:
        return False
    return _assertion_numeric_tokens(mention.raw) == tuple(value_tokens)


def _assertion_segments(source_text: str) -> tuple[_AssertionSegment, ...]:
    raw_lines = str(source_text or "").splitlines()
    blocks: list[tuple[int, int, str]] = []
    current: list[str] = []
    start_line = 1
    for line_number, raw_line in enumerate(raw_lines, start=1):
        if raw_line.strip():
            if not current:
                start_line = line_number
            current.append(raw_line.strip())
            continue
        if current:
            blocks.append((start_line, line_number - 1, " ".join(current)))
            current = []
    if current:
        blocks.append((start_line, len(raw_lines) or start_line, " ".join(current)))
    if not blocks and str(source_text or "").strip():
        blocks.append((1, 1, str(source_text).strip()))

    result: list[_AssertionSegment] = []
    for block_index, (line_start, line_end, raw_block) in enumerate(blocks):
        normalized = normalize_evidence_text(raw_block).replace(r"\%", "%")
        if not normalized or _ASSERTION_TABLE_OR_SIDECAR.search(normalized):
            continue
        sentences = tuple(
            row.strip()
            for row in re.split(r"(?<=[.!?])\s+(?=[a-z0-9])", normalized)
            if row.strip()
        )
        for sentence_index, sentence in enumerate(sentences):
            result.append(
                _AssertionSegment(
                    block_index=block_index,
                    sentence_index=sentence_index,
                    line_start=line_start,
                    line_end=line_end,
                    text=sentence,
                    previous_text=(
                        sentences[sentence_index - 1] if sentence_index else ""
                    ),
                )
            )
    return tuple(result)


def _assertion_alias_pattern(alias: str) -> re.Pattern[str] | None:
    normalized = normalize_evidence_text(alias)
    compact = re.sub(r"[^a-z0-9]+", "", normalized)
    if len(compact) < 2 or normalized in {
        "alloy",
        "material",
        "sample",
        "samples",
        "specimen",
        "specimens",
        "target",
        "reference",
    }:
        return None
    escaped = re.escape(normalized).replace(r"\ ", r"\s+")
    return re.compile(rf"(?<![a-z0-9]){escaped}(?![a-z0-9])")


def _assertion_owner_mentions(
    text: str,
    owner_aliases: Mapping[str, Sequence[str]],
) -> tuple[_AssertionOwnerMention, ...]:
    mentions: list[_AssertionOwnerMention] = []
    for owner_key in sorted(str(key) for key in owner_aliases):
        aliases = owner_aliases.get(owner_key) or ()
        normalized_aliases = sorted(
            {
                normalize_evidence_text(alias)
                for alias in aliases
                if normalize_evidence_text(alias)
            },
            key=lambda alias: (-len(alias), alias),
        )
        for alias in normalized_aliases:
            pattern = _assertion_alias_pattern(alias)
            if pattern is None:
                continue
            mentions.extend(
                _AssertionOwnerMention(
                    owner_key=owner_key,
                    literal=match.group(0),
                    start=match.start(),
                    end=match.end(),
                )
                for match in pattern.finditer(text)
            )
    # Keep the longest alias for the same owner/start while retaining alias
    # collisions across owners as an explicit ambiguity signal.
    by_slot: dict[tuple[str, int], _AssertionOwnerMention] = {}
    for mention in mentions:
        key = (mention.owner_key, mention.start)
        prior = by_slot.get(key)
        if prior is None or mention.end > prior.end:
            by_slot[key] = mention
    contained = {
        (mention.owner_key, mention.start, mention.end, mention.literal)
        for mention in by_slot.values()
        if any(
            other.start <= mention.start
            and other.end >= mention.end
            and (other.start, other.end) != (mention.start, mention.end)
            for other in by_slot.values()
        )
    }
    return tuple(
        sorted(
            (
                mention
                for mention in by_slot.values()
                if (
                    mention.owner_key,
                    mention.start,
                    mention.end,
                    mention.literal,
                )
                not in contained
            ),
            key=lambda row: (row.start, row.end, row.owner_key, row.literal),
        )
    )


def _assertion_connected_owner_list(
    text: str,
    mentions: Sequence[_AssertionOwnerMention],
) -> bool:
    unique: list[_AssertionOwnerMention] = []
    for mention in mentions:
        if unique and mention.owner_key == unique[-1].owner_key:
            continue
        unique.append(mention)
    if len({row.owner_key for row in unique}) < 2:
        return False
    for left, right in zip(unique, unique[1:]):
        connector = text[left.end : right.start]
        if re.fullmatch(r"\s*(?:,|and|&|/|or|both|either|as\s+well\s+as)\s*", connector):
            return True
    return False


def _assertion_owner_for_value(
    text: str,
    value: _AssertionValueMention,
    owner_mentions: Sequence[_AssertionOwnerMention],
    all_values: Sequence[_AssertionValueMention],
) -> tuple[_AssertionOwnerMention | None, bool, str]:
    owners_in_order: list[_AssertionOwnerMention] = []
    seen_owner_keys: set[str] = set()
    for mention in owner_mentions:
        if mention.owner_key in seen_owner_keys:
            continue
        seen_owner_keys.add(mention.owner_key)
        owners_in_order.append(mention)

    if "respectiv" in text and len(owners_in_order) > 1:
        if len(owners_in_order) != len(all_values):
            return None, True, "ordered_owner_value_cardinality_mismatch"
        value_index = next(
            (
                index
                for index, candidate in enumerate(all_values)
                if candidate.start == value.start and candidate.end == value.end
            ),
            -1,
        )
        if value_index < 0:
            return None, True, "ordered_value_not_indexed"
        return owners_in_order[value_index], False, "ordered_owner_value"

    following = [
        mention
        for mention in owner_mentions
        if 0 <= mention.start - value.end <= 72
        and re.fullmatch(
            r"(?ix)\s*(?:(?:\(|\[)\s*|(?:for|of|in)\s+(?:the\s+)?)",
            text[value.end : mention.start],
        )
    ]
    if following:
        nearest_start = min(row.start for row in following)
        nearest = [row for row in following if row.start == nearest_start]
        keys = {row.owner_key for row in nearest}
        if len(keys) == 1:
            return max(nearest, key=lambda row: row.end), False, "following_owner"
        return None, True, "following_owner_alias_collision"

    preceding = [row for row in owner_mentions if row.end <= value.start]
    if not preceding:
        return None, False, "owner_absent"
    latest_start = max(row.start for row in preceding)
    latest = [row for row in preceding if row.start == latest_start]
    latest_keys = {row.owner_key for row in latest}
    if len(latest_keys) != 1:
        return None, True, "preceding_owner_alias_collision"
    if _assertion_connected_owner_list(text, preceding):
        # A later clause subject (``whereas A2 ...``) is a valid local owner;
        # a bare ``A1 and A2 ... value`` is a collective unresolved owner.
        selected = latest[0]
        prefix = text[max(0, selected.start - 24) : selected.start]
        if not re.search(r"(?ix)\b(?:whereas|while|but|however)\s*$", prefix):
            return None, True, "collective_owner_without_ordered_values"
    return max(latest, key=lambda row: row.end), False, "preceding_owner"


def _assertion_property_for_value(
    text: str,
    value: _AssertionValueMention,
    family: str,
    property_mentions: Sequence[tuple[str, str, int, int]],
    all_values: Sequence[_AssertionValueMention],
) -> tuple[tuple[str, str, int, int] | None, bool, str]:
    ordered_families: list[tuple[str, str, int, int]] = []
    for mention in property_mentions:
        if not ordered_families or mention[0] != ordered_families[-1][0]:
            ordered_families.append(mention)
    if "respectiv" in text and len(ordered_families) > 1:
        if len(ordered_families) != len(all_values):
            return None, True, "ordered_property_value_cardinality_mismatch"
        value_index = next(
            (
                index
                for index, candidate in enumerate(all_values)
                if candidate.start == value.start and candidate.end == value.end
            ),
            -1,
        )
        if value_index < 0:
            return None, True, "ordered_property_value_not_indexed"
        selected = ordered_families[value_index]
        return (
            (selected, False, "ordered_property_value")
            if selected[0] == family
            else (None, False, "ordered_property_belongs_to_other_family")
        )

    preceding = [
        row
        for row in property_mentions
        if row[3] <= value.start and value.start - row[3] <= 180
    ]
    if preceding:
        nearest = max(preceding, key=lambda row: (row[3], row[2]))
        if nearest[0] == family:
            return nearest, False, "direct_property_value"
        return None, False, "nearest_property_belongs_to_other_family"
    following = [
        row
        for row in property_mentions
        if row[2] >= value.end and row[2] - value.end <= 72
    ]
    if following:
        nearest = min(following, key=lambda row: (row[2], -row[3]))
        if nearest[0] == family:
            return nearest, False, "following_property_value"
    return None, False, "property_not_local"


def _assertion_key(prefix: str, payload: Mapping[str, Any]) -> str:
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return f"{prefix}:{hashlib.sha256(encoded).hexdigest()}"


def _assertion_coordinate(
    *,
    owner: _AssertionOwnerMention,
    property_row: tuple[str, str, int, int],
    value: _AssertionValueMention,
    value_raw: str,
    unit_raw: str,
    assertion_type: str,
    condition_raw: str,
    segment: _AssertionSegment,
    source_text: str,
) -> TensileAssertionCoordinate:
    bundle_payload = {
        "block_index": segment.block_index,
        "line_start": segment.line_start,
        "line_end": segment.line_end,
        "source_text": source_text,
    }
    bundle_key = _assertion_key("tensile-bundle", bundle_payload)
    coordinate_payload = {
        **bundle_payload,
        "owner_key": owner.owner_key,
        "property_family": property_row[0],
        "value_tokens": _assertion_numeric_tokens(value_raw),
        "unit": _assertion_unit(unit_raw),
        "condition": normalize_evidence_text(condition_raw),
        "owner_span": (owner.start, owner.end),
        "property_span": (property_row[2], property_row[3]),
        "value_span": (value.start, value.end),
    }
    source_coordinate_key = _assertion_key(
        "tensile-assertion", coordinate_payload
    )
    return TensileAssertionCoordinate(
        owner_key=owner.owner_key,
        owner_literal=owner.literal,
        property_family=property_row[0],
        property_name=property_row[1],
        value_raw=str(value_raw).strip(),
        unit_raw=_assertion_unit(unit_raw),
        condition_raw=str(condition_raw or "").strip(),
        assertion_type=assertion_type,
        block_index=segment.block_index,
        line_start=segment.line_start,
        line_end=segment.line_end,
        source_text=source_text,
        owner_span=(owner.start, owner.end),
        property_span=(property_row[2], property_row[3]),
        value_span=(value.start, value.end),
        bundle_key=bundle_key,
        source_coordinate_key=source_coordinate_key,
        decision_key=_assertion_key(
            "tensile-assertion-decision", coordinate_payload
        ),
    )


def resolve_tensile_assertion_coordinate(
    *,
    property_name: str,
    value_raw: str,
    unit_raw: str,
    evidence: Sequence[str],
    source_text: str,
    owner_aliases: Mapping[str, Sequence[str]],
) -> TensileAssertionDecision:
    """Resolve an existing core-tensile candidate to one literal prose owner.

    This is deliberately a validator over an already extracted candidate.  It
    does not enumerate arbitrary prose numbers or create a scientific fact.
    """

    property_contract = _assertion_property_family(property_name)
    value_tokens = _assertion_numeric_tokens(value_raw)
    unit = _assertion_unit(unit_raw)
    if property_contract is None or not value_tokens or not unit:
        return TensileAssertionDecision(
            status="not_found",
            reason="candidate_requires_core_property_numeric_value_and_unit",
        )
    family, _ = property_contract
    evidence_needles = tuple(
        normalize_evidence_text(row).replace(r"\%", "%")
        for row in evidence
        if normalize_evidence_text(row).replace(r"\%", "%")
    )
    if not evidence_needles or not source_text or not owner_aliases:
        return TensileAssertionDecision(
            status="not_found", reason="missing_source_evidence_or_owner_ledger"
        )

    coordinates: list[TensileAssertionCoordinate] = []
    ambiguity_reasons: set[str] = set()
    for segment in _assertion_segments(source_text):
        if not any(needle in segment.text for needle in evidence_needles):
            continue
        values = _assertion_value_mentions(segment.text)
        matching_values = tuple(
            row
            for row in values
            if _assertion_value_matches(
                row, value_tokens=value_tokens, unit=unit
            )
        )
        if not matching_values:
            continue
        property_mentions = _assertion_property_mentions(segment.text)
        owner_mentions = _assertion_owner_mentions(
            segment.text, owner_aliases
        )
        for value in matching_values:
            property_row, property_ambiguous, property_reason = (
                _assertion_property_for_value(
                    segment.text,
                    value,
                    family,
                    property_mentions,
                    values,
                )
            )
            if property_ambiguous:
                ambiguity_reasons.add(property_reason)
                continue
            if property_row is None:
                continue
            owner, owner_ambiguous, owner_reason = _assertion_owner_for_value(
                segment.text, value, owner_mentions, values
            )
            assertion_type = (
                "ordered"
                if property_reason.startswith("ordered")
                or owner_reason.startswith("ordered")
                else "direct"
            )
            coordinate_source = segment.text
            coordinate_segment = segment
            if owner_ambiguous:
                ambiguity_reasons.add(owner_reason)
                continue
            if owner is None and segment.previous_text and _ASSERTION_CONTINUATION.search(
                segment.text
            ):
                previous_owners = _assertion_owner_mentions(
                    segment.previous_text, owner_aliases
                )
                previous_keys = {row.owner_key for row in previous_owners}
                if len(previous_keys) == 1:
                    owner = max(
                        previous_owners, key=lambda row: (row.start, row.end)
                    )
                    assertion_type = "continuation"
                    coordinate_source = (
                        segment.previous_text + " " + segment.text
                    )
                    # Spans remain relative to their literal local sentence;
                    # the audit also preserves the joined source envelope.
                    coordinate_segment = segment
                elif previous_keys:
                    ambiguity_reasons.add("continuation_owner_ambiguous")
            elif owner is None and segment.previous_text:
                previous_owners = _assertion_owner_mentions(
                    segment.previous_text, owner_aliases
                )
                if len({row.owner_key for row in previous_owners}) > 1:
                    ambiguity_reasons.add("preceding_owner_scope_ambiguous")
            if owner is None:
                continue
            condition_raw = _assertion_result_condition(segment.text)
            if (
                not condition_raw
                and segment.previous_text
                and (
                    assertion_type == "continuation"
                    or _ASSERTION_FIGURE_SPLIT_CONTINUATION.search(segment.text)
                )
            ):
                condition_raw = _assertion_result_condition(
                    segment.previous_text
                )
                if condition_raw and not coordinate_source.startswith(
                    segment.previous_text
                ):
                    coordinate_source = (
                        segment.previous_text + " " + coordinate_source
                    )
            coordinates.append(
                _assertion_coordinate(
                    owner=owner,
                    property_row=property_row,
                    value=value,
                    value_raw=value_raw,
                    unit_raw=unit_raw,
                    assertion_type=assertion_type,
                    condition_raw=condition_raw,
                    segment=coordinate_segment,
                    source_text=coordinate_source,
                )
            )

    coordinates.sort(
        key=lambda row: (
            row.block_index,
            row.line_start,
            row.owner_key,
            row.property_family,
            row.source_coordinate_key,
        )
    )
    unique_coordinates = {
        row.source_coordinate_key: row for row in coordinates
    }
    candidates = tuple(unique_coordinates[key] for key in sorted(unique_coordinates))
    scientific_owners = {row.owner_key for row in candidates}
    if len(scientific_owners) == 1 and candidates:
        selected = min(
            candidates,
            key=lambda row: (
                row.block_index,
                row.line_start,
                row.source_coordinate_key,
            ),
        )
        return TensileAssertionDecision(
            status="matched",
            coordinate=selected,
            candidates=candidates,
            reason="one_source_literal_owner_property_value_unit_coordinate",
        )
    if len(scientific_owners) > 1 or ambiguity_reasons:
        return TensileAssertionDecision(
            status="ambiguous",
            candidates=candidates,
            reason=";".join(sorted(ambiguity_reasons))
            or "multiple_source_owner_coordinates",
        )
    return TensileAssertionDecision(
        status="not_found",
        candidates=candidates,
        reason="no_source_literal_owner_property_value_unit_coordinate",
    )
