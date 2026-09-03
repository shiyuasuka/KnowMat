import json
from dataclasses import replace

from knowmat.alpha25.contracts import PropertyFact
from knowmat.alpha25.verification_client import (
    COMPACT_REVIEW_SYSTEM_PROMPT,
    CONFIRMATION_SYSTEM_PROMPT,
    FIELD_SYSTEM_PROMPT,
    VerificationClient,
    VerificationClientError,
    VerifierRoleConfig,
    RECOVERY_SYSTEM_PROMPT,
    _compact_label_prompt,
    _default_invoke_responses,
    verifier_configs_from_env,
)
from knowmat.alpha25.verification import required_scientific_fields
from knowmat.alpha25.verification_contracts import (
    COMPACT_REVIEW_PROTOCOL_VERSION,
    FIELD_VERIFICATION_PROTOCOL_VERSION,
)
from knowmat.alpha25.verification_inventory import (
    build_recovery_requests,
    build_verification_bundles,
    build_verification_inventory,
)


def _fact(source: str) -> PropertyFact:
    return PropertyFact(
        sample_id_raw="Sample A",
        evidence_unit_id="unit-a",
        data={
            "property_id_candidate": "temporary",
            "property_name_raw": "yield strength",
            "value_raw": "900",
            "unit_raw": "MPa",
            "test_method_raw": "tensile",
            "test_standard_raw": "",
            "test_condition_raw": "",
            "test_specimen_raw": "",
            "raw_note": "",
            "data_source": "text",
            "source_evidence": [source],
            "confidence": 0.9,
        },
        source_evidence=[source],
        confidence=0.9,
    )


def _bundle():
    source = "Sample A had a yield strength of 900 MPa."
    inventory = build_verification_inventory(
        [], [_fact(source)], source_text=source, task_ids=["task-a"]
    )
    bundle = build_verification_bundles(inventory, source_text=source)[0]
    return inventory, bundle


def _two_fact_bundle():
    first_source = "Sample A had a yield strength of 900 MPa."
    second_source = "Sample A had a yield strength of 800 MPa."
    second_payload = _fact(second_source).model_dump()
    second_payload["data"]["value_raw"] = "800"
    facts = [_fact(first_source), PropertyFact.model_validate(second_payload)]
    source = f"{first_source} {second_source}"
    inventory = build_verification_inventory(
        [], facts, source_text=source, task_ids=["task-a", "task-b"]
    )
    bundle = build_verification_bundles(
        inventory, source_text=source, max_assertions=2
    )[0]
    return inventory, bundle


def _config(role, model):
    return VerifierRoleConfig(
        role=role,
        model=model,
        endpoint="https://example.invalid/v1",
        thinking_mode="provider_default",
    )


def _responses_config(role, model):
    return VerifierRoleConfig(
        role=role,
        model=model,
        endpoint="https://example.invalid/v1",
        thinking_mode="provider_default",
        api_mode="responses",
    )


def test_compact_review_default_budget_is_1024(monkeypatch):
    monkeypatch.delenv(
        "KNOWMAT2_ALPHA25_VERIFIER_COMPACT_MAX_TOKENS", raising=False
    )

    client = VerificationClient(
        _config("primary", "model-a"),
        _config("fallback", "model-b"),
        field_level=True,
    )

    assert client.compact_output_token_budget == 1024


def test_direct_responses_transport_uses_output_text_and_keeps_key_out_of_metadata(
    monkeypatch,
):
    import openai

    observed = {}

    class FakeResponse:
        status = "completed"
        output_text = '["S"]'
        id = "response-a"
        incomplete_details = None
        output = []
        usage = {"input_tokens": 10, "output_tokens": 2}

    class FakeResponses:
        def create(self, **kwargs):
            observed["request"] = kwargs
            return FakeResponse()

    class FakeOpenAI:
        def __init__(self, **kwargs):
            observed["client"] = kwargs
            self.responses = FakeResponses()

    monkeypatch.setattr(openai, "OpenAI", FakeOpenAI)
    monkeypatch.setenv("LLM_API_KEY", "secret-key")
    config = _responses_config("fallback", "model-b")
    config = config.__class__(
        **{
            **config.__dict__,
            "reasoning_effort": "low",
            "output_token_budget": 1024,
        }
    )
    slots = []

    output, metadata = _default_invoke_responses(
        config,
        "system",
        "user",
        acquire_slot=lambda: slots.append("acquire"),
        release_slot=lambda: slots.append("release"),
    )

    assert output == '["S"]'
    assert observed["request"]["max_output_tokens"] == 1024
    assert observed["request"]["reasoning"] == {
        "effort": "low",
        "summary": "concise",
    }
    assert observed["client"]["api_key"] == "secret-key"
    assert "secret-key" not in json.dumps(metadata)
    assert metadata["response_status"] == "completed"
    assert slots == ["acquire", "release"]


def _accept(bundle):
    return {
        "protocol_version": bundle.protocol_version,
        "bundle_id": bundle.bundle_id,
        "decisions": [
            {
                "assertion_id": bundle.assertions[0].assertion_id,
                "decision": "accept",
                "evidence_ids": [row.evidence_id for row in bundle.evidence],
                "reason_code": "SOURCE_SUPPORTED",
                "rationale": "Literal source evidence supports the candidate.",
                "merge_member_ids": [],
                "survivor_assertion_id": None,
                "reassignment": None,
            }
        ],
    }


def _quarantine(bundle):
    return {
        "protocol_version": bundle.protocol_version,
        "bundle_id": bundle.bundle_id,
        "decisions": [
            {
                "assertion_id": row.assertion_id,
                "decision": "quarantine",
                "evidence_ids": [evidence.evidence_id for evidence in bundle.evidence],
                "reason_code": "UNSUPPORTED_OWNER",
                "rationale": "The supplied evidence does not support the owner.",
                "merge_member_ids": [],
                "survivor_assertion_id": None,
                "reassignment": None,
            }
            for row in bundle.assertions
        ],
    }


def _requested_bundle(template, user):
    payload = json.loads(user)
    assertions = payload.get("assertions")
    if assertions is None:
        assertions = [payload["assertion"]]
    return type(template)(
        protocol_version=payload["protocol_version"],
        bundle_id=payload["bundle_id"],
        axis=payload["axis"],
        assertions=assertions,
        entities=payload.get("inventory_entities", []),
        evidence=payload["evidence"],
        source_char_count=sum(len(row["text"]) for row in payload["evidence"]),
    )


def _field_supported(payload, *, owner_verdict="supported"):
    decisions = []
    for assertion in payload["assertions"]:
        fields = []
        for field in payload["required_fields"][assertion["assertion_id"]]:
            fields.append(
                {
                    "field": field,
                    "verdict": (
                        owner_verdict if field == "owner" else "supported"
                    ),
                    "evidence_ids": assertion["evidence_ids"],
                    "selected_entity_id": None,
                    "selected_text": None,
                }
            )
        decisions.append(
            {
                "assertion_id": assertion["assertion_id"],
                "fields": fields,
                "reason_code": "FIELD_REVIEW_COMPLETE",
                "rationale": "Every required field was reviewed independently.",
            }
        )
    return {
        "protocol_version": FIELD_VERIFICATION_PROTOCOL_VERSION,
        "bundle_id": payload["bundle_id"],
        "decisions": decisions,
    }


def _compact_review(payload, *, verdict="all_fields_supported"):
    return {
        "protocol_version": COMPACT_REVIEW_PROTOCOL_VERSION,
        "bundle_id": payload["bundle_id"],
        "decisions": [
            {
                "assertion_id": assertion["assertion_id"],
                "verdict": verdict,
                "evidence_ids": assertion["evidence_ids"],
                "failed_fields": (
                    [] if verdict == "all_fields_supported" else ["owner"]
                ),
                "reason_code": (
                    "ALL_FIELDS_SUPPORTED"
                    if verdict == "all_fields_supported"
                    else "OWNER_NOT_PROVEN"
                ),
            }
            for assertion in payload["assertions"]
        ],
    }


def test_primary_success_uses_one_call_and_no_fallback(tmp_path):
    inventory, bundle = _bundle()
    calls = []

    def invoke(config, _system, _user):
        calls.append(config.role)
        return _accept(bundle), {"provider_calls": 1, "provider_call_seconds": 1.5}

    client = VerificationClient(
        _config("primary", "model-a"),
        _config("fallback", "model-b"),
        cache_dir=tmp_path,
        invoke_json=invoke,
    )
    result = client.verify_bundle(bundle, inventory)
    assert len(result.applied.accepted) == 1
    assert calls == ["primary"]
    assert result.metrics["provider_calls"] == 1
    assert result.metrics["fallback_calls"] == 0


def test_destructive_consensus_preserves_primary_quarantine_on_disagreement():
    inventory, bundle = _bundle()
    calls = []

    def invoke(config, _system, user):
        calls.append(config.role)
        requested = _requested_bundle(bundle, user)
        value = _quarantine(requested) if config.role == "primary" else _accept(requested)
        return value, {"provider_calls": 1}

    client = VerificationClient(
        _config("primary", "model-a"),
        _config("fallback", "model-b"),
        invoke_json=invoke,
        destructive_consensus=True,
    )
    result = client.verify_bundle(bundle, inventory)

    assert calls == ["primary", "fallback"]
    assert len(result.applied.accepted) == 1
    assert result.applied.audit_records[0]["decision"] == "unresolved"
    assert result.applied.audit_records[0]["secondary_confirmation"]["decision"] == "accept"
    assert result.applied.issues[0]["code"] == "verifier_unresolved_preserved"
    assert result.metrics["destructive_candidate_count"] == 1
    assert result.metrics["confirmed_quarantine_count"] == 0
    assert result.metrics["preserved_destructive_disagreement_count"] == 1


def test_destructive_consensus_quarantines_only_when_both_roles_agree():
    inventory, bundle = _bundle()
    observed_timeouts = []
    observed_output_budgets = []
    observed_system_prompts = []
    observed_payloads = []

    def invoke(config, system, user):
        observed_timeouts.append(config.timeout_seconds)
        observed_output_budgets.append(config.output_token_budget)
        observed_system_prompts.append(system)
        observed_payloads.append(json.loads(user))
        requested = _requested_bundle(bundle, user)
        return _quarantine(requested), {"provider_calls": 1}

    client = VerificationClient(
        _config("primary", "model-a"),
        _config("fallback", "model-b"),
        invoke_json=invoke,
        destructive_consensus=True,
        confirmation_timeout_seconds=321,
        confirmation_output_token_budget=777,
    )
    result = client.verify_bundle(bundle, inventory)

    assert result.applied.accepted == ()
    assert result.applied.audit_records[0]["decision"] == "quarantine"
    assert result.applied.audit_records[0]["secondary_confirmation"]["decision"] == "quarantine"
    assert result.applied.issues[0]["code"] == "verifier_quarantine_consensus"
    assert observed_timeouts == [180, 321]
    assert observed_output_budgets == [4096, 777]
    assert observed_system_prompts[1] == CONFIRMATION_SYSTEM_PROMPT
    assert "assertion" in observed_payloads[1]
    assert "assertions" not in observed_payloads[1]
    assert "inventory_entities" not in observed_payloads[1]
    assert (
        observed_payloads[1]["response_shape"]["decisions"][0]["decision"]
        == "accept|quarantine|unresolved"
    )
    assert result.metrics["destructive_confirmation_calls"] == 1
    assert result.metrics["confirmed_quarantine_count"] == 1


def test_confirmation_budget_is_independent_from_primary_bundle_budget():
    inventory, bundle = _bundle()
    observed_output_budgets = []

    def invoke(config, _system, user):
        observed_output_budgets.append(config.output_token_budget)
        requested = _requested_bundle(bundle, user)
        return _quarantine(requested), {"provider_calls": 1}

    primary = _config("primary", "model-a")
    primary = VerifierRoleConfig(
        **{**primary.__dict__, "output_token_budget": 768}
    )
    client = VerificationClient(
        primary,
        _config("fallback", "model-b"),
        invoke_json=invoke,
        destructive_consensus=True,
        confirmation_output_token_budget=2048,
    )

    result = client.verify_bundle(bundle, inventory)

    assert result.metrics["confirmed_quarantine_count"] == 1
    assert observed_output_budgets == [768, 2048]


def test_confirmation_defaults_to_low_reasoning_effort_independent_from_primary_role(
    monkeypatch,
):
    monkeypatch.delenv(
        "KNOWMAT2_ALPHA25_VERIFIER_CONFIRMATION_REASONING_EFFORT", raising=False
    )
    inventory, bundle = _bundle()
    observed_reasoning_efforts = []

    def invoke(config, _system, user):
        observed_reasoning_efforts.append(config.reasoning_effort)
        requested = _requested_bundle(bundle, user)
        return _quarantine(requested), {"provider_calls": 1}

    client = VerificationClient(
        _config("primary", "model-a"),
        _config("fallback", "model-b"),
        invoke_json=invoke,
        destructive_consensus=True,
    )

    result = client.verify_bundle(bundle, inventory)

    assert result.metrics["confirmed_quarantine_count"] == 1
    assert observed_reasoning_efforts == ["provider_default", "low"]


def test_destructive_consensus_preserves_when_confirmation_fails():
    inventory, bundle = _bundle()

    def invoke(config, _system, user):
        requested = _requested_bundle(bundle, user)
        if config.role == "fallback":
            raise VerificationClientError("output_truncated", "confirmation")
        return _quarantine(requested), {"provider_calls": 1}

    client = VerificationClient(
        _config("primary", "model-a"),
        _config("fallback", "model-b"),
        invoke_json=invoke,
        destructive_consensus=True,
    )
    result = client.verify_bundle(bundle, inventory)

    assert len(result.applied.accepted) == 1
    assert result.applied.audit_records[0]["reason_code"] == "DESTRUCTIVE_CONFIRMATION_FAILED"
    assert result.metrics["destructive_confirmation_failures"] == 1


def test_destructive_confirmation_failure_is_isolated_per_candidate():
    inventory, bundle = _two_fact_bundle()
    failure_id = sorted(row.assertion_id for row in bundle.assertions)[0]
    assertion_evidence = {
        row.assertion_id: set(row.evidence_ids) for row in bundle.assertions
    }
    confirmation_ids = []

    def invoke(config, _system, user):
        requested = _requested_bundle(bundle, user)
        if config.role == "fallback":
            assert len(requested.assertions) == 1
            assertion_id = requested.assertions[0].assertion_id
            confirmation_ids.append(assertion_id)
            sibling_evidence = set().union(
                *(
                    evidence_ids
                    for candidate_id, evidence_ids in assertion_evidence.items()
                    if candidate_id != assertion_id
                )
            )
            assert not sibling_evidence & {
                row.evidence_id for row in requested.evidence
            }
            if assertion_id == failure_id:
                raise VerificationClientError("output_truncated", "confirmation")
        return _quarantine(requested), {"provider_calls": 1}

    client = VerificationClient(
        _config("primary", "model-a"),
        _config("fallback", "model-b"),
        invoke_json=invoke,
        destructive_consensus=True,
    )
    result = client.verify_bundle(bundle, inventory)

    assert sorted(confirmation_ids) == sorted(
        row.assertion_id for row in bundle.assertions
    )
    assert len(result.applied.accepted) == 1
    assert result.metrics["destructive_confirmation_calls"] == 2
    assert result.metrics["destructive_confirmation_failures"] == 1
    assert result.metrics["confirmed_quarantine_count"] == 1
    assert result.metrics["preserved_destructive_disagreement_count"] == 1


def test_destructive_consensus_never_deletes_after_primary_technical_failure():
    inventory, bundle = _bundle()
    calls = []

    def invoke(config, _system, user):
        calls.append(config.role)
        if config.role == "primary":
            raise VerificationClientError("provider_timeout", "primary")
        requested = _requested_bundle(bundle, user)
        return _quarantine(requested), {"provider_calls": 1}

    client = VerificationClient(
        _config("primary", "model-a"),
        _config("fallback", "model-b"),
        invoke_json=invoke,
        destructive_consensus=True,
    )
    result = client.verify_bundle(bundle, inventory)

    assert len(result.applied.accepted) == 1
    assert calls == ["primary", "fallback"]
    assert result.applied.issues[0]["code"] == "verifier_unresolved_preserved"
    audit = result.applied.audit_records[0]
    assert audit["proposed_destructive_decision"]["decision"] == "quarantine"
    assert audit["secondary_confirmation"]["decision"] == "technical_failure"
    assert audit["secondary_confirmation"]["reason_code"] == "provider_timeout"
    assert result.metrics["primary_failures"] == 1
    assert result.metrics["destructive_confirmation_calls"] == 0
    assert result.metrics["destructive_confirmation_failures"] == 0
    assert result.metrics["destructive_confirmation_skipped_count"] == 1
    assert result.metrics["confirmed_quarantine_count"] == 0
    assert result.metrics["preserved_destructive_disagreement_count"] == 1


def test_grounding_failure_falls_back_by_bundle(tmp_path):
    inventory, bundle = _bundle()
    calls = []

    def invoke(config, _system, _user):
        calls.append(config.role)
        value = _accept(bundle)
        if config.role == "primary":
            value["decisions"][0]["evidence_ids"] = ["invented"]
        return value, {"provider_calls": 1}

    client = VerificationClient(
        _config("primary", "model-a"),
        _config("fallback", "model-b"),
        cache_dir=tmp_path,
        invoke_json=invoke,
    )
    result = client.verify_bundle(bundle, inventory)
    assert len(result.applied.accepted) == 1
    assert calls == ["primary", "fallback"]
    assert result.applied.audit_records[0]["verifier_role"] == "fallback"
    assert result.metrics["primary_failures"] == 1


def test_double_failure_is_explicit_unresolved_and_preserved_for_review(tmp_path):
    inventory, bundle = _bundle()

    def invoke(config, _system, _user):
        raise VerificationClientError("output_truncated", config.role)

    client = VerificationClient(
        _config("primary", "model-a"),
        _config("fallback", "model-b"),
        cache_dir=tmp_path,
        invoke_json=invoke,
    )
    result = client.verify_bundle(bundle, inventory)
    assert len(result.applied.accepted) == 1
    assert result.applied.audit_records[0]["decision"] == "unresolved"
    assert result.applied.audit_records[0]["after"] is not None
    assert result.applied.issues[0]["code"] == "verifier_unresolved_preserved"
    assert result.metrics["unresolved_bundles"] == 1
    assert result.metrics["preserved_unresolved_assertions"] == 1
    assert result.metrics["failures_by_code"] == {"output_truncated": 2}


def test_cache_identity_separates_role_model_and_bundle(tmp_path):
    inventory, bundle = _bundle()
    calls = []

    def invoke(config, _system, _user):
        calls.append(config.model)
        return _accept(bundle), {"provider_calls": 1}

    first = VerificationClient(
        _config("primary", "model-a"),
        _config("fallback", "model-b"),
        cache_dir=tmp_path,
        invoke_json=invoke,
    )
    assert len(first.verify_bundle(bundle, inventory).applied.accepted) == 1
    assert first.verify_bundle(bundle, inventory).metrics["cache_hits"] == 1

    second = VerificationClient(
        _config("primary", "model-c"),
        _config("fallback", "model-b"),
        cache_dir=tmp_path,
        invoke_json=invoke,
    )
    assert len(second.verify_bundle(bundle, inventory).applied.accepted) == 1
    assert calls == ["model-a", "model-c"]
    identities = [
        json.loads(path.read_text())["identity"]["role_config"]["effective"]["model"]
        for path in tmp_path.glob("primary/*.json")
    ]
    assert sorted(identities) == ["model-a", "model-c"]


def test_env_configuration_has_no_model_name_behavior(monkeypatch):
    monkeypatch.setenv("LLM_BASE_URL", "https://user:secret@example.test/v1?token=x")
    monkeypatch.setenv("KNOWMAT2_ALPHA25_VERIFIER_MODEL", "future-primary")
    monkeypatch.setenv("KNOWMAT2_ALPHA25_VERIFIER_FALLBACK_MODEL", "future-fallback")
    monkeypatch.setenv("KNOWMAT2_ALPHA25_VERIFIER_THINKING", "disabled")
    monkeypatch.setenv("KNOWMAT2_ALPHA25_VERIFIER_REASONING_EFFORT", "low")
    monkeypatch.setenv(
        "KNOWMAT2_ALPHA25_VERIFIER_API_MODE", "chat_completions"
    )
    monkeypatch.setenv(
        "KNOWMAT2_ALPHA25_VERIFIER_FALLBACK_API_MODE", "responses"
    )
    primary, fallback = verifier_configs_from_env()
    assert primary.model == "future-primary"
    assert fallback.model == "future-fallback"
    assert primary.thinking_mode == "disabled"
    assert primary.reasoning_effort == "low"
    assert primary.api_mode == "chat_completions"
    assert fallback.api_mode == "responses"
    assert primary.endpoint == "https://example.test/v1"
    assert "secret" not in json.dumps(primary.identity())


def test_api_mode_is_role_config_not_model_behavior(monkeypatch):
    monkeypatch.setenv("KNOWMAT2_ALPHA25_VERIFIER_MODEL", "model-one")
    monkeypatch.setenv("KNOWMAT2_ALPHA25_VERIFIER_FALLBACK_MODEL", "model-two")
    monkeypatch.setenv("KNOWMAT2_ALPHA25_VERIFIER_API_MODE", "responses_api")
    monkeypatch.delenv(
        "KNOWMAT2_ALPHA25_VERIFIER_FALLBACK_API_MODE", raising=False
    )

    primary, fallback = verifier_configs_from_env()

    assert primary.api_mode == fallback.api_mode == "responses"
    assert primary.identity()["api_mode"] == "responses"
    assert fallback.identity()["api_mode"] == "responses"


def test_fallback_defaults_to_low_reasoning_without_model_name_behavior(monkeypatch):
    monkeypatch.delenv("KNOWMAT2_ALPHA25_VERIFIER_REASONING_EFFORT", raising=False)
    monkeypatch.delenv(
        "KNOWMAT2_ALPHA25_VERIFIER_FALLBACK_REASONING_EFFORT", raising=False
    )
    monkeypatch.setenv("KNOWMAT2_ALPHA25_VERIFIER_MODEL", "future-primary")
    monkeypatch.setenv("KNOWMAT2_ALPHA25_VERIFIER_FALLBACK_MODEL", "future-fallback")

    primary, fallback = verifier_configs_from_env()

    assert primary.reasoning_effort == "provider_default"
    assert fallback.reasoning_effort == "low"


def test_recovery_requires_a_separate_verification_call(tmp_path):
    source = "Sample B had an elongation of 12 %."
    inventory = build_verification_inventory([], [], source_text=source)
    request = build_recovery_requests(inventory)[0]
    calls = []

    def invoke(config, system, user):
        payload = json.loads(user)
        if system == RECOVERY_SYSTEM_PROMPT:
            calls.append((config.role, "recover"))
            evidence = request.evidence[0]
            fact = _fact(source).model_dump(mode="json")
            fact["sample_id_raw"] = "Sample B"
            fact["data"].update(
                {
                    "property_name_raw": "elongation",
                    "value_raw": "12",
                    "unit_raw": "%",
                }
            )
            return {
                "protocol_version": request.protocol_version,
                "proposals": [
                    {
                        "proposal_id": "proposal-1",
                        "axis": "properties",
                        "candidate": fact,
                        "evidence_ids": [evidence.evidence_id],
                        "reason_code": "UNCOVERED_LITERAL_FACT",
                    }
                ],
            }, {"provider_calls": 1}
        calls.append((config.role, "verify"))
        assertion = payload["assertions"][0]
        evidence = payload["evidence"][0]
        return {
            "protocol_version": payload["protocol_version"],
            "bundle_id": payload["bundle_id"],
            "decisions": [
                {
                    "assertion_id": assertion["assertion_id"],
                    "decision": "accept",
                    "evidence_ids": [evidence["evidence_id"]],
                    "reason_code": "SOURCE_SUPPORTED",
                    "rationale": "The recovered fact is literal.",
                    "merge_member_ids": [],
                    "survivor_assertion_id": None,
                    "reassignment": None,
                }
            ],
        }, {"provider_calls": 1}

    client = VerificationClient(
        _config("primary", "model-a"),
        _config("fallback", "model-b"),
        cache_dir=tmp_path,
        invoke_json=invoke,
    )
    result = client.recover_request(
        request, inventory, source_text=source
    )
    assert calls == [("primary", "recover"), ("primary", "verify")]
    assert len(result.applied.accepted) == 1
    assert result.applied.accepted[0].data["value_raw"] == "12"
    assert any(row["decision"] == "recovered" for row in result.applied.audit_records)
    assert result.metrics["provider_calls"] == 2


def test_recovery_double_failure_produces_review_audit(tmp_path):
    source = "Sample B had an elongation of 12 %."
    inventory = build_verification_inventory([], [], source_text=source)
    request = build_recovery_requests(inventory)[0]

    def invoke(config, _system, _user):
        raise VerificationClientError("provider_error", config.role)

    client = VerificationClient(
        _config("primary", "model-a"),
        _config("fallback", "model-b"),
        cache_dir=tmp_path,
        invoke_json=invoke,
    )
    result = client.recover_request(request, inventory, source_text=source)
    assert result.applied.accepted == ()
    assert result.applied.issues[0]["code"] == "verifier_recovery_unresolved"
    assert result.applied.audit_records[0]["decision"] == "unresolved"


def test_effective_capability_is_reused_across_bundle_calls():
    inventory, bundle = _bundle()
    observed = []
    primary = VerifierRoleConfig(
        role="primary",
        model="capability-reuse-model",
        endpoint="https://capability.example.invalid/v1",
        thinking_mode="disabled",
    )

    def invoke(config, _system, _user):
        observed.append(config.thinking_mode)
        return _accept(bundle), {
            "provider_calls": 1,
            "capability_fallback_count": 1 if len(observed) == 1 else 0,
            "effective_thinking_mode": "provider_default",
            "effective_reasoning_effort": "provider_default",
            "effective_response_mode": "json_object",
        }

    client = VerificationClient(
        primary,
        _config("fallback", "fallback-capability-model"),
        invoke_json=invoke,
    )
    assert len(client.verify_bundle(bundle, inventory).applied.accepted) == 1
    assert len(client.verify_bundle(bundle, inventory).applied.accepted) == 1
    assert observed == ["disabled", "provider_default"]


def test_failed_provider_attempts_remain_in_metrics():
    inventory, bundle = _bundle()

    def invoke(config, _system, _user):
        raise VerificationClientError(
            "provider_error",
            config.role,
            metrics={
                "provider_calls": 2,
                "provider_call_seconds": 3.0,
                "retry_count": 1,
            },
        )

    client = VerificationClient(
        _config("primary", "metrics-primary-model"),
        _config("fallback", "metrics-fallback-model"),
        invoke_json=invoke,
    )
    result = client.verify_bundle(bundle, inventory)
    assert len(result.applied.accepted) == 1
    assert result.applied.issues[0]["code"] == "verifier_unresolved_preserved"
    assert result.metrics["preserved_unresolved_assertions"] == 1
    assert result.metrics["provider_calls"] == 4
    assert result.metrics["provider_call_seconds"] == 6.0
    assert result.metrics["retry_count"] == 2


def _risk_bundle(bundle, severity):
    return bundle.model_copy(
        update={
            "assertions": [
                row.model_copy(
                    update={
                        "risk_severity": severity,
                        "risk_codes": [f"{severity}_test_risk"],
                    }
                )
                for row in bundle.assertions
            ]
        }
    )


def test_field_level_hard_risk_uses_blind_independent_roles():
    inventory, raw_bundle = _bundle()
    bundle = _risk_bundle(raw_bundle, "hard")
    observed = []

    def invoke(config, system, user):
        payload = json.loads(user)
        observed.append((config.role, system, payload))
        response = (
            _compact_review(payload)
            if payload["protocol_version"] == COMPACT_REVIEW_PROTOCOL_VERSION
            else _field_supported(payload)
        )
        return response, {"provider_calls": 1}

    client = VerificationClient(
        _config("primary", "model-a"),
        _config("fallback", "model-b"),
        invoke_json=invoke,
        field_level=True,
    )
    result = client.verify_bundle(bundle, inventory)

    assert result.applied.accepted == (inventory.facts_by_assertion_id[bundle.assertions[0].assertion_id],)
    by_role = {row[0]: row for row in observed}
    assert set(by_role) == {"primary", "fallback"}
    assert by_role["primary"][1] == FIELD_SYSTEM_PROMPT
    assert "nested value_raw/unit_raw" in FIELD_SYSTEM_PROMPT
    assert "region" in FIELD_SYSTEM_PROMPT
    assert by_role["fallback"][1] == COMPACT_REVIEW_SYSTEM_PROMPT
    assert by_role["primary"][2]["protocol_version"] == FIELD_VERIFICATION_PROTOCOL_VERSION
    assert by_role["primary"][2]["required_fields"][bundle.assertions[0].assertion_id] == [
        "semantic",
        "value",
        "unit",
        "owner",
    ]
    assert by_role["fallback"][2]["protocol_version"] == (
        COMPACT_REVIEW_PROTOCOL_VERSION
    )
    assert "primary" not in json.dumps(by_role["fallback"][2]).casefold()
    assert result.metrics["field_primary_calls"] == 1
    assert result.metrics["field_secondary_calls"] == 1
    assert result.metrics["compact_secondary_calls"] == 1
    assert result.metrics["field_hard_assertion_count"] == 1


def test_field_level_hard_primary_finishes_before_compact_review_starts():
    inventory, raw_bundle = _bundle()
    bundle = _risk_bundle(raw_bundle, "hard")
    observed = []

    def invoke(config, _system, user):
        payload = json.loads(user)
        observed.append((config.role, payload["protocol_version"]))
        response = (
            _compact_review(payload)
            if payload["protocol_version"] == COMPACT_REVIEW_PROTOCOL_VERSION
            else _field_supported(payload)
        )
        return response, {"provider_calls": 1}

    client = VerificationClient(
        _config("primary", "model-a"),
        _config("fallback", "model-b"),
        invoke_json=invoke,
        field_level=True,
    )

    result = client.verify_bundle(bundle, inventory)

    assert result.applied.accepted
    assert observed == [
        ("primary", FIELD_VERIFICATION_PROTOCOL_VERSION),
        ("fallback", COMPACT_REVIEW_PROTOCOL_VERSION),
    ]
    assert result.metrics["provider_calls"] == 2


def test_field_level_primary_and_compact_review_both_pack_related_assertions():
    inventory, raw_bundle = _two_fact_bundle()
    bundle = _risk_bundle(raw_bundle, "hard")
    observed = []

    def invoke(config, _system, user):
        payload = json.loads(user)
        observed.append((config.role, len(payload["assertions"])))
        response = (
            _compact_review(payload)
            if payload["protocol_version"] == COMPACT_REVIEW_PROTOCOL_VERSION
            else _field_supported(payload)
        )
        return response, {"provider_calls": 1}

    client = VerificationClient(
        _config("primary", "model-a"),
        _config("fallback", "model-b"),
        invoke_json=invoke,
        field_level=True,
    )

    result = client.verify_bundle(bundle, inventory)

    assert len(result.applied.accepted) == 2
    assert observed.count(("primary", 2)) == 1
    assert observed.count(("fallback", 2)) == 1
    assert result.metrics["field_primary_calls"] == 1
    assert result.metrics["field_secondary_calls"] == 1
    assert result.metrics["provider_calls"] == 2


def test_field_level_invalid_sibling_does_not_poison_valid_primary_decision():
    inventory, raw_bundle = _two_fact_bundle()
    bundle = _risk_bundle(raw_bundle, "hard")
    invalid_id = bundle.assertions[0].assertion_id

    def invoke(config, _system, user):
        payload = json.loads(user)
        if payload["protocol_version"] == COMPACT_REVIEW_PROTOCOL_VERSION:
            return _compact_review(payload), {"provider_calls": 1}
        response = _field_supported(payload)
        if config.role == "primary":
            invalid = next(
                row
                for row in response["decisions"]
                if row["assertion_id"] == invalid_id
            )
            invalid["fields"][0]["evidence_ids"] = ["invented-evidence"]
        return response, {"provider_calls": 1}

    client = VerificationClient(
        _config("primary", "model-a"),
        _config("fallback", "model-b"),
        invoke_json=invoke,
        field_level=True,
    )

    result = client.verify_bundle(bundle, inventory)

    assert len(result.applied.accepted) == 1
    accepted_id = result.applied.accepted_assertion_ids[0]
    assert accepted_id != invalid_id
    audits = {row["assertion_id"]: row for row in result.applied.audit_records}
    assert audits[invalid_id]["formal_action"] == "isolate"
    assert audits[accepted_id]["formal_action"] == "accept"


def test_field_level_invalid_soft_sibling_is_preserved_without_bundle_failure():
    inventory, raw_bundle = _two_fact_bundle()
    bundle = _risk_bundle(raw_bundle, "soft")
    invalid_id = bundle.assertions[0].assertion_id

    def invoke(_config, _system, user):
        payload = json.loads(user)
        response = _field_supported(payload)
        invalid = next(
            row
            for row in response["decisions"]
            if row["assertion_id"] == invalid_id
        )
        invalid["fields"][0]["evidence_ids"] = ["invented-evidence"]
        return response, {"provider_calls": 1}

    client = VerificationClient(
        _config("primary", "model-a"),
        _config("fallback", "model-b"),
        invoke_json=invoke,
        field_level=True,
    )

    result = client.verify_bundle(bundle, inventory)

    assert len(result.applied.accepted) == 2
    audits = {row["assertion_id"]: row for row in result.applied.audit_records}
    assert audits[invalid_id]["formal_action"] == "preserve"
    assert audits[invalid_id]["primary_field_review"]["decision"] == (
        "technical_failure"
    )
    assert result.applied.issues[0]["code"] == "verifier_soft_risk_preserved"


def test_field_response_repairs_inactive_targets_and_audits_them(tmp_path):
    inventory, raw_bundle = _bundle()
    bundle = _risk_bundle(raw_bundle, "hard")

    def invoke(_config, _system, user):
        payload = json.loads(user)
        if payload["protocol_version"] == COMPACT_REVIEW_PROTOCOL_VERSION:
            return _compact_review(payload), {"provider_calls": 1}
        response = _field_supported(payload)
        owner = next(
            row
            for row in response["decisions"][0]["fields"]
            if row["field"] == "owner"
        )
        owner["selected_entity_id"] = "inactive-entity"
        owner["selected_text"] = "inactive text"
        return response, {"provider_calls": 1}

    client = VerificationClient(
        _config("primary", "model-a"),
        _config("fallback", "model-b"),
        cache_dir=tmp_path,
        invoke_json=invoke,
        field_level=True,
    )

    result = client.verify_bundle(bundle, inventory)

    assert result.applied.accepted
    assert result.metrics["field_shape_normalization_count"] == 1
    audit = result.applied.audit_records[0]
    assert audit["primary_response_normalizations"][0]["code"] == (
        "inactive_correction_target_removed"
    )
    assert audit["secondary_response_normalizations"] == []
    field_rows = [
        json.loads(path.read_text()) for path in tmp_path.glob("*_field/*.json")
    ]
    compact_rows = [
        json.loads(path.read_text())
        for path in tmp_path.glob("*_compact/*.json")
    ]
    assert len(field_rows) == len(compact_rows) == 1
    assert field_rows[0]["raw_response"]
    assert field_rows[0]["response_normalizations"]


def test_field_response_normalizations_are_scoped_to_their_assertion():
    inventory, raw_bundle = _two_fact_bundle()
    bundle = _risk_bundle(raw_bundle, "hard")
    normalized_id = bundle.assertions[0].assertion_id

    def invoke(_config, _system, user):
        payload = json.loads(user)
        if payload["protocol_version"] == COMPACT_REVIEW_PROTOCOL_VERSION:
            return _compact_review(payload), {"provider_calls": 1}
        response = _field_supported(payload)
        for decision in response["decisions"]:
            if decision["assertion_id"] != normalized_id:
                continue
            owner = next(
                row for row in decision["fields"] if row["field"] == "owner"
            )
            owner["selected_entity_id"] = "inactive-entity"
            owner["selected_text"] = "inactive text"
        return response, {"provider_calls": 1}

    client = VerificationClient(
        _config("primary", "model-a"),
        _config("fallback", "model-b"),
        invoke_json=invoke,
        field_level=True,
    )

    result = client.verify_bundle(bundle, inventory)

    audits = {row["assertion_id"]: row for row in result.applied.audit_records}
    normalized = audits[normalized_id]
    untouched = next(
        row for assertion_id, row in audits.items() if assertion_id != normalized_id
    )
    assert normalized["primary_response_normalizations"]
    assert normalized["secondary_response_normalizations"] == []
    assert untouched["primary_response_normalizations"] == []
    assert untouched["secondary_response_normalizations"] == []


def test_field_level_soft_supported_fact_skips_second_role():
    inventory, raw_bundle = _bundle()
    bundle = _risk_bundle(raw_bundle, "soft")
    calls = []

    def invoke(config, _system, user):
        calls.append(config.role)
        return _field_supported(json.loads(user)), {"provider_calls": 1}

    client = VerificationClient(
        _config("primary", "model-a"),
        _config("fallback", "model-b"),
        invoke_json=invoke,
        field_level=True,
    )
    result = client.verify_bundle(bundle, inventory)

    assert len(result.applied.accepted) == 1
    assert calls == ["primary"]
    assert result.metrics["field_secondary_calls"] == 0


def test_field_level_hard_disagreement_isolates_formal_fact():
    inventory, raw_bundle = _bundle()
    bundle = _risk_bundle(raw_bundle, "hard")

    def invoke(config, _system, user):
        payload = json.loads(user)
        if payload["protocol_version"] == COMPACT_REVIEW_PROTOCOL_VERSION:
            return _compact_review(payload, verdict="not_proven"), {
                "provider_calls": 1
            }
        return _field_supported(payload), {"provider_calls": 1}

    client = VerificationClient(
        _config("primary", "model-a"),
        _config("fallback", "model-b"),
        invoke_json=invoke,
        field_level=True,
    )
    result = client.verify_bundle(bundle, inventory)

    assert result.applied.accepted == ()
    assert result.applied.issues[0]["code"] == "verifier_hard_risk_isolated"
    assert result.metrics["field_isolated_assertion_count"] == 1


def test_compact_review_truncation_splits_multi_assertion_bundle_once():
    inventory, raw_bundle = _two_fact_bundle()
    bundle = _risk_bundle(raw_bundle, "hard")
    fallback_sizes = []

    def invoke(_config, _system, user):
        payload = json.loads(user)
        if payload["protocol_version"] == COMPACT_REVIEW_PROTOCOL_VERSION:
            fallback_sizes.append(len(payload["assertions"]))
            if len(payload["assertions"]) > 1:
                raise VerificationClientError(
                    "output_truncated",
                    metrics={"provider_calls": 1},
                )
            return _compact_review(payload), {"provider_calls": 1}
        return _field_supported(payload), {"provider_calls": 1}

    client = VerificationClient(
        _config("primary", "model-a"),
        _config("fallback", "model-b"),
        invoke_json=invoke,
        field_level=True,
        compact_split_limit=1,
    )

    result = client.verify_bundle(bundle, inventory)

    assert len(result.applied.accepted) == 2
    assert fallback_sizes == [2, 1, 1]
    assert result.metrics["compact_split_count"] == 1
    assert result.metrics["compact_truncation_count"] == 1
    assert result.metrics["provider_calls"] == 4


def test_compact_singleton_truncation_is_not_retried_or_expanded():
    inventory, raw_bundle = _bundle()
    bundle = _risk_bundle(raw_bundle, "hard")
    calls = []

    def invoke(config, _system, user):
        payload = json.loads(user)
        calls.append(config.role)
        if payload["protocol_version"] == COMPACT_REVIEW_PROTOCOL_VERSION:
            raise VerificationClientError(
                "output_truncated",
                metrics={"provider_calls": 1},
            )
        return _field_supported(payload), {"provider_calls": 1}

    client = VerificationClient(
        _config("primary", "model-a"),
        _config("fallback", "model-b"),
        invoke_json=invoke,
        field_level=True,
        compact_split_limit=1,
    )

    result = client.verify_bundle(bundle, inventory)

    assert calls == ["primary", "fallback"]
    assert result.applied.accepted == ()
    assert result.metrics["compact_split_count"] == 0
    assert result.metrics["compact_truncation_count"] == 1
    assert result.metrics["provider_calls"] == 2


def test_field_level_hard_double_failure_isolates_with_complete_audit():
    inventory, raw_bundle = _bundle()
    bundle = _risk_bundle(raw_bundle, "hard")
    calls = []

    def invoke(config, _system, _user):
        calls.append(config.role)
        raise VerificationClientError("provider_timeout", config.role)

    client = VerificationClient(
        _config("primary", "model-a"),
        _config("fallback", "model-b"),
        invoke_json=invoke,
        field_level=True,
    )
    result = client.verify_bundle(bundle, inventory)

    assert calls == ["primary"]
    assert result.applied.accepted == ()
    assert result.applied.issues[0]["code"] == "verifier_technical_failure_isolated"
    assert result.applied.audit_records[0]["primary_field_review"]["error"]
    compact = result.applied.audit_records[0]["secondary_compact_review"]
    assert compact["decision"] == "skipped"
    assert compact["reason_code"] == "SECONDARY_SKIPPED_PRIMARY_NONPOSITIVE"
    assert compact["bundle_id"] is None
    assert compact["cache_hit"] is False
    assert compact["status"] == "skipped"


def test_field_level_cache_identity_is_separate_from_v1(tmp_path):
    _inventory, bundle = _bundle()
    client = VerificationClient(
        _config("primary", "model-a"),
        _config("fallback", "model-b"),
        cache_dir=tmp_path,
        field_level=True,
        invoke_json=lambda *_args: ({}, {}),
    )

    assert client._field_cache_path(client.primary, bundle) != client._cache_path(
        client.primary, bundle
    )


def test_paper_field_phase_packs_primary_positive_hard_assertions_into_one_label_call():
    inventory, _bundle = _two_fact_bundle()
    inventory = replace(
        inventory,
        assertions=tuple(
            row.model_copy(update={"risk_severity": "hard"})
            for row in inventory.assertions
        ),
    )
    source = " ".join(row.text for row in inventory.evidence)
    bundles = build_verification_bundles(
        inventory, source_text=source, max_assertions=1
    )
    events = []
    observed_label_payloads = []

    def invoke_json(_config, _system, user):
        payload = json.loads(user)
        events.append(("primary", payload["bundle_id"]))
        return _field_supported(payload), {"provider_calls": 1}

    def invoke_responses(_config, _system, user):
        payload = json.loads(user)
        events.append(("label", payload["bundle_id"]))
        observed_label_payloads.append(payload)
        return json.dumps(["S"] * payload["label_count"]), {
            "provider_calls": 1,
            "api_mode": "responses",
            "response_status": "completed",
            "usage": {"output_tokens": 3},
        }

    client = VerificationClient(
        _config("primary", "model-a"),
        _responses_config("fallback", "model-b"),
        invoke_json=invoke_json,
        invoke_responses=invoke_responses,
        field_level=True,
    )
    result = client.verify_field_bundles(bundles, inventory, workers=2)

    assert len(result.applied.accepted) == 2
    assert [row[0] for row in events] == ["primary", "primary", "label"]
    assert result.metrics["provider_calls"] == 3
    assert result.metrics["compact_secondary_calls"] == 1
    assert observed_label_payloads[0]["label_count"] == 2
    assert all(
        "assertion_id" not in row
        for row in observed_label_payloads[0]["assertions"]
    )
    assert all(
        audit["secondary_label_review"]["label"] == "S"
        for audit in result.applied.audit_records
    )


def test_compact_label_prompt_drops_verbose_candidate_mirrors_but_keeps_evidence():
    _inventory, bundle = _bundle()
    payload = json.loads(_compact_label_prompt(bundle))
    candidate = payload["assertions"][0]["candidate"]
    data = candidate["data"]
    assert "original" not in data
    assert "simplified" not in data
    assert "raw_note" not in data
    assert "source_evidence" not in data
    assert payload["evidence"][0]["text"] == bundle.evidence[0].text


def test_paper_label_cardinality_failure_splits_once_and_maps_by_position():
    inventory, _bundle = _two_fact_bundle()
    inventory = replace(
        inventory,
        assertions=tuple(
            row.model_copy(update={"risk_severity": "hard"})
            for row in inventory.assertions
        ),
    )
    source = " ".join(row.text for row in inventory.evidence)
    bundles = build_verification_bundles(
        inventory, source_text=source, max_assertions=1
    )
    label_sizes = []

    def invoke_json(_config, _system, user):
        payload = json.loads(user)
        return _field_supported(payload), {"provider_calls": 1}

    def invoke_responses(_config, _system, user):
        payload = json.loads(user)
        label_sizes.append(payload["label_count"])
        return json.dumps(["S"]), {"provider_calls": 1}

    client = VerificationClient(
        _config("primary", "model-a"),
        _responses_config("fallback", "model-b"),
        invoke_json=invoke_json,
        invoke_responses=invoke_responses,
        field_level=True,
        compact_split_limit=1,
    )
    result = client.verify_field_bundles(bundles, inventory, workers=1)

    assert len(result.applied.accepted) == 2
    assert label_sizes == [2, 1, 1]
    assert result.metrics["compact_split_count"] == 1
    assert result.metrics["compact_secondary_calls"] == 3


def test_paper_label_transport_failure_never_switches_to_chat_and_fails_closed():
    inventory, raw_bundle = _bundle()
    inventory = replace(
        inventory,
        assertions=tuple(
            row.model_copy(update={"risk_severity": "hard"})
            for row in inventory.assertions
        ),
    )
    bundle = raw_bundle.model_copy(update={"assertions": list(inventory.assertions)})
    chat_calls = []

    def invoke_json(_config, _system, user):
        payload = json.loads(user)
        chat_calls.append(payload["bundle_id"])
        return _field_supported(payload), {"provider_calls": 1}

    def invoke_responses(_config, _system, _user):
        raise VerificationClientError(
            "provider_timeout", metrics={"provider_calls": 1}
        )

    client = VerificationClient(
        _config("primary", "model-a"),
        _responses_config("fallback", "model-b"),
        invoke_json=invoke_json,
        invoke_responses=invoke_responses,
        field_level=True,
    )
    result = client.verify_field_bundles((bundle,), inventory)

    assert len(chat_calls) == 1
    assert not result.applied.accepted
    assert result.applied.audit_records[0]["formal_action"] == "isolate"
    assert result.applied.audit_records[0]["secondary_label_review"][
        "failure_code"
    ] == "provider_timeout"
