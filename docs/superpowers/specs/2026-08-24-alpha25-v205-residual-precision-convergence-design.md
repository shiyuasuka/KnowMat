# Alpha25 v205 residual precision convergence

## Status and objective

The user approved the v205 precision-first specification on 2026-08-24.
This iteration improves the accepted Alpha25 v204 baseline by addressing the
largest remaining source-audited precision residuals.  It does not change the
professionally reviewed extraction prompt and does not make another model or
provider call.

The objective is to improve global loose precision/F1, owner and condition
attribution, and core-tensile quality without reducing source-supported recall.
The primary targets are unsupported Structure/Characterization projection and
presentation locators copied into scientific conditions.  A secondary target
is a process or method label used as a Property owner when one literal material
or specimen owner is uniquely provable.

Production code must not read GT, evaluator output, expected values or counts,
paper IDs, paper titles, provider names, or model names.  GPT expert GT and
business GT remain offline evaluation inputs only.  A claim unmatched by either
GT is not, by itself, a hallucination and must not be removed for that reason.

## Frozen v204 baseline and residual diagnosis

The authoritative v204 baseline is:

- output:
  `data/output-alpha25-v204-source-assertion-protocolfix-final30-20260824`;
- deterministic replay:
  `data/output-alpha25-v204-source-assertion-protocolfix-replay30-20260824`;
- acceptance report:
  `data/experiments/alpha25-v204-source-assertion-20260824/protocolfix_v204_acceptance.md`;
- three-way evaluation:
  `data/experiments/alpha25-v204-source-assertion-20260824/protocolfix_v204_vs_gpt_expert_and_business.json`; and
- direct business comparison:
  `data/experiments/alpha25-v204-source-assertion-20260824/protocolfix_v204_direct_business_gt.json`.

Against GPT expert GT, v204 core-tensile loose precision/recall/F1 is
`0.899/0.671/0.769`, strict precision/recall/F1 is `0.774/0.577/0.661`, and
condition conflicts are 42.  Against business GT directly, unique global loose
precision/recall/F1 is `0.488199/0.279417/0.355415`; core-tensile loose
precision/recall/F1 is `0.874214/0.735450/0.798851` and strict F1 is
`0.557471`.

The direct business residual ledger shows that v204 changed only Properties
relative to v203.  The largest remaining global precision deficits are
Structure and Characterization, followed by residual Property projections and
owner/condition conflicts.  Source-audited recurring classes include:

- one structural measurement projected into repeated entities or owners;
- `d-spacing`, lattice-parameter, grain-size, and density values lacking a
  complete local entity/value/unit coordinate;
- characterization methods duplicated across aliases or projected from a
  method mention without one material-local event;
- `Table 3`, figure numbers, page/section labels, and repeated method prose
  copied into `test_condition_raw`;
- process names such as Binder Jetting, EPBF, or LPBF used as a tensile owner;
- a discrete plot assertion whose orientation/state/value coordinates are
  collapsed or crossed; and
- true source-supported facts absent from one or both GTs, which must remain.

Composition is frozen because it is the strongest GLM axis and v204 already
preserved it 30/30.  v205 must keep Composition scientific payloads identical
to v204 for every paper.

## Considered approaches

### 1. Atomic assertions plus provenance/condition separation

This is the selected primary approach.  Apply source-local atomicity to
Structure and Characterization, then remove presentation-only locators and
duplicated method prose from Property conditions without discarding evidence.
It directly addresses the largest precision residuals, remains deterministic,
adds no API latency, and can be shadowed component by component.

### 2. Condition-only cleanup

Cleaning only Property conditions is lower risk and should reduce some strict
and condition conflicts, but it leaves the dominant Structure and
Characterization over-projection unchanged.  It is insufficient as the full
v205 iteration, though its condition-separation component remains independently
switchable.

### 3. Secondary LLM verification or prompt revision

A verifier or prompt change could judge broader semantic ambiguity, but it
adds latency and nondeterminism and would confound post-processing quality with
the professionally reviewed prompt baseline.  It is outside v205.  The current
model/provider, prompt, OCR, VLM, and chart inputs remain unchanged.

## Architecture

### Component 1: Structure assertion atomicity

Add a paper-local assertion ledger for quantitative and categorical Structure
claims.  One accepted structural coordinate consists of:

`(source atom, owner, material state, entity, feature, value, unit, qualifier)`.

For a quantitative feature, the accepted source atom must contain an explicit
feature/value relation and the literal value/unit, plus one compatible owner or
entity coordinate.  A logical table cell may use its exact row/column/header
path.  Shared units are allowed only within a syntactically bounded list or one
logical table row.  Qualitative presence claims remain eligible when the
structural entity and observation are explicit; v205 does not require a number
for inherently qualitative structure.

The ledger must fail closed for:

- a value detached from its row, entity, feature, or unit;
- one evidence atom copied to several owners or entities without independent
  source coordinates;
- a table/figure/page locator used as a feature or value;
- a measurement method, axis label, crystallographic designation, nominal
  formula token, or processing parameter projected as an observed value; and
- crossed owner/value or orientation/value lists with no explicit ordering.

When one coordinate proves one compatible existing candidate, preserve it.
When it proves an exact source-identical generic duplicate, merge the duplicate.
When it proves that a candidate projected the same assertion to an incompatible
owner/entity/value, quarantine that projection.  When zero or multiple
coordinates are compatible, make an audited no-op; never choose the closest or
first owner.

This component must not delete a source-supported `d-spacing`, lattice
parameter, grain size, phase, morphology, texture, or defect observation merely
because a GT omits it.

### Component 2: Characterization event atomicity

Represent one characterization event as:

`(source atom, owner, material state, canonical method family, purpose/target,
instrument details when literal)`.

A bare method mention may create at most one event for one uniquely compatible
owner/state in its local source scope.  Method aliases within the same source
atom and owner/state are merged into one event while retaining every literal
alias and the complete before/after audit.  Instrument settings, scan ranges,
software names, detector names, figure labels, and measured structural values
remain details or separate scientific claims; they do not fan out into new
characterization events.

Cross-owner routing is allowed only when the source independently states an
event for each owner.  Citation-only background methods, caption-only labels,
presentation locators, and unresolved multi-owner method mentions remain
audited no-ops or quarantined projections.  Ambiguous method-family aliases are
not guessed.

### Component 3: provenance and scientific-condition separation

Introduce a source-literal condition normalizer for Properties, applied before
condition-aware deduplication and protocol comparison.  It separates three
kinds of text:

1. scientific coordinates: temperature, rate, orientation, state, delay,
   environment, loading mode, and other actual test dimensions;
2. protocol details: standard, machine, specimen geometry, extensometer, and
   acquisition details; and
3. provenance locators: table/figure/supplement/page/section identifiers and
   phrases such as `shown in Table 3`.

Only source-literal scientific coordinates remain in
`test_condition_raw`.  Existing schema fields retain literal protocol details
where supported; otherwise those details remain in evidence and audit rather
than being synthesized into a new public field.  Provenance locators remain in
evidence/data-source metadata and audit, never in the scientific condition.

The normalizer removes repeated equivalent condition segments, including
duplicate `room temperature` fragments, while preserving distinct dimensions.
It must not equate preparation temperature with test temperature, delay with
hold time, strain rate with crosshead speed, or orientation with material
owner.  If removing presentation/method text leaves no scientific coordinate,
the condition is empty rather than inferred from neighboring text.

Discrete chart points remain eligible only through the existing bounded chart
contract.  v205 may preserve distinct orientation/state/value coordinates but
must not interpolate continuous curves or expand chart context.

### Component 4: unique material-owner convergence

For core-tensile Properties only, detect process/method-only owners such as an
additive-manufacturing technique when that text names how a specimen was made,
not the specimen/material itself.  Reassign such a candidate only when the same
source assertion or exact logical table coordinate proves exactly one existing
material/specimen owner and the value, unit, role, state, orientation, and
condition are compatible.

If the process label is itself the only explicit sample designation, preserve
it.  If two material/specimen owners are possible, do nothing and emit an
ambiguity decision.  Delay, orientation, and build-state labels remain
condition/state dimensions unless the source explicitly defines them as sample
identities.  No owner is selected by frequency, string similarity, GT match,
or a paper-specific alias table.

This component is intentionally secondary and independently switchable.  It
must not modify Composition owners or non-core Property owners.

### Component 5: quarantine and audit contract

Every removal, merge, field cleanup, reassignment, and ambiguity decision is
written to the existing per-paper `quality_audit.json` with the complete
before/after record, source coordinate, compatible coordinates, rationale, and
stable decision key.  Existing `issues.json` and `issues.md` receive a compact
reason code, locator, and review flag.  The public `final.json` schema and field
names do not change.

Required reason codes are:

- `structure_assertion_projection_quarantined`;
- `structure_assertion_duplicate_merged`;
- `structure_assertion_coordinate_ambiguous`;
- `characterization_event_projection_quarantined`;
- `characterization_event_alias_merged`;
- `characterization_event_coordinate_ambiguous`;
- `property_provenance_locator_removed_from_condition`;
- `property_condition_duplicate_segment_removed`;
- `property_condition_protocol_context_separated`;
- `tensile_process_owner_reassigned`; and
- `tensile_process_owner_ambiguous`.

Add default-on, independently shadowable switches:

- `KNOWMAT2_ALPHA25_STRUCTURE_ASSERTION_ATOMICITY_V205`;
- `KNOWMAT2_ALPHA25_CHARACTERIZATION_EVENT_ATOMICITY_V205`;
- `KNOWMAT2_ALPHA25_PROPERTY_PROVENANCE_CONDITION_SEPARATION_V205`; and
- `KNOWMAT2_ALPHA25_UNIQUE_MATERIAL_OWNER_CONVERGENCE_V205`.

With all v205 switches off, frozen v204 inputs must reproduce v204 scientific
payloads and audit output.  Raw `final.json` may differ only in existing run
metadata such as `Rule_Metadata.git_commit`.

## Data flow

The v205 materialization flow is:

1. read one paper's frozen v204 candidates and explicit source directory;
2. run existing v202-v204 source-coordinate, promotion, and quality gates;
3. build Structure assertion and Characterization event coordinates from the
   same bounded source atoms;
4. quarantine only coordinate-proven unsupported projections and merge only
   exact dominated duplicates;
5. separate provenance/protocol text from Property scientific conditions and
   deduplicate equivalent condition segments;
6. converge a process/method-only core-tensile owner only when one material or
   specimen coordinate is uniquely proven;
7. run existing owner, role, evidence, value/unit, protocol, deduplication,
   sanitization, and materialization checks;
8. materialize the unchanged public schema; and
9. write complete deterministic audit and compact review issues.

GT evaluators remain outside the production call graph.  Offline replay must
receive each paper source directory explicitly and must not search arbitrary
workspace paths.

## Error handling and safety

Missing source, malformed markup, invalid numeric syntax, incomplete logical
tables, conflicting units, unresolved aliases, multiple compatible owners,
crossed lists, or invalid audit serialization must not silently create, delete,
or reassign a fact.  Candidate ambiguity is an audited no-op.  Failure to write
the required audit makes the paper fail instead of succeeding without a trace.

No source or sidecar path may escape the explicit paper directory.  Continuous
line-chart points remain externalized.  v205 permits no provider call, prompt
change, OCR/VLM/chart rerun, frozen-response mutation, schema migration, or
Composition mutation.

## Verification and acceptance

### Unit and invariant tests

Tests must cover:

- one structural feature/value/unit bound to one owner/entity coordinate;
- complete logical-table coordinates and bounded shared-unit lists;
- structure fanout, crossed owner/value, locator-as-value, method-as-feature,
  and nominal-token negative controls;
- source-supported qualitative structure and GT-unmatched true facts;
- characterization alias merging, one-event-per-source-atom behavior, literal
  multi-owner events, and ambiguous/citation-only negatives;
- exact removal of table/figure/page/section locators from conditions;
- duplicate scientific-condition segment collapse without losing distinct
  temperature/rate/state/orientation/delay dimensions;
- separation of protocol details from conditions with complete audit retention;
- process-label owner preservation when it is the only explicit designation;
- process-label reassignment only with one exact material/specimen coordinate;
- multi-owner and incompatible-coordinate no-op behavior;
- distinct discrete-chart orientation/state/value coordinates and continuous
  chart negative controls;
- candidate/source-order determinism and stable decision keys;
- Composition payload invariance;
- all-switches-off v204 compatibility; and
- no production dependency on GT, paper identity, provider, or model name.

Every pytest command uses `-o addopts=''`.

### Source-audited pilot

Before a 30-paper replay, run a bounded pilot containing:

- repeated `d-spacing`/lattice-parameter/grain-size residuals;
- characterization alias and multi-owner method cases;
- a core-tensile row owned by a process label;
- a discrete plot with multiple orientations or states;
- a citation-heavy reference table whose locator currently pollutes condition;
- explicit delay/state rows; and
- known source-supported claims absent from one or both GTs.

Every changed scientific record must be reviewed against its exact source atom.
Any unsupported removal, wrong owner/entity/value/unit/condition, or chart
expansion fails the responsible switch.

### Thirty-paper acceptance gates

Run the same frozen 30-paper corpus twice and compare v205 with v204, GPT expert
GT, and business GT.  Acceptance requires:

- 30/30 success, zero fatal or silent-empty papers, and zero provider calls;
- byte-identical scientific `final.json`, `quality_audit.json`, and summary
  outputs across the two v205 replays, excluding documented run metadata;
- Composition scientific payloads identical to v204 for 30/30 papers;
- all v205 switches off reproducing v204 scientific payloads and audit output;
- no source-audited false quarantine or owner/value/condition mutation;
- direct-business unique global loose precision and F1 not below v204;
- GPT-expert global loose precision and F1 not below v204;
- core-tensile loose precision not below v204 against either GT, except a
  documented matcher artifact supported by source and both expert reviews;
- core-tensile loose/strict F1, wrong-owner count, and condition-conflict count
  not worse than v204 unless every regression is individually source-adjudicated
  and accepted as a GT omission or evaluator-expression artifact;
- Structure and Characterization precision not below v204 on either comparison;
  and
- mean replay wall time no more than 20% above v204.

Metric improvement alone cannot override a source error.  If a component raises
F1 by deleting a source-supported fact, crosses an owner/value coordinate, or
changes Composition, that component fails and must remain disabled.
