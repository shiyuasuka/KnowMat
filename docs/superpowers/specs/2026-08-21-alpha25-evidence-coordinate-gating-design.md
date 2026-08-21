# Alpha25 evidence-coordinate gating

## Goal

Improve GLM-5.2 Alpha25 precision without changing the reviewed extraction
prompt, the Alpha25 contract, or the public `final.json` shape.  The gate
must suppress cross-chunk projection: a fact copied from one shared table or
multi-owner prose span must not be emitted as several owner-specific facts
unless the source provides a unique coordinate for that owner.

## Design

The gate runs after the existing source-backed owner recovery and before facts
are grouped into material items.  It is deterministic and only consumes the
candidate fact, source evidence, and the identity index.

1. Complete Markdown tables are treated as coordinate-bearing evidence.  A
   property fact is eligible when its semantic row, owner column/row, and value
   cell are each unique.  A table with multiple possible coordinates remains
   unchanged and is audited rather than guessed.
2. A prose fact may be retained when its evidence explicitly names exactly one
   resolved owner, or when a numeric `respectively` sentence has a one-to-one
   owner/value mapping.  A shared qualitative/comparison sentence copied to
   multiple owners is isolated because the schema cannot represent the joint
   assertion without manufacturing separate owners.
3. Empty, method-only, source-locator, and comparison-heading properties remain
   in the existing audit trail but are excluded from formal `Properties`.
4. Every isolation/removal emits a short issue code plus complete before/evidence
   payload through the existing materialization issue path.  No production rule
   reads business GT or expert GT.

## Safety and compatibility

- The gate is opt-in through the existing Alpha25 quality path and defaults to
  the precision-first behavior for Alpha25 runs.
- Existing tensile-specific table/owner rules run first and are not weakened.
- Explicit multi-owner tensile assertions already covered by the current
  bundle rules remain preserved.
- `final.json` remains schema-compatible; only the facts present in formal
  arrays change.  Audit consumers continue to receive `issues.json/.md` data.

## Verification

- Unit tests cover unique table coordinates, ambiguous tables, shared prose,
  `respectively` mappings, and empty/method properties.
- A frozen-cache single-paper pilot must show fewer shared-projection and
  duplicate claims with no increase in wrong-owner/value-conflict tags.
- The 30-paper replay is accepted only if unique loose/core-tensile F1 does
  not regress and unsupported/duplicate counts decrease.
