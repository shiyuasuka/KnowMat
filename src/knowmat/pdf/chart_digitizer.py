"""Chart digitization for KnowMat (line/bar charts → structured VLM-digitized block).

Companion to :mod:`knowmat.pdf.figure_describer`.  Where ``figure_describer``
produces a *prose* description (200-500 words) used as soft context only, this
module produces a *structured* digitization that the extraction stage is
allowed to consume as data (under a dedicated whitelist rule keyed on the
``VLM-digitized`` marker).

Two-stage triage:
  1. Cheap routing on the OCR crop filename: PaddleOCR-VL names figure crops
     ``img_in_chart_box_*`` (plottable data) vs ``img_in_image_box_*``
     (micrograph/photo).  Only ``chart_box`` crops are candidates here.
  2. A VLM classification gate confirms the chart type and chooses an output
     contract:
       - bar/histogram  → CSV of discrete bar heights (directly readable)
       - line/scatter   → classification, axis calibration and labels only.
         Curve coordinates always come from deterministic vector/raster code;
         VLM-generated points are never accepted.
       - xrd/micrograph/other → skipped.

Like ``figure_describer`` it never raises — failures log and return empty so
the main pipeline is never blocked.  It reuses the VLM key pool / retry from
``figure_describer``.
"""

from __future__ import annotations

import base64
import json
import logging
import os
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

from knowmat.pdf.figure_describer import (
    _call_vlm_with_negative_cache,
    _get_vlm_pool,
    _image_media_type,
)

logger = logging.getLogger(__name__)

_CHART_BOX_TOKEN = "chart_box"
_IMAGE_BOX_TOKEN = "image_box"

# Enum of chart types the VLM may return; anything else is coerced to "other".
_VALID_TYPES = {"line", "bar", "xrd", "micrograph", "other"}

_CHART_PROMPT = """You are a scientific chart reader. Look at this cropped figure image.

STEP 1 — Classify. Output exactly one of these enum values for "type":
  line      : line chart / scatter plot with continuous numeric X and Y axes
  bar       : bar / column chart or histogram (categorical or binned X axis)
  xrd       : diffraction pattern / spectrum (intensity vs 2-theta, sharp peaks)
  micrograph: SEM/TEM/optical image, photo, schematic, or map (NOT a data plot)
  other     : phase diagram, flowchart, multi-panel mix, unreadable, or none of the above
If a crop contains MULTIPLE panels of different kinds, pick the single
dominant data-plot type if one clearly dominates, else "other".

STEP 2 — Read the chart according to its type. Two DIFFERENT contracts:

  IF type == "bar":
    Digitize to CSV (discrete, directly-readable bar heights).
    - One CSV table, first row = header.
    - Encode variable + unit in each header (e.g. "Lamellar_Thickness_nm").
    - Each series = its own column; preserve series labels.
    - One row per bar / bin. Read the bar heights off the Y axis.
    Put the CSV string in "csv". Set "line_summary" to null.

  IF type == "line":
    DO NOT output curve points, start/end values, extrema, or a per-point CSV.
    Reading coordinates off a continuous curve produces fabricated,
    evenly-spaced, over-smoothed data. Extract ONLY semantic labels into
    "line_summary":
    - x_axis / y_axis : variable + unit (e.g. "Temperature (C)")
    - series          : list of curve labels (e.g. ["theta=0", "theta=45"])
    - Also return axis_calibration using TWO well-separated labelled ticks per
      axis. pixel_x/pixel_y use the supplied image pixel coordinates (origin
      top-left). This calibration is used by code to map traced pixels; do not
      guess a tick that is not clearly readable.
    Set "csv" to "".

  IF type in (xrd, micrograph, other): digitizable=false, "csv"="", "line_summary"=null.

confidence = how readable/reliable your extraction is (0.0-1.0).

Return STRICT JSON only (no markdown fences, no prose, no <think>):
{
  "type": "line|bar|xrd|micrograph|other",
  "digitizable": true,
  "confidence": 0.0,
  "reason": "one short sentence",
  "csv": "",
  "axis_calibration": {
    "x_ref": [{"value": 0.0, "pixel_x": 0}, {"value": 1.0, "pixel_x": 100}],
    "y_ref": [{"value": 0.0, "pixel_y": 100}, {"value": 1.0, "pixel_y": 0}]
  },
  "line_summary": {
    "x_axis": "", "y_axis": "",
    "series": [{"label": ""}]
  }
}"""


_SINGLE_LINE_PROMPT = """You are a scientific chart reader. This image shows a line chart that has
been pre-processed so that exactly ONE data curve is drawn in a strong color
(approx RGB {rgb}); all other curves were removed. The axes, tick labels,
gridlines and legend are intact.

Your job: digitize the SINGLE highlighted curve into a point CSV.

Rules:
  - Read the axis tick labels to establish the real X and Y scales, then read
    the highlighted curve's value at a sequence of X positions.
  - Sample 8-20 points along the curve, spaced to capture its shape (denser
    where it bends, sparser where it is straight). Include the true endpoints.
  - Output a 2-column CSV: header row encodes variable + unit taken from the
    axis labels (e.g. "Crack_Length_mm,Stiffness_kN_per_mm"); then one row per
    point, in increasing X order.
  - Use ONLY the highlighted curve. Ignore faint anti-aliasing ghosts of other
    curves. If the curve is partly occluded/missing, sample only where visible.
  - Identify this curve's legend label (match the highlighted color to the
    legend). Put it in "label". If unreadable, use "".
  - confidence = how reliable your reading is (0.0-1.0).

Return STRICT JSON only (no markdown fences, no prose, no <think>):
{{
  "label": "",
  "x_axis": "",
  "y_axis": "",
  "confidence": 0.0,
  "csv": "X_header,Y_header\\n..."
}}"""


_AXIS_CALIB_PROMPT = """Image size: width={w}px height={h}px.
This is a line chart. Report ONLY the axis calibration — do NOT read the data curves.

For each axis pick TWO well-separated, clearly-labelled ticks and give the tick's
numeric value together with its pixel coordinate in THIS image (origin = top-left,
x grows right, y grows down). Also give the axis labels (with units) and, if a
legend is present, list EVERY legend entry with its text label AND the RGB color
of its line/marker sample (read the actual swatch color, 0-255 per channel).

Return STRICT JSON only (no markdown fences, no prose, no <think>):
{{
  "x_axis": "<label with unit>",
  "y_axis": "<label with unit>",
  "x_ref": [{{"value": <num>, "pixel_x": <int>}}, {{"value": <num>, "pixel_x": <int>}}],
  "y_ref": [{{"value": <num>, "pixel_y": <int>}}, {{"value": <num>, "pixel_y": <int>}}],
  "series": [{{"label": "<legend text>", "rgb": [<r>, <g>, <b>]}}, "..."]
}}"""


def _read_axis_calibration(
    image_path: Path,
    *,
    model: Optional[str] = None,
    api_key: Optional[str] = None,
    base_url: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    """Ask the VLM ONLY for axis calibration (tick value <-> pixel) + labels.

    This is the sole VLM step in the code-driven line digitization path: the
    model reads a handful of axis ticks (a stable, easy task) instead of trying
    to trace whole curves.  Returns the parsed dict or None on failure.
    """
    resolved = Path(image_path)
    if not resolved.is_file():
        return None
    b64 = _encode_image_base64(resolved)
    if b64 is None:
        return None

    _api_key = api_key or _get_vlm_pool().next_key()
    _base_url = (
        base_url
        or os.getenv("VLM_BASE_URL")
        or os.getenv("LLM_BASE_URL")
        or os.getenv("OPENAI_BASE_URL")
    )
    _model = model or os.getenv("VLM_MODEL") or os.getenv("LLM_MODEL", "")
    if not _api_key:
        return None

    try:
        import cv2

        img = cv2.imread(str(resolved))
        h, w = img.shape[:2]
    except Exception:
        return None

    media_type = _image_media_type(resolved)
    prompt = _AXIS_CALIB_PROMPT.format(w=w, h=h)
    messages = [
        {
            "role": "user",
            "content": [
                {"type": "image_url", "image_url": {"url": f"data:{media_type};base64,{b64}"}},
                {"type": "text", "text": prompt},
            ],
        },
    ]
    create_kwargs: dict = {
        "model": _model,
        "messages": messages,
        "max_tokens": 1024,
        "temperature": 0.1,
    }
    try:
        raw = _call_vlm_with_negative_cache(
            _base_url,
            create_kwargs,
            resolved,
            positive_validator=_is_valid_axis_calibration_json,
        )
    except Exception as exc:
        logger.warning("Axis calibration VLM call failed for %s: %s", image_path, exc)
        return None

    parsed = _parse_vlm_json(raw)
    if not isinstance(parsed, dict):
        return None
    return validate_axis_calibration(parsed)


def _validated_axis_refs(
    refs: Any,
    pixel_key: str,
) -> Optional[List[Dict[str, float]]]:
    """Return finite, distinct and monotonic tick references or ``None``."""
    import math

    if not isinstance(refs, list):
        return None
    points: List[tuple[float, float]] = []
    seen_pixels: set[float] = set()
    for row in refs:
        if not isinstance(row, dict):
            continue
        try:
            value = float(row.get("value"))
            pixel = float(row.get(pixel_key))
        except (TypeError, ValueError):
            continue
        if not math.isfinite(value) or not math.isfinite(pixel):
            continue
        if pixel in seen_pixels:
            return None
        seen_pixels.add(pixel)
        points.append((pixel, value))
    if len(points) < 2:
        return None

    points.sort(key=lambda pair: pair[0])
    value_deltas = [
        points[index + 1][1] - points[index][1]
        for index in range(len(points) - 1)
    ]
    if not (
        all(delta > 0 for delta in value_deltas)
        or all(delta < 0 for delta in value_deltas)
    ):
        return None
    return [
        {"value": value, pixel_key: pixel}
        for pixel, value in points
    ]


def validate_axis_calibration(
    calibration: Any,
) -> Optional[Dict[str, Any]]:
    """Validate an untrusted VLM pixel/value calibration.

    Both axes need at least two finite references. Pixel positions must be
    unique and the referenced values must change monotonically with pixel
    position, which rules out zero-slope and contradictory mappings.
    """
    if not isinstance(calibration, dict):
        return None
    x_refs = _validated_axis_refs(calibration.get("x_ref"), "pixel_x")
    y_refs = _validated_axis_refs(calibration.get("y_ref"), "pixel_y")
    if not x_refs or not y_refs:
        return None
    validated = dict(calibration)
    validated["x_ref"] = x_refs
    validated["y_ref"] = y_refs
    return validated


def _linear_mapper(refs: List[Dict[str, Any]], pixel_key: str):
    """Build pixel->value linear map from two calibration reference ticks.

    Returns a function f(pixel)->value, or None if the refs are unusable
    (fewer than 2 distinct pixel positions).
    """
    validated = _validated_axis_refs(refs, pixel_key)
    if not validated:
        return None
    # Use the most widely separated ticks to reduce pixel-rounding error.
    p1 = float(validated[0][pixel_key])
    v1 = float(validated[0]["value"])
    p2 = float(validated[-1][pixel_key])
    v2 = float(validated[-1]["value"])
    slope = (v2 - v1) / (p2 - p1)
    return lambda p: v1 + slope * (p - p1)


def _match_labels_by_color(
    split_colors: List[Tuple[int, int, int]],
    legend: List[Dict[str, Any]],
) -> List[Optional[str]]:
    """Assign a legend label to each split curve by nearest RGB color.

    Colors are the only reliable link between a color-split curve and its
    legend entry (vertical order breaks when the legend has entries that were
    never color-extracted, e.g. a black reference line).  Greedy nearest-color
    matching in RGB space; each legend entry is used at most once.

    Returns a label (or None) per curve, aligned with ``split_colors``.
    """
    parsed_legend: List[Tuple[str, Tuple[float, float, float]]] = []
    for entry in legend or []:
        if not isinstance(entry, dict):
            continue
        label = str(entry.get("label") or "").strip()
        rgb = entry.get("rgb")
        if not label or not isinstance(rgb, (list, tuple)) or len(rgb) < 3:
            continue
        try:
            parsed_legend.append((label, (float(rgb[0]), float(rgb[1]), float(rgb[2]))))
        except (TypeError, ValueError):
            continue

    labels: List[Optional[str]] = [None] * len(split_colors)
    if not parsed_legend:
        return labels

    # Build all (distance, curve_idx, legend_idx) pairs, assign greedily.
    pairs = []
    for ci, c in enumerate(split_colors):
        for li, (_, lc) in enumerate(parsed_legend):
            dist = (c[0] - lc[0]) ** 2 + (c[1] - lc[1]) ** 2 + (c[2] - lc[2]) ** 2
            pairs.append((dist, ci, li))
    pairs.sort()
    used_curve: set = set()
    used_legend: set = set()
    for dist, ci, li in pairs:
        if ci in used_curve or li in used_legend:
            continue
        labels[ci] = parsed_legend[li][0]
        used_curve.add(ci)
        used_legend.add(li)
    return labels


def _round_sig(x: float, sig: int = 4) -> float:
    """Round to a few significant figures for tidy CSV output."""
    import math

    if x == 0 or not math.isfinite(x):
        return 0.0
    from decimal import Decimal

    d = round(x, -int(math.floor(math.log10(abs(x)))) + (sig - 1))
    return float(d)


def _points_to_csv(points, x_header: str, y_header: str) -> str:
    """Render mapped (x, y) value points as a 2-column CSV string."""
    lines = [f"{x_header},{y_header}"]
    for x, y in points:
        lines.append(f"{_round_sig(x)},{_round_sig(y)}")
    return "\n".join(lines)


def _axis_header(label: str, fallback: str) -> str:
    """Turn an axis label like 'Crack Length (a) [mm]' into a CSV-safe header."""
    text = str(label or "").strip() or fallback
    text = re.sub(r"\s+", "_", text)
    text = re.sub(r"[^0-9A-Za-z_%.\-]", "", text)
    return text or fallback


def _sanitize_filename_part(text: str, fallback: str = "figure") -> str:
    """Make a string safe to use as a filename stem."""
    s = re.sub(r"\s+", "_", str(text or "").strip())
    s = re.sub(r"[^0-9A-Za-z_.\-]", "", s)
    return s.strip("._-") or fallback


def _line_multi_long_csv(usable_series: List[Dict[str, Any]]) -> str:
    """Combine per-series 2-column CSVs into one long-format CSV.

    Output columns: ``series,kind,<x_header>,<y_header>``.  Each series contributes
    its own rows (series may have different x samples / row counts — long
    format handles this naturally without NaN padding).
    """
    import csv as _csv
    import io

    x_hdr, y_hdr = "x", "y"
    for s in usable_series:
        lines = str(s.get("csv") or "").strip().splitlines()
        if lines and "," in lines[0]:
            try:
                header_cells = next(_csv.reader([lines[0]]))
            except Exception:
                header_cells = lines[0].split(",", 1)
            if len(header_cells) >= 2:
                x_hdr, y_hdr = header_cells[0], header_cells[1]
            break

    buf = io.StringIO()
    w = _csv.writer(buf)
    w.writerow(["series", "kind", x_hdr, y_hdr])
    for s in usable_series:
        label = str(s.get("label") or "series").strip()
        lines = str(s.get("csv") or "").strip().splitlines()
        for row in lines[1:]:  # skip the per-series header
            try:
                cells = next(_csv.reader([row]))
            except Exception:
                cells = row.split(",")
            if len(cells) >= 2:
                w.writerow([label, str(s.get("kind") or "trend"), cells[0], cells[1]])
    return buf.getvalue().strip()


def _line_summary_long_csv(series: List[Dict[str, Any]]) -> str:
    """Render line-summary key points (start/end/extrema) as a long-format CSV.

    Columns: ``series,point_type,x,y,note``.  Used by the ``line`` fallback path
    (color split failed → VLM reported only trend key points, not a dense
    table), so the md keeps a trend gist and the points live in a sibling CSV.
    """
    import csv as _csv
    import io

    def _xy(pt: Any) -> Tuple[str, str]:
        if isinstance(pt, (list, tuple)) and len(pt) == 2:
            return str(pt[0]), str(pt[1])
        return "", ""

    buf = io.StringIO()
    w = _csv.writer(buf)
    w.writerow(["series", "point_type", "x", "y", "note"])
    for s in series:
        if not isinstance(s, dict):
            continue
        label = str(s.get("label") or "series").strip()
        sx, sy = _xy(s.get("start"))
        if sx or sy:
            w.writerow([label, "start", sx, sy, ""])
        for e in s.get("extrema") or []:
            if not isinstance(e, dict):
                continue
            ex, ey = _xy(e.get("point"))
            w.writerow([label, str(e.get("kind") or "extremum"), ex, ey, str(e.get("note") or "")])
        ex_, ey_ = _xy(s.get("end"))
        if ex_ or ey_:
            w.writerow([label, "end", ex_, ey_, ""])
    return buf.getvalue().strip()


def _write_csv_file(csv_dir: str, basename: str, content: str) -> Optional[str]:
    """Write ``content`` to ``{csv_dir}/{basename}.csv``; return the filename.

    Returns the bare filename (for a relative reference from a sibling .md), or
    None on any failure so callers can fall back to inlining the CSV.
    """
    try:
        stem = _sanitize_filename_part(basename)
        out_dir = Path(csv_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        fname = f"{stem}.csv"
        (out_dir / fname).write_text(content.strip() + "\n", encoding="utf-8")
        return fname
    except OSError as exc:
        logger.warning("Failed to write digitized CSV %s in %s: %s", basename, csv_dir, exc)
        return None


def is_chart_crop(image_path: str) -> bool:
    """True if the OCR crop filename marks it as a plottable chart."""
    return _CHART_BOX_TOKEN in Path(str(image_path or "")).name


def is_micrograph_crop(image_path: str) -> bool:
    """True if the OCR crop filename marks it as a micrograph/photo."""
    return _IMAGE_BOX_TOKEN in Path(str(image_path or "")).name


def _encode_image_base64(image_path: Path) -> Optional[str]:
    try:
        return base64.b64encode(image_path.read_bytes()).decode("utf-8")
    except OSError as exc:
        logger.warning("Cannot read chart image %s: %s", image_path, exc)
        return None


def _parse_vlm_json(raw: str) -> Optional[Dict[str, Any]]:
    """Best-effort parse of the VLM JSON response."""
    text = str(raw or "").strip()
    if not text:
        return None
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.S | re.I).strip()
    text = re.sub(r"^```(?:json)?\s*", "", text)
    text = re.sub(r"\s*```$", "", text).strip()
    try:
        return json.loads(text)
    except Exception:
        pass
    match = re.search(r"\{.*\}", text, re.S)
    if match:
        try:
            return json.loads(match.group(0))
        except Exception:
            return None
    return None


def _is_parseable_vlm_json_object(raw: str) -> bool:
    """Return whether a chart response is safe to reuse from positive cache."""

    return isinstance(_parse_vlm_json(raw), dict)


def _is_valid_axis_calibration_json(raw: str) -> bool:
    """Return whether a cached response contains usable numeric tick anchors."""

    parsed = _parse_vlm_json(raw)
    return isinstance(parsed, dict) and validate_axis_calibration(parsed) is not None


def _is_valid_single_line_json(raw: str) -> bool:
    """Validate the legacy single-line response before positive caching."""

    parsed = _parse_vlm_json(raw)
    return isinstance(parsed, dict) and bool(str(parsed.get("csv") or "").strip())


def digitize_chart_image(
    image_path: Path,
    caption: str = "",
    *,
    model: Optional[str] = None,
    api_key: Optional[str] = None,
    base_url: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    """Classify + digitize a single chart crop. Returns parsed dict or None.

    The returned dict has keys: type, digitizable, confidence, reason, csv,
    line_summary.  ``type`` is coerced into the valid enum (else "other").
    Returns None on hard failure (unreadable image, no keys, VLM error).
    """
    resolved = Path(image_path)
    if not resolved.is_file():
        logger.debug("Chart image not found, skipping digitization: %s", image_path)
        return None

    b64 = _encode_image_base64(resolved)
    if b64 is None:
        return None

    _api_key = api_key or _get_vlm_pool().next_key()
    _base_url = (
        base_url
        or os.getenv("VLM_BASE_URL")
        or os.getenv("LLM_BASE_URL")
        or os.getenv("OPENAI_BASE_URL")
    )
    _model = model or os.getenv("VLM_MODEL") or os.getenv("LLM_MODEL", "")
    if not _api_key:
        logger.warning("No VLM_API_KEY/LLM_API_KEY configured; skipping chart digitization.")
        return None

    user_text = _CHART_PROMPT
    try:
        from PIL import Image

        with Image.open(resolved) as image:
            width, height = image.size
        user_text = (
            f"Image pixel size: width={width}, height={height}; origin=(0,0) top-left.\n\n"
            + user_text
        )
    except Exception:
        pass
    if caption:
        user_text = f"Caption: {caption}\n\n{user_text}"

    media_type = _image_media_type(resolved)
    messages = [
        {
            "role": "user",
            "content": [
                {
                    "type": "image_url",
                    "image_url": {"url": f"data:{media_type};base64,{b64}"},
                },
                {"type": "text", "text": user_text},
            ],
        },
    ]
    create_kwargs: dict = {
        "model": _model,
        "messages": messages,
        "max_tokens": 2048,
        "temperature": 0.1,
    }

    try:
        raw = _call_vlm_with_negative_cache(
            _base_url,
            create_kwargs,
            resolved,
            positive_validator=_is_parseable_vlm_json_object,
        )
    except Exception as exc:
        logger.warning("Chart digitization VLM call failed for %s: %s", image_path, exc)
        return None

    parsed = _parse_vlm_json(raw)
    if not parsed:
        logger.warning("Chart digitization JSON parse failed for %s", image_path)
        return None

    ctype = str(parsed.get("type") or "").strip().lower()
    if ctype not in _VALID_TYPES:
        # Coerce non-enum (e.g. "bar|line", "multi-panel mix") to "other" so
        # neither contract fires on an ambiguous crop.
        logger.debug("Chart type '%s' not a valid enum for %s; coercing to 'other'.", ctype, image_path)
        ctype = "other"
    parsed["type"] = ctype
    try:
        confidence = float(parsed.get("confidence"))
    except (TypeError, ValueError):
        confidence = 0.0
    if not 0.0 <= confidence <= 1.0:
        confidence = 0.0
    parsed["confidence"] = confidence
    parsed["axis_calibration"] = validate_axis_calibration(
        parsed.get("axis_calibration")
    )
    return parsed


def _digitize_single_line(
    image_path: Path,
    color_rgb: tuple,
    *,
    model: Optional[str] = None,
    api_key: Optional[str] = None,
    base_url: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    """Digitize ONE highlighted curve in a pre-split single-line image → CSV.

    Returns a dict {label, x_axis, y_axis, confidence, csv} or None on failure.
    Used by :func:`digitize_line_chart_multi` after color splitting.
    """
    resolved = Path(image_path)
    if not resolved.is_file():
        return None
    b64 = _encode_image_base64(resolved)
    if b64 is None:
        return None

    _api_key = api_key or _get_vlm_pool().next_key()
    _base_url = (
        base_url
        or os.getenv("VLM_BASE_URL")
        or os.getenv("LLM_BASE_URL")
        or os.getenv("OPENAI_BASE_URL")
    )
    _model = model or os.getenv("VLM_MODEL") or os.getenv("LLM_MODEL", "")
    if not _api_key:
        return None

    media_type = _image_media_type(resolved)
    prompt = _SINGLE_LINE_PROMPT.format(rgb=f"{color_rgb[0]},{color_rgb[1]},{color_rgb[2]}")
    messages = [
        {
            "role": "user",
            "content": [
                {"type": "image_url", "image_url": {"url": f"data:{media_type};base64,{b64}"}},
                {"type": "text", "text": prompt},
            ],
        },
    ]
    create_kwargs: dict = {
        "model": _model,
        "messages": messages,
        "max_tokens": 2048,
        "temperature": 0.1,
    }
    try:
        raw = _call_vlm_with_negative_cache(
            _base_url,
            create_kwargs,
            resolved,
            positive_validator=_is_valid_single_line_json,
        )
    except Exception as exc:
        logger.warning("Single-line digitization VLM call failed for %s: %s", image_path, exc)
        return None

    parsed = _parse_vlm_json(raw)
    if not parsed or not str(parsed.get("csv") or "").strip():
        return None
    return parsed


def _max_curve_points() -> int:
    """Per-curve point budget for code-based extraction (env-configurable)."""
    try:
        return max(10, int(os.getenv("KNOWMAT2_CHART_MAX_POINTS", "60")))
    except ValueError:
        return 60


def digitize_line_chart_multi(
    image_path: Path,
    caption: str = "",
    *,
    max_series: int = 6,
    model: Optional[str] = None,
    api_key: Optional[str] = None,
    base_url: Optional[str] = None,
    axis_calibration: Optional[Dict[str, Any]] = None,
    allow_axis_calibration_vlm: bool = True,
) -> Optional[Dict[str, Any]]:
    """Digitize a multi-line chart with a pure-code PDF fast path.

    Pipeline:
      1. For vector PDFs, read paths, markers and tick references directly;
         this branch never needs an API key and never asks a VLM for values.
      2. For legacy raster/color inputs, retain the existing deterministic
         splitter and optional calibration path for compatibility.
      3. If the legacy path is used with a configured VLM, the model is only
         asked for axis calibration or labels; curve coordinates remain code
         sampled.

    If the legacy raster path cannot calibrate without a VLM, it returns no
    numeric series rather than fabricating point values.  Returns a
    ``type="line_multi"`` dict, or ``None`` if not splittable/calibratable.
    """
    import tempfile

    # Vector-first path: the benchmark charts are black/white vector PDFs, so
    # colour splitting cannot see their curves.  Recovering the original PDF
    # paths is deterministic and does not require a VLM/API key.  If the file
    # is not a PDF or vector extraction is inconclusive, continue through the
    # existing colour/raster path below.
    if Path(image_path).suffix.lower() == ".pdf":
        try:
            from knowmat.pdf.vector_chart_digitizer import digitize_vector_pdf

            vector_result = digitize_vector_pdf(
                image_path,
                max_points=max(_max_curve_points(), 300),
            )
            if vector_result:
                return vector_result
        except Exception as exc:  # pragma: no cover - optional accelerator
            logger.debug("Vector PDF chart extraction unavailable: %s", exc)

    from knowmat.pdf.line_chart_splitter import (
        extract_curve_points,
        split_line_chart_by_color,
    )

    tmp_dir = Path(tempfile.mkdtemp(prefix="linesplit_"))
    try:
        splits = split_line_chart_by_color(image_path, tmp_dir, max_series=max_series)
        if len(splits) < 2:
            return None

        max_pts = _max_curve_points()
        x_axis = ""
        y_axis = ""

        # --- Code-first path: extract dense points + one VLM axis calibration ---
        calib = validate_axis_calibration(axis_calibration)
        if not calib and allow_axis_calibration_vlm:
            calib = _read_axis_calibration(
                image_path, model=model, api_key=api_key, base_url=base_url
            )
        fx = _linear_mapper(calib.get("x_ref"), "pixel_x") if calib else None
        fy = _linear_mapper(calib.get("y_ref"), "pixel_y") if calib else None

        series_out: List[Dict[str, Any]] = []
        if calib and fx and fy:
            x_axis = str(calib.get("x_axis") or "").strip()
            y_axis = str(calib.get("y_axis") or "").strip()
            x_hdr = _axis_header(x_axis, "x")
            y_hdr = _axis_header(y_axis, "y")
            # Match each split curve to a legend label by color (robust to
            # legend entries that were never color-extracted, e.g. a black
            # reference line). Falls back to series_N when unmatched.
            legend = calib.get("series") or []
            color_labels = _match_labels_by_color(
                [tuple(sp.color_rgb) for sp in splits], legend
            )
            for idx, sp in enumerate(splits):
                pts = extract_curve_points(sp.image_path, sp.color_rgb, max_points=max_pts)
                if len(pts) < 2:
                    continue
                mapped = [(fx(px), fy(py)) for px, py in pts]
                mapped.sort(key=lambda p: p[0])  # ascending X
                label = color_labels[idx] or f"series_{idx + 1}"
                series_out.append({
                    "label": label,
                    "color_rgb": list(sp.color_rgb),
                    "csv": _points_to_csv(mapped, x_hdr, y_hdr),
                    "n_points": len(mapped),
                    "method": "raster_code",
                })

        # --- No numeric VLM fallback ---
        # A VLM-produced per-point CSV is deliberately not accepted: it tends
        # to invent evenly spaced values and erase bends.  Keep the old helper
        # available for callers that explicitly use it, but never invoke it
        # from this multi-line contract.
        if not series_out:
            logger.info(
                "[line-digitize] axis calibration unavailable for %s; "
                "returning no numeric series (VLM point fallback disabled).", image_path,
            )

        if not series_out:
            return None

        # Dedup series the VLM gave the SAME legend label to. This happens when
        # two split images carry near-identical curves (e.g. a black reference
        # line leaking in beside the real curve) and the VLM picks the same
        # legend entry for both. Keep the higher-confidence one; the other is
        # almost always the spurious / mislabelled split.
        by_label: Dict[str, Dict[str, Any]] = {}
        deduped: List[Dict[str, Any]] = []
        for s in series_out:
            key = s["label"].strip().lower()
            if key.startswith("series_"):
                # Auto-generated placeholder labels are never "duplicates".
                deduped.append(s)
                continue
            prev = by_label.get(key)
            if prev is None:
                by_label[key] = s
                deduped.append(s)
                continue
            # Same label twice: keep the more confident, drop the other.
            prev_conf = prev.get("confidence") or 0.0
            cur_conf = s.get("confidence") or 0.0
            if cur_conf > prev_conf:
                deduped[deduped.index(prev)] = s
                by_label[key] = s
            logger.info(
                "[line-split] dropped duplicate series label '%s' (kept conf=%.2f)",
                s["label"], max(prev_conf, cur_conf),
            )

        if not deduped:
            return None
        return {
            "type": "line_multi",
            "method": "raster_code",
            "coordinate_source": "pure_code",
            "value_source": "image_digitized",
            "x_axis": x_axis,
            "y_axis": y_axis,
            "n_series": len(deduped),
            "series": deduped,
        }
    finally:
        import shutil
        shutil.rmtree(tmp_dir, ignore_errors=True)


def digitize_line_chart_region(
    source_pdf: str | Path,
    page_number: int,
    bbox: Optional[List[float]] = None,
    *,
    legacy_image_path: str | Path = "",
    max_series: int = 6,
) -> Optional[Dict[str, Any]]:
    """Digitize one PDF figure region without changing the source document.

    ``page_number`` is one-based and ``bbox`` uses PDF point coordinates.  A
    temporary one-page PDF is built with ``show_pdf_page`` so vector paths and
    text remain vector data for :func:`digitize_line_chart_multi`.

    Older API OCR sidecars do not carry a PDF bbox; their crop filename embeds
    pixel coordinates instead.  For those files only, ``legacy_image_path`` is
    decoded with a narrowly-scoped, configurable render DPI (144 by default).
    This compatibility rule never affects current bbox-bearing OCR output.
    """
    import math
    import tempfile

    try:
        import fitz  # type: ignore
    except ImportError:  # pragma: no cover - optional dependency
        return None

    pdf_path = Path(source_pdf)
    if not pdf_path.is_file() or pdf_path.suffix.lower() != ".pdf":
        return None
    try:
        page_idx = int(page_number) - 1
    except (TypeError, ValueError):
        return None

    try:
        with fitz.open(pdf_path) as source_doc:
            if page_idx < 0 or page_idx >= len(source_doc):
                return None
            source_page = source_doc[page_idx]

            values: Optional[List[float]] = None
            if isinstance(bbox, (list, tuple)) and len(bbox) == 4:
                try:
                    candidate = [float(value) for value in bbox]
                    if all(math.isfinite(value) for value in candidate):
                        values = candidate
                except (TypeError, ValueError):
                    values = None

            if values is None and legacy_image_path:
                match = re.search(
                    r"img_in_chart_box_(\d+)_(\d+)_(\d+)_(\d+)\.(?:png|jpe?g|webp)$",
                    Path(legacy_image_path).name,
                    re.IGNORECASE,
                )
                if match:
                    try:
                        legacy_dpi = float(
                            os.getenv("KNOWMAT2_LEGACY_CHART_RENDER_DPI", "144")
                        )
                    except ValueError:
                        legacy_dpi = 144.0
                    scale = 72.0 / max(72.0, legacy_dpi)
                    values = [float(token) * scale for token in match.groups()]

            if values is None:
                # Whole-page extraction can mix body text and neighbouring
                # figures, so absence of a resolved region is a safe failure.
                return None

            x0, y0, x1, y1 = values
            if x1 <= x0 or y1 <= y0:
                return None
            clip = fitz.Rect(x0, y0, x1, y1) & source_page.rect
            if clip.is_empty or clip.width < 12.0 or clip.height < 12.0:
                return None

            # Preserve strokes that touch an OCR crop edge without widening
            # enough to pull in a neighbouring panel.
            padded = fitz.Rect(
                clip.x0 - 2.0,
                clip.y0 - 2.0,
                clip.x1 + 2.0,
                clip.y1 + 2.0,
            ) & source_page.rect

            # Avoid a needless copy for standalone figure PDFs.  This also
            # retains the deliberately narrow raster-only compatibility path,
            # whose guard uses the original fixture filename and page geometry.
            full_page = (
                len(source_doc) == 1
                and abs(padded.x0 - source_page.rect.x0) <= 2.1
                and abs(padded.y0 - source_page.rect.y0) <= 2.1
                and abs(padded.x1 - source_page.rect.x1) <= 2.1
                and abs(padded.y1 - source_page.rect.y1) <= 2.1
            )
            if full_page:
                return digitize_line_chart_multi(
                    pdf_path,
                    max_series=max_series,
                )

            with tempfile.TemporaryDirectory(prefix="knowmat_chart_region_") as tmp:
                region_pdf = Path(tmp) / "figure-region.pdf"
                with fitz.open() as region_doc:
                    region_page = region_doc.new_page(
                        width=float(padded.width), height=float(padded.height)
                    )
                    region_page.show_pdf_page(
                        region_page.rect,
                        source_doc,
                        page_idx,
                        clip=padded,
                    )
                    region_doc.save(region_pdf)
                return digitize_line_chart_multi(
                    region_pdf,
                    max_series=max_series,
                )
    except Exception as exc:
        logger.debug(
            "Pure-code line extraction failed for %s page %s bbox %s: %s",
            pdf_path,
            page_number,
            bbox,
            exc,
        )
        return None


def _coordinate_signature(result: Dict[str, Any]) -> tuple:
    """Return the fields that optional semantic enrichment must not change."""
    return tuple(
        (
            series.get("csv"),
            series.get("n_points"),
            series.get("kind"),
            series.get("method"),
        )
        for series in result.get("series") or []
        if isinstance(series, dict)
    )


def merge_line_semantics(
    code_result: Dict[str, Any],
    vlm_result: Optional[Dict[str, Any]],
) -> Dict[str, Any]:
    """Add optional VLM labels/validation while preserving code coordinates.

    The VLM response is treated as untrusted semantic metadata.  Its ``csv``,
    start/end points and extrema are never copied.  Axis text is only used to
    fill a missing code-derived label, and series names are applied only when
    the number of readable VLM labels exactly matches a deterministic group of
    placeholder-labelled code series.
    """
    from copy import deepcopy

    merged = deepcopy(code_result)
    before = _coordinate_signature(merged)
    if not isinstance(vlm_result, dict):
        merged.setdefault("coordinate_source", "pure_code")
        merged.setdefault("semantic_source", "code_only")
        assert before == _coordinate_signature(merged)
        return merged

    vlm_type = str(vlm_result.get("type") or "").strip().lower()
    line_summary = vlm_result.get("line_summary")
    if not isinstance(line_summary, dict):
        line_summary = {}

    warnings = list(merged.get("warnings") or [])
    if vlm_type and vlm_type != "line":
        warnings.append(
            f"optional VLM classified this code-extracted chart as {vlm_type}"
        )

    for axis_key in ("x_axis", "y_axis"):
        semantic_axis = str(line_summary.get(axis_key) or "").strip()
        code_axis = str(merged.get(axis_key) or "").strip()
        if semantic_axis and not code_axis:
            merged[axis_key] = semantic_axis
        elif semantic_axis and semantic_axis != code_axis:
            merged.setdefault("semantic_axes", {})[axis_key] = semantic_axis

    semantic_series = [
        row
        for row in line_summary.get("series") or []
        if isinstance(row, dict) and str(row.get("label") or "").strip()
    ]
    code_series = [row for row in merged.get("series") or [] if isinstance(row, dict)]
    placeholders = [
        row
        for row in code_series
        if re.fullmatch(r"series_\d+", str(row.get("label") or "").strip())
    ]
    # Prefer true trend paths when marker/spread auxiliaries are also present.
    trend_placeholders = [
        row
        for row in placeholders
        if str(row.get("kind") or "").strip().lower().startswith("trend")
    ]
    candidates = trend_placeholders if len(trend_placeholders) == len(semantic_series) else placeholders
    if semantic_series and len(candidates) == len(semantic_series):
        for code_row, semantic_row in zip(candidates, semantic_series):
            label = str(semantic_row.get("label") or "").strip()
            code_row["semantic_label"] = label
            code_row["label"] = label
    elif semantic_series:
        warnings.append(
            "VLM series labels were not applied because their count did not match code traces"
        )

    merged["coordinate_source"] = "pure_code"
    merged["semantic_source"] = "vlm_optional"
    merged["semantic_validation"] = {
        "classification": vlm_type or "unavailable",
        "consistent": vlm_type in {"", "line"},
        "confidence": vlm_result.get("confidence"),
        "reason": str(vlm_result.get("reason") or "").strip(),
    }
    if warnings:
        merged["warnings"] = warnings

    # Hard invariant: semantic enrichment cannot alter any numeric series.
    assert before == _coordinate_signature(merged)
    return merged


def _fmt_pt(pt: Any) -> str:
    if isinstance(pt, (list, tuple)) and len(pt) == 2:
        return f"[{pt[0]}, {pt[1]}]"
    return str(pt)


def _context_limit(value: Any, default: int, *, minimum: int) -> int:
    """Return a safe positive context limit from config or a caller override."""
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        parsed = default
    return max(minimum, parsed)


def _context_text(value: Any, *, max_chars: int = 160) -> str:
    """Flatten provider labels so one field cannot consume the block budget."""
    text = re.sub(r"\s+", " ", str(value or "")).strip()
    if len(text) > max_chars:
        return text[: max_chars - 1].rstrip() + "…"
    return text


def _series_context_line(series: Dict[str, Any]) -> str:
    """Summarize one code-derived series without inventing new coordinates."""
    import csv as _csv

    rows: List[tuple[str, str]] = []
    lines = str(series.get("csv") or "").strip().splitlines()
    for raw in lines[1:]:
        try:
            cells = next(_csv.reader([raw]))
        except Exception:
            cells = raw.split(",")
        if len(cells) >= 2 and str(cells[0]).strip() and str(cells[1]).strip():
            rows.append((str(cells[0]).strip(), str(cells[1]).strip()))

    candidates: List[tuple[str, tuple[str, str]]] = []
    if rows:
        candidates.extend(
            [
                ("start", rows[0]),
                ("mid", rows[len(rows) // 2]),
                ("end", rows[-1]),
            ]
        )
        numeric_y: List[tuple[float, tuple[str, str]]] = []
        for point in rows:
            try:
                numeric_y.append((float(point[1]), point))
            except (TypeError, ValueError):
                continue
        if numeric_y:
            candidates.extend(
                [
                    ("min_y", min(numeric_y, key=lambda row: row[0])[1]),
                    ("max_y", max(numeric_y, key=lambda row: row[0])[1]),
                ]
            )

    seen: set[tuple[str, str]] = set()
    key_points: List[str] = []
    for role, point in candidates:
        if point in seen:
            continue
        seen.add(point)
        key_points.append(f"{role}=({point[0]},{point[1]})")

    label = _context_text(series.get("label") or "series")
    kind = _context_text(series.get("kind") or "trend", max_chars=48)
    try:
        n_points = int(series.get("n_points") or len(rows))
    except (TypeError, ValueError):
        n_points = len(rows)
    suffix = "; key_points=" + ";".join(key_points) if key_points else ""
    return f"series: {label}; kind={kind}; n_points={n_points}{suffix}"


def _line_series_numeric_values(series: Dict[str, Any]) -> List[tuple[float, float]] | None:
    """Parse a deterministic per-series CSV, rejecting non-finite coordinates."""

    import csv as _csv
    import math

    values: List[tuple[float, float]] = []
    lines = str(series.get("csv") or "").strip().splitlines()
    for raw in lines[1:]:
        if not raw.strip():
            continue
        try:
            cells = next(_csv.reader([raw]))
        except Exception:
            return None
        if len(cells) < 2:
            return None
        try:
            x_value, y_value = float(cells[0]), float(cells[1])
        except (TypeError, ValueError):
            return None
        if not math.isfinite(x_value) or not math.isfinite(y_value):
            return None
        values.append((x_value, y_value))
    return values or None


def _line_series_quality_partition(
    result: Dict[str, Any], series: List[Dict[str, Any]]
) -> tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """Quarantine code-derived series that violate generic numeric contracts."""

    y_axis = str(result.get("y_axis") or "")
    nonnegative_tensile = bool(
        re.search(r"(?i)\btensile\b", y_axis)
        and re.search(r"(?i)\b(?:strength|stress|yield|uts)\b", y_axis)
    )
    accepted: List[Dict[str, Any]] = []
    quarantined: List[Dict[str, Any]] = []
    for row in series:
        values = _line_series_numeric_values(row)
        if values is None:
            quarantined.append(
                {
                    "label": _context_text(row.get("label") or "series", max_chars=24),
                    "reason": "invalid_or_non_finite_coordinates",
                    "observed_min": None,
                    "observed_max": None,
                }
            )
            continue
        y_values = [value[1] for value in values]
        tolerance = max(1.0, max(abs(value) for value in y_values) * 0.01)
        if nonnegative_tensile and min(y_values) < -tolerance:
            quarantined.append(
                {
                    "label": _context_text(row.get("label") or "series", max_chars=24),
                    "reason": "significant_negative_on_nonnegative_tensile_axis",
                    "observed_min": min(y_values),
                    "observed_max": max(y_values),
                }
            )
            continue
        accepted.append(row)
    return accepted, quarantined


def _quality_quarantine_line(
    quarantined: List[Dict[str, Any]], data_csv: Optional[str]
) -> str:
    if not quarantined:
        return ""
    minima = [
        row["observed_min"]
        for row in quarantined
        if row.get("observed_min") is not None
    ]
    maxima = [
        row["observed_max"]
        for row in quarantined
        if row.get("observed_max") is not None
    ]
    payload = {
        "code": "curve_series_quarantined",
        "series": [row["label"] for row in quarantined],
        "reasons": sorted({str(row["reason"]) for row in quarantined}),
        "observed_min": min(minima) if minima else None,
        "observed_max": max(maxima) if maxima else None,
        "data_csv": _context_text(data_csv or "unavailable", max_chars=80),
    }
    return "quality_quarantine:" + json.dumps(
        payload, ensure_ascii=False, separators=(",", ":")
    )


def _bounded_line_context_block(
    result: Dict[str, Any],
    usable: List[Dict[str, Any]],
    header: str,
    *,
    data_csv: Optional[str],
    quality_quarantine: str = "",
    max_chars: int,
    max_series: int,
) -> str:
    """Build a hard-bounded chart block while full points remain external."""
    limit = _context_limit(max_chars, 2400, minimum=512)
    series_limit = _context_limit(max_series, 12, minimum=1)
    total_points = 0
    for series in usable:
        try:
            total_points += int(
                series.get("n_points")
                or max(0, str(series.get("csv") or "").count("\n"))
            )
        except (TypeError, ValueError):
            continue

    prefix = [header]
    if quality_quarantine:
        prefix.append(quality_quarantine)
    x_axis = _context_text(result.get("x_axis"), max_chars=240)
    y_axis = _context_text(result.get("y_axis"), max_chars=240)
    if x_axis:
        prefix.append(f"x_axis: {x_axis}")
    if y_axis:
        prefix.append(f"y_axis: {y_axis}")
    for key in ("coordinate_source", "value_source", "semantic_source"):
        value = _context_text(result.get(key), max_chars=80)
        if value:
            prefix.append(f"{key}: {value}")
    prefix.extend(
        [
            "context_detail: bounded_key_points",
            f"series_total: {len(usable)}",
        ]
    )

    summaries: List[str] = []
    candidates = usable[:series_limit]
    for series in candidates:
        line = _series_context_line(series)
        omitted_after = len(usable) - (len(summaries) + 1)
        tail = [
            f"context_omitted_series: {max(0, omitted_after)}",
            f"total_points: {total_points}",
            f"data_csv: {data_csv or 'unavailable'}",
            f"full_data_externalized: {'true' if data_csv else 'false'}",
        ]
        trial = "\n".join(prefix + summaries + [line] + tail)
        if len(trial) > limit:
            break
        summaries.append(line)

    omitted = len(usable) - len(summaries)
    tail = [
        f"context_omitted_series: {omitted}",
        f"total_points: {total_points}",
        f"data_csv: {data_csv or 'unavailable'}",
        f"full_data_externalized: {'true' if data_csv else 'false'}",
    ]
    block = "\n".join(prefix + summaries + tail)
    if len(block) <= limit:
        return block

    # Pathological labels/axes still cannot evict the file reference or counts.
    minimal_rows = [_context_text(header, max_chars=100)]
    if quality_quarantine:
        minimal_rows.append(quality_quarantine)
    minimal_rows.extend(
        [
            "context_detail: reference_only",
            f"series_total: {len(usable)}",
            f"total_points: {total_points}",
            f"data_csv: {data_csv or 'unavailable'}",
            f"full_data_externalized: {'true' if data_csv else 'false'}",
        ]
    )
    minimal = "\n".join(minimal_rows)
    if len(minimal) <= limit:
        return minimal
    # The audit marker is the recoverable record for quarantined data. Never
    # truncate its JSON merely to retain decorative chart context.
    if quality_quarantine and len(quality_quarantine) <= limit:
        return quality_quarantine
    return minimal[:limit]


def format_digitized_block(
    result: Dict[str, Any],
    figure_num: str = "",
    *,
    csv_dir: Optional[str] = None,
    context_max_chars: int = 2400,
    context_max_series: int = 12,
) -> str:
    """Render a VLM-digitized injection block, or "" if nothing usable.

    Output is plain text under the dedicated ``VLM-digitized`` marker so the
    extraction prompt whitelist can target it. ``line_multi`` is necessarily
    code-derived; a VLM-only ``line`` result is rejected. Everything else
    returns "" except the existing discrete bar contract.

    Line-chart point tables are never fully inlined. When ``csv_dir`` is given,
    the complete table is written to a standalone ``.csv`` and the Markdown
    receives bounded deterministic key points plus a file reference. If the
    sidecar cannot be written, the same bounded summary is returned with
    ``data_csv: unavailable``. This prevents a filesystem failure from turning
    into an unbounded LLM prompt.
    """
    if not isinstance(result, dict):
        return ""
    ctype = result.get("type")
    label = f"Figure {figure_num}" if figure_num else "Figure"
    fig_stem = _sanitize_filename_part(
        f"figure_{figure_num}" if figure_num else "figure", "figure"
    )

    if ctype == "bar":
        csv = str(result.get("csv") or "").strip()
        if not csv:
            return ""
        header = f"> [{label} VLM-digitized | bar chart, estimated from pixels]:"
        if csv_dir:
            fname = _write_csv_file(csv_dir, f"{fig_stem}_digitized", csv)
            if fname:
                return f"{header}\ndata_csv: {fname}"
        return f"{header}\n{csv}"

    if ctype == "line_multi":
        series = result.get("series") or []
        recovered = [
            s
            for s in series
            if isinstance(s, dict) and str(s.get("csv") or "").strip()
        ]
        if not recovered:
            return ""
        fname = None
        if csv_dir:
            # Preserve every recovered coordinate before applying the context
            # quality gate. Quarantine is reversible through this sidecar.
            long_csv = _line_multi_long_csv(recovered)
            fname = _write_csv_file(csv_dir, f"{fig_stem}_digitized", long_csv)
        usable, quarantined = _line_series_quality_partition(result, recovered)
        n = len(usable)
        method = str(result.get("method") or "").strip().lower()
        if method == "pdf_vector":
            method_text = "pure-code PDF vector extraction"
        elif method == "raster_code":
            method_text = "pure-code raster extraction, estimated from pixels"
        else:
            method_text = "colour/pixel extraction"
        header = f"> [{label} VLM-digitized | line chart, {n} series, {method_text}]:"
        return _bounded_line_context_block(
            result,
            usable,
            header,
            data_csv=fname,
            quality_quarantine=_quality_quarantine_line(quarantined, fname),
            max_chars=context_max_chars,
            max_series=context_max_series,
        )

    if ctype == "line":
        # VLM-only line coordinates are deliberately never promoted to an
        # extraction source. A successful deterministic trace is represented
        # by ``line_multi`` above.
        return ""

    return ""
