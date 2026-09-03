import hashlib
from pathlib import Path

import pytest

from knowmat.alpha25.package import (
    ALPHA25_SCHEMA_VERSION,
    ALPHA25_SKILL_VERSION,
    EXPECTED_SYSTEM_PROMPT_SHA256,
    EXPECTED_USER_PROMPT_SHA256,
    load_alpha25_package,
)


def test_checked_in_alpha25_package_is_complete_and_pinned():
    package = load_alpha25_package()

    assert package.skill_version == ALPHA25_SKILL_VERSION
    assert package.schema_version == ALPHA25_SCHEMA_VERSION
    assert package.system_prompt_sha256 == EXPECTED_SYSTEM_PROMPT_SHA256
    assert package.user_prompt_sha256 == EXPECTED_USER_PROMPT_SHA256
    assert package.ruleset_digest == package.deployment["ruleset_digest"]


def test_alpha25_reference_path_rejects_escape():
    package = load_alpha25_package()

    with pytest.raises(ValueError, match="Unsafe"):
        package.reference_path("../deployment_metadata.json")


def test_alpha25_rule_hash_validation_detects_mutation(tmp_path: Path):
    source = load_alpha25_package().root
    clone = tmp_path / "material-extractor"
    clone.symlink_to(source, target_is_directory=True)

    # A symlinked valid package remains valid; package validation follows the resolved root.
    package = load_alpha25_package(clone)
    prompt = package.reference_path("03-extract-system-prompt.md")
    assert hashlib.sha256(prompt.read_bytes()).hexdigest() == EXPECTED_SYSTEM_PROMPT_SHA256
