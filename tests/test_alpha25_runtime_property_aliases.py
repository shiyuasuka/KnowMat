from types import SimpleNamespace

import pytest

from knowmat.alpha25.runner_compat import (
    install_process_unit_compat,
    install_structure_unit_compat,
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
