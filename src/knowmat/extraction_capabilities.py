"""Provider-neutral capability probing for the extraction request shape."""

from __future__ import annotations

import json
import os
import time
from typing import Any, Callable

from knowmat.app_config import settings
from knowmat.extractors import (
    extraction_reasoning_effort,
    extraction_thinking_mode,
    get_llm,
    llm_api_mode,
)
from knowmat.nodes.extraction import (
    _endpoint_identity,
    _extract_json_object_text,
    _flatten_message_content,
    _is_provider_option_error,
    _v11_json_mode_for_model,
)


_PROBE_MESSAGES = [
    {
        "role": "system",
        "content": "Return exactly one compact JSON object and no explanation.",
    },
    {"role": "user", "content": 'Return {"probe":"ok"}.'},
]


def _response_format_name(response_mode: dict[str, str] | None) -> str:
    return response_mode["type"] if response_mode else "text"


def _attempt_record(
    *,
    number: int,
    thinking_mode: str,
    reasoning_effort: str,
    response_mode: dict[str, str] | None,
    elapsed_seconds: float,
    outcome: str,
    error: Exception | None = None,
    rejected_option: str | None = None,
) -> dict[str, Any]:
    row: dict[str, Any] = {
        "attempt": number,
        "thinking_mode": thinking_mode,
        "reasoning_effort": reasoning_effort,
        "response_format": _response_format_name(response_mode),
        "elapsed_seconds": round(elapsed_seconds, 6),
        "outcome": outcome,
    }
    if error is not None:
        # Provider messages can echo request details. Keep only the exception
        # class and the capability category proven by the generic classifier.
        row["error_class"] = error.__class__.__name__
    if rejected_option:
        row["rejected_option"] = rejected_option
    return row


def probe_extraction_capabilities(
    *,
    model: str,
    llm_factory: Callable[..., Any] | None = None,
) -> dict[str, Any]:
    """Return configured/effective extraction capabilities for one endpoint.

    The probe contains no paper text and never branches on a provider or model
    name. Optional capabilities are dropped only after the endpoint explicitly
    rejects their request fields.
    """

    factory = llm_factory or get_llm
    configured_thinking = extraction_thinking_mode(model)
    configured_reasoning = extraction_reasoning_effort(model)
    configured_response = _v11_json_mode_for_model(model)
    thinking_mode = configured_thinking
    reasoning_effort = configured_reasoning
    response_mode = configured_response
    attempts: list[dict[str, Any]] = []
    thinking_fallback_used = False
    reasoning_fallback_used = False
    response_fallback_used = False
    original_model = settings.extraction_model
    settings.extraction_model = model
    started = time.monotonic()
    try:
        while True:
            llm = factory(
                agent_type="extraction",
                thinking_mode_override=thinking_mode,
                reasoning_effort_override=reasoning_effort,
            )
            bind_options: dict[str, Any] = {"max_tokens": 64}
            if response_mode:
                bind_options["response_format"] = response_mode
            bound = llm.bind(**bind_options)
            attempt_started = time.monotonic()
            try:
                response = bound.invoke(_PROBE_MESSAGES)
                content = _flatten_message_content(
                    getattr(response, "content", response)
                )
                payload = json.loads(_extract_json_object_text(content))
                if not isinstance(payload, dict) or payload.get("probe") != "ok":
                    raise ValueError("probe response did not contain probe=ok")
            except Exception as exc:
                elapsed = time.monotonic() - attempt_started
                if (
                    thinking_mode != "provider_default"
                    and not thinking_fallback_used
                    and _is_provider_option_error(exc, "thinking", "coding plan")
                ):
                    attempts.append(
                        _attempt_record(
                            number=len(attempts) + 1,
                            thinking_mode=thinking_mode,
                            reasoning_effort=reasoning_effort,
                            response_mode=response_mode,
                            elapsed_seconds=elapsed,
                            outcome="capability_rejected",
                            error=exc,
                            rejected_option="thinking",
                        )
                    )
                    thinking_fallback_used = True
                    thinking_mode = "provider_default"
                    continue
                if (
                    reasoning_effort != "provider_default"
                    and not reasoning_fallback_used
                    and _is_provider_option_error(
                        exc, "reasoning_effort", "reasoning effort"
                    )
                ):
                    attempts.append(
                        _attempt_record(
                            number=len(attempts) + 1,
                            thinking_mode=thinking_mode,
                            reasoning_effort=reasoning_effort,
                            response_mode=response_mode,
                            elapsed_seconds=elapsed,
                            outcome="capability_rejected",
                            error=exc,
                            rejected_option="reasoning_effort",
                        )
                    )
                    reasoning_fallback_used = True
                    reasoning_effort = "provider_default"
                    continue
                if (
                    response_mode is not None
                    and not response_fallback_used
                    and _is_provider_option_error(
                        exc, "response_format", "json_object", "json mode"
                    )
                ):
                    attempts.append(
                        _attempt_record(
                            number=len(attempts) + 1,
                            thinking_mode=thinking_mode,
                            reasoning_effort=reasoning_effort,
                            response_mode=response_mode,
                            elapsed_seconds=elapsed,
                            outcome="capability_rejected",
                            error=exc,
                            rejected_option="response_format",
                        )
                    )
                    response_fallback_used = True
                    response_mode = None
                    continue
                attempts.append(
                    _attempt_record(
                        number=len(attempts) + 1,
                        thinking_mode=thinking_mode,
                        reasoning_effort=reasoning_effort,
                        response_mode=response_mode,
                        elapsed_seconds=elapsed,
                        outcome="failed",
                        error=exc,
                    )
                )
                raise
            attempts.append(
                _attempt_record(
                    number=len(attempts) + 1,
                    thinking_mode=thinking_mode,
                    reasoning_effort=reasoning_effort,
                    response_mode=response_mode,
                    elapsed_seconds=time.monotonic() - attempt_started,
                    outcome="ok",
                )
            )
            break
    finally:
        settings.extraction_model = original_model

    base_url = os.environ.get("LLM_BASE_URL") or os.environ.get("OPENAI_BASE_URL") or ""
    return {
        "schema_version": "knowmat_extraction_capability_probe_v1",
        "status": "ok",
        "model": model,
        "endpoint": _endpoint_identity(base_url),
        "api_mode": llm_api_mode(),
        "configured": {
            "thinking_mode": configured_thinking,
            "reasoning_effort": configured_reasoning,
            "response_format": _response_format_name(configured_response),
        },
        "effective": {
            "thinking_mode": thinking_mode,
            "reasoning_effort": reasoning_effort,
            "response_format": _response_format_name(response_mode),
        },
        "attempt_count": len(attempts),
        "total_elapsed_seconds": round(time.monotonic() - started, 6),
        "attempts": attempts,
    }


__all__ = ["probe_extraction_capabilities"]
