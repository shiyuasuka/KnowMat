from __future__ import annotations

import importlib.util
import json
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = REPO_ROOT / "scripts" / "independent_gt.py"
SPEC = importlib.util.spec_from_file_location("independent_gt", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
independent_gt = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(independent_gt)


def _valid_claim() -> dict[str, object]:
    return {
        "claim_id": "clm_0001",
        "paper_key": "Paper title",
        "axis": "Properties",
        "owner": {
            "material_id": "mat_001",
            "material_name": "Alloy A",
            "sample_id": None,
            "state": None,
            "region": None,
            "orientation": None,
            "role": "Target",
        },
        "semantic_key": "yield_strength",
        "name_raw": "yield strength",
        "value": {
            "kind": "scalar",
            "raw": "100 MPa",
            "number": 100,
            "min": None,
            "max": None,
            "operator": None,
            "bound": None,
            "stddev": None,
            "text": None,
        },
        "unit_raw": "MPa",
        "condition": {
            "raw": None,
            "temperature_raw": None,
            "time_raw": None,
            "rate_raw": None,
            "environment_raw": None,
            "details": {},
        },
        "origin": "author_experiment",
        "evidence": [
            {
                "source_type": "markdown",
                "path": "paper.md",
                "sha256": "a" * 64,
                "locator": "L10",
                "quote": "The yield strength was 100 MPa.",
                "columns": [],
            }
        ],
        "confidence": 0.95,
        "review_status": "accepted",
        "notes": None,
    }


def test_title_key_normalizes_unicode_slashes_and_punctuation() -> None:
    left = "Sc／Zr-modified γ-TiAl"
    right = "Sc/Zr modified γ TiAl"
    assert independent_gt._title_key(left) == independent_gt._title_key(right)


def test_quote_support_tolerates_ocr_line_wrapping_but_not_locator_only() -> None:
    source = "The yield strength was\n100 MPa after aging."
    assert independent_gt._quote_supported("yield strength was 100 MPa", source)
    assert not independent_gt._quote_supported("L10", source)


def test_dependency_free_claim_contract_accepts_valid_claim() -> None:
    schema = json.loads(
        (REPO_ROOT / "schemas/independent_gt/claim.schema.json").read_text(
            encoding="utf-8"
        )
    )
    assert independent_gt._schema_errors(_valid_claim(), schema) == []


def test_claim_contract_rejects_missing_owner_and_bad_axis() -> None:
    schema = json.loads(
        (REPO_ROOT / "schemas/independent_gt/claim.schema.json").read_text(
            encoding="utf-8"
        )
    )
    claim = _valid_claim()
    claim.pop("owner")
    claim["axis"] = "Equipment"
    errors = independent_gt._schema_errors(claim, schema)
    assert any("missing required property 'owner'" in error for error in errors)
    assert any("allowed enum" in error for error in errors)


def test_claim_contract_rejects_sentence_slug_semantic_key() -> None:
    schema = json.loads(
        (REPO_ROOT / "schemas/independent_gt/claim.schema.json").read_text(
            encoding="utf-8"
        )
    )
    claim = _valid_claim()
    claim["semantic_key"] = "properties.this_is_a_sentence_" + "x" * 80
    errors = independent_gt._schema_errors(claim, schema)
    assert any("longer than" in error or "does not match" in error for error in errors)


def test_claim_contract_rejects_sentence_as_raw_name() -> None:
    schema = json.loads(
        (REPO_ROOT / "schemas/independent_gt/claim.schema.json").read_text(
            encoding="utf-8"
        )
    )
    claim = _valid_claim()
    claim["name_raw"] = (
        "The yield strength was measured after heat treatment at room temperature "
        "using a standard tensile specimen."
    )
    errors = independent_gt._schema_errors(claim, schema)
    assert any("longer than" in error for error in errors)


def test_prepared_manifest_has_expected_frozen_corpus() -> None:
    manifest = json.loads(
        (
            REPO_ROOT
            / "data/gt/gpt56sol-independent-expert-20260818/blind_input_manifest.json"
        ).read_text(encoding="utf-8")
    )
    assert manifest["ocr_baseline"]["baseline_id"] == independent_gt.EXPECTED_BASELINE_ID
    assert manifest["paper_count"] == 30
    assert manifest["chart_csv_count"] == 95
    assert {paper["batch_id"] for paper in manifest["papers"]} == {
        "batch_a",
        "batch_b",
        "batch_c",
    }
