from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

from scripts import run_frozen_alpha25_extraction as runner


REPO_ROOT = Path(__file__).resolve().parents[1]


def _args(**overrides):
    values = {
        "verifier_field_level": False,
        "verifier_model": "primary-role",
        "verifier_fallback_model": "review-role",
        "verifier_api_mode": "chat_completions",
        "verifier_fallback_api_mode": None,
        "verifier_thinking": "provider_default",
        "verifier_fallback_thinking": None,
        "verifier_reasoning_effort": "provider_default",
        "verifier_fallback_reasoning_effort": "low",
        "verifier_response_format": "json_object",
        "verifier_timeout": 180,
        "verifier_confirmation_timeout": None,
        "verifier_confirmation_max_tokens": 1536,
        "verifier_max_tokens": 4096,
        "verifier_fallback_max_tokens": 6144,
        "verifier_workers": None,
        "verifier_transient_retries": 0,
        "verifier_singleton_truncation_retries": 1,
        "verifier_compact_max_tokens": 1024,
        "verifier_compact_split_limit": 1,
        "verifier_bundle_assertions": 6,
        "verifier_bundle_chars": 6000,
        "verifier_bypass_axes": "composition,properties",
        "verifier_risk_routing": False,
        "no_verifier_recovery": False,
        "no_verifier_destructive_consensus": False,
    }
    values.update(overrides)
    return argparse.Namespace(**values)


def test_runner_help_exposes_field_level_switch():
    completed = subprocess.run(
        [
            sys.executable,
            str(REPO_ROOT / "scripts/run_frozen_alpha25_extraction.py"),
            "--help",
        ],
        cwd=REPO_ROOT,
        check=True,
        capture_output=True,
        text=True,
    )

    assert "--verifier-field-level" in completed.stdout
    assert "--verifier-reasoning-effort" in completed.stdout


def test_runner_field_level_configuration_has_no_model_or_paper_branch():
    text = (REPO_ROOT / "scripts/run_frozen_alpha25_extraction.py").read_text(
        encoding="utf-8"
    ).casefold()

    assert "glm-5" not in text
    assert "paper_00" not in text


def test_field_level_configuration_forces_precision_experiment_bounds():
    environment, config = runner._build_verification_configuration(
        _args(
            verifier_field_level=True,
            verifier_bundle_assertions=12,
            verifier_bundle_chars=12000,
            verifier_bypass_axes="composition,properties",
            verifier_risk_routing=False,
            no_verifier_recovery=False,
        ),
        extraction_model="extraction-role",
    )

    assert environment["KNOWMAT2_ALPHA25_VERIFIER_FIELD_LEVEL"] == "1"
    assert environment["KNOWMAT2_ALPHA25_VERIFIER_RECOVERY"] == "0"
    assert environment["KNOWMAT2_ALPHA25_VERIFIER_RISK_ROUTING"] == "1"
    assert environment["KNOWMAT2_ALPHA25_VERIFIER_BYPASS_AXES"] == "composition"
    assert environment["KNOWMAT2_ALPHA25_VERIFIER_BUNDLE_ASSERTIONS"] == "6"
    assert environment["KNOWMAT2_ALPHA25_VERIFIER_BUNDLE_CHARS"] == "6000"
    assert environment["KNOWMAT2_ALPHA25_VERIFIER_REASONING_EFFORT"] == (
        "provider_default"
    )
    assert environment[
        "KNOWMAT2_ALPHA25_VERIFIER_FALLBACK_REASONING_EFFORT"
    ] == "low"
    assert config == {
        "protocol_version": runner.FIELD_VERIFICATION_PROTOCOL_VERSION,
        "field_level": True,
        "risk_routing_enabled": True,
        "recovery_enabled": False,
        "bypass_axes": ["composition"],
        "max_bundle_assertions": 6,
        "max_bundle_source_chars": 6000,
        "primary_reasoning_effort": "provider_default",
        "fallback_reasoning_effort": "low",
        "primary_api_mode": "chat_completions",
        "fallback_api_mode": "chat_completions",
        "primary_output_token_budget": 3072,
        "fallback_output_token_budget": 6144,
        "singleton_truncation_retries": 1,
        "compact_output_token_budget": 1024,
        "compact_split_limit": 1,
    }


def test_field_level_configuration_preserves_stricter_user_bundle_bounds():
    environment, config = runner._build_verification_configuration(
        _args(
            verifier_field_level=True,
            verifier_bundle_assertions=2,
            verifier_bundle_chars=2400,
        ),
        extraction_model="extraction-role",
    )

    assert environment["KNOWMAT2_ALPHA25_VERIFIER_BUNDLE_ASSERTIONS"] == "2"
    assert environment["KNOWMAT2_ALPHA25_VERIFIER_BUNDLE_CHARS"] == "2400"
    assert config["max_bundle_assertions"] == 2
    assert config["max_bundle_source_chars"] == 2400


def test_legacy_verification_configuration_remains_cli_driven():
    environment, config = runner._build_verification_configuration(
        _args(
            verifier_field_level=False,
            verifier_bundle_assertions=8,
            verifier_bundle_chars=7000,
            verifier_bypass_axes="composition,properties",
            verifier_risk_routing=True,
            no_verifier_recovery=True,
        ),
        extraction_model="extraction-role",
    )

    assert environment["KNOWMAT2_ALPHA25_VERIFIER_FIELD_LEVEL"] == "0"
    assert environment["KNOWMAT2_ALPHA25_VERIFIER_RECOVERY"] == "0"
    assert environment["KNOWMAT2_ALPHA25_VERIFIER_RISK_ROUTING"] == "1"
    assert environment["KNOWMAT2_ALPHA25_VERIFIER_BYPASS_AXES"] == (
        "composition,properties"
    )
    assert environment["KNOWMAT2_ALPHA25_VERIFIER_BUNDLE_ASSERTIONS"] == "8"
    assert environment["KNOWMAT2_ALPHA25_VERIFIER_BUNDLE_CHARS"] == "7000"
    assert config["protocol_version"] == runner.VERIFICATION_PROTOCOL_VERSION
    assert config["field_level"] is False


def test_field_level_protocol_and_effective_config_are_written_to_manifest(
    tmp_path, monkeypatch
):
    output_root = tmp_path / "output"
    monkeypatch.setattr(runner, "load_paper_specs", lambda *args, **kwargs: ({}, []))
    monkeypatch.setattr(
        runner,
        "_read_object",
        lambda path: {
            "status": "ok",
            "model": "extraction-role",
            "effective": {
                "thinking_mode": "provider_default",
                "response_format": "json_object",
            },
        },
    )
    monkeypatch.setattr(
        runner,
        "_configure_effective_capabilities",
        lambda manifest, probe, model: {},
    )
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "run_frozen_alpha25_extraction.py",
            "--experiment-manifest",
            str(tmp_path / "experiment.json"),
            "--capability-probe",
            str(tmp_path / "probe.json"),
            "--output-root",
            str(output_root),
            "--model",
            "extraction-role",
            "--hierarchical-verification",
            "--verifier-field-level",
            "--verifier-model",
            "primary-role",
            "--verifier-fallback-model",
            "review-role",
            "--verifier-api-mode",
            "chat_completions",
            "--verifier-fallback-api-mode",
            "responses",
            "--verifier-bundle-assertions",
            "10",
            "--verifier-bundle-chars",
            "9000",
        ],
    )
    original_environment = dict(os.environ)
    try:
        assert runner.main() == 0
    finally:
        os.environ.clear()
        os.environ.update(original_environment)

    manifest = json.loads(
        (output_root / "extraction_run_manifest.json").read_text(encoding="utf-8")
    )
    assert (
        manifest["verifier_protocol_version"]
        == runner.FIELD_VERIFICATION_PROTOCOL_VERSION
    )
    assert manifest["verifier_config"] == {
        "protocol_version": runner.FIELD_VERIFICATION_PROTOCOL_VERSION,
        "field_level": True,
        "risk_routing_enabled": True,
        "recovery_enabled": False,
        "bypass_axes": ["composition"],
        "max_bundle_assertions": 6,
        "max_bundle_source_chars": 6000,
        "primary_reasoning_effort": "provider_default",
        "fallback_reasoning_effort": "low",
        "primary_api_mode": "chat_completions",
        "fallback_api_mode": "responses",
        "primary_output_token_budget": 3072,
        "fallback_output_token_budget": 3072,
        "singleton_truncation_retries": 1,
        "compact_output_token_budget": 1024,
        "compact_split_limit": 1,
    }
    assert manifest["applied_safe_environment"][
        "KNOWMAT2_ALPHA25_VERIFIER_FIELD_LEVEL"
    ] == "1"
