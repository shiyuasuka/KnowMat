# Alpha25 test-protocol Processing gate

## Goal

Keep test execution details out of the formal `Processing` route when the
extractor emits them as process stages. This is a narrow continuation of the
specimen-preparation gate and uses the same precision-first, audit-preserving
contract.

## Rule

For prose-only `process_stage` facts, isolate the candidate when its evidence
contains a direct mechanical-test protocol (`tensile-deformed`, fatigue/creep
tested, stress-strain or S–S curve) tied to a sample/specimen and does not
contain an executed fabrication, deposition, heat-treatment, or other material
processing event. Markdown/HTML tables and genuine manufacturing sentences are
left untouched.

## Audit and safety

Use issue code `promotion_processing_test_protocol_quarantined`; retain the
complete candidate and evidence in the existing audit artifacts. Do not change
the prompt, public `final.json` schema, owners, conditions, or tensile values.
The 30-paper replay must remain fatal-free and preserve the protected core
tensile strict precision baseline.
