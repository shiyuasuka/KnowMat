# Alpha25 field-level hierarchical verification implementation plan

This is the local fallback for the unavailable `writing-plans` skill. It
implements
`docs/superpowers/specs/2026-08-26-alpha25-field-level-hierarchical-verification-design.md`.

## Task 1: Freeze the v1 compatibility baseline

1. Record the current verification protocol, risk-routing, five-paper replay,
   r58 output, evaluator, and real-provider manifests used by the design.
2. Add regression fixtures for the existing whole-assertion response so old
   caches fail closed rather than being parsed as the new protocol.
3. Preserve current provider-neutral capability handling and secret-redaction
   behavior.

## Task 2: Add field-level verification contracts

**Modify:** `src/knowmat/alpha25/verification_contracts.py`.

**Test:** `tests/test_alpha25_verification_contracts.py`.

1. Add red tests for complete field verdicts, allowed verdict enums, evidence
   IDs, optional selected inventory coordinates, and stable serialization.
2. Add protocol-v2 field-verdict response models without changing AxisFact or
   public final-output models.
3. Reject missing required fields, invented corrections, duplicate assertion
   decisions, and v1/v2 protocol mixing.

## Task 3: Implement severity-aware source-only routing

**Modify:** `src/knowmat/alpha25/verification_risk.py`.

**Test:** `tests/test_alpha25_verification_risk.py`.

1. Add red tests for hard risks: incompatible multi-owner evidence, ambiguous
   multi-condition evidence, cross-owner payload projection, unresolved
   respectively mapping, qualitative/derived/source-locator scalar projection,
   and incomplete/generic owners.
2. Add preservation tests for aliases, one literal compatible owner, explicit
   collective mappings, direct table cells, complete source sentences, and
   low-risk core tensile.
3. Return `none`, `soft`, or `hard` severity plus stable source-only reason
   codes. Never consult paper identity, GT, model, or expected values.

## Task 4: Validate and apply field-level decisions

**Modify:** `src/knowmat/alpha25/verification.py`.

**Test:** `tests/test_alpha25_verification.py`.

1. Add red tests for exact required-field coverage and grounded evidence.
2. Implement immutable field verdict validation restricted to supplied
   assertions, evidence, entities, and literal coordinates.
3. Implement soft-risk behavior: primary support preserves; destructive or
   reassignment decisions require compatible independent review; failed
   destructive confirmation preserves with review.
4. Implement hard-risk behavior: both roles must support every required field;
   exact same-target consensus is required for reassignment; contradiction,
   not-proven, disagreement, or technical failure isolates the complete record.
5. Produce complete before/after audit payloads and compact stable issue codes.

## Task 5: Upgrade the provider client and prompts

**Modify:** `src/knowmat/alpha25/verification_client.py`.

**Test:** `tests/test_alpha25_verification_client.py`.

1. Add red tests for compact v2 prompts, independent-review blindness,
   hard-risk mandatory second review, soft-risk destructive-only review,
   malformed/truncated/grounding failure handling, cache separation, and role
   metrics.
2. Replace the whole-assertion verifier response shape with field verdicts for
   semantic, value, unit, owner, state, condition, and origin/role as actually
   asserted.
3. Keep extraction prompt compilation untouched.
4. Preserve generic capability fallback and prohibit model-name branching.
5. Bound initial bundles to three assertions and 3,500 source characters;
   expose limits through configuration and cache identity.

## Task 6: Wire protocol v2 into the paper pipeline

**Modify:** `src/knowmat/alpha25/verification_pipeline.py`.

**Modify:** `scripts/run_frozen_alpha25_extraction.py`.

**Test:** `tests/test_alpha25_verification_pipeline.py`.

**Test:** `tests/test_alpha25_hierarchical_integration.py`.

1. Route `none` facts unchanged, send soft/hard facts with their severity and
   reasons, and retain Composition as an unconditional bypass.
2. Permit only routed high-risk Properties; direct low-risk tensile facts stay
   out of provider requests.
3. Disable omission recovery for the v2 precision experiment.
4. Report severity counts, both scientific-review roles, technical fallback,
   isolation/reassignment/preservation counts, provider calls, tokens, and
   latency.
5. Keep `final.json` unchanged and cross-link full quality audit to compact
   issues.

## Task 7: Run local verification

1. Run the contract, risk, applicator, client, pipeline, and hierarchical
   integration tests with the repository virtual environment.
2. Run the Alpha25 focused suite and independent-GT evaluator regression.
3. Validate production-safety scans, git whitespace, public schema, and
   Composition non-mutation.
4. Fix only failures caused by this change; document unrelated dirty-worktree
   failures separately.

## Task 8: Run the frozen five-paper real-provider pilot

1. Replay the exact cached GLM-5.2 candidates from the frozen pilot.
2. Use configured GLM-5.3 primary and GLM-5.2 independent-review roles with
   real provider calls and recovery disabled.
3. Validate 5/5 outputs, role/capability manifests, cache identities, no
   extraction calls, and complete audit/issue links.
4. Source-review every formal delta before interpreting GT scores.
5. Compare the pilot to the same-candidate control against business GT and GPT
   expert GT and enforce every gate in the design.

## Task 9: Run and report 30 papers only after a passing pilot

1. Replay all 30 frozen candidates with the unchanged passing configuration.
2. Require 30/30 promotable outputs, zero fatal/silent-empty papers, canonical
   Composition identity, unchanged public schema, and deterministic cache-only
   replay.
3. Produce global/per-axis/per-paper loose and strict metrics, core-tensile
   metrics, owner/condition residuals, source-adjudicated disagreement classes,
   latency, provider-call, token, fallback, and failure statistics.
4. Compare the result to r58, business GT, and GPT expert GT in plain language.
5. Accept the implementation only if the real 30-paper evidence satisfies the
   precision, F1, tensile, attribution, auditability, and performance gates in
   the approved specification.
