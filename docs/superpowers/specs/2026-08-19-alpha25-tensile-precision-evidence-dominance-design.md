# Alpha25 Tensile Precision Evidence Dominance

## Goal

Improve GLM Alpha25 core-tensile precision by merging redundant low-information
projections into a uniquely bound, more precise source record. The change must not
modify the professionally reviewed prompt, make provider calls, change the
`final.json` schema, reduce Composition quality, or trade recall for precision.

The GPT expert ledger and business GT are evaluation instruments only. Runtime
decisions must remain paper-, title-, GT-, model-, and provider-independent.

## Problem

One scientific tensile result can be emitted more than once across chunks: prose
often contributes a rounded value or generic material owner, while a complete
table contributes the same result with uncertainty, greater numeric precision,
or a more explicit material state. Existing exact-fingerprint deduplication cannot
merge these records because their value strings or owners differ. Keeping every
projection inflates the formal `Properties` claim set and lowers precision even
though the underlying scientific observation is not new.

This design addresses only redundant numeric yield strength, ultimate tensile
strength, and elongation projections. It does not broaden extraction, infer a
missing measurement, or resolve general semantic and owner conflicts.

## Considered approaches

1. **Precision evidence dominance (selected).** Merge only when a complete source
   record deterministically dominates a rounded or less-specific projection.
   This removes a high-confidence false-positive cluster while preserving
   ambiguous and independently asserted results.
2. **Broader third-party prose owner recovery.** Resolve more residuals by
   following citation and pronoun context across sentences. This may improve
   recall but has materially higher cross-sentence attribution risk.
3. **Shared Structure/Characterization consolidation.** Merge facts attached to
   several nearby samples. This targets a larger residual class but can erase
   genuinely shared observations and is outside the tensile-specific scope.

## Placement and boundaries

Add one isolated materialization pass after table/context tensile owner recovery
and before ordinary cross-item dominance deduplication. The relevant flow is:

1. claim quality gate;
2. reference and other fact-level owner recovery;
3. numeric tensile table/context owner recovery;
4. **tensile precision evidence dominance**;
5. existing cross-item dominance and per-item deduplication;
6. property condition recovery and public document construction.

The pass accepts the existing identity index and internal `AxisFact` sequence. It
returns a new fact sequence plus `MaterializeIssue` records. It does not mutate
anchors, prompt artifacts, caches, or public schema definitions.

## Eligibility contract

A loser/survivor pair is eligible only when every requirement below is satisfied.

### Same scientific observation

- Both facts are numeric core-tensile facts: normalized yield strength, ultimate
  tensile strength, or elongation.
- Their normalized semantic, central numeric value, and canonical unit agree.
  Numeric comparison may normalize formatting but must not round one distinct
  measured value into another.
- Both have the same Target/Reference role and experimental/computational source
  nature after the earlier owner-recovery passes.
- Test temperature, strain rate, orientation, test standard, and other declared
  conditions do not conflict. Missing context is compatible; two unequal explicit
  values are not.
- Elongation subtype is the same when both are explicit. An unspecified subtype
  may pair with an explicit subtype only when no competing subtype shares the
  observation. Uniform, total, and fracture elongation never dominate one another.

### Positive dominance evidence

At least one of these independently verifiable relations must hold:

1. the survivor is bound to one complete table record and preserves uncertainty
   or numeric precision absent from the loser; or
2. the survivor is bound to exactly one more explicit state owner in the same
   material lineage, while the loser is a generic projection and the combined
   evidence uniquely names that state.

`data_source=table` alone is not positive dominance evidence. A table value with
the same information content as prose does not supersede the prose fact.
A complete table record means the fact evidence contains a compatible header and
value row with exactly one aligned owner/value binding; a detached OCR cell,
caption fragment, or provider source label is not complete table evidence.

### Uniqueness and protection gates

- The survivor owner must be unique after routing.
- Multiple table rows or owners matching the same value make the candidate
  ambiguous and therefore unchanged.
- Relative comparisons, ranges, thresholds, standard requirements, qualitative
  statements, and facts with incompatible Target/Reference roles are protected.
- A loser independently asserted for a distinct owner or condition is protected.
- A candidate is all-or-nothing: failure of any gate leaves both records intact.

## Deterministic selection

Candidates are grouped by normalized tensile semantic, central value, canonical
unit, compatible conditions, source role/nature, and material lineage. Within a
group, the pass computes evidence completeness rather than trusting confidence
alone. A survivor exists only when exactly one record satisfies the positive
dominance rules and every other eligible record is strictly less informative.

Selection and output ordering must be stable under input-order permutations. If
two records have equal evidence strength or competing precise owners, neither is
removed. Provider confidence may be preserved or maximized after selection, but
it must never break a scientific ambiguity tie.

## Merge and audit behavior

The formal `Properties` output keeps only the survivor. All distinct source
evidence from removed facts is appended to the survivor, preserving deterministic
order, and survivor confidence becomes the maximum of the merged facts.

Every removed projection emits one
`tensile_precision_duplicate_merged` record in the existing `issues.json`; the
same concise issue code appears in `issues.md`. Its audit payload records:

- the complete removed fact;
- the survivor before and after evidence merge;
- before/after owners;
- normalized semantic, value, unit, conditions, and source nature;
- the positive dominance rule and table/state binding evidence; and
- all uniqueness and protection-gate decisions needed to reproduce the result.

No `quality_audit.json` is created and no audit-only field is added to
`final.json`.

## Failure handling

Parsing failure, incomplete evidence, incompatible conditions, or non-unique
selection is a safe no-op. The pass must never manufacture a fact, owner, state,
condition, uncertainty, or unit. Unexpected candidate-local exceptions preserve
the original records and emit no partial merge. Existing materialization failure
handling remains authoritative for document-level errors.

## Verification

Focused tests cover:

- rounded prose versus uncertainty-bearing or higher-precision table records;
- same-information prose/table pairs that must remain unchanged;
- generic owner versus one uniquely named state in the same lineage;
- multiple matching table owners and multiple precise survivor candidates;
- Target/Reference and experimental/computational source conflicts;
- condition conflicts and compatible missing conditions;
- explicit and ambiguous elongation subtypes;
- relative, range, threshold, requirement, and qualitative protections;
- deterministic ordering, evidence union, confidence handling, and full audit;
- non-tensile and Composition non-interference.

Run a narrow paper pilot first and manually inspect every merge. Then run a
30-paper frozen-cache rematerialization and the same GPT expert/business GT
comparison used for v36. The frozen residual analysis predicts 31 eligible
projections across four papers, but this number is an evaluation expectation, not
a production selector.

Acceptance requires:

- 30/30 papers and 405/405 cached task responses materialize successfully;
- zero OCR, VLM, LLM, or other provider calls;
- unchanged prompt, skill, schema, and cache digests;
- Composition loose/strict matched, precision, recall, and F1 do not decline;
- global and core-tensile loose/strict matched and recall do not decline;
- global and core-tensile precision and F1 improve or remain unchanged;
- every removal has a complete existing-artifact audit trail; and
- repeated materialization produces byte-identical `final.json` files.

The current v36 core-tensile baseline is loose P/R/F1
61.80%/76.39%/68.32% and strict P/R/F1 42.32%/52.31%/46.79%. If the predicted
31 projections are the only changes, the expected core-tensile result is loose
69.92%/76.39%/73.01% and strict 47.88%/52.31%/50.00%, with matched counts
unchanged. Any acceptance-gate failure narrows or disables the rule instead of
weakening its evidence requirements.

## Out of scope and continuation

This increment does not change prompts, retry policy, chunking, API concurrency,
OCR/VLM processing, GT content, evaluator matching rules, or `final.json`. After
v37 passes all gates, the next optimization cycle will re-rank remaining residual
clusters by error count, scientific certainty, and regression risk; broader prose
reference recovery and shared non-tensile observations require separate designs.
