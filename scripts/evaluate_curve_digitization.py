"""Compare pure-code line-chart CSVs against ``曲线图带人工标注``.

The evaluator intentionally matches series globally (rather than by output
order), interpolates on the annotated X coordinates, and reports coverage and
RMSE separately.  Marker series are counted by point proximity; they are not
mixed into the continuous-trend RMSE.  Error-bar files are handled as three
related tracks (``upper``, ``average`` and ``lower``), so spread endpoints do
not inflate the ordinary marker counts.
"""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from typing import Iterable

import numpy as np

from knowmat.pdf.vector_chart_digitizer import digitize_vector_pdf


def _rows(rows: Iterable[list[str]]) -> np.ndarray:
    values = []
    for row in rows:
        if len(row) < 2:
            continue
        try:
            values.append((float(row[0]), float(row[1])))
        except (TypeError, ValueError):
            continue
    out = np.asarray(values, dtype=float)
    return out[np.argsort(out[:, 0])] if len(out) else out.reshape(0, 2)


def _read(path: Path) -> np.ndarray:
    return _rows(csv.reader(path.read_text(encoding="utf-8").splitlines()))


def _read_text(text: str) -> np.ndarray:
    return _rows(csv.reader(text.splitlines()))


def _read_spread(path: Path) -> dict[str, np.ndarray]:
    """Read ``x,y,index,side`` rows from an annotated spread CSV.

    The manual files intentionally have no header and use a fourth column to
    identify the upper/average/lower observation.  Be tolerant of a header or
    malformed rows: the evaluator must never make extraction fail merely
    because one annotation is incomplete.
    """

    groups: dict[str, list[tuple[float, float]]] = {"upper": [], "average": [], "lower": []}
    for row in csv.reader(path.read_text(encoding="utf-8").splitlines()):
        if len(row) < 4:
            continue
        try:
            x, y = float(row[0]), float(row[1])
        except (TypeError, ValueError):
            continue
        side = str(row[3]).strip().lower()
        if side in groups:
            groups[side].append((x, y))
    return {
        side: _rows(((str(x), str(y)) for x, y in values))
        for side, values in groups.items()
        if values
    }


def _spread_base(label: str) -> tuple[str, str] | None:
    """Return (base-label, side) for a predicted spread series label."""

    text = str(label or "").strip()
    for side in ("upper", "lower", "average"):
        suffix = f" {side}"
        if text.lower().endswith(suffix):
            return text[: -len(suffix)].rstrip(), side
    return None


def _match_cost(gt: np.ndarray, pred: np.ndarray) -> tuple[float, float] | None:
    if len(gt) < 3 or len(pred) < 2:
        return None
    lo = max(float(gt[:, 0].min()), float(pred[:, 0].min()))
    hi = min(float(gt[:, 0].max()), float(pred[:, 0].max()))
    mask = (gt[:, 0] >= lo) & (gt[:, 0] <= hi)
    if int(mask.sum()) < 3:
        return None
    estimate = np.interp(gt[mask, 0], pred[:, 0], pred[:, 1])
    rmse = float(np.sqrt(np.mean((estimate - gt[mask, 1]) ** 2)))
    return rmse, float(mask.mean())


def _assignment(cost: np.ndarray) -> list[tuple[int, int]]:
    try:
        from scipy.optimize import linear_sum_assignment

        rows, cols = linear_sum_assignment(cost)
        return list(zip(rows.tolist(), cols.tolist()))
    except Exception:
        pairs = []
        available = set(range(cost.shape[1]))
        for row in range(cost.shape[0]):
            if not available:
                break
            col = min(available, key=lambda c: float(cost[row, c]))
            pairs.append((row, col))
            available.remove(col)
        return pairs


def evaluate(root: Path) -> list[dict]:
    report = []
    for figure_dir in sorted(root.glob("Figure_*")):
        pdf = figure_dir / f"{figure_dir.name}.pdf"
        if not pdf.is_file():
            continue
        predicted = digitize_vector_pdf(pdf)
        gt_trends = []
        gt_boundaries = []
        gt_markers = []
        gt_spreads = []
        for csv_path in sorted(figure_dir.glob("*.csv")):
            if csv_path.name == "alldata.csv":
                continue
            lower_name = csv_path.name.lower()
            if "average value + spread of value" in lower_name:
                spread = _read_spread(csv_path)
                if spread:
                    gt_spreads.append((csv_path.name, spread))
                continue
            data = _read(csv_path)
            if "boundary" in lower_name:
                if len(data) >= 3:
                    gt_boundaries.append((csv_path.name, data))
            elif "trend curve" in lower_name or "stress rupture curve" in lower_name or "fatigue curve" in lower_name or "connecting curve" in lower_name or "stress-strain curve" in lower_name or "stress range curve" in lower_name:
                if len(data) >= 3:
                    gt_trends.append((csv_path.name, data))
            elif len(data):
                gt_markers.append((csv_path.name, data[:, :2]))
        if not gt_trends and not gt_boundaries and not gt_markers and not gt_spreads:
            continue
        pred_trends = []
        pred_boundaries = []
        pred_markers = []
        pred_spread_series = []
        if predicted:
            for series in predicted.get("series", []):
                data = _read_text(str(series.get("csv") or ""))
                if str(series.get("kind") or "").startswith("trend"):
                    pred_trends.append((str(series.get("label") or ""), data))
                elif str(series.get("kind") or "") == "boundary":
                    pred_boundaries.append((str(series.get("label") or ""), data[:, :2]))
                elif str(series.get("kind") or "") == "spread":
                    pred_spread_series.append((str(series.get("label") or ""), data[:, :2]))
                elif len(data):
                    pred_markers.append((str(series.get("label") or ""), data[:, :2]))

        costs = np.full((len(gt_trends), len(pred_trends)), 1e6)
        raw: dict[tuple[int, int], tuple[float, float]] = {}
        for i, (_, gt) in enumerate(gt_trends):
            for j, (_, pred) in enumerate(pred_trends):
                score = _match_cost(gt, pred)
                if score is None:
                    continue
                rmse, coverage = score
                costs[i, j] = rmse / max(float(np.ptp(gt[:, 1])), 1e-9) + (1.0 - coverage) * 0.5
                raw[i, j] = score
        matches = []
        for i, j in _assignment(costs):
            if (i, j) in raw:
                rmse, coverage = raw[i, j]
                matches.append({"gt": gt_trends[i][0], "pred": pred_trends[j][0], "rmse": rmse, "coverage": coverage})

        boundary_costs = np.full((len(gt_boundaries), len(pred_boundaries)), 1e6)
        boundary_raw: dict[tuple[int, int], tuple[float, float]] = {}
        for i, (_, gt) in enumerate(gt_boundaries):
            for j, (_, pred) in enumerate(pred_boundaries):
                score = _match_cost(gt, pred)
                if score is None:
                    continue
                rmse, coverage = score
                boundary_costs[i, j] = rmse / max(float(np.ptp(gt[:, 1])), 1e-9) + (1.0 - coverage) * 0.5
                boundary_raw[i, j] = score
        boundary_matches = []
        for i, j in _assignment(boundary_costs):
            if (i, j) not in boundary_raw:
                continue
            rmse, coverage = boundary_raw[i, j]
            boundary_matches.append({
                "gt": gt_boundaries[i][0],
                "pred": pred_boundaries[j][0],
                "rmse": rmse,
                "coverage": coverage,
            })

        # Match the average point of each annotated spread file to an ordinary
        # marker group.  The assignment is global, just like trend matching,
        # and gives us a stable base label for the corresponding endpoint
        # series (``<base> upper`` / ``<base> lower``).
        gt_spread_items = [
            (name, spread)
            for name, spread in gt_spreads
            if len(spread.get("average", ())) >= 1
        ]
        gt_spread_centres = [(name, spread["average"]) for name, spread in gt_spread_items]
        centre_costs = np.full((len(gt_spread_centres), len(pred_markers)), 1e6)
        centre_raw: dict[tuple[int, int], tuple[float, float]] = {}
        for i, (_, gt) in enumerate(gt_spread_centres):
            for j, (_, pred) in enumerate(pred_markers):
                score = _match_cost(gt, pred)
                if score is None:
                    # A sparse 2-point average still has value for a spread
                    # report; score it on nearest X/Y samples instead.
                    if len(gt) < 3 or len(pred) < 1:
                        continue
                    distances = []
                    for gx, gy in gt:
                        k = int(np.argmin(np.abs(pred[:, 0] - gx)))
                        distances.append(abs(float(pred[k, 1]) - float(gy)))
                    score = (float(np.sqrt(np.mean(np.square(distances)))), 1.0)
                rmse, coverage = score
                scale = max(float(np.ptp(gt[:, 1])), 1e-9)
                centre_costs[i, j] = rmse / scale + (1.0 - coverage) * 0.5
                centre_raw[i, j] = score
        centre_matches: list[dict] = []
        centre_assignment: dict[int, int] = {}
        for i, j in _assignment(centre_costs):
            if (i, j) not in centre_raw:
                continue
            rmse, coverage = centre_raw[i, j]
            centre_assignment[i] = j
            centre_matches.append({
                "gt": gt_spread_centres[i][0],
                "pred": pred_markers[j][0],
                "rmse": rmse,
                "coverage": coverage,
            })

        predicted_spread_groups: dict[str, dict[str, np.ndarray]] = {}
        for label, data in pred_spread_series:
            parsed = _spread_base(label)
            if parsed is None:
                continue
            base, side = parsed
            predicted_spread_groups.setdefault(base, {})[side] = data
        spread_matches: list[dict] = []
        for i, (gt_name, gt_spread) in enumerate(gt_spread_items):
            pred_index = centre_assignment.get(i)
            if pred_index is None:
                continue
            base = pred_markers[pred_index][0]
            pred_group = predicted_spread_groups.get(base, {})
            item: dict[str, object] = {"gt": gt_name, "pred": base}
            for side in ("upper", "lower"):
                gt_side = gt_spread.get(side)
                pred_side = pred_group.get(side)
                if gt_side is None or pred_side is None:
                    item[side] = None
                    continue
                score = _match_cost(gt_side, pred_side)
                if score is None:
                    item[side] = None
                    continue
                rmse, coverage = score
                item[side] = {"rmse": rmse, "coverage": coverage}
            spread_matches.append(item)

        spread_rmse_values = [
            float(item[side]["rmse"])
            for item in spread_matches
            for side in ("upper", "lower")
            if isinstance(item.get(side), dict) and item[side].get("rmse") is not None
        ]
        spread_coverage_values = [
            float(item[side]["coverage"])
            for item in spread_matches
            for side in ("upper", "lower")
            if isinstance(item.get(side), dict) and item[side].get("coverage") is not None
        ]
        report.append({
            "figure": figure_dir.name,
            "method": predicted.get("method") if predicted else None,
            "gt_trend_series": len(gt_trends),
            "pred_trend_series": len(pred_trends),
            "matched_trends": len(matches),
            "trend_rmse_mean": float(np.mean([m["rmse"] for m in matches])) if matches else None,
            "trend_coverage_mean": float(np.mean([m["coverage"] for m in matches])) if matches else None,
            "gt_boundary_series": len(gt_boundaries),
            "pred_boundary_series": len(pred_boundaries),
            "matched_boundaries": len(boundary_matches),
            "boundary_rmse_mean": float(np.mean([m["rmse"] for m in boundary_matches])) if boundary_matches else None,
            "boundary_coverage_mean": float(np.mean([m["coverage"] for m in boundary_matches])) if boundary_matches else None,
            "boundary_matches": boundary_matches,
            "gt_marker_series": len(gt_markers),
            "pred_marker_series": len(pred_markers),
            "pred_marker_points": int(sum(len(data) for _, data in pred_markers)),
            "gt_spread_series": len(gt_spreads),
            "pred_spread_series": len(pred_spread_series),
            "spread_center_matches": len(centre_matches),
            "spread_center_rmse_mean": float(np.mean([m["rmse"] for m in centre_matches])) if centre_matches else None,
            "spread_center_coverage_mean": float(np.mean([m["coverage"] for m in centre_matches])) if centre_matches else None,
            "spread_endpoint_rmse_mean": float(np.mean(spread_rmse_values)) if spread_rmse_values else None,
            "spread_endpoint_coverage_mean": float(np.mean(spread_coverage_values)) if spread_coverage_values else None,
            "spread_matches": spread_matches,
            "matches": matches,
        })
    return report


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path("曲线图带人工标注"))
    parser.add_argument("--json", type=Path)
    args = parser.parse_args()
    result = evaluate(args.root)
    payload = json.dumps(result, ensure_ascii=False, indent=2)
    if args.json:
        args.json.write_text(payload + "\n", encoding="utf-8")
    print(payload)


if __name__ == "__main__":
    main()
