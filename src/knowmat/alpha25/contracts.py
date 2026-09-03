"""Compact LLM response contracts for axis-scoped alpha25 extraction."""

from __future__ import annotations

from typing import Any, Annotated, Literal, Union

from pydantic import BaseModel, Field, TypeAdapter, field_validator, model_validator


AxisName = Literal["composition", "processing", "structure", "properties"]
Role = Literal["Target", "Reference"]
DataNature = Literal[
    "Experimental", "Computed", "Literature_Experimental", "Literature_Computed"
]
_FACT_TYPES_BY_AXIS = {
    "composition": {"material_identity", "composition_observation"},
    "processing": {"process_text", "process_stage", "process_edge"},
    "structure": {"structure_text", "structure_observation", "characterization"},
    "properties": {"property"},
}


class GroundedModel(BaseModel):
    """Base response object whose facts require non-empty copied evidence."""

    source_evidence: list[str]
    confidence: float = Field(ge=0.0, le=1.0)
    # Chunk protocol metadata is intentionally excluded from serialization so
    # the alpha25 candidate/final schemas remain byte-for-byte compatible.  It
    # is still available to the extraction coordinator for boundary auditing.
    chunk_id: str | None = Field(default=None, exclude=True)
    source_span: str | None = Field(default=None, exclude=True)
    incomplete: bool = Field(default=False, exclude=True)
    continuation_of: str | None = Field(default=None, exclude=True)

    @field_validator("source_evidence", mode="before")
    @classmethod
    def coerce_evidence(cls, value: Any) -> Any:
        if isinstance(value, str):
            value = [value]
        return value

    @field_validator("source_evidence")
    @classmethod
    def require_evidence(cls, value: list[str]) -> list[str]:
        cleaned = [str(row).strip() for row in value if str(row).strip()]
        if not cleaned:
            raise ValueError("source_evidence must contain a non-empty copied OCR span")
        return cleaned

    model_config = {"extra": "forbid"}


class InventoryAnchor(GroundedModel):
    """Source-named item identity without any four-axis facts."""

    sample_id_raw: str = Field(min_length=1)
    material_name_raw: str | None = None
    state_raw: str | None = None
    role: Role
    data_nature: DataNature

    @field_validator("role", mode="before")
    @classmethod
    def normalize_role_case(cls, value: Any) -> Any:
        mapping = {"target": "Target", "reference": "Reference"}
        return mapping.get(str(value).strip().casefold(), value)

    @field_validator("data_nature", mode="before")
    @classmethod
    def normalize_data_nature_case(cls, value: Any) -> Any:
        normalized = str(value).strip().casefold().replace("-", "_").replace(" ", "_")
        mapping = {
            "experimental": "Experimental",
            "experiment": "Experimental",
            "measured": "Experimental",
            "computed": "Computed",
            "computation": "Computed",
            "computational": "Computed",
            "calculated": "Computed",
            "derived": "Computed",
            "inferred": "Computed",
            "predicted": "Computed",
            "simulation": "Computed",
            "simulated": "Computed",
            "synthetic": "Computed",
            "ml": "Computed",
            "machine_learning": "Computed",
            "literature_experimental": "Literature_Experimental",
            "literature": "Literature_Experimental",
            "reported_literature": "Literature_Experimental",
            "literature_computed": "Literature_Computed",
            "literature_computational": "Literature_Computed",
            "literature_simulated": "Literature_Computed",
        }
        return mapping.get(normalized, value)

    @field_validator("sample_id_raw")
    @classmethod
    def clean_sample_id(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("sample_id_raw cannot be blank")
        return value


class InventoryResponse(BaseModel):
    anchors: list[InventoryAnchor] = Field(default_factory=list)
    coverage: dict[str, Any] | None = None

    model_config = {"extra": "forbid"}


class _AxisFact(GroundedModel):
    sample_id_raw: str = Field(min_length=1)
    evidence_unit_id: str | None = None

    @field_validator("sample_id_raw")
    @classmethod
    def clean_sample_id(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("sample_id_raw cannot be blank")
        return value


class CompositionFact(_AxisFact):
    axis: Literal["composition"] = "composition"
    fact_type: Literal["material_identity", "composition_observation"]
    data: dict[str, Any]

    @model_validator(mode="after")
    def require_composition_fragment_shape(self) -> "CompositionFact":
        if self.fact_type == "material_identity":
            allowed = {
                "material_family",
                "material_name_raw",
                "designation_raw",
                "feedstock_form",
            }
            extra = sorted(set(self.data) - allowed)
            if extra:
                raise ValueError("material_identity contains unsupported keys: " + ", ".join(extra))
            return self
        required = {
            "observation_id",
            "source_type",
            "material_state",
            "sample_id",
            "basis",
            "component_type",
            "components",
            "measurement",
            "raw_expression",
            "data_source",
            "source_evidence",
            "note",
        }
        _require_data_keys(self.data, required, "composition_observation")
        return self


class ProcessingFact(_AxisFact):
    axis: Literal["processing"] = "processing"
    fact_type: Literal["process_text", "process_stage", "process_edge"]
    data: dict[str, Any]

    @model_validator(mode="after")
    def require_processing_fragment_shape(self) -> "ProcessingFact":
        required = {
            "process_text": {"original", "simplified"},
            "process_stage": {
                "candidate_stage_id",
                "stage_index_candidate",
                "process_name_raw",
                "process_code_candidate",
                "process_role_candidate",
                "parameters_raw",
                "source_evidence",
                "confidence",
            },
            "process_edge": {
                "source_candidate_stage_id",
                "target_candidate_stage_id",
                "edge_type",
                "source_evidence",
            },
        }[self.fact_type]
        _require_data_keys(self.data, required, self.fact_type)
        return self


class StructureFact(_AxisFact):
    axis: Literal["structure"] = "structure"
    fact_type: Literal[
        "structure_text", "structure_observation", "characterization"
    ]
    data: dict[str, Any]

    @model_validator(mode="after")
    def require_structure_fragment_shape(self) -> "StructureFact":
        required = {
            "structure_text": {"original", "simplified"},
            "structure_observation": {
                "observation_id",
                "structure_kind",
                "material_state",
                "sample_id",
                "source_type",
                "original",
                "simplified",
                "entities",
                "features",
                "source_evidence",
            },
            "characterization": {
                "characterization_id",
                "method_raw",
                "method_class",
                "source_evidence",
            },
        }[self.fact_type]
        _require_data_keys(self.data, required, self.fact_type)
        return self


class PropertyFact(_AxisFact):
    axis: Literal["properties"] = "properties"
    fact_type: Literal["property"] = "property"
    data: dict[str, Any]

    @model_validator(mode="after")
    def require_alpha25_raw_property_fields(self) -> "PropertyFact":
        required = {
            "property_id_candidate",
            "property_name_raw",
            "value_raw",
            "unit_raw",
            "test_method_raw",
            "test_standard_raw",
            "test_condition_raw",
            "test_specimen_raw",
            "raw_note",
            "data_source",
            "source_evidence",
            "confidence",
        }
        missing = sorted(required - set(self.data))
        if missing:
            raise ValueError(
                "property data is missing alpha25 candidate fields: " + ", ".join(missing)
            )
        return self


AxisFact = Annotated[
    Union[CompositionFact, ProcessingFact, StructureFact, PropertyFact],
    Field(discriminator="axis"),
]
_AXIS_FACT_ADAPTER = TypeAdapter(AxisFact)


class ContractRejection(BaseModel):
    """One independently invalid provider row removed from a complete response."""

    code: Literal["invalid_fact_contract"] = "invalid_fact_contract"
    fact_index: int = Field(ge=0)
    axis: AxisName | None = None
    fact_type: str | None = None
    source_evidence: list[str] = Field(default_factory=list)
    message: str

    model_config = {"extra": "forbid"}


_DATA_EVIDENCE_FACT_TYPES = {
    "composition_observation",
    "process_stage",
    "process_edge",
    "structure_observation",
    "characterization",
    "property",
}
_DATA_CONFIDENCE_FACT_TYPES = {"process_stage", "property"}


def _detect_fragment_type(axis: str, value: dict[str, Any]) -> str | None:
    """Identify only unambiguous raw data fragments from their required keys."""

    keys = set(value)
    if axis == "composition" and {"observation_id", "components", "source_type"} <= keys:
        return "composition_observation"
    if axis == "processing" and {"candidate_stage_id", "process_name_raw"} <= keys:
        return "process_stage"
    if axis == "processing" and {
        "source_candidate_stage_id",
        "target_candidate_stage_id",
        "edge_type",
    } <= keys:
        return "process_edge"
    if axis == "structure" and {"observation_id", "structure_kind", "sample_id"} <= keys:
        return "structure_observation"
    if axis == "structure" and {"characterization_id", "method_raw"} <= keys:
        return "characterization"
    if axis == "properties" and {"property_name_raw", "value_raw"} <= keys:
        return "property"
    return None


def _normalize_fact_wire(
    axis: str,
    fact: Any,
    *,
    complete_combined_property_metadata: bool = False,
) -> Any:
    """Repair only deterministic envelope omissions around unchanged fact data."""

    if not isinstance(fact, dict):
        return fact
    row = dict(fact)
    row.setdefault("axis", axis)
    if not isinstance(row.get("data"), dict):
        fragment_type = _detect_fragment_type(axis, row)
        if (
            fragment_type is None
            and axis == "composition"
            and str(row.get("fact_type") or "").casefold() == "material_identity"
            and str(row.get("sample_id_raw") or "").strip()
        ):
            # A combined response may place an InventoryAnchor-shaped material
            # identity in facts[]. Preserve its copied label/evidence while
            # supplying only the deterministic material-identity envelope.
            fragment_type = "material_identity"
            row = {
                "axis": axis,
                "fact_type": fragment_type,
                "sample_id_raw": str(row["sample_id_raw"]),
                "evidence_unit_id": row.get("evidence_unit_id"),
                "chunk_id": row.get("chunk_id"),
                "source_span": row.get("source_span"),
                "incomplete": row.get("incomplete", False),
                "continuation_of": row.get("continuation_of"),
                "data": {
                    "material_family": None,
                    "material_name_raw": row.get("material_name_raw"),
                    "designation_raw": row.get("sample_id_raw"),
                    "feedstock_form": None,
                },
                "source_evidence": row.get("source_evidence"),
                "confidence": row.get("confidence"),
            }
        if fragment_type is None:
            return row
        if not isinstance(row.get("data"), dict):
            evidence = row.get("source_evidence")
            confidence = row.get("confidence")
            sample_id = (
                row.get("sample_id") or row.get("sample_id_raw") or "not_reported"
            )
            row = {
                "axis": axis,
                "fact_type": fragment_type,
                "sample_id_raw": str(sample_id),
                "evidence_unit_id": row.get("evidence_unit_id"),
                "chunk_id": row.get("chunk_id"),
                "source_span": row.get("source_span"),
                "incomplete": row.get("incomplete", False),
                "continuation_of": row.get("continuation_of"),
                "data": {
                    key: child
                    for key, child in fact.items()
                    if key
                    not in {
                        "axis",
                        "fact_type",
                        "sample_id_raw",
                        "evidence_unit_id",
                        "confidence",
                        "chunk_id",
                        "source_span",
                        "incomplete",
                        "continuation_of",
                    }
                },
                "source_evidence": evidence,
                "confidence": confidence,
            }
    else:
        # Provider-added explanation keys in the fact envelope are not part of
        # the candidate contract. They carry no source fact and must not make
        # every valid sibling row trigger a second LLM request.
        envelope_keys = {
            "axis",
            "fact_type",
            "sample_id_raw",
            "evidence_unit_id",
            "data",
            "source_evidence",
            "confidence",
            "chunk_id",
            "source_span",
            "incomplete",
            "continuation_of",
        }
        row = {key: child for key, child in row.items() if key in envelope_keys}
    fact_type = str(row.get("fact_type") or "").casefold()
    data = dict(row["data"])
    if axis == "composition" and fact_type == "material_identity":
        allowed_identity_keys = {
            "material_family",
            "material_name_raw",
            "designation_raw",
            "feedstock_form",
        }
        data = {
            key: child for key, child in data.items() if key in allowed_identity_keys
        }
    if (
        complete_combined_property_metadata
        and axis == "composition"
        and fact_type == "composition_observation"
    ):
        # Alpha25 requires these nullable slots to be present even when the
        # source reports no measurement method or note. Their null value adds
        # no fact and avoids regenerating an otherwise complete response.
        data.setdefault("observation_id", "temporary")
        data.setdefault("material_state", "not_reported")
        data.setdefault("sample_id", str(row.get("sample_id_raw") or "not_reported"))
        data.setdefault("measurement", None)
        data.setdefault("note", None)
    if (
        complete_combined_property_metadata
        and axis == "processing"
        and fact_type == "process_stage"
    ):
        # IDs and final ordering are always reassigned after cross-task
        # reconciliation. Empty optional candidate slots add no source fact.
        data.setdefault("candidate_stage_id", "temporary")
        data.setdefault("stage_index_candidate", 0)
        data.setdefault("process_code_candidate", None)
        data.setdefault("process_role_candidate", None)
        data.setdefault("parameters_raw", [])
    if (
        complete_combined_property_metadata
        and axis == "structure"
        and fact_type == "structure_observation"
    ):
        evidence = row.get("source_evidence")
        if isinstance(evidence, str):
            evidence_rows = [evidence]
        elif isinstance(evidence, list):
            evidence_rows = [str(value) for value in evidence if str(value).strip()]
        else:
            evidence_rows = []
        original = " | ".join(evidence_rows)
        data.setdefault("observation_id", "temporary")
        data.setdefault("material_state", "not_reported")
        data.setdefault("sample_id", str(row.get("sample_id_raw") or "not_reported"))
        data.setdefault("original", original)
        data.setdefault("simplified", original)
        data.setdefault("entities", [])
        data.setdefault("features", [])
    if (
        complete_combined_property_metadata
        and axis == "structure"
        and fact_type == "characterization"
    ):
        data.setdefault("characterization_id", "temporary")
    if (
        complete_combined_property_metadata
        and axis == "properties"
        and fact_type == "property"
    ):
        # name/value remain mandatory facts. The remaining keys are candidate
        # metadata whose empty values explicitly mean "not reported". Filling
        # those empty slots is deterministic envelope repair, not extraction.
        data.setdefault("property_id_candidate", "temporary")
        data.setdefault("unit_raw", "")
        data.setdefault("test_method_raw", "")
        data.setdefault("test_standard_raw", "")
        data.setdefault("test_condition_raw", "")
        data.setdefault("test_specimen_raw", "")
        data.setdefault("raw_note", "")
        data.setdefault("data_source", "unknown")
    if axis == "structure" and fact_type == "structure_observation":
        # The provider sometimes omits an empty collection even though the
        # observation itself is complete and grounded. Restoring the two
        # schema-required containers is an envelope repair only: it does not
        # invent an entity, feature, value, or evidence span.
        data.setdefault("entities", [])
        data.setdefault("features", [])
    if row.get("source_evidence") in (None, "", []):
        evidence = data.get("source_evidence")
        if evidence not in (None, "", []):
            row["source_evidence"] = evidence
    if row.get("confidence") is None and data.get("confidence") is not None:
        row["confidence"] = data["confidence"]
    requires_evidence = fact_type in _DATA_EVIDENCE_FACT_TYPES or (
        axis == "properties"
        or axis == "processing" and fact_type != "process_text"
        or axis == "structure" and fact_type != "structure_text"
        or axis == "composition" and fact_type != "material_identity"
    )
    requires_confidence = fact_type in _DATA_CONFIDENCE_FACT_TYPES or axis == "properties"
    if requires_evidence and "source_evidence" not in data:
        evidence = row.get("source_evidence")
        if evidence not in (None, "", []):
            data["source_evidence"] = evidence
    if requires_confidence and "confidence" not in data:
        confidence = row.get("confidence")
        if confidence is not None:
            data["confidence"] = confidence
    return {**row, "data": data}


def _require_data_keys(data: dict[str, Any], required: set[str], label: str) -> None:
    missing = sorted(required - set(data))
    if missing:
        raise ValueError(f"{label} data is missing alpha25 keys: " + ", ".join(missing))


class AxisResponse(BaseModel):
    axis: AxisName
    facts: list[AxisFact] = Field(default_factory=list)
    coverage: dict[str, Any] | None = None

    @model_validator(mode="after")
    def facts_match_response_axis(self) -> "AxisResponse":
        mismatched = [fact.axis for fact in self.facts if fact.axis != self.axis]
        if mismatched:
            raise ValueError(
                f"response axis {self.axis!r} contains facts for {sorted(set(mismatched))}"
            )
        return self

    model_config = {"extra": "forbid"}


class MultiAxisResponse(BaseModel):
    """Mixed four-axis facts returned for one shared evidence unit."""

    axis: Literal["combined"] = "combined"
    anchors: list[InventoryAnchor] = Field(default_factory=list)
    facts: list[AxisFact] = Field(default_factory=list)
    contract_rejections: list[ContractRejection] = Field(default_factory=list)
    coverage: dict[str, Any] | None = None

    model_config = {"extra": "forbid"}


def _mixed_fact_axis(fact: Any) -> str | None:
    """Resolve a mixed fact's axis only when its wire shape is unambiguous."""

    if not isinstance(fact, dict):
        return None
    explicit = str(fact.get("axis") or "").strip().casefold()
    if explicit in _FACT_TYPES_BY_AXIS:
        return explicit
    fact_type = str(fact.get("fact_type") or "").strip().casefold()
    candidates = [
        axis for axis, allowed in _FACT_TYPES_BY_AXIS.items() if fact_type in allowed
    ]
    if len(candidates) == 1:
        return candidates[0]
    fragment = fact.get("data") if isinstance(fact.get("data"), dict) else fact
    candidates = [
        axis
        for axis in _FACT_TYPES_BY_AXIS
        if _detect_fragment_type(axis, fragment) is not None
    ]
    return candidates[0] if len(candidates) == 1 else None


def _wire_source_evidence(fact: Any) -> list[str]:
    """Read only provider-supplied evidence strings for a rejected wire row."""

    if not isinstance(fact, dict):
        return []
    values = fact.get("source_evidence")
    if values in (None, "", []):
        data = fact.get("data")
        values = data.get("source_evidence") if isinstance(data, dict) else None
    if isinstance(values, str):
        values = [values]
    if not isinstance(values, list):
        return []
    return list(dict.fromkeys(str(value).strip() for value in values if str(value).strip()))


def _contract_rejection(
    fact: Any,
    *,
    fact_index: int,
    fact_axis: str | None,
    message: str,
) -> ContractRejection:
    fact_type = (
        str(fact.get("fact_type") or "").strip() if isinstance(fact, dict) else ""
    )
    compact_message = " ".join(str(message).split())
    return ContractRejection(
        fact_index=fact_index,
        axis=(fact_axis if fact_axis in _FACT_TYPES_BY_AXIS else None),
        fact_type=fact_type or None,
        source_evidence=_wire_source_evidence(fact),
        message=compact_message[:1200],
    )


def parse_task_response(
    axis: str, value: Any
) -> InventoryResponse | AxisResponse | MultiAxisResponse:
    """Validate a decoded response for the requested task axis."""

    if axis == "inventory":
        if isinstance(value, list):
            value = {"anchors": value}
        elif isinstance(value, dict):
            if "anchors" not in value and "sample_id_raw" in value:
                value = {"anchors": [value]}
            elif isinstance(value.get("anchors"), dict):
                value = {**value, "anchors": [value["anchors"]]}
        return InventoryResponse.model_validate(value)
    if axis == "combined":
        if isinstance(value, list):
            value = {"axis": "combined", "facts": value}
        elif isinstance(value, dict):
            value = dict(value)
            is_anchor = (
                "sample_id_raw" in value
                and "role" in value
                and "data_nature" in value
                and "fact_type" not in value
            )
            # Providers occasionally obey the fact wire format but omit the
            # response envelope when only one fact is present.  This is the
            # mixed-axis equivalent of the single-axis normalization below:
            # preserve the fact's real axis inside facts[] while assigning the
            # requested combined axis only to the response envelope.
            if "facts" not in value and is_anchor:
                value = {"axis": "combined", "anchors": [value], "facts": []}
            elif "facts" not in value and (
                "fact_type" in value or _mixed_fact_axis(value) is not None
            ):
                value = {"axis": "combined", "facts": [value]}
            else:
                value["axis"] = "combined"
            if isinstance(value.get("anchors"), dict):
                value["anchors"] = [value["anchors"]]
            if isinstance(value.get("facts"), dict):
                value["facts"] = [value["facts"]]
            value = {
                key: child
                for key, child in value.items()
                if key in {
                    "axis",
                    "anchors",
                    "facts",
                    "contract_rejections",
                    "coverage",
                }
            }
        if isinstance(value, dict) and isinstance(value.get("anchors"), list):
            anchor_keys = {
                "sample_id_raw",
                "material_name_raw",
                "state_raw",
                "role",
                "data_nature",
                "source_evidence",
                "confidence",
                "chunk_id",
                "source_span",
                "incomplete",
                "continuation_of",
            }
            valid_anchors: list[Any] = []
            for anchor in value["anchors"]:
                if not isinstance(anchor, dict):
                    continue
                compact = {
                    key: child for key, child in anchor.items() if key in anchor_keys
                }
                try:
                    validated = InventoryAnchor.model_validate(compact)
                except Exception:
                    # An optional malformed identity must not force regeneration
                    # of every independently grounded fact in this evidence leaf.
                    continue
                valid_anchors.append(validated)
            value = {**value, "anchors": valid_anchors}
        if isinstance(value, dict) and isinstance(value.get("facts"), list):
            normalized_facts: list[Any] = []
            contract_rejections = list(value.get("contract_rejections") or [])
            for fact_index, fact in enumerate(value["facts"]):
                fact_axis = _mixed_fact_axis(fact)
                if fact_axis is None:
                    contract_rejections.append(
                        _contract_rejection(
                            fact,
                            fact_index=fact_index,
                            fact_axis=None,
                            message="Could not resolve a legal alpha25 axis for this fact row.",
                        ).model_dump()
                    )
                    continue
                normalized = _normalize_fact_wire(
                    fact_axis,
                    fact,
                    complete_combined_property_metadata=True,
                )
                if not isinstance(normalized, dict):
                    contract_rejections.append(
                        _contract_rejection(
                            fact,
                            fact_index=fact_index,
                            fact_axis=fact_axis,
                            message="Fact row is not a JSON object after envelope normalization.",
                        ).model_dump()
                    )
                    continue
                normalized["axis"] = fact_axis
                if str(normalized.get("fact_type") or "") not in _FACT_TYPES_BY_AXIS[
                    fact_axis
                ]:
                    contract_rejections.append(
                        _contract_rejection(
                            fact,
                            fact_index=fact_index,
                            fact_axis=fact_axis,
                            message="Fact type is not legal for the resolved alpha25 axis.",
                        ).model_dump()
                    )
                    continue
                try:
                    validated = _AXIS_FACT_ADAPTER.validate_python(normalized)
                except Exception as exc:
                    contract_rejections.append(
                        _contract_rejection(
                            fact,
                            fact_index=fact_index,
                            fact_axis=fact_axis,
                            message=str(exc),
                        ).model_dump()
                    )
                    continue
                # Keep excluded chunk metadata attached to the in-memory
                # model; GroundedModel excludes it from model_dump(), so the
                # public candidate/final schema is unchanged.
                normalized_facts.append(validated)
            value = {
                **value,
                "facts": normalized_facts,
                "contract_rejections": contract_rejections,
            }
        return MultiAxisResponse.model_validate(value)
    if isinstance(value, list):
        value = {"axis": axis, "facts": value}
    elif isinstance(value, dict):
        root_fragment_type = _detect_fragment_type(axis, value)
        if "facts" not in value and (
            "fact_type" in value or root_fragment_type is not None
        ):
            value = {"axis": axis, "facts": [value]}
        else:
            value = dict(value)
            value.setdefault("axis", axis)
            if isinstance(value.get("facts"), dict):
                value["facts"] = [value["facts"]]
    if isinstance(value, dict) and isinstance(value.get("facts"), list):
        normalized_facts = [
            _normalize_fact_wire(axis, fact) for fact in value["facts"]
        ]
        value = {
            **value,
            # A provider occasionally emits one otherwise valid row for another
            # requested axis. Reject that row locally; do not invalidate every
            # grounded sibling fact or mark the entire evidence leaf uncovered.
            "facts": [
                fact
                for fact in normalized_facts
                if isinstance(fact, dict)
                and str(fact.get("axis") or axis) == axis
                and str(fact.get("fact_type") or "")
                in _FACT_TYPES_BY_AXIS.get(axis, set())
            ],
        }
    response = AxisResponse.model_validate(value)
    if response.axis != axis:
        raise ValueError(f"requested axis {axis!r}, received {response.axis!r}")
    return response
