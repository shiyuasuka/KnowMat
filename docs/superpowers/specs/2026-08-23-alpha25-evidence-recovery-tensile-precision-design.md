# Alpha25 evidence recovery and tensile precision convergence design

## Goal

Move the GLM Alpha25 pipeline closer to the adjudicated GPT expert GT with
precision as the first priority, while recovering facts that the upstream
evidence gate can prove deterministically. The change must not modify the
business-reviewed prompt, Alpha25 schema, provider/model behavior, line-chart
capability, or the public `final.json` shape.

The frozen v188e reference is:

- source/task cache: `data/output-alpha25-prompt-v2-rulesfix-final-20260818`
- output: `/tmp/knowmat-v188e-reference-binary-final30-20260823`
- expert audit: `/tmp/v188e-reference-binary-work/adjudicated/paper_*.json`
- unique loose P/R/F1: `0.423137 / 0.176204 / 0.248802`
- unique strict P/R/F1: `0.205745 / 0.085677 / 0.120977`
- core-tensile loose P/R/F1: `0.707865 / 0.295775 / 0.417219`

This iteration is a deterministic post-extraction convergence layer. It does
not add another LLM pass and does not use either expert GT to decide individual
production facts.

## Chosen approach

Use four independent, source-bounded components:

1. Recover a rejected candidate only when its retained table cells form a
   unique ordered projection of one original Markdown/HTML table row.
2. Require every core-tensile numeric value to appear in the candidate's own
   evidence and suppress a rounded/qualitative duplicate when an exact value
   for the same semantic coordinate is available.
3. Route directly cited and immediately continued literature results to a
   Reference owner using literal author/citation cues.
4. Bind a shared tensile-test protocol only to uniquely proven table owners
   when the source explicitly makes that protocol global to all tensile tests
   or specimens.

This is preferred over precision-only deletion because v188e has substantial
deterministically recoverable recall, including 20 table tensile facts in
`paper_003`. It is preferred over a second LLM judge because the latter is
slower, provider-dependent, and cannot give a reproducible evidence contract.

## Component 1: unique ordered table-row projection

The evidence layer exposes a validator that receives a rejected candidate's
evidence cells and the original Markdown/HTML source block. It normalizes only
representation noise already accepted elsewhere in the evidence contract,
such as whitespace and table delimiters. It does not use fuzzy string
similarity, material aliases, GT records, or row position.

A candidate is recoverable only when all of the following hold:

- at least three non-empty candidate cells remain;
- the cells occur in the same order within one original data row;
- the projection matches exactly one distinct normalized original row;
- owner and value coordinates required by the candidate are present in that
  matched row;
- the matched row is not a header, separator, or prose line.

Repeated copies of the exact same normalized source row count as one distinct
row. Two different rows that produce the same projection are ambiguous and
must not be recovered. Extra original columns are allowed; this is the case
that repairs cropped evidence from wide tables such as the nine-column table
in `paper_003`.

The validator returns a structured decision containing the matched original
row, projected coordinates, candidate payload, and reason. Materialization
may consume an accepted decision; it may not independently relax the match.

## Component 2: source-local tensile quality gates

For core tensile properties, a numeric candidate is formally promotable only
when its value is grounded in its own `source_evidence`. The check applies even
when the evidence contains no numbers at all. This closes the current branch
where `value_numbers` is populated but `evidence_numbers` is empty, which lets
unsupported values such as the `paper_023` BJP `650 MPa` and `45 %` pass.

The gate uses the existing numeric normalization and tolerance contract so
scientific notation, decimal punctuation, uncertainty notation, and canonical
unit conversion continue to work. A number found elsewhere in the paper,
another candidate, or a neighboring chunk cannot satisfy the local evidence
requirement.

An approximate/rounded tensile statement is quarantined when an exact fact
exists with the same owner, state, property meaning, test coordinate, and
source lineage. Examples include `around 2%` shadowed by `2 ± 1%` and `>1 GPa`
shadowed by `1036 ± 35 MPa`. Different specimens, orientations, temperatures,
strain rates, or genuinely distinct source rows are never merged. When
lineage or coordinate equality is uncertain, both records remain and the
existing review path handles the ambiguity.

## Component 3: direct literature Reference routing

Extend the existing prose citation owner resolver without broadening it into
general coreference resolution. A tensile fact may move from a current Target
owner to a Reference owner only through one of these source-local patterns:

- the fact sentence itself contains one unique `Author et al.` attribution
  plus a reporting verb;
- the immediately following sentence begins with an unambiguous continuation
  such as `They showed` or `They reported`, contains no new author, and stays
  in the same paragraph/source block;
- the fact sentence contains a literal material owner plus a numeric citation,
  such as `cast alloy 625 [11]`.

The route is disabled when multiple author groups compete, a current-study cue
is present, paragraph/source-block boundaries are crossed, the antecedent is
not unique, or the matching Reference anchor does not already exist. It never
invents a bibliographic identity. A successful migration also removes copied
current-experiment state/condition fields that are not literal in the cited
source and records the before/after owner payload.

## Component 4: table-owner tensile protocol binding

The existing property-context detector remains responsible for discovering
test protocols. Materialization may override `shared_scope_risk` only for a
core-tensile fact whose owner/value row has already passed the unique ordered
projection contract and for a protocol that is uniquely compatible with that
property.

The source must explicitly scope the protocol to all tensile tests, all tested
specimens/samples, or an equivalent universal set. A singular local test,
multiple competing protocols, or a merely nearby Methods sentence is not
enough. The binding may include strain rate, machine, measurement method, and
repeat count when they belong to the same protocol block.

Reference facts never inherit a current paper's shared protocol. Prose facts
without a uniquely proven table owner continue through the existing
conservative shared-scope path.

## Data flow and failure behavior

Offline and live materialization use the same decisions:

1. Evidence/contract validation classifies each candidate as accepted,
   recoverable-by-unique-projection, ambiguous, or rejected.
2. Accepted and uniquely recovered candidates enter existing materialization.
3. Reference routing resolves source-local cited owners before current-paper
   protocol binding.
4. Core-tensile numeric grounding and exact-over-approximate dominance run
   before final property serialization.
5. Existing reconciliation and packaging produce an unchanged `final.json`.

Ambiguity, malformed source rows, missing source blocks, multiple protocols,
or incomplete provenance always fail closed: the candidate is isolated rather
than guessed. One bad candidate must not abort the paper. Fatal parsing or
contract errors retain the existing fatal behavior and diagnostics.

`scripts/rematerialize_alpha25_tasks.py` must serialize evidence-layer
rejections and recoveries into the same paper-level audit path as later gates;
it must not report them only as aggregate counters.

## Audit contract

Every recovery, migration, shadow, and quarantine preserves the complete
original candidate, source evidence, decision inputs, reason, and any
before/after payload in the existing `quality_audit.json`. The existing
`issues.json` and `issues.md` receive concise issue summaries. No second audit
truth is created.

Stable issue codes:

- `evidence_unique_ordered_projection_recovered`
- `evidence_projection_ambiguous_quarantined`
- `core_tensile_value_not_in_local_evidence`
- `core_tensile_approximate_shadow_quarantined`
- `reference_tensile_direct_author_owner_recovered`
- `reference_tensile_pronoun_continuation_owner_recovered`
- `reference_tensile_literal_citation_owner_recovered`
- `property_test_context_table_owner_recovered`

Successful recovery codes describe provenance and are not review failures by
themselves. Quarantine codes set or retain the paper review marker according
to the current issues policy.

## Compatibility and invariants

- Business-reviewed prompts remain byte-for-byte unchanged.
- Alpha25 schema and public `final.json` remain unchanged.
- No code branches on `glm`, `gpt`, provider name, or model version.
- No new API call or second-pass model review is introduced.
- Line-chart extraction stays enabled and follows its existing bounded-context
  behavior.
- Composition must not regress against v188e in matched count, precision,
  recall, or F1.
- Correct current-paper tensile facts such as the two source-supported
  `paper_015` UTS records must remain.
- GT files are evaluation inputs only and are never read by production routing.

## Testing

Add focused unit tests for:

- wide-table cropped rows that uniquely project and recover;
- fewer than three cells, out-of-order cells, duplicate ambiguous rows,
  headers, and near-but-not-exact rows that remain quarantined;
- evidence containing no number, a conflicting number, scientific notation,
  uncertainty notation, and valid unit-normalized tensile values;
- exact-over-approximate dominance with positive same-coordinate cases and
  negative cross-owner/state/orientation/temperature cases;
- same-sentence author attribution, immediate `They showed` continuation,
  literal owner plus citation, competing authors, paragraph boundaries, and
  current-study cues;
- globally scoped unique table protocols, competing/local protocols, prose
  owners, and Reference facts that must not inherit the protocol;
- complete offline audit serialization for evidence acceptance, recovery, and
  rejection decisions.

Run the focused evidence, claim-quality, promotion, property-context, and
materialization suites, followed by all Alpha25 tests and the full repository
suite. The known external fixture failure for
`/ssd1/jinzongxiao/paddle_work/sci-align/dataset_test/embedding_index.json` is
reported separately and is not attributed to this change.

## Thirty-paper acceptance gate

Replay all 30 papers from the frozen v188e source/task cache. Require 30/30
papers, 405/405 task-cache hits, and zero API calls. Compare both v188e and the
candidate output to the same adjudicated GPT expert GT and report business-GT
metrics separately when available.

Keep the implementation only if all of these hold:

- unique loose precision and F1 both improve over v188e;
- unique strict precision and F1 do not regress;
- core-tensile loose precision remains at least v188e's `0.707865`, recall is
  greater than `0.295775`, and F1 improves over `0.417219`;
- core-tensile strict precision and F1 do not regress, and strict matched count
  increases when a uniquely global table protocol is recovered;
- wrong-owner, unsupported-value, and condition-conflict residuals each do not
  increase, with wrong-owner and unsupported-value residuals expected to fall;
- Composition metrics do not regress;
- every changed fact is accounted for by one of the audit decisions above.

If a gate fails, use per-paper audit deltas to disable or narrow the responsible
rule. Do not compensate by changing prompts, reading GT in production, or
blindly deleting unrelated facts.
