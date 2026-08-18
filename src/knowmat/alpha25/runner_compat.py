"""Evidence-neutral compatibility adapter for the frozen Alpha25 runner."""

from __future__ import annotations

import argparse
import re
import sys
from copy import deepcopy
from pathlib import Path
from typing import Any, Callable, Sequence


_PROPERTY_NAME_UNIT_SUFFIX = re.compile(
    r"(?ix)\s*(?:"
    r"\(\s*(?:MPa|GPa|Pa|ksi|%|percent)\s*\)|"
    r"\[\s*(?:MPa|GPa|Pa|ksi|%|percent)\s*\]|"
    r"/\s*(?:MPa|GPa|Pa|ksi|%|percent)"
    r")\s*$"
)
_TEMPORAL_UNIT = re.compile(
    r"(?i)^(?:time\s*\()?\s*(?:µs|us|ms|s|sec(?:ond)?s?|min(?:ute)?s?|"
    r"h|hr|hrs|hour|hours)\s*\)?$"
)
_TEMPORAL_VALUE = re.compile(
    r"(?i)\b\d+(?:\.\d+)?\s*(?:µs|us|ms|sec(?:ond)?s?|min(?:ute)?s?|"
    r"h|hr|hrs|hour|hours)\b"
)
_TEMPERATURE_UNIT = re.compile(
    r"(?i)^(?:°|º)?\s*(?:c|k)|deg(?:ree)?\s*[ck]|celsius|kelvin$"
)
_LINEAR_RATE_UNIT = re.compile(
    r"(?i)^(?:µm|um|mm|cm|m|in(?:ch(?:es)?)?)/(?:s|min|h|hr|hour)$"
)
_MASS_RATE_UNIT = re.compile(
    r"(?i)^(?:mg|g|kg)/(?:s|min|h|hr|hour)$"
)


def property_name_without_unit_suffix(raw_name: Any) -> str:
    """Return a semantic lookup label while preserving the caller's raw data."""

    return _PROPERTY_NAME_UNIT_SUFFIX.sub("", str(raw_name or "")).strip()


def install_property_alias_compat(normalize_tensile: Any) -> None:
    """Retry only unmapped property aliases without a trailing unit label."""

    original: Callable[..., tuple[Any, ...]] = normalize_tensile.resolve_property
    if getattr(original, "_knowmat_unit_suffix_compat", False):
        return

    def compatible_resolver(candidate: dict[str, Any], rules: Any) -> tuple[Any, ...]:
        result = original(candidate, rules)
        if result[0] is not None:
            return result
        raw_name = str(candidate.get("property_name_raw") or "")
        semantic_name = property_name_without_unit_suffix(raw_name)
        if not semantic_name or semantic_name == raw_name:
            return result
        semantic_candidate = deepcopy(candidate)
        semantic_candidate["property_name_raw"] = semantic_name
        return original(semantic_candidate, rules)

    compatible_resolver._knowmat_unit_suffix_compat = True  # type: ignore[attr-defined]
    normalize_tensile.resolve_property = compatible_resolver


def structure_unit_without_tex(raw_unit: Any) -> Any:
    """Return a semantic unit spelling while retaining the caller's raw field."""

    if not isinstance(raw_unit, str) or not raw_unit.strip():
        return raw_unit
    text = raw_unit.strip().replace("$", "")
    text = re.sub(
        r"\\(?:text|mathrm|operatorname)\s*\{([^{}]*)\}",
        r"\1",
        text,
    )
    text = text.replace("{", "").replace("}", "")
    text = text.replace(r"\mu", "µ").replace("μ", "µ")
    compact = re.sub(r"\s+", "", text)
    if compact.casefold() in {"um", "μm"}:
        return "µm"
    inverse_area = (
        compact.replace("−", "-")
        .replace("⁻", "^-")
        .replace("²", "2")
    )
    if inverse_area.casefold() in {"um^-2", "μm^-2", "um-2", "μm-2"}:
        return "um^-2"
    return raw_unit


def process_parameter_alias(
    raw_key: Any, raw_unit: Any, raw_value: Any
) -> str | None:
    """Return a guarded canonical process key for common ontology synonyms."""

    key = re.sub(r"[_-]+", " ", str(raw_key or "")).strip().casefold()
    key = re.sub(r"\s+", " ", key)
    unit = str(structure_unit_without_tex(raw_unit) or "").strip()
    value = str(raw_value or "").strip()

    if key in {"hatch space", "hatch distance", "scanning spacing"}:
        return "hatch_spacing"
    if key in {
        "laser spot",
        "laser spot size",
        "spot size",
        "laser beam size",
    }:
        return "beam_diameter"
    if key in {"volumetric energy density", "volume energy density"}:
        return "energy_density"
    if key in {
        "build chamber environment",
        "build environment",
        "deposition environment",
        "environment",
    } and unit.casefold() in {"", "none"}:
        return "atmosphere"
    if key in {"oxygen level", "oxygen concentration"}:
        return "oxygen_content"
    if key in {"isostatic pressure", "process pressure"}:
        return "pressure"
    if key in {"substrate temperature", "build plate preheat"} and (
        _TEMPERATURE_UNIT.fullmatch(unit) or re.search(r"(?:°|º)\s*[CK]\b", value)
    ):
        return "preheat_temperature"
    if (
        key in {
            "heating temperature",
            "heat treatment temperature",
            "process temperature",
            "treatment temperature",
            "thermal environment temperature",
            "maximum temperature",
        }
        or re.fullmatch(r"(?:first|second) stage temperature", key)
        or re.fullmatch(r"step \d+ temperature", key)
    ) and (
        _TEMPERATURE_UNIT.fullmatch(unit) or re.search(r"(?:°|º)\s*[CK]\b", value)
    ):
        return "process_temperature"
    if (
        key in {
            "time",
            "total duration",
            "hold time",
            "holding time",
            "delay time",
            "exposure time",
        }
        or re.fullmatch(r"(?:first|second) stage time", key)
        or re.fullmatch(r"step \d+ time", key)
    ) and (_TEMPORAL_UNIT.fullmatch(unit) or _TEMPORAL_VALUE.search(value)):
        return "duration"
    if key in {"feed rate", "wire feed rate"}:
        if _LINEAR_RATE_UNIT.fullmatch(unit):
            return "wire_feed_rate"
        if _MASS_RATE_UNIT.fullmatch(unit):
            return "feed_rate_mass"
    return None


def _process_variant_label(
    raw: dict[str, Any], *, disambiguate_value: bool = False
) -> str | None:
    """Preserve an explicit sub-step or evidence-backed parameter variant."""

    raw_key = str(raw.get("parameter_name_raw") or "").strip()
    key = re.sub(r"[_-]+", " ", raw_key).casefold()
    key = re.sub(r"\s+", " ", key).strip()
    qualified = bool(
        key == "total duration"
        or re.fullmatch(r"(?:first|second) stage (?:temperature|time)", key)
        or re.fullmatch(r"step \d+ (?:temperature|time)", key)
    )
    if not qualified and not disambiguate_value:
        return None

    evidence = str(raw.get("source_evidence") or "").strip()
    label = evidence or raw_key
    if not label:
        return None
    if disambiguate_value:
        value = str(raw.get("value_raw") or "").strip()
        unit = str(raw.get("unit_raw") or "").strip()
        reported = " ".join(part for part in (value, unit) if part)
        if reported:
            label = f"{label} [reported {raw_key}: {reported}]"
    return label


def prepare_process_variant_conditions(
    candidate: dict[str, Any],
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Label only alias rows that would otherwise collide inside one stage.

    The frozen normalizer already keys parameters by canonical code plus an
    optional condition label.  Alpha25 candidates can carry several real
    experimental variants in one stage, so assigning every alias to a bare
    canonical code would silently retain only the first value.  This adapter
    uses the existing raw evidence as the condition and never invents a new
    process fact.
    """

    stages = candidate.get("candidate_stages")
    if not isinstance(stages, list):
        return candidate, []

    prepared = deepcopy(candidate)
    changes: list[dict[str, Any]] = []
    for stage_index, stage in enumerate(prepared.get("candidate_stages") or []):
        if not isinstance(stage, dict):
            continue
        parameters = stage.get("parameters_raw")
        if not isinstance(parameters, list):
            continue

        alias_rows: list[tuple[int, dict[str, Any], str]] = []
        signatures_by_code: dict[str, set[tuple[str, str]]] = {}
        for parameter_index, raw in enumerate(parameters):
            if not isinstance(raw, dict) or raw.get("condition_label_raw"):
                continue
            alias_code = process_parameter_alias(
                raw.get("parameter_name_raw"),
                raw.get("unit_raw"),
                raw.get("value_raw"),
            )
            if alias_code is None:
                continue
            alias_rows.append((parameter_index, raw, alias_code))
            signatures_by_code.setdefault(alias_code, set()).add(
                (
                    str(raw.get("value_raw") or "").strip().casefold(),
                    str(raw.get("unit_raw") or "").strip().casefold(),
                )
            )

        for parameter_index, raw, alias_code in alias_rows:
            raw_key = re.sub(
                r"\s+",
                " ",
                re.sub(
                    r"[_-]+", " ", str(raw.get("parameter_name_raw") or "")
                ),
            ).strip().casefold()
            disambiguate = (
                raw_key == "time"
                and len(signatures_by_code.get(alias_code, set())) > 1
            )
            label = _process_variant_label(raw, disambiguate_value=disambiguate)
            if label is None:
                continue
            raw["condition_label_raw"] = label
            changes.append(
                {
                    "path": (
                        f"candidate_stages.{stage_index}.parameters_raw."
                        f"{parameter_index}.condition_label_raw"
                    ),
                    "before": None,
                    "after": label,
                }
            )
    return prepared, changes


def install_structure_unit_compat(normalize_structure: Any) -> None:
    """Let the frozen structure normalizer recognize OCR/TeX micrometre units."""

    original: Callable[..., Any] = normalize_structure._canonical_unit
    if getattr(original, "_knowmat_tex_unit_compat", False):
        return

    def compatible_unit(raw_unit: Any, ontology: dict[str, Any]) -> Any:
        semantic_unit = structure_unit_without_tex(raw_unit)
        return original(semantic_unit, ontology)

    compatible_unit._knowmat_tex_unit_compat = True  # type: ignore[attr-defined]
    normalize_structure._canonical_unit = compatible_unit


def install_process_unit_compat(normalize_process: Any) -> None:
    """Normalize TeX micrometre units without resolving unknown parameter names."""

    original_factor: Callable[..., Any] = normalize_process._unit_factor
    if not getattr(original_factor, "_knowmat_tex_unit_compat", False):

        def compatible_factor(raw_unit: Any, canonical_unit: Any) -> Any:
            return original_factor(
                structure_unit_without_tex(raw_unit), canonical_unit
            )

        compatible_factor._knowmat_tex_unit_compat = True  # type: ignore[attr-defined]
        normalize_process._unit_factor = compatible_factor

    original_parameter: Callable[..., tuple[Any, ...]] = (
        normalize_process.normalize_parameter
    )
    if not getattr(original_parameter, "_knowmat_tex_unit_compat", False):

        def compatible_parameter(
            raw: dict[str, Any], stage_uid: str, profile: str, rules: Any
        ) -> tuple[Any, ...]:
            record, issues, audit = original_parameter(raw, stage_uid, profile, rules)
            if not isinstance(record, dict):
                return record, issues, audit
            alias_code = process_parameter_alias(
                raw.get("parameter_name_raw"),
                raw.get("unit_raw"),
                raw.get("value_raw"),
            )
            if (
                record.get("parameter_code") == "raw_unmapped_parameter"
                and alias_code is not None
            ):
                alias_raw = deepcopy(raw)
                alias_raw["parameter_name_raw"] = alias_code
                alias_record, alias_issues, alias_audit = original_parameter(
                    alias_raw, stage_uid, profile, rules
                )
                if (
                    isinstance(alias_record, dict)
                    and alias_record.get("parameter_code") == alias_code
                ):
                    audit_factory = getattr(normalize_process, "_audit", None)
                    if callable(audit_factory):
                        alias_audit.append(
                            audit_factory(
                                "compat.process_parameter_alias.v1",
                                (
                                    f"stages.{stage_uid}.parameters."
                                    f"{raw.get('parameter_name_raw')}"
                                ),
                                {
                                    "parameter_name_raw": raw.get(
                                        "parameter_name_raw"
                                    ),
                                    "value_raw": raw.get("value_raw"),
                                    "unit_raw": raw.get("unit_raw"),
                                },
                                {"parameter_code": alias_code},
                            )
                        )
                    return alias_record, alias_issues, alias_audit
            semantic_unit = structure_unit_without_tex(record.get("unit_raw"))
            if (
                record.get("parameter_code") != "raw_unmapped_parameter"
                or semantic_unit != "µm"
                or record.get("canonical_unit") not in (None, "")
            ):
                return record, issues, audit

            before = deepcopy(record)
            record = deepcopy(record)
            record["canonical_unit"] = "um"
            value_text = str(record.get("value_raw") or "").strip()
            if re.fullmatch(
                r"[-+]?\d+(?:\.\d+)?(?:[eE][-+]?\d+)?", value_text
            ):
                record["canonical_value"] = float(value_text)
            audit_factory = getattr(normalize_process, "_audit", None)
            if callable(audit_factory):
                audit.append(
                    audit_factory(
                        "compat.raw_parameter.tex_micrometre.v1",
                        (
                            f"stages.{stage_uid}.parameters."
                            f"{raw.get('parameter_name_raw')}"
                        ),
                        before,
                        deepcopy(record),
                    )
                )
            return record, issues, audit

        compatible_parameter._knowmat_tex_unit_compat = True  # type: ignore[attr-defined]
        normalize_process.normalize_parameter = compatible_parameter

    original_route = getattr(normalize_process, "normalize_route", None)
    if callable(original_route) and not getattr(
        original_route, "_knowmat_variant_condition_compat", False
    ):

        def compatible_route(
            candidate: dict[str, Any], rules: Any
        ) -> tuple[Any, ...]:
            prepared, changes = prepare_process_variant_conditions(candidate)
            route, issues, audit = original_route(prepared, rules)
            audit_factory = getattr(normalize_process, "_audit", None)
            if callable(audit_factory):
                audit.extend(
                    audit_factory(
                        "compat.process_variant_condition.v1",
                        change["path"],
                        change["before"],
                        change["after"],
                    )
                    for change in changes
                )
            return route, issues, audit

        compatible_route._knowmat_variant_condition_compat = True  # type: ignore[attr-defined]
        normalize_process.normalize_route = compatible_route


def main(argv: Sequence[str] | None = None) -> int:
    """Load the frozen runner, install the narrow adapter, and delegate."""

    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--package-root", required=True, type=Path)
    args, runner_argv = parser.parse_known_args(argv)
    package_root = args.package_root.resolve()
    sys.path.insert(0, str(package_root))

    from scripts import (  # type: ignore[import-not-found]
        normalize_process,
        normalize_structure,
        normalize_tensile,
    )

    install_property_alias_compat(normalize_tensile)
    install_process_unit_compat(normalize_process)
    install_structure_unit_compat(normalize_structure)
    from scripts.run_v11 import main as runner_main  # type: ignore[import-not-found]

    return int(runner_main(runner_argv))


if __name__ == "__main__":
    raise SystemExit(main())
