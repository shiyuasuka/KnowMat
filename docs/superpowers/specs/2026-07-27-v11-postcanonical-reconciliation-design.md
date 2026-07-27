# V11 Post-Canonical Reconciliation Design

## Goal

Make bounded GLM5.2 multi-item extraction robust to a fresh run emitting new,
one-off `Sample_ID` aliases. The fix must collapse duplicate physical materials
after deterministic sample canonicalization, preserve true experimental variants,
eliminate locally repairable fatal vocabulary issues, and recover the frozen
eight-paper alignment without changing prompts, model selection, chunking
architecture, or LLM request count.

The regression fixture is the fresh 2026-07-27 run under
`data/output/v11-8papers-regression-glm52-20260727`. Its final output contains 53
items versus 21 in GT, including 32 Inconel items that normalize to only three
canonical identities but are never merged afterward.

## Root Cause

Cross-chunk reconciliation runs before `_prepare_candidate` canonicalizes sample
identities. It therefore sees one-off aliases such as `IN625_BJ`, `BJ_X`, and
`IN625_BJ_HIP_X` as unrelated groups when no repeated raw ID provides an anchor.
Later preparation maps many of these rows to `Binder_Jetting_HIPed`,
`EPBF_HIPed`, or `LPBF_HIPed`, but no second merge pass exists, leaving repeated
canonical IDs in the normalized document.

The same ordering problem prevents state-specific recovery when raw CCIMA and
wall aliases do not reach the expected stable identity. Independently, safe
provider vocabulary such as reported numeric composition values can survive into
the frozen validator as an unsupported `value_kind` and produce fatal issues.

## Selected Design

### 1. Canonical identity before final fact preparation

Split deterministic preparation into two logical phases:

1. resolve process codes and derive a stable canonical sample identity;
2. merge items that now share the same physical identity before final axis
   pruning, recovery, ID regeneration, and frozen normalization.

The post-canonical identity key includes:

- canonical sample ID;
- role and data-nature compatibility;
- stable process family;
- explicit experimental discriminators such as delay value, wall number, and
  named manufacturing route.

Orientation, specimen location, observation time, heat-treatment state, and test
condition do not create a new material unless the source also contains an explicit
stable sample discriminator.

### 2. Merge semantics

Items in one post-canonical cluster merge through the existing axis-aware merge
logic:

- process stages merge by canonical process code, with parameter and evidence
  union;
- properties merge by property family, value, unit, method, specimen, and test
  condition;
- composition merges by basis and normalized component tuples;
- structure merges by entity, feature, value, state, and evidence.

After merging, candidate item IDs, process stage IDs, edges, property IDs, and
structure observation IDs are regenerated. State-aware deterministic recovery runs
once on the merged item rather than independently on each chunk alias.

### 3. Conservative handling of unmatched aliases

An unmatched alias is attached to a canonical material only when material family
and process family agree and no explicit discriminator conflicts. Ambiguous aliases
remain separate and reviewable. This prevents the repair from collapsing the three
interlayer delays, the six wall experiments, or distinct Binder Jetting, EPBF, and
LPBF routes.

### 4. Safe vocabulary repair

Extend the existing lossless composition compatibility layer for provider values
that unambiguously mean a reported scalar, range, inequality, balance, or
categorical value. Unknown or contradictory shapes remain fatal/reviewable; the
repair does not infer a number or composition absent from source evidence.

## Data Flow

1. Load fresh or cached chunk candidates.
2. Perform the existing conservative raw-alias reconciliation.
3. Resolve process codes and canonical sample identities.
4. Run post-canonical clustering and axis-aware merge.
5. Apply state-aware parameter, composition, structure, and property recovery.
6. Regenerate IDs and edges.
7. Run the unchanged frozen alpha.6 normalizer and validator.
8. Compare the rebuilt eight papers with frozen GT.

## Failure Handling and Observability

Log raw item count, first-pass reconciled count, post-canonical item count, and the
source aliases contributing to each non-trivial cluster. Reject clusters with
conflicting explicit discriminators. A document with no valid process stage remains
fatal rather than being silently promoted.

## Testing

Focused tests cover:

- many one-off Inconel aliases collapsing to exactly three process-family items;
- X/Z orientation aliases merging into the same material while retaining
  orientation-bound facts;
- CCIMA state aliases resolving to as-printed and thermal-stabilized targets;
- delay and wall-number discriminators remaining separate;
- repeated canonical IDs never reaching frozen normalization;
- safe reported numeric composition aliases producing no fatal issue;
- regenerated routes and IDs remaining valid after the second merge.

Business-path verification uses the 2026-07-27 cached GLM5.2 chunks, so it adds no
LLM calls. Each repair round runs the focused unit suite, rebuilds all eight papers,
and runs `scripts/validate_v11_examples.py`. At most three repair rounds are allowed.

## Acceptance Criteria

- eight papers evaluated with schema match rate 100%;
- no fatal or P0 issue;
- no duplicate canonical `Sample_ID` in any final document;
- Inconel item count returns from 32 to 3 while preserving its three routes;
- explicit delay and wall variants remain distinct;
- all six axis count alignments improve over the 2026-07-27 fresh-run baseline;
- target outcome is exact frozen-GT axis counts for all eight cached runs;
- prompts, GLM5.2, bounded chunk architecture, and LLM request count remain
  unchanged.

## Scope Boundaries

This change does not modify OCR, prompts, GT examples, the frozen alpha.6 package,
or extraction concurrency. It does not add an LLM reconciliation call or require
three independent extraction runs. Runtime logic does not read GT files or paper
titles.
