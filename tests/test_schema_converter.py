import math

from knowmat import schema_converter as schema_converter_module
from knowmat.schema_converter import SchemaConverter


converter = SchemaConverter()


def test_parse_temperature_to_k_from_at_k():
    assert converter.parse_temperature_to_k("measured at 298 K in air") == 298
    assert converter.parse_temperature_to_k("AT 873 K; compression") == 873


def test_parse_temperature_to_k_from_celsius():
    assert converter.parse_temperature_to_k("tested at 25 C") == 298.15
    assert converter.parse_temperature_to_k("at 100 c in vacuum") == 373.15


def test_parse_temperature_to_k_from_k_without_at():
    assert converter.parse_temperature_to_k("873K tensile test") == 873


def test_parse_temperature_to_k_for_room_temperature_alias():
    assert converter.parse_temperature_to_k("room temperature test") == 298.15


def test_parse_temperature_to_k_returns_none_when_no_temperature():
    assert converter.parse_temperature_to_k("tensile test under argon") is None


def test_validate_composition_json_warns_on_sum_far_from_100():
    comp = {"Ti": 30.0, "Nb": 30.0, "Zr": 30.0}
    cleaned, warnings = converter.validate_composition_json(comp, "Ti30Nb30Zr30")
    assert any("Normalised to 100 at%" in w for w in warnings)
    assert abs(sum(cleaned.values()) - 100.0) < 1e-6


def test_build_composition_json_defaults_missing_amounts_to_one():
    comp = converter.build_composition_json("FeCoCrNiMo0.5")
    assert set(comp.keys()) == {"Fe", "Co", "Cr", "Ni", "Mo"}
    if schema_converter_module._PymatgenComposition is not None:
        assert math.isclose(sum(comp.values()), 100.0, rel_tol=1e-6, abs_tol=1e-6)
        assert math.isclose(comp["Fe"], comp["Co"], rel_tol=1e-6)
        assert math.isclose(comp["Cr"], comp["Ni"], rel_tol=1e-6)
        assert comp["Mo"] < comp["Fe"]
    else:
        assert comp["Fe"] == 1.0
        assert comp["Co"] == 1.0
        assert comp["Cr"] == 1.0
        assert comp["Ni"] == 1.0
        assert math.isclose(comp["Mo"], 0.5)


def test_build_composition_json_handles_balance_notation_without_barium_leak():
    comp = converter.build_composition_json(
        "NiBalCr21.49W13.13Mo2.22Fe1.57Co1.30Al0.46Mn0.34Si0.30La0.029C0.48"
    )
    assert "Ba" not in comp
    assert "Ni" in comp
    if schema_converter_module._PymatgenComposition is not None:
        assert math.isclose(sum(comp.values()), 100.0, rel_tol=1e-6, abs_tol=1e-6)
        assert comp["Ni"] > 50.0


def test_build_composition_json_handles_ti_v_amount_tokens_without_crashing():
    comp = converter.build_composition_json("Ti4V10")
    assert "Ti" in comp
    assert "V" in comp
    if schema_converter_module._PymatgenComposition is not None:
        assert math.isclose(sum(comp.values()), 100.0, rel_tol=1e-6, abs_tol=1e-6)


def test_recover_formula_from_paper_text_prefers_explicit_balance_line():
    paper_text = (
        "The powder's elemental composition is 21.49 Cr - 13.13 W - 2.22 Mo - "
        "1.57 Fe - 1.30 Co - 0.46 Al - 0.34 Mn - 0.30 Si - 0.029 La - 0.48 C - Bal Ni "
        "(weight percent, wt.%)."
    )
    recovered = converter._recover_formula_from_paper_text(
        paper_text=paper_text,
        comp_raw="SD3230 [As-Built, Horizontal BD]",
        fallback_formula="Ni21.18Cr13.27W2.84Mo0.92Fe1.12Co0.88Al0.68Mn0.25Si0.43C1.59La0.008",
        target_count=1,
    )
    assert recovered is not None
    assert recovered.startswith("Ni58.681")
    comp = converter.build_composition_json(recovered)
    if schema_converter_module._PymatgenComposition is not None:
        assert math.isclose(comp["Ni"], 58.681, rel_tol=1e-4, abs_tol=1e-4)
        assert math.isclose(comp["Cr"], 21.49, rel_tol=1e-4, abs_tol=1e-4)
        assert math.isclose(sum(comp.values()), 100.0, rel_tol=1e-6, abs_tol=1e-6)


def test_validate_composition_json_drops_invalid_element():
    comp = {"Ti": 50.0, "Xx": 50.0}
    cleaned, warnings = converter.validate_composition_json(comp, "Ti50Xx50")
    assert "Xx" not in cleaned
    assert any("Invalid element" in w for w in warnings)


def test_parse_key_params_tolerates_noisy_numeric_tokens():
    params = converter.parse_key_params("laser power=10V2 W; scan speed=900 mm/s")
    assert "Scanning_Speed_mm_s" in params


def test_convert_bootstraps_datasheet_compositions_when_llm_returns_none():
    data = {"compositions": []}
    paper_text = (
        "Common Name: Iodide Ti\n"
        "Specifications and Compositions.\n"
        "| Specification designation | Form(s) | C | H | N | O | Cu | Fe | Mn | Sn | Si | Zr | Cl | Mg | Tibal |\n"
        "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |\n"
        "| Typical %, electrolytic T1 | ... | 0.008 | ... | 0.004 | 0.037 | 0.007 | 0.009 | <0.001 | <0.020 | 0.002 | <0.001 | 0.073 | <0.001 | 99.837 |\n"
    )
    out = converter.convert(data, "High-Purity Ti.md", paper_text=paper_text)
    assert len(out["items"]) >= 1
    comp = out["items"][0]["Composition_Info"]["Nominal_Composition"]["Elements_Normalized"]
    assert "Ti" in comp


def test_convert_expands_step_keyed_runtime_composition_maps():
    data = {
        "compositions": [
            {
                "composition": "Multigraded Ti6Al4V-IN718 specimen",
                "alloy_name_raw": "Multigraded Ti6Al4V-IN718 specimen",
                "nominal_composition": {
                    "0": {"Ti": 88.93, "Al": 6.4, "V": 4.1, "Fe": 0.18, "other": 0.39},
                    "5": {
                        "Ti": 86.7,
                        "Al": 5.52,
                        "V": 3.68,
                        "Ni": 2.5,
                        "Cr": 0.98,
                        "Fe": 0.87,
                        "Nb": 0.24,
                        "Mo": 0.14,
                    },
                    "20 wt%": {
                        "Ti": 74.36,
                        "Al": 3.85,
                        "V": 2.91,
                        "Ni": 10.0,
                        "Cr": 3.92,
                        "Fe": 3.5,
                        "Nb": 0.95,
                        "Mo": 0.53,
                    },
                },
                "nominal_composition_type": "wt%",
                "processing_conditions": (
                    "original: Multi-material SLM graded transition from Ti6Al4V to IN718: "
                    "42 layers at 0% IN718, then 12 layers each at 5%, 10%, 15%, 20% IN718. "
                    "|| simplified: graded Ti6Al4V/IN718 transition"
                ),
                "process_category": "AM_LPBF + Graded_Composition",
                "properties_of_composition": [
                    {
                        "property_name": "hardness",
                        "value": "400-700",
                        "value_numeric": 550.0,
                        "value_type": "range",
                        "unit": "HV",
                    }
                ],
                "characterisation": {},
            }
        ]
    }
    out = converter.convert(data, "graded.md")
    names = [item["Composition_Info"]["Alloy_Name_Raw"] for item in out["items"]]
    assert names == [
        "Graded Ti6Al4V/IN718 - Ti6Al4V base layer (0 wt% IN718)",
        "Graded Ti6Al4V/IN718 - 5 wt% IN718 step",
        "Graded Ti6Al4V/IN718 - 20 wt% IN718 step",
    ]
    assert all(item["Properties_Info"] == [] for item in out["items"])
    assert all(item["Gradient_Material"] is True for item in out["items"])
    assert len({item["Gradient_Group_ID"] for item in out["items"]}) == 1


def test_convert_keeps_gradient_specimen_whole_without_explicit_layer_data():
    data = {
        "compositions": [
            {
                "composition": "Multigraded Ti6Al4V-IN718 specimen",
                "alloy_name_raw": "Multigraded Ti6Al4V-IN718 specimen",
                "gradient_material": True,
                "nominal_composition": {"Ti": 90.0, "Al": 6.0, "V": 4.0},
                "nominal_composition_type": "wt%",
                "processing_conditions": (
                    "original: Multi-material SLM graded transition from Ti6Al4V to IN718 with "
                    "42 layers of Ti6Al4V and 12 layers each at 5, 10, 15, and 20 wt% IN718. "
                    "|| simplified: graded Ti6Al4V/IN718 specimen"
                ),
                "process_category": "AM_LPBF + Graded_Composition",
                "properties_of_composition": [],
                "characterisation": {},
            }
        ]
    }

    out = converter.convert(data, "graded_whole.md")

    assert len(out["items"]) == 1
    item = out["items"][0]
    assert item["Gradient_Material"] is True
    assert item["Gradient_Group_ID"] is None
    assert item["Composition_Info"]["Alloy_Name_Raw"] == "Multigraded Ti6Al4V-IN718 specimen"


def test_convert_preserves_v5_runtime_fields_and_enforces_main_phase_rules():
    data = {
        "compositions": [
            {
                "composition": "IN718",
                "sample_id": "SAMPLE-01",
                "alloy_name_raw": "IN718",
                "role": "Target",
                "nominal_composition": {"Ni": 53.0, "Cr": 19.0, "Fe": 18.0, "Nb": 5.0, "Mo": 3.0, "other": 2.0},
                "nominal_composition_type": "wt%",
                "composition_note": "C <= 0.08 wt%; S <= 0.015 wt%",
                "main_phase": "Laves",
                "precipitates": [
                    {"phase_type": "Laves", "volume_fraction_pct": 3.2},
                    {"phase_type": "MC Carbide", "volume_fraction_pct": None},
                ],
                "porosity_pct": 0.3,
                "relative_density_pct": 99.2,
                "grain_size_avg_um": 18.5,
                "precipitate_size_avg_nm": 120.0,
                "precipitate_volume_fraction_pct": 3.2,
                "processing_conditions": (
                    "original: LPBF build followed by aging. || simplified: LPBF + aging"
                ),
                "processing_params": {"Solution_Temperature_K": "1273-1373"},
                "equipment": "EOS M290",
                "process_category": "AM_LPBF",
                "microstructure_description": (
                    "original: FCC matrix with Laves and MC carbide precipitates. "
                    "|| simplified: FCC matrix plus Laves and carbides"
                ),
                "characterisation": {"Microstructure": "FCC matrix with Laves and MC carbides"},
                "properties_of_composition": [
                    {
                        "property_name": "elongation",
                        "value": "18",
                        "value_numeric": 18.0,
                        "value_type": "exact",
                        "unit": "%",
                        "measurement_condition": "at 298.15 K; strain rate 1e-3 s^-1",
                        "data_source": "text",
                    },
                    {
                        "property_name": "hardness",
                        "value": "410",
                        "value_numeric": 410.0,
                        "value_type": "exact",
                        "unit": "HV",
                        "measurement_condition": "at 298.15 K",
                        "hardness_load": "200 gf",
                        "hardness_dwell_time_s": 15.0,
                        "test_specimen": "ASTM E8, gauge length 25 mm",
                        "data_source": "text",
                    },
                ],
            }
        ]
    }

    out = converter.convert(data, "runtime_v5.md")
    item = out["items"][0]

    assert item["Sample_ID"] == "SAMPLE-01"
    assert item["Composition_Info"]["Note"] == "C <= 0.08 wt%; S <= 0.015 wt%"
    assert item["Process_Info"]["Equipment"] == "EOS M290"
    assert item["Microstructure_Info"]["Main_Phase"] == "FCC"
    assert item["Microstructure_Info"]["Precipitates"] == [
        {"Phase_Type": "Laves", "Volume_Fraction_pct": 3.2},
        {"Phase_Type": "MC Carbide", "Volume_Fraction_pct": None},
    ]

    elongation = next(prop for prop in item["Properties_Info"] if prop["Property_Name"] == "Elongation_Total")
    hardness = next(prop for prop in item["Properties_Info"] if prop["Property_Name"] == "Hardness_HV")

    assert elongation["Strain_Rate_s1"] == "1e-3 s^-1"
    assert elongation["Data_Source"] == "text"
    assert elongation["Note"] == "Original only provides total elongation."
    assert hardness["Hardness_Load"] == "200 gf"
    assert hardness["Hardness_Dwell_Time_s"] == 15.0
    assert hardness["Test_Specimen"] == "ASTM E8, gauge length 25 mm"


def test_parse_key_params_preserves_heat_treatment_ranges():
    params = converter.parse_key_params(
        "solution treatment at 1000-1100 C for 2-4 h, followed by aging at 700-750 C for 8-10 h"
    )

    assert params["Solution_Temperature_K"] == "1273-1373"
    assert params["Solution_Time_h"] == "2-4"
    assert params["Aging_Temperature_K"] == "973-1023"
    assert params["Aging_Time_h"] == "8-10"


def test_extract_tensile_speed_mm_min_converts_mm_per_s():
    value = converter._extract_tensile_speed_mm_min(
        "These tests were performed under displacement control with a rate of 0.006 mm/s."
    )
    assert math.isclose(value, 0.36, rel_tol=1e-9, abs_tol=1e-9)


def test_convert_repairs_abbreviated_sample_matrix_from_paper_text():
    data = {
        "items": [
            {
                "Sample_ID": "S3090",
                "Gradient_Material": False,
                "Gradient_Group_ID": None,
                "Composition_Info": {
                    "Role": "Target",
                    "Alloy_Name_Raw": "Ti-6Al-4V ELI",
                    "Nominal_Composition": {
                        "Composition_Type": "wt%",
                        "Elements_Normalized": {"Ti": 90.0, "Al": 6.0, "V": 4.0},
                    },
                    "Measured_Composition": {
                        "Composition_Type": None,
                        "Elements_Normalized": None,
                        "Measurement_Method": None,
                    },
                    "Note": "ELI grade Ti64 powder",
                },
                "Process_Info": {
                    "Process_Category": "AM_SLM",
                    "Process_Text": {
                        "original": "Selective laser melting in argon; post-SLM stress relief annealing at 650 C for 3 h.",
                        "simplified": "SLM + stress relief",
                    },
                    "Equipment": "EOSINT M 280 (Yb:YAG fiber laser)",
                    "Key_Params": {
                        "Laser_Power_W": 280,
                        "Scanning_Speed_mm_s": 1200,
                        "Hatch_Spacing_um": 140,
                        "Layer_Thickness_um": 30,
                        "Scan_Rotation_deg": 90,
                        "Volumetric_Energy_Density_J_mm3": 55.6,
                    },
                },
                "Microstructure_Info": {
                    "Microstructure_Text": {
                        "original": "Fine acicular alpha/alpha prime laths within prior beta grains.",
                        "simplified": "Acicular alpha/alpha prime laths",
                    },
                    "Main_Phase": "alpha/alpha prime lath structure",
                    "Precipitates": [],
                    "Porosity_pct": 0.37,
                    "Relative_Density_pct": None,
                    "Grain_Size_avg_um": 140.0,
                    "Precipitate_Size_avg_nm": None,
                    "Precipitate_Volume_Fraction_pct": None,
                    "Phase_Fraction_pct": None,
                    "Advanced_Quantitative_Features": {},
                },
                "Properties_Info": [
                    {
                        "Property_Name": "Yield_Strength",
                        "Test_Condition": "at 298.15 K; strain rate 0.001 s^-1; displacement control 0.006 mm/s",
                        "Value_Numeric": 1029.0,
                        "Value_Range": None,
                        "Value_StdDev": 8.0,
                        "Unit": "MPa",
                        "Test_Temperature_K": 298.15,
                    }
                ],
            }
        ]
    }
    paper_text = """
Different combinations of SLM process parameters utilized for manufacturing the Ti-6Al-4V alloy coupons that were examined in this study.
| Nomenclature | Laser Power (w) | Scan Speed (v) (mm/s) | Scan spacing(l) (mm) | Layer Thickness(t) ( $ \\mu $m) | Scan rotation ( $ ^{\\circ} $) | Energy Density (J) (J/mm $ ^{3} $) |
| --- | --- | --- | --- | --- | --- | --- |
| 3090 | 280 | 1200 | 0.14 | 30 | 90 | 55.6 |
| 3067 | 280 | 1200 | 0.14 | 30 | 67 | 55.6 |
| 6090 | 340 | 1250 | 0.12 | 60 | 90 | 37.8 |
| 6067 | 340 | 1250 | 0.12 | 60 | 67 | 37.8 |

Summary of the mechanical properties of SLM Ti64 examined in this study.
| Sample | $ \\sigma_{Y} $ (MPa) | $ \\sigma_{U} $ (MPa) | $ e_{f} $ (%) | $ K_{Ic} $ (MPa  $ \\sqrt{m} $) | $ \\Delta K_{0} $ (MPa  $ \\sqrt{m} $) | m | FS (MPa) | FS/ $ \\sigma_{U} $ |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| B3090 | 1161  $ \\pm $ 30 | 1237  $ \\pm $ 30 | 7.6  $ \\pm $ 1 | 52 | 5.6 | 2.53 | 340 | 0.28 |
| S3090 | 1029  $ \\pm $ 8 | 1091  $ \\pm $ 6 | 7.8  $ \\pm $ 0.8 | 55 | 5.7 | 3.31 |  |  |
| B3067 | 1121  $ \\pm $ 42 | 1186  $ \\pm $ 42 | 8.1  $ \\pm $ 0.6 | 48 | 5.3 | 3.55 | 340 | 0.29 |
| S3067 | 1121  $ \\pm $ 9 | 1202  $ \\pm $ 11 | 10.1  $ \\pm $ 0.3 | 54 | 5.7 | 3.08 |  |  |
| B6090 | 1151  $ \\pm $ 11 | 1222  $ \\pm $ 25 | 9.8  $ \\pm $ 1.1 | 51 | 5.8 | 2.87 | 453 | 0.37 |
| S6090 | 1115  $ \\pm $ 18 | 1183  $ \\pm $ 22 | 9.7  $ \\pm $ 0.3 | 52 | 5.8 | 2.89 |  |  |
| B6067 | 1102  $ \\pm $ 16 | 1145  $ \\pm $ 14 | 12.5  $ \\pm $ 1.4 | 58 | 5.4 | 3.51 | 475 | 0.41 |
| S6067 | 1063  $ \\pm $ 17 | 1137  $ \\pm $ 23 | 12.8  $ \\pm $ 0.9 | 58 | 5.7 | 3.48 |  |  |

These tests were performed under displacement control with a rate of 0.006 mm/s, which corresponds to a nominal strain rate of 0.001 s^-1.
For the FCG measurements, the tensile load was applied on the sample in sinusoidal wave form at a frequency of 10 Hz at constant R (0.1).
For the fracture toughness measurements, the specimens were precracked such that the a/W ratio is ~0.45-0.55, before being fractured at a displacement rate of 0.01 mm/s.
The calculated apparent densities, rho, of 3090, 3067, 6090, 6067 samples are 99.76 ± 0.16%, 99.83 ± 0.08%, 99.83 ± 0.07% and 99.77 ± 0.15%, respectively. The corresponding porosities, measured using X-ray tomography, are 0.37%, 0.39%, 0.29%, and 0.17% respectively.
The lath thickness' are too small (up to 2 um) than these estimated rp. On the other hand, the average colony sizes of ~10-15 um are in the similar range of interaction.
"""

    out = converter.convert(data, "kumar_like.md", paper_text=paper_text)

    assert len(out["items"]) == 8
    sample_ids = [item["Sample_ID"] for item in out["items"]]
    assert sample_ids == ["B3090", "S3090", "B3067", "S3067", "B6090", "S6090", "B6067", "S6067"]

    b3090 = next(item for item in out["items"] if item["Sample_ID"] == "B3090")
    assert b3090["Process_Info"]["Process_Category"] == "Selective Laser Melting (SLM)"
    assert b3090["Process_Info"]["Key_Params"]["Annealing_Temperature_K"] == 923.15
    assert b3090["Microstructure_Info"]["Relative_Density_pct"] == 99.76
    assert b3090["Microstructure_Info"]["Porosity_pct"] == 0.37
    assert b3090["Microstructure_Info"]["Advanced_Quantitative_Features"]["Colony_Size_avg_um"] == "10-15"
    assert b3090["Microstructure_Info"]["Advanced_Quantitative_Features"]["Lath_Thickness_max_um"] == 2.0

    ys = next(prop for prop in b3090["Properties_Info"] if prop["Property_Name"] == "Yield_Strength")
    kic = next(prop for prop in b3090["Properties_Info"] if prop["Property_Name"] == "Fracture_Toughness_KIC")
    fs = next(prop for prop in b3090["Properties_Info"] if prop["Property_Name"] == "Fatigue_Strength_Unnotched")
    assert ys["Tensile_Speed_mm_min"] == 0.36
    assert kic["Unit"] == "MPa√m"
    assert fs["Value_Numeric"] == 340.0

    s3090 = next(item for item in out["items"] if item["Sample_ID"] == "S3090")
    assert not any(prop["Property_Name"] == "Fatigue_Strength_Unnotched" for prop in s3090["Properties_Info"])
