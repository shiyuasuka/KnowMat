# Alpha25 v203 precision-first tensile ledger and bounded completion

## Status and objective

This design is the approved option 3 for improving the accepted GLM Alpha25
v202 baseline.  The primary objective is to increase loose F1 without reducing
precision, then improve strict owner/condition attribution and Target
core-tensile recall.  It addresses two remaining classes: incomplete tensile
protocol binding and source-explicit tensile cells that did not reach
materialization.

The change is deterministic and source-proven.  It does not modify the
professionally reviewed prompt, model/provider selection, OCR, VLM, line-chart
digitization, Alpha25 task schema, or public `final.json` structure.  It uses
the same frozen upstream task responses as v202 and therefore makes no model or
provider call during the acceptance replay.

Production code must not read GT, expected counts or values, paper IDs, paper
titles, provider names, or model names.  GPT expert GT and business GT are
offline diagnostic and evaluation inputs only.  A fact is never deleted merely
because either GT omits it.

## Frozen v202 baseline

The authoritative baseline is:

- output:
  `data/output-alpha25-v202-source-coordinate-converged-final30-20260824`;
- acceptance report:
  `data/experiments/alpha25-v202-source-coordinate-20260824/converged_v202_acceptance.md`;
- three-way evaluation:
  `data/experiments/alpha25-v202-source-coordinate-20260824/converged_v202_vs_gpt_expert_and_business.json`.

Against GPT expert GT, v202 has global loose precision/F1
`0.460618/0.312393`, global strict precision/F1 `0.280403/0.190171`, Target
core-tensile loose precision/F1 `0.904412/0.704871`, and Target core-tensile
strict precision/F1 `0.639706/0.498567`.  The matcher reports 225 owner
conflicts and 59 condition conflicts.

Against business GT directly, v202 has global loose/strict F1
`0.347273/0.181818` and Target core-tensile loose/strict F1
`0.720000/0.467692`.

The remaining GPT-expert residual queue contains 2,502 system-missing claims,
225 wrong-owner conflicts, 59 condition conflicts, 114 value conflicts, 32
unit conflicts, and 712 system claims that the expert ledger does not cover or
support.  The 712 records are an audit queue rather than 712 proven
hallucinations: source review shows that many are literal scientific facts.

For Target core tensile, v202 emits 136 unique claims and loosely matches 123,
leaving only 13 loose extras.  Most of those 13 have literal source support.
Approximately 35 loose-correct claims fail strict matching primarily because
test protocol dimensions are incomplete.  Business GT also identifies a
concentrated set of source-explicit tensile cells that v202 does not emit.
Therefore broad Property deletion is unsafe, while protocol repair and bounded
table completion offer a precision-preserving path to higher recall.

## Considered approaches

### 1. Prompt or model expansion

A prompt revision or additional model pass could recover more candidates but
would invalidate the reviewed prompt baseline, add latency and provider
variance, and risk recreating the over-projection problem.  It is outside this
iteration.

### 2. GT-driven subtractive filtering

Filtering all system-only records could improve a metric against one ledger,
but both expert and business GT omit source-supported claims.  It would also
encode evaluation artifacts in production behavior.  This approach is
rejected.

### 3. Source-proven protocol ledger, bounded table completion, and fail-closed
precision quarantine

This is the selected approach.  It binds tensile protocol dimensions only
from a unique compatible method event, completes only explicit cells from a
uniquely resolved structured table coordinate, and quarantines only records
whose own source coordinates prove a conflict or projection error.  It keeps
the prompt and upstream extraction frozen and preserves every action in the
existing audit output.

## Architecture

### Component 1: paper-level tensile protocol ledger

Build an immutable, paper-local ledger of source-literal tensile test events.
Each event keeps independent dimensions rather than one free-form condition:

- Target or Reference role;
- material owner and material/process state;
- tensile test family;
- temperature;
- loading, crosshead, or strain rate with rate type;
- testing machine;
- testing standard;
- specimen geometry and dimensions;
- loading/specimen orientation;
- environment;
- hold time; and
- replicate count.

An event is admitted only when the source contains a tensile-method trigger and
the event resolves to one bounded prose assertion, method paragraph, table
scope, or existing structured coordinate.  Each dimension retains its literal
evidence span and source coordinate.

The ledger classifies event scope as one of:

1. `owner_local`: an explicit owner/state/orientation is in the event;
2. `target_global`: the source explicitly declares the protocol for all
   compatible Target tensile specimens/results;
3. `reference_local`: a cited literature owner and its local protocol; or
4. `ambiguous`: more than one compatible owner, role, state, orientation, or
   test family remains.

Only the first three scopes can bind a fact.  Reference-local events never bind
Target facts, and Target events never bind Reference facts.  A heat-treatment
or fabrication temperature remains material state; it cannot become a test
temperature.  A test temperature remains condition; it cannot create a new
material owner.  Crosshead speed and strain rate are kept distinct and are not
converted without source-explicit geometry.

Binding uses compatibility over role, owner, state, orientation, test family,
and source scope.  Exactly one compatible event may contribute missing
dimensions.  Existing source-literal dimensions are preserved.  An explicit
conflict, two equally compatible events, or a `respectively` mapping without a
unique coordinate is a no-op and is sent to audit review.  Serialization is
stable, deduplicated, and uses the existing `Test_Condition` field.

### Component 2: deterministic dense tensile table completion

Extend the existing v202 logical table-coordinate index with a bounded
enumerator for explicit tensile result cells.  It may create a candidate only
when it proves one tuple:

`(table block, logical row, logical column, property, unit, owner, value)`.

Completion is allowed only when all conditions below hold:

- the table is literally present in the current paper source and has one
  unique block coordinate;
- the property is an explicit core-tensile semantic: yield strength, ultimate
  tensile strength, or tensile elongation/ductility;
- the unit is explicit in the same header path or value cell;
- the value is one exact numeric scalar or source-literal uncertainty/range
  accepted by existing normalization;
- one row/column/header path identifies one Target owner and, when present, one
  state and orientation;
- the logical cell is not a citation-only Reference cell;
- the coordinate is not already owned by an accepted scientific fact; and
- property, value, unit, owner, role, state, and orientation are mutually
  compatible without caption-only inference.

The completion pass does not enumerate prose numbers, infer values from plots,
interpolate curves, convert image pixels, promote continuous sidecar points,
or synthesize a missing owner/property/unit.  Citation-bearing Reference tables
continue through the existing Reference logic.  Ambiguous merged headers,
multiple possible owners, missing units, repeated values with no unique cell,
or conflicting row/column labels fail closed.

Every completed fact goes through the normal evidence, ownership, protocol,
deduplication, and materialization gates.  It does not bypass v202 safeguards.

### Component 3: coordinate-level precision quarantine

Run a final decision pass over existing and newly completed Property facts.
Quarantine is permitted only when the fact's own local source proves one of
these errors:

- `cross_owner_projection`: one coordinate was copied to an incompatible
  owner;
- `cross_cell_projection`: a value was paired with another cell's property,
  unit, state, or orientation;
- `semantic_projection`: a comparative or qualitative statement was emitted
  as an unsupported numeric scalar;
- `role_protocol_leakage`: a Reference inherited a Target protocol or the
  reverse;
- `explicit_coordinate_conflict`: accepted value/unit/condition contradicts
  its uniquely resolved source coordinate; or
- `same_coordinate_duplicate`: multiple records encode the same owner, axis,
  semantic, value, unit, and condition coordinate.

For exact duplicates, retain the richest source-grounded survivor.  For every
other class, remove the record from formal `Properties` without replacing it
with a guessed value or owner.  Source-supported claims absent from either GT
are preserved.  Structure, Processing, Characterization, and Composition do
not receive generic unmatched-record filtering.

### Component 4: audit and public output compatibility

`final.json` retains its current structure and field names.  No private source
coordinates or decision metadata are added to it.

All mutations are written to the existing per-paper `quality_audit.json` with:

- stable decision key and reason code;
- action: `recovered`, `condition_enriched`, `merged`, or `quarantined`;
- complete before and after records;
- owner/role/state/orientation candidates;
- source block and logical cell or evidence span;
- protocol event and contributed dimensions;
- conflict candidates, if any; and
- deterministic rationale.

Required reason codes are:

- `tensile_protocol_ledger_bound`;
- `tensile_protocol_ledger_ambiguous`;
- `dense_tensile_table_cell_recovered`;
- `dense_tensile_table_cell_rejected`;
- `property_cross_owner_projection_quarantined`;
- `property_cross_cell_projection_quarantined`;
- `property_semantic_projection_quarantined`;
- `property_role_protocol_leakage_quarantined`;
- `property_coordinate_conflict_quarantined`; and
- `property_same_coordinate_duplicate_merged`.

The existing `issues.json` and `issues.md` receive only the short reason code,
record locator, and review flag.  They do not duplicate the complete audit
payload.

## Data flow and integration boundaries

The materialization flow is:

1. read one paper's frozen task candidates and frozen source context;
2. build the existing v202 logical source-coordinate index;
3. build the tensile protocol ledger from bounded source events;
4. enumerate eligible structured tensile cells and reject ambiguity;
5. combine original and completed candidates;
6. bind only uniquely compatible missing protocol dimensions;
7. apply coordinate-level duplicate/conflict quarantine;
8. write the unchanged `final.json` and complete audit outputs.

The source-coordinate parser remains a focused Alpha25 component.
Materialization remains the sole public-output writer.  GT evaluators remain
outside the production call graph.  Offline rematerialization must explicitly
receive each paper's source directory and must not search arbitrary workspace
paths.

Add independently shadowable, default-on switches:

- `KNOWMAT2_ALPHA25_TENSILE_PROTOCOL_LEDGER_V203`;
- `KNOWMAT2_ALPHA25_DENSE_TENSILE_TABLE_COMPLETION_V203`; and
- `KNOWMAT2_ALPHA25_PROPERTY_COORDINATE_QUARANTINE_V203`.

With all three switches off, the same frozen inputs must reproduce v202 bytes.
If an acceptance gate fails, narrow or disable the responsible switch rather
than weakening a metric or source-safety requirement.

## Error handling and safety

Missing sources, malformed tables, unsupported encodings, invalid numeric
cells, incomplete protocol events, ambiguous coordinates, and audit write
problems must not silently create facts.  Candidate-level ambiguity is a
reason-coded no-op.  A paper-level inability to write its required audit is a
paper failure rather than an unaudited success.

No sidecar or source path may escape the explicit paper source directory.
Continuous line-chart data remain externalized and are never expanded into
Properties by v203.  The implementation may not call a provider, modify frozen
task responses, or use GT during materialization.

## Verification strategy

### Unit and invariant tests

Tests must cover:

- owner-local, Target-global, and Reference-local protocol events;
- temperature, rate type, standard, machine, geometry, orientation, hold time,
  and replicate count binding;
- state-versus-test-condition separation;
- ambiguous and conflicting events as no-ops;
- Markdown and HTML dense tables, including `rowspan`/`colspan`;
- unique Target cells and every fail-closed table condition;
- duplicate merge and each quarantine reason code;
- Reference/Target protocol isolation;
- continuous chart sidecars as mandatory no-ops;
- stable audit keys under input-order permutations;
- switches-off v202 byte compatibility; and
- no production dependency on GT, paper ID/title, provider, or model name.

All pytest commands use `-o addopts=''` so repository defaults do not hide or
alter the intended test selection.

### Source-audited pilot

Before the 30-paper replay, run a bounded pilot covering the diagnosed
condition gaps, dense Target tensile tables, a citation-heavy Reference table,
and a continuous-chart negative control.  Inspect every changed Property and
its audit record against source.  Any wrong owner, role, state, orientation,
value, unit, or protocol contribution fails the responsible switch.

### Thirty-paper acceptance replay

Using the same frozen upstream responses and unchanged evaluator rules, require:

| Gate | Requirement |
|---|---:|
| Papers / fatal / silent-empty | 30 / 0 / 0 |
| Provider/API calls | 0 |
| GPT expert global loose precision | `>= 0.460618` |
| GPT expert global loose F1 | `> 0.312393` |
| GPT expert global strict precision | `>= 0.280403` |
| GPT expert global strict F1 | `>= 0.190171` |
| GPT expert Target core-tensile loose precision | `>= 0.900000` |
| GPT expert Target core-tensile loose recall/F1 | both greater than v202 |
| GPT expert Target core-tensile strict precision | `>= 0.639706` |
| GPT expert Target core-tensile strict recall/F1 | both greater than v202 |
| Wrong-owner conflicts | `<= 225` |
| Condition conflicts | `< 59` |
| Direct business-GT Target core-tensile loose F1 | `> 0.720000` |
| Direct business-GT Target core-tensile strict F1 | `> 0.467692` |
| Composition payload | byte-identical for 30/30 papers |
| Prompt/schema/upstream responses | hash-identical to v202 |
| Deterministic replay | `final.json`, `quality_audit.json`, summaries byte-identical |
| Mean rematerialization runtime regression | `<= 20%` versus v202 |

Global and core matched counts must not fall below v202.  No already matched
claim may be removed unless its own source audit proves an explicit coordinate
error and the acceptance report lists that exception.  Evaluator thresholds,
GT inputs, and matcher rules are frozen before the replay.

## Deliverables

- focused implementation and regression tests;
- one v203 30-paper output and one deterministic replay output;
- per-paper unchanged `final.json`, complete `quality_audit.json`, and concise
  `issues.json`/`issues.md`;
- GPT expert, business GT, and three-way comparison artifacts;
- a source-audited delta ledger for every recovered, enriched, merged, or
  quarantined Property; and
- an acceptance report that records runtime, API count, hashes, test results,
  metrics, and any disabled/narrowed switch.

## Non-goals

- changing the reviewed extraction prompt;
- changing GLM model/provider configuration;
- rerunning OCR, VLM, line-chart extraction, or upstream LLM extraction;
- changing Alpha25 or `final.json` schemas;
- deriving dense points from continuous curves;
- broad filtering of GT-unmatched records; or
- paper-specific rules, expected values, titles, or IDs in production code.
