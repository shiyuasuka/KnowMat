# Alpha25 Source-Block Complete Tensile Survivor Deduplication — Implementation Plan

Design: `docs/superpowers/specs/2026-08-20-alpha25-same-owner-complete-tensile-bundle-dedup-design.md`

## Constraints and baseline

- Modify only Alpha25 internal materialization, focused tests, and validation
  artifacts.
- Do not modify prompts, schema, model/provider settings, OCR/VLM/LLM behavior,
  frozen task caches, or public `final.json` structure.
- Require one identical uniquely routed canonical owner; state-lineage and
  cross-owner extensions are outside A1.
- The survivor must be a complete YS/UTS/elongation bundle proven by one source
  block. The loser may be one corresponding fact.
- Preserve thresholds, ranges, relative/qualitative facts, elongation subtypes,
  orientation siblings, explicit conditions, no-candidate facts, non-Properties
  axes, and Composition.
- v46 baseline: 30 papers, 405 frozen caches, 301.37 seconds; GPT expert global
  loose = 1,578/6,272/3,093 and core tensile loose/strict = 166/211/213 and
  126/211/213.

## Task 1 — Correct the test contract

1. Replace the obsolete two-complete-bundle expectations with helpers for a
   source-block complete survivor and a single member-level loser.
2. Add success tests for table and prose survivor blocks whose member facts have
   different copied evidence strings.
3. Assert one removal and one complete audit per loser, with the whole survivor
   bundle retained and only its matched member enriched.
4. Add negatives for incomplete survivor, synthetic cross-block assembly,
   multiple survivor bundles, owner/state/orientation, role/nature, condition,
   subtype, threshold/range/relative/qualitative, and uncertainty conflicts.
5. Add a protection test for multiple identical narrative assertions folded
   into one evidence envelope, and preserve input-permutation determinism.

## Task 2 — Build source-block complete survivors

1. Replace the prototype evidence-string grouping with a deterministic source
   block index computed once from `source_text`.
2. Represent whole Markdown tables and prose paragraphs separately and keep a
   stable source-location key.
3. Reuse current tensile semantic, numeric-literal, canonical-unit, owner route,
   role/nature, subtype, condition, and assertion helpers.
4. Build a survivor only when one block contains exactly one eligible YS, UTS,
   and elongation for one canonical owner and compatible context.
5. Reject any ambiguous member, owner, row, condition, or synthetic cross-block
   construction as a safe no-op.

## Task 3 — Implement member-level dominance

1. Run existing exact alias folding first; protect an exact identity represented
   by multiple input assertions or multiple distinct evidence strings.
2. Compare every eligible single-assertion fact only with the corresponding
   semantic member of complete survivor bundles for the same owner.
3. Require canonical-unit equality, exact/literal-rounding/complete-bundle
   approximation compatibility, compatible uncertainty, identical role/nature,
   explicit condition compatibility, and elongation subtype equality.
4. Require the survivor member to be no less informative and strictly richer.
5. Accept only one unique maximal complete-survivor/member relation per loser;
   reject multiple bundles or competing conditions without using confidence or
   output order as a tie-breaker.
6. Merge only the selected survivor member, remove only the loser, and emit one
   `tensile_same_owner_bundle_member_duplicate_merged` audit containing the full
   removed fact and complete survivor bundle before/after.
7. Invoke the pass after cross-owner dominance and exact same-owner alias
   folding.

## Task 4 — Focused and related verification

1. Run the corrected tests first and observe failure against the obsolete
   prototype.
2. Implement the production change and run
   `pytest -o addopts='' tests/test_alpha25_materialize.py -q`.
3. Run claim-quality, runtime-property-alias, production-safety, evaluator, and
   other directly related suites.
4. Run Python compilation and `git diff --check` for touched source/test files.
5. Confirm prompt, schema, ruleset, and provider files were not changed by A1.

## Task 5 — Frozen-cache pilot and manual audit

1. Rematerialize the diagnosed 15 papers from the v46 frozen workload using
   `scripts/rematerialize_alpha25_tasks.py`.
2. Compare all changed `final.json` output with v46 while excluding automatic
   metadata.
3. Inspect every accepted member-level merge against copied OCR Markdown,
   including paper_006 PBF-EB and paper_028 HA1100 sentinels.
4. Confirm orientation, condition, subtype, threshold/range, no-candidate,
   Composition, and non-Properties protection gates.
5. Evaluate the pilot against sealed GPT expert GT and business GT; proceed only
   with no matched/recall regression.

## Task 6 — Full frozen-cache dual replay and evaluation

1. Rematerialize all 30 papers from exactly 405 cached task responses into a new
   output root, recording wall time and proving zero provider calls.
2. Evaluate global, Composition, Properties, and unique core-tensile loose and
   strict metrics against both GT sets.
3. Repeat the complete replay into a second root and prove all 30 `final.json`
   files are byte-identical.
4. Verify prompt, skill, schema, ruleset, and cache digests against v46 and the
   331.51-second runtime ceiling.
5. Write the v47 acceptance report with per-paper changes, source evidence,
   audits, metrics, determinism, runtime, and a gate-by-gate verdict.

## Expected tracked files

- `src/knowmat/alpha25/materialize.py`
- `tests/test_alpha25_materialize.py`
- this implementation plan and its design document

Pilot, full-run, determinism, and evaluation artifacts remain untracked under
the existing `data/` and `reports/` conventions.

## Acceptance and rollback boundary

Accept only when every design gate passes: loose precision/F1 strictly improve,
matched/recall never decline, strict precision/F1 do not decline, Composition
and non-Properties remain unchanged, every removal is source-audited, dual runs
are deterministic, and runtime stays within the ceiling. If any gate fails,
narrow or remove only A1. Do not reset, clean, or overwrite unrelated user
changes in the dirty worktree.
