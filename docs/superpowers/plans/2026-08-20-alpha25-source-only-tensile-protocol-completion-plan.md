# Alpha25 Source-Only Tensile Protocol Completion — Implementation Plan

Design: `docs/superpowers/specs/2026-08-20-alpha25-source-only-tensile-protocol-completion-design.md`

## Constraints and baseline

- Change only the isolated property-context recovery behavior and its tests.
- Do not modify prompts, schema, provider settings, OCR/VLM/LLM calls, frozen caches, or public `final.json` structure.
- Preserve source-literal evidence, reference protections, owner routing, condition conflict gates, elongation distinctions, and deterministic ordering.
- v45 frozen-cache baseline: 30 papers, 405 caches, 297.95 seconds; GPT expert unique core-tensile loose/strict = 166/211/213 and 117/211/213.

## Task 1 — Expand tensile event recognition

1. Update the model-agnostic lexical patterns in `src/knowmat/alpha25/property_context.py` to recognize explicit monotonic `tensile loading experiment` and equivalent loading/test forms.
2. Keep result-only, figure/caption, literature, fatigue, creep, relaxation, and preparation-only negatives ineligible.
3. Add focused tests for positive and negative wording through `PropertyContextIndex`/materialization.

## Task 2 — Assemble bounded procedural continuations

1. Change sentence assembly so a following sentence with a repeated tensile noun can still continue the same event when it has a procedural action and a new protocol detail.
2. Stop at an incompatible explicit discriminator or a second complete independent event; retain the two-sentence bound and same-block boundary.
3. Keep candidate source text and line ranges deterministic and preserve existing candidate ranking.
4. Add tests for adjacent ASTM/rate sentences, independent nearby protocols, and mechanical-test-family boundaries.

## Task 3 — Protect multi-temperature protocols

1. Reuse existing discriminator conflict logic; do not infer a temperature for an unqualified property from a multi-temperature source.
2. For a property with an explicit temperature, allow only shared method details from a compatible matrix without adding a conflicting temperature.
3. Add tests proving RT/600 °C isolation, no overwrite of explicit conditions, and safe no-op on ambiguity.

## Task 4 — Focused verification and pilot

1. Run the new property-context tests with `pytest -o addopts=''`.
2. Run the Alpha25 materialization test module and inspect all failures.
3. Run frozen-cache pilot/rematerialization for paper_017, paper_020, and paper_029.
4. Compare changed `final.json` files, issue audits, condition counts, and byte determinism against v45.

## Task 5 — Full frozen-cache validation

1. Rematerialize all 30 papers from exactly 405 frozen task responses with zero provider calls.
2. Verify schema/skill/prompt/cache digests, success/failure counts, runtime, and repeated output byte identity.
3. Run the existing GPT-5.6-sol expert and business-GT comparison, including global, Composition, Properties, and unique core-tensile loose/strict metrics.
4. Accept only if every gate in the design passes; otherwise narrow or revert the candidate rule and retain the audit.

## Expected files

- `src/knowmat/alpha25/property_context.py`
- `tests/test_alpha25_materialize.py`
- pilot and full-run output/report directories outside tracked source code

## Rollback boundary

All production behavior is isolated to the parser/index path. If any acceptance
gate fails, revert only the new grammar/continuation logic and its tests; do not
touch unrelated worktree changes or delete audit artifacts.
