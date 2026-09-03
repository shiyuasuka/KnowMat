"""Resolve and validate the checked-in material-extractor alpha25 package."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any


ALPHA25_SKILL_VERSION = "11.0.0-alpha.25"
ALPHA25_SCHEMA_VERSION = "material_extraction_v11.3.3"
DEFAULT_PACKAGE_ROOT = "material-extractor-alpha25-20260804/material-extractor"
EXPECTED_SYSTEM_PROMPT_SHA256 = (
    "5aa5f38b1a51ccd895abecee3c511b5c1172735af5cab72455cbdf591027107d"
)
EXPECTED_USER_PROMPT_SHA256 = (
    "24629932a3c8119eaa285ebd372dc20fa9712aa96ca4a913e6a9415b8f3eb6ab"
)

_REQUIRED_REFERENCES = (
    "references/03-extract-system-prompt.md",
    "references/03-extract-user-prompt.md",
    "references/deployment_metadata.json",
    "references/rules/ruleset_manifest.json",
    "references/schema/material_extraction_v11.schema.json",
)


def _project_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _read_object(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise FileNotFoundError(f"Missing alpha25 package artifact: {path}") from None
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid alpha25 JSON artifact {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise ValueError(f"Expected alpha25 JSON object: {path}")
    return value


def _resolve_root(package_root: str | Path | None) -> Path:
    raw = Path(package_root or DEFAULT_PACKAGE_ROOT).expanduser()
    root = raw if raw.is_absolute() else _project_root() / raw
    root = root.resolve()
    if (root / "material-extractor").is_dir():
        root = (root / "material-extractor").resolve()
    return root


@dataclass(frozen=True)
class Alpha25Package:
    """Validated immutable view of the alpha25 runtime package."""

    root: Path
    deployment: dict[str, Any]
    ruleset_manifest: dict[str, Any]
    schema: dict[str, Any]
    system_prompt_sha256: str
    user_prompt_sha256: str

    @property
    def skill_version(self) -> str:
        return str(self.deployment["skill_version"])

    @property
    def schema_version(self) -> str:
        return str(self.schema["$id"])

    @property
    def ruleset_digest(self) -> str:
        return str(self.ruleset_manifest["ruleset_digest"])

    def reference_path(self, relative_path: str) -> Path:
        relative = Path(relative_path)
        if relative.is_absolute() or ".." in relative.parts:
            raise ValueError(f"Unsafe alpha25 reference path: {relative_path!r}")
        path = (self.root / "references" / relative).resolve()
        try:
            path.relative_to((self.root / "references").resolve())
        except ValueError:
            raise ValueError(f"Unsafe alpha25 reference path: {relative_path!r}") from None
        if not path.is_file():
            raise FileNotFoundError(f"Missing alpha25 reference: {path}")
        return path

    def read_reference(self, relative_path: str) -> str:
        return self.reference_path(relative_path).read_text(encoding="utf-8")


def _validate_package(root: Path) -> Alpha25Package:
    if not root.is_dir():
        raise FileNotFoundError(f"Missing alpha25 package root: {root}")
    for relative in _REQUIRED_REFERENCES:
        path = root / relative
        if not path.is_file():
            raise FileNotFoundError(f"Missing alpha25 package artifact: {path}")

    deployment = _read_object(root / "references/deployment_metadata.json")
    manifest = _read_object(root / "references/rules/ruleset_manifest.json")
    schema = _read_object(root / "references/schema/material_extraction_v11.schema.json")

    if deployment.get("skill_version") != ALPHA25_SKILL_VERSION:
        raise ValueError(
            "Unsupported material-extractor package version: "
            f"{deployment.get('skill_version')!r}; expected {ALPHA25_SKILL_VERSION!r}"
        )
    if schema.get("$id") != ALPHA25_SCHEMA_VERSION:
        raise ValueError(
            f"Unsupported alpha25 schema {schema.get('$id')!r}; "
            f"expected {ALPHA25_SCHEMA_VERSION!r}"
        )
    if manifest.get("compatible_schema") != ALPHA25_SCHEMA_VERSION:
        raise ValueError("Alpha25 ruleset manifest is incompatible with the schema")
    if deployment.get("ruleset_digest") != manifest.get("ruleset_digest"):
        raise ValueError("Alpha25 deployment and ruleset digests do not match")

    for entry in manifest.get("files", []):
        if not isinstance(entry, dict):
            raise ValueError("Alpha25 ruleset manifest contains a non-object entry")
        relative = entry.get("path")
        expected = entry.get("sha256")
        if not isinstance(relative, str) or not isinstance(expected, str):
            raise ValueError("Alpha25 ruleset manifest entry is missing path/sha256")
        rule_path = (root / relative).resolve()
        try:
            rule_path.relative_to(root)
        except ValueError:
            raise ValueError(f"Unsafe alpha25 ruleset path: {relative!r}") from None
        if not rule_path.is_file():
            raise FileNotFoundError(f"Missing alpha25 rule file: {rule_path}")
        actual = _sha256_file(rule_path)
        if actual != expected:
            raise ValueError(
                f"Alpha25 rule hash mismatch for {relative}: {actual} != {expected}"
            )

    system_path = root / "references/03-extract-system-prompt.md"
    user_path = root / "references/03-extract-user-prompt.md"
    return Alpha25Package(
        root=root,
        deployment=deployment,
        ruleset_manifest=manifest,
        schema=schema,
        system_prompt_sha256=_sha256_file(system_path),
        user_prompt_sha256=_sha256_file(user_path),
    )


@lru_cache(maxsize=8)
def _load_cached(root_string: str) -> Alpha25Package:
    return _validate_package(Path(root_string))


def load_alpha25_package(package_root: str | Path | None = None) -> Alpha25Package:
    """Return a validated alpha25 package, cached by its resolved root."""

    root = _resolve_root(package_root)
    return _load_cached(str(root))
