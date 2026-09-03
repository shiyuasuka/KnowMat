from knowmat.extractors import PaperRouting
from knowmat.nodes.subfield_detection import detect_sub_field


def test_frozen_ocr_routing_is_cached_per_paper(monkeypatch, tmp_path):
    calls = []

    def fake_invoke(prompt):
        calls.append(prompt)
        return {
            "responses": [
                PaperRouting(
                    base_material="Metals",
                    application="Structural",
                    research_paradigm="Experimental",
                    domain_overlays=["Additive_Manufacturing"],
                    patch_tags=[],
                )
            ]
        }

    monkeypatch.setattr(
        "knowmat.nodes.subfield_detection.routing_extractor.invoke", fake_invoke
    )
    state = {
        "paper_text": "Sample A was fabricated by LPBF.",
        "output_dir": str(tmp_path / "paper-a"),
        "ocr_baseline_id": "baseline-1",
        "ocr_manifest_path": str(tmp_path / "manifest.json"),
    }

    first = detect_sub_field(state)
    second = detect_sub_field(state)

    assert len(calls) == 1
    assert first["paper_routing"] == second["paper_routing"]
    assert (tmp_path / "paper-a" / "v11" / "01_routing.json").is_file()

    detect_sub_field({**state, "paper_text": "The frozen source changed."})
    assert len(calls) == 2


def test_non_frozen_routing_is_not_persisted(monkeypatch, tmp_path):
    calls = []

    def fake_invoke(prompt):
        calls.append(prompt)
        return {
            "responses": [
                PaperRouting(
                    base_material="Metals",
                    application="Structural",
                    research_paradigm="Experimental",
                )
            ]
        }

    monkeypatch.setattr(
        "knowmat.nodes.subfield_detection.routing_extractor.invoke", fake_invoke
    )
    state = {
        "paper_text": "Sample A was tested.",
        "output_dir": str(tmp_path / "paper-a"),
    }

    detect_sub_field(state)
    detect_sub_field(state)

    assert len(calls) == 2
    assert not (tmp_path / "paper-a" / "v11" / "01_routing.json").exists()
