from knowmat.prompt_generator import (
    generate_axis_task_prompt,
    generate_system_prompt,
    generate_user_prompt,
)
from knowmat.extractors import V11CandidateStructure


def test_system_prompt_uses_alpha25_candidate_contract_and_dynamic_sections():
    prompt = generate_system_prompt("ROUTING_SENTINEL", "UPDATE_SENTINEL")

    assert "material-extractor 11.0.0-alpha.25" in prompt
    assert "material_extraction_v11.3.3" in prompt
    assert "Composition_Observations" in prompt
    assert "candidate_stages" in prompt
    assert "property_id_candidate" in prompt
    assert "Structure_Observations" in prompt
    assert "ROUTING_SENTINEL" in prompt
    assert "UPDATE_SENTINEL" in prompt
    assert "Processing.Equipment" not in prompt
    assert "Key_Params" not in prompt


def test_user_prompt_uses_compact_alpha25_workflow_and_runtime_values():
    prompt = generate_user_prompt(
        "PAPER_SENTINEL", "Metals", "Structural", "Experimental", "Titanium_Alloy"
    )

    assert "Task scope: all" in prompt
    assert "full alpha25 evidence-first candidate" in prompt
    assert "PAPER_SENTINEL" in prompt
    assert '"base_material": "Metals"' in prompt
    assert "{paper_text}" not in prompt


def test_axis_prompt_has_no_filename_or_gt_inputs():
    prompt = generate_axis_task_prompt(
        "laser power of 300 W",
        axis="processing",
        routing={"base_material": "Metals"},
        sample_anchors=[{"sample_id_raw": "A1"}],
        unit_id="unit-1",
    )

    assert "Task scope: processing" in prompt
    assert "laser power of 300 W" in prompt
    assert '"sample_id_raw": "A1"' in prompt
    assert "filename" not in prompt.casefold()
    assert "ground truth" not in prompt.casefold()


def test_axis_prompt_includes_provider_neutral_chunk_precision_protocol():
    prompt = generate_axis_task_prompt("A had a yield strength of 900 MPa", axis="properties")

    assert "The OCR EVIDENCE block is the complete factual scope for this chunk" in prompt
    assert "never use them to fill an owner" in prompt
    assert "Never expand one assertion into multiple owner-specific facts" in prompt
    assert '"status":"complete|none|partial"' in prompt
    assert "continuation_of" in prompt


def test_axis_prompts_compile_alpha25_nested_candidate_enums():
    composition = generate_axis_task_prompt("A contained 1 wt% Zr", axis="composition")
    processing = generate_axis_task_prompt("A was annealed", axis="processing")
    structure = generate_axis_task_prompt("A contained fine grains", axis="structure")

    assert "name_raw, value_kind, value_raw" in composition
    assert "omit canonical_name/value/canonical_unit" in composition
    assert "Never use old keys" in composition
    assert "runner assigns IDs/order" in processing
    assert "never linear/sequential" in processing
    assert "omit entity_id because the runner assigns it" in structure
    assert "Never use feature_name" in structure


def test_combined_prompt_requests_grounded_anchors_and_mixed_facts():
    prompt = generate_axis_task_prompt(
        "A was annealed and had a yield strength of 900 MPa", axis="combined"
    )

    assert "Task scope: combined" in prompt
    assert 'Return {"axis":"combined","anchors":[...],"facts":[...]}' in prompt
    assert "FIB/TEM/APT sub-samples" in prompt
    assert "bare numeric values" in prompt
    assert "Paper_Metadata" in prompt
    assert "Do not return a full candidate document" in prompt
    assert "uniquely attributable source sample/state" in prompt
    assert "Do not create an anchor or expand sample_id_raw" in prompt
    assert "Reuse the shortest literal source label" in prompt
    assert "long descriptive material/state phrase with a short code" in prompt
    assert "emit one anchor rather than splitting the two" in prompt
    assert "literature/reference-table row" in prompt
    assert "never Target facts of the current study" in prompt
    assert "sample_anchors in Task context are already accepted" in prompt
    assert "author-year name or citation number is provenance" in prompt
    assert "a process, test, or post-test mention alone is not an item" in prompt
    assert "shortest complete quote or quotes needed to prove that fact" in prompt
    assert "characterization recall" in prompt
    assert "voltage, current, step size, resolution" in prompt
    assert "result-only figure/caption mentions as structure observations" in prompt
    assert "explicitly states a performed acquisition/measurement" in prompt


def test_prompt_keeps_region_orientation_and_specimen_as_fact_context():
    system = generate_system_prompt()
    inventory = generate_axis_task_prompt(
        "Horizontal specimens were tested after deformation in the coarse region.",
        axis="inventory",
    )
    structure = generate_axis_task_prompt(
        "The coarse region of horizontal specimen A contained fine grains.",
        axis="structure",
    )
    system_flat = " ".join(system.split())

    assert "fact context, not separate item anchors" in system_flat
    assert "Create a state anchor only when the source names it" in system_flat
    assert "author-year citation or citation number is provenance" in system_flat
    assert "region/location, orientation, specimen geometry" in inventory
    assert "author-year citations" in inventory
    assert "not separate item identities" in structure


def test_processing_prompt_does_not_turn_stages_into_item_labels():
    prompt = generate_axis_task_prompt(
        "Sample A was annealed at 800 °C and then tested.", axis="processing"
    )

    assert "A process-stage mention alone never creates or expands an item label" in prompt
    assert "Keep route/stage/condition distinctions in process fact data" in prompt


def test_table_combined_prompt_limits_adjacent_context_to_disambiguation():
    prompt = generate_axis_task_prompt(
        "| Sample | UTS |\n|---|---:|\n| A | 900 |",
        axis="combined",
        evidence_kind="table",
    )

    assert "deterministic table projection" in prompt
    assert "Do not emit standalone facts found only in that adjacent context" in prompt
    assert "Never turn a metric, method, unit, or component heading" in prompt
    assert "exact contiguous substring" in prompt
    assert "complete literal body row" in prompt
    assert "deleting intervening columns" in prompt
    assert "fact condition/specimen/region/orientation/material_state" in prompt
    assert "anchor state_raw only when the header explicitly names" in prompt
    assert "a test or location header alone is not an item" in prompt


def test_v11_structure_status_accepts_evidence_level_model_variants():
    for raw_status, expected in (
        ("mentioned_without_extractable_observations", "partially_reported"),
        ("methods_reported_only", "partially_reported"),
        ("observed", "reported"),
    ):
        value = V11CandidateStructure.model_validate(
            {
                "Structure_Text": {"original": None, "simplified": None},
                "structure_status": raw_status,
                "Structure_Observations": [],
            }
        )
        assert value.structure_status == expected
