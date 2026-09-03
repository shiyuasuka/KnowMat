"""Source-only inventory and bounded evidence bundle construction."""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from typing import Iterable, Mapping, Sequence

from knowmat.alpha25.contracts import AxisFact, InventoryAnchor
from knowmat.alpha25.verification_contracts import (
    AssertionEnvelope,
    EvidenceSpan,
    InventoryEntity,
    RecoveryRequest,
    VERIFICATION_PROTOCOL_VERSION,
    VerificationBundle,
    stable_id,
)


DEFAULT_MAX_BUNDLE_ASSERTIONS = 12
DEFAULT_MAX_BUNDLE_SOURCE_CHARS = 12000
DEFAULT_CONTEXT_RADIUS = 500


@dataclass(frozen=True)
class VerificationInventory:
    """Deterministic paper-level source inventory and typed fact lookup."""

    anchors: tuple[InventoryAnchor, ...]
    assertions: tuple[AssertionEnvelope, ...]
    entities: tuple[InventoryEntity, ...]
    evidence: tuple[EvidenceSpan, ...]
    recovery_evidence: tuple[EvidenceSpan, ...]
    facts_by_assertion_id: dict[str, AxisFact]
    ungrounded_assertion_ids: tuple[str, ...]


def _fact_evidence(fact: AxisFact) -> list[str]:
    values = list(getattr(fact, "source_evidence", []) or [])
    data = getattr(fact, "data", {})

    def collect_nested(node: object) -> None:
        if isinstance(node, Mapping):
            for key, nested in node.items():
                if str(key) == "source_evidence":
                    if isinstance(nested, str):
                        values.append(nested)
                    elif isinstance(nested, Sequence) and not isinstance(
                        nested, (str, bytes)
                    ):
                        values.extend(
                            str(row)
                            for row in nested
                            if isinstance(row, (str, int, float))
                        )
                collect_nested(nested)
        elif isinstance(node, Sequence) and not isinstance(node, (str, bytes)):
            for nested in node:
                collect_nested(nested)

    collect_nested(data)
    return list(dict.fromkeys(str(row).strip() for row in values if str(row).strip()))


def _compact_with_positions(value: str) -> tuple[str, list[int]]:
    greek = {
        "α": "alpha",
        "β": "beta",
        "γ": "gamma",
        "δ": "delta",
        "θ": "theta",
        "μ": "mu",
        "σ": "sigma",
    }

    def latex_command(command: str) -> str:
        lowered = command.casefold()
        if lowered.startswith("circ"):
            # OCR frequently emits ``170^\circC`` without a delimiter between
            # the TeX command and the unit. Preserve both the degree symbol and
            # the suffix unit in the compact scientific coordinate.
            return "degree" + lowered[4:]
        if lowered.startswith("pm"):
            return "plusminus" + lowered[2:]
        for symbol in ("alpha", "beta", "gamma", "delta", "theta", "sigma", "mu"):
            if lowered.startswith(symbol):
                return symbol + lowered[len(symbol) :]
        return ""

    compact: list[str] = []
    positions: list[int] = []
    index = 0
    while index < len(value):
        raw = value[index]
        if raw == "\\":
            command_end = index + 1
            while command_end < len(value) and value[command_end].isalpha():
                command_end += 1
            if command_end > index + 1:
                command = value[index + 1 : command_end]
                mapped = latex_command(command)
                for mapped_index, char in enumerate(mapped):
                    compact.append(char)
                    lowered = command.casefold()
                    if lowered.startswith("circ") and mapped_index >= len("degree"):
                        # ``\\circC`` lexes as one command even though the
                        # trailing ``C`` is the physical unit. Point the
                        # normalized suffix back to that literal character so
                        # the returned evidence span includes it.
                        positions.append(
                            index + 1 + 4 + mapped_index - len("degree")
                        )
                    elif lowered.startswith("pm") and mapped_index >= len(
                        "plusminus"
                    ):
                        positions.append(
                            index + 1 + 2 + mapped_index - len("plusminus")
                        )
                    else:
                        positions.append(index if mapped_index == 0 else command_end - 1)
                index = command_end
                continue
        for char in unicodedata.normalize("NFKC", raw).casefold():
            scientific = {
                "±": "plusminus",
                "%": "percent",
                "°": "degree",
            }.get(char)
            if scientific is not None:
                compact.extend(scientific)
                positions.extend([index] * len(scientific))
                continue
            mapped = greek.get(char, char)
            if mapped != char:
                compact.extend(mapped)
                positions.extend([index] * len(mapped))
                continue
            if not char.isalnum():
                continue
            compact.append(char)
            positions.append(index)
        index += 1
    return "".join(compact), positions


def _locate_literal(
    source_text: str,
    quoted: str,
    *,
    compact_source: str | None = None,
    compact_positions: Sequence[int] | None = None,
) -> tuple[int, int, str] | None:
    """Locate a copied quote, allowing only whitespace presentation changes."""

    start = source_text.find(quoted)
    if start >= 0:
        return start, start + len(quoted), quoted
    tokens = re.split(r"\s+", str(quoted or "").strip())
    if not tokens:
        return None
    pattern = r"\s+".join(re.escape(token) for token in tokens)
    match = re.search(pattern, source_text)
    if match is not None:
        return match.start(), match.end(), source_text[match.start() : match.end()]
    compact_quote, _ = _compact_with_positions(quoted)
    if len(compact_quote) < 16:
        return None
    if compact_source is None or compact_positions is None:
        compact_source, compact_positions = _compact_with_positions(source_text)
    compact_start = compact_source.find(compact_quote)
    if compact_start < 0:
        return None
    compact_end = compact_start + len(compact_quote) - 1
    start = compact_positions[compact_start]
    end = compact_positions[compact_end] + 1
    return start, end, source_text[start:end]


def _evidence_span(
    source_text: str,
    quoted: str,
    *,
    unit_id: str | None,
    kind: str,
    compact_source: str | None = None,
    compact_positions: Sequence[int] | None = None,
) -> EvidenceSpan | None:
    located = _locate_literal(
        source_text,
        quoted,
        compact_source=compact_source,
        compact_positions=compact_positions,
    )
    if located is None:
        return None
    start, end, literal = located
    payload = {
        "unit_id": unit_id,
        "kind": kind,
        "text": literal,
        "start_char": start,
        "end_char": end,
    }
    return EvidenceSpan(
        evidence_id=stable_id("evidence", payload),
        **payload,
    )


def _ordered_projection_evidence_span(
    source_text: str,
    source_scope: str,
    quoted: str,
    *,
    unit_id: str | None,
) -> EvidenceSpan | None:
    """Locate the smallest literal line window proving an ordered projection."""

    located_scope = _locate_literal(source_text, source_scope)
    if located_scope is None:
        return None
    scope_start, _scope_end, literal_scope = located_scope

    def tokens(value: str) -> list[tuple[str, int, int]]:
        return [
            (
                unicodedata.normalize("NFKC", match.group(0)).casefold(),
                match.start(),
                match.end(),
            )
            for match in re.finditer(r"[^\W_]+", value, flags=re.UNICODE)
        ]

    wanted = tokens(quoted)
    available = tokens(literal_scope)
    if len(wanted) < 3:
        return None
    candidates: list[list[tuple[str, int, int]]] = []
    for start_index, available_token in enumerate(available):
        if available_token[0] != wanted[0][0]:
            continue
        matched = [available_token]
        cursor = start_index + 1
        for token, _start, _end in wanted[1:]:
            while cursor < len(available) and available[cursor][0] != token:
                cursor += 1
            if cursor >= len(available):
                break
            matched.append(available[cursor])
            cursor += 1
        if len(matched) == len(wanted):
            candidates.append(matched)
    if not candidates:
        return None
    matched = min(
        candidates,
        key=lambda rows: (rows[-1][2] - rows[0][1], rows[0][1]),
    )

    local_start = literal_scope.rfind("\n", 0, matched[0][1]) + 1
    line_end = literal_scope.find("\n", matched[-1][2])
    local_end = len(literal_scope) if line_end < 0 else line_end
    literal = literal_scope[local_start:local_end]
    if not literal.strip():
        return None
    start = scope_start + local_start
    end = scope_start + local_end
    payload = {
        "unit_id": unit_id,
        "kind": "context",
        "text": source_text[start:end],
        "start_char": start,
        "end_char": end,
    }
    return EvidenceSpan(evidence_id=stable_id("evidence", payload), **payload)


def build_verification_inventory(
    anchors: Iterable[InventoryAnchor],
    facts: Iterable[AxisFact],
    *,
    source_text: str,
    task_ids: Sequence[str | None] | None = None,
    task_source_scopes: Mapping[str, str] | None = None,
) -> VerificationInventory:
    """Create source-grounded non-Composition assertion and entity inventories."""

    anchor_rows = list(anchors)
    fact_rows = list(facts)
    if task_ids is not None and len(task_ids) != len(fact_rows):
        raise ValueError("task_ids must contain exactly one entry per fact")
    lineage = list(task_ids) if task_ids is not None else [None] * len(fact_rows)
    source_scopes = dict(task_source_scopes or {})

    evidence_by_id: dict[str, EvidenceSpan] = {}
    compact_source, compact_positions = _compact_with_positions(source_text)
    assertions: list[AssertionEnvelope] = []
    facts_by_assertion_id: dict[str, AxisFact] = {}
    ungrounded: list[str] = []

    for fact, task_id in zip(fact_rows, lineage):
        if fact.axis == "composition":
            continue
        evidence_ids: list[str] = []
        for quote in _fact_evidence(fact):
            span = _evidence_span(
                source_text,
                quote,
                unit_id=getattr(fact, "evidence_unit_id", None),
                kind="assertion",
                compact_source=compact_source,
                compact_positions=compact_positions,
            )
            if span is None:
                scope = str(source_scopes.get(task_id or "") or "").strip()
                if scope:
                    span = _ordered_projection_evidence_span(
                        source_text,
                        scope,
                        quote,
                        unit_id=getattr(fact, "evidence_unit_id", None),
                    )
                if span is None:
                    continue
            evidence_by_id.setdefault(span.evidence_id, span)
            evidence_ids.append(span.evidence_id)
        if (
            not evidence_ids
            and task_id
            and str(source_scopes.get(task_id) or "").strip()
        ):
            span = _evidence_span(
                source_text,
                str(source_scopes[task_id]).strip(),
                unit_id=getattr(fact, "evidence_unit_id", None),
                kind="context",
                compact_source=compact_source,
                compact_positions=compact_positions,
            )
            if span is not None:
                evidence_by_id.setdefault(span.evidence_id, span)
                evidence_ids.append(span.evidence_id)
        candidate = fact.model_dump(mode="json")
        identity_payload = {
            "task_id": task_id,
            "evidence_unit_id": getattr(fact, "evidence_unit_id", None),
            "axis": fact.axis,
            "fact_type": fact.fact_type,
            "candidate": candidate,
            "evidence_ids": sorted(set(evidence_ids)),
        }
        assertion_id = stable_id("assertion", identity_payload)
        envelope = AssertionEnvelope(
            assertion_id=assertion_id,
            axis=fact.axis,
            fact_type=fact.fact_type,
            sample_id_raw=fact.sample_id_raw,
            task_id=task_id,
            evidence_unit_id=getattr(fact, "evidence_unit_id", None),
            evidence_ids=evidence_ids,
            candidate=candidate,
        )
        assertions.append(envelope)
        facts_by_assertion_id[assertion_id] = fact
        if not evidence_ids:
            ungrounded.append(assertion_id)

    entities: list[InventoryEntity] = []
    seen_entities: set[str] = set()
    for anchor in anchor_rows:
        evidence_ids: list[str] = []
        for quote in anchor.source_evidence:
            span = _evidence_span(
                source_text,
                quote,
                unit_id=None,
                kind="anchor",
                compact_source=compact_source,
                compact_positions=compact_positions,
            )
            if span is None:
                continue
            evidence_by_id.setdefault(span.evidence_id, span)
            evidence_ids.append(span.evidence_id)
        if not evidence_ids:
            continue
        payload = {
            "sample_id_raw": anchor.sample_id_raw,
            "material_name_raw": anchor.material_name_raw,
            "state_raw": anchor.state_raw,
            "role": anchor.role,
            "data_nature": anchor.data_nature,
            "evidence_ids": sorted(set(evidence_ids)),
        }
        entity_id = stable_id("entity", payload)
        if entity_id in seen_entities:
            continue
        seen_entities.add(entity_id)
        entities.append(InventoryEntity(entity_id=entity_id, **payload))

    assertions.sort(key=lambda row: (row.axis, row.assertion_id))
    entities.sort(key=lambda row: row.entity_id)
    evidence = sorted(
        evidence_by_id.values(), key=lambda row: (row.start_char, row.end_char, row.evidence_id)
    )
    recovery_evidence = _uncovered_recovery_evidence(
        source_text,
        covered=[
            evidence_by_id[evidence_id]
            for assertion in assertions
            for evidence_id in assertion.evidence_ids
            if evidence_id in evidence_by_id
        ],
    )
    return VerificationInventory(
        anchors=tuple(anchor_rows),
        assertions=tuple(assertions),
        entities=tuple(entities),
        evidence=tuple(evidence),
        recovery_evidence=tuple(recovery_evidence),
        facts_by_assertion_id=facts_by_assertion_id,
        ungrounded_assertion_ids=tuple(sorted(ungrounded)),
    )


_RECOVERY_SPAN = re.compile(r"[^\n.!?;]+(?:[.!?;]|\n|$)")
_LITERAL_MEASUREMENT = re.compile(
    r"(?i)(?:[<>≤≥~≈]?\s*[-+]?\d+(?:\.\d+)?(?:\s*(?:±|\+/-)\s*\d+(?:\.\d+)?)?"
    r"\s*(?:gpa|mpa|kpa|pa|hv|hrc|%|°\s*c|k|h|hr|hrs|min|s|ms|hz|"
    r"mm|cm|nm|um|µm|μm|m/s|mm/s|kg/m3|g/cm3|wt\.?\s*%|at\.?\s*%|vol\.?\s*%))"
)
_QUALITATIVE_COMPARISON = re.compile(
    r"(?i)\b(?:higher|lower|greater|smaller|stronger|weaker|more ductile|"
    r"less ductile|increased|decreased|superior|inferior|comparable|similar)\b"
)
_NONCOMPOSITION_SIGNAL = re.compile(
    r"(?i)\b(?:process|fabricat|anneal|heat treat|sinter|laser|scan speed|"
    r"microstructure|phase|grain|pore|porosity|precipitat|characteri[sz]|"
    r"strength|yield|uts|elongation|ductility|hardness|fatigue|creep|"
    r"tensile|modulus|density|corrosion|wear|conductivity)\b"
)
_CHART_RECOVERY_EXCLUSION = re.compile(
    r"(?i)(?:vlm[- ]digitized|digitized[_ ]chart|chart[_ ]series|"
    r"figure[_ ]\d+[_ ]digitized\.csv|estimated from (?:the )?(?:plot|curve|chart))"
)


def _uncovered_recovery_evidence(
    source_text: str,
    *,
    covered: Sequence[EvidenceSpan],
) -> list[EvidenceSpan]:
    """Find only explicit non-Composition source assertions not already covered."""

    rows: list[EvidenceSpan] = []
    for match in _RECOVERY_SPAN.finditer(source_text):
        literal = match.group(0).strip()
        if not literal or len(literal) > 1800:
            continue
        if _CHART_RECOVERY_EXCLUSION.search(literal):
            continue
        if not _NONCOMPOSITION_SIGNAL.search(literal):
            continue
        if not (
            _LITERAL_MEASUREMENT.search(literal)
            or _QUALITATIVE_COMPARISON.search(literal)
        ):
            continue
        start = match.start() + len(match.group(0)) - len(match.group(0).lstrip())
        end = start + len(literal)
        if any(start < row.end_char and end > row.start_char for row in covered):
            continue
        payload = {
            "unit_id": None,
            "kind": "recovery",
            "text": source_text[start:end],
            "start_char": start,
            "end_char": end,
        }
        rows.append(EvidenceSpan(evidence_id=stable_id("evidence", payload), **payload))
    unique = {row.evidence_id: row for row in rows}
    return sorted(unique.values(), key=lambda row: (row.start_char, row.evidence_id))


def build_recovery_requests(
    inventory: VerificationInventory,
    *,
    max_assertions: int = 10,
    max_source_chars: int = 12000,
) -> list[RecoveryRequest]:
    """Group uncovered literal source assertions for one non-recursive scan."""

    if not 1 <= max_assertions <= 10:
        raise ValueError("max_assertions must be between 1 and 10")
    if not 1 <= max_source_chars <= 12000:
        raise ValueError("max_source_chars must be between 1 and 12000")
    groups: list[list[EvidenceSpan]] = []
    current: list[EvidenceSpan] = []
    chars = 0
    for row in inventory.recovery_evidence:
        if current and (
            len(current) >= max_assertions or chars + len(row.text) > max_source_chars
        ):
            groups.append(current)
            current = []
            chars = 0
        if len(row.text) > max_source_chars:
            continue
        current.append(row)
        chars += len(row.text)
    if current:
        groups.append(current)

    requests: list[RecoveryRequest] = []
    for group in groups:
        combined = "\n".join(row.text for row in group).casefold()
        entities = [
            entity
            for entity in inventory.entities
            if entity.sample_id_raw.casefold() in combined
            or entity.material_name_raw
            and entity.material_name_raw.casefold() in combined
        ]
        payload = {
            "protocol_version": VERIFICATION_PROTOCOL_VERSION,
            "evidence_ids": [row.evidence_id for row in group],
            "entity_ids": [row.entity_id for row in entities],
            "max_assertions": max_assertions,
            "max_source_chars": max_source_chars,
        }
        requests.append(
            RecoveryRequest(
                request_id=stable_id("recovery", payload),
                evidence=group,
                entities=entities,
                source_char_count=sum(len(row.text) for row in group),
            )
        )
    return requests


def _context_spans(
    source_text: str,
    exact: Sequence[EvidenceSpan],
    *,
    radius: int,
) -> list[EvidenceSpan]:
    intervals = sorted(
        (
            max(0, row.start_char - radius),
            min(len(source_text), row.end_char + radius),
        )
        for row in exact
    )
    merged: list[list[int]] = []
    for start, end in intervals:
        if merged and start <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], end)
        else:
            merged.append([start, end])
    contexts: list[EvidenceSpan] = []
    for start, end in merged:
        literal = source_text[start:end]
        payload = {
            "unit_id": None,
            "kind": "context",
            "text": literal,
            "start_char": start,
            "end_char": end,
        }
        contexts.append(
            EvidenceSpan(evidence_id=stable_id("evidence", payload), **payload)
        )
    return contexts


def _relevant_entities(
    assertions: Sequence[AssertionEnvelope],
    entities: Sequence[InventoryEntity],
    evidence_by_id: dict[str, EvidenceSpan],
    contexts: Sequence[EvidenceSpan],
) -> list[InventoryEntity]:
    owner_labels = {row.sample_id_raw.casefold() for row in assertions}
    context_text = "\n".join(row.text for row in contexts).casefold()
    selected: list[InventoryEntity] = []
    for entity in entities:
        if (
            entity.sample_id_raw.casefold() in owner_labels
            or entity.sample_id_raw.casefold() in context_text
            or entity.material_name_raw
            and entity.material_name_raw.casefold() in context_text
        ):
            if all(evidence_id in evidence_by_id for evidence_id in entity.evidence_ids):
                selected.append(entity)
    return selected


def _bundle_material(
    assertions: Sequence[AssertionEnvelope],
    inventory: VerificationInventory,
    *,
    source_text: str,
    context_radius: int,
) -> tuple[list[EvidenceSpan], list[InventoryEntity]]:
    evidence_by_id = {row.evidence_id: row for row in inventory.evidence}
    exact = [
        evidence_by_id[evidence_id]
        for assertion in assertions
        for evidence_id in assertion.evidence_ids
        if evidence_id in evidence_by_id
    ]
    exact_by_id = {row.evidence_id: row for row in exact}
    contexts = _context_spans(source_text, list(exact_by_id.values()), radius=context_radius)
    entities = _relevant_entities(
        assertions,
        inventory.entities,
        evidence_by_id,
        contexts,
    )
    entity_evidence = {
        evidence_id
        for entity in entities
        for evidence_id in entity.evidence_ids
        if evidence_id in evidence_by_id
    }
    rows = {
        **exact_by_id,
        **{evidence_id: evidence_by_id[evidence_id] for evidence_id in entity_evidence},
        **{row.evidence_id: row for row in contexts},
    }
    return (
        sorted(rows.values(), key=lambda row: (row.start_char, row.kind, row.evidence_id)),
        sorted(entities, key=lambda row: row.entity_id),
    )


def build_verification_bundles(
    inventory: VerificationInventory,
    *,
    source_text: str,
    max_assertions: int = DEFAULT_MAX_BUNDLE_ASSERTIONS,
    max_source_chars: int = DEFAULT_MAX_BUNDLE_SOURCE_CHARS,
    context_radius: int = DEFAULT_CONTEXT_RADIUS,
) -> list[VerificationBundle]:
    """Group grounded candidates without crossing the configured context caps."""

    if not 1 <= max_assertions <= 12:
        raise ValueError("max_assertions must be between 1 and 12")
    if not 1 <= max_source_chars <= 12000:
        raise ValueError("max_source_chars must be between 1 and 12000")
    grounded = [row for row in inventory.assertions if row.evidence_ids]
    evidence_by_id = {row.evidence_id: row for row in inventory.evidence}

    def position(row: AssertionEnvelope) -> int:
        positions = [
            evidence_by_id[evidence_id].start_char
            for evidence_id in row.evidence_ids
            if evidence_id in evidence_by_id
        ]
        return min(positions) if positions else len(source_text)

    ordered = sorted(grounded, key=lambda row: (row.axis, position(row), row.assertion_id))
    groups: list[list[AssertionEnvelope]] = []
    current: list[AssertionEnvelope] = []
    for assertion in ordered:
        if current and assertion.axis != current[0].axis:
            groups.append(current)
            current = []
        proposed = [*current, assertion]
        evidence, _ = _bundle_material(
            proposed,
            inventory,
            source_text=source_text,
            context_radius=context_radius,
        )
        mandatory_ids = {
            evidence_id
            for candidate in proposed
            for evidence_id in candidate.evidence_ids
        }
        # Entity matching may select many remote anchors merely because a
        # common alloy/material name occurs in local context. Those anchors
        # are optional and are trimmed when the final bounded bundle is built;
        # counting them here forces every assertion into a singleton bundle
        # and defeats cross-candidate verification. Pack by the evidence that
        # must survive: exact candidate spans plus bounded local context.
        proposed_chars = sum(
            len(row.text)
            for row in evidence
            if row.evidence_id in mandatory_ids or row.kind == "context"
        )
        if current and (
            len(proposed) > max_assertions or proposed_chars > max_source_chars
        ):
            groups.append(current)
            current = [assertion]
        else:
            current = proposed
    if current:
        groups.append(current)

    bundles: list[VerificationBundle] = []
    for group in groups:
        evidence, entities = _bundle_material(
            group,
            inventory,
            source_text=source_text,
            context_radius=context_radius,
        )
        # A single very long evidence quote is source data, not permission to
        # violate the provider request cap. Retain the literal assertion spans
        # first, then the smallest context/entity spans that fit.
        mandatory_ids = {
            evidence_id for assertion in group for evidence_id in assertion.evidence_ids
        }
        selected: list[EvidenceSpan] = []
        used = 0
        for row in sorted(
            evidence,
            key=lambda item: (
                item.evidence_id not in mandatory_ids,
                # After the candidate's exact spans, retain its bounded local
                # source neighborhood before remote entity anchors. Common
                # material names can otherwise select dozens of anchors and
                # crowd the only text that proves state/condition fields out
                # of a capped bundle.
                item.kind != "context",
                len(item.text),
                item.start_char,
            ),
        ):
            if used + len(row.text) > max_source_chars:
                continue
            selected.append(row)
            used += len(row.text)
        selected_ids = {row.evidence_id for row in selected}
        if not mandatory_ids <= selected_ids:
            # The assertion cannot be safely sent when its own literal evidence
            # exceeds the cap; it remains unverified and will become unresolved.
            continue
        entities = [
            row for row in entities if set(row.evidence_ids) <= selected_ids
        ]
        selected.sort(key=lambda row: (row.start_char, row.kind, row.evidence_id))
        payload = {
            "protocol_version": VERIFICATION_PROTOCOL_VERSION,
            "axis": group[0].axis,
            "assertion_ids": [row.assertion_id for row in group],
            "entity_ids": [row.entity_id for row in entities],
            "evidence_ids": [row.evidence_id for row in selected],
            "max_assertions": max_assertions,
            "max_source_chars": max_source_chars,
            "context_radius": context_radius,
        }
        bundles.append(
            VerificationBundle(
                bundle_id=stable_id("bundle", payload),
                axis=group[0].axis,
                assertions=list(group),
                entities=entities,
                evidence=selected,
                source_char_count=used,
            )
        )
    return bundles


__all__ = [
    "DEFAULT_CONTEXT_RADIUS",
    "DEFAULT_MAX_BUNDLE_ASSERTIONS",
    "DEFAULT_MAX_BUNDLE_SOURCE_CHARS",
    "VerificationInventory",
    "build_recovery_requests",
    "build_verification_bundles",
    "build_verification_inventory",
]
