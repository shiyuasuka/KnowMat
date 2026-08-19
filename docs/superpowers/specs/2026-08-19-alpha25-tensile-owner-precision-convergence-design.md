# Alpha25 Tensile, Owner, and Precision Convergence

## Goal

Improve the GLM-5.2 Alpha25 production output toward both the business-provided
ground truth and the adjudicated GPT-5.6-sol expert extraction ledger. The current
Composition result already exceeds the business baseline, so this increment focuses
on global precision, material/state ownership, test-condition attribution, and core
tensile quality without changing the professionally reviewed prompt or the public
`final.json` schema.

The adjudicated GPT expert ledger remains an offline evaluation reference. Production
code must be GT-blind and model/provider-independent.

## Corrected v23 baseline

The location-aware corrected evaluator establishes the regression baseline:

| Metric | GLM v23 | Business GT |
|---|---:|---:|
| Unique loose F1 | 0.308069 | 0.411145 |
| Unique strict F1 | 0.146272 | 0.143373 |
| Core tensile loose F1 | 0.482866 | 0.712788 |
| Core tensile strict F1 | 0.258567 | 0.448637 |
| Composition loose F1 | 0.657286 | 0.592096 |
| Composition strict F1 | 0.325628 | 0.155392 |

The GLM baseline has 1,508 unique loose matches from 6,697 system claims against
3,093 expert claims. Composition must not regress while precision and tensile
attribution improve.

## Confirmed constraints

- Do not modify the Alpha25 system prompt, user prompt, compiled prompt hash, or
  professional extraction instructions.
- Preserve schema `material_extraction_v11.3.3` and the existing `final.json` field
  hierarchy exactly.
- Do not add `quality_audit.json`. Store every quarantine, migration, recovery, and
  merge in the existing `issues.json` and `issues.md` artifacts.
- Do not add OCR, VLM, or LLM requests. Development and the formal 30-paper
  regression rematerialize the 405 frozen Alpha25 task responses.
- Do not read business GT or GPT expert GT during production routing. Paper titles,
  expected values, GT sample IDs, model names, and provider-specific branches are
  forbidden in runtime rules.
- Preserve genuine source claims. Precision improvements must come from correcting
  representation, attribution, and duplication, not deleting supported quantitative
  results to match a benchmark.
- Point, Spot, Area, and Location identify observations, not material owners.
- Fatigue specimens and fatigue protocols must not be converted into static tensile
  results or donate conditions to them.

## Considered approaches

### A. Qualitative-tensile quarantine only

Remove non-numeric comparison phrases from formal tensile `Properties` and retain
them in the audit. This is low risk and improves core-tensile precision, but it does
not address unresolved numeric tensile facts or cross-item duplicates.

### B. Deterministic quarantine, owner/condition recovery, and dominance deduplication

Classify tensile semantics, resolve only source-proven numeric owners, separate owner
state from test conditions, and merge only duplicates for which one owner dominates
by explicit evidence. This is the selected approach. It is reproducible, adds no
provider calls, and directly addresses the measured failure modes.

### C. Second LLM adjudication pass

Ask another model call to decide ambiguous owner and condition cases. This can handle
some implicit prose, but increases latency, cost, and stochasticity and can introduce
new unsupported decisions. It remains out of scope for this increment.

## Architecture

### 1. Tensile semantic classifier and quarantine

Extend the deterministic property quality gate in
`src/knowmat/alpha25/claim_quality.py`. A property is in the core tensile family only
after canonical alias normalization for ultimate tensile strength, yield strength,
and elongation.

The classifier distinguishes four cases:

1. **Absolute quantitative result.** A digit, range, inequality, uncertainty, or
   unambiguous textual absolute number such as `more than one gigapascal` remains a
   formal Property.
2. **Quantified relation.** Expressions such as `twice`, `three times`, percentage
   retention, and percentage increase/decrease become explicitly relative
   properties. They cannot masquerade as absolute UTS, YS, or elongation.
3. **Purely qualitative comparison.** Values such as `lower`, `higher`, `comparable`,
   `similar`, `excellent`, `large`, `strength was lower`, `ductility was similar`, or
   anisotropy descriptions with no magnitude are excluded from formal Properties.
4. **Chart-derived numeric result.** A chart value remains eligible only under the
   existing chart grounding and curve-quality gates; its presentation as chart data
   does not make a qualitative phrase numeric.

Every excluded qualitative tensile fact produces
`qualitative_tensile_quarantined`. The issue contains the complete original fact,
owner presentation, source evidence, classification reason, and review action.
Nothing is silently discarded.

An offline v23 simulation found 50 eligible qualitative core-tensile records. Removing
them lost zero loose or strict matches and changed core-tensile loose F1 from
`0.482866` to `0.521886`, supporting this boundary.

### 2. Two-pass numeric tensile owner recovery

Implement owner recovery in `src/knowmat/alpha25/materialize.py` after the global
identity index exists and before unresolved facts are quarantined.

The first pass routes all facts that already have direct, unique evidence. The second
pass may recover an unresolved or generic-owner numeric core-tensile fact only through
the following ordered evidence rules:

1. exact inventory owner/state alias in the fact or its literal evidence;
2. a complete projected table row label containing a recognized material/sample plus
   preparation state;
3. one normalized evidence bundle in which at least two different sibling tensile
   semantics already resolve to the same single owner/state; or
4. a current-study prose block that explicitly names one material lineage and for
   which the identity graph contains exactly one compatible prepared Target state.

An evidence bundle is an exact normalized copied quote, projected table row, or set of
overlapping literal evidence strings. Similar wording in unrelated chunks is not a
bundle.

Recovery is prohibited when any of these conditions holds:

- two or more compatible owners remain;
- Target and Reference roles conflict;
- the value is a standard/specification threshold rather than a reported result;
- the source is cited literature without its own explicit Reference owner;
- the evidence belongs to fatigue, creep, compression, hardness, or another
  incompatible protocol;
- owner recovery would require borrowing a value, state, or label from another row;
  or
- an explicit state in the fact conflicts with the candidate owner state.

Successful recovery produces `numeric_tensile_owner_recovered` containing the original
fact, before/after owner, before/after material state, sibling facts or row binding,
all decision evidence, and the applied rule. Ambiguous facts remain quarantined with
their candidate owners.

### 3. Owner and condition separation

Owner resolution and test-condition resolution become two explicit phases.

Owner/state routing may consume material/sample labels and preparation states such as
`as-built`, `solution treated`, `aged`, or `sintered`. It must not consume
`test_condition_raw`, tensile specimen geometry, strain rate, test temperature,
orientation, standard, fatigue cycle count, or fatigue loading as material-state
evidence.

After one owner has been selected, `PropertyContextIndex` may fill an empty tensile
condition only when one compatible source-verbatim procedure is unique for that
owner. Existing conditions are never overwritten. Reference facts cannot inherit the
current paper's protocol. Multiple incompatible procedures, multi-owner prose without
a local discriminator, and any fatigue/static-tensile ambiguity produce review issues
without changing the Property.

The condition audit records the selected owner, candidate procedure blocks, rejected
blocks and reasons, and the final literal condition. No condition is synthesized.

### 4. Conservative cross-item dominance deduplication

Run a paper-level duplicate pass after direct and recovered owner decisions but before
the final per-item projection. The fingerprint contains:

- axis and fact type;
- canonical semantic name;
- value/range/inequality/uncertainty and unit;
- scientific condition;
- data origin and Target/Reference role;
- normalized literal evidence; and
- observation location where applicable.

For Properties, existing semantic aliases may be canonicalized because value and
condition fields are complete. Other axes require exact payload equivalence after
removing owner presentation; they are not merged merely because their labels are
similar.

One duplicate may be removed only when all of the following are true:

- every scientific fingerprint field is identical;
- owners belong to the same source-backed material lineage and role;
- evidence explicitly names exactly one more-specific sample or state owner;
- the losing generic/base owner is not independently named by that evidence;
- no state, condition, origin, region, orientation, or observation-location conflict
  exists; and
- the source does not explicitly enumerate or grammatically share the assertion across
  multiple owners.

Plural and conjunction forms are protected. For example, `EPBF and LPBF powders are
spherical` must retain one fact for each explicitly enumerated owner even when a naive
exact-name matcher misses the plural form.

State-specific owners dominate a generic/base projection only under these evidence
rules. A sample-specific owner similarly dominates a family projection. Equal values
for different materials, states, conditions, Target/Reference roles, or explicitly
listed samples remain separate.

Each merge produces `cross_item_duplicate_merged` with the full removed fact, survivor
before and after evidence union, both owner presentations, fingerprint, dominance
evidence, and rule. Confidence never decides which scientific claim survives.

A read-only v23 simulation showed why this gate must be conservative. A broad rule
removed 217 claims and lost four true matches. The evidence-dominance form removed 17
claims (nine unique claims) with zero loose or strict match loss, moving overall loose
F1 from `0.308069` to `0.308353` before any tensile or owner recovery.

### 5. Audit serialization

All new issues flow through the current `MaterializeIssue` and v11 normalization
pipeline. `issues.json` holds complete machine-readable records; `issues.md` renders a
short code, owner, reason, and evidence summary for review.

The public `final.json` contains only accepted material facts and retains its current
schema. Internal routing markers and decision records must never leak into it.

## Data flow

`frozen task responses -> literal evidence gate -> tensile semantic classifier -> global identity index -> direct owner routing -> numeric tensile owner recovery -> paper-level dominance deduplication -> owner-scoped condition recovery -> existing sanitization/normalization -> unchanged final.json + existing issues.json/.md`

Business GT and GPT expert claims enter only after the production outputs are complete.

## Error handling

- Unsupported or non-literal values remain quarantined under existing evidence codes.
- A failed owner rule records candidates and evidence and leaves the fact unresolved.
- A failed condition rule preserves an existing condition or leaves an empty condition
  unchanged.
- A failed deduplication dominance test preserves every claim.
- No eligible facts after quality gates is not silently reported as a successful empty
  material extraction.
- All deterministic passes are linear or near-linear in facts, evidence bundles, and
  indexed owners.

## Verification

### Focused tests

Add generic, paper-independent tests for:

- qualitative `lower`, `comparable`, `similar`, `excellent`, and anisotropy tensile
  facts being quarantined with complete audit payloads;
- digits, inequalities, ranges, uncertainty, textual absolute numbers, and valid chart
  numbers remaining quantitative;
- `twice`, `three times`, retention, and percent changes becoming relative rather than
  absolute core-tensile properties;
- exact owner aliases, complete material/state table rows, sibling-bundle consensus,
  and unique current-study lineage recovery;
- Target/Reference conflict, standards, cited references, multi-owner ambiguity,
  fatigue data, and incompatible state remaining unresolved;
- material-state routing excluding test temperature, rate, specimen, orientation, and
  fatigue protocol;
- owner-compatible unique condition recovery and all ambiguous/reference/fatigue
  rejection cases;
- same-owner and cross-item duplicate evidence union;
- explicit multi-sample enumeration, plural aliases, distinct state/condition/origin,
  unrelated owners, observation locations, and equal coincidental values being
  preserved;
- complete issues audit and absence of internal fields from `final.json`; and
- unchanged prompt hashes and schema paths.

### Pilot rematerialization

Run focused cache-only pilots over the known residual shapes: generic alloy/state
tensile bundles, quasi-static tensile followed by fatigue sections, sintering table
rows, and cited-reference property duplicates. Inspect every recovery and removal
record before corpus rollout.

### Frozen 30-paper regression

Rematerialize all 405 task caches with zero OCR, VLM, and LLM calls. Acceptance
requires:

- 30/30 papers promotable, zero fatal issues, and zero invalid cache files;
- schema `material_extraction_v11.3.3`, Alpha25 skill `11.0.0-alpha.25`, prompt digest,
  and `final.json` envelope unchanged;
- overall unique loose F1 greater than `0.308069` and unique strict F1 not lower than
  `0.146272`;
- core-tensile loose F1 greater than `0.482866` and core-tensile strict F1 greater than
  `0.258567`;
- Composition loose/strict F1 not lower than `0.657286 / 0.325628`;
- no lost loose or strict match attributable solely to cross-item deduplication;
- reduced system claim count and residual duplicate/qualitative-tensile queues, with
  no unexplained recall regression; and
- complete audit records for every affected fact.

If any gate fails, narrow or revert the responsible rule rather than weaken grounding
or owner safeguards.

### Three-way expert comparison

Use the corrected location-aware evaluator and the adjudicated GPT-5.6-sol expert
ledger as the factual reference. Produce a versioned JSON, Markdown report, per-paper
CSV, and residual claim work directory comparing:

1. business-provided GT versus the GPT expert ledger;
2. corrected GLM v23 versus the GPT expert ledger;
3. the new GLM result versus the GPT expert ledger; and
4. v23 versus the new GLM result for attributable deltas.

For every system and paper, report raw and unique loose/strict precision, recall, and
F1 by axis; overall micro/macro metrics; core-tensile metrics; and owner, condition,
duplicate, value, unit, origin, omission, OCR, and chart residuals. The professional
conclusion must explain who is more accurate, who has more supported facts, who has
more omissions, and which differences are factual errors rather than representation
differences.

The GPT expert ledger is evidence-validated but not represented as a meaningless
self-comparison score. Its provenance, blind seal, accepted amendments, validation
status, and limitations remain visible in the report.

## Rollout boundary

This increment ends after deterministic 30-paper regression and three-way comparison.
The previously completed live GLM probe already proves that the no-cache provider path
works. A new full 30-paper live GLM run is a separate stochastic validation and is not
required to judge these deterministic materialization changes.
