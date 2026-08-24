"""Paper-level precision promotion for Alpha25 candidate facts.

The extraction model remains a high-recall candidate generator.  This module
provides deterministic, source-derived records and decisions used to decide
which candidates may enter the existing materializer.  It never consults GT
data and never invents scientific fields.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import re
from collections import Counter
from copy import deepcopy
from dataclasses import dataclass
from typing import Any, Iterable, Literal, Sequence

from bs4 import BeautifulSoup

from knowmat.alpha25.claim_quality import (
    core_tensile_subtype,
    filter_composition_precision_facts,
    filter_axis_facts,
    is_core_tensile_property_name,
    semantic_fact_signature,
)
from knowmat.alpha25.contracts import (
    AxisFact,
    CompositionFact,
    InventoryAnchor,
    ProcessingFact,
    PropertyFact,
    StructureFact,
)
from knowmat.alpha25.evidence import normalize_evidence_text
from knowmat.alpha25.property_context import TensileProtocolLedger
from knowmat.alpha25.source_coordinates import (
    TensileAssertionDecision,
    resolve_tensile_assertion_coordinate,
)


def tensile_assertion_coordinates_v204_enabled() -> bool:
    """Return whether source-proven prose tensile coordinates are enabled."""

    raw = os.getenv("KNOWMAT2_ALPHA25_TENSILE_ASSERTION_COORDINATES_V204", "1")
    return raw.strip().casefold() not in {
        "0",
        "false",
        "no",
        "off",
        "disabled",
    }


def tensile_coordinate_fanout_guard_v204_enabled() -> bool:
    """Return whether complete assertion coordinates may defeat false fanout."""

    raw = os.getenv(
        "KNOWMAT2_ALPHA25_TENSILE_COORDINATE_FANOUT_GUARD_V204", "1"
    )
    return raw.strip().casefold() not in {
        "0",
        "false",
        "no",
        "off",
        "disabled",
    }


def tensile_result_protocol_binding_v204_enabled() -> bool:
    """Return whether a literal assertion temperature may fill an empty condition."""

    raw = os.getenv(
        "KNOWMAT2_ALPHA25_TENSILE_RESULT_PROTOCOL_BINDING_V204", "1"
    )
    return raw.strip().casefold() not in {
        "0",
        "false",
        "no",
        "off",
        "disabled",
    }


def structure_assertion_atomicity_v205_enabled() -> bool:
    """Return whether source-atomic Structure projection gates are enabled."""

    raw = os.getenv("KNOWMAT2_ALPHA25_STRUCTURE_ASSERTION_ATOMICITY_V205", "1")
    return raw.strip().casefold() not in {
        "0",
        "false",
        "no",
        "off",
        "disabled",
    }


def characterization_event_atomicity_v205_enabled() -> bool:
    """Return whether source-atomic Characterization events are enabled."""

    raw = os.getenv(
        "KNOWMAT2_ALPHA25_CHARACTERIZATION_EVENT_ATOMICITY_V205", "1"
    )
    return raw.strip().casefold() not in {
        "0",
        "false",
        "no",
        "off",
        "disabled",
    }


def property_provenance_condition_separation_v205_enabled() -> bool:
    """Return whether provenance is separated from scientific conditions."""

    raw = os.getenv(
        "KNOWMAT2_ALPHA25_PROPERTY_PROVENANCE_CONDITION_SEPARATION_V205", "1"
    )
    return raw.strip().casefold() not in {
        "0",
        "false",
        "no",
        "off",
        "disabled",
    }


def unique_material_owner_convergence_v205_enabled() -> bool:
    """Return whether uniquely proven tensile material owners may converge."""

    raw = os.getenv(
        "KNOWMAT2_ALPHA25_UNIQUE_MATERIAL_OWNER_CONVERGENCE_V205", "1"
    )
    return raw.strip().casefold() not in {
        "0",
        "false",
        "no",
        "off",
        "disabled",
    }


PromotionAction = Literal[
    "accept",
    "merge",
    "reassign_owner",
    "quarantine_owner",
    "quarantine_condition",
    "quarantine_conflict",
    "needs_review",
]

_PROMOTION_ACTIONS = {
    "accept",
    "merge",
    "reassign_owner",
    "quarantine_owner",
    "quarantine_condition",
    "quarantine_conflict",
    "needs_review",
}


@dataclass(frozen=True)
class PromotionDecision:
    """One immutable decision over existing candidate and owner IDs only."""

    action: PromotionAction
    candidate_ids: tuple[str, ...]
    rule: str
    survivor_id: str | None = None
    owner_id: str | None = None

    def __post_init__(self) -> None:
        if self.action not in _PROMOTION_ACTIONS:
            raise ValueError(f"Unsupported promotion action: {self.action!r}")
        if not self.candidate_ids:
            raise ValueError("candidate_ids must contain at least one existing claim")
        if self.action == "merge" and self.survivor_id not in self.candidate_ids:
            raise ValueError("merge survivor_id must be one of candidate_ids")
        if self.action == "reassign_owner" and not self.owner_id:
            raise ValueError("reassign_owner requires one existing owner_id")


@dataclass(frozen=True)
class PromotionIssue:
    """Audit record compatible with the existing materialization issue writer."""

    code: str
    sample_id_raw: str
    message: str
    severity: str = "review"
    path: str | None = None
    evidence: Any = None
    expected: Any = None
    actual: Any = None
    suggested_action: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "severity": self.severity,
            "path": self.path or f"items.{self.sample_id_raw}",
            "message": self.message,
            "evidence": self.evidence,
            "expected": self.expected,
            "actual": (
                self.actual
                if self.actual is not None
                else {"sample_id_raw": self.sample_id_raw}
            ),
            "suggested_action": self.suggested_action,
        }


@dataclass(frozen=True)
class PromotionRecord:
    """Immutable scientific candidate plus paper-local provenance."""

    claim_id: str
    fact: AxisFact
    source_order: int
    task_id: str | None
    evidence_unit_id: str | None
    evidence: tuple[str, ...]
    normalized_evidence: tuple[str, ...]
    assertion_signature: str
    semantic_signature: str
    explicit_owner: str
    owner_candidates: tuple[str, ...]
    risk_codes: tuple[str, ...] = ()


@dataclass(frozen=True)
class AssertionGroup:
    """Candidates proven to be projections of one paper-local assertion."""

    group_id: str
    source_block_key: str
    source_kind: Literal["prose", "table", "unresolved"]
    projection_owner: str
    records: tuple[PromotionRecord, ...]
    ambiguous_source: bool = False


@dataclass(frozen=True)
class PromotionResult:
    """Accepted existing facts and complete audit decisions."""

    accepted: tuple[AxisFact, ...]
    issues: tuple[PromotionIssue, ...]


@dataclass(frozen=True)
class OwnerNode:
    """One source-declared material identity, including role and state."""

    owner_id: str
    sample_id_raw: str
    material_name_raw: str
    state_raw: str
    role: str
    data_nature: str
    aliases: tuple[str, ...]
    source_evidence: tuple[str, ...] = ()


@dataclass(frozen=True)
class OwnerResolution:
    """Deterministic routing result over owners that already exist."""

    owner_ids: tuple[str, ...]
    candidate_owner_ids: tuple[str, ...]
    explicit_shared_owner_ids: tuple[str, ...] = ()
    risk_codes: tuple[str, ...] = ()


@dataclass(frozen=True)
class OwnerGraph:
    """Paper-local owner index; it never creates owners from candidate facts."""

    nodes: tuple[OwnerNode, ...]

    def node(self, owner_id: str) -> OwnerNode:
        for candidate in self.nodes:
            if candidate.owner_id == owner_id:
                return candidate
        raise KeyError(owner_id)

    def display_label(self, owner_id: str) -> str:
        candidate = self.node(owner_id)
        label = candidate.sample_id_raw or candidate.material_name_raw
        if candidate.state_raw:
            return f"{label} [{candidate.state_raw}]"
        return label


@dataclass(frozen=True)
class _SourceBlock:
    key: str
    kind: Literal["prose", "table"]
    start_line: int
    end_line: int
    normalized_text: str


def _identity_text(value: Any) -> str:
    return normalize_evidence_text(str(value or ""))


def _is_table_evidence_row(value: Any) -> bool:
    """Return whether an evidence string contains a real table row.

    Alpha25 task assembly joins independent evidence spans with ``" | "``.
    Treating any pipe character as a Markdown-table marker therefore disables
    prose owner/state gates for otherwise ordinary sentences.  Only a line
    that starts with a Markdown row marker (or an explicit HTML table) is a
    table coordinate; an inline pipe used as an evidence separator is not.
    """

    text = str(value or "")
    if "<table" in text.casefold():
        return True
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or "|" not in stripped:
            continue
        cells = _table_cells(stripped)
        if not cells:
            continue
        if stripped.startswith("|"):
            return True
        # OCR/table assembly sometimes strips the outer Markdown pipes.  A
        # compact row with at least three cells and numeric/condition tokens is
        # still a table coordinate (e.g. ``1 Solution treatment | HT2 | ...``).
        # Ordinary evidence concatenation usually has only two cells or a
        # sentence punctuation mark in one of the cells, so it remains prose.
        if len(cells) >= 3 and stripped.count("|") >= 2:
            compact = all(len(cell) <= 96 for cell in cells)
            no_sentence = all(not re.search(r"[.!?]", cell) for cell in cells)
            structured = any(
                re.search(
                    r"(?ix)(?:\d|%|°|\\circ|\b(?:h|min|sec|s|bar|mpa|gpa|w)\b|^[-–—]+$)",
                    cell,
                )
                for cell in cells[1:]
            )
            if compact and no_sentence and structured:
                return True
    return False


def _has_table_evidence(values: Sequence[Any]) -> bool:
    return any(_is_table_evidence_row(value) for value in values)


def _owner_node_id(anchor: InventoryAnchor) -> str:
    identity = {
        "sample": _identity_text(anchor.sample_id_raw),
        "state": _identity_text(anchor.state_raw),
        "role": str(anchor.role),
        "data_nature": str(anchor.data_nature),
    }
    encoded = json.dumps(
        identity,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return "owner_" + hashlib.sha256(encoded).hexdigest()[:24]


_BRACKETED_OWNER_STATE = re.compile(r"(?is)^\s*(.*?)\s*\[\s*([^\[\]]+)\s*\]\s*$")


def _owner_state_from_anchor(anchor: InventoryAnchor) -> str:
    """Return the source-declared state, including bracketed Sample_ID state.

    Inventory extraction often emits ``Sample_ID=EBAM [as-built]`` while
    leaving ``state_raw`` empty.  The bracket is part of the source label, so
    recovering it here does not invent an owner or a condition; it only makes
    the existing owner graph aware of a state that was already declared.
    """

    explicit = str(anchor.state_raw or "").strip()
    if explicit:
        return explicit
    match = _BRACKETED_OWNER_STATE.match(str(anchor.sample_id_raw or ""))
    if not match:
        return ""
    state = re.sub(r"\s+", " ", match.group(2)).strip()
    if _scientific_fold(state) in _UNREPORTED:
        return ""
    return state


def build_owner_graph(anchors: Iterable[InventoryAnchor]) -> OwnerGraph:
    """Build a stable graph index from source-declared inventory anchors."""

    grouped: dict[str, list[InventoryAnchor]] = {}
    for anchor in anchors:
        owner_id = _owner_node_id(anchor)
        grouped.setdefault(owner_id, []).append(anchor)

    by_id: dict[str, OwnerNode] = {}
    for owner_id, rows in grouped.items():
        first = rows[0]
        aliases = {
            value
            for anchor in rows
            for value in (
                str(anchor.sample_id_raw).strip(),
                str(anchor.material_name_raw or "").strip(),
            )
            if value
        }
        material_names = sorted(
            {
                str(anchor.material_name_raw or "").strip()
                for anchor in rows
                if str(anchor.material_name_raw or "").strip()
            },
            key=lambda row: (_identity_text(row), row),
        )
        by_id[owner_id] = OwnerNode(
            owner_id=owner_id,
            sample_id_raw=str(first.sample_id_raw).strip(),
            material_name_raw=(material_names[0] if material_names else ""),
            state_raw=_owner_state_from_anchor(first),
            role=str(first.role),
            data_nature=str(first.data_nature),
            aliases=tuple(sorted(aliases, key=lambda row: (_identity_text(row), row))),
            source_evidence=tuple(
                sorted(
                    {
                        str(evidence).strip()
                        for anchor in rows
                        for evidence in anchor.source_evidence
                        if str(evidence).strip()
                    },
                    key=lambda row: (_identity_text(row), row),
                )
            ),
        )
    return OwnerGraph(nodes=tuple(sorted(by_id.values(), key=lambda row: row.owner_id)))


def _literal_mention(haystack: str, needle: str) -> bool:
    normalized_haystack = _identity_text(haystack)
    normalized_needle = _identity_text(needle)
    if not normalized_haystack or not normalized_needle:
        return False
    if re.search(
        rf"(?<!\w){re.escape(normalized_needle)}(?!\w)",
        normalized_haystack,
    ) is not None:
        return True
    # OCR/Markdown commonly renders a short sample label as ``S_{15}``
    # while inventory anchors store ``S15``.  Tolerate formatting punctuation
    # only inside compact alphanumeric labels, never scientific-name fuzziness.
    compact = re.sub(r"[^a-z0-9]+", "", normalized_needle)
    if (
        2 <= len(compact) <= 12
        and any(character.isalpha() for character in compact)
        and any(character.isdigit() for character in compact)
    ):
        tolerant = r"[\s_{}]*".join(
            re.escape(character) for character in compact
        )
        return re.search(
            rf"(?<![a-z0-9]){tolerant}(?![a-z0-9])",
            normalized_haystack,
        ) is not None
    return False


def _distinctive_owner_label(value: str) -> bool:
    """Reject labels such as ``A`` that collide with ordinary prose words."""

    compact = re.sub(r"[^a-z0-9#]+", "", _identity_text(value))
    return bool(compact) and not (
        len(compact) == 1 and compact.isalpha()
    )


def _record_state(record: PromotionRecord) -> str:
    data = record.fact.data
    for key in ("material_state", "material_state_raw", "state_raw", "state"):
        value = data.get(key)
        normalized = _scientific_fold(value)
        # ``not_reported``/``unknown`` are absence markers, not a state. Treating
        # them as explicit state text makes two state variants look like an
        # intentionally shared owner and bypasses the ambiguity quarantine.
        if normalized and normalized not in _UNREPORTED:
            return str(value).strip()
    return ""


def _candidate_nodes(record: PromotionRecord, graph: OwnerGraph) -> list[OwnerNode]:
    owner = _identity_text(record.explicit_owner)
    exact_sample = [
        node for node in graph.nodes if _identity_text(node.sample_id_raw) == owner
    ]
    if exact_sample:
        return exact_sample
    return [
        node
        for node in graph.nodes
        if owner and any(_identity_text(alias) == owner for alias in node.aliases)
    ]


def _reference_base_label(value: Any) -> str:
    """Normalize a reference item's display label to its cited base label.

    Inventory labels use a small presentation convention such as
    ``Wrought [37] [reference]``.  Only the explicit ``[reference]`` suffix
    and a trailing numeric citation are removed; state labels such as
    ``A1 [HIPed]`` are intentionally left intact.
    """

    text = str(value or "").strip()
    if not text:
        return ""
    text = re.sub(r"\s*\[\s*reference\s*\]\s*$", "", text, flags=re.I)
    text = re.sub(r"\s*\[\s*\d{1,4}\s*\]\s*$", "", text)
    return _identity_text(text)


def _table_row_cells(value: Any) -> tuple[str, ...]:
    """Return exact normalized cells from one projected/source table row."""

    cells = tuple(
        normalized
        for cell in _table_cells(str(value or ""))
        if (normalized := _scientific_fold(cell))
    )
    return cells if len(cells) >= 3 else ()


def _ordered_cell_projection(
    projected: Sequence[str], source: Sequence[str]
) -> bool:
    """Require every cropped-row cell to occur in source order, exactly."""

    if not projected or len(projected) > len(source):
        return False
    index = 0
    for cell in source:
        if cell == projected[index]:
            index += 1
            if index == len(projected):
                return True
    return False


def _projected_reference_row_owner(
    support_rows: Sequence[str], references: Sequence[OwnerNode]
) -> OwnerNode | None:
    """Resolve a citation-cropped row only when one full source row matches.

    Evidence-unit projection may remove the ``Reference`` and ``Year`` columns
    before the model sees a comparison table.  The remaining cells can still
    be joined to the original row, but only by exact ordered-subsequence
    matching.  Repeated rows remain unresolved instead of guessing a citation.
    """

    projected_rows = [
        cells
        for evidence in support_rows
        for line in str(evidence or "").splitlines()
        if (cells := _table_row_cells(line))
    ]
    if not projected_rows:
        return None
    suffix_matches: dict[str, OwnerNode] = {}
    for node in references:
        source_rows = [
            cells
            for evidence in node.source_evidence
            for line in str(evidence or "").splitlines()
            if (cells := _table_row_cells(line))
        ]
        if any(
            len(projected) >= 3
            and len(projected) <= len(source)
            and projected[0] in source[: -(len(projected) - 1)]
            and tuple(projected[1:]) == tuple(source[-(len(projected) - 1) :])
            for projected in projected_rows
            for source in source_rows
        ):
            suffix_matches[node.owner_id] = node
    if suffix_matches:
        return (
            next(iter(suffix_matches.values()))
            if len(suffix_matches) == 1
            else None
        )
    matches: dict[str, OwnerNode] = {}
    for node in references:
        source_rows = [
            cells
            for evidence in node.source_evidence
            for line in str(evidence or "").splitlines()
            if (cells := _table_row_cells(line))
        ]
        if any(
            _ordered_cell_projection(projected, source)
            for projected in projected_rows
            for source in source_rows
        ):
            matches[node.owner_id] = node
    return next(iter(matches.values())) if len(matches) == 1 else None


def _table_reference_owner_collision(
    fact: AxisFact,
    record: PromotionRecord,
    graph: OwnerGraph,
) -> OwnerNode | None:
    """Return one existing Reference sibling for a cited comparison-table value.

    This is a role correction, not a chemistry/name fuzzy match.  It requires
    a current Target candidate, exactly one Reference item with the same
    presentation-stripped base label and a table-shaped evidence span.  The
    evidence must either name the citation/standard directly or be an exact
    cropped-row projection of one full cited source row.  If any coordinate is
    ambiguous the caller leaves the fact for the normal audit gates.
    """

    if not isinstance(
        fact, (CompositionFact, ProcessingFact, PropertyFact, StructureFact)
    ):
        return None
    candidate_nodes = _candidate_nodes(record, graph)
    current_targets = [
        node
        for node in candidate_nodes
        if node.role == "Target" and node.data_nature == "Experimental"
    ]
    if not current_targets:
        return None
    target_labels = {
        _reference_base_label(node.sample_id_raw) for node in current_targets
    }
    if len(target_labels) != 1:
        return None
    record_state = _identity_text(_record_state(record))
    state_matches = [
        node
        for node in current_targets
        if record_state and _identity_text(node.state_raw) == record_state
    ]
    target = state_matches[0] if len(state_matches) == 1 else current_targets[0]
    support = "\n".join(record.evidence)
    if not support or not _has_table_evidence(record.evidence):
        return None
    # The target label must be visible in the same table evidence.  This keeps
    # a citation from a neighboring table/chunk from changing an owner role.
    if not _literal_mention(support, target.sample_id_raw):
        return None
    base = _reference_base_label(target.sample_id_raw)
    if not base:
        return None
    references = [
        node
        for node in graph.nodes
        if node.role == "Reference"
        and str(node.data_nature).startswith("Literature_")
        and _reference_base_label(node.sample_id_raw) == base
    ]
    unique = {node.owner_id: node for node in references}
    if _REFERENCE_STANDARD_MARKER.search(support) and len(unique) == 1:
        return next(iter(unique.values()))
    support_citations = set(
        re.findall(r"\[\s*(\d{1,4})\s*\]", support)
    )
    if support_citations:
        cited = {
            owner_id: node
            for owner_id, node in unique.items()
            if support_citations
            & set(
                re.findall(
                    r"\[\s*(\d{1,4})\s*\]",
                    str(node.sample_id_raw or ""),
                )
            )
        }
        return next(iter(cited.values())) if len(cited) == 1 else None
    if _REFERENCE_TABLE_MARKER.search(support) and len(unique) == 1:
        return next(iter(unique.values()))
    return _projected_reference_row_owner(record.evidence, tuple(unique.values()))


def _table_candidate_nodes(
    record: PromotionRecord,
    graph: OwnerGraph,
) -> list[OwnerNode]:
    """Return the candidate owner plus already-declared state siblings for tables.

    A table value is a coordinate problem, not a chemistry similarity problem.
    The extractor often assigns a row to a base sample (``EBAM``) while the
    inventory contains source-declared children such as ``EBAM [as-built]`` or
    ``EBAM [HIPed]``.  Looking only at the base node makes a sibling value look
    valid because the table row is never compared against the existing state
    coordinate.  Expand only along the owner graph's established lineage; this
    does not create owners or perform a global material-name lookup.
    """

    candidates = _candidate_nodes(record, graph)
    if not candidates:
        return []
    expanded: dict[str, OwnerNode] = {
        node.owner_id: node for node in candidates
    }
    for node in _lineage_state_nodes(candidates, graph):
        expanded[node.owner_id] = node
    return list(expanded.values())


def _explicit_shared_nodes(
    record: PromotionRecord,
    graph: OwnerGraph,
) -> tuple[OwnerNode, ...]:
    evidence = "\n".join(record.evidence)
    mentioned = [
        node
        for node in graph.nodes
        if _distinctive_owner_label(node.sample_id_raw)
        and _literal_mention(evidence, node.sample_id_raw)
    ]
    # State variants with the same sample label are one mentioned identity until
    # the source also names a state; do not call that generic mention "shared".
    state = _record_state(record)
    if state:
        state_matches = [
            node
            for node in mentioned
            if _identity_text(node.state_raw) == _identity_text(state)
        ]
        if state_matches:
            mentioned = state_matches + [
                node
                for node in mentioned
                if _identity_text(node.sample_id_raw)
                != _identity_text(state_matches[0].sample_id_raw)
            ]
    else:
        by_sample: dict[str, list[OwnerNode]] = {}
        for node in mentioned:
            by_sample.setdefault(_identity_text(node.sample_id_raw), []).append(node)
        mentioned = [
            node
            for nodes in by_sample.values()
            for node in (
                nodes
                if len(nodes) == 1
                else [
                    candidate
                    for candidate in nodes
                    if candidate.state_raw
                    and _literal_mention(evidence, candidate.state_raw)
                ]
            )
        ]
    unique = {node.owner_id: node for node in mentioned}
    return tuple(unique[key] for key in sorted(unique))


def resolve_record_owner(
    record: PromotionRecord,
    graph: OwnerGraph,
) -> OwnerResolution:
    """Resolve one candidate without broadcasting generic facts to child states."""

    candidates = _candidate_nodes(record, graph)
    candidate_ids = tuple(sorted(node.owner_id for node in candidates))
    shared = _explicit_shared_nodes(record, graph)
    shared_ids = tuple(node.owner_id for node in shared)
    state = _record_state(record)

    if state:
        state_key = _identity_text(state)
        state_matches = [
            node
            for node in candidates
            if _identity_text(node.state_raw) == state_key
            and (
                not node.state_raw
                or _literal_mention("\n".join(record.evidence), node.state_raw)
                or state_key == _identity_text(node.state_raw)
            )
        ]
        if len(state_matches) == 1:
            return OwnerResolution(
                owner_ids=(state_matches[0].owner_id,),
                candidate_owner_ids=candidate_ids,
                explicit_shared_owner_ids=shared_ids,
            )

    base_matches = [node for node in candidates if not node.state_raw]
    if len(base_matches) == 1:
        return OwnerResolution(
            owner_ids=(base_matches[0].owner_id,),
            candidate_owner_ids=candidate_ids,
            explicit_shared_owner_ids=shared_ids,
        )
    if len(candidates) == 1:
        return OwnerResolution(
            owner_ids=(candidates[0].owner_id,),
            candidate_owner_ids=candidate_ids,
            explicit_shared_owner_ids=shared_ids,
        )
    if candidates:
        return OwnerResolution(
            owner_ids=(),
            candidate_owner_ids=candidate_ids,
            explicit_shared_owner_ids=shared_ids,
            risk_codes=("ambiguous_owner",),
        )
    return OwnerResolution(
        owner_ids=(),
        candidate_owner_ids=(),
        explicit_shared_owner_ids=shared_ids,
        risk_codes=("unresolved_owner",),
    )


def _record_identity(fact: AxisFact, normalized_evidence: tuple[str, ...]) -> str:
    scientific_identity = {
        "axis": fact.axis,
        "fact_type": fact.fact_type,
        "owner": _identity_text(fact.sample_id_raw),
        "evidence_unit_id": str(fact.evidence_unit_id or ""),
        "evidence": normalized_evidence,
        "semantic": semantic_fact_signature(fact),
    }
    encoded = json.dumps(
        scientific_identity,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return "promotion_" + hashlib.sha256(encoded).hexdigest()[:24]


def _assertion_signature(
    fact: AxisFact, normalized_evidence: tuple[str, ...]
) -> str:
    assertion_identity = {
        "evidence_unit_id": str(fact.evidence_unit_id or ""),
        "evidence": normalized_evidence,
    }
    encoded = json.dumps(
        assertion_identity,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def build_promotion_records(
    facts: Iterable[AxisFact],
    *,
    task_ids: Sequence[str | None] | None = None,
) -> list[PromotionRecord]:
    """Wrap candidates without mutating them or using order as scientific truth."""

    rows = list(facts)
    if task_ids is None:
        tasks: list[str | None] = [None] * len(rows)
    else:
        tasks = list(task_ids)
        if len(tasks) != len(rows):
            raise ValueError("task_ids must contain exactly one entry per fact")

    records: list[PromotionRecord] = []
    for source_order, (fact, task_id) in enumerate(zip(rows, tasks)):
        evidence = tuple(str(row).strip() for row in fact.source_evidence)
        normalized_evidence = tuple(
            normalize_evidence_text(row) for row in evidence
        )
        semantic = semantic_fact_signature(fact)
        owner = str(fact.sample_id_raw).strip()
        records.append(
            PromotionRecord(
                claim_id=_record_identity(fact, normalized_evidence),
                fact=fact,
                source_order=source_order,
                task_id=task_id,
                evidence_unit_id=fact.evidence_unit_id,
                evidence=evidence,
                normalized_evidence=normalized_evidence,
                assertion_signature=_assertion_signature(
                    fact, normalized_evidence
                ),
                semantic_signature=semantic,
                explicit_owner=owner,
                owner_candidates=(owner,),
            )
        )
    return records


def _source_blocks(source_text: str) -> list[_SourceBlock]:
    lines = str(source_text or "").splitlines()
    blocks: list[_SourceBlock] = []
    index = 0
    while index < len(lines):
        if not lines[index].strip():
            index += 1
            continue
        start = index
        is_table = lines[index].lstrip().startswith("|")
        collected: list[str] = []
        while index < len(lines):
            line = lines[index]
            if not line.strip():
                break
            if line.lstrip().startswith("|") != is_table:
                break
            collected.append(line)
            index += 1
        end = max(start, index - 1)
        normalized = normalize_evidence_text("\n".join(collected))
        if normalized:
            kind: Literal["prose", "table"] = "table" if is_table else "prose"
            digest = hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:12]
            blocks.append(
                _SourceBlock(
                    key=(
                        f"{kind}:L{start + 1:06d}-L{end + 1:06d}-{digest}"
                    ),
                    kind=kind,
                    start_line=start + 1,
                    end_line=end + 1,
                    normalized_text=normalized,
                )
            )
        if index == start:
            index += 1
    return blocks


def _record_source_binding(
    record: PromotionRecord, blocks: Sequence[_SourceBlock]
) -> tuple[str, Literal["prose", "table", "unresolved"], bool]:
    needles = tuple(row for row in record.normalized_evidence if row)
    matches = [
        block
        for block in blocks
        if needles and all(needle in block.normalized_text for needle in needles)
    ]
    if len(matches) == 1:
        return matches[0].key, matches[0].kind, False
    kind: Literal["prose", "table", "unresolved"] = (
        matches[0].kind if matches else "unresolved"
    )
    reason = "ambiguous" if matches else "unresolved"
    return (
        f"{reason}:{record.claim_id}:{record.source_order:06d}",
        kind,
        True,
    )


def _evidence_blob(record: PromotionRecord) -> str:
    return "\n".join(row for row in record.normalized_evidence if row)


def _same_projection(left: PromotionRecord, right: PromotionRecord) -> bool:
    if _identity_text(left.explicit_owner) != _identity_text(right.explicit_owner):
        return False
    if left.semantic_signature != right.semantic_signature:
        return False
    left_evidence = _evidence_blob(left)
    right_evidence = _evidence_blob(right)
    return bool(left_evidence and right_evidence) and (
        left_evidence == right_evidence
        or left_evidence in right_evidence
        or right_evidence in left_evidence
    )


def _assertion_group_id(
    source_block_key: str,
    records: Sequence[PromotionRecord],
) -> str:
    identity = {
        "source_block": source_block_key,
        "owner": _identity_text(records[0].explicit_owner),
        "claims": sorted(record.claim_id for record in records),
        "evidence": sorted(_evidence_blob(record) for record in records),
    }
    encoded = json.dumps(
        identity,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return "assertion_" + hashlib.sha256(encoded).hexdigest()[:24]


def group_source_assertions(
    records: Iterable[PromotionRecord],
    *,
    source_text: str,
) -> list[AssertionGroup]:
    """Group only source-proven projections; never join on text similarity alone."""

    rows = list(records)
    blocks = _source_blocks(source_text)
    grouped: list[dict[str, Any]] = []
    for record in rows:
        source_key, source_kind, ambiguous = _record_source_binding(record, blocks)
        selected: dict[str, Any] | None = None
        if not ambiguous:
            for candidate in grouped:
                if candidate["ambiguous"] or candidate["source_key"] != source_key:
                    continue
                if any(
                    _same_projection(record, existing)
                    for existing in candidate["records"]
                ):
                    selected = candidate
                    break
        if selected is None:
            grouped.append(
                {
                    "source_key": source_key,
                    "source_kind": source_kind,
                    "ambiguous": ambiguous,
                    "records": [record],
                }
            )
        else:
            selected["records"].append(record)

    result: list[AssertionGroup] = []
    for group in grouped:
        members = tuple(
            sorted(group["records"], key=lambda record: record.source_order)
        )
        result.append(
            AssertionGroup(
                group_id=_assertion_group_id(group["source_key"], members),
                source_block_key=group["source_key"],
                source_kind=group["source_kind"],
                projection_owner=members[0].explicit_owner,
                records=members,
                ambiguous_source=group["ambiguous"],
            )
        )
    return sorted(
        result,
        key=lambda group: min(record.source_order for record in group.records),
    )


def _ordered_evidence(
    records: Sequence[PromotionRecord], source_text: str
) -> list[str]:
    source = normalize_evidence_text(source_text)
    unique: dict[str, str] = {}
    for record in records:
        for raw, normalized in zip(record.evidence, record.normalized_evidence):
            if normalized and normalized not in unique:
                unique[normalized] = raw

    def evidence_key(item: tuple[str, str]) -> tuple[int, int, str]:
        normalized, _ = item
        position = source.find(normalized)
        if position < 0:
            position = len(source) + 1
        return position, -len(normalized), normalized

    return [raw for _, raw in sorted(unique.items(), key=evidence_key)]


def _survivor_rank(record: PromotionRecord) -> tuple[int, str]:
    return len(_evidence_blob(record)), record.claim_id


def _with_merged_evidence(
    survivor: PromotionRecord,
    members: Sequence[PromotionRecord],
    source_text: str,
) -> AxisFact:
    evidence = _ordered_evidence(members, source_text)
    data = deepcopy(survivor.fact.data)
    if "source_evidence" in data:
        data["source_evidence"] = list(evidence)
    if "confidence" in data:
        data["confidence"] = max(member.fact.confidence for member in members)
    return survivor.fact.model_copy(
        deep=True,
        update={
            "data": data,
            "source_evidence": list(evidence),
            "confidence": max(member.fact.confidence for member in members),
        },
    )


def _fact_output_key(fact: AxisFact, source_text: str) -> tuple[Any, ...]:
    normalized_rows = tuple(
        normalize_evidence_text(row) for row in fact.source_evidence
    )
    source = normalize_evidence_text(source_text)
    positions = tuple(
        source.find(row) if source.find(row) >= 0 else len(source) + 1
        for row in normalized_rows
    )
    return (
        min(positions, default=len(source) + 1),
        _identity_text(fact.sample_id_raw),
        semantic_fact_signature(fact),
        str(fact.evidence_unit_id or ""),
        normalized_rows,
    )


def deduplicate_source_assertions(
    facts: Iterable[AxisFact],
    *,
    source_text: str,
    task_ids: Sequence[str | None] | None = None,
) -> PromotionResult:
    """Merge only same-owner semantic duplicates proven by one source assertion."""

    records = build_promotion_records(facts, task_ids=task_ids)
    groups = group_source_assertions(records, source_text=source_text)
    accepted: list[AxisFact] = []
    issues: list[PromotionIssue] = []
    for group in groups:
        if len(group.records) == 1:
            accepted.append(group.records[0].fact)
            continue
        survivor_record = max(group.records, key=_survivor_rank)
        survivor_before = survivor_record.fact
        survivor_after = _with_merged_evidence(
            survivor_record, group.records, source_text
        )
        accepted.append(survivor_after)
        losers = sorted(
            (
                record
                for record in group.records
                if record is not survivor_record
            ),
            key=lambda record: (
                record.claim_id,
                record.normalized_evidence,
            ),
        )
        for loser in losers:
            issues.append(
                PromotionIssue(
                    code="promotion_assertion_duplicate_merged",
                    sample_id_raw=survivor_after.sample_id_raw,
                    message=(
                        "A repeated projection of one source assertion was merged "
                        "into one existing scientific fact."
                    ),
                    evidence=list(survivor_after.source_evidence),
                    expected={
                        "source_block_key": group.source_block_key,
                        "projection_owner": group.projection_owner,
                        "survivor_id": survivor_record.claim_id,
                    },
                    actual={
                        "removed": loser.fact.model_dump(),
                        "survivor_before": survivor_before.model_dump(),
                        "survivor_after": survivor_after.model_dump(),
                    },
                    suggested_action=(
                        "Review only if the copied spans represent independent "
                        "scientific assertions."
                    ),
                )
            )

    accepted.sort(key=lambda fact: _fact_output_key(fact, source_text))
    issues.sort(
        key=lambda issue: (
            issue.code,
            _identity_text(issue.sample_id_raw),
            json.dumps(issue.actual, ensure_ascii=False, sort_keys=True),
        )
    )
    return PromotionResult(accepted=tuple(accepted), issues=tuple(issues))


_UNREPORTED = {
    "",
    "n a",
    "na",
    "none",
    "not available",
    "not given",
    "not provided",
    "not reported",
    "unknown",
    "unspecified",
}
_UNKNOWN_ENTITY = {
    "entity",
    "unknown",
    "unknown entity",
    "not reported",
    "unspecified",
}
_METHOD_FAMILIES: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("sem", re.compile(r"(?i)\bSEM\b|scanning\s+electron\s+microscop")),
    (
        "tem",
        re.compile(
            r"(?i)\b(?:HR)?TEM\b|(?:high[\s-]*resolution\s+)?"
            r"transmission\s+electron\s+microscop"
        ),
    ),
    ("stem", re.compile(r"(?i)\bSTEM\b|scanning\s+transmission\s+electron")),
    ("ebsd", re.compile(r"(?i)\bEBSD\b|electron\s+backscatter\s+diffraction")),
    ("tkd", re.compile(r"(?i)\bTKD\b|transmission\s+kikuchi\s+diffraction")),
    ("xrd", re.compile(r"(?i)\bXRD\b|x[\s-]*ray\s+diffraction")),
    (
        "saed",
        re.compile(
            r"(?i)\bSAED\b|selected[\s-]*(?:area|area\s+electron)\s+"
            r"diffraction"
        ),
    ),
    ("fft", re.compile(r"(?i)\bFFT\b|fast[\s-]*fourier[\s-]*transform")),
    ("eds", re.compile(r"(?i)\b(?:EDS|EDX)\b|energy[\s-]*dispersive\s+x[\s-]*ray")),
    ("apt", re.compile(r"(?i)\bAPT\b|atom\s+probe\s+tomograph")),
    ("om", re.compile(r"(?i)\bOM\b|optical\s+microscop")),
    (
        "xct",
        re.compile(
            r"(?i)\b(?:XCT|micro[\s-]*CT)\b|x[\s-]*ray\s+"
            r"(?:computed\s+)?tomograph"
        ),
    ),
    ("nmr", re.compile(r"(?i)\bNMR\b|nuclear\s+magnetic\s+resonance")),
    (
        "nexafs",
        re.compile(
            r"(?i)\bNEXAFS\b|near[\s-]*edge\s+x[\s-]*ray\s+"
            r"absorption\s+fine[\s-]*structure"
        ),
    ),
    ("xps", re.compile(r"(?i)\bXPS\b|x[\s-]*ray\s+photoelectron")),
    ("raman", re.compile(r"(?i)\braman\b")),
)
_GENERIC_CHARACTERIZATION_CLASSES = {
    "",
    "analysis",
    "compositional",
    "compositional analysis",
    "diffraction",
    "diffraction analysis",
    "electron microscopy",
    "imaging",
    "method",
    "microscopy",
    "spectroscopy",
    "tomography",
}
_CHARACTERIZATION_CLASS_LABELS = {
    "sem": "SEM",
    "tem": "TEM",
    "stem": "STEM",
    "ebsd": "EBSD",
    "tkd": "TKD",
    "xrd": "XRD",
    "saed": "SAED",
    "fft": "FFT",
    "eds": "EDS",
    "apt": "APT",
    "om": "OM",
    "xct": "XCT",
    "nmr": "NMR",
    "nexafs": "NEXAFS",
    "xps": "XPS",
    "raman": "Raman",
}
_CHARACTERIZATION_CLASS_ALIASES = {
    "sem": {"sem", "scanning electron microscopy", "scanning electron microscope"},
    "tem": {"tem", "transmission electron microscopy", "transmission electron microscope"},
    "stem": {"stem", "scanning transmission electron microscopy"},
    "ebsd": {"ebsd", "electron backscatter diffraction"},
    "tkd": {"tkd", "transmission kikuchi diffraction"},
    "xrd": {"xrd", "x ray diffraction"},
    "saed": {"saed", "selected area electron diffraction"},
    "fft": {"fft", "fast fourier transform"},
    "eds": {
        "eds",
        "edx",
        "energy dispersive spectroscopy",
        "energy dispersive x ray spectroscopy",
    },
    "apt": {"apt", "atom probe tomography"},
    "om": {"om", "optical microscopy", "light optical microscopy"},
    "xct": {
        "xct",
        "micro ct",
        "x ray ct",
        "x ray computed tomography",
        "x ray microtomography",
        "x ray tomography",
    },
    "nmr": {"nmr", "nuclear magnetic resonance"},
    "nexafs": {"nexafs", "near edge x ray absorption fine structure"},
    "xps": {"xps", "x ray photoelectron spectroscopy"},
    "raman": {"raman", "raman spectroscopy"},
}
_CHARACTERIZATION_PROCEDURAL_CUE = re.compile(
    r"(?ix)\b(?:"
    r"perform(?:ed|ing)?|conduct(?:ed|ing)?|acquir(?:ed|ing|isition)|"
    r"characteri[sz](?:ed|ation|ing)?|examin(?:ed|ation|ing)?|"
    r"analy[sz](?:ed|is|ing)?|measur(?:ed|ement|ing)?|test(?:ed|ing)?|"
    r"utili[sz](?:ed|ing)?|employ(?:ed|ing)?|us(?:ed|ing)|"
    r"record(?:ed|ing)?|collect(?:ed|ion|ing)?|obtain(?:ed|ing)?|"
    r"operat(?:ed|ing)?|equipped|determined\s+by"
    r")\b"
)
_CHARACTERIZATION_RESULT_MENTION = re.compile(
    r"(?ix)\b(?:"
    r"fig(?:ure)?\.?|image|images|micrograph|micrographs|map|maps|mapping|"
    r"pattern|patterns|result|results|analysis\s+presented|according\s+to|"
    r"based\s+on|show|shows|showing|reveal|reveals|revealing|"
    r"confirm|confirms|confirming|observed\s+by"
    r")\b"
)
_CHARACTERIZATION_STRONG_DECLARATION = re.compile(
    r"(?ix)(?:"
    r"\b(?:was|were|is|are|has\s+been|have\s+been)\s+(?:also\s+)?"
    r"(?:performed|conducted|acquired|characteri[sz]ed|examined|"
    r"analy[sz]ed|measured|tested|utili[sz]ed|employed|used|recorded|"
    r"collected|operated)\b|"
    r"\b(?:performed|conducted|acquired|characteri[sz]ed|examined|"
    r"analy[sz]ed|measured|tested|utili[sz]ed|employed|used|recorded|"
    r"collected|operated)\s+(?:using|by|with|via|on)\b"
    r")"
)
# A compact method row in an extracted Markdown table is a valid method
# assertion even when it does not use prose verbs (for example ``SEM: Zeiss
# Supra 55``).  Keep this allow-list deliberately narrow: a caption such as
# ``Fig. 2 | SEM images`` must not become a Characterization method merely
# because it happens to be rendered as a table.
_CHARACTERIZATION_TABLE_METHOD_LABEL = re.compile(
    r"(?im)^\s*\|?\s*(?:"
    r"om|optical\s+microscopy|sem|fesem|tem|stem|hrtem|ebsd|eds|edx|"
    r"xrd|xps|apt|fibs?(?:/sem)?|saed|raman|eis|clsm|profilometr(?:y|ic)|"
    r"electron\s+backscatter\s+diffraction|transmission\s+electron\s+"
    r"microscopy|scanning\s+electron\s+microscopy|energy\s+dispersive\s+"
    r"spectroscop(?:y|ic)|x[-\s]?ray\s+diffraction"
    r")\s*(?::|\|)\s*\S+"
)
_CHARACTERIZATION_OBSERVATION_CONTEXT = re.compile(
    r"(?ix)\b(?:"
    r"as[\s-](?:printed|built|fabricated|deposited|received|cast)|"
    r"after|before|post[\s-](?:test|creep|fatigue|heat[\s-]*treat(?:ment|ed))|"
    r"heat[\s-]*treat(?:ed|ment|ing)|hip(?:ped)?|sinter(?:ed|ing)|"
    r"anneal(?:ed|ing)|ag(?:ed|ing)|oxid(?:ized|ised|ation)|"
    r"creep(?:ed|ing|[\s-]*tested)?|fatigue(?:d|[\s-]*tested)?|"
    r"fractur(?:e|ed)|powder|top\s+layer|bulk\s+region"
    r")\b"
)
# These labels describe a rendered result (figure/map/pattern) rather than an
# acquisition method.  A high-recall chunk often turns each caption into a
# second Characterization fact.  We quarantine only the presentation-shaped
# candidates whose own evidence has no procedural declaration; a formal
# method sentence such as ``EBSD maps were acquired using ...`` remains valid.
_CHARACTERIZATION_PRESENTATION_ARTIFACT = re.compile(
    r"(?ix)\b(?:"
    r"image(?:s)?|micrograph(?:s)?|map(?:s|ping)?|pattern(?:s)?|"
    r"result(?:s)?|analysis|analyses|observation(?:s)?|"
    r"inverse\s+pole\s+figure|phase\s+map|ipf|iq\s+map|"
    r"kam\s+map|gnd\s+map|fft|sadp|"
    r"quantitative\s+microscopy|bright[-\s]*field"
    r")\b"
)
# These labels are structured subfields of an instrument/method record, not
# independent characterization modalities.  The extractor sometimes emits
# them as separate methods (``XRD instrument``, ``SEM condition``), which
# creates formally valid-looking but semantically wrong Characterization rows.
_CHARACTERIZATION_NON_METHOD_LABEL = re.compile(
    r"(?ix)(?:^|\s)(?:instrument|equipment|condition|setting|parameter|"
    r"operating\s+(?:condition|parameter)|machine|device|detector|"
    r"accelerating\s+voltage|scan(?:ning)?\s+(?:speed|range)|"
    r"probe\s+condition)s?\s*$"
)
_PROCESS_REGION_LOCATOR = re.compile(
    r"(?ix)\b(?:"
    r"cast(?:ing)?|laser[\s-]*(?:glaz(?:ed|ing)|remelt(?:ed|ing))|"
    r"remelt(?:ed|ing)|melt[\s-]*pool|fusion|heat[\s-]*affected"
    r")[\s-]*(?:region|zone|area|track|surface)s?\b"
)
_REGION_SCOPED_PROPERTY_COORDINATE = re.compile(
    r"(?ix)\b(?:"
    r"(?:fine|coarse|certain|selected|local|specific)\s+regions?\b|"
    r"regions?\b|zones?\b|areas?\b|locations?\b|"
    r"rosette(?:\s+(?:region|regions|microstructure))?\b|"
    r"micropillars?\b|micro[-\s]*pillars?\b|"
    r"phase[-\s]+specific\b|region[-\s]+specific\b"
    r")"
)
_STRUCTURE_LOCAL_REGION_COORDINATE = re.compile(
    r"(?ix)\b(?:"
    r"(?:fine|coarse|upper|lower|top|bottom|central|center|middle|"
    r"interdendritic|dendritic|cellular|melt[-\s]*pool|fracture|crack|"
    r"surface|bulk|prx|lagb|hagb|intrinsic|extrinsic|rosette|"
    r"grain[-\s]*boundary|phase[-\s]*specific)\s+"
    r"(?:region|regions|zone|zones|area|areas|section|sections|surface|"
    r"layer|layers|colony|colonies|boundary|boundaries|rosette|rosettes)|"
    r"\b(?:fracture\s+surface|melt[-\s]*pool\s+(?:center|boundary)|"
    r"cellular\s+walls?|fine[-\s]+grained\s+layer)\b"
    r")"
)
_PROCESS_OBSERVATION_CUE = re.compile(
    r"(?ix)\b(?:"
    r"SEM|EBSD|TEM|STEM|EDS|EDX|XRD|microscop(?:e|y|ic)|"
    r"characteri[sz](?:ed|ation|ing)?|observ(?:ed|ation)|"
    r"microstructur(?:e|al)|morpholog(?:y|ical)|texture|"
    r"grain|grains|phase|phases|precipitate|precipitates|"
    r"pore|pores|porosity|defect|defects|segregation|interface|"
    r"consist(?:ed|s|ing)?|contain(?:ed|s|ing)?|"
    r"absent|presence|present|left|remain(?:ed|s|ing)?|"
    r"show(?:ed|s|ing)?|reveal(?:ed|s|ing)?"
    r")\b"
)
_PROCESS_EVENT_CUE = re.compile(
    r"(?ix)(?:"
    r"\b(?:was|were|is|are|been|being|had\s+been|have\s+been)\s+"
    r"(?:successfully\s+)?(?:"
    r"cast|fabricated|manufactured|processed|produced|prepared|"
    r"built|printed|deposited|clad|melted|remelted|laser[\s-]*glazed|"
    r"atomized|annealed|aged|solutioni[sz]ed|heat[\s-]*treated|"
    r"sintered|forged|rolled|extruded|machined"
    r")\b|"
    r"\b(?:casting|fabrication|manufacturing|processing|deposition|"
    r"printing|building|laser[\s-]*glazing|laser[\s-]*remelting|"
    r"atomization|annealing|aging|solution\s+treatment|heat\s+treatment|"
    r"sintering|forging|rolling|extrusion)\b.{0,80}?"
    r"\b(?:was|were|is|are)?\s*(?:applied|performed|conducted|"
    r"carried\s+out|used)\b|"
    r"\b(?:after|before|following|prior\s+to)\s+(?:the\s+)?(?:"
    r"casting|fabrication|processing|deposition|laser[\s-]*glazing|"
    r"laser[\s-]*remelting|atomization|annealing|aging|"
    r"solution\s+treatment|heat\s+treatment|sintering|forging|rolling"
    r")\b|"
    r"\b(?:fabricated|manufactured|processed|produced|prepared|built|"
    r"printed|deposited|remelted|laser[\s-]*glazed)\s+"
    r"(?:by|using|with|via|under|at|on)\b"
    r")"
)
_PROCESS_PARAMETER_CUE = re.compile(
    r"(?ix)\b(?:"
    r"process(?:ing)?\s+(?:parameter|condition|window|route|method)s?|"
    r"laser\s+power|scan(?:ning)?\s+(?:speed|velocity)|hatch\s+spacing|"
    r"layer\s+thickness|rotation\s+angle|feed(?:stock)?\s+rate|"
    r"travel\s+speed|wire\s+feed|gas\s+flow|build\s+plate\s+temperature|"
    r"heat(?:ing)?\s+rate|cooling\s+rate|holding\s+time|dwell\s+time|"
    r"pressure|atmosphere"
    r")\b"
)
# A process-stage candidate can be emitted from an item label or a result
# caption (for example ``as-built EBAM sample``) even though the cited span
# never asserts that a process step occurred.  Keep this cue separate from the
# broader parameter vocabulary: a source phrase such as ``aging heat
# treatment`` is a genuine process reference, while a bare sample label is not.
_PROCESS_TREATMENT_CUE = re.compile(
    r"(?ix)\b(?:"
    r"heat[\s-]*treat(?:ed|ment|ing)?|"
    r"solution[\s-]*(?:treat(?:ed|ment|ing)?|anneal(?:ed|ing)?)|"
    r"anneal(?:ed|ing)?|ag(?:ed|ing)?|"
    r"sinter(?:ed|ing)?|forg(?:e|ed|ing)|"
    r"roll(?:ed|ing)|extrud(?:e|ed|ing)|"
    r"cast(?:ing|ed)?|fabricat(?:e|ed|ion|ing)|"
    r"manufactur(?:e|ed|ing)|deposi(?:t|ted|tion)|"
    r"print(?:ed|ing)?|build(?:ing|t)?|"
    r"laser[\s-]*(?:melt(?:ed|ing)|clad(?:ded|ding)?|"
    r"remelt(?:ed|ing)|glaz(?:ed|ing))"
    r")\b"
)
_PROCESS_ACTION_ASSERTION = re.compile(
    r"(?ix)\b(?:"
    r"heat(?:ed|ing)?|cool(?:ed|ing)?|electro[\s-]*etch(?:ed|ing)?|"
    r"homogen(?:ized|ised|ization|isation)|"
    r"mix(?:ed|ing)?|blend(?:ed|ing)?|siev(?:ed|ing)?|"
    r"store(?:d|ing)?|reload(?:ed|ing)?|irradiat(?:ed|ing)?|"
    r"relax(?:ed|ing|ation)?|consolidat(?:e|ed|ing|ion)|"
    r"section(?:ed|ing)?|mount(?:ed|ing)?|polish(?:ed|ing)?|"
    r"etch(?:ed|ing)?|calculat(?:e|ed|ing|ion)|"
    r"simulat(?:e|ed|ing|ion)|tensile[\s-]*(?:test|tested|deform)|"
    r"test(?:ed|ing)?|weld(?:ed|ing)?|"
    r"delay(?:ed|ing)?|deposi(?:t|ted|tion)|"
    r"subject(?:ed|ing)?|develop(?:ed|ing)?|"
    r"becom(?:e|es|ing)|break(?:s|ing)?|form(?:ed|ing)?|"
    r"affect(?:ed|ing)?|accelerat(?:e|ed|ing|ion)|"
    r"maintain(?:ed|ing)?|utili[sz](?:e|ed|ing)|employ(?:ed|ing)?|"
    r"obtain(?:ed|ing)?|result(?:ed|ing)?|"
    r"powder[\s-]*bed|electron[\s-]*beam|laser[\s-]*powder[\s-]*bed|"
    r"EBM|PBF(?:-[A-Z]+)?|LPBF|LHW[\s-]*DED|"
    r"process(?:ed|ing)?\s+(?:was|is|parameters?|route|conditions?)"
    r")\b"
)
# Sample preparation is a frequent source of false Processing stages.  These
# operations describe how a specimen was made ready for microscopy or testing,
# not how the material itself was fabricated or heat-treated.  Keep the
# vocabulary explicit and pair it with a specimen/material target below so a
# genuine production operation such as ``the surface was polished`` is not
# rejected solely because it contains the word ``polished``.
_PROCESS_SPECIMEN_PREPARATION_ACTION = re.compile(
    r"(?ix)\b(?:"
    r"section(?:ed|ing)?|cross[\s-]*section(?:ed|ing)?|"
    r"cut(?:ting|t?ed)?|wire[\s-]*cut(?:ting|t?ed)?|edm|"
    r"mount(?:ed|ing)?|embed(?:ded|ding)?|"
    r"polish(?:ed|ing)?|grind(?:ed|ing)?|"
    r"etch(?:ed|ing)?|metallograph(?:ic|y)|"
    r"specimen[\s-]*prepar(?:ed|ation)|sample[\s-]*prepar(?:ed|ation)"
    r")\b"
)
_PROCESS_SPECIMEN_PREPARATION_TARGET = re.compile(
    r"(?ix)\b(?:"
    r"sample(?:s)?|specimen(?:s)?|coupon(?:s)?|"
    r"wall(?:s)?|component(?:s)?|part(?:s)?|"
    r"cross[\s-]*section(?:s)?|metallograph(?:ic)?\s+(?:sample|specimen)s?"
    r")\b"
)
# ``_PROCESS_DIRECT_EVENT_ASSERTION`` intentionally includes the generic verb
# ``prepared`` for ordinary process descriptions.  For this gate we need the
# narrower material-event subset; otherwise ``samples were prepared by
# sectioning`` would incorrectly protect the very preparation projection we
# are trying to isolate.
_PROCESS_MATERIAL_EVENT_ASSERTION = re.compile(
    r"(?ix)(?:"
    r"\b(?:was|were|is|are|been|being|had\s+been|have\s+been)\s+"
    r"(?:successfully\s+)?(?:cast|fabricated|manufactured|processed|"
    r"produced|built|printed|deposited|clad|melted|remelted|"
    r"laser[\s-]*glazed|laser[\s-]*remelted|atomized|annealed|aged|"
    r"solutioni[sz]ed|heat[\s-]*treated|sintered|forged|rolled|"
    r"extruded|welded)\b|"
    r"\b(?:fabricated|manufactured|processed|produced|built|printed|"
    r"deposited|remelted|laser[\s-]*glazed|cast|annealed|aged|"
    r"sintered|forged|rolled|extruded|welded)\s+"
    r"(?:by|using|with|via|under|at|on)\b|"
    r"\b(?:process|treatment|heat[\s-]*treatment|annealing|aging|"
    r"sintering|fabrication|deposition|printing|building)\b.{0,80}\b"
    r"(?:was|were|is|are|performed|applied|conducted|carried\s+out|used|done)\b"
    r")"
)
_PROCESS_TEST_PROTOCOL_CUE = re.compile(
    r"(?ix)\b(?:"
    r"tensile[\s-]*(?:test(?:ed|ing)?|deform(?:ed|ing)?|loading)|"
    r"fatigue[\s-]*(?:test(?:ed|ing)?|load(?:ed|ing)?)|"
    r"creep[\s-]*(?:test(?:ed|ing)?|load(?:ed|ing)?)|"
    r"stress[\s-]*strain|s[\s-]*s\s+curves?|"
    r"mechanical[\s-]*test(?:ed|ing)?"
    r")\b"
)
# A result sentence can contain process vocabulary without reporting that the
# stage happened (``high build temperature ... results in ...``).  Keep this
# cue set separate from the broad action vocabulary above so causal verbs do
# not accidentally promote a process stage.
_PROCESS_RESULT_EXPLANATION_CUE = re.compile(
    r"(?ix)\b(?:"
    r"result(?:s|ed|ing)?\s+in|"
    r"lead(?:s|ing)?\s+to|"
    r"due\s+to|because\s+of|"
    r"consequent(?:ly)?|therefore|thus|hence|"
    r"caus(?:e|es|ed|ing)\s+"
    r")\b"
)
_PROCESS_HYPOTHETICAL_CUE = re.compile(
    r"(?ix)\b(?:"
    r"if|unless|would|could|might|may|possibly|potentially|"
    r"assuming|should\s+be|in\s+case|were\s+to|"
    r"can\s+be\s+added|could\s+be\s+added|"
    r"if\s+added|if\s+applied|if\s+used"
    r")\b"
)
_PROCESS_DIRECT_EVENT_ASSERTION = re.compile(
    r"(?ix)(?:"
    r"\b(?:was|were|is|are|been|being|had\s+been|have\s+been)\s+"
    r"(?:successfully\s+)?(?:cast|fabricated|manufactured|processed|"
    r"produced|prepared|built|printed|deposited|clad|melted|remelted|"
    r"laser[\s-]*glazed|atomized|annealed|aged|solutioni[sz]ed|"
    r"heat[\s-]*treated|sintered|forged|rolled|extruded|welded)\b|"
    r"\b(?:fabricated|manufactured|processed|produced|prepared|built|"
    r"printed|deposited|remelted|laser[\s-]*glazed|cast|annealed|aged|"
    r"sintered|forged|rolled|extruded|welded)\s+"
    r"(?:by|using|with|via|under|at|on)\b|"
    r"\b(?:process|treatment|heat[\s-]*treatment|annealing|aging|"
    r"sintering|fabrication|deposition|printing|building)\b.{0,80}\b"
    r"(?:was|were|is|are|performed|applied|conducted|carried\s+out|"
    r"used|done)\b"
    r")"
)
_PROCESS_EXPLICIT_TREATMENT_REFERENCE = re.compile(
    r"(?ix)\b(?:"
    r"hot\s+isostatic\s+press(?:ing|ed)?|hip(?:ed|ped|ping)?|"
    r"heat[\s-]*treat(?:ed|ment|ing)?|"
    r"solution[\s-]*(?:treat(?:ed|ment|ing)?|anneal(?:ed|ing)?)|"
    r"anneal(?:ed|ing)?|ag(?:ed|ing)|sinter(?:ed|ing)?|"
    r"forg(?:e|ed|ing)|roll(?:ed|ing)|extrud(?:e|ed|ing)"
    r")\b"
)
_PROCESS_HEAT_TREATMENT_STAGE_NAME = re.compile(
    r"(?ix)\b(?:post[\s-]*ht|heat[\s-]*treat(?:ed|ment|ing)?|"
    r"solution[\s-]*(?:treat(?:ed|ment|ing)?|anneal(?:ed|ing)?)|"
    r"anneal(?:ed|ing)?|ag(?:ed|ing)|stress[\s-]*relie(?:f|ved|ving))\b"
)
_PROCESS_DURATION_PARAMETER_NAME = re.compile(
    r"(?ix)\b(?:duration|time|holding[\s-]*time|hold[\s-]*time|"
    r"dwell[\s-]*time)\b"
)
_PROCESS_DIRECT_HEATING_EVENT = re.compile(
    r"(?ix)\b(?:was|were|is|are|been|being|had\s+been|have\s+been)\s+"
    r"(?:heated|annealed|aged|solution[\s-]*treated|heat[\s-]*treated)\b|"
    r"\bheated\s+(?:to|at|under|in|for)\b"
)
_PROCESS_METADATA_PARAMETER = re.compile(
    r"(?ix)^\s*(?:"
    r"equipment|machine|device|system|instrument|apparatus|"
    r"environment|atmosphere|chamber|ambient|vacuum|gas|"
    r"(?:build|printing|processing)\s+environment|"
    r"energy\s+source|cooling\s+(?:method|condition)|"
    r"technique|technology|method|process(?:\s+type)?|"
    r"laser\s+(?:type|system)|robotic\s+system|"
    r"powder\s+spreading\s+mechanism|feedstock|wire[-\s]?feed|"
    r"feedstock\s+form|material\s+form|"
    r"(?:accelerating\s+)?voltage\s+source|type|model|manufacturer"
    r")\s*$"
)
_PROCESS_NUMERIC_PARAMETER_NAME = re.compile(
    r"(?ix)\b(?:"
    r"power|(?:scan(?:ning)?|travel|wire|feed|recoat|roller|oscillator)\s+"
    r"(?:speed|velocity|rate)|speed|velocity|hatch\s+spacing|"
    r"layer\s+(?:thickness|height)|layer\s+thickness|"
    r"rotation\s+angle|interlayer\s+delay|delay|temperature|"
    r"(?:heating|cooling|feed|hold(?:ing)?|dwell|sintering)\s+rate|"
    r"(?:hold(?:ing)?|dwell|sintering|annealing)\s+time|duration|"
    r"pressure|current|voltage|energy\s+density|line\s+offset|"
    r"number\s+of\s+beads|no\.\s+of\s+beads|printing\s+direction|"
    r"build\s+(?:plate|platform)\s+temperature"
    r")\b"
)
_WRONG_AXIS_PROPERTY = re.compile(
    r"(?ix)^\s*(?:"
    r"mass\s+(?:loaded|loading)|powder\s+flow\s+time|flow\s+time|"
    r"equipment\s+(?:capacity|power|speed)|specimen\s+(?:length|width|thickness|diameter)|"
    r"(?:extensometer\s+)?gauge\s+(?:length|width|thickness)|crosshead\s+speed|"
    r"(?:test|testing)\s+(?:frequency|rate|speed|temperature)|"
    r"frequency|(?:constant\s+)?strain\s+rate|loading\s+rate|"
    r"(?:re)?loading\s+rate|reload\s+rate|displacement\s+rate|"
    r"relaxation\s+holding\s+time|"
    r"preheat(?:ing)?\s+temp(?:erature)?(?:\s*\([^)]*\))?(?:\s+.*)?|"
    r"melt\s+pool\s+(?:length|width|depth|size|area|volume)(?:\s+.*)?|"
    r"cooling\s+rates?(?:\s+.*)?|"
    r"(?:(?:linear|areal|area|volumetric|specific)\s+)?energy\s+density(?:\s+.*)?|"
    r"(?:processing|build|deposition)\s+efficiency|"
    r"(?:cathodic\s+reduction|potentiostatic\s+hold)\s+potential|"
    r"crystallographic(?:\s+orientation)?\s+misorientation|dislocation\s+density|"
    r"pyrometer\s+measurement\s+precision|"
    r"(?:(?:quasi[\s-]*static|uniaxial)\s+)*"
    r"(?:creep|tensile|fatigue|compression)\s+tests?"
    r"(?:\s+(?:rate|speed|temperature|frequency))?|"
    r"(?:average\s+)?fitted\s+ellipse\s+aspect\s+ratio|"
    r"(?:average\s+)?equivalent\s+circle\s+diameter|"
    r"schmid\s+factor(?:\s*\([^)]*\))?\s+frequency(?:\s+.*)?|"
    r"(?:lagb|low[\s-]*angle\s+grain\s+boundar(?:y|ies))\s+fraction|"
    r"(?:β₀[/\s]*B₂|beta\s*0[/\s]*b\s*2)\s+phase\s+content|"
    r"volume\s+fraction\s+of\s+dinl|"
    r"(?:wall|bead)\s+(?:width|height|length|thickness)(?:\s+.*)?"
    r")\s*$"
)
_PROCESS_ENERGY_DENSITY_UNIT = re.compile(
    r"(?ix)^\s*j\s*/\s*mm(?:\s*(?:\^?\s*[123]|[²³]))?\s*$"
)
_COMPARATIVE_TENSILE_PROPERTY = re.compile(
    r"(?ix)(?:"
    r"improv(?:ement|ed)?|increas(?:e|ed)?|increment|"
    r"reduc(?:tion|ed)?|decreas(?:e|ed)?|retention|"
    r"relative|ratio|difference|discrepancy|anisotrop(?:y|ic)|"
    r"contribut(?:e|ed|ion)|per\b|higher|lower|change|"
    r"at\s+given\s+strain|strengthening"
    r")"
)
# A Property candidate can be source-grounded and still be the wrong scientific
# object: high-recall extraction commonly turns a comparison, improvement, or
# strengthening decomposition into an apparently independent scalar.  Core
# tensile names are handled by the stricter claim-quality gate above, but the
# same projection pattern occurs for creep, density, hardness, corrosion, and
# other material outcomes.  Keep this vocabulary intentionally explicit rather
# than rejecting every result whose evidence happens to contain a comparison.
_COMPARATIVE_PROPERTY_NAME = re.compile(
    r"(?ix)\b(?:"
    r"relative\s+(?:change|difference|increase|decrease|improvement|ratio|"
    r"retention|gain|loss)|"
    r"(?:change|difference|discrepancy|variation|anisotrop(?:y|ic)|"
    r"improvement|enhancement|reduction|increase|decrease|increment|"
    r"decrement|contribution|retention|gain|loss|debit)\b|"
    r"\b(?:higher|lower|more|less)\s+than\b|"
    r"\b(?:approximate|estimated|calculated)\s+"
    r"(?:decrease|increase|difference|improvement|reduction)\b"
    r")"
)
_ABSOLUTE_RELATIVE_PROPERTY_NAMES = {
    # These are dimensionless/normalized material outcomes, not comparisons
    # between two reported samples.  They must remain eligible for promotion.
    "relative density",
    "relative permeability",
    "relative permittivity",
}
_COMPARATIVE_PROPERTY_VALUE = re.compile(
    r"(?ix)(?:"
    # ``more than 800 MPa``/``less than 1%`` are absolute inequalities and
    # remain valid material outcomes.  Only directional comparison words are
    # unsafe when they occur inside the candidate's own value literal.
    r"\b(?:higher|lower)\b"
    r"|\bcompared\s+(?:to|with|against)\b"
    r"|\brelative\s+to\b"
    r"|\b(?:improv(?:ed|ement|ing)|enhanc(?:ed|ement|ing)|"
    r"reduc(?:ed|tion|ing)|decreas(?:ed|e|ing)|increas(?:ed|e|ing)|"
    r"retain(?:ed|s|ing)?|contribut(?:e|ed|ion|ing)|"
    r"differ(?:ence|ent|ed|ing)|anisotrop(?:y|ic)|"
    r"variation|discrepancy|similar|comparable|superior|inferior|"
    r"stronger|weaker|"
    r"better|worse|greater|"
    # ``more than 800 MPa`` and ``less than 1%`` are absolute inequalities;
    # only the unqualified comparative forms below are projections.
    r"more(?!\s+than)|less(?!\s+than))\b"
    r")"
)
_NON_RESULT_TABLE_FIRST_COLUMN = {
    "process",
    "processes",
    "parameter",
    "parameters",
    "process parameter",
    "process parameters",
    "process stage",
    "test parameter",
    "test parameters",
    "test condition",
    "test conditions",
    "equipment",
    "specimen",
    "setting",
    "settings",
    "control",
    "controls",
}
_NON_RESULT_TABLE_SECOND_COLUMN = {
    "rate",
    "value",
    "values",
    "condition",
    "conditions",
    "parameter",
    "parameters",
    "setting",
    "settings",
    "equipment",
    "method",
}
_PROPERTY_METADATA_NAME = re.compile(
    r"(?ix)^\s*(?:"
    r"unknown|not\s+reported|not\s+available|not\s+determined|"
    r"fit(?:ted)?\s+parameters?|"
    r"young\s*/\s*voigt(?:\s+model)?|voigt\s*/\s*young(?:\s+model)?|"
    r"(?:measurement|test|analysis|calculation)\s+(?:method|model|procedure)|"
    r"(?:material|property|result)\s+(?:parameter|value|field)"
    r")\s*$"
)
_PROPERTY_METADATA_TABLE_HEADER = re.compile(
    r"(?ix)^\s*(?:fit\s+parameters?|young(?:\s*/\s*|\s+)voigt(?:\s+model)?|"
    r"measurement\s+method|analysis\s+method|model)\s*$"
)
_PROPERTY_PROCESS_PARAMETER_NAME = re.compile(
    r"(?ix)\b(?:"
    r"laser\s+power|scan(?:ning)?\s+(?:speed|velocity)|hatch\s+spacing|"
    r"layer\s+thickness|rotation\s+angle|feed(?:stock)?\s+rate|"
    r"travel\s+speed|wire\s+feed|gas\s+flow|build\s+plate\s+temperature|"
    r"heat(?:ing)?\s+rate|cooling\s+rate|holding\s+time|dwell\s+time|"
    r"process(?:ing)?\s+(?:parameter|condition|window|route|setting)s?|"
    r"(?:parameter|setting)\s+(?:value|range)|laser\s+power\s+condition"
    r")\b"
)
_DIMENSIONLESS_PROPERTY = re.compile(
    r"(?ix)(?:"
    r"poisson(?:'?s)?\s+ratio|stress\s+exponent|"
    r"aspect\s+ratio|schmid\s+factor|coefficient|index|"
    r"dimensionless|normalized\s+ratio|normalized\s+value"
    r")"
)
_NEGATED_STRUCTURE_FEATURE = re.compile(
    r"(?ix)(?:"
    r"\bno\b|\bnot\s+(?:observed|detected|present)\b|\babsent\b|"
    r"\bwithout\b|\beliminat(?:ed|ion)\b|\bannihilat(?:ed|ion)\b|"
    r"\bsuppress(?:ed|ion)\b|\bdeplet(?:ed|ion)\b|"
    r"\bdisappear(?:ed|ance|ing)?\b|\bdissolv(?:ed|ution|ing)?\b"
    r")"
)
_NEGATED_STRUCTURE_ENTITY_ROLES = {"absent", "negative"}
_NEGATED_STRUCTURE_ENTITY_EXPRESSION = re.compile(
    r"(?ix)^(?:"
    r"no\b|without\b|absence\s+of\b|"
    r"not\s+(?:observed|detected|present)\b"
    r")"
)
_NONATOMIC_STRUCTURE_ENTITY_TYPES = {
    "chemical state",
    "constituent",
    "feature",
    "morphology",
    "other",
}
_STRUCTURE_ENTITY_DESCRIPTOR_TOKENS = {
    "constituent",
    "constituents",
    "defect",
    "defects",
    "entity",
    "feature",
    "features",
    "grain",
    "grains",
    "matrix",
    "matrices",
    "particle",
    "particles",
    "phase",
    "phases",
    "pore",
    "pores",
    "precipitate",
    "precipitates",
    "structure",
    "structures",
}
# A bare chemical element token in Structure is normally a composition or
# partitioning projection (for example ``W shows no preference for either
# phase``), not an independently observed structural entity.  Keep compounds
# and phase labels such as ``W-rich gamma phase`` eligible.
_STRUCTURE_BARE_ELEMENT_ENTITY = re.compile(
    r"(?i)^(?:h|he|li|be|b|c|n|o|f|ne|na|mg|al|si|p|s|cl|ar|k|ca|"
    r"sc|ti|v|cr|mn|fe|co|ni|cu|zn|y|zr|nb|mo|tc|ru|rh|pd|ag|cd|"
    r"hf|ta|w|re|os|ir|pt|au|hg|al|pb|bi|sn|sb|te|i|xe|la|ce|pr|"
    r"nd|sm|eu|gd|tb|dy|ho|er|tm|yb|lu|th|pa|u|np|pu|am|cm|bk|cf|"
    r"es|fm|md|no|lr)$"
)
_STRUCTURE_CONTEXT_ONLY_FEATURES = {"area", "location", "region"}
_STRUCTURE_GENERIC_ENTITY_NAMES = {
    "location",
    "material",
    "region",
    "result",
    "sample",
    "specimen",
}
_INLINE_CORE_TENSILE_UNIT = re.compile(
    r"(?ix)(?:%|\b(?:m|g|k)?pa\b|\bhv(?:[_₀-₉.]*)\b)"
)
# Source-literal strength units used by the narrow tensile provenance gate.
# Keep this separate from canonical-unit normalization: ``0.33 GPa`` is a
# valid source value whose materialized canonical unit may be MPa, while
# ``value_raw=0.33, unit_raw=MPa`` against that same quote is a source conflict.
_TENSILE_SOURCE_VALUE_UNIT = re.compile(
    r"(?ix)(?<![a-z0-9])(?:gpa|mpa|kpa|pa)(?![a-z0-9])"
)
_TENSILE_STATE_COORDINATE = re.compile(
    r"(?ix)\b(?:"
    r"hip(?:ed|ping)?(?:\s*[-+]?\s*\d+)?|"
    r"ht\s*[-+]?\s*\d+|"
    r"heat[\s-]*treated?|thermal[\s-]*treated?|"
    r"solution[\s-]*treated?|annealed?|aged?|aging|"
    r"as[\s-]*(?:built|printed|fabricated|deposited)|"
    r"sintered?|consolidated?|pbf[-\s]*(?:eb|lb)|"
    r"(?:horizontal|vertical|transverse|longitudinal)\s+direction"
    r")\b"
    r"|\b(?:hip|ht)\s*[-+]?\s*\d+\s*[+]\s*\w+\b"
    r"|\b(?:hip|ht)\s*[-+]?\s*\d+\b\s*\+\s*"
    r"(?:hip|ht)\s*[-+]?\s*\d+\b"
)
# The table fallback below is intentionally limited to unambiguous core
# tensile labels.  A bare ``Tensile strength`` row is often a generic summary
# or a literature comparison; without an explicit UTS/YS/elongation label it
# should remain in the audit stream rather than being newly promoted merely
# because a repeated table value can be located.
_EXPLICIT_TABLE_TENSILE_PROPERTY_NAME = re.compile(
    r"(?ix)\b(?:uts|ultimate\s+tensile\s+strength|yield\s+strength|"
    r"yield\s+stress|elongation|te|eab)\b"
)
_EXPLICIT_TREATMENT_CONDITION = re.compile(
    r"(?ix)\b(?:"
    r"after|following|subsequent(?:ly)?|aged?|ageing|aging|annealed?|"
    r"heat[\s-]*treated?|heat[\s-]*treatment|thermal[\s-]*treatment|"
    r"thermal[\s-]*exposure|solution[\s-]*(?:treated?|treatment)|"
    r"homogen(?:ized|ised)|sinter(?:ed|ing)?"
    r")\b[^.\n;]{0,120}?"
    r"[-+]?\d+(?:\.\d+)?\s*(?:°\s*C|°C|K|"
    r"\^?\s*\\circ\s*(?:\{\s*C\s*\}|C))"
    r"\s*(?:/|for|at|,|;|and)\s*"
    r"\d+(?:\.\d+)?\s*(?:hours?|hrs?|h|minutes?|mins?|min|seconds?|secs?|sec|s)\b"
)
_FEEDSTOCK_SCOPE = re.compile(
    r"(?ix)\b(?:feed[\s-]*stock|powder(?:s)?|powdered|"
    r"(?:gas|water|plasma)[\s-]*atomiz(?:ed|ation)|raw\s+material)\b"
)
_FEEDSTOCK_OWNER_LABEL = re.compile(
    r"(?ix)\b(?:feed[\s-]*stock|powder(?:s)?|powdered|"
    r"atomiz(?:ed|ation)|raw\s+material)\b"
)
_TENSILE_PREPARATION_CONDITION = re.compile(
    r"(?ix)\b(?:"
    r"feed[\s-]*stock|powder(?:s)?|powder[\s-]*bed|powdered|"
    r"(?:gas|water|plasma)[\s-]*atomiz(?:ed|ation)|raw\s+material|"
    r"wire[\s-]*(?:feed|arc)|wire\s+based|filament|"
    r"build\s+(?:plate|platform)|substrate|"
    r"(?:as[\s-]*)?(?:built|printed|deposited|fabricated)\s+condition"
    r")\b"
)
_TENSILE_EXTERNAL_SCOPE = re.compile(
    r"(?ix)\b(?:reference|previous\s+work|literature|"
    r"comput(?:ed|ational|ation)|simulation|simulated|predicted|"
    r"calculated|model(?:led|ed)?|theoretical)\b"
)
_TENSILE_RESULT_CUE = re.compile(
    r"(?ix)\b(?:tensile|yield|ultimate|uts|elongation|ductility|"
    r"strength|stress|strain|fracture)\b"
)
_TENSILE_PROCESSED_RESULT_SCOPE = re.compile(
    r"(?ix)\b(?:"
    r"as[\s-]*(?:printed|built|fabricated|deposited)|"
    r"printed\s+(?:sample|part|specimen)s?|"
    r"built\s+(?:sample|part|specimen)s?|"
    r"fabricated\s+(?:sample|part|specimen)s?|"
    r"sinter(?:ed|ing)?|"
    r"heat[\s-]*treated?|"
    r"hip(?:ped)?|"
    r"consolidated\s+(?:sample|part|specimen)s?"
    r")\b"
)

# A process candidate whose sample label starts with a treatment/state word is
# frequently a model-generated owner (for example ``annealed Cu-B4C
# composite``) rather than a source-declared material identity.  Such a label
# is safe only when the complete label is literally present in the candidate's
# own evidence or when an earlier coordinate gate routed it to an existing
# state owner.  Keep this allow-list narrow; ordinary alloy/sample labels such
# as ``Wrought`` and ``PBF-EB`` are not affected.
_STATE_PREFIXED_PROCESSING_OWNER = re.compile(
    r"(?ix)^\s*(?:"
    r"anneal(?:ed|ing)?|aged?|"
    r"heat[\s-]*treated?|solution[\s-]*treated?|"
    r"sinter(?:ed|ing)?|as[\s-]*(?:built|printed|fabricated|deposited)"
    r")\b"
)


def _distinctive_state_prefixed_processing_owner(value: Any) -> bool:
    """Return whether a treatment-prefixed owner carries a material identity.

    Generic labels such as ``sintered sample`` and ``as-built`` are commonly
    generated as shorthand for a process event and do not create a new sample
    identity by themselves.  A qualified label such as ``annealed Cu-B4C
    composite`` is different: it looks like a model-created state/material
    owner and needs the literal-owner guard below.  Keeping this distinction
    avoids suppressing grounded process facts merely because their structured
    owner used a generic stage description.
    """

    text = str(value or "").strip()
    match = _STATE_PREFIXED_PROCESSING_OWNER.match(text)
    if match is None:
        return False
    suffix = text[match.end() :].strip(" -_:;,/")
    if not suffix:
        return False
    return not bool(
        re.fullmatch(
            r"(?ix)(?:sample|specimen|part|material|alloy|powder|wall|"
            r"component|components|piece|coupon)s?",
            suffix,
        )
    )

# Reference tables commonly carry a citation or a named standard in the
# value/row (``[6]``, ``[ASTM F136]``).  This is deliberately not a general
# origin classifier: it is used only when a Target and a Reference owner with
# the same base label already coexist in the paper-local inventory.
_REFERENCE_TABLE_MARKER = re.compile(
    r"(?ix)\[(?:[^\]]*\b(?:astm|ams|iso|en|ref(?:erence)?|\d{1,4})\b[^\]]*)\]"
)
_REFERENCE_STANDARD_MARKER = re.compile(
    r"(?ix)\[(?:[^\]]*\b(?:astm|ams|iso|en|ref(?:erence)?)\b[^\]]*)\]"
)
_EXTERNAL_SOURCE_ASSERTION = re.compile(
    r"(?ix)(?:\bet\s+al\.?\b|\bprevious(?:ly)?\s+(?:reported|work|study)\b|"
    r"\b(?:literature|reference|cited|prior\s+study)\b|"
    r"\[\s*\d+(?:\s*[,;]\s*\d+)*\s*\])"
)
# Keep author-year citations separate from the broad gate above.  The
# structure unasserted-entity pass deliberately defers only the established
# citation grammar; otherwise a bibliographic year can make a bare noun
# survive long enough to evade owner routing.  The dedicated external-source
# pass consumes this narrower pattern only after the structural payload has
# already been validated.
_EXTERNAL_BIBLIOGRAPHIC_ASSERTION = re.compile(
    r"(?ix)(?:\([^\n()]{2,100}\b(?:19|20)\d{2}\b[^\n()]*\)|"
    r"\b[A-Z][A-Za-z'’-]+(?:\s+(?:and|&)\s+[A-Z][A-Za-z'’-]+)?[, ]+"
    r"(?:19|20)\d{2}\b)"
)
_EXTERNAL_REPORTING_CUE = re.compile(
    r"(?ix)\b(?:reported|reports?|according\s+to|"
    r"as\s+reported\s+by|by\s+(?:the\s+)?(?:same|that|their)\s+study|"
    r"et\s+al\.?)\b"
)
_EXTERNAL_REFERENCE_AUTHOR = re.compile(
    r"(?<![A-Za-z])(?P<author>[A-Z][A-Za-zÀ-ÖØ-öø-ÿ'’.-]{1,}"
    r"\s+et\s+al\.?)"
)
_EXTERNAL_REFERENCE_AUTHOR_YEAR = re.compile(
    r"(?<![A-Za-z])(?P<author>[A-Z][A-Za-zÀ-ÖØ-öø-ÿ'’.-]{1,}"
    r"\s+et\s+al\.?)\s*,?\s*(?P<year>(?:19|20)\d{2}[a-z]?)"
)
_CURRENT_SOURCE_ASSERTION = re.compile(
    r"(?ix)\b(?:in\s+this\s+(?:study|work|paper)|the\s+present\s+(?:study|work)|"
    r"we\s+(?:observed|found|report(?:ed)?|measured)|our\s+(?:results?|study|work)|"
    r"this\s+work)\b"
)
_TENSILE_COMPARATOR_RELATION = re.compile(
    r"(?ix)(?:"
    r"\b(?:comparable|similar)\s+to\s+(?:those|that)\s+of\b|"
    r"\b(?:compared|relative)\s+(?:to|with|against)\b|"
    r"\b(?:higher|lower|greater|less)\s+than\b"
    r")"
)
_TENSILE_COMPARATOR_MATERIAL = re.compile(
    r"(?ix)\b(?:"
    r"alloys?|materials?|samples?|specimens?|parts?|rods?|walls?|"
    r"conditions?|states?|cast|wrought|forged|rolled|conventional(?:ly)?|"
    r"literature|reference"
    r")\b"
)
_TENSILE_EXTERNAL_SUBJECT_QUALIFIER = re.compile(
    r"(?ix)\b(?:as[\s-]*)?"
    r"(?:cast|wrought|forged|rolled|conventional(?:ly)?\s+manufactured)\s*$"
)
_TENSILE_DIRECT_AUTHOR_ATTRIBUTION = re.compile(
    r"(?ix)(?<![a-z])"
    r"(?P<author>[a-z][a-zà-öø-ÿ'’.-]{1,}\s+et\s+al\.?)\s+"
    r"(?P<reporting>reported|presented|showed|found|measured|observed|"
    r"demonstrated|documented)\b"
)
_TENSILE_ATTRIBUTED_PROPERTY_SUBJECT = re.compile(
    r"(?ix)\b(?:"
    r"ultimate\s+tensile\s+strengths?|uts|"
    r"yield\s+(?:strengths?|stress(?:es)?)|"
    r"(?:total\s+|uniform\s+|fracture\s+)?elongations?|ductilit(?:y|ies)"
    r")\s+of\s+(?P<subject>.+?)\s+"
    r"(?:is|are|was|were|reaches?|reached|averages?|averaged|equals?|equalled)"
    r"\s+(?:approximately|about|around|roughly|nearly|only)?\s*$"
)
_TENSILE_SENTENCE_BOUNDARY = re.compile(
    r"(?ix)(?<!et\sal\.)(?<=[.!?;])\s+|\n+"
)


@dataclass(frozen=True)
class _TensileValueScope:
    matched_source_sentence: str
    value_local_proposition: str
    normalized_proposition: str
    value_start: int


@dataclass(frozen=True)
class _TensileExternalSubjectDecision:
    matched_source_sentence: str
    value_local_proposition: str
    external_subject: str
    subject_cue: str
    embedded_owner_literal: str | None
    reason: Literal[
        "cited_subject", "comparator_relation", "direct_author_attribution"
    ]


def _tensile_numeric_matches(
    value: Any,
) -> tuple[str, tuple[tuple[str, int, int], ...]]:
    """Return source-stable tensile number tokens and their normalized spans."""

    normalized = _identity_text(value)
    # A range dash is a separator, not the sign of the upper bound. Replacing
    # it with one space preserves character offsets for the audit window.
    normalized = re.sub(r"(?<=\d)[-–—~](?=\d)", " ", normalized)
    matches = tuple(
        (
            match.group(0).lstrip("+"),
            match.start(),
            match.end(),
        )
        for match in re.finditer(
            r"(?<![a-z0-9])[-+]?\d+(?:\.\d+)?(?:e[-+]?\d+)?",
            normalized,
        )
    )
    return normalized, matches


def _tensile_value_sequence_starts(
    text: Any,
    expected: Sequence[str],
) -> tuple[int, ...]:
    if not expected:
        return ()
    _, matches = _tensile_numeric_matches(text)
    tokens = tuple(row[0] for row in matches)
    width = len(expected)
    return tuple(
        matches[index][1]
        for index in range(0, len(tokens) - width + 1)
        if tokens[index : index + width] == tuple(expected)
    )


def _tensile_value_local_scope(
    fact: PropertyFact,
    evidence: Sequence[str],
) -> _TensileValueScope | None:
    """Resolve one complete tensile value to one sentence and one clause.

    The fail-closed uniqueness rule matters when a sentence reports both the
    current and comparator result. A repeated identical value is deliberately
    left to the established owner gates instead of being assigned by order.
    """

    _, value_matches = _tensile_numeric_matches(fact.data.get("value_raw"))
    expected = tuple(row[0] for row in value_matches)
    if not expected:
        return None
    scopes: list[_TensileValueScope] = []
    for evidence_row in evidence:
        for raw_sentence in _TENSILE_SENTENCE_BOUNDARY.split(
            str(evidence_row or "")
        ):
            sentence = raw_sentence.strip()
            if not sentence:
                continue
            sentence_starts = _tensile_value_sequence_starts(sentence, expected)
            if len(sentence_starts) != 1:
                continue
            clauses = [
                row.strip()
                for row in re.split(r",\s+(?=[A-Za-z])", sentence)
                if row.strip()
            ]
            matching_clauses = [
                clause
                for clause in clauses
                if len(_tensile_value_sequence_starts(clause, expected)) == 1
            ]
            proposition = (
                matching_clauses[0]
                if len(matching_clauses) == 1
                else sentence
            ).strip().rstrip(".;")
            normalized, _ = _tensile_numeric_matches(proposition)
            starts = _tensile_value_sequence_starts(proposition, expected)
            if len(starts) != 1:
                continue
            scopes.append(
                _TensileValueScope(
                    matched_source_sentence=sentence.rstrip(".;"),
                    value_local_proposition=proposition,
                    normalized_proposition=normalized,
                    value_start=starts[0],
                )
            )
    unique = list(
        {
            (
                row.matched_source_sentence,
                row.value_local_proposition,
                row.normalized_proposition,
                row.value_start,
            ): row
            for row in scopes
        }.values()
    )
    return unique[0] if len(unique) == 1 else None


def _literal_alias_spans(value: str, alias: str) -> tuple[tuple[int, int], ...]:
    normalized_alias = _identity_text(alias)
    if not normalized_alias:
        return ()
    return tuple(
        (match.start(), match.end())
        for match in re.finditer(
            rf"(?<!\w){re.escape(normalized_alias)}(?!\w)",
            value,
        )
    )


def _tensile_external_subject_decision(
    fact: PropertyFact,
    evidence: Sequence[str],
    owner_nodes: Sequence[OwnerNode],
) -> _TensileExternalSubjectDecision | None:
    """Prove that one numeric tensile value belongs to a comparator subject."""

    scope = _tensile_value_local_scope(fact, evidence)
    if scope is None:
        return None
    proposition = scope.normalized_proposition
    current_nodes = [
        node
        for node in owner_nodes
        if node.role == "Target" and node.data_nature == "Experimental"
    ]
    current_aliases = tuple(
        dict.fromkeys(
            alias
            for node in current_nodes
            for alias in node.aliases
            if _distinctive_owner_label(alias)
        )
    )
    subject_aliases = current_aliases or tuple(
        alias
        for alias in _owner_evidence_aliases(fact.sample_id_raw)
        if _distinctive_owner_label(alias)
    )

    # A named prior author can own a value without a bracket citation in the
    # cropped model evidence.  Require the author, reporting verb, tensile
    # property, comparator material subject, and complete value to occur in
    # the same value-local proposition.  This covers source grammar such as
    # ``Yan et al. presented that the yield stress of high-Nb TiAl alloys is
    # approximately 900 MPa`` without treating a bare plural ``alloys`` as a
    # current-paper collective result.
    if _CURRENT_SOURCE_ASSERTION.search(proposition) is None:
        attribution = _TENSILE_DIRECT_AUTHOR_ATTRIBUTION.search(
            proposition, 0, scope.value_start
        )
        if attribution is not None:
            attributed_tail = proposition[
                attribution.end() : scope.value_start
            ].strip()
            attributed_tail = re.sub(r"(?ix)^that\s+", "", attributed_tail)
            subject_match = _TENSILE_ATTRIBUTED_PROPERTY_SUBJECT.search(
                attributed_tail
            )
            if subject_match is not None:
                subject = subject_match.group("subject").strip(" \t(:;,-~")
                if subject and _TENSILE_COMPARATOR_MATERIAL.search(subject):
                    embedded_alias = next(
                        (
                            _identity_text(alias)
                            for alias in sorted(
                                current_aliases,
                                key=lambda row: (-len(row), row.casefold()),
                            )
                            if _literal_mention(subject, alias)
                        ),
                        None,
                    )
                    return _TensileExternalSubjectDecision(
                        matched_source_sentence=scope.matched_source_sentence,
                        value_local_proposition=scope.value_local_proposition,
                        external_subject=subject,
                        subject_cue=(
                            f"{attribution.group('author')} "
                            f"{attribution.group('reporting')}"
                        ),
                        embedded_owner_literal=embedded_alias,
                        reason="direct_author_attribution",
                    )

    # A citation attached directly to a material noun phrase owns that subject.
    # In ``cast alloy 625 [11]``, the current alias ``alloy 625`` is therefore
    # only an embedded substring and cannot rescue the literature value.
    for alias in sorted(subject_aliases, key=lambda row: (-len(row), row.casefold())):
        for start, end in _literal_alias_spans(proposition, alias):
            citation = re.match(
                r"\s*(?P<cue>\[\s*\d+(?:\s*[,;]\s*\d+)*\s*\])",
                proposition[end:],
            )
            if citation is None:
                continue
            subject_start = start
            qualifier = _TENSILE_EXTERNAL_SUBJECT_QUALIFIER.search(
                proposition[:start]
            )
            if qualifier is not None:
                subject_start = qualifier.start()
            subject_end = end + citation.end()
            embedded = (
                _identity_text(alias)
                if any(
                    _literal_mention(alias, current_alias)
                    for current_alias in current_aliases
                )
                else None
            )
            return _TensileExternalSubjectDecision(
                matched_source_sentence=scope.matched_source_sentence,
                value_local_proposition=scope.value_local_proposition,
                external_subject=proposition[subject_start:subject_end].strip(),
                subject_cue=citation.group("cue"),
                embedded_owner_literal=embedded,
                reason="cited_subject",
            )

    comparator_matches = [
        match
        for match in _TENSILE_COMPARATOR_RELATION.finditer(proposition)
        if match.end() <= scope.value_start
    ]
    if not comparator_matches:
        return None
    comparator = comparator_matches[-1]
    subject = proposition[comparator.end() : scope.value_start].strip(" \t(:;,-")
    subject = re.sub(r"(?ix)^(?:those|that)\s+of\s+", "", subject)
    subject = re.sub(
        r"(?ix)\s+\b(?:at|of|with|having|showing|was|were|is|had)\s*$",
        "",
        subject,
    ).strip(" \t(:;,-~")
    if not subject or not _TENSILE_COMPARATOR_MATERIAL.search(subject):
        return None
    embedded_alias = next(
        (
            _identity_text(alias)
            for alias in sorted(
                current_aliases, key=lambda row: (-len(row), row.casefold())
            )
            if _literal_mention(subject, alias)
        ),
        None,
    )
    # If the comparator subject is literally the current owner, it is external
    # only when the subject itself carries a citation. A bare comparison to the
    # same current item remains a no-op because no Reference coordinate exists.
    if (
        embedded_alias is not None
        and _EXTERNAL_SOURCE_ASSERTION.search(subject) is None
    ):
        return None
    return _TensileExternalSubjectDecision(
        matched_source_sentence=scope.matched_source_sentence,
        value_local_proposition=scope.value_local_proposition,
        external_subject=subject,
        subject_cue=comparator.group(0),
        embedded_owner_literal=embedded_alias,
        reason="comparator_relation",
    )


def _external_reference_author_keys(value: Any) -> set[str]:
    """Return literal ``Author et al.`` keys without bibliography lookup."""

    return {
        _identity_text(match.group("author"))
        for match in _EXTERNAL_REFERENCE_AUTHOR.finditer(str(value or ""))
        if _identity_text(match.group("author"))
    }


def _external_reference_author_year_keys(value: Any) -> set[tuple[str, str]]:
    """Return exact local author-year markers such as ``Marchese et al., 2018``."""

    return {
        (
            _identity_text(match.group("author")),
            str(match.group("year")).casefold(),
        )
        for match in _EXTERNAL_REFERENCE_AUTHOR_YEAR.finditer(str(value or ""))
        if _identity_text(match.group("author"))
    }


def _direct_author_reference_anchor_supports_fact(
    fact: PropertyFact,
    evidence: Sequence[str],
    reference: OwnerNode,
) -> bool:
    """Prove one cited tensile fact belongs to one existing Reference anchor.

    Upstream extraction often emits a rich reference label such as
    ``binder jetting as-sintered (Mostafaei et al., 2016b)`` while quoting only
    ``Mostafaei et al. reported ...`` in the Property evidence. Requiring the
    complete rich label verbatim loses that valid coordinate. This exception
    remains fail-closed: the value sentence must contain one reporting author,
    that author must be present in the already-declared Reference anchor, and
    the anchor must carry the same literal source sentence (allowing only a
    cropped prefix/suffix projection).
    """

    if not (
        reference.role == "Reference"
        or str(reference.data_nature).startswith("Literature_")
    ):
        return False
    anchor_authors = _external_reference_author_keys(
        "\n".join([reference.sample_id_raw, *reference.source_evidence])
    )
    if not anchor_authors:
        return False
    anchor_evidence = [
        _identity_text(row)
        for row in reference.source_evidence
        if len(_identity_text(row)) >= 24
    ]
    if not anchor_evidence:
        return False
    value_numbers = set(_numeric_tokens(fact.data.get("value_raw")))
    if not value_numbers:
        return False
    for evidence_row in evidence:
        row_text = str(evidence_row)
        windows = list(
            dict.fromkeys(
                [
                    row_text,
                    *re.split(r"(?<=[.!?;])\s+|\n+", row_text),
                ]
            )
        )
        for sentence in windows:
            if not value_numbers.intersection(_numeric_tokens(sentence)):
                continue
            authors = _external_reference_author_keys(sentence)
            if len(authors) != 1 or authors != anchor_authors:
                continue
            author = _EXTERNAL_REFERENCE_AUTHOR.search(sentence)
            reporting = (
                _EXTERNAL_REPORTING_CUE.search(sentence, author.end())
                if author is not None
                else None
            )
            if (
                reporting is None
                or author is None
                or author.start() >= reporting.start()
                or _CURRENT_SOURCE_ASSERTION.search(sentence)
            ):
                continue
            normalized_sentence = _identity_text(sentence)
            if len(normalized_sentence) < 24:
                continue
            if any(
                normalized_sentence in source or source in normalized_sentence
                for source in anchor_evidence
            ):
                return True
    return False


def _literal_author_year_reference_anchor_supports_fact(
    fact: PropertyFact,
    evidence: Sequence[str],
    reference: OwnerNode,
) -> bool:
    """Accept a value-local author-year citation only for its exact Reference."""

    anchor_markers = _external_reference_author_year_keys(reference.sample_id_raw)
    if len(anchor_markers) != 1:
        return False
    anchor_evidence = [
        _identity_text(row)
        for row in reference.source_evidence
        if len(_identity_text(row)) >= 16
    ]
    value_numbers = set(_numeric_tokens(fact.data.get("value_raw")))
    if not anchor_evidence or not value_numbers:
        return False
    for row in evidence:
        if not value_numbers.intersection(_numeric_tokens(row)):
            continue
        if _CURRENT_SOURCE_ASSERTION.search(str(row)):
            continue
        if _external_reference_author_year_keys(row) != anchor_markers:
            continue
        normalized = _identity_text(row)
        if len(normalized) < 16:
            continue
        if any(
            normalized in source or source in normalized
            for source in anchor_evidence
        ):
            return True
    return False
_CONDITION_DISCRIMINATOR_CUE = re.compile(
    r"(?ix)(?:"
    r"\b(?:delay|temperature|temperatures|orientation|oriented|direction|"
    r"state|condition|aged|ageing|aging|heat[\s-]*treat(?:ed|ment)?|"
    r"as[\s-]*built|as[\s-]*printed|build[\s-]*height|"
    r"layer|wall|region|location|position|plane|axis)\b|"
    r"(?:°\s*C|\bK\b|\b(?:s|sec|seconds?|min|minutes?|h|hours?)\b|%)"
    r")"
)

# ``test_condition_raw`` is frequently populated by the extractor with the
# complete tensile-method paragraph (specimen dimensions, machine model,
# polishing steps, repetition count, etc.).  Those details are source
# evidence, but they are not the coordinate of the reported Property.  The
# promotion layer may retain only compact, source-literal coordinates below;
# it never synthesizes a condition from a neighbouring sentence/chunk.
_CONDITION_METHOD_NOISE = re.compile(
    r"(?ix)\b(?:"
    r"dog[\s-]*bone|specimen(?:s)?|gauge\s+(?:length|width|thickness|dimension)|"
    r"universal\s+testing\s+machine|testing\s+machine|instron|"
    r"digital\s+image\s+correlation|extensometer|"
    r"repeated?|reproducible|at\s+least\s+\d+\s+samples?|"
    r"polish(?:ed|ing)?|machin(?:ed|ing)|electrical\s+discharg(?:e|ing)|"
    r"fabricated?\s+(?:using|by)|extracted\s+from|shown\s+in\s+(?:fig|figure)|"
    r"standard|astm|iso|equipment|device|software|camera|manufacturer|"
    r"utili[sz](?:ed|ing)|measured\s+using|performed\s+on"
    r")\b"
)
_CONDITION_COORDINATE_FRAGMENT = re.compile(
    r"(?ix)(?:"
    # Explicit preparation/state labels.  These are intentionally lexical;
    # the owner router still requires a matching source-declared state.
    r"\b(?:as[\s-]*(?:built|printed|fabricated|deposited)|"
    r"hip(?:ed|ped)?(?:\s*\d+)?|ht\s*\d+|"
    r"anneal(?:ed|ing)?|aged?|ageing|solution[\s-]*treated?|"
    r"heat[\s-]*treated?|sinter(?:ed|ing)?|wa|ga|"
    r"(?:horizontal|vertical|transverse|longitudinal)\s+direction|"
    r"build(?:ing)?\s+direction|parallel\s+to\s+[^,.;]+|"
    r"perpendicular\s+to\s+[^,.;]+)\b"
    r"|\b(?:\d+(?:\.\d+)?|\.\d+)\s*(?:s|sec(?:onds?)?|min(?:utes?)?|"
    r"h(?:ours?)?)\s*delay\b"
    r"|\bdelay\s*(?:of|=|:)\s*(?:\d+(?:\.\d+)?|\.\d+)\s*"
    r"(?:s|sec(?:onds?)?|min(?:utes?)?|h(?:ours?))\b"
    r"|\b(?:at|under|tested?\s+at|temperature\s*(?:of|=|:)?)\s*"
    r"[-+]?\d+(?:\.\d+)?\s*(?:°\s*C|°C|K)\b"
    r"|\b(?:strain|stress|loading|crosshead)\s+rate\s*(?:of|=|:)\s*"
    r"[-+]?\d+(?:\.\d+)?(?:\s*[×x]\s*10\s*\^?\s*[-+]?\d+)?\s*"
    r"(?:s\s*\^?\s*[-+]?\s*1|1\s*/\s*s|%\s*/\s*s)\b"
    r"|\b(?:stress|strain)\s+ratio\s*(?:of|=|:)\s*[-+]?\d+(?:\.\d+)?\b"
    r")"
)

# Presentation locators prove where a result appeared, not the scientific
# coordinate under which it was measured.  Keep the expression deliberately
# identifier-bound so words such as ``table temperature`` or ``figure of
# merit`` are not removed as locators.
_CONDITION_PROVENANCE_LOCATOR_V205 = re.compile(
    r"(?ix)\b(?:supp(?:lementary)?\.?\s*)?"
    r"(?:table|fig(?:ure)?\.?|page|section|appendix)\s*"
    r"(?:[A-Z]?\d+(?:[.\-]\d+)*(?:[a-z])?|[IVXLC]+)\b"
)
_CONDITION_PROVENANCE_GLUE_V205 = re.compile(
    r"(?ix)(?:\b(?:as\s+)?(?:shown|reported|listed|given|summari[sz]ed|"
    r"presented|provided)\s+(?:in|by|from)\s*$|\b(?:see|cf\.)\s*$)"
)
_SCIENTIFIC_CONDITION_CUE_V205 = re.compile(
    r"(?ix)(?:"
    r"\b(?:temperature|ambient|cryogenic|vacuum|air|argon|inert|"
    r"orientation|oriented|direction|parallel|perpendicular|state|"
    r"condition|delay|aged|ageing|aging|annealed|heat[\s-]*treated|"
    r"as[\s-]*(?:built|printed|fabricated|deposited)|strain\s+rate|"
    r"stress\s+rate|loading\s+rate|crosshead\s+(?:rate|speed)|"
    r"tension|compression|fatigue|creep)\b|"
    r"(?:°\s*C|\bK\b|\bs\s*\^?\s*-?1\b|\b1\s*/\s*s\b)"
    r")"
)


def _scientific_fold(value: Any) -> str:
    text = str(value or "")
    text = text.replace("γ′", " gamma prime ").replace("γ'", " gamma prime ")
    greek = {
        "γ": " gamma ",
        "α": " alpha ",
        "β": " beta ",
        "σ": " sigma ",
        "δ": " delta ",
        "η": " eta ",
    }
    for source, target in greek.items():
        text = text.replace(source, target)
    text = re.sub(
        r"\\(?:gamma|alpha|beta|sigma|delta|eta)\s*'?",
        lambda match: (
            " "
            + match.group(0).lstrip("\\").replace("'", " prime ")
            + " "
        ),
        text,
        flags=re.IGNORECASE,
    )
    text = re.sub(
        r"\\(?:mathrm|text|mathbf|mathit)\s*\{([^{}]*)\}",
        r" \1 ",
        text,
    )
    text = re.sub(r"[_^]\s*\{([^{}]*)\}", r" \1 ", text)
    text = text.replace("µ", "μ")
    text = normalize_evidence_text(text)
    return re.sub(r"[^a-z0-9μ°%]+", " ", text).strip()


def _scientific_compact(value: Any) -> str:
    return re.sub(r"[^a-z0-9μ%]+", "", _scientific_fold(value))


def _numeric_tokens(value: Any) -> tuple[str, ...]:
    return tuple(
        match.group(0).lstrip("+")
        for match in re.finditer(
            r"(?<![a-z0-9])[-+]?\d+(?:\.\d+)?(?:e[-+]?\d+)?",
            _scientific_fold(value),
        )
    )


def _tensile_unit_key(value: Any) -> str:
    """Normalize only source physical units used by tensile conflict checks."""

    text = str(value or "").strip().casefold().replace(" ", "")
    aliases = {
        "gpa": "gpa",
        "mpa": "mpa",
        "kpa": "kpa",
        "pa": "pa",
    }
    return aliases.get(text, text)


def _source_units_next_to_value(value: Any, evidence: Sequence[str]) -> tuple[str, ...]:
    """Return units written immediately after a numeric value in source text.

    The evidence often contains a complete table or a method paragraph.  A
    bare unit anywhere in that text is not enough to override the candidate's
    unit, so only a number followed directly by a strength unit is considered.
    This catches the dangerous ``0.33 GPa`` -> ``unit_raw=MPa`` projection while
    leaving unrelated protocol units untouched.
    """

    raw_numbers = tuple(
        match.group(0).lstrip("+")
        for match in re.finditer(
            r"(?<![a-z0-9])[-+]?\d+(?:\.\d+)?(?:e[-+]?\d+)?",
            str(value or "").casefold(),
        )
    )
    numbers = _numeric_tokens(value)
    if not raw_numbers and not numbers:
        return ()
    units: list[str] = []
    number_pattern = re.compile(
        r"(?<![a-z0-9])(?P<number>[-+]?\d+(?:\.\d+)?(?:e[-+]?\d+)?)"
        r"\s*(?:\\(?:mathrm|text)\s*\{\s*)?"
        r"(?P<unit>GPa|MPa|kPa|Pa)(?![a-z0-9])",
        flags=re.IGNORECASE,
    )
    wanted = set(raw_numbers) | set(numbers)
    for row in evidence:
        for match in number_pattern.finditer(str(row or "")):
            number = match.group("number").lstrip("+").casefold()
            if number in wanted:
                units.append(_tensile_unit_key(match.group("unit")))
    return tuple(dict.fromkeys(units))


# Source-local unit binding for non-tensile numeric axes.  This is intentionally
# narrower than a general unit converter: it only asks whether the unit written
# immediately after the quoted number agrees with the structured ``unit_raw``.
# A mismatch is quarantined, never silently converted, because changing 50 µm
# to 50 mm (or 40 kV to 40 V) changes the scientific value by orders of
# magnitude.
_SOURCE_NUMERIC_UNIT = re.compile(
    r"(?<![a-z0-9])(?P<number>[-+]?\d+(?:\.\d+)?(?:e[-+]?\d+)?)\s*"
    r"(?:\\(?:mathrm|text)\s*\{\s*)?"
    r"(?P<unit>"
    r"mm\s*/\s*(?:min|s)|m\s*/\s*s|µm|μm|\\mu\s*m|um|nm|cm|"
    r"mm|km|m|ppm|ppb|vol\.?\s*%|wt\.?\s*%|at\.?\s*%|mol\.?\s*%|"
    r"%|°\s*C|deg\.?\s*C|K|GPa|MPa|kPa|Pa|W|kW|A|mA|V|kV|Hz|"
    r"J\s*/\s*mm(?:\s*\^?\s*[123²³])?|r\s*/\s*min|cycles?"
    r")\b",
    flags=re.IGNORECASE,
)


def _generic_unit_key(value: Any) -> str:
    text = str(value or "").strip().casefold()
    text = text.replace("μ", "µ")
    text = re.sub(r"\\(?:mathrm|text)\s*\{([^{}]*)\}", r"\1", text)
    text = re.sub(r"\\mu\s*", "µ", text)
    text = re.sub(r"\s+", "", text)
    aliases = {
        "micron": "um",
        "microns": "um",
        "µm": "um",
        "um": "um",
        "µm^2": "um2",
        "mm/min": "mm/min",
        "mm/s": "mm/s",
        "m/s": "m/s",
        "degc": "degc",
        "°c": "degc",
        "degreec": "degc",
        "degreesc": "degc",
        "wt.%": "wt%",
        "at.%": "at%",
        "vol.%": "vol%",
        "mol.%": "mol%",
        "j/mm²": "j/mm2",
        "j/mm³": "j/mm3",
        "j/mm^2": "j/mm2",
        "j/mm^3": "j/mm3",
        "r/min": "r/min",
    }
    if text in aliases:
        return aliases[text]
    # ``mm (0.045 in)`` and similar contract values still have a clear first
    # physical unit; use only that token for the source mismatch check.
    match = _SOURCE_NUMERIC_UNIT.search("1 " + text)
    if match:
        token = match.group("unit").casefold().replace("μ", "µ")
        token = re.sub(r"\s+", "", token)
        return aliases.get(token, token)
    return re.sub(r"[^a-z0-9µ°/%]+", "", text)


def _source_units_next_to_value_generic(
    value: Any,
    evidence: Sequence[str],
) -> tuple[str, ...]:
    def number_key(raw: Any) -> str:
        text = str(raw or "").strip().lstrip("+")
        try:
            # Candidate values frequently normalize ``1.0`` to ``1`` (the
            # extraction schema stores numeric tokens without preserving
            # presentation precision).  Compare the numeric identity rather
            # than the original decimal spelling so a source-local ``1.0
            # GPa`` still binds to a candidate value ``1``/``1.0``.
            return format(float(text), ".15g")
        except ValueError:
            return text.casefold()

    # Use the raw value spelling here instead of ``_numeric_tokens``.  The
    # latter is intentionally used for semantic matching and may split a
    # decimal into ``("0", "33")`` after scientific normalization; source
    # unit binding needs the complete literal ``0.33``.
    raw_value_numbers = re.findall(
        r"(?<![A-Za-z0-9])[-+]?\d+(?:\.\d+)?(?:e[-+]?\d+)?",
        str(value or ""),
        flags=re.IGNORECASE,
    )
    numbers = {number_key(token) for token in raw_value_numbers}
    if not numbers:
        numbers = {number_key(token) for token in _numeric_tokens(value)}
    if not numbers:
        return ()
    found: list[str] = []
    for row in evidence:
        for match in _SOURCE_NUMERIC_UNIT.finditer(str(row or "")):
            if number_key(match.group("number")) not in numbers:
                continue
            found.append(_generic_unit_key(match.group("unit")))
    return tuple(dict.fromkeys(unit for unit in found if unit))


def _source_unit_conflict(
    fact: AxisFact,
    *,
    value: Any,
    declared_unit: Any,
) -> tuple[bool, dict[str, Any]]:
    declared = _generic_unit_key(declared_unit)
    if not declared or declared in {"unknown", "notreported", "n a"}:
        return False, {}
    source_units = _source_units_next_to_value_generic(value, _fact_evidence(fact))
    if not source_units or declared in source_units or len(source_units) != 1:
        return False, {
            "declared_unit": declared,
            "source_units": list(source_units),
        }
    return True, {
        "declared_unit": declared,
        "source_units": list(source_units),
        "value_raw": str(value or ""),
        "reason": "source_literal_unit_disagrees_with_unit_raw",
    }


def _tensile_source_unit_conflict(fact: PropertyFact) -> tuple[bool, dict[str, Any]]:
    """Detect a source-literal unit that disagrees with ``unit_raw``."""

    declared = _tensile_unit_key(fact.data.get("unit_raw"))
    if not declared or declared in _UNREPORTED:
        return False, {}
    value_raw = str(fact.data.get("value_raw") or "")
    embedded = tuple(
        dict.fromkeys(
            _tensile_unit_key(match.group(0))
            for match in _TENSILE_SOURCE_VALUE_UNIT.finditer(value_raw)
        )
    )
    source_units = embedded or _source_units_next_to_value(
        value_raw, _fact_evidence(fact)
    )
    if not source_units or all(unit == declared for unit in source_units):
        return False, {
            "declared_unit": declared,
            "source_units": list(source_units),
            "value_raw": value_raw,
        }
    return True, {
        "declared_unit": declared,
        "source_units": list(source_units),
        "value_raw": value_raw,
        "reason": "source_literal_unit_disagrees_with_unit_raw",
    }


def _payload_grounded(value: Any, evidence: Sequence[str]) -> bool:
    candidate = _scientific_compact(value)
    if not candidate or _scientific_fold(value) in _UNREPORTED:
        return False
    joined = "\n".join(evidence)
    source = _scientific_compact(joined)
    numbers = _numeric_tokens(value)
    if numbers:
        # Do not use compact substring matching for numeric payloads.  Without
        # token boundaries, ``0 s delay`` incorrectly matches the trailing
        # ``0`` in ``300 s delay`` and can route a fact to the wrong state.
        source_numbers = _numeric_tokens(joined)
        if not all(number in source_numbers for number in numbers):
            return False
        lexical = [
            word
            for word in _scientific_fold(value).split()
            if len(word) > 2 and word not in {"the", "and", "with", "from", "that"}
        ]
        source_words = set(_scientific_fold(joined).split())
        if not lexical:
            return True
        # Permit singular/plural OCR variation (``delay``/``delays``) while
        # still requiring the condition words to be source-grounded.
        return all(
            word in source_words
            or (word.endswith("s") and word[:-1] in source_words)
            or (word + "s") in source_words
            for word in lexical
        )
    if candidate in source:
        return True
    words = [
        word
        for word in _scientific_fold(value).split()
        if len(word) > 2 and word not in {"the", "and", "with", "from", "that"}
    ]
    source_words = set(_scientific_fold(joined).split())
    return bool(words) and len(words) >= 3 and (
        sum(word in source_words for word in words) / len(words) >= 0.85
    )


def _fact_evidence(fact: AxisFact) -> list[str]:
    rows = [str(row).strip() for row in fact.source_evidence if str(row).strip()]
    nested = fact.data.get("source_evidence")
    if isinstance(nested, str):
        nested = [nested]
    if isinstance(nested, Sequence) and not isinstance(nested, (str, bytes)):
        rows.extend(str(row).strip() for row in nested if str(row).strip())
    return list(dict.fromkeys(rows))


def _promotion_issue(
    fact: AxisFact,
    *,
    code: str,
    message: str,
    actual: Any,
    expected: Any,
    evidence: Any | None = None,
    severity: str = "review",
    suggested_action: str = "Review the preserved candidate against its cited evidence.",
) -> PromotionIssue:
    return PromotionIssue(
        code=code,
        sample_id_raw=fact.sample_id_raw,
        message=message,
        severity=severity,
        evidence=_fact_evidence(fact) if evidence is None else evidence,
        expected=expected,
        actual=actual,
        suggested_action=suggested_action,
    )


def _quarantine_source_numeric_unit_conflicts(
    facts: Sequence[AxisFact],
) -> tuple[list[AxisFact], list[PromotionIssue]]:
    """Isolate numeric fields with a source-unit mismatch.

    The extractor frequently preserves the number but corrupts the unit (for
    example ``50 µm`` becoming ``unit_raw=mm``).  This pass checks only the
    number immediately followed by a unique source unit in the candidate's own
    evidence.  It never converts values and never borrows units from a
    neighboring chunk.  Composition and core tensile remain on their dedicated
    gates because their unit contracts have additional domain semantics; other
    Property values use the same generic source-local check below.
    """

    accepted: list[AxisFact] = []
    issues: list[PromotionIssue] = []
    for fact in facts:
        if isinstance(fact, ProcessingFact):
            data = deepcopy(fact.data)
            removed: list[dict[str, Any]] = []
            kept: list[dict[str, Any]] = []
            for parameter in data.get("parameters_raw") or []:
                if not isinstance(parameter, dict):
                    continue
                value = parameter.get("value_raw")
                unit = parameter.get("unit_raw")
                evidence = _feature_evidence(parameter, _fact_evidence(fact))
                conflict, details = _source_unit_conflict(
                    fact, value=value, declared_unit=unit
                )
                # Re-run against the nested evidence when available; the
                # helper above is intentionally fact-level for stable audit
                # paths, while a nested quote is the strongest local binding.
                if conflict and evidence != _fact_evidence(fact):
                    nested_units = _source_units_next_to_value_generic(value, evidence)
                    declared = _generic_unit_key(unit)
                    conflict = bool(
                        nested_units
                        and len(nested_units) == 1
                        and declared
                        and declared not in {"unknown", "notreported", "n a"}
                        and declared not in nested_units
                    )
                    details = {
                        "declared_unit": declared,
                        "source_units": list(nested_units),
                        "value_raw": str(value or ""),
                        "reason": "source_literal_unit_disagrees_with_unit_raw",
                    }
                if conflict:
                    removed.append({"parameter": deepcopy(parameter), **details})
                else:
                    kept.append(parameter)
            if removed:
                data["parameters_raw"] = kept
                after = fact.model_copy(deep=True, update={"data": data})
                # A process-stage event can survive with its bad parameter
                # removed; a parameter-only record with no remaining payload is
                # isolated entirely by the normal materializer contract.
                if kept or fact.fact_type != "process_stage":
                    accepted.append(after)
                for row in removed:
                    issues.append(
                        _promotion_issue(
                            fact,
                            code="promotion_source_unit_conflict_quarantined",
                            message=(
                                "A Processing numeric field used a unit that did "
                                "not match the unique source-literal unit next to "
                                "the quoted value; the field was isolated without "
                                "conversion."
                            ),
                            expected={
                                "source_literal_unit_matches_unit_raw": True,
                                "conversion": False,
                                "audit_preserved": True,
                            },
                            actual={
                                "removed": row["parameter"],
                                "before": fact.model_dump(),
                                "after": after.model_dump(),
                                **{
                                    key: value
                                    for key, value in row.items()
                                    if key != "parameter"
                                },
                            },
                            evidence=_feature_evidence(
                                row["parameter"], _fact_evidence(fact)
                            ),
                        )
                    )
                continue
            accepted.append(fact)
            continue

        if isinstance(fact, StructureFact) and fact.fact_type == "structure_observation":
            data = deepcopy(fact.data)
            removed: list[dict[str, Any]] = []

            def keep_feature(feature: dict[str, Any], *, owner: str) -> bool:
                value = feature.get("value_raw")
                unit = feature.get("unit_raw")
                evidence = _feature_evidence(feature, _fact_evidence(fact))
                conflict, details = _source_unit_conflict(
                    fact, value=value, declared_unit=unit
                )
                if conflict and evidence != _fact_evidence(fact):
                    nested_units = _source_units_next_to_value_generic(value, evidence)
                    declared = _generic_unit_key(unit)
                    conflict = bool(
                        nested_units
                        and len(nested_units) == 1
                        and declared
                        and declared not in {"unknown", "notreported", "n a"}
                        and declared not in nested_units
                    )
                    details = {
                        "declared_unit": declared,
                        "source_units": list(nested_units),
                        "value_raw": str(value or ""),
                        "reason": "source_literal_unit_disagrees_with_unit_raw",
                    }
                if not conflict:
                    return True
                removed.append(
                    {
                        "feature": deepcopy(feature),
                        "owner": owner,
                        "evidence": evidence,
                        **details,
                    }
                )
                return False

            entities: list[dict[str, Any]] = []
            for entity in data.get("entities") or []:
                if not isinstance(entity, dict):
                    continue
                cleaned = deepcopy(entity)
                owner = str(entity.get("name_raw") or entity.get("raw_expression") or "")
                cleaned["features"] = [
                    feature
                    for feature in entity.get("features") or []
                    if isinstance(feature, dict) and keep_feature(feature, owner=owner)
                ]
                entities.append(cleaned)
            data["entities"] = entities
            data["features"] = [
                feature
                for feature in data.get("features") or []
                if isinstance(feature, dict) and keep_feature(feature, owner="")
            ]
            if removed:
                after = fact.model_copy(deep=True, update={"data": data})
                if data["entities"] or data["features"]:
                    accepted.append(after)
                for row in removed:
                    issues.append(
                        _promotion_issue(
                            fact,
                            code="promotion_source_unit_conflict_quarantined",
                            message=(
                                "A Structure numeric feature used a unit that did "
                                "not match the unique source-literal unit next to "
                                "the quoted value; the feature was isolated without "
                                "conversion."
                            ),
                            expected={
                                "source_literal_unit_matches_unit_raw": True,
                                "conversion": False,
                                "audit_preserved": True,
                            },
                            actual={
                                "removed": row["feature"],
                                "owner": row["owner"],
                                "before": fact.model_dump(),
                                "after": after.model_dump(),
                                "declared_unit": row.get("declared_unit"),
                                "source_units": row.get("source_units", []),
                            },
                            evidence=row["evidence"],
                        )
                    )
                continue

        # Non-tensile Properties use the same source-local unit contract as
        # Processing and Structure.  The dedicated tensile gate above owns
        # core tensile units because it also handles MPa/GPa canonicalization;
        # applying this generic branch to those facts would duplicate the
        # audit row and could race that domain-specific decision.  For every
        # other numeric Property, however, a unique unit written immediately
        # after the quoted value is a hard provenance check.  A mismatch is
        # isolated rather than silently converted (for example ``1.0 GPa``
        # paired with ``unit_raw=MPa``).
        if isinstance(fact, PropertyFact) and not is_core_tensile_property_name(
            fact.data.get("property_name_raw")
        ):
            declared = _generic_unit_key(fact.data.get("unit_raw"))
            if declared and declared not in {"unknown", "notreported", "n a"}:
                conflict, details = _source_unit_conflict(
                    fact,
                    value=fact.data.get("value_raw"),
                    declared_unit=fact.data.get("unit_raw"),
                )
                if conflict:
                    issues.append(
                        _promotion_issue(
                            fact,
                            code="promotion_source_unit_conflict_quarantined",
                            message=(
                                "A non-tensile Property used a unit that did not "
                                "match the unique source-literal unit next to the "
                                "quoted value; the fact was isolated without "
                                "conversion."
                            ),
                            expected={
                                "source_literal_unit_matches_unit_raw": True,
                                "conversion": False,
                                "axis": "properties",
                                "audit_preserved": True,
                            },
                            actual={
                                "removed": fact.model_dump(),
                                **details,
                            },
                            evidence=_fact_evidence(fact),
                        )
                    )
                    continue
        accepted.append(fact)
    return accepted, issues


def _is_wrong_axis_property(fact: PropertyFact) -> bool:
    name = str(fact.data.get("property_name_raw") or "")
    if _WRONG_AXIS_PROPERTY.fullmatch(name):
        return True
    return (
        _scientific_fold(name) == "ed"
        and _PROCESS_ENERGY_DENSITY_UNIT.fullmatch(
            str(fact.data.get("unit_raw") or "")
        )
        is not None
    )


def _property_table_cells(row: Any) -> list[str]:
    """Return normalized cells for one Markdown table row."""

    text = str(row or "").strip()
    if not text.startswith("|"):
        return []
    return [
        _scientific_fold(cell.strip())
        for cell in text.strip().strip("|").split("|")
    ]


def _property_evidence_is_non_result_table(fact: PropertyFact) -> bool:
    """Detect a protocol/parameter table that leaked into Properties.

    A table headed ``Process | Rate`` or ``Parameter | Value`` is not a
    material-result table even when the model gives its first-column label a
    plausible Property name (for example ``Cr diffusion``).  We require the
    explicit header grammar and never classify a normal ``Material | UTS`` or
    ``Technology | Density`` result table as a protocol table.
    """

    rows = [_property_table_cells(row) for row in _fact_evidence(fact)]
    rows = [row for row in rows if len(row) >= 2]
    for cells in rows:
        first, second = cells[0], cells[1]
        second_head = second.split()[0] if second else ""
        if _PROPERTY_METADATA_TABLE_HEADER.fullmatch(first):
            return True
        if first in _NON_RESULT_TABLE_FIRST_COLUMN and (
            second in _NON_RESULT_TABLE_SECOND_COLUMN
            or second_head in _NON_RESULT_TABLE_SECOND_COLUMN
            or first in {"process", "processes", "process stage"}
        ):
            return True
    return False


def _property_metadata_projection_reason(fact: PropertyFact) -> str | None:
    """Identify labels that describe a model/header, not a material outcome."""

    name = str(fact.data.get("property_name_raw") or "").strip()
    if _PROPERTY_METADATA_NAME.fullmatch(name):
        folded = _scientific_fold(name)
        if "fit" in folded:
            return "fit_parameter_label"
        if "young" in folded or "voigt" in folded:
            return "elastic_model_label"
        return "placeholder_or_metadata_label"
    rows = [_property_table_cells(row) for row in _fact_evidence(fact)]
    if any(
        cells
        and _PROPERTY_METADATA_TABLE_HEADER.fullmatch(cells[0])
        for cells in rows
    ):
        return "metadata_or_fit_parameter_table"
    return None


def _property_comparative_projection_reason(fact: PropertyFact) -> str | None:
    """Return why a Property is a comparison/derived projection, if any."""

    name = str(fact.data.get("property_name_raw") or "").strip()
    name_folded = _scientific_fold(name)
    if name_folded in _ABSOLUTE_RELATIVE_PROPERTY_NAMES:
        return None
    # Let the dedicated one-to-one ``respectively`` gate own ambiguous value
    # lists.  In particular, labels such as ``fracture-location variation
    # range`` are often a valid metric with missing coordinates; classifying
    # them here would hide the more precise mapping audit code.
    if (
        "respectiv" in "\n".join(_fact_evidence(fact)).casefold()
        and re.search(r"(?i)\b(?:variation|range|location)\b", name)
    ):
        return None
    if _COMPARATIVE_PROPERTY_NAME.search(name):
        return "comparative_property_name"
    value = str(fact.data.get("value_raw") or "").strip()
    if _COMPARATIVE_PROPERTY_VALUE.search(value):
        return "comparative_value_literal"
    if _PROPERTY_PROCESS_PARAMETER_NAME.search(name):
        return "process_parameter_name"
    if _property_evidence_is_non_result_table(fact):
        return "non_result_parameter_table"
    return None


def _has_source_explicit_processing_parameter(
    fact: ProcessingFact, source_text: str
) -> bool:
    """Protect only literal, non-generic parameter values found in the paper."""

    normalized_source = normalize_evidence_text(source_text)
    generic_values = {
        "",
        "different",
        "high",
        "low",
        "higher",
        "lower",
        "increased",
        "decreased",
        "greater",
        "less",
        "rapid",
        "slow",
        "faster",
        "slower",
        "variable",
        "various",
        "significant",
        "negligible",
        "not reported",
        "not_reported",
        "unknown",
        "various",
    }
    for parameter in fact.data.get("parameters_raw") or []:
        if not isinstance(parameter, dict):
            continue
        value = str(parameter.get("value_raw") or "").strip()
        if _scientific_fold(value) in generic_values:
            continue
        evidence = parameter.get("source_evidence")
        if isinstance(evidence, Sequence) and not isinstance(evidence, (str, bytes)):
            evidence_rows = [str(row).strip() for row in evidence if str(row).strip()]
        else:
            evidence_rows = [str(evidence or "").strip()]
        for row in evidence_rows:
            normalized_row = normalize_evidence_text(row)
            if (
                normalized_row
                and normalized_row in normalized_source
                and _literal_mention(row, value)
            ):
                return True
    return False


def _is_processing_observation_projection(
    fact: ProcessingFact, source_text: str
) -> bool:
    """Identify a region observation misclassified as a process event."""

    if fact.fact_type != "process_stage":
        return False
    evidence = "\n".join(_fact_evidence(fact))
    if not (
        _PROCESS_REGION_LOCATOR.search(evidence)
        and _PROCESS_OBSERVATION_CUE.search(evidence)
    ):
        return False
    if _PROCESS_EVENT_CUE.search(evidence) or _PROCESS_PARAMETER_CUE.search(evidence):
        return False
    return not _has_source_explicit_processing_parameter(fact, source_text)


def _gate_processing_observation_projections(
    facts: Sequence[AxisFact], source_text: str
) -> tuple[list[AxisFact], list[PromotionIssue]]:
    accepted: list[AxisFact] = []
    issues: list[PromotionIssue] = []
    for fact in facts:
        if not isinstance(fact, ProcessingFact) or not _is_processing_observation_projection(
            fact, source_text
        ):
            accepted.append(fact)
            continue
        issues.append(
            _promotion_issue(
                fact,
                code="promotion_processing_observation_projection_quarantined",
                message=(
                    "A cast or laser-treated region used only as the location of "
                    "a structure/characterization result is not a process stage."
                ),
                expected={
                    "explicit_process_event_or_parameter": True,
                    "region_locator_alone_is_process": False,
                    "audit_preserved": True,
                },
                actual={
                    "removed": fact.model_dump(),
                    "reason": "region_observation_not_process_event",
                },
            )
        )
    return accepted, issues


def _is_unasserted_process_stage(
    fact: ProcessingFact,
) -> bool:
    """Return whether a stage is supported only by a label/caption fragment.

    The extraction prompt may correctly identify a process code from an item
    label, but a material identity is not itself evidence that the paper
    reported that process step.  This gate is deliberately prose-only and
    leaves Markdown/HTML table rows to the coordinate-aware processing path.
    A treatment noun (``aging heat treatment``) is enough to keep a genuine
    process reference; otherwise require an event or parameter assertion.
    """

    if fact.fact_type != "process_stage":
        return False
    evidence = _fact_evidence(fact)
    if not evidence or _has_table_evidence(evidence):
        return False

    # The older version of this gate treated broad process vocabulary as an
    # executed event.  That admitted projections such as ``EBAM``/``LPBF``
    # copied from a sample label or ``electron beam`` mentioned only as a
    # causal context.  Use the same narrow direct-event predicate as the
    # result/hypothetical gate instead: a stage must be tied to an executed
    # event or to a literal parameter in the candidate's own evidence.  A
    # grounded process noun by itself is not enough to claim that the step
    # occurred.
    joined = "\n".join(evidence)
    # A prose sentence that directly asserts a named process parameter is
    # source-grounded even when the extractor omitted ``parameters_raw``.
    # Keep this narrow exception before the executed-event predicate so that
    # ``The laser power was 300 W`` is not treated like a bare ``EBAM`` label.
    if (
        _PROCESS_PARAMETER_CUE.search(joined)
        and re.search(r"(?<!\w)[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?!\w)", joined)
        and not _PROCESS_RESULT_EXPLANATION_CUE.search(joined)
        and not _PROCESS_HYPOTHETICAL_CUE.search(joined)
        and not _COMPARATIVE_ASSERTION_CUE.search(joined)
    ):
        return False
    return not _processing_stage_has_direct_assertion(
        fact,
        joined,
    )


def _quarantine_unasserted_process_stages(
    facts: Sequence[AxisFact],
) -> tuple[list[AxisFact], list[PromotionIssue]]:
    """Isolate process-code projections that have no source process assertion."""

    accepted: list[AxisFact] = []
    issues: list[PromotionIssue] = []
    for fact in facts:
        if not isinstance(fact, ProcessingFact) or not _is_unasserted_process_stage(
            fact
        ):
            accepted.append(fact)
            continue
        issues.append(
            _promotion_issue(
                fact,
                code="promotion_processing_stage_unasserted_quarantined",
                message=(
                    "A process stage was emitted from a sample label or caption "
                    "without a source-grounded process event, treatment, or "
                    "parameter assertion."
                ),
                expected={
                    "explicit_process_event_or_parameter": True,
                    "label_only_projection": False,
                    "table_path_unchanged": True,
                    "audit_preserved": True,
                },
                actual={
                    "removed": fact.model_dump(),
                    "reason": "process_stage_without_source_assertion",
                },
                evidence=_fact_evidence(fact),
            )
        )
    return accepted, issues


def _processing_stage_has_direct_assertion(
    fact: ProcessingFact,
    source_text: str,
) -> bool:
    """Return whether a process-stage candidate has an executed source event.

    This is deliberately stricter than ``_PROCESS_ACTION_ASSERTION``.  The
    latter is used by legacy gates and includes causal verbs such as
    ``resulted``/``affected``; those verbs describe an outcome, not a process
    event.  A stage may also be supported by a source-literal parameter, but
    generic values (``high``, ``different`` and ``not reported``) do not count.
    """

    evidence = _fact_evidence(fact)
    if not evidence:
        return False
    if _has_table_evidence(evidence):
        # Markdown/HTML tables are routed by the coordinate-aware processing
        # gate; this source-only pass must not pre-empt that path.
        return True
    joined = "\n".join(evidence)
    if _has_source_explicit_processing_parameter(fact, source_text):
        return True
    if _PROCESS_DIRECT_EVENT_ASSERTION.search(joined):
        return True
    # Compact treatment references such as ``aging heat treatment`` are valid
    # only when they are not hypothetical.  Do not use the broader treatment
    # vocabulary here: it includes generic AM labels such as ``build`` and
    # ``fabrication`` that are not executed events by themselves.
    if _PROCESS_EXPLICIT_TREATMENT_REFERENCE.search(joined) and not _PROCESS_HYPOTHETICAL_CUE.search(
        joined
    ):
        return True
    return False


def _quarantine_processing_result_or_hypothetical_stages(
    facts: Sequence[AxisFact],
    source_text: str,
) -> tuple[list[AxisFact], list[PromotionIssue]]:
    """Isolate result explanations and hypothetical process-stage projections.

    The extractor is allowed to be high recall, but a process stage is a
    historical event, not a causal explanation.  This pass only removes
    prose-only ``process_stage`` records.  Table rows and source-literal
    numeric parameters remain on the existing coordinate-aware path.
    """

    accepted: list[AxisFact] = []
    issues: list[PromotionIssue] = []
    for fact in facts:
        if not isinstance(fact, ProcessingFact) or fact.fact_type != "process_stage":
            accepted.append(fact)
            continue
        evidence = _fact_evidence(fact)
        if not evidence or _has_table_evidence(evidence):
            accepted.append(fact)
            continue
        joined = "\n".join(evidence)
        hypothetical = bool(_PROCESS_HYPOTHETICAL_CUE.search(joined))
        result_explanation = bool(_PROCESS_RESULT_EXPLANATION_CUE.search(joined))
        direct = _processing_stage_has_direct_assertion(fact, source_text)
        # A conditional statement must describe an actual executed event, not
        # merely contain a process noun.  Even ``if ... was used`` is unsafe
        # unless a non-generic source parameter independently anchors it.
        if hypothetical and not _has_source_explicit_processing_parameter(
            fact, source_text
        ):
            reason = "hypothetical_process_step"
        elif result_explanation and not direct:
            reason = "result_explanation_not_process_event"
        else:
            accepted.append(fact)
            continue
        issues.append(
            _promotion_issue(
                fact,
                code="promotion_processing_result_or_hypothetical_stage_quarantined",
                message=(
                    "A Processing stage was emitted from a result explanation or "
                    "conditional/hypothetical statement without an executed source "
                    "event or source-literal parameter."
                ),
                expected={
                    "executed_process_event_or_source_parameter": True,
                    "result_or_hypothetical_projection": False,
                    "table_path_unchanged": True,
                    "audit_preserved": True,
                },
                actual={
                    "removed": fact.model_dump(),
                    "reason": reason,
                    "result_explanation_cue": result_explanation,
                    "hypothetical_cue": hypothetical,
                },
                evidence=evidence,
            )
        )
    return accepted, issues


def _is_zero_duration_heat_treatment_stage(fact: ProcessingFact) -> bool:
    """Return whether a zero table cell was projected as an executed HT stage."""

    if fact.fact_type != "process_stage" or not _PROCESS_HEAT_TREATMENT_STAGE_NAME.search(
        str(fact.data.get("process_name_raw") or "")
    ):
        return False
    parameters = [
        row
        for row in (fact.data.get("parameters_raw") or [])
        if isinstance(row, dict)
    ]
    if not parameters or any(
        not _PROCESS_DURATION_PARAMETER_NAME.search(
            str(row.get("parameter_name_raw") or "")
        )
        for row in parameters
    ):
        return False
    for row in parameters:
        tokens = _numeric_tokens(row.get("value_raw"))
        if len(tokens) != 1:
            return False
        try:
            if float(tokens[0]) != 0.0:
                return False
        except ValueError:
            return False

    joined = "\n".join(_fact_evidence(fact))
    return not bool(
        _PROCESS_DIRECT_EVENT_ASSERTION.search(joined)
        or _PROCESS_DIRECT_HEATING_EVENT.search(joined)
    )


def _quarantine_zero_duration_heat_treatment_stages(
    facts: Sequence[AxisFact],
) -> tuple[list[AxisFact], list[PromotionIssue]]:
    """Isolate a no-treatment zero row without dropping its audit payload."""

    accepted: list[AxisFact] = []
    issues: list[PromotionIssue] = []
    for fact in facts:
        if not isinstance(fact, ProcessingFact) or not _is_zero_duration_heat_treatment_stage(
            fact
        ):
            accepted.append(fact)
            continue
        issues.append(
            _promotion_issue(
                fact,
                code="promotion_processing_zero_duration_stage_quarantined",
                message=(
                    "A heat-treatment candidate whose only reported parameter "
                    "was zero duration was isolated as a not-applied table row."
                ),
                expected={
                    "executed_heat_treatment": True,
                    "positive_duration_or_other_parameter": True,
                    "audit_preserved": True,
                },
                actual={
                    "removed": fact.model_dump(),
                    "reason": "zero_duration_encodes_treatment_not_applied",
                },
                evidence=_fact_evidence(fact),
            )
        )
    return accepted, issues


def _quarantine_processing_specimen_preparation_stages(
    facts: Sequence[AxisFact],
) -> tuple[list[AxisFact], list[PromotionIssue]]:
    """Isolate specimen-preparation protocol steps from the process route.

    High-recall extraction frequently promotes ``sectioned``, ``mounted``,
    ``polished`` or ``etched`` sample preparation as a material Processing
    stage.  Those actions are useful audit context, but they are not the
    material fabrication/thermal-processing route consumed by downstream
    analysis.  Keep this pass prose-only and conservative: table rows remain
    on the coordinate-aware path, and an explicit material-processing event in
    the same evidence protects a legitimate production operation.
    """

    accepted: list[AxisFact] = []
    issues: list[PromotionIssue] = []
    for fact in facts:
        if not isinstance(fact, ProcessingFact) or fact.fact_type != "process_stage":
            accepted.append(fact)
            continue
        evidence = _fact_evidence(fact)
        if not evidence or _has_table_evidence(evidence):
            accepted.append(fact)
            continue
        joined = "\n".join(evidence)
        action = _PROCESS_SPECIMEN_PREPARATION_ACTION.search(joined)
        target = _PROCESS_SPECIMEN_PREPARATION_TARGET.search(joined)
        if (
            action is None
            or target is None
            or _PROCESS_MATERIAL_EVENT_ASSERTION.search(joined)
        ):
            accepted.append(fact)
            continue
        issues.append(
            _promotion_issue(
                fact,
                code="promotion_processing_specimen_preparation_quarantined",
                message=(
                    "A prose Processing stage described specimen/sample preparation "
                    "rather than a material fabrication or treatment event; it was "
                    "isolated from the formal process route while preserving audit."
                ),
                expected={
                    "material_processing_event": True,
                    "specimen_preparation_only": False,
                    "table_path_unchanged": True,
                    "audit_preserved": True,
                },
                actual={
                    "removed": fact.model_dump(),
                    "reason": "specimen_preparation_protocol_not_material_process",
                    "preparation_action": action.group(0),
                    "preparation_target": target.group(0),
                    "material_event_cue": False,
                },
                evidence=evidence,
            )
        )
    return accepted, issues


def _quarantine_processing_test_protocol_stages(
    facts: Sequence[AxisFact],
) -> tuple[list[AxisFact], list[PromotionIssue]]:
    """Isolate mechanical-test protocol prose from material Processing."""

    accepted: list[AxisFact] = []
    issues: list[PromotionIssue] = []
    for fact in facts:
        if not isinstance(fact, ProcessingFact) or fact.fact_type != "process_stage":
            accepted.append(fact)
            continue
        evidence = _fact_evidence(fact)
        if not evidence or _has_table_evidence(evidence):
            accepted.append(fact)
            continue
        joined = "\n".join(evidence)
        target_match = _PROCESS_SPECIMEN_PREPARATION_TARGET.search(joined)
        if target_match is None and _literal_mention(joined, fact.sample_id_raw):
            target_match_text = str(fact.sample_id_raw)
        else:
            target_match_text = target_match.group(0) if target_match else ""
        if (
            not _PROCESS_TEST_PROTOCOL_CUE.search(joined)
            or not target_match_text
            or _PROCESS_MATERIAL_EVENT_ASSERTION.search(joined)
        ):
            accepted.append(fact)
            continue
        issue = _promotion_issue(
            fact,
            code="promotion_processing_test_protocol_quarantined",
            message=(
                "A prose Processing stage described tensile/fatigue/creep test "
                "execution rather than a material-processing event; it was "
                "isolated while preserving the complete audit record."
            ),
            expected={
                "material_processing_event": True,
                "test_protocol_only": False,
                "table_path_unchanged": True,
                "audit_preserved": True,
            },
            actual={
                "removed": fact.model_dump(),
                "reason": "mechanical_test_protocol_not_material_process",
                "test_protocol_cue": _PROCESS_TEST_PROTOCOL_CUE.search(joined).group(0),
                "test_target_cue": target_match_text,
                "material_event_cue": False,
            },
            evidence=evidence,
        )
        issues.append(issue)
    return accepted, issues


def _quarantine_processing_metadata_parameters(
    facts: Sequence[AxisFact],
) -> tuple[list[AxisFact], list[PromotionIssue]]:
    """Remove prose-only equipment/environment metadata subfields.

    Equipment, atmosphere, technique, and feedstock labels are useful audit
    context but are not independent process parameters.  They remain eligible
    when emitted from a Markdown/HTML table, while numeric process coordinates
    are always preserved.  A surviving process stage is kept with its event
    and remaining parameters; if no payload remains, the original stage still
    remains auditable through the issue record.
    """

    accepted: list[AxisFact] = []
    issues: list[PromotionIssue] = []
    for fact in facts:
        if not isinstance(fact, ProcessingFact) or fact.fact_type != "process_stage":
            accepted.append(fact)
            continue
        parameters = [
            parameter
            for parameter in fact.data.get("parameters_raw") or []
            if isinstance(parameter, dict)
        ]
        removed: list[dict[str, Any]] = []
        kept: list[dict[str, Any]] = []
        fallback = _fact_evidence(fact)
        for parameter in parameters:
            name = str(parameter.get("parameter_name_raw") or "").strip()
            evidence = _feature_evidence(parameter, fallback)
            table_bound = _has_table_evidence(evidence)
            numeric_coordinate = bool(_PROCESS_NUMERIC_PARAMETER_NAME.search(name))
            if (
                not table_bound
                and not numeric_coordinate
                and _PROCESS_METADATA_PARAMETER.fullmatch(name)
            ):
                removed.append(
                    {
                        "parameter": deepcopy(parameter),
                        "parameter_name_raw": name,
                        "reason": "prose_metadata_subfield_without_coordinate",
                        "evidence": evidence,
                    }
                )
                continue
            kept.append(parameter)
        if not removed:
            accepted.append(fact)
            continue
        data = deepcopy(fact.data)
        data["parameters_raw"] = kept
        after = fact.model_copy(deep=True, update={"data": data})
        # A process-stage event can survive with metadata removed.  For a
        # parameter-only candidate the empty stage is not useful to the formal
        # ledger and is therefore isolated in full.
        if kept or _processing_stage_has_direct_assertion(fact, ""):
            accepted.append(after)
        for row in removed:
            issues.append(
                _promotion_issue(
                    fact,
                    code="promotion_processing_metadata_parameter_quarantined",
                    message=(
                        "A prose-only Processing equipment/environment/technique "
                        "label was isolated from the formal parameter ledger; the "
                        "complete candidate and source evidence remain in audit."
                    ),
                    expected={
                        "independent_numeric_or_table_coordinate": True,
                        "metadata_subfield_only": False,
                        "audit_preserved": True,
                    },
                    actual={
                        "removed": row["parameter"],
                        "reason": row["reason"],
                        "before": fact.model_dump(),
                        "after": after.model_dump() if kept else None,
                    },
                    evidence=row["evidence"],
                )
            )
    return accepted, issues


def _quality_gate(
    facts: Sequence[AxisFact],
) -> tuple[list[AxisFact], list[PromotionIssue]]:
    accepted: list[AxisFact] = []
    issues: list[PromotionIssue] = []
    for fact in facts:
        # Keep Composition on its accepted v47 path. Its protected recall must
        # not depend on stricter experimental gates introduced for other axes.
        if fact.axis == "composition":
            accepted.append(fact)
            continue
        gate = filter_axis_facts([fact], mode="safe")
        cleaned = gate.accepted[0] if gate.accepted else None
        for issue in gate.issues:
            # A source-local tensile unit rewrite is converted below into the
            # stricter promotion quarantine code; do not emit a second audit
            # row that looks like the rewrite was accepted.
            if issue.code == "property_source_unit_reconciled":
                continue
            actual = (
                {
                    "removed": fact.model_dump(),
                    "gate_actual": deepcopy(issue.actual),
                }
                if cleaned is None
                else {
                    "before": fact.model_dump(),
                    "after": cleaned.model_dump(),
                    "gate_actual": deepcopy(issue.actual),
                }
            )
            issues.append(
                PromotionIssue(
                    code=issue.code,
                    sample_id_raw=fact.sample_id_raw,
                    path=issue.path,
                    message=issue.message,
                    evidence=deepcopy(issue.evidence),
                    expected=deepcopy(issue.expected),
                    actual=actual,
                    suggested_action=issue.suggested_action,
                )
            )
        if cleaned is None:
            continue
        source_unit_reconciled = any(
            issue.code == "property_source_unit_reconciled"
            for issue in gate.issues
        )
        if source_unit_reconciled and isinstance(cleaned, PropertyFact):
            # ``claim_quality`` keeps a direct unit-reconciliation path for
            # callers that explicitly request a cleaned fact.  The promotion
            # ledger is stricter: changing MPa to GPa before materialization
            # hides a source/contract conflict, so isolate the original row
            # and retain the quality issue plus a stable promotion code.
            quality_actual = next(
                (
                    issue.actual
                    for issue in gate.issues
                    if issue.code == "property_source_unit_reconciled"
                ),
                {},
            )
            issues.append(
                _promotion_issue(
                    fact,
                    code="promotion_tensile_source_unit_conflict_quarantined",
                    message=(
                        "A core-tensile unit was reconciled from a source-local "
                        "mismatch; the promotion ledger isolated the original "
                        "candidate instead of silently relabeling it."
                    ),
                    expected={
                        "source_literal_unit_matches_unit_raw": True,
                        "canonical_conversion": "materialization_only",
                        "audit_preserved": True,
                    },
                    actual={
                        "removed": fact.model_dump(),
                        "reconciled": cleaned.model_dump(),
                        "declared_unit": quality_actual.get("declared_unit"),
                        "source_units": [quality_actual.get("inline_unit")]
                        if quality_actual.get("inline_unit")
                        else [],
                        "quality_gate": [quality_actual],
                    },
                    evidence=_fact_evidence(fact),
                )
            )
            continue
        if isinstance(cleaned, PropertyFact) and _is_wrong_axis_property(cleaned):
            issues.append(
                _promotion_issue(
                    cleaned,
                    code="property_non_result_quarantined",
                    message=(
                        "A structural metric, specimen/equipment value, process "
                        "parameter, or test control is not a material Property "
                        "outcome."
                    ),
                    expected={
                        "axis": "structure, processing, or test metadata",
                        "property": False,
                    },
                    actual={
                        "removed": cleaned.model_dump(),
                        "reason": "wrong_axis_non_result",
                    },
                )
            )
            continue
        accepted.append(cleaned)
    return accepted, issues


def _composition_precision_gate(
    facts: Sequence[AxisFact],
) -> tuple[list[AxisFact], list[PromotionIssue]]:
    """Apply the production composition precision gate with full audit payloads.

    Composition intentionally bypasses the recall-oriented ``safe`` quality gate
    above.  The Alpha25 promotion contract nevertheless needs to prevent a
    component-shaped projection (for example ``Al: higher`` or ``Ti: unknown``)
    from reaching the public materializer.  ``filter_composition_precision_facts``
    returns a cleaned copy plus one issue per removed component; translate those
    issues into the promotion audit format while retaining the complete original
    fact and the surviving projection.
    """

    accepted: list[AxisFact] = []
    issues: list[PromotionIssue] = []
    for fact in facts:
        if not isinstance(fact, CompositionFact):
            accepted.append(fact)
            continue

        gate = filter_composition_precision_facts([fact])
        cleaned = gate.accepted[0] if gate.accepted else None
        for issue in gate.issues:
            removed = None
            if isinstance(issue.actual, dict):
                removed = issue.actual.get("component")
            actual = {
                "reason": (
                    issue.actual.get("reason")
                    if isinstance(issue.actual, dict)
                    else None
                ),
                "removed_component": deepcopy(removed),
                "before": fact.model_dump(),
                "after": cleaned.model_dump() if cleaned is not None else None,
                "gate_actual": deepcopy(issue.actual),
            }
            issues.append(
                PromotionIssue(
                    code=issue.code,
                    sample_id_raw=fact.sample_id_raw,
                    path=issue.path,
                    message=issue.message,
                    evidence=deepcopy(issue.evidence),
                    expected=deepcopy(issue.expected),
                    actual=actual,
                    suggested_action=issue.suggested_action,
                )
            )
        if cleaned is not None:
            accepted.append(cleaned)
    return accepted, issues


def _feature_evidence(feature: dict[str, Any], fallback: Sequence[str]) -> list[str]:
    value = feature.get("source_evidence")
    if isinstance(value, str):
        value = [value]
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        rows = [str(row).strip() for row in value if str(row).strip()]
        if rows:
            return rows
    return list(fallback)


def _is_quantitative_structure_feature(feature: dict[str, Any]) -> bool:
    return _scientific_fold(feature.get("value_kind")) in {
        "scalar",
        "range",
        "inequality",
        "uncertainty",
    }


_STRUCTURE_METHOD_ONLY_VALUE = re.compile(
    r"(?ix)^\s*(?:"
    r"measur(?:e|ed|ement|ements)?|determin(?:e|ed|ation)|"
    r"evaluat(?:e|ed|ion)|calculat(?:e|ed|ion)|quantif(?:y|ied|ication)|"
    r"analys(?:e|ed|is)|analyz(?:e|ed|is)|characteriz(?:e|ed|ation)|"
    r"assess(?:ed|ment)?|test(?:ed|ing)?|report(?:ed|ing)?|"
    r"observ(?:ed|ation)?|(?:shown|displayed|presented)|"
    r"(?:sem|tem|ebsd|xrd)\s+(?:image|images|map|maps|micrograph|micrographs)|"
    r"snapshots?\b|corresponding\s+.*\bmaps?\b"
    r")(?:\s+(?:using|by|via|with|from|according\s+to|through)\b.*)?\s*$"
)
_STRUCTURE_METHOD_ONLY_NAME = re.compile(
    r"(?ix)\b(?:measurement\s+method|measurement\s+procedure|"
    r"measuring\s+method|analysis\s+method|test\s+method|"
    r"measurement\s+technique|imaging\s+method|procedure|protocol)\b"
)
_STRUCTURE_UNIT_ONLY_VALUE = re.compile(
    r"(?ix)^\s*(?:nm|[µμu]m|\\mu\s*m|\\mum|mm|cm|"
    r"å|(?:ångstr(?:ö|o)m|angstrom)s?)\s*$"
)
_STRUCTURE_DERIVED_FEATURE_NAME = re.compile(
    r"(?ix)\b(?:coefficient|fit(?:ted)?\s+parameter|equation|"
    r"calculated\s+(?:value|parameter)|derived\s+(?:value|parameter)|"
    r"formula)\b"
)
_STRUCTURE_FORMULA_EVIDENCE = re.compile(
    r"(?ix)\b(?:equation|relation(?:ship)?|coefficient|formula|"
    r"where\s+[a-z]\s*=|[a-z]\s*=\s*[a-z0-9])\b"
)
_STRUCTURE_COEFFICIENT_ASSIGNMENT = re.compile(
    r"(?ix)^\s*(?P<variable>[a-z])\s*=\s*"
    r"[-+]?(?:\d+(?:\.\d*)?|\.\d+)(?:e[-+]?\d+)?\s*$"
)
_STRUCTURE_PHYSICAL_SIZE_NAME = re.compile(
    r"(?ix)\b(?:grain|pore|particle|precipitate|lath|cell)\b.*"
    r"\b(?:size|diameter|width|length|thickness|spacing)\b|"
    r"\b(?:size|diameter|width|length|thickness|spacing)\b.*"
    r"\b(?:grain|pore|particle|precipitate|lath|cell)\b"
)
_STRUCTURE_POWDER_SIZE_COMPARISON = re.compile(
    r"(?ixs)\bgrains?\b.{0,120}?\b(?:comparable|similar)\s+to\b"
    r".{0,100}?\b(?:powder\s+)?particle\s+size\b(?P<payload>.{0,80})"
)
_STRUCTURE_PROCESS_COORDINATE_NAME = re.compile(
    r"(?ix)^\s*(?:build|printing|deposition)\s+orientation\s*$"
)
_STRUCTURE_UNRESOLVED_VARIABLE = re.compile(
    r"(?ix)^\s*(?:d|x|h|l[_\s-]*(?:g|gbar)|r|t)\s*$"
)
_STRUCTURE_GENERIC_FEATURE_NAME = re.compile(
    r"(?ix)^\s*(?:amount|quantity|value|distribution|function|effect|"
    r"origin|cause|purpose|mechanism|role|impact|influence)\s*$"
)
_STRUCTURE_FEEDSTOCK_PARTICLE_NAME = re.compile(
    r"(?ix)\b(?:particle\s+size(?:\s+distribution)?|"
    r"powder\s+size|average\s+powder\s+size)\b"
)
_STRUCTURE_FEEDSTOCK_PARTICLE_CONTEXT = re.compile(
    r"(?ix)\b(?:powder|feedstock|gas[-\s]?atomiz(?:ed|ation)?|"
    r"starting\s+(?:reinforcing\s+)?particles?|particle\s+size\s+"
    r"(?:distribution|analy[sz]er)|mastersizer)\b"
)
_STRUCTURE_COMPOSITION_FIELD_NAME = re.compile(
    r"(?ix)\b(?:content|concentration|weight\s+(?:fraction|percentage)|"
    r"atomic\s+(?:fraction|percentage)|wt\.?\s*%|at\.?\s*%)\b"
)
_STRUCTURE_COMPOSITION_EVIDENCE = re.compile(
    r"(?ix)\b(?:at\.?\s*%|wt\.?\s*%|weight\s+percent|atomic\s+percent|"
    r"element(?:al|al\s+analysis)?|stoichiometr|enriched\s+in|depleted\s+in)\b"
)
_STRUCTURE_FIGURE_ARTIFACT_VALUE = re.compile(
    r"(?ix)\b(?:sem|tem|ebsd|xrd)?\s*(?:image|images|map|maps|"
    r"micrograph|micrographs|snapshot|snapshots)\b\s*(?:of|from|showing)?\b"
)
_STRUCTURE_FEEDSTOCK_TABLE_CUE = re.compile(
    r"(?ix)\b(?:particle\s+size\s+distribution|"
    r"(?:average|avg\.?|mean)\s+particle\s+size|flow\s+rate|"
    r"solid\s+density|density\s+change)\b"
)
_STRUCTURE_COMPOSITION_COMPARATIVE_NAME = re.compile(
    r"(?ix)\b(?:content|concentration|weight\s+(?:fraction|percentage)|"
    r"atomic\s+(?:fraction|percentage)|wt\.?\s*%|at\.?\s*%)\b"
)
_STRUCTURE_COMPOSITION_COMPARATIVE_VALUE = re.compile(
    r"(?ix)\b(?:higher|lower|greater|less|more|"
    r"increas(?:e|ed|es|ing)|decreas(?:e|ed|es|ing)|"
    r"reduc(?:e|ed|es|ing)|minimal(?:ly)?|alteration|"
    r"difference|relative\s+to|compared\s+(?:to|with)|than)\b"
)
_STRUCTURE_FEATURE_PHASE_NAME = re.compile(
    r"(?ix)\b(?:precipitat(?:e|ed|ion)|grain|phase|microstructure|"
    r"morphology|structure)\b"
)
_STRUCTURE_COUNT_FEATURE_NAME = re.compile(
    r"(?ix)\b(?:sample|specimen|observation|measurement|inspection|"
    r"exam(?:ine|ined|ination)|count|number|population|n\s*=)\w*\b"
)
_STRUCTURE_POROSITY_COUNT_NAME = re.compile(
    r"(?ix)\b(?:porosity|pore|pores)\b.*\b(?:sample|specimen|count|number|"
    r"fraction|population)\b|\b(?:sample|specimen)s?\b.*\b(?:porosity|pore|pores)\b"
)
_STRUCTURE_COUNT_RELATION = re.compile(
    r"(?ix)(?<!\d)(?P<numerator>\d+)\s*(?:out\s+of|of|/)\s*"
    r"(?P<denominator>\d+)(?!\d)"
)
_STRUCTURE_BARE_INTEGER = re.compile(r"^\s*\d+\s*$")
_STRUCTURE_RELATIONAL_DENOMINATOR_NAME_V205 = re.compile(
    r"(?ix)^\s*(?:[a-z0-9'′γασδ_()/\-]+\s+){0,8}"
    r"(?:increment|denominator|per[\s_-]*increment|reference[\s_-]*increment)\s*$"
)
_STRUCTURE_RELATIONAL_THRESHOLD_NAME_V205 = re.compile(
    r"(?ix)^\s*(?:size|diameter|width|length|spacing|fraction|value)?"
    r"[\s_-]*threshold\s*$"
)
_STRUCTURE_PROCESS_CONDITION_NAME_V205 = re.compile(
    r"(?ix)^\s*(?:(?:formation|processing|process|sintering|annealing|"
    r"aging|heat[\s_-]*treatment)\s+)?(?:temperature\s+)?condition\s*$"
)
_STRUCTURE_PROCESS_CONDITION_EVIDENCE_V205 = re.compile(
    r"(?ix)\b(?:sinter(?:ed|ing)?|anneal(?:ed|ing)?|ag(?:ed|ing)|"
    r"heat[\s-]*treat(?:ed|ment|ing)?|solution(?:ized|ised|izing)|"
    r"homogeni[sz](?:ed|ation|ing)?)\b"
)
_STRUCTURE_RESULT_AFTER_CONDITION_V205 = re.compile(
    r"(?ix)\b(?:detect(?:ed|ion)|observ(?:ed|ation)|form(?:ed|ation)|"
    r"precipitat(?:ed|ion)|dissolv(?:ed|ution)|phase|grain|pore|"
    r"microstructur(?:e|al))\b"
)


def _structure_count_status(
    feature: dict[str, Any], evidence: Sequence[str]
) -> tuple[str, str] | None:
    """Classify a bare specimen/count projection without deleting real metrics."""

    name = str(feature.get("feature_name_raw") or feature.get("canonical_name") or "")
    folded_name = _scientific_fold(name)
    value = str(feature.get("value_raw") or "").strip()
    if not _STRUCTURE_BARE_INTEGER.fullmatch(value):
        return None
    if not _STRUCTURE_COUNT_FEATURE_NAME.search(folded_name):
        # A numeric ``porosity`` field with no unit is commonly the numerator
        # of ``2 of 164``.  It gets the same relation requirement below, while
        # percentage/decimal porosity values remain untouched.
        if "porosity" not in folded_name and "pore" not in folded_name:
            return None

    candidate_number = str(int(value))
    relation = None
    for row in evidence:
        match = _STRUCTURE_COUNT_RELATION.search(str(row or ""))
        if match and match.group("numerator") == candidate_number:
            relation = match.group(0)
            break

    porosity_count = bool(
        _STRUCTURE_POROSITY_COUNT_NAME.search(folded_name)
        or "porosity" in folded_name
        or "pore" in folded_name
    )
    if porosity_count and relation:
        return "complete", relation
    if porosity_count:
        return "quarantine", "porosity_count_without_denominator_relation"
    if _STRUCTURE_COUNT_FEATURE_NAME.search(folded_name):
        return "quarantine", "standalone_sample_or_specimen_count"
    return None


def _complete_structure_count_feature(
    feature: dict[str, Any], evidence: Sequence[str]
) -> tuple[dict[str, Any], str] | None:
    status = _structure_count_status(feature, evidence)
    if status is None or status[0] != "complete":
        return None
    relation = status[1]
    if relation in str(feature.get("value_raw") or ""):
        return None
    completed = deepcopy(feature)
    # Keep value_kind=scalar so the existing Structure materializer treats this
    # as a quantitative feature.  The literal ``2 of 164`` remains auditable
    # and prevents a separate denominator claim from being materialized.
    completed["value_raw"] = relation
    return completed, relation


def _structure_feature_precision_risk(
    feature: dict[str, Any],
    evidence: Sequence[str],
    *,
    has_entity: bool = False,
) -> tuple[str, str] | None:
    """Return a deterministic reason for a non-result Structure projection."""

    count_status = _structure_count_status(feature, evidence)
    if count_status is not None and count_status[0] == "quarantine":
        return (
            "promotion_structure_count_metadata_quarantined",
            count_status[1],
        )

    value = str(feature.get("value_raw") or "").strip()
    if _STRUCTURE_UNIT_ONLY_VALUE.fullmatch(value):
        return (
            "promotion_structure_unit_only_value_quarantined",
            "standalone_measurement_unit_is_not_an_observation",
        )

    quantitative = _is_quantitative_structure_feature(feature)
    if not quantitative and not _is_negated_structure_feature(feature):
        if _STRUCTURE_METHOD_ONLY_VALUE.fullmatch(value):
            return (
                "promotion_structure_method_only_value_quarantined",
                "method_only_value",
            )
        name_text = str(feature.get("feature_name_raw") or "")
        if _STRUCTURE_METHOD_ONLY_NAME.search(name_text):
            return (
                "promotion_structure_method_feature_quarantined",
                "method_or_measurement_feature",
            )
        if _STRUCTURE_FIGURE_ARTIFACT_VALUE.search(value):
            return (
                "promotion_structure_figure_artifact_quarantined",
                "figure_or_image_artifact_value",
            )

    name = str(feature.get("feature_name_raw") or "")
    value = str(feature.get("value_raw") or "")
    joined = "\n".join(str(row or "") for row in evidence)

    if structure_assertion_atomicity_v205_enabled():
        value_numbers = set(_numeric_tokens(value))
        if _STRUCTURE_RELATIONAL_DENOMINATOR_NAME_V205.fullmatch(name):
            per_match = re.search(r"(?is)\bper\b(?P<denominator>.{0,120})", joined)
            if per_match is not None:
                denominator_numbers = set(
                    _numeric_tokens(per_match.group("denominator"))
                )
                numerator_numbers = set(
                    _numeric_tokens(joined[: per_match.start()])
                )
                if (
                    value_numbers
                    and numerator_numbers
                    and value_numbers <= denominator_numbers
                ):
                    return (
                        "structure_assertion_projection_quarantined",
                        "relational_denominator_fragment",
                    )
        if _STRUCTURE_RELATIONAL_THRESHOLD_NAME_V205.fullmatch(name):
            source_numbers = set(_numeric_tokens(joined))
            other_numbers = source_numbers - value_numbers
            fraction_relation = re.search(
                r"(?ix)(?:%|percent)\s+of\b.{0,100}\b"
                r"(?:measur(?:e|ed|ing)|below|under|less\s+than|smaller\s+than)\b",
                joined,
            )
            if value_numbers and other_numbers and fraction_relation is not None:
                return (
                    "structure_assertion_projection_quarantined",
                    "relational_threshold_fragment",
                )
        if (
            _STRUCTURE_PROCESS_CONDITION_NAME_V205.fullmatch(name)
            and _STRUCTURE_PROCESS_CONDITION_EVIDENCE_V205.search(joined)
            and _STRUCTURE_RESULT_AFTER_CONDITION_V205.search(joined)
            and (value_numbers or re.search(r"(?ix)\b(?:ambient|room)\b", value))
        ):
            return (
                "structure_assertion_projection_quarantined",
                "process_condition_fragment",
            )

    # A fabrication orientation is a process/specimen coordinate, not a
    # microstructural feature.  Crystallographic orientations remain eligible
    # because this rule is limited to the exact build/printing/deposition
    # labels used by the high-recall projection.
    if _STRUCTURE_PROCESS_COORDINATE_NAME.fullmatch(_scientific_fold(name)):
        return (
            "promotion_structure_process_coordinate_quarantined",
            "build_or_printing_orientation_is_not_structure",
        )

    # A candidate can carry ``value_kind=inequality`` even when the model has
    # emitted only a qualitative comparison (``lower amounts of continuous
    # alpha``).  Treating that as a numeric Structure atom is a projection,
    # not a measurement.  Numeric inequalities/ranges remain untouched.
    if (
        quantitative
        and not _numeric_tokens(value)
        and _STRUCTURE_COMPARATIVE_PROJECTION.search(f"{name} {value}")
    ):
        atomic_comparative_subject = bool(
            re.search(
                r"(?i)\b(?:grain|pore|particle|precipitate|lath|variant|"
                r"diameter|width|length|thickness|spacing|fraction|count|"
                r"size|aspect\s+ratio)\b",
                name,
            )
            and (
                _STRUCTURE_DIRECT_PRESENCE.search(joined)
                or re.search(
                    r"(?ix)\b(?:nm|μm|µm|um|mm|cm|micron|micrometers?|"
                    r"%|percent|degree|°)\b",
                    joined,
                )
            )
        )
        if not atomic_comparative_subject:
            return (
                "promotion_structure_comparative_text_without_magnitude_quarantined",
                "qualitative_comparison_marked_as_quantitative",
            )

    # Unresolved equation variables and coefficient fields are method/derivation
    # metadata.  Require a formula cue in the same evidence block so a literal
    # crystallographic parameter such as ``a = 0.384 nm`` is not discarded.
    if quantitative and _STRUCTURE_UNRESOLVED_VARIABLE.fullmatch(value):
        if _STRUCTURE_FORMULA_EVIDENCE.search(joined):
            return (
                "promotion_structure_unresolved_variable_quarantined",
                "unresolved_formula_variable",
            )
    coefficient_assignment = _STRUCTURE_COEFFICIENT_ASSIGNMENT.fullmatch(value)
    if (
        quantitative
        and coefficient_assignment is not None
        and _STRUCTURE_PHYSICAL_SIZE_NAME.search(name)
        and re.search(
            rf"(?ix)\bcoefficient\s+{re.escape(coefficient_assignment.group('variable'))}\b",
            joined,
        )
    ):
        return (
            "promotion_structure_derived_feature_quarantined",
            "regression_coefficient_projected_as_physical_size",
        )
    if (
        _STRUCTURE_DERIVED_FEATURE_NAME.search(name)
        and _STRUCTURE_FORMULA_EVIDENCE.search(joined)
    ):
        return (
            "promotion_structure_derived_feature_quarantined",
            "derived_or_formula_feature",
        )

    # ``grain sizes comparable to the powder particle size, 15-20 um`` does
    # not report a measured grain-size coordinate: the numeric range belongs
    # to the powder D50/particle-size phrase.  Isolate only when every numeric
    # token in the candidate occurs in that explicit particle-size suffix.
    powder_comparison = _STRUCTURE_POWDER_SIZE_COMPARISON.search(joined)
    if (
        quantitative
        and powder_comparison is not None
        and re.search(r"(?ix)\bgrain\b.*\b(?:size|diameter)\b", name)
    ):
        value_numbers = _numeric_tokens(value)
        particle_numbers = _numeric_tokens(powder_comparison.group("payload"))
        if value_numbers and all(number in particle_numbers for number in value_numbers):
            return (
                "promotion_structure_indirect_comparison_projection_quarantined",
                "powder_particle_size_projected_as_grain_measurement",
            )

    # Generic top-level fields are often the model's summary of a sentence
    # rather than an atomic structural observation.  Nested fields such as an
    # entity's ``distribution`` are left for the entity-aware gates.
    generic_name = _STRUCTURE_GENERIC_FEATURE_NAME.fullmatch(name.strip())
    generic_atomic_hint = bool(
        (
            name.strip().casefold() == "distribution"
            and (
                "distribut" in value.casefold()
                or _STRUCTURE_DIRECT_PRESENCE.search(joined)
            )
        )
        or (
            name.strip().casefold() == "quantity"
            and _has_table_evidence((joined,))
            and bool(_numeric_tokens(value))
        )
        or (
            name.strip().casefold() == "amount"
            and re.search(
                r"(?ix)\b(?:phase|grain|pore|precipitat|particle|lath|variant)\b",
                value,
            )
        )
    )
    if (
        not has_entity
        and generic_name
        and not generic_atomic_hint
        and not _is_negated_structure_feature(feature)
        and not _STRUCTURE_INFERENTIAL_PROJECTION.search(joined)
    ):
        return (
            "promotion_structure_generic_feature_quarantined",
            "generic_non_atomic_feature_name",
        )

    # Elemental content/concentration belongs to Composition unless the field
    # is explicitly a phase/area/volume fraction.  This gate uses both the
    # label and source-local chemistry cues and never guesses from the number
    # alone.
    if (
        _STRUCTURE_COMPOSITION_FIELD_NAME.search(name)
        and _STRUCTURE_COMPOSITION_EVIDENCE.search(joined)
        and not re.search(r"(?ix)\b(?:phase|area|volume)\s+(?:fraction|content)\b", name)
    ):
        return (
            "promotion_structure_composition_projection_quarantined",
            "elemental_composition_field_projected_as_structure",
        )

    # Particle-size values tied to powder/feedstock preparation are not
    # processed-material Structure atoms.  Processed nanoparticles or
    # precipitates without these explicit feedstock cues remain eligible.
    if (
        _STRUCTURE_FEEDSTOCK_PARTICLE_NAME.search(name)
        and _STRUCTURE_FEEDSTOCK_PARTICLE_CONTEXT.search(joined)
    ):
        return (
            "promotion_structure_feedstock_particle_projection_quarantined",
            "feedstock_or_powder_particle_metadata",
        )
    if (
        _STRUCTURE_COMPOSITION_COMPARATIVE_NAME.search(name)
        and _STRUCTURE_COMPOSITION_COMPARATIVE_VALUE.search(value)
    ):
        return (
            "promotion_structure_composition_projection_quarantined",
            "comparative_composition_field_projected_as_structure",
        )
    if (
        not _is_quantitative_structure_feature(feature)
        and not _is_negated_structure_feature(feature)
        and _STRUCTURE_DERIVED_FEATURE_NAME.search(
            str(feature.get("feature_name_raw") or "")
        )
        and re.search(r"(?ix)\b(?:equation|relation|coefficient|calculated|derived)\b", joined)
    ):
        return (
            "promotion_structure_derived_feature_quarantined",
            "derived_or_formula_feature",
        )
    if (
        _has_table_evidence((joined,))
        and _STRUCTURE_FEEDSTOCK_TABLE_CUE.search(joined)
        and _STRUCTURE_FEATURE_PHASE_NAME.search(name)
        and not re.search(r"(?ix)\bparticle\s+size\b", name)
    ):
        return (
            "promotion_structure_table_axis_mismatch_quarantined",
            "feedstock_table_projected_as_structure",
        )
    return None


def _structure_assertion_decision_key_v205(
    fact: StructureFact,
    feature: dict[str, Any],
    evidence: Sequence[str],
    reason: str,
) -> str:
    payload = {
        "owner": _identity_text(fact.sample_id_raw),
        "state": _scientific_fold(fact.data.get("material_state")),
        "feature": _scientific_fold(feature.get("feature_name_raw")),
        "value": _scientific_fold(feature.get("value_raw")),
        "unit": _scientific_fold(feature.get("unit_raw")),
        "evidence": [normalize_evidence_text(row) for row in evidence],
        "reason": reason,
    }
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return "structure-v205:" + hashlib.sha256(encoded).hexdigest()[:24]


def _is_negated_structure_feature(feature: dict[str, Any]) -> bool:
    return bool(
        _NEGATED_STRUCTURE_FEATURE.search(str(feature.get("value_raw") or ""))
    )


def _is_negated_structure_entity(entity: dict[str, Any]) -> bool:
    """Identify entity-only candidates whose source assertion is absence.

    An entity object normally materializes as positive presence.  A candidate
    extractor may also emit that object for an explicit negative such as ``No
    cracks`` or a table cell marked ``absent``.  Only source-explicit polarity
    fields are used here;
    shared evidence text is intentionally ignored because a table block may
    contain both positive and negative cells.
    """

    if entity.get("features"):
        return False
    role = _scientific_fold(entity.get("role"))
    expression = _scientific_fold(entity.get("raw_expression"))
    return (
        role in _NEGATED_STRUCTURE_ENTITY_ROLES
        or _NEGATED_STRUCTURE_ENTITY_EXPRESSION.search(expression) is not None
    )


def _entity_negated_by_prose_evidence(
    entity: dict[str, Any], evidence: Sequence[str]
) -> bool:
    """Detect source-local absence grammar for one explicitly named entity.

    Shared Markdown table blocks are intentionally excluded because their
    polarity is cell-specific and is handled by ``raw_expression``.  Prose is
    accepted only when the entity itself is the object/subject of a bounded
    negative construction; an unrelated phrase such as ``no difference`` can
    therefore never negate later positive entities in the sentence.
    """

    label = _scientific_fold(
        entity.get("name_raw") or entity.get("raw_expression")
    )
    if not label:
        return False
    escaped = re.escape(label).replace(r"\ ", r"\s+")
    entity_pattern = rf"(?<![a-z0-9]){escaped}(?:s|es)?(?![a-z0-9])"
    direct_prefix = re.compile(
        rf"(?ix)\b(?:no|without)\s+"
        rf"(?:(?:detectable|visible|obvious|remaining)\s+){{0,2}}"
        rf"{entity_pattern}"
    )
    nominal_prefix = re.compile(
        rf"(?ix)\b(?:(?:absence|disappearance|elimination|annihilation)|"
        rf"(?:complete|full)\s+(?:dissolution|removal))\s+of\s+"
        rf"(?!\s*(?:difference|change|variation)\b)"
        rf"(?:[a-z0-9]+\s+){{0,12}}{entity_pattern}"
    )
    negative_predicate = re.compile(
        rf"(?ix){entity_pattern}"
        rf"(?:\s+(?:and|or)(?:\s+[a-z0-9]+){{1,8}})?"
        rf"\s+(?:was|were|is|are|has\s+been|have\s+been)\s+"
        rf"(?:[a-z0-9]+\s+){{0,5}}"
        rf"(?:absent|missing|eliminated|annihilated|dissolved|removed|"
        rf"non\s+existent|not\s+(?:observed|detected|found|present))\b"
    )
    quantified_subject = re.compile(
        rf"(?ix)\b(?:majority|fraction|portion|some|many|most)\s+of\s+"
        rf"{entity_pattern}"
    )
    partial_qualifier = re.compile(
        r"(?ix)\b(?:partial|partially|partly|incomplete|incompletely)\b"
    )
    for row in evidence:
        raw = str(row or "").strip()
        if not raw or raw.startswith("|"):
            continue
        folded = _scientific_fold(raw)
        if direct_prefix.search(folded):
            return True
        nominal_match = nominal_prefix.search(folded)
        if nominal_match is not None:
            prefix = folded[max(0, nominal_match.start() - 24) : nominal_match.start()]
            if not partial_qualifier.search(prefix):
                return True
        predicate_match = negative_predicate.search(folded)
        if (
            predicate_match is not None
            and not partial_qualifier.search(predicate_match.group())
            and not quantified_subject.search(folded)
        ):
            return True
    return False


def _structure_subject_tokens(value: Any) -> frozenset[str]:
    """Normalize an entity/feature subject without inventing an ontology."""

    tokens: set[str] = set()
    for token in _scientific_fold(value).split():
        if token in _STRUCTURE_ENTITY_DESCRIPTOR_TOKENS:
            continue
        if len(token) > 4 and token.endswith("ies"):
            token = token[:-3] + "y"
        elif len(token) > 3 and token.endswith("es"):
            token = token[:-2]
        elif len(token) > 2 and token.endswith("s"):
            token = token[:-1]
        if token:
            tokens.add(token)
    return frozenset(tokens)


def _negated_sibling_feature(
    entity: dict[str, Any],
    features: Sequence[dict[str, Any]],
    entity_evidence: Sequence[str],
) -> dict[str, Any] | None:
    """Return a same-assertion feature that proves entity removal/absence."""

    entity_subject = _structure_subject_tokens(entity.get("name_raw"))
    if not entity_subject:
        return None
    normalized_entity_evidence = {
        normalize_evidence_text(row) for row in entity_evidence if str(row).strip()
    }
    for feature in features:
        if not isinstance(feature, dict) or not _is_negated_structure_feature(feature):
            continue
        feature_subject = _structure_subject_tokens(
            feature.get("feature_name_raw")
        )
        if not entity_subject & feature_subject:
            continue
        feature_evidence = _feature_evidence(feature, entity_evidence)
        normalized_feature_evidence = {
            normalize_evidence_text(row)
            for row in feature_evidence
            if str(row).strip()
        }
        if normalized_entity_evidence & normalized_feature_evidence:
            return feature
    return None


def _structure_entity_subject_tokens(entity: dict[str, Any]) -> frozenset[str]:
    """Return only the source identity tokens that can name a numeric feature."""

    tokens = _scientific_fold(entity.get("name_raw")).split()
    return frozenset(
        token
        for token in tokens
        if token not in _STRUCTURE_ENTITY_DESCRIPTOR_TOKENS
    )


def _is_generic_structure_entity_projection(
    entity: dict[str, Any], evidence: Sequence[str]
) -> bool:
    """Return whether a prose entity is only a generic carrier noun."""

    if entity.get("features") or not evidence or _has_table_evidence(evidence):
        return False
    name = _scientific_fold(entity.get("name_raw")).strip()
    if name not in _STRUCTURE_GENERIC_ENTITY_NAMES:
        return False
    expression = _scientific_fold(entity.get("raw_expression")).strip()
    return not expression or expression == name


def _table_binary_structure_entity_feature(
    entity: dict[str, Any], evidence: Sequence[str]
) -> dict[str, Any] | None:
    """Convert a table ``Yes`` cell mis-shaped as an entity into presence."""

    if entity.get("features") or not _has_table_evidence(evidence):
        return None
    name = str(entity.get("name_raw") or "").strip()
    normalized_name = _scientific_fold(name)
    if not name or normalized_name in _UNKNOWN_ENTITY:
        return None
    if _scientific_fold(entity.get("raw_expression")) != "yes":
        return None
    return {
        "feature_name_raw": f"{name} presence",
        "value_kind": "categorical",
        "value_raw": "Yes",
        "data_nature": "reported",
        "source_evidence": list(evidence),
    }


def _quantitative_feature_names_entity(
    feature: dict[str, Any], entity: dict[str, Any]
) -> bool:
    if not _is_quantitative_structure_feature(feature):
        return False
    subject = _structure_entity_subject_tokens(entity)
    feature_tokens = frozenset(
        _scientific_fold(feature.get("feature_name_raw")).split()
    )
    return bool(subject) and subject <= feature_tokens


def _is_location_only_structure_context(
    entities: Sequence[dict[str, Any]], features: Sequence[dict[str, Any]]
) -> bool:
    if entities or not features:
        return False
    return all(
        not _is_quantitative_structure_feature(feature)
        and _scientific_fold(feature.get("feature_name_raw"))
        in _STRUCTURE_CONTEXT_ONLY_FEATURES
        for feature in features
    )


def _qualitative_structure_shadow_issue(
    fact: StructureFact,
    feature: dict[str, Any],
    *,
    entity: dict[str, Any] | None,
    evidence: Sequence[str],
) -> PromotionIssue:
    return _promotion_issue(
        fact,
        code="promotion_structure_qualitative_projection_quarantined",
        message=(
            "A named structural entity already carried the source assertion; an "
            "additional non-quantitative descriptive projection was isolated."
        ),
        expected={
            "independent_atomic_feature": False,
            "named_entity_preserved": True,
            "audit_preserved": True,
        },
        actual={
            "removed": deepcopy(feature),
            "entity": deepcopy(entity),
            "reason": "qualitative_projection_shadow",
        },
        evidence=list(evidence),
    )


def _gate_structure_fact(
    fact: StructureFact,
) -> tuple[StructureFact | None, list[PromotionIssue]]:
    if fact.fact_type != "structure_observation":
        return fact, []
    before_fact = fact.model_dump()
    data = deepcopy(fact.data)
    fallback = _fact_evidence(fact)
    entities: list[dict[str, Any]] = []
    features: list[dict[str, Any]] = []
    negated_entity_shadows: list[tuple[dict[str, Any], str]] = []
    issues: list[PromotionIssue] = []
    top_level_features = [
        feature
        for feature in data.get("features") or []
        if isinstance(feature, dict)
    ]

    for entity in data.get("entities") or []:
        if not isinstance(entity, dict):
            continue
        row = deepcopy(entity)
        entity_evidence = _feature_evidence(row, fallback)
        name = row.get("name_raw")
        raw_expression = row.get("raw_expression")
        binary_feature = _table_binary_structure_entity_feature(
            row, entity_evidence
        )
        if binary_feature is not None:
            features.append(binary_feature)
            issues.append(
                _promotion_issue(
                    fact,
                    code="promotion_structure_table_binary_entity_normalized",
                    message=(
                        "A binary table cell was emitted as a bare Structure "
                        "entity; it was normalized to a source-literal presence fact."
                    ),
                    expected={
                        "table_binary_value": "Yes",
                        "independent_bare_entity": False,
                        "audit_preserved": True,
                    },
                    actual={
                        "before": deepcopy(entity),
                        "after": deepcopy(binary_feature),
                        "reason": "table_yes_entity_to_presence_feature",
                    },
                    evidence=entity_evidence,
                )
            )
            continue
        if _is_generic_structure_entity_projection(row, entity_evidence):
            issues.append(
                _promotion_issue(
                    fact,
                    code="promotion_structure_generic_entity_quarantined",
                    message=(
                        "A generic carrier noun was emitted as an independent "
                        "Structure entity without naming a material feature."
                    ),
                    expected={
                        "independent_structure_entity": False,
                        "generic_carrier_noun": True,
                        "audit_preserved": True,
                    },
                    actual={
                        "removed": deepcopy(entity),
                        "reason": "generic_entity_only_projection",
                    },
                    evidence=entity_evidence,
                )
            )
            continue
        if _STRUCTURE_BARE_ELEMENT_ENTITY.fullmatch(
            _scientific_fold(name).strip()
        ) and not row.get("features"):
            issues.append(
                _promotion_issue(
                    fact,
                    code="promotion_structure_element_projection_quarantined",
                    message=(
                        "A bare chemical element token was emitted as a Structure "
                        "entity; the source assertion is more consistent with a "
                        "composition or partitioning statement."
                    ),
                    expected={
                        "independent_structure_entity": False,
                        "composition_axis_for_elemental_claim": True,
                        "audit_preserved": True,
                    },
                    actual={
                        "removed": deepcopy(entity),
                        "reason": "bare_element_token_in_structure",
                    },
                    evidence=entity_evidence,
                )
            )
            continue
        if _scientific_fold(name) in _UNKNOWN_ENTITY:
            if _payload_grounded(raw_expression, entity_evidence):
                previous = deepcopy(row)
                row["name_raw"] = str(raw_expression).strip()
                row["canonical_name"] = None
                issues.append(
                    _promotion_issue(
                        fact,
                        code="promotion_structure_entity_name_recovered",
                        message=(
                            "A placeholder entity name was replaced by its existing "
                            "source-literal raw expression."
                        ),
                        expected={"entity_name": "source-literal structural entity"},
                        actual={"before": previous, "after": deepcopy(row)},
                        evidence=entity_evidence,
                    )
                )
            else:
                issues.append(
                    _promotion_issue(
                        fact,
                        code="promotion_structure_entity_unsupported",
                        message=(
                            "A placeholder structural entity lacked a "
                            "source-literal identity."
                        ),
                        expected={"entity_name_grounded": True},
                        actual={
                            "removed": deepcopy(entity),
                            "fact_before": before_fact,
                        },
                        evidence=entity_evidence,
                    )
                )
                continue
        elif not (
            _payload_grounded(name, entity_evidence)
            or _payload_grounded(raw_expression, entity_evidence)
        ):
            issues.append(
                _promotion_issue(
                    fact,
                    code="promotion_structure_entity_unsupported",
                    message=(
                        "A structural entity identity was absent from its cited "
                        "evidence."
                    ),
                    expected={"entity_name_or_raw_expression_grounded": True},
                    actual={
                        "removed": deepcopy(entity),
                        "fact_before": before_fact,
                    },
                    evidence=entity_evidence,
                )
            )
            continue
        if _is_negated_structure_entity(row):
            negated_entity_shadows.append(
                (deepcopy(row), "negated_entity_was_not_positive_presence")
            )
            continue
        if _entity_negated_by_prose_evidence(row, entity_evidence):
            negated_entity_shadows.append(
                (deepcopy(row), "entity_local_prose_negation")
            )
            continue
        if _negated_sibling_feature(
            row, top_level_features, entity_evidence
        ) is not None:
            negated_entity_shadows.append(
                (deepcopy(row), "negated_sibling_feature")
            )
            continue
        nested: list[dict[str, Any]] = []
        for feature in row.get("features") or []:
            if not isinstance(feature, dict):
                continue
            feature_evidence = _feature_evidence(feature, entity_evidence)
            original_feature = deepcopy(feature)
            completed_count = _complete_structure_count_feature(
                feature, feature_evidence
            )
            if completed_count is not None:
                feature, relation = completed_count
                issues.append(
                    _promotion_issue(
                        fact,
                        code="promotion_structure_count_relation_completed",
                        message=(
                            "A porosity/specimen count was retained only after its "
                            "source-literal numerator/denominator relation was "
                            "completed; the denominator will not be materialized "
                            "as a separate Structure fact."
                        ),
                        expected={
                            "complete_count_relation": True,
                            "standalone_denominator": False,
                            "audit_preserved": True,
                        },
                        actual={
                            "before": original_feature,
                            "relation": relation,
                            "reason": "source_literal_count_relation",
                        },
                        evidence=feature_evidence,
                    )
                )
            precision_risk = _structure_feature_precision_risk(
                feature,
                feature_evidence,
                has_entity=True,
            )
            if precision_risk is not None:
                issue_code, reason = precision_risk
                issues.append(
                    _promotion_issue(
                        fact,
                        code=issue_code,
                        message=(
                            "A Structure feature was isolated because its value "
                            "did not encode an atomic structural result."
                        ),
                        expected={
                            "structural_result": True,
                            "audit_preserved": True,
                        },
                        actual={
                            "removed": deepcopy(feature),
                            "entity": deepcopy(entity),
                            "reason": reason,
                            **(
                                {
                                    "decision_key": _structure_assertion_decision_key_v205(
                                        fact, feature, feature_evidence, reason
                                    )
                                }
                                if issue_code
                                == "structure_assertion_projection_quarantined"
                                else {}
                            ),
                        },
                        evidence=feature_evidence,
                    )
                )
            elif not _payload_grounded(feature.get("value_raw"), feature_evidence):
                issues.append(
                    _promotion_issue(
                        fact,
                        code="promotion_structure_feature_unsupported",
                        message=(
                            "A structural feature value was absent from its cited "
                            "evidence."
                        ),
                        expected={"feature_value_grounded": True},
                        actual={
                            "removed": deepcopy(feature),
                            "entity": deepcopy(entity),
                        },
                        evidence=feature_evidence,
                    )
                )
            elif not _is_quantitative_structure_feature(
                feature
            ) and not _is_negated_structure_feature(feature):
                issues.append(
                    _qualitative_structure_shadow_issue(
                        fact,
                        feature,
                        entity=entity,
                        evidence=feature_evidence,
                    )
                )
            else:
                nested.append(deepcopy(feature))
        row["features"] = nested
        entity_type = _scientific_fold(row.get("entity_type") or "other")
        entity_evidence_text = "\n".join(entity_evidence)
        if (
            entity_type in _NONATOMIC_STRUCTURE_ENTITY_TYPES
            and not any(
                _is_quantitative_structure_feature(feature)
                or _is_negated_structure_feature(feature)
                for feature in nested
            )
            and not _NEGATED_STRUCTURE_FEATURE.search(entity_evidence_text)
        ):
            issues.append(
                _promotion_issue(
                    fact,
                    code="promotion_structure_nonatomic_entity_quarantined",
                    message=(
                        "A generic entity category without an atomic quantitative "
                        "or negated structural payload was isolated."
                    ),
                    expected={
                        "entity_type": "named material entity ontology",
                        "independent_atomic_payload": True,
                    },
                    actual={
                        "removed": deepcopy(row),
                        "reason": "nonatomic_generic_entity_type",
                    },
                    evidence=entity_evidence,
                )
            )
            continue
        entities.append(row)

    for feature in data.get("features") or []:
        if not isinstance(feature, dict):
            continue
        feature_evidence = _feature_evidence(feature, fallback)
        original_feature = deepcopy(feature)
        completed_count = _complete_structure_count_feature(
            feature, feature_evidence
        )
        if completed_count is not None:
            feature, relation = completed_count
            issues.append(
                _promotion_issue(
                    fact,
                    code="promotion_structure_count_relation_completed",
                    message=(
                        "A porosity/specimen count was retained only after its "
                        "source-literal numerator/denominator relation was "
                        "completed; the denominator will not be materialized as a "
                        "separate Structure fact."
                    ),
                    expected={
                        "complete_count_relation": True,
                        "standalone_denominator": False,
                        "audit_preserved": True,
                    },
                    actual={
                        "before": original_feature,
                        "relation": relation,
                        "reason": "source_literal_count_relation",
                    },
                    evidence=feature_evidence,
                )
            )
        precision_risk = _structure_feature_precision_risk(
            feature,
            feature_evidence,
            has_entity=False,
        )
        if precision_risk is not None:
            issue_code, reason = precision_risk
            issues.append(
                _promotion_issue(
                    fact,
                    code=issue_code,
                    message=(
                        "A Structure feature was isolated because its value did "
                        "not encode an atomic structural result."
                    ),
                    expected={
                        "structural_result": True,
                        "audit_preserved": True,
                    },
                    actual={
                        "removed": deepcopy(feature),
                        "reason": reason,
                        **(
                            {
                                "decision_key": _structure_assertion_decision_key_v205(
                                    fact, feature, feature_evidence, reason
                                )
                            }
                            if issue_code
                            == "structure_assertion_projection_quarantined"
                            else {}
                        ),
                    },
                    evidence=feature_evidence,
                )
            )
        elif not _payload_grounded(feature.get("value_raw"), feature_evidence):
            issues.append(
                _promotion_issue(
                    fact,
                    code="promotion_structure_feature_unsupported",
                    message=(
                        "A structural feature value was absent from its cited "
                        "evidence."
                    ),
                    expected={"feature_value_grounded": True},
                    actual={
                        "removed": deepcopy(feature),
                        "fact_before": before_fact,
                    },
                    evidence=feature_evidence,
                )
            )
        elif entities and not _is_quantitative_structure_feature(
            feature
        ) and not _is_negated_structure_feature(feature):
            issues.append(
                _qualitative_structure_shadow_issue(
                    fact,
                    feature,
                    entity=None,
                    evidence=feature_evidence,
                )
            )
        else:
            features.append(deepcopy(feature))
    presence_shadows: list[dict[str, Any]] = []
    if features:
        retained_entities: list[dict[str, Any]] = []
        for entity in entities:
            original_entity = next(
                (
                    row
                    for row in data.get("entities") or []
                    if isinstance(row, dict)
                    and _scientific_fold(row.get("name_raw"))
                    == _scientific_fold(entity.get("name_raw"))
                ),
                entity,
            )
            if (
                not (original_entity.get("features") or [])
                and any(
                    _quantitative_feature_names_entity(feature, entity)
                    for feature in features
                )
            ):
                presence_shadows.append(deepcopy(entity))
                continue
            retained_entities.append(entity)
        entities = retained_entities

    data["entities"] = entities
    data["features"] = features
    cleaned_preview = (
        fact.model_copy(deep=True, update={"data": data})
        if entities or features
        else None
    )
    for removed, reason in negated_entity_shadows:
        issues.append(
            _promotion_issue(
                fact,
                code="promotion_structure_negated_entity_quarantined",
                message=(
                    "An explicitly absent structural entity cannot also be "
                    "promoted as positive entity presence."
                ),
                expected={
                    "positive_entity_presence": False,
                    "negative_feature_preserved_when_available": True,
                    "audit_preserved": True,
                },
                actual={
                    "removed": removed,
                    "survivor_before": before_fact,
                    "survivor_after": (
                        cleaned_preview.model_dump()
                        if cleaned_preview is not None
                        else None
                    ),
                    "reason": reason,
                },
                evidence=_feature_evidence(removed, fallback),
            )
        )
    if _is_location_only_structure_context(entities, features):
        issues.append(
            _promotion_issue(
                fact,
                code="promotion_structure_context_quarantined",
                message=(
                    "A Structure observation contained only a location, region, "
                    "or area label without an independently reported material "
                    "entity or quantitative feature."
                ),
                expected={
                    "independent_structure_payload": True,
                    "audit_preserved": True,
                },
                actual={
                    "removed": before_fact,
                    "reason": "location_only_structure_context",
                },
            )
        )
        return None, issues
    if not entities and not features:
        issues.append(
            _promotion_issue(
                fact,
                code="promotion_structure_observation_quarantined",
                message=(
                    "The Structure observation had no source-grounded atomic entity "
                    "or feature after field-level verification."
                ),
                expected={"grounded_entity_or_feature_count": ">=1"},
                actual={"removed": before_fact},
            )
        )
        return None, issues
    cleaned = cleaned_preview
    assert cleaned is not None
    for removed in presence_shadows:
        issues.append(
            _promotion_issue(
                fact,
                code="promotion_structure_entity_presence_shadow_quarantined",
                message=(
                    "A quantitative Structure feature already named this entity; "
                    "the extra presence-only projection was isolated."
                ),
                expected={
                    "quantitative_feature_survived": True,
                    "independent_presence_projection": False,
                    "audit_preserved": True,
                },
                actual={
                    "removed": removed,
                    "survivor_before": before_fact,
                    "survivor_after": cleaned.model_dump(),
                    "reason": "entity_presence_dominated_by_named_numeric_feature",
                },
            )
        )
    return cleaned, issues


# A high-recall chunk often turns one comparative sentence into a set of
# apparently independent Structure features (for example ``volume fraction
# increased``, ``grain morphology larger``, and ``distribution differed``).
# Those strings are source-grounded, but they are not atomic measurements and
# are especially prone to being projected onto the wrong material.  Keep the
# vocabulary deliberately small and apply it only to prose, non-numeric
# features.  Numeric values and explicit presence/absence assertions remain
# eligible for the formal Structure ledger.
_STRUCTURE_COMPARATIVE_PROJECTION = re.compile(
    r"(?ix)\b(?:"
    r"higher|lower|greater|smaller|larger|fewer|more|less|similar|different|"
    r"comparable|compared|versus|relative\s+to|than|"
    r"increase(?:d|s)?|decrease(?:d|s)?|reduc(?:ed|tion)|improv(?:ed|ement)|"
    r"enhanc(?:ed|ement)|trend|ratio|difference|disparity|"
    r"variation|range|"
    r"prefer(?:red|ential)|suggest(?:s|ing|ed)?|indic(?:ate|ates|ating)|"
    r"attribut(?:e|ed|es|ing)|caus(?:e|ed|es|ing)|due\s+to|leading\s+to|"
    r"result(?:ed|s)?\s+in|contribut(?:e|ed|es|ing)|risk|likely|"
    r"relationship|correlation|mechanism|effect|influence|role|criterion|"
    r"threshold|behavio(?:u)?r)\b"
)
_STRUCTURE_DIRECT_PRESENCE = re.compile(
    r"(?ix)\b(?:"
    r"contain(?:s|ed|ing)?|compris(?:e|es|ed|ing)|consist(?:s|ed|ing)?|"
    r"present|presence|observ(?:e|ed|es|ing)|detect(?:ed|s|ing)?|"
    r"identif(?:y|ied|ies|ying)|form(?:ed|s|ing)?|"
    r"exhibit(?:ed|s|ing)?|show(?:ed|s|ing)?|reveal(?:ed|s|ing)?|"
    r"precipitat(?:e|ed|es|ing|ion)|mainly|primarily|consist(?:s|ed|ing)?|"
    r"separat(?:ed|es|ing)\b"
    r")\b"
)

# A source-grounded sentence can still be an interpretation rather than a
# directly observed Structure assertion (``likely a martensitic phase``,
# ``indicative of grain refinement``, ``may promote nucleation``).  The model
# often projects the interpreted noun phrase as a second entity.  Keep this
# cue set deliberately narrow: it never applies to numeric features, explicit
# positive/negative observations, or a named entity that has a direct
# assertion in the same evidence span.
_STRUCTURE_INFERENTIAL_PROJECTION = re.compile(
    r"(?ix)\b(?:"
    r"likely|possibly|possible|suggest(?:s|ed|ing)?|"
    r"indicative|indicat(?:es|ed|ing)?|may|might|could|"
    r"expected|assuming|inferred|inference|evidently|"
    r"imply|implies|implied|consistent\s+with|"
    r"attribut(?:e|ed|es|ing)|due\s+to|result(?:ed|s)?\s+in|"
    r"promot(?:e|ed|es|ing)|caus(?:e|ed|es|ing)|because|"
    r"therefore|thus|hence|provid(?:e|es|ed)\s+evidence|"
    r"which\s+(?:can|could|may|might)\b|"
    r"\b(?:can|could|would|might|may)\s+be\b|"
    r"\b(?:can|could|would)\s+(?:form|occur|develop|deploy|produce|lead)\b|"
    r"\bif\s+(?:the|a|an|this|these|those)\b|\bhypothetical(?:ly)?\b|"
    r"\bpotential(?:ly)?\b"
    r")\b"
)
_STRUCTURE_DIRECT_ASSERTION = re.compile(
    r"(?ix)(?:"
    r"\b(?:contain(?:s|ed|ing)?|compris(?:e|es|ed|ing)?|"
    r"consist(?:s|ed|ing)?|present|presence|observ(?:e|ed|es|ing)?|"
    r"detect(?:ed|s|ing)?|identif(?:ied|y|ies|ying)|"
    r"form(?:ed|s|ing|ation)|"
    r"exist(?:s|ed|ing)?|exhibit(?:ed|s|ing)?|found|embedded|"
    r"located|distributed|revealed|confirm(?:s|ed|ing)?|"
    r"detail(?:s|ed|ing)?|show(?:s|ed|ing)?|mainly|primarily|"
    r"there\s+(?:is|are)|such\s+as)\b|"
    r"\b(?:was|were|is|are)\s+(?:formed|observed|detected|identified|"
    r"present|found|located|distributed|embedded)\b|"
    r"\b(?:consisting|composed)\s+of\b"
    r")"
)

# A few Structure observations are expressed as a change rather than with an
# ``observed/found`` verb (for example ``the gamma phase decreased`` or
# ``phase evolution from alpha to gamma``).  These are still direct source
# assertions and must not be treated as bare noun-phrase projections.  Keep
# this allow-list separate from ``_STRUCTURE_DIRECT_ASSERTION`` so the
# inferential gate above remains conservative: ``suggested dissolution`` is
# still inferential even though ``dissolution`` is a change noun.  Do not put
# comparative adjectives (``higher``, ``different``, ``larger``, ... ) here:
# a phrase such as ``the orientation distribution of the transformed phase``
# mentions an entity in comparison/description context but does not assert
# that the extractor's entity is a standalone observed material constituent.
_STRUCTURE_DIRECT_CHANGE_ASSERTION = re.compile(
    r"(?ix)\b(?:"
    # Keep inflected verb forms that cannot be mistaken for a noun phrase.
    # ``appears`` in ``the image appears ... with equiaxed grains`` and
    # ``precipitates`` in ``cubical gamma-prime precipitates`` are not direct
    # assertions about the extracted entity.
    r"appear(?:ed|ing)?|"
    r"emerg(?:ed|es|ing)?|"
    r"increas(?:e|ed|es|ing)|"
    r"decreas(?:e|ed|es|ing)|"
    r"coarsen(?:ed|ing)?|"
    r"refin(?:e|ed|es|ing|ement)|"
    r"evol(?:ve|ved|ves|ving|ution)|"
    r"grow(?:s|th|ing|n)?|"
    r"nucleat(?:e|ed|ing)|"
    r"precipitat(?:ed|ing)|"
    r"segregat(?:e|ed|ing)|"
    r"dissol(?:ve|ved|ving)|"
    r"remov(?:e|ed|es|ing|al)"
    r"|annihilat(?:e|ed|es|ing|ion)"
    r")\b"
)

# Comparative measurement grammar can assert the measured entity even when
# the sentence has no ``observed/found`` verb (``the volume fraction of ZrC
# phases was higher ...``).  This is intentionally limited to measurement
# heads; broad comparative adjectives must not authorize arbitrary noun
# phrases such as ``the different orientation distribution of the transformed
# alpha phase``.
_STRUCTURE_MEASURED_ENTITY_CONTEXT = re.compile(
    r"(?ix)\b(?:volume\s+fraction|fraction|content|concentration|"
    r"amount|density|size|thickness|spacing|width|length|diameter|"
    r"morphology|number|count)\s+of\s+$"
)


_STRUCTURE_HAD_ASSERTION_BLOCKER = re.compile(
    r"(?ix)\b(?:likely|possible|possibly|suggest(?:s|ed|ing)?|"
    r"indicative|indicat(?:es|ed|ing)?|expected|evidence|"
    r"assuming|inferred|inference|possibility|potential|"
    r"reason|effect|role|because|due\s+to|result(?:ed|s)?\s+in)\b"
)

_STRUCTURE_DIRECT_OBJECT_CHANGE = re.compile(
    r"(?ix)\b(?:dissolution|dissolv(?:e|ed|ing)|annihilation|"
    r"annihilat(?:e|ed|ing)|removal|remov(?:e|ed|ing))\s+of\s+"
)


def _structure_had_asserts_label(
    folded: str,
    label_pattern: re.Pattern[str],
) -> bool:
    """Return whether a bounded ``had/has/have`` clause asserts *label*.

    ``had`` is common in real observations (``the sample had columnar
    grains``), but a broad context search incorrectly authorizes a noun that
    follows an inferential clause (``had very low beta content suggesting a
    martensitic transformation``).  Require a short object span and reject
    interpretation/evidence cues between the auxiliary and the label.
    """

    matches = list(label_pattern.finditer(folded))
    for match in matches:
        prefix = folded[max(0, match.start() - 90) : match.start()]
        for had_match in re.finditer(r"(?i)\b(?:had|has|have)\b", prefix):
            between = prefix[had_match.end() :]
            if _STRUCTURE_HAD_ASSERTION_BLOCKER.search(between):
                continue
            tokens = re.findall(r"[a-z0-9]+", between)
            if len(tokens) <= 5:
                return True

        # The entity can also be the subject of the clause (``grains had a
        # columnar morphology``).  Only inspect a short suffix so a later
        # unrelated ``had`` cannot authorize the entity.
        suffix = folded[match.end() : match.end() + 70]
        if re.search(
            r"(?i)\b(?:had|has|have)\b",
            suffix,
        ) and not _STRUCTURE_HAD_ASSERTION_BLOCKER.search(suffix):
            return True
    return False


def _structure_evidence_has_direct_assertion(
    label: Any,
    evidence: Sequence[str],
) -> bool:
    """Return whether *label* is tied to a direct source assertion.

    The surrounding evidence may contain an inference cue elsewhere in the
    same paragraph.  Looking in a bounded window around the named entity (or
    feature) prevents a direct assertion about one noun from accidentally
    authorizing a second, inferred noun phrase.
    """

    folded_label = _scientific_fold(label)
    if not folded_label:
        return False
    escaped = re.escape(folded_label).replace(r"\ ", r"\s+")
    label_pattern = re.compile(
        rf"(?<![a-z0-9]){escaped}(?:s|es)?(?![a-z0-9])",
        flags=re.IGNORECASE,
    )
    for row in evidence:
        folded = _scientific_fold(row)
        if not folded:
            continue
        matches = list(label_pattern.finditer(folded))
        if not matches:
            continue
        for match in matches:
            # Keep the assertion window local to the named payload.  A broad
            # paragraph window lets ``primarily``/``observed`` about one phase
            # authorize a second phase in a comparative sentence.
            context_start = max(0, match.start() - 55)
            context = folded[context_start : match.end() + 55]
            direct_match = _STRUCTURE_DIRECT_ASSERTION.search(context)
            if direct_match:
                direct_token = _scientific_fold(direct_match.group()).strip()
                if direct_token in {"mainly", "primarily"}:
                    label_offset = match.start() - context_start
                    between = context[direct_match.end() : label_offset]
                    # A broad ``primarily responsible ... while <other
                    # phase>`` clause does not assert the later phase.  Keep
                    # only the compact ``primarily <named phase>`` grammar.
                    if (
                        len(re.findall(r"[a-z0-9]+", between)) <= 3
                        and not re.search(r"(?i)\b(?:while|where|but|although)\b", between)
                    ):
                        return True
                else:
                    return True
            if _structure_had_asserts_label(folded, label_pattern):
                return True
            object_change = _STRUCTURE_DIRECT_OBJECT_CHANGE.search(
                folded[max(0, match.start() - 90) : match.start()]
            )
            if object_change is not None:
                object_tail = folded[match.start() : match.end() + 2]
                if label_pattern.search(object_tail):
                    return True
    return False


def _structure_entity_inferential_projection(
    entity: dict[str, Any],
    evidence: Sequence[str],
) -> bool:
    """Identify an entity emitted only from an inferential interpretation."""

    if entity.get("features"):
        # A numeric/negative child feature is an independent payload; retain
        # the entity even if the surrounding prose also contains interpretation.
        return False
    if not evidence or not _STRUCTURE_INFERENTIAL_PROJECTION.search(
        "\n".join(evidence)
    ):
        return False
    label = entity.get("name_raw") or entity.get("raw_expression")
    return bool(label) and not _structure_evidence_has_direct_assertion(
        label, evidence
    )


def _structure_entity_unasserted_projection(
    entity: dict[str, Any],
    evidence: Sequence[str],
) -> bool:
    """Identify a bare Structure entity with no local source assertion.

    The extractor frequently turns a noun mentioned in a caption, parenthetic
    label, or cross-reference into a positive presence claim.  Such a claim is
    not safe to promote merely because the literal is present in the OCR.  A
    direct observation verb (or a direct structural change verb) must occur in
    the same bounded evidence window.  Markdown/HTML table rows are excluded:
    their column/row binding is handled by the table-aware gates downstream.
    """

    if entity.get("features") or not evidence:
        return False
    if any(
        str(row).lstrip().startswith("|") or "<table" in str(row).casefold()
        for row in evidence
    ):
        return False
    labels = [
        value
        for value in (entity.get("name_raw"), entity.get("raw_expression"))
        if str(value or "").strip()
    ]
    labels = list(dict.fromkeys(str(value) for value in labels))
    if not labels:
        return False
    for label in labels:
        if _structure_evidence_has_direct_assertion(label, evidence):
            return False
        folded_label = _scientific_fold(label)
        escaped = re.escape(folded_label).replace(r"\ ", r"\s+")
        label_pattern = re.compile(
            rf"(?<![a-z0-9]){escaped}(?:s|es)?(?![a-z0-9])",
            flags=re.IGNORECASE,
        )
        for row in evidence:
            folded = _scientific_fold(row)
            for match in label_pattern.finditer(folded):
                context = folded[max(0, match.start() - 55) : match.end() + 55]
                if _STRUCTURE_DIRECT_CHANGE_ASSERTION.search(context):
                    return False
                prefix = folded[max(0, match.start() - 80) : match.start()]
                if _STRUCTURE_MEASURED_ENTITY_CONTEXT.search(prefix):
                    return False
    return True


def _structure_projection_feature_is_comparative(
    fact: StructureFact,
    feature: dict[str, Any],
) -> bool:
    """Return whether one qualitative prose feature is a comparative shadow."""

    if _is_quantitative_structure_feature(feature) or _is_negated_structure_feature(
        feature
    ):
        return False
    evidence = _feature_evidence(feature, _fact_evidence(fact))
    if not evidence or _has_table_evidence(evidence):
        return False
    feature_text = " ".join(
        str(feature.get(key) or "")
        for key in ("feature_name_raw", "value_raw", "raw_expression")
    )
    if not _STRUCTURE_COMPARATIVE_PROJECTION.search(feature_text):
        return False
    # A sentence such as ``oxides were mainly ...`` is comparative-context
    # prose but still declares positive phase presence.  Do not quarantine it
    # unless the feature itself is a comparison/interpretation rather than the
    # named phase assertion.
    feature_name = _scientific_fold(feature.get("feature_name_raw"))
    if re.search(
        r"(?i)\b(?:presence|phase|phases|morphology|microstructure|"
        r"crystal\s+structure|coherency|lattice|grain\s+size|pore\s+size)\b",
        feature_name,
    ) and _STRUCTURE_DIRECT_PRESENCE.search(" ".join(evidence)):
        return False
    # Explicit comparative measurements remain atomic even when the value is
    # expressed as ``fewer variants than the bulk`` rather than as a scalar.
    # The subject must name a measurable structural population/geometry; broad
    # effect or causal prose does not qualify.
    if re.search(
        r"(?i)\b(?:variant|grain|pore|particle|precipitate|lath|"
        r"diameter|width|length|thickness|spacing|density|fraction|"
        r"misorientation|orientation|count)\b",
        feature_name,
    ) and _STRUCTURE_DIRECT_PRESENCE.search(" ".join(evidence)):
        return False
    return True


def _structure_entity_is_comparative_shadow(
    entity: dict[str, Any], evidence: Sequence[str]
) -> bool:
    """Drop an entity mentioned only as the comparator side of a prose claim."""

    if entity.get("features") or not evidence or _has_table_evidence(evidence):
        return False
    joined = " ".join(str(row) for row in evidence)
    if not _STRUCTURE_COMPARATIVE_PROJECTION.search(joined):
        return False
    label = str(entity.get("name_raw") or entity.get("raw_expression") or "").strip()
    if not label:
        return False
    escaped = re.escape(_scientific_fold(label)).replace(r"\ ", r"\s+")
    if not re.search(
        rf"(?ix)(?:\bthan\b|\bversus\b|\bcompared\s+(?:to|with)\b|"
        rf"\brelative\s+to\b|\bthat\s+of\b).{{0,90}}"
        rf"(?<![a-z0-9]){escaped}(?![a-z0-9])",
        _scientific_fold(joined),
    ):
        return False
    # Explicit ``mainly X``/``X was observed`` grammar proves positive phase
    # presence even when the surrounding sentence compares two materials.
    direct = re.compile(
        rf"(?ix)\b(?:contain(?:s|ed|ing)?|present|observ(?:ed|e|es|ing)|"
        rf"detect(?:ed|s|ing)?|identif(?:ied|y|ies|ying)|form(?:ed|s|ing)?|"
        rf"exhibit(?:ed|s|ing)?|show(?:ed|s|ing)?|mainly|primarily|"
        rf"precipitat(?:e|ed|es|ing|ion))\b.{{0,70}}"
        rf"(?<![a-z0-9]){escaped}(?![a-z0-9])"
    )
    return direct.search(_scientific_fold(joined)) is None


def _quarantine_structure_comparative_projections(
    facts: Sequence[AxisFact],
) -> tuple[list[AxisFact], list[PromotionIssue]]:
    """Isolate non-atomic comparative Structure projections with full audit."""

    accepted: list[AxisFact] = []
    issues: list[PromotionIssue] = []
    for fact in facts:
        if not isinstance(fact, StructureFact) or fact.fact_type != "structure_observation":
            accepted.append(fact)
            continue
        before = fact.model_dump()
        data = deepcopy(fact.data)
        fallback = _fact_evidence(fact)
        entities: list[dict[str, Any]] = []
        for entity in data.get("entities") or []:
            if not isinstance(entity, dict):
                continue
            entity_evidence = _feature_evidence(entity, fallback)
            if _structure_entity_is_comparative_shadow(entity, entity_evidence):
                issues.append(
                    _promotion_issue(
                        fact,
                        code="promotion_structure_comparative_entity_projection_quarantined",
                        message=(
                            "An entity mentioned only on the comparator side of a "
                            "prose comparison was isolated from the formal Structure ledger."
                        ),
                        expected={
                            "independent_positive_entity_assertion": False,
                            "audit_preserved": True,
                        },
                        actual={
                            "removed": deepcopy(entity),
                            "fact_before": before,
                            "reason": "comparator_side_only",
                        },
                        evidence=list(entity_evidence),
                    )
                )
                continue
            entities.append(entity)
        features: list[dict[str, Any]] = []
        for feature in data.get("features") or []:
            if not isinstance(feature, dict):
                continue
            feature_evidence = _feature_evidence(feature, fallback)
            if _structure_projection_feature_is_comparative(fact, feature):
                issues.append(
                    _promotion_issue(
                        fact,
                        code="promotion_structure_comparative_projection_quarantined",
                        message=(
                            "A qualitative comparative or interpretive Structure "
                            "projection was isolated; numeric and explicit presence "
                            "assertions remain eligible."
                        ),
                        expected={
                            "atomic_numeric_or_presence_fact": True,
                            "audit_preserved": True,
                        },
                        actual={
                            "removed": deepcopy(feature),
                            "fact_before": before,
                            "reason": "qualitative_comparative_projection",
                        },
                        evidence=list(feature_evidence),
                    )
                )
                continue
            features.append(feature)
        if not entities and not features:
            issues.append(
                _promotion_issue(
                    fact,
                    code="promotion_structure_comparative_observation_quarantined",
                    message=(
                        "A Structure observation contained only non-atomic comparative "
                        "projections after source-grounded precision gating."
                    ),
                    expected={"grounded_atomic_payload": True, "audit_preserved": True},
                    actual={"removed": before, "reason": "all_comparative_projections"},
                    evidence=list(fallback),
                )
            )
            continue
        if entities == (data.get("entities") or []) and features == (data.get("features") or []):
            accepted.append(fact)
            continue
        data["entities"] = entities
        data["features"] = features
        accepted.append(fact.model_copy(deep=True, update={"data": data}))
    return accepted, issues


_STRUCTURE_NUMERIC_COMPARATIVE_NAME = re.compile(
    r"(?ix)\b(?:"
    r"percent(?:age)?\s+(?:increase|decrease|change|difference|reduction|"
    r"amplification|effect)|"
    r"(?:increase|decrease|reduction|difference|discrepancy|variation|"
    r"disparity|amplification|retention|improvement|enhancement|change|growth|"
    r"ratio)\b(?:[^\n]{0,80}\b(?:relative|compared|versus|than|of)\b)?|"
    r"\b(?:relative|comparative)\s+(?:value|metric|quantity)\b"
    r")"
)
_STRUCTURE_NUMERIC_COMPARATIVE_VALUE = re.compile(
    r"(?ix)\b(?:higher|lower|greater|smaller|larger|more|less|"
    r"increased|decreased|reduced|compared|relative\s+to|versus|than)\b"
)


def _structure_numeric_comparative_reason(
    feature: dict[str, Any], evidence: Sequence[str]
) -> str | None:
    """Return a reason for a derived/comparative numeric Structure feature."""

    if not _is_quantitative_structure_feature(feature):
        return None
    name = str(feature.get("feature_name_raw") or "")
    value = str(feature.get("value_raw") or "")
    if _STRUCTURE_NUMERIC_COMPARATIVE_NAME.search(name):
        return "comparative_or_derived_feature_name"
    if (
        _numeric_tokens(value)
        and _STRUCTURE_NUMERIC_COMPARATIVE_VALUE.search(value)
    ):
        return "comparative_or_derived_value_literal"
    return None


def _quarantine_structure_numeric_comparative_projections(
    facts: Sequence[AxisFact],
) -> tuple[list[AxisFact], list[PromotionIssue]]:
    """Isolate numeric Structure deltas/variations from formal observations.

    Numeric values are usually retained by the qualitative comparison gate,
    but a field named ``percent increase relative to ...`` or ``melt-pool
    length variation`` is a relationship between observations, not an atomic
    structural measurement.  Keeping it in the Structure ledger invites
    owner/state fan-out.  The original feature and parent fact stay in audit.
    """

    accepted: list[AxisFact] = []
    issues: list[PromotionIssue] = []
    for fact in facts:
        if not isinstance(fact, StructureFact) or fact.fact_type != "structure_observation":
            accepted.append(fact)
            continue
        before = fact.model_dump()
        data = deepcopy(fact.data)
        removed: list[dict[str, Any]] = []
        entities: list[dict[str, Any]] = []
        for entity in data.get("entities") or []:
            if not isinstance(entity, dict):
                continue
            cleaned = deepcopy(entity)
            entity_name = str(entity.get("name_raw") or entity.get("raw_expression") or "")
            kept_features: list[dict[str, Any]] = []
            for feature in entity.get("features") or []:
                if not isinstance(feature, dict):
                    continue
                evidence = _feature_evidence(feature, _fact_evidence(fact))
                reason = _structure_numeric_comparative_reason(feature, evidence)
                if reason is None:
                    kept_features.append(feature)
                    continue
                removed.append(
                    {
                        "feature": deepcopy(feature),
                        "entity": entity_name,
                        "reason": reason,
                        "evidence": evidence,
                    }
                )
            cleaned["features"] = kept_features
            entities.append(cleaned)
        kept_top: list[dict[str, Any]] = []
        for feature in data.get("features") or []:
            if not isinstance(feature, dict):
                continue
            evidence = _feature_evidence(feature, _fact_evidence(fact))
            reason = _structure_numeric_comparative_reason(feature, evidence)
            if reason is None:
                kept_top.append(feature)
                continue
            removed.append(
                {
                    "feature": deepcopy(feature),
                    "entity": "",
                    "reason": reason,
                    "evidence": evidence,
                }
            )
        data["entities"] = entities
        data["features"] = kept_top
        if not removed:
            accepted.append(fact)
            continue
        after = fact.model_copy(deep=True, update={"data": data})
        if entities or kept_top:
            accepted.append(after)
        for row in removed:
            issues.append(
                _promotion_issue(
                    fact,
                    code="promotion_structure_comparative_numeric_projection_quarantined",
                    message=(
                        "A numeric Structure field represented a comparison, "
                        "delta, variation, or derived effect rather than an "
                        "atomic structural measurement; it was isolated with "
                        "the complete parent fact preserved."
                    ),
                    expected={
                        "atomic_structural_measurement": True,
                        "comparative_projection": False,
                        "audit_preserved": True,
                    },
                    actual={
                        "removed": row["feature"],
                        "entity": row["entity"],
                        "reason": row["reason"],
                        "before": before,
                        "after": after.model_dump() if entities or kept_top else None,
                    },
                    evidence=row["evidence"],
                )
            )
    return accepted, issues


def _quarantine_structure_inferential_projections(
    facts: Sequence[AxisFact],
) -> tuple[list[AxisFact], list[PromotionIssue]]:
    """Isolate entities/features emitted only from an interpretation cue.

    This is intentionally narrower than a generic ``source_type=inferred``
    filter.  Explicitly reported phases, grains, defects, and measurements may
    appear in a sentence that also contains causal discussion; they survive
    when the named payload has a direct assertion in its local evidence span.
    Only the extra noun/qualitative feature that lacks such an assertion is
    quarantined, with the complete original candidate retained in the issue
    audit.
    """

    accepted: list[AxisFact] = []
    issues: list[PromotionIssue] = []
    for fact in facts:
        if not isinstance(fact, StructureFact) or fact.fact_type != "structure_observation":
            accepted.append(fact)
            continue
        before = fact.model_dump()
        data = deepcopy(fact.data)
        fallback = _fact_evidence(fact)
        entities: list[dict[str, Any]] = []
        features: list[dict[str, Any]] = []

        for entity in data.get("entities") or []:
            if not isinstance(entity, dict):
                continue
            entity_evidence = _feature_evidence(entity, fallback)
            if _structure_entity_inferential_projection(entity, entity_evidence):
                issues.append(
                    _promotion_issue(
                        fact,
                        code="promotion_structure_inferential_projection_quarantined",
                        message=(
                            "A Structure entity was emitted from an inferential or "
                            "causal interpretation without a direct source assertion."
                        ),
                        expected={
                            "direct_entity_assertion": True,
                            "numeric_or_negative_payload": False,
                            "audit_preserved": True,
                        },
                        actual={
                            "removed": deepcopy(entity),
                            "fact_before": before,
                            "reason": "inferential_entity_without_direct_assertion",
                        },
                        evidence=list(entity_evidence),
                    )
                )
                continue
            entities.append(entity)

        for feature in data.get("features") or []:
            if not isinstance(feature, dict):
                continue
            feature_evidence = _feature_evidence(feature, fallback)
            if (
                not _is_quantitative_structure_feature(feature)
                and not _is_negated_structure_feature(feature)
                and _STRUCTURE_INFERENTIAL_PROJECTION.search(
                    "\n".join(feature_evidence)
                )
                and not _structure_evidence_has_direct_assertion(
                    feature.get("feature_name_raw") or feature.get("value_raw"),
                    feature_evidence,
                )
            ):
                issues.append(
                    _promotion_issue(
                        fact,
                        code="promotion_structure_inferential_projection_quarantined",
                        message=(
                            "A qualitative Structure feature was emitted from an "
                            "inferential or causal interpretation without a direct "
                            "source assertion."
                        ),
                        expected={
                            "direct_feature_assertion": True,
                            "numeric_or_negative_payload": False,
                            "audit_preserved": True,
                        },
                        actual={
                            "removed": deepcopy(feature),
                            "fact_before": before,
                            "reason": "inferential_feature_without_direct_assertion",
                        },
                        evidence=list(feature_evidence),
                    )
                )
                continue
            features.append(feature)

        if not entities and not features:
            issues.append(
                _promotion_issue(
                    fact,
                    code="promotion_structure_inferential_observation_quarantined",
                    message=(
                        "A Structure observation contained only inferential or "
                        "causal projections after direct-evidence gating."
                    ),
                    expected={"grounded_atomic_payload": True, "audit_preserved": True},
                    actual={"removed": before, "reason": "all_inferential_projections"},
                    evidence=list(fallback),
                )
            )
            continue
        if entities == (data.get("entities") or []) and features == (data.get("features") or []):
            accepted.append(fact)
            continue
        data["entities"] = entities
        data["features"] = features
        accepted.append(fact.model_copy(deep=True, update={"data": data}))
    return accepted, issues


def _quarantine_structure_unasserted_entities(
    facts: Sequence[AxisFact],
) -> tuple[list[AxisFact], list[PromotionIssue]]:
    """Isolate positive Structure entities emitted from bare mentions.

    This is deliberately applied after inferential gating.  It removes only
    entity-only projections that have neither a direct observation grammar nor
    a direct structural-change grammar; numeric and negative payloads remain
    untouched, and the complete pre-filter candidate is written to the normal
    issue audit stream.
    """

    accepted: list[AxisFact] = []
    issues: list[PromotionIssue] = []
    for fact in facts:
        if not isinstance(fact, StructureFact) or fact.fact_type != "structure_observation":
            accepted.append(fact)
            continue
        before = fact.model_dump()
        data = deepcopy(fact.data)
        fallback = _fact_evidence(fact)
        entities: list[dict[str, Any]] = []
        for entity in data.get("entities") or []:
            if not isinstance(entity, dict):
                continue
            entity_evidence = _feature_evidence(entity, fallback)
            # Preserve cited/previous-work candidates until the dedicated
            # origin gate can emit its more informative audit code.  Removing
            # them here as a generic bare mention would hide the source-scope
            # failure and make review less actionable.
            if _EXTERNAL_SOURCE_ASSERTION.search("\n".join(entity_evidence)):
                entities.append(entity)
                continue
            if _structure_entity_unasserted_projection(entity, entity_evidence):
                issues.append(
                    _promotion_issue(
                        fact,
                        code="promotion_structure_unasserted_entity_quarantined",
                        message=(
                            "A positive Structure entity was emitted from a bare "
                            "mention without a direct observation or change assertion."
                        ),
                        expected={
                            "direct_entity_assertion": True,
                            "numeric_or_negative_payload": False,
                            "audit_preserved": True,
                        },
                        actual={
                            "removed": deepcopy(entity),
                            "fact_before": before,
                            "reason": "entity_without_direct_assertion",
                        },
                        evidence=list(entity_evidence),
                    )
                )
                continue
            entities.append(entity)
        if not entities and not (data.get("features") or []):
            issues.append(
                _promotion_issue(
                    fact,
                    code="promotion_structure_unasserted_observation_quarantined",
                    message=(
                        "A Structure observation contained only bare entity mentions "
                        "after direct-assertion gating."
                    ),
                    expected={"grounded_atomic_payload": True, "audit_preserved": True},
                    actual={
                        "removed": before,
                        "reason": "all_entities_without_direct_assertion",
                    },
                    evidence=list(fallback),
                )
            )
            continue
        if entities == (data.get("entities") or []):
            accepted.append(fact)
            continue
        data["entities"] = entities
        accepted.append(fact.model_copy(deep=True, update={"data": data}))
    return accepted, issues


_STRUCTURE_GENERALIZATION_CUE = re.compile(
    r"(?ix)\b(?:"
    r"typically|usual(?:ly)?|often|frequently|generally|normally|"
    r"commonly|in\s+general|as\s+a\s+rule|characteristically|"
    r"stud(?:y|ies)\s+have\s+shown|previous\s+stud(?:y|ies)|"
    r"the\s+literature\s+(?:shows?|reports?|indicates?)|"
    r"it\s+is\s+(?:known|well\s+known|common)|"
    r"can\s+be\s+formed|can\s+form|may\s+be\s+observed"
    r")\b"
)
_STRUCTURE_LOCAL_MEASUREMENT_PAYLOAD = re.compile(
    r"(?ix)(?:"
    r"[-+]?\d+(?:\.\d+)?\s*(?:nm|μm|µm|um|mm|cm|°\s*C|°C|K|%|"
    r"mpa|gpa|hv|vol\.?\s*%|wt\.?\s*%|at\.?\s*%)\b|"
    r"\b(?:measur(?:ed|ement|ing)?|quantif(?:ied|y|ication)|"
    r"average|mean|median|standard\s+deviation|"
    r"(?:grain|pore|particle|precipitate)\s+(?:size|diameter|width|length|"
    r"thickness|spacing)|volume\s+fraction|number\s+density)\b"
    r")"
)


def _structure_generalization_entity_projection(
    entity: dict[str, Any],
    evidence: Sequence[str],
    fact: StructureFact,
) -> bool:
    """Return whether an entity-only claim is a generic literature statement."""

    if entity.get("features") or not evidence:
        return False
    if any(
        str(row).lstrip().startswith("|") or "<table" in str(row).casefold()
        for row in evidence
    ):
        return False
    if not _STRUCTURE_GENERALIZATION_CUE.search("\n".join(evidence)):
        return False
    if _is_negated_structure_entity(entity) or _entity_negated_by_prose_evidence(
        entity, evidence
    ):
        return False
    # A numeric/local measurement payload in the same evidence span makes the
    # entity an observed coordinate rather than a bare generalization.  The
    # feature-level numeric and negative gates already protect structured
    # payloads; this check covers entity-only records with copied evidence.
    if _STRUCTURE_LOCAL_MEASUREMENT_PAYLOAD.search("\n".join(evidence)):
        return False
    if any(
        isinstance(feature, dict)
        and (
            _is_quantitative_structure_feature(feature)
            or _is_negated_structure_feature(feature)
        )
        for feature in (fact.data.get("features") or [])
    ):
        return False
    return True


def _quarantine_structure_generalization_projections(
    facts: Sequence[AxisFact],
) -> tuple[list[AxisFact], list[PromotionIssue]]:
    """Isolate entity-only qualitative Structure generalizations.

    ``typically consisted of columnar grains`` is source-grounded text, but it
    is not an observation of the current owner.  This source-only gate keeps
    direct/local measurements, negative assertions, and table coordinates while
    preserving each removed entity and its complete parent fact in audit.
    """

    accepted: list[AxisFact] = []
    issues: list[PromotionIssue] = []
    for fact in facts:
        if not isinstance(fact, StructureFact) or fact.fact_type != "structure_observation":
            accepted.append(fact)
            continue
        before = fact.model_dump()
        fallback = _fact_evidence(fact)
        data = deepcopy(fact.data)
        entities: list[dict[str, Any]] = []
        removed: list[dict[str, Any]] = []
        for entity in data.get("entities") or []:
            if not isinstance(entity, dict):
                continue
            evidence = _feature_evidence(entity, fallback)
            if _structure_generalization_entity_projection(entity, evidence, fact):
                removed.append(
                    {
                        "entity": deepcopy(entity),
                        "reason": "generic_generalization_without_local_payload",
                        "evidence": evidence,
                    }
                )
                continue
            entities.append(entity)
        if not removed:
            accepted.append(fact)
            continue
        data["entities"] = entities
        after = fact.model_copy(deep=True, update={"data": data})
        if entities or data.get("features"):
            accepted.append(after)
        for row in removed:
            issues.append(
                _promotion_issue(
                    fact,
                    code="promotion_structure_generalization_projection_quarantined",
                    message=(
                        "A qualitative Structure entity was emitted from a generic "
                        "literature/generalization statement without a numeric, "
                        "negative, or local measurement payload."
                    ),
                    expected={
                        "owner_local_observation_or_measurement": True,
                        "generic_entity_only_projection": False,
                        "audit_preserved": True,
                    },
                    actual={
                        "removed": row["entity"],
                        "reason": row["reason"],
                        "before": before,
                        "after": after.model_dump() if entities or data.get("features") else None,
                    },
                    evidence=row["evidence"],
                )
            )
        if not entities and not data.get("features"):
            issues.append(
                _promotion_issue(
                    fact,
                    code="promotion_structure_generalization_observation_quarantined",
                    message=(
                        "A Structure observation contained only generic qualitative "
                        "entity projections after source-local precision gating."
                    ),
                    expected={"grounded_local_payload": True, "audit_preserved": True},
                    actual={
                        "removed": before,
                        "reason": "all_entities_generic_generalizations",
                    },
                    evidence=fallback,
                )
            )
    return accepted, issues


_STRUCTURE_PROCEDURAL_PRESENTATION_CUE = re.compile(
    r"(?ix)\b(?:"
    r"used\s+to\s+(?:distinguish|identify|verify|determine|assess|calculate)|"
    r"used\s+for\s+(?:distinguish|identif|verif|determin|assess|calculat)|"
    r"(?:arrow|arrows|dashed\s+line|annotated|annotation)s?\b|"
    r"(?:inset|criterion|criteria|highlight(?:ed|s|ing)?|"
    r"mark(?:ed|s|ing)?|label(?:ed|s|ing)?)\b.{0,80}\b(?:fig(?:ure)?|image|map|region|boundary)|"
    r"\b(?:fig(?:ure)?|image|map|micrograph)s?\b.{0,80}\b(?:shown|illustrat|indicat|used|distinguish)|"
    r"\bto\s+(?:distinguish|identify|verify|determine|assess|calculate)\b"
    r")"
)


def _structure_has_local_direct_payload(
    fact: StructureFact,
    evidence: Sequence[str],
) -> bool:
    """Return whether one entity/feature is directly asserted in its span."""

    data = fact.data
    for entity in data.get("entities") or []:
        if not isinstance(entity, dict):
            continue
        if entity.get("features"):
            return True
        for label in (
            entity.get("name_raw"),
            entity.get("raw_expression"),
        ):
            if label and _structure_evidence_has_direct_assertion(label, evidence):
                return True
    for feature in data.get("features") or []:
        if not isinstance(feature, dict):
            continue
        if _is_quantitative_structure_feature(feature) or _is_negated_structure_feature(
            feature
        ):
            return True
        for label in (
            feature.get("feature_name_raw"),
            feature.get("value_raw"),
            feature.get("raw_expression"),
        ):
            if label and _structure_evidence_has_direct_assertion(label, evidence):
                return True
    return False


def _quarantine_structure_procedural_presentations(
    facts: Sequence[AxisFact],
) -> tuple[list[AxisFact], list[PromotionIssue]]:
    """Remove figure/procedure descriptions lacking an observed structure fact.

    A caption can contain a structural noun (``grain boundary``, ``CP region``)
    solely to explain how a figure or criterion is used.  Treating that noun as
    a measured material state is a common projection path.  This gate acts only
    when the same evidence span contains a procedural/presentation cue and no
    local direct entity/feature assertion; numeric and explicit negative facts
    are preserved.
    """

    accepted: list[AxisFact] = []
    issues: list[PromotionIssue] = []
    for fact in facts:
        if not (
            isinstance(fact, StructureFact)
            and fact.fact_type == "structure_observation"
        ):
            accepted.append(fact)
            continue
        evidence = _fact_evidence(fact)
        joined = "\n".join(evidence)
        if (
            not evidence
            or _has_table_evidence(evidence)
            or not _STRUCTURE_PROCEDURAL_PRESENTATION_CUE.search(joined)
            or _structure_has_local_direct_payload(fact, evidence)
        ):
            accepted.append(fact)
            continue
        issues.append(
            _promotion_issue(
                fact,
                code="promotion_structure_procedural_projection_quarantined",
                message=(
                    "A Structure candidate was supported only by figure/caption "
                    "procedure or locator language and had no local direct "
                    "observation, measurement, or explicit absence assertion."
                ),
                expected={
                    "local_direct_structure_assertion": True,
                    "presentation_only_projection": False,
                    "numeric_or_negative_payload": False,
                    "audit_preserved": True,
                },
                actual={
                    "removed": fact.model_dump(),
                    "reason": "procedural_or_figure_locator_only",
                },
                evidence=evidence,
            )
        )
    return accepted, issues


def _method_family(value: Any) -> str:
    text = str(value or "")
    for family, pattern in _METHOD_FAMILIES:
        if pattern.search(text):
            return family
    return _scientific_fold(text)


def _specific_method_families(value: Any) -> tuple[str, ...]:
    text = str(value or "")
    families = [
        family for family, pattern in _METHOD_FAMILIES if pattern.search(text)
    ]
    # ``scanning transmission electron microscopy`` contains the TEM phrase,
    # but a literal standalone ``TEM`` in ``TEM/STEM`` declares two modalities.
    if "stem" in families and "tem" not in _scientific_fold(text).split():
        families = [family for family in families if family != "tem"]
    return tuple(dict.fromkeys(families))


def _resolved_method_family(method: Any, evidence: Sequence[str]) -> str:
    direct = _specific_method_families(method)
    if len(direct) == 1:
        return direct[0]
    cited = _specific_method_families("\n".join(evidence))
    if len(cited) == 1:
        return cited[0]
    return _method_family(method)


def _method_grounded(method: Any, evidence: Sequence[str]) -> bool:
    if _payload_grounded(method, evidence):
        return True
    family = _method_family(method)
    if not family:
        return False
    source = "\n".join(evidence)
    return any(
        candidate_family == family and pattern.search(source)
        for candidate_family, pattern in _METHOD_FAMILIES
    )


def _characterization_procedural_support(
    fact: AxisFact,
    blocks: Sequence[_SourceBlock],
    block_by_key: dict[str, _SourceBlock],
) -> bool:
    evidence = "\n".join(_fact_evidence(fact))
    # Result captions and discussion sentences often contain words such as
    # ``analysis`` that overlap the broad procedural vocabulary.  They prove
    # that a method produced a result, but they are not independent instrument
    # declarations.  A direct acquisition/use construction remains formal even
    # when it also contains words such as ``image`` or ``analysis``.
    if (
        _CHARACTERIZATION_RESULT_MENTION.search(evidence)
        and not _CHARACTERIZATION_STRONG_DECLARATION.search(evidence)
    ):
        return False
    if _CHARACTERIZATION_PROCEDURAL_CUE.search(evidence):
        return True
    record = build_promotion_records([fact])[0]
    source_key, _, ambiguous = _record_source_binding(record, blocks)
    if ambiguous:
        return False
    block = block_by_key.get(source_key)
    return bool(
        block
        and _CHARACTERIZATION_PROCEDURAL_CUE.search(block.normalized_text)
    )


def _characterization_has_observation_context(fact: AxisFact) -> bool:
    """Return whether a result mention names a distinct observed state/region."""

    return bool(
        _CHARACTERIZATION_OBSERVATION_CONTEXT.search(
            "\n".join(_fact_evidence(fact))
        )
    )


def _characterization_is_presentation_artifact(fact: AxisFact) -> bool:
    """Return whether one candidate is a caption/result alias, not a method."""

    evidence = "\n".join(_fact_evidence(fact))
    method = str(fact.data.get("method_raw") or "")
    if not method or not evidence:
        return False
    if not _CHARACTERIZATION_RESULT_MENTION.search(evidence):
        return False
    # Formal acquisition/use constructions are authoritative even when they
    # mention images or maps as the produced artifact.
    if _CHARACTERIZATION_STRONG_DECLARATION.search(evidence):
        return False
    if _CHARACTERIZATION_PROCEDURAL_CUE.search(evidence):
        return False
    return bool(_CHARACTERIZATION_PRESENTATION_ARTIFACT.search(method))


def _characterization_has_direct_method_assertion(
    fact: StructureFact,
    blocks: Sequence[_SourceBlock],
    block_by_key: dict[str, _SourceBlock],
) -> bool:
    """Return whether the candidate itself asserts an acquisition method.

    Characterization is a method/measurement axis.  A result sentence such as
    ``SEM images show ...`` is evidence that an image exists, not evidence
    that the paper introduced a new method record at that location.  Earlier
    versions let these result mentions survive as state-qualified observations,
    which is the main source of the current Characterization precision loss.

    The only non-prose exception is a compact Markdown table method row (for
    example ``SEM: Zeiss Supra 55``).  We accept that form only when the
    candidate evidence binds unambiguously to a table block and the row starts
    with a known modality label; figure/caption rows therefore remain rejected.
    """

    evidence = "\n".join(_fact_evidence(fact))
    if not evidence:
        return False
    if _CHARACTERIZATION_STRONG_DECLARATION.search(evidence):
        return True

    record = build_promotion_records([fact])[0]
    source_key, source_kind, ambiguous = _record_source_binding(record, blocks)
    if ambiguous or source_kind != "table":
        return False
    block = block_by_key.get(source_key)
    return bool(
        block
        and _CHARACTERIZATION_TABLE_METHOD_LABEL.search(evidence)
    )


_CHARACTERIZATION_SIMULATION_EVENT_V205 = re.compile(
    r"(?ix)\b(?:simulation|simulations|simulated|computational)\b"
)
_CHARACTERIZATION_LINE_SCAN_EVENT_V205 = re.compile(
    r"(?ix)\bline[\s-]*scan(?:ning)?\b"
)


def _characterization_event_kind_v205(fact: AxisFact) -> str:
    """Return a source-literal event discriminator, or v204's empty key."""

    if not characterization_event_atomicity_v205_enabled():
        return ""
    text = "\n".join(
        [str(fact.data.get("method_raw") or ""), *_fact_evidence(fact)]
    )
    if _CHARACTERIZATION_SIMULATION_EVENT_V205.search(text):
        return "simulation"
    if _CHARACTERIZATION_LINE_SCAN_EVENT_V205.search(text):
        return "line_scan"
    return "experiment"


def _characterization_event_decision_key_v205(
    fact: AxisFact, *, event_kind: str, reason: str
) -> str:
    payload = {
        "owner": _identity_text(fact.sample_id_raw),
        "state": _fact_material_state(fact),
        "family": _resolved_method_family(
            fact.data.get("method_raw"), _fact_evidence(fact)
        ),
        "event_kind": event_kind,
        "method": _scientific_fold(fact.data.get("method_raw")),
        "evidence": [
            normalize_evidence_text(row) for row in _fact_evidence(fact)
        ],
        "reason": reason,
    }
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return "characterization-v205:" + hashlib.sha256(encoded).hexdigest()[:24]


def _merge_characterization_across_source_blocks(
    facts: Sequence[AxisFact], source_text: str
) -> tuple[list[AxisFact], list[PromotionIssue]]:
    """Absorb result/caption aliases into one owner-local method declaration."""

    blocks = _source_blocks(source_text)
    block_by_key = {block.key: block for block in blocks}
    # ``source_type`` is a presentation/provenance label, not a scientific
    # identity.  Chunk-local extractors frequently mark the formal methods
    # paragraph as ``method`` and a figure caption as ``reported``/``result``.
    # Keeping that field in the grouping key lets the same SEM/EBSD/TEM method
    # leak into the material ledger twice.  Group by the owner and material
    # state instead; explicit state/region observations are split below.
    grouped: dict[tuple[str, str, str, str], list[StructureFact]] = {}
    passthrough: list[AxisFact] = []
    for fact in facts:
        if not isinstance(fact, StructureFact) or fact.fact_type != "characterization":
            passthrough.append(fact)
            continue
        # A candidate may preserve a coupled modality in one source-literal
        # method label (for example TEM+SAED or STEM+EDS).  It is not a
        # presentation alias of either family alone, so cross-source merging
        # must not collapse the coupled method into whichever family happens
        # to match first.
        if len(_specific_method_families(fact.data.get("method_raw"))) > 1:
            passthrough.append(fact)
            continue
        grouped.setdefault(
            (
                _identity_text(fact.sample_id_raw),
                _fact_material_state(fact),
                _resolved_method_family(
                    fact.data.get("method_raw"), _fact_evidence(fact)
                ),
                _characterization_event_kind_v205(fact),
            ),
            [],
        ).append(fact)

    accepted: list[AxisFact] = list(passthrough)
    issues: list[PromotionIssue] = []
    for rows in grouped.values():
        if len(rows) < 2:
            row = rows[0]
            if _characterization_is_presentation_artifact(row):
                issues.append(
                    _promotion_issue(
                        row,
                        code="promotion_characterization_presentation_artifact_quarantined",
                        message=(
                            "A figure/caption-shaped Characterization projection "
                            "had no matching formal method declaration and was "
                            "isolated from the formal ledger."
                        ),
                        expected={
                            "formal_method_declaration": True,
                            "presentation_alias": False,
                            "audit_preserved": True,
                        },
                        actual={
                            "removed": row.model_dump(),
                            "reason": "caption_or_result_presentation_alias",
                        },
                        evidence=_fact_evidence(row),
                    )
                )
            else:
                accepted.extend(rows)
            continue
        procedural_support = {
            id(row): _characterization_procedural_support(
                row, blocks, block_by_key
            )
            for row in rows
        }
        # A state/region-qualified result is a separate observation context,
        # even when the instrument family is the same as a generic method
        # declaration elsewhere in the paper.  Keep it independently owned so
        # materialization can route it to the explicit state.
        contextual_results = [
            row
            for row in rows
            if not procedural_support[id(row)]
            and _characterization_has_observation_context(row)
        ]
        contextual_ids = {id(row) for row in contextual_results}
        mergeable = [row for row in rows if id(row) not in contextual_ids]
        accepted.extend(contextual_results)
        if len(mergeable) < 2:
            for row in mergeable:
                if _characterization_is_presentation_artifact(row):
                    issues.append(
                        _promotion_issue(
                            row,
                            code="promotion_characterization_presentation_artifact_quarantined",
                            message=(
                                "A figure/caption-shaped Characterization projection "
                                "had no matching formal method declaration and was "
                                "isolated from the formal ledger."
                            ),
                            expected={
                                "formal_method_declaration": True,
                                "presentation_alias": False,
                                "audit_preserved": True,
                            },
                            actual={
                                "removed": row.model_dump(),
                                "reason": "caption_or_result_presentation_alias",
                            },
                            evidence=_fact_evidence(row),
                        )
                    )
                else:
                    accepted.append(row)
            continue
        procedural = [
            row for row in mergeable if procedural_support[id(row)]
        ]
        # Competing formal declarations can represent different instruments or
        # acquisition conditions.  Without an explicit condition field, keep
        # them separate instead of selecting by confidence or output order.
        if len(procedural) != 1:
            if (
                characterization_event_atomicity_v205_enabled()
                and len(procedural) > 1
            ):
                accepted.extend(procedural)
                formal_events = [row.model_dump() for row in procedural]
                for row in mergeable:
                    if row in procedural:
                        continue
                    event_kind = _characterization_event_kind_v205(row)
                    issues.append(
                        _promotion_issue(
                            row,
                            code="characterization_event_coordinate_ambiguous",
                            message=(
                                "A Characterization result alias was compatible "
                                "with multiple formal owner-local events and was "
                                "isolated instead of being promoted independently."
                            ),
                            expected={
                                "unique_formal_event": True,
                                "result_alias_as_independent_event": False,
                                "audit_preserved": True,
                            },
                            actual={
                                "removed": row.model_dump(),
                                "formal_event_count": len(procedural),
                                "formal_events": formal_events,
                                "event_kind": event_kind,
                                "decision_key": _characterization_event_decision_key_v205(
                                    row,
                                    event_kind=event_kind,
                                    reason="multiple_compatible_formal_events",
                                ),
                            },
                            evidence=_fact_evidence(row),
                        )
                    )
                continue
            # ``contextual_results`` were already emitted above.  Extending
            # the whole group here would duplicate them in the materializer.
            for row in mergeable:
                if not procedural and _characterization_is_presentation_artifact(row):
                    issues.append(
                        _promotion_issue(
                            row,
                            code="promotion_characterization_presentation_artifact_quarantined",
                            message=(
                                "A figure/caption-shaped Characterization projection "
                                "had no matching formal method declaration and was "
                                "isolated from the formal ledger."
                            ),
                            expected={
                                "formal_method_declaration": True,
                                "presentation_alias": False,
                                "audit_preserved": True,
                            },
                            actual={
                                "removed": row.model_dump(),
                                "reason": "caption_or_result_presentation_alias",
                            },
                            evidence=_fact_evidence(row),
                        )
                    )
                else:
                    accepted.append(row)
            continue
        survivor_before = procedural[0]
        losers = [row for row in mergeable if row is not survivor_before]
        survivor_after = _with_combined_fact_evidence(
            survivor_before,
            [survivor_before, *losers],
            source_text,
        )
        assert isinstance(survivor_after, StructureFact)
        accepted.append(survivor_after)
        for loser in losers:
            issues.append(
                _promotion_issue(
                    survivor_after,
                    code="promotion_characterization_alias_merged",
                    message=(
                        "A repeated result/caption mention of one owner-local "
                        "Characterization method was merged into its formal "
                        "method declaration."
                    ),
                    expected={
                        "method_family": _resolved_method_family(
                            survivor_after.data.get("method_raw"),
                            _fact_evidence(survivor_after),
                        ),
                        "owner_local_method_declarations": 1,
                        "audit_preserved": True,
                    },
                    actual={
                        "removed": loser.model_dump(),
                        "survivor_before": survivor_before.model_dump(),
                        "survivor_after": survivor_after.model_dump(),
                        "reason": "cross_source_method_alias",
                    },
                    evidence=list(survivor_after.source_evidence),
                )
            )
            event_kind = _characterization_event_kind_v205(survivor_after)
            if (
                characterization_event_atomicity_v205_enabled()
                and event_kind != "experiment"
            ):
                issues.append(
                    _promotion_issue(
                        survivor_after,
                        code="characterization_event_alias_merged",
                        message=(
                            "A presentation alias was merged into one source-"
                            "compatible Characterization event coordinate."
                        ),
                        expected={
                            "same_owner_state_family_event_kind": True,
                            "one_formal_event": True,
                            "audit_preserved": True,
                        },
                        actual={
                            "removed": loser.model_dump(),
                            "survivor_before": survivor_before.model_dump(),
                            "survivor_after": survivor_after.model_dump(),
                            "event_kind": event_kind,
                            "decision_key": _characterization_event_decision_key_v205(
                                loser,
                                event_kind=event_kind,
                                reason="source_compatible_alias_merged",
                            ),
                        },
                        evidence=list(survivor_after.source_evidence),
                    )
                )
    return accepted, issues


def _gate_characterizations(
    facts: Sequence[AxisFact], source_text: str
) -> tuple[list[AxisFact], list[PromotionIssue]]:
    accepted: list[AxisFact] = []
    issues: list[PromotionIssue] = []
    valid: list[AxisFact] = []
    pending_unasserted: list[tuple[StructureFact, list[str]]] = []
    blocks = _source_blocks(source_text)
    block_by_key = {block.key: block for block in blocks}
    for fact in facts:
        if not isinstance(fact, StructureFact) or fact.fact_type != "characterization":
            accepted.append(fact)
            continue
        method = fact.data.get("method_raw")
        evidence = _fact_evidence(fact)
        method_text = str(method or "").strip()
        if _CHARACTERIZATION_NON_METHOD_LABEL.search(method_text):
            issues.append(
                _promotion_issue(
                    fact,
                    code="promotion_characterization_non_method_quarantined",
                    message=(
                        "A Characterization candidate was labeled as an instrument, "
                        "condition, setting, or other method subfield rather than "
                        "an independent acquisition modality."
                    ),
                    expected={
                        "independent_method_modality": True,
                        "instrument_or_condition_subfield": False,
                        "audit_preserved": True,
                    },
                    actual={
                        "removed": fact.model_dump(),
                        "reason": "characterization_subfield_label",
                    },
                    evidence=evidence,
                )
            )
            continue
        if not _method_grounded(method, evidence):
            issues.append(
                _promotion_issue(
                    fact,
                    code="promotion_characterization_method_unsupported",
                    message=(
                        "A Characterization method was absent from its cited "
                        "evidence."
                    ),
                    expected={"method_raw_grounded": True},
                    actual={"removed": fact.model_dump()},
                )
            )
            continue
        if not _characterization_has_direct_method_assertion(
            fact, blocks, block_by_key
        ):
            pending_unasserted.append((fact, evidence))
            continue
        method_families = _specific_method_families(method)
        method_class = _scientific_fold(fact.data.get("method_class"))
        if (
            len(method_families) == 1
            and (
                method_class in _GENERIC_CHARACTERIZATION_CLASSES
                or method_class
                in _CHARACTERIZATION_CLASS_ALIASES[method_families[0]]
            )
            and method_class
            != _scientific_fold(
                _CHARACTERIZATION_CLASS_LABELS[method_families[0]]
            )
        ):
            before = fact.model_dump()
            data = deepcopy(fact.data)
            data["method_class"] = _CHARACTERIZATION_CLASS_LABELS[
                method_families[0]
            ]
            normalized = fact.model_copy(deep=True, update={"data": data})
            valid.append(normalized)
            issues.append(
                _promotion_issue(
                    normalized,
                    code="promotion_characterization_class_normalized",
                    message=(
                        "A generic Characterization class was normalized to the "
                        "single modality explicitly named by method_raw."
                    ),
                    expected={
                        "single_source_explicit_modality": method_families[0],
                        "multi_modality_rewrite": False,
                        "audit_preserved": True,
                    },
                    actual={
                        "before": before,
                        "after": normalized.model_dump(),
                        "reason": "single_source_explicit_modality",
                    },
                    evidence=evidence,
                )
            )
            continue
        valid.append(fact)

    # A result/caption candidate may be a legitimate alias of a formal method
    # declaration in the same owner/state (for example ``SEM-BSE images ...``
    # after a preceding ``SEM was performed ...`` sentence).  Keep that alias
    # only so the source-block merger can fold its evidence into the formal
    # survivor.  Do not let a result mention create a method on its own, and do
    # not preserve state-qualified observations or coupled modalities merely
    # because a broad family name happens to overlap.
    direct_keys = {
        (
            _identity_text(row.sample_id_raw),
            _fact_material_state(row),
            _resolved_method_family(
                row.data.get("method_raw"), _fact_evidence(row)
            ),
            _characterization_event_kind_v205(row),
        )
        for row in valid
        if isinstance(row, StructureFact) and row.fact_type == "characterization"
    }
    direct_family_keys = {key[:3] for key in direct_keys}
    for fact, evidence in pending_unasserted:
        key = (
            _identity_text(fact.sample_id_raw),
            _fact_material_state(fact),
            _resolved_method_family(
                fact.data.get("method_raw"), _fact_evidence(fact)
            ),
            _characterization_event_kind_v205(fact),
        )
        reusable_alias = (
            key in direct_keys
            and len(_specific_method_families(fact.data.get("method_raw"))) <= 1
            and not _characterization_has_observation_context(fact)
        )
        if reusable_alias:
            valid.append(fact)
            continue
        event_coordinate_conflict = (
            characterization_event_atomicity_v205_enabled()
            and key[:3] in direct_family_keys
            and key not in direct_keys
        )
        if event_coordinate_conflict:
            issues.append(
                _promotion_issue(
                    fact,
                    code="characterization_event_projection_quarantined",
                    message=(
                        "A Characterization result mention shared a method family "
                        "with a formal event but had an incompatible source-"
                        "literal event kind; it was isolated instead of hitchhiking "
                        "on that event."
                    ),
                    expected={
                        "same_owner_state_family_event_kind": True,
                        "result_alias_as_independent_event": False,
                        "audit_preserved": True,
                    },
                    actual={
                        "removed": fact.model_dump(),
                        "reason": "event_kind_coordinate_conflict",
                        "event_kind": key[3],
                        "compatible_formal_event_kinds": sorted(
                            direct[3]
                            for direct in direct_keys
                            if direct[:3] == key[:3]
                        ),
                        "decision_key": _characterization_event_decision_key_v205(
                            fact,
                            event_kind=key[3],
                            reason="event_kind_coordinate_conflict",
                        ),
                    },
                    evidence=evidence,
                )
            )
            continue
        issues.append(
            _promotion_issue(
                fact,
                code="promotion_characterization_unasserted_result_quarantined",
                message=(
                    "A Characterization candidate was supported only by a "
                    "figure/result/observation mention, not by a direct "
                    "method declaration. It was isolated from the formal "
                    "ledger while preserving the complete candidate audit."
                ),
                expected={
                    "direct_method_declaration": True,
                    "same_owner_formal_alias": True,
                    "table_method_row": True,
                    "presentation_or_result_alias": False,
                    "audit_preserved": True,
                },
                actual={
                    "removed": fact.model_dump(),
                    "reason": (
                        "unasserted_result_or_caption"
                        if key not in direct_keys
                        else "state_or_coupled_result_alias"
                    ),
                },
                evidence=evidence,
            )
        )

    grouped: dict[tuple[str, str, str], list[AxisFact]] = {}
    passthrough: list[AxisFact] = []
    for fact in valid:
        record = build_promotion_records([fact])[0]
        source_key, _, ambiguous = _record_source_binding(record, blocks)
        if ambiguous:
            passthrough.append(fact)
            continue
        grouped.setdefault(
            (
                _identity_text(fact.sample_id_raw),
                source_key,
                _resolved_method_family(
                    fact.data.get("method_raw"), _fact_evidence(fact)
                ),
            ),
            [],
        ).append(fact)
    accepted.extend(passthrough)
    for rows in grouped.values():
        survivor = max(
            rows,
            key=lambda row: (
                bool(_specific_method_families(row.data.get("method_raw"))),
                len(str(row.data.get("method_raw") or "")),
                semantic_fact_signature(row),
            ),
        )
        accepted.append(survivor)
        for loser in rows:
            if loser is survivor:
                continue
            issues.append(
                _promotion_issue(
                    survivor,
                    code="promotion_characterization_alias_merged",
                    message=(
                        "Presentation aliases of one Characterization method were "
                        "merged."
                    ),
                    expected={
                        "method_family": _resolved_method_family(
                            survivor.data.get("method_raw"),
                            _fact_evidence(survivor),
                        )
                    },
                    actual={
                        "removed": loser.model_dump(),
                        "survivor_before": survivor.model_dump(),
                        "survivor_after": survivor.model_dump(),
                    },
                    evidence=list(
                        dict.fromkeys(
                            [*_fact_evidence(survivor), *_fact_evidence(loser)]
                        )
                    ),
                )
            )
    accepted, cross_source_issues = _merge_characterization_across_source_blocks(
        accepted, source_text
    )
    issues.extend(cross_source_issues)
    return accepted, issues


def _v205_condition_segments(value: Any) -> tuple[str, ...]:
    """Return stable top-level condition segments without splitting units."""

    return tuple(
        segment
        for raw in re.split(r"\s*(?:\||;|\n)\s*", str(value or ""))
        if (segment := re.sub(r"\s+", " ", raw).strip(" ,;:|"))
    )


def _v205_remove_locator_from_segment(
    segment: str,
) -> tuple[str, tuple[str, ...]]:
    matches = tuple(
        re.sub(r"\s+", " ", match.group(0)).strip()
        for match in _CONDITION_PROVENANCE_LOCATOR_V205.finditer(segment)
    )
    if not matches:
        return segment, ()
    cleaned = _CONDITION_PROVENANCE_LOCATOR_V205.sub("", segment)
    cleaned = _CONDITION_PROVENANCE_GLUE_V205.sub("", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip(" ,;:|()[]")
    # A locator-bearing segment that leaves only presentation prose does not
    # contain a scientific coordinate.  Do not manufacture a replacement.
    if cleaned and not _SCIENTIFIC_CONDITION_CUE_V205.search(cleaned):
        cleaned = ""
    return cleaned, matches


def _separate_property_provenance_conditions_v205(
    facts: Sequence[AxisFact],
) -> tuple[list[AxisFact], list[PromotionIssue]]:
    """Remove provenance locators and exact duplicate condition segments.

    The pass is source-neutral and idempotent.  It changes only
    ``test_condition_raw``; full evidence and every before/after record remain
    available to the audit writer.  Grounding is still enforced by the
    downstream condition gate.
    """

    if not property_provenance_condition_separation_v205_enabled():
        return list(facts), []
    accepted: list[AxisFact] = []
    issues: list[PromotionIssue] = []
    for fact in facts:
        if not isinstance(fact, PropertyFact):
            accepted.append(fact)
            continue
        raw_condition = str(fact.data.get("test_condition_raw") or "").strip()
        if not raw_condition or _scientific_fold(raw_condition) in _UNREPORTED:
            accepted.append(fact)
            continue

        current = fact
        locator_segments: list[str] = []
        removed_locators: list[str] = []
        for segment in _v205_condition_segments(raw_condition):
            cleaned, locators = _v205_remove_locator_from_segment(segment)
            removed_locators.extend(locators)
            if cleaned:
                locator_segments.append(cleaned)
        locator_condition = "; ".join(locator_segments)
        if removed_locators and _condition_fragment_key(locator_condition) != (
            _condition_fragment_key(raw_condition)
        ):
            data = deepcopy(current.data)
            data["test_condition_raw"] = locator_condition
            updated = current.model_copy(deep=True, update={"data": data})
            issues.append(
                _promotion_issue(
                    current,
                    code="property_provenance_locator_removed_from_condition",
                    message=(
                        "Presentation locators were removed from a Property's "
                        "scientific condition while the complete evidence and "
                        "candidate were retained in audit."
                    ),
                    expected={
                        "test_condition": "source-literal scientific coordinates only",
                        "provenance_retained_in_evidence": True,
                        "property_value_preserved": True,
                        "audit_preserved": True,
                    },
                    actual={
                        "before": current.model_dump(),
                        "after": updated.model_dump(),
                        "removed_locators": list(dict.fromkeys(removed_locators)),
                    },
                    evidence=_fact_evidence(current),
                )
            )
            current = updated

        current_condition = str(
            current.data.get("test_condition_raw") or ""
        ).strip()
        unique_segments: list[str] = []
        duplicate_segments: list[str] = []
        seen: set[str] = set()
        for segment in _v205_condition_segments(current_condition):
            key = _condition_fragment_key(segment)
            if not key:
                continue
            if key in seen:
                duplicate_segments.append(segment)
                continue
            seen.add(key)
            unique_segments.append(segment)
        deduplicated_condition = "; ".join(unique_segments)
        if duplicate_segments:
            data = deepcopy(current.data)
            data["test_condition_raw"] = deduplicated_condition
            updated = current.model_copy(deep=True, update={"data": data})
            issues.append(
                _promotion_issue(
                    current,
                    code="property_condition_duplicate_segment_removed",
                    message=(
                        "Equivalent repeated scientific-condition segments were "
                        "collapsed without removing any distinct test dimension."
                    ),
                    expected={
                        "one_segment_per_scientific_coordinate": True,
                        "distinct_dimensions_preserved": True,
                        "property_value_preserved": True,
                        "audit_preserved": True,
                    },
                    actual={
                        "before": current.model_dump(),
                        "after": updated.model_dump(),
                        "removed_duplicate_segments": duplicate_segments,
                    },
                    evidence=_fact_evidence(current),
                )
            )
            current = updated
        accepted.append(current)
    return accepted, issues


def _v205_protocol_separation_audit(
    issues: Sequence[PromotionIssue],
) -> list[PromotionIssue]:
    """Mirror v204 method cleanup with the explicit v205 audit contract."""

    if not property_provenance_condition_separation_v205_enabled():
        return []
    output: list[PromotionIssue] = []
    for issue in issues:
        if issue.code != "promotion_condition_method_context_trimmed":
            continue
        actual = deepcopy(issue.actual)
        output.append(
            PromotionIssue(
                code="property_condition_protocol_context_separated",
                sample_id_raw=issue.sample_id_raw,
                message=(
                    "Protocol or method prose was separated from the scientific "
                    "Property condition; the complete original remains in audit."
                ),
                severity=issue.severity,
                path=issue.path,
                evidence=deepcopy(issue.evidence),
                expected={
                    "test_condition": "source-literal scientific coordinates only",
                    "protocol_context_retained_in_evidence": True,
                    "property_value_preserved": True,
                    "audit_preserved": True,
                },
                actual=actual,
                suggested_action=issue.suggested_action,
            )
        )
    return output


def _strip_unbound_conditions(
    facts: Sequence[AxisFact],
    source_text: str = "",
) -> tuple[list[AxisFact], list[PromotionIssue]]:
    accepted: list[AxisFact] = []
    issues: list[PromotionIssue] = []
    for fact in facts:
        if not isinstance(fact, PropertyFact):
            accepted.append(fact)
            continue
        condition = fact.data.get("test_condition_raw")
        if _scientific_fold(condition) in _UNREPORTED or _payload_grounded(
            condition, _fact_evidence(fact)
        ) or _table_condition_is_source_bound(fact, source_text):
            accepted.append(fact)
            continue
        before = fact.model_dump()
        data = deepcopy(fact.data)
        data["test_condition_raw"] = ""
        cleaned = fact.model_copy(deep=True, update={"data": data})
        accepted.append(cleaned)
        issues.append(
            _promotion_issue(
                fact,
                code="promotion_unbound_condition_quarantined",
                message=(
                    "A Property condition absent from the candidate's own source "
                    "assertion was removed without dropping the grounded result."
                ),
                expected={
                    "condition_binding": "same assertion or not_reported"
                },
                actual={"before": before["data"], "after": cleaned.data},
            )
        )
    return accepted, issues


def _condition_fragment_key(value: str) -> str:
    """Normalize a condition fragment for stable de-duplication."""

    return _scientific_fold(re.sub(r"\s+", " ", value).strip(" ,;:"))


def _condition_fragment_shares_value_assertion(
    fragment: str,
    value: Any,
    evidence: Sequence[str],
) -> bool:
    """Require a coordinate and Property value to share one source assertion."""

    value_text = str(value or "").strip()
    if not value_text or _scientific_fold(value_text) in _UNREPORTED:
        return True
    for raw in evidence:
        for sentence in re.split(r"(?<=[.!?;])\s+|\n+", str(raw or "")):
            if not _payload_grounded(fragment, (sentence,)):
                continue
            if _payload_grounded(value_text, (sentence,)):
                return True
    return False


def _source_condition_fragments(
    condition: str,
    evidence: Sequence[str],
    *,
    value: Any = None,
) -> tuple[str, ...]:
    """Extract compact source-literal coordinates from a method paragraph.

    This is deliberately a *lossy cleanup of the condition field only*.  The
    complete candidate and its evidence remain in the promotion issue audit.
    A fragment is eligible only when it is literally present in the candidate's
    own evidence; no source-text search or neighbouring-chunk recovery is used.
    """

    text = re.sub(r"\s+", " ", str(condition or "")).strip()
    if not text:
        return ()
    support = "\n".join(str(row or "") for row in evidence)
    normalized_support = _scientific_fold(support)
    fragments: list[str] = []
    seen: set[str] = set()
    for match in _CONDITION_COORDINATE_FRAGMENT.finditer(text):
        fragment = re.sub(r"\s+", " ", match.group(0)).strip(" ,;:")
        if not fragment:
            continue
        # Use the same token-boundary grounding as the main condition gate.
        # Compact fallback is acceptable for a short state label but never for
        # a long method sentence, where a copied number is not a coordinate.
        grounded = _payload_grounded(fragment, (support,))
        if not grounded and len(fragment) <= 48:
            grounded = _scientific_fold(fragment) in normalized_support
        if not grounded:
            continue
        if not _condition_fragment_shares_value_assertion(
            fragment, value, evidence
        ):
            continue
        key = _condition_fragment_key(fragment)
        if key and key not in seen:
            seen.add(key)
            fragments.append(fragment)
    return tuple(fragments)


def _clean_method_conditions(
    facts: Sequence[AxisFact],
) -> tuple[list[AxisFact], list[PromotionIssue]]:
    """Trim method/protocol prose that was copied into Property conditions.

    Short, source-grounded conditions are left byte-for-byte unchanged.  A
    long condition is considered method-like only when it contains explicit
    method noise or exceeds the compact-coordinate budget.  In that case we
    keep only source-literal coordinate fragments (temperature, delay, state,
    orientation, or test rate).  If no coordinate survives, the condition is
    cleared while the grounded Property value/owner remains accepted.
    """

    accepted: list[AxisFact] = []
    issues: list[PromotionIssue] = []
    for fact in facts:
        if not isinstance(fact, PropertyFact):
            accepted.append(fact)
            continue
        raw_condition = str(fact.data.get("test_condition_raw") or "").strip()
        if not raw_condition or _scientific_fold(raw_condition) in _UNREPORTED:
            accepted.append(fact)
            continue
        evidence = _fact_evidence(fact)
        method_like = len(raw_condition) > 180 or bool(
            _CONDITION_METHOD_NOISE.search(raw_condition)
        )
        if not method_like:
            accepted.append(fact)
            continue
        fragments = _source_condition_fragments(
            raw_condition,
            evidence,
            value=fact.data.get("value_raw"),
        )
        cleaned_condition = "; ".join(fragments)
        if _scientific_fold(cleaned_condition) == _scientific_fold(raw_condition):
            accepted.append(fact)
            continue
        data = deepcopy(fact.data)
        data["test_condition_raw"] = cleaned_condition
        cleaned = fact.model_copy(deep=True, update={"data": data})
        accepted.append(cleaned)
        issues.append(
            _promotion_issue(
                fact,
                code="promotion_condition_method_context_trimmed",
                message=(
                    "A method/protocol paragraph copied into a Property condition "
                    "was reduced to source-literal coordinate fragments. The "
                    "complete original candidate remains in the audit record."
                ),
                expected={
                    "condition_contains_only_direct_coordinates": True,
                    "source_literal_only": True,
                    "value_preserved": True,
                    "audit_preserved": True,
                },
                actual={
                    "before": fact.model_dump(),
                    "after": cleaned.model_dump(),
                    "method_like": method_like,
                    "kept_fragments": list(fragments),
                    "reason": (
                        "no_source_literal_coordinate_survived"
                        if not cleaned_condition
                        else "method_context_removed"
                    ),
                },
                evidence=evidence,
            )
        )
    return accepted, issues


def _explicit_treatment_condition(evidence: Sequence[str]) -> str | None:
    """Return one source-literal preparation condition from the same assertion.

    This intentionally handles only a temperature/time pair introduced by an
    explicit treatment cue.  It does not search neighboring paragraphs, infer a
    state from a bare temperature, or turn a test temperature into a material
    condition.
    """

    matches: list[str] = []
    for row in evidence:
        text = str(row or "").strip()
        for match in _EXPLICIT_TREATMENT_CONDITION.finditer(text):
            literal = re.sub(r"\s+", " ", match.group(0)).strip(" ,;:")
            if literal and literal not in matches:
                matches.append(literal)
    if len(matches) != 1:
        return None
    return matches[0]


def _bind_explicit_treatment_conditions(
    facts: Sequence[AxisFact],
) -> tuple[list[AxisFact], list[PromotionIssue]]:
    """Bind a treatment condition only when the result assertion states it.

    Property-context recovery later supplies shared tensile-test protocol
    details.  This pass adds the orthogonal preparation state only when the
    candidate's own evidence contains one unambiguous source-literal
    treatment, preventing cross-sentence state borrowing.
    """

    accepted: list[AxisFact] = []
    issues: list[PromotionIssue] = []
    for fact in facts:
        if not isinstance(fact, PropertyFact) or not is_core_tensile_property_name(
            fact.data.get("property_name_raw")
        ):
            accepted.append(fact)
            continue
        evidence = _fact_evidence(fact)
        treatment = _explicit_treatment_condition(evidence)
        if not treatment:
            accepted.append(fact)
            continue
        current = str(fact.data.get("test_condition_raw") or "").strip()
        if current and _EXPLICIT_TREATMENT_CONDITION.search(current):
            accepted.append(fact)
            continue
        data = deepcopy(fact.data)
        data["test_condition_raw"] = (
            treatment if not current else f"{current}; {treatment}"
        )
        updated = fact.model_copy(deep=True, update={"data": data})
        accepted.append(updated)
        issues.append(
            _promotion_issue(
                fact,
                code="promotion_explicit_treatment_condition_bound",
                message=(
                    "A preparation treatment stated in the same tensile result "
                    "assertion was bound to its condition without borrowing from "
                    "neighboring source text."
                ),
                expected={
                    "condition_binding": "one source-literal treatment in own evidence",
                    "cross_sentence_inference": False,
                    "audit_preserved": True,
                },
                actual={
                    "before": fact.model_dump(),
                    "after": updated.model_dump(),
                    "treatment_literal": treatment,
                },
                evidence=evidence,
            )
        )
    return accepted, issues


def _source_condition_label(label: Any, evidence: Sequence[str]) -> str:
    """Return a candidate condition label only when it is source-grounded.

    ``condition_label_raw`` is useful for mapping a value to a state (for
    example ``0 s delay``), but extraction responses also use it for free-form method or
    chunk context.  Promote only a literal label that both occurs in the
    quoted evidence and carries a state/axis/temperature/time discriminator.
    """

    value = str(label or "").strip()
    if not value or _scientific_fold(value) in _UNREPORTED:
        return ""
    if not _CONDITION_DISCRIMINATOR_CUE.search(value):
        return ""
    if not _payload_grounded(value, evidence):
        return ""
    return value


def _bind_property_condition_labels(
    facts: Sequence[AxisFact],
) -> tuple[list[AxisFact], list[PromotionIssue]]:
    """Bind source-literal ``condition_label_raw`` into the public condition.

    The raw candidate contract intentionally keeps labels separate because an
    extraction response may use them as a routing hint.  Once the label is proven to be a
    literal part of the candidate's own evidence, retaining it in
    ``test_condition_raw`` prevents materialization from silently dropping the
    only owner/state discriminator.  No label is inferred from neighboring
    chunks and method-only labels are ignored.
    """

    accepted: list[AxisFact] = []
    issues: list[PromotionIssue] = []
    for fact in facts:
        if not isinstance(fact, PropertyFact):
            accepted.append(fact)
            continue
        evidence = _fact_evidence(fact)
        label = _source_condition_label(
            fact.data.get("condition_label_raw"), evidence
        )
        if not label:
            accepted.append(fact)
            continue
        current = str(fact.data.get("test_condition_raw") or "").strip()
        if current and _scientific_fold(label) in _scientific_fold(current):
            accepted.append(fact)
            continue
        data = deepcopy(fact.data)
        data["test_condition_raw"] = (
            label if not current else f"{label}; {current}"
        )
        updated = fact.model_copy(deep=True, update={"data": data})
        accepted.append(updated)
        issues.append(
            _promotion_issue(
                fact,
                code="promotion_condition_label_bound",
                message=(
                    "A source-literal condition label was promoted into the "
                    "formal Property condition so owner/state routing cannot "
                    "silently drop it."
                ),
                expected={
                    "condition_label_source_grounded": True,
                    "condition_discriminator": True,
                    "cross_chunk_inference": False,
                    "audit_preserved": True,
                },
                actual={
                    "before": fact.model_dump(),
                    "after": updated.model_dump(),
                    "condition_label": label,
                },
                evidence=evidence,
            )
        )
    return accepted, issues


def _condition_matches_state(
    condition: Any,
    node: OwnerNode,
    *,
    structure_state: bool = False,
) -> bool:
    """Match one source condition to one existing state owner conservatively."""

    state = str(node.state_raw or "").strip()
    condition_text = str(condition or "").strip()
    if not state or not condition_text:
        return False
    if _literal_mention(condition_text, state):
        if not structure_state:
            return True
        # For Structure, a short state token such as ``initial`` or
        # ``fracture`` appearing inside a richer phrase is not a sufficient
        # coordinate.  Exact normalized labels were handled by the caller;
        # textual containment must not silently canonicalize a different
        # observation state.  Numeric state coordinates may still match below
        # when they share a structural discriminator (for example ``1% creep
        # strain`` and ``interrupted at 1% strain``).
        return False

    state_durations = _duration_values(state)
    condition_durations = _duration_values(condition_text)
    if state_durations and condition_durations and not (
        state_durations & condition_durations
    ):
        return False

    state_numbers = set(_numeric_tokens(state))
    condition_numbers = set(_numeric_tokens(condition_text))
    if not state_numbers or not condition_numbers or not (
        state_numbers & condition_numbers
    ):
        return False
    state_folded = _scientific_fold(state)
    condition_folded = _scientific_fold(condition_text)
    shared_cues = (
        "delay",
        "temperature",
        "orientation",
        "direction",
        "condition",
        "aged",
        "aging",
        "heat treatment",
        "layer",
        "wall",
        "region",
        "position",
        "plane",
    )
    if structure_state:
        # Observation-local states use preparation/deformation vocabulary that
        # is deliberately excluded from Property test-condition routing.
        shared_cues += (
            "initial",
            "sinter",
            "print",
            "fabricat",
            "powder",
            "feedstock",
            "strain",
            "creep",
            "deform",
            "interrupted",
            "as built",
            "as printed",
            "heat treated",
        )
    return any(
        cue in state_folded and cue in condition_folded for cue in shared_cues
    )


_REFERENCE_TREATMENT_FAMILIES: tuple[tuple[str, re.Pattern[str]], ...] = (
    (
        "aging",
        re.compile(r"\b(?:age|aged|aging|ageing)\w*\b"),
    ),
    (
        "annealing",
        re.compile(r"\banneal(?:ed|ing)?\w*\b"),
    ),
    (
        "solution_treatment",
        re.compile(r"\bsolution(?:ized|izing|ising|izing|treatment)?\w*\b"),
    ),
    (
        "sintering",
        re.compile(r"\bsinter(?:ed|ing)?\w*\b"),
    ),
    (
        "hip",
        re.compile(r"\bhip(?:ed|ping)?\w*\b"),
    ),
)


def _reference_treatment_state_matches_condition(
    condition: Any,
    node: OwnerNode,
) -> bool:
    """Match a cited tensile condition to one existing reference treatment.

    Reference inventories often use a compact state label (``aged condition``)
    while prose uses an inflected treatment phrase (``aging for 60 h``).  The
    ordinary numeric condition matcher cannot connect those forms when the
    state has no number.  This helper allows only a small treatment-family
    equivalence and still requires a node-local state; it never searches by
    chemistry or creates a state.
    """

    condition_text = _scientific_fold(_primary_property_condition(condition))
    state_text = _scientific_fold(node.state_raw)
    if not condition_text or not state_text:
        return False
    if _condition_matches_state(condition, node):
        return True
    return any(
        pattern.search(condition_text) is not None
        and pattern.search(state_text) is not None
        for _family, pattern in _REFERENCE_TREATMENT_FAMILIES
    )


def _composition_state_matches_state(
    condition: Any,
    node: OwnerNode,
) -> bool:
    """Match a composition observation state to one existing owner state.

    Composition tables often label a row/section as ``fracture surface`` while
    the inventory anchor carries the fuller state ``HIPed and tensile-fractured``.
    A literal full-label match is uncommon, so use only a small set of explicit
    state cues and require one shared cue. The caller still requires a unique
    candidate within the same owner lineage; this helper never creates or
    globally searches for an owner.
    """

    condition_folded = _scientific_fold(condition)
    state_folded = _scientific_fold(node.state_raw)
    if not condition_folded or not state_folded:
        return False
    if condition_folded in _UNREPORTED:
        return False
    if _literal_mention(str(condition), node.state_raw):
        return True
    # These are state-bearing roots, not generic process words.
    cues = (
        "fractur",
        "hip",
        "sinter",
        "powder",
        "feedstock",
        "print",
        "fabricat",
        "as built",
        "as fabricated",
        "aged",
        "aging",
        "heat treated",
    )
    return any(cue in condition_folded and cue in state_folded for cue in cues)


def _route_facts_by_condition_owner(
    anchors: Sequence[InventoryAnchor],
    facts: Sequence[AxisFact],
) -> tuple[list[AxisFact], list[PromotionIssue]]:
    """Route one source-literal state coordinate to an existing owner.

    Property facts use ``test_condition_raw`` while Structure observations and
    Composition observations use their local ``material_state``. Both
    coordinates must be grounded in the fact's own evidence and must match one
    already existing inventory state.
    This never creates an owner from a number or from source text.  A tie or a
    missing match is preserved for the ambiguity gate instead of resolved by
    confidence/order.
    """

    graph = build_owner_graph(anchors)
    if not graph.nodes:
        return list(facts), []
    accepted: list[AxisFact] = []
    issues: list[PromotionIssue] = []
    for fact in facts:
        if isinstance(fact, PropertyFact):
            coordinate_kind = "test_condition_raw"
            coordinate = fact.data.get("test_condition_raw")
        elif (
            isinstance(fact, CompositionFact)
            and fact.fact_type == "composition_observation"
        ):
            coordinate_kind = "composition_material_state"
            coordinate = fact.data.get("material_state")
        elif (
            isinstance(fact, StructureFact)
            and fact.fact_type == "structure_observation"
        ):
            coordinate_kind = "material_state"
            coordinate = fact.data.get("material_state")
        else:
            accepted.append(fact)
            continue
        condition = str(coordinate or "").strip()
        if not condition or _scientific_fold(condition) in _UNREPORTED:
            accepted.append(fact)
            continue
        evidence = _fact_evidence(fact)
        if not _payload_grounded(condition, evidence):
            accepted.append(fact)
            continue
        record = build_promotion_records([fact])[0]
        candidates = _candidate_nodes(record, graph)
        # Expand only through the explicit sample/state lineage already
        # declared by the inventory graph (same sample base or shared
        # non-chemistry alias).  A shared ``material_name_raw`` is deliberately
        # *not* a lineage key: the same alloy designation can have independent
        # specimens, heat treatments, or test rows in one paper.
        if candidates:
            expanded = {node.owner_id: node for node in candidates}
            for node in _lineage_state_nodes(candidates, graph):
                expanded[node.owner_id] = node
            candidates = list(expanded.values())
        # Prefer an exact normalized state label over the broader numeric/cue
        # matcher.  ``Initial`` and ``initial state`` both contain the word
        # ``initial`` but are distinct source-declared rows.
        exact_state_matches = [
            node
            for node in candidates
            if _identity_text(node.state_raw) == _identity_text(condition)
        ]
        structure_state = (
            isinstance(fact, StructureFact)
            and coordinate_kind == "material_state"
        )
        composition_state = (
            isinstance(fact, CompositionFact)
            and coordinate_kind == "composition_material_state"
        )
        state_matches = (
            exact_state_matches
            if exact_state_matches
            else [
                node
                for node in candidates
                if (
                    _composition_state_matches_state(condition, node)
                    if composition_state
                    else _condition_matches_state(
                        condition, node, structure_state=structure_state
                    )
                )
            ]
        )
        owner_label_in_evidence = any(
            _literal_mention("\n".join(evidence), node.sample_id_raw)
            for node in candidates
            if node.sample_id_raw
        )
        condition_label = str(fact.data.get("condition_label_raw") or "").strip()
        label_is_explicit_coordinate = bool(
            condition_label
            and _identity_text(condition_label) in _identity_text(condition)
            and _payload_grounded(condition_label, evidence)
        )
        if (
            not state_matches
            and not structure_state
            and not composition_state
            and not owner_label_in_evidence
            and label_is_explicit_coordinate
            and any(not node.state_raw for node in candidates)
        ):
            # Inventory responses may describe the generic candidate and the
            # delay-qualified state with different material-name prose.  A
            # source-literal label can still route safely when exactly one
            # current experimental state in the paper matches it.  The
            # fallback is restricted to an explicit extracted condition label
            # and owner-implicit prose: a bare ``test_condition_raw`` such as
            # ``HIPed`` is not enough to jump from sample A1 to an unrelated
            # sample A2 with the same alloy name.  This property-only fallback
            # deliberately does not apply to Structure:
            # a state such as ``fracture surface`` is not enough to jump from
            # one unresolved structure owner to an unrelated material.
            state_matches = [
                node
                for node in graph.nodes
                if node.role == "Target"
                and node.data_nature == "Experimental"
                and node.state_raw
                and _condition_matches_state(
                    condition, node, structure_state=structure_state
                )
            ]
        if len(state_matches) != 1:
            accepted.append(fact)
            continue
        target = state_matches[0]
        reassigned = fact
        state_normalized = False
        if (
            (structure_state or composition_state)
            and target.state_raw
            and _identity_text(target.state_raw)
            != _identity_text(condition)
        ):
            data = deepcopy(reassigned.data)
            data["material_state"] = target.state_raw
            if "sample_id" in data:
                data["sample_id"] = target.sample_id_raw
            reassigned = reassigned.model_copy(update={"data": data})
            state_normalized = True
        owner_reassigned = _identity_text(target.sample_id_raw) != _identity_text(
            reassigned.sample_id_raw
        )
        if owner_reassigned:
            reassigned = _reassign_fact_owner(reassigned, target.sample_id_raw)
        if not owner_reassigned and not state_normalized:
            accepted.append(fact)
            continue
        accepted.append(reassigned)
        issues.append(
            _promotion_issue(
                fact,
                code=(
                    "promotion_structure_state_owner_reassigned"
                    if structure_state
                    else "promotion_composition_state_owner_reassigned"
                    if composition_state
                    else "promotion_condition_owner_reassigned"
                ),
                message=(
                    "A source-literal "
                    + (
                        "material state"
                        if structure_state or composition_state
                        else "test condition"
                    )
                    + " matched exactly one existing state owner; the fact was "
                    "routed there without inventing an owner."
                ),
                expected={
                    "unique_existing_state_owner": target.sample_id_raw,
                    "owner_invented": False,
                    "coordinate_kind": coordinate_kind,
                    "state_normalized_to_existing_owner": state_normalized,
                    "condition_source_grounded": True,
                    "audit_preserved": True,
                },
                actual={
                    "before": fact.model_dump(),
                    "after": reassigned.model_dump(),
                    "candidate_owner_ids": [
                        node.sample_id_raw for node in candidates
                    ],
                    "condition": condition,
                },
                evidence=evidence,
            )
        )
    return accepted, issues


def _structure_source_state_matches(
    fact: StructureFact,
    candidate_nodes: Sequence[OwnerNode],
    graph: OwnerGraph,
) -> tuple[OwnerNode, ...]:
    """Find state owners named by one Structure assertion.

    Structure candidates frequently lose ``material_state`` during chunked
    extraction even though the cited sentence still says ``as-built``,
    ``after creep testing``, or names a numeric state coordinate.  The normal
    condition route cannot help when that field is ``not_reported``.  Recover
    only an existing state in the candidate's declared lineage; this is a
    source-coordinate operation, not a chemistry/name lookup.
    """

    evidence = _fact_evidence(fact)
    support = "\n".join(evidence)
    if not support or _has_table_evidence(evidence):
        # Tables have their own row/column coordinate gates.  Do not let a
        # prose state matcher reinterpret a table header or neighboring cell.
        return ()
    expanded: dict[str, OwnerNode] = {
        node.owner_id: node for node in candidate_nodes
    }
    for node in _lineage_state_nodes(candidate_nodes, graph):
        expanded[node.owner_id] = node
    state_nodes = tuple(
        node
        for node in expanded.values()
        if node.state_raw
    )
    if not state_nodes:
        return ()

    # Full source-literal state labels are the strongest coordinate.  A
    # generic base label may be present in every child alias, so only retain
    # one child when exactly one state label is literally named.
    literal = tuple(
        node
        for node in state_nodes
        if _literal_mention(support, node.state_raw)
    )
    unique_literal = {node.owner_id: node for node in literal}
    if unique_literal:
        return tuple(unique_literal[key] for key in sorted(unique_literal))

    # Numeric state labels (for example ``1% creep strain`` versus
    # ``interrupted at 1% strain at 1030 °C``) use the existing conservative
    # structure matcher.  It requires shared numeric tokens and a structural
    # cue, so a bare neighboring temperature cannot select a state.
    matched = tuple(
        node
        for node in state_nodes
        if _condition_matches_state(support, node, structure_state=True)
    )
    unique_matched = {node.owner_id: node for node in matched}
    return tuple(unique_matched[key] for key in sorted(unique_matched))


def _route_structure_source_state_owners(
    anchors: Sequence[InventoryAnchor],
    facts: Sequence[AxisFact],
) -> tuple[list[AxisFact], list[PromotionIssue]]:
    """Route Structure facts to one existing state named in their evidence.

    This closes the common cross-chunk failure where a Structure observation
    keeps a generic/base ``Sample_ID`` and ``material_state=not_reported``
    while the source sentence names one state child.  A unique state is
    reassigned and normalized.  If the evidence names multiple sibling states
    without explicit collective grammar, the whole candidate is quarantined
    instead of being broadcast to one arbitrary/base owner.  Unqualified
    base-level observations remain untouched.
    """

    graph = build_owner_graph(anchors)
    if not graph.nodes:
        return list(facts), []
    accepted: list[AxisFact] = []
    issues: list[PromotionIssue] = []
    for fact in facts:
        if not isinstance(fact, StructureFact) or fact.fact_type != "structure_observation":
            accepted.append(fact)
            continue
        record = build_promotion_records([fact])[0]
        candidates = _candidate_nodes(record, graph)
        if not candidates:
            accepted.append(fact)
            continue
        matches = _structure_source_state_matches(fact, candidates, graph)
        if not matches:
            accepted.append(fact)
            continue
        support = "\n".join(_fact_evidence(fact))
        if len(matches) > 1:
            # Explicit collective assertions (``both states ...``, ``all
            # samples ...``) are valid shared facts and are intentionally
            # left for the existing shared-owner gates.
            if _has_collective_owner_scope(support):
                accepted.append(fact)
                continue
            issues.append(
                _promotion_issue(
                    fact,
                    code="promotion_structure_source_state_ambiguous_quarantined",
                    message=(
                        "A Structure assertion named multiple existing state "
                        "owners without a collective/one-to-one coordinate; "
                        "the candidate was isolated instead of broadcast."
                    ),
                    expected={
                        "unique_existing_state_owner": True,
                        "broadcast": False,
                        "collective_owner_grammar": True,
                        "audit_preserved": True,
                    },
                    actual={
                        "removed": fact.model_dump(),
                        "candidate_owners": [node.sample_id_raw for node in candidates],
                        "matched_states": [node.sample_id_raw for node in matches],
                        "reason": "multiple_source_state_coordinates",
                    },
                    evidence=_fact_evidence(fact),
                )
            )
            continue

        target = matches[0]
        # A state-qualified sample label is already an existing owner
        # coordinate.  Do not rewrite its ``material_state`` merely because
        # the extractor left that redundant field as ``not_reported``; this
        # preserves shared-owner assertions and keeps the change limited to
        # genuine base/generic-owner projections.
        if any(
            node.owner_id == target.owner_id and node.state_raw
            for node in candidates
        ):
            accepted.append(fact)
            continue
        data = deepcopy(fact.data)
        state_normalized = (
            _identity_text(data.get("material_state"))
            != _identity_text(target.state_raw)
        )
        if target.state_raw:
            data["material_state"] = target.state_raw
        reassigned = fact.model_copy(deep=True, update={"data": data})
        owner_reassigned = _identity_text(reassigned.sample_id_raw) != _identity_text(
            target.sample_id_raw
        )
        if owner_reassigned:
            reassigned = _reassign_fact_owner(reassigned, target.sample_id_raw)
        if not owner_reassigned and not state_normalized:
            accepted.append(fact)
            continue
        accepted.append(reassigned)
        issues.append(
            _promotion_issue(
                fact,
                code="promotion_structure_source_state_owner_reassigned",
                message=(
                    "A Structure assertion named one existing state owner; "
                    "the candidate was routed there without inventing an owner."
                ),
                expected={
                    "unique_existing_state_owner": target.sample_id_raw,
                    "owner_invented": False,
                    "state_source_grounded": True,
                    "audit_preserved": True,
                },
                actual={
                    "before": fact.model_dump(),
                    "after": reassigned.model_dump(),
                    "matched_state": target.state_raw,
                    "candidate_owners": [node.sample_id_raw for node in candidates],
                },
                evidence=_fact_evidence(fact),
            )
        )
    return accepted, issues


def _respectively_descriptor(fact: AxisFact) -> tuple[str, str] | None:
    """Return a same-metric key for conservative ``respectively`` gating."""

    if isinstance(fact, PropertyFact):
        return (
            "property",
            "|".join(
                (
                    _scientific_fold(fact.data.get("property_name_raw")),
                    _scientific_fold(fact.data.get("unit_raw")),
                )
            ),
        )
    if isinstance(fact, StructureFact) and fact.fact_type == "structure_observation":
        features = tuple(
            sorted(
                _scientific_fold(row.get("feature_name_raw"))
                for row in fact.data.get("features", []) or []
                if isinstance(row, dict) and row.get("feature_name_raw")
            )
        )
        if features:
            return "structure", "|".join(features)
    if isinstance(fact, ProcessingFact) and fact.fact_type == "process_stage":
        parameters = tuple(
            sorted(
                _scientific_fold(row.get("parameter_name_raw"))
                for row in fact.data.get("parameters_raw", []) or []
                if isinstance(row, dict) and row.get("parameter_name_raw")
            )
        )
        return "processing", "|".join(
            (_scientific_fold(fact.data.get("process_name_raw")), *parameters)
        )
    return None


def _respectively_value_key(fact: AxisFact) -> str:
    if isinstance(fact, PropertyFact):
        return _scientific_compact(fact.data.get("value_raw"))
    if isinstance(fact, StructureFact):
        values = [
            _scientific_compact(row.get("value_raw"))
            for row in fact.data.get("features", []) or []
            if isinstance(row, dict)
        ]
        return "|".join(values)
    if isinstance(fact, ProcessingFact):
        values = [
            _scientific_compact(row.get("value_raw"))
            for row in fact.data.get("parameters_raw", []) or []
            if isinstance(row, dict)
        ]
        return "|".join(values)
    return ""


def _quarantine_ambiguous_respectively_groups(
    facts: Sequence[AxisFact],
) -> tuple[list[AxisFact], list[PromotionIssue]]:
    """Isolate same-metric value lists whose condition/owner coordinate vanished.

    ``respectively`` is a one-to-one relation, not evidence that every value
    belongs to every candidate owner.  When the extraction response emits multiple values
    for one metric from one exact evidence span but drops the corresponding
    labels, retaining the group would create a deterministic-looking fiction.
    Distinct property/feature/parameter names or explicit source-grounded
    conditions are sufficient coordinates and therefore pass.
    """

    records = build_promotion_records(facts)
    grouped: dict[tuple[str, str, tuple[str, ...]], list[PromotionRecord]] = {}
    for record in records:
        if "respectiv" not in _evidence_blob(record).casefold():
            continue
        descriptor = _respectively_descriptor(record.fact)
        if descriptor is None:
            continue
        grouped.setdefault(
            (descriptor[0], descriptor[1], record.normalized_evidence), []
        ).append(record)

    removed: set[int] = set()
    issues: list[PromotionIssue] = []
    for rows in grouped.values():
        if len(rows) < 2:
            continue
        values = [_respectively_value_key(row.fact) for row in rows]
        if not values:
            continue
        conditions = [
            str(row.fact.data.get("test_condition_raw") or "").strip()
            if isinstance(row.fact, PropertyFact)
            else ""
            for row in rows
        ]
        source = _evidence_blob(rows[0])
        grounded_conditions = [
            value
            for value, row in zip(conditions, rows)
            if value and _payload_grounded(value, row.evidence)
        ]
        if len(grounded_conditions) == len(rows) and len(
            {_scientific_fold(value) for value in grounded_conditions}
        ) == len(rows):
            continue

        owners = {_identity_text(row.explicit_owner) for row in rows}
        # Candidate owner fields are not coordinates by themselves.  A chunk
        # can assign the same shared ``respectively`` span to several owners
        # without quoting those labels.  Treat owner order as safe only when
        # every owner is literally named in the exact evidence span.
        distinct_owner_labels = (
            len(owners) == len(rows)
            and all(
                _literal_mention(source, row.explicit_owner)
                for row in rows
                if str(row.explicit_owner or "").strip()
            )
        )
        if distinct_owner_labels:
            # Explicit owner order is handled by the dedicated prose gate. Do
            # not duplicate its audit or quarantine a correctly ordered pair.
            continue

        conflict = [row.fact.model_dump() for row in rows]
        for row in rows:
            removed.add(id(row.fact))
            issues.append(
                _promotion_issue(
                    row.fact,
                    code="promotion_respectively_mapping_ambiguous_quarantined",
                    message=(
                        "Multiple values from one respectively assertion share "
                        "one metric but no unique condition or owner coordinate; "
                        "the projection was isolated instead of broadcast."
                    ),
                    expected={
                        "one_to_one_condition_or_owner_coordinate": True,
                        "broadcast": False,
                        "audit_preserved": True,
                    },
                    actual={
                        "removed": row.fact.model_dump(),
                        "conflict_set": conflict,
                        "source_assertion": source,
                    },
                    evidence=list(row.evidence),
                )
            )
    return [fact for fact in facts if id(fact) not in removed], issues


def _respectively_state_coordinate(fact: AxisFact) -> str:
    """Return the explicit condition/state coordinate carried by a fact."""

    if isinstance(fact, PropertyFact):
        # Keep only the primary coordinate.  The materializer may append a
        # method/protocol block after a blank line or pipe separator; that
        # block is not an owner selector.
        return _primary_property_condition(fact.data.get("test_condition_raw"))
    if isinstance(fact, StructureFact) and fact.fact_type == "structure_observation":
        return str(fact.data.get("material_state") or "").strip()
    if isinstance(fact, CompositionFact) and fact.fact_type == "composition_observation":
        return str(fact.data.get("material_state") or "").strip()
    return ""


_STATE_COORDINATE_STOPWORDS = frozenset(
    {"of", "the", "at", "for", "and", "in", "on", "condition", "under"}
)


def _state_coordinate_score(condition: str, state: str) -> tuple[int, int] | None:
    """Score a state label against a condition after conservative tokenization."""

    condition_tokens = {
        token
        for token in re.findall(r"[a-z0-9μ]+", _scientific_fold(condition))
        if token not in _STATE_COORDINATE_STOPWORDS
    }
    state_tokens = {
        token
        for token in re.findall(r"[a-z0-9μ]+", _scientific_fold(state))
        if token not in _STATE_COORDINATE_STOPWORDS
    }
    if not condition_tokens or not condition_tokens <= state_tokens:
        return None
    # Prefer the shortest source state that contains every condition token.
    # This disambiguates ``0 s delay`` from the broader ``0 s interlayer
    # delay`` without falling back to item order or material-name similarity.
    return (len(state_tokens - condition_tokens), -len(condition_tokens))


def _quarantine_respectively_state_owner_projections(
    anchors: Sequence[InventoryAnchor],
    facts: Sequence[AxisFact],
) -> tuple[list[AxisFact], list[PromotionIssue]]:
    """Route explicit respectively coordinates to a unique existing state.

    A high-recall chunk can preserve the condition on each value while losing
    the state owner, leaving a group such as ``0 s``/``120 s`` on one generic
    base item.  This pass uses only the exact evidence span and existing owner
    states.  It requires a bijection across the whole group, so a partial or
    tied mapping is a no-op and remains governed by the existing ambiguity
    gates.
    """

    graph = build_owner_graph(anchors)
    if not graph.nodes:
        return list(facts), []
    records = build_promotion_records(facts)
    grouped: dict[tuple[str, tuple[str, ...]], list[PromotionRecord]] = {}
    for record in records:
        fact = record.fact
        if not isinstance(fact, (PropertyFact, CompositionFact, StructureFact)):
            continue
        if isinstance(fact, CompositionFact) and fact.fact_type != "composition_observation":
            continue
        if isinstance(fact, StructureFact) and fact.fact_type != "structure_observation":
            continue
        descriptor = _respectively_descriptor(fact)
        if descriptor is None:
            # Composition observations are atomic bundles rather than one
            # scalar per component; use their semantic signature only when a
            # future extractor emits multiple state-qualified bundles.
            if isinstance(fact, CompositionFact):
                descriptor = ("composition", semantic_fact_signature(fact))
            else:
                continue
        evidence = tuple(row for row in record.normalized_evidence if row)
        if not evidence or not any("respectively" in row for row in evidence):
            continue
        grouped.setdefault((str(descriptor), evidence), []).append(record)

    accepted = list(facts)
    replacements: dict[int, AxisFact] = {}
    issues: list[PromotionIssue] = []
    for (descriptor, evidence), rows in grouped.items():
        if len(rows) < 2:
            continue
        coordinates = [_respectively_state_coordinate(row.fact) for row in rows]
        if any(not value or _scientific_fold(value) in _UNREPORTED for value in coordinates):
            continue
        if len({_scientific_fold(value) for value in coordinates}) != len(coordinates):
            continue
        support = "\n".join(evidence)
        targets: list[OwnerNode] = []
        for row, coordinate in zip(rows, coordinates):
            structure_state = isinstance(row.fact, StructureFact)
            composition_state = isinstance(row.fact, CompositionFact)
            matches = [
                node
                for node in graph.nodes
                if node.state_raw
                and node.role == "Target"
                and node.data_nature == "Experimental"
                and (
                    _composition_state_matches_state(coordinate, node)
                    if composition_state
                    else _condition_matches_state(
                        coordinate, node, structure_state=structure_state
                    )
                )
            ]
            if len(matches) > 1:
                scored = [
                    (score, node)
                    for node in matches
                    if (score := _state_coordinate_score(coordinate, node.state_raw))
                    is not None
                ]
                if scored:
                    best_score = min(score for score, _ in scored)
                    best = [node for score, node in scored if score == best_score]
                    matches = best
            unique = {node.owner_id: node for node in matches}
            if len(unique) != 1:
                targets = []
                break
            targets.append(next(iter(unique.values())))
        if len(targets) != len(rows) or len({node.owner_id for node in targets}) != len(targets):
            continue
        # Every target must have the same role/data nature as the candidate's
        # current owner.  This prevents an experimental result from jumping to
        # a literature/reference state merely because a condition string looks
        # similar.
        compatible = True
        for row, target in zip(rows, targets):
            current = [
                node
                for node in graph.nodes
                if _identity_text(node.sample_id_raw)
                == _identity_text(row.fact.sample_id_raw)
            ]
            if current and not any(
                node.role == target.role and node.data_nature == target.data_nature
                for node in current
            ):
                compatible = False
                break
        if not compatible:
            continue
        for row, target in zip(rows, targets):
            fact = row.fact
            if _identity_text(fact.sample_id_raw) == _identity_text(target.sample_id_raw):
                continue
            reassigned = _reassign_fact_owner(fact, target.sample_id_raw)
            replacements[id(fact)] = reassigned
            issues.append(
                _promotion_issue(
                    fact,
                    code="promotion_respectively_state_owner_reassigned",
                    message=(
                        "A respectively assertion supplied a unique source "
                        "condition-to-state mapping; the fact was routed to "
                        "the existing state owner without creating an owner."
                    ),
                    expected={
                        "bijective_condition_state_mapping": True,
                        "owner_invented": False,
                        "audit_preserved": True,
                    },
                    actual={
                        "before": fact.model_dump(),
                        "after": reassigned.model_dump(),
                        "condition": _respectively_state_coordinate(fact),
                        "target_owner": target.sample_id_raw,
                        "group_descriptor": descriptor,
                        "group_conditions": coordinates,
                    },
                    evidence=list(row.evidence),
                )
            )
    if not replacements:
        return accepted, issues
    return [replacements.get(id(fact), fact) for fact in accepted], issues


def _property_fanout_descriptor(fact: AxisFact) -> tuple[str, str] | None:
    """Return the scalar Property axis used by prose fan-out gating."""

    if not isinstance(fact, PropertyFact):
        return None
    name = _scientific_fold(fact.data.get("property_name_raw"))
    unit = _scientific_fold(fact.data.get("unit_raw"))
    if not name or name in _UNREPORTED:
        return None
    return name, unit


def _quarantine_ambiguous_property_fanout(
    facts: Sequence[AxisFact],
) -> tuple[list[AxisFact], list[PromotionIssue]]:
    """Isolate multiple same-metric values copied from one prose assertion.

    High-recall extraction often turns a comparison such as ``hardness rose
    from 334 HV to 346 HV`` into two scalar Properties on one generic owner.
    The values are source-supported, but their owner/state coordinate is not;
    keeping both creates a false pair of measurements.  This gate is deliberately
    source-only and conservative: a table is handled by the row/column gate,
    while distinct source-grounded owners or conditions are accepted.
    """

    records = build_promotion_records(facts)
    grouped: dict[tuple[tuple[str, str], tuple[str, ...]], list[PromotionRecord]] = {}
    for record in records:
        descriptor = _property_fanout_descriptor(record.fact)
        if descriptor is None:
            continue
        # The table gate owns Markdown coordinate semantics.  Do not let a
        # repeated table row be mistaken for an unqualified prose comparison.
        if _has_table_evidence(record.evidence):
            continue
        grouped.setdefault((descriptor, record.normalized_evidence), []).append(record)

    removed: set[int] = set()
    issues: list[PromotionIssue] = []
    for (descriptor, _), rows in grouped.items():
        if len(rows) < 2:
            continue
        values = [
            _scientific_compact(row.fact.data.get("value_raw"))
            for row in rows
            if isinstance(row.fact, PropertyFact)
        ]
        if len(values) < 2 or len(set(values)) < 2:
            # Exact same-owner duplicates are handled by the normal assertion
            # deduplicator.  A same-valued multi-owner projection is still
            # ambiguous and is handled below.
            owner_keys = {_identity_text(row.explicit_owner) for row in rows}
            if len(owner_keys) <= 1:
                continue

        conditions = [
            str(row.fact.data.get("test_condition_raw") or "").strip()
            for row in rows
        ]
        grounded_conditions = [
            value
            for value, row in zip(conditions, rows)
            if value and _payload_grounded(value, row.evidence)
        ]
        if len(grounded_conditions) == len(rows) and len(
            {_scientific_fold(value) for value in grounded_conditions}
        ) == len(rows):
            continue

        source = _evidence_blob(rows[0])
        distinct_owner_labels = (
            len({_identity_text(row.explicit_owner) for row in rows}) == len(rows)
            and all(
                str(row.explicit_owner or "").strip()
                and _literal_mention(source, row.explicit_owner)
                for row in rows
            )
        )
        if distinct_owner_labels:
            continue

        conflict = [row.fact.model_dump() for row in rows]
        for row in rows:
            removed.add(id(row.fact))
            issues.append(
                _promotion_issue(
                    row.fact,
                    code="promotion_property_value_fanout_ambiguous_quarantined",
                    message=(
                        "Multiple scalar values for one Property metric came from "
                        "one prose assertion without a unique source owner or "
                        "condition coordinate; the fan-out was isolated."
                    ),
                    expected={
                        "one_to_one_owner_or_condition_coordinate": True,
                        "broadcast": False,
                        "audit_preserved": True,
                    },
                    actual={
                        "removed": row.fact.model_dump(),
                        "conflict_set": conflict,
                        "property_descriptor": descriptor,
                        "source_assertion": source,
                    },
                    evidence=list(row.evidence),
                )
            )
    return [fact for fact in facts if id(fact) not in removed], issues


def _quarantine_source_block_property_fanout(
    anchors: Sequence[InventoryAnchor],
    facts: Sequence[AxisFact],
    source_text: str,
) -> tuple[list[AxisFact], list[PromotionIssue]]:
    """Isolate unqualified same-metric values split across extraction chunks.

    The exact-evidence fan-out gate above intentionally uses the copied
    evidence tuple as its grouping key.  That is safe, but a chunked extractor
    can preserve slightly different subsets of one paragraph in each result,
    allowing a single comparison to evade the gate.  This pass joins only
    through one unambiguous *prose source block* from the paper itself and
    keeps all table/owner/condition coordinates conservative.  The new
    same-valued branch is limited to non-core Properties; the historical
    different-valued branch remains active for core tensile so its existing
    coordinate protection is unchanged.

    No source order, confidence, GT, or model signal is used.  When a
    conflict cannot be proven to be an unqualified projection, the candidates
    are left unchanged for review.
    """

    blocks = _source_blocks(source_text)
    if not blocks:
        return list(facts), []
    graph = build_owner_graph(anchors)
    grouped: dict[tuple[str, tuple[str, str]], list[PromotionRecord]] = {}
    for record in build_promotion_records(facts):
        descriptor = _property_fanout_descriptor(record.fact)
        if descriptor is None:
            continue
        source_key, source_kind, ambiguous = _record_source_binding(record, blocks)
        if ambiguous or source_kind != "prose":
            continue
        grouped.setdefault((source_key, descriptor), []).append(record)

    removed: set[int] = set()
    issues: list[PromotionIssue] = []
    block_by_key = {block.key: block for block in blocks}

    def state_coordinate_in_own_evidence(record: PromotionRecord) -> bool:
        """Accept a compact source-state owner when chunk text omits a noun.

        OCR chunks often keep "1290 deg C" but drop the trailing "sample"
        while the inventory owner is "1290 deg C sample".  A numeric token
        alone is not enough ("N1" would match every sentence), so require an
        explicit state/condition cue in the owner label as well.
        """

        owner = _scientific_fold(record.explicit_owner)
        owner_numbers = _numeric_tokens(owner)
        if not owner_numbers or not re.search(
            r"(?ix)(?:°\s*c|\bc\s+(?:sample|specimen|condition)|"
            r"\b(?:s|h|min)\s+(?:delay|sample|condition)|"
            r"\b(?:aged|sintered|heat\s+treated|as\s+built|"
            r"as\s+printed|as\s+fabricated)\b)",
            owner,
        ):
            return False
        evidence_numbers = set(_numeric_tokens(record.evidence))
        return all(number in evidence_numbers for number in owner_numbers)

    for (source_key, descriptor), rows in grouped.items():
        if len(rows) < 2:
            continue
        values = [
            _scientific_compact(row.fact.data.get("value_raw"))
            for row in rows
            if isinstance(row.fact, PropertyFact)
        ]
        if len(values) < 2:
            continue
        same_value = len(set(values)) == 1
        is_core_tensile = any(
            is_core_tensile_property_name(
                row.fact.data.get("property_name_raw")
            )
            for row in rows
            if isinstance(row.fact, PropertyFact)
        )
        if (
            is_core_tensile
            and graph.nodes
            and tensile_coordinate_fanout_guard_v204_enabled()
            and all(
            (
                decision := _v204_tensile_assertion_decision(
                    row.fact, graph, source_text
                )
            ).status
            == "matched"
            and decision.coordinate is not None
            and any(
                _v204_same_existing_owner(
                    node, graph.node(decision.coordinate.owner_key)
                )
                for node in _candidate_nodes(row, graph)
            )
            for row in rows
            if isinstance(row.fact, PropertyFact)
            )
        ):
            # The complete source assertion proves an independent owner/value
            # coordinate for every candidate in this apparent fanout group.
            # Preserve the rows; the earlier owner gate already emitted the
            # complete per-coordinate audit decisions.
            continue
        if same_value and is_core_tensile:
            continue
        block = block_by_key.get(source_key)
        if block is None or _has_collective_owner_scope(block.normalized_text):
            continue

        conditions = [
            str(row.fact.data.get("test_condition_raw") or "").strip()
            for row in rows
        ]
        grounded_conditions = [
            condition
            for condition, row in zip(conditions, rows)
            if condition
            and _scientific_fold(condition) not in _UNREPORTED
            and _payload_grounded(condition, row.evidence)
        ]
        # A one-to-one source-grounded condition is a valid coordinate even
        # when the same metric appears several times in one paragraph.
        if len(grounded_conditions) == len(rows) and len(
            {_scientific_fold(value) for value in grounded_conditions}
        ) == len(rows):
            continue

        owners = [_identity_text(row.explicit_owner) for row in rows]
        distinct_owner_labels = (
            len(set(owners)) == len(rows)
            and all(
                str(row.explicit_owner or "").strip()
                and (
                    _literal_mention("\n".join(row.evidence), row.explicit_owner)
                    or state_coordinate_in_own_evidence(row)
                )
                for row in rows
            )
        )
        # Explicit owner/value pairs are safe.  Requiring each candidate's
        # own evidence to contain its owner avoids treating paragraph-level
        # owner lists as an ordered coordinate.
        if distinct_owner_labels:
            continue

        conflict = [row.fact.model_dump() for row in rows]
        issue_code = (
            "promotion_source_block_property_same_value_fanout_quarantined"
            if same_value
            else "promotion_source_block_property_fanout_quarantined"
        )
        issue_message = (
            "The same scalar value for one non-core Property metric was emitted "
            "for multiple owners from one prose source block without a unique "
            "owner or condition coordinate; the cross-chunk fan-out was isolated."
            if same_value
            else (
                "Multiple values for one Property metric were emitted from one "
                "prose source block without a unique owner or condition "
                "coordinate; the cross-chunk fan-out was isolated."
            )
        )
        for row in rows:
            removed.add(id(row.fact))
            issues.append(
                _promotion_issue(
                    row.fact,
                    code=issue_code,
                    message=issue_message,
                    expected={
                        "one_to_one_owner_or_condition_coordinate": True,
                        "source_kind": "prose",
                        "broadcast": False,
                        "audit_preserved": True,
                    },
                    actual={
                        "removed": row.fact.model_dump(),
                        "conflict_set": conflict,
                        "property_descriptor": descriptor,
                        **({"same_value": True} if same_value else {}),
                        "source_block": {
                            "key": block.key,
                            "start_line": block.start_line,
                            "end_line": block.end_line,
                            "text": block.normalized_text,
                        },
                    },
                    evidence=list(row.evidence),
                )
            )
    return [fact for fact in facts if id(fact) not in removed], issues


def _quarantine_source_block_structural_fanout(
    facts: Sequence[AxisFact], source_text: str
) -> tuple[list[AxisFact], list[PromotionIssue]]:
    """Isolate unqualified multi-value Structure/Processing projections.

    Property fan-out already has a dedicated gate, but the same cross-chunk
    failure occurs in the other numeric axes: one prose sentence is copied into
    several chunks and a list such as ``41 and 9.5 µm`` becomes two facts under
    one generic owner.  Tables, explicit ``respectively`` mappings, collective
    assertions, and facts with a literal owner/condition coordinate are left
    untouched.  The gate never merges or invents a coordinate; it only removes
    the ambiguous atomic payload and records the complete parent fact.
    """

    blocks = _source_blocks(source_text)
    if not blocks:
        return list(facts), []
    block_by_key = {block.key: block for block in blocks}

    @dataclass(frozen=True)
    class _AtomicProjection:
        fact: AxisFact
        block: _SourceBlock
        descriptor: tuple[str, str, str, str]
        value: str
        evidence: tuple[str, ...]
        index: int
        payload: dict[str, Any]

    rows: list[_AtomicProjection] = []
    for fact in facts:
        if isinstance(fact, StructureFact) and fact.fact_type == "structure_observation":
            fallback = _fact_evidence(fact)
            # A single observation can legitimately contain several different
            # entities/features.  Treat each atomic feature as a projection and
            # retain the entity label in the descriptor so RX/PRX (or X/Y/Z)
            # remain independent coordinates.
            payload_index = 0
            candidates: list[tuple[dict[str, Any], str, int]] = []
            for entity in fact.data.get("entities") or []:
                if not isinstance(entity, dict):
                    continue
                entity_name = str(
                    entity.get("name_raw") or entity.get("raw_expression") or ""
                ).strip()
                for feature in entity.get("features") or []:
                    if isinstance(feature, dict):
                        current_index = payload_index
                        payload_index += 1
                        candidates.append((feature, entity_name, current_index))
            for feature in fact.data.get("features") or []:
                if isinstance(feature, dict):
                    current_index = payload_index
                    payload_index += 1
                    candidates.append((feature, "", current_index))
            for feature, entity_name, feature_index in candidates:
                value = str(feature.get("value_raw") or "").strip()
                name = str(
                    feature.get("canonical_name")
                    or feature.get("feature_name_raw")
                    or ""
                ).strip()
                if not name or not value:
                    continue
                evidence = tuple(_feature_evidence(feature, fallback))
                if not evidence or _has_table_evidence(evidence):
                    continue
                matches = [
                    block
                    for block in blocks
                    if block.kind == "prose"
                    and all(
                        normalize_evidence_text(row) in block.normalized_text
                        for row in evidence
                    )
                ]
                if len(matches) != 1:
                    continue
                unit = str(feature.get("unit_raw") or "").strip()
                rows.append(
                    _AtomicProjection(
                        fact=fact,
                        block=matches[0],
                        descriptor=(
                            "structure",
                            _scientific_fold(name),
                            _scientific_fold(unit),
                            _scientific_fold(entity_name),
                        ),
                        value=value,
                        evidence=evidence,
                        index=feature_index,
                        payload={
                            "kind": "feature",
                            "entity_name": entity_name,
                            "feature": deepcopy(feature),
                        },
                    )
                )
        elif isinstance(fact, ProcessingFact) and fact.fact_type == "process_stage":
            evidence = tuple(_fact_evidence(fact))
            if not evidence or _has_table_evidence(evidence):
                continue
            matches = [
                block
                for block in blocks
                if block.kind == "prose"
                and all(
                    normalize_evidence_text(row) in block.normalized_text
                    for row in evidence
                )
            ]
            if len(matches) != 1:
                continue
            for index, parameter in enumerate(fact.data.get("parameters_raw") or []):
                if not isinstance(parameter, dict):
                    continue
                name = str(parameter.get("parameter_name_raw") or "").strip()
                value = str(parameter.get("value_raw") or "").strip()
                if not name or not value:
                    continue
                parameter_evidence = tuple(
                    _feature_evidence(parameter, evidence)
                )
                if _has_table_evidence(parameter_evidence):
                    continue
                rows.append(
                    _AtomicProjection(
                        fact=fact,
                        block=matches[0],
                        descriptor=(
                            "processing",
                            _scientific_fold(name),
                            _scientific_fold(parameter.get("unit_raw")),
                            _scientific_fold(
                                parameter.get("condition_label_raw")
                            ),
                        ),
                        value=value,
                        evidence=parameter_evidence,
                        index=index,
                        payload={"kind": "parameter", "parameter": deepcopy(parameter)},
                    )
                )

    grouped: dict[tuple[str, tuple[str, str, str, str]], list[_AtomicProjection]] = {}
    for row in rows:
        grouped.setdefault((row.block.key, row.descriptor), []).append(row)

    remove_structure: dict[int, set[int]] = {}
    remove_processing: dict[int, set[int]] = {}
    issues: list[PromotionIssue] = []

    def _coordinate_is_explicit(row: _AtomicProjection, group: Sequence[_AtomicProjection]) -> bool:
        block_text = row.block.normalized_text
        if "respectiv" in block_text or _has_collective_owner_scope(block_text):
            return True
        # One-to-one literal owner labels are a valid coordinate, but the
        # label must occur in that candidate's own evidence, not merely in the
        # shared paragraph copied to every chunk.
        owner = str(row.fact.sample_id_raw or "").strip()
        owner_keys = {
            _identity_text(other.fact.sample_id_raw) for other in group
        }
        if (
            len(owner_keys) == len(group)
            and owner
            and _distinctive_owner_label(owner)
            and _literal_mention("\n".join(row.evidence), owner)
        ):
            # The evidence attached to a chunk frequently contains the whole
            # comparison sentence, so a plain literal mention is not enough:
            # ``H230 and H230AM ... 13.2 and 10.9`` mentions both owners for
            # both values.  Accept an owner pair only when the candidate's
            # value is in a bounded local phrase that contains this owner and
            # no sibling owner.  Parenthetical forms such as ``H230AM (10
            # um)`` and chunk-local ``A1 ... 10 um`` therefore survive, while
            # an unqualified ordered list is quarantined for review.
            sibling_owners = [
                str(other.fact.sample_id_raw or "").strip()
                for other in group
                if _identity_text(other.fact.sample_id_raw)
                != _identity_text(row.fact.sample_id_raw)
            ]
            if _owner_value_local_pair(
                row.value,
                row.evidence,
                owner,
                sibling_owners,
            ):
                return True
        if isinstance(row.fact, StructureFact):
            state = str(row.fact.data.get("material_state") or "").strip()
            entity = str(row.payload.get("entity_name") or "").strip()
            coordinate = entity or state
            if coordinate and _payload_grounded(coordinate, row.evidence):
                # A coordinate is only decisive when it is unique in the
                # conflicting set; two rows sharing the same state/entity are
                # still an unresolved value fan-out.
                coordinates = {
                    _scientific_fold(
                        str(other.payload.get("entity_name") or "").strip()
                        or str(other.fact.data.get("material_state") or "").strip()
                    )
                    for other in group
                }
                return len(coordinates) == len(group)
        else:
            condition = str(row.payload["parameter"].get("condition_label_raw") or "").strip()
            if condition and _payload_grounded(condition, row.evidence):
                conditions = {
                    _scientific_fold(
                        str(other.payload["parameter"].get("condition_label_raw") or "").strip()
                    )
                    for other in group
                }
                return len(conditions) == len(group)
        return False

    for (_, _), group in grouped.items():
        if len(group) < 2 or len({_scientific_compact(row.value) for row in group}) < 2:
            continue
        # A fact can legitimately report multiple differently named entities
        # or parameters; this function only sees identical descriptors.
        if all(_coordinate_is_explicit(row, group) for row in group):
            continue
        conflict = [row.fact.model_dump() for row in group]
        for row in group:
            if isinstance(row.fact, StructureFact):
                remove_structure.setdefault(id(row.fact), set()).add(row.index)
                code = "promotion_source_block_structure_fanout_quarantined"
                path = "data.entities/features"
            else:
                remove_processing.setdefault(id(row.fact), set()).add(row.index)
                code = "promotion_source_block_processing_fanout_quarantined"
                path = "data.parameters_raw"
            issues.append(
                _promotion_issue(
                    row.fact,
                    code=code,
                    message=(
                        "Multiple values for one source-block "
                        + ("Structure feature" if isinstance(row.fact, StructureFact) else "Processing parameter")
                        + " had no unique owner, state, entity, or condition coordinate; "
                        "the cross-chunk projection was isolated."
                    ),
                    expected={
                        "one_to_one_coordinate": True,
                        "broadcast": False,
                        "audit_preserved": True,
                    },
                    actual={
                        "removed": row.payload,
                        "conflict_set": conflict,
                        "source_block": {
                            "key": row.block.key,
                            "start_line": row.block.start_line,
                            "end_line": row.block.end_line,
                            "text": row.block.normalized_text,
                        },
                    },
                    evidence=list(row.evidence),
                )
            )

    accepted: list[AxisFact] = []
    for fact in facts:
        if isinstance(fact, StructureFact) and id(fact) in remove_structure:
            data = deepcopy(fact.data)
            remove = remove_structure[id(fact)]
            feature_index = 0
            entities: list[dict[str, Any]] = []
            for entity in data.get("entities") or []:
                if not isinstance(entity, dict):
                    continue
                cleaned = deepcopy(entity)
                kept_features = []
                for feature in entity.get("features") or []:
                    if not isinstance(feature, dict):
                        continue
                    if feature_index not in remove:
                        kept_features.append(feature)
                    feature_index += 1
                cleaned["features"] = kept_features
                if kept_features or cleaned.get("raw_expression") or cleaned.get("name_raw"):
                    entities.append(cleaned)
            top_features = []
            for feature in data.get("features") or []:
                if not isinstance(feature, dict):
                    continue
                if feature_index not in remove:
                    top_features.append(feature)
                feature_index += 1
            data["entities"] = entities
            data["features"] = top_features
            if entities or top_features:
                accepted.append(fact.model_copy(deep=True, update={"data": data}))
            continue
        if isinstance(fact, ProcessingFact) and id(fact) in remove_processing:
            data = deepcopy(fact.data)
            remove = remove_processing[id(fact)]
            data["parameters_raw"] = [
                parameter
                for index, parameter in enumerate(data.get("parameters_raw") or [])
                if index not in remove
            ]
            if data["parameters_raw"] or fact.fact_type != "process_stage":
                accepted.append(fact.model_copy(deep=True, update={"data": data}))
            continue
        accepted.append(fact)
    return accepted, issues


# ``_source_block_property_fanout`` and ``_source_block_structural_fanout``
# protect one metric at a time.  They cannot catch a more common chunking
# failure in which one paragraph names two materials, then the extractor emits
# *different* parameters/features for the same generic owner.  The values are
# individually source-grounded, so a value-only check is insufficient; the
# missing invariant is the local owner/condition binding.
_PROSE_SENTENCE_SPLIT = re.compile(
    r"(?<=[.!?])\s+(?=[A-Z0-9$\\])|[;\n]+"
)


def _prose_local_segments(rows: Sequence[str]) -> tuple[str, ...]:
    """Return conservative prose clauses for owner/payload co-location.

    This is intentionally not a general sentence parser.  It only creates
    bounded windows for a source-local precision check and keeps decimal
    points, LaTeX, and table rows out of the path (tables are filtered by the
    caller).  A clause may be slightly larger than a grammatical sentence;
    that is safer than inventing a narrower coordinate.
    """

    segments: list[str] = []
    for row in rows:
        text = str(row or "").strip()
        if not text:
            continue
        for segment in _PROSE_SENTENCE_SPLIT.split(text):
            normalized = re.sub(r"\s+", " ", segment).strip()
            if normalized:
                segments.append(normalized)
    return tuple(dict.fromkeys(segments))


def _prose_fact_payload_in_segment(
    fact: AxisFact,
    segment: str,
) -> bool:
    """Return whether one atomic payload is literally present in *segment*.

    Numeric payloads use token-aware grounding.  Qualitative Structure payloads
    use their named entity/feature literal because values such as ``present``
    and ``fine`` are too generic to prove a binding on their own.  The helper
    deliberately does not infer synonyms or convert units.
    """

    if isinstance(fact, PropertyFact):
        value = fact.data.get("value_raw")
        name = str(fact.data.get("property_name_raw") or "").strip()
        return bool(
            _payload_grounded(value, [segment])
            and (
                not name
                or _literal_mention(segment, name)
                or bool(_numeric_tokens(value))
            )
        )

    if isinstance(fact, ProcessingFact) and fact.fact_type == "process_stage":
        parameters = [
            row
            for row in fact.data.get("parameters_raw") or []
            if isinstance(row, dict)
        ]
        for parameter in parameters:
            value = parameter.get("value_raw")
            name = str(parameter.get("parameter_name_raw") or "").strip()
            if not value or not _payload_grounded(value, [segment]):
                continue
            if (
                not name
                or _literal_mention(segment, name)
                or bool(_numeric_tokens(value))
            ):
                return True
        # Parameter-free stages still need a local event/owner pair.  A
        # process name alone is not enough; the direct event predicate keeps
        # labels such as ``LPBF`` from becoming fabricated process facts.
        process_name = str(fact.data.get("process_name_raw") or "").strip()
        return bool(
            process_name
            and _literal_mention(segment, process_name)
            and _PROCESS_DIRECT_EVENT_ASSERTION.search(segment)
        )

    if isinstance(fact, StructureFact) and fact.fact_type == "structure_observation":
        fallback = _fact_evidence(fact)
        features: list[dict[str, Any]] = [
            row
            for row in fact.data.get("features") or []
            if isinstance(row, dict)
        ]
        for entity in fact.data.get("entities") or []:
            if not isinstance(entity, dict):
                continue
            features.extend(
                row for row in entity.get("features") or [] if isinstance(row, dict)
            )
            if not features and entity.get("name_raw"):
                # Entity-only observations are source-grounded only when the
                # entity itself is named in this local clause.  The existing
                # direct-assertion gate performs the polarity check later.
                if _literal_mention(segment, entity.get("name_raw")):
                    return True
        for feature in features:
            value = feature.get("value_raw")
            name = str(feature.get("feature_name_raw") or "").strip()
            if value and _payload_grounded(value, [segment]):
                if (
                    not name
                    or _literal_mention(segment, name)
                    or bool(_numeric_tokens(value))
                ):
                    return True
            if (
                name
                and not _numeric_tokens(value)
                and _literal_mention(segment, name)
            ):
                return True
        return False

    return False


def _owner_base_key(node: OwnerNode) -> str:
    return _identity_text(
        re.sub(r"\s*\[[^\]]+\]\s*$", "", node.sample_id_raw).strip()
    ) or _identity_text(node.sample_id_raw)


def _prose_segment_owner_ids(
    segment: str,
    nodes: Sequence[OwnerNode],
) -> tuple[str, ...]:
    matched = {
        node.owner_id
        for node in nodes
        if _safe_explicit_owner_label(node.sample_id_raw)
        and any(
            _literal_mention(segment, alias)
            for alias in _owner_evidence_aliases(node.sample_id_raw)
        )
    }
    return tuple(sorted(matched))


def _prose_fact_owner_bound_in_segment(
    fact: AxisFact,
    segment: str,
    candidate_nodes: Sequence[OwnerNode],
    state_nodes: Sequence[OwnerNode],
) -> bool:
    """Check a candidate owner/state literal in one payload clause."""

    candidate_ids = {node.owner_id for node in candidate_nodes}
    if any(
        node.owner_id in candidate_ids
        for node in candidate_nodes
        if _safe_explicit_owner_label(node.sample_id_raw)
        and any(
            _literal_mention(segment, alias)
            for alias in _owner_evidence_aliases(node.sample_id_raw)
        )
    ):
        return True
    if any(
        node.owner_id in candidate_ids
        for node in state_nodes
        if _safe_explicit_owner_label(node.sample_id_raw)
        and any(
            _literal_mention(segment, alias)
            for alias in _owner_evidence_aliases(node.sample_id_raw)
        )
    ):
        return True

    # A state-qualified candidate may be named by its state label while the
    # extractor drops the full ``Sample [state]`` label.  Accept that only for
    # the exact existing state node; a generic base item cannot borrow a child
    # state's coordinate.
    for node in candidate_nodes:
        if not node.state_raw:
            continue
        if _literal_mention(segment, node.state_raw):
            return True
    return False


def _prose_multi_owner_scope_is_collective(text: str) -> bool:
    """Recognize explicit shared-owner prose without guessing from order."""

    if _has_collective_owner_scope(text):
        return True
    # ``performed on S0, S15, and S70`` is an explicit owner list even when
    # the sentence does not contain the word ``both``.  Likewise, anaphora
    # such as ``A2 contained the same amount`` is a source-declared shared
    # value, not an owner-free numeric broadcast.  These cues preserve the
    # assertion for the dedicated cross-owner/ordered gates to audit.
    if re.search(
        r"(?ix)\b(?:on|for|from|between|among|within|across)\b"
        r".{0,120}\band\b",
        text,
    ):
        return True
    if re.search(r"(?ix)\b(?:same|identical|common|shared)\b", text):
        return True
    return bool(
        re.search(
            r"(?ix)\b(?:both|all|each|every)\b.{0,100}\b(?:were|was|are|is|"
            r"had|showed|exhibited|contained|consisted|fabricated|processed)\b",
            text,
        )
    )


def _quarantine_prose_multi_owner_atomicity(
    anchors: Sequence[InventoryAnchor],
    facts: Sequence[AxisFact],
    source_text: str,
) -> tuple[list[AxisFact], list[PromotionIssue]]:
    """Isolate prose facts whose owner/condition binding was lost across chunks.

    The rule is intentionally limited to non-composition, non-core-tensile
    facts.  Composition tables and the dedicated tensile gates have stronger
    coordinate logic and must not be pre-empted.  A fact survives when the
    payload is co-located with its existing owner/state label, or when the
    source explicitly declares a collective/``respectively`` relation.  If a
    paragraph names multiple material bases/states but the payload appears only
    in an owner-free clause, the entire candidate is quarantined with a full
    audit record instead of broadcasting it to one item.
    """

    graph = build_owner_graph(anchors)
    blocks = _source_blocks(source_text)
    if not graph.nodes or not blocks:
        return list(facts), []
    block_by_key = {block.key: block for block in blocks}
    accepted: list[AxisFact] = []
    issues: list[PromotionIssue] = []

    for fact in facts:
        if isinstance(fact, CompositionFact):
            accepted.append(fact)
            continue
        if isinstance(fact, PropertyFact) and is_core_tensile_property_name(
            fact.data.get("property_name_raw")
        ):
            accepted.append(fact)
            continue
        if isinstance(fact, StructureFact) and fact.fact_type != "structure_observation":
            accepted.append(fact)
            continue
        if not isinstance(fact, (PropertyFact, ProcessingFact, StructureFact)):
            accepted.append(fact)
            continue
        evidence = _fact_evidence(fact)
        if not evidence or _has_table_evidence(evidence):
            accepted.append(fact)
            continue
        record = build_promotion_records([fact])[0]
        source_key, source_kind, ambiguous = _record_source_binding(record, blocks)
        if ambiguous or source_kind != "prose":
            accepted.append(fact)
            continue
        block = block_by_key.get(source_key)
        if block is None:
            accepted.append(fact)
            continue

        named_nodes = _safe_source_owner_nodes(block.normalized_text, graph)
        base_keys = {_owner_base_key(node) for node in named_nodes}
        state_keys = {
            (_owner_base_key(node), _identity_text(node.state_raw))
            for node in named_nodes
            if node.state_raw
        }
        # Only a genuine multi-coordinate source needs this gate.  A single
        # owner paragraph may legitimately omit the sample label because the
        # surrounding inventory already provides the paper-local identity.
        multi_base = len(base_keys) > 1
        multi_state = len(state_keys) > 1
        if not multi_base and not multi_state:
            accepted.append(fact)
            continue
        block_text = block.normalized_text
        if _prose_multi_owner_scope_is_collective(block_text) or "respectiv" in block_text.casefold():
            accepted.append(fact)
            continue

        record_candidates = _candidate_nodes(record, graph)
        if not record_candidates:
            issues.append(
                _promotion_issue(
                    fact,
                    code="promotion_prose_multi_owner_atomicity_quarantined",
                    message=(
                        "A prose assertion named multiple source owners but the "
                        "candidate owner was not an existing source coordinate."
                    ),
                    expected={
                        "local_owner_or_state_binding": True,
                        "broadcast": False,
                        "audit_preserved": True,
                    },
                    actual={
                        "removed": fact.model_dump(),
                        "source_block": {
                            "key": block.key,
                            "start_line": block.start_line,
                            "end_line": block.end_line,
                        },
                        "named_owners": [node.sample_id_raw for node in named_nodes],
                        "reason": "candidate_owner_not_in_source_inventory",
                    },
                    evidence=evidence,
                )
            )
            continue

        state_nodes = _lineage_state_nodes(record_candidates, graph)
        segments = _prose_local_segments(evidence)
        bound = False
        for segment in segments:
            if not _prose_fact_payload_in_segment(fact, segment):
                continue
            if _prose_fact_owner_bound_in_segment(
                fact, segment, record_candidates, state_nodes
            ):
                # If the source explicitly names more than one state in one
                # base lineage, a generic/base candidate cannot claim a value
                # from a state sentence merely because the base alias appears.
                if multi_state:
                    segment_states = {
                        (_owner_base_key(node), _identity_text(node.state_raw))
                        for node in state_nodes
                        if node.state_raw and _literal_mention(segment, node.state_raw)
                    }
                    candidate_states = {
                        (_owner_base_key(node), _identity_text(node.state_raw))
                        for node in record_candidates
                        if node.state_raw
                    }
                    if segment_states and not (segment_states & candidate_states):
                        continue
                bound = True
                break
        if bound:
            accepted.append(fact)
            continue

        issues.append(
            _promotion_issue(
                fact,
                code="promotion_prose_multi_owner_atomicity_quarantined",
                message=(
                    "A prose payload was source-grounded but its owner/state was "
                    "not co-located with the value in an unambiguous local clause; "
                    "the cross-chunk projection was isolated."
                ),
                expected={
                    "local_owner_or_state_binding": True,
                    "broadcast": False,
                    "source_kind": "prose",
                    "audit_preserved": True,
                },
                actual={
                    "removed": fact.model_dump(),
                    "source_block": {
                        "key": block.key,
                        "start_line": block.start_line,
                        "end_line": block.end_line,
                        "text": block.normalized_text,
                    },
                    "named_owners": [node.sample_id_raw for node in named_nodes],
                    "candidate_owner": fact.sample_id_raw,
                    "reason": (
                        "multi_owner_without_local_payload_binding"
                        if multi_base
                        else "multi_state_without_local_payload_binding"
                    ),
                },
                evidence=evidence,
            )
        )
    return accepted, issues


def _raw_markdown_table_blocks(source_text: str) -> list[tuple[int, int, tuple[str, ...]]]:
    """Return raw Markdown table blocks without losing row/column boundaries.

    ``_source_blocks`` deliberately normalizes whitespace for assertion
    grouping.  Owner/value binding needs the opposite: the literal cells and
    their coordinates.  This parser is intentionally limited to the Markdown
    tables emitted by the OCR normalizers; HTML and prose are left untouched.
    """

    lines = str(source_text or "").splitlines()
    blocks: list[tuple[int, int, tuple[str, ...]]] = []
    index = 0
    while index < len(lines):
        if not lines[index].lstrip().startswith("|"):
            index += 1
            continue
        start = index
        rows: list[str] = []
        while index < len(lines) and lines[index].lstrip().startswith("|"):
            rows.append(lines[index].strip())
            index += 1
        if rows:
            blocks.append((start, index - 1, tuple(rows)))
    return blocks


def _raw_html_table_blocks(
    source_text: str,
) -> list[tuple[tuple[str, ...], str]]:
    """Return HTML table rows plus their normalized source representation.

    MinerU/PaddleOCR output frequently keeps tables as one HTML line.  The
    Markdown-only coordinate gate therefore could not see that a tensile or
    density value belonged to a different row.  We parse only literal table
    cells here; no text outside a ``<table>`` is used as an owner/value
    coordinate.  ``rowspan``/``colspan`` are expanded conservatively so a
    source row remains addressable even when the first header spans several
    columns.
    """

    if "<table" not in str(source_text or "").casefold():
        return []
    soup = BeautifulSoup(str(source_text), "html.parser")
    blocks: list[tuple[tuple[str, ...], str]] = []
    for table in soup.find_all("table"):
        raw_rows: list[list[tuple[str, int, int]]] = []
        for tr in table.find_all("tr"):
            cells = tr.find_all(["th", "td"], recursive=False)
            if not cells:
                # A few OCR renderers insert a ``tbody`` or a harmless wrapper
                # between ``tr`` and its cells.  Do not descend into nested
                # tables, which would merge unrelated coordinates.
                cells = [
                    cell
                    for cell in tr.find_all(["th", "td"])
                    if cell.find_parent("table") is table
                ]
            if not cells:
                continue
            row: list[tuple[str, int, int]] = []
            for cell in cells:
                text = " ".join(cell.get_text(" ", strip=True).split())
                try:
                    colspan = max(1, int(cell.get("colspan") or 1))
                except (TypeError, ValueError):
                    colspan = 1
                try:
                    rowspan = max(1, int(cell.get("rowspan") or 1))
                except (TypeError, ValueError):
                    rowspan = 1
                row.append((text, colspan, rowspan))
            if row:
                raw_rows.append(row)
        if not raw_rows:
            continue

        occupied: dict[tuple[int, int], str] = {}
        for row_index, raw_row in enumerate(raw_rows):
            column_index = 0
            for text, colspan, rowspan in raw_row:
                while (row_index, column_index) in occupied:
                    column_index += 1
                for row_offset in range(rowspan):
                    for column_offset in range(colspan):
                        key = (
                            row_index + row_offset,
                            column_index + column_offset,
                        )
                        # Overlapping malformed OCR spans are left with the
                        # first literal cell rather than guessed/reordered.
                        occupied.setdefault(key, text)
                column_index += colspan

        max_row = max(row for row, _ in occupied)
        max_column = max(column for _, column in occupied)
        rows: list[str] = []
        for row_index in range(max_row + 1):
            cells = [
                occupied.get((row_index, column_index), "")
                for column_index in range(max_column + 1)
            ]
            rows.append("| " + " | ".join(cells) + " |")
        # Keep a pipe-rendered representation alongside the original HTML.
        # Promotion evidence is emitted as compact Markdown rows, so matching
        # against the tag-bearing HTML string alone would never find the same
        # table even though the cells are identical.  The representation is
        # built solely from literal cells parsed above; no prose outside the
        # table can participate in owner/value binding.
        raw_normalized = normalize_evidence_text("\n".join(rows))
        if raw_normalized and rows:
            blocks.append((tuple(rows), raw_normalized))
    return blocks


def _html_table_coordinate_variants(
    lines: Sequence[str],
) -> tuple[tuple[str, ...], ...]:
    """Add a compact two-level-header view for HTML table coordinates.

    HTML ``colspan`` headers are expanded by :func:`_raw_html_table_blocks`.
    Extractor evidence, however, often joins the group and sub-header into a
    single cell (``EDS At. (%) / Al``).  The original expanded rows remain the
    canonical layout; this derived variant only makes that literal join
    addressable and never changes data-row order or values.
    """

    parsed = [
        _table_cells(line)
        for line in lines
        if _table_cells(line) and not _is_table_separator(_table_cells(line))
    ]
    if len(parsed) < 3 or len(parsed[0]) != len(parsed[1]):
        return ()
    first, second = parsed[0], parsed[1]
    if not any(
        _scientific_fold(cell).startswith(
            ("eds at", "phases", "grain size", "properties", "process variables")
        )
        or "/" in str(cell)
        for cell in first
    ):
        return ()
    merged: list[str] = []
    for parent, child in zip(first, second):
        parent_text = str(parent or "").strip()
        child_text = str(child or "").strip()
        if parent_text and child_text and _scientific_fold(parent_text) != _scientific_fold(child_text):
            merged.append(f"{parent_text} / {child_text}")
        else:
            merged.append(parent_text or child_text)
    variant = tuple(
        ["| " + " | ".join(merged) + " |"]
        + list(lines[2:])
    )
    return (variant,)


def _table_cells(line: str) -> tuple[str, ...]:
    """Split one Markdown row conservatively, preserving empty cells."""

    raw = str(line or "").strip()
    if "|" not in raw:
        return ()
    if raw.startswith("|"):
        raw = raw[1:]
    if raw.endswith("|"):
        raw = raw[:-1]
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
    return tuple(cells)


def _is_table_separator(cells: Sequence[str]) -> bool:
    return bool(cells) and all(
        bool(re.fullmatch(r":?\s*-{3,}\s*:?.*", str(cell).strip()))
        for cell in cells
    )


def _table_owner_cell_matches(cell: str, node: OwnerNode) -> bool:
    """Match a source owner label, including ``AF-RT`` state row labels."""

    text = str(cell or "").strip()
    if not text:
        return False
    for alias in node.aliases:
        if _literal_mention(text, alias):
            return True
        cell_compact = re.sub(r"[^a-z0-9]+", "", _identity_text(text))
        alias_compact = re.sub(r"[^a-z0-9]+", "", _identity_text(alias))
        if (
            alias_compact
            and len(alias_compact) >= 2
            and cell_compact.startswith(alias_compact)
            and len(cell_compact) > len(alias_compact)
        ):
            # Only accept a qualified row/header when the suffix is visibly
            # separated in the source.  This prevents ``A1`` matching ``A10``.
            boundary = text[len(alias) : len(alias) + 1]
            if boundary and not boundary.isalnum():
                return True
    return False


_TABLE_NUMERIC_TOKEN = re.compile(
    r"(?<![A-Za-z0-9])[-+]?(?:\d+(?:\.\d+)?|\.\d+)(?:[eE][-+]?\d+)?"
)


def _table_numeric_tokens(value: Any) -> tuple[str, ...]:
    """Keep decimal boundaries for Markdown cell coordinate matching."""

    return tuple(
        match.group(0).lstrip("+")
        for match in _TABLE_NUMERIC_TOKEN.finditer(str(value or ""))
    )


def _table_value_cell_matches(cell: str, value: Any) -> bool:
    """Require every numeric token in the candidate value in one cell."""

    value_tokens = _table_numeric_tokens(value)
    text = str(cell or "")
    if value_tokens:
        cell_tokens = _table_numeric_tokens(text)
        if all(token in cell_tokens for token in value_tokens):
            return True
        # Mean ± standard-deviation rows are commonly rendered as two
        # adjacent table rows (the mean row and a ``Std.`` row), while the
        # candidate contract combines them into one value.  The row/column
        # gate can still prove the owner from the primary mean token; the
        # dedicated statistical-shadow pass later binds the deviation.  Do
        # not apply this fallback to arbitrary multi-number values.
        if (
            ("±" in text or "+/-" in text or r"\pm" in text or
             "±" in str(value) or "+/-" in str(value) or r"\pm" in str(value))
            and value_tokens
        ):
            return value_tokens[0] in cell_tokens
        return False
    folded_value = _scientific_compact(value)
    return bool(folded_value and folded_value == _scientific_compact(text))


def _table_condition_matches_row(row: Sequence[str], condition: Any) -> bool:
    folded = _scientific_fold(condition)
    if not folded or folded in _UNREPORTED:
        return False
    row_text = " ".join(str(cell) for cell in row)
    # Prefer token-boundary grounding in either direction.  The reverse
    # direction is needed when a candidate carries a longer test-condition
    # paragraph but the table cell contains only its compact state label.
    # Unlike substring matching, this prevents ``0 s`` from matching the
    # numeric suffix inside ``300 s``.
    if _payload_grounded(str(condition), (row_text,)) or _payload_grounded(
        row_text, (str(condition),)
    ):
        return True
    # A numeric condition that was not grounded as a whole is not allowed to
    # fall through to the older cue matcher: ``0 s delay`` and ``300 s
    # delay`` must remain distinct coordinates.
    if _numeric_tokens(str(condition)):
        return False
    if _literal_mention(row_text, str(condition)):
        return True
    tokens = [token for token in folded.split() if len(token) > 1]
    return bool(tokens) and sum(token in _scientific_fold(row_text) for token in tokens) >= max(
        1, len(tokens) // 2
    )


def _table_condition_matches_owner_cell(
    cell: Any,
    condition: Any,
    node: OwnerNode,
) -> bool:
    """Match a condition encoded in an owner-row label.

    OCR tables often flatten a row such as ``AF-250 °C`` into the first
    (owner) cell, while the candidate still carries ``250 °C`` as its test
    condition.  The normal condition-column path cannot see that coordinate.
    Recover it only when every numeric condition token appears in the suffix
    following an explicit owner alias; this keeps arbitrary result numbers in
    other cells from becoming conditions.
    """

    condition_tokens = _numeric_tokens(condition)
    condition_folded = _scientific_fold(condition)
    if not condition_folded or not _table_owner_cell_matches(str(cell), node):
        return False
    text = str(cell or "")
    for alias in node.aliases:
        match = re.search(re.escape(str(alias)), text, flags=re.IGNORECASE)
        if not match:
            continue
        suffix = text[match.end() :]
        suffix_tokens = _numeric_tokens(suffix)
        if condition_tokens and all(token in suffix_tokens for token in condition_tokens):
            return True
        # Non-numeric compact labels such as ``AF-RT`` use the same suffix
        # coordinate.  Require every meaningful condition token after the
        # alias; this does not turn a value cell elsewhere in the row into an
        # owner/condition match.
        condition_words = [
            token
            for token in condition_folded.split()
            if len(token) > 1 and token not in {"the", "and", "with", "at"}
        ]
        suffix_words = set(_scientific_fold(suffix).split())
        if condition_words and all(token in suffix_words for token in condition_words):
            return True
    return False


def _table_condition_coordinate(
    headers: Sequence[str],
    rows: Sequence[Sequence[str]],
    value: Any,
    condition: Any,
) -> tuple[bool | None, dict[str, Any]]:
    """Check a scalar value against condition-labelled table columns.

    A candidate may cite only the numeric row while its ``test_condition_raw``
    came from the same table header.  This helper proves that coordinate from
    the complete source table.  It never infers a condition when the candidate
    has none and never accepts a value copied into a different condition
    column.
    """

    condition_text = str(condition or "").strip()
    if not condition_text or _scientific_fold(condition_text) in _UNREPORTED:
        return None, {}

    condition_columns = [
        column_index
        for column_index, header in enumerate(headers)
        if _table_condition_matches_row((header,), condition_text)
    ]
    # HTML/OCR tables frequently render a two-level header as an owner row
    # followed by a condition row (for example ``H230AM`` over ``HT / 200 h /
    # 500 h``).  The first parsed row is still the owner header, so looking at
    # it alone makes every repeated value appear ambiguous.  Treat the first
    # data row as a condition header only when its leading cell is blank or an
    # explicit condition/state label; this cannot promote a normal numeric
    # result row as a coordinate.  The candidate condition must match a
    # literal cell, so no state is inferred from column order.
    condition_header_row_index: int | None = None
    if not condition_columns and rows:
        first_row = rows[0]
        first_cell = _scientific_fold(first_row[0]) if first_row else ""
        header_like_first_cell = (
            not first_cell
            or first_cell in {"condition", "conditions", "state", "states"}
        )
        if header_like_first_cell:
            condition_columns = [
                column_index
                for column_index, cell in enumerate(first_row)
                if _table_condition_matches_row((cell,), condition_text)
            ]
            if condition_columns:
                condition_header_row_index = 0
    if not condition_columns:
        return None, {"reason": "condition_header_not_found"}

    all_condition_columns: list[int] = []
    for column_index, header in enumerate(headers):
        header_text = str(header or "").strip()
        if not header_text:
            continue
        if _CONDITION_DISCRIMINATOR_CUE.search(header_text):
            all_condition_columns.append(column_index)
    # A renderer can expand one ``colspan`` header into repeated cells.  Keep
    # the repeated target columns, but count value coordinates rather than
    # header labels so a single literal value is still a unique binding.
    if not all_condition_columns:
        all_condition_columns = list(condition_columns)
    # Preserve all literal condition cells in a two-level header, not just the
    # one requested by the candidate.  This lets the uniqueness check disprove
    # a value copied into another condition column while still accepting a
    # value that occurs once in the requested column.
    if condition_header_row_index == 0:
        first_row = rows[0]
        # Once one literal cell selected this row as the second header, every
        # non-empty cell in it is a condition coordinate.  In particular,
        # ``HT`` has no unit/cue of its own but is still a valid state label.
        row_condition_columns = [
            column_index
            for column_index, cell in enumerate(first_row)
            if column_index > 0 and str(cell or "").strip()
        ]
        all_condition_columns = sorted(
            set(all_condition_columns).union(row_condition_columns)
        )

    # A detected second header row must not be searched as if it were a
    # quantitative result row (``200`` in ``200 h`` would otherwise look like
    # the reported value).  Keep original source row numbers in the audit
    # payload while evaluating only rows below that header.
    value_rows = rows[1:] if condition_header_row_index == 0 else rows
    value_row_offset = 1 if condition_header_row_index == 0 else 0

    target_hits = [
        (row_index, column_index)
        for row_index, row in enumerate(value_rows)
        for column_index in condition_columns
        if column_index < len(row)
        and _table_value_cell_matches(row[column_index], value)
    ]
    all_hits = [
        (row_index, column_index)
        for row_index, row in enumerate(value_rows)
        for column_index in all_condition_columns
        if column_index < len(row)
        and _table_value_cell_matches(row[column_index], value)
    ]
    details: dict[str, Any] = {
        "candidate_condition": condition_text,
        "condition_columns": list(condition_columns),
        "all_condition_columns": list(all_condition_columns),
        "condition_value_hits": [
            {"row": row_index + value_row_offset, "column": column_index}
            for row_index, column_index in target_hits
        ],
        "all_condition_value_hits": [
            {"row": row_index + value_row_offset, "column": column_index}
            for row_index, column_index in all_hits
        ],
    }
    if len(target_hits) == 1 and len(all_hits) == 1:
        return True, {**details, "reason": "unique_condition_value_coordinate"}
    if target_hits or all_hits:
        if not target_hits and len(all_hits) == 1:
            reason = "value_bound_to_other_condition_column"
        elif len(target_hits) > 1 or len(all_hits) > 1:
            reason = "repeated_or_ambiguous_condition_value"
        else:
            reason = "condition_value_coordinate_ambiguous"
        return False, {**details, "reason": reason}
    return None, {**details, "reason": "value_not_located_in_condition_columns"}


def _table_row_projection_matches(candidate: str, source_row: str) -> bool:
    """Return whether a compact row preserves ordered literal source cells.

    HTML table evidence is often rendered with only the selected value column,
    while OCR keeps the other columns on the same source row.  For the
    precision-only ambiguity gate it is sufficient to recognize that the
    compact row came from this table; no value is accepted from this helper.
    Requiring the first label cell and every remaining cell in order avoids
    treating an unrelated prose line as a table coordinate.
    """

    candidate_cells = tuple(
        normalize_evidence_text(cell) for cell in _table_cells(candidate)
    )
    source_cells = tuple(
        normalize_evidence_text(cell) for cell in _table_cells(source_row)
    )
    if len(candidate_cells) < 2 or len(source_cells) < len(candidate_cells):
        return False
    first = candidate_cells[0]
    try:
        start = source_cells.index(first)
    except ValueError:
        return False
    cursor = start + 1
    for cell in candidate_cells[1:]:
        try:
            cursor = source_cells.index(cell, cursor) + 1
        except ValueError:
            return False
    return True


def _table_record_rows_grounded(
    evidence: Sequence[str], lines: Sequence[str], normalized_table: str
) -> bool:
    """Match literal table rows, including compact selected-column renders."""

    if all(row in normalized_table for row in evidence):
        return True
    source_rows = tuple(lines)
    candidate_rows: list[str] = []
    for value in evidence:
        candidate_rows.extend(
            line.strip()
            for line in str(value or "").splitlines()
            if _table_cells(line)
        )
    if not candidate_rows:
        return False
    matched = [
        any(_table_row_projection_matches(row, source) for source in source_rows)
        for row in candidate_rows
    ]
    if all(matched):
        return True
    # Some chunk-local responses retain only the table header (for example
    # ``| Alloy | Ni | Ti | ... |``) while the structured candidate carries
    # one value parsed from the same source table.  The header itself is a
    # deterministic table locator, but it must not be treated as a value row.
    # Accept this narrow shape only when every cited row is a header-like row
    # that matches the source table literally; the downstream owner/value gate
    # still requires a unique cell coordinate before accepting or quarantining
    # a fact.
    header_first_cells = {
        "alloy",
        "alloys",
        "component",
        "components",
        "element",
        "elements",
        "feature",
        "features",
        "material",
        "materials",
        "parameter",
        "parameters",
        "phase",
        "phases",
        "property",
        "properties",
        "regions",
        "sample",
        "samples",
    }
    if all(
        not is_match
        and len(_table_cells(row)) >= 2
        and _scientific_fold(_table_cells(row)[0]) in header_first_cells
        and any(
            _table_row_projection_matches(row, source)
            for source in source_rows
        )
        for row, is_match in zip(candidate_rows, matched)
    ):
        return True
    # Multi-row HTML headers commonly combine a spanning owner row with a
    # second condition row.  A compact extractor quote may retain the joined
    # display label (``T5 / 1030 C/2h``), which is not present in either raw
    # header row separately.  Ignore only that single header-like row; every
    # quantitative/value row must still map to a literal source row.
    remaining = [
        row
        for row, is_match in zip(candidate_rows, matched)
        if not (
            not is_match
            and len(_table_cells(row)) <= 2
            and normalize_evidence_text(_table_cells(row)[0])
            in {"parameter", "property", "properties", "sample", "alloy"}
        )
    ]
    return bool(remaining) and all(
        any(_table_row_projection_matches(row, source) for source in source_rows)
        for row in remaining
    )


def _table_block_for_record(
    record: PromotionRecord, source_text: str
) -> tuple[tuple[str, ...], ...]:
    evidence = [normalize_evidence_text(row) for row in record.evidence if str(row).strip()]
    if not evidence:
        return ()
    matches: list[tuple[str, ...]] = []
    for _, _, lines in _raw_markdown_table_blocks(source_text):
        normalized = normalize_evidence_text("\n".join(lines))
        if normalized and _table_record_rows_grounded(evidence, lines, normalized):
            matches.append(lines)
    # A candidate may quote the complete HTML table instead of the compact
    # pipe rows emitted by the extractor.  Convert HTML evidence through the
    # same literal-cell parser before matching it to the source table.  This
    # keeps row/column coordinates intact while avoiding any fuzzy substring
    # match over tag-bearing markup.
    html_evidence_layouts: list[tuple[str, ...]] = []
    for row in record.evidence:
        if "<table" not in str(row or "").casefold():
            continue
        for evidence_lines, _ in _raw_html_table_blocks(str(row)):
            html_evidence_layouts.append(evidence_lines)
    for lines, normalized_html in _raw_html_table_blocks(source_text):
        same_html_layout = any(
            tuple(_scientific_fold(value) for value in evidence_lines)
            == tuple(_scientific_fold(value) for value in lines)
            for evidence_lines in html_evidence_layouts
        )
        if same_html_layout or _table_record_rows_grounded(
            evidence, lines, normalized_html
        ):
            matches.append(lines)
            continue
        for variant in _html_table_coordinate_variants(lines):
            normalized_variant = normalize_evidence_text("\n".join(variant))
            if normalized_variant and _table_record_rows_grounded(
                evidence, variant, normalized_variant
            ):
                matches.append(variant)
                break
    # OCR pipelines may preserve the same physical table once as Markdown and
    # once as HTML.  Treat byte-equivalent row layouts as one coordinate block;
    # a repeated value in different rows/columns remains ambiguous inside the
    # deduplicated block and is still rejected by the coordinate gate.
    unique: list[tuple[str, ...]] = []
    seen: set[tuple[str, ...]] = set()
    for lines in matches:
        key = tuple(_scientific_fold(row) for row in lines)
        if key in seen:
            continue
        seen.add(key)
        unique.append(lines)
    return tuple(unique)


def _table_condition_is_source_bound(
    fact: AxisFact,
    source_text: str,
) -> bool:
    """Keep a table condition long enough for the coordinate gate to use it.

    ``_strip_unbound_conditions`` intentionally removes labels absent from a
    candidate's copied evidence.  A compact table header is a safe exception:
    when the full source table contains one condition column and the cited
    value occurs exactly once in that column, the header is the source
    coordinate rather than cross-chunk context.  This helper is deliberately
    narrower than the later owner routing and has no effect on non-tensile
    Properties.
    """

    if not isinstance(fact, PropertyFact) or not is_core_tensile_property_name(
        fact.data.get("property_name_raw")
    ):
        return False
    condition = str(fact.data.get("test_condition_raw") or "").strip()
    if not condition or _scientific_fold(condition) in _UNREPORTED:
        return False
    if not str(source_text or "").strip():
        return False
    record = build_promotion_records([fact])[0]
    table_matches = _table_block_for_record(record, source_text)
    if len(table_matches) != 1:
        return False
    lines = table_matches[0]
    parsed = [
        _table_cells(line)
        for line in lines
        if _table_cells(line) and not _is_table_separator(_table_cells(line))
    ]
    if len(parsed) < 2:
        return False
    decision, _ = _table_condition_coordinate(
        parsed[0], parsed[1:], fact.data.get("value_raw"), condition
    )
    # Preserve both a proven match and a proven mismatch.  The latter must
    # reach the tensile table gate so it can emit the precise
    # ``value_bound_to_other_condition_column`` audit instead of degrading into
    # a generic unbound-condition/owner-ambiguity issue.
    return decision is not None


def _table_binding_payload(
    fact: AxisFact,
) -> tuple[Any, Any] | None:
    """Return one table-coordinate value and optional row condition.

    The table gate must never broadcast a multi-atom candidate.  Properties
    already have one scalar value; a Structure candidate is eligible only
    when it contains exactly one quantitative feature (top-level or nested).
    Composition is intentionally not handled here because its independently
    audited path preserves component/column semantics upstream.
    """

    if isinstance(fact, PropertyFact):
        condition = fact.data.get("test_condition_raw")
        # In table-derived tensile candidates the extractor may place a
        # compact column label (``HT``, ``200 h``) in ``test_specimen_raw``
        # while leaving ``test_condition_raw`` empty.  It is safe to use this
        # field only as an internal table coordinate: the caller still has to
        # prove a unique literal header/value cell before the fact is accepted.
        # Prose candidates and non-tensile properties keep their original
        # condition semantics and are never affected by this fallback.
        if (
            is_core_tensile_property_name(fact.data.get("property_name_raw"))
            and _EXPLICIT_TABLE_TENSILE_PROPERTY_NAME.search(
                str(fact.data.get("property_name_raw") or "")
            )
            and _scientific_fold(condition) in _UNREPORTED
            and _scientific_fold(fact.data.get("data_source")) == "table"
        ):
            specimen = fact.data.get("test_specimen_raw")
            if _scientific_fold(specimen) not in _UNREPORTED:
                condition = specimen
        return fact.data.get("value_raw"), condition
    if not isinstance(fact, StructureFact):
        return None
    features: list[dict[str, Any]] = []
    for row in fact.data.get("features") or []:
        if isinstance(row, dict):
            features.append(row)
    for entity in fact.data.get("entities") or []:
        if not isinstance(entity, dict):
            continue
        for row in entity.get("features") or []:
            if isinstance(row, dict):
                features.append(row)
    quantitative = [
        row for row in features if _is_quantitative_structure_feature(row)
    ]
    if len(quantitative) != 1:
        return None
    condition = next(
        (
            fact.data.get(key)
            for key in ("test_condition_raw", "material_state", "region", "location", "orientation")
            if str(fact.data.get(key) or "").strip()
            and _scientific_fold(fact.data.get(key)) not in _UNREPORTED
        ),
        "",
    )
    return quantitative[0].get("value_raw"), condition


_STRUCTURE_TABLE_LABEL_STOPWORDS = frozenset(
    {
        "a",
        "an",
        "and",
        "average",
        "avg",
        "feature",
        "for",
        "mean",
        "of",
        "the",
        "value",
    }
)


def _structure_table_label_tokens(value: Any) -> tuple[str, ...]:
    """Normalize a Structure feature label for literal table-row matching.

    This is intentionally a small semantic normalizer, not a fuzzy matcher.
    The table gate must distinguish ``area fraction`` from ``grain size`` and
    must retain phase qualifiers such as ``O`` or ``beta``.  Only presentation
    words and the common ``diameter``/``size`` spelling variant are folded.
    """

    text = _scientific_fold(value)
    if not text or text in _UNREPORTED:
        return ()
    text = re.sub(
        r"\b(?:μm|µm|um|nm|mm|cm|%|wt|at|vol|mol|mpa|gpa|hv)\b",
        " ",
        text,
    )
    text = text.replace("diameter", "size")
    tokens = [
        token
        for token in re.findall(r"[a-z0-9μ]+", text)
        if token not in _STRUCTURE_TABLE_LABEL_STOPWORDS
    ]
    return tuple(tokens)


def _structure_table_feature_rows(
    fact: StructureFact,
    parsed_rows: Sequence[Sequence[str]],
    value: Any,
) -> tuple[bool | None, dict[str, Any]]:
    """Require one Structure feature to match the row that contains its value.

    Owner/column matching alone is insufficient for a table with repeated
    numeric values: ``42.3`` may be an area fraction in one row and a grain
    diameter in another.  This helper proves the feature-label/value-row
    coordinate for a single quantitative Structure feature.  ``None`` means
    the table has no literal value hit and therefore cannot make a safe
    decision; ``False`` is a source-proven semantic mismatch.
    """

    if fact.fact_type != "structure_observation":
        return None, {}
    features: list[tuple[dict[str, Any], str]] = []
    for entity in fact.data.get("entities") or []:
        if not isinstance(entity, dict):
            continue
        entity_name = str(
            entity.get("name_raw") or entity.get("raw_expression") or ""
        ).strip()
        for feature in entity.get("features") or []:
            if isinstance(feature, dict) and _is_quantitative_structure_feature(feature):
                features.append((feature, entity_name))
    for feature in fact.data.get("features") or []:
        if isinstance(feature, dict) and _is_quantitative_structure_feature(feature):
            features.append((feature, ""))
    if len(features) != 1:
        return None, {"reason": "multi_atom_or_missing_structure_feature"}

    feature, entity_name = features[0]
    name = str(feature.get("feature_name_raw") or feature.get("canonical_name") or "").strip()
    feature_tokens = _structure_table_label_tokens(
        " ".join(part for part in (name, entity_name) if part)
    )
    if not feature_tokens:
        return None, {"reason": "feature_label_unreported"}
    value_hits: list[int] = []
    label_hits: list[int] = []
    bound_hits: list[int] = []
    header_tokens = _structure_table_label_tokens(
        " ".join(str(cell or "") for cell in parsed_rows[0])
    )
    for row_index, row in enumerate(parsed_rows[1:], start=1):
        cells = [str(cell or "") for cell in row]
        if any(_table_value_cell_matches(cell, value) for cell in cells):
            value_hits.append(row_index)
        row_tokens = _structure_table_label_tokens(" ".join(cells))
        row_tokens = tuple(dict.fromkeys((*header_tokens, *row_tokens)))
        if row_tokens and set(feature_tokens).issubset(set(row_tokens)):
            label_hits.append(row_index)
    bound_hits = sorted(set(value_hits).intersection(label_hits))
    details = {
        "feature_name": name,
        "entity_name": entity_name,
        "feature_tokens": list(feature_tokens),
        "value": value,
        "value_rows": value_hits,
        "label_rows": label_hits,
        "bound_rows": bound_hits,
    }
    if not value_hits:
        return None, details
    if bound_hits:
        return True, details
    return False, {
        **details,
        "reason": (
            "structure_feature_value_row_label_mismatch"
            if not bound_hits
            else "structure_feature_value_row_label_ambiguous"
        ),
    }


def _composition_component_header_key(value: Any) -> str:
    """Normalize a table component header without collapsing distinct elements."""

    text = _scientific_fold(value)
    # Headers frequently carry the basis (``Al (wt.%)``) or a display label
    # (``Element: Al``).  Keep the actual component token while dropping only
    # those presentation wrappers.
    text = re.sub(
        r"\b(?:element|component|composition|content|wt|at|vol|mol|percent|percentage)\b",
        " ",
        text,
    )
    text = re.sub(r"(?:%|\b(?:wt|at|vol|mol)\s*%\b)", " ", text)
    return re.sub(r"[^a-z0-9μ]+", "", text)


def _composition_name_matches_header(name: Any, header: Any) -> bool:
    left = _composition_component_header_key(name)
    right = _composition_component_header_key(header)
    if not left or not right:
        return False
    # Chemical/component headers are expected to be atomic labels after the
    # wrapper removal above.  Substring matching would make ``Al`` match the
    # ordinary header ``Alloy`` and silently shift a value into the wrong cell.
    return left == right


def _composition_table_owner_nodes(
    fact: CompositionFact,
    record: PromotionRecord,
    graph: OwnerGraph,
) -> tuple[OwnerNode, ...]:
    """Resolve candidate owner aliases conservatively for a composition table."""

    candidates = _candidate_nodes(record, graph)
    if not candidates:
        return ()
    exact = [
        node
        for node in candidates
        if _identity_text(node.sample_id_raw)
        == _identity_text(fact.sample_id_raw)
    ]
    if exact:
        return tuple(exact)
    state = _record_state(record)
    if state:
        state_matches = [
            node
            for node in candidates
            if node.state_raw
            and _identity_text(node.state_raw) == _identity_text(state)
        ]
        if state_matches:
            return tuple(state_matches)
    # A base alias shared by several state children is not a unique table
    # coordinate.  Do not silently select one by confidence or inventory order.
    return tuple(candidates)


def _composition_table_binding_decision(
    fact: CompositionFact,
    record: PromotionRecord,
    graph: OwnerGraph,
    source_text: str,
) -> tuple[bool | None, dict[str, Any]]:
    """Validate Composition components against one explicit table coordinate.

    The extractor may copy a complete chemistry table into several material
    candidates.  This gate acts only when the cited evidence maps every emitted
    component to one literal row/column cell.  If the table lacks a reliable
    coordinate, it returns ``None`` and leaves the candidate for existing audit
    paths; it never invents an owner.
    """

    if fact.fact_type == "material_identity":
        return None, {"reason": "material_identity"}
    components = [
        row
        for row in (fact.data.get("components") or [])
        if isinstance(row, dict)
    ]
    if not components:
        return None, {"reason": "no_components"}
    matches = _table_block_for_record(record, source_text)
    if len(matches) != 1:
        return None, {"table_block_count": len(matches)}
    lines = matches[0]
    parsed = [(_table_cells(line), line) for line in lines]
    parsed = [
        (cells, line)
        for cells, line in parsed
        if cells and not _is_table_separator(cells)
    ]
    if len(parsed) < 2:
        return None, {"table_rows": list(lines), "reason": "insufficient_rows"}
    headers = parsed[0][0]
    rows = [cells for cells, _ in parsed[1:]]
    owner_nodes = _composition_table_owner_nodes(fact, record, graph)
    if not owner_nodes:
        return None, {"table_rows": list(lines), "reason": "owner_not_in_inventory"}

    details: dict[str, Any] = {
        "table_rows": list(lines),
        "candidate_owner": fact.sample_id_raw,
        "candidate_components": deepcopy(components),
        "candidate_owner_nodes": [node.sample_id_raw for node in owner_nodes],
    }

    # Row-oriented chemistry table: the first column identifies a material and
    # component names occupy the remaining headers.
    row_hits = [
        (row_index, node)
        for row_index, row in enumerate(rows)
        for node in owner_nodes
        if row
        and any(
            _table_owner_cell_matches(row[0], node)
            for _ in (0,)
        )
    ]
    if row_hits:
        unique_rows = sorted({row_index for row_index, _ in row_hits})
        if len(unique_rows) != 1:
            details["owner_row_hits"] = [
                {"row": index, "owner": node.sample_id_raw}
                for index, node in row_hits
            ]
            return False, {**details, "reason": "owner_row_ambiguous"}
        row_index = unique_rows[0]
        row = rows[row_index]
        component_hits: list[dict[str, Any]] = []
        for component in components:
            name = component.get("name_raw") or component.get("canonical_name")
            value = component.get("value_raw")
            header_hits = [
                index
                for index, header in enumerate(headers)
                if _composition_name_matches_header(name, header)
            ]
            if len(header_hits) != 1:
                # A row table with no component header cannot prove which cell
                # owns a value.  Leave it to the existing recall-oriented path.
                return None, {
                    **details,
                    "reason": "component_header_unresolved",
                    "component": deepcopy(component),
                }
            column = header_hits[0]
            if column >= len(row) or not _table_value_cell_matches(row[column], value):
                component_hits.append(
                    {"name": name, "value": value, "row": row_index, "column": column}
                )
                return False, {
                    **details,
                    "reason": "component_value_bound_to_other_owner_row",
                    "component_value_hits": component_hits,
                }
            component_hits.append(
                {"name": name, "value": value, "row": row_index, "column": column}
            )
        return True, {**details, "owner_row": row_index, "component_hits": component_hits}

    # Column-oriented chemistry table: owner labels occupy the header row and
    # component names occupy the first cell of each data row.
    owner_columns = {
        column: node
        for column, header in enumerate(headers)
        for node in owner_nodes
        if _table_owner_cell_matches(header, node)
    }
    if not owner_columns:
        return None, {**details, "reason": "no_owner_row_or_column_coordinate"}
    if len({node.owner_id for node in owner_columns.values()}) != 1:
        return False, {**details, "reason": "owner_column_ambiguous"}
    component_hits = []
    for component in components:
        name = component.get("name_raw") or component.get("canonical_name")
        value = component.get("value_raw")
        row_hits_for_component = [
            (row_index, row)
            for row_index, row in enumerate(rows)
            if row and _composition_name_matches_header(name, row[0])
        ]
        if len(row_hits_for_component) != 1:
            return None, {
                **details,
                "reason": "component_row_unresolved",
                "component": deepcopy(component),
            }
        row_index, row = row_hits_for_component[0]
        column = next(iter(owner_columns))
        if column >= len(row) or not _table_value_cell_matches(row[column], value):
            component_hits.append(
                {"name": name, "value": value, "row": row_index, "column": column}
            )
            return False, {
                **details,
                "reason": "component_value_bound_to_other_owner_column",
                "component_value_hits": component_hits,
            }
        component_hits.append(
            {"name": name, "value": value, "row": row_index, "column": column}
        )
    return True, {**details, "owner_columns": owner_columns, "component_hits": component_hits}


def _gate_composition_table_bindings(
    anchors: Sequence[InventoryAnchor],
    facts: Sequence[AxisFact],
    source_text: str,
) -> tuple[list[AxisFact], list[PromotionIssue]]:
    """Quarantine Composition facts disproved by explicit table coordinates."""

    graph = build_owner_graph(anchors)
    if not graph.nodes:
        return list(facts), []
    accepted: list[AxisFact] = []
    issues: list[PromotionIssue] = []
    for fact in facts:
        if not isinstance(fact, CompositionFact):
            accepted.append(fact)
            continue
        record = build_promotion_records([fact])[0]
        decision, details = _composition_table_binding_decision(
            fact, record, graph, source_text
        )
        if decision is not False:
            accepted.append(fact)
            continue
        issues.append(
            _promotion_issue(
                fact,
                code="promotion_composition_table_owner_value_ambiguous_quarantined",
                message=(
                    "A Composition table candidate was not bound to one unique "
                    "owner row/column and was isolated instead of being broadcast."
                ),
                expected={
                    "unique_owner_value_coordinate": True,
                    "broadcast": False,
                    "audit_preserved": True,
                },
                actual={"removed": fact.model_dump(), **details},
            )
        )
    return accepted, issues


def _table_binding_decision(
    fact: AxisFact,
    record: PromotionRecord,
    graph: OwnerGraph,
    source_text: str,
) -> tuple[bool | None, dict[str, Any]]:
    """Decide only source-coordinate ambiguity; ``None`` means no-op.

    ``True`` is a proven one-to-one row/column binding, ``False`` is an
    ambiguity that must be isolated, and ``None`` means the table does not
    contain enough literal coordinates for this gate to decide safely.
    """

    payload = _table_binding_payload(fact)
    if payload is None:
        return None, {"reason": "multi_atom_or_unsupported_table_fact"}
    value, condition = payload
    source_coordinate_v202 = os.getenv(
        "KNOWMAT2_ALPHA25_SOURCE_COORDINATE_PRECISION_V202", "1"
    ).strip().casefold() not in {"0", "false", "no", "off", "disabled"}
    if source_coordinate_v202 and isinstance(fact, PropertyFact):
        # HTML span expansion in the legacy promotion parser intentionally
        # discards physical cell origins.  That makes one rowspan value look
        # like several competing values even after the evidence gate has proven
        # a unique owner/property/unit/citation cell.  Reuse the origin-aware
        # v202 resolver before the presentation-only fallback; it remains
        # fail-closed for wrong citations, wrong owners, and repeated tables.
        from knowmat.alpha25.source_coordinates import (
            resolve_structured_table_record,
        )

        coordinate = resolve_structured_table_record(fact, source_text)
        if coordinate.status == "matched":
            return True, {
                "reason": "v202_unique_structured_source_coordinate",
                "candidate_owner": fact.sample_id_raw,
                "candidate_value": value,
                "candidate_condition": condition,
                "structured_coordinate": coordinate.to_dict(),
            }
        if coordinate.status == "ambiguous":
            return False, {
                "reason": "v202_structured_source_coordinate_ambiguous",
                "candidate_owner": fact.sample_id_raw,
                "candidate_value": value,
                "candidate_condition": condition,
                "structured_coordinate": coordinate.to_dict(),
            }
    table_matches = _table_block_for_record(record, source_text)
    if len(table_matches) != 1:
        return None, {"table_block_count": len(table_matches)}
    lines = table_matches[0]
    parsed = [(_table_cells(line), line) for line in lines]
    parsed = [(cells, line) for cells, line in parsed if cells and not _is_table_separator(cells)]
    if len(parsed) < 2:
        return None, {"table_rows": list(lines), "reason": "insufficient_rows"}
    headers = parsed[0][0]
    rows = [cells for cells, _ in parsed[1:]]
    structure_coordinate, structure_details = (None, {})
    if isinstance(fact, StructureFact):
        structure_coordinate, structure_details = _structure_table_feature_rows(
            fact, [cells for cells, _ in parsed], value
        )
        if structure_coordinate is False:
            return False, {
                "table_rows": list(lines),
                "candidate_owner": fact.sample_id_raw,
                "candidate_value": value,
                "structure_feature_coordinate": structure_details,
                "reason": structure_details.get(
                    "reason", "structure_feature_value_row_label_mismatch"
                ),
            }
    condition_decision, condition_details = _table_condition_coordinate(
        headers, rows, value, condition
    )
    # Include existing state children so a base-owner projection can be
    # disproved by the row/column coordinate that belongs to a sibling state.
    base_candidate_nodes = _candidate_nodes(record, graph)
    candidate_nodes = _table_candidate_nodes(record, graph)
    if not candidate_nodes:
        return None, {"table_rows": list(lines), "reason": "owner_not_in_inventory"}
    base_candidate_ids = {node.owner_id for node in base_candidate_nodes}
    owner_has_explicit_state = bool(_record_state(record)) or bool(
        _BRACKETED_OWNER_STATE.match(record.explicit_owner)
    )

    owner_row_hits: list[tuple[int, int, OwnerNode]] = []
    for row_index, row in enumerate(rows):
        for column_index, cell in enumerate(row):
            for node in candidate_nodes:
                if _table_owner_cell_matches(cell, node):
                    owner_row_hits.append((row_index, column_index, node))
    all_owner_row_hits: list[tuple[int, int, OwnerNode]] = []
    for row_index, row in enumerate(rows):
        for column_index, cell in enumerate(row):
            for node in graph.nodes:
                if _table_owner_cell_matches(cell, node):
                    all_owner_row_hits.append((row_index, column_index, node))
    owner_row_keys = {(row_index, node.owner_id) for row_index, _, node in owner_row_hits}
    details: dict[str, Any] = {
        "table_rows": list(lines),
        "candidate_owner": fact.sample_id_raw,
        "candidate_value": value,
        "candidate_condition": condition,
        "condition_binding": condition_details,
        "structure_feature_coordinate": structure_details,
        "owner_row_hits": [
            {"row": row_index, "column": column_index, "owner": node.sample_id_raw}
            for row_index, column_index, node in owner_row_hits
        ],
    }

    # A source table can disprove a condition/value projection even when the
    # owner is expressed only by the candidate item and the conditions are
    # expressed as columns.  Resolve this before owner-row/owner-column logic
    # so a unique value in the wrong condition column cannot be accepted.
    if condition_decision is False:
        return False, {**details, "reason": condition_details.get("reason")}

    if owner_row_keys:
        candidate_rows = sorted({row_index for row_index, _ in owner_row_keys})
        conditioned_rows = [
            row_index
            for row_index in candidate_rows
            if _table_condition_matches_row(rows[row_index], condition)
        ]
        # Some OCR renderers encode the condition in the owner cell (for
        # example ``AF-250``) rather than in a dedicated column.  Prefer that
        # owner-local coordinate whenever it uniquely selects one of the
        # candidate's base-owner rows; the broad row-text matcher can also
        # hit a numerically identical sibling row (for example HT-250).
        owner_conditioned_rows = sorted(
            {
                row_index
                for row_index, column_index, node in owner_row_hits
                if row_index in candidate_rows
                and node.owner_id in base_candidate_ids
                and column_index < len(rows[row_index])
                and _table_condition_matches_owner_cell(
                    rows[row_index][column_index], condition, node
                )
            }
        )
        if len(owner_conditioned_rows) == 1:
            conditioned_rows = owner_conditioned_rows
        if len(conditioned_rows) == 1:
            candidate_rows = conditioned_rows
        if len(candidate_rows) != 1:
            # A base owner such as ``AF`` legitimately has several source
            # rows (AF-RT, AF-200 °C, ...).  When the candidate condition is
            # absent, a value occurring in exactly one of those rows is still
            # a unique source coordinate and must be retained.  Only repeated
            # values remain ambiguous; this is the key distinction between a
            # safe row lookup and owner-wide broadcasting.
            row_value_hits = [
                (row_index, column_index)
                for row_index in candidate_rows
                for column_index, cell in enumerate(rows[row_index])
                if _table_value_cell_matches(cell, value)
                and (
                    condition_decision is not True
                    or column_index
                    in condition_details.get("condition_columns", [])
                )
            ]
            details["candidate_rows"] = candidate_rows
            details["value_hits"] = [
                {"row": row_index, "column": column_index}
                for row_index, column_index in row_value_hits
            ]
            if len({row_index for row_index, _ in row_value_hits}) == 1 and len(row_value_hits) == 1:
                hit_row = row_value_hits[0][0]
                sibling_hits = {
                    node.owner_id
                    for row_index, _, node in all_owner_row_hits
                    if row_index == hit_row
                    and node.owner_id not in base_candidate_ids
                    and node.state_raw
                }
                if sibling_hits and not owner_has_explicit_state:
                    details["state_sibling_value_hits"] = [
                        {
                            "row": hit_row,
                            "owner": graph.node(owner_id).sample_id_raw,
                        }
                        for owner_id in sorted(sibling_hits)
                    ]
                    return False, {
                        **details,
                        "reason": "value_bound_to_existing_state_sibling",
                    }
                return True, {**details, "reason": "unique_value_row_under_shared_base_owner"}
            if not row_value_hits:
                return None, {**details, "reason": "value_not_located_in_candidate_rows"}
            details["candidate_rows"] = candidate_rows
            details["reason"] = "owner_row_or_condition_ambiguous"
            return False, details
        row_index = candidate_rows[0]
        value_hits = [
            column_index
            for column_index, cell in enumerate(rows[row_index])
            if _table_value_cell_matches(cell, value)
            and (
                condition_decision is not True
                or column_index in condition_details.get("condition_columns", [])
            )
        ]
        details["value_hits"] = [{"row": row_index, "column": index} for index in value_hits]
        if len(value_hits) == 1:
            sibling_hits = {
                node.owner_id
                for other_row_index, other_column_index, node in all_owner_row_hits
                if other_row_index == row_index
                and node.owner_id not in base_candidate_ids
                and node.state_raw
                and other_column_index == value_hits[0]
            }
            if sibling_hits and not owner_has_explicit_state:
                details["state_sibling_value_hits"] = [
                    {
                        "row": row_index,
                        "column": value_hits[0],
                        "owner": graph.node(owner_id).sample_id_raw,
                    }
                    for owner_id in sorted(sibling_hits)
                ]
                return False, {
                    **details,
                    "reason": "value_bound_to_existing_state_sibling",
                }
            return True, details
        if len(value_hits) > 1:
            details["reason"] = "repeated_value_in_owner_row"
            return False, details
        candidate_owner_ids = {node.owner_id for node in candidate_nodes}
        other_owner_rows = sorted(
            {
                other_row_index
                for other_row_index, _, node in all_owner_row_hits
                if node.owner_id not in candidate_owner_ids
            }
        )
        other_row_hits = [
            (other_row_index, column_index)
            for other_row_index in other_owner_rows
            if other_row_index != row_index
            for column_index, cell in enumerate(rows[other_row_index])
            if _table_value_cell_matches(cell, value)
        ]
        if len(other_row_hits) == 1:
            details["other_owner_value_hits"] = [
                {"row": other_row_index, "column": column_index}
                for other_row_index, column_index in other_row_hits
            ]
            details["reason"] = "value_bound_to_other_owner_row"
            return False, details
        # The model may have copied a rendered value whose cell is not literal
        # in this OCR table.  Do not turn that absence into a false rejection.
        return None, {**details, "reason": "value_not_located_in_owner_row"}

    if condition_decision is True:
        # The table exposes a unique condition/value coordinate but no owner
        # row/column label.  The owner may be represented by the candidate's
        # existing sample/state lineage; the condition coordinate is still
        # sufficient to prevent cross-column broadcasting.
        return True, details

    owner_columns: dict[int, OwnerNode] = {}
    for column_index, header in enumerate(headers):
        for node in candidate_nodes:
            if _table_owner_cell_matches(header, node):
                owner_columns[column_index] = node
    if not owner_columns:
        return None, {**details, "reason": "no_owner_coordinate"}

    value_hits = [
        (row_index, column_index)
        for row_index, row in enumerate(rows)
        for column_index, node in owner_columns.items()
        if column_index < len(row) and _table_value_cell_matches(row[column_index], value)
        and (
            condition_decision is not True
            or column_index in condition_details.get("condition_columns", [])
        )
    ]
    all_owner_value_hits = [
        (row_index, column_index)
        for row_index, row in enumerate(rows)
        for column_index, header in enumerate(headers)
        if column_index < len(row)
        and any(_table_owner_cell_matches(header, node) for node in graph.nodes)
        and _table_value_cell_matches(row[column_index], value)
        and (
            condition_decision is not True
            or column_index in condition_details.get("condition_columns", [])
        )
    ]
    details["owner_columns"] = {
        str(index): node.sample_id_raw for index, node in sorted(owner_columns.items())
    }
    details["value_hits"] = [
        {"row": row_index, "column": column_index}
        for row_index, column_index in value_hits
    ]
    details["all_owner_value_hits"] = [
        {"row": row_index, "column": column_index}
        for row_index, column_index in all_owner_value_hits
    ]
    if condition_decision is True:
        # The condition-column helper has already established one value hit in
        # the target column and one across all condition columns.  Require the
        # owner coordinate to agree when the table also exposes owner columns.
        if len(value_hits) == 1 and len(all_owner_value_hits) == 1:
            return True, details
        if value_hits or all_owner_value_hits:
            details["reason"] = "owner_condition_coordinate_ambiguous"
            return False, details
        return True, details
    if len(value_hits) == 1 and len(all_owner_value_hits) == 1:
        sibling_columns = {
            node.owner_id
            for column_index, node in owner_columns.items()
            if node.owner_id not in base_candidate_ids
            and node.state_raw
            and column_index == value_hits[0][1]
        }
        if sibling_columns and not owner_has_explicit_state:
            details["state_sibling_value_hits"] = [
                {
                    "row": value_hits[0][0],
                    "column": value_hits[0][1],
                    "owner": graph.node(owner_id).sample_id_raw,
                }
                for owner_id in sorted(sibling_columns)
            ]
            return False, {
                **details,
                "reason": "value_bound_to_existing_state_sibling",
            }
        return True, details
    if value_hits or all_owner_value_hits:
        details["reason"] = "repeated_or_multi_owner_column_value"
        return False, details
    return None, {**details, "reason": "value_not_located_in_owner_column"}


def _condition_is_external_scope(
    fact: PropertyFact,
    graph: OwnerGraph,
) -> tuple[bool, str]:
    condition = str(fact.data.get("test_condition_raw") or "").strip()
    if not condition or _scientific_fold(condition) in _UNREPORTED:
        return False, ""
    if _TENSILE_PREPARATION_CONDITION.search(condition):
        return True, "preparation_or_feedstock_condition"
    owner_nodes = _candidate_nodes(build_promotion_records([fact])[0], graph)
    current_experimental = any(
        node.role == "Target" and node.data_nature == "Experimental"
        for node in owner_nodes
    )
    if not current_experimental:
        return False, ""
    if _TENSILE_EXTERNAL_SCOPE.search(condition):
        return True, "reference_or_computational_condition"
    condition_tokens = set(_numeric_tokens(condition))
    for evidence in _fact_evidence(fact):
        for sentence in re.split(r"(?<=[.!?;])\s+|\n+", evidence):
            if not condition_tokens.intersection(_numeric_tokens(sentence)):
                continue
            if _TENSILE_EXTERNAL_SCOPE.search(sentence) and not _TENSILE_RESULT_CUE.search(sentence):
                return True, "condition_literal_in_external_assertion"
    return False, ""


def _table_condition_state_owner(
    record: PromotionRecord,
    graph: OwnerGraph,
    condition: Any,
) -> OwnerNode | None:
    """Return one existing lineage state selected by a proven table column."""

    candidates = _candidate_nodes(record, graph)
    if candidates:
        expanded = {node.owner_id: node for node in candidates}
        for node in _lineage_state_nodes(candidates, graph):
            expanded[node.owner_id] = node
        candidates = list(expanded.values())
    matches = [
        node
        for node in candidates
        if node.state_raw
        and _table_condition_matches_row((node.state_raw,), condition)
        and node.role == "Target"
        and node.data_nature == "Experimental"
    ]
    unique = {node.owner_id: node for node in matches}
    if len(unique) == 1:
        return next(iter(unique.values()))
    # A generic base-material candidate may have state children represented as
    # separate sample IDs, so they are not lineage siblings by identifier.
    # Permit a paper-level fallback only when the table condition selects one
    # current experimental state and its material designation agrees exactly
    # with the candidate's existing material owner.  This is narrower than
    # ordinary condition routing and never searches by chemistry alone.
    candidate_materials = {
        _identity_text(node.material_name_raw)
        for node in _candidate_nodes(record, graph)
        if _identity_text(node.material_name_raw)
    }
    if len(candidate_materials) == 1:
        global_matches = [
            node
            for node in graph.nodes
            if node.state_raw
            and _identity_text(node.material_name_raw) in candidate_materials
            and _table_condition_matches_row((node.state_raw,), condition)
            and node.role == "Target"
            and node.data_nature == "Experimental"
        ]
        global_unique = {node.owner_id: node for node in global_matches}
        if len(global_unique) == 1:
            return next(iter(global_unique.values()))
    return None


def _gate_tensile_source_bindings(
    anchors: Sequence[InventoryAnchor],
    facts: Sequence[AxisFact],
    source_text: str,
) -> tuple[list[AxisFact], list[PromotionIssue]]:
    """Protect tensile table coordinates and condition scope using source only."""

    graph = build_owner_graph(anchors)
    accepted: list[AxisFact] = []
    issues: list[PromotionIssue] = []
    for fact in facts:
        if not isinstance(fact, PropertyFact) or not is_core_tensile_property_name(
            fact.data.get("property_name_raw")
        ):
            accepted.append(fact)
            continue
        record = build_promotion_records([fact])[0]
        support = "\n".join(record.evidence)
        # A core tensile candidate is intentionally allowed to remain generic
        # when a paragraph omits its owner.  When the candidate's own quote
        # names exactly one current experimental owner, however, retaining a
        # different owner is a source-proven attribution error.  Route to that
        # existing owner before applying table/condition checks; never create a
        # state or choose between ties.
        named_nodes = _safe_source_owner_nodes(support, graph)
        current_named_nodes = [
            node
            for node in named_nodes
            if node.role == "Target" and node.data_nature == "Experimental"
        ]
        candidate_nodes = _candidate_nodes(record, graph)
        if len(current_named_nodes) == 1 and not any(
            node.owner_id == current_named_nodes[0].owner_id
            for node in candidate_nodes
        ):
            target = current_named_nodes[0]
            before_reassignment = fact
            reassigned = _reassign_fact_owner(fact, target.sample_id_raw)
            fact = reassigned
            record = build_promotion_records([fact])[0]
            issues.append(
                _promotion_issue(
                    before_reassignment,
                    code="promotion_tensile_source_owner_reassigned",
                    message=(
                        "The tensile assertion named one existing current-paper "
                        "owner; the candidate was routed there instead of being "
                        "left on a different material/state."
                    ),
                    expected={
                        "source_explicit_owner": target.sample_id_raw,
                        "unique_current_experimental_owner": True,
                        "owner_invented": False,
                        "audit_preserved": True,
                    },
                    actual={
                        "before": before_reassignment.model_dump(),
                        "after": reassigned.model_dump(),
                    },
                    evidence=list(record.evidence),
                )
            )
        table_decision, table_details = _table_binding_decision(
            fact, record, graph, source_text
        )
        if table_decision is True:
            condition = _table_binding_payload(fact)
            table_condition = condition[1] if condition is not None else ""
            target = _table_condition_state_owner(record, graph, table_condition)
            current_owner = _identity_text(record.explicit_owner)
            if target is not None and current_owner != _identity_text(
                target.sample_id_raw
            ):
                before_reassignment = fact
                reassigned = _reassign_fact_owner(fact, target.sample_id_raw)
                fact = reassigned
                record = build_promotion_records([fact])[0]
                issues.append(
                    _promotion_issue(
                        before_reassignment,
                        code="promotion_tensile_table_condition_owner_reassigned",
                        message=(
                            "A tensile table condition column selected one existing "
                            "state owner; the candidate was routed there without "
                            "inventing a state from the table."
                        ),
                        expected={
                            "unique_existing_table_condition_owner": target.sample_id_raw,
                            "owner_invented": False,
                            "audit_preserved": True,
                        },
                        actual={
                            "before": before_reassignment.model_dump(),
                            "after": reassigned.model_dump(),
                            "table_binding": table_details,
                        },
                        evidence=list(record.evidence),
                    )
                )
        if table_decision is False:
            issues.append(
                _promotion_issue(
                    fact,
                    code="promotion_table_owner_condition_ambiguous_quarantined",
                    message=(
                        "A tensile table value could not be bound to one unique "
                        "source row/column owner and was isolated without broadcast."
                    ),
                    expected={
                        "unique_owner_value_coordinate": True,
                        "broadcast": False,
                        "audit_preserved": True,
                    },
                    actual={"removed": fact.model_dump(), **table_details},
                )
            )
            continue

        condition_violation, reason = _condition_is_external_scope(fact, graph)
        if not condition_violation:
            accepted.append(fact)
            continue
        data = deepcopy(fact.data)
        data["test_condition_raw"] = ""
        cleaned = fact.model_copy(deep=True, update={"data": data})
        accepted.append(cleaned)
        issues.append(
            _promotion_issue(
                fact,
                code="promotion_tensile_condition_scope_quarantined",
                message=(
                    "A tensile condition was outside the current experimental "
                    "test scope (preparation/feedstock or external reference); "
                    "the grounded value and owner were preserved without the condition."
                ),
                expected={
                    "condition_scope": "current experimental tensile test or source-literal state",
                    "invented_condition": False,
                    "audit_preserved": True,
                },
                actual={
                    "before": fact.model_dump(),
                    "after": cleaned.model_dump(),
                    "reason": reason,
                    "table_binding": table_details,
                },
            )
        )
    return accepted, issues


def _route_cited_table_reference_owners(
    anchors: Sequence[InventoryAnchor],
    facts: Sequence[AxisFact],
) -> tuple[list[AxisFact], list[PromotionIssue]]:
    """Move cited comparison-table facts from a duplicate Target to Reference.

    Some extraction responses create both ``Wrought`` (Target) and
    ``Wrought [37] [reference]`` (Reference), then attach a cited table cell to
    the Target because the table header contains the shorter label.  A planner
    projection may also crop the citation columns; in that case every remaining
    cell must exactly match one full cited row in order.  All ambiguous cases
    remain on the normal quarantine path.
    """

    graph = build_owner_graph(anchors)
    if not graph.nodes:
        return list(facts), []
    accepted: list[AxisFact] = []
    issues: list[PromotionIssue] = []
    for fact in facts:
        record = build_promotion_records([fact])[0]
        target = _table_reference_owner_collision(fact, record, graph)
        if target is None:
            accepted.append(fact)
            continue
        reassigned = _reassign_fact_owner(fact, target.sample_id_raw)
        if target.state_raw:
            data = deepcopy(reassigned.data)
            state_keys = {
                key
                for key in ("material_state", "material_state_raw", "state_raw", "state")
                if key in data
            }
            if not state_keys:
                state_keys.add("material_state")
            for key in state_keys:
                data[key] = target.state_raw
            reassigned = reassigned.model_copy(deep=True, update={"data": data})
        accepted.append(reassigned)
        issues.append(
            _promotion_issue(
                fact,
                code="promotion_cited_table_reference_owner_reassigned",
                message=(
                    "A cited or uniquely source-row-matched comparison-table "
                    "value was attached to a duplicate Target label; it was "
                    "routed to the proven Reference owner."
                ),
                expected={
                    "owner_role": "Reference",
                    "unique_reference_sibling": target.sample_id_raw,
                    "citation_or_unique_source_row": True,
                    "audit_preserved": True,
                },
                actual={
                    "before": fact.model_dump(),
                    "after": reassigned.model_dump(),
                    "reference_owner": target.sample_id_raw,
                },
                evidence=_fact_evidence(fact),
            )
        )
    return accepted, issues


def _gate_noncomposition_table_bindings(
    anchors: Sequence[InventoryAnchor],
    facts: Sequence[AxisFact],
    source_text: str,
) -> tuple[list[AxisFact], list[PromotionIssue]]:
    """Reject non-Composition table projections without one cell coordinate.

    High-recall chunks commonly copy a complete table into every material
    item.  The existing tensile-only gate cannot protect density, hardness,
    or numeric Structure rows, so a table value such as ``8.401`` can be
    silently attached to ``#2``--``#5`` even though it belongs to ``#1``.
    Apply the same source-coordinate rule to non-core Properties and single
    numeric Structure observations.  A table without an owner coordinate, or
    a multi-atom candidate, is left unchanged for downstream/manual review;
    this gate only acts when the source proves a coordinate and disproves it.
    Composition remains explicitly excluded to preserve its audited recall
    path.
    """

    graph = build_owner_graph(anchors)
    if not graph.nodes:
        return list(facts), []
    accepted: list[AxisFact] = []
    issues: list[PromotionIssue] = []
    for fact in facts:
        eligible = isinstance(fact, StructureFact) or (
            isinstance(fact, PropertyFact)
            and not is_core_tensile_property_name(
                fact.data.get("property_name_raw")
            )
        )
        if not eligible:
            accepted.append(fact)
            continue
        record = build_promotion_records([fact])[0]
        decision, details = _table_binding_decision(
            fact, record, graph, source_text
        )
        if decision is not False:
            accepted.append(fact)
            continue
        issues.append(
            _promotion_issue(
                fact,
                code="promotion_table_owner_value_ambiguous_quarantined",
                message=(
                    "A non-Composition table value was not bound to one unique "
                    "source row/column owner and was isolated instead of being "
                    "broadcast across material items."
                ),
                expected={
                    "unique_owner_value_coordinate": True,
                    "broadcast": False,
                    "composition_path_unchanged": True,
                    "audit_preserved": True,
                },
                actual={"removed": fact.model_dump(), **details},
            )
        )
    return accepted, issues


def _processing_parameter_name_matches(name: Any, cell: Any) -> bool:
    """Match a process-table parameter label without fuzzy value projection.

    OCR tables frequently put the unit in the row label (``Power (W)``) while
    the model keeps it in ``unit_raw``.  Strip only presentation wrappers and
    compare the remaining scientific label.  A short substring is not enough:
    ``speed`` must not accidentally select ``scanning speed`` when both rows
    exist.
    """

    left = _scientific_fold(name)
    right = _scientific_fold(cell)
    if not left or not right:
        return False
    def normalize_label(value: str) -> str:
        value = re.sub(r"\([^)]*\)|\[[^\]]*\]", " ", value)
        value = re.sub(r"\b(?:parameter|parameters|value|setting)\b", " ", value)
        value = re.sub(r"[^a-z0-9μµ]+", " ", value)
        return " ".join(value.split())

    left = normalize_label(left)
    right = normalize_label(right)
    # ``_scientific_fold`` intentionally removes Markdown punctuation, so a
    # parenthesized unit reaches this point as a trailing token (``power w``).
    # Strip only well-known unit tokens; a descriptive suffix remains part of
    # the row label and cannot be silently discarded.
    unit_tokens = {
        "w", "kw", "mw", "v", "kv", "a", "ma", "s", "ms", "min", "h",
        "hz", "mhz", "pa", "kpa", "mpa", "gpa", "mm", "μm", "µm", "um",
        "mm/s", "m/s", "mm/min", "r/min", "j/mm3", "j/mm", "°c", "k",
        "%",
    }
    right_tokens = right.split()
    left_tokens = left.split()
    if len(right_tokens) > len(left_tokens) and right_tokens[: len(left_tokens)] == left_tokens:
        suffix = right_tokens[len(left_tokens) :]
        if suffix and all(token in unit_tokens for token in suffix):
            right = left
    if left == right:
        return True
    # Permit a conservative synonym pair used by the extraction schema.  Do
    # not generalize to arbitrary substrings, which can bind the wrong row in
    # tables containing both ``scan speed`` and ``wire feed speed``.
    aliases = {
        "hatch distance": "hatch spacing",
        "hatch spacing": "hatch distance",
        "scanning speed": "scan speed",
        "scan speed": "scanning speed",
        "feed rate": "wire feed rate",
        "wire feed rate": "feed rate",
        "interlayer delay": "interpass dwell time",
        "interpass dwell time": "interlayer delay",
    }
    return aliases.get(left) == right


def _processing_table_parameter_coordinate(
    fact: ProcessingFact,
    record: PromotionRecord,
    graph: OwnerGraph,
    source_text: str,
) -> tuple[dict[int, tuple[bool | None, dict[str, Any]]], dict[str, Any]]:
    """Resolve each process parameter to one literal table row/column.

    ``process_stage`` is multi-atom: one fact can contain all rows from a
    process table.  Reusing the scalar Property/Structure gate would either
    reject the whole stage or broadcast every value.  This helper instead
    returns one decision per parameter index, so only values proven to belong
    to a sibling owner are isolated.
    """

    # ``PromotionRecord.evidence`` contains the outer fact quote, while the
    # table extractor commonly stores the compact row coordinate only on each
    # nested parameter.  Include both layers here; otherwise a fact quoting
    # only the caption/owner would never reach the source table gate.
    table_evidence = _fact_evidence(fact)
    for parameter in fact.data.get("parameters_raw") or []:
        if isinstance(parameter, dict):
            table_evidence.extend(_feature_evidence(parameter, table_evidence))
    table_evidence = list(
        dict.fromkeys(
            row
            for row in table_evidence
            if _is_table_evidence_row(row)
        )
    )
    table_matches: list[tuple[str, ...]] = []
    if table_evidence:
        normalized_evidence = [normalize_evidence_text(row) for row in table_evidence]
        for _, _, lines in _raw_markdown_table_blocks(source_text):
            normalized = normalize_evidence_text("\n".join(lines))
            if normalized and _table_record_rows_grounded(
                normalized_evidence, lines, normalized
            ):
                table_matches.append(lines)
        html_evidence_layouts: list[tuple[str, ...]] = []
        for row in table_evidence:
            if "<table" not in str(row or "").casefold():
                continue
            for evidence_lines, _ in _raw_html_table_blocks(str(row)):
                html_evidence_layouts.append(evidence_lines)
        for lines, normalized_html in _raw_html_table_blocks(source_text):
            same_html_layout = any(
                tuple(_scientific_fold(value) for value in evidence_lines)
                == tuple(_scientific_fold(value) for value in lines)
                for evidence_lines in html_evidence_layouts
            )
            if same_html_layout or _table_record_rows_grounded(
                normalized_evidence, lines, normalized_html
            ):
                table_matches.append(lines)
                continue
            for variant in _html_table_coordinate_variants(lines):
                normalized_variant = normalize_evidence_text("\n".join(variant))
                if normalized_variant and _table_record_rows_grounded(
                    normalized_evidence, variant, normalized_variant
                ):
                    table_matches.append(variant)
                    break
    unique_matches: list[tuple[str, ...]] = []
    seen_matches: set[tuple[str, ...]] = set()
    for lines in table_matches:
        key = tuple(_scientific_fold(row) for row in lines)
        if key in seen_matches:
            continue
        seen_matches.add(key)
        unique_matches.append(lines)
    table_matches = unique_matches
    if len(table_matches) != 1:
        return {}, {"table_block_count": len(table_matches)}
    lines = table_matches[0]
    parsed = [
        _table_cells(line)
        for line in lines
        if _table_cells(line) and not _is_table_separator(_table_cells(line))
    ]
    if len(parsed) < 2:
        return {}, {"table_rows": list(lines), "reason": "insufficient_rows"}
    # Include existing state children so a base-owner projection can be
    # disproved by the row/column coordinate that belongs to a sibling state.
    candidate_nodes = _table_candidate_nodes(record, graph)
    if not candidate_nodes:
        return {}, {
            "table_rows": list(lines),
            "reason": "owner_not_in_inventory",
        }

    # The common column-oriented form has owner labels in the first row.  A
    # small number of OCR tables use two header rows; scanning the first three
    # rows is enough to find the literal owner without treating data rows as a
    # coordinate.  Duplicate aliases/columns are intentionally ambiguous.
    owner_columns: dict[int, OwnerNode] = {}
    for header in parsed[:3]:
        for column, cell in enumerate(header):
            matches = [
                node
                for node in candidate_nodes
                if _table_owner_cell_matches(cell, node)
            ]
            # Inventory extraction can legitimately emit the same sample label
            # more than once (different provenance/state metadata).  The table
            # still exposes one literal owner column in that case; collapse
            # only identical sample labels, never two distinct labels.
            matched_labels = {
                _identity_text(node.sample_id_raw) for node in matches
            }
            if len(matched_labels) == 1 and matches:
                prior = owner_columns.get(column)
                if prior is None or _identity_text(prior.sample_id_raw) == next(
                    iter(matched_labels)
                ):
                    owner_columns[column] = matches[0]
                else:
                    owner_columns.pop(column, None)
    candidate_owner_ids = {node.owner_id for node in candidate_nodes}
    owner_columns = {
        column: node
        for column, node in owner_columns.items()
        if node.owner_id in candidate_owner_ids
    }
    unique_owner_columns = (
        owner_columns
        if len({node.owner_id for node in owner_columns.values()}) == 1
        else {}
    )

    # The row-oriented form has the owner in the first cell of one data row.
    # Exclude the first parsed row, which is the header even when it happens to
    # contain a sample-like label such as ``A1``.
    owner_rows: dict[int, OwnerNode] = {}
    for row_index, row in enumerate(parsed[1:], start=1):
        if not row:
            continue
        matches = [
            node
            for node in candidate_nodes
            if _table_owner_cell_matches(row[0], node)
        ]
        matched_labels = {
            _identity_text(node.sample_id_raw) for node in matches
        }
        if len(matched_labels) == 1 and matches:
            prior = owner_rows.get(row_index)
            if prior is None or _identity_text(prior.sample_id_raw) == next(
                iter(matched_labels)
            ):
                owner_rows[row_index] = matches[0]
    target_rows = [
        row_index
        for row_index, node in owner_rows.items()
        if node.owner_id in candidate_owner_ids
    ]
    unique_target_rows = target_rows if len(target_rows) == 1 else []

    # Prefer an explicit owner row.  Otherwise use one owner column.  If a
    # table exposes both, requiring agreement prevents a row/column cross-wire.
    layout = "row" if unique_target_rows else (
        "column" if len(unique_owner_columns) == 1 else ""
    )
    if not layout:
        return {}, {
            "table_rows": list(lines),
            "candidate_owner": fact.sample_id_raw,
            "owner_columns": {
                str(index): node.sample_id_raw
                for index, node in sorted(unique_owner_columns.items())
            },
            "owner_rows": {
                str(index): node.sample_id_raw
                for index, node in sorted(owner_rows.items())
            },
            "reason": "owner_coordinate_ambiguous_or_missing",
        }

    parameters = [
        parameter
        for parameter in fact.data.get("parameters_raw") or []
        if isinstance(parameter, dict)
    ]
    decisions: dict[int, tuple[bool | None, dict[str, Any]]] = {}
    for index, parameter in enumerate(fact.data.get("parameters_raw") or []):
        if not isinstance(parameter, dict):
            continue
        name = parameter.get("parameter_name_raw")
        value = parameter.get("value_raw")
        if layout == "row":
            target_row_index = unique_target_rows[0]
            header = parsed[0]
            header_hits = [
                column
                for column, cell in enumerate(header[1:], start=1)
                if _processing_parameter_name_matches(name, cell)
            ]
            # A parameter that is not present in the literal source header may
            # be an OCR repair or a prose parameter bundled with the table.
            if len(header_hits) != 1:
                continue
            column = header_hits[0]
            row = parsed[target_row_index]
            target_cell = row[column] if column < len(row) else ""
            matches_target = _table_value_cell_matches(target_cell, value)
            all_hits = [
                (other_index, other_column)
                for other_index, other_row in enumerate(parsed[1:], start=1)
                for other_column, cell in enumerate(other_row)
                if other_column == column
                if _table_value_cell_matches(cell, value)
            ]
        else:
            parameter_rows = [
                (row_index, row)
                for row_index, row in enumerate(parsed[1:], start=1)
                if row and _processing_parameter_name_matches(name, row[0])
            ]
            # A row that is not present in the literal source table may be an
            # OCR repair or a prose parameter bundled with the table.  Leave
            # it to the normal evidence gates instead of guessing a coordinate.
            if len(parameter_rows) != 1:
                continue
            row_index, row = parameter_rows[0]
            column = next(iter(unique_owner_columns))
            target_cell = row[column] if column < len(row) else ""
            matches_target = _table_value_cell_matches(target_cell, value)
            all_hits = [
                (other_index, other_column)
                for other_index, other_row in enumerate(parsed[1:], start=1)
                for other_column, cell in enumerate(other_row)
                if _table_value_cell_matches(cell, value)
            ]
        details = {
            "table_rows": list(lines),
            "candidate_owner": fact.sample_id_raw,
            "layout": layout,
            "parameter_index": index,
            "parameter_name": name,
            "candidate_value": value,
            "parameter_row": row_index,
            "target_column": column,
            "target_cell": target_cell,
            "value_hits": [
                {"row": hit_row, "column": hit_column}
                for hit_row, hit_column in all_hits
            ],
        }
        if matches_target:
            decisions[index] = (True, details)
        elif all_hits:
            decisions[index] = (
                False,
                {**details, "reason": "value_bound_to_other_owner_coordinate"},
            )
        # No literal value hit means the coordinate is not strong enough to
        # reject (possible OCR normalization); preserve the candidate.
    return decisions, {
        "table_rows": list(lines),
        "candidate_owner": fact.sample_id_raw,
        "layout": layout,
        "owner_columns": {
            str(index): node.sample_id_raw
            for index, node in sorted(unique_owner_columns.items())
        },
        "owner_rows": {
            str(index): node.sample_id_raw
            for index, node in sorted(owner_rows.items())
        },
    }


def _gate_processing_table_bindings(
    anchors: Sequence[InventoryAnchor],
    facts: Sequence[AxisFact],
    source_text: str,
) -> tuple[list[AxisFact], list[PromotionIssue]]:
    """Filter process parameters copied from sibling table columns/rows.

    This is intentionally a partial gate: only a disproven, source-located
    parameter is removed.  Unlocatable rows remain candidates for manual
    review, preserving recall when OCR altered a label or value.
    """

    graph = build_owner_graph(anchors)
    if not graph.nodes:
        return list(facts), []
    accepted: list[AxisFact] = []
    issues: list[PromotionIssue] = []
    for fact in facts:
        if not isinstance(fact, ProcessingFact) or fact.fact_type != "process_stage":
            accepted.append(fact)
            continue
        if not fact.data.get("parameters_raw"):
            accepted.append(fact)
            continue
        record = build_promotion_records([fact])[0]
        decisions, table_details = _processing_table_parameter_coordinate(
            fact, record, graph, source_text
        )
        rejected = {
            index: details
            for index, (decision, details) in decisions.items()
            if decision is False
        }
        if not rejected:
            accepted.append(fact)
            continue
        before = fact.model_dump()
        data = deepcopy(fact.data)
        data["parameters_raw"] = [
            parameter
            for index, parameter in enumerate(data.get("parameters_raw") or [])
            if index not in rejected
        ]
        removed = [
            parameter
            for index, parameter in enumerate(fact.data.get("parameters_raw") or [])
            if index in rejected
        ]
        after = None
        if data["parameters_raw"]:
            cleaned = fact.model_copy(deep=True, update={"data": data})
            accepted.append(cleaned)
            after = cleaned.model_dump()
        issues.append(
            _promotion_issue(
                fact,
                code="promotion_processing_table_parameter_projection_filtered",
                message=(
                    "A Processing table parameter value was bound to a sibling "
                    "owner row/column; only the unsupported projection was "
                    "isolated and the complete candidate was preserved in audit."
                ),
                expected={
                    "unique_owner_value_coordinate": True,
                    "broadcast": False,
                    "audit_preserved": True,
                },
                actual={
                    "before": before,
                    "after": after,
                    "removed_parameters": removed,
                    "parameter_coordinates": list(rejected.values()),
                    "table_coordinate": table_details,
                },
                evidence=list(record.evidence),
            )
        )
    return accepted, issues


def _quarantine_ambiguous_structure_table_projections(
    facts: Sequence[AxisFact], source_text: str
) -> tuple[list[AxisFact], list[PromotionIssue]]:
    """Isolate multi-value Structure rows without a per-value coordinate.

    A compact table response can carry several values for one repeated metric
    (for example, ``gamma-prime volume fraction`` for dendrite-core and
    interdendritic rows) while retaining only one owner/state on the enclosing
    observation.  Keeping that observation would materialize every value on
    the same owner and manufacture a condition/region binding.  A single
    quantitative row is already handled by the normal coordinate gate; this
    additional guard is limited to repeated metric names inside one table
    assertion and preserves the complete fact in the audit trail.
    """

    accepted: list[AxisFact] = []
    issues: list[PromotionIssue] = []
    for fact in facts:
        if not isinstance(fact, StructureFact) or fact.fact_type != "structure_observation":
            accepted.append(fact)
            continue
        record = build_promotion_records([fact])[0]
        table_matches = _table_block_for_record(record, source_text)
        if len(table_matches) != 1:
            accepted.append(fact)
            continue
        feature_rows: list[dict[str, Any]] = []
        for row in fact.data.get("features") or []:
            if isinstance(row, dict):
                feature_rows.append(row)
        for entity in fact.data.get("entities") or []:
            if not isinstance(entity, dict):
                continue
            for row in entity.get("features") or []:
                if isinstance(row, dict):
                    feature_rows.append(row)
        quantitative = [
            row for row in feature_rows if _is_quantitative_structure_feature(row)
        ]
        if len(quantitative) < 2:
            accepted.append(fact)
            continue
        names = [
            _scientific_fold(row.get("feature_name_raw"))
            for row in quantitative
            if str(row.get("feature_name_raw") or "").strip()
        ]
        repeated = sorted(
            name for name, count in Counter(names).items() if name and count > 1
        )
        if not repeated:
            accepted.append(fact)
            continue
        table_lines = table_matches[0]
        parsed_rows = [
            _table_cells(line)
            for line in table_lines
            if _table_cells(line) and not _is_table_separator(_table_cells(line))
        ]
        # Resolve a single owner/state column from the joined multi-row table
        # header.  This lets us retain values that are actually in the target
        # column while dropping only the sibling-column projections.
        header_rows: list[tuple[str, ...]] = []
        for row in parsed_rows:
            first = normalize_evidence_text(row[0]) if row else ""
            if header_rows and first not in {"parameter", "property", "properties"}:
                break
            if first in {"parameter", "property", "properties"}:
                header_rows.append(row)
            elif not header_rows:
                break
        owner = str(record.explicit_owner or "").strip()
        state = str(_record_state(record) or "").strip()
        target_columns: list[int] = []
        if header_rows and (owner or state):
            max_columns = max(len(row) for row in header_rows)
            for column in range(max_columns):
                header = " ".join(
                    row[column] for row in header_rows if column < len(row)
                )
                owner_match = not owner or _table_condition_matches_row(
                    (header,), owner
                )
                state_match = not state or _table_condition_matches_row(
                    (header,), state
                )
                if owner_match and state_match:
                    target_columns.append(column)

        if len(target_columns) == 1:
            target_column = target_columns[0]
            data_rows = parsed_rows[len(header_rows) :]

            # Repeated metrics in a table with an explicit Location/Region
            # (or equivalent) column are not one scalar per material state.
            # If the chunk output dropped that row coordinate, retaining all
            # values would broadcast D/ID (or similar rows) onto one owner.
            # Require the coordinate literal to survive in the candidate
            # evidence or in an explicit feature-level coordinate field.
            row_coordinate_columns = {
                column
                for column in range(
                    max((len(row) for row in header_rows), default=0)
                )
                if re.search(
                    r"(?ix)\b(?:location|region|orientation|position|"
                    r"section|zone|area|specimen|sample)\b",
                    " ".join(
                        row[column]
                        for row in header_rows
                        if column < len(row)
                    ),
                )
            }

            def feature_coordinate_survived(
                feature: dict[str, Any],
                source_rows: Sequence[Sequence[str]],
            ) -> bool:
                feature_evidence = _feature_evidence(feature, record.evidence)
                evidence_text = "\n".join(feature_evidence)
                for key in (
                    "region",
                    "location",
                    "orientation",
                    "position",
                    "section",
                    "zone",
                    "specimen",
                    "sample_id",
                ):
                    value = str(feature.get(key) or "").strip()
                    if value and _scientific_fold(value) not in _UNREPORTED:
                        if _payload_grounded(value, feature_evidence) or _literal_mention(
                            evidence_text, value
                        ):
                            return True
                if not row_coordinate_columns:
                    return False
                name = str(feature.get("feature_name_raw") or "").strip()
                value = feature.get("value_raw")
                matching_rows = []
                for source_row in source_rows:
                    if not source_row:
                        continue
                    if not (
                        _payload_grounded(name, (source_row[0],))
                        or _payload_grounded(source_row[0], (name,))
                    ):
                        continue
                    if target_column < len(source_row) and _table_value_cell_matches(
                        source_row[target_column], value
                    ):
                        matching_rows.append(source_row)
                if len(matching_rows) != 1:
                    return False
                coordinate_cells = [
                    str(source_row[column]).strip()
                    for source_row in matching_rows
                    for column in row_coordinate_columns
                    if column < len(source_row) and str(source_row[column]).strip()
                ]
                return bool(
                    coordinate_cells
                    and any(
                        _payload_grounded(cell, feature_evidence)
                        or _literal_mention(evidence_text, cell)
                        for cell in coordinate_cells
                    )
                )

            if row_coordinate_columns and any(
                not feature_coordinate_survived(feature, data_rows)
                for feature in feature_rows
                if _is_quantitative_structure_feature(feature)
            ):
                issues.append(
                    _promotion_issue(
                        fact,
                        code="promotion_structure_table_row_coordinate_missing_quarantined",
                        message=(
                            "A repeated Structure table metric had an explicit "
                            "row coordinate in the source table, but the chunk "
                            "candidate did not preserve that coordinate; the "
                            "values were isolated instead of broadcast to one "
                            "material state."
                        ),
                        expected={
                            "feature_level_row_coordinate": True,
                            "broadcast": False,
                            "audit_preserved": True,
                        },
                        actual={
                            "removed": fact.model_dump(),
                            "row_coordinate_columns": sorted(row_coordinate_columns),
                            "table_rows": list(table_lines),
                            "reason": "repeated_metric_row_coordinate_missing",
                        },
                        evidence=list(record.evidence),
                    )
                )
                continue

            def feature_matches_target(row: dict[str, Any]) -> bool:
                name = str(row.get("feature_name_raw") or "").strip()
                value = row.get("value_raw")
                if not name or value is None:
                    return False
                for source_row in data_rows:
                    if not source_row:
                        continue
                    source_name = source_row[0]
                    if not (
                        _payload_grounded(name, (source_name,))
                        or _payload_grounded(source_name, (name,))
                    ):
                        continue
                    if target_column < len(source_row) and _table_value_cell_matches(
                        source_row[target_column], value
                    ):
                        return True
                return False

            kept_top = [row for row in feature_rows if feature_matches_target(row)]
            # Only rewrite the feature containers when this table actually
            # locates at least one candidate value.  A non-locatable feature is
            # never silently accepted as a table coordinate.
            if kept_top:
                kept_ids = {id(row) for row in kept_top}
                data = deepcopy(fact.data)
                data["features"] = [
                    row
                    for row in data.get("features") or []
                    if isinstance(row, dict) and id(row) in kept_ids
                ]
                for entity in data.get("entities") or []:
                    if not isinstance(entity, dict):
                        continue
                    entity["features"] = [
                        row
                        for row in entity.get("features") or []
                        if isinstance(row, dict) and id(row) in kept_ids
                    ]
                # ``deepcopy`` changes object identities, so rebuild the
                # filtered containers by semantic object identity from the
                # original rows rather than relying on the copied IDs.
                keep_signatures = {
                    (
                        _scientific_fold(row.get("feature_name_raw")),
                        _scientific_compact(row.get("value_raw")),
                    )
                    for row in kept_top
                }
                data["features"] = [
                    row
                    for row in fact.data.get("features") or []
                    if isinstance(row, dict)
                    and (
                        _scientific_fold(row.get("feature_name_raw")),
                        _scientific_compact(row.get("value_raw")),
                    )
                    in keep_signatures
                ]
                for original_entity, copied_entity in zip(
                    fact.data.get("entities") or [], data.get("entities") or []
                ):
                    if not isinstance(original_entity, dict) or not isinstance(
                        copied_entity, dict
                    ):
                        continue
                    copied_entity["features"] = [
                        row
                        for row in original_entity.get("features") or []
                        if isinstance(row, dict)
                        and (
                            _scientific_fold(row.get("feature_name_raw")),
                            _scientific_compact(row.get("value_raw")),
                        )
                        in keep_signatures
                    ]
                cleaned = fact.model_copy(deep=True, update={"data": data})
                accepted.append(cleaned)
                removed_features = [
                    row
                    for row in quantitative
                    if not feature_matches_target(row)
                ]
                if removed_features:
                    issues.append(
                        _promotion_issue(
                            fact,
                            code="promotion_structure_table_feature_projection_filtered",
                            message=(
                                "A repeated Structure table metric was reduced "
                                "to the one source column matching the existing "
                                "owner/state; sibling-column values were isolated."
                            ),
                            expected={
                                "one_source_owner_state_column": True,
                                "broadcast": False,
                                "audit_preserved": True,
                            },
                            actual={
                                "before": fact.model_dump(),
                                "after": cleaned.model_dump(),
                                "target_column": target_column,
                                "removed_features": removed_features,
                                "reason": "sibling_column_value_projection",
                            },
                            evidence=list(record.evidence),
                        )
                    )
                continue
        # A feature-level region/condition is the only safe way to retain
        # repeated metrics in one observation.  A top-level material_state is
        # intentionally insufficient because it would be broadcast to every
        # value in the row bundle.
        coordinate_keys = (
            "region",
            "location",
            "orientation",
            "material_state",
            "test_condition_raw",
            "condition_raw",
            "sample_id",
        )
        if all(
            any(
                str(row.get(key) or "").strip()
                and _scientific_fold(row.get(key)) not in _UNREPORTED
                for key in coordinate_keys
            )
            for row in quantitative
        ):
            accepted.append(fact)
            continue
        issues.append(
            _promotion_issue(
                fact,
                code="promotion_structure_table_coordinate_ambiguous_quarantined",
                message=(
                    "A Structure table assertion contained repeated quantitative "
                    "metrics without one coordinate per value; the bundle was "
                    "isolated instead of broadcasting all rows to one owner/state."
                ),
                expected={
                    "feature_level_owner_or_condition_coordinate": True,
                    "broadcast": False,
                    "audit_preserved": True,
                },
                actual={
                    "removed": fact.model_dump(),
                    "repeated_feature_names": repeated,
                    "quantitative_feature_count": len(quantitative),
                    "table_rows": list(table_matches[0]),
                    "reason": "repeated_metric_without_feature_coordinate",
                },
                evidence=list(record.evidence),
            )
        )
    return accepted, issues


_COMPOSITION_EXTERNAL_NOTE = re.compile(
    r"(?ix)(?:"
    r"\b(?:literature|external|reference)\b.{0,64}\b(?:composition|chemistry|"
    r"content|concentration|range|value|reported)\b|"
    r"\b(?:composition|chemistry|content|concentration|range|value|reported)\b"
    r".{0,64}\b(?:literature|external|reference)\b"
    r")"
)
_COMPOSITION_EXTERNAL_REPORTING_SUBJECT = re.compile(
    r"(?ix)(?:"
    r"\b[a-z][a-z'’.-]{1,}\s+et\s+al\.?\s*"
    r"(?:\[[^\]\n]{1,40}\]\s*)?"
    r"(?:reported|showed|found|observed|determined|measured)\b|"
    r"\b(?:previous|prior|earlier)\s+(?:work|study)\b.{0,40}"
    r"\b(?:reported|showed|found|observed|determined|measured)\b|"
    r"\b(?:according\s+to|as\s+reported\s+by)\b|"
    r"\b(?:the\s+)?(?:literature|reference)\b.{0,40}"
    r"\b(?:reported|shows?|gives?|lists?)\b"
    r")"
)
_COMPOSITION_GENERAL_REFERENCE_SCOPE = re.compile(
    r"(?ix)\b(?:in\s+general|generally|typically|equilibrium|maximum|"
    r"upper\s+limit|limiting)\b"
)
_COMPOSITION_SOLID_SOLUBILITY = re.compile(
    r"(?ix)\bsolid\s+solubilit(?:y|ies)\b"
)
_COMPOSITION_GENERAL_CLASS_RANGE = re.compile(
    r"(?ix)\b(?:alloys?|superalloys?|materials?)\b.{0,120}"
    r"\b(?:composition|chemistry|content|concentration|range)\b"
)
_COMPOSITION_CURRENT_SUBJECT = re.compile(
    r"(?ix)(?:"
    r"\b(?:we|the\s+authors?)\s+(?:measured|determined|found|observed|used|"
    r"prepared|produced|fabricated|report(?:ed)?)\b|"
    r"\bour\s+(?:(?:as[\s-]*)?(?:built|printed|sintered|fabricated)\s+)?"
    r"(?:alloys?|materials?|samples?|specimens?|parts?|powders?|matrix|matrices)\b|"
    r"\b(?:this|current|present)\s+(?:study|work|paper|alloys?|materials?|"
    r"samples?|specimens?|parts?|powders?)\b|"
    r"\b(?:the\s+)?(?:alloys?|materials?|samples?|specimens?|parts?|powders?)"
    r"\b.{0,48}\b(?:contained|contains|consisted|had|was\s+measured|"
    r"were\s+measured)\b"
    r")"
)
_COMPOSITION_DIRECT_MEASUREMENT = re.compile(
    r"(?ix)\b(?:apt|atom\s+probe|eds|edx|sem-eds|icp|xrf|measured|"
    r"determined|quantified|actual\s+composition|nominal\s+composition)\b"
)
_COMPOSITION_UNIT_TOKEN = re.compile(
    r"(?ix)(?:at\.?\s*%|wt\.?\s*%|vol\.?\s*%|mol\.?\s*%|ppm|ppb)"
)


@dataclass(frozen=True)
class _CompositionSubjectDecision:
    component_index: int
    component: dict[str, Any]
    matched_source_sentence: str
    value_local_proposition: str
    subject_cue: str
    decision_class: Literal[
        "attributed_literature_chemistry",
        "general_reference_constraint",
    ]
    reason: str


def _composition_number_key(value: Any) -> str:
    text = str(value or "").strip().lstrip("+")
    try:
        return format(float(text), ".15g")
    except ValueError:
        return text.casefold()


def _composition_number_spans(value: Any) -> tuple[tuple[str, int, int], ...]:
    return tuple(
        (
            _composition_number_key(match.group(0)),
            match.start(),
            match.end(),
        )
        for match in _TABLE_NUMERIC_TOKEN.finditer(str(value or ""))
    )


def _composition_unit_keys(value: Any) -> tuple[str, ...]:
    return tuple(
        dict.fromkeys(
            _generic_unit_key(match.group(0))
            for match in _COMPOSITION_UNIT_TOKEN.finditer(str(value or ""))
        )
    )


def _composition_component_value_windows(
    text: str,
    component: dict[str, Any],
) -> tuple[str, ...]:
    """Bind one component name, complete value, and unit in a small window."""

    value_raw = component.get("value_raw")
    expected_numbers = tuple(
        row[0] for row in _composition_number_spans(value_raw)
    )
    if not expected_numbers:
        return ()
    source_numbers = _composition_number_spans(text)
    if not source_numbers:
        return ()
    aliases = tuple(
        dict.fromkeys(
            str(component.get(key) or "").strip()
            for key in ("name_raw", "canonical_name")
            if str(component.get(key) or "").strip()
        )
    )
    if not aliases:
        return ()
    declared_unit = _generic_unit_key(
        component.get("canonical_unit") or component.get("unit_raw")
    )
    if not declared_unit or declared_unit in _UNREPORTED:
        return ()

    matched: list[str] = []
    for start_index, (number, start, end) in enumerate(source_numbers):
        if number != expected_numbers[0]:
            continue
        cursor = start_index + 1
        final_end = end
        complete = True
        for expected in expected_numbers[1:]:
            while (
                cursor < len(source_numbers)
                and source_numbers[cursor][0] != expected
            ):
                cursor += 1
            if cursor >= len(source_numbers):
                complete = False
                break
            _, next_start, next_end = source_numbers[cursor]
            if next_start - final_end > 48:
                complete = False
                break
            final_end = next_end
            cursor += 1
        if not complete:
            continue
        source = str(text)
        window = source[max(0, start - 20) : min(len(source), final_end + 20)]
        if not any(_literal_mention(window, alias) for alias in aliases):
            continue
        source_units = _composition_unit_keys(window)
        if declared_unit not in source_units:
            continue
        matched.append(window.strip())
    return tuple(dict.fromkeys(matched))


def _composition_source_sentences(source_text: str) -> tuple[str, ...]:
    """Return bounded prose sentences while preserving repeated occurrences."""

    rows: list[str] = []
    for paragraph in re.split(r"\n\s*\n|\r\n\s*\r\n", str(source_text or "")):
        paragraph = paragraph.strip()
        if not paragraph:
            continue
        rows.extend(
            sentence.strip()
            for sentence in re.split(
                r"(?<=[.!?])\s+(?=[A-Z0-9])|\n+",
                paragraph,
            )
            if sentence.strip()
        )
    return tuple(rows)


def _composition_current_subject_guard(
    proposition: str,
    owner_nodes: Sequence[OwnerNode],
) -> bool:
    if _COMPOSITION_CURRENT_SUBJECT.search(proposition):
        return True
    for node in owner_nodes:
        if any(
            _distinctive_owner_label(alias)
            and _literal_mention(proposition, alias)
            for alias in node.aliases
        ):
            return True
        if node.state_raw and _literal_mention(proposition, node.state_raw):
            return True
    return False


def _composition_subject_decision(
    fact: CompositionFact,
    component_index: int,
    component: dict[str, Any],
    owner_nodes: Sequence[OwnerNode],
    source_text: str,
) -> _CompositionSubjectDecision | None:
    evidence_rows = [
        row
        for row in _fact_evidence(fact)
        if len(_composition_component_value_windows(row, component)) == 1
    ]
    if not evidence_rows:
        return None

    matches: list[tuple[str, str]] = []
    for sentence in _composition_source_sentences(source_text):
        normalized_sentence = normalize_evidence_text(sentence)
        if not normalized_sentence:
            continue
        if len(_composition_component_value_windows(sentence, component)) != 1:
            continue
        for proposition in evidence_rows:
            normalized_proposition = normalize_evidence_text(proposition)
            if not normalized_proposition:
                continue
            if (
                normalized_proposition in normalized_sentence
                or normalized_sentence in normalized_proposition
            ):
                matches.append((sentence, proposition))
    # Repeated source occurrences and multiple evidence projections are
    # deliberately unresolved. The gate never chooses the nearest paragraph.
    if len(matches) != 1:
        return None
    sentence, proposition = matches[0]
    if _composition_current_subject_guard(proposition, owner_nodes):
        return None

    normalized_sentence = normalize_evidence_text(sentence)
    normalized_proposition = normalize_evidence_text(proposition)
    proposition_start = normalized_sentence.find(normalized_proposition)
    proposition_end = proposition_start + len(normalized_proposition)
    note = str(fact.data.get("note") or "")

    external_cues = [
        match
        for match in _COMPOSITION_EXTERNAL_REPORTING_SUBJECT.finditer(
            normalized_sentence
        )
        if match.start() <= max(proposition_start, 0)
        or (
            proposition_start >= 0
            and match.start() < proposition_end
            and match.end() > proposition_start
        )
    ]
    if _COMPOSITION_EXTERNAL_NOTE.search(note) and len(external_cues) == 1:
        cue = external_cues[0]
        subject_window = normalized_sentence[cue.start() : proposition_end]
        if not _COMPOSITION_CURRENT_SUBJECT.search(subject_window):
            return _CompositionSubjectDecision(
                component_index=component_index,
                component=deepcopy(component),
                matched_source_sentence=sentence,
                value_local_proposition=proposition,
                subject_cue=cue.group(0),
                decision_class="attributed_literature_chemistry",
                reason="external_reporting_subject_owns_value",
            )

    reference_scope = bool(
        _COMPOSITION_GENERAL_REFERENCE_SCOPE.search(normalized_sentence)
        or _COMPOSITION_GENERAL_REFERENCE_SCOPE.search(note)
    )
    reference_constraint = bool(
        _COMPOSITION_SOLID_SOLUBILITY.search(normalized_sentence)
        or (
            _COMPOSITION_GENERAL_CLASS_RANGE.search(normalized_sentence)
            and _COMPOSITION_EXTERNAL_NOTE.search(note)
        )
    )
    if (
        reference_scope
        and reference_constraint
        and not _COMPOSITION_DIRECT_MEASUREMENT.search(proposition)
        and not _COMPOSITION_CURRENT_SUBJECT.search(normalized_sentence)
    ):
        cue_match = (
            _COMPOSITION_SOLID_SOLUBILITY.search(normalized_sentence)
            or _COMPOSITION_GENERAL_CLASS_RANGE.search(normalized_sentence)
        )
        return _CompositionSubjectDecision(
            component_index=component_index,
            component=deepcopy(component),
            matched_source_sentence=sentence,
            value_local_proposition=proposition,
            subject_cue=cue_match.group(0) if cue_match is not None else "",
            decision_class="general_reference_constraint",
            reason="general_material_constraint_not_current_composition",
        )
    return None


def _quarantine_external_composition_subject_projections(
    anchors: Sequence[InventoryAnchor],
    facts: Sequence[AxisFact],
    source_text: str,
) -> tuple[list[AxisFact], list[PromotionIssue]]:
    """Isolate external/reference chemistry projected onto current Targets."""

    graph = build_owner_graph(anchors)
    if not graph.nodes or not source_text:
        return list(facts), []
    accepted: list[AxisFact] = []
    issues: list[PromotionIssue] = []
    for fact in facts:
        if not (
            isinstance(fact, CompositionFact)
            and fact.fact_type == "composition_observation"
        ):
            accepted.append(fact)
            continue
        evidence = _fact_evidence(fact)
        if _has_table_evidence(evidence):
            accepted.append(fact)
            continue
        record = build_promotion_records([fact])[0]
        owner_nodes = _candidate_nodes(record, graph)
        if not owner_nodes or not all(
            node.role == "Target" and node.data_nature == "Experimental"
            for node in owner_nodes
        ):
            accepted.append(fact)
            continue
        components = [
            row
            for row in fact.data.get("components") or []
            if isinstance(row, dict)
        ]
        decisions = [
            decision
            for index, component in enumerate(components)
            if (
                decision := _composition_subject_decision(
                    fact,
                    index,
                    component,
                    owner_nodes,
                    source_text,
                )
            )
            is not None
        ]
        if not decisions:
            accepted.append(fact)
            continue
        removed_indexes = {decision.component_index for decision in decisions}
        kept = [
            deepcopy(component)
            for index, component in enumerate(components)
            if index not in removed_indexes
        ]
        cleaned: CompositionFact | None = None
        if kept:
            data = deepcopy(fact.data)
            data["components"] = kept
            cleaned = fact.model_copy(deep=True, update={"data": data})
            accepted.append(cleaned)
        before = fact.model_dump()
        after = cleaned.model_dump() if cleaned is not None else None
        owner_candidates = [node.sample_id_raw for node in owner_nodes]
        for decision in decisions:
            issues.append(
                _promotion_issue(
                    fact,
                    code="promotion_external_composition_subject_quarantined",
                    message=(
                        "A chemistry value belonged to cited literature or a "
                        "general reference constraint rather than the current "
                        "experimental Target; only that disproven component was "
                        "isolated."
                    ),
                    expected={
                        "value_subject": "current experimental material",
                        "external_projection": False,
                        "component_local_filtering": True,
                        "audit_preserved": True,
                    },
                    actual={
                        "before": before,
                        "after": after,
                        "removed_component": decision.component,
                        "matched_source_sentence": decision.matched_source_sentence,
                        "value_local_proposition": decision.value_local_proposition,
                        "subject_cue": decision.subject_cue,
                        "decision_class": decision.decision_class,
                        "reason": decision.reason,
                        "owner_candidates": owner_candidates,
                        "current_source_guard": False,
                        "owner_invented": False,
                    },
                    evidence=evidence,
                )
            )
    return accepted, issues


def _quarantine_external_source_projections(
    anchors: Sequence[InventoryAnchor],
    facts: Sequence[AxisFact],
) -> tuple[list[AxisFact], list[PromotionIssue]]:
    """Isolate cited/previous-work claims copied onto a current owner.

    This is deliberately narrower than an origin classifier.  It requires an
    explicit citation/previous-work cue, a current experimental owner, no
    collective-owner grammar, and no literal owner label in the candidate's
    own evidence.  A source sentence that names the owner or says ``we
    observed`` remains untouched.  Composition is excluded because its source
    path is independently audited and protected.
    """

    graph = build_owner_graph(anchors)
    if not graph.nodes:
        return list(facts), []
    accepted: list[AxisFact] = []
    issues: list[PromotionIssue] = []
    for fact in facts:
        if isinstance(fact, CompositionFact):
            accepted.append(fact)
            continue
        record = build_promotion_records([fact])[0]
        support = "\n".join(record.evidence)
        external_match = _EXTERNAL_SOURCE_ASSERTION.search(support)
        if external_match is None:
            external_match = _EXTERNAL_BIBLIOGRAPHIC_ASSERTION.search(support)
        if external_match is None:
            accepted.append(fact)
            continue
        if _CURRENT_SOURCE_ASSERTION.search(support) or _has_collective_owner_scope(support):
            accepted.append(fact)
            continue
        owner_nodes = _candidate_nodes(record, graph)
        if not any(
            node.role == "Target" and node.data_nature == "Experimental"
            for node in owner_nodes
        ):
            accepted.append(fact)
            continue
        literal_owner = any(
            _distinctive_owner_label(alias)
            and _literal_mention(support, alias)
            for node in owner_nodes
            for alias in node.aliases
        )
        if literal_owner:
            accepted.append(fact)
            continue
        issues.append(
            _promotion_issue(
                fact,
                code="promotion_external_source_projection_quarantined",
                message=(
                    "A cited or previous-work assertion was copied onto a current "
                    "experimental owner without a literal owner binding; it was "
                    "isolated instead of being promoted as a current-paper fact."
                ),
                expected={
                    "source_scope": "current experimental assertion with literal owner",
                    "external_projection": False,
                    "audit_preserved": True,
                },
                actual={
                    "removed": fact.model_dump(),
                    "owner_candidates": [node.sample_id_raw for node in owner_nodes],
                    "external_cue": external_match.group(0),
                },
                evidence=list(record.evidence),
            )
        )
    return accepted, issues


def _quarantine_unbound_core_tensile_external_projections(
    anchors: Sequence[InventoryAnchor],
    facts: Sequence[AxisFact],
) -> tuple[list[AxisFact], list[PromotionIssue]]:
    """Isolate cited tensile values that are not bound to a source owner.

    A prose sentence such as ``cast alloy 625 [11] had a UTS of 710 MPa`` is
    source-grounded, but it is a literature comparison rather than a result for
    the current paper's target item.  When the extractor attaches that value to
    a generic current owner, the number looks valid while its provenance is
    false.  The existing external-source gate can only act when the inventory
    graph resolves the candidate owner; this narrower pass closes the unresolved
    case without touching table rows, explicitly named owners, or reference
    items.  It never consults GT and keeps the complete candidate in audit.
    """

    graph = build_owner_graph(anchors)
    accepted: list[AxisFact] = []
    issues: list[PromotionIssue] = []
    for fact in facts:
        if not (
            isinstance(fact, PropertyFact)
            and is_core_tensile_property_name(
                fact.data.get("property_name_raw")
            )
        ):
            accepted.append(fact)
            continue
        evidence = _fact_evidence(fact)
        support = "\n".join(evidence)
        # Table/HTML rows are handled by the coordinate-aware tensile gates;
        # this pass is intentionally prose-only.
        if _has_table_evidence(evidence):
            accepted.append(fact)
            continue
        record = build_promotion_records([fact])[0]
        owner_nodes = _candidate_nodes(record, graph)
        subject_decision = _tensile_external_subject_decision(
            fact, evidence, owner_nodes
        )
        external = _EXTERNAL_SOURCE_ASSERTION.search(support)
        if external is None and subject_decision is None:
            accepted.append(fact)
            continue
        # Current-study language is protective only when the candidate's own
        # value-local proposition is not proven to belong to a comparator.
        if (
            subject_decision is None
            and _CURRENT_SOURCE_ASSERTION.search(support)
        ):
            accepted.append(fact)
            continue
        if (
            _has_collective_owner_scope(support)
            and subject_decision is None
        ):
            accepted.append(fact)
            continue

        current_experimental_owner = any(
            node.role == "Target" and node.data_nature == "Experimental"
            for node in owner_nodes
        )
        if current_experimental_owner:
            if subject_decision is not None:
                issues.append(
                    _promotion_issue(
                        fact,
                        code=(
                            "promotion_external_current_tensile_projection_"
                            "quarantined"
                        ),
                        message=(
                            "A numeric core-tensile value belonged to a cited "
                            "or comparison material subject, not the current "
                            "experimental owner; the embedded current-alloy "
                            "substring did not override that source scope."
                        ),
                        expected={
                            "current_result_assertion": True,
                            "external_projection": False,
                            "audit_preserved": True,
                        },
                        actual={
                            "removed": fact.model_dump(),
                            "reason": (
                                "external_comparator_subject_on_current_owner"
                            ),
                            "owner_candidates": [
                                node.sample_id_raw for node in owner_nodes
                            ],
                            "matched_source_sentence": (
                                subject_decision.matched_source_sentence
                            ),
                            "value_local_proposition": (
                                subject_decision.value_local_proposition
                            ),
                            "external_subject": (
                                subject_decision.external_subject
                            ),
                            "subject_cue": subject_decision.subject_cue,
                            "embedded_owner_literal": (
                                subject_decision.embedded_owner_literal
                            ),
                            "owner_invented": False,
                        },
                        evidence=evidence,
                    )
                )
                continue
            # A literal current-paper label is not sufficient when the same
            # sentence explicitly says the number was reported by a prior
            # study.  This is the common ``EPBF ... were reported ...``
            # projection: source-grounded, but not a result of this paper.
            # Preserve a direct current assertion when its own result sentence
            # has no reporting cue; a citation in a separate sentence must not
            # erase an otherwise source-local result.
            direct_current = False
            value_scope = _tensile_value_local_scope(fact, evidence)
            value_windows = (
                [value_scope.value_local_proposition]
                if value_scope is not None
                else [
                    sentence
                    for evidence_row in evidence
                    for sentence in _TENSILE_SENTENCE_BOUNDARY.split(
                        str(evidence_row)
                    )
                    if set(_numeric_tokens(fact.data.get("value_raw"))).intersection(
                        _numeric_tokens(sentence)
                    )
                ]
            )
            for value_window in value_windows:
                if not _TENSILE_RESULT_CUE.search(value_window):
                    continue
                if _EXTERNAL_REPORTING_CUE.search(value_window):
                    continue
                if any(
                    _distinctive_owner_label(alias)
                    and _literal_mention(value_window, alias)
                    for node in owner_nodes
                    for alias in _owner_evidence_aliases(node.sample_id_raw)
                ):
                    direct_current = True
                    break
            if not direct_current:
                issues.append(
                    _promotion_issue(
                        fact,
                        code="promotion_external_current_tensile_projection_quarantined",
                        message=(
                            "A cited/previous-work core-tensile value was attached "
                            "to a current experimental owner; a literal owner label "
                            "does not override the external reporting scope."
                        ),
                        expected={
                            "current_result_assertion": True,
                            "external_projection": False,
                            "audit_preserved": True,
                        },
                        actual={
                            "removed": fact.model_dump(),
                            "reason": "external_reporting_on_current_owner",
                            "owner_candidates": [
                                node.sample_id_raw for node in owner_nodes
                            ],
                            "external_cue": (
                                external.group(0) if external is not None else None
                            ),
                            "matched_source_sentence": (
                                value_scope.matched_source_sentence
                                if value_scope is not None
                                else None
                            ),
                            "value_local_proposition": (
                                value_scope.value_local_proposition
                                if value_scope is not None
                                else None
                            ),
                            "external_subject": None,
                            "subject_cue": (
                                external.group(0) if external is not None else None
                            ),
                            "embedded_owner_literal": None,
                            "owner_invented": False,
                        },
                        evidence=evidence,
                    )
                )
                continue
        reference_nodes = [
            node
            for node in owner_nodes
            if node.role == "Reference"
            or str(node.data_nature).startswith("Literature_")
        ]
        if len(reference_nodes) == 1 and (
            _direct_author_reference_anchor_supports_fact(
                fact, evidence, reference_nodes[0]
            )
            or _literal_author_year_reference_anchor_supports_fact(
                fact, evidence, reference_nodes[0]
            )
        ):
            # The owner is not being inferred from the author alone: the fact
            # already names one existing Reference anchor and that anchor
            # carries the same source-local assertion. Materialization will
            # add the explicit ``[reference]`` presentation and full audit.
            accepted.append(fact)
            continue
        owner_label = str(fact.sample_id_raw or "").strip()
        owner_nodes_are_reference = bool(owner_nodes) and all(
            node.role == "Reference"
            or str(node.data_nature).startswith("Literature_")
            for node in owner_nodes
        )
        if (
            subject_decision is None
            and owner_label
            and _literal_mention(support, owner_label)
            and not owner_nodes_are_reference
        ):
            accepted.append(fact)
            continue
        # A resolved literature/reference owner is only safe when the source
        # assertion selects one existing reference coordinate.  A citation
        # author or generic alloy label can legitimately have several state
        # siblings in the inventory (for example ``as-sintered``,
        # ``solutionized`` and ``aged``).  Treating ``all Reference`` as
        # sufficient would therefore broadcast one value across those states
        # and make the formal owner look more precise than the source.  Keep
        # the historical permissive path for a single resolved reference
        # node, or for an explicitly source-named reference owner; unresolved
        # and multi-state reference projections are isolated below.
        source_named_reference_nodes = [
            node
            for node in _safe_source_owner_nodes(support, graph)
            if node.role == "Reference"
            or str(node.data_nature).startswith("Literature_")
        ]
        if len(reference_nodes) > 1:
            condition = str(
                fact.data.get("test_condition_raw") or ""
            ).strip()
            if condition and _payload_grounded(condition, evidence):
                state_matches = {
                    node.owner_id: node
                    for node in reference_nodes
                    if node.state_raw
                    and _reference_treatment_state_matches_condition(
                        condition, node
                    )
                }
                if len(state_matches) == 1:
                    target = next(iter(state_matches.values()))
                    # Property facts do not carry a public ``sample_id``
                    # coordinate for the treatment state.  Preserve the
                    # existing source owner and add the already declared
                    # state to the internal routing field; materialization
                    # uses this field to resolve the same owner graph node
                    # without inventing a new Sample_ID.
                    data = deepcopy(fact.data)
                    data["material_state"] = target.state_raw
                    reassigned = fact.model_copy(deep=True, update={"data": data})
                    accepted.append(reassigned)
                    issues.append(
                        _promotion_issue(
                            fact,
                            code=(
                                "promotion_external_tensile_reference_state_"
                                "reassigned"
                            ),
                            message=(
                                "A cited core-tensile condition selected one "
                                "existing reference treatment state; the value "
                                "was routed there without inventing an owner."
                            ),
                            expected={
                                "unique_existing_reference_state": (
                                    target.sample_id_raw
                                ),
                                "condition_source_grounded": True,
                                "owner_invented": False,
                                "audit_preserved": True,
                            },
                            actual={
                                "before": fact.model_dump(),
                                "after": reassigned.model_dump(),
                                "condition": condition,
                                "reference_owner_candidates": [
                                    node.sample_id_raw
                                    for node in reference_nodes
                                ],
                                "target_state": target.state_raw,
                            },
                            evidence=evidence,
                        )
                    )
                    continue
        if reference_nodes and len(reference_nodes) == 1:
            reference = reference_nodes[0]
            condition = str(fact.data.get("test_condition_raw") or "").strip()
            owner_literal = any(
                _distinctive_owner_label(alias)
                and _literal_mention(support, alias)
                for alias in _owner_evidence_aliases(reference.sample_id_raw)
            )
            condition_literal = bool(
                condition
                and _payload_grounded(condition, evidence)
                and _reference_treatment_state_matches_condition(
                    condition, reference
                )
            )
            if owner_literal or condition_literal:
                accepted.append(fact)
                continue
            # A single generated Reference node is not itself provenance.  If
            # neither the source owner nor a unique treatment coordinate is
            # present in the quoted assertion, isolate the projection.
            # Otherwise an alloy label plus a citation can silently create a
            # new literature owner/state.
        if len(source_named_reference_nodes) == 1:
            accepted.append(fact)
            continue

        issues.append(
            _promotion_issue(
                fact,
                code="promotion_unbound_external_tensile_quarantined",
                message=(
                    "A cited/previous-work core-tensile value lacked a literal "
                    "owner binding in its own prose evidence; it was isolated "
                    "instead of being attached to the current target item."
                ),
                expected={
                    "current_owner_literal_in_evidence": True,
                    "reference_owner_explicit": True,
                    "audit_preserved": True,
                },
                actual={
                    "removed": fact.model_dump(),
                    "reason": (
                        "external_comparator_without_reference_owner"
                        if subject_decision is not None
                        else "external_prose_without_owner_coordinate"
                    ),
                    "external_cue": (
                        subject_decision.subject_cue
                        if subject_decision is not None
                        else external.group(0)
                    ),
                    "owner_candidates": [
                        node.sample_id_raw for node in owner_nodes
                    ],
                    "matched_source_sentence": (
                        subject_decision.matched_source_sentence
                        if subject_decision is not None
                        else None
                    ),
                    "value_local_proposition": (
                        subject_decision.value_local_proposition
                        if subject_decision is not None
                        else None
                    ),
                    "external_subject": (
                        subject_decision.external_subject
                        if subject_decision is not None
                        else None
                    ),
                    "subject_cue": (
                        subject_decision.subject_cue
                        if subject_decision is not None
                        else external.group(0)
                    ),
                    "embedded_owner_literal": (
                        subject_decision.embedded_owner_literal
                        if subject_decision is not None
                        else None
                    ),
                    "owner_invented": False,
                },
                evidence=evidence,
            )
        )
    return accepted, issues


def _quarantine_property_projections(
    facts: Sequence[AxisFact],
) -> tuple[list[AxisFact], list[PromotionIssue]]:
    """Keep formal material outcomes; audit comparison and protocol shadows.

    This is deliberately later than the claim-quality gate: claim quality may
    normalize a source-explicit relative quantity (for example ``density
    change`` or ``creep lifetime improvement``) before it reaches promotion.
    Such a normalized candidate is still not an absolute material outcome and
    must remain in the audit stream rather than entering ``Properties``.
    """

    accepted: list[AxisFact] = []
    issues: list[PromotionIssue] = []
    for fact in facts:
        if not isinstance(fact, PropertyFact):
            accepted.append(fact)
            continue
        name = str(fact.data.get("property_name_raw") or "")
        metadata_reason = _property_metadata_projection_reason(fact)
        if metadata_reason is not None:
            issues.append(
                _promotion_issue(
                    fact,
                    code="promotion_property_metadata_quarantined",
                    message=(
                        "A Property candidate was isolated because its label or "
                        "table header identifies a model, fit parameter, method, "
                        "or placeholder rather than a standalone material result."
                    ),
                    expected={
                        "scientific_property_label": True,
                        "metadata_or_model_projection": False,
                        "audit_preserved": True,
                    },
                    actual={
                        "removed": fact.model_dump(),
                        "reason": metadata_reason,
                    },
                )
            )
            continue
        if is_core_tensile_property_name(name) and _COMPARATIVE_TENSILE_PROPERTY.search(
            name
        ):
            issues.append(
                _promotion_issue(
                    fact,
                    code="promotion_comparative_tensile_quarantined",
                    message=(
                        "A comparison, contribution, retention, or relative tensile "
                        "quantity is not an absolute material Property outcome."
                    ),
                    expected={
                        "formal_property": False,
                        "audit_preserved": True,
                    },
                    actual={
                        "removed": fact.model_dump(),
                        "reason": "comparison_only_tensile_quantity",
                    },
                )
            )
            continue
        comparative_reason = _property_comparative_projection_reason(fact)
        if comparative_reason is not None:
            issues.append(
                _promotion_issue(
                    fact,
                    code="promotion_property_comparative_projection_quarantined",
                    message=(
                        "A source-grounded Property candidate represented a "
                        "comparison, derived contribution, process parameter, or "
                        "protocol-table field rather than an absolute material "
                        "outcome. It was isolated with its complete audit payload."
                    ),
                    expected={
                        "absolute_material_outcome": True,
                        "comparison_or_protocol_projection": False,
                        "audit_preserved": True,
                    },
                    actual={
                        "removed": fact.model_dump(),
                        "reason": comparative_reason,
                    },
                )
            )
            continue
        unit = _scientific_fold(fact.data.get("unit_raw"))
        inline_core_unit = bool(
            is_core_tensile_property_name(name)
            and _INLINE_CORE_TENSILE_UNIT.search(
                str(fact.data.get("value_raw") or "")
            )
        )
        if (
            unit in _UNREPORTED
            and not _DIMENSIONLESS_PROPERTY.search(name)
            and not inline_core_unit
        ):
            issues.append(
                _promotion_issue(
                    fact,
                    code="promotion_unitless_property_quarantined",
                    message=(
                        "A formal Property candidate lacked a physical unit and was "
                        "not an explicitly dimensionless material quantity."
                    ),
                    expected={
                        "unit": "source-literal physical unit or dimensionless ontology",
                        "formal_property": False,
                    },
                    actual={
                        "removed": fact.model_dump(),
                        "reason": "unit_missing_for_dimensional_property",
                    },
                )
            )
            continue
        accepted.append(fact)
    return accepted, issues


_COMPARATIVE_OWNER_CUE = re.compile(
    r"(?i)\b(?:compared\s+(?:with|to)|relative\s+to|than)\b"
)


def _owner_is_comparison_target(fact: PropertyFact) -> bool:
    """Return whether the declared owner occurs only as a comparator target.

    A sentence such as ``the annealed sample had 3% elongation compared with
    the as-built samples`` reports the value for the annealed sample.  If a
    high-recall chunk assigns that value to ``as-built``, retaining it would
    create a factually plausible number under the wrong state.  We isolate the
    candidate unless the source also provides a direct owner coordinate later;
    the full evidence remains in the audit issue for manual reassignment.
    """

    owner = _identity_text(fact.sample_id_raw)
    if len(owner) < 2:
        return False
    evidence_rows = _fact_evidence(fact)
    value_scope = _tensile_value_local_scope(fact, evidence_rows)
    scoped_evidence = (
        [value_scope.value_local_proposition]
        if value_scope is not None
        else evidence_rows
    )
    for evidence in scoped_evidence:
        text = _identity_text(evidence)
        if not text:
            continue
        start = 0
        while True:
            position = text.find(owner, start)
            if position < 0:
                break
            prefix = text[max(0, position - 120) : position]
            if _COMPARATIVE_OWNER_CUE.search(prefix):
                return True
            start = position + len(owner)
    return False


def _quarantine_comparative_owner_projections(
    facts: Sequence[AxisFact],
) -> tuple[list[AxisFact], list[PromotionIssue]]:
    """Isolate numeric core-tensile values attached to a comparator owner."""

    accepted: list[AxisFact] = []
    issues: list[PromotionIssue] = []
    for fact in facts:
        if not (
            isinstance(fact, PropertyFact)
            and is_core_tensile_property_name(fact.data.get("property_name_raw"))
            and _numeric_tokens(str(fact.data.get("value_raw") or ""))
            and _owner_is_comparison_target(fact)
        ):
            accepted.append(fact)
            continue
        issues.append(
            _promotion_issue(
                fact,
                code="promotion_comparative_owner_projection_quarantined",
                message=(
                    "A numeric core-tensile value was assigned to an owner that "
                    "the source mentions only as the comparison target; it was "
                    "isolated instead of being promoted under the wrong state."
                ),
                expected={
                    "owner_role": "value subject, not comparison target",
                    "audit_preserved": True,
                },
                actual={
                    "removed": fact.model_dump(),
                    "reason": "declared_owner_occurs_after_comparison_cue",
                },
                suggested_action=(
                    "Reassign to the sentence subject only when the source gives "
                    "an explicit owner/state coordinate."
                ),
            )
        )
    return accepted, issues


_STATISTICAL_SHADOW_SUFFIX = re.compile(
    r"(?ix)^\s*(?P<base>.+?)\s+(?:std\.?|stdev\.?|standard\s+deviation|sd)\s*$"
)
_STATISTICAL_TABLE_ROW_LABELS = {
    "sd",
    "standard deviation",
    "std",
    "stdev",
}
_COMPOSITION_PROPERTY_DESCRIPTORS = {
    "amount",
    "composition",
    "concentration",
    "content",
    "fraction",
    "level",
}
_MEASUREMENT_NAME_MODIFIERS = {
    "average",
    "avg",
    "maximum",
    "mean",
    "minimum",
    "nominal",
    "reported",
}


def _reported_state(value: Any) -> str:
    normalized = _scientific_fold(value)
    return "" if normalized in _UNREPORTED else normalized


def _fact_material_state(fact: AxisFact) -> str:
    for key in ("material_state", "material_state_raw", "state_raw", "state"):
        if key in fact.data:
            return _reported_state(fact.data.get(key))
    return ""


_EXPLICIT_NUMBERED_TABLE_CITATION = re.compile(
    r"(?i)\btable\s*(?P<number>\d+[a-z]?)\b"
)
_EXACT_PROPERTY_SCALAR = re.compile(
    r"(?ix)^\s*(?P<number>[-+]?\d+(?:\.\d+)?(?:e[-+]?\d+)?)\s*"
    r"(?P<unit>%|[a-zµμ°]+(?:\s*/\s*[a-z0-9µμ°]+)?)?\s*$"
)
_PROPERTY_COORDINATE_FIELDS = (
    "test_method_raw",
    "test_standard_raw",
    "test_condition_raw",
    "test_specimen_raw",
)
_INDEPENDENT_PROPERTY_MEASUREMENT = re.compile(
    r"(?ix)\b(?:independent(?:ly)?|separate(?:ly)?\s+measured|"
    r"new\s+measurement|replicate\s+average|average\s+of\s+"
    r"(?:the\s+)?(?:repeated|replicate))\b"
)


def same_table_property_merge_v201_enabled() -> bool:
    """Return whether the v201 same-table Property merge is enabled.

    The default is production-on.  The switch exists so an experiment can
    rematerialize the same frozen task responses with the current runtime
    on both sides, isolating this gate from unrelated historical code changes.
    """

    raw = os.getenv("KNOWMAT2_ALPHA25_SAME_TABLE_PROPERTY_MERGE_V201", "1")
    return raw.strip().casefold() not in {
        "0",
        "false",
        "no",
        "off",
        "disabled",
    }


def _exact_property_scalar(fact: PropertyFact) -> tuple[float, str] | None:
    """Return an exact non-comparative scalar and canonical declared unit."""

    raw = str(fact.data.get("value_raw") or "").strip()
    if re.search(
        r"(?ix)(?:±|\+/-|\\pm|[<>≥≤]|(?<=\d)\s*[-–—~]\s*(?=\d)|"
        r"\b(?:about|around|approx(?:imately)?|roughly|nearly)\b)",
        raw,
    ):
        return None
    match = _EXACT_PROPERTY_SCALAR.fullmatch(raw)
    if match is None:
        return None
    try:
        number = float(match.group("number"))
    except ValueError:
        return None
    if not math.isfinite(number):
        return None
    declared = _generic_unit_key(fact.data.get("unit_raw"))
    literal = _generic_unit_key(match.group("unit"))
    if declared and literal and declared != literal:
        return None
    unit = declared or literal
    if not unit or unit in {"unknown", "notreported", "n a"}:
        return None
    return number, unit


def _fact_owner_coordinate(
    fact: AxisFact, graph: OwnerGraph
) -> tuple[str, str, str] | None:
    """Resolve one existing owner and retain role/nature for compatibility."""

    record = build_promotion_records([fact])[0]
    resolution = resolve_record_owner(record, graph)
    if len(resolution.owner_ids) != 1:
        return None
    node = graph.node(resolution.owner_ids[0])
    return node.owner_id, node.role, node.data_nature


def _property_owner_coordinate(
    fact: PropertyFact, graph: OwnerGraph
) -> tuple[str, str, str] | None:
    return _fact_owner_coordinate(fact, graph)


def _property_metadata_compatible(left: PropertyFact, right: PropertyFact) -> bool:
    if _fact_material_state(left) != _fact_material_state(right):
        return False
    for key in _PROPERTY_COORDINATE_FIELDS:
        left_value = _reported_state(left.data.get(key))
        right_value = _reported_state(right.data.get(key))
        if left_value and right_value and left_value != right_value:
            return False
    return True


def _numbered_table_block(
    block: _SourceBlock, source_lines: Sequence[str]
) -> tuple[str, str] | None:
    """Bind a Markdown table block to one nearest explicit caption number."""

    start_index = max(0, block.start_line - 1)
    matches: list[tuple[str, str]] = []
    for index in range(start_index - 1, max(-1, start_index - 7), -1):
        line = str(source_lines[index] or "").strip()
        if not line:
            continue
        if line.startswith("#") or line.startswith("|"):
            break
        caption = _EXPLICIT_NUMBERED_TABLE_CITATION.search(line)
        if caption and re.match(r"(?i)^\s*table\s*\d+", line):
            matches.append((caption.group("number").casefold(), line))
            break
    return matches[0] if len(matches) == 1 else None


def _cell_exact_scalar(cell: str) -> tuple[float, str] | None:
    match = _EXACT_PROPERTY_SCALAR.fullmatch(str(cell or "").strip())
    if match is None:
        return None
    try:
        number = float(match.group("number"))
    except ValueError:
        return None
    return number, _generic_unit_key(match.group("unit"))


def _unique_table_property_coordinate(
    fact: PropertyFact,
    *,
    block: _SourceBlock,
    table_number: str,
    caption: str,
    source_lines: Sequence[str],
) -> dict[str, Any] | None:
    """Prove one owner/value cell inside one numbered source table."""

    scalar = _exact_property_scalar(fact)
    if scalar is None:
        return None
    value, unit = scalar
    evidence = [normalize_evidence_text(row) for row in _fact_evidence(fact)]
    evidence = [row for row in evidence if row]
    coordinates: list[dict[str, Any]] = []
    for line_number in range(block.start_line, block.end_line + 1):
        raw_line = str(source_lines[line_number - 1] or "").strip()
        if not raw_line.startswith("|"):
            continue
        normalized_line = normalize_evidence_text(raw_line)
        if evidence and not any(
            row == normalized_line or row in normalized_line
            for row in evidence
        ):
            continue
        if not _literal_mention(raw_line, fact.sample_id_raw):
            continue
        cells = [cell.strip() for cell in raw_line.strip("|").split("|")]
        for column_index, cell in enumerate(cells):
            parsed = _cell_exact_scalar(cell)
            if parsed is None:
                continue
            cell_value, cell_unit = parsed
            if not math.isclose(cell_value, value, rel_tol=1e-12, abs_tol=1e-12):
                continue
            if cell_unit and cell_unit != unit:
                continue
            coordinates.append(
                {
                    "table_number": table_number,
                    "table_caption": caption,
                    "source_block_key": block.key,
                    "line": line_number,
                    "column_index": column_index,
                    "row": raw_line,
                    "cell": cell,
                    "value": value,
                    "unit": unit,
                }
            )
    return coordinates[0] if len(coordinates) == 1 else None


def _explicit_table_citation(
    record: PromotionRecord, block: _SourceBlock | None = None
) -> str | None:
    evidence = [*record.evidence]
    if block is not None:
        # An extraction response may quote only the owner/value tail (for example
        # ``0.21% for PL sample``) even though its uniquely resolved source
        # paragraph starts with ``Table 2 indicates ...``.  The complete
        # bounded block is source evidence, not a nearest-table guess.
        evidence.append(block.normalized_text)
    numbers = {
        match.group("number").casefold()
        for row in evidence
        for match in _EXPLICIT_NUMBERED_TABLE_CITATION.finditer(row)
    }
    return next(iter(numbers)) if len(numbers) == 1 else None


def _unique_table_scalar_coordinate(
    fact: AxisFact,
    *,
    scalar: tuple[float, str],
    block: _SourceBlock,
    table_number: str,
    caption: str,
    source_lines: Sequence[str],
) -> dict[str, Any] | None:
    """Prove one exact owner/value cell for any axis fact carried by a table."""

    value, unit = scalar
    evidence = [normalize_evidence_text(row) for row in _fact_evidence(fact)]
    evidence = [row for row in evidence if row]
    coordinates: list[dict[str, Any]] = []
    for line_number in range(block.start_line, block.end_line + 1):
        raw_line = str(source_lines[line_number - 1] or "").strip()
        if not raw_line.startswith("|"):
            continue
        normalized_line = normalize_evidence_text(raw_line)
        if evidence and not any(
            row == normalized_line or row in normalized_line
            for row in evidence
        ):
            continue
        if not _literal_mention(raw_line, fact.sample_id_raw):
            continue
        cells = [cell.strip() for cell in raw_line.strip("|").split("|")]
        for column_index, cell in enumerate(cells):
            parsed = _cell_exact_scalar(cell)
            if parsed is None:
                continue
            cell_value, cell_unit = parsed
            if not math.isclose(cell_value, value, rel_tol=1e-12, abs_tol=1e-12):
                continue
            if cell_unit and cell_unit != unit:
                continue
            coordinates.append(
                {
                    "table_number": table_number,
                    "table_caption": caption,
                    "source_block_key": block.key,
                    "line": line_number,
                    "column_index": column_index,
                    "row": raw_line,
                    "cell": cell,
                    "value": value,
                    "unit": unit,
                }
            )
    return coordinates[0] if len(coordinates) == 1 else None


def _exact_structure_claim_scalar(
    value_raw: Any, unit_raw: Any
) -> tuple[float, str] | None:
    """Return the same exact scalar contract used for Property candidates."""

    raw = str(value_raw or "").strip()
    if re.search(
        r"(?ix)(?:±|\+/-|\\pm|[<>≥≤]|(?<=\d)\s*[-–—~]\s*(?=\d)|"
        r"\b(?:about|around|approx(?:imately)?|roughly|nearly)\b)",
        raw,
    ):
        return None
    match = _EXACT_PROPERTY_SCALAR.fullmatch(raw)
    if match is None:
        return None
    try:
        number = float(match.group("number"))
    except ValueError:
        return None
    if not math.isfinite(number):
        return None
    declared = _generic_unit_key(unit_raw)
    literal = _generic_unit_key(match.group("unit"))
    if declared and literal and declared != literal:
        return None
    unit = declared or literal
    if not unit or unit in {"unknown", "notreported", "n a"}:
        return None
    return number, unit


def _matching_structure_table_claim(
    property_fact: PropertyFact,
    structure_fact: StructureFact,
) -> tuple[float, str] | None:
    """Return one exact Structure feature matching the Property semantic/value."""

    property_scalar = _exact_property_scalar(property_fact)
    if property_scalar is None:
        return None
    matches: list[tuple[float, str]] = []
    for name, value, unit in _dominant_axis_numeric_claims(structure_fact):
        scalar = _exact_structure_claim_scalar(value, unit)
        if (
            scalar == property_scalar
            and _property_names_structure_feature(
                property_fact.data.get("property_name_raw"), name
            )
        ):
            matches.append(scalar)
    return matches[0] if len(matches) == 1 else None


def _property_richness(
    fact: PropertyFact, *, explicit_table_citation: bool, table_coordinate: bool
) -> tuple[int, int, int, int]:
    metadata_count = sum(
        bool(_reported_state(fact.data.get(key)))
        for key in _PROPERTY_COORDINATE_FIELDS
    )
    state_count = int(bool(_fact_material_state(fact)))
    return (
        metadata_count,
        state_count,
        int(explicit_table_citation),
        int(table_coordinate),
    )


def _merge_same_numbered_table_property_duplicates(
    anchors: Sequence[InventoryAnchor],
    facts: Sequence[AxisFact],
    source_text: str,
) -> tuple[list[AxisFact], list[PromotionIssue]]:
    """Merge one exact table/prose Property duplicate with reversible audit."""

    graph = build_owner_graph(anchors)
    if not graph.nodes:
        return list(facts), []
    source_lines = str(source_text or "").splitlines()
    blocks = _source_blocks(source_text)
    block_by_key = {block.key: block for block in blocks}
    records = build_promotion_records(facts)
    eligible: list[
        tuple[
            PromotionRecord,
            tuple[float, str],
            tuple[str, str, str],
            str,
            Literal["prose", "table", "unresolved"],
            bool,
        ]
    ] = []
    for record in records:
        fact = record.fact
        if not isinstance(fact, PropertyFact) or is_core_tensile_property_name(
            fact.data.get("property_name_raw")
        ):
            continue
        scalar = _exact_property_scalar(fact)
        owner = _property_owner_coordinate(fact, graph)
        if scalar is None or owner is None:
            continue
        source_key, source_kind, ambiguous = _record_source_binding(record, blocks)
        if ambiguous or source_kind not in {"prose", "table"}:
            continue
        eligible.append(
            (record, scalar, owner, source_key, source_kind, ambiguous)
        )

    grouped: dict[tuple[Any, ...], list[tuple[Any, ...]]] = {}
    for row in eligible:
        record, scalar, owner, _, _, _ = row
        fact = record.fact
        grouped.setdefault(
            (
                owner,
                _identity_text(fact.sample_id_raw),
                _fact_material_state(fact),
                _scientific_fold(fact.data.get("property_name_raw")),
                scalar,
            ),
            [],
        ).append(row)

    removed: set[int] = set()
    replacements: dict[int, AxisFact] = {}
    same_axis_handled: set[int] = set()
    issues: list[PromotionIssue] = []
    for group_key, rows in sorted(
        grouped.items(), key=lambda item: json.dumps(item[0], ensure_ascii=False)
    ):
        if len(rows) != 2:
            continue
        table_rows = [row for row in rows if row[4] == "table"]
        prose_rows = [row for row in rows if row[4] == "prose"]
        if len(table_rows) != 1 or len(prose_rows) != 1:
            continue
        table_record, _, owner, table_key, _, _ = table_rows[0]
        prose_record, _, _, prose_key, _, _ = prose_rows[0]
        table_fact = table_record.fact
        prose_fact = prose_record.fact
        if not isinstance(table_fact, PropertyFact) or not isinstance(
            prose_fact, PropertyFact
        ):
            continue
        if not _property_metadata_compatible(table_fact, prose_fact):
            continue
        table_block = block_by_key.get(table_key)
        if table_block is None:
            continue
        numbered = _numbered_table_block(table_block, source_lines)
        if numbered is None:
            continue
        table_number, caption = numbered
        cited_number = _explicit_table_citation(prose_record)
        if cited_number != table_number:
            continue
        if any(
            _INDEPENDENT_PROPERTY_MEASUREMENT.search(evidence)
            for evidence in prose_record.evidence
        ):
            continue
        coordinate = _unique_table_property_coordinate(
            table_fact,
            block=table_block,
            table_number=table_number,
            caption=caption,
            source_lines=source_lines,
        )
        if coordinate is None:
            continue

        ranked = [
            (
                _property_richness(
                    table_fact,
                    explicit_table_citation=False,
                    table_coordinate=True,
                ),
                table_record,
            ),
            (
                _property_richness(
                    prose_fact,
                    explicit_table_citation=True,
                    table_coordinate=False,
                ),
                prose_record,
            ),
        ]
        best_score = max(score for score, _ in ranked)
        survivors = [record for score, record in ranked if score == best_score]
        if len(survivors) != 1:
            continue
        survivor_record = survivors[0]
        loser_record = (
            prose_record if survivor_record is table_record else table_record
        )
        loser_score = next(
            score for score, record in ranked if record is loser_record
        )
        if best_score[0] <= loser_score[0]:
            # Citation and cell coordinates prove the relation, but neither is
            # intrinsically richer than the other.  Require a strict metadata
            # advantage so equal-detail records remain separate for review.
            continue
        # A prose survivor must add actual source metadata, not merely win
        # because it repeats the table number.  This prevents a generic nearby
        # summary from eclipsing the unique source cell.
        if survivor_record is prose_record and not any(
            _reported_state(prose_fact.data.get(key))
            and not _reported_state(table_fact.data.get(key))
            for key in _PROPERTY_COORDINATE_FIELDS
        ):
            continue
        survivor_before = survivor_record.fact
        survivor_after = _with_merged_evidence(
            survivor_record,
            [table_record, prose_record],
            source_text,
        )
        same_axis_handled.update(
            {id(table_record.fact), id(prose_record.fact)}
        )
        removed.add(id(loser_record.fact))
        replacements[id(survivor_record.fact)] = survivor_after
        issues.append(
            _promotion_issue(
                loser_record.fact,
                code="promotion_same_table_property_duplicate_merged",
                message=(
                    "An exact non-tensile Property repeated in prose with an "
                    "explicit citation to the same numbered source table was "
                    "merged into the uniquely richer source-proven record."
                ),
                expected={
                    "same_numbered_table": True,
                    "unique_owner_value_cell": True,
                    "exact_owner_state_role_nature_semantic_value_unit": True,
                    "unique_richer_survivor": True,
                    "audit_preserved": True,
                },
                actual={
                    "removed": loser_record.fact.model_dump(),
                    "survivor_before": survivor_before.model_dump(),
                    "survivor_after": survivor_after.model_dump(),
                    "source_relation": {
                        "table_number": table_number,
                        "table_caption": caption,
                        "table_source_block_key": table_key,
                        "prose_source_block_key": prose_key,
                        "prose_explicit_citation": cited_number,
                        "unique_table_coordinate": coordinate,
                    },
                    "comparison": {
                        "group_key": list(group_key),
                        "owner_id": owner[0],
                        "owner_role": owner[1],
                        "owner_data_nature": owner[2],
                        "table_richness": list(ranked[0][0]),
                        "prose_richness": list(ranked[1][0]),
                        "survivor_claim_id": survivor_record.claim_id,
                        "removed_claim_id": loser_record.claim_id,
                        "unique_richer_survivor": True,
                        "owner_invented": False,
                    },
                },
                evidence=list(survivor_after.source_evidence),
                suggested_action=(
                    "Review only if the prose reports an independent repeat "
                    "measurement rather than summarizing the cited table."
                ),
            )
        )

    # An extraction response can validly model a physical measurement such as porosity as
    # a Structure feature in the literal table while also emitting the prose
    # sentence that summarizes that same table as a Property.  The existing
    # wrong-axis gate intentionally requires one source block, so it cannot see
    # this explicit table/prose relation.  Complete only that proven relation:
    # preserve the richer table Structure carrier and quarantine the redundant
    # non-core Property.  No Structure feature is deleted or synthesized.
    structure_rows: list[
        tuple[
            PromotionRecord,
            tuple[str, str, str],
            str,
            _SourceBlock,
            str,
            str,
        ]
    ] = []
    for record in records:
        fact = record.fact
        if not (
            isinstance(fact, StructureFact)
            and fact.fact_type == "structure_observation"
            and _dominant_axis_numeric_claims(fact)
        ):
            continue
        owner = _fact_owner_coordinate(fact, graph)
        if owner is None:
            continue
        source_key, source_kind, ambiguous = _record_source_binding(
            record, blocks
        )
        if ambiguous or source_kind != "table":
            continue
        table_block = block_by_key.get(source_key)
        if table_block is None:
            continue
        numbered = _numbered_table_block(table_block, source_lines)
        if numbered is None:
            continue
        table_number, caption = numbered
        structure_rows.append(
            (
                record,
                owner,
                source_key,
                table_block,
                table_number,
                caption,
            )
        )

    for row in eligible:
        property_record, _, property_owner, prose_key, source_kind, _ = row
        property_fact = property_record.fact
        if (
            not isinstance(property_fact, PropertyFact)
            or source_kind != "prose"
            or id(property_fact) in same_axis_handled
            or id(property_fact) in removed
        ):
            continue
        if any(
            _reported_state(property_fact.data.get(key))
            for key in (
                "test_condition_raw",
                "test_standard_raw",
                "test_specimen_raw",
            )
        ):
            # A condition-bearing Property may be a distinct measurement even
            # when its central value equals a table cell.
            continue
        prose_block = block_by_key.get(prose_key)
        if prose_block is None:
            continue
        cited_number = _explicit_table_citation(property_record, prose_block)
        if cited_number is None or _INDEPENDENT_PROPERTY_MEASUREMENT.search(
            prose_block.normalized_text
        ):
            continue

        matches: list[
            tuple[
                PromotionRecord,
                tuple[str, str, str],
                str,
                _SourceBlock,
                str,
                str,
                tuple[float, str],
                dict[str, Any],
            ]
        ] = []
        for (
            structure_record,
            structure_owner,
            table_key,
            table_block,
            table_number,
            caption,
        ) in structure_rows:
            structure_fact = structure_record.fact
            assert isinstance(structure_fact, StructureFact)
            if (
                table_number != cited_number
                or structure_owner != property_owner
                or _fact_material_state(structure_fact)
                != _fact_material_state(property_fact)
            ):
                continue
            scalar = _matching_structure_table_claim(
                property_fact, structure_fact
            )
            if scalar is None:
                continue
            coordinate = _unique_table_scalar_coordinate(
                structure_fact,
                scalar=scalar,
                block=table_block,
                table_number=table_number,
                caption=caption,
                source_lines=source_lines,
            )
            if coordinate is None:
                continue
            matches.append(
                (
                    structure_record,
                    structure_owner,
                    table_key,
                    table_block,
                    table_number,
                    caption,
                    scalar,
                    coordinate,
                )
            )
        if len(matches) != 1:
            continue

        (
            structure_record,
            structure_owner,
            table_key,
            _,
            table_number,
            caption,
            scalar,
            coordinate,
        ) = matches[0]
        structure_fact = structure_record.fact
        assert isinstance(structure_fact, StructureFact)
        survivor_before = structure_fact
        survivor_after = _with_combined_fact_evidence(
            structure_fact,
            [structure_fact, property_fact],
            source_text,
        )
        removed.add(id(property_fact))
        replacements[id(structure_fact)] = survivor_after
        issues.append(
            _promotion_issue(
                property_fact,
                code=(
                    "promotion_same_table_wrong_axis_property_duplicate_quarantined"
                ),
                message=(
                    "A non-core Property copied one exact Structure measurement "
                    "from prose explicitly summarizing the same numbered table; "
                    "the unique table Structure carrier was retained."
                ),
                expected={
                    "same_numbered_table": True,
                    "dominant_axis": "structure",
                    "unique_owner_value_cell": True,
                    "exact_owner_state_role_nature_semantic_value_unit": True,
                    "property_copy": False,
                    "audit_preserved": True,
                },
                actual={
                    "removed": property_fact.model_dump(),
                    "survivor_before": survivor_before.model_dump(),
                    "survivor_after": survivor_after.model_dump(),
                    "source_relation": {
                        "table_number": table_number,
                        "table_caption": caption,
                        "table_source_block_key": table_key,
                        "prose_source_block_key": prose_key,
                        "prose_explicit_citation": cited_number,
                        "unique_table_coordinate": coordinate,
                    },
                    "comparison": {
                        "property_claim_id": property_record.claim_id,
                        "survivor_claim_id": structure_record.claim_id,
                        "owner_id": structure_owner[0],
                        "owner_role": structure_owner[1],
                        "owner_data_nature": structure_owner[2],
                        "scalar": list(scalar),
                        "owner_invented": False,
                    },
                },
                evidence=list(survivor_after.source_evidence),
                suggested_action=(
                    "Review only if the prose reports a separate conditioned "
                    "measurement rather than summarizing the cited table."
                ),
            )
        )

    output = [
        replacements.get(id(fact), fact)
        for fact in facts
        if id(fact) not in removed
    ]
    issues.sort(
        key=lambda issue: (
            issue.code,
            _identity_text(issue.sample_id_raw),
            json.dumps(issue.actual, ensure_ascii=False, sort_keys=True),
        )
    )
    return output, issues


def _statistical_shadow_base_name(value: Any) -> str:
    match = _STATISTICAL_SHADOW_SUFFIX.fullmatch(str(value or ""))
    return str(match.group("base")).strip() if match else ""


def _table_row_label(value: str) -> str:
    if not str(value).lstrip().startswith("|"):
        return ""
    cells = [cell.strip() for cell in str(value).strip().strip("|").split("|")]
    return _scientific_fold(cells[0]) if cells else ""


def _statistical_evidence_rows(fact: PropertyFact) -> tuple[str, ...]:
    return tuple(
        row
        for row in _fact_evidence(fact)
        if _table_row_label(row) in _STATISTICAL_TABLE_ROW_LABELS
    )


def _source_line_indices(source_text: str, line: str) -> tuple[int, ...]:
    needle = normalize_evidence_text(line)
    if not needle:
        return ()
    return tuple(
        index
        for index, source_line in enumerate(str(source_text or "").splitlines())
        if normalize_evidence_text(source_line) == needle
    )


def _fact_table_row_indices(fact: PropertyFact, source_text: str) -> set[int]:
    positions: set[int] = set()
    for row in _fact_evidence(fact):
        if not str(row).lstrip().startswith("|"):
            continue
        label = _table_row_label(row)
        if label in _STATISTICAL_TABLE_ROW_LABELS:
            continue
        positions.update(_source_line_indices(source_text, row))
    return positions


def _same_statistical_property_context(
    mean: PropertyFact,
    shadow: PropertyFact,
    *,
    base_name: str,
) -> bool:
    if _identity_text(mean.sample_id_raw) != _identity_text(shadow.sample_id_raw):
        return False
    if _scientific_fold(mean.data.get("property_name_raw")) != _scientific_fold(
        base_name
    ):
        return False
    if _scientific_compact(mean.data.get("unit_raw")) != _scientific_compact(
        shadow.data.get("unit_raw")
    ):
        return False
    if _fact_material_state(mean) != _fact_material_state(shadow):
        return False
    for key in ("test_method_raw", "test_condition_raw", "test_specimen_raw"):
        if _scientific_fold(mean.data.get(key)) != _scientific_fold(
            shadow.data.get(key)
        ):
            return False
    return _scientific_fold(mean.data.get("data_source")) == "table"


def _value_with_uncertainty(mean: Any, deviation: Any) -> str:
    mean_text = str(mean or "").strip()
    deviation_text = str(deviation or "").strip()
    if not mean_text or not deviation_text:
        return mean_text
    mean_numbers = _numeric_tokens(mean_text)
    deviation_numbers = _numeric_tokens(deviation_text)
    if (
        ("±" in mean_text or "+/-" in mean_text or r"\pm" in mean_text)
        and deviation_numbers
        and deviation_numbers[-1] in mean_numbers
    ):
        return mean_text
    return f"{mean_text} ± {deviation_text}"


def _with_combined_fact_evidence(
    survivor: AxisFact,
    members: Sequence[AxisFact],
    source_text: str,
    *,
    data_updates: dict[str, Any] | None = None,
) -> AxisFact:
    records = build_promotion_records(members)
    evidence = _ordered_evidence(records, source_text)
    data = deepcopy(survivor.data)
    if data_updates:
        data.update(deepcopy(data_updates))
    if "source_evidence" in data:
        data["source_evidence"] = list(evidence)
    return survivor.model_copy(
        deep=True,
        update={
            "data": data,
            "source_evidence": list(evidence),
            "confidence": max(member.confidence for member in members),
        },
    )


def _absorb_property_statistical_shadows(
    facts: Sequence[AxisFact], source_text: str
) -> tuple[list[AxisFact], list[PromotionIssue]]:
    """Bind table Std. rows to the immediately preceding reported mean."""

    means = [
        fact
        for fact in facts
        if isinstance(fact, PropertyFact)
        and not _statistical_shadow_base_name(
            fact.data.get("property_name_raw")
        )
    ]
    shadows = [
        fact
        for fact in facts
        if isinstance(fact, PropertyFact)
        and _statistical_shadow_base_name(fact.data.get("property_name_raw"))
        and _scientific_fold(fact.data.get("data_source")) == "table"
        and _statistical_evidence_rows(fact)
    ]
    if not shadows:
        return list(facts), []

    proposed: dict[int, tuple[PropertyFact, PropertyFact]] = {}
    mean_claims: dict[int, list[PropertyFact]] = {}
    for shadow in shadows:
        statistical_rows = _statistical_evidence_rows(shadow)
        shadow_positions = {
            position
            for row in statistical_rows
            for position in _source_line_indices(source_text, row)
        }
        base_name = _statistical_shadow_base_name(
            shadow.data.get("property_name_raw")
        )
        matches = [
            mean
            for mean in means
            if len(shadow_positions) == 1
            and _same_statistical_property_context(
                mean, shadow, base_name=base_name
            )
            and (next(iter(shadow_positions)) - 1)
            in _fact_table_row_indices(mean, source_text)
        ]
        if len(matches) == 1:
            proposed[id(shadow)] = (shadow, matches[0])
            mean_claims.setdefault(id(matches[0]), []).append(shadow)

    replacements: dict[int, PropertyFact] = {}
    removed_shadow_ids = {id(shadow) for shadow in shadows}
    issues: list[PromotionIssue] = []
    for shadow in shadows:
        binding = proposed.get(id(shadow))
        if binding is not None and len(mean_claims[id(binding[1])]) == 1:
            _, mean = binding
            after = _with_combined_fact_evidence(
                mean,
                [mean, shadow],
                source_text,
                data_updates={
                    "value_raw": _value_with_uncertainty(
                        mean.data.get("value_raw"),
                        shadow.data.get("value_raw"),
                    )
                },
            )
            assert isinstance(after, PropertyFact)
            replacements[id(mean)] = after
            issues.append(
                _promotion_issue(
                    shadow,
                    code="promotion_property_statistical_shadow_absorbed",
                    message=(
                        "An adjacent table standard-deviation row was bound to "
                        "its same-owner reported mean instead of becoming a "
                        "separate Property."
                    ),
                    expected={
                        "independent_property": False,
                        "adjacent_mean_binding": True,
                        "audit_preserved": True,
                    },
                    actual={
                        "removed": shadow.model_dump(),
                        "survivor_before": mean.model_dump(),
                        "survivor_after": after.model_dump(),
                        "reason": "adjacent_table_standard_deviation",
                    },
                    evidence=list(after.source_evidence),
                )
            )
            continue
        issues.append(
            _promotion_issue(
                shadow,
                code="promotion_property_statistical_shadow_quarantined",
                message=(
                    "A table standard-deviation row could not be uniquely bound "
                    "to one adjacent same-owner mean and was isolated."
                ),
                expected={
                    "independent_property": False,
                    "unique_adjacent_mean_binding": True,
                    "audit_preserved": True,
                },
                actual={
                    "removed": shadow.model_dump(),
                    "reason": "missing_or_ambiguous_adjacent_mean",
                },
            )
        )

    accepted = [
        replacements.get(id(fact), fact)
        for fact in facts
        if id(fact) not in removed_shadow_ids
    ]
    return accepted, issues


def _numeric_claim_values_compatible(left: Any, right: Any) -> bool:
    if _scientific_compact(left) == _scientific_compact(right):
        return True
    left_numbers = _numeric_tokens(left)
    right_numbers = _numeric_tokens(right)
    if not left_numbers or not right_numbers or left_numbers[0] != right_numbers[0]:
        return False
    if len(left_numbers) == len(right_numbers):
        return left_numbers == right_numbers
    longer = str(left if len(left_numbers) > len(right_numbers) else right)
    shorter_numbers, longer_numbers = sorted(
        (left_numbers, right_numbers), key=len
    )
    return (
        len(shorter_numbers) == 1
        and ("±" in longer or "+/-" in longer or r"\pm" in longer)
        and shorter_numbers[0] == longer_numbers[0]
    )


def _measurement_name_tokens(value: Any) -> frozenset[str]:
    return frozenset(
        token
        for token in _scientific_fold(value).split()
        if token not in _MEASUREMENT_NAME_MODIFIERS
    )


def _property_names_composition_component(
    property_name: Any, component_name: Any
) -> bool:
    property_tokens = frozenset(_scientific_fold(property_name).split())
    component_tokens = frozenset(_scientific_fold(component_name).split())
    return bool(component_tokens) and component_tokens <= property_tokens and bool(
        property_tokens & _COMPOSITION_PROPERTY_DESCRIPTORS
    )


def _property_names_structure_feature(
    property_name: Any, feature_name: Any
) -> bool:
    property_tokens = _measurement_name_tokens(property_name)
    feature_tokens = _measurement_name_tokens(feature_name)
    return bool(property_tokens and feature_tokens) and (
        property_tokens <= feature_tokens or feature_tokens <= property_tokens
    )


def _dominant_axis_numeric_claims(
    fact: AxisFact,
) -> tuple[tuple[str, Any, Any], ...]:
    claims: list[tuple[str, Any, Any]] = []
    if isinstance(fact, CompositionFact) and fact.fact_type == "composition_observation":
        for component in fact.data.get("components") or []:
            if not isinstance(component, dict):
                continue
            if _scientific_fold(component.get("value_kind")) not in {
                "inequality",
                "range",
                "scalar",
                "uncertainty",
            }:
                continue
            claims.append(
                (
                    str(component.get("name_raw") or ""),
                    component.get("value_raw"),
                    component.get("unit_raw"),
                )
            )
    elif isinstance(fact, StructureFact) and fact.fact_type == "structure_observation":
        for feature in fact.data.get("features") or []:
            if isinstance(feature, dict) and _is_quantitative_structure_feature(feature):
                claims.append(
                    (
                        str(feature.get("feature_name_raw") or ""),
                        feature.get("value_raw"),
                        feature.get("unit_raw"),
                    )
                )
        for entity in fact.data.get("entities") or []:
            if not isinstance(entity, dict):
                continue
            for feature in entity.get("features") or []:
                if isinstance(feature, dict) and _is_quantitative_structure_feature(feature):
                    claims.append(
                        (
                            str(feature.get("feature_name_raw") or ""),
                            feature.get("value_raw"),
                            feature.get("unit_raw"),
                        )
                    )
    return tuple(claims)


def _structure_unit_completion_from_property(
    structure: StructureFact, property_fact: PropertyFact
) -> StructureFact | None:
    """Copy one source-literal unit into one otherwise identical Structure feature."""

    property_name = property_fact.data.get("property_name_raw")
    property_value = property_fact.data.get("value_raw")
    property_unit = property_fact.data.get("unit_raw")
    if _scientific_fold(property_unit) in _UNREPORTED:
        return None
    evidence = _fact_evidence(property_fact)
    joined = _structure_unit_compact("\n".join(evidence))
    literal = _structure_unit_compact(property_value) + _structure_unit_compact(
        property_unit
    )
    if not literal or literal not in joined:
        return None

    matches: list[tuple[str, int, int | None]] = []
    for feature_index, feature in enumerate(structure.data.get("features") or []):
        if not isinstance(feature, dict) or not _is_quantitative_structure_feature(
            feature
        ):
            continue
        if (
            _property_names_structure_feature(
                property_name, feature.get("feature_name_raw")
            )
            and _numeric_claim_values_compatible(
                property_value, feature.get("value_raw")
            )
            and _scientific_fold(feature.get("unit_raw")) in _UNREPORTED
        ):
            matches.append(("features", feature_index, None))
    for entity_index, entity in enumerate(structure.data.get("entities") or []):
        if not isinstance(entity, dict):
            continue
        for feature_index, feature in enumerate(entity.get("features") or []):
            if not isinstance(feature, dict) or not _is_quantitative_structure_feature(
                feature
            ):
                continue
            if (
                _property_names_structure_feature(
                    property_name, feature.get("feature_name_raw")
                )
                and _numeric_claim_values_compatible(
                    property_value, feature.get("value_raw")
                )
                and _scientific_fold(feature.get("unit_raw")) in _UNREPORTED
            ):
                matches.append(("entities", entity_index, feature_index))
    if len(matches) != 1:
        return None

    data = deepcopy(structure.data)
    container, index, nested_index = matches[0]
    if container == "features":
        feature = data["features"][index]
    else:
        assert nested_index is not None
        feature = data["entities"][index]["features"][nested_index]
    feature["unit_raw"] = property_unit
    return structure.model_copy(deep=True, update={"data": data})


def _quarantine_wrong_axis_property_duplicates(
    facts: Sequence[AxisFact], source_text: str
) -> tuple[list[AxisFact], list[PromotionIssue]]:
    """Prefer Composition/Structure when Property copies the same assertion."""

    blocks = _source_blocks(source_text)
    bindings: dict[int, tuple[str, bool]] = {}
    for record in build_promotion_records(facts):
        source_key, _, ambiguous = _record_source_binding(record, blocks)
        bindings[id(record.fact)] = (source_key, ambiguous)

    dominants = [
        fact
        for fact in facts
        if isinstance(fact, (CompositionFact, StructureFact))
        and _dominant_axis_numeric_claims(fact)
    ]
    removed: set[int] = set()
    replacements: dict[int, AxisFact] = {}
    issues: list[PromotionIssue] = []
    for fact in facts:
        if not isinstance(fact, PropertyFact):
            continue
        property_binding = bindings.get(id(fact))
        if property_binding is None or property_binding[1]:
            continue
        property_name = fact.data.get("property_name_raw")
        property_value = fact.data.get("value_raw")
        property_unit = fact.data.get("unit_raw")
        matches: list[tuple[AxisFact, StructureFact | None]] = []
        for dominant in dominants:
            dominant_binding = bindings.get(id(dominant))
            if dominant_binding is None or dominant_binding[1]:
                continue
            if property_binding[0] != dominant_binding[0]:
                continue
            if _identity_text(fact.sample_id_raw) != _identity_text(
                dominant.sample_id_raw
            ):
                continue
            if _fact_material_state(fact) != _fact_material_state(dominant):
                continue
            for name, value, unit in _dominant_axis_numeric_claims(dominant):
                name_matches = (
                    _property_names_composition_component(property_name, name)
                    if isinstance(dominant, CompositionFact)
                    else _property_names_structure_feature(property_name, name)
                )
                if not (
                    name_matches
                    and _numeric_claim_values_compatible(property_value, value)
                ):
                    continue
                completed: StructureFact | None = None
                units_match = _scientific_compact(
                    property_unit
                ) == _scientific_compact(unit)
                if (
                    not units_match
                    and isinstance(dominant, StructureFact)
                    and _scientific_fold(unit) in _UNREPORTED
                ):
                    completed = _structure_unit_completion_from_property(
                        dominant, fact
                    )
                if units_match or completed is not None:
                    matches.append((dominant, completed))
                    break
        unique_matches = {id(row): (row, completed) for row, completed in matches}
        if len(unique_matches) != 1:
            continue
        dominant, completed = next(iter(unique_matches.values()))
        removed.add(id(fact))
        if completed is not None:
            after = _with_combined_fact_evidence(
                completed,
                [dominant, fact],
                source_text,
            )
            replacements[id(dominant)] = after
            issues.append(
                _promotion_issue(
                    fact,
                    code="promotion_wrong_axis_structure_unit_completed",
                    message=(
                        "A wrong-axis Property duplicate supplied the literal unit "
                        "missing from its one matching Structure assertion."
                    ),
                    expected={
                        "dominant_axis": "structure",
                        "source_grounded_unit": True,
                        "property_copy": False,
                        "audit_preserved": True,
                    },
                    actual={
                        "removed": fact.model_dump(),
                        "dominant_before": dominant.model_dump(),
                        "dominant_after": after.model_dump(),
                        "reason": "wrong_axis_unit_completion",
                    },
                    evidence=list(after.source_evidence),
                )
            )
            continue
        issues.append(
            _promotion_issue(
                fact,
                code="promotion_wrong_axis_duplicate_quarantined",
                message=(
                    "A Property repeated the same owner, value, unit, and source "
                    "assertion already represented on its Composition or Structure "
                    "axis."
                ),
                expected={
                    "dominant_axis": dominant.axis,
                    "property_copy": False,
                    "audit_preserved": True,
                },
                actual={
                    "removed": fact.model_dump(),
                    "dominant": dominant.model_dump(),
                    "reason": "same_assertion_wrong_axis_property_copy",
                },
                evidence=list(
                    dict.fromkeys(
                        [*_fact_evidence(dominant), *_fact_evidence(fact)]
                    )
                ),
            )
        )
    return [
        replacements.get(id(fact), fact)
        for fact in facts
        if id(fact) not in removed
    ], issues


def _structure_atomic_keys(fact: StructureFact) -> frozenset[tuple[str, ...]]:
    atoms: set[tuple[str, ...]] = set()
    for entity in fact.data.get("entities") or []:
        if not isinstance(entity, dict):
            continue
        entity_name = _scientific_fold(entity.get("name_raw"))
        entity_type = _scientific_fold(entity.get("entity_type"))
        if entity_name:
            atoms.add(("entity", entity_name, entity_type))
        for feature in entity.get("features") or []:
            if not isinstance(feature, dict):
                continue
            atoms.add(
                (
                    "entity_feature",
                    entity_name,
                    _scientific_fold(feature.get("feature_name_raw")),
                    _scientific_fold(feature.get("value_kind")),
                    _scientific_compact(feature.get("value_raw")),
                    _scientific_compact(feature.get("unit_raw")),
                )
            )
    for feature in fact.data.get("features") or []:
        if not isinstance(feature, dict):
            continue
        atoms.add(
            (
                "feature",
                _scientific_fold(feature.get("feature_name_raw")),
                _scientific_fold(feature.get("value_kind")),
                _scientific_compact(feature.get("value_raw")),
                _scientific_compact(feature.get("unit_raw")),
            )
        )
    return frozenset(atom for atom in atoms if any(atom[1:]))


def _single_top_level_structure_feature(
    fact: AxisFact,
) -> dict[str, Any] | None:
    if not isinstance(fact, StructureFact) or fact.fact_type != "structure_observation":
        return None
    if any(isinstance(row, dict) for row in fact.data.get("entities") or []):
        return None
    features = [
        row for row in fact.data.get("features") or [] if isinstance(row, dict)
    ]
    if len(features) != 1 or not _numeric_tokens(features[0].get("value_raw")):
        return None
    return features[0]


def _structure_unit_compact(value: Any) -> str:
    text = str(value or "")
    text = re.sub(r"\\mu\s*", "u", text, flags=re.IGNORECASE)
    text = text.replace("µ", "u").replace("μ", "u")
    text = re.sub(r"\\circ\s*", "deg", text, flags=re.IGNORECASE)
    return re.sub(r"[^a-z0-9%]+", "", normalize_evidence_text(text))


def _structure_feature_unit_is_grounded(
    feature: dict[str, Any], fact: StructureFact
) -> bool:
    unit = _structure_unit_compact(feature.get("unit_raw"))
    value = _structure_unit_compact(feature.get("value_raw"))
    if not unit or _scientific_fold(feature.get("unit_raw")) in _UNREPORTED:
        return False
    evidence = _feature_evidence(feature, _fact_evidence(fact))
    source = _structure_unit_compact("\n".join(evidence))
    return bool(value and value + unit in source)


def _merge_structure_unit_shadows(
    facts: Sequence[AxisFact], source_text: str
) -> tuple[list[AxisFact], list[PromotionIssue]]:
    """Absorb one unitless copy of a source-identical numeric Structure fact."""

    candidates = [
        fact for fact in facts if _single_top_level_structure_feature(fact) is not None
    ]
    blocks = _source_blocks(source_text)
    grouped: dict[tuple[Any, ...], list[StructureFact]] = {}
    for record in build_promotion_records(candidates):
        fact = record.fact
        assert isinstance(fact, StructureFact)
        feature = _single_top_level_structure_feature(fact)
        assert feature is not None
        source_key, _, ambiguous = _record_source_binding(record, blocks)
        if ambiguous:
            continue
        context = tuple(
            _scientific_fold(fact.data.get(key))
            for key in ("material_state", "region", "location", "orientation")
        )
        grouped.setdefault(
            (
                _identity_text(fact.sample_id_raw),
                source_key,
                _scientific_fold(fact.data.get("structure_kind")),
                context,
                _scientific_fold(feature.get("feature_name_raw")),
                _scientific_compact(feature.get("value_raw")),
                _scientific_fold(feature.get("data_nature")),
            ),
            [],
        ).append(fact)

    removed: set[int] = set()
    replacements: dict[int, StructureFact] = {}
    issues: list[PromotionIssue] = []
    for rows in grouped.values():
        complete: list[StructureFact] = []
        unitless: list[StructureFact] = []
        for fact in rows:
            feature = _single_top_level_structure_feature(fact)
            assert feature is not None
            if _structure_feature_unit_is_grounded(feature, fact):
                complete.append(fact)
            elif _scientific_fold(feature.get("unit_raw")) in _UNREPORTED:
                unitless.append(fact)
        if len(complete) != 1 or not unitless:
            continue
        survivor = complete[0]
        related_losers = [
            loser
            for loser in unitless
            if _related_fact_evidence(loser, survivor)
        ]
        if not related_losers:
            continue
        after = _with_combined_fact_evidence(
            survivor,
            [survivor, *related_losers],
            source_text,
        )
        assert isinstance(after, StructureFact)
        replacements[id(survivor)] = after
        for loser in related_losers:
            removed.add(id(loser))
            issues.append(
                _promotion_issue(
                    loser,
                    code="promotion_structure_unit_shadow_merged",
                    message=(
                        "A unitless duplicate of one numeric Structure assertion "
                        "was absorbed by its source-grounded unit-bearing copy."
                    ),
                    expected={
                        "same_owner_state_assertion": True,
                        "source_grounded_unit": True,
                        "distinct_measurement": False,
                        "audit_preserved": True,
                    },
                    actual={
                        "removed": loser.model_dump(),
                        "survivor_before": survivor.model_dump(),
                        "survivor_after": after.model_dump(),
                        "reason": "same_assertion_unitless_structure_shadow",
                    },
                    evidence=list(after.source_evidence),
                )
            )
    return [
        replacements.get(id(fact), fact)
        for fact in facts
        if id(fact) not in removed
    ], issues


def _related_fact_evidence(left: AxisFact, right: AxisFact) -> bool:
    left_blob = "\n".join(
        normalize_evidence_text(row) for row in _fact_evidence(left)
    )
    right_blob = "\n".join(
        normalize_evidence_text(row) for row in _fact_evidence(right)
    )
    return bool(left_blob and right_blob) and (
        left_blob == right_blob or left_blob in right_blob or right_blob in left_blob
    )


def _merge_strict_structure_subsets(
    facts: Sequence[AxisFact], source_text: str
) -> tuple[list[AxisFact], list[PromotionIssue]]:
    observations = [
        fact
        for fact in facts
        if isinstance(fact, StructureFact)
        and fact.fact_type == "structure_observation"
        and _structure_atomic_keys(fact)
    ]
    blocks = _source_blocks(source_text)
    bindings: dict[int, tuple[str, bool]] = {}
    for record in build_promotion_records(observations):
        source_key, _, ambiguous = _record_source_binding(record, blocks)
        bindings[id(record.fact)] = (source_key, ambiguous)

    richer_for: dict[int, list[StructureFact]] = {}
    for subset in observations:
        subset_binding = bindings.get(id(subset))
        if subset_binding is None or subset_binding[1]:
            continue
        subset_atoms = _structure_atomic_keys(subset)
        for richer in observations:
            if richer is subset:
                continue
            richer_binding = bindings.get(id(richer))
            if richer_binding != subset_binding:
                continue
            if _identity_text(subset.sample_id_raw) != _identity_text(
                richer.sample_id_raw
            ):
                continue
            if _fact_material_state(subset) != _fact_material_state(richer):
                continue
            if _scientific_fold(subset.data.get("structure_kind")) != _scientific_fold(
                richer.data.get("structure_kind")
            ):
                continue
            if _scientific_fold(subset.data.get("source_type")) != _scientific_fold(
                richer.data.get("source_type")
            ):
                continue
            if not _related_fact_evidence(subset, richer):
                continue
            if subset_atoms < _structure_atomic_keys(richer):
                richer_for.setdefault(id(subset), []).append(richer)

    removed: set[int] = set()
    losers_by_survivor: dict[int, list[StructureFact]] = {}
    survivor_by_id: dict[int, StructureFact] = {}
    for subset in observations:
        candidates = richer_for.get(id(subset), [])
        if not candidates:
            continue
        maximal = [
            candidate
            for candidate in candidates
            if not any(
                _structure_atomic_keys(candidate) < _structure_atomic_keys(other)
                for other in candidates
                if other is not candidate
            )
        ]
        unique_maximal = {id(candidate): candidate for candidate in maximal}
        if len(unique_maximal) != 1:
            continue
        survivor = next(iter(unique_maximal.values()))
        removed.add(id(subset))
        survivor_by_id[id(survivor)] = survivor
        losers_by_survivor.setdefault(id(survivor), []).append(subset)

    replacements: dict[int, StructureFact] = {}
    issues: list[PromotionIssue] = []
    for survivor_id, losers in losers_by_survivor.items():
        survivor = survivor_by_id[survivor_id]
        after = _with_combined_fact_evidence(
            survivor,
            [survivor, *losers],
            source_text,
        )
        assert isinstance(after, StructureFact)
        replacements[survivor_id] = after
        for loser in losers:
            issues.append(
                _promotion_issue(
                    loser,
                    code="promotion_richer_assertion_survived",
                    message=(
                        "A strict atomic subset from the same owner and source "
                        "assertion was absorbed by one richer Structure observation."
                    ),
                    expected={
                        "strict_atomic_subset": True,
                        "independent_assertion": False,
                        "audit_preserved": True,
                    },
                    actual={
                        "removed": loser.model_dump(),
                        "survivor_before": survivor.model_dump(),
                        "survivor_after": after.model_dump(),
                        "reason": "same_assertion_strict_atomic_subset",
                    },
                    evidence=list(after.source_evidence),
                )
            )
    accepted = [
        replacements.get(id(fact), fact)
        for fact in facts
        if id(fact) not in removed
    ]
    return accepted, issues


def _reassign_fact_owner(fact: AxisFact, sample_id_raw: str) -> AxisFact:
    """Route an existing fact to one source-explicit inventory owner."""

    data = deepcopy(fact.data)
    if fact.fact_type in {"composition_observation", "structure_observation"}:
        data["sample_id"] = sample_id_raw
    return fact.model_copy(
        deep=True,
        update={"sample_id_raw": sample_id_raw, "data": data},
    )


_DURATION_TOKEN = re.compile(
    r"(?ix)(?<![a-z0-9])(?P<value>\d+(?:\.\d+)?)\s*"
    r"(?P<unit>hours?|hrs?|h|minutes?|mins?|min|seconds?|secs?|sec|s)\b"
)


def _duration_values(value: Any) -> frozenset[float]:
    """Return source-literal durations in seconds for conflict comparison."""

    seconds: set[float] = set()
    for match in _DURATION_TOKEN.finditer(_scientific_fold(value)):
        number = float(match.group("value"))
        unit = match.group("unit").casefold()
        if unit.startswith("h"):
            number *= 3600.0
        elif unit.startswith("m"):
            number *= 60.0
        seconds.add(number)
    return frozenset(seconds)


def _primary_property_condition(value: Any) -> str:
    """Exclude appended method prose when comparing an explicit condition."""

    text = str(value or "").strip()
    if not text:
        return ""
    return re.split(r"\n\s*\n|\s+\|\s+", text, maxsplit=1)[0].strip()


def _route_tensile_state_conflicts(
    anchors: Sequence[InventoryAnchor], facts: Sequence[AxisFact]
) -> tuple[list[AxisFact], list[PromotionIssue]]:
    """Move a condition-conflicting state projection to its existing base owner."""

    graph = build_owner_graph(anchors)
    if not graph.nodes:
        return list(facts), []
    accepted: list[AxisFact] = []
    issues: list[PromotionIssue] = []
    for fact in facts:
        if not isinstance(fact, PropertyFact) or not is_core_tensile_property_name(
            fact.data.get("property_name_raw")
        ):
            accepted.append(fact)
            continue
        owner_nodes = [
            node
            for node in graph.nodes
            if _identity_text(node.sample_id_raw)
            == _identity_text(fact.sample_id_raw)
        ]
        if len(owner_nodes) != 1:
            accepted.append(fact)
            continue
        owner_node = owner_nodes[0]
        owner_context = owner_node.state_raw or owner_node.sample_id_raw
        owner_durations = _duration_values(owner_context)
        primary_condition = _primary_property_condition(
            fact.data.get("test_condition_raw")
        )
        condition_durations = _duration_values(primary_condition)
        if (
            not owner_durations
            or not condition_durations
            or owner_durations & condition_durations
        ):
            accepted.append(fact)
            continue

        bracket_base = re.sub(
            r"\s*\[[^\]]+\]\s*$", "", owner_node.sample_id_raw
        ).strip()
        base_nodes = [
            node
            for node in graph.nodes
            if not node.state_raw
            and node.role == owner_node.role
            and node.data_nature == owner_node.data_nature
            and (
                (
                    bracket_base
                    and _identity_text(node.sample_id_raw)
                    == _identity_text(bracket_base)
                )
                or (
                    owner_node.material_name_raw
                    and _identity_text(node.material_name_raw)
                    == _identity_text(owner_node.material_name_raw)
                )
            )
        ]
        unique_bases = {node.owner_id: node for node in base_nodes}
        if len(unique_bases) != 1:
            accepted.append(fact)
            continue
        base_node = next(iter(unique_bases.values()))
        evidence = _fact_evidence(fact)
        evidence_text = "\n".join(evidence)
        if not _literal_mention(evidence_text, base_node.sample_id_raw):
            accepted.append(fact)
            continue
        if not condition_durations <= _duration_values(evidence_text):
            accepted.append(fact)
            continue
        reassigned = _reassign_fact_owner(fact, base_node.sample_id_raw)
        accepted.append(reassigned)
        issues.append(
            _promotion_issue(
                fact,
                code="promotion_tensile_owner_state_conflict_reassigned",
                message=(
                    "A core-tensile result carried a duration that conflicted "
                    "with its state-specific owner label and was moved to the "
                    "one existing source-named base owner."
                ),
                expected={
                    "owner_condition_compatible": True,
                    "existing_base_owner": base_node.sample_id_raw,
                    "invented_owner": False,
                    "audit_preserved": True,
                },
                actual={
                    "before": fact.model_dump(),
                    "after": reassigned.model_dump(),
                    "conflict_dimension": "duration",
                    "owner_duration_seconds": sorted(owner_durations),
                    "condition_duration_seconds": sorted(condition_durations),
                },
                evidence=evidence,
            )
        )
    return accepted, issues


def _source_owner_nodes(
    support: str,
    graph: OwnerGraph,
) -> tuple[OwnerNode, ...]:
    """Return inventory owners literally named by one source assertion."""

    named = {
        node.owner_id: node
        for node in graph.nodes
        if any(
            _distinctive_owner_label(alias)
            and _literal_mention(support, alias)
            for alias in _owner_evidence_aliases(node.sample_id_raw)
        )
    }
    return tuple(named[key] for key in sorted(named))


_NON_OWNER_LABEL_TOKENS = {
    "alloy",
    "alloys",
    "analysis",
    "area",
    "condition",
    "conditions",
    "grain",
    "grains",
    "material",
    "materials",
    "point",
    "points",
    "powder",
    "powders",
    "region",
    "regions",
    "sample",
    "samples",
    "specimen",
    "specimens",
    "standard",
    "surface",
    "surfaces",
    "wall",
    "walls",
    "zone",
    "zones",
}


def _safe_explicit_owner_label(value: str) -> bool:
    """Reject measurement/descriptor labels that only look like owners."""

    folded = _identity_text(value)
    if not folded:
        return False
    if re.search(r"\b(?:astm|iso|din|ams)\b", folded):
        return False
    # Numeric conditions and table row values are not material identities.
    if re.fullmatch(
        r"(?:[-+]?\d+(?:\.\d+)?(?:\s*[°%a-zμ]+)?(?:\s+\w+)*)",
        folded,
    ):
        return False
    tokens = set(re.findall(r"[a-z0-9μ]+", folded))
    if tokens and tokens <= _NON_OWNER_LABEL_TOKENS:
        return False
    if any(token in {"s", "sec", "min", "h", "hour", "hours"} for token in tokens):
        if not re.search(r"[a-z]{2,}\d|\d[a-z]{2,}", folded):
            return False
    return _distinctive_owner_label(value)


def _safe_source_owner_nodes(
    support: str,
    graph: OwnerGraph,
) -> tuple[OwnerNode, ...]:
    """Return only distinctive inventory labels explicitly present in prose."""

    named = {
        node.owner_id: node
        for node in graph.nodes
        if _safe_explicit_owner_label(node.sample_id_raw)
        and any(
            _literal_mention(support, alias)
            for alias in _owner_evidence_aliases(node.sample_id_raw)
        )
    }
    return tuple(named[key] for key in sorted(named))


def _owner_lineage_matches(left: OwnerNode, right: OwnerNode) -> bool:
    """Return whether two existing owner nodes belong to one material lineage.

    Inventory extraction commonly emits a generic material node alongside
    state-qualified nodes (``Alloy``, ``Alloy [as-built]``, ``Alloy [HIPed]``).
    Only source-declared aliases/material names are compared here; no fuzzy
    chemistry or item-order inference is allowed.
    """

    if left.role != right.role or left.data_nature != right.data_nature:
        return False
    # ``material_name_raw`` is deliberately *not* a lineage key. It is the
    # chemistry/designation shared by many independently tested specimens, so
    # matching on it turns every same-alloy row into a sibling and makes the
    # precision gate quarantine valid facts. A lineage must be anchored by the
    # source sample label itself or by the explicit bracketed state form emitted
    # by the materializer (``A [HIPed]``).
    left_base = _identity_text(
        re.sub(r"\s*\[[^\]]+\]\s*$", "", left.sample_id_raw).strip()
    )
    right_base = _identity_text(
        re.sub(r"\s*\[[^\]]+\]\s*$", "", right.sample_id_raw).strip()
    )
    if left_base and right_base and left_base == right_base:
        return True
    left_material_key = _identity_text(left.material_name_raw)
    right_material_key = _identity_text(right.material_name_raw)
    # A state child may use a compact sample label (``EBAM [as-built]``)
    # while the generic owner carries the expanded label
    # (``EBAM Ti-6Al-4V``).  When the chemistry/material name is identical and
    # one base label is a whole-token prefix of the other, treat the pair as
    # one existing lineage.  The state requirement prevents this from
    # becoming a chemistry-only global join between unrelated specimens.
    if (
        left_material_key
        and left_material_key == right_material_key
        and (left.state_raw or right.state_raw)
    ):
        left_label = _scientific_fold(left_base)
        right_label = _scientific_fold(right_base)
        if (
            left_label
            and right_label
            and (
                left_label == right_label
                or left_label.startswith(right_label + " ")
                or right_label.startswith(left_label + " ")
            )
        ):
            return True
    left_aliases = {
        _identity_text(value)
        for value in (left.sample_id_raw, *left.aliases)
        if _identity_text(value)
        and _identity_text(value) not in {left_material_key, right_material_key}
    }
    right_aliases = {
        _identity_text(value)
        for value in (right.sample_id_raw, *right.aliases)
        if _identity_text(value)
        and _identity_text(value) not in {left_material_key, right_material_key}
    }
    return bool(left_aliases & right_aliases)


def _lineage_state_nodes(
    candidate_nodes: Sequence[OwnerNode], graph: OwnerGraph
) -> tuple[OwnerNode, ...]:
    """Return source-declared state children in the candidates' lineages."""

    states: dict[str, OwnerNode] = {}
    for candidate in candidate_nodes:
        for node in graph.nodes:
            if node.state_raw and _owner_lineage_matches(candidate, node):
                states[node.owner_id] = node
    return tuple(states[key] for key in sorted(states))


def _fact_has_literal_owner_or_state(
    fact: AxisFact,
    graph: OwnerGraph,
    *,
    current_only: bool = False,
) -> tuple[OwnerNode, ...]:
    """Find existing owners literally present in a candidate's own evidence."""

    support = "\n".join(_fact_evidence(fact))
    nodes = _safe_source_owner_nodes(support, graph)
    # A generic sample label is copied into every state node's alias set.  It
    # is not a unique coordinate unless the evidence also names one state
    # literally; collapse only that proven state and otherwise leave the
    # group unresolved for the caller's quarantine decision.
    by_sample: dict[str, list[OwnerNode]] = {}
    for node in nodes:
        by_sample.setdefault(_identity_text(node.sample_id_raw), []).append(node)
    disambiguated: list[OwnerNode] = []
    for group in by_sample.values():
        if len(group) <= 1:
            disambiguated.extend(group)
            continue
        state_named = [
            node
            for node in group
            if node.state_raw and _literal_mention(support, node.state_raw)
        ]
        if len(state_named) == 1:
            disambiguated.extend(state_named)
        # Multiple state labels or a generic label with no state label are
        # intentionally omitted: the source has not selected one owner.
    nodes = tuple(disambiguated)
    if not current_only:
        return nodes
    return tuple(
        node
        for node in nodes
        if node.role == "Target" and node.data_nature == "Experimental"
    )


def _source_context_owner_nodes(
    fact: AxisFact,
    graph: OwnerGraph,
    source_text: str,
) -> tuple[OwnerNode, ...]:
    """Recover one owner from the source sentence when chunk evidence is lossy.

    Alpha25 task assembly can retain only ``yield strength 900 MPa`` even
    though the source sentence is ``Sample 2-1 had yield strength 900 MPa``.
    The candidate's own evidence then looks owner-free and the core-tensile
    ambiguity gate would discard a fact that is actually source-local.  This
    helper rechecks only sentences containing the exact evidence span and
    accepts the coordinate only when that sentence names one distinctive
    current owner.  It never uses item order, chemistry similarity, or a
    neighboring sentence/table row.
    """

    if not source_text or _has_table_evidence(_fact_evidence(fact)):
        return ()
    evidence = tuple(
        normalize_evidence_text(row)
        for row in _fact_evidence(fact)
        if normalize_evidence_text(row)
    )
    if not evidence:
        return ()
    matches: dict[str, OwnerNode] = {}
    sentences = re.split(r"(?<=[.!?])\s+(?=[A-Z0-9])", source_text)
    for sentence in sentences:
        normalized = normalize_evidence_text(sentence)
        if not normalized or not all(row in normalized for row in evidence):
            continue
        named = _safe_source_owner_nodes(sentence, graph)
        if len(named) == 1:
            matches[named[0].owner_id] = named[0]
    return tuple(matches[key] for key in sorted(matches))


def _fact_has_explicit_base_owner_without_state(
    fact: AxisFact,
    candidate_nodes: Sequence[OwnerNode],
    state_nodes: Sequence[OwnerNode],
) -> bool:
    """Return whether prose names only the candidate's base owner.

    A headline result may be asserted for ``Alloy-A`` while the inventory also
    contains ``Alloy-A [as-built]`` and ``Alloy-A [aged]``.  When the source
    sentence literally names only the unqualified owner, that is a base-item
    assertion rather than a broadcast to both state children.  Numeric-only
    quotes and any quote naming a state remain ambiguous and are quarantined.
    """

    owner = str(fact.sample_id_raw or "").strip()
    if not _safe_explicit_owner_label(owner):
        return False
    support = "\n".join(_fact_evidence(fact))
    if not _literal_mention(support, owner):
        return False
    if any(
        node.state_raw and _literal_mention(support, node.state_raw)
        for node in state_nodes
    ):
        return False
    owner_key = _identity_text(owner)
    return any(
        _identity_text(node.sample_id_raw) == owner_key
        and not re.search(r"\s*\[[^\]]+\]\s*$", node.sample_id_raw)
        for node in candidate_nodes
    )


def _processing_parameter_state_matches(
    fact: ProcessingFact,
    state_nodes: Sequence[OwnerNode],
) -> tuple[OwnerNode, ...]:
    """Resolve one existing state from explicit process parameter coordinates.

    A process paragraph may omit the structured owner but still provide a
    source coordinate such as ``optimum sintering temperature of 1280 °C and
    time of 4 h``.  When exactly one existing state in the candidate lineage
    carries that numeric treatment coordinate, it is safe to reassign the
    fact to that state.  Multiple temperatures, missing numeric coordinates,
    and unrelated thermal measurements remain ambiguous and are quarantined.
    """

    if not isinstance(fact, ProcessingFact) or not state_nodes:
        return ()
    parameters = [
        parameter
        for parameter in fact.data.get("parameters_raw") or []
        if isinstance(parameter, dict)
    ]
    coordinates: list[str] = []
    for parameter in parameters:
        value = str(parameter.get("value_raw") or "").strip()
        unit = str(parameter.get("unit_raw") or "").strip()
        if not _numeric_tokens(value):
            continue
        source = " ".join(
            str(part or "").strip()
            for part in (
                parameter.get("source_evidence"),
                parameter.get("condition_label_raw"),
                value,
                unit,
            )
            if str(part or "").strip()
        )
        if source:
            coordinates.append(source)
    if not coordinates:
        return ()
    matches: dict[str, OwnerNode] = {}
    for node in state_nodes:
        if not node.state_raw:
            continue
        state_text = _scientific_fold(node.state_raw)
        state_numbers = set(_numeric_tokens(node.state_raw))
        if not state_numbers:
            continue
        process_state_match = False
        for coordinate in coordinates:
            coordinate_text = _scientific_fold(coordinate)
            if not state_numbers.intersection(_numeric_tokens(coordinate)):
                continue
            # ``_condition_matches_state`` intentionally keeps the generic
            # Property cue set narrow.  Processing coordinates need explicit
            # treatment vocabulary so ``sintering ... 1280 °C`` can bind to
            # ``sintered at 1280 °C`` without allowing an unrelated DSC value
            # to choose a material state.
            if any(
                cue in state_text and cue in coordinate_text
                for cue in (
                    "sinter",
                    "anneal",
                    "heat treat",
                    "solution treat",
                    "age",
                    "hip",
                    "print",
                    "build",
                    "fabricat",
                    "deposit",
                    "cure",
                )
            ):
                process_state_match = True
                break
        if process_state_match:
            matches[node.owner_id] = node
    return tuple(matches[key] for key in sorted(matches))


_IMPLICIT_PROCESSED_STATE = re.compile(
    r"(?ix)^as[\s-]*(?:built|printed|fabricated|deposited)(?:\s+"
    r"(?:condition|state))?$"
)


def _implicit_processed_state_target(
    fact: AxisFact,
    graph: OwnerGraph,
) -> OwnerNode | None:
    """Resolve one existing ``as-built``-like child from a process event.

    Inventory rows frequently encode the state only in ``Sample_ID`` (now
    parsed by ``build_owner_graph``), while the process assertion says
    ``EBAM specimens were built``.  If one and only one target/experimental
    state child exists in the candidate's declared lineage, that wording is a
    source-grounded state coordinate.  This helper never searches by
    chemistry alone and never creates a state owner.
    """

    if not isinstance(fact, ProcessingFact) or fact.fact_type != "process_stage":
        return None
    evidence = _fact_evidence(fact)
    support = "\n".join(evidence)
    if not support or not _PROCESS_DIRECT_EVENT_ASSERTION.search(support):
        return None
    record = build_promotion_records([fact])[0]
    candidates = _candidate_nodes(record, graph)
    if not candidates:
        return None
    state_nodes = _lineage_state_nodes(candidates, graph)
    processed_states = [
        node
        for node in state_nodes
        if node.role == "Target"
        and node.data_nature == "Experimental"
        and node.state_raw
        and _IMPLICIT_PROCESSED_STATE.fullmatch(node.state_raw.strip())
    ]
    unique = {node.owner_id: node for node in processed_states}
    if len(unique) != 1:
        return None
    target = next(iter(unique.values()))
    # A different explicit state in the same assertion wins over this
    # process-event shorthand.  The condition/state gates handle that case.
    if any(
        node.state_raw
        and not _IMPLICIT_PROCESSED_STATE.fullmatch(node.state_raw.strip())
        and _literal_mention(support, node.state_raw)
        for node in state_nodes
    ):
        return None
    return target


def _route_implicit_processed_state_owners(
    anchors: Sequence[InventoryAnchor],
    facts: Sequence[AxisFact],
) -> tuple[list[AxisFact], list[PromotionIssue]]:
    """Route process-event candidates to one existing processed-state owner."""

    graph = build_owner_graph(anchors)
    if not graph.nodes:
        return list(facts), []
    accepted: list[AxisFact] = []
    issues: list[PromotionIssue] = []
    for fact in facts:
        target = _implicit_processed_state_target(fact, graph)
        if target is None or _identity_text(fact.sample_id_raw) == _identity_text(
            target.sample_id_raw
        ):
            accepted.append(fact)
            continue
        reassigned = _reassign_fact_owner(fact, target.sample_id_raw)
        accepted.append(reassigned)
        issues.append(
            _promotion_issue(
                fact,
                code="promotion_processing_implicit_state_owner_reassigned",
                message=(
                    "A direct process event selected one existing as-built-like "
                    "state child in the candidate owner's lineage; the candidate "
                    "was routed there without inventing an owner."
                ),
                expected={
                    "unique_existing_processed_state_owner": target.sample_id_raw,
                    "owner_invented": False,
                    "audit_preserved": True,
                },
                actual={
                    "before": fact.model_dump(),
                    "after": reassigned.model_dump(),
                    "target_state": target.state_raw,
                },
                evidence=_fact_evidence(fact),
            )
        )
    return accepted, issues


def _quarantine_processing_owner_ambiguities(
    anchors: Sequence[InventoryAnchor],
    facts: Sequence[AxisFact],
    source_text: str,
) -> tuple[list[AxisFact], list[PromotionIssue]]:
    """Require a source coordinate before promoting state-sensitive processing.

    Process parameters are often emitted from a short neighboring chunk such
    as ``laser power of 300 W`` and copied onto a material/base item.  When the
    inventory already contains state children, that short quote does not prove
    which state owns the parameter.  Keep explicit shared assertions and
    literal-owner bindings; otherwise isolate the candidate so the extraction
    cannot manufacture an owner by item order or confidence.
    """

    graph = build_owner_graph(anchors)
    if not graph.nodes:
        return list(facts), []
    accepted: list[AxisFact] = []
    issues: list[PromotionIssue] = []
    for fact in facts:
        if not isinstance(fact, ProcessingFact) or fact.fact_type != "process_stage":
            accepted.append(fact)
            continue
        # A parameter-less process stage is a route/event assertion, not the
        # state-sensitive numeric projection this gate is designed to police.
        # Keep it under the existing process-event and owner gates; otherwise a
        # generic ``fabricated by LPBF`` sentence would be mistaken for a
        # misplaced parameter and recall would collapse across a paper.
        if not (fact.data.get("parameters_raw") or []):
            accepted.append(fact)
            continue
        record = build_promotion_records([fact])[0]
        support = "\n".join(record.evidence)
        if not support.strip() or _has_collective_owner_scope(support):
            accepted.append(fact)
            continue
        # A parsed row/column coordinate is handled by the table gate.  The
        # processing-specific prose rule must not reinterpret a table header as
        # a missing owner, especially when several columns intentionally share
        # one value.
        if _has_table_evidence(record.evidence):
            accepted.append(fact)
            continue
        candidate_nodes = _candidate_nodes(record, graph)
        if not candidate_nodes:
            accepted.append(fact)
            continue
        # The precision gate is for the paper's current experimental target
        # samples. Reference/computed owners may reuse a chemistry label across
        # independent states; their provenance is handled by the existing
        # reference-owner gates instead of this experimental-state quarantine.
        if not any(
            node.role == "Target" and node.data_nature == "Experimental"
            for node in candidate_nodes
        ):
            accepted.append(fact)
            continue
        named_nodes = _fact_has_literal_owner_or_state(
            fact, graph, current_only=True
        )
        if len(named_nodes) == 1:
            target = named_nodes[0]
            if any(node.owner_id == target.owner_id for node in candidate_nodes):
                accepted.append(fact)
                continue
            reassigned = _reassign_fact_owner(fact, target.sample_id_raw)
            accepted.append(reassigned)
            issues.append(
                _promotion_issue(
                    fact,
                    code="promotion_processing_source_owner_reassigned",
                    message=(
                        "A processing assertion named one existing current-paper "
                        "owner; the candidate was routed there instead of being "
                        "left on a different material/state."
                    ),
                    expected={
                        "source_explicit_owner": target.sample_id_raw,
                        "unique_current_experimental_owner": True,
                        "owner_invented": False,
                        "audit_preserved": True,
                    },
                    actual={
                        "before": fact.model_dump(),
                        "after": reassigned.model_dump(),
                    },
                    evidence=list(record.evidence),
                )
            )
            continue
        # Several literal owners can legitimately share one process assertion
        # (e.g. a paragraph explicitly saying both samples used the same
        # route).  If the candidate is one of those owners, retain it; a copy
        # onto an unmentioned owner is not source-proven.
        if len(named_nodes) > 1:
            if any(
                candidate.owner_id == named.owner_id
                for candidate in candidate_nodes
                for named in named_nodes
            ):
                accepted.append(fact)
                continue
            issues.append(
                _promotion_issue(
                    fact,
                    code="promotion_processing_owner_ambiguous_quarantined",
                    message=(
                        "A processing assertion named multiple existing owners, "
                        "but this candidate was attached to none of them."
                    ),
                    expected={
                        "source_named_owner": "one_of_named_owners",
                        "broadcast": False,
                        "audit_preserved": True,
                    },
                    actual={
                        "removed": fact.model_dump(),
                        "named_owners": [node.sample_id_raw for node in named_nodes],
                        "candidate_owners": [
                            node.sample_id_raw for node in candidate_nodes
                        ],
                    },
                    evidence=list(record.evidence),
                )
            )
            continue

        # A treatment-prefixed sample label is not itself proof of a material
        # identity.  If the full label is absent from this fact's evidence and
        # no unique state owner was resolved above, isolate the parameterized
        # stage rather than letting the self-created inventory anchor validate
        # it.  This protects the narrow ``annealed Cu-B4C composite`` failure
        # mode while leaving explicit ``A1 was annealed ...`` evidence intact.
        if (
            _distinctive_state_prefixed_processing_owner(fact.sample_id_raw)
            and not _literal_mention(support, fact.sample_id_raw)
        ):
            issues.append(
                _promotion_issue(
                    fact,
                    code="promotion_processing_state_label_unbound_quarantined",
                    message=(
                        "A parameterized Processing stage used a treatment/state "
                        "prefixed owner label that was not literally present in "
                        "its own evidence and had no unique state coordinate."
                    ),
                    expected={
                        "source_literal_owner_or_unique_state": True,
                        "self_created_owner_inference": False,
                        "audit_preserved": True,
                    },
                    actual={
                        "removed": fact.model_dump(),
                        "owner": fact.sample_id_raw,
                        "reason": "state_prefixed_owner_not_literal_in_evidence",
                    },
                    evidence=list(record.evidence),
                )
            )
            continue

        state_nodes = _lineage_state_nodes(candidate_nodes, graph)
        if not state_nodes:
            accepted.append(fact)
            continue
        parameter_state_matches = _processing_parameter_state_matches(
            fact, state_nodes
        )
        if len(parameter_state_matches) == 1 and (
            parameter_state_matches[0].role == "Target"
            and parameter_state_matches[0].data_nature == "Experimental"
        ):
            target = parameter_state_matches[0]
            reassigned = _reassign_fact_owner(fact, target.sample_id_raw)
            accepted.append(reassigned)
            issues.append(
                _promotion_issue(
                    fact,
                    code="promotion_processing_parameter_state_owner_reassigned",
                    message=(
                        "A parameterized processing fact was routed to one "
                        "existing state owner selected by its explicit numeric "
                        "treatment coordinate."
                    ),
                    expected={
                        "unique_existing_state_owner": target.sample_id_raw,
                        "owner_invented": False,
                        "audit_preserved": True,
                    },
                    actual={
                        "before": fact.model_dump(),
                        "after": reassigned.model_dump(),
                        "state_coordinate": target.state_raw,
                    },
                    evidence=list(record.evidence),
                )
            )
            continue
        # A source-literal state/condition can be routed by the earlier
        # condition-owner pass.  If it survived here and names one candidate
        # state directly, it is not ambiguous.
        state_literals = tuple(
            node
            for node in state_nodes
            if node.state_raw and _literal_mention(support, node.state_raw)
        )
        if len(state_literals) == 1 and any(
            node.owner_id == state_literals[0].owner_id
            for node in candidate_nodes
        ):
            accepted.append(fact)
            continue

        issues.append(
            _promotion_issue(
                fact,
                code="promotion_processing_owner_ambiguous_quarantined",
                message=(
                    "A state-sensitive processing assertion had no unique "
                    "source owner/state coordinate; the generic projection was "
                    "isolated instead of being broadcast to a base item."
                ),
                expected={
                    "unique_source_owner_or_state": True,
                    "state_sibling_count": len(state_nodes),
                    "broadcast": False,
                    "audit_preserved": True,
                },
                actual={
                    "removed": fact.model_dump(),
                    "candidate_owners": [node.sample_id_raw for node in candidate_nodes],
                    "candidate_states": [node.state_raw for node in state_nodes],
                    "reason": "processing_parameter_without_source_coordinate",
                },
                evidence=list(record.evidence),
            )
        )
    return accepted, issues


def _v204_tensile_assertion_decision(
    fact: PropertyFact,
    graph: OwnerGraph,
    source_text: str,
) -> TensileAssertionDecision:
    """Resolve one existing tensile candidate against the complete source.

    The coordinate parser validates only the candidate's literal property,
    value, and unit.  This wrapper supplies the already-declared current-paper
    owner ledger; it never creates an owner from prose.
    """

    if not tensile_assertion_coordinates_v204_enabled() or not source_text:
        return TensileAssertionDecision(status="disabled", reason="v204_disabled")
    grouped_nodes: dict[tuple[str, str, str], list[OwnerNode]] = {}
    for node in graph.nodes:
        if node.role != "Target" or node.data_nature != "Experimental":
            continue
        grouped_nodes.setdefault(
            (
                _identity_text(node.sample_id_raw),
                node.role,
                node.data_nature,
            ),
            [],
        ).append(node)
    owner_aliases: dict[str, tuple[str, ...]] = {}
    for nodes in grouped_nodes.values():
        representative = min(nodes, key=lambda row: row.owner_id)
        aliases = {str(representative.sample_id_raw or "").strip()}
        owner_aliases[representative.owner_id] = tuple(
            sorted(
                (alias for alias in aliases if alias),
                key=lambda value: (_identity_text(value), value),
            )
        )
    return resolve_tensile_assertion_coordinate(
        property_name=str(fact.data.get("property_name_raw") or ""),
        value_raw=str(fact.data.get("value_raw") or ""),
        unit_raw=str(fact.data.get("unit_raw") or ""),
        evidence=tuple(_fact_evidence(fact)),
        source_text=source_text,
        owner_aliases=owner_aliases,
    )


def _v204_same_existing_owner(left: OwnerNode, right: OwnerNode) -> bool:
    """Collapse duplicate inventory anchors, never independent states."""

    return (
        _identity_text(left.sample_id_raw) == _identity_text(right.sample_id_raw)
        and left.role == right.role
        and left.data_nature == right.data_nature
    )


def _v204_bind_assertion_condition(
    fact: PropertyFact,
    decision: TensileAssertionDecision,
) -> tuple[PropertyFact, bool]:
    """Publish the source coordinate and fill only a literal result condition."""

    coordinate = decision.coordinate
    if (
        not tensile_result_protocol_binding_v204_enabled()
        or coordinate is None
    ):
        return fact, False
    data = deepcopy(fact.data)
    changed = False
    if data.get("property_id_candidate") != coordinate.source_coordinate_key:
        data["property_id_candidate"] = coordinate.source_coordinate_key
        changed = True
    condition_bound = bool(
        str(coordinate.condition_raw or "").strip()
        and not str(data.get("test_condition_raw") or "").strip()
    )
    if condition_bound:
        data["test_condition_raw"] = coordinate.condition_raw
        changed = True
    if not changed:
        return fact, False
    return fact.model_copy(deep=True, update={"data": data}), condition_bound


_PROCESS_ROLE_VERBS_V205 = (
    r"fabricat(?:ed|ion)|manufactur(?:ed|ing)|print(?:ed|ing)|"
    r"process(?:ed|ing)|produc(?:ed|tion)|build|built|deposit(?:ed|ion)"
)


def _owner_label_has_process_role_v205(label: str, support: str) -> bool:
    """Require grammar that explicitly uses an owner label as a process."""

    normalized_label = _identity_text(label)
    normalized_support = _identity_text(support)
    if not normalized_label or not normalized_support:
        return False
    escaped = re.escape(normalized_label).replace(r"\ ", r"[\s-]+")
    return bool(
        re.search(
            rf"(?ix)(?<!\w){escaped}(?!\w)[\s-]*(?:{_PROCESS_ROLE_VERBS_V205})\b",
            normalized_support,
        )
        or re.search(
            rf"(?ix)\b(?:{_PROCESS_ROLE_VERBS_V205})\s+"
            rf"(?:by|using|via|with)\s+(?:the\s+)?{escaped}(?!\w)",
            normalized_support,
        )
    )


def _tensile_process_owner_decision_key_v205(
    fact: PropertyFact,
    candidates: Sequence[OwnerNode],
    *,
    reason: str,
) -> str:
    payload = {
        "owner": _identity_text(fact.sample_id_raw),
        "property": core_tensile_subtype(fact.data.get("property_name_raw")),
        "value": _scientific_fold(fact.data.get("value_raw")),
        "unit": _scientific_fold(fact.data.get("unit_raw")),
        "condition": _scientific_fold(fact.data.get("test_condition_raw")),
        "evidence": [
            normalize_evidence_text(row) for row in _fact_evidence(fact)
        ],
        "candidate_owner_ids": sorted(node.owner_id for node in candidates),
        "reason": reason,
    }
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return "tensile-process-owner-v205:" + hashlib.sha256(encoded).hexdigest()[:24]


def _route_unique_material_owner_v205(
    anchors: Sequence[InventoryAnchor],
    facts: Sequence[AxisFact],
    source_text: str,
) -> tuple[list[AxisFact], list[PromotionIssue]]:
    """Route a process-only tensile owner to one literal existing specimen.

    A manufacturing label remains a valid sample designation unless its own
    source assertion grammatically uses that label as a process.  Even then,
    reassignment requires exactly one existing Target/Experimental owner named
    in the same assertion.  No process-name registry or paper-specific alias is
    used.
    """

    if not unique_material_owner_convergence_v205_enabled() or not source_text:
        return list(facts), []
    graph = build_owner_graph(anchors)
    if not graph.nodes:
        return list(facts), []
    accepted: list[AxisFact] = []
    issues: list[PromotionIssue] = []
    for fact in facts:
        if not isinstance(fact, PropertyFact) or not is_core_tensile_property_name(
            fact.data.get("property_name_raw")
        ):
            accepted.append(fact)
            continue
        evidence = _fact_evidence(fact)
        support = "\n".join(evidence)
        if not support or _has_table_evidence(evidence):
            accepted.append(fact)
            continue
        current_nodes = _candidate_nodes(build_promotion_records([fact])[0], graph)
        current_targets = [
            node
            for node in current_nodes
            if node.role == "Target" and node.data_nature == "Experimental"
        ]
        if len({node.owner_id for node in current_targets}) != 1:
            accepted.append(fact)
            continue
        current = current_targets[0]
        process_aliases = [
            alias
            for alias in current.aliases
            if _owner_label_has_process_role_v205(alias, support)
        ]
        if not process_aliases:
            accepted.append(fact)
            continue

        assertion_decision = _v204_tensile_assertion_decision(
            fact, graph, source_text
        )
        coordinate_target: OwnerNode | None = None
        if (
            assertion_decision.status == "matched"
            and assertion_decision.coordinate is not None
        ):
            candidate = graph.node(assertion_decision.coordinate.owner_key)
            if candidate.owner_id != current.owner_id:
                coordinate_target = candidate

        literal_targets: dict[str, OwnerNode] = {}
        for node in graph.nodes:
            if (
                node.owner_id == current.owner_id
                or node.role != "Target"
                or node.data_nature != "Experimental"
                or not _distinctive_owner_label(node.sample_id_raw)
                or not _literal_mention(support, node.sample_id_raw)
                or _owner_label_has_process_role_v205(node.sample_id_raw, support)
            ):
                continue
            if node.state_raw and not _literal_mention(support, node.state_raw):
                continue
            literal_targets[node.owner_id] = node
        if coordinate_target is not None:
            literal_targets = {coordinate_target.owner_id: coordinate_target}

        if len(literal_targets) == 1:
            target = next(iter(literal_targets.values()))
            reassigned = _reassign_fact_owner(fact, target.sample_id_raw)
            accepted.append(reassigned)
            decision_key = (
                assertion_decision.coordinate.decision_key
                if assertion_decision.coordinate is not None
                and assertion_decision.coordinate.owner_key == target.owner_id
                else _tensile_process_owner_decision_key_v205(
                    fact,
                    [target],
                    reason="unique_literal_material_owner",
                )
            )
            issues.append(
                _promotion_issue(
                    fact,
                    code="tensile_process_owner_reassigned",
                    severity="info",
                    message=(
                        "A core-tensile candidate used a source-explicit process "
                        "label as owner while the same assertion named exactly "
                        "one existing material/specimen owner; it was rerouted "
                        "without inventing an owner."
                    ),
                    expected={
                        "process_role_grammar": True,
                        "unique_existing_material_owner": True,
                        "owner_invented": False,
                        "value_unit_condition_changed": False,
                        "audit_preserved": True,
                    },
                    actual={
                        "before": fact.model_dump(),
                        "after": reassigned.model_dump(),
                        "process_aliases": process_aliases,
                        "selected_owner": target.sample_id_raw,
                        "selected_owner_id": target.owner_id,
                        "decision_key": decision_key,
                        "assertion_decision": assertion_decision.to_dict(),
                    },
                    evidence=evidence,
                )
            )
            continue

        reason = (
            "ambiguous_material_coordinate"
            if len(literal_targets) > 1
            or assertion_decision.status == "ambiguous"
            else "no_unique_material_coordinate"
        )
        accepted.append(fact)
        issues.append(
            _promotion_issue(
                fact,
                code="tensile_process_owner_ambiguous",
                message=(
                    "A process-role tensile owner had no unique literal existing "
                    "material/specimen coordinate; the original candidate was "
                    "preserved for review without reassignment."
                ),
                expected={
                    "unique_existing_material_owner": True,
                    "owner_invented": False,
                    "ambiguous_reassignment": False,
                    "audit_preserved": True,
                },
                actual={
                    "before": fact.model_dump(),
                    "reason": reason,
                    "process_aliases": process_aliases,
                    "candidate_owners": [
                        node.sample_id_raw for node in literal_targets.values()
                    ],
                    "decision_key": _tensile_process_owner_decision_key_v205(
                        fact,
                        tuple(literal_targets.values()),
                        reason=reason,
                    ),
                    "assertion_decision": assertion_decision.to_dict(),
                },
                evidence=evidence,
            )
        )
    return accepted, issues


def _quarantine_core_tensile_owner_ambiguities(
    anchors: Sequence[InventoryAnchor],
    facts: Sequence[AxisFact],
    source_text: str = "",
) -> tuple[list[AxisFact], list[PromotionIssue]]:
    """Isolate generic core-tensile values when state ownership is unresolved."""

    graph = build_owner_graph(anchors)
    if not graph.nodes:
        return list(facts), []
    accepted: list[AxisFact] = []
    issues: list[PromotionIssue] = []
    for fact in facts:
        if not isinstance(fact, PropertyFact) or not is_core_tensile_property_name(
            fact.data.get("property_name_raw")
        ):
            accepted.append(fact)
            continue
        value_text = str(fact.data.get("value_raw") or "")
        if not _numeric_tokens(value_text) or re.search(
            r"(?ix)\b(?:times|fold|relative|ratio|compared|higher|lower|"
            r"difference|anisotrop(?:y|ic)|contribution|estimated|calculated)\b",
            value_text,
        ):
            # Qualitative/comparative/derived tensile descriptions are handled
            # by the existing Property projection gate.  They do not need an
            # owner-state quarantine here, and a relative quantity must not be
            # counted as an absolute tensile result merely because it contains
            # a number (``three times``, ``1.7-fold``, etc.).
            accepted.append(fact)
            continue
        support = "\n".join(_fact_evidence(fact))
        if not support.strip() or _has_collective_owner_scope(support):
            accepted.append(fact)
            continue
        record = build_promotion_records([fact])[0]
        candidate_nodes = _candidate_nodes(record, graph)
        if not candidate_nodes:
            accepted.append(fact)
            continue
        # Computed and literature owners are intentionally outside this gate:
        # state ambiguity for them is not evidence that an experimental scalar
        # was copied between samples, and citation/reference passes own that
        # provenance decision.
        if not any(
            node.role == "Target" and node.data_nature == "Experimental"
            for node in candidate_nodes
        ):
            accepted.append(fact)
            continue
        state_nodes = _lineage_state_nodes(candidate_nodes, graph)

        # A prose quote about a generic population (``the rods``, ``the
        # samples``, ``the alloy``) cannot safely validate one of several
        # current-paper owners when the candidate's declared owner is absent
        # from that quote.  Tables have a separate coordinate gate and
        # explicitly collective prose is valid for all named owners; only the
        # unresolved prose projection is isolated here.  This prevents a
        # chemistry/base item such as ``44-4`` from silently owning a value that
        # the source actually reports for a rectangular rod or an R1/R2/R5
        # specimen.
        prose_evidence = not _has_table_evidence(_fact_evidence(fact))
        explicit_owner_in_quote = any(
            _safe_explicit_owner_label(alias)
            and _literal_mention(support, alias)
            for node in candidate_nodes
            for alias in _owner_evidence_aliases(node.sample_id_raw)
        )
        if prose_evidence and not explicit_owner_in_quote and source_text:
            # The chunk may have dropped the owner while the bounded source
            # sentence still names it.  Treat one source-local current owner
            # as an explicit coordinate, but do not rescue a multi-owner
            # paragraph or a neighboring table row.
            source_context_nodes = _source_context_owner_nodes(
                fact, graph, source_text
            )
            explicit_owner_in_quote = len(source_context_nodes) == 1 and any(
                node.owner_id == source_context_nodes[0].owner_id
                for node in candidate_nodes
            )
        if prose_evidence and not explicit_owner_in_quote and source_text:
            assertion_decision = _v204_tensile_assertion_decision(
                fact, graph, source_text
            )
            coordinate = assertion_decision.coordinate
            if assertion_decision.status == "matched" and coordinate is not None:
                target = graph.node(coordinate.owner_key)
                reassigned = fact
                if not any(
                    _v204_same_existing_owner(node, target)
                    for node in candidate_nodes
                ) or _identity_text(fact.sample_id_raw) != _identity_text(
                    target.sample_id_raw
                ):
                    reassigned = _reassign_fact_owner(
                        fact, target.sample_id_raw
                    )
                conditioned, condition_bound = _v204_bind_assertion_condition(
                    reassigned, assertion_decision
                )
                accepted.append(conditioned)
                issues.append(
                    _promotion_issue(
                        fact,
                        code=(
                            "tensile_coordinate_owner_reassigned"
                            if reassigned is not fact
                            else "tensile_assertion_coordinate_recovered"
                        ),
                        severity="info",
                        message=(
                            "A complete source assertion supplied one literal "
                            "owner/property/value/unit coordinate for an existing "
                            "core-tensile candidate."
                        ),
                        expected={
                            "source_coordinate_count": 1,
                            "owner_invented": False,
                            "candidate_value_changed": False,
                            "candidate_unit_changed": False,
                            "broadcast": False,
                        },
                        actual={
                            "before": fact.model_dump(),
                            "after": conditioned.model_dump(),
                            "decision": assertion_decision.to_dict(),
                            "selected_owner": target.sample_id_raw,
                            "selected_owner_id": target.owner_id,
                        },
                        evidence=[coordinate.source_text],
                    )
                )
                if condition_bound:
                    issues.append(
                        _promotion_issue(
                            reassigned,
                            code="tensile_result_protocol_bound",
                            severity="info",
                            message=(
                                "A literal tensile-result temperature from the "
                                "same complete source assertion filled an empty "
                                "candidate condition."
                            ),
                            expected={
                                "same_assertion": True,
                                "overwrite_existing_literal": False,
                                "preparation_temperature": False,
                            },
                            actual={
                                "before": reassigned.model_dump(),
                                "after": conditioned.model_dump(),
                                "decision": assertion_decision.to_dict(),
                                "contributed_dimensions": ["temperature"],
                            },
                            evidence=[coordinate.source_text],
                        )
                    )
                continue
            if assertion_decision.status == "ambiguous":
                issues.append(
                    _promotion_issue(
                        fact,
                        code="tensile_assertion_coordinate_ambiguous",
                        message=(
                            "The complete source assertion did not prove one "
                            "owner/property/value/unit coordinate; the existing "
                            "precision gate retained its fail-closed behavior."
                        ),
                        expected={
                            "source_coordinate_count": 1,
                            "broadcast": False,
                        },
                        actual={
                            "fact": fact.model_dump(),
                            "decision": assertion_decision.to_dict(),
                        },
                        evidence=list(_fact_evidence(fact)),
                    )
                )
        explicit_state_in_quote = bool(
            _record_state(record)
            and _payload_grounded(_record_state(record), _fact_evidence(fact))
            and any(
                node.state_raw
                and _identity_text(node.state_raw)
                == _identity_text(_record_state(record))
                and _literal_mention(support, node.state_raw)
                for node in state_nodes
            )
        )
        current_target_count = sum(
            node.role == "Target" and node.data_nature == "Experimental"
            for node in graph.nodes
        )
        if (
            prose_evidence
            and current_target_count > 1
            and not explicit_owner_in_quote
            and not explicit_state_in_quote
            and not _has_collective_owner_scope(support)
        ):
            issues.append(
                _promotion_issue(
                    fact,
                    code="promotion_core_tensile_owner_ambiguous_quarantined",
                    message=(
                        "A prose core-tensile value lacked a literal owner/state "
                        "coordinate while multiple current experimental owners "
                        "were available; the generic projection was isolated."
                    ),
                    expected={
                        "source_literal_owner_or_state": True,
                        "multiple_current_owners": True,
                        "broadcast": False,
                        "audit_preserved": True,
                    },
                    actual={
                        "removed": fact.model_dump(),
                        "candidate_owners": [
                            node.sample_id_raw for node in candidate_nodes
                        ],
                        "current_target_count": current_target_count,
                        "reason": "prose_owner_not_literal",
                    },
                    evidence=list(_fact_evidence(fact)),
                )
            )
            continue
        if not state_nodes:
            accepted.append(fact)
            continue

        if _fact_has_explicit_base_owner_without_state(
            fact, candidate_nodes, state_nodes
        ):
            accepted.append(fact)
            continue

        # A complete source table can provide the missing state coordinate even
        # when the candidate evidence contains only the numeric row.  The
        # tensile table gate has already proven the one-to-one condition/value
        # binding; accept it here only when that condition resolves to one
        # existing lineage state (or there are no state siblings at all).
        table_decision, _ = _table_binding_decision(
            fact, record, graph, source_text
        )
        table_payload = _table_binding_payload(fact)
        table_target = (
            _table_condition_state_owner(record, graph, table_payload[1])
            if table_decision is True and table_payload is not None
            else None
        )
        if table_decision is True:
            # A unique table value/condition coordinate is already stronger
            # than a generic inventory owner.  Prefer it even when the
            # inventory did not materialize an exactly matching state node
            # (for example ``500 h`` may remain only in the table header).
            # The condition must be non-empty for this fallback; an
            # unconditional unique-value table still goes through the normal
            # owner ambiguity gate below.
            if table_target is not None or (
                table_payload is not None
                and str(table_payload[1] or "").strip()
                and _scientific_fold(table_payload[1]) not in _UNREPORTED
            ):
                accepted.append(fact)
                continue

        # Some table/abstract projections put the state in the structured
        # ``material_state`` field while the copied evidence omits the sample
        # label (for example, ``... after HIP2 + HT2 ...``).  A single state
        # that is literally present in that same evidence is still a valid
        # coordinate; requiring a literal owner label here would discard it.
        declared_state = _record_state(record)
        if declared_state:
            declared_matches = tuple(
                node
                for node in state_nodes
                if _identity_text(node.state_raw) == _identity_text(declared_state)
                and _literal_mention(support, node.state_raw)
            )
            unique_declared = {
                node.owner_id: node for node in declared_matches
            }
            if len(unique_declared) == 1:
                target = next(iter(unique_declared.values()))
                if any(
                    candidate.owner_id == target.owner_id
                    for candidate in candidate_nodes
                ):
                    accepted.append(fact)
                    continue

        named_nodes = _fact_has_literal_owner_or_state(
            fact, graph, current_only=True
        )
        if len(named_nodes) == 1 and any(
            candidate.owner_id == named_nodes[0].owner_id
            for candidate in candidate_nodes
        ):
            accepted.append(fact)
            continue
        if len(named_nodes) > 1 and any(
            candidate.owner_id == named.owner_id
            for candidate in candidate_nodes
            for named in named_nodes
        ):
            # A multi-owner comparison/table quote can be valid when the
            # candidate itself is one explicitly named owner.  The dedicated
            # value/row gates decide whether the numeric pairing is safe.
            accepted.append(fact)
            continue
        state_literals = tuple(
            node
            for node in state_nodes
            if node.state_raw and _literal_mention(support, node.state_raw)
        )
        if len(state_literals) == 1 and any(
            candidate.owner_id == state_literals[0].owner_id
            for candidate in candidate_nodes
        ):
            accepted.append(fact)
            continue

        issues.append(
            _promotion_issue(
                fact,
                code="promotion_core_tensile_owner_ambiguous_quarantined",
                message=(
                    "A core-tensile value was attached to a generic or wrong "
                    "state owner while multiple existing state owners were "
                    "available and the candidate evidence supplied no unique "
                    "owner/condition coordinate."
                ),
                expected={
                    "unique_source_owner_or_state": True,
                    "state_sibling_count": len(state_nodes),
                    "broadcast": False,
                    "audit_preserved": True,
                },
                actual={
                    "removed": fact.model_dump(),
                    "candidate_owners": [node.sample_id_raw for node in candidate_nodes],
                    "candidate_states": [node.state_raw for node in state_nodes],
                    "reason": "core_tensile_generic_owner_without_coordinate",
                },
                evidence=list(_fact_evidence(fact)),
            )
        )
    return accepted, issues


def _quarantine_region_scoped_property_owners(
    anchors: Sequence[InventoryAnchor],
    facts: Sequence[AxisFact],
) -> tuple[list[AxisFact], list[PromotionIssue]]:
    """Isolate local-region Property values attached to a generic owner.

    A phrase such as ``fine rosette region`` or ``certain regions`` is a
    measurement coordinate, not a material identity.  When a paper has more
    than one existing owner, attaching such a value to the generic chemistry
    item silently changes the scope of the assertion.  Preserve explicitly
    named owners/states and uniquely matching state coordinates; quarantine
    only the unresolved projection.  Table rows and collective prose remain
    under their dedicated one-to-one gates.
    """

    graph = build_owner_graph(anchors)
    if len(graph.nodes) <= 1:
        return list(facts), []
    accepted: list[AxisFact] = []
    issues: list[PromotionIssue] = []
    for fact in facts:
        if not isinstance(fact, PropertyFact) or is_core_tensile_property_name(
            fact.data.get("property_name_raw")
        ):
            accepted.append(fact)
            continue
        evidence = _fact_evidence(fact)
        support = "\n".join(evidence)
        if not support.strip() or _has_table_evidence(evidence):
            accepted.append(fact)
            continue
        coordinate = " ".join(
            str(value or "")
            for value in (
                fact.data.get("test_condition_raw"),
                fact.data.get("test_specimen_raw"),
                fact.data.get("material_state"),
            )
        ).strip()
        if not _REGION_SCOPED_PROPERTY_COORDINATE.search(coordinate):
            accepted.append(fact)
            continue
        if _has_collective_owner_scope(support):
            accepted.append(fact)
            continue
        record = build_promotion_records([fact])[0]
        candidate_nodes = _candidate_nodes(record, graph)
        if not candidate_nodes:
            accepted.append(fact)
            continue
        # A source sentence may explicitly name the unqualified base sample
        # while describing a local region (for example ``cast regions of
        # sample #5``).  That is a valid base-owner assertion when no existing
        # state label is also named; do not mistake the region locator for an
        # unresolved owner in that case.
        state_nodes = _lineage_state_nodes(candidate_nodes, graph)
        if _fact_has_explicit_base_owner_without_state(
            fact, candidate_nodes, state_nodes
        ):
            accepted.append(fact)
            continue
        named_nodes = _fact_has_literal_owner_or_state(
            fact, graph, current_only=True
        )
        if len(named_nodes) == 1 and any(
            candidate.owner_id == named_nodes[0].owner_id
            for candidate in candidate_nodes
        ):
            accepted.append(fact)
            continue
        state_matches = tuple(
            node
            for node in state_nodes
            if node.state_raw
            and _condition_matches_state(coordinate, node, structure_state=False)
        )
        if len({node.owner_id for node in state_matches}) == 1:
            target_id = state_matches[0].owner_id
            if any(candidate.owner_id == target_id for candidate in candidate_nodes):
                accepted.append(fact)
                continue
        issues.append(
            _promotion_issue(
                fact,
                code="promotion_region_scoped_owner_ambiguous_quarantined",
                message=(
                    "A local-region Property value was attached to a generic "
                    "owner without a source-literal owner/state coordinate; "
                    "the value was isolated instead of being promoted under "
                    "the whole material."
                ),
                expected={
                    "unique_source_owner_or_state": True,
                    "generic_region_broadcast": False,
                    "audit_preserved": True,
                },
                actual={
                    "removed": fact.model_dump(),
                    "coordinate": coordinate,
                    "candidate_owners": [node.sample_id_raw for node in candidate_nodes],
                    "candidate_states": [node.state_raw for node in state_nodes],
                    "reason": "region_scoped_property_without_coordinate",
                },
                evidence=evidence,
            )
        )
    return accepted, issues


def _quarantine_structure_region_coordinate_projections(
    facts: Sequence[AxisFact],
) -> tuple[list[AxisFact], list[PromotionIssue]]:
    """Isolate numeric Structure facts whose local region coordinate was lost.

    Chunk extraction often keeps a measurement (for example, a fine/coarse
    rosette thickness or a fracture-surface grain diameter) while dropping the
    region that gives the number its meaning.  The value may remain
    source-grounded, but promoting it under the whole material changes the
    assertion scope.  Only quantitative Structure facts with an explicit local
    region cue are considered; tables and candidates carrying a grounded
    feature-level coordinate are left to the existing coordinate gates.
    """

    accepted: list[AxisFact] = []
    issues: list[PromotionIssue] = []
    coordinate_keys = (
        "region",
        "location",
        "orientation",
        "position",
        "section",
        "zone",
        "area",
        "layer",
    )
    for fact in facts:
        if not (
            isinstance(fact, StructureFact)
            and fact.fact_type == "structure_observation"
        ):
            accepted.append(fact)
            continue
        evidence = _fact_evidence(fact)
        support = "\n".join(evidence)
        if (
            not support.strip()
            or _has_table_evidence(evidence)
            or not _STRUCTURE_LOCAL_REGION_COORDINATE.search(support)
        ):
            accepted.append(fact)
            continue
        quantitative_features: list[dict[str, Any]] = []
        for feature in fact.data.get("features") or []:
            if isinstance(feature, dict) and _is_quantitative_structure_feature(feature):
                quantitative_features.append(feature)
        for entity in fact.data.get("entities") or []:
            if not isinstance(entity, dict):
                continue
            for feature in entity.get("features") or []:
                if isinstance(feature, dict) and _is_quantitative_structure_feature(feature):
                    quantitative_features.append(feature)
        if not quantitative_features:
            accepted.append(fact)
            continue
        grounded_coordinate = False
        for key in coordinate_keys:
            value = fact.data.get(key)
            if value and _scientific_fold(value) not in _UNREPORTED and _payload_grounded(
                value, evidence
            ):
                grounded_coordinate = True
                break
        if not grounded_coordinate:
            for feature in quantitative_features:
                for key in coordinate_keys:
                    value = feature.get(key)
                    if value and _scientific_fold(value) not in _UNREPORTED and _payload_grounded(
                        value, _feature_evidence(feature, evidence)
                    ):
                        grounded_coordinate = True
                        break
                if grounded_coordinate:
                    break
        if grounded_coordinate:
            accepted.append(fact)
            continue
        issues.append(
            _promotion_issue(
                fact,
                code="promotion_structure_region_coordinate_missing_quarantined",
                message=(
                    "A quantitative Structure observation was tied to a local "
                    "region/surface/layer in the source, but the candidate did "
                    "not preserve one coordinate per measurement."
                ),
                expected={
                    "feature_level_region_coordinate": True,
                    "whole_material_broadcast": False,
                    "audit_preserved": True,
                },
                actual={
                    "removed": fact.model_dump(),
                    "region_cues": sorted(
                        {match.group(0).strip() for match in _STRUCTURE_LOCAL_REGION_COORDINATE.finditer(support)}
                    ),
                    "reason": "local_region_coordinate_missing",
                },
                evidence=evidence,
            )
        )
    return accepted, issues


def _tensile_state_coordinate_target(
    fact: PropertyFact,
    graph: OwnerGraph,
) -> OwnerNode | None:
    """Resolve an explicit extracted tensile state to one existing owner.

    ``material_state`` is a source-coordinate field emitted by the extractor;
    it is stronger than a long test-method condition.  We therefore allow an
    exact existing state, a conservative state cue match within the candidate's
    declared lineage, or a candidate sample label that is itself the state
    label.  No chemistry-only/global fallback is used here.
    """

    coordinate = _record_state(build_promotion_records([fact])[0])
    if not coordinate or not _TENSILE_STATE_COORDINATE.search(coordinate):
        return None
    record = build_promotion_records([fact])[0]
    candidates = _candidate_nodes(record, graph)
    if not candidates:
        return None
    expanded = {node.owner_id: node for node in candidates}
    for node in _lineage_state_nodes(candidates, graph):
        expanded[node.owner_id] = node
    candidates = list(expanded.values())
    current = [
        node
        for node in candidates
        if node.role == "Target" and node.data_nature == "Experimental"
    ]
    exact = [
        node
        for node in current
        if node.state_raw
        and _identity_text(node.state_raw) == _identity_text(coordinate)
    ]
    if len(exact) == 1:
        return exact[0]
    matched = [
        node
        for node in current
        if node.state_raw and _condition_matches_state(coordinate, node)
    ]
    if len(matched) == 1:
        return matched[0]
    # Some inventory rows use the state itself as the sample label and leave
    # ``state_raw`` empty (for example an item named ``as-annealed``).  This is
    # a valid existing owner, not an invitation to manufacture a new state.
    label_matches = [
        node
        for node in current
        if _identity_text(node.sample_id_raw) == _identity_text(coordinate)
    ]
    if len(label_matches) == 1:
        return label_matches[0]
    return None


def _quarantine_tensile_source_unit_conflicts(
    facts: Sequence[AxisFact],
) -> tuple[list[AxisFact], list[PromotionIssue]]:
    """Isolate core-tensile facts whose source unit conflicts with ``unit_raw``."""

    accepted: list[AxisFact] = []
    issues: list[PromotionIssue] = []
    for fact in facts:
        if not isinstance(fact, PropertyFact) or not is_core_tensile_property_name(
            fact.data.get("property_name_raw")
        ):
            accepted.append(fact)
            continue
        conflict, details = _tensile_source_unit_conflict(fact)
        if not conflict:
            accepted.append(fact)
            continue
        issues.append(
            _promotion_issue(
                fact,
                code="promotion_tensile_source_unit_conflict_quarantined",
                message=(
                    "A core-tensile value carried a source-literal physical unit "
                    "that disagreed with unit_raw; the value was isolated rather "
                    "than silently converted or relabeled."
                ),
                expected={
                    "source_literal_unit_matches_unit_raw": True,
                    "canonical_conversion": "materialization_only",
                    "audit_preserved": True,
                },
                actual={"removed": fact.model_dump(), **details},
                evidence=_fact_evidence(fact),
            )
        )
    return accepted, issues


def _quarantine_unresolved_tensile_state_bundles(
    anchors: Sequence[InventoryAnchor],
    facts: Sequence[AxisFact],
) -> tuple[list[AxisFact], list[PromotionIssue]]:
    """Quarantine tensile bundles with an explicit but unresolvable state.

    The extractor can emit yield strength, UTS, and elongation from one prose
    assertion while retaining ``material_state`` on every row.  If that state
    does not map to one existing inventory owner, accepting the rows on a
    generic base item creates three coherent-looking but misattributed facts.
    The whole source bundle is therefore isolated as one auditable decision.
    """

    graph = build_owner_graph(anchors)
    if not graph.nodes:
        return list(facts), []
    records = build_promotion_records(facts)
    grouped: dict[tuple[str, str], list[PromotionRecord]] = {}
    for record in records:
        fact = record.fact
        if not isinstance(fact, PropertyFact) or not is_core_tensile_property_name(
            fact.data.get("property_name_raw")
        ):
            continue
        candidate_nodes = _candidate_nodes(record, graph)
        # Cited Reference treatment states are routed by the dedicated prose
        # citation gate above.  This pass protects current-paper Target
        # bundles from unresolved state fan-out; applying the same restriction
        # to an already source-bound Reference would undo that routing and
        # incorrectly discard a valid literature comparison.
        if candidate_nodes and all(
            node.role == "Reference"
            or str(node.data_nature).startswith("Literature_")
            for node in candidate_nodes
        ):
            continue
        coordinate = _record_state(record)
        if not coordinate or not _TENSILE_STATE_COORDINATE.search(coordinate):
            continue
        evidence_key = record.normalized_evidence or (
            _scientific_fold("\n".join(_fact_evidence(fact))),
        )
        grouped.setdefault(
            ("|".join(evidence_key), _scientific_fold(coordinate)),
            [],
        ).append(record)

    removed: set[int] = set()
    issues: list[PromotionIssue] = []
    for rows in grouped.values():
        if not rows:
            continue
        # A source assertion with one or more explicit state-qualified tensile
        # rows is safe only if every row resolves to one existing owner.  The
        # resolver is intentionally applied per row so mixed-owner bundles do
        # not get collapsed into a shared base item.
        targets = [
            _tensile_state_coordinate_target(row.fact, graph)
            for row in rows
        ]
        if all(target is not None for target in targets):
            continue
        conflict = [row.fact.model_dump() for row in rows]
        for row in rows:
            removed.add(id(row.fact))
            issues.append(
                _promotion_issue(
                    row.fact,
                    code="promotion_tensile_state_bundle_ambiguous_quarantined",
                    message=(
                        "A source tensile assertion carried an explicit material "
                        "state, but that state did not resolve to one existing "
                        "current experimental owner; the complete metric bundle "
                        "was isolated instead of being attached to a generic base."
                    ),
                    expected={
                        "unique_existing_state_owner": True,
                        "owner_invented": False,
                        "bundle_broadcast": False,
                        "audit_preserved": True,
                    },
                    actual={
                        "removed": row.fact.model_dump(),
                        "state_coordinate": _record_state(row),
                        "candidate_owner": row.fact.sample_id_raw,
                        "bundle": conflict,
                    },
                    evidence=list(row.evidence),
                )
            )
    return [fact for fact in facts if id(fact) not in removed], issues


def _owner_gate(
    anchors: Sequence[InventoryAnchor],
    facts: Sequence[AxisFact],
    source_text: str,
) -> tuple[list[AxisFact], list[PromotionIssue]]:
    graph = build_owner_graph(anchors)
    if not graph.nodes:
        return list(facts), []
    blocks = _source_blocks(source_text)
    block_by_key = {block.key: block for block in blocks}
    records = build_promotion_records(facts)
    assertion_groups: dict[tuple[str, str], list[PromotionRecord]] = {}
    for record in records:
        source_key, _, ambiguous = _record_source_binding(record, blocks)
        if ambiguous:
            continue
        assertion_groups.setdefault(
            (source_key, record.semantic_signature), []
        ).append(record)

    reassigned: dict[int, AxisFact] = {}
    issues: list[PromotionIssue] = []
    for (source_key, _), rows in assertion_groups.items():
        if len({_identity_text(row.explicit_owner) for row in rows}) < 2:
            continue
        first = rows[0].fact
        if first.axis in {"composition", "processing"} or (
            isinstance(first, PropertyFact)
            and is_core_tensile_property_name(
                first.data.get("property_name_raw")
            )
        ):
            continue
        support = block_by_key[source_key].normalized_text
        if _has_collective_owner_scope(support):
            continue
        named_nodes = _source_owner_nodes(support, graph)
        if len(named_nodes) != 1:
            continue
        named_node = named_nodes[0]
        for row in rows:
            candidates = _candidate_nodes(row, graph)
            if any(node.owner_id == named_node.owner_id for node in candidates):
                continue
            before = row.fact
            after = _reassign_fact_owner(before, named_node.sample_id_raw)
            reassigned[id(before)] = after
            issues.append(
                _promotion_issue(
                    before,
                    code="promotion_owner_reassigned",
                    message=(
                        "A copied candidate was moved to the one existing owner "
                        "literally named by its source assertion."
                    ),
                    expected={
                        "source_explicit_owner": named_node.sample_id_raw,
                        "owner_id": named_node.owner_id,
                    },
                    actual={
                        "before": before.model_dump(),
                        "after": after.model_dump(),
                    },
                    evidence=list(row.evidence),
                )
            )

    accepted: list[AxisFact] = []
    routed_facts = [reassigned.get(id(fact), fact) for fact in facts]
    for record in build_promotion_records(routed_facts):
        resolution = resolve_record_owner(record, graph)
        fact = record.fact
        prose_owner_sensitive_axis = (
            isinstance(fact, (CompositionFact, ProcessingFact))
            and not _has_table_evidence(record.evidence)
            and not _has_collective_owner_scope("\n".join(record.evidence))
        )
        quarantine_ambiguous_owner = (
            isinstance(fact, PropertyFact)
            and not is_core_tensile_property_name(
                fact.data.get("property_name_raw")
            )
        ) or isinstance(fact, StructureFact) or prose_owner_sensitive_axis
        if (
            "ambiguous_owner" in resolution.risk_codes
            and quarantine_ambiguous_owner
            and not resolution.explicit_shared_owner_ids
        ):
            issues.append(
                _promotion_issue(
                    fact,
                    code="promotion_ambiguous_owner_quarantined",
                    message=(
                        "A fact could not be uniquely bound to one existing "
                        "material state."
                    ),
                    expected={"owner_count": 1, "broadcast": False},
                    actual={
                        "removed": fact.model_dump(),
                        "candidate_owner_ids": list(
                            resolution.candidate_owner_ids
                        ),
                    },
                )
            )
            continue
        accepted.append(fact)
    return accepted, issues


def _feedstock_owner_node(node: OwnerNode) -> bool:
    return bool(
        _FEEDSTOCK_OWNER_LABEL.search(
            " ".join(
                value
                for value in (
                    node.sample_id_raw,
                    node.material_name_raw,
                    node.state_raw,
                    *node.aliases,
                )
                if value
            )
        )
    )


def _quarantine_tensile_feedstock_result_mismatches(
    anchors: Sequence[InventoryAnchor],
    facts: Sequence[AxisFact],
) -> tuple[list[AxisFact], list[PromotionIssue]]:
    """Isolate tensile results copied onto a powder/feedstock owner.

    A powder owner may legitimately carry powder characterization, but a
    tensile quote that explicitly describes a sintered/printed/heat-treated
    specimen is a different material state.  This gate acts only when the
    candidate owner is source-declared feedstock and the candidate's own
    evidence contains a processed-result cue; powder tensile assertions with
    no such cue are preserved.  Explicit owner routing above runs first, so a
    uniquely named processed owner is reassigned rather than discarded.
    """

    graph = build_owner_graph(anchors)
    if not graph.nodes:
        return list(facts), []
    accepted: list[AxisFact] = []
    issues: list[PromotionIssue] = []
    for fact in facts:
        if not isinstance(fact, PropertyFact) or not is_core_tensile_property_name(
            fact.data.get("property_name_raw")
        ):
            accepted.append(fact)
            continue
        record = build_promotion_records([fact])[0]
        owner_nodes = _candidate_nodes(record, graph)
        if not owner_nodes or not all(_feedstock_owner_node(node) for node in owner_nodes):
            accepted.append(fact)
            continue
        evidence = _fact_evidence(fact)
        support = "\n".join(evidence)
        if not _TENSILE_PROCESSED_RESULT_SCOPE.search(support):
            accepted.append(fact)
            continue
        # A literal feedstock owner in the same assertion is a valid powder
        # result, even if the paragraph later discusses processed samples.
        if any(
            _literal_mention(support, alias)
            for node in owner_nodes
            for alias in _owner_evidence_aliases(node.sample_id_raw)
        ):
            accepted.append(fact)
            continue
        issues.append(
            _promotion_issue(
                fact,
                code="promotion_tensile_feedstock_result_owner_mismatch_quarantined",
                message=(
                    "A tensile result described a processed specimen but was "
                    "assigned to a powder/feedstock owner without a literal "
                    "feedstock binding."
                ),
                expected={
                    "owner_kind": "processed experimental specimen",
                    "feedstock_projection": False,
                    "audit_preserved": True,
                },
                actual={
                    "removed": fact.model_dump(),
                    "candidate_owners": [node.sample_id_raw for node in owner_nodes],
                    "reason": "processed_result_on_feedstock_owner",
                },
                evidence=evidence,
            )
        )
    return accepted, issues


def _quarantine_feedstock_composition_mismatches(
    anchors: Sequence[InventoryAnchor],
    facts: Sequence[AxisFact],
) -> tuple[list[AxisFact], list[PromotionIssue]]:
    """Keep powder/feedstock composition on a source-proven owner only.

    A composition sentence that explicitly describes powder/feedstock is not
    evidence for a later heat-treated or fabricated sample.  Existing explicit
    sample labels (for example ``H230 powder``) remain valid; otherwise the
    candidate is routed to one existing feedstock owner or isolated for review.
    No feedstock owner is invented here.
    """

    graph = build_owner_graph(anchors)
    if not graph.nodes:
        return list(facts), []
    accepted: list[AxisFact] = []
    issues: list[PromotionIssue] = []
    feedstock_nodes = tuple(
        node for node in graph.nodes if _feedstock_owner_node(node)
    )
    for fact in facts:
        # Feedstock wording is only a composition-owner hazard when the
        # candidate itself is a composition observation.  Material identity
        # anchors/facts can legitimately be described in the context of a
        # powder or feedstock and must remain available to the material graph.
        # Do not let this narrow ownership gate erase those identity records.
        if not (
            isinstance(fact, CompositionFact)
            and fact.fact_type == "composition_observation"
        ):
            accepted.append(fact)
            continue
        evidence = _fact_evidence(fact)
        support = "\n".join(evidence)
        if not _FEEDSTOCK_SCOPE.search(support):
            accepted.append(fact)
            continue
        candidate_nodes = _candidate_nodes(build_promotion_records([fact])[0], graph)
        explicit_candidate_owner = any(
            _safe_explicit_owner_label(node.sample_id_raw)
            and _literal_mention(support, node.sample_id_raw)
            for node in candidate_nodes
        )
        if explicit_candidate_owner or _FEEDSTOCK_OWNER_LABEL.search(
            str(fact.sample_id_raw or "")
        ):
            accepted.append(fact)
            continue
        if len(feedstock_nodes) == 1:
            target = feedstock_nodes[0]
            updated = _reassign_fact_owner(fact, target.sample_id_raw)
            accepted.append(updated)
            issues.append(
                _promotion_issue(
                    fact,
                    code="promotion_feedstock_owner_reassigned",
                    message=(
                        "A powder/feedstock composition was routed to the one "
                        "existing source-named feedstock owner."
                    ),
                    expected={
                        "source_owner": target.sample_id_raw,
                        "owner_kind": "feedstock_or_powder",
                        "invented_owner": False,
                        "audit_preserved": True,
                    },
                    actual={
                        "before": fact.model_dump(),
                        "after": updated.model_dump(),
                        "source_owner_id": target.owner_id,
                    },
                    evidence=evidence,
                )
            )
            continue
        # A bare/unresolved label cannot be safely attached to a fabricated or
        # heat-treated target.  Keep it in the normal audit stream rather than
        # allowing materialization to broadcast it across target states.
        issues.append(
            _promotion_issue(
                fact,
                code="promotion_feedstock_owner_mismatch_quarantined",
                message=(
                    "A composition assertion explicitly describes powder/feedstock "
                    "but no unique source-backed feedstock owner was available."
                ),
                expected={
                    "owner_kind": "explicit feedstock_or_powder owner",
                    "unique_existing_owner": True,
                    "broadcast": False,
                    "audit_preserved": True,
                },
                actual={
                    "removed": fact.model_dump(),
                    "candidate_owner_ids": [node.owner_id for node in candidate_nodes],
                    "feedstock_owner_ids": [node.owner_id for node in feedstock_nodes],
                },
                evidence=evidence,
            )
        )
    return accepted, issues


_COLLECTIVE_OWNER_SCOPE = re.compile(
    r"(?ix)(?:"
    r"\b(?:all|both|each|every)\b(?:\s+[a-z0-9#_-]+){0,5}\s+"
    r"(?:alloys|superalloys|samples|specimens|powders|walls|conditions)\b|"
    r"\bboth\b.{0,80}\band\b|"
    r"\band\b.{0,80}\b(?:alloys|superalloys|samples|specimens|powders|walls)\b|"
    r"\b(?:samples|alloys|superalloys|specimens|powders|walls)\s+"
    r"(?:\#?[a-z0-9_{}]+)\s*(?:-|–|—|to|through)\s*(?:\#?[a-z0-9_{}]+)\b|"
    r"\b(?:[a-z]+\s*-\s*and\s+[a-z]+-?)\s*"
    r"(?:samples|alloys|superalloys|specimens|powders|walls)\b|"
    r"\b(?:investigated|different|various|respective|boron-containing)\s+"
    r"(?:alloys|superalloys|samples|specimens|powders|walls)\b|"
    r"\b(?:samples|alloys|superalloys|specimens|powders|walls)\s+"
    r"(?:with|without|containing|inoculated|fabricated|processed|examined|"
    r"are|is|were|had|showed|exhibited|contained|consisted|displayed)\b"
    r")"
)


def _has_collective_owner_scope(value: str) -> bool:
    return bool(_COLLECTIVE_OWNER_SCOPE.search(value))


def _owner_evidence_aliases(value: str) -> tuple[str, ...]:
    """Return conservative source labels for a material-state owner string."""

    label = str(value or "").strip()
    if not label:
        return ()
    aliases = [label]
    bracket_base = re.sub(r"\s*\[[^\]]+\]\s*$", "", label).strip()
    if bracket_base and _identity_text(bracket_base) != _identity_text(label):
        aliases.append(bracket_base)
    return tuple(dict.fromkeys(aliases))


def _owner_value_local_pair(
    value: Any,
    evidence: Sequence[str],
    owner: str,
    sibling_owners: Sequence[str],
) -> bool:
    """Check a value/owner pair in one bounded prose window.

    A chunk's evidence may contain a complete comparison sentence and therefore
    mention every owner in the sentence.  This helper deliberately refuses to
    use sentence order as a coordinate.  A value is locally bound only when
    the candidate owner is the nearest literal owner and is close enough to
    look like a parenthetical/subject phrase.  For a chunk that contains no
    sibling owner at all, the wider clause window is safe because there is no
    competing material label to select.
    """

    text = _scientific_fold("\n".join(str(row or "") for row in evidence))
    if not text:
        return False
    value_tokens = _numeric_tokens(value)
    if not value_tokens:
        # Qualitative structural payloads are not handled by this numeric
        # fan-out gate; a literal owner/value pair is already checked by the
        # dedicated prose-owner gate.
        return False
    value_pattern = re.compile(
        rf"(?<![a-z0-9]){re.escape(value_tokens[0])}(?![a-z0-9])"
    )
    value_matches = list(value_pattern.finditer(text))
    if len(value_matches) != 1:
        return False
    value_position = value_matches[0].start()

    def positions(label: str) -> list[int]:
        result: list[int] = []
        for alias in _owner_evidence_aliases(label):
            folded = _scientific_fold(alias)
            if not folded:
                continue
            pattern = re.compile(
                rf"(?<![a-z0-9]){re.escape(folded)}(?![a-z0-9])"
            )
            result.extend(match.start() for match in pattern.finditer(text))
        return sorted(set(result))

    owner_positions = positions(owner)
    if not owner_positions:
        return False
    sibling_positions = [
        position
        for sibling in sibling_owners
        for position in positions(sibling)
    ]
    nearest_owner_distance = min(
        abs(position - value_position) for position in owner_positions
    )
    nearest_sibling_distance = (
        min(abs(position - value_position) for position in sibling_positions)
        if sibling_positions
        else None
    )
    if nearest_sibling_distance is None:
        return nearest_owner_distance <= 72
    # A competing owner in the same sentence is acceptable only for a compact
    # local pair (``H230AM (10 um)``).  A broad ordered list keeps both owners
    # far from every value and is therefore quarantined.
    return nearest_owner_distance <= 24 and (
        nearest_sibling_distance > nearest_owner_distance
    )


def _exact_evidence_mentions_owner(support: str, owner_label: str) -> bool:
    return any(
        _distinctive_owner_label(alias) and _literal_mention(support, alias)
        for alias in _owner_evidence_aliases(owner_label)
    )


def _quarantine_cross_owner_projections(
    facts: Sequence[AxisFact], source_text: str
) -> tuple[list[AxisFact], list[PromotionIssue]]:
    records = build_promotion_records(facts)
    blocks = _source_blocks(source_text)
    block_by_key = {block.key: block for block in blocks}
    grouped: dict[tuple[str, str], list[PromotionRecord]] = {}
    for record in records:
        if record.fact.axis == "composition" or (
            isinstance(record.fact, PropertyFact)
            and is_core_tensile_property_name(
                record.fact.data.get("property_name_raw")
            )
        ):
            continue
        source_key, _, ambiguous = _record_source_binding(record, blocks)
        if ambiguous:
            continue
        grouped.setdefault(
            (source_key, record.semantic_signature), []
        ).append(record)
    removed: set[int] = set()
    issues: list[PromotionIssue] = []
    for (source_key, _), rows in grouped.items():
        owners = {_identity_text(row.explicit_owner) for row in rows}
        if len(owners) < 2:
            continue
        evidence = list(
            dict.fromkeys(value for row in rows for value in row.evidence)
        )
        support = block_by_key[source_key].normalized_text
        mentioned = {
            _identity_text(row.explicit_owner)
            for row in rows
            if _distinctive_owner_label(row.explicit_owner)
            and _literal_mention(support, row.explicit_owner)
        }
        if _has_collective_owner_scope(support):
            continue
        if not mentioned:
            # A source block with no owner grammar cannot justify selecting a
            # survivor.  When the exact same semantic assertion was copied to
            # multiple owners, preserving every copy would turn ambiguity into
            # a set of apparently factual cross-item claims.  Isolate the whole
            # group; the complete candidates remain in the audit stream and a
            # reviewer can restore one only after checking the surrounding chunk.
            if not all(
                isinstance(row.fact, StructureFact)
                or (
                    isinstance(row.fact, PropertyFact)
                    and not is_core_tensile_property_name(
                        row.fact.data.get("property_name_raw")
                    )
                )
                for row in rows
            ):
                # Processing stages often carry a paper-level method statement
                # without an owner coordinate; preserving that stage is the
                # existing recall contract.  Dedicated process-owner gates deal
                # with numeric/result projections later in the pipeline.
                continue
            for row in rows:
                removed.add(id(row.fact))
                issues.append(
                    _promotion_issue(
                        row.fact,
                        code="promotion_ambiguous_shared_assertion_quarantined",
                        message=(
                            "An identical source assertion was copied to multiple "
                            "owners, but the quoted source block names none of "
                            "them; no owner was selected by confidence or order."
                        ),
                        expected={
                            "source_explicit_owner": True,
                            "shared_owner_grammar": False,
                            "unresolved_group_quarantined": True,
                            "audit_preserved": True,
                        },
                        actual={
                            "removed": row.fact.model_dump(),
                            "candidate_owners": sorted(owners),
                            "source_block_key": source_key,
                        },
                        evidence=evidence,
                    )
                )
            continue
        if mentioned == owners:
            continue
        winners = mentioned
        for row in rows:
            if _identity_text(row.explicit_owner) in winners:
                continue
            removed.add(id(row.fact))
            code = (
                "promotion_cross_owner_projection_quarantined"
                if winners
                else "promotion_ambiguous_shared_assertion_quarantined"
            )
            issues.append(
                _promotion_issue(
                    row.fact,
                    code=code,
                    message=(
                        "An identical source assertion was copied to an owner not "
                        "proved by that assertion."
                    ),
                    expected={
                        "explicit_owners": sorted(winners),
                        "shared_owner_grammar": False,
                        "unresolved_group_quarantined": not bool(winners),
                    },
                    actual={
                        "removed": row.fact.model_dump(),
                        "named_owners": sorted(winners),
                    },
                    evidence=evidence,
                )
            )
    return [fact for fact in facts if id(fact) not in removed], issues


_STRUCTURE_COLLECTIVE_RANGE_CUE = re.compile(
    r"(?ix)(?:"
    r"\b(?:samples?|specimens?|alloys?|conditions?|regions?)\s+"
    r"(?:[#№]?\s*[a-z]?\d+)\s*(?:-|–|—|to)\s*"
    r"(?:[#№]?\s*[a-z]?\d+)\b|"
    r"(?<![a-z0-9])([a-z]{1,3})(\d+)\s*(?:-|–|—|to)\s*"
    r"\1(\d+)(?![a-z0-9])"
    r")"
)
_STRUCTURE_COLLECTIVE_COMPARISON_CUE = re.compile(
    r"(?ix)\bfrom\s+[^\n]{0,100}\b[a-z]{1,3}\d+\b"
    r"[^\n]{0,100}\bto\s+[^\n]{0,100}\b[a-z]{1,3}\d+\b"
)


def _structure_is_entity_only(fact: StructureFact) -> bool:
    """Return whether a Structure fact has no atomic feature coordinate.

    Qualitative feature shadows (``nearly absent``, ``fine``, ``elongated``)
    are treated like entity-only payloads for a collective range assertion;
    scalar/range measurements and explicit presence/absence features remain
    protected.
    """

    def atomic(feature: Any) -> bool:
        return isinstance(feature, dict) and (
            _is_quantitative_structure_feature(feature)
            or _is_negated_structure_feature(feature)
        )

    if any(atomic(feature) for feature in fact.data.get("features") or []):
        return False
    return all(
        not any(atomic(feature) for feature in entity.get("features") or [])
        for entity in fact.data.get("entities") or []
        if isinstance(entity, dict)
    )


def _structure_collective_range_contains_owner(owner: str, support: str) -> bool:
    """Return whether a short numbered owner falls inside a cited range."""

    if _literal_mention(support, owner):
        return True
    owner_numbers = re.findall(r"\d+", str(owner or ""))
    if len(owner_numbers) != 1:
        return False
    number = int(owner_numbers[0])
    for match in _STRUCTURE_COLLECTIVE_RANGE_CUE.finditer(support):
        range_match = re.search(
            r"[#№]?\s*([A-Za-z]?)(\d+)\s*(?:-|–|—|to)\s*"
            r"[#№]?\s*([A-Za-z]?)(\d+)",
            match.group(),
        )
        if range_match is None:
            continue
        prefixes = {
            value.casefold()
            for value in (range_match.group(1), range_match.group(3))
            if value
        }
        bounds = [int(range_match.group(2)), int(range_match.group(4))]
        if len(bounds) != 2 or not bounds[0] <= number <= bounds[1]:
            continue
        # Avoid treating ``samples #1-#3`` as a binding for an unrelated
        # owner such as ``A2`` when the candidate carries a letter prefix.
        owner_prefix = re.sub(r"[^A-Za-z]+", "", str(owner or "")).casefold()
        if not owner_prefix or not prefixes or owner_prefix in prefixes:
            return True
    return False


def _quarantine_structure_collective_range_fanout(
    facts: Sequence[AxisFact], source_text: str
) -> tuple[list[AxisFact], list[PromotionIssue]]:
    """Isolate entity-only copies of a range-scoped prose assertion.

    Chunk-local extraction commonly turns one sentence such as ``samples
    #1-#3 contained columnar grains`` into one identical Structure observation
    for every inventory row that happens to be mentioned in the range.  The
    sentence proves a collective assertion, but the current item schema has no
    multi-owner field; retaining each copy therefore inflates the formal ledger
    and makes the same fact look independently observed for every owner.  This
    gate handles only prose range grammar and entity-only payloads.  Tables,
    ``both A and B`` assertions, and feature-level numeric measurements remain
    on their existing paths.
    """

    grouped: dict[tuple[str, tuple[str, ...]], list[PromotionRecord]] = {}
    for record in build_promotion_records(facts):
        if not (
            isinstance(record.fact, StructureFact)
            and record.fact.fact_type == "structure_observation"
            and _structure_is_entity_only(record.fact)
        ):
            continue
        evidence = tuple(row for row in record.normalized_evidence if row)
        if not evidence or _has_table_evidence(evidence):
            continue
        grouped.setdefault((record.semantic_signature, evidence), []).append(record)

    removed: set[int] = set()
    issues: list[PromotionIssue] = []
    for (_, evidence), rows in grouped.items():
        owners = {
            _identity_text(row.explicit_owner): row.explicit_owner
            for row in rows
            if _identity_text(row.explicit_owner)
        }
        if len(owners) < 2:
            continue
        support = "\n".join(evidence)
        range_scoped = _STRUCTURE_COLLECTIVE_RANGE_CUE.search(support) is not None
        comparison_scoped = (
            _STRUCTURE_COLLECTIVE_COMPARISON_CUE.search(support) is not None
            and _COMPARATIVE_ASSERTION_CUE.search(support) is not None
        )
        if not (range_scoped or comparison_scoped):
            continue
        if not all(
            _safe_explicit_owner_label(label)
            and _structure_collective_range_contains_owner(label, support)
            for label in owners.values()
        ):
            continue
        conflict = [row.fact.model_dump() for row in rows]
        for row in rows:
            removed.add(id(row.fact))
            issues.append(
                _promotion_issue(
                    row.fact,
                    code="promotion_structure_collective_range_fanout_quarantined",
                    message=(
                        "An entity-only Structure observation was copied to multiple "
                        "owners from one range-scoped prose assertion. The source "
                        "proves a collective range, not one independent owner fact; "
                        "all copies were isolated for review."
                    ),
                    expected={
                        "one_to_one_owner_coordinate": True,
                        "collective_range_broadcast": False,
                        "numeric_feature_untouched": True,
                        "audit_preserved": True,
                    },
                    actual={
                        "removed": row.fact.model_dump(),
                        "conflict_set": conflict,
                        "owners": list(owners.values()),
                        "reason": "entity_only_collective_range_fanout",
                    },
                    evidence=list(row.evidence),
                )
            )
    return [fact for fact in facts if id(fact) not in removed], issues


def _quarantine_evidence_explicit_owner_mismatches(
    anchors: Sequence[InventoryAnchor],
    facts: Sequence[AxisFact],
    source_text: str,
) -> tuple[list[AxisFact], list[PromotionIssue]]:
    """Isolate facts whose own prose quote names a different sole owner.

    The broader promotion gates operate on one semantic assertion group.  A
    high-recall chunk can still emit two different semantic projections from
    one sentence, however, and therefore evade that grouping.  This gate uses
    only the candidate's copied evidence, never confidence or output order:

    * the evidence must bind to one unambiguous prose source block;
    * that evidence must literally name exactly one distinctive inventory owner;
    * collective/shared-owner grammar and all Markdown tables are excluded;
    * Composition, Processing, Structure/Characterization, and non-core
      Properties are eligible; core tensile remains on its dedicated owner
      gates.

    If a candidate's explicit owner differs from that sole source owner, the
    complete candidate is quarantined and retained in the normal audit stream.
    Ambiguous, table-based, owner-implicit, Composition, Processing, and core
    tensile records are preserved for downstream handling.
    """

    graph = build_owner_graph(anchors)
    if not graph.nodes:
        return list(facts), []
    blocks = _source_blocks(source_text)
    removed: set[int] = set()
    issues: list[PromotionIssue] = []

    eligible = [
        fact
        for fact in facts
        if isinstance(fact, (CompositionFact, ProcessingFact, StructureFact))
        or (
            isinstance(fact, PropertyFact)
            and not is_core_tensile_property_name(
                fact.data.get("property_name_raw")
            )
        )
    ]
    for record in build_promotion_records(eligible):
        # This rule is intentionally prose-only.  A table row/header can name
        # several owners while one cell belongs to only one of them; without a
        # parsed cell coordinate it is not safe to infer a mismatch here.
        if _has_table_evidence(record.evidence):
            continue
        source_key, source_kind, ambiguous = _record_source_binding(record, blocks)
        if ambiguous or source_kind != "prose":
            continue
        evidence = "\n".join(record.evidence)
        if not evidence.strip() or _has_collective_owner_scope(evidence):
            continue
        named_nodes = _safe_source_owner_nodes(evidence, graph)
        if len(named_nodes) != 1:
            continue
        named_node = named_nodes[0]
        if any(
            node.owner_id == named_node.owner_id
            for node in _candidate_nodes(record, graph)
        ):
            continue
        removed.add(id(record.fact))
        issues.append(
            _promotion_issue(
                record.fact,
                code="promotion_evidence_explicit_owner_mismatch_quarantined",
                message=(
                    "The copied prose evidence names one existing material owner, "
                    "but the candidate was assigned to a different owner."
                ),
                expected={
                    "source_explicit_owner": named_node.sample_id_raw,
                    "unique_source_owner": True,
                    "shared_owner_grammar": False,
                    "source_kind": "prose",
                    "audit_preserved": True,
                },
                actual={
                    "removed": record.fact.model_dump(),
                    "copied_owner": record.explicit_owner,
                    "source_owner": named_node.sample_id_raw,
                    "source_owner_id": named_node.owner_id,
                    "source_block_key": source_key,
                },
                evidence=list(record.evidence),
            )
        )
    return [fact for fact in facts if id(fact) not in removed], issues


def _prose_owner_value_descriptor(
    fact: AxisFact,
) -> tuple[str, str, tuple[str, ...]] | None:
    """Return one conservative owner/value descriptor for a prose fact.

    This helper deliberately accepts only a single numeric claim.  A complete
    table-cell parser belongs upstream; trying to infer several values from one
    candidate here would risk deleting a valid column binding.  The descriptor
    is therefore limited to one top-level Structure feature or one non-core
    Property value, and is used only by the ordered prose gate below.
    """

    if isinstance(fact, StructureFact):
        features: list[dict[str, Any]] = []
        for row in fact.data.get("features") or []:
            if isinstance(row, dict):
                features.append(row)
        for entity in fact.data.get("entities") or []:
            if not isinstance(entity, dict):
                continue
            for row in entity.get("features") or []:
                if isinstance(row, dict):
                    features.append(row)
        if len(features) != 1:
            return None
        feature = features[0]
        value_raw = feature.get("value_raw")
        tokens = _numeric_tokens(value_raw)
        name = _scientific_fold(feature.get("feature_name_raw"))
        kind = _scientific_fold(fact.data.get("structure_kind"))
        if not name or not tokens:
            return None
        return ("structure", f"{kind}|{name}", tokens)

    if isinstance(fact, PropertyFact):
        value_raw = fact.data.get("value_raw")
        tokens = _numeric_tokens(value_raw)
        name = _scientific_fold(fact.data.get("property_name_raw"))
        if not name or not tokens:
            return None
        if is_core_tensile_property_name(name):
            # Core tensile prose is eligible only for the same conservative
            # one-value/order mapping used by Structure. Tables and multi-value
            # cells are still excluded by the caller's prose-only binding gate.
            return (
                "property",
                "|".join(
                    (
                        _core_tensile_family(name),
                        core_tensile_subtype(name),
                        _scientific_fold(fact.data.get("unit_raw")),
                        _scientific_fold(fact.data.get("test_condition_raw")),
                    )
                ),
                tokens,
            )
        return ("property", name, tokens)

    return None


def _ordered_owner_mentions(
    support: str,
    graph: OwnerGraph,
) -> list[tuple[str, int]]:
    """Find unique base-owner labels in their literal prose order."""

    normalized_support = _identity_text(support)
    if not normalized_support:
        return []
    by_base: dict[str, list[int]] = {}
    for node in graph.nodes:
        if not _safe_explicit_owner_label(node.sample_id_raw):
            continue
        base = _identity_text(
            re.sub(r"\s*\[[^\]]+\]\s*$", "", node.sample_id_raw).strip()
        )
        if not base:
            continue
        positions: list[int] = []
        for alias in sorted(
            _owner_evidence_aliases(node.sample_id_raw),
            key=lambda value: len(_identity_text(value)),
            reverse=True,
        ):
            needle = _identity_text(alias)
            if not needle:
                continue
            positions.extend(
                match.start()
                for match in re.finditer(
                    rf"(?<![a-z0-9]){re.escape(needle)}(?![a-z0-9])",
                    normalized_support,
                )
            )
            # The full state label is preferred; a shorter base alias is only a
            # fallback when the state-qualified label is absent.
            if positions and "[" in str(alias):
                break
        if positions:
            by_base.setdefault(base, []).extend(positions)
    ordered = [
        (base, min(positions))
        for base, positions in by_base.items()
        if positions
    ]
    return sorted(ordered, key=lambda row: (row[1], row[0]))


def _numeric_value_positions(
    value_tokens: tuple[str, ...],
    support: str,
) -> tuple[int, ...]:
    """Return literal positions for one candidate value, or no result if noisy."""

    normalized_support = _scientific_fold(support)
    if not normalized_support or not value_tokens:
        return ()
    positions: list[int] = []
    cursor = 0
    for token in value_tokens:
        match = re.search(
            rf"(?<![a-z0-9]){re.escape(token.casefold())}(?![a-z0-9])",
            normalized_support[cursor:],
        )
        if match is None:
            return ()
        absolute = cursor + match.start()
        positions.append(absolute)
        cursor = cursor + match.end()
    # A value repeated in the same source block cannot be safely paired with
    # one owner by order alone.  The caller treats an ambiguous position as a
    # preserve decision.
    return tuple(positions)


def _quarantine_prose_owner_value_mismatches(
    anchors: Sequence[InventoryAnchor],
    facts: Sequence[AxisFact],
    source_text: str,
) -> tuple[list[AxisFact], list[PromotionIssue]]:
    """Quarantine swapped owner/value pairs from explicit prose enumerations.

    Example handled safely: ``grain sizes of H230 and H230AM ... were 13.2 µm
    and 10.9 µm``.  The gate requires one prose source block, unique owner
    labels, one single-value fact per owner, and a one-to-one order-preserving
    value mapping.  Tables, compositions, repeated labels, and ambiguous value
    occurrences are intentionally preserved.  Core tensile prose is admitted
    only in this same single-value/order-mapping shape.
    """

    graph = build_owner_graph(anchors)
    if not graph.nodes:
        return list(facts), []
    blocks = _source_blocks(source_text)
    block_by_key = {block.key: block for block in blocks}
    grouped: dict[tuple[str, str, str], list[PromotionRecord]] = {}
    for record in build_promotion_records(facts):
        descriptor = _prose_owner_value_descriptor(record.fact)
        if descriptor is None:
            continue
        source_key, source_kind, ambiguous = _record_source_binding(
            record, blocks
        )
        if ambiguous or source_kind != "prose":
            continue
        grouped.setdefault(
            (source_key, descriptor[0], descriptor[1]), []
        ).append(record)

    removed: set[int] = set()
    issues: list[PromotionIssue] = []
    for (source_key, _, _), rows in grouped.items():
        # Use the candidate-copied span itself for owner/value order.  A source
        # block may contain an entire paragraph with several later mentions of
        # the same owners and numbers; using that paragraph would manufacture a
        # false swap.  Every member must quote the same normalized span before
        # this local pairing is attempted.
        evidence_sets = {row.normalized_evidence for row in rows}
        if len(evidence_sets) != 1:
            continue
        support = "\n".join(rows[0].evidence)
        owners = _ordered_owner_mentions(support, graph)
        if len(owners) < 2 or len({base for base, _ in owners}) != len(owners):
            continue
        owner_order = {base: index for index, (base, _) in enumerate(owners)}
        row_values: list[tuple[PromotionRecord, str, int]] = []
        for row in rows:
            descriptor = _prose_owner_value_descriptor(row.fact)
            if descriptor is None:
                continue
            candidate_base = _identity_text(
                re.sub(
                    r"\s*\[[^\]]+\]\s*$",
                    "",
                    row.explicit_owner,
                ).strip()
            )
            if candidate_base not in owner_order:
                continue
            positions = _numeric_value_positions(descriptor[2], support)
            if len(positions) != len(descriptor[2]):
                row_values = []
                break
            row_values.append((row, candidate_base, positions[0]))
        if len(row_values) != len(owners):
            continue
        if len({base for _, base, _ in row_values}) != len(row_values):
            continue
        value_order = sorted(
            row_values,
            key=lambda item: (item[2], item[1], item[0].claim_id),
        )
        if len({position for _, _, position in value_order}) != len(value_order):
            continue
        for expected_index, (row, candidate_base, value_position) in enumerate(
            value_order
        ):
            if owner_order.get(candidate_base) == expected_index:
                continue
            removed.add(id(row.fact))
            issues.append(
                _promotion_issue(
                    row.fact,
                    code="promotion_prose_owner_value_mismatch_quarantined",
                    message=(
                        "A prose enumeration paired this candidate's value with "
                        "a different explicit material owner; the copied fact was "
                        "isolated without changing table or ambiguous bindings."
                    ),
                    expected={
                        "ordered_owner": owners,
                        "candidate_owner_index": owner_order.get(candidate_base),
                        "value_index": expected_index,
                        "audit_preserved": True,
                    },
                    actual={
                        "removed": row.fact.model_dump(),
                        "candidate_owner": row.explicit_owner,
                        "candidate_owner_base": candidate_base,
                        "value_position": value_position,
                        "source_block_key": source_key,
                    },
                    evidence=list(row.evidence),
                )
            )
    return [fact for fact in facts if id(fact) not in removed], issues


def _quarantine_structure_exact_evidence_projections(
    facts: Sequence[AxisFact],
) -> tuple[list[AxisFact], list[PromotionIssue]]:
    """Remove a whole Structure copy disproved by its exact evidence owner."""

    records = build_promotion_records(facts)
    grouped: dict[tuple[str, tuple[str, ...]], list[PromotionRecord]] = {}
    for record in records:
        if not (
            isinstance(record.fact, StructureFact)
            and record.fact.fact_type == "structure_observation"
        ):
            continue
        exact_evidence = tuple(
            row for row in record.normalized_evidence if row
        )
        if not exact_evidence:
            continue
        grouped.setdefault(
            (record.semantic_signature, exact_evidence), []
        ).append(record)

    removed: set[int] = set()
    issues: list[PromotionIssue] = []
    for (_, exact_evidence), rows in grouped.items():
        owners = {
            _identity_text(row.explicit_owner): row.explicit_owner
            for row in rows
            if _identity_text(row.explicit_owner)
        }
        if len(owners) < 2:
            continue
        support = "\n".join(exact_evidence)
        if _has_collective_owner_scope(support):
            continue
        named_owner_ids = {
            owner_id
            for owner_id, owner_label in owners.items()
            if _exact_evidence_mentions_owner(support, owner_label)
        }
        if len(named_owner_ids) != 1:
            continue
        named_owner_id = next(iter(named_owner_ids))
        named_owner_label = owners[named_owner_id]
        grounded_survivors = [
            row.fact.model_dump()
            for row in rows
            if _identity_text(row.explicit_owner) == named_owner_id
        ]
        evidence = list(rows[0].evidence)
        for row in rows:
            if _identity_text(row.explicit_owner) == named_owner_id:
                continue
            removed.add(id(row.fact))
            issues.append(
                _promotion_issue(
                    row.fact,
                    code=(
                        "promotion_structure_exact_evidence_owner_projection_"
                        "quarantined"
                    ),
                    message=(
                        "An identical Structure observation was copied to an "
                        "owner not named by its exact source evidence."
                    ),
                    expected={
                        "source_explicit_owner": named_owner_label,
                        "identical_semantic_payload": True,
                        "exact_normalized_evidence": True,
                        "shared_owner_grammar": False,
                        "audit_preserved": True,
                    },
                    actual={
                        "removed": row.fact.model_dump(),
                        "copied_owner": row.explicit_owner,
                        "source_named_survivors": grounded_survivors,
                    },
                    evidence=evidence,
                )
            )
    return [fact for fact in facts if id(fact) not in removed], issues


def _quarantine_composition_exact_evidence_projections(
    facts: Sequence[AxisFact],
) -> tuple[list[AxisFact], list[PromotionIssue]]:
    """Quarantine Composition copies contradicted by their exact evidence owner.

    Composition is protected from paragraph-level owner inference.  This gate
    acts only when multiple owners carry the same semantic payload and the
    exact same normalized evidence tuple.  That already evidence-gated tuple
    must name exactly one distinctive candidate owner and contain no
    collective-owner grammar.  Different evidence, values, table columns, or
    source-explicit shared owners therefore remain untouched.  Using the tuple
    instead of a containing OCR paragraph also tolerates audited plain-text
    versus Markdown/LaTeX formula presentation differences.
    """

    records = build_promotion_records(facts)
    grouped: dict[tuple[str, tuple[str, ...]], list[PromotionRecord]] = {}
    for record in records:
        if not (
            isinstance(record.fact, CompositionFact)
            and record.fact.fact_type == "composition_observation"
        ):
            continue
        exact_evidence = tuple(
            row for row in record.normalized_evidence if row
        )
        if not exact_evidence:
            continue
        grouped.setdefault(
            (record.semantic_signature, exact_evidence), []
        ).append(record)

    removed: set[int] = set()
    issues: list[PromotionIssue] = []
    for (_, exact_evidence), rows in grouped.items():
        owners = {
            _identity_text(row.explicit_owner): row.explicit_owner
            for row in rows
            if _identity_text(row.explicit_owner)
        }
        if len(owners) < 2:
            continue
        support = "\n".join(exact_evidence)
        if _has_collective_owner_scope(support):
            continue
        named_owner_ids = {
            owner_id
            for owner_id, owner_label in owners.items()
            if _exact_evidence_mentions_owner(support, owner_label)
        }
        if len(named_owner_ids) != 1:
            continue
        named_owner_id = next(iter(named_owner_ids))
        named_owner_label = owners[named_owner_id]
        grounded_survivors = [
            row.fact.model_dump()
            for row in rows
            if _identity_text(row.explicit_owner) == named_owner_id
        ]
        evidence = list(rows[0].evidence)
        for row in rows:
            if _identity_text(row.explicit_owner) == named_owner_id:
                continue
            removed.add(id(row.fact))
            issues.append(
                _promotion_issue(
                    row.fact,
                    code=(
                        "promotion_composition_cross_owner_projection_"
                        "quarantined"
                    ),
                    message=(
                        "An identical Composition assertion was copied to an "
                        "owner not named by its exact source evidence."
                    ),
                    expected={
                        "source_explicit_owner": named_owner_label,
                        "identical_semantic_payload": True,
                        "exact_normalized_evidence": True,
                        "shared_owner_grammar": False,
                        "audit_preserved": True,
                    },
                    actual={
                        "removed": row.fact.model_dump(),
                        "copied_owner": row.explicit_owner,
                        "source_named_survivors": grounded_survivors,
                    },
                    evidence=evidence,
                )
            )
    return [fact for fact in facts if id(fact) not in removed], issues


_COMPARATIVE_ASSERTION_CUE = re.compile(
    r"(?ix)\b(?:respectively|more|less|higher|lower|greater|fewer|"
    r"increased|decreased|reduced|rose|fell|compared|times|than)\b"
)


def _quarantine_comparative_owner_duplicates(
    facts: Sequence[AxisFact],
) -> tuple[list[AxisFact], list[PromotionIssue]]:
    """Isolate identical owner projections from an ordered comparison.

    A comparison sentence can be copied verbatim into every named material
    item.  If the semantic payload is also identical, the source has not
    proven that the *same* observation belongs to each owner: it has only
    supplied a relationship (for example, PBF-EB 42.3% versus PBF-LB 7.34%).
    Collective assertions (``both alloys ...``/``samples #1-#3``) are kept.
    """

    records = build_promotion_records(facts)
    grouped: dict[tuple[str, tuple[str, ...]], list[PromotionRecord]] = {}
    for record in records:
        if not isinstance(record.fact, (PropertyFact, StructureFact)):
            continue
        evidence = tuple(row for row in record.normalized_evidence if row)
        if not evidence:
            continue
        grouped.setdefault((record.semantic_signature, evidence), []).append(record)

    removed: set[int] = set()
    issues: list[PromotionIssue] = []
    for (semantic, evidence), rows in grouped.items():
        owners = {
            _identity_text(row.explicit_owner): row.explicit_owner for row in rows
        }
        if len(owners) < 2:
            continue
        support = "\n".join(evidence)
        if _has_collective_owner_scope(support) or not _COMPARATIVE_ASSERTION_CUE.search(
            support
        ):
            continue
        if not all(
            _safe_explicit_owner_label(label)
            and _exact_evidence_mentions_owner(support, label)
            for label in owners.values()
        ):
            continue
        conflict = [row.fact.model_dump() for row in rows]
        for row in rows:
            removed.add(id(row.fact))
            issues.append(
                _promotion_issue(
                    row.fact,
                    code="promotion_comparative_owner_duplicate_quarantined",
                    message=(
                        "An ordered comparison was copied as an identical fact "
                        "to multiple explicitly named owners; the unbound "
                        "projection was isolated instead of broadcast."
                    ),
                    expected={
                        "owner_specific_payload": True,
                        "collective_assertion": False,
                        "broadcast": False,
                        "audit_preserved": True,
                    },
                    actual={
                        "removed": row.fact.model_dump(),
                        "conflict_set": conflict,
                        "owners": list(owners.values()),
                        "semantic_signature": semantic,
                    },
                    evidence=list(row.evidence),
                )
            )
    return [fact for fact in facts if id(fact) not in removed], issues


def _core_tensile_family(value: Any) -> str:
    text = _scientific_fold(value)
    if re.search(
        r"\b(?:uts|ultimate tensile strength|tensile strength)\b",
        text,
    ):
        return "uts"
    if re.search(r"\b(?:ys|yield strength|yield stress)\b", text):
        return "ys"
    if re.search(r"\b(?:te|eab|elongation|ductility)\b", text):
        return "elongation"
    return ""


_TENSILE_THRESHOLD_LITERAL = re.compile(
    r"(?ix)^\s*(?P<operator>>=|<=|≥|≤|>|<)\s*"
    r"(?P<bound>[-+]?\d+(?:\.\d+)?(?:e[-+]?\d+)?)"
    r"(?:\s*(?:gpa|mpa|kpa|pa|%))?\s*$"
)
_TENSILE_APPROXIMATE_SCALAR = re.compile(
    r"(?ix)(?:~|≈|\b(?:approx(?:imately)?|about|around|roughly|nearly)\b)"
)
_RAW_NUMBER = re.compile(
    r"(?i)(?<![A-Za-z0-9])[-+]?\d+(?:\.\d+)?(?:e[-+]?\d+)?"
)


@dataclass(frozen=True)
class _TensileThreshold:
    operator: Literal[">", ">=", "<", "<="]
    bound: float


@dataclass(frozen=True)
class _TensileThresholdBinding:
    bounded_source_proposition: str
    nested_owner_value_phrase: str


@dataclass(frozen=True)
class _TensileOwnerCoordinate:
    key: str
    label: str
    owner_ids: tuple[str, ...]
    role: str
    data_nature: str
    kind: Literal["resolved", "identical_candidate_envelope"]


@dataclass(frozen=True)
class _TensileScalarShape:
    central: float
    uncertainty: float | None
    central_decimal_places: int
    unit_key: str
    unit_dimension: Literal["pressure", "percent"]
    unit_scale: float
    canonical_central: float
    canonical_uncertainty: float | None


@dataclass(frozen=True)
class _GenericTensileSummaryBinding:
    proposition: str
    collective_scope: str
    result_cue: str
    material_lineage: str


@dataclass(frozen=True)
class _TensileGroupExtremumBinding:
    proposition: str
    extremum_cue: str
    collective_scope: str
    companion_family: str
    companion_constraint: str
    named_owner_ids: tuple[str, ...]
    owner_ids: tuple[str, ...]
    owner_candidate_ids: tuple[str, ...]
    owner_coordinate_kind: str


_TENSILE_SCALAR_LITERAL = re.compile(
    r"(?ix)^\s*"
    r"(?P<central>[-+]?\d+(?:\.\d+)?(?:e[-+]?\d+)?)\s*"
    r"(?:"
    r"(?:±|\+/-|\\pm|plus\s*/?\s*minus)\s*"
    r"(?P<uncertainty>[-+]?\d+(?:\.\d+)?(?:e[-+]?\d+)?)\s*"
    r")?"
    r"(?P<unit>gpa|mpa|kpa|pa|%)?\s*$"
)
_TENSILE_PRESSURE_UNIT_SCALE = {
    "pa": 1.0,
    "kpa": 1_000.0,
    "mpa": 1_000_000.0,
    "gpa": 1_000_000_000.0,
}
_GENERIC_TENSILE_SUMMARY_RESULT = re.compile(
    r"(?ix)\b(?:"
    r"(?:are|were|was|is)\s+(?:successfully\s+)?"
    r"(?:produced|fabricated|developed|obtained|achieved)|"
    r"achieved|attained|demonstrated|delivered|exhibited"
    r")\b"
)
_GENERIC_TENSILE_SUMMARY_STATISTIC = re.compile(
    r"(?ix)\b(?:average|averaged|mean|median|replicate|standard\s+deviation|"
    r"distribution|range|minimum|maximum|highest|lowest|record)\b"
)
_COLLECTIVE_TENSILE_OWNER_LABEL = re.compile(
    r"(?ix)\b(?:alloys|samples|specimens|materials|parts|coupons|"
    r"conditions|combinations|dataset|table\s*\d*)\b"
)
_TENSILE_EXTREMUM_CUE = re.compile(
    r"(?ix)\b(?P<cue>highest|maximum|maximal|largest|best)\b"
)
_TENSILE_EXTREMUM_SCOPE = re.compile(
    r"(?ix)\b(?P<scope>(?:among|in)\s+(?:the\s+)?"
    r"(?:(?:different|various|tested|investigated)\s+)?"
    r"(?:parameter\s+combinations|alloys|samples|specimens|materials|"
    r"conditions|combinations))\b"
)
_TENSILE_EXTREMUM_CONSTRAINT = re.compile(
    r"(?ix)\b(?:with|having|near|around|satisfying|subject\s+to)\b"
    r"(?P<constraint>[^.;]{0,180})"
)
_TENSILE_FAMILY_PATTERNS = {
    "uts": re.compile(
        r"(?ix)\b(?:uts|ultimate\s+tensile\s+strength|tensile\s+strength)\b"
    ),
    "ys": re.compile(r"(?ix)\b(?:ys|yield\s+(?:strength|stress))\b"),
    "elongation": re.compile(
        r"(?ix)\b(?:te|eab|(?:total\s+|uniform\s+|fracture\s+)?"
        r"elongation|ductility)\b"
    ),
}


def _decimal_places(raw: str) -> int:
    mantissa = str(raw or "").casefold().split("e", 1)[0]
    return len(mantissa.split(".", 1)[1]) if "." in mantissa else 0


def _tensile_scalar_shape(fact: PropertyFact) -> _TensileScalarShape | None:
    """Parse only one exact scalar, optionally with explicit uncertainty."""

    raw = str(fact.data.get("value_raw") or "").strip()
    if not raw or _TENSILE_APPROXIMATE_SCALAR.search(raw):
        return None
    if re.search(r"(?:>=|<=|[<>≥≤])", raw) or re.search(
        r"(?<=\d)\s*[-–—~]\s*(?=\d)", raw
    ):
        return None
    cleaned = raw.replace("$", "")
    cleaned = re.sub(
        r"\\(?:mathrm|text)\s*\{([^{}]*)\}", r"\1", cleaned
    )
    match = _TENSILE_SCALAR_LITERAL.fullmatch(cleaned)
    if match is None:
        return None
    try:
        central = float(match.group("central"))
        uncertainty = (
            float(match.group("uncertainty"))
            if match.group("uncertainty") is not None
            else None
        )
    except ValueError:
        return None
    if not math.isfinite(central) or (
        uncertainty is not None
        and (not math.isfinite(uncertainty) or uncertainty < 0)
    ):
        return None
    declared_unit = _generic_unit_key(fact.data.get("unit_raw"))
    literal_unit = _generic_unit_key(match.group("unit"))
    if literal_unit and declared_unit and literal_unit != declared_unit:
        return None
    unit_key = declared_unit or literal_unit
    family = _core_tensile_family(fact.data.get("property_name_raw"))
    if family in {"uts", "ys"}:
        if unit_key not in _TENSILE_PRESSURE_UNIT_SCALE:
            return None
        dimension: Literal["pressure", "percent"] = "pressure"
        scale = _TENSILE_PRESSURE_UNIT_SCALE[unit_key]
    elif family == "elongation":
        if unit_key != "%":
            return None
        dimension = "percent"
        scale = 1.0
    else:
        return None
    return _TensileScalarShape(
        central=central,
        uncertainty=uncertainty,
        central_decimal_places=_decimal_places(match.group("central")),
        unit_key=unit_key,
        unit_dimension=dimension,
        unit_scale=scale,
        canonical_central=central * scale,
        canonical_uncertainty=(
            uncertainty * scale if uncertainty is not None else None
        ),
    )


def _tensile_families_in_text(value: Any) -> tuple[str, ...]:
    text = _scientific_fold(value)
    return tuple(
        family
        for family, pattern in _TENSILE_FAMILY_PATTERNS.items()
        if pattern.search(text)
    )


def _bounded_scalar_proposition(
    fact: PropertyFact,
    scalar: float,
) -> str | None:
    candidates: dict[str, str] = {}
    for evidence in _fact_evidence(fact):
        for raw in _TENSILE_SENTENCE_BOUNDARY.split(str(evidence or "")):
            proposition = raw.strip().rstrip(".;")
            if not proposition:
                continue
            if len(_numeric_spans_for_value(scalar, proposition)) != 1:
                continue
            normalized = normalize_evidence_text(proposition)
            if normalized:
                candidates[normalized] = proposition
    return next(iter(candidates.values())) if len(candidates) == 1 else None


def _material_lineage_key(value: Any) -> str:
    text = _scientific_fold(value)
    if text in _UNREPORTED:
        return ""
    text = re.sub(
        r"\b(?:alloy|alloys|material|materials)\s*$", "", text
    ).strip()
    return text if text not in _UNREPORTED else ""


def _fact_material_lineages(
    fact: PropertyFact,
    owner: _TensileOwnerCoordinate,
    graph: OwnerGraph,
) -> tuple[str, ...]:
    sample = _identity_text(fact.sample_id_raw)
    keys = {
        key
        for node in graph.nodes
        if node.role == owner.role
        and node.data_nature == owner.data_nature
        and (
            node.owner_id in owner.owner_ids
            or _identity_text(node.sample_id_raw) == sample
        )
        if (key := _material_lineage_key(node.material_name_raw))
    }
    return tuple(sorted(keys))


def _collective_owner_label(value: Any) -> bool:
    folded = _scientific_fold(value)
    return folded in _UNREPORTED or bool(
        _COLLECTIVE_TENSILE_OWNER_LABEL.search(folded)
    )


def _concrete_tensile_survivor(
    fact: PropertyFact,
    shape: _TensileScalarShape,
) -> bool:
    owner = str(fact.sample_id_raw or "").strip()
    if not _safe_explicit_owner_label(owner) or _collective_owner_label(owner):
        return False
    support = "\n".join(_fact_evidence(fact))
    if not _literal_mention(support, owner):
        return False
    table_bound = (
        _scientific_fold(fact.data.get("data_source")) == "table"
        and _has_table_evidence(_fact_evidence(fact))
    )
    return bool(
        table_bound
        or shape.uncertainty is not None
        or shape.central_decimal_places > 0
    )


def _generic_summary_binding(
    fact: PropertyFact,
    shape: _TensileScalarShape,
    graph: OwnerGraph,
) -> tuple[str, str, str] | None:
    if shape.uncertainty is not None or _has_table_evidence(_fact_evidence(fact)):
        return None
    if _scientific_fold(fact.data.get("data_source")) == "table":
        return None
    proposition = _bounded_scalar_proposition(fact, shape.central)
    if proposition is None:
        return None
    folded = _scientific_fold(proposition)
    if "respectively" not in folded or not _has_collective_owner_scope(folded):
        return None
    if _GENERIC_TENSILE_SUMMARY_STATISTIC.search(folded):
        return None
    result_match = _GENERIC_TENSILE_SUMMARY_RESULT.search(folded)
    if result_match is None:
        return None
    family = _core_tensile_family(fact.data.get("property_name_raw"))
    families = _tensile_families_in_text(folded)
    if family not in families or len(families) < 2:
        return None
    named = [
        node
        for node in _safe_source_owner_nodes(proposition, graph)
        if _identity_text(node.sample_id_raw)
        != _identity_text(fact.sample_id_raw)
        and not _collective_owner_label(node.sample_id_raw)
    ]
    if named:
        return None
    collective_match = _COLLECTIVE_OWNER_SCOPE.search(folded)
    if collective_match is None:
        return None
    return proposition, collective_match.group(0), result_match.group(0)


def _same_tensile_summary_coordinate(
    generic: PropertyFact,
    generic_shape: _TensileScalarShape,
    survivor: PropertyFact,
    survivor_shape: _TensileScalarShape,
    graph: OwnerGraph,
    summary_proposition: str,
) -> tuple[str, _TensileOwnerCoordinate, _TensileOwnerCoordinate] | None:
    generic_family = _core_tensile_family(generic.data.get("property_name_raw"))
    survivor_family = _core_tensile_family(survivor.data.get("property_name_raw"))
    if generic_family != survivor_family:
        return None
    if core_tensile_subtype(generic.data.get("property_name_raw")) != (
        core_tensile_subtype(survivor.data.get("property_name_raw"))
    ):
        return None
    if generic_shape.unit_dimension != survivor_shape.unit_dimension:
        return None
    if not math.isclose(
        generic_shape.canonical_central,
        survivor_shape.canonical_central,
        rel_tol=1e-12,
        abs_tol=1e-9,
    ):
        return None
    if _scientific_fold(generic.data.get("test_condition_raw")) != (
        _scientific_fold(survivor.data.get("test_condition_raw"))
    ):
        return None
    generic_owner = _tensile_owner_coordinate(generic, graph)
    if generic_owner is not None and generic_owner.kind != "resolved":
        generic_owner = None
    if generic_owner is None:
        record = build_promotion_records([generic])[0]
        resolution = resolve_record_owner(record, graph)
        proposition_key = normalize_evidence_text(summary_proposition).rstrip(
            " .;"
        )
        source_bound = [
            graph.node(owner_id)
            for owner_id in resolution.candidate_owner_ids
            if any(
                proposition_key
                and proposition_key
                == normalize_evidence_text(source_evidence).rstrip(" .;")
                for source_evidence in graph.node(owner_id).source_evidence
            )
        ]
        # A generic material label can expand to many state anchors.  Reuse
        # one only when its own source declaration is exactly this headline;
        # never select a state by material-name similarity or candidate order.
        if len(source_bound) == 1:
            node = source_bound[0]
            generic_owner = _TensileOwnerCoordinate(
                key=node.owner_id,
                label=node.sample_id_raw,
                owner_ids=(node.owner_id,),
                role=node.role,
                data_nature=node.data_nature,
                kind="resolved",
            )
    survivor_owner = _tensile_owner_coordinate(survivor, graph)
    if generic_owner is None or survivor_owner is None:
        return None
    if survivor_owner.kind != "resolved":
        return None
    if (
        generic_owner.role != survivor_owner.role
        or generic_owner.data_nature != survivor_owner.data_nature
    ):
        return None
    generic_lineages = _fact_material_lineages(generic, generic_owner, graph)
    survivor_lineages = _fact_material_lineages(survivor, survivor_owner, graph)
    common = set(generic_lineages).intersection(survivor_lineages)
    if (
        len(generic_lineages) != 1
        or len(survivor_lineages) != 1
        or len(common) != 1
    ):
        return None
    if _identity_text(generic.sample_id_raw) == _identity_text(
        survivor.sample_id_raw
    ):
        return None
    return next(iter(common)), generic_owner, survivor_owner


def _append_fact_evidence(
    survivor: PropertyFact,
    loser: PropertyFact,
) -> PropertyFact:
    evidence = list(_fact_evidence(survivor))
    seen = {normalize_evidence_text(row) for row in evidence}
    for row in _fact_evidence(loser):
        normalized = normalize_evidence_text(row)
        if normalized and normalized not in seen:
            evidence.append(row)
            seen.add(normalized)
    data = deepcopy(survivor.data)
    if "source_evidence" in data:
        data["source_evidence"] = list(evidence)
    return survivor.model_copy(
        deep=True,
        update={
            "data": data,
            "source_evidence": list(evidence),
            "confidence": max(survivor.confidence, loser.confidence),
        },
    )


def _tensile_precision_fact_key(fact: PropertyFact) -> tuple[Any, ...]:
    return (
        _identity_text(fact.sample_id_raw),
        _core_tensile_family(fact.data.get("property_name_raw")),
        core_tensile_subtype(fact.data.get("property_name_raw")),
        _generic_unit_key(fact.data.get("unit_raw")),
        _scientific_fold(fact.data.get("value_raw")),
        _scientific_fold(fact.data.get("test_condition_raw")),
        tuple(normalize_evidence_text(row) for row in _fact_evidence(fact)),
    )


def _quarantine_generic_tensile_summary_shadows(
    anchors: Sequence[InventoryAnchor],
    facts: Sequence[AxisFact],
) -> tuple[list[AxisFact], list[PromotionIssue]]:
    """Fold one paired generic headline into one richer specimen result."""

    graph = build_owner_graph(anchors)
    if not graph.nodes:
        return list(facts), []
    properties = [
        fact
        for fact in facts
        if isinstance(fact, PropertyFact)
        and is_core_tensile_property_name(fact.data.get("property_name_raw"))
    ]
    shapes = {
        id(fact): shape
        for fact in properties
        if (shape := _tensile_scalar_shape(fact)) is not None
    }
    proposals: list[
        tuple[
            PropertyFact,
            PropertyFact,
            _TensileScalarShape,
            _TensileScalarShape,
            _GenericTensileSummaryBinding,
            _TensileOwnerCoordinate,
            _TensileOwnerCoordinate,
        ]
    ] = []
    for generic in sorted(properties, key=_tensile_precision_fact_key):
        generic_shape = shapes.get(id(generic))
        if generic_shape is None:
            continue
        summary = _generic_summary_binding(generic, generic_shape, graph)
        if summary is None:
            continue
        proposition, collective_scope, result_cue = summary
        candidates: list[
            tuple[
                PropertyFact,
                _TensileScalarShape,
                str,
                _TensileOwnerCoordinate,
                _TensileOwnerCoordinate,
            ]
        ] = []
        for survivor in properties:
            survivor_shape = shapes.get(id(survivor))
            if (
                survivor is generic
                or survivor_shape is None
                or not _concrete_tensile_survivor(survivor, survivor_shape)
                or _literal_mention(proposition, survivor.sample_id_raw)
            ):
                continue
            coordinate = _same_tensile_summary_coordinate(
                generic,
                generic_shape,
                survivor,
                survivor_shape,
                graph,
                proposition,
            )
            if coordinate is None:
                continue
            lineage, generic_owner, survivor_owner = coordinate
            richer = bool(
                survivor_shape.uncertainty is not None
                or survivor_shape.central_decimal_places
                > generic_shape.central_decimal_places
                or _scientific_fold(survivor.data.get("data_source"))
                == "table"
            )
            if richer:
                candidates.append(
                    (
                        survivor,
                        survivor_shape,
                        lineage,
                        generic_owner,
                        survivor_owner,
                    )
                )
        if len(candidates) != 1:
            continue
        survivor, survivor_shape, lineage, generic_owner, survivor_owner = (
            candidates[0]
        )
        proposals.append(
            (
                generic,
                survivor,
                generic_shape,
                survivor_shape,
                _GenericTensileSummaryBinding(
                    proposition=proposition,
                    collective_scope=collective_scope,
                    result_cue=result_cue,
                    material_lineage=lineage,
                ),
                generic_owner,
                survivor_owner,
            )
        )

    survivor_counts = Counter(id(row[1]) for row in proposals)
    removed: set[int] = set()
    replacements: dict[int, PropertyFact] = {}
    issues: list[PromotionIssue] = []
    for (
        generic,
        survivor,
        generic_shape,
        survivor_shape,
        binding,
        generic_owner,
        survivor_owner,
    ) in proposals:
        if survivor_counts[id(survivor)] != 1:
            continue
        survivor_before = survivor
        survivor_after = _append_fact_evidence(survivor_before, generic)
        removed.add(id(generic))
        replacements[id(survivor)] = survivor_after
        issues.append(
            _promotion_issue(
                generic,
                code="core_tensile_generic_summary_shadow_quarantined",
                message=(
                    "A generic paired tensile headline repeated one unique, "
                    "richer specimen/table result and was merged into that "
                    "source-grounded survivor."
                ),
                expected={
                    "independent_measurement": False,
                    "unique_concrete_survivor": True,
                    "audit_preserved": True,
                },
                actual={
                    "removed": generic.model_dump(),
                    "survivor_before": survivor_before.model_dump(),
                    "survivor_after": survivor_after.model_dump(),
                    "generic_summary": True,
                    "summary_proposition": binding.proposition,
                    "summary_collective_scope": binding.collective_scope,
                    "summary_result_cue": binding.result_cue,
                    "material_lineage": binding.material_lineage,
                    "tensile_family": _core_tensile_family(
                        generic.data.get("property_name_raw")
                    ),
                    "tensile_subtype": core_tensile_subtype(
                        generic.data.get("property_name_raw")
                    ),
                    "generic_value": generic_shape.central,
                    "survivor_value": survivor_shape.central,
                    "canonical_value": generic_shape.canonical_central,
                    "generic_unit": generic_shape.unit_key,
                    "survivor_unit": survivor_shape.unit_key,
                    "survivor_uncertainty": survivor_shape.uncertainty,
                    "condition": _scientific_fold(
                        generic.data.get("test_condition_raw")
                    ),
                    "generic_owner": generic_owner.label,
                    "generic_owner_ids": list(generic_owner.owner_ids),
                    "survivor_owner": survivor_owner.label,
                    "survivor_owner_ids": list(survivor_owner.owner_ids),
                    "owner_role": generic_owner.role,
                    "owner_data_nature": generic_owner.data_nature,
                    "unique_survivor": True,
                    "candidate_key": list(_tensile_precision_fact_key(generic)),
                    "survivor_key": list(_tensile_precision_fact_key(survivor)),
                    "owner_invented": False,
                },
                evidence=_fact_evidence(generic),
            )
        )
    issues.sort(
        key=lambda row: (
            _identity_text(row.sample_id_raw),
            json.dumps(row.actual, ensure_ascii=False, sort_keys=True),
        )
    )
    return [
        replacements.get(id(fact), fact)
        for fact in facts
        if id(fact) not in removed
    ], issues


def _group_extremum_binding(
    fact: PropertyFact,
    shape: _TensileScalarShape,
    graph: OwnerGraph,
) -> _TensileGroupExtremumBinding | None:
    if shape.uncertainty is not None:
        return None
    if _scientific_fold(fact.data.get("data_source")) == "table" or (
        _has_table_evidence(_fact_evidence(fact))
    ):
        return None
    proposition = _bounded_scalar_proposition(fact, shape.central)
    if proposition is None:
        return None
    folded = _scientific_fold(proposition)
    cue = _TENSILE_EXTREMUM_CUE.search(folded)
    scope = _TENSILE_EXTREMUM_SCOPE.search(folded)
    if cue is None or scope is None:
        return None
    family = _core_tensile_family(fact.data.get("property_name_raw"))
    constraints = []
    for match in _TENSILE_EXTREMUM_CONSTRAINT.finditer(folded):
        constraint = match.group("constraint").strip()
        if not re.search(r"[-+]?\d+(?:\.\d+)?", constraint):
            continue
        companions = [
            candidate
            for candidate in _tensile_families_in_text(constraint)
            if candidate != family
        ]
        if len(companions) == 1:
            constraints.append((companions[0], constraint))
    unique_constraints = list(dict.fromkeys(constraints))
    if len(unique_constraints) != 1:
        return None
    resolution = resolve_record_owner(build_promotion_records([fact])[0], graph)
    unresolved = not resolution.owner_ids
    if not unresolved and not _collective_owner_label(fact.sample_id_raw):
        return None
    named_nodes = [
        node
        for node in _safe_source_owner_nodes(proposition, graph)
        if not _collective_owner_label(node.sample_id_raw)
    ]
    if named_nodes:
        return None
    owner_kind = (
        "resolved_collective"
        if len(resolution.owner_ids) == 1
        else "unresolved_collective"
    )
    companion_family, companion_constraint = unique_constraints[0]
    return _TensileGroupExtremumBinding(
        proposition=proposition,
        extremum_cue=cue.group("cue"),
        collective_scope=scope.group("scope"),
        companion_family=companion_family,
        companion_constraint=companion_constraint,
        named_owner_ids=tuple(sorted(node.owner_id for node in named_nodes)),
        owner_ids=tuple(sorted(resolution.owner_ids)),
        owner_candidate_ids=tuple(sorted(resolution.candidate_owner_ids)),
        owner_coordinate_kind=owner_kind,
    )


def _quarantine_ownerless_tensile_group_extrema(
    anchors: Sequence[InventoryAnchor],
    facts: Sequence[AxisFact],
) -> tuple[list[AxisFact], list[PromotionIssue]]:
    """Isolate scalar Pareto/group extrema that have no specimen owner."""

    graph = build_owner_graph(anchors)
    if not graph.nodes:
        return list(facts), []
    removed: set[int] = set()
    issues: list[PromotionIssue] = []
    properties = sorted(
        (
            fact
            for fact in facts
            if isinstance(fact, PropertyFact)
            and is_core_tensile_property_name(
                fact.data.get("property_name_raw")
            )
        ),
        key=_tensile_precision_fact_key,
    )
    for fact in properties:
        shape = _tensile_scalar_shape(fact)
        if shape is None:
            continue
        binding = _group_extremum_binding(fact, shape, graph)
        if binding is None:
            continue
        removed.add(id(fact))
        issues.append(
            _promotion_issue(
                fact,
                code="promotion_tensile_group_extremum_quarantined",
                message=(
                    "A numeric tensile Pareto/group extremum had no unique "
                    "specimen coordinate and was isolated from specimen-level "
                    "Properties while preserving the complete assertion."
                ),
                expected={
                    "unique_specimen_owner": True,
                    "specimen_level_scalar": True,
                    "audit_preserved": True,
                },
                actual={
                    "removed": fact.model_dump(),
                    "reason": "ownerless_group_pareto_extremum",
                    "bounded_source_proposition": binding.proposition,
                    "extremum_cue": binding.extremum_cue,
                    "collective_scope": binding.collective_scope,
                    "companion_tensile_family": binding.companion_family,
                    "companion_property_constraint": (
                        binding.companion_constraint
                    ),
                    "tensile_family": _core_tensile_family(
                        fact.data.get("property_name_raw")
                    ),
                    "tensile_subtype": core_tensile_subtype(
                        fact.data.get("property_name_raw")
                    ),
                    "value": shape.central,
                    "unit": shape.unit_key,
                    "canonical_value": shape.canonical_central,
                    "owner_ids": list(binding.owner_ids),
                    "owner_candidate_ids": list(binding.owner_candidate_ids),
                    "owner_coordinate_kind": binding.owner_coordinate_kind,
                    "named_owner_ids": list(binding.named_owner_ids),
                    "candidate_key": list(_tensile_precision_fact_key(fact)),
                    "owner_invented": False,
                },
                evidence=_fact_evidence(fact),
            )
        )
    issues.sort(
        key=lambda row: (
            _identity_text(row.sample_id_raw),
            json.dumps(row.actual, ensure_ascii=False, sort_keys=True),
        )
    )
    return [fact for fact in facts if id(fact) not in removed], issues


def _parse_tensile_threshold(value: Any) -> _TensileThreshold | None:
    match = _TENSILE_THRESHOLD_LITERAL.fullmatch(str(value or ""))
    if match is None:
        return None
    operator = {"≥": ">=", "≤": "<="}.get(
        match.group("operator"), match.group("operator")
    )
    try:
        bound = float(match.group("bound"))
    except ValueError:
        return None
    if not math.isfinite(bound):
        return None
    return _TensileThreshold(
        operator=operator,  # type: ignore[arg-type]
        bound=bound,
    )


def _parse_exact_tensile_scalar(value: Any) -> float | None:
    text = str(value or "").strip()
    if (
        not text
        or _TENSILE_APPROXIMATE_SCALAR.search(text)
        or re.search(r"(?:>=|<=|[<>≥≤±]|\+/-|\\pm)", text)
        or re.search(r"(?<=\d)\s*[-–—~]\s*(?=\d)", text)
    ):
        return None
    numbers = _RAW_NUMBER.findall(text)
    if len(numbers) != 1:
        return None
    try:
        scalar = float(numbers[0])
    except ValueError:
        return None
    return scalar if math.isfinite(scalar) else None


def _threshold_relation_satisfied(
    threshold: _TensileThreshold,
    scalar: float,
) -> bool:
    if threshold.operator == ">":
        return scalar > threshold.bound
    if threshold.operator == ">=":
        return scalar >= threshold.bound
    if threshold.operator == "<":
        return scalar < threshold.bound
    return scalar <= threshold.bound


def _numeric_spans_for_value(value: float, text: Any) -> tuple[tuple[int, int], ...]:
    spans: list[tuple[int, int]] = []
    for match in _RAW_NUMBER.finditer(str(text or "")):
        try:
            candidate = float(match.group(0))
        except ValueError:
            continue
        if math.isclose(candidate, value, rel_tol=1e-12, abs_tol=1e-12):
            spans.append((match.start(), match.end()))
    return tuple(spans)


def _nested_tensile_owner_value_phrase(
    survivor: PropertyFact,
    owner_label: str,
    scalar: float,
    unit_key: str,
    proposition: str,
) -> str | None:
    normalized_proposition = _identity_text(proposition)
    candidates: list[str] = []
    for evidence in _fact_evidence(survivor):
        phrase = str(evidence or "").strip().rstrip(".;")
        normalized_phrase = _identity_text(phrase)
        if not phrase or normalized_phrase not in normalized_proposition:
            continue
        if len(_numeric_spans_for_value(scalar, phrase)) != 1:
            continue
        source_units = _source_units_next_to_value_generic(scalar, [phrase])
        if unit_key not in source_units:
            continue
        if not any(
            _distinctive_owner_label(alias)
            and _literal_mention(phrase, alias)
            for alias in _owner_evidence_aliases(owner_label)
        ):
            continue
        candidates.append(phrase)
    unique = list(dict.fromkeys(candidates))
    return unique[0] if len(unique) == 1 else None


def _tensile_threshold_source_binding(
    threshold_fact: PropertyFact,
    survivor: PropertyFact,
    owner_label: str,
    threshold: _TensileThreshold,
    scalar: float,
    unit_key: str,
) -> _TensileThresholdBinding | None:
    bindings: list[_TensileThresholdBinding] = []
    for evidence in _fact_evidence(threshold_fact):
        for sentence in _TENSILE_SENTENCE_BOUNDARY.split(str(evidence or "")):
            proposition = sentence.strip().rstrip(".;")
            if not proposition:
                continue
            bound_spans = _numeric_spans_for_value(threshold.bound, proposition)
            scalar_spans = _numeric_spans_for_value(scalar, proposition)
            if math.isclose(
                threshold.bound, scalar, rel_tol=1e-12, abs_tol=1e-12
            ):
                if len(bound_spans) != 2:
                    continue
            elif len(bound_spans) != 1 or len(scalar_spans) != 1:
                continue
            bound_units = _source_units_next_to_value_generic(
                threshold.bound, [proposition]
            )
            scalar_units = _source_units_next_to_value_generic(
                scalar, [proposition]
            )
            if unit_key not in bound_units or unit_key not in scalar_units:
                continue
            nested_phrase = _nested_tensile_owner_value_phrase(
                survivor,
                owner_label,
                scalar,
                unit_key,
                proposition,
            )
            if nested_phrase is None:
                continue
            bindings.append(
                _TensileThresholdBinding(
                    bounded_source_proposition=proposition,
                    nested_owner_value_phrase=nested_phrase,
                )
            )
    unique = list(
        {
            (
                row.bounded_source_proposition,
                row.nested_owner_value_phrase,
            ): row
            for row in bindings
        }.values()
    )
    return unique[0] if len(unique) == 1 else None


def _tensile_owner_coordinate(
    fact: PropertyFact,
    graph: OwnerGraph,
) -> _TensileOwnerCoordinate | None:
    record = build_promotion_records([fact])[0]
    resolution = resolve_record_owner(record, graph)
    if len(resolution.owner_ids) == 1:
        node = graph.node(resolution.owner_ids[0])
        return _TensileOwnerCoordinate(
            key=node.owner_id,
            label=node.sample_id_raw,
            owner_ids=(node.owner_id,),
            role=node.role,
            data_nature=node.data_nature,
            kind="resolved",
        )
    if resolution.owner_ids or not resolution.candidate_owner_ids:
        return None
    nodes = [graph.node(owner_id) for owner_id in resolution.candidate_owner_ids]
    sample = _identity_text(fact.sample_id_raw)
    if not sample or any(
        _identity_text(node.sample_id_raw) != sample for node in nodes
    ):
        return None
    roles = {node.role for node in nodes}
    natures = {node.data_nature for node in nodes}
    if len(roles) != 1 or len(natures) != 1:
        return None
    owner_ids = tuple(sorted(node.owner_id for node in nodes))
    encoded = "\n".join(owner_ids).encode("utf-8")
    return _TensileOwnerCoordinate(
        key="owner_envelope_" + hashlib.sha256(encoded).hexdigest()[:24],
        label=str(fact.sample_id_raw).strip(),
        owner_ids=owner_ids,
        role=next(iter(roles)),
        data_nature=next(iter(natures)),
        kind="identical_candidate_envelope",
    )


def _quarantine_dominated_tensile_thresholds(
    anchors: Sequence[InventoryAnchor],
    facts: Sequence[AxisFact],
) -> tuple[list[AxisFact], list[PromotionIssue]]:
    """Isolate a same-owner threshold dominated by one nested exact value."""

    graph = build_owner_graph(anchors)
    if not graph.nodes:
        return list(facts), []
    grouped: dict[tuple[str, str, str, str, str], list[PropertyFact]] = {}
    owner_by_fact: dict[int, _TensileOwnerCoordinate] = {}
    for fact in facts:
        if not (
            isinstance(fact, PropertyFact)
            and is_core_tensile_property_name(fact.data.get("property_name_raw"))
        ):
            continue
        family = _core_tensile_family(fact.data.get("property_name_raw"))
        subtype = core_tensile_subtype(fact.data.get("property_name_raw"))
        unit = _generic_unit_key(fact.data.get("unit_raw"))
        if not family or not unit:
            continue
        owner = _tensile_owner_coordinate(fact, graph)
        if owner is None:
            continue
        owner_by_fact[id(fact)] = owner
        grouped.setdefault(
            (
                owner.key,
                family,
                subtype,
                unit,
                _scientific_fold(fact.data.get("test_condition_raw")),
            ),
            [],
        ).append(fact)

    removed: set[int] = set()
    issues: list[PromotionIssue] = []
    for group_key, rows in sorted(grouped.items()):
        owner_key, family, subtype, unit_key, condition = group_key
        owner = owner_by_fact[id(rows[0])]
        scalar_rows = [
            (row, scalar)
            for row in rows
            if (scalar := _parse_exact_tensile_scalar(row.data.get("value_raw")))
            is not None
        ]
        threshold_rows = [
            (row, threshold)
            for row in rows
            if (threshold := _parse_tensile_threshold(row.data.get("value_raw")))
            is not None
        ]
        for threshold_fact, threshold in sorted(
            threshold_rows,
            key=lambda row: semantic_fact_signature(row[0]),
        ):
            candidates: list[
                tuple[PropertyFact, float, _TensileThresholdBinding]
            ] = []
            for survivor, scalar in scalar_rows:
                if not _threshold_relation_satisfied(threshold, scalar):
                    continue
                binding = _tensile_threshold_source_binding(
                    threshold_fact,
                    survivor,
                    owner.label,
                    threshold,
                    scalar,
                    unit_key,
                )
                if binding is not None:
                    candidates.append((survivor, scalar, binding))
            if len(candidates) != 1:
                continue
            survivor, scalar, binding = candidates[0]
            removed.add(id(threshold_fact))
            issues.append(
                _promotion_issue(
                    threshold_fact,
                    code="promotion_tensile_dominated_threshold_quarantined",
                    message=(
                        "A core-tensile threshold was a less-specific projection "
                        "of one same-owner exact value nested in the same source "
                        "assertion; the exact result was retained."
                    ),
                    expected={
                        "independent_measurement": False,
                        "unique_exact_survivor": True,
                        "audit_preserved": True,
                    },
                    actual={
                        "removed": threshold_fact.model_dump(),
                        "survivor": survivor.model_dump(),
                        "owner": owner.label,
                        "owner_id": (
                            owner.owner_ids[0]
                            if owner.kind == "resolved"
                            else None
                        ),
                        "owner_candidate_ids": list(owner.owner_ids),
                        "owner_coordinate_kind": owner.kind,
                        "owner_role": owner.role,
                        "owner_data_nature": owner.data_nature,
                        "tensile_family": family,
                        "tensile_subtype": subtype,
                        "unit": unit_key,
                        "condition": condition,
                        "operator": threshold.operator,
                        "bound": threshold.bound,
                        "scalar": scalar,
                        "relation_satisfied": True,
                        "bounded_source_proposition": (
                            binding.bounded_source_proposition
                        ),
                        "nested_owner_value_phrase": (
                            binding.nested_owner_value_phrase
                        ),
                        "unique_survivor": True,
                        "owner_invented": False,
                    },
                    evidence=_fact_evidence(threshold_fact),
                )
            )
    return [fact for fact in facts if id(fact) not in removed], issues


def _quarantine_tensile_conflicts(
    facts: Sequence[AxisFact], source_text: str
) -> tuple[list[AxisFact], list[PromotionIssue]]:
    blocks = _source_blocks(source_text)
    grouped: dict[tuple[Any, ...], list[PropertyFact]] = {}
    for fact in facts:
        if not isinstance(
            fact, PropertyFact
        ) or not is_core_tensile_property_name(
            fact.data.get("property_name_raw")
        ):
            continue
        record = build_promotion_records([fact])[0]
        source_key, _, ambiguous = _record_source_binding(record, blocks)
        if ambiguous:
            continue
        grouped.setdefault(
            (
                _identity_text(fact.sample_id_raw),
                source_key,
                record.normalized_evidence,
                _core_tensile_family(fact.data.get("property_name_raw")),
                core_tensile_subtype(fact.data.get("property_name_raw")),
                _scientific_fold(fact.data.get("test_condition_raw")),
                _scientific_fold(fact.data.get("unit_raw")),
            ),
            [],
        ).append(fact)
    removed: set[int] = set()
    issues: list[PromotionIssue] = []
    for rows in grouped.values():
        values = {
            _scientific_compact(row.data.get("value_raw")) for row in rows
        }
        if len(rows) < 2 or len(values) < 2:
            continue
        conflict = [row.model_dump() for row in rows]
        for row in rows:
            removed.add(id(row))
            issues.append(
                _promotion_issue(
                    row,
                    code="promotion_tensile_value_conflict_quarantined",
                    message=(
                        "Incompatible core-tensile values shared one owner, "
                        "condition, unit, and source assertion without a unique "
                        "column binding."
                    ),
                    expected={
                        "conflicting_value_count": 1,
                        "unique_binding": True,
                    },
                    actual={
                        "removed": row.model_dump(),
                        "conflict_set": conflict,
                    },
                )
            )
    return [fact for fact in facts if id(fact) not in removed], issues


def _restore_input_order(
    facts: Sequence[AxisFact], original: Sequence[AxisFact]
) -> list[AxisFact]:
    """Keep materializer presentation stable without using order as truth."""

    original_evidence = [
        tuple(normalize_evidence_text(row) for row in fact.source_evidence)
        for fact in original
    ]

    def position(fact: AxisFact) -> tuple[int, str]:
        rows = tuple(
            normalize_evidence_text(row) for row in fact.source_evidence
        )
        candidates: list[int] = []
        for index, prior in enumerate(original):
            if (
                fact.axis != prior.axis
                or fact.fact_type != prior.fact_type
                or _identity_text(fact.sample_id_raw)
                != _identity_text(prior.sample_id_raw)
            ):
                continue
            if id(fact) == id(prior) or any(
                left
                and right
                and (left == right or left in right or right in left)
                for left in rows
                for right in original_evidence[index]
            ):
                candidates.append(index)
        return (
            min(candidates, default=len(original)),
            semantic_fact_signature(fact),
        )

    return sorted(facts, key=position)


def _publish_v204_tensile_assertion_coordinates(
    anchors: Sequence[InventoryAnchor],
    facts: Sequence[AxisFact],
    source_text: str,
) -> tuple[list[AxisFact], list[PromotionIssue]]:
    """Attach exact assertion keys to final, already accepted tensile facts.

    The earlier owner gate invokes the v204 parser only when a short quote
    needs owner recovery.  A fact whose quote already names the correct owner
    still needs the same immutable key so the materializer can link it to one
    unique protocol event.  This pass runs after every quarantine/dedup gate,
    changes neither owner nor scientific value, and fails closed unless the
    source coordinate resolves to that fact's existing owner.
    """

    if (
        not tensile_assertion_coordinates_v204_enabled()
        or not tensile_result_protocol_binding_v204_enabled()
        or not source_text
    ):
        return list(facts), []
    graph = build_owner_graph(anchors)
    if not graph.nodes:
        return list(facts), []
    protocol_ledger = TensileProtocolLedger(source_text)

    accepted: list[AxisFact] = []
    issues: list[PromotionIssue] = []
    for fact in facts:
        if not isinstance(fact, PropertyFact) or not is_core_tensile_property_name(
            fact.data.get("property_name_raw")
        ):
            accepted.append(fact)
            continue
        if str(fact.data.get("property_id_candidate") or "").startswith(
            "tensile-assertion:"
        ):
            accepted.append(fact)
            continue
        decision = _v204_tensile_assertion_decision(fact, graph, source_text)
        coordinate = decision.coordinate
        if decision.status != "matched" or coordinate is None:
            accepted.append(fact)
            continue
        target = graph.node(coordinate.owner_key)
        record = build_promotion_records([fact])[0]
        if not any(
            _v204_same_existing_owner(node, target)
            for node in _candidate_nodes(record, graph)
        ):
            accepted.append(fact)
            continue

        owner_labels = tuple(
            dict.fromkeys((target.sample_id_raw, *target.aliases))
        )
        other_owner_labels = tuple(
            dict.fromkeys(
                alias
                for node in graph.nodes
                if not _v204_same_existing_owner(node, target)
                for alias in (node.sample_id_raw, *node.aliases)
                if alias
            )
        )
        baseline_decision = protocol_ledger.bind(
            fact.data,
            owner_role=target.role,
            owner_labels=owner_labels,
            other_owner_labels=other_owner_labels,
        )
        probe_data = deepcopy(fact.data)
        probe_data["property_id_candidate"] = coordinate.source_coordinate_key
        probe_decision = protocol_ledger.bind(
            probe_data,
            owner_role=target.role,
            owner_labels=owner_labels,
            other_owner_labels=other_owner_labels,
        )
        # Publish internal metadata only when the assertion coordinate is the
        # fact that changes a unique protocol decision.  This keeps v204 from
        # rewriting already-safe single-owner facts merely for bookkeeping.
        if probe_decision.status != "bound" or baseline_decision.status == "bound":
            accepted.append(fact)
            continue

        published, condition_bound = _v204_bind_assertion_condition(
            fact, decision
        )
        accepted.append(published)
        if published is fact:
            continue
        issues.append(
            _promotion_issue(
                fact,
                code="tensile_assertion_coordinate_recovered",
                severity="info",
                message=(
                    "A complete source assertion published one immutable "
                    "owner/property/value/unit coordinate for a retained "
                    "core-tensile candidate."
                ),
                expected={
                    "existing_owner_preserved": target.sample_id_raw,
                    "candidate_value_changed": False,
                    "candidate_unit_changed": False,
                    "broadcast": False,
                },
                actual={
                    "before": fact.model_dump(),
                    "after": published.model_dump(),
                    "decision": decision.to_dict(),
                    "selected_owner": target.sample_id_raw,
                    "selected_owner_id": target.owner_id,
                },
                evidence=[coordinate.source_text],
            )
        )
        if condition_bound:
            issues.append(
                _promotion_issue(
                    fact,
                    code="tensile_result_protocol_bound",
                    severity="info",
                    message=(
                        "A literal tensile-result temperature from the same "
                        "source assertion filled an empty condition."
                    ),
                    expected={
                        "same_assertion": True,
                        "overwrite_existing_literal": False,
                        "preparation_temperature": False,
                    },
                    actual={
                        "before": fact.model_dump(),
                        "after": published.model_dump(),
                        "decision": decision.to_dict(),
                        "contributed_dimensions": ["temperature"],
                    },
                    evidence=[coordinate.source_text],
                )
            )
    return accepted, issues


def promote_axis_facts(
    anchors: Iterable[InventoryAnchor],
    facts: Iterable[AxisFact],
    *,
    source_text: str,
    task_ids: Sequence[str | None] | None = None,
) -> PromotionResult:
    """Promote high-recall facts using source-only, paper-level precision gates."""

    anchor_rows = list(anchors)
    fact_rows = list(facts)
    original_fact_rows = list(fact_rows)
    if task_ids is not None and len(task_ids) != len(fact_rows):
        raise ValueError("task_ids must contain exactly one entry per fact")
    issues: list[PromotionIssue] = []

    fact_rows, stage_issues = _quality_gate(fact_rows)
    issues.extend(stage_issues)
    fact_rows, stage_issues = _quarantine_source_numeric_unit_conflicts(
        fact_rows
    )
    issues.extend(stage_issues)
    fact_rows, stage_issues = _gate_processing_observation_projections(
        fact_rows, source_text
    )
    issues.extend(stage_issues)
    fact_rows, stage_issues = _quarantine_processing_result_or_hypothetical_stages(
        fact_rows, source_text
    )
    issues.extend(stage_issues)
    fact_rows, stage_issues = _quarantine_zero_duration_heat_treatment_stages(
        fact_rows
    )
    issues.extend(stage_issues)
    fact_rows, stage_issues = _quarantine_processing_specimen_preparation_stages(
        fact_rows
    )
    issues.extend(stage_issues)
    fact_rows, stage_issues = _quarantine_processing_test_protocol_stages(
        fact_rows
    )
    issues.extend(stage_issues)
    fact_rows, stage_issues = _quarantine_unasserted_process_stages(
        fact_rows
    )
    issues.extend(stage_issues)
    fact_rows, stage_issues = _quarantine_processing_metadata_parameters(
        fact_rows
    )
    issues.extend(stage_issues)

    structured: list[AxisFact] = []
    for fact in fact_rows:
        if isinstance(fact, StructureFact):
            cleaned, fact_issues = _gate_structure_fact(fact)
            issues.extend(fact_issues)
            if cleaned is not None:
                structured.append(cleaned)
        else:
            structured.append(fact)
    fact_rows = structured
    fact_rows, stage_issues = _quarantine_structure_comparative_projections(
        fact_rows
    )
    issues.extend(stage_issues)
    fact_rows, stage_issues = _quarantine_structure_numeric_comparative_projections(
        fact_rows
    )
    issues.extend(stage_issues)
    fact_rows, stage_issues = _quarantine_structure_inferential_projections(
        fact_rows
    )
    issues.extend(stage_issues)
    fact_rows, stage_issues = _quarantine_structure_unasserted_entities(
        fact_rows
    )
    issues.extend(stage_issues)
    fact_rows, stage_issues = _quarantine_structure_generalization_projections(
        fact_rows
    )
    issues.extend(stage_issues)
    fact_rows, stage_issues = _quarantine_structure_procedural_presentations(
        fact_rows
    )
    issues.extend(stage_issues)
    fact_rows, stage_issues = _gate_characterizations(
        fact_rows, source_text
    )
    issues.extend(stage_issues)
    # Normalize presentation-only locators and repeated fragments before the
    # all-or-nothing source-grounding check.  Otherwise a condition such as
    # ``room temperature | Table 3 | room temperature`` is either retained as
    # provenance pollution or cleared together with its valid coordinate.
    fact_rows, stage_issues = _separate_property_provenance_conditions_v205(
        fact_rows
    )
    issues.extend(stage_issues)
    fact_rows, stage_issues = _strip_unbound_conditions(fact_rows, source_text)
    issues.extend(stage_issues)
    fact_rows, stage_issues = _bind_explicit_treatment_conditions(fact_rows)
    issues.extend(stage_issues)
    fact_rows, stage_issues = _bind_property_condition_labels(fact_rows)
    issues.extend(stage_issues)
    fact_rows, stage_issues = _clean_method_conditions(fact_rows)
    issues.extend(stage_issues)
    issues.extend(_v205_protocol_separation_audit(stage_issues))
    # Condition labels and treatment binding may add a segment after the first
    # pass.  Re-run the idempotent normalizer so the public condition has one
    # presentation-neutral representation.
    fact_rows, stage_issues = _separate_property_provenance_conditions_v205(
        fact_rows
    )
    issues.extend(stage_issues)
    fact_rows, stage_issues = _quarantine_tensile_source_unit_conflicts(
        fact_rows
    )
    issues.extend(stage_issues)
    fact_rows, stage_issues = _gate_tensile_source_bindings(
        anchor_rows, fact_rows, source_text
    )
    issues.extend(stage_issues)
    fact_rows, stage_issues = _gate_noncomposition_table_bindings(
        anchor_rows, fact_rows, source_text
    )
    issues.extend(stage_issues)
    fact_rows, stage_issues = _gate_processing_table_bindings(
        anchor_rows, fact_rows, source_text
    )
    issues.extend(stage_issues)
    fact_rows, stage_issues = _route_cited_table_reference_owners(
        anchor_rows, fact_rows
    )
    issues.extend(stage_issues)
    fact_rows, stage_issues = _quarantine_ambiguous_structure_table_projections(
        fact_rows, source_text
    )
    issues.extend(stage_issues)
    fact_rows, stage_issues = _gate_composition_table_bindings(
        anchor_rows, fact_rows, source_text
    )
    issues.extend(stage_issues)
    fact_rows, stage_issues = _route_implicit_processed_state_owners(
        anchor_rows, fact_rows
    )
    issues.extend(stage_issues)
    fact_rows, stage_issues = _quarantine_processing_owner_ambiguities(
        anchor_rows, fact_rows, source_text
    )
    issues.extend(stage_issues)
    fact_rows, stage_issues = _route_unique_material_owner_v205(
        anchor_rows, fact_rows, source_text
    )
    issues.extend(stage_issues)
    fact_rows, stage_issues = _quarantine_core_tensile_owner_ambiguities(
        anchor_rows, fact_rows, source_text
    )
    issues.extend(stage_issues)
    fact_rows, stage_issues = _quarantine_region_scoped_property_owners(
        anchor_rows, fact_rows
    )
    issues.extend(stage_issues)
    fact_rows, stage_issues = _quarantine_external_composition_subject_projections(
        anchor_rows, fact_rows, source_text
    )
    issues.extend(stage_issues)
    fact_rows, stage_issues = _quarantine_external_source_projections(
        anchor_rows, fact_rows
    )
    issues.extend(stage_issues)
    fact_rows, stage_issues = _quarantine_unbound_core_tensile_external_projections(
        anchor_rows, fact_rows
    )
    issues.extend(stage_issues)
    fact_rows, stage_issues = _quarantine_property_projections(fact_rows)
    issues.extend(stage_issues)
    fact_rows, stage_issues = _quarantine_comparative_owner_projections(
        fact_rows
    )
    issues.extend(stage_issues)
    fact_rows, stage_issues = _route_tensile_state_conflicts(
        anchor_rows, fact_rows
    )
    issues.extend(stage_issues)
    fact_rows, stage_issues = _route_facts_by_condition_owner(
        anchor_rows, fact_rows
    )
    issues.extend(stage_issues)
    fact_rows, stage_issues = _route_structure_source_state_owners(
        anchor_rows, fact_rows
    )
    issues.extend(stage_issues)
    fact_rows, stage_issues = _quarantine_structure_region_coordinate_projections(
        fact_rows
    )
    issues.extend(stage_issues)
    fact_rows, stage_issues = _quarantine_unresolved_tensile_state_bundles(
        anchor_rows, fact_rows
    )
    issues.extend(stage_issues)
    fact_rows, stage_issues = _quarantine_respectively_state_owner_projections(
        anchor_rows, fact_rows
    )
    issues.extend(stage_issues)
    fact_rows, stage_issues = _owner_gate(
        anchor_rows, fact_rows, source_text
    )
    issues.extend(stage_issues)
    fact_rows, stage_issues = _quarantine_feedstock_composition_mismatches(
        anchor_rows, fact_rows
    )
    issues.extend(stage_issues)
    fact_rows, stage_issues = _quarantine_tensile_feedstock_result_mismatches(
        anchor_rows, fact_rows
    )
    issues.extend(stage_issues)
    # Run the precision-only composition gate after owner/feedstock routing so
    # those specialized checks can retain their more informative audit code.
    fact_rows, stage_issues = _composition_precision_gate(fact_rows)
    issues.extend(stage_issues)

    deduplicated = deduplicate_source_assertions(
        fact_rows,
        source_text=source_text,
    )
    fact_rows = list(deduplicated.accepted)
    issues.extend(deduplicated.issues)
    if same_table_property_merge_v201_enabled():
        fact_rows, stage_issues = _merge_same_numbered_table_property_duplicates(
            anchor_rows, fact_rows, source_text
        )
        issues.extend(stage_issues)
    fact_rows, stage_issues = _absorb_property_statistical_shadows(
        fact_rows, source_text
    )
    issues.extend(stage_issues)
    fact_rows, stage_issues = _quarantine_wrong_axis_property_duplicates(
        fact_rows, source_text
    )
    issues.extend(stage_issues)
    fact_rows, stage_issues = _merge_structure_unit_shadows(
        fact_rows, source_text
    )
    issues.extend(stage_issues)
    fact_rows, stage_issues = _merge_strict_structure_subsets(
        fact_rows, source_text
    )
    issues.extend(stage_issues)
    fact_rows, stage_issues = _quarantine_cross_owner_projections(
        fact_rows, source_text
    )
    issues.extend(stage_issues)
    fact_rows, stage_issues = _quarantine_structure_collective_range_fanout(
        fact_rows, source_text
    )
    issues.extend(stage_issues)
    fact_rows, stage_issues = _quarantine_structure_exact_evidence_projections(
        fact_rows
    )
    issues.extend(stage_issues)
    fact_rows, stage_issues = _quarantine_composition_exact_evidence_projections(
        fact_rows
    )
    issues.extend(stage_issues)
    fact_rows, stage_issues = _quarantine_comparative_owner_duplicates(
        fact_rows
    )
    issues.extend(stage_issues)
    fact_rows, stage_issues = _quarantine_evidence_explicit_owner_mismatches(
        anchor_rows, fact_rows, source_text
    )
    issues.extend(stage_issues)
    fact_rows, stage_issues = _quarantine_prose_owner_value_mismatches(
        anchor_rows, fact_rows, source_text
    )
    issues.extend(stage_issues)
    fact_rows, stage_issues = _quarantine_dominated_tensile_thresholds(
        anchor_rows, fact_rows
    )
    issues.extend(stage_issues)
    fact_rows, stage_issues = _quarantine_generic_tensile_summary_shadows(
        anchor_rows, fact_rows
    )
    issues.extend(stage_issues)
    fact_rows, stage_issues = _quarantine_ownerless_tensile_group_extrema(
        anchor_rows, fact_rows
    )
    issues.extend(stage_issues)
    fact_rows, stage_issues = _quarantine_tensile_conflicts(
        fact_rows, source_text
    )
    issues.extend(stage_issues)
    fact_rows, stage_issues = _quarantine_ambiguous_respectively_groups(
        fact_rows
    )
    issues.extend(stage_issues)
    fact_rows, stage_issues = _quarantine_ambiguous_property_fanout(
        fact_rows
    )
    issues.extend(stage_issues)
    fact_rows, stage_issues = _quarantine_source_block_property_fanout(
        anchor_rows, fact_rows, source_text
    )
    issues.extend(stage_issues)
    fact_rows, stage_issues = _quarantine_source_block_structural_fanout(
        fact_rows, source_text
    )
    issues.extend(stage_issues)
    fact_rows, stage_issues = _quarantine_prose_multi_owner_atomicity(
        anchor_rows, fact_rows, source_text
    )
    issues.extend(stage_issues)
    fact_rows, stage_issues = _publish_v204_tensile_assertion_coordinates(
        anchor_rows, fact_rows, source_text
    )
    issues.extend(stage_issues)
    fact_rows = _restore_input_order(fact_rows, original_fact_rows)

    return PromotionResult(
        accepted=tuple(fact_rows),
        issues=tuple(issues),
    )


__all__ = [
    "PromotionAction",
    "AssertionGroup",
    "PromotionDecision",
    "PromotionIssue",
    "PromotionRecord",
    "PromotionResult",
    "OwnerGraph",
    "OwnerNode",
    "OwnerResolution",
    "build_owner_graph",
    "build_promotion_records",
    "deduplicate_source_assertions",
    "group_source_assertions",
    "promote_axis_facts",
    "resolve_record_owner",
    "structure_assertion_atomicity_v205_enabled",
    "characterization_event_atomicity_v205_enabled",
    "property_provenance_condition_separation_v205_enabled",
    "unique_material_owner_convergence_v205_enabled",
    "tensile_assertion_coordinates_v204_enabled",
    "tensile_coordinate_fanout_guard_v204_enabled",
    "tensile_result_protocol_binding_v204_enabled",
]
