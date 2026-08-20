# Alpha25 Source-Only Tensile Protocol Completion

## Goal

Improve GLM Alpha25 owner/condition attribution and strict core-tensile quality
without changing the professionally reviewed prompt, extraction schema, cached
model responses, or public `final.json` format. The increment repairs a narrow
transport loss: a property claim already exists, but its compatible tensile
method is stranded elsewhere in the same OCR Markdown because the method wording
or sentence boundary is not recognized.

This is the first stage of the approved `A -> validate -> B` sequence. Complete
tensile-bundle precision dominance is a separate follow-up design and may begin
only if this stage passes every non-regression gate.

The GPT expert ledger and business GT are evaluation instruments only. Runtime
decisions must remain paper-, title-, GT-, provider-, model-, and corpus-independent.

## Confirmed failure modes

Read-only diagnostics on the frozen 30-paper corpus found two general parser
failures:

1. A source method written as `uniaxial tensile loading experiment` contains a
   real tensile event, equipment, DIC, specimen dimensions, and loading rate,
   but the current grammar recognizes only narrower `tensile test/experiment`
   forms. No protocol candidate is produced.
2. A tensile event sentence can be followed by a sentence beginning `Each
   tensile specimen was tested ...` that carries ASTM and strain-rate details.
   The current continuation loop treats the second tensile noun as a competing
   protocol anchor and stops before attaching its details. A weaker results
   paragraph can then win instead of the formal methods paragraph.

A third case defines a mandatory protection: one paper-level protocol may list
both room-temperature and elevated-temperature tests. A property-specific RT or
600 C condition must not be overwritten by, or interpreted as equal to, the
entire multi-temperature matrix.

## Considered approaches

1. **Source-only protocol completion (selected).** Expand only explicit tensile
   event grammar and recover adjacent procedure continuations inside one Markdown
   block. Bind the resulting literal protocol only through existing owner and
   condition compatibility gates. This directly addresses verified transport
   loss with no new fact generation.
2. **Complete tensile-bundle precision dominance.** Merge rounded or generic
   YS/UTS/elongation projections into one complete uncertainty-bearing bundle.
   This can improve loose precision but has greater owner-lineage risk and is
   deferred until the selected stage passes full regression testing.
3. **Global Structure/Characterization isolation.** Remove unsupported or
   duplicated non-tensile claims to improve micro precision. This has the largest
   possible precision gain but also the largest expert-GT omission risk, so it is
   not part of this increment.

## Architecture and placement

Keep the existing materialization flow and modify only the isolated
`PropertyContextIndex` subsystem:

1. OCR Markdown is split into source blocks and sentences.
2. The tensile event recognizer identifies explicit test/loading events.
3. A bounded continuation assembler attaches at most the next two procedural
   sentences from the same block.
4. Candidate construction extracts source-literal details and discriminators.
5. Existing reference, owner, temperature, rate, standard, and orientation gates
   select or reject a candidate for each property.
6. Accepted completions are materialized through the current condition path and
   audited in the existing `issues.json/.md` artifacts.

No new public document field, audit file, prompt artifact, cache mutation, or
provider call is introduced.

## Tensile event grammar

The recognizer may add syntactic variants only when all of these are explicit in
the source text:

- a monotonic tensile/tension noun phrase;
- a test, testing, experiment, loading, or load event; and
- procedural wording rather than a measured-result or literature-comparison
  statement.

Examples that become eligible include `uniaxial tensile loading experiment` and
`tensile loading tests`. Phrases such as `tensile strength increased`, `during
tensile deformation`, a figure caption, an abstract result, fatigue/creep,
stress relaxation, or a bibliographic title remain ineligible.

This is model-agnostic lexical support, not a paper-title or material-name rule.

## Bounded continuation assembly

A following sentence may join an established tensile event only when it:

- remains in the same Markdown block;
- contains a procedural action;
- contributes at least one protocol detail such as specimen, standard, rate,
  equipment, strain measurement, orientation, environment, or replicates;
- does not introduce another mechanical-test family; and
- is demonstrably a continuation, even if it repeats `tensile specimen` or
  `tensile test`.

Repeating a tensile noun is no longer an unconditional stop. It starts a distinct
protocol only when it introduces an incompatible explicit temperature, rate,
standard, or orientation, or when both sentences independently describe complete
test events. The join remains bounded to two following sentences and never
crosses a heading, paragraph, table, figure, or source block.

Candidate scoring must prefer the formal source block with richer explicit
procedure detail over a results paragraph that merely describes replicate count
or an exceptional specimen-handling note. Confidence never resolves a scientific
ambiguity.

## Property-specific compatibility

Recovery remains all-or-nothing for each property.

- Reference-owned and citation-local claims never inherit current-paper methods.
- A candidate naming another material owner is rejected.
- Explicit temperature, strain/loading rate, standard, or orientation conflicts
  are rejected.
- Multiple incompatible candidates without a unique property-local discriminator
  remain unchanged and receive the existing ambiguity audit.
- Existing explicit conditions are never replaced. Completion may only add
  source-reported dimensions that are absent and compatible.
- A protocol that enumerates several test temperatures is compatible with an
  already temperature-qualified property only for dimensions shared by that test
  matrix. It must preserve the property's one explicit temperature and must not
  turn the other matrix temperatures into property-specific conditions.
- An unqualified property does not receive a temperature from a multi-temperature
  protocol unless its local evidence uniquely selects one temperature.

The implementation may project source-literal clauses or fields from a candidate
to avoid introducing a conflicting matrix temperature, but it may not paraphrase,
invent, default, or infer a method value. Every appended detail must be traceable
to the selected source block in the audit payload.

## Audit and output behavior

Successful empty-condition recovery continues to emit
`property_test_context_recovered`; safe completion of a partial condition
continues to emit `property_test_context_augmented`. Existing ambiguity and
reference-protection issue codes remain authoritative.

Each success audit records the complete selected source candidate, source line
range and heading, property-local discriminators, accepted shared details, and
rejected/conflicting candidates. The public `final.json` schema and item layout
remain byte-compatible with the current contract. No `quality_audit.json` is
created.

## Failure handling

Parsing failure, incomplete method prose, multiple viable protocols, owner
ambiguity, discriminator conflict, or inability to make a source-literal
property-specific projection is a safe no-op. Candidate-local exceptions preserve
the original property. Document-level error handling remains unchanged.

## Verification

Focused tests cover:

- `uniaxial tensile loading experiment` recognition;
- event sentence plus adjacent ASTM/rate procedure sentence;
- repeated tensile nouns that are continuations versus distinct protocols;
- results, figure, abstract, references, fatigue, creep, and relaxation negatives;
- owner-specific and reference protections;
- single- and multi-temperature compatibility;
- RT and 600 C properties retaining their own temperature while sharing only
  compatible method details;
- missing local temperature plus multi-temperature protocol remaining unmodified;
- deterministic candidate ordering, output, and complete audit payloads;
- Composition and non-tensile non-interference.

Run focused unit tests first, then frozen-cache pilots for the diagnosed papers,
and finally rematerialize all 30 papers using all 405 cached task responses. Run
the existing GPT-expert and business-GT comparison against v45.

The official v45 GPT-expert unique-claim baseline is:

- global loose: 1,578 / 6,272 / 3,093 matched/system/expert, F1 0.336999;
- global strict: 786 / 6,272 / 3,093, F1 0.167859;
- core tensile loose: 166 / 211 / 213, F1 0.783019; and
- core tensile strict: 117 / 211 / 213, F1 0.551887.

## Acceptance gates

The increment is accepted only when all of the following hold:

- 30/30 papers and 405/405 cached task responses materialize successfully;
- zero OCR, VLM, LLM, or other provider calls;
- prompt, skill, schema, and frozen-cache digests are unchanged;
- `final.json` format is unchanged;
- Composition loose/strict matched, precision, recall, and F1 do not decline;
- global and core-tensile loose/strict matched and recall do not decline;
- global and core-tensile precision and F1 improve or remain unchanged;
- strict core-tensile owner/condition matches increase above 117;
- every changed condition is source-supported and fully audited in existing
  artifacts;
- repeat materialization produces byte-identical `final.json` files; and
- full frozen-cache runtime is no more than 110% of the measured v45 297.95-second
  run on the same host and workload, with no new per-property full-document scan.

Any gate failure narrows or reverts the rule instead of weakening its scientific
evidence requirements. Candidate counts and diagnosed paper IDs are validation
targets only and never enter production selection.

## Follow-up boundary

After this increment passes, remeasure the residual core-tensile queue. Only then
write and approve a separate design for complete-bundle precision dominance.
That follow-up must retain the established protections for explicit distinct
owners, orientation siblings, elongation subtypes, thresholds, ranges, and
relative comparisons.
