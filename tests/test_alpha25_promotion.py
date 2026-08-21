from copy import deepcopy

from knowmat.alpha25.contracts import (
    CompositionFact,
    InventoryAnchor,
    ProcessingFact,
    PropertyFact,
    StructureFact,
)
from knowmat.alpha25.promotion import (
    PromotionDecision,
    PromotionIssue,
    build_owner_graph,
    build_promotion_records,
    deduplicate_source_assertions,
    group_source_assertions,
    promote_axis_facts,
    resolve_record_owner,
)


def _property(
    *,
    sample: str = "A1",
    name: str = "yield strength",
    value: str = "900",
    unit: str = "MPa",
    condition: str = "650 °C",
    evidence: str = "A1 had a yield strength of 900 MPa at 650 °C.",
    confidence: float = 0.8,
    candidate_id: str = "temporary",
    evidence_unit_id: str = "prose-L000010-L000010-deadbeef",
) -> PropertyFact:
    return PropertyFact(
        sample_id_raw=sample,
        evidence_unit_id=evidence_unit_id,
        data={
            "property_id_candidate": candidate_id,
            "property_name_raw": name,
            "value_raw": value,
            "unit_raw": unit,
            "test_method_raw": "tensile",
            "test_standard_raw": "",
            "test_condition_raw": condition,
            "test_specimen_raw": "",
            "raw_note": "",
            "data_source": "text",
            "source_evidence": [evidence],
            "confidence": confidence,
        },
        source_evidence=[evidence],
        confidence=confidence,
    )


def _anchor(
    sample: str,
    *,
    material: str | None = None,
    state: str | None = None,
    role: str = "Target",
    evidence: str | None = None,
) -> InventoryAnchor:
    return InventoryAnchor(
        sample_id_raw=sample,
        material_name_raw=material,
        state_raw=state,
        role=role,
        data_nature=(
            "Experimental" if role == "Target" else "Literature_Experimental"
        ),
        source_evidence=[evidence or sample],
        confidence=0.9,
    )


def _structure(
    *,
    sample: str = "A1",
    evidence: str = "A1 contained fine gamma-prime precipitates.",
    entities: list[dict] | None = None,
    features: list[dict] | None = None,
    structure_kind: str = "precipitate",
    source_type: str = "reported",
) -> StructureFact:
    return StructureFact(
        sample_id_raw=sample,
        fact_type="structure_observation",
        evidence_unit_id="prose-L000001-L000001-structure",
        data={
            "observation_id": "temporary",
            "structure_kind": structure_kind,
            "material_state": "not_reported",
            "sample_id": sample,
            "source_type": source_type,
            "original": evidence,
            "simplified": evidence,
            "entities": entities
            if entities is not None
            else [
                {
                    "name_raw": "gamma-prime precipitates",
                    "entity_type": "precipitate",
                    "role": "reported",
                    "features": [],
                    "raw_expression": "gamma-prime precipitates",
                }
            ],
            "features": features or [],
            "source_evidence": [evidence],
        },
        source_evidence=[evidence],
        confidence=0.8,
    )


def _characterization(
    *,
    sample: str = "A1",
    method: str = "SEM",
    method_class: str | None = None,
    evidence: str = "A1 was examined by SEM.",
) -> StructureFact:
    return StructureFact(
        sample_id_raw=sample,
        fact_type="characterization",
        evidence_unit_id="prose-L000001-L000001-characterization",
        data={
            "characterization_id": "temporary",
            "method_raw": method,
            "method_class": method if method_class is None else method_class,
            "source_evidence": [evidence],
        },
        source_evidence=[evidence],
        confidence=0.8,
    )


def _processing(
    *,
    sample: str = "A1",
    process: str = "laser powder bed fusion",
    evidence: str = "A1 was fabricated by laser powder bed fusion.",
    parameters: list[dict] | None = None,
) -> ProcessingFact:
    return ProcessingFact(
        sample_id_raw=sample,
        fact_type="process_stage",
        evidence_unit_id="prose-L000001-L000001-processing",
        data={
            "candidate_stage_id": "temporary",
            "stage_index_candidate": 1,
            "process_name_raw": process,
            "process_code_candidate": "A2.AM.PBF_L",
            "process_role_candidate": "primary_forming",
            "parameters_raw": parameters or [],
            "source_evidence": [evidence],
            "confidence": 0.8,
        },
        source_evidence=[evidence],
        confidence=0.8,
    )


def _composition(
    *,
    sample: str = "A1",
    component: str = "Al",
    value: str = "47.86 ± 0.5",
    unit: str = "at.%",
    evidence: str = "A1 contained 47.86 ± 0.5 at.% Al.",
    region: str | None = None,
) -> CompositionFact:
    data = {
        "observation_id": "temporary",
        "source_type": "measured",
        "material_state": "not_reported",
        "sample_id": sample,
        "basis": "atomic_fraction",
        "component_type": "elemental",
        "components": [
            {
                "name_raw": component,
                "value_kind": "uncertainty",
                "value_raw": value,
                "unit_raw": unit,
                "data_nature": "reported",
            }
        ],
        "measurement": "EDS",
        "raw_expression": evidence,
        "data_source": "text",
        "source_evidence": [evidence],
        "note": None,
    }
    if region is not None:
        data["region"] = region
    return CompositionFact(
        sample_id_raw=sample,
        fact_type="composition_observation",
        evidence_unit_id="prose-L000001-L000001-composition",
        data=data,
        source_evidence=[evidence],
        confidence=0.9,
    )


def test_promotion_record_is_stable_across_order_confidence_and_generated_ids():
    first = _property(confidence=0.6, candidate_id="prop_a")
    second = _property(confidence=0.99, candidate_id="prop_b")

    forward = build_promotion_records(
        [first, second], task_ids=["task-a", "task-b"]
    )
    reverse = build_promotion_records(
        [second, first], task_ids=["task-b", "task-a"]
    )

    assert [row.claim_id for row in forward] == [
        row.claim_id for row in reversed(reverse)
    ]
    assert forward[0].claim_id == forward[1].claim_id
    assert forward[0].source_order == 0
    assert forward[1].source_order == 1
    assert forward[0].task_id == "task-a"
    assert forward[0].evidence_unit_id == first.evidence_unit_id


def test_promotion_record_id_changes_for_scientific_identity_fields():
    baseline = _property()
    variants = [
        _property(sample="A2"),
        _property(value="901"),
        _property(condition="700 °C"),
        _property(evidence="A1 had a yield strength of 900 MPa after aging."),
    ]

    baseline_id = build_promotion_records([baseline])[0].claim_id

    assert all(
        build_promotion_records([variant])[0].claim_id != baseline_id
        for variant in variants
    )


def test_promotion_record_preserves_original_fact_and_normalizes_evidence():
    fact = _property(
        evidence="  A1  HAD a yield strength of 900 MPa at 650 °C.  "
    )

    record = build_promotion_records([fact])[0]

    assert record.fact is fact
    assert record.evidence == tuple(fact.source_evidence)
    assert record.normalized_evidence == (
        "a1 had a yield strength of 900 mpa at 650 °c.",
    )
    assert record.explicit_owner == "A1"
    assert record.owner_candidates == ("A1",)
    assert record.risk_codes == ()


def test_task_id_sequence_must_cover_every_fact():
    facts = [_property(), _property(value="901")]

    try:
        build_promotion_records(facts, task_ids=["only-one"])
    except ValueError as exc:
        assert "task_ids" in str(exc)
    else:  # pragma: no cover - documents the required failure mode.
        raise AssertionError("expected a provenance length error")


def test_promotion_decision_is_strict_and_immutable():
    decision = PromotionDecision(
        action="merge",
        candidate_ids=("claim-a", "claim-b"),
        survivor_id="claim-a",
        rule="same_source_assertion",
    )

    assert decision.action == "merge"
    assert decision.candidate_ids == ("claim-a", "claim-b")
    try:
        decision.action = "accept"
    except (AttributeError, TypeError):
        pass
    else:  # pragma: no cover - frozen dataclass contract.
        raise AssertionError("promotion decisions must be immutable")


def test_promotion_issue_retains_complete_removed_and_survivor_payloads():
    loser = _property(candidate_id="coarse", evidence="A1 had YS 900 MPa.")
    survivor = _property(
        candidate_id="rich",
        value="900 ± 20",
        evidence="A1 had YS 900 ± 20 MPa at 650 °C.",
    )
    after = survivor.model_copy(deep=True)
    after.source_evidence.append(loser.source_evidence[0])
    issue = PromotionIssue(
        code="promotion_richer_assertion_survived",
        sample_id_raw="A1",
        message="A less complete projection was merged.",
        evidence=[*loser.source_evidence, *survivor.source_evidence],
        expected={"decision": "one richer survivor"},
        actual={
            "removed": loser.model_dump(),
            "survivor_before": survivor.model_dump(),
            "survivor_after": after.model_dump(),
        },
        suggested_action="Review only if these are independent assertions.",
    )

    payload = issue.to_dict()

    assert payload["code"] == "promotion_richer_assertion_survived"
    assert payload["path"] == "items.A1"
    assert payload["actual"]["removed"] == loser.model_dump()
    assert payload["actual"]["survivor_before"] == survivor.model_dump()
    assert payload["actual"]["survivor_after"] == after.model_dump()
    assert payload["evidence"] == [
        *loser.source_evidence,
        *survivor.source_evidence,
    ]


def test_build_records_does_not_mutate_candidate_payload():
    fact = _property()
    before = deepcopy(fact.model_dump())

    build_promotion_records([fact], task_ids=["task-a"])

    assert fact.model_dump() == before


def test_exact_and_contained_evidence_share_one_source_assertion():
    source = "A1 had a yield strength of 900 MPa at 650 °C."
    full = _property(evidence=source)
    contained = _property(evidence="yield strength of 900 MPa at 650 °C")
    records = build_promotion_records([full, contained])

    groups = group_source_assertions(records, source_text=source)

    assert len(groups) == 1
    assert groups[0].source_kind == "prose"
    assert groups[0].source_block_key.startswith("prose:L000001-L000001")
    assert groups[0].records == tuple(records)


def test_identical_text_repeated_in_two_paragraphs_is_not_synthetically_joined():
    sentence = "A1 had a yield strength of 900 MPa at 650 °C."
    source = f"{sentence}\n\n{sentence}"
    first = _property(evidence=sentence, evidence_unit_id="prose-first")
    second = _property(evidence=sentence, evidence_unit_id="prose-second")

    groups = group_source_assertions(
        build_promotion_records([first, second]), source_text=source
    )

    assert len(groups) == 2
    assert all(group.ambiguous_source for group in groups)


def test_multi_column_table_keeps_distinct_owner_value_assertions():
    source = "\n".join(
        [
            "| Property | A1 | A2 |",
            "|---|---:|---:|",
            "| Yield strength (MPa) | 900 | 850 |",
        ]
    )
    evidence = [
        "| Property | A1 | A2 |",
        "| Yield strength (MPa) | 900 | 850 |",
    ]
    first = _property(
        sample="A1", value="900", evidence=evidence[0]
    )
    first.source_evidence = evidence
    first.data["source_evidence"] = evidence
    second = _property(
        sample="A2", value="850", evidence=evidence[0]
    )
    second.source_evidence = evidence
    second.data["source_evidence"] = evidence

    groups = group_source_assertions(
        build_promotion_records([first, second]), source_text=source
    )

    assert len(groups) == 2
    assert {group.projection_owner for group in groups} == {"A1", "A2"}
    assert {group.source_block_key for group in groups} == {
        groups[0].source_block_key
    }
    assert all(group.source_kind == "table" for group in groups)


def test_explicit_shared_owner_sentence_retains_one_projection_per_owner():
    source = "A1 and A2 both had a yield strength of 900 MPa at 650 °C."
    facts = [
        _property(sample="A1", evidence=source),
        _property(sample="A2", evidence=source),
    ]

    groups = group_source_assertions(
        build_promotion_records(facts), source_text=source
    )

    assert len(groups) == 2
    assert {group.projection_owner for group in groups} == {"A1", "A2"}
    assert len({group.source_block_key for group in groups}) == 1


def test_similar_claims_in_distinct_source_blocks_remain_independent():
    source = (
        "A1 had a yield strength of 900 MPa at 650 °C.\n\n"
        "After a repeat test, A1 again had a yield strength of 900 MPa at 650 °C."
    )
    facts = [
        _property(evidence="A1 had a yield strength of 900 MPa at 650 °C."),
        _property(
            evidence=(
                "After a repeat test, A1 again had a yield strength of "
                "900 MPa at 650 °C."
            )
        ),
    ]

    groups = group_source_assertions(
        build_promotion_records(facts), source_text=source
    )

    assert len(groups) == 2
    assert len({group.source_block_key for group in groups}) == 2


def test_source_assertion_duplicate_merges_into_richer_evidence_with_audit():
    source = "A1 had a yield strength of 900 MPa at 650 °C."
    full = _property(evidence=source, candidate_id="full")
    contained = _property(
        evidence="yield strength of 900 MPa at 650 °C",
        candidate_id="contained",
    )

    result = deduplicate_source_assertions([contained, full], source_text=source)

    assert len(result.accepted) == 1
    survivor = result.accepted[0]
    assert survivor.data["property_id_candidate"] == "full"
    assert survivor.source_evidence == [
        source,
        "yield strength of 900 MPa at 650 °C",
    ]
    assert survivor.data["source_evidence"] == survivor.source_evidence
    assert [issue.code for issue in result.issues] == [
        "promotion_assertion_duplicate_merged"
    ]
    issue = result.issues[0]
    assert issue.actual["removed"] == contained.model_dump()
    assert issue.actual["survivor_before"] == full.model_dump()
    assert issue.actual["survivor_after"] == survivor.model_dump()


def test_dedup_preserves_multi_column_and_independent_prose_assertions():
    table = "\n".join(
        [
            "| Property | A1 | A2 |",
            "|---|---:|---:|",
            "| Yield strength (MPa) | 900 | 850 |",
        ]
    )
    header = "| Property | A1 | A2 |"
    row = "| Yield strength (MPa) | 900 | 850 |"
    first = _property(sample="A1", value="900", evidence=header)
    first.source_evidence = [header, row]
    first.data["source_evidence"] = [header, row]
    second = _property(sample="A2", value="850", evidence=header)
    second.source_evidence = [header, row]
    second.data["source_evidence"] = [header, row]

    table_result = deduplicate_source_assertions(
        [first, second], source_text=table
    )

    assert table_result.accepted == (first, second)
    assert table_result.issues == ()

    sentence = "A1 had a yield strength of 900 MPa at 650 °C."
    prose_result = deduplicate_source_assertions(
        [
            _property(evidence=sentence, evidence_unit_id="first"),
            _property(evidence=sentence, evidence_unit_id="second"),
        ],
        source_text=f"{sentence}\n\n{sentence}",
    )

    assert len(prose_result.accepted) == 2
    assert prose_result.issues == ()


def test_source_assertion_dedup_is_input_permutation_deterministic():
    source = "A1 had a yield strength of 900 MPa at 650 °C."
    full = _property(evidence=source, candidate_id="full")
    contained = _property(
        evidence="yield strength of 900 MPa at 650 °C",
        candidate_id="contained",
    )

    forward = deduplicate_source_assertions([full, contained], source_text=source)
    reverse = deduplicate_source_assertions([contained, full], source_text=source)

    assert [fact.model_dump() for fact in forward.accepted] == [
        fact.model_dump() for fact in reverse.accepted
    ]
    assert [issue.to_dict() for issue in forward.issues] == [
        issue.to_dict() for issue in reverse.issues
    ]


def test_owner_graph_resolves_explicit_state_without_broadcasting_base():
    graph = build_owner_graph(
        [
            _anchor("Alloy A", material="Alloy A"),
            _anchor("Alloy A", material="Alloy A", state="as-built"),
            _anchor("Alloy A", material="Alloy A", state="aged"),
        ]
    )
    base = build_promotion_records(
        [
            _property(
                sample="Alloy A",
                evidence="Alloy A had a yield strength of 900 MPa at 650 °C.",
            )
        ]
    )[0]
    aged_fact = _property(
        sample="Alloy A",
        evidence="The aged Alloy A had a yield strength of 900 MPa at 650 °C.",
    )
    aged_fact.data["material_state"] = "aged"
    aged = build_promotion_records([aged_fact])[0]

    base_resolution = resolve_record_owner(base, graph)
    aged_resolution = resolve_record_owner(aged, graph)

    assert len(base_resolution.owner_ids) == 1
    assert graph.display_label(base_resolution.owner_ids[0]) == "Alloy A"
    assert base_resolution.risk_codes == ()
    assert len(aged_resolution.owner_ids) == 1
    assert graph.display_label(aged_resolution.owner_ids[0]) == "Alloy A [aged]"
    assert aged_resolution.risk_codes == ()


def test_generic_owner_without_base_anchor_is_ambiguous_not_broadcast():
    graph = build_owner_graph(
        [
            _anchor("Alloy A", material="Alloy A", state="as-built"),
            _anchor("Alloy A", material="Alloy A", state="aged"),
        ]
    )
    record = build_promotion_records(
        [
            _property(
                sample="Alloy A",
                evidence="Alloy A had a yield strength of 900 MPa.",
                condition="",
            )
        ]
    )[0]

    resolution = resolve_record_owner(record, graph)

    assert resolution.owner_ids == ()
    assert resolution.candidate_owner_ids == tuple(
        sorted(node.owner_id for node in graph.nodes)
    )
    assert resolution.risk_codes == ("ambiguous_owner",)


def test_state_named_in_evidence_selects_one_existing_child_owner():
    graph = build_owner_graph(
        [
            _anchor("Alloy A", material="Alloy A", state="as-built"),
            _anchor("Alloy A", material="Alloy A", state="aged"),
        ]
    )
    fact = _property(
        sample="Alloy A",
        evidence="The aged Alloy A had a yield strength of 900 MPa.",
        condition="",
    )
    fact.data["material_state"] = "aged"
    record = build_promotion_records([fact])[0]

    resolution = resolve_record_owner(record, graph)

    assert len(resolution.owner_ids) == 1
    assert graph.display_label(resolution.owner_ids[0]) == "Alloy A [aged]"
    assert resolution.risk_codes == ()


def test_explicit_shared_owner_grammar_is_recorded_without_combined_item():
    graph = build_owner_graph([_anchor("A1"), _anchor("A2")])
    sentence = "A1 and A2 both had a yield strength of 900 MPa."
    record = build_promotion_records(
        [_property(sample="A1", evidence=sentence, condition="")]
    )[0]

    resolution = resolve_record_owner(record, graph)

    assert len(resolution.owner_ids) == 1
    assert graph.display_label(resolution.owner_ids[0]) == "A1"
    assert {
        graph.display_label(owner_id)
        for owner_id in resolution.explicit_shared_owner_ids
    } == {"A1", "A2"}
    assert resolution.risk_codes == ()


def test_reference_and_target_with_same_material_name_remain_distinct():
    graph = build_owner_graph(
        [
            _anchor("A1", material="Alloy A", role="Target"),
            _anchor("A1 literature", material="Alloy A", role="Reference"),
        ]
    )
    record = build_promotion_records(
        [_property(sample="A1", evidence="A1 had a yield strength of 900 MPa.")]
    )[0]

    resolution = resolve_record_owner(record, graph)

    assert len(resolution.owner_ids) == 1
    assert graph.node(resolution.owner_ids[0]).role == "Target"


def test_same_sample_state_role_merges_material_descriptors_as_aliases():
    graph = build_owner_graph(
        [
            _anchor("A1", material="Alloy A"),
            _anchor("A1", material="as-deposited Alloy A specimen"),
        ]
    )
    record = build_promotion_records(
        [_property(sample="A1", evidence="A1 had a yield strength of 900 MPa.")]
    )[0]

    resolution = resolve_record_owner(record, graph)

    assert len(graph.nodes) == 1
    assert len(resolution.owner_ids) == 1
    assert set(graph.node(resolution.owner_ids[0]).aliases) == {
        "A1",
        "Alloy A",
        "as-deposited Alloy A specimen",
    }
    assert resolution.risk_codes == ()


def test_structure_gate_quarantines_ungrounded_entity_and_feature_payloads():
    evidence = "A1 contained fine gamma-prime precipitates."
    fact = _structure(
        evidence=evidence,
        entities=[
            {
                "name_raw": "gamma-prime precipitates",
                "entity_type": "precipitate",
                "features": [],
                "raw_expression": "gamma-prime precipitates",
            },
            {
                "name_raw": "beta phase",
                "entity_type": "phase",
                "features": [],
                "raw_expression": "beta phase",
            },
        ],
        features=[
            {
                "feature_name_raw": "size",
                "value_kind": "text",
                "value_raw": "fine",
                "data_nature": "reported",
            },
            {
                "feature_name_raw": "volume fraction",
                "value_kind": "scalar",
                "value_raw": "42%",
                "unit_raw": "%",
                "data_nature": "reported",
            },
        ],
    )

    result = promote_axis_facts([_anchor("A1")], [fact], source_text=evidence)

    assert len(result.accepted) == 1
    cleaned = result.accepted[0]
    assert [row["name_raw"] for row in cleaned.data["entities"]] == [
        "gamma-prime precipitates"
    ]
    assert cleaned.data["features"] == []
    assert {issue.code for issue in result.issues} == {
        "promotion_structure_entity_unsupported",
        "promotion_structure_feature_unsupported",
        "promotion_structure_qualitative_projection_quarantined",
    }
    assert all("removed" in issue.actual for issue in result.issues)


def test_structure_entity_keeps_numeric_and_negated_features_only():
    evidence = "A1 had 42% gamma-prime; no cracks were observed."
    fact = _structure(
        evidence=evidence,
        entities=[
            {
                "name_raw": "gamma-prime",
                "entity_type": "precipitate",
                "features": [
                    {
                        "feature_name_raw": "volume fraction",
                        "value_kind": "scalar",
                        "value_raw": "42%",
                        "unit_raw": "%",
                        "data_nature": "reported",
                    },
                    {
                        "feature_name_raw": "description",
                        "value_kind": "text",
                        "value_raw": "gamma-prime",
                        "data_nature": "reported",
                    },
                    {
                        "feature_name_raw": "crack presence",
                        "value_kind": "categorical",
                        "value_raw": "no cracks were observed",
                        "data_nature": "reported",
                    },
                ],
                "raw_expression": "gamma-prime",
            }
        ],
        features=[],
    )

    result = promote_axis_facts([_anchor("A1")], [fact], source_text=evidence)

    assert len(result.accepted) == 1
    features = result.accepted[0].data["entities"][0]["features"]
    assert [row["feature_name_raw"] for row in features] == [
        "volume fraction",
        "crack presence",
    ]
    assert [issue.code for issue in result.issues] == [
        "promotion_structure_qualitative_projection_quarantined"
    ]


def test_negated_structure_entity_shadow_is_quarantined_but_negative_feature_survives():
    evidence = "No cracks were observed in A1 after heat treatment."
    fact = _structure(
        evidence=evidence,
        entities=[
            {
                "name_raw": "cracks",
                "entity_type": "defect",
                "role": "reported",
                "features": [],
                "raw_expression": evidence,
                "source_evidence": [evidence],
            }
        ],
        features=[
            {
                "feature_name_raw": "crack presence",
                "value_kind": "categorical",
                "value_raw": "No cracks were observed",
                "data_nature": "reported",
                "source_evidence": [evidence],
            }
        ],
    )

    result = promote_axis_facts([_anchor("A1")], [fact], source_text=evidence)

    assert len(result.accepted) == 1
    assert result.accepted[0].data["entities"] == []
    assert result.accepted[0].data["features"] == fact.data["features"]
    assert [issue.code for issue in result.issues] == [
        "promotion_structure_negated_entity_quarantined"
    ]
    issue = result.issues[0]
    assert issue.actual["removed"] == fact.data["entities"][0]
    assert issue.actual["survivor_after"]["data"]["features"] == fact.data["features"]
    assert issue.actual["reason"] == "negated_entity_was_not_positive_presence"


def test_absent_table_entity_is_quarantined_without_removing_positive_sibling():
    evidence = "| Alloy | Boride | Carbide |\n| A1 | Yes | No |"
    fact = _structure(
        evidence=evidence,
        entities=[
            {
                "name_raw": "Boride",
                "entity_type": "phase",
                "role": "reported",
                "features": [],
                "raw_expression": "Yes",
                "source_evidence": evidence.splitlines(),
            },
            {
                "name_raw": "Carbide",
                "entity_type": "phase",
                "role": "absent",
                "features": [],
                "raw_expression": "Carbide",
                "source_evidence": evidence.splitlines(),
            },
        ],
        features=[],
    )

    result = promote_axis_facts([_anchor("A1")], [fact], source_text=evidence)

    assert len(result.accepted) == 1
    assert [row["name_raw"] for row in result.accepted[0].data["entities"]] == [
        "Boride"
    ]
    assert [issue.code for issue in result.issues] == [
        "promotion_structure_negated_entity_quarantined"
    ]
    assert result.issues[0].actual["removed"] == fact.data["entities"][1]


def test_negated_entity_only_observation_is_fully_audited_when_quarantined():
    evidence = "No cell boundaries are observed in the microstructure of A1."
    fact = _structure(
        evidence=evidence,
        entities=[
            {
                "name_raw": "cell boundaries",
                "entity_type": "feature",
                "role": "reported",
                "features": [],
                "raw_expression": evidence,
                "source_evidence": [evidence],
            }
        ],
        features=[],
    )

    result = promote_axis_facts([_anchor("A1")], [fact], source_text=evidence)

    assert result.accepted == ()
    assert [issue.code for issue in result.issues] == [
        "promotion_structure_negated_entity_quarantined",
        "promotion_structure_observation_quarantined",
    ]
    assert result.issues[0].actual["removed"] == fact.data["entities"][0]
    assert result.issues[1].actual["removed"] == fact.model_dump()


def test_generic_nonatomic_structure_entity_requires_atomic_payload():
    evidence = "A1 showed a matrix description with a width of 2 μm."
    unsupported = _structure(
        evidence=evidence,
        entities=[
            {
                "name_raw": "matrix description",
                "entity_type": "other",
                "features": [],
                "raw_expression": "matrix description",
            }
        ],
        features=[],
    )
    supported = _structure(
        evidence=evidence,
        entities=[
            {
                "name_raw": "matrix description",
                "entity_type": "other",
                "features": [
                    {
                        "feature_name_raw": "width",
                        "value_kind": "scalar",
                        "value_raw": "2",
                        "unit_raw": "μm",
                        "data_nature": "reported",
                    }
                ],
                "raw_expression": "matrix description",
            }
        ],
        features=[],
    )

    rejected = promote_axis_facts(
        [_anchor("A1")], [unsupported], source_text=evidence
    )
    accepted = promote_axis_facts(
        [_anchor("A1")], [supported], source_text=evidence
    )

    assert rejected.accepted == ()
    assert {issue.code for issue in rejected.issues} == {
        "promotion_structure_nonatomic_entity_quarantined",
        "promotion_structure_observation_quarantined",
    }
    assert accepted.accepted == (supported,)


def test_missing_structure_entity_type_is_not_promoted_as_implicit_other():
    evidence = "A1 showed an untyped matrix description."
    fact = _structure(
        evidence=evidence,
        entities=[
            {
                "name_raw": "untyped matrix description",
                "features": [],
                "raw_expression": "untyped matrix description",
            }
        ],
        features=[],
    )

    result = promote_axis_facts([_anchor("A1")], [fact], source_text=evidence)

    assert result.accepted == ()
    assert {issue.code for issue in result.issues} == {
        "promotion_structure_nonatomic_entity_quarantined",
        "promotion_structure_observation_quarantined",
    }


def test_unknown_entity_is_recovered_from_source_literal_instead_of_deleted():
    evidence = "A1 contained cuboidal γ′ precipitates."
    fact = _structure(
        evidence=evidence,
        entities=[
            {
                "name_raw": "unknown_entity",
                "canonical_name": "unknown_entity",
                "entity_type": "precipitate",
                "features": [],
                "raw_expression": "γ′ precipitates",
            }
        ],
    )

    result = promote_axis_facts([_anchor("A1")], [fact], source_text=evidence)

    assert len(result.accepted) == 1
    entity = result.accepted[0].data["entities"][0]
    assert entity["name_raw"] == "γ′ precipitates"
    assert entity.get("canonical_name") is None
    assert [issue.code for issue in result.issues] == [
        "promotion_structure_entity_name_recovered"
    ]
    assert result.issues[0].actual["before"]["name_raw"] == "unknown_entity"
    assert result.issues[0].actual["after"]["name_raw"] == "γ′ precipitates"


def test_negated_structure_entity_is_not_positive_when_sibling_feature_proves_removal():
    evidence = "After HIP treatment, the cracks in A1 were completely annihilated."
    fact = _structure(
        evidence=evidence,
        entities=[
            {
                "name_raw": "cracks",
                "entity_type": "defect",
                "role": "reported",
                "features": [],
                "raw_expression": "cracks",
                "source_evidence": [evidence],
            }
        ],
        features=[
            {
                "feature_name_raw": "crack state",
                "value_kind": "categorical",
                "value_raw": "completely annihilated",
                "data_nature": "reported",
                "source_evidence": [evidence],
            }
        ],
    )

    result = promote_axis_facts([_anchor("A1")], [fact], source_text=evidence)

    assert len(result.accepted) == 1
    assert result.accepted[0].data["entities"] == []
    assert result.accepted[0].data["features"] == fact.data["features"]
    assert [issue.code for issue in result.issues] == [
        "promotion_structure_negated_entity_quarantined"
    ]
    assert result.issues[0].actual["reason"] == "negated_sibling_feature"


def test_prose_disappearance_does_not_promote_listed_entities_as_present():
    evidence = (
        "Increasing temperature led to the disappearance of Laves/carbide "
        "and chromium oxide peaks."
    )
    fact = _structure(
        evidence=evidence,
        entities=[
            {
                "name_raw": "Laves/carbide",
                "entity_type": "intermetallic",
                "features": [],
            },
            {
                "name_raw": "chromium oxide",
                "entity_type": "oxide",
                "features": [],
            },
        ],
        features=[
            {
                "feature_name_raw": "peak disappearance",
                "value_kind": "categorical",
                "value_raw": "disappearance",
                "data_nature": "reported",
                "source_evidence": [evidence],
            }
        ],
    )

    result = promote_axis_facts([_anchor("A1")], [fact], source_text=evidence)

    assert len(result.accepted) == 1
    assert result.accepted[0].data["entities"] == []
    assert result.accepted[0].data["features"] == fact.data["features"]
    negated = [
        issue
        for issue in result.issues
        if issue.code == "promotion_structure_negated_entity_quarantined"
    ]
    assert len(negated) == 2
    assert {issue.actual["reason"] for issue in negated} == {
        "entity_local_prose_negation"
    }


def test_unrelated_no_difference_clause_keeps_positive_structure_entities():
    evidence = (
        "There was no distinct difference between A1 and A2 surface oxides, "
        "which were mainly chromium oxide and aluminium oxide."
    )
    fact = _structure(
        evidence=evidence,
        entities=[
            {
                "name_raw": "chromium oxide",
                "entity_type": "oxide",
                "features": [],
            },
            {
                "name_raw": "aluminium oxide",
                "entity_type": "oxide",
                "features": [],
            },
        ],
        features=[],
    )

    result = promote_axis_facts([_anchor("A1")], [fact], source_text=evidence)

    assert result.accepted == (fact,)
    assert not any(
        issue.code == "promotion_structure_negated_entity_quarantined"
        for issue in result.issues
    )


def test_partial_or_process_dissolution_does_not_erase_present_entity():
    cases = [
        ("The partial annihilation of dislocations reduced KAM.", "dislocations"),
        (
            "Anodic dissolution of the surrounding FCC matrix occurred locally.",
            "FCC matrix",
        ),
        ("The vast majority of pores is removed after HIP.", "pores"),
    ]

    for evidence, entity_name in cases:
        fact = _structure(
            evidence=evidence,
            entities=[
                {
                    "name_raw": entity_name,
                    "entity_type": "phase",
                    "features": [],
                }
            ],
            features=[],
        )

        result = promote_axis_facts(
            [_anchor("A1")], [fact], source_text=evidence
        )

        assert result.accepted == (fact,)
        assert not any(
            issue.code == "promotion_structure_negated_entity_quarantined"
            for issue in result.issues
        )


def test_entity_local_negative_predicates_do_not_become_positive_presence():
    cases = [
        (
            "Network segregation phases are completely dissolved after heat treatment.",
            "network segregation phases",
            "completely dissolved",
        ),
        (
            "Gamma-prime phase and carbide precipitates were small or non-existent.",
            "gamma-prime phase",
            "small or non-existent",
        ),
    ]

    for evidence, entity_name, value in cases:
        fact = _structure(
            evidence=evidence,
            entities=[
                {
                    "name_raw": entity_name,
                    "entity_type": "phase",
                    "features": [],
                }
            ],
            features=[
                {
                    "feature_name_raw": "existence state",
                    "value_kind": "categorical",
                    "value_raw": value,
                    "data_nature": "reported",
                    "source_evidence": [evidence],
                }
            ],
        )

        result = promote_axis_facts(
            [_anchor("A1")], [fact], source_text=evidence
        )

        assert len(result.accepted) == 1
        assert result.accepted[0].data["entities"] == []
        assert any(
            issue.code == "promotion_structure_negated_entity_quarantined"
            and issue.actual["reason"] == "entity_local_prose_negation"
            for issue in result.issues
        )


def test_characterization_aliases_merge_across_chunks_for_one_owner():
    method_evidence = (
        "A1 was characterized by scanning electron microscopy "
        "(SEM, Zeiss Supra 55)."
    )
    result_evidence = "SEM-BSE images of A1 reveal the pore distribution."
    source = f"{method_evidence}\n\n{result_evidence}"
    formal = _characterization(
        method="scanning electron microscopy (SEM, Zeiss Supra 55)",
        evidence=method_evidence,
    )
    result_mention = _characterization(
        method="SEM-BSE",
        evidence=result_evidence,
    )

    result = promote_axis_facts(
        [_anchor("A1")],
        [formal, result_mention],
        source_text=source,
    )

    assert len(result.accepted) == 1
    survivor = result.accepted[0]
    assert survivor.data["method_raw"] == formal.data["method_raw"]
    assert survivor.source_evidence == [method_evidence, result_evidence]
    merged = [
        issue
        for issue in result.issues
        if issue.code == "promotion_characterization_alias_merged"
    ]
    assert len(merged) == 1
    assert merged[0].actual["removed"] == result_mention.model_dump()


def test_characterization_result_analysis_does_not_compete_with_method_declaration():
    method_evidence = (
        "EDS measurements were performed using an Oxford X-Max detector."
    )
    analysis_evidence = (
        "EDS analysis presented in Fig. 9 confirms an aluminium-rich oxide."
    )
    mapping_evidence = "The EDS mapping shows zirconium at the grain boundary."
    source = "\n\n".join(
        [method_evidence, analysis_evidence, mapping_evidence]
    )
    formal = _characterization(
        method="EDS (Oxford X-Max detector)",
        method_class="EDS",
        evidence=method_evidence,
    )
    analysis = _characterization(
        method="EDS analysis",
        method_class="EDS",
        evidence=analysis_evidence,
    )
    mapping = _characterization(
        method="EDS mapping",
        method_class="EDS",
        evidence=mapping_evidence,
    )

    result = promote_axis_facts(
        [_anchor("A1")],
        [formal, analysis, mapping],
        source_text=source,
    )

    assert len(result.accepted) == 1
    survivor = result.accepted[0]
    assert survivor.data["method_raw"] == formal.data["method_raw"]
    assert survivor.source_evidence == [
        method_evidence,
        analysis_evidence,
        mapping_evidence,
    ]
    assert sum(
        issue.code == "promotion_characterization_alias_merged"
        for issue in result.issues
    ) == 2


def test_characterization_aliases_merge_across_source_types_for_one_state():
    method_evidence = (
        "A1 was characterized by scanning electron microscopy "
        "(SEM, Zeiss Supra 55)."
    )
    result_evidence = "SEM-BSE images of A1 reveal the pore distribution."
    source = f"{method_evidence}\n\n{result_evidence}"
    formal = _characterization(
        method="scanning electron microscopy (SEM, Zeiss Supra 55)",
        evidence=method_evidence,
    )
    formal.data["source_type"] = "method"
    result_mention = _characterization(
        method="SEM-BSE",
        evidence=result_evidence,
    )
    result_mention.data["source_type"] = "reported"

    result = promote_axis_facts(
        [_anchor("A1")],
        [formal, result_mention],
        source_text=source,
    )

    assert len(result.accepted) == 1
    assert result.accepted[0].data["method_raw"] == formal.data["method_raw"]
    assert result.accepted[0].source_evidence == [
        method_evidence,
        result_evidence,
    ]
    assert [
        issue.code
        for issue in result.issues
        if issue.code == "promotion_characterization_alias_merged"
    ] == ["promotion_characterization_alias_merged"]


def test_caption_shaped_characterization_projection_is_quarantined():
    evidence = "KAM maps of A1 reveal the residual-stress distribution."
    fact = _characterization(
        method="KAM maps",
        method_class="EBSD",
        evidence=evidence,
    )

    result = promote_axis_facts([_anchor("A1")], [fact], source_text=evidence)

    assert result.accepted == ()
    assert [issue.code for issue in result.issues] == [
        "promotion_characterization_unasserted_result_quarantined"
    ]
    assert result.issues[0].actual["removed"] == fact.model_dump()


def test_characterization_method_row_in_markdown_table_is_preserved():
    evidence = "| SEM | Zeiss Supra 55 |"
    source = "| Method | Instrument |\n|---|---|\n" + evidence
    fact = _characterization(
        method="SEM",
        method_class="SEM",
        evidence=evidence,
    )

    result = promote_axis_facts([_anchor("A1")], [fact], source_text=source)

    assert result.accepted == (fact,)
    assert result.issues == ()


def test_characterization_result_with_observation_state_is_not_absorbed():
    method_evidence = "A1 was characterized by TEM using a Talos F200X."
    state_evidence = "TEM images of A1 after heat treatment reveal twins."
    source = f"{method_evidence}\n\n{state_evidence}"
    formal = _characterization(
        method="TEM (Talos F200X)",
        method_class="TEM",
        evidence=method_evidence,
    )
    state_result = _characterization(
        method="TEM",
        method_class="TEM",
        evidence=state_evidence,
    )

    result = promote_axis_facts(
        [_anchor("A1")],
        [formal, state_result],
        source_text=source,
    )

    assert result.accepted == (formal,)
    assert not any(
        issue.code == "promotion_characterization_alias_merged"
        for issue in result.issues
    )
    assert any(
        issue.code
        == "promotion_characterization_unasserted_result_quarantined"
        and issue.actual["removed"] == state_result.model_dump()
        for issue in result.issues
    )


def test_multimodal_characterization_result_is_not_absorbed_by_one_family():
    method_evidence = "A1 was characterized by TEM using a Talos F200X."
    multimodal_evidence = "TEM coupled with SAED identified the ordered phase."
    source = f"{method_evidence}\n\n{multimodal_evidence}"
    formal = _characterization(
        method="TEM (Talos F200X)",
        method_class="TEM",
        evidence=method_evidence,
    )
    multimodal = _characterization(
        method="TEM coupled with SAED",
        method_class="diffraction",
        evidence=multimodal_evidence,
    )

    result = promote_axis_facts(
        [_anchor("A1")],
        [formal, multimodal],
        source_text=source,
    )

    assert result.accepted == (formal,)
    assert not any(
        issue.code == "promotion_characterization_alias_merged"
        for issue in result.issues
    )
    assert any(
        issue.code
        == "promotion_characterization_unasserted_result_quarantined"
        and issue.actual["removed"] == multimodal.model_dump()
        for issue in result.issues
    )


def test_characterization_same_method_for_distinct_owners_is_preserved():
    first_evidence = "A1 was characterized by SEM."
    second_evidence = "A2 was characterized by SEM."
    source = f"{first_evidence}\n\n{second_evidence}"
    first = _characterization(sample="A1", evidence=first_evidence)
    second = _characterization(sample="A2", evidence=second_evidence)

    result = promote_axis_facts(
        [_anchor("A1"), _anchor("A2")],
        [first, second],
        source_text=source,
    )

    assert result.accepted == (first, second)
    assert not any(
        issue.code == "promotion_characterization_alias_merged"
        for issue in result.issues
    )


def test_tensile_owner_state_conflict_reassigns_to_existing_base_owner():
    evidence = (
        "H230AM tensile strength after 200 h thermal exposure at 900 °C "
        "was 204 MPa."
    )
    fact = _property(
        sample="H230AM [after thermal exposure at 900 °C for 500 h]",
        name="tensile strength",
        value="204",
        unit="MPa",
        condition="900 °C; 200 h thermal exposure",
        evidence=evidence,
    )
    anchors = [
        _anchor("H230AM", material="H230AM"),
        _anchor(
            "H230AM [after thermal exposure at 900 °C for 500 h]",
            material="H230AM",
            state="after thermal exposure at 900 °C for 500 h",
        ),
    ]

    result = promote_axis_facts(anchors, [fact], source_text=evidence)

    assert len(result.accepted) == 1
    assert result.accepted[0].sample_id_raw == "H230AM"
    assert result.accepted[0].data["test_condition_raw"] == fact.data[
        "test_condition_raw"
    ]
    assert [issue.code for issue in result.issues] == [
        "promotion_tensile_owner_state_conflict_reassigned"
    ]
    issue = result.issues[0]
    assert issue.actual["before"] == fact.model_dump()
    assert issue.actual["after"] == result.accepted[0].model_dump()
    assert issue.actual["conflict_dimension"] == "duration"


def test_tensile_matching_owner_state_is_not_reassigned():
    evidence = (
        "H230AM tensile strength after 500 h thermal exposure at 900 °C "
        "was 200 MPa."
    )
    fact = _property(
        sample="H230AM [after thermal exposure at 900 °C for 500 h]",
        name="tensile strength",
        value="200",
        unit="MPa",
        condition="900 °C; 500 h thermal exposure",
        evidence=evidence,
    )
    anchors = [
        _anchor("H230AM", material="H230AM"),
        _anchor(
            "H230AM [after thermal exposure at 900 °C for 500 h]",
            material="H230AM",
            state="after thermal exposure at 900 °C for 500 h",
        ),
    ]

    result = promote_axis_facts(anchors, [fact], source_text=evidence)

    assert result.accepted == (fact,)
    assert not any(
        issue.code == "promotion_tensile_owner_state_conflict_reassigned"
        for issue in result.issues
    )


def test_structure_fact_with_no_supported_atomic_payload_is_quarantined():
    evidence = "Fig. 3 shows the representative micrograph of A1."
    fact = _structure(
        evidence=evidence,
        entities=[
            {
                "name_raw": "sigma phase",
                "entity_type": "phase",
                "features": [],
                "raw_expression": "sigma phase",
            }
        ],
        features=[],
    )

    result = promote_axis_facts([_anchor("A1")], [fact], source_text=evidence)

    assert result.accepted == ()
    assert [issue.code for issue in result.issues][-1] == (
        "promotion_structure_observation_quarantined"
    )
    assert result.issues[-1].actual["removed"] == fact.model_dump()


def test_comparative_structure_projection_isolated_but_numeric_fact_survives():
    evidence = (
        "The CL sample has a larger grain size than the PL sample, while the "
        "average grain size was 1.52 µm."
    )
    fact = _structure(
        sample="CL",
        evidence=evidence,
        structure_kind="grain_structure",
        entities=[],
        features=[
            {
                "feature_name_raw": "grain size comparison",
                "value_kind": "text",
                "value_raw": "larger than the PL sample",
                "data_nature": "reported",
            },
            {
                "feature_name_raw": "average grain size",
                "value_kind": "scalar",
                "value_raw": "1.52",
                "unit_raw": "µm",
                "data_nature": "reported",
            },
        ],
    )

    result = promote_axis_facts([_anchor("CL")], [fact], source_text=evidence)

    assert len(result.accepted) == 1
    assert [row["feature_name_raw"] for row in result.accepted[0].data["features"]] == [
        "average grain size"
    ]
    assert [issue.code for issue in result.issues] == [
        "promotion_structure_comparative_projection_quarantined"
    ]
    assert result.issues[0].actual["removed"]["feature_name_raw"] == (
        "grain size comparison"
    )


def test_comparator_only_structure_entity_isolated_without_erasing_primary_entity():
    evidence = (
        "The volume fraction of ZrC phases in H230AM is much higher than that "
        "of the M6C in H230."
    )
    fact = _structure(
        sample="H230",
        evidence=evidence,
        entities=[
            {
                "name_raw": "ZrC phases",
                "entity_type": "phase",
                "features": [],
                "raw_expression": "ZrC phases",
            },
            {
                "name_raw": "M6C",
                "entity_type": "phase",
                "features": [],
                "raw_expression": "M6C",
            },
        ],
        features=[],
    )

    result = promote_axis_facts([_anchor("H230")], [fact], source_text=evidence)

    assert len(result.accepted) == 1
    assert [row["name_raw"] for row in result.accepted[0].data["entities"]] == [
        "ZrC phases"
    ]
    assert any(
        issue.code
        == "promotion_structure_comparative_entity_projection_quarantined"
        for issue in result.issues
    )


def test_numeric_comparative_structure_feature_is_not_quarantined():
    evidence = "The average grain size increased from 0.91 to 1.52 µm."
    fact = _structure(
        sample="CL",
        evidence=evidence,
        structure_kind="grain_structure",
        entities=[],
        features=[
            {
                "feature_name_raw": "average grain size",
                "value_kind": "scalar",
                "value_raw": "1.52",
                "unit_raw": "µm",
                "data_nature": "reported",
            }
        ],
    )

    result = promote_axis_facts([_anchor("CL")], [fact], source_text=evidence)

    assert result.accepted == (fact,)
    assert not any(
        issue.code == "promotion_structure_comparative_projection_quarantined"
        for issue in result.issues
    )


def test_structure_method_only_value_is_quarantined_with_full_audit():
    evidence = (
        "The volume fraction and sizes were measured using polishing and imaging "
        "methods developed by Smith et al."
    )
    fact = _structure(
        evidence=evidence,
        entities=[],
        features=[
            {
                "feature_name_raw": "volume fraction and sizes",
                "value_kind": "text",
                "value_raw": "measured using the polishing and imaging methods",
                "data_nature": "reported",
            }
        ],
    )

    result = promote_axis_facts([_anchor("A1")], [fact], source_text=evidence)

    assert result.accepted == ()
    issue = next(
        issue
        for issue in result.issues
        if issue.code == "promotion_structure_method_only_value_quarantined"
    )
    assert issue.actual["removed"]["value_raw"].startswith("measured using")
    assert issue.evidence == [evidence]


def test_feedstock_table_metric_cannot_be_projected_as_precipitate_structure():
    evidence = (
        "| Technology | Mass (g) | Flow rate (s/50g) | Particle size distribution (µm) |\n"
        "| Binder Jetting | 23 | 12 | 7-24 |"
    )
    fact = _structure(
        evidence=evidence,
        entities=[],
        features=[
            {
                "feature_name_raw": "precipitate size",
                "value_kind": "range",
                "value_raw": "7-24",
                "unit_raw": "µm",
                "data_nature": "reported",
            }
        ],
    )

    result = promote_axis_facts([_anchor("A1")], [fact], source_text=evidence)

    assert result.accepted == ()
    assert any(
        issue.code == "promotion_structure_table_axis_mismatch_quarantined"
        and issue.actual["reason"] == "feedstock_table_projected_as_structure"
        for issue in result.issues
    )


def test_inferential_structure_entity_is_quarantined_without_direct_assertion():
    evidence = (
        "The lath microstructure was likely a massive martensite phase."
    )
    fact = _structure(
        evidence=evidence,
        entities=[
            {
                "name_raw": "massive martensite phase",
                "entity_type": "phase",
                "role": "reported",
                "features": [],
                "raw_expression": "massive martensite phase",
                "source_evidence": [evidence],
            }
        ],
        features=[],
        structure_kind="transformation",
    )

    result = promote_axis_facts(
        [_anchor("A1")], [fact], source_text=evidence
    )

    assert result.accepted == ()
    assert any(
        issue.code == "promotion_structure_inferential_projection_quarantined"
        and issue.actual["reason"] == "inferential_entity_without_direct_assertion"
        for issue in result.issues
    )
    assert any(
        issue.actual["removed"]["name_raw"] == "massive martensite phase"
        and issue.evidence == [evidence]
        for issue in result.issues
        if issue.code == "promotion_structure_inferential_projection_quarantined"
    )


def test_direct_structure_entity_survives_inferential_sentence():
    evidence = (
        "Fine Widmanstatten alpha platelets were observed in the EBAM material; "
        "the martensitic phase is also possible at high build temperature."
    )
    fact = _structure(
        evidence=evidence,
        entities=[
            {
                "name_raw": "Widmanstatten alpha platelets",
                "entity_type": "phase",
                "role": "reported",
                "features": [],
                "raw_expression": "Widmanstatten alpha platelets",
                "source_evidence": [evidence],
            }
        ],
        features=[],
        structure_kind="phase_assemblage",
    )

    result = promote_axis_facts(
        [_anchor("A1")], [fact], source_text=evidence
    )

    assert result.accepted
    assert result.accepted[0].data["entities"][0]["name_raw"] == (
        "Widmanstatten alpha platelets"
    )
    assert not any(
        issue.code == "promotion_structure_inferential_projection_quarantined"
        for issue in result.issues
    )


def test_numeric_structure_feature_survives_inferential_sentence():
    evidence = "The grain size was likely 10 µm based on the image analysis."
    fact = _structure(
        evidence=evidence,
        entities=[],
        features=[
            {
                "feature_name_raw": "grain size",
                "value_kind": "scalar",
                "value_raw": "10",
                "unit_raw": "µm",
                "source_evidence": [evidence],
            }
        ],
        structure_kind="grain_structure",
    )

    result = promote_axis_facts(
        [_anchor("A1")], [fact], source_text=evidence
    )

    assert result.accepted
    assert result.accepted[0].data["features"][0]["value_raw"] == "10"
    assert not any(
        issue.code == "promotion_structure_inferential_projection_quarantined"
        for issue in result.issues
    )


def test_bare_structure_entity_mention_is_quarantined_without_assertion():
    evidence = "γ/M23C6 (boron-free alloy)"
    fact = _structure(
        evidence=evidence,
        entities=[
            {
                "name_raw": "γ/M23C6",
                "entity_type": "interface",
                "role": "reported",
                "features": [],
                "raw_expression": "γ/M23C6",
                "source_evidence": [evidence],
            }
        ],
        features=[],
        structure_kind="interface",
    )

    result = promote_axis_facts([_anchor("A1")], [fact], source_text=evidence)

    assert result.accepted == ()
    assert any(
        issue.code == "promotion_structure_unasserted_entity_quarantined"
        and issue.actual["reason"] == "entity_without_direct_assertion"
        for issue in result.issues
    )
    assert any(
        issue.code == "promotion_structure_unasserted_observation_quarantined"
        for issue in result.issues
    )


def test_direct_structure_change_entity_survives_without_observation_verb():
    evidence = "The α/α₂ phase gradually decreased with increasing recycling number."
    fact = _structure(
        evidence=evidence,
        entities=[
            {
                "name_raw": "α/α₂ phase",
                "entity_type": "phase",
                "role": "decreasing",
                "features": [],
                "raw_expression": "α/α₂ phase",
                "source_evidence": [evidence],
            }
        ],
        features=[],
        structure_kind="phase_assemblage",
    )

    result = promote_axis_facts([_anchor("A1")], [fact], source_text=evidence)

    assert result.accepted
    assert result.accepted[0].data["entities"][0]["name_raw"] == "α/α₂ phase"
    assert not any(
        issue.code == "promotion_structure_unasserted_entity_quarantined"
        for issue in result.issues
    )


def test_direct_structure_assertion_variants_survive_bare_mention_gate():
    cases = [
        (
            "LSHR presented the formation of W-rich γ phase along SESFs.",
            "W-rich γ phase",
            "W-rich γ phase",
        ),
        (
            "The SAED graph confirms the dominance of FCC phase.",
            "FCC phase",
            "FCC phase",
        ),
        (
            "The BCC phase grows to 2 µm and surrounds the FCC matrix.",
            "FCC phase",
            "surrounds the FCC matrix",
        ),
        (
            "Ductile failure was detailed by ductile dimple fracture.",
            "ductile dimple fracture",
            "ductile dimple fracture",
        ),
    ]

    for evidence, name_raw, raw_expression in cases:
        fact = _structure(
            evidence=evidence,
            entities=[
                {
                    "name_raw": name_raw,
                    "entity_type": "phase",
                    "role": "reported",
                    "features": [],
                    "raw_expression": raw_expression,
                    "source_evidence": [evidence],
                }
            ],
            features=[],
            structure_kind="phase_assemblage",
        )

        result = promote_axis_facts(
            [_anchor("A1")], [fact], source_text=evidence
        )

        assert result.accepted
        assert not any(
            issue.code == "promotion_structure_unasserted_entity_quarantined"
            for issue in result.issues
        )


def test_table_structure_entity_is_not_subject_to_bare_mention_gate():
    evidence = "| Phase | α/α₂ |"
    fact = _structure(
        evidence=evidence,
        entities=[
            {
                "name_raw": "α/α₂",
                "entity_type": "phase",
                "role": "reported",
                "features": [],
                "raw_expression": "α/α₂",
                "source_evidence": [evidence],
            }
        ],
        features=[],
        structure_kind="phase_assemblage",
    )

    result = promote_axis_facts([_anchor("A1")], [fact], source_text=evidence)

    assert result.accepted == (fact,)


def test_exact_structure_projection_is_routed_to_named_owner_and_deduplicated():
    evidence = "A1 contained fine gamma-prime precipitates."
    facts = [
        _structure(sample="A1", evidence=evidence),
        _structure(sample="A2", evidence=evidence),
    ]

    result = promote_axis_facts(
        [_anchor("A1"), _anchor("A2")], facts, source_text=evidence
    )

    assert [fact.sample_id_raw for fact in result.accepted] == ["A1"]
    assert {issue.code for issue in result.issues} == {
        "promotion_owner_reassigned",
        "promotion_assertion_duplicate_merged",
    }
    reassigned = next(
        issue for issue in result.issues if issue.code == "promotion_owner_reassigned"
    )
    assert reassigned.actual["before"]["sample_id_raw"] == "A2"
    assert reassigned.actual["after"]["sample_id_raw"] == "A1"


def test_explicit_shared_structure_assertion_preserves_each_named_owner():
    evidence = "A1 and A2 both contained fine gamma-prime precipitates."
    facts = [
        _structure(sample="A1", evidence=evidence),
        _structure(sample="A2", evidence=evidence),
    ]

    result = promote_axis_facts(
        [_anchor("A1"), _anchor("A2")], facts, source_text=evidence
    )

    assert {fact.sample_id_raw for fact in result.accepted} == {"A1", "A2"}
    assert not any(
        issue.code == "promotion_cross_owner_projection_quarantined"
        for issue in result.issues
    )


def test_cross_owner_projection_keeps_named_pair_but_quarantines_third_copy():
    evidence = "A1 and A2 contained fine gamma-prime precipitates."
    facts = [
        _structure(sample="A1", evidence=evidence),
        _structure(sample="A2", evidence=evidence),
        _structure(sample="A3", evidence=evidence),
    ]

    result = promote_axis_facts(
        [_anchor("A1"), _anchor("A2"), _anchor("A3")],
        facts,
        source_text=evidence,
    )

    assert [fact.sample_id_raw for fact in result.accepted] == ["A1", "A2"]
    assert [issue.code for issue in result.issues] == [
        "promotion_cross_owner_projection_quarantined"
    ]
    assert result.issues[0].actual["removed"] == facts[2].model_dump()
    assert result.issues[0].expected["explicit_owners"] == ["a1", "a2"]


def test_collective_owner_grammar_preserves_shared_processing_assertion():
    evidence = "The same heat treatment was applied to all three alloys."
    facts = [
        _processing(sample="A1", process="heat treatment", evidence=evidence),
        _processing(sample="A2", process="heat treatment", evidence=evidence),
        _processing(sample="A3", process="heat treatment", evidence=evidence),
    ]

    result = promote_axis_facts(
        [_anchor("A1"), _anchor("A2"), _anchor("A3")],
        facts,
        source_text=evidence,
    )

    assert [row.sample_id_raw for row in result.accepted] == ["A1", "A2", "A3"]
    assert not any(
        issue.code.startswith("promotion_cross_owner")
        or issue.code == "promotion_ambiguous_shared_assertion_quarantined"
        for issue in result.issues
    )


def test_composition_exact_evidence_projection_quarantines_only_unnamed_owner():
    evidence = (
        "The hatch melt sample with addition of Y2O3 nanoparticles exhibits "
        "many lack-of-fusion defects."
    )
    wrong_copy = _composition(
        sample="multi-spot melt sample",
        component="Y2O3 nanoparticles",
        value="addition",
        unit="not_reported",
        evidence=evidence,
    )
    grounded = _composition(
        sample="hatch melt sample",
        component="Y2O3 nanoparticles",
        value="addition",
        unit="not_reported",
        evidence=evidence,
    )

    result = promote_axis_facts(
        [
            _anchor("multi-spot melt sample"),
            _anchor("hatch melt sample"),
        ],
        [wrong_copy, grounded],
        source_text=evidence,
    )

    assert result.accepted == (grounded,)
    assert [issue.code for issue in result.issues] == [
        "promotion_composition_cross_owner_projection_quarantined"
    ]
    issue = result.issues[0]
    assert issue.actual["removed"] == wrong_copy.model_dump()
    assert issue.actual["copied_owner"] == "multi-spot melt sample"
    assert issue.expected["source_explicit_owner"] == "hatch melt sample"
    assert issue.expected["exact_normalized_evidence"] is True
    assert issue.expected["audit_preserved"] is True


def test_composition_explicit_both_owners_are_preserved():
    evidence = "A1 and A2 both contained 2 wt.% TiB2."
    facts = [
        _composition(
            sample=sample,
            component="TiB2",
            value="2",
            unit="wt.%",
            evidence=evidence,
        )
        for sample in ("A1", "A2")
    ]

    result = promote_axis_facts(
        [_anchor("A1"), _anchor("A2")],
        facts,
        source_text=evidence,
    )

    assert [row.sample_id_raw for row in result.accepted] == ["A1", "A2"]
    assert not any(
        issue.code
        == "promotion_composition_cross_owner_projection_quarantined"
        for issue in result.issues
    )


def test_composition_table_owner_columns_with_equal_values_are_preserved():
    header = "| Component | A1 | A2 |"
    row = "| TiB2 (wt.%) | 2 | 2 |"
    source = "\n".join([header, row])
    facts = [
        _composition(
            sample=sample,
            component="TiB2",
            value="2",
            unit="wt.%",
            evidence=row,
        )
        for sample in ("A1", "A2")
    ]
    for fact in facts:
        fact.source_evidence = [header, row]
        fact.data["source_evidence"] = [header, row]
        fact.data["data_source"] = "table"

    result = promote_axis_facts(
        [_anchor("A1"), _anchor("A2")],
        facts,
        source_text=source,
    )

    assert result.accepted == tuple(facts)
    assert not any(
        issue.code
        == "promotion_composition_cross_owner_projection_quarantined"
        for issue in result.issues
    )


def test_prose_explicit_owner_mismatch_is_quarantined_even_with_different_payload():
    evidence = "A1 exhibited fine gamma-prime precipitates after aging."
    fact = _structure(sample="A2", evidence=evidence)

    result = promote_axis_facts(
        [_anchor("A1"), _anchor("A2")], [fact], source_text=evidence
    )

    assert result.accepted == ()
    assert [issue.code for issue in result.issues] == [
        "promotion_evidence_explicit_owner_mismatch_quarantined"
    ]
    issue = result.issues[0]
    assert issue.actual["removed"] == fact.model_dump()
    assert issue.actual["copied_owner"] == "A2"
    assert issue.expected["source_explicit_owner"] == "A1"
    assert issue.expected["audit_preserved"] is True


def test_prose_explicit_owner_mismatch_keeps_noncore_property_audit_safe():
    evidence = "A1 had a hardness of 420 HV after aging."
    fact = _property(
        sample="A2",
        name="hardness",
        value="420",
        unit="HV",
        condition="",
        evidence=evidence,
    )

    result = promote_axis_facts(
        [_anchor("A1"), _anchor("A2")], [fact], source_text=evidence
    )

    assert result.accepted == ()
    assert [issue.code for issue in result.issues] == [
        "promotion_evidence_explicit_owner_mismatch_quarantined"
    ]


def test_prose_owner_implicit_fact_is_preserved_for_review():
    evidence = "The aged samples exhibited fine gamma-prime precipitates."
    fact = _structure(sample="A2", evidence=evidence)

    result = promote_axis_facts(
        [_anchor("A1"), _anchor("A2")], [fact], source_text=evidence
    )

    assert result.accepted == (fact,)
    assert result.issues == ()


def test_table_owner_mismatch_is_deferred_without_cell_coordinates():
    header = "| Feature | A1 | A2 |"
    row = "| Precipitates | fine gamma-prime precipitates | fine gamma-prime precipitates |"
    source = "\n".join([header, row])
    fact = _structure(sample="A2", evidence=row)
    fact.source_evidence = [header, row]
    fact.data["source_evidence"] = [header, row]

    result = promote_axis_facts(
        [_anchor("A1"), _anchor("A2")], [fact], source_text=source
    )

    assert result.accepted == (fact,)
    assert not any(
        issue.code == "promotion_evidence_explicit_owner_mismatch_quarantined"
        for issue in result.issues
    )


def test_shared_owner_prose_is_preserved_without_broadcast_deletion():
    evidence = "A1 and A2 both exhibited fine gamma-prime precipitates."
    facts = [
        _structure(sample="A1", evidence=evidence),
        _structure(sample="A2", evidence=evidence),
    ]

    result = promote_axis_facts(
        [_anchor("A1"), _anchor("A2")], facts, source_text=evidence
    )

    assert result.accepted == tuple(facts)
    assert not any(
        issue.code == "promotion_evidence_explicit_owner_mismatch_quarantined"
        for issue in result.issues
    )


def test_numeric_condition_mention_is_not_treated_as_material_owner():
    evidence = "Hardness increased from 149 ± 12 to 191 ± 7 HV with 120 s delay."
    fact = _property(
        sample="single wall",
        name="hardness",
        value="191 ± 7",
        unit="HV",
        condition="",
        evidence=evidence,
    )

    result = promote_axis_facts(
        [_anchor("single wall"), _anchor("120 s")], [fact], source_text=evidence
    )

    assert result.accepted == (fact,)
    assert not any(
        issue.code == "promotion_evidence_explicit_owner_mismatch_quarantined"
        for issue in result.issues
    )


def test_generic_sample_descriptor_is_not_treated_as_material_owner():
    evidence = "The BSE images show the wall samples with a basal texture."
    fact = _characterization(sample="Wall 1", method="BSE", evidence=evidence)

    result = promote_axis_facts(
        [_anchor("Wall 1"), _anchor("wall samples")], [fact], source_text=evidence
    )

    assert result.accepted == ()
    assert any(
        issue.code
        == "promotion_characterization_unasserted_result_quarantined"
        and issue.actual["removed"] == fact.model_dump()
        for issue in result.issues
    )


def test_composition_sample_range_scope_is_preserved_without_middle_owner_name():
    evidence = "Samples A1-A3 all contained 2 wt.% TiB2."
    facts = [
        _composition(
            sample=sample,
            component="TiB2",
            value="2",
            unit="wt.%",
            evidence=evidence,
        )
        for sample in ("A1", "A2", "A3")
    ]

    result = promote_axis_facts(
        [_anchor("A1"), _anchor("A2"), _anchor("A3")],
        facts,
        source_text=evidence,
    )

    assert result.accepted == tuple(facts)
    assert not any(
        issue.code
        == "promotion_composition_cross_owner_projection_quarantined"
        for issue in result.issues
    )


def test_composition_sample_list_scope_is_preserved():
    evidence = "Samples A1, A2, and A3 each contained 2 wt.% TiB2."
    facts = [
        _composition(
            sample=sample,
            component="TiB2",
            value="2",
            unit="wt.%",
            evidence=evidence,
        )
        for sample in ("A1", "A2", "A3")
    ]

    result = promote_axis_facts(
        [_anchor("A1"), _anchor("A2"), _anchor("A3")],
        facts,
        source_text=evidence,
    )

    assert result.accepted == tuple(facts)
    assert not any(
        issue.code
        == "promotion_composition_cross_owner_projection_quarantined"
        for issue in result.issues
    )


def test_composition_different_evidence_or_values_are_not_cross_owner_deduped():
    first_evidence = "A1 contained 2 wt.% TiB2."
    second_evidence = "A2 independently contained 2 wt.% TiB2."
    shared_evidence = "A1 contained 3 wt.% TiB2."
    facts = [
        _composition(
            sample="A1",
            component="TiB2",
            value="2",
            unit="wt.%",
            evidence=first_evidence,
        ),
        _composition(
            sample="A2",
            component="TiB2",
            value="2",
            unit="wt.%",
            evidence=second_evidence,
        ),
        _composition(
            sample="A1",
            component="TiB2",
            value="3",
            unit="wt.%",
            evidence=shared_evidence,
        ),
        _composition(
            sample="A2",
            component="TiB2",
            value="4",
            unit="wt.%",
            evidence=shared_evidence,
        ),
    ]
    source = " ".join([first_evidence, second_evidence, shared_evidence])

    result = promote_axis_facts(
        [_anchor("A1"), _anchor("A2")],
        facts,
        source_text=source,
    )

    assert result.accepted == tuple(facts)
    assert not any(
        issue.code
        == "promotion_composition_cross_owner_projection_quarantined"
        for issue in result.issues
    )


def test_composition_bracketed_owner_base_mention_preserves_shared_fact():
    evidence = "GA as well as WA contained 0.2 wt.% oxygen."
    facts = [
        _composition(
            sample=sample,
            component="oxygen",
            value="0.2",
            unit="wt.%",
            evidence=evidence,
        )
        for sample in ("GA [GA powder]", "WA")
    ]

    result = promote_axis_facts(
        [_anchor("GA [GA powder]"), _anchor("WA")],
        facts,
        source_text=evidence,
    )

    assert result.accepted == tuple(facts)
    assert not any(
        issue.code
        == "promotion_composition_cross_owner_projection_quarantined"
        for issue in result.issues
    )


def test_structure_exact_evidence_projection_quarantines_only_unnamed_owner():
    evidence = (
        "Sigma precipitation inhibited B2 phase grain growth in the PBF-EB "
        "samples."
    )
    source = "PBF-LB samples were also examined in this section. " + evidence
    entity = {
        "name_raw": "B2 phase",
        "entity_type": "phase",
        "features": [],
        "raw_expression": "B2 phase",
    }
    grounded = _structure(
        sample="PBF-EB",
        evidence=evidence,
        entities=[entity],
        features=[],
        structure_kind="phase_assemblage",
    )
    wrong_copy = _structure(
        sample="PBF-LB",
        evidence=evidence,
        entities=[entity],
        features=[],
        structure_kind="phase_assemblage",
    )

    result = promote_axis_facts(
        [_anchor("PBF-EB"), _anchor("PBF-LB")],
        [grounded, wrong_copy],
        source_text=source,
    )

    assert result.accepted == (grounded,)
    issue = next(
        issue
        for issue in result.issues
        if issue.code
        == "promotion_structure_exact_evidence_owner_projection_quarantined"
    )
    assert issue.actual["removed"] == wrong_copy.model_dump()
    assert issue.expected["source_explicit_owner"] == "PBF-EB"
    assert issue.expected["audit_preserved"] is True


def test_structure_bracketed_owner_base_mention_preserves_shared_fact():
    evidence = (
        "B2 phase was observed in EPBF as well as non-heat treated LPBF."
    )
    source = (
        "LPBF [non-heat treated] denotes the non-heat treated LPBF condition. "
        + evidence
    )
    entity = {
        "name_raw": "B2 phase",
        "entity_type": "phase",
        "features": [],
        "raw_expression": "B2 phase",
    }
    facts = [
        _structure(
            sample=sample,
            evidence=evidence,
            entities=[entity],
            features=[],
            structure_kind="phase_assemblage",
        )
        for sample in ("EPBF", "LPBF [non-heat treated]")
    ]

    result = promote_axis_facts(
        [_anchor("EPBF"), _anchor("LPBF [non-heat treated]")],
        facts,
        source_text=source,
    )

    assert result.accepted == tuple(facts)
    assert not any(
        issue.code
        == "promotion_structure_exact_evidence_owner_projection_quarantined"
        for issue in result.issues
    )


def test_processing_region_observations_do_not_become_process_stages():
    facts = [
        _processing(
            process="casting",
            evidence=(
                "In cast regions, all samples consisted of nearly equiaxed grains."
            ),
        ),
        _processing(
            process="laser surface remelting",
            evidence=(
                "Fine intergranular phases were left in laser glazing regions."
            ),
        ),
        _processing(
            process="laser glazing",
            evidence=(
                "SEM and EBSD characterizations were performed at laser glazing "
                "regions and cast regions."
            ),
        ),
    ]

    result = promote_axis_facts(
        [_anchor("A1")],
        facts,
        source_text="\n\n".join(
            evidence for fact in facts for evidence in fact.source_evidence
        ),
    )

    assert result.accepted == ()
    assert [issue.code for issue in result.issues] == [
        "promotion_processing_observation_projection_quarantined",
        "promotion_processing_observation_projection_quarantined",
        "promotion_processing_observation_projection_quarantined",
    ]
    assert [issue.actual["removed"] for issue in result.issues] == [
        fact.model_dump() for fact in facts
    ]


def test_explicit_process_events_survive_processing_observation_gate():
    facts = [
        _processing(process="casting", evidence="The five ingots were cast."),
        _processing(
            process="laser glazing",
            evidence="The polished cylinders were laser-glazed on the top surface.",
        ),
        _processing(
            process="laser surface remelting",
            evidence="The specimen surface was remelted with a fiber laser.",
        ),
        _processing(
            process="laser powder bed fusion",
            evidence="The alloy was fabricated by laser powder bed fusion.",
        ),
    ]

    result = promote_axis_facts(
        [_anchor("A1")],
        facts,
        source_text="\n\n".join(
            evidence for fact in facts for evidence in fact.source_evidence
        ),
    )

    assert result.accepted == tuple(facts)
    assert not any(
        issue.code == "promotion_processing_observation_projection_quarantined"
        for issue in result.issues
    )


def test_explicit_process_parameters_preserve_processing_stage():
    evidence = "Table 2. Processing parameters of laser glazing: power 300 W."
    fact = _processing(
        process="laser glazing",
        evidence=evidence,
        parameters=[
            {
                "parameter_name_raw": "laser power",
                "value_raw": "300",
                "unit_raw": "W",
                "source_evidence": "power 300 W",
            }
        ],
    )

    result = promote_axis_facts([_anchor("A1")], [fact], source_text=evidence)

    assert result.accepted == (fact,)
    assert not any(
        issue.code == "promotion_processing_observation_projection_quarantined"
        for issue in result.issues
    )


def test_tex_sample_list_and_both_grammar_preserve_shared_assertions():
    characterization_evidence = (
        "TEM analysis was performed on S_{0}, S_{15}, and S_{70}."
    )
    characterization_facts = [
        _characterization(sample=sample, method="TEM", evidence=characterization_evidence)
        for sample in ("S0", "S15", "S70")
    ]

    characterization = promote_axis_facts(
        [_anchor("S0"), _anchor("S15"), _anchor("S70")],
        characterization_facts,
        source_text=characterization_evidence,
    )

    assert characterization.accepted == tuple(characterization_facts)
    assert characterization.issues == ()

    property_evidence = "Both S_{15} and S_{70} had grain sizes below 10 μm."
    property_facts = [
        _property(
            sample=sample,
            name="average grain size",
            value="<10",
            unit="μm",
            condition="",
            evidence=property_evidence,
        )
        for sample in ("S15", "S70")
    ]

    properties = promote_axis_facts(
        [_anchor("S15"), _anchor("S70")],
        property_facts,
        source_text=property_evidence,
    )

    assert properties.accepted == tuple(property_facts)
    assert properties.issues == ()


def test_enumerated_plural_alloy_caption_preserves_shared_heat_treatment():
    evidence = (
        "Backscattered SEM images showing fully heat treated boron-free, low, "
        "medium and high boron alloys are given in Fig. 1."
    )
    facts = [
        _processing(sample=sample, process="heat treatment", evidence=evidence)
        for sample in (
            "boron-free alloy",
            "low boron alloy",
            "medium boron alloy",
            "high boron alloy",
        )
    ]

    result = promote_axis_facts(
        [_anchor(fact.sample_id_raw) for fact in facts],
        facts,
        source_text=evidence,
    )

    assert result.accepted == tuple(facts)
    assert result.issues == ()


def test_unowned_processing_group_is_preserved_when_no_owner_can_be_proved():
    evidence = "The laser power was 300 W."
    facts = [
        _processing(sample="A1", evidence=evidence),
        _processing(sample="A2", evidence=evidence),
    ]

    result = promote_axis_facts(
        [_anchor("A1"), _anchor("A2")], facts, source_text=evidence
    )

    assert result.accepted == tuple(facts)
    assert result.issues == ()


def test_multi_owner_processing_table_preserves_one_fact_per_named_column():
    source = "\n".join(
        [
            "| Parameter | A1 | A2 |",
            "|---|---:|---:|",
            "| Laser power (W) | 300 | 300 |",
        ]
    )
    evidence = "| Laser power (W) | 300 | 300 |"
    facts = [
        _processing(sample="A1", evidence=evidence),
        _processing(sample="A2", evidence=evidence),
    ]

    result = promote_axis_facts(
        [_anchor("A1"), _anchor("A2")], facts, source_text=source
    )

    assert result.accepted == tuple(facts)
    assert result.issues == ()


def test_coordinated_owner_ellipsis_preserves_each_shared_projection():
    evidence = (
        "XRD characterization was performed on sintered WA and GA "
        "nickel-based alloy 625 samples."
    )
    facts = [
        _characterization(
            sample="WA nickel-based alloy 625",
            method="XRD",
            evidence=evidence,
        ),
        _characterization(
            sample="GA nickel-based alloy 625",
            method="XRD",
            evidence=evidence,
        ),
    ]

    result = promote_axis_facts(
        [_anchor(fact.sample_id_raw) for fact in facts],
        facts,
        source_text=evidence,
    )

    assert result.accepted == tuple(facts)
    assert result.issues == ()


def test_unique_source_owner_reassigns_wrong_projection_before_deduplication():
    evidence = "Ti-6Al-4V wire was examined by SEM."
    facts = [
        _characterization(sample="Wall 1", evidence=evidence),
        _characterization(sample="Wall 2", evidence=evidence),
    ]

    result = promote_axis_facts(
        [
            _anchor("Ti-6Al-4V wire"),
            _anchor("Wall 1"),
            _anchor("Wall 2"),
        ],
        facts,
        source_text=evidence,
    )

    assert len(result.accepted) == 1
    assert result.accepted[0].sample_id_raw == "Ti-6Al-4V wire"
    assert {issue.code for issue in result.issues} == {
        "promotion_owner_reassigned",
        "promotion_assertion_duplicate_merged",
    }
    reassigned = [
        issue for issue in result.issues if issue.code == "promotion_owner_reassigned"
    ]
    assert len(reassigned) == 2
    assert {issue.actual["before"]["sample_id_raw"] for issue in reassigned} == {
        "Wall 1",
        "Wall 2",
    }
    assert {
        issue.actual["after"]["sample_id_raw"] for issue in reassigned
    } == {"Ti-6Al-4V wire"}


def test_single_letter_anchor_is_not_inferred_from_an_indefinite_article():
    evidence = "A FIB sampling analysis was conducted on Specimen II and Specimen III."
    facts = [
        _characterization(sample="Specimen II", method="FIB", evidence=evidence),
        _characterization(sample="Specimen III", method="FIB", evidence=evidence),
    ]

    result = promote_axis_facts(
        [_anchor("A"), _anchor("Specimen II"), _anchor("Specimen III")],
        facts,
        source_text=evidence,
    )

    assert result.accepted == tuple(facts)
    assert not any(
        issue.code == "promotion_owner_reassigned" for issue in result.issues
    )


def test_characterization_requires_a_source_literal_method_and_merges_aliases():
    source = "A1 was examined by scanning electron microscopy (SEM)."
    facts = [
        _characterization(method="SEM", evidence=source),
        _characterization(method="scanning electron microscopy", evidence=source),
        _characterization(method="TEM", evidence=source),
    ]

    result = promote_axis_facts([_anchor("A1")], facts, source_text=source)

    assert len(result.accepted) == 1
    assert result.accepted[0].data["method_raw"] == (
        "scanning electron microscopy"
    )
    assert {issue.code for issue in result.issues} == {
        "promotion_characterization_alias_merged",
        "promotion_characterization_class_normalized",
        "promotion_characterization_method_unsupported",
    }


def test_generic_characterization_alias_yields_to_specific_cited_method():
    source = "A1 was examined by scanning electron microscopy (SEM)."
    facts = [
        _characterization(method="microscopy", evidence=source),
        _characterization(method="SEM", evidence=source),
    ]

    result = promote_axis_facts([_anchor("A1")], facts, source_text=source)

    assert len(result.accepted) == 1
    assert result.accepted[0].data["method_raw"] == "SEM"
    assert [issue.code for issue in result.issues] == [
        "promotion_characterization_alias_merged"
    ]
    assert result.issues[0].actual["removed"] == facts[0].model_dump()


def test_generic_characterization_class_is_normalized_from_one_explicit_modality():
    source = "A1 was examined by scanning electron microscopy (SEM)."
    fact = _characterization(
        method="SEM", method_class="microscopy", evidence=source
    )

    result = promote_axis_facts([_anchor("A1")], [fact], source_text=source)

    assert len(result.accepted) == 1
    assert result.accepted[0].data["method_raw"] == "SEM"
    assert result.accepted[0].data["method_class"] == "SEM"
    assert [issue.code for issue in result.issues] == [
        "promotion_characterization_class_normalized"
    ]
    issue = result.issues[0]
    assert issue.actual["before"] == fact.model_dump()
    assert issue.actual["after"] == result.accepted[0].model_dump()
    assert issue.actual["reason"] == "single_source_explicit_modality"


def test_multi_modality_characterization_keeps_provider_class_unchanged():
    source = "A1 was examined by combined TEM/STEM imaging."
    fact = _characterization(
        method="TEM/STEM", method_class="microscopy", evidence=source
    )

    result = promote_axis_facts([_anchor("A1")], [fact], source_text=source)

    assert result.accepted == (fact,)
    assert result.issues == ()


def test_specific_characterization_class_alias_is_canonicalized_losslessly():
    source = "A1 was examined by electron backscatter diffraction (EBSD)."
    fact = _characterization(
        method="electron backscatter diffraction (EBSD)",
        method_class="electron_backscatter_diffraction",
        evidence=source,
    )

    result = promote_axis_facts([_anchor("A1")], [fact], source_text=source)

    assert len(result.accepted) == 1
    assert result.accepted[0].data["method_class"] == "EBSD"
    assert [issue.code for issue in result.issues] == [
        "promotion_characterization_class_normalized"
    ]


def test_high_resolution_characterization_class_is_not_collapsed_to_parent():
    source = "A1 was examined by high-resolution TEM (HRTEM)."
    fact = _characterization(
        method="HRTEM", method_class="HRTEM", evidence=source
    )

    result = promote_axis_facts([_anchor("A1")], [fact], source_text=source)

    assert result.accepted == (fact,)
    assert result.issues == ()


def test_characterization_projection_is_routed_to_named_owner_and_deduplicated():
    source = "Alloy was examined by EBSD."
    facts = [
        _characterization(sample="Alloy", method="EBSD", evidence=source),
        _characterization(sample="Alloy as-built", method="EBSD", evidence=source),
    ]

    result = promote_axis_facts(
        [_anchor("Alloy"), _anchor("Alloy as-built")],
        facts,
        source_text=source,
    )

    assert result.accepted == (facts[0],)
    assert {issue.code for issue in result.issues} == {
        "promotion_owner_reassigned",
        "promotion_assertion_duplicate_merged",
    }
    reassigned = next(
        issue for issue in result.issues if issue.code == "promotion_owner_reassigned"
    )
    assert reassigned.actual["before"] == facts[1].model_dump()
    assert reassigned.actual["after"]["sample_id_raw"] == "Alloy"


def test_characterization_with_ambiguous_material_state_is_quarantined():
    anchors = [
        _anchor("Alloy", material="Alloy", state="as-built"),
        _anchor("Alloy", material="Alloy", state="aged"),
    ]
    source = "Alloy was examined by EBSD."
    fact = _characterization(sample="Alloy", method="EBSD", evidence=source)

    result = promote_axis_facts(anchors, [fact], source_text=source)

    assert result.accepted == ()
    assert [issue.code for issue in result.issues] == [
        "promotion_ambiguous_owner_quarantined"
    ]
    assert result.issues[0].actual["removed"] == fact.model_dump()


def test_wrong_axis_test_control_is_quarantined_but_material_result_survives():
    source = (
        "Tensile tests used a crosshead speed of 1 mm/min. "
        "A1 had a yield strength of 900 MPa."
    )
    control = _property(
        name="crosshead speed",
        value="1",
        unit="mm/min",
        condition="",
        evidence="Tensile tests used a crosshead speed of 1 mm/min.",
    )
    result_fact = _property(
        name="yield strength",
        value="900",
        unit="MPa",
        condition="",
        evidence="A1 had a yield strength of 900 MPa.",
    )

    result = promote_axis_facts(
        [_anchor("A1")], [control, result_fact], source_text=source
    )

    assert result.accepted == (result_fact,)
    assert [issue.code for issue in result.issues] == [
        "property_non_result_quarantined"
    ]
    assert result.issues[0].actual["removed"] == control.model_dump()


def test_wrong_axis_process_and_geometry_values_do_not_enter_properties():
    facts = [
        _property(
            name="Melt Pool Width",
            value="10.2",
            unit="mm",
            condition="",
            evidence="The melt pool width was 10.2 mm.",
        ),
        _property(
            name="Cooling Rate",
            value="80",
            unit="K/s",
            condition="",
            evidence="The cooling rate was 80 K/s.",
        ),
    ]
    source = " ".join(fact.source_evidence[0] for fact in facts)

    result = promote_axis_facts([_anchor("A1")], facts, source_text=source)

    assert result.accepted == ()
    assert [issue.code for issue in result.issues] == [
        "property_non_result_quarantined",
        "property_non_result_quarantined",
    ]
    assert [issue.actual["removed"] for issue in result.issues] == [
        fact.model_dump() for fact in facts
    ]


def test_process_energy_density_and_test_temperature_do_not_enter_properties():
    facts = [
        _property(
            name="ED",
            value="4.0",
            unit="J/mm²",
            condition="",
            evidence="The applied ED was 4.0 J/mm².",
        ),
        _property(
            name="creep test",
            value="760",
            unit="°C",
            condition="",
            evidence="The creep test was conducted at 760 °C.",
        ),
    ]
    source = " ".join(fact.source_evidence[0] for fact in facts)

    result = promote_axis_facts([_anchor("A1")], facts, source_text=source)

    assert result.accepted == ()
    assert [issue.code for issue in result.issues] == [
        "property_non_result_quarantined",
        "property_non_result_quarantined",
    ]
    assert [issue.actual["removed"] for issue in result.issues] == [
        fact.model_dump() for fact in facts
    ]


def test_structural_metrics_are_audited_outside_properties_without_broad_geometry_loss():
    structural = [
        ("average fitted ellipse aspect ratio", "2", ""),
        ("average equivalent circle diameter", "37.9", "μm"),
        ("Schmid factor (SF) frequency in range 0.4–0.5", "54.80", "%"),
        ("LAGB fraction", "8.15", "%"),
        ("β₀/B₂ phase content", "4.6", "%"),
        ("volume fraction of DINL", "0.08", "%"),
    ]
    facts = [
        _property(
            name=name,
            value=value,
            unit=unit,
            condition="",
            evidence=f"The {name} was {value} {unit}.",
        )
        for name, value, unit in structural
    ]
    valid = _property(
        name="critical thickness",
        value="0.515",
        unit="mm",
        condition="",
        evidence="The critical thickness was 0.515 mm.",
    )
    source = " ".join(fact.source_evidence[0] for fact in [*facts, valid])

    result = promote_axis_facts(
        [_anchor("A1")], [*facts, valid], source_text=source
    )

    assert result.accepted == (valid,)
    assert [issue.code for issue in result.issues] == [
        "property_non_result_quarantined"
    ] * len(facts)
    assert [issue.actual["removed"] for issue in result.issues] == [
        fact.model_dump() for fact in facts
    ]


def test_wrong_axis_electrochemical_controls_and_measurement_metadata_are_quarantined():
    facts = [
        _property(
            name="cathodic reduction potential",
            value="-0.8",
            unit="V_SCE",
            condition="",
            evidence="An initial cathodic reduction at -0.8 V_SCE was used.",
        ),
        _property(
            name="potentiostatic hold potential",
            value="0.15",
            unit="V_SCE",
            condition="",
            evidence="A potentiostatic hold at 0.15 V_SCE was used.",
        ),
        _property(
            name="crystallographic orientation misorientation",
            value="15",
            unit="degree",
            condition="",
            evidence="The orientation threshold used a 15 degree misorientation.",
        ),
        _property(
            name="pyrometer measurement precision",
            value="5",
            unit="°C",
            condition="",
            evidence="The pyrometer measurement precision was 5 °C.",
        ),
    ]
    source = " ".join(fact.source_evidence[0] for fact in facts)

    result = promote_axis_facts([_anchor("A1")], facts, source_text=source)

    assert result.accepted == ()
    assert [issue.code for issue in result.issues] == [
        "property_non_result_quarantined",
        "property_non_result_quarantined",
        "property_non_result_quarantined",
        "property_non_result_quarantined",
    ]


def test_unbound_property_condition_is_removed_without_dropping_grounded_value():
    evidence = "A1 had a yield strength of 900 MPa."
    fact = _property(condition="650 °C", evidence=evidence)

    result = promote_axis_facts([_anchor("A1")], [fact], source_text=evidence)

    assert len(result.accepted) == 1
    assert result.accepted[0].data["test_condition_raw"] == ""
    assert [issue.code for issue in result.issues] == [
        "promotion_unbound_condition_quarantined"
    ]
    assert result.issues[0].actual["before"]["test_condition_raw"] == "650 °C"
    assert result.issues[0].actual["after"]["test_condition_raw"] == ""


def test_quantified_comparative_tensile_is_quarantined_from_properties():
    evidence = "The aged sample retained 74% of its room-temperature yield strength."
    fact = _property(
        name="yield strength retention",
        value="74",
        unit="%",
        condition="",
        evidence=evidence,
    )

    result = promote_axis_facts([_anchor("A1")], [fact], source_text=evidence)

    assert result.accepted == ()
    assert [issue.code for issue in result.issues] == [
        "promotion_comparative_tensile_quarantined"
    ]
    assert result.issues[0].actual["removed"] == fact.model_dump()


def test_unitless_property_is_quarantined_but_dimensionless_ontology_survives():
    unsupported = _property(
        name="strengthening response",
        value="4.9",
        unit="",
        condition="",
        evidence="A1 had a strengthening response of 4.9.",
    )
    stress_exponent = _property(
        name="stress exponent",
        value="4.9",
        unit="",
        condition="",
        evidence="The stress exponent of A1 was 4.9.",
    )
    source = "A1 had a strengthening response of 4.9. The stress exponent of A1 was 4.9."

    result = promote_axis_facts(
        [_anchor("A1")], [unsupported, stress_exponent], source_text=source
    )

    assert result.accepted == (stress_exponent,)
    assert [issue.code for issue in result.issues] == [
        "promotion_unitless_property_quarantined"
    ]
    assert result.issues[0].actual["removed"] == unsupported.model_dump()


def test_inline_unit_keeps_direct_core_tensile_for_existing_unit_recovery():
    evidence = "A1 had a uniform elongation of 7.2% ± 0.4%."
    fact = _property(
        name="uniform elongation",
        value="7.2% ± 0.4%",
        unit="",
        condition="",
        evidence=evidence,
    )

    result = promote_axis_facts([_anchor("A1")], [fact], source_text=evidence)

    assert result.accepted == (fact,)
    assert result.issues == ()


def test_conflicting_core_tensile_values_from_one_assertion_are_quarantined():
    evidence = "A1 yield strength: 900 or 950 MPa (column identity unclear)."
    facts = [
        _property(value="900", condition="", evidence=evidence),
        _property(value="950", condition="", evidence=evidence),
    ]

    result = promote_axis_facts([_anchor("A1")], facts, source_text=evidence)

    assert result.accepted == ()
    assert len(result.issues) == 2
    assert {issue.code for issue in result.issues} == {
        "promotion_tensile_value_conflict_quarantined"
    }
    assert {issue.actual["removed"]["data"]["value_raw"] for issue in result.issues} == {
        "900",
        "950",
    }


def test_promotion_preserves_original_fact_order_for_materialization_stability():
    yield_evidence = "A1 had a yield strength of 850 MPa."
    uts_evidence = "A1 had an ultimate tensile strength of 900 MPa."
    source = f"{yield_evidence}\n\n{uts_evidence}"
    facts = [
        _property(
            name="ultimate tensile strength",
            value="900",
            condition="",
            evidence=uts_evidence,
        ),
        _property(value="850", condition="", evidence=yield_evidence),
    ]

    result = promote_axis_facts([_anchor("A1")], facts, source_text=source)

    assert [fact.data["property_name_raw"] for fact in result.accepted] == [
        "ultimate tensile strength",
        "yield strength",
    ]


def test_core_tensile_ambiguity_is_deferred_to_existing_table_owner_logic():
    anchors = [
        _anchor("Alloy A", material="Alloy A", state="as-built"),
        _anchor("Alloy A", material="Alloy A", state="aged"),
    ]
    evidence = "Alloy A had a yield strength of 900 MPa."
    fact = _property(sample="Alloy A", condition="", evidence=evidence)

    result = promote_axis_facts(anchors, [fact], source_text=evidence)

    assert result.accepted == (fact,)
    assert not any(
        issue.code == "promotion_ambiguous_owner_quarantined"
        for issue in result.issues
    )


def test_noncore_property_ambiguity_is_quarantined_without_broadcast():
    anchors = [
        _anchor("Alloy A", material="Alloy A", state="as-built"),
        _anchor("Alloy A", material="Alloy A", state="aged"),
    ]
    evidence = "Alloy A had a hardness of 420 HV."
    fact = _property(
        sample="Alloy A",
        name="hardness",
        value="420",
        unit="HV",
        condition="",
        evidence=evidence,
    )

    result = promote_axis_facts(anchors, [fact], source_text=evidence)

    assert result.accepted == ()
    assert [issue.code for issue in result.issues] == [
        "promotion_ambiguous_owner_quarantined"
    ]


def test_prose_composition_ambiguity_is_quarantined_without_base_owner():
    anchors = [
        _anchor("Alloy A", material="Alloy A", state="as-built"),
        _anchor("Alloy A", material="Alloy A", state="aged"),
    ]
    evidence = "Alloy A contained 2 wt.% TiB2."
    fact = _composition(sample="Alloy A", component="TiB2", value="2", unit="wt.%", evidence=evidence)

    result = promote_axis_facts(anchors, [fact], source_text=evidence)

    assert result.accepted == ()
    assert [issue.code for issue in result.issues if issue.code == "promotion_ambiguous_owner_quarantined"] == [
        "promotion_ambiguous_owner_quarantined"
    ]


def test_prose_processing_ambiguity_is_quarantined_without_base_owner():
    anchors = [
        _anchor("Alloy A", material="Alloy A", state="as-built"),
        _anchor("Alloy A", material="Alloy A", state="aged"),
    ]
    evidence = "Alloy A was fabricated by laser powder bed fusion."
    fact = _processing(sample="Alloy A", evidence=evidence)

    result = promote_axis_facts(anchors, [fact], source_text=evidence)

    assert result.accepted == ()
    assert [issue.code for issue in result.issues if issue.code == "promotion_ambiguous_owner_quarantined"] == [
        "promotion_ambiguous_owner_quarantined"
    ]


def test_quantitative_structure_feature_dominates_redundant_entity_presence():
    evidence = "A1 contained 42% gamma-prime precipitates."
    fact = _structure(
        evidence=evidence,
        entities=[
            {
                "name_raw": "gamma-prime precipitates",
                "entity_type": "precipitate",
                "features": [],
                "raw_expression": "gamma-prime precipitates",
            }
        ],
        features=[
            {
                "feature_name_raw": "gamma-prime precipitate volume fraction",
                "value_kind": "scalar",
                "value_raw": "42%",
                "unit_raw": "%",
                "data_nature": "reported",
            }
        ],
    )

    result = promote_axis_facts([_anchor("A1")], [fact], source_text=evidence)

    assert len(result.accepted) == 1
    assert result.accepted[0].data["entities"] == []
    assert result.accepted[0].data["features"] == fact.data["features"]
    assert [issue.code for issue in result.issues] == [
        "promotion_structure_entity_presence_shadow_quarantined"
    ]
    assert result.issues[0].actual["removed"] == fact.data["entities"][0]
    assert result.issues[0].actual["survivor_after"]["data"]["features"] == (
        fact.data["features"]
    )


def test_structure_entity_is_preserved_without_entity_named_quantitative_feature():
    evidence = "A1 contained gamma-prime precipitates at a volume fraction of 42%."
    fact = _structure(
        evidence=evidence,
        entities=[
            {
                "name_raw": "gamma-prime precipitates",
                "entity_type": "precipitate",
                "features": [],
                "raw_expression": "gamma-prime precipitates",
            }
        ],
        features=[
            {
                "feature_name_raw": "volume fraction",
                "value_kind": "scalar",
                "value_raw": "42%",
                "unit_raw": "%",
                "data_nature": "reported",
            }
        ],
    )

    result = promote_axis_facts([_anchor("A1")], [fact], source_text=evidence)

    assert result.accepted == (fact,)
    assert not any(
        issue.code == "promotion_structure_entity_presence_shadow_quarantined"
        for issue in result.issues
    )


def test_location_only_structure_context_is_quarantined_with_complete_audit():
    evidence = "The observation was made in the top region of A1."
    fact = _structure(
        evidence=evidence,
        entities=[],
        features=[
            {
                "feature_name_raw": "location",
                "value_kind": "categorical",
                "value_raw": "top region",
                "data_nature": "reported",
            }
        ],
    )

    result = promote_axis_facts([_anchor("A1")], [fact], source_text=evidence)

    assert result.accepted == ()
    assert [issue.code for issue in result.issues] == [
        "promotion_structure_context_quarantined"
    ]
    assert result.issues[0].actual["removed"] == fact.model_dump()


def test_reported_morphology_is_not_treated_as_location_only_context():
    evidence = "A1 showed a cellular morphology."
    fact = _structure(
        evidence=evidence,
        entities=[],
        features=[
            {
                "feature_name_raw": "morphology",
                "value_kind": "categorical",
                "value_raw": "cellular morphology",
                "data_nature": "reported",
            }
        ],
    )

    result = promote_axis_facts([_anchor("A1")], [fact], source_text=evidence)

    assert result.accepted == (fact,)
    assert result.issues == ()


def test_adjacent_table_standard_deviation_is_absorbed_into_reported_mean():
    header = "| Density [g/cm^3] | #1 | #2 |"
    mean_row = "| As-sintered | 8.401 | 8.394 |"
    std_row = "| Std. | 0.013 | 0.024 |"
    source = "\n".join([header, mean_row, std_row])
    mean = _property(
        sample="#1",
        name="Density",
        value="8.401",
        unit="g/cm^3",
        condition="",
        evidence=mean_row,
    )
    shadow = _property(
        sample="#1",
        name="Density Std.",
        value="0.013",
        unit="g/cm^3",
        condition="",
        evidence=std_row,
    )
    for fact, row in ((mean, mean_row), (shadow, std_row)):
        fact.source_evidence = [header, row]
        fact.data["source_evidence"] = [header, row]
        fact.data["data_source"] = "table"
        fact.data["material_state"] = "As-sintered"

    result = promote_axis_facts(
        [_anchor("#1")], [mean, shadow], source_text=source
    )

    assert len(result.accepted) == 1
    assert result.accepted[0].data["property_name_raw"] == "Density"
    assert result.accepted[0].data["value_raw"] == "8.401 ± 0.013"
    assert result.accepted[0].source_evidence == [header, mean_row, std_row]
    assert [issue.code for issue in result.issues] == [
        "promotion_property_statistical_shadow_absorbed"
    ]
    assert result.issues[0].actual["removed"] == shadow.model_dump()
    assert result.issues[0].actual["survivor_before"] == mean.model_dump()
    assert (
        result.issues[0].actual["survivor_after"]
        == result.accepted[0].model_dump()
    )


def test_unbound_table_standard_deviation_is_quarantined_not_promoted():
    header = "| Density [g/cm^3] | #1 |"
    std_row = "| Std. | 0.013 |"
    source = "\n".join([header, std_row])
    shadow = _property(
        sample="#1",
        name="Density standard deviation",
        value="0.013",
        unit="g/cm^3",
        condition="",
        evidence=std_row,
    )
    shadow.source_evidence = [header, std_row]
    shadow.data["source_evidence"] = [header, std_row]
    shadow.data["data_source"] = "table"

    result = promote_axis_facts([_anchor("#1")], [shadow], source_text=source)

    assert result.accepted == ()
    assert [issue.code for issue in result.issues] == [
        "promotion_property_statistical_shadow_quarantined"
    ]
    assert result.issues[0].actual["removed"] == shadow.model_dump()


def test_direct_uncertainty_property_is_not_treated_as_statistical_shadow():
    evidence = "A1 density was 8.401 ± 0.013 g/cm^3."
    fact = _property(
        name="Density",
        value="8.401 ± 0.013",
        unit="g/cm^3",
        condition="",
        evidence=evidence,
    )

    result = promote_axis_facts([_anchor("A1")], [fact], source_text=evidence)

    assert result.accepted == (fact,)
    assert result.issues == ()


def test_composition_claim_dominates_same_assertion_property_axis_copy():
    evidence = "A1 contained 47.86 ± 0.5 at.% Al."
    composition = _composition(evidence=evidence)
    copied_property = _property(
        name="Al content",
        value="47.86 ± 0.5",
        unit="at.%",
        condition="",
        evidence="47.86 ± 0.5 at.% Al",
    )

    result = promote_axis_facts(
        [_anchor("A1")],
        [composition, copied_property],
        source_text=evidence,
    )

    assert result.accepted == (composition,)
    assert [issue.code for issue in result.issues] == [
        "promotion_wrong_axis_duplicate_quarantined"
    ]
    assert result.issues[0].actual["removed"] == copied_property.model_dump()
    assert result.issues[0].actual["dominant"] == composition.model_dump()


def test_structure_feature_dominates_same_assertion_property_axis_copy():
    evidence = "A1 had a random grain distribution and maximum texture index of 2.56."
    structure = _structure(
        evidence=evidence,
        entities=[
            {
                "name_raw": "grain distribution",
                "entity_type": "grain",
                "features": [],
                "raw_expression": "grain distribution",
            }
        ],
        features=[
            {
                "feature_name_raw": "texture index",
                "value_kind": "scalar",
                "value_raw": "2.56",
                "unit_raw": "",
                "data_nature": "reported",
            }
        ],
    )
    copied_property = _property(
        name="maximum texture index",
        value="2.56",
        unit="",
        condition="",
        evidence="maximum texture index of 2.56",
    )

    result = promote_axis_facts(
        [_anchor("A1")],
        [structure, copied_property],
        source_text=evidence,
    )

    assert result.accepted == (structure,)
    assert [issue.code for issue in result.issues] == [
        "promotion_wrong_axis_duplicate_quarantined"
    ]
    assert result.issues[0].actual["dominant"] == structure.model_dump()


def test_wrong_axis_property_completes_unitless_structure_before_quarantine():
    evidence = "A1 had recrystallized grains ranging from 10 to 90 \\mum in size."
    structure = _structure(
        evidence=evidence,
        entities=[],
        features=[
            {
                "feature_name_raw": "grain size",
                "value_kind": "range",
                "value_raw": "10 to 90",
                "source_evidence": [evidence],
            }
        ],
        structure_kind="grain_structure",
    )
    property_copy = _property(
        name="grain size",
        value="10 to 90",
        unit="µm",
        condition="",
        evidence=evidence,
    )

    result = promote_axis_facts(
        [_anchor("A1")],
        [structure, property_copy],
        source_text=evidence,
    )

    assert len(result.accepted) == 1
    assert isinstance(result.accepted[0], StructureFact)
    assert result.accepted[0].data["features"][0]["unit_raw"] == "µm"
    issue = next(
        issue
        for issue in result.issues
        if issue.code == "promotion_wrong_axis_structure_unit_completed"
    )
    assert issue.actual["removed"] == property_copy.model_dump()
    assert issue.actual["dominant_before"] == structure.model_dump()
    assert issue.actual["dominant_after"] == result.accepted[0].model_dump()


def test_wrong_axis_structure_unit_completion_rejects_value_conflict():
    evidence = "A1 grains ranged from 10 to 90 \\mum; A1 pores ranged from 20 to 40 \\mum."
    structure = _structure(
        evidence=evidence,
        entities=[],
        features=[
            {
                "feature_name_raw": "grain size",
                "value_kind": "range",
                "value_raw": "10 to 90",
                "source_evidence": [evidence],
            }
        ],
        structure_kind="grain_structure",
    )
    property_fact = _property(
        name="grain size",
        value="20 to 40",
        unit="µm",
        condition="",
        evidence=evidence,
    )

    result = promote_axis_facts(
        [_anchor("A1")],
        [structure, property_fact],
        source_text=evidence,
    )

    assert result.accepted == (structure, property_fact)
    assert not any(
        issue.code == "promotion_wrong_axis_structure_unit_completed"
        for issue in result.issues
    )


def test_cross_axis_claim_with_different_owner_is_preserved():
    evidence = "A1 contained 47.86 ± 0.5 at.% Al; A2 contained the same amount."
    composition = _composition(sample="A1", evidence=evidence)
    property_fact = _property(
        sample="A2",
        name="Al content",
        value="47.86 ± 0.5",
        unit="at.%",
        condition="",
        evidence=evidence,
    )

    result = promote_axis_facts(
        [_anchor("A1"), _anchor("A2")],
        [composition, property_fact],
        source_text=evidence,
    )

    assert result.accepted == (composition, property_fact)
    assert not any(
        issue.code == "promotion_wrong_axis_duplicate_quarantined"
        for issue in result.issues
    )


def test_strict_structure_atomic_subset_is_absorbed_by_richer_observation():
    evidence = "A1 exhibited SISF with W segregation."
    subset = _structure(
        evidence=evidence,
        entities=[
            {
                "name_raw": "SISF",
                "entity_type": "defect",
                "features": [],
                "raw_expression": "SISF",
            }
        ],
        features=[],
    )
    richer = _structure(
        evidence=evidence,
        entities=[
            {
                "name_raw": "SISF",
                "entity_type": "defect",
                "features": [],
                "raw_expression": "SISF",
            },
            {
                "name_raw": "W segregation",
                "entity_type": "segregation",
                "features": [],
                "raw_expression": "W segregation",
            },
        ],
        features=[],
    )

    result = promote_axis_facts(
        [_anchor("A1")], [subset, richer], source_text=evidence
    )

    assert len(result.accepted) == 1
    assert len(result.accepted[0].data["entities"]) == 2
    assert [issue.code for issue in result.issues] == [
        "promotion_richer_assertion_survived"
    ]
    assert result.issues[0].actual["removed"] == subset.model_dump()


def test_structure_subset_from_independent_assertion_is_not_absorbed():
    first_evidence = "A1 exhibited SISF."
    second_evidence = "A later region exhibited SISF with W segregation."
    subset = _structure(evidence=first_evidence)
    subset.data["entities"][0].update(
        {
            "name_raw": "SISF",
            "entity_type": "defect",
            "raw_expression": "SISF",
        }
    )
    richer = _structure(
        evidence=second_evidence,
        entities=[
            {
                "name_raw": "SISF",
                "entity_type": "defect",
                "features": [],
                "raw_expression": "SISF",
            },
            {
                "name_raw": "W segregation",
                "entity_type": "segregation",
                "features": [],
                "raw_expression": "W segregation",
            },
        ],
        features=[],
    )
    source = f"{first_evidence}\n\n{second_evidence}"

    result = promote_axis_facts(
        [_anchor("A1")], [subset, richer], source_text=source
    )

    assert len(result.accepted) == 2
    assert not any(
        issue.code == "promotion_richer_assertion_survived"
        for issue in result.issues
    )


def test_structure_feature_with_unit_absorbs_unitless_same_assertion_shadow():
    evidence = "A1 had recrystallized grains ranging from 10 to 90 \\mum in size."
    unitless = _structure(
        evidence=evidence,
        entities=[],
        features=[
            {
                "feature_name_raw": "grain size",
                "value_kind": "range",
                "value_raw": "10 to 90",
                "source_evidence": [evidence],
            }
        ],
        structure_kind="grain_structure",
        source_type="cited",
    )
    complete = _structure(
        evidence="recrystallized grains ranging from 10 to 90 \\mum in size",
        entities=[],
        features=[
            {
                "feature_name_raw": "grain size",
                "value_kind": "range",
                "value_raw": "10 to 90",
                "unit_raw": "µm",
                "source_evidence": [
                    "recrystallized grains ranging from 10 to 90 \\mum in size"
                ],
            }
        ],
        structure_kind="grain_structure",
        source_type="reported",
    )

    result = promote_axis_facts(
        [_anchor("A1", role="Reference")],
        [unitless, complete],
        source_text=evidence,
    )

    assert len(result.accepted) == 1
    assert result.accepted[0].data["features"][0]["unit_raw"] == "µm"
    issue = next(
        issue
        for issue in result.issues
        if issue.code == "promotion_structure_unit_shadow_merged"
    )
    assert issue.actual["removed"] == unitless.model_dump()
    assert issue.actual["survivor_before"] == complete.model_dump()
    assert issue.actual["survivor_after"] == result.accepted[0].model_dump()


def test_structure_unit_shadow_gate_preserves_distinct_values_and_blocks():
    first_evidence = "A1 grains were 10 to 90 \\mum in size."
    second_evidence = "A later region had grains 20 to 40 \\mum in size."
    first = _structure(
        evidence=first_evidence,
        entities=[],
        features=[
            {
                "feature_name_raw": "grain size",
                "value_kind": "range",
                "value_raw": "10 to 90",
                "source_evidence": [first_evidence],
            }
        ],
        structure_kind="grain_structure",
    )
    second = _structure(
        evidence=second_evidence,
        entities=[],
        features=[
            {
                "feature_name_raw": "grain size",
                "value_kind": "range",
                "value_raw": "20 to 40",
                "unit_raw": "µm",
                "source_evidence": [second_evidence],
            }
        ],
        structure_kind="grain_structure",
    )

    result = promote_axis_facts(
        [_anchor("A1")],
        [first, second],
        source_text=f"{first_evidence}\n\n{second_evidence}",
    )

    assert result.accepted == (first, second)
    assert not any(
        issue.code == "promotion_structure_unit_shadow_merged"
        for issue in result.issues
    )


def test_prose_owner_value_gate_quarantines_swapped_structure_value():
    evidence = (
        "The average grain sizes of H230 and H230AM after heat treatment "
        "were 13.2 µm and 10.9 µm."
    )
    h230_wrong = _structure(
        sample="H230",
        evidence=evidence,
        entities=[],
        features=[
            {
                "feature_name_raw": "average grain size",
                "value_kind": "scalar",
                "value_raw": "10.9",
                "unit_raw": "µm",
                "source_evidence": [evidence],
            }
        ],
        structure_kind="grain_structure",
    )
    h230am_wrong = _structure(
        sample="H230AM",
        evidence=evidence,
        entities=[],
        features=[
            {
                "feature_name_raw": "average grain size",
                "value_kind": "scalar",
                "value_raw": "13.2",
                "unit_raw": "µm",
                "source_evidence": [evidence],
            }
        ],
        structure_kind="grain_structure",
    )

    result = promote_axis_facts(
        [_anchor("H230"), _anchor("H230AM")],
        [h230_wrong, h230am_wrong],
        source_text=evidence,
    )

    assert result.accepted == ()
    issues = [
        issue
        for issue in result.issues
        if issue.code == "promotion_prose_owner_value_mismatch_quarantined"
    ]
    assert len(issues) == 2
    assert {issue.actual["removed"]["sample_id_raw"] for issue in issues} == {
        "H230",
        "H230AM",
    }


def test_prose_owner_value_gate_preserves_correct_ordered_pairs():
    evidence = (
        "The average grain sizes of H230 and H230AM after heat treatment "
        "were 13.2 µm and 10.9 µm."
    )
    facts = [
        _structure(
            sample="H230",
            evidence=evidence,
            entities=[],
            features=[
                {
                    "feature_name_raw": "average grain size",
                    "value_kind": "scalar",
                    "value_raw": "13.2",
                    "unit_raw": "µm",
                    "source_evidence": [evidence],
                }
            ],
            structure_kind="grain_structure",
        ),
        _structure(
            sample="H230AM",
            evidence=evidence,
            entities=[],
            features=[
                {
                    "feature_name_raw": "average grain size",
                    "value_kind": "scalar",
                    "value_raw": "10.9",
                    "unit_raw": "µm",
                    "source_evidence": [evidence],
                }
            ],
            structure_kind="grain_structure",
        ),
    ]
    result = promote_axis_facts(
        [_anchor("H230"), _anchor("H230AM")], facts, source_text=evidence
    )
    assert result.accepted == tuple(facts)
    assert not any(
        issue.code == "promotion_prose_owner_value_mismatch_quarantined"
        for issue in result.issues
    )


def test_prose_owner_value_gate_does_not_touch_markdown_table_bindings():
    evidence = (
        "| Sample | Grain size (µm) |\n"
        "| H230 | 13.2 |\n"
        "| H230AM | 10.9 |"
    )
    facts = [
        _structure(
            sample="H230",
            evidence=evidence,
            entities=[],
            features=[
                {
                    "feature_name_raw": "grain size",
                    "value_kind": "scalar",
                    "value_raw": "13.2",
                    "unit_raw": "µm",
                    "source_evidence": [evidence],
                }
            ],
            structure_kind="grain_structure",
        ),
        _structure(
            sample="H230AM",
            evidence=evidence,
            entities=[],
            features=[
                {
                    "feature_name_raw": "grain size",
                    "value_kind": "scalar",
                    "value_raw": "10.9",
                    "unit_raw": "µm",
                    "source_evidence": [evidence],
                }
            ],
            structure_kind="grain_structure",
        ),
    ]

    result = promote_axis_facts(
        [_anchor("H230"), _anchor("H230AM")],
        facts,
        source_text=evidence,
    )

    assert result.accepted == tuple(facts)
    assert not any(
        issue.code == "promotion_prose_owner_value_mismatch_quarantined"
        for issue in result.issues
    )


def test_prose_owner_value_gate_quarantines_swapped_core_tensile_values():
    evidence = "The yield strengths of A1 and A2 were 900 MPa and 800 MPa."
    facts = [
        _property(
            sample="A1",
            name="yield strength",
            value="800",
            unit="MPa",
            condition="",
            evidence=evidence,
        ),
        _property(
            sample="A2",
            name="yield strength",
            value="900",
            unit="MPa",
            condition="",
            evidence=evidence,
        ),
    ]

    result = promote_axis_facts(
        [_anchor("A1"), _anchor("A2")], facts, source_text=evidence
    )

    assert result.accepted == ()
    issues = [
        issue
        for issue in result.issues
        if issue.code == "promotion_prose_owner_value_mismatch_quarantined"
    ]
    assert len(issues) == 2
    assert {issue.actual["removed"]["sample_id_raw"] for issue in issues} == {
        "A1",
        "A2",
    }


def test_prose_owner_value_gate_preserves_ordered_core_tensile_values():
    evidence = "The yield strengths of A1 and A2 were 900 MPa and 800 MPa."
    facts = [
        _property(
            sample="A1",
            name="yield strength",
            value="900",
            unit="MPa",
            condition="",
            evidence=evidence,
        ),
        _property(
            sample="A2",
            name="yield strength",
            value="800",
            unit="MPa",
            condition="",
            evidence=evidence,
        ),
    ]

    result = promote_axis_facts(
        [_anchor("A1"), _anchor("A2")], facts, source_text=evidence
    )

    assert result.accepted == tuple(facts)
    assert not any(
        issue.code == "promotion_prose_owner_value_mismatch_quarantined"
        for issue in result.issues
    )


def test_condition_label_is_bound_only_when_source_literal_and_discriminative():
    evidence = "The yield strength at 800 °C was 900 MPa."
    fact = _property(
        sample="A1",
        value="900",
        condition="",
        evidence=evidence,
    )
    fact.data["condition_label_raw"] = "800 °C"

    result = promote_axis_facts([_anchor("A1")], [fact], source_text=evidence)

    assert len(result.accepted) == 1
    assert result.accepted[0].data["test_condition_raw"] == "800 °C"
    assert any(issue.code == "promotion_condition_label_bound" for issue in result.issues)


def test_condition_label_routes_generic_fact_to_existing_state_owner():
    evidence = (
        "The hardness values for 0 s delay and 300 s delay were 334 HV and "
        "346 HV, respectively."
    )
    facts = [
        _property(
            sample="Ti_{64}",
            name="Vickers microhardness",
            value="334",
            unit="HV",
            condition="",
            evidence=evidence,
        ),
        _property(
            sample="Ti_{64}",
            name="Vickers microhardness",
            value="346",
            unit="HV",
            condition="",
            evidence=evidence,
        ),
    ]
    facts[0].data["condition_label_raw"] = "0 s delay"
    facts[1].data["condition_label_raw"] = "300 s delay"
    anchors = [
        _anchor("Ti_{64}", material="Ti_{64}"),
        _anchor("0 s Delay", material="Ti_{64}", state="0 s Delay"),
        _anchor("300 s Delay", material="Ti_{64}", state="300 s Delay"),
    ]

    result = promote_axis_facts(anchors, facts, source_text=evidence)

    assert [row.sample_id_raw for row in result.accepted] == [
        "0 s Delay",
        "300 s Delay",
    ]
    assert all(row.data["test_condition_raw"] for row in result.accepted)
    assert sum(
        issue.code == "promotion_condition_owner_reassigned"
        for issue in result.issues
    ) == 2


def test_ambiguous_respectively_values_with_one_metric_are_quarantined():
    evidence = "The fracture-location ranges were 1.10 and 0.96 mm, respectively."
    facts = [
        _property(
            sample="Ti-6Al-4V",
            name="fracture location variation range",
            value="1.10",
            unit="mm",
            condition="",
            evidence=evidence,
        ),
        _property(
            sample="Ti-6Al-4V",
            name="fracture location variation range",
            value="0.96",
            unit="mm",
            condition="",
            evidence=evidence,
        ),
    ]

    result = promote_axis_facts([_anchor("Ti-6Al-4V")], facts, source_text=evidence)

    assert result.accepted == ()
    assert sum(
        issue.code == "promotion_respectively_mapping_ambiguous_quarantined"
        for issue in result.issues
    ) == 2


def test_respectively_different_property_names_remain_atomic():
    evidence = "The yield strength and elongation were 900 MPa and 20%, respectively."
    facts = [
        _property(
            sample="A1",
            name="yield strength",
            value="900",
            unit="MPa",
            condition="",
            evidence=evidence,
        ),
        _property(
            sample="A1",
            name="elongation",
            value="20",
            unit="%",
            condition="",
            evidence=evidence,
        ),
    ]

    result = promote_axis_facts([_anchor("A1")], facts, source_text=evidence)

    assert {
        row.data["property_name_raw"] for row in result.accepted
    } == {"yield strength", "elongation"}
    assert {
        row.data["value_raw"] for row in result.accepted
    } == {"900", "20"}
    assert not any(
        issue.code == "promotion_respectively_mapping_ambiguous_quarantined"
        for issue in result.issues
    )


def test_explicit_treatment_condition_is_bound_from_same_tensile_assertion():
    evidence = (
        "Subsequent thermal treatment (800 °C/4 h) leads to an ultimate tensile "
        "strength of 1148 MPa and a ductility of 28 %."
    )
    fact = _property(
        sample="HT-HEA",
        name="ductility",
        value="28",
        unit="%",
        condition="",
        evidence=evidence,
    )

    result = promote_axis_facts([_anchor("HT-HEA")], [fact], source_text=evidence)

    assert len(result.accepted) == 1
    assert "800 °C/4 h" in result.accepted[0].data["test_condition_raw"]
    issue = next(
        issue
        for issue in result.issues
        if issue.code == "promotion_explicit_treatment_condition_bound"
    )
    assert issue.actual["before"] == fact.model_dump()
    assert issue.actual["after"] == result.accepted[0].model_dump()


def test_feedstock_composition_on_processed_owner_is_quarantined_without_anchor():
    evidence = (
        "A gas-atomized alloy powder, comprising Al-3.89Cu-1.22Li-0.98Sc-0.43Zr "
        "(wt%), was employed as the feedstock for the LPBF process."
    )
    fact = _composition(sample="HT", evidence=evidence)

    result = promote_axis_facts([_anchor("HT")], [fact], source_text=evidence)

    assert result.accepted == ()
    issue = next(
        issue
        for issue in result.issues
        if issue.code == "promotion_feedstock_owner_mismatch_quarantined"
    )
    assert issue.actual["removed"] == fact.model_dump()


def test_explicit_sample_named_as_powder_keeps_composition_owner():
    evidence = "Chemical compositions of H230 powder are listed in Table 1."
    fact = _composition(sample="H230", evidence=evidence)

    result = promote_axis_facts([_anchor("H230")], [fact], source_text=evidence)

    assert result.accepted == (fact,)
    assert not any(
        issue.code.startswith("promotion_feedstock_owner_")
        for issue in result.issues
    )


def test_feedstock_context_does_not_quarantine_material_identity():
    """Feedstock wording must not remove a material identity fact."""

    evidence = (
        "The gas-atomized alloy powder was employed as the feedstock for the LPBF process."
    )
    fact = CompositionFact(
        sample_id_raw="AF",
        fact_type="material_identity",
        evidence_unit_id="prose-L000001-L000001-identity",
        data={
            "material_family": "nickel-based alloy",
            "material_name_raw": "AF",
            "designation_raw": "AF",
            "feedstock_form": "gas-atomized powder",
        },
        source_evidence=[evidence],
        confidence=0.9,
    )

    result = promote_axis_facts([_anchor("AF")], [fact], source_text=evidence)

    assert result.accepted == (fact,)
    assert not any(
        issue.code.startswith("promotion_feedstock_owner_")
        for issue in result.issues
    )


def test_tensile_table_unique_row_coordinate_is_preserved():
    source = (
        "| Samples | Yield strength (MPa) | Elongation (%) |\n"
        "|---|---:|---:|\n"
        "| AF-RT | 482 ± 1 | 9 ± 1 |\n"
        "| AF-200 C | 402 ± 14 | 11 ± 2 |"
    )
    evidence = "| AF-RT | 482 ± 1 | 9 ± 1 |"
    fact = _property(sample="AF", value="482 ± 1", condition="RT", evidence=evidence)

    result = promote_axis_facts([_anchor("AF")], [fact], source_text=source)

    assert result.accepted == (fact,)
    assert not any(
        issue.code == "promotion_table_owner_condition_ambiguous_quarantined"
        for issue in result.issues
    )


def test_tensile_table_unique_value_selects_one_row_for_shared_base_owner():
    source = (
        "| Samples | Yield strength (MPa) | Elongation (%) |\n"
        "|---|---:|---:|\n"
        "| AF-RT | 482 ± 1 | 9 ± 1 |\n"
        "| AF-200 C | 402 ± 14 | 11 ± 2 |"
    )
    evidence = "| AF-200 C | 402 ± 14 | 11 ± 2 |"
    fact = _property(sample="AF", value="402 ± 14", condition="", evidence=evidence)
    anchors = [_anchor("AF", state="RT"), _anchor("AF", state="200 C")]

    result = promote_axis_facts(anchors, [fact], source_text=source)

    assert result.accepted == (fact,)
    assert not any(
        issue.code == "promotion_table_owner_condition_ambiguous_quarantined"
        for issue in result.issues
    )


def test_tensile_table_repeated_value_across_owner_columns_is_quarantined():
    source = (
        "| Property | A1 | A2 |\n"
        "|---|---:|---:|\n"
        "| Yield strength (MPa) | 900 | 900 |"
    )
    evidence = "| Yield strength (MPa) | 900 | 900 |"
    fact = _property(sample="A1", value="900", condition="", evidence=evidence)

    result = promote_axis_facts(
        [_anchor("A1"), _anchor("A2")], [fact], source_text=source
    )

    assert result.accepted == ()
    issue = next(
        issue
        for issue in result.issues
        if issue.code == "promotion_table_owner_condition_ambiguous_quarantined"
    )
    assert issue.actual["removed"] == fact.model_dump()
    assert len(issue.actual["all_owner_value_hits"]) == 2
    assert issue.expected["broadcast"] is False


def test_tensile_table_unique_owner_column_value_is_preserved():
    source = (
        "| Property | A1 | A2 |\n"
        "|---|---:|---:|\n"
        "| Yield strength (MPa) | 900 | 800 |"
    )
    evidence = "| Yield strength (MPa) | 900 | 800 |"
    fact = _property(sample="A1", value="900", condition="", evidence=evidence)

    result = promote_axis_facts(
        [_anchor("A1"), _anchor("A2")], [fact], source_text=source
    )

    assert result.accepted == (fact,)


def test_tensile_feedstock_condition_is_isolated_but_value_survives():
    evidence = (
        "A1 had a yield strength of 900 MPa; gas-atomized powder was used as feedstock."
    )
    fact = _property(
        sample="A1",
        value="900",
        condition="gas-atomized powder",
        evidence=evidence,
    )

    result = promote_axis_facts([_anchor("A1")], [fact], source_text=evidence)

    assert len(result.accepted) == 1
    assert result.accepted[0].data["value_raw"] == "900"
    assert result.accepted[0].data["test_condition_raw"] == ""
    issue = next(
        issue
        for issue in result.issues
        if issue.code == "promotion_tensile_condition_scope_quarantined"
    )
    assert issue.actual["before"] == fact.model_dump()
    assert issue.actual["after"] == result.accepted[0].model_dump()


def test_external_reference_condition_is_not_attached_to_current_experiment():
    evidence = (
        "A1 had a yield strength of 900 MPa. "
        "A reference simulation at 700 °C predicted 950 MPa."
    )
    fact = _property(sample="A1", value="900", condition="700 °C", evidence=evidence)

    result = promote_axis_facts([_anchor("A1")], [fact], source_text=evidence)

    assert len(result.accepted) == 1
    assert result.accepted[0].data["test_condition_raw"] == ""
    assert any(
        issue.code == "promotion_tensile_condition_scope_quarantined"
        for issue in result.issues
    )


def test_tensile_source_gate_does_not_touch_composition():
    evidence = "A1 contained 47.86 ± 0.5 at.% Al."
    fact = _composition(sample="A1", evidence=evidence)

    result = promote_axis_facts([_anchor("A1")], [fact], source_text=evidence)

    assert result.accepted == (fact,)
    assert not any("tensile" in issue.code for issue in result.issues)


def test_cited_previous_work_projection_is_quarantined_without_owner_literal():
    evidence = "Previous work [26] reported fine gamma-prime precipitates in the alloy."
    fact = _structure(sample="A1", evidence=evidence)

    result = promote_axis_facts([_anchor("A1")], [fact], source_text=evidence)

    assert any(
        issue.code == "promotion_external_source_projection_quarantined"
        for issue in result.issues
    )
    issue = next(
        issue
        for issue in result.issues
        if issue.code == "promotion_external_source_projection_quarantined"
    )
    assert issue.actual["removed"] == fact.model_dump()
    assert issue.expected["external_projection"] is False


def test_cited_sentence_with_literal_current_owner_is_preserved():
    evidence = "A1 showed fine gamma-prime precipitates; previous work [26] is cited for context."
    fact = _structure(sample="A1", evidence=evidence)

    result = promote_axis_facts([_anchor("A1")], [fact], source_text=evidence)

    assert fact in result.accepted
    assert not any(
        issue.code == "promotion_external_source_projection_quarantined"
        for issue in result.issues
    )
