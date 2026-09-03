"""
Application configuration for KnowMat 2.0.

This module defines a ``Settings`` class using pydantic's ``BaseSettings``
mechanism to manage environment‑configurable options such as the default
output directory, the model to use and the generation temperature.

Environment variables are prefixed with ``KNOWMAT2_``.  For example,
``KNOWMAT2_OUTPUT_DIR`` overrides the default output directory and
``KNOWMAT2_MODEL_NAME`` changes the base model.  See the attributes of
``Settings`` for supported options.
"""

import os
from pydantic_settings import BaseSettings
from pydantic import ConfigDict

from knowmat.env_loader import load_project_dotenv

# Load .env early so model defaults can read LLM_MODEL before settings instantiation.
load_project_dotenv(override=False)

DEFAULT_LLM_MODEL = os.getenv("LLM_MODEL", "gpt-5")


class Settings(BaseSettings):
    """Configuration options for KnowMat 2.0.

    Attributes
    ----------
    input_dir: str
        Default folder where raw ``.pdf``/``.txt`` files are stored. Defaults to
        ``"data/raw"`` relative to the current working directory.

    output_dir: str
        Where extracted results and artifacts will be written (LLM extraction
        JSON, reports, etc.).  Defaults to ``"data/output"`` so that raw/OCR
        (data/raw) and extraction output are kept separate.
    
    model_name: str
        The default model name for all agents.  Defaults to ``LLM_MODEL`` when
        set, otherwise ``"gpt-5"``.
    
    temperature: float
        Sampling temperature when generating with the language model.  A
        temperature of 0 yields deterministic outputs.  The default is 0.0.
        Note: GPT-5 models don't support custom temperature settings.
    
    subfield_model: str
        Model for subfield detection agent. Defaults to ``LLM_MODEL``.
    
    extraction_model: str
        Model for extraction agent. Defaults to ``LLM_MODEL``.
    
    evaluation_model: str
        Model for evaluation agent. Defaults to ``LLM_MODEL``.
    
    manager_model: str
        Model for validation agent (Stage 2: hallucination correction).
        Note: "manager_model" name kept for backward compatibility.
        Defaults to ``LLM_MODEL``.
    
    flagging_model: str
        Model for flagging/quality assessment agent. Defaults to ``LLM_MODEL``.

    trim_references_section: bool
        Whether to trim content after References/Bibliography/Citations during parsing.
        Defaults to ``False`` to preserve full text (including appendix/supplementary).

    figure_description_enabled: bool
        When ``True``, uses a multimodal LLM to generate a textual description of
        each detected figure image and inserts it into ``paper_text`` above the
        corresponding figure caption.  Requires ``LLM_MODEL`` to support vision.
        Defaults to ``True``.  Disable via ``KNOWMAT2_FIGURE_DESCRIPTION_ENABLED=0``.

    chart_digitization_enabled: bool
        When ``True``, line charts are first digitized from source-PDF vectors
        with deterministic code.  A VLM may add labels/classification but
        cannot generate or replace curve coordinates. Legacy
        ``img_in_chart_box_*`` bar crops keep their discrete VLM CSV route.
        Results are injected as ``> [Figure N VLM-digitized]`` blocks that the
        extraction stage may consume as ``image_digitized`` estimates.
        Defaults to ``True``.  Disable via ``KNOWMAT2_CHART_DIGITIZATION_ENABLED=0``.

    line_chart_split_enabled: bool
        When ``True``, source-PDF vector curves are traced and calibrated by
        code. Raster-only legacy crops retain deterministic color splitting;
        VLM point generation is disabled for both paths.
        Defaults to ``True``.  Disable via ``KNOWMAT2_LINE_CHART_SPLIT_ENABLED=0``.

    line_chart_max_series: int
        Hard cap on the number of color series extracted from one raster chart.
        Vector sidecars retain every source-supported series. Defaults to ``6``.
        Override via ``KNOWMAT2_LINE_CHART_MAX_SERIES``.

    line_chart_classification_min_confidence: float
        Minimum VLM confidence required before a vector-inconclusive chart crop
        may enter the deterministic raster line splitter. Defaults to ``0.7``.

    chart_context_max_chars_per_figure: int
        Hard character budget for one line-chart block injected into Markdown.
        Full point data stays in a sidecar CSV. Defaults to ``2400``.

    chart_context_max_chars_per_paper: int
        Shared character budget for all line-chart blocks injected into one
        paper. Later blocks degrade to metadata/file references. Defaults to
        ``12000``.

    chart_context_max_series: int
        Maximum number of per-series key-point summaries exposed to the LLM for
        one chart. The sidecar CSV remains complete. Defaults to ``12``.

    alpha25_package_root: str
        Workspace-relative or absolute path to the checked-in material-extractor
        alpha25 package root. The package is validated before prompt generation.
    """

    # IO defaults (can be overridden by env or CLI)
    input_dir: str = "data/raw"
    output_dir: str = "data/output"
    model_name: str = DEFAULT_LLM_MODEL
    temperature: float = 0.0  # Note: ignored for GPT-5 models
    
    # Per-agent model configuration
    subfield_model: str = DEFAULT_LLM_MODEL
    extraction_model: str = DEFAULT_LLM_MODEL
    evaluation_model: str = DEFAULT_LLM_MODEL
    manager_model: str = DEFAULT_LLM_MODEL
    flagging_model: str = DEFAULT_LLM_MODEL
    trim_references_section: bool = False
    figure_description_enabled: bool = True
    chart_digitization_enabled: bool = True
    line_chart_split_enabled: bool = True
    line_chart_max_series: int = 6
    line_chart_classification_min_confidence: float = 0.7
    chart_context_max_chars_per_figure: int = 2400
    chart_context_max_chars_per_paper: int = 12000
    chart_context_max_series: int = 12
    alpha25_package_root: str = (
        "material-extractor-alpha25-20260804/material-extractor"
    )

    model_config = ConfigDict(env_prefix="KNOWMAT2_")


# Singleton instance to be imported throughout the package
settings = Settings()
