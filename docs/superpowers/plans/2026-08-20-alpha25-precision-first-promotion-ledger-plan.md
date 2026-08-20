# Alpha25 Precision-First Promotion Ledger and Bounded Risk Verifier — Implementation Plan

Design: `docs/superpowers/specs/2026-08-20-alpha25-precision-first-promotion-ledger-design.md`

## Constraints and baseline

- Keep the reviewed extraction prompt, Alpha25 task response schema, OCR/VLM
  stages, provider capability negotiation, and public `final.json` unchanged.
- Protect v47 Composition: loose F1 65.9939%, strict F1 32.6942%, with no
  matched/recall regression.
- v47 global unique loose precision/recall/F1 is
  25.1675%/51.0184%/33.7071%; final rollout requires at least
  35%/46.0718%/40%.
- v47 core-tensile unique loose precision/recall/F1 is
  79.4258%/77.9343%/78.6730%; final rollout requires at least
  85%/77.9343%/81%.
- Preserve all rejected, merged, reassigned, and quarantined candidate payloads
  in the existing `issues.json/.md` contract.
- GT content remains offline-only. No title-, value-, item-, provider-, or
  model-specific rule may enter production.
- Work in the dirty tree without resetting, cleaning, or overwriting unrelated
  user changes.

## Task 1 — Add promotion contracts with failing tests

Files:

- create `src/knowmat/alpha25/promotion.py`
- create `tests/test_alpha25_promotion.py`

Steps:

1. Add tests for immutable promotion records, stable content IDs, evidence-unit
   provenance, normalized evidence spans, owner candidates, value/condition
   fields, risk codes, and decision enums.
2. Add tests proving IDs ignore candidate order and confidence but change when
   scientific payload, evidence, owner, or condition changes.
3. Add tests for complete `MaterializeIssue`-compatible audits containing the
   original payload, decision rule, evidence, and survivor before/after.
4. Run the focused file and confirm failures before implementation.
5. Implement only the contracts, serialization, deterministic ordering, and
   audit adapter needed to pass this task.

Verification:

`./venv/bin/pytest -o addopts='' tests/test_alpha25_promotion.py -q`

## Task 2 — Build source-block and assertion grouping

Files:

- modify `src/knowmat/alpha25/promotion.py`
- modify `tests/test_alpha25_promotion.py`

Steps:

1. Add tests for prose sentence/list blocks, Markdown table header/row/column
   anchors, exact evidence spans, and contained subspans.
2. Add multi-column table negatives proving one row with six owner columns
   retains six distinct owner/value assertions.
3. Add explicit shared-owner grammar tests such as “A and B both …”.
4. Add cross-paragraph and text-similarity negatives; similar text without one
   source block must not merge.
5. Implement a source index computed once per paper and assertion keys derived
   only from source provenance.
6. Implement exact presentation dedup and complementary record fusion without
   merging conflicting value/unit/condition/origin fields.
7. Emit `promotion_assertion_duplicate_merged` and
   `promotion_richer_assertion_survived` audits.

## Task 3 — Build owner/state graph and no-broadcast routing

Files:

- modify `src/knowmat/alpha25/promotion.py`
- modify `tests/test_alpha25_promotion.py`
- modify `tests/test_alpha25_materialize.py` only where integration behavior is
  asserted

Steps:

1. Add tests for exact aliases, explicit abbreviations, generic/base/state
   relations, orientations, regions, process states, and literature references.
2. Add tests proving a generic fact is not broadcast to multiple child states
   and one child is not collapsed into a base when the source distinguishes it.
3. Add tests for one unique local owner reassignment and ambiguous-owner
   quarantine.
4. Add tests for explicit shared-owner facts and table owner columns remaining
   independent.
5. Implement source-derived graph construction and the documented owner
   precedence; do not use confidence or output order as truth.
6. Emit `promotion_owner_reassigned` or
   `promotion_ambiguous_owner_quarantined` with all candidates and evidence.
7. Mark alias-only owners with no independently promoted fact so the final
   materializer can omit them and audit `promotion_empty_alias_item_removed`.

## Task 4 — Add Structure and Characterization precision gates

Files:

- modify `src/knowmat/alpha25/promotion.py`
- modify `tests/test_alpha25_promotion.py`

Steps:

1. Add tests for named phase/defect/texture/grain/precipitate/pore/interface
   entities and quantitative/categorical features.
2. Add quarantine tests for unknown-entity presence, empty location/region,
   captions/arrows/panel directions, observation-method-only descriptions, and
   generic records dominated by richer records from the same assertion.
3. Add preservation tests for distinct phases, regions, material states,
   conditions, independently reported categorical presence, and separate source
   assertions.
4. Add same-owner and cross-owner long/short/paraphrase duplicate tests.
5. Add Characterization method-alias dedup tests keyed by owner, condition, and
   origin, while preserving distinct observation contexts.
6. Implement the gates and audits without using expert semantic keys or paper
   identities.
7. Verify that all quarantined facts retain full nested entity/feature payloads.

## Task 5 — Add Property and core-tensile promotion gates

Files:

- modify `src/knowmat/alpha25/promotion.py`
- modify `tests/test_alpha25_promotion.py`
- extend `tests/test_alpha25_claim_quality.py` only for shared property
  classification primitives

Steps:

1. Add tests separating material outcomes from mass loaded, powder flow time,
   equipment metadata, specimen dimensions, test controls, and processing
   parameters.
2. Add numeric grounding tests for scalar/range/inequality/uncertainty, same-
   header unit inheritance, table cell binding, and absent versus explicit
   conditions.
3. Add tests proving no condition can be borrowed across samples, rows,
   paragraphs, or unrelated test families.
4. Add YS/UTS/elongation semantic, unit, subtype, owner, state, orientation,
   temperature, specimen, and condition preservation tests.
5. Add conflict-set tests for incompatible values and units; accept only
   existing source-proven precedence and otherwise quarantine.
6. Preserve thresholds, ranges, different elongation subtypes, independent
   assertions, and existing v47 uncertainty/rounding guards.
7. Emit wrong-axis, unbound-condition, owner, conflict, merge, and quarantine
   audits with complete before/after records.

## Task 6 — Integrate deterministic promotion before materialization

Files:

- modify `src/knowmat/nodes/extraction.py`
- modify `src/knowmat/alpha25/materialize.py` only for issue ingestion and any
  narrowly reusable owner/source helpers
- modify `src/knowmat/app_config.py` and `.env.example` only for generic
  promotion feature flags and limits
- modify `tests/test_alpha25_extraction_integration.py`
- modify `tests/test_alpha25_production_safety.py`

Steps:

1. Add `promote_axis_facts(...)` after coverage assertion and before
   `materialize_candidate(...)`.
2. Pass evidence-unit/task provenance collected during the existing extraction
   phases without changing provider prompts or cache identities.
3. Merge promotion audits into existing materialization issues and summary
   timing fields.
4. Default deterministic promotion on only after frozen gates pass; keep an
   explicit rollback flag during development.
5. Add production-safety tests proving GT terms, titles, expected values,
   provider names, and model-name branches are absent.
6. Add integration tests proving `final.json` schema identity, no extra audit
   file, and complete `issues.json/.md` propagation.
7. Run focused and related suites before any corpus replay.

Verification:

- `./venv/bin/pytest -o addopts='' tests/test_alpha25_promotion.py tests/test_alpha25_claim_quality.py tests/test_alpha25_materialize.py -q`
- `./venv/bin/pytest -o addopts='' tests/test_alpha25_extraction_integration.py tests/test_alpha25_production_safety.py tests/test_alpha25_runtime_property_aliases.py -q`

## Task 7 — Deterministic pilot and full frozen regression

Files/artifacts:

- use `scripts/rematerialize_alpha25_tasks.py`
- create new untracked pilot/full output roots
- create deterministic acceptance reports under `reports/`

Steps:

1. Replay papers 001, 006, 007, 012, 019, 025, 029, and 030 from the v47 405-
   cache corpus with zero provider calls.
2. Inspect every changed item, Structure observation, Property, owner, condition,
   and issue against OCR Markdown.
3. Reject or narrow any rule that cannot be explained without GT data.
4. Evaluate the pilot against business GT and adjudicated GPT expert GT.
5. Replay all 30 papers with verifier disabled and record stage timing, claim
   count, issue count, and provider-call count.
6. Compare every design gate, including protected Composition and core tensile.
7. If any deterministic gate fails, keep v47 active and revise generic rules;
   do not proceed to verifier integration on an invalid base.

## Task 8 — Add the bounded risk verifier with failing tests

Files:

- create `src/knowmat/alpha25/risk_verifier.py`
- create `tests/test_alpha25_risk_verifier.py`
- modify `src/knowmat/nodes/extraction.py`
- modify `src/knowmat/app_config.py` and `.env.example`

Steps:

1. Add strict Pydantic contracts for accept, merge, owner reassignment,
   quarantine, conflict, and review decisions.
2. Add tests rejecting unknown candidate/owner IDs, added facts or fields,
   partial group coverage, invalid enums, and invented evidence.
3. Add deterministic compact prompt compilation using only opaque IDs, cited
   evidence, existing owners, structured conflicts, and allowed actions.
4. Add grouping/batching limits: at most four batches and at most 20% of
   extraction-task count per paper, with evidence-character, candidate, and
   output-token ceilings.
5. Reuse the existing provider scheduler and generic capability configuration;
   add no provider/model-name branch.
6. Add content-addressed cache identity using OCR baseline, evidence/candidate/
   owner graph digests, contract/prompt/ruleset versions, and generic LLM
   request identity.
7. On timeout, invalid response, missing decision, or exhausted budget, emit a
   complete audit and quarantine the unresolved high-risk group.
8. Keep verifier disabled by default until live pilot acceptance.

Verification:

`./venv/bin/pytest -o addopts='' tests/test_alpha25_risk_verifier.py tests/test_alpha25_extraction_integration.py tests/test_alpha25_production_safety.py -q`

## Task 9 — Live verifier pilot, frozen replay, and full evaluation

1. Run the stratified pilot with real GLM verifier calls and unchanged frozen
   extraction responses.
2. Audit every verifier decision against source evidence; invalid scientific
   decisions invalidate the corresponding generic risk class.
3. Freeze accepted verifier responses and replay the pilot twice, proving
   byte-identical outputs and audits.
4. Run the full 30-paper bounded-verifier regression only after the pilot gates
   pass.
5. Compare v47, deterministic promotion, bounded-verifier output, business GT,
   and GPT expert GT by global/axis/core-tensile loose and strict metrics.
6. Report actual provider requests, queue/call time, materialization time, total
   LLM-stage wall time, and cache hits.
7. Accept only if every final rollout threshold in the design passes; otherwise
   retain v47 and continue with a generic precision increment.

## Task 10 — Complete regression and handoff

1. Run all Alpha25 materialize, claim-quality, extraction, runtime, production-
   safety, evaluator, CLI, and reporting tests relevant to touched code.
2. Run Python compilation and `git diff --check`.
3. Confirm prompt/schema/ruleset and public `final.json` compatibility.
4. Confirm no GT values, titles, paper IDs, model branches, or private benchmark
   artifacts entered production modules.
5. Write human and machine-readable acceptance reports, per-paper axes CSV,
   adjudication CSV, runtime summary, and deterministic replay evidence.
6. State plainly whether GLM improved, which gates passed, which gaps remain,
   and whether the new version is promotable.

## Expected tracked files

- `src/knowmat/alpha25/promotion.py`
- `src/knowmat/alpha25/risk_verifier.py`
- `src/knowmat/nodes/extraction.py`
- `src/knowmat/alpha25/materialize.py` only if integration requires it
- `src/knowmat/app_config.py`
- `.env.example`
- `tests/test_alpha25_promotion.py`
- `tests/test_alpha25_risk_verifier.py`
- focused existing Alpha25 integration/safety tests
- this plan and the approved design

Pilot, full-run, cache, determinism, and evaluation outputs remain untracked
under existing `data/` and `reports/` conventions.

## Rollback boundary

Keep v47 as the production baseline until the complete deterministic and
bounded-verifier gates pass. Each stage is independently feature-gated. A
failed verifier or metric must not weaken evidence requirements, enable broad
acceptance, or silently discard audit records. Rollback disables promotion or
verifier execution without changing frozen extraction caches or historical
outputs.
