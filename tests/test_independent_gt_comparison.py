from __future__ import annotations

import pytest

from knowmat.evaluation.independent_gt_comparison import (
    _numeric_rounding_tolerance,
    compare_claim_sets,
    condition_score,
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


def test_characterization_nested_provenance_is_one_method_claim() -> None:
    document = {
        "Paper_Metadata": {"source_text": "paper_final_output.md"},
        "items": [
            {
                "Item_ID": "item_001",
                "Sample_ID": "S1",
                "Role": "Target",
                "Data_Nature": "Experimental",
                "Extracted_Data": {
                    "Structure": {
                        "Characterization": [
                            {
                                "method_raw": "SEM",
                                "method_class": "SEM",
                                "equipment_raw": "FE-SEM",
                                "condition_raw": "operated at 30 kV",
                                "source_evidence": ["SEM was performed using FE-SEM at 30 kV"],
                            }
                        ]
                    }
                },
            }
        ],
    }

    claims = flatten_v11(document, source="final_v5", paper_key="paper")

    characterization = [row for row in claims if row["axis"] == "Characterization"]
    assert len(characterization) == 1
    assert characterization[0]["semantic_key"] == "sem_method"
    assert characterization[0]["name_raw"] == "SEM"
    assert characterization[0]["value"]["raw"] == "FE-SEM"


def test_enriched_tensile_owner_projects_material_state_and_orientation() -> None:
    document = {
        "items": [
            {
                "Item_ID": "item_001",
                "Sample_ID": "Inconel 625 / LPBF tensile specimen [HIPed] / X",
                "Role": "Target",
                "Data_Nature": "Experimental",
                "Extracted_Data": {
                    "Properties": [
                        {
                            "Property_Name_Raw": "Ultimate Tensile Strength",
                            "Canonical_Property": "ultimate_tensile_strength",
                            "Value": {
                                "value_kind": "scalar",
                                "value_raw": "0.906 ± 0.028",
                                "unit_raw": "GPa",
                                "value_num": 906.0,
                                "value_stddev": 28.0,
                                "canonical_unit": "MPa",
                            },
                            "Test_Condition": {
                                "original": "strain rate of 0.005 mm/min/min",
                                "original_excerpt": "strain rate of 0.005 mm/min/min",
                                "simplified": (
                                    "Method: tensile test; Condition: strain rate "
                                    "of 0.005 mm/min/min"
                                ),
                                "Specimen": {"specimen_raw": "X"},
                                "specimen_raw": "X",
                            },
                            "source_evidence": ["LPBF X UTS was 0.906 ± 0.028 GPa"],
                        }
                    ]
                },
            }
        ]
    }

    claim = flatten_v11(document, source="final_v5", paper_key="paper")[0]

    assert claim["owner"] == {
        "material_id": "item_001",
        "material_name": "Inconel 625",
        "sample_id": "LPBF tensile specimen",
        "state": "HIPed",
        "region": None,
        "location": None,
        "orientation": "X",
        "role": "Target",
    }
    assert claim["condition"] == "strain rate of 0.005 mm/min/min"


def test_condition_score_accepts_owner_orientation_as_condition_coordinate() -> None:
    system = {
        **_expert(condition="tensile test"),
        "owner": {**_expert()["owner"], "orientation": "X"},
    }
    expert = {
        **_expert(condition="tensile test; X orientation"),
        "owner": {**_expert()["owner"], "orientation": "X"},
    }
    assert condition_score(system, expert) == 1.0


def test_condition_text_uses_expert_raw_instead_of_serializing_condition_json() -> None:
    """Structured expert conditions must compare by their canonical raw text."""

    system = {
        **_expert(condition="room temperature tensile test"),
    }
    expert = {
        **_expert(
            condition={
                "raw": "room-temperature tensile test",
                "temperature_raw": "room temperature",
                "details": {"replicates": 3, "standard": "ASTM B557M-10"},
            }
        ),
    }

    assert condition_score(system, expert) >= 0.65


@pytest.mark.parametrize(
    ("system_semantic", "system_name", "expert_semantic", "expert_name"),
    [
        ("TE", "TE", "total_elongation", "total elongation"),
        ("EAB", "EAB", "elongation_at_break", "elongation at break"),
        (
            "modulus_of_elasticity",
            "modulus of elasticity",
            "elastic_modulus",
            "elastic modulus",
        ),
    ],
)
def test_property_domain_aliases_match_without_changing_payload(
    system_semantic: str,
    system_name: str,
    expert_semantic: str,
    expert_name: str,
) -> None:
    left = {
        **_expert(),
        "semantic_key": system_semantic,
        "name_raw": system_name,
    }
    right = {
        **_expert(),
        "semantic_key": expert_semantic,
        "name_raw": expert_name,
    }

    assert semantic_score(left, right) == 1.0


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
    "semantic_key",
    [
        "elongation_relative_ratio",
        "elongation_relative_change",
        "yield_strength_retention",
        "yield_strength_difference",
        "yield_strength_increment",
        "elongation_improvement",
    ],
)
def test_relative_tensile_quantity_is_not_counted_as_absolute_core_tensile(
    semantic_key: str,
) -> None:
    relative = {
        **_expert(),
        "semantic_key": semantic_key,
        "name_raw": semantic_key.replace("_", " "),
        "unit_raw": "%",
    }

    report = compare_claim_sets([relative], [])

    assert report["unique_modes"]["loose"]["core_tensile"]["system"] == 0


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


def test_uncertainty_intervals_do_not_substitute_for_distinct_numeric_centers() -> None:
    left = {
        **_expert(),
        "value": {
            **_expert()["value"],
            "number": 817.0,
            "stddev": 8.68,
            "raw": "817 ± 8.68",
        },
    }
    right = {
        **_expert(),
        "value": {
            **_expert()["value"],
            "number": 825.3,
            "stddev": 3.10,
            "raw": "825.3 ± 3.10",
        },
    }

    assert value_score(left, right) == 0.0


def test_uncertainty_values_match_by_center_even_with_different_spread() -> None:
    left = {
        **_expert(),
        "value": {
            **_expert()["value"],
            "number": 0.71,
            "stddev": 0.02,
            "raw": "0.71 ± 0.02",
        },
        "unit_raw": "GPa",
    }
    right = {
        **_expert(),
        "value": {
            **_expert()["value"],
            "number": 0.707,
            "stddev": 0.012,
            "raw": "0.707 ± 0.012",
        },
        "unit_raw": "GPa",
    }

    assert value_score(left, right) == 1.0


def test_rounded_uncertainty_center_matches_precise_table_center() -> None:
    left = {
        **_expert(),
        "value": {
            **_expert()["value"],
            "number": 0.48,
            "stddev": 0.05,
            "raw": "0.48 ± 0.05",
        },
        "unit_raw": "GPa",
    }
    right = {
        **_expert(),
        "value": {
            **_expert()["value"],
            "number": 0.484,
            "stddev": 0.052,
            "raw": "0.484 ± 0.052",
        },
        "unit_raw": "GPa",
    }

    assert value_score(left, right) == 1.0


def test_rounded_center_uses_source_unit_before_canonical_conversion() -> None:
    left = {
        **_expert(),
        "value": {
            **_expert()["value"],
            "number": 390.0,
            "stddev": 20.0,
            "raw": "0.39 ± 0.02",
        },
        "unit_raw": "MPa",
        "raw": {"Value": {"unit_raw": "GPa", "canonical_unit": "MPa"}},
    }
    right = {
        **_expert(),
        "value": {
            **_expert()["value"],
            "number": 0.393,
            "stddev": 0.002,
            "raw": "0.393 ± 0.002",
        },
        "unit_raw": "GPa",
    }

    assert value_score(left, right) == 1.0


def test_uncertainty_value_still_matches_scalar_center() -> None:
    uncertainty = {
        **_expert(),
        "value": {
            **_expert()["value"],
            "number": 817.0,
            "stddev": 8.68,
            "raw": "817 ± 8.68",
        },
    }
    scalar = {
        **_expert(),
        "value": {
            **_expert()["value"],
            "number": 817.0,
            "stddev": None,
            "raw": "817",
        },
    }

    assert value_score(uncertainty, scalar) == 1.0


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


def test_energy_source_discriminator_retains_composite_process_environment() -> None:
    environment = "LHW-DED deposition in inert argon atmosphere"
    system = [
        {
            **_expert(condition=f"laser | {environment}"),
            "uid": "sys_1",
            "source": "final_v5",
            "axis": "Processing",
            "semantic_key": "power",
            "name_raw": "power",
            "value": {**_expert()["value"], "number": 5000.0, "raw": "5000"},
            "unit_raw": "W",
            "evidence": ["Laser Power (W): 5000"],
        }
    ]
    expert = [
        {
            **_expert(condition="LHW-DED in inert argon"),
            "axis": "Processing",
            "semantic_key": "laser_power",
            "name_raw": "laser power",
            "value": {**_expert()["value"], "number": 5000.0, "raw": "5000"},
            "unit_raw": "W",
            "evidence": ["Laser Power (W): 5000"],
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


def test_reference_owner_matches_author_year_and_et_al_sample_aliases() -> None:
    system = _expert(sample="LPBF printed Inconel 625 Amato et al. [reference]", condition="HIPed at 1120 °C")
    system["uid"] = "sys_1"
    system["source"] = "final_v5"
    system["owner"] = {
        **system["owner"],
        "material_name": "LPBF printed Inconel 625",
        "sample_id": "LPBF printed Inconel 625 Amato et al. [reference]",
        "state": None,
        "role": "Reference",
    }
    expert = {**system, "uid": "clm_1", "source": "expert"}
    expert["owner"] = {
        **system["owner"],
        "material_id": "Amato2012_LPBF_HIPed",
        "material_name": "Inconel 625",
        "sample_id": "Amato2012_LPBF_HIPed",
    }

    report = compare_claim_sets([system], [expert])

    assert report["modes"]["strict"]["micro"]["matched"] == 1


def test_reference_author_alias_does_not_merge_distinct_process_samples() -> None:
    system = _expert(sample="EPBF printed Inconel 625 Amato et al. [reference]", condition="HIPed at 1120 °C")
    system["uid"] = "sys_1"
    system["source"] = "final_v5"
    system["owner"] = {
        **system["owner"],
        "material_name": "EPBF printed Inconel 625",
        "sample_id": "EPBF printed Inconel 625 Amato et al. [reference]",
        "state": None,
        "role": "Reference",
    }
    expert = {**system, "uid": "clm_1", "source": "expert"}
    expert["owner"] = {
        **system["owner"],
        "material_id": "Amato2012_LPBF_HIPed",
        "material_name": "Inconel 625",
        "sample_id": "Amato2012_LPBF_HIPed",
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


def _point_composition_document(*locations: str) -> dict:
    return {
        "items": [
            {
                "Item_ID": "item_ga_1300",
                "Sample_ID": "GA sample sintered at 1300 °C",
                "Role": "Target",
                "Data_Nature": "Experimental",
                "Extracted_Data": {
                    "Composition": {
                        "Material_Identity": {
                            "material_name_raw": "binder-jet printed alloy 625"
                        },
                        "Composition_Observations": [
                            {
                                "sample_id": location,
                                "material_state": "sintered 1300 °C for 4 h",
                                "basis": "wt%",
                                "source_type": "measured",
                                "components": [
                                    {
                                        "canonical_name": "Ni",
                                        "value_kind": "scalar",
                                        "value": 61.7,
                                        "value_raw": "61.7",
                                        "unit_raw": "wt%",
                                        "data_nature": "reported",
                                    }
                                ],
                            }
                            for location in locations
                        ],
                    },
                    "Processing": {"Process_Route": {"stages": []}},
                    "Structure": {
                        "Structure_Observations": [],
                        "Characterization": [],
                    },
                    "Properties": [],
                },
            }
        ]
    }


def test_flatten_composition_preserves_material_owner_and_projects_point_location() -> None:
    claims = flatten_v11(
        _point_composition_document("Point 3"),
        source="final_v5",
        paper_key="paper",
    )

    assert len(claims) == 1
    assert claims[0]["owner"]["sample_id"] == "GA sample sintered at 1300 °C"
    assert claims[0]["owner"]["location"] == "Point 3"
    assert claims[0]["owner"]["region"] is None


def test_composition_point_matches_across_sample_and_region_representations() -> None:
    system = {
        **_expert(sample="S1280", condition=""),
        "uid": "sys_1",
        "source": "final_v5",
        "axis": "Composition",
        "semantic_key": "composition_element_ni",
        "name_raw": "Ni",
        "unit_raw": "wt%",
        "owner": {
            **_expert()["owner"],
            "sample_id": "S1280",
            "state": "sintered 1280 °C for 4 h",
            "region": "EDS point 1",
        },
    }
    expert = {
        **system,
        "uid": "clm_1",
        "source": "expert",
        "owner": {
            **system["owner"],
            "sample_id": "Point 1",
            "region": "grain boundary/precipitate",
        },
    }

    report = compare_claim_sets([system], [expert])

    assert report["modes"]["strict"]["micro"]["matched"] == 1


def test_composition_point_alias_does_not_hide_specimen_conflict() -> None:
    system = {
        **_expert(sample="GA", condition=""),
        "uid": "sys_1",
        "source": "final_v5",
        "axis": "Composition",
        "semantic_key": "composition_element_ni",
        "owner": {
            **_expert()["owner"],
            "sample_id": "GA",
            "location": "Point 1",
        },
    }
    expert = {
        **system,
        "uid": "clm_1",
        "source": "expert",
        "owner": {
            **system["owner"],
            "sample_id": "WA",
            "location": "EDS point 1",
        },
    }

    report = compare_claim_sets([system], [expert])

    assert report["modes"]["loose"]["micro"]["matched"] == 1
    assert report["modes"]["strict"]["micro"]["matched"] == 0


def test_morphology_region_is_not_treated_as_a_point_alias() -> None:
    system = {
        **_expert(sample="S1280", condition=""),
        "uid": "sys_1",
        "source": "final_v5",
        "axis": "Composition",
        "semantic_key": "composition_element_ni",
        "owner": {
            **_expert()["owner"],
            "sample_id": "S1280",
            "region": "matrix",
            "location": "Point 1",
        },
    }
    expert = {
        **system,
        "uid": "clm_1",
        "source": "expert",
        "owner": {**system["owner"], "location": "Point 2"},
    }

    report = compare_claim_sets([system], [expert])

    assert report["modes"]["strict"]["micro"]["matched"] == 0


def test_unique_composition_keeps_equal_values_at_distinct_points() -> None:
    claims = flatten_v11(
        _point_composition_document("Point 1", "Point 2"),
        source="final_v5",
        paper_key="paper",
    )

    report = compare_claim_sets(claims, [])

    assert report["counts"]["system"] == 2
    assert report["counts"]["unique_system"] == 2


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


@pytest.mark.parametrize("source", ["final_v5", "business_gt"])
@pytest.mark.parametrize(
    ("parameter", "expected_value", "expected_unit"),
    [
        (
            {
                "parameter_code": "preheat_temperature",
                "status": "reported",
                "value_kind": "scalar",
                "value_raw": "~850",
                "unit_raw": "°C",
                "canonical_value": 1123.15,
                "canonical_unit": "K",
            },
            {
                "kind": "scalar",
                "raw": "1123.15",
                "number": 1123.15,
                "min": None,
                "max": None,
                "operator": None,
                "bound": None,
                "stddev": None,
                "text": None,
            },
            "K",
        ),
        (
            {
                "parameter_code": "current",
                "status": "reported",
                "value_kind": "scalar",
                "value_raw": "14",
                "unit_raw": "mA",
                "canonical_value": 0.014,
                "canonical_unit": "A",
            },
            {
                "kind": "scalar",
                "raw": "0.014",
                "number": 0.014,
                "min": None,
                "max": None,
                "operator": None,
                "bound": None,
                "stddev": None,
                "text": None,
            },
            "A",
        ),
        (
            {
                "parameter_code": "duration",
                "status": "reported",
                "value_kind": "scalar",
                "value_raw": "60",
                "unit_raw": "h",
                "canonical_value": 216000.0,
                "canonical_unit": "s",
            },
            {
                "kind": "scalar",
                "raw": "216000",
                "number": 216000.0,
                "min": None,
                "max": None,
                "operator": None,
                "bound": None,
                "stddev": None,
                "text": None,
            },
            "s",
        ),
        (
            {
                "parameter_code": "particle_size",
                "status": "reported",
                "value_kind": "range",
                "value_raw": "50–70",
                "unit_raw": "µm",
                "canonical_value": [0.05, 0.07],
                "canonical_unit": "mm",
            },
            {
                "kind": "range",
                "raw": "0.05–0.07",
                "number": None,
                "min": 0.05,
                "max": 0.07,
                "operator": None,
                "bound": None,
                "stddev": None,
                "text": None,
            },
            "mm",
        ),
        (
            {
                "parameter_code": "duration",
                "status": "reported",
                "value_kind": "categorical",
                "value_raw": "4 h",
                "unit_raw": "h",
                "canonical_value": 14400.0,
                "canonical_unit": "s",
            },
            {
                "kind": "scalar",
                "raw": "14400",
                "number": 14400.0,
                "min": None,
                "max": None,
                "operator": None,
                "bound": None,
                "stddev": None,
                "text": None,
            },
            "s",
        ),
    ],
)
def test_flatten_selects_complete_canonical_numeric_pair_for_both_v11_sources(
    source: str,
    parameter: dict,
    expected_value: dict,
    expected_unit: str,
) -> None:
    document = {
        "items": [
            {
                "Item_ID": "item_1",
                "Sample_ID": "S1",
                "Role": "Target",
                "Data_Nature": "Experimental",
                "Extracted_Data": {
                    "Processing": {
                        "Process_Route": {
                            "stages": [
                                {
                                    "process_code": "A2.AM.PBF_EB",
                                    "parameters": [parameter],
                                }
                            ]
                        }
                    }
                },
            }
        ]
    }

    claims = flatten_v11(document, source=source, paper_key="paper")
    claim = next(
        row
        for row in claims
        if row["axis"] == "Processing"
        and row["semantic_key"] == parameter["parameter_code"]
    )

    assert claim["value"] == expected_value
    assert claim["unit_raw"] == expected_unit
    assert claim["raw"]["value_raw"] == parameter["value_raw"]
    assert claim["raw"]["unit_raw"] == parameter["unit_raw"]


def test_flatten_falls_back_atomically_to_raw_range_pair() -> None:
    document = {
        "items": [
            {
                "Item_ID": "item_1",
                "Sample_ID": "S1",
                "Role": "Target",
                "Data_Nature": "Experimental",
                "Extracted_Data": {
                    "Structure": {
                        "Structure_Observations": [
                            {
                                "sample_id": "S1",
                                "features": [
                                    {
                                        "feature_name_raw": "grain size",
                                        "value_kind": "range",
                                        "value_raw": "7–24",
                                        "value_min": 7,
                                        "value_max": 24,
                                        "unit_raw": "µm",
                                        "canonical_unit": "mm",
                                    }
                                ],
                            }
                        ]
                    }
                },
            }
        ]
    }

    claims = flatten_v11(document, source="final_v5", paper_key="paper")
    claim = next(row for row in claims if row["axis"] == "Structure")

    assert claim["value"]["min"] == 7.0
    assert claim["value"]["max"] == 24.0
    assert claim["value"]["raw"] == "7–24"
    assert claim["unit_raw"] == "µm"


def test_flatten_keeps_uncertainty_as_one_numeric_observation() -> None:
    document = {
        "items": [
            {
                "Item_ID": "item_1",
                "Sample_ID": "S1",
                "Role": "Target",
                "Data_Nature": "Experimental",
                "Extracted_Data": {
                    "Composition": {
                        "Composition_Observations": [
                            {
                                "sample_id": "S1",
                                "components": [
                                    {
                                        "canonical_name": "Ni",
                                        "value_kind": "scalar",
                                        "value_raw": "48.99 ± 0.37",
                                        "value_stddev": 0.37,
                                        "unit_raw": "at.%",
                                        "canonical_unit": "at%",
                                    }
                                ],
                            }
                        ]
                    }
                },
            }
        ]
    }

    claims = flatten_v11(document, source="final_v5", paper_key="paper")

    assert claims[0]["value"]["number"] == 48.99
    assert claims[0]["value"]["stddev"] == 0.37
    assert claims[0]["unit_raw"] == "at.%"


def test_flatten_selects_normalized_property_center_and_uncertainty_together() -> None:
    claims = flatten_v11(
        _v11_property_document(
            "0.39 ± 0.02",
            unit_raw="GPa",
            nested_value={
                "value_kind": "scalar",
                "value_raw": "0.39 ± 0.02",
                "value_num": 390.0,
                "value_stddev": 20.0,
                "unit_raw": "GPa",
                "canonical_unit": "MPa",
            },
        ),
        source="final_v5",
        paper_key="paper",
    )

    assert claims[0]["value"]["raw"] == "390 ± 20"
    assert claims[0]["value"]["number"] == 390.0
    assert claims[0]["value"]["stddev"] == 20.0
    assert claims[0]["unit_raw"] == "MPa"
    assert claims[0]["raw"]["Value"]["value_raw"] == "0.39 ± 0.02"
    assert claims[0]["raw"]["Value"]["unit_raw"] == "GPa"


def test_rounding_tolerance_uses_top_level_source_value_and_unit() -> None:
    document = {
        "items": [
            {
                "Item_ID": "item_1",
                "Sample_ID": "S1",
                "Role": "Target",
                "Data_Nature": "Experimental",
                "Extracted_Data": {
                    "Processing": {
                        "Process_Route": {
                            "stages": [
                                {
                                    "process_code": "B2.HT.AGING",
                                    "parameters": [
                                        {
                                            "parameter_code": "duration",
                                            "status": "reported",
                                            "value_kind": "scalar",
                                            "value_raw": "60",
                                            "unit_raw": "h",
                                            "canonical_value": 216000.0,
                                            "canonical_unit": "s",
                                        }
                                    ],
                                }
                            ]
                        }
                    }
                },
            }
        ]
    }
    claim = next(
        row
        for row in flatten_v11(document, source="final_v5", paper_key="paper")
        if row["axis"] == "Processing" and row["semantic_key"] == "duration"
    )

    assert _numeric_rounding_tolerance(claim) == 1800.0


def test_canonical_display_does_not_replace_source_literal_in_semantic_score() -> None:
    document = {
        "items": [
            {
                "Item_ID": "item_1",
                "Sample_ID": "S1",
                "Role": "Target",
                "Data_Nature": "Experimental",
                "Extracted_Data": {
                    "Processing": {
                        "Process_Route": {
                            "stages": [
                                {
                                    "process_code": "B2.HT.CURING",
                                    "parameters": [
                                        {
                                            "parameter_code": "process_temperature",
                                            "status": "reported",
                                            "value_kind": "scalar",
                                            "value_raw": "200",
                                            "unit_raw": "°C",
                                            "canonical_value": 473.15,
                                            "canonical_unit": "K",
                                        }
                                    ],
                                }
                            ]
                        }
                    }
                },
            }
        ]
    }
    system = next(
        row
        for row in flatten_v11(document, source="final_v5", paper_key="paper")
        if row["semantic_key"] == "process_temperature"
    )
    expert = {
        **_expert(sample="S1", condition=""),
        "axis": "Processing",
        "semantic_key": "curing_temperature",
        "name_raw": "curing temperature",
        "value": {**_expert()["value"], "raw": "200", "number": 200.0},
        "unit_raw": "°C",
    }
    expert["raw"] = {"value": expert["value"]}

    assert system["value"]["raw"] == "473.15"
    assert semantic_score(system, expert) >= 0.5
    assert value_score(system, expert) == 1.0


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


def _v11_property_document(
    value_raw: str,
    *,
    unit_raw: str | None = "MPa",
    nested_value: dict | None = None,
) -> dict:
    prop = {
        "Property_ID": "prop_001",
        "Property_Name_Raw": "ultimate tensile strength",
        "Value_Raw": value_raw,
        "Unit_Raw": unit_raw,
        "Test_Condition": {"original": "room temperature"},
        "Observation_Origin": "direct_experiment",
        "source_evidence": [f"UTS was {value_raw} {unit_raw or ''}".strip()],
    }
    if nested_value is not None:
        prop["Value"] = nested_value
    return {
        "items": [
            {
                "Item_ID": "item_1",
                "Sample_ID": "S1",
                "Role": "Target",
                "Data_Nature": "Experimental",
                "Extracted_Data": {
                    "Composition": {
                        "Material_Identity": {"material_name_raw": "Alloy X"}
                    },
                    "Processing": {"Process_Route": {"stages": []}},
                    "Structure": {
                        "Structure_Observations": [],
                        "Characterization": [],
                    },
                    "Properties": [prop],
                },
            }
        ]
    }


def test_flatten_property_origin_falls_back_to_reference_item_provenance() -> None:
    document = _v11_property_document("900")
    item = document["items"][0]
    item["Role"] = "Reference"
    item["Data_Nature"] = "Literature_Experimental"
    prop = item["Extracted_Data"]["Properties"][0]
    prop["Observation_Origin"] = "unknown"
    prop["Data_Nature"] = "Computed"

    claims = flatten_v11(document, source="final_v5", paper_key="paper")
    report = compare_claim_sets(claims, [])

    assert claims[0]["origin"] == "literature_computation"
    assert report["unique_modes"]["loose"]["core_tensile"]["system"] == 0


def test_flatten_property_origin_falls_back_to_target_item_provenance() -> None:
    document = _v11_property_document("900")
    prop = document["items"][0]["Extracted_Data"]["Properties"][0]
    prop["Observation_Origin"] = "unknown"
    prop.pop("Data_Nature", None)

    claims = flatten_v11(document, source="final_v5", paper_key="paper")
    report = compare_claim_sets(claims, [])

    assert claims[0]["origin"] == "author_experiment"
    assert report["unique_modes"]["loose"]["core_tensile"]["system"] == 1


@pytest.mark.parametrize(
    ("value_raw", "expected_kind", "expected"),
    [
        ("~1148", "scalar", {"number": 1148.0}),
        ("595 ± 14", "scalar", {"number": 595.0, "stddev": 14.0}),
        (r"2.18 \\times 10^{6}", "scalar", {"number": 2_180_000.0}),
        ("> 787", "inequality", {"operator": ">", "bound": 787.0}),
        ("12–14", "range", {"min": 12.0, "max": 14.0}),
    ],
)
def test_flatten_parses_unambiguous_v11_property_value_raw(
    value_raw: str, expected_kind: str, expected: dict
) -> None:
    claims = flatten_v11(
        _v11_property_document(value_raw),
        source="final_v5",
        paper_key="paper",
    )

    assert len(claims) == 1
    assert claims[0]["value"]["kind"] == expected_kind
    for key, value in expected.items():
        assert claims[0]["value"][key] == value


def test_flatten_does_not_compress_multi_value_property_prose() -> None:
    claims = flatten_v11(
        _v11_property_document("672%, 756%, and >787%", unit_raw="%"),
        source="final_v5",
        paper_key="paper",
    )

    assert claims[0]["value"]["kind"] == "unknown"
    assert claims[0]["value"]["number"] is None


def test_flatten_preserves_existing_structured_property_value() -> None:
    claims = flatten_v11(
        _v11_property_document(
            "approximately 1 GPa",
            nested_value={
                "value_kind": "scalar",
                "value_raw": "1.0",
                "value_num": 1.0,
                "unit_raw": "GPa",
            },
        ),
        source="business_gt",
        paper_key="paper",
    )

    assert claims[0]["value"]["kind"] == "scalar"
    assert claims[0]["value"]["raw"] == "1.0"
    assert claims[0]["value"]["number"] == 1.0
    assert claims[0]["unit_raw"] == "GPa"


def test_flatten_completes_declared_scalar_without_numeric_payload() -> None:
    claims = flatten_v11(
        _v11_property_document(
            "595 ± 14",
            nested_value={
                "value_kind": "scalar",
                "value_raw": "595 ± 14",
                "unit_raw": "MPa",
            },
        ),
        source="final_v5",
        paper_key="paper",
    )

    assert claims[0]["value"]["kind"] == "scalar"
    assert claims[0]["value"]["number"] == 595.0
    assert claims[0]["value"]["stddev"] == 14.0


def test_structure_entity_with_features_is_a_container_not_extra_presence_claim() -> None:
    document = {
        "items": [
            {
                "Item_ID": "item_1",
                "Sample_ID": "S1",
                "Role": "Target",
                "Data_Nature": "Experimental",
                "Extracted_Data": {
                    "Composition": {
                        "Material_Identity": {"material_name_raw": "Alloy X"}
                    },
                    "Processing": {"Process_Route": {"stages": []}},
                    "Structure": {
                        "Structure_Observations": [
                            {
                                "sample_id": "S1",
                                "material_state": "as-built",
                                "entities": [
                                    {
                                        "entity_id": "entity_001",
                                        "entity_type": "precipitate",
                                        "name_raw": "gamma prime precipitates",
                                        "canonical_name": "gamma_prime",
                                        "features": [
                                            {
                                                "feature_name_raw": "size",
                                                "value_kind": "scalar",
                                                "value_raw": "25",
                                                "value": 25.0,
                                                "unit_raw": "nm",
                                                "source_evidence": [
                                                    "gamma prime precipitates were 25 nm"
                                                ],
                                            }
                                        ],
                                        "source_evidence": [
                                            "gamma prime precipitates were 25 nm"
                                        ],
                                    }
                                ],
                                "features": [],
                                "source_evidence": [
                                    "gamma prime precipitates were 25 nm"
                                ],
                            }
                        ],
                        "Characterization": [],
                    },
                    "Properties": [],
                },
            }
        ]
    }

    claims = flatten_v11(document, source="final_v5", paper_key="paper")

    assert len(claims) == 1
    assert claims[0]["axis"] == "Structure"
    assert claims[0]["semantic_key"] == "size"


def test_structure_entity_without_features_remains_a_presence_claim() -> None:
    document = {
        "items": [
            {
                "Item_ID": "item_1",
                "Sample_ID": "S1",
                "Role": "Target",
                "Data_Nature": "Experimental",
                "Extracted_Data": {
                    "Composition": {
                        "Material_Identity": {"material_name_raw": "Alloy X"}
                    },
                    "Processing": {"Process_Route": {"stages": []}},
                    "Structure": {
                        "Structure_Observations": [
                            {
                                "sample_id": "S1",
                                "material_state": "as-built",
                                "entities": [
                                    {
                                        "entity_id": "entity_001",
                                        "entity_type": "phase",
                                        "name_raw": "B2 phase",
                                        "canonical_name": "b2_phase",
                                        "features": [],
                                        "source_evidence": ["B2 phase was detected"],
                                    }
                                ],
                                "features": [],
                                "source_evidence": ["B2 phase was detected"],
                            }
                        ],
                        "Characterization": [],
                    },
                    "Properties": [],
                },
            }
        ]
    }

    claims = flatten_v11(document, source="final_v5", paper_key="paper")

    assert len(claims) == 1
    assert claims[0]["semantic_key"] == "b2_phase_presence"
