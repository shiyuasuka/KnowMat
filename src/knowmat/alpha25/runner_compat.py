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


def main(argv: Sequence[str] | None = None) -> int:
    """Load the frozen runner, install the narrow adapter, and delegate."""

    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--package-root", required=True, type=Path)
    args, runner_argv = parser.parse_known_args(argv)
    package_root = args.package_root.resolve()
    sys.path.insert(0, str(package_root))

    from scripts import normalize_tensile  # type: ignore[import-not-found]

    install_property_alias_compat(normalize_tensile)
    from scripts.run_v11 import main as runner_main  # type: ignore[import-not-found]

    return int(runner_main(runner_argv))


if __name__ == "__main__":
    raise SystemExit(main())
