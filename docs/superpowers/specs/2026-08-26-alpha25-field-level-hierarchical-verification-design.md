# Alpha25 Field-Level GLM-5.2/5.3 Hierarchical Verification

## Status

The user selected the GLM-5.2/5.3 hierarchical-verification direction and
reconfirmed the precision-first objective on 2026-08-26. This document is the
written review gate before implementation planning. It refines the existing
hierarchical verifier; it does not change the professionally reviewed Alpha25
candidate-extraction prompt.

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

### Selected: deterministic risk routing plus field-level independent review

Route only narrowly defined high-risk assertions. GLM-5.3 judges each asserted
scientific field separately. GLM-5.2 independently reviews every hard-risk
assertion and confirms any destructive soft-risk decision. A deterministic
applicator uses only grounded, contract-valid field verdicts.

This directly targets owner/condition projection and unsupported expansion,
while allowing source-literal, low-risk facts to avoid provider latency.

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
risk reasons. Initial limits are at most three assertions and 3,500 source
characters. Limits are configuration and cache identity, never model-name
branches.

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

### 4. GLM-5.2 independent review

The fallback role receives the original assertion and evidence, not the
GLM-5.3 answer or rationale.

GLM-5.2 independently reviews:

- every hard-risk assertion, because hard-risk output requires positive
  cross-model support; and
- every soft-risk assertion for which GLM-5.3 proposes quarantine or
  reassignment.

The review uses the same field-level schema and grounding validator. Technical
fallback after a failed GLM-5.3 request remains distinct from scientific
second review and is reported separately.

### 5. Deterministic decision applicator

For low-risk bypassed assertions, output remains unchanged.

For soft-risk assertions:

- a fully grounded GLM-5.3 `supported` result preserves the assertion;
- quarantine or reassignment requires a compatible independent GLM-5.2
  decision;
- destructive disagreement or a confirmation failure preserves the unchanged
  assertion with a review issue; and
- reassignment is allowed only when both roles select the same supplied
  literal entity/coordinate.

For hard-risk assertions, precision takes priority:

- the assertion enters formal output only when both roles support every
  required field;
- it is reassigned only when both roles select the same supplied literal
  entity/coordinate and support all other required fields;
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
- `VERIFIER_OWNER_REASSIGNED`;
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
- exact same-target consensus for reassignment;
- hard-risk isolation on disagreement and every technical failure class;
- soft-risk preservation on failed destructive confirmation;
- input-order and concurrent-completion determinism;
- complete audit/issue cross-links;
- unchanged `final.json` schema; and
- canonical scientific Composition equality.

Integration tests use deterministic fake providers before any real API call.
The Alpha25 focused suite and independent-GT evaluator regression must pass.

## Five-Paper Real-API Pilot

The already frozen five-paper ambiguity pilot is replayed from the same cached
GLM-5.2 candidates. Candidate extraction remains cache-only so all output
differences come from the new verifier.

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
7. Average verifier provider calls are at most four per paper and median added
   verification wall time is at most three minutes per paper.
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
