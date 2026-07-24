# V11 Multi-Item Quality Repair Design

## Goal

Repair the quality regression introduced by bounded multi-item chunk extraction while
preserving its bounded request count and runtime. The repaired path must reuse the
existing chunk JSON files for validation, must not depend on the eight frozen examples
at runtime, and must not add another LLM call.

The primary acceptance signal is the frozen eight-paper comparison. The repair must
eliminate all locally repairable fatal issues, materially improve item and axis count
alignment, retain evidence, and avoid a regression in schema compatibility. Exact GT
counts are not a runtime rule because legitimate unseen papers can contain different
sample structures.

## Context and Root Causes

The current chunk merger keys items by the complete `Sample_ID`, `Role`, and
`Data_Nature`. The model gives the same physical material different descriptive IDs in
different chunks, such as `H230AM_as_ht`, `H230AM_900C_50h`, and
`H230AM_post_creep_900C_65MPa`. These condition suffixes are observations or test
conditions, not new material identities. Exact-string merging therefore inflated 21
reviewed items to 130 items and duplicated routes, parameters, compositions, and
properties.

The candidate preparation layer also accepts only a narrow set of provider aliases.
Valid composition facts become fatal issues when `component_type`, `value_kind`, or
`data_nature` uses a safe synonymous spelling. Structure observations are discarded
unless they already contain both a named entity and observation-level evidence, even
when the feature or entity contains usable evidence. This produced zero normalized
structure observations for several papers. Property deduplication ignores the target
identity and test context, causing both duplicated values and attachment drift.

## Considered Approaches

### A. Deterministic post-extraction reconciliation (selected)

Canonicalize and cluster item identities using explicit sample tokens, material/process
families, role, and experiment-defining conditions. Merge facts conservatively inside
each cluster and repair only safe schema aliases. This reuses cached chunk results,
adds no model calls, is deterministic, and can be tested directly.

### B. Restore discover-then-single-item extraction

Discover canonical targets first and make one extraction request per target. This gives
the model a stable identity contract, but restores the multiplicative request pattern
that caused the performance regression.

### C. Add an LLM reconciliation pass

Ask a model to merge all chunk items after extraction. This reduces local rules but adds
latency and quota usage, and makes the same cached inputs produce less reproducible
results.

## Architecture

### 1. Item identity reconciliation

Add a focused reconciliation module between chunk validation and candidate merging. It
will derive a conservative identity profile from each item:

- normalized sample ID tokens;
- material/alloy family;
- manufacturing family;
- explicit variant tokens such as delay value, wall/sample number, and named process
  family;
- role and data nature;
- evidence-supported status or test condition tokens.

Exact normalized IDs merge first. Alias IDs merge only when their stable family and
variant tokens agree and no explicit discriminator conflicts. Observation-only suffixes
such as heat-treatment, aging time, creep condition, oxidation condition, location, or
test orientation are retained in the attached facts rather than automatically creating
a new material. Explicitly different process routes, delay values, wall/sample numbers,
or reference roles remain separate. Orientation separates items only when another
stable sample discriminator proves that the paper treats the specimens as different
material targets.

The canonical ID is selected deterministically from the cluster: prefer IDs repeated
across chunks, then concise IDs containing the stable material/variant tokens, then the
first source order. No GT sample ID is consulted.

### 2. Axis-aware fact merging

Merge clustered items by semantic signatures rather than serialized JSON equality:

- process stages by canonical process code, role, and compatible parameter context,
  with parameter union and evidence union;
- process parameters by normalized key, numeric/raw value, and unit;
- composition observations by basis and normalized component tuples;
- structure observations by entity/feature identity and value;
- properties by property family, value, unit, method, and condition.

IDs and edges are regenerated after merging. Conflicting explicit values are preserved
as separate observations; identical facts only merge their evidence and confidence.

### 3. Safe vocabulary compatibility

Centralize safe aliases for composition `component_type`, component `value_kind`, and
component `data_nature`. Infer a missing value kind only from the supplied value shape:
range bounds imply `range`, a numeric value implies `scalar`, and non-numeric labels
imply `categorical`. Unknown or contradictory values remain reviewable rather than
being guessed.

### 4. Structure preservation

Recover `name_raw` from known provider fields, and recover feature evidence from the
feature, entity, or observation. Preserve an observation when it has a meaningful
entity or feature plus evidence anywhere in that observation. Do not require an entity
when the observation contains a named quantitative or categorical feature. Fill
`value_raw` from range bounds, scalar values, or categorical labels when lossless.

### 5. Property attachment and filtering

Property facts remain attached to the reconciled item that contributed them. Generic
literature/reference rows are not merged into target items. Deduplication includes the
normalized property family and test context. Conditions are used to distinguish valid
measurements, not to manufacture new sample identities.

## Data Flow

1. Load successful chunk candidates from cache or fresh extraction.
2. Coerce each chunk to the compact V11 candidate schema.
3. Build identity profiles and cluster compatible items across chunks.
4. Select canonical IDs and merge each axis semantically.
5. Run candidate preparation, safe alias repair, and structure preservation.
6. Invoke the frozen alpha.6 normalizer and validator unchanged.
7. Compare the rebuilt outputs with the frozen eight-paper GT.

## Failure Handling and Observability

Ambiguous identities are not merged. The reconciliation logger reports item counts
before and after clustering and the source IDs in each non-trivial cluster. Alias repair
counts and dropped-fact reasons are logged per axis. A paper with no valid process stage
continues to fail instead of being silently promoted.

## Testing

Focused unit tests cover:

- condition suffixes for one physical material merge without losing facts;
- explicit delay, wall/sample, process-family, and role discriminators stay separate;
- orientation remains a condition unless another stable sample discriminator requires
  separate targets;
- stage, parameter, composition, structure, and property semantic deduplication;
- all observed safe composition aliases normalize without fatal issues;
- feature-only structure observations survive and receive a lossless `value_raw`;
- ambiguous identities remain separate;
- the existing request bounds and cache identity tests remain unchanged.

Business-path verification rebuilds all eight outputs from `v11/02_chunks`, runs the
frozen normalizer/validator, and reruns `scripts/validate_v11_examples.py`. Verification
may iterate at most three repair rounds. Results must report both absolute counts and
the change from the pre-repair report; passing unit tests alone is insufficient.

## Scope Boundaries

This repair does not modify OCR, prompts, the frozen alpha.6 rule package, or the GT
examples. It does not hard-code paper titles or expected sample IDs. It does not add a
new LLM request or restore target discovery by default.
