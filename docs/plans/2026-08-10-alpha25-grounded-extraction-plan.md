# Alpha25 Grounded Extraction Execution Plan

**Goal:** Replace the paper-specific alpha6 extraction path with a generic,
evidence-gated alpha25 pipeline, run one fresh local OCR baseline for 30 PDFs,
iterate LLM-only extraction, and publish a source-aware GT and performance report.

**Architecture:** KnowMat creates and freezes a fresh OCR manifest, compiles a
compact alpha25 candidate prompt, plans axis-scoped evidence tasks, rejects facts
without literal OCR support, reconciles facts generically, invokes alpha25's
deterministic normalizer/validator, and evaluates final outputs against GT only in
an offline script.

**Tech Stack:** Python 3.12, Pydantic, LangChain/OpenAI-compatible chat models,
pytest, JSON Schema, existing KnowMat OCR and CLI infrastructure.

---

## Task 1: Establish the alpha25 package adapter and prompt source of truth

**Files:**

- Create: `src/knowmat/alpha25/package.py`
- Create: `src/knowmat/alpha25/prompt_compiler.py`
- Create: `src/knowmat/alpha25/__init__.py`
- Modify: `src/knowmat/app_config.py`
- Modify: `src/knowmat/prompt_loader.py`
- Modify: `src/knowmat/prompt_generator.py`
- Modify: `.env.example`
- Modify: `tests/test_prompt_templates.py`
- Create: `tests/test_alpha25_package.py`

**Interfaces:**

- Produces: validated alpha25 package metadata, schema/ruleset identity, compiled
  system prompt, axis-task user prompt, prompt hash.
- Consumes: checked-in `material-extractor-alpha25-20260804/material-extractor`.

**Steps:**

1. Add one configurable alpha25 package-root setting with the checked-in package as
   the default; do not retain an alpha6 fallback in the accepted production path.
2. Validate deployment metadata, schema ID, ruleset manifest, and required files at
   startup. Error messages must identify the missing or mismatched artifact.
3. Compile a compact candidate prompt from alpha25's binding v11.3.3 constraints and
   relevant overlays. Exclude conflicting legacy normalized-output examples such as
   `Processing.Equipment` and `Key_Params`.
4. Pin source prompt hashes and required safety clauses so package drift fails tests.
5. Ensure prompt generation accepts an axis, evidence-unit text, routing, and
   source-derived sample anchors without accepting GT or filename hints.

**Verification:**

Run: `./venv/bin/pytest -q tests/test_alpha25_package.py tests/test_prompt_templates.py`

Expected: alpha25 resolves successfully, alpha6 paths are absent from generated
prompts, conflicting legacy shapes are absent, and required evidence rules remain.

---

## Task 2: Define compact candidate fact contracts and strict evidence validation

**Files:**

- Create: `src/knowmat/alpha25/contracts.py`
- Create: `src/knowmat/alpha25/evidence.py`
- Modify: `src/knowmat/extractors.py`
- Create: `tests/test_alpha25_contracts.py`
- Create: `tests/test_alpha25_evidence.py`

**Interfaces:**

- Produces: Pydantic contracts for inventory anchors and axis facts; evidence gate
  result with accepted facts and machine-readable rejection issues.
- Consumes: OCR evidence-unit IDs/text and raw model JSON.

**Steps:**

1. Model inventory anchors separately from Composition, Processing, Structure,
   Characterization, and Properties fact fragments.
2. Preserve alpha25 nullable requirements, ranges, inequalities, standard deviation,
   source origin, and raw evidence without emitting final canonical values.
3. Implement deterministic evidence normalization limited to Unicode compatibility,
   whitespace/line-break joining, soft-hyphen removal, and dash/micro-symbol variants.
4. Validate evidence only against the assigned unit plus explicitly attached shared
   context. Reject paraphrases and model-created table labels.
5. Materialize table evidence deterministically from OCR headers, selected row/cells,
   units, caption, and footnotes.

**Verification:**

Run: `./venv/bin/pytest -q tests/test_alpha25_contracts.py tests/test_alpha25_evidence.py`

Expected: exact/OCR-normalized evidence passes, paraphrases fail, and no repair adds
a fact or evidence quote.

---

## Task 3: Build generic evidence units, item inventory, axis tasks, and coverage ledger

**Files:**

- Create: `src/knowmat/alpha25/planner.py`
- Create: `src/knowmat/alpha25/coverage.py`
- Modify: `src/knowmat/nodes/extraction.py`
- Create: `tests/test_alpha25_planner.py`
- Create: `tests/test_alpha25_coverage.py`
- Modify: `tests/test_v11_llm_compat.py`

**Interfaces:**

- Produces: source line map, bounded prose/table/caption evidence units, generic item
  registry, axis tasks, retry children, complete/incomplete coverage state.
- Consumes: enriched OCR Markdown and compact alpha25 prompts/contracts.

**Steps:**

1. Assign stable line IDs and split prose on headings/paragraphs without losing text.
2. Split tables by sample columns and bounded row groups while retaining caption,
   headers, units, footnotes, and nearby context.
3. Run one lightweight inventory call per bounded source region only when deterministic
   source labels are insufficient. Inventory emits identity anchors, never four-axis
   facts.
4. Plan axis-scoped calls and calculate output budgets from task kind and maximum
   record capacity. Remove full four-axis item generation from each chunk.
5. Record every planned unit, attempt, accepted/rejected result, retry child, cache
   hit, and merge result in the coverage ledger.
6. Split invalid/empty/truncated/evidence-empty tasks once. Fail or flag a paper when
   any leaf remains unrecovered; never merge partial coverage as complete.

**Verification:**

Run: `./venv/bin/pytest -q tests/test_alpha25_planner.py tests/test_alpha25_coverage.py tests/test_v11_llm_compat.py`

Expected: dense tables are pre-split, task output is axis-scoped, retries are bounded,
and missing coverage cannot report success.

---

## Task 4: Replace sample-specific reconciliation with generic fact reconciliation

**Files:**

- Replace: `src/knowmat/v11_reconcile.py`
- Create: `src/knowmat/alpha25/materialize.py`
- Modify: `tests/test_v11_reconcile.py`
- Create: `tests/test_alpha25_materialize.py`

**Interfaces:**

- Produces: reconciled evidence-backed facts and complete alpha25 candidate documents
  with stable IDs and required empty containers.
- Consumes: accepted inventory anchors and axis facts from all completed tasks.

**Steps:**

1. Group item identities using source aliases, material identity, role, data nature,
   state, composition discriminator, process discriminator, and orientation evidence.
2. Preserve ambiguous groups and emit review issues instead of guessing.
3. Deduplicate with axis-specific raw fact signatures including condition and evidence.
4. Union duplicate evidence and preserve conflicting raw facts as separate records.
5. Assign stable item/observation/stage/property IDs only after reconciliation.
6. Remove title-, alloy-, process-, wall-, delay-, and sample-ID-specific branches.

**Verification:**

Run: `./venv/bin/pytest -q tests/test_v11_reconcile.py tests/test_alpha25_materialize.py`

Expected: aliases merge only with compatible evidence, variants stay separate, no
facts disappear due to count caps, and repository-specific paper/sample literals are
absent from production reconciliation.

---

## Task 5: Replace the paper-specific normalizer with a thin alpha25 runner

**Files:**

- Replace: `src/knowmat/nodes/v11_normalize.py`
- Create: `tests/test_alpha25_normalize.py`
- Modify: `src/knowmat/orchestrator.py`
- Modify: `src/knowmat/report_writer.py`

**Interfaces:**

- Produces: alpha25 normalized JSON, validation issues, run metadata, promotability.
- Consumes: materialized evidence-first candidate and its source OCR path.

**Steps:**

1. Reduce `v11_normalize.py` to generic metadata preparation, candidate persistence,
   alpha25 `run_v11.py` invocation, and result loading.
2. Pass the frozen OCR Markdown to alpha25 so locators and evidence expansion use the
   current baseline.
3. Propagate fatal/review counts and coverage state into reports and final status.
4. Refuse promotion on fatal alpha25 validation or incomplete task coverage.
5. Delete all functions that synthesize or prune known samples, experiment matrices,
   properties, compositions, structures, or stages.

**Verification:**

Run: `./venv/bin/pytest -q tests/test_alpha25_normalize.py tests/test_v11_reporting.py`

Expected: fixture candidates normalize through alpha25, fatal/incomplete results are
not promotable, and no paper-specific transform remains.

---

## Task 6: Add fresh OCR baseline manifest and freeze enforcement

**Files:**

- Create: `src/knowmat/ocr_manifest.py`
- Modify: `src/knowmat/__main__.py`
- Modify: `src/knowmat/batch/ocr_dispatcher.py`
- Create: `tests/test_ocr_manifest.py`
- Modify: `tests/test_alignment/test_mineru_pipeline.py`

**Interfaces:**

- Produces: versioned manifest with PDF/OCR/parser hashes, backend identity, status,
  timestamps, and a stable baseline ID.
- Consumes: the 30 `data/raw/*.pdf` files and locally generated OCR artifacts.

**Steps:**

1. Write manifest records only after each OCR Markdown/parser artifact is complete and
   non-empty.
2. Add a command option to freeze/verify a named OCR baseline without rerunning OCR.
3. Extraction verifies PDF and OCR hashes against the selected manifest before LLM
   calls. Changed/missing artifacts fail clearly.
4. Preserve existing OCR behavior outside the opt-in baseline workflow.
5. Document the exact first-pass OCR command and subsequent LLM-only command.

**Verification:**

Run: `./venv/bin/pytest -q tests/test_ocr_manifest.py tests/test_alignment/test_mineru_pipeline.py`

Expected: 30-record manifests validate, mutation is detected, incomplete OCR cannot
freeze, and LLM-only reuse does not invoke OCR.

---

## Task 7: Implement offline source-aware GT and performance evaluation

**Files:**

- Create: `scripts/evaluate_alpha25_gt.py`
- Create: `src/knowmat/evaluation/alpha25_gt.py`
- Create: `src/knowmat/evaluation/__init__.py`
- Create: `tests/test_alpha25_gt_evaluation.py`

**Interfaces:**

- Produces: JSON and Markdown reports with supported/unsupported GT evidence, semantic
  item matching, per-axis precision/recall/F1, disagreement classes, and performance.
- Consumes: frozen OCR manifest, final output directory, and GT directory only after
  extraction is complete.

**Steps:**

1. Audit every GT fact's evidence against the frozen OCR and classify it as supported,
   format mismatch, unsupported, or ambiguous.
2. Match items using evidence-supported identity/composition/process/state signals,
   not exact generated IDs.
3. Compare raw and normalized Composition, Processing, Structure, Characterization,
   Properties, and core tensile facts.
4. Report extraction misses, source-supported extras, semantic ambiguity, and likely
   GT defects separately.
5. Assert by tests and import scans that production modules do not depend on this
   evaluator or accept a GT path.

**Verification:**

Run: `./venv/bin/pytest -q tests/test_alpha25_gt_evaluation.py`

Expected: synthetic matches/disagreements are classified correctly and GT remains
offline-only.

---

## Task 8: Run full automated regression and production-safety scans

**Files:**

- Modify: `tests/test_v11_reporting.py`
- Modify: `tests/test_prompt_templates.py`
- Create: `tests/test_alpha25_production_safety.py`
- Modify: `prompts/README.md`

**Interfaces:**

- Produces: green focused/full test results and static evidence that the production
  path is generic and GT-independent.
- Consumes: Tasks 1-7.

**Steps:**

1. Add static scans for GT imports/paths and reviewed title/sample literals in the
   alpha25 production modules.
2. Add end-to-end stub integration tests covering dense tables, ranges,
   inequalities, standard deviations, references, ambiguous aliases, equipment,
   and failed coverage.
3. Verify all cache identities include OCR baseline, prompt, task, schema/ruleset,
   model endpoint, response mode, budget, and thinking mode.
4. Run focused tests, then the full repository suite; distinguish pre-existing
   unrelated failures from regressions with exact evidence.

**Verification:**

Run: `./venv/bin/pytest -q`

Expected: all relevant alpha25 and existing extraction/OCR tests pass; production
safety scans find no GT dependency or paper-specific branch.

---

## Task 9: Create one fresh OCR baseline and run the 30-paper LLM/GT iteration

**Files/Artifacts:**

- Create: `data/interim/ocr-baselines/alpha25-20260810/manifest.json`
- Create: versioned `data/output/alpha25-*` extraction directories
- Create: versioned `reports/alpha25-*` JSON/Markdown comparison reports

**Interfaces:**

- Produces: fresh OCR baseline, development/validation/final extraction outputs, GT
  comparison report, and performance report.
- Consumes: Tasks 1-8, 30 PDFs, configured OCR/model credentials.

**Steps:**

1. Confirm exactly 30 input PDFs and no existing title-matched OCR directories are
   selected as the new baseline.
2. Run the local OCR-only command once for all 30 papers and freeze the manifest.
3. Establish a no-GT extraction baseline on a small development subset.
4. Iterate prompt/task parameters only on the deterministic 20-paper development
   split, always reusing the frozen OCR and evidence-task cache as appropriate.
5. Freeze the candidate implementation and run the 10-paper validation split once.
6. If hard gates pass, run all 30 papers once with the frozen implementation.
7. Run offline GT evaluation and verify truth, similarity, coverage, and performance
   acceptance criteria from the design.
8. If criteria fail, diagnose by disagreement category, make only generic changes,
   rerun affected LLM tasks, and repeat validation without rerunning OCR.

**Verification:**

Run the documented OCR-only, LLM-only, and evaluator commands from the final
implementation.

Expected: 30/30 fresh OCR records, 30/30 schema-valid promoted outputs with complete
coverage and grounded facts, accepted GT similarity goals, median LLM-only time at
most five minutes, P90 at most eight minutes, no normal output truncation, and retry
amplification at most 10%.

---

## Parallel Execution Groups

> Tasks within a wave have non-overlapping primary files and no unresolved interface
> dependency. Waves are sequential.

- **Wave 1:** Task 1 (package/prompt adapter), Task 2 (contracts/evidence), Task 6
  (OCR manifest), Task 7 (offline evaluator skeleton).
- **Wave 2:** Task 3 (planner/extraction) and Task 4 (generic reconciliation), both
  consuming the Wave 1 contracts.
- **Wave 3:** Task 5 (alpha25 normalization/reporting), consuming materialized
  candidates and package adapter.
- **Wave 4:** Task 8 (full regression/safety scans).
- **Wave 5:** Task 9 (fresh OCR and live LLM/GT iteration).

## Consistency Check

- Fresh local OCR exactly once is Task 6 plus Task 9; supplied OCR is not reused.
- Alpha25 prompt/schema/rules are Task 1 and Task 5.
- Axis-scoped extraction and performance control are Tasks 2-3.
- Evidence truth gate is Task 2 and enforced again in Tasks 3-5 and 8.
- Cross-chunk loss and paper-specific hardcoding are removed by Tasks 3-5.
- GT is offline-only in Task 7 and statically enforced in Task 8.
- Development/frozen validation/full-30 iteration and performance acceptance are
  Task 9.
- No design requirement is deferred or downgraded.
