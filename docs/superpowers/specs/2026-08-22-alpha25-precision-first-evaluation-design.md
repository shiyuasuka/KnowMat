# Alpha25 precision-first evaluation and owner matching

## Goal

Improve the trustworthiness of the Alpha25 precision report without changing
the reviewed extraction prompt, model/provider behavior, or the public
`final.json` schema. The immediate false-positive source is evaluator-side:
numeric claims from the same table can be greedily paired to the wrong
condition when their uncertainty intervals overlap.

## Scope and non-goals

In scope:

- Make numeric comparison center-value aware when both claims report a center
  and standard deviation.
- Make candidate assignment deterministic and condition/value aware so a claim
  is not forced into an ambiguous pairing.
- Add regression coverage for the 817/825.3 table-column failure and for valid
  rounded/scalar matches.
- Re-run the frozen 30-paper Alpha25 comparison and separate evaluator changes
  from production extraction changes in the report.

Out of scope:

- Editing the human-reviewed extraction prompt.
- Hard-coding GLM-5.2 or any provider-specific request shape.
- Changing `final.json`, `issues.json`, or `issues.md` public formats.
- Adding a production quarantine rule before a corrected residual is observed.

## Design

### Numeric value matching

`value_score` continues to normalize units and support scalar, range, and
inequality values. When both sides contain a numeric center and a standard
deviation, the center values are compared directly with a conservative
rounding tolerance; overlapping uncertainty intervals are not sufficient for
a match. When only one side has a standard deviation, the center can still
match a scalar using the existing presentation tolerance. This preserves
rounded prose/table matches while preventing 817 ± 8.68 from matching
825.3 ± 3.10.

### Assignment

Candidate pairs retain semantic, value, owner, and condition scores. For each
system claim, candidates are ranked by exact canonical value/condition first,
then the existing weighted score. A candidate is accepted only when it is the
unique best expert claim or beats the second-best candidate by a deterministic
margin. Otherwise it remains unmatched and is reported for adjudication. This
is intentionally conservative: an unmatched claim is preferable to a wrong
owner/condition match in a precision-first audit.

### Production follow-up

After the evaluator rerun, only residuals that are both (a) reproducible on the
frozen cache and (b) independently verified as factual production errors may
drive a new promotion/quarantine gate. Any such gate must retain the full
record and issue code in the existing audit artifacts.

## Data flow

```text
v11 output + expert ledger
        |
        v
  flatten + normalize
        |
        v
  center-aware candidate scoring
        |
        v
  conservative deterministic assignment
        |
        +--> metrics / issue candidates
        |
        +--> verified production residuals (later, if any)
```

## Error handling and compatibility

- Missing or non-numeric values retain current categorical behavior.
- Unit conversion remains unchanged.
- Ambiguous candidates are emitted as unmatched, never silently discarded.
- Existing report fields remain valid; new diagnostic detail may be additive in
  evaluator reports only.

## Verification

1. Add unit tests for center-vs-uncertainty mismatch, exact center match with
   different uncertainty, scalar/uncertainty compatibility, and deterministic
   ambiguous assignment.
2. Run the focused evaluator and Alpha25 regression suites.
3. Re-materialize the frozen 30-paper cache and compare v95 metrics and issue
   counts before deciding whether production code needs another gate.
