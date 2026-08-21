"""Paper-level precision promotion for Alpha25 candidate facts.

The extraction model remains a high-recall candidate generator.  This module
provides deterministic, source-derived records and decisions used to decide
which candidates may enter the existing materializer.  It never consults GT
data and never invents scientific fields.
"""

from __future__ import annotations

import hashlib
import json
import re
from copy import deepcopy
from dataclasses import dataclass
from typing import Any, Iterable, Literal, Sequence

from knowmat.alpha25.claim_quality import (
    core_tensile_subtype,
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
            state_raw=str(first.state_raw or "").strip(),
            role=str(first.role),
            data_nature=str(first.data_nature),
            aliases=tuple(sorted(aliases, key=lambda row: (_identity_text(row), row))),
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
_PROCESS_REGION_LOCATOR = re.compile(
    r"(?ix)\b(?:"
    r"cast(?:ing)?|laser[\s-]*(?:glaz(?:ed|ing)|remelt(?:ed|ing))|"
    r"remelt(?:ed|ing)|melt[\s-]*pool|fusion|heat[\s-]*affected"
    r")[\s-]*(?:region|zone|area|track|surface)s?\b"
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
    r"(?:creep|tensile|fatigue|compression)\s+tests?|"
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
    r"\bsuppress(?:ed|ion)\b|\bdeplet(?:ed|ion)\b"
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
_STRUCTURE_CONTEXT_ONLY_FEATURES = {"area", "location", "region"}
_INLINE_CORE_TENSILE_UNIT = re.compile(
    r"(?ix)(?:%|\b(?:m|g|k)?pa\b|\bhv(?:[_₀-₉.]*)\b)"
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
_EXTERNAL_SOURCE_ASSERTION = re.compile(
    r"(?ix)(?:\bet\s+al\.?\b|\bprevious(?:ly)?\s+(?:reported|work|study)\b|"
    r"\b(?:literature|reference|cited|prior\s+study)\b|"
    r"\[\s*\d+(?:\s*[,;]\s*\d+)*\s*\])"
)
_CURRENT_SOURCE_ASSERTION = re.compile(
    r"(?ix)\b(?:in\s+this\s+(?:study|work|paper)|the\s+present\s+(?:study|work)|"
    r"we\s+(?:observed|found|report(?:ed)?|measured)|our\s+(?:results?|study|work)|"
    r"this\s+work)\b"
)
_CONDITION_DISCRIMINATOR_CUE = re.compile(
    r"(?ix)(?:"
    r"\b(?:delay|temperature|temperatures|orientation|oriented|direction|"
    r"state|condition|aged|ageing|aging|heat[\s-]*treat(?:ed|ment)?|"
    r"as[\s-]*built|as[\s-]*printed|build[\s-]*height|"
    r"layer|wall|region|location|position|plane|axis)\b|"
    r"(?:°\s*C|\bK\b|\b(?:s|sec|seconds?|min|minutes?|h|hours?)\b|%)"
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


def _payload_grounded(value: Any, evidence: Sequence[str]) -> bool:
    candidate = _scientific_compact(value)
    if not candidate or _scientific_fold(value) in _UNREPORTED:
        return False
    joined = "\n".join(evidence)
    source = _scientific_compact(joined)
    if candidate in source:
        return True
    numbers = _numeric_tokens(value)
    if numbers and not all(number in _numeric_tokens(joined) for number in numbers):
        return False
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
    suggested_action: str = "Review the preserved candidate against its cited evidence.",
) -> PromotionIssue:
    return PromotionIssue(
        code=code,
        sample_id_raw=fact.sample_id_raw,
        message=message,
        evidence=_fact_evidence(fact) if evidence is None else evidence,
        expected=expected,
        actual=actual,
        suggested_action=suggested_action,
    )


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
    r"assess(?:ed|ment)?|test(?:ed|ing)?|report(?:ed|ing)?"
    r")(?:\s+(?:using|by|via|with|from|according\s+to|through)\b.*)?\s*$"
)
_STRUCTURE_FEEDSTOCK_TABLE_CUE = re.compile(
    r"(?ix)\b(?:particle\s+size\s+distribution|"
    r"(?:average|avg\.?|mean)\s+particle\s+size|flow\s+rate|"
    r"solid\s+density|density\s+change)\b"
)
_STRUCTURE_FEATURE_PHASE_NAME = re.compile(
    r"(?ix)\b(?:precipitat(?:e|ed|ion)|grain|phase|microstructure|"
    r"morphology|structure)\b"
)


def _structure_feature_precision_risk(
    feature: dict[str, Any], evidence: Sequence[str]
) -> tuple[str, str] | None:
    """Return a deterministic reason for a non-result Structure projection."""

    if not _is_quantitative_structure_feature(feature) and not _is_negated_structure_feature(feature):
        value = str(feature.get("value_raw") or "").strip()
        if _STRUCTURE_METHOD_ONLY_VALUE.fullmatch(value):
            return (
                "promotion_structure_method_only_value_quarantined",
                "method_only_value",
            )

    name = str(feature.get("feature_name_raw") or "")
    joined = "\n".join(str(row or "") for row in evidence)
    if (
        "|" in joined
        and _STRUCTURE_FEEDSTOCK_TABLE_CUE.search(joined)
        and _STRUCTURE_FEATURE_PHASE_NAME.search(name)
        and not re.search(r"(?ix)\bparticle\s+size\b", name)
    ):
        return (
            "promotion_structure_table_axis_mismatch_quarantined",
            "feedstock_table_projected_as_structure",
        )
    return None


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
            precision_risk = _structure_feature_precision_risk(
                feature, feature_evidence
            )
            if precision_risk is not None:
                issue_code, reason = precision_risk
                issues.append(
                    _promotion_issue(
                        fact,
                        code=issue_code,
                        message=(
                            "A Structure feature was isolated because its value "
                            "describes a method or a feedstock-table field rather "
                            "than an atomic structural result."
                        ),
                        expected={
                            "structural_result": True,
                            "audit_preserved": True,
                        },
                        actual={
                            "removed": deepcopy(feature),
                            "entity": deepcopy(entity),
                            "reason": reason,
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
        precision_risk = _structure_feature_precision_risk(
            feature, feature_evidence
        )
        if precision_risk is not None:
            issue_code, reason = precision_risk
            issues.append(
                _promotion_issue(
                    fact,
                    code=issue_code,
                    message=(
                        "A Structure feature was isolated because its value "
                        "describes a method or a feedstock-table field rather "
                        "than an atomic structural result."
                    ),
                    expected={
                        "structural_result": True,
                        "audit_preserved": True,
                    },
                    actual={
                        "removed": deepcopy(feature),
                        "reason": reason,
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
    r"prefer(?:red|ential)|suggest(?:s|ing|ed)?|indic(?:ate|ates|ating)|"
    r"attribut(?:e|ed|es|ing)|caus(?:e|ed|es|ing)|due\s+to|leading\s+to|"
    r"result(?:ed|s)?\s+in|contribut(?:e|ed|es|ing)|risk|likely|"
    r"relationship|correlation|mechanism|behavio(?:u)?r)\b"
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
    r"which\s+(?:can|could|may|might)\b"
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
    r"detail(?:s|ed|ing)?|mainly|primarily|"
    r"had|has|have|"
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
# still inferential even though ``dissolution`` is a change noun.
_STRUCTURE_DIRECT_CHANGE_ASSERTION = re.compile(
    r"(?ix)\b(?:"
    r"appear(?:ed|s|ing)?|"
    r"emerg(?:ed|es|ing)?|"
    r"increas(?:e|ed|es|ing)|"
    r"decreas(?:e|ed|es|ing)|"
    r"coarsen(?:ed|ing)?|"
    r"refin(?:e|ed|es|ing|ement)|"
    r"evol(?:ve|ved|ves|ving|ution)|"
    r"transform(?:ed|s|ation|ing)?|"
    r"grow(?:s|th|ing|n)?|"
    r"nucleat(?:e|ed|es|ing|ion)|"
    r"precipitat(?:e|ed|es|ing|ion)|"
    r"segregat(?:e|ed|es|ing|ion)|"
    r"dissol(?:ve|ved|ves|ving|ution)|"
    r"remov(?:e|ed|es|ing|al)"
    r"|annihilat(?:e|ed|es|ing|ion)"
    r"|higher|lower|greater|smaller|larger|fewer|more|less|"
    r"similar|different|compar(?:e|ed|ison)|versus|relative"
    r")\b"
)


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
            context = folded[max(0, match.start() - 100) : match.end() + 100]
            if _STRUCTURE_DIRECT_ASSERTION.search(context):
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
                context = folded[max(0, match.start() - 100) : match.end() + 100]
                if _STRUCTURE_DIRECT_CHANGE_ASSERTION.search(context):
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
    if not evidence or any("|" in str(row) for row in evidence):
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
    return True


def _structure_entity_is_comparative_shadow(
    entity: dict[str, Any], evidence: Sequence[str]
) -> bool:
    """Drop an entity mentioned only as the comparator side of a prose claim."""

    if entity.get("features") or not evidence or any("|" in str(row) for row in evidence):
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
    grouped: dict[tuple[str, str, str], list[StructureFact]] = {}
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
        )
        for row in valid
        if isinstance(row, StructureFact) and row.fact_type == "characterization"
    }
    for fact, evidence in pending_unasserted:
        key = (
            _identity_text(fact.sample_id_raw),
            _fact_material_state(fact),
            _resolved_method_family(
                fact.data.get("method_raw"), _fact_evidence(fact)
            ),
        )
        reusable_alias = (
            key in direct_keys
            and len(_specific_method_families(fact.data.get("method_raw"))) <= 1
            and not _characterization_has_observation_context(fact)
        )
        if reusable_alias:
            valid.append(fact)
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


def _strip_unbound_conditions(
    facts: Sequence[AxisFact],
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
        ):
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


def _condition_matches_state(condition: Any, node: OwnerNode) -> bool:
    """Match one source condition to one existing state owner conservatively."""

    state = str(node.state_raw or "").strip()
    condition_text = str(condition or "").strip()
    if not state or not condition_text:
        return False
    if _literal_mention(condition_text, state):
        return True

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
    return any(
        cue in state_folded and cue in condition_folded for cue in shared_cues
    )


def _route_facts_by_condition_owner(
    anchors: Sequence[InventoryAnchor],
    facts: Sequence[AxisFact],
) -> tuple[list[AxisFact], list[PromotionIssue]]:
    """Route a source-literal condition to one existing state owner.

    This is intentionally limited to an already explicit candidate condition;
    it never creates an owner from a number or from the source text.  A tie or
    a missing match is preserved for the ambiguity gate instead of resolved by
    confidence/order.
    """

    graph = build_owner_graph(anchors)
    if not graph.nodes:
        return list(facts), []
    accepted: list[AxisFact] = []
    issues: list[PromotionIssue] = []
    for fact in facts:
        if not isinstance(fact, PropertyFact):
            accepted.append(fact)
            continue
        condition = str(fact.data.get("test_condition_raw") or "").strip()
        if not condition:
            accepted.append(fact)
            continue
        evidence = _fact_evidence(fact)
        if not _payload_grounded(condition, evidence):
            accepted.append(fact)
            continue
        record = build_promotion_records([fact])[0]
        candidates = _candidate_nodes(record, graph)
        # ``_candidate_nodes`` intentionally prefers an exact base sample
        # label.  For condition routing we also need its existing state
        # children (for example a generic ``Ti_{64}`` candidate alongside
        # ``0 s Delay``/``300 s Delay`` anchors); include only same-lineage,
        # same-role/nature nodes and never synthesize a child.
        if candidates:
            lineage = {
                _identity_text(node.material_name_raw)
                for node in candidates
                if node.material_name_raw
            }
            expanded = {
                node.owner_id: node
                for node in candidates
            }
            for node in graph.nodes:
                if not node.state_raw or node.owner_id in expanded:
                    continue
                if not any(
                    node.role == parent.role
                    and node.data_nature == parent.data_nature
                    and (
                        (
                            node.material_name_raw
                            and _identity_text(node.material_name_raw) in lineage
                        )
                        or any(
                            _identity_text(alias) in lineage
                            for alias in node.aliases
                        )
                    )
                    for parent in candidates
                ):
                    continue
                expanded[node.owner_id] = node
            candidates = list(expanded.values())
        state_matches = [
            node for node in candidates if _condition_matches_state(condition, node)
        ]
        if not state_matches:
            # Inventory responses may describe the generic candidate and the
            # delay-qualified state with different material-name prose.  A
            # source-literal label can still route safely when exactly one
            # current experimental state in the paper matches it.  A tie is a
            # no-op and remains subject to the ambiguity quarantine.
            state_matches = [
                node
                for node in graph.nodes
                if node.role == "Target"
                and node.data_nature == "Experimental"
                and node.state_raw
                and _condition_matches_state(condition, node)
            ]
        if len(state_matches) != 1:
            accepted.append(fact)
            continue
        target = state_matches[0]
        if _identity_text(target.sample_id_raw) == _identity_text(
            fact.sample_id_raw
        ):
            accepted.append(fact)
            continue
        reassigned = _reassign_fact_owner(fact, target.sample_id_raw)
        accepted.append(reassigned)
        issues.append(
            _promotion_issue(
                fact,
                code="promotion_condition_owner_reassigned",
                message=(
                    "A source-literal condition matched exactly one existing "
                    "state owner; the fact was routed there without inventing "
                    "an owner."
                ),
                expected={
                    "unique_existing_state_owner": target.sample_id_raw,
                    "owner_invented": False,
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
        if not values or len(set(values)) < 2:
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
        distinct_owner_labels = len(owners) == len(rows)
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


def _table_value_cell_matches(cell: str, value: Any) -> bool:
    """Require every numeric token in the candidate value in one cell."""

    value_tokens = _numeric_tokens(value)
    text = str(cell or "")
    if value_tokens:
        cell_tokens = _numeric_tokens(text)
        return all(token in cell_tokens for token in value_tokens)
    folded_value = _scientific_compact(value)
    return bool(folded_value and folded_value == _scientific_compact(text))


def _table_condition_matches_row(row: Sequence[str], condition: Any) -> bool:
    folded = _scientific_fold(condition)
    if not folded or folded in _UNREPORTED:
        return False
    row_text = " ".join(str(cell) for cell in row)
    if _literal_mention(row_text, str(condition)):
        return True
    tokens = [token for token in folded.split() if len(token) > 1]
    return bool(tokens) and sum(token in _scientific_fold(row_text) for token in tokens) >= max(
        1, len(tokens) // 2
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
        if normalized and all(row in normalized for row in evidence):
            matches.append(lines)
    return tuple(matches)


def _table_binding_decision(
    fact: PropertyFact,
    record: PromotionRecord,
    graph: OwnerGraph,
    source_text: str,
) -> tuple[bool | None, dict[str, Any]]:
    """Decide only source-coordinate ambiguity; ``None`` means no-op.

    ``True`` is a proven one-to-one row/column binding, ``False`` is an
    ambiguity that must be isolated, and ``None`` means the table does not
    contain enough literal coordinates for this gate to decide safely.
    """

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
    candidate_nodes = _candidate_nodes(record, graph)
    if not candidate_nodes:
        return None, {"table_rows": list(lines), "reason": "owner_not_in_inventory"}

    owner_row_hits: list[tuple[int, int, OwnerNode]] = []
    for row_index, row in enumerate(rows):
        for column_index, cell in enumerate(row):
            for node in candidate_nodes:
                if _table_owner_cell_matches(cell, node):
                    owner_row_hits.append((row_index, column_index, node))
    owner_row_keys = {(row_index, node.owner_id) for row_index, _, node in owner_row_hits}
    value = fact.data.get("value_raw")
    condition = fact.data.get("test_condition_raw")
    details: dict[str, Any] = {
        "table_rows": list(lines),
        "candidate_owner": fact.sample_id_raw,
        "candidate_value": value,
        "candidate_condition": condition,
        "owner_row_hits": [
            {"row": row_index, "column": column_index, "owner": node.sample_id_raw}
            for row_index, column_index, node in owner_row_hits
        ],
    }

    if owner_row_keys:
        candidate_rows = sorted({row_index for row_index, _ in owner_row_keys})
        conditioned_rows = [
            row_index
            for row_index in candidate_rows
            if _table_condition_matches_row(rows[row_index], condition)
        ]
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
            ]
            details["candidate_rows"] = candidate_rows
            details["value_hits"] = [
                {"row": row_index, "column": column_index}
                for row_index, column_index in row_value_hits
            ]
            if len({row_index for row_index, _ in row_value_hits}) == 1 and len(row_value_hits) == 1:
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
        ]
        details["value_hits"] = [{"row": row_index, "column": index} for index in value_hits]
        if len(value_hits) == 1:
            return True, details
        if len(value_hits) > 1:
            details["reason"] = "repeated_value_in_owner_row"
            return False, details
        # The model may have copied a rendered value whose cell is not literal
        # in this OCR table.  Do not turn that absence into a false rejection.
        return None, {**details, "reason": "value_not_located_in_owner_row"}

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
    ]
    all_owner_value_hits = [
        (row_index, column_index)
        for row_index, row in enumerate(rows)
        for column_index, header in enumerate(headers)
        if column_index < len(row)
        and any(_table_owner_cell_matches(header, node) for node in graph.nodes)
        and _table_value_cell_matches(row[column_index], value)
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
    if len(value_hits) == 1 and len(all_owner_value_hits) == 1:
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
        table_decision, table_details = _table_binding_decision(
            fact, record, graph, source_text
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
        if not _EXTERNAL_SOURCE_ASSERTION.search(support):
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
                    "external_cue": _EXTERNAL_SOURCE_ASSERTION.search(support).group(0),
                },
                evidence=list(record.evidence),
            )
        )
    return accepted, issues


def _quarantine_property_projections(
    facts: Sequence[AxisFact],
) -> tuple[list[AxisFact], list[PromotionIssue]]:
    """Keep formal material outcomes; audit comparison-only and unitless shadows."""

    accepted: list[AxisFact] = []
    issues: list[PromotionIssue] = []
    for fact in facts:
        if not isinstance(fact, PropertyFact):
            accepted.append(fact)
            continue
        name = str(fact.data.get("property_name_raw") or "")
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
            and not any("|" in row for row in record.evidence)
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
            # survivor.  Preserve the candidates for later bounded review;
            # confidence or output order must never become scientific truth.
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
    * only Structure/Characterization and non-core Properties are eligible.

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
        if isinstance(fact, StructureFact)
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
        if any("|" in row for row in record.evidence):
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
    fact_rows, stage_issues = _gate_processing_observation_projections(
        fact_rows, source_text
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
    fact_rows, stage_issues = _quarantine_structure_inferential_projections(
        fact_rows
    )
    issues.extend(stage_issues)
    fact_rows, stage_issues = _quarantine_structure_unasserted_entities(
        fact_rows
    )
    issues.extend(stage_issues)

    fact_rows, stage_issues = _gate_characterizations(
        fact_rows, source_text
    )
    issues.extend(stage_issues)
    fact_rows, stage_issues = _strip_unbound_conditions(fact_rows)
    issues.extend(stage_issues)
    fact_rows, stage_issues = _bind_explicit_treatment_conditions(fact_rows)
    issues.extend(stage_issues)
    fact_rows, stage_issues = _bind_property_condition_labels(fact_rows)
    issues.extend(stage_issues)
    fact_rows, stage_issues = _gate_tensile_source_bindings(
        anchor_rows, fact_rows, source_text
    )
    issues.extend(stage_issues)
    fact_rows, stage_issues = _quarantine_external_source_projections(
        anchor_rows, fact_rows
    )
    issues.extend(stage_issues)
    fact_rows, stage_issues = _quarantine_property_projections(fact_rows)
    issues.extend(stage_issues)
    fact_rows, stage_issues = _route_tensile_state_conflicts(
        anchor_rows, fact_rows
    )
    issues.extend(stage_issues)
    fact_rows, stage_issues = _route_facts_by_condition_owner(
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

    deduplicated = deduplicate_source_assertions(
        fact_rows,
        source_text=source_text,
    )
    fact_rows = list(deduplicated.accepted)
    issues.extend(deduplicated.issues)
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
    fact_rows, stage_issues = _quarantine_structure_exact_evidence_projections(
        fact_rows
    )
    issues.extend(stage_issues)
    fact_rows, stage_issues = _quarantine_composition_exact_evidence_projections(
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
    fact_rows, stage_issues = _quarantine_tensile_conflicts(
        fact_rows, source_text
    )
    issues.extend(stage_issues)
    fact_rows, stage_issues = _quarantine_ambiguous_respectively_groups(
        fact_rows
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
]
