# Alpha25 GLM-5.2 Expert-Convergence v23

Date: 2026-08-19

## Outcome

v23 recovers source-grounded numeric SEM/EDS observations that GLM-5.2 had
already emitted as bare numbered rows but the paper-level materializer could
not previously attach to a material state. The repair is deterministic,
provider-neutral, and GT-blind. It does not change the professionally reviewed
prompt, model request shape, schema, or `final.json` envelope.

- 30/30 papers are promotable; fatal validation issues: 0.
- Invalid task-cache files: 0; cached task responses rematerialized: 405.
- New OCR, VLM, and LLM requests caused by the repair: 0.
- Review issues decrease from 1,955 in v22 to 1,946 in v23.
- Materialized item count remains 355.
- Existing issue artifacts remain 30 JSON and 30 Markdown files.
- New `quality_audit.json` files: 0.
- No Point/Spot/Area/Location observation was materialized as a material item.
- `final.json` remains `material_extraction_v11.3.3`, skill
  `11.0.0-alpha.25`, with unchanged ruleset digest
  `b4d071ca8a43b36ffc0e6b4766343d0f5024bc9ef2a042967d92185cdc120284`.
- All 30 outputs record production commit
  `45384c76bab31bfbfe92b55c286df9df7ff8d86c`.

## Fair production comparison

The table compares v22 and v23 with the same corrected owner/location
evaluator. This isolates production movement from evaluator-only movement.

| Metric | v22 corrected baseline | v23 corrected | Delta |
|---|---:|---:|---:|
| Raw loose matched / system | 1,493 / 6,874 | 1,597 / 6,978 | +104 / +104 |
| Raw loose micro F1 | 0.293898 | 0.311185 | +0.017287 |
| Raw strict matched / system | 739 / 6,874 | 779 / 6,978 | +40 / +104 |
| Raw strict micro F1 | 0.145472 | 0.151793 | +0.006321 |
| Unique loose matched / system | 1,404 / 6,593 | 1,508 / 6,697 | +104 / +104 |
| Unique loose F1 | 0.289903 | 0.308069 | +0.018166 |
| Unique strict matched / system | 676 / 6,593 | 716 / 6,697 | +40 / +104 |
| Unique strict F1 | 0.139583 | 0.146272 | +0.006689 |
| Unique Composition loose matched / system | 550 / 1,030 | 654 / 1,134 | +104 / +104 |
| Unique Composition loose F1 | 0.583245 | 0.657286 | +0.074041 |
| Unique Composition strict matched / system | 284 / 1,030 | 324 / 1,134 | +40 / +104 |
| Unique Composition strict F1 | 0.301166 | 0.325628 | +0.024462 |

Unique core-tensile loose remains 155/420 matched (F1 0.482866), and
strict remains 83/420 matched (F1 0.258567). Every non-Composition axis is
unchanged.

## Evaluator-only movement

The legacy evaluator is retained as an audit artifact. It projected an inner
`Point n` label as the material `sample_id`, overwriting the outer material
owner. It also collapsed equal element values measured at different Points.
The corrected evaluator keeps material owner, observation location, and
morphological region as separate dimensions.

On v22 GLM output, legacy and corrected aggregate metrics are byte-for-byte
identical. This demonstrates that the historical production baseline was not
raised by changing the evaluator. On the new v23 facts, applying the corrected
semantics changes only paper_019 Composition:

| Metric | v23 legacy evaluator | v23 corrected evaluator | Evaluator-only delta |
|---|---:|---:|---:|
| Raw loose matched / system | 1,597 / 6,978 | 1,597 / 6,978 | 0 / 0 |
| Raw strict matched / system | 739 / 6,978 | 779 / 6,978 | +40 / 0 |
| Unique loose matched / system | 1,505 / 6,694 | 1,508 / 6,697 | +3 / +3 |
| Unique strict matched / system | 676 / 6,694 | 716 / 6,697 | +40 / +3 |
| Unique Composition loose F1 | 0.655259 | 0.657286 | +0.002027 |
| Unique Composition strict F1 | 0.285858 | 0.325628 | +0.039770 |

The +3 unique claims are equal-valued element measurements at distinct Point
locations that the legacy signature incorrectly folded together. The +40
strict matches are facts whose material state and Point both agree with the
expert ledger after the two dimensions are represented correctly.

For business GT, the corrected evaluator adds two strict Composition matches
in paper_023, where the same EDS Point is represented in `sample_id` on one
side and `region` on the other. No business-GT count or score changes outside
Composition.

## Production repair

A bare numeric composition row is promoted only when all of the following are
true:

1. the source contains an EDS/EDX table with an explicit numeric
   Point/Spot/Area/Location header;
2. the row is a measured table observation with at least two reported numeric
   elemental values;
3. paper prose explicitly links that numbered location to a named sample
   family and a unit-qualified process state;
4. the inventory contains exactly one compatible Target owner;
5. conflicting source owners or multiple compatible states remain unresolved;
6. non-EDS numeric tables, single-element rows, missing headers, and fatigue
   specimen tables remain quarantined.

The numbered label is preserved as an observation location. It is never used
to create a material item. Internal routing markers are consumed before
serialization. Four `numeric_microanalysis_owner_recovered` issue records keep
the complete pre-repair facts, selected owners, state corrections, and source
evidence in the existing `issues.json/.md` channel.

## Recovered paper and facts

After excluding `Rule_Metadata.git_commit`, only paper_019 changes:

`Microstructural evolution and mechanical properties of differently
heat-treated binder jet printed samples from gas- and water-atomized alloy 625
powders`.

The source-backed routing recovers 13 EDS observations and 104 elemental
values:

- WA 1300 °C: Point 2, 8 values;
- GA 1300 °C: Points 3-6, 32 values;
- GA 1285 °C plus aging: Points 7-11, 40 values; and
- WA 1270 °C plus aging: Points 12-14, 24 values.

Point 1 remains isolated because the source does not establish one unique
owner under the accepted evidence rules. The paper remains at 22 material
items, while review issues fall from 215 to 206.

| paper_019 metric | v22 corrected | v23 corrected | Delta |
|---|---:|---:|---:|
| Raw loose matched / system | 146 / 431 | 250 / 535 | +104 / +104 |
| Raw loose F1 | 0.376289 | 0.568182 | +0.191893 |
| Unique loose matched / system | 139 / 398 | 243 / 502 | +104 / +104 |
| Unique loose F1 | 0.381344 | 0.583433 | +0.202089 |
| Unique strict matched / system | 81 / 398 | 121 / 502 | +40 / +104 |
| Unique strict F1 | 0.222222 | 0.290516 | +0.068294 |
| Unique Composition loose F1 | 0.336066 | 0.833333 | +0.497267 |
| Unique Composition strict F1 | 0.081967 | 0.287356 | +0.205389 |

paper_023 is unchanged by production and retains unique loose/strict F1
0.560166/0.319502 and Composition loose/strict F1
0.906122/0.595918 under the corrected evaluator.

## Position relative to business GT

Against the adjudicated GPT-5.6-sol expert ledger, v23 GLM has more matched
unique claims than business GT but also substantially more system claims.
Consequently business GT remains better overall on unique loose F1
(0.411145 versus 0.308069) and core tensile loose/strict F1
(0.712788/0.448637 versus 0.482866/0.258567). v23 GLM is marginally higher on
overall unique strict F1 (0.146272 versus 0.143373) and now higher on
Composition loose/strict F1 (0.657286/0.325628 versus
0.592096/0.155392). The remaining primary gap is therefore global precision,
owner/condition organization outside this recovered EDS subset, and core
tensile quality rather than Composition recall alone.

## Performance and safety

The 30-paper deterministic rematerialization completed in 4 minutes 53
seconds. This is an offline cache-rebuild measurement, not a live OCR or GLM
latency benchmark. The implementation does not add a prompt, task, retry,
model call, OCR call, VLM call, or provider-specific branch, so live extraction
request volume is unchanged.

The production implementation does not import or read GT. GT is used only by
the offline comparison command. No real claim was deleted to increase
precision.

## Verification

- Focused materializer regression: 138 passed.
- Expanded Alpha25/v11/evaluator regression: 382 passed.
- Full repository regression: 481 passed; the same two pre-existing unrelated
  failures remain: the external `/ssd1/.../embedding_index.json` fixture is
  absent, and the existing schema-converter sample-matrix behavior differs
  from its test expectation.
- Corpus audit: 30 final documents, 30 issue JSON files, 30 issue Markdown
  files, zero `quality_audit.json` files, zero Point material items, and zero
  leaked internal markers.

## Artifacts

- Final corpus:
  `data/output-alpha25-expert-convergence-v23-numeric-microanalysis-final-20260819`
- Rematerialization summary:
  `data/output-alpha25-expert-convergence-v23-numeric-microanalysis-final-20260819/rematerialize_summary.json`
- Frozen legacy-evaluator v23 report:
  `reports/gpt56sol_independent_gt_vs_convergence_v23_numeric_microanalysis_legacy_evaluator_20260819.json`
- Corrected-evaluator v22 baseline:
  `reports/gpt56sol_independent_gt_vs_convergence_v22_corrected_location_evaluator_20260819.json`
- Corrected-evaluator v23 report:
  `reports/gpt56sol_independent_gt_vs_convergence_v23_numeric_microanalysis_corrected_evaluator_20260819.json`
- Production commit: `45384c76bab31bfbfe92b55c286df9df7ff8d86c`.
- Evaluator commit: `9eb5b120`.
