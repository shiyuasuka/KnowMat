# Alpha25 source-block property fan-out suppression

## Goal

Improve precision without changing the business-reviewed extraction prompt or
the public `final.json` schema.  The rule targets a known cross-chunk failure:
one prose assertion is emitted in several chunks with slightly different
evidence envelopes, so the existing exact-evidence fan-out gate cannot see the
group and a comparison is materialized as multiple scalar properties.

## Scope and safety contract

The new gate is source-only and conservative.  It may inspect only existing
candidate facts, their copied evidence, and the full paper source text.  It
must not use GT, confidence, generated IDs, item order, or provider/model
names, and it must never create an owner or condition.

It groups only Property facts when all of the following hold:

1. Their records bind to the same unambiguous prose source block.
2. They have the same normalized property name and unit.
3. At least two distinct literal value payloads are present.
4. No value has a source-grounded distinct test condition.
5. The source block is not collective/shared-owner prose.
6. Every candidate owner is not explicitly named as a complete one-to-one
   owner coordinate in the source block.

Markdown/HTML tables, ambiguous source bindings, explicit respectively
coordinates, and source blocks that name all candidate owners are left
untouched.  Core tensile properties are eligible because they are the primary
overprojection risk; an explicit owner/condition coordinate still protects a
valid pair.

## Output and audit behavior

Facts rejected by the gate are isolated from the accepted list and retained in
the existing promotion audit stream with code
`promotion_source_block_property_fanout_quarantined`.  The issue payload keeps
the complete conflict set, source block, and original fact.  No accepted fact
is rewritten, and the existing issue/audit writers continue to provide the
same schema and traceability guarantees.

## Verification

Add focused tests for:

- suppressing two unqualified values from one prose block;
- preserving explicitly owner-labelled pairs;
- preserving condition-labelled pairs;
- preserving table facts and collective assertions;
- determinism under input order changes.

Run the focused Alpha25 promotion/claim-quality tests, then rematerialize the
cached 30-paper corpus and compare independent GT metrics.  Success is a
reduction in unqualified property fan-out and no removal of the protected
owner/condition/table cases; any F1 change is reported separately from the
audit reduction.
