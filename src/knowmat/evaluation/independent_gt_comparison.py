"""Claim-level comparison for the sealed independent expert GT corpus.

The production and business artifacts are v11 documents whose records contain
multiple atomic facts (for example, one composition observation contains many
elements).  This module first projects those documents into the same atomic
shape as ``expert_claims.jsonl`` and then performs two explicit match passes:

* loose: axis + scientific semantic + value/unit;
* strict: loose requirements + material owner/state + test condition.

The matcher deliberately does not use Item_ID equality and never treats a
shared number alone as a match.
"""

from __future__ import annotations

import json
import math
import re
import unicodedata
from collections import Counter
from functools import lru_cache
from pathlib import Path
from typing import Any, Iterable


AXES = ("Composition", "Processing", "Structure", "Characterization", "Properties")
CORE_TENSILE = {"ultimate_tensile_strength", "yield_strength", "elongation"}

_STOP_TOKENS = {
    "a", "an", "and", "at", "by", "for", "from", "in", "of", "on", "or",
    "the", "to", "with", "raw", "reported", "value", "property", "feature",
    "composition", "element", "process", "processing", "structure",
    "characterization", "method", "material", "sample", "test",
}

_PROPERTY_ALIASES = {
    "uts": "ultimate_tensile_strength",
    "ultimate_strength": "ultimate_tensile_strength",
    "ultimate_tensile_strength": "ultimate_tensile_strength",
    "engineering_ultimate_tensile_strength": "ultimate_tensile_strength",
    "ys": "yield_strength",
    "yield_stress": "yield_strength",
    "yield_strength": "yield_strength",
    "engineering_yield_strength": "yield_strength",
    "elongation": "elongation",
    "te": "elongation",
    "eab": "elongation",
    "total_elongation": "elongation",
    "uniform_elongation": "elongation",
    "fracture_elongation": "elongation",
    "elongation_at_break": "elongation",
    "elongation_at_failure": "elongation",
    "elongation_at_fracture": "elongation",
    "tensile_elongation": "elongation",
    "young_s_modulus": "elastic_modulus",
    "youngs_modulus": "elastic_modulus",
    "elastic_modulus": "elastic_modulus",
    "modulus_of_elasticity": "elastic_modulus",
    "vickers_microhardness": "vickers_hardness",
    "microhardness": "vickers_hardness",
    "vickers_hardness": "vickers_hardness",
}

_CHARACTERIZATION_METHOD_ALIASES = {
    "sem": "sem",
    "scanning_electron_microscopy": "sem",
    "eds": "eds",
    "edx": "eds",
    "energy_dispersive_x_ray_spectroscopy": "eds",
    "ebsd": "ebsd",
    "electron_backscatter_diffraction": "ebsd",
    "xrd": "xrd",
    "x_ray_diffraction": "xrd",
    "tem": "tem",
    "transmission_electron_microscopy": "tem",
    "stem": "stem",
    "scanning_transmission_electron_microscopy": "stem",
    "apt": "apt",
    "atom_probe_tomography": "apt",
    "tkd": "tkd",
    "micro_ct": "xct",
    "microct": "xct",
    "xct": "xct",
    "optical_microscopy": "om",
    "om": "om",
}
_RELATIVE_PROPERTY_SEMANTIC = re.compile(
    r"(?:^|_)(?:retention|relative|difference|change|increase|decrease|"
    r"increment|decrement|improvement|enhancement|contribution|ratio|delta|"
    r"reduction|drop|gain|loss)(?:_|$)"
)
_PROCESS_PREFIX = re.compile(
    r"^(?:(?:laser_)?powder_bed_fusion|lpbf|pbf_lb|pbf_eb|ebpbf|"
    r"directed_energy_deposition|ded|waam|am)_+"
)
_THERMAL_PROCESS_OPERATIONS = (
    ("sintering", re.compile(r"\b(?:vacuum\s+)?sinter(?:ed|ing)?\b")),
    (
        "solution",
        re.compile(r"\bsolution\s+(?:treat(?:ed|ment)?|anneal(?:ed|ing)?)\b"),
    ),
    (
        "aging",
        re.compile(r"\b(?:ag(?:e|ed|ing|eing)|age\s+hardening)\b"),
    ),
    ("annealing", re.compile(r"\banneal(?:ed|ing)?\b")),
    ("homogenization", re.compile(r"\bhomogeni[sz](?:ed|ation)?\b")),
    (
        "hot_isostatic_pressing",
        re.compile(r"\b(?:hot\s+isostatic\s+press(?:ed|ing)?|hip(?:ing)?)\b"),
    ),
    ("stress_relief", re.compile(r"\bstress\s+relie(?:ved|f)\b")),
    ("curing", re.compile(r"\bcur(?:ed|ing)\b")),
    ("debinding", re.compile(r"\bdeb(?:ind(?:ing)?|ound)\b")),
    ("drying", re.compile(r"\bdry(?:ing|ied)\b")),
    ("heat_treatment", re.compile(r"\bheat\s+treat(?:ed|ment)?\b")),
)
_THERMAL_TIME_KEYS = {"duration", "time", "hold_time", "holding_time"}
_THERMAL_TEMPERATURE_KEYS = {
    "heating_temperature",
    "heat_treatment_temperature",
    "process_temperature",
    "treatment_temperature",
    "thermal_environment_temperature",
}
_ENERGY_SOURCE_CONDITIONS = {
    "laser": "laser",
    "wire": "wire",
    "hot wire": "hot_wire",
    "electron beam": "electron_beam",
    "arc": "arc",
}


def fold(value: Any) -> str:
    text = unicodedata.normalize("NFKC", str(value or "")).casefold()
    text = text.replace("γ′", "gamma_prime").replace("γ'", "gamma_prime")
    text = text.replace("γ", "gamma").replace("α", "alpha").replace("β", "beta")
    text = text.replace("₂", "2").replace("₃", "3")
    return re.sub(r"[^a-z0-9]+", " ", text).strip()


def _microanalysis_location(value: Any) -> str:
    """Normalize one literal numbered microanalysis observation location."""

    text = fold(value)
    match = re.fullmatch(
        r"(?:(?:eds|edx|sem|tem)(?: analysis)? )?"
        r"(?:point|spot|area|location) (\d+)",
        text,
    )
    return f"location {int(match.group(1))}" if match else ""


def slug(value: Any) -> str:
    return fold(value).replace(" ", "_") or "unknown"


def title_key(value: Any) -> str:
    return re.sub(r"[^a-z0-9]+", "", fold(value))


def _tokens(value: Any) -> set[str]:
    return {token for token in fold(value).split() if token not in _STOP_TOKENS}


def _jaccard(left: set[str], right: set[str]) -> float:
    if not left or not right:
        return 0.0
    return len(left & right) / len(left | right)


def _evidence(value: Any) -> list[str]:
    rows: list[str] = []
    if isinstance(value, dict):
        for key, child in value.items():
            if key == "source_evidence":
                if isinstance(child, str):
                    child = [child]
                if isinstance(child, list):
                    rows.extend(str(row).strip() for row in child if str(row).strip())
            else:
                rows.extend(_evidence(child))
    elif isinstance(value, list):
        for child in value:
            rows.extend(_evidence(child))
    return list(dict.fromkeys(rows))


def _origin(value: Any, data_nature: Any = None) -> str:
    text = fold(value or data_nature)
    if "literature" in text or "reference" in text or "previous" in text:
        return "literature_computation" if "comput" in text else "literature_experiment"
    if "comput" in text or "simulation" in text or "calculated" in text or "derived" in text:
        return "author_computation"
    if "direct experiment" in text or "experimental" in text or "measured" in text:
        return "author_experiment"
    if "provided" in text:
        return "provided"
    if "inferred" in text:
        return "inferred"
    return "unknown"


def _property_origin(prop: dict[str, Any], item: dict[str, Any]) -> str:
    """Resolve property provenance with the enclosing item's source role.

    A normalized property can retain ``Observation_Origin=unknown`` even when
    its material item is explicitly a literature Reference.  Conversely, a
    cited source's own direct experiment is still literature from the current
    paper's perspective.  Item role therefore has priority for Reference facts;
    Target facts use property provenance first and item data nature as fallback.
    """

    role = fold(item.get("Role"))
    property_nature = prop.get("Data_Nature")
    if role == "reference":
        text = fold(property_nature or item.get("Data_Nature"))
        return (
            "literature_computation"
            if any(token in text for token in ("comput", "simulat", "calculat", "derived"))
            else "literature_experiment"
        )
    resolved = _origin(prop.get("Observation_Origin"), property_nature)
    return resolved if resolved != "unknown" else _origin(item.get("Data_Nature"))


def _condition_text(value: Any) -> str:
    if not value:
        return ""
    if isinstance(value, dict):
        preferred = [
            # Expert-claim conditions use ``raw`` as the canonical source
            # spelling, while v11 output uses ``original``.  Treat these as
            # equivalent presentations of one condition.  Falling through to
            # ``json.dumps`` here turns temperature/standard/replicate fields
            # into ordinary tokens (for example ``"replicates": 3``), which
            # makes a correctly attributed tensile result look like a strict
            # condition conflict.
            value.get("raw"), value.get("original"), value.get("condition_raw"),
            value.get("test_condition_raw"), value.get("original_excerpt"),
            value.get("simplified"),
        ]
        # These are alternate presentations of one condition, not independent
        # dimensions.  Joining all of them made one literal rate appear two or
        # three times and unfairly converted formatting redundancy into a
        # condition conflict.  Prefer the source-facing spelling and fall back
        # only when it is absent.
        for row in preferred:
            if row and str(row).strip():
                return str(row).strip()
        meaningful = {
            key: child
            for key, child in value.items()
            if child not in (None, "", [], {})
            and key not in {"condition_status", "test_method_class"}
        }
        if not meaningful:
            return ""
        # Some amended expert rows contain only structured dimensions (for
        # example temperature/rate/environment) and no ``raw`` presentation.
        # Render those dimensions as condition text instead of serializing the
        # JSON object, which would expose bookkeeping keys and replicate counts
        # as if they were scientific coordinates.
        dimensions = [
            meaningful.get("temperature_raw"),
            meaningful.get("time_raw"),
            meaningful.get("rate_raw"),
            meaningful.get("environment_raw"),
        ]
        details = meaningful.get("details")
        if isinstance(details, dict):
            dimensions.append(details.get("standard"))
        rendered = [str(row).strip() for row in dimensions if str(row or "").strip()]
        if rendered:
            return "; ".join(dict.fromkeys(rendered))
        return ""
    if isinstance(value, list):
        return " | ".join(_condition_text(row) for row in value if row)
    return str(value)


_ENRICHED_TENSILE_OWNER = re.compile(
    r"(?i)^(?P<material>.+?)\s*/\s*"
    r"(?P<sample>.+?\btensile\s+specimen)\s*"
    r"\[(?P<state>[^\[\]]+)\]\s*/\s*"
    r"(?P<orientation>[XYZ])\s*$"
)
_COMPACT_ORIENTATION_OWNER = re.compile(
    r"(?i)^(?P<sample>.+?)\s*/\s*(?P<orientation>[XYZ])\s*$"
)


def _condition_specimen_orientation(value: Any) -> str:
    if not isinstance(value, dict):
        return ""
    specimen = value.get("Specimen") or value.get("specimen") or {}
    candidates = [
        specimen.get("specimen_raw") if isinstance(specimen, dict) else None,
        value.get("specimen_raw"),
        value.get("test_specimen_raw"),
    ]
    for candidate in candidates:
        match = re.fullmatch(
            r"(?i)\s*([XYZ])(?:\s+(?:build\s+)?(?:orientation|direction))?\s*",
            str(candidate or ""),
        )
        if match is not None:
            return match.group(1).upper()
    return ""


def _numeric_values(value: dict[str, Any]) -> tuple[float, ...]:
    rows: list[float] = []
    for key in ("number", "canonical_value", "value_num", "bound", "bound_value", "min", "value_min", "max", "value_max"):
        candidate = value.get(key)
        if isinstance(candidate, (int, float)) and not isinstance(candidate, bool):
            rows.append(float(candidate))
    if not rows:
        raw = value.get("raw") or value.get("value_raw")
        if value.get("kind") in {"scalar", "inequality", "range"} or value.get("value_kind") in {"scalar", "inequality", "range"}:
            rows = [float(row) for row in re.findall(r"[-+]?\d+(?:\.\d+)?(?:[eE][-+]?\d+)?", str(raw or ""))]
    return tuple(rows)


_RAW_NUMBER = r"[-+]?\d+(?:\.\d+)?(?:[eE][-+]?\d+)?"
_RAW_UNIT_SUFFIX = r"(?:\s*(?:%|[A-Za-zμµ°][A-Za-z0-9μµ°/%·._^{}\\-]*))?"


def _parse_unstructured_numeric_value(raw: Any) -> dict[str, Any] | None:
    """Parse one unambiguous v11 ``Value_Raw`` numeric expression.

    Final v11 documents intentionally preserve source presentation and can omit
    a structured ``Value`` object.  The expert ledger is numeric, so treating
    ``~1148`` or ``595 ± 14`` as categorical text creates false evaluation
    misses.  This parser accepts only a single complete scalar/range/bound and
    deliberately rejects multi-value or comparison prose.
    """

    text = unicodedata.normalize("NFKC", str(raw or "")).strip()
    text = text.strip("$").strip()
    text = re.sub(r"\\+,(?=\s|$)", " ", text)
    text = re.sub(r"\\+(?:mathrm|text)\s*\{([^{}]*)\}", r"\1", text)
    text = re.sub(r"^\s*(?:approximately|approx\.?|about|ca\.?|~|≈)\s*", "", text, flags=re.I)
    text = re.sub(r"\\+pm\b", "±", text, flags=re.I)
    text = re.sub(r"\\+times\b", "×", text, flags=re.I)
    text = re.sub(r"\s+", " ", text).strip()
    if not text:
        return None

    scientific = re.fullmatch(
        rf"({_RAW_NUMBER})\s*×\s*10\s*\^?\s*\{{?([-+]?\d+)\}}?{_RAW_UNIT_SUFFIX}",
        text,
    )
    if scientific:
        return {
            "kind": "scalar",
            "number": float(scientific.group(1)) * (10 ** int(scientific.group(2))),
            "min": None,
            "max": None,
            "operator": None,
            "bound": None,
            "stddev": None,
            "text": None,
        }

    uncertainty = re.fullmatch(
        rf"({_RAW_NUMBER})\s*±\s*({_RAW_NUMBER}){_RAW_UNIT_SUFFIX}", text
    )
    if uncertainty:
        return {
            "kind": "scalar",
            "number": float(uncertainty.group(1)),
            "min": None,
            "max": None,
            "operator": None,
            "bound": None,
            "stddev": float(uncertainty.group(2)),
            "text": None,
        }

    inequality = re.fullmatch(
        rf"(<=|>=|<|>|≤|≥)\s*({_RAW_NUMBER}){_RAW_UNIT_SUFFIX}", text
    )
    if inequality:
        operator = {"≤": "<=", "≥": ">="}.get(
            inequality.group(1), inequality.group(1)
        )
        return {
            "kind": "inequality",
            "number": None,
            "min": None,
            "max": None,
            "operator": operator,
            "bound": float(inequality.group(2)),
            "stddev": None,
            "text": None,
        }

    value_range = re.fullmatch(
        rf"({_RAW_NUMBER})\s*(?:–|—|to)\s*({_RAW_NUMBER}){_RAW_UNIT_SUFFIX}",
        text,
        flags=re.I,
    )
    if value_range:
        return {
            "kind": "range",
            "number": None,
            "min": float(value_range.group(1)),
            "max": float(value_range.group(2)),
            "operator": None,
            "bound": None,
            "stddev": None,
            "text": None,
        }

    scalar = re.fullmatch(rf"({_RAW_NUMBER}){_RAW_UNIT_SUFFIX}", text)
    if scalar:
        return {
            "kind": "scalar",
            "number": float(scalar.group(1)),
            "min": None,
            "max": None,
            "operator": None,
            "bound": None,
            "stddev": None,
            "text": None,
        }
    return None


def _finite_number(value: Any) -> float | None:
    if (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(float(value))
    ):
        return float(value)
    return None


def _number_text(value: float) -> str:
    return format(float(value), ".15g")


def _numeric_display(
    *,
    kind: str,
    number: float | None = None,
    minimum: float | None = None,
    maximum: float | None = None,
    operator: Any = None,
    bound: float | None = None,
    stddev: float | None = None,
) -> str | None:
    if kind == "scalar" and number is not None:
        center = _number_text(number)
        return (
            f"{center} ± {_number_text(stddev)}"
            if stddev is not None
            else center
        )
    if kind == "range" and minimum is not None and maximum is not None:
        return f"{_number_text(minimum)}–{_number_text(maximum)}"
    if kind == "inequality" and bound is not None:
        qualifier = {"≤": "<=", "≥": ">="}.get(str(operator or ""), str(operator or ""))
        return f"{qualifier}{_number_text(bound)}"
    return None


def _value_field(
    nested: dict[str, Any], row: dict[str, Any], *names: str
) -> Any:
    for source in (nested, row):
        for name in names:
            if source.get(name) is not None:
                return source.get(name)
    return None


def _structured_value(
    *,
    kind: str,
    raw: Any,
    number: Any = None,
    minimum: Any = None,
    maximum: Any = None,
    operator: Any = None,
    bound: Any = None,
    stddev: Any = None,
) -> dict[str, Any]:
    number_value = _finite_number(number)
    minimum_value = _finite_number(minimum)
    maximum_value = _finite_number(maximum)
    bound_value = _finite_number(bound)
    stddev_value = _finite_number(stddev)
    return {
        "kind": kind,
        "raw": None if raw is None else str(raw),
        "number": number_value,
        "min": minimum_value,
        "max": maximum_value,
        "operator": operator,
        "bound": bound_value,
        "stddev": stddev_value,
        "text": (
            str(raw)
            if kind in {"categorical", "boolean", "unknown"} and raw is not None
            else None
        ),
    }


def _canonical_numeric_value(
    nested: dict[str, Any], row: dict[str, Any], *, kind: str
) -> tuple[dict[str, Any], str] | None:
    """Select one complete canonical numeric payload and its canonical unit."""

    canonical_unit = _value_field(nested, row, "canonical_unit")
    if canonical_unit in (None, ""):
        return None
    canonical_value = _value_field(nested, row, "canonical_value")

    if kind == "range":
        if (
            isinstance(canonical_value, (list, tuple))
            and len(canonical_value) == 2
        ):
            minimum = _finite_number(canonical_value[0])
            maximum = _finite_number(canonical_value[1])
            if minimum is not None and maximum is not None:
                display = _numeric_display(
                    kind=kind, minimum=minimum, maximum=maximum
                )
                return (
                    _structured_value(
                        kind=kind,
                        raw=display,
                        minimum=minimum,
                        maximum=maximum,
                    ),
                    str(canonical_unit),
                )
        return None

    if kind == "inequality":
        bound = _finite_number(canonical_value)
        if bound is None:
            return None
        operator = _value_field(nested, row, "operator", "qualifier")
        display = _numeric_display(
            kind=kind, operator=operator, bound=bound
        )
        return (
            _structured_value(
                kind=kind, raw=display, operator=operator, bound=bound
            ),
            str(canonical_unit),
        )

    # A normalized v11 Property.Value stores its canonical center and spread
    # in value_num/value_stddev while retaining source presentation separately.
    nested_number = _finite_number(nested.get("value_num")) if nested else None
    if nested_number is not None:
        stddev = _finite_number(nested.get("value_stddev"))
        display = _numeric_display(
            kind="scalar", number=nested_number, stddev=stddev
        )
        return (
            _structured_value(
                kind="scalar", raw=display, number=nested_number, stddev=stddev
            ),
            str(canonical_unit),
        )

    number = _finite_number(canonical_value)
    if number is None:
        return None
    raw_stddev = _finite_number(_value_field(nested, row, "value_stddev"))
    raw_unit = _value_field(nested, row, "unit_raw", "Unit_Raw")
    if (
        raw_stddev is not None
        and raw_unit not in (None, "")
        and _unit(raw_unit) != _unit(canonical_unit)
    ):
        # The center was converted but the uncertainty was not. Fall back as
        # one unit-consistent raw observation instead of mixing the layers.
        return None
    display = _numeric_display(
        kind="scalar", number=number, stddev=raw_stddev
    )
    return (
        _structured_value(
            kind="scalar", raw=display, number=number, stddev=raw_stddev
        ),
        str(canonical_unit),
    )


def _value(
    row: dict[str, Any], *, parse_unstructured_numeric: bool = False
) -> tuple[dict[str, Any], str | None]:
    """Return one representation-consistent atomic value/unit pair."""

    nested = row.get("Value") if isinstance(row.get("Value"), dict) else {}
    declared_kind = str(
        _value_field(nested, row, "value_kind") or "unknown"
    ).casefold()
    canonical = _canonical_numeric_value(
        nested, row, kind=declared_kind
    )
    if canonical is not None:
        return canonical

    raw = _value_field(nested, row, "value_raw", "Value_Raw", "value")
    raw_unit = _value_field(nested, row, "unit_raw", "Unit_Raw")
    number = _finite_number(_value_field(nested, row, "value_num", "value"))
    minimum = _finite_number(_value_field(nested, row, "value_min"))
    maximum = _finite_number(_value_field(nested, row, "value_max"))
    operator = _value_field(nested, row, "operator", "qualifier")
    bound = _finite_number(_value_field(nested, row, "bound_value"))
    stddev = _finite_number(_value_field(nested, row, "value_stddev"))

    parsed = _parse_unstructured_numeric_value(raw)
    parsed_allowed = (
        declared_kind in {"scalar", "range", "inequality"}
        or parse_unstructured_numeric
        or (
            declared_kind == "unknown"
            and raw_unit not in (None, "")
            and parsed is not None
            and parsed["kind"] == "scalar"
        )
    )
    if parsed is not None and parsed_allowed:
        if declared_kind == "unknown" or declared_kind == parsed["kind"]:
            declared_kind = parsed["kind"]
            if number is None:
                number = _finite_number(parsed.get("number"))
            if minimum is None:
                minimum = _finite_number(parsed.get("min"))
            if maximum is None:
                maximum = _finite_number(parsed.get("max"))
            if operator is None:
                operator = parsed.get("operator")
            if bound is None:
                bound = _finite_number(parsed.get("bound"))
            if stddev is None:
                stddev = _finite_number(parsed.get("stddev"))

    value = _structured_value(
        kind=declared_kind,
        raw=raw,
        number=number,
        minimum=minimum,
        maximum=maximum,
        operator=operator,
        bound=bound,
        stddev=stddev,
    )
    return value, None if raw_unit is None else str(raw_unit)


def _owner(
    item: dict[str, Any],
    *,
    sample_id: Any = None,
    state: Any = None,
    region: Any = None,
    location: Any = None,
    test_condition: Any = None,
) -> dict[str, Any]:
    extracted = item.get("Extracted_Data") or {}
    identity = ((extracted.get("Composition") or {}).get("Material_Identity") or {})
    item_sample = str(item.get("Sample_ID") or "").strip()
    material_name = (
        identity.get("material_name_raw") or identity.get("designation_raw")
        or identity.get("material_family") or item.get("Sample_ID") or "unknown material"
    )
    sample = sample_id if sample_id not in (None, "") else item.get("Sample_ID")
    owner_state = state
    orientation = _condition_specimen_orientation(test_condition)
    enriched = _ENRICHED_TENSILE_OWNER.fullmatch(item_sample)
    if enriched is not None and sample_id in (None, ""):
        material_name = enriched.group("material").strip()
        sample = enriched.group("sample").strip()
        if owner_state in (None, ""):
            owner_state = enriched.group("state").strip()
        orientation = orientation or enriched.group("orientation").upper()
    elif sample_id in (None, ""):
        compact = _COMPACT_ORIENTATION_OWNER.fullmatch(item_sample)
        if compact is not None:
            sample = compact.group("sample").strip()
            orientation = orientation or compact.group("orientation").upper()
    return {
        "material_id": str(item.get("Item_ID") or sample or slug(material_name)),
        "material_name": str(material_name),
        "sample_id": None if sample in (None, "") else str(sample),
        "state": None if owner_state in (None, "") else str(owner_state),
        "region": None if region in (None, "") else str(region),
        "location": None if location in (None, "") else str(location),
        "orientation": orientation or None,
        "role": str(item.get("Role") or "Target"),
    }


def _claim(
    *, source: str, paper_key: str, uid: str, axis: str, owner: dict[str, Any],
    semantic_key: Any, name_raw: Any, value: dict[str, Any], unit_raw: str | None,
    condition: Any, origin: str, evidence: Iterable[str], raw_path: str,
    raw: dict[str, Any],
) -> dict[str, Any]:
    return {
        "uid": uid,
        "source": source,
        "paper_key": paper_key,
        "axis": axis,
        "owner": owner,
        "semantic_key": slug(semantic_key),
        "name_raw": str(name_raw or semantic_key),
        "value": value,
        "unit_raw": unit_raw,
        "condition": _condition_text(condition),
        "origin": origin,
        "evidence": list(dict.fromkeys(str(row).strip() for row in evidence if str(row).strip())),
        "raw_path": raw_path,
        "raw": raw,
    }


def flatten_v11(document: dict[str, Any], *, source: str, paper_key: str) -> list[dict[str, Any]]:
    """Project a v11 document to atomic comparison claims."""

    claims: list[dict[str, Any]] = []

    def add(**kwargs: Any) -> None:
        kwargs["uid"] = f"{source}_{len(claims) + 1:05d}"
        claims.append(_claim(source=source, paper_key=paper_key, **kwargs))

    for item_index, item in enumerate(document.get("items") or []):
        if not isinstance(item, dict):
            continue
        extracted = item.get("Extracted_Data") or {}
        composition = extracted.get("Composition") or {}
        for obs_index, observation in enumerate(composition.get("Composition_Observations") or []):
            if not isinstance(observation, dict):
                continue
            observation_sample = observation.get("sample_id")
            location = (
                observation_sample
                if _microanalysis_location(observation_sample)
                else observation.get("location_raw")
            )
            owner = _owner(
                item,
                sample_id=(
                    None
                    if _microanalysis_location(observation_sample)
                    else observation_sample
                ),
                state=observation.get("material_state"),
                region=observation.get("region_raw"),
                location=location,
            )
            condition = None
            for component_index, component in enumerate(observation.get("components") or []):
                if not isinstance(component, dict):
                    continue
                value, unit = _value(component)
                name = component.get("canonical_name") or component.get("name_raw")
                add(
                    axis="Composition", owner=owner,
                    semantic_key=f"composition_element_{name}", name_raw=name,
                    value=value, unit_raw=unit or observation.get("basis"), condition=condition,
                    origin=_origin(component.get("data_nature"), observation.get("source_type")),
                    evidence=_evidence(component) or _evidence(observation),
                    raw_path=f"items[{item_index}].Composition[{obs_index}].components[{component_index}]",
                    raw=component,
                )

        route = ((extracted.get("Processing") or {}).get("Process_Route") or {})
        stages = route.get("stages") or route.get("candidate_stages") or []
        for stage_index, stage in enumerate(stages):
            if not isinstance(stage, dict):
                continue
            stage_owner = _owner(item)
            code = stage.get("process_code") or stage.get("process_name") or stage.get("process_name_raw")
            if code:
                stage_value = {"kind": "categorical", "raw": str(code), "number": None, "min": None, "max": None, "operator": None, "bound": None, "stddev": None, "text": str(code)}
                add(
                    axis="Processing", owner=stage_owner, semantic_key=f"process_stage_{code}",
                    name_raw=code, value=stage_value, unit_raw=None,
                    condition=None, origin=_origin(item.get("Data_Nature")),
                    evidence=_evidence(stage), raw_path=f"items[{item_index}].Processing.stages[{stage_index}]",
                    raw=stage,
                )
            for parameter_index, parameter in enumerate(stage.get("parameters") or []):
                if not isinstance(parameter, dict):
                    continue
                status = fold(parameter.get("status"))
                value, unit = _value(parameter)
                if status in {"not reported", "unknown", "ambiguous"} and not value.get("raw") and not _numeric_values(value):
                    continue
                name = parameter.get("parameter_code") or parameter.get("parameter_name_raw")
                if not name or slug(name) == "raw_unmapped_parameter":
                    name = parameter.get("parameter_name_raw") or name
                add(
                    axis="Processing", owner=stage_owner, semantic_key=name, name_raw=name,
                    value=value, unit_raw=unit,
                    condition=parameter.get("condition_label"),
                    origin=_origin(status, item.get("Data_Nature")),
                    evidence=_evidence(parameter) or _evidence(stage),
                    raw_path=f"items[{item_index}].Processing.stages[{stage_index}].parameters[{parameter_index}]",
                    raw={
                        **parameter,
                        "_stage_process_code": code,
                        "_stage_parameter_profile": stage.get("parameter_profile"),
                    },
                )
            for equipment_index, equipment in enumerate(stage.get("equipment_entities") or []):
                if not isinstance(equipment, dict):
                    continue
                name = equipment.get("raw_name") or equipment.get("name")
                if not name:
                    continue
                value = {"kind": "categorical", "raw": str(name), "number": None, "min": None, "max": None, "operator": None, "bound": None, "stddev": None, "text": str(name)}
                add(
                    axis="Processing", owner=stage_owner, semantic_key="process_equipment",
                    name_raw="process equipment", value=value, unit_raw=None,
                    condition=None, origin=_origin(item.get("Data_Nature")),
                    evidence=_evidence(equipment) or _evidence(stage),
                    raw_path=f"items[{item_index}].Processing.stages[{stage_index}].equipment[{equipment_index}]",
                    raw=equipment,
                )

        structure = extracted.get("Structure") or {}
        for observation_index, observation in enumerate(structure.get("Structure_Observations") or []):
            if not isinstance(observation, dict):
                continue
            obs_owner = _owner(
                item, sample_id=observation.get("sample_id"), state=observation.get("material_state"),
                region=observation.get("region_raw"),
            )
            base_path = f"items[{item_index}].Structure[{observation_index}]"

            def add_feature(feature: dict[str, Any], path: str, *, prefix: str = "") -> None:
                value, unit = _value(feature)
                name = feature.get("canonical_name") or feature.get("feature_name_raw") or prefix
                add(
                    axis="Structure", owner=obs_owner, semantic_key=name, name_raw=feature.get("feature_name_raw") or name,
                    value=value, unit_raw=unit, condition=None,
                    origin=_origin(feature.get("data_nature"), observation.get("source_type")),
                    evidence=_evidence(feature) or _evidence(observation), raw_path=path, raw=feature,
                )

            for feature_index, feature in enumerate(observation.get("features") or []):
                if isinstance(feature, dict):
                    add_feature(feature, f"{base_path}.features[{feature_index}]")
            for entity_index, entity in enumerate(observation.get("entities") or []):
                if not isinstance(entity, dict):
                    continue
                entity_name = entity.get("canonical_name") or entity.get("name_raw")
                if entity_name and not (entity.get("features") or []):
                    presence = {"kind": "categorical", "raw": str(entity.get("name_raw") or entity_name), "number": None, "min": None, "max": None, "operator": None, "bound": None, "stddev": None, "text": str(entity.get("name_raw") or entity_name)}
                    add(
                        axis="Structure", owner=obs_owner, semantic_key=f"{entity_name}_presence",
                        name_raw=entity.get("name_raw") or entity_name, value=presence, unit_raw=None,
                        condition=None,
                        origin=_origin(observation.get("source_type"), item.get("Data_Nature")),
                        evidence=_evidence(entity) or _evidence(observation),
                        raw_path=f"{base_path}.entities[{entity_index}]", raw=entity,
                    )
                for feature_index, feature in enumerate(entity.get("features") or []):
                    if isinstance(feature, dict):
                        add_feature(feature, f"{base_path}.entities[{entity_index}].features[{feature_index}]", prefix=str(entity_name or "entity"))
            for feature_index, feature in enumerate(observation.get("additional_features") or []):
                if isinstance(feature, dict):
                    add_feature(feature, f"{base_path}.additional_features[{feature_index}]")

        for char_index, char in enumerate(structure.get("Characterization") or []):
            if not isinstance(char, dict):
                continue
            char_owner = _owner(item, state=char.get("material_state"), region=char.get("sample_location_raw"))
            method_class = char.get("method_class") or "method"
            method_raw = char.get("method_raw") or method_class
            # Characterization is one scientific method assertion.  Instrument,
            # operating condition, preparation, and location are provenance
            # fields of that assertion, not independent modalities.  Emitting
            # each nested field as a separate claim made a correctly structured
            # final.json look like a hallucinated list of methods and unfairly
            # penalized the production output against the expert ledger.
            instrument = char.get("instrument") or char.get("equipment") or char.get("equipment_raw")
            value_text = _condition_text(instrument or method_raw)
            value = {"kind": "categorical", "raw": value_text, "number": None, "min": None, "max": None, "operator": None, "bound": None, "stddev": None, "text": value_text}
            add(
                axis="Characterization", owner=char_owner,
                semantic_key=f"{method_class}_method", name_raw=method_raw,
                value=value, unit_raw=None, condition=None,
                origin=_origin(item.get("Data_Nature")), evidence=_evidence(char),
                raw_path=f"items[{item_index}].Characterization[{char_index}]", raw=char,
            )

        for property_index, prop in enumerate(extracted.get("Properties") or []):
            if not isinstance(prop, dict):
                continue
            name = (
                prop.get("Canonical_Property") or prop.get("canonical_property")
                or prop.get("Property_Subtype") or prop.get("property_subtype")
                or prop.get("Property_Name_Raw") or prop.get("property_name_raw")
            )
            if not name:
                continue
            value, unit = _value(prop, parse_unstructured_numeric=True)
            add(
                axis="Properties", owner=_owner(
                    item, test_condition=prop.get("Test_Condition")
                ), semantic_key=name,
                name_raw=prop.get("Property_Name_Raw") or name, value=value, unit_raw=unit,
                condition=prop.get("Test_Condition"),
                origin=_property_origin(prop, item),
                evidence=_evidence(prop), raw_path=f"items[{item_index}].Properties[{property_index}]",
                raw=prop,
            )
    return deduplicate_claims(claims)


def load_expert_claims(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        source = json.loads(line)
        rows.append(
            {
                "uid": source["claim_id"], "source": "expert", "paper_key": source["paper_key"],
                "axis": source["axis"], "owner": source["owner"],
                "semantic_key": source["semantic_key"], "name_raw": source["name_raw"],
                "value": source["value"], "unit_raw": source.get("unit_raw"),
                "condition": _condition_text(source.get("condition")), "origin": source["origin"],
                "evidence": [row.get("quote", "") for row in source.get("evidence") or []],
                "raw_path": str(path), "raw": source,
            }
        )
    return rows


def _process_context(claim: dict[str, Any]) -> str:
    parts = [
        str(claim.get("semantic_key") or ""),
        str(claim.get("name_raw") or ""),
        str(claim.get("condition") or ""),
    ]
    parts.extend(str(row) for row in claim.get("evidence") or [])
    raw = claim.get("raw")
    if isinstance(raw, dict):
        parts.extend(
            str(raw.get(key) or "")
            for key in ("_stage_process_code", "_stage_parameter_profile")
        )
    return fold(" ".join(parts))


@lru_cache(maxsize=32768)
def _thermal_process_operation(context: str) -> str | None:
    return next(
        (
            operation
            for operation, pattern in _THERMAL_PROCESS_OPERATIONS
            if pattern.search(context)
        ),
        None,
    )


def _thermal_process_dimension(
    claim: dict[str, Any], value: str
) -> str | None:
    """Fold time/temperature only within the same thermal operation."""

    is_time = value in _THERMAL_TIME_KEYS or value.endswith(
        ("_time", "_holding_time", "_dwell_time")
    )
    is_temperature = (
        value in _THERMAL_TEMPERATURE_KEYS or value.endswith("_temperature")
    )
    if not is_time and not is_temperature:
        return None
    context = _process_context(claim)
    operation = _thermal_process_operation(context)
    if operation is None:
        return None
    if is_time:
        return f"thermal_{operation}_time"
    if is_temperature:
        return f"thermal_{operation}_temperature"
    return None


def _energy_source_condition(claim: dict[str, Any]) -> str | None:
    condition = fold(claim.get("condition"))
    exact = _ENERGY_SOURCE_CONDITIONS.get(condition)
    if exact is not None:
        return exact
    # Production conditions may retain both the energy-source discriminator
    # and a source-backed process environment (for example
    # ``laser | LHW-DED deposition in inert argon``). Only an exact delimited
    # segment is treated as the energy source; free-text token containment
    # would incorrectly classify phrases such as "laser hot-wire process".
    for segment in re.split(r"\s*[|;]\s*", condition):
        resolved = _ENERGY_SOURCE_CONDITIONS.get(segment.strip())
        if resolved is not None:
            return resolved
    return None


def _matching_condition(claim: dict[str, Any]) -> str:
    # Accept both already-flattened strings and structured expert conditions.
    # Keeping this normalization at the matching boundary prevents callers
    # that construct claims directly (rather than through ``load_expert_claims``)
    # from reintroducing Python-dict serialization into condition scoring.
    condition = _condition_text(claim.get("condition"))
    if _energy_source_condition(claim) is None:
        return condition
    residual = [
        segment.strip()
        for segment in re.split(r"\s*[|;]\s*", condition)
        if segment.strip()
        and fold(segment) not in _ENERGY_SOURCE_CONDITIONS
    ]
    return " | ".join(residual)


def _condition_with_owner_dimensions(claim: dict[str, Any]) -> str:
    """Include source-proven owner dimensions in strict condition matching.

    Digitized tensile rows keep X/Y/Z in the public owner coordinate (and in
    ``Test_Condition.Specimen``) while the flattened system condition is often
    just ``tensile test``.  Expert claims may spell the same coordinate as
    ``tensile test; X orientation``.  Treating the owner coordinate as an
    equivalent condition dimension avoids false strict conflicts without
    weakening a real orientation disagreement.
    """

    condition = _matching_condition(claim)
    owner = claim.get("owner") or {}
    orientation = str(owner.get("orientation") or "").strip().upper()
    if orientation not in {"X", "Y", "Z"}:
        return condition
    if re.search(
        rf"(?i)(?<![A-Z]){orientation}(?:\s+(?:build\s+)?(?:orientation|direction))?(?![A-Z])",
        condition,
    ):
        return condition
    return (
        f"{condition}; {orientation} orientation"
        if condition
        else f"{orientation} orientation"
    )


def _thermal_variant_temperature(claim: dict[str, Any]) -> float | None:
    key = slug(claim.get("semantic_key") or claim.get("name_raw"))
    match = re.search(r"(?:^|_)(?:s|ha)(\d{3,4})(?:_|$)", key)
    return float(match.group(1)) if match else None


def _reported_temperatures(claim: dict[str, Any]) -> tuple[float, ...]:
    evidence = " ".join(str(row) for row in claim.get("evidence") or [])
    return tuple(
        float(row)
        for row in re.findall(
            r"([-+]?\d+(?:\.\d+)?)\s*(?:\^?\s*\\circ|[°º])\s*c\b",
            evidence,
            flags=re.IGNORECASE,
        )
    )


def _thermal_variant_compatible(
    left: dict[str, Any], right: dict[str, Any]
) -> bool:
    left_target = _thermal_variant_temperature(left)
    right_target = _thermal_variant_temperature(right)
    if left_target is not None and right_target is not None:
        return math.isclose(left_target, right_target, abs_tol=2.0)
    for target, other in ((left_target, right), (right_target, left)):
        if target is None:
            continue
        reported = _reported_temperatures(other)
        if reported and not any(
            math.isclose(target, value, abs_tol=2.0) for value in reported
        ):
            return False
    return True


def _canonical_semantic(claim: dict[str, Any]) -> str:
    value = slug(claim.get("semantic_key") or claim.get("name_raw"))
    name = slug(claim.get("name_raw"))
    if claim.get("axis") == "Properties":
        for candidate in (value, name):
            if _RELATIVE_PROPERTY_SEMANTIC.search(candidate):
                return candidate
        for candidate in (value, name):
            if candidate in _PROPERTY_ALIASES:
                return _PROPERTY_ALIASES[candidate]
            for alias, canonical in _PROPERTY_ALIASES.items():
                if re.search(
                    rf"(?:^|_){re.escape(alias)}(?:_|$)", candidate
                ):
                    return canonical
    if claim.get("axis") == "Composition":
        tokens = [row for row in re.split(r"_+", value) if row]
        ignored = {"composition", "element", "bulk", "nominal", "content", "fraction", "mass", "atomic", "wt", "at", "feedstock", "measured"}
        elements = [row for row in tokens if row not in ignored and 1 <= len(row) <= 3]
        if elements:
            return f"composition_element_{elements[-1]}"
    if claim.get("axis") == "Characterization":
        # Expert GT uses descriptive keys (e.g. ``powder_sem_instrument``),
        # while Alpha25 emits the provider's method class (e.g. ``sem_method``).
        # Normalize both to the instrument family; model/equipment details stay
        # in the value and evidence fields and are still checked separately.
        candidates = [value, name]
        for candidate in candidates:
            for alias, family in _CHARACTERIZATION_METHOD_ALIASES.items():
                if alias in candidate:
                    return f"{family}_method"
    if claim.get("axis") == "Processing" and not value.startswith("process_stage_"):
        while _PROCESS_PREFIX.match(value):
            value = _PROCESS_PREFIX.sub("", value, count=1)
        value = re.sub(r"_range$", "", value)
        thermal_dimension = _thermal_process_dimension(claim, value)
        if thermal_dimension is not None:
            return thermal_dimension
        energy_source = _energy_source_condition(claim)
        if value == "power" and energy_source is not None:
            return f"{energy_source}_power"
        if re.fullmatch(
            r"(?:laser_)?(?:beam_)?spot_(?:size|diameter)|"
            r"(?:laser_)?beam_(?:size|diameter)",
            value,
        ):
            return "beam_diameter"
        if value in {
            "hatch_space",
            "hatch_spacing",
            "scan_spacing",
            "scanning_spacing",
        }:
            return "hatch_spacing"
        if value in {
            "build_plate_temperature",
            "build_plate_preheat",
            "substrate_temperature",
            "preheat_temperature",
        }:
            return "preheat_temperature"
        if value in {
            "heating_temperature",
            "heat_treatment_temperature",
            "process_temperature",
            "treatment_temperature",
            "thermal_environment_temperature",
        }:
            return "process_temperature"
        if value in {
            "oxygen_content",
            "oxygen_concentration",
            "oxygen_level",
            "oxygen_limit",
        }:
            return "oxygen_content"
        if value in {
            "duration",
            "time",
            "hold_time",
            "holding_time",
            "delay_time",
            "exposure_time",
        }:
            return "duration"
        if value in {
            "atmosphere",
            "environment",
            "build_environment",
            "deposition_environment",
        }:
            return "atmosphere"
        if value in {
            "energy_density",
            "volumetric_energy_density",
            "volume_energy_density",
        }:
            return "energy_density"
        if value in {"feed_rate", "wire_feed_rate"}:
            return "wire_feed_rate"
    return value


def semantic_score(left: dict[str, Any], right: dict[str, Any]) -> float:
    if left.get("axis") != right.get("axis"):
        return 0.0
    if left.get("axis") == "Processing" and not _thermal_variant_compatible(
        left, right
    ):
        return 0.0
    left_key = _canonical_semantic(left)
    right_key = _canonical_semantic(right)
    if left_key == right_key:
        return 1.0
    if left.get("axis") == "Composition":
        left_element = left_key.removeprefix("composition_element_")
        right_element = right_key.removeprefix("composition_element_")
        if left_element == right_element:
            return 0.98
    left_tokens = _semantic_tokens(left)
    right_tokens = _semantic_tokens(right)
    score = _jaccard(left_tokens, right_tokens)
    if left_tokens and right_tokens and (left_tokens <= right_tokens or right_tokens <= left_tokens):
        score = max(score, min(len(left_tokens), len(right_tokens)) / max(len(left_tokens), len(right_tokens)))
    if score >= 0.15:
        evidence = evidence_score(left, right)
        if evidence >= 0.55:
            score = max(score, min(0.95, 0.35 + 0.65 * evidence))
    return score


def _semantic_tokens(claim: dict[str, Any]) -> set[str]:
    value = ""
    if claim.get("axis") in {"Processing", "Structure", "Characterization"}:
        value = _source_value_raw(claim)
    return _tokens(f"{_canonical_semantic(claim)} {claim.get('name_raw', '')} {value}")


def _source_value_raw(claim: dict[str, Any]) -> Any:
    """Return the literal source presentation retained by one claim.

    Semantic scoring historically included this literal for processing,
    structure, and characterization records. Canonical numeric display must
    not silently change that semantic score; numeric scale compatibility is
    evaluated independently by ``value_score``.
    """

    raw_record = claim.get("raw")
    if isinstance(raw_record, dict):
        nested_value = raw_record.get("Value")
        if isinstance(nested_value, dict):
            for key in ("value_raw", "Value_Raw"):
                if nested_value.get(key) is not None:
                    return nested_value.get(key)
            nested_scalar = nested_value.get("value")
            if not isinstance(nested_scalar, (dict, list, tuple)) and nested_scalar is not None:
                return nested_scalar
        for key in ("value_raw", "Value_Raw"):
            if raw_record.get(key) is not None:
                return raw_record.get(key)
        top_level_scalar = raw_record.get("value")
        if (
            not isinstance(top_level_scalar, (dict, list, tuple))
            and top_level_scalar is not None
        ):
            return top_level_scalar
    selected = claim.get("value") or {}
    return selected.get("text") or selected.get("raw") or ""


@lru_cache(maxsize=32768)
def _cached_evidence_parts(value: str) -> tuple[str, frozenset[str]]:
    return fold(value), frozenset(_tokens(value))


def evidence_score(left: dict[str, Any], right: dict[str, Any]) -> float:
    best = 0.0
    for a in left.get("evidence") or []:
        a_fold, a_tokens = _cached_evidence_parts(str(a))
        if not a_fold:
            continue
        for b in right.get("evidence") or []:
            b_fold, b_tokens = _cached_evidence_parts(str(b))
            if not b_fold:
                continue
            if min(len(a_fold), len(b_fold)) >= 12 and (a_fold in b_fold or b_fold in a_fold):
                best = max(best, min(len(a_fold), len(b_fold)) / max(len(a_fold), len(b_fold)))
            best = max(best, _jaccard(set(a_tokens), set(b_tokens)))
    return best


def _unit(value: Any) -> str:
    raw = unicodedata.normalize("NFKC", str(value or ""))
    raw = re.sub(
        r"\\(?:text|mathrm|operatorname)\s*\{([^{}]*)\}",
        r"\1",
        raw,
    )
    raw = raw.replace("{", "").replace("}", "").replace("$", "")
    raw = raw.replace(r"\mu", "u").replace("µ", "u").replace("μ", "u")
    raw = raw.replace("−", "-").replace("⁻", "^-").replace("²", "2")
    raw_compact = re.sub(r"\s+", "", raw).casefold()
    text = fold(raw).replace("microm", "um")
    compact = text.replace(" ", "")
    aliases = {
        "wt": "percent", "wt percent": "percent", "wt pct": "percent", "wt%": "percent",
        "at": "percent", "at percent": "percent", "at pct": "percent", "%": "percent",
        "mpa": "mpa", "gpa": "gpa", "c": "degc", "degree c": "degc", "deg c": "degc",
        "um": "um", "mum": "um", "micron": "um", "microns": "um", "mm": "mm",
        "w": "w", "kw": "kw", "a": "a", "ma": "ma",
    }
    if "%" in raw_compact or raw_compact in {
        "wt", "wtpercent", "wtpct", "at", "atpercent", "atpct", "percent", "pct"
    }:
        return "percent"
    if compact in {"um", "mum", "micron", "microns"}:
        return "um"
    if compact in {"um2", "um^2", "um-2", "um^-2"}:
        return "um^-2"
    if compact in {"m2", "m^2", "m-2", "m^-2"}:
        return "m^-2"
    if compact in {"g/cm3", "gcm3", "g/cc", "gcc"}:
        return "g/cm3"
    if raw_compact.replace("^", "") in {"j/mm3", "jmm-3", "j·mm-3"}:
        return "j/mm3"
    if compact in {"cycle", "cycles"}:
        return "cycle"
    if compact in {"s", "sec", "second", "seconds"}:
        return "s"
    if compact in {"min", "minute", "minutes"}:
        return "min"
    if compact in {"h", "hr", "hrs", "hour", "hours"}:
        return "h"
    hardness = re.fullmatch(r"hv(?:ickers)?([0-9]+(?:\.[0-9]+)?)?", compact)
    if hardness:
        load = hardness.group(1)
        return f"hv{load}" if load else "hv"
    return aliases.get(text, aliases.get(compact, text))


def _converted_numbers(claim: dict[str, Any]) -> tuple[tuple[float, ...], str]:
    numbers = _numeric_values(claim.get("value") or {})
    unit = _unit(claim.get("unit_raw"))
    if unit == "gpa":
        return tuple(row * 1000.0 for row in numbers), "mpa"
    if unit == "kw":
        return tuple(row * 1000.0 for row in numbers), "w"
    if unit == "ma":
        return tuple(row / 1000.0 for row in numbers), "a"
    if unit == "k":
        return tuple(row - 273.15 for row in numbers), "degc"
    if unit == "um":
        return tuple(row / 1000.0 for row in numbers), "mm"
    if unit == "h":
        return tuple(row * 3600.0 for row in numbers), "s"
    if unit == "min":
        return tuple(row * 60.0 for row in numbers), "s"
    return numbers, unit


def _numeric_center_and_stddev(claim: dict[str, Any]) -> tuple[float | None, float | None]:
    """Return the reported numeric center and uncertainty, when present.

    The uncertainty is deliberately kept separate from the value interval.
    Two measurements with overlapping ``center ± stddev`` intervals are not
    interchangeable observations: the center identifies the table cell and
    the uncertainty describes its spread.  The evaluator therefore uses this
    pair for a conservative center-first comparison whenever both claims
    report it.
    """

    value = claim.get("value") or {}
    numbers, _ = _converted_numbers(claim)
    center = numbers[0] if numbers and value.get("kind") not in {"range", "inequality"} else None
    stddev = value.get("stddev")
    if not isinstance(stddev, (int, float)) or isinstance(stddev, bool):
        return center, None
    unit = _unit(claim.get("unit_raw"))
    converted_stddev = float(stddev)
    if unit == "gpa":
        converted_stddev *= 1000.0
    elif unit == "kw":
        converted_stddev *= 1000.0
    elif unit == "ma":
        converted_stddev /= 1000.0
    elif unit == "um":
        converted_stddev /= 1000.0
    elif unit == "h":
        converted_stddev *= 3600.0
    elif unit == "min":
        converted_stddev *= 60.0
    return center, converted_stddev


def _numeric_rounding_tolerance(claim: dict[str, Any]) -> float:
    """Return half of the center value's displayed rounding unit.

    A prose value such as ``0.48 ± 0.05`` is a rounded presentation of a
    more precise table value such as ``0.484 ± 0.052``.  Using the displayed
    decimal resolution as an absolute tolerance preserves that match without
    reopening broad percentage-based matches for integer-valued cells.
    """

    selected_raw = (claim.get("value") or {}).get("raw")
    source_raw: Any = selected_raw
    source_unit: Any = claim.get("unit_raw")
    raw_record = claim.get("raw")
    if isinstance(raw_record, dict):
        nested_value = raw_record.get("Value")
        if isinstance(nested_value, dict):
            source_raw = (
                nested_value.get("value_raw")
                if nested_value.get("value_raw") is not None
                else source_raw
            )
            source_unit = nested_value.get("unit_raw") or source_unit
        else:
            source_raw = next(
                (
                    raw_record.get(key)
                    for key in ("value_raw", "Value_Raw")
                    if raw_record.get(key) is not None
                ),
                source_raw,
            )
            source_unit = (
                raw_record.get("unit_raw")
                or raw_record.get("Unit_Raw")
                or source_unit
            )
    match = re.search(r"[-+]?\d+(?:\.\d+)?", str(source_raw or ""))
    if not match:
        return 0.0
    center_text = match.group(0)
    if "." not in center_text:
        tolerance = 0.5
    else:
        tolerance = 0.5 * (10 ** -len(center_text.partition(".")[2]))
    # Source presentation determines resolution. Convert that resolution once
    # into the same common unit used by _converted_numbers.
    unit = _unit(source_unit)
    if unit in {"gpa", "kw"}:
        tolerance *= 1000.0
    elif unit == "ma":
        tolerance /= 1000.0
    elif unit == "um":
        tolerance /= 1000.0
    elif unit == "h":
        tolerance *= 3600.0
    elif unit == "min":
        tolerance *= 60.0
    return tolerance


def value_score(left: dict[str, Any], right: dict[str, Any]) -> float:
    left_numbers, left_unit = _converted_numbers(left)
    right_numbers, right_unit = _converted_numbers(right)
    if left_unit and right_unit and left_unit != right_unit:
        return 0.0
    if left_numbers and right_numbers:
        if len(left_numbers) != len(right_numbers):
            return 0.0
        left_kind = fold((left.get("value") or {}).get("kind"))
        right_kind = fold((right.get("value") or {}).get("kind"))
        if (left_kind == "inequality") != (right_kind == "inequality"):
            return 0.0
        left_center, left_stddev = _numeric_center_and_stddev(left)
        right_center, right_stddev = _numeric_center_and_stddev(right)
        if (
            left_center is not None
            and right_center is not None
            and left_stddev is not None
            and right_stddev is not None
        ):
            # Center values identify the reported table cells.  Do not use
            # overlapping uncertainty intervals as a substitute for equality:
            # e.g. 817 ± 8.68 must not pair with 825.3 ± 3.10.  A 0.5%
            # relative tolerance plus displayed-rounding tolerance still
            # accepts 0.48 ± 0.05 versus 0.484 ± 0.052 and similar prose/table
            # presentations.
            center_closeness = [
                math.isclose(
                    a,
                    b,
                    rel_tol=0.005,
                    abs_tol=max(
                        1e-6,
                        _numeric_rounding_tolerance(left),
                        _numeric_rounding_tolerance(right),
                    ),
                )
                for a, b in zip((left_center,), (right_center,))
            ]
            return 1.0 if all(center_closeness) else 0.0
        if left_unit == right_unit == "degc":
            closeness = [
                math.isclose(a, b, rel_tol=0.001, abs_tol=2.0)
                for a, b in zip(left_numbers, right_numbers)
            ]
        else:
            closeness = [
                math.isclose(
                    a,
                    b,
                    rel_tol=0.03,
                    abs_tol=max(1e-6, 0.005 * max(abs(a), abs(b), 1.0)),
                )
                for a, b in zip(left_numbers, right_numbers)
            ]
        return 1.0 if all(closeness) else 0.0
    if bool(left_numbers) != bool(right_numbers):
        return 0.0
    left_text = _tokens((left.get("value") or {}).get("text") or (left.get("value") or {}).get("raw"))
    right_text = _tokens((right.get("value") or {}).get("text") or (right.get("value") or {}).get("raw"))
    if not left_text and not right_text:
        return 0.7
    score = _jaccard(left_text, right_text)
    if left_text and right_text and (left_text <= right_text or right_text <= left_text):
        score = max(score, min(len(left_text), len(right_text)) / max(len(left_text), len(right_text)))
    # Characterization values are often represented at different granularity:
    # one side keeps the instrument (``Bruker D8 Advanced XRD``), while the
    # other keeps the method label plus specimen context.  Once the semantic
    # matcher has established the same modality, a shared distinctive token
    # (instrument/model or modality) is sufficient for loose compatibility;
    # strict matching still checks owner/state/condition independently.
    if (
        left.get("axis") == right.get("axis") == "Characterization"
        and _canonical_semantic(left) == _canonical_semantic(right)
        and left_text
        and right_text
    ):
        shared = {
            token for token in left_text & right_text if len(token) >= 3
        }
        if shared:
            score = max(score, 0.65)
    return score


def _material_designations(value: Any) -> set[str]:
    """Return explicit grade/designation tokens, not broad material classes."""

    text = fold(value)
    return {
        f"{family}:{grade}"
        for family, grade in re.findall(
            r"\b(alloy|grade|inconel)\s+([a-z]*\d[a-z0-9.-]*)\b", text
        )
    }


def _reference_author_keys(owner: dict[str, Any]) -> set[str]:
    """Normalize source-style ``Surname et al.`` and ledger ``Surname2020``."""

    keys: set[str] = set()
    for value in (owner.get("sample_id"), owner.get("material_id")):
        text = fold(value)
        keys.update(
            match.group(1)
            for match in re.finditer(r"\b([a-z][a-z.-]{2,})\s+et\s+al\b", text)
        )
        keys.update(
            match.group(1)
            for match in re.finditer(
                r"\b([a-z][a-z.-]{2,}?)(?:19|20)\d{2}[a-z]?\b", text
            )
        )
    return keys


def _reference_sample_discriminators(
    owner: dict[str, Any], author_keys: set[str]
) -> set[str]:
    """Keep process/state sample tokens while removing citation presentation."""

    tokens: set[str] = set()
    for token in fold(owner.get("sample_id")).split():
        token = re.sub(r"(?:19|20)\d{2}[a-z]?$", "", token)
        if token:
            tokens.add(token)
    designation_tokens = {
        token
        for designation in _material_designations(owner.get("material_name"))
        for token in designation.split(":")
    }
    return tokens - designation_tokens - author_keys - {
        "al",
        "cited",
        "et",
        "fabricated",
        "literature",
        "printed",
        "processed",
        "reference",
        "reported",
        "sample",
        "specimen",
    }


def _reference_designation_alias(
    left_owner: dict[str, Any], right_owner: dict[str, Any]
) -> bool:
    left_role = fold(left_owner.get("role"))
    right_role = fold(right_owner.get("role"))
    if left_role != "reference" or right_role != "reference":
        return False
    left_state = _owner_dimension("state", left_owner.get("state"))
    right_state = _owner_dimension("state", right_owner.get("state"))
    if left_state and right_state and left_state != right_state:
        return False
    same_designation = bool(
        _material_designations(left_owner.get("material_name"))
        & _material_designations(right_owner.get("material_name"))
    )
    if not same_designation:
        return False
    if left_state and right_state:
        return True

    left_authors = _reference_author_keys(left_owner)
    right_authors = _reference_author_keys(right_owner)
    shared_authors = left_authors & right_authors
    if not shared_authors:
        return False
    return bool(
        _reference_sample_discriminators(left_owner, shared_authors)
        & _reference_sample_discriminators(right_owner, shared_authors)
    )


def _project_owner_dimensions(claim: dict[str, Any]) -> dict[str, str]:
    """Separate a material specimen, morphology region, and EDS location."""

    owner = claim.get("owner") or {}
    dimensions = {
        key: _owner_dimension(key, owner.get(key))
        for key in ("sample_id", "state", "region", "orientation")
    }
    dimensions["location"] = ""
    if claim.get("axis") != "Composition":
        return dimensions

    locations = [
        location
        for location in (_microanalysis_location(owner.get("location")),)
        if location
    ]
    for key in ("sample_id", "region"):
        location = _microanalysis_location(owner.get(key))
        if not location:
            continue
        locations.append(location)
        dimensions[key] = ""
    unique_locations = list(dict.fromkeys(locations))
    if len(unique_locations) == 1:
        dimensions["location"] = unique_locations[0]
    elif unique_locations:
        dimensions["location"] = " | ".join(sorted(unique_locations))
    return dimensions


def owner_score(left: dict[str, Any], right: dict[str, Any]) -> float:
    left_owner = left.get("owner") or {}
    right_owner = right.get("owner") or {}
    left_dimensions = _project_owner_dimensions(left)
    right_dimensions = _project_owner_dimensions(right)
    reference_alias = _reference_designation_alias(left_owner, right_owner)
    scores: list[float] = []
    for key in ("sample_id", "state", "location", "region", "orientation"):
        a, b = left_dimensions[key], right_dimensions[key]
        if a and b:
            scores.append(
                1.0
                if (
                    a == b
                    or (key != "location" and (a in b or b in a))
                    or (key == "sample_id" and reference_alias)
                )
                else _jaccard(_tokens(a), _tokens(b))
            )
        elif a or b:
            scores.append(0.35)
    material_score = (
        1.0
        if reference_alias
        else _jaccard(
            _tokens(left_owner.get("material_name")),
            _tokens(right_owner.get("material_name")),
        )
    )
    if material_score:
        scores.append(material_score)
    if fold(left_owner.get("role")) and fold(right_owner.get("role")):
        scores.append(1.0 if fold(left_owner.get("role")) == fold(right_owner.get("role")) else 0.0)
    return sum(scores) / len(scores) if scores else 0.5


def owner_conflict(left: dict[str, Any], right: dict[str, Any]) -> bool:
    """Return true for explicit owner dimensions that cannot describe one sample."""

    left_owner = left.get("owner") or {}
    right_owner = right.get("owner") or {}
    left_dimensions = _project_owner_dimensions(left)
    right_dimensions = _project_owner_dimensions(right)
    reference_alias = _reference_designation_alias(left_owner, right_owner)
    for key in ("sample_id", "state", "location", "region", "orientation"):
        a, b = left_dimensions[key], right_dimensions[key]
        if not a or not b:
            continue
        if key == "sample_id" and reference_alias:
            continue
        if a == b:
            continue
        if key == "location":
            return True
        if a in b or b in a:
            continue
        if _jaccard(_tokens(a), _tokens(b)) >= 0.6:
            continue
        return True
    left_role, right_role = fold(left_owner.get("role")), fold(right_owner.get("role"))
    return bool(left_role and right_role and left_role != right_role)


def _owner_dimension(key: str, value: Any) -> str:
    text = fold(value)
    if text in {"not reported", "unknown", "none", "n a"}:
        return ""
    if key == "state":
        aliases = {
            "feedstock": "powder",
            "feedstock powder": "powder",
            "as built condition": "as built",
            "as fabricated": "as built",
            "as printed": "as built",
            "as deposited": "as built",
        }
        normalized = aliases.get(text, text)
        if normalized in {"heat treated", "post treated", "post processed"}:
            return "treated"
        return normalized
    return text


def condition_score(left: dict[str, Any], right: dict[str, Any]) -> float:
    a, b = _condition_with_owner_dimensions(left), _condition_with_owner_dimensions(right)
    a_tokens, b_tokens = _tokens(a), _tokens(b)
    if not a_tokens and not b_tokens:
        return 1.0
    if not a_tokens or not b_tokens:
        return 0.25

    def profile(text: str) -> dict[str, Any]:
        folded = fold(text)
        temperatures: set[float | str] = set()
        if re.search(r"(?i)\b(?:rt|room\s+temperature|ambient\s+temperature)\b", text):
            temperatures.add("room")
        for match in re.finditer(
            r"(?i)([-+]?\d+(?:\.\d+)?)\s*(?:°\s*C|degrees?\s*C|deg\.?\s*C|C)\b",
            text,
        ):
            temperatures.add(round(float(match.group(1)), 3))
        for match in re.finditer(r"(?i)([-+]?\d+(?:\.\d+)?)\s*K\b", text):
            temperatures.add(round(float(match.group(1)) - 273.15, 3))
        times = {
            (round(float(match.group(1)), 6), match.group(2).casefold()[0])
            for match in re.finditer(
                r"(?i)([-+]?\d+(?:\.\d+)?)\s*(h(?:ours?)?|min(?:ute)?s?|s(?:ec(?:ond)?s?)?)\b",
                text,
            )
        }
        orientations = set(
            match.group(1).upper()
            for match in re.finditer(
                r"(?i)(?<![a-z])([XYZ])\s*(?:build\s+)?(?:orientation|direction)\b",
                text,
            )
        )
        protocol = bool(
            re.search(
                r"(?i)\b(?:tensile|tension|strain\s+rate|test(?:ing)?|specimen|"
                r"rupture|fracture|universal\s+testing|standard|crosshead|gauge)\b",
                text,
            )
        )
        preparation = bool(
            re.search(
                r"(?i)\b(?:sinter(?:ed|ing)?|heat[-\s]*treat(?:ed|ment)?|"
                r"hip(?:ed|ping)?|aged?|anneal(?:ed|ing)?|as[-\s]*(?:built|printed|fabricated))\b",
                text,
            )
        )
        return {
            "temperatures": temperatures,
            "times": times,
            "orientations": orientations,
            "protocol": protocol,
            "preparation": preparation,
            "folded": folded,
        }

    left_profile, right_profile = profile(a), profile(b)
    left_temps, right_temps = left_profile["temperatures"], right_profile["temperatures"]
    if left_temps and right_temps:
        if "room" in left_temps or "room" in right_temps:
            if left_temps != right_temps:
                return 0.0
        elif not any(
            isinstance(x, float)
            and isinstance(y, float)
            and abs(x - y) <= 2.0
            for x in left_temps
            for y in right_temps
        ):
            return 0.0
    left_numbers = set(re.findall(r"[-+]?\d+(?:\.\d+)?", a))
    right_numbers = set(re.findall(r"[-+]?\d+(?:\.\d+)?", b))
    if left_numbers and right_numbers and not (left_numbers & right_numbers):
        return 0.0
    base = _jaccard(a_tokens, b_tokens)
    if left_numbers & right_numbers:
        base = max(base, 0.65)

    # A detailed source-local tensile procedure and a concise expert label are
    # compatible when they share a real coordinate (temperature, orientation,
    # or time).  Conversely, preparation-only text must not masquerade as the
    # test protocol that produced a result.
    shared_coordinate = bool(
        (left_temps and right_temps)
        or (left_profile["times"] & right_profile["times"])
        or (left_profile["orientations"] & right_profile["orientations"])
    )
    if shared_coordinate and left_profile["protocol"] and right_profile["protocol"]:
        return max(base, 0.65)
    if left_profile["protocol"] and right_profile["protocol"]:
        return max(base, 0.35)
    if left_profile["preparation"] and right_profile["preparation"]:
        return max(base, 0.35)
    if left_profile["preparation"] != right_profile["preparation"]:
        return min(base, 0.3)
    return base


def deduplicate_claims(claims: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    unique: list[dict[str, Any]] = []
    seen: set[str] = set()
    for claim in claims:
        numbers, unit = _converted_numbers(claim)
        owner = _project_owner_dimensions(claim)
        signature = json.dumps(
            [claim.get("axis"), _canonical_semantic(claim), numbers,
             fold((claim.get("value") or {}).get("text") or (claim.get("value") or {}).get("raw")),
             unit, owner["sample_id"], owner["state"], owner["location"],
             fold(_matching_condition(claim))],
            ensure_ascii=False, sort_keys=True,
        )
        if signature in seen:
            continue
        seen.add(signature)
        unique.append(claim)
    return unique


def deduplicate_unique_claims(claims: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    """Collapse cross-item assignment copies while retaining scientific state."""

    unique: list[dict[str, Any]] = []
    seen: set[str] = set()
    for claim in claims:
        numbers, unit = _converted_numbers(claim)
        owner = claim.get("owner") or {}
        dimensions = _project_owner_dimensions(claim)
        signature = json.dumps(
            [claim.get("axis"), _canonical_semantic(claim), numbers,
             fold((claim.get("value") or {}).get("text") or (claim.get("value") or {}).get("raw")),
             unit, fold(owner.get("material_name")), dimensions["state"],
             dimensions["location"], dimensions["region"], dimensions["orientation"],
             fold(owner.get("role")),
             fold(_matching_condition(claim)), claim.get("origin")],
            ensure_ascii=False, sort_keys=True,
        )
        if signature in seen:
            continue
        seen.add(signature)
        unique.append(claim)
    return unique


def match_claims(system: list[dict[str, Any]], expert: list[dict[str, Any]], *, strict: bool) -> dict[str, Any]:
    candidates: list[tuple[float, int, int, dict[str, float]]] = []
    exact_index: dict[tuple[str, str], set[int]] = {}
    token_index: dict[tuple[str, str], set[int]] = {}
    for expert_index, right in enumerate(expert):
        axis = str(right.get("axis"))
        exact_index.setdefault((axis, _canonical_semantic(right)), set()).add(expert_index)
        for token in _semantic_tokens(right):
            token_index.setdefault((axis, token), set()).add(expert_index)
    for system_index, left in enumerate(system):
        axis = str(left.get("axis"))
        expert_candidates = set(exact_index.get((axis, _canonical_semantic(left)), set()))
        for token in _semantic_tokens(left):
            expert_candidates.update(token_index.get((axis, token), set()))
        for expert_index in expert_candidates:
            right = expert[expert_index]
            semantic = semantic_score(left, right)
            if semantic < 0.5:
                continue
            value = value_score(left, right)
            if value < 0.45:
                continue
            owner = owner_score(left, right)
            condition = condition_score(left, right)
            if strict and (owner_conflict(left, right) or owner < 0.48 or condition < 0.40):
                continue
            total = 5.0 * semantic + 3.0 * value + (1.5 * owner + condition if strict else 0.25 * owner + 0.25 * condition)
            candidates.append((total, system_index, expert_index, {"semantic": semantic, "value": value, "owner": owner, "condition": condition}))
    used_system: set[int] = set()
    used_expert: set[int] = set()
    matches: list[dict[str, Any]] = []
    for total, system_index, expert_index, scores in sorted(candidates, reverse=True):
        if system_index in used_system or expert_index in used_expert:
            continue
        used_system.add(system_index)
        used_expert.add(expert_index)
        matches.append({"system_index": system_index, "expert_index": expert_index, "score": round(total, 6), "scores": {key: round(value, 6) for key, value in scores.items()}})
    return {
        "matches": matches,
        "unmatched_system": [index for index in range(len(system)) if index not in used_system],
        "unmatched_expert": [index for index in range(len(expert)) if index not in used_expert],
    }


def metrics(matched: int, system_count: int, expert_count: int) -> dict[str, Any]:
    precision = matched / system_count if system_count else (1.0 if not expert_count else 0.0)
    recall = matched / expert_count if expert_count else (1.0 if not system_count else 0.0)
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return {"matched": matched, "system": system_count, "expert": expert_count, "precision": round(precision, 6), "recall": round(recall, 6), "f1": round(f1, 6)}


def _compare_modes(system: list[dict[str, Any]], expert: list[dict[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for mode, strict in (("loose", False), ("strict", True)):
        match = match_claims(system, expert, strict=strict)
        by_axis: dict[str, Any] = {}
        for axis in AXES:
            system_indices = {index for index, claim in enumerate(system) if claim["axis"] == axis}
            expert_indices = {index for index, claim in enumerate(expert) if claim["axis"] == axis}
            matched = sum(row["system_index"] in system_indices and row["expert_index"] in expert_indices for row in match["matches"])
            by_axis[axis] = metrics(matched, len(system_indices), len(expert_indices))
        total = metrics(len(match["matches"]), len(system), len(expert))
        macro = {
            key: round(sum(by_axis[axis][key] for axis in AXES) / len(AXES), 6)
            for key in ("precision", "recall", "f1")
        }
        system_core = deduplicate_unique_claims(row for row in system if row["axis"] == "Properties" and _canonical_semantic(row) in CORE_TENSILE and row.get("origin") not in {"literature_experiment", "literature_computation"})
        expert_core = deduplicate_unique_claims(row for row in expert if row["axis"] == "Properties" and _canonical_semantic(row) in CORE_TENSILE and row.get("origin") not in {"literature_experiment", "literature_computation"})
        core_match = match_claims(system_core, expert_core, strict=strict)
        result[mode] = {
            "micro": total, "macro": macro, "axes": by_axis,
            "core_tensile": metrics(len(core_match["matches"]), len(system_core), len(expert_core)),
            "match": match,
        }
    return result


def compare_claim_sets(system: list[dict[str, Any]], expert: list[dict[str, Any]]) -> dict[str, Any]:
    unique_system = deduplicate_unique_claims(system)
    unique_expert = deduplicate_unique_claims(expert)
    return {
        "counts": {
            "system": len(system),
            "expert": len(expert),
            "unique_system": len(unique_system),
            "unique_expert": len(unique_expert),
        },
        "modes": _compare_modes(system, expert),
        "unique_modes": _compare_modes(unique_system, unique_expert),
    }


def issue_candidates(system: list[dict[str, Any]], expert: list[dict[str, Any]], comparison: dict[str, Any]) -> list[dict[str, Any]]:
    """Classify strict-pass differences for later evidence adjudication."""

    strict = comparison["modes"]["strict"]["match"]
    loose = comparison["modes"]["loose"]["match"]
    loose_system = {row["system_index"]: row for row in loose["matches"]}
    loose_expert = {row["expert_index"]: row for row in loose["matches"]}
    issues: list[dict[str, Any]] = []
    for index in strict["unmatched_expert"]:
        claim = expert[index]
        code = "system_missing"
        if index in loose_expert:
            row = loose_expert[index]
            system_claim = system[row["system_index"]]
            code = "wrong_owner" if owner_conflict(system_claim, claim) else "condition_conflict"
        issues.append({"code": code, "expert_claim": claim, "system_claim": system[loose_expert[index]["system_index"]] if index in loose_expert else None})
    for index in strict["unmatched_system"]:
        claim = system[index]
        if index in loose_system:
            # The paired owner/condition conflict was emitted from the expert
            # side above. Do not double-count it as a second system extra.
            continue
        code = "expert_gt_missing_or_unsupported"
        same_semantic = [row for row in expert if semantic_score(claim, row) >= 0.6]
        if same_semantic:
            if any(_unit(claim.get("unit_raw")) and _unit(row.get("unit_raw")) and _unit(claim.get("unit_raw")) != _unit(row.get("unit_raw")) for row in same_semantic):
                code = "unit_conflict"
            elif all(value_score(claim, row) == 0 for row in same_semantic):
                code = "value_conflict"
        issues.append({"code": code, "system_claim": claim, "expert_claim": None})
    return issues


def summarize_counts(claims: Iterable[dict[str, Any]]) -> dict[str, int]:
    counter = Counter(row["axis"] for row in claims)
    return {axis: counter[axis] for axis in AXES}
