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
    "vickers_microhardness": "vickers_hardness",
    "microhardness": "vickers_hardness",
    "vickers_hardness": "vickers_hardness",
}
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


def _condition_text(value: Any) -> str:
    if not value:
        return ""
    if isinstance(value, dict):
        preferred = [
            value.get("original"), value.get("original_excerpt"), value.get("simplified"),
            value.get("condition_raw"), value.get("test_condition_raw"),
        ]
        text = " | ".join(str(row) for row in preferred if row and str(row).strip())
        if text:
            return text
        meaningful = {
            key: child
            for key, child in value.items()
            if child not in (None, "", [], {})
            and key not in {"condition_status", "test_method_class"}
        }
        if not meaningful:
            return ""
        return json.dumps(meaningful, ensure_ascii=False, sort_keys=True)
    if isinstance(value, list):
        return " | ".join(_condition_text(row) for row in value if row)
    return str(value)


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


def _value(row: dict[str, Any]) -> tuple[dict[str, Any], str | None]:
    nested = row.get("Value") if isinstance(row.get("Value"), dict) else {}
    kind = nested.get("value_kind") or row.get("value_kind") or "unknown"
    raw = (
        nested.get("value_raw") or row.get("value_raw") or row.get("Value_Raw")
        or row.get("value") or nested.get("canonical_value") or row.get("canonical_value")
    )
    number = nested.get("value_num")
    if number is None:
        number = nested.get("canonical_value", row.get("canonical_value"))
    if not isinstance(number, (int, float)) or isinstance(number, bool):
        number = row.get("value") if isinstance(row.get("value"), (int, float)) else None
    value = {
        "kind": str(kind),
        "raw": None if raw is None else str(raw),
        "number": float(number) if isinstance(number, (int, float)) and not isinstance(number, bool) else None,
        "min": nested.get("value_min", row.get("value_min")),
        "max": nested.get("value_max", row.get("value_max")),
        "operator": nested.get("operator", row.get("operator")),
        "bound": nested.get("bound_value", row.get("bound_value")),
        "stddev": nested.get("value_stddev", row.get("value_stddev")),
        "text": str(raw) if kind in {"categorical", "boolean", "unknown"} and raw is not None else None,
    }
    unit = (
        nested.get("canonical_unit") or nested.get("unit_raw") or row.get("canonical_unit")
        or row.get("unit_raw") or row.get("Unit_Raw")
    )
    return value, None if unit is None else str(unit)


def _owner(item: dict[str, Any], *, sample_id: Any = None, state: Any = None, region: Any = None) -> dict[str, Any]:
    extracted = item.get("Extracted_Data") or {}
    identity = ((extracted.get("Composition") or {}).get("Material_Identity") or {})
    material_name = (
        identity.get("material_name_raw") or identity.get("designation_raw")
        or identity.get("material_family") or item.get("Sample_ID") or "unknown material"
    )
    sample = sample_id if sample_id not in (None, "") else item.get("Sample_ID")
    return {
        "material_id": str(item.get("Item_ID") or sample or slug(material_name)),
        "material_name": str(material_name),
        "sample_id": None if sample in (None, "") else str(sample),
        "state": None if state in (None, "") else str(state),
        "region": None if region in (None, "") else str(region),
        "orientation": None,
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
            owner = _owner(item, sample_id=observation.get("sample_id"), state=observation.get("material_state"))
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
                    raw=parameter,
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
                if entity_name:
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
            fields = (
                ("method", char.get("method_raw")),
                ("instrument", char.get("instrument") or char.get("equipment") or char.get("equipment_raw")),
                ("standard", char.get("standard_raw")),
                ("condition", char.get("condition_raw") or char.get("test_condition_raw")),
                ("sample_preparation", char.get("sample_preparation_raw")),
                ("sample_location", char.get("sample_location_raw")),
            )
            for field, content in fields:
                if content in (None, "", [], {}):
                    continue
                raw_text = _condition_text(content)
                value = {"kind": "categorical", "raw": raw_text, "number": None, "min": None, "max": None, "operator": None, "bound": None, "stddev": None, "text": raw_text}
                add(
                    axis="Characterization", owner=char_owner,
                    semantic_key=f"{method_class}_{field}", name_raw=f"{method_class} {field}",
                    value=value, unit_raw=None, condition=None,
                    origin=_origin(item.get("Data_Nature")), evidence=_evidence(char),
                    raw_path=f"items[{item_index}].Characterization[{char_index}].{field}", raw=char,
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
            value, unit = _value(prop)
            add(
                axis="Properties", owner=_owner(item), semantic_key=name,
                name_raw=prop.get("Property_Name_Raw") or name, value=value, unit_raw=unit,
                condition=prop.get("Test_Condition"),
                origin=_origin(prop.get("Observation_Origin"), prop.get("Data_Nature")),
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
    return _ENERGY_SOURCE_CONDITIONS.get(fold(claim.get("condition")))


def _matching_condition(claim: dict[str, Any]) -> str:
    if _energy_source_condition(claim) is not None:
        return ""
    return str(claim.get("condition") or "")


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
        value = (claim.get("value") or {}).get("text") or (claim.get("value") or {}).get("raw") or ""
    return _tokens(f"{_canonical_semantic(claim)} {claim.get('name_raw', '')} {value}")


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
        "w": "w", "kw": "kw",
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
    if unit == "k":
        return tuple(row - 273.15 for row in numbers), "degc"
    if unit == "um":
        return tuple(row / 1000.0 for row in numbers), "mm"
    if unit == "h":
        return tuple(row * 3600.0 for row in numbers), "s"
    if unit == "min":
        return tuple(row * 60.0 for row in numbers), "s"
    return numbers, unit


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
    return score


def owner_score(left: dict[str, Any], right: dict[str, Any]) -> float:
    left_owner = left.get("owner") or {}
    right_owner = right.get("owner") or {}
    scores: list[float] = []
    for key in ("sample_id", "state", "region", "orientation"):
        a, b = _owner_dimension(key, left_owner.get(key)), _owner_dimension(key, right_owner.get(key))
        if a and b:
            scores.append(1.0 if a == b or a in b or b in a else _jaccard(_tokens(a), _tokens(b)))
        elif a or b:
            scores.append(0.35)
    material_score = _jaccard(_tokens(left_owner.get("material_name")), _tokens(right_owner.get("material_name")))
    if material_score:
        scores.append(material_score)
    if fold(left_owner.get("role")) and fold(right_owner.get("role")):
        scores.append(1.0 if fold(left_owner.get("role")) == fold(right_owner.get("role")) else 0.0)
    return sum(scores) / len(scores) if scores else 0.5


def owner_conflict(left: dict[str, Any], right: dict[str, Any]) -> bool:
    """Return true for explicit owner dimensions that cannot describe one sample."""

    left_owner = left.get("owner") or {}
    right_owner = right.get("owner") or {}
    for key in ("sample_id", "state", "region", "orientation"):
        a, b = _owner_dimension(key, left_owner.get(key)), _owner_dimension(key, right_owner.get(key))
        if not a or not b:
            continue
        if a == b or a in b or b in a:
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
    a, b = _matching_condition(left), _matching_condition(right)
    a_tokens, b_tokens = _tokens(a), _tokens(b)
    if not a_tokens and not b_tokens:
        return 1.0
    if not a_tokens or not b_tokens:
        return 0.25
    a_numbers = set(re.findall(r"[-+]?\d+(?:\.\d+)?", a))
    b_numbers = set(re.findall(r"[-+]?\d+(?:\.\d+)?", b))
    if a_numbers and b_numbers and not (a_numbers & b_numbers):
        return 0.0
    return max(_jaccard(a_tokens, b_tokens), 0.65 if a_numbers & b_numbers else 0.0)


def deduplicate_claims(claims: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    unique: list[dict[str, Any]] = []
    seen: set[str] = set()
    for claim in claims:
        numbers, unit = _converted_numbers(claim)
        signature = json.dumps(
            [claim.get("axis"), _canonical_semantic(claim), numbers,
             fold((claim.get("value") or {}).get("text") or (claim.get("value") or {}).get("raw")),
             unit, fold((claim.get("owner") or {}).get("sample_id")),
             fold((claim.get("owner") or {}).get("state")), fold(_matching_condition(claim))],
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
        signature = json.dumps(
            [claim.get("axis"), _canonical_semantic(claim), numbers,
             fold((claim.get("value") or {}).get("text") or (claim.get("value") or {}).get("raw")),
             unit, fold(owner.get("material_name")), _owner_dimension("state", owner.get("state")),
             fold(owner.get("region")), fold(owner.get("orientation")), fold(owner.get("role")),
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
