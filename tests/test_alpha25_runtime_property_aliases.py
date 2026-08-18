from types import SimpleNamespace

import pytest

from knowmat.alpha25.runner_compat import (
    install_process_unit_compat,
    install_structure_unit_compat,
    prepare_process_stage_compat,
    prepare_process_variant_conditions,
    process_parameter_alias,
    property_name_without_unit_suffix,
    structure_unit_without_tex,
)


def test_unit_suffix_is_semantic_only_and_raw_property_name_is_retained():
    raw_name = "UTS (MPa)"

    assert property_name_without_unit_suffix(raw_name) == "UTS"
    assert raw_name == "UTS (MPa)"


@pytest.mark.parametrize(
    ("raw_unit", "semantic_unit"),
    [
        (r"\mum", "µm"),
        (r"\mu\text{m}", "µm"),
        (r"$ \mu $m", "µm"),
        (r"\mum⁻²", "um^-2"),
        ("nm", "nm"),
    ],
)
def test_structure_unit_tex_is_normalized_semantically(
    raw_unit: str, semantic_unit: str
):
    assert structure_unit_without_tex(raw_unit) == semantic_unit


def test_structure_unit_compat_preserves_raw_caller_value() -> None:
    calls: list[str] = []

    def canonical_unit(raw_unit, _ontology):
        calls.append(raw_unit)
        return {"µm": "um"}.get(raw_unit, raw_unit)

    runtime = SimpleNamespace(_canonical_unit=canonical_unit)
    install_structure_unit_compat(runtime)
    raw_unit = r"\mum"

    assert runtime._canonical_unit(raw_unit, {}) == "um"
    assert calls == ["µm"]
    assert raw_unit == r"\mum"


def test_process_unit_compat_normalizes_unmapped_tex_unit_with_audit() -> None:
    factor_calls: list[tuple[str, str]] = []

    def unit_factor(raw_unit, canonical_unit):
        factor_calls.append((raw_unit, canonical_unit))
        return (1.0, 0.0, "unit_identity")

    def normalize_parameter(raw, stage_uid, _profile, _rules):
        return (
            {
                "parameter_code": "raw_unmapped_parameter",
                "parameter_name_raw": raw["parameter_name_raw"],
                "value_raw": raw["value_raw"],
                "unit_raw": raw["unit_raw"],
                "canonical_value": None,
                "canonical_unit": None,
            },
            [],
            [],
        )

    runtime = SimpleNamespace(
        _unit_factor=unit_factor,
        normalize_parameter=normalize_parameter,
        _audit=lambda rule_id, path, before, after: {
            "rule_id": rule_id,
            "path": path,
            "before": before,
            "after": after,
        },
    )
    install_process_unit_compat(runtime)
    raw = {
        "parameter_name_raw": "hatch space",
        "value_raw": "100",
        "unit_raw": r"\mum",
    }

    record, issues, audit = runtime.normalize_parameter(raw, "pstg_001", "", {})

    assert record["unit_raw"] == r"\mum"
    assert record["canonical_value"] == 100.0
    assert record["canonical_unit"] == "um"
    assert issues == []
    assert audit[0]["rule_id"] == "compat.raw_parameter.tex_micrometre.v1"
    assert runtime._unit_factor(r"\mum", "um") == (1.0, 0.0, "unit_identity")
    assert factor_calls == [("µm", "um")]
    assert raw["unit_raw"] == r"\mum"


@pytest.mark.parametrize(
    ("raw_key", "unit", "value", "expected"),
    [
        ("hatch space", r"\mum", "100", "hatch_spacing"),
        ("laser spot", r"\mum", "70", "beam_diameter"),
        ("Heating Temperature", "°C", "900", "process_temperature"),
        ("first stage temperature", "°C", "1120", "process_temperature"),
        ("substrate temperature", "°C", "200", "preheat_temperature"),
        ("time", "h", "4", "duration"),
        ("Heating Time", "h", "2", "duration"),
        ("time", "", "1 hour", "duration"),
        ("time", "", "2", None),
        ("Feed Rate", "mm/s", "40", "wire_feed_rate"),
        ("Feed Rate", "g/s", "2.5", "feed_rate_mass"),
        ("environment", "", "vacuum", "atmosphere"),
        ("volumetric energy density", "J/mm³", "61.22", "energy_density"),
        ("oxygen level", "PPM", "below 1000", "oxygen_content"),
    ],
)
def test_process_parameter_alias_is_guarded_by_semantics_and_unit(
    raw_key: str, unit: str, value: str, expected: str | None
) -> None:
    assert process_parameter_alias(raw_key, unit, value) == expected


def test_process_alias_compat_retries_existing_ontology_code() -> None:
    def unit_factor(_raw_unit, _canonical_unit):
        return (1.0, 0.0, "unit_identity")

    def normalize_parameter(raw, stage_uid, _profile, _rules):
        if raw["parameter_name_raw"] == "hatch_spacing":
            return (
                {
                    "parameter_code": "hatch_spacing",
                    "value_raw": raw["value_raw"],
                    "unit_raw": raw["unit_raw"],
                    "canonical_value": 0.1,
                    "canonical_unit": "mm",
                    "stage_scope": stage_uid,
                },
                [],
                [],
            )
        return (
            {
                "parameter_code": "raw_unmapped_parameter",
                "parameter_name_raw": raw["parameter_name_raw"],
                "value_raw": raw["value_raw"],
                "unit_raw": raw["unit_raw"],
                "canonical_value": None,
                "canonical_unit": None,
            },
            [],
            [],
        )

    runtime = SimpleNamespace(
        _unit_factor=unit_factor,
        normalize_parameter=normalize_parameter,
        _audit=lambda rule_id, path, before, after: {
            "rule_id": rule_id,
            "path": path,
            "before": before,
            "after": after,
        },
    )
    install_process_unit_compat(runtime)
    raw = {
        "parameter_name_raw": "hatch space",
        "value_raw": "100",
        "unit_raw": r"\mum",
    }

    record, issues, audit = runtime.normalize_parameter(raw, "pstg_001", "", {})

    assert record["parameter_code"] == "hatch_spacing"
    assert record["unit_raw"] == r"\mum"
    assert record["canonical_value"] == 0.1
    assert record["canonical_unit"] == "mm"
    assert issues == []
    assert audit[-1]["rule_id"] == "compat.process_parameter_alias.v1"
    assert audit[-1]["before"]["parameter_name_raw"] == "hatch space"
    assert raw["parameter_name_raw"] == "hatch space"


def test_process_variant_conditions_preserve_substeps_and_multi_value_time() -> None:
    first_evidence = "first treatment at 1120 °C for 4 h"
    second_evidence = "second treatment at 900 °C for 16 h"
    variant_evidence = "annealing at 600 °C for 5 and 30 min"
    candidate = {
        "candidate_stages": [
            {
                "parameters_raw": [
                    {
                        "parameter_name_raw": "first stage temperature",
                        "value_raw": "1120",
                        "unit_raw": "°C",
                        "source_evidence": first_evidence,
                    },
                    {
                        "parameter_name_raw": "first stage time",
                        "value_raw": "4",
                        "unit_raw": "h",
                        "source_evidence": first_evidence,
                    },
                    {
                        "parameter_name_raw": "second stage temperature",
                        "value_raw": "900",
                        "unit_raw": "°C",
                        "source_evidence": second_evidence,
                    },
                    {
                        "parameter_name_raw": "second stage time",
                        "value_raw": "16",
                        "unit_raw": "h",
                        "source_evidence": second_evidence,
                    },
                    {
                        "parameter_name_raw": "time",
                        "value_raw": "5",
                        "unit_raw": "min",
                        "source_evidence": variant_evidence,
                    },
                    {
                        "parameter_name_raw": "time",
                        "value_raw": "30",
                        "unit_raw": "min",
                        "source_evidence": variant_evidence,
                    },
                    {
                        "parameter_name_raw": "hatch space",
                        "value_raw": "100",
                        "unit_raw": "µm",
                        "source_evidence": "hatch space of 100 µm",
                    },
                ]
            }
        ]
    }

    prepared, changes = prepare_process_variant_conditions(candidate)
    rows = prepared["candidate_stages"][0]["parameters_raw"]

    assert rows[0]["condition_label_raw"] == first_evidence
    assert rows[1]["condition_label_raw"] == first_evidence
    assert rows[2]["condition_label_raw"] == second_evidence
    assert rows[3]["condition_label_raw"] == second_evidence
    assert rows[4]["condition_label_raw"] != rows[5]["condition_label_raw"]
    assert "reported time: 5 min" in rows[4]["condition_label_raw"]
    assert "reported time: 30 min" in rows[5]["condition_label_raw"]
    assert "condition_label_raw" not in rows[6]
    assert "condition_label_raw" not in candidate["candidate_stages"][0][
        "parameters_raw"
    ][0]
    assert len(changes) == 6


def test_process_variant_conditions_preserve_distinct_energy_source_powers() -> None:
    candidate = {
        "candidate_stages": [
            {
                "parameters_raw": [
                    {
                        "parameter_name_raw": "Laser Power",
                        "value_raw": "5000",
                        "unit_raw": "W",
                        "source_evidence": "| Laser Power (W) | 5000 |",
                    },
                    {
                        "parameter_name_raw": "Wire Power",
                        "value_raw": "300",
                        "unit_raw": "W",
                        "source_evidence": "| Wire Power (W) | 300 |",
                    },
                ]
            },
            {
                "parameters_raw": [
                    {
                        "parameter_name_raw": "input laser power",
                        "value_raw": "5",
                        "unit_raw": "kW",
                        "source_evidence": "an input laser power of 5 kW",
                    },
                    {
                        "parameter_name_raw": "hot wire power",
                        "value_raw": "0.3",
                        "unit_raw": "kW",
                        "source_evidence": "a hot wire power of 0.3 kW",
                    },
                ]
            },
        ]
    }

    prepared, changes = prepare_process_variant_conditions(candidate)
    first_stage = prepared["candidate_stages"][0]["parameters_raw"]
    second_stage = prepared["candidate_stages"][1]["parameters_raw"]

    assert [row["condition_label_raw"] for row in first_stage] == [
        "laser",
        "wire",
    ]
    assert [row["condition_label_raw"] for row in second_stage] == [
        "laser",
        "hot_wire",
    ]
    assert len(changes) == 4
    assert all(change["before"] is None for change in changes)
    assert "condition_label_raw" not in candidate["candidate_stages"][0][
        "parameters_raw"
    ][0]


def test_process_variant_conditions_do_not_label_single_energy_power() -> None:
    candidate = {
        "candidate_stages": [
            {
                "parameters_raw": [
                    {
                        "parameter_name_raw": "Laser Power",
                        "value_raw": "250",
                        "unit_raw": "W",
                        "source_evidence": "laser power was 250 W",
                    },
                    {
                        "parameter_name_raw": "scan speed",
                        "value_raw": "1000",
                        "unit_raw": "mm/s",
                        "source_evidence": "scan speed was 1000 mm/s",
                    },
                ]
            }
        ]
    }

    prepared, changes = prepare_process_variant_conditions(candidate)

    assert prepared == candidate
    assert changes == []


def test_process_stage_compat_rehomes_split_table_parameters_without_mutation() -> None:
    candidate = {
        "candidate_stages": [
            {
                "candidate_stage_id": "cand_001",
                "stage_index_candidate": 1,
                "process_name_raw": "Printing Parameters",
                "parameters_raw": [
                    {
                        "parameter_name_raw": "Volumetric Energy Density",
                        "value_raw": "94.69",
                        "unit_raw": "J/mm^3",
                        "source_evidence": "| 1-1 | 2 | 94.69 |",
                    }
                ],
                "source_evidence": ["| 1-1 | 2 | 94.69 |"],
            },
            {
                "candidate_stage_id": "cand_002",
                "stage_index_candidate": 2,
                "process_name_raw": "post-HT",
                "parameters_raw": [
                    {
                        "parameter_name_raw": "Heating Time",
                        "value_raw": "2",
                        "unit_raw": "h",
                        "source_evidence": "| 1-1 | 2 | 94.69 |",
                    }
                ],
                "source_evidence": ["| 1-1 | 2 | 94.69 |"],
            },
            {
                "candidate_stage_id": "cand_003",
                "stage_index_candidate": 3,
                "process_name_raw": "LPBF",
                "parameters_raw": [
                    {
                        "parameter_name_raw": "Laser Power",
                        "value_raw": "250",
                        "unit_raw": "W",
                        "source_evidence": "| 1-1 | 250 | 1100 | 900 |",
                    },
                    {
                        "parameter_name_raw": "Scan Speed",
                        "value_raw": "1100",
                        "unit_raw": "mm/s",
                        "source_evidence": "| 1-1 | 250 | 1100 | 900 |",
                    },
                    {
                        "parameter_name_raw": "Heating Temperature",
                        "value_raw": "900",
                        "unit_raw": "°C",
                        "source_evidence": "| 1-1 | 250 | 1100 | 900 |",
                    },
                ],
                "source_evidence": ["| 1-1 | 250 | 1100 | 900 |"],
            },
        ]
    }

    def resolve_process(name, _code, _role, _rules):
        matches = {
            "heat treatment": {
                "code": "B2.HT.UNSPECIFIED",
                "parameter_profile": "HEAT_TREATMENT",
            },
            "LPBF": {
                "code": "A2.AM.PBF_LB",
                "parameter_profile": "AM_PBF",
            },
        }
        return matches.get(name), [], []

    def normalize_parameter(raw, _stage_uid, profile, _rules):
        aliases = {
            "Laser Power": "power",
            "Scan Speed": "scan_speed",
            "Heating Time": "duration",
            "Heating Temperature": "process_temperature",
        }
        code = aliases.get(raw["parameter_name_raw"])
        allowed = {
            "AM_PBF": {"power", "scan_speed"},
            "HEAT_TREATMENT": {"duration", "process_temperature"},
        }
        if code in allowed.get(profile, set()):
            return {"parameter_code": code}, [], []
        return {"parameter_code": "raw_unmapped_parameter"}, [], []

    rules = SimpleNamespace(
        parameter_catalog={
            "energy_density": {
                "model_policy": "auxiliary_derived_or_reported"
            }
        }
    )
    prepared, changes = prepare_process_stage_compat(
        candidate,
        rules=rules,
        resolve_process_type=resolve_process,
        normalize_parameter=normalize_parameter,
    )

    container, heat_treatment, lpbf = prepared["candidate_stages"]
    assert container["parameters_raw"] == []
    assert heat_treatment["process_name_raw"] == "heat treatment"
    assert [row["parameter_name_raw"] for row in heat_treatment["parameters_raw"]] == [
        "Heating Time",
        "Heating Temperature",
    ]
    assert [row["parameter_name_raw"] for row in lpbf["parameters_raw"]] == [
        "Laser Power",
        "Scan Speed",
        "Volumetric Energy Density",
    ]
    assert "| 1-1 | 250 | 1100 | 900 |" in heat_treatment["source_evidence"]
    assert candidate["candidate_stages"][0]["parameters_raw"][0][
        "parameter_name_raw"
    ] == "Volumetric Energy Density"
    assert candidate["candidate_stages"][1]["process_name_raw"] == "post-HT"
    assert candidate["candidate_stages"][2]["parameters_raw"][-1][
        "parameter_name_raw"
    ] == "Heating Temperature"
    assert {change["rule_id"] for change in changes} == {
        "compat.process_stage_alias.v1",
        "compat.process_container_parameter_rehome.v1",
        "compat.process_thermal_parameter_rehome.v1",
    }


def test_process_stage_compat_does_not_guess_an_isolated_container() -> None:
    candidate = {
        "candidate_stages": [
            {
                "candidate_stage_id": "cand_001",
                "stage_index_candidate": 1,
                "process_name_raw": "Printing Parameters",
                "parameters_raw": [
                    {
                        "parameter_name_raw": "Volumetric Energy Density",
                        "value_raw": "94.69",
                        "unit_raw": "J/mm^3",
                        "source_evidence": "table row",
                    }
                ],
                "source_evidence": ["table row"],
            }
        ]
    }

    prepared, changes = prepare_process_stage_compat(
        candidate,
        rules=SimpleNamespace(parameter_catalog={}),
        resolve_process_type=lambda *_args: (None, [], []),
        normalize_parameter=lambda *_args: (
            {"parameter_code": "raw_unmapped_parameter"},
            [],
            [],
        ),
    )

    assert prepared == candidate
    assert changes == []


def test_process_stage_compat_keeps_am_temperature_without_thermal_sibling() -> None:
    candidate = {
        "candidate_stages": [
            {
                "candidate_stage_id": "cand_001",
                "stage_index_candidate": 1,
                "process_name_raw": "LPBF",
                "parameters_raw": [
                    {
                        "parameter_name_raw": "Heating Temperature",
                        "value_raw": "200",
                        "unit_raw": "°C",
                        "source_evidence": "powder bed heating temperature was 200 °C",
                    }
                ],
                "source_evidence": ["powder bed heating temperature was 200 °C"],
            }
        ]
    }

    prepared, changes = prepare_process_stage_compat(
        candidate,
        rules=SimpleNamespace(parameter_catalog={}),
        resolve_process_type=lambda name, *_args: (
            {
                "code": "A2.AM.PBF_LB",
                "parameter_profile": "AM_PBF",
            }
            if name == "LPBF"
            else None,
            [],
            [],
        ),
        normalize_parameter=lambda *_args: (
            {"parameter_code": "raw_unmapped_parameter"},
            [],
            [],
        ),
    )

    assert prepared == candidate
    assert changes == []


def test_process_variant_route_compat_records_condition_audit() -> None:
    seen: list[dict] = []

    def normalize_parameter(raw, _stage_uid, _profile, _rules):
        return (
            {
                "parameter_code": "raw_unmapped_parameter",
                "parameter_name_raw": raw["parameter_name_raw"],
                "value_raw": raw["value_raw"],
                "unit_raw": raw["unit_raw"],
                "canonical_value": None,
                "canonical_unit": None,
            },
            [],
            [],
        )

    def normalize_route(candidate, _rules):
        seen.append(candidate)
        return {"route_type": "linear", "stages": []}, [], []

    runtime = SimpleNamespace(
        _unit_factor=lambda _raw, _canonical: None,
        normalize_parameter=normalize_parameter,
        normalize_route=normalize_route,
        _audit=lambda rule_id, path, before, after: {
            "rule_id": rule_id,
            "path": path,
            "before": before,
            "after": after,
        },
    )
    install_process_unit_compat(runtime)
    candidate = {
        "candidate_stages": [
            {
                "parameters_raw": [
                    {
                        "parameter_name_raw": "total duration",
                        "value_raw": "16",
                        "unit_raw": "h",
                        "source_evidence": "taking roughly 16 h total",
                    }
                ]
            },
            {
                "parameters_raw": [
                    {
                        "parameter_name_raw": "Laser Power",
                        "value_raw": "5000",
                        "unit_raw": "W",
                        "source_evidence": "Laser Power (W): 5000",
                    },
                    {
                        "parameter_name_raw": "Wire Power",
                        "value_raw": "300",
                        "unit_raw": "W",
                        "source_evidence": "Wire Power (W): 300",
                    },
                ]
            }
        ]
    }

    route, issues, audit = runtime.normalize_route(candidate, {})

    assert route == {"route_type": "linear", "stages": []}
    assert issues == []
    assert seen[0]["candidate_stages"][0]["parameters_raw"][0][
        "condition_label_raw"
    ] == "taking roughly 16 h total"
    assert [row["condition_label_raw"] for row in seen[0]["candidate_stages"][1][
        "parameters_raw"
    ]] == ["laser", "wire"]
    assert len(audit) == 3
    assert {row["rule_id"] for row in audit} == {
        "compat.process_variant_condition.v1"
    }
    assert "condition_label_raw" not in candidate["candidate_stages"][0][
        "parameters_raw"
    ][0]
    assert "condition_label_raw" not in candidate["candidate_stages"][1][
        "parameters_raw"
    ][0]
