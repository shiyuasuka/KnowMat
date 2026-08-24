# Alpha25 v204 source-assertion/protocol convergence acceptance

## Executive conclusion

v204 is recommended for the precision-first GLM baseline. It does not change
the reviewed prompt, model/provider, OCR/VLM/chart inputs, frozen responses, or
public `final.json` format. It restores source-literal core tensile facts,
prevents the confirmed CoCrNi cross-owner reversal, rejects the 1280 °C sample
state as a tensile test temperature, and binds only one compatible tensile
protocol.

The main precision result is strict attribution: GPT-expert core-tensile
strict precision rises from **0.702128 to 0.773585**, recall from **0.464789 to
0.577465**, and F1 from **0.559322 to 0.661290**. Condition conflicts fall from
**52 to 42**. Directly against business GT, core-tensile loose/strict F1 rises
from **0.739394/0.496970 to 0.798851/0.557471**.

Two frozen-GPT numeric gates remain recorded exceptions rather than production
deletion rules. Core loose precision is 0.899371 versus the 0.907801 gate
because the frozen expert ledger omits source-literal Al-Li and CL/PL facts
that business GT and the papers contain. The wrong-owner queue is 226 versus
225 because one Composition matcher pairing changes on the newly
tensile-bearing 1280 °C sample item; the recovered UTS itself has the correct
source owner. Removing these facts to improve a frozen score would delete true
source evidence and is therefore rejected.

## GPT expert comparison

| Metric | v203 | v204 | Delta | Gate |
|---|---:|---:|---:|---:|
| Global loose precision | 0.462312 | 0.466460 | +0.004148 | pass |
| Global loose F1 | 0.314194 | 0.319371 | +0.005177 | pass |
| Global strict precision | 0.287060 | 0.298758 | +0.011698 | pass |
| Global strict F1 | 0.195091 | 0.204550 | +0.009459 | pass |
| Core loose precision | 0.907801 | 0.899371 | -0.008430 | source-audited GT exception |
| Core loose recall | 0.600939 | 0.671362 | +0.070423 | pass |
| Core loose F1 | 0.723164 | 0.768817 | +0.045653 | pass |
| Core strict precision | 0.702128 | 0.773585 | +0.071457 | pass |
| Core strict recall | 0.464789 | 0.577465 | +0.112676 | pass |
| Core strict F1 | 0.559322 | 0.661290 | +0.101968 | pass |
| Wrong-owner conflicts | 225 | 226 | +1 | source-audited matcher exception |
| Condition conflicts | 52 | 42 | -10 | pass |
| System-missing claims | 2497 | 2482 | -15 | pass |

## Direct business-GT comparison

| Metric | v203 | v204 | Delta |
|---|---:|---:|---:|
| Global loose F1 | 0.349149 | 0.355415 | +0.006266 |
| Global strict F1 | 0.184336 | 0.190369 | +0.006033 |
| Core tensile loose F1 | 0.739394 | 0.798851 | +0.059457 |
| Core tensile strict F1 | 0.496970 | 0.557471 | +0.060501 |

## Source-audited high-risk results

- AP-HEA: YS ≈548 MPa, UTS ≈835 MPa, and fracture elongation ≈30% retain one
  owner and the unique room-temperature strain-rate protocol.
- L70/L90: six owner-specific tensile values retain ordered mapping and share
  the unique 800 °C/ISO 783-1999 protocol.
- LPBF Al-Li: YS 482 ± 1 MPa, UTS 539 ± 1 MPa, and elongation 8.8 ± 0.7% are
  assigned to the LPBF sample with ASTM B557M-10/extensometer details.
- CL/PL: source-literal values remain owner-specific and receive the unique
  room-temperature displacement-rate protocol.
- CoCrNi: 781.2 MPa stays on CoCrNi; 1165.2 MPa stays on
  CoCrNi(Al0.6TiFe)0.5. The earlier reversal is gone.
- Alloy 625: UTS 612 MPa stays on the literal 1280 °C sample, while 1280 °C is
  no longer represented as tensile test temperature.
- CCIMA: multiple compatible protocol events remain ambiguous and unbound.

The complete per-fact before/after records remain in each paper's
`quality_audit.json`. Across 30 papers there are 32 recovered assertion
coordinates, 11 owner reassignments, 33 protocol bindings, eight assertion
ambiguities, and two protocol ambiguities.

## Operational verification

| Check | Result |
|---|---:|
| Papers / frozen task responses | 30 / 405 |
| Fatal / silent-empty / provider calls | 0 / 0 / 0 |
| Replay wall times | 151.39 s / 152.17 s |
| Mean runtime regression versus v203 | +7.83% (gate ≤20%) |
| `final.json` deterministic byte matches | 30 / 30 |
| `quality_audit.json` deterministic byte matches | 30 / 30 |
| Summary deterministic byte match | yes |
| Composition unchanged versus v203 | 30 / 30 |
| All v204 switches off: v203 scientific payload match | 30 / 30 |
| All v204 switches off: v203 audit byte match | 30 / 30 |
| Focused regression | 756 passed |
| Complete Alpha25 regression | 1017 passed |
| Repository regression | 1231 passed; 1 unrelated missing external fixture |

The repository-only failure is the pre-existing absolute-path sci-align test
fixture `/ssd1/jinzongxiao/paddle_work/sci-align/dataset_test/embedding_index.json`.

## Artifacts

- First replay: `data/output-alpha25-v204-source-assertion-protocolfix-final30-20260824`
- Deterministic replay: `data/output-alpha25-v204-source-assertion-protocolfix-replay30-20260824`
- Three-way comparison: `protocolfix_v204_vs_gpt_expert_and_business.json`
- Direct business comparison: `protocolfix_v204_direct_business_gt.json`
- Compact delta ledger: `protocolfix_v204_delta_ledger.json`
