"""
Top-level assembly of the KnowMat 2.0 LangGraph workflow.

This module wires together the individual processing nodes and drives the
end-to-end extraction pipeline for a single PDF document.  Domain-specific
conversion logic lives in :mod:`knowmat.schema_converter` and report
generation in :mod:`knowmat.report_writer`.
"""

import json
import os
import re
import uuid
from pathlib import Path
from typing import Optional

from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.memory import MemorySaver

from knowmat.states import KnowMatState
from knowmat.report_writer import write_comprehensive_report
from knowmat.nodes.paddleocrvl_parse_pdf import parse_pdf_with_paddleocrvl
from knowmat.nodes.subfield_detection import detect_sub_field
from knowmat.nodes.extraction import extract_data
from knowmat.nodes.evaluation import evaluate_data
from knowmat.nodes.aggregator import aggregate_runs
from knowmat.nodes.validator import validate_and_correct
from knowmat.nodes.flagging import assess_final_quality
from knowmat.nodes.standardize import standardize_properties
from knowmat.nodes.schema_convert import convert_to_target_schema
from knowmat.nodes.v11_normalize import normalize_v11
from knowmat.app_config import Settings, settings
from knowmat.config import _env_path
from knowmat.ocr_manifest import load_ocr_manifest, verify_ocr_record


def sanitize_filename(name: str, max_length: int = 200) -> str:
    """Sanitize a filename to prevent path traversal and filesystem issues.
    
    Removes potentially dangerous characters and limits length to prevent
    issues with very long filenames.
    
    Parameters
    ----------
    name : str
        The original filename to sanitize.
    max_length : int
        Maximum allowed length for the filename. Default 200 characters.
        
    Returns
    -------
    str
        A sanitized filename safe for filesystem use.
    """
    if not name:
        return "unnamed"
    
    # Remove path separators and potentially dangerous characters
    # Keep alphanumeric, underscores, hyphens, dots, and common Unicode
    safe = re.sub(r'[<>:"/\\|?*\x00-\x1f]', '_', name)
    
    # Remove leading/trailing dots and spaces (issues on Windows)
    safe = safe.strip('. ')
    
    # Collapse multiple underscores/spaces
    safe = re.sub(r'[_\s]+', '_', safe)
    
    # Ensure we have something left
    if not safe:
        safe = "unnamed"
    
    # Limit length
    if len(safe) > max_length:
        # Try to cut at a reasonable point (underscore or space)
        cut_point = safe[:max_length].rfind('_')
        if cut_point > max_length // 2:
            safe = safe[:cut_point]
        else:
            safe = safe[:max_length]
    
    return safe


def verify_selected_ocr_input(
    input_path: str,
    *,
    ocr_baseline_id: Optional[str],
    ocr_manifest_path: Optional[str],
) -> None:
    """Verify the frozen source artifact before any graph node or LLM call."""

    manifest_path = str(ocr_manifest_path or "").strip()
    if not manifest_path:
        return
    manifest = load_ocr_manifest(Path(manifest_path))
    expected_baseline = str(ocr_baseline_id or "").strip()
    if expected_baseline and manifest.get("baseline_id") != expected_baseline:
        raise RuntimeError("Selected OCR baseline identity changed before extraction")
    verify_ocr_record(manifest, Path(input_path))


def evaluation_condition(state: KnowMatState) -> str:
    """Decide whether to rerun extraction or proceed to aggregation.

    Called by the graph when the evaluation node completes.  If
    ``state['needs_rerun']`` is true and ``state['run_count']`` is less
    than ``state['max_runs']`` the function returns the name of the
    extraction node to trigger another cycle.  Otherwise it returns
    ``aggregate_runs`` to begin the two-stage manager process.
    """
    run_count = state.get("run_count", 0)
    max_runs = state.get("max_runs", 3)
    needs_rerun = state.get("needs_rerun", False)
    if needs_rerun and run_count < max_runs:
        return "extract_data"
    return "aggregate_runs"


def build_graph(full_pipeline: bool = True) -> StateGraph:
    """Construct the LangGraph for KnowMat 2.0 with two-stage manager.

    When *full_pipeline* is True the graph includes subfield detection,
    iterative evaluation, aggregation, validation, flagging, optional
    property standardization, and schema conversion -- all as tracked
    graph nodes with checkpoint support.
    """
    builder = StateGraph(KnowMatState)

    builder.add_node("parse_pdf", parse_pdf_with_paddleocrvl)
    builder.add_node("detect_sub_field", detect_sub_field)
    builder.add_node("extract_data", extract_data)

    builder.add_edge(START, "parse_pdf")
    builder.add_edge("parse_pdf", "detect_sub_field")
    builder.add_edge("detect_sub_field", "extract_data")

    if not full_pipeline:
        builder.add_node("normalize_v11", normalize_v11)
        builder.add_node("convert_schema", convert_to_target_schema)
        builder.add_edge("extract_data", "normalize_v11")
        builder.add_edge("normalize_v11", "convert_schema")
        builder.add_edge("convert_schema", END)
    else:
        builder.add_node("evaluate_data", evaluate_data)
        builder.add_node("aggregate_runs", aggregate_runs)
        builder.add_node("validate_and_correct", validate_and_correct)
        builder.add_node("assess_final_quality", assess_final_quality)
        builder.add_node("standardize_properties", standardize_properties)
        builder.add_node("normalize_v11", normalize_v11)
        builder.add_node("convert_schema", convert_to_target_schema)

        builder.add_edge("extract_data", "evaluate_data")
        builder.add_conditional_edges(
            "evaluate_data", evaluation_condition, ["extract_data", "aggregate_runs"]
        )
        builder.add_edge("aggregate_runs", "validate_and_correct")
        builder.add_edge("validate_and_correct", "normalize_v11")
        builder.add_edge("normalize_v11", "assess_final_quality")
        builder.add_edge("assess_final_quality", "standardize_properties")
        builder.add_edge("standardize_properties", "convert_schema")
        builder.add_edge("convert_schema", END)

    return builder.compile(checkpointer=MemorySaver())


def run(
    pdf_path: str,
    output_dir: Optional[str] = None,
    model_name: Optional[str] = None,
    max_runs: int = 3,
    subfield_model: Optional[str] = None,
    extraction_model: Optional[str] = None,
    evaluation_model: Optional[str] = None,
    manager_model: Optional[str] = None,
    flagging_model: Optional[str] = None,
    full_pipeline: bool = False,
    enable_property_standardization: bool = False,
    ocr_baseline_id: Optional[str] = None,
    ocr_manifest_path: Optional[str] = None,
) -> dict:
    """Run the full KnowMat 2.0 pipeline on a given input file and write results.

    Parameters
    ----------
    pdf_path : str
        Path to the materials science paper in ``.pdf`` or ``.txt`` format.
    output_dir : Optional[str]
        Directory where results will be saved.
    model_name : Optional[str]
        Override the base model (e.g., "gpt-4", "gpt-5-mini").
    max_runs : int
        Maximum number of extraction/evaluation cycles.
    subfield_model, extraction_model, evaluation_model, manager_model, flagging_model
        Per-agent model overrides.
    full_pipeline : bool
        If True, run subfield/evaluation/aggregation/validation stages.
    enable_property_standardization : bool
        If True, run optional property post-processing (extra LLM calls).

    Returns
    -------
    dict
        Results dictionary containing final_data, flag, output_dir, etc.
    """

    if _env_path:
        print(f"Loaded environment variables from: {_env_path}")

    # Baseline membership must be checked against the immutable source Markdown,
    # not the parser's output copy.  Do this before routing so a bad selection
    # cannot consume even one LLM request.
    verify_selected_ocr_input(
        pdf_path,
        ocr_baseline_id=ocr_baseline_id,
        ocr_manifest_path=ocr_manifest_path,
    )

    # Build an isolated Settings instance for this run to avoid mutating
    # the module-level singleton in concurrent executions.
    overrides = {}
    if output_dir:
        overrides["output_dir"] = output_dir
    if model_name:
        overrides["model_name"] = model_name
    if subfield_model:
        overrides["subfield_model"] = subfield_model
    if extraction_model:
        overrides["extraction_model"] = extraction_model
    if evaluation_model:
        overrides["evaluation_model"] = evaluation_model
    if manager_model:
        overrides["manager_model"] = manager_model
    if flagging_model:
        overrides["flagging_model"] = flagging_model

    if overrides:
        effective_settings = Settings(**{**settings.model_dump(), **overrides})
    else:
        effective_settings = settings

    # Default all per-agent models to model_name when not overridden.
    if not subfield_model and not overrides.get("subfield_model"):
        effective_settings.subfield_model = effective_settings.model_name
    if not extraction_model and not overrides.get("extraction_model"):
        effective_settings.extraction_model = effective_settings.model_name
    if not evaluation_model and not overrides.get("evaluation_model"):
        effective_settings.evaluation_model = effective_settings.model_name
    if not manager_model and not overrides.get("manager_model"):
        effective_settings.manager_model = effective_settings.model_name
    if not flagging_model and not overrides.get("flagging_model"):
        effective_settings.flagging_model = effective_settings.model_name

    print("\nModel Configuration:")
    print(f"   Subfield Detection: {effective_settings.subfield_model}")
    print(f"   Extraction:         {effective_settings.extraction_model}")
    print(f"   Evaluation:         {effective_settings.evaluation_model}")
    print("   Aggregation:        rule-based (no LLM)")
    print(f"   Validation:         {effective_settings.manager_model}")
    print(f"   Flagging:           {effective_settings.flagging_model}")

    # Sanitize the base name to prevent path traversal issues
    raw_base_name = os.path.splitext(os.path.basename(pdf_path))[0]
    base_name = sanitize_filename(raw_base_name)
    if base_name != raw_base_name:
        print(f"   Note: Filename sanitized: '{raw_base_name}' -> '{base_name}'")
    
    paper_output_dir = os.path.join(effective_settings.output_dir, base_name)
    os.makedirs(paper_output_dir, exist_ok=True)

    print(f"\nOutput directory: {paper_output_dir}\n")

    state: KnowMatState = {
        "pdf_path": pdf_path,
        "output_dir": paper_output_dir,
        "run_count": 0,
        "run_results": [],
        "max_runs": max_runs,
        "enable_property_standardization": enable_property_standardization,
        "ocr_baseline_id": ocr_baseline_id,
        "ocr_manifest_path": ocr_manifest_path,
        "extraction_model": effective_settings.extraction_model,
    }

    thread_id = f"knowmat2_{base_name}_{uuid.uuid4().hex[:8]}"
    thread_config = {"configurable": {"thread_id": thread_id}}

    graph = build_graph(full_pipeline=full_pipeline)
    for _ in graph.stream(state, thread_config, stream_mode="values"):
        # Stream execution - each step updates state automatically
        continue

    final_state = graph.get_state(thread_config).values
    final_data = final_state.get("final_data", {})
    if not final_data:
        final_data = final_state.get("latest_extracted_data", {})
    flag = final_state.get("flag", False) if full_pipeline else False

    # --- Write outputs to disk ---
    output_path = os.path.join(paper_output_dir, f"{base_name}_extraction.json")
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(final_data, f, ensure_ascii=False, indent=2)
    print(f"Saved extraction to {output_path}")

    if isinstance(final_data, dict) and isinstance(final_data.get("items"), list):
        if final_state.get("v11_promotable", False):
            final_path = os.path.join(paper_output_dir, "final.json")
            with open(final_path, "w", encoding="utf-8") as f:
                json.dump(final_data, f, ensure_ascii=False, indent=2)
            print(f"Saved v11 final to {final_path}")
        else:
            print("V11 validation has fatal issues; final.json was not promoted.")

    report_path = os.path.join(paper_output_dir, f"{base_name}_analysis_report.txt")
    with open(report_path, "w", encoding="utf-8") as f:
        write_comprehensive_report(f, final_state)
    print(f"Saved analysis report to {report_path}")

    runs_path = os.path.join(paper_output_dir, f"{base_name}_runs.json")
    with open(runs_path, "w", encoding="utf-8") as f:
        json.dump(final_state.get("run_results", []), f, ensure_ascii=False, indent=2)

    # --- Generate QA Report (pure computation, no LLM) ---
    qa_report = _build_qa_report(base_name, final_data, final_state)

    qa_path = os.path.join(paper_output_dir, f"{base_name}_qa_report.json")
    with open(qa_path, "w", encoding="utf-8") as f:
        json.dump(qa_report, f, ensure_ascii=False, indent=2)
    print(f"Saved QA report to {qa_path}")

    if qa_report.get("red_line_triggers"):
        triggers = qa_report["red_line_triggers"]
        print(f"\n[RED LINE] QA check failed: {', '.join(triggers)}")
        print(f"           Human review REQUIRED for {base_name}")

    return {
        "final_data": final_data,
        "flag": flag,
        "output_dir": paper_output_dir,
        "final_confidence_score": final_state.get("final_confidence_score"),
        "aggregation_rationale": final_state.get("aggregation_rationale"),
        "human_review_guide": final_state.get("human_review_guide"),
    }


def _build_qa_report(base_name: str, final_data: dict, final_state: dict) -> dict:
    """Build the QA report dict from final extraction results."""
    items = final_data.get("items") or final_data.get("Materials", [])
    is_v11 = bool(items) and all(
        isinstance(item, dict) and isinstance(item.get("Extracted_Data"), dict)
        for item in items
    )
    if is_v11:
        extracted_rows = [item["Extracted_Data"] for item in items]
        all_tests = [
            prop
            for extracted in extracted_rows
            for prop in (extracted.get("Properties") or [])
        ]
        routes = [
            ((extracted.get("Processing") or {}).get("Process_Route") or {})
            for extracted in extracted_rows
        ]
        stages = [stage for route in routes for stage in (route.get("stages") or [])]
        unknown_process_count = sum(
            1
            for route in routes
            if not any(stage.get("process_code") for stage in (route.get("stages") or []))
        )
        structure_observations = [
            observation
            for extracted in extracted_rows
            for observation in (
                (extracted.get("Structure") or {}).get("Structure_Observations") or []
            )
        ]
        composition_observations = [
            observation
            for extracted in extracted_rows
            for observation in (
                (extracted.get("Composition") or {}).get("Composition_Observations") or []
            )
        ]
        phase_filled_count = sum(
            bool((extracted.get("Structure") or {}).get("Structure_Observations"))
            for extracted in extracted_rows
        )
        target_count = sum(item.get("Role") == "Target" for item in items)
    else:
        all_tests = [t for item in items for t in (item.get("Properties_Info", []) or [])]
        stages = []
        structure_observations = []
        composition_observations = []
        unknown_process_count = sum(
            1
            for item in items
            if (item.get("Process_Info", {}).get("Process_Category") or "Unknown")
            == "Unknown"
        )
        phase_filled_count = sum(
            1
            for item in items
            if (item.get("Microstructure_Info", {}) or {}).get("Main_Phase")
        )
        target_count = sum(
            1
            for item in items
            if (item.get("Composition_Info", {}) or {}).get("Role", "Target") == "Target"
        )
    phase_filled_rate = phase_filled_count / len(items) if items else 0
    paper_metadata = final_data.get("Paper_Metadata") or {}
    missing_doi = 1 if not (paper_metadata.get("doi") or paper_metadata.get("DOI")) else 0
    validation = final_state.get("v11_validation") or {}
    coverage = final_state.get("alpha25_coverage") or {}

    red_line_triggers = []
    if len(items) == 0:
        red_line_triggers.append("NO_TARGET_MATERIALS")
    if len(all_tests) == 0:
        red_line_triggers.append("NO_PROPERTIES")
    if items:
        unknown_ratio = unknown_process_count / len(items)
        if unknown_ratio > 0.5:
            red_line_triggers.append("HIGH_UNKNOWN_PROCESS_RATIO")

    return {
        "paper_name": base_name,
        "pipeline_version": "knowmat-2.0.1",
        "schema_version": (final_data.get("Rule_Metadata") or {}).get("schema_version"),
        "materials_target_count": target_count,
        "samples_count": len(items),
        "properties_count": len(all_tests),
        "process_stage_count": len(stages),
        "composition_observation_count": len(composition_observations),
        "structure_observation_count": len(structure_observations),
        "unknown_process_count": unknown_process_count,
        "phase_filled_rate": round(phase_filled_rate, 3),
        "missing_doi": missing_doi,
        "validation_state": validation.get("state"),
        "fatal_count": validation.get("fatal_count", 0),
        "review_count": validation.get("review_count", 0),
        "coverage_complete": coverage.get("complete"),
        "coverage_task_strategy": coverage.get("task_strategy"),
        "coverage_thinking_mode": coverage.get("thinking_mode"),
        "coverage_initial_task_count": coverage.get("initial_task_count", 0),
        "coverage_retry_task_count": coverage.get("retry_task_count", 0),
        "coverage_task_count": coverage.get("task_count", 0),
        "coverage_max_evidence_chars": coverage.get("max_evidence_chars", 0),
        "coverage_rejected_facts": coverage.get("rejected_facts", 0),
        "llm_extraction_elapsed_seconds": coverage.get("elapsed_seconds"),
        "llm_provider_call_p95_seconds": coverage.get(
            "provider_call_elapsed_p95"
        ),
        "llm_provider_queue_sum_seconds": coverage.get(
            "provider_queue_elapsed_sum"
        ),
        "ocr_baseline_id": final_state.get("ocr_baseline_id"),
        "needs_review": bool(red_line_triggers)
        or validation.get("state") in {"failed", "passed_with_review"},
        "red_line_triggers": red_line_triggers,
        "final_confidence_score": final_state.get("final_confidence_score"),
    }
