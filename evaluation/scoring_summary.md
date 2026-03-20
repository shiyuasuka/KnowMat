# Extraction Scoring Report

- Groundtruth dir: `groundtruth`
- Output dir: `output`
- Drop zero elements: `False`
- Value tolerance: `0.1`
- Temp tolerance (K): `1.0`
- Allow Celsius shift: `False`
- Ignore test unit: `False`
- Material match uses tests: `False`
- JSON report: `/Users/zhangziyu02/Desktop/对比试验/scoring_report.json`

## Overall

### Composition Element Detection

- TP/FP/FN: `55` / `0` / `1`
- Precision/Recall/F1: `1.0000` / `0.9821` / `0.9910`

### Composition Value Error

- Count: `55`
- MAE: `0.470749`
- Max Abs Error: `10.519027`
- Exact Rate: `0.563636`
- Within Tol Rate: `0.709091`

### Performance Test Detection

- TP/FP/FN: `93` / `37` / `25`
- Precision/Recall/F1: `0.7154` / `0.7881` / `0.7500`

### Performance Test Value Error

- Count: `93`
- MAE: `113.375591`
- Max Abs Error: `1071.07`
- Exact Rate: `0.623656`
- Within Tol Rate: `0.623656`

## By Temperature (K)

| Temp_K | Test TP | Test FP | Test FN | Test F1 | Value Count | Value MAE | Value MaxErr |
|---:|---:|---:|---:|---:|---:|---:|---:|
| 77 | 6 | 0 | 0 | 1.0000 | 6 | 101.033333 | 375.0 |
| 298 | 43 | 5 | 1 | 0.9348 | 43 | 87.62907 | 1071.07 |
| 673 | 2 | 0 | 0 | 1.0000 | 2 | 0.0 | 0.0 |
| 773 | 5 | 0 | 0 | 1.0000 | 5 | 0.0 | 0.0 |
| 873 | 21 | 0 | 5 | 0.8936 | 21 | 151.575238 | 779.07 |
| 973 | 0 | 0 | 5 | 0.0000 | 0 | None | None |
| 1073 | 0 | 0 | 6 | 0.0000 | 0 | None | None |
| 1173 | 0 | 0 | 8 | 0.0000 | 0 | None | None |
| 1273 | 4 | 8 | 0 | 0.5000 | 4 | 121.5 | 486.0 |
| 1473 | 6 | 6 | 0 | 0.6667 | 6 | 136.766667 | 549.0 |
| 1673 | 2 | 10 | 0 | 0.2857 | 2 | 419.5 | 839.0 |
| 1873 | 4 | 8 | 0 | 0.5000 | 4 | 210.25 | 841.0 |

## By Property Type

| Property | Test TP | Test FP | Test FN | Test F1 | Value Count | Value MAE | Value MaxErr |
|---|---:|---:|---:|---:|---:|---:|---:|
| elongation | 10 | 4 | 8 | 0.6250 | 10 | 2.44 | 12.2 |
| elongation_compressive | 8 | 12 | 0 | 0.5714 | 8 | 0.075 | 0.6 |
| fracture_strain | 4 | 0 | 0 | 1.0000 | 4 | 0.0 | 0.0 |
| total_elongation | 7 | 0 | 1 | 0.9333 | 7 | 8.347143 | 28.28 |
| ultimate_strength_compressive | 8 | 12 | 0 | 0.5714 | 8 | 33.875 | 271.0 |
| ultimate_tensile_strength | 14 | 0 | 6 | 0.8235 | 14 | 369.871429 | 1071.07 |
| uniform_elongation | 8 | 0 | 0 | 1.0000 | 8 | 6.91125 | 20.75 |
| yield_strength | 22 | 1 | 10 | 0.8000 | 22 | 101.864091 | 558.62 |
| yield_strength_compressive | 12 | 8 | 0 | 0.7500 | 12 | 226.25 | 841.0 |

## Per Article

### Article `1`
- Composition Detection P/R/F1: `1.0000` / `1.0000` / `1.0000`
- Composition Value MAE: `0.0` (count=4)
- Test Detection P/R/F1: `1.0000` / `1.0000` / `1.0000`
- Test Value MAE: `0.0` (count=8)

### Article `2`
- Composition Detection P/R/F1: `1.0000` / `1.0000` / `1.0000`
- Composition Value MAE: `0.158571` (count=7)
- Test Detection P/R/F1: `0.4590` / `1.0000` / `0.6292`
- Test Value MAE: `106.664286` (count=28)

### Article `3`
- Composition Detection P/R/F1: `1.0000` / `1.0000` / `1.0000`
- Composition Value MAE: `0.0` (count=5)
- Test Detection P/R/F1: `1.0000` / `1.0000` / `1.0000`
- Test Value MAE: `67.355556` (count=18)

### Article `4`
- Composition Detection P/R/F1: `1.0000` / `1.0000` / `1.0000`
- Composition Value MAE: `2.143744` (count=11)
- Test Detection P/R/F1: `1.0000` / `0.5000` / `0.6667`
- Test Value MAE: `0.0` (count=8)

### Article `5`
- Composition Detection P/R/F1: `1.0000` / `0.9500` / `0.9744`
- Composition Value MAE: `0.057895` (count=19)
- Test Detection P/R/F1: `0.8857` / `0.9688` / `0.9254`
- Test Value MAE: `204.675161` (count=31)

### Article `6`
- Composition Detection P/R/F1: `1.0000` / `1.0000` / `1.0000`
- Composition Value MAE: `0.011111` (count=9)
- Test Detection P/R/F1: `0.0000` / `0.0000` / `0.0000`
- Test Value MAE: `None` (count=0)
