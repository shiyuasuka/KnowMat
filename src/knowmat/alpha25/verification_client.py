"""Provider-neutral cached client for bounded Alpha25 verification bundles."""

from __future__ import annotations

import json
import os
import re
import time
from contextlib import nullcontext
from dataclasses import dataclass, field, replace
from pathlib import Path
from threading import Lock
from typing import Any, Callable, Literal
from urllib.parse import urlsplit, urlunsplit

from knowmat.alpha25.verification import (
    AppliedVerification,
    VerificationGroundingError,
    preserve_failed_bundle_result,
    unresolved_bundle_result,
    validate_and_apply_bundle,
    validate_recovery_response,
)
from knowmat.alpha25.verification_contracts import (
    VERIFICATION_PROTOCOL_VERSION,
    RecoveryRequest,
    RecoveryResponse,
    VerificationBundle,
    VerificationResponse,
    canonical_json,
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
InvokeJSON = Callable[["VerifierRoleConfig", str, str], tuple[dict[str, Any], dict[str, Any]]]


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

RECOVERY_SYSTEM_PROMPT = """You are a bounded scientific omission detector.
Use only the supplied uncovered literal evidence. Propose a non-Composition AxisFact
only when its owner, semantic, value, unit, and conditions are explicit in that
evidence or in a supplied inventory entity. Never estimate a chart or curve, convert
a qualitative comparison into a numeric scalar, copy a collective statement to each
owner, or infer an unstated value. Return compact JSON with zero or more proposals and
no markdown. Every proposal will be independently verified by a separate request.
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
    response_mode: Literal["json_object", "text"] = "json_object"
    output_token_budget: int = 4096
    timeout_seconds: int = 180
    transient_retries: int = 1

    def identity(self) -> dict[str, Any]:
        return {
            "role": self.role,
            "model": self.model,
            "endpoint": self.endpoint,
            "thinking_mode": self.thinking_mode,
            "response_mode": self.response_mode,
            "output_token_budget": self.output_token_budget,
            "timeout_seconds": self.timeout_seconds,
            "transient_retries": self.transient_retries,
        }


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
    retry_count: int = 0
    capability_fallback_count: int = 0
    elapsed_seconds: float = 0.0
    provider_call_seconds: float = 0.0
    failures_by_code: dict[str, int] = field(default_factory=dict)

    def record_failure(self, code: str) -> None:
        self.failures_by_code[code] = self.failures_by_code.get(code, 0) + 1

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
_EFFECTIVE_CAPABILITIES: dict[str, tuple[str, str]] = {}
_CAPABILITY_DISCOVERY_LOCKS: dict[str, Lock] = {}


def _capability_key(config: VerifierRoleConfig) -> str:
    return stable_id(
        "capability",
        {
            "model": config.model,
            "endpoint": config.endpoint,
            "configured_thinking_mode": config.thinking_mode,
            "configured_response_mode": config.response_mode,
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
        response_mode=effective[1],
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


def verifier_configs_from_env() -> tuple[VerifierRoleConfig, VerifierRoleConfig]:
    """Resolve role configuration without interpreting any model name."""

    endpoint = _endpoint_identity(
        os.getenv("LLM_BASE_URL") or os.getenv("OPENAI_BASE_URL") or ""
    )
    common_thinking = _mode(
        os.getenv("KNOWMAT2_ALPHA25_VERIFIER_THINKING", "provider_default")
    )
    response_mode: Literal["json_object", "text"] = (
        "json_object"
        if os.getenv(
            "KNOWMAT2_ALPHA25_VERIFIER_RESPONSE_FORMAT", "json_object"
        ).strip().casefold()
        in {"json", "json_object", "object"}
        else "text"
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
        response_mode=response_mode,
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
        response_mode=response_mode,
        output_token_budget=output_tokens,
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
            "effective_response_mode": response_mode,
        }

    while True:
        llm = get_llm(
            "extraction",
            model_override=config.model,
            thinking_mode_override=thinking,
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
        try:
            provider_calls += 1
            response = bound.invoke(
                [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ]
            )
        except Exception as exc:
            if thinking != "provider_default" and _provider_option_error(
                exc, "thinking", "coding plan"
            ):
                thinking = "provider_default"
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
        "retry_count",
        "capability_fallback_count",
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


class VerificationClient:
    """Verify bundles with primary/fallback roles and content-addressed cache."""

    def __init__(
        self,
        primary: VerifierRoleConfig,
        fallback: VerifierRoleConfig,
        *,
        cache_dir: Path | None = None,
        invoke_json: InvokeJSON | None = None,
        acquire_slot: Callable[[], None] | None = None,
        release_slot: Callable[[], None] | None = None,
        destructive_consensus: bool = False,
        confirmation_timeout_seconds: int | None = None,
        confirmation_output_token_budget: int | None = None,
    ) -> None:
        self.primary = primary
        self.fallback = fallback
        self.cache_dir = cache_dir
        self.acquire_slot = acquire_slot or (lambda: None)
        self.release_slot = release_slot or (lambda: None)
        self.destructive_consensus = bool(destructive_consensus)
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
            output_token_budget=min(
                config.output_token_budget,
                self.confirmation_output_token_budget,
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
        self, config: VerifierRoleConfig, bundle: VerificationBundle
    ) -> dict[str, Any]:
        configured = self.primary if config.role == "primary" else self.fallback
        return {
            "protocol_version": VERIFICATION_PROTOCOL_VERSION,
            "role_config": {
                "configured": configured.identity(),
                "effective": config.identity(),
            },
            "bundle": bundle.model_dump(mode="json"),
            "system_prompt": SYSTEM_PROMPT,
        }

    def _cache_path(
        self, config: VerifierRoleConfig, bundle: VerificationBundle
    ) -> Path | None:
        if self.cache_dir is None:
            return None
        identity = self._cache_identity(config, bundle)
        return self.cache_dir / config.role / f"{stable_id('verify', identity)}.json"

    def _load_or_call(
        self,
        config: VerifierRoleConfig,
        bundle: VerificationBundle,
        metrics: VerificationClientMetrics,
    ) -> tuple[VerificationResponse, bool]:
        configured = config
        guard = (
            nullcontext()
            if _capability_is_known(configured)
            else _capability_discovery_lock(configured)
        )
        with guard:
            config = _effective_config(configured)
            cache_path = self._cache_path(config, bundle)
            if cache_path is not None and cache_path.is_file():
                metrics.cache_hits += 1
                value = json.loads(cache_path.read_text(encoding="utf-8"))
                _remember_effective_capability(configured, config)
                return VerificationResponse.model_validate(value["response"]), True
            started = time.monotonic()
            value, call_metrics = self.invoke_json(
                config, SYSTEM_PROMPT, _bundle_prompt(bundle)
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
                response_mode=call_metrics.get(
                    "effective_response_mode", config.response_mode
                ),
            )
            _remember_effective_capability(configured, effective)
            try:
                response = VerificationResponse.model_validate(value)
            except Exception as exc:
                raise VerificationClientError("invalid_contract", str(exc)) from exc
            cache_path = self._cache_path(effective, bundle)
            if cache_path is not None:
                cache_path.parent.mkdir(parents=True, exist_ok=True)
                payload = {
                    "cache_record_type": "alpha25_verification_response",
                    "identity": self._cache_identity(effective, bundle),
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

    def verify_bundle(
        self, bundle: VerificationBundle, inventory: VerificationInventory
    ) -> VerificationClientResult:
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
    "SYSTEM_PROMPT",
    "RECOVERY_SYSTEM_PROMPT",
    "VerificationClient",
    "VerificationClientError",
    "VerificationClientMetrics",
    "VerificationClientResult",
    "VerifierRoleConfig",
    "verifier_configs_from_env",
]
