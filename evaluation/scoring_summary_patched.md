# Extraction Scoring Report

- Groundtruth dir: `evaluation/groundtruth`
- Output dir: `evaluation/output_patched`
- Drop zero elements: `False`
- Value tolerance: `0.1`
- Temp tolerance (K): `1.0`
- Allow Celsius shift: `False`
- Ignore test unit: `False`
- Material match uses tests: `False`
- JSON report: `/Users/zhangziyu02/Desktop/太行实验室/KnowMat/evaluation/scoring_report_patched.json`

## Overall

### Composition Element Detection

- TP/FP/FN: `54` / `0` / `9`
- Precision/Recall/F1: `1.0000` / `0.8571` / `0.9231`

### Composition Value Error

- Count: `54`
- MAE: `0.006667`
- Max Abs Error: `0.18`
- Exact Rate: `0.962963`
- Within Tol Rate: `0.962963`

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

- Full Hit / Total: `6` / `7`
- Hit Rate: `0.857143`

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
- Composition Detection P/R/F1: `1.0000` / `0.8571` / `0.9231`
- Composition Value MAE: `0.006667` (count=54)
- Material Full Hit: `6/7` (hit_rate=0.857143)
- Test Detection P/R/F1: `1.0000` / `1.0000` / `1.0000`
- Test Value MAE: `0.0` (count=6)
