"""Conservative recovery of paper-level mechanical test context.

Alpha25 axis tasks are intentionally bounded.  A property value in a table can
therefore be cached without the methods paragraph that defines its test
conditions.  This module repairs only that transport loss: it copies literal
source prose into an otherwise empty ``test_condition_raw`` field when the
paper contains one unambiguous compatible tensile-test context.

The recovery is deterministic and source-only.  It does not infer customary
temperatures, standards, specimen geometries, or equipment.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from typing import Any, Literal


RecoveryStatus = Literal[
    "recovered",
    "ambiguous",
    "existing",
    "ineligible",
    "reference",
    "not_found",
    "disabled",
]


_UNREPORTED = {
    "",
    "n/a",
    "na",
    "none",
    "not available",
    "not provided",
    "not reported",
    "not_reported",
    "unknown",
    "unspecified",
}

_TENSILE_PROPERTY = re.compile(
    r"(?ix)\b(?:"
    r"ultimate\s+tensile\s+strength|tensile\s+strength|yield\s+(?:strength|stress)|"
    r"uniform\s+elongation|total\s+elongation|elongation\s+(?:at|to)\s+(?:break|failure)|"
    r"elongation|tensile\s+ductility|reduction\s+of\s+area|young'?s\s+modulus"
    r")\b"
)
_TENSILE_ABBREVIATION = re.compile(
    r"(?ix)^\s*(?:"
    r"(?:UTS|YS)(?:\s*(?:\(\s*(?:MPa|GPa|Pa|ksi)\s*\)|"
    r"\[\s*(?:MPa|GPa|Pa|ksi)\s*\]|/\s*(?:MPa|GPa|Pa|ksi)))?|"
    r"(?:TE|EL|EAB)(?:\s*(?:\(\s*%\s*\)|\[\s*%\s*\]|/\s*%))?"
    r")\s*$"
)
_NON_TENSILE_PROPERTY = re.compile(
    r"(?i)\b(?:compress(?:ive|ion)|fatigue|creep|hardness|indentation|flexur|bend(?:ing)?|"
    r"impact|shear|torsion|wear|corrosion)\b"
)
_TENSILE_METHOD = re.compile(
    r"(?ix)\b(?:"
    r"(?:uniaxial\s+)?tensile\s+(?:test(?:s|ing|ed)?|experiment(?:s)?|specimens?|samples?)|"
    r"tensile\s+propert(?:y|ies)\s+(?:were\s+)?(?:tested|conducted|examined|measured)|"
    r"tension\s+(?:test(?:s|ing|ed)?|experiment(?:s)?)|"
    r"tested\s+(?:under|in)\s+(?:uniaxial\s+)?tension"
    r")\b"
)
_PROCEDURE_ACTION = re.compile(
    r"(?ix)\b(?:"
    r"perform(?:ed|ing)?|conduct(?:ed|ing)?|carried\s+out|subject(?:ed|ing)?|"
    r"test(?:ed|ing)|machin(?:ed|ing)|extract(?:ed|ing)|utiliz(?:ed|ing)|"
    r"measur(?:ed|ing)|repeat(?:ed|ing)?|record(?:ed|ing)|load(?:ed|ing)|"
    r"design(?:ed|ing)?"
    r")\b"
)
_RESULT_ONLY = re.compile(
    r"(?i)\b(?:results?\s+(?:show|indicate|demonstrate)|yielded|exhibited|achieved|"
    r"increased|decreased|higher|lower|superior)\b"
)
_MATERIAL_STATE_TEMPERATURE = re.compile(
    r"(?ix)\b(?:samples?|specimens?|materials?|alloys?)\s+"
    r"(?:heat[\s-]*treated|annealed|aged|sintered|solutionized|homogenized)\s+at\b"
)
_EXPLICIT_TEST_TEMPERATURE = re.compile(
    r"(?ix)\b(?:test(?:ed|ing|s)?|experiment(?:s)?|deform(?:ed|ation))\b"
    r"[^.;]{0,55}\bat\s+(?:RT|room\s+temperature|[-+]?\d+(?:\.\d+)?\s*"
    r"(?:°\s*C|°C|\^?\s*\{?\s*\\circ|K))"
)
_OTHER_TEST_FAMILY = re.compile(
    r"(?i)\b(?:fatigue|creep|compress(?:ion|ive)|hardness|indentation|"
    r"stress\s+relaxation|relaxation\s+test|wear|corrosion)\b"
)
_NON_MONOTONIC_TENSILE_PROTOCOL = re.compile(
    r"(?i)\b(?:multiple?\s+stress\s+relaxation|multi[\s-]*cycle\s+relaxation|"
    r"preset\s+strain|relaxation\s+(?:cycle|period)|holding\s+time)\b"
)
_TENSILE_TEST_EVENT = re.compile(
    r"(?ix)\b(?:"
    r"(?:uniaxial\s+)?tensile\s+(?:test(?:s|ing|ed)?|experiment(?:s)?)|"
    r"tensile\s+propert(?:y|ies)\s+(?:were\s+)?(?:tested|conducted|examined|measured)|"
    r"tension\s+(?:test(?:s|ing|ed)?|experiment(?:s)?)|"
    r"tested\s+(?:under|in)\s+(?:uniaxial\s+)?tension"
    r")\b"
)
_SPECIMEN_PREPARATION = re.compile(
    r"(?ix)\b(?:dog[\s-]*bone|dumbbell|gauge\s+(?:length|width|diameter|section|dimensions?)|"
    r"(?:tensile\s+)?specimens?\s+(?:were\s+)?(?:machined|extracted|cut|prepared)|"
    r"(?:machined|extracted|cut|prepared)\s+(?:the\s+)?tensile\s+specimens?)\b"
)

_DETAIL_PATTERNS: dict[str, re.Pattern[str]] = {
    "rate": re.compile(
        r"(?ix)\b(?:strain|loading|load|displacement|crosshead|extension)\s+rate\b|"
        r"\b(?:mm\s*[/·]\s*min|s\s*\^?\s*[-−]\s*1|s\s*[-−]1)\b"
    ),
    "temperature": re.compile(
        r"(?ix)\b(?:RT|(?:room|ambient|elevated|test(?:ing)?|cryogenic)\s+temperature)\b|"
        r"(?<![A-Za-z0-9])[-+]?\d+(?:\.\d+)?\s*"
        r"(?:°\s*C|°C|\^?\s*\{?\s*\\circ\s*\}?\s*(?:\\mathrm\s*\{?)?C|K)\b"
    ),
    "standard": re.compile(
        r"(?i)\b(?:ASTM|ISO|DIN|EN|JIS|GB/T|BS)\s*[-_/.:()]*\s*"
        r"(?=[A-Z-]*\d)[A-Z0-9./:()_-]+"
    ),
    "specimen": re.compile(
        r"(?ix)\b(?:dog[\s-]*bone|dumbbell|gauge\s+(?:length|width|diameter|section)|"
        r"tensile\s+(?:specimens?|samples?)|specimen\s+(?:geometry|dimensions?|thickness)|"
        r"diameter\s+of\s+\d)\b"
    ),
    "equipment": re.compile(
        r"(?ix)\b(?:Instron|MTS|Zwick|Shimadzu|Gleeble|universal\s+(?:testing|test)\s+machine|"
        r"servo[\s-]*hydraulic|testing\s+machine|load\s+frame)\b"
    ),
    "strain_measurement": re.compile(
        r"(?ix)\b(?:extensometer|digital\s+image\s+correlation|\bDIC\b|ARAMIS|strain\s+gauge)\b"
    ),
    "replicates": re.compile(
        r"(?ix)\b(?:repeat(?:ed|ing)?|replicates?|reproducib(?:le|ility)|"
        r"at\s+least\s+(?:three|four|five|\d+)\s+(?:times|specimens?|samples?))\b"
    ),
    "orientation": re.compile(
        r"(?ix)\b(?:horizontal|vertical|transverse|longitudinal|build\s+direction|"
        r"parallel|perpendicular)\b"
    ),
    "environment": re.compile(
        r"(?ix)\b(?:air|vacuum|argon|inert\s+(?:gas|atmosphere)|hydrogen|"
        r"laboratory\s+atmosphere)\b"
    ),
}

_TEMPERATURE_VALUE = re.compile(
    r"(?ix)\b(?:RT|(?:room|ambient|cryogenic)\s+temperature)\b|"
    r"(?<![A-Za-z0-9])[-+]?\d+(?:\.\d+)?\s*"
    r"(?:°\s*C|°C|\^?\s*\{?\s*\\circ\s*\}?\s*(?:\\mathrm\s*\{?)?C|K)\b"
)
_STANDARD_VALUE = _DETAIL_PATTERNS["standard"]
_ORIENTATION_VALUE = re.compile(
    r"(?i)\b(?:horizontal|vertical|transverse|longitudinal|parallel|perpendicular|"
    r"build\s+direction)\b"
)
_NUMERIC_CITATION = re.compile(
    r"(?x)\[\s*"
    r"\d{1,4}(?:\s*[-–—,;]\s*\d{1,4})*"
    r"\s*\]"
)
_AUTHOR_YEAR_CITATION = re.compile(
    r"(?ix)\b[A-Z][A-Za-z'’-]+(?:\s+et\s+al\.)?\s*"
    r"(?:\(|,\s*)?(?:19|20)\d{2}[a-z]?\)?"
)


def property_context_recovery_enabled() -> bool:
    """Return the model-agnostic feature switch (enabled by default)."""

    raw = os.getenv("KNOWMAT2_ALPHA25_PROPERTY_CONTEXT_RECOVERY", "1")
    return raw.strip().casefold() not in {"0", "false", "no", "off", "disabled"}


def _fold(value: Any) -> str:
    text = str(value or "").casefold()
    text = text.replace("−", "-").replace("–", "-").replace("—", "-")
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def _is_unreported(value: Any) -> bool:
    return _fold(value).replace("_", " ") in {row.replace("_", " ") for row in _UNREPORTED}


def _property_is_tensile(row: dict[str, Any]) -> bool:
    name = str(row.get("property_name_raw") or "")
    method = str(row.get("test_method_raw") or "")
    combined = f"{name} | {method}"
    if _NON_TENSILE_PROPERTY.search(combined):
        return False
    abbreviation = _TENSILE_ABBREVIATION.fullmatch(name)
    return bool(
        abbreviation
        or _TENSILE_PROPERTY.search(name)
        or _TENSILE_METHOD.search(method)
    )


def _reference_ineligibility_reason(
    row: dict[str, Any], owner_role: str | None
) -> str | None:
    """Explain why paper-level methods cannot be bound to this property.

    Material role is the strongest signal, but comparison-table extraction can
    occasionally classify literature material families as Target.  Preserve
    those values while treating row-local citations as provenance boundaries.
    """

    if _fold(owner_role) == "reference":
        return "the owning material is explicitly classified as Reference"

    data_source = _fold(row.get("data_source")).replace(" ", "_")
    if data_source == "external_reference":
        return "the property explicitly declares external_reference provenance"

    raw_note = str(row.get("raw_note") or "")
    if _NUMERIC_CITATION.search(raw_note) or _AUTHOR_YEAR_CITATION.search(raw_note):
        return "the property-local note carries bibliographic provenance"

    evidence_rows = (
        row.get("source_evidence")
        if isinstance(row.get("source_evidence"), list)
        else [row.get("source_evidence")]
    )
    evidence = "\n".join(str(value or "") for value in evidence_rows)
    table_like = "|" in evidence or "<table" in evidence.casefold()
    if table_like and (
        _NUMERIC_CITATION.search(evidence)
        or _AUTHOR_YEAR_CITATION.search(evidence)
    ):
        return (
            "citation-bearing table evidence does not uniquely establish a "
            "current-paper test-method binding"
        )
    return None


def _is_table_or_figure(block: str) -> bool:
    stripped = block.lstrip()
    return bool(
        stripped.startswith(("<table", "|", "![", "<img", "quality_quarantine:"))
        or re.match(r"(?i)^(?:fig(?:ure)?|table)\s*\d", stripped)
    )


def _markdown_blocks(source_text: str) -> list[tuple[int, int, str, str]]:
    """Return ``(start, end, heading, literal block)`` tuples."""

    blocks: list[tuple[int, int, str, str]] = []
    current: list[str] = []
    start = 0
    heading = ""

    def flush(end: int) -> None:
        nonlocal current, start
        text = "\n".join(current).strip()
        if text:
            blocks.append((start, end, heading, text))
        current = []

    for number, raw_line in enumerate(source_text.splitlines(), start=1):
        stripped = raw_line.strip()
        if stripped.startswith("#"):
            flush(number - 1)
            heading = stripped.lstrip("#").strip()
            continue
        if not stripped:
            flush(number - 1)
            continue
        if not current:
            start = number
        current.append(raw_line.rstrip())
    flush(len(source_text.splitlines()))
    return blocks


def _normalized_values(pattern: re.Pattern[str], text: str) -> tuple[str, ...]:
    return tuple(sorted({_fold(match.group(0)) for match in pattern.finditer(text)}))


def _temperature_values(text: str) -> tuple[str, ...]:
    values: set[str] = set()
    for match in _TEMPERATURE_VALUE.finditer(text):
        value = _fold(match.group(0))
        if value == "rt" or value.startswith(("room temperature", "ambient temperature")):
            value = "room temperature"
        values.add(value)
    return tuple(sorted(values))


def _rate_values(text: str) -> tuple[str, ...]:
    """Canonicalize explicit rate magnitudes without interpreting them."""

    cleaned = _fold(text)
    cleaned = cleaned.replace("\\times", " x ").replace("×", " x ")
    cleaned = cleaned.replace("$", "").replace("{", "").replace("}", "")
    cleaned = cleaned.replace("^", "").replace("\\,", " ")
    cleaned = re.sub(r"\\mathrm|\\text", "", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned)
    pattern = re.compile(
        r"(?ix)\b(strain|loading|load|displacement|crosshead|extension)\s+rate"
        r"(?:\s+of|\s*=|\s*:)?\s*"
        r"([0-9]+(?:\.[0-9]+)?)"
        r"(?:\s*x\s*10\s*([-+]?\d+))?\s*"
        r"(s\s*[-−]?1|mm\s*/\s*min(?:\s*/\s*min)?|%\s*/\s*min|mpa\s*/\s*min)?"
    )
    values: set[str] = set()
    for match in pattern.finditer(cleaned):
        family, magnitude, exponent, unit = match.groups()
        number = f"{magnitude}e{exponent}" if exponent else magnitude
        normalized_unit = re.sub(r"\s+", "", unit or "")
        values.add(f"{family}:{number}:{normalized_unit}")
    return tuple(sorted(values))


@dataclass(frozen=True)
class TestContextCandidate:
    text: str
    line_start: int
    line_end: int
    heading: str
    score: int
    discriminators: dict[str, tuple[str, ...]]
    source_order: int = 0

    def audit_dict(self) -> dict[str, Any]:
        return {
            "line_start": self.line_start,
            "line_end": self.line_end,
            "heading": self.heading,
            "score": self.score,
            "discriminators": self.discriminators,
            "text": self.text,
        }


@dataclass(frozen=True)
class PropertyContextDecision:
    status: RecoveryStatus
    reason: str
    condition_raw: str | None = None
    selected: tuple[TestContextCandidate, ...] = ()
    candidates: tuple[TestContextCandidate, ...] = ()


def _candidate_from_block(
    line_start: int,
    line_end: int,
    heading: str,
    text: str,
    *,
    source_order: int = 0,
) -> TestContextCandidate | None:
    if _is_table_or_figure(text) or not _TENSILE_METHOD.search(text):
        return None
    if re.search(r"(?i)\b(?:shown|depicted|illustrated)\s+in\s+(?:Fig|Table)\.$", text):
        return None
    if re.search(r"(?i)\b(?:abstract|introduction|references|bibliography)\b", heading):
        return None
    family_hits = sorted(
        [
            *((match.start(), "tensile") for match in _TENSILE_METHOD.finditer(text)),
            *((match.start(), "other") for match in _OTHER_TEST_FAMILY.finditer(text)),
        ]
    )
    if family_hits and family_hits[0][1] == "other":
        return None
    if _NON_MONOTONIC_TENSILE_PROTOCOL.search(text):
        return None
    if not _TENSILE_TEST_EVENT.search(text) and not _SPECIMEN_PREPARATION.search(text):
        return None
    details = {
        name: tuple(match.group(0).strip() for match in pattern.finditer(text))
        for name, pattern in _DETAIL_PATTERNS.items()
    }
    detail_count = sum(bool(values) for values in details.values())
    action = bool(_PROCEDURE_ACTION.search(text))
    if not detail_count or not action:
        return None
    # Results prose can mention a testing temperature next to a measured value.
    # Require at least two procedural details before accepting such a block.
    if _RESULT_ONLY.search(text) and detail_count < 2:
        return None
    if (
        _MATERIAL_STATE_TEMPERATURE.search(text)
        and _temperature_values(text)
        and not _EXPLICIT_TEST_TEMPERATURE.search(text)
    ):
        # A sentence such as "tests on samples sintered at 1300 °C" reports a
        # material state, not a test temperature.  Passing the whole sentence
        # to the downstream generic condition normalizer would silently turn
        # that process temperature into a testing condition.
        return None
    heading_bonus = 3 if re.search(r"(?i)\b(?:tensile|mechanical\s+test)", heading) else 0
    score = 4 + 2 * detail_count + heading_bonus
    if re.search(r"(?i)\b(?:methods?|experimental|materials?\s+and\s+methods?)\b", heading):
        score += 1
    discriminators = {
        "temperature": _temperature_values(text),
        "rate": _rate_values(text),
        "standard": _normalized_values(_STANDARD_VALUE, text),
        "orientation": _normalized_values(_ORIENTATION_VALUE, text),
    }
    return TestContextCandidate(
        text=text,
        line_start=line_start,
        line_end=line_end,
        heading=heading,
        score=score,
        discriminators=discriminators,
        source_order=source_order,
    )


def extract_tensile_test_contexts(source_text: str) -> tuple[TestContextCandidate, ...]:
    """Extract detailed, literal tensile-method blocks from OCR Markdown."""

    candidates: list[TestContextCandidate] = []
    seen: set[str] = set()
    for line_start, line_end, heading, text in _markdown_blocks(source_text):
        sentences = [
            sentence.strip()
            for sentence in re.split(r"(?<=[.!?])\s+(?=[A-Z0-9])", text)
            if sentence.strip()
        ]
        for index, sentence in enumerate(sentences):
            if not _TENSILE_METHOD.search(sentence):
                continue
            parts = [sentence]
            # A following sentence such as "Specimens were tested at ..." may
            # carry the rate while relying on the explicit tensile noun in the
            # previous sentence.  Include it only until another tensile anchor
            # starts a potentially distinct protocol.
            for following in sentences[index + 1 : index + 3]:
                if _TENSILE_METHOD.search(following):
                    break
                if _OTHER_TEST_FAMILY.search(following):
                    break
                if not _PROCEDURE_ACTION.search(following):
                    break
                if not any(pattern.search(following) for pattern in _DETAIL_PATTERNS.values()):
                    break
                parts.append(following)
            literal = " ".join(parts)
            candidate = _candidate_from_block(
                line_start,
                line_end,
                heading,
                literal,
                source_order=line_start * 10_000 + index,
            )
            if candidate is None:
                continue
            signature = _fold(candidate.text)
            if signature in seen:
                continue
            seen.add(signature)
            candidates.append(candidate)
    return tuple(candidates)


def _conflicting(left: TestContextCandidate, right: TestContextCandidate) -> bool:
    for key in ("temperature", "rate", "standard", "orientation"):
        left_values = set(left.discriminators.get(key, ()))
        right_values = set(right.discriminators.get(key, ()))
        if left_values and right_values and left_values.isdisjoint(right_values):
            return True
    return False


def _hint_matches(candidate: TestContextCandidate, hint: str) -> int:
    score = 0
    for values in candidate.discriminators.values():
        score += sum(value in hint for value in values if value)
    return score


def _select_complementary(
    primary: TestContextCandidate,
    candidates: tuple[TestContextCandidate, ...],
) -> tuple[TestContextCandidate, ...]:
    selected = [primary]
    for candidate in candidates:
        if candidate is primary or _conflicting(primary, candidate):
            continue
        same_source_block = (
            candidate.line_start == primary.line_start
            and candidate.line_end == primary.line_end
        )
        if same_source_block:
            selected.append(candidate)
    return tuple(sorted(selected, key=lambda row: row.source_order))


def _join_selected(candidates: tuple[TestContextCandidate, ...]) -> str:
    parts: list[str] = []
    previous: TestContextCandidate | None = None
    for candidate in candidates:
        if previous is not None and candidate.line_start == previous.line_start:
            parts[-1] = f"{parts[-1]} {candidate.text}"
        else:
            parts.append(candidate.text)
        previous = candidate
    return "\n\n".join(parts)


class PropertyContextIndex:
    """Reusable source-text index for condition recovery within one paper."""

    def __init__(self, source_text: str | None) -> None:
        self._enabled = property_context_recovery_enabled()
        self._candidates = (
            extract_tensile_test_contexts(source_text or "")
            if self._enabled and source_text
            else ()
        )

    @property
    def candidates(self) -> tuple[TestContextCandidate, ...]:
        return self._candidates

    def recover(
        self,
        row: dict[str, Any],
        *,
        owner_role: str | None = None,
    ) -> PropertyContextDecision:
        if not self._enabled:
            return PropertyContextDecision("disabled", "feature flag is disabled")
        if not _is_unreported(row.get("test_condition_raw")):
            return PropertyContextDecision("existing", "property already has a reported condition")
        if not _property_is_tensile(row):
            return PropertyContextDecision("ineligible", "property is not an explicit tensile family")
        if not self._candidates:
            return PropertyContextDecision("not_found", "no detailed tensile procedure was found")
        reference_reason = _reference_ineligibility_reason(row, owner_role)
        if reference_reason:
            return PropertyContextDecision("reference", reference_reason)

        hint = _fold(
            " | ".join(
                str(value or "")
                for value in (
                    row.get("property_name_raw"),
                    row.get("test_method_raw"),
                    row.get("test_standard_raw"),
                    row.get("test_specimen_raw"),
                    *(
                        row.get("source_evidence")
                        if isinstance(row.get("source_evidence"), list)
                        else [row.get("source_evidence")]
                    ),
                )
            )
        )
        ranked = sorted(
            self._candidates,
            key=lambda candidate: (_hint_matches(candidate, hint), candidate.score),
            reverse=True,
        )
        hint_scores = [_hint_matches(candidate, hint) for candidate in ranked]
        if hint_scores[0] > 0 and (len(hint_scores) == 1 or hint_scores[0] > hint_scores[1]):
            primary = ranked[0]
        else:
            primary = max(ranked, key=lambda candidate: candidate.score)
            conflicts = [
                candidate
                for candidate in ranked
                if candidate is not primary and _conflicting(primary, candidate)
            ]
            if conflicts:
                return PropertyContextDecision(
                    "ambiguous",
                    "multiple incompatible tensile test contexts lack a property-local discriminator",
                    candidates=tuple(ranked),
                )

        selected = _select_complementary(primary, tuple(ranked))
        condition = _join_selected(selected)
        if len(condition) > 4000:
            selected = (primary,)
            condition = primary.text
        return PropertyContextDecision(
            "recovered",
            "one compatible paper-level tensile procedure was uniquely identifiable",
            condition_raw=condition,
            selected=selected,
            candidates=tuple(ranked),
        )
