# Alpha25 specimen-preparation Processing gate

## Goal

Improve GLM Alpha25 precision by preventing specimen-preparation instructions
from entering the formal `Processing` route. The extraction prompt remains
unchanged, the public `final.json` shape remains unchanged, and every isolated
candidate remains available in the existing audit artifacts.

## Evidence and scope

The v166 frozen replay still contains process-stage candidates such as
sectioning walls, mounting samples, polishing, and etching for metallography.
These are experimental preparation/protocol steps, not material fabrication,
deposition, heat treatment, or other paper-level material-processing stages.
The rule is source-only: it may inspect the candidate's own evidence and
structured fields, but never GT, model/provider identity, confidence, or item
ordering.

## Chosen approach

Use a conservative gate immediately after existing process-stage assertion
gates and before metadata cleanup. A candidate is isolated only when all of the
following are true:

1. It is a prose `Processing` `process_stage` candidate (table rows remain on
   the coordinate-aware path).
2. Its own evidence contains an explicit specimen/sample preparation target
   (`sample`, `specimen`, `wall`, `mount`, or equivalent) and a preparation
   action such as sectioning/cutting/EDM, mounting, polishing, etching, or
   metallographic preparation.
3. The same evidence does not contain an executed material-processing cue such
   as fabrication/deposition/building, casting, heat treatment, aging,
   sintering, or a numeric manufacturing parameter.

This is intentionally narrower than rejecting every `machining` or `polishing`
mention. A source sentence that explicitly describes a production operation,
material surface treatment, or a table-declared process remains eligible.

## Audit behavior

The candidate is removed from the accepted facts and emits the concise issue
code `promotion_processing_specimen_preparation_quarantined`. The issue keeps
the complete candidate, source evidence, detected preparation action, and
reason. Existing `quality_audit.json`, `issues.json`, and `issues.md` writers
continue to carry the record; no new public field is added.

## Safety and acceptance criteria

- No prompt, provider, OCR, or schema changes.
- No owner or condition is created or rewritten.
- `core tensile strict precision` must remain at or above the protected v163
  baseline of `0.815534`.
- Existing processing events, numeric parameters, table facts, and explicit
  manufacturing surface operations remain unchanged.
- Focused promotion tests and the complete 30-paper cached rematerialization
  must pass with deterministic output.
