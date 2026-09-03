"""Provider-neutral deterministic routing for Alpha25 verification.

The classifier never accepts or rejects scientific content. It only decides
whether one already promoted candidate needs the expensive hierarchical
verifier. Every rule is source-local and paper/model/provider neutral.
"""

from __future__ import annotations

import json
import re
import unicodedata
from collections import Counter, defaultdict
from dataclasses import dataclass
from typing import Any, Iterable, Sequence

from knowmat.alpha25.contracts import AxisFact, InventoryAnchor


RISK_ROUTING_VERSION = "alpha25_verification_risk_v4"

_COMPARISON = re.compile(
    r"(?i)\b(?:respectively|whereas|while|compared\s+(?:with|to)|"
    r"than|versus|vs\.?|higher|lower|greater|less|different)\b"
)
_QUALITATIVE_PARAMETER = re.compile(
    r"(?i)^(?:different|higher|lower|greater|less|increased?|decreased?|"
    r"varied|variable|not[_\s-]*reported|unknown|same|similar)$"
)
_STATE_AS_PROCESS = re.compile(
    r"(?i)^(?:as[\s-]*(?:printed|built|fabricated|deposited|cast)|"
    r"aged?|annealed?|heat[\s-]*treated|solutionized|sintered)$"
)
_FIGURE_OR_PARAMETRIC = re.compile(
    r"(?i)\b(?:fig(?:ure)?\.?\s*\d+|as\s+(?:a\s+)?function\s+of|"
    r"calculated\s+.*\bversus\b)"
)
_RESPECTIVELY = re.compile(r"(?i)\brespectively\b")
_EXPLICIT_COLLECTIVE = re.compile(
    r"(?i)\b(?:both|all|each|every)\b"
)
_SOURCE_LOCATOR_VALUE = re.compile(
    r"(?i)\b(?:digitized|replotted|taken|read|estimated)\s+from\s+"
    r"(?:fig(?:ure)?|table|plot|curve)\b"
)
_QUALITATIVE_SCALAR_VALUE = re.compile(
    r"(?i)^(?:higher|lower|greater|less|stronger|weaker|more|fewer|"
    r"increased|decreased|similar|comparable|superior|inferior)\b"
)
_CONDITION_TOKEN = re.compile(
    r"(?i)(?:[-+]?\d+(?:\.\d+)?\s*(?:°\s*c|k|h(?:ours?|rs?)?|min|s(?:ec)?|"
    r"s\s*[-^]?\s*1|mm\s*/\s*min)|\b(?:room temperature|rt|vacuum|air|argon)\b)"
)
_UNREPORTED = {
    "",
    "none",
    "notreported",
    "unknown",
    "unspecified",
    "na",
}
_SIGNATURE_DROP_KEYS = {
    "candidate_stage_id",
    "characterization_id",
    "confidence",
    "evidence_unit_id",
    "observation_id",
    "original",
    "property_id_candidate",
    "sample_id",
    "sample_id_raw",
    "simplified",
    "source_evidence",
}


@dataclass(frozen=True)
class VerificationRiskDecision:
    route_to_verifier: bool
    severity: str
    risk_codes: tuple[str, ...]


def _compact(value: Any) -> str:
    text = unicodedata.normalize("NFKC", str(value or "")).casefold()
    return re.sub(r"[^a-z0-9]+", "", text)


def _evidence_text(fact: AxisFact) -> str:
    rows = [str(row) for row in fact.source_evidence if str(row).strip()]
    nested = fact.data.get("source_evidence")
    if isinstance(nested, str) and nested.strip():
        rows.append(nested)
    elif isinstance(nested, list):
        rows.extend(str(row) for row in nested if str(row).strip())
    return "\n".join(dict.fromkeys(rows))


def _literal(value: Any, evidence: str) -> bool:
    """Require a contiguous literal token sequence, not a compact substring.

    Compact substring matching made short sample IDs unsafe: ``PL`` matched
    the tail of ``Sample`` and created false multi-owner risks.  Presentation
    normalization still treats OCR/LaTeX unit spellings as equivalent.
    """

    def tokens(raw: Any) -> list[str]:
        text = unicodedata.normalize("NFKC", str(raw or "")).casefold()
        text = text.replace(r"\mu", "μ")
        text = re.sub(r"\^\s*\{?\s*\\circ\s*\}?", "°", text)
        text = text.replace(r"\circ", "°")
        text = re.sub(r"[$^{}_]", "", text)
        text = re.sub(r"([μµ])\s+(?=[a-z])", r"\1", text)
        return re.findall(
            r"[-+]?\d+(?:\.\d+)?|[^\W\d_]+|%|°",
            text,
            flags=re.UNICODE,
        )

    needle = tokens(value)
    if not needle:
        return True
    haystack = tokens(evidence)
    width = len(needle)
    return any(
        haystack[start : start + width] == needle
        for start in range(len(haystack) - width + 1)
    )


def _payload_literals(fact: AxisFact) -> list[str]:
    data = fact.data
    values: list[str] = []
    if fact.fact_type == "process_stage":
        # Routing is precision-focused on immutable scientific coordinates.
        # A normalized process label is reviewed only by dedicated semantic
        # risks (for example state_as_process), while literal parameter values
        # and units determine whether the payload itself is source-grounded.
        for parameter in data.get("parameters_raw") or []:
            if not isinstance(parameter, dict):
                continue
            values.extend(
                str(parameter.get(key) or "")
                for key in ("value_raw", "unit_raw")
            )
    elif fact.fact_type == "structure_observation":
        values.extend(
            str(data.get(key) or "")
            for key in ("material_state", "region")
        )
        features = [
            row for row in data.get("features") or [] if isinstance(row, dict)
        ]
        for entity in data.get("entities") or []:
            if not isinstance(entity, dict):
                continue
            values.extend(
                str(entity.get(key) or "")
                for key in ("name_raw", "role", "raw_expression")
            )
            features.extend(
                row
                for row in entity.get("features") or []
                if isinstance(row, dict)
            )
        for feature in features:
            values.extend(
                str(feature.get(key) or "")
                for key in ("value_raw", "unit_raw")
            )
    elif fact.fact_type == "characterization":
        values.append(str(data.get("method_raw") or ""))
    return [
        value
        for value in values
        if _compact(value) not in _UNREPORTED and len(_compact(value)) >= 2
    ]


def _nested_literals(value: Any, keys: set[str]) -> tuple[str, ...]:
    rows: list[str] = []
    if isinstance(value, dict):
        for key, child in value.items():
            if key in keys and not isinstance(child, (dict, list)):
                text = str(child or "").strip()
                if _compact(text) not in _UNREPORTED:
                    rows.append(text)
            elif isinstance(child, (dict, list)):
                rows.extend(_nested_literals(child, keys))
    elif isinstance(value, list):
        for child in value:
            rows.extend(_nested_literals(child, keys))
    return tuple(dict.fromkeys(rows))


def _condition_literals(fact: AxisFact) -> tuple[str, ...]:
    keys = {
        "condition_raw",
        "orientation",
        "orientation_raw",
        "region",
        "region_raw",
        "test_condition_raw",
    }
    return _nested_literals(fact.data, keys)


def _clean_signature(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            key: _clean_signature(child)
            for key, child in sorted(value.items())
            if key not in _SIGNATURE_DROP_KEYS
            and child not in (None, "", [], {})
        }
    if isinstance(value, list):
        return [_clean_signature(child) for child in value]
    if isinstance(value, str):
        return " ".join(value.casefold().split())
    return value


def _scientific_signature(fact: AxisFact) -> str:
    return json.dumps(
        {
            "axis": fact.axis,
            "fact_type": fact.fact_type,
            "data": _clean_signature(fact.data),
        },
        ensure_ascii=False,
        sort_keys=True,
        default=str,
    )


def _owner_labels(anchors: Iterable[InventoryAnchor]) -> tuple[str, ...]:
    return tuple(
        dict.fromkeys(
            str(value).strip()
            for anchor in anchors
            for value in (anchor.sample_id_raw, anchor.material_name_raw)
            if str(value or "").strip() and len(_compact(value)) >= 2
        )
    )


def _base_risk_codes(
    fact: AxisFact, *, known_owner_labels: Sequence[str]
) -> set[str]:
    codes: set[str] = set()
    evidence = _evidence_text(fact)
    evidence_rows = list(dict.fromkeys(fact.source_evidence))
    payload_literals = _payload_literals(fact)

    if float(fact.confidence) < 0.8:
        codes.add("low_confidence")
    owner_not_literal = not _literal(fact.sample_id_raw, evidence)
    if owner_not_literal:
        codes.add("owner_not_literal")
    literal_owner_labels = {
        str(label).strip()
        for label in known_owner_labels
        if _literal(label, evidence)
    }
    named_owners = {_compact(label) for label in literal_owner_labels}
    asserted_owner = _compact(fact.sample_id_raw)
    compatible_literal_owners = {
        label
        for label in literal_owner_labels
        if asserted_owner
        and (
            asserted_owner in _compact(label)
            or _compact(label) in asserted_owner
        )
    }
    if len(named_owners) > 1:
        codes.add("multi_owner_evidence")
    missing_literals = [
        value for value in payload_literals if not _literal(value, evidence)
    ]
    if missing_literals:
        codes.add("nonliteral_payload_field")
    if len(evidence_rows) > 1 and len(payload_literals) > 1:
        codes.add("multi_evidence_payload")
    if _COMPARISON.search(evidence) and len(payload_literals) > 1:
        codes.add("comparative_payload_fanout")
    if (
        owner_not_literal
        and not compatible_literal_owners
        and _COMPARISON.search(evidence)
    ):
        codes.add("comparative_owner_projection")
    original = str(fact.data.get("original") or "").strip()
    if original and not _literal(original, evidence):
        codes.add("evidence_envelope_expansion")
    if (
        _FIGURE_OR_PARAMETRIC.search(evidence)
        and owner_not_literal
        and not compatible_literal_owners
    ):
        codes.add("figure_owner_projection")

    if fact.fact_type == "property":
        value = str(fact.data.get("value_raw") or "").strip()
        condition = str(fact.data.get("test_condition_raw") or "").strip()
        if _SOURCE_LOCATOR_VALUE.search(value):
            codes.add("source_locator_scalar")
        if _QUALITATIVE_SCALAR_VALUE.search(value):
            codes.add("qualitative_scalar_projection")
        condition_tokens = {
            _compact(match.group(0))
            for match in _CONDITION_TOKEN.finditer(evidence)
            if _compact(match.group(0))
        }
        if condition and not _literal(condition, evidence) and len(condition_tokens) > 1:
            codes.add("multi_condition_projection")

    asserted_conditions = _condition_literals(fact)
    if any(not _literal(value, evidence) for value in asserted_conditions):
        if _COMPARISON.search(evidence) or len(
            {_compact(match.group(0)) for match in _CONDITION_TOKEN.finditer(evidence)}
        ) > 1:
            codes.add("multi_condition_projection")
    state = str(
        fact.data.get("material_state") or fact.data.get("state_raw") or ""
    ).strip()
    if (
        _compact(state) not in _UNREPORTED
        and not _literal(state, evidence)
        and _COMPARISON.search(evidence)
    ):
        codes.add("multi_condition_projection")

    if _RESPECTIVELY.search(evidence) and len(named_owners) > 1:
        numeric_values = re.findall(r"[-+]?\d+(?:\.\d+)?", evidence)
        if len(numeric_values) > 1:
            codes.add("respectively_mapping_ambiguous")
    if _EXPLICIT_COLLECTIVE.search(evidence) and len(named_owners) > 1:
        codes.add("explicit_collective_mapping")
    if (
        _EXPLICIT_COLLECTIVE.search(evidence)
        and owner_not_literal
        and missing_literals
    ):
        codes.add("collective_payload_projection")
    if owner_not_literal and named_owners and not compatible_literal_owners:
        codes.add("owner_conflicts_with_literal_entity")

    if fact.fact_type == "process_stage":
        process_name = str(fact.data.get("process_name_raw") or "").strip()
        if _STATE_AS_PROCESS.fullmatch(process_name):
            codes.add("state_as_process")
        parameter_values = [
            str(parameter.get("value_raw") or "").strip()
            for parameter in fact.data.get("parameters_raw") or []
            if isinstance(parameter, dict)
        ]
        if any(_QUALITATIVE_PARAMETER.fullmatch(value) for value in parameter_values):
            codes.add("qualitative_parameter_projection")
        parameters = [
            row
            for row in fact.data.get("parameters_raw") or []
            if isinstance(row, dict)
            and str(row.get("value_raw") or "").strip()
        ]
        if (
            len(parameters) > 1
            and _RESPECTIVELY.search(evidence)
            and len(re.findall(r"[-+]?\d+(?:\.\d+)?", evidence)) > 1
        ):
            codes.add("respectively_condition_mapping_ambiguous")
    return codes


def classify_verification_risks(
    facts: Sequence[AxisFact],
    anchors: Sequence[InventoryAnchor],
) -> tuple[VerificationRiskDecision, ...]:
    """Return one deterministic verifier-routing decision per candidate fact."""

    known_owner_labels = _owner_labels(anchors)
    codes_by_position = [
        _base_risk_codes(fact, known_owner_labels=known_owner_labels)
        for fact in facts
    ]

    signature_owners: dict[str, set[str]] = defaultdict(set)
    signature_positions: dict[str, list[int]] = defaultdict(list)
    for position, fact in enumerate(facts):
        signature = _scientific_signature(fact)
        signature_owners[signature].add(_compact(fact.sample_id_raw))
        signature_positions[signature].append(position)
    for signature, owners in signature_owners.items():
        if len(owners) <= 1:
            continue
        for position in signature_positions[signature]:
            codes_by_position[position].add("cross_owner_duplicate_payload")

        positions = signature_positions[signature]
        evidence_rows = [_evidence_text(facts[position]) for position in positions]
        shared_evidence = len({_compact(row) for row in evidence_rows}) == 1
        collective = all(_EXPLICIT_COLLECTIVE.search(row) for row in evidence_rows)
        owners_literal = all(
            _literal(facts[position].sample_id_raw, evidence_rows[index])
            for index, position in enumerate(positions)
        )
        if shared_evidence and owners_literal and not collective:
            for position in positions:
                codes_by_position[position].add("cross_owner_payload_projection")

    def severity(codes: set[str], fact: AxisFact) -> str:
        # Hard risk means formal correctness cannot be established without a
        # unique owner/value/condition mapping. Keep this set deliberately
        # narrow because hard-risk technical failure isolates formal output.
        if fact.fact_type in {"process_text", "structure_text"}:
            return "none"
        if codes & {
            "cross_owner_payload_projection",
            "figure_owner_projection",
            "multi_condition_projection",
            "owner_conflicts_with_literal_entity",
            "qualitative_parameter_projection",
            "qualitative_scalar_projection",
            "respectively_mapping_ambiguous",
            "respectively_condition_mapping_ambiguous",
            "source_locator_scalar",
            "state_as_process",
            "comparative_owner_projection",
            "collective_payload_projection",
        }:
            return "hard"
        if "multi_evidence_payload" in codes and codes & {
            "comparative_payload_fanout",
            "multi_owner_evidence",
            "nonliteral_payload_field",
        }:
            return "soft"
        if {
            "comparative_payload_fanout",
            "nonliteral_payload_field",
        } <= codes:
            return "soft"
        if codes & {
            "evidence_envelope_expansion",
            "low_confidence",
        }:
            return "soft"
        return "none"

    decisions = []
    for fact, codes in zip(facts, codes_by_position):
        level = severity(codes, fact)
        decisions.append(
            VerificationRiskDecision(
                route_to_verifier=level != "none",
                severity=level,
                risk_codes=tuple(sorted(codes)),
            )
        )
    return tuple(decisions)


def summarize_risk_codes(
    decisions: Iterable[VerificationRiskDecision],
) -> dict[str, int]:
    counts: Counter[str] = Counter(
        code for decision in decisions for code in decision.risk_codes
    )
    return dict(sorted(counts.items()))


def summarize_risk_severities(
    decisions: Iterable[VerificationRiskDecision],
) -> dict[str, int]:
    counts: Counter[str] = Counter(decision.severity for decision in decisions)
    return dict(sorted(counts.items()))


__all__ = [
    "RISK_ROUTING_VERSION",
    "VerificationRiskDecision",
    "classify_verification_risks",
    "summarize_risk_codes",
    "summarize_risk_severities",
]
