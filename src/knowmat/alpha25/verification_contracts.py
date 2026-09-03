"""Strict contracts for paper-level Alpha25 candidate verification.

The contracts intentionally contain no provider, model, paper, or evaluation
identity. Those belong to runtime manifests, not scientific decision logic.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator, model_validator


VERIFICATION_PROTOCOL_VERSION = "alpha25_hierarchical_verification_v1"
FIELD_VERIFICATION_PROTOCOL_VERSION = "alpha25_field_verification_v2"
COMPACT_REVIEW_PROTOCOL_VERSION = "alpha25_compact_independent_review_v1"
COMPACT_LABEL_REVIEW_PROTOCOL_VERSION = "alpha25_compact_label_review_v2"
VerificationAxis = Literal["processing", "structure", "properties"]
RiskSeverity = Literal["none", "soft", "hard"]
DecisionName = Literal[
    "accept", "merge", "reassign", "quarantine", "unresolved"
]
ScientificFieldName = Literal[
    "semantic",
    "value",
    "unit",
    "owner",
    "state",
    "condition",
    "specimen",
    "origin",
    "role",
]
ScientificFieldVerdictName = Literal[
    "supported", "contradicted", "not_proven"
]
CompactReviewVerdictName = Literal[
    "all_fields_supported", "contradicted", "not_proven"
]
CompactLabel = Literal["S", "C", "N"]
_SCIENTIFIC_FIELD_ORDER = {
    name: position
    for position, name in enumerate(
        (
            "semantic",
            "value",
            "unit",
            "owner",
            "state",
            "condition",
            "specimen",
            "origin",
            "role",
        )
    )
}


def canonical_json(value: Any) -> str:
    """Serialize a JSON-compatible value for stable identities and caches."""

    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def stable_id(prefix: str, value: Any, *, length: int = 24) -> str:
    """Return a readable content identity without runtime or paper metadata."""

    digest = hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()
    return f"{prefix}_{digest[:length]}"


def parse_compact_label_array(
    raw: str, *, label_count: int
) -> tuple[CompactLabel, ...]:
    """Parse one exact-cardinality independent-review label array.

    The protocol deliberately accepts no envelope, IDs, prose, or scientific
    content from the provider. Request order is the only mapping authority.
    """

    if label_count < 1:
        raise ValueError("label cardinality must be positive")
    try:
        value = json.loads(str(raw or ""))
    except json.JSONDecodeError as exc:
        raise ValueError("compact labels must be valid JSON") from exc
    if not isinstance(value, list):
        raise ValueError("compact labels must be one JSON array")
    if len(value) != label_count:
        raise ValueError(
            "compact label cardinality does not match request assertions"
        )
    if any(label not in {"S", "C", "N"} for label in value):
        raise ValueError("compact labels contain values outside allowed labels")
    return tuple(value)  # type: ignore[return-value]


class EvidenceSpan(BaseModel):
    """One literal, bounded span from the supplied paper source."""

    evidence_id: str = Field(min_length=3)
    unit_id: str | None = None
    kind: Literal["assertion", "anchor", "context", "recovery"]
    text: str = Field(min_length=1)
    start_char: int = Field(ge=0)
    end_char: int = Field(gt=0)

    @model_validator(mode="after")
    def validate_bounds(self) -> "EvidenceSpan":
        if self.end_char <= self.start_char:
            raise ValueError("evidence end_char must be greater than start_char")
        if self.end_char - self.start_char != len(self.text):
            raise ValueError("evidence bounds must equal the literal text length")
        return self

    model_config = {"extra": "forbid", "frozen": True}


class InventoryEntity(BaseModel):
    """A source-supported material/specimen identity available for reassignment."""

    entity_id: str = Field(min_length=3)
    sample_id_raw: str = Field(min_length=1)
    material_name_raw: str | None = None
    state_raw: str | None = None
    role: Literal["Target", "Reference"]
    data_nature: Literal[
        "Experimental", "Computed", "Literature_Experimental", "Literature_Computed"
    ]
    evidence_ids: list[str] = Field(min_length=1)

    @field_validator("evidence_ids")
    @classmethod
    def unique_evidence(cls, value: list[str]) -> list[str]:
        return list(dict.fromkeys(value))

    model_config = {"extra": "forbid", "frozen": True}


class AssertionEnvelope(BaseModel):
    """Immutable candidate plus independently reviewable ownership fields."""

    assertion_id: str = Field(min_length=3)
    axis: VerificationAxis
    fact_type: str = Field(min_length=1)
    sample_id_raw: str = Field(min_length=1)
    task_id: str | None = None
    evidence_unit_id: str | None = None
    evidence_ids: list[str] = Field(default_factory=list)
    risk_severity: RiskSeverity = "none"
    risk_codes: list[str] = Field(default_factory=list)
    candidate: dict[str, Any]

    @field_validator("evidence_ids", "risk_codes")
    @classmethod
    def unique_evidence(cls, value: list[str]) -> list[str]:
        return sorted(set(value))

    model_config = {"extra": "forbid", "frozen": True}


class VerificationBundle(BaseModel):
    """Bounded verifier input for one compatible paper-level assertion group."""

    protocol_version: str = VERIFICATION_PROTOCOL_VERSION
    bundle_id: str = Field(min_length=3)
    axis: VerificationAxis
    assertions: list[AssertionEnvelope] = Field(min_length=1, max_length=12)
    entities: list[InventoryEntity] = Field(default_factory=list)
    evidence: list[EvidenceSpan] = Field(min_length=1)
    source_char_count: int = Field(ge=1, le=12000)

    @model_validator(mode="after")
    def validate_references_and_axis(self) -> "VerificationBundle":
        evidence_ids = {row.evidence_id for row in self.evidence}
        if len(evidence_ids) != len(self.evidence):
            raise ValueError("bundle evidence IDs must be unique")
        assertion_ids = {row.assertion_id for row in self.assertions}
        if len(assertion_ids) != len(self.assertions):
            raise ValueError("bundle assertion IDs must be unique")
        if any(row.axis != self.axis for row in self.assertions):
            raise ValueError("all bundle assertions must use the bundle axis")
        referenced = {
            evidence_id
            for row in [*self.assertions, *self.entities]
            for evidence_id in row.evidence_ids
        }
        missing = sorted(referenced - evidence_ids)
        if missing:
            raise ValueError("bundle references unknown evidence IDs: " + ", ".join(missing))
        actual_chars = sum(len(row.text) for row in self.evidence)
        if actual_chars != self.source_char_count:
            raise ValueError("source_char_count must equal bundled evidence text length")
        return self

    model_config = {"extra": "forbid", "frozen": True}


class ReassignmentPatch(BaseModel):
    """Only ownership coordinates may change during verification."""

    entity_id: str | None = None
    sample_id_raw: str | None = None
    state_raw: str | None = None
    test_condition_raw: str | None = None
    test_specimen_raw: str | None = None

    @model_validator(mode="after")
    def require_change(self) -> "ReassignmentPatch":
        if not any(
            value is not None
            for value in (
                self.entity_id,
                self.sample_id_raw,
                self.state_raw,
                self.test_condition_raw,
                self.test_specimen_raw,
            )
        ):
            raise ValueError("reassignment must contain at least one ownership field")
        return self

    model_config = {"extra": "forbid", "frozen": True}


class VerificationDecision(BaseModel):
    """One model judgment whose mutation surface is deliberately narrow."""

    assertion_id: str = Field(min_length=3)
    decision: DecisionName
    evidence_ids: list[str] = Field(default_factory=list)
    reason_code: str = Field(pattern=r"^[A-Z][A-Z0-9_]{2,63}$")
    rationale: str = Field(min_length=1, max_length=1200)
    merge_member_ids: list[str] = Field(default_factory=list)
    survivor_assertion_id: str | None = None
    reassignment: ReassignmentPatch | None = None

    @field_validator("evidence_ids", "merge_member_ids")
    @classmethod
    def unique_ids(cls, value: list[str]) -> list[str]:
        return list(dict.fromkeys(value))

    @model_validator(mode="after")
    def decision_shape(self) -> "VerificationDecision":
        if self.decision == "merge":
            if len(self.merge_member_ids) < 2 or not self.survivor_assertion_id:
                raise ValueError("merge requires at least two members and one survivor")
            if self.survivor_assertion_id not in self.merge_member_ids:
                raise ValueError("merge survivor must be a merge member")
            if self.reassignment is not None:
                raise ValueError("merge cannot also reassign")
        elif self.merge_member_ids or self.survivor_assertion_id is not None:
            raise ValueError("merge fields are allowed only for merge decisions")
        if self.decision == "reassign":
            if self.reassignment is None:
                raise ValueError("reassign requires a reassignment patch")
        elif self.reassignment is not None:
            raise ValueError("reassignment is allowed only for reassign decisions")
        if self.decision != "unresolved" and not self.evidence_ids:
            raise ValueError(f"{self.decision} requires cited evidence")
        return self

    model_config = {"extra": "forbid"}


class VerificationResponse(BaseModel):
    """Strict provider response for one verification bundle."""

    protocol_version: str = VERIFICATION_PROTOCOL_VERSION
    bundle_id: str = Field(min_length=3)
    decisions: list[VerificationDecision] = Field(min_length=1)

    @field_validator("decisions")
    @classmethod
    def unique_primary_decisions(
        cls, value: list[VerificationDecision]
    ) -> list[VerificationDecision]:
        primary = [row.assertion_id for row in value]
        if len(set(primary)) != len(primary):
            raise ValueError("each assertion must have one primary decision")
        return value

    model_config = {"extra": "forbid"}


class ScientificFieldVerdict(BaseModel):
    """One grounded judgment for one immutable scientific assertion field."""

    field: ScientificFieldName
    verdict: ScientificFieldVerdictName
    evidence_ids: list[str] = Field(min_length=1)
    selected_entity_id: str | None = None
    selected_text: str | None = None

    @field_validator("evidence_ids")
    @classmethod
    def unique_evidence(cls, value: list[str]) -> list[str]:
        return sorted(set(value))

    @model_validator(mode="after")
    def correction_shape(self) -> "ScientificFieldVerdict":
        has_target = self.selected_entity_id is not None or self.selected_text is not None
        if self.verdict == "supported" and has_target:
            raise ValueError("supported field cannot select a correction target")
        if self.verdict == "not_proven" and has_target:
            raise ValueError(
                "only a contradicted field can select a correction target"
            )
        if has_target and self.field not in {
            "owner",
            "state",
            "condition",
            "specimen",
            "origin",
            "role",
        }:
            raise ValueError(
                "correction target is allowed only for ownership coordinates"
            )
        if self.selected_entity_id is not None and self.field not in {
            "owner",
            "state",
            "origin",
            "role",
        }:
            raise ValueError(
                "inventory entity correction is allowed only for entity fields"
            )
        return self

    model_config = {"extra": "forbid", "frozen": True}


class FieldVerificationDecision(BaseModel):
    """A complete set of field-level judgments for one assertion."""

    assertion_id: str = Field(min_length=3)
    fields: list[ScientificFieldVerdict] = Field(min_length=1)
    reason_code: str = Field(pattern=r"^[A-Z][A-Z0-9_]{2,63}$")
    rationale: str = Field(min_length=1, max_length=1200)

    @field_validator("fields")
    @classmethod
    def unique_fields(
        cls, value: list[ScientificFieldVerdict]
    ) -> list[ScientificFieldVerdict]:
        names = [row.field for row in value]
        if len(names) != len(set(names)):
            raise ValueError("each assertion requires one verdict per scientific field")
        return sorted(value, key=lambda row: _SCIENTIFIC_FIELD_ORDER[row.field])

    model_config = {"extra": "forbid"}


class FieldVerificationResponse(BaseModel):
    """Strict protocol-v2 provider response for one bounded bundle."""

    protocol_version: Literal["alpha25_field_verification_v2"] = (
        FIELD_VERIFICATION_PROTOCOL_VERSION
    )
    bundle_id: str = Field(min_length=3)
    decisions: list[FieldVerificationDecision] = Field(min_length=1)

    @field_validator("decisions")
    @classmethod
    def unique_decisions(
        cls, value: list[FieldVerificationDecision]
    ) -> list[FieldVerificationDecision]:
        assertion_ids = [row.assertion_id for row in value]
        if len(assertion_ids) != len(set(assertion_ids)):
            raise ValueError("each assertion must have one field decision")
        return value

    model_config = {"extra": "forbid"}


class CompactReviewDecision(BaseModel):
    """One bounded all-fields judgment for an immutable assertion."""

    assertion_id: str = Field(min_length=3)
    verdict: CompactReviewVerdictName
    evidence_ids: list[str] = Field(min_length=1)
    failed_fields: list[ScientificFieldName] = Field(default_factory=list)
    reason_code: str = Field(pattern=r"^[A-Z][A-Z0-9_]{2,63}$")

    @field_validator("evidence_ids")
    @classmethod
    def unique_evidence(cls, value: list[str]) -> list[str]:
        return sorted(set(value))

    @field_validator("failed_fields")
    @classmethod
    def unique_fields(
        cls, value: list[ScientificFieldName]
    ) -> list[ScientificFieldName]:
        return sorted(set(value), key=lambda row: _SCIENTIFIC_FIELD_ORDER[row])

    @model_validator(mode="after")
    def verdict_shape(self) -> "CompactReviewDecision":
        if self.verdict == "all_fields_supported" and self.failed_fields:
            raise ValueError(
                "all_fields_supported cannot contain failed_fields"
            )
        if self.verdict != "all_fields_supported" and not self.failed_fields:
            raise ValueError(
                "contradicted and not_proven require failed_fields"
            )
        return self

    model_config = {"extra": "forbid", "frozen": True}


class CompactReviewResponse(BaseModel):
    """Strict compact protocol for blinded independent hard-risk review."""

    protocol_version: Literal["alpha25_compact_independent_review_v1"] = (
        COMPACT_REVIEW_PROTOCOL_VERSION
    )
    bundle_id: str = Field(min_length=3)
    decisions: list[CompactReviewDecision] = Field(min_length=1)

    @field_validator("decisions")
    @classmethod
    def unique_decisions(
        cls, value: list[CompactReviewDecision]
    ) -> list[CompactReviewDecision]:
        assertion_ids = [row.assertion_id for row in value]
        if len(assertion_ids) != len(set(assertion_ids)):
            raise ValueError("each assertion must have one compact decision")
        return value

    model_config = {"extra": "forbid", "frozen": True}


class RecoveryProposal(BaseModel):
    """A proposed AxisFact wire object that still requires another verifier call."""

    proposal_id: str = Field(min_length=3)
    axis: VerificationAxis
    candidate: dict[str, Any]
    evidence_ids: list[str] = Field(min_length=1)
    reason_code: str = Field(pattern=r"^[A-Z][A-Z0-9_]{2,63}$")

    @field_validator("evidence_ids")
    @classmethod
    def unique_evidence(cls, value: list[str]) -> list[str]:
        return list(dict.fromkeys(value))

    model_config = {"extra": "forbid"}


class RecoveryRequest(BaseModel):
    """Bounded source-only request for one non-recursive omission scan."""

    protocol_version: str = VERIFICATION_PROTOCOL_VERSION
    request_id: str = Field(min_length=3)
    evidence: list[EvidenceSpan] = Field(min_length=1, max_length=10)
    entities: list[InventoryEntity] = Field(default_factory=list)
    source_char_count: int = Field(ge=1, le=12000)

    @model_validator(mode="after")
    def validate_source_count(self) -> "RecoveryRequest":
        if sum(len(row.text) for row in self.evidence) != self.source_char_count:
            raise ValueError("source_char_count must equal recovery evidence length")
        if len({row.evidence_id for row in self.evidence}) != len(self.evidence):
            raise ValueError("recovery evidence IDs must be unique")
        return self

    model_config = {"extra": "forbid", "frozen": True}


class RecoveryResponse(BaseModel):
    """Provider response for one bounded uncovered-source request."""

    protocol_version: str = VERIFICATION_PROTOCOL_VERSION
    proposals: list[RecoveryProposal] = Field(default_factory=list, max_length=10)

    model_config = {"extra": "forbid"}


class VerificationAuditRecord(BaseModel):
    """Complete reversible scientific decision persisted outside final.json."""

    assertion_id: str
    bundle_id: str
    protocol_version: str = VERIFICATION_PROTOCOL_VERSION
    decision: DecisionName | Literal["recovered"]
    reason_code: str
    before: dict[str, Any] | None = None
    after: dict[str, Any] | None = None
    evidence: list[EvidenceSpan] = Field(default_factory=list)
    merge_member_ids: list[str] = Field(default_factory=list)
    verifier_role: Literal["primary", "fallback", "deterministic"]
    fallback_used: bool = False
    cache_hit: bool = False
    rationale: str

    model_config = {"extra": "forbid"}


__all__ = [
    "AssertionEnvelope",
    "COMPACT_LABEL_REVIEW_PROTOCOL_VERSION",
    "COMPACT_REVIEW_PROTOCOL_VERSION",
    "CompactLabel",
    "CompactReviewDecision",
    "CompactReviewResponse",
    "DecisionName",
    "EvidenceSpan",
    "FIELD_VERIFICATION_PROTOCOL_VERSION",
    "FieldVerificationDecision",
    "FieldVerificationResponse",
    "InventoryEntity",
    "RecoveryProposal",
    "RecoveryRequest",
    "RecoveryResponse",
    "ReassignmentPatch",
    "RiskSeverity",
    "ScientificFieldName",
    "ScientificFieldVerdict",
    "ScientificFieldVerdictName",
    "VERIFICATION_PROTOCOL_VERSION",
    "VerificationAuditRecord",
    "VerificationAxis",
    "VerificationBundle",
    "VerificationDecision",
    "VerificationResponse",
    "canonical_json",
    "parse_compact_label_array",
    "stable_id",
]
