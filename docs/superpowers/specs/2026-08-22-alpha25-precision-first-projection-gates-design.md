# Alpha25 precision-first projection gates

## Goal

Improve GLM Alpha25 precision without changing the business-reviewed extraction
prompt, provider behavior, or the public `final.json` schema. The change is
source-only: it may quarantine a candidate that cannot be proven to be an
independent scientific fact, but it must preserve the complete candidate,
evidence, owner, and reason in the existing promotion/materialization audit.

## Design

1. Processing result-vs-stage gate

   A `process_stage` is promoted only when its evidence contains a direct
   process event, a source-literal parameter/table assertion, or an explicit
   treatment reference. Sentences that merely explain a material result (for
   example, “high build temperature ... results in ...”) or describe a
   hypothetical step (“if a HIP step is added”) are isolated. Generic values
   such as `high`, `low`, `different`, or `not reported` cannot rescue such a
   result projection.

2. Processing metadata subfield gate

   Equipment/environment/technique labels copied as independent parameters are
   isolated when they are prose-only metadata without a process coordinate.
   Table-bound rows remain eligible for the existing coordinate-aware gate, and
   the full source row remains in audit. Numeric process parameters such as
   power, speed, layer thickness, temperature, and cooling rate are unaffected.

3. Structure generalization gate

   A qualitative entity-only Structure claim is isolated when its evidence is a
   generic literature/generalization statement (`typically`, `usually`,
   `often`, `studies have shown`, `may`, `suggesting`, etc.) and has no numeric,
   explicit-absence, or local measurement payload. Direct source assertions
   (`contained`, `was observed`, `showed`, `formed`) and table/numeric/negative
   records remain eligible.

4. Structure source-state coordinate gate

   A Structure candidate that lost `material_state` during chunk extraction is
   routed to one existing state owner when its own prose evidence names that
   state (including conservative numeric state coordinates).  If the evidence
   names multiple sibling states without explicit collective/one-to-one grammar,
   the candidate is quarantined rather than attached to the generic base item.
   Table evidence remains on the table-coordinate path; state-qualified sample
   labels already provide their own owner coordinate and are not rewritten.

5. Qualitative process-parameter gate

   Comparative words such as `higher`, `lower`, `increased`, and `decreased`
   are not source-literal process parameters.  A process stage whose only
   parameter is one of these generic qualitative values is therefore not
   rescued from a result/cause sentence.  Numeric process values and explicit
   table coordinates are unaffected.

6. Zero-duration heat-treatment gate

   A heat-treatment candidate whose only reported parameter is a literal zero
   duration is treated as a table encoding of “not applied,” not as an executed
   material-processing stage. The rule does not fire when the evidence directly
   states that heating, aging, annealing, or another treatment occurred, or when
   any other reported nonzero parameter is present. The removed stage and its
   zero-duration parameter remain complete in the audit ledger.

## Ordering and audit

The gates run before owner routing and cross-chunk fan-out deduplication. They
return existing `PromotionIssue` records with stable short codes; no GT data is
consulted. A fact is removed from the accepted promotion stream only after its
original serialized payload and source evidence are attached to the issue.

## Verification

Add positive and negative unit tests for each gate, run the focused Alpha25
promotion/quality tests, then replay all 30 cached papers without OCR/API calls.
Keep the change only if overall unique-loose precision and core-tensile
precision improve without a material regression in the existing direct-event
regressions.
