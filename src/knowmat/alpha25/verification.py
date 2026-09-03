"""Deterministic validation and application of hierarchical verifier output."""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from typing import Any, Iterable, Literal

from pydantic import TypeAdapter, ValidationError

from knowmat.alpha25.contracts import AxisFact
from knowmat.alpha25.verification_contracts import (
    AssertionEnvelope,
    COMPACT_REVIEW_PROTOCOL_VERSION,
    CompactLabel,
    CompactReviewDecision,
    CompactReviewResponse,
    EvidenceSpan,
    FIELD_VERIFICATION_PROTOCOL_VERSION,
    FieldVerificationDecision,
    FieldVerificationResponse,
    ReassignmentPatch,
    RecoveryRequest,
    RecoveryResponse,
    VerificationAuditRecord,
    VerificationBundle,
    VerificationDecision,
    VerificationResponse,
    canonical_json,
)
from knowmat.alpha25.verification_inventory import VerificationInventory


_AXIS_FACT_ADAPTER = TypeAdapter(AxisFact)
_PRESENTATION_KEYS = {
    "confidence",
    "source_evidence",
    "property_id_candidate",
    "candidate_stage_id",
    "observation_id",
    "characterization_id",
}


class VerificationGroundingError(ValueError):
    """A syntactically valid verifier response exceeded its evidence authority."""


@dataclass(frozen=True)
class AppliedVerification:
    """Atomic output from one or more completely validated bundles."""

    accepted: tuple[AxisFact, ...]
    audit_records: tuple[dict[str, Any], ...]
    issues: tuple[dict[str, Any], ...]
    decided_assertion_ids: tuple[str, ...]
    accepted_assertion_ids: tuple[str, ...] = ()


def _fold(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "").casefold()).strip()


_LATEX_LITERAL_REPLACEMENTS = {
    r"\alpha": " α ",
    r"\beta": " β ",
    r"\gamma": " γ ",
    r"\delta": " δ ",
    r"\epsilon": " ε ",
    r"\theta": " θ ",
    r"\lambda": " λ ",
    # Keep the following unit character adjacent: ``\\mum`` means ``µm``.
    r"\mu": "μ",
    r"\pm": " ± ",
    r"\sigma": " σ ",
    r"\phi": " φ ",
    r"\omega": " ω ",
}


def _literal_tokens(value: Any) -> list[str]:
    """Tokenize literal evidence while normalizing common OCR/LaTeX variants.

    PaddleOCR/Markdown sources routinely encode ``µm`` as ``\\mum`` and a
    phase such as ``σ`` as ``\\sigma``.  Inventory location already treats
    these as presentation variants; the applicator must use the same
    scientific identity or it can reject a correctly cited provider answer.
    """

    text = unicodedata.normalize("NFKC", str(value or "")).casefold()
    for latex, literal in _LATEX_LITERAL_REPLACEMENTS.items():
        text = text.replace(latex, literal)
    text = re.sub(r"\^\s*\{?\s*\\circ\s*\}?", "°", text)
    text = text.replace(r"\circ", "°")
    # TeX math delimiters and grouping do not carry scientific identity.
    text = re.sub(r"[$^{}_]", "", text)
    # Markdown commonly renders ``$ \\mu $m`` with a presentation-only space
    # between the Greek prefix and its following unit symbol.
    text = re.sub(r"([μµ])\s+(?=[a-z])", r"\1", text)
    return re.findall(
        r"[-+]?\d+(?:\.\d+)?|[^\W\d_]+(?:-[^\W\d_]+)*|%|°",
        text,
        flags=re.UNICODE,
    )


def _source_text_for(
    evidence_ids: Iterable[str], evidence_by_id: dict[str, EvidenceSpan]
) -> str:
    return "\n".join(
        evidence_by_id[evidence_id].text
        for evidence_id in evidence_ids
        if evidence_id in evidence_by_id
    )


def _strip_presentation(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            key: _strip_presentation(child)
            for key, child in sorted(value.items())
            if key not in _PRESENTATION_KEYS and child not in (None, "", [], {})
        }
    if isinstance(value, list):
        return [_strip_presentation(child) for child in value]
    if isinstance(value, str):
        return _fold(value)
    return value


def _merge_compatible(rows: list[AssertionEnvelope]) -> bool:
    if len(rows) < 2:
        return False
    if len({(row.axis, row.fact_type, _fold(row.sample_id_raw)) for row in rows}) != 1:
        return False
    if rows[0].axis == "properties":
        data_rows = [row.candidate.get("data", {}) for row in rows]
        required = ("property_name_raw", "value_raw", "unit_raw")
        if any(
            len({_fold(data.get(key)) for data in data_rows}) != 1 for key in required
        ):
            return False
        for key in (
            "test_method_raw",
            "test_standard_raw",
            "test_condition_raw",
            "test_specimen_raw",
        ):
            present = {_fold(data.get(key)) for data in data_rows if _fold(data.get(key))}
            if len(present) > 1:
                return False
        return True
    signatures = [_strip_presentation(row.candidate) for row in rows]
    return all(signature == signatures[0] for signature in signatures[1:])


def _union_fact_provenance(facts: list[AxisFact], survivor: AxisFact) -> AxisFact:
    payload = survivor.model_dump(mode="json")
    top_evidence = list(payload.get("source_evidence") or [])
    data = dict(payload.get("data") or {})
    nested_evidence = list(data.get("source_evidence") or [])
    confidence = float(payload.get("confidence") or 0.0)
    nested_confidence = float(data.get("confidence") or 0.0)
    for fact in facts:
        row = fact.model_dump(mode="json")
        for quote in row.get("source_evidence") or []:
            if quote not in top_evidence:
                top_evidence.append(quote)
        nested = row.get("data") if isinstance(row.get("data"), dict) else {}
        for quote in nested.get("source_evidence") or []:
            if quote not in nested_evidence:
                nested_evidence.append(quote)
        confidence = max(confidence, float(row.get("confidence") or 0.0))
        nested_confidence = max(
            nested_confidence, float(nested.get("confidence") or 0.0)
        )
    payload["source_evidence"] = top_evidence
    payload["confidence"] = confidence
    if "source_evidence" in data:
        data["source_evidence"] = nested_evidence
    if "confidence" in data:
        data["confidence"] = nested_confidence
    payload["data"] = data
    return _AXIS_FACT_ADAPTER.validate_python(payload)


def _literal_in_evidence(value: str | None, source: str) -> bool:
    if value is None:
        return True
    folded = _fold(value)
    return not folded or folded in _fold(source)


def _literal_coordinate_in_evidence(value: str | None, source: str) -> bool:
    """Match one immutable coordinate across OCR/Markdown presentation forms.

    Exact folded text remains the first authority.  The token fallback is
    deliberately contiguous: it accepts presentation-only variants such as
    ``µm``/``\\mu m`` and ``°C``/``^\\circC`` without accepting a paraphrase or
    a reordered scientific coordinate.
    """

    if _literal_in_evidence(value, source):
        return True
    value_tokens = _literal_tokens(value)
    source_tokens = _literal_tokens(source)
    if not value_tokens or len(value_tokens) > len(source_tokens):
        return False
    width = len(value_tokens)
    return any(
        source_tokens[start : start + width] == value_tokens
        for start in range(len(source_tokens) - width + 1)
    )


def _source_supports_quote(quote: str, source: str) -> bool:
    """Accept a literal quote or an ordered table projection in one source scope."""

    if _literal_in_evidence(quote, source):
        return True
    quote_tokens = _literal_tokens(quote)
    source_tokens = _literal_tokens(source)
    if len(quote_tokens) < 3:
        return False
    cursor = 0
    for token in quote_tokens:
        try:
            cursor = source_tokens.index(token, cursor) + 1
        except ValueError:
            return False
    return True


def _validate_candidate_grounding(
    envelope: AssertionEnvelope,
    decision: VerificationDecision,
    bundle: VerificationBundle,
    *,
    allow_owner_change: bool = False,
    allow_condition_change: bool = False,
) -> None:
    """Require the immutable scientific payload to occur in cited source text."""

    evidence_by_id = {row.evidence_id: row for row in bundle.evidence}
    cited_text = _source_text_for(decision.evidence_ids, evidence_by_id)
    candidate = envelope.candidate
    for quote in candidate.get("source_evidence") or []:
        if not _source_supports_quote(str(quote), cited_text):
            raise VerificationGroundingError(
                "candidate source_evidence is not contained in cited evidence"
            )
    data = candidate.get("data") if isinstance(candidate.get("data"), dict) else {}
    nested_evidence = data.get("source_evidence") or []
    if isinstance(nested_evidence, str):
        nested_evidence = [nested_evidence]
    for quote in nested_evidence:
        if not _source_supports_quote(str(quote), cited_text):
            raise VerificationGroundingError(
                "candidate nested source_evidence is not contained in cited evidence"
            )
    if envelope.axis != "properties":
        return
    value = str(data.get("value_raw") or "").strip()
    unit = str(data.get("unit_raw") or "").strip()
    if value and not _literal_in_evidence(value, cited_text):
        raise VerificationGroundingError(
            "property value is not literal in cited evidence"
        )
    if unit and not _literal_in_evidence(unit, cited_text):
        raise VerificationGroundingError(
            "property unit is not literal in cited evidence"
        )
    if not allow_owner_change:
        owner_is_literal = _literal_in_evidence(envelope.sample_id_raw, cited_text)
        owner_entity_supported = any(
            _fold(entity.sample_id_raw) == _fold(envelope.sample_id_raw)
            and any(evidence_id in decision.evidence_ids for evidence_id in entity.evidence_ids)
            for entity in bundle.entities
        )
        if not owner_is_literal and not owner_entity_supported:
            raise VerificationGroundingError(
                "property owner is not grounded in cited evidence or inventory"
            )
    if not allow_condition_change:
        condition = str(data.get("test_condition_raw") or "").strip()
        if condition:
            numeric_tokens = re.findall(r"[-+]?\d+(?:\.\d+)?", condition)
            cited_numbers = set(re.findall(r"[-+]?\d+(?:\.\d+)?", cited_text))
            if numeric_tokens and not set(numeric_tokens) <= cited_numbers:
                raise VerificationGroundingError(
                    "property condition numbers are not literal in cited evidence"
                )
            if not numeric_tokens and not _literal_in_evidence(condition, cited_text):
                raise VerificationGroundingError(
                    "property condition is not literal in cited evidence"
                )
        specimen = str(data.get("test_specimen_raw") or "").strip()
        if specimen and not _literal_in_evidence(specimen, cited_text):
            raise VerificationGroundingError(
                "property specimen is not literal in cited evidence"
            )


def _apply_reassignment(
    envelope: AssertionEnvelope,
    decision: VerificationDecision,
    bundle: VerificationBundle,
    fact: AxisFact,
) -> AxisFact:
    patch = decision.reassignment
    if patch is None:
        raise VerificationGroundingError("missing reassignment patch")
    evidence_by_id = {row.evidence_id: row for row in bundle.evidence}
    cited_text = _source_text_for(decision.evidence_ids, evidence_by_id)
    entities = {row.entity_id: row for row in bundle.entities}
    entity = entities.get(patch.entity_id) if patch.entity_id else None
    if patch.entity_id and entity is None:
        raise VerificationGroundingError("reassignment cites an unknown inventory entity")
    if entity is not None:
        if patch.sample_id_raw not in (None, entity.sample_id_raw):
            raise VerificationGroundingError("reassigned owner conflicts with inventory entity")
        if patch.state_raw not in (None, entity.state_raw):
            raise VerificationGroundingError("reassigned state conflicts with inventory entity")
    target_owner = patch.sample_id_raw or (entity.sample_id_raw if entity else None)
    target_state = patch.state_raw or (entity.state_raw if entity else None)
    for label, value in (
        ("owner", target_owner),
        ("state", target_state),
        ("condition", patch.test_condition_raw),
        ("specimen", patch.test_specimen_raw),
    ):
        if not _literal_in_evidence(value, cited_text):
            raise VerificationGroundingError(
                f"reassigned {label} is not literal in cited evidence"
            )

    payload = fact.model_dump(mode="json")
    data = dict(payload.get("data") or {})
    if target_owner:
        payload["sample_id_raw"] = target_owner
        if "sample_id" in data:
            data["sample_id"] = target_owner
    if target_state:
        if "material_state" not in data:
            raise VerificationGroundingError(
                "candidate contract has no material_state field to reassign"
            )
        data["material_state"] = target_state
    if patch.test_condition_raw is not None:
        if "test_condition_raw" not in data:
            raise VerificationGroundingError(
                "candidate contract has no test_condition_raw field to reassign"
            )
        data["test_condition_raw"] = patch.test_condition_raw
    if patch.test_specimen_raw is not None:
        if "test_specimen_raw" not in data:
            raise VerificationGroundingError(
                "candidate contract has no test_specimen_raw field to reassign"
            )
        data["test_specimen_raw"] = patch.test_specimen_raw
    payload["data"] = data
    try:
        return _AXIS_FACT_ADAPTER.validate_python(payload)
    except ValidationError as exc:
        raise VerificationGroundingError(
            f"reassignment violates the existing AxisFact contract: {exc}"
        ) from exc


def _audit_record(
    *,
    envelope: AssertionEnvelope,
    decision: VerificationDecision,
    bundle: VerificationBundle,
    after: AxisFact | None,
    verifier_role: Literal["primary", "fallback", "deterministic"],
    fallback_used: bool,
    cache_hit: bool,
) -> dict[str, Any]:
    evidence_by_id = {row.evidence_id: row for row in bundle.evidence}
    audit = VerificationAuditRecord(
        assertion_id=envelope.assertion_id,
        bundle_id=bundle.bundle_id,
        decision=decision.decision,
        reason_code=decision.reason_code,
        before=envelope.candidate,
        after=after.model_dump(mode="json") if after is not None else None,
        evidence=[
            evidence_by_id[evidence_id]
            for evidence_id in decision.evidence_ids
            if evidence_id in evidence_by_id
        ],
        merge_member_ids=decision.merge_member_ids,
        verifier_role=verifier_role,
        fallback_used=fallback_used,
        cache_hit=cache_hit,
        rationale=decision.rationale,
    )
    return audit.model_dump(mode="json", exclude_none=True)


def _issue_record(
    envelope: AssertionEnvelope,
    decision: VerificationDecision,
    audit: dict[str, Any],
) -> dict[str, Any] | None:
    if decision.decision == "accept":
        return None
    severity = "review" if decision.decision in {"quarantine", "unresolved"} else "info"
    return {
        "code": f"verifier_{decision.decision}",
        "severity": severity,
        "path": f"items.{envelope.sample_id_raw}.{envelope.axis}",
        "message": decision.reason_code,
        "evidence": [row.get("evidence_id") for row in audit.get("evidence", [])],
        "expected": {"assertion_id": envelope.assertion_id, "source_grounded": True},
        "actual": {
            "assertion_id": envelope.assertion_id,
            "bundle_id": audit["bundle_id"],
            "decision": decision.decision,
            "reason_code": decision.reason_code,
        },
        "suggested_action": (
            "Review the complete linked record in quality_audit.json."
            if severity == "review"
            else "No manual action is required unless the linked audit is disputed."
        ),
    }


def required_scientific_fields(
    envelope: AssertionEnvelope,
) -> tuple[str, ...]:
    """Return the exact immutable fields a v2 verifier must adjudicate."""

    fields = ["semantic"]
    data = envelope.candidate.get("data")
    data = data if isinstance(data, dict) else {}
    if _scientific_field_literals(data, "value"):
        fields.append("value")
    if _scientific_field_literals(data, "unit"):
        fields.append("unit")
    fields.append("owner")
    state = str(
        data.get("material_state")
        or data.get("state_raw")
        or ""
    ).strip()
    if _fold(state) not in {"", "not_reported", "unknown", "unspecified"}:
        fields.append("state")
    if _scientific_field_literals(data, "condition"):
        fields.append("condition")
    if str(data.get("test_specimen_raw") or "").strip():
        fields.append("specimen")
    if str(data.get("origin") or "").strip():
        fields.append("origin")
    if str(data.get("role") or "").strip():
        fields.append("role")
    return tuple(fields)


_FIELD_SOURCE_KEYS = {
    "value": {"value_raw"},
    "unit": {"unit_raw"},
    "condition": {
        "condition_raw",
        "orientation",
        "orientation_raw",
        "region",
        "region_raw",
        "test_condition_raw",
    },
}
_NON_ASSERTED_LITERALS = {
    "",
    "n/a",
    "na",
    "none",
    "not reported",
    "not_reported",
    "unknown",
    "unspecified",
}


def _scientific_field_literals(data: Any, field: str) -> tuple[str, ...]:
    """Collect every immutable literal represented by one aggregate field.

    A field verdict is atomic for the complete assertion. Processing parameters
    and structure/entity features therefore contribute all of their nested
    ``value_raw``/``unit_raw`` coordinates instead of silently escaping review.
    """

    keys = _FIELD_SOURCE_KEYS.get(field, set())
    values: list[str] = []

    def visit(node: Any) -> None:
        if isinstance(node, dict):
            for key, child in node.items():
                if key in keys and not isinstance(child, (dict, list)):
                    text = str(child or "").strip()
                    if text.casefold() not in _NON_ASSERTED_LITERALS:
                        values.append(text)
                elif isinstance(child, (dict, list)):
                    visit(child)
        elif isinstance(node, list):
            for child in node:
                visit(child)

    visit(data)
    return tuple(dict.fromkeys(values))


def _field_cited_text(
    verdict: Any, evidence_by_id: dict[str, EvidenceSpan]
) -> str:
    return _source_text_for(verdict.evidence_ids, evidence_by_id)


def _validate_supported_field(
    envelope: AssertionEnvelope,
    field: str,
    cited_text: str,
    bundle: VerificationBundle,
    evidence_ids: set[str],
) -> None:
    data = envelope.candidate.get("data")
    data = data if isinstance(data, dict) else {}
    if field == "value":
        for value in _scientific_field_literals(data, "value"):
            if not _literal_coordinate_in_evidence(value, cited_text):
                raise VerificationGroundingError(
                    "supported value is not literal in cited evidence"
                )
    elif field == "unit":
        for unit in _scientific_field_literals(data, "unit"):
            if not _literal_coordinate_in_evidence(unit, cited_text):
                raise VerificationGroundingError(
                    "supported unit is not literal in cited evidence"
                )
    elif field == "owner":
        literal = _literal_in_evidence(envelope.sample_id_raw, cited_text)
        entity_supported = any(
            _fold(entity.sample_id_raw) == _fold(envelope.sample_id_raw)
            and bool(set(entity.evidence_ids) & evidence_ids)
            for entity in bundle.entities
        )
        if not literal and not entity_supported:
            raise VerificationGroundingError(
                "supported owner is not grounded in cited evidence or inventory"
            )
    elif field == "state":
        state = str(data.get("material_state") or data.get("state_raw") or "").strip()
        literal = _literal_in_evidence(state, cited_text)
        entity_supported = any(
            _fold(entity.state_raw) == _fold(state)
            and bool(set(entity.evidence_ids) & evidence_ids)
            for entity in bundle.entities
            if entity.state_raw
        )
        if state and not literal and not entity_supported:
            raise VerificationGroundingError(
                "supported state is not grounded in cited evidence or inventory"
            )
    elif field == "condition":
        for condition in _scientific_field_literals(data, "condition"):
            if _literal_coordinate_in_evidence(condition, cited_text):
                continue
            numbers = re.findall(r"[-+]?\d+(?:\.\d+)?", condition)
            cited_numbers = set(re.findall(r"[-+]?\d+(?:\.\d+)?", cited_text))
            if not numbers or not set(numbers) <= cited_numbers:
                raise VerificationGroundingError(
                    "supported condition is not grounded in cited evidence"
                )
    elif field == "specimen":
        specimen = str(data.get("test_specimen_raw") or "").strip()
        if specimen and not _literal_in_evidence(specimen, cited_text):
            raise VerificationGroundingError(
                "supported specimen is not literal in cited evidence"
            )


def _validate_field_target(
    field_verdict: Any,
    *,
    envelope: AssertionEnvelope,
    bundle: VerificationBundle,
    cited_text: str,
) -> None:
    if field_verdict.selected_entity_id is None and field_verdict.selected_text is None:
        return
    entities = {row.entity_id: row for row in bundle.entities}
    entity = (
        entities.get(field_verdict.selected_entity_id)
        if field_verdict.selected_entity_id
        else None
    )
    if field_verdict.selected_entity_id and entity is None:
        raise VerificationGroundingError(
            "field verdict selects an unknown inventory entity"
        )
    data = envelope.candidate.get("data")
    data = data if isinstance(data, dict) else {}
    if (
        field_verdict.field == "condition"
        and "test_condition_raw" not in data
    ):
        raise VerificationGroundingError(
            "candidate contract has no mutable test_condition_raw correction slot"
        )
    if field_verdict.field == "specimen" and "test_specimen_raw" not in data:
        raise VerificationGroundingError(
            "candidate contract has no mutable test_specimen_raw correction slot"
        )
    if field_verdict.field == "state" and "material_state" not in data:
        raise VerificationGroundingError(
            "candidate contract has no mutable material_state correction slot"
        )
    selected = str(field_verdict.selected_text or "").strip()
    if entity is not None:
        expected = {
            "owner": entity.sample_id_raw,
            "state": entity.state_raw,
            "origin": entity.data_nature,
            "role": entity.role,
        }.get(field_verdict.field)
        if selected and expected and _fold(selected) != _fold(expected):
            raise VerificationGroundingError(
                "field correction conflicts with the selected inventory entity"
            )
        if not selected and expected:
            selected = str(expected)
    entity_cited = bool(
        entity is not None
        and set(entity.evidence_ids) & set(field_verdict.evidence_ids)
    )
    if selected and not _literal_in_evidence(selected, cited_text) and not entity_cited:
        raise VerificationGroundingError(
            "field correction target is not literal or inventory-grounded"
        )


def validate_field_response(
    bundle: VerificationBundle,
    response: FieldVerificationResponse,
) -> dict[str, FieldVerificationDecision]:
    """Validate protocol-v2 field coverage and source authority atomically."""

    if response.protocol_version != FIELD_VERIFICATION_PROTOCOL_VERSION:
        raise VerificationGroundingError("field response protocol version is invalid")
    if response.bundle_id != bundle.bundle_id:
        raise VerificationGroundingError("field response bundle_id does not match request")
    assertions = {row.assertion_id: row for row in bundle.assertions}
    decisions = {row.assertion_id: row for row in response.decisions}
    if set(decisions) != set(assertions):
        missing = sorted(set(assertions) - set(decisions))
        extra = sorted(set(decisions) - set(assertions))
        raise VerificationGroundingError(
            f"field response must decide every assertion; missing={missing}, extra={extra}"
        )
    evidence_by_id = {row.evidence_id: row for row in bundle.evidence}
    known_evidence = set(evidence_by_id)
    for assertion_id, decision in decisions.items():
        envelope = assertions[assertion_id]
        expected = set(required_scientific_fields(envelope))
        actual = {row.field for row in decision.fields}
        if actual != expected:
            raise VerificationGroundingError(
                "field coverage must equal asserted scientific fields; "
                f"assertion={assertion_id}, missing={sorted(expected - actual)}, "
                f"extra={sorted(actual - expected)}"
            )
        for row in decision.fields:
            unknown = sorted(set(row.evidence_ids) - known_evidence)
            if unknown:
                raise VerificationGroundingError(
                    "field verdict cites unknown evidence IDs: " + ", ".join(unknown)
                )
            cited_text = _field_cited_text(row, evidence_by_id)
            _validate_field_target(
                row,
                envelope=envelope,
                bundle=bundle,
                cited_text=cited_text,
            )
            if row.verdict == "supported":
                _validate_supported_field(
                    envelope,
                    row.field,
                    cited_text,
                    bundle,
                    set(row.evidence_ids),
                )
    return decisions


def validate_compact_review_response(
    bundle: VerificationBundle,
    response: CompactReviewResponse,
) -> dict[str, CompactReviewDecision]:
    """Validate a compact all-fields review against immutable source authority."""

    if response.protocol_version != COMPACT_REVIEW_PROTOCOL_VERSION:
        raise VerificationGroundingError(
            "compact review protocol version is invalid"
        )
    if response.bundle_id != bundle.bundle_id:
        raise VerificationGroundingError(
            "compact review bundle_id does not match request"
        )
    assertions = {row.assertion_id: row for row in bundle.assertions}
    decisions = {row.assertion_id: row for row in response.decisions}
    if set(decisions) != set(assertions):
        missing = sorted(set(assertions) - set(decisions))
        extra = sorted(set(decisions) - set(assertions))
        raise VerificationGroundingError(
            "compact review must decide every assertion; "
            f"missing={missing}, extra={extra}"
        )
    evidence_by_id = {row.evidence_id: row for row in bundle.evidence}
    known_evidence = set(evidence_by_id)
    for assertion_id, decision in decisions.items():
        envelope = assertions[assertion_id]
        unknown = sorted(set(decision.evidence_ids) - known_evidence)
        if unknown:
            raise VerificationGroundingError(
                "compact review cites unknown evidence IDs: "
                + ", ".join(unknown)
            )
        required = set(required_scientific_fields(envelope))
        failed = set(decision.failed_fields)
        if not failed <= required:
            raise VerificationGroundingError(
                "compact review failed_fields exceed asserted scientific fields; "
                f"assertion={assertion_id}, extra={sorted(failed - required)}"
            )
        if decision.verdict != "all_fields_supported":
            continue
        cited_text = _source_text_for(decision.evidence_ids, evidence_by_id)
        for field in required_scientific_fields(envelope):
            _validate_supported_field(
                envelope,
                field,
                cited_text,
                bundle,
                set(decision.evidence_ids),
            )
    return decisions


def _field_action(
    decision: FieldVerificationDecision,
) -> tuple[str, ReassignmentPatch | None, tuple[str, ...]]:
    fields = {row.field: row for row in decision.fields}
    if all(row.verdict == "supported" for row in fields.values()):
        evidence_ids = tuple(
            sorted({evidence_id for row in fields.values() for evidence_id in row.evidence_ids})
        )
        return "support", None, evidence_ids
    correction_rows = [
        row
        for row in fields.values()
        if row.verdict == "contradicted"
        and (row.selected_entity_id is not None or row.selected_text is not None)
    ]
    if correction_rows and all(
        row.verdict == "supported" or row in correction_rows
        for row in fields.values()
    ):
        payload: dict[str, Any] = {}
        for row in correction_rows:
            if row.field == "owner":
                payload["entity_id"] = row.selected_entity_id
                payload["sample_id_raw"] = row.selected_text
            elif row.field == "state":
                payload.setdefault("entity_id", row.selected_entity_id)
                payload["state_raw"] = row.selected_text
            elif row.field == "condition":
                payload["test_condition_raw"] = row.selected_text
            elif row.field == "specimen":
                payload["test_specimen_raw"] = row.selected_text
            else:
                return "reject", None, ()
        evidence_ids = tuple(
            sorted({evidence_id for row in fields.values() for evidence_id in row.evidence_ids})
        )
        return "reassign", ReassignmentPatch(**payload), evidence_ids
    return "reject", None, tuple(
        sorted({evidence_id for row in fields.values() for evidence_id in row.evidence_ids})
    )


def _field_decision_payload(
    decision: FieldVerificationDecision | None,
    error: str | None,
) -> dict[str, Any]:
    if decision is not None:
        return decision.model_dump(mode="json")
    return {
        "decision": "technical_failure",
        "error": str(error or "missing field response"),
    }


def _compact_decision_payload(
    decision: CompactReviewDecision | None,
    error: str | None,
    *,
    skipped: bool,
) -> dict[str, Any]:
    if decision is not None:
        return decision.model_dump(mode="json")
    if skipped:
        return {
            "decision": "skipped",
            "reason_code": "SECONDARY_SKIPPED_PRIMARY_NONPOSITIVE",
        }
    return {
        "decision": "technical_failure",
        "error": str(error or "missing compact review response"),
    }


def _label_decision_payload(
    label: CompactLabel | None,
    error: str | None,
    *,
    skipped: bool,
) -> dict[str, Any]:
    if label is not None:
        return {
            "decision": "support" if label == "S" else "reject",
            "label": label,
            "reason_code": {
                "S": "ALL_FIELDS_SUPPORTED",
                "C": "FIELD_CONTRADICTED",
                "N": "FIELD_NOT_PROVEN",
            }[label],
        }
    if skipped:
        return {
            "decision": "skipped",
            "reason_code": "SECONDARY_SKIPPED_PRIMARY_NONPOSITIVE",
        }
    return {
        "decision": "technical_failure",
        "error": str(error or "missing label review response"),
    }


def _reassignment_issue_code(patch: ReassignmentPatch) -> str:
    changed = []
    if patch.sample_id_raw is not None:
        changed.append("owner")
    if patch.state_raw is not None:
        changed.append("state")
    if patch.test_condition_raw is not None:
        changed.append("condition")
    if patch.test_specimen_raw is not None:
        changed.append("specimen")
    return (
        f"verifier_{changed[0]}_reassigned"
        if len(changed) == 1
        else "verifier_field_reassigned"
    )


def apply_field_consensus(
    bundle: VerificationBundle,
    inventory: VerificationInventory,
    *,
    primary_response: FieldVerificationResponse | None,
    secondary_response: FieldVerificationResponse | None,
    primary_error: str | None = None,
    secondary_error: str | None = None,
    primary_cache_hit: bool = False,
    secondary_cache_hit: bool = False,
    primary_decisions: dict[str, FieldVerificationDecision] | None = None,
    secondary_decisions: dict[str, FieldVerificationDecision] | None = None,
    primary_errors: dict[str, str] | None = None,
    secondary_errors: dict[str, str] | None = None,
    secondary_compact_response: CompactReviewResponse | None = None,
    secondary_compact_decisions: dict[str, CompactReviewDecision] | None = None,
    secondary_compact_error: str | None = None,
    secondary_compact_errors: dict[str, str] | None = None,
    secondary_compact_cache_hit: bool = False,
    secondary_label_decisions: dict[str, CompactLabel] | None = None,
    secondary_label_errors: dict[str, str] | None = None,
    secondary_label_cache_hits: set[str] | None = None,
    secondary_label_mode: bool = False,
    secondary_skipped_assertion_ids: set[str] | None = None,
) -> AppliedVerification:
    """Apply severity-aware independent field review without new science."""

    primary = (
        dict(primary_decisions)
        if primary_decisions is not None
        else validate_field_response(bundle, primary_response)
        if primary_response is not None
        else {}
    )
    secondary = (
        dict(secondary_decisions)
        if secondary_decisions is not None
        else validate_field_response(bundle, secondary_response)
        if secondary_response is not None
        else {}
    )
    if secondary and (
        secondary_compact_response is not None
        or secondary_compact_decisions
        or secondary_label_decisions
    ):
        raise VerificationGroundingError(
            "field and compact secondary responses cannot be combined"
        )
    compact_secondary = (
        dict(secondary_compact_decisions)
        if secondary_compact_decisions is not None
        else validate_compact_review_response(bundle, secondary_compact_response)
        if secondary_compact_response is not None
        else {}
    )
    primary_errors = dict(primary_errors or {})
    secondary_errors = dict(secondary_errors or {})
    secondary_compact_errors = dict(secondary_compact_errors or {})
    secondary_label_decisions = dict(secondary_label_decisions or {})
    secondary_label_errors = dict(secondary_label_errors or {})
    secondary_label_cache_hits = set(secondary_label_cache_hits or set())
    secondary_skipped_assertion_ids = set(
        secondary_skipped_assertion_ids or set()
    )
    label_mode = bool(
        secondary_label_mode
        or secondary_label_decisions
        or secondary_label_errors
    )
    compact_object_mode = bool(
        secondary_compact_response is not None
        or secondary_compact_decisions is not None
        or secondary_compact_error is not None
        or secondary_compact_errors
        or (secondary_skipped_assertion_ids and not label_mode)
    )
    compact_mode = bool(
        compact_object_mode
        or label_mode
        or secondary_skipped_assertion_ids
    )
    evidence_by_id = {row.evidence_id: row for row in bundle.evidence}
    accepted_by_id: dict[str, AxisFact] = {}
    audits: list[dict[str, Any]] = []
    issues: list[dict[str, Any]] = []

    for envelope in sorted(bundle.assertions, key=lambda row: row.assertion_id):
        assertion_id = envelope.assertion_id
        fact = inventory.facts_by_assertion_id[assertion_id]
        first = primary.get(assertion_id)
        second = secondary.get(assertion_id)
        compact_second = compact_secondary.get(assertion_id)
        label_second = secondary_label_decisions.get(assertion_id)
        first_action, first_patch, first_evidence = (
            _field_action(first) if first is not None else ("failure", None, ())
        )
        second_action, second_patch, second_evidence = (
            _field_action(second) if second is not None else ("failure", None, ())
        )
        if compact_second is not None:
            second_action = (
                "support"
                if compact_second.verdict == "all_fields_supported"
                else "reject"
            )
            second_patch = None
            second_evidence = tuple(compact_second.evidence_ids)
        elif label_second is not None:
            second_action = "support" if label_second == "S" else "reject"
            second_patch = None
            # The label protocol has no evidence-citation authority. Primary
            # field grounding remains the sole source for formal citations.
            second_evidence = ()
        elif assertion_id in secondary_skipped_assertion_ids:
            second_action, second_patch, second_evidence = ("skipped", None, ())
        hard = envelope.risk_severity == "hard"
        final_action = "preserve"
        issue_code: str | None = None
        reason_code = "FIELD_VERIFICATION_SUPPORTED"
        patch: ReassignmentPatch | None = None
        cited_ids = tuple(sorted(set(first_evidence) | set(second_evidence)))

        if hard:
            if first_action == second_action == "support":
                final_action = "accept"
            elif not compact_mode and (
                first_action == second_action == "reassign"
                and first_patch is not None
                and second_patch is not None
                and canonical_json(first_patch.model_dump(mode="json"))
                == canonical_json(second_patch.model_dump(mode="json"))
            ):
                final_action = "reassign"
                patch = first_patch
                issue_code = _reassignment_issue_code(first_patch)
                reason_code = "FIELD_REASSIGNMENT_CONSENSUS"
            else:
                final_action = "isolate"
                compact_missing = (
                    compact_mode
                    and compact_second is None
                    and label_second is None
                    and assertion_id not in secondary_skipped_assertion_ids
                )
                if first is None or (not compact_mode and second is None) or compact_missing:
                    label_error = secondary_label_errors.get(assertion_id, "")
                    if "invalid_label_cardinality" in label_error:
                        issue_code = "verifier_label_cardinality_failure"
                    elif any(
                        code in label_error
                        for code in ("responses_incomplete", "output_truncated")
                    ):
                        issue_code = "verifier_label_incomplete"
                    elif label_error:
                        issue_code = "verifier_label_transport_failure"
                    else:
                        issue_code = "verifier_technical_failure_isolated"
                    reason_code = "HARD_RISK_TECHNICAL_FAILURE"
                else:
                    issue_code = (
                        "verifier_label_contradicted_isolated"
                        if label_second == "C"
                        else "verifier_label_not_proven_isolated"
                        if label_second == "N"
                        else "verifier_hard_risk_isolated"
                    )
                    reason_code = "HARD_RISK_NOT_POSITIVELY_CONFIRMED"
        else:
            if first_action == "support":
                final_action = "accept"
            elif first is None and second_action == "support":
                final_action = "preserve"
                issue_code = "verifier_soft_risk_preserved"
                reason_code = "SOFT_RISK_PRIMARY_FAILURE"
            elif (
                first_action == second_action == "reassign"
                and first_patch is not None
                and second_patch is not None
                and canonical_json(first_patch.model_dump(mode="json"))
                == canonical_json(second_patch.model_dump(mode="json"))
            ):
                final_action = "reassign"
                patch = first_patch
                issue_code = _reassignment_issue_code(first_patch)
                reason_code = "FIELD_REASSIGNMENT_CONSENSUS"
            elif first_action == second_action == "reject":
                final_action = "isolate"
                issue_code = "verifier_field_consensus_isolated"
                reason_code = "FIELD_REJECTION_CONSENSUS"
            else:
                final_action = "preserve"
                issue_code = "verifier_soft_risk_preserved"
                reason_code = "SOFT_RISK_DECISION_NOT_CONFIRMED"

        after: AxisFact | None = None
        if final_action in {"accept", "preserve"}:
            after = fact
            accepted_by_id[assertion_id] = fact
        elif final_action == "reassign" and patch is not None:
            synthetic = VerificationDecision(
                assertion_id=assertion_id,
                decision="reassign",
                evidence_ids=list(cited_ids),
                reason_code=reason_code,
                rationale="Both field-review roles selected the same grounded coordinates.",
                reassignment=patch,
            )
            after = _apply_reassignment(envelope, synthetic, bundle, fact)
            accepted_by_id[assertion_id] = after

        audit_evidence_ids = cited_ids or tuple(envelope.evidence_ids)
        audit = {
            "assertion_id": assertion_id,
            "bundle_id": bundle.bundle_id,
            "protocol_version": FIELD_VERIFICATION_PROTOCOL_VERSION,
            "decision": (
                "reassign"
                if final_action == "reassign"
                else "accept"
                if final_action in {"accept", "preserve"}
                else "quarantine"
            ),
            "reason_code": reason_code,
            "before": envelope.candidate,
            "after": after.model_dump(mode="json") if after is not None else None,
            "evidence": [
                evidence_by_id[evidence_id].model_dump(mode="json")
                for evidence_id in audit_evidence_ids
                if evidence_id in evidence_by_id
            ],
            "verifier_role": "deterministic",
            "fallback_used": (
                secondary_response is not None
                or bool(secondary_decisions)
                or compact_second is not None
                or label_second is not None
                or assertion_id in secondary_compact_errors
                or assertion_id in secondary_label_errors
                or secondary_compact_error is not None
            ),
            "cache_hit": primary_cache_hit and (
                (not compact_mode and (secondary_response is None or secondary_cache_hit))
                or (
                    compact_mode
                    and (
                        assertion_id in secondary_skipped_assertion_ids
                        or secondary_compact_cache_hit
                        or assertion_id in secondary_label_cache_hits
                    )
                )
            ),
            "rationale": "Severity-aware field-level consensus was applied deterministically.",
            "risk_severity": envelope.risk_severity,
            "risk_codes": list(envelope.risk_codes),
            "primary_field_review": _field_decision_payload(first, primary_error),
            "secondary_field_review": _field_decision_payload(
                second,
                secondary_errors.get(assertion_id, secondary_error),
            ),
            "secondary_compact_review": _compact_decision_payload(
                compact_second,
                secondary_compact_errors.get(
                    assertion_id, secondary_compact_error
                ),
                skipped=assertion_id in secondary_skipped_assertion_ids,
            ) if compact_object_mode else None,
            "secondary_label_review": _label_decision_payload(
                label_second,
                secondary_label_errors.get(assertion_id),
                skipped=assertion_id in secondary_skipped_assertion_ids,
            ) if hard and label_mode else None,
            "formal_action": final_action,
        }
        if first is None:
            audit["primary_field_review"] = _field_decision_payload(
                first,
                primary_errors.get(assertion_id, primary_error),
            )
        audits.append(audit)
        if issue_code is not None:
            severity = "review" if final_action in {"isolate", "preserve"} else "info"
            issues.append(
                {
                    "code": issue_code,
                    "severity": severity,
                    "path": f"items.{envelope.sample_id_raw}.{envelope.axis}",
                    "message": reason_code,
                    "evidence": list(audit_evidence_ids),
                    "expected": {
                        "assertion_id": assertion_id,
                        "field_grounded": True,
                    },
                    "actual": {
                        "assertion_id": assertion_id,
                        "bundle_id": bundle.bundle_id,
                        "formal_action": final_action,
                        "risk_severity": envelope.risk_severity,
                    },
                    "suggested_action": (
                        "Review the complete linked field decisions in quality_audit.json."
                    ),
                }
            )

    ordered_ids = tuple(sorted(row.assertion_id for row in bundle.assertions))
    accepted_ids = tuple(
        assertion_id for assertion_id in ordered_ids if assertion_id in accepted_by_id
    )
    return AppliedVerification(
        accepted=tuple(accepted_by_id[row] for row in accepted_ids),
        audit_records=tuple(audits),
        issues=tuple(issues),
        decided_assertion_ids=ordered_ids,
        accepted_assertion_ids=accepted_ids,
    )


def validate_and_apply_bundle(
    bundle: VerificationBundle,
    response: VerificationResponse,
    inventory: VerificationInventory,
    *,
    verifier_role: Literal["primary", "fallback"] = "primary",
    fallback_used: bool = False,
    cache_hit: bool = False,
) -> AppliedVerification:
    """Validate a complete response, then atomically apply its decisions."""

    if response.bundle_id != bundle.bundle_id:
        raise VerificationGroundingError("response bundle_id does not match request")
    if response.protocol_version != bundle.protocol_version:
        raise VerificationGroundingError("response protocol version does not match request")
    assertions = {row.assertion_id: row for row in bundle.assertions}
    decisions = {row.assertion_id: row for row in response.decisions}
    if set(decisions) != set(assertions):
        missing = sorted(set(assertions) - set(decisions))
        extra = sorted(set(decisions) - set(assertions))
        raise VerificationGroundingError(
            f"response must decide every bundle assertion exactly once; missing={missing}, extra={extra}"
        )
    evidence_ids = {row.evidence_id for row in bundle.evidence}
    entities = {row.entity_id: row for row in bundle.entities}
    normalized_decisions: dict[str, VerificationDecision] = {}
    for decision in response.decisions:
        unknown = sorted(set(decision.evidence_ids) - evidence_ids)
        if unknown:
            raise VerificationGroundingError(
                "decision cites unknown evidence IDs: " + ", ".join(unknown)
            )
        # A verifier often cites the one decisive span while an Alpha25
        # candidate carries two or more literal provenance quotes.  When the
        # cited set already intersects the candidate's deterministic evidence,
        # complete that citation set from the request envelope.  This grants no
        # new source authority and still rejects a decision that cites only an
        # unrelated bundle span.
        envelope = assertions[decision.assertion_id]
        linked_ids = list(envelope.evidence_ids)
        if decision.decision == "reassign" and decision.reassignment is not None:
            entity = entities.get(decision.reassignment.entity_id or "")
            if entity is not None:
                linked_ids.extend(entity.evidence_ids)
        if set(decision.evidence_ids) & set(linked_ids):
            completed_ids = list(
                dict.fromkeys([*decision.evidence_ids, *linked_ids])
            )
            decision = decision.model_copy(update={"evidence_ids": completed_ids})
        normalized_decisions[decision.assertion_id] = decision

    decisions = normalized_decisions
    for decision in decisions.values():
        if decision.decision in {"accept", "merge"}:
            _validate_candidate_grounding(
                assertions[decision.assertion_id], decision, bundle
            )
        elif decision.decision == "reassign":
            _validate_candidate_grounding(
                assertions[decision.assertion_id],
                decision,
                bundle,
                allow_owner_change=True,
                allow_condition_change=True,
            )

    merge_groups: dict[tuple[tuple[str, ...], str], list[VerificationDecision]] = {}
    for decision in response.decisions:
        if decision.decision != "merge":
            continue
        members = tuple(sorted(decision.merge_member_ids))
        if not set(members) <= set(assertions):
            raise VerificationGroundingError("merge cites an assertion outside the bundle")
        key = (members, str(decision.survivor_assertion_id))
        merge_groups.setdefault(key, []).append(decision)
    for (members, _survivor), rows in merge_groups.items():
        if {row.assertion_id for row in rows} != set(members):
            raise VerificationGroundingError(
                "every merge member must emit the same complete merge decision"
            )
        member_rows = [assertions[assertion_id] for assertion_id in members]
        if not _merge_compatible(member_rows):
            raise VerificationGroundingError(
                "merge members are not deterministically compatible"
            )

    accepted_by_id: dict[str, AxisFact] = {}
    for assertion_id, envelope in assertions.items():
        decision = decisions[assertion_id]
        fact = inventory.facts_by_assertion_id[assertion_id]
        if decision.decision == "accept":
            accepted_by_id[assertion_id] = fact
        elif decision.decision == "reassign":
            accepted_by_id[assertion_id] = _apply_reassignment(
                envelope, decision, bundle, fact
            )

    for (members, survivor_id), _rows in merge_groups.items():
        member_facts = [inventory.facts_by_assertion_id[row] for row in members]
        accepted_by_id[survivor_id] = _union_fact_provenance(
            member_facts,
            inventory.facts_by_assertion_id[survivor_id],
        )

    audit_records: list[dict[str, Any]] = []
    issues: list[dict[str, Any]] = []
    for envelope in sorted(bundle.assertions, key=lambda row: row.assertion_id):
        decision = decisions[envelope.assertion_id]
        after = accepted_by_id.get(envelope.assertion_id)
        audit = _audit_record(
            envelope=envelope,
            decision=decision,
            bundle=bundle,
            after=after,
            verifier_role=verifier_role,
            fallback_used=fallback_used,
            cache_hit=cache_hit,
        )
        audit_records.append(audit)
        issue = _issue_record(envelope, decision, audit)
        if issue is not None:
            issues.append(issue)

    accepted_rows = [
        (row.assertion_id, accepted_by_id[row.assertion_id])
        for row in sorted(bundle.assertions, key=lambda item: item.assertion_id)
        if row.assertion_id in accepted_by_id
    ]
    return AppliedVerification(
        accepted=tuple(row[1] for row in accepted_rows),
        audit_records=tuple(audit_records),
        issues=tuple(issues),
        decided_assertion_ids=tuple(sorted(assertions)),
        accepted_assertion_ids=tuple(row[0] for row in accepted_rows),
    )


def unresolved_bundle_result(
    bundle: VerificationBundle,
    inventory: VerificationInventory,
    *,
    reason_code: str,
    rationale: str,
    fallback_used: bool,
) -> AppliedVerification:
    """Build explicit unresolved records after both configured verifiers fail."""

    response = VerificationResponse(
        bundle_id=bundle.bundle_id,
        decisions=[
            VerificationDecision(
                assertion_id=row.assertion_id,
                decision="unresolved",
                reason_code=reason_code,
                rationale=rationale,
            )
            for row in bundle.assertions
        ],
    )
    return validate_and_apply_bundle(
        bundle,
        response,
        inventory,
        verifier_role="fallback",
        fallback_used=fallback_used,
    )


def preserve_failed_bundle_result(
    bundle: VerificationBundle,
    inventory: VerificationInventory,
    *,
    reason_code: str,
    rationale: str,
    fallback_used: bool,
) -> AppliedVerification:
    """Fail open only for verifier-role failures, with a complete review audit.

    This is deliberately separate from an explicit model ``unresolved``
    decision, which remains excluded from formal output.  A transport,
    truncation, contract, or applicator failure is not scientific evidence
    against the candidate and therefore must not silently turn into deletion.
    """

    accepted: list[AxisFact] = []
    audits: list[dict[str, Any]] = []
    issues: list[dict[str, Any]] = []
    evidence_by_id = {row.evidence_id: row for row in bundle.evidence}
    for envelope in sorted(bundle.assertions, key=lambda row: row.assertion_id):
        fact = inventory.facts_by_assertion_id[envelope.assertion_id]
        accepted.append(fact)
        audit = VerificationAuditRecord(
            assertion_id=envelope.assertion_id,
            bundle_id=bundle.bundle_id,
            decision="unresolved",
            reason_code=reason_code,
            before=envelope.candidate,
            after=fact.model_dump(mode="json"),
            evidence=[
                evidence_by_id[evidence_id]
                for evidence_id in envelope.evidence_ids
                if evidence_id in evidence_by_id
            ],
            verifier_role="deterministic",
            fallback_used=fallback_used,
            cache_hit=False,
            rationale=rationale,
        ).model_dump(mode="json", exclude_none=True)
        audits.append(audit)
        issues.append(
            {
                "code": "verifier_unresolved_preserved",
                "severity": "review",
                "path": f"items.{envelope.sample_id_raw}.{envelope.axis}",
                "message": reason_code,
                "evidence": list(envelope.evidence_ids),
                "expected": {
                    "assertion_id": envelope.assertion_id,
                    "verified_decision": True,
                },
                "actual": {
                    "assertion_id": envelope.assertion_id,
                    "bundle_id": bundle.bundle_id,
                    "decision": "unresolved",
                    "formal_output": "preserved_pending_review",
                    "reason_code": reason_code,
                },
                "suggested_action": (
                    "Review the complete linked record in quality_audit.json."
                ),
            }
        )
    assertion_ids = tuple(row.assertion_id for row in sorted(
        bundle.assertions, key=lambda row: row.assertion_id
    ))
    return AppliedVerification(
        accepted=tuple(accepted),
        audit_records=tuple(audits),
        issues=tuple(issues),
        decided_assertion_ids=assertion_ids,
        accepted_assertion_ids=assertion_ids,
    )


def validate_recovery_response(
    request: RecoveryRequest,
    response: RecoveryResponse,
) -> tuple[AxisFact, ...]:
    """Ground recovery proposals without allowing estimated or invented facts."""

    evidence_by_id = {row.evidence_id: row for row in request.evidence}
    entities = {row.entity_id: row for row in request.entities}
    proposal_ids = [row.proposal_id for row in response.proposals]
    if len(set(proposal_ids)) != len(proposal_ids):
        raise VerificationGroundingError("recovery proposal IDs must be unique")
    facts: list[AxisFact] = []
    for proposal in response.proposals:
        unknown = sorted(set(proposal.evidence_ids) - set(evidence_by_id))
        if unknown:
            raise VerificationGroundingError(
                "recovery proposal cites unknown evidence IDs: " + ", ".join(unknown)
            )
        try:
            fact = _AXIS_FACT_ADAPTER.validate_python(proposal.candidate)
        except ValidationError as exc:
            raise VerificationGroundingError(
                f"recovery candidate violates AxisFact contract: {exc}"
            ) from exc
        if fact.axis != proposal.axis or fact.axis == "composition":
            raise VerificationGroundingError("recovery proposal axis is invalid")
        cited_text = _source_text_for(proposal.evidence_ids, evidence_by_id)
        entity_owner = any(
            _fold(entity.sample_id_raw) == _fold(fact.sample_id_raw)
            for entity in entities.values()
        )
        if not entity_owner and not _literal_in_evidence(fact.sample_id_raw, cited_text):
            raise VerificationGroundingError(
                "recovery owner is neither literal nor a supplied inventory entity"
            )
        for quote in getattr(fact, "source_evidence", []) or []:
            if not _literal_in_evidence(quote, cited_text):
                raise VerificationGroundingError(
                    "recovery candidate source_evidence is not literal in cited evidence"
                )
        data = fact.data if isinstance(fact.data, dict) else {}
        nested_evidence = data.get("source_evidence") or []
        if isinstance(nested_evidence, str):
            nested_evidence = [nested_evidence]
        for quote in nested_evidence:
            if not _literal_in_evidence(str(quote), cited_text):
                raise VerificationGroundingError(
                    "recovery nested source_evidence is not literal in cited evidence"
                )
        if fact.axis == "properties":
            value = str(data.get("value_raw") or "").strip()
            unit = str(data.get("unit_raw") or "").strip()
            if not _literal_in_evidence(value, cited_text):
                raise VerificationGroundingError(
                    "recovery property value is not literal in cited evidence"
                )
            if unit and not _literal_in_evidence(unit, cited_text):
                raise VerificationGroundingError(
                    "recovery property unit is not literal in cited evidence"
                )
        facts.append(fact)
    return tuple(facts)


__all__ = [
    "AppliedVerification",
    "VerificationGroundingError",
    "apply_field_consensus",
    "unresolved_bundle_result",
    "preserve_failed_bundle_result",
    "required_scientific_fields",
    "validate_recovery_response",
    "validate_and_apply_bundle",
    "validate_compact_review_response",
    "validate_field_response",
]
