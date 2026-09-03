"""Generic source-only evidence and axis task planning for alpha25."""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field, replace
from typing import Iterable, Literal, Mapping, Sequence

from bs4 import BeautifulSoup

from knowmat.alpha25.materialize import is_plausible_material_identity
from knowmat.alpha25.prompt_compiler import Axis


EvidenceKind = Literal["prose", "table", "caption"]

_TABLE_SEPARATOR = re.compile(r"^\s*\|?(?:\s*:?-{3,}:?\s*\|)+\s*:?-{3,}:?\s*\|?\s*$")
_CAPTION = re.compile(r"^\s*(?:table|fig(?:ure)?)[\s.]*\d+\b", re.IGNORECASE)
_INVENTORY_LABEL = re.compile(
    r"(?i:\b(?:sample|specimen|alloy|material|condition|batch|group)s?\s+)"
    r"(?i:(?:designated|denoted|labelled)\s+(?:as\s+)?)?"
    r"[\"'(]?([A-Z0-9][A-Za-z0-9_.+\-/]{0,30})"
)
_EXPLICIT_INVENTORY_LABEL = re.compile(
    r"(?i:\b(?:sample|specimen|alloy|material|condition|batch|group)s?\s+)"
    r"(?i:(?:designated|denoted|labelled)\s+(?:as\s+)?)"
    r"[\"'(]?([A-Za-z0-9][A-Za-z0-9_.+\-/]{0,30})"
)
_REVERSE_INVENTORY_LABEL = re.compile(
    r"\b([A-Z][A-Z0-9_.+\-/]{1,30})\s+(?:samples?|specimens?|alloys?|materials?)\b"
)
_ROW_SAMPLE_HEADER = re.compile(
    r"(?i)^(?:(?:sample|specimen|alloy|material|condition|state|batch|group|"
    r"designation|label|code|process|route|treatment)(?:\s+(?:id|name|code))?"
    r"|step\s+purpose)$"
)
_FEEDSTOCK_OWNER = re.compile(
    r"(?i)^\s*([A-Za-z][A-Za-z0-9_.+\-/]{1,30})\s+feedstocks?\b"
)
_COMPACT_SAMPLE_CODE = re.compile(r"^(?:#\s*\d+|\d+(?:[-_]\d+)+)$")
_PROSE_COMPACT_SAMPLE_CODE = re.compile(
    r"(?<![A-Za-z0-9])(?:#\s*\d+|\d+(?:[-_]\d+)+)(?![A-Za-z0-9])"
)
_STATE_TABLE_LABEL = re.compile(
    r"(?i)^(?=.*\d)(?=.*\b(?:delay|dwell|hold|aged?|anneal(?:ed|ing)?|"
    r"heat[\s-]*treat(?:ed|ment)?|sinter(?:ed|ing)?|solution(?:ized|ing)?|"
    r"temperature|orientation|direction|condition|state|region)\b).{1,80}$"
)
_QUALITATIVE_STATE_TABLE_LABEL = re.compile(
    r"(?i)^(?:as[\s-]*(?:built|printed|fabricated|deposited|received|sintered|cast)|"
    r"aged|annealed|heat[\s-]*treated|solution[\s-]*treated|sintered|cured|"
    r"powder|feedstock|wrought|cast|hot[\s-]*isostatic(?:ally)?[\s-]*pressed|HIP\d*)$"
)
_ORIENTED_SAMPLE_LABEL = re.compile(
    r"(?i)^(?:(?:waam|ebam|webam|wlam|lpbf|epbf|pbf|slm|ebm|ded|bj|binder\s+jetting)"
    r"(?:\s*[/_-]\s*|\s+))?(?:horizontal|vertical|longitudinal|transverse|x|y|z)"
    r"(?:[\s-]+(?:sample|orientation|direction))?$"
)
_MATERIAL_OR_STATE_COLUMN_LABEL = re.compile(
    r"(?i)^(?:wall\s*#?\d+|(?:single|multi)[\s-]*wall\s*#?\d+|"
    r"(?:waam|ebam|webam|wlam|lpbf|epbf|pbf|slm|ebm|ded|bj|binder\s+jetting)|"
    r"(?:as[\s-]*)?(?:wrought|cast)(?:\s+.+)?|.+\s+(?:alloy|material|powder|feedstock))$"
)
_ALPHANUMERIC_SAMPLE_CODE = re.compile(
    r"^(?=.*[A-Za-z])(?=.*\d)[A-Za-z0-9_.+#/-]{2,30}$"
)
_STATE_DIMENSION_EXCLUSION = re.compile(
    r"(?i)\b(?:test(?:ing)?|tensile|creep|fatigue|measurement|measuring|"
    r"characteri[sz](?:ation|ing)|analysis)\b"
)
_STATE_DIMENSION_MARKER = re.compile(
    r"(?i)\b(?:temperature|temp\.?|time|duration|pressure|condition|state)\b"
)
_STATE_CHANGING_PROCESS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"(?i)\bsolution(?:\s+heat)?[\s-]*treat(?:ment|ing|ed)?\b"), "solution treated"),
    (re.compile(r"(?i)\bheat[\s-]*treat(?:ment|ing|ed)?\b"), "heat treated"),
    (re.compile(r"(?i)\bhot[\s-]*isostatic(?:ally)?[\s-]*press(?:ing|ed)?\b|\bHIP\b"), "HIP"),
    (re.compile(r"(?i)\bsinter(?:ing|ed)?\b"), "sintered"),
    (re.compile(r"(?i)\b(?:ageing|aging|aged?)\b"), "aged"),
    (re.compile(r"(?i)\banneal(?:ing|ed)?\b"), "annealed"),
    (re.compile(r"(?i)\bhomogeni[sz](?:ation|ing|ed)?\b"), "homogenized"),
    (re.compile(r"(?i)\btemper(?:ing|ed)?\b"), "tempered"),
    (re.compile(r"(?i)\bcur(?:e|ed|ing)\b"), "cured"),
)
_MATERIAL_SERIES_CONTEXT = re.compile(
    r"(?i)\b(?:sample|specimen|alloy|material|powder|feedstock|part|coupon)s?\b"
)
_STANDARD_IDENTIFIER = re.compile(
    r"(?i)\b(?:ASTM|ISO|DIN|JIS|ANSI|EN)\s*[A-Z]*[\s-]*\d"
)

_AXIS_PATTERNS: dict[Axis, re.Pattern[str]] = {
    "composition": re.compile(
        r"\b(?:composition|alloying|chemical|wt\.?\s*%|at\.?\s*%|vol\.?\s*%|"
        r"ppm|eds|edx|xrf|icp(?:-oes)?|element(?:al)?|feedstock|powder chemistry)\b",
        re.IGNORECASE,
    ),
    "processing": re.compile(
        r"\b(?:fabricat(?:e|ed|ion)|manufactur(?:e|ed|ing)|process(?:ed|ing)?|anneal(?:ed|ing)?|"
        r"ag(?:e|ed|ing)|ageing|solution treat|heat treat|sinter(?:ed|ing)?|cast(?:ing)?|"
        r"forg(?:e|ed|ing)|roll(?:ed|ing)?|extrud(?:e|ed|ing)|hip(?:ed|ing)?|"
        r"lpbf|pbf|slm|ebm|ded|waam|laser power|scan(?:ning)? speed|hatch|layer thickness)\b",
        re.IGNORECASE,
    ),
    "structure": re.compile(
        r"\b(?:microstructure|structure|phase|grain|precipitat|porosity|pore|texture|"
        r"dislocation|twin|fracture surface|morpholog|sem|tem|stem|ebsd|eds|edx|"
        r"xrd|apt|afm|bse|optical microscop|microscop|tomograph|spectroscop|"
        r"diffraction|raman|imagej)\b",
        re.IGNORECASE,
    ),
    "properties": re.compile(
        r"\b(?:propert(?:y|ies)|strength|yield|uts|elongation|ductility|hardness|fatigue|"
        r"creep|fracture toughness|modulus|density|corrosion|wear|conductivity|resistivity|"
        r"tensile|compression|impact|stress rupture)\b",
        re.IGNORECASE,
    ),
}
_STRUCTURE_TABLE_METRIC = re.compile(
    r"(?i)(?:\b(?:grain|pore|particle|precipitate|dendrite|crystallite)\s+"
    r"(?:size|diameter|radius|spacing|fraction)\b|\bporosity\b|"
    r"\bdislocation\s+density\b|\bphase\s+fraction\b)"
)
_MEASUREMENT_SIGNAL = re.compile(
    r"(?i)(?:[<>\u2264\u2265~\u2248]?\s*[-+]?\d+(?:\.\d+)?(?:\s*(?:\u00b1|\+/-)\s*\d+(?:\.\d+)?)?"
    r"\s*(?:wt\.?\s*%|at\.?\s*%|vol\.?\s*%|mol\.?\s*%|ppm|ppb|"
    r"gpa|mpa|kpa|pa|hv|hrc|gj\s*m\^?-?2|mj\s*m\^?-?2|j\s*m\^?-?2|"
    r"\u00b0?\s*c|k|h|hr|hrs|min|s|ms|hz|khz|mhz|w|kw|v|mv|a|ma|"
    r"mm|cm|nm|um|\u00b5m|\u03bcm|m/s|mm/s|kg/m3|g/cm3|%))"
)
_FACT_SIGNAL_SPAN = re.compile(r"(?<=[.!?;])\s+|\n+")


def _split_markdown_row(line: str) -> list[str] | None:
    raw = line.strip()
    if "|" not in raw:
        return None
    cells: list[str] = []
    current: list[str] = []
    escaped = False
    for char in raw:
        if char == "|" and not escaped:
            cells.append("".join(current).strip())
            current = []
        else:
            current.append(char)
        escaped = char == "\\" and not escaped
        if char != "\\":
            escaped = False
    cells.append("".join(current).strip())
    if raw.startswith("|") and cells and not cells[0]:
        cells.pop(0)
    if raw.endswith("|") and cells and not cells[-1]:
        cells.pop()
    return cells if len(cells) >= 2 else None


def _render_row(cells: Sequence[str]) -> str:
    return "| " + " | ".join(cells) + " |"


def _is_row_sample_header(value: str) -> bool:
    folded = re.sub(r"[^a-z0-9]+", " ", str(value or "").casefold()).strip()
    return bool(_ROW_SAMPLE_HEADER.fullmatch(folded))


def _is_plausible_table_anchor(value: str) -> bool:
    """Accept a source table's explicit item/state label without guessing facts."""

    text = re.sub(r"\s+", " ", str(value or "")).strip().strip("|,;:")
    if not text or len(text) > 120:
        return False
    folded = re.sub(r"[^a-z0-9]+", " ", text.casefold()).strip()
    if folded in {"comment", "comments", "note", "notes", "remark", "remarks"}:
        return False
    # Bare coefficient columns (A/B/C/D) are common in scientific tables and
    # are not safe item identities without an explicit Sample/Material header.
    if re.fullmatch(r"[A-Za-z]", text):
        return False
    if is_plausible_material_identity(text):
        return True
    return bool(_COMPACT_SAMPLE_CODE.fullmatch(text) or _STATE_TABLE_LABEL.fullmatch(text))


def _row_sample_column(
    header: Sequence[str], rows: Sequence[Sequence[str]]
) -> int | None:
    """Locate a row-oriented sample-ID column, including multi-row HTML headers."""

    candidates: list[int] = []
    for index, value in enumerate(header):
        folded = re.sub(r"[^a-z0-9]+", " ", str(value or "").casefold()).strip()
        explicit_sample_number = bool(
            re.search(r"\bsample\s+(?:number|no|id|code|name)\b", folded)
        )
        # A test ``specimen number`` identifies a coupon/row, not a material.
        # Ambiguous suffixes such as ``Horizontal sample`` are column states,
        # not row-ID headers. They are handled by column-anchor inference.
        if not folded.startswith("specimen") and (
            _is_row_sample_header(folded) or explicit_sample_number
        ):
            candidates.append(index)
    if not candidates:
        return None

    def score(index: int) -> tuple[float, int, int, int]:
        values = [
            str(row[index]).strip()
            for row in rows
            if index < len(row) and str(row[index]).strip()
        ]
        if not values:
            return (-1.0, -1, -1, -index)
        unique_ratio = len(set(values)) / len(values)
        coded = sum(bool(_COMPACT_SAMPLE_CODE.fullmatch(value)) for value in values)
        plausible = sum(_is_plausible_table_anchor(value) for value in values)
        # Prefer the most discriminating source-code column. This selects the
        # actual ``1-1`` column over a repeated iteration-number column when a
        # merged HTML header labels both as "Iteration and Sample Number".
        return (unique_ratio, coded, plausible, -index)

    return max(candidates, key=score)


def _is_explicit_column_anchor(value: str) -> bool:
    """Return true for a header that itself denotes a material/state column."""

    text = re.sub(r"\s+", " ", str(value or "")).strip().strip("|,;:")
    if not text or re.fullmatch(r"[+-]?(?:\d+(?:\.\d+)?|\.\d+)", text):
        return False
    if not _is_plausible_table_anchor(text):
        return False
    return bool(
        _COMPACT_SAMPLE_CODE.fullmatch(text)
        or _ALPHANUMERIC_SAMPLE_CODE.fullmatch(text)
        or _STATE_TABLE_LABEL.fullmatch(text)
        or _QUALITATIVE_STATE_TABLE_LABEL.fullmatch(text)
        or _ORIENTED_SAMPLE_LABEL.fullmatch(text)
        or _MATERIAL_OR_STATE_COLUMN_LABEL.fullmatch(text)
        or _FEEDSTOCK_OWNER.match(text)
    )


def _inferred_row_sample_column(
    header: Sequence[str], rows: Sequence[Sequence[str]]
) -> int | None:
    """Infer first-column material states only from a strong state/value layout."""

    if not header or not rows:
        return None
    first_header = re.sub(
        r"[^a-z0-9]+", " ", str(header[0] or "").casefold()
    ).strip()
    if re.search(
        r"\b(?:crack|defect|location|parameter|property|metric|phase|element|reference)\b",
        first_header,
    ):
        return None
    labels = [str(row[0]).strip() for row in rows if row and str(row[0]).strip()]
    if len(labels) < 2 or not all(
        _QUALITATIVE_STATE_TABLE_LABEL.fullmatch(label)
        or _STATE_TABLE_LABEL.fullmatch(label)
        or _MATERIAL_OR_STATE_COLUMN_LABEL.fullmatch(label)
        or _COMPACT_SAMPLE_CODE.fullmatch(label)
        or _ALPHANUMERIC_SAMPLE_CODE.fullmatch(label)
        for label in labels
    ):
        return None
    value_cells = [
        str(cell).strip()
        for row in rows
        for cell in row[1:]
        if str(cell).strip()
    ]
    numeric = sum(bool(re.search(r"[-+]?\d", cell)) for cell in value_cells)
    return 0 if value_cells and numeric / len(value_cells) >= 0.6 else None


def _is_relation_matrix(header: Sequence[str], rows: Sequence[Sequence[str]]) -> bool:
    """Recognize a labelled square/near-square relation table, not sample columns."""

    if not header or str(header[0]).strip() or len(header) < 4 or len(rows) < 3:
        return False
    column_labels = {
        re.sub(r"\W+", "", str(value).casefold())
        for value in header[1:]
        if str(value).strip()
    }
    row_labels = {
        re.sub(r"\W+", "", str(row[0]).casefold())
        for row in rows
        if row and str(row[0]).strip()
    }
    if not column_labels or not row_labels:
        return False
    overlap = len(column_labels & row_labels)
    return overlap >= 3 and overlap / min(len(column_labels), len(row_labels)) >= 0.6


def _table_anchor_label(value: str) -> str:
    text = str(value or "").strip()
    owner = _FEEDSTOCK_OWNER.match(text)
    return owner.group(1) if owner else text


def _unit_id(kind: str, start_line: int, end_line: int, text: str, suffix: str = "") -> str:
    digest = hashlib.sha256(text.encode("utf-8")).hexdigest()[:12]
    ending = f"-{suffix}" if suffix else ""
    return f"{kind}-L{start_line:06d}-L{end_line:06d}-{digest}{ending}"


@dataclass(frozen=True)
class TableStateAnchor:
    """A source-derived material-series/state pair from one table projection."""

    sample_id_raw: str
    state_raw: str
    source_evidence: tuple[str, ...]


@dataclass(frozen=True)
class EvidenceUnit:
    unit_id: str
    kind: EvidenceKind
    text: str
    start_line: int
    end_line: int
    axes: tuple[Axis, ...]
    source_text: str = ""
    sample_anchors: tuple[str, ...] = ()
    state_anchors: tuple[TableStateAnchor, ...] = ()
    parent_unit_id: str | None = None
    split_depth: int = 0
    metadata: dict[str, object] = field(default_factory=dict)


@dataclass(frozen=True)
class AxisTask:
    task_id: str
    unit_id: str
    axis: Axis
    evidence_text: str
    source_text: str
    output_token_budget: int
    kind: EvidenceKind = "prose"
    sample_anchors: tuple[str, ...] = ()
    state_anchors: tuple[TableStateAnchor, ...] = ()
    parent_task_id: str | None = None
    split_depth: int = 0


def classify_axes(text: str) -> tuple[Axis, ...]:
    """Return only axes with explicit lexical signals in one evidence unit."""

    axes = tuple(axis for axis, pattern in _AXIS_PATTERNS.items() if pattern.search(text))
    return axes


def fact_signal_score(text: str) -> int:
    """Estimate response density without using paper/material-specific rules.

    The score is deliberately source-only: each sentence/line contributes for
    the generic extraction axes it mentions and for explicit numeric-unit
    measurements.  It is used only to choose a safe evidence capacity; it
    never decides whether a fact exists and therefore cannot remove coverage.
    """

    score = 0
    for span in _FACT_SIGNAL_SPAN.split(str(text or "")):
        cleaned = span.strip()
        if not cleaned:
            continue
        score += len(classify_axes(cleaned))
        score += min(3, len(_MEASUREMENT_SIGNAL.findall(cleaned)))
    return score


def _inventory_candidate_labels(unit: EvidenceUnit) -> tuple[str, ...]:
    """Return source labels that caused a prose unit to need item discovery."""

    explicit = _EXPLICIT_INVENTORY_LABEL.findall(unit.text)
    candidates = [
        *(_INVENTORY_LABEL.findall(unit.text)),
        *(_REVERSE_INVENTORY_LABEL.findall(unit.text)),
    ]
    stopwords = {
        "the",
        "this",
        "that",
        "was",
        "were",
        "is",
        "are",
        "with",
        "without",
        "design",
        "science",
        "figure",
        "fig.",
        "table",
        "composition",
        "compositions",
        "fabrication",
        "fabricated",
        "processed",
        "produced",
        "reported",
        "powder",
        "powders",
    }
    method_or_process_acronyms = {
        "AM",
        "DED",
        "EBM",
        "EBSD",
        "EDS",
        "EDX",
        "LPBF",
        "PBF",
        "SEM",
        "SLM",
        "TEM",
        "TE",
        "UEL",
        "UTS",
        "XRD",
        "YS",
    }

    def clean(label: str) -> str:
        return str(label).strip().strip("\"'()[]{}.,;:")

    def explicit_label(label: str) -> bool:
        value = clean(label)
        return bool(value) and value.casefold() not in stopwords

    def source_code(label: str) -> bool:
        value = clean(label)
        if not value or value.casefold() in stopwords:
            return False
        if value.upper() in method_or_process_acronyms:
            return False
        if any(char.isdigit() for char in value):
            return True
        return value.isupper() and 1 <= len(value) <= 20

    labels = [clean(label) for label in explicit if explicit_label(label)]
    labels.extend(clean(label) for label in candidates if source_code(label))
    # Preserve the original conservative inventory trigger: compact codes in
    # ordinary prose only expand an already-triggered label list. They must not
    # make every numeric range/figure reference into a new inventory task.
    if not labels:
        return ()
    for match in _PROSE_COMPACT_SAMPLE_CODE.finditer(unit.text):
        prefix = unit.text[max(0, match.start() - 32) : match.start()]
        if re.search(
            r"(?i)(?:fig(?:ure)?s?|table|note)\.?\s*$",
            prefix,
        ):
            continue
        labels.append(clean(match.group(0)))
    return tuple(dict.fromkeys(label for label in labels if label))


def _inventory_label_key(value: str) -> str:
    return re.sub(r"\s+", "", str(value or "").strip().casefold())


def needs_inventory(unit: EvidenceUnit) -> bool:
    """Use an inventory call only where the source appears to name item labels."""

    if unit.sample_anchors:
        return False
    return bool(_inventory_candidate_labels(unit))


def _paragraph_units(
    lines: Sequence[str],
    included: Sequence[bool],
    *,
    max_chars: int,
) -> list[EvidenceUnit]:
    units: list[EvidenceUnit] = []
    buffer: list[tuple[int, str]] = []
    buffer_chars = 0

    def flush() -> None:
        nonlocal buffer, buffer_chars
        if not buffer:
            return
        text = "\n".join(line for _, line in buffer).strip()
        if text:
            start = buffer[0][0]
            end = buffer[-1][0]
            axes = classify_axes(text)
            if axes:
                units.append(
                    EvidenceUnit(
                        unit_id=_unit_id("prose", start, end, text),
                        kind="prose",
                        text=text,
                        source_text=text,
                        start_line=start,
                        end_line=end,
                        axes=axes,
                    )
                )
        buffer = []
        buffer_chars = 0

    for index, line in enumerate(lines, start=1):
        if not included[index - 1]:
            flush()
            continue
        projected = buffer_chars + len(line) + 1
        is_heading = bool(re.match(r"^\s*#{1,6}\s+", line))
        if buffer and (projected > max_chars or is_heading):
            flush()
        buffer.append((index, line))
        buffer_chars += len(line) + 1
        if not line.strip() and buffer_chars >= max_chars // 2:
            flush()
    flush()
    return units


def _table_blocks(lines: Sequence[str]) -> list[tuple[int, int, list[list[str]]]]:
    blocks: list[tuple[int, int, list[list[str]]]] = []
    index = 0
    while index + 2 < len(lines):
        if not _TABLE_SEPARATOR.match(lines[index + 1]):
            index += 1
            continue
        header = _split_markdown_row(lines[index])
        separator = _split_markdown_row(lines[index + 1])
        if not header or not separator or len(header) != len(separator):
            index += 1
            continue
        rows = [header, separator]
        cursor = index + 2
        while cursor < len(lines):
            row = _split_markdown_row(lines[cursor])
            if not row or len(row) != len(header):
                break
            rows.append(row)
            cursor += 1
        if len(rows) >= 3:
            blocks.append((index, cursor, rows))
            index = cursor
        else:
            index += 1
    return blocks


def _html_grid(table: object) -> list[list[str]]:
    """Expand rowspan/colspan into a rectangular source-text grid."""

    rows: list[list[str]] = []
    spans: dict[int, tuple[int, str]] = {}
    for tr in table.find_all("tr"):  # type: ignore[attr-defined]
        row: list[str] = []
        column = 0

        def consume_span() -> None:
            nonlocal column
            remaining, value = spans[column]
            row.append(value)
            if remaining <= 1:
                del spans[column]
            else:
                spans[column] = (remaining - 1, value)
            column += 1

        for cell in tr.find_all(["th", "td"], recursive=False):
            while column in spans:
                consume_span()
            text = re.sub("\\s+", " ", cell.get_text(" ", strip=True)).strip()
            try:
                colspan = max(1, int(cell.get("colspan") or 1))
            except (TypeError, ValueError):
                colspan = 1
            try:
                rowspan = max(1, int(cell.get("rowspan") or 1))
            except (TypeError, ValueError):
                rowspan = 1
            for _ in range(colspan):
                row.append(text)
                if rowspan > 1:
                    spans[column] = (rowspan - 1, text)
                column += 1
        while column in spans:
            consume_span()
        if row:
            rows.append(row)
    width = max((len(row) for row in rows), default=0)
    return [row + [""] * (width - len(row)) for row in rows]


def _html_header_and_rows(grid: Sequence[Sequence[str]]) -> tuple[list[str], list[list[str]]]:
    """Combine leading HTML header rows without treating them as measurements."""

    if not grid:
        return [], []

    def looks_like_data_row(row: Sequence[str]) -> bool:
        populated = [str(cell).strip() for cell in row if str(cell).strip()]
        if not populated:
            return False
        numeric_cells = sum(
            bool(re.search(r"\d", cell)) and not _STANDARD_IDENTIFIER.search(cell)
            for cell in populated
        )
        ratio = numeric_cells / len(populated)
        # Multi-level scientific headers may contain numeric method or plane
        # identifiers (ASTM E-112-13, 111/200/220/311). A real body row is
        # normally numeric in a majority of its populated cells. Preserve the
        # two-column label/value case, where one numeric cell is sufficient.
        return numeric_cells >= 1 and (
            ratio > 0.5 or (len(populated) <= 2 and ratio >= 0.5)
        )

    first_data = 1
    for index, row in enumerate(grid[1:], start=1):
        if looks_like_data_row(row):
            first_data = index
            break
    else:
        first_data = 1
    header_rows = grid[:first_data]
    width = max(len(row) for row in grid)
    header: list[str] = []
    for column in range(width):
        parts: list[str] = []
        for row in header_rows:
            value = str(row[column] if column < len(row) else "").strip()
            if value and value not in parts:
                parts.append(value)
        header.append(" / ".join(parts))
    return header, [list(row) for row in grid[first_data:]]


def _caption_text(value: str) -> str:
    """Return visible caption text while keeping source fragments untouched."""

    return re.sub(
        r"\s+",
        " ",
        BeautifulSoup(str(value or ""), "lxml").get_text(" ", strip=True),
    ).strip()


def _caption_supports_series_label(caption: str, label: str) -> bool:
    """Require a header label and nearby caption material semantics."""

    visible = _caption_text(caption)
    candidate = re.sub(r"\s+", " ", str(label or "")).strip()
    if not visible or not candidate:
        return False
    boundary = rf"(?<![A-Za-z0-9]){re.escape(candidate)}(?![A-Za-z0-9])"
    for match in re.finditer(boundary, visible, flags=re.IGNORECASE):
        context = visible[max(0, match.start() - 120) : match.end() + 120]
        if _MATERIAL_SERIES_CONTEXT.search(context):
            return True
    return False


def _header_series_labels(header_path: str, caption: str) -> tuple[str, ...]:
    """Extract only caption-confirmed material-series labels from a header path."""

    labels: list[str] = []
    for part in (
        re.sub(r"\s+", " ", value).strip()
        for value in str(header_path or "").split(" / ")
    ):
        if not part:
            continue
        candidates = [part]
        candidates.extend(
            match.group(0)
            for match in re.finditer(
                r"(?<![A-Za-z0-9])[A-Z][A-Z0-9_.+/-]{0,19}(?![A-Za-z0-9])",
                part,
            )
        )
        for candidate in candidates:
            cleaned = candidate.strip().strip("|,;:")
            if (
                cleaned
                and not _STANDARD_IDENTIFIER.search(cleaned)
                and _caption_supports_series_label(caption, cleaned)
            ):
                labels.append(_table_anchor_label(cleaned))
    return tuple(dict.fromkeys(labels))


def _state_dimension_unit(header: str) -> str:
    text = str(header or "")
    if re.search(r"(?i)(?:\\circ\s*\}?\s*C|°\s*C|deg(?:ree)?s?\s*C)", text):
        return "°C"
    if re.search(r"(?i)(?:\\circ\s*\}?\s*F|°\s*F|deg(?:ree)?s?\s*F)", text):
        return "°F"
    for pattern, unit in (
        (r"(?i)(?:\[|\(|\b)K(?:\]|\)|\b)", "K"),
        (r"(?i)(?:\[|\(|\b)(?:hours?|hrs?|h)(?:\]|\)|\b)", "h"),
        (r"(?i)(?:\[|\(|\b)(?:minutes?|mins?|min)(?:\]|\)|\b)", "min"),
        (r"(?i)(?:\[|\(|\b)(?:seconds?|secs?|s)(?:\]|\)|\b)", "s"),
        (r"(?i)(?:\[|\(|\b)MPa(?:\]|\)|\b)", "MPa"),
    ):
        if re.search(pattern, text):
            return unit
    return ""


def _state_from_dimension(header: str, raw_value: str) -> str | None:
    """Compose a state qualifier only from an explicit changing-process dimension."""

    dimension = re.sub(r"\s+", " ", str(header or "")).strip()
    value = re.sub(r"\s+", " ", str(raw_value or "")).strip().strip("|,;:")
    if (
        not dimension
        or not value
        or not re.search(r"\d", value)
        or len(value) > 80
        or _STATE_DIMENSION_EXCLUSION.search(dimension)
        or not _STATE_DIMENSION_MARKER.search(dimension)
    ):
        return None
    process = next(
        (name for pattern, name in _STATE_CHANGING_PROCESS if pattern.search(dimension)),
        None,
    )
    if process is None:
        return None
    unit = _state_dimension_unit(dimension)
    if unit and unit.casefold() not in value.casefold():
        value = f"{value} {unit}"
    preposition = "for" if re.search(r"(?i)\b(?:time|duration)\b", dimension) else "at"
    return f"{process} {preposition} {value}"


def _table_state_anchors(
    header: Sequence[str],
    selected_columns: Sequence[int],
    selected_rows: Sequence[Sequence[str]],
    *,
    caption: str,
    row_sample_column: int | None,
    relation_matrix: bool,
) -> tuple[TableStateAnchor, ...]:
    """Cross a state-changing row dimension with caption-backed material series."""

    if relation_matrix or row_sample_column is not None or not header:
        return ()
    dimension_header = str(header[0] or "").strip()
    series = tuple(
        dict.fromkeys(
            label
            for index in selected_columns
            for label in _header_series_labels(str(header[index]), caption)
        )
    )
    if not series:
        return ()
    anchors: list[TableStateAnchor] = []
    for row in selected_rows:
        if not row:
            continue
        raw_value = str(row[0] or "").strip()
        state = _state_from_dimension(dimension_header, raw_value)
        if state is None:
            continue
        for label in series:
            anchors.append(
                TableStateAnchor(
                    sample_id_raw=label,
                    state_raw=state,
                    source_evidence=tuple(
                        dict.fromkeys((label, dimension_header, raw_value))
                    ),
                )
            )
    return tuple(dict.fromkeys(anchors))


def _html_table_blocks(lines: Sequence[str]) -> list[tuple[int, int, list[list[str]]]]:
    blocks: list[tuple[int, int, list[list[str]]]] = []
    index = 0
    while index < len(lines):
        if "<table" not in lines[index].casefold():
            index += 1
            continue
        start = index
        html_lines = [lines[index]]
        while "</table>" not in "\n".join(html_lines).casefold() and index + 1 < len(lines):
            index += 1
            html_lines.append(lines[index])
        end = index + 1
        soup = BeautifulSoup("\n".join(html_lines), "lxml")
        table = soup.find("table")
        if table is not None:
            header, data_rows = _html_header_and_rows(_html_grid(table))
            if header and data_rows and all(len(row) == len(header) for row in data_rows):
                blocks.append((start, end, [header, ["---"] * len(header), *data_rows]))
        index += 1
    return blocks


def _table_units(
    lines: Sequence[str],
    blocks: Sequence[tuple[int, int, list[list[str]]]],
    *,
    columns_per_unit: int,
    rows_per_unit: int,
    context_chars: int,
    structure_cells_per_unit: int,
    cells_per_unit: int,
    minimum_columns_per_unit: int,
    max_chars_per_unit: int,
) -> list[EvidenceUnit]:
    units: list[EvidenceUnit] = []
    for table_index, (start, end, rows) in enumerate(blocks, start=1):
        header = rows[0]
        data_rows = rows[2:]
        relation_matrix = _is_relation_matrix(header, data_rows)
        structure_metric_table = bool(
            _STRUCTURE_TABLE_METRIC.search(" ".join(str(cell) for cell in header))
        )
        caption_lines: list[str] = []
        cursor = start - 1
        while cursor >= 0 and len("\n".join(reversed(caption_lines))) < context_chars:
            line = lines[cursor]
            if not line.strip() and caption_lines:
                break
            caption_lines.append(line)
            cursor -= 1
        caption = "\n".join(reversed(caption_lines)).strip()
        after_lines: list[str] = []
        cursor = end
        while cursor < len(lines) and len("\n".join(after_lines)) < context_chars:
            line = lines[cursor]
            if not line.strip() and after_lines:
                break
            after_lines.append(line)
            cursor += 1
        after = "\n".join(after_lines).strip()

        row_sample_column = _row_sample_column(header, data_rows)
        if row_sample_column is None:
            row_sample_column = _inferred_row_sample_column(header, data_rows)
        sample_columns = [
            index for index in range(len(header)) if index != row_sample_column
        ]
        if row_sample_column is None and sample_columns and sample_columns[0] == 0:
            sample_columns = sample_columns[1:]
        if not sample_columns:
            sample_columns = [row_sample_column if row_sample_column is not None else 0]
        effective_rows = (
            len(data_rows) if relation_matrix else max(1, rows_per_unit)
        )
        rows_for_column_capacity = max(
            1, min(len(data_rows), effective_rows)
        )
        legacy_column_floor = min(
            len(sample_columns),
            max(1, columns_per_unit),
            max(1, minimum_columns_per_unit),
        )
        columns_by_cell_capacity = max(
            legacy_column_floor,
            max(1, cells_per_unit) // rows_for_column_capacity,
        )
        effective_columns = min(
            len(sample_columns),
            (
                len(sample_columns)
                if relation_matrix
                else max(1, columns_per_unit)
            ),
            columns_by_cell_capacity,
        )

        def projection_text(
            selected_columns: Sequence[int],
            selected_rows: Sequence[Sequence[str]],
        ) -> str:
            identity_column = row_sample_column if row_sample_column is not None else 0
            selected_indices = list(
                dict.fromkeys([identity_column, *selected_columns])
            )
            table_lines = [
                _render_row([header[index] for index in selected_indices]),
                _render_row(["---" for _ in selected_indices]),
                *[
                    _render_row([row[index] for index in selected_indices])
                    for row in selected_rows
                ],
            ]
            return "\n\n".join(
                part for part in (caption, "\n".join(table_lines), after) if part
            )

        column_offset = 0
        while column_offset < len(sample_columns):
            column_width = min(
                effective_columns,
                len(sample_columns) - column_offset,
            )
            # Text-heavy cells can exceed the context bound even when their cell
            # count is small. Narrow the whole column slice until every one-row
            # projection fits; row packing below then preserves the same bound.
            while column_width > 1:
                candidate_columns = sample_columns[
                    column_offset : column_offset + column_width
                ]
                if max(
                    len(projection_text(candidate_columns, [row]))
                    for row in data_rows
                ) <= max_chars_per_unit:
                    break
                column_width -= 1
            columns = sample_columns[column_offset : column_offset + column_width]
            bounded_rows = effective_rows
            if not relation_matrix and len(columns) > legacy_column_floor:
                bounded_rows = min(
                    bounded_rows,
                    max(1, max(1, cells_per_unit) // max(1, len(columns))),
                )
            if structure_metric_table and not relation_matrix:
                bounded_rows = min(
                    bounded_rows,
                    max(
                        1,
                        max(1, structure_cells_per_unit) // max(1, len(columns)),
                    ),
                )
            row_offset = 0
            while row_offset < len(data_rows):
                row_count = min(bounded_rows, len(data_rows) - row_offset)
                selected_rows = data_rows[row_offset : row_offset + row_count]
                text = projection_text(columns, selected_rows)
                while len(text) > max_chars_per_unit and row_count > 1:
                    row_count -= 1
                    selected_rows = data_rows[row_offset : row_offset + row_count]
                    text = projection_text(columns, selected_rows)
                if len(text) > max_chars_per_unit:
                    raise ValueError(
                        "A single table row exceeds the configured Alpha25 "
                        f"table evidence limit ({len(text)} > {max_chars_per_unit})."
                    )
                source = "\n".join(lines[start:end]).strip()
                axes = classify_axes(text)
                if not axes:
                    axes = ("composition", "processing", "structure", "properties")
                if relation_matrix:
                    anchor_candidates = []
                elif row_sample_column is not None:
                    anchor_candidates = [row[row_sample_column] for row in selected_rows]
                else:
                    first_header = re.sub(
                        r"[^a-z0-9]+", " ", str(header[0]).casefold()
                    ).strip()
                    anchor_candidates = [
                        header[index]
                        for index in columns
                        if re.sub(
                            r"[^a-z0-9]+", " ", str(header[index]).casefold()
                        ).strip()
                        != first_header
                        and _is_explicit_column_anchor(header[index])
                    ]
                anchors = tuple(
                    dict.fromkeys(
                        _table_anchor_label(label)
                        for label in anchor_candidates
                        if _is_plausible_table_anchor(_table_anchor_label(label))
                    )
                )
                state_anchors = _table_state_anchors(
                    header,
                    columns,
                    selected_rows,
                    caption=caption,
                    row_sample_column=row_sample_column,
                    relation_matrix=relation_matrix,
                )
                suffix = f"t{table_index}-c{column_offset + 1}-r{row_offset + 1}"
                units.append(
                    EvidenceUnit(
                        unit_id=_unit_id("table", start + 1, end, text, suffix),
                        kind="table",
                        text=text,
                        source_text="\n\n".join(
                            part for part in (caption, source, after) if part
                        ),
                        start_line=start + 1,
                        end_line=end,
                        axes=axes,
                        sample_anchors=anchors,
                        state_anchors=state_anchors,
                        metadata={
                            "table_index": table_index,
                            "column_start": column_offset + 1,
                            "row_start": row_offset + 1,
                            "sample_columns": len(columns),
                            "data_rows": len(selected_rows),
                            "projection_cells": len(columns) * len(selected_rows),
                            "projection_chars": len(text),
                            "relation_matrix": relation_matrix,
                            "row_sample_column": row_sample_column,
                        },
                    )
                )
                row_offset += row_count
            column_offset += len(columns)
    return units


def build_evidence_units(
    paper_text: str,
    *,
    max_prose_chars: int = 6000,
    table_columns: int = 2,
    table_rows: int = 10,
    table_context_chars: int = 600,
    structure_table_cells: int = 16,
    table_cells: int = 36,
    table_min_columns: int = 4,
    table_max_chars: int = 8000,
) -> list[EvidenceUnit]:
    """Build non-overlapping prose units and bounded table projections."""

    lines = str(paper_text or "").splitlines()
    if not lines:
        return []
    blocks = sorted(
        [*_table_blocks(lines), *_html_table_blocks(lines)], key=lambda row: row[0]
    )
    included = [True] * len(lines)
    for start, end, _ in blocks:
        for index in range(start, end):
            included[index] = False
    units = _paragraph_units(lines, included, max_chars=max(1000, max_prose_chars))
    units.extend(
        _table_units(
            lines,
            blocks,
            columns_per_unit=max(1, table_columns),
            rows_per_unit=max(1, table_rows),
            context_chars=max(0, table_context_chars),
            structure_cells_per_unit=max(1, structure_table_cells),
            cells_per_unit=max(1, table_cells),
            minimum_columns_per_unit=max(1, table_min_columns),
            max_chars_per_unit=max(1000, table_max_chars),
        )
    )
    return sorted(units, key=lambda unit: (unit.start_line, unit.kind != "table", unit.unit_id))


def output_budget_for(
    unit: EvidenceUnit,
    axis: Axis,
    *,
    dense_table_cell_threshold: int = 24,
    dense_table_output_tokens: int = 12288,
) -> int:
    """Bound completion tokens by task scope and planned table capacity."""

    base = {
        # Some provider-default reasoning modes consume completion tokens before
        # JSON content, so inventory uses the same safe ceiling as dense axes.
        "inventory": 4096,
        "composition": 3500,
        "processing": 3500,
        "structure": 4096,
        "properties": 3500,
        # A combined task replaces as many as four axis-scoped calls.  Small
        # evidence units still only need a compact response; reserving 8k for
        # every leaf makes GLM providers spend minutes in otherwise empty
        # reasoning/output space.  Larger/dense tasks are promoted below.
        "combined": 4096,
        "all": 4096,
    }[axis]
    dense_combined_table = False
    if unit.kind == "table":
        rows = int(unit.metadata.get("data_rows", 1))
        columns = int(unit.metadata.get("sample_columns", 1))
        # A dense table can legitimately produce one grounded fact per cell.
        # Starting such a task at 8k tokens and then regenerating the identical
        # evidence at 12k after truncation doubles the slowest provider work.
        # Give only tables above the configurable capacity threshold the same
        # budget that truncation recovery would otherwise use.
        if axis == "combined" and rows * columns > max(
            1, dense_table_cell_threshold
        ):
            dense_combined_table = True
            base = max(base, dense_table_output_tokens)
        base += min(1200, rows * columns * 60)
    ceiling = (
        max(8192, dense_table_output_tokens)
        if dense_combined_table
        else 8192
        if axis == "combined"
        else 4096
    )
    return min(ceiling, max(512, base))


def _grouped_axis_tasks(
    units: Iterable[EvidenceUnit],
    *,
    axis: Axis,
    max_chars: int,
    max_units_per_task: int | None = None,
    dense_table_cell_threshold: int = 16,
    dense_table_output_tokens: int = 12288,
    long_combined_chars: int = 4000,
    long_combined_output_tokens: int = 12288,
    long_combined_fact_signals: int = 18,
    dense_fact_signals: int = 60,
    dense_max_chars: int = 6000,
    sparse_fact_signals: int = 4,
    sparse_max_chars: int = 8000,
) -> list[AxisTask]:
    """Coalesce source-ordered prose for one axis without overlapping evidence."""

    ordered = sorted(units, key=lambda unit: (unit.start_line, unit.unit_id))
    if axis == "inventory":
        selected = [unit for unit in ordered if needs_inventory(unit)]
    elif axis == "combined":
        selected = ordered
    else:
        selected = [unit for unit in ordered if axis in unit.axes]
    def capacity_for_score(signals: int) -> int:
        normal = max(1000, max_chars)
        if axis != "combined":
            return normal
        if signals >= max(1, dense_fact_signals):
            return min(normal, max(1000, dense_max_chars))
        if signals <= max(0, sparse_fact_signals):
            return max(normal, max(1000, sparse_max_chars))
        return normal

    def capacity_for(unit: EvidenceUnit) -> int:
        if unit.kind == "table":
            return max(1000, max_chars)
        return capacity_for_score(fact_signal_score(unit.text))

    bounded: list[EvidenceUnit] = []
    for unit in selected:
        unit_capacity = capacity_for(unit)
        metadata = {
            **unit.metadata,
            "fact_signal_score": fact_signal_score(unit.text),
            "task_char_capacity": unit_capacity,
        }
        if unit.kind == "table" or len(unit.text) <= unit_capacity:
            bounded.append(replace(unit, metadata=metadata))
            continue
        parts = _split_text_to_limit(unit.text, unit_capacity)
        bounded.extend(
            replace(
                unit,
                unit_id=f"{unit.unit_id}-p{index}",
                text=part,
                source_text=part,
                metadata={
                    **metadata,
                    "fact_signal_score": fact_signal_score(part),
                },
            )
            for index, part in enumerate(parts, start=1)
        )
    selected = bounded
    groups: list[list[EvidenceUnit]] = []
    pending: list[EvidenceUnit] = []
    pending_chars = 0
    pending_signal_score = 0
    pending_capacity = max(1000, max_chars)

    def flush() -> None:
        nonlocal pending, pending_chars, pending_signal_score, pending_capacity
        if pending:
            groups.append(pending)
        pending = []
        pending_chars = 0
        pending_signal_score = 0
        pending_capacity = max(1000, max_chars)

    for unit in selected:
        # Table projections are already capacity-bounded by row and column;
        # keeping them isolated preserves their deterministic sample headers.
        if unit.kind == "table":
            flush()
            groups.append([unit])
            continue
        unit_capacity = int(unit.metadata.get("task_char_capacity", max_chars))
        unit_signal_score = int(
            unit.metadata.get("fact_signal_score", fact_signal_score(unit.text))
        )
        projected_signal_score = pending_signal_score + unit_signal_score
        aggregate_capacity = capacity_for_score(projected_signal_score)
        candidate_capacity = min(
            aggregate_capacity,
            pending_capacity if pending else unit_capacity,
            unit_capacity,
        )
        projected = pending_chars + len(unit.text) + (2 if pending else 0)
        unit_cap_reached = (
            max_units_per_task is not None
            and len(pending) >= max(1, max_units_per_task)
        )
        if pending and (projected > candidate_capacity or unit_cap_reached):
            flush()
            candidate_capacity = unit_capacity
            projected_signal_score = unit_signal_score
        pending.append(unit)
        pending_capacity = candidate_capacity
        pending_signal_score = projected_signal_score
        pending_chars += len(unit.text) + (2 if len(pending) > 1 else 0)
    flush()

    tasks: list[AxisTask] = []
    for group_index, group in enumerate(groups, start=1):
        evidence_text = "\n\n".join(unit.text for unit in group if unit.text)
        source_text = "\n\n".join(
            unit.source_text or unit.text for unit in group if unit.source_text or unit.text
        )
        start_line = min(unit.start_line for unit in group)
        end_line = max(unit.end_line for unit in group)
        kind = group[0].kind if len(group) == 1 else "prose"
        # The source line range and content hash are normally unique, but a
        # mechanically repeated long paragraph can split into byte-identical
        # parts. Include the stable group ordinal so coverage IDs never collide.
        unit_id = _unit_id(
            f"{axis}-group",
            start_line,
            end_line,
            evidence_text,
            suffix=f"g{group_index}",
        )
        anchors = tuple(
            dict.fromkeys(
                anchor
                for unit in group
                for anchor in unit.sample_anchors
                if str(anchor).strip()
            )
        )
        state_anchors = tuple(
            dict.fromkeys(
                anchor
                for unit in group
                for anchor in unit.state_anchors
                if anchor.sample_id_raw.strip() and anchor.state_raw.strip()
            )
        )
        base_budget = max(
            output_budget_for(
                unit,
                axis,
                dense_table_cell_threshold=dense_table_cell_threshold,
                dense_table_output_tokens=dense_table_output_tokens,
            )
            for unit in group
        )
        if (
            axis == "combined"
            and (
                len(evidence_text) >= max(1000, long_combined_chars)
                and fact_signal_score(evidence_text)
                >= max(1, long_combined_fact_signals)
                or fact_signal_score(evidence_text)
                >= max(1, dense_fact_signals)
            )
        ):
            base_budget = max(base_budget, long_combined_output_tokens)
        # Do not force every combined leaf to an 8k completion ceiling.  The
        # base budget is now 4k for a single small unit and grows with grouped
        # units; long/dense tasks can still promote themselves to 8k/12k above.
        budget_ceiling = max(4096, base_budget) if axis == "combined" else 4096
        output_budget = min(
            budget_ceiling, base_budget + max(0, len(group) - 1) * 300
        )
        tasks.append(
            AxisTask(
                task_id=f"{unit_id}-{axis}",
                unit_id=unit_id,
                axis=axis,
                evidence_text=evidence_text,
                source_text=source_text,
                output_token_budget=output_budget,
                kind=kind,
                sample_anchors=anchors,
                state_anchors=state_anchors,
                split_depth=max(unit.split_depth for unit in group),
            )
        )
    return tasks


def _split_text_to_limit(text: str, max_chars: int) -> list[str]:
    """Split source text losslessly near paragraph/sentence/word boundaries."""

    remaining = str(text or "").strip()
    parts: list[str] = []
    while len(remaining) > max_chars:
        boundary = remaining.rfind("\n\n", 0, max_chars + 1)
        if boundary < max_chars // 2:
            sentence = remaining.rfind(". ", 0, max_chars + 1)
            boundary = sentence + 1 if sentence >= max_chars // 2 else boundary
        if boundary < max_chars // 2:
            boundary = remaining.rfind("\n", 0, max_chars + 1)
        if boundary < max_chars // 2:
            boundary = remaining.rfind(" ", 0, max_chars + 1)
        if boundary < 1:
            boundary = max_chars
        part = remaining[:boundary].strip()
        if not part:
            boundary = max_chars
            part = remaining[:boundary]
        parts.append(part)
        remaining = remaining[boundary:].strip()
    if remaining:
        parts.append(remaining)
    return parts


def plan_inventory_tasks(
    units: Iterable[EvidenceUnit], *, max_chars: int = 7000
) -> list[AxisTask]:
    """Plan bounded source-label discovery calls after cross-unit deduplication.

    Table parsing has already established source-backed item labels without an
    LLM. A later prose chunk that only repeats those same labels does not need
    another inventory call. Prose containing any previously unseen trigger
    label remains eligible, so this optimization cannot suppress discovery of
    a genuinely new sample or comparison material.
    """

    materialized = list(units)
    known = {
        _inventory_label_key(anchor)
        for unit in materialized
        for anchor in unit.sample_anchors
        if str(anchor).strip()
    }
    selected: list[EvidenceUnit] = []
    for unit in materialized:
        if not needs_inventory(unit):
            continue
        trigger_keys = {
            _inventory_label_key(label)
            for label in _inventory_candidate_labels(unit)
            if str(label).strip()
        }
        if known and trigger_keys and trigger_keys <= known:
            continue
        selected.append(unit)
    return _grouped_axis_tasks(selected, axis="inventory", max_chars=max_chars)


def plan_axis_tasks(
    units: Iterable[EvidenceUnit],
    *,
    max_chars: int = 7000,
    axis_max_chars: Mapping[Axis, int] | None = None,
) -> list[AxisTask]:
    """Plan non-overlapping tasks by axis, coalescing small prose sections."""

    materialized = list(units)
    tasks: list[AxisTask] = []
    limits = dict(axis_max_chars or {})
    for axis in ("composition", "processing", "structure", "properties"):
        tasks.extend(
            _grouped_axis_tasks(
                materialized,
                axis=axis,
                max_chars=max(1000, int(limits.get(axis, max_chars))),
            )
        )
    return sorted(tasks, key=lambda task: (task.unit_id, task.axis, task.task_id))


def plan_combined_axis_tasks(
    units: Iterable[EvidenceUnit],
    *,
    max_chars: int = 8000,
    max_units_per_task: int = 8,
    dense_table_cell_threshold: int = 16,
    dense_table_output_tokens: int = 12288,
    long_combined_chars: int = 4000,
    long_combined_output_tokens: int = 12288,
    long_combined_fact_signals: int = 18,
    dense_fact_signals: int = 60,
    dense_max_chars: int = 6000,
    sparse_fact_signals: int = 4,
    sparse_max_chars: int = 8000,
) -> list[AxisTask]:
    """Plan one mixed four-axis call per bounded evidence group.

    Every evidence unit is assigned exactly once.  Prose is coalesced in source
    order up to ``max_chars`` and table projections remain isolated so their
    deterministic row/column identities cannot bleed into a neighboring table.
    The response still contains individually typed axis facts, which are gated
    one by one against this task's evidence before materialization.
    """

    materialized = list(units)
    # Tables remain independent tasks, but they must not force a flush between
    # two otherwise coalescible prose sections. Group the two evidence kinds
    # separately so a paper with many short tables does not create two extra
    # prose calls around every table.
    prose_tasks = _grouped_axis_tasks(
        (unit for unit in materialized if unit.kind != "table"),
        axis="combined",
        max_chars=max_chars,
        max_units_per_task=max_units_per_task,
        dense_table_cell_threshold=dense_table_cell_threshold,
        dense_table_output_tokens=dense_table_output_tokens,
        long_combined_chars=long_combined_chars,
        long_combined_output_tokens=long_combined_output_tokens,
        long_combined_fact_signals=long_combined_fact_signals,
        dense_fact_signals=dense_fact_signals,
        dense_max_chars=dense_max_chars,
        sparse_fact_signals=sparse_fact_signals,
        sparse_max_chars=sparse_max_chars,
    )
    table_tasks = _grouped_axis_tasks(
        (unit for unit in materialized if unit.kind == "table"),
        axis="combined",
        max_chars=max_chars,
        max_units_per_task=max_units_per_task,
        dense_table_cell_threshold=dense_table_cell_threshold,
        dense_table_output_tokens=dense_table_output_tokens,
        long_combined_chars=long_combined_chars,
        long_combined_output_tokens=long_combined_output_tokens,
        long_combined_fact_signals=long_combined_fact_signals,
        dense_fact_signals=dense_fact_signals,
        dense_max_chars=dense_max_chars,
        sparse_fact_signals=sparse_fact_signals,
        sparse_max_chars=sparse_max_chars,
    )
    return [*prose_tasks, *table_tasks]


def split_task_once(
    task: AxisTask, *, max_depth: int = 1, min_chars: int = 800
) -> list[AxisTask]:
    """Split one failed task at a source boundary up to an explicit depth cap."""

    if task.split_depth >= max(0, max_depth) or len(task.evidence_text) < max(200, min_chars):
        return []
    text = task.evidence_text
    length = len(text)
    midpoint = length // 2
    lower_limit = length // 3
    upper_limit = length - lower_limit

    def nearest_boundary(token: str, *, offset: int = 0) -> int | None:
        lower = text.rfind(token, lower_limit, midpoint + 1)
        upper = text.find(token, midpoint, upper_limit + 1)
        candidates = [
            candidate + offset
            for candidate in (lower, upper)
            if candidate >= lower_limit and candidate <= upper_limit
        ]
        return min(candidates, key=lambda row: abs(row - midpoint)) if candidates else None

    # Prefer semantic boundaries, but never accept a paragraph break near one
    # edge (for example a long prose block followed by a one-line caption).
    boundary = nearest_boundary("\n\n")
    if boundary is None:
        boundary = nearest_boundary(". ", offset=1)
    if boundary is None:
        boundary = nearest_boundary("\n")
    if boundary is None:
        boundary = nearest_boundary(" ")
    if boundary is None:
        boundary = midpoint
    parts = [task.evidence_text[:boundary].strip(), task.evidence_text[boundary:].strip()]
    if any(not part for part in parts):
        return []
    children: list[AxisTask] = []
    for index, part in enumerate(parts, start=1):
        children.append(
            replace(
                task,
                task_id=f"{task.task_id}-s{index}",
                evidence_text=part,
                source_text=part,
                parent_task_id=task.task_id,
                split_depth=task.split_depth + 1,
                # Splitting reduces input ambiguity; it must not also recreate
                # the same output truncation with a smaller completion budget.
                output_token_budget=task.output_token_budget,
            )
        )
    return children
