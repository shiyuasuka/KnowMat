# Alpha25 GLM-5.2 Expert-Convergence v16

Date: 2026-08-19

## Outcome

The v16 pipeline improves the cached Alpha25 GLM-5.2 corpus toward the
adjudicated GPT-5.6-sol expert ledger without changing the professional prompt,
the `final.json` envelope, or the source chunk responses. All changes are
deterministic and provider-neutral.

- 30/30 papers are promotable.
- Fatal validation issues: 0.
- Invalid task-cache files: 0.
- Missing comparison papers: 0.
- New OCR/VLM/LLM calls caused by these repairs: 0.
- `quality_audit.json` files introduced: 0.
- Existing per-paper `*_issues.json` and `*_issues.md` files: 30 each.

## Fair v10 to v16 comparison

Both versions below were scored with the same corrected evaluator against the
same adjudicated expert ledger.

| Metric | v10 | v16 | Delta |
|---|---:|---:|---:|
| Loose matched claims | 1,181 | 1,242 | +61 |
| Loose micro F1 | 0.234442 | 0.246673 | +0.012231 |
| Strict matched claims | 538 | 578 | +40 |
| Strict micro F1 | 0.106799 | 0.114796 | +0.007997 |
| Unique loose matched | 1,125 | 1,185 | +60 |
| Unique loose F1 | 0.233961 | 0.246567 | +0.012606 |
| Unique strict matched | 498 | 538 | +40 |
| Unique strict F1 | 0.103567 | 0.111943 | +0.008376 |
| Raw system claims | 6,789 | 6,784 | -5 |
| Unique system claims | 6,522 | 6,517 | -5 |

Core tensile performance did not regress: loose remains 155/420 matched
(F1 0.482866), and strict remains 83/420 matched (F1 0.258567).

The gain is concentrated in correcting fact axes, preserving valid structure
facts, and recovering process parameters whose TeX units previously failed
normalization. Structure loose matches rise from 237 to 289 and strict matches
from 118 to 154; Processing rises from 175 to 184 loose matches and 83 to 87
strict matches. Properties shrink from 1,160 to 1,066 records without losing a
matched expert property claim.

## Business GT and GLM v16 versus expert ledger

| Metric | Business GT | GLM v16 |
|---|---:|---:|
| Loose matched | 1,313 | 1,242 |
| Loose F1 | 0.312507 | 0.246673 |
| Strict matched | 449 | 578 |
| Strict F1 | 0.106867 | 0.114796 |
| Unique loose F1 | 0.370705 | 0.246567 |
| Unique strict F1 | 0.128391 | 0.111943 |
| Core tensile loose F1 | 0.721174 | 0.482866 |
| Core tensile strict F1 | 0.452830 | 0.258567 |

Professional interpretation: business GT remains the more precise and useful
reference set, especially for unique claims and core tensile facts. GLM v16
contains more strictly matched atomic facts in absolute count, but produces far
more records, so its precision and deduplicated F1 remain lower. The main
remaining gap is over-projection and owner/state/condition organization, not a
wholesale lack of correct scientific content.

Wrong-owner counts must not be optimized blindly. The expert ledger sometimes
models EDS points, regions, feedstock, or literature rows as independent owners,
whereas the approved business prompt explicitly excludes regions, test
subsamples, and table locators as material items. Rebuilding the material item
model around the scorer would violate the business contract.

## Production repairs

- Relative percentage quantities are separated from absolute physical
  properties and audited with `property_relative_quantity_reclassified`.
- Test protocols, source locators, methods, and comparison headings are
  quarantined from Properties with `property_non_result_quarantined`.
- Invalid dimensional units are removed from purely categorical property
  responses with `property_categorical_unit_removed`.
- Morphology-only names can be replaced by a fuller source-grounded identity
  with `material_identity_descriptor_replaced`.
- Lattice parameters, lattice misfit, d-spacing, diffraction peak positions,
  crystallographic planes, and 2-theta facts are moved from Properties to
  Structure through the existing `fact_axis_reclassified` audit path.
- OCR/TeX micrometre forms are normalized semantically while preserving
  `unit_raw`; this includes mapped structure fields and unmapped process
  parameters. All 59 TeX-micrometre records now have a canonical unit, and the
  normalization review total falls from 1,984 to 1,975. No paper, material,
  model, or GT literal is used.

## Evaluator-only repairs

These changes affect fair measurement but do not alter production output:

- Property aliases now require underscore-token boundaries, so `ys` no longer
  matches inside `crystallographic`.
- Unicode/TeX micrometre spellings, Vickers-load notation, percent variants,
  density units, cycles, K/degree-C, and hour/minute/second conversions are
  compared semantically.

Production improvements and evaluator corrections are therefore reported
separately. The v10-to-v16 table uses the same evaluator on both corpora.

## Verification

- Focused convergence tests: 171 passed.
- Expanded Alpha25/v11 regression: 302 passed.
- Full repository regression: 417 passed, 2 unrelated pre-existing failures.
  One requires `/ssd1/.../embedding_index.json`; the other is in the user's
  existing `schema_converter.py` worktree change.
- Production safety test confirms no reviewed paper/material literals in the
  reconciliation and normalization code.

## Artifacts

- Final corpus: `data/output-alpha25-expert-convergence-v16-tex-unit-final-20260819`
- Official comparison: `reports/gpt56sol_independent_gt_vs_business_vs_convergence_v16_tex_unit_final_20260819.json`
- Readable comparison: `reports/gpt56sol_independent_gt_vs_business_vs_convergence_v16_tex_unit_final_20260819.md`
- Per-paper axes: `reports/gpt56sol_independent_gt_vs_business_vs_convergence_v16_tex_unit_final_20260819_per_paper_axis.csv`
- Adjudication summary: `reports/gpt56sol_independent_gt_vs_business_vs_convergence_v16_tex_unit_final_20260819_adjudication.csv`
