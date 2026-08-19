# Alpha25 Citation-Aware Tensile Reference Owner Implementation Plan

1. Add generic failing materialization tests for cited value cells, standard-qualified
   header cells, and protected Target/ambiguous cases.
2. Add Markdown cell parsing, literal numeric-value matching, and reference-marker
   extraction helpers in `src/knowmat/alpha25/materialize.py`.
3. Add a pre-index fact-level recovery pass that creates independent Reference
   anchors, rewrites only eligible Property facts, and emits a complete
   `reference_tensile_owner_recovered` issue.
4. Run focused Alpha25 tests, then the broader repository suite.
5. Rematerialize the highest-signal paper and inspect every changed fact and audit.
6. Rematerialize all 30 frozen papers, compare against v35 and the adjudicated GPT
   expert ledger, and reject any Composition or matched/recall regression.
