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
    "reported",
    "studied",
    "tested",
}
_STRUCTURAL_COMPOSITION_VALUE = re.compile(
    r"(?i)\b(?:appear(?:s|ed)?|form(?:s|ed|ation)?|observed|present|located|"
    r"precipitat(?:e|ed|ion)|matrix|film|phase|structure|interface|region)\b"
)
_MEASURED_COMPOSITION_CONTEXT = re.compile(
    r"(?i)(?:\bmeasur(?:e|ed|ement)|\bactual|\banaly(?:sis|sed|zed)|"
    r"\bquantif(?:y|ied|ication)|\b(?:eds|edx|icp|xrf|oes)\b|spectro|"
    r"chemical\s+composition|composition\s*\(|concentration|content|"
    r"\b(?:wt|at|vol|mol)\s*\.?\s*%)"
)
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
    "elongation at break": "elongation",
    "elongation at failure": "elongation",
    "elongation at fracture": "elongation",
    "fracture elongation": "elongation",
    "tensile elongation": "elongation",
    "total elongation": "elongation",
    "uniform elongation": "elongation",
    "young s modulus": "elastic modulus",
    "youngs modulus": "elastic modulus",
    "microhardness": "vickers hardness",
    "vickers microhardness": "vickers hardness",
}
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
    value_numbers = _numbers(value)
    evidence_numbers = _numbers("\n".join(evidence))
    if value_numbers and evidence_numbers and not _value_is_grounded(value, evidence):
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
    return fact, []


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
            cleaned, fact_issues = fact, []
        else:  # pragma: no cover - AxisFact is a closed discriminated union.
            cleaned, fact_issues = fact, []
        issues.extend(fact_issues)
        if cleaned is not None:
            accepted.append(cleaned)
    return ClaimQualityResult(accepted=accepted, issues=issues)


def _canonical_name(value: Any) -> str:
    folded = _fold(value)
    return _PROPERTY_ALIASES.get(folded, folded)


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
        return (
            _canonical_name(data.get("property_name_raw")),
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


def deduplicate_axis_facts(
    facts: Iterable[AxisFact], *, mode: ClaimQualityMode = "safe"
) -> list[AxisFact]:
    """Merge semantic duplicates while preserving all literal evidence."""

    rows = list(facts)
    if mode == "off":
        return rows
    if mode not in {"safe", "strict"}:
        raise ValueError(f"Unsupported claim quality mode: {mode!r}")

    merged: dict[str, AxisFact] = {}
    order: list[str] = []
    passthrough: list[tuple[int, AxisFact]] = []
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
        evidence = list(existing.source_evidence)
        for row in fact.source_evidence:
            if row not in evidence:
                evidence.append(row)
        merged[signature] = existing.model_copy(
            update={
                "source_evidence": evidence,
                "confidence": max(existing.confidence, fact.confidence),
            }
        )
    property_rows = [merged[key] for key in order]
    # Preserve original relative ordering for non-property facts; property IDs are
    # regenerated deterministically after materialization.
    return [fact for _, fact in passthrough] + property_rows


__all__ = [
    "ClaimQualityMode",
    "ClaimQualityIssue",
    "ClaimQualityResult",
    "deduplicate_axis_facts",
    "filter_axis_facts",
    "semantic_fact_signature",
]
