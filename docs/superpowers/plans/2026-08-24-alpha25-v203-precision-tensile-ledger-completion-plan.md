# Alpha25 v203 precision-first tensile ledger implementation plan

## Goal

Implement the approved v203 design on top of the frozen, accepted v202 output.
Increase global loose F1 and Target core-tensile recall/F1 without reducing the
approved precision floors, changing upstream extraction, or adding provider
calls.  Improve owner/condition attribution only when one source coordinate
proves the decision.

Authoritative design:
`docs/superpowers/specs/2026-08-24-alpha25-v203-precision-tensile-ledger-completion-design.md`.

## Guardrails

- Do not modify prompts, model/provider configuration, OCR/VLM/chart
  generation, Alpha25 schemas, frozen task responses, or `final.json` shape.
- Production code must not read GT, paper IDs/titles, expected values/counts,
  provider names, or model names.
- A GT-unmatched fact is not deletion evidence.  Recover, enrich, merge, or
  quarantine only from a unique local source coordinate.
- Preserve all existing unrelated dirty-worktree changes.
- Edit source files only with `apply_patch`; reread every target before editing.
- Run every pytest command with `-o addopts=''`.
- Every public-output mutation must have a complete deterministic
  `quality_audit.json` record and concise issue code.

## Task 1: Add v203 protocol-ledger contracts and parser

Files:

- Modify `src/knowmat/alpha25/property_context.py`.
- Modify `tests/test_alpha25_materialize.py` or create a focused protocol-ledger
  test module if isolation materially improves readability.

Steps:

1. Add failing tests for immutable paper-local protocol events carrying role,
   owner/state/orientation scope, test family, temperature, rate type/value,
   machine, standard, specimen geometry, environment, hold time, and replicate
   count with literal evidence spans.
2. Add positive tests for `owner_local`, explicit `target_global`, and
   `reference_local` scopes.
3. Add fail-closed tests for two compatible events, Reference/Target leakage,
   state temperature mistaken for test temperature, crosshead speed mistaken
   for strain rate, conflicting existing dimensions, and unresolved
   `respectively` mappings.
4. Introduce focused immutable ledger/event/decision records.  Reuse existing
   condition discriminators where safe, but keep each dimension separate until
   final serialization.
5. Build events only from one bounded method assertion/paragraph/table scope.
   Preserve literal evidence and stable decision keys.
6. Bind only missing compatible dimensions; never overwrite a literal existing
   condition.  Return explicit `bound`, `ambiguous`, `conflict`, `reference`,
   `ineligible`, or `disabled` decisions.
7. Prove decision/audit stability under input-order permutations.

Verification:

- `pytest -q -o addopts='' <focused protocol-ledger tests>`
- `pytest -q -o addopts='' tests/test_alpha25_materialize.py -k 'test_context or protocol or v203'`

## Task 2: Add bounded dense Target tensile-table enumeration

Files:

- Modify `src/knowmat/alpha25/source_coordinates.py`.
- Modify `tests/test_alpha25_source_coordinates.py`.

Steps:

1. Add tests for Markdown and HTML tables with multi-level headers,
   `rowspan`/`colspan`, explicit Target owner/state/orientation, YS/UTS/elongation
   headers, units, scalar values, uncertainty, and ranges.
2. Add mandatory no-op tests for citation-only Reference cells, missing units,
   caption-only semantics, conflicting row/column owners, ambiguous merged
   headers, repeated values without unique cells, prose values, malformed
   numeric cells, and continuous curve/sidecar data.
3. Add immutable dense-cell records containing table block, logical row/column,
   property, unit, owner, state, orientation, value, source rows, and stable
   coordinate key.
4. Enumerate only explicit core-tensile cells from the already bounded paper
   source.  Resolve exactly one Target owner and never infer a property, unit,
   value, state, or orientation from a caption alone.
5. Return accepted and reason-coded rejected decisions; never select the first
   ambiguous coordinate.
6. Verify deterministic results under table and input-record permutations.

Verification:

- `pytest -q -o addopts='' tests/test_alpha25_source_coordinates.py -k 'dense or v203'`
- `pytest -q -o addopts='' tests/test_alpha25_source_coordinates.py`

## Task 3: Integrate dense completion into materialization

Files:

- Modify `src/knowmat/alpha25/materialize.py`.
- Modify `tests/test_alpha25_materialize.py`.

Steps:

1. Add `KNOWMAT2_ALPHA25_DENSE_TENSILE_TABLE_COMPLETION_V203`, default-on and
   independently shadowable.
2. Add failing tests proving an eligible dense cell becomes one ordinary
   Target Property with its exact owner/state/orientation/value/unit and source
   coordinate.
3. Add tests proving a pre-existing fact owns the coordinate and prevents a
   duplicate, two possible Target bases fail closed, and Reference cells remain
   on existing Reference paths.
4. Convert eligible cells into ordinary input facts before the existing v202
   coordinate gate.  Do not bypass evidence, owner, role, protocol,
   deduplication, or sanitization.
5. Emit complete `dense_tensile_table_cell_recovered` and
   `dense_tensile_table_cell_rejected` audit rows with before/after, coordinate,
   candidates, source rows, rationale, and stable decision key.
6. Confirm continuous line-chart sidecars remain mandatory no-ops.

Verification:

- `pytest -q -o addopts='' tests/test_alpha25_materialize.py -k 'dense_tensile or v203'`

## Task 4: Integrate protocol ledger and precision quarantine

Files:

- Modify `src/knowmat/alpha25/materialize.py`.
- Modify `src/knowmat/alpha25/claim_quality.py` or
  `src/knowmat/alpha25/promotion.py` only if the existing materialization
  boundary cannot express a required coordinate decision.
- Modify focused tests for every touched module.

Steps:

1. Add `KNOWMAT2_ALPHA25_TENSILE_PROTOCOL_LEDGER_V203` and
   `KNOWMAT2_ALPHA25_PROPERTY_COORDINATE_QUARANTINE_V203`, default-on and
   independently shadowable.
2. Bind ledger dimensions after owner/state/orientation resolution and before
   Property sanitization.  Serialize through the existing `Test_Condition`
   field only.
3. Emit `tensile_protocol_ledger_bound` with the literal contributed
   dimensions and complete event/decision payload.  Emit
   `tensile_protocol_ledger_ambiguous` as a no-op review record.
4. Add coordinate gates for cross-owner projection, cross-cell projection,
   numeric semantic projection, role/protocol leakage, explicit coordinate
   conflict, and exact same-coordinate duplicate.
5. Merge only exact same-coordinate duplicates into the richest grounded
   survivor.  Quarantine other proven errors from formal Properties without
   guessing replacements.
6. Emit every reason code required by the design with full before/after and
   source evidence.  Do not add broad unmatched filtering to any axis.
7. Add regression tests proving source-supported GT-unmatched tensile facts are
   retained and Composition is untouched.

Verification:

- `pytest -q -o addopts='' tests/test_alpha25_materialize.py -k 'v203 or protocol_ledger or coordinate'`
- Run complete tests for every modified Alpha25 module.

## Task 5: Plumb switches, metadata, and v202 compatibility

Files:

- Modify `scripts/rematerialize_alpha25_tasks.py`.
- Modify direct offline/live caller tests if repository search shows the same
  metadata contract elsewhere.
- Modify `.env.example` only if this repository's existing switch convention
  requires documentation there; do not modify the user's real `.env`.

Steps:

1. Record all three v203 switch states in per-paper and run summary metadata.
2. Ensure offline materialization uses the explicit paper source directory and
   cannot reach a provider client.
3. Add a switches-off test: the frozen v202 inputs reproduce v202 output bytes.
4. Add malformed/missing source tests that fail closed locally without
   producing unaudited facts.
5. Verify no prompt/schema/frozen-response file changes enter the implementation
   diff.

Verification:

- Focused script/CLI tests with `-o addopts=''`.
- Compare frozen prompt/schema/task-response hashes to v202.

## Task 6: Focused regression and source-audited pilot

Steps:

1. Run all focused v203 tests and complete test files touched by the call chain.
2. Run all Alpha25 tests plus schema, CLI, OCR-manifest, and evaluator tests
   used by the v202 acceptance.
3. Rematerialize a bounded pilot containing the diagnosed protocol gaps, dense
   Target tables, citation-heavy Reference data, and a continuous-chart
   negative control, with provider access disabled.
4. Inspect every changed Property against its source coordinate and audit row.
5. Narrow or disable the responsible switch if any owner, role, state,
   orientation, value, unit, or protocol decision is unsupported.

Verification:

- No API/provider call.
- No continuous curve point promoted.
- Every delta has one stable audit decision.
- Composition is byte-identical to v202 for pilot papers.

## Task 7: Thirty-paper dual-GT acceptance and determinism

Steps:

1. Rematerialize all 30 frozen papers into a new v203 output root; require
   30/30, fatal=0, silent-empty=0, and API=0.
2. Run the frozen GPT expert and business GT evaluators without matcher or GT
   changes.
3. Enforce every metric threshold in the design, including global/core matched
   counts, precision floors, higher recall/F1, wrong-owner/condition conflicts,
   and direct business core-tensile F1.
4. Compare Composition payloads byte-for-byte across 30/30 papers.
5. Replay into a second output root and require byte-identical `final.json`,
   `quality_audit.json`, and summaries.
6. Require mean rematerialization runtime regression no greater than 20% versus
   the accepted v202 replay.
7. Produce a machine-readable comparison, per-paper/axis CSV, adjudication
   ledger, and concise acceptance report linking every semantic delta to audit
   codes.
8. If a gate fails, leave the responsible switch narrowed or disabled and
   report the measured blocker.  Do not weaken thresholds or alter evaluator
   inputs.

## Task 8: Code review and repository regression

Steps:

1. Review the implementation diff for source grounding, ambiguity behavior,
   audit completeness, deterministic iteration, path safety, hard-coded
   paper/value/model artifacts, and unrelated edits.
2. Run `git diff --check` on the implementation files.
3. Run the full repository suite with `pytest -q -o addopts=''` after focused
   suites pass.
4. Distinguish any pre-existing external-fixture failure from a changed test,
   and never claim a clean full suite without exact evidence.
5. Commit only the intended v203 implementation/test/report artifacts; preserve
   all user changes.

## Completion evidence

Completion requires all deliverables and gates from the design, not merely
passing unit tests.  The authoritative evidence is the committed source/tests,
focused/full pytest output, frozen-input hashes, two byte-identical 30-paper
replays, zero-API run metadata, source-audited delta ledger, Composition byte
comparison, dual-GT metrics, runtime measurement, and final acceptance report.
