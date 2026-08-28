# Alpha25 source-proven owner-state protocol completion

## Goal

Improve GLM Alpha25 tensile accuracy relative to both the business GT and the
independent GPT expert GT by correcting facts whose numeric value is already
source-grounded but whose owner, material state, orientation, or tensile test
protocol is incomplete or misclassified. This iteration is precision-first:
it must not create, delete, or duplicate accepted facts merely to increase an
evaluation score.

The professional extraction prompt, extraction schema, OCR/VLM inputs,
Composition output, and public `final.json` shape remain unchanged. The
implementation is deterministic and is evaluated by replaying the frozen task
cache without provider API calls.

## Scope

This iteration covers existing core tensile facts that already have a direct
source assertion and a valid value/unit pair. It may:

- select one existing physical owner or specimen coordinate;
- reconcile a base owner with one explicitly reported material state;
- separate preparation history from the tensile test protocol;
- add source-literal temperature, loading rate, standard, orientation,
  extensometer/gauge, or equipment details to `Test_Condition`; and
- preserve a complete before/after decision in the existing audit stream.

It does not recover new property values, remove source-supported values,
classify reference facts globally, or increase Processing, Structure, and
Characterization recall. Those are separate precision/recall iterations after
this coordinate repair is stable.

## Alternatives considered

### 1. Source-proven deterministic completion — selected

Complete coordinates only when the source and the existing owner/protocol
inventories produce one compatible answer. This directly addresses the large
set of loose matches that fail strict matching and has the smallest risk of
lowering loose precision.

### 2. Current-study/reference boundary filtering

Quarantine tensile values that belong to cited literature rather than the
current study. This can improve loose precision, but the current expert GT is
not exhaustive for all valid reference facts. It requires a separate,
source-by-source adjudication design to avoid deleting true facts.

### 3. Global structured recall recovery

Recover missing Processing, Structure, and Characterization facts from tables
and captions. This targets overall loose F1, but it expands the owner fan-out
surface and should follow, rather than be mixed with, owner/protocol repair.

## Architecture

The change extends the existing Alpha25 materialization pipeline rather than
adding a second postprocessor.

1. `source_coordinates.py` and the existing owner inventory identify literal
   owner, state, and orientation coordinates from the fact's own source block.
2. `materialize.py` reconciles that coordinate against existing owner graph
   nodes. It never synthesizes a paper name, material label, or state.
3. `property_context.py` selects one compatible tensile protocol event from
   the existing protocol ledger and projects only source-literal test details.
4. `promotion.py` keeps the repaired coordinate through physical-owner and
   semantic deduplication.
5. Existing issue writers persist the complete decision without changing the
   public fact schema.

The code must use generic evidence predicates. Paper identifiers, expected GT
values, publication titles, and provider/model names are forbidden in runtime
rules.

## Decision model

### Owner and state reconciliation

A fact is eligible only when all of the following hold:

1. It is an accepted core tensile fact with a direct, source-literal value and
   unit.
2. Its source block exposes exactly one owner/state/orientation coordinate, or
   the table row plus header/caption jointly expose exactly one coordinate.
3. That coordinate resolves to exactly one existing owner graph node or one
   existing base-owner/state relationship.
4. The candidate does not contradict an explicit owner/state already attached
   to the fact.
5. The source block is a current-result assertion, not an unresolved
   comparator, literature projection, simulation-only value, or protocol-only
   methods statement.

Heat treatment, ageing, annealing, sintering, as-built/as-fabricated status,
and equivalent preparation history belong to the owner/material-state
coordinate. Horizontal/vertical/build-direction labels identify the specimen
coordinate when the source uses them to distinguish tested specimens. They
must not be copied into Structure facts or treated as test temperature.

If any candidate remains ambiguous, the accepted fact is left unchanged and a
review issue records the competing candidates. Ambiguity never falls back to
the nearest chunk, first owner, or most frequent owner.

### Tensile protocol binding

After owner/state reconciliation, a fact may inherit protocol details only
when exactly one ledger event is compatible with its immutable source
coordinate. Compatibility is determined by source-literal owner aliases,
state/orientation scope, tensile-test language, temperature, and protocol
discriminators already present on the fact.

Only test-time dimensions are added to `Test_Condition`:

- test temperature;
- strain, crosshead, or loading rate;
- tensile standard;
- test/build orientation where it describes the tested specimen;
- gauge length or extensometer details; and
- test machine/equipment.

Manufacturing, heat treatment, ageing, sintering, machining, and specimen
preparation steps are excluded from `Test_Condition`. Existing correct
condition fragments are retained and source-literal missing dimensions are
appended once in stable order. Conflicting temperatures, rates, standards, or
orientations make the binding ineligible.

An owner explicitly named by a protocol is authoritative only for that owner.
A paper-level protocol can be shared only when the source explicitly states
that it applies to all relevant tensile specimens or when the existing
physical-owner coordinate and ledger jointly identify one unique event.

## Data flow and invariants

For every eligible fact:

1. Preserve the original fact as the audit `before` value.
2. Resolve the source-local owner/state coordinate.
3. Resolve one compatible protocol event.
4. Build a candidate fact without mutating the input object.
5. Re-run condition conflict and physical-owner dedup guards.
6. Publish the candidate only if fact count, value, unit, property subtype,
   evidence, and data nature remain stable.
7. Emit one grouped audit decision containing the before/after facts, source
   block, evidence spans, selected owner/protocol decision keys, and rule name.

The following invariants are mandatory:

- no accepted fact is added or removed by this feature;
- Composition facts are byte-equivalent after canonical serialization;
- property value, unit, subtype, evidence, and source identifiers do not
  change;
- `final.json` has the same schema as the r81 baseline;
- every changed owner/state/condition is reconstructable from the audit;
- ambiguous or conflicting evidence fails closed; and
- frozen replay performs zero provider API calls.

## Audit and failure handling

Successful reconciliation emits a concise issue code for owner/state repair
and, when applicable, a second code for protocol completion. The audit payload
contains the stable decision key, source span, compatibility dimensions, and
full before/after facts.

Skipped candidates use machine-readable reason codes, including ambiguous
owner, ambiguous state, multiple compatible protocols, protocol conflict,
reference/comparator uncertainty, and preparation-only context. These records
remain in the existing `quality_audit.json` and `issues.json/.md` flow; no new
public sidecar format is introduced.

Unexpected parsing failures leave the original fact unchanged, emit a review
issue, and do not abort the paper. Fatal materialization behavior is unchanged.

## Verification strategy

### Focused tests

Add generic tests covering:

- one table owner/state mapping to one existing graph node;
- a base owner plus explicit heat-treated/as-fabricated state;
- horizontal/vertical specimen owner reconciliation;
- preparation history excluded from `Test_Condition`;
- unique room-temperature/rate/standard/orientation protocol completion;
- preservation of an already-correct partial condition;
- conflicting or multiple protocols failing closed;
- unresolved comparator/reference context failing closed;
- deduplication preserving the repaired coordinate; and
- complete audit payloads with no public schema change.

### Frozen pilot

Replay the six high-yield residual papers represented by evaluation indices
002, 013, 019, 025, 026, and 028. These identifiers select evaluation inputs
only and must not appear in runtime logic. Inspect every changed fact against
its OCR/table source, not merely the matcher result.

The pilot passes when value/unit fact counts are unchanged, all modifications
are source-supported, target condition/owner conflicts decrease, and neither
GPT-expert nor business-GT loose precision decreases.

### Full 30-paper regression

Replay `data/output-alpha25-prompt-v5-final30-20260818` with provider calls
disabled, then compare against r81, GPT expert GT, and business GT.

Required gates:

- 30/30 papers complete and fatal errors equal zero;
- provider API calls equal zero;
- all Alpha25 tests pass;
- Composition output is unchanged for all 30 papers;
- canonical `final.json` schema is unchanged for all 30 papers;
- accepted fact counts, values, units, subtypes, and evidence are unchanged by
  this iteration;
- core-tensile loose precision does not decrease against either GT;
- overall loose precision does not decrease against either GT;
- core strict precision, recall, and F1 improve over r81, whose strict F1 is
  `0.628713` against GPT expert GT;
- core `condition_conflict` decreases from the r81 adjudicated count of 36;
  and
- core `wrong_owner` decreases from the r81 adjudicated count of 9.

If any precision or invariance gate fails, the full output is rejected and r81
remains the release baseline. Improvements on one paper cannot compensate for
unsupported changes on another.

## Follow-up sequence

After this iteration passes, the next precision-first design will adjudicate
current-study versus literature/reference projections. Only after that gate is
stable should structured global recall recovery target Processing, Structure,
Characterization, and non-core Properties to close the remaining business-GT
overall loose-F1 gap.
