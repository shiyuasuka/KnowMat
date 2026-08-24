# Alpha25 v202 source-coordinate tensile convergence implementation plan

## Goal

Implement the approved v202 source-coordinate recovery and precision gates on
top of the frozen GLM-5.2 v201 task responses.  The implementation must recover
uniquely grounded tensile facts without changing prompts, Alpha25 schemas,
OCR/VLM/chart generation, provider calls, Composition, or the public
`final.json` shape.

## Guardrails

- Production code may not read GT, paper IDs/titles, expected values, provider
  names, or model names.
- Every new decision is deterministic, fail-closed, and fully represented in
  the existing materialization audit path.
- Sidecar paths are resolved only below an explicit per-paper `source_dir`.
- Continuous `series,kind,x,y` curves are always no-ops.
- All edits are restricted to focused Alpha25 modules, runner plumbing, and
  tests. Existing unrelated worktree changes are preserved.

## Task 1: Add a source-coordinate module with logical table parsing

Files:

- Create `src/knowmat/alpha25/source_coordinates.py`.
- Create `tests/test_alpha25_source_coordinates.py`.

Steps:

1. Write failing tests for HTML tables with multi-row headers,
   `rowspan`/`colspan`, unique data cells, and retained physical source rows.
2. Add equivalent Markdown-table coverage.
3. Add fail-closed tests for repeated compatible cells, conflicting row and
   column owners, missing property units, reordered cells, and duplicate table
   blocks.
4. Implement immutable coordinate records containing table/block locator,
   logical row/column, header path, owner path, value cell, original rows, and
   a stable decision key.
5. Parse HTML with the standard library only; expand spans into a logical grid
   while retaining the original cell locator and text. Parse Markdown tables
   into the same representation.
6. Implement exact normalized cell/value matching and property/unit/owner
   compatibility checks. Return explicit matched, ambiguous, or unsupported
   decisions; never select the first of several matches.
7. Verify deterministic output under record/source iteration permutations.

## Task 2: Extend evidence recovery to structured table cells

Files:

- Modify `src/knowmat/alpha25/evidence.py`.
- Modify `tests/test_alpha25_evidence.py`.

Steps:

1. Add a failing evidence-gate test matching the paper_003 failure class: the
   candidate carries a synthetic multi-level header path plus a cropped data
   row, neither of which alone is a literal physical row.
2. Add negative tests for an ambiguous header path and correct value under the
   wrong owner.
3. Behind `KNOWMAT2_ALPHA25_STRUCTURED_TABLE_CELL_RECOVERY_V202`, invoke the
   logical coordinate resolver only after literal grounding and the v201 row
   projection both fail.
4. Recover only existing Property candidates whose owner and structured value
   resolve to one coordinate. Preserve v201 behavior when the switch is off.
5. Emit `evidence_structured_table_cell_recovered` with the complete coordinate
   decision; emit `evidence_structured_table_cell_ambiguous` for review while
   leaving the candidate rejected.
6. Run focused evidence and coordinate tests.

## Task 3: Implement bounded discrete sidecar discovery and parsing

Files:

- Extend `src/knowmat/alpha25/source_coordinates.py`.
- Extend `tests/test_alpha25_source_coordinates.py`.

Steps:

1. Write a positive test for a small CSV with state, orientation, yield
   strength, UTS, and elongation columns.
2. Write mandatory no-op tests for continuous `series,kind,x,y`, sampled
   trajectories, oversized row/column/cell shapes, duplicate headers, missing
   units, malformed/nonnumeric cells, and missing condition labels.
3. Write filesystem-safety tests for missing files, traversal, absolute paths,
   symlinks escaping `source_dir`, and references not present literally in the
   Markdown.
4. Resolve exactly one literal `data_csv:` reference, require a regular file
   below `source_dir`, hash the bytes, and parse without injecting content into
   any prompt.
5. Enforce caps of 32 data rows, 12 columns, and 192 non-empty data cells.
6. Recognize only explicit core-tensile headers with units and exact numeric
   cells. Return immutable sidecar coordinates and reason-coded no-op decisions.

## Task 4: Promote eligible sidecar rows with separate attribution dimensions

Files:

- Modify `src/knowmat/alpha25/materialize.py`.
- Modify `tests/test_alpha25_materialize.py`.

Steps:

1. Add failing materialization tests proving one unique Target base can own
   source-literal state/orientation rows, while two possible bases are a no-op.
2. Add tests separating heat-treatment state, specimen orientation, tensile
   temperature, and Target/Reference role.
3. Add tests proving Reference cells do not inherit a Target protocol and a
   discrete row cannot be broadcast across owners.
4. Add optional `source_dir: Path | None` to `materialize_candidate`; keep all
   existing callers source-compatible.
5. Behind `KNOWMAT2_ALPHA25_DISCRETE_CHART_SIDECAR_V202`, convert eligible
   sidecar cells into ordinary Alpha25 Property facts using only literal CSV
   row/header/unit evidence and one unique owner decision.
6. Behind `KNOWMAT2_ALPHA25_OWNER_STATE_CONDITION_V202`, bind base owner, state,
   orientation, role, and test condition as independent fields before ordinary
   materialization. Do not create a child owner from a caption-only label.
7. Record every created fact or owner as `discrete_chart_property_recovered` or
   `source_literal_owner_state_recovered`, including literal row, file hash,
   coordinate, candidates, before/after, and stable decision key.
8. Record rejected eligible-looking sidecars as
   `discrete_chart_sidecar_rejected`; record continuous inputs as
   `continuous_curve_sidecar_not_promoted` without producing Properties.

## Task 5: Apply coordinate precision and protocol gates

Files:

- Modify `src/knowmat/alpha25/materialize.py` and, only where the existing
  promotion boundary requires it, `src/knowmat/alpha25/promotion.py`.
- Extend `tests/test_alpha25_materialize.py` and
  `tests/test_alpha25_promotion.py`.

Steps:

1. Add tests for same-cell duplicate candidates, same assertion projected onto
   multiple axes, Target/Reference conflicts, owner/state/value/unit conflicts,
   and compatible partial tensile protocols.
2. Behind `KNOWMAT2_ALPHA25_SOURCE_COORDINATE_PRECISION_V202`, allow one
   scientific source coordinate to produce one owner/axis fact unless the
   source explicitly declares shared ownership.
3. Merge exact same-coordinate table/prose copies into one richer survivor;
   quarantine rather than rewrite explicit conflicts.
4. Bind test family, temperature, rate, machine, standard, geometry,
   orientation, environment, hold time, and replicate count only from a
   compatible bounded method event.
5. Emit complete `source_coordinate_duplicate_quarantined`,
   `source_coordinate_conflict_quarantined`, and
   `tensile_protocol_coordinate_recovered` audit records.
6. Verify no generic Structure/Characterization deletion is introduced.

## Task 6: Plumb explicit source directories and switch metadata

Files:

- Modify `scripts/rematerialize_alpha25_tasks.py`.
- Modify `scripts/run_frozen_alpha25_extraction.py` and any direct live caller
  found by repository search.
- Extend the corresponding script/CLI tests.

Steps:

1. Pass `source_path.parent` explicitly into materialization in cached
   rematerialization.
2. Pass the copied paper-local `txt_parse` directory in frozen/live execution;
   never infer it from the workspace root.
3. Record the four v202 switch states in run/coverage metadata.
4. Add tests showing switches-off reproduces v201 behavior and invalid source
   directories are local no-ops rather than paper-fatal errors.
5. Confirm no provider client is reachable from rematerialization.

## Task 7: Focused and repository regression tests

Commands:

1. `pytest -q tests/test_alpha25_source_coordinates.py`
2. `pytest -q tests/test_alpha25_evidence.py`
3. Run focused materialize/promotion tests selected by `-k v202` while
   iterating, then the complete two files.
4. Run all `tests/test_alpha25_*.py` plus package/CLI/evaluator tests touched by
   the call-chain.
5. Run the full repository suite if the focused suites pass.
6. Compare prompt and schema file hashes to the v201 baseline and confirm no
   prompt/schema diff was introduced by v202.

## Task 8: Pilot replay and semantic audit

Use only frozen v201 task responses and disable provider access.

1. Replay the complex Target table, categorical sidecar, and cited Reference
   table papers identified in the design.
2. Add the fatigue/global-protocol and continuous-curve negative-control papers.
3. Review every changed `final.json` record against its v202 audit entry and
   source coordinate.
4. Narrow or disable the responsible switch if any wrong owner, wrong role,
   wrong state, cross-cell projection, or curve-point promotion appears.

## Task 9: Thirty-paper A/B, dual-GT evaluation, and determinism

1. Rematerialize all 30 frozen papers with v202 gates on; require 30/30,
   fatal=0, silent-empty=0, and zero API calls.
2. Compare against the adjudicated GPT expert ledger and business GT using the
   frozen one-to-one evaluators without changing matcher rules.
3. Enforce the exact metric thresholds in the approved design, including
   global/core-tensile matched counts, precision, recall/F1, owner/condition
   conflicts, and no lost v201 matches.
4. Compare Composition sections byte-for-byte across all 30 papers.
5. Replay v202 into a second output root and compare `final.json`,
   `quality_audit.json`, and run summary bytes.
6. Measure rematerialization time against v201 and require no more than 20%
   regression.
7. Produce a concise acceptance report with all semantic deltas linked to audit
   codes. If a gate fails, leave the corresponding v202 switch disabled or
   narrowed and report the measured blocker rather than weakening evaluation.

