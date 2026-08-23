# Independent GT canonical value/unit pairing design

## Context

The independent-GT evaluator flattens business-GT and production `final.json`
documents into atomic claims before comparing them with the sealed GPT expert
ledger. A flattened numeric claim must use one coherent representation layer.

The current scalar path usually compares the canonical pair correctly. For
example, a production parameter containing source value `~850 °C` and canonical
value `1123.15 K` is compared as `1123.15 K`. However, its flattened `raw`
display remains `~850` while its claim unit is `K`. More importantly, canonical
range payloads such as `50–70 µm` represented as `[0.05, 0.07] mm` are not read
as a canonical pair. The evaluator can therefore compare raw range endpoints
against a canonical unit. Rounding tolerance can make the same mistake for
top-level values.

This is an evaluator correctness issue. It does not authorize changing the
expert ledger, business GT, extraction prompts, schema, provider, production
materialization, or any `final.json` artifact.

## Objective

Make every numeric claim internally representation-consistent so that the
published comparison measures real extraction quality. The correction must:

1. use canonical numeric payloads only together with their canonical unit;
2. otherwise use the complete raw numeric payload together with its raw unit;
3. support scalar, uncertainty, range, and inequality values without crossing
   representation layers;
4. retain the source literal and complete source record for audit;
5. apply identically to production `final_v5` and business-GT v11 documents;
6. leave expert claims and all scientific matching rules unchanged.

## Considered approaches

### A. Canonical-first atomic representation (selected)

Select a complete canonical payload and canonical unit when available. If the
canonical payload is absent or incomplete, select the complete raw payload and
raw unit. Keep source literals in the original `raw` record rather than mixing
them into the selected claim representation.

This matches the evaluator's existing unit-normalized design, fixes canonical
ranges, and avoids repeated ambiguity at match time.

### B. Raw-only comparison

Always compare source values and source units and let the matcher convert them.
This is simpler conceptually, but it discards already validated canonical
normalization, increases dependence on the evaluator's unit parser, and makes
nontrivial normalized payloads harder to compare.

### C. Display-only correction

Change CSV/report rendering while leaving flattening unchanged. This removes
misleading labels but leaves the canonical-range and rounding defects in the
actual comparison path.

Approach A is selected because it fixes both comparison semantics and audit
clarity while preserving the existing canonical evaluation contract.

## Representation selection

### Canonical layer

A canonical representation is eligible only when both its numeric payload and
canonical unit are usable.

- Scalar: a finite canonical scalar is present. Existing v11 `value_num` is
  treated as the normalized scalar when it accompanies `canonical_unit`, as in
  normalized property `Value` objects.
- Uncertainty: the center and standard deviation must be expressed in the same
  selected layer. A raw standard deviation must not be attached to a converted
  center unless the schema already stores both in canonical units.
- Range: a canonical two-element numeric sequence supplies canonical `min` and
  `max`. A scalar canonical payload cannot stand in for a range.
- Inequality: a canonical bound must be present explicitly or be losslessly
  derivable from a canonical numeric payload whose declared kind is
  `inequality`.

Non-finite values, booleans, malformed sequences, or one-sided canonical
payloads are ineligible.

### Raw layer

When the canonical layer is ineligible, all numeric fields come from the raw
layer:

- `value_num`/raw numeric scalar where it is not already the documented
  normalized property scalar;
- `value_min` and `value_max` for ranges;
- `bound_value` plus operator/qualifier for inequalities;
- `value_stddev` with its raw center;
- a conservative full-expression parser for an unambiguous source literal
  when structured numeric fields are absent.

The unit is `unit_raw`/`Unit_Raw`. A mere `canonical_unit` spelling alias with
no converted numeric payload must not force the raw value into a different
scale. Unit spelling normalization remains the matcher's responsibility.

### Source literal and audit

The flattened claim's selected numeric presentation must agree with its
selected unit. The original source literal remains available under the claim's
complete `raw` source record, including `value_raw`, `unit_raw`, normalization
rule, evidence, and canonical fields. No production audit file or output schema
changes are required.

## Rounding and uncertainty

Displayed rounding resolution is determined from the source literal and its
source unit. The tolerance is then converted once into the comparison unit.
This applies to both nested property `Value` objects and top-level processing,
composition, and structure records.

The evaluator must not:

- interpret `60` from `60 h` as a one-second-resolution canonical value;
- combine a converted scalar with an unconverted standard deviation;
- convert a tolerance twice;
- widen existing scientific equality thresholds.

## Data flow

1. `flatten_v11` passes a v11 atomic record to one representation selector.
2. The selector inspects nested `Value` and top-level fields without mixing
   them.
3. It returns the selected structured value, selected unit, and enough source
   metadata for rounding/audit.
4. Existing semantic, owner, condition, provenance, unit-conversion, matching,
   deduplication, and metric code consumes the coherent claim unchanged.
5. The report and adjudication CSV render the selected representation while
   the complete source record remains available for traceability.

## Error handling

- An incomplete or malformed canonical payload falls back atomically to raw.
- An incomplete raw numeric payload remains categorical/unknown under existing
  conservative parsing rules; the evaluator must not invent endpoints or
  bounds.
- Conflicting nested and top-level fields prefer the nested v11 `Value` object
  as the authoritative local record, consistent with current behavior.
- The selector never drops a production or business claim merely because its
  numeric normalization is incomplete.

## Tests

Focused unit tests must cover:

1. `~850 °C` / `1123.15 K` scalar selection;
2. `14 mA` / `0.014 A` scalar selection;
3. `60 h` / `216000 s` scalar selection and source-unit rounding tolerance;
4. `50–70 µm` / `[0.05, 0.07] mm` canonical range selection;
5. raw range fallback when no canonical numeric range exists;
6. normalized property `0.39 ± 0.02 GPa` / `390 ± 20 MPa` consistency;
7. raw scalar, range, inequality, categorical, and unknown fallback;
8. identical logic for `final_v5` and `business_gt` sources;
9. no regression in Composition, Processing, Structure, Characterization, or
   Properties flattening and matching.

After unit tests pass, rerun the evaluator against the existing immutable v199
30-paper output. Compare old and corrected reports by axis and failure reason.
Any metric change must be explained by an affected claim pair; no extraction
API call or rematerialization is part of this evaluator-only correction.

## Acceptance criteria

- No flattened claim contains a numeric payload from one scale and the unit of
  another scale.
- All focused and full evaluator tests pass.
- The corrected v199 comparison completes for all 30 papers.
- Production `final.json`, `quality_audit.json`, prompts, schema, provider, and
  expert/business GT source artifacts remain byte-unchanged.
- The report states separately which changes are evaluator corrections and
  which remaining gaps are genuine GLM precision/recall/owner/condition or
  tensile residuals.
- The next extraction optimization is chosen only from the corrected residual
  evidence and must retain the established no-recall-regression gate.
