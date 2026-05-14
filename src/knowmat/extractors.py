"""
TrustCall extractor definitions for KnowMat 2.0.

This module defines all of the Pydantic models used by TrustCall tools and
provides lazily bound extractors so that each invocation constructs a fresh
ChatOpenAI instance with the current settings.  The pattern follows that
used in the MI‑Agent project.

The three extractors defined here correspond to the three agents in the
KnowMat 2.0 pipeline:

* ``subfield_extractor`` returns a ``SubFieldDetection`` model with two
  fields: ``sub_field`` and ``updated_prompt``.
* ``extraction_extractor`` returns a ``CompositionList`` model consisting
  of compositions and their properties.  The schema mirrors the original
  Pydantic classes from KnowMat v1.
* ``evaluation_extractor`` returns an ``EvaluationFeedback`` model used
  by the evaluation agent to determine whether another extraction pass
  should be performed and to capture suggestions for improving the prompt.

The lazy binding of extractors ensures that long‑running workloads do not
hold onto stale language model instances and makes it straightforward to
adjust the model name or temperature via environment variables.
"""

import logging
import json
import os
import re
import time
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field, model_validator
from langchain_openai import ChatOpenAI
from trustcall import create_extractor

from knowmat.app_config import settings

logger = logging.getLogger(__name__)


_AQF_TECHNIQUE_KEYS = {
    "apt",
    "clsm",
    "ebsd",
    "edx",
    "eis",
    "microct",
    "micro_ct",
    "micro-ct",
    "sem",
    "stem",
    "tem",
    "xps",
    "xrd",
}


def _llm_connection_kwargs() -> Dict[str, str]:
    """Build optional connection kwargs for OpenAI-compatible endpoints."""
    kwargs: Dict[str, str] = {}
    api_key = os.getenv("LLM_API_KEY") or os.getenv("OPENAI_API_KEY")
    base_url = os.getenv("LLM_BASE_URL") or os.getenv("OPENAI_BASE_URL")
    if api_key:
        kwargs["api_key"] = api_key
    if base_url:
        kwargs["base_url"] = base_url
    return kwargs


def get_llm(agent_type: str = "default") -> ChatOpenAI:
    """Instantiate a ChatOpenAI using the current settings for a specific agent.

    A new instance is created on each call to avoid stale connections
    persisting across multiple extractions.
    
    Parameters
    ----------
    agent_type: str
        The type of agent requesting the LLM. One of: "subfield", "extraction",
        "evaluation", "manager", "flagging", or "default".
    
    Returns
    -------
    ChatOpenAI
        Configured ChatOpenAI instance for the specified agent.
    """
    # Map agent types to their configured models
    model_map = {
        "subfield": settings.subfield_model,
        "extraction": settings.extraction_model,
        "evaluation": settings.evaluation_model,
        "manager": settings.manager_model,
        "flagging": settings.flagging_model,
        "default": settings.model_name
    }
    
    model = model_map.get(agent_type, settings.model_name)
    
    base_kwargs = {
        "model": model,
        "request_timeout": 1200,  # 20 minute timeout per API call (not per pipeline)
        "max_retries": 3,  # Retry failed requests up to 3 times
        **_llm_connection_kwargs(),
    }

    # GPT-5 models don't support temperature parameter
    if any(gpt5_variant in model for gpt5_variant in ["gpt-5", "gpt-5-mini", "gpt-5-nano"]):
        return ChatOpenAI(**base_kwargs)
    else:
        return ChatOpenAI(temperature=settings.temperature, **base_kwargs)


def _coerce_numeric_leaf(value: Any) -> Optional[float]:
    """Best-effort numeric coercion for schema recovery."""
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    txt = str(value).strip()
    if not txt:
        return None
    m = re.search(r"-?\d+(?:\.\d+)?", txt)
    if not m:
        return None
    try:
        return float(m.group(0))
    except Exception:
        return None


def _contains_numeric_signal(value: Any) -> bool:
    if value is None or isinstance(value, bool):
        return False
    if isinstance(value, (int, float)):
        return True
    if isinstance(value, dict):
        return any(_contains_numeric_signal(v) for v in value.values())
    if isinstance(value, list):
        return any(_contains_numeric_signal(v) for v in value)
    return bool(re.search(r"[-+]?\d+(?:\.\d+)?(?:e[-+]?\d+)?", str(value), re.IGNORECASE))


def _infer_balance_element_from_context(*texts: Any) -> Optional[str]:
    joined = " ".join(str(text or "") for text in texts if text)
    lowered = joined.lower()
    explicit_patterns = (
        (r"\bal(?:uminum|uminium)?[-\s]?based\b|\baa\d{4}\b", "Al"),
        (r"\bni(?:ckel)?[-\s]?based\b|\binconel\b|\bin718\b", "Ni"),
        (r"\bti(?:tanium)?[-\s]?based\b|\bti64\b|\bti-?6al-?4v\b", "Ti"),
        (r"\bfe(?:rritic|ron)?[-\s]?based\b", "Fe"),
        (r"\bco(?:balt)?[-\s]?based\b", "Co"),
        (r"\bmg(?:nesium)?[-\s]?based\b", "Mg"),
        (r"\bcu(?:pper)?[-\s]?based\b", "Cu"),
    )
    for pattern, element in explicit_patterns:
        if re.search(pattern, lowered):
            return element
    match = re.search(r"\b([A-Z][a-z]?)(?=\d|\b)", joined)
    if match:
        return match.group(1)
    return None


def _repair_large_other_bucket(payload: Any, fallback_element: Optional[str]) -> Any:
    if not isinstance(payload, dict) or not fallback_element:
        return payload
    other = _coerce_numeric_leaf(payload.get("other"))
    if other is None or other <= 50:
        return payload
    if fallback_element in payload:
        return payload
    repaired = dict(payload)
    repaired.pop("other", None)
    repaired[fallback_element] = other
    return repaired


def _normalize_composition_map(payload: Any) -> Any:
    """Normalize flat or step-keyed composition maps.

    Preferred schema is a flat element->number map. Some providers may still
    return a graded-step map such as {"0": {...}, "5": {...}}; keep that
    recoverable shape instead of failing validation.
    """
    if payload is None or not isinstance(payload, dict):
        return payload

    normalized: Dict[str, Any] = {}
    for raw_key, raw_value in payload.items():
        key = str(raw_key).strip()
        if not key:
            continue
        if isinstance(raw_value, dict):
            nested = _normalize_composition_map(raw_value)
            if nested:
                normalized[key] = nested
            continue
        numeric = _coerce_numeric_leaf(raw_value)
        if numeric is not None:
            normalized[key] = numeric
    return normalized or None


def _normalize_feature_map(payload: Any) -> Any:
    """Normalize free-form advanced feature maps without destroying ranges."""
    if payload is None:
        return None
    if isinstance(payload, str):
        text = payload.strip()
        if not text:
            return None
        try:
            payload = json.loads(text)
        except Exception:
            return None

    if not isinstance(payload, dict):
        return None

    if "Advanced_Quantitative_Features" in payload:
        nested = _normalize_feature_map(payload.get("Advanced_Quantitative_Features"))
        if nested is not None:
            return nested

    normalized: Dict[str, Any] = {}
    for raw_key, raw_value in payload.items():
        key = str(raw_key).strip()
        if not key or raw_value is None:
            continue
        key_norm = re.sub(r"[\s_\-]+", "", key).lower()
        if key_norm in _AQF_TECHNIQUE_KEYS:
            if isinstance(raw_value, dict):
                nested = _normalize_feature_map(raw_value)
                if nested:
                    normalized.update(nested)
            continue
        if isinstance(raw_value, dict):
            nested = _normalize_feature_map(raw_value)
            if nested:
                normalized[key] = nested
            continue
        if isinstance(raw_value, list):
            cleaned = [item for item in raw_value if item is not None and _contains_numeric_signal(item)]
            if cleaned:
                normalized[key] = cleaned
            continue
        if not _contains_numeric_signal(raw_value):
            continue
        normalized[key] = raw_value
    return normalized or None


def _normalize_metric_key_fragment(value: Any) -> str:
    text = re.sub(r"[^A-Za-z0-9]+", "_", str(value or "").strip()).strip("_")
    return text or "value"


def _structured_micro_key(parent_field: str, child_key: Any) -> str:
    fragment = _normalize_metric_key_fragment(child_key)
    lowered = fragment.lower()
    if parent_field == "phase_fraction_pct":
        return fragment if lowered.endswith("phase_fraction_pct") else f"{fragment}_phase_fraction_pct"
    if parent_field == "precipitate_size_avg_nm":
        return fragment if lowered.endswith("nm") else f"{fragment}_nm"
    if parent_field == "precipitate_volume_fraction_pct":
        return fragment if lowered.endswith("pct") else f"{fragment}_volume_fraction_pct"
    if parent_field == "grain_size_avg_um":
        return fragment if lowered.endswith("um") else f"{fragment}_grain_size_um"
    if parent_field == "porosity_pct":
        return fragment if lowered.endswith("pct") else f"{fragment}_porosity_pct"
    if parent_field == "relative_density_pct":
        return fragment if lowered.endswith("pct") else f"{fragment}_relative_density_pct"
    return f"{fragment}_{parent_field}"


class _LazyExtractor:
    """Wrapper around create_extractor that binds to a fresh LLM each call.

    TrustCall extractors need to be constructed with a particular LLM.
    However, long‑lived extractors can cause open connections and stale
    authentication.  This wrapper delays construction until the first
    invocation and uses the latest settings from ``knowmat2.app_config``.

    This wrapper also implements retry logic with exponential backoff for
    transient API failures.

    Parameters
    ----------
    tools: list
        A list of Pydantic models that define the tool schema.
    tool_choice: str
        The name of the tool (usually the name of the Pydantic class) to
        select when multiple tools are provided.
    enable_inserts: bool
        If True, allow the extractor to insert text into the prompt.
    agent_type: str
        The type of agent this extractor is for (determines which model to use).
    """

    # Retry configuration
    MAX_RETRIES = 3
    RETRY_DELAY_BASE = 5  # seconds, will be multiplied by attempt number

    def __init__(self, tools: list, tool_choice: str, enable_inserts: bool = False, 
                 agent_type: str = "default") -> None:
        self.tools = tools
        self.tool_choice = tool_choice
        self.enable_inserts = enable_inserts
        self.agent_type = agent_type

    def invoke(self, *args, **kwargs) -> Dict[str, Any]:
        """Invoke the extractor with retry logic for transient failures.
        
        Returns
        -------
        Dict[str, Any]
            The extractor response.
            
        Raises
        ------
        RuntimeError
            If all retries fail or authentication error occurs.
        """
        last_error: Optional[Exception] = None
        
        for attempt in range(self.MAX_RETRIES):
            try:
                llm = get_llm(agent_type=self.agent_type)
                extractor = create_extractor(
                    llm,
                    tools=self.tools,
                    tool_choice=self.tool_choice,
                    enable_inserts=self.enable_inserts,
                )
                return extractor.invoke(*args, **kwargs)
            except Exception as e:
                last_error = e
                error_str = str(e)
                
                # Authentication errors should not be retried
                if "401" in error_str or "invalid_model" in error_str.lower() or "authentication" in error_str.lower():
                    logger.error("LLM API authentication failed for %s agent: %s", self.agent_type, e)
                    raise RuntimeError(
                        f"LLM API authentication failed for {self.agent_type} agent: {e}. "
                        "Please check LLM_API_KEY and LLM_MODEL configuration in your .env file."
                    ) from e
                
                # Rate limit or server errors - retry with backoff
                if attempt < self.MAX_RETRIES - 1:
                    delay = self.RETRY_DELAY_BASE * (attempt + 1)
                    logger.warning(
                        "LLM invocation failed for %s agent (attempt %d/%d): %s. Retrying in %ds...",
                        self.agent_type, attempt + 1, self.MAX_RETRIES, e, delay
                    )
                    time.sleep(delay)
                else:
                    logger.error(
                        "LLM invocation failed for %s agent after %d attempts: %s",
                        self.agent_type, self.MAX_RETRIES, e
                    )
        
        raise RuntimeError(
            f"LLM invocation failed for {self.agent_type} agent after {self.MAX_RETRIES} retries: {last_error}"
        ) from last_error


# -----------------------------------------------------------------------------
# Pydantic schemas defining the structure of TrustCall tool outputs
# -----------------------------------------------------------------------------

class SubFieldDetection(BaseModel):
    """Output schema for the sub‑field detection agent.

    Attributes
    ----------
    sub_field: str
        The niche domain of materials science that best describes the paper.
        One of ``experimental``, ``computational``, ``simulation``,
        ``machine learning`` or ``hybrid``.
    updated_prompt: str
        An updated extraction prompt tailored to the detected sub‑field.
    """

    sub_field: str = Field(
        description=(
            "The detected materials science sub‑field.  Must be one of: experimental, "
            "computational, simulation, machine learning, or hybrid."
        )
    )
    updated_prompt: str = Field(
        description=(
            "An extraction prompt modified to emphasise instructions relevant to the detected sub‑field."
        )
    )


class Property(BaseModel):
    """Represents a material property extracted from the text.
    
    This schema supports both high-fidelity extraction (preserving inequalities,
    ranges, and qualitative values) and ML-ready numeric values for downstream
    database usage and model training.
    """

    property_name: str = Field(
        description=(
            "Full descriptive name of the material property (e.g., 'glass transition temperature', "
            "'melting temperature', 'critical casting diameter', 'fracture strength', 'compressive plasticity')."
        )
    )
    
    property_symbol: Optional[str] = Field(
        default=None,
        description=(
            "Standard symbol or abbreviation for the property as used in the paper (e.g., 'Tg', 'Tm', 'Tx', "
            "'Dc', 'σ_max', 'σ_y', 'ε_p'). Use null if no standard symbol is provided in the paper."
        )
    )
    
    value: Optional[str] = Field(
        description=(
            "Original value as reported in the paper. Can be: "
            "(1) A numeric string like '683.0' for exact measurements, "
            "(2) An inequality like '>50' or '<2000' for bounds, "
            "(3) A range like '12-30' for interval values, "
            "(4) A qualitative descriptor like 'no plasticity' or 'brittle', "
            "(5) null for missing/unreported values (e.g., table shows '-')."
        )
    )
    
    value_numeric: Optional[float] = Field(
        default=None,
        description=(
            "ML-ready numeric value extracted for database and model training. "
            "IMPORTANT: Always write values as decimal floats (e.g., 1.0e20), "
            "NEVER as plain large integers exceeding 999999999. "
            "For exact measurements: the measured value (e.g., 683.0). "
            "For inequalities: the boundary value (e.g., '>50' → 50.0, '<2000' → 2000.0). "
            "For ranges: the midpoint (e.g., '12-30' → 21.0). "
            "For qualitative: a mapped numeric value (e.g., 'no plasticity' → 0.0). "
            "For missing: null."
        ),
    )

    value_range: Optional[str] = Field(
        default=None,
        description=(
            "Original textual range when the reported value is an interval, "
            "e.g. '200-230'. Keep null for non-range values."
        ),
    )

    value_stddev: Optional[float] = Field(
        default=None,
        description=(
            "Standard deviation when a mean±std format is reported, e.g. 215±5 -> 5. "
            "Always write as a decimal float (e.g., 5.0), never as a large plain integer. "
            "Keep null when not available."
        ),
    )
    
    value_type: str = Field(
        description=(
            "Classification of the value type for downstream processing: "
            "'exact' - precise measurement (e.g., '683.0' K), "
            "'lower_bound' - inequality with '>' (e.g., '>50 mm'), "
            "'upper_bound' - inequality with '<' (e.g., '<2000 MPa'), "
            "'range' - interval (e.g., '12-30 mm'), "
            "'qualitative' - textual descriptor (e.g., 'no plasticity'), "
            "'missing' - not reported in paper (null value)."
        )
    )
    
    unit: Optional[str] = Field(
        default=None,
        description="Measurement unit of the property (e.g., 'K', 'MPa', 'mm', '%')."
    )

    test_temperature_k: Optional[float] = Field(
        default=None,
        description=(
            "Actual test environment temperature in Kelvin. "
            "Always write as a decimal float (e.g., 1873.0), never as a large plain integer. "
            "Use only the testing temperature here, never fabrication or heat-treatment temperatures."
        ),
    )
    
    measurement_condition: Optional[str] = Field(
        default=None,
        description=(
            "Conditions under which the property was measured. "
            "CRITICAL: If a test temperature is mentioned, ALWAYS start with 'at XXX K'. "
            "Then add other conditions (pressure, sample geometry, heating rate, strain rate). "
            "Examples: 'at 298.15 K; strain rate 1e-3 /s', 'at 1073.15 K; heating rate 20 K/min; Ar atmosphere'. "
            "Use null if not provided."
        )
    )

    strain_rate_s1: Optional[str] = Field(
        default=None,
        description=(
            "Strain rate for tensile or compressive testing, preserved as source text "
            "(e.g., '1e-3 s^-1', '5 x 10^-4 s^-1'). Use null if not reported."
        ),
    )

    tensile_speed_mm_min: Optional[float] = Field(
        default=None,
        description="Tensile or crosshead speed in mm/min when explicitly reported. Use null if not reported.",
    )

    hardness_load: Optional[str] = Field(
        default=None,
        description=(
            "Hardness indentation load with unit preserved, e.g. '200 gf' or '0.98 N'. "
            "Use null if not reported."
        ),
    )

    hardness_dwell_time_s: Optional[float] = Field(
        default=None,
        description="Hardness dwell time in seconds. Use null if not reported.",
    )

    data_source: Optional[str] = Field(
        default=None,
        description=(
            "Source modality for this property value: 'text' for body/table/caption text, "
            "'image' for chart or figure-derived values, or null if unclear."
        ),
    )

    test_specimen: Optional[str] = Field(
        default=None,
        description=(
            "Specimen standard or geometry linked to this test, e.g. 'ASTM E8, gauge length 25 mm'. "
            "Use null if not reported."
        ),
    )

    note: Optional[str] = Field(
        default=None,
        description=(
            "Short note for this property entry, such as elongation interpretation or provenance cautions. "
            "Use null if not needed."
        ),
    )
    
    additional_information: Optional[str] = Field(
        default=None,
        description=(
            "Any additional context related to this property, such as anisotropy details, "
            "figure/table references, uncertainty notes, or data quality flags."
        ),
    )


class CompositionProperties(BaseModel):
    """Represents the properties, processing conditions, and characterisation for a composition."""

    composition: str = Field(
        default="",
        description="The chemical composition of the material as written in the paper (including any abbreviations)."
    )

    sample_id: Optional[str] = Field(
        default=None,
        description=(
            "Stable specimen identifier for this runtime composition. "
            "All tests belonging to the same specimen should share the same sample_id. "
            "Prefer informative IDs such as {alloy}_{route}_{state} when the paper gives enough context; "
            "avoid overly generic labels like AP/HT unless the source itself only uses that code. "
            "For retained comparison matrices, preserve the explicit family/state granularity from the paper "
            "(for example R0 vs R5 vs S0 vs S15, theta0 vs theta45 vs theta90, As_Fabricated vs T6, "
            "Powder vs PBF_EB vs PBF_LB). Do not drop the family prefix when it distinguishes retained specimens. "
            "If the same specimen appears under a shorthand code and a long descriptive alias, choose one canonical "
            "sample_id rather than emitting duplicate entries. For Reference items, preserve the explicit benchmark "
            "label/state rather than collapsing multiple named benchmarks into one umbrella id such as Pure_Al_Reference "
            "or various_AM_alloys_reference. Do not invent a standalone sample_id for powder, ingot, or "
            "intermediate-route mentions unless that state is itself a retained specimen with sample-resolved evidence. "
            "Do not create separate sample_id entries for testing temperatures, creep stresses, exposure times, or "
            "optimization breadcrumbs unless the paper clearly retains them as standalone specimens in the final comparison set."
        ),
    )

    alloy_name_raw: Optional[str] = Field(
        default=None,
        description=(
            "Raw alloy name from source text, preserving commercial names and original formatting "
            "(e.g., 'IN718', 'Ti-6Al-4V'). Use null if not explicitly provided."
        ),
    )

    gradient_material: Optional[bool] = Field(
        default=None,
        description=(
            "Whether this composition entry represents a gradient material specimen. "
            "Prefer one gradient entry unless the paper explicitly reports layer-specific independent data."
        ),
    )

    gradient_group_id: Optional[str] = Field(
        default=None,
        description=(
            "Linking identifier used only when one gradient specimen is intentionally split into multiple "
            "layer-specific runtime compositions."
        ),
    )

    role: Optional[str] = Field(
        default="Target",
        description=(
            "Material role in this paper. "
            "'Target' = synthesized, processed, or tested in this work (has original experimental data). "
            "'Reference' = only cited from other papers for comparison (no original data). "
            "Use 'Reference' only when the current paper reports specimen-resolved comparison rows/values/caption data "
            "for that benchmark material. Named cast/baseline/benchmark alloys appearing in a current-paper "
            "comparison table, figure, caption, or legend should still be emitted as standalone Reference entries. "
            "Generic literature discussion, broad landscape plots, review-style alloy lists, umbrella labels "
            "such as 'various AM alloys', or narrative 'better than X/Y/Z' claims should not become standalone "
            "Reference entries. If the retained comparison set explicitly includes state-paired benchmarks or "
            "directly characterized upstream endpoints, keep those exact labels as items rather than collapsing or "
            "dropping them. "
            "Default to 'Target' if unclear."
        )
    )
    
    composition_normalized: Optional[str] = Field(
        default=None,
        description=(
            "Normalized chemical formula containing ONLY element symbols and numbers. "
            "Remove any parenthetical abbreviations or sample codes. "
            "E.g., 'Ti42Hf21Nb21V16 (T42)' → 'Ti42Hf21Nb21V16', "
            "'FeCoCrNiMo0.5' → 'Fe22.22Co22.22Cr22.22Ni22.22Mo11.11'."
        )
    )

    nominal_composition: Optional[Dict[str, Any]] = Field(
        default=None,
        description=(
            "Nominal bulk composition by element when available. Preferred form is a flat "
            "element->number map such as {'Ti': 88.9, 'Al': 6.4}. "
            "Design / target / supplier values belong here. "
            "If a named element is marked Bal./balance, compute and store that element explicitly instead of using 'other'. "
            "Never encode graded steps as nested percentage keys; emit separate compositions instead. "
            "Use null if not provided."
        ),
    )

    nominal_composition_type: Optional[str] = Field(
        default=None,
        description=(
            "Composition unit for nominal_composition. Expected values: 'wt%' or 'at%'. "
            "Use null when unknown."
        ),
    )

    measured_composition: Optional[Dict[str, Any]] = Field(
        default=None,
        description=(
            "Measured composition by element (e.g., EDS/EPMA) when available. "
            "Use this for ICP-OES/EDS/EPMA/SEM-EDS measured tables rather than nominal design formulas. "
            "Preferred form is a flat element->number map. "
            "Never encode graded steps as nested percentage keys; emit separate compositions instead. "
            "Use null if not provided."
        ),
    )

    measured_composition_type: Optional[str] = Field(
        default=None,
        description=(
            "Composition unit for measured_composition. Expected values: 'wt%' or 'at%'. "
            "Use null when unknown."
        ),
    )

    measured_composition_method: Optional[str] = Field(
        default=None,
        description=(
            "Measurement method for measured_composition, e.g. 'EDS', 'EDX (SEM)', 'EPMA', 'ICP-OES'. "
            "Use null if not reported."
        ),
    )

    composition_note: Optional[str] = Field(
        default=None,
        description=(
            "Top-level composition note for special annotations such as ranges, upper-limit impurities, "
            "balance handling, or other composition caveats. Use null if not needed."
        ),
    )
    
    source_doi: Optional[str] = Field(
        default=None,
        description=(
            "The DOI of the paper if found in the text. "
            "E.g., '10.1016/j.msea.2024.147225'. Use null if not found."
        )
    )
    
    main_phase: Optional[str] = Field(
        default=None,
        description=(
            "Primary crystal structure identified from XRD, EBSD, or similar characterization. "
            "Use matrix-phase labels such as Gamma matrix, BCC, FCC, HCP, or amorphous. "
            "Combined matrix labels such as 'FCC + BCC' or 'FCC + L12' are allowed when the paper explicitly "
            "describes a dual-phase or multi-phase matrix. "
            "Do not use isolated Laves, carbides, or gamma-prime precipitates as the main phase. "
            "Use null if not mentioned."
        )
    )
    
    has_precipitates: bool = Field(
        default=False,
        description=(
            "Whether any secondary phases or precipitates are mentioned in the microstructure description. "
            "Examples: sigma phase, mu phase, L12, NbC, carbides, nitrides. "
            "Set to true if ANY precipitates are mentioned, false otherwise."
        )
    )
    
    grain_size_avg_um: Optional[float] = Field(
        default=None,
        description=(
            "Average grain size in micrometers (μm). "
            "If reported in nanometers, convert to micrometers (divide by 1000). "
            "Use null if not reported."
        )
    )

    porosity_pct: Optional[float] = Field(
        default=None,
        description=(
            "Porosity percentage when explicitly reported as a numeric value. "
            "Qualitative statements such as 'no porosity detected' or 'pore-free' are not numeric porosity values; "
            "keep this field null unless the paper gives an explicit percentage."
        ),
    )

    relative_density_pct: Optional[float] = Field(
        default=None,
        description=(
            "Relative density percentage when explicitly reported. "
            "Qualitative statements such as 'fully dense' or 'full densification' do not justify filling 100%. "
            "Use null if not reported and never infer 100%."
        ),
    )

    precipitate_size_avg_nm: Optional[float] = Field(
        default=None,
        description="Average precipitate size in nm when explicitly reported. Use null if not reported.",
    )

    precipitate_volume_fraction_pct: Optional[float] = Field(
        default=None,
        description=(
            "Aggregate precipitate volume fraction percentage when explicitly reported. Use null if not reported."
        ),
    )

    phase_fraction_pct: Optional[float] = Field(
        default=None,
        description=(
            "Overall phase fraction percentage when explicitly reported as a root microstructure quantity. "
            "Use null if not reported."
        ),
    )

    advanced_quantitative_features: Optional[Dict[str, Any]] = Field(
        default=None,
        description=(
            "Free-form quantified microstructure metrics not covered by the root scalar fields. "
            "Use explicit dynamic keys such as 'Cell_Size_avg_um', 'KAM_Value_deg', "
            "'Equiaxed_Grain_Size_avg_um', or 'Dislocation_Density_m2'. "
            "Keep separate sub-populations separate instead of averaging them into one scalar. "
            "Store only quantitative values, ranges, or numerically anchored metrics here; "
            "do not store technique headings or narrative method descriptions such as SEM/TEM/XRD/EBSD summaries."
        ),
    )
    
    processing_conditions: str = Field(
        default="not provided",
        description=(
            "Processing conditions with dual-track text in one string: "
            "'original: <detailed source-faithful process description preserving all explicit process details> "
            "|| simplified: <condensed process summary that keeps key details and removes redundancy without over-simplifying>'. "
            "Use 'not provided' if absent."
        )
    )

    processing_params: Optional[Dict[str, Any]] = Field(
        default=None,
        description=(
            "Structured key process parameters extracted from the text. "
            "Use standardised keys: "
            "Laser_Power_W (float), Scanning_Speed_mm_s (float), "
            "Layer_Thickness_um (float), Hatch_Spacing_um (float), "
            "Build_Plate_Temperature_K (float), Protective_Atmosphere (str, e.g. 'Argon'), "
            "Volumetric_Energy_Density_J_mm3 (float/range), Oxygen_Content_ppm (float), "
            "Beam_Current_mA (float), Acceleration_Voltage_kV (float), "
            "Build_Orientation (str, e.g. 'Parallel-BD'). "
            "For heat-treatment ranges, preserve strings such as '1273-1373' or '2-4' instead of averaging. "
            "Include ONLY parameters with explicit values in the paper. "
            "Use null if no structured parameters can be extracted."
        )
    )

    equipment: Optional[str] = Field(
        default=None,
        description=(
            "Equipment model, instrument, or furnace information for the processing route. "
            "Use null if not reported."
        ),
    )

    build_orientation: Optional[str] = Field(
        default=None,
        description=(
            "Build/loading direction for this specific sample/condition entry. "
            "Examples: 'Parallel-BD', 'Perpendicular-BD', 'X-Y plane', 'X-Z plane', "
            "'Horizontal', 'Vertical', '45deg'. "
            "CRITICAL: If the paper reports properties for the same composition in "
            "different directions, create SEPARATE composition entries for each direction "
            "and set this field accordingly. Use null if not applicable."
        )
    )

    process_category: Optional[str] = Field(
        default=None,
        description=(
            "Base manufacturing process category. Prefer the base route rather than only the latest post-treatment. "
            "Supported values include: AM_DED, AM_LPBF, AM_SLM, WAAM, EBM, Powder_Metallurgy, "
            "Wrought, SPS, Arc_Melting, HeatTreat, Casting, Forging, Rolling, Mechanical_Alloying, or Unknown. "
            "AM_DED covers DED/LENS/LAAM/laser cladding style deposition routes. "
            "EBM covers electron beam melting / PBF-EB / electron beam powder bed fusion. "
            "Powder_Metallurgy covers consolidated PM/HIP/extrusion/isothermal-forging routes only. "
            "Do not label a final LPBF/DED/EBM specimen as Powder_Metallurgy just because the paper also describes "
            "powder production, powder characterization, or feedstock preparation. "
            "Likewise, do not create a separate Powder_Metallurgy/feedstock item unless the powder or upstream state "
            "is explicitly characterized or tabulated as its own specimen in the paper."
        )
    )

    xrd_details: Optional[str] = Field(
        default=None,
        description=(
            "XRD instrument, scan parameters, and phase identification results. "
            "Example: 'XRD (D8 Advance, Cu-Ka, 40kV/40mA, 20-100 deg, 1.5 deg/min); "
            "single BCC phase identified; dislocation density 3.36e14 m-2'. "
            "Do NOT mix microstructure morphology descriptions here."
        )
    )

    microstructure_description: Optional[str] = Field(
        default=None,
        description=(
            "Microstructure morphology from SEM/EBSD/TEM observations in dual-track format: "
            "'original: <detailed source-faithful microstructure description preserving all explicit features> "
            "|| simplified: <condensed summary that keeps key microstructural details without over-simplifying>'. "
            "Include grain shape, size distribution, phase morphology, texture, "
            "columnar vs equiaxed, precipitate distribution, etc. "
            "Example simplified part: 'Equiaxed grains + columnar regions; single BCC phase'. "
            "Do NOT include XRD instrument parameters here."
        )
    )

    precipitates: List[Dict[str, Any]] = Field(
        default_factory=list,
        description=(
            "Explicit precipitate list. Each entry should include phase_type and optionally "
            "volume_fraction_pct, e.g. {'phase_type': 'Laves', 'volume_fraction_pct': 3.2}."
        ),
    )

    grain_size_text: Optional[str] = Field(
        default=None,
        description=(
            "Original text describing grain size measurements, including method and "
            "any direction-dependent values. Example: 'XY plane equiaxed ~200 um; "
            "XZ plane columnar 10.4 um (vertical) / 6.72 um (horizontal), measured by "
            "line intercept and area methods'."
        )
    )
    
    characterisation: Dict[str, str] = Field(
        default_factory=dict,
        description=(
            "Characterisation techniques and their findings keyed by technique names. "
            "Use structured keys: 'XRD', 'Microstructure', 'EBSD', 'TEM', 'SEM', 'APT', etc. "
            "'XRD' should contain phase identification and instrument details. "
            "'Microstructure' should contain grain morphology and distribution descriptions. "
            "Do not use this field as the primary storage location for advanced quantitative metrics; "
            "use advanced_quantitative_features for those."
        )
    )
    properties_of_composition: List[Property] = Field(
        default_factory=list,
        description=(
            "List of properties extracted for this specimen. Multiple test temperatures, creep stresses, "
            "exposure times, and loading conditions for the same specimen should stay in this list rather than "
            "triggering new composition entries."
        )
    )

    @model_validator(mode="before")
    @classmethod
    def repair_structured_microstructure_scalars(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data

        repaired = dict(data)
        aqf = _normalize_feature_map(repaired.get("advanced_quantitative_features")) or {}
        moved_any = False
        structured_fields = (
            "grain_size_avg_um",
            "precipitate_size_avg_nm",
            "precipitate_volume_fraction_pct",
            "phase_fraction_pct",
            "porosity_pct",
            "relative_density_pct",
        )

        for field_name in structured_fields:
            value = repaired.get(field_name)
            if not isinstance(value, dict):
                continue
            for child_key, child_value in value.items():
                if child_value is None:
                    continue
                aqf[_structured_micro_key(field_name, child_key)] = child_value
            repaired[field_name] = None
            moved_any = True

        if moved_any:
            repaired["advanced_quantitative_features"] = aqf or None
        return repaired

    @model_validator(mode="after")
    def fill_composition_from_normalized(self) -> "CompositionProperties":
        """When LLM returns only composition_normalized, use it as composition."""
        updates: Dict[str, Any] = {}
        if not self.composition and self.composition_normalized:
            updates["composition"] = self.composition_normalized

        balance_element = _infer_balance_element_from_context(
            self.alloy_name_raw,
            self.composition_normalized,
            self.composition,
        )
        nominal = _repair_large_other_bucket(
            _normalize_composition_map(self.nominal_composition),
            balance_element,
        )
        measured = _repair_large_other_bucket(
            _normalize_composition_map(self.measured_composition),
            balance_element,
        )
        advanced_features = _normalize_feature_map(self.advanced_quantitative_features)
        if nominal != self.nominal_composition:
            updates["nominal_composition"] = nominal
        if measured != self.measured_composition:
            updates["measured_composition"] = measured
        if advanced_features != self.advanced_quantitative_features:
            updates["advanced_quantitative_features"] = advanced_features

        if updates:
            return self.model_copy(update=updates)
        return self


class CompositionList(BaseModel):
    """Encapsulates a list of compositions with extracted details."""

    compositions: List[CompositionProperties] = Field(
        description="A list of extracted material compositions."
    )

    @model_validator(mode="before")
    @classmethod
    def parse_compositions_string(cls, data: Any) -> Any:
        """Handle LLM returning compositions as a JSON string instead of a list."""
        if isinstance(data, dict):
            val = data.get("compositions")
            if isinstance(val, str):
                try:
                    data["compositions"] = json.loads(val)
                except (json.JSONDecodeError, TypeError):
                    pass
        return data


class EvaluationFeedback(BaseModel):
    """Schema for the evaluation agent's output."""

    confidence_score: float = Field(
        description=(
            "A float between 0 and 1 indicating how accurate the extracted data is compared to the paper."
        )
    )
    rationale: str = Field(
        description="A brief explanation of the evaluation, including missing or hallucinated fields."
    )
    missing_fields: Optional[List[str]] = Field(
        default=None,
        description="A list of fields that were missing from the extraction but present in the paper."
    )
    hallucinated_fields: Optional[List[str]] = Field(
        default=None,
        description="A list of fields that were present in the extraction but not supported by the paper."
    )
    update_prompt: Optional[str] = Field(
        default=None,
        description=(
            "Suggested text to append to the current extraction prompt to improve future extractions."
        )
    )
    needs_rerun: bool = Field(
        description=(
            "Whether another extraction/evaluation cycle should be performed to improve accuracy."
        )
    )


class ManagerFeedback(BaseModel):
    """Schema for the manager agent's output - focused only on aggregation."""

    final_extracted_data: CompositionList = Field(
        description="The final aggregated extraction data combining the best information from all runs."
    )
    
    aggregation_rationale: str = Field(
        description=(
            "Detailed explanation of how data from multiple runs was combined. "
            "Explain what decisions were made, what conflicts were resolved, "
            "which run data was preferred and why."
        )
    )
    
    human_review_guide: str = Field(
        description=(
            "Specific guidance for human reviewers on what to double-check in the final result. "
            "Highlight areas where runs disagreed, uncertain values, or potential issues. "
            "Be specific about compositions, properties, or values to verify."
        )
    )


class FlaggingFeedback(BaseModel):
    """Schema for the flagging agent's output - focused only on quality assessment."""

    final_confidence_score: float = Field(
        description=(
            "A float between 0 and 1 indicating confidence in the final aggregated result. "
            "Base this on the manager's aggregation quality, consistency across runs, "
            "and the complexity of issues noted in the human review guide."
        )
    )
    
    confidence_rationale: str = Field(
        description=(
            "Explanation of why this confidence score was assigned. "
            "Reference the manager's aggregation decisions, run consistency, "
            "and potential review areas."
        )
    )
    
    needs_human_review: bool = Field(
        description=(
            "Whether human review is recommended based on confidence score and review complexity. "
            "Generally true if confidence < 0.8 OR if human review guide indicates significant issues."
        )
    )

# -----------------------------------------------------------------------------
# Lazy extractors exposed for use in nodes
# -----------------------------------------------------------------------------

subfield_extractor = _LazyExtractor(
    [SubFieldDetection], "SubFieldDetection", enable_inserts=True, agent_type="subfield"
)

# The extraction output may be large, so we do not enable inserts here.
extraction_extractor = _LazyExtractor(
    [CompositionList], "CompositionList", enable_inserts=False, agent_type="extraction"
)

evaluation_extractor = _LazyExtractor(
    [EvaluationFeedback], "EvaluationFeedback", enable_inserts=True, agent_type="evaluation"
)

manager_extractor = _LazyExtractor(
    [ManagerFeedback], "ManagerFeedback", enable_inserts=True, agent_type="manager"
)

flagging_extractor = _LazyExtractor(
    [FlaggingFeedback], "FlaggingFeedback", enable_inserts=True, agent_type="flagging"
)
