"""Deterministic quality gates for paper-level Alpha25 facts.

The extraction model is intentionally treated as a high-recall candidate generator.
This module never invents a fact or repairs one from domain knowledge.  It only checks
whether structured fields are present in their cited evidence, removes unsafe nested
fragments, and builds model-independent semantic signatures for duplicate handling.
"""

from __future__ import annotations

import json
import re
import unicodedata
from copy import deepcopy
from dataclasses import dataclass
from typing import Any, Iterable, Literal, Sequence

from knowmat.alpha25.contracts import (
    AxisFact,
    CompositionFact,
    ProcessingFact,
    PropertyFact,
    StructureFact,
)
from knowmat.alpha25.evidence import normalize_evidence_text


ClaimQualityMode = Literal["off", "safe", "strict"]


_NUMBER = re.compile(r"(?<![A-Za-z0-9])[-+]?\d+(?:\.\d+)?(?:[eE][-+]?\d+)?")
_TEXTUAL_NUMBER = re.compile(
    r"(?i)\b(?:zero|one|two|three|four|five|six|seven|eight|nine|ten|eleven|"
    r"twelve|hundred|thousand|million|billion)\b"
)
_PLACEHOLDER_VALUES = {
    "",
    "n a",
    "na",
    "none",
    "not applicable",
    "not available",
    "not determined",
    "not given",
    "not measured",
    "not provided",
    "not reported",
    "unknown",
    "unspecified",
}
_NON_VALUE_ACTIONS = {
    "analysed",
    "analyzed",
    "assessed",
    "characterized",
    "determined",
    "evaluated",
    "examined",
    "investigated",
    "measured",
    "published",
    "reported",
    "studied",
    "tested",
}
# A creep-life candidate can contain a number while still reporting only a
# test-control event (for example, ``artificially interrupted when the creep
# life reached 1500 h``).  The number is a timestamp/stop condition, not a
# measured lifetime, and must not be promoted as a scalar Property.
_CREEP_LIFE_EVENT_VALUE = re.compile(
    r"(?ix)\b(?:artificially\s+)?(?:interrupt(?:ed|ing)|stop(?:ped|ping)|"
    r"terminat(?:ed|ing)|halt(?:ed|ing)|suspend(?:ed|ing)|"
    r"pause(?:d|ing))\b"
    r"|\b(?:when|before|after)\s+the\s+(?:creep\s+)?life\s+"
    r"(?:reach(?:ed|es|ing)?|exceed(?:ed|s|ing)?)\b"
    r"|\b(?:test|testing)\s+(?:was|were)\s+(?:artificially\s+)?"
    r"(?:interrupt|stop|terminat|halt|suspend)"
)
_STRUCTURAL_COMPOSITION_VALUE = re.compile(
    r"(?i)\b(?:appear(?:s|ed)?|form(?:s|ed|ation)?|observed|present|located|"
    r"precipitat(?:e|ed|ion)|matrix|film|phase|structure|interface|region)\b"
)
_STRUCTURAL_CONTEXT_ONLY_NAME = re.compile(
    r"(?i)^\s*(?:interior|wall|matrix|interface|region|location|area|zone)\s*$"
)
_MEASURED_COMPOSITION_CONTEXT = re.compile(
    r"(?i)(?:\bmeasur(?:e|ed|ement)|\bactual|\banaly(?:sis|sed|zed)|"
    r"\bquantif(?:y|ied|ication)|\b(?:eds|edx|icp|xrf|oes)\b|spectro|"
    r"chemical\s+composition|composition\s*\(|concentration|content|"
    r"\b(?:wt|at|vol|mol)\s*\.?\s*%)"
)

# Composition candidates are often emitted from prose chunks rather than a
# complete table cell. In that setting the model can turn comparison language
# (``higher``, ``reduced``, ``present``) or an unresolved placeholder into a
# component amount. Those strings remain useful audit evidence, but they are
# not composition amounts and must not enter the materialized Composition axis.
_COMPOSITION_BALANCE_VALUE = re.compile(
    r"(?ix)^\s*(?:bal(?:ance)?\.?|remainder(?:\s+of)?\s+"
    r"[A-Za-z][A-Za-z0-9_{}'′]*)\s*$"
)
_COMPOSITION_COMPARATIVE_VALUE = re.compile(
    r"(?ix)\b(?:higher|lower|greater|less|similar|comparable|"
    r"increas(?:e|ed|es|ing)|decreas(?:e|ed|es|ing)|reduc(?:e|ed|es|ing)|"
    r"drop(?:s|ped|ping)?|gain(?:s|ed|ing)?|loss|deplet(?:ed|ion)|"
    r"enrich(?:ed|ment)?|rich|present|absent|typical|significant(?:ly)?|"
    r"unknown|not\s+reported)\b"
)
_COMPOSITION_TREND_NAME = re.compile(
    r"(?ix)\b(?:trend|content|concentration|enrichment|depletion|"
    r"segregation|partition(?:ing)?)\b"
)
_COMPOSITION_DESIGNATION_VALUE = re.compile(
    r"(?ix)^\s*(?:addition|added|alloyed|nominal|base|matrix|remainder)\s*$"
)
_COMPOSITION_FORMULA_VALUE = re.compile(
    # Keep element-symbol capitalization significant.  With ``re.I`` an
    # ordinary word such as ``present`` or ``unknown`` is tokenized as if it
    # were a multi-element chemical formula and bypasses the qualitative gate.
    r"(?x)^(?:[A-Z][a-z]?\s*(?:[_{\[]?\s*\d+(?:\.\d+)?\s*[_}\]]?)?"
    r"(?:\s*[-+(),/]\s*|\s+)?){2,}$"
)
_COMPOSITION_EXPLICIT_QUANTITY = re.compile(
    r"(?ix)(?<![A-Za-z0-9])[-+~≈]?\d+(?:\.\d+)?(?:\s*[-–]\s*\d+(?:\.\d+)?)?"
    r"\s*(?:%|percent(?:age)?|pct\.?|at\.?\s*%?|wt\.?\s*%?|vol\.?\s*%?|"
    r"ppm|ppb|[A-Za-zμµ°][A-Za-z0-9μµ°/%·._^{}\\-]*)"
)
# ``_COMPOSITION_EXPLICIT_QUANTITY`` is intentionally a search pattern: it is
# useful for finding a quantity inside a larger source sentence.  It must not
# be used to decide whether a whole categorical component is numeric, because
# prose such as ``declines ... in the case of a 0 s delay`` contains a number
# and a unit-like token but is still a qualitative trend.  This anchored form
# accepts only a standalone amount (with an optional uncertainty/range and a
# composition unit), so a number embedded in a trend/procedure cannot be
# silently retyped as ``scalar``.
_COMPOSITION_NUMERIC_LITERAL = re.compile(
    r"(?ix)^\s*(?:(?:about|approximately|approx\.?|ca\.?)\s+)?"
    r"(?:<=|>=|<|>|≤|≥)?\s*[-+~≈]?\d+(?:\.\d+)?"
    r"(?:\s*(?:±|\+/-)\s*[-+~≈]?\d+(?:\.\d+)?)?"
    r"(?:\s*(?:[-–—]|to)\s*[-+~≈]?\d+(?:\.\d+)?)?"
    r"(?:\s*(?:%|percent(?:age)?|pct\.?|at\.?\s*%?|wt\.?\s*%?|"
    r"vol\.?\s*%?|mol\.?\s*%?|ppm|ppb))?\s*$"
)

_FORMULA_SUBSCRIPT_TRANSLATION = str.maketrans(
    {
        "₀": "0",
        "₁": "1",
        "₂": "2",
        "₃": "3",
        "₄": "4",
        "₅": "5",
        "₆": "6",
        "₇": "7",
        "₈": "8",
        "₉": "9",
    }
)
_FORMULA_ELEMENT_TOKEN = re.compile(
    r"(?P<element>[A-Z][a-z]?)(?P<count>\d*(?:\.\d+)?)"
)


def _normalize_formula_surface(value: Any) -> str:
    """Normalize LaTeX/Unicode formula presentation for literal comparison."""

    text = unicodedata.normalize("NFKC", str(value or "")).translate(
        _FORMULA_SUBSCRIPT_TRANSLATION
    )
    # OCR commonly leaves a subscript as ``_{92}``, ``^2`` or ``$_{92}$``.
    # Removing only presentation wrappers keeps element capitalization intact.
    text = re.sub(r"\\(?:mathrm|mathit|mathbf|text)\s*", "", text)
    text = re.sub(r"[_^]\s*\{\s*", "", text)
    text = re.sub(r"[{}$]", "", text)
    return re.sub(r"\s+", "", text)


def _formula_signature(value: Any) -> tuple[tuple[str, str], ...] | None:
    """Parse one compact chemical formula, returning ordered element/count pairs.

    This is deliberately stricter than a generic chemical-name detector.  It
    accepts only a complete formula surface (not a sentence), requires at least
    two element tokens and at least one explicit numeric subscript, and therefore
    cannot classify prose such as ``present`` or ``unknown`` as a formula.
    """

    normalized = _normalize_formula_surface(value)
    if not normalized:
        return None
    # Parentheses and separators are formula syntax, not element text.  Their
    # removal is safe only after the complete-string check below.
    surface = re.sub(r"[()\[\],;+\-/]", "", normalized)
    tokens: list[tuple[str, str]] = []
    cursor = 0
    for match in _FORMULA_ELEMENT_TOKEN.finditer(surface):
        if match.start() != cursor:
            return None
        element = match.group("element")
        if element not in _ELEMENT_SYMBOLS:
            return None
        count = match.group("count") or "1"
        tokens.append((element, count))
        cursor = match.end()
    if cursor != len(surface) or len(tokens) < 2:
        return None
    if not any(count != "1" for _, count in tokens):
        return None
    return tuple(tokens)


def _formula_surface_contains(
    evidence: Sequence[str], components: Sequence[dict[str, Any]]
) -> bool:
    """Return whether evidence contains the ordered formula represented by rows."""

    rows = [
        _normalize_formula_surface(row)
        for row in evidence
        if str(row or "").strip()
    ]
    if not rows or len(components) < 2:
        return False
    expected_parts: list[str] = []
    for component in components:
        name = str(
            component.get("name_raw") or component.get("canonical_name") or ""
        ).strip()
        value = str(
            component.get("value_raw")
            if component.get("value_raw") not in (None, "")
            else component.get("amount_raw", component.get("amount_value", ""))
        ).strip()
        numbers = _numbers(value)
        if not name or len(numbers) != 1:
            return False
        expected_parts.append(f"{name}{numbers[0]}")
    expected = _normalize_formula_surface("".join(expected_parts))
    return bool(expected) and any(expected in row for row in rows)


def _is_formula_subscript_projection(
    fact: CompositionFact,
    component: dict[str, Any],
) -> bool:
    """Detect scalar components copied from a nominal alloy formula.

    A formula such as ``Al92Ti2Fe2Co2Ni2`` is a designation, not five measured
    Composition scalars.  We reject only a component whose literal number equals
    the corresponding formula subscript and whose evidence contains the complete
    ordered formula.  Explicit measured rows (for example ``78.06% Al``) do not
    satisfy this test and remain eligible.
    """

    kind = _fold(component.get("value_kind"))
    if kind in {"formula", "balance"}:
        return False
    value = component.get("value_raw")
    if value in (None, ""):
        value = component.get("amount_raw", component.get("amount_value"))
    numbers = _numbers(value)
    if len(numbers) != 1:
        return False
    name = str(
        component.get("name_raw") or component.get("canonical_name") or ""
    ).strip()
    if not name:
        return False
    raw_expression = fact.data.get("raw_expression")
    signature = _formula_signature(raw_expression)
    all_components = [
        row
        for row in (fact.data.get("components") or [])
        if isinstance(row, dict)
    ]
    if signature is None:
        # A complete formula may be present only in the copied evidence while
        # ``raw_expression`` is a sentence.  Reconstructing the expected surface
        # from all scalar rows is still source-only and never invents a value.
        if not _formula_surface_contains(_fact_evidence(fact), all_components):
            return False
        expected_number = numbers[0]
        return any(
            symbol.casefold() == name.casefold() and count == expected_number
            for row in all_components
            for symbol, count in (_formula_signature(
                _normalize_formula_surface(
                    f"{row.get('name_raw') or row.get('canonical_name') or ''}"
                    f"{row.get('value_raw') or row.get('amount_raw') or ''}"
                )
            ) or ())
        )
    value_number = numbers[0]
    return any(
        symbol.casefold() == name.casefold() and _number_key(count) == value_number
        for symbol, count in signature
    ) and _formula_surface_contains(_fact_evidence(fact), all_components)

# A Composition component is normally an element or an explicit chemical
# formula.  High-recall extraction also emits derived descriptors (``Al
# equivalent``, ``molybdenum equivalent``, ``density change``) into the
# component list.  Those descriptors are not atom-level composition fields;
# when they also lack a composition unit there is no safe way to reinterpret
# them without inventing an ontology.  Keep this allow-list source-only and
# conservative: formula-like names and explicitly quantified constituents
# remain eligible.
_ELEMENT_SYMBOLS = {
    "H", "He", "Li", "Be", "B", "C", "N", "O", "F", "Ne",
    "Na", "Mg", "Al", "Si", "P", "S", "Cl", "Ar", "K", "Ca",
    "Sc", "Ti", "V", "Cr", "Mn", "Fe", "Co", "Ni", "Cu", "Zn",
    "Ga", "Ge", "As", "Se", "Br", "Kr", "Rb", "Sr", "Y", "Zr",
    "Nb", "Mo", "Tc", "Ru", "Rh", "Pd", "Ag", "Cd", "In", "Sn",
    "Sb", "Te", "I", "Xe", "Cs", "Ba", "La", "Ce", "Pr", "Nd",
    "Pm", "Sm", "Eu", "Gd", "Tb", "Dy", "Ho", "Er", "Tm", "Yb",
    "Lu", "Hf", "Ta", "W", "Re", "Os", "Ir", "Pt", "Au", "Hg",
    "Tl", "Pb", "Bi", "Po", "At", "Rn", "Fr", "Ra", "Ac", "Th",
    "Pa", "U", "Np", "Pu", "Am", "Cm", "Bk", "Cf", "Es", "Fm",
    "Md", "No", "Lr", "Rf", "Db", "Sg", "Bh", "Hs", "Mt", "Ds",
    "Rg", "Cn", "Nh", "Fl", "Mc", "Lv", "Ts", "Og",
}


def _composition_name_is_atomic_or_formula(name: Any) -> bool:
    """Return whether a component name is an element or formula-like label."""

    raw = unicodedata.normalize("NFKC", str(name or "")).strip()
    if not raw:
        return False
    if raw in _ELEMENT_SYMBOLS:
        return True
    # Strip only formula presentation punctuation/subscripts.  Require at
    # least two element tokens so ordinary words such as ``x`` or ``phase``
    # cannot pass as a chemical formula.
    tokens = re.findall(r"[A-Z][a-z]?", raw)
    if len(tokens) < 2 or not all(token in _ELEMENT_SYMBOLS for token in tokens):
        return False
    remainder = re.sub(r"[A-Z][a-z]?|[0-9.₀-₉+−\-_/{}()\[\]\s]", "", raw)
    return not remainder
_PROPERTY_ALIASES = {
    "engineering ultimate tensile strength": "ultimate tensile strength",
    "tensile strength": "ultimate tensile strength",
    "ultimate strength": "ultimate tensile strength",
    "ultimate tensile strength": "ultimate tensile strength",
    "uts": "ultimate tensile strength",
    "engineering yield strength": "yield strength",
    "yield stress": "yield strength",
    "yield strength": "yield strength",
    "ys": "yield strength",
    "te": "elongation",
    "eab": "elongation",
    "elongation at break": "elongation",
    "elongation at failure": "elongation",
    "elongation at fracture": "elongation",
    "fracture elongation": "elongation",
    "tensile elongation": "elongation",
    "total elongation": "elongation",
    "uniform elongation": "elongation",
    "young s modulus": "elastic modulus",
    "youngs modulus": "elastic modulus",
    "modulus of elasticity": "elastic modulus",
    "microhardness": "vickers hardness",
    "vickers microhardness": "vickers hardness",
}
_CORE_TENSILE_NAME = re.compile(
    r"(?ix)(?:"
    r"\b(?:uts|ys|el|te|eab)\b"
    r"|ultimate\s+tensile\s+strength"
    r"|tensile\s+strength"
    r"|yield\s+(?:strength|stress)"
    r"|(?:total|uniform|fracture|tensile)?\s*elongation(?:\s+at\s+(?:break|failure|fracture))?"
    r"|ductility"
    r"|strength\s+ductility\s+synergy"
    r")"
)
_TEXTUAL_RELATIVE_RATIO = re.compile(
    r"(?ix)\b(?:"
    r"twice|double|doubled|triple|tripled"
    r"|(?:one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|"
    r"hundred|thousand|million|billion|\d+(?:\.\d+)?)\s*(?:times?|fold)"
    r"|orders?\s+of\s+magnitude"
    r")\b"
)
_PERCENT_QUANTITY = re.compile(r"(?i)(?:%|\bpercent(?:age)?\b|\bpct\.?\b)")
_RELATIVE_CHANGE_CUE = re.compile(
    r"(?ix)(?:"
    r"\\(?:up|down)arrow"
    r"|[↑↓↗↘]"
    r"|\b(?:increase|decrease|change|increment|decrement|improvement|"
    r"enhancement|reduction|drop|gain|loss)"
    r"(?:d|s|ed|ing)?\b"
    r")"
)
_REFERENCE_BASELINE_CUE = re.compile(
    r"(?ix)\b(?:"
    r"room[\s-]*temperature|ambient[\s-]*temperature|room\s*temp(?:erature)?|rt"
    r"|baseline|counterpart|reference\s+(?:value|condition|sample|material)"
    r"|initial\s+value|original\s+value"
    r")\b"
)
_PERCENT_OF_REFERENCE = re.compile(
    r"(?is)(?:%|\bpercent(?:age)?\b).{0,80}?\bof\b.{0,100}?"
    r"(?:room[\s-]*temperature|ambient[\s-]*temperature|room\s*temp(?:erature)?|rt\b"
    r"|baseline|counterpart|reference\s+(?:value|condition|sample|material)"
    r"|initial\s+value|original\s+value)"
)
_RELATIVE_PROPERTY_NAME = re.compile(
    r"(?i)\b(?:retention|relative|ratio|delta|difference|change|increase|decrease|"
    r"increment|decrement|improvement|enhancement|contribution|reduction|drop|gain|loss|"
    r"percentage\s+(?:change|difference)|percent\s+(?:change|difference))\b"
)
_TENSILE_COMPARISON_ONLY = re.compile(
    r"(?ix)\b(?:"
    r"higher|lower|similar|comparable|between|unchanged|"
    r"does\s+not\s+(?:vary|change|surpass|exceed)|"
    r"did\s+not\s+(?:vary|change|surpass|exceed)|"
    r"not\s+(?:vary|change|surpass|exceed)"
    r")\b"
)
_TENSILE_PHYSICAL_UNIT = re.compile(
    r"(?ix)(?:%|\bpercent(?:age)?\b|\bpct\.?\b|\b(?:m|g|k)?pa\b|"
    r"\bksi\b|\bgigapascal(?:s)?\b|\bmegapascal(?:s)?\b|\bpascal(?:s)?\b)"
)
_NUMBER_WITH_TENSILE_UNIT = re.compile(
    r"(?ix)(?<![A-Za-z0-9])[-+]?\d+(?:\.\d+)?(?:[eE][-+]?\d+)?"
    r"\s*(?:%|percent(?:age)?|pct\.?|(?:m|g|k)?pa|ksi|"
    r"gigapascal(?:s)?|megapascal(?:s)?|pascal(?:s)?)"
)
_QUANTIFIED_RELATIVE_CUE = re.compile(
    r"(?ix)(?:"
    r"\b(?:higher|lower|exceed(?:s|ed|ing)?|surpass(?:es|ed|ing)?)\b"
    r"|\b(?:increase|decrease|change|difference|increment|decrement|"
    r"improvement|enhancement|reduce|reduction|drop|gain|loss)"
    r"(?:d|s|ed|ing)?\b"
    r"|\\(?:up|down)arrow|[↑↓↗↘]"
    r")"
)
_EVIDENCE_RELATION_BY = re.compile(
    r"(?ix)(?:"
    r"\b(?:increase|decrease|change|reduce|reduction|drop|gain|loss)"
    r"(?:d|s|ed|ing)?\b"
    r"|\b(?:exceed(?:s|ed|ing)?|surpass(?:es|ed|ing)?|higher|lower)\b"
    r").{0,120}\bby\s*$"
)
_EVIDENCE_RELATION_OF = re.compile(
    r"(?ix)\b(?:increase|decrease|change|difference|increment|decrement|"
    r"improvement|enhancement|reduction|drop|gain|loss)\b"
    r".{0,80}\bof\s+(?:(?:approximately|approx\.?|about|ca\.?)\s*)?$"
)
_EVIDENCE_DIFFERENCE_WITHIN = re.compile(
    r"(?ix)\b(?:difference|discrepancy)\b.{0,120}\bwithin\s*$"
)
_EVIDENCE_POST_VALUE_DIFFERENCE = re.compile(
    r"(?ix)^\s*(?:higher|lower|more|less|above|below)\s+than\b"
)
_EVIDENCE_POST_VALUE_CHANGE = re.compile(
    r"(?ix)^\s*(?:increase|decrease|reduction|difference|discrepancy|"
    r"drop|gain|loss)\b"
)
_EVIDENCE_PARALLEL_CHANGE = re.compile(
    r"(?ix)\b(?:increase|decrease|change|reduction|gain|loss)"
    r"(?:d|s|ed|ing)?\b.{0,180}\bby\b"
)
_TENSILE_UNIT_EVIDENCE_PATTERNS = {
    "%": r"\s*(?:%|percent(?:age)?\b|pct\.?\b)",
    "pa": r"\s*(?:pa|pascal(?:s)?)\b",
    "kpa": r"\s*(?:kpa|kilopascal(?:s)?)\b",
    "mpa": r"\s*(?:mpa|megapascal(?:s)?)\b",
    "gpa": r"\s*(?:gpa|gigapascal(?:s)?)\b",
    "ksi": r"\s*ksi\b",
}
_INLINE_TENSILE_UNIT = re.compile(
    r"(?ix)\s*(?:\\pm\s*[-+]?\d+(?:\.\d+)?\s*)?"
    r"(?P<unit>%|percent(?:age)?|pct\.?|kpa|mpa|gpa|pa|ksi|"
    r"kilopascal(?:s)?|megapascal(?:s)?|gigapascal(?:s)?|pascal(?:s)?)\b"
)
_SOURCE_LOCATOR_VALUE = re.compile(
    r"(?ix)^\s*(?:supplementary\s+)?(?:table|fig(?:ure)?)\s*"
    r"[A-Za-z0-9._-]*\s*$"
)
_SOURCE_LOCATOR_PLACEHOLDER_VALUE = re.compile(
    r"(?ix)^\s*(?:"
    r"(?:digitiz(?:e|ed)|extract(?:ed)?|read|replot(?:ted)?)\s+from\s+"
    r"|(?:shown|plotted|replotted)\s+in\s+"
    r")"
    r"(?:supplementary\s+)?(?:table|fig(?:ure)?)\s*[A-Za-z0-9._()\-]*\s*$"
)
_DIRECTIONAL_TREND = re.compile(
    r"(?ix)\b(?:"
    r"increas(?:e|ed|es|ing)|decreas(?:e|ed|es|ing)|"
    r"ris(?:e|es|ing|en)|rose|fall(?:s|ing|en)?|fell|"
    r"reduc(?:e|ed|es|ing|tion)|drop(?:s|ped|ping)?|"
    r"declin(?:e|ed|es|ing)|var(?:y|ied|ies|ying)|chang(?:e|ed|es|ing)"
    r")\b"
)
_TREND_DEPENDENCY_CONNECTOR = re.compile(r"(?i)\b(?:as|with|when)\b")
_EXPLICIT_RESPONSE_MAGNITUDE = re.compile(
    r"(?ix)\b(?:by|to)\s*"
    r"(?:(?:about|approximately|approx\.?|ca\.?)\s*)?"
    r"(?:<=|>=|<|>|≤|≥)?\s*[-+~≈]?\d+(?:\.\d+)?"
)
_METHOD_ONLY_VALUE = re.compile(
    r"(?ix)(?:"
    r"^\s*(?:measur(?:e|ed|ement)|determin(?:e|ed|ation)|evaluat(?:e|ed|ion)|"
    r"calculat(?:e|ed|ion)|assess(?:ed|ment)|characteriz(?:e|ed|ation)|"
    r"test(?:ed|ing)?|report(?:ed|ing))\s+(?:by|using|via|with)\b"
    r"|\b(?:measurements?|tests?|curves?|data|properties)\s+"
    r"(?:were\s+)?(?:measured|determined|evaluated|calculated|reported)\s*$"
    r")"
)
_COMPARISON_HEADING_VALUE = re.compile(r"(?i)^\s*comparison\s+of\b")
_PROPERTY_PROTOCOL_NAME = re.compile(
    r"(?i)\b(?:tests?|testing|measurements?|prediction)\b"
)
_TEST_CONTROL_PROPERTY_NAME = re.compile(
    r"(?ix)^\s*(?:"
    r"(?:constant\s+)?strain\s+rate"
    r"|tensile\s+test\s+strain\s+rate"
    r"|(?:loading|load|displacement|crosshead|extension)\s+rate"
    r"|(?:stress\s+relaxation\s+)?(?:reload|reloading)\s+rate"
    r"|crosshead\s+speed"
    r"|(?:stress\s+ratio(?:\s*\(?R\)?)?|R\s+ratio)"
    r"|test(?:ing)?\s+(?:temperature|frequency|speed)"
    r"|test\s+frequency\s+range"
    r"|(?:tension\s+)?creep(?:\s+test)?\s+stress"
    r"|applied\s+creep\s+stress"
    r"|strain\s+offset"
    r"|extensometer\s+removal\s+strain"
    r")\s*$"
)
_CHARACTERIZATION_STRAIN_CONDITION_NAME = re.compile(
    r"(?ix)(?:"
    r"\bstrain\s+mapping\b.*\b(?:after|at)\b.*\btensile\s+strain\b"
    r"|\bcharacteri[sz]ation\b.*\bdeformed\s+microstructure\b"
    r")"
)
_CHARACTERIZATION_EVIDENCE_CUE = re.compile(
    r"(?ix)\b(?:analysis|mapping|image|micrograph|characteri[sz]ation)\b"
)
_APPLIED_STRAIN_CONDITION = re.compile(
    r"(?ix)(?:"
    r"\b(?:after|at)\s+(?:a\s+)?tensile\s+strain(?:\s+of)?\b"
    r"|\(\s*[-+~≈]?\d+(?:\.\d+)?\s*%\s*strain\s*\)"
    r"|\b[-+~≈]?\d+(?:\.\d+)?\s*%\s*strain\b"
    r")"
)
# ``creep test`` by itself is a protocol/event label, not a material outcome.
# Keep result names such as ``creep life``, ``creep rupture time`` and
# ``creep strength`` eligible; only the bare test label (optionally prefixed by
# a loading mode such as ``tension``) is routed to the audit stream.  This
# closes the common projection ``Tension creep test = 45 MPa`` while leaving
# measured creep-life/strength claims untouched.
_CREEP_TEST_PROTOCOL_PROPERTY_NAME = re.compile(
    r"(?ix)^\s*(?:tension|compressive|compression|uniaxial|constant[-\s]*)?\s*"
    r"creep\s+test(?:ing)?\s*$"
)
_DROP_SIGNATURE_KEYS = {
    "candidate_stage_id",
    "stage_index_candidate",
    "property_id_candidate",
    "observation_id",
    "characterization_id",
    "entity_id",
    "source_evidence",
    "confidence",
}


@dataclass(frozen=True)
class ClaimQualityIssue:
    code: str
    sample_id_raw: str
    fact_type: str
    path: str
    message: str
    evidence: list[str]
    expected: Any
    actual: Any
    suggested_action: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "sample_id_raw": self.sample_id_raw,
            "fact_type": self.fact_type,
            "path": self.path,
            "message": self.message,
            "evidence": self.evidence,
            "expected": self.expected,
            "actual": self.actual,
            "suggested_action": self.suggested_action,
        }


@dataclass(frozen=True)
class ClaimQualityResult:
    accepted: list[AxisFact]
    issues: list[ClaimQualityIssue]


def _fold(value: Any) -> str:
    text = unicodedata.normalize("NFKC", str(value or "")).casefold()
    text = text.replace("γ′", "gamma prime").replace("γ'", "gamma prime")
    text = text.replace("γ", "gamma").replace("α", "alpha").replace("β", "beta")
    text = text.replace("µ", "μ")
    return re.sub(r"[^a-z0-9μ°%]+", " ", text).strip()


def _placeholder(value: Any) -> bool:
    return _fold(value) in _PLACEHOLDER_VALUES


def _evidence_rows(value: Any) -> list[str]:
    rows: list[str] = []
    if isinstance(value, dict):
        for key, child in value.items():
            if key == "source_evidence":
                if isinstance(child, str):
                    child = [child]
                if isinstance(child, Sequence) and not isinstance(child, (str, bytes)):
                    rows.extend(str(row).strip() for row in child if str(row).strip())
            else:
                rows.extend(_evidence_rows(child))
    elif isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        for child in value:
            rows.extend(_evidence_rows(child))
    return list(dict.fromkeys(rows))


def _fact_evidence(fact: AxisFact) -> list[str]:
    return list(
        dict.fromkeys(
            [
                *(str(row).strip() for row in fact.source_evidence if str(row).strip()),
                *_evidence_rows(fact.data),
            ]
        )
    )


def _number_key(value: str) -> str:
    try:
        number = float(value)
    except ValueError:
        return value
    if number == 0:
        number = 0.0
    return f"{number:.12g}"


def _numbers(value: Any) -> tuple[str, ...]:
    normalized = normalize_evidence_text(str(value or ""))
    return tuple(_number_key(match.group(0)) for match in _NUMBER.finditer(normalized))


def _value_is_grounded(value: Any, evidence: Sequence[str]) -> bool:
    raw = str(value or "").strip()
    if not raw:
        return False
    joined = "\n".join(evidence)
    raw_numbers = _numbers(raw)
    if raw_numbers:
        evidence_numbers = set(_numbers(joined))
        return all(number in evidence_numbers for number in raw_numbers)
    needle = _fold(raw)
    haystack = _fold(joined)
    return bool(needle) and needle in haystack


def _source_local_evidence_spans(evidence: Sequence[str]) -> tuple[str, ...]:
    """Split chunk-sized evidence into sentence/row-local assertions."""

    spans: list[str] = []
    for raw in evidence:
        text = str(raw or "").strip()
        if not text:
            continue
        for line in text.splitlines():
            line = line.strip()
            if not line:
                continue
            spans.extend(
                part.strip()
                for part in re.split(r"(?<=[.!?])\s+|;\s+", line)
                if part.strip()
            )
    return tuple(dict.fromkeys(spans))


def _source_local_value_grounded(value: Any, evidence: Sequence[str]) -> bool:
    """Require all numeric value tokens to share one source assertion."""

    if not _numbers(value):
        return _value_is_grounded(value, evidence)
    spans = _source_local_evidence_spans(evidence)
    if any(_value_is_grounded(value, (span,)) for span in spans):
        return True
    # A compact table often stores ``value ± std`` on two adjacent rows
    # (measurement row followed by ``Std.``).  Preserve that established
    # representation for Properties while still requiring every numeric token
    # to occur in a real table row; prose can never use this fallback.
    if any("|" in span for span in spans):
        return all(
            any(_value_is_grounded(number, (span,)) for span in spans)
            for number in _numbers(value)
        )
    return False


def _independent_variable_trend(value: Any) -> bool:
    """Detect a directional response whose numbers belong to its driver.

    A string such as ``decreases as t/d decreases from 34.5 to 4.5`` contains
    numbers, but none is a fatigue-life magnitude.  The dependency connector
    separates the response from the changing independent variable.  Preserve
    an explicitly quantified response such as ``decreased by 40% as ...``.
    """

    text = normalize_evidence_text(str(value or "")).strip()
    connector = _TREND_DEPENDENCY_CONNECTOR.search(text)
    if connector is None:
        return False
    response = text[: connector.start()]
    driver = text[connector.end() :]
    return bool(
        _DIRECTIONAL_TREND.search(response)
        and _DIRECTIONAL_TREND.search(driver)
        and not _EXPLICIT_RESPONSE_MAGNITUDE.search(response)
    )


def _characterization_strain_condition(fact: PropertyFact) -> bool:
    """Detect an applied-strain label projected as a material result.

    Microscopy and strain-mapping captions often include the deformation level
    at which a specimen was observed, for example ``(3% strain)``.  The number
    is a characterization condition, not the measured response.  Require the
    role-bearing name, a strain-decorated unit, an explicit condition carrying
    the same numeric token, and a characterization cue in the cited evidence.
    This keeps measured responses such as residual elastic strain eligible.
    """

    name = str(fact.data.get("property_name_raw") or "")
    if _CHARACTERIZATION_STRAIN_CONDITION_NAME.search(name) is None:
        return False
    if _unit_key(fact.data.get("unit_raw")) not in {"%strain", "strain%"}:
        return False
    condition = str(fact.data.get("test_condition_raw") or "")
    if _APPLIED_STRAIN_CONDITION.search(condition) is None:
        return False
    value_numbers = set(_numbers(fact.data.get("value_raw")))
    if not value_numbers or not value_numbers <= set(_numbers(condition)):
        return False
    evidence = "\n".join(_fact_evidence(fact))
    return bool(
        _CHARACTERIZATION_EVIDENCE_CUE.search(evidence)
        and _APPLIED_STRAIN_CONDITION.search(evidence)
    )


def _unit_key(value: Any) -> str:
    raw = str(value or "")
    raw = re.sub(r"\^?\\?circ", "°", raw, flags=re.I)
    text = _fold(raw).replace("percent", "%")
    aliases = {
        "at %": "at%",
        "atomic %": "at%",
        "wt %": "wt%",
        "weight %": "wt%",
        "vol %": "vol%",
        "volume %": "vol%",
        "mol %": "mol%",
        "degree c": "°c",
        "degrees c": "°c",
        "deg c": "°c",
        "micron": "μm",
        "microns": "μm",
        "um": "μm",
    }
    return aliases.get(text, text.replace(" ", ""))


def _explicit_tensile_magnitude(value: Any, unit: Any) -> bool:
    """Reject digits that occur only inside grades or coded sample labels."""

    text = str(value or "").strip()
    if not text:
        return False
    if _NUMBER_WITH_TENSILE_UNIT.search(text):
        return True
    textual_unit = bool(_TENSILE_PHYSICAL_UNIT.search(text))
    if _TEXTUAL_NUMBER.search(text) and textual_unit:
        return True
    unit_key = _unit_key(unit)
    physical_unit = unit_key in {"%", "pa", "mpa", "gpa", "kpa", "ksi"}
    return bool(
        physical_unit
        and _numbers(text)
        and not _TENSILE_COMPARISON_ONLY.search(text)
    )


def _literal_property_name_tensile_unit(
    property_name: Any,
    evidence: Sequence[str],
) -> str | None:
    """Recover a physical unit only when it is literal in the property label.

    Row-oriented tables commonly encode the unit in the row header (for
    example ``% Elongation`` or ``UTS (MPa)``) and leave ``unit_raw`` empty.
    Treating the resulting numeric cell as qualitative loses a source-proven
    result. The label itself must occur in this candidate's own evidence;
    neighboring headers and domain defaults are never consulted.
    """

    raw = str(property_name or "").strip()
    normalized = normalize_evidence_text(raw)
    if not normalized:
        return None
    source = normalize_evidence_text("\n".join(str(row) for row in evidence))
    if normalized not in source:
        return None
    if re.fullmatch(
        r"(?ix)%\s*(?:(?:total|uniform|fracture|tensile)\s+)?"
        r"elongation(?:\s+(?:at|to)\s+(?:break|failure|fracture)|"
        r"\s*\(\s*(?:at|to)\s+(?:break|failure|fracture)\s*\))?",
        raw,
    ):
        return "%"
    match = re.search(
        r"(?ix)(?:\(\s*|\[\s*|/\s*|\s+)"
        r"(?P<unit>MPa|GPa|kPa|Pa|ksi|%)\s*(?:\)|\])?\s*$",
        raw,
    )
    if match is None:
        return None
    return _display_tensile_unit(_unit_key(match.group("unit")))


def _quantified_tensile_relative(value: Any, property_name: Any) -> bool:
    text = str(value or "").strip()
    context = f"{property_name or ''}\n{text}"
    return bool(
        _QUANTIFIED_RELATIVE_CUE.search(context)
        and (
            _NUMBER_WITH_TENSILE_UNIT.search(text)
            or (
                _RELATIVE_PROPERTY_NAME.search(str(property_name or ""))
                and _numbers(text)
            )
        )
    )


def _core_tensile_family(value: Any) -> str:
    text = _fold(value)
    if re.search(r"\b(?:uts|ultimate tensile strength)\b", text):
        return "uts"
    if re.search(r"\b(?:ys|yield strength|yield stress)\b", text):
        return "ys"
    if re.search(
        r"\b(?:te|eab|elongation|ductility)\b",
        text,
    ):
        return "elongation"
    return ""


def _property_marker_pattern(property_name: Any) -> str:
    family = _core_tensile_family(property_name)
    if family == "uts":
        return r"(?:UTS|ultimate\s+tensile\s+strength|tensile\s+strength)"
    if family == "ys":
        return r"(?:YS|yield\s+(?:strength|stress))"
    if family == "elongation":
        return r"(?:TE|EAB|(?:total\s+|uniform\s+|fracture\s+)?elongation|ductility)"
    return ""


def _explicit_tensile_unit_key(value: Any, unit: Any) -> str:
    """Prefer a physical unit written inside the raw value for local binding."""

    text = normalize_evidence_text(str(value or ""))
    match = re.search(
        r"(?ix)(?:%|\bpercent(?:age)?\b|\bpct\.?\b|\b(?:k|m|g)?pa\b|"
        r"\bksi\b|\bkilopascal(?:s)?\b|\bmegapascal(?:s)?\b|"
        r"\bgigapascal(?:s)?\b|\bpascal(?:s)?\b)",
        text,
    )
    if match:
        token = _fold(match.group(0))
        token = token.replace("percentage", "%")
        token = token.replace("percent", "%").replace("pct", "%")
        aliases = {
            "kilopascal": "kpa",
            "kilopascals": "kpa",
            "megapascal": "mpa",
            "megapascals": "mpa",
            "gigapascal": "gpa",
            "gigapascals": "gpa",
            "pascal": "pa",
            "pascals": "pa",
        }
        return aliases.get(token, token)
    return _unit_key(unit)


def _evidence_bound_tensile_relation(
    value: Any,
    unit: Any,
    property_name: Any,
    evidence: Sequence[str],
) -> str:
    """Classify a scalar only when its unit and relation share one evidence row."""

    value_numbers = tuple(dict.fromkeys(_numbers(value)))
    if len(value_numbers) != 1:
        return ""
    unit_key = _explicit_tensile_unit_key(value, unit)
    unit_pattern = _TENSILE_UNIT_EVIDENCE_PATTERNS.get(unit_key)
    if unit_pattern is None:
        return ""
    marker_pattern = _property_marker_pattern(property_name)
    for raw_row in evidence:
        row = normalize_evidence_text(str(raw_row or ""))
        for number_match in _NUMBER.finditer(row):
            if _number_key(number_match.group(0)) != value_numbers[0]:
                continue
            after_number = row[number_match.end() :]
            unit_match = re.match(unit_pattern, after_number, flags=re.IGNORECASE)
            if unit_match is None:
                continue
            prefix = row[max(0, number_match.start() - 260) : number_match.start()]
            suffix = after_number[unit_match.end() :]
            if _EVIDENCE_DIFFERENCE_WITHIN.search(prefix):
                return "difference"
            if _EVIDENCE_RELATION_BY.search(prefix):
                return "relative change" if unit_key == "%" else "difference"
            if _EVIDENCE_RELATION_OF.search(prefix):
                return "relative change" if unit_key == "%" else "difference"
            if _EVIDENCE_POST_VALUE_DIFFERENCE.search(suffix):
                return "difference"
            post_change = _EVIDENCE_POST_VALUE_CHANGE.search(suffix)
            if post_change:
                word = _fold(post_change.group(0))
                if "difference" in word or "discrepancy" in word:
                    return "difference"
                return "relative change" if unit_key == "%" else "difference"
            if (
                marker_pattern
                and _EVIDENCE_PARALLEL_CHANGE.search(prefix)
                and re.match(
                    rf"(?ix)^\s*in\s+terms\s+of\s+{marker_pattern}\b",
                    suffix,
                )
                and re.search(r"(?ix)\bcompared\s+(?:to|with|against)\b", suffix)
            ):
                return "relative change" if unit_key == "%" else "difference"
    return ""


def _unit_is_grounded(unit: Any, evidence: Sequence[str]) -> bool:
    if unit in (None, "") or _placeholder(unit):
        return True
    key = _unit_key(unit)
    haystack = normalize_evidence_text("\n".join(evidence))
    compact = _fold(haystack).replace(" ", "")
    if key in {"at%", "wt%", "vol%", "mol%"}:
        prefix = key[:-1]
        return bool(re.search(rf"(?<![a-z]){prefix}\s*\.?\s*%", haystack))
    if key == "°c":
        return bool(re.search(r"(?:°\s*c|degrees?\s*c|deg\.?\s*c)", haystack))
    if key == "μm":
        return bool(re.search(r"(?:μ\s*m|\bum\b|microns?)", haystack))
    if len(key) > 1:
        return key in compact
    return bool(
        re.search(rf"(?<![a-z0-9]){re.escape(key)}(?![a-z0-9])", haystack)
    )


def _source_inline_tensile_unit(
    value: Any,
    evidence: Sequence[str],
) -> str:
    """Return one unit written immediately after the candidate's value.

    This is deliberately local to the value token.  A method paragraph or a
    neighboring table column may contain several units; those must not be
    borrowed to repair a Property.  Returning a unit only when every matching
    value occurrence agrees prevents cross-field normalization.
    """

    numbers = _numbers(value)
    if not numbers:
        return ""
    found: set[str] = set()
    for raw in evidence:
        text = normalize_evidence_text(str(raw or ""))
        for match in _NUMBER.finditer(text):
            if _number_key(match.group(0)) != numbers[0]:
                continue
            unit_match = _INLINE_TENSILE_UNIT.match(text[match.end() :])
            if unit_match is None:
                continue
            token = _unit_key(unit_match.group("unit"))
            if token in {"%", "pa", "kpa", "mpa", "gpa", "ksi"}:
                found.add(token)
    if len(found) != 1:
        return ""
    return next(iter(found))


def _display_tensile_unit(value: str) -> str:
    return {
        "%": "%",
        "pa": "Pa",
        "kpa": "kPa",
        "mpa": "MPa",
        "gpa": "GPa",
        "ksi": "ksi",
    }.get(value, value)


def _issue(
    fact: AxisFact,
    *,
    code: str,
    path: str,
    message: str,
    expected: Any,
    actual: Any,
) -> ClaimQualityIssue:
    return ClaimQualityIssue(
        code=code,
        sample_id_raw=fact.sample_id_raw,
        fact_type=fact.fact_type,
        path=path,
        message=message,
        evidence=_fact_evidence(fact),
        expected=expected,
        actual=deepcopy(actual),
        suggested_action="Review the structured field against its cited source evidence.",
    )


def _component_gate(
    fact: CompositionFact,
    component: dict[str, Any],
    index: int,
) -> ClaimQualityIssue | None:
    evidence = _fact_evidence(fact)
    value = component.get("value_raw")
    if value in (None, ""):
        value = component.get("amount_raw", component.get("amount_value"))
    kind = _fold(component.get("value_kind"))
    if _placeholder(value):
        return _issue(
            fact,
            code="fact_placeholder_value",
            path=f"data.components[{index}].value_raw",
            message="A composition component placeholder is not a scientific amount.",
            expected={"value_raw": "explicit source-supported amount"},
            actual=component,
        )
    if kind == "categorical" and _STRUCTURAL_COMPOSITION_VALUE.search(str(value or "")):
        return _issue(
            fact,
            code="fact_quarantined_wrong_axis",
            path=f"data.components[{index}]",
            message="A structural presence/location phrase cannot be promoted as composition.",
            expected={"axis": "composition", "value": "composition amount or category"},
            actual=component,
        )
    # Compact table tasks can carry the value and basis in deterministic row/header
    # context while a component-level quote contains only one of them.  Until the
    # task-cache contract persists source coordinates, rejecting component numbers or
    # units here loses many valid table cells.  Measured-vs-designation provenance is
    # enforced below at the observation level; wrong-axis categorical placeholders are
    # still removed above.
    return None


def _composition_precision_component(
    fact: CompositionFact,
    component: dict[str, Any],
    index: int,
) -> tuple[dict[str, Any] | None, ClaimQualityIssue | None]:
    """Apply the production precision contract to one composition component.

    The model may emit a component-shaped record for a comparison or a phase
    description because those phrases occur next to real composition tables.
    Keep the permissive safe gate above for callers that explicitly request
    high recall, but give promotion a deterministic, source-only precision
    gate. It never changes a numeric value; it only rejects malformed
    qualitative projections and normalizes an obvious numeric kind typo.
    """

    value = component.get("value_raw")
    if value in (None, ""):
        value = component.get("amount_raw", component.get("amount_value"))
    value_text = str(value or "").strip()
    kind = _fold(component.get("value_kind"))
    name = str(component.get("name_raw") or component.get("canonical_name") or "")
    evidence = _fact_evidence(fact)
    evidence_text = "\n".join(evidence)

    def reject(
        reason: str,
        *,
        code: str = "composition_component_precision_quarantined",
    ) -> tuple[None, ClaimQualityIssue]:
        return None, _issue(
            fact,
            code=code,
            path=f"data.components[{index}]",
            message=(
                "A composition component was isolated because its value is a "
                "qualitative comparison, placeholder, or unresolved projection."
            ),
            expected={
                "value_kind": (
                    "scalar, range, inequality, uncertainty, formula, balance, "
                    "or an explicitly named composition trend"
                ),
                "source_grounded": True,
            },
            actual={"reason": reason, "component": deepcopy(component)},
        )

    if _placeholder(value_text) or kind in {"", "unknown"}:
        return reject("placeholder_or_unknown_kind")

    if _is_formula_subscript_projection(fact, component):
        return reject(
            "nominal_formula_subscript_projection",
            code="composition_formula_subscript_quarantined",
        )

    # Some legacy composition observations encode a constituent role such as
    # ``Y2O3 nanoparticles: addition`` with an uncertainty/text kind.  Preserve
    # that explicit, source-grounded designation before numeric-kind validation.
    if (
        _COMPOSITION_DESIGNATION_VALUE.fullmatch(value_text)
        and _value_is_grounded(value_text, evidence)
        and str(name).strip()
    ):
        return component, None

    # A categorical ``48``/``2`` commonly comes from a formula extractor that
    # forgot to tag the value as scalar. Numeric normalization is safe because
    # the literal value and its evidence remain unchanged.
    if kind == "categorical" and _COMPOSITION_NUMERIC_LITERAL.fullmatch(
        value_text
    ):
        if _COMPOSITION_EXPLICIT_QUANTITY.fullmatch(value_text) or str(
            component.get("unit_raw") or ""
        ).strip():
            normalized = deepcopy(component)
            normalized["value_kind"] = "scalar"
            return normalized, None

    if kind == "balance":
        if _COMPOSITION_BALANCE_VALUE.fullmatch(value_text):
            return component, None
        return reject("balance_kind_without_balance_literal")

    if kind == "categorical":
        if _COMPOSITION_BALANCE_VALUE.fullmatch(value_text):
            normalized = deepcopy(component)
            normalized["value_kind"] = "balance"
            return normalized, None
        if "formula" in _fold(name) and value_text:
            return component, None
        if _COMPOSITION_FORMULA_VALUE.fullmatch(value_text):
            return component, None
        # A qualitative trend (``higher``, ``declines``, ``minimal alteration``)
        # can be source-supported and still fail the Composition contract: it
        # has no amount, range, formula, or explicit balance value.  Keep the
        # prose in the audit stream rather than treating a field name such as
        # ``concentration`` or ``content`` as permission to manufacture a
        # scalar composition claim.
        # A source may identify an explicit constituent by its role (for
        # example ``Y2O3 nanoparticles: addition``) rather than by a numeric
        # amount.  Keep this narrow, source-grounded designation category; it
        # is distinct from an unqualified comparison such as ``present``.
        return reject("qualitative_or_comparative_component")

    if kind == "text":
        if (
            _COMPOSITION_EXPLICIT_QUANTITY.search(value_text)
            and not _COMPOSITION_COMPARATIVE_VALUE.search(value_text)
        ):
            return component, None
        return reject("untyped_text_without_explicit_quantity")

    if kind in {"scalar", "range", "inequality", "uncertainty", "formula"}:
        if (
            kind != "formula"
            and _COMPOSITION_COMPARATIVE_VALUE.search(value_text)
            and not _COMPOSITION_NUMERIC_LITERAL.fullmatch(value_text)
        ):
            return reject("qualitative_or_comparative_component")
        # A scalar/range must be the literal amount itself.  Accepting any
        # source-grounded number lets a full sentence such as ``CrB2 with
        # diameters of ~10 um`` become the component value.  That is a
        # descriptive projection, not a composition amount.
        if kind == "formula":
            formula_like = bool(
                _COMPOSITION_FORMULA_VALUE.fullmatch(value_text)
                or _composition_name_is_atomic_or_formula(name)
                or _unit_key(component.get("unit_raw")) == "formula_ratio"
            )
            if not formula_like:
                return reject("formula_value_not_literal_formula")
            if value_text and not _numbers(value_text):
                return component, None
        elif not _COMPOSITION_NUMERIC_LITERAL.fullmatch(value_text):
            return reject("numeric_value_not_literal_amount")
        if not _numbers(value_text):
            return reject("numeric_kind_without_numeric_literal")
        # A value copied from a different chunk must still occur literally in
        # the component's own evidence; this blocks cross-chunk number reuse.
        if not _value_is_grounded(value_text, evidence):
            return reject("numeric_literal_not_in_component_evidence")
        # Derived descriptors such as ``molybdenum equivalent`` are not atom
        # amounts.  If the extractor gives them no composition basis/unit,
        # isolate them instead of silently presenting the descriptor as an
        # element-level Composition claim.  Explicitly quantified constituents
        # (e.g. nanoparticles in vol.%) and formula-like names remain allowed.
        unit_key = _unit_key(component.get("unit_raw"))
        if (
            not _composition_name_is_atomic_or_formula(name)
            and unit_key in {"", "unknown", "notreported", "n a"}
            and _unit_key(component.get("unit_raw")) != "formula_ratio"
        ):
            return reject("non_atomic_descriptor_without_composition_unit")
        return component, None

    return reject("unsupported_value_kind")


def filter_composition_precision_facts(
    facts: Iterable[AxisFact],
) -> ClaimQualityResult:
    """Filter only the obvious high-risk composition projections.

    This is intentionally separate from ``filter_axis_facts(..., mode="safe")``
    so existing safe-mode callers retain their recall-oriented contract. The
    Alpha25 promotion stage invokes this additional gate before materialization.
    """

    accepted: list[AxisFact] = []
    issues: list[ClaimQualityIssue] = []
    for fact in facts:
        if not isinstance(fact, CompositionFact) or fact.fact_type == "material_identity":
            accepted.append(fact)
            continue
        data = deepcopy(fact.data)
        components: list[dict[str, Any]] = []
        for index, component in enumerate(data.get("components") or []):
            if not isinstance(component, dict):
                continue
            cleaned, issue = _composition_precision_component(fact, component, index)
            if issue is not None:
                issues.append(issue)
            if cleaned is not None:
                components.append(cleaned)
        data["components"] = components
        if components:
            accepted.append(fact.model_copy(update={"data": data}))
    return ClaimQualityResult(accepted=accepted, issues=issues)


def _gate_composition(fact: CompositionFact) -> tuple[AxisFact | None, list[ClaimQualityIssue]]:
    if fact.fact_type == "material_identity":
        return fact, []
    data = deepcopy(fact.data)
    components: list[dict[str, Any]] = []
    issues: list[ClaimQualityIssue] = []
    for index, component in enumerate(data.get("components") or []):
        if not isinstance(component, dict):
            continue
        issue = _component_gate(fact, component, index)
        if issue is not None:
            issues.append(issue)
        else:
            components.append(component)
    data["components"] = components
    if not components:
        return None, issues
    composition_measurement = _unit_key(data.get("basis")) in {
        "at%",
        "wt%",
        "vol%",
        "mol%",
        "atomicfraction",
        "massfraction",
        "volumefraction",
    }
    if _fold(data.get("source_type")) == "measured" and composition_measurement:
        evidence = "\n".join(_fact_evidence(fact))
        if not _MEASURED_COMPOSITION_CONTEXT.search(evidence):
            issues.append(
                _issue(
                    fact,
                    code="composition_source_type_unsupported",
                    path="data.source_type",
                    message=(
                        "The cited evidence does not establish that the composition "
                        "is a measured sample result."
                    ),
                    expected={"source_type": "measured", "measurement_context": True},
                    actual=data,
                )
            )
            return None, issues
    return fact.model_copy(update={"data": data}), issues


def _gate_processing(fact: ProcessingFact) -> tuple[AxisFact | None, list[ClaimQualityIssue]]:
    if fact.fact_type != "process_stage":
        return fact, []
    data = deepcopy(fact.data)
    accepted: list[dict[str, Any]] = []
    issues: list[ClaimQualityIssue] = []
    for index, parameter in enumerate(data.get("parameters_raw") or []):
        if not isinstance(parameter, dict):
            continue
        evidence = list(
            dict.fromkeys([*_evidence_rows(parameter), *_fact_evidence(fact)])
        )
        value = parameter.get("value_raw")
        if _placeholder(value):
            issues.append(
                _issue(
                    fact,
                    code="fact_placeholder_value",
                    path=f"data.parameters_raw[{index}].value_raw",
                    message="A process parameter placeholder is not a reported value.",
                    expected={"value_raw": "explicit source-supported value"},
                    actual=parameter,
                )
            )
            continue
        if not _value_is_grounded(value, evidence):
            issues.append(
                _issue(
                    fact,
                    code="fact_value_not_grounded",
                    path=f"data.parameters_raw[{index}].value_raw",
                    message="The process parameter value is absent from its cited evidence.",
                    expected={"value_raw": value, "in_source_evidence": True},
                    actual=parameter,
                )
            )
            continue
        accepted.append(parameter)
    data["parameters_raw"] = accepted
    return fact.model_copy(update={"data": data}), issues


def _gate_property(fact: PropertyFact) -> tuple[AxisFact | None, list[ClaimQualityIssue]]:
    evidence = _fact_evidence(fact)
    value = fact.data.get("value_raw")
    folded = _fold(value)
    if _placeholder(value) or folded in _NON_VALUE_ACTIONS:
        return None, [
            _issue(
                fact,
                code="fact_placeholder_value",
                path="data.value_raw",
                message="A method/action/placeholder cannot be promoted as a property value.",
                expected={"value_raw": "explicit material response"},
                actual=fact.data,
            )
        ]
    property_name = str(fact.data.get("property_name_raw") or "").strip()
    non_result_reason = ""
    if (
        re.search(r"(?i)\b(?:creep|rupture)\s+(?:test\s+)?life\b", property_name)
        and _CREEP_LIFE_EVENT_VALUE.search(str(value or ""))
    ):
        non_result_reason = "creep_test_event_not_measured_life"
    elif _SOURCE_LOCATOR_VALUE.fullmatch(str(value or "")):
        non_result_reason = "source_locator"
    elif _SOURCE_LOCATOR_PLACEHOLDER_VALUE.fullmatch(str(value or "")):
        non_result_reason = "source_locator_placeholder"
    elif _independent_variable_trend(value):
        non_result_reason = "independent_variable_trend"
    elif _METHOD_ONLY_VALUE.search(str(value or "")):
        non_result_reason = "measurement_method"
    elif _COMPARISON_HEADING_VALUE.search(str(value or "")):
        non_result_reason = "comparison_heading"
    elif _characterization_strain_condition(fact):
        non_result_reason = "characterization_strain_condition"
    elif _TEST_CONTROL_PROPERTY_NAME.fullmatch(property_name):
        non_result_reason = "test_control_parameter"
    elif _CREEP_TEST_PROTOCOL_PROPERTY_NAME.fullmatch(property_name):
        non_result_reason = "creep_test_protocol"
    elif not _numbers(value) and _PROPERTY_PROTOCOL_NAME.search(property_name):
        non_result_reason = "protocol_record"
    if non_result_reason:
        return None, [
            ClaimQualityIssue(
                code="property_non_result_quarantined",
                sample_id_raw=fact.sample_id_raw,
                fact_type=fact.fact_type,
                path="data.value_raw",
                message=(
                    "A source locator, method, protocol, or comparison heading is "
                    "not an observed material-property result."
                ),
                evidence=evidence,
                expected={"value_raw": "explicit material response"},
                actual={"reason": non_result_reason, "fact": fact.model_dump()},
                suggested_action=(
                    "Review the preserved evidence and restore only an explicit "
                    "property outcome, not its test protocol or source locator."
                ),
            )
        ]

    is_core_tensile = bool(_CORE_TENSILE_NAME.search(_fold(property_name)))
    embedded_name_unit = (
        _literal_property_name_tensile_unit(property_name, evidence)
        if is_core_tensile and _placeholder(fact.data.get("unit_raw"))
        else None
    )
    textual_relative_ratio = bool(_TEXTUAL_RELATIVE_RATIO.search(str(value or "")))
    evidence_relation = _evidence_bound_tensile_relation(
        value,
        fact.data.get("unit_raw"),
        property_name,
        evidence,
    )
    quantified_relative = bool(
        _quantified_tensile_relative(value, property_name) or evidence_relation
    )
    chart_series_summary = bool(
        _fold(fact.data.get("data_source")) in {"chart", "figure", "image"}
        and any(str(row).strip().casefold().startswith("series:") for row in evidence)
    )
    absolute_tensile_numbers = _numbers(value)
    compressive_context = "compress" in _fold(
        f"{property_name} {fact.data.get('test_method_raw') or ''}"
    )
    if (
        is_core_tensile
        and absolute_tensile_numbers
        and min(float(number) for number in absolute_tensile_numbers) < 0
        and not _RELATIVE_PROPERTY_NAME.search(property_name)
        and not quantified_relative
        and not chart_series_summary
        and not compressive_context
    ):
        return None, [
            ClaimQualityIssue(
                code="physically_invalid_tensile_value",
                sample_id_raw=fact.sample_id_raw,
                fact_type=fact.fact_type,
                path="data.value_raw",
                message=(
                    "A negative absolute tensile strength or elongation cannot be "
                    "promoted as a physical magnitude."
                ),
                evidence=evidence,
                expected={
                    "absolute_tensile_magnitude": ">= 0",
                    "automatic_sign_repair": False,
                },
                actual={"fact": deepcopy(fact.data)},
                suggested_action=(
                    "Review the original PDF for an OCR-damaged approximation mark; "
                    "restore only after confirming the printed value."
                ),
            )
        ]
    if is_core_tensile and not _explicit_tensile_magnitude(
        value, fact.data.get("unit_raw") or embedded_name_unit
    ) and not quantified_relative and not chart_series_summary:
        if textual_relative_ratio:
            before = deepcopy(fact.data)
            data = deepcopy(fact.data)
            if not _RELATIVE_PROPERTY_NAME.search(property_name):
                data["property_name_raw"] = (
                    f"{property_name} relative ratio".strip()
                )
            data["unit_raw"] = None
            cleaned = fact.model_copy(update={"data": data})
            return cleaned, [
                ClaimQualityIssue(
                    code="property_relative_quantity_reclassified",
                    sample_id_raw=fact.sample_id_raw,
                    fact_type=fact.fact_type,
                    path="data.property_name_raw",
                    message=(
                        "A source-explicit textual ratio was separated from the "
                        "corresponding absolute tensile property."
                    ),
                    evidence=evidence,
                    expected={
                        "quantity_semantics": "relative ratio",
                        "unit_raw": None,
                    },
                    actual={
                        "before": before,
                        "after": deepcopy(data),
                        "reason": "textual_relative_ratio",
                    },
                    suggested_action=(
                        "Review only if the source reports an independent absolute "
                        "tensile magnitude for this statement."
                    ),
                )
            ]
        return None, [
            ClaimQualityIssue(
                code="qualitative_tensile_quarantined",
                sample_id_raw=fact.sample_id_raw,
                fact_type=fact.fact_type,
                path="data.value_raw",
                message=(
                    "A qualitative or comparison-only tensile description cannot "
                    "be promoted as an absolute scalar Property."
                ),
                evidence=evidence,
                expected={
                    "value_raw": (
                        "an explicit magnitude, range, inequality, uncertainty, "
                        "or quantified relative relation"
                    ),
                    "formal_property": False,
                },
                actual={
                    "reason": "qualitative_without_magnitude",
                    "fact": fact.model_dump(),
                },
                suggested_action=(
                    "Retain this source-supported comparison in the issue audit; "
                    "restore it to Properties only with an explicit magnitude."
                ),
            )
        ]
    value_numbers = _numbers(value)
    evidence_numbers = _numbers("\n".join(evidence))
    if is_core_tensile and value_numbers and not _source_local_value_grounded(
        value, evidence
    ):
        return None, [
            _issue(
                fact,
                code="core_tensile_value_not_in_local_evidence",
                path="data.value_raw",
                message=(
                    "A numeric core-tensile value was isolated because its own "
                    "candidate evidence does not contain every value token."
                ),
                expected={
                    "value_raw": value,
                    "all_numeric_tokens_in_local_source_evidence": True,
                    "cross_candidate_or_cross_chunk_grounding": False,
                },
                actual={
                    "reason": (
                        "local_evidence_contains_no_numbers"
                        if not evidence_numbers
                        else "local_evidence_has_conflicting_numbers"
                    ),
                    "fact": fact.model_dump(),
                },
            )
        ]
    if value_numbers and evidence_numbers and not _source_local_value_grounded(
        value, evidence
    ):
        return None, [
            _issue(
                fact,
                code="fact_value_not_grounded",
                path="data.value_raw",
                message="The property value is absent from its cited evidence.",
                expected={"value_raw": value, "in_source_evidence": True},
                actual=fact.data,
            )
        ]

    data = deepcopy(fact.data)
    property_name = str(data.get("property_name_raw") or "").strip()
    value_text = str(value or "").strip()
    unit_key = _unit_key(data.get("unit_raw"))
    unit_reconciliation_issue: ClaimQualityIssue | None = None
    if embedded_name_unit is not None and _placeholder(data.get("unit_raw")):
        before = deepcopy(data)
        data["unit_raw"] = embedded_name_unit
        unit_key = _unit_key(embedded_name_unit)
        unit_reconciliation_issue = ClaimQualityIssue(
            code="property_name_unit_recovered",
            sample_id_raw=fact.sample_id_raw,
            fact_type=fact.fact_type,
            path="data.unit_raw",
            message=(
                "A missing tensile unit was recovered from the literal property "
                "label in this candidate's own source evidence."
            ),
            evidence=evidence,
            expected={
                "property_label_in_local_evidence": True,
                "physical_unit": embedded_name_unit,
                "neighbor_unit_borrowed": False,
            },
            actual={
                "before": before,
                "after": deepcopy(data),
                "reason": "source_local_property_label_unit",
            },
            suggested_action=(
                "Review the literal table header only if OCR merged labels from "
                "different cells."
            ),
        )
    # A structured unit may be corrupted while the model still preserves the
    # literal source token in ``value_raw`` (for example ``0.33 GPa`` paired
    # with ``unit_raw=MPa``).  Reconcile only this source-local, unambiguous
    # mismatch.  Never infer a unit from a neighboring sentence/chunk, and do
    # not repair non-tensile or ambiguous/multi-unit candidates.
    if is_core_tensile and not _placeholder(data.get("unit_raw")):
        inline_unit = _source_inline_tensile_unit(value, evidence)
        if inline_unit and unit_key in {"%", "pa", "kpa", "mpa", "gpa", "ksi"}:
            if inline_unit != unit_key:
                before = deepcopy(data)
                data["unit_raw"] = _display_tensile_unit(inline_unit)
                unit_reconciliation_issue = ClaimQualityIssue(
                    code="property_source_unit_reconciled",
                    sample_id_raw=fact.sample_id_raw,
                    fact_type=fact.fact_type,
                    path="data.unit_raw",
                    message=(
                        "The structured tensile unit was reconciled to the unique "
                        "physical unit written immediately after the candidate "
                        "value in its own source evidence."
                    ),
                    evidence=evidence,
                    expected={
                        "unit_raw": _display_tensile_unit(inline_unit),
                        "source_local_unit": inline_unit,
                        "unique_matching_unit": True,
                    },
                    actual={
                        "before": before,
                        "after": deepcopy(data),
                        "declared_unit": unit_key,
                        "inline_unit": inline_unit,
                        "reason": "source_local_inline_unit_mismatch",
                    },
                    suggested_action=(
                        "Review the cited value token only if OCR merged the unit "
                        "from a different field or the source prints multiple "
                        "units for the same numeric value."
                    ),
                )
                unit_key = inline_unit
    evidence_text = "\n".join(evidence)
    has_percent_value = bool(_PERCENT_QUANTITY.search(value_text))
    reference_relative = bool(
        has_percent_value
        and _REFERENCE_BASELINE_CUE.search(evidence_text)
        and _PERCENT_OF_REFERENCE.search(evidence_text)
    )
    dimensional_relative_change = bool(
        has_percent_value
        and unit_key not in {"", "%"}
        and _RELATIVE_CHANGE_CUE.search(f"{property_name}\n{value_text}")
    )
    already_relative = bool(_RELATIVE_PROPERTY_NAME.search(property_name))

    classification = ""
    if evidence_relation:
        classification = evidence_relation
    elif quantified_relative:
        classification = "relative change" if has_percent_value else "difference"
    elif reference_relative:
        classification = "retention"
    elif dimensional_relative_change:
        classification = "relative change"
    if not classification:
        unit_raw = data.get("unit_raw")
        data_source = _fold(data.get("data_source"))
        if (
            not value_numbers
            and not _TEXTUAL_NUMBER.search(value_text)
            and data_source not in {"chart", "figure", "image"}
            and unit_raw not in (None, "")
            and not _placeholder(unit_raw)
        ):
            before = deepcopy(data)
            data["unit_raw"] = None
            return fact.model_copy(update={"data": data}), [
                ClaimQualityIssue(
                    code="property_categorical_unit_removed",
                    sample_id_raw=fact.sample_id_raw,
                    fact_type=fact.fact_type,
                    path="data.unit_raw",
                    message=(
                        "A purely categorical property response cannot carry a "
                        "dimensional unit copied from an absolute-value field."
                    ),
                    evidence=evidence,
                    expected={"unit_raw": None, "value_semantics": "categorical"},
                    actual={"before": before, "after": deepcopy(data)},
                    suggested_action=(
                        "Review only if the cited source reports a numeric magnitude "
                        "for this categorical response."
                    ),
                )
            ]
        if unit_reconciliation_issue is not None:
            return fact.model_copy(update={"data": data}), [unit_reconciliation_issue]
        return fact, []

    before = deepcopy(data)
    if classification == "retention" and not already_relative:
        data["property_name_raw"] = f"{property_name} retention".strip()
    elif classification == "difference" and not already_relative:
        data["property_name_raw"] = f"{property_name} difference".strip()
    elif classification == "relative change" and not already_relative:
        data["property_name_raw"] = f"{property_name} relative change".strip()
    if classification != "difference":
        data["unit_raw"] = "%"
    if data == before:
        if unit_reconciliation_issue is not None:
            return fact.model_copy(update={"data": data}), [unit_reconciliation_issue]
        return fact, []

    cleaned = fact.model_copy(update={"data": data})
    issues = [
        ClaimQualityIssue(
            code="property_relative_quantity_reclassified",
            sample_id_raw=fact.sample_id_raw,
            fact_type=fact.fact_type,
            path="data.property_name_raw",
            message=(
                "A source-explicit relative quantity was separated from the "
                "corresponding absolute physical property."
            ),
            evidence=evidence,
            expected={
                "quantity_semantics": classification,
                "unit_raw": data.get("unit_raw"),
                "absolute_property_unit": "not applicable to this relative value",
            },
            actual={
                "before": before,
                "after": deepcopy(data),
                "reason": (
                    "percent_of_reference_baseline"
                    if reference_relative
                    else "evidence_bound_difference"
                    if evidence_relation == "difference"
                    else "evidence_bound_relative_change"
                    if evidence_relation == "relative change"
                    else "quantified_comparative_difference"
                    if classification == "difference"
                    else "directional_percent_with_incompatible_unit"
                ),
            },
            suggested_action=(
                "Review the cited baseline or change direction only if the source "
                "intended an absolute measurement."
            ),
        )
    ]
    if unit_reconciliation_issue is not None:
        issues.insert(0, unit_reconciliation_issue)
    return cleaned, issues


def _gate_structure(fact: StructureFact) -> tuple[AxisFact | None, list[ClaimQualityIssue]]:
    if fact.fact_type != "structure_observation":
        return fact, []
    data = deepcopy(fact.data)
    accepted: list[dict[str, Any]] = []
    issues: list[ClaimQualityIssue] = []
    for index, entity in enumerate(data.get("entities") or []):
        if not isinstance(entity, dict):
            continue
        entity_type = _fold(entity.get("entity_type"))
        name = str(entity.get("name_raw") or "").strip()
        features = [
            feature
            for feature in entity.get("features") or []
            if isinstance(feature, dict)
        ]
        context_only = entity_type in {"area", "location", "region", "zone"} or bool(
            _STRUCTURAL_CONTEXT_ONLY_NAME.fullmatch(name)
        )
        if context_only and not features:
            issues.append(
                ClaimQualityIssue(
                    code="structure_context_entity_removed",
                    sample_id_raw=fact.sample_id_raw,
                    fact_type=fact.fact_type,
                    path=f"data.entities[{index}]",
                    message=(
                        "An empty region/location label is observation context, not "
                        "an independent structural presence claim."
                    ),
                    evidence=_fact_evidence(fact),
                    expected={
                        "entity": "structural entity or context with quantitative features"
                    },
                    actual={"removed_entity": deepcopy(entity)},
                    suggested_action=(
                        "Review the source only if the location owns an explicit "
                        "structural feature."
                    ),
                )
            )
            continue
        accepted.append(entity)
    data["entities"] = accepted
    return fact.model_copy(update={"data": data}), issues


def filter_axis_facts(
    facts: Iterable[AxisFact], *, mode: ClaimQualityMode = "safe"
) -> ClaimQualityResult:
    """Filter candidates according to the selected deterministic safety level.

    ``safe`` applies only gates that are reliable with the current task-cache
    provenance. ``strict`` additionally enables experimental composition and
    processing field gates that require complete evidence-unit context to avoid
    false rejection. ``off`` is a lossless control path.
    """

    rows = list(facts)
    if mode == "off":
        return ClaimQualityResult(accepted=rows, issues=[])
    if mode not in {"safe", "strict"}:
        raise ValueError(f"Unsupported claim quality mode: {mode!r}")

    accepted: list[AxisFact] = []
    issues: list[ClaimQualityIssue] = []
    for fact in rows:
        if mode == "strict" and isinstance(fact, CompositionFact):
            cleaned, fact_issues = _gate_composition(fact)
        elif mode == "strict" and isinstance(fact, ProcessingFact):
            cleaned, fact_issues = _gate_processing(fact)
        elif isinstance(fact, PropertyFact):
            cleaned, fact_issues = _gate_property(fact)
        elif isinstance(fact, StructureFact):
            cleaned, fact_issues = _gate_structure(fact)
        else:  # pragma: no cover - AxisFact is a closed discriminated union.
            cleaned, fact_issues = fact, []
        issues.extend(fact_issues)
        if cleaned is not None:
            accepted.append(cleaned)
    return ClaimQualityResult(accepted=accepted, issues=issues)


def _canonical_name(value: Any) -> str:
    folded = _fold(value)
    return _PROPERTY_ALIASES.get(folded, folded)


def is_core_tensile_property_name(value: Any) -> bool:
    """Return whether a raw property name belongs to the core tensile family."""

    return bool(_CORE_TENSILE_NAME.search(_fold(value)))


def core_tensile_subtype(value: Any) -> str:
    """Preserve scientifically distinct elongation subtypes across aliases."""

    name = _fold(value)
    if not is_core_tensile_property_name(name):
        return ""
    if "uniform" in name:
        return "uniform"
    if (
        "fracture" in name
        or "at break" in name
        or "at failure" in name
        or name == "eab"
    ):
        return "fracture"
    if "total" in name or name == "te":
        return "total"
    return "unspecified"


def _canonical_value(value: Any) -> Any:
    text = str(value or "").strip()
    numbers = _numbers(text)
    if numbers:
        return {"numbers": numbers, "text": _fold(text)}
    return _fold(text)


def _feature_signature(row: dict[str, Any]) -> tuple[Any, ...]:
    return (
        _canonical_name(row.get("canonical_name") or row.get("feature_name_raw")),
        _fold(row.get("value_kind")),
        json.dumps(_canonical_value(row.get("value_raw")), sort_keys=True),
        _unit_key(row.get("canonical_unit") or row.get("unit_raw")),
        _fold(row.get("data_nature")),
    )


def _semantic_payload(fact: AxisFact) -> Any:
    data = fact.data
    if isinstance(fact, PropertyFact):
        property_name = data.get("property_name_raw")
        return (
            _canonical_name(property_name),
            core_tensile_subtype(property_name),
            json.dumps(_canonical_value(data.get("value_raw")), sort_keys=True),
            _unit_key(data.get("unit_raw")),
            _canonical_name(data.get("test_method_raw")),
            _fold(data.get("test_standard_raw")),
            _fold(data.get("test_condition_raw")),
            _fold(data.get("test_specimen_raw")),
            _fold(data.get("data_source")),
        )
    if isinstance(fact, CompositionFact):
        if fact.fact_type == "material_identity":
            return (
                _canonical_name(data.get("material_family")),
                _canonical_name(data.get("material_name_raw")),
                _canonical_name(data.get("designation_raw")),
                _canonical_name(data.get("feedstock_form")),
            )
        components = sorted(
            (
                _canonical_name(component.get("canonical_name") or component.get("name_raw")),
                _fold(component.get("value_kind")),
                json.dumps(_canonical_value(component.get("value_raw")), sort_keys=True),
                _unit_key(component.get("canonical_unit") or component.get("unit_raw")),
                _fold(component.get("data_nature")),
            )
            for component in data.get("components") or []
            if isinstance(component, dict)
        )
        return (
            _fold(data.get("source_type")),
            _fold(data.get("material_state")),
            _unit_key(data.get("basis")),
            _fold(data.get("component_type")),
            components,
            _fold(data.get("measurement")),
            _fold(data.get("data_source")),
        )
    if isinstance(fact, ProcessingFact):
        if fact.fact_type == "process_stage":
            parameters = sorted(
                (
                    _canonical_name(row.get("parameter_name_raw")),
                    json.dumps(_canonical_value(row.get("value_raw")), sort_keys=True),
                    _unit_key(row.get("unit_raw")),
                    _fold(row.get("condition_label_raw")),
                )
                for row in data.get("parameters_raw") or []
                if isinstance(row, dict)
            )
            return (
                _canonical_name(data.get("process_name_raw")),
                _fold(data.get("process_role_candidate")),
                parameters,
            )
        if fact.fact_type == "process_text":
            return _fold(data.get("simplified") or data.get("original"))
    if isinstance(fact, StructureFact):
        if fact.fact_type == "characterization":
            remainder = {
                key: child
                for key, child in data.items()
                if key not in _DROP_SIGNATURE_KEYS
                and child not in (None, "", [], {})
            }
            return _clean_signature_value(remainder)
        if fact.fact_type == "structure_observation":
            entities = sorted(
                (
                    _fold(row.get("entity_type")),
                    _fold(row.get("role")),
                    _canonical_name(row.get("canonical_name") or row.get("name_raw")),
                    sorted(
                        _feature_signature(feature)
                        for feature in row.get("features") or []
                        if isinstance(feature, dict)
                    ),
                )
                for row in data.get("entities") or []
                if isinstance(row, dict)
            )
            features = sorted(
                _feature_signature(row)
                for row in data.get("features") or []
                if isinstance(row, dict)
            )
            return (
                _fold(data.get("structure_kind")),
                _fold(data.get("material_state")),
                _fold(data.get("source_type")),
                entities,
                features,
                _fold(data.get("simplified") or data.get("original")),
            )
        if fact.fact_type == "structure_text":
            return _fold(data.get("simplified") or data.get("original"))
    return _clean_signature_value(data)


def _clean_signature_value(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            key: _clean_signature_value(child)
            for key, child in sorted(value.items())
            if key not in _DROP_SIGNATURE_KEYS and child not in (None, "", [], {})
        }
    if isinstance(value, list):
        return [_clean_signature_value(child) for child in value]
    if isinstance(value, str):
        return _fold(value)
    return value


def semantic_fact_signature(fact: AxisFact) -> str:
    """Return a source-presentation-neutral signature, excluding owner identity."""

    return json.dumps(
        [fact.axis, fact.fact_type, _semantic_payload(fact)],
        ensure_ascii=False,
        sort_keys=True,
        default=str,
    )


def deduplicate_axis_facts_with_audit(
    facts: Iterable[AxisFact], *, mode: ClaimQualityMode = "safe"
) -> ClaimQualityResult:
    """Merge semantic duplicates and return a complete removal audit."""

    rows = list(facts)
    if mode == "off":
        return ClaimQualityResult(accepted=rows, issues=[])
    if mode not in {"safe", "strict"}:
        raise ValueError(f"Unsupported claim quality mode: {mode!r}")

    merged: dict[str, AxisFact] = {}
    order: list[str] = []
    passthrough: list[tuple[int, AxisFact]] = []
    issues: list[ClaimQualityIssue] = []
    for index, fact in enumerate(rows):
        # Structure/process observations can repeat the same semantic entity in
        # different regions, sequence positions, or prose spans that the compact
        # candidate does not fully encode.  Their existing axis sanitizers retain
        # those distinctions.  Property aliases have a complete condition/value
        # key and are safe to merge here.
        if not isinstance(fact, PropertyFact):
            passthrough.append((index, fact))
            continue
        signature = semantic_fact_signature(fact)
        existing = merged.get(signature)
        if existing is None:
            merged[signature] = fact
            order.append(signature)
            continue
        issues.append(
            ClaimQualityIssue(
                code="semantic_duplicate_merged",
                sample_id_raw=fact.sample_id_raw,
                fact_type=fact.fact_type,
                path="data",
                message=(
                    "A property alias duplicate was merged into one condition-aware claim."
                ),
                evidence=_fact_evidence(fact),
                expected={"surviving_signature": signature},
                actual={
                    "removed_duplicate": fact.model_dump(),
                    "surviving_fact_before_merge": existing.model_dump(),
                },
                suggested_action=(
                    "Review only if the aliases represent different scientific "
                    "properties under the cited condition."
                ),
            )
        )
        evidence = list(existing.source_evidence)
        for row in fact.source_evidence:
            if row not in evidence:
                evidence.append(row)
        data = dict(existing.data)
        existing_coordinate = str(
            existing.data.get("property_id_candidate") or ""
        ).strip()
        duplicate_coordinate = str(
            fact.data.get("property_id_candidate") or ""
        ).strip()
        if (
            not existing_coordinate.startswith("physical-owner-envelope:")
            and duplicate_coordinate.startswith("physical-owner-envelope:")
            and _fold(existing.sample_id_raw) == _fold(fact.sample_id_raw)
        ):
            # Promotion has already proven this internal source-block owner
            # coordinate. Semantic deduplication may choose an earlier alias as
            # the public survivor, but must not discard that proof before the
            # tensile protocol ledger consumes it.
            data["property_id_candidate"] = duplicate_coordinate
        merged[signature] = existing.model_copy(
            update={
                "data": data,
                "source_evidence": evidence,
                "confidence": max(existing.confidence, fact.confidence),
            }
        )
    property_rows = [merged[key] for key in order]
    # Preserve original relative ordering for non-property facts; property IDs are
    # regenerated deterministically after materialization.
    return ClaimQualityResult(
        accepted=[fact for _, fact in passthrough] + property_rows,
        issues=issues,
    )


def deduplicate_axis_facts(
    facts: Iterable[AxisFact], *, mode: ClaimQualityMode = "safe"
) -> list[AxisFact]:
    """Merge semantic duplicates while preserving all literal evidence."""

    return deduplicate_axis_facts_with_audit(facts, mode=mode).accepted


__all__ = [
    "ClaimQualityMode",
    "ClaimQualityIssue",
    "ClaimQualityResult",
    "core_tensile_subtype",
    "deduplicate_axis_facts",
    "deduplicate_axis_facts_with_audit",
    "filter_composition_precision_facts",
    "filter_axis_facts",
    "is_core_tensile_property_name",
    "semantic_fact_signature",
]
