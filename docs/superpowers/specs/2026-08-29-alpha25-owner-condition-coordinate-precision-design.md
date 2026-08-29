# Alpha25 owner/condition coordinate closure gate

## Status

Approved for implementation by the ongoing precision-first GLM pipeline
optimization on 2026-08-29. This iteration does not change the professionally
reviewed extraction prompt, provider/model selection, or the public
`final.json` schema.

## Objective

Reduce false-positive facts caused by projecting one source assertion onto the
wrong material state or by copying a methods/test condition into a result that
does not carry that coordinate. Improve overall unique-loose precision and
core-tensile attribution while preserving source-supported Composition facts.

## Design

Add one deterministic, source-only publication gate after existing owner and
condition routing passes:

1. For non-table facts, retain an owner-sensitive fact only when its own
   evidence contains a literal alias of the selected owner, or a unique
   previously-resolved source coordinate. A fact whose evidence names multiple
   sibling owners without an explicit one-to-one mapping is quarantined rather
   than broadcast.
2. For core tensile Properties, require a closed value coordinate: the same
   assertion must bind the value to one existing owner and, when multiple
   state/orientation/temperature candidates exist, to one state coordinate.
   A methods paragraph is reusable only when the bounded tensile event
   explicitly declares universal scope for all relevant specimens. Otherwise
   the scientific value remains out of formal Properties and its complete
   candidate is audited.
3. Preserve explicit table rows, `respectively` mappings, collective scope
   assertions, Reference items, and Composition's established table/prose path
   when their coordinates are unique and source-proven.
4. Never infer a missing owner/state, repair a value, use GT, or consult a
   provider. Quarantined records keep the complete fact, evidence, reason,
   candidate owners, and a deterministic issue code in the existing audit
   stream.

## Data flow and audit

The gate returns accepted facts plus `PromotionIssue` records. Materialization
continues to emit the unchanged `final.json` contract. New issue codes are
short, axis-specific, and stable so `issues.json`/`issues.md` remain suitable
for manual review. `quality_audit.json` stores the full before/after payload.

## Safety boundaries

- No prompt or extraction schema changes.
- No paper-specific IDs, expected counts, GT data, or model-name branches.
- Composition facts are not removed by the generic gate; existing composition
  gates remain the sole authority for composition-specific corrections.
- Explicit source/table coordinates are always preferred to quarantine.

## Verification

Add positive and negative unit tests for owner-local prose, multi-owner prose,
unique table/`respectively` coordinates, method-only tensile conditions,
explicit universal tensile scope, and audit completeness. Then rematerialize
the frozen 30-paper cache and compare r240 using unique-loose precision/F1,
owner/condition conflicts, duplicate claims, core-tensile strict F1, and
Composition byte identity.
