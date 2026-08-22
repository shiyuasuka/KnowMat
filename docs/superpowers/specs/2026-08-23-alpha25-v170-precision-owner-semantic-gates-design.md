# Alpha25 v170 precision-first owner and semantic gates

## Goal

Reduce unsupported projections and owner/value misattribution in the Alpha25
materialized ledger while preserving the reviewed extraction prompt, existing
`final.json` shape, and complete auditability.  The target is higher precision
on Composition, Structure, and non-core Properties; recall is allowed to fall
only for facts whose source coordinate or scientific semantics cannot be proved.

## Design

### Composition formula and coordinate gate

The promotion layer will distinguish literal nominal designations and chemical
formulae from component observations.  Formula-like labels such as
`Al92Ti2Fe2Co2Ni2` remain identity/provenance text unless the candidate carries
an explicit source unit and a component-level quantity.  Numeric components
must be grounded in their own evidence.  A Markdown table candidate must carry
one recoverable row/column coordinate (material, feedstock, point, or region);
when multiple rows or owners remain possible, the candidate is quarantined with
the original table evidence.

### Structure precision gate

Keep explicit entity presence/absence and quantitative features.  Isolate
generic categories, comparative/inferential prose, method-only values, and
duplicate qualitative shadows when the same source assertion already contains
an atomic entity or measurement.  A structure fact without an atomic entity,
quantitative feature, or source-local coordinate is not promoted.

### Property semantic/table gate

Reject unresolved or model-only labels (`unknown`, Young/Voigt model names,
table headings without a property semantic) from formal `Properties`.  A
numeric non-core property survives only when its raw property label matches a
source table row/column or a source-local asserted result.  Ambiguous header or
owner matches are quarantined, never broadcast.

## Audit and compatibility

Every rejection uses a short deterministic issue code and stores the complete
fact, evidence, coordinate candidates, and reason in the existing quality audit
ledger.  No API calls or prompt changes are required for the v170 test; the
frozen Alpha25 task cache is rematerialized offline.  `final.json` keeps its
existing top-level keys and item schema.

## Validation

1. Add unit tests for formula-vs-composition, point/feedstock row binding,
   structure atomicity, and model/unknown property labels.
2. Run the Alpha25 test suite and the offline rematerialization script.
3. Compare v170 against v169 with the independent GPT expert GT and report
   precision, recall, F1, owner/value conflicts, duplicates, and per-axis
   counts.  If precision does not improve, retain v169 as the production
   candidate and keep v170 as an audited experiment.
