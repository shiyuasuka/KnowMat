# Alpha25 Tensile, Owner, and Precision Convergence Implementation Plan

**Design:** `docs/superpowers/specs/2026-08-19-alpha25-tensile-owner-precision-convergence-design.md`

**Goal:** Improve global precision and core-tensile quality while preserving
Composition, prompt identity, request volume, auditability, and the public v11 schema.

## Task 1: Add tensile semantic classification and quarantine

**Files:**

- Modify: `src/knowmat/alpha25/claim_quality.py`
- Modify: `tests/test_alpha25_claim_quality.py`

1. Add failing tests for qualitative UTS/YS/elongation values, textual absolute
   numbers, quantified relations, existing numeric forms, and complete audit payloads.
2. Add a canonical core-tensile family predicate and deterministic value classifier.
3. Quarantine only purely qualitative core-tensile facts under
   `qualitative_tensile_quarantined`.
4. Reclassify quantified relations as relative properties without changing absolute
   numeric results.
5. Run:

   ```bash
   ./venv/bin/pytest -q tests/test_alpha25_claim_quality.py
   ```

## Task 2: Separate owner state from test conditions

**Files:**

- Modify: `src/knowmat/alpha25/materialize.py`
- Modify: `src/knowmat/alpha25/property_context.py`
- Modify: `tests/test_alpha25_materialize.py`

1. Add failing tests proving test temperature, rate, orientation, specimen geometry,
   and fatigue protocol cannot select a material state.
2. Remove test-only fields from owner/state routing inputs.
3. Extend condition recovery with selected-owner context and incompatible-protocol
   guards while preserving existing conditions and Reference isolation.
4. Add audit assertions for recovered and rejected condition decisions.
5. Run:

   ```bash
   ./venv/bin/pytest -q tests/test_alpha25_materialize.py -k 'condition or context or owner_state'
   ```

## Task 3: Recover source-proven numeric tensile owners

**Files:**

- Modify: `src/knowmat/alpha25/materialize.py`
- Modify: `tests/test_alpha25_materialize.py`

1. Add generic fixtures for exact alias, material/state table row, sibling-bundle
   consensus, and unique current-study lineage recovery.
2. Add negative fixtures for multiple owners, Target/Reference conflict, standards,
   cited references, state conflict, and quasi-static tensile followed by fatigue.
3. Implement a two-pass route index and conservative recovery decision record.
4. Emit grouped `numeric_tensile_owner_recovered` issues with complete before/after
   facts and decision evidence.
5. Run focused owner tests, then the complete materializer suite.

## Task 4: Add paper-level evidence-dominance deduplication

**Files:**

- Modify: `src/knowmat/alpha25/claim_quality.py`
- Modify: `src/knowmat/alpha25/materialize.py`
- Modify: `tests/test_alpha25_claim_quality.py`
- Modify: `tests/test_alpha25_materialize.py`

1. Add tests for same-lineage generic/state projections, exact evidence dominance,
   evidence union, and complete removal audits.
2. Add preservation tests for conjunction/plural multi-owner assertions, different
   states, conditions, origins, roles, regions, orientations, locations, and unrelated
   equal-valued owners.
3. Implement a paper-level fingerprint and dominance decision before per-item
   projection. Keep non-property axes on exact payload equivalence.
4. Emit `cross_item_duplicate_merged` with survivor and removed facts.
5. Run claim-quality and materializer suites.

## Task 5: Verify compatibility and production safety

**Files:**

- Modify tests only if a missing invariant needs coverage.

Run:

```bash
./venv/bin/pytest -q \
  tests/test_alpha25_claim_quality.py \
  tests/test_alpha25_materialize.py \
  tests/test_alpha25_normalize.py \
  tests/test_alpha25_production_safety.py \
  tests/test_prompt_templates.py \
  tests/test_v11_reporting.py
```

Verify no runtime GT import, prompt change, provider/model branch, internal-field leak,
new audit file, or schema-envelope change.

## Task 6: Run cache-only pilots

**Inputs:**

- Frozen task root: `data/output-alpha25-prompt-v5-final30-20260818`
- v23 baseline: `data/output-alpha25-expert-convergence-v23-numeric-microanalysis-final-20260819`

Rematerialize the four highest-signal residual shapes into a new versioned pilot root.
Inspect every qualitative quarantine, numeric tensile recovery, condition decision,
and cross-item merge. Narrow any rule that lacks literal evidence or changes an
explicit multi-owner assertion.

## Task 7: Run the 30-paper deterministic regression

Rematerialize all 405 cached task responses into a new versioned output root using
`scripts/rematerialize_alpha25_tasks.py`. Confirm 30/30 promotable, zero failures,
zero invalid caches, unchanged schema/ruleset/prompt identity, and no provider calls.

Run the corrected independent-GT comparison into versioned JSON, Markdown, CSV, and
claim-work artifacts. Evaluate every acceptance gate from the design rather than only
aggregate F1.

## Task 8: Produce the three-way professional report

Compare:

1. business GT against the adjudicated GPT-5.6-sol expert ledger;
2. corrected GLM v23 against the expert ledger;
3. the new GLM corpus against the expert ledger; and
4. v23 against the new corpus for attributable deltas.

Report overall and per-axis raw/unique loose/strict precision, recall, F1; core
tensile; claim counts; owner/condition/duplicate/value/unit/origin errors; paper-level
regressions; complete provenance; and a professional conclusion. If any production
gate fails, keep the goal active and continue narrowing the responsible rule.
