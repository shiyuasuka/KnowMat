"""Evidence-neutral compatibility adapter for the frozen Alpha25 runner."""

from __future__ import annotations

import argparse
import re
import sys
import unicodedata
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
_POWER_TOKEN = re.compile(r"(?i)(?:^|\s)power(?:$|\s)")
_POST_HEAT_TREATMENT_STAGE = re.compile(
    r"(?ix)^post[\s_-]*(?:ht|heat[\s_-]*treat(?:ment)?s?)$"
)
_GENERIC_PROCESS_PARAMETER_STAGE = re.compile(
    r"(?ix)^(?:printing|processing|process|build|fabrication|manufacturing)"
    r"(?:\s+process)?\s+parameters?$"
)
_HEAT_TREATMENT_TEMPERATURE = re.compile(
    r"(?ix)^(?:(?:post[\s_-]*)?(?:ht|heat[\s_-]*treatment)|heating)"
    r"[\s_-]*temperature$"
)
_TENSILE_VALUE_NUMBER = r"[-+]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?"
_TENSILE_VALUE_WITH_EMBEDDED_UNIT = re.compile(
    rf"(?ix)^\s*"
    rf"(?P<central>{_TENSILE_VALUE_NUMBER})\s*"
    rf"(?P<unit1>MPa|GPa|%|percent)?\s*"
    rf"(?:\s*(?:±|\+/-|plus\s*/?\s*minus)\s*"
    rf"(?P<uncertainty>{_TENSILE_VALUE_NUMBER})\s*"
    rf"(?P<unit2>MPa|GPa|%|percent)?\s*)?$"
)
_QUANTITY_NUMBER = re.compile(
    r"(?<![\w.])[-+]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][-+]?\d+)?(?![\w.])"
)
_SOURCE_LITERAL_DERIVED_ENERGY_UNITS = {
    "line_energy": re.compile(
        r"(?ix)(?:"
        r"\bj\s*(?:/|per)\s*mm(?!\s*(?:\^?\s*[-+]?\s*[23]))|"
        r"\bj\s*(?:[\u00b7*]\s*)?mm\s*(?:\^?\s*-\s*1)"
        r")"
    ),
    "energy_density": re.compile(
        r"(?ix)(?:"
        r"\bj\s*(?:/|per)\s*mm\s*(?:\^?\s*3)|"
        r"\bj\s*(?:[\u00b7*]\s*)?mm\s*(?:\^?\s*-\s*3)"
        r")"
    ),
}


def _normalized_quantity_evidence(value: Any) -> str:
    text = unicodedata.normalize("NFKC", str(value or ""))
    text = text.replace("−", "-").replace("–", "-").replace("—", "-")
    text = re.sub(r"\\(?:mathrm|text)\s*\{([^{}]*)\}", r"\1", text)
    text = text.replace("{", "").replace("}", "").replace("$", "")
    return re.sub(r"\s+", " ", text).strip()


def _source_contains_numeric_value(value: Any, evidence: str) -> bool:
    try:
        target = float(value)
    except (TypeError, ValueError):
        return False
    if not (target == target and abs(target) != float("inf")):
        return False
    for match in _QUANTITY_NUMBER.finditer(evidence):
        try:
            candidate = float(match.group(0))
        except ValueError:
            continue
        if candidate == target:
            return True
    return False


def _derived_energy_is_source_literal(parameter: dict[str, Any]) -> bool:
    """Require a derived result, not merely its inputs, in cited evidence."""

    code = str(parameter.get("parameter_code") or "").strip().casefold()
    unit_pattern = _SOURCE_LITERAL_DERIVED_ENERGY_UNITS.get(code)
    if unit_pattern is None:
        return True
    evidence = _normalized_quantity_evidence(parameter.get("source_evidence"))
    value = parameter.get("canonical_value")
    if value is None:
        value = parameter.get("value_raw")
    return bool(
        evidence
        and unit_pattern.search(evidence)
        and _source_contains_numeric_value(value, evidence)
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


def tensile_value_without_embedded_unit(
    raw_value: Any, raw_unit: Any
) -> str | None:
    """Return a parser-only numeric spelling when the same unit is embedded."""

    unit_aliases = {
        "%": "%",
        "percent": "%",
        "mpa": "MPa",
        "gpa": "GPa",
    }
    declared = unit_aliases.get(str(raw_unit or "").strip().casefold())
    if declared is None:
        return None
    original_text = unicodedata.normalize("NFKC", str(raw_value or "")).strip()
    text = original_text
    text = text.replace(r"\%", "%").replace(r"\pm", "±").replace("$", "")
    text = re.sub(r"\\[,;:! ]", " ", text)
    match = _TENSILE_VALUE_WITH_EMBEDDED_UNIT.fullmatch(text)
    if match is None:
        return None
    units = {
        unit_aliases.get(str(raw or "").strip().casefold())
        for raw in (match.group("unit1"), match.group("unit2"))
        if raw
    }
    if units and units != {declared}:
        return None
    if not units and not (r"\pm" in original_text or "$" in original_text):
        return None
    central = match.group("central")
    uncertainty = match.group("uncertainty")
    return central if uncertainty is None else f"{central} ± {uncertainty}"


def install_tensile_value_unit_compat(normalize_tensile: Any) -> None:
    """Let the frozen parser read repeated literal units without losing raw text."""

    original: Callable[..., tuple[Any, ...]] = normalize_tensile.normalize_tensile_value
    if getattr(original, "_knowmat_embedded_unit_compat", False):
        return

    def compatible_value(
        candidate: dict[str, Any], canonical_property: str, rules: Any
    ) -> tuple[Any, ...]:
        parser_value = tensile_value_without_embedded_unit(
            candidate.get("value_raw"), candidate.get("unit_raw")
        )
        if parser_value is None:
            return original(candidate, canonical_property, rules)
        semantic_candidate = deepcopy(candidate)
        semantic_candidate["value_raw"] = parser_value
        value, issues, audit = original(
            semantic_candidate, canonical_property, rules
        )
        if isinstance(value, dict):
            value = deepcopy(value)
            value["value_raw"] = str(candidate.get("value_raw") or "").strip()
        return value, issues, audit

    compatible_value._knowmat_embedded_unit_compat = True  # type: ignore[attr-defined]
    normalize_tensile.normalize_tensile_value = compatible_value


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
    if key in {"line energy", "linear energy"}:
        return "line_energy"
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
            "post ht temperature",
            "post heat treatment temperature",
            "ht temperature",
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
            "heating time",
            "heat treatment time",
            "post ht time",
            "post heat treatment time",
            "ht time",
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


def process_energy_value_without_embedded_unit(
    raw_value: Any,
    raw_unit: Any,
    parameter_code: Any,
) -> str | None:
    """Return a parser-only number for an explicit energy value with its unit."""

    code = str(parameter_code or "").strip().casefold()
    unit_pattern = _SOURCE_LITERAL_DERIVED_ENERGY_UNITS.get(code)
    if unit_pattern is None:
        return None
    declared_unit = _normalized_quantity_evidence(raw_unit)
    if unit_pattern.fullmatch(declared_unit) is None:
        return None
    value = _normalized_quantity_evidence(raw_value)
    match = re.fullmatch(
        rf"(?ix)\s*(?:approximately|approx\.?|about|around|~|≈)?\s*"
        rf"(?P<number>{_TENSILE_VALUE_NUMBER})\s*"
        rf"(?P<unit>.+?)\s*",
        value,
    )
    if match is None or unit_pattern.fullmatch(match.group("unit")) is None:
        return None
    return match.group("number")


def _reported_auxiliary_energy_parameter(
    raw: dict[str, Any],
    *,
    parameter_code: str,
    parser_value: str | None,
    stage_uid: str,
    rules: Any,
    normalize_process: Any,
) -> dict[str, Any] | None:
    """Build a grounded reported auxiliary record rejected only by profile policy."""

    if parser_value is None:
        return None
    catalog = getattr(rules, "parameter_catalog", None)
    definition = catalog.get(parameter_code) if isinstance(catalog, dict) else None
    if not isinstance(definition, dict) or not str(
        definition.get("model_policy") or ""
    ).startswith("auxiliary_"):
        return None
    evidence = _normalized_quantity_evidence(raw.get("source_evidence"))
    unit_pattern = _SOURCE_LITERAL_DERIVED_ENERGY_UNITS.get(parameter_code)
    if (
        unit_pattern is None
        or unit_pattern.search(evidence) is None
        or not _source_contains_numeric_value(parser_value, evidence)
    ):
        return None
    routing_class_for_code = getattr(
        normalize_process, "_routing_class_for_code", None
    )
    routing_class = (
        routing_class_for_code(parameter_code, rules)
        if callable(routing_class_for_code)
        else "process_parameter"
    )
    try:
        confidence = min(1.0, max(0.0, float(raw.get("confidence", 0.5))))
    except (TypeError, ValueError):
        confidence = 0.5
    record: dict[str, Any] = {
        "parameter_code": parameter_code,
        "routing_class": routing_class,
        "value_kind": "scalar",
        "value_raw": str(raw.get("value_raw") or "").strip(),
        "unit_raw": raw.get("unit_raw"),
        "canonical_value": float(parser_value),
        "canonical_unit": definition.get("canonical_unit"),
        "status": "reported",
        "normalization_rule_id": "compat.reported_auxiliary_energy.v1",
        "stage_scope": stage_uid,
        "source_evidence": str(raw.get("source_evidence") or "").strip(),
        "confidence": confidence,
    }
    condition = str(raw.get("condition_label_raw") or "").strip()
    if condition:
        record["condition_label"] = condition
    return record


def _resolved_process(
    stage: dict[str, Any], rules: Any, resolve_process_type: Callable[..., Any]
) -> dict[str, Any] | None:
    result = resolve_process_type(
        stage.get("process_name_raw"),
        stage.get("process_code_candidate"),
        stage.get("process_role_candidate"),
        rules,
    )
    if not isinstance(result, tuple) or not result:
        return None
    return result[0] if isinstance(result[0], dict) else None


def _parameter_supported_by_profile(
    raw: dict[str, Any],
    profile: str,
    rules: Any,
    normalize_parameter: Callable[..., Any],
) -> bool:
    result = normalize_parameter(deepcopy(raw), "pstg_001", profile, rules)
    record = result[0] if isinstance(result, tuple) and result else None
    if isinstance(record, dict) and record.get("parameter_code") not in {
        None,
        "raw_unmapped_parameter",
    }:
        return True

    # The frozen profile intentionally keeps reported energy-density values
    # auxiliary rather than opening a model slot.  They are still legitimate
    # AM evidence and may be attached to an explicit AM stage as raw evidence.
    alias_code = process_parameter_alias(
        raw.get("parameter_name_raw"), raw.get("unit_raw"), raw.get("value_raw")
    )
    catalog = getattr(rules, "parameter_catalog", {})
    catalog_row = catalog.get(alias_code) if isinstance(catalog, dict) else None
    return bool(
        profile.startswith("AM_")
        and isinstance(catalog_row, dict)
        and str(catalog_row.get("model_policy") or "").startswith("auxiliary_")
    )


def _stage_distance(
    source_index: int,
    source: dict[str, Any],
    target_index: int,
    target: dict[str, Any],
) -> int:
    source_order = source.get("stage_index_candidate")
    target_order = target.get("stage_index_candidate")
    if isinstance(source_order, int) and isinstance(target_order, int):
        return abs(source_order - target_order)
    return abs(source_index - target_index)


def _extend_stage_evidence(stage: dict[str, Any], parameter: dict[str, Any]) -> None:
    evidence = parameter.get("source_evidence")
    new_evidence = (
        [evidence]
        if isinstance(evidence, str) and evidence.strip()
        else [
            value
            for value in evidence
            if isinstance(value, str) and value.strip()
        ]
        if isinstance(evidence, list)
        else []
    )
    existing = stage.get("source_evidence")
    if not isinstance(existing, list):
        existing = [existing] if isinstance(existing, str) and existing.strip() else []
        stage["source_evidence"] = existing
    for value in new_evidence:
        if value not in existing:
            existing.append(value)


def _rehome_parameters(
    stages: list[Any],
    source_index: int,
    target_index: int,
    parameter_indexes: set[int],
    rule_id: str,
) -> list[dict[str, Any]]:
    source = stages[source_index]
    target = stages[target_index]
    if not isinstance(source, dict) or not isinstance(target, dict):
        return []
    source_parameters = source.get("parameters_raw")
    if not isinstance(source_parameters, list):
        return []
    target_parameters = target.get("parameters_raw")
    if not isinstance(target_parameters, list):
        target_parameters = []
        target["parameters_raw"] = target_parameters

    retained: list[Any] = []
    changes: list[dict[str, Any]] = []
    for parameter_index, parameter in enumerate(source_parameters):
        if parameter_index not in parameter_indexes or not isinstance(parameter, dict):
            retained.append(parameter)
            continue
        moved = deepcopy(parameter)
        target_parameters.append(moved)
        _extend_stage_evidence(target, moved)
        changes.append(
            {
                "rule_id": rule_id,
                "path": (
                    f"candidate_stages.{source_index}.parameters_raw."
                    f"{parameter_index}"
                ),
                "before": {
                    "stage_id": source.get("candidate_stage_id"),
                    "stage_name": source.get("process_name_raw"),
                    "parameter": deepcopy(parameter),
                },
                "after": {
                    "stage_id": target.get("candidate_stage_id"),
                    "stage_name": target.get("process_name_raw"),
                    "parameter": moved,
                },
            }
        )
    source["parameters_raw"] = retained
    return changes


def prepare_process_stage_compat(
    candidate: dict[str, Any],
    *,
    rules: Any,
    resolve_process_type: Callable[..., Any],
    normalize_parameter: Callable[..., Any],
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Reconcile evidence-backed stage fragments before frozen normalization.

    Alpha25 can split one table row into a generic parameter container, a
    post-heat-treatment fragment, and an explicit AM stage.  This adapter only
    rehomes reported rows when those explicit sibling stages prove ownership;
    it never infers a process from a container heading alone.
    """

    stages = candidate.get("candidate_stages")
    if not isinstance(stages, list):
        return candidate, []
    prepared = deepcopy(candidate)
    prepared_stages = prepared.get("candidate_stages") or []
    changes: list[dict[str, Any]] = []

    # Resolve only an otherwise-unmapped, explicit post-HT abbreviation.  The
    # caller's candidate remains untouched and the exact raw spelling is kept
    # in the normalization audit below.
    for stage_index, stage in enumerate(prepared_stages):
        if not isinstance(stage, dict):
            continue
        raw_name = str(stage.get("process_name_raw") or "").strip()
        if not _POST_HEAT_TREATMENT_STAGE.fullmatch(raw_name):
            continue
        if _resolved_process(stage, rules, resolve_process_type) is not None:
            continue
        stage["process_name_raw"] = "heat treatment"
        changes.append(
            {
                "rule_id": "compat.process_stage_alias.v1",
                "path": f"candidate_stages.{stage_index}.process_name_raw",
                "before": raw_name,
                "after": "heat treatment",
            }
        )

    resolved = [
        _resolved_process(stage, rules, resolve_process_type)
        if isinstance(stage, dict)
        else None
        for stage in prepared_stages
    ]
    am_targets = [
        index
        for index, match in enumerate(resolved)
        if isinstance(match, dict)
        and str(match.get("parameter_profile") or "").startswith("AM_")
    ]

    # A generic container is evidence, not a process.  Attach only parameters
    # accepted by a real sibling AM profile (plus ontology-declared auxiliary
    # reported parameters), preferring the nearest compatible sibling.
    for source_index, source in enumerate(prepared_stages):
        if not isinstance(source, dict) or not _GENERIC_PROCESS_PARAMETER_STAGE.fullmatch(
            str(source.get("process_name_raw") or "").strip()
        ):
            continue
        parameters = source.get("parameters_raw")
        if not isinstance(parameters, list) or not parameters or not am_targets:
            continue
        scored: list[tuple[int, int, int, set[int]]] = []
        for target_index in am_targets:
            target = prepared_stages[target_index]
            match = resolved[target_index]
            if not isinstance(target, dict) or not isinstance(match, dict):
                continue
            profile = str(match.get("parameter_profile") or "")
            supported = {
                index
                for index, raw in enumerate(parameters)
                if isinstance(raw, dict)
                and _parameter_supported_by_profile(
                    raw, profile, rules, normalize_parameter
                )
            }
            if supported:
                scored.append(
                    (
                        len(supported),
                        -_stage_distance(source_index, source, target_index, target),
                        target_index,
                        supported,
                    )
                )
        if not scored:
            continue
        best_score = max((score, distance) for score, distance, _, _ in scored)
        best = [row for row in scored if row[:2] == best_score]
        if len(best) > 1:
            process_codes = {
                resolved[row[2]].get("code")
                for row in best
                if isinstance(resolved[row[2]], dict)
            }
            if len(process_codes) != 1:
                continue
        _, _, target_index, supported = max(best, key=lambda row: row[2])
        changes.extend(
            _rehome_parameters(
                prepared_stages,
                source_index,
                target_index,
                supported,
                "compat.process_container_parameter_rehome.v1",
            )
        )

    # Move an explicitly thermal temperature out of an AM stage only when a
    # sibling heat-treatment stage already owns a reported duration.  This is
    # deliberately stricter than interpreting every "heating" mention as HT.
    heat_treatment_targets: list[int] = []
    for target_index, (target, match) in enumerate(zip(prepared_stages, resolved)):
        if not isinstance(target, dict) or not isinstance(match, dict):
            continue
        if match.get("parameter_profile") != "HEAT_TREATMENT":
            continue
        target_parameters = target.get("parameters_raw")
        if not isinstance(target_parameters, list):
            continue
        if any(
            isinstance(raw, dict)
            and process_parameter_alias(
                raw.get("parameter_name_raw"),
                raw.get("unit_raw"),
                raw.get("value_raw"),
            )
            == "duration"
            for raw in target_parameters
        ):
            heat_treatment_targets.append(target_index)

    for source_index in am_targets:
        source = prepared_stages[source_index]
        if not isinstance(source, dict) or not heat_treatment_targets:
            continue
        parameters = source.get("parameters_raw")
        if not isinstance(parameters, list):
            continue
        thermal_indexes = {
            index
            for index, raw in enumerate(parameters)
            if isinstance(raw, dict)
            and _HEAT_TREATMENT_TEMPERATURE.fullmatch(
                re.sub(
                    r"\s+",
                    " ",
                    re.sub(
                        r"[_-]+", " ", str(raw.get("parameter_name_raw") or "")
                    ),
                ).strip()
            )
            and process_parameter_alias(
                raw.get("parameter_name_raw"),
                raw.get("unit_raw"),
                raw.get("value_raw"),
            )
            == "process_temperature"
        }
        if not thermal_indexes:
            continue
        ranked = sorted(
            heat_treatment_targets,
            key=lambda target_index: (
                _stage_distance(
                    source_index,
                    source,
                    target_index,
                    prepared_stages[target_index],
                ),
                -target_index,
            ),
        )
        target_index = ranked[0]
        profile = str(resolved[target_index].get("parameter_profile") or "")
        supported = {
            index
            for index in thermal_indexes
            if _parameter_supported_by_profile(
                parameters[index], profile, rules, normalize_parameter
            )
        }
        if supported:
            changes.extend(
                _rehome_parameters(
                    prepared_stages,
                    source_index,
                    target_index,
                    supported,
                    "compat.process_thermal_parameter_rehome.v1",
                )
            )
    return prepared, changes


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


def _energy_source_qualifier(raw_key: Any) -> str | None:
    """Return an explicit energy-source label from a reported power name."""

    key = re.sub(r"[_-]+", " ", str(raw_key or "")).strip().casefold()
    key = re.sub(r"\s+", " ", key)
    if not _POWER_TOKEN.search(key):
        return None
    if re.search(r"\bhot\s+wire\b", key):
        return "hot_wire"
    if re.search(r"\blaser\b", key):
        return "laser"
    if re.search(r"\b(?:electron\s+beam|e\s+beam)\b", key):
        return "electron_beam"
    if re.search(r"\bwire\b", key):
        return "wire"
    if re.search(r"\barc\b", key):
        return "arc"
    return None


def _combine_condition_labels(discriminator: str, existing: Any) -> str:
    """Preserve an existing process context while adding a collision discriminator."""

    current = str(existing or "").strip()
    if not current:
        return discriminator
    parts = [row.strip() for row in current.split("|") if row.strip()]
    if discriminator.casefold() in {row.casefold() for row in parts}:
        return current
    return f"{discriminator} | {current}"


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

        energy_rows: list[tuple[int, dict[str, Any], str]] = []
        for parameter_index, raw in enumerate(parameters):
            if not isinstance(raw, dict):
                continue
            qualifier = _energy_source_qualifier(raw.get("parameter_name_raw"))
            if qualifier is not None:
                energy_rows.append((parameter_index, raw, qualifier))
        if len({qualifier for _, _, qualifier in energy_rows}) >= 2:
            for parameter_index, raw, qualifier in energy_rows:
                before = raw.get("condition_label_raw")
                combined = _combine_condition_labels(qualifier, before)
                if combined == before:
                    continue
                raw["condition_label_raw"] = combined
                changes.append(
                    {
                        "path": (
                            f"candidate_stages.{stage_index}.parameters_raw."
                            f"{parameter_index}.condition_label_raw"
                        ),
                        "before": before,
                        "after": combined,
                    }
                )

        alias_rows: list[tuple[int, dict[str, Any], str]] = []
        signatures_by_code: dict[str, set[tuple[str, str]]] = {}
        for parameter_index, raw in enumerate(parameters):
            if not isinstance(raw, dict):
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
            before = raw.get("condition_label_raw")
            combined = _combine_condition_labels(label, before)
            if combined == before:
                continue
            raw["condition_label_raw"] = combined
            changes.append(
                {
                    "path": (
                        f"candidate_stages.{stage_index}.parameters_raw."
                        f"{parameter_index}.condition_label_raw"
                    ),
                    "before": before,
                    "after": combined,
                }
            )
    return prepared, changes


def install_structure_unit_compat(normalize_structure: Any) -> None:
    """Install lossless compatibility for structure units and raw identities."""

    original: Callable[..., Any] = normalize_structure._canonical_unit
    if getattr(original, "_knowmat_tex_unit_compat", False):
        return

    def compatible_unit(raw_unit: Any, ontology: dict[str, Any]) -> Any:
        semantic_unit = structure_unit_without_tex(raw_unit)
        return original(semantic_unit, ontology)

    compatible_unit._knowmat_tex_unit_compat = True  # type: ignore[attr-defined]
    normalize_structure._canonical_unit = compatible_unit

    original_entity = getattr(normalize_structure, "_normalize_entity", None)
    if not callable(original_entity) or getattr(
        original_entity, "_knowmat_raw_identity_compat", False
    ):
        return

    def compatible_entity(
        candidate: Any,
        path: str,
        ontology: dict[str, Any],
        issues: list[Any],
        audit: list[Any],
    ) -> dict[str, Any]:
        entity = original_entity(candidate, path, ontology, issues, audit)
        canonical = re.sub(
            r"[^a-z0-9]+",
            "",
            unicodedata.normalize(
                "NFKC", str(entity.get("canonical_name") or "")
            ).casefold(),
        )
        raw_name = str(entity.get("name_raw") or "").strip()
        raw_alias = re.sub(
            r"[^a-z0-9]+",
            "",
            unicodedata.normalize("NFKC", raw_name).casefold(),
        )
        placeholders = {
            "unknown",
            "unknownentity",
            "notreported",
            "unspecified",
        }
        if canonical in placeholders and raw_name and raw_alias not in placeholders:
            before = entity.get("canonical_name")
            entity["canonical_name"] = None
            audit_factory = getattr(normalize_structure, "_audit", None)
            if callable(audit_factory):
                audit.append(
                    audit_factory(
                        "compat.structure_raw_identity.v1",
                        f"{path}.canonical_name",
                        before,
                        None,
                    )
                )
        return entity

    compatible_entity._knowmat_raw_identity_compat = True  # type: ignore[attr-defined]
    normalize_structure._normalize_entity = compatible_entity


def _quarantine_ungrounded_derived_energy(
    route: Any,
    normalize_process: Any,
) -> tuple[list[Any], list[Any]]:
    """Remove only computed energy results absent from their cited evidence."""

    issues: list[Any] = []
    audit: list[Any] = []
    if not isinstance(route, dict):
        return issues, audit
    stages = route.get("stages")
    if not isinstance(stages, list):
        return issues, audit

    issue_factory = getattr(normalize_process, "_issue", None)
    audit_factory = getattr(normalize_process, "_audit", None)
    for stage_index, stage in enumerate(stages):
        if not isinstance(stage, dict):
            continue
        parameters = stage.get("parameters")
        if not isinstance(parameters, list):
            continue
        removed_rows: list[tuple[int, dict[str, Any]]] = []
        for parameter_index, parameter in enumerate(parameters):
            if not isinstance(parameter, dict):
                continue
            code = str(parameter.get("parameter_code") or "").strip().casefold()
            if (
                str(parameter.get("status") or "").strip().casefold()
                != "derived"
                or code not in _SOURCE_LITERAL_DERIVED_ENERGY_UNITS
                or _derived_energy_is_source_literal(parameter)
            ):
                continue
            removed_rows.append((parameter_index, deepcopy(parameter)))
        if not removed_rows:
            continue
        removed_indexes = {index for index, _ in removed_rows}
        retained = [
            parameter
            for parameter_index, parameter in enumerate(parameters)
            if parameter_index not in removed_indexes
        ]
        before = deepcopy(parameters)
        after = deepcopy(retained)
        stage["parameters"] = retained
        for _, parameter in removed_rows:
            code = str(parameter.get("parameter_code") or "derived_energy")
            path = (
                f"Process_Route.stages.{stage_index}.parameters.{code}"
            )
            if callable(issue_factory):
                issues.append(
                    issue_factory(
                        "promotion_ungrounded_derived_parameter_quarantined",
                        "review",
                        path,
                        (
                            "A computed process-energy result was absent from its "
                            "own cited evidence and was isolated without removing "
                            "the reported input parameters or process stage."
                        ),
                        evidence=str(parameter.get("source_evidence") or ""),
                        expected={
                            "result_value_and_unit_in_source_evidence": True,
                            "reported_inputs_preserved": True,
                        },
                        actual={
                            "removed": deepcopy(parameter),
                            "stage_parameters_before": before,
                            "stage_parameters_after": after,
                            "reason": "derived_result_not_source_literal",
                        },
                        suggested_action=(
                            "Restore only when the cited source explicitly reports "
                            "this result value and unit."
                        ),
                    )
                )
            if callable(audit_factory):
                audit.append(
                    audit_factory(
                        "compat.ungrounded_derived_parameter_quarantine.v1",
                        path,
                        deepcopy(parameter),
                        None,
                    )
                )
    return issues, audit


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
                parser_value = process_energy_value_without_embedded_unit(
                    raw.get("value_raw"),
                    raw.get("unit_raw"),
                    alias_code,
                )
                if parser_value is not None:
                    alias_raw["value_raw"] = parser_value
                alias_record, alias_issues, alias_audit = original_parameter(
                    alias_raw, stage_uid, profile, rules
                )
                if not (
                    isinstance(alias_record, dict)
                    and alias_record.get("parameter_code") == alias_code
                ):
                    auxiliary_record = _reported_auxiliary_energy_parameter(
                        raw,
                        parameter_code=alias_code,
                        parser_value=parser_value,
                        stage_uid=stage_uid,
                        rules=rules,
                        normalize_process=normalize_process,
                    )
                    if auxiliary_record is not None:
                        alias_record = auxiliary_record
                        alias_issues = []
                        alias_audit = []
                if (
                    isinstance(alias_record, dict)
                    and alias_record.get("parameter_code") == alias_code
                ):
                    if parser_value is not None:
                        alias_record = deepcopy(alias_record)
                        alias_record["value_raw"] = str(
                            raw.get("value_raw") or ""
                        ).strip()
                        alias_record["unit_raw"] = raw.get("unit_raw")
                    audit_factory = getattr(normalize_process, "_audit", None)
                    if callable(audit_factory):
                        if parser_value is not None:
                            alias_audit.append(
                                audit_factory(
                                    "compat.process_embedded_unit_value.v1",
                                    (
                                        f"stages.{stage_uid}.parameters."
                                        f"{raw.get('parameter_name_raw')}.value_raw"
                                    ),
                                    raw.get("value_raw"),
                                    parser_value,
                                )
                            )
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
            stage_changes: list[dict[str, Any]] = []
            resolve_process_type = getattr(
                normalize_process, "resolve_process_type", None
            )
            if callable(resolve_process_type):
                candidate, stage_changes = prepare_process_stage_compat(
                    candidate,
                    rules=rules,
                    resolve_process_type=resolve_process_type,
                    normalize_parameter=normalize_process.normalize_parameter,
                )
            prepared, changes = prepare_process_variant_conditions(candidate)
            route, issues, audit = original_route(prepared, rules)
            derived_issues, derived_audit = _quarantine_ungrounded_derived_energy(
                route,
                normalize_process,
            )
            issues.extend(derived_issues)
            audit.extend(derived_audit)
            audit_factory = getattr(normalize_process, "_audit", None)
            if callable(audit_factory):
                audit.extend(
                    audit_factory(
                        change["rule_id"],
                        change["path"],
                        change["before"],
                        change["after"],
                    )
                    for change in stage_changes
                )
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


def install_process_validation_compat(validate_v11: Any) -> None:
    """Honor the ontology's declared reported-or-derived auxiliary policy."""

    original = getattr(validate_v11, "_validate_parameter", None)
    if not callable(original) or getattr(
        original, "_knowmat_auxiliary_reported_compat", False
    ):
        return

    def compatible_parameter_validation(
        parameter: Any,
        path: str,
        stage_uid: Any,
        allowed_parameters: set[str],
        forbidden: set[str],
        rules: Any,
        issues: list[Any],
    ) -> None:
        issue_start = len(issues)
        original(
            parameter,
            path,
            stage_uid,
            allowed_parameters,
            forbidden,
            rules,
            issues,
        )
        if not isinstance(parameter, dict) or str(
            parameter.get("status") or ""
        ).casefold() != "reported":
            return
        catalog = getattr(rules, "parameter_catalog", None)
        definition = (
            catalog.get(parameter.get("parameter_code"))
            if isinstance(catalog, dict)
            else None
        )
        if not isinstance(definition, dict) or definition.get(
            "model_policy"
        ) != "auxiliary_derived_or_reported":
            return
        retained = [
            issue
            for issue in issues[issue_start:]
            if not (
                getattr(issue, "code", None)
                == "parameter_not_allowed_by_profile"
                and getattr(issue, "path", None) == f"{path}.parameter_code"
            )
        ]
        issues[issue_start:] = retained

    compatible_parameter_validation._knowmat_auxiliary_reported_compat = True  # type: ignore[attr-defined]
    validate_v11._validate_parameter = compatible_parameter_validation


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
        validate_v11,
    )

    install_property_alias_compat(normalize_tensile)
    install_tensile_value_unit_compat(normalize_tensile)
    install_process_unit_compat(normalize_process)
    install_process_validation_compat(validate_v11)
    install_structure_unit_compat(normalize_structure)
    from scripts.run_v11 import main as runner_main  # type: ignore[import-not-found]

    return int(runner_main(runner_argv))


if __name__ == "__main__":
    raise SystemExit(main())
