from copy import deepcopy

from knowmat.v11_reconcile import merge_canonical_v11_items, reconcile_v11_candidates


def _item(sample, properties=None):
    return {
        "Item_ID": "temporary",
        "Sample_ID": sample,
        "Role": "Target",
        "Data_Nature": "Experimental",
        "Extracted_Data": {
            "Composition": {"Composition_Observations": []},
            "Processing": {"Process_Route": {"candidate_stages": [], "candidate_edges": []}},
            "Structure": {"Structure_Observations": []},
            "Properties": deepcopy(properties or []),
        },
    }


def _candidate(*items):
    return {"Paper_Metadata": {}, "Paper_Routing": {}, "items": list(items)}


def _property(evidence):
    return {
        "property_id_candidate": "temporary",
        "property_name_raw": "yield strength",
        "value_raw": "900",
        "unit_raw": "MPa",
        "test_condition_raw": "room temperature",
        "source_evidence": [evidence],
        "confidence": 0.8,
    }


def test_exact_normalized_source_aliases_merge_without_material_lookup():
    merged = reconcile_v11_candidates(
        [
            _candidate(_item("Sample-A", [_property("first quote")])),
            _candidate(_item("sample A", [_property("second quote")])),
        ]
    )

    assert len(merged["items"]) == 1
    properties = merged["items"][0]["Extracted_Data"]["Properties"]
    assert len(properties) == 1
    assert properties[0]["source_evidence"] == ["first quote", "second quote"]


def test_distinct_source_labels_are_preserved_without_suffix_guessing():
    merged = merge_canonical_v11_items([_item("A-0"), _item("A-120"), _item("A-300")])

    assert [row["Sample_ID"] for row in merged] == ["A-0", "A-120", "A-300"]


def test_reconciliation_has_no_record_count_cap():
    properties = [
        {**_property(f"evidence {index}"), "value_raw": str(index)}
        for index in range(25)
    ]
    merged = reconcile_v11_candidates([_candidate(_item("A", properties))])

    assert len(merged["items"][0]["Extracted_Data"]["Properties"]) == 25
