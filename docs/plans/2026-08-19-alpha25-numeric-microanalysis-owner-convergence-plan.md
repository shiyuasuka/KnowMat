# Alpha25 Numeric Microanalysis Owner Convergence Implementation Plan

## Objective

Implement the approved v23 design in two isolated layers: a deterministic,
GT-blind production recovery for numeric EDS observation locations, and a
separately testable offline evaluator projection for material owner plus
observation location.

## Task 1: Production regression fixtures

**Files:** `tests/test_alpha25_materialize.py`

1. Add a positive fixture with a numeric multi-element EDS table row, explicit
   prose ownership, and one compatible Target state.
2. Assert that the fact is routed to the existing material item, keeps
   `Point n` as its observation label, and emits one complete grouped
   `numeric_microanalysis_owner_recovered` issue.
3. Add negative fixtures for a missing table header, a non-EDS numeric table,
   a single-element row, conflicting source ownership, multiple compatible
   targets, and a fatigue specimen table.
4. Run the focused tests and confirm that the positive case initially fails
   for the expected unresolved-owner reason.

## Task 2: Production numeric-location recovery

**File:** `src/knowmat/alpha25/materialize.py`

1. Add narrow recognition helpers for numeric measured EDS table observations.
2. Parse source text into discourse spans and build conflict-aware
   location-to-sample/state candidates from explicit Point/Spot/Area/Location
   mentions.
3. Resolve each descriptor against the existing identity index and accept only
   one compatible Target owner.
4. Route the fact without creating a Point item, preserve the observation
   label, and consume any internal marker before serialization.
5. Group complete before/after/evidence payloads into
   `numeric_microanalysis_owner_recovered` issues.
6. Run focused materializer tests, existing microanalysis tests, and static
   formatting checks.

## Task 3: Offline evaluator regression fixtures

**Files:** existing independent-GT evaluator test module, or a new focused test
module under `tests/` when no suitable module exists.

1. Assert that a composition observation with outer material sample and inner
   `Point n` projects the material sample as owner and Point as observation
   location.
2. Cover Point-in-sample versus Point-in-region equivalence.
3. Assert that incompatible explicit specimen owners still conflict.
4. Assert that morphological regions are not treated as Point aliases.
5. Assert that unique deduplication retains equal values measured at distinct
   Point locations.

## Task 4: Offline evaluator semantic repair

**File:** `src/knowmat/evaluation/independent_gt_comparison.py`

1. Preserve outer item ownership and project literal microanalysis labels to
   the location dimension for composition claims.
2. Normalize location labels independently of material/sample identities.
3. Compare equivalent locations across sample/region representation without
   suppressing true specimen or morphological-region conflicts.
4. Include normalized observation location in unique-claim signatures.
5. Run focused evaluator and comparison regression tests.

## Task 5: Single-paper production pilot

1. Rematerialize the frozen-cache paper containing the highest-signal numeric
   EDS table into a new v23 pilot directory.
2. Verify the recovered Point set, element counts, selected owners, states,
   issue payloads, item count, schema, prompt/ruleset digest, and marker
   absence.
3. Compare the pilot against v22 and the adjudicated expert ledger with both
   the legacy and corrected evaluator semantics.
4. Narrow or revert any rule that promotes the source-unproven Point or affects
   unrelated facts.

## Task 6: Full regression and corpus rollout

1. Run the focused Alpha25/v11/evaluator suites, then the full repository
   suite and classify only pre-existing unrelated failures.
2. Rematerialize all 30 papers from the frozen 405-task cache without provider
   calls.
3. Verify 30/30 promotable, fatal=0, invalid cache=0, schema and envelope
   unchanged, no Point material items, no `quality_audit.json`, and no internal
   marker leakage.
4. Byte-compare all documents with v22 excluding commit provenance and explain
   every changed paper.
5. Produce three comparisons: corrected-evaluator v22 baseline,
   corrected-evaluator v23 production, and frozen legacy-evaluator v23.
6. Confirm no fairly evaluated unique loose, unique strict, composition loose,
   composition strict, or core-tensile regression.

## Task 7: Release record

1. Write a v23 final report under `reports/` with production and evaluator-only
   deltas separated.
2. Commit only the implementation plan, production/evaluator code, focused
   tests, and final report required for this version.
3. Record the final commit in regenerated Rule Metadata and verify the corpus
   once more if provenance changes materialized bytes.
