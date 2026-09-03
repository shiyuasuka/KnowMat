from knowmat.alpha25.contracts import InventoryAnchor, ProcessingFact, PropertyFact
from knowmat.alpha25.verification_inventory import (
    build_recovery_requests,
    build_verification_bundles,
    build_verification_inventory,
)


def _property(owner: str, value: str, evidence: str) -> PropertyFact:
    return PropertyFact(
        sample_id_raw=owner,
        evidence_unit_id="unit-properties",
        data={
            "property_id_candidate": "temporary",
            "property_name_raw": "yield strength",
            "value_raw": value,
            "unit_raw": "MPa",
            "test_method_raw": "tensile",
            "test_standard_raw": "",
            "test_condition_raw": "room temperature",
            "test_specimen_raw": "",
            "raw_note": "",
            "data_source": "text",
            "source_evidence": [evidence],
            "confidence": 0.9,
        },
        source_evidence=[evidence],
        confidence=0.9,
    )


def _anchor(owner: str, evidence: str) -> InventoryAnchor:
    return InventoryAnchor(
        sample_id_raw=owner,
        role="Target",
        data_nature="Experimental",
        source_evidence=[evidence],
        confidence=0.9,
    )


def test_inventory_is_source_grounded_and_identity_is_permutation_stable():
    source = (
        "Sample A and Sample B were tensile tested at room temperature. "
        "Sample A had a yield strength of 900 MPa. "
        "Sample B had a yield strength of 800 MPa."
    )
    facts = [
        _property("Sample A", "900", "Sample A had a yield strength of 900 MPa."),
        _property("Sample B", "800", "Sample B had a yield strength of 800 MPa."),
    ]
    anchors = [_anchor("Sample A", "Sample A"), _anchor("Sample B", "Sample B")]
    left = build_verification_inventory(
        anchors, facts, source_text=source, task_ids=["task-a", "task-b"]
    )
    right = build_verification_inventory(
        list(reversed(anchors)),
        list(reversed(facts)),
        source_text=source,
        task_ids=["task-b", "task-a"],
    )
    assert [row.assertion_id for row in left.assertions] == [
        row.assertion_id for row in right.assertions
    ]
    assert [row.entity_id for row in left.entities] == [
        row.entity_id for row in right.entities
    ]
    assert not left.ungrounded_assertion_ids


def test_bundle_is_bounded_and_contains_cross_candidate_context():
    source = (
        "All tensile samples were tested at room temperature. "
        "Sample A had a yield strength of 900 MPa. "
        "Sample B had a yield strength of 800 MPa."
    )
    facts = [
        _property("Sample A", "900", "Sample A had a yield strength of 900 MPa."),
        _property("Sample B", "800", "Sample B had a yield strength of 800 MPa."),
    ]
    inventory = build_verification_inventory(
        [
            _anchor("Sample A", "Sample A"),
            _anchor("Sample B", "Sample B"),
        ],
        facts,
        source_text=source,
        task_ids=["task-a", "task-b"],
    )
    bundles = build_verification_bundles(
        inventory,
        source_text=source,
        max_assertions=2,
        max_source_chars=1000,
        context_radius=100,
    )
    assert len(bundles) == 1
    bundle = bundles[0]
    assert len(bundle.assertions) == 2
    assert bundle.source_char_count <= 1000
    assert any("All tensile samples" in row.text for row in bundle.evidence)
    assert {row.sample_id_raw for row in bundle.entities} == {"Sample A", "Sample B"}


def test_bundle_cap_keeps_local_context_before_remote_entity_anchors():
    remote = " ".join(f"Remote anchor {index}." for index in range(20))
    local = (
        "Sample A was solutioned at 1150°C for 2 h and this treatment "
        "resulted in recrystallized grains from 10 to 90 µm. "
        "Sample A also contained annealing twins."
    )
    source = f"{remote}\n{local}"
    anchors = [
        InventoryAnchor(
            sample_id_raw=f"Remote {index}",
            material_name_raw="Sample A",
            role="Reference",
            data_nature="Literature_Experimental",
            source_evidence=[f"Remote anchor {index}."],
            confidence=0.9,
        )
        for index in range(20)
    ]
    facts = [
        _property(
            "Sample A",
            "10 to 90",
            "resulted in recrystallized grains from 10 to 90 µm.",
        ),
        _property(
            "Sample A",
            "present",
            "Sample A also contained annealing twins.",
        ),
    ]
    inventory = build_verification_inventory(
        anchors, facts, source_text=source, task_ids=["task-a", "task-b"]
    )

    bundles = build_verification_bundles(
        inventory,
        source_text=source,
        max_assertions=2,
        max_source_chars=400,
        context_radius=90,
    )
    assert len(bundles) == 1
    bundle = bundles[0]

    assert bundle.source_char_count <= 400
    assert any(
        row.kind == "context" and "solutioned at 1150°C for 2 h" in row.text
        for row in bundle.evidence
    )


def test_unlocated_candidate_is_never_silently_bundled():
    fact = _property("Sample A", "900", "This quote is not in the source.")
    inventory = build_verification_inventory(
        [], [fact], source_text="Different source text.", task_ids=["task-a"]
    )
    assert len(inventory.ungrounded_assertion_ids) == 1
    assert build_verification_bundles(inventory, source_text="Different source text.") == []


def test_inventory_locates_latex_presentation_variants_without_inventing_text():
    source = "The UTS was 803 MPa at $650^{\\circ}\\mathrm{C}$."
    evidence = "The UTS was 803 MPa at  $ 650^\\circ $C"
    fact = _property("Sample A", "803", evidence)
    inventory = build_verification_inventory(
        [], [fact], source_text=source, task_ids=["task-a"]
    )
    assert not inventory.ungrounded_assertion_ids
    span = next(
        row
        for row in inventory.evidence
        if row.evidence_id == inventory.assertions[0].evidence_ids[0]
    )
    assert source[span.start_char : span.end_char] == span.text
    assert "803 MPa" in span.text


def test_task_source_scope_grounds_a_unique_table_projection():
    source = "| Sample | Yield strength | Elongation |\n| A | 900 MPa | 12 % |"
    projected = "Sample | Yield strength | A | 900 MPa"
    fact = _property("A", "900", projected)
    inventory = build_verification_inventory(
        [],
        [fact],
        source_text=source,
        task_ids=["table-task"],
        task_source_scopes={"table-task": source},
    )
    assert not inventory.ungrounded_assertion_ids
    assert inventory.assertions[0].evidence_ids


def test_inventory_locates_unicode_units_against_undelimited_latex_commands():
    source = (
        "The PBF-LB experiments used a preheating temperature of 170^\\circC. "
        "The average grain diameter was 57 \\mum."
    )
    facts = [
        _property(
            "PBF-LB",
            "170",
            "The PBF-LB experiments used a preheating temperature of 170°C",
        ),
        _property("PBF-LB", "57", "The average grain diameter was 57 µm"),
    ]

    inventory = build_verification_inventory(
        [], facts, source_text=source, task_ids=["task-a", "task-b"]
    )

    assert not inventory.ungrounded_assertion_ids
    assert all(row.evidence_ids for row in inventory.assertions)
    located = " ".join(row.text for row in inventory.evidence)
    assert "170^\\circC" in located
    assert "57 \\mum" in located


def test_inventory_compact_location_retains_trailing_percent_coordinate():
    source = r"Sample A had a ductility of 23% \pm 1%."
    copied = "Sample A had a ductility of 23% ± 1%."
    fact = _property("Sample A", "23% ± 1%", copied)

    inventory = build_verification_inventory(
        [_anchor("Sample A", "Sample A")],
        [fact],
        source_text=source,
        task_ids=["task-a"],
    )

    assert not inventory.ungrounded_assertion_ids
    span = next(
        row
        for row in inventory.evidence
        if row.evidence_id == inventory.assertions[0].evidence_ids[0]
    )
    assert span.text == r"Sample A had a ductility of 23% \pm 1%"
    assert source[span.start_char : span.end_char] == span.text


def test_inventory_links_nested_parameter_evidence_to_multifield_stage():
    source = (
        "PL used a 400 W laser. "
        "The layer thickness was 30 µm. "
        "The interlayer rotation was 67°."
    )
    top_level = "PL used a 400 W laser."
    fact = ProcessingFact(
        sample_id_raw="PL",
        evidence_unit_id="unit-processing",
        fact_type="process_stage",
        data={
            "candidate_stage_id": "temporary",
            "stage_index_candidate": 0,
            "process_name_raw": "LPBF pulsed laser mode",
            "process_code_candidate": None,
            "process_role_candidate": None,
            "parameters_raw": [
                {
                    "parameter_name_raw": "layer thickness",
                    "value_raw": "30",
                    "unit_raw": "µm",
                    "source_evidence": "The layer thickness was 30 µm.",
                },
                {
                    "parameter_name_raw": "interlayer rotation",
                    "value_raw": "67",
                    "unit_raw": "°",
                    "source_evidence": "The interlayer rotation was 67°.",
                },
            ],
            "source_evidence": [top_level],
            "confidence": 0.95,
        },
        source_evidence=[top_level],
        confidence=0.95,
    )

    inventory = build_verification_inventory(
        [], [fact], source_text=source, task_ids=["task-a"]
    )

    assertion = inventory.assertions[0]
    linked = {
        row.text for row in inventory.evidence if row.evidence_id in assertion.evidence_ids
    }
    assert linked == {
        top_level,
        "The layer thickness was 30 µm.",
        "The interlayer rotation was 67°.",
    }


def test_partial_table_projection_adds_only_the_minimal_ordered_window():
    literal = "Sample A was tensile tested."
    table = "| Sample | Batch | Yield strength |\n| A | X | 900 MPa |"
    source = literal + "\n" + table
    projected = "Sample | Yield strength | A | 900 MPa"
    payload = _property("A", "900", literal).model_dump()
    payload["source_evidence"] = [literal, projected]
    payload["data"]["source_evidence"] = [literal, projected]
    fact = PropertyFact.model_validate(payload)

    inventory = build_verification_inventory(
        [],
        [fact],
        source_text=source,
        task_ids=["mixed-task"],
        task_source_scopes={"mixed-task": source},
    )

    assertion = inventory.assertions[0]
    linked = {
        (row.kind, row.text)
        for row in inventory.evidence
        if row.evidence_id in assertion.evidence_ids
    }
    assert ("assertion", literal) in linked
    projection = next(text for kind, text in linked if kind == "context")
    assert projection == table
    assert len(projection) < len(source)


def test_assertion_cap_splits_deterministically():
    fragments = [f"Sample A had yield strength {index} MPa." for index in range(5)]
    source = " ".join(fragments)
    facts = [_property("Sample A", str(index), fragment) for index, fragment in enumerate(fragments)]
    inventory = build_verification_inventory(
        [_anchor("Sample A", "Sample A")],
        facts,
        source_text=source,
        task_ids=[f"task-{index}" for index in range(5)],
    )
    bundles = build_verification_bundles(
        inventory,
        source_text=source,
        max_assertions=2,
        max_source_chars=12000,
        context_radius=0,
    )
    assert [len(bundle.assertions) for bundle in bundles] == [2, 2, 1]


def test_recovery_requests_include_only_uncovered_literal_nonchart_assertions():
    covered = "Sample A had a yield strength of 900 MPa."
    missing = "Sample B had an elongation of 12 %."
    chart = "[Figure 2 VLM-digitized] yield strength estimated from the curve was 850 MPa."
    source = " ".join([covered, missing, chart])
    inventory = build_verification_inventory(
        [],
        [_property("Sample A", "900", covered)],
        source_text=source,
        task_ids=["task-a"],
    )
    requests = build_recovery_requests(inventory)
    assert len(requests) == 1
    texts = [row.text for row in requests[0].evidence]
    assert texts == [missing]
    assert covered not in texts
    assert all("VLM-digitized" not in row for row in texts)


def test_recovery_request_cap_is_deterministic():
    source = " ".join(
        f"Sample A had a tensile strength of {index + 100} MPa."
        for index in range(5)
    )
    inventory = build_verification_inventory([], [], source_text=source)
    requests = build_recovery_requests(inventory, max_assertions=2)
    assert [len(row.evidence) for row in requests] == [2, 2, 1]
