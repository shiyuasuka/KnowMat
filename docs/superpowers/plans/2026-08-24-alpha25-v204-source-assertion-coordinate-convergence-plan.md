# Alpha25 v204 source-assertion coordinate convergence implementation plan

## Goal

Implement the approved v204 design on top of accepted v203.  Recover only
source-literal core-tensile assertions, enforce one source coordinate per
owner/condition tuple, and improve protocol binding without reducing precision
or changing Composition, prompts, upstream responses, or the public schema.

Authoritative design:
`docs/superpowers/specs/2026-08-24-alpha25-v204-source-assertion-coordinate-convergence-design.md`.

## Guardrails

- Do not modify prompts, model/provider configuration, OCR/VLM/chart output,
  frozen task responses, Alpha25 schemas, or `final.json` shape.
- Production code must not read GT, matcher output, paper identities, expected
  values/counts, providers, or model names.
- Do not treat a GT-unmatched fact as a hallucination or deletion signal.
- Do not modify Composition routing, normalization, filtering, or output.
- Preserve all unrelated dirty-worktree changes.  Stage and commit only v204
  whitelist files.
- Edit source files with `apply_patch` and run pytest with `-o addopts=''`.
- Every output mutation must have a complete deterministic audit row.

## Task 1: Add immutable tensile assertion-coordinate contracts

Files:

- Modify `src/knowmat/alpha25/source_coordinates.py`.
- Modify `tests/test_alpha25_source_coordinates.py`.

Steps:

1. Add failing tests for a source-literal coordinate containing source block,
   span, owner, role, state, orientation, property, value, unit, condition,
   assertion type, stable coordinate key, and stable decision key.
2. Add positive tests for one-owner YS/UTS/EL bundles, uncertainty and
   approximation preservation, exact shared-unit scoping, and input-order
   determinism.
3. Add immutable coordinate and decision dataclasses with deterministic
   `to_dict()` output.  Reuse existing logical-table and numeric-normalization
   helpers where their contracts are already strict enough.
4. Parse only bounded source blocks and emit accepted plus reason-coded rejected
   decisions.  Keep exact evidence rather than synthesized prose.
5. Prove that invalid values, missing units, property/value cardinality
   mismatch, plot references, continuous sidecars, and caption-only assertions
   produce no accepted coordinate.

Verification:

- `./venv/bin/pytest -q -o addopts='' tests/test_alpha25_source_coordinates.py -k 'assertion_coordinate or v204'`

## Task 2: Add ordered-owner and continuation coordinates

Files:

- Modify `src/knowmat/alpha25/source_coordinates.py`.
- Modify `tests/test_alpha25_source_coordinates.py`.

Steps:

1. Add failing tests for explicit two-owner/two-value order, literal
   `respectively`, multiple properties per owner, and independently keyed
   coordinates per owner/property tuple.
2. Add failing tests for a continuation whose immediately preceding assertion
   uniquely supplies owner and property sequence.
3. Add mandatory rejection tests for mismatched cardinality, implicit order,
   non-adjacent continuation, two compatible antecedents, cited Reference
   values without a local owner, and qualitative comparison.
4. Implement explicit ordered mapping without choosing by confidence, first
   occurrence, shortest alias, or majority.
5. Implement bounded continuation as a state machine over adjacent source
   blocks.  Reset state at headings, tables, citations with new owners, or any
   conflicting property sequence.
6. Verify stable accepted and rejected decisions under candidate-order
   permutations.

Verification:

- `./venv/bin/pytest -q -o addopts='' tests/test_alpha25_source_coordinates.py -k 'ordered or continuation or v204'`
- `./venv/bin/pytest -q -o addopts='' tests/test_alpha25_source_coordinates.py`

## Task 3: Integrate bounded assertion recovery before existing gates

Files:

- Modify `src/knowmat/alpha25/materialize.py`.
- Modify `tests/test_alpha25_materialize.py`.
- Modify `.env.example` only for documented v204 switches.

Steps:

1. Add `KNOWMAT2_ALPHA25_TENSILE_ASSERTION_COORDINATES_V204`, default-on and
   independently shadowable.
2. Add failing materialization tests proving an eligible source coordinate
   becomes one ordinary core-tensile candidate and then passes every existing
   owner/evidence/value/unit gate.
3. Add tests proving a pre-existing scientific coordinate prevents a duplicate
   and a rejected source decision cannot create an item or Property.
4. Convert accepted coordinates into ordinary `AxisFact` rows before the v202
   coordinate and quality gates.  Never bypass existing sanitization or
   materialization.
5. Emit `tensile_assertion_coordinate_recovered`,
   `tensile_assertion_continuation_recovered`,
   `tensile_assertion_ordered_mapping_recovered`, and bounded rejected/ambiguous
   audit rows with full source decisions.
6. Keep chart/continuous sidecars and citation-only Reference rows on their
   existing paths.

Verification:

- `./venv/bin/pytest -q -o addopts='' tests/test_alpha25_materialize.py -k 'assertion_coordinate or v204'`

## Task 4: Enforce the one-coordinate-to-one-owner fanout guard

Files:

- Modify `src/knowmat/alpha25/materialize.py`.
- Modify `tests/test_alpha25_materialize.py`.

Steps:

1. Add `KNOWMAT2_ALPHA25_TENSILE_COORDINATE_FANOUT_GUARD_V204`, default-on and
   independently shadowable.
2. Add tests for one evidence atom copied to two incompatible owners, a generic
   duplicate beside one coordinate-proven owner, independent ordered owner
   coordinates, conflicting state/orientation/role, and exact duplicate merge.
3. Index core-tensile facts by exact source coordinate and scientific tuple.
   Preserve complete compatible tuples.
4. Reassign only a missing/generic owner when one exact coordinate proves the
   destination.  Merge only exact dominated duplicates.
5. Quarantine a tuple only when its own coordinate proves an incompatible
   owner/property/value/unit/state/orientation/role.  Ambiguity is a no-op.
6. Emit complete `tensile_coordinate_owner_reassigned`,
   `tensile_coordinate_projection_quarantined`, and
   `tensile_coordinate_duplicate_merged` records.
7. Add invariants proving Composition facts and non-core Properties are
   unchanged.

Verification:

- `./venv/bin/pytest -q -o addopts='' tests/test_alpha25_materialize.py -k 'coordinate_fanout or v204'`

## Task 5: Bind results to one compatible protocol event

Files:

- Modify `src/knowmat/alpha25/property_context.py` if the existing immutable
  ledger cannot express result-coordinate compatibility.
- Modify `src/knowmat/alpha25/materialize.py`.
- Modify `tests/test_alpha25_protocol_ledger.py`.
- Modify focused materialization tests.

Steps:

1. Add `KNOWMAT2_ALPHA25_TENSILE_RESULT_PROTOCOL_BINDING_V204`, default-on and
   independently shadowable.
2. Add tests for bundle-level binding, result temperature selecting one of two
   protocol events, role/state/orientation isolation, and adding only missing
   dimensions.
3. Add no-op tests for conflicting literals, two equally compatible events,
   preparation temperature mistaken for test temperature, rate-type mixing,
   and Target/Reference leakage.
4. Extend the ledger decision boundary only as needed to accept one immutable
   result-coordinate context.  Do not weaken v203 compatibility checks.
5. Apply one selected event consistently to every property in a source bundle.
   Never overwrite an existing literal dimension.
6. Emit complete `tensile_result_protocol_bound` and
   `tensile_result_protocol_ambiguous` records with selected/candidate events
   and contributed dimensions.
7. Prove stable serialization under property and event permutations.

Verification:

- `./venv/bin/pytest -q -o addopts='' tests/test_alpha25_protocol_ledger.py -k 'result or v204'`
- `./venv/bin/pytest -q -o addopts='' tests/test_alpha25_materialize.py -k 'result_protocol or v204'`

## Task 6: Focused regression and switches-off compatibility

Files:

- Modify focused tests only where an intentional v204 default-on delta changes
  the expected result.
- Modify `scripts/rematerialize_alpha25_tasks.py` only if switch plumbing or
  manifest validation requires it.

Steps:

1. Run all tests for touched modules and fix only v204-caused regressions.
2. Run the complete Alpha25 suite.
3. Run the complete repository suite and record unrelated fixture failures
   separately.
4. Rematerialize a bounded source-audited pilot from frozen responses with API
   count zero.
5. Compare every changed Property against source and inspect every audit row.
6. Run with all three v204 switches off and compare scientific payload and
   audit output against accepted v203 for all pilot papers.
7. Narrow the responsible feature if any owner/value/unit/condition or
   precision invariant fails.

Verification:

- `./venv/bin/pytest -q -o addopts='' tests/test_alpha25_source_coordinates.py tests/test_alpha25_protocol_ledger.py tests/test_alpha25_materialize.py`
- `./venv/bin/pytest -q -o addopts='' tests/test_alpha25_*`
- `./venv/bin/pytest -q -o addopts=''`

## Task 7: Thirty-paper frozen acceptance and deterministic replay

Files and artifacts:

- Create `data/output-alpha25-v204-source-assertion-final30-20260824`.
- Create `data/output-alpha25-v204-source-assertion-replay30-20260824`.
- Create `data/experiments/alpha25-v204-source-assertion-20260824/` reports.

Steps:

1. Freeze and record hashes for the 30-paper manifest, 405 task responses,
   prompts, schema, expert GT, business GT, and evaluator configuration.
2. Rematerialize all 30 papers from frozen responses; make zero provider calls.
3. Validate 30/30 success, no fatal/silent-empty paper, path confinement,
   unchanged `final.json` shape, and complete audit outputs.
4. Produce a source-audited delta ledger for every v204 mutation.
5. Run the frozen GPT-expert, business-GT, and three-way evaluators.
6. Enforce every metric and invariance gate from the design.  Disable or narrow
   a component if its gate fails; never change the evaluator or GT.
7. Repeat the full rematerialization into the replay directory.
8. Compare scientific `final.json`, `quality_audit.json`, and summaries for
   determinism and compare Composition payloads byte-for-byte to v203.
9. Measure mean rematerialization runtime and verify the 20% regression cap.
10. Write an acceptance report with tests, hashes, API count, runtime, metrics,
    switch status, and professional comparison against both GTs.

## Task 8: Commit accepted implementation and reports

Steps:

1. Review the exact v204 whitelist diff and scan production code for forbidden
   GT, paper, expected-value, provider, and model dependencies.
2. Confirm no unrelated dirty-worktree file is staged.
3. Commit source/tests first if the implementation gates pass.
4. Commit only compact acceptance reports and explicitly intended artifacts;
   do not stage transient matcher work directories or unrelated outputs.
5. Report the final commit IDs, accepted metrics, runtime, API count,
   determinism status, Composition invariance, and remaining audited residuals.
