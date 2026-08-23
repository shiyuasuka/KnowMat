# Alpha25 Core-Tensile Exact Value Dominates Threshold

## Status

Approved by the user's continuing precision-first objective on 2026-08-23.
This is the next bounded increment after the v198 direct-author comparator
attribution fix.

## Goal

Remove a redundant core-tensile threshold from the formal Properties output
when the same owner and source assertion already provide a compatible exact
scalar for the same property. Keep the exact result and preserve the removed
threshold in the existing quality audit.

The change must improve precision without reducing matched count or recall. It
must not modify the professionally reviewed prompt, Alpha25 schema,
`final.json` shape, provider/model configuration, frozen responses, OCR/VLM,
or line-chart handling. Runtime decisions remain paper-, title-, material-,
model-, provider-, value-, and GT-independent.

## Confirmed Residual

The v198 30-paper output contains one inequality core-tensile Property:

- the R1 item contains `>700 MPa` from `exceed 700 MPa (773 MPa for R1)`; and
- the same R1 item contains the exact UTS `773 MPa`, grounded by the nested
  source phrase `773 MPa for R1`.

The threshold is scientifically true but is not a second measurement for R1.
Keeping it beside the exact value projects one source assertion into two
formal facts and produces a GPT-expert `value_conflict`. The exact `773 MPa`
claim is already matched by the expert ledger. No expert claim depends on the
coarser R1 threshold.

## Considered Approaches

1. **Exact-value dominance gate (selected).** Isolate only a threshold whose
   own source evidence contains a compatible exact scalar already emitted for
   the same owner/property/condition.
2. **Blanket inequality removal.** Rejected because a threshold can be the
   paper's only reported result and therefore carry unique recall.
3. **Evaluator-only deduplication.** Rejected because it would improve a score
   presentation without cleaning the incorrect formal claim set delivered to
   downstream consumers.

## Placement and Interface

Add one deterministic promotion pass after owner and source-coordinate gates,
cross-chunk source-assertion deduplication, and prose owner/value mismatch
handling, but before the existing tensile conflict quarantine.

The pass receives the inventory anchors and current `AxisFact` sequence, uses
the existing owner graph to verify canonical owner/role/nature equality, and
returns accepted facts plus ordinary `PromotionIssue` records. When both facts
have the same generic Sample_ID and the graph exposes the same non-empty set of
state candidates for both, that identical unresolved owner envelope is an
eligible equality witness only if every candidate has the same role and source
nature. The pass never selects one of those states. It does not create, modify,
or infer an owner, condition, value, unit, or evidence record.

## Eligibility Contract

A threshold/scalar pair is eligible only when every condition below holds:

1. Both candidates are numeric UTS, yield-strength, or elongation Properties.
2. The loser is a true inequality with one literal operator and finite bound;
   the survivor is one finite scalar, not a range, approximation-only text,
   second threshold, relative comparison, requirement, or qualitative value.
3. Both candidates have the same normalized owner, tensile family and subtype,
   canonical unit, Target/Reference role, and Experimental/Computational
   nature after the existing owner gates. Owner equality is either one resolved
   canonical owner ID or the identical non-empty unresolved candidate envelope
   described above; a merely similar material name is insufficient.
4. Their explicit test conditions are identical after current normalization.
   Missing versus explicit temperature, orientation, strain rate, standard,
   specimen state, or other condition is not compatible for this pass.
5. The survivor satisfies the threshold exactly: `>` and `>=` require a scalar
   at or above the bound with strictness respected; `<` and `<=` use the
   corresponding upper relation.
6. The threshold's own evidence contains the complete survivor scalar and
   compatible unit in the same bounded sentence or parenthetical proposition.
   Sharing only a paragraph, source block, numeric token, or material family is
   insufficient.
7. The threshold evidence explicitly binds that scalar to the same owner, or
   the survivor's complete evidence phrase (including owner) is literally
   nested inside the threshold evidence.
8. Exactly one scalar survivor satisfies all gates. Multiple values, owners,
   conditions, units, or survivor candidates make the relation a safe no-op.

A threshold that remains routed to a distinct group owner is never dominated
merely because one group member has an exact result. If an earlier owner gate
has already projected the threshold onto that exact member, the relation is
eligible only when the nested source phrase proves the same member/value. This
removes the false member-level duplicate without erasing the independently
routed group statement.

## Output and Audit Behavior

The formal output keeps the exact scalar unchanged and removes only the
dominated inequality. It does not merge the threshold text into the survivor,
because the audit already preserves the secondary presentation and the formal
Property should remain the exact scientific observation.

Emit `promotion_tensile_dominated_threshold_quarantined`. The complete record
in `quality_audit.json` must contain:

- the full removed threshold fact;
- the full surviving scalar fact;
- normalized owner, resolved owner ID or complete identical candidate envelope,
  role/nature, tensile family/subtype, unit, and condition;
- parsed operator, bound, scalar, and the satisfied relation;
- the bounded source proposition containing both presentations;
- the literal owner/value phrase proving same-owner nesting;
- the unique-survivor decision and `owner_invented=false`; and
- all original source evidence.

The existing `issues.json`/`issues.md` path receives the same concise issue
code. No field is added to `final.json`.

## Safety and Failure Handling

Ranges, approximate scalars, qualitative comparisons, requirements, table
limits, standards, independently asserted thresholds, different owners,
different states, different conditions, different tensile subtypes, unit
ambiguity, repeated scalar candidates, missing evidence, and parsing failures
are safe no-ops. Candidate-local failure preserves every original fact.

The implementation must use general numeric/source grammar and current owner
coordinates. Paper names and the `700`/`773` fixture values are regression
sentinels only and must never appear in runtime selectors.

## Verification

Focused tests must cover:

- `>700 MPa` being isolated when the same R1 owner has exact `773 MPa` and the
  threshold evidence contains `773 MPa for R1`;
- the scalar remaining byte-for-byte unchanged;
- a unique, complete audit payload;
- `<`, `<=`, `>`, and `>=` relation semantics;
- a lone threshold surviving;
- a distinct group-owner threshold surviving when an exact value belongs to
  only one member, while a threshold already projected onto that member remains
  eligible under the nested-evidence rule;
- owner, owner-envelope, condition, unit, subtype, role/nature, and
  source-proposition mismatches surviving;
- ranges, approximate scalars, requirements, and qualitative comparisons
  surviving;
- multiple possible scalar survivors producing a no-op;
- non-core-tensile and Composition non-interference; and
- deterministic output under input-order permutations.

Run the affected TiAl paper from frozen task cache and manually inspect every
semantic change. Then rematerialize all 30 papers with the unchanged evaluator.

Acceptance requires:

- 30/30 papers, 371/371 frozen tasks, invalid cache `0`, fatal `0`, and zero
  OCR/VLM/LLM/provider calls;
- the TiAl `>700 MPa` threshold absent and its `773 MPa` scalar present;
- no other unexplained formal semantic changes;
- GPT-expert global, Properties, and core-tensile matched counts and recall
  unchanged under loose and strict modes;
- corresponding precision and F1 non-decreasing, with core-tensile precision
  strictly increasing;
- Composition metrics and output unchanged;
- unchanged prompt/schema/cache digests and unchanged `final.json` shape; and
- complete audit plus deterministic replay behavior.

The official v198 GPT-expert unique baseline is:

- global loose: matched `665`, system `1376`, precision `0.483285`, recall
  `0.215002`, F1 `0.297606`;
- global strict: matched `361`, system `1376`, precision `0.262355`, recall
  `0.116715`, F1 `0.161557`;
- core tensile loose: matched `76`, system `88`, precision `0.863636`, recall
  `0.356808`, F1 `0.504983`; and
- core tensile strict: matched `41`, system `88`, precision `0.465909`, recall
  `0.192488`, F1 `0.272425`.

Any matched or recall decline narrows or reverts only this gate.

## Out of Scope

This increment does not suppress a threshold that is the only result, merge
different source assertions, reconcile condition mismatches, change reference
ownership, broaden tensile recall, alter evaluator rules, or address non-core
global precision residuals. Those remain separate evidence-driven increments.
