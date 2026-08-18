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
    if getattr(original_parameter, "_knowmat_tex_unit_compat", False):
        return

    def compatible_parameter(
        raw: dict[str, Any], stage_uid: str, profile: str, rules: Any
    ) -> tuple[Any, ...]:
        record, issues, audit = original_parameter(raw, stage_uid, profile, rules)
        if not isinstance(record, dict):
            return record, issues, audit
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
        if re.fullmatch(r"[-+]?\d+(?:\.\d+)?(?:[eE][-+]?\d+)?", value_text):
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
