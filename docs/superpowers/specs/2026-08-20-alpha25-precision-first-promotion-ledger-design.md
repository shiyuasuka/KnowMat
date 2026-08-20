# Alpha25 precision-first promotion ledger and bounded risk verifier

## Status and objective

This design continues the approved GLM-5.2 Alpha25 convergence direction after
the accepted v47 materialization baseline. Composition is already stronger than
the business GT, while overall loose F1 and core-tensile loose F1 remain lower.
The objective is therefore to improve production precision, material/state owner
and condition attribution, and tensile quality without modifying the
professionally reviewed extraction prompt or the public `final.json` format.

The extraction model remains a high-recall candidate generator. A new
paper-level promotion layer decides which candidates are sufficiently grounded
and uniquely attributed to enter trusted production fields. Rejected or
uncertain candidates remain fully auditable in the existing `issues.json/.md`.

## Authoritative v47 baseline

All numbers below use the adjudicated GPT-5.6-sol expert ledger and unique
scientific claims unless stated otherwise.

| Metric | Business GT | GLM v47 | GPT expert ledger |
|---|---:|---:|---:|
| Global claim count | 3,331 | 6,270 | 3,093 |
| Global loose precision / recall / F1 | 42.7799% / 46.0718% / 44.3649% | 25.1675% / 51.0184% / 33.7071% | reference |
| Global strict precision / recall / F1 | 15.0405% / 16.1979% / 15.5978% | 12.6316% / 25.6062% / 16.9177% | reference |
| Core-tensile claims | 189 | 209 | 213 |
| Core-tensile loose precision / recall / F1 | 89.9471% / 79.8122% / 84.5771% | 79.4258% / 77.9343% / 78.6730% | reference |
| Core-tensile strict precision / recall / F1 | 56.6138% / 50.2347% / 53.2338% | 60.2871% / 59.1549% / 59.7156% | reference |
| Composition loose F1 | 59.2096% | 65.9939% | reference |
| Composition strict F1 | 15.5392% | 32.6942% | reference |

The quantity difference is concentrated rather than uniform:

- GLM materializes 371 items across 30 papers; business GT materializes 171.
- Nine GLM items contain identity only, and 75 contain only one promoted fact.
- Structure contains 1,324 observations. The evaluator produces 2,796 unique
  Structure claims versus 715 in business GT and 773 in the expert ledger.
- About 70.8% of GLM's 2,939-claim excess over business GT is Structure.
- Exact normalized evidence repeats occur 227 times in Structure and 320 times
  in Properties when owner is ignored. These include 112 and 105 cross-owner
  evidence groups respectively, so they cannot be deleted without validating
  table columns and explicit shared-owner grammar.
- Evidence adjudication records 2,936 unsupported-claim tags, 552 wrong-owner
  tags, 493 value-conflict tags, and 1,796 duplicate tags for GLM. These tags
  overlap and diagnose error modes; they are not a confusion matrix.

The evidence shows that the principal defect is not missing extraction. It is
promotion of too many fragmented, repeated, weakly attributed, or wrongly
classified candidate facts.

## Constraints

- Do not modify the reviewed Alpha25 extraction system/user prompt, extraction
  schema, OCR/VLM stages, or provider capability negotiation.
- Preserve the exact existing `final.json` hierarchy and field names.
- Do not place verifier decisions or new audit fields in `final.json`.
- Preserve every removed, merged, reassigned, conflicted, or quarantined
  candidate in `issues.json/.md` with its original payload and evidence.
- Do not create a separate `quality_audit.json`.
- Composition is a protected axis. Generic precision rules must not erase
  source-backed composition or regress its current loose/strict metrics.
- The expert and business GTs are offline evaluation inputs only. Production
  code and verifier prompts must not contain paper titles, GT values, GT item
  IDs, expected output counts, or provider/model-name branches.
- Do not delete merely to approach the business or expert claim count.
- Do not use confidence, majority voting, or three extraction runs as a truth
  decision.
- The verifier may not create a fact, value, unit, owner, condition, evidence
  span, or material item.
- Preserve table columns that explicitly describe distinct owners, values,
  conditions, directions, states, or regions.
- Preserve reproducibility through content-addressed verifier caches and frozen
  replay.

## Considered approaches

### 1. Deterministic post-materialization deduplication only

This is fast and reproducible. It safely handles exact aliases and a small
number of evidence-dominance relations, as v47 demonstrated. It cannot resolve
the dominant ambiguous owner, paraphrase, axis, and condition cases. The v47
gain is consequently too small for the current objective.

### 2. Full-paper or full-output second-pass rewrite

A second LLM could rewrite every paper into a smaller result, but this repeats
large contexts, increases latency, and permits the reviewer to invent or silently
drop facts. It also makes deterministic audit and cache invalidation difficult.
This approach is rejected.

### 3. Paper-level promotion ledger with deterministic gates and bounded
risk-only verification

This is the selected approach. Candidate extraction remains unchanged. A
paper-level internal ledger groups source assertions, resolves identity where
the source proves it, applies axis-specific promotion gates, and submits only
unresolved high-risk groups to a constrained verifier. Trusted candidates then
flow through the existing materializer.

## Architecture

### 1. Integration point

The promotion stage runs in `src/knowmat/nodes/extraction.py` after inventory and
axis tasks have completed and coverage has been asserted, but before
`materialize_candidate(...)` is called. It receives the complete paper's
accepted anchors, accepted facts, OCR Markdown, task provenance, and evidence
unit metadata.

The deterministic implementation is isolated under
`src/knowmat/alpha25/promotion.py`. The optional verifier contract, prompt
compiler, batching, and response validation live under
`src/knowmat/alpha25/risk_verifier.py`. The existing materializer remains the
only producer of v11 output.

### 2. Internal promotion record

Every accepted `AxisFact` becomes one immutable internal record containing:

- a content-derived claim ID and original source order;
- axis, fact type, complete original payload, and confidence as metadata only;
- evidence-unit ID, task ID, source block, table header/row/cell anchors, and
  copied evidence spans;
- normalized assertion signature and axis-specific semantic signature;
- explicit owner labels, candidate owners, role, data nature, state, region,
  orientation, and source origin;
- value semantics, numeric tokens, units, conditions, and data source;
- deterministic risk codes; and
- one promotion decision with its rule and evidence.

The ledger is internal. A debug serialization may be enabled for development,
but it is not a production output contract.

### 3. Source-assertion groups

Facts are grouped only when their provenance proves that they derive from the
same assertion:

1. the same table cell;
2. the same table header plus row and owner column;
3. the same normalized sentence or list item;
4. an exact evidence span and its contained subspan in one evidence unit; or
5. compatible projections from the same source block whose structured fields
   are complementary rather than conflicting.

Text similarity alone never joins different source blocks. A table row shared
by several columns is one evidence block but contains a distinct assertion per
owner column. A sentence that explicitly says both A and B share a fact may
produce two owner-bound projections, both referencing the one shared assertion.

Within a proven assertion group, presentation duplicates merge. Complementary
entity/features merge into one richer record. Incompatible values, units,
conditions, origins, or owners form a risk group rather than being silently
combined.

### 4. Global identity and state graph

Build one graph from all source-explicit anchors before promotion. Nodes are
materials, independently named samples, states, orientations, regions, and
literature references. Edges are exact aliases, source-declared abbreviations,
base/state relations, process/state transitions, and explicit shared-owner
relations.

Owner precedence is:

1. table owner column or explicit sentence subject;
2. evidence-unit-local exact alias;
3. unique source-declared state/orientation/region relation;
4. unique base owner when the assertion is explicitly generic; and
5. unresolved.

A generic owner is not broadcast to children. A child is not collapsed into its
base when the source distinguishes state, orientation, region, or process route.
An alias-only item with no independently owned promoted fact is omitted. An
ambiguous candidate is quarantined unless the verifier can select one existing
owner from the evidence.

### 5. Axis-aware promotion gates

#### Composition

Composition remains protected. Existing literal value, basis, source-type, and
nominal/measured safeguards remain active. This increment changes an owner only
when the same table header/row/cell or explicit sentence subject proves a unique
owner. Ambiguity is audited, but no broad Composition count reduction is
allowed. Nominal alloy designations cannot become measured components.

#### Processing

Processing counts are close to business GT, so this is not a bulk-deletion
axis. Merge duplicate stages only when process family, owner/state, parameters,
conditions, source origin, and event identity are compatible. Keep independent
cycles and repeated stages when the source distinguishes sequence or condition.
Test controls and specimen preparation must not be promoted as material
Properties; they may remain Processing only when the source provides a valid
stage or parameter contract.

#### Structure

Structure is the first precision target.

Promote an observation when it owns at least one of:

- an explicit phase, defect, texture, grain population, precipitate, pore,
  interface, or other material entity;
- a quantitative or categorical feature bound to an explicit entity; or
- a source-explicit structural conclusion with a unique owner/state/region.

Quarantine or absorb:

- `unknown_entity_presence` without a named entity;
- location/area/region placeholders without an owned structural feature;
- captions, arrows, panel directions, and observation-method descriptions that
  do not assert a material structure;
- a generic presence record dominated by a richer entity/feature record from
  the same assertion;
- repeated long/short/simplified projections of the same source assertion; and
- copies routed to a generic or sibling owner without source grammar proving
  shared ownership.

Do not merge distinct phases, defects, regions, conditions, or states. Do not
drop a source-explicit categorical presence solely because it lacks a number.

#### Characterization

Normalize and merge method aliases once per owner, observation condition, and
source origin. Keep a method when it is source-explicit and tied to the paper's
material observation or measurement. Quarantine repeated method mentions,
caption-only labels, and methods copied to owners not named by the evidence.
Characterization is not reduced merely because its expert-ledger precision is
low; business GT contains more unique Characterization claims than GLM.

#### Properties

A numeric Property is promotable only when the assertion group proves:

- a material outcome property rather than equipment, process, specimen, or test
  control metadata;
- the reported value/range/inequality and unit or a lossless unit inherited from
  the same table header;
- one owner or source-explicit shared owners; and
- source support for every condition dimension used in the output. When the
  source reports no condition, the output may remain `not_reported`; the system
  must not manufacture an explicit condition or borrow one from another test.

Mass loaded, powder flow time, equipment capacity, specimen dimensions, test
frequency/rate, and processing parameters do not enter Properties. They are
reclassified only when an existing schema path is unambiguous; otherwise they
are quarantined rather than invented in another axis.

Qualitative or comparison-only tensile descriptions remain outside formal
Properties. Source text and complete candidate payload remain in the issue
audit.

#### Core tensile

YS, UTS, and elongation require a recognized tensile semantic, physical value
and unit, unique owner, and compatible test condition. Table header/row/owner
column binding is authoritative. Prose conditions cannot be borrowed across an
unrelated sample or test paragraph.

For one owner/property/condition identity:

- exact aliases merge;
- a richer uncertainty-bearing source may dominate a rounded projection only
  under the existing value/rounding proof;
- distinct orientations, temperatures, states, specimen types, elongation
  subtypes, ranges, thresholds, and independent assertions remain separate; and
- incompatible values without a proven distinguishing dimension form a
  conflict group and are not both promoted.

The verifier may choose an existing claim or quarantine the group, but it may
not compute a missing value, infer an unstated condition, or synthesize a
headline bundle.

### 6. Conflict sets

After deterministic grouping, claims with one semantic identity but
incompatible owner, value, unit, condition, role, data nature, or origin form a
conflict set. Deterministic precedence is allowed only for source-proven rules,
including a table cell over an unbound row projection and a measured table over
a nominal designation. Otherwise the set is sent to the verifier or
quarantined when the verifier budget is exhausted.

No conflict is resolved by confidence score, occurrence count, GT similarity,
or provider identity.

## Bounded risk-only verifier

### Eligibility

Only these deterministic risk classes are eligible:

- multiple plausible owners or a generic owner competing with specific states;
- one assertion producing incompatible structured paraphrases;
- property value/unit/condition conflicts;
- target/reference or experimental/literature origin conflict;
- Structure entity versus context ambiguity; and
- multi-column table projections whose cell binding is incomplete.

Low-risk accepted claims and deterministic duplicate merges never incur a
verifier call.

### Input

Each verifier batch contains only:

- opaque candidate IDs;
- the cited evidence block and necessary table header/row/column context;
- existing owner candidates from the source-derived graph;
- the conflicting structured fields; and
- the allowed decision enum.

It receives no full paper, business GT, expert GT, previous expected answer, or
unrelated candidate facts.

### Output contract

For every risk group the verifier returns exactly one of:

- `accept` with existing candidate IDs;
- `merge` with one existing survivor ID and loser IDs;
- `reassign_owner` with one existing owner ID;
- `quarantine_owner`;
- `quarantine_condition`;
- `quarantine_conflict`; or
- `needs_review`.

Response validation rejects unknown IDs, added fields, invented text, absent
group decisions, and decisions outside the enum. A failed, timed-out, invalid,
or missing decision becomes `needs_review` and is quarantined under the
precision-first policy.

### Budget, cache, and model independence

Verifier requests reuse the existing provider scheduler and generic endpoint
capability handling. There is no model-name branch. The request ceiling per
paper is the smaller of four batches and 20% of that paper's completed
extraction-task count, rounded up. Batches also obey fixed evidence-character,
candidate-count, and output-token limits.

Cache identity contains the OCR baseline, normalized evidence, candidate
payload hashes, owner graph digest, verifier contract version, prompt hash,
schema/ruleset digest, and generic LLM request identity. Cache replay must be
byte-deterministic after verifier decisions are frozen.

## Data flow

`OCR/figure Markdown -> current Alpha25 extraction tasks -> accepted anchors and facts -> promotion ledger -> assertion grouping -> identity/state routing -> axis promotion gates -> deterministic conflict resolution -> bounded risk verifier -> existing materialize_candidate -> unchanged final.json + existing issues.json/.md`

GT data enters only after `final.json` has been produced.

## Audit and error handling

Every non-pass-through decision emits one `MaterializeIssue`-compatible record.
Codes include:

- `promotion_assertion_duplicate_merged`;
- `promotion_richer_assertion_survived`;
- `promotion_empty_alias_item_removed`;
- `promotion_structure_context_quarantined`;
- `promotion_wrong_axis_quarantined`;
- `promotion_ambiguous_owner_quarantined`;
- `promotion_condition_unbound_quarantined`;
- `promotion_conflict_quarantined`;
- `promotion_owner_reassigned`;
- `promotion_verifier_merged`;
- `promotion_verifier_quarantined`; and
- `promotion_verifier_invalid_response`.

The issue contains the original candidate or group, full evidence, owner
candidates, deterministic risk codes, verifier request/response hashes when
applicable, survivor before/after, and suggested human action. Audit summaries
may remain concise in Markdown, but `issues.json` retains complete payloads.

No source Markdown, chart CSV, task response, or candidate is deleted. A paper
with no promoted material facts is not emitted as a successful empty result.

## Testing design

### Unit tests

Tests cover:

- exact sentence, subspan, and table-cell assertion grouping;
- multi-column tables preserving distinct owner/value cells;
- explicit “A and B both” ownership preservation;
- generic owner not broadcasting to multiple children;
- exact aliases merging without state/orientation collapse;
- identity-only and alias-only item removal;
- Structure entity/feature fusion and rich-over-generic dominance;
- unknown entity, location-only, caption-only, and method-only Structure
  quarantine;
- distinct phases, regions, states, and conditions remaining separate;
- property outcome versus process/test-control classification;
- value/unit/condition field grounding;
- YS/UTS/elongation subtype and condition preservation;
- incompatible tensile conflicts being quarantined;
- verifier enum, ID, completeness, and no-invention validation;
- verifier timeout, invalid response, budget exhaustion, and cache replay;
- complete issue audit payloads; and
- unchanged `final.json` schema paths.

### Stratified pilot

Run a source-error pilot covering papers with:

- large Structure overproduction;
- large item fragmentation;
- multi-column tensile tables;
- generic/base/state owner conflicts;
- high wrong-owner Composition risk;
- reference versus target prose; and
- condition-heavy tensile results.

The pilot must include representative papers 001, 006, 007, 012, 019, 025,
029, and 030. Rules remain generic; these IDs appear only in offline test and
evaluation configuration, never in production code.

Every pilot removal and reassignment is manually audited against OCR Markdown
before a 30-paper run. A rule that cannot be stated without a title, expected
value, or GT identity is rejected.

### Frozen 30-paper deterministic regression

First replay the 405 frozen extraction responses with the deterministic
promotion layer and verifier disabled. Acceptance requires:

- 30/30 papers complete, zero fatal schema errors, and zero provider calls;
- all Composition loose/strict matched and recall counts unchanged or improved;
- Composition loose F1 at least 65.9939% and strict F1 at least 32.6942%;
- global loose precision and F1 improve over v47;
- global loose recall remains at least 46.0718%;
- core-tensile loose matched and recall do not decline;
- core-tensile loose/strict precision and F1 do not decline;
- Structure and Properties duplicate, wrong-owner, value-conflict, and
  unsupported residual queues decrease;
- no non-Properties payload changes unless directly explained by an audited
  generic promotion rule; and
- deterministic materialization time increases by no more than 15%.

Failure preserves v47 as the production baseline. A failed gate is not bypassed
by weakening evidence rules solely to improve a metric.

### Bounded-verifier regression

After deterministic acceptance, run the pilot with actual verifier calls, audit
every decision, freeze the valid verifier responses, and replay them twice.
Proceed to all 30 papers only after the pilot passes.

Final rollout gates are:

- global unique loose precision at least 35%, with 40% as the convergence
  target;
- global unique loose recall at least 46.0718%;
- global unique loose F1 at least 40%;
- global unique strict F1 at least 16.9177%;
- core-tensile loose precision at least 85%;
- core-tensile loose recall at least 77.9343%;
- core-tensile loose F1 at least 81%;
- core-tensile strict F1 at least 59.7156%;
- Composition gates identical to the deterministic run;
- verifier requests no more than 20% of extraction tasks;
- comparable LLM-stage wall time no more than 25% above v47 extraction under
  comparable endpoint capacity;
- 30/30 successful papers and zero fatal/provider-contract errors; and
- byte-identical `final.json`, issue reports, summaries, and verifier decisions
  across two frozen replays, excluding documented automatic runtime metadata.

The 35% precision threshold is a minimum rollout milestone, not completion of
the broader convergence goal. Business-GT-level precision remains the target,
and additional generic precision increments continue if the result remains
materially below it.

## Rollout order

1. Add promotion contracts and source-assertion grouping.
2. Add the owner/state graph and no-broadcast routing.
3. Add Structure and wrong-axis Property gates.
4. Add tensile owner/condition/conflict gates.
5. Integrate audit emission and the unchanged materializer.
6. Run focused tests and the stratified deterministic pilot.
7. Run the frozen 30-paper deterministic regression.
8. Add the verifier contract, batching, cache, and provider integration behind
   a disabled-by-default flag.
9. Run and audit the live verifier pilot, freeze responses, and replay twice.
10. Run the full bounded-verifier 30-paper regression and compare against v47,
    business GT, and the GPT expert ledger.
11. Promote only if every required gate passes; otherwise retain v47 and report
    the failed requirement.

## Deliverables

- production promotion and verifier modules;
- integration with the existing Alpha25 extraction/materialization path;
- focused unit and integration tests;
- deterministic and bounded-verifier pilot reports;
- full 30-paper timing, provider-call, issue, and determinism reports;
- machine-readable and human-readable three-way comparisons;
- per-paper and per-axis metrics and adjudication CSVs; and
- unchanged public `final.json` plus complete existing issue audit artifacts.
