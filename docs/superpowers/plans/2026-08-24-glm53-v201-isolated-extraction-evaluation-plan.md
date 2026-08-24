# GLM-5.3 / v201 Isolated Trial Implementation Plan

> Fallback plan written locally because the required `writing-plans` skill is
> not available in this session. It implements
> `docs/superpowers/specs/2026-08-24-glm53-v201-isolated-extraction-evaluation-design.md`.

## Objective

Run a real, provider-backed GLM-5.3 extraction experiment while preserving the
professionally reviewed prompt and schema, then apply two deterministic v201
precision gates to the exact same responses and compare all arms against the
adjudicated GPT expert ledger and business GT.

## Task 1: Freeze v200 Experiment Inputs

**Create:** experiment manifest under
`data/experiments/glm53-v201-20260824/`.

1. Resolve the 30 papers from the sealed independent-GT manifest.
2. Hash each enhanced Markdown input, all prompt/schema files used by Alpha25,
   the v200 runtime source files, and the current uncommitted runtime diff.
3. Record HEAD, dirty-worktree state, `.env`-safe configuration, existing A
   roots, evaluator revision, and output root names without credentials.
4. Resolve the five pilot papers before GLM-5.3 scoring:
   `paper_006`, `paper_007`, `paper_015`, `paper_016`, and `paper_028`.
5. Validate 30/30 Markdown inputs and 5/5 pilot mappings.

## Task 2: Provider-Neutral Capability Probe

**Create:** `scripts/probe_extraction_capabilities.py`.

**Test:** `tests/test_v11_llm_compat.py`.

1. Add failing tests for a successful configured option, generic fallback from
   rejected thinking/response-format options, redacted endpoint identity,
   secret-free manifest output, and effective-setting cache identity.
2. Implement a one-request non-scientific probe using the same
   OpenAI-compatible request layer as Alpha25.
3. On recognized optional-capability rejection, retry once with the generic
   fallback; never inspect a model-name prefix.
4. Write configured/effective settings, latency, and safe error class to JSON.
5. Run focused tests and inspect the manifest for secret leakage.

## Task 3: Run GLM-5.3 + v200 Pilot

**Output:**
`data/output-alpha25-glm53-v200-pilot-20260824`.

1. Use the capability probe's effective settings for the whole run.
2. Run LLM-only extraction from the frozen OCR baseline with
   `--extraction-model glm-5.3`, `--max-runs 1`, and the five predeclared
   papers. Do not run OCR/VLM/chart processing.
3. Preserve command, start/end time, wall time, exit status, and stdout/stderr.
4. Validate 5/5 papers, task identities, schema, audit artifacts, call counts,
   cache misses, retries, splits, malformed responses, timeout counts,
   median/p95 task latency, and per-paper time.
5. Manually inspect owner fan-out, condition projection, and response shape.
6. Stop before the remaining 25 if any pilot gate fails.

## Task 4: Complete and Freeze GLM-5.3 + v200

**Output:**
`data/output-alpha25-glm53-v200-final30-20260824`.

1. Continue the same task root for all 30 papers without overwriting arm A.
2. Verify 30/30 completion and zero silent-empty/fatal outputs.
3. Freeze hashes of every `v11/02_alpha25_tasks/*.json` response before reading
   comparative scores.
4. Replay in cache-only mode and require byte-identical candidates/finals.
5. Run canonical GPT-expert and business-GT evaluations labeled
   `glm53_v200`.

## Task 5: Implement v201 Global Tensile Protocol Scope

**Modify:** `src/knowmat/alpha25/property_context.py`.

**Modify:** `src/knowmat/alpha25/materialize.py`.

**Test:** `tests/test_alpha25_materialize.py`.

1. Add failing tests for:
   - “at least three samples were tested for each material” within a tensile
     method event authorizing Target recovery;
   - “all the specimens” inside a fatigue statement not authorizing tensile;
   - Reference, multiple protocol/temperature, `respective temperature`,
     owner/state conflict, and missing universal-scope no-ops;
   - complete reversible audit payload.
2. Restrict global-scope evidence to the selected tensile event/compatible
   continuation rather than the entire Markdown block.
3. Extend universal tensile grammar to explicit per-material replicate scope
   only when the same event is tensile and no other test family owns the cue.
4. Preserve current compact source-literal condition projection and do not
   overwrite explicit conditions.
5. Run focused materialization and property-context tests.

## Task 6: Implement v201 Same-Table Table/Prose Merge

**Modify:** `src/knowmat/alpha25/promotion.py`.

**Test:** `tests/test_alpha25_promotion.py`.

1. Add failing positive tests for the CL/PL shapes: unique table row plus prose
   explicitly citing the same table, identical owner/semantic/value/unit, and
   one uniquely richer method-bearing prose survivor.
2. Add no-op tests for different owner/state/role/nature/condition, near value,
   implicit or different table, multiple cell hits, independent average,
   multiple equally rich survivors, core tensile, and Composition.
3. Implement source-only table locator, exact canonical scalar/unit comparison,
   role/owner/state/condition compatibility, explicit same-table citation, and
   deterministic survivor ranking.
4. Merge evidence and confidence into the survivor; write the complete removed
   and before/after survivor records to the normal promotion issue/audit path.
5. Insert the pass after source-assertion deduplication and before downstream
   conflict quarantine.
6. Run permutation, audit, promotion, materialization, and `final.json` schema
   tests.

## Task 7: v201 Pilot and 30-Paper Rematerialization

**Output:**
`data/output-alpha25-glm53-v201-pilot-20260824` and
`data/output-alpha25-glm53-v201-final30-20260824`.

1. Rematerialize the five pilot papers from the frozen GLM-5.3 task responses
   with provider access disabled.
2. Inspect every B-to-C semantic change and audit record.
3. Rematerialize all 30 with zero external calls.
4. Replay to a second output root and require byte-identical results.
5. Verify Composition byte identity and unchanged public schema.

## Task 8: A/B/C Dual-GT Evaluation and Recommendation

**Create:** machine-readable and Markdown reports under
`data/experiments/glm53-v201-20260824/`.

1. Evaluate `glm52_v200`, `glm53_v200`, and `glm53_v201` with the same
   canonical one-to-one matcher against the adjudicated GPT expert ledger.
2. Evaluate the same three arms against business GT; retain the existing
   source-audit evaluator as a supplemental report.
3. Report global/per-axis/core-tensile loose and strict counts, precision,
   recall, F1, owner/condition/value/unit/unsupported/duplicate residuals,
   per-paper deltas, and paper wins.
4. Report model effect B−A, code effect C−B, combined effect C−A, wall time,
   per-task/per-paper latency, provider calls, retries, failures, and effective
   capabilities.
5. Source-review material new disagreements so correct GT omissions are not
   mislabeled hallucinations.
6. Change `.env` default to GLM-5.3 only if every promotion gate in the spec
   passes; otherwise leave GLM-5.2 unchanged and state the failed gate plainly.
7. Audit every named deliverable and acceptance condition before declaring the
   goal complete.
