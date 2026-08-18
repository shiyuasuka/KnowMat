# Alpha25 GLM-5.2 Expert-Convergence v19

Date: 2026-08-19

## Outcome

v19 recovers multi-energy-source power facts that were already present in the
Alpha25 candidates but were lost when the frozen process normalizer collapsed
laser and wire/hot-wire power to the same `power` slot. The repair is
deterministic, provider-neutral, and does not change the professional prompt or
the `final.json` envelope.

- 30/30 papers are promotable; fatal validation issues: 0.
- Invalid task-cache files: 0; cached task responses rematerialized: 405.
- New OCR/VLM/LLM calls caused by the repair: 0.
- Existing issue artifacts: 30 JSON and 30 Markdown files.
- New `quality_audit.json` files: 0.
- `final.json` schema remains `material_extraction_v11.3.3`.
- Full cached rematerialization wall time: about 3 minutes 55 seconds.

## Fair production comparison

The table below compares v18 and v19 with the same final evaluator. Evaluator
changes are therefore excluded from the production delta.

| Metric | v18 fair baseline | v19 | Delta |
|---|---:|---:|---:|
| Loose matched claims | 1,298 | 1,305 | +7 |
| Loose system claims | 6,791 | 6,798 | +7 |
| Loose micro F1 | 0.257616 | 0.258826 | +0.001210 |
| Strict matched claims | 592 | 592 | 0 |
| Strict micro F1 | 0.117495 | 0.117414 | -0.000081 |
| Unique loose matched | 1,232 | 1,235 | +3 |
| Unique loose system claims | 6,523 | 6,529 | +6 |
| Unique loose F1 | 0.256240 | 0.256703 | +0.000463 |
| Unique strict matched | 545 | 545 | 0 |
| Unique strict F1 | 0.113353 | 0.113282 | -0.000071 |
| Processing loose matched | 240 | 247 | +7 |
| Processing loose system claims | 884 | 891 | +7 |
| Processing loose F1 | 0.312907 | 0.320571 | +0.007664 |
| Processing strict matched | 101 | 101 | 0 |
| Processing strict F1 | 0.131682 | 0.131084 | -0.000598 |

The seven new raw loose matches are exactly the intended recovered facts:

- paper_029: one `hot_wire_power = 0.3 kW` claim;
- paper_030: six `wire_power` claims, one for each Wall/Multiwall owner.

Strict matched count is unchanged because the expert ledger also records owner
or inert-argon condition details that the source candidates do not fully encode.
The small strict-F1 decrease is the denominator cost of retaining seven real
facts, not a factual regression. Those attribution differences remain visible
as `wrong_owner` or `condition_conflict` review items.

Core tensile is unchanged: unique loose remains 155/420 matched (F1 0.482866)
and unique strict remains 83/420 matched (F1 0.258567).

## Production repair

The compatibility adapter now recognizes explicit energy-source qualifiers in
reported power names: `laser`, `hot_wire`, `wire`, `electron_beam`, and `arc`.
It activates only when one candidate stage contains at least two distinct,
explicit energy sources. A stage with only ordinary Laser Power is untouched.

The adapter writes the qualifier to the schema's existing
`condition_label_raw` field before frozen normalization. It does not invent a
power value, change evidence, or mutate the caller's candidate. Sixteen new
bindings (8 laser, 6 wire, 2 hot-wire) are retained in the existing
`compat.process_variant_condition.v1` normalization audit.

Observed effects:

- paper_029 retains both 5 kW laser and 0.3 kW hot-wire power;
- paper_030 retains 12 powered-source records instead of 6;
- paper_029 process-conflict issues fall from 5 to 3;
- paper_030 process-conflict issues fall from 11 to 0;
- total review issues fall from 1,975 to 1,962.

## Evaluator-only corrections

The evaluator was independently tightened and then applied to both v18 and
v19. These changes do not alter production output:

- process time/temperature aliases are folded only inside the same evidenced
  operation (sintering, solution treatment, aging, annealing, homogenization,
  HIP, stress relief, curing, debinding, drying, or generic heat treatment);
- different operations with the same duration are not treated as equivalent;
- named thermal variants such as S1290/HA1065 must be compatible with the
  counterpart evidence temperature;
- discrete process temperatures use a tighter tolerance, and scalar values no
  longer match inequality bounds;
- kW/W conversion is supported;
- `laser`/`wire`/`hot_wire` source qualifiers identify the power semantic and
  are not misinterpreted as test-environment conditions.

On unchanged v18 output, these evaluator-only corrections move loose F1 from
0.251465 to 0.257616 and Processing loose F1 from 0.272608 to 0.312907. This
delta is reported separately and is not claimed as a production improvement.

## Verification

- Focused process/evaluator regression: 55 passed.
- Expanded Alpha25/v11/independent-GT regression: 359 passed.
- Full repository regression: 455 passed, with 2 pre-existing unrelated
  failures: the external `/ssd1/.../embedding_index.json` fixture is absent,
  and the existing schema-converter sample-matrix behavior differs from its
  test expectation.
- Corpus audit: 30 `final.json`, 30 issue JSON files, 30 issue Markdown files,
  and zero `quality_audit.json` files.
- No prompt file was changed in this iteration.

## Artifacts

- Final corpus:
  `data/output-alpha25-expert-convergence-v19-energy-power-final-20260819`
- Rematerialization summary:
  `data/output-alpha25-expert-convergence-v19-energy-power-final-20260819/rematerialize_summary.json`
- Fair v18 evaluator baseline:
  `reports/gpt56sol_independent_gt_vs_convergence_v18_v19_evaluator_baseline_20260819.json`
- Official v19 comparison:
  `reports/gpt56sol_independent_gt_vs_convergence_v19_energy_power_final_20260819.json`
- Readable v19 comparison:
  `reports/gpt56sol_independent_gt_vs_convergence_v19_energy_power_final_20260819.md`
- Per-paper axes:
  `reports/gpt56sol_independent_gt_vs_convergence_v19_energy_power_final_20260819_per_paper_axis.csv`
- Adjudication summary:
  `reports/gpt56sol_independent_gt_vs_convergence_v19_energy_power_final_20260819_adjudication.csv`
