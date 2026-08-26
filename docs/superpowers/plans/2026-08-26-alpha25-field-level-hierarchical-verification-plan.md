# Alpha25 gated compact hierarchical verification implementation plan

This is the local fallback for the unavailable `writing-plans` skill. It
implements the r65 corrective revision in
`docs/superpowers/specs/2026-08-26-alpha25-field-level-hierarchical-verification-design.md`.

The current field-level implementation remains the compatibility baseline.
Work in this plan is limited to the verifier, its source-coordinate authority,
the frozen runner, audit sidecars, and focused tests. It does not change the
professional Alpha25 extraction prompt, extraction schema, Composition
scientific output, OCR/VLM/chart behavior, or public `final.json` shape.

## Task 1: Freeze r58, precisionfix, and r65 evidence

**Inspect:**
`data/output-alpha25-r58-final-source-sentence-state-owner-full30-20260826`.

**Inspect:**
`data/output-alpha25-hierarchical-pilot5-precisionfix-20260825`.

**Inspect:**
`data/output-alpha25-field-level-hierarchical-r65-pilot5-20260826`.

1. Record the five paper IDs, accepted-candidate provenance, evaluator inputs,
   r58 same-paper metrics, precisionfix metrics, and r65 provider metrics.
2. Add no production rule derived from GT, paper ID, title, expected count, or
   model name.
3. Treat the r58 accepted candidate ledger as the next acceptance replay.
   Retain precisionfix only as a diagnostic control.

## Task 2: Repair presentation-only source-coordinate parity

**Modify:** `src/knowmat/alpha25/verification.py`.

**Modify:** `src/knowmat/alpha25/verification_inventory.py`.

**Test:** `tests/test_alpha25_verification.py`.

**Test:** `tests/test_alpha25_verification_inventory.py`.

**Test:** `tests/test_alpha25_evidence.py`.

1. Add red tests proving `±` and `\\pm`, `°` and `^\\circ`, and
   `µ`/`μ` and `\\mu` are presentation-equivalent in verifier grounding.
2. Add a red regression for `23% \\pm 1%` showing that compact location retains
   the final percent sign and its exact source coordinate.
3. Make verifier token normalization share the narrow scientific-symbol
   equivalences already accepted by evidence grounding.
4. Preserve significant trailing `%`, `°`, and equivalent TeX coordinates in
   located evidence spans. Do not expand across unrelated prose.
5. Keep paraphrases, reordered tokens, missing numbers, missing units, and
   scientifically different symbols fail-closed.

## Task 3: Add a compact independent-review protocol

**Modify:** `src/knowmat/alpha25/verification_contracts.py`.

**Test:** `tests/test_alpha25_verification_contracts.py`.

1. Add red tests for a new protocol identity distinct from the primary
   field-verdict protocol and all legacy caches.
2. Define one compact decision per assertion with only:
   `assertion_id`, `verdict`, supplied `evidence_ids`, optional
   `failed_fields`, and a bounded uppercase `reason_code`.
3. Allow only `all_fields_supported`, `contradicted`, or `not_proven`.
4. Reject duplicate/missing assertions, invented evidence IDs, invalid field
   names, free scientific payloads, correction targets, and extra keys.
5. Keep AxisFact and public final-output models unchanged.

## Task 4: Validate compact all-fields support deterministically

**Modify:** `src/knowmat/alpha25/verification.py`.

**Test:** `tests/test_alpha25_verification.py`.

1. Reuse `required_scientific_fields` and the corrected literal-coordinate
   validator for every compact `all_fields_supported` decision.
2. Require the cited evidence set to ground every required immutable field;
   the compact model's claim of support is never authoritative by itself.
3. Partition validation by assertion so one malformed sibling cannot poison a
   valid decision.
4. Accept a hard-risk fact only when the primary field decision and compact
   independent decision are both complete, grounded, and positive.
5. Isolate hard risk on contradiction, not-proven, scientific disagreement,
   missing decision, provider error, truncation, malformed response, or
   grounding failure.
6. Preserve every soft-risk fact unchanged. A non-positive or failed primary
   adds review metadata but performs no destructive mutation.

## Task 5: Gate and batch independent review

**Modify:** `src/knowmat/alpha25/verification_client.py`.

**Test:** `tests/test_alpha25_verification_client.py`.

1. Add red tests proving the primary field review finishes before compact
   secondary requests are selected.
2. Skip GLM-5.2 for every hard assertion whose primary decision is not fully
   supported; audit it as `secondary_skipped_primary_nonpositive`.
3. Build blinded compact requests from only the original assertion, required
   field names, supplied evidence, and compatible inventory entities. Never
   include the primary answer or rationale.
4. Pack at most six primary-positive hard assertions and 6,000 source
   characters per compact request. Partition decisions independently.
5. Use a 1,024-token compact budget. Split a truncated multi-assertion compact
   bundle once; do not retry a truncated singleton with a larger budget.
6. Remove the current one-full-field-response-per-hard-assertion fan-out.
7. Keep all capability fallback provider-neutral and cache identities
   credential-free. Do not branch on provider or model names.

## Task 6: Wire revised limits, metrics, and audit

**Modify:** `src/knowmat/alpha25/verification_pipeline.py`.

**Modify:** `scripts/run_frozen_alpha25_extraction.py`.

**Test:** `tests/test_alpha25_verification_pipeline.py`.

**Test:** `tests/test_alpha25_hierarchical_integration.py`.

**Test:** `tests/test_run_frozen_alpha25_extraction.py`.

1. Expose provider-neutral primary limits of six assertions, 6,000 source
   characters, and 3,072 response tokens.
2. Expose a separate compact-review token budget and split limit without
   changing extraction role settings.
3. Record primary-positive count, secondary-skipped count, compact bundle and
   split counts, compact truncations, provider calls/seconds, wall time,
   failures, and final action counts.
4. Store the complete primary result, compact secondary result or skip reason,
   corrected evidence coordinates, and final action in `quality_audit.json`.
5. Keep compact issue codes and stable assertion references in existing
   issues outputs. Keep verifier-only fields out of `final.json`.
6. Keep omission recovery disabled and Composition as an unconditional bypass.

## Task 7: Prove local correctness and compatibility

1. Run all verification contract, evidence, inventory, applicator, client,
   pipeline, frozen-runner, and integration tests.
2. Run the complete Alpha25 suite and independent-GT evaluator regression.
3. Validate `git diff --check`, model/provider-name production scans,
   GT/title/paper-ID production scans, and unchanged public output schema.
4. Canonically compare Composition scientific observations and identity facts
   before and after the verifier on deterministic fixtures.
5. Preserve unrelated dirty-worktree changes and report unrelated failures
   separately.

## Task 8: Prove r58 candidate replay is cache-only

1. Validate that the frozen runner can load the exact r58 accepted candidate
   ledger for paper_006, paper_007, paper_015, paper_016, and paper_028.
2. Prove candidate extraction makes zero provider calls and no task is silently
   regenerated.
3. Produce a deterministic no-verifier rematerialization control from the same
   candidate ledger so verifier deltas are isolated from materializer drift.
4. Require canonical Composition equality and identical public schema between
   replay control and verified output.

## Task 9: Run the five-paper real-provider acceptance pilot

1. Use real GLM-5.3 primary and GLM-5.2 compact independent-review calls with
   recovery disabled and fresh verifier cache identity.
2. Require 5/5 promotable papers, zero fatal/silent-empty output, zero
   extraction API calls, and complete audit/issue links.
3. Source-review every isolated or preserved formal delta before interpreting
   automated scores.
4. Compare the same five papers against r58 replay control, business GT, and
   adjudicated GPT expert GT with the same one-to-one evaluator.
5. Enforce the design gates: at least +2 points overall unique loose precision
   against each frozen reference, at most -1.5 points recall, non-decreasing
   F1, non-decreasing core-tensile precision, at most -1 point core-tensile
   recall, no lost direct source-literal tensile fact, average at most seven
   verifier calls per paper, median at most three verification minutes, no
   paper above six minutes, and no singleton compact truncation.

## Task 10: Run 30 papers only after the fixed pilot passes

1. Replay all 30 r58 candidate ledgers with the unchanged passing
   configuration.
2. Require 30/30 promotable outputs, zero fatal/silent-empty papers, unchanged
   Composition scientific output, unchanged public schema, and complete audit.
3. Produce global/per-axis/per-paper loose and strict metrics, core-tensile
   metrics, owner/condition residuals, source-adjudicated disagreement classes,
   and complete latency/call/token/failure statistics.
4. Compare the result to r58, business GT, and GPT expert GT in plain language.
5. Accept the implementation only when the real 30-paper evidence satisfies
   every precision, F1, tensile, attribution, auditability, and performance
   gate in the approved specification.
