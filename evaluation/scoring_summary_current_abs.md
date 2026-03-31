# Extraction Scoring Report

- Groundtruth dir: `/Users/zhangziyu02/Desktop/太行实验室/KnowMat/evaluation/groundtruth`
- Output dir: `/Users/zhangziyu02/Desktop/太行实验室/KnowMat/evaluation/output`
- Drop zero elements: `False`
- Value tolerance: `0.1`
- Temp tolerance (K): `1.0`
- Allow Celsius shift: `False`
- Ignore test unit: `False`
- Material match uses tests: `False`
- JSON report: `/Users/zhangziyu02/Desktop/太行实验室/KnowMat/evaluation/scoring_report_current_abs.json`

## Overall

### Composition Element Detection

- TP/FP/FN: `48` / `0` / `15`
- Precision/Recall/F1: `1.0000` / `0.7619` / `0.8649`

### Composition Value Error

- Count: `48`
- MAE: `0.00375`
- Max Abs Error: `0.18`
- Exact Rate: `0.979167`
- Within Tol Rate: `0.979167`

### Performance Test Detection

- TP/FP/FN: `6` / `0` / `0`
- Precision/Recall/F1: `1.0000` / `1.0000` / `1.0000`

### Performance Test Value Error

- Count: `6`
- MAE: `0.0`
- Max Abs Error: `0.0`
- Exact Rate: `1.0`
- Within Tol Rate: `1.0`

### Material-Level Full Hit

- Full Hit / Total: `4` / `7`
- Hit Rate: `0.571429`

## By Temperature (K)

| Temp_K | Test TP | Test FP | Test FN | Test F1 | Value Count | Value MAE | Value MaxErr |
|---:|---:|---:|---:|---:|---:|---:|---:|
| 298.15 | 6 | 0 | 0 | 1.0000 | 6 | 0.0 | 0.0 |

## By Property Type

| Property | Test TP | Test FP | Test FN | Test F1 | Value Count | Value MAE | Value MaxErr |
|---|---:|---:|---:|---:|---:|---:|---:|
| microhardness | 6 | 0 | 0 | 1.0000 | 6 | 0.0 | 0.0 |

## Per Article

### Article `AYzJ5YexzHG1b1fwF_ul`
- Composition Detection P/R/F1: `1.0000` / `0.7619` / `0.8649`
- Composition Value MAE: `0.00375` (count=48)
- Material Full Hit: `4/7` (hit_rate=0.571429)
- Test Detection P/R/F1: `1.0000` / `1.0000` / `1.0000`
- Test Value MAE: `0.0` (count=6)
