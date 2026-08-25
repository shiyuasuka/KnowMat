import json

from knowmat.alpha25.contracts import PropertyFact
from knowmat.alpha25.verification_client import (
    VerificationClient,
    VerificationClientError,
    VerifierRoleConfig,
    RECOVERY_SYSTEM_PROMPT,
    verifier_configs_from_env,
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
    return type(template)(
        protocol_version=payload["protocol_version"],
        bundle_id=payload["bundle_id"],
        axis=payload["axis"],
        assertions=payload["assertions"],
        entities=payload["inventory_entities"],
        evidence=payload["evidence"],
        source_char_count=sum(len(row["text"]) for row in payload["evidence"]),
    )


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

    def invoke(config, _system, user):
        observed_timeouts.append(config.timeout_seconds)
        observed_output_budgets.append(config.output_token_budget)
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
    assert result.metrics["destructive_confirmation_calls"] == 1
    assert result.metrics["confirmed_quarantine_count"] == 1


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
    primary, fallback = verifier_configs_from_env()
    assert primary.model == "future-primary"
    assert fallback.model == "future-fallback"
    assert primary.thinking_mode == "disabled"
    assert primary.endpoint == "https://example.test/v1"
    assert "secret" not in json.dumps(primary.identity())


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
