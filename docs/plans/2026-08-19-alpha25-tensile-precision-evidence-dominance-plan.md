# Alpha25 Tensile Precision Evidence Dominance Implementation Plan

1. Add focused failing materialization tests for rounded prose versus a complete
   uncertainty-bearing table record, one uniquely more-specific state owner, and
   deterministic evidence/audit merging.
2. Add protection tests for equal-information prose/table records, multiple table
   owners, competing precise survivors, owner role/nature conflicts, explicit
   condition conflicts, elongation subtype conflicts, ranges, thresholds,
   relative/qualitative results, and non-tensile/Composition facts.
3. Implement small pure helpers in `src/knowmat/alpha25/materialize.py` for central
   numeric values, measurement detail, compatible conditions, elongation subtype,
   complete table binding, owner provenance, and conservative candidate grouping.
4. Implement `_deduplicate_tensile_precision_evidence` as a deterministic
   post-owner-recovery pass. Keep one uniquely dominant fact, merge all evidence,
   preserve maximum confidence, and emit one complete
   `tensile_precision_duplicate_merged` audit record per removed fact.
5. Insert the pass after numeric tensile table/context owner recovery and before
   existing cross-item dominance. Run focused materialization, quality, and
   evaluator tests, then the full repository suite.
6. Rematerialize the highest-signal frozen papers without provider access, inspect
   every merge and protected ambiguity, and narrow the rule if any scientific
   binding is unsupported.
7. Rematerialize all 30 frozen papers twice. Verify 30/30 papers, 405/405 caches,
   zero failures/fatals/provider calls, byte-identical repeat outputs, unchanged
   prompt/schema/skill/cache digests, and complete `issues.json/.md` audit records.
8. Run the unchanged GPT expert/business GT evaluator against v36 and v37. Reject
   any Composition or global/core matched/recall regression; publish measured
   precision/F1, owner/condition residuals, timing, and the next residual cluster.
