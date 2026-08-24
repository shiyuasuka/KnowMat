# Alpha25 v202 source-coordinate tensile convergence

## Status and objective

This design continues the approved precision-first GLM-5.2 Alpha25 baseline
after v201.  Its objective is to move overall loose F1 and Target core-tensile
quality toward the business GT and the adjudicated GPT expert ledger while
improving material owner, state, orientation, and test-condition attribution.

The change must preserve GLM's current Composition advantage and may not obtain
precision by deleting already matched facts.  It therefore combines bounded
source-coordinate recovery with stricter one-to-one ownership rather than a
new prompt, a second model pass, or count-driven filtering.

The production implementation must not read GT, expected counts, paper IDs,
paper titles, provider names, or model names.  GT is used only to locate error
classes for this offline design and to evaluate a frozen A/B replay.

## Frozen v201 baseline

The authoritative production baseline is:

- output:
  `data/output-alpha25-glm52-v201-gates-on-final30-20260824`;
- GPT-expert comparison:
  `data/experiments/glm53-v201-20260824/glm52_v201_gates_on_final30_dual_gt.json`;
- direct business-GT comparison:
  `data/experiments/glm53-v201-20260824/glm52_v201_gates_on_vs_business_gt.json`;
- deterministic replay:
  `data/output-alpha25-glm52-v201-gates-on-final30-replay-20260824`.

Against the adjudicated GPT expert ledger, unique scientific claims are:

| Metric | Matched / system / expert | Precision | Recall | F1 |
|---|---:|---:|---:|---:|
| Global loose | 649 / 1505 / 3093 | 0.431229 | 0.209829 | 0.282297 |
| Global strict | 357 / 1505 / 3093 | 0.237209 | 0.115422 | 0.155285 |
| Target core-tensile loose | 88 / 101 / 213 | 0.871287 | 0.413146 | 0.560510 |
| Target core-tensile strict | 55 / 101 / 213 | 0.544554 | 0.258216 | 0.350318 |

Against business GT directly, the same GLM output has global unique loose F1
`0.328856`, strict F1 `0.176934`, Target core-tensile loose F1 `0.634483`, and
Target core-tensile strict F1 `0.386207`.

The v201 GPT-expert residual queue contains 712 loose-unmatched system claims,
including 349 Structure claims.  It also contains 225 owner conflicts and 65
condition conflicts.  Owner conflicts are concentrated in Composition (118)
and Processing (56); condition conflicts are concentrated in Properties (57),
including 40 YS/UTS/elongation records.  These counts are diagnostic, not
permission to delete the records.

Source review found three concentrated recovery classes among 105 missing
claims with tensile semantics:

1. Twenty Target UTS/total-elongation cells were already extracted from one
   complex HTML table, but the evidence gate rejected their synthetic
   multi-level header because it is not one literal source row.
2. Twenty-one Target tensile cells are present in a small, discrete,
   source-referenced chart CSV.  The full CSV is correctly externalized from
   the LLM context, but no deterministic consumer promotes its categorical
   rows.
3. Twenty-seven literature tensile cells are present in a complex comparison
   table with column owners, row-spanning property names, and per-cell
   citations.  They improve global recall but remain Reference facts and do
   not count as Target core tensile.

These examples motivate general source contracts.  Runtime logic must not
contain their paper IDs, values, expected row counts, or GT owners.

## Considered approaches

### 1. Further subtractive precision gates

Removing broad unmatched Structure or Property groups could raise measured
precision, but expert and business ledgers are incomplete and many unmatched
facts are source-supported.  This approach risks losing the current 649 loose
matches and does not repair core-tensile recall.  It is rejected.

### 2. Owner/condition rewriting only

Source-bounded owner and condition repair can improve strict attribution, but
it cannot recover table and sidecar facts that never reached materialization.
It does not address the largest safe tensile recall opportunities.  It is
insufficient by itself.

### 3. Source-coordinate recovery plus guarded attribution

This is the selected approach.  It recovers only uniquely addressable table or
small categorical sidecar cells, then uses the same coordinate ledger to bind
owner, state, orientation, role, and tensile protocol.  It also prevents one
cell or assertion from being copied across owners or axes.  It requires no
model call and preserves the reviewed prompt and public schema.

## Architecture

### Component 1: logical table-cell coordinate recovery

Add a reusable logical-table index that supports both Markdown tables and HTML
tables with `rowspan` and `colspan`.  It expands presentation spans into a
logical grid while retaining every original row, cell, and source locator.

For each candidate whose evidence contains a projected header path and data
row, the resolver attempts to prove one tuple:

`(table block, logical row, logical column, header path, owner path, value cell)`.

Recovery is allowed only when:

- the table block is uniquely identified in the current source;
- the projected data cells occur in order within one logical data row;
- the property semantic and unit resolve from one logical header path;
- the candidate value resolves to exactly one compatible cell;
- the candidate owner resolves to one literal row or column label;
- merged cells do not create multiple possible coordinates; and
- no accepted fact already owns the same scientific coordinate.

Unlike v201's row-only projection, the header path may span several original
rows.  The evidence gate validates the header and data row as one table-cell
relation rather than requiring each synthetic evidence line to be a literal
source row.  This component recovers existing extracted candidates; it does
not synthesize a property that the candidate inventory never contained.

Near matches, reordered values, repeated compatible cells, missing units,
conflicting row/column owners, and multiple table blocks fail closed.  The
original rejection remains fully auditable.

### Component 2: bounded discrete-chart sidecar promotion

The current chart pipeline correctly writes complete digitized data to a CSV
sidecar and gives the LLM only bounded key points.  v202 adds a deterministic
consumer for small categorical result tables without inlining the CSV into the
prompt.

A sidecar is eligible only when all of the following hold:

- the Markdown source contains one literal `data_csv:` reference to it;
- the resolved file is a regular file below the paper's own source directory;
- the CSV has at most 32 data rows, 12 columns, and 192 non-empty data cells;
- headers identify one or more core tensile properties with explicit units;
- every promoted row contains a literal condition/state label and, when the
  table distinguishes it, an orientation label;
- numeric cells parse exactly under existing value/unit normalization; and
- one existing base Target material or a unique source-literal child of that
  base owns the result.

Continuous curve sidecars are mandatory no-ops.  A CSV is treated as
continuous when it contains `series` plus `kind` with values such as `trend`,
`curve`, or `line`, when repeated x-coordinates describe sampled trajectories,
or when its shape exceeds the categorical caps.  No curve point, interpolated
point, endpoint, extremum, or derived tensile value is promoted by this
component.  This preserves the existing protection against context explosion
and over-detailed curve extraction.

The component may create a Property candidate only from the literal CSV row,
header, and unit.  It may create a source-derived child owner only when the row
label is literal, the base Target material is unique, and the state/orientation
split is unambiguous.  It may not infer a value, semantic, unit, owner, state,
or condition from a caption alone.

### Component 3: owner, state, role, and orientation ledger

All accepted and recovered coordinates pass through one paper-level ownership
ledger before final promotion.

The ledger keeps these dimensions separate:

- base material identity;
- source-literal sample or condition label;
- material/process state;
- specimen orientation or region;
- Target versus Reference role; and
- tensile test condition.

Owner precedence is:

1. a unique table row/column owner at the value cell;
2. a unique prose grammatical subject in the same assertion;
3. a source-declared child state/orientation of one existing base owner;
4. a unique existing anchor with an exact source alias; or
5. unresolved.

A processing parameter belongs to the explicitly produced specimen/state, not
to a powder feedstock or a generic Reference simply because that anchor is
nearby.  A temperature suffix used as a test coordinate remains a test
condition; it does not automatically create a new material owner.  Conversely,
an explicit heat-treatment label remains material state and is not serialized
as tensile temperature.

For literature comparison tables, the column material/process family and the
cell's own citation or standard jointly identify a Reference owner.  A
row-spanning property label may apply to several rows, but a citation-bearing
cell applies only to its own Reference.  Reference values never inherit a
current-paper Target protocol.

When two owners, states, roles, or orientations remain possible, no reassignment
or recovery occurs.  The ledger cannot broadcast a generic fact to children or
collapse distinct children into a base item.

### Component 4: structured tensile protocol binding

Represent a candidate protocol internally as independent source-literal
dimensions:

- test family;
- temperature;
- loading or strain rate;
- machine;
- standard;
- specimen geometry;
- loading orientation;
- environment;
- hold time; and
- replicate count.

Bind dimensions only from the same bounded method event when that event is
owner-specific or explicitly global to the relevant Target tensile set.  Table
or sidecar coordinates must agree with the protocol's role, state, orientation,
and test family.  Multiple protocols, `respective` mappings without a unique
coordinate, explicit conflicts, and cross-family proximity are no-ops.

Missing optional dimensions do not invalidate a locally grounded tensile
value.  An explicit contradiction is isolated or preserved for review rather
than silently overwritten.  Serialization is stable and source-literal: each
dimension appears once, so forms such as `RT | RT` are eliminated without
inventing fuller wording.

### Component 5: coordinate-level precision gates

The same source-coordinate ledger prevents over-projection:

- one table/sidecar cell cannot materialize on several owners without explicit
  shared-owner grammar;
- one assertion cannot materialize on several axes when a unique dominant axis
  is source-proven;
- exact same-coordinate table/prose copies merge into one richer survivor;
- a core-tensile numeric value must still occur in its local source evidence;
- Reference and Target coordinates never merge; and
- explicit owner/state/value/unit/condition conflicts remain quarantined.

There is no generic deletion of unmatched Structure or Characterization facts
in v202.  Such deletion would conflate GT omission with hallucination and is
not needed to validate the selected source-coordinate recovery.

## Integration and feature switches

Implement the reusable logical coordinate parser in a focused Alpha25 module
rather than adding more paper-specific branches to `promotion.py` or
`materialize.py`.  Evidence validation consumes the logical table index;
promotion consumes its immutable coordinate decisions; materialization remains
the sole writer of `final.json`.

Sidecar ingestion receives an explicit paper source directory from live and
offline runners.  It never searches arbitrary workspace paths.  Cache-only
rematerialization copies or references the frozen source sidecars and performs
no provider call.

Add independent, default-on, shadowable switches:

- `KNOWMAT2_ALPHA25_STRUCTURED_TABLE_CELL_RECOVERY_V202`;
- `KNOWMAT2_ALPHA25_DISCRETE_CHART_SIDECAR_V202`;
- `KNOWMAT2_ALPHA25_OWNER_STATE_CONDITION_V202`; and
- `KNOWMAT2_ALPHA25_SOURCE_COORDINATE_PRECISION_V202`.

Each switch state is recorded in rematerialization metadata.  Gates-off and
gates-on therefore use the same code revision and frozen model responses.

## Data flow and failure behavior

1. Build the existing inventory and candidate facts from frozen or live model
   responses.
2. Build the Markdown/HTML logical-table index and bounded sidecar inventory.
3. Re-evaluate eligible evidence rejections as complete table-cell relations.
4. Generate eligible discrete-sidecar Property candidates.
5. Resolve owner/state/role/orientation on one immutable coordinate ledger.
6. Bind compatible tensile protocol dimensions.
7. Apply coordinate-level duplicate, axis, fan-out, and conflict gates.
8. Materialize the accepted facts through the unchanged public writer.
9. Serialize complete audit decisions and concise issue codes.

A malformed table, CSV, source path, value, or candidate affects only its local
decision.  It never aborts the paper and never produces a partial fact.  A
candidate-local exception leaves the v201 fact set unchanged and records a
review issue.  Missing sidecars and unsafe paths are no-ops.

## Audit contract

Every recovery, creation, reassignment, merge, or quarantine stores:

- the complete original candidate, or literal sidecar row for a new candidate;
- survivor before/after when applicable;
- table/sidecar path and content hash;
- source block, logical row/column, header path, owner path, and value cell;
- candidate owners and rejected alternatives;
- role/state/orientation/condition compatibility decisions;
- protocol dimensions and scope cue;
- deterministic decision key;
- `owner_invented=false` for existing owners, or
  `owner_created_from_source_literal=true` for an eligible child owner; and
- the final reason and issue severity.

Stable issue codes include:

- `evidence_structured_table_cell_recovered`;
- `evidence_structured_table_cell_ambiguous`;
- `discrete_chart_property_recovered`;
- `discrete_chart_sidecar_rejected`;
- `continuous_curve_sidecar_not_promoted`;
- `source_literal_owner_state_recovered`;
- `tensile_protocol_coordinate_recovered`;
- `source_coordinate_duplicate_quarantined`; and
- `source_coordinate_conflict_quarantined`.

The full records remain in `quality_audit.json`; concise codes continue through
the existing `issues.json`/`issues.md` path.  `final.json` receives no new
field.

## Compatibility and invariants

- The professionally reviewed extraction prompts remain byte-identical.
- The Alpha25 task schema and public `final.json` schema remain unchanged.
- GLM-5.2 remains the default model; no model/provider branch is added.
- OCR, VLM, chart digitization, and continuous-curve point budgets are
  unchanged.
- No second model pass, verifier call, voting run, or additional API call is
  introduced.
- Composition output must be byte-identical for all 30 papers.
- Correct v201 facts and audit history remain unless a v202 source coordinate
  proves a more precise owner or one duplicate survivor.
- Runtime code never reads either GT or expected evaluation values.
- `quality_audit.json` retains every removed, migrated, or created record.
- Output and audit ordering are deterministic under input-order permutations.

## Testing strategy

### Logical table tests

- positive multi-row `rowspan`/`colspan` header plus unique data cell;
- Markdown and HTML equivalence;
- per-cell citation and column-owner Reference routing;
- repeated values in different columns, ambiguous merged cells, reordered
  evidence, missing units, conflicting owners, and duplicate tables as no-ops;
- exact input-order and source-order determinism; and
- full reversible audit payloads.

### Sidecar tests

- positive small categorical tensile CSV with state and orientation;
- multiple eligible tensile columns in one row;
- state/orientation child-owner construction from one literal base;
- continuous `series,kind,x,y` CSV as a mandatory no-op;
- row/column/cell caps, malformed CSV, missing units, duplicate headers,
  nonnumeric values, missing owner labels, missing files, path traversal,
  symlinks outside the paper root, and hash changes;
- no full CSV injection into the model prompt; and
- no mutation of line-chart extraction settings.

### Owner and condition tests

- Target table rows with unique state and temperature separation;
- process parameters reassigned from feedstock/Reference to the literal produced
  specimen;
- Reference cell citations that do not inherit Target protocol;
- global versus owner-specific tensile methods;
- duplicate condition fragments and compatible partial protocols;
- explicit rate, temperature, orientation, state, and role conflicts as no-ops;
- fatigue `all specimens` not authorizing tensile; and
- missing optional protocol detail preserving a locally grounded result.

### Regression and replay

Run focused evidence, coordinate, promotion, property-context,
materialization, package, CLI, and evaluator tests; all Alpha25 tests; then the
full repository suite.  Pilot the source classes represented by the complex
Target table, discrete chart table, and cited Reference table, plus negative
fatigue and continuous-line examples.  Inspect every pilot semantic change
before the 30-paper replay.

## Thirty-paper A/B acceptance

Arm A is the frozen v201 gates-on output.  Arm B rematerializes the exact same
task responses with all v202 switches enabled and provider access disabled.
A second Arm B replay must be byte-identical.

The implementation is accepted only if all of the following hold against the
adjudicated GPT expert ledger:

- global unique loose matched count is at least 649, precision is greater than
  `0.431229`, and F1 is greater than `0.282297`;
- global unique strict matched count is at least 357, and strict precision and
  F1 do not regress from `0.237209` and `0.155285`;
- Target core-tensile loose matched count is greater than 88, precision is at
  least `0.871287`, and F1 is greater than `0.560510`;
- Target core-tensile strict matched count is greater than 55, precision is at
  least `0.544554`, and F1 is greater than `0.350318`;
- matcher owner and condition conflict counts do not increase, and at least one
  decreases after source review;
- Composition is byte-identical in all 30 outputs;
- every semantic delta is explained by a v202 audit decision; and
- source review finds no new systematic wrong-owner, wrong-role, wrong-state,
  condition-conflict, sidecar-point, or cross-cell projection.

Run the identical one-to-one comparison against business GT and report all
global, per-axis, and Target core-tensile metrics.  Business-GT results are a
second evaluation view, not a runtime tuning input.  A claim-count increase or
decrease alone is not evidence of improvement.

Operational acceptance additionally requires:

- 30/30 papers, zero fatal or silent-empty outputs;
- zero provider/API calls during rematerialization;
- unchanged prompt, task schema, public `final.json` schema, and Composition;
- replay byte identity for `final.json`, `quality_audit.json`, and summary;
- no more than 20% rematerialization wall-time regression versus the v201
  deterministic replay, unless separately justified by measured table count;
  and
- unchanged live extraction call count and chart context budget.

If any gate fails, disable or narrow the responsible independent v202 switch.
Do not compensate by altering GT matching rules, changing the professional
prompt, broadly deleting another axis, or promoting continuous curve points.

## Out of scope

This increment does not switch to GLM-5.3, revise the extraction prompt or
schema, rerun OCR/VLM, regenerate chart CSVs, adopt a new schema package,
introduce an LLM judge, extract full continuous curves into Properties, or
attempt a generic cleanup of every residual Structure/Characterization claim.
Those require separate isolated designs and acceptance gates.
