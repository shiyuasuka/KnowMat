# Alpha25 Hierarchical GLM Verification and Bounded Recovery

## Status

The user approved the architecture, data flow, audit policy, failure behavior,
and quantitative acceptance gates on 2026-08-25. This specification is the
written review gate before implementation planning.

## Goal

Improve the current GLM extraction pipeline toward both the business-provided
GT and the independently adjudicated GPT expert GT, with precision as the
primary objective and without manufacturing precision by deleting useful
recall. The main error classes are:

- one supported fact expanded, copied, or projected into several unsupported
  facts;
- correct values assigned to the wrong material, specimen, state, region, test
  condition, or role;
- duplicated assertions emitted by independent chunks;
- unsupported numeric interpretations of qualitative comparisons or chart
  context; and
- source-supported tensile facts omitted because their owner or condition is
  defined outside the extraction chunk.

The accepted design is a provider-neutral, hierarchical second-pass protocol:
the existing Alpha25 extraction prompt produces candidates, a separately
configured primary verifier is initially exercised with GLM-5.3, and a
separately configured fallback verifier is initially exercised with GLM-5.2.
Model names are experiment configuration, never runtime branches.

## Evidence Baseline

The accepted v205 30-paper baseline is
`data/output-alpha25-v205-residual-precision-accepted-final30-20260824`.
Its current comparison metrics are:

| Reference | Scope | Precision | Recall | F1 |
|---|---|---:|---:|---:|
| Business GT | Global loose | 0.489720 | 0.279417 | 0.355817 |
| GPT expert GT | Global loose | 0.467913 | 0.242806 | 0.319711 |
| Business GT | Core tensile loose | 0.874214 | 0.735450 | 0.798851 |
| GPT expert GT | Core tensile loose | 0.899371 | 0.671362 | 0.768817 |

The v204-to-v205 improvement was negligible because both versions
rematerialized the same 405 frozen GLM-5.2 task responses. Post-processing
cannot recover facts absent from those responses. A fresh model-assisted pass
is therefore required.

Earlier GLM-5.3 probes rejected an explicitly disabled thinking extension,
exceeded 180 seconds on some requests, produced an 8192-token truncation, and
had transient failures. The new design contains bounded requests, capability
fallback, per-bundle retry, and explicit truncation detection. These controls
do not imply that GLM-5.3 has already passed the quality or performance gate.

## Non-Negotiable Boundaries

- The professionally reviewed Alpha25 extraction prompt and its schema remain
  unchanged.
- Composition bypasses the new verifier and recovery path completely. Its
  scientific output must remain identical to v205.
- OCR, VLM, chart digitization, and figure description are outside this change.
- The public shape of `final.json` remains unchanged.
- Complete removed, merged, reassigned, recovered, quarantined, and unresolved
  records go to `quality_audit.json`. `issues.json` and `issues.md` contain
  compact issue codes and stable assertion references.
- Production extraction, verification, promotion, materialization, and
  packaging must not read GT, evaluation matches, paper IDs or titles,
  expected counts or values, model-specific expected behavior, or model names.
- The implementation is provider/model neutral. Capability configuration and
  fallback depend on declared endpoint capabilities and response behavior, not
  string matching on provider or model names.
- All evaluation GT access remains in the existing isolated evaluation layer.

## Considered Approaches

### Selected: GLM-5.2 candidates, independently configured GLM-5.3 verifier

Keep the stable high-recall candidate producer and use a stronger independent
GLM pass for paper-level reconciliation and bounded omission recovery. Fall
back by evidence bundle to GLM-5.2 when the primary verifier fails. This
separates generation from judgment, addresses cross-chunk context directly,
and limits the blast radius of GLM-5.3 latency or truncation.

### Rejected for the first trial: GLM-5.2 for both passes

This is operationally simpler and more stable, but correlated model errors are
likely: the same model may validate its own owner projection or unsupported
expansion. It remains the failure fallback and a future controlled comparison,
not the preferred primary arm.

### Rejected for the first trial: GLM-5.3 end to end

This maximizes model replacement but confounds candidate quality with verifier
quality and repeats the known endpoint latency and truncation risk across every
chunk. It also makes regressions harder to attribute.

## Architecture

The new subsystem sits after deterministic promotion and before
materialization. It consists of six isolated components. Promotion runs first
so the verifier judges the same atomic assertions that could otherwise enter
the public output; it must not spend provider calls on rows already removed by
deterministic precision gates.

### 1. Source inventory builder

The inventory builder consumes only the current paper's OCR/VLM source units
and frozen task provenance. It deterministically records:

- material and specimen mentions plus source-supported aliases;
- processing state, heat treatment, region, orientation, and role mentions;
- test families, method blocks, temperatures, strain rates, loading modes, and
  other explicit conditions;
- numeric and qualitative source assertions with stable source coordinates;
  and
- which source assertions are already covered by candidates.

The inventory does not infer a scientific fact, copy a condition between
owners, or mutate candidates. Composition inventory may be retained for local
context disambiguation only if required, but Composition candidates and output
are not verifier inputs and cannot be changed.

### 2. Candidate normalizer and assertion identity

Every non-Composition candidate becomes an immutable assertion envelope with a
stable `assertion_id`. The identifier is derived from source coordinates,
property axis, normalized candidate payload, and task lineage; it does not use
paper title, GT, model name, or expected output. The envelope preserves the
exact before-state and exposes owner, state, condition, value, unit, role,
nature, and provenance as independently reviewable fields.

### 3. Bounded evidence bundler

Candidates are grouped by property axis, overlapping source neighborhood, and
potential owner/state/condition compatibility. A bundle contains the relevant
inventory slice, candidate envelopes, and exact source spans, not an entire
paper dump.

Initial defaults are at most 12 candidate assertions and 12,000 source
characters per verifier request. A larger group is split deterministically at
source-boundary and owner-boundary cuts. Limits are configuration values and
part of the cache identity. Bundles are independently schedulable and may run
concurrently under the existing global provider concurrency budget.

### 4. Verification engine

The verifier uses a new, versioned verification protocol; it does not alter or
wrap the Alpha25 extraction prompt. For each assertion, the response must emit
exactly one decision:

- `accept`: value, unit, semantic, owner, state, and condition are directly
  supported;
- `merge`: two or more candidates represent the same source-supported fact and
  have one deterministic survivor;
- `reassign`: the fact is real but one or more ownership fields are attached to
  the wrong source-supported entity;
- `quarantine`: the assertion is contradicted, unsupported, improperly
  projected, or a qualitative comparison disguised as a numeric scalar; or
- `unresolved`: the supplied evidence cannot prove a safe decision.

Every accepted field and every reassigned field must cite one or more exact
input source spans. The deterministic response validator rejects invented
values, units, owners, source coordinates, or evidence text. `merge` requires
a complete member list and a survivor already present in the bundle.
`reassign` may select only an inventory entity explicitly present in the
bundle. A verifier cannot change the property value or create a new fact under
either decision.

### 5. Bounded omission recovery

After candidate verification, the coverage checker selects source assertions
that contain an explicit scientific numeric value or an explicit qualitative
comparison, belong to a supported non-Composition axis, and have no accepted,
merged, reassigned, quarantined, or unresolved assertion linked to them.

Recovery is one pass over these uncovered source assertions. Each request is
bounded by the same source-character ceiling and at most 10 uncovered source
assertions. Recovery may propose a new assertion only from supplied inventory
entities and literal source content. Every proposal is sent through the same
verification engine in a separate request before it can enter output. The
verifier cannot validate its own proposal in the same response. There is no
recursive recovery.

Qualitative tensile comparisons remain audit facts rather than numeric
`Properties`. Recovery cannot estimate chart values, interpolate curves, turn
adjectives into scalars, or copy a collective statement to every named owner
without explicit source scoping.

### 6. Decision applicator

The applicator is deterministic and runs after `promote_axis_facts` and before
`materialize_candidate`:

- `accept` passes the unchanged candidate;
- `merge` passes one survivor with a provenance union and quarantines the other
  full records;
- `reassign` passes the candidate with only validated ownership fields changed
  and audits the complete before/after pair;
- `quarantine` and a verifier's explicit scientific `unresolved` decision do
  not enter formal output;
- provider, transport, truncation, response-contract, or grounding-validator
  double failure preserves the unchanged promoted candidate in formal output,
  marks it `unresolved` for review, and records
  `verifier_unresolved_preserved`; and
- independently verified recovery produces a normal candidate carrying its
  source and recovery lineage.

Existing promotion and materialization precision gates remain in force. The
new verifier cannot bypass them.

## Model and Capability Configuration

Extraction, primary verification, and fallback verification have separate
configuration roles. For the first experiment they resolve to GLM-5.2,
GLM-5.3, and GLM-5.2 respectively. Code paths depend only on these roles.

Each role records credential-free endpoint identity, protocol, configured and
effective thinking mode, configured and effective structured-response mode,
token limit, timeout, retry policy, and concurrency. Unsupported optional
extensions fall back once at the capability layer and the effective result is
reused. An explicit provider rejection is not handled by a model-name branch.

Verification cache identity includes:

- protocol version;
- normalized inventory and exact source content;
- complete candidate envelopes;
- bundle and recovery limits;
- credential-free endpoint identity and model role configuration;
- configured and effective provider capabilities; and
- output token budget.

This prevents a model switch, capability fallback, evidence change, or
protocol change from reusing an incompatible response.

## Failure and Safety Behavior

A primary-verifier timeout, transient provider failure, truncation, malformed
JSON response, schema violation, or source-grounding violation triggers at
most the configured per-bundle retry, then sends only that bundle to the
fallback verifier. It never restarts the whole paper.

If both verifier roles fail because of provider, transport, truncation,
response-contract, or grounding-validation errors, every affected assertion
is preserved unchanged and becomes an audited `unresolved` review item. A
technical inability to verify is not scientific evidence that the candidate
is false. A verifier's explicit scientific `unresolved` decision and a
deterministic `SOURCE_EVIDENCE_NOT_LOCATED` failure remain isolated from formal
output. The system never silently emits an empty success or manufactures a
default scientific decision.

A bundle is applied atomically. A candidate-local exception cannot partially
change output. Decisions and audit ordering are deterministic under task and
response ordering permutations.

No credentials, authorization headers, credential-bearing URLs, full request
bodies, or unrestricted paper text are written to logs or committed reports.
Reports may contain bounded source evidence already permitted by the existing
scientific audit contract.

## Audit Contract

`quality_audit.json` contains one full record per decision with:

- stable `assertion_id`, bundle ID, protocol version, and decision;
- complete candidate before-state and output after-state when applicable;
- exact evidence spans and source coordinates;
- field-level owner/state/condition/value/unit validation;
- merge membership and survivor identity;
- recovery proposal and independent verification lineage;
- compact reason code plus verifier rationale;
- configured/effective verifier role and capability metadata;
- retry, truncation, fallback, and cache status; and
- deterministic timestamps or run-relative sequence information consistent
  with the repository's reproducibility convention.

`issues.json` and `issues.md` receive only concise codes and assertion IDs, such
as `VERIFIER_QUARANTINED`, `VERIFIER_REASSIGNED`,
`VERIFIER_UNRESOLVED`, `VERIFIER_FALLBACK`, and
`VERIFIED_RECOVERY`. They remain sufficient to locate the complete audit
record. `final.json` receives no audit-only field.

Per-paper and run summaries record extraction, inventory, verification,
recovery, promotion, and materialization wall time; provider-call, retry,
fallback, timeout, truncation, malformed-response, and cache-hit counts; input
and output tokens when exposed by the provider; and bundle throughput. Metrics
are separated by role so slow verification cannot be mistaken for slow OCR or
candidate extraction.

## Testing Strategy

Focused unit tests must cover:

- stable assertion and bundle identities;
- deterministic grouping and splitting at configured limits;
- exact evidence acceptance and rejection of invented text or coordinates;
- all five decision types and illegal decision transitions;
- duplicate merge with full provenance union;
- owner, state, and condition reassignment restricted to inventory entities;
- value or unit mutation rejection;
- qualitative comparison isolation from numeric `Properties`;
- collective-to-individual owner fan-out rejection;
- one-pass recovery and mandatory independent verification;
- primary failure, capability fallback, verifier fallback, and double failure;
- atomic application and input-order invariance;
- cache separation across protocol, evidence, limits, endpoint identity,
  capabilities, and model configuration;
- no GT, paper identity, title, expected value, or model-name behavior in the
  production path;
- byte- or canonical-scientific equality of Composition to v205;
- unchanged public `final.json` schema; and
- complete cross-links between quality audit and issues artifacts.

Integration tests use deterministic fake model responses to exercise the
existing extraction-to-materialization boundary. The Alpha25 focused suite and
full repository suite run with `./venv/bin/python -m pytest -o addopts=''`.
Any unrelated pre-existing fixture failure is documented separately and is not
represented as a clean full-suite pass.

## Five-Paper Blind Pilot

The five-paper list is frozen in an evaluation manifest before new provider
responses or scores are observed. It covers owner/condition ambiguity,
cross-chunk tensile context, duplicate or fan-out behavior, unsupported chart
or qualitative projection, and a Composition-rich control. Selection criteria
and resolved IDs are audit data, never production branches.

The pilot performs real provider calls over the fixed current OCR/VLM/chart
inputs. It compares the new result to the same five-paper v205 baseline against
both references:

- business GT:
  `data/gt/papers-native-ids-with-pdf-ocr-images-20260809`;
- GPT expert GT:
  `data/gt/gpt56sol-independent-expert-20260818/adjudicated`.

Promotion to the 30-paper run requires all of the following:

1. Global loose precision improves by at least 5 percentage points against
   each reference, recall declines by no more than 2 percentage points, and F1
   improves by at least 3 percentage points.
2. Core-tensile loose precision is at least 0.93 against each reference, recall
   declines by no more than 3 percentage points, and F1 exceeds the matching
   five-paper v205 baseline.
3. Source-adjudicated fact expansion, copying, or wrong-owner projection false
   positives decline by at least 30%.
4. Owner/condition errors decline by at least 30% and are reported separately
   from value-only matches.
5. Composition is scientifically identical to v205 on all five papers.
6. Five of five papers complete with zero fatal or silent-empty tasks;
   `final.json`, quality audit, and issues contracts validate and cross-link.
7. Median per-paper total runtime is at most 10 minutes. Extraction,
   verification, recovery, fallback, and queue time are reported separately;
   no verifier failure causes a whole-paper rerun.

The thresholds are evaluated against the fixed same-paper baseline, not the
30-paper aggregate quoted earlier. Important GT disagreements receive
source-level adjudication; neither GT is assumed infallible merely because an
unmatched fact exists.

If any gate fails, retain the pilot responses and audit, classify the failure,
and revise the general protocol or bundling strategy. Do not add paper-specific
or GT-derived rules. Do not run all 30 until a subsequent fixed pilot passes.

## Thirty-Paper Acceptance

After a passing pilot, run the same frozen configuration over all 30 papers and
produce:

- metrics against business GT and GPT expert GT for global loose/strict and
  core-tensile loose/strict scopes;
- per-axis and per-paper results;
- owner/condition and overprojection error counts;
- Composition equality evidence;
- API call, token, latency, retry, fallback, truncation, and cache statistics;
- complete quality-audit and issues artifacts; and
- a plain-language source-adjudicated conclusion identifying which system is
  more accurate, what each system misses, and which unmatched facts are true
  omissions versus GT incompleteness.

The implementation is accepted only if the 30-paper evidence proves a material
precision/F1 improvement without violating recall, Composition, schema,
auditability, production-safety, or runtime boundaries. Passing tests alone is
not evidence that the scientific quality objective is complete.

## Implementation Scope

Implementation planning may add focused modules under `src/knowmat/alpha25/`,
wire them into `src/knowmat/nodes/extraction.py`, extend configuration and the
fresh-extraction runner, add evaluation manifest/report support, and add
focused tests. It should not refactor OCR, chart extraction, Composition,
unrelated v11 paths, or the professionally reviewed Alpha25 extraction prompt.
