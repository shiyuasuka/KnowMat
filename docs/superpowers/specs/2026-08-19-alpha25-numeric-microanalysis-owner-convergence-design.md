# Alpha25 Numeric Microanalysis Owner Convergence

## Goal

Recover measured EDS microanalysis rows that GLM-5.2 already extracted correctly
but the paper-level materializer quarantines because the row owner is only a
numeric observation location such as `1`, `2`, or `14`. The repair must move
production output toward the adjudicated GPT-5.6-sol expert ledger without
reading that ledger at runtime, changing the professionally reviewed prompt, or
changing the `final.json` schema.

The v22 production baseline is the regression reference. It has 30/30
promotable papers, zero fatal validation issues, 6,593 unique system claims,
1,404 unique loose matches (F1 `0.289903`), and 676 unique strict matches (F1
`0.139583`). Composition has 550 unique loose matches (F1 `0.583245`) and 284
unique strict matches (F1 `0.301166`).

## Evidence audit

The v22 residual queue exposes two different failure classes:

- `paper_019` contains 14 complete measured EDS rows. Each row has eight
  numeric elemental values and a literal numeric table column. The paper text
  associates Points 2-14 with one source sample family and processing state;
  Point 1 lacks equally strong text-only ownership evidence.
- `paper_018` mixes fatigue specimen numbers, FIB subsamples,
  characterization locations, and facts with no reported owner. It needs a
  separate specimen/condition design and is outside this version.

An offline, GT-blind production simulation for `paper_019` shows that recovering
Points 2-14 adds 104 raw claims and 104 raw loose matches. Unique loose matches
increase by 101 because the current evaluator collapses a small number of
scientifically distinct observation locations. The simulated paper-level raw
loose F1 rises from `0.376289` to `0.568182`; unique loose F1 rises from
`0.381344` to `0.578313`.

## Considered approaches

1. **Production recovery only.** This restores source-grounded facts, but the
   current offline projector replaces the material sample with `Point n` and
   then reports a false strict-attribution regression.
2. **Production recovery plus a separately reported evaluator semantic repair
   (selected).** This restores the facts and represents material owner and
   observation location as two independent dimensions during offline scoring.
3. **Recover numeric EDS and fatigue specimen tables together.** Rejected for
   this version because a fatigue specimen is a test-condition entity, whereas
   an EDS point is an observation location. Combining the two would enlarge the
   rule surface and increase wrong-owner risk.

## Production architecture

### 1. Numeric observation recognition

A fact is eligible only when all of the following are true:

- it is a `composition_observation` with `source_type=measured` and
  `data_source=table`;
- its outer or observation sample label is a bare positive integer;
- the cited table evidence contains that integer as a literal column or row
  location, not merely as a measured value;
- the measurement or table evidence explicitly denotes EDS/EDX elemental
  point, spot, area, or location analysis; and
- the observation contains at least two named components with reported numeric
  values.

A bare number in a fatigue, process, structure, or generic property table is
never eligible. A single-element value, prose-only number, model-reported state,
or number absent from the cited table header remains unresolved.

### 2. Source-backed location map

The materializer builds a paper-local map from numeric observation locations to
sample descriptors. It uses only complete source text and inventory anchors.
The map may use:

1. a sentence or paragraph block that explicitly names one material/sample
   family and one processing state while naming one or more EDS points;
2. a figure/table caption that names the analyzed sample and state, when the
   associated prose provides an unambiguous point group; and
3. a shortened state such as `sintered and aged` only when the same sample
   family has exactly one Target inventory owner with that state category.

The resolver normalizes typographic variants such as `Point 3`, `point 3`, and
the bare table header `3`, but does not infer a missing point from sequence,
adjacency, a GT entry, or a presumed figure-panel boundary. Conflicting source
descriptors remove the location from the resolved map.

### 3. Unique owner selection

For an eligible location, the resolved source descriptor must select exactly one
Target owner in the existing identity index. Selection requires compatible
sample-family evidence and a compatible state descriptor. Numeric state
qualifiers in the source and inventory must agree. A direct source-named sample
wins over a generated state presentation only when both identify the same
canonical target. Two compatible targets remain unresolved.

The recovered fact keeps the normalized observation label `Point n` inside the
composition observation and routes the fact to the selected material item. It
does not create a Point material item or alter any elemental value, unit, or
source type.

### 4. Audit and serialization

Successful migrations are grouped by target owner in the existing validation
artifacts under issue code `numeric_microanalysis_owner_recovered`. Each record
stores:

- all original fact payloads;
- original and selected owners;
- normalized observation locations;
- source text used for location-to-sample binding;
- selected inventory-owner evidence; and
- any corrected material state.

Unresolved rows retain `unresolved_sample_alias`. Internal routing markers are
consumed before serialization. No `quality_audit.json` is added, and the
`final.json` envelope, paths, and field names remain unchanged.

## Offline evaluator semantics

The evaluator change is independent of production materialization and receives
no access to runtime routing decisions or GT labels. For composition
observations whose `sample_id` is a literal Point/Spot/Area/Location label, the
projector retains:

- the outer item `Sample_ID` as the material/specimen owner; and
- the observation label as the observation location.

Owner comparison treats equivalent observation labels across `sample_id` and
`region` as the same location because the expert ledger legitimately uses both
representations. A location-only label never conflicts with a specimen label in
the other representation. Non-location sample IDs and true morphological
regions retain the existing conflict rules.

Unique-claim deduplication includes the normalized observation location so two
EDS points with equal elemental values do not collapse. All other evaluator
semantics and thresholds remain unchanged.

Every result report must separate:

1. the v22 and v23 production outputs scored with the corrected evaluator;
2. the frozen legacy-evaluator result for audit; and
3. the evaluator-only movement obtained by rescoring unchanged v22.

## Error handling and safeguards

- Production code must not contain paper titles, material names, point ranges,
  expected GT values, model names, or provider branches.
- The adjudicated expert GT is used only after materialization for evaluation.
- Point 1 in the audited paper remains quarantined unless the generic resolver
  proves it from the source under the same rules.
- `paper_018` numeric fatigue rows remain quarantined in this version.
- No existing claim is removed to improve precision.
- The deterministic pass is linear or near-linear in source lines, locations,
  inventory anchors, and facts, and adds no OCR, VLM, or LLM request.

## Testing

Focused production tests cover:

- a numeric multi-element EDS table row uniquely bound by prose to one target;
- multiple points bound to one source-backed sample/state group;
- a shortened state resolving to exactly one compatible Target owner;
- typographic Point/spot/area/location variants;
- a missing table header, single-element row, non-EDS table, prose-only number,
  unsupported model state, conflicting prose, and multiple compatible owners;
- preservation of Point as observation location without creating a material;
- complete grouped audit payloads and no internal-marker leakage; and
- the audited Point 1 and fatigue-table shapes remaining unresolved.

Focused evaluator tests cover:

- outer material owner plus observation location projection;
- cross-representation location equivalence;
- continued conflicts between two explicit, incompatible specimen owners;
- continued distinction between observation location and morphological region;
- location-aware unique deduplication; and
- no change for ordinary composition, processing, structure,
  characterization, or property claims.

## Rollout and acceptance

First rematerialize the single highest-signal paper from the frozen 405-task
cache and inspect every recovered row and audit record. Then rematerialize all
30 papers and compare byte-level changes excluding commit provenance.

Acceptance requires:

- 30/30 promotable papers, zero fatal issues, and zero invalid task-cache files;
- zero new OCR, VLM, or LLM requests;
- unchanged prompt digest, schema `material_extraction_v11.3.3`, skill
  `11.0.0-alpha.25`, and `final.json` envelope;
- no new material item for a Point and no `quality_audit.json`;
- every promoted numeric EDS row to satisfy the generic source-evidence gates;
- no production changes outside papers containing an eligible row, excluding
  commit provenance;
- no decrease in fairly rescored unique loose, unique strict, composition
  loose, or composition strict F1;
- no decrease in core-tensile metrics; and
- legacy-evaluator movement, evaluator-only movement, and actual production
  movement reported separately.
