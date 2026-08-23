# Alpha25 Composition Source-Subject Boundary Gate

## Status

Approved under the user's precision-first continuation on 2026-08-23. This is
the next bounded convergence increment after the microanalysis table-envelope
owner recovery.

## Goal

Prevent a numeric chemistry statement about cited literature or a general
reference material constraint from being emitted as the measured or nominal
Composition of a current-paper Target.

The change must remain deterministic and GT-blind. It must not modify the
professionally reviewed prompt, Alpha25 schema, `final.json` shape, provider or
model configuration, OCR/VLM/line-chart behavior, or frozen model responses.
It must not add an LLM/API review step.

## Observed Failure Envelope

The 30-paper v195 output contains two source-proven false projections totaling
five component claims:

1. `Pyczak et al. [34] reported` a `10–30 vol.% Cr` range for Ni-based
   alloys. The extractor attached that range to the current sintered Alloy 625,
   although the same source sentence separately says `our sintered parts with
   21.2 wt.% of Cr`.
2. Four equilibrium solid-solubility limits for transition metals in Al were
   attached as the as-printed alloy's Composition. They are general reference
   constraints, not the paper's APT measurements.

All five claims are unmatched `value_conflict` rows with no GPT expert claim.
The current-sample `21.2 wt.% Cr` claim and the measured APT matrix values are
valid and must survive.

## Considered Approaches

1. **Value-local source-subject gate (selected).** Resolve the exact component,
   value, and unit to one prose proposition and isolate it only when that
   proposition explicitly belongs to an external reporting subject or a
   general material-reference constraint.
2. **Apply the existing broad citation gate to all Composition.** Rejected
   because citations commonly explain a valid current-sample result. A citation
   anywhere in the evidence is not proof that the chemistry belongs to another
   owner.
3. **Create a new Reference owner for every external chemistry statement.**
   Rejected because an author, generic alloy family, or equilibrium constraint
   does not uniquely identify an existing material/state owner. Inventing one
   would replace a false Target assignment with a falsely precise Reference
   assignment.

## Placement and Interface

Add one isolated Composition-only promotion pass after table and source owner
routing have exposed the best available coordinates, and before final
Composition precision filtering and materialization.

The pass receives existing inventory anchors, promoted candidate facts, and the
frozen paper source text. It returns accepted facts plus ordinary
`PromotionIssue` records. It never reads an evaluation artifact or creates an
owner.

## Eligibility Contract

A component can be isolated only when all requirements below hold:

1. The candidate is a `composition_observation` attached to a current-paper
   `Target` whose owner graph resolves as `Experimental`.
2. The candidate evidence is prose, not a Markdown/HTML table coordinate.
3. The component name, complete value, and compatible unit occur together in
   exactly one bounded source sentence or clause. Repeated or ambiguous source
   matches are a no-op.
4. One of these source-subject cases is proven:
   - **attributed literature chemistry:** the value-local proposition is under
     an explicit author/reporting or literature-reporting cue, and the
     component observation note or exact source clause independently identifies
     it as literature/external/reference chemistry; or
   - **general reference constraint:** the value-local proposition explicitly
     describes an equilibrium/maximum solid-solubility limit or a general
     composition range for a material class, without claiming a measurement,
     nominal formulation, or current-sample composition.
5. The value-local proposition does not name the candidate's current owner,
   state, or a current-study subject such as `our sintered parts`, `the present
   samples`, `we measured`, or an equivalent direct observation.
6. A citation, the phrase `in general`, or a literature-like note by itself is
   insufficient. The subject boundary and value binding must both be proven.
7. The decision is component-local. If an observation mixes removable external
   components and valid current components, retain the valid components in the
   same schema-shaped fact. If no components remain, quarantine the entire
   observation.

The gate is paper-, material-, alloy-, model-, provider-, and GT-independent.
The known papers and numeric values are test fixtures only, never runtime keys.

## Data and Audit Behavior

Every component removal emits
`promotion_external_composition_subject_quarantined` through the existing issue
pipeline and therefore into `quality_audit.json` and the existing
`issues.json`/`issues.md` outputs.

The audit contains:

- the complete original fact;
- the complete accepted fact after filtering, or `null` when fully removed;
- every removed component;
- the uniquely matched source sentence and value-local proposition;
- the subject cue and decision class;
- owner candidates and the current-source guard result; and
- the reason code and explicit statement that no owner was invented.

No public field is added to `final.json`. Retained values, units, evidence,
confidence, and identifiers are unchanged apart from removing the disproven
component rows.

## Safety and Failure Handling

Table evidence, a Reference owner, multiple matching source sentences, unit or
value ambiguity, mixed subject scope that cannot be split, missing source text,
and any unclear owner binding are safe no-ops.

The same source sentence may contain an external comparison and a current
result. The decision window follows the component's exact value; therefore the
external `10–30 vol.% Cr` can be isolated while the current `21.2 wt.% Cr`
survives. A current result followed by a citation remains valid when its
value-local clause has a current subject.

## Verification

Focused tests must cover:

- the attributed `10–30 vol.% Cr` range being isolated;
- the same sentence's current `21.2 wt.% Cr` surviving;
- four general equilibrium solid-solubility limits being isolated;
- measured APT matrix chemistry surviving;
- component-local filtering in a mixed observation;
- current chemistry with a sentence-end citation;
- `in general` without a reference constraint;
- table evidence, a Reference owner, ambiguous/repeated source matches, and
  missing source text;
- complete audit before/after data and deterministic ordering.

After focused tests, run the complete repository test suite excluding only the
known SciAlign integration test. Then rematerialize all 30 papers from the same
frozen task cache with zero provider calls and compare v194, v195, and the new
output under one unchanged evaluator.

Acceptance requires:

- 30/30 successful papers, no fatal outputs, no invalid cache entries, and zero
  API calls;
- unchanged prompt/schema/cache digests and unchanged `final.json` shape;
- the five source-proven false component claims absent with complete audit;
- current `21.2 wt.% Cr` and measured APT chemistry retained;
- global and Composition matched counts and recall unchanged;
- global and Composition precision/F1 non-decreasing;
- core-tensile matched counts, recall, precision, and F1 unchanged; and
- no unexplained semantic output changes outside the affected observations.

If any matched/recall gate declines, narrow or revert this increment rather than
weakening the source-subject proof requirements.
