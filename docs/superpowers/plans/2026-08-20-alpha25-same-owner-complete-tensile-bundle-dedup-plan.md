# Alpha25 Same-Owner Complete Tensile Bundle Deduplication — Implementation Plan

Design: `docs/superpowers/specs/2026-08-20-alpha25-same-owner-complete-tensile-bundle-dedup-design.md`

## Constraints and baseline

- Modify only Alpha25 internal materialization and its focused tests.
- Do not modify prompts, schema, model/provider settings, OCR/VLM/LLM behavior,
  frozen task caches, or public `final.json` structure.
- Require one identical uniquely routed canonical owner; state-lineage and
  cross-owner extensions are outside B1.
- Merge only atomic, locally coherent YS/UTS/elongation bundles. Preserve
  thresholds, ranges, relative/qualitative facts, elongation subtypes,
  orientation siblings, explicit conditions, and all no-candidate facts.
- v46 baseline: 30 papers, 405 frozen caches, 301.37 seconds; GPT expert unique
  global loose = 1,578/6,272/3,093 and core tensile loose/strict =
  166/211/213 and 126/211/213.

## Task 1 — Add bundle-focused failing tests

1. Add test helpers that construct locally bound three-member core-tensile
   bundles with controlled owner, role, nature, evidence unit, values,
   uncertainties, subtype, and condition.
2. Prove one same-owner rounded bundle is atomically absorbed by one uniquely
   richer bundle, with three survivor facts and one complete audit issue.
3. Add negatives for one mismatched member, incomplete bundle, synthetic
   cross-evidence assembly, condition conflict, state/orientation siblings,
   role/nature conflict, elongation subtype conflict, threshold/range/relative
   values, uncertainty conflict, crossed dominance, and multiple maxima.
4. Add input-permutation tests for stable output and audit payloads.

## Task 2 — Build isolated bundle candidates

1. Add small internal immutable bundle/member records near the existing tensile
   precision helpers in `src/knowmat/alpha25/materialize.py`.
2. Reuse current semantic, literal value-shape, canonical unit, owner routing,
   role/nature, subtype, condition, table-binding, evidence-unit, and
   source-assertion helpers rather than creating a second normalization system.
3. Construct a candidate only from exactly one YS, one UTS, and one elongation
   sharing one unique owner and one local source binding.
4. Reject ambiguous members, mixed conditions, and synthetic bundles as a safe
   no-op; keep ordering independent of input position.

## Task 3 — Implement atomic dominance and merge

1. Compare bundles element-wise with exact or literal-rounding compatibility,
   separate central/uncertainty precision, interval overlap, identical units,
   role/nature, subtype, owner, and source-proven condition compatibility.
2. Require one survivor to be no less informative for all three members and
   strictly richer for at least one; confidence and provider labels cannot break
   ties.
3. Build a deterministic per-owner dominance graph and accept only one unique
   maximal one-to-one survivor. Reject crossed, tied, competing, or transitive
   ambiguous candidates.
4. Merge all three member envelopes and evidence atomically. Emit one
   `tensile_same_owner_bundle_duplicate_merged` issue containing removed bundle,
   survivor before/after, three relations, source bindings, and gate decisions.
5. Invoke the new pass after cross-owner dominance and before exact same-owner
   alias folding so existing owner resolution retains its complete bundle.

## Task 4 — Focused verification

1. Run the new tests with `pytest -o addopts=''` and confirm they fail before and
   pass after the production change.
2. Run `tests/test_alpha25_materialize.py`, claim-quality, runtime property alias,
   production-safety, and evaluator tests.
3. Run Python compilation and `git diff --check` on the touched source and test
   files.
4. Verify no prompt/schema/ruleset files changed during B1.

## Task 5 — Frozen-cache pilot and manual audit

1. Rematerialize diagnosed duplicate candidates from the v46 frozen run with
   `scripts/rematerialize_alpha25_tasks.py`, plus orientation, threshold, range,
   condition, and no-candidate protection papers.
2. Compare every changed `final.json` against v46 while excluding automatic run
   metadata.
3. Inspect every accepted bundle audit against copied OCR Markdown. Reject or
   narrow any relation that lacks one unique same-owner scientific observation.
4. Run pilot evaluation against the sealed GPT expert ledger and business GT;
   proceed only when matched/recall and all protection gates hold.

## Task 6 — Full frozen-cache dual replay and evaluation

1. Rematerialize all 30 papers from exactly 405 cached task responses into a new
   output root, recording wall time and confirming zero provider calls.
2. Run the existing GPT-expert/business comparison and capture global,
   Composition, Properties, and unique core-tensile loose/strict metrics.
3. Repeat the complete rematerialization into a second root and prove all 30
   `final.json` files and summaries are byte-identical.
4. Verify prompt, skill, schema, ruleset, and cache digests against v46; verify
   runtime is at most 331.51 seconds on the same host/workload.
5. Write a final v47 report with per-paper changes, audit counts, test results,
   performance, both GT comparisons, and a requirement-by-requirement verdict.

## Expected tracked files

- `src/knowmat/alpha25/materialize.py`
- `tests/test_alpha25_materialize.py`
- `docs/superpowers/plans/2026-08-20-alpha25-same-owner-complete-tensile-bundle-dedup-plan.md`

Pilot, full-run, determinism, and evaluation artifacts remain untracked under
the existing `data/` and `reports/` conventions.

## Acceptance and rollback boundary

Accept only when every gate in the design passes, including strict improvement
of global and core-tensile loose precision/F1 without any matched/recall loss,
unchanged Composition, unchanged non-Properties output, complete audits, byte
determinism, and the runtime ceiling. If any gate fails, narrow or remove only
the B1 pass and its new tests. Do not reset, clean, or overwrite unrelated user
changes in the existing dirty worktree.
