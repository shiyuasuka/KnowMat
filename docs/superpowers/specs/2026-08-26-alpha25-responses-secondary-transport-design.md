# Alpha25 Responses Secondary Transport and Paper-Level Compact Review

## Status

The user directed continued optimization toward higher global precision,
correct owner/condition attribution, and stronger tensile quality without
regressing Composition. The previously presented recommendation was a
GLM-5.3 field primary plus GLM-5.2 Responses-based minimal independent review.
This document specifies that next iteration before implementation.

This design revises only the verifier transport and its private independent
review protocol. It does not revise the professionally reviewed Alpha25
candidate-extraction prompt.

## Goal

Retain the r68/r69 precision improvement while removing technical GLM-5.2
Chat Completions failures that isolate source-literal facts and inflate
latency. The implementation must:

- preserve hard-risk dual-model positive consensus;
- improve or maintain global and Properties precision and F1;
- avoid material core-tensile recall loss;
- reduce verification to at most seven provider calls per paper on average;
- eliminate singleton independent-review truncation in the five-paper pilot;
- preserve every Composition scientific claim; and
- keep the public `final.json` shape unchanged.

## Evidence

The r68/r69 five-paper result improved over the matching r58 control:

| Unique loose metric against GPT expert GT | r58 | r68/r69 |
| --- | ---: | ---: |
| Overall precision / recall / F1 | 0.5111 / 0.4947 / 0.5027 | 0.5692 / 0.4840 / 0.5231 |
| Properties precision / recall / F1 | 0.7143 / 0.6349 / 0.6723 | 0.7900 / 0.6270 / 0.6991 |
| Core-tensile precision / recall / F1 | 0.8548 / 1.0000 / 0.9217 | 0.8814 / 0.9811 / 0.9286 |

It still made 42 provider calls, or 8.4 per paper, and produced 11 compact
truncations. Some primary-supported literal facts were isolated only because
the independent role did not return a valid response.

The controlled 2,048-token r70 attempt did not repair Chat Completions:

- 46 provider attempts across five papers;
- 14 compact truncations and seven compact splits;
- every inspected failure stopped at 2,049 completion tokens; and
- reported reasoning tokens were zero.

The r70 pre-verifier accepted fact counts did not match r68/r69, so its GT
scores are diagnostic rather than a valid quality A/B. This design therefore
adds a pre-verifier digest gate before any future comparison.

Transport probes isolated the failure:

- strict JSON-schema response format was rejected by the endpoint;
- Chat Completions tool calls and minimal text labels reached their output
  limit without usable content;
- the LangChain Responses adapter did not reliably parse the endpoint;
- the official OpenAI Responses client returned a correct singleton `S` in
  4.4 seconds and 148 output tokens; and
- the same direct client returned a cardinality-valid three-assertion label
  array `['S', 'S', 'S']` in 10.4 seconds and 551 output tokens.

The last result establishes a bounded alternative without changing model
roles or scientific extraction behavior.

## Non-Negotiable Boundaries

- Do not change the Alpha25 extraction prompt, extraction schema, or package
  identity.
- Do not change the public `final.json` shape.
- Do not modify Composition candidates, routing, promotion, or
  materialization.
- Do not alter OCR, VLM, chart digitization, or figure description.
- Do not implement model-name, provider-name, paper-ID, title, expected-value,
  GT, or evaluation branches.
- Do not send primary decisions, rationales, GT, or expected labels to the
  independent role.
- Do not invent, repair, normalize, reassign, or copy scientific content in
  the independent-review path.
- A hard-risk assertion enters formal output only after a complete grounded
  positive primary decision and an independent `S` decision.
- Soft-risk assertions remain unchanged; a non-positive or failed primary
  review only adds review metadata.
- Omission recovery remains disabled.
- Every isolation and technical failure remains complete in
  `quality_audit.json`; `issues.json` and `issues.md` contain compact codes and
  stable references.

## Alternatives

### Selected: per-role Responses transport with indexed label arrays

Keep field-level primary review unchanged. Send only primary-positive hard
assertions to an independently configured Responses transport. The response is
a JSON array with exactly one label per request assertion in stable request
order:

- `S`: every required field is supported;
- `C`: at least one asserted field is contradicted; or
- `N`: at least one asserted field is not proven.

The array contains no candidate copy, evidence copy, rationale, or correction.
Deterministic code requires the exact array length and allowed labels before
mapping positions back to stable assertion IDs.

This is the smallest response proven to preserve bundle cardinality on the
configured endpoint. It retains independent positive consensus while avoiding
the verbose object graph that triggered length failures.

### Rejected: keep the complete compact JSON response

The current response contains assertion IDs, evidence IDs, failed fields, and
reason codes. It is easier to read in isolation, but failed both 1,024- and
2,048-token Chat Completions trials. The same three-assertion object did not
produce parseable JSON within 1,024 Responses tokens. Increasing the budget
does not satisfy the speed or truncation gates.

### Rejected: one Responses request per assertion

Singleton labels are simple and one probe succeeded, but the five-paper hard
assertion volume would recreate the r65 call explosion. It cannot meet the
average provider-call gate.

### Rejected: silently change the secondary model or endpoint

A different service might be reliable, but it changes the selected experiment
and may conceal a transport defect. Models and endpoints remain external role
configuration. A future trial may change them explicitly without production
code changes.

## Architecture

### 1. Provider-neutral role transport configuration

`VerifierRoleConfig` gains an API transport field with two values:
`chat_completions` and `responses`. Transport is part of cache identity and
runtime manifests.

Environment configuration is role-based:

- `KNOWMAT2_ALPHA25_VERIFIER_API_MODE` configures the primary default;
- `KNOWMAT2_ALPHA25_VERIFIER_FALLBACK_API_MODE` configures the independent
  role and otherwise inherits the primary mode.

The five-paper pilot configures the primary role as Chat Completions and the
independent role as Responses. No model string is inspected.

The Responses path uses the official OpenAI client directly because the local
LangChain adapter failed on a valid provider response. It uses the configured
endpoint, model, timeout, output budget, and reasoning effort. Credentials are
read from the existing connection environment and are never cached, logged, or
included in an identity digest.

Unsupported optional reasoning/thinking parameters may be retried once without
that optional parameter through the existing generic capability-fallback
policy. A Responses failure never silently switches transport to Chat
Completions; it fails closed and remains auditable.

### 2. Minimal independent-review protocol

The private protocol version advances to
`alpha25_compact_label_review_v2`. Each request contains:

- protocol and bundle IDs;
- a zero-based stable request index for every assertion;
- immutable candidate data and required field names;
- only supplied inventory entities and evidence; and
- the exact expected array length and label definitions.

It contains no primary answer, primary evidence selection, primary rationale,
GT, or expected decision.

The final answer must parse as one JSON array whose length equals the number of
request assertions and whose entries are exactly `S`, `C`, or `N`. Additional
text, a missing entry, an extra entry, a different value, an incomplete
Responses status, or an absent final message is a technical failure.

The provider's reasoning summary is not decision authority. It may be retained
verbatim in `quality_audit.json` for debugging, with response status and token
usage, but is excluded from `final.json`, compact issues, cache identity, and
scientific mutation logic.

### 3. Two-phase paper-level execution

The current client finishes primary and independent review inside each
verification bundle. That prevents compact packing across primary bundles and
keeps call volume above target.

The revised pipeline executes one paper in two phases:

1. Run every primary field bundle with current bounded concurrency.
2. Partition and validate each primary decision independently.
3. Preserve soft assertions and mark non-positive hard assertions as secondary
   skipped.
4. Collect all primary-positive hard assertions across the paper.
5. Repack them into blinded independent-review bundles of at most six
   assertions and 6,000 supplied evidence characters. Bundles remain axis
   homogeneous so current scientific contracts are not broadened.
6. Run Responses label review for those compact bundles.
7. Map valid label positions to stable assertion IDs and apply existing
   fail-closed hard consensus.

Primary field bundles and independent label bundles have separate IDs, cache
directories, token budgets, and metrics.

### 4. Deterministic decision application

For hard risk:

- primary all-fields-supported plus independent `S` accepts the unchanged
  assertion;
- primary contradiction/not-proven/failure skips independent review and
  isolates the assertion;
- independent `C`, `N`, malformed output, incomplete response, timeout,
  provider error, or grounding failure isolates the assertion; and
- no reassignment occurs in this pass.

The independent label never overrides primary field evidence. A positive
decision remains usable only because the primary decision already passed the
complete field contract and deterministic evidence grounding.

For soft risk, primary review is advisory and the unchanged assertion is
preserved with review metadata on any non-positive or technical result.

### 5. Truncation and split policy

The initial Responses label budget remains 1,024 output tokens. A truncated or
cardinality-invalid multi-assertion label bundle may split once into smaller
label bundles. A singleton is never expanded or retried with a larger budget.

The five-paper acceptance gate requires zero singleton label truncation. A
single violation blocks the 30-paper run.

### 6. Cache and audit

Cache identity includes:

- private protocol version;
- request kind;
- role, model, endpoint identity, API transport, thinking/reasoning mode,
  timeout, and output budget;
- complete blinded request payload; and
- prompt version.

Cache payload includes:

- final label array;
- mapped assertion decisions;
- Responses status and incomplete details;
- raw reasoning summary and final output text;
- token and latency metadata; and
- capability fallback history.

It excludes API keys and other credentials.

`quality_audit.json` records the independent bundle ID, request index, label,
cache hit, transport, status, reasoning summary, usage, failure code, and final
formal action for each assertion. `issues.json` and `issues.md` add only stable
codes such as:

- `verifier_secondary_label_nonpositive`;
- `verifier_secondary_label_cardinality_invalid`;
- `verifier_secondary_responses_incomplete`; and
- `verifier_secondary_transport_failure`.

No verifier-private field enters `final.json`.

### 7. Pre-verifier reproducibility gate

Before provider calls, the pilot generates a no-verifier control and a
canonical pre-verifier digest per paper from:

- accepted/promoted immutable scientific candidate payloads;
- source and task-cache hashes;
- planner/evidence-gate configuration; and
- enabled deterministic promotion switches.

The verified run must reproduce the same digest for every paper. A mismatch
aborts the quality A/B and records the configuration difference. Accepted-fact
counts alone are not sufficient proof.

## Testing

Unit tests must prove:

- role API modes are parsed without model-name branches and affect cache
  identity;
- Responses requests use `max_output_tokens`, configured timeout, and generic
  optional-parameter fallback;
- credentials never enter cache identity or audit;
- exact label arrays map by position to stable assertion IDs;
- wrong length, invalid labels, extra prose, incomplete status, missing final
  output, and provider errors fail closed;
- primary results complete before paper-level independent bundles are built;
- independent bundles pack across primary bundles but stay within axis,
  assertion-count, and evidence-size limits;
- soft assertions never enter independent review;
- hard non-positive primary decisions never enter independent review;
- a multi-assertion technical failure splits at most once and singleton failure
  never retries with a larger budget;
- `final.json` contains no new keys; and
- Composition scientific signatures are unchanged.

The full Alpha25 and independent-GT regression suite, `git diff --check`, and
production scans for model/provider, paper/title, and GT branches must pass.

## Five-Paper Acceptance Pilot

Use the same five frozen papers and a new verifier cache. Candidate extraction
must make zero API calls. The pilot proceeds only after the pre-verifier digest
matches its newly generated no-verifier control.

Required gates:

- 5/5 promotable; zero fatal or silent-empty papers;
- complete audit and issue links;
- Composition scientific equality for 5/5;
- zero singleton Responses label truncation;
- at most seven provider calls per paper on average;
- median verification time at most three minutes and no paper above six
  minutes;
- overall unique-loose precision at least two points above the matching
  no-verifier control and not below r58;
- overall recall loss at most 1.5 points versus the matching control;
- non-decreasing overall F1;
- non-decreasing Properties and core-tensile precision;
- core-tensile recall loss at most one point after source adjudication;
- no lost direct source-literal tensile fact; and
- source review of every formal delta before interpreting GT scores.

Report the same five papers against the matching no-verifier control, r58,
business GT, and the adjudicated GPT expert GT. GT disagreements must be
classified as system error, GT omission/duplication, compatible alias, or
uncertain attribution.

## Thirty-Paper Gate

Do not run 30 papers unless every five-paper gate passes. If the pilot fails,
retain all output, cache, metrics, and audit artifacts; report the blocker and
revise the design before another provider run.
