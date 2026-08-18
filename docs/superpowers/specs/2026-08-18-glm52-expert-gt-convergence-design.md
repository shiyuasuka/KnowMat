# GLM-5.2 Expert-GT Convergence Pipeline

## Goal

Improve the current GLM-5.2 Alpha25 baseline toward the adjudicated GPT-5.6-sol
expert ledger without changing the professionally reviewed extraction prompt or the
production `final.json` schema. The system must retain GLM's useful high recall while
reducing unsupported projections, cross-item duplicates, wrong material/state owners,
and conflicting values.

This is a production-quality repair, not benchmark fitting. The adjudicated expert GT
is used only for evaluation and regression. Runtime code must not contain paper titles,
expected values, GT sample identifiers, provider names, or model-name branches.

## Frozen baseline

The formal comparison against the adjudicated expert ledger establishes this baseline:

| Metric | final v5 |
|---|---:|
| Unique loose precision / recall / F1 | 0.162 / 0.339 / 0.219 |
| Unique strict precision / recall / F1 | 0.060 / 0.125 / 0.081 |
| Unique core-tensile loose precision / recall / F1 | 0.328 / 0.707 / 0.448 |
| Unique core-tensile strict precision / recall / F1 | 0.079 / 0.171 / 0.108 |
| Confirmed correct | 1081 |
| Unsupported-claim tags | 2936 |
| Wrong-owner tags | 552 |
| Value-conflict tags | 493 |
| Duplicate-claim tags | 1796 |

These adjudication tags can overlap. They diagnose failure modes; the one-to-one claim
matcher supplies precision, recall, and F1.

## Constraints

- Do not change the Alpha25 professional extraction system/user prompt or its compiled
  hash contract.
- Preserve the exact existing `final.json` structure and field hierarchy.
- Keep the business GT, final-v5 corpus, sealed expert GT, and adjudicated expert GT
  immutable.
- Preserve source evidence and record every removal, reassignment, merge, or quarantine
  in the existing `issues.json` and `issues.md` contract.
- Do not introduce a separate `quality_audit.json`.
- Do not run OCR again for deterministic development and the first 30-paper regression.
- Do not perform three complete extraction runs or choose a result by model confidence.
- Do not reduce output merely to match GT item or claim counts.
- Keep provider request behavior model-independent and configurable by endpoint
  capability rather than model name.

## Considered approaches

### 1. Prompt-only tightening

Add more prohibitions and examples to the extraction prompt. This is rejected for the
initial repair because the prompt is professionally reviewed, the observed issue is
mostly global fact organization, and prompt changes require costly stochastic reruns.

### 2. Deterministic cleanup only

Use stronger semantic signatures, owner graphs, field grounding, and conflict rules
without any additional model call. This is fast, reproducible, and can rematerialize
the frozen task cache, but deterministic rules cannot reliably decide all prose-level
entailment and implicit condition-binding cases.

### 3. Layered claim ledger with risk-only verification — selected

Compile all chunk facts into a paper-level atomic claim ledger, apply deterministic
grounding, ownership, deduplication, and conflict gates, then send only unresolved
high-risk claim groups to a compact verifier. This retains the speed and recall of one
GLM extraction pass while adding a bounded precision layer. The deterministic stage
ships and is evaluated first; risk-only verification is enabled only after its request
and latency bounds are demonstrated.

## Architecture

### 1. Atomic claim ledger

Introduce a focused production module under `src/knowmat/alpha25/` that converts each
validated `AxisFact` into an internal claim record before v11 materialization. The
internal record contains:

- evidence-unit and source-order provenance;
- axis and fact type;
- material owner candidate, role, data nature, state, region, and orientation;
- semantic key;
- raw and parsed value, uncertainty/range semantics, and unit family;
- test/process/observation condition;
- source origin;
- literal source evidence; and
- a deterministic risk and decision record.

The ledger is an internal representation and optional debug artifact. It is not added
to `final.json`. Accepted claims are projected through the existing materializer;
quarantined claims are preserved in the existing issue report.

### 2. Field-level grounding

Retain the current literal evidence-substring gate, then add structured field checks.
The gate verifies, where applicable:

- every emitted numeric value, range endpoint, inequality, and uncertainty is present
  in the cited evidence or is an explicitly lossless parse of it;
- unit and basis are supported by the same evidence group, including table headers;
- a raw owner label is present in evidence or linked through a deterministic table
  header/row anchor from the same evidence unit;
- numeric conditions such as temperature, duration, rate, orientation, and specimen
  labels are not borrowed from unrelated rows or sentences;
- `measured`, `nominal`, `provided`, `calculated`, and `inferred` composition origins
  remain distinct; a numeric alloy designation cannot become a measured component;
- target/reference and experimental/computed origin do not conflict with explicit
  citation or simulation language.

Presentation normalization may reconcile OCR-equivalent glyphs, LaTeX, whitespace,
and unit spelling. It must not invent semantic equivalence. A failed mandatory field
check produces a quarantine issue rather than silently deleting or accepting the fact.

### 3. Global identity and state graph

Build one evidence-derived identity graph for the complete paper before routing facts.
Nodes represent explicit materials, batches, source sample codes, and independently
named material states. Edges represent exact aliases, source-declared long/short names,
qualified state relations, and citation ownership.

Routing precedence is:

1. exact source sample/state label;
2. explicit source alias in the same evidence unit;
3. unique qualified state relation;
4. unique unqualified base owner; and
5. otherwise unresolved.

An ambiguous owner is never broadcast. A fact may be attached to several owners only
when the cited evidence explicitly names every owner and grammatically attributes the
same assertion to all of them. Otherwise it is quarantined as
`ambiguous_fact_owner`. A specific source sample wins over a related generic alloy
owner for the same semantic fact; unrelated materials with coincidentally equal values
remain distinct.

### 4. Axis-aware semantic deduplication

Replace JSON-shape-only duplicate decisions with per-axis canonical signatures while
preserving all raw fields and evidence.

- Composition: owner/state, source type, basis, normalized component/value/unit tuples,
  measurement context, and origin.
- Processing: owner/state, stage family, parameter/value/unit/condition tuples, route
  role, and origin.
- Structure: owner/state/region, structure kind, entity, feature/value/unit, method,
  and observation condition.
- Characterization: owner/state/region, method family, purpose/condition, and origin.
- Properties: owner/state, property family, value/range/uncertainty, canonical unit,
  method, temperature, orientation, specimen, environment, and origin.

Canonical signatures ignore generated IDs, confidence, evidence ordering, and harmless
presentation aliases. They do not ignore owner, material state, scientific condition,
or data origin. Duplicate records merge their evidence and retain the highest evidence
clarity only as metadata; confidence never decides scientific truth.

### 5. Conflict sets and quarantine

Claims with the same owner/state/semantic/condition identity but incompatible explicit
values, units, origins, or roles form a conflict set. The resolver may choose a claim
only when a deterministic source rule establishes precedence, such as an explicit
measured table value versus a nominal designation or a correctly bound table cell
versus a prose value for a different condition.

When deterministic evidence does not establish precedence, all conflicting alternatives
remain in the audit record and none is promoted as a single trusted fact. Issue codes
include `claim_value_conflict`, `claim_unit_conflict`, `claim_origin_conflict`, and
`claim_condition_conflict`.

### 6. Risk-only semantic verifier

The optional verifier receives compact batches of claims plus only their cited evidence
and deterministic identity context. It returns a strict decision contract:

- `accept`;
- `reject_unsupported`;
- `quarantine_owner`;
- `quarantine_condition`;
- `quarantine_conflict`; or
- `needs_review`.

It cannot add facts, values, owners, conditions, or evidence. It is invoked only for
risk classes that deterministic checks cannot resolve: multiple named owners, multiple
numeric candidates, cross-unit owner inheritance, nominal/measured ambiguity,
target/reference ambiguity, chart-derived scalar claims, and incompatible conflict
sets. Low-risk claims never incur a verifier call.

Verification is one bounded pass, not majority voting. The default request ceiling is
the smaller of four verifier batches per paper or 20% of that paper's extraction task
count. Exceeding the ceiling quarantines residual risky claims for review rather than
expanding requests. Provider options remain generic endpoint configuration.

### 7. Semantic coverage recovery

The existing task ledger proves transport coverage, not fact coverage. Add a semantic
coverage index for high-signal table cells and numeric evidence spans. It records
whether a source span produced an accepted, duplicate, quarantined, or absent claim.

Only uncovered high-signal spans are eligible for one targeted recovery task. Recovery
cannot resubmit the full paper and cannot run when the paper already reaches the
configured request ceiling. This stage is enabled after precision gates pass, so it
does not reintroduce unsupported projections while trying to recover recall.

## Data flow

`OCR/figure Markdown -> bounded GLM chunk extraction -> literal evidence gate -> atomic claim ledger -> field grounding -> global identity routing -> semantic dedup/conflict sets -> optional risk verifier -> existing v11 materializer/normalizer -> unchanged final.json + issues.json/.md`

The adjudicated expert GT enters only the offline evaluation path after production
outputs are complete.

## Error handling and audit

- Schema-invalid or non-literal evidence remains a failed extraction record under the
  existing contracts.
- Unsupported fields, ambiguous owners, semantic conflicts, and verifier uncertainty
  are recoverable review issues and are excluded from trusted production fields.
- Every issue stores the original fact, source evidence, deterministic reason, affected
  owner candidates, and suggested review action.
- Duplicate merges record the surviving claim signature and all merged provenance.
- No evidence or chart CSV is deleted or overwritten.
- A paper with zero eligible material facts after quarantine cannot be promoted as a
  successful empty result.

## Performance design

The deterministic ledger, indices, signatures, and conflict grouping must be linear or
near-linear in paper claims. They operate on cached task responses and add no provider
latency.

The live path retains the combined-axis planner, shared provider scheduler, bounded
evidence units, and one extraction pass. Risk-only verification and targeted recovery
have independent hard ceilings. The implementation must report extraction, provider
queue, provider call, deterministic quality, verifier, and recovery timing separately.

## Verification plan

### Focused tests

Tests cover:

- numeric and unit field grounding for prose and projected tables;
- nominal alloy designations not becoming measured compositions;
- same-unit table header/row/cell binding;
- exact, alias, qualified-state, generic, ambiguous, and explicitly shared owners;
- no ambiguous-owner broadcast;
- semantic duplicate aliases with evidence union;
- preservation of equal values belonging to unrelated owners or conditions;
- value/unit/origin/condition conflict sets;
- target/reference and experimental/computed separation;
- verifier request ceilings and inability to add facts;
- targeted recovery ceilings;
- complete issue/audit preservation; and
- unchanged `final.json` schema paths.

### Frozen 30-paper deterministic regression

Rematerialize the 405 frozen task-cache responses with zero OCR, LLM, and VLM calls.
Compare against both final v5 and the adjudicated expert GT. The deterministic phase is
accepted only when all conditions hold:

- 30/30 papers complete and zero fatal schema validations;
- unique loose F1 is greater than 0.219 and unique strict F1 is greater than 0.081;
- unique core-tensile loose F1 is greater than 0.448 and strict F1 is greater than
  0.108;
- unique loose recall remains at least 0.329, no more than 0.010 below the 0.339
  baseline;
- duplicate, wrong-owner, value-conflict, and unsupported residual queues each decrease;
- no extracted fact lacking literal evidence enters production;
- every quarantine, reassignment, and merge is auditable; and
- deterministic rematerialization wall time increases by no more than 15%.

If a metric fails, the implementation reports the failure and keeps the previous
production baseline; it must not weaken an evidence or owner rule solely to pass GT.

### Controlled live GLM regression

After the deterministic phase passes, run a representative pilot followed by the full
30-paper GLM extraction with the same frozen OCR baseline and unchanged professional
prompt. Acceptance requires:

- no extraction-task coverage loss;
- risk-verifier calls remain within their hard ceiling;
- no three-run voting or unbounded retry behavior;
- total model requests increase by no more than 20%;
- 30-paper LLM-stage wall time increases by no more than 25% under comparable endpoint
  capacity; and
- expert-ledger precision/F1 improve without exceeding the allowed loose-recall loss.

## Rollout order

1. Add the internal claim contract and deterministic field-grounding tests.
2. Add global owner routing with ambiguous-owner quarantine.
3. Add axis-aware semantic deduplication and conflict sets.
4. Integrate the existing issue writer and unchanged v11 projection.
5. Run the frozen 30-paper deterministic regression and tune only generic rules.
6. Add the bounded risk-only verifier behind a configuration switch.
7. Run a small controlled GLM pilot, then the 30-paper live regression.
8. Enable semantic recovery only after the precision path passes.

## Deliverables

- production claim-quality modules and integration;
- focused unit/integration tests;
- frozen-cache and controlled-live regression reports;
- per-paper timing and issue summaries;
- machine-readable comparison against the adjudicated expert GT; and
- a business-facing summary that distinguishes correctness, omissions, ownership,
  condition binding, conflicts, and duplicates.
