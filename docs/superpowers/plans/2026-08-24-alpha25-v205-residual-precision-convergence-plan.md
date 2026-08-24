# Alpha25 v205 residual precision convergence implementation plan

## Goal

Implement the approved v205 design on top of accepted v204.  Improve global
precision/F1 by enforcing source-local Structure and Characterization
atomicity, separating presentation/protocol text from scientific Property
conditions, and converging process-only core-tensile owners only when one
existing material/specimen coordinate is uniquely proven.

Authoritative design:
`docs/superpowers/specs/2026-08-24-alpha25-v205-residual-precision-convergence-design.md`.

## Guardrails

- Do not modify prompts, model/provider configuration, OCR/VLM/chart output,
  frozen task responses, Alpha25 schemas, or `final.json` shape.
- Production code must not read GT, matcher output, paper identities, expected
  values/counts, providers, or model names.
- Do not treat a GT-unmatched fact as a hallucination or deletion signal.
- Do not modify Composition routing, normalization, filtering, or output.
- Preserve all unrelated dirty-worktree changes.  Stage and commit only the
  explicit v205 whitelist files.
- Edit source files with `apply_patch`, use `./venv/bin/python`, and run pytest
  with `-o addopts=''`.
- Every scientific mutation requires a complete deterministic audit record.

## Task 1: Freeze v204 residual fixtures and switches-off invariants

Files:

- Modify `tests/test_alpha25_promotion.py`.
- Modify `tests/test_alpha25_materialize.py` only when public materialization
  behavior needs a direct invariant.
- Modify `.env.example` only if it already documents Alpha25 feature switches.

Steps:

1. Add synthetic fixtures representing the audited residual grammars: a
   repeated structural measurement, method aliases, `Table/Figure` locators in
   a Property condition, duplicate scientific condition fragments, a
   process-only tensile owner with one material owner, and ambiguous controls.
2. Add tests proving Composition facts are byte-identical before and after the
   v205 passes.
3. Add default-on switch helpers for the four approved v205 components.
4. Add a test that disables all four switches and proves the v204 scientific
   facts and audit decisions are unchanged.
5. Add a static negative test that production modules contain no GT paths,
   paper IDs/titles, provider/model dispatch, or expected residual values.

Verification:

- `./venv/bin/pytest -q -o addopts='' tests/test_alpha25_promotion.py -k 'v205 or switches_off'`
- `./venv/bin/pytest -q -o addopts='' tests/test_alpha25_materialize.py -k 'v205 or switches_off'`

## Task 2: Separate provenance locators and protocol prose from conditions

Files:

- Modify `src/knowmat/alpha25/promotion.py`.
- Modify `tests/test_alpha25_promotion.py`.

Steps:

1. Add failing tests for locator-only conditions (`Table`, `Figure`,
   supplement, page, and section), locators embedded beside a real scientific
   condition, and multiple repeated `room temperature` fragments.
2. Add negative tests for distinct temperature/rate/state/orientation/delay
   dimensions, preparation versus test temperature, delay versus hold time,
   strain rate versus crosshead speed, and an ungrounded condition.
3. Implement one source-literal condition tokenizer that classifies locator,
   protocol, and scientific-coordinate segments without searching neighboring
   source blocks.
4. Remove only presentation locators; reuse the existing bounded scientific
   coordinate extractor for method/protocol prose.
5. Deduplicate condition segments by semantic coordinate key while preserving
   original presentation for one survivor and preserving all distinct
   dimensions.
6. Emit the approved `property_provenance_locator_removed_from_condition`,
   `property_condition_protocol_context_separated`, and
   `property_condition_duplicate_segment_removed` audit rows with complete
   before/after records.
7. Run this pass after source-grounding and condition-label binding but before
   condition-aware owner routing and source-assertion deduplication.

Verification:

- `./venv/bin/pytest -q -o addopts='' tests/test_alpha25_promotion.py -k 'provenance_condition or condition_duplicate or v205'`

## Task 3: Add Structure assertion atomicity

Files:

- Modify `src/knowmat/alpha25/source_coordinates.py` if an immutable coordinate
  cannot be represented by the existing source-binding decisions.
- Modify `src/knowmat/alpha25/promotion.py`.
- Modify `tests/test_alpha25_source_coordinates.py` when a new coordinate
  contract is added.
- Modify `tests/test_alpha25_promotion.py`.

Steps:

1. Add failing tests for one explicit feature/value/unit/entity coordinate,
   one logical table row/cell coordinate, and a bounded shared-unit list.
2. Add mandatory negative tests for value detached from entity/feature/unit,
   one evidence atom copied to several owners/entities, locator-as-value,
   method-as-feature, processing-parameter projection, nominal formula token,
   and crossed lists without explicit order.
3. Add positive controls for source-supported qualitative phase/morphology,
   explicit `d-spacing`, lattice parameter, grain size, texture, and defect
   observations even when an offline GT omits them.
4. Build a deterministic source-atom coordinate keyed by owner/state/entity/
   feature/value/unit/qualifier plus source block or logical table path.
5. Preserve compatible candidates, merge only exact source-identical generic
   duplicates, and quarantine only a coordinate-proven incompatible
   projection.  Zero or multiple matches are an audited no-op.
6. Emit `structure_assertion_projection_quarantined`,
   `structure_assertion_duplicate_merged`, and
   `structure_assertion_coordinate_ambiguous` with stable decision keys.
7. Place the pass after existing structure syntax/procedural gates and table
   binding, but before cross-owner projection and final source-assertion dedup.

Verification:

- `./venv/bin/pytest -q -o addopts='' tests/test_alpha25_source_coordinates.py -k 'structure_coordinate or v205'`
- `./venv/bin/pytest -q -o addopts='' tests/test_alpha25_promotion.py -k 'structure_assertion or v205'`

## Task 4: Add Characterization event atomicity

Files:

- Modify `src/knowmat/alpha25/promotion.py`.
- Modify `src/knowmat/alpha25/materialize.py` only if final alias coalescing
  must consume a coordinate marker.
- Modify `tests/test_alpha25_promotion.py`.
- Modify `tests/test_alpha25_materialize.py` when final coalescing changes.

Steps:

1. Add failing tests for acronym/full-name aliases in one source atom and one
   owner/state, as well as one independently stated method event per owner.
2. Add negative controls for caption-only/citation-only mentions, unresolved
   multi-owner methods, instrument settings/software/detectors projected as
   events, measured values projected as method events, and distinct acquisition
   modes that must not merge.
3. Reuse the current method-family registry but require one unambiguous local
   source binding and owner/state coordinate before event fanout or alias merge.
4. Merge only presentation aliases with the same source atom, owner/state,
   method family, and compatible secondary metadata; union exact evidence.
5. Quarantine only coordinate-proven presentation/result projections and leave
   ambiguous aliases unchanged with a review decision.
6. Emit `characterization_event_projection_quarantined`,
   `characterization_event_alias_merged`, and
   `characterization_event_coordinate_ambiguous` with complete records.
7. Ensure the materializer does not perform a second broader merge that would
   erase distinctions preserved by the source-coordinate pass.

Verification:

- `./venv/bin/pytest -q -o addopts='' tests/test_alpha25_promotion.py -k 'characterization_event or v205'`
- `./venv/bin/pytest -q -o addopts='' tests/test_alpha25_materialize.py -k 'characterization_event or alias'`

## Task 5: Add unique material-owner convergence for core tensile

Files:

- Modify `src/knowmat/alpha25/promotion.py`.
- Modify `tests/test_alpha25_promotion.py`.

Steps:

1. Add failing tests for a process/method-only owner where the same assertion
   or logical table coordinate names exactly one existing material/specimen.
2. Add preservation tests where the process label is the source's only sample
   designation or is itself an explicit declared inventory identity.
3. Add mandatory no-op tests for two compatible material owners, mismatched
   value/unit/role/state/orientation/condition, citation-only references,
   nearby-but-not-local owner mentions, and non-core Properties.
4. Reuse the existing owner graph and v204 tensile assertion/table coordinates.
   Do not add a static process-name list; classify a candidate as process-only
   only from existing inventory roles and local process grammar.
5. Reassign only to one existing current-paper Target/Experimental owner.
   Otherwise preserve the candidate and emit ambiguity.
6. Emit `tensile_process_owner_reassigned` and
   `tensile_process_owner_ambiguous` with before/after and candidate-coordinate
   ledgers.
7. Prove that Composition and non-core Property owners are unchanged.

Verification:

- `./venv/bin/pytest -q -o addopts='' tests/test_alpha25_promotion.py -k 'unique_material_owner or tensile_process_owner or v205'`

## Task 6: Integrate audit, deterministic ordering, and compatibility

Files:

- Modify `src/knowmat/alpha25/promotion.py`.
- Modify `src/knowmat/alpha25/materialize.py` only when issue transport or
  internal coordinate cleanup is required.
- Modify focused tests.

Steps:

1. Integrate all v205 passes into `promote_axis_facts` in the approved order.
2. Ensure every removed/reassigned/merged record is emitted through the
   existing issue transport into full `quality_audit.json`; keep
   `issues.json/.md` compact and leave `final.json` unchanged in shape.
3. Remove all private coordinate markers before public materialization.
4. Add candidate-order, source-block-order, and repeated-run determinism tests.
5. Add independent per-switch shadow tests and an all-switches-off v204 replay
   compatibility test.
6. Run the focused files and complete Alpha25 regression.

Verification:

- `./venv/bin/pytest -q -o addopts='' tests/test_alpha25_source_coordinates.py tests/test_alpha25_promotion.py tests/test_alpha25_claim_quality.py tests/test_alpha25_materialize.py tests/test_alpha25_protocol_ledger.py`
- `./venv/bin/pytest -q -o addopts='' tests/test_alpha25_*.py`

## Task 7: Source-audited pilot and component selection

Files/artifacts:

- Create `data/experiments/alpha25-v205-residual-precision-20260824/` reports.
- Create pilot output directories under `data/output-alpha25-v205-*`.

Steps:

1. Replay frozen v204 responses for a bounded pilot covering the approved
   Structure, Characterization, locator-condition, process-owner, discrete
   chart, delay/state, and GT-omission controls.  Make zero provider calls.
2. Produce a per-decision delta ledger with exact source atom, before/after,
   switch, reason, and adjudication.
3. Reject or revise any switch that removes a source-supported fact, crosses an
   owner/entity/value/unit/condition coordinate, or expands chart context.
4. Compare each switch independently with GPT expert GT and business GT.
5. Keep only source-correct components whose precision/F1 gates do not regress.

Verification:

- pilot success/fatal/API-call summary;
- source-audited decision ledger; and
- per-component comparison JSON/Markdown.

## Task 8: Thirty-paper double replay and dual-GT acceptance

Files/artifacts:

- Create final and repeat output directories under `data/output-alpha25-v205-*`.
- Create acceptance, three-way comparison, direct-business comparison, and
  delta-ledger JSON/Markdown under
  `data/experiments/alpha25-v205-residual-precision-20260824/`.

Steps:

1. Replay all 30 papers twice from the same frozen 405 task responses with no
   model/provider calls.
2. Verify 30/30 success, zero fatal/silent-empty papers, zero API calls, and a
   mean wall-time regression no greater than 20% versus v204.
3. Verify deterministic scientific `final.json`, `quality_audit.json`, and
   summary output across both runs, excluding documented run metadata.
4. Verify Composition scientific payloads match v204 30/30.
5. Disable all v205 switches and verify v204 scientific payload and audit
   compatibility.
6. Compare v205 with GPT expert GT and business GT, both globally and by axis;
   report loose/strict precision, recall, F1, core-tensile metrics, wrong-owner,
   value/unit/condition conflicts, unsupported claims, and missing claims.
7. Source-adjudicate every regression and all high-risk v205 mutations.
8. Accept v205 only if every gate in the design passes; otherwise disable or
   revise the responsible component and rerun the affected checks.

Verification:

- complete focused and Alpha25 pytest results;
- 30-paper first/repeat summaries and deterministic hashes;
- Composition and switches-off compatibility manifests;
- dual-GT comparison JSON/Markdown; and
- final source-adjudicated v205 acceptance report.

## Commit sequence

1. `test: freeze alpha25 v205 residual precision contracts`
2. `feat: separate alpha25 v205 property provenance conditions`
3. `feat: enforce alpha25 v205 structure assertion atomicity`
4. `feat: enforce alpha25 v205 characterization event atomicity`
5. `feat: converge alpha25 v205 tensile material owners`
6. `docs: record alpha25 v205 acceptance`

Each commit stages only files from its task whitelist.  If implementation
requires a file outside the whitelist, update this plan first and document why.
