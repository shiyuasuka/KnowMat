# Alpha25 Source-Block Complete Tensile Survivor Deduplication

## Goal

Improve GLM Alpha25 loose precision and F1 by folding a redundant single
core-tensile projection into a uniquely richer member of one complete,
source-proven YS/UTS/elongation survivor bundle. The losing projection does not
need to belong to a second complete bundle.

This A1 increment is intentionally narrow. It must preserve the v46 owner and
condition gains, all Composition output, and the public `final.json` format. It
must not modify the professionally reviewed prompt, extraction schema, frozen
responses, provider behavior, OCR/VLM/LLM stages, or any public contract. GPT
expert GT and business GT remain evaluation instruments only and are never
runtime inputs.

## Confirmed residual and corrected hypothesis

The accepted v46 run has 45 unmatched system core-tensile claims. Read-only
adjudication classified 25 as duplicate-like and 20 as no-candidate. The first
B1 prototype required both the loser and survivor to be complete bundles. A
15-paper frozen-cache pilot produced zero output changes because real residuals
are normally single prose or citation projections beside a complete table row.

A source-block scan found six pre-exact candidates. One is already handled by
the existing exact pass. The expected net A1 scope is therefore three facts:
one PBF-EB UTS, one PBF-EB elongation, and one HA1100 yield-strength projection.
These paper names and values are regression sentinels, not production selectors.

## Considered approaches

1. **Complete survivor plus member-level loser (selected).** Build only a
   complete survivor bundle from one Markdown table record or source assertion
   block, then compare each remaining single fact with its corresponding
   survivor member. This matches the observed residual shape while keeping a
   strong three-property identity witness.
2. **Two complete bundles.** This was implemented as a prototype but had no
   recall on the real pilot and is replaced by A1.
3. **Pairwise same-owner numeric deduplication.** This would remove more rows but
   lacks the complete-result witness needed to distinguish repeated reporting
   from independent tests and is rejected.

## Architecture and placement

Add one isolated internal pass in `alpha25.materialize` after existing
cross-owner dominance and before exact same-owner alias folding:

1. Run existing quality gates, owner/state recovery, unresolved reconciliation,
   precision reconciliation, and cross-owner dominance unchanged.
2. Partition the OCR Markdown into deterministic source blocks, including whole
   Markdown tables and prose paragraphs.
3. Build complete same-owner survivor bundles from one block.
4. Compare eligible single facts with the corresponding member of every
   compatible survivor bundle.
5. Merge only a loser with one unique maximal survivor member and emit one full
   audit record per removed fact.
6. Continue through existing exact deduplication and materialization.

The pass consumes only the current `AxisFact` sequence, identity index, and
already available `source_text`. It performs no network calls and introduces no
prompt, cache, schema, model, provider, or document dependency.

## Complete survivor construction

A survivor candidate must satisfy all of the following:

- exactly one eligible numeric yield-strength fact, one numeric ultimate-
  tensile-strength fact, and one numeric elongation fact are asserted by one
  local source block;
- all three facts route to the same single canonical owner;
- all three have the same Target/Reference role and the same
  Experimental/Computational nature;
- the block is either one complete Markdown table record (header plus the
  uniquely selected owner/value row) or one prose paragraph/assertion block;
- each member's semantic and full numeric literal occur in that block;
- explicit temperature, orientation, strain/loading rate, test standard,
  specimen state, and other condition values are mutually compatible; and
- the elongation member has one stable subtype.

Members may carry different copied `source_evidence` strings. Shared evidence
text or shared `evidence_unit_id` is not required when `source_text` proves that
all three occur in the same block. The implementation must never synthesize a
bundle across paragraphs, table rows, specimens, temperatures, orientations, or
owners. A block with more than one eligible candidate for any required semantic
is ambiguous and ineligible.

## Member-level loser eligibility

The loser may be a single YS, UTS, or elongation fact. It need not have sibling
YS/UTS/elongation rows. It may be removed only when:

- it and the bundle route to exactly the same canonical owner;
- it has the same Target/Reference role and Experimental/Computational nature;
- it maps to exactly one member with the same tensile semantic and canonical
  unit;
- its explicit condition is compatible with the survivor member and bundle;
  one-sided missing conditions are rejected unless the loser and survivor are
  directly linked by the same source assertion block;
- elongation subtypes are identical; two unspecified subtypes may match, but
  unspecified never matches explicit uniform, total, fracture, or
  reduction-of-area semantics;
- values are exact, literal-rounding compatible, or the loser is explicitly
  approximate and lies inside the literal rounding envelope supported by the
  complete bundle; and
- the survivor is no less informative and is strictly richer by adding central
  precision, compatible uncertainty, uncertainty precision, or removing an
  approximation marker.

Ranges, inequalities, thresholds, relative comparisons, requirements,
qualitative descriptions, ratios, deltas, and non-result statements are never
eligible. If both sides contain uncertainty, normalized intervals must overlap;
a survivor may add compatible uncertainty but may not discard or contradict it.

## Uniqueness and deterministic selection

Candidate comparison is performed per losing fact. A fact is removed only when
all qualifying relations resolve to one unique survivor member in one unique
complete bundle. Multiple table rows, multiple compatible bundles, tied maxima,
crossed precision, or competing conditions produce a safe no-op.

Several identical loser projections may independently merge into the same
survivor member. Existing exact deduplication may first collapse identical
losers; this does not weaken the A1 proof. Candidate construction, relation
selection, evidence union, audit ordering, and output ordering must be stable
under input-order permutations. Confidence, data source labels, output order,
paper identity, and GT membership cannot establish or break scientific ties.

## Merge and audit behavior

For every accepted single-fact relation, the formal Properties output keeps the
complete survivor bundle and removes only the matched loser. The corresponding
survivor member receives the loser's distinct evidence and compatible envelope
metadata. No owner, value, unit, condition, subtype, uncertainty, or method is
invented or broadened.

One `tensile_same_owner_bundle_member_duplicate_merged` issue is written per
removed fact. Its structured record contains:

- canonical owner, role/nature, bundle condition values and elongation subtype;
- the complete removed fact;
- the complete survivor bundle before and after the member merge;
- the selected member's semantic, normalized value/unit/uncertainty relation;
- the source block and its binding kind;
- uniqueness, ambiguity, and all protection-gate decisions; and
- the deterministic survivor and loser keys.

`issues.md` receives the same short code and concise message through the current
reporting path. No `quality_audit.json` is introduced and no field is added to
`final.json`.

## Mandatory protections

A1 must preserve:

- distinct canonical owners and all X/Y/Z orientation siblings, including the
  paper_007 representation that previously lost eight strict matches;
- distinct specimen states, heat treatments, delay times, CL/PL and WA/GA;
- all elevated-temperature series, including paper_001;
- uniform, total, fracture, and reduction-of-area elongation as different
  semantics;
- thresholds, ranges, relative, qualitative, and no-candidate facts, including
  the protected 1280 C elongation result;
- every non-tensile axis and all Composition output.

Paper identifiers and example values are test and manual-review sentinels only.
They must not appear in production selectors or special cases.

## Failure behavior

Incomplete survivor bundles, block-location failure, parsing failure, ambiguous
owners, ambiguous table rows, incompatible or missing conditions, conflicting
uncertainties, non-unique survivor selection, or any candidate-local exception
leaves the original facts unchanged. A failed relation never partially changes
the survivor. Existing document-level materialization and issue handling remain
authoritative.

## Verification

Focused tests must cover:

- a complete table-row survivor absorbing one rounded prose UTS or elongation;
- a complete prose-block survivor absorbing one single projection;
- different evidence strings for the three survivor members;
- member-level exact, rounding, compatible uncertainty, and approximation cases;
- source-block and table-row construction without synthetic cross-block joins;
- multiple survivors, owner/state/orientation, role/nature, condition and
  elongation-subtype conflicts;
- thresholds, ranges, relative and qualitative facts remaining unchanged;
- complete per-fact audit payload, evidence union, and input determinism; and
- non-tensile and Composition non-interference.

After focused regression, run the diagnosed 15-paper frozen-cache pilot and
manually inspect every accepted relation against OCR Markdown. Only then run two
complete 30-paper rematerializations from all 405 frozen task responses and
compare with both sealed GPT expert GT and business GT.

## Baseline and acceptance gates

Official v46 GPT-expert unique-claim baseline:

- global loose: 1,578 / 6,272 / 3,093, F1 0.336999;
- global strict: 792 / 6,272 / 3,093, F1 0.169140;
- core tensile loose: 166 / 211 / 213, F1 0.783019; and
- core tensile strict: 126 / 211 / 213, F1 0.594340.

A1 is accepted only when all of the following hold:

- 30/30 papers and 405/405 frozen task responses materialize successfully;
- zero OCR, VLM, LLM, or other provider calls;
- prompt, skill, schema, ruleset, and frozen-cache digests remain unchanged;
- `final.json` structure is unchanged;
- Composition loose/strict counts and metrics are unchanged;
- global and core-tensile loose/strict matched counts and recall do not decline;
- global and core-tensile loose precision and F1 strictly improve;
- global and core-tensile strict precision and F1 do not decline;
- non-Properties output is identical to v46 after automatic metadata exclusion;
- every removal has a complete, source-verified per-fact audit;
- every protection sentinel remains present with its v46 owner and semantics;
- two full replays produce byte-identical `final.json` files; and
- each full replay is no slower than 331.51 seconds, 110% of v46's 301.37
  seconds, with source blocks parsed once per document rather than per pair.

Any gate failure narrows or reverts only A1. Neither GT, residual counts, paper
IDs, model names, provider names, nor example values may influence runtime logic.

## Follow-up boundary

Only after A1 passes every gate may the residual queue be remeasured. Any
state-lineage, cross-owner, or unsupported-claim policy requires a separate
design and approval.
