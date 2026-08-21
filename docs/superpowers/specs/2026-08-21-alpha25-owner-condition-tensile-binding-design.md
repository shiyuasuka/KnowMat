# Alpha25 Source-Only Owner/Condition Binding

## Goal

Improve GLM-5.2 Alpha25 precision for Properties/tensile and owner attribution
without changing the professionally reviewed prompt, public `final.json`
shape, provider configuration, or the protected Composition path.

The v89r audit shows the actionable residuals are copied or mis-bound claims:
266 matcher-level `wrong_owner`, 45 `condition_conflict`, and 178
`value_conflict` candidates. These counts are diagnostic rather than a direct
error total, so the implementation must use source evidence only and preserve
every isolated candidate in the existing audit stream.

## Selected approach

Add a deterministic source-only binding gate around Properties/tensile claims.
It has two parts:

1. **Table-coordinate protection.** A table-derived owner/value/condition is
   accepted only when the candidate evidence contains one unique row/column
   binding, an explicit `respectively` relation, or an unambiguous owner/state
   label in the same cell span. A header with multiple owners, a detached OCR
   cell, or a value repeated in several columns is ambiguous and is isolated;
   it is never broadcast to every candidate owner.
2. **Tensile condition scope.** A condition remains attached only when it is
   literal in the candidate's own assertion and its scope is compatible with
   the owner's role/nature. Feedstock/powder preparation conditions cannot be
   copied onto a printed/test tensile result; reference or computational
   conditions cannot be attached to a current experimental result. A unique
   source-literal state may route an existing owner, but no owner is invented.

This option is preferred over prompt changes because it addresses chunk
projection and attribution errors after extraction while keeping the reviewed
semantic instructions intact. It is preferred over a global all-axis gate
because Composition currently outperforms the business GT and must not be
regressed by a broad recall tradeoff.

## Data flow and placement

The new gate is implemented in `src/knowmat/alpha25/promotion.py` and runs
after candidate quality/condition cleanup and before cross-owner duplicate
quarantine and final ordering:

1. existing quality and axis gates;
2. existing explicit condition binding and tensile state routing;
3. **new source-only table binding and tensile condition-scope gate**;
4. existing owner and cross-owner projection gates;
5. existing source-assertion deduplication and output ordering.

The gate consumes existing `AxisFact`, `InventoryAnchor`, and source Markdown.
It returns accepted facts plus `PromotionIssue` records. It does not call an
LLM/OCR/VLM provider, consult GT, mutate prompt artifacts, or add fields to
the public schema.

## Binding contract

- Source evidence is the authority; confidence and chunk order never resolve a
  tie.
- A table candidate with a single explicit owner/state and a value that occurs
  once in its row/cell may pass.
- `respectively` may pass only when the number and order of owners and values
  are equal and every candidate has exactly one value; otherwise all ambiguous
  projections remain isolated.
- A table containing multiple feedstock/test states without a unique column
  coordinate is ambiguous. The complete candidate is quarantined with
  `promotion_table_owner_condition_ambiguous_quarantined`.
- A prose result may retain a condition only if the condition is in the same
  evidence assertion and has a direct treatment/test cue. Neighboring
  paragraph conditions are not borrowed.
- Feedstock/powder cues on a tensile result are compatible only with an
  existing feedstock owner or an explicit feedstock preparation claim; they do
  not become the tensile test condition.
- Reference/computational claims and current experimental claims are distinct
  source-nature scopes. A condition crossing that boundary is removed from the
  property payload (or the complete claim is quarantined when the value itself
  is ambiguous) and audited.
- Missing conditions remain missing; the gate never invents temperature,
  strain rate, orientation, state, or test standard.

## Audit behavior

The formal `Properties` output contains only accepted, uniquely bound facts.
Each isolated or condition-cleaned candidate is written through the existing
`PromotionIssue` path, preserving the complete pre-filter fact, source
evidence, candidate owner set, condition scope, and reason code. The concise
code is therefore available in existing `issues.json`/`issues.md`; no new
public field or artifact is required.

## Tests and verification

Add focused tests for:

- unique table row/column owner binding;
- repeated value or multiple owner columns being quarantined;
- explicit `respectively` one-to-one mapping and ambiguous mapping;
- feedstock preparation not becoming a printed tensile condition;
- reference/computational versus current experimental condition conflicts;
- compatible missing condition remaining unchanged;
- audit payload completeness and deterministic output under input permutation;
- Composition and non-Properties non-interference.

Run the existing Alpha25/promotion suite first. Then rematerialize five
representative cached papers with provider recovery disabled and compare the
pilot against v89r. Only if no Composition regression and no materialization
failure are observed should the same gate be run across all 30 cached papers.
The comparison must report loose/strict precision, recall, F1, core tensile
metrics, issue-code counts, and byte-identical repeat behavior.

## Failure handling

Any parser uncertainty, missing coordinate, conflicting condition, or
unexpected candidate-local exception is a safe no-op or quarantine with the
complete audit payload. No partial rewrite is allowed, and no provider call is
introduced by this change.
