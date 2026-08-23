# Alpha25 Structure semantic atomic gates

## Goal

Improve precision of the GLM-5.2 Alpha25 materialized Structure ledger without
changing the reviewed extraction prompt or the existing `final.json` schema.
The gate must suppress projections that are comparisons, unresolved formula
variables, feedstock metadata, or method/causal prose while preserving
source-grounded measured structure quantities such as phase fractions, lattice
parameters, grain sizes, and texture metrics.

## Design

The promotion layer adds a narrow semantic pass after the existing field-level
Structure gate and before owner/table reconciliation:

1. A quantitative-looking feature whose raw value contains no numeric payload
   but is an inequality/comparison phrase (for example, `lower amounts of
   continuous alpha`) is quarantined. Numeric ranges, inequalities, and
   uncertainty values remain eligible.
2. A scalar/range feature whose raw value is only an unresolved variable or
   formula symbol (`d`, `x`, `h`) is quarantined when its evidence is a
   relation/equation or coefficient statement. Literal crystallographic fields
   (`a lattice parameter`, `c lattice parameter`) remain eligible.
3. Particle-size features are quarantined only when the same evidence clearly
   describes powder/feedstock/starting reinforcing particles or a particle-size
   analyzer. Nanoscale particles measured in the processed microstructure are
   not removed by this rule.
4. Generic method/effect/origin/function fields are isolated when they lack a
   direct atomic structural entity or measurement. Explicit phase presence,
   negative observations, and source-local measurements remain eligible.
5. A feature whose value payload is only a standalone measurement unit (for
   example, a second `grain size unit = µm` projection next to the real numeric
   grain-size fact) is quarantined as a non-observation. Numeric values with a
   separate unit, values that embed both number and unit, ranges, inequalities,
   and uncertainties remain eligible.

Each quarantine emits a deterministic issue code and retains the complete
candidate, evidence, reason, and before/after payload in the existing audit
ledger. The materializer continues to emit the same top-level `final.json`
keys.

## Validation

Add unit tests for each gate and for the preservation of legitimate measured
features. Run the focused Alpha25 tests, the complete Alpha25 suite, offline
rematerialization from the frozen 30-paper task cache, and both GT comparisons.
Production selection is based on strict owner/value precision first; changes
to loose recall/F1 are reported without hiding trade-offs.
