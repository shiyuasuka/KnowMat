# Alpha25 Hierarchical GLM Verification Implementation Plan

> Fallback plan written locally because the required `writing-plans` skill is
> not available in this session. It implements
> `docs/superpowers/specs/2026-08-25-alpha25-hierarchical-verification-design.md`.

## Objective

Insert a provider-neutral paper-level verification layer between fresh Alpha25
candidate collection and the existing promotion/materialization path. Preserve
the reviewed Alpha25 prompt, Composition output, public `final.json` contract,
and production/GT isolation while improving global precision,
owner/condition attribution, and core-tensile quality.

## Task 1: Freeze the Five-Paper Pilot Before New Calls

**Create:** `data/experiments/alpha25-hierarchical-verification-20260825/pilot_manifest.json`.

1. Select five papers from source-only/frozen-v205 diagnostics covering
   cross-chunk tensile context, owner/condition ambiguity, duplicate fan-out,
   qualitative/chart overprojection, and a Composition-rich control.
2. Record resolved paper IDs, Markdown hashes, v205 output hashes, selection
   reason, HEAD, dirty-worktree hash, and credential-free effective settings.
3. Validate that the manifest was created before any new verifier response and
   that neither production code nor cache identity contains the selected IDs.

## Task 2: Define Verification Contracts and Stable Identities

**Create:** `src/knowmat/alpha25/verification_contracts.py`.

**Create:** `tests/test_alpha25_verification_contracts.py`.

1. Add failing tests for immutable assertion envelopes, inventory entities,
   exact evidence spans, bounded bundles, five decision types, recovery
   proposals, audit records, and run metrics.
2. Implement strict Pydantic/dataclass contracts with `extra="forbid"` for
   provider responses and deterministic serialization helpers.
3. Derive assertion, evidence, and bundle IDs from source/candidate content and
   lineage only; exclude GT, paper identity/title, model names, and expected
   results.
4. Add permutation tests proving stable identities and ordering.

## Task 3: Build the Source Inventory and Evidence Bundles

**Create:** `src/knowmat/alpha25/verification_inventory.py`.

**Create:** `tests/test_alpha25_verification_inventory.py`.

1. Reuse Alpha25 `EvidenceUnit`, accepted anchors, facts, and exact source
   evidence rather than reparsing the paper into an unrelated schema.
2. Add failing tests for entity aliases, state/condition source mentions,
   candidate coverage, axis separation, source-neighborhood grouping, and
   deterministic split boundaries.
3. Implement non-inferential inventory construction and candidate envelopes.
4. Bundle at most 12 candidates and 12,000 source characters by default;
   include only relevant evidence units and inventory entities.
5. Exclude Composition candidates from every verifier/recovery bundle and test
   that Composition bypass remains exact.

## Task 4: Implement Deterministic Decision Validation and Application

**Create:** `src/knowmat/alpha25/verification.py`.

**Create:** `tests/test_alpha25_verification.py`.

1. Add failing tests for `accept`, `merge`, `reassign`, `quarantine`, and
   `unresolved`, including illegal value/unit changes and invented evidence,
   owner, state, or condition.
2. Validate every cited span against the supplied bundle and restrict
   reassignments to inventory entities.
3. Require merge members and survivor to be existing bundle assertions.
4. Apply a complete bundle atomically and preserve stable output ordering.
5. Convert verifier decisions to complete quality-audit records and compact
   issue codes without changing `final.json`.

## Task 5: Add a Provider-Neutral Verifier Client

**Create:** `src/knowmat/alpha25/verification_client.py`.

**Modify:** `src/knowmat/app_config.py` only if typed settings are needed.

**Test:** `tests/test_alpha25_verification_client.py`.

1. Add failing tests for separate extraction/primary/fallback roles, redacted
   endpoint identity, cache separation, optional-capability fallback, timeout,
   truncation, malformed JSON, schema error, one bounded retry, verifier
   fallback, and double failure.
2. Reuse the existing OpenAI-compatible model construction and global provider
   concurrency boundary without importing private extraction-node state into
   domain modules.
3. Compile a compact versioned verifier prompt that contains only the bundle
   contract and supplied evidence. Do not alter Alpha25 extraction prompts.
4. Cache responses by protocol, evidence/candidates, limits, endpoint/model
   role configuration, effective capabilities, and output budget.
5. Fall back per bundle. Convert a double failure to explicit unresolved
   decisions rather than accepting candidates or aborting the paper.

## Task 6: Implement One-Pass Bounded Omission Recovery

**Modify:** `src/knowmat/alpha25/verification.py`.

**Test:** `tests/test_alpha25_verification.py`.

1. Add failing tests for uncovered literal numeric/qualitative source
   assertions, already-covered no-ops, chart estimation rejection, collective
   owner fan-out rejection, and no recursive recovery.
2. Build recovery requests only from supported non-Composition uncovered
   evidence, at most 10 assertions and 12,000 source characters per request.
3. Require an independent verifier call for every proposed fact; the proposing
   response cannot validate itself.
4. Route qualitative tensile comparisons to audit instead of numeric
   `Properties`.

## Task 7: Integrate Before Promotion and Preserve Artifacts

**Modify:** `src/knowmat/nodes/extraction.py`.

**Modify:** `scripts/run_frozen_alpha25_extraction.py`.

**Modify:** the existing report/audit packaging module only where current
artifact assembly requires it.

**Test:** `tests/test_alpha25_extraction_integration.py` and focused reporting
tests.

1. Add an opt-in hierarchical-verification mode with explicit primary and
   fallback roles; the default remains off until the pilot passes.
2. Run it after complete task collection and before
   `promote_axis_facts → materialize_candidate`.
3. Preserve task-to-fact lineage and pass verified/reassigned/recovered facts
   through all existing precision gates.
4. Append complete verification audit records to `quality_audit.json` and
   compact cross-linked codes to `issues.json/.md` through the existing issue
   pipeline.
5. Add per-stage/provider/cache/fallback metrics to coverage and run summaries.
6. Prove legacy mode is byte/scientifically identical and that Composition is
   identical with verification on or off.

## Task 8: Production-Safety, Contract, and Regression Tests

**Modify:** `tests/test_alpha25_production_safety.py`.

1. Scan all new production modules for GT imports/paths, paper IDs/titles,
   expected values/counts, and model/provider-specific branches.
2. Validate unchanged public `final.json` schema and complete audit/issues
   cross-links.
3. Run focused tests, then the entire Alpha25 suite, then the full repository:

   `./venv/bin/python -m pytest -o addopts='' <focused tests>`

   `./venv/bin/python -m pytest -o addopts='' tests/test_alpha25_*.py`

   `./venv/bin/python -m pytest -o addopts=''`

4. Document any unrelated pre-existing external-fixture failure separately.

## Task 9: Run the Five-Paper Real-API Blind Pilot

**Output:** `data/output-alpha25-hierarchical-verification-pilot5-20260825`.

1. Run fresh GLM-5.2 Alpha25 candidate extraction and GLM-5.3 primary
   verification with GLM-5.2 bundle fallback over the frozen pilot manifest.
2. Do not run OCR/VLM/chart stages and do not read either GT until all provider
   responses and outputs are frozen.
3. Validate 5/5 completion, cache identities, audit cross-links, Composition
   equality, unchanged schema, API counts, tokens, latency, retries, fallback,
   timeout, truncation, and median per-paper runtime.
4. Evaluate against business GT and GPT expert GT with the same canonical
   matcher and same-paper v205 baseline.
5. Source-adjudicate owner/condition, overprojection, and important GT
   disagreements.
6. Require every quantitative gate in the design before proceeding.

## Task 10: Iterate Generally or Run the Thirty-Paper Acceptance

1. If a pilot gate fails, retain all responses, classify failures, and adjust
   only general contracts, evidence bundling, capability behavior, or verifier
   protocol. Never add GT-derived or paper-specific production rules.
2. Repeat the frozen five-paper pilot until it passes or evidence proves the
   architecture unsuitable.
3. On a passing pilot, run the identical configuration over all 30 papers.
4. Produce dual-GT global/per-axis/core-tensile loose/strict metrics,
   owner/condition and overprojection counts, per-paper wins, Composition
   equality, audit coverage, and complete runtime/provider statistics.
5. Give a source-adjudicated plain-language conclusion describing which system
   is more accurate, each system's omissions and factual errors, and whether
   unmatched output is a pipeline hallucination or a GT omission.
6. Audit every design requirement and named artifact before declaring the
   optimization goal complete.
