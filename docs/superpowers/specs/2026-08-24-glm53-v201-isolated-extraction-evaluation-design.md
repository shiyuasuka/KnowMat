# GLM-5.3 Isolated Extraction Trial and v201 Precision Gates

## Status

The user approved the experiment design and execution order on 2026-08-24.
Implementation and paid provider calls remain pending written confirmation of
this specification.

## Goal

Determine whether replacing only the Alpha25 extraction agent from GLM-5.2 to
GLM-5.3 improves factual precision, recall, and owner/condition attribution,
then measure the independent contribution of two deterministic v201
post-processing gates.

The primary objective is precision-first convergence toward the adjudicated
GPT-5.6-sol expert ledger without losing useful recall. The business-provided GT
is a second external comparison. Composition, which is already a relative
strength of the GLM pipeline, must not regress materially.

This experiment does not change the professionally reviewed prompt, extraction
schema, OCR Markdown, chart context, routing, evaluator, or public `final.json`
shape. It must not contain a runtime branch for `glm-5.2`, `glm-5.3`, any future
model name, any paper title, GT membership, material name, or fixture value.

## Selected Approach

Use a staged three-arm isolation experiment:

1. **A — GLM-5.2 + v200:** the existing frozen 30-paper result.
2. **B — GLM-5.3 + v200:** fresh extraction calls over the same 30 OCR Markdown
   inputs using the current v200 code.
3. **C — GLM-5.3 + v201:** rematerialize the exact frozen B task responses with
   the v201 deterministic gates and no additional model calls.

Run a five-paper pilot before the full 30-paper B arm. This is preferred over a
direct full-corpus run because it can detect endpoint incompatibility,
pathological latency, malformed response behavior, and a material precision
regression before spending the full call budget. Mixing GLM-5.3 and v201 in the
first fresh run is rejected because any observed change would be impossible to
attribute to the model or code.

## Frozen Inputs and Baselines

All model arms consume the existing 30 nested Markdown files under `data/raw`.
They are the fixed result of the earlier fresh OCR/chart pass. No OCR, PaddleOCR,
MinerU, VLM, PDF parsing, chart digitization, or figure-description call is
allowed during this experiment.

The frozen A task/output roots are:

- task cache: `data/output-alpha25-prompt-v5-final30-20260818`;
- v200 materialization:
  `data/output-alpha25-expert-convergence-v200-summary-shadow-final30-20260824`;
- canonical evaluation:
  `data/evaluation-alpha25-v200-summary-shadow-canonical-v1-20260824`.

The official external references are:

- adjudicated GPT expert GT:
  `data/gt/gpt56sol-independent-expert-20260818/adjudicated`;
- business GT: `data/gt/papers-native-ids-with-pdf-ocr-images-20260809`.

The GT files are evaluation-only. They are unavailable to prompt compilation,
model calls, candidate generation, promotion, deduplication, recovery,
quarantine, and packaging.

The corrected A baseline against the GPT expert ledger is:

| Scope | Mode | Matched / System / Expert | Precision | Recall | F1 |
|---|---|---:|---:|---:|---:|
| Global unique | loose | 669 / 1371 / 3093 | 0.487965 | 0.216295 | 0.299731 |
| Global unique | strict | 365 / 1371 / 3093 | 0.266229 | 0.118008 | 0.163530 |
| Core tensile | loose | 76 / 83 / 213 | 0.915663 | 0.356808 | 0.513514 |
| Core tensile | strict | 41 / 83 / 213 | 0.493976 | 0.192488 | 0.277027 |

Business GT is not treated as an infallible universal truth. The final report
must provide metrics against both ledgers and source-level adjudication for
important disagreements, rather than equating every unmatched claim with a
hallucination.

## Provider-Neutral GLM-5.3 Injection

Only the extraction model changes in arm B, through the existing CLI option:
`--extraction-model glm-5.3`. The `.env` default remains `glm-5.2` until the
experiment passes. Subfield detection, evaluation, manager, and flagging models
remain unchanged.

Before the pilot, execute one non-scientific capability probe using the same
OpenAI-compatible protocol and option shape as extraction. Record, without any
credential or query string:

- requested model and endpoint identity;
- API protocol;
- configured and effective thinking mode;
- configured and effective structured-response mode;
- status, latency, and provider error class if rejected.

If an optional provider extension is rejected, select the existing generic
fallback (`provider_default` for thinking or text mode for response format) once
for the whole run. Do not rediscover the same incompatibility on every task.
Capability selection is keyed by endpoint identity, model, protocol, option,
and option value—not by a hard-coded model branch. The effective settings are
written to an experiment manifest and become part of the arm-B task identity.

The current extraction cache identity already includes model, credential-free
endpoint identity, response mode, output token budget, and thinking mode. Tests
must prove that `glm-5.2` and `glm-5.3` cannot share a candidate cache entry and
that changing the effective fallback mode also changes the identity. API keys,
authorization headers, and full credential-bearing URLs must never enter logs,
manifests, cache keys, reports, or commits.

## Five-Paper Pilot

The pilot uses five fixed scientific roles, selected before any GLM-5.3 score is
seen:

1. paper 015 — table/prose duplicate positive case;
2. paper 016 — globally applicable tensile protocol recovery positive case;
3. paper 028 — tensile-versus-fatigue scope-confounder negative case;
4. one composition-rich paper with multiple explicitly named materials or
   states, selected deterministically from the frozen input manifest by the
   highest v200 Composition count, then lowest paper ID;
5. one multi-temperature or multi-protocol tensile paper, selected
   deterministically from the frozen source inventory by the highest number of
   distinct explicit tensile temperatures/protocols, then lowest paper ID.

If one selected control duplicates papers 015, 016, or 028, take the next paper
under the same predeclared ordering. Persist the resolved paper IDs and the
source-only selection counts before running GLM-5.3. Neither GT score nor model
output may influence selection.

Pilot promotion to all 30 requires:

- 5/5 papers complete with no fatal or silent-empty task;
- no credential leakage;
- every task records model identity and configured/effective capabilities;
- malformed, empty, timeout, truncation, retry, and split counts are explicit;
- no repeated per-task retry caused by one already-known unsupported optional
  provider parameter;
- median task latency and p95 task latency are reported, together with wall
  time, provider-call count, cache-hit count, queue time, model-call time,
  retry count, and throughput;
- output validates against the unchanged schema and preserves all required
  audit artifacts; and
- manual source review finds no systemic owner fan-out, cross-condition
  projection, or response-contract corruption.

Pilot score is diagnostic, not a tuning input. A poor pilot stops the full run
and produces a failure report; it does not trigger ad-hoc prompt edits or
paper-specific filters.

## v201 Gate 1: Safe Global Tensile Protocol Recovery

Recover an omitted tensile condition onto an existing **Target** tensile result
only when all of the following are proven from the current source inventory:

1. The numeric result has explicit evidence for its current Target owner.
2. Exactly one compatible tensile protocol exists in the same bounded tensile
   method block and the same test family.
3. The method block explicitly states universal scope for the relevant tensile
   specimens/materials, including grammar such as “each material,” “all tensile
   specimens,” or an equivalent unambiguous quantifier.
4. Protocol and result agree on material lineage, test family, property family,
   state, orientation, temperature family, and role/nature.
5. The recovered condition does not overwrite or conflict with an explicit
   condition already attached to the result.

Reference results never inherit a protocol. A nearby fatigue, creep, hardness,
or other test statement cannot prove tensile scope. In particular, “all the
specimens” inside a fatigue proposition is not universal evidence for a nearby
tensile result.

The gate is a no-op for multiple compatible protocols, multiple temperatures,
`respective temperature`, condition/owner conflicts, non-unique method blocks,
missing universal scope, parsing uncertainty, or cross-family proximity. It
never invents a condition or chooses the nearest protocol.

Each accepted recovery emits a reversible audit record containing the full
fact before/after, protocol candidate, bounded method block, universal-scope
cue, family/owner compatibility decisions, rejected competing candidates, and
`owner_invented=false`.

## v201 Gate 2: Same-Fact Table/Prose Duplicate Merge

Merge a prose Property into one table Property survivor only when all of the
following are true:

1. Both are non-core-tensile numeric Properties.
2. Owner, material lineage, state/region, role/nature, property semantic,
   compatible canonical unit, normalized central value, and explicit condition
   are exactly compatible.
3. The prose explicitly cites or summarizes the same table, and the table fact
   resolves to one unique row/cell coordinate.
4. Exactly one survivor satisfies the full relation.
5. The table survivor is at least as specific and retains a complete evidence
   union.

Nearby prose, equal values in different experiments, rounded-near values,
range overlap, evaluator matches, different owners/states/conditions,
independent averages, repeated measurements, multiple candidate cells, or an
implicit table association are mandatory no-ops.

The removed record is retained in `quality_audit.json` with the full removed
fact, survivor before/after, source relation, comparison fields, uniqueness
decision, and deterministic keys. `issues.json` and `issues.md` receive a short
issue code. `final.json` receives no new field.

## v201 Placement and Determinism

Both gates live in `src/knowmat/alpha25/promotion.py` after existing
owner/source-coordinate reconciliation and before final conflict quarantine and
packaging. Protocol recovery runs before table/prose duplicate merge. They
consume only current source evidence and candidate inventory; they make no
model call.

Candidate and audit ordering must be stable under input-order permutations. A
candidate-local exception leaves the original fact unchanged and records an
issue; it must not partially mutate output. Runtime selection cannot read any
GT, prior expected output, paper title, UID, model name, or provider name.

Focused tests must include:

- the paper-016 universal tensile positive grammar;
- the paper-028 fatigue-scope confounder as a no-op;
- Target versus Reference behavior;
- one versus multiple protocols and temperatures;
- explicit condition conflicts and `respective temperature`;
- same-table exact duplicate merge;
- near-value, different owner/state/condition, independent average, multiple
  table cells, and implicit-table no-ops;
- complete reversible audit and issue payloads;
- unchanged `final.json` schema;
- input-order invariance; and
- Composition and core-tensile non-interference for the duplicate gate.

The read-only v201 simulation over frozen A responses is a forecast, not an
acceptance substitute:

| Metric | v200 | v201 simulation |
|---|---:|---:|
| Global loose precision | 0.487965 | 0.488678 |
| Global loose F1 | 0.299731 | 0.299866 |
| Global strict F1 | 0.163530 | 0.169879 |
| Core-tensile loose precision | 0.915663 | unchanged |
| Core-tensile strict matched | 41 | 55 |
| Core-tensile strict precision | 0.493976 | 0.662651 |
| Core-tensile strict recall | 0.192488 | 0.258216 |
| Core-tensile strict F1 | 0.277027 | 0.371622 |

Production implementation must select relations from source semantics, not from
these expected counts.

## Execution Order

1. Seal the experiment manifest: code revision, dirty-worktree notice, hashes
   of every runtime source file and the uncommitted runtime diff, hashes of all
   30 Markdown inputs, prompt package/schema, provider-neutral settings, A
   roots, and evaluator version. This makes the current uncommitted v200 state
   reproducible without staging or overwriting unrelated user changes.
2. Run the capability probe and freeze effective optional capabilities.
3. Run the five-paper GLM-5.3 + v200 pilot into a new output/task root.
4. Validate and manually review the pilot. Stop on a pilot gate failure.
5. Run the remaining 25 papers into the same B root; do not overwrite A.
6. Verify 30/30 completeness and freeze B task-response hashes before looking
   at comparative scores.
7. Evaluate B against adjudicated GPT expert GT and business GT.
8. Implement and test v201.
9. Rematerialize the five pilot papers from the exact B cache with zero provider
   calls; inspect every v201 change.
10. Rematerialize all 30 B task responses into a separate C root with zero
    provider calls and deterministic replay.
11. Evaluate C using the identical evaluator and both external references.
12. Produce one A/B/C comparison report and a source-adjudicated residual
    sample. Only then decide whether to change `.env` default to GLM-5.3.

## Measurement Contract

For A, B, and C report, at minimum:

- 30-paper completion/failure/review count;
- total wall time; per-paper and per-task median/p95/max latency; queue versus
  provider-call time; calls, retries, task splits, timeouts, malformed outputs,
  cache hits/misses, and effective concurrency;
- raw and unique claim counts globally and for each of Composition,
  Processing, Structure, Characterization, and Properties;
- loose and strict matched/system/reference counts, precision, recall, and F1
  against adjudicated GPT expert GT;
- the same axis/core-tensile comparison against business GT using the same
  one-to-one matching rules;
- unique core-tensile metrics;
- owner, condition, value, unit, unsupported-claim, and duplicate residual
  counts;
- per-paper deltas and the number of papers led by each arm; and
- exact B-to-C claim/audit diff proving that only v201 deterministic decisions
  changed.

All comparison tables use the explicit labels `glm52_v200`, `glm53_v200`, and
`glm53_v201`; they must not reuse the ambiguous historical label `final_v5`.
The GPT-expert and business-GT tables use the same canonical claim
normalization and one-to-one matcher. The existing business source-audit report
may also be emitted as a supplemental diagnostic, but it cannot replace the
apples-to-apples matcher.

The report must separate three conclusions:

1. **Model effect:** B minus A.
2. **Code effect:** C minus B.
3. **Combined effect:** C minus A.

Claim-count reduction alone is not evidence of higher precision. Important
unmatched B/C claims are manually checked against source evidence, and correct
facts missing from either GT are labeled as GT omissions rather than
hallucinations.

## Acceptance and Promotion

Arm B is eligible for full-corpus completion after the pilot gates pass. It is
eligible to replace GLM-5.2 as the default extraction model only if the final
30-paper report shows:

- no fatal, empty, or schema-invalid paper;
- global loose precision and F1 against GPT expert GT do not regress;
- global strict F1 and core-tensile strict F1 do not regress;
- Properties precision does not regress;
- Composition loose precision does not regress by more than 0.01 absolute and
  Composition matched count does not regress by more than 2%;
- no material rise in unsupported projection, wrong-owner, condition-conflict,
  or duplicate rates after source adjudication; and
- wall time and provider-call behavior are reported and operationally
  acceptable, with no systematic optional-parameter retry tax.

Arm C is accepted only if, relative to B:

- every semantic change is explained by one of the two source-only v201 gates;
- loose matched count and recall do not decrease globally, by axis, or for core
  tensile;
- global loose precision/F1, strict F1, Properties precision, and core-tensile
  strict precision/F1 are non-decreasing;
- Composition is byte-identical;
- all removed, merged, or recovered records are reversibly audited;
- 30/30 rematerialization makes zero external calls; and
- a second replay is byte-identical.

If GLM-5.3 improves recall but lowers precision, it is not promoted merely for
finding more facts. If it improves precision but loses material recall, the
report identifies the affected axes and the `.env` default remains GLM-5.2
pending a separate approved design. If C fails only because of one unsafe v201
relation, narrow or disable that relation; do not compensate with a broader
recovery rule.

## Deliverables

- capability-probe and experiment manifests without secrets;
- fresh GLM-5.3 v200 pilot and 30-paper B outputs;
- frozen B task-response digest manifest;
- v201 implementation and focused/full test results;
- GLM-5.3 v201 five-paper and 30-paper C rematerializations;
- unchanged-shape `final.json`, plus complete `quality_audit.json` and concise
  `issues.json`/`issues.md` per paper;
- machine-readable and Markdown A/B/C comparisons against both GT ledgers;
- latency/call-volume report; and
- a plain-language recommendation: keep GLM-5.2, promote GLM-5.3, or continue
  experiment without changing the default.

## Out of Scope

This experiment does not revise the prompt, adopt a new schema/package release,
rerun OCR/VLM/chart extraction, tune against GT, add multi-pass voting, alter
evaluation semantics, suppress arbitrary unmatched claims, or change models for
non-extraction agents. Any such change requires a separate isolated design.
