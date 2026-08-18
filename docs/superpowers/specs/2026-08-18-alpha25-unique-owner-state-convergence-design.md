# Alpha25 Unique-Evidence Owner and State Convergence

## Goal

Reduce GLM-5.2 Alpha25 facts assigned to a generic material, base sample, or wrong
state when the fact's own copied evidence uniquely identifies a more specific
source-backed inventory item. This is a deterministic materialization repair over the
frozen extraction cache; it does not change OCR, invoke a model, alter the reviewed
Alpha25 prompt, or change the `final.json` envelope.

The v9 baseline is the regression reference. It has 6,445 unique claims, 30/30
promotable papers, zero fatal validations, unique loose F1 `0.220126`, unique strict
F1 `0.090147`, core-tensile loose F1 `0.451237`, core-tensile strict F1 `0.232897`,
and 550 wrong-owner adjudication tags.

## Considered approaches

1. **Prompt changes or another extraction pass.** Rejected because the professional
   prompt is frozen, model output would be stochastic, and the observed facts already
   carry useful local evidence.
2. **Fuzzy aliases or GT-derived owner maps.** Rejected because similarities and
   expected labels do not prove scientific ownership and would overfit this corpus.
3. **Unique local-evidence reconciliation (selected).** Narrow an existing owner only
   when observation-local labels, copied table rows, or explicit state/source
   qualifiers resolve to exactly one inventory item in the same material family.

## Design

### Evidence precedence

Fact routing uses the following evidence from most to least specific:

1. an observation-internal `sample_id` or explicit fact owner;
2. an exact source label present in the fact's own evidence rows;
3. an explicit state/source qualifier in the same observation or copied table row;
4. the outer fact `sample_id_raw`; and
5. a unique evidence-derived inventory label.

A narrower result may replace a base-family owner only when it belongs to that same
family. Evidence mentioning a comparison material cannot move the fact to that other
family. Multi-candidate results remain unresolved or keep their existing owner; they
are never broadcast and are never resolved by similarity.

### Generic qualifier handling

The reconciliation layer may interpret only generic source semantics that are already
explicit in Alpha25 facts and inventory anchors:

- material states with explicit category and qualifiers, such as `aged 0.5 h`,
  `aged 2 h`, `annealed 8 h`, or `fully heat treated`;
- feedstock qualifiers, such as `powder` or `as-received powder`; and
- composition-source qualifiers, such as `nominal`, `measured`, `provided`,
  `manufacturer analysis`, and `EDS analysis`; and
- a source-named manufacturing qualifier, but only when the base anchor uses
  explicit process grammar such as `deposited by X`, `X process`, or
  `X-fabricated`, exactly one longer inventory identity contains that qualifier,
  and both identities agree on Target/Reference role.

These tokens are not material-specific aliases. A qualifier is applied only when the
current fact owner family plus the qualifier identifies exactly one indexed target.
Material classes such as `HEA` or `alloy` never qualify as manufacturing evidence.
Likewise, explicit Target/Reference disagreement blocks residual-label merging even
when the remaining text matches another source sample.

Measured/nominal table suffixes such as `(M)` and `(N)` remain composition-source
annotations. Repetition frequency cannot make one of those columns replace the
source-backed base material display label. Numeric sample states such as `120 s
Delay` are retained only when the inventory repeats the same value in `state_raw`
and supplies a plausible parent material; a bare table header is still rejected.

### Auditing

Every successful reassignment records `fact_owner_state_reconciled` in the existing
`issues.json` and `issues.md`. Records are grouped by `(before_owner, after_owner,
rule)` so a dense table does not create one review issue per cell. Each grouped issue
still contains the complete ordered facts and per-fact evidence. An eligible but
multi-target decision records `ambiguous_fact_owner_state` and preserves the original
routing behavior. No separate audit file is added.

### Scope safeguards

- No paper title, material name, expected value, GT label, provider, or model branch
  may enter runtime code.
- No claim is removed to improve precision, and property values remain unchanged.
- `final.json` field paths, names, nesting, and ID conventions remain unchanged.
- Runtime work is linear or near-linear in inventory labels and facts and adds no
  OCR, VLM, or LLM latency.

## Verification

Focused tests cover source-generic cases for:

- WA/GA-like base samples versus their powder/feedstock inventory items;
- T0/T5-like samples with uniquely named aging durations;
- provided/manufacturer versus measured/EDS composition observations; and
- Target/Reference role conflicts, explicit process-qualified aliases, and material
  class suffixes that must not be interpreted as processes; and
- ambiguous siblings that must not be guessed, broadcast, or silently moved.

First rematerialize the five highest-signal papers (`paper_012`, `paper_019`,
`paper_020`, `paper_023`, and `paper_029`) from frozen task responses and compare them
to v9. Then rematerialize all 30 papers and run the same expert-GT evaluation.

Acceptance requires:

- 30/30 promotable, zero fatal validations, and zero schema-envelope mismatches;
- at least 6,445 unique claims, with any increase explained by restoring distinct
  source states rather than duplicating one claim, and no loose-recall loss caused by
  deletion;
- no decrease in aggregate unique strict or core-tensile strict F1;
- a material reduction in wrong-owner tags; and
- no unexplained paper-level regression. Any rule that fails these gates is reverted
  or narrowed before release.
