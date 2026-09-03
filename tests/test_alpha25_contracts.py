import pytest
from pydantic import ValidationError

from knowmat.alpha25.contracts import (
    AxisResponse,
    InventoryResponse,
    MultiAxisResponse,
    parse_task_response,
)


def test_inventory_requires_source_named_identity_and_evidence():
    response = InventoryResponse.model_validate(
        {
            "anchors": [
                {
                    "sample_id_raw": "A1",
                    "material_name_raw": "alloy A1",
                    "state_raw": "as-built",
                    "role": "Target",
                    "data_nature": "Experimental",
                    "source_evidence": "The as-built A1 alloy was tested.",
                    "confidence": 0.95,
                }
            ]
        }
    )

    assert response.anchors[0].source_evidence == ["The as-built A1 alloy was tested."]


def test_task_parser_rejects_wrong_axis_row_without_invalidating_siblings():
    response = parse_task_response(
        "composition",
        {
            "axis": "composition",
            "facts": [
                {
                    "axis": "processing",
                    "sample_id_raw": "A1",
                    "fact_type": "process_text",
                    "data": {
                        "original": "aged at 800 C",
                        "simplified": "aged at 800 C",
                    },
                    "source_evidence": ["aged at 800 C"],
                    "confidence": 0.9,
                },
                {
                    "axis": "composition",
                    "sample_id_raw": "A1",
                    "fact_type": "material_identity",
                    "data": {
                        "material_family": "alloy",
                        "material_name_raw": "A1",
                        "designation_raw": "A1",
                        "feedstock_form": None,
                    },
                    "source_evidence": ["A1 alloy"],
                    "confidence": 0.9,
                },
            ],
        },
    )

    assert len(response.facts) == 1
    assert response.facts[0].fact_type == "material_identity"


def test_mixed_task_parser_preserves_independently_typed_axis_facts():
    response = parse_task_response(
        "combined",
        {
            "facts": [
                {
                    "axis": "processing",
                    "sample_id_raw": "A1",
                    "fact_type": "process_text",
                    "data": {
                        "original": "A1 was annealed",
                        "simplified": "annealed",
                    },
                    "source_evidence": ["A1 was annealed"],
                    "confidence": 0.9,
                },
                {
                    "axis": "composition",
                    "sample_id_raw": "A1",
                    "fact_type": "material_identity",
                    "data": {
                        "material_family": "alloy",
                        "material_name_raw": "A1",
                        "designation_raw": "A1",
                        "feedstock_form": None,
                    },
                    "source_evidence": ["A1 alloy"],
                    "confidence": 0.9,
                },
            ]
        },
    )

    assert isinstance(response, MultiAxisResponse)
    assert [fact.axis for fact in response.facts] == ["processing", "composition"]


def test_chunk_protocol_metadata_is_accepted_but_excluded_from_public_schema():
    response = parse_task_response(
        "properties",
        {
            "axis": "properties",
            "coverage": {"status": "complete", "unresolved_spans": []},
            "facts": [
                {
                    "axis": "properties",
                    "fact_type": "property",
                    "sample_id_raw": "A1",
                    "chunk_id": "unit-1",
                    "source_span": "A1 had a yield strength of 900 MPa",
                    "incomplete": False,
                    "continuation_of": None,
                    "data": {
                        "property_id_candidate": "p1",
                        "property_name_raw": "yield strength",
                        "value_raw": "900",
                        "unit_raw": "MPa",
                        "test_method_raw": "",
                        "test_standard_raw": "",
                        "test_condition_raw": "",
                        "test_specimen_raw": "",
                        "raw_note": "",
                        "data_source": "text",
                    },
                    "source_evidence": ["A1 had a yield strength of 900 MPa"],
                    "confidence": 0.95,
                }
            ],
        },
    )

    fact = response.facts[0]
    assert fact.chunk_id == "unit-1"
    assert fact.source_span.startswith("A1 had")
    assert fact.incomplete is False
    public = response.model_dump(mode="json")
    assert "chunk_id" not in public["facts"][0]
    assert "source_span" not in public["facts"][0]
    assert "incomplete" not in public["facts"][0]
    assert "continuation_of" not in public["facts"][0]
    assert public["coverage"]["status"] == "complete"


def test_mixed_task_parser_preserves_inventory_anchors_with_facts():
    response = parse_task_response(
        "combined",
        {
            "axis": "combined",
            "anchors": [
                {
                    "sample_id_raw": "A1",
                    "material_name_raw": "A1 alloy",
                    "state_raw": "as-built",
                    "role": "Target",
                    "data_nature": "Experimental",
                    "source_evidence": ["as-built A1 alloy"],
                    "confidence": 0.95,
                }
            ],
            "facts": [],
        },
    )

    assert isinstance(response, MultiAxisResponse)
    assert [anchor.sample_id_raw for anchor in response.anchors] == ["A1"]
    assert response.facts == []


def test_mixed_task_repairs_unreported_property_metadata_without_retrying_leaf():
    response = parse_task_response(
        "combined",
        {
            "axis": "combined",
            "provider_summary": "extra envelope text",
            "anchors": [],
            "facts": [
                {
                    "axis": "properties",
                    "sample_id_raw": "A1",
                    "fact_type": "property",
                    "data": {
                        "property_name_raw": "UTS",
                        "value_raw": "900",
                        "origin": "experimental",
                    },
                    "source_evidence": ["UTS was 900 MPa"],
                    "confidence": 0.9,
                    "provider_note": "extra fact envelope text",
                }
            ],
        },
    )

    assert len(response.facts) == 1
    data = response.facts[0].data
    assert data["property_name_raw"] == "UTS"
    assert data["value_raw"] == "900"
    assert data["unit_raw"] == ""
    assert data["test_condition_raw"] == ""
    assert data["data_source"] == "unknown"


def test_mixed_task_repairs_nullable_composition_metadata_without_retrying_leaf():
    response = parse_task_response(
        "combined",
        {
            "axis": "combined",
            "anchors": [],
            "facts": [
                {
                    "axis": "composition",
                    "sample_id_raw": "A1",
                    "fact_type": "composition_observation",
                    "data": {
                        "observation_id": "c1",
                        "source_type": "measured",
                        "material_state": "as-built",
                        "sample_id": "A1",
                        "basis": "wt%",
                        "component_type": "elemental",
                        "components": [],
                        "raw_expression": "Ni balance",
                        "data_source": "text",
                    },
                    "source_evidence": ["A1 contained Ni balance"],
                    "confidence": 0.9,
                }
            ],
        },
    )

    assert len(response.facts) == 1
    assert response.facts[0].data["measurement"] is None
    assert response.facts[0].data["note"] is None


def test_mixed_task_assigns_only_deterministic_candidate_metadata_locally():
    response = parse_task_response(
        "combined",
        {
            "axis": "combined",
            "anchors": [],
            "facts": [
                {
                    "axis": "processing",
                    "sample_id_raw": "A1",
                    "fact_type": "process_stage",
                    "data": {"process_name_raw": "annealed", "parameters_raw": []},
                    "source_evidence": ["A1 was annealed"],
                    "confidence": 0.9,
                },
                {
                    "axis": "structure",
                    "sample_id_raw": "A1",
                    "fact_type": "structure_observation",
                    "data": {
                        "structure_kind": "grain_structure",
                        "source_type": "reported",
                        "entities": [{"name_raw": "equiaxed grains"}],
                        "features": [],
                    },
                    "source_evidence": ["A1 contained equiaxed grains"],
                    "confidence": 0.9,
                },
                {
                    "axis": "structure",
                    "sample_id_raw": "A1",
                    "fact_type": "characterization",
                    "data": {"method_raw": "EBSD", "method_class": "diffraction"},
                    "source_evidence": ["analyzed by EBSD"],
                    "confidence": 0.9,
                },
            ],
        },
    )

    stage, observation, characterization = [fact.data for fact in response.facts]
    assert stage["candidate_stage_id"] == "temporary"
    assert stage["stage_index_candidate"] == 0
    assert stage["process_code_candidate"] is None
    assert observation["observation_id"] == "temporary"
    assert observation["sample_id"] == "A1"
    assert observation["original"] == "A1 contained equiaxed grains"
    assert characterization["characterization_id"] == "temporary"


def test_invalid_optional_anchor_does_not_discard_grounded_sibling_facts():
    response = parse_task_response(
        "combined",
        {
            "axis": "combined",
            "anchors": [
                {
                    "sample_id_raw": "A1",
                    "role": "Target",
                    "data_nature": "Hybrid",
                    "source_evidence": ["A1 alloy"],
                    "confidence": 0.8,
                }
            ],
            "facts": [
                {
                    "axis": "properties",
                    "sample_id_raw": "A1",
                    "fact_type": "property",
                    "data": {"property_name_raw": "UTS", "value_raw": "900"},
                    "source_evidence": ["UTS was 900 MPa"],
                    "confidence": 0.9,
                }
            ],
        },
    )

    assert response.anchors == []
    assert len(response.facts) == 1
    assert response.facts[0].data["property_name_raw"] == "UTS"


def test_old_mixed_task_payload_without_anchors_remains_compatible():
    response = parse_task_response("combined", {"axis": "combined", "facts": []})

    assert isinstance(response, MultiAxisResponse)
    assert response.anchors == []


def test_single_anchor_is_wrapped_for_combined_task():
    response = parse_task_response(
        "combined",
        {
            "sample_id_raw": "A1",
            "material_name_raw": "A1 alloy",
            "state_raw": None,
            "role": "Target",
            "data_nature": "Experimental",
            "source_evidence": ["A1 alloy"],
            "confidence": 0.9,
        },
    )

    assert isinstance(response, MultiAxisResponse)
    assert [anchor.sample_id_raw for anchor in response.anchors] == ["A1"]
    assert response.facts == []


def test_single_mixed_axis_fact_is_wrapped_in_combined_response():
    response = parse_task_response(
        "combined",
        {
            "axis": "composition",
            "fact_type": "material_identity",
            "sample_id_raw": "GH4169",
            "data": {
                "material_family": "superalloy",
                "material_name_raw": "GH4169",
                "designation_raw": "GH4169",
                "feedstock_form": "powder",
            },
            "source_evidence": [
                "Nominal chemical composition of the tested GH4169 specimen powders"
            ],
            "confidence": 0.9,
        },
    )

    assert isinstance(response, MultiAxisResponse)
    assert response.axis == "combined"
    assert len(response.facts) == 1
    assert response.facts[0].axis == "composition"
    assert response.facts[0].sample_id_raw == "GH4169"


def test_anchor_shaped_material_identity_inside_facts_is_rewrapped_locally():
    response = parse_task_response(
        "combined",
        {
            "axis": "combined",
            "anchors": [],
            "facts": [
                {
                    "axis": "composition",
                    "fact_type": "material_identity",
                    "sample_id_raw": "Inconel 625",
                    "material_name_raw": "Inconel 625",
                    "state_raw": "sintered",
                    "role": "Target",
                    "data_nature": "Literature_Experimental",
                    "source_evidence": ["sintered Inconel 625"],
                    "confidence": 0.85,
                }
            ],
        },
    )

    assert len(response.facts) == 1
    fact = response.facts[0]
    assert fact.fact_type == "material_identity"
    assert fact.data["material_name_raw"] == "Inconel 625"
    assert fact.data["designation_raw"] == "Inconel 625"


def test_property_fact_requires_complete_alpha25_raw_candidate():
    with pytest.raises(ValidationError, match="missing alpha25 candidate fields"):
        parse_task_response(
            "properties",
            {
                "axis": "properties",
                "facts": [
                    {
                        "axis": "properties",
                        "sample_id_raw": "A1",
                        "fact_type": "property",
                        "data": {"property_name_raw": "UTS", "value_raw": "900"},
                        "source_evidence": ["UTS was 900 MPa"],
                        "confidence": 0.9,
                    }
                ],
            },
        )


def test_raw_property_fragment_at_response_root_is_wrapped():
    response = parse_task_response(
        "properties",
        {
            "property_id_candidate": "p1",
            "property_name_raw": "yield strength",
            "value_raw": "900",
            "unit_raw": "MPa",
            "test_method_raw": "tensile",
            "test_standard_raw": "",
            "test_condition_raw": "room temperature",
            "test_specimen_raw": "",
            "raw_note": "",
            "data_source": "text",
            "source_evidence": ["yield strength was 900 MPa"],
            "confidence": 0.9,
            "sample_id": "A1",
        },
    )

    assert len(response.facts) == 1
    assert response.facts[0].fact_type == "property"
    assert response.facts[0].sample_id_raw == "A1"


def test_single_axis_fact_is_wrapped_without_relaxing_fact_validation():
    response = parse_task_response(
        "composition",
        {
            "axis": "composition",
            "fact_type": "material_identity",
            "sample_id_raw": "A1",
            "evidence_unit_id": "unit-1",
            "data": {
                "material_family": "Al alloy",
                "material_name_raw": "A1",
                "designation_raw": "A1",
                "feedstock_form": None,
            },
            "source_evidence": ["A1 alloy"],
            "confidence": 0.9,
        },
    )

    assert response.axis == "composition"
    assert len(response.facts) == 1
    assert response.facts[0].sample_id_raw == "A1"


def test_single_inventory_anchor_is_wrapped():
    response = parse_task_response(
        "inventory",
        {
            "sample_id_raw": "A1",
            "material_name_raw": "A1 alloy",
            "state_raw": "as-built",
            "role": "Target",
            "data_nature": "Experimental",
            "source_evidence": ["as-built A1 alloy"],
            "confidence": 0.9,
        },
    )

    assert len(response.anchors) == 1
    assert response.anchors[0].sample_id_raw == "A1"


def test_mixed_task_parser_rejects_only_the_incomplete_fact_and_persists_issue():
    payload = {
        "axis": "combined",
        "anchors": [],
        "facts": [
            {
                "axis": "properties",
                "sample_id_raw": "A1",
                "fact_type": "property",
                "data": {
                    "property_name_raw": "yield strength",
                    "value_raw": "900",
                    "unit_raw": "MPa",
                    "data_source": "text",
                },
                "source_evidence": ["yield strength was 900 MPa"],
                "confidence": 0.9,
            },
            {
                "axis": "properties",
                "sample_id_raw": "A1",
                "fact_type": "property",
                "data": {
                    "property_name_raw": "stress-strain curve",
                    "data_source": "figure",
                },
                "source_evidence": ["stress-strain curves of A1"],
                "confidence": 0.5,
            },
        ],
    }

    response = parse_task_response("combined", payload)

    assert len(response.facts) == 1
    assert response.facts[0].data["value_raw"] == "900"
    assert len(response.contract_rejections) == 1
    rejection = response.contract_rejections[0]
    assert rejection.code == "invalid_fact_contract"
    assert rejection.fact_index == 1
    assert rejection.axis == "properties"
    assert rejection.source_evidence == ["stress-strain curves of A1"]
    assert "value_raw" in rejection.message

    cached = parse_task_response(
        "combined", response.model_dump(mode="json", exclude_none=True)
    )
    assert len(cached.facts) == 1
    assert cached.contract_rejections == response.contract_rejections


def test_inventory_enum_casing_is_normalized_but_unknown_values_fail():
    response = parse_task_response(
        "inventory",
        {
            "anchors": [
                {
                    "sample_id_raw": "A1",
                    "role": "target",
                    "data_nature": "experimental",
                    "source_evidence": ["A1 sample"],
                    "confidence": 0.9,
                }
            ]
        },
    )

    assert response.anchors[0].role == "Target"
    assert response.anchors[0].data_nature == "Experimental"

    with pytest.raises(ValidationError):
        parse_task_response(
            "inventory",
            {
                "anchors": [
                    {
                        "sample_id_raw": "A1",
                        "role": "unknown",
                        "data_nature": "experimental",
                        "source_evidence": ["A1 sample"],
                        "confidence": 0.9,
                    }
                ]
            },
        )


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("experiment", "Experimental"),
        ("simulated", "Computed"),
        ("ML", "Computed"),
        ("machine learning", "Computed"),
        ("literature", "Literature_Experimental"),
        ("literature simulated", "Literature_Computed"),
    ],
)
def test_inventory_data_nature_provider_synonyms_are_normalized(raw, expected):
    response = parse_task_response(
        "inventory",
        {
            "anchors": [
                {
                    "sample_id_raw": "A1",
                    "role": "target",
                    "data_nature": raw,
                    "source_evidence": ["A1 sample"],
                    "confidence": 0.9,
                }
            ]
        },
    )

    assert response.anchors[0].data_nature == expected


def test_outer_evidence_and_confidence_fill_required_duplicate_data_fields():
    response = parse_task_response(
        "properties",
        {
            "axis": "properties",
            "facts": [
                {
                    "axis": "properties",
                    "fact_type": "property",
                    "sample_id_raw": "A1",
                    "data": {
                        "property_id_candidate": "p1",
                        "property_name_raw": "yield strength",
                        "value_raw": "900",
                        "unit_raw": "MPa",
                        "test_method_raw": "tensile",
                        "test_standard_raw": "",
                        "test_condition_raw": "room temperature",
                        "test_specimen_raw": "",
                        "raw_note": "",
                        "data_source": "text",
                    },
                    "source_evidence": ["yield strength was 900 MPa"],
                    "confidence": 0.9,
                }
            ],
        },
    )

    assert response.facts[0].data["source_evidence"] == [
        "yield strength was 900 MPa"
    ]
    assert response.facts[0].data["confidence"] == 0.9


def test_inner_evidence_and_confidence_fill_required_outer_envelope():
    response = parse_task_response(
        "properties",
        {
            "axis": "properties",
            "facts": [
                {
                    "axis": "properties",
                    "fact_type": "property",
                    "sample_id_raw": "A1",
                    "data": {
                        "property_id_candidate": "p1",
                        "property_name_raw": "yield strength",
                        "value_raw": "900",
                        "unit_raw": "MPa",
                        "test_method_raw": "tensile",
                        "test_standard_raw": "",
                        "test_condition_raw": "room temperature",
                        "test_specimen_raw": "",
                        "raw_note": "",
                        "data_source": "text",
                        "source_evidence": ["yield strength was 900 MPa"],
                        "confidence": 0.9,
                    },
                }
            ],
        },
    )

    assert response.facts[0].source_evidence == ["yield strength was 900 MPa"]
    assert response.facts[0].confidence == 0.9


def test_missing_fact_axis_is_filled_from_task_scope():
    response = parse_task_response(
        "composition",
        {
            "facts": [
                {
                    "fact_type": "material_identity",
                    "sample_id_raw": "A1",
                    "data": {
                        "material_family": "Al alloy",
                        "material_name_raw": "A1",
                        "designation_raw": "A1",
                        "feedstock_form": None,
                    },
                    "source_evidence": ["A1 alloy"],
                    "confidence": 0.9,
                }
            ]
        },
    )

    assert response.facts[0].axis == "composition"


def test_unambiguous_structure_fragment_is_wrapped_as_fact():
    response = parse_task_response(
        "structure",
        {
            "axis": "structure",
            "facts": [
                {
                    "observation_id": "s1",
                    "structure_kind": "grain",
                    "material_state": "as-built",
                    "sample_id": "A1",
                    "source_type": "experimental",
                    "original": "A1 had fine grains",
                    "simplified": "fine grains",
                    "entities": [],
                    "features": [],
                    "source_evidence": ["A1 had fine grains"],
                    "confidence": 0.9,
                }
            ],
        },
    )

    assert response.facts[0].fact_type == "structure_observation"
    assert response.facts[0].sample_id_raw == "A1"
    assert response.facts[0].data["observation_id"] == "s1"


@pytest.mark.parametrize("missing_key", ["entities", "features"])
def test_structure_observation_restores_missing_empty_collection(missing_key):
    data = {
        "observation_id": "s1",
        "structure_kind": "grain",
        "material_state": "as-built",
        "sample_id": "A1",
        "source_type": "experimental",
        "original": "A1 had fine grains",
        "simplified": "fine grains",
        "entities": [],
        "features": [],
        "source_evidence": ["A1 had fine grains"],
    }
    data.pop(missing_key)

    response = parse_task_response(
        "structure",
        {
            "axis": "structure",
            "facts": [
                {
                    "axis": "structure",
                    "fact_type": "structure_observation",
                    "sample_id_raw": "A1",
                    "data": data,
                    "source_evidence": ["A1 had fine grains"],
                    "confidence": 0.9,
                }
            ],
        },
    )

    assert response.facts[0].data[missing_key] == []
