"""Node for three-dimensional paper routing and supplement loading.

This node classifies the paper along three axes (base_material, application,
research_paradigm) and loads the corresponding supplement files that define
domain-specific extraction field structures and priorities.
"""

import hashlib
import json
import logging
from pathlib import Path
from typing import Dict, List

from knowmat.app_config import settings
from knowmat.extractors import routing_extractor, PaperRouting
from knowmat.prompt_loader import load_routing_supplement, load_yaml_templates_required
from knowmat.states import KnowMatState

logger = logging.getLogger(__name__)

_ROUTING_PROMPT_TEMPLATE = load_yaml_templates_required(
    "subfield_detection.yaml", ("prompt_template",)
).get("prompt_template", "")

_BASE_MAP = {
    "Metals": "base/Metals.txt",
    "Ceramics_Inorganic": "base/Ceramics_Inorganic.txt",
    "Polymers": "base/Polymers.txt",
    "Composites": "base/Composites.txt",
    "Organic_Small_Molecules": "base/Organic_Small_Molecules.txt",
}

_APPLICATION_MAP = {
    "Structural": "application/Structural.txt",
    "Functional": "application/Functional.txt",
}

_PARADIGM_MAP = {
    "Experimental": "paradigm/Experimental.txt",
    "Pure_Simulation": "paradigm/Pure_Simulation.txt",
    "Hybrid": "paradigm/Hybrid.txt",
}

_DOMAIN_MAP = {
    "Machining": "domain/Machining.txt",
    "Coating": "domain/Coating.txt",
    "Battery": "domain/Battery.txt",
    "Additive_Manufacturing": "domain/Additive_Manufacturing.txt",
    "Titanium_Alloy": "domain/Titanium_Alloy.txt",
    "High_Temperature_Alloy": "domain/High_Temperature_Alloy.txt",
    "High_Entropy_Alloy": "domain/High_Entropy_Alloy.txt",
}


def _frozen_routing_cache(state: KnowMatState, paper_text: str) -> tuple[Path, dict] | None:
    """Return a paper-local deterministic cache only for a frozen OCR run."""

    baseline_id = str(state.get("ocr_baseline_id") or "").strip()
    manifest_path = str(state.get("ocr_manifest_path") or "").strip()
    output_dir = str(state.get("output_dir") or "").strip()
    if not baseline_id or not manifest_path or not output_dir:
        return None
    identity = {
        "ocr_baseline_id": baseline_id,
        "paper_text_sha256": hashlib.sha256(paper_text.encode("utf-8")).hexdigest(),
        "routing_prompt_sha256": hashlib.sha256(
            _ROUTING_PROMPT_TEMPLATE.encode("utf-8")
        ).hexdigest(),
        "model": settings.subfield_model,
    }
    return Path(output_dir) / "v11" / "01_routing.json", identity


def _read_frozen_routing(path: Path, identity: dict) -> dict | None:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(payload, dict) or payload.get("identity") != identity:
        return None
    routing = payload.get("routing")
    return dict(routing) if isinstance(routing, dict) else None


def _write_frozen_routing(path: Path, identity: dict, routing: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(
        json.dumps(
            {"identity": identity, "routing": routing},
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def _compact_direction_text(content: str, edge_chars: int = 2500) -> str:
    """Keep high-priority direction preamble and v11 override while removing repetition."""
    if len(content) <= edge_chars * 2:
        return content
    return (
        content[:edge_chars].rstrip()
        + "\n\n[中间旧版展开说明已省略；以 system 中 v11 强制合约为准]\n\n"
        + content[-edge_chars:].lstrip()
    )


def _build_routing_supplements(routing: Dict) -> str:
    """Load and concatenate supplement files based on routing classification."""
    parts: List[str] = []
    supplements_loaded: List[str] = []

    base = routing.get("base_material", "")
    if base in _BASE_MAP:
        content = load_routing_supplement(_BASE_MAP[base])
        if content:
            parts.append(
                f"=== Base Material Route: {base} ===\n"
                "Apply the alpha.6 core four-axis contract with this material route."
            )
            supplements_loaded.append(f"directions/{_BASE_MAP[base]}")

    app = routing.get("application", "")
    if app in _APPLICATION_MAP:
        content = load_routing_supplement(_APPLICATION_MAP[app])
        if content:
            parts.append(
                f"=== Application Route: {app} ===\n"
                "Apply the alpha.6 property and test-condition rules for this application."
            )
            supplements_loaded.append(f"directions/{_APPLICATION_MAP[app]}")

    paradigm = routing.get("research_paradigm", "")
    if paradigm in _PARADIGM_MAP:
        content = load_routing_supplement(_PARADIGM_MAP[paradigm])
        if content:
            parts.append(
                f"=== Research Paradigm Route: {paradigm} ===\n"
                "Keep experimental, computed, literature and derived origins isolated."
            )
            supplements_loaded.append(f"directions/{_PARADIGM_MAP[paradigm]}")

    for domain in routing.get("domain_overlays", []):
        if domain in _DOMAIN_MAP:
            content = load_routing_supplement(_DOMAIN_MAP[domain])
            if content:
                parts.append(f"=== Domain Overlay: {domain} ===\n{content}")
                supplements_loaded.append(f"directions/{_DOMAIN_MAP[domain]}")

    routing["supplements_loaded"] = supplements_loaded
    return "\n\n".join(parts)


def detect_sub_field(state: KnowMatState) -> dict:
    """Classify the paper and load routing supplements.

    Returns
    -------
    dict
        Updates containing ``paper_routing``, ``routing_supplements``,
        and ``sub_field`` (for backwards compatibility).
    """
    paper_text = state.get("paper_text", "")
    cache = _frozen_routing_cache(state, paper_text)
    routing = _read_frozen_routing(*cache) if cache is not None else None
    if routing is not None:
        logger.info("Frozen OCR routing cache hit: %s", cache[0])
    else:
        prompt = _ROUTING_PROMPT_TEMPLATE.format(paper_text=paper_text)
        result = routing_extractor.invoke(prompt)
        response = result.get("responses", [None])[0]

        if not response:
            logger.warning("Routing extractor returned no response, using defaults")
            routing = {
                "base_material": "Metals",
                "application": "Structural",
                "research_paradigm": "Experimental",
                "domain_overlays": [],
                "patch_tags": [],
            }
        elif isinstance(response, PaperRouting):
            routing = {
                "base_material": response.base_material,
                "application": response.application,
                "research_paradigm": response.research_paradigm,
                "domain_overlays": response.domain_overlays,
                "patch_tags": response.patch_tags,
            }
        else:
            routing = dict(response)
        if cache is not None:
            _write_frozen_routing(cache[0], cache[1], routing)

    supplements_text = _build_routing_supplements(routing)

    logger.info(
        "Paper routing: %s × %s × %s | overlays=%s | supplements=%d chars",
        routing.get("base_material"),
        routing.get("application"),
        routing.get("research_paradigm"),
        routing.get("domain_overlays", []),
        len(supplements_text),
    )

    return {
        "paper_routing": routing,
        "routing_supplements": supplements_text,
        "sub_field": routing.get("base_material", "experimental"),
    }
