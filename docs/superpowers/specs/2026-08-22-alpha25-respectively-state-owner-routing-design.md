# Alpha25 Explicit `Respectively` State-Owner Routing

## Goal

Correct a narrow owner-coordinate loss that survives the current Alpha25
promotion gates: a prose assertion explicitly pairs values with conditions
(`respectively`), but the extracted values remain attached to a generic base
owner even though the paper inventory already contains one state owner for
each condition. This is a source-only correction; it does not use GT data,
model/provider identity, or prompt changes.

## Scope and invariants

- Apply only to existing `PropertyFact`, `CompositionFact`, and
  `StructureFact` candidates. No owner may be created from prose.
- Require an exact shared evidence span containing an explicit condition
  coordinate and a one-to-one mapping to existing state owners. Numeric tokens
  must match as complete values (`0 s` must not match `300 s`).
- Require every mapped target to be unique within the paper and distinct from
  the other mapped targets. Ties, missing states, and owner-implicit prose
  remain unchanged or are handled by existing ambiguity quarantine.
- Preserve the public `final.json` schema. Reassigned facts retain their full
  source evidence and are recorded with complete before/after payloads in the
  existing audit stream. Add a concise issue code
  `promotion_respectively_state_owner_reassigned`.
- Do not alter the reviewed extraction prompt or provider-specific request
  handling.

## Data flow

1. Build the existing paper-local `OwnerGraph` from inventory anchors.
2. Group facts by normalized evidence and metric descriptor. Groups are
   considered only when the source evidence contains `respectively` or an
   equivalent ordered condition/value assertion.
3. Extract the condition coordinate already carried by each fact. If the
   condition is missing, do not guess it from list order; the group is left for
   the existing ambiguity gate.
4. Resolve each condition against state labels using the existing conservative
   matcher. Accept only a bijection: one fact → one unique existing state
   owner, with no duplicate target and no unresolved member.
5. Reassign only facts whose current owner differs from the resolved state
   owner. Keep values, conditions, evidence, and schema fields unchanged.

## Failure handling

Any failed uniqueness check is a no-op for this rule. Existing gates continue
to decide whether the unresolved group is accepted or quarantined. The rule
never falls back to item order, confidence, material-name similarity, or a
chemistry-only match.

## Verification

- Add unit tests for decimal/token boundaries, bijective `0/120 s` mapping,
  duplicate-state ambiguity, and non-`respectively` no-op behavior.
- Rematerialize the cached 30-paper corpus without API calls and verify
  30/30 success, unchanged `final.json` schema, exact audit coverage, and a
  paper-level diff.
- Re-run the independent-GT comparison and report final claim counts,
  precision/recall/F1, and any legal source-supported facts removed.
