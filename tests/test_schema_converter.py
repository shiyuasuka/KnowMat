import math

from knowmat.schema_converter import SchemaConverter


converter = SchemaConverter()


def test_parse_temperature_to_k_from_at_k():
    assert converter.parse_temperature_to_k("measured at 298 K in air") == 298
    assert converter.parse_temperature_to_k("AT 873 K; compression") == 873


def test_parse_temperature_to_k_from_celsius():
    # 25 °C ≈ 298.15 K
    assert converter.parse_temperature_to_k("tested at 25 °C") == 298
    # plain 'c' should still be treated as Celsius when clearly temperature
    assert converter.parse_temperature_to_k("at 100 c in vacuum") == 373


def test_parse_temperature_to_k_from_k_without_at():
    assert converter.parse_temperature_to_k("873K tensile test") == 873


def test_parse_temperature_to_k_returns_none_when_no_temperature():
    assert converter.parse_temperature_to_k("room temperature test") is None


def test_validate_composition_json_keeps_non_100_sum_as_is():
    comp = {"Ti": 30.0, "Nb": 30.0, "Zr": 30.0}
    cleaned, warnings = converter.validate_composition_json(comp, "Ti30Nb30Zr30")
    assert warnings == []
    assert cleaned == comp


def test_build_composition_json_defaults_missing_amounts_to_one():
    comp = converter.build_composition_json("FeCoCrNiMo0.5")
    assert comp["Fe"] == 1.0
    assert comp["Co"] == 1.0
    assert comp["Cr"] == 1.0
    assert comp["Ni"] == 1.0
    assert math.isclose(comp["Mo"], 0.5)


def test_build_composition_json_parses_hyphen_separated_amounts():
    comp = converter.build_composition_json(
        "Ni-21.49Cr-13.13W-2.22Mo-1.57Fe-1.30Co-0.46Al-0.34Mn-0.30Si-0.029La-0.48C"
    )
    assert math.isclose(comp["Ni"], 21.49, rel_tol=1e-6)
    assert math.isclose(comp["Cr"], 13.13, rel_tol=1e-6)
    assert math.isclose(comp["W"], 2.22, rel_tol=1e-6)
    assert math.isclose(comp["Mo"], 1.57, rel_tol=1e-6)
    assert math.isclose(comp["Fe"], 1.30, rel_tol=1e-6)
    assert math.isclose(comp["Co"], 0.46, rel_tol=1e-6)
    assert math.isclose(comp["Al"], 0.34, rel_tol=1e-6)
    assert math.isclose(comp["Mn"], 0.30, rel_tol=1e-6)
    assert math.isclose(comp["Si"], 0.029, rel_tol=1e-6)
    assert math.isclose(comp["La"], 0.48, rel_tol=1e-6)
    assert "C" not in comp


def test_validate_composition_json_drops_invalid_element():
    comp = {"Ti": 50.0, "Xx": 50.0}
    cleaned, warnings = converter.validate_composition_json(comp, "Ti50Xx50")
    assert "Xx" not in cleaned
    assert any("Invalid element" in w for w in warnings)

