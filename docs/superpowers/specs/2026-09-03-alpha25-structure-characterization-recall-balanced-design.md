# Alpha25 Structure/Characterization Recall-Balanced Precision Design

## Goal

Move the GLM-5.3 Alpha25 output toward the adjudicated GPT-5.6-sol expert ledger without trading away source precision. The current v203 run preserves good property precision but quarantines too many source-grounded Structure and Characterization claims and duplicates claims across overlapping chunks.

## Constraints and invariants

- `final.json` remains schema-compatible with the existing materializer.
- OCR evidence is the only factual source; no GT or world knowledge is consulted at runtime.
- Properties numeric/value/unit/condition/owner gates remain unchanged unless a failing regression test proves a bug.
- Every promoted fact keeps literal `source_evidence`, owner/state coordinates, and an auditable quarantine/merge record.
- Uniquely attributable source assertions may be promoted once; an unqualified assertion is never fanned out to every compatible item.

## Design

### 1. Structure promotion

Retain a Structure feature when all of the following hold:

1. The feature/entity label and value are grounded in the same source span.
2. The span contains a bounded direct observation/change assertion (for example *contains*, *observed*, *formed*, *distributed*, *increased*, or *decreased*).
3. The feature is not a comparative-only, inferential, feedstock-metadata, composition-axis, or negated projection.
4. The fact has one explicit owner/state coordinate.

This allows atomic qualitative observations such as a named phase or grain morphology while continuing to reject generic/interpretive projections. A single observation can contain multiple explicitly stated atomic features; exact duplicates are merged.

### 2. Characterization promotion

Keep the existing direct-method requirement, but merge a result/caption candidate into a formal event when owner, state, method family, and event kind are source-compatible and the result evidence is in the same bounded source block. A result-only mention without a unique formal event remains quarantined. The merge is recorded in the quality audit and does not create a second event.

### 3. Chunk-level source-span deduplication

Before paper-level promotion, canonicalize candidate signatures using axis, owner, state, method/condition, normalized value, and normalized literal evidence span. Across overlapping chunks:

- identical assertions keep one survivor (the shortest complete evidence span);
- complementary fields for the same assertion are merged only when owner/state and source coordinates agree;
- conflicting values or coordinates remain separate and are sent to the existing review/audit path;
- no signature may cause owner fan-out.

### 4. Validation gates

Run the existing Alpha25 test suite, then an offline replay over all 30 papers. The change is acceptable only if unique-loose overall precision does not fall below the v203 reference (0.6162) and Structure/Characterization recall improves. If the gate fails, retain the code and audit changes but do not start a new live extraction.

## Rollout

1. Add focused unit/regression tests for qualitative direct Structure facts, inferential/comparative negatives, characterization event aliasing, and overlapping-chunk duplicate/conflict handling.
2. Run the offline replay and compare v203/v204/v205 metrics against the adjudicated expert GT.
3. If validation passes, run a new GLM-5.3 `reasoning_effort=low` 30-paper extraction in a new dated directory and generate the expert-GT comparison report.

