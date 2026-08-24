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

import hashlib
import json
import os
import re
from dataclasses import dataclass
from typing import Any, Literal, Sequence


RecoveryStatus = Literal[
    "recovered",
    "augmented",
    "ambiguous",
    "existing",
    "ineligible",
    "reference",
    "not_found",
    "disabled",
]

ProtocolLedgerStatus = Literal[
    "bound",
    "existing",
    "ambiguous",
    "conflict",
    "reference",
    "ineligible",
    "not_found",
    "disabled",
]

ProtocolScope = Literal[
    "owner_local",
    "target_global",
    "reference_local",
    "ambiguous",
    "",
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
_CORE_TENSILE_PROPERTY = re.compile(
    r"(?ix)\b(?:ultimate\s+tensile\s+strength|tensile\s+strength|"
    r"yield\s+(?:strength|stress)|uniform\s+elongation|total\s+elongation|"
    r"elongation\s+(?:at|to)\s+(?:break|failure)|elongation|"
    r"tensile\s+ductility|reduction\s+of\s+area)\b"
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
    r"(?:uniaxial\s+)?tensile\s+(?:(?:load(?:ing)?)\s+)?"
    r"(?:test(?:s|ing|ed)?|experiment(?:s)?|specimens?|samples?)|"
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
    r"design(?:ed|ing)?|execut(?:ed|ing)?|captur(?:ed|ing)?|excis(?:ed|ing)?"
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
    r"(?:uniaxial\s+)?tensile\s+(?:(?:load(?:ing)?)\s+)?"
    r"(?:test(?:s|ing|ed)?|experiment(?:s)?)|"
    r"tensile\s+propert(?:y|ies)\s+(?:were\s+)?(?:tested|conducted|examined|measured)|"
    r"tension\s+(?:test(?:s|ing|ed)?|experiment(?:s)?)|"
    r"tested\s+(?:under|in)\s+(?:uniaxial\s+)?tension"
    r")\b"
)
_SPECIMEN_PREPARATION = re.compile(
    r"(?ix)\b(?:dog[\s-]*bone|dumbbell|gauge\s+(?:length|width|diameter|section|dimensions?)|"
    r"(?:tensile\s+)?(?:specimens?|coupons?)\s+(?:were\s+)?"
    r"(?:machined|extracted|excised|cut|prepared)|"
    r"(?:machined|extracted|excised|cut|prepared)\s+(?:the\s+)?"
    r"tensile\s+(?:specimens?|coupons?))\b"
)
_EXPLICIT_GLOBAL_TENSILE_SCOPE = re.compile(
    r"(?ix)(?:"
    r"\b(?:all|each|every)\s+(?:(?:of\s+)?the\s+)?"
    r"(?:tensile\s+)?(?:tests?|specimens?|samples?|coupons?)\b"
    r"|\b(?:tensile\s+)?(?:tests?|specimens?|samples?|coupons?)\s+"
    r"(?:were\s+)?(?:all|each)\b"
    r"|\bat\s+least\s+(?:three|four|five|six|\d+)\s+"
    r"(?:tensile\s+)?(?:specimens?|samples?|coupons?)\s+"
    r"(?:were\s+)?tested\s+for\s+each\s+(?:material|alloy|condition)\b"
    r")"
)

_DETAIL_PATTERNS: dict[str, re.Pattern[str]] = {
    "rate": re.compile(
        r"(?ix)\b(?:strain|loading|load|displacement|crosshead|extension)\s+rate\b|"
        r"\b(?:mm\s*[/·]\s*min|min\s*\^?\s*[-−]?\s*1|"
        r"s\s*\^?\s*[-−]\s*1|s\s*[-−]1)\b"
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
        r"tensile\s+(?:specimens?|samples?|coupons?)|"
        r"(?:specimen|coupon)\s+(?:geometry|dimensions?|thickness)|"
        r"diameter\s+of\s+\d)\b"
    ),
    "equipment": re.compile(
        r"(?ix)\b(?:Instron|MTS|Zwick|Shimadzu|Gleeble|universal\s+(?:testing|test)\s+machine|"
        r"servo[\s-]*hydraulic|testing\s+machine|load\s+frame)\b"
    ),
    "strain_measurement": re.compile(
        r"(?ix)\b(?:extensometer|digital\s+image\s+correlation|\bDIC\b|ARAMIS|"
        r"strain\s+(?:gauge|images?))\b"
    ),
    "replicates": re.compile(
        r"(?ix)\b(?:repeat(?:ed|ing)?|replicates?|reproducib(?:le|ility)|"
        r"at\s+least\s+(?:three|four|five|\d+)\s+(?:times|specimens?|samples?)|"
        r"(?:number\s+of\s+)?(?:specimens?|samples?|coupons?)\s+tested\s+"
        r"(?:from\s+[^.;]{1,40}\s+)?"
        r"(?:was|were|=|:)\s*(?:three|four|five|six|\d+))\b"
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

# ``test_condition_raw`` is a public, compact condition field.  It is not a
# second copy of the paper's methods section.  These are the dimensions that
# can safely be transported from a paper-level tensile protocol to a Property
# without carrying specimen geometry, equipment, image-correlation details,
# or replicate counts along with it.
_CONDITION_DETAIL_KEYS = (
    "temperature",
    "rate",
    "standard",
    "orientation",
    "environment",
)
_CONDITION_PREFIX = re.compile(
    r"(?ix)(?:\baccording\s+to\s+(?:the\s+)?|\bat\s+(?:a\s+|an\s+|the\s+)?|"
    r"\bin\s+|\bunder\s+|\bwith\s+|\bof\s+)$"
)
_CONDITION_TAIL_NOISE = re.compile(
    r"(?ix)\s+(?:using|with|on)\s+(?:an?|the)\b|"
    r"\s+(?:all|the)\s+(?:tensile\s+)?(?:tests?|specimens?|samples?|coupons?)"
    r"\s+(?:were\s+)?(?:repeated|replicated|tested\s+again)\b|"
    r"\s*,?\s*at\s+least\s+(?:three|four|five|six|\d+)\s+"
    r"(?:tensile\s+)?(?:specimens?|samples?|coupons?)\s+"
    r"(?:were\s+)?tested\s+for\s+each\s+(?:material|alloy|condition)\b"
)
_RATE_LITERAL = re.compile(
    r"(?ix)(?:\b(?:strain|loading|load|displacement|crosshead|extension)\s+rate\b"
    r"\s*(?:of|=|:)?\s*"
    # Keep the source literal, including OCR/TeX wrappers, but stop before a
    # second condition clause or method noise.  This covers both ``5 × 10^-3
    # s^-1`` and ``$1\\times10^{-3}\\,\\mathrm{s}^{-1}$`` forms.
    r"(?=[^;.!?]*(?:\d|\\d)).*?"
    r"(?=(?:\s+(?:using|with|on|along|parallel|perpendicular)\b|"
    r"\s*,?\s*at\s+least\s+(?:three|four|five|six|\d+)\s+"
    r"(?:tensile\s+)?(?:specimens?|samples?|coupons?)\b|"
    r"\s+and\s+(?:an?|the)\s+"
    r"(?:experimental\s+)?(?:temperature|environment)\b|;|"
    r"[.!?](?:\s|$)|$))|"
    r"[-+]?\d+(?:\.\d+)?\s*(?:mm\s*/\s*min|%\s*/\s*min|"
    r"mm\s*min\s*\^?\s*[-−]?\s*1|min\s*\^?\s*[-−]?\s*1|"
    r"s\s*\^?\s*[-−]?\s*1)\b)"
)
_ORIENTATION_PHRASE = re.compile(
    r"(?ix)(?:\b(?:horizontal|vertical|transverse|longitudinal|parallel|"
    r"perpendicular)\b(?:\s+to\s+(?:the\s+)?(?:build(?:ing)?\s+direction|"
    r"deposition\s+direction|scan\s+direction))?|"
    r"\b(?:along|parallel|perpendicular)\s+(?:to\s+)?(?:the\s+)?"
    r"(?:RD|TD|ND|BD|GD)\b(?:\s*\([^.;]{1,100}\))?|"
    r"\bbuild\s+direction\b)"
)
_ENVIRONMENT_PHRASE = re.compile(
    r"(?ix)(?:\b(?:in|under|within)\s+)?(?:air|vacuum|argon|"
    r"inert\s+(?:gas|atmosphere)|hydrogen|laboratory\s+atmosphere)\b"
)

_PROTOCOL_SPECIMEN_GEOMETRY = re.compile(
    r"(?ix)(?:"
    r"\b(?:dog[\s-]*bone|dumbbell)[\s-]*(?:shaped?\s+)?(?:tensile\s+)?"
    r"(?:specimens?|samples?|coupons?)\b|"
    r"\b(?:gauge|gage)\s+(?:length|width|diameter|section)\s*"
    r"(?:of|=|:)?\s*[-+]?\d+(?:\.\d+)?\s*(?:mm|cm|m|µm|um)\b|"
    r"\b(?:cylindrical|flat|rectangular|round)\s+(?:tensile\s+)?"
    r"(?:specimens?|samples?|coupons?)\b)"
)
_PROTOCOL_REPLICATE_VALUE = re.compile(
    r"(?ix)(?:"
    r"\b(?:at\s+least\s+)?(?:three|four|five|six|seven|eight|nine|ten|\d+)\s+"
    r"(?:tensile\s+)?(?:specimens?|samples?|coupons?)\s+were\s+tested\b|"
    r"\b(?:tensile\s+)?tests?\s+were\s+(?:repeated|replicated)\s+"
    r"(?:at\s+least\s+)?(?:three|four|five|six|seven|eight|nine|ten|\d+)\s+"
    r"times\b)"
)
_PROTOCOL_HOLD_TIME = re.compile(
    r"(?ix)(?:"
    r"\bafter\s+(?:a|an|the)?\s*[-+]?\d+(?:\.\d+)?\s*"
    r"(?:s|sec(?:ond)?s?|min(?:ute)?s?|h(?:our)?s?)\s+hold\b|"
    r"\b(?:hold(?:ing)?|soak(?:ing)?)\s+(?:time\s+)?(?:of|=|:)?\s*"
    r"[-+]?\d+(?:\.\d+)?\s*(?:s|sec(?:ond)?s?|min(?:ute)?s?|h(?:our)?s?)\b)"
)


def property_context_recovery_enabled() -> bool:
    """Return the model-agnostic feature switch (enabled by default)."""

    raw = os.getenv("KNOWMAT2_ALPHA25_PROPERTY_CONTEXT_RECOVERY", "1")
    return raw.strip().casefold() not in {"0", "false", "no", "off", "disabled"}


def tensile_protocol_ledger_v203_enabled() -> bool:
    """Return whether the source-proven v203 tensile ledger is enabled."""

    raw = os.getenv("KNOWMAT2_ALPHA25_TENSILE_PROTOCOL_LEDGER_V203", "1")
    return raw.strip().casefold() not in {
        "0",
        "false",
        "no",
        "off",
        "disabled",
    }


def _fold(value: Any) -> str:
    text = str(value or "").casefold()
    # OCR and Markdown frequently alternate hyphen-minus, en/em dashes, and
    # non-breaking hyphens inside sample labels (for example
    # ``Cu-12%-CNP`` vs ``Cu-12%–CNP``).  They are presentation variants, not
    # different owner identities.  Canonicalizing them here makes the
    # property-local owner/protocol checks deterministic without fuzzy
    # chemistry matching.
    text = re.sub(r"[\u2010-\u2015\u2212\uFE58\uFE63\uFF0D]", "-", text)
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


def _property_is_core_tensile(row: dict[str, Any]) -> bool:
    """Keep the core scalar tensile precision guard independent of imports."""

    name = str(row.get("property_name_raw") or "")
    if _CORE_TENSILE_PROPERTY.search(name):
        return True
    return bool(_TENSILE_ABBREVIATION.fullmatch(name))


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
    values.update(_temperature_keys(text))
    return tuple(sorted(values))


def _temperature_keys(text: str) -> tuple[str, ...]:
    """Canonicalize source-literal temperature spellings for compatibility."""

    keys: set[str] = set()
    for match in _TEMPERATURE_VALUE.finditer(text):
        literal = _fold(match.group(0))
        if literal == "rt" or literal.startswith(
            ("room temperature", "ambient temperature")
        ):
            keys.add("room temperature")
            continue
        number_match = re.search(r"[-+]?\d+(?:\.\d+)?", literal)
        if number_match is None:
            continue
        number = float(number_match.group(0))
        # TeX OCR commonly renders Celsius as ``^\circC`` while properties use
        # the Unicode degree sign.  Canonical Kelvin keys let those literal
        # presentations intersect without changing the preserved source text.
        celsius = "circ" in literal or "°" in literal or literal.endswith("c")
        kelvin = number + 273.15 if celsius else number
        keys.add(f"temperature_k:{kelvin:.2f}")
    return tuple(sorted(keys))


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
    if not values:
        # Some methods state a bare speed (``5 mm/min``) without the words
        # ``strain rate``.  Preserve a comparable canonical dimension so a
        # partial condition can be augmented and duplicate protocol fragments
        # are not treated as already present.
        bare = re.compile(
            r"(?ix)([-+]?\d+(?:\.\d+)?)\s*(mm\s*/\s*min|"
            r"mm\s*min\s*\^?\s*[-−]?\s*1|%\s*/\s*min|"
            r"min\s*\^?\s*[-−]?\s*1|s\s*\^?\s*[-−]?\s*1)"
        )
        for match in bare.finditer(cleaned):
            number, unit = match.groups()
            values.add(
                f"rate:{number}:{re.sub(r'\s+', '', unit or '')}"
            )
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
    explicit_global_scope: bool = False
    global_scope_evidence: str = ""
    foreign_global_scope_evidence: str = ""

    def audit_dict(self) -> dict[str, Any]:
        return {
            "line_start": self.line_start,
            "line_end": self.line_end,
            "heading": self.heading,
            "score": self.score,
            "discriminators": self.discriminators,
            "explicit_global_scope": self.explicit_global_scope,
            "global_scope_evidence": self.global_scope_evidence,
            "text": self.text,
        }


@dataclass(frozen=True)
class PropertyContextDecision:
    status: RecoveryStatus
    reason: str
    condition_raw: str | None = None
    owner_qualifier: str | None = None
    shared_scope_risk: bool = False
    selected: tuple[TestContextCandidate, ...] = ()
    candidates: tuple[TestContextCandidate, ...] = ()
    rejected: tuple[TestContextCandidate, ...] = ()
    accepted_fragments: tuple[str, ...] = ()


def has_explicit_global_tensile_scope(
    decision: PropertyContextDecision,
) -> bool:
    """Return whether the selected source protocol explicitly covers all tests."""

    if decision.status not in {"recovered", "augmented"} or not decision.selected:
        return False
    return any(candidate.explicit_global_scope for candidate in decision.selected)


def _global_tensile_scope_evidence(text: str) -> str:
    """Return a universal cue owned by this bounded tensile event only.

    A Markdown paragraph can contain tensile and fatigue procedures together.
    The former implementation searched that whole paragraph, allowing a cue
    such as ``all the specimens`` from the fatigue sentence to authorize a
    tensile-condition projection.  Candidates are already built from one
    tensile anchor plus compatible continuations, so inspect only that literal
    event and reject any sentence whose own proposition names another test
    family.
    """

    if not _TENSILE_METHOD.search(text):
        return ""
    for sentence in re.split(r"(?<=[.!?])\s+(?=[A-Z0-9])", text):
        candidate = sentence.strip()
        if not candidate or not _EXPLICIT_GLOBAL_TENSILE_SCOPE.search(candidate):
            continue
        if _OTHER_TEST_FAMILY.search(candidate):
            continue
        return candidate
    return ""


def _foreign_global_scope_evidence(text: str) -> str:
    """Return a nearby universal cue owned by a non-tensile test event.

    A unique dense tensile table is not enough to borrow a methods protocol
    when the same bounded paragraph gives ``all specimens`` scope to fatigue,
    creep, or another test family.  Retain that competing proposition on the
    tensile candidate so the v203 ledger can fail closed without merging the
    two events or losing their literal audit evidence.
    """

    for sentence in re.split(r"(?<=[.!?])\s+(?=[A-Z0-9])", text):
        candidate = sentence.strip()
        if (
            candidate
            and _EXPLICIT_GLOBAL_TENSILE_SCOPE.search(candidate)
            and _OTHER_TEST_FAMILY.search(candidate)
        ):
            return candidate
    return ""


def _candidate_from_block(
    line_start: int,
    line_end: int,
    heading: str,
    text: str,
    *,
    source_order: int = 0,
    scope_text: str = "",
    neighbor_text: str = "",
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
    if not _condition_detail_count(text):
        # Specimen/equipment/replicate-only methods are retained in the
        # candidate audit only when a Property already has a condition that
        # can be checked against them; they must not create a new condition
        # by themselves.
        return None
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
    discriminators = _condition_discriminators(text)
    global_scope_evidence = _global_tensile_scope_evidence(scope_text or text)
    foreign_global_scope_evidence = _foreign_global_scope_evidence(
        neighbor_text or text
    )
    return TestContextCandidate(
        text=text,
        line_start=line_start,
        line_end=line_end,
        heading=heading,
        score=score,
        discriminators=discriminators,
        source_order=source_order,
        explicit_global_scope=bool(global_scope_evidence),
        global_scope_evidence=global_scope_evidence,
        foreign_global_scope_evidence=foreign_global_scope_evidence,
    )


def _condition_discriminators(text: str) -> dict[str, tuple[str, ...]]:
    """Return comparable, source-literal test-protocol dimensions."""

    values = {
        name: tuple(
            sorted(
                {
                    _fold(match.group(0))
                    for match in pattern.finditer(text)
                    if _fold(match.group(0))
                }
            )
        )
        for name, pattern in _DETAIL_PATTERNS.items()
    }
    values.update(
        {
            "temperature": _temperature_values(text),
            "rate": _rate_values(text),
            "standard": _normalized_values(_STANDARD_VALUE, text),
            "orientation": _normalized_values(_ORIENTATION_VALUE, text),
        }
    )
    return values


def _protocol_detail_count(text: str) -> int:
    return sum(bool(pattern.search(text)) for pattern in _DETAIL_PATTERNS.values())


def _condition_detail_count(text: str) -> int:
    """Count only dimensions suitable for a Property condition.

    A methods block containing only ``Instron``, ``dog-bone``, ``DIC`` or a
    replicate count is useful audit evidence, but it is not a safe source for
    ``test_condition_raw``.  Keeping this gate separate from the broad
    protocol-detail count prevents those method-only blocks from becoming
    competing recovery candidates.
    """

    discriminators = _condition_discriminators(text)
    count = sum(bool(discriminators.get(key)) for key in _CONDITION_DETAIL_KEYS)
    # ``_rate_values`` intentionally remains conservative for compatibility
    # with existing audit normalization, but the broad rate grammar also
    # recognizes source forms such as ``5 mm/min`` and ``0.6 mm min^-1``.
    if not discriminators.get("rate") and _DETAIL_PATTERNS["rate"].search(text):
        count += 1
    return count


def _temperature_match_is_material_state(text: str, match: re.Match[str]) -> bool:
    """Return whether a temperature token belongs to material preparation."""

    prefix = text[max(0, match.start() - 45) : match.start()]
    return bool(
        re.search(
            r"(?ix)\b(?:heat[\s-]*treated|annealed|aged|sintered|"
            r"solutionized|homogenized|stress[\s-]*relieved)\s+at\s*$",
            prefix,
        )
    )


def _condition_spans(
    sentence: str,
    *,
    include_temperature: bool,
) -> list[tuple[int, int]]:
    """Find source spans for compact, property-relevant protocol details."""

    spans: list[tuple[int, int]] = []
    if include_temperature:
        spans.extend(
            (match.start(), match.end())
            for match in _TEMPERATURE_VALUE.finditer(sentence)
            if not _temperature_match_is_material_state(sentence, match)
        )
    spans.extend((match.start(), match.end()) for match in _RATE_LITERAL.finditer(sentence))
    spans.extend((match.start(), match.end()) for match in _STANDARD_VALUE.finditer(sentence))
    spans.extend((match.start(), match.end()) for match in _ORIENTATION_PHRASE.finditer(sentence))
    spans.extend((match.start(), match.end()) for match in _ENVIRONMENT_PHRASE.finditer(sentence))
    return sorted(set(spans))


def _expand_condition_start(sentence: str, position: int) -> int:
    """Include a short source connective (``at``, ``according to``, etc.)."""

    prefix = sentence[:position]
    match = _CONDITION_PREFIX.search(prefix)
    modifier = re.search(
        r"(?ix)\b(?:initial|nominal|constant|engineering|true)\s*$", prefix
    )
    if modifier is not None:
        before_modifier = prefix[: modifier.start()]
        connective = _CONDITION_PREFIX.search(before_modifier)
        return connective.start() if connective is not None else modifier.start()
    return match.start() if match else position


def _compact_condition_sentence(
    sentence: str,
    *,
    include_temperature: bool,
) -> str | None:
    """Project one sentence to source-literal condition text.

    The returned text deliberately excludes method transport noise such as
    equipment, specimen preparation, DIC, and replicate counts.  It never
    paraphrases a value: every token comes from the source sentence.
    """

    spans = _condition_spans(sentence, include_temperature=include_temperature)
    if not spans:
        return None
    chunks: list[tuple[int, int]] = []
    start = _expand_condition_start(sentence, spans[0][0])
    end = spans[0][1]
    for span_start, span_end in spans[1:]:
        tail = _CONDITION_TAIL_NOISE.search(sentence, pos=end)
        if tail is not None and tail.start() < span_start:
            chunks.append((start, min(end, tail.start())))
            start = _expand_condition_start(sentence, span_start)
        end = max(end, span_end)
    tail = _CONDITION_TAIL_NOISE.search(sentence, pos=end)
    if tail is not None:
        end = min(end, tail.start())
    chunks.append((start, end))
    fragments = [sentence[left:right].strip(" ,;:") for left, right in chunks]
    fragments = [fragment for fragment in fragments if fragment]
    fragment = "; ".join(dict.fromkeys(fragments))
    if not fragment:
        return None
    # A pure value token (for example ``650 °C``) is still source-grounded,
    # but a lone ``build direction`` token is too weak without its orientation
    # relation.  The latter is retained when the source supplies a relation.
    if not _condition_detail_count(fragment):
        return None
    return fragment


def _compact_condition_fragments(
    text: str,
    *,
    existing_temperature_keys: set[str],
) -> tuple[str, ...]:
    """Return compact source-literal details from selected protocol text."""

    candidate_temperature_keys = set(_temperature_keys(text))
    candidate_has_matrix = len(candidate_temperature_keys) > 1
    if candidate_has_matrix and not existing_temperature_keys:
        # Do not choose one member of a paper-level matrix by order or score.
        return ()
    # If the Property already carries a temperature, keep its source spelling
    # and add only missing dimensions.  Re-appending a TeX/OCR spelling of the
    # same temperature creates duplicate conditions and can make an otherwise
    # exact owner/temperature match look contradictory downstream.
    include_temperature = not candidate_has_matrix and not existing_temperature_keys
    fragments: list[str] = []
    sentences = [
        sentence.strip()
        for sentence in re.split(r"(?<=[.!?])\s+(?=[A-Z0-9])", text)
        if sentence.strip()
    ]
    for sentence in sentences:
        fragment = _compact_condition_sentence(
            sentence,
            include_temperature=include_temperature,
        )
        if fragment and fragment not in fragments:
            fragments.append(fragment)

    # For a temperature-qualified Property, a multi-temperature protocol may
    # contribute only temperature-neutral details.  If the existing condition
    # names a temperature that is not in the candidate matrix, reject the
    # projection rather than silently attaching a foreign protocol.
    if candidate_has_matrix:
        if len(existing_temperature_keys) != 1 or not existing_temperature_keys <= candidate_temperature_keys:
            return ()
    return tuple(fragments)


def _is_complete_executed_tensile_event(text: str) -> bool:
    """Return whether a sentence independently reports an executed test.

    Specimen-preparation clauses can repeat a tensile noun immediately before
    the sentence that carries the actual standard or loading rate.  Treating
    every repeated noun as a new protocol strands those details.  Conversely,
    two independently executed tests must remain separate candidates.
    """

    if not _TENSILE_TEST_EVENT.search(text) or not _protocol_detail_count(text):
        return False
    return bool(
        re.search(
            r"(?ix)\b(?:perform(?:ed|ing)?|conduct(?:ed|ing)?|carried\s+out|"
            r"subject(?:ed|ing)?|test(?:ed|ing)|execut(?:ed|ing)?|"
            r"load(?:ed|ing)?)\b",
            text,
        )
    )


def _continuation_is_compatible(anchor: str, following: str) -> bool:
    """Accept a bounded procedural continuation without merging two tests."""

    if _OTHER_TEST_FAMILY.search(following):
        return False
    if not _PROCEDURE_ACTION.search(following) or not _protocol_detail_count(
        following
    ):
        return False

    anchor_discriminators = _condition_discriminators(anchor)
    following_discriminators = _condition_discriminators(following)
    for key in ("temperature", "rate", "standard", "orientation"):
        anchor_values = set(anchor_discriminators.get(key, ()))
        following_values = set(following_discriminators.get(key, ()))
        if anchor_values and following_values and anchor_values.isdisjoint(
            following_values
        ):
            return False

    if (
        _TENSILE_METHOD.search(following)
        and _is_complete_executed_tensile_event(anchor)
        and _is_complete_executed_tensile_event(following)
    ):
        return False
    return True


def extract_tensile_test_contexts(source_text: str) -> tuple[TestContextCandidate, ...]:
    """Extract detailed, literal tensile-method blocks from OCR Markdown."""

    candidates: list[TestContextCandidate] = []
    seen: set[str] = set()
    absorbed_anchors: set[tuple[int, int]] = set()
    for line_start, line_end, heading, text in _markdown_blocks(source_text):
        sentences = [
            sentence.strip()
            for sentence in re.split(r"(?<=[.!?])\s+(?=[A-Z0-9])", text)
            if sentence.strip()
        ]
        for index, sentence in enumerate(sentences):
            anchor_key = (line_start, index)
            if anchor_key in absorbed_anchors:
                continue
            if not _TENSILE_METHOD.search(sentence):
                continue
            parts = [sentence]
            absorbed_here: list[tuple[int, int]] = []
            # A following sentence such as "Specimens were tested at ..." may
            # carry the rate while relying on the explicit tensile noun in the
            # previous sentence.  Include it only until another tensile anchor
            # starts a potentially distinct protocol.
            for following_index in range(index + 1, min(index + 4, len(sentences))):
                following = sentences[following_index]
                if not _continuation_is_compatible(" ".join(parts), following):
                    break
                parts.append(following)
                if _TENSILE_METHOD.search(following):
                    absorbed_here.append((line_start, following_index))
            literal = " ".join(parts)
            candidate = _candidate_from_block(
                line_start,
                line_end,
                heading,
                literal,
                source_order=line_start * 10_000 + index,
                scope_text=literal,
                neighbor_text=text,
            )
            if candidate is None:
                continue
            signature = _fold(candidate.text)
            if signature in seen:
                continue
            seen.add(signature)
            candidates.append(candidate)
            absorbed_anchors.update(absorbed_here)
    return tuple(candidates)


def _conflicting(left: TestContextCandidate, right: TestContextCandidate) -> bool:
    for key in ("temperature", "rate", "standard", "orientation"):
        left_values = set(left.discriminators.get(key, ()))
        right_values = set(right.discriminators.get(key, ()))
        if left_values and right_values and left_values.isdisjoint(right_values):
            return True
    return False


def _conflicts_with_discriminators(
    candidate: TestContextCandidate,
    existing: dict[str, tuple[str, ...]],
) -> bool:
    for key in ("temperature", "rate", "standard", "orientation"):
        candidate_values = set(candidate.discriminators.get(key, ()))
        existing_values = set(existing.get(key, ()))
        if candidate_values and existing_values and candidate_values.isdisjoint(
            existing_values
        ):
            return True
    return False


def _hint_matches(candidate: TestContextCandidate, hint: str) -> int:
    score = 0
    for values in candidate.discriminators.values():
        score += sum(value in hint for value in values if value)
    return score


def _property_evidence_matches_candidate(
    row: dict[str, Any], candidate: TestContextCandidate
) -> bool:
    """Return whether a Property assertion carries one candidate coordinate.

    A paper-level tensile method is not automatically the condition of every
    value in a multi-owner paper.  This helper only accepts a literal,
    property-local discriminator (temperature, rate, standard, orientation, or
    environment) that occurs in the candidate's own evidence bundle.  It is
    deliberately source-only and does not inspect neighboring chunks or infer
    that all samples used the same protocol.
    """

    evidence_rows = (
        row.get("source_evidence")
        if isinstance(row.get("source_evidence"), list)
        else [row.get("source_evidence")]
    )
    evidence = "\n".join(str(value or "") for value in evidence_rows if value)
    if not evidence.strip():
        return False
    evidence_discriminators = _condition_discriminators(evidence)
    for key in ("temperature", "rate", "standard", "orientation", "environment"):
        candidate_values = set(candidate.discriminators.get(key, ()))
        if not candidate_values:
            continue
        if key == "temperature":
            if set(_temperature_keys(evidence)) & set(_temperature_keys(candidate.text)):
                return True
            continue
        if candidate_values & set(evidence_discriminators.get(key, ())):
            return True
    return False


def _property_evidence_mentions_owner(
    row: dict[str, Any], owner_labels: Sequence[str]
) -> bool:
    """Return whether the value quote names one current owner literally.

    A paper-level tensile Methods paragraph may be valid for several samples,
    but it is not a coordinate for a value whose own evidence lost its owner
    during chunking.  This helper deliberately checks only the Property's
    evidence bundle and uses the same boundary-aware owner matcher as the
    matrix/owner recovery path; it never performs a chemistry or alias lookup
    outside the labels already selected for this material.
    """

    evidence_rows = (
        row.get("source_evidence")
        if isinstance(row.get("source_evidence"), list)
        else [row.get("source_evidence")]
    )
    evidence = "\n".join(str(value or "") for value in evidence_rows if value)
    if not evidence.strip():
        return False
    return any(_owner_label_in_text(label, evidence) for label in owner_labels)


def _owner_label_in_text(label: str, text: str) -> bool:
    """Match a source owner label without substring or punctuation accidents."""

    folded_label = _fold(label)
    if len(folded_label) < 2 or folded_label in _UNREPORTED:
        return False
    folded_text = _fold(text)
    return bool(
        re.search(
            rf"(?<![a-z0-9]){re.escape(folded_label)}(?![a-z0-9])",
            folded_text,
        )
    )


def _mentions_any_owner(
    candidate: TestContextCandidate, labels: Sequence[str]
) -> bool:
    return any(_owner_label_in_text(label, candidate.text) for label in labels)


# These are deliberately narrow.  A material name is not a test condition,
# while a source-named delay/orientation column can disambiguate one member of
# a shared tensile protocol matrix.  Do not turn arbitrary state labels (for
# example ``aged at 745 °C``) into a condition merely because they are owners.
_MATRIX_OWNER_QUALIFIER = re.compile(
    r"(?ix)(?:"
    r"\b(?:interlayer|interpass)\s+delays?\b|"
    r"\bdelays?\b|"
    r"\b(?:horizontal|vertical|transverse|longitudinal)\b"
    r")"
)


def _condition_owner_qualifier(label: str) -> bool:
    """Return whether an owner label can safely qualify a shared protocol."""

    folded = _fold(label)
    if not folded or _is_unreported(folded):
        return False
    if not _MATRIX_OWNER_QUALIFIER.search(folded):
        return False
    # A bare word such as ``delay`` is not an owner.  Require either a
    # numeric/time value or an explicit orientation token.
    return bool(
        re.search(
            r"(?ix)(?:\b[-+]?\d+(?:\.\d+)?\s*(?:s|sec(?:ond)?s?|"
            r"min(?:ute)?s?|h(?:our)?s?)\b)|"
            r"\b(?:horizontal|vertical|transverse|longitudinal)\b",
            folded,
        )
    )


def _source_owner_qualifier(
    owner_labels: Sequence[str],
    other_owner_labels: Sequence[str],
    evidence: Sequence[Any],
) -> str | None:
    """Find one current-owner matrix qualifier explicitly present in evidence.

    The source evidence for a table property commonly contains the header and
    the complete row, so the current owner label is source-grounded even when
    the extracted property payload lost the column metadata.  We require at
    least two distinct qualifier labels in that same evidence bundle; this
    prevents ordinary prose/state labels from being promoted to test
    conditions and limits the rule to a genuine comparison matrix.
    """

    text = "\n".join(str(value or "") for value in evidence if value)
    if not text or "|" not in text:
        return None
    current = [
        str(label).strip()
        for label in owner_labels
        if _condition_owner_qualifier(str(label))
        and _owner_label_in_text(str(label), text)
    ]
    if not current:
        return None
    all_labels = [*owner_labels, *other_owner_labels]
    matrix_labels = {
        _fold(label)
        for label in all_labels
        if _condition_owner_qualifier(str(label))
        and _owner_label_in_text(str(label), text)
    }
    if len(matrix_labels) < 2:
        return None
    # Prefer the shortest explicit label (``0 s Delay`` over a longer alias
    # such as ``single-bead wall deposited with 0 s interlayer delay``) so the
    # audit string remains compact and source-literal.
    return min(current, key=lambda value: (len(value), value.casefold()))


def _matrix_owner_sentence(text: str) -> bool:
    """Return whether a sentence enumerates multiple comparison owners."""

    if not _MATRIX_OWNER_QUALIFIER.search(text):
        return False
    # ``0, 120, and 300 s interlayer delays`` carries the unit only once, so
    # count nearby numeric values rather than requiring ``number + unit`` for
    # every item.  A two-value matrix is sufficient to be ambiguous.
    return len(
        re.findall(r"(?<![A-Za-z0-9])[-+]?\d+(?:\.\d+)?", text)
    ) >= 2


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


def _source_literal_shared_fragments(
    candidate: TestContextCandidate,
    existing_temperature_keys: set[str],
) -> tuple[str, ...]:
    """Project only compact, source-literal condition dimensions.

    The selected candidate remains complete in the audit payload.  The public
    Property receives only temperature/rate/standard/orientation/environment
    fragments, so a unique method block cannot reintroduce specimen geometry,
    equipment, DIC, or replicate prose into every value in the paper.
    """

    return _compact_condition_fragments(
        candidate.text,
        existing_temperature_keys=existing_temperature_keys,
    )


def _condition_fragments(
    selected: tuple[TestContextCandidate, ...],
    existing_condition: str,
) -> tuple[str, ...]:
    existing_temperature_keys = set(_temperature_keys(existing_condition))
    if not existing_temperature_keys and any(
        len(_temperature_keys(candidate.text)) > 1 for candidate in selected
    ):
        return ()

    fragments: list[str] = []
    for candidate in selected:
        projected = _source_literal_shared_fragments(
            candidate, existing_temperature_keys
        )
        for fragment in projected:
            if fragment not in fragments:
                fragments.append(fragment)
    return tuple(fragments)


def _fragments_add_protocol_detail(
    fragments: tuple[str, ...],
    existing: dict[str, tuple[str, ...]],
) -> bool:
    for fragment in fragments:
        for key, values in _condition_discriminators(fragment).items():
            if key == "temperature":
                fragment_values = set(_temperature_keys(fragment))
                existing_values = set(
                    _temperature_keys(" ".join(existing.get(key, ())))
                )
            else:
                fragment_values = set(values)
                existing_values = set(existing.get(key, ()))
            if fragment_values - existing_values:
                return True
    return False


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
        owner_labels: Sequence[str] = (),
        other_owner_labels: Sequence[str] = (),
    ) -> PropertyContextDecision:
        if not self._enabled:
            return PropertyContextDecision("disabled", "feature flag is disabled")
        existing_condition = str(row.get("test_condition_raw") or "").strip()
        has_existing = not _is_unreported(existing_condition)
        if not _property_is_tensile(row):
            return PropertyContextDecision(
                "existing" if has_existing else "ineligible",
                (
                    "property already has a reported non-tensile condition"
                    if has_existing
                    else "property is not an explicit tensile family"
                ),
            )
        if not self._candidates:
            return PropertyContextDecision(
                "existing" if has_existing else "not_found",
                (
                    "property condition was preserved because no detailed tensile procedure was found"
                    if has_existing
                    else "no detailed tensile procedure was found"
                ),
            )
        reference_reason = _reference_ineligibility_reason(row, owner_role)
        if reference_reason:
            return PropertyContextDecision(
                "existing" if has_existing else "reference", reference_reason
            )

        all_candidates = self._candidates
        shared_scope_risk = False
        owner_candidates = tuple(
            candidate
            for candidate in all_candidates
            if _mentions_any_owner(candidate, owner_labels)
        )
        if owner_candidates:
            eligible_candidates = owner_candidates
            rejected_candidates = tuple(
                candidate
                for candidate in all_candidates
                if candidate not in owner_candidates
            )
        else:
            other_owned = tuple(
                candidate
                for candidate in all_candidates
                if _mentions_any_owner(candidate, other_owner_labels)
            )
            # When several material/state owners are present, a candidate that
            # is only a paper-level protocol is not a safe condition for the
            # current Property.  Require either a literal protocol
            # discriminator in the Property's own evidence or a source-named
            # matrix qualifier (for example ``300 s Delay``) carried by the
            # property table.  Explicitly owner-bound foreign candidates are
            # left to the existing ``other_owned`` branch so callers retain a
            # precise different-owner audit reason.
            matrix_qualifier = _source_owner_qualifier(
                owner_labels,
                other_owner_labels,
                row.get("source_evidence")
                if isinstance(row.get("source_evidence"), list)
                else [row.get("source_evidence")],
            )
            # For core tensile values, an owner+value sentence is still not a
            # protocol coordinate.  In a multi-owner paper, inheriting a
            # paper-level rate/temperature/orientation from Methods can attach
            # the wrong condition to a result (the common chunk-loss failure).
            # Only a discriminator in the value's own evidence or a literal
            # matrix/table owner qualifier may authorize recovery.  The full
            # selected method remains in the audit when this risk is raised.
            shared_scope_risk = bool(
                other_owner_labels
                and _property_is_core_tensile(row)
                and not other_owned
                and not matrix_qualifier
                and not any(
                    _property_evidence_matches_candidate(row, candidate)
                    for candidate in all_candidates
                )
            )
            if (
                other_owner_labels
                and not _property_is_core_tensile(row)
                and not other_owned
                and not matrix_qualifier
                and not any(
                    _property_evidence_matches_candidate(row, candidate)
                    for candidate in all_candidates
                )
            ):
                return PropertyContextDecision(
                    "existing" if has_existing else "ambiguous",
                    "a paper-level tensile procedure lacked a property-local owner or protocol discriminator",
                    condition_raw=existing_condition if has_existing else None,
                    candidates=all_candidates,
                    rejected=all_candidates,
                )
            eligible_candidates = tuple(
                candidate
                for candidate in all_candidates
                if candidate not in other_owned
            )
            rejected_candidates = other_owned
            if not eligible_candidates and other_owned:
                return PropertyContextDecision(
                    "ambiguous",
                    "all compatible tensile procedures explicitly belong to a different material owner",
                    candidates=all_candidates,
                    rejected=other_owned,
                )

        existing_discriminators = _condition_discriminators(existing_condition)
        if has_existing:
            compatible_candidates = tuple(
                candidate
                for candidate in eligible_candidates
                if not _conflicts_with_discriminators(
                    candidate, existing_discriminators
                )
            )
            conflicting_candidates = tuple(
                candidate
                for candidate in eligible_candidates
                if candidate not in compatible_candidates
            )
            rejected_candidates = tuple(
                [
                    *rejected_candidates,
                    *(
                        candidate
                        for candidate in conflicting_candidates
                        if candidate not in rejected_candidates
                    ),
                ]
            )
            if not compatible_candidates:
                return PropertyContextDecision(
                    "ambiguous",
                    "the reported property condition conflicts with every candidate tensile procedure",
                    candidates=eligible_candidates,
                    rejected=rejected_candidates,
                )
            eligible_candidates = compatible_candidates

        hint = _fold(
            " | ".join(
                str(value or "")
                for value in (
                    row.get("property_name_raw"),
                    row.get("test_method_raw"),
                    row.get("test_standard_raw"),
                    row.get("test_condition_raw"),
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
            eligible_candidates,
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
                    rejected=rejected_candidates,
                )

        selected = _select_complementary(primary, tuple(ranked))
        accepted_fragments = _condition_fragments(selected, existing_condition)
        if not accepted_fragments:
            if any(len(_temperature_keys(candidate.text)) > 1 for candidate in selected):
                return PropertyContextDecision(
                    "existing" if has_existing else "ambiguous",
                    (
                        "the reported condition was preserved because a multi-temperature "
                        "protocol had no source-literal property-specific projection"
                        if has_existing
                        else "a multi-temperature tensile protocol lacked a property-local temperature discriminator"
                    ),
                    condition_raw=existing_condition if has_existing else None,
                    owner_qualifier=None,
                    selected=selected,
                    candidates=tuple(ranked),
                    rejected=rejected_candidates,
                )
            return PropertyContextDecision(
                "existing" if has_existing else "not_found",
                "the compatible tensile procedure contributed no source-literal protocol detail",
                condition_raw=existing_condition if has_existing else None,
                owner_qualifier=None,
                selected=selected,
                candidates=tuple(ranked),
                rejected=rejected_candidates,
            )
        if accepted_fragments == tuple(candidate.text for candidate in selected):
            condition = _join_selected(selected)
        else:
            condition = "\n\n".join(accepted_fragments)
        owner_qualifier = _source_owner_qualifier(
            owner_labels,
            other_owner_labels,
            row.get("source_evidence")
            if isinstance(row.get("source_evidence"), list)
            else [row.get("source_evidence")],
        )
        # A shared protocol is not, by itself, the material condition.  When a
        # table row explicitly carries one of several source-named comparison
        # owners (for example ``0 s Delay``), retain that literal qualifier so
        # downstream strict matching and human review cannot confuse the row
        # with another owner.  Gate it by the candidate's own matrix sentence;
        # an unrelated table elsewhere in the evidence bundle may not decorate
        # a prose property.
        selected_text = "\n".join(candidate.text for candidate in selected)
        if owner_qualifier and (
            _matrix_owner_sentence(selected_text)
            or _owner_label_in_text(owner_qualifier, selected_text)
        ):
            if not _owner_label_in_text(owner_qualifier, condition):
                condition = f"{owner_qualifier}; {condition}"
        if len(condition) > 4000:
            selected = (primary,)
            accepted_fragments = _condition_fragments(selected, existing_condition)
            if not accepted_fragments:
                return PropertyContextDecision(
                    "existing" if has_existing else "ambiguous",
                    "the bounded protocol projection could not be represented safely",
                    condition_raw=existing_condition if has_existing else None,
                    owner_qualifier=owner_qualifier,
                    selected=selected,
                    candidates=tuple(ranked),
                    rejected=rejected_candidates,
                )
            condition = "\n\n".join(accepted_fragments)
        if has_existing:
            if (
                _fold(condition) in _fold(existing_condition)
                or not _fragments_add_protocol_detail(
                    accepted_fragments, existing_discriminators
                )
            ):
                return PropertyContextDecision(
                    "existing",
                    "the reported condition already contains the compatible protocol details",
                    condition_raw=existing_condition,
                    owner_qualifier=owner_qualifier,
                    selected=selected,
                    candidates=tuple(ranked),
                    rejected=rejected_candidates,
                    shared_scope_risk=shared_scope_risk,
                    accepted_fragments=accepted_fragments,
                )
            condition = f"{existing_condition}\n\n{condition}"
            return PropertyContextDecision(
                "augmented",
                "one compatible paper-level tensile procedure safely completed a partial condition",
                condition_raw=condition,
                owner_qualifier=owner_qualifier,
                selected=selected,
                candidates=tuple(ranked),
                rejected=rejected_candidates,
                shared_scope_risk=shared_scope_risk,
                accepted_fragments=accepted_fragments,
            )
        return PropertyContextDecision(
            "recovered",
            "one compatible paper-level tensile procedure was uniquely identifiable",
            condition_raw=condition,
            owner_qualifier=owner_qualifier,
            selected=selected,
            candidates=tuple(ranked),
            rejected=rejected_candidates,
            shared_scope_risk=shared_scope_risk,
            accepted_fragments=accepted_fragments,
        )


@dataclass(frozen=True)
class TensileProtocolDimension:
    """One source-literal dimension of a bounded tensile method event."""

    name: str
    literals: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {"name": self.name, "literals": list(self.literals)}


@dataclass(frozen=True)
class TensileProtocolEvent:
    """One immutable method event retained by the paper-local v203 ledger."""

    decision_key: str
    text: str
    line_start: int
    line_end: int
    heading: str
    explicit_global_scope: bool
    global_scope_evidence: str
    foreign_global_scope_evidence: str
    dimensions: tuple[TensileProtocolDimension, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "decision_key": self.decision_key,
            "text": self.text,
            "line_start": self.line_start,
            "line_end": self.line_end,
            "heading": self.heading,
            "explicit_global_scope": self.explicit_global_scope,
            "global_scope_evidence": self.global_scope_evidence,
            "foreign_global_scope_evidence": self.foreign_global_scope_evidence,
            "dimensions": [row.to_dict() for row in self.dimensions],
        }


@dataclass(frozen=True)
class TensileProtocolLedgerDecision:
    """Fail-closed v203 decision for binding one Property to one event."""

    status: ProtocolLedgerStatus
    reason: str
    condition_raw: str | None = None
    scope: ProtocolScope = ""
    selected_events: tuple[TensileProtocolEvent, ...] = ()
    candidate_events: tuple[TensileProtocolEvent, ...] = ()
    rejected_events: tuple[TensileProtocolEvent, ...] = ()
    contributed_dimensions: tuple[str, ...] = ()
    base_status: RecoveryStatus | str = "not_found"

    def audit_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "reason": self.reason,
            "condition_raw": self.condition_raw,
            "scope": self.scope,
            "selected_events": [row.to_dict() for row in self.selected_events],
            "candidate_events": [row.to_dict() for row in self.candidate_events],
            "rejected_events": [row.to_dict() for row in self.rejected_events],
            "contributed_dimensions": list(self.contributed_dimensions),
            "base_status": self.base_status,
        }


_PROTOCOL_EQUIPMENT_VALUE = re.compile(
    r"(?ix)\b(?:Instron|MTS|Zwick|Shimadzu|Gleeble)"
    r"(?:\s+[A-Za-z0-9-]+){0,2}(?:\s+servo[\s-]*hydraulic)?\s+"
    r"(?:testing\s+(?:machine|system)|machine|load\s+frame)\b|"
    r"\b(?:universal\s+(?:testing|test)\s+machine|servo[\s-]*hydraulic\s+"
    r"(?:testing\s+machine|load\s+frame)|testing\s+machine|load\s+frame)\b"
)


def _literal_matches(
    pattern: re.Pattern[str], text: str, *, reject_state_temperature: bool = False
) -> tuple[str, ...]:
    rows: list[str] = []
    for match in pattern.finditer(text):
        if reject_state_temperature and _temperature_match_is_material_state(
            text, match
        ):
            continue
        literal = re.sub(r"\s+", " ", match.group(0)).strip(" ,;\n\t")
        if literal and _fold(literal) not in {_fold(row) for row in rows}:
            rows.append(literal)
    return tuple(rows)


def _protocol_dimensions(text: str) -> tuple[TensileProtocolDimension, ...]:
    """Project compact literal dimensions without paraphrasing the method."""

    patterns: tuple[tuple[str, re.Pattern[str], bool], ...] = (
        ("temperature", _TEMPERATURE_VALUE, True),
        ("rate", _RATE_LITERAL, False),
        ("standard", _STANDARD_VALUE, False),
        ("equipment", _PROTOCOL_EQUIPMENT_VALUE, False),
        ("specimen", _PROTOCOL_SPECIMEN_GEOMETRY, False),
        ("orientation", _ORIENTATION_PHRASE, False),
        ("environment", _ENVIRONMENT_PHRASE, False),
        ("strain_measurement", _DETAIL_PATTERNS["strain_measurement"], False),
        ("hold_time", _PROTOCOL_HOLD_TIME, False),
        ("replicates", _PROTOCOL_REPLICATE_VALUE, False),
    )
    dimensions: list[TensileProtocolDimension] = []
    for name, pattern, reject_state_temperature in patterns:
        literals = _literal_matches(
            pattern,
            text,
            reject_state_temperature=reject_state_temperature,
        )
        if name == "strain_measurement" and literals:
            specific = tuple(
                literal
                for literal in literals
                if _fold(literal) not in {"dic", "strain image", "strain images"}
            )
            if specific:
                literals = specific
        if literals:
            dimensions.append(
                TensileProtocolDimension(name=name, literals=literals)
            )
    return tuple(dimensions)


def _protocol_event(candidate: TestContextCandidate) -> TensileProtocolEvent:
    dimensions = _protocol_dimensions(candidate.text)
    payload = {
        "line_start": candidate.line_start,
        "line_end": candidate.line_end,
        "heading": candidate.heading,
        "text": candidate.text,
        "dimensions": [row.to_dict() for row in dimensions],
        "explicit_global_scope": candidate.explicit_global_scope,
        "foreign_global_scope_evidence": candidate.foreign_global_scope_evidence,
    }
    digest = hashlib.sha256(
        json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()
    return TensileProtocolEvent(
        decision_key=f"tensile-protocol-event:{digest}",
        text=candidate.text,
        line_start=candidate.line_start,
        line_end=candidate.line_end,
        heading=candidate.heading,
        explicit_global_scope=candidate.explicit_global_scope,
        global_scope_evidence=candidate.global_scope_evidence,
        foreign_global_scope_evidence=candidate.foreign_global_scope_evidence,
        dimensions=dimensions,
    )


def _event_identity(candidate: TestContextCandidate) -> tuple[Any, ...]:
    return (
        candidate.line_start,
        candidate.line_end,
        candidate.source_order,
        _fold(candidate.text),
    )


def _protocol_coordinate_present(row: dict[str, Any]) -> bool:
    decision_key = str(row.get("property_id_candidate") or "").strip()
    return decision_key.startswith(("table-cell:", "sidecar-cell:", "dense-table-cell:"))


def _selected_protocol_scope(
    row: dict[str, Any],
    selected: Sequence[TestContextCandidate],
    *,
    owner_role: str | None,
    owner_labels: Sequence[str],
    other_owner_labels: Sequence[str],
) -> ProtocolScope:
    if _fold(owner_role) == "reference":
        return "reference_local"
    current_mentions = any(
        _mentions_any_owner(candidate, owner_labels) for candidate in selected
    )
    foreign_mentions = any(
        _mentions_any_owner(candidate, other_owner_labels) for candidate in selected
    )
    if current_mentions and not foreign_mentions:
        return "owner_local"
    if foreign_mentions:
        return "ambiguous"
    if not other_owner_labels:
        return "owner_local"
    if any(
        _property_evidence_matches_candidate(row, candidate)
        for candidate in selected
    ):
        return "owner_local"
    if (
        selected
        and all(candidate.explicit_global_scope for candidate in selected)
        and _protocol_coordinate_present(row)
    ):
        return "target_global"
    return "ambiguous"


def _dimension_already_present(
    name: str, literals: Sequence[str], condition: str
) -> bool:
    if not condition.strip():
        return False
    if name in {"temperature", "rate", "standard", "orientation", "environment"}:
        candidate = _condition_discriminators("; ".join(literals))
        existing = _condition_discriminators(condition)
        if name == "temperature":
            return bool(
                set(_temperature_keys("; ".join(literals)))
                & set(_temperature_keys(condition))
            )
        return bool(set(candidate.get(name, ())) & set(existing.get(name, ())))
    folded_condition = _fold(condition)
    return all(_fold(literal) in folded_condition for literal in literals)


def _append_protocol_dimensions(
    base_condition: str,
    original_condition: str,
    events: Sequence[TensileProtocolEvent],
) -> tuple[str, tuple[str, ...]]:
    parts = [base_condition.strip()] if base_condition.strip() else []
    contributed: list[str] = []
    for event in events:
        for dimension in event.dimensions:
            if not _dimension_already_present(
                dimension.name, dimension.literals, original_condition
            ) and dimension.name not in contributed:
                contributed.append(dimension.name)
            if _dimension_already_present(
                dimension.name, dimension.literals, "; ".join(parts)
            ):
                continue
            for literal in dimension.literals:
                if _fold(literal) not in {_fold(row) for row in parts}:
                    parts.append(literal)
    return "; ".join(parts), tuple(contributed)


def _unique_dense_target_protocol(
    row: dict[str, Any],
    events: Sequence[TensileProtocolEvent],
    rejected_events: Sequence[TensileProtocolEvent],
    *,
    owner_role: str | None,
) -> bool:
    """Authorize one current-study protocol for one dense Target coordinate.

    The table cell itself supplies the immutable property coordinate.  A
    single non-conflicting tensile method event may complete its protocol even
    when the paper inventory contains several state/orientation owners.  Two
    events, a Reference owner, a rejected foreign event, or a multi-valued
    protocol dimension remains fail-closed.
    """

    if (
        _fold(owner_role) != "target"
        or not str(row.get("property_id_candidate") or "").startswith(
            "dense-table-cell:"
        )
        or len(events) != 1
        or rejected_events
    ):
        return False
    event = events[0]
    if not event.dimensions or event.foreign_global_scope_evidence:
        return False
    discriminating = {"temperature", "rate", "standard", "orientation", "environment"}
    return all(
        dimension.name not in discriminating or len(dimension.literals) == 1
        for dimension in event.dimensions
    )


class TensileProtocolLedger:
    """Paper-local source ledger for precision-first v203 condition binding."""

    def __init__(self, source_text: str | None) -> None:
        self._enabled = tensile_protocol_ledger_v203_enabled()
        self._index = PropertyContextIndex(source_text)
        self._candidate_by_identity = {
            _event_identity(candidate): candidate for candidate in self._index.candidates
        }
        self._events = tuple(
            _protocol_event(candidate)
            for candidate in sorted(
                self._index.candidates,
                key=lambda row: (row.source_order, row.line_start, row.text),
            )
        )
        self._event_by_identity = {
            _event_identity(candidate): event
            for candidate, event in zip(
                sorted(
                    self._index.candidates,
                    key=lambda row: (row.source_order, row.line_start, row.text),
                ),
                self._events,
            )
        }

    @property
    def events(self) -> tuple[TensileProtocolEvent, ...]:
        return self._events

    def _events_for(
        self, candidates: Sequence[TestContextCandidate]
    ) -> tuple[TensileProtocolEvent, ...]:
        return tuple(
            event
            for candidate in candidates
            if (event := self._event_by_identity.get(_event_identity(candidate)))
            is not None
        )

    def bind(
        self,
        row: dict[str, Any],
        *,
        owner_role: str | None = None,
        owner_labels: Sequence[str] = (),
        other_owner_labels: Sequence[str] = (),
    ) -> TensileProtocolLedgerDecision:
        original_condition = str(row.get("test_condition_raw") or "").strip()
        if not self._enabled:
            return TensileProtocolLedgerDecision(
                "disabled",
                "v203 tensile protocol ledger is disabled",
                condition_raw=original_condition or None,
                candidate_events=self._events,
                base_status="disabled",
            )

        base = self._index.recover(
            row,
            owner_role=owner_role,
            owner_labels=owner_labels,
            other_owner_labels=other_owner_labels,
        )
        selected_events = self._events_for(base.selected)
        candidate_events = self._events_for(base.candidates) or self._events
        rejected_events = self._events_for(base.rejected)

        if base.status == "reference":
            return TensileProtocolLedgerDecision(
                "reference",
                base.reason,
                condition_raw=original_condition or None,
                scope="reference_local",
                candidate_events=candidate_events,
                rejected_events=rejected_events,
                base_status=base.status,
            )
        if base.status in {"ineligible", "not_found", "disabled"}:
            return TensileProtocolLedgerDecision(
                base.status,
                base.reason,
                condition_raw=original_condition or None,
                candidate_events=candidate_events,
                rejected_events=rejected_events,
                base_status=base.status,
            )
        if base.status == "ambiguous":
            status: ProtocolLedgerStatus = (
                "conflict"
                if original_condition and "conflict" in base.reason.casefold()
                else "ambiguous"
            )
            return TensileProtocolLedgerDecision(
                status,
                base.reason,
                condition_raw=original_condition or None,
                scope="ambiguous",
                candidate_events=candidate_events,
                rejected_events=rejected_events,
                base_status=base.status,
            )

        selected_candidates = tuple(base.selected)
        if not selected_candidates or not selected_events:
            return TensileProtocolLedgerDecision(
                "existing" if original_condition else "not_found",
                base.reason,
                condition_raw=original_condition or None,
                candidate_events=candidate_events,
                rejected_events=rejected_events,
                base_status=base.status,
            )
        scope = _selected_protocol_scope(
            row,
            selected_candidates,
            owner_role=owner_role,
            owner_labels=owner_labels,
            other_owner_labels=other_owner_labels,
        )
        if scope == "ambiguous":
            if _unique_dense_target_protocol(
                row,
                selected_events,
                rejected_events,
                owner_role=owner_role,
            ):
                scope = "target_global"
            else:
                return TensileProtocolLedgerDecision(
                    "ambiguous",
                    "the selected tensile event lacked one owner-local or explicit global source coordinate",
                    condition_raw=original_condition or None,
                    scope=scope,
                    selected_events=selected_events,
                    candidate_events=candidate_events,
                    rejected_events=rejected_events,
                    base_status=base.status,
                )
        if scope == "reference_local":
            return TensileProtocolLedgerDecision(
                "reference",
                "a current-paper Target protocol was not bound to a Reference owner",
                condition_raw=original_condition or None,
                scope=scope,
                candidate_events=candidate_events,
                rejected_events=rejected_events,
                base_status=base.status,
            )

        base_condition = str(base.condition_raw or original_condition).strip()
        condition, contributed = _append_protocol_dimensions(
            base_condition,
            original_condition,
            selected_events,
        )
        if len(condition) > 4000:
            return TensileProtocolLedgerDecision(
                "ambiguous",
                "the bounded tensile protocol could not be serialized within the condition limit",
                condition_raw=original_condition or None,
                scope=scope,
                selected_events=selected_events,
                candidate_events=candidate_events,
                rejected_events=rejected_events,
                base_status=base.status,
            )
        if not contributed:
            return TensileProtocolLedgerDecision(
                "existing",
                "the existing condition already contains every compatible ledger dimension",
                condition_raw=original_condition or condition or None,
                scope=scope,
                selected_events=selected_events,
                candidate_events=candidate_events,
                rejected_events=rejected_events,
                base_status=base.status,
            )
        return TensileProtocolLedgerDecision(
            "bound",
            "one compatible source-proven tensile protocol event supplied missing dimensions",
            condition_raw=condition,
            scope=scope,
            selected_events=selected_events,
            candidate_events=candidate_events,
            rejected_events=rejected_events,
            contributed_dimensions=contributed,
            base_status=base.status,
        )
