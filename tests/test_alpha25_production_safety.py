from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PRODUCTION_FILES = [
    ROOT / "src/knowmat/alpha25/contracts.py",
    ROOT / "src/knowmat/alpha25/candidate_replay.py",
    ROOT / "src/knowmat/alpha25/coverage.py",
    ROOT / "src/knowmat/alpha25/evidence.py",
    ROOT / "src/knowmat/alpha25/materialize.py",
    ROOT / "src/knowmat/alpha25/planner.py",
    ROOT / "src/knowmat/alpha25/promotion.py",
    ROOT / "src/knowmat/alpha25/prompt_compiler.py",
    ROOT / "src/knowmat/alpha25/verification.py",
    ROOT / "src/knowmat/alpha25/verification_client.py",
    ROOT / "src/knowmat/alpha25/verification_contracts.py",
    ROOT / "src/knowmat/alpha25/verification_inventory.py",
    ROOT / "src/knowmat/alpha25/verification_pipeline.py",
    ROOT / "src/knowmat/alpha25/verification_risk.py",
    ROOT / "src/knowmat/nodes/extraction.py",
    ROOT / "src/knowmat/nodes/v11_normalize.py",
    ROOT / "src/knowmat/v11_reconcile.py",
]


def test_production_path_does_not_read_gt_or_import_offline_evaluator():
    text = "\n".join(path.read_text(encoding="utf-8").casefold() for path in PRODUCTION_FILES)

    assert "data/gt" not in text
    assert "evaluation.alpha25_gt" not in text
    assert "ground_truth" not in text


def test_production_reconcile_and_normalize_have_no_reviewed_paper_literals():
    paths = [
        ROOT / "src/knowmat/alpha25/materialize.py",
        ROOT / "src/knowmat/nodes/v11_normalize.py",
        ROOT / "src/knowmat/v11_reconcile.py",
    ]
    text = "\n".join(path.read_text(encoding="utf-8").casefold() for path in paths)
    forbidden = (
        "inconel",
        "ti-6al-4v",
        "ti64",
        "haynes",
        "h230",
        "ccima",
        "wall_delay",
        "macrozone",
    )

    assert not [literal for literal in forbidden if literal in text]


def test_precision_promotion_has_no_provider_or_model_specific_branch():
    text = (
        ROOT / "src/knowmat/alpha25/promotion.py"
    ).read_text(encoding="utf-8").casefold()

    assert "glm" not in text
    assert "openai" not in text
    assert "provider" not in text


def test_hierarchical_verification_has_no_model_or_paper_specific_branch():
    paths = [
        ROOT / "src/knowmat/alpha25/verification.py",
        ROOT / "src/knowmat/alpha25/candidate_replay.py",
        ROOT / "src/knowmat/alpha25/verification_client.py",
        ROOT / "src/knowmat/alpha25/verification_contracts.py",
        ROOT / "src/knowmat/alpha25/verification_inventory.py",
        ROOT / "src/knowmat/alpha25/verification_pipeline.py",
        ROOT / "src/knowmat/alpha25/verification_risk.py",
    ]
    text = "\n".join(path.read_text(encoding="utf-8").casefold() for path in paths)
    forbidden = (
        "glm-5",
        "paper_00",
        "inconel",
        "ti-6al-4v",
        "expected_count",
        "expected_value",
    )
    assert not [literal for literal in forbidden if literal in text]
