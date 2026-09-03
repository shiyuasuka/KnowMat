from __future__ import annotations

from scripts import rematerialize_alpha25_tasks as rematerialize


def test_rematerialized_replay_wires_field_and_compact_verifier_env(
    tmp_path, monkeypatch
):
    observed = {}

    class FakeClient:
        def __init__(self, primary, fallback, **kwargs):
            observed.update(
                {"primary": primary, "fallback": fallback, **kwargs}
            )

    monkeypatch.setattr(
        rematerialize,
        "verifier_configs_from_env",
        lambda: ("primary-role", "fallback-role"),
    )
    monkeypatch.setattr(rematerialize, "VerificationClient", FakeClient)
    monkeypatch.setenv("KNOWMAT2_ALPHA25_VERIFIER_CACHE_DIR", str(tmp_path / "cache"))
    monkeypatch.setenv("KNOWMAT2_ALPHA25_VERIFIER_FIELD_LEVEL", "1")
    monkeypatch.setenv("KNOWMAT2_ALPHA25_VERIFIER_COMPACT_MAX_TOKENS", "1024")
    monkeypatch.setenv("KNOWMAT2_ALPHA25_VERIFIER_COMPACT_SPLIT_LIMIT", "1")

    paper_root = tmp_path / "paper"
    rematerialize._verification_client_for_paper(paper_root)

    assert observed == {
        "primary": "primary-role",
        "fallback": "fallback-role",
        "cache_dir": tmp_path / "cache" / "paper",
        "destructive_consensus": True,
        "field_level": True,
        "compact_output_token_budget": 1024,
        "compact_split_limit": 1,
    }


def test_rematerialized_replay_defaults_compact_budget_to_1024(
    tmp_path, monkeypatch
):
    observed = {}

    class FakeClient:
        def __init__(self, primary, fallback, **kwargs):
            observed.update(kwargs)

    monkeypatch.setattr(
        rematerialize,
        "verifier_configs_from_env",
        lambda: ("primary-role", "fallback-role"),
    )
    monkeypatch.setattr(rematerialize, "VerificationClient", FakeClient)
    monkeypatch.delenv(
        "KNOWMAT2_ALPHA25_VERIFIER_COMPACT_MAX_TOKENS", raising=False
    )

    rematerialize._verification_client_for_paper(tmp_path / "paper")

    assert observed["compact_output_token_budget"] == 1024
