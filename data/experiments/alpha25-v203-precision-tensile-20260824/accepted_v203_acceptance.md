# Alpha25 v203 precision-first tensile acceptance

Date: 2026-08-24

## Verdict

Accepted.  The v203 source-coordinate/materialization changes improve recall
and F1 without reducing the approved precision floors.  The professional
prompt, provider/model, OCR/VLM inputs, Alpha25 schema, frozen responses, and
public `final.json` shape were not changed.  The replay consumed the same 405
cached task responses and made zero provider/API calls.

The main gain is a source-proven Alloy 625 tensile table.  X/Y/Z and
Horizontal/Vertical orientation matrices remain fail-closed because their
owner/orientation coordinates were not precise enough under strict matching.
An adjacent fatigue `all specimens` clause can no longer authorize a tensile
protocol.  Existing complete source-block bundles are not rewritten by dense
completion.

## GPT expert GT result

All metrics below use unique scientific claims.  Strict matching additionally
requires compatible owner, state/region, and condition.

| Metric | v202 | v203 | Delta | Gate | Result |
|---|---:|---:|---:|---:|---:|
| Global loose matched | 731 | 736 | +5 | >= 731 | pass |
| Global loose precision | 0.460618 | 0.462312 | +0.001694 | >= 0.460618 | pass |
| Global loose F1 | 0.312393 | 0.314194 | +0.001801 | > 0.312393 | pass |
| Global strict matched | 445 | 457 | +12 | >= 445 | pass |
| Global strict precision | 0.280403 | 0.287060 | +0.006657 | >= 0.280403 | pass |
| Global strict F1 | 0.190171 | 0.195091 | +0.004920 | >= 0.190171 | pass |
| Core tensile loose matched | 123 | 128 | +5 | > 123 | pass |
| Core tensile loose precision | 0.904412 | 0.907801 | +0.003389 | >= 0.900000 | pass |
| Core tensile loose recall | 0.577465 | 0.600939 | +0.023474 | > 0.577465 | pass |
| Core tensile loose F1 | 0.704871 | 0.723164 | +0.018293 | > 0.704871 | pass |
| Core tensile strict matched | 87 | 99 | +12 | > 87 | pass |
| Core tensile strict precision | 0.639706 | 0.702128 | +0.062422 | >= 0.639706 | pass |
| Core tensile strict recall | 0.408451 | 0.464789 | +0.056338 | > 0.408451 | pass |
| Core tensile strict F1 | 0.498567 | 0.559322 | +0.060755 | > 0.498567 | pass |
| Wrong-owner conflicts | 225 | 225 | 0 | <= 225 | pass |
| Condition conflicts | 59 | 52 | -7 | < 59 | pass |

## Direct business-GT result

| Metric | v202 | v203 | Delta | Gate | Result |
|---|---:|---:|---:|---:|---:|
| Global loose F1 | 0.347273 | 0.349149 | +0.001876 | no regression | pass |
| Global strict F1 | 0.181818 | 0.184336 | +0.002518 | no regression | pass |
| Core tensile loose F1 | 0.720000 | 0.739394 | +0.019394 | > 0.720000 | pass |
| Core tensile strict F1 | 0.467692 | 0.496970 | +0.029278 | > 0.467692 | pass |

Business GT remains broader and has higher recall.  Against GPT expert GT,
business GT core-tensile loose F1 is 0.840796 versus v203's 0.723164.  v203 is
the more conservative precision-first output: core-tensile loose precision is
0.907801 versus business GT's 0.894180, and strict precision is 0.702128 versus
0.566138.  The architecture improvement narrows the gap without trading
precision for bulk output.

## Operational and compatibility evidence

| Check | Result |
|---|---:|
| Papers / frozen task responses | 30 / 405 |
| Fatal outputs / provider calls | 0 / 0 |
| Accepted replay wall times | 140.45 s / 141.06 s |
| Mean runtime regression vs v202 | +0.23% |
| `final.json` deterministic byte matches | 30 / 30 |
| `quality_audit.json` deterministic byte matches | 30 / 30 |
| Summary deterministic byte match | yes |
| Composition-stable papers | 30 / 30 |
| Shared Composition payloads changed | 0 / 264 |
| New item with non-empty Composition | 0 / 1 |
| All v203 switches off: scientific `final.json` match | 30 / 30 |
| All v203 switches off: `quality_audit.json` byte match | 30 / 30 |
| All v203 switches off: summary byte match | yes |

The switches-off raw `final.json` files differ from historical v202 only in
`Rule_Metadata.git_commit`, which correctly records the current repository
revision.  Removing that run metadata field yields 30/30 identical scientific
documents; audit and summary files are already byte-identical.

## Verification

- Focused materialize/protocol/source-coordinate: 372 passed.
- All Alpha25 tests: 988 passed.
- Full repository: 1202 passed, one known external-fixture failure.  The
  failing test requires an unavailable absolute
  `/ssd1/jinzongxiao/paddle_work/sci-align/dataset_test/embedding_index.json`.
- Python compile and `git diff --check`: passed.

Primary output:
`data/output-alpha25-v203-precision-tensile-accepted-final30-20260824`

Deterministic replay:
`data/output-alpha25-v203-precision-tensile-accepted-replay30-20260824`

Machine-readable metrics:
`data/experiments/alpha25-v203-precision-tensile-20260824/accepted_v203_acceptance.json`

Full three-way matcher report:
`data/experiments/alpha25-v203-precision-tensile-20260824/accepted_v203_vs_gpt_expert_and_business.json`
