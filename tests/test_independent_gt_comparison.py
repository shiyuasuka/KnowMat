from __future__ import annotations

from knowmat.evaluation.independent_gt_comparison import (
    compare_claim_sets,
    flatten_v11,
    issue_candidates,
    semantic_score,
    value_score,
)


def _expert(*, sample: str = "S1", condition: str = "25 °C") -> dict:
    return {
        "uid": "clm_0001", "source": "expert", "paper_key": "paper",
        "axis": "Properties",
        "owner": {"material_id": "m1", "material_name": "Ti-6Al-4V", "sample_id": sample, "state": "as-built", "region": None, "orientation": None, "role": "Target"},
        "semantic_key": "ultimate_tensile_strength", "name_raw": "UTS",
        "value": {"kind": "scalar", "raw": "1000", "number": 1000.0, "min": None, "max": None, "operator": None, "bound": None, "stddev": None, "text": None},
        "unit_raw": "MPa", "condition": condition, "origin": "author_experiment",
        "evidence": ["UTS was 1000 MPa"], "raw_path": "x", "raw": {},
    }


def test_property_alias_and_unit_value_match() -> None:
    left = {**_expert(), "semantic_key": "engineering_uts", "unit_raw": "GPa", "value": {**_expert()["value"], "number": 1.0, "raw": "1.0"}}
    right = _expert()
    assert semantic_score(left, right) == 1.0
    assert value_score(left, right) == 1.0


def test_strict_rejects_wrong_sample_while_loose_matches() -> None:
    system = [{**_expert(sample="S2"), "uid": "sys_1", "source": "final_v5"}]
    expert = [_expert(sample="S1")]
    report = compare_claim_sets(system, expert)
    assert report["modes"]["loose"]["micro"]["matched"] == 1
    assert report["modes"]["strict"]["micro"]["matched"] == 0
    issues = issue_candidates(system, expert, report)
    assert [row["code"] for row in issues] == ["wrong_owner"]


def test_strict_rejects_missing_condition() -> None:
    system = [{**_expert(condition=""), "uid": "sys_1", "source": "final_v5"}]
    report = compare_claim_sets(system, [_expert(condition="25 °C")])
    assert report["modes"]["loose"]["micro"]["matched"] == 1
    assert report["modes"]["strict"]["micro"]["matched"] == 0


def test_flatten_composition_is_atomic_and_skips_not_reported_parameter() -> None:
    document = {
        "items": [{
            "Item_ID": "item_1", "Sample_ID": "S1", "Role": "Target", "Data_Nature": "Experimental",
            "Extracted_Data": {
                "Composition": {
                    "Material_Identity": {"material_name_raw": "Alloy X"},
                    "Composition_Observations": [{"sample_id": "S1", "material_state": "powder", "basis": "wt%", "components": [
                        {"canonical_name": "Ni", "value_kind": "scalar", "value": 50, "value_raw": "50", "unit_raw": "wt%", "data_nature": "reported"},
                        {"canonical_name": "Cr", "value_kind": "scalar", "value": 20, "value_raw": "20", "unit_raw": "wt%", "data_nature": "reported"},
                    ], "source_evidence": "table row"}],
                },
                "Processing": {"Process_Route": {"stages": [{"process_code": "A2.AM.PBF_LB", "process_role": "primary_forming", "parameters": [
                    {"parameter_code": "power", "status": "not_reported", "value_kind": "unknown", "canonical_value": None, "canonical_unit": "W"}
                ]}]}},
                "Structure": {"Structure_Observations": [], "Characterization": []},
                "Properties": [],
            },
        }]
    }
    claims = flatten_v11(document, source="business_gt", paper_key="paper")
    composition = [row for row in claims if row["axis"] == "Composition"]
    processing = [row for row in claims if row["axis"] == "Processing"]
    assert len(composition) == 2
    assert len(processing) == 1  # stage identity only; absent power is not a fact
