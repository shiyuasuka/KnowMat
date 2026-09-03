"""Provider-neutral cached client for bounded Alpha25 verification bundles."""

from __future__ import annotations

import json
import os
import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from contextlib import nullcontext
from dataclasses import dataclass, field, replace
from pathlib import Path
from threading import Lock
from typing import Any, Callable, Literal
from urllib.parse import urlsplit, urlunsplit

from knowmat.alpha25.verification import (
    AppliedVerification,
    VerificationGroundingError,
    _literal_coordinate_in_evidence,
    _scientific_field_literals,
    apply_field_consensus,
    preserve_failed_bundle_result,
    required_scientific_fields,
    unresolved_bundle_result,
    validate_and_apply_bundle,
    validate_compact_review_response,
    validate_field_response,
    validate_recovery_response,
)
from knowmat.alpha25.verification_contracts import (
    COMPACT_LABEL_REVIEW_PROTOCOL_VERSION,
    COMPACT_REVIEW_PROTOCOL_VERSION,
    CompactLabel,
    CompactReviewDecision,
    CompactReviewResponse,
    FIELD_VERIFICATION_PROTOCOL_VERSION,
    FieldVerificationResponse,
    VERIFICATION_PROTOCOL_VERSION,
    RecoveryRequest,
    RecoveryResponse,
    VerificationBundle,
    VerificationResponse,
    canonical_json,
    parse_compact_label_array,
    stable_id,
)
from knowmat.alpha25.verification_inventory import (
    VerificationInventory,
    build_verification_bundles,
    build_verification_inventory,
)
from knowmat.app_config import settings
from knowmat.extractors import get_llm


VerifierRole = Literal["primary", "fallback"]
VerifierAPIMode = Literal["chat_completions", "responses"]
InvokeJSON = Callable[["VerifierRoleConfig", str, str], tuple[dict[str, Any], dict[str, Any]]]
InvokeResponses = Callable[
    ["VerifierRoleConfig", str, str], tuple[str, dict[str, Any]]
]


SYSTEM_PROMPT = """You are a source-grounded scientific assertion verifier.
Judge only the supplied candidate assertions against the supplied literal evidence.
Do not add or alter a value, unit, property semantic, material, state, or condition.
Accept only when every scientific field asserted by the candidate is supported; if
one multi-field candidate mixes supported and unsupported fields, quarantine the
whole candidate because this protocol does not permit editing its scientific payload.
For every assertion return exactly one decision: accept, merge, reassign, quarantine,
or unresolved. Merge only scientifically identical complete payloads, never partial,
overlapping, or subset assertions. Repeat the exact sorted member list and the same
existing survivor for every merge member. Reassign only a demonstrably wrong owner,
state, condition, or specimen to text that occurs literally in cited evidence; never
use reassignment for label normalization, abbreviation expansion, or generalization.
Cite only supplied evidence_id values. Treat Unicode and LaTeX presentation variants
as equivalent, but do not treat a paraphrase as a literal value or owner. If evidence
is insufficient, use unresolved. Return one compact JSON object matching the requested
protocol and no markdown or reasoning outside it.
"""

CONFIRMATION_SYSTEM_PROMPT = """You are the independent second reviewer for one
scientific assertion. Decide only whether the supplied literal evidence confirms
the first reviewer's proposed quarantine. Return exactly one compact protocol JSON
decision: quarantine when any asserted scientific field is contradicted or not
supported, accept when every asserted field is supported, or unresolved when the
evidence is insufficient. Never merge, reassign, edit, or add scientific content.
Use only supplied evidence_id values. Keep reason_code short and rationale to at
most 30 words. Return JSON only, with no analysis or markdown.
"""

RECOVERY_SYSTEM_PROMPT = """You are a bounded scientific omission detector.
Use only the supplied uncovered literal evidence. Propose a non-Composition AxisFact
only when its owner, semantic, value, unit, and conditions are explicit in that
evidence or in a supplied inventory entity. Never estimate a chart or curve, convert
a qualitative comparison into a numeric scalar, copy a collective statement to each
owner, or infer an unstated value. Return compact JSON with zero or more proposals and
no markdown. Every proposal will be independently verified by a separate request.
"""

FIELD_SYSTEM_PROMPT = """You are a source-grounded materials-science field
verifier. Judge every required field of every supplied immutable assertion using
only supplied evidence and inventory entities. For each required field return
exactly supported, contradicted, or not_proven and cite only supplied evidence_id
values. The value and unit verdicts are aggregate: they cover every top-level and
nested value_raw/unit_raw in Processing parameters, Structure features/entities,
and Properties; if any member is unsupported, the aggregate field is not fully
supported. The condition verdict likewise covers every asserted region,
orientation, and test/process condition. Do not add or alter a value, unit,
semantic, owner, state, condition,
specimen, origin, role, or evidence span. A correction target is allowed only for
owner/state/condition/specimen/origin/role with verdict=contradicted and must select
supplied literal text or
an existing inventory entity; state/condition/specimen corrections are allowed only
when the assertion contains that exact mutable contract field. Do not reinterpret a
Structure region as a property test condition. Do not infer a collective or
respectively mapping. For every supported or not_proven verdict, return both
selected_entity_id and selected_text as null. Keep rationale under 30 words.
For aggregate value, unit, or condition support, cite evidence IDs that
collectively cover every nested literal. When owner or state support relies on
an inventory entity, cite that entity's exact supplied evidence ID.
Return exactly one compact JSON object matching the requested protocol and no
markdown or hidden analysis.
"""

FIELD_REVIEW_SYSTEM_PROMPT = """You are an independent source-grounded
materials-science field reviewer. Judge every required field of every supplied
immutable assertion from the supplied evidence and inventory only. Return exactly
supported, contradicted, or not_proven for each required field with supplied
evidence_id citations. Do not add or edit scientific content, infer a mapping, or
select anything outside the supplied literal coordinates. Select a correction target
only for verdict=contradicted; supported and not_proven must return null targets.
Aggregate value, unit, and condition evidence IDs must collectively cover every
nested literal. Inventory-backed owner or state support must cite the exact
supplied entity evidence ID.
Keep rationale under 30 words. Return one compact JSON
object matching the requested protocol and no markdown or analysis.
"""

COMPACT_REVIEW_SYSTEM_PROMPT = """You are an independent source-grounded
materials-science reviewer. Check every listed required field of each immutable
assertion against only the supplied evidence and inventory. Return exactly one
compact decision per assertion. Use all_fields_supported only when every listed
field is supported; otherwise use contradicted or not_proven and list only the
failed field names. Cite only supplied evidence_id values. Do not copy, edit, or
add any assertion, value, unit, semantic, owner, state, condition, specimen,
origin, role, evidence text, or correction target. Do not include rationale,
analysis, markdown, or extra keys. Return exactly one compact JSON object.
"""

COMPACT_LABEL_SYSTEM_PROMPT = """You are an independent source-grounded
materials-science reviewer. For each indexed immutable assertion, check every
listed required field against only the supplied evidence and inventory. Return
one JSON array in request order and nothing else. Use S only when every required
field is supported, C when any required field is contradicted, and N when any
required field is not proven. The array length must exactly equal label_count.
Do not copy, edit, infer, normalize, reassign, or add scientific content. Do not
inherit an observation from a child specimen to a parent material, or from a
parent material to a child specimen. At the first contradicted field choose C;
at the first unproven field choose N; do not search for a charitable mapping.
Return the final array immediately. Do not return IDs, evidence, rationale,
markdown, or analysis.
"""


class VerificationClientError(RuntimeError):
    """Classified provider/response failure eligible for role fallback."""

    def __init__(
        self,
        code: str,
        message: str = "",
        *,
        metrics: dict[str, Any] | None = None,
    ) -> None:
        self.code = code
        self.metrics = dict(metrics or {})
        super().__init__(f"{code}: {message}" if message else code)


@dataclass(frozen=True)
class VerifierRoleConfig:
    role: VerifierRole
    model: str
    endpoint: str
    thinking_mode: Literal["enabled", "disabled", "provider_default"] = (
        "provider_default"
    )
    reasoning_effort: Literal["low", "medium", "high", "provider_default"] = (
        "provider_default"
    )
    response_mode: Literal["json_object", "text"] = "json_object"
    api_mode: VerifierAPIMode = "chat_completions"
    output_token_budget: int = 4096
    timeout_seconds: int = 180
    transient_retries: int = 1

    def identity(self) -> dict[str, Any]:
        identity = {
            "role": self.role,
            "model": self.model,
            "endpoint": self.endpoint,
            "thinking_mode": self.thinking_mode,
            "response_mode": self.response_mode,
            "api_mode": self.api_mode,
            "output_token_budget": self.output_token_budget,
            "timeout_seconds": self.timeout_seconds,
            "transient_retries": self.transient_retries,
        }
        # Omitting the default preserves existing content-addressed caches.
        # An explicit effort changes the request and therefore the cache key.
        if self.reasoning_effort != "provider_default":
            identity["reasoning_effort"] = self.reasoning_effort
        return identity


@dataclass
class VerificationClientMetrics:
    provider_calls: int = 0
    cache_hits: int = 0
    primary_failures: int = 0
    fallback_calls: int = 0
    fallback_failures: int = 0
    unresolved_bundles: int = 0
    preserved_unresolved_assertions: int = 0
    destructive_confirmation_calls: int = 0
    destructive_confirmation_failures: int = 0
    destructive_confirmation_skipped_count: int = 0
    destructive_candidate_count: int = 0
    confirmed_quarantine_count: int = 0
    preserved_destructive_disagreement_count: int = 0
    field_primary_calls: int = 0
    field_secondary_calls: int = 0
    field_primary_positive_hard_count: int = 0
    field_secondary_skipped_count: int = 0
    compact_secondary_calls: int = 0
    compact_split_count: int = 0
    compact_truncation_count: int = 0
    field_hard_assertion_count: int = 0
    field_soft_assertion_count: int = 0
    field_isolated_assertion_count: int = 0
    field_reassigned_assertion_count: int = 0
    field_preserved_assertion_count: int = 0
    field_shape_normalization_count: int = 0
    split_retry_eligible: int = 0
    retry_count: int = 0
    capability_fallback_count: int = 0
    elapsed_seconds: float = 0.0
    provider_call_seconds: float = 0.0
    failures_by_code: dict[str, int] = field(default_factory=dict)

    def record_failure(self, code: str) -> None:
        self.failures_by_code[code] = self.failures_by_code.get(code, 0) + 1

    def absorb_provider_attempt(self, other: "VerificationClientMetrics") -> None:
        """Merge one independently executed role without double-counting wall time."""

        for name in (
            "provider_calls",
            "cache_hits",
            "retry_count",
            "capability_fallback_count",
        ):
            setattr(self, name, int(getattr(self, name)) + int(getattr(other, name)))
        self.provider_call_seconds += other.provider_call_seconds
        for code, count in other.failures_by_code.items():
            self.failures_by_code[code] = self.failures_by_code.get(code, 0) + count

    def to_dict(self) -> dict[str, Any]:
        return {
            "provider_calls": self.provider_calls,
            "cache_hits": self.cache_hits,
            "primary_failures": self.primary_failures,
            "fallback_calls": self.fallback_calls,
            "fallback_failures": self.fallback_failures,
            "unresolved_bundles": self.unresolved_bundles,
            "preserved_unresolved_assertions": self.preserved_unresolved_assertions,
            "destructive_confirmation_calls": self.destructive_confirmation_calls,
            "destructive_confirmation_failures": (
                self.destructive_confirmation_failures
            ),
            "destructive_confirmation_skipped_count": (
                self.destructive_confirmation_skipped_count
            ),
            "destructive_candidate_count": self.destructive_candidate_count,
            "confirmed_quarantine_count": self.confirmed_quarantine_count,
            "preserved_destructive_disagreement_count": (
                self.preserved_destructive_disagreement_count
            ),
            "field_primary_calls": self.field_primary_calls,
            "field_secondary_calls": self.field_secondary_calls,
            "field_primary_positive_hard_count": (
                self.field_primary_positive_hard_count
            ),
            "field_secondary_skipped_count": (
                self.field_secondary_skipped_count
            ),
            "compact_secondary_calls": self.compact_secondary_calls,
            "compact_split_count": self.compact_split_count,
            "compact_truncation_count": self.compact_truncation_count,
            "field_hard_assertion_count": self.field_hard_assertion_count,
            "field_soft_assertion_count": self.field_soft_assertion_count,
            "field_isolated_assertion_count": self.field_isolated_assertion_count,
            "field_reassigned_assertion_count": self.field_reassigned_assertion_count,
            "field_preserved_assertion_count": self.field_preserved_assertion_count,
            "field_shape_normalization_count": (
                self.field_shape_normalization_count
            ),
            "split_retry_eligible": self.split_retry_eligible,
            "retry_count": self.retry_count,
            "capability_fallback_count": self.capability_fallback_count,
            "elapsed_seconds": self.elapsed_seconds,
            "provider_call_seconds": self.provider_call_seconds,
            "failures_by_code": dict(sorted(self.failures_by_code.items())),
        }


@dataclass(frozen=True)
class VerificationClientResult:
    applied: AppliedVerification
    metrics: dict[str, Any]


_CAPABILITY_REGISTRY_LOCK = Lock()
_EFFECTIVE_CAPABILITIES: dict[str, tuple[str, str, str]] = {}
_CAPABILITY_DISCOVERY_LOCKS: dict[str, Lock] = {}


def _capability_key(config: VerifierRoleConfig) -> str:
    return stable_id(
        "capability",
        {
            "model": config.model,
            "endpoint": config.endpoint,
            "configured_thinking_mode": config.thinking_mode,
            "configured_reasoning_effort": config.reasoning_effort,
            "configured_response_mode": config.response_mode,
            "api_mode": config.api_mode,
        },
    )


def _effective_config(config: VerifierRoleConfig) -> VerifierRoleConfig:
    with _CAPABILITY_REGISTRY_LOCK:
        effective = _EFFECTIVE_CAPABILITIES.get(_capability_key(config))
    if effective is None:
        return config
    return replace(
        config,
        thinking_mode=effective[0],
        reasoning_effort=effective[1],
        response_mode=effective[2],
    )


def _capability_discovery_lock(config: VerifierRoleConfig) -> Lock:
    key = _capability_key(config)
    with _CAPABILITY_REGISTRY_LOCK:
        lock = _CAPABILITY_DISCOVERY_LOCKS.get(key)
        if lock is None:
            lock = Lock()
            _CAPABILITY_DISCOVERY_LOCKS[key] = lock
        return lock


def _capability_is_known(config: VerifierRoleConfig) -> bool:
    with _CAPABILITY_REGISTRY_LOCK:
        return _capability_key(config) in _EFFECTIVE_CAPABILITIES


def _remember_effective_capability(
    configured: VerifierRoleConfig,
    effective: VerifierRoleConfig,
) -> None:
    with _CAPABILITY_REGISTRY_LOCK:
        _EFFECTIVE_CAPABILITIES[_capability_key(configured)] = (
            effective.thinking_mode,
            effective.reasoning_effort,
            effective.response_mode,
        )


def _endpoint_identity(raw: str) -> str:
    value = str(raw or "").strip()
    if not value:
        return ""
    parsed = urlsplit(value)
    if not parsed.scheme or not parsed.hostname:
        return value.split("?", 1)[0]
    host = parsed.hostname
    if parsed.port:
        host = f"{host}:{parsed.port}"
    return urlunsplit((parsed.scheme, host, parsed.path.rstrip("/"), "", ""))


def _mode(raw: str) -> Literal["enabled", "disabled", "provider_default"]:
    folded = str(raw or "").strip().casefold()
    if folded in {"enabled", "enable", "on", "true", "1"}:
        return "enabled"
    if folded in {"disabled", "disable", "off", "false", "0"}:
        return "disabled"
    return "provider_default"


def _reasoning_effort(
    raw: str,
) -> Literal["low", "medium", "high", "provider_default"]:
    folded = str(raw or "").strip().casefold()
    if folded in {"low", "medium", "high"}:
        return folded  # type: ignore[return-value]
    return "provider_default"


def _api_mode(raw: str) -> VerifierAPIMode:
    folded = str(raw or "").strip().casefold()
    if folded in {"responses", "response", "responses_api"}:
        return "responses"
    return "chat_completions"


def verifier_configs_from_env() -> tuple[VerifierRoleConfig, VerifierRoleConfig]:
    """Resolve role configuration without interpreting any model name."""

    endpoint = _endpoint_identity(
        os.getenv("LLM_BASE_URL") or os.getenv("OPENAI_BASE_URL") or ""
    )
    common_thinking = _mode(
        os.getenv("KNOWMAT2_ALPHA25_VERIFIER_THINKING", "provider_default")
    )
    common_reasoning_effort = _reasoning_effort(
        os.getenv(
            "KNOWMAT2_ALPHA25_VERIFIER_REASONING_EFFORT", "provider_default"
        )
    )
    response_mode: Literal["json_object", "text"] = (
        "json_object"
        if os.getenv(
            "KNOWMAT2_ALPHA25_VERIFIER_RESPONSE_FORMAT", "json_object"
        ).strip().casefold()
        in {"json", "json_object", "object"}
        else "text"
    )
    common_api_mode = _api_mode(
        os.getenv("KNOWMAT2_ALPHA25_VERIFIER_API_MODE")
        or os.getenv("KNOWMAT2_LLM_API_MODE")
        or "chat_completions"
    )
    fallback_api_mode = _api_mode(
        os.getenv("KNOWMAT2_ALPHA25_VERIFIER_FALLBACK_API_MODE")
        or common_api_mode
    )
    output_tokens = max(
        512, int(os.getenv("KNOWMAT2_ALPHA25_VERIFIER_MAX_TOKENS", "4096"))
    )
    timeout = max(1, int(os.getenv("KNOWMAT2_ALPHA25_VERIFIER_TIMEOUT", "180")))
    retries = max(
        0, int(os.getenv("KNOWMAT2_ALPHA25_VERIFIER_TRANSIENT_RETRIES", "1"))
    )
    primary = VerifierRoleConfig(
        role="primary",
        model=str(
            os.getenv("KNOWMAT2_ALPHA25_VERIFIER_MODEL")
            or settings.extraction_model
        ).strip(),
        endpoint=endpoint,
        thinking_mode=common_thinking,
        reasoning_effort=common_reasoning_effort,
        response_mode=response_mode,
        api_mode=common_api_mode,
        output_token_budget=output_tokens,
        timeout_seconds=timeout,
        transient_retries=retries,
    )
    fallback = VerifierRoleConfig(
        role="fallback",
        model=str(
            os.getenv("KNOWMAT2_ALPHA25_VERIFIER_FALLBACK_MODEL")
            or settings.extraction_model
        ).strip(),
        endpoint=endpoint,
        thinking_mode=_mode(
            os.getenv(
                "KNOWMAT2_ALPHA25_VERIFIER_FALLBACK_THINKING",
                common_thinking,
            )
        ),
        reasoning_effort=_reasoning_effort(
            os.getenv(
                "KNOWMAT2_ALPHA25_VERIFIER_FALLBACK_REASONING_EFFORT",
                # Fallback is a bounded repair role. Low effort prevents
                # reasoning-only completions from consuming the entire JSON
                # budget; unsupported endpoint options fall back generically.
                "low",
            )
        ),
        response_mode=response_mode,
        api_mode=fallback_api_mode,
        output_token_budget=max(
            512,
            int(
                os.getenv(
                    "KNOWMAT2_ALPHA25_VERIFIER_FALLBACK_MAX_TOKENS",
                    str(output_tokens),
                )
            ),
        ),
        timeout_seconds=timeout,
        transient_retries=retries,
    )
    return primary, fallback


def _flatten_content(value: Any) -> str:
    content = getattr(value, "content", value)
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "\n".join(
            str(row.get("text") or row.get("content") or "")
            if isinstance(row, dict)
            else str(row)
            for row in content
        ).strip()
    return str(content or "")


def _json_object(text: str) -> dict[str, Any]:
    payload = str(text or "").strip()
    if payload.startswith("```"):
        payload = re.sub(r"^```(?:json)?\s*", "", payload)
        payload = re.sub(r"\s*```$", "", payload)
    try:
        value = json.loads(payload)
        if isinstance(value, dict):
            return value
    except json.JSONDecodeError:
        pass
    decoder = json.JSONDecoder()
    for match in re.finditer(r"\{", payload):
        try:
            value, _ = decoder.raw_decode(payload[match.start() :])
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict):
            return value
    raise VerificationClientError("invalid_json", "no JSON object in response")


def _provider_option_error(exc: Exception, *names: str) -> bool:
    message = str(exc).casefold()
    return any(name.casefold() in message for name in names) and any(
        signal in message
        for signal in (
            "invalidparameter",
            "invalid parameter",
            "not supported",
            "unsupported",
            "unknown field",
            "extra inputs are not permitted",
        )
    )


def _transient(exc: Exception) -> bool:
    message = str(exc).casefold()
    return bool(re.search(r"\b(?:429|500|502|503|504)\b", message)) or any(
        signal in message
        for signal in (
            "rate limit",
            "timeout",
            "timed out",
            "connection reset",
            "connection error",
            "internal server error",
        )
    )


def _provider_failure_code(exc: Exception) -> str:
    """Classify provider failures without relying on a model name."""

    name = type(exc).__name__.casefold()
    message = str(exc).casefold()
    if "lengthfinishreason" in name or any(
        signal in message
        for signal in ("length limit was reached", "finish_reason='length'")
    ):
        return "output_truncated"
    if "timeout" in name or "timed out" in message or "timeout" in message:
        return "provider_timeout"
    if "ratelimit" in name or "rate limit" in message or re.search(r"\b429\b", message):
        return "provider_rate_limit"
    if "connection" in name or any(
        signal in message for signal in ("connection reset", "connection error")
    ):
        return "provider_connection_error"
    if "badrequest" in name or re.search(r"\b400\b", message):
        return "provider_bad_request"
    if re.search(r"\b(?:500|502|503|504)\b", message):
        return "provider_server_error"
    return "provider_error"


def _default_invoke_json(
    config: VerifierRoleConfig,
    system_prompt: str,
    user_prompt: str,
    *,
    acquire_slot: Callable[[], None],
    release_slot: Callable[[], None],
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Invoke one request with generic capability and transient fallback."""

    thinking = config.thinking_mode
    reasoning_effort = config.reasoning_effort
    response_mode = config.response_mode
    transient_attempt = 0
    capability_fallbacks = 0
    provider_calls = 0
    provider_seconds = 0.0

    def call_metrics() -> dict[str, Any]:
        return {
            "provider_calls": provider_calls,
            "provider_call_seconds": provider_seconds,
            "retry_count": transient_attempt,
            "capability_fallback_count": capability_fallbacks,
            "effective_thinking_mode": thinking,
            "effective_reasoning_effort": reasoning_effort,
            "effective_response_mode": response_mode,
        }

    while True:
        llm = get_llm(
            "extraction",
            model_override=config.model,
            thinking_mode_override=thinking,
            reasoning_effort_override=reasoning_effort,
            request_timeout_override=config.timeout_seconds,
            max_tokens_override=config.output_token_budget,
            max_retries_override=0,
        )
        bind: dict[str, Any] = {"max_tokens": config.output_token_budget}
        if response_mode == "json_object":
            bind["response_format"] = {"type": "json_object"}
        bound = llm.bind(**bind)
        acquire_slot()
        started = time.monotonic()
        provider_time_recorded = False
        try:
            provider_calls += 1
            response = bound.invoke(
                [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ]
            )
        except Exception as exc:
            provider_seconds += time.monotonic() - started
            provider_time_recorded = True
            if thinking != "provider_default" and _provider_option_error(
                exc, "thinking", "coding plan"
            ):
                thinking = "provider_default"
                capability_fallbacks += 1
                continue
            if reasoning_effort != "provider_default" and _provider_option_error(
                exc, "reasoning_effort", "reasoning effort"
            ):
                reasoning_effort = "provider_default"
                capability_fallbacks += 1
                continue
            if response_mode == "json_object" and _provider_option_error(
                exc, "response_format", "json_object", "json mode"
            ):
                response_mode = "text"
                capability_fallbacks += 1
                continue
            if _transient(exc) and transient_attempt < config.transient_retries:
                transient_attempt += 1
                continue
            raise VerificationClientError(
                _provider_failure_code(exc), str(exc), metrics=call_metrics()
            ) from exc
        finally:
            if not provider_time_recorded:
                provider_seconds += time.monotonic() - started
            release_slot()
        metadata = getattr(response, "response_metadata", None) or {}
        finish_reason = str(metadata.get("finish_reason") or "").casefold()
        content = _flatten_content(response)
        if not content.strip():
            raise VerificationClientError("empty_content", metrics=call_metrics())
        if finish_reason in {"length", "max_tokens", "max_output_tokens"}:
            raise VerificationClientError(
                "output_truncated", metrics=call_metrics()
            )
        try:
            value = _json_object(content)
        except VerificationClientError as exc:
            exc.metrics = call_metrics()
            raise
        return value, call_metrics()


def _wire_value(value: Any) -> Any:
    """Convert an SDK response fragment to JSON-compatible audit metadata."""

    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, dict):
        return {str(key): _wire_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_wire_value(item) for item in value]
    for method_name in ("model_dump", "to_dict"):
        method = getattr(value, method_name, None)
        if callable(method):
            try:
                return _wire_value(method())
            except Exception:
                pass
    return str(value)


def _responses_reasoning_summary(response: Any) -> list[Any]:
    """Retain provider reasoning summaries for audit, never decision authority."""

    summaries: list[Any] = []
    for item in getattr(response, "output", None) or []:
        item_type = str(
            getattr(item, "type", None)
            or (item.get("type") if isinstance(item, dict) else "")
        )
        if item_type != "reasoning":
            continue
        summary = (
            getattr(item, "summary", None)
            if not isinstance(item, dict)
            else item.get("summary")
        )
        if summary:
            summaries.extend(
                _wire_value(summary)
                if isinstance(_wire_value(summary), list)
                else [_wire_value(summary)]
            )
    return summaries


def _default_invoke_responses(
    config: VerifierRoleConfig,
    system_prompt: str,
    user_prompt: str,
    *,
    acquire_slot: Callable[[], None],
    release_slot: Callable[[], None],
) -> tuple[str, dict[str, Any]]:
    """Invoke the official Responses client without transport switching.

    Only the standard ``reasoning.effort`` option is optional. If an endpoint
    rejects it, the same Responses transport is retried once without that
    option. Provider failures never fall back to Chat Completions.
    """

    from openai import OpenAI

    api_key = os.getenv("LLM_API_KEY") or os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise VerificationClientError("missing_api_key")

    client_kwargs: dict[str, Any] = {
        "api_key": api_key,
        "timeout": config.timeout_seconds,
        "max_retries": 0,
    }
    if config.endpoint:
        client_kwargs["base_url"] = config.endpoint
    client = OpenAI(**client_kwargs)

    reasoning_effort = config.reasoning_effort
    reasoning_summary = "concise"
    transient_attempt = 0
    capability_fallbacks = 0
    provider_calls = 0
    provider_seconds = 0.0

    def call_metrics(**extra: Any) -> dict[str, Any]:
        return {
            "provider_calls": provider_calls,
            "provider_call_seconds": provider_seconds,
            "retry_count": transient_attempt,
            "capability_fallback_count": capability_fallbacks,
            "effective_thinking_mode": "provider_default",
            "effective_reasoning_effort": reasoning_effort,
            "effective_reasoning_summary": reasoning_summary,
            "effective_response_mode": "text",
            "api_mode": "responses",
            **extra,
        }

    while True:
        request: dict[str, Any] = {
            "model": config.model,
            "input": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "max_output_tokens": config.output_token_budget,
        }
        if reasoning_effort != "provider_default":
            request["reasoning"] = {
                "effort": reasoning_effort,
                **(
                    {"summary": reasoning_summary}
                    if reasoning_summary != "provider_default"
                    else {}
                ),
            }
        acquire_slot()
        started = time.monotonic()
        recorded = False
        try:
            provider_calls += 1
            response = client.responses.create(**request)
        except Exception as exc:
            provider_seconds += time.monotonic() - started
            recorded = True
            if reasoning_summary != "provider_default" and _provider_option_error(
                exc, "summary", "generate_summary"
            ):
                reasoning_summary = "provider_default"
                capability_fallbacks += 1
                continue
            if reasoning_effort != "provider_default" and _provider_option_error(
                exc, "reasoning", "effort"
            ):
                reasoning_effort = "provider_default"
                capability_fallbacks += 1
                continue
            if _transient(exc) and transient_attempt < config.transient_retries:
                transient_attempt += 1
                continue
            raise VerificationClientError(
                _provider_failure_code(exc),
                str(exc),
                metrics=call_metrics(),
            ) from exc
        finally:
            if not recorded:
                provider_seconds += time.monotonic() - started
            release_slot()

        status = str(getattr(response, "status", "") or "")
        incomplete = _wire_value(getattr(response, "incomplete_details", None))
        output_text = str(getattr(response, "output_text", "") or "")
        metadata = call_metrics(
            response_id=str(getattr(response, "id", "") or ""),
            response_status=status,
            incomplete_details=incomplete,
            reasoning_summary=_responses_reasoning_summary(response),
            usage=_wire_value(getattr(response, "usage", None)),
            output_text=output_text,
        )
        if status != "completed":
            reason = str(
                (incomplete or {}).get("reason", "")
                if isinstance(incomplete, dict)
                else incomplete or ""
            ).casefold()
            code = (
                "output_truncated"
                if any(token in reason for token in ("max_output", "length", "token"))
                else "responses_incomplete"
            )
            raise VerificationClientError(code, status or reason, metrics=metadata)
        if not output_text.strip():
            raise VerificationClientError(
                "empty_content", "Responses output_text is empty", metrics=metadata
            )
        return output_text, metadata


def _bundle_prompt(bundle: VerificationBundle) -> str:
    payload = {
        "protocol_version": bundle.protocol_version,
        "bundle_id": bundle.bundle_id,
        "axis": bundle.axis,
        "assertions": [row.model_dump(mode="json") for row in bundle.assertions],
        "inventory_entities": [row.model_dump(mode="json") for row in bundle.entities],
        "evidence": [row.model_dump(mode="json") for row in bundle.evidence],
        "response_shape": {
            "protocol_version": bundle.protocol_version,
            "bundle_id": bundle.bundle_id,
            "decisions": [
                {
                    "assertion_id": "existing assertion_id",
                    "decision": "accept|merge|reassign|quarantine|unresolved",
                    "evidence_ids": ["existing evidence_id"],
                    "reason_code": "UPPER_SNAKE_CASE",
                    "rationale": "short source-grounded reason",
                    "merge_member_ids": [],
                    "survivor_assertion_id": None,
                    "reassignment": None,
                }
            ],
        },
    }
    return canonical_json(payload)


def _field_bundle_prompt(bundle: VerificationBundle) -> str:
    required = {
        row.assertion_id: list(required_scientific_fields(row))
        for row in bundle.assertions
    }
    decisions = []
    for assertion in bundle.assertions:
        decisions.append(
            {
                "assertion_id": assertion.assertion_id,
                "fields": [
                    {
                        "field": field,
                        "verdict": "supported|contradicted|not_proven",
                        "evidence_ids": ["existing evidence_id"],
                        "selected_entity_id": None,
                        "selected_text": None,
                    }
                    for field in required[assertion.assertion_id]
                ],
                "reason_code": "UPPER_SNAKE_CASE",
                "rationale": "short source-grounded reason",
            }
        )
    return canonical_json(
        {
            "protocol_version": FIELD_VERIFICATION_PROTOCOL_VERSION,
            "bundle_id": bundle.bundle_id,
            "axis": bundle.axis,
            "assertions": [
                row.model_dump(mode="json") for row in bundle.assertions
            ],
            "required_fields": required,
            "inventory_entities": [
                row.model_dump(mode="json") for row in bundle.entities
            ],
            "evidence": [row.model_dump(mode="json") for row in bundle.evidence],
            "response_shape": {
                "protocol_version": FIELD_VERIFICATION_PROTOCOL_VERSION,
                "bundle_id": bundle.bundle_id,
                "decisions": decisions,
            },
        }
    )


def _compact_review_prompt(bundle: VerificationBundle) -> str:
    required = {
        row.assertion_id: list(required_scientific_fields(row))
        for row in bundle.assertions
    }
    return canonical_json(
        {
            "protocol_version": COMPACT_REVIEW_PROTOCOL_VERSION,
            "bundle_id": bundle.bundle_id,
            "axis": bundle.axis,
            "assertions": [
                {
                    "assertion_id": row.assertion_id,
                    "required_fields": required[row.assertion_id],
                    "candidate": row.candidate,
                    "evidence_ids": list(row.evidence_ids),
                }
                for row in bundle.assertions
            ],
            "inventory_entities": [
                row.model_dump(mode="json") for row in bundle.entities
            ],
            "evidence": [row.model_dump(mode="json") for row in bundle.evidence],
            "response_shape": {
                "protocol_version": COMPACT_REVIEW_PROTOCOL_VERSION,
                "bundle_id": bundle.bundle_id,
                "decisions": [
                    {
                        "assertion_id": row.assertion_id,
                        "verdict": (
                            "all_fields_supported|contradicted|not_proven"
                        ),
                        "evidence_ids": ["existing evidence_id"],
                        "failed_fields": [],
                        "reason_code": "UPPER_SNAKE_CASE",
                    }
                    for row in bundle.assertions
                ],
            },
        }
    )


def _compact_label_prompt(bundle: VerificationBundle) -> str:
    """Build the blinded, positional secondary-review request."""

    def scientific_candidate(candidate: dict[str, Any]) -> dict[str, Any]:
        def project(value: Any) -> Any:
            if isinstance(value, dict):
                result = {}
                for key, child in value.items():
                    if key in {
                        "confidence",
                        "source_evidence",
                        "evidence_unit_id",
                        "property_id_candidate",
                        "candidate_stage_id",
                        # These are presentation/provenance mirrors of the
                        # immutable evidence span.  Sending them to the
                        # positional label reviewer needlessly duplicates long
                        # OCR/chart prose and increases reasoning truncation
                        # risk; the authoritative text remains in ``evidence``.
                        "original",
                        "simplified",
                        "raw_note",
                        "observation_id",
                    }:
                        continue
                    if key.endswith("_id") and str(child or "") == "temporary":
                        continue
                    result[key] = project(child)
                return result
            if isinstance(value, list):
                return [project(row) for row in value]
            return value

        return project(candidate)

    assertions = []
    for index, row in enumerate(bundle.assertions):
        assertions.append(
            {
                "index": index,
                "required_fields": list(required_scientific_fields(row)),
                "candidate": scientific_candidate(row.candidate),
                "evidence_ids": list(row.evidence_ids),
            }
        )
    return canonical_json(
        {
            "protocol_version": COMPACT_LABEL_REVIEW_PROTOCOL_VERSION,
            "bundle_id": bundle.bundle_id,
            "axis": bundle.axis,
            "label_count": len(assertions),
            "labels": {
                "S": "every required field is supported",
                "C": "at least one required field is contradicted",
                "N": "at least one required field is not proven",
            },
            "assertions": assertions,
            "inventory_entities": [
                row.model_dump(mode="json") for row in bundle.entities
            ],
            "evidence": [row.model_dump(mode="json") for row in bundle.evidence],
            "response_shape": ["S|C|N"] * len(assertions),
        }
    )


def _confirmation_prompt(bundle: VerificationBundle) -> str:
    """Build the smallest complete destructive-consensus request."""

    if len(bundle.assertions) != 1:
        raise ValueError("destructive confirmation must contain one assertion")
    assertion = bundle.assertions[0]
    return canonical_json(
        {
            "protocol_version": bundle.protocol_version,
            "bundle_id": bundle.bundle_id,
            "axis": bundle.axis,
            "assertion": assertion.model_dump(mode="json"),
            "evidence": [row.model_dump(mode="json") for row in bundle.evidence],
            "response_shape": {
                "protocol_version": bundle.protocol_version,
                "bundle_id": bundle.bundle_id,
                "decisions": [
                    {
                        "assertion_id": assertion.assertion_id,
                        "decision": "accept|quarantine|unresolved",
                        "evidence_ids": ["existing evidence_id"],
                        "reason_code": "UPPER_SNAKE_CASE",
                        "rationale": "at most 30 words",
                        "merge_member_ids": [],
                        "survivor_assertion_id": None,
                        "reassignment": None,
                    }
                ],
            },
        }
    )


def _recovery_prompt(request: RecoveryRequest) -> str:
    return canonical_json(
        {
            "protocol_version": request.protocol_version,
            "request_id": request.request_id,
            "uncovered_evidence": [
                row.model_dump(mode="json") for row in request.evidence
            ],
            "inventory_entities": [
                row.model_dump(mode="json") for row in request.entities
            ],
            "response_shape": {
                "protocol_version": request.protocol_version,
                "proposals": [
                    {
                        "proposal_id": "stable request-local ID",
                        "axis": "processing|structure|properties",
                        "candidate": "one complete existing Alpha25 AxisFact wire object",
                        "evidence_ids": ["existing evidence_id"],
                        "reason_code": "UNCOVERED_LITERAL_FACT",
                    }
                ],
            },
        }
    )


def _accumulate_metrics(target: VerificationClientMetrics, raw: dict[str, Any]) -> None:
    for key in (
        "provider_calls",
        "cache_hits",
        "primary_failures",
        "fallback_calls",
        "fallback_failures",
        "unresolved_bundles",
        "preserved_unresolved_assertions",
        "destructive_confirmation_calls",
        "destructive_confirmation_failures",
        "destructive_confirmation_skipped_count",
        "destructive_candidate_count",
        "confirmed_quarantine_count",
        "preserved_destructive_disagreement_count",
        "retry_count",
        "capability_fallback_count",
        "field_primary_calls",
        "field_secondary_calls",
        "field_primary_positive_hard_count",
        "field_secondary_skipped_count",
        "compact_secondary_calls",
        "compact_split_count",
        "compact_truncation_count",
        "field_hard_assertion_count",
        "field_soft_assertion_count",
        "field_isolated_assertion_count",
        "field_reassigned_assertion_count",
        "field_preserved_assertion_count",
        "field_shape_normalization_count",
        "split_retry_eligible",
    ):
        setattr(target, key, getattr(target, key) + int(raw.get(key, 0)))
    target.elapsed_seconds += float(raw.get("elapsed_seconds", 0.0))
    target.provider_call_seconds += float(raw.get("provider_call_seconds", 0.0))
    for code, count in (raw.get("failures_by_code") or {}).items():
        target.failures_by_code[str(code)] = (
            target.failures_by_code.get(str(code), 0) + int(count)
        )


def _record_exception_metrics(
    target: VerificationClientMetrics, exc: Exception
) -> None:
    raw = getattr(exc, "metrics", None)
    if not isinstance(raw, dict):
        return
    target.provider_calls += int(raw.get("provider_calls", 0))
    target.provider_call_seconds += float(raw.get("provider_call_seconds", 0.0))
    target.retry_count += int(raw.get("retry_count", 0))
    target.capability_fallback_count += int(
        raw.get("capability_fallback_count", 0)
    )


def _split_retryable_error(exc: Exception | None) -> bool:
    """Return whether a smaller request can plausibly fix this failure.

    Scientific grounding and response-contract disagreements are deterministic
    for the same assertion and must never trigger repeated provider calls.
    """

    if exc is None:
        return False
    if isinstance(exc, (VerificationGroundingError, ValueError)):
        return False
    code = str(getattr(exc, "code", "") or _provider_failure_code(exc))
    return code in {
        "empty_content",
        "invalid_json",
        "output_truncated",
        "provider_connection_error",
        "provider_error",
        "provider_rate_limit",
        "provider_server_error",
        "provider_timeout",
    }


def _normalize_field_response_shape(
    value: dict[str, Any],
    bundle: VerificationBundle | None = None,
) -> tuple[dict[str, Any], tuple[dict[str, Any], ...]]:
    """Remove only correction targets that cannot affect the declared verdict.

    Providers sometimes copy an entity selection into every field.  A target
    attached to ``supported`` or ``not_proven`` is forbidden and semantically
    inactive, so dropping it is a response-shape repair rather than a
    scientific edit.  The complete repair record is persisted in cache and
    copied into the paper audit.
    """

    normalized = json.loads(json.dumps(value, ensure_ascii=False))
    records: list[dict[str, Any]] = []
    decisions = normalized.get("decisions")
    if not isinstance(decisions, list):
        return normalized, ()
    for decision in decisions:
        if not isinstance(decision, dict):
            continue
        assertion_id = str(decision.get("assertion_id") or "")
        fields = decision.get("fields")
        if not isinstance(fields, list):
            continue
        for row in fields:
            if not isinstance(row, dict) or row.get("verdict") not in {
                "supported",
                "not_proven",
            }:
                continue
            selected_entity_id = row.get("selected_entity_id")
            selected_text = row.get("selected_text")
            if selected_entity_id is None and selected_text is None:
                continue
            records.append(
                {
                    "code": "inactive_correction_target_removed",
                    "assertion_id": assertion_id,
                    "field": str(row.get("field") or ""),
                    "verdict": str(row.get("verdict") or ""),
                    "selected_entity_id": selected_entity_id,
                    "selected_text": selected_text,
                }
            )
            row["selected_entity_id"] = None
            row["selected_text"] = None
    if bundle is None:
        return normalized, tuple(records)

    assertions = {row.assertion_id: row for row in bundle.assertions}
    evidence_by_id = {row.evidence_id: row for row in bundle.evidence}
    for decision in decisions:
        if not isinstance(decision, dict):
            continue
        assertion_id = str(decision.get("assertion_id") or "")
        assertion = assertions.get(assertion_id)
        fields = decision.get("fields")
        if assertion is None or not isinstance(fields, list):
            continue
        data = assertion.candidate.get("data")
        data = data if isinstance(data, dict) else {}
        related_ids = set(assertion.evidence_ids)
        asserted_owner = assertion.sample_id_raw.strip().casefold()
        asserted_state = str(
            data.get("material_state") or data.get("state_raw") or ""
        ).strip().casefold()
        for entity in bundle.entities:
            if (
                str(entity.sample_id_raw or "").strip().casefold()
                == asserted_owner
                or asserted_state
                and str(entity.state_raw or "").strip().casefold()
                == asserted_state
            ):
                related_ids.update(entity.evidence_ids)
        for row in fields:
            if not isinstance(row, dict) or row.get("verdict") != "supported":
                continue
            field_name = str(row.get("field") or "")
            if field_name in {"value", "unit", "condition"}:
                literals = list(_scientific_field_literals(data, field_name))
            elif field_name == "owner":
                literals = [assertion.sample_id_raw]
            elif field_name == "state":
                literals = [
                    str(data.get("material_state") or data.get("state_raw") or "")
                ]
            elif field_name == "specimen":
                literals = [str(data.get("test_specimen_raw") or "")]
            else:
                continue
            cited_ids = [
                str(evidence_id)
                for evidence_id in row.get("evidence_ids") or []
                if str(evidence_id) in evidence_by_id
            ]
            if not cited_ids and assertion.evidence_ids:
                chosen = sorted(
                    (
                        evidence_id
                        for evidence_id in assertion.evidence_ids
                        if evidence_id in evidence_by_id
                    ),
                    key=lambda evidence_id: (
                        len(evidence_by_id[evidence_id].text),
                        evidence_id,
                    ),
                )
                if chosen:
                    cited_ids = [chosen[0]]
                    row["evidence_ids"] = cited_ids
                    records.append(
                        {
                            "code": "empty_evidence_citation_completed",
                            "assertion_id": assertion_id,
                            "field": field_name,
                            "added_evidence_ids": cited_ids,
                        }
                    )
            if not set(cited_ids) & related_ids:
                continue
            cited_text = "\n".join(
                evidence_by_id[evidence_id].text for evidence_id in cited_ids
            )
            added_ids: list[str] = []
            completed_literals: list[str] = []
            for literal in [value for value in literals if str(value).strip()]:
                if _literal_coordinate_in_evidence(str(literal), cited_text):
                    continue
                matches = [
                    evidence_id
                    for evidence_id, evidence in evidence_by_id.items()
                    if _literal_coordinate_in_evidence(
                        str(literal), evidence.text
                    )
                ]
                if not matches:
                    continue
                chosen = sorted(
                    matches,
                    key=lambda evidence_id: (
                        evidence_id not in related_ids,
                        len(evidence_by_id[evidence_id].text),
                        evidence_id,
                    ),
                )[0]
                if chosen not in cited_ids:
                    cited_ids.append(chosen)
                    added_ids.append(chosen)
                cited_text += "\n" + evidence_by_id[chosen].text
                completed_literals.append(str(literal))
            if added_ids:
                row["evidence_ids"] = sorted(set(cited_ids))
                records.append(
                    {
                        "code": "literal_evidence_citation_completed",
                        "assertion_id": assertion_id,
                        "field": field_name,
                        "added_evidence_ids": sorted(set(added_ids)),
                        "completed_literals": completed_literals,
                    }
                )
    return normalized, tuple(records)


def _partition_valid_field_decisions(
    bundle: VerificationBundle,
    response: FieldVerificationResponse,
) -> tuple[dict[str, Any], dict[str, str]]:
    """Validate each assertion independently after bundle-envelope checks."""

    assertion_ids = {row.assertion_id for row in bundle.assertions}
    decision_ids = {row.assertion_id for row in response.decisions}
    if (
        response.protocol_version != FIELD_VERIFICATION_PROTOCOL_VERSION
        or response.bundle_id != bundle.bundle_id
        or assertion_ids != decision_ids
    ):
        # Reuse the canonical validator for the precise global error.
        validate_field_response(bundle, response)
    assertions = {row.assertion_id: row for row in bundle.assertions}
    valid: dict[str, Any] = {}
    errors: dict[str, str] = {}
    for decision in response.decisions:
        assertion_id = decision.assertion_id
        singleton_bundle = bundle.model_copy(
            update={"assertions": [assertions[assertion_id]]}
        )
        singleton_response = response.model_copy(update={"decisions": [decision]})
        try:
            valid.update(
                validate_field_response(singleton_bundle, singleton_response)
            )
        except Exception as exc:
            errors[assertion_id] = str(exc)
    return valid, errors


def _partition_valid_compact_decisions(
    bundle: VerificationBundle,
    response: CompactReviewResponse,
) -> tuple[dict[str, CompactReviewDecision], dict[str, str]]:
    """Validate compact decisions independently after envelope checks."""

    assertion_ids = {row.assertion_id for row in bundle.assertions}
    decision_ids = {row.assertion_id for row in response.decisions}
    if (
        response.protocol_version != COMPACT_REVIEW_PROTOCOL_VERSION
        or response.bundle_id != bundle.bundle_id
        or assertion_ids != decision_ids
    ):
        validate_compact_review_response(bundle, response)
    assertions = {row.assertion_id: row for row in bundle.assertions}
    valid: dict[str, CompactReviewDecision] = {}
    errors: dict[str, str] = {}
    for decision in response.decisions:
        assertion_id = decision.assertion_id
        singleton_bundle = bundle.model_copy(
            update={"assertions": [assertions[assertion_id]]}
        )
        singleton_response = response.model_copy(
            update={"decisions": [decision]}
        )
        try:
            valid.update(
                validate_compact_review_response(
                    singleton_bundle, singleton_response
                )
            )
        except Exception as exc:
            errors[assertion_id] = str(exc)
    return valid, errors


class VerificationClient:
    """Verify bundles with primary/fallback roles and content-addressed cache."""

    def __init__(
        self,
        primary: VerifierRoleConfig,
        fallback: VerifierRoleConfig,
        *,
        cache_dir: Path | None = None,
        invoke_json: InvokeJSON | None = None,
        invoke_responses: InvokeResponses | None = None,
        acquire_slot: Callable[[], None] | None = None,
        release_slot: Callable[[], None] | None = None,
        destructive_consensus: bool = False,
        field_level: bool = False,
        confirmation_timeout_seconds: int | None = None,
        confirmation_output_token_budget: int | None = None,
        confirmation_reasoning_effort: str | None = None,
        compact_output_token_budget: int | None = None,
        compact_split_limit: int | None = None,
    ) -> None:
        self.primary = primary
        self.fallback = fallback
        self.cache_dir = cache_dir
        self.acquire_slot = acquire_slot or (lambda: None)
        self.release_slot = release_slot or (lambda: None)
        self.destructive_consensus = bool(destructive_consensus)
        self.field_level = bool(field_level)
        configured_confirmation_timeout = (
            confirmation_timeout_seconds
            if confirmation_timeout_seconds is not None
            else int(
                os.getenv("KNOWMAT2_ALPHA25_VERIFIER_CONFIRMATION_TIMEOUT") or "0"
            )
        )
        self.confirmation_timeout_seconds = (
            max(1, int(configured_confirmation_timeout))
            if configured_confirmation_timeout
            else None
        )
        configured_confirmation_tokens = (
            confirmation_output_token_budget
            if confirmation_output_token_budget is not None
            else int(
                os.getenv("KNOWMAT2_ALPHA25_VERIFIER_CONFIRMATION_MAX_TOKENS")
                or "1536"
            )
        )
        self.confirmation_output_token_budget = max(
            512, int(configured_confirmation_tokens)
        )
        configured_confirmation_reasoning = (
            confirmation_reasoning_effort
            if confirmation_reasoning_effort is not None
            else os.getenv(
                "KNOWMAT2_ALPHA25_VERIFIER_CONFIRMATION_REASONING_EFFORT",
                "low",
            )
        )
        self.confirmation_reasoning_effort = _reasoning_effort(
            configured_confirmation_reasoning
        )
        configured_compact_tokens = (
            compact_output_token_budget
            if compact_output_token_budget is not None
            else int(
                os.getenv("KNOWMAT2_ALPHA25_VERIFIER_COMPACT_MAX_TOKENS")
                or "1024"
            )
        )
        self.compact_output_token_budget = max(
            256, int(configured_compact_tokens)
        )
        configured_compact_splits = (
            compact_split_limit
            if compact_split_limit is not None
            else int(
                os.getenv("KNOWMAT2_ALPHA25_VERIFIER_COMPACT_SPLIT_LIMIT")
                or "1"
            )
        )
        self.compact_split_limit = max(0, int(configured_compact_splits))
        if invoke_json is None:
            self.invoke_json: InvokeJSON = lambda config, system, user: _default_invoke_json(
                config,
                system,
                user,
                acquire_slot=self.acquire_slot,
                release_slot=self.release_slot,
            )
        else:
            self.invoke_json = invoke_json
        if invoke_responses is None:
            self.invoke_responses: InvokeResponses = (
                lambda config, system, user: _default_invoke_responses(
                    config,
                    system,
                    user,
                    acquire_slot=self.acquire_slot,
                    release_slot=self.release_slot,
                )
            )
        else:
            self.invoke_responses = invoke_responses

    def _compact_config(self) -> VerifierRoleConfig:
        return replace(
            self.fallback,
            output_token_budget=self.compact_output_token_budget,
        )

    def _confirmation_config(
        self, config: VerifierRoleConfig
    ) -> VerifierRoleConfig:
        return replace(
            config,
            timeout_seconds=(
                self.confirmation_timeout_seconds
                if self.confirmation_timeout_seconds is not None
                else config.timeout_seconds
            ),
            # Confirmation is a separate provider role and request contract.
            # Its configured budget must not be silently capped by the
            # primary bundle budget; some endpoints need a larger generation
            # allowance even when the validated JSON itself is tiny.
            output_token_budget=self.confirmation_output_token_budget,
            reasoning_effort=(
                self.confirmation_reasoning_effort
                if self.confirmation_reasoning_effort != "provider_default"
                else config.reasoning_effort
            ),
        )

    @staticmethod
    def _destructive_subset(
        bundle: VerificationBundle,
        assertion_ids: set[str],
        *,
        cited_evidence_ids: set[str] | None = None,
    ) -> VerificationBundle:
        assertions = [
            row for row in bundle.assertions if row.assertion_id in assertion_ids
        ]
        assertion_evidence_ids = {
            evidence_id
            for assertion in assertions
            for evidence_id in assertion.evidence_ids
        }
        sibling_evidence_ids = {
            evidence_id
            for assertion in bundle.assertions
            if assertion.assertion_id not in assertion_ids
            for evidence_id in assertion.evidence_ids
        }
        required_ids = assertion_evidence_ids | (
            set(cited_evidence_ids or ()) - sibling_evidence_ids
        )
        evidence_by_id = {row.evidence_id: row for row in bundle.evidence}
        required_spans = [
            evidence_by_id[evidence_id]
            for evidence_id in required_ids
            if evidence_id in evidence_by_id
        ]
        owner_labels = {row.sample_id_raw.casefold() for row in assertions}
        entities = [
            row
            for row in bundle.entities
            if row.sample_id_raw.casefold() in owner_labels
            or set(row.evidence_ids) & required_ids
        ]
        entity_evidence_ids = {
            evidence_id for row in entities for evidence_id in row.evidence_ids
        }

        def relevant(row: Any) -> bool:
            if row.evidence_id in required_ids | entity_evidence_ids:
                return True
            if row.kind != "context":
                return False
            return any(
                row.start_char < span.end_char and row.end_char > span.start_char
                for span in required_spans
            )

        evidence = sorted(
            (row for row in bundle.evidence if relevant(row)),
            key=lambda row: (row.start_char, row.kind, row.evidence_id),
        )
        selected_ids = {row.evidence_id for row in evidence}
        entities = [
            row for row in entities if set(row.evidence_ids) <= selected_ids
        ]
        payload = {
            "parent_bundle_id": bundle.bundle_id,
            "purpose": "independent_destructive_confirmation",
            "assertion_ids": sorted(assertion_ids),
            "evidence_ids": sorted(row.evidence_id for row in evidence),
        }
        return VerificationBundle(
            protocol_version=bundle.protocol_version,
            bundle_id=stable_id("bundle_confirm", payload),
            axis=bundle.axis,
            assertions=assertions,
            entities=entities,
            evidence=evidence,
            source_char_count=sum(len(row.text) for row in evidence),
        )

    @staticmethod
    def _field_review_subset(
        bundle: VerificationBundle,
        assertion_id: str,
    ) -> VerificationBundle:
        """Build one blind-review request with only assertion-local context."""

        subset = VerificationClient._destructive_subset(
            bundle,
            {assertion_id},
        )
        assertion = subset.assertions[0]
        evidence_by_id = {row.evidence_id: row for row in subset.evidence}
        assertion_spans = [
            evidence_by_id[evidence_id]
            for evidence_id in assertion.evidence_ids
            if evidence_id in evidence_by_id
        ]
        assertion_center = (
            sum((row.start_char + row.end_char) / 2 for row in assertion_spans)
            / len(assertion_spans)
            if assertion_spans
            else 0.0
        )
        candidate_data = assertion.candidate.get("data")
        candidate_data = candidate_data if isinstance(candidate_data, dict) else {}
        candidate_state = str(
            candidate_data.get("material_state")
            or candidate_data.get("state_raw")
            or ""
        ).strip().casefold()

        def entity_score(entity: Any) -> tuple[int, int, int, float, str]:
            spans = [
                evidence_by_id[evidence_id]
                for evidence_id in entity.evidence_ids
                if evidence_id in evidence_by_id
            ]
            distance = min(
                (
                    abs((row.start_char + row.end_char) / 2 - assertion_center)
                    for row in spans
                ),
                default=float("inf"),
            )
            return (
                0
                if set(entity.evidence_ids) & set(assertion.evidence_ids)
                else 1,
                0
                if candidate_state
                and str(entity.state_raw or "").strip().casefold()
                == candidate_state
                else 1,
                len(entity.evidence_ids),
                distance,
                entity.entity_id,
            )

        selected_entities = sorted(subset.entities, key=entity_score)[
            : 2 if candidate_state else 1
        ]
        retained_ids = set(assertion.evidence_ids)
        retained_ids.update(
            row.evidence_id for row in subset.evidence if row.kind == "context"
        )
        retained_ids.update(
            evidence_id
            for entity in selected_entities
            for evidence_id in entity.evidence_ids
        )
        retained_evidence = [
            row for row in subset.evidence if row.evidence_id in retained_ids
        ]
        retained_evidence_ids = {row.evidence_id for row in retained_evidence}
        selected_entities = [
            row
            for row in selected_entities
            if set(row.evidence_ids) <= retained_evidence_ids
        ]
        subset = subset.model_copy(
            update={
                "entities": selected_entities,
                "evidence": retained_evidence,
                "source_char_count": sum(
                    len(row.text) for row in retained_evidence
                ),
            }
        )
        payload = {
            "parent_bundle_id": bundle.bundle_id,
            "purpose": "independent_field_review",
            "assertion_id": assertion_id,
            "evidence_ids": sorted(
                row.evidence_id for row in subset.evidence
            ),
            "entity_ids": sorted(row.entity_id for row in subset.entities),
        }
        return subset.model_copy(
            update={"bundle_id": stable_id("bundle_field_review", payload)}
        )

    @staticmethod
    def _compact_review_subset(
        bundle: VerificationBundle,
        assertion_ids: set[str],
    ) -> VerificationBundle:
        """Build one blinded compact-review bundle from original source inputs."""

        subset = VerificationClient._destructive_subset(
            bundle,
            assertion_ids,
        )
        payload = {
            "parent_bundle_id": bundle.bundle_id,
            "purpose": "compact_independent_field_review",
            "assertion_ids": sorted(assertion_ids),
            "evidence_ids": sorted(
                row.evidence_id for row in subset.evidence
            ),
            "entity_ids": sorted(row.entity_id for row in subset.entities),
        }
        return subset.model_copy(
            update={"bundle_id": stable_id("bundle_compact_review", payload)}
        )

    @staticmethod
    def _label_review_subset(
        bundle: VerificationBundle,
        assertion_ids: set[str],
    ) -> VerificationBundle:
        """Build a minimal independent label request from source authorities."""

        base = VerificationClient._destructive_subset(bundle, assertion_ids)
        evidence_by_id = {row.evidence_id: row for row in base.evidence}
        selected_entities: dict[str, Any] = {}
        retained_ids: set[str] = set()
        for assertion in base.assertions:
            assertion_ids_set = set(assertion.evidence_ids)
            retained_ids.update(assertion_ids_set)
            assertion_spans = [
                evidence_by_id[evidence_id]
                for evidence_id in assertion.evidence_ids
                if evidence_id in evidence_by_id
            ]
            center = (
                sum((row.start_char + row.end_char) / 2 for row in assertion_spans)
                / len(assertion_spans)
                if assertion_spans
                else 0.0
            )
            data = assertion.candidate.get("data")
            data = data if isinstance(data, dict) else {}
            state = str(
                data.get("material_state") or data.get("state_raw") or ""
            ).strip().casefold()
            owner_entities = [
                row
                for row in base.entities
                if row.sample_id_raw.strip().casefold()
                == assertion.sample_id_raw.strip().casefold()
            ]

            def entity_score(entity: Any) -> tuple[int, int, int, float, str]:
                spans = [
                    evidence_by_id[evidence_id]
                    for evidence_id in entity.evidence_ids
                    if evidence_id in evidence_by_id
                ]
                return (
                    0 if set(entity.evidence_ids) & assertion_ids_set else 1,
                    0
                    if state
                    and str(entity.state_raw or "").strip().casefold() == state
                    else 1,
                    sum(len(row.text) for row in spans),
                    min(
                        (
                            abs((row.start_char + row.end_char) / 2 - center)
                            for row in spans
                        ),
                        default=float("inf"),
                    ),
                    entity.entity_id,
                )

            for entity in sorted(owner_entities, key=entity_score)[
                : 2 if state else 1
            ]:
                # Keep only compact owner anchors.  Context spans can contain
                # an entire paragraph/table and are already represented by the
                # assertion's immutable evidence; including them here makes a
                # supposedly tiny label request balloon without adding an
                # independent ownership signal.
                owner_evidence_ids = tuple(
                    evidence_id
                    for evidence_id in entity.evidence_ids
                    if (
                        evidence_id in evidence_by_id
                        and evidence_by_id[evidence_id].kind
                        in {"anchor", "assertion"}
                    )
                )
                if owner_evidence_ids:
                    selected_entities[entity.entity_id] = entity.model_copy(
                        update={"evidence_ids": list(owner_evidence_ids)}
                    )
                    retained_ids.update(owner_evidence_ids)

        evidence = sorted(
            (
                row
                for row in base.evidence
                if row.evidence_id in retained_ids
            ),
            key=lambda row: (row.start_char, row.kind, row.evidence_id),
        )
        available_ids = {row.evidence_id for row in evidence}
        entities = sorted(
            (
                row
                for row in selected_entities.values()
                if set(row.evidence_ids) <= available_ids
            ),
            key=lambda row: row.entity_id,
        )
        payload = {
            "parent_bundle_id": bundle.bundle_id,
            "purpose": "minimal_compact_label_review",
            "assertion_ids": [row.assertion_id for row in base.assertions],
            "evidence_ids": [row.evidence_id for row in evidence],
            "entity_ids": [row.entity_id for row in entities],
        }
        return base.model_copy(
            update={
                "bundle_id": stable_id("bundle_label_review", payload),
                "entities": entities,
                "evidence": evidence,
                "source_char_count": sum(len(row.text) for row in evidence),
            }
        )

    @staticmethod
    def _combine_destructive_consensus(
        bundle: VerificationBundle,
        inventory: VerificationInventory,
        primary_applied: AppliedVerification,
        primary_response: VerificationResponse,
        confirmation_bundle: VerificationBundle,
        confirmation_response: VerificationResponse | None,
        *,
        confirmation_cache_hit: bool,
        confirmation_error: Exception | None,
    ) -> tuple[AppliedVerification, int, int]:
        primary_decisions = {
            row.assertion_id: row for row in primary_response.decisions
        }
        confirmation_decisions = {
            row.assertion_id: row
            for row in (
                confirmation_response.decisions
                if confirmation_response is not None
                else []
            )
        }
        destructive_ids = {
            assertion_id
            for assertion_id, decision in primary_decisions.items()
            if decision.decision == "quarantine"
        }
        confirmed_ids = {
            assertion_id
            for assertion_id in destructive_ids
            if confirmation_decisions.get(assertion_id) is not None
            and confirmation_decisions[assertion_id].decision == "quarantine"
        }
        preserved_ids = destructive_ids - confirmed_ids

        primary_audits = {
            str(row.get("assertion_id")): dict(row)
            for row in primary_applied.audit_records
        }
        primary_issues = {
            str((row.get("actual") or {}).get("assertion_id")): dict(row)
            for row in primary_applied.issues
        }
        primary_accepted = dict(
            zip(
                primary_applied.accepted_assertion_ids,
                primary_applied.accepted,
            )
        )
        preserved = preserve_failed_bundle_result(
            VerificationClient._destructive_subset(bundle, preserved_ids),
            inventory,
            reason_code=(
                "DESTRUCTIVE_CONFIRMATION_FAILED"
                if confirmation_error is not None
                else "DESTRUCTIVE_DECISION_NOT_CONFIRMED"
            ),
            rationale=(
                "The independent destructive confirmation failed; the promoted "
                "candidate is preserved pending review."
                if confirmation_error is not None
                else "The independently configured roles did not both quarantine "
                "this candidate; it is preserved pending review."
            ),
            fallback_used=True,
        ) if preserved_ids else AppliedVerification(
            accepted=(),
            audit_records=(),
            issues=(),
            decided_assertion_ids=(),
            accepted_assertion_ids=(),
        )
        preserved_audits = {
            str(row.get("assertion_id")): dict(row)
            for row in preserved.audit_records
        }
        preserved_issues = {
            str((row.get("actual") or {}).get("assertion_id")): dict(row)
            for row in preserved.issues
        }
        preserved_accepted = dict(
            zip(preserved.accepted_assertion_ids, preserved.accepted)
        )

        accepted_by_id = {**primary_accepted, **preserved_accepted}
        audits: list[dict[str, Any]] = []
        issues: list[dict[str, Any]] = []
        for envelope in sorted(bundle.assertions, key=lambda row: row.assertion_id):
            assertion_id = envelope.assertion_id
            primary_decision = primary_decisions[assertion_id]
            confirmation_decision = confirmation_decisions.get(assertion_id)
            confirmation_audit = {
                "bundle_id": confirmation_bundle.bundle_id,
                "verifier_role": (
                    "fallback"
                    if primary_audits[assertion_id].get("verifier_role") == "primary"
                    else "primary"
                ),
                "decision": (
                    confirmation_decision.decision
                    if confirmation_decision is not None
                    else "technical_failure"
                ),
                "reason_code": (
                    confirmation_decision.reason_code
                    if confirmation_decision is not None
                    else getattr(confirmation_error, "code", type(confirmation_error).__name__)
                    if confirmation_error is not None
                    else "MISSING_CONFIRMATION"
                ),
                "evidence_ids": (
                    list(confirmation_decision.evidence_ids)
                    if confirmation_decision is not None
                    else []
                ),
                "rationale": (
                    confirmation_decision.rationale
                    if confirmation_decision is not None
                    else str(confirmation_error or "No confirmation response")
                ),
                "cache_hit": confirmation_cache_hit,
            }
            if assertion_id in preserved_ids:
                audit = preserved_audits[assertion_id]
                audit["proposed_destructive_decision"] = {
                    "decision": primary_decision.decision,
                    "reason_code": primary_decision.reason_code,
                    "evidence_ids": list(primary_decision.evidence_ids),
                    "rationale": primary_decision.rationale,
                }
                audit["secondary_confirmation"] = confirmation_audit
                audits.append(audit)
                issues.append(preserved_issues[assertion_id])
                continue
            audit = primary_audits[assertion_id]
            if assertion_id in confirmed_ids:
                audit["secondary_confirmation"] = confirmation_audit
                issue = primary_issues.get(assertion_id)
                if issue is not None:
                    issue["code"] = "verifier_quarantine_consensus"
                    issues.append(issue)
            else:
                issue = primary_issues.get(assertion_id)
                if issue is not None:
                    issues.append(issue)
            audits.append(audit)

        accepted_rows = [
            (row.assertion_id, accepted_by_id[row.assertion_id])
            for row in sorted(bundle.assertions, key=lambda item: item.assertion_id)
            if row.assertion_id in accepted_by_id
        ]
        return (
            AppliedVerification(
                accepted=tuple(row[1] for row in accepted_rows),
                audit_records=tuple(audits),
                issues=tuple(issues),
                decided_assertion_ids=tuple(
                    sorted(row.assertion_id for row in bundle.assertions)
                ),
                accepted_assertion_ids=tuple(row[0] for row in accepted_rows),
            ),
            len(confirmed_ids),
            len(preserved_ids),
        )

    def _confirm_destructive_individually(
        self,
        bundle: VerificationBundle,
        inventory: VerificationInventory,
        applied: AppliedVerification,
        response: VerificationResponse,
        metrics: VerificationClientMetrics,
        *,
        origin_role: VerifierRole,
        origin_fallback_used: bool,
        origin_cache_hit: bool,
        confirmation_config: VerifierRoleConfig,
        confirmation_role: VerifierRole,
        confirmation_unavailable_error: Exception | None = None,
    ) -> AppliedVerification:
        """Confirm each proposed deletion independently.

        A malformed or timed-out multi-assertion confirmation must not cause
        every destructive candidate in that request to be preserved together.
        Singleton confirmation also keeps the decision contract small while
        retaining the original bounded evidence context.
        """

        decisions = {row.assertion_id: row for row in response.decisions}
        destructive_ids = sorted(
            assertion_id
            for assertion_id, decision in decisions.items()
            if decision.decision == "quarantine"
        )
        metrics.destructive_candidate_count += len(destructive_ids)

        accepted_by_id = dict(
            zip(applied.accepted_assertion_ids, applied.accepted)
        )
        audit_by_id = {
            str(row.get("assertion_id")): dict(row) for row in applied.audit_records
        }
        issue_by_id = {
            str((row.get("actual") or {}).get("assertion_id")): dict(row)
            for row in applied.issues
        }

        for assertion_id in destructive_ids:
            confirmation_bundle = self._destructive_subset(
                bundle,
                {assertion_id},
                cited_evidence_ids=set(decisions[assertion_id].evidence_ids),
            )
            confirmation_evidence_ids = {
                row.evidence_id for row in confirmation_bundle.evidence
            }
            origin_evidence_ids = [
                evidence_id
                for evidence_id in decisions[assertion_id].evidence_ids
                if evidence_id in confirmation_evidence_ids
            ]
            if not origin_evidence_ids:
                origin_evidence_ids = list(
                    confirmation_bundle.assertions[0].evidence_ids
                )
            origin_decision = decisions[assertion_id].model_copy(
                update={
                    "evidence_ids": origin_evidence_ids
                }
            )
            origin_response = VerificationResponse(
                protocol_version=response.protocol_version,
                bundle_id=confirmation_bundle.bundle_id,
                decisions=[origin_decision],
            )
            origin_applied = validate_and_apply_bundle(
                confirmation_bundle,
                origin_response,
                inventory,
                verifier_role=origin_role,
                fallback_used=origin_fallback_used,
                cache_hit=origin_cache_hit,
            )
            confirmation_response: VerificationResponse | None = None
            confirmation_cache_hit = False
            confirmation_error: Exception | None = confirmation_unavailable_error
            if confirmation_unavailable_error is not None:
                # The scientific confirmation role has already failed on this
                # bundle. Calling it again cannot establish independent
                # consensus and caused repeated full-budget truncations in
                # production. Preserve the fallback proposal for review.
                metrics.destructive_confirmation_skipped_count += 1
            else:
                metrics.destructive_confirmation_calls += 1
                try:
                    confirmation_response, confirmation_cache_hit = self._load_or_call(
                        self._confirmation_config(confirmation_config),
                        confirmation_bundle,
                        metrics,
                        system_prompt=CONFIRMATION_SYSTEM_PROMPT,
                        user_prompt=_confirmation_prompt(confirmation_bundle),
                        request_kind="destructive_confirmation",
                    )
                    validate_and_apply_bundle(
                        confirmation_bundle,
                        confirmation_response,
                        inventory,
                        verifier_role=confirmation_role,
                        fallback_used=confirmation_role == "fallback",
                        cache_hit=confirmation_cache_hit,
                    )
                except Exception as exc:
                    confirmation_error = exc
                    _record_exception_metrics(metrics, exc)
                    metrics.destructive_confirmation_failures += 1
                    metrics.record_failure(
                        getattr(exc, "code", exc.__class__.__name__)
                    )

            combined, confirmed, preserved = self._combine_destructive_consensus(
                confirmation_bundle,
                inventory,
                origin_applied,
                origin_response,
                confirmation_bundle,
                confirmation_response,
                confirmation_cache_hit=confirmation_cache_hit,
                confirmation_error=confirmation_error,
            )
            metrics.confirmed_quarantine_count += confirmed
            metrics.preserved_destructive_disagreement_count += preserved
            metrics.preserved_unresolved_assertions += preserved
            accepted_by_id.pop(assertion_id, None)
            accepted_by_id.update(
                zip(combined.accepted_assertion_ids, combined.accepted)
            )
            for row in combined.audit_records:
                audit_by_id[str(row.get("assertion_id"))] = dict(row)
            issue_by_id.pop(assertion_id, None)
            for row in combined.issues:
                issue_by_id[
                    str((row.get("actual") or {}).get("assertion_id"))
                ] = dict(row)

        ordered_ids = sorted(row.assertion_id for row in bundle.assertions)
        return AppliedVerification(
            accepted=tuple(
                accepted_by_id[assertion_id]
                for assertion_id in ordered_ids
                if assertion_id in accepted_by_id
            ),
            audit_records=tuple(audit_by_id[assertion_id] for assertion_id in ordered_ids),
            issues=tuple(
                issue_by_id[assertion_id]
                for assertion_id in ordered_ids
                if assertion_id in issue_by_id
            ),
            decided_assertion_ids=tuple(ordered_ids),
            accepted_assertion_ids=tuple(
                assertion_id
                for assertion_id in ordered_ids
                if assertion_id in accepted_by_id
            ),
        )

    def _cache_identity(
        self,
        config: VerifierRoleConfig,
        bundle: VerificationBundle,
        *,
        system_prompt: str = SYSTEM_PROMPT,
        request_kind: str = "verification",
    ) -> dict[str, Any]:
        configured = self.primary if config.role == "primary" else self.fallback
        identity = {
            "protocol_version": VERIFICATION_PROTOCOL_VERSION,
            "role_config": {
                "configured": configured.identity(),
                "effective": config.identity(),
            },
            "bundle": bundle.model_dump(mode="json"),
            "system_prompt": system_prompt,
        }
        # Preserve compatibility with already-sealed ordinary verification
        # caches. A distinct kind is needed only for the new compact
        # confirmation protocol, whose prompt and authority differ.
        if request_kind != "verification":
            identity["request_kind"] = request_kind
        return identity

    def _cache_path(
        self,
        config: VerifierRoleConfig,
        bundle: VerificationBundle,
        *,
        system_prompt: str = SYSTEM_PROMPT,
        request_kind: str = "verification",
    ) -> Path | None:
        if self.cache_dir is None:
            return None
        identity = self._cache_identity(
            config,
            bundle,
            system_prompt=system_prompt,
            request_kind=request_kind,
        )
        return self.cache_dir / config.role / f"{stable_id('verify', identity)}.json"

    def _load_or_call(
        self,
        config: VerifierRoleConfig,
        bundle: VerificationBundle,
        metrics: VerificationClientMetrics,
        *,
        system_prompt: str = SYSTEM_PROMPT,
        user_prompt: str | None = None,
        request_kind: str = "verification",
    ) -> tuple[VerificationResponse, bool]:
        configured = config
        guard = (
            nullcontext()
            if _capability_is_known(configured)
            else _capability_discovery_lock(configured)
        )
        with guard:
            config = _effective_config(configured)
            cache_path = self._cache_path(
                config,
                bundle,
                system_prompt=system_prompt,
                request_kind=request_kind,
            )
            if cache_path is not None and cache_path.is_file():
                metrics.cache_hits += 1
                value = json.loads(cache_path.read_text(encoding="utf-8"))
                _remember_effective_capability(configured, config)
                return VerificationResponse.model_validate(value["response"]), True
            started = time.monotonic()
            value, call_metrics = self.invoke_json(
                config,
                system_prompt,
                user_prompt if user_prompt is not None else _bundle_prompt(bundle),
            )
            metrics.elapsed_seconds += time.monotonic() - started
            metrics.provider_calls += int(call_metrics.get("provider_calls", 1))
            metrics.provider_call_seconds += float(
                call_metrics.get("provider_call_seconds", 0.0)
            )
            metrics.retry_count += int(call_metrics.get("retry_count", 0))
            metrics.capability_fallback_count += int(
                call_metrics.get("capability_fallback_count", 0)
            )
            effective = replace(
                config,
                thinking_mode=call_metrics.get(
                    "effective_thinking_mode", config.thinking_mode
                ),
                reasoning_effort=call_metrics.get(
                    "effective_reasoning_effort", config.reasoning_effort
                ),
                response_mode=call_metrics.get(
                    "effective_response_mode", config.response_mode
                ),
            )
            _remember_effective_capability(configured, effective)
            try:
                response = VerificationResponse.model_validate(value)
            except Exception as exc:
                raise VerificationClientError("invalid_contract", str(exc)) from exc
            cache_path = self._cache_path(
                effective,
                bundle,
                system_prompt=system_prompt,
                request_kind=request_kind,
            )
            if cache_path is not None:
                cache_path.parent.mkdir(parents=True, exist_ok=True)
                payload = {
                    "cache_record_type": "alpha25_verification_response",
                    "identity": self._cache_identity(
                        effective,
                        bundle,
                        system_prompt=system_prompt,
                        request_kind=request_kind,
                    ),
                    "effective": call_metrics,
                    "response": response.model_dump(mode="json"),
                }
                temporary = cache_path.with_suffix(".tmp")
                temporary.write_text(
                    json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
                    encoding="utf-8",
                )
                temporary.replace(cache_path)
            return response, False

    def _field_cache_identity(
        self,
        config: VerifierRoleConfig,
        bundle: VerificationBundle,
        *,
        system_prompt: str = FIELD_SYSTEM_PROMPT,
        request_kind: str = "field_primary",
    ) -> dict[str, Any]:
        configured = self.primary if config.role == "primary" else self.fallback
        return {
            "protocol_version": FIELD_VERIFICATION_PROTOCOL_VERSION,
            "request_kind": request_kind,
            "role_config": {
                "configured": configured.identity(),
                "effective": config.identity(),
            },
            "bundle": bundle.model_dump(mode="json"),
            "required_fields": {
                row.assertion_id: list(required_scientific_fields(row))
                for row in bundle.assertions
            },
            "system_prompt": system_prompt,
        }

    def _field_cache_path(
        self,
        config: VerifierRoleConfig,
        bundle: VerificationBundle,
        *,
        system_prompt: str = FIELD_SYSTEM_PROMPT,
        request_kind: str = "field_primary",
    ) -> Path | None:
        if self.cache_dir is None:
            return None
        identity = self._field_cache_identity(
            config,
            bundle,
            system_prompt=system_prompt,
            request_kind=request_kind,
        )
        return (
            self.cache_dir
            / f"{config.role}_field"
            / f"{stable_id('verify_field', identity)}.json"
        )

    def _load_or_call_field(
        self,
        config: VerifierRoleConfig,
        bundle: VerificationBundle,
        metrics: VerificationClientMetrics,
        *,
        system_prompt: str,
        request_kind: str,
    ) -> tuple[
        FieldVerificationResponse,
        bool,
        tuple[dict[str, Any], ...],
    ]:
        configured = config
        guard = (
            nullcontext()
            if _capability_is_known(configured)
            else _capability_discovery_lock(configured)
        )
        with guard:
            config = _effective_config(configured)
            cache_path = self._field_cache_path(
                config,
                bundle,
                system_prompt=system_prompt,
                request_kind=request_kind,
            )
            if cache_path is not None and cache_path.is_file():
                metrics.cache_hits += 1
                value = json.loads(cache_path.read_text(encoding="utf-8"))
                _remember_effective_capability(configured, config)
                return FieldVerificationResponse.model_validate(
                    value["response"]
                ), True, tuple(value.get("response_normalizations") or ())
            started = time.monotonic()
            truncation_retries = max(
                0,
                int(
                    os.getenv(
                        "KNOWMAT2_ALPHA25_VERIFIER_SINGLETON_TRUNCATION_RETRIES",
                        "0",
                    )
                ),
            )
            truncation_attempt = 0
            while True:
                try:
                    value, call_metrics = self.invoke_json(
                        config,
                        system_prompt,
                        _field_bundle_prompt(bundle),
                    )
                    break
                except Exception as exc:
                    failure_metrics = getattr(exc, "metrics", None)
                    if isinstance(failure_metrics, dict):
                        observed = replace(
                            config,
                            thinking_mode=failure_metrics.get(
                                "effective_thinking_mode", config.thinking_mode
                            ),
                            reasoning_effort=failure_metrics.get(
                                "effective_reasoning_effort", config.reasoning_effort
                            ),
                            response_mode=failure_metrics.get(
                                "effective_response_mode", config.response_mode
                            ),
                        )
                        _remember_effective_capability(configured, observed)
                        config = observed
                    eligible_retry = (
                        getattr(exc, "code", None) == "output_truncated"
                        and request_kind == "field_independent_review"
                        and len(bundle.assertions) == 1
                        and truncation_attempt < truncation_retries
                    )
                    if not eligible_retry:
                        raise
                    _record_exception_metrics(metrics, exc)
                    metrics.record_failure("output_truncated")
                    metrics.retry_count += 1
                    truncation_attempt += 1
            metrics.elapsed_seconds += time.monotonic() - started
            metrics.provider_calls += int(call_metrics.get("provider_calls", 1))
            metrics.provider_call_seconds += float(
                call_metrics.get("provider_call_seconds", 0.0)
            )
            metrics.retry_count += int(call_metrics.get("retry_count", 0))
            metrics.capability_fallback_count += int(
                call_metrics.get("capability_fallback_count", 0)
            )
            effective = replace(
                config,
                thinking_mode=call_metrics.get(
                    "effective_thinking_mode", config.thinking_mode
                ),
                reasoning_effort=call_metrics.get(
                    "effective_reasoning_effort", config.reasoning_effort
                ),
                response_mode=call_metrics.get(
                    "effective_response_mode", config.response_mode
                ),
            )
            _remember_effective_capability(configured, effective)
            normalized_value, response_normalizations = (
                _normalize_field_response_shape(value, bundle)
            )
            try:
                response = FieldVerificationResponse.model_validate(
                    normalized_value
                )
            except Exception as exc:
                raise VerificationClientError(
                    "invalid_field_contract", str(exc)
                ) from exc
            cache_path = self._field_cache_path(
                effective,
                bundle,
                system_prompt=system_prompt,
                request_kind=request_kind,
            )
            if cache_path is not None:
                cache_path.parent.mkdir(parents=True, exist_ok=True)
                payload = {
                    "cache_record_type": "alpha25_field_verification_response",
                    "identity": self._field_cache_identity(
                        effective,
                        bundle,
                        system_prompt=system_prompt,
                        request_kind=request_kind,
                    ),
                    "effective": call_metrics,
                    "response": response.model_dump(mode="json"),
                }
                if response_normalizations:
                    payload["raw_response"] = value
                    payload["response_normalizations"] = list(
                        response_normalizations
                    )
                temporary = cache_path.with_suffix(".tmp")
                temporary.write_text(
                    json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
                    encoding="utf-8",
                )
                temporary.replace(cache_path)
            return response, False, response_normalizations

    def _compact_cache_identity(
        self,
        config: VerifierRoleConfig,
        bundle: VerificationBundle,
    ) -> dict[str, Any]:
        return {
            "protocol_version": COMPACT_REVIEW_PROTOCOL_VERSION,
            "request_kind": "compact_independent_review",
            "role_config": {
                "configured": self.fallback.identity(),
                "effective": config.identity(),
            },
            "bundle": bundle.model_dump(mode="json"),
            "required_fields": {
                row.assertion_id: list(required_scientific_fields(row))
                for row in bundle.assertions
            },
            "system_prompt": COMPACT_REVIEW_SYSTEM_PROMPT,
        }

    def _compact_cache_path(
        self,
        config: VerifierRoleConfig,
        bundle: VerificationBundle,
    ) -> Path | None:
        if self.cache_dir is None:
            return None
        identity = self._compact_cache_identity(config, bundle)
        return (
            self.cache_dir
            / f"{config.role}_compact"
            / f"{stable_id('verify_compact', identity)}.json"
        )

    def _load_or_call_compact(
        self,
        config: VerifierRoleConfig,
        bundle: VerificationBundle,
        metrics: VerificationClientMetrics,
    ) -> tuple[CompactReviewResponse, bool]:
        configured = config
        guard = (
            nullcontext()
            if _capability_is_known(configured)
            else _capability_discovery_lock(configured)
        )
        with guard:
            config = _effective_config(configured)
            cache_path = self._compact_cache_path(config, bundle)
            if cache_path is not None and cache_path.is_file():
                metrics.cache_hits += 1
                value = json.loads(cache_path.read_text(encoding="utf-8"))
                _remember_effective_capability(configured, config)
                return CompactReviewResponse.model_validate(
                    value["response"]
                ), True
            started = time.monotonic()
            try:
                value, call_metrics = self.invoke_json(
                    config,
                    COMPACT_REVIEW_SYSTEM_PROMPT,
                    _compact_review_prompt(bundle),
                )
            except Exception as exc:
                metrics.elapsed_seconds += time.monotonic() - started
                failure_metrics = getattr(exc, "metrics", None)
                if isinstance(failure_metrics, dict):
                    observed = replace(
                        config,
                        thinking_mode=failure_metrics.get(
                            "effective_thinking_mode", config.thinking_mode
                        ),
                        reasoning_effort=failure_metrics.get(
                            "effective_reasoning_effort", config.reasoning_effort
                        ),
                        response_mode=failure_metrics.get(
                            "effective_response_mode", config.response_mode
                        ),
                    )
                    _remember_effective_capability(configured, observed)
                raise
            metrics.elapsed_seconds += time.monotonic() - started
            metrics.provider_calls += int(call_metrics.get("provider_calls", 1))
            metrics.provider_call_seconds += float(
                call_metrics.get("provider_call_seconds", 0.0)
            )
            metrics.retry_count += int(call_metrics.get("retry_count", 0))
            metrics.capability_fallback_count += int(
                call_metrics.get("capability_fallback_count", 0)
            )
            effective = replace(
                config,
                thinking_mode=call_metrics.get(
                    "effective_thinking_mode", config.thinking_mode
                ),
                reasoning_effort=call_metrics.get(
                    "effective_reasoning_effort", config.reasoning_effort
                ),
                response_mode=call_metrics.get(
                    "effective_response_mode", config.response_mode
                ),
            )
            _remember_effective_capability(configured, effective)
            try:
                response = CompactReviewResponse.model_validate(value)
            except Exception as exc:
                raise VerificationClientError(
                    "invalid_compact_contract", str(exc)
                ) from exc
            cache_path = self._compact_cache_path(effective, bundle)
            if cache_path is not None:
                cache_path.parent.mkdir(parents=True, exist_ok=True)
                payload = {
                    "cache_record_type": "alpha25_compact_review_response",
                    "identity": self._compact_cache_identity(
                        effective, bundle
                    ),
                    "effective": call_metrics,
                    "response": response.model_dump(mode="json"),
                }
                temporary = cache_path.with_suffix(".tmp")
                temporary.write_text(
                    json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
                    encoding="utf-8",
                )
                temporary.replace(cache_path)
            return response, False

    def _label_cache_identity(
        self,
        config: VerifierRoleConfig,
        bundle: VerificationBundle,
    ) -> dict[str, Any]:
        return {
            "protocol_version": COMPACT_LABEL_REVIEW_PROTOCOL_VERSION,
            "request_kind": "compact_label_independent_review",
            "role_config": {
                "configured": self.fallback.identity(),
                "effective": config.identity(),
            },
            "bundle": bundle.model_dump(mode="json"),
            "required_fields": {
                row.assertion_id: list(required_scientific_fields(row))
                for row in bundle.assertions
            },
            "system_prompt": COMPACT_LABEL_SYSTEM_PROMPT,
            "responses_reasoning_summary": (
                "concise"
                if config.reasoning_effort != "provider_default"
                else "provider_default"
            ),
        }

    def _label_cache_path(
        self,
        config: VerifierRoleConfig,
        bundle: VerificationBundle,
    ) -> Path | None:
        if self.cache_dir is None:
            return None
        identity = self._label_cache_identity(config, bundle)
        return (
            self.cache_dir
            / f"{config.role}_labels"
            / f"{stable_id('verify_labels', identity)}.json"
        )

    def _load_or_call_labels(
        self,
        config: VerifierRoleConfig,
        bundle: VerificationBundle,
        metrics: VerificationClientMetrics,
    ) -> tuple[tuple[CompactLabel, ...], bool, dict[str, Any]]:
        """Load or call one fixed-cardinality Responses label request."""

        if config.api_mode != "responses":
            raise VerificationClientError(
                "label_transport_not_responses",
                "compact label review requires the configured Responses transport",
            )
        configured = config
        guard = (
            nullcontext()
            if _capability_is_known(configured)
            else _capability_discovery_lock(configured)
        )
        with guard:
            config = _effective_config(configured)
            cache_path = self._label_cache_path(config, bundle)
            if cache_path is not None and cache_path.is_file():
                metrics.cache_hits += 1
                value = json.loads(cache_path.read_text(encoding="utf-8"))
                labels = parse_compact_label_array(
                    canonical_json(value["labels"]),
                    label_count=len(bundle.assertions),
                )
                _remember_effective_capability(configured, config)
                return labels, True, dict(value.get("response_metadata") or {})

            started = time.monotonic()
            try:
                output_text, call_metrics = self.invoke_responses(
                    config,
                    COMPACT_LABEL_SYSTEM_PROMPT,
                    _compact_label_prompt(bundle),
                )
            except Exception as exc:
                metrics.elapsed_seconds += time.monotonic() - started
                failure_metrics = getattr(exc, "metrics", None)
                if isinstance(failure_metrics, dict):
                    observed = replace(
                        config,
                        thinking_mode=failure_metrics.get(
                            "effective_thinking_mode", config.thinking_mode
                        ),
                        reasoning_effort=failure_metrics.get(
                            "effective_reasoning_effort", config.reasoning_effort
                        ),
                        response_mode=failure_metrics.get(
                            "effective_response_mode", config.response_mode
                        ),
                    )
                    _remember_effective_capability(configured, observed)
                raise
            metrics.elapsed_seconds += time.monotonic() - started
            metrics.provider_calls += int(call_metrics.get("provider_calls", 1))
            metrics.provider_call_seconds += float(
                call_metrics.get("provider_call_seconds", 0.0)
            )
            metrics.retry_count += int(call_metrics.get("retry_count", 0))
            metrics.capability_fallback_count += int(
                call_metrics.get("capability_fallback_count", 0)
            )
            effective = replace(
                config,
                thinking_mode=call_metrics.get(
                    "effective_thinking_mode", config.thinking_mode
                ),
                reasoning_effort=call_metrics.get(
                    "effective_reasoning_effort", config.reasoning_effort
                ),
                response_mode=call_metrics.get(
                    "effective_response_mode", config.response_mode
                ),
            )
            _remember_effective_capability(configured, effective)
            try:
                labels = parse_compact_label_array(
                    output_text,
                    label_count=len(bundle.assertions),
                )
            except ValueError as exc:
                raise VerificationClientError(
                    "invalid_label_cardinality", str(exc), metrics=call_metrics
                ) from exc

            response_metadata = {
                key: _wire_value(value)
                for key, value in call_metrics.items()
                if key
                in {
                    "api_mode",
                    "response_id",
                    "response_status",
                    "incomplete_details",
                    "reasoning_summary",
                    "usage",
                    "output_text",
                    "provider_call_seconds",
                    "effective_reasoning_effort",
                    "effective_reasoning_summary",
                    "capability_fallback_count",
                }
            }
            cache_path = self._label_cache_path(effective, bundle)
            if cache_path is not None:
                cache_path.parent.mkdir(parents=True, exist_ok=True)
                payload = {
                    "cache_record_type": "alpha25_compact_label_response",
                    "identity": self._label_cache_identity(effective, bundle),
                    "labels": list(labels),
                    "response_metadata": response_metadata,
                }
                temporary = cache_path.with_suffix(".tmp")
                temporary.write_text(
                    json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
                    encoding="utf-8",
                )
                temporary.replace(cache_path)
            return labels, False, response_metadata

    def _recovery_cache_identity(
        self, config: VerifierRoleConfig, request: RecoveryRequest
    ) -> dict[str, Any]:
        configured = self.primary if config.role == "primary" else self.fallback
        return {
            "protocol_version": VERIFICATION_PROTOCOL_VERSION,
            "role_config": {
                "configured": configured.identity(),
                "effective": config.identity(),
            },
            "recovery_request": request.model_dump(mode="json"),
            "system_prompt": RECOVERY_SYSTEM_PROMPT,
        }

    def _recovery_cache_path(
        self, config: VerifierRoleConfig, request: RecoveryRequest
    ) -> Path | None:
        if self.cache_dir is None:
            return None
        identity = self._recovery_cache_identity(config, request)
        return self.cache_dir / f"{config.role}_recovery" / f"{stable_id('recover', identity)}.json"

    def _load_or_call_recovery(
        self,
        config: VerifierRoleConfig,
        request: RecoveryRequest,
        metrics: VerificationClientMetrics,
    ) -> tuple[RecoveryResponse, bool]:
        configured = config
        guard = (
            nullcontext()
            if _capability_is_known(configured)
            else _capability_discovery_lock(configured)
        )
        with guard:
            config = _effective_config(configured)
            cache_path = self._recovery_cache_path(config, request)
            if cache_path is not None and cache_path.is_file():
                metrics.cache_hits += 1
                value = json.loads(cache_path.read_text(encoding="utf-8"))
                _remember_effective_capability(configured, config)
                return RecoveryResponse.model_validate(value["response"]), True
            started = time.monotonic()
            value, call_metrics = self.invoke_json(
                config, RECOVERY_SYSTEM_PROMPT, _recovery_prompt(request)
            )
            metrics.elapsed_seconds += time.monotonic() - started
            metrics.provider_calls += int(call_metrics.get("provider_calls", 1))
            metrics.provider_call_seconds += float(
                call_metrics.get("provider_call_seconds", 0.0)
            )
            metrics.retry_count += int(call_metrics.get("retry_count", 0))
            metrics.capability_fallback_count += int(
                call_metrics.get("capability_fallback_count", 0)
            )
            effective = replace(
                config,
                thinking_mode=call_metrics.get(
                    "effective_thinking_mode", config.thinking_mode
                ),
                reasoning_effort=call_metrics.get(
                    "effective_reasoning_effort", config.reasoning_effort
                ),
                response_mode=call_metrics.get(
                    "effective_response_mode", config.response_mode
                ),
            )
            _remember_effective_capability(configured, effective)
            try:
                response = RecoveryResponse.model_validate(value)
            except Exception as exc:
                raise VerificationClientError(
                    "invalid_recovery_contract", str(exc)
                ) from exc
            cache_path = self._recovery_cache_path(effective, request)
            if cache_path is not None:
                cache_path.parent.mkdir(parents=True, exist_ok=True)
                payload = {
                    "cache_record_type": "alpha25_recovery_response",
                    "identity": self._recovery_cache_identity(effective, request),
                    "effective": call_metrics,
                    "response": response.model_dump(mode="json"),
                }
                temporary = cache_path.with_suffix(".tmp")
                temporary.write_text(
                    json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
                    encoding="utf-8",
                )
                temporary.replace(cache_path)
            return response, False

    @staticmethod
    def _field_response_needs_secondary(
        bundle: VerificationBundle,
        response: FieldVerificationResponse,
    ) -> bool:
        if any(row.risk_severity == "hard" for row in bundle.assertions):
            return True
        return any(
            field.verdict != "supported"
            for decision in response.decisions
            for field in decision.fields
        )

    def _verify_field_bundle(
        self,
        bundle: VerificationBundle,
        inventory: VerificationInventory,
    ) -> VerificationClientResult:
        metrics = VerificationClientMetrics()
        started = time.monotonic()
        metrics.field_hard_assertion_count = sum(
            row.risk_severity == "hard" for row in bundle.assertions
        )
        metrics.field_soft_assertion_count = sum(
            row.risk_severity == "soft" for row in bundle.assertions
        )
        primary_response: FieldVerificationResponse | None = None
        secondary_response: FieldVerificationResponse | None = None
        primary_cache_hit = False
        secondary_cache_hit = False
        primary_normalizations: tuple[dict[str, Any], ...] = ()
        secondary_normalizations: tuple[dict[str, Any], ...] = ()
        primary_error: Exception | None = None
        secondary_error: Exception | None = None
        primary_decisions_by_id: dict[str, Any] | None = None
        primary_errors_by_id: dict[str, str] = {}
        secondary_decisions_by_id: dict[str, Any] | None = None
        secondary_errors_by_id: dict[str, str] = {}
        compact_decisions_by_id: dict[str, CompactReviewDecision] = {}
        compact_errors_by_id: dict[str, str] = {}
        compact_cache_hits: list[bool] = []
        compact_metadata_by_id: dict[str, dict[str, Any]] = {}
        secondary_skipped_ids: set[str] = set()

        def run_role(
            config,
            system_prompt: str,
            request_kind: str,
            target_bundle: VerificationBundle = bundle,
            partition_assertions: bool = False,
        ):
            role_metrics = VerificationClientMetrics()
            try:
                response, cache_hit, normalizations = self._load_or_call_field(
                    config,
                    target_bundle,
                    role_metrics,
                    system_prompt=system_prompt,
                    request_kind=request_kind,
                )
                if partition_assertions:
                    decisions, decision_errors = _partition_valid_field_decisions(
                        target_bundle, response
                    )
                    for error in decision_errors.values():
                        role_metrics.record_failure("VerificationGroundingError")
                    return (
                        response,
                        cache_hit,
                        normalizations,
                        None,
                        role_metrics,
                        decisions,
                        decision_errors,
                    )
                decisions = validate_field_response(target_bundle, response)
                return (
                    response,
                    cache_hit,
                    normalizations,
                    None,
                    role_metrics,
                    decisions,
                    {},
                )
            except Exception as exc:
                _record_exception_metrics(role_metrics, exc)
                role_metrics.record_failure(
                    getattr(exc, "code", exc.__class__.__name__)
                )
                return None, False, (), exc, role_metrics, {}, {}

        def run_compact(target_bundle: VerificationBundle):
            role_metrics = VerificationClientMetrics()
            try:
                response, cache_hit = self._load_or_call_compact(
                    self._compact_config(),
                    target_bundle,
                    role_metrics,
                )
                decisions, decision_errors = (
                    _partition_valid_compact_decisions(
                        target_bundle, response
                    )
                )
                for _error in decision_errors.values():
                    role_metrics.record_failure(
                        "VerificationGroundingError"
                    )
                return (
                    response,
                    cache_hit,
                    None,
                    role_metrics,
                    decisions,
                    decision_errors,
                )
            except Exception as exc:
                _record_exception_metrics(role_metrics, exc)
                role_metrics.record_failure(
                    getattr(exc, "code", exc.__class__.__name__)
                )
                return None, False, exc, role_metrics, {}, {}

        def execute_compact(
            target_bundle: VerificationBundle,
            *,
            split_depth: int = 0,
        ) -> None:
            metrics.field_secondary_calls += 1
            metrics.compact_secondary_calls += 1
            (
                response,
                cache_hit,
                error,
                role_metrics,
                decisions,
                decision_errors,
            ) = run_compact(target_bundle)
            metrics.absorb_provider_attempt(role_metrics)
            assertion_ids = {
                row.assertion_id for row in target_bundle.assertions
            }
            if error is not None:
                code = getattr(error, "code", error.__class__.__name__)
                if code == "output_truncated":
                    metrics.compact_truncation_count += 1
                if (
                    code == "output_truncated"
                    and len(target_bundle.assertions) > 1
                    and split_depth < self.compact_split_limit
                ):
                    metrics.compact_split_count += 1
                    ordered = sorted(assertion_ids)
                    midpoint = max(1, len(ordered) // 2)
                    for child_ids in (
                        set(ordered[:midpoint]),
                        set(ordered[midpoint:]),
                    ):
                        child = self._compact_review_subset(
                            target_bundle, child_ids
                        )
                        execute_compact(
                            child, split_depth=split_depth + 1
                        )
                    return
                for assertion_id in assertion_ids:
                    compact_errors_by_id[assertion_id] = str(error)
                    compact_metadata_by_id[assertion_id] = {
                        "bundle_id": target_bundle.bundle_id,
                        "cache_hit": False,
                        "status": "technical_failure",
                    }
                return
            compact_cache_hits.append(cache_hit)
            compact_decisions_by_id.update(decisions)
            compact_errors_by_id.update(decision_errors)
            for assertion_id in assertion_ids:
                compact_metadata_by_id[assertion_id] = {
                    "bundle_id": target_bundle.bundle_id,
                    "cache_hit": cache_hit,
                    "status": "completed",
                }

        hard_bundle = any(
            row.risk_severity == "hard" for row in bundle.assertions
        )
        metrics.field_primary_calls += 1
        if hard_bundle:
            # A hard assertion cannot enter formal output unless the primary
            # supports every field. Finish and validate that role first, then
            # spend independent-review calls only on assertions that remain
            # eligible for positive consensus.
            (
                primary_response,
                primary_cache_hit,
                primary_normalizations,
                primary_error,
                primary_metrics,
                primary_decisions_by_id,
                primary_errors_by_id,
            ) = run_role(
                self.primary,
                FIELD_SYSTEM_PROMPT,
                "field_primary",
                bundle,
                True,
            )
            metrics.absorb_provider_attempt(primary_metrics)
            hard_ids = {
                row.assertion_id
                for row in bundle.assertions
                if row.risk_severity == "hard"
            }
            primary_positive_ids = {
                assertion_id
                for assertion_id, decision in (
                    primary_decisions_by_id or {}
                ).items()
                if assertion_id in hard_ids
                and all(
                    field.verdict == "supported"
                    for field in decision.fields
                )
            }
            secondary_skipped_ids = hard_ids - primary_positive_ids
            for assertion_id in secondary_skipped_ids:
                compact_metadata_by_id[assertion_id] = {
                    "bundle_id": None,
                    "cache_hit": False,
                    "status": "skipped",
                }
            metrics.field_primary_positive_hard_count += len(
                primary_positive_ids
            )
            metrics.field_secondary_skipped_count += len(
                secondary_skipped_ids
            )
            if primary_positive_ids:
                compact_bundle = self._compact_review_subset(
                    bundle, primary_positive_ids
                )
                execute_compact(compact_bundle)
        else:
            (
                primary_response,
                primary_cache_hit,
                primary_normalizations,
                primary_error,
                primary_metrics,
                primary_decisions_by_id,
                primary_errors_by_id,
            ) = run_role(
                self.primary,
                FIELD_SYSTEM_PROMPT,
                "field_primary",
                bundle,
                True,
            )
            metrics.absorb_provider_attempt(primary_metrics)

        metrics.field_shape_normalization_count += len(primary_normalizations)
        metrics.field_shape_normalization_count += len(secondary_normalizations)

        if primary_error is not None:
            metrics.primary_failures += 1
        if primary_errors_by_id:
            metrics.primary_failures += len(primary_errors_by_id)
        if compact_errors_by_id:
            metrics.fallback_failures += len(compact_errors_by_id)
            metrics.unresolved_bundles += 1

        applied = apply_field_consensus(
            bundle,
            inventory,
            primary_response=primary_response,
            secondary_response=secondary_response,
            primary_error=str(primary_error) if primary_error is not None else None,
            secondary_error=(
                str(secondary_error) if secondary_error is not None else None
            ),
            primary_cache_hit=primary_cache_hit,
            secondary_cache_hit=secondary_cache_hit,
            primary_decisions=primary_decisions_by_id,
            secondary_decisions=secondary_decisions_by_id,
            primary_errors=primary_errors_by_id,
            secondary_errors=secondary_errors_by_id,
            secondary_compact_decisions=(
                compact_decisions_by_id if hard_bundle else None
            ),
            secondary_compact_errors=(
                compact_errors_by_id if hard_bundle else None
            ),
            secondary_compact_cache_hit=(
                bool(compact_cache_hits) and all(compact_cache_hits)
            ),
            secondary_skipped_assertion_ids=secondary_skipped_ids,
        )
        if primary_normalizations or secondary_normalizations:
            applied = replace(
                applied,
                audit_records=tuple(
                    {
                        **dict(audit),
                        "primary_response_normalizations": [
                            row
                            for row in primary_normalizations
                            if row.get("assertion_id")
                            == audit.get("assertion_id")
                        ],
                        "secondary_response_normalizations": [
                            row
                            for row in secondary_normalizations
                            if row.get("assertion_id")
                            == audit.get("assertion_id")
                        ],
                    }
                    for audit in applied.audit_records
                ),
            )
        if compact_metadata_by_id:
            applied = replace(
                applied,
                audit_records=tuple(
                    {
                        **dict(audit),
                        "secondary_compact_review": {
                            **dict(
                                audit.get("secondary_compact_review") or {}
                            ),
                            **compact_metadata_by_id.get(
                                str(audit.get("assertion_id")), {}
                            ),
                        },
                    }
                    for audit in applied.audit_records
                ),
            )
        for audit in applied.audit_records:
            action = str(audit.get("formal_action") or "")
            if action == "isolate":
                metrics.field_isolated_assertion_count += 1
            elif action == "reassign":
                metrics.field_reassigned_assertion_count += 1
            elif action == "preserve":
                metrics.field_preserved_assertion_count += 1
                metrics.preserved_unresolved_assertions += 1
        metrics.elapsed_seconds += max(
            0.0, time.monotonic() - started - metrics.elapsed_seconds
        )
        return VerificationClientResult(
            applied=applied,
            metrics=metrics.to_dict(),
        )

    @staticmethod
    def _pack_paper_label_bundles(
        eligible: list[tuple[VerificationBundle, str]],
        *,
        max_assertions: int = 6,
        max_source_chars: int = 6000,
    ) -> tuple[VerificationBundle, ...]:
        """Repack primary-positive hard assertions across primary bundles."""

        singleton_rows: list[tuple[str, VerificationBundle, str]] = []
        for parent, assertion_id in eligible:
            subset = VerificationClient._label_review_subset(
                parent, {assertion_id}
            )
            singleton_rows.append((subset.axis, subset, parent.bundle_id))
        singleton_rows.sort(
            key=lambda row: (
                row[0],
                min(
                    (evidence.start_char for evidence in row[1].evidence),
                    default=0,
                ),
                row[1].assertions[0].fact_type,
                row[1].assertions[0].sample_id_raw.casefold(),
                row[1].assertions[0].assertion_id,
                row[2],
            )
        )

        packed: list[VerificationBundle] = []
        current: list[tuple[VerificationBundle, str]] = []

        def combined(
            rows: list[tuple[VerificationBundle, str]],
        ) -> VerificationBundle:
            assertions = sorted(
                (row for bundle, _parent in rows for row in bundle.assertions),
                key=lambda row: row.assertion_id,
            )
            evidence_by_id: dict[str, Any] = {}
            entities_by_id: dict[str, Any] = {}
            for bundle, _parent in rows:
                for evidence in bundle.evidence:
                    existing = evidence_by_id.get(evidence.evidence_id)
                    if existing is not None and existing != evidence:
                        raise ValueError(
                            "paper label packing found conflicting evidence IDs"
                        )
                    evidence_by_id[evidence.evidence_id] = evidence
                for entity in bundle.entities:
                    existing = entities_by_id.get(entity.entity_id)
                    if existing is not None and existing != entity:
                        raise ValueError(
                            "paper label packing found conflicting entity IDs"
                        )
                    entities_by_id[entity.entity_id] = entity
            evidence = sorted(
                evidence_by_id.values(),
                key=lambda row: (row.start_char, row.kind, row.evidence_id),
            )
            evidence_ids = {row.evidence_id for row in evidence}
            entities = sorted(
                (
                    row
                    for row in entities_by_id.values()
                    if set(row.evidence_ids) <= evidence_ids
                ),
                key=lambda row: row.entity_id,
            )
            payload = {
                "purpose": "paper_compact_label_review",
                "parent_bundle_ids": sorted({parent for _bundle, parent in rows}),
                "assertion_ids": [row.assertion_id for row in assertions],
                "evidence_ids": [row.evidence_id for row in evidence],
            }
            return VerificationBundle(
                protocol_version=rows[0][0].protocol_version,
                bundle_id=stable_id("bundle_paper_labels", payload),
                axis=rows[0][0].axis,
                assertions=assertions,
                entities=entities,
                evidence=evidence,
                source_char_count=sum(len(row.text) for row in evidence),
            )

        def flush() -> None:
            nonlocal current
            if current:
                packed.append(combined(current))
                current = []

        for axis, singleton, parent_id in singleton_rows:
            candidate = [*current, (singleton, parent_id)]
            if current and current[0][0].axis != axis:
                flush()
                candidate = [(singleton, parent_id)]
            trial = combined(candidate)
            if current and (
                len(trial.assertions) > max_assertions
                or trial.source_char_count > max_source_chars
            ):
                flush()
                trial = combined([(singleton, parent_id)])
            if len(trial.assertions) > max_assertions:
                raise ValueError("singleton label request exceeds assertion limit")
            if trial.source_char_count > max_source_chars:
                raise ValueError("singleton label request exceeds evidence limit")
            current.append((singleton, parent_id))
        flush()
        return tuple(packed)

    def verify_field_bundles(
        self,
        bundles: list[VerificationBundle] | tuple[VerificationBundle, ...],
        inventory: VerificationInventory,
        *,
        workers: int = 4,
    ) -> VerificationClientResult:
        """Run all paper primaries before one cross-bundle label phase."""

        if not self.field_level:
            raise ValueError("paper field verification requires field_level=True")
        ordered_bundles = sorted(
            bundles,
            key=lambda bundle: (
                sum(len(row.text) for row in bundle.evidence),
                len(bundle.assertions),
                bundle.bundle_id,
            ),
        )
        metrics = VerificationClientMetrics()
        started = time.monotonic()
        metrics.field_hard_assertion_count = sum(
            row.risk_severity == "hard"
            for bundle in ordered_bundles
            for row in bundle.assertions
        )
        metrics.field_soft_assertion_count = sum(
            row.risk_severity == "soft"
            for bundle in ordered_bundles
            for row in bundle.assertions
        )

        def run_primary(bundle: VerificationBundle) -> dict[str, Any]:
            role_metrics = VerificationClientMetrics()
            try:
                response, cache_hit, normalizations = self._load_or_call_field(
                    self.primary,
                    bundle,
                    role_metrics,
                    system_prompt=FIELD_SYSTEM_PROMPT,
                    request_kind="field_primary",
                )
                decisions, decision_errors = _partition_valid_field_decisions(
                    bundle, response
                )
                for _error in decision_errors.values():
                    role_metrics.record_failure("VerificationGroundingError")
                return {
                    "bundle": bundle,
                    "response": response,
                    "cache_hit": cache_hit,
                    "normalizations": normalizations,
                    "error": None,
                    "decisions": decisions,
                    "decision_errors": decision_errors,
                    "metrics": role_metrics,
                }
            except Exception as exc:
                _record_exception_metrics(role_metrics, exc)
                role_metrics.record_failure(
                    getattr(exc, "code", exc.__class__.__name__)
                )
                return {
                    "bundle": bundle,
                    "response": None,
                    "cache_hit": False,
                    "normalizations": (),
                    "error": exc,
                    "decisions": {},
                    "decision_errors": {
                        row.assertion_id: str(exc) for row in bundle.assertions
                    },
                    "metrics": role_metrics,
                }

        primary_rows: list[dict[str, Any]] = []
        if ordered_bundles:
            # Seed generic capability discovery with the smallest bundle, then
            # run the remaining paper primaries concurrently.
            primary_rows.append(run_primary(ordered_bundles[0]))
            remaining = ordered_bundles[1:]
            if remaining:
                with ThreadPoolExecutor(
                    max_workers=max(1, min(workers, len(remaining)))
                ) as pool:
                    pending = {
                        pool.submit(run_primary, bundle): bundle.bundle_id
                        for bundle in remaining
                    }
                    for future in as_completed(pending):
                        primary_rows.append(future.result())
        primary_rows.sort(key=lambda row: row["bundle"].bundle_id)
        metrics.field_primary_calls += len(primary_rows)
        for row in primary_rows:
            metrics.absorb_provider_attempt(row["metrics"])
            metrics.field_shape_normalization_count += len(row["normalizations"])
            if row["error"] is not None:
                metrics.primary_failures += 1
            metrics.primary_failures += len(row["decision_errors"])

        eligible: list[tuple[VerificationBundle, str]] = []
        skipped_ids: set[str] = set()
        for row in primary_rows:
            bundle = row["bundle"]
            decisions = row["decisions"]
            for assertion in bundle.assertions:
                if assertion.risk_severity != "hard":
                    continue
                decision = decisions.get(assertion.assertion_id)
                if decision is not None and all(
                    field.verdict == "supported" for field in decision.fields
                ):
                    eligible.append((bundle, assertion.assertion_id))
                else:
                    skipped_ids.add(assertion.assertion_id)
        metrics.field_primary_positive_hard_count = len(eligible)
        metrics.field_secondary_skipped_count = len(skipped_ids)

        label_decisions: dict[str, CompactLabel] = {}
        label_errors: dict[str, str] = {}
        label_cache_hits: set[str] = set()
        label_metadata: dict[str, dict[str, Any]] = {
            assertion_id: {
                "bundle_id": None,
                "request_index": None,
                "cache_hit": False,
                "transport": "responses",
                "status": "skipped",
            }
            for assertion_id in skipped_ids
        }
        label_state_lock = Lock()

        label_bundles = self._pack_paper_label_bundles(eligible)

        def run_label(bundle: VerificationBundle) -> dict[str, Any]:
            role_metrics = VerificationClientMetrics()
            try:
                labels, cache_hit, response_metadata = self._load_or_call_labels(
                    self._compact_config(), bundle, role_metrics
                )
                return {
                    "bundle": bundle,
                    "labels": labels,
                    "cache_hit": cache_hit,
                    "metadata": response_metadata,
                    "error": None,
                    "metrics": role_metrics,
                }
            except Exception as exc:
                _record_exception_metrics(role_metrics, exc)
                role_metrics.record_failure(
                    getattr(exc, "code", exc.__class__.__name__)
                )
                return {
                    "bundle": bundle,
                    "labels": (),
                    "cache_hit": False,
                    "metadata": dict(getattr(exc, "metrics", {}) or {}),
                    "error": exc,
                    "metrics": role_metrics,
                }

        def execute_label(
            target_bundle: VerificationBundle,
            *,
            split_depth: int = 0,
        ) -> None:
            with label_state_lock:
                metrics.field_secondary_calls += 1
                metrics.compact_secondary_calls += 1
            result = run_label(target_bundle)
            with label_state_lock:
                metrics.absorb_provider_attempt(result["metrics"])
            error = result["error"]
            assertion_ids = [
                row.assertion_id for row in target_bundle.assertions
            ]
            if error is not None:
                code = str(
                    getattr(error, "code", error.__class__.__name__)
                )
                if code == "output_truncated":
                    with label_state_lock:
                        metrics.compact_truncation_count += 1
                if (
                    code in {"output_truncated", "invalid_label_cardinality"}
                    and len(assertion_ids) > 1
                    and split_depth < self.compact_split_limit
                ):
                    with label_state_lock:
                        metrics.compact_split_count += 1
                    midpoint = max(1, len(assertion_ids) // 2)
                    for child_ids in (
                        set(assertion_ids[:midpoint]),
                        set(assertion_ids[midpoint:]),
                    ):
                        execute_label(
                            self._label_review_subset(
                                target_bundle, child_ids
                            ),
                            split_depth=split_depth + 1,
                        )
                    return
                with label_state_lock:
                    metrics.fallback_failures += len(assertion_ids)
                    metrics.unresolved_bundles += 1
                    for index, assertion_id in enumerate(assertion_ids):
                        label_errors[assertion_id] = str(error)
                        label_metadata[assertion_id] = {
                            "bundle_id": target_bundle.bundle_id,
                            "request_index": index,
                            "cache_hit": False,
                            "transport": "responses",
                            "status": "technical_failure",
                            "failure_code": code,
                            **{
                                key: _wire_value(value)
                                for key, value in result["metadata"].items()
                                if key
                                in {
                                    "response_status",
                                    "incomplete_details",
                                    "reasoning_summary",
                                    "usage",
                                    "provider_call_seconds",
                                }
                            },
                        }
                return
            with label_state_lock:
                for index, (assertion_id, label) in enumerate(
                    zip(assertion_ids, result["labels"])
                ):
                    label_decisions[assertion_id] = label
                    if result["cache_hit"]:
                        label_cache_hits.add(assertion_id)
                    label_metadata[assertion_id] = {
                        "bundle_id": target_bundle.bundle_id,
                        "request_index": index,
                        "label": label,
                        "cache_hit": bool(result["cache_hit"]),
                        "transport": "responses",
                        "status": "completed",
                        **dict(result["metadata"]),
                    }

        if label_bundles:
            # Capability discovery is serialized by the client. Seed one label
            # bundle, then use bounded concurrency for the rest.
            execute_label(label_bundles[0])
            remaining_labels = label_bundles[1:]
            if remaining_labels:
                with ThreadPoolExecutor(
                    max_workers=max(1, min(workers, len(remaining_labels)))
                ) as pool:
                    pending = [
                        pool.submit(execute_label, bundle)
                        for bundle in remaining_labels
                    ]
                    for future in as_completed(pending):
                        future.result()

        accepted_by_id: dict[str, Any] = {}
        audits_by_id: dict[str, dict[str, Any]] = {}
        issues_by_id: dict[str, dict[str, Any]] = {}
        for row in primary_rows:
            bundle = row["bundle"]
            bundle_ids = {item.assertion_id for item in bundle.assertions}
            applied = apply_field_consensus(
                bundle,
                inventory,
                primary_response=row["response"],
                secondary_response=None,
                primary_error=(
                    str(row["error"]) if row["error"] is not None else None
                ),
                primary_cache_hit=bool(row["cache_hit"]),
                primary_decisions=row["decisions"],
                primary_errors=row["decision_errors"],
                secondary_label_decisions={
                    key: value
                    for key, value in label_decisions.items()
                    if key in bundle_ids
                },
                secondary_label_errors={
                    key: value
                    for key, value in label_errors.items()
                    if key in bundle_ids
                },
                secondary_label_cache_hits=label_cache_hits & bundle_ids,
                secondary_label_mode=True,
                secondary_skipped_assertion_ids=skipped_ids & bundle_ids,
            )
            accepted_by_id.update(
                zip(applied.accepted_assertion_ids, applied.accepted)
            )
            for audit in applied.audit_records:
                assertion_id = str(audit.get("assertion_id"))
                normalizations = [
                    value
                    for value in row["normalizations"]
                    if value.get("assertion_id") == assertion_id
                ]
                enriched = {
                    **dict(audit),
                    "primary_response_normalizations": normalizations,
                }
                if assertion_id in label_metadata:
                    enriched["secondary_label_review"] = {
                        **dict(enriched.get("secondary_label_review") or {}),
                        **label_metadata[assertion_id],
                    }
                audits_by_id[assertion_id] = enriched
                action = str(enriched.get("formal_action") or "")
                if action == "isolate":
                    metrics.field_isolated_assertion_count += 1
                elif action == "reassign":
                    metrics.field_reassigned_assertion_count += 1
                elif action == "preserve":
                    metrics.field_preserved_assertion_count += 1
                    metrics.preserved_unresolved_assertions += 1
            for issue in applied.issues:
                assertion_id = str(
                    (issue.get("actual") or {}).get("assertion_id")
                )
                issues_by_id[assertion_id] = dict(issue)

        ordered_ids = tuple(sorted(audits_by_id))
        accepted_ids = tuple(
            assertion_id
            for assertion_id in ordered_ids
            if assertion_id in accepted_by_id
        )
        metrics.elapsed_seconds += max(
            0.0, time.monotonic() - started - metrics.elapsed_seconds
        )
        return VerificationClientResult(
            applied=AppliedVerification(
                accepted=tuple(accepted_by_id[row] for row in accepted_ids),
                audit_records=tuple(audits_by_id[row] for row in ordered_ids),
                issues=tuple(
                    issues_by_id[row]
                    for row in ordered_ids
                    if row in issues_by_id
                ),
                decided_assertion_ids=ordered_ids,
                accepted_assertion_ids=accepted_ids,
            ),
            metrics=metrics.to_dict(),
        )

    def verify_bundle(
        self, bundle: VerificationBundle, inventory: VerificationInventory
    ) -> VerificationClientResult:
        if self.field_level:
            return self._verify_field_bundle(bundle, inventory)
        metrics = VerificationClientMetrics()
        started = time.monotonic()
        primary_error: Exception | None = None
        try:
            response, cache_hit = self._load_or_call(self.primary, bundle, metrics)
            applied = validate_and_apply_bundle(
                bundle,
                response,
                inventory,
                verifier_role="primary",
                cache_hit=cache_hit,
            )
            destructive_ids = {
                row.assertion_id
                for row in response.decisions
                if row.decision == "quarantine"
            }
            if self.destructive_consensus and destructive_ids:
                applied = self._confirm_destructive_individually(
                    bundle,
                    inventory,
                    applied,
                    response,
                    metrics,
                    origin_role="primary",
                    origin_fallback_used=False,
                    origin_cache_hit=cache_hit,
                    confirmation_config=self.fallback,
                    confirmation_role="fallback",
                )
            metrics.elapsed_seconds += max(0.0, time.monotonic() - started - metrics.elapsed_seconds)
            return VerificationClientResult(applied=applied, metrics=metrics.to_dict())
        except Exception as exc:
            primary_error = exc
            _record_exception_metrics(metrics, exc)
            metrics.primary_failures += 1
            metrics.record_failure(getattr(exc, "code", exc.__class__.__name__))

        metrics.fallback_calls += 1
        try:
            response, cache_hit = self._load_or_call(self.fallback, bundle, metrics)
            applied = validate_and_apply_bundle(
                bundle,
                response,
                inventory,
                verifier_role="fallback",
                fallback_used=True,
                cache_hit=cache_hit,
            )
            destructive_ids = {
                row.assertion_id
                for row in response.decisions
                if row.decision == "quarantine"
            }
            if self.destructive_consensus and destructive_ids:
                # The original primary request failed. The fallback role may
                # keep supported candidates flowing, but it can never become
                # sole deletion authority. Do not call the failed primary role
                # again; preserve each destructive proposal for review.
                applied = self._confirm_destructive_individually(
                    bundle,
                    inventory,
                    applied,
                    response,
                    metrics,
                    origin_role="fallback",
                    origin_fallback_used=True,
                    origin_cache_hit=cache_hit,
                    confirmation_config=self.primary,
                    confirmation_role="primary",
                    confirmation_unavailable_error=primary_error,
                )
        except Exception as exc:
            _record_exception_metrics(metrics, exc)
            metrics.fallback_failures += 1
            metrics.unresolved_bundles += 1
            metrics.split_retry_eligible = int(
                _split_retryable_error(primary_error)
                and _split_retryable_error(exc)
            )
            metrics.record_failure(getattr(exc, "code", exc.__class__.__name__))
            applied = preserve_failed_bundle_result(
                bundle,
                inventory,
                reason_code="VERIFIERS_FAILED",
                rationale=(
                    "Primary and fallback verifier roles failed; "
                    f"primary={type(primary_error).__name__}, fallback={type(exc).__name__}."
                ),
                fallback_used=True,
            )
            metrics.preserved_unresolved_assertions += len(bundle.assertions)
        metrics.elapsed_seconds += max(0.0, time.monotonic() - started - metrics.elapsed_seconds)
        return VerificationClientResult(applied=applied, metrics=metrics.to_dict())

    def recover_request(
        self,
        request: RecoveryRequest,
        inventory: VerificationInventory,
        *,
        source_text: str,
    ) -> VerificationClientResult:
        """Propose omissions, then independently verify every proposed fact."""

        metrics = VerificationClientMetrics()
        proposal_role: VerifierRole = "primary"
        proposal_cache_hit = False
        try:
            response, proposal_cache_hit = self._load_or_call_recovery(
                self.primary, request, metrics
            )
            facts = validate_recovery_response(request, response)
        except Exception as primary_error:
            _record_exception_metrics(metrics, primary_error)
            metrics.primary_failures += 1
            metrics.record_failure(
                getattr(primary_error, "code", primary_error.__class__.__name__)
            )
            metrics.fallback_calls += 1
            proposal_role = "fallback"
            try:
                response, proposal_cache_hit = self._load_or_call_recovery(
                    self.fallback, request, metrics
                )
                facts = validate_recovery_response(request, response)
            except Exception as fallback_error:
                _record_exception_metrics(metrics, fallback_error)
                metrics.fallback_failures += 1
                metrics.record_failure(
                    getattr(fallback_error, "code", fallback_error.__class__.__name__)
                )
                issue = {
                    "code": "verifier_recovery_unresolved",
                    "severity": "review",
                    "path": "materialization.recovery",
                    "message": "Both configured roles failed the bounded omission request.",
                    "evidence": [row.evidence_id for row in request.evidence],
                    "expected": {"request_id": request.request_id, "source_grounded": True},
                    "actual": {
                        "request_id": request.request_id,
                        "primary_error": type(primary_error).__name__,
                        "fallback_error": type(fallback_error).__name__,
                    },
                    "suggested_action": "Review the uncovered source spans manually.",
                }
                applied = AppliedVerification(
                    accepted=(),
                    audit_records=(
                        {
                            "assertion_id": request.request_id,
                            "bundle_id": request.request_id,
                            "protocol_version": request.protocol_version,
                            "decision": "unresolved",
                            "reason_code": "RECOVERY_ROLES_FAILED",
                            "evidence": [
                                row.model_dump(mode="json") for row in request.evidence
                            ],
                            "verifier_role": "fallback",
                            "fallback_used": True,
                            "cache_hit": False,
                            "rationale": issue["message"],
                        },
                    ),
                    issues=(issue,),
                    decided_assertion_ids=(),
                )
                return VerificationClientResult(
                    applied=applied, metrics=metrics.to_dict()
                )

        if not facts:
            return VerificationClientResult(
                applied=AppliedVerification(
                    accepted=(), audit_records=(), issues=(), decided_assertion_ids=()
                ),
                metrics=metrics.to_dict(),
            )

        proposal_by_index = list(response.proposals)
        built = build_verification_inventory(
            inventory.anchors,
            facts,
            source_text=source_text,
            task_ids=[f"recovery:{row.proposal_id}" for row in proposal_by_index],
        )
        bundles = build_verification_bundles(
            built,
            source_text=source_text,
        )
        accepted: list[Any] = []
        audits: list[dict[str, Any]] = []
        issues: list[dict[str, Any]] = []
        decided: list[str] = []
        for bundle in bundles:
            verified = self.verify_bundle(bundle, built)
            _accumulate_metrics(metrics, verified.metrics)
            accepted.extend(verified.applied.accepted)
            audits.extend(verified.applied.audit_records)
            issues.extend(verified.applied.issues)
            decided.extend(verified.applied.decided_assertion_ids)

        accepted_payloads = {
            canonical_json(row.model_dump(mode="json")): row for row in accepted
        }
        request_evidence = {row.evidence_id: row for row in request.evidence}
        for proposal, fact in zip(proposal_by_index, facts):
            payload = canonical_json(fact.model_dump(mode="json"))
            if payload not in accepted_payloads:
                continue
            assertion = next(
                (
                    row
                    for row in built.assertions
                    if row.task_id == f"recovery:{proposal.proposal_id}"
                ),
                None,
            )
            if assertion is None:
                continue
            audits.append(
                {
                    "assertion_id": assertion.assertion_id,
                    "bundle_id": request.request_id,
                    "protocol_version": request.protocol_version,
                    "decision": "recovered",
                    "reason_code": proposal.reason_code,
                    "before": None,
                    "after": fact.model_dump(mode="json"),
                    "evidence": [
                        request_evidence[evidence_id].model_dump(mode="json")
                        for evidence_id in proposal.evidence_ids
                    ],
                    "verifier_role": proposal_role,
                    "fallback_used": proposal_role == "fallback",
                    "cache_hit": proposal_cache_hit,
                    "rationale": "The uncovered literal proposal passed a separate verification request.",
                    "recovery_request_id": request.request_id,
                    "proposal_id": proposal.proposal_id,
                }
            )
            issues.append(
                {
                    "code": "verified_recovery",
                    "severity": "info",
                    "path": f"items.{fact.sample_id_raw}.{fact.axis}",
                    "message": proposal.reason_code,
                    "evidence": proposal.evidence_ids,
                    "expected": {"independent_verification": True},
                    "actual": {
                        "assertion_id": assertion.assertion_id,
                        "request_id": request.request_id,
                        "proposal_id": proposal.proposal_id,
                    },
                    "suggested_action": "Inspect the linked recovery and verification audit if disputed.",
                }
            )
        return VerificationClientResult(
            applied=AppliedVerification(
                accepted=tuple(accepted),
                audit_records=tuple(audits),
                issues=tuple(issues),
                decided_assertion_ids=tuple(sorted(set(decided))),
                accepted_assertion_ids=(),
            ),
            metrics=metrics.to_dict(),
        )


__all__ = [
    "COMPACT_REVIEW_SYSTEM_PROMPT",
    "SYSTEM_PROMPT",
    "CONFIRMATION_SYSTEM_PROMPT",
    "FIELD_REVIEW_SYSTEM_PROMPT",
    "FIELD_SYSTEM_PROMPT",
    "RECOVERY_SYSTEM_PROMPT",
    "VerificationClient",
    "VerificationClientError",
    "VerificationClientMetrics",
    "VerificationClientResult",
    "VerifierRoleConfig",
    "verifier_configs_from_env",
]
