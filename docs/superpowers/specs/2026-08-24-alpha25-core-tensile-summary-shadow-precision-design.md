# Alpha25 Core-Tensile Summary Shadow Precision

## Status

Approved by the user on 2026-08-24 as the next precision-first increment after
the v199 threshold-dominance baseline and the corrected canonical value/unit
evaluation.

## Goal

Improve GLM-5.2 Alpha25 core-tensile precision without reducing matched count
or recall by removing two narrowly proven kinds of over-projection from formal
Properties:

1. a generic prose summary that merely repeats one uniquely identified,
   richer specimen/table result from the same material lineage; and
2. a numeric Pareto/group extremum that is a true cohort-level comparison but
   has no uniquely identifiable specimen owner.

Every removed record remains fully traceable in `quality_audit.json` and is
represented by a concise issue code in `issues.json` and `issues.md`.
`final.json` keeps its existing shape.

The professionally reviewed prompt, extraction schema, model/provider
configuration, OCR/VLM/LLM stages, frozen responses, and evaluator are outside
this increment. Runtime decisions must not depend on GPT expert GT, business
GT, paper title, material name, model name, provider name, or fixture values.

## Confirmed Residual

The corrected v199 30-paper evaluation contains 11 loose unmatched system
core-tensile facts. Four records in one active-learning paper are the clearest
source-proven precision residuals:

- generic headline values `1190 MPa` and `16.5%` repeat the more specific
  specimen results `3-2: 1190 +/- 12.4 MPa` and `3-2: 16.5 +/- 1.3%`; and
- `14%` as the highest tensile elongation among alloys near one UTS target and
  `945 MPa` as the highest UTS among alloys near one elongation target are
  Pareto/frontier summaries without a unique specimen coordinate.

These literals and the paper identity are regression sentinels only. They must
never appear in production selectors.

The other unmatched core-tensile facts remain formal output unless separately
proven redundant or ownerless. Many are source-supported facts absent from the
expert ledger, so unmatched status alone is never a quarantine reason.

## Considered Approaches

1. **Two evidence-bound narrow gates (selected).** Treat exact summary shadows
   and ownerless group extrema independently, with positive source grammar,
   owner, value, unit, condition, uniqueness, and audit requirements.
2. **General same-value core-tensile deduplication.** Rejected because equal
   values can be independent tests, distinct specimens, rounded observations,
   or repeated results under different conditions.
3. **Remove all generic-owner or GPT-unmatched tensile facts.** Rejected
   because it uses evaluation membership as a runtime selector and would erase
   scientifically valid group averages, thresholds, and uniquely reported
   results.

## Architecture and Placement

Add two deterministic, candidate-local passes to `alpha25.promotion` after the
existing owner/source-coordinate reconciliation and source-assertion
deduplication, and before tensile conflict quarantine:

1. `_quarantine_generic_tensile_summary_shadows` compares eligible generic
   numeric results with unique richer specimen/table survivors.
2. `_quarantine_ownerless_tensile_group_extrema` isolates eligible cohort-level
   Pareto/frontier extrema that cannot be assigned to one specimen.

Both passes consume only current inventory anchors, promoted facts, and
available source evidence/source text. They return accepted facts plus normal
`PromotionIssue` records. They do not mutate prompts, call a model, invent an
owner, infer a missing condition, or add a public field.

The summary-shadow pass runs first. A record removed as a shadow cannot also
produce an extremum issue. Candidate ordering and issue ordering are stable
under input-order permutations.

## Gate A: Generic Prose Summary Shadow

A generic core-tensile fact may be merged into one survivor only when every
condition below holds:

1. Both facts are numeric yield strength, ultimate tensile strength, or
   elongation results with the same tensile family/subtype and compatible
   canonical unit.
2. The losing fact has a generic, collective, or unresolved owner. Its bounded
   prose evidence does not name a distinct specimen, table row, orientation,
   state, or condition coordinate.
3. The survivor resolves to exactly one concrete specimen/table owner within
   the same material lineage and the same Target/Reference and
   Experimental/Computational role/nature.
4. Their explicit test conditions are identical. One-sided missing conditions
   are allowed only when the generic summary is unqualified and the source
   context exposes exactly one compatible concrete survivor; any competing
   temperature, orientation, state, strain rate, standard, or treatment makes
   the relation a no-op.
5. Their normalized central values are equal after compatible unit conversion.
   A loose tolerance, nearby value, range overlap, or evaluator match is
   insufficient.
6. The survivor is strictly more informative because it has a concrete
   specimen/table coordinate and at least one of: explicit uncertainty, higher
   literal precision, or a uniquely bound table cell/row.
7. The summary evidence uses headline/result grammar and does not assert an
   independent average, replicate, distribution, threshold, requirement,
   record, or second experiment.
8. Exactly one survivor satisfies all gates. Multiple specimens with the same
   value, multiple compatible states, or multiple table coordinates are a safe
   no-op.

The survivor stays byte-for-byte scientifically unchanged except for the
existing evidence-union mechanism. The removed summary is emitted as
`core_tensile_generic_summary_shadow_quarantined` with its complete original
record and the complete before/after survivor.

## Gate B: Ownerless Group/Pareto Extremum

A core-tensile fact is isolated only when every condition below holds:

1. It is a numeric YS, UTS, or elongation result from prose evidence, not a
   literal table cell, figure point, chart series, or named specimen result.
2. The bounded proposition explicitly uses extremum grammar such as
   `highest`, `maximum`, `largest`, or `best` together with collective scope
   grammar such as `among/in the alloys`, `samples`, `specimens`, `conditions`,
   or `parameter combinations`.
3. The same proposition includes a second mechanical-property constraint or
   Pareto/frontier criterion. A simple statement that one named specimen has
   the highest value is not eligible.
4. The fact owner remains generic, collective, or unresolved after existing
   owner gates, and the proposition contains no unique specimen label, table
   coordinate, sample index, orientation/state coordinate, or one-to-one owner
   binding.
5. No current anchor/fact relation proves one unique concrete owner for the
   extremum. The pass never selects the nearest value or one candidate from a
   group.

Eligible records are true cohort-level comparisons, but they are not valid
specimen-level scalar Properties. They are removed from formal Properties and
emitted as `promotion_tensile_group_extremum_quarantined` with the original
fact, bounded proposition, extremum cue, collective scope, companion-property
constraint, unresolved owner envelope, ambiguity evidence, and
`owner_invented=false`.

## Mandatory Safe No-Ops

Both passes preserve:

- any named specimen, unique table row/cell, explicit figure series, or
  resolved condition owner;
- independent averages, replicate statistics, distributions, ranges,
  inequalities, qualitative comparisons, requirements, and standalone group
  results;
- equal values reported for multiple specimens or conditions;
- facts with incompatible or ambiguous units, conditions, roles, natures,
  material lineages, or elongation subtypes;
- any candidate with parsing failure or non-unique survivor selection;
- every non-core-tensile Property and all Composition, Processing, Structure,
  and Characterization facts.

Candidate-local failure leaves all original facts unchanged. An exception must
not partially mutate a survivor or suppress a fact.

## Audit Contract

For every accepted relation, `quality_audit.json` must preserve enough data to
reverse and independently inspect the decision:

- full removed fact;
- full survivor before and after merge for Gate A, or the complete unresolved
  owner candidate envelope for Gate B;
- normalized owner, lineage, role/nature, tensile family/subtype, value, unit,
  uncertainty, and condition comparison;
- exact bounded source proposition and all original evidence;
- positive grammar cues and every uniqueness/ambiguity decision;
- deterministic candidate and survivor keys;
- `owner_invented=false`; and
- the selected issue code and reason.

The existing reporting path writes the concise code to `issues.json` and
`issues.md`. No field is added to `final.json`, and no audit record may be
discarded during packaging.

## Verification

Focused failing tests must cover:

- a generic `1190 MPa` summary merging into one `1190 +/- 12.4 MPa` concrete
  specimen survivor;
- the analogous elongation summary;
- exact central-value equality, compatible unit conversion, explicit
  uncertainty, table-coordinate richness, and evidence union;
- different owners, conditions, subtypes, role/nature, material lineages,
  non-equal values, multiple survivors, independent averages, and named
  specimen prose remaining unchanged;
- ownerless `highest X among alloys with Y` and `maximum X among parameter
  combinations satisfying Y` being isolated;
- a named specimen with the highest value, a table maximum, a simple group
  average, and extremum prose without a companion-property constraint
  remaining unchanged;
- complete issue/audit payload and stable results under input-order
  permutations; and
- non-core-tensile and Composition non-interference.

Then rematerialize only the diagnosed active-learning paper from the unchanged
frozen task cache and manually inspect every semantic change. The pilot must
remove exactly the four confirmed residuals, retain both concrete `3-2`
results, and preserve complete audit records. Any extra removal narrows the
gate before the 30-paper run.

Finally rematerialize all 30 papers from the same frozen task responses and run
the corrected canonical-pairing evaluator. No GLM, OCR, VLM, or provider call
is expected or allowed in this deterministic rematerialization.

## Baseline and Acceptance

The corrected v199 unique baseline is:

- global loose: matched `669`, system `1375`, precision `0.486545`, recall
  `0.216295`, F1 `0.299463`;
- global strict: matched `365`, system `1375`, precision `0.265455`, recall
  `0.118008`, F1 `0.163384`;
- core tensile loose: matched `76`, system `87`, precision `0.873563`, recall
  `0.356808`, F1 `0.506667`; and
- core tensile strict: matched `41`, system `87`, precision `0.471264`, recall
  `0.192488`, F1 `0.273333`.

Acceptance requires:

- 30/30 papers, all frozen tasks valid, fatal `0`, and zero external calls;
- exactly the source-proven relations selected by the pilot, with no
  unexplained semantic change;
- loose and strict matched counts and recall unchanged globally and for core
  tensile;
- global and core-tensile precision/F1 non-decreasing, with core-tensile loose
  precision strictly increasing;
- Composition metrics and formal output unchanged;
- unchanged prompt/schema/provider/cache digests and unchanged `final.json`
  shape;
- complete, reversible audit records and concise issue codes; and
- byte-identical deterministic replay.

If any matched count or recall falls, only the new relation responsible is
disabled or narrowed. The gate is never broadened to recover a score.

## Out of Scope

This increment does not change prompts, improve extraction recall, synthesize
owners, rewrite conditions, generalize non-tensile deduplication, suppress all
generic prose, alter GT/evaluator rules, or use evaluation output in runtime
selection. Remaining Structure, Processing, Composition, Characterization, and
Properties residuals require separate source-proven designs.
