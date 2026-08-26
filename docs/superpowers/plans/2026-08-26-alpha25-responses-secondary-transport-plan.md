# Alpha25 Responses Secondary Transport Implementation Plan

## Scope

Implement the approved provider-neutral Responses transport and fixed-length
label-array independent review described in
`docs/superpowers/specs/2026-08-26-alpha25-responses-secondary-transport-design.md`.
Keep extraction prompts/schema, Composition, OCR/VLM/chart behavior, and the
public `final.json` contract unchanged.

## Task 1: Add the private label protocol

**Modify:** `src/knowmat/alpha25/verification_contracts.py`

**Test:** `tests/test_alpha25_verification_contracts.py`

1. Add `alpha25_compact_label_review_v2` and the `S/C/N` label type.
2. Add a deterministic parser that accepts only one JSON array, exact expected
   cardinality, and allowed labels.
3. Map request positions back to stable assertion IDs without accepting IDs or
   scientific content from the provider.
4. Keep the v1 compact object parser for cached historical runs.

## Task 2: Add provider-neutral per-role API mode

**Modify:** `src/knowmat/alpha25/verification_client.py`

**Modify:** `scripts/run_frozen_alpha25_extraction.py`

**Modify:** `scripts/rematerialize_alpha25_tasks.py`

**Test:** `tests/test_alpha25_verification_client.py`

**Test:** `tests/test_run_frozen_alpha25_extraction.py`

**Test:** `tests/test_rematerialize_alpha25_tasks.py`

1. Add `chat_completions|responses` to `VerifierRoleConfig` and cache identity.
2. Resolve primary and fallback API modes from role-level environment settings;
   do not inspect model or provider strings.
3. Expose the effective modes in runner manifests and rematerialization wiring.
4. Prove credentials never enter identity, cache, metrics, or audit.

## Task 3: Implement the direct Responses label transport

**Modify:** `src/knowmat/alpha25/verification_client.py`

**Test:** `tests/test_alpha25_verification_client.py`

1. Add an injectable official-OpenAI Responses caller separate from the
   Chat Completions JSON caller.
2. Send the blinded indexed label request with configured endpoint, role model,
   timeout, reasoning effort, and `max_output_tokens`.
3. Parse only `response.output_text`; require completed status and an exact
   label array.
4. Capture response status, incomplete details, reasoning summary, token usage,
   final text, latency, and generic capability fallback.
5. Fail closed on incomplete/missing/malformed/cardinality-invalid responses.
6. Do not silently switch API transport after a failure.

## Task 4: Execute verification in two paper-level phases

**Modify:** `src/knowmat/alpha25/verification_client.py`

**Modify:** `src/knowmat/alpha25/verification_pipeline.py`

**Test:** `tests/test_alpha25_verification_client.py`

**Test:** `tests/test_alpha25_verification_pipeline.py`

**Test:** `tests/test_alpha25_hierarchical_integration.py`

1. Finish and partition every primary field bundle before selecting secondary
   work.
2. Skip secondary work for soft assertions and non-positive hard primary
   decisions.
3. Repack all primary-positive hard assertions across primary bundles into
   axis-homogeneous label bundles capped at six assertions and 6,000 evidence
   characters.
4. Run the independent Responses bundles with existing bounded concurrency.
5. Apply the current fail-closed hard consensus after mapping labels to stable
   assertion IDs.
6. Preserve the current soft sibling isolation behavior and prevent one invalid
   assertion response from poisoning valid siblings.

## Task 5: Preserve cache, audit, metrics, and split behavior

**Modify:** `src/knowmat/alpha25/verification_client.py`

**Modify:** `src/knowmat/alpha25/verification_pipeline.py`

**Test:** `tests/test_alpha25_verification_client.py`

**Test:** `tests/test_alpha25_verification_pipeline.py`

1. Store label bundle identity, request index, mapped label, Responses metadata,
   reasoning summary, and final action in `quality_audit.json`.
2. Add compact issue codes for non-positive labels, invalid cardinality,
   incomplete Responses, and transport failure.
3. Record primary calls, Responses calls, cache hits, labels, splits,
   truncations, technical failures, latency, and provider attempts.
4. Split a failed multi-assertion label bundle at most once; never expand or
   retry a failed singleton with a larger budget.
5. Keep verifier-only data out of `final.json`.

## Task 6: Add pre-verifier reproducibility manifests

**Modify:** `scripts/rematerialize_alpha25_tasks.py`

**Modify:** `scripts/run_frozen_alpha25_extraction.py`

**Test:** `tests/test_rematerialize_alpha25_tasks.py`

**Test:** `tests/test_run_frozen_alpha25_extraction.py`

1. Canonically hash promoted candidate payloads before verification per paper.
2. Record task-cache/source hashes, evidence/planner configuration, and enabled
   deterministic feature switches.
3. Allow a pilot to require an expected pre-verifier digest and abort before
   provider calls on mismatch.
4. Generate a matching no-verifier control with the same digest before the
   real-provider pilot.

## Task 7: Prove local correctness

1. Run focused contract/client/pipeline/runner/rematerializer tests.
2. Run the complete Alpha25 and independent-GT regression suite.
3. Run `git diff --check` and production scans for model/provider, paper/title,
   and GT branches.
4. Compare canonical Composition scientific signatures and public top-level
   schema against a matching no-verifier control.

## Task 8: Run the real five-paper acceptance pilot

1. Use a new verifier cache and zero candidate-extraction API calls.
2. Prove the verified and control pre-verifier digests match before scoring.
3. Require 5/5 promotable, zero fatal/silent-empty papers, zero singleton label
   truncation, average at most seven calls per paper, median at most three
   minutes, and no paper above six minutes.
4. Compare with the matching control, r58, business GT, and GPT expert GT.
5. Source-review every formal delta and classify GT disagreement.
6. Do not run 30 papers unless every design gate passes.
