# Alpha25 GLM-5.2 Expert-Convergence v20

Date: 2026-08-19

## Outcome

v20 repairs evidence-backed process facts that Alpha25 had already extracted
from structured tables but the frozen process normalizer discarded or attached
to the wrong stage. The production change is deterministic and
provider-neutral. It does not change the professional prompt, make new model
requests, or alter the `final.json` envelope.

- 30/30 papers are promotable; fatal validation issues: 0.
- Invalid task-cache files: 0; cached task responses rematerialized: 405.
- New OCR/VLM/LLM calls caused by the repair: 0.
- Review issues: 1,962 in v19 and 1,961 in v20.
- Existing issue artifacts: 30 JSON and 30 Markdown files.
- New `quality_audit.json` files: 0.
- `final.json` remains `material_extraction_v11.3.3` with skill
  `11.0.0-alpha.25`.
- Full cached rematerialization wall time: about 3 minutes.

## Fair production comparison

The table below compares v19 and v20 with the same corrected final evaluator.
Evaluator changes are therefore excluded from the production delta.

| Metric | v19 fair baseline | v20 | Delta |
|---|---:|---:|---:|
| Loose matched claims | 1,431 | 1,451 | +20 |
| Loose system claims | 6,795 | 6,832 | +37 |
| Loose micro F1 | 0.283900 | 0.286816 | +0.002916 |
| Strict matched claims | 646 | 665 | +19 |
| Strict micro F1 | 0.128162 | 0.131449 | +0.003287 |
| Unique loose matched | 1,350 | 1,362 | +12 |
| Unique loose system claims | 6,526 | 6,551 | +25 |
| Unique loose F1 | 0.280694 | 0.282455 | +0.001761 |
| Unique strict matched | 591 | 602 | +11 |
| Unique strict F1 | 0.122882 | 0.124844 | +0.001962 |
| Processing loose matched | 291 | 311 | +20 |
| Processing loose system claims | 888 | 925 | +37 |
| Processing loose F1 | 0.378414 | 0.394921 | +0.016507 |
| Processing strict matched | 127 | 146 | +19 |
| Processing strict F1 | 0.165150 | 0.185397 | +0.020247 |
| Unique processing loose matched | 237 | 249 | +12 |
| Unique processing loose F1 | 0.352941 | 0.364035 | +0.011094 |
| Unique processing strict matched | 101 | 112 | +11 |
| Unique processing strict F1 | 0.150410 | 0.163743 | +0.013333 |

Core tensile is unchanged: loose remains 155/420 matched (F1 0.482866)
and strict remains 83/420 matched (F1 0.258567).

## Production repair

The compatibility adapter now performs three conservative operations before
the frozen process normalizer runs:

1. An otherwise-unmapped explicit post-heat-treatment abbreviation such as
   `post-HT` or `Post-heat treatments` is routed to the frozen generic heat
   treatment process. The exact original wording remains in the normalization
   audit.
2. A generic container such as `Printing Parameters` is never treated as a
   process on its own. Its parameter is moved only when the same route already
   contains an explicit compatible AM stage. Ambiguous ties between different
   process codes are left untouched.
3. `Heating Temperature` is moved out of an AM stage only when the same route
   contains an explicit heat-treatment stage that already owns reported time
   evidence. Without that sibling evidence the temperature is not moved.

The input candidate is deep-copied and never mutated. Original raw key, value,
unit, evidence, stage ID, and destination are retained in the existing
normalization log under:

- `compat.process_stage_alias.v1`: 13 records;
- `compat.process_container_parameter_rehome.v1`: 10 records;
- `compat.process_thermal_parameter_rehome.v1`: 10 records.

### Recovered facts

For the active-learning Ti-6Al-4V paper, v20 restores all 30 reported Table 1
process values that were present in the cached candidates:

- 10 volumetric energy-density values;
- 10 post-heat-treatment temperatures;
- 10 post-heat-treatment times, including the explicitly reported 0 °C and
  0 h row for sample 5-2.

The paper's Processing loose matched count rises from 32 to 51 and strict from
29 to 48. Processing loose F1 rises from 0.609524 to 0.739130; strict rises
from 0.552381 to 0.695652. Nine temperatures already matched loosely in v19
despite being attached to the wrong AM stage, so the new loose matches are
primarily the ten energy-density values and nine nonzero heat-treatment times.

One additional genuine stage is recovered in the nanotwinned EHEA paper from
the explicit sentence `Post-heat treatments were performed in a muffle furnace
at 600 °C ... followed by water quenching.` It contributes one new loose GT
match and retains the other source-supported stage details even though the
expert ledger does not enumerate all of them. Removing those true details to
improve precision would violate the evidence-preservation policy.

Excluding `Rule_Metadata.git_commit`, only these two papers differ from v19.
Two complex heat-treatment control papers are otherwise byte-identical to v19
and emit none of the new compatibility audit rules.

## Evaluator-only corrections

The evaluator was corrected independently and then applied to both v19 and
v20. These changes do not alter production output:

- canonical numeric values are compared with canonical units, while raw values
  remain available for provenance;
- numeric raw-unmapped evidence with an explicit unit is treated as a numeric
  comparison claim instead of an opaque category;
- a process parameter inherits the enclosing stage code/profile as semantic
  context, without adding that context as a strict condition;
- `J/mm^3` and `J/mm³` are normalized as the same unit.

On unchanged v19 output, these evaluator-only corrections move loose F1 from
0.258826 to 0.283900 and strict F1 from 0.117414 to 0.128162. Processing loose
F1 moves from 0.320571 to 0.378414 and Processing strict F1 from 0.131084 to
0.165150. This delta is reported separately and is not claimed as a production
improvement.

## Verification

- Focused runtime/evaluator regression: 61 passed.
- Expanded Alpha25/v11/independent-GT regression: 352 passed.
- Full repository regression: 461 passed; 2 pre-existing unrelated failures
  remain: the external `/ssd1/.../embedding_index.json` fixture is absent, and
  the existing schema-converter sample-matrix behavior differs from its test
  expectation.
- Corpus audit: 30 `final.json`, 30 issue JSON files, 30 issue Markdown files,
  and zero `quality_audit.json` files.
- No prompt file was changed in this iteration.

## Artifacts

- Final corpus:
  `data/output-alpha25-expert-convergence-v20-stage-routing-final-20260819`
- Rematerialization summary:
  `data/output-alpha25-expert-convergence-v20-stage-routing-final-20260819/rematerialize_summary.json`
- Fair v19 evaluator baseline:
  `reports/gpt56sol_independent_gt_vs_convergence_v19_v20_evaluator_baseline_20260819.json`
- Official v20 comparison:
  `reports/gpt56sol_independent_gt_vs_convergence_v20_stage_routing_final_20260819.json`
- Readable v20 comparison:
  `reports/gpt56sol_independent_gt_vs_convergence_v20_stage_routing_final_20260819.md`
- Per-paper axes:
  `reports/gpt56sol_independent_gt_vs_convergence_v20_stage_routing_final_20260819_per_paper_axis.csv`
- Adjudication summary:
  `reports/gpt56sol_independent_gt_vs_convergence_v20_stage_routing_final_20260819_adjudication.csv`
