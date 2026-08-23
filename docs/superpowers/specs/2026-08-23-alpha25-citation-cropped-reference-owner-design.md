# Alpha25 citation-cropped reference owner design

## Goal

Improve GLM Alpha25 precision for literature comparison tables without changing
the business-reviewed prompt, Alpha25 schema, model/provider behavior, or the
public `final.json` format. Facts that can be proven to belong to a cited
literature row must not remain on a current-experiment Target owner. Every
migration, normalization, or quarantine remains available in
`quality_audit.json` and the existing issues JSON/Markdown files.

## Source-bound routing

Only a literal Markdown or HTML table with a `Reference` column, a material
owner column, and a numeric citation may create deterministic Reference
anchors. Each anchor keeps the full original row and uses a citation-specific
identity such as `Astroloy [32] [reference]`.

When an evidence-unit projection retains the citation, the citation selects
the corresponding Reference sibling. When projection removes the `Reference`
and `Year` columns, routing requires an exact match between the remaining cells
and one original cited row. Exact trailing-column coordinates take precedence
over a more permissive ordered-cell projection. No fuzzy chemistry/name match
or GT lookup is permitted.

If two cited rows remain identical after projection, the pipeline does not
guess between them. The existing owner-ambiguity path isolates the candidate
and preserves its full payload and evidence for review. A successful migration
also replaces a copied Target state with the Reference anchor's
`literature-reported` state.

## Structure normalization

A table cell such as `Carbide = Yes` may be emitted by the model as a bare
Structure entity whose serialized value becomes `Carbide`. For table evidence
only, an entity with no nested features and exact raw expression `Yes` is
normalized to `Carbide presence = Yes`. The original entity and normalized
feature are both recorded in audit. Prose entities and non-binary table values
are unaffected.

A prose Structure entity whose complete name is only a carrier noun such as
`material`, `sample`, or `region`, has no feature payload, and is not table
evidence is isolated. Any independent numeric/categorical feature in the same
fact remains eligible for output.

## Invariants

- No prompt, schema, model-name branch, or provider option changes.
- `final.json` retains its existing public shape.
- Core tensile facts and Composition/Processing/Properties metrics do not
  regress.
- A current-experiment table without a literal `Reference` column cannot enter
  this routing path.
- Ambiguous cited rows are never assigned by row order or first-match choice.
- Full before/after/removed payloads and evidence remain in audit and issues.

## Verification

Run positive and negative unit tests for citation-specific anchors, cropped-row
matching, duplicate cited rows, state correction, generic entities, and binary
table normalization. Run the focused promotion/materialization suites and the
full repository suite. Finally replay the same frozen 30-paper task cache used
by v187i and compare against the adjudicated GPT expert GT. Keep the change only
if unique loose precision, strict precision, and Structure precision improve,
wrong-owner errors decline, and core tensile output remains identical.
