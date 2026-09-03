import json
import time
from types import SimpleNamespace

import pytest

from knowmat.nodes.extraction import (
    V11RawResponseError,
    _alpha25_llm_identity,
    _decode_v11_json_response,
    _invoke_with_hard_timeout,
    _invoke_alpha25_task_json,
    _v11_json_mode_for_model,
)


def test_hard_timeout_closes_long_running_invocation(monkeypatch):
    class SlowClient:
        def close(self):
            # Simulate a gateway transport whose close blocks on a live socket.
            time.sleep(0.2)

    class SlowLLM:
        root_client = SlowClient()

        def invoke(self, _messages):
            time.sleep(0.2)
            return SimpleNamespace(content="{}")

    # Keep the unit test independent from the production socket-drain grace.
    monkeypatch.setenv("KNOWMAT2_ALPHA25_TIMEOUT_DRAIN_SECONDS", "0")
    monkeypatch.setenv("KNOWMAT2_ALPHA25_TIMEOUT_CLOSE_SECONDS", "0.01")
    started = time.monotonic()
    with pytest.raises(TimeoutError, match="hard timeout"):
        _invoke_with_hard_timeout(SlowLLM(), [{"role": "user", "content": "x"}], 0.02)
    assert time.monotonic() - started < 0.15
from knowmat.extractors import extraction_thinking_mode, get_llm, llm_api_mode
from knowmat.extraction_capabilities import probe_extraction_capabilities


def test_json_object_mode_is_endpoint_configuration_not_model_name(monkeypatch):
    monkeypatch.delenv("KNOWMAT2_EXTRACTION_RESPONSE_FORMAT", raising=False)
    assert _v11_json_mode_for_model("glm-5.2") is None
    assert _v11_json_mode_for_model("future-model") is None

    monkeypatch.setenv("KNOWMAT2_EXTRACTION_RESPONSE_FORMAT", "json_object")
    assert _v11_json_mode_for_model("glm-5.2") == {"type": "json_object"}
    assert _v11_json_mode_for_model("future-model") == {"type": "json_object"}


def test_thinking_mode_is_endpoint_configuration_not_model_name(monkeypatch):
    monkeypatch.delenv("KNOWMAT2_EXTRACTION_THINKING", raising=False)
    assert extraction_thinking_mode("glm-5.2") == "provider_default"
    assert extraction_thinking_mode("future-model") == "provider_default"

    monkeypatch.setenv("KNOWMAT2_EXTRACTION_THINKING", "disabled")
    assert extraction_thinking_mode("glm-5.2") == "disabled"
    assert extraction_thinking_mode("future-model") == "disabled"


def test_llm_api_protocol_is_endpoint_configuration_not_model_name(monkeypatch):
    monkeypatch.delenv("KNOWMAT2_LLM_API_MODE", raising=False)
    assert llm_api_mode() == "chat_completions"

    monkeypatch.setenv("KNOWMAT2_LLM_API_MODE", "responses")
    assert llm_api_mode() == "responses"


def test_chat_client_accepts_explicit_provider_neutral_reasoning_effort(monkeypatch):
    captured = {}

    def fake_chat_openai(**kwargs):
        captured.update(kwargs)
        return kwargs

    monkeypatch.setattr("knowmat.extractors.ChatOpenAI", fake_chat_openai)
    monkeypatch.setenv("KNOWMAT2_LLM_API_MODE", "chat_completions")

    get_llm(
        agent_type="extraction",
        model_override="future-model",
        reasoning_effort_override="low",
    )

    assert captured["reasoning_effort"] == "low"


def test_extraction_client_uses_bounded_timeout_and_configured_protocol(monkeypatch):
    captured = {}

    def fake_chat_openai(**kwargs):
        captured.update(kwargs)
        return kwargs

    monkeypatch.setattr("knowmat.extractors.ChatOpenAI", fake_chat_openai)
    monkeypatch.setattr("knowmat.extractors.settings.extraction_model", "future-model")
    monkeypatch.delenv("KNOWMAT2_EXTRACTION_TIMEOUT", raising=False)
    monkeypatch.setenv("KNOWMAT2_LLM_API_MODE", "responses")

    get_llm(agent_type="extraction")

    assert captured["request_timeout"] == 180
    assert captured["use_responses_api"] is True
    assert "temperature" not in captured


def test_extraction_client_explicit_model_override_wins_without_mutating_settings(
    monkeypatch,
):
    captured = {}

    def fake_chat_openai(**kwargs):
        captured.update(kwargs)
        return kwargs

    monkeypatch.setattr("knowmat.extractors.ChatOpenAI", fake_chat_openai)
    monkeypatch.setattr("knowmat.extractors.settings.extraction_model", "baseline-model")

    get_llm(agent_type="extraction", model_override="trial-model")

    assert captured["model"] == "trial-model"
    assert settings_model("knowmat.extractors") == "baseline-model"


def settings_model(module_name):
    module = __import__(module_name, fromlist=["settings"])
    return module.settings.extraction_model


def test_alpha25_identity_uses_per_task_output_budget(monkeypatch):
    monkeypatch.setattr("knowmat.nodes.extraction.settings.extraction_model", "glm-5.2")
    monkeypatch.setenv("LLM_BASE_URL", "https://user:secret@example.test/v1")
    monkeypatch.setenv("KNOWMAT2_EXTRACTION_RESPONSE_FORMAT", "json_object")
    monkeypatch.setenv("KNOWMAT2_EXTRACTION_THINKING", "provider_default")

    identity = _alpha25_llm_identity(2400)

    assert identity["output_token_budget"] == 2400
    assert identity["endpoint"] == "https://example.test/v1"
    assert identity["thinking_mode"] == "provider_default"


def test_alpha25_identity_accepts_explicit_per_run_model(monkeypatch):
    monkeypatch.setattr("knowmat.nodes.extraction.settings.extraction_model", "baseline-model")
    monkeypatch.setenv("KNOWMAT2_EXTRACTION_THINKING", "provider_default")

    identity = _alpha25_llm_identity(2400, extraction_model="trial-model")

    assert identity["model"] == "trial-model"
    assert settings_model("knowmat.nodes.extraction") == "baseline-model"


def test_truncated_response_is_objective_retry_failure():
    response = SimpleNamespace(
        content='{"axis":"properties","facts":[',
        response_metadata={"finish_reason": "length"},
    )
    with pytest.raises(V11RawResponseError) as caught:
        _decode_v11_json_response(response)
    assert caught.value.code == "output_truncated"


def test_axis_invocation_binds_small_budget_and_parses_contract(monkeypatch):
    captured = {}

    class FakeLLM:
        def bind(self, **kwargs):
            captured.update(kwargs)
            return self

        def invoke(self, messages):
            captured["messages"] = messages
            return SimpleNamespace(
                content='{"axis":"structure","facts":[]}',
                response_metadata={"finish_reason": "stop"},
            )

    monkeypatch.setattr("knowmat.nodes.extraction.settings.extraction_model", "glm-5.2")
    fake_llm = FakeLLM()
    monkeypatch.setattr("knowmat.nodes.extraction.get_llm", lambda **_kwargs: fake_llm)
    monkeypatch.setenv("KNOWMAT2_EXTRACTION_RESPONSE_FORMAT", "json_object")

    response = _invoke_alpha25_task_json(
        "SYSTEM", "USER", axis="structure", output_token_budget=1800
    )

    assert response.axis == "structure"
    assert captured["max_tokens"] == 1800
    assert captured["response_format"] == {"type": "json_object"}


def test_axis_invocation_compacts_budget_after_transient_timeouts(monkeypatch):
    budgets = []

    class FakeLLM:
        calls = 0

        def bind(self, **kwargs):
            budgets.append(kwargs["max_tokens"])
            return self

        def invoke(self, _messages):
            self.calls += 1
            if self.calls < 3:
                raise TimeoutError("request timed out")
            return SimpleNamespace(
                content='{"axis":"structure","facts":[]}',
                response_metadata={"finish_reason": "stop"},
            )

    fake_llm = FakeLLM()
    monkeypatch.setattr("knowmat.nodes.extraction.get_llm", lambda **_kwargs: fake_llm)
    monkeypatch.setenv("KNOWMAT2_ALPHA25_TRANSIENT_RETRIES", "0")
    monkeypatch.setenv("KNOWMAT2_ALPHA25_COMPACT_BUDGET_FALLBACKS", "2")
    monkeypatch.setenv("KNOWMAT2_ALPHA25_COMPACT_BUDGET_FLOOR", "1024")

    response = _invoke_alpha25_task_json(
        "SYSTEM", "USER", axis="structure", output_token_budget=4096
    )

    assert response.axis == "structure"
    assert budgets == [4096, 2048, 1024]


def test_axis_invocation_passes_explicit_model_to_client(monkeypatch):
    captured = {}

    class FakeLLM:
        def bind(self, **kwargs):
            captured["bind"] = kwargs
            return self

        def invoke(self, _messages):
            return SimpleNamespace(
                content='{"axis":"structure","facts":[]}',
                response_metadata={"finish_reason": "stop"},
            )

    def fake_get_llm(**kwargs):
        captured["client"] = kwargs
        return FakeLLM()

    monkeypatch.setattr("knowmat.nodes.extraction.get_llm", fake_get_llm)
    monkeypatch.setattr("knowmat.nodes.extraction.settings.extraction_model", "baseline-model")
    monkeypatch.setenv("KNOWMAT2_EXTRACTION_THINKING", "provider_default")

    response = _invoke_alpha25_task_json(
        "SYSTEM",
        "USER",
        axis="structure",
        output_token_budget=1800,
        extraction_model="trial-model",
    )

    assert response.axis == "structure"
    assert captured["client"]["model_override"] == "trial-model"


def test_rejected_thinking_capability_falls_back_without_model_name_rule(monkeypatch):
    modes = []

    class FakeLLM:
        calls = 0

        def bind(self, **_kwargs):
            return self

        def invoke(self, _messages):
            self.calls += 1
            if self.calls == 1:
                raise RuntimeError("InvalidParameter: thinking is not supported")
            return SimpleNamespace(
                content='{"axis":"structure","facts":[]}',
                response_metadata={"finish_reason": "stop"},
            )

    llm = FakeLLM()

    def fake_get_llm(**kwargs):
        modes.append(kwargs.get("thinking_mode_override"))
        return llm

    monkeypatch.setattr(
        "knowmat.nodes.extraction.settings.extraction_model", "future-model"
    )
    monkeypatch.setattr("knowmat.nodes.extraction.get_llm", fake_get_llm)
    monkeypatch.setenv("KNOWMAT2_EXTRACTION_THINKING", "disabled")

    response = _invoke_alpha25_task_json(
        "SYSTEM", "USER", axis="structure", output_token_budget=1800
    )

    assert response.axis == "structure"
    assert modes == ["disabled", "provider_default"]


def test_rejected_coding_plan_capability_uses_same_generic_fallback(monkeypatch):
    modes = []

    class FakeLLM:
        calls = 0

        def bind(self, **_kwargs):
            return self

        def invoke(self, _messages):
            self.calls += 1
            if self.calls == 1:
                raise RuntimeError(
                    "UnsupportedModel: model does not support the coding plan feature"
                )
            return SimpleNamespace(
                content='{"axis":"structure","facts":[]}',
                response_metadata={"finish_reason": "stop"},
            )

    llm = FakeLLM()

    def fake_get_llm(**kwargs):
        modes.append(kwargs.get("thinking_mode_override"))
        return llm

    monkeypatch.setattr(
        "knowmat.nodes.extraction.settings.extraction_model", "future-model"
    )
    monkeypatch.setattr("knowmat.nodes.extraction.get_llm", fake_get_llm)
    monkeypatch.setenv("KNOWMAT2_EXTRACTION_THINKING", "disabled")

    response = _invoke_alpha25_task_json(
        "SYSTEM", "USER", axis="structure", output_token_budget=1800
    )

    assert response.axis == "structure"
    assert modes == ["disabled", "provider_default"]


def test_capability_probe_falls_back_once_without_model_name_rule(monkeypatch):
    modes = []
    binds = []

    class FakeLLM:
        calls = 0

        def bind(self, **kwargs):
            binds.append(kwargs)
            return self

        def invoke(self, _messages):
            self.calls += 1
            if self.calls == 1:
                raise RuntimeError("InvalidParameter: thinking is not supported")
            return SimpleNamespace(content='{"probe":"ok"}')

    llm = FakeLLM()

    def factory(**kwargs):
        modes.append(kwargs.get("thinking_mode_override"))
        return llm

    monkeypatch.setenv("KNOWMAT2_EXTRACTION_THINKING", "disabled")
    monkeypatch.setenv("KNOWMAT2_EXTRACTION_RESPONSE_FORMAT", "json_object")
    monkeypatch.setenv("LLM_BASE_URL", "https://user:secret@example.test/v1?token=x")

    result = probe_extraction_capabilities(
        model="future-model",
        llm_factory=factory,
    )

    assert result["status"] == "ok"
    assert result["configured"]["thinking_mode"] == "disabled"
    assert result["effective"]["thinking_mode"] == "provider_default"
    assert result["effective"]["response_format"] == "json_object"
    assert result["endpoint"] == "https://example.test/v1"
    assert modes == ["disabled", "provider_default"]
    assert binds == [
        {"max_tokens": 64, "response_format": {"type": "json_object"}},
        {"max_tokens": 64, "response_format": {"type": "json_object"}},
    ]
    serialized = json.dumps(result, sort_keys=True)
    assert "secret" not in serialized
    assert "token=x" not in serialized


def test_capability_probe_can_fall_back_from_response_format(monkeypatch):
    binds = []

    class FakeLLM:
        calls = 0

        def bind(self, **kwargs):
            binds.append(kwargs)
            return self

        def invoke(self, _messages):
            self.calls += 1
            if self.calls == 1:
                raise RuntimeError(
                    "Invalid parameter: response_format json_object is not supported"
                )
            return SimpleNamespace(content='{"probe":"ok"}')

    llm = FakeLLM()
    monkeypatch.setenv("KNOWMAT2_EXTRACTION_THINKING", "provider_default")
    monkeypatch.setenv("KNOWMAT2_EXTRACTION_RESPONSE_FORMAT", "json_object")

    result = probe_extraction_capabilities(
        model="another-future-model",
        llm_factory=lambda **_kwargs: llm,
    )

    assert result["status"] == "ok"
    assert result["effective"]["thinking_mode"] == "provider_default"
    assert result["effective"]["response_format"] == "text"
    assert binds == [
        {"max_tokens": 64, "response_format": {"type": "json_object"}},
        {"max_tokens": 64},
    ]


def test_alpha25_identity_changes_with_model_and_effective_capability(monkeypatch):
    monkeypatch.setenv("KNOWMAT2_EXTRACTION_RESPONSE_FORMAT", "json_object")
    monkeypatch.setenv("KNOWMAT2_EXTRACTION_THINKING", "disabled")
    monkeypatch.setattr("knowmat.nodes.extraction.settings.extraction_model", "model-a")
    model_a = _alpha25_llm_identity(1800)

    monkeypatch.setattr("knowmat.nodes.extraction.settings.extraction_model", "model-b")
    model_b = _alpha25_llm_identity(1800)

    monkeypatch.setenv("KNOWMAT2_EXTRACTION_THINKING", "provider_default")
    fallback = _alpha25_llm_identity(1800)

    assert model_a != model_b
    assert model_b != fallback
    assert model_a["model"] == "model-a"
    assert model_b["model"] == "model-b"
    assert fallback["thinking_mode"] == "provider_default"
