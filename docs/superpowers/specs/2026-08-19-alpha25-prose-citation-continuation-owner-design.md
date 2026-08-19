# Alpha25 Prose Citation Continuation Owner Recovery

## Status

Approved by the user on 2026-08-19 as the next precision-first convergence
increment after v38.

## Goal

Correct numeric core-tensile facts that belong to a cited literature study but
were attached to a current-study Target because the fact sentence continues an
author-attributed prose passage without repeating the author's name.

The change must remain deterministic and GT-blind. It must not modify the
professionally reviewed prompt, schema, provider configuration, or cached model
responses, and it must not make OCR, VLM, LLM, or other API calls.

## Considered approaches

1. **Bounded citation-continuation chain (selected).** Resolve only an adjacent
   prose chain beginning with an explicit `Author et al. reported/showed/...`
   attribution and continuing through an explicitly anaphoric result sentence.
   This covers the known false-owner cluster while keeping ambiguity a no-op.
2. **Any sentence containing `reported`.** This has broader coverage but would
   misclassify ordinary current-paper reporting language and is rejected.
3. **Paragraph-wide nearest-author inheritance.** This can resolve longer
   discussions but becomes unsafe when a paragraph compares several studies and
   is rejected.

## Placement and interface

Add one isolated fact-level owner-recovery pass immediately after existing cited
table owner recovery and before identity-index construction. The pass receives
inventory anchors, candidate facts, and frozen source text. It returns updated
anchors, facts, and `MaterializeIssue` records.

Existing table recovery remains unchanged. The prose pass creates a Reference
anchor only for facts satisfying the contract below. All other axes and facts
are untouched.

## Eligibility contract

A fact can move only when all of these requirements hold:

1. It is a numeric absolute yield-strength, ultimate-tensile-strength, or
   elongation fact. Relative, qualitative, range, threshold, and non-tensile
   facts are excluded by the existing numeric-core predicate.
2. It is not already owned by a literature/reference anchor.
3. Its evidence is prose, occurs in exactly one source paragraph, and binds to
   exactly one source sentence. Markdown table evidence is excluded.
4. The fact sentence is part of one bounded adjacent chain:
   - the immediately preceding sentence explicitly names one author identity
     using `Surname et al.` and a reporting verb; or
   - the fact sentence explicitly says `by the same study`, and the immediately
     preceding continuation sentence resolves to one such author-attributed
     sentence directly before it.
5. A continuation sentence must contain an explicit reporting/anaphora cue such
   as `the reported ... values` or `by the same study`; adjacency alone is not
   enough.
6. The chain contains exactly one author identity. Multiple authors, competing
   antecedents, broken paragraph boundaries, or non-adjacent inference are safe
   no-ops.
7. Neither the fact sentence nor its resolved attribution chain marks the result
   as `this/current/present study/work`, `our study/work`, or equivalent current
   research.
8. The fact owner is a plausible material/sample identity and can be split from
   its Target without changing unrelated facts.

The same resolved author marker and same declared owner reuse one Reference
anchor. Different process/sample owners such as LPBF and EPBF remain separate
Reference items even when they come from the same cited study.

## Data and audit behavior

The moved fact keeps its value, unit, conditions, evidence, confidence, and all
other payload fields. Only `sample_id_raw` is routed to a citation-qualified
Reference anchor with `Role=Reference` and
`Data_Nature=Literature_Experimental`.

Every move emits `reference_tensile_prose_owner_recovered` in existing
`issues.json` and `issues.md`. The audit includes the complete original fact,
before/after owner, author marker, antecedent sentence, continuation sentence,
chain type, source paragraph, uniqueness decisions, and current-study guard.
No new audit file or public `final.json` field is introduced.

## Safety and failure handling

Parsing failure, repeated evidence, multiple matching paragraphs, multiple
author markers, missing continuation cues, or any role/identity uncertainty is
a no-op. The pass never guesses an author from the bibliography, a section
heading, an earlier paragraph, or an unrelated cached fact.

Identity reconciliation must preserve Target/Reference separation after the new
anchor is created. Existing current-study table rows and facts on the original
Target remain unchanged.

## Verification

Focused tests must cover:

- explicit author sentence followed by `The reported ... values`;
- a second adjacent sentence ending in `by the same study`;
- all facts in one eligible YS/UTS/elongation bundle sharing the same Reference
  owner;
- two possible author antecedents, non-adjacent attribution, and paragraph
  boundary protection;
- `this/current/present/our study/work` protection;
- an ordinary current-paper `reported value` without an author antecedent;
- table, non-tensile, relative, and already-Reference facts;
- Target facts remaining on the original item;
- complete audit payload and deterministic output.

First rematerialize and inspect the affected paper. Then rematerialize all 30
papers from all 405 frozen task responses with zero provider calls. Compare the
new result with v38 under the same corrected GPT expert and business GT
evaluators.

Acceptance requires 30/30 successful papers, 405/405 valid caches, unchanged
prompt/schema/cache digests, unchanged Composition metrics, no decline in global
or core-tensile recall, and non-decreasing global/core precision and F1. A
scientifically correct Reference migration may expose one previous loose
owner-agnostic accidental match; if that occurs, report it separately and judge
the change by strict owner correctness rather than hiding the attribution error.
