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
                if raw.get("condition_label_raw"):
                    continue
                raw["condition_label_raw"] = qualifier
                changes.append(
                    {
                        "path": (
                            f"candidate_stages.{stage_index}.parameters_raw."
                            f"{parameter_index}.condition_label_raw"
                        ),
                        "before": None,
                        "after": qualifier,
                    }
                )

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
