# Alpha25 exact state-owner isolation design

## Goal

Prevent downstream materialization from merging independent numbered treatment
states such as `HIP1` and `HIP2` (or `HT1` and `HT2`) into one canonical item.
The fix must preserve the existing Alpha25 prompt, schema, `final.json` shape,
audit records, and tolerant matching of prose temperature/time variants.

## Design

`_expand_distinct_state_anchors()` remains the single place that creates
state-qualified material identities. State bucketing will use a stable compact
treatment-code discriminator whenever an explicit `HIP<n>` or `HT<n>` code is
present. The discriminator normalizes spacing, hyphens, and case, so `HIP1`,
`HIP 1`, and `hip-1` share one bucket, while `HIP1` and `HIP2` remain separate.
Existing multi-component preparation handling (`HIP2 + HT2` versus
`as-sintered + HIP2 + HT2`) remains unchanged.

Within a generic state category, an exact qualifier tuple is selected before a
qualifier superset. Superset matching remains a fallback only for source labels
that omit a detail which is uniquely recoverable from a sibling state. This
prevents a composite or broader state from stealing a narrower numbered state.

When a shared processing-table evidence envelope contains structured parameter
payloads with distinct values for the competing owners, the rows are retained
as an explicit table coordinate. The shared-projection quarantine still applies
to processing prose or copied rows without owner-distinct values.

## Invariants

- `HIP1` and `HIP2` produce distinct canonical display labels and distinct
  owners.
- Parameters explicitly owned by `HIP1` cannot appear under `HIP2`, and vice
  versa.
- `HT1` through `HT4` remain distinct when independently anchored.
- Same-coordinate presentation variants still coalesce.
- Unqualified facts continue to stay on the base material and are not
  broadcast to every state.
- Any rejected or quarantined projection continues to be represented in the
  existing `issues.json`/`quality_audit.json` flow.

## Verification

Add focused materialization tests for numbered HIP and HT states, including
owner-specific processing parameters and same-coordinate textual variants.
Run the Alpha25 materialization suite, the full test suite, rematerialize the
30 cached papers, and regenerate the independent-GT comparison. Precision is a
non-regression gate; a recall change is acceptable only when it comes from
restoring a previously merged owner.
