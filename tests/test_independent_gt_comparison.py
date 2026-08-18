from __future__ import annotations

import pytest

from knowmat.evaluation.independent_gt_comparison import (
    compare_claim_sets,
    flatten_v11,
    issue_candidates,
    semantic_score,
    value_score,
)


def _expert(*, sample: str = "S1", condition: str = "25 °C") -> dict:
    return {
        "uid": "clm_0001", "source": "expert", "paper_key": "paper",
        "axis": "Properties",
        "owner": {"material_id": "m1", "material_name": "Ti-6Al-4V", "sample_id": sample, "state": "as-built", "region": None, "orientation": None, "role": "Target"},
        "semantic_key": "ultimate_tensile_strength", "name_raw": "UTS",
        "value": {"kind": "scalar", "raw": "1000", "number": 1000.0, "min": None, "max": None, "operator": None, "bound": None, "stddev": None, "text": None},
        "unit_raw": "MPa", "condition": condition, "origin": "author_experiment",
        "evidence": ["UTS was 1000 MPa"], "raw_path": "x", "raw": {},
    }


def test_property_alias_and_unit_value_match() -> None:
    left = {**_expert(), "semantic_key": "engineering_uts", "unit_raw": "GPa", "value": {**_expert()["value"], "number": 1.0, "raw": "1.0"}}
    right = _expert()
    assert semantic_score(left, right) == 1.0
    assert value_score(left, right) == 1.0


def test_tex_and_unicode_micrometre_units_match() -> None:
    left = {
        **_expert(),
        "unit_raw": r"\mum",
        "value": {**_expert()["value"], "number": 12.4, "raw": "12.4"},
    }
    right = {
        **_expert(),
        "unit_raw": "µm",
        "value": {**_expert()["value"], "number": 12.4, "raw": "12.4"},
    }

    assert value_score(left, right) == 1.0


def test_kelvin_and_celsius_values_match_after_conversion() -> None:
    left = {
        **_expert(),
        "unit_raw": "K",
        "value": {**_expert()["value"], "number": 1303.15, "raw": "1303.15"},
    }
    right = {
        **_expert(),
        "unit_raw": "°C",
        "value": {**_expert()["value"], "number": 1030.0, "raw": "1030"},
    }

    assert value_score(left, right) == 1.0


def test_vickers_load_notation_variants_match() -> None:
    left = {**_expert(), "unit_raw": "HV_{0.1}"}
    right = {**_expert(), "unit_raw": "HV₀.₁"}

    assert value_score(left, right) == 1.0


def test_percent_presentation_variants_match() -> None:
    left = {**_expert(), "unit_raw": "%RD"}
    right = {**_expert(), "unit_raw": "%"}

    assert value_score(left, right) == 1.0


def test_kilowatt_and_watt_values_match_after_conversion() -> None:
    left = {
        **_expert(),
        "unit_raw": "kW",
        "value": {**_expert()["value"], "number": 5.0, "raw": "5"},
    }
    right = {
        **_expert(),
        "unit_raw": "W",
        "value": {**_expert()["value"], "number": 5000.0, "raw": "5000"},
    }

    assert value_score(left, right) == 1.0


def test_core_tensile_alias_does_not_match_inside_crystallographic_word() -> None:
    crystallographic = {
        **_expert(),
        "semantic_key": "crystallographic_plane_111_2theta",
        "name_raw": "crystallographic plane (111) 2theta",
    }

    report = compare_claim_sets([crystallographic], [])

    assert report["unique_modes"]["strict"]["core_tensile"]["system"] == 0


@pytest.mark.parametrize(
    ("system_semantic", "expert_semantic"),
    [
        ("beam_diameter", "lpbf_laser_spot_diameter"),
        ("hatch_spacing", "lpbf_hatch_space"),
        ("preheat_temperature", "lpbf_build_plate_temperature"),
        ("oxygen_content", "lpbf_oxygen_limit"),
        ("duration", "hold_time"),
        ("atmosphere", "deposition_environment"),
    ],
)
def test_process_parameter_semantic_aliases_match(
    system_semantic: str, expert_semantic: str
) -> None:
    left = {
        **_expert(),
        "axis": "Processing",
        "semantic_key": system_semantic,
        "name_raw": system_semantic,
    }
    right = {
        **_expert(),
        "axis": "Processing",
        "semantic_key": expert_semantic,
        "name_raw": expert_semantic,
    }

    assert semantic_score(left, right) == 1.0


@pytest.mark.parametrize(
    ("generic_semantic", "specific_semantic", "evidence"),
    [
        (
            "duration",
            "vacuum_sintering_time",
            "vacuum sintering at 1255 °C with a holding time of 4 h",
        ),
        (
            "duration",
            "solution_treatment_time",
            "solution treated at 1150 °C for 2 h",
        ),
        (
            "duration",
            "aging_time",
            "aged at 745 °C for 20 h",
        ),
        (
            "duration",
            "annealing_time",
            "annealed at 800 °C for 4 h",
        ),
        (
            "process_temperature",
            "heat_treatment_temperature",
            "heat treated at 900 °C for 2 h",
        ),
        (
            "process_temperature",
            "homogenization_temperature",
            "homogenized at 1065 °C before aging",
        ),
    ],
)
def test_guarded_thermal_process_semantic_families_match(
    generic_semantic: str, specific_semantic: str, evidence: str
) -> None:
    left = {
        **_expert(),
        "axis": "Processing",
        "semantic_key": generic_semantic,
        "name_raw": generic_semantic,
        "evidence": [evidence],
    }
    right = {
        **_expert(),
        "axis": "Processing",
        "semantic_key": specific_semantic,
        "name_raw": specific_semantic,
        "evidence": [evidence],
    }

    assert semantic_score(left, right) == 1.0


def test_generic_process_time_is_not_collapsed_without_thermal_context() -> None:
    generic = {
        **_expert(),
        "axis": "Processing",
        "semantic_key": "duration",
        "name_raw": "duration",
        "evidence": ["the mixing time was 4 h"],
    }
    delay = {
        **_expert(),
        "axis": "Processing",
        "semantic_key": "interlayer_delay",
        "name_raw": "interlayer delay",
        "evidence": ["the interlayer delay was 4 h"],
    }

    assert semantic_score(generic, delay) < 1.0


def test_different_thermal_operations_are_not_collapsed_by_shared_duration() -> None:
    aged = {
        **_expert(),
        "axis": "Processing",
        "semantic_key": "duration",
        "name_raw": "duration",
        "evidence": ["isothermally aged at 800 °C for 4 h"],
    }
    dried = {
        **_expert(),
        "axis": "Processing",
        "semantic_key": "powder_drying_time",
        "name_raw": "powder drying time",
        "evidence": ["the powder was dried for 4 h"],
    }

    assert semantic_score(aged, dried) < 1.0


def test_distinct_discrete_process_temperatures_do_not_match() -> None:
    left = {
        **_expert(),
        "unit_raw": "°C",
        "value": {**_expert()["value"], "number": 1225.0, "raw": "1225"},
    }
    right = {
        **_expert(),
        "unit_raw": "°C",
        "value": {**_expert()["value"], "number": 1255.0, "raw": "1255"},
    }

    assert value_score(left, right) == 0.0


def test_scalar_temperature_does_not_match_inequality_bound() -> None:
    scalar = {
        **_expert(),
        "unit_raw": "°C",
        "value": {
            **_expert()["value"],
            "kind": "scalar",
            "number": 1180.0,
            "raw": "1180",
        },
    }
    inequality = {
        **_expert(),
        "unit_raw": "°C",
        "value": {
            **_expert()["value"],
            "kind": "inequality",
            "number": 1200.0,
            "raw": "> 1200",
            "operator": ">",
            "bound": 1200.0,
        },
    }

    assert value_score(scalar, inequality) == 0.0


def test_named_thermal_variant_does_not_match_other_temperature_hold() -> None:
    named = {
        **_expert(),
        "axis": "Processing",
        "semantic_key": "s1290_hold_time",
        "name_raw": "S1290 hold time",
        "evidence": [
            "holding temperatures were 1200, 1220, 1240, 1260, 1280, "
            "1290 and 1300 °C for 4 h"
        ],
    }
    other = {
        **_expert(),
        "axis": "Processing",
        "semantic_key": "duration",
        "name_raw": "duration",
        "evidence": ["the sample was sintered at 1280 °C for 4 h"],
    }

    assert semantic_score(named, other) == 0.0


def test_energy_source_condition_qualifies_power_without_becoming_test_condition() -> None:
    system = [
        {
            **_expert(condition="hot_wire"),
            "uid": "sys_1",
            "source": "final_v5",
            "axis": "Processing",
            "semantic_key": "power",
            "name_raw": "power",
            "value": {**_expert()["value"], "number": 0.3, "raw": "0.3"},
            "unit_raw": "kW",
            "evidence": ["a hot wire power of 0.3 kW"],
        }
    ]
    expert = [
        {
            **_expert(condition=""),
            "axis": "Processing",
            "semantic_key": "hot_wire_power",
            "name_raw": "hot wire power",
            "value": {**_expert()["value"], "number": 0.3, "raw": "0.3"},
            "unit_raw": "kW",
            "evidence": ["a hot wire power of 0.3 kW"],
        }
    ]

    report = compare_claim_sets(system, expert)

    assert report["modes"]["loose"]["micro"]["matched"] == 1
    assert report["modes"]["strict"]["micro"]["matched"] == 1


def test_process_stage_codes_are_not_collapsed_as_parameter_aliases() -> None:
    left = {
        **_expert(),
        "axis": "Processing",
        "semantic_key": "process_stage_A2.AM.PBF_LB",
    }
    right = {
        **_expert(),
        "axis": "Processing",
        "semantic_key": "process_stage_A2.AM.DED_GENERIC",
    }

    assert semantic_score(left, right) < 1.0


def test_strict_rejects_wrong_sample_while_loose_matches() -> None:
    system = [{**_expert(sample="S2"), "uid": "sys_1", "source": "final_v5"}]
    expert = [_expert(sample="S1")]
    report = compare_claim_sets(system, expert)
    assert report["modes"]["loose"]["micro"]["matched"] == 1
    assert report["modes"]["strict"]["micro"]["matched"] == 0
    issues = issue_candidates(system, expert, report)
    assert [row["code"] for row in issues] == ["wrong_owner"]


def test_strict_matches_cited_nominal_reference_owner_by_alloy_designation() -> None:
    system = [
        {
            **_expert(sample="nickel-based alloy 625 [18] [reference]", condition=""),
            "uid": "sys_1",
            "source": "final_v5",
            "axis": "Composition",
            "semantic_key": "composition_element_ni",
            "name_raw": "Ni",
            "owner": {
                "material_id": "item_1",
                "material_name": "nickel-based alloy 625",
                "sample_id": "nickel-based alloy 625 [18] [reference]",
                "state": "nominal composition",
                "region": None,
                "orientation": None,
                "role": "Reference",
            },
            "unit_raw": "wt%",
        }
    ]
    expert = [
        {
            **system[0],
            "uid": "clm_1",
            "source": "expert",
            "owner": {
                "material_id": "expert_1",
                "material_name": "binder-jet printed alloy 625",
                "sample_id": "nominal alloy 625",
                "state": "nominal composition",
                "region": None,
                "orientation": None,
                "role": "Reference",
            },
        }
    ]

    report = compare_claim_sets(system, expert)

    assert report["modes"]["strict"]["micro"]["matched"] == 1


def test_reference_alloy_designation_does_not_override_state_conflict() -> None:
    system = _expert(sample="alloy 625 [reference]", condition="")
    system["owner"] = {
        **system["owner"],
        "material_name": "nickel-based alloy 625",
        "sample_id": "alloy 625 [reference]",
        "state": "as-built",
        "role": "Reference",
    }
    expert = {**system, "uid": "clm_1", "source": "expert"}
    expert["owner"] = {
        **system["owner"],
        "material_name": "binder-jet printed alloy 625",
        "sample_id": "nominal alloy 625",
        "state": "nominal composition",
    }

    report = compare_claim_sets([system], [expert])

    assert report["modes"]["loose"]["micro"]["matched"] == 1
    assert report["modes"]["strict"]["micro"]["matched"] == 0


def test_strict_rejects_missing_condition() -> None:
    system = [{**_expert(condition=""), "uid": "sys_1", "source": "final_v5"}]
    report = compare_claim_sets(system, [_expert(condition="25 °C")])
    assert report["modes"]["loose"]["micro"]["matched"] == 1
    assert report["modes"]["strict"]["micro"]["matched"] == 0


def test_flatten_composition_is_atomic_and_skips_not_reported_parameter() -> None:
    document = {
        "items": [{
            "Item_ID": "item_1", "Sample_ID": "S1", "Role": "Target", "Data_Nature": "Experimental",
            "Extracted_Data": {
                "Composition": {
                    "Material_Identity": {"material_name_raw": "Alloy X"},
                    "Composition_Observations": [{"sample_id": "S1", "material_state": "powder", "basis": "wt%", "components": [
                        {"canonical_name": "Ni", "value_kind": "scalar", "value": 50, "value_raw": "50", "unit_raw": "wt%", "data_nature": "reported"},
                        {"canonical_name": "Cr", "value_kind": "scalar", "value": 20, "value_raw": "20", "unit_raw": "wt%", "data_nature": "reported"},
                    ], "source_evidence": "table row"}],
                },
                "Processing": {"Process_Route": {"stages": [{"process_code": "A2.AM.PBF_LB", "process_role": "primary_forming", "parameters": [
                    {"parameter_code": "power", "status": "not_reported", "value_kind": "unknown", "canonical_value": None, "canonical_unit": "W"}
                ]}]}},
                "Structure": {"Structure_Observations": [], "Characterization": []},
                "Properties": [],
            },
        }]
    }
    claims = flatten_v11(document, source="business_gt", paper_key="paper")
    composition = [row for row in claims if row["axis"] == "Composition"]
    processing = [row for row in claims if row["axis"] == "Processing"]
    assert len(composition) == 2
    assert len(processing) == 1  # stage identity only; absent power is not a fact


def test_flatten_process_uses_stage_context_and_canonical_value_unit_pair() -> None:
    document = {
        "items": [
            {
                "Item_ID": "item_1",
                "Sample_ID": "S1",
                "Role": "Target",
                "Data_Nature": "Experimental",
                "Extracted_Data": {
                    "Composition": {
                        "Material_Identity": {"material_name_raw": "Ti-6Al-4V"}
                    },
                    "Processing": {
                        "Process_Route": {
                            "stages": [
                                {
                                    "process_code": "B2.HT.UNSPECIFIED",
                                    "parameter_profile": "HEAT_TREATMENT",
                                    "parameters": [
                                        {
                                            "parameter_code": "duration",
                                            "status": "reported",
                                            "value_kind": "scalar",
                                            "value_raw": "2",
                                            "unit_raw": "h",
                                            "canonical_value": 7200.0,
                                            "canonical_unit": "s",
                                            "source_evidence": "heated for 2 h",
                                        },
                                        {
                                            "parameter_code": "process_temperature",
                                            "status": "reported",
                                            "value_kind": "scalar",
                                            "value_raw": "900",
                                            "unit_raw": "°C",
                                            "canonical_value": 1173.15,
                                            "canonical_unit": "K",
                                            "source_evidence": "heated at 900 °C",
                                        },
                                    ],
                                }
                            ]
                        }
                    },
                    "Structure": {"Structure_Observations": [], "Characterization": []},
                    "Properties": [],
                },
            }
        ]
    }
    system = flatten_v11(document, source="final_v5", paper_key="paper")
    system = [row for row in system if not row["semantic_key"].startswith("process_stage_")]
    expert = [
        {
            **_expert(sample="S1", condition=""),
            "axis": "Processing",
            "semantic_key": "heat_treatment_time",
            "name_raw": "Heating Time",
            "value": {**_expert()["value"], "raw": "2", "number": 2.0},
            "unit_raw": "h",
        },
        {
            **_expert(sample="S1", condition=""),
            "uid": "clm_0002",
            "axis": "Processing",
            "semantic_key": "heat_treatment_temperature",
            "name_raw": "Heating Temperature",
            "value": {**_expert()["value"], "raw": "900", "number": 900.0},
            "unit_raw": "°C",
        },
    ]

    report = compare_claim_sets(system, expert)

    assert report["modes"]["loose"]["micro"]["matched"] == 2
    assert {row["unit_raw"] for row in system} == {"s", "K"}
    assert {row["value"]["number"] for row in system} == {7200.0, 1173.15}


def test_flatten_numeric_raw_unmapped_parameter_is_comparable() -> None:
    document = {
        "items": [
            {
                "Item_ID": "item_1",
                "Sample_ID": "S1",
                "Role": "Target",
                "Data_Nature": "Experimental",
                "Extracted_Data": {
                    "Composition": {
                        "Material_Identity": {"material_name_raw": "Ti-6Al-4V"}
                    },
                    "Processing": {
                        "Process_Route": {
                            "stages": [
                                {
                                    "process_code": "A2.AM.PBF_LB",
                                    "parameter_profile": "AM_PBF",
                                    "parameters": [
                                        {
                                            "parameter_code": "raw_unmapped_parameter",
                                            "parameter_name_raw": "Volumetric Energy Density",
                                            "status": "ambiguous",
                                            "value_kind": "unknown",
                                            "value_raw": "94.69",
                                            "unit_raw": "J/mm^3",
                                            "canonical_value": None,
                                            "canonical_unit": None,
                                            "source_evidence": "VED was 94.69 J/mm^3",
                                        }
                                    ],
                                }
                            ]
                        }
                    },
                    "Structure": {"Structure_Observations": [], "Characterization": []},
                    "Properties": [],
                },
            }
        ]
    }
    system = flatten_v11(document, source="final_v5", paper_key="paper")
    system = [row for row in system if row["semantic_key"] == "volumetric_energy_density"]
    expert = [
        {
            **_expert(sample="S1", condition=""),
            "axis": "Processing",
            "semantic_key": "lpbf_volumetric_energy_density",
            "name_raw": "Volumetric Energy Density",
            "value": {**_expert()["value"], "raw": "94.69", "number": 94.69},
            "unit_raw": "J/mm³",
        }
    ]

    report = compare_claim_sets(system, expert)

    assert system[0]["value"]["kind"] == "scalar"
    assert system[0]["value"]["number"] == 94.69
    assert report["modes"]["loose"]["micro"]["matched"] == 1
