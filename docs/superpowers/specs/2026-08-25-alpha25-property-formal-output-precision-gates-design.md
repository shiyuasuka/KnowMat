# Alpha25 Property Formal-Output Precision Gates

## Status

Approved by the user on 2026-08-25 as the next precision-first iteration of
the hierarchical GLM-5.2/5.3 verification design. This focused design does not
change the professionally reviewed extraction prompt or schema.

## Goal

Prevent source locators, independent-variable trend prose, and syntactically
incomplete owners from becoming formal `Properties`, while preserving every
complete rejected record in `quality_audit.json` and a compact issue code in
`issues.json` and `issues.md`.

## Alternatives Considered

1. Ask the verifier to decide every residual Property. This adds latency and
   did not produce a confirmed quarantine in the five-paper real-API pilot.
2. Remove every Property absent from GPT expert GT. This would incorrectly
   discard source-supported facts that the expert inventory did not include.
3. Apply narrow deterministic source-only gates before materialization. This
   is selected because each rejection can be proved from the candidate's own
   value, owner, and evidence without GT or paper-specific knowledge.

## Accepted Gates

### Source-locator placeholder

A Property whose `value_raw` says only that a value was digitized, replotted,
or taken from a figure/table, but contains no actual measured response, is not
a Property value. Examples include `digitized from Fig.10`. It is quarantined
with reason `source_locator_placeholder`.

This gate does not reject an actual numeric value merely because its
`data_source` is a chart or figure.

### Independent-variable trend projected as a scalar

A prose value such as `decreases as the t/d value decreases from 34.5 to 4.5`
does not report fatigue life in cycles: its numeric tokens belong to the
independent variable. A directional response joined to an `as`, `with`, or
`when` independent-variable change is quarantined with reason
`independent_variable_trend`.

Quantified results such as `decreased by 40%`, explicit inequalities such as
`<10^4 cycles`, and actual scalar/range/uncertainty values remain eligible.

### Syntactically incomplete owner

An owner label ending in a dangling separator such as `PBF-` is not allowed to
create an independent formal Property owner. The candidate is quarantined
with issue code `property_incomplete_owner_quarantined`. A complete literal
owner such as `PBF-EB`, `Al-4.5Cu`, or `A-1` remains eligible.

This rule never guesses the missing suffix or reassigns the fact to another
owner. A separately source-proven complete candidate remains available to the
existing deterministic merge and owner logic.

## Data Flow and Audit

The gates run in the existing `claim_quality.filter_axis_facts` stage before
materialization. Accepted facts continue unchanged. Rejected facts do not
enter formal `Properties`; their complete fact payload, evidence, owner, rule,
and reason are emitted as `ClaimQualityIssue` records and flow through the
existing quality-audit and compact-issue packaging. The public structure of
`final.json` is unchanged.

Composition is not inspected or removed by these gates.

## Safety Boundaries

- No GT, paper ID/title, expected count/value, provider, or model name may be
  read by production code.
- No prompt or extraction schema changes.
- No numerical repair, owner completion, or scientific inference.
- A real numeric chart point remains eligible when its value is explicit.
- A source-supported Property absent from either GT remains eligible unless
  it independently violates one of the three gates above.

## Tests and Acceptance

Unit tests must prove rejection of figure-only placeholders, independent-
variable trends, and dangling owners, plus preservation of numeric chart
values, quantified relative changes, inequalities, complete hyphenated owners,
and source-supported GT omissions.

The five frozen pilot papers are then rematerialized cache-only. Acceptance
requires:

- the known placeholder/trend/truncated-owner Properties are absent from
  formal output and fully present in the audit;
- no Composition change;
- no loss of matched core-tensile claims other than an already unsupported
  incomplete-owner projection;
- improved unique-loose Property precision and F1 against GPT expert GT; and
- unchanged `final.json` top-level contract.

