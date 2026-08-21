# Alpha25 Respectively/Condition Coordinate Binding

## Goal

Reduce high-precision errors caused by a candidate value losing the state or
owner coordinate that appeared in its source assertion. The change is
source-only and deterministic: the reviewed extraction prompt, provider
configuration, Composition path, and public `final.json` schema remain
unchanged.

## Design

1. A `condition_label_raw` value is promoted to `test_condition_raw` only when
   the label is literally present in the candidate's own evidence and contains
   a discriminator such as delay, temperature, orientation, state, location,
   or a time/temperature/unit marker. Method-only or neighboring-chunk labels
   remain absent. The promotion is recorded as
   `promotion_condition_label_bound`.
2. A source-literal condition may route a fact to one already-existing target
   state owner when that state is uniquely matched. Duplicate aliases or ties
   are left unchanged; no owner is invented and no confidence/order tie-break
   is used. The audit code is
   `promotion_condition_owner_reassigned`.
3. When one exact `respectively` assertion emits multiple values for the same
   metric but no unique condition or owner coordinate survives, all ambiguous
   projections are quarantined as
   `promotion_respectively_mapping_ambiguous_quarantined`. Different metric
   names, explicit source-grounded conditions, Markdown coordinates, and the
   existing prose owner/value gate are unaffected.

Every removed or modified candidate continues through the existing
`issues.json`/`issues.md` audit path with the complete before/after payload and
source evidence. No GT, model name, or provider branch is consulted.

## Verification

- Focused and Alpha25/V11 regression suite: 663 passed.
- Five cached-paper pilot: 30/30-compatible output shape on the selected
  papers; only the known paper-029 same-metric, missing-coordinate pair was
  quarantined (two records). The other four papers had no new quarantines or
  materialization failures.
- `final.json` item and field shape remains unchanged; the isolated pair is
  retained in the validation issues audit.
