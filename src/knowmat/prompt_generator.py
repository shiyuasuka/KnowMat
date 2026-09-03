"""Prompt generation utilities for KnowMat 2.0.

Constructs compact evidence-first alpha25 prompts for the extraction agent.
"""

from typing import Any, Iterable, Mapping

from knowmat.alpha25.package import load_alpha25_package
from knowmat.alpha25.prompt_compiler import (
    Axis,
    compile_system_prompt,
    compile_task_prompt,
)
from knowmat.app_config import settings


def generate_system_prompt(
    routing_supplements: str = "",
    prompt_update: str = "",
) -> str:
    """Return the system prompt for the extraction agent.

    Parameters
    ----------
    routing_supplements : str
        Concatenated supplement text loaded from routing classification.
        Injected at the ``{routing_supplements}`` placeholder in the template.
    """
    package = load_alpha25_package(settings.alpha25_package_root)
    supplements = [routing_supplements] if routing_supplements.strip() else []
    return compile_system_prompt(
        package=package,
        routing_supplements=supplements,
        prompt_update=prompt_update,
    )


def generate_user_prompt(
    paper_text: str,
    target_base_material: str = "",
    target_application: str = "",
    target_research_paradigm: str = "",
    target_patch_tags: str = "",
) -> str:
    """Wrap the user message around the paper text with routing hints.

    Parameters
    ----------
    paper_text : str
        The full OCR-parsed paper text.
    target_base_material, target_application, target_research_paradigm : str
        Routing hints from the classification step.
    target_patch_tags : str
        Comma-separated patch tags hint.
    """
    routing = {
        key: value
        for key, value in {
            "base_material": target_base_material,
            "application": target_application,
            "research_paradigm": target_research_paradigm,
            "domain_overlays": target_patch_tags,
        }.items()
        if value
    }
    return compile_task_prompt(paper_text, axis="all", routing=routing)


def generate_axis_task_prompt(
    evidence: str,
    *,
    axis: Axis,
    routing: Mapping[str, Any] | None = None,
    sample_anchors: Iterable[Mapping[str, Any]] = (),
    unit_id: str = "",
    evidence_kind: str = "prose",
) -> str:
    """Generate one source-only axis extraction request."""

    return compile_task_prompt(
        evidence,
        axis=axis,
        routing=routing,
        sample_anchors=sample_anchors,
        unit_id=unit_id,
        evidence_kind=evidence_kind,
    )
