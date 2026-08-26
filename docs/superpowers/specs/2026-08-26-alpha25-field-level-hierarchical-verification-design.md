# Alpha25 Field-Level GLM-5.2/5.3 Hierarchical Verification

## Status

The user selected the GLM-5.2/5.3 hierarchical-verification direction and
reconfirmed the precision-first objective on 2026-08-26. The first field-level
implementation was exercised as real-provider pilot r65 on the frozen five
papers. That pilot improved the already-pruned candidate replay but failed the
r58 quality and latency gates. This revision specifies the corrective design
before the next implementation pass. It does not change the professionally
reviewed Alpha25 candidate-extraction prompt.

## Goal

Move the current GLM pipeline closer to both the business GT and the
independently adjudicated GPT expert ledger by improving:

- global loose precision without manufacturing a score by deleting true facts;
- material, sample, state, region, orientation, role, and condition ownership;
- core-tensile factual and attribution quality; and
- verification latency and provider-call efficiency.

Composition is already the strongest GLM axis in the current comparison. This
iteration must leave its scientific output unchanged.

## Evidence and Problem Statement

The r58 frozen-candidate result is the current comparison baseline:

| Metric against GPT expert ledger | r58 |
| --- | ---: |
| Overall unique loose precision / recall / F1 | 0.4734 / 0.2502 / 0.3274 |
| Properties unique loose precision / recall / F1 | 0.6878 / 0.4392 / 0.5361 |
| Core-tensile unique loose precision / recall / F1 | 0.8984 / 0.7887 / 0.8400 |

The sealed expert ledger omits at least two source-literal paper_015 UTS
claims; the source-adjudicated core-tensile estimate is therefore also retained
as a supplemental measure. Neither the expert ledger nor business GT is
treated as infallible merely because a system claim is unmatched.

The existing risk-routed verifier trial did not justify its cost. On the frozen
five-paper pilot it:

- routed 68 of 158 eligible non-protected facts;
- made 50 verifier provider calls;
- incurred 15 primary failures and 15 fallback calls;
- produced zero consensus quarantines; and
- changed no formal scientific output while the parallel pilot wall time was
  542.8 seconds.

Its main weakness is the decision contract. One response must currently judge
an entire multi-field assertion as `accept`, `merge`, `reassign`,
`quarantine`, or `unresolved`. This makes a model either accept a partially
unsupported assertion or reject a complete assertion without identifying the
bad field. Grounding validation then rejects many otherwise useful responses,
and destructive consensus rarely activates.

The r58 automated disagreement queue is useful for locating examples but is
not a deletion list. Source review shows that many
`expert_gt_missing_or_unsupported` claims are literal facts missing from the
expert ledger, and many `wrong_owner` rows are compatible aliases rather than
scientific misattributions.

### r65 real-provider evidence

Pilot r65 used GLM-5.3 field-level primary review and GLM-5.2 singleton
field-level independent review. All five papers completed, but the result is
not eligible for a 30-paper run:

| Five-paper metric against GPT expert ledger | precisionfix replay | r58 same papers | r65 |
| --- | ---: | ---: | ---: |
| Overall unique loose precision | 0.4779 | 0.5110 | 0.5126 |
| Overall unique loose recall | 0.3476 | 0.4947 | 0.3797 |
| Overall unique loose F1 | 0.4025 | 0.5027 | 0.4363 |
| Properties unique loose precision | 0.5439 | 0.7143 | 0.6731 |
| Properties unique loose recall | 0.4921 | 0.6349 | 0.5556 |
| Core-tensile unique loose precision | 0.6486 | 0.8548 | 0.7879 |
| Core-tensile unique loose recall | 0.9057 | 1.0000 | 0.9811 |

r65 therefore improved precisionfix overall precision by 3.47 points,
Properties precision by 12.92 points, and core-tensile precision by 13.92
points. It did not improve over r58 in the target Properties or core-tensile
precision measures, and its overall recall was 11.50 points below r58.

The five-paper wall time was 1,451.9 seconds. Per-paper verification wall time
ranged from 211.6 to 1,435.1 seconds. The fallback role repeatedly generated
4,097-token truncated responses for singleton requests whose validated JSON
should be small. Across the five papers, 48 hard assertions caused one
independent field response per assertion, including assertions that the
primary role had already failed or rejected. This work could not change the
final decision and amplified provider-slot contention.

The audit also exposed deterministic false failures in direct tensile facts.
For example, a candidate value `1222 ± 56` was rejected against literal source
text `1222 \\pm 56` because the verifier token normalizer did not share the
existing evidence normalizer's `\\pm` equivalence. Compact source-coordinate
location also stopped at the final digit of `23% \\pm 1%`, omitting the trailing
percent sign from the verifier evidence span. These are presentation-coordinate
bugs, not scientific disagreements, and must be fixed before interpreting
model verdict quality.

## Non-Negotiable Boundaries

- Do not change the professional Alpha25 extraction prompt, extraction schema,
  or package identity.
- Do not change the public shape of `final.json`.
- Do not modify Composition candidates or Composition materialization.
- Do not alter OCR, VLM, chart digitization, or figure-description behavior.
- Do not read GT, evaluation matches, paper IDs or titles, expected counts or
  values, or model-specific expected behavior in production code.
- Do not branch on provider or model-name strings. GLM-5.3 and GLM-5.2 are
  initial role configuration only.
- Do not invent or numerically repair a value, unit, owner, state, condition,
  or source coordinate.
- Every removed, isolated, merged, or reassigned record remains complete and
  traceable in `quality_audit.json`; `issues.json` and `issues.md` contain only
  compact codes and stable assertion references.

## Alternatives Considered

### Selected after r65: gated field primary plus compact independent review

Route only narrowly defined high-risk assertions. GLM-5.3 judges each asserted
scientific field separately. Only hard-risk assertions that receive a complete,
grounded, all-fields-supported primary decision proceed to GLM-5.2. GLM-5.2
independently checks the same immutable fields but returns a compact
whole-assertion confirmation rather than repeating the full field object graph.
A deterministic applicator accepts a hard assertion only after both positive
reviews.

This directly targets owner/condition projection and unsupported expansion,
while allowing source-literal, low-risk facts to avoid provider latency. It
also removes independent-review calls that cannot possibly produce formal
acceptance.

### Rejected after r65: singleton full-field independent review

The full field schema remains valuable for the GLM-5.3 primary because it
identifies the unsupported coordinate. Repeating that schema for every hard
assertion caused 4,097-token truncations, 117 provider calls across five papers,
and long-tail paper latency above 20 minutes. Raising the token limit would
make malformed behavior slower and more expensive without adding decision
authority.

### Rejected: primary-only destructive decisions

Accepting a hard assertion after one model would be faster, but it removes the
independent positive-consensus boundary selected for precision. The compact
review reduces response size without weakening that boundary.

### Rejected: retain whole-assertion verification

This is the smallest code change, but the five-paper trial made 50 calls and
produced no formal delta. Increasing bundle size or timeouts would make the
same ambiguous decision contract more expensive without addressing its cause.

### Rejected as the primary approach: deterministic gates only

Deterministic gates remain useful for source syntax and exact duplicates, but
they cannot safely adjudicate many multi-owner, multi-condition, or
cross-sentence mappings. Previous deterministic iterations have already
captured most low-risk gains.

## Architecture

The subsystem remains after deterministic promotion and before
materialization. The new protocol has five bounded stages.

### 1. Deterministic pre-collapse

Before any provider request, exact candidate duplicates and exact
source-assertion duplicates are resolved by existing source-only rules. A
provider is not asked to merge byte- or canonically identical records.

No scientific field is added, inferred, or reassigned in this stage.

### 2. Severity-aware risk router

Composition always bypasses verification. Low-risk facts with a literal owner,
literal value/unit, and one compatible condition path also bypass it.

The router assigns only `soft` or `hard` risk. A rule may inspect the candidate,
its literal source evidence, stable inventory anchors, and other candidates in
the same paper. It may not inspect GT or evaluation output.

Hard risk is deliberately narrow:

- the asserted owner is absent while two or more incompatible owners occur in
  the supplied evidence;
- the asserted condition is absent while multiple incompatible test or process
  conditions occur in the supplied evidence;
- the same scientific payload is projected to multiple owners without an
  explicit collective or one-to-one source mapping;
- a `respectively` sentence or multi-column row lacks a deterministic
  one-to-one mapping for the asserted owner/value/condition;
- a qualitative comparison, derived difference/ratio, independent-variable
  value, or source locator is represented as a formal numeric response; or
- an incomplete or generic owner cannot identify a unique material/state
  inventory entity.

Soft risk includes lower-confidence evidence envelopes, multi-span payloads,
or contextual paraphrases that remain compatible with one owner and one
condition. A single absent short alias is not hard risk when the evidence and
inventory prove a unique compatible entity.

Core-tensile Properties are no longer bypassed as an entire axis. Only
hard-risk or independently corroborated soft-risk tensile assertions are sent
to the verifier. Direct table cells and complete source sentences with unique
owner/value/unit/condition coordinates continue unchanged.

### 3. GLM-5.3 primary field adjudication

The primary verifier receives a bounded bundle containing one related
assertion group, exact evidence spans, compatible inventory entities, and the
risk reasons. Revised pilot limits are at most six assertions, 6,000 source
characters, and a 3,072-token response budget. Limits are configuration and
cache identity, never model-name branches.

For every assertion, the response contains a verdict for each required field:

- `semantic`;
- `value`;
- `unit` when asserted;
- `owner`;
- `state` when asserted;
- `condition` when asserted; and
- `origin` or role when asserted.

Each field verdict is exactly `supported`, `contradicted`, or `not_proven` and
cites existing evidence IDs. An owner/state/condition correction may select
only an existing inventory entity or literal coordinate supplied in the
request. The verifier cannot emit a new value, unit, semantic, evidence span,
or entity.

The deterministic response validator requires one verdict for every asserted
field, validates every identifier, and rejects invented text or coordinates.
A malformed field does not partially mutate an assertion.

Before provider verdict validation, every immutable coordinate uses one shared
presentation-only normalizer. It must preserve scientific symbols and source
positions while treating the following forms as identical:

- `±` and `\\pm`;
- `°` and `^\\circ`;
- `µ`/`μ` and `\\mu`; and
- a literal trailing `%` retained by compact source-span location.

This layer may remove TeX presentation syntax. It may not drop or infer a
number, percent sign, unit, owner token, condition, or semantic word. A
paraphrase such as removing `which were` from a categorical structure value
remains nonliteral and cannot be repaired by normalization.

### 4. Gated GLM-5.2 compact independent review

The fallback role receives the original assertion and evidence, not the
GLM-5.3 answer or rationale.

GLM-5.2 independently reviews only:

- hard-risk assertions for which every required GLM-5.3 field verdict is
  grounded, contract-valid, and `supported`.

If the primary contradicts, cannot prove, or technically fails any field, the
hard assertion is already unable to form positive consensus. It is isolated
immediately and the audit records `secondary_skipped_primary_nonpositive`.
This does not weaken fail-closed behavior; it removes a request that could not
change the result.

The compact response protocol returns exactly one decision per assertion:

- `all_fields_supported`;
- `contradicted`; or
- `not_proven`.

Each decision contains existing evidence IDs, an optional list of failed field
names for a non-positive verdict, and a short reason code. It contains no free
rationale and no copied assertion, field payload, evidence text, primary
answer, or correction target. The deterministic validator independently
checks every required candidate literal against the cited evidence before an
`all_fields_supported` result is usable.

Primary-positive hard assertions are packed in blinded compact bundles of at
most six assertions and 6,000 source characters. The compact output budget
remains 1,024 tokens pending a verifier-transport redesign. A controlled
2,048-token r70 pilot was rejected: it still produced 14 compact truncations,
each exactly at 2,049 completion tokens with zero reasoning tokens, while
raising total verifier attempts to 46 across five papers. Strict JSON-schema
output was rejected by the endpoint. Under Chat Completions, tool-call,
single-label text, and explicit-thinking probes also reached their output
limit without a usable decision. A direct OpenAI Responses API probe,
however, returned a correct singleton `S` decision in 148 output tokens and
4.4 seconds. The LangChain Responses adapter failed on the same endpoint, and
the existing three-assertion compact JSON protocol did not produce parseable
output within 1,024 tokens. The next design iteration should therefore test a
provider-neutral per-role Responses transport plus a minimal assertion-label
contract; raising the Chat Completions limit does not repair the behavior.
A truncated multi-assertion compact review may split once into smaller compact
bundles; a truncated singleton is a technical failure and is not retried with
a larger unconstrained generation.

Soft-risk assertions are never destructively changed in this precision pass.
A non-positive primary soft review preserves the unchanged assertion with a
review issue. This avoids spending a second model call on a deletion that the
selected policy would preserve on disagreement or technical failure anyway.

### 5. Deterministic decision applicator

For low-risk bypassed assertions, output remains unchanged.

For soft-risk assertions:

- a fully grounded GLM-5.3 `supported` result preserves the assertion;
- a contradiction, `not_proven`, malformed response, grounding failure, or
  provider failure also preserves the unchanged assertion with a review issue;
  and
- no soft-risk quarantine or reassignment is applied in this precision pass.

For hard-risk assertions, precision takes priority:

- the assertion enters formal output only when both roles support every
  required field;
- no hard-risk reassignment is performed in this pass; a wrong or ambiguous
  owner/condition is isolated with its complete source record;
- a contradiction, `not_proven`, scientific disagreement, provider failure,
  truncation, malformed response, or grounding failure isolates it from formal
  output; and
- the complete candidate, risk reasons, both responses or failures, and the
  decision are retained in `quality_audit.json`.

This stricter technical-failure policy applies only to narrowly routed hard
risks. It does not allow a provider outage to empty ordinary low-risk output.

## Precision-First Recovery Boundary

Omission recovery is disabled for this iteration. The same run must not both
remove ambiguous assertions and generate new facts, because that would obscure
the precision effect and increase provider cost.

After this precision iteration passes the five-paper and 30-paper gates,
source-literal omission recovery may be designed and measured as a separate
recall iteration over the frozen accepted output.

## Provider-Neutral Configuration and Caching

Extraction, primary verification, and independent review remain separate
roles. The initial experiment configures GLM-5.2 extraction, GLM-5.3 primary
review, and GLM-5.2 independent review.

Cache identity includes the protocol version, field schema, risk-routing
version and reasons, exact assertion/evidence/entity payload, bundle limits,
credential-free endpoint identity, model-role configuration, effective
capabilities, and output-token budget.

Primary-field and compact-independent protocols have distinct versioned cache
identities. A full-field response can never satisfy a compact-review cache key
or vice versa.

Unsupported optional provider extensions fall back through declared or
observed capabilities. No model prefix is inspected.

## Audit and Issue Contract

Every routed assertion receives a complete audit record containing:

- stable assertion, bundle, protocol, and risk-routing identities;
- risk severity and source-only reason codes;
- complete before-state and optional after-state;
- exact evidence and inventory coordinates;
- field-level verdicts from each role;
- configured/effective role and capability metadata;
- cache, latency, token, retry, timeout, truncation, and failure metadata; and
- final deterministic action.

Compact issue codes include:

- `VERIFIER_FIELD_CONTRADICTION`;
- `VERIFIER_FIELD_NOT_PROVEN`;
- `VERIFIER_HARD_RISK_ISOLATED`;
- `VERIFIER_ROLE_DISAGREEMENT`;
- `VERIFIER_TECHNICAL_FAILURE_ISOLATED`; and
- `VERIFIER_SOFT_RISK_PRESERVED`.

`final.json` contains no verifier-only field.

## Testing Strategy

Unit tests must prove:

- stable risk, assertion, bundle, and cache identities;
- hard versus soft classification for positive and fail-closed examples;
- preservation of literal aliases and direct table/source-sentence facts;
- field completeness and rejection of invented IDs, values, units, owners,
  conditions, and evidence;
- independent-review blindness to the primary answer;
- secondary skipping for every primary non-positive hard assertion;
- compact all-fields support validation against every required immutable
  coordinate;
- compact bundle partitioning without sibling poisoning;
- hard-risk isolation on disagreement and every technical failure class;
- soft-risk preservation on every primary non-positive or technical result;
- input-order and concurrent-completion determinism;
- complete audit/issue cross-links;
- unchanged `final.json` schema; and
- canonical scientific Composition equality.

Integration tests use deterministic fake providers before any real API call.
The Alpha25 focused suite and independent-GT evaluator regression must pass.

## Five-Paper Real-API Pilot

The already frozen five-paper ambiguity pilot is replayed from the r58 accepted
candidate ledger, not from the lower-recall precisionfix materialization. The
precisionfix replay remains a diagnostic comparison only. Candidate extraction
remains cache-only so provider calls and output differences come from the new
verifier and the explicitly versioned deterministic coordinate fixes.

The pilot uses real GLM-5.3 and GLM-5.2 calls and records the configured and
effective capabilities. Every changed assertion is source-reviewed before
aggregate scores are interpreted.

Promotion to 30 papers requires all of the following:

1. Five of five papers complete with zero fatal or silent-empty results.
2. Composition is canonically identical on five of five papers.
3. No known source-supported assertion is quarantined by an invalid mapping or
   provider failure outside the narrowly defined hard-risk class.
4. Source-adjudicated unsupported or wrong-owner/condition formal assertions
   decline; every formal delta has a complete audit record.
5. Against each frozen reference, overall unique loose precision improves by
   at least two percentage points, recall declines by at most 1.5 percentage
   points, and F1 does not decrease.
6. Core-tensile unique loose precision does not decrease, recall declines by at
   most one percentage point, and no direct source-literal tensile table row or
   complete source-sentence fact is lost.
7. Average verifier provider calls are at most seven per paper, median added
   verification wall time is at most three minutes per paper, no paper exceeds
   six minutes, and no singleton compact response reaches its output limit.
8. No verifier failure reruns candidate extraction or the whole paper.

If a score gate conflicts with source adjudication because a GT omits a literal
fact or treats compatible aliases as different owners, both frozen and
source-adjudicated results are reported. A GT mismatch alone never becomes a
production rule.

## Thirty-Paper Acceptance

Only a passing fixed pilot is promoted to all 30 papers. The 30-paper report
must compare the new output, r58, business GT, and GPT expert ledger with the
same evaluator and paper pairing.

Acceptance requires:

- overall unique loose precision and F1 exceed r58 against both references;
- core-tensile unique loose F1 is at least the r58 value of 0.8400 against the
  GPT expert ledger, with the source-adjudicated correction reported
  separately;
- source-adjudicated owner/condition and unsupported-projection errors decline
  without knowingly deleting true direct facts;
- Composition is canonically identical for 30 of 30 papers;
- all outputs validate with unchanged `final.json` shape and complete
  `quality_audit.json` / `issues.json` / `issues.md` links;
- provider-call, latency, cache, retry, fallback, truncation, and failure
  statistics are complete; and
- the conclusion explains which metric differences are genuine system errors,
  compatible alias differences, or GT omissions.

Passing tests alone is not completion. The implementation is accepted only
when the real-provider pilot and 30-paper evidence demonstrate movement toward
the precision, attribution, tensile-quality, and runtime objectives.

## Implementation Scope

Implementation planning may update the verification risk classifier,
verification contracts, prompts, client, applicator, runner configuration,
audit packaging, and focused tests under the existing Alpha25 subsystem. It
must not refactor unrelated extraction, OCR, chart, Composition, or public
schema paths.
