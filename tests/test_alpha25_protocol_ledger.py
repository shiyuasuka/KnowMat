from __future__ import annotations

from knowmat.alpha25.contracts import InventoryAnchor, PropertyFact
from knowmat.alpha25.materialize import materialize_candidate
from knowmat.alpha25.property_context import TensileProtocolLedger


def _property(**overrides: object) -> dict[str, object]:
    row: dict[str, object] = {
        "property_name_raw": "Ultimate Tensile Strength",
        "value_raw": "781",
        "unit_raw": "MPa",
        "test_method_raw": "tensile test",
        "test_standard_raw": "",
        "test_condition_raw": "",
        "test_specimen_raw": "",
        "property_id_candidate": "table-cell:explicit-coordinate",
        "raw_note": "",
        "data_source": "table",
        "source_evidence": ["| Ti64-H | UTS (MPa) | 781 |"],
        "confidence": 0.95,
    }
    row.update(overrides)
    return row


def test_v203_owner_local_protocol_ledger_keeps_literal_dimensions(monkeypatch):
    monkeypatch.setenv("KNOWMAT2_ALPHA25_TENSILE_PROTOCOL_LEDGER_V203", "1")
    source = """
## Tensile testing

Tensile tests for Ti64-H were conducted at room temperature on an MTS testing
machine at a crosshead speed of 0.6 mm/min according to ASTM E8. Strain was
measured by digital image correlation and three specimens were tested.
"""

    decision = TensileProtocolLedger(source).bind(
        _property(),
        owner_role="Target",
        owner_labels=("Ti64-H",),
        other_owner_labels=("Ti64-V",),
    )

    assert decision.status == "bound"
    assert decision.scope == "owner_local"
    assert decision.condition_raw is not None
    assert "room temperature" in decision.condition_raw
    assert "0.6 mm/min" in decision.condition_raw
    assert "ASTM E8" in decision.condition_raw
    assert "MTS testing machine" in decision.condition_raw
    assert "digital image correlation" in decision.condition_raw
    assert "three specimens" in decision.condition_raw
    assert set(decision.contributed_dimensions) >= {
        "temperature",
        "rate",
        "standard",
        "equipment",
        "strain_measurement",
        "replicates",
    }
    assert len(decision.selected_events) == 1
    assert decision.selected_events[0].decision_key.startswith(
        "tensile-protocol-event:"
    )


def test_v203_explicit_global_protocol_requires_a_property_coordinate(monkeypatch):
    monkeypatch.setenv("KNOWMAT2_ALPHA25_TENSILE_PROTOCOL_LEDGER_V203", "1")
    source = """
## Mechanical tests

All tensile tests were conducted at 650 °C after a 15 min hold at a strain rate
of 5 × 10^-3 s^-1 with the loading direction parallel to the build direction.
"""
    ledger = TensileProtocolLedger(source)

    bound = ledger.bind(
        _property(),
        owner_role="Target",
        owner_labels=("Ti64-H",),
        other_owner_labels=("Ti64-V",),
    )
    uncoordinated = ledger.bind(
        _property(property_id_candidate=""),
        owner_role="Target",
        owner_labels=("Ti64-H",),
        other_owner_labels=("Ti64-V",),
    )

    assert bound.status == "bound"
    assert bound.scope == "target_global"
    assert bound.condition_raw is not None
    assert "650 °C" in bound.condition_raw
    assert "15 min hold" in bound.condition_raw
    assert "5 × 10^-3 s^-1" in bound.condition_raw
    assert "parallel to the build direction" in bound.condition_raw
    assert uncoordinated.status == "ambiguous"
    assert uncoordinated.condition_raw is None


def test_v203_unique_protocol_binds_only_to_dense_target_coordinate(monkeypatch):
    monkeypatch.setenv("KNOWMAT2_ALPHA25_TENSILE_PROTOCOL_LEDGER_V203", "1")
    source = """
## Mechanical testing

Rate controlled tensile tests at 5 mm/min were performed using an MTS 880.
"""
    ledger = TensileProtocolLedger(source)

    bound = ledger.bind(
        _property(property_id_candidate="dense-table-cell:literal"),
        owner_role="Target",
        owner_labels=("GA sample sintered at 1285 °C",),
        other_owner_labels=("WA sample sintered at 1270 °C",),
    )
    uncoordinated = ledger.bind(
        _property(property_id_candidate="temporary"),
        owner_role="Target",
        owner_labels=("GA sample sintered at 1285 °C",),
        other_owner_labels=("WA sample sintered at 1270 °C",),
    )

    assert bound.status == "bound"
    assert bound.scope == "target_global"
    assert bound.condition_raw == "at 5 mm/min"
    assert uncoordinated.status == "ambiguous"


def test_v203_protocol_ledger_keeps_reference_isolated(monkeypatch):
    monkeypatch.setenv("KNOWMAT2_ALPHA25_TENSILE_PROTOCOL_LEDGER_V203", "1")
    source = """
All tensile tests were conducted at room temperature at a strain rate of
1 × 10^-3 s^-1 according to ASTM E8.
"""

    decision = TensileProtocolLedger(source).bind(
        _property(),
        owner_role="Reference",
        owner_labels=("Literature alloy",),
        other_owner_labels=("Ti64-H",),
    )

    assert decision.status == "reference"
    assert decision.condition_raw is None
    assert decision.contributed_dimensions == ()


def test_v203_protocol_ledger_fails_closed_for_two_incompatible_events(
    monkeypatch,
):
    monkeypatch.setenv("KNOWMAT2_ALPHA25_TENSILE_PROTOCOL_LEDGER_V203", "1")
    source = """
## Mechanical tests

Tensile tests were conducted at room temperature at a strain rate of
1 × 10^-3 s^-1.

Tensile tests were conducted at 650 °C at a strain rate of 5 × 10^-3 s^-1.
"""

    decision = TensileProtocolLedger(source).bind(
        _property(property_id_candidate=""),
        owner_role="Target",
        owner_labels=("Ti64-H",),
        other_owner_labels=("Ti64-V",),
    )

    assert decision.status == "ambiguous"
    assert decision.condition_raw is None
    assert len(decision.candidate_events) == 2


def test_v203_protocol_ledger_does_not_treat_material_state_as_test_temperature(
    monkeypatch,
):
    monkeypatch.setenv("KNOWMAT2_ALPHA25_TENSILE_PROTOCOL_LEDGER_V203", "1")
    source = """
The samples were sintered at 1300 °C before machining. Tensile tests were
conducted at room temperature on an MTS machine at 5 mm/min.
"""

    decision = TensileProtocolLedger(source).bind(
        _property(source_evidence=["Ti64-H showed a UTS of 781 MPa."]),
        owner_role="Target",
        owner_labels=("Ti64-H",),
    )

    assert decision.status == "bound"
    assert decision.condition_raw is not None
    assert "room temperature" in decision.condition_raw
    assert "1300" not in decision.condition_raw
    assert "sintered" not in decision.condition_raw


def test_v203_protocol_ledger_preserves_conflicting_existing_condition(
    monkeypatch,
):
    monkeypatch.setenv("KNOWMAT2_ALPHA25_TENSILE_PROTOCOL_LEDGER_V203", "1")
    source = """
Tensile tests were conducted at 650 °C at a strain rate of 5 × 10^-3 s^-1.
"""

    decision = TensileProtocolLedger(source).bind(
        _property(test_condition_raw="room temperature"),
        owner_role="Target",
        owner_labels=("Ti64-H",),
    )

    assert decision.status == "conflict"
    assert decision.condition_raw == "room temperature"
    assert decision.contributed_dimensions == ()


def test_v203_protocol_event_keys_are_stable(monkeypatch):
    monkeypatch.setenv("KNOWMAT2_ALPHA25_TENSILE_PROTOCOL_LEDGER_V203", "1")
    source = """
Tensile tests for Ti64-H were conducted at room temperature on an MTS machine
at 0.6 mm/min according to ASTM E8.
"""

    first = TensileProtocolLedger(source).events
    second = TensileProtocolLedger(source).events

    assert first
    assert [row.to_dict() for row in first] == [row.to_dict() for row in second]


def test_v203_materialization_binds_ledger_and_preserves_complete_audit(
    monkeypatch,
):
    monkeypatch.setenv("KNOWMAT2_ALPHA25_TENSILE_PROTOCOL_LEDGER_V203", "1")
    source = """
## Tensile testing

Tensile tests for Ti64-H were conducted at room temperature on an MTS testing
machine at 0.6 mm/min according to ASTM E8. Strain was measured by digital
image correlation and three specimens were tested.
"""
    anchor = InventoryAnchor(
        sample_id_raw="Ti64-H",
        material_name_raw="Ti-6Al-4V",
        state_raw="heat treated",
        role="Target",
        data_nature="Experimental",
        source_evidence=["Ti64-H"],
        confidence=0.95,
    )
    payload = _property()
    fact = PropertyFact(
        sample_id_raw="Ti64-H",
        fact_type="property",
        data=payload,
        source_evidence=list(payload["source_evidence"]),
        confidence=0.95,
    )

    result = materialize_candidate([anchor], [fact], source_text=source)

    prop = result.document["items"][0]["Extracted_Data"]["Properties"][0]
    assert "MTS testing machine" in prop["test_condition_raw"]
    assert "digital image correlation" in prop["test_condition_raw"]
    assert "three specimens" in prop["test_condition_raw"]
    issue = next(
        row for row in result.issues if row.code == "tensile_protocol_ledger_bound"
    )
    assert issue.actual["before"]["test_condition_raw"] in (None, "")
    assert issue.actual["after"]["test_condition_raw"] == prop["test_condition_raw"]
    assert set(issue.actual["decision"]["contributed_dimensions"]) >= {
        "equipment",
        "strain_measurement",
        "replicates",
    }
    assert issue.actual["decision"]["selected_events"][0][
        "decision_key"
    ].startswith("tensile-protocol-event:")


def test_v203_materialization_switch_off_preserves_v202_condition(monkeypatch):
    monkeypatch.setenv("KNOWMAT2_ALPHA25_TENSILE_PROTOCOL_LEDGER_V203", "0")
    source = """
Tensile tests for Ti64-H were conducted at room temperature on an MTS testing
machine at 0.6 mm/min according to ASTM E8.
"""
    anchor = InventoryAnchor(
        sample_id_raw="Ti64-H",
        material_name_raw="Ti-6Al-4V",
        role="Target",
        data_nature="Experimental",
        source_evidence=["Ti64-H"],
        confidence=0.95,
    )
    payload = _property()
    fact = PropertyFact(
        sample_id_raw="Ti64-H",
        fact_type="property",
        data=payload,
        source_evidence=list(payload["source_evidence"]),
        confidence=0.95,
    )

    result = materialize_candidate([anchor], [fact], source_text=source)

    prop = result.document["items"][0]["Extracted_Data"]["Properties"][0]
    assert "MTS" not in (prop["test_condition_raw"] or "")
    assert not any(
        row.code.startswith("tensile_protocol_ledger_") for row in result.issues
    )


def test_v203_dense_tensile_table_completion_materializes_explicit_cells(
    monkeypatch,
):
    monkeypatch.setenv(
        "KNOWMAT2_ALPHA25_DENSE_TENSILE_TABLE_COMPLETION_V203", "1"
    )
    source = """
| Sample | Yield Strength (MPa) | UTS (MPa) | Total Elongation (%) |
| --- | --- | --- | --- |
| Ti64-H | 486 | 781 | 12.0 |
"""
    anchor = InventoryAnchor(
        sample_id_raw="Ti64-H",
        material_name_raw="Ti-6Al-4V",
        state_raw="heat treated",
        role="Target",
        data_nature="Experimental",
        source_evidence=["Ti64-H"],
        confidence=0.95,
    )

    result = materialize_candidate([anchor], [], source_text=source)

    properties = result.document["items"][0]["Extracted_Data"]["Properties"]
    assert [
        (row["property_name_raw"], row["value_raw"], row["unit_raw"])
        for row in properties
    ] == [
        ("Yield Strength", "486", "MPa"),
        ("Ultimate Tensile Strength", "781", "MPa"),
        ("Total Elongation", "12.0", "%"),
    ]
    recovered = [
        row
        for row in result.issues
        if row.code == "dense_tensile_table_cell_recovered"
    ]
    assert len(recovered) == 3
    assert all(
        row.actual["cell"]["decision_key"].startswith("dense-table-cell:")
        for row in recovered
    )
    assert all(row.actual["before"] is None for row in recovered)


def test_v203_dense_completion_does_not_duplicate_existing_coordinate(monkeypatch):
    monkeypatch.setenv(
        "KNOWMAT2_ALPHA25_DENSE_TENSILE_TABLE_COMPLETION_V203", "1"
    )
    header = "| Sample | UTS (MPa) |"
    row = "| Ti64-H | 781 |"
    source = f"{header}\n| --- | --- |\n{row}\n"
    anchor = InventoryAnchor(
        sample_id_raw="Ti64-H",
        material_name_raw="Ti-6Al-4V",
        role="Target",
        data_nature="Experimental",
        source_evidence=["Ti64-H"],
        confidence=0.95,
    )
    payload = _property(source_evidence=[header, row])
    fact = PropertyFact(
        sample_id_raw="Ti64-H",
        fact_type="property",
        data=payload,
        source_evidence=[header, row],
        confidence=0.95,
    )

    result = materialize_candidate([anchor], [fact], source_text=source)

    properties = result.document["items"][0]["Extracted_Data"]["Properties"]
    assert len(properties) == 1
    issue = next(
        row
        for row in result.issues
        if row.code == "dense_tensile_table_cell_rejected"
        and row.actual.get("reason") == "existing_coordinate_owned"
    )
    assert issue.actual["existing_fact"]["data"]["value_raw"] == "781"


def test_v203_dense_cell_migrates_alias_duplicates_and_clears_owner_state_condition(
    monkeypatch,
):
    monkeypatch.setenv(
        "KNOWMAT2_ALPHA25_DENSE_TENSILE_TABLE_COMPLETION_V203", "1"
    )
    monkeypatch.setenv("KNOWMAT2_ALPHA25_TENSILE_PROTOCOL_LEDGER_V203", "1")
    source = """
Rate controlled tensile tests at 5 mm/min were performed using an MTS 880.

| Sample | UTS (MPa) |
| --- | --- |
| WA sample sintered at 1270 °C | 386 ± 15 |
"""
    anchor = InventoryAnchor(
        sample_id_raw="WA sample sintered at 1270 °C",
        material_name_raw="alloy 625",
        state_raw="sintered at 1270 °C",
        role="Target",
        data_nature="Experimental",
        source_evidence=["WA sample sintered at 1270 °C"],
        confidence=0.95,
    )
    table_fact = PropertyFact(
        sample_id_raw=anchor.sample_id_raw,
        fact_type="property",
        data=_property(
            property_id_candidate="temporary",
            value_raw="386 ± 15",
            source_evidence=["| WA sample sintered at 1270 °C | 386 ± 15 |"],
        ),
        source_evidence=["| WA sample sintered at 1270 °C | 386 ± 15 |"],
        confidence=0.95,
    )
    prose_fact = PropertyFact(
        sample_id_raw="WA",
        fact_type="property",
        data=_property(
            property_id_candidate="temporary",
            value_raw="386 ± 15",
            test_condition_raw="sintered at 1270 °C",
            source_evidence=["WA tensile strength was 386 ± 15 MPa."],
        ),
        source_evidence=["WA tensile strength was 386 ± 15 MPa."],
        confidence=0.9,
    )

    result = materialize_candidate(
        [anchor], [table_fact, prose_fact], source_text=source
    )

    properties = [
        prop
        for item in result.document["items"]
        for prop in item["Extracted_Data"]["Properties"]
    ]
    assert len(properties) == 1
    assert properties[0]["value_raw"] == "386 ± 15"
    assert "5 mm/min" in properties[0]["test_condition_raw"]
    assert "1270" not in properties[0]["test_condition_raw"]
    issue = next(
        row
        for row in result.issues
        if row.code == "dense_tensile_table_cell_recovered"
    )
    assert issue.actual["before"] is not None


def test_v203_dense_completion_ambiguous_owner_is_audited_noop(monkeypatch):
    monkeypatch.setenv(
        "KNOWMAT2_ALPHA25_DENSE_TENSILE_TABLE_COMPLETION_V203", "1"
    )
    source = """
| Sample | UTS (MPa) |
| --- | --- |
| HT | 781 |
"""
    anchors = [
        InventoryAnchor(
            sample_id_raw=sample,
            material_name_raw="Ti-6Al-4V",
            state_raw="HT",
            role="Target",
            data_nature="Experimental",
            source_evidence=[sample],
            confidence=0.95,
        )
        for sample in ("Ti64-H", "Ti64-V")
    ]

    result = materialize_candidate(anchors, [], source_text=source)

    assert all(
        not item["Extracted_Data"]["Properties"] for item in result.document["items"]
    )
    issue = next(
        row for row in result.issues if row.code == "dense_tensile_table_cell_rejected"
    )
    assert issue.actual["decision"]["reason"] == "ambiguous_target_owner_alias"


def test_v203_dense_completion_switch_off_is_noop(monkeypatch):
    monkeypatch.setenv(
        "KNOWMAT2_ALPHA25_DENSE_TENSILE_TABLE_COMPLETION_V203", "0"
    )
    source = """
| Sample | UTS (MPa) |
| --- | --- |
| Ti64-H | 781 |
"""
    anchor = InventoryAnchor(
        sample_id_raw="Ti64-H",
        material_name_raw="Ti-6Al-4V",
        role="Target",
        data_nature="Experimental",
        source_evidence=["Ti64-H"],
        confidence=0.95,
    )

    result = materialize_candidate([anchor], [], source_text=source)

    assert result.document["items"] == []
    assert not any(
        row.code.startswith("dense_tensile_table_cell_") for row in result.issues
    )


def _coordinate_property(
    owner: str,
    *,
    decision_key: str,
    value: str = "781",
    evidence: str | None = None,
) -> PropertyFact:
    source = evidence or f"{owner} had an ultimate tensile strength of {value} MPa."
    payload = _property(
        property_id_candidate=decision_key,
        value_raw=value,
        source_evidence=[source],
    )
    return PropertyFact(
        sample_id_raw=owner,
        fact_type="property",
        data=payload,
        source_evidence=[source],
        confidence=0.95,
    )


def _target_anchor(owner: str) -> InventoryAnchor:
    return InventoryAnchor(
        sample_id_raw=owner,
        material_name_raw=owner,
        role="Target",
        data_nature="Experimental",
        source_evidence=[owner],
        confidence=0.95,
    )


def test_v203_same_coordinate_duplicate_merges_with_specific_audit(monkeypatch):
    monkeypatch.setenv(
        "KNOWMAT2_ALPHA25_PROPERTY_COORDINATE_QUARANTINE_V203", "1"
    )
    key = "dense-table-cell:one-cell"
    first = _coordinate_property("Ti64-H", decision_key=key)
    second = _coordinate_property("Ti64-H", decision_key=key)
    second.data["raw_note"] = "same literal cell"

    result = materialize_candidate([_target_anchor("Ti64-H")], [first, second])

    properties = result.document["items"][0]["Extracted_Data"]["Properties"]
    assert len(properties) == 1
    issue = next(
        row
        for row in result.issues
        if row.code == "property_same_coordinate_duplicate_merged"
    )
    assert issue.actual["decision_key"] == key
    assert issue.actual["survivor_after"]["data"]["raw_note"] == (
        "same literal cell"
    )


def test_v203_cross_owner_same_coordinate_quarantines_all(monkeypatch):
    monkeypatch.setenv(
        "KNOWMAT2_ALPHA25_PROPERTY_COORDINATE_QUARANTINE_V203", "1"
    )
    key = "dense-table-cell:one-cell"
    facts = [
        _coordinate_property("Ti64-H", decision_key=key),
        _coordinate_property("Ti64-V", decision_key=key),
    ]

    result = materialize_candidate(
        [_target_anchor("Ti64-H"), _target_anchor("Ti64-V")], facts
    )

    assert result.document["items"] == []
    issues = [
        row
        for row in result.issues
        if row.code == "property_cross_owner_projection_quarantined"
    ]
    assert len(issues) == 2
    assert all(row.actual["decision_key"] == key for row in issues)


def test_v203_numeric_scalar_from_qualitative_comparison_is_quarantined(
    monkeypatch,
):
    monkeypatch.setenv(
        "KNOWMAT2_ALPHA25_PROPERTY_COORDINATE_QUARANTINE_V203", "1"
    )
    monkeypatch.setenv("KNOWMAT2_ALPHA25_CLAIM_QUALITY", "off")
    fact = _coordinate_property(
        "Ti64-H",
        decision_key="temporary",
        value="900",
        evidence="Ti64-H had higher tensile strength than Ti64-V.",
    )

    result = materialize_candidate([_target_anchor("Ti64-H")], [fact])

    assert result.document["items"] == []
    issue = next(
        row
        for row in result.issues
        if row.code == "property_semantic_projection_quarantined"
    )
    assert issue.actual["removed"]["data"]["value_raw"] == "900"
    assert "higher tensile strength" in issue.evidence[0]


def test_v203_coordinate_quarantine_switch_off_preserves_qualitative_projection(
    monkeypatch,
):
    monkeypatch.setenv(
        "KNOWMAT2_ALPHA25_PROPERTY_COORDINATE_QUARANTINE_V203", "0"
    )
    monkeypatch.setenv("KNOWMAT2_ALPHA25_CLAIM_QUALITY", "off")
    fact = _coordinate_property(
        "Ti64-H",
        decision_key="temporary",
        value="900",
        evidence="Ti64-H had higher tensile strength than Ti64-V.",
    )

    result = materialize_candidate([_target_anchor("Ti64-H")], [fact])

    properties = result.document["items"][0]["Extracted_Data"]["Properties"]
    assert len(properties) == 1
    assert not any(
        row.code.startswith("property_semantic_projection_")
        for row in result.issues
    )
