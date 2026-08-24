# GPT-5.6-sol independent expert GT vs business GT vs final v5

## Executive verdict

**Professional conclusion: the adjudicated GPT-5.6-sol expert GT is the most reliable factual ledger; among the two evaluated system outputs, business GT is more accurate overall, while final v5 contains more source-supported correct facts but also materially more unsupported projections, owner/value errors, and cross-item duplicates.**

- Business GT unique loose F1: **0.484**; final v5: **0.314**.
- Business GT unique strict F1: **0.170**; final v5: **0.195**. Strict matching additionally requires compatible owner/state/condition.
- Business GT unique core-tensile loose F1: **0.841**; final v5: **0.723**.
- Evidence adjudication confirmed 984 correct business-GT tags and 1081 correct final-v5 tags, but final v5 accumulated 4847 core factual-error tags versus 3699 for business GT.
- Cross-item duplicate tags: business GT 1284; final v5 1796.
- Paper-level professional ranking: business GT leads on **24/30** papers; final v5 on **6/30**.
- The audit-tag totals are diagnostic counts and may overlap; precision/recall/F1 comes only from the one-to-one claim matcher below.

## Expert-GT provenance

- Blind seal: `2026-08-18T08:55:41+00:00`
- Blind manifest SHA-256: `5278ca2dd788d7f2bfde9940bd768a67fee9dc6e1a1727e7822723dbb23d7155`
- Sealed independent claims: `3267`
- Official adjudicated claims: `3286`
- Accepted post-unblinding amendments: `89` (19 add, 70 replace); rejected: `2`.
- Adjudicated validation: `passed`; sealed artifact hash check: `150/150 matched; 0 mismatch`.
- Chart evidence audit: `95/95` CSVs covered by the sealed validation.
- Papers: `30/30`
- Loose match = same axis + compatible scientific semantic + compatible value/unit.
- Strict match = loose match + compatible material owner/state/region + test condition.
- Item IDs are never used as scientific identity. One-to-one matching prevents duplicates from inflating matches.
- This is an evidence-validated LLM expert reference, not an independently human-certified universal gold standard; the blind seal and all post-unblinding amendments are supplied for audit.

## Unique scientific claims: strict metrics

| System | Axis | Matched | System | Expert | Precision | Recall | F1 |
|---|---|---:|---:|---:|---:|---:|---:|
| business_gt | Composition | 116 | 637 | 856 | 0.182 | 0.136 | 0.155 |
| business_gt | Processing | 112 | 827 | 553 | 0.135 | 0.203 | 0.162 |
| business_gt | Structure | 102 | 715 | 773 | 0.143 | 0.132 | 0.137 |
| business_gt | Characterization | 11 | 206 | 294 | 0.053 | 0.037 | 0.044 |
| business_gt | Properties | 160 | 428 | 617 | 0.374 | 0.259 | 0.306 |
| business_gt | **micro** | 501 | 2813 | 3093 | 0.178 | 0.162 | 0.170 |
| business_gt | **unique core tensile** | 107 | 189 | 213 | 0.566 | 0.502 | 0.532 |
| final_v5 | Composition | 161 | 429 | 856 | 0.375 | 0.188 | 0.251 |
| final_v5 | Processing | 58 | 294 | 553 | 0.197 | 0.105 | 0.137 |
| final_v5 | Structure | 73 | 466 | 773 | 0.157 | 0.094 | 0.118 |
| final_v5 | Characterization | 5 | 58 | 294 | 0.086 | 0.017 | 0.028 |
| final_v5 | Properties | 160 | 345 | 617 | 0.464 | 0.259 | 0.333 |
| final_v5 | **micro** | 457 | 1592 | 3093 | 0.287 | 0.148 | 0.195 |
| final_v5 | **unique core tensile** | 99 | 141 | 213 | 0.702 | 0.465 | 0.559 |

## Unique scientific claims: loose metrics

| System | Axis | Matched | System | Expert | Precision | Recall | F1 |
|---|---|---:|---:|---:|---:|---:|---:|
| business_gt | Composition | 442 | 637 | 856 | 0.694 | 0.516 | 0.592 |
| business_gt | Processing | 291 | 827 | 553 | 0.352 | 0.526 | 0.422 |
| business_gt | Structure | 316 | 715 | 773 | 0.442 | 0.409 | 0.425 |
| business_gt | Characterization | 51 | 206 | 294 | 0.248 | 0.173 | 0.204 |
| business_gt | Properties | 329 | 428 | 617 | 0.769 | 0.533 | 0.630 |
| business_gt | **micro** | 1429 | 2813 | 3093 | 0.508 | 0.462 | 0.484 |
| business_gt | **unique core tensile** | 169 | 189 | 213 | 0.894 | 0.793 | 0.841 |
| final_v5 | Composition | 287 | 429 | 856 | 0.669 | 0.335 | 0.447 |
| final_v5 | Processing | 116 | 294 | 553 | 0.395 | 0.210 | 0.274 |
| final_v5 | Structure | 91 | 466 | 773 | 0.195 | 0.118 | 0.147 |
| final_v5 | Characterization | 9 | 58 | 294 | 0.155 | 0.031 | 0.051 |
| final_v5 | Properties | 233 | 345 | 617 | 0.675 | 0.378 | 0.484 |
| final_v5 | **micro** | 736 | 1592 | 3093 | 0.462 | 0.238 | 0.314 |
| final_v5 | **unique core tensile** | 128 | 141 | 213 | 0.908 | 0.601 | 0.723 |

## Raw item assignments: strict metrics

| System | Axis | Matched | System | Expert | Precision | Recall | F1 |
|---|---|---:|---:|---:|---:|---:|---:|
| business_gt | Composition | 117 | 752 | 875 | 0.156 | 0.134 | 0.144 |
| business_gt | Processing | 163 | 1760 | 650 | 0.093 | 0.251 | 0.135 |
| business_gt | Structure | 104 | 775 | 795 | 0.134 | 0.131 | 0.132 |
| business_gt | Characterization | 12 | 319 | 340 | 0.038 | 0.035 | 0.036 |
| business_gt | Properties | 160 | 436 | 626 | 0.367 | 0.256 | 0.301 |
| business_gt | **micro** | 556 | 4042 | 3286 | 0.138 | 0.169 | 0.152 |
| business_gt | **unique core tensile** | 107 | 189 | 213 | 0.566 | 0.502 | 0.532 |
| final_v5 | Composition | 177 | 450 | 875 | 0.393 | 0.202 | 0.267 |
| final_v5 | Processing | 96 | 324 | 650 | 0.296 | 0.148 | 0.197 |
| final_v5 | Structure | 73 | 470 | 795 | 0.155 | 0.092 | 0.115 |
| final_v5 | Characterization | 5 | 58 | 340 | 0.086 | 0.015 | 0.025 |
| final_v5 | Properties | 161 | 345 | 626 | 0.467 | 0.257 | 0.332 |
| final_v5 | **micro** | 512 | 1647 | 3286 | 0.311 | 0.156 | 0.208 |
| final_v5 | **unique core tensile** | 99 | 141 | 213 | 0.702 | 0.465 | 0.559 |

## Raw item assignments: loose metrics

| System | Axis | Matched | System | Expert | Precision | Recall | F1 |
|---|---|---:|---:|---:|---:|---:|---:|
| business_gt | Composition | 469 | 752 | 875 | 0.624 | 0.536 | 0.577 |
| business_gt | Processing | 381 | 1760 | 650 | 0.216 | 0.586 | 0.316 |
| business_gt | Structure | 324 | 775 | 795 | 0.418 | 0.408 | 0.413 |
| business_gt | Characterization | 57 | 319 | 340 | 0.179 | 0.168 | 0.173 |
| business_gt | Properties | 330 | 436 | 626 | 0.757 | 0.527 | 0.621 |
| business_gt | **micro** | 1561 | 4042 | 3286 | 0.386 | 0.475 | 0.426 |
| business_gt | **unique core tensile** | 169 | 189 | 213 | 0.894 | 0.793 | 0.841 |
| final_v5 | Composition | 302 | 450 | 875 | 0.671 | 0.345 | 0.456 |
| final_v5 | Processing | 153 | 324 | 650 | 0.472 | 0.235 | 0.314 |
| final_v5 | Structure | 91 | 470 | 795 | 0.194 | 0.114 | 0.144 |
| final_v5 | Characterization | 9 | 58 | 340 | 0.155 | 0.026 | 0.045 |
| final_v5 | Properties | 234 | 345 | 626 | 0.678 | 0.374 | 0.482 |
| final_v5 | **micro** | 789 | 1647 | 3286 | 0.479 | 0.240 | 0.320 |
| final_v5 | **unique core tensile** | 128 | 141 | 213 | 0.908 | 0.601 | 0.723 |

## Evidence-adjudicated error profile

| System | Audit tag | Count |
|---|---|---:|
| business_gt | `confirmed_correct` | 984 |
| business_gt | `confirmed_missing` | 2152 |
| business_gt | `unsupported_claim` | 1911 |
| business_gt | `wrong_owner` | 406 |
| business_gt | `wrong_axis` | 34 |
| business_gt | `wrong_origin` | 17 |
| business_gt | `value_conflict` | 283 |
| business_gt | `unit_conflict` | 244 |
| business_gt | `condition_conflict` | 804 |
| business_gt | `duplicate_claim` | 1284 |
| business_gt | `likely_ocr_error` | 100 |
| business_gt | `likely_chart_error` | 0 |
| final_v5 | `confirmed_correct` | 1081 |
| final_v5 | `confirmed_missing` | 2177 |
| final_v5 | `unsupported_claim` | 2936 |
| final_v5 | `wrong_owner` | 552 |
| final_v5 | `wrong_axis` | 61 |
| final_v5 | `wrong_origin` | 18 |
| final_v5 | `value_conflict` | 493 |
| final_v5 | `unit_conflict` | 219 |
| final_v5 | `condition_conflict` | 568 |
| final_v5 | `duplicate_claim` | 1796 |
| final_v5 | `likely_ocr_error` | 47 |
| final_v5 | `likely_chart_error` | 0 |

These are source-evidence adjudication tags, not mutually exclusive confusion-matrix cells. They identify the failure mode: omission, unsupported fact, wrong material/sample attribution, wrong axis/origin, value/unit/condition conflict, or duplication.

## Automated residual-difference queue

| System | Issue code | Count |
|---|---|---:|
| business_gt | `condition_conflict` | 108 |
| business_gt | `expert_gt_missing_or_unsupported` | 2149 |
| business_gt | `system_missing` | 1725 |
| business_gt | `unit_conflict` | 166 |
| business_gt | `value_conflict` | 165 |
| business_gt | `wrong_owner` | 897 |
| final_v5 | `condition_conflict` | 52 |
| final_v5 | `expert_gt_missing_or_unsupported` | 712 |
| final_v5 | `system_missing` | 2497 |
| final_v5 | `unit_conflict` | 32 |
| final_v5 | `value_conflict` | 114 |
| final_v5 | `wrong_owner` | 225 |

This queue is matcher-generated against the final adjudicated ledger. It is useful for locating disagreements but is not itself the professional verdict.

## Sealed vs adjudicated audit

The blind seal remains the historical pre-unblinding record. Official metrics use adjudicated GT; sealed metrics are retained below solely to show the effect of accepted corrections.

| System | Metric | Sealed F1 | Adjudicated F1 | Delta |
|---|---|---:|---:|---:|
| business_gt | unique loose micro | 0.481 | 0.484 | +0.003 |
| business_gt | unique strict micro | 0.166 | 0.170 | +0.004 |
| business_gt | unique core tensile | 0.843 | 0.841 | -0.002 |
| final_v5 | unique loose micro | 0.313 | 0.314 | +0.001 |
| final_v5 | unique strict micro | 0.194 | 0.195 | +0.001 |
| final_v5 | unique core tensile | 0.720 | 0.723 | +0.004 |

## Professional interpretation

- **Who is more accurate?** Business GT. Its unique loose, unique strict, and core-tensile F1 are all higher; it leads the paper-level professional ranking on 24/30 papers and has fewer total core factual-error tags and duplicates.
- **Who has more correct extracted content?** Final v5 has more individually confirmed correct tags, so it is not simply worse or hallucinated wholesale. Its problem is precision and organization: supported facts are mixed with many repeated projections and facts assigned to the wrong item/state/condition.
- **Who has more omissions?** Both omit substantial expert-ledger content. Evidence-tagged omissions are close, with final v5 slightly higher in this adjudication. The missing content is concentrated in owner/state-specific process, structure, characterization, and property facts rather than only headline tensile values.
- **What are the factual errors?** Final v5 has substantially more unsupported projections, wrong-owner tags, value conflicts, and duplicates. Business GT is more conservative but has more condition-conflict and slightly more unit-conflict tags, so it is not uniformly better on every error class.
- **Why are strict F1 values low?** The professional ledger is atomic and owner/state/condition-specific, while both v11 outputs often bundle, replicate, or omit those dimensions. Strict F1 is therefore a demanding attribution score, not a statement that only that fraction of sentences is scientifically true.

A post-materialization validation caught one concrete nominal-versus-measured composition error in an amendment: the PBF-EB Ti-22Al-25Nb sample contains 21.93 at.% Nb in the reported table, not nominal 25 at.%. It was corrected before official scoring. Two non-atomic umbrella claims were rejected. The sealed corpus was never changed.

Per-paper metrics are in the CSV. Per-claim evidence decisions and full audit payloads are retained in the adjudication files and machine-readable JSON report.
