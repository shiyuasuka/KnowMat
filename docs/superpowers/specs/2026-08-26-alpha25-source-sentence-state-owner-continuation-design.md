# Alpha25 source-sentence state-owner continuation design

## Goal

Restore direct core-tensile scalars whose extraction evidence is a shortened
fragment of one complete source sentence and therefore omits the state/owner
prefix. The change must improve recall without weakening the precision-first
owner gates or changing prompts, schema, Composition semantics, or the
`final.json` contract.

## Chosen approach

Add one bounded resolver inside the existing core-tensile owner ambiguity gate.
The resolver may select only an owner/state already present in the paper-local
inventory. It accepts a candidate only when all of these source-only conditions
hold:

- the candidate is a direct scalar core-tensile result with a supported unit;
- the property name is not comparative, derived, theoretical, calculated,
  relative, incremental, a difference, or a ratio;
- the candidate evidence is prose and is contained in exactly one complete
  source sentence;
- the complete candidate value occurs exactly once in that sentence;
- the candidate tensile family and its declared unit are literal in that
  sentence;
- exactly one existing state in the candidate lineage is literal in the same
  sentence; and
- after duplicate graph anchors are collapsed, that state identifies one
  current experimental owner identity.

The resolver does not use paper names, GT values, model names, extraction
order, nearest-neighbour text, adjacent sentences, or approximate numeric
matching. Tables, multi-state sentences, repeated evidence occurrences,
collective/comparative assertions, and unresolved units remain fail-closed.

## Data flow and audit

The new resolver runs only after the existing literal-owner and complete
assertion checks fail, and immediately before the final state-sibling
quarantine. A successful decision keeps the scientific value and unit
unchanged, reassigns only to an already-declared owner when necessary, and
emits an informational promotion issue containing:

- the complete matched source sentence;
- the before and after fact payloads;
- the selected owner ID, sample label, and state; and
- the exact decision constraints.

Rejected candidates continue through the existing quarantine path, so
`quality_audit.json` and `issues.json/.md` retain the full record. The formal
`final.json` shape remains unchanged.

## Verification

Focused tests must prove that:

- a shortened UTS or elongation phrase is restored when one source sentence
  uniquely names `as-built`;
- direct CL/PL UTS values are retained only for the source-named state;
- difference, theoretical, calculated, relative, increment, and ratio
  properties are never restored;
- two states in one sentence, two containing sentences, a mismatched unit,
  a mismatched property family, and table evidence all remain quarantined;
- duplicate inventory anchors do not manufacture ambiguity, while distinct
  state identities still do.

Run the focused promotion tests first, rematerialize the two affected papers,
then run a frozen pilot and the 30-paper comparison. Core-tensile loose
precision is a hard non-regression gate; any additional formal fact must be
source-supported and either match the GPT expert ledger or be explicitly
adjudicated as a true expert-ledger omission.
