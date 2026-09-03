"""Split a multi-series line chart into single-curve images by color.

Multi-line charts are the hard case for VLM digitization: when several curves
share one plot the model confuses which line is which and routinely reads
*identical* coordinates for every series.  Rather than rely on the model to
disentangle them, we do it deterministically in code:

  1. Locate the plot area (largest rectangular contour = axes box).
  2. Mask the *colored* ink (saturated, mid-value pixels) — this is the curve
     ink, excluding the white background, grey gridlines and black axes/text.
  3. Cluster that ink by HUE (mapped onto the color wheel so it is robust to
     marker lightness) → one cluster per visually-distinct series color.
  4. For each cluster, render a copy of the ORIGINAL crop with every *other*
     series color erased to white, keeping axes / ticks / labels / legend /
     gridlines intact.  The result is N clean single-curve charts that a VLM
     can digitize reliably one at a time.

Known limits (documented, not silently swallowed):
  - Where curves overlap, the occluded segments of the rear curve are lost.
  - Black / grey dashed reference lines (e.g. an analytical "LEFM" line) have
    low saturation and live in the same value range as the axes, so they are
    NOT separable by color; they are handled best-effort as a single residual
    "dark" series only when they form a clear line inside the plot box.
  - Series whose colors are too close get merged (we prefer under-splitting to
    fabricating a series).

Never raises: any failure returns an empty list so the caller falls back to the
single-pass digitization path.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import List, NamedTuple, Tuple

logger = logging.getLogger(__name__)

# Saturation / value thresholds isolating colored curve ink from background,
# gridlines and black axes/text.  Tuned on real PaddleOCR chart crops.
# _SAT_MIN raised + an explicit near-grey exclusion (below) keep black/dark-grey
# reference lines (e.g. an analytical "LEFM" line, which is NOT color-separable)
# out of the colored-ink set, so they are never mis-split into a phantom series.
_SAT_MIN = 65
_VAL_MIN = 40
_VAL_MAX = 252
# A pixel whose max(R,G,B) - min(R,G,B) is below this is treated as achromatic
# (black / grey / white) regardless of its HSV saturation, and excluded from the
# colored ink.  Catches dark markers on black reference lines that survive the
# saturation gate due to JPEG/anti-aliasing color fringing.
_MIN_RGB_SPREAD = 35

# A hue peak must hold at least this fraction of all colored ink to count as a
# real series (absolute floor below), filtering anti-aliasing fringe.
_MIN_CLUSTER_FRAC = 0.025
_MIN_PEAK_ABS = 30
# Minimum absolute colored-ink pixels for the whole crop to be worth splitting.
_MIN_COLORED_PX = 150
# Two hue peaks closer than this (degrees) are merged into one series.
_HUE_MERGE_DEG = 14.0
# A peak smaller than this fraction of the LARGEST peak is treated as a stray
# minor color (e.g. a few odd marker pixels on a single-line chart) and dropped.
_MIN_REL_TO_MAX = 0.12
# Half-width (degrees) of the hue window assigned to each series peak.
_PEAK_WINDOW_DEG = 12.0


class SplitSeries(NamedTuple):
    """One extracted single-curve image plus a color hint for the VLM."""

    image_path: str
    color_rgb: Tuple[int, int, int]
    pixel_count: int


def _hue_distance(a: float, b: float) -> float:
    """Circular distance between two hues in degrees (OpenCV hue is 0-179)."""
    d = abs(a - b) % 180.0
    return min(d, 180.0 - d)


def _detect_series_hues(hue, max_series: int) -> List[float]:
    """Find the dominant series hues via histogram-peak detection.

    Scientific multi-line charts use a small palette of well-separated colors,
    one per series.  A coarse circular hue histogram therefore has a clean peak
    per series.  K-means on such data tends to merge close hues (green vs blue,
    ~20 deg apart) or over-split a single color, so we detect peaks directly:

      - bin hue into 5-degree bins (circular),
      - keep bins that are a local maximum and clear the absolute + fractional
        floor,
      - merge peaks closer than ``_HUE_MERGE_DEG``,
      - drop peaks smaller than ``_MIN_REL_TO_MAX`` of the largest (stray
        marker pixels on an otherwise single-line chart),
      - cap at ``max_series`` (largest peaks win).

    Returns a sorted list of peak hue centers (degrees, 0-180).
    """
    import numpy as np

    n_px = len(hue)
    nbins = 36  # 5 degrees per bin
    counts, _ = np.histogram(hue, bins=nbins, range=(0, 180))
    floor = max(_MIN_CLUSTER_FRAC * n_px, _MIN_PEAK_ABS)

    peaks: List[Tuple[float, int]] = []
    for i in range(nbins):
        c = counts[i]
        if c < floor:
            continue
        if c >= counts[(i - 1) % nbins] and c >= counts[(i + 1) % nbins]:
            peaks.append((i * 5 + 2.5, int(c)))

    if not peaks:
        return []

    peaks.sort(key=lambda p: -p[1])
    max_count = peaks[0][1]

    kept: List[float] = []
    for center, count in peaks:
        if count < _MIN_REL_TO_MAX * max_count:
            continue
        if any(_hue_distance(center, k) < _HUE_MERGE_DEG for k in kept):
            continue
        kept.append(center)
        if len(kept) >= max_series:
            break
    return sorted(kept)


def split_line_chart_by_color(
    image_path: str | Path,
    out_dir: str | Path,
    *,
    max_series: int = 6,
) -> List[SplitSeries]:
    """Split a multi-series line chart into per-series single-curve images.

    Parameters
    ----------
    image_path : path to the original chart crop.
    out_dir    : directory to write the per-series PNGs into (created if absent).
    max_series : hard cap on number of series to extract.

    Returns
    -------
    List of :class:`SplitSeries`, one per detected color series, sorted by
    pixel count (most prominent first).  Returns ``[]`` (caller should fall
    back to single-pass digitization) when the chart is single-color, has too
    little colored ink, or anything fails.
    """
    try:
        import cv2
        import numpy as np
    except ImportError:  # pragma: no cover - cv2 missing
        logger.warning("opencv/numpy unavailable; cannot split line chart.")
        return []

    try:
        src = Path(image_path)
        img = cv2.imread(str(src))
        if img is None:
            logger.debug("Cannot read chart image for splitting: %s", image_path)
            return []

        hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
        H, S, V = hsv[:, :, 0], hsv[:, :, 1], hsv[:, :, 2]
        color_mask = (S > _SAT_MIN) & (V > _VAL_MIN) & (V < _VAL_MAX)
        # Exclude achromatic pixels (black/grey/white): even when their HSV
        # saturation sneaks past the gate (JPEG/anti-alias fringing on a black
        # reference line's markers), a low RGB spread means they carry no real
        # color and must not seed a phantom series.
        rgb_spread = img.max(axis=2).astype(np.int16) - img.min(axis=2).astype(np.int16)
        color_mask &= rgb_spread >= _MIN_RGB_SPREAD
        n_colored = int(color_mask.sum())
        if n_colored < _MIN_COLORED_PX:
            logger.debug("Too little colored ink (%d px) to split: %s", n_colored, src.name)
            return []

        ys, xs = np.where(color_mask)
        hue = H[color_mask]
        colored_bgr = img[color_mask]

        peak_hues = _detect_series_hues(hue, max_series)
        if len(peak_hues) < 2:
            # Single-color (or indistinguishable) chart: not a multi-line split.
            logger.debug(
                "Only %d distinct series color(s) in %s; no split.",
                len(peak_hues), src.name,
            )
            return []

        # Assign every colored pixel to its nearest peak hue (circular). Pixels
        # farther than the peak window from all peaks are left unassigned (fringe).
        peaks_arr = np.asarray(peak_hues, dtype=np.float32)
        # diff[p, i] = circular distance from pixel i to peak p
        raw = np.abs(hue[None, :].astype(np.float32) - peaks_arr[:, None]) % 180.0
        dist = np.minimum(raw, 180.0 - raw)
        nearest = dist.argmin(axis=0)
        nearest_dist = dist.min(axis=0)
        assigned = nearest_dist <= _PEAK_WINDOW_DEG

        out = Path(out_dir)
        out.mkdir(parents=True, exist_ok=True)
        structure_mask = ~color_mask  # axes, text, gridlines, legend frame

        results: List[SplitSeries] = []
        for rank in range(len(peak_hues)):
            sel = assigned & (nearest == rank)
            n_sel = int(sel.sum())
            if n_sel < _MIN_PEAK_ABS:
                continue
            # Render: keep the full coordinate system (axes/ticks/labels/legend)
            # by painting back all non-colored structure, then overlay ONLY this
            # series' colored ink. The VLM sees one clean curve in full context.
            canvas = np.full_like(img, 255)
            canvas[structure_mask] = img[structure_mask]
            sy, sx = ys[sel], xs[sel]
            canvas[sy, sx] = colored_bgr[sel]

            mean_bgr = colored_bgr[sel].mean(axis=0)
            color_rgb = (int(mean_bgr[2]), int(mean_bgr[1]), int(mean_bgr[0]))

            dest = out / f"{src.stem}__series{rank}.png"
            cv2.imwrite(str(dest), canvas)
            results.append(SplitSeries(str(dest), color_rgb, n_sel))

        if len(results) < 2:
            return []

        results.sort(key=lambda r: -r.pixel_count)
        logger.info(
            "[line-split] %s → %d single-curve images (colored_px=%d)",
            src.name, len(results), n_colored,
        )
        return results
    except Exception as exc:  # never block the pipeline
        logger.warning("Line chart split failed for %s: %s", image_path, exc)
        return []


# Half-width (degrees) of the hue window used to re-select a series' ink when
# extracting its curve points from a split image.
_CURVE_HUE_WINDOW = 14


def _rgb_to_hue(color_rgb: Tuple[int, int, int]) -> int:
    """OpenCV hue (0-179) for an (R, G, B) triple."""
    import cv2
    import numpy as np

    r, g, b = color_rgb
    bgr = np.uint8([[[b, g, r]]])
    return int(cv2.cvtColor(bgr, cv2.COLOR_BGR2HSV)[0][0][0])


def _rdp_simplify(points, epsilon: float):
    """Ramer-Douglas-Peucker polyline simplification (keeps corners/extrema).

    ``points`` is a list of (x, y) in pixel space, sorted by x.  Returns a
    subset preserving the curve shape within ``epsilon`` pixels.
    """
    if len(points) < 3:
        return list(points)
    import numpy as np

    pts = np.asarray(points, dtype=float)
    start, end = pts[0], pts[-1]
    line = end - start
    line_len = float(np.hypot(*line))
    if line_len == 0.0:
        dists = np.hypot(pts[:, 0] - start[0], pts[:, 1] - start[1])
    else:
        # perpendicular distance of every point to the start-end line
        dists = np.abs(
            line[0] * (start[1] - pts[:, 1]) - (start[0] - pts[:, 0]) * line[1]
        ) / line_len
    idx = int(np.argmax(dists))
    if dists[idx] > epsilon:
        left = _rdp_simplify(points[: idx + 1], epsilon)
        right = _rdp_simplify(points[idx:], epsilon)
        return left[:-1] + right
    return [tuple(points[0]), tuple(points[-1])]


def extract_curve_points(
    image_path: str | Path,
    color_rgb: Tuple[int, int, int],
    *,
    max_points: int = 60,
) -> List[Tuple[int, int]]:
    """Extract a curve's points from a single-series image by column scanning.

    For each image column, find the target-color ink pixels and take their
    median row — yielding one (col, row) sample per column the curve covers.
    This is deterministic and dense (often hundreds of points), unlike asking a
    VLM to guess coordinates.  The dense trace is then simplified with RDP to at
    most ``max_points`` points, preserving corners and extrema.

    Returns pixel coordinates (origin top-left), sorted by column ascending.
    Empty list if the color is not found or anything fails.
    """
    try:
        import cv2
        import numpy as np

        img = cv2.imread(str(image_path))
        if img is None:
            return []
        hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
        H, S, V = hsv[:, :, 0], hsv[:, :, 1], hsv[:, :, 2]
        target_hue = _rgb_to_hue(color_rgb)
        dh = np.minimum(
            np.abs(H.astype(int) - target_hue),
            180 - np.abs(H.astype(int) - target_hue),
        )
        mask = (dh < _CURVE_HUE_WINDOW) & (S > _SAT_MIN) & (V > _VAL_MIN) & (V < _VAL_MAX)

        h, w = mask.shape
        # Legend swatch removal via connected components, but ONLY when a
        # dominant near-full-width blob exists (solid-line charts). Dashed /
        # scatter curves have no large component — skip filtering there and let
        # the DP path tracer below reject the legend geometrically.
        m8 = mask.astype(np.uint8)
        n_lbl, labels, stats, _ = cv2.connectedComponentsWithStats(m8, connectivity=8)
        if n_lbl > 2:
            widths = stats[1:, cv2.CC_STAT_WIDTH]
            max_w = int(widths.max()) if widths.size else 0
            if max_w >= 0.5 * w:  # a curve body spanning most of the width
                keep = np.zeros(n_lbl, dtype=bool)
                for lbl in range(1, n_lbl):
                    if stats[lbl, cv2.CC_STAT_WIDTH] >= 0.25 * max_w:
                        keep[lbl] = True
                mask = keep[labels]

        # Per-column candidate clusters: split each column's ink into contiguous
        # runs and take each run's median row. A column may yield several
        # candidates (curve body, a crossing line, a legend swatch overhead).
        col_cands: List[Tuple[int, List[float]]] = []
        for col in range(w):
            ink = np.where(mask[:, col])[0]
            if ink.size == 0:
                continue
            splits_idx = np.where(np.diff(ink) > 3)[0] + 1
            runs = np.split(ink, splits_idx)
            col_cands.append((col, [float(np.median(r)) for r in runs]))
        if len(col_cands) < 2:
            return [(c, int(cc[0])) for c, cc in col_cands]

        # DP shortest smooth path: pick one candidate per column minimising the
        # sum of |Δrow| between consecutive picks. This traces the curve body
        # and rejects legend swatches (selecting one would force a jump off the
        # curve and back — a large cost) and crossing-line bleed.
        INF = float("inf")
        cost = [[0.0 for _ in col_cands[0][1]]]
        back = [[-1] * len(col_cands[0][1])]
        for i in range(1, len(col_cands)):
            cur = col_cands[i][1]
            prev = col_cands[i - 1][1]
            prev_cost = cost[i - 1]
            row_cost: List[float] = []
            row_back: List[int] = []
            for y in cur:
                best, bj = INF, 0
                for j, py in enumerate(prev):
                    c = prev_cost[j] + abs(y - py)
                    if c < best:
                        best, bj = c, j
                row_cost.append(best)
                row_back.append(bj)
            cost.append(row_cost)
            back.append(row_back)
        last = cost[-1]
        k = int(min(range(len(last)), key=lambda t: last[t]))
        path: List[Tuple[int, int]] = []
        for i in range(len(col_cands) - 1, -1, -1):
            path.append((col_cands[i][0], int(round(col_cands[i][1][k]))))
            k = back[i][k]
            if k < 0:
                k = 0
        path.reverse()

        # Segment on large vertical jumps and keep the widest x-span segment.
        # A legend swatch the DP was forced through connects to the curve via
        # two big jumps (up to it, back down) forming a short isolated segment;
        # a genuine steep rise is gradual (many small steps) and stays in one
        # segment. Threshold scales with the curve's vertical extent.
        if len(path) >= 3:
            ys_all = [p[1] for p in path]
            vext = max(ys_all) - min(ys_all)
            jump_tol = max(25.0, 0.35 * vext)
            segs: List[List[Tuple[int, int]]] = [[path[0]]]
            for i in range(1, len(path)):
                if abs(path[i][1] - path[i - 1][1]) > jump_tol:
                    segs.append([path[i]])
                else:
                    segs[-1].append(path[i])
            if len(segs) > 1:
                path = max(segs, key=lambda s: (s[-1][0] - s[0][0], len(s)))

        cols = [p[0] for p in path]
        rows_est = [float(p[1]) for p in path]

        # Outlier rejection: drop columns whose row deviates sharply from a
        # rolling median of neighbours (residual marker blobs, bleed).
        arr = np.array(rows_est)
        k = max(3, len(arr) // 20 | 1)  # odd window ~5% of width
        pad = k // 2
        padded = np.pad(arr, pad, mode="edge")
        roll = np.array([np.median(padded[i:i + k]) for i in range(len(arr))])
        resid = np.abs(arr - roll)
        tol = max(6.0, 3.0 * float(np.median(resid)))
        keep = resid <= tol
        raw = [(cols[i], int(round(arr[i]))) for i in range(len(cols)) if keep[i]]
        if len(raw) < 2:
            raw = [(cols[i], int(round(arr[i]))) for i in range(len(cols))]

        # Simplify to <= max_points. Grow epsilon until the point budget is met.
        if len(raw) <= max_points:
            return raw
        span = raw[-1][0] - raw[0][0]
        eps = max(1.0, span / (max_points * 4.0))
        simplified = raw
        for _ in range(12):
            simplified = _rdp_simplify(raw, eps)
            if len(simplified) <= max_points:
                break
            eps *= 1.6
        return [(int(x), int(y)) for x, y in simplified]
    except Exception as exc:  # never block the pipeline
        logger.warning("Curve point extraction failed for %s: %s", image_path, exc)
        return []
