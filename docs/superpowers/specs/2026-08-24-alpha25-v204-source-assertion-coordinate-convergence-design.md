# Alpha25 v204 source-assertion coordinate convergence

## Status and objective

The user approved the precision-first v204 direction on 2026-08-24.  This
iteration improves the accepted Alpha25 v203 baseline without changing the
professionally reviewed extraction prompt or making another model call.

The objective is to increase global loose F1 and Target core-tensile
recall/F1 while preserving or improving precision.  The implementation must
reduce unsupported fanout, owner leakage, and condition conflicts from local
source evidence.  It must not increase recall by copying one assertion to
multiple owners or by expanding qualitative comparisons into numeric facts.

Production code must not read GT, matcher output, expected counts or values,
paper IDs, paper titles, provider names, or model names.  GPT expert GT and
business GT remain offline evaluation inputs only.  A GT-unmatched fact is not
evidence of hallucination and cannot be removed for that reason.

## Frozen v203 baseline

The authoritative baseline is:

- output:
  `data/output-alpha25-v203-precision-tensile-accepted-final30-20260824`;
- deterministic replay:
  `data/output-alpha25-v203-precision-tensile-accepted-replay30-20260824`;
- acceptance report:
  `data/experiments/alpha25-v203-precision-tensile-20260824/accepted_v203_acceptance.md`;
- three-way evaluation:
  `data/experiments/alpha25-v203-precision-tensile-20260824/accepted_v203_vs_gpt_expert_and_business.json`.

Against GPT expert GT, v203 has:

| Metric | v203 |
|---|---:|
| Global loose precision / recall / F1 | `0.462312 / 0.231156 / 0.314194` |
| Global strict precision / recall / F1 | `0.287060 / 0.143530 / 0.195091` |
| Target core-tensile loose precision / recall / F1 | `0.907801 / 0.600939 / 0.723164` |
| Target core-tensile strict precision / recall / F1 | `0.702128 / 0.464789 / 0.559322` |
| Wrong-owner / condition conflicts | `225 / 52` |
| System missing / expert-uncovered system claims | `2497 / 712` |

Against business GT directly, v203 has global loose/strict F1
`0.349149/0.184336`, Target core-tensile loose/strict F1
`0.739394/0.496970`, and Composition loose/strict F1
`0.521576/0.320826`.

The 30-paper source audit shows that the 712 expert-uncovered system claims are
not a uniform hallucination set.  Only eight are Target core-tensile claims,
and many non-core records are literal source facts outside the expert ledger.
The core-tensile residual is instead concentrated in 36 missing expert claims,
28 condition conflicts, and four wrong-owner conflicts.  Explicit missing
tensile bundles occur in bounded prose assertions, continuation assertions,
ordered owner/value comparisons, and structured tables.  Global wrong-owner
residuals are dominated by Composition and Processing; Composition is frozen
because it is already the strongest GLM axis and a broad owner rewrite would
create unacceptable regression risk.

## Considered approaches

### 1. Source-assertion coordinate ledger and fail-closed fanout control

This is the selected approach.  Build deterministic coordinates from literal
source blocks, recover only complete numeric tensile assertions, bind each
coordinate to one proven owner/state/condition, and quarantine only a proven
projection conflict.  It uses the same 405 frozen task responses, adds no API
latency, remains model-independent, and can be shadowed or rolled back by
component.

### 2. Secondary LLM verifier

A second model pass could judge owner and condition ambiguity with broader
language coverage.  It also adds provider cost and latency, introduces another
nondeterministic failure surface, and couples production behavior to a model.
It is outside v204 and may be evaluated later as an isolated experiment.

### 3. Prompt revision and upstream re-extraction

A prompt change could improve candidate recall but would invalidate the
professionally reviewed prompt baseline and confound post-processing effects
with model effects.  It is outside v204.

## Architecture

### Component 1: bounded tensile assertion coordinates

Add an immutable, paper-local `TensileAssertionCoordinate` representation for
one complete literal source assertion.  A coordinate retains:

- source block and exact evidence span;
- property semantic and literal value/unit;
- owner label, role, material state, and orientation when present;
- test-condition dimensions when present;
- assertion family and coordinate type;
- source positions for every owner/property/value pairing; and
- stable coordinate and decision keys.

Only the three core tensile semantics are eligible: yield strength, ultimate
tensile strength, and tensile elongation/ductility.  The parser may accept:

1. a single-owner clause containing one or more explicit property/value/unit
   pairs;
2. a complete table cell with a unique logical row/column/header path;
3. an ordered multi-owner assertion whose owner and value cardinalities match
   and whose grammar explicitly establishes order, including a literal
   `respectively`; or
4. a bounded continuation whose immediately preceding assertion uniquely
   supplies the same owner and tensile property sequence.

Every numeric token and unit must be literal in the accepted block.  Property
and value cardinality must agree.  Units may be shared only by a syntactically
bounded property/value list.  Approximation and uncertainty markers are
preserved.  The parser must reject plot-derived values, continuous sidecars,
caption-only inference, citation-only Reference results without a local
reference owner, unmatched owner/value lists, incomplete continuation chains,
multiple compatible antecedents, and any coordinate requiring scientific
interpolation or guessed aliases.

The parser is general source grammar.  It must not contain paper-specific
titles, IDs, expected values, or material names.

### Component 2: one-coordinate-to-one-owner projection ledger

Before routing Property facts, group core-tensile assertions by their literal
source coordinate rather than by loose evidence text alone.  Each coordinate
may own one scientific tuple:

`(owner, role, state, orientation, property, value, unit, test condition)`.

A candidate may be repaired or recovered only when exactly one compatible
coordinate proves the tuple.  One coordinate cannot be copied to multiple
owners unless the source itself contains independent owner/value coordinates
for each owner.  Ordered multi-owner assertions therefore produce independent
coordinates, not a shared fanout coordinate.

For an existing candidate:

- preserve an already complete compatible tuple;
- fill a missing owner/state/orientation only from one exact coordinate;
- merge an evidence-identical generic projection into its uniquely resolved
  coordinate owner;
- quarantine a candidate whose own source coordinate proves a different owner,
  property, value, unit, state, orientation, or role; and
- fail closed when zero or multiple coordinates are compatible.

Ambiguity is never resolved by choosing the first owner, shortest alias,
highest confidence, GT match, or majority vote.  Composition facts do not
enter this v204 ledger.  Non-core Properties are unchanged except when an exact
same-coordinate duplicate is proven by existing generic contracts.

### Component 3: result-to-protocol condition binding

Link each accepted tensile result coordinate to the existing v203
`TensileProtocolLedger`.  Compatibility is evaluated over role, owner, state,
orientation, tensile family, result temperature, and bounded source scope.

A protocol event may add only a missing dimension.  It never overwrites a
literal existing dimension.  Material preparation temperature remains state;
test temperature remains condition.  Crosshead speed, stress rate, strain
rate, and data-acquisition rate remain distinct.  Reference events never bind
Target results, and Target events never bind Reference results.

When a paper contains multiple protocol events, a literal result temperature,
state, orientation, local section, or explicit global statement must reduce
the compatible set to exactly one event.  Otherwise binding is a reason-coded
no-op.  A complete source assertion bundle is bound once so all bundle members
receive the same compatible protocol dimensions without independent nearest-
text guesses.

### Component 4: recovery, quarantine, and audit contract

Recovered coordinates become ordinary candidate facts before existing v202
and v203 gates.  They do not bypass owner, role, evidence, value/unit,
condition, deduplication, sanitization, or materialization checks.

Every v204 decision is recorded in the existing per-paper
`quality_audit.json` with the complete before/after record, source coordinate,
candidate coordinates, selected protocol event, contributed dimensions,
rationale, and stable decision key.  The existing `issues.json` and
`issues.md` receive only a short code, locator, and review flag.  The public
`final.json` schema and field names remain byte-compatible in shape.

Required reason codes are:

- `tensile_assertion_coordinate_recovered`;
- `tensile_assertion_coordinate_rejected`;
- `tensile_assertion_continuation_recovered`;
- `tensile_assertion_ordered_mapping_recovered`;
- `tensile_assertion_coordinate_ambiguous`;
- `tensile_coordinate_owner_reassigned`;
- `tensile_coordinate_projection_quarantined`;
- `tensile_coordinate_duplicate_merged`;
- `tensile_result_protocol_bound`; and
- `tensile_result_protocol_ambiguous`.

Add independently shadowable, default-on switches:

- `KNOWMAT2_ALPHA25_TENSILE_ASSERTION_COORDINATES_V204`;
- `KNOWMAT2_ALPHA25_TENSILE_COORDINATE_FANOUT_GUARD_V204`; and
- `KNOWMAT2_ALPHA25_TENSILE_RESULT_PROTOCOL_BINDING_V204`.

With all three switches off, the same frozen inputs must reproduce accepted
v203 scientific payloads and audit output.  The raw `final.json` may differ
only in existing run metadata such as `Rule_Metadata.git_commit`.

## Data flow

The v204 materialization flow is:

1. read one paper's frozen candidates and explicit source directory;
2. run existing v202/v203 source-coordinate and dense-table parsing;
3. build bounded tensile assertion coordinates from the same source;
4. combine source-recovered and frozen candidates;
5. run all existing evidence and quality gates;
6. resolve each core-tensile coordinate to zero or one owner tuple;
7. quarantine only coordinate-proven projection conflicts and exact
   duplicates;
8. bind missing protocol dimensions from exactly one compatible event;
9. materialize the unchanged public schema; and
10. write complete deterministic audit records.

GT evaluators remain outside the production call graph.  Offline
rematerialization must receive each paper's source directory explicitly and
must not search arbitrary workspace paths.

## Error handling and safety

Missing source text, malformed markup, invalid numeric syntax, incomplete
lists, ambiguous antecedents, conflicting units, unresolved owner aliases,
multiple protocol events, or invalid audit serialization must not silently
create a fact.  Candidate-level ambiguity is an audited no-op.  A failure to
write the required audit makes the paper fail rather than succeed without an
audit trail.

No source or sidecar path may escape the explicit paper directory.  Continuous
line-chart points remain externalized and are never expanded into Properties.
No provider call, prompt change, OCR/VLM rerun, chart rerun, frozen-response
mutation, or schema migration is permitted in v204.

## Verification strategy

### Unit and invariant tests

Tests must cover:

- single-owner multi-property prose bundles;
- ordered multi-owner/value bundles and literal `respectively` mappings;
- safe adjacent continuation and ambiguous/non-adjacent continuation rejection;
- exact uncertainty, approximation, range, sign, decimal, and shared-unit
  preservation;
- property/value cardinality mismatch and missing-unit rejection;
- Target/Reference, state/test-temperature, and orientation isolation;
- one-coordinate-to-one-owner fanout prevention;
- exact duplicate merge and each quarantine reason code;
- multiple protocol events resolved by literal result dimensions;
- conflicting or incomplete protocol events as no-ops;
- table, chart, citation-only, qualitative, and prose-negative controls;
- Composition payload invariance;
- stable decisions under candidate and source-record permutations;
- switches-off v203 compatibility; and
- no production dependency on GT, paper identity, provider, or model name.

Every pytest command uses `-o addopts=''`.

### Source-audited pilot

Run a bounded pilot that includes:

- a single-owner explicit tensile bundle;
- an ordered two-owner tensile comparison;
- a safe continuation assertion;
- a multi-temperature protocol case;
- a citation-heavy Reference table; and
- a continuous-chart negative control.

Review every changed Property against its exact source block.  Any wrong
owner, role, state, orientation, property, value, unit, or protocol dimension
fails the responsible switch.  Source-supported claims absent from both GTs
must be retained.

### Thirty-paper acceptance replay

Use the same 405 frozen upstream responses and frozen evaluator inputs.

| Gate | Requirement |
|---|---:|
| Papers / fatal / silent-empty | `30 / 0 / 0` |
| Provider/API calls | `0` |
| GPT expert global loose precision | `>= 0.462312` |
| GPT expert global loose F1 | `> 0.314194` |
| GPT expert global strict precision | `>= 0.287060` |
| GPT expert global strict F1 | `> 0.195091` |
| GPT expert Target core-tensile loose precision | `>= 0.907801` |
| GPT expert Target core-tensile loose recall | `> 0.600939` |
| GPT expert Target core-tensile loose F1 | `> 0.723164` |
| GPT expert Target core-tensile strict precision | `>= 0.702128` |
| GPT expert Target core-tensile strict recall | `> 0.464789` |
| GPT expert Target core-tensile strict F1 | `> 0.559322` |
| Wrong-owner conflicts | `<= 225` |
| Condition conflicts | `< 52` |
| System-missing claims | `< 2497` |
| Direct business-GT Target core-tensile loose F1 | `> 0.739394` |
| Direct business-GT Target core-tensile strict F1 | `> 0.496970` |
| Composition scientific payload | byte-identical for `30/30` papers |
| Prompt/schema/frozen responses | hash-identical to v203 |
| Deterministic replay | scientific `final.json`, `quality_audit.json`, and summaries identical |
| Mean rematerialization runtime regression | `<= 20%` versus v203 |

Global and core matched counts may not fall below v203.  No already matched
claim may be removed unless its own source coordinate proves an explicit
scientific error and the acceptance report lists the source-audited exception.
Evaluator thresholds, GT inputs, matcher rules, and the 30-paper manifest are
frozen before replay.

If a gate fails, narrow or disable the responsible v204 switch.  Do not weaken
the gate, change the evaluator, or add paper-specific behavior.

## Deliverables

- focused implementation and invariant tests;
- one accepted v204 30-paper output and one deterministic replay output;
- unchanged-shape `final.json`, complete `quality_audit.json`, and concise
  `issues.json`/`issues.md` per paper;
- a source-audited delta ledger for every recovered, reassigned, merged,
  quarantined, or condition-enriched Property;
- GPT expert, business GT, and three-way comparison artifacts; and
- an acceptance report with hashes, API count, runtime, tests, metrics, and
  switch status.

## Non-goals

- changing the reviewed extraction prompt;
- changing the model or provider;
- adding a verifier-model pass;
- rerunning OCR, VLM, line charts, or upstream extraction;
- changing Alpha25 or `final.json` schemas;
- deriving values from continuous plots;
- modifying Composition behavior;
- broad filtering of GT-unmatched records; or
- paper-specific production rules.
