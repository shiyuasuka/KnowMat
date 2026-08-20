# Alpha25 Same-Owner Complete Tensile Bundle Deduplication

## Goal

Improve GLM Alpha25 loose precision and F1 by folding redundant cross-chunk
representations of one complete tensile result into one source-preserving record.
This B1 increment is deliberately narrower than general property deduplication:
it may act only when two complete YS/UTS/elongation bundles route to the same
unique canonical owner and the source proves that all three values represent the
same scientific observation.

The change must preserve the v46 gains in strict owner/condition attribution and
Composition. It must not change the professionally reviewed prompt, extraction
schema, frozen responses, provider behavior, or public `final.json` format. The
GPT expert ledger and business GT remain evaluation instruments only; runtime
logic is paper-, title-, GT-, provider-, model-, material-, and corpus-agnostic.

## Confirmed residual and scope

The accepted v46 run has 45 unmatched system core-tensile claims. Read-only
adjudication classifies 25 as duplicate-like and 20 as no-candidate. The
duplicate-like queue contains 11 elongation, 7 yield-strength, and 7
ultimate-tensile-strength projections. Several are rounded prose projections
beside more precise or uncertainty-bearing records, but evaluator owner scores
show that only a small subset is unambiguously same-owner.

B1 therefore targets only the high-confidence same-owner subset. It does not
remove an isolated unmatched fact, a source-supported fact omitted by either GT,
or any claim merely because its numeric value is close to another claim. The 20
no-candidate records are explicitly outside this design.

## Considered approaches

1. **Same-owner complete-bundle dominance (selected).** Require two locally
   coherent three-property bundles, one identical canonical owner, compatible
   scientific context, and three element-wise exact/rounding relations. This has
   the smallest expected recall risk and directly tests whether safe duplicate
   reduction can improve loose precision.
2. **Proven state-lineage bundle dominance.** Allow a generic/base owner bundle
   to fold into one uniquely proven state descendant. This may cover more
   residuals but reopens owner-representation risk and is deferred to a separate
   B2 design after B1 passes.
3. **Global unsupported-claim isolation.** Remove unmatched claims without a GT
   candidate. This could improve the displayed score most, but it would discard
   source-supported facts that the expert ledger may omit and is rejected.

## Architecture and placement

Add one isolated internal pass in `alpha25.materialize` after existing cross-owner
dominance and before exact same-owner alias folding:

1. Run existing quality gates and owner/state recovery.
2. Run existing unresolved, precision, and cross-owner reconciliation unchanged.
3. Build complete same-owner tensile bundle candidates from the remaining fact
   inventory.
4. Select only unique source-proven dominance relations and merge the losing
   bundle into the surviving bundle.
5. Run existing exact same-owner deduplication and downstream condition recovery.
6. Write the unchanged public document plus full records in existing
   `issues.json/.md`.

This placement preserves all three members long enough for the existing
cross-owner bundle logic to finish. The B1 pass consumes and returns internal
`AxisFact` values and `MaterializeIssue` records only. It introduces no prompt,
cache, schema, network, or public document dependency.

## Complete bundle construction

A bundle candidate must satisfy every condition below:

- exactly one numeric yield-strength fact, one numeric ultimate-tensile-strength
  fact, and one numeric elongation fact are present;
- all three facts route through the existing identity index to exactly one
  canonical owner, and that canonical owner is identical across the bundle;
- all three have the same Target/Reference role and the same
  Experimental/Computational nature;
- the members are locally bound by one evidence unit, one complete table row, or
  one source assertion block that explicitly presents them as a set;
- temperature, orientation, strain/loading rate, standard, specimen state, and
  other explicit conditions do not conflict within the bundle; and
- the elongation subtype is identical across the two compared bundles. Both
  unspecified subtypes may match, but an unspecified subtype does not dominate
  or get dominated by explicit uniform, total, fracture, or reduction-of-area
  semantics.

The implementation must not assemble a bundle by taking the nearest YS, UTS, and
elongation from unrelated paragraphs, table rows, specimens, temperatures, or
orientations. If one local evidence unit contains more than one candidate for a
required semantic, the bundle is ambiguous and ineligible.

## Pair eligibility and observation identity

Two complete bundles may be compared only when they have the same unique routed
canonical owner. Base/state family membership, alias similarity, or a shared
material name is not sufficient. In particular, a base owner and its state
descendant, and X/Y/Z orientation siblings, are different owners for B1.

The bundles must also agree on source role, source nature, elongation subtype,
and every explicit condition. A missing condition may be compatible only when
the two bundle evidence units are directly linked to the same source assertion
or complete table record and no competing test condition exists for that owner.
Otherwise missing-versus-explicit context is ambiguous and remains unchanged.

For each of YS, UTS, and elongation, the canonical unit must agree and exactly
one of these value relations must hold:

- equal central value and equal uncertainty after literal unit conversion; or
- the richer central value has more reported decimal precision and rounds
  exactly to the coarser value at the coarser literal precision; or
- the coarser value is explicitly approximate and the richer value or
  uncertainty-bearing value falls inside its literal rounding envelope.

Central-value precision and uncertainty precision are computed separately. A
record that adds uncertainty does not make an unchanged integer central value
artificially more precise. If both records report uncertainty, their normalized
intervals must overlap; a winner may add uncertainty but may not discard or
contradict an existing uncertainty.

Approximation wording is eligible only inside an otherwise complete,
element-wise matching bundle. Ranges, inequalities, thresholds, relative
comparisons, requirements, qualitative descriptions, and derived ratios or
deltas are never eligible.

## Dominance and deterministic selection

The survivor must be at least as informative for all three properties and
strictly more informative for at least one. More informative means source-literal
higher central precision, added compatible uncertainty, or an otherwise equal
fact bound to a uniquely complete table row. `data_source=table`, confidence,
evidence length, or output order alone never establishes scientific dominance.

The pass builds a dominance graph per canonical owner and compatible condition
key. A losing bundle is removed only when it has exactly one unique maximal
survivor and the three property mappings are one-to-one. Crossed dominance, tied
maxima, competing complete rows, non-unique member mapping, or a transitive path
through an already losing bundle produces a safe no-op.

One maximal survivor may absorb multiple coarser bundles only when each relation
independently passes the full contract. Candidate construction, ranking, evidence
union, audit ordering, and output ordering must be stable under input-order
permutations. Provider confidence may be preserved or maximized after scientific
selection, but it cannot break a tie.

## Merge and audit behavior

For one accepted bundle relation, the formal Properties output keeps exactly the
surviving YS, UTS, and elongation facts. Each survivor member receives the
distinct source evidence and compatible envelope metadata from its corresponding
removed member. No value, owner, unit, condition, subtype, uncertainty, or method
is invented or broadened.

One `tensile_same_owner_bundle_duplicate_merged` issue records the atomic
three-member decision in existing `issues.json`; `issues.md` shows the same short
code and concise summary. The structured audit contains:

- canonical owner, role, nature, condition key, and elongation subtype;
- the complete removed bundle;
- the complete survivor bundle before and after evidence merge;
- all three normalized semantic/value/unit/uncertainty relations;
- the source-local bundle binding for both sides;
- dominance, uniqueness, ambiguity, and protection-gate decisions; and
- the deterministic survivor-selection key.

The merge is atomic. If any one member cannot be proven, none of the three is
removed. No `quality_audit.json` is created and no audit-only field is added to
`final.json`.

## Mandatory protections

B1 must preserve:

- explicit distinct owners and all X/Y/Z orientation siblings, including the
  paper_007 representation that previously lost eight strict matches;
- all elevated-temperature series such as the six paper_001 UTS values;
- thresholds and ranges such as `<700`, `<450`, `>1 GPa`, and `~10%` when they
  are not one member of a proven complete duplicate bundle;
- CL/PL, WA/GA, heat-treatment, delay-time, and other explicit sample/state
  distinctions;
- uniform, total, and fracture elongation as different scientific semantics;
- source-supported no-candidate facts, including the protected 1280 C
  elongation result; and
- every non-tensile axis and all Composition output.

Paper identifiers and example values above are regression sentinels only. They
must not appear in production selectors or special cases.

## Failure handling

Incomplete bundles, source-location failure, parsing failure, ambiguous owners,
ambiguous table rows, incompatible conditions, conflicting uncertainties,
non-unique dominance, or any candidate-local exception leaves the original facts
unchanged. The pass never partially merges a bundle. Existing document-level
materialization and issue handling remain authoritative.

## Verification

Focused tests cover:

- same-owner rounded prose versus one complete uncertainty-bearing bundle;
- all three semantic members matching element-wise before an atomic merge;
- one mismatched member preventing the entire merge;
- exact values with one bundle adding compatible uncertainty;
- approximate central values inside and outside literal rounding envelopes;
- overlapping and conflicting uncertainty intervals;
- locally coherent evidence units versus synthetic cross-paragraph bundles;
- exact condition equality, source-proven missing context, and condition
  ambiguity/conflict;
- Target/Reference and Experimental/Computational mismatches;
- elongation subtype equality and all cross-subtype negatives;
- distinct state owners, X/Y/Z siblings, thresholds, ranges, relative and
  qualitative facts remaining unchanged;
- multiple maxima, crossed dominance, competing table rows, and transitive
  candidates remaining unchanged;
- input permutation determinism, complete evidence union, atomic audit payload,
  and non-tensile/Composition non-interference.

Run focused tests first, then a frozen-cache pilot over the diagnosed candidate
and protection papers, followed by two complete 30-paper rematerializations from
all 405 cached task responses. Compare the accepted candidate with v46 against
both the sealed GPT-expert ledger and business GT. Manually review every accepted
bundle merge against its OCR source evidence.

## Baseline and acceptance gates

The official v46 GPT-expert unique-claim baseline is:

- global loose: 1,578 / 6,272 / 3,093 matched/system/expert, F1 0.336999;
- global strict: 792 / 6,272 / 3,093, F1 0.169140;
- core tensile loose: 166 / 211 / 213, F1 0.783019; and
- core tensile strict: 126 / 211 / 213, F1 0.594340.

B1 is accepted only when all of the following hold:

- 30/30 papers and 405/405 frozen task responses materialize successfully;
- zero OCR, VLM, LLM, or other provider calls;
- prompt, skill, schema, ruleset, and frozen-cache digests remain unchanged;
- `final.json` schema and item layout remain unchanged;
- Composition loose/strict matched, system count, precision, recall, and F1 are
  byte-for-byte or numerically unchanged;
- global and core-tensile loose/strict matched counts and recall do not decline;
- global and core-tensile loose precision and F1 strictly improve;
- global and core-tensile strict precision and F1 do not decline;
- non-Properties axes are identical to v46 after excluding automatic run
  metadata;
- every removed fact belongs to one manually verified, fully audited atomic
  three-property duplicate relation;
- all mandatory-protection sentinels remain present with their v46 owner and
  scientific semantics;
- two full rematerializations produce byte-identical `final.json` files; and
- full frozen-cache runtime is no more than 110% of v46's measured 301.37-second
  run on the same host and workload, with no new per-fact full-document scan.

Any gate failure narrows or reverts B1 rather than weakening its evidence or
owner protections. Residual counts, paper IDs, example values, and either GT are
never runtime inputs.

## Follow-up boundary

Only after B1 passes all gates may the residual queue be remeasured for B2. B2
would require a separate written design and approval before considering a
generic/base bundle and a uniquely proven state-lineage bundle. Global
unsupported isolation remains out of scope.
