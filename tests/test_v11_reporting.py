from io import StringIO

from knowmat.orchestrator import _build_qa_report
from knowmat.report_writer import write_comprehensive_report


def _v11_document():
    return {
        "Paper_Metadata": {"doi": "10.1000/example"},
        "Rule_Metadata": {"schema_version": "material_extraction_v11.3.0"},
        "items": [
            {
                "Role": "Target",
                "Extracted_Data": {
                    "Composition": {"Composition_Observations": [{"observation_id": "c1"}]},
                    "Processing": {
                        "Process_Route": {
                            "stages": [{"process_code": "A2.AM.PBF_LB"}]
                        }
                    },
                    "Structure": {"Structure_Observations": [{"observation_id": "s1"}]},
                    "Properties": [{"Canonical_Property": "ultimate_tensile_strength"}],
                },
            }
        ],
    }


def test_v11_qa_counts_nested_axes_and_lowercase_doi():
    report = _build_qa_report(
        "paper",
        _v11_document(),
        {
            "v11_validation": {
                "state": "passed_with_review",
                "fatal_count": 0,
                "review_count": 2,
            },
            "alpha25_coverage": {
                "complete": True,
                "task_count": 12,
                "rejected_facts": 0,
                "elapsed_seconds": 45.0,
            },
            "ocr_baseline_id": "baseline-test",
        },
    )

    assert report["properties_count"] == 1
    assert report["process_stage_count"] == 1
    assert report["composition_observation_count"] == 1
    assert report["structure_observation_count"] == 1
    assert report["missing_doi"] == 0
    assert report["red_line_triggers"] == []
    assert report["needs_review"] is True
    assert report["coverage_complete"] is True
    assert report["coverage_task_count"] == 12


def test_v11_analysis_report_uses_v11_counts():
    buffer = StringIO()
    write_comprehensive_report(
        buffer,
        {
            "final_data": _v11_document(),
            "v11_validation": {"state": "passed", "fatal_count": 0, "review_count": 0},
            "alpha25_coverage": {
                "complete": True,
                "task_count": 12,
                "accepted_facts": 20,
                "rejected_facts": 0,
                "elapsed_seconds": 45.0,
            },
        },
    )

    text = buffer.getvalue()
    assert "Final V11 Items: 1" in text
    assert "Final Process Stages: 1" in text
    assert "Total Properties in Final Result: 1" in text
    assert "V11 Validation: passed (fatal=0, review=0)" in text
    assert "Alpha25 Coverage: complete=True, tasks=12" in text
