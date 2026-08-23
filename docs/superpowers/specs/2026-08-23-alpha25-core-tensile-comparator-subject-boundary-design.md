# Alpha25 Core-Tensile Comparator Subject Boundary Gate

## Status

Approved under the user's precision-first continuation on 2026-08-23. This is
the next bounded convergence increment after the Composition source-subject
boundary gate.

## Goal

Prevent a numeric core-tensile value that the source assigns to a cited or
comparison material from being emitted as a Property of the current-paper
Target merely because the Target's generic alloy name is a substring of the
comparison subject.

The change must remain deterministic, source-grounded, and GT-blind. It must
not modify the professionally reviewed prompt, Alpha25 schema, `final.json`
shape, provider/model configuration, OCR/VLM/line-chart processing, or frozen
model responses. It must not add an LLM or API review step.

## Observed Failure Envelope

The 30-paper v196 output contains three source-proven false Target Properties:

1. `cast alloy 625 [11] had a UTS of 710 MPa with 48% elongation` produced both
   `710 MPa` UTS and `48%` elongation on the current Target `alloy 625`.
   The citation and the state-qualified subject `cast alloy 625` make both
   values literature-comparator results, not results for the binder-jet target.
2. `comparable to those of cast TNM alloys (700–800 MPa)` produced a
   `700–800 MPa` UTS range on the current Target `44–4 alloy rods`. The numeric
   range explicitly belongs to the comparator `cast TNM alloys`.

The existing external tensile gate correctly recognizes external prose, but
its `direct_current` rescue accepts any literal Target alias in the value
sentence. Thus the substring `alloy 625` inside the external subject
`cast alloy 625 [11]` incorrectly overrides citation scope. The comparator-only
TNM sentence is also too weak for the existing reporting-cue path.

These three records are GPT-expert `value_conflict` or
`expert_gt_missing_or_unsupported` residuals. No matched GPT-expert tensile
claim depends on them.

## Considered Approaches

1. **Value-local comparator-subject gate (selected).** Inspect only the bounded
   proposition containing the candidate value. A literal current owner rescues
   the claim only when it is the proposition's actual result subject, not a
   substring of a cited/state-qualified comparator.
2. **Blanket citation/comparison quarantine.** Rejected because current results
   and literature values frequently occur in the same sentence. A citation or
   `comparable` cue alone does not prove that every number is external.
3. **Create or infer a Reference owner.** Rejected because a generic comparator
   material does not uniquely identify an existing material/state coordinate.
   Inventing an owner would replace a false Target assignment with a falsely
   precise Reference assignment.

## Placement and Interface

Refine the existing prose-only core-tensile external-projection promotion pass.
The pass continues to receive inventory anchors and promoted facts and to
return accepted facts plus ordinary `PromotionIssue` records. It does not read
evaluation artifacts, mutate the owner graph, or create a Reference item.

Keep table/HTML evidence on the existing coordinate-aware tensile gates.
Reference-owned values already proven against one existing Reference anchor
continue through the established routing path.

## Eligibility Contract

A core-tensile candidate can be isolated only when all requirements below hold:

1. It is a numeric UTS, yield-strength, or elongation Property whose resolved
   owner is a current-paper `Target` with `Experimental` data nature.
2. Its evidence is prose, and the complete candidate value occurs in one
   bounded sentence or clause. Missing, repeated, or ambiguous value-local
   matches are a safe no-op.
3. The value-local proposition explicitly binds the value to an external
   subject through at least one of these deterministic forms:
   - a cited or previous-work material subject with a citation/reporting cue;
   - an explicitly state-qualified comparator material, such as `cast alloy`
     or `wrought alloy`, under external source scope; or
   - a comparison construction that grammatically owns the numeric value, such
     as `those of <comparator> (<value>)` or `<value> for <comparator>`.
4. The current owner alias is not considered a direct-current assertion when
   its only literal occurrence is contained inside that proven external
   subject. A generic alias substring cannot erase a source-level modifier,
   citation, author attribution, or comparator relation.
5. A direct current result survives when the value-local proposition separately
   names the current specimen/state as its result subject, even if another
   clause cites or compares literature. Current-source cues and comparator cues
   must therefore be evaluated against the same value, not the whole evidence
   block.
6. Existing uniquely proven Reference ownership remains valid. The gate never
   converts a Target fact into a new Reference fact and never invents a missing
   material or state.

The rule is paper-, title-, alloy-, model-, provider-, and GT-independent. The
known material names and values are regression fixtures only, never runtime
selectors.

## Data and Audit Behavior

Every removed candidate uses the existing
`promotion_external_current_tensile_projection_quarantined` issue path and is
therefore preserved in `quality_audit.json` and summarized in the existing
`issues.json`/`issues.md` artifacts.

The audit must contain:

- the complete removed fact;
- the resolved current owner candidates;
- the exact value-local sentence or proposition;
- the external/comparator subject span and the cue that proves its scope;
- the literal owner span that was rejected as an embedded substring;
- the deterministic reason code and confirmation that no owner was invented;
  and
- the original source evidence.

No public field is added to `final.json`. Isolation only removes the disproven
Property from the formal output.

## Safety and Failure Handling

Unclear grammar, multiple possible value owners, absent source text, table
evidence, non-core-tensile Properties, generic qualitative comparison without a
numeric comparator value, and a value-local direct current result are safe
no-ops.

The implementation must use bounded source patterns and existing owner aliases,
not a closed list of alloys, paper titles, providers, or fixture values. A
candidate-local parsing failure preserves the original fact.

## Verification

Focused tests must cover:

- both `710 MPa` UTS and `48%` elongation being isolated from the cited
  `cast alloy 625 [11]` proposition when attached to Target `alloy 625`;
- the `700–800 MPa` UTS range being isolated from the `cast TNM alloys`
  comparator proposition;
- complete audit payloads for both decision forms;
- the same alloy label as a genuine current result subject surviving;
- a current result followed by a citation surviving when the citation does not
  own the value;
- one sentence containing distinct current and comparator values filtering only
  the comparator-bound candidate;
- a uniquely proven existing Reference value surviving;
- table evidence, ambiguous value-local matches, non-tensile Properties, and
  missing source text remaining unchanged; and
- deterministic results under input-order permutations.

After focused tests, run a two-paper frozen-cache pilot and manually inspect all
semantic changes. Then rematerialize all 30 papers from the same frozen task
cache with zero provider calls and compare v196 with the new output using the
unchanged GPT-expert and business-GT evaluator.

Acceptance requires:

- 30/30 successful papers, no fatal outputs, no invalid cache entries, and zero
  API calls;
- unchanged prompt/schema/cache digests and unchanged `final.json` shape;
- exactly the three source-proven external comparator Properties absent, unless
  the full run exposes another claim satisfying the same strict contract;
- every removal preserved with complete audit;
- GPT-expert global and core-tensile matched counts and recall unchanged;
- GPT-expert global and core-tensile precision/F1 non-decreasing;
- business-GT matched counts and recall non-decreasing under both loose and
  strict modes;
- Composition metrics unchanged; and
- no unexplained semantic output changes outside affected Properties.

If any matched or recall gate declines, narrow or revert the rule instead of
weakening the source-subject proof requirements.

## Out of Scope

This increment does not address threshold shadowing such as a rounded
`>700 MPa` statement coexisting with an exact `773 MPa` result. It does not
change cross-chunk deduplication, prompts, retries, chunk size, concurrency,
provider settings, line-chart extraction, GT content, evaluator rules, or
public output schemas.
