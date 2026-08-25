# Alpha25 Frozen Candidate Replay Implementation Plan

> The required `writing-plans` skill is not available in this session. This
> local plan implements the approved frozen-candidate replay design.

## Task 1: Add a content-addressed replay cache contract

- Create `src/knowmat/alpha25/candidate_replay.py`.
- Validate task response/identity pairs and recorded response hashes.
- Build deterministic credential-free manifests and stage caches only into an
  empty destination.
- Add focused tests for success, corruption, missing identity, and non-empty
  destination behavior.

## Task 2: Preserve exact future source scopes

- Extend new task identity sidecars with an audit-only source-scope payload and
  SHA-256 without changing `_alpha25_task_cache_identity` or cache filenames.
- Test that the response cache path stays stable and that the saved scope hash
  is correct.

## Task 3: Integrate replay into the frozen extraction runner

- Add `--candidate-replay-root`.
- Stage each selected paper's exact task cache before extraction and set
  `KNOWMAT2_ALPHA25_CACHE_ONLY=1` before workers start.
- Enforce all terminal tasks are cache hits, no extraction-provider time is
  recorded, and staged/output task manifests match.
- Record replay provenance in per-paper and run manifests.

## Task 4: Verify locally

- Run replay, extraction-integration, hierarchical-verification, and
  production-safety focused tests.
- Run the complete focused verification suite and report unrelated failures
  separately.

## Task 5: Build the same-candidate five-paper control

- Replay the five precision-fix candidate caches with verifier disabled.
- Require 5/5 success, 100% task-cache hits, zero extraction API calls, and
  exact response-manifest equality.
- Freeze outputs before evaluation.

## Task 6: Evaluate the verifier itself

- Compare the replayed no-verifier control with the existing precision-fix
  verified arm against business GT and GPT expert GT.
- Report global/per-axis/core-tensile precision, recall, F1, and deltas plus
  verifier calls and latency.
- If any five-paper gate fails, keep the 30-paper run blocked and use the same
  replay source for the next general risk-routing iteration.

## Task 7: Require two-role consensus for deletion

- Send only primary `quarantine` assertions to the independent fallback role.
- Quarantine only when both grounded judgments agree; preserve disagreements
  and technical failures unchanged with complete audit lineage.
- Keep technical fallback and scientific confirmation metrics separate.
- Add contract, client, pipeline, integration, audit, and production-safety
  tests without changing the Alpha25 extraction prompt/schema or `final.json`.

## Task 8: Re-run the same frozen five-paper candidates

- Use the identical replay manifests from Task 5.
- Make real verifier API calls with GLM-5.3 primary and GLM-5.2 confirmation.
- Compare the new arm against the no-verifier control, the previous broad
  verifier arm, business GT, and GPT expert GT.
- Keep the 30-paper run blocked unless every original gate passes.

## Task 9: Fail closed after primary technical failure

- When the primary bundle request fails, allow the fallback role to accept or
  non-destructively route assertions, but preserve every fallback quarantine
  proposal unchanged for review.
- Do not call the already failed primary role again for destructive
  confirmation; record the skipped confirmation and original failure in
  `quality_audit.json` and aggregate metrics.
- Give normal singleton confirmations a model-neutral, separately configurable
  short output-token budget.
- Prove the route with focused tests, then replay `paper_007` before reopening
  the frozen five-paper gate. The 30-paper run remains blocked.
