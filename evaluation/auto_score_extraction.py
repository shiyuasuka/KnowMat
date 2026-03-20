#!/usr/bin/env python3
"""
Detailed auto scoring for extraction results vs ground truth.

Scoring dimensions:
1. Material alignment (best match within each article).
2. Composition element detection (precision / recall / F1).
3. Composition value error (MAE / exact rate / tolerance rate).
4. Performance test detection and value errors:
   - Overall
   - By temperature (K)
   - By property type

Usage:
  python auto_score_extraction.py
  python auto_score_extraction.py --drop-zero-elements --value-tol 0.1
"""

from __future__ import annotations

import argparse
import json
import math
import re
from collections import Counter, defaultdict
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Dict, List, Optional, Tuple


ALIASES = {
    "yieldstrengthys": "yield_strength",
    "yieldstrength": "yield_strength",
    "ultimatetensilestrengthuts": "ultimate_tensile_strength",
    "ultimatetensilestrength": "ultimate_tensile_strength",
    "uniformelongationufe": "uniform_elongation",
    "uniformelongation": "uniform_elongation",
    "totalelongationte": "total_elongation",
    "totalelongation": "total_elongation",
    "youngsmodulus": "youngs_modulus",
    "fracturestrain": "fracture_strain",
    "latticeparameter": "lattice_parameter",
    "locallatticestrain": "local_lattice_strain",
    "yieldstrengthcompressive": "yield_strength_compressive",
    "ultimatestrengthcompressive": "ultimate_strength_compressive",
    "elongationcompressive": "elongation_compressive",
}


@dataclass
class TestRecord:
    temp_k: Optional[float]
    property_type: str
    unit: str
    value: Optional[float]
    raw_property_type: Optional[str]
    raw_unit: Optional[str]

    @property
    def key(self) -> Tuple[str, str, str]:
        return (temp_key(self.temp_k), self.property_type, self.unit)


@dataclass
class MaterialRecord:
    mat_id: str
    formula: Optional[str]
    alloy_name: Optional[str]
    composition: Dict[str, float]
    tests: List[TestRecord]


def to_float(v) -> Optional[float]:
    try:
        if v is None:
            return None
        if isinstance(v, str) and not v.strip():
            return None
        return float(v)
    except (ValueError, TypeError):
        return None


def normalize_property_type(value: Optional[str]) -> str:
    if not value:
        return "unknown"
    # Normalize common styles: CamelCase, snake_case, and mixed punctuations.
    value = re.sub(r"([a-z])([A-Z])", r"\1_\2", value)
    value = value.strip().lower().replace("-", "_").replace("/", "_")
    cleaned = re.sub(r"[^a-z0-9]+", "", value)
    return ALIASES.get(cleaned, cleaned or "unknown")


def normalize_unit(value: Optional[str]) -> str:
    if not value:
        return "unknown"
    unit = value.strip().lower()
    unit = unit.replace("μ", "u").replace("µ", "u")
    unit = re.sub(r"\s+", "", unit)
    return unit or "unknown"


def normalize_temp(value) -> Optional[float]:
    t = to_float(value)
    if t is None:
        return None
    return round(t, 6)


def temp_key(value: Optional[float]) -> str:
    if value is None:
        return "null"
    if abs(value - int(value)) < 1e-9:
        return str(int(value))
    return f"{value:.6f}".rstrip("0").rstrip(".")


def temp_key_sort_key(k: str) -> Tuple[int, float, str]:
    if k == "null":
        return (0, -1.0, k)
    try:
        return (1, float(k), k)
    except ValueError:
        return (2, 0.0, k)


def load_materials(path: Path, drop_zero_elements: bool, zero_eps: float) -> List[MaterialRecord]:
    with path.open("r", encoding="utf-8") as f:
        data = json.load(f)

    out: List[MaterialRecord] = []
    for i, m in enumerate(data.get("Materials", [])):
        comp: Dict[str, float] = {}
        raw_comp = m.get("Composition_JSON") or {}
        for k, v in raw_comp.items():
            fv = to_float(v)
            if fv is None:
                continue
            if drop_zero_elements and abs(fv) <= zero_eps:
                continue
            comp[k] = fv

        tests: List[TestRecord] = []
        for sample in m.get("Processed_Samples", []):
            for t in sample.get("Performance_Tests", []):
                tests.append(
                    TestRecord(
                        temp_k=normalize_temp(t.get("Test_Temperature_K")),
                        property_type=normalize_property_type(t.get("Property_Type")),
                        unit=normalize_unit(t.get("Property_Unit")),
                        value=to_float(t.get("Property_Value")),
                        raw_property_type=t.get("Property_Type"),
                        raw_unit=t.get("Property_Unit"),
                    )
                )

        out.append(
            MaterialRecord(
                mat_id=str(m.get("Mat_ID", f"M{i+1:03d}")),
                formula=m.get("Formula_Normalized"),
                alloy_name=m.get("Alloy_Name_Raw"),
                composition=comp,
                tests=tests,
            )
        )
    return out


def composition_cost(gt: MaterialRecord, pred: MaterialRecord) -> float:
    gk = set(gt.composition)
    pk = set(pred.composition)
    missing = len(gk - pk)
    extra = len(pk - gk)
    value_err = sum(abs(gt.composition[e] - pred.composition[e]) for e in (gk & pk))
    return (missing + extra) * 100.0 + value_err


def tests_signature_cost(gt: MaterialRecord, pred: MaterialRecord) -> float:
    g = Counter((t.temp_k, t.property_type, t.unit) for t in gt.tests)
    p = Counter((t.temp_k, t.property_type, t.unit) for t in pred.tests)
    keys = set(g) | set(p)
    mismatch = sum(abs(g[k] - p[k]) for k in keys)
    return mismatch * 2.0


def material_pair_cost(gt: MaterialRecord, pred: MaterialRecord, match_by_tests: bool) -> float:
    base = composition_cost(gt, pred)
    if match_by_tests:
        base += tests_signature_cost(gt, pred)
    return base


def unmatched_gt_cost(gt: MaterialRecord) -> float:
    return len(gt.composition) * 120.0 + len(gt.tests) * 3.0 + 300.0


def unmatched_pred_cost(pred: MaterialRecord) -> float:
    return len(pred.composition) * 120.0 + len(pred.tests) * 3.0 + 300.0


def best_material_matching(
    gts: List[MaterialRecord], preds: List[MaterialRecord], match_by_tests: bool
) -> List[Tuple[Optional[int], Optional[int], float]]:
    n = len(gts)
    m = len(preds)

    @lru_cache(None)
    def dp(i: int, used_mask: int) -> Tuple[float, Tuple[Tuple[Optional[int], Optional[int], float], ...]]:
        if i >= n:
            remaining_cost = 0.0
            assignments: List[Tuple[Optional[int], Optional[int], float]] = []
            for j in range(m):
                if (used_mask >> j) & 1:
                    continue
                c = unmatched_pred_cost(preds[j])
                remaining_cost += c
                assignments.append((None, j, c))
            return remaining_cost, tuple(assignments)

        best_cost = math.inf
        best_assign: Tuple[Tuple[Optional[int], Optional[int], float], ...] = ()

        c_unmatched = unmatched_gt_cost(gts[i])
        tail_cost, tail_assign = dp(i + 1, used_mask)
        total = c_unmatched + tail_cost
        if total < best_cost:
            best_cost = total
            best_assign = ((i, None, c_unmatched),) + tail_assign

        for j in range(m):
            if (used_mask >> j) & 1:
                continue
            c_pair = material_pair_cost(gts[i], preds[j], match_by_tests=match_by_tests)
            tail_cost, tail_assign = dp(i + 1, used_mask | (1 << j))
            total = c_pair + tail_cost
            if total < best_cost:
                best_cost = total
                best_assign = ((i, j, c_pair),) + tail_assign

        return best_cost, best_assign

    _, result = dp(0, 0)
    return sorted(result, key=lambda x: (10**6 if x[0] is None else x[0], 10**6 if x[1] is None else x[1]))


def min_abs_matching(gt_vals: List[float], pred_vals: List[float]) -> List[Tuple[float, float, float]]:
    if not gt_vals or not pred_vals:
        return []

    a = list(gt_vals)
    b = list(pred_vals)
    if len(a) <= len(b):
        small, large = a, b
        reverse = False
    else:
        small, large = b, a
        reverse = True

    n = len(small)
    m = len(large)

    @lru_cache(None)
    def dp(i: int, used_mask: int) -> Tuple[float, Tuple[Tuple[float, float, float], ...]]:
        if i >= n:
            return 0.0, tuple()
        best_cost = math.inf
        best_pairs: Tuple[Tuple[float, float, float], ...] = tuple()
        for j in range(m):
            if (used_mask >> j) & 1:
                continue
            err = abs(small[i] - large[j])
            tail_cost, tail_pairs = dp(i + 1, used_mask | (1 << j))
            total = err + tail_cost
            if total < best_cost:
                best_cost = total
                if reverse:
                    pair = (large[j], small[i], err)
                else:
                    pair = (small[i], large[j], err)
                best_pairs = (pair,) + tail_pairs
        return best_cost, best_pairs

    _, pairs = dp(0, 0)
    return list(pairs)


def min_temp_diff(gt_temp: Optional[float], pred_temp: Optional[float], allow_celsius_shift: bool) -> Optional[float]:
    if gt_temp is None and pred_temp is None:
        return 0.0
    if gt_temp is None or pred_temp is None:
        return None

    diffs = [abs(gt_temp - pred_temp)]
    if allow_celsius_shift:
        # If one side is in Celsius and the other in Kelvin, allow matching via +273.15.
        diffs.append(abs(gt_temp - (pred_temp + 273.15)))
        diffs.append(abs((gt_temp + 273.15) - pred_temp))
    return min(diffs)


def match_tests_group(
    g_tests: List[TestRecord],
    p_tests: List[TestRecord],
    temp_tol: float,
    allow_celsius_shift: bool,
) -> Tuple[List[Tuple[int, int, float, float]], List[int], List[int]]:
    n = len(g_tests)
    m = len(p_tests)

    @lru_cache(None)
    def dp(i: int, used_mask: int) -> Tuple[float, Tuple[Tuple[int, int, float, float], ...], Tuple[int, ...]]:
        if i >= n:
            return 0.0, tuple(), tuple()

        # Option 1: leave this gt unmatched (FN)
        best_cost, best_pairs, best_unmatched = dp(i + 1, used_mask)
        best_cost += 1000.0
        best_unmatched = (i,) + best_unmatched

        # Option 2: match to any compatible pred
        for j in range(m):
            if (used_mask >> j) & 1:
                continue

            tdiff = min_temp_diff(g_tests[i].temp_k, p_tests[j].temp_k, allow_celsius_shift)
            if tdiff is None:
                # One side missing temp: allow but apply moderate penalty.
                tpenalty = 10.0
            else:
                if tdiff > temp_tol:
                    continue
                tpenalty = tdiff

            v1 = g_tests[i].value if g_tests[i].value is not None else 0.0
            v2 = p_tests[j].value if p_tests[j].value is not None else 0.0
            verr = abs(v1 - v2)
            # Matching priority is count first; errors are tie-breakers.
            pair_cost = tpenalty + verr / 1000.0

            tail_cost, tail_pairs, tail_unmatched = dp(i + 1, used_mask | (1 << j))
            total = pair_cost + tail_cost
            if total < best_cost:
                best_cost = total
                best_pairs = ((i, j, tdiff if tdiff is not None else -1.0, verr),) + tail_pairs
                best_unmatched = tail_unmatched

        return best_cost, best_pairs, best_unmatched

    _, pairs, unmatched_gt = dp(0, 0)
    used_pred = {j for _, j, _, _ in pairs}
    unmatched_pred = [j for j in range(m) if j not in used_pred]
    return list(pairs), list(unmatched_gt), unmatched_pred


def update_detection(stats: Dict[str, int], tp: int, fp: int, fn: int) -> None:
    stats["tp"] += tp
    stats["fp"] += fp
    stats["fn"] += fn


def update_value_stats(stats: Dict[str, float], errs: List[float], value_tol: float) -> None:
    for e in errs:
        stats["count"] += 1
        stats["sum_abs_err"] += e
        stats["max_abs_err"] = max(stats["max_abs_err"], e)
        if e == 0:
            stats["exact"] += 1
        if e <= value_tol:
            stats["within_tol"] += 1


def finalize_detection(stats: Dict[str, int]) -> Dict[str, float]:
    tp = stats["tp"]
    fp = stats["fp"]
    fn = stats["fn"]
    p = tp / (tp + fp) if (tp + fp) else 0.0
    r = tp / (tp + fn) if (tp + fn) else 0.0
    f1 = 2 * p * r / (p + r) if (p + r) else 0.0
    return {"tp": tp, "fp": fp, "fn": fn, "precision": p, "recall": r, "f1": f1}


def finalize_value(stats: Dict[str, float]) -> Dict[str, float]:
    c = int(stats["count"])
    mae = stats["sum_abs_err"] / c if c else None
    return {
        "count": c,
        "mae": mae,
        "max_abs_err": (stats["max_abs_err"] if c else None),
        "exact_rate": (stats["exact"] / c if c else None),
        "within_tol_rate": (stats["within_tol"] / c if c else None),
    }


def round_floats(obj, ndigits: int = 6):
    if isinstance(obj, float):
        return round(obj, ndigits)
    if isinstance(obj, list):
        return [round_floats(x, ndigits) for x in obj]
    if isinstance(obj, dict):
        return {k: round_floats(v, ndigits) for k, v in obj.items()}
    return obj


def build_markdown_report(report: Dict, output_json_path: Path) -> str:
    lines: List[str] = []
    lines.append("# Extraction Scoring Report")
    lines.append("")
    lines.append(f"- Groundtruth dir: `{report['config']['groundtruth_dir']}`")
    lines.append(f"- Output dir: `{report['config']['output_dir']}`")
    lines.append(f"- Drop zero elements: `{report['config']['drop_zero_elements']}`")
    lines.append(f"- Value tolerance: `{report['config']['value_tol']}`")
    lines.append(f"- Temp tolerance (K): `{report['config']['temp_tol']}`")
    lines.append(f"- Allow Celsius shift: `{report['config']['allow_celsius_shift']}`")
    lines.append(f"- Ignore test unit: `{report['config']['ignore_test_unit']}`")
    lines.append(f"- Material match uses tests: `{report['config']['material_match_use_tests']}`")
    lines.append(f"- JSON report: `{output_json_path}`")
    lines.append("")

    ov = report["overall"]
    lines.append("## Overall")
    lines.append("")
    lines.append("### Composition Element Detection")
    lines.append("")
    lines.append(
        f"- TP/FP/FN: `{ov['composition_detection']['tp']}` / `{ov['composition_detection']['fp']}` / `{ov['composition_detection']['fn']}`"
    )
    lines.append(
        f"- Precision/Recall/F1: `{ov['composition_detection']['precision']:.4f}` / `{ov['composition_detection']['recall']:.4f}` / `{ov['composition_detection']['f1']:.4f}`"
    )
    lines.append("")
    lines.append("### Composition Value Error")
    lines.append("")
    cv = ov["composition_values"]
    lines.append(f"- Count: `{cv['count']}`")
    lines.append(f"- MAE: `{cv['mae']}`")
    lines.append(f"- Max Abs Error: `{cv['max_abs_err']}`")
    lines.append(f"- Exact Rate: `{cv['exact_rate']}`")
    lines.append(f"- Within Tol Rate: `{cv['within_tol_rate']}`")
    lines.append("")
    lines.append("### Performance Test Detection")
    lines.append("")
    td = ov["test_detection"]
    lines.append(f"- TP/FP/FN: `{td['tp']}` / `{td['fp']}` / `{td['fn']}`")
    lines.append(
        f"- Precision/Recall/F1: `{td['precision']:.4f}` / `{td['recall']:.4f}` / `{td['f1']:.4f}`"
    )
    lines.append("")
    lines.append("### Performance Test Value Error")
    lines.append("")
    tv = ov["test_values"]
    lines.append(f"- Count: `{tv['count']}`")
    lines.append(f"- MAE: `{tv['mae']}`")
    lines.append(f"- Max Abs Error: `{tv['max_abs_err']}`")
    lines.append(f"- Exact Rate: `{tv['exact_rate']}`")
    lines.append(f"- Within Tol Rate: `{tv['within_tol_rate']}`")
    lines.append("")

    lines.append("## By Temperature (K)")
    lines.append("")
    lines.append("| Temp_K | Test TP | Test FP | Test FN | Test F1 | Value Count | Value MAE | Value MaxErr |")
    lines.append("|---:|---:|---:|---:|---:|---:|---:|---:|")
    by_temp = report["by_temperature"]
    for k in sorted(by_temp.keys(), key=temp_key_sort_key):
        item = by_temp[k]
        d = item["detection"]
        v = item["values"]
        lines.append(
            f"| {k} | {d['tp']} | {d['fp']} | {d['fn']} | {d['f1']:.4f} | {v['count']} | {v['mae']} | {v['max_abs_err']} |"
        )
    lines.append("")

    lines.append("## By Property Type")
    lines.append("")
    lines.append("| Property | Test TP | Test FP | Test FN | Test F1 | Value Count | Value MAE | Value MaxErr |")
    lines.append("|---|---:|---:|---:|---:|---:|---:|---:|")
    by_prop = report["by_property"]
    for k in sorted(by_prop):
        item = by_prop[k]
        d = item["detection"]
        v = item["values"]
        lines.append(
            f"| {k} | {d['tp']} | {d['fp']} | {d['fn']} | {d['f1']:.4f} | {v['count']} | {v['mae']} | {v['max_abs_err']} |"
        )
    lines.append("")

    lines.append("## Per Article")
    lines.append("")
    for a in report["articles"]:
        lines.append(f"### Article `{a['article_id']}`")
        if a.get("status") == "missing_output":
            lines.append("- Missing output extraction file.")
            lines.append("")
            continue
        cd = a["composition_detection"]
        cv = a["composition_values"]
        td = a["test_detection"]
        tv = a["test_values"]
        lines.append(
            f"- Composition Detection P/R/F1: `{cd['precision']:.4f}` / `{cd['recall']:.4f}` / `{cd['f1']:.4f}`"
        )
        lines.append(f"- Composition Value MAE: `{cv['mae']}` (count={cv['count']})")
        lines.append(f"- Test Detection P/R/F1: `{td['precision']:.4f}` / `{td['recall']:.4f}` / `{td['f1']:.4f}`")
        lines.append(f"- Test Value MAE: `{tv['mae']}` (count={tv['count']})")
        lines.append("")

    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="Detailed scoring for extraction results.")
    parser.add_argument("--groundtruth-dir", default="groundtruth", help="Groundtruth directory path.")
    parser.add_argument("--output-dir", default="output", help="Output directory path.")
    parser.add_argument("--report-json", default="scoring_report.json", help="Output JSON report path.")
    parser.add_argument("--report-md", default="scoring_summary.md", help="Output Markdown report path.")
    parser.add_argument(
        "--value-tol",
        type=float,
        default=0.1,
        help="Tolerance for counting value as within tolerance.",
    )
    parser.add_argument(
        "--drop-zero-elements",
        action="store_true",
        help="Ignore near-zero elements in composition (for Mo=0 style formatting differences).",
    )
    parser.add_argument(
        "--zero-eps",
        type=float,
        default=1e-12,
        help="Absolute threshold used with --drop-zero-elements.",
    )
    parser.add_argument(
        "--temp-tol",
        type=float,
        default=1.0,
        help="Temperature tolerance (K) for test-item matching.",
    )
    parser.add_argument(
        "--allow-celsius-shift",
        action="store_true",
        help="Allow Celsius/Kelvin conversion when matching test temperatures.",
    )
    parser.add_argument(
        "--ignore-test-unit",
        action="store_true",
        help="Match tests by property and temperature even if units differ.",
    )
    parser.add_argument(
        "--material-match-use-tests",
        action="store_true",
        help="Include test-signature cost when matching materials (default: composition-only matching).",
    )
    args = parser.parse_args()

    gt_dir = Path(args.groundtruth_dir)
    out_dir = Path(args.output_dir)
    report_json = Path(args.report_json)
    report_md = Path(args.report_md)

    gt_files = sorted(gt_dir.glob("*-data.json"))
    if not gt_files:
        raise SystemExit(f"No groundtruth files found in: {gt_dir}")

    overall_comp_det = {"tp": 0, "fp": 0, "fn": 0}
    overall_comp_val = {"count": 0, "sum_abs_err": 0.0, "max_abs_err": 0.0, "exact": 0, "within_tol": 0}
    overall_test_det = {"tp": 0, "fp": 0, "fn": 0}
    overall_test_val = {"count": 0, "sum_abs_err": 0.0, "max_abs_err": 0.0, "exact": 0, "within_tol": 0}

    by_temp_det = defaultdict(lambda: {"tp": 0, "fp": 0, "fn": 0})
    by_temp_val = defaultdict(lambda: {"count": 0, "sum_abs_err": 0.0, "max_abs_err": 0.0, "exact": 0, "within_tol": 0})
    by_prop_det = defaultdict(lambda: {"tp": 0, "fp": 0, "fn": 0})
    by_prop_val = defaultdict(lambda: {"count": 0, "sum_abs_err": 0.0, "max_abs_err": 0.0, "exact": 0, "within_tol": 0})

    article_reports = []

    for gt_path in gt_files:
        m = re.match(r"(\d+)-data\.json$", gt_path.name)
        if not m:
            continue
        article_id = m.group(1)
        out_candidates = sorted(out_dir.glob(f"{article_id}-*/*_extraction.json"))

        if not out_candidates:
            article_reports.append({"article_id": article_id, "status": "missing_output", "groundtruth_file": str(gt_path)})
            continue

        out_path = out_candidates[0]
        gt_materials = load_materials(gt_path, args.drop_zero_elements, args.zero_eps)
        pred_materials = load_materials(out_path, args.drop_zero_elements, args.zero_eps)

        matches = best_material_matching(
            gt_materials,
            pred_materials,
            match_by_tests=args.material_match_use_tests,
        )

        art_comp_det = {"tp": 0, "fp": 0, "fn": 0}
        art_comp_val = {"count": 0, "sum_abs_err": 0.0, "max_abs_err": 0.0, "exact": 0, "within_tol": 0}
        art_test_det = {"tp": 0, "fp": 0, "fn": 0}
        art_test_val = {"count": 0, "sum_abs_err": 0.0, "max_abs_err": 0.0, "exact": 0, "within_tol": 0}

        pair_details = []

        for gi, pi, pair_cost in matches:
            gt_m = gt_materials[gi] if gi is not None else None
            pred_m = pred_materials[pi] if pi is not None else None

            g_comp = gt_m.composition if gt_m else {}
            p_comp = pred_m.composition if pred_m else {}

            g_keys = set(g_comp)
            p_keys = set(p_comp)
            inter = g_keys & p_keys

            comp_tp = len(inter)
            comp_fp = len(p_keys - g_keys)
            comp_fn = len(g_keys - p_keys)
            update_detection(art_comp_det, comp_tp, comp_fp, comp_fn)
            update_detection(overall_comp_det, comp_tp, comp_fp, comp_fn)

            comp_errs = [abs(g_comp[e] - p_comp[e]) for e in inter]
            update_value_stats(art_comp_val, comp_errs, args.value_tol)
            update_value_stats(overall_comp_val, comp_errs, args.value_tol)

            g_tests = [t for t in (gt_m.tests if gt_m else []) if t.value is not None]
            p_tests = [t for t in (pred_m.tests if pred_m else []) if t.value is not None]

            def test_group_key(t: TestRecord) -> Tuple[str, str]:
                if args.ignore_test_unit:
                    return (t.property_type, "")
                return (t.property_type, t.unit)

            g_groups: Dict[Tuple[str, str], List[TestRecord]] = defaultdict(list)
            p_groups: Dict[Tuple[str, str], List[TestRecord]] = defaultdict(list)
            for t in g_tests:
                g_groups[test_group_key(t)].append(t)
            for t in p_tests:
                p_groups[test_group_key(t)].append(t)

            all_group_keys = sorted(set(g_groups) | set(p_groups))
            pair_test_detail = []

            for gk in all_group_keys:
                prop, unit = gk
                gt_list = g_groups.get(gk, [])
                pred_list = p_groups.get(gk, [])

                pairs, unmatched_gt_idx, unmatched_pred_idx = match_tests_group(
                    gt_list,
                    pred_list,
                    temp_tol=args.temp_tol,
                    allow_celsius_shift=args.allow_celsius_shift,
                )

                tp = len(pairs)
                fp = len(unmatched_pred_idx)
                fn = len(unmatched_gt_idx)
                update_detection(art_test_det, tp, fp, fn)
                update_detection(overall_test_det, tp, fp, fn)

                # Matched pairs contribute TP and value errors, credited to GT temperature bins.
                value_pairs = []
                for gi2, pi2, tdiff, verr in pairs:
                    gt_item = gt_list[gi2]
                    pred_item = pred_list[pi2]
                    tk = temp_key(gt_item.temp_k)
                    update_detection(by_temp_det[tk], 1, 0, 0)
                    update_detection(by_prop_det[prop], 1, 0, 0)

                    errs = [verr]
                    update_value_stats(art_test_val, errs, args.value_tol)
                    update_value_stats(overall_test_val, errs, args.value_tol)
                    update_value_stats(by_temp_val[tk], errs, args.value_tol)
                    update_value_stats(by_prop_val[prop], errs, args.value_tol)

                    value_pairs.append(
                        {
                            "gt": gt_item.value,
                            "pred": pred_item.value,
                            "abs_err": verr,
                            "gt_temp_k": temp_key(gt_item.temp_k),
                            "pred_temp_k": temp_key(pred_item.temp_k),
                            "temp_diff_k": tdiff,
                        }
                    )

                # Unmatched GT contributes FN at GT bins.
                for idx in unmatched_gt_idx:
                    gt_item = gt_list[idx]
                    tk = temp_key(gt_item.temp_k)
                    update_detection(by_temp_det[tk], 0, 0, 1)
                    update_detection(by_prop_det[prop], 0, 0, 1)

                # Unmatched Pred contributes FP at Pred bins.
                for idx in unmatched_pred_idx:
                    pred_item = pred_list[idx]
                    tk = temp_key(pred_item.temp_k)
                    update_detection(by_temp_det[tk], 0, 1, 0)
                    update_detection(by_prop_det[prop], 0, 1, 0)

                pair_test_detail.append(
                    {
                        "property_type": prop,
                        "unit": unit if unit else ("*" if args.ignore_test_unit else ""),
                        "gt_count": len(gt_list),
                        "pred_count": len(pred_list),
                        "tp": tp,
                        "fp": fp,
                        "fn": fn,
                        "unmatched_gt": [
                            {"temp_k": temp_key(gt_list[idx].temp_k), "value": gt_list[idx].value}
                            for idx in unmatched_gt_idx
                        ],
                        "unmatched_pred": [
                            {"temp_k": temp_key(pred_list[idx].temp_k), "value": pred_list[idx].value}
                            for idx in unmatched_pred_idx
                        ],
                        "value_pairs": value_pairs,
                    }
                )

            pair_details.append(
                {
                    "gt_material": (
                        {
                            "mat_id": gt_m.mat_id,
                            "formula": gt_m.formula,
                            "alloy_name": gt_m.alloy_name,
                        }
                        if gt_m
                        else None
                    ),
                    "pred_material": (
                        {
                            "mat_id": pred_m.mat_id,
                            "formula": pred_m.formula,
                            "alloy_name": pred_m.alloy_name,
                        }
                        if pred_m
                        else None
                    ),
                    "pair_cost": pair_cost,
                    "composition": {
                        "tp": comp_tp,
                        "fp": comp_fp,
                        "fn": comp_fn,
                        "missing_elements": sorted(g_keys - p_keys),
                        "extra_elements": sorted(p_keys - g_keys),
                        "value_errors": [
                            {
                                "element": e,
                                "gt": g_comp[e],
                                "pred": p_comp[e],
                                "abs_err": abs(g_comp[e] - p_comp[e]),
                            }
                            for e in sorted(inter)
                            if abs(g_comp[e] - p_comp[e]) > 0
                        ],
                    },
                    "tests": pair_test_detail,
                }
            )

        article_reports.append(
            {
                "article_id": article_id,
                "status": "ok",
                "groundtruth_file": str(gt_path),
                "output_file": str(out_path),
                "material_match_count": len(matches),
                "composition_detection": finalize_detection(art_comp_det),
                "composition_values": finalize_value(art_comp_val),
                "test_detection": finalize_detection(art_test_det),
                "test_values": finalize_value(art_test_val),
                "material_pairs": pair_details,
            }
        )

    by_temperature = {}
    for k in sorted(by_temp_det.keys(), key=temp_key_sort_key):
        by_temperature[k] = {
            "detection": finalize_detection(by_temp_det[k]),
            "values": finalize_value(by_temp_val[k]),
        }

    by_property = {}
    for k in sorted(by_prop_det.keys()):
        by_property[k] = {
            "detection": finalize_detection(by_prop_det[k]),
            "values": finalize_value(by_prop_val[k]),
        }

    report = {
        "config": {
            "groundtruth_dir": str(gt_dir),
            "output_dir": str(out_dir),
            "value_tol": args.value_tol,
            "drop_zero_elements": args.drop_zero_elements,
            "zero_eps": args.zero_eps,
            "temp_tol": args.temp_tol,
            "allow_celsius_shift": args.allow_celsius_shift,
            "ignore_test_unit": args.ignore_test_unit,
            "material_match_use_tests": args.material_match_use_tests,
        },
        "overall": {
            "composition_detection": finalize_detection(overall_comp_det),
            "composition_values": finalize_value(overall_comp_val),
            "test_detection": finalize_detection(overall_test_det),
            "test_values": finalize_value(overall_test_val),
        },
        "by_temperature": by_temperature,
        "by_property": by_property,
        "articles": sorted(article_reports, key=lambda x: int(x["article_id"])),
    }

    report = round_floats(report, ndigits=6)

    with report_json.open("w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)

    md_text = build_markdown_report(report, report_json.resolve())
    with report_md.open("w", encoding="utf-8") as f:
        f.write(md_text)

    print(f"Done. JSON report: {report_json.resolve()}")
    print(f"Done. Markdown summary: {report_md.resolve()}")


if __name__ == "__main__":
    main()
