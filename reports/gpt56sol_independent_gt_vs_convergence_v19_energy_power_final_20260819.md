# GPT-5.6-sol independent expert GT vs business GT vs final v5

## Executive verdict

**Professional conclusion: the adjudicated GPT-5.6-sol expert GT is the most reliable factual ledger; among the two evaluated system outputs, business GT is more accurate overall, while final v5 contains more source-supported correct facts but also materially more unsupported projections, owner/value errors, and cross-item duplicates.**

- Business GT unique loose F1: **0.370**; final v5: **0.257**.
- Business GT unique strict F1: **0.128**; final v5: **0.113**. Strict matching additionally requires compatible owner/state/condition.
- Business GT unique core-tensile loose F1: **0.713**; final v5: **0.483**.
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
| business_gt | Composition | 114 | 637 | 856 | 0.179 | 0.133 | 0.153 |
| business_gt | Processing | 84 | 828 | 553 | 0.101 | 0.152 | 0.122 |
| business_gt | Structure | 102 | 931 | 773 | 0.110 | 0.132 | 0.120 |
| business_gt | Characterization | 12 | 724 | 294 | 0.017 | 0.041 | 0.024 |
| business_gt | Properties | 114 | 428 | 617 | 0.266 | 0.185 | 0.218 |
| business_gt | **micro** | 426 | 3548 | 3093 | 0.120 | 0.138 | 0.128 |
| business_gt | **unique core tensile** | 107 | 255 | 222 | 0.420 | 0.482 | 0.449 |
| final_v5 | Composition | 210 | 988 | 856 | 0.213 | 0.245 | 0.228 |
| final_v5 | Processing | 82 | 793 | 553 | 0.103 | 0.148 | 0.122 |
| final_v5 | Structure | 153 | 3087 | 773 | 0.050 | 0.198 | 0.079 |
| final_v5 | Characterization | 10 | 609 | 294 | 0.016 | 0.034 | 0.022 |
| final_v5 | Properties | 90 | 1052 | 617 | 0.086 | 0.146 | 0.108 |
| final_v5 | **micro** | 545 | 6529 | 3093 | 0.083 | 0.176 | 0.113 |
| final_v5 | **unique core tensile** | 83 | 420 | 222 | 0.198 | 0.374 | 0.259 |

## Unique scientific claims: loose metrics

| System | Axis | Matched | System | Expert | Precision | Recall | F1 |
|---|---|---:|---:|---:|---:|---:|---:|
| business_gt | Composition | 442 | 637 | 856 | 0.694 | 0.516 | 0.592 |
| business_gt | Processing | 197 | 828 | 553 | 0.238 | 0.356 | 0.285 |
| business_gt | Structure | 316 | 931 | 773 | 0.339 | 0.409 | 0.371 |
| business_gt | Characterization | 54 | 724 | 294 | 0.075 | 0.184 | 0.106 |
| business_gt | Properties | 221 | 428 | 617 | 0.516 | 0.358 | 0.423 |
| business_gt | **micro** | 1230 | 3548 | 3093 | 0.347 | 0.398 | 0.370 |
| business_gt | **unique core tensile** | 170 | 255 | 222 | 0.667 | 0.766 | 0.713 |
| final_v5 | Composition | 508 | 988 | 856 | 0.514 | 0.593 | 0.551 |
| final_v5 | Processing | 203 | 793 | 553 | 0.256 | 0.367 | 0.302 |
| final_v5 | Structure | 288 | 3087 | 773 | 0.093 | 0.373 | 0.149 |
| final_v5 | Characterization | 30 | 609 | 294 | 0.049 | 0.102 | 0.066 |
| final_v5 | Properties | 206 | 1052 | 617 | 0.196 | 0.334 | 0.247 |
| final_v5 | **micro** | 1235 | 6529 | 3093 | 0.189 | 0.399 | 0.257 |
| final_v5 | **unique core tensile** | 155 | 420 | 222 | 0.369 | 0.698 | 0.483 |

## Raw item assignments: strict metrics

| System | Axis | Matched | System | Expert | Precision | Recall | F1 |
|---|---|---:|---:|---:|---:|---:|---:|
| business_gt | Composition | 115 | 752 | 875 | 0.153 | 0.131 | 0.141 |
| business_gt | Processing | 105 | 1758 | 650 | 0.060 | 0.162 | 0.087 |
| business_gt | Structure | 104 | 1076 | 795 | 0.097 | 0.131 | 0.111 |
| business_gt | Characterization | 13 | 1096 | 340 | 0.012 | 0.038 | 0.018 |
| business_gt | Properties | 114 | 436 | 626 | 0.261 | 0.182 | 0.215 |
| business_gt | **micro** | 451 | 5118 | 3286 | 0.088 | 0.137 | 0.107 |
| business_gt | **unique core tensile** | 107 | 255 | 222 | 0.420 | 0.482 | 0.449 |
| final_v5 | Composition | 231 | 1001 | 875 | 0.231 | 0.264 | 0.246 |
| final_v5 | Processing | 101 | 891 | 650 | 0.113 | 0.155 | 0.131 |
| final_v5 | Structure | 154 | 3185 | 795 | 0.048 | 0.194 | 0.077 |
| final_v5 | Characterization | 16 | 655 | 340 | 0.024 | 0.047 | 0.032 |
| final_v5 | Properties | 90 | 1066 | 626 | 0.084 | 0.144 | 0.106 |
| final_v5 | **micro** | 592 | 6798 | 3286 | 0.087 | 0.180 | 0.117 |
| final_v5 | **unique core tensile** | 83 | 420 | 222 | 0.198 | 0.374 | 0.259 |

## Raw item assignments: loose metrics

| System | Axis | Matched | System | Expert | Precision | Recall | F1 |
|---|---|---:|---:|---:|---:|---:|---:|
| business_gt | Composition | 469 | 752 | 875 | 0.624 | 0.536 | 0.577 |
| business_gt | Processing | 236 | 1758 | 650 | 0.134 | 0.363 | 0.196 |
| business_gt | Structure | 324 | 1076 | 795 | 0.301 | 0.408 | 0.346 |
| business_gt | Characterization | 65 | 1096 | 340 | 0.059 | 0.191 | 0.091 |
| business_gt | Properties | 221 | 436 | 626 | 0.507 | 0.353 | 0.416 |
| business_gt | **micro** | 1315 | 5118 | 3286 | 0.257 | 0.400 | 0.313 |
| business_gt | **unique core tensile** | 170 | 255 | 222 | 0.667 | 0.766 | 0.713 |
| final_v5 | Composition | 529 | 1001 | 875 | 0.528 | 0.605 | 0.564 |
| final_v5 | Processing | 247 | 891 | 650 | 0.277 | 0.380 | 0.321 |
| final_v5 | Structure | 289 | 3185 | 795 | 0.091 | 0.364 | 0.145 |
| final_v5 | Characterization | 34 | 655 | 340 | 0.052 | 0.100 | 0.068 |
| final_v5 | Properties | 206 | 1066 | 626 | 0.193 | 0.329 | 0.243 |
| final_v5 | **micro** | 1305 | 6798 | 3286 | 0.192 | 0.397 | 0.259 |
| final_v5 | **unique core tensile** | 155 | 420 | 222 | 0.369 | 0.698 | 0.483 |

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
| business_gt | `condition_conflict` | 77 |
| business_gt | `expert_gt_missing_or_unsupported` | 3268 |
| business_gt | `system_missing` | 1971 |
| business_gt | `unit_conflict` | 182 |
| business_gt | `value_conflict` | 351 |
| business_gt | `wrong_owner` | 787 |
| final_v5 | `condition_conflict` | 113 |
| final_v5 | `expert_gt_missing_or_unsupported` | 4694 |
| final_v5 | `system_missing` | 1981 |
| final_v5 | `unit_conflict` | 205 |
| final_v5 | `value_conflict` | 592 |
| final_v5 | `wrong_owner` | 600 |

This queue is matcher-generated against the final adjudicated ledger. It is useful for locating disagreements but is not itself the professional verdict.

## Sealed vs adjudicated audit

The blind seal remains the historical pre-unblinding record. Official metrics use adjudicated GT; sealed metrics are retained below solely to show the effect of accepted corrections.

| System | Metric | Sealed F1 | Adjudicated F1 | Delta |
|---|---|---:|---:|---:|
| business_gt | unique loose micro | 0.367 | 0.370 | +0.003 |
| business_gt | unique strict micro | 0.125 | 0.128 | +0.003 |
| business_gt | unique core tensile | 0.714 | 0.713 | -0.001 |
| final_v5 | unique loose micro | 0.256 | 0.257 | +0.001 |
| final_v5 | unique strict micro | 0.111 | 0.113 | +0.003 |
| final_v5 | unique core tensile | 0.480 | 0.483 | +0.002 |

## Professional interpretation

- **Who is more accurate?** Business GT. Its unique loose, unique strict, and core-tensile F1 are all higher; it leads the paper-level professional ranking on 24/30 papers and has fewer total core factual-error tags and duplicates.
- **Who has more correct extracted content?** Final v5 has more individually confirmed correct tags, so it is not simply worse or hallucinated wholesale. Its problem is precision and organization: supported facts are mixed with many repeated projections and facts assigned to the wrong item/state/condition.
- **Who has more omissions?** Both omit substantial expert-ledger content. Evidence-tagged omissions are close, with final v5 slightly higher in this adjudication. The missing content is concentrated in owner/state-specific process, structure, characterization, and property facts rather than only headline tensile values.
- **What are the factual errors?** Final v5 has substantially more unsupported projections, wrong-owner tags, value conflicts, and duplicates. Business GT is more conservative but has more condition-conflict and slightly more unit-conflict tags, so it is not uniformly better on every error class.
- **Why are strict F1 values low?** The professional ledger is atomic and owner/state/condition-specific, while both v11 outputs often bundle, replicate, or omit those dimensions. Strict F1 is therefore a demanding attribution score, not a statement that only that fraction of sentences is scientifically true.

A post-materialization validation caught one concrete nominal-versus-measured composition error in an amendment: the PBF-EB Ti-22Al-25Nb sample contains 21.93 at.% Nb in the reported table, not nominal 25 at.%. It was corrected before official scoring. Two non-atomic umbrella claims were rejected. The sealed corpus was never changed.

Per-paper metrics are in the CSV. Per-claim evidence decisions and full audit payloads are retained in the adjudication files and machine-readable JSON report.
