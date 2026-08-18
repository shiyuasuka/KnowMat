# Alpha25 Deterministic Semantic Quality Gates

## Context

The frozen 30-paper Alpha25 run completed successfully and retained strong source
grounding, but professional review found four remaining quality classes:

- non-material concepts or process labels can become material items;
- grounded facts can be assigned to the wrong semantic axis or material owner;
- core tensile facts can lose sample or condition attribution across chunks; and
- invalid line-chart coordinates can enter material properties.

The repair must improve production truthfulness without mechanically fitting the AI
GT. The professionally reviewed prompt baseline, OCR output, and cached LLM task
responses are frozen for the first implementation and evaluation pass.

## Constraints

- Do not modify prompt files or `src/knowmat/alpha25/prompt_compiler.py`.
- Preserve the exact Alpha25 `final.json` schema and field hierarchy.
- Do not add rules keyed by paper title, material name, expected GT value, model name,
  endpoint provider, or API implementation.
- Preserve all original source evidence. Never infer a missing value or owner from
  domain knowledge alone.
- Keep explicitly named target materials and reference materials that own independent
  composition, processing, structure, characterization, or property facts.
- Do not create material items from citations, comparison prose, datasets, process
  names, phases, regions, test pieces, or characterization sub-samples alone.
- Reuse frozen OCR and existing task-cache outputs for the first 30-paper regression.
  That regression must not call OCR, LLM, or VLM providers.

## Considered approaches

### 1. Layered deterministic quality gates — selected

Validate chart data before contextualization, reconcile semantic axes and identities
during materialization, and apply a final output eligibility gate. This prevents
invalid data from influencing later reconciliation while still repairing cached
grounded facts offline.

### 2. Final-document cleanup only

Cleaning only `final.json` would centralize the implementation, but incorrect facts
would already have influenced identity resolution, state routing, and deduplication.
It would also make owner recovery unreliable.

### 3. Evaluation or presentation filtering only

Hiding disputed facts in reports would leave the production JSON polluted for other
consumers. This does not repair the extraction pipeline and is rejected.

## Architecture and data flow

The frozen inputs flow through three deterministic gates:

1. **Chart confidence gate** validates axis calibration, numeric coordinates, bounds,
   units, and semantic constraints before a curve summary can enter extraction
   context.
2. **Semantic and identity gate** validates material eligibility, fact axis, sample
   owner, state, and reference role while cached facts are materialized.
3. **Final output gate** removes empty or ineligible items, preserves only validated
   facts in the unchanged Alpha25 document, and records every destructive or
   corrective action in the existing validation issues report.

The resulting flow is:

`frozen OCR/task cache -> chart gate -> semantic/identity reconciliation -> output gate -> final.json + issues.json + issues.md + existing CSV files`

No separate `quality_audit.json` is introduced.

## Material identity rules

A material item requires an explicit source-named material, composition, batch,
source sample code, or independently prepared material state plus at least one
substantive non-identity fact.

- Process families and manufacturing methods are context unless the source also uses
  the same string as an explicit material or sample label.
- Dataset names, iteration labels, phases, precipitates, matrices, regions, specimen
  geometries, test coupons, and characterization sub-samples are not material items.
- An explicit source sample code that embeds orientation remains an item when the
  source uses it as an independent row or specimen identifier. A prose qualifier such
  as `X orientation` remains fact context and does not split an item by itself.
- A reference item is retained only when it owns an independent composition,
  processing, structure, characterization, or property fact. A citation or relational
  comparison alone is insufficient.
- Identity-only and otherwise empty items are removed.

## Semantic axis rules

### Composition

Composition accepts material identity and observations containing chemical
components with an explicit amount, range, balance, categorical composition value,
or basis. Element effects, oxidation affinity, thermodynamic values, mechanisms, and
comparative prose are not composition observations.

### Processing

Processing accepts state-changing manufacturing, thermal, deformation, joining,
surface-treatment, and feedstock-preparation operations. Test execution,
characterization, specimen geometry, and observed thermal history are not process
stages unless the source explicitly describes them as state-changing treatment.

### Structure

Structure accepts phases, grains, precipitates, defects, interfaces, textures, and
their sizes, fractions, morphologies, distributions, and spatial relationships.
Measurements whose semantic subject is one of these structural entities remain
structure facts rather than generic material properties.

### Properties

Properties accept material responses associated with a material owner and a reported
test or observation condition. Structural metrics are not generic properties.
Canonical tensile aliases such as `sigma_B`, `UTS`, and `ultimate tensile strength`
are reconciled without replacing the original property name, raw value, unit,
temperature, orientation, specimen, or evidence.

A fact is deterministically reclassified only when it fully satisfies exactly one
target-axis contract. Ambiguous facts are quarantined for review rather than guessed.

## Cross-chunk ownership

Owner resolution uses the following evidence-derived precedence:

1. exact source sample code;
2. explicit source alias;
3. qualified material-state identity; and
4. a unique unqualified base material.

An unqualified fact is never broadcast to several material states. A fact that names
multiple known materials may be represented as a shared comparison only under the
existing comparison contract; it cannot create a combined material item. If no
unique owner can be established, the fact is omitted from `final.json` and recorded
as `unresolved_fact_owner`.

## Chart confidence and quarantine

Chart coordinates are accepted only when their calibration and series both pass the
generic quality contract.

- Axis references must be finite, distinct, monotonic, and sufficient to define the
  mapping.
- Mapped points must be finite and remain within the calibrated plot domain, allowing
  only an explicit small numerical tolerance derived from the calibrated span.
- A curve with contradictory axes, invalid scale, or systematic coordinate failure is
  quarantined as a complete series.
- A localized invalid point may be quarantined individually only when the remaining
  series still passes the series-level contract.
- When an axis explicitly denotes a non-negative tensile quantity, a significant
  negative mapped value is invalid. The implementation must not silently clamp it to
  zero.
- Existing cached chart summaries using the deterministic `series: ... key_points=...`
  format are subject to the same materialization-time gate.

Quarantined chart data never enter `Properties`, derived metrics, GT matching, or
business conclusions. Existing CSV files remain unchanged and provide the complete
recoverable record.

## Output and audit contract

`final.json` remains schema-identical to the current Alpha25 output. It receives no
audit flags, quarantine fields, or new top-level keys.

The existing `issues.json` is the canonical audit record. New review-level issue
codes are added without changing its top-level shape:

- `non_material_item_removed`
- `empty_item_removed`
- `reference_without_independent_fact_removed`
- `fact_axis_reclassified`
- `fact_quarantined_wrong_axis`
- `unresolved_fact_owner`
- `curve_point_quarantined`
- `curve_series_quarantined`

Each issue uses the existing fields `code`, `severity`, `path`, `message`, `evidence`,
`expected`, `actual`, and `suggested_action`. Removed or migrated facts are preserved
under `actual`. Large curve point arrays are not duplicated: the issue stores the
series identity, observed range, reason, and existing CSV path. `issues.md` is rendered
from the same JSON and presents a concise review summary.

Recoverable quarantine and reclassification issues set review state but are not
fatal. Missing evidence, an unmaterializable schema, or structurally corrupt data
remain fatal under the existing validation contract.

## Implementation boundaries

The implementation may change the deterministic chart digitization gate,
materializer, normalization/report integration, and their tests. It must not change
the prompt baseline, OCR clients, provider request behavior, or Alpha25 output schema.

The materializer and gates must remain deterministic and bounded. They must not add
model calls. Their expected complexity is linear or near-linear in anchors, facts,
and chart points.

## Verification

### Unit and integration tests

Tests must cover:

- rejecting process, dataset, phase, region, specimen, and empty-reference identities;
- retaining source-labelled independent sample codes while treating ordinary
  orientation prose as context;
- excluding thermodynamic and mechanism statements from composition;
- routing grain size, phase fraction, and related structural measurements to
  structure;
- reconciling core tensile aliases while preserving raw condition fields;
- quarantining unresolved owners without cross-state broadcast;
- quarantining invalid chart points or series while retaining their CSV references;
- extending the existing issues report without changing `final.json`; and
- preserving every existing relevant regression test.

### Frozen 30-paper regression

Rematerialize all existing task responses against the frozen OCR baseline and compare
the result with the same GT and the current production baseline. Acceptance requires:

- 30/30 papers complete with zero fatal validation failures;
- zero unsupported extracted facts;
- every removed, migrated, or quarantined fact has an issues record;
- unique four-axis macro recall does not fall more than `0.005` from the current
  `0.978` baseline;
- unique core-tensile recall does not fall below the current `0.633` baseline and is
  improved where evidence-derived owner reconciliation permits;
- known generic false-item, wrong-axis, and invalid-curve classes decrease;
- item count is not mechanically optimized against GT; and
- offline materialization runtime increases by no more than five percent relative to
  the current offline baseline.

The final report compares item count, issue classes, evidence audit, per-axis unique
metrics, core tensile metrics, and runtime before and after the repair.
