# Alpha25 GLM-5.2 Expert-Convergence v18

Date: 2026-08-19

## Outcome

v18 improves the cached Alpha25 GLM-5.2 corpus toward the adjudicated
GPT-5.6-sol expert ledger without changing the professional prompt, the
`final.json` schema/envelope, or any OCR/VLM/LLM response. The production
repairs are deterministic and provider-neutral.

- 30/30 papers are promotable.
- Fatal validation issues: 0.
- Missing comparison papers: 0.
- Invalid task-cache files: 0.
- New OCR/VLM/LLM calls caused by the repairs: 0.
- `quality_audit.json` files introduced: 0.
- Existing per-paper `*_issues.json` and `*_issues.md` files: 30 each.
- Full cached rematerialization wall time: about 4 minutes 40 seconds.

## Fair v16 to v18 comparison

Both corpora were scored with the same corrected evaluator against the same
sealed and adjudicated expert ledger. This separates production gains from
evaluator-only alias corrections.

| Metric | v16 | v18 | Delta |
|---|---:|---:|---:|
| Loose matched claims | 1,251 | 1,266 | +15 |
| Loose system claims | 6,784 | 6,783 | -1 |
| Loose micro F1 | 0.248461 | 0.251465 | +0.003004 |
| Strict matched claims | 579 | 585 | +6 |
| Strict micro F1 | 0.114995 | 0.116198 | +0.001203 |
| Unique loose matched | 1,194 | 1,205 | +11 |
| Unique loose F1 | 0.248439 | 0.250754 | +0.002315 |
| Unique strict matched | 539 | 545 | +6 |
| Unique strict F1 | 0.112151 | 0.113412 | +0.001261 |
| Processing loose matched | 193 | 208 | +15 |
| Processing loose F1 | 0.252783 | 0.272608 | +0.019825 |
| Processing strict matched | 88 | 94 | +6 |
| Processing strict F1 | 0.115259 | 0.123198 | +0.007939 |

Core tensile performance is unchanged: loose remains 155/420 matched
(F1 0.482866), and strict remains 83/420 matched (F1 0.258567).

## v17 condition-preservation repair

The first process-alias implementation recovered valid ontology concepts but
temporarily treated several real experimental variants as conflicting values
of one stage parameter. Examples included first/second aging steps, 5 min /
30 min / 8 h annealing variants, and dwell time versus total cycle time.

v18 reuses the schema's existing optional `condition_label` field and the exact
source evidence to keep those variants distinct. When one evidence span reports
multiple values, the raw value and unit are included in the label solely to
prevent a collision. No new scientific value is inferred. Twenty such bindings
are recorded with `compat.process_variant_condition.v1` in the existing
normalization audit.

| Metric | v17 | v18 | Delta |
|---|---:|---:|---:|
| Loose matched claims | 1,264 | 1,266 | +2 |
| Loose micro F1 | 0.251367 | 0.251465 | +0.000098 |
| Strict matched claims | 581 | 585 | +4 |
| Strict micro F1 | 0.115541 | 0.116198 | +0.000657 |
| Unique loose F1 | 0.250625 | 0.250754 | +0.000129 |
| Unique strict F1 | 0.112708 | 0.113412 | +0.000704 |
| Processing loose F1 | 0.272127 | 0.272608 | +0.000481 |
| Processing strict F1 | 0.118890 | 0.123198 | +0.004308 |

The validation review queue returns from 1,991 in v17 to 1,975 in v18, exactly
the v16 total. `process_parameter_conflict` returns from 32 to 25 and
`conflicting_process_parameter` from 24 to 15. The recovered variants remain in
`final.json`; no real claim was deleted to improve precision.

## Production repairs

- Common process-parameter synonyms are retried only when the frozen
  normalizer originally returns `raw_unmapped_parameter` and the value/unit
  semantics are compatible.
- Supported aliases include hatch spacing, beam diameter, preheat/process
  temperature, duration, atmosphere, oxygen content, energy density, pressure,
  and unit-qualified feed rate.
- Raw key, value, unit, and evidence remain unchanged in the input and audit.
- A successful retry is recorded as `compat.process_parameter_alias.v1`;
  failed retries remain raw and reviewable.
- Explicit sub-steps and multi-value temporal variants receive evidence-backed
  condition labels before the frozen normalizer deduplicates stage parameters.
- The existing `final.json` schema version remains
  `material_extraction_v11.3.3`; no envelope or custom sidecar was added.

## Evaluator-only repairs

The comparison evaluator now treats common process naming families as
semantically equivalent, including `lpbf_hatch_space`/`hatch_spacing`,
`lpbf_laser_spot_diameter`/`beam_diameter`, build-plate/preheat temperature,
oxygen level/content, duration/time, environment/atmosphere, and volumetric
energy density. Process-stage codes are explicitly excluded from this folding.

These rules do not alter production output. All v16-to-v18 values above use the
same evaluator version.

## Verification

- Focused process/evaluator regression: 49 passed.
- Expanded Alpha25/v11 regression: 331 passed.
- Full repository regression: 440 passed, 2 unrelated pre-existing failures.
  One requires `/ssd1/.../embedding_index.json`; the other is in the user's
  existing `schema_converter.py` worktree change.
- Production safety tests confirm that no model, paper, material, title, or GT
  literal was added to production normalization logic.
- Corpus audit: 30 `final.json`, 30 issue JSON files, 30 issue Markdown files,
  and zero `quality_audit.json` files.

## Artifacts

- Final corpus:
  `data/output-alpha25-expert-convergence-v18-condition-aware-final-20260819`
- Official comparison:
  `reports/gpt56sol_independent_gt_vs_convergence_v18_condition_aware_final_20260819.json`
- Readable comparison:
  `reports/gpt56sol_independent_gt_vs_convergence_v18_condition_aware_final_20260819.md`
- Per-paper axes:
  `reports/gpt56sol_independent_gt_vs_convergence_v18_condition_aware_final_20260819_per_paper_axis.csv`
- Adjudication summary:
  `reports/gpt56sol_independent_gt_vs_convergence_v18_condition_aware_final_20260819_adjudication.csv`
