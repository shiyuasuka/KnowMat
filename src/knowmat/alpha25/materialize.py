"""Generic reconciliation and candidate materialization for alpha25 facts."""

from __future__ import annotations

import json
import os
import re
import unicodedata
from collections import Counter
from copy import deepcopy
from dataclasses import dataclass
from typing import Any, Iterable, Sequence

from knowmat.alpha25.contracts import (
    AxisFact,
    CompositionFact,
    InventoryAnchor,
    ProcessingFact,
    PropertyFact,
    StructureFact,
)
from knowmat.alpha25.claim_quality import (
    ClaimQualityMode,
    deduplicate_axis_facts_with_audit,
    filter_axis_facts,
    semantic_fact_signature,
)
from knowmat.alpha25.property_context import PropertyContextIndex


_ID_FIELDS = {
    "candidate_stage_id",
    "stage_index_candidate",
    "property_id_candidate",
    "observation_id",
    "characterization_id",
    "entity_id",
}
_EVIDENCE_FIELDS = {"source_evidence", "confidence"}
_ELEMENT_SYMBOLS = frozenset(
    (
        "H He Li Be B C N O F Ne Na Mg Al Si P S Cl Ar K Ca Sc Ti V Cr Mn Fe "
        "Co Ni Cu Zn Ga Ge As Se Br Kr Rb Sr Y Zr Nb Mo Tc Ru Rh Pd Ag Cd In "
        "Sn Sb Te I Xe Cs Ba La Ce Pr Nd Pm Sm Eu Gd Tb Dy Ho Er Tm Yb Lu Hf "
        "Ta W Re Os Ir Pt Au Hg Tl Pb Bi Po At Rn Fr Ra Ac Th Pa U Np Pu Am Cm "
        "Bk Cf Es Fm Md No Lr Rf Db Sg Bh Hs Mt Ds Rg Cn Nh Fl Mc Lv Ts Og"
    ).split()
)
_ELEMENT_SYMBOL_KEYS = {symbol.casefold() for symbol in _ELEMENT_SYMBOLS}
_GREEK_ALIAS_NAMES = {
    "α": "alpha",
    "β": "beta",
    "γ": "gamma",
    "δ": "delta",
    "ε": "epsilon",
    "λ": "lambda",
    "σ": "sigma",
}
_UNRESOLVED_ALIASES = {
    "",
    "na",
    "none",
    "notapplicable",
    "notavailable",
    "notreported",
    "notprovided",
    "unknown",
    "unspecified",
}
_GENERIC_MATERIAL_WORDS = {
    "alloys",
    "composites",
    "materials",
    "metals",
    "nanocomposites",
    "samples",
    "specimens",
    "superalloys",
}
_COMPOSITION_SOURCE_TYPES = {
    "nominal",
    "measured",
    "provided",
    "calculated",
    "inferred",
    "unknown",
}
_COMPOSITION_BASES = {
    "wt%",
    "at%",
    "vol%",
    "mol%",
    "mass_fraction",
    "volume_fraction",
    "atomic_fraction",
    "formula_ratio",
    "mass_trace",
    "atomic_trace",
    "unknown",
}
_COMPOSITION_COMPONENT_TYPES = {
    "elemental",
    "phase",
    "constituent",
    "formula",
    "ratio",
    "unknown",
}
_COMPOSITION_DATA_SOURCES = {
    "text",
    "table",
    "image",
    "figure",
    "supplement",
    "abstract",
    "external_reference",
    "unknown",
}
_COMPOSITION_VALUE_KINDS = {
    "scalar",
    "range",
    "inequality",
    "balance",
    "categorical",
    "formula",
    "unknown",
}
_STRUCTURE_KINDS = {
    "phase_assemblage",
    "grain_structure",
    "precipitate",
    "texture",
    "defect",
    "porosity",
    "interface",
    "morphology",
    "transformation",
    "surface_or_layer",
    "configuration",
    "other",
}
_STRUCTURE_SOURCE_TYPES = {
    "reported",
    "calculated",
    "inferred",
    "simulated",
    "cited",
    "unknown",
}
_STRUCTURE_VALUE_KINDS = {"scalar", "range", "inequality", "categorical", "text"}
_STRUCTURE_DATA_NATURES = {
    "reported",
    "derived",
    "calculated",
    "inferred",
    "simulated",
    "unknown",
}
_PROCESS_EDGE_TYPES = {"next", "branch", "merge", "parallel", "repeat"}
_IDENTITY_SUFFIX = re.compile(
    r"(?i)\s+(?:samples?|specimens?|materials?|conditions?|walls?|blocks?)\s*$"
)
_FEEDSTOCK_PLURAL_SUFFIX = re.compile(r"(?i)\b(powder|feedstock)s\s*$")
_FEEDSTOCK_PRESENTATION_SUFFIX = re.compile(
    r"(?i)\s+(?:powders?|feedstocks?)\s*$"
)
_VARIANT_PRESENTATION_SUFFIX = re.compile(
    r"(?i)\s+(?:alloys?|versions?)\s*$"
)
_MANUFACTURING_DESCRIPTOR_PREFIX = re.compile(
    r"(?i)^\s*(?:(?:the|our)\s+)?"
    r"(?:(?:(?:additive(?:ly)?|laser|powder|bed|fusion|electron|beam|wire|arc|"
    r"directed|energy|deposition|lpbf|pbf|slm|ebm|ded|waam|am)[\s/\-]+)+)?"
    r"(?:fabricated|manufactured|printed|processed|produced)[\s:–—\-]+"
)
_SAMPLE_STATE_PREFIX = re.compile(
    r"(?i)^\s*(?:as[\s-]+(?:built|fabricated|deposited|printed|produced)|"
    r"additively[\s-]+manufactured)[\s:–—\-]+"
)
_CONTEXTUAL_SAMPLE_QUALIFIER = re.compile(
    r"(?i)\b(?:melt|build|fabricated|manufactured|printed)\b"
    r"(?=\s+(?:samples?|specimens?)\s*$)"
)
_NON_MATERIAL_PARENT_PATTERNS = (
    r"(?i)\s*/\s*[XYZ]\s*$",
    r"(?i)\s*\[\s*[XYZ]\s+orientation\s*\]\s*$",
    r"(?i)\s+(?:fabricated\s+samples?|fracture\s+surfaces?)\s*$",
    r"(?i)\s+orientation\s*$",
    r"(?i)\s+(?:oscillation\s+)?build(?:ing)?\s+strateg(?:y|ies)\s*$",
    r"(?i)\s*\(\s*(?:this|present)\s+(?:study|work)\s*\)\s*$",
)
_EXPLICIT_SLASH_ORIENTATION = re.compile(r"(?i)^(.+?)\s*/\s*([XYZ])\s*$")
_FEEDSTOCK_OWNER_PREFIX = re.compile(
    r"(?i)^\s*([A-Za-z][A-Za-z0-9_.+\-/]{1,30})\s+feedstocks?\b"
)
_GENERIC_MATERIAL_GROUP = re.compile(
    r"(?i)\b(?:samples?|specimens?|materials?)\s+"
    r"(?:made|fabricated|manufactured|printed|processed|produced)\s+by\b"
)
_NON_MATERIAL_LABELS = {
    "alloy",
    "alloy code",
    "angle",
    "average",
    "axis angle misorientation",
    "axis angle misorientation pairs",
    "axis angle type",
    "boride",
    "carbide",
    "crystal structure",
    "direction",
    "eds powder analysis",
    "experimental",
    "laser profile",
    "location",
    "manufacturer analysis",
    "material property",
    "morphology",
    "nominal composition",
    "orientation relationship",
    "phase composition",
    "phase",
    "phases",
    "powder",
    "powders",
    "porosity",
    "process",
    "quantity",
    "rate",
    "solid solution",
    "unit",
    "value",
    "feedstock",
    "feedstocks",
    "measured composition",
}
_MEASUREMENT_LABEL = re.compile(
    r"(?i)\b(?:average|avg\.?|change|current|corrosion\s+potential|pitting\s+potential|"
    r"passivation\s+current|d[\s-]*spacing|microhardness|(?:interlayer\s+)?delay(?:\s+time)?|density|diameter|"
    r"elongation|energy|flow\s+rate|frequency|hatch\s+distance|lattice\s+parameter|"
    r"layer\s+thickness|maximum\s+size|modulus|particle\s+size|roughness|"
    r"stress|strength|temperature|total\s+.*\bvf\b|uts|voltage|yield|ys)\b"
)
_PURE_NUMERIC_ID = re.compile(r"^[+-]?(?:\d+(?:\.\d+)?|\.\d+)$")
_TEST_OR_MICRO_SUBSAMPLE = re.compile(
    r"(?i)^(?:(?:fib|tem|apt|xrt|sem)[\s_-]*(?:sample|specimen|lamella|tip)"
    r"(?:[\s_-]*[A-Za-z0-9]+)*\b|"
    r"(?:sample|specimen)[\s_-]*(?:[ivxlcdm]+|\d+)\b|.+\s+specimen)$"
)
_MICROANALYSIS_LOCATION = re.compile(
    r"(?i)^(?:eds\s+)?(?:point|spot|area|location)\s*#?\s*[A-Za-z0-9._-]+$"
)
_MICROANALYSIS_LOCATION_SEARCH = re.compile(
    r"(?i)\b(?:eds\s+)?(point|spot|area|location)s?\s*#?\s*([A-Za-z0-9._-]+)"
)
_MICROANALYSIS_LOCATION_GROUP = re.compile(
    r"(?i)\b(point|spot|area|location)s?\s*#?\s*([A-Za-z0-9._-]+)"
    r"((?:\s*(?:,|and|&)\s*(?:(?:point|spot|area|location)s?\s*)?"
    r"#?\s*[A-Za-z0-9._-]+)+)"
)
_NUMERIC_MICROANALYSIS_LOCATION = re.compile(r"^[1-9]\d*$")
_MICROANALYSIS_METHOD = re.compile(
    r"(?i)\b(?:eds|edx|energy[\s-]+dispersive(?:[\s-]+x[\s-]*ray)?)\b"
)
_SOURCE_SAMPLE_NOUN = re.compile(
    r"(?i)\b(?:samples?|specimens?|materials?|powders?|feedstocks?)\b"
)
_SOURCE_STATE_QUALIFIER = re.compile(
    r"(?i)(?<![A-Za-z0-9])([-+]?\d+(?:\.\d+)?)\s*"
    r"(°\s*C|deg(?:ree)?s?\s*C|K|h|hr|hrs|hours?|min|mins|minutes?|"
    r"s|sec|seconds?)\b"
)
_CELSIUS_SERIES = re.compile(
    r"(?i)(?<![A-Za-z0-9])"
    r"([-+]?\d{2,4}(?:\.\d+)?(?:\s*(?:,|and|to|[-–—])\s*"
    r"[-+]?\d{2,4}(?:\.\d+)?)*)\s*"
    r"(?:°\s*C|deg(?:ree)?s?\s*C|\^?\s*\\circ\s*\{?\s*C\s*\}?)"
)
_SYNTHETIC_ROW_LABEL = re.compile(r"(?i)^.+[_-]row[_-]?\d+$")
_TABLE_OR_FIGURE_LABEL = re.compile(
    r"(?i)^(?:table|fig(?:ure)?)\s*[A-Za-z0-9._-]+"
    r"(?:\s+(?:row\s*\d+|samples?|specimens?|powders?|materials?|alloys?))?$"
)
_STRUCTURAL_ENTITY_STATE = re.compile(
    r"(?i)\b(?:phase|precipitate|carbide|boride|oxide|inclusion)\b"
)
_STRUCTURAL_LOCATION_STATE = re.compile(
    r"(?i)^\s*(?:interior|wall|matrix|interface|region|location|area|zone)\s*$"
)
_STRUCTURAL_PHASE_TOKEN = re.compile(
    r"(?i)\b(?:fcc|bcc|hcp|b2|l1[_{}₂2]*|sigma|gamma|delta|"
    r"α|β|γ|δ|σ)\b"
)
_STRUCTURAL_ENTITY_SUFFIX = re.compile(
    r"(?i)(?:\s+(?:phase|precipitate|carbide|boride|oxide|inclusion)){1,3}\s*$"
)
_CITATION_ONLY_LABEL = re.compile(
    r"(?ix)^\s*(?:"
    r"(?:[\w'’.-]+\s+){0,5}et\s+al\.?"
    r"(?:\s*,?\s*(?:\(?\d{4}[a-z]?\)?|\[[0-9,;\s-]+\]))?"
    r"|(?:[\w'’.-]+\s+){0,5}[\w'’.-]+\s*,?\s*\(?\d{4}[a-z]?\)?"
    r"|(?:literature|reference|ref\.?)"
    r"(?:\s+(?:sample|alloy|material|data))?\s*\[[0-9,;\s-]+\]"
    r")\s*$"
)
_CITATION_MARKER = re.compile(
    r"(?ix)(?:"
    r"\bet\s+al\.?(?:\s*,?\s*\d{4}[a-z]?)?"
    r"|\b[\w'’.-]+\s*,?\s*(?:19|20)\d{2}[a-z]?\b"
    r"|\[[0-9,;\s-]+\]\s*$"
    r")"
)
_CITED_NOMINAL_COMPOSITION_LABEL = re.compile(
    r"(?i)^\s*nominal\s+composition\s*\[[0-9,;\s-]+\]\s*$"
)
_NON_MATERIAL_CONTEXT_LABEL = re.compile(
    r"(?ix)^\s*(?:"
    r"(?:dft|density\s+functional\s+theory)"
    r"|(?:astm|iso|din|en|ams)\s*[-A-Z0-9][A-Z0-9./:()\s-]*"
    r"|(?:horizontal|vertical|transverse|longitudinal)"
    r"(?:\s+(?:sample|specimen|orientation|direction))?"
    r"|(?:failure|fracture|tensile|fatigue|creep|tested?)\s+(?:samples?|specimens?)"
    r"|(?:post[\s-]*(?:deformation|test)\s+)?(?:micro)?pillars?"
    r"|.+\b(?:phases?|precipitates?|nanoprecipitates?|regions?|bands?|films?)\b"
    r"(?:\s+post[\s-]*deformation)?"
    r")\s*$"
)
_DATASET_CONTEXT_LABEL = re.compile(
    r"(?i)\b(?:data\s*sets?|datasets?|training\s+set|validation\s+set|test\s+set)\b"
)
_COMPARISON_ONLY_VALUE = re.compile(
    r"(?i)\b(?:inferior|superior|higher|lower|greater|less|more|weaker|stronger|"
    r"better|worse|comparable|similar)\b|\bthan\b|\bcompared\s+(?:with|to)\b"
)
_STRUCTURAL_PROPERTY_SUBJECT = re.compile(
    r"(?i)\b(?:grains?|grain\s+boundaries?|phases?|precipitates?|particles?|"
    r"pores?|porosity|voids?|defects?|dislocations?|dendrites?|cells?|lamellae?|"
    r"laths?|colonies|textures?|interfaces?|inclusions?)\b"
)
_STRUCTURAL_PROPERTY_MEASUREMENT = re.compile(
    r"(?i)\b(?:size|diameter|radius|length|width|thickness|spacing|fraction|"
    r"density|number\s+density|aspect\s+ratio|area|volume|morphology|distribution|"
    r"equivalent\s+circle|circularity|misorientation)\b"
)
_CRYSTALLOGRAPHIC_STRUCTURE_PROPERTY = re.compile(
    r"(?i)\b(?:lattice\s+(?:parameter|constant|misfit)|"
    r"(?:interplanar\s+|d[\s-]*)spacing|diffraction\s+peak\s+position|"
    r"crystallographic\s+planes?|"
    r"peak\s+position(?:\s+for)?\s+crystallographic|"
    r"2\s*theta|2θ)\b"
)
_MATERIAL_RESPONSE_PROPERTY = re.compile(
    r"(?i)\b(?:strength|stress|strain|hardness|ductility|elongation|modulus|"
    r"toughness|fatigue|creep|conductivity|resistivity|corrosion)\b"
)
_CHART_POINT_PAIR = re.compile(
    r"(?:start|mid|end|min_y|max_y)\s*=\s*\(\s*"
    r"([+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?)\s*,\s*"
    r"([+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?)\s*\)",
    re.I,
)
_MORPHOLOGY_IDENTITY_DESCRIPTOR = re.compile(
    r"(?ix)^\s*(?:"
    r"spherical|near[\s-]*spherical|irregular(?:ly)?(?:[\s-]*shaped)?|"
    r"angular|elongated|dendritic|satellite(?:d)?"
    r")(?:\s+(?:shape|morphology))?(?:\s+(?:for|of)\s+.+)?\s*$"
)
_MATERIAL_IDENTITY_TERM = re.compile(
    r"(?i)\b(?:alloy|steel|superalloy|composite|nanocomposite|intermetallic|"
    r"metal|ceramic|titanium|aluminium|aluminum|nickel|cobalt|copper|"
    r"magnesium)\b"
)


def _claim_quality_mode() -> ClaimQualityMode:
    raw = os.getenv("KNOWMAT2_ALPHA25_CLAIM_QUALITY", "safe").strip().casefold()
    if raw in {"0", "false", "no", "off", "disabled"}:
        return "off"
    if raw in {"2", "strict", "full", "experimental"}:
        return "strict"
    # Preserve the former boolean-on contract while making the production-safe
    # behavior the default. Unknown truthy values also fail closed to ``safe``
    # instead of unexpectedly enabling experimental provenance-sensitive gates.
    return "safe"


def _claim_quality_enabled() -> bool:
    return _claim_quality_mode() != "off"


_ORIENTATION_CONTEXT_ONLY_EVIDENCE = re.compile(
    r"(?i)\b(?:fractur(?:e|ed|ing)|tested?|testing|orientation|direction)\b"
)
_STATE_OBSERVATION_CONTEXT = re.compile(
    r"(?ix)\b(?:"
    r"fracture\s+surfaces?"
    r"|(?:horizontal|vertical|transverse|longitudinal)\s+(?:orientation|direction)"
    r"|(?:after|post[\s-]*)\s*(?:a\s+)?(?:creep|fatigue|tensile|compression)?\s*"
    r"(?:test(?:ed|ing)?|deformation|deformed)"
    r"|(?:creep|fatigue|tensile|compression)[\s-]+(?:tested?|deformed)"
    r"|post[\s-]*deformation"
    r"|(?:un)?deformed\s+(?:samples?|specimens?)"
    r"|deformed\s+(?:to|by|at)\s*[-+~]?\d+(?:\.\d+)?\s*%\s*"
    r"(?:plastic\s+)?strain"
    r"|(?:micro)?pillars?"
    r"|(?:coarse|fine|melted?|cast)\s+regions?"
    r")\b"
)
_SAMPLE_OWNER_PREFIX = re.compile(
    r"(?i)^\s*([A-Za-z0-9][A-Za-z0-9_.+\-/]{0,30})\s+"
    r"(?:powders?|feedstocks?|samples?|specimens?)\b"
)
_UNRESOLVED_IDENTITY_PREFIX = re.compile(
    r"(?i)^\s*(?:n/?a|none|not[\s_-]*(?:reported|provided|available)|"
    r"unknown|unspecified)(?:\b|\s*\[)"
)
_PHASE_SYMBOL_ONLY = re.compile(
    r"(?i)^[\s$'′″_^{}()+\-/\\]*(?:\\+)?(?:alpha|beta|gamma|delta|sigma|"
    r"epsilon|lambda|α|β|γ|δ|σ|ε|λ)(?:\s*['′″]|\s*\d+)?[\s$'′″_^{}()+\-/\\]*$"
)
_MEASUREMENT_UNIT = re.compile(
    r"(?i)(?:\b(?:ev|gpa|kpa|mpa|ma|mv|kv|nm|mm|cm|um|µm|μm|ms|hz|"
    r"g/cc|s/50g)\b|%|\\mu|\\circ|\^\{?-?\d)"
)
_COMPACT_SOURCE_SAMPLE_ID = re.compile(r"^(?:#\s*\d+|\d+(?:[-_]\d+)+)$")
_EXPLICIT_STATE_ID = re.compile(
    r"(?i)^(?=.*\d)(?=.*\b(?:delay|dwell|hold|aged?|anneal(?:ed|ing)?|"
    r"heat[\s-]*treat(?:ed|ment)?|sinter(?:ed|ing)?|solution(?:ized|ing)?|"
    r"temperature|orientation|direction|condition|state|region)\b).{1,80}$"
)
_FORBIDDEN_PROCESS_PARAMETER_KEYS = {
    "test temperature",
    "gauge length",
    "specimen diameter",
    "tensile speed",
    "yield strength",
    "ultimate tensile strength",
    "elongation",
    "stress ratio",
    "number of cycles",
    "simulation time step",
}
_STATE_CATEGORY_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("hip", re.compile(r"(?i)\b(?:hip|hot\s+isostatic(?:ally)?\s+press(?:ed|ing)?)\b")),
    ("thermal_exposure", re.compile(r"(?i)\b(?:thermal(?:ly)?\s+expos(?:ed|ure)|expos(?:ed|ure))\b")),
    ("laser_region", re.compile(r"(?i)\b(?:laser\s+glaz(?:ed|ing)|melt(?:ed|ing)?\s+region)\b")),
    ("cast_region", re.compile(r"(?i)\b(?:cast(?:ing)?\s+region|as[\s-]*cast)\b")),
    ("solution_treated", re.compile(r"(?i)\bsolution(?:ized|ising|izing|\s+treat(?:ed|ment)?)\b")),
    (
        "heat_treated",
        re.compile(
            r"(?i)\b(?:ht|heat[\s-]*treat(?:ed|ment)?|"
            r"thermal(?:ly)?[\s-]+stabili[sz](?:ed|ation))\b"
        ),
    ),
    ("aged", re.compile(r"(?i)\b(?:aged?|ageing|aging)\b")),
    ("sintered", re.compile(r"(?i)\bsinter(?:ed|ing)?\b")),
    ("as_built", re.compile(r"(?i)\b(?:as[\s-]*(?:built|printed|fabricated|deposited|produced)|fabricated\s+by\s+(?:am|lpbf|pbf|slm|ebm|ded|waam))\b")),
    ("powder", re.compile(r"(?i)\b(?:powder|feedstock)\b")),
    ("rolled", re.compile(r"(?i)\broll(?:ed|ing)?\b")),
    ("wrought", re.compile(r"(?i)\bwrought\b")),
    ("deformed", re.compile(r"(?i)\b(?:deform(?:ed|ation)|creep[\s-]*deformed)\b")),
)
_STATE_QUALIFIER = re.compile(
    r"(?i)(?<![A-Za-z0-9])([-+]?\d+(?:\.\d+)?)\s*"
    r"(°?\s*c|k|h|hr|hrs|hours?|min|mins|minutes?|s|sec|seconds?|mpa|gpa|%)?"
)


def normalize_source_alias(value: Any) -> str:
    """Normalize presentation only; do not add material-specific aliases."""

    text = unicodedata.normalize("NFKC", str(value or ""))
    text = re.sub(
        r"\\(alpha|beta|gamma|delta|epsilon|lambda|sigma)\b",
        lambda match: match.group(1),
        text,
        flags=re.IGNORECASE,
    )
    for symbol, name in _GREEK_ALIAS_NAMES.items():
        text = text.replace(symbol, name).replace(symbol.upper(), name)
    text = text.casefold()
    return re.sub(r"[^a-z0-9]+", "", text)


def _state_descriptor(value: Any) -> tuple[str, tuple[str, ...]] | None:
    """Return a generic state category plus explicit numeric qualifiers."""

    text = unicodedata.normalize("NFKC", str(value or "")).strip()
    text = re.sub(
        r"\^?\s*\\circ\s*\{?\s*C\s*\}?",
        "°C",
        text,
        flags=re.IGNORECASE,
    )
    if not text:
        return None
    if _is_unresolved_alias(text):
        return None
    if _STATE_OBSERVATION_CONTEXT.search(text):
        return None
    category = next(
        (name for name, pattern in _STATE_CATEGORY_PATTERNS if pattern.search(text)),
        "",
    )
    qualifiers: list[str] = []
    for match in _STATE_QUALIFIER.finditer(text):
        number = match.group(1)
        unit = re.sub(r"\s+", "", str(match.group(2) or "").casefold())
        unit = {"hr": "h", "hrs": "h", "hour": "h", "hours": "h", "sec": "s", "seconds": "s", "minute": "min", "minutes": "min"}.get(unit, unit)
        qualifiers.append(number + unit)
    if not category:
        folded = re.sub(r"[^a-z0-9]+", " ", text.casefold()).strip()
        if not folded or folded in {"condition", "state", "sample", "specimen"}:
            return None
        category = "raw:" + folded
    return category, tuple(dict.fromkeys(qualifiers))


def _expand_distinct_state_anchors(
    anchors: Sequence[InventoryAnchor],
) -> tuple[list[InventoryAnchor], dict[str, set[str]]]:
    """Create a base identity plus stable IDs for 2+ explicit source states.

    The base identity is intentionally retained.  Facts that name only the
    base sample must have one deterministic home; aliasing that base to every
    state used to broadcast the same property/structure fact across all state
    items and caused multiplicative duplicates.
    """

    grouped: dict[str, list[InventoryAnchor]] = {}

    def base_label(anchor: InventoryAnchor) -> str:
        text = str(anchor.sample_id_raw or "").strip()
        owner = _SAMPLE_OWNER_PREFIX.match(text)
        return owner.group(1) if owner else text

    for anchor in anchors:
        grouped.setdefault(_identity_key(base_label(anchor)), []).append(anchor)
    expanded: list[InventoryAnchor] = []
    base_aliases: dict[str, set[str]] = {}

    for base_key, rows in grouped.items():
        described: list[
            tuple[InventoryAnchor, tuple[str, tuple[str, ...]]]
        ] = []
        for anchor in rows:
            descriptor = _state_descriptor(anchor.state_raw)
            # Providers sometimes copy the sample label into ``state_raw``.
            # That is an identity restatement, not a distinct material state.
            if (
                descriptor is None
                or (descriptor[0].startswith("raw:") and not descriptor[1])
                or _identity_key(anchor.state_raw) == _identity_key(base_label(anchor))
            ):
                continue
            described.append((anchor, descriptor))

        # A projected table may abbreviate a fully described prose state to a
        # numeric header such as ``200 h``.  Join that compact source label to
        # one explicit sibling state only when its qualifiers identify exactly
        # one candidate in the same base-sample family.
        explicit_descriptors = {
            descriptor
            for _, descriptor in described
            if not descriptor[0].startswith("raw:")
        }
        reconciled_described: list[
            tuple[InventoryAnchor, tuple[str, tuple[str, ...]]]
        ] = []
        for anchor, descriptor in described:
            category, qualifiers = descriptor
            if category.startswith("raw:") and qualifiers:
                matches = {
                    candidate
                    for candidate in explicit_descriptors
                    if set(qualifiers) <= set(candidate[1])
                }
                if len(matches) == 1:
                    descriptor = next(iter(matches))
            reconciled_described.append((anchor, descriptor))
        described = reconciled_described
        # A bare temperature/duration such as ``1030 °C/2 h`` is not, by
        # itself, proof of a distinct material identity. Keep it only when it
        # uniquely abbreviates an explicitly classified sibling state (for
        # example ``200 h`` beside ``thermal exposure for 200 h``).
        described = [
            (anchor, descriptor)
            for anchor, descriptor in described
            if not descriptor[0].startswith("raw:")
        ]

        by_category: dict[str, set[tuple[str, ...]]] = {}
        for _, descriptor in described:
            assert descriptor is not None
            category, qualifiers = descriptor
            if qualifiers:
                by_category.setdefault(category, set()).add(qualifiers)
            else:
                by_category.setdefault(category, set())

        record_buckets: dict[int, list[str]] = {}
        bucket_states: dict[str, list[str]] = {}
        for anchor, descriptor in described:
            assert descriptor is not None
            category, qualifiers = descriptor
            qualified = sorted(by_category.get(category) or set())
            if qualifiers:
                supersets = [
                    candidate
                    for candidate in qualified
                    if set(qualifiers) <= set(candidate)
                ]
                effective = (
                    max(supersets, key=lambda value: (len(value), value))
                    if supersets
                    else qualifiers
                )
                buckets = [category + "|" + ",".join(effective)]
            elif len(qualified) <= 1:
                effective = qualified[0] if qualified else ()
                buckets = [category + ("|" + ",".join(effective) if effective else "")]
            else:
                # An unqualified mention such as "heat-treated" is shared
                # context for every explicitly distinguished temperature/time.
                buckets = [category + "|" + ",".join(value) for value in qualified]
            record_buckets[id(anchor)] = buckets
            for bucket in buckets:
                bucket_states.setdefault(bucket, []).append(str(anchor.state_raw).strip())

        if len(bucket_states) < 2:
            expanded.extend(rows)
            continue

        display_base = min(
            (base_label(anchor) for anchor in rows),
            key=lambda value: (len(value), value.casefold()),
        )
        representative: dict[str, str] = {}
        for bucket, states in bucket_states.items():
            representative[bucket] = min(
                dict.fromkeys(states),
                key=lambda value: (
                    -len(_state_descriptor(value)[1]) if _state_descriptor(value) else 0,
                    len(value),
                    value.casefold(),
                ),
            )
        displays = {
            bucket: f"{display_base} [{representative[bucket]}]"
            for bucket in bucket_states
        }

        base_anchor = next(
            (anchor for anchor in rows if not str(anchor.state_raw or "").strip()),
            max(rows, key=lambda anchor: anchor.confidence),
        )
        expanded.append(
            base_anchor.model_copy(
                update={"sample_id_raw": display_base, "state_raw": None}
            )
        )

        for anchor in rows:
            buckets = record_buckets.get(id(anchor))
            if not buckets:
                continue
            for bucket in buckets:
                original = str(anchor.sample_id_raw).strip()
                base_aliases.setdefault(original, set()).add(displays[bucket])
                expanded.append(
                    anchor.model_copy(update={"sample_id_raw": displays[bucket]})
                )
    return expanded, base_aliases


@dataclass(frozen=True)
class MaterializeIssue:
    code: str
    sample_id_raw: str
    message: str
    severity: str = "review"
    path: str | None = None
    evidence: Any = None
    expected: Any = None
    actual: Any = None
    suggested_action: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "severity": self.severity,
            "path": self.path or f"items.{self.sample_id_raw}",
            "message": self.message,
            "evidence": self.evidence,
            "expected": self.expected,
            "actual": (
                self.actual
                if self.actual is not None
                else {"sample_id_raw": self.sample_id_raw}
            ),
            "suggested_action": self.suggested_action,
        }


@dataclass(frozen=True)
class MaterializationResult:
    document: dict[str, Any]
    issues: list[MaterializeIssue]


def _clean_for_signature(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            key: _clean_for_signature(child)
            for key, child in sorted(value.items())
            if key not in _ID_FIELDS | _EVIDENCE_FIELDS
            and child not in (None, "", [], {})
        }
    if isinstance(value, list):
        return [_clean_for_signature(child) for child in value]
    if isinstance(value, str):
        return " ".join(value.casefold().split())
    return value


def _signature(value: dict[str, Any]) -> str:
    return json.dumps(
        _clean_for_signature(value), ensure_ascii=False, sort_keys=True, default=str
    )


def _evidence(value: Any) -> list[str]:
    if isinstance(value, str):
        value = [value]
    if not isinstance(value, list):
        return []
    return [str(row).strip() for row in value if str(row).strip()]


def _union_evidence(target: dict[str, Any], incoming: dict[str, Any]) -> None:
    rows = _evidence(target.get("source_evidence"))
    for row in _evidence(incoming.get("source_evidence")):
        if row not in rows:
            rows.append(row)
    if rows:
        target["source_evidence"] = rows
    if "confidence" in target or "confidence" in incoming:
        target["confidence"] = max(
            float(target.get("confidence") or 0),
            float(incoming.get("confidence") or 0),
        )


def _merge_record(target: dict[str, Any], incoming: dict[str, Any]) -> None:
    _union_evidence(target, incoming)
    for key, value in incoming.items():
        if key in _EVIDENCE_FIELDS:
            continue
        if key not in target or target[key] in (None, "", [], {}):
            target[key] = deepcopy(value)
        elif isinstance(target[key], dict) and isinstance(value, dict):
            _merge_record(target[key], value)


def _deduplicate(records: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    merged: dict[str, dict[str, Any]] = {}
    order: list[str] = []
    for record in records:
        row = deepcopy(record)
        signature = _signature(row)
        if signature not in merged:
            merged[signature] = row
            order.append(signature)
        else:
            _merge_record(merged[signature], row)
    return [merged[key] for key in order]


def _fact_data(fact: AxisFact) -> dict[str, Any]:
    data = deepcopy(fact.data)
    evidence = list(fact.source_evidence)
    if fact.fact_type in {
        "composition_observation",
        "process_stage",
        "structure_observation",
        "characterization",
        "property",
    }:
        # The fact envelope is the validated source of truth for grounding.
        # Providers sometimes duplicate this field inside ``data`` as a
        # scalar string even though the alpha25 candidate requires a list.
        # Always replace that untyped duplicate with the already validated
        # envelope value instead of preserving a schema-invalid shape.
        data["source_evidence"] = evidence
    if fact.fact_type == "process_edge":
        data["source_evidence"] = " | ".join(evidence)
    if fact.fact_type in {"process_stage", "property"}:
        data["confidence"] = fact.confidence
    return data


def _first_present(row: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        value = row.get(key)
        if value not in (None, "", [], {}):
            return value
    return None


def _value_kind(value: Any, *, structure: bool = False) -> str:
    text = str(value or "").strip()
    allowed = _STRUCTURE_VALUE_KINDS if structure else _COMPOSITION_VALUE_KINDS
    if not text:
        return "text" if structure else "unknown"
    lowered = text.casefold()
    if not structure and lowered in {"bal", "bal.", "balance", "remainder"}:
        return "balance"
    if re.match(r"^(?:<=|>=|<|>|≤|≥)", text):
        return "inequality"
    if re.search(r"\d\s*(?:-|–|—|to)\s*\d", text, re.I):
        return "range"
    if re.fullmatch(r"[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?", text):
        return "scalar"
    fallback = "text" if structure else "categorical"
    return fallback if fallback in allowed else next(iter(allowed))


def _sanitize_composition_observation(row: dict[str, Any]) -> dict[str, Any] | None:
    components: list[dict[str, Any]] = []
    for raw_component in row.get("components") or []:
        if not isinstance(raw_component, dict):
            continue
        name = _first_present(
            raw_component,
            "name_raw",
            "element",
            "component",
            "name",
            "phase_name_raw",
        )
        raw_value = _first_present(
            raw_component,
            "value_raw",
            "amount_raw",
            "amount_value",
        )
        if name in (None, "") or raw_value in (None, ""):
            continue
        if (
            raw_component.get("data_nature") == "derived"
            and not isinstance(raw_component.get("normalization"), dict)
        ):
            # Never relabel an unsupported LLM calculation as reported merely
            # to satisfy the schema. Alpha25 requires deterministic provenance.
            continue
        kind = str(raw_component.get("value_kind") or "").strip().casefold()
        if kind not in _COMPOSITION_VALUE_KINDS:
            kind = _value_kind(raw_value)
        inferred_kind = _value_kind(raw_value)
        if kind in {"inequality", "range"} and inferred_kind != kind:
            kind = inferred_kind
        evidence = _evidence(raw_component.get("source_evidence"))
        normalized_value: Any = None
        text_value = str(raw_value).strip()
        if kind == "balance":
            normalized_value = "Balance"
        elif kind == "inequality":
            match = re.match(
                r"^\s*(<=|>=|<|>|≤|≥)\s*([+-]?(?:\d+(?:\.\d*)?|\.\d+))",
                text_value,
            )
            if match:
                normalized_value = {
                    "operator": {"≤": "<=", "≥": ">="}.get(
                        match.group(1), match.group(1)
                    ),
                    "value": float(match.group(2)),
                }
        elif kind == "range":
            match = re.search(
                r"([+-]?(?:\d+(?:\.\d*)?|\.\d+))\s*(?:-|–|—|to)\s*"
                r"([+-]?(?:\d+(?:\.\d*)?|\.\d+))",
                text_value,
                re.I,
            )
            if match:
                normalized_value = {
                    "min": float(match.group(1)),
                    "max": float(match.group(2)),
                }
        component: dict[str, Any] = {
            "name_raw": str(name).strip(),
            "canonical_name": raw_component.get("canonical_name"),
            "value_kind": kind,
            "value_raw": raw_value,
            "value": normalized_value,
            "unit_raw": _first_present(raw_component, "unit_raw", "amount_unit"),
            "canonical_unit": None,
            "data_nature": (
                raw_component.get("data_nature")
                if raw_component.get("data_nature") in {"reported", "derived", "inferred"}
                else "reported"
            ),
        }
        if kind == "balance":
            component["balance_basis"] = "explicit_remainder"
        if evidence:
            component["source_evidence"] = evidence
        components.append(component)
    if not components:
        return None

    source_type = str(row.get("source_type") or "").strip().casefold()
    if source_type not in _COMPOSITION_SOURCE_TYPES:
        source_type = "measured" if row.get("measurement") else "provided"
    basis = str(row.get("basis") or "").strip()
    if basis not in _COMPOSITION_BASES:
        units = {
            str(component.get("unit_raw") or "").strip()
            for component in components
            if str(component.get("unit_raw") or "").strip() in _COMPOSITION_BASES
        }
        basis = next(iter(units)) if len(units) == 1 else "unknown"
    component_type = str(row.get("component_type") or "").strip().casefold()
    if component_type not in _COMPOSITION_COMPONENT_TYPES:
        component_type = (
            "elemental"
            if all(_is_element_symbol(component["name_raw"]) for component in components)
            else "unknown"
        )
    evidence = _evidence(row.get("source_evidence"))
    data_source = str(row.get("data_source") or "").strip().casefold()
    if data_source not in _COMPOSITION_DATA_SOURCES:
        data_source = "unknown"
    elif data_source == "external_reference":
        # Alpha25 reserves ``external_reference`` for an explicitly declared
        # web/standards lookup linked through Composition.External_References.
        # Production extraction does not perform such lookups: every accepted
        # quote has already been verified against the current paper. Models can
        # nevertheless use this label for a literature alloy mentioned in the
        # paper. Preserve that grounded observation as text provenance instead
        # of emitting an unlinked external observation that is schema-fatal.
        # An observation without current-paper evidence is not safe to relabel.
        if not evidence:
            return None
        data_source = "text"
    raw_expression = str(row.get("raw_expression") or "").strip()
    if not raw_expression:
        raw_expression = " | ".join(evidence)
    if not raw_expression:
        return None
    sanitized = {
        "observation_id": str(row.get("observation_id") or "temporary"),
        "source_type": source_type,
        "material_state": str(row.get("material_state") or "not_reported"),
        "sample_id": str(row.get("sample_id") or "not_reported"),
        "basis": basis,
        "component_type": component_type,
        "components": components,
        "measurement": row.get("measurement"),
        "raw_expression": raw_expression,
        "data_source": data_source,
        "source_evidence": evidence,
        "note": row.get("note"),
    }
    if row.get("_microanalysis_owner_recovered") is True:
        # Internal routing marker only.  It survives composition splitting and
        # deduplication, then is consumed before the public document is built.
        sanitized["_microanalysis_owner_recovered"] = True
    return sanitized


def _composition_raw_unit_family(value: Any) -> tuple[str, str] | None:
    """Return the official alpha25 unit family and canonical raw unit."""

    if not isinstance(value, str) or not value.strip():
        return None
    key = re.sub(r"\s+", "", value.strip().casefold())
    aliases = {
        "wt%": ("mass", "wt%"),
        "wt.%": ("mass", "wt%"),
        "wt-%": ("mass", "wt%"),
        "wt.-%": ("mass", "wt%"),
        "wt(%)": ("mass", "wt%"),
        "wt.(%)": ("mass", "wt%"),
        "w%": ("mass", "wt%"),
        "weight%": ("mass", "wt%"),
        "mass%": ("mass", "wt%"),
        "massfraction": ("mass", "mass_fraction"),
        "weightfraction": ("mass", "mass_fraction"),
        "g/kg": ("mass", "g/kg"),
        "mg/g": ("mass", "mg/g"),
        "ppm": ("mass", "ppm"),
        "ppm.": ("mass", "ppm"),
        "ppmw": ("mass", "ppm_w"),
        "ppm(wt)": ("mass", "ppm_w"),
        "ppm(wt%)": ("mass", "ppm_w"),
        "ppb": ("mass", "ppb"),
        "ppbw": ("mass", "ppb_w"),
        "mg/kg": ("mass", "ppm"),
        "µg/g": ("mass", "ppm"),
        "μg/g": ("mass", "ppm"),
        "ug/g": ("mass", "ppm"),
        "at%": ("atomic", "at%"),
        "at.%": ("atomic", "at%"),
        "at(%)": ("atomic", "at%"),
        "at.(%)": ("atomic", "at%"),
        "atomic%": ("atomic", "at%"),
        "atomicfraction": ("atomic", "atomic_fraction"),
        "ppma": ("atomic", "ppm_a"),
        "ppm(at)": ("atomic", "ppm_a"),
        "ppba": ("atomic", "ppb_a"),
        "vol%": ("volume", "vol%"),
        "vol.%": ("volume", "vol%"),
        "volume%": ("volume", "vol%"),
        "volumefraction": ("volume", "volume_fraction"),
        "mol%": ("molar", "mol%"),
        "mol.%": ("molar", "mol%"),
        "mole%": ("molar", "mol%"),
        "molar%": ("molar", "mol%"),
        "molefraction": ("molar", "mol%"),
        "amountfraction": ("molar", "mol%"),
        "formularatio": ("molar", "formula_ratio"),
        "formula_ratio": ("molar", "formula_ratio"),
    }
    return aliases.get(key)


def _partition_wrong_axis_composition_components(
    observation: dict[str, Any],
) -> tuple[dict[str, Any] | None, list[dict[str, Any]]]:
    """Separate explicit non-composition measurements from component amounts."""

    components = observation.get("components") or []
    if not isinstance(components, list):
        return observation, []
    explicit_basis = str(observation.get("basis") or "").strip()
    invalid_basis = bool(
        explicit_basis
        and explicit_basis != "unknown"
        and explicit_basis not in _COMPOSITION_BASES
        and _composition_raw_unit_family(explicit_basis) is None
    )
    kept: list[dict[str, Any]] = []
    quarantined: list[dict[str, Any]] = []
    for component in components:
        if not isinstance(component, dict):
            continue
        value = str(
            _first_present(component, "value_raw", "amount_raw", "amount_value")
            or ""
        ).strip()
        unit = str(
            _first_present(component, "unit_raw", "amount_unit") or ""
        ).strip()
        numeric = bool(re.search(r"[+-]?(?:\d+(?:\.\d*)?|\.\d+)", value))
        unit_missing = not unit or bool(re.search(r"[A-Za-z0-9]", unit)) and (
            _is_unresolved_alias(unit)
        )
        wrong_unit = bool(
            not unit_missing and _composition_raw_unit_family(unit) is None
        )
        if numeric and (wrong_unit or (invalid_basis and unit_missing)):
            quarantined.append(deepcopy(component))
        else:
            kept.append(deepcopy(component))
    if not quarantined:
        return observation, []
    if not kept:
        return None, quarantined
    cleaned = deepcopy(observation)
    cleaned["components"] = kept
    if invalid_basis:
        cleaned["basis"] = "unknown"
    return cleaned, quarantined


def _composition_basis_for_units(family: str, units: set[str]) -> str:
    if family == "mass":
        if units and units <= {"ppm", "ppm_w", "ppb", "ppb_w"}:
            return "mass_trace"
        if "wt%" in units:
            return "wt%"
        return "mass_fraction"
    if family == "atomic":
        if units and units <= {"ppm_a", "ppb_a"}:
            return "atomic_trace"
        if "at%" in units:
            return "at%"
        return "atomic_fraction"
    if family == "volume":
        return "vol%" if "vol%" in units else "volume_fraction"
    if family == "molar":
        return "formula_ratio" if units == {"formula_ratio"} else "mol%"
    return "unknown"


def _split_mixed_composition_observation(
    observation: dict[str, Any],
) -> list[dict[str, Any]]:
    """Split incompatible reported unit families without changing any fact."""

    grouped: dict[str, list[dict[str, Any]]] = {}
    canonical_units: dict[str, set[str]] = {}
    unknown: list[dict[str, Any]] = []
    for component in observation.get("components") or []:
        resolved = _composition_raw_unit_family(component.get("unit_raw"))
        if resolved is None:
            unknown.append(component)
            continue
        family, canonical = resolved
        grouped.setdefault(family, []).append(component)
        canonical_units.setdefault(family, set()).add(canonical)
    if len(grouped) <= 1:
        return [observation]

    split: list[dict[str, Any]] = []
    for family, components in grouped.items():
        row = deepcopy(observation)
        row["components"] = components
        row["basis"] = _composition_basis_for_units(
            family, canonical_units.get(family, set())
        )
        split.append(row)
    if unknown:
        row = deepcopy(observation)
        row["components"] = unknown
        row["basis"] = "unknown"
        split.append(row)
    return split


def _sanitize_structure_feature(
    row: dict[str, Any], fallback_evidence: Sequence[str]
) -> dict[str, Any] | None:
    name = _first_present(
        row,
        "feature_name_raw",
        "feature_name",
        "feature_type",
        "description_raw",
    )
    raw_value = _first_present(
        row,
        "value_raw",
        "feature_value_raw",
        "description_raw",
        "raw_note",
    )
    if name in (None, "") or raw_value in (None, ""):
        return None
    kind = str(row.get("value_kind") or "").strip().casefold()
    if kind not in _STRUCTURE_VALUE_KINDS:
        kind = _value_kind(raw_value, structure=True)
    nature = str(row.get("data_nature") or "").strip().casefold()
    if nature not in _STRUCTURE_DATA_NATURES:
        nature = "reported"
    normalization = row.get("normalization")
    has_derived_provenance = (
        isinstance(normalization, dict)
        and isinstance(normalization.get("rule_id"), str)
        and bool(normalization["rule_id"].strip())
        and isinstance(normalization.get("formula"), str)
        and bool(normalization["formula"].strip())
        and isinstance(normalization.get("source_fields"), list)
        and bool(normalization["source_fields"])
        and all(
            isinstance(value, str) and bool(value.strip())
            for value in normalization["source_fields"]
        )
    )
    if nature == "derived" and not has_derived_provenance:
        # A provider may label an author-reported number as "derived" without
        # supplying the calculation required by the v11 contract. Do not
        # relabel it as reported or let one unsupported feature make the whole
        # paper fatal; retain the surrounding observation and supported facts.
        return None
    evidence = _evidence(row.get("source_evidence")) or list(fallback_evidence)
    if not evidence:
        return None
    result: dict[str, Any] = {
        "feature_name_raw": str(name).strip(),
        "value_kind": kind,
        "value_raw": raw_value,
        "data_nature": nature,
        "source_evidence": evidence,
    }
    if nature == "derived":
        result["normalization"] = deepcopy(normalization)
    text_value = str(raw_value).strip()
    if kind == "inequality":
        match = re.match(
            r"^\s*(<=|>=|<|>|≤|≥)\s*([+-]?(?:\d+(?:\.\d*)?|\.\d+))",
            text_value,
        )
        if match:
            result["qualifier"] = {"≤": "<=", "≥": ">="}.get(
                match.group(1), match.group(1)
            )
            result["bound_value"] = float(match.group(2))
        else:
            result["value_kind"] = "text"
    elif kind == "range":
        plus_minus = re.search(
            r"([+-]?(?:\d+(?:\.\d*)?|\.\d+))\s*(?:±|\\pm)\s*"
            r"([+-]?(?:\d+(?:\.\d*)?|\.\d+))",
            text_value,
        )
        endpoints = re.search(
            r"([+-]?(?:\d+(?:\.\d*)?|\.\d+))\s*(?:-|–|—|to)\s*"
            r"([+-]?(?:\d+(?:\.\d*)?|\.\d+))",
            text_value,
            re.I,
        )
        if plus_minus:
            result["value_kind"] = "scalar"
            result["value"] = float(plus_minus.group(1))
            result["value_stddev"] = float(plus_minus.group(2))
        elif endpoints:
            result["value_min"] = float(endpoints.group(1))
            result["value_max"] = float(endpoints.group(2))
        else:
            result["value_kind"] = "text"
    for key in (
        "canonical_name",
        "value",
        "value_stddev",
        "bound_value",
        "value_min",
        "value_max",
        "qualifier",
        "unit_raw",
        "canonical_unit",
        "measurement_basis",
    ):
        if row.get(key) not in (None, "", [], {}):
            result[key] = deepcopy(row[key])
    return result


def _sanitize_structure_entity(
    row: dict[str, Any], fallback_evidence: Sequence[str], entity_index: int
) -> dict[str, Any] | None:
    name = _first_present(
        row,
        "name_raw",
        "entity_name_raw",
        "entity_name",
        "phase_name_raw",
        "phase",
        "raw_description",
    )
    if name in (None, ""):
        return None
    evidence = _evidence(row.get("source_evidence")) or list(fallback_evidence)
    if not evidence:
        return None
    nested_features = [
        sanitized
        for feature in row.get("features") or []
        if isinstance(feature, dict)
        and (sanitized := _sanitize_structure_feature(feature, evidence)) is not None
    ]
    entity_type = str(row.get("entity_type") or "other").strip().casefold()
    # Regions and locations are observation context, not independent scientific
    # entities.  Keeping an empty ``CP region``/``wall`` entity makes the final
    # claim projection manufacture a categorical presence claim.  A quantitative
    # feature still preserves the row as a real structural observation.
    if _claim_quality_enabled() and not nested_features and (
        entity_type in {"area", "location", "region", "zone"}
        or _STRUCTURAL_LOCATION_STATE.fullmatch(str(name).strip())
    ):
        return None
    raw_expression = _first_present(row, "raw_expression", "raw_description") or name
    return {
        "entity_id": str(
            _first_present(row, "entity_id", "entity_id_candidate")
            or f"entity_{entity_index:03d}"
        ),
        "entity_type": entity_type,
        "role": str(_first_present(row, "role", "role_raw") or "reported"),
        "name_raw": str(name).strip(),
        "canonical_name": row.get("canonical_name"),
        "features": nested_features,
        "raw_expression": str(raw_expression).strip(),
        "source_evidence": evidence,
    }


def _sanitize_structure_observation(row: dict[str, Any]) -> dict[str, Any] | None:
    evidence = _evidence(row.get("source_evidence"))
    if not evidence:
        return None
    original = str(row.get("original") or "").strip() or " | ".join(evidence)
    simplified = str(row.get("simplified") or "").strip() or original
    entities = [
        sanitized
        for index, entity in enumerate(row.get("entities") or [], start=1)
        if isinstance(entity, dict)
        and (
            sanitized := _sanitize_structure_entity(entity, evidence, index)
        )
        is not None
    ]
    features = [
        sanitized
        for feature in row.get("features") or []
        if isinstance(feature, dict)
        and (sanitized := _sanitize_structure_feature(feature, evidence)) is not None
    ]
    kind = str(row.get("structure_kind") or "").strip().casefold()
    if kind not in _STRUCTURE_KINDS:
        kind = "other"
    source_type = str(row.get("source_type") or "").strip().casefold()
    if source_type not in _STRUCTURE_SOURCE_TYPES:
        source_type = "reported"
    if not entities and not features:
        return None
    return {
        "observation_id": str(row.get("observation_id") or "temporary"),
        "structure_kind": kind,
        "material_state": str(row.get("material_state") or "not_reported"),
        "sample_id": str(row.get("sample_id") or "not_reported"),
        "source_type": source_type,
        "original": original,
        "simplified": simplified,
        "entities": entities,
        "features": features,
        "source_evidence": evidence,
    }


def _sanitize_parameters(value: Any, stage_evidence: Sequence[str]) -> list[dict[str, Any]]:
    if isinstance(value, dict):
        raw_rows: list[Any] = [
            {"parameter_name_raw": key, "value_raw": child}
            for key, child in value.items()
        ]
    elif isinstance(value, str):
        raw_rows = []
        for part in value.split(";"):
            name, separator, raw_value = part.partition(":")
            if separator and name.strip() and raw_value.strip():
                raw_rows.append(
                    {"parameter_name_raw": name.strip(), "value_raw": raw_value.strip()}
                )
    elif isinstance(value, list):
        raw_rows = value
    else:
        raw_rows = []
    fallback = " | ".join(stage_evidence)
    parameters: list[dict[str, Any]] = []
    for raw in raw_rows:
        if not isinstance(raw, dict):
            continue
        name = str(raw.get("parameter_name_raw") or "").strip()
        raw_value = raw.get("value_raw")
        evidence = " | ".join(_evidence(raw.get("source_evidence"))) or fallback
        if not name or raw_value in (None, "") or not evidence:
            continue
        normalized_name = re.sub(r"[_\-]+", " ", name).casefold()
        normalized_name = re.sub(r"\s+", " ", normalized_name).strip()
        if any(
            re.search(rf"\b{re.escape(forbidden)}\b", normalized_name)
            for forbidden in _FORBIDDEN_PROCESS_PARAMETER_KEYS
        ):
            # alpha25 classifies these as test/specimen/property leakage, not
            # stage-local process parameters. The exact phrase remains in the
            # stage evidence, so filtering the invalid slot loses no citation.
            continue
        parameter = {
            "parameter_name_raw": name,
            "value_raw": str(raw_value).strip(),
            "unit_raw": raw.get("unit_raw"),
            "source_evidence": evidence,
        }
        unit_raw = str(parameter.get("unit_raw") or "").strip()
        if re.fullmatch(r"\^?\\?circ\s*C", unit_raw, re.I):
            parameter["unit_raw"] = "°C"
        if raw.get("confidence") is not None:
            parameter["confidence"] = raw["confidence"]
        if raw.get("condition_label_raw"):
            parameter["condition_label_raw"] = raw["condition_label_raw"]
        parameters.append(parameter)
    return parameters


def _sanitize_property(row: dict[str, Any]) -> dict[str, Any] | None:
    value_raw = str(row.get("value_raw") or "").strip()
    if not value_raw:
        return None
    result = deepcopy(row)
    specimen = str(result.get("test_specimen_raw") or "").strip()
    condition = str(result.get("test_condition_raw") or "").strip()
    if specimen and (not condition or _is_unresolved_alias(condition)):
        # alpha25 normalizes specimen_raw inside Test_Condition. Reuse the exact
        # reported specimen phrase so the condition cannot contradictorily be
        # labelled not_reported while containing that raw detail.
        result["test_condition_raw"] = specimen
    return result


def _composition_component_to_structure_observation(
    component: dict[str, Any], observation: dict[str, Any], sample_id: str
) -> dict[str, Any] | None:
    """Move an unambiguous phase/structural measurement out of Composition."""

    name = str(
        _first_present(component, "name_raw", "component", "name") or ""
    ).strip()
    unit = str(
        _first_present(component, "unit_raw", "amount_unit") or ""
    ).strip()
    value = str(
        _first_present(component, "value_raw", "amount_raw", "amount_value")
        or ""
    ).strip()
    normalized_unit = re.sub(r"\s+", "", unit.casefold())
    is_fraction = normalized_unit in {"%", "vol%", "vol.%"}
    is_size = normalized_unit in {"nm", "um", "µm", "μm", "mm", "å"}
    if (
        not name
        or not value
        or not _STRUCTURAL_PROPERTY_SUBJECT.search(name)
        or not (is_fraction or is_size)
    ):
        return None
    evidence = _evidence(observation.get("source_evidence"))
    if not evidence:
        return None
    lowered = name.casefold()
    if "grain" in lowered:
        structure_kind = "grain_structure"
    elif "precipitat" in lowered or "particle" in lowered:
        structure_kind = "precipitate"
    elif "por" in lowered or "void" in lowered:
        structure_kind = "porosity"
    elif "phase" in lowered:
        structure_kind = "phase_assemblage"
    elif "texture" in lowered:
        structure_kind = "texture"
    else:
        structure_kind = "other"
    feature_name = f"{name} {'fraction' if is_fraction else 'size'}"
    return {
        "observation_id": "temporary",
        "structure_kind": structure_kind,
        "material_state": str(observation.get("material_state") or "not_reported"),
        "sample_id": sample_id,
        "source_type": "reported",
        "original": str(observation.get("raw_expression") or " | ".join(evidence)),
        "simplified": f"{feature_name}: {value} {unit}".strip(),
        "entities": [],
        "features": [
            {
                "feature_name_raw": feature_name,
                "value_kind": _value_kind(value, structure=True),
                "value_raw": value,
                "unit_raw": unit,
                "data_nature": str(component.get("data_nature") or "reported"),
                "source_evidence": evidence,
            }
        ],
        "source_evidence": evidence,
    }


def _property_to_structure_observation(
    row: dict[str, Any], sample_id: str
) -> dict[str, Any] | None:
    """Reclassify an unambiguous structural measurement from Properties."""

    name = str(row.get("property_name_raw") or "").strip()
    normalized_name = re.sub(r"[_-]+", " ", name)
    is_crystallographic = bool(
        _CRYSTALLOGRAPHIC_STRUCTURE_PROPERTY.search(normalized_name)
    )
    if (
        not name
        or not (
            is_crystallographic
            or (
                _STRUCTURAL_PROPERTY_SUBJECT.search(name)
                and _STRUCTURAL_PROPERTY_MEASUREMENT.search(name)
            )
        )
        or _MATERIAL_RESPONSE_PROPERTY.search(name)
    ):
        return None
    value = str(row.get("value_raw") or "").strip()
    evidence = _evidence(row.get("source_evidence"))
    if not value or not evidence:
        return None
    lowered = name.casefold()
    if "grain" in lowered:
        structure_kind = "grain_structure"
    elif "precipitat" in lowered or "particle" in lowered:
        structure_kind = "precipitate"
    elif "por" in lowered or "void" in lowered:
        structure_kind = "porosity"
    elif "texture" in lowered:
        structure_kind = "texture"
    elif "defect" in lowered or "dislocation" in lowered:
        structure_kind = "defect"
    elif "interface" in lowered or "boundary" in lowered:
        structure_kind = "interface"
    elif is_crystallographic:
        structure_kind = "phase_assemblage"
    else:
        structure_kind = "other"
    unit = str(row.get("unit_raw") or "").strip()
    simplified = f"{name}: {value}" + (f" {unit}" if unit else "")
    return {
        "observation_id": "temporary",
        "structure_kind": structure_kind,
        "material_state": str(row.get("test_condition_raw") or "not_reported"),
        "sample_id": sample_id,
        "source_type": "reported",
        "original": " | ".join(evidence),
        "simplified": simplified,
        "entities": [],
        "features": [
            {
                "feature_name_raw": name,
                "value_kind": _value_kind(value, structure=True),
                "value_raw": value,
                "unit_raw": unit or None,
                "data_nature": "reported",
                "source_evidence": evidence,
            }
        ],
        "source_evidence": evidence,
    }


def _chart_series_csv_references(source_text: str | None) -> dict[str, str]:
    """Map bounded series summaries to their preserved CSV within one block."""

    if not source_text:
        return {}
    candidates: dict[str, set[str]] = {}
    pending_series: list[str] = []
    for raw_line in source_text.splitlines():
        line = raw_line.strip()
        if line.startswith("> [Figure"):
            pending_series = []
        if line.startswith("series:") and "key_points=" in line:
            pending_series.append(line)
            continue
        if not line.startswith("data_csv:"):
            continue
        csv_reference = line.split(":", 1)[1].strip()
        if csv_reference and csv_reference.casefold() != "unavailable":
            for series in pending_series:
                candidates.setdefault(series, set()).add(csv_reference)
        pending_series = []
    return {
        series: next(iter(references))
        for series, references in candidates.items()
        if len(references) == 1
    }


def _invalid_nonnegative_chart_series(
    row: dict[str, Any],
    *,
    chart_csv_references: dict[str, str] | None = None,
) -> dict[str, Any] | None:
    """Return a bounded audit summary for an invalid cached chart series."""

    name = str(row.get("property_name_raw") or "").casefold()
    method = str(row.get("test_method_raw") or "").casefold()
    unit = re.sub(r"\s+", "", str(row.get("unit_raw") or "").casefold())
    tensile_quantity = (
        ("tensile" in name or "tensile" in method)
        and bool(re.search(r"\b(?:strength|stress|yield|uts|sigma)\b", name))
        and unit in {"pa", "kpa", "mpa", "gpa"}
    )
    if not tensile_quantity:
        return None
    evidence = _evidence(row.get("source_evidence"))
    chart_rows = [line for line in evidence if "series:" in line and "key_points=" in line]
    if not chart_rows:
        return None
    values = [
        float(match.group(2))
        for line in chart_rows
        for match in _CHART_POINT_PAIR.finditer(line)
    ]
    if not values:
        return None
    tolerance = max(1.0, max(abs(value) for value in values) * 0.01)
    minimum = min(values)
    if minimum >= -tolerance:
        return None
    csv_reference = next(
        (
            line.split("data_csv:", 1)[1].strip()
            for line in evidence
            if "data_csv:" in line
        ),
        None,
    )
    if csv_reference is None and chart_csv_references:
        mapped_references = {
            chart_csv_references[line.strip()]
            for line in chart_rows
            if line.strip() in chart_csv_references
        }
        if len(mapped_references) == 1:
            csv_reference = next(iter(mapped_references))
    return {
        "series_evidence": chart_rows,
        "observed_minimum": minimum,
        "observed_maximum": max(values),
        "negative_tolerance": tolerance,
        "data_csv": csv_reference,
        "property": deepcopy(row),
    }


def _explicit_process_graph_is_valid(
    stage_ids: set[str], edges: Sequence[dict[str, Any]]
) -> bool:
    """Accept non-linear edges only when they describe a complete real DAG."""

    explicit = [
        edge
        for edge in edges
        if edge.get("edge_type") in {"branch", "merge", "parallel"}
    ]
    if not explicit:
        return True
    incoming = {stage_id: [] for stage_id in stage_ids}
    outgoing = {stage_id: [] for stage_id in stage_ids}
    undirected = {stage_id: set() for stage_id in stage_ids}
    for edge in edges:
        source = edge.get("source_candidate_stage_id")
        target = edge.get("target_candidate_stage_id")
        if source not in stage_ids or target not in stage_ids:
            return False
        outgoing[source].append(edge)
        incoming[target].append(edge)
        undirected[source].add(target)
        undirected[target].add(source)
    if stage_ids:
        pending = [next(iter(stage_ids))]
        visited: set[str] = set()
        while pending:
            current = pending.pop()
            if current in visited:
                continue
            visited.add(current)
            pending.extend(undirected[current] - visited)
        if visited != stage_ids:
            return False
    if not any(
        len(outgoing[stage_id]) > 1 or len(incoming[stage_id]) > 1
        for stage_id in stage_ids
    ):
        return False
    for edge in explicit:
        source = edge["source_candidate_stage_id"]
        target = edge["target_candidate_stage_id"]
        edge_type = edge["edge_type"]
        if edge_type == "branch" and len(outgoing[source]) <= 1:
            return False
        if edge_type == "merge" and len(incoming[target]) <= 1:
            return False
        if edge_type == "parallel" and (
            len(outgoing[source]) <= 1 and len(incoming[target]) <= 1
        ):
            return False
    return all(
        all(edge["edge_type"] in {"branch", "parallel"} for edge in outgoing[stage_id])
        for stage_id in stage_ids
        if len(outgoing[stage_id]) > 1
    ) and all(
        all(edge["edge_type"] in {"merge", "parallel"} for edge in incoming[stage_id])
        for stage_id in stage_ids
        if len(incoming[stage_id]) > 1
    )


def _text_pair(records: Sequence[dict[str, Any]], *, nullable: bool) -> dict[str, Any]:
    originals: list[str] = []
    simplified: list[str] = []
    for record in records:
        original = record.get("original")
        simple = record.get("simplified")
        if isinstance(original, str) and original.strip() and original not in originals:
            originals.append(original.strip())
        if isinstance(simple, str) and simple.strip() and simple not in simplified:
            simplified.append(simple.strip())
    if originals or simplified:
        return {
            "original": "\n".join(originals) or None,
            "simplified": "\n".join(simplified) or None,
        }
    if nullable:
        return {"original": None, "simplified": None}
    return {"original": "not_reported", "simplified": "not_reported"}


def _route_value(routing: dict[str, Any], key: str, fallback: str) -> str:
    value = str(routing.get(key) or "").strip()
    return value or fallback


def _is_element_symbol(value: Any) -> bool:
    text = unicodedata.normalize("NFKC", str(value or "")).strip()
    # Source sample codes are commonly all-uppercase (CL, FE, IN).  Chemical
    # symbols have canonical title-case spelling, so case-folding here silently
    # discarded legitimate identities that happened to collide with an element.
    return text in _ELEMENT_SYMBOLS and len(text) <= 2


def _is_unresolved_alias(value: Any) -> bool:
    return normalize_source_alias(value) in _UNRESOLVED_ALIASES


def _strip_identity_suffix(value: Any) -> str:
    text = unicodedata.normalize("NFKC", str(value or "")).strip()
    while True:
        stripped = _IDENTITY_SUFFIX.sub("", text).strip()
        if stripped == text:
            return stripped
        text = stripped


def _identity_key(value: Any) -> str:
    text = _strip_identity_suffix(value)
    # Singular/plural feedstock wording is presentation-only. Do not erase the
    # feedstock state here: ``X powder`` remains distinct from ``X`` unless the
    # paper inventory also supplies that exact base identity and the conservative
    # parent redirect below can prove the relationship.
    text = _FEEDSTOCK_PLURAL_SUFFIX.sub(r"\1", text)
    return normalize_source_alias(text)


def _identity_alias_keys(value: Any) -> tuple[str, ...]:
    """Return conservative presentation variants for one source identity.

    Manufacturing phrases describe how a material was made, not a distinct
    sample identity.  Keeping this normalization here lets an inventory label
    such as ``LPBF-fabricated X alloy`` match ``X alloy`` in another chunk while
    preserving meaningful state prefixes such as ``heat-treated``.
    """

    text = unicodedata.normalize("NFKC", str(value or "")).strip()
    variants = [_identity_key(text)]
    stripped = _MANUFACTURING_DESCRIPTOR_PREFIX.sub("", text, count=1).strip()
    if stripped and stripped != text:
        variants.append(_identity_key(stripped))
    return tuple(dict.fromkeys(key for key in variants if key))


def _qualified_sample_base_key(value: Any) -> str:
    """Return the unqualified base of an explicitly qualified sample label.

    The qualifier is presentation context only when it occurs immediately
    before a terminal ``sample`` or ``specimen`` noun.  Returning an empty key
    for all other labels keeps this rule from weakening ordinary identity
    matching.
    """

    text = unicodedata.normalize("NFKC", str(value or "")).strip()
    stripped = _CONTEXTUAL_SAMPLE_QUALIFIER.sub("", text).strip()
    if not stripped or stripped == text:
        return ""
    return _identity_key(stripped)


def _variant_presentation_key(value: Any) -> str:
    """Normalize an explicit variant label without erasing material names.

    ``high boron alloy`` and ``high boron`` are presentation variants, whereas
    ``reference alloy`` is too generic to shorten safely.  This helper is used
    only when two source anchors also share a material descriptor.
    """

    text = unicodedata.normalize("NFKC", str(value or "")).strip()
    stripped = _VARIANT_PRESENTATION_SUFFIX.sub("", text).strip()
    words = re.findall(r"[A-Za-z0-9]+", stripped)
    if stripped != text and (len(words) >= 2 or "-" in stripped):
        return _identity_key(stripped)
    return _identity_key(text)


def _source_initialism(value: Any) -> str:
    """Return a conservative initialism for a multiword source label."""

    text = unicodedata.normalize("NFKC", str(value or "")).strip()
    stripped = _VARIANT_PRESENTATION_SUFFIX.sub("", text).strip()
    words = re.findall(r"[A-Za-z0-9]+", stripped)
    if len(words) < 2 or any(word.isdigit() for word in words):
        return ""
    return "".join(word[0] for word in words).casefold()


def _ocr_confusable_key(value: Any) -> str:
    """Fold a narrow letter-O/digit-zero OCR ambiguity for paired aliases."""

    return _identity_key(value).replace("o", "0")


def _presentation_parent_text(value: Any) -> str:
    """Strip presentation-only qualifiers while preserving source wording."""

    original = unicodedata.normalize("NFKC", str(value or "")).strip()
    text = original
    changed = True
    while changed:
        changed = False
        for pattern in _NON_MATERIAL_PARENT_PATTERNS:
            stripped = re.sub(pattern, "", text).strip()
            if stripped and stripped != text:
                text = stripped
                changed = True
    state_stripped = _SAMPLE_STATE_PREFIX.sub("", text, count=1).strip()
    if state_stripped:
        text = state_stripped
    return text if text and text != original else ""


def _composition_source_parent_text(value: Any) -> str:
    """Strip a terminal measured/nominal composition column annotation.

    ``(M)`` and ``(N)`` distinguish composition sources in many tables; they do
    not rename the material or a prepared state.  Preserve a trailing generated
    state suffix so the same rule works for both ``T5 (M)`` and
    ``T5 (M) [heat-treated]`` without model-, paper-, or material-specific
    aliases.
    """

    text = unicodedata.normalize("NFKC", str(value or "")).strip()
    state_suffix = ""
    state_match = re.match(r"(?s)^(.*?)\s*(\[[^\[\]]+\])\s*$", text)
    if state_match:
        text, state_suffix = state_match.groups()
    compact_tex = re.sub(r"\^\s*\{?\s*[A-Za-z0-9]+\s*\}?\s*\$?\s*$", "", text)
    compact_tex = compact_tex.strip(" $\\")
    match = re.match(r"(?is)^(.+?)\s*\(\s*[MN]\s*\)\s*$", compact_tex)
    if not match:
        return ""
    parent = match.group(1).strip(" $\\")
    return f"{parent} {state_suffix}".strip()


def _existing_identity_parent(value: Any) -> str:
    """Return a source label's base identity for non-material qualifiers."""

    text = unicodedata.normalize("NFKC", str(value or "")).strip()
    parent_text = _presentation_parent_text(text)
    if parent_text:
        return _identity_key(parent_text)

    feedstock_parent = _FEEDSTOCK_PRESENTATION_SUFFIX.sub("", text).strip()
    if feedstock_parent and feedstock_parent != text:
        return _identity_key(feedstock_parent)

    trailing_sample = re.match(
        r"(?i)^.+\bsamples?\s+([A-Za-z][A-Za-z0-9_.+-]{0,20})\s*$", text
    )
    if trailing_sample:
        return _identity_key(trailing_sample.group(1))

    # The caller still requires the extracted base identity to exist in the
    # same paper inventory before applying this presentation-only redirect.
    composition_parent = _composition_source_parent_text(text)
    return _identity_key(composition_parent) if composition_parent else ""


def _anchor_is_structural_entity(anchor: InventoryAnchor) -> bool:
    """Reject provider-created material anchors that explicitly name phases."""

    state = str(anchor.state_raw or "")
    sample_raw = unicodedata.normalize(
        "NFKC", str(anchor.sample_id_raw or "")
    )
    material_raw = unicodedata.normalize(
        "NFKC", str(anchor.material_name_raw or "")
    )
    location_subentity = bool(
        _STRUCTURAL_LOCATION_STATE.fullmatch(state)
        and normalize_source_alias(state) in normalize_source_alias(sample_raw)
        and (
            _STRUCTURAL_ENTITY_STATE.search(material_raw)
            or (
                re.search(r"(?i)\bmatrix\b", material_raw)
                and _STRUCTURAL_PHASE_TOKEN.search(sample_raw + " " + material_raw)
            )
        )
    )
    if not _STRUCTURAL_ENTITY_STATE.search(state) and not location_subentity:
        return False
    sample = _identity_key(anchor.sample_id_raw)
    material = _identity_key(anchor.material_name_raw)
    entity_base = _STRUCTURAL_ENTITY_SUFFIX.sub(
        "", unicodedata.normalize("NFKC", str(anchor.material_name_raw or ""))
    ).strip()
    sample_compact = re.sub(
        r"[^a-z0-9]+",
        "",
        unicodedata.normalize("NFKC", str(anchor.sample_id_raw or "")).casefold(),
    )
    entity_compact = re.sub(
        r"[^a-z0-9]+", "", entity_base.casefold()
    )
    compact_structural_name = bool(
        sample_compact
        and entity_compact
        and (
            sample_compact == entity_compact
            or re.fullmatch(
                re.escape(entity_compact) + r"(?:(?:row|index)?\d+|[a-z])",
                sample_compact,
            )
        )
    )
    sample_words = re.sub(
        r"[^a-z0-9]+",
        " ",
        unicodedata.normalize("NFKC", str(anchor.sample_id_raw or "")).casefold(),
    ).strip()
    material_words = re.sub(
        r"[^a-z0-9]+",
        " ",
        unicodedata.normalize("NFKC", str(anchor.material_name_raw or "")).casefold(),
    ).strip()
    structural_name = bool(
        sample_words
        and material_words
        and re.fullmatch(
            re.escape(sample_words)
            + r"\s+(?:(?:phase|precipitate|carbide|boride|oxide|inclusion)\s*){1,3}",
            material_words,
        )
    )
    # A real composite/sample can mention an oxide in its material name.  The
    # unsafe case is the phase/entity itself (or a synthetic row label) being
    # promoted to the sample identity.  Providers also commonly return a phase
    # formula as ``sample_id_raw`` and restate it as ``<formula> carbide`` or
    # ``<formula> boride phase`` in ``material_name_raw``; that explicit
    # source relationship is structural, not a material-item identity.
    return bool(
        location_subentity
        or
        _SYNTHETIC_ROW_LABEL.fullmatch(str(anchor.sample_id_raw or "").strip())
        or (sample and material and (sample == material or sample.startswith(material + "row")))
        or structural_name
        or compact_structural_name
    )


def _anchor_is_explicit_state_sample(anchor: InventoryAnchor) -> bool:
    """Return whether an otherwise metric-like label is a declared sample state.

    Numeric state labels such as ``120 s Delay`` are also measurement-shaped, so
    the generic non-material filter rejects them in isolation.  An inventory row
    is stronger evidence: retain the label only when the provider copied the same
    explicit state into ``state_raw`` and supplied a plausible parent material.
    This does not legalize bare table headers or test conditions as material items.
    """

    sample = str(anchor.sample_id_raw or "").strip()
    state = str(anchor.state_raw or "").strip()
    material = str(anchor.material_name_raw or "").strip()
    if not (
        sample
        and state
        and material
        and _EXPLICIT_STATE_ID.fullmatch(sample)
        and is_plausible_material_identity(material)
    ):
        return False
    sample_descriptor = _state_descriptor(sample)
    state_descriptor = _state_descriptor(state)
    return bool(
        sample_descriptor is not None
        and state_descriptor is not None
        and sample_descriptor == state_descriptor
    )


def _citation_owner(anchor: InventoryAnchor) -> tuple[InventoryAnchor | None, str]:
    """Move citation-labelled reference facts to their named material owner."""

    sample = str(anchor.sample_id_raw or "").strip()
    is_literature_reference = (
        anchor.role == "Reference"
        and str(anchor.data_nature or "").startswith("Literature_")
    )
    if not is_literature_reference or not (
        _CITATION_ONLY_LABEL.fullmatch(sample) or _CITATION_MARKER.search(sample)
    ):
        return anchor, ""
    material = str(anchor.material_name_raw or "").strip()
    if (
        not material
        or _CITATION_ONLY_LABEL.fullmatch(material)
        or _CITATION_MARKER.search(material)
        or _identity_key(material) == _identity_key(sample)
        or not is_plausible_material_identity(material)
    ):
        return None, ""
    return anchor.model_copy(update={"sample_id_raw": material}), sample


def _looks_like_composition_designation(value: Any) -> bool:
    text = unicodedata.normalize("NFKC", str(value or ""))
    symbols = {
        match.group(1).casefold()
        for match in re.finditer(r"(?<![A-Za-z])([A-Z][a-z]?)(?=\s*[-_]?\s*\d)", text)
        if match.group(1).casefold() in _ELEMENT_SYMBOL_KEYS
    }
    return len(symbols) >= 2


def _is_non_material_label(value: Any) -> bool:
    """Reject table metrics, structure entities, and process slots as item IDs."""

    text = unicodedata.normalize("NFKC", str(value or "")).strip()
    folded = re.sub(r"[^a-z0-9]+", " ", text.casefold()).strip()
    if not folded or folded in _NON_MATERIAL_LABELS:
        return True
    if _DATASET_CONTEXT_LABEL.search(text):
        return True
    if (
        _PURE_NUMERIC_ID.fullmatch(text)
        or _TEST_OR_MICRO_SUBSAMPLE.fullmatch(text)
        or _MICROANALYSIS_LOCATION.fullmatch(text)
        or _SYNTHETIC_ROW_LABEL.fullmatch(text)
        or _TABLE_OR_FIGURE_LABEL.fullmatch(text)
        or _NON_MATERIAL_CONTEXT_LABEL.fullmatch(text)
    ):
        return True
    if _PHASE_SYMBOL_ONLY.fullmatch(text):
        return True
    if re.search(r"(?i)\be\s*[_{}-]*\s*(?:corr|pit)\b", text):
        return True
    if _GENERIC_MATERIAL_GROUP.search(text) or re.search(r"(?i)\blimits?\s*$", text):
        return True
    if re.fullmatch(
        r"(?i)\d+\s+(?:age(?:ing|d)?|age\s+hardening|anneal(?:ing|ed)?|solution\s+treatment|"
        r"heat\s+treatment|sinter(?:ing|ed)?)",
        text,
    ):
        return True
    if re.fullmatch(
        r"(?i)[+-]?(?:\d+(?:\.\d+)?|\.\d+)\s*(?:s|sec(?:onds?)?|ms|"
        r"v|kv|a|ma|w|kw|pa|mpa|gpa|hz|mm|nm|µm|μm)",
        text,
    ):
        return True
    composition = _looks_like_composition_designation(text)
    if _MEASUREMENT_LABEL.search(text) and not composition:
        return True
    if (
        ("$" in text or "\\" in text)
        and _MEASUREMENT_UNIT.search(text)
        and not composition
    ):
        return True
    if re.search(r"(?i)\b(?:at|wt|vol)\.?\s*%", text) and not composition:
        return True
    return False


def _is_generic_material_class(value: Any) -> bool:
    """Reject unanchored plural material classes, not named sample identities."""

    text = unicodedata.normalize(
        "NFKC", _strip_identity_suffix(value)
    ).casefold().strip()
    if any(character.isdigit() for character in text):
        return False
    words = re.findall(r"[a-z]+", text)
    return bool(words and words[-1] in _GENERIC_MATERIAL_WORDS)


def _combined_parts(value: Any) -> list[str]:
    text = unicodedata.normalize("NFKC", str(value or "")).strip()
    if not text:
        return []
    parts = re.split(r"\s+(?:and|versus|vs\.?)\s+|\s*[;&]\s*", text, flags=re.I)
    cleaned = [part.strip(" ,()[]") for part in parts if part.strip(" ,()[]")]
    return cleaned if len(cleaned) > 1 else []


def is_plausible_material_identity(value: Any) -> bool:
    """Return whether a source label can safely anchor a material item."""

    text = str(value or "").strip()
    if _UNRESOLVED_IDENTITY_PREFIX.match(text):
        return False
    if _COMPACT_SOURCE_SAMPLE_ID.fullmatch(text) or _EXPLICIT_STATE_ID.fullmatch(text):
        return True
    return bool(_identity_key(text)) and not (
        _is_unresolved_alias(text)
        or _is_element_symbol(text)
        or _is_non_material_label(text)
        or _combined_parts(text)
        or _is_generic_material_class(text)
    )


class _IdentityIndex:
    """Evidence-derived aliases with primary sample IDs protected from collisions."""

    def __init__(self) -> None:
        self.labels: dict[str, Counter[str]] = {}
        self.alias_targets: dict[str, set[str]] = {}
        self.state_alias_targets: dict[str, set[str]] = {}
        self.state_descriptor_targets: dict[
            tuple[str, tuple[str, ...]], set[str]
        ] = {}
        self.state_family_base: dict[str, str] = {}
        self.anchors: dict[str, list[InventoryAnchor]] = {}

    @property
    def primary_aliases(self) -> set[str]:
        return set(self.labels)

    def add_primary(self, value: Any) -> str | None:
        text = str(value or "").strip()
        alias = _identity_key(text)
        if not is_plausible_material_identity(text):
            return None
        self.labels.setdefault(alias, Counter())[text] += 1
        return alias

    def add_anchor(self, anchor: InventoryAnchor) -> None:
        canonical = self.add_primary(anchor.sample_id_raw)
        if canonical is not None:
            self.anchors.setdefault(canonical, []).append(anchor)

    def add_anchor_as(self, anchor: InventoryAnchor, canonical: str) -> None:
        text = str(anchor.sample_id_raw or "").strip()
        if not canonical or not is_plausible_material_identity(text):
            return
        self.labels.setdefault(canonical, Counter())[text] += 1
        self.anchors.setdefault(canonical, []).append(anchor)

    def add_alias(self, value: Any, canonical: str) -> None:
        if _is_unresolved_alias(value):
            return
        for alias in _identity_alias_keys(value):
            if alias == canonical:
                continue
            # A source-declared sample ID is authoritative. A noisy
            # material_name_raw must never collapse one primary sample into a
            # differently suffixed one.
            if alias in self.primary_aliases and alias != canonical:
                continue
            self.alias_targets.setdefault(alias, set()).add(canonical)

    def bind_unique_alias(self, value: Any, canonical: str) -> None:
        """Bind a proven one-to-one alias ahead of ambiguous descriptors."""

        if _is_unresolved_alias(value):
            return
        for alias in _identity_alias_keys(value):
            if alias == canonical:
                continue
            if alias in self.primary_aliases and alias != canonical:
                continue
            self.alias_targets[alias] = {canonical}

    def add_state_alias(self, value: Any, canonical: str) -> None:
        alias = normalize_source_alias(value)
        if alias and len(alias) >= 3:
            self.state_alias_targets.setdefault(alias, set()).add(canonical)
        descriptor = _state_descriptor(value)
        if descriptor is not None:
            self.state_descriptor_targets.setdefault(descriptor, set()).add(canonical)

    def add_state_family(self, canonical: str, base: str) -> None:
        if canonical and base and canonical != base:
            self.state_family_base[canonical] = base

    def resolve_state_family_base(self, targets: Iterable[str]) -> tuple[str, ...]:
        bases = {self.state_family_base.get(target, target) for target in targets}
        return tuple(bases) if len(bases) == 1 else ()

    def resolve_state_label(self, value: Any) -> tuple[str, ...]:
        """Resolve a source state label only when it names one inventory item."""

        descriptor = _state_descriptor(value)
        if descriptor is None:
            return ()
        category, qualifiers = descriptor
        if qualifiers:
            targets = set(self.state_descriptor_targets.get(descriptor, set()))
        else:
            targets = {
                target
                for (candidate_category, _), rows in self.state_descriptor_targets.items()
                if candidate_category == category
                for target in rows
            }
        return tuple(targets) if len(targets) == 1 else ()

    def resolve_exact(self, value: Any) -> tuple[str, ...]:
        alias = _identity_key(value)
        if not alias:
            return ()
        if alias in self.primary_aliases:
            return (alias,)
        targets = {
            target
            for variant in _identity_alias_keys(value)
            for target in self.alias_targets.get(variant, set())
        }
        if not targets:
            owner = _FEEDSTOCK_OWNER_PREFIX.match(str(value or ""))
            if owner:
                owner_key = _identity_key(owner.group(1))
                if owner_key in self.primary_aliases:
                    targets.add(owner_key)
                targets.update(self.alias_targets.get(owner_key, set()))
        return tuple(sorted(targets))

    def resolve_label(self, value: Any) -> tuple[str, ...]:
        exact = self.resolve_exact(value)
        if exact:
            return exact
        parts = _combined_parts(value)
        if not parts:
            return ()
        targets: list[str] = []
        for part in parts:
            resolved = self.resolve_exact(part)
            if not resolved:
                return ()
            for target in resolved:
                if target not in targets:
                    targets.append(target)
        return tuple(targets)

    def resolve_evidence(self, evidence: Iterable[str]) -> tuple[str, ...]:
        """Find non-overlapping, longest known aliases in copied evidence."""

        aliases: dict[str, tuple[str, ...]] = {
            canonical: (canonical,) for canonical in self.labels
        }
        for alias, targets in self.alias_targets.items():
            if targets:
                aliases[alias] = tuple(sorted(targets))
        matches: list[tuple[int, int, int, tuple[str, ...]]] = []
        for row in evidence:
            normalized = normalize_source_alias(row)
            if not normalized:
                continue
            for alias, canonical_targets in aliases.items():
                if len(alias) < 3:
                    continue
                start = normalized.find(alias)
                while start >= 0:
                    matches.append(
                        (-(len(alias)), start, start + len(alias), canonical_targets)
                    )
                    start = normalized.find(alias, start + 1)
        occupied: list[tuple[int, int]] = []
        targets: list[str] = []
        for _, start, end, canonical_targets in sorted(matches):
            if any(start < used_end and end > used_start for used_start, used_end in occupied):
                continue
            occupied.append((start, end))
            for canonical in canonical_targets:
                if canonical not in targets:
                    targets.append(canonical)
        return tuple(targets)

    def resolve_state_evidence(self, evidence: Iterable[str]) -> tuple[str, ...]:
        qualified_rows: list[set[str]] = []
        generic_targets: set[str] = set()
        for row in evidence:
            normalized = normalize_source_alias(row)
            if not normalized:
                continue
            row_qualified: set[str] = set()
            # Use the same category/qualifier normalization that registered
            # inventory states. This resolves grammatical variants such as
            # "sintering temperature 1225 °C" against "sintered at 1225 °C"
            # without relying on brittle substring equality.
            descriptor = _state_descriptor(row)
            if descriptor is not None:
                row_qualified.update(
                    self.state_descriptor_targets.get(descriptor, set())
                )
            for (category, qualifiers), canonical_targets in (
                self.state_descriptor_targets.items()
            ):
                category_key = normalize_source_alias(category.removeprefix("raw:"))
                qualifier_keys = [normalize_source_alias(value) for value in qualifiers]
                if (
                    qualifiers
                    and category_key
                    and category_key in normalized
                    and all(value and value in normalized for value in qualifier_keys)
                ):
                    row_qualified.update(canonical_targets)
            for alias, canonical_targets in self.state_alias_targets.items():
                if alias in normalized:
                    generic_targets.update(canonical_targets)
            if row_qualified:
                qualified_rows.append(row_qualified)
        qualified_targets: set[str] = set()
        if qualified_rows:
            intersection = set.intersection(*qualified_rows)
            qualified_targets = intersection or set.union(*qualified_rows)
        targets = qualified_targets or generic_targets
        return tuple(sorted(targets))

    def display_label(self, canonical: str) -> str:
        labels = self.labels.get(canonical) or Counter({canonical: 1})
        # A composition table can repeat measured/nominal columns many more
        # times than it repeats the actual sample heading. Frequency must not
        # let ``T5 (M)`` replace the source-backed base label ``T5``. Only
        # suppress the annotated forms when an unannotated label for this exact
        # canonical identity is present; otherwise a literal source sample that
        # happens to contain parentheses remains unchanged.
        unannotated = Counter(
            {
                label: count
                for label, count in labels.items()
                if not _composition_source_parent_text(label)
            }
        )
        display_labels = unannotated or labels
        source_codes = [
            label
            for label in display_labels
            if re.fullmatch(r"[A-Za-z]{2,6}", label)
            and any(
                other != label
                and _source_initialism(other) == label.casefold()
                for other in display_labels
            )
        ]
        if source_codes:
            return min(
                source_codes,
                key=lambda label: (
                    -display_labels[label],
                    len(label),
                    label.casefold(),
                ),
            )
        selected = min(
            display_labels,
            key=lambda label: (
                -display_labels[label],
                _identity_key(label) != canonical,
                len(re.sub(r"[A-Za-z0-9]", "", label)),
                len(label),
                label.casefold(),
            ),
        )
        parent_text = _presentation_parent_text(selected)
        if parent_text and _identity_key(parent_text) == canonical:
            return parent_text
        return selected


def _fact_identity_labels(fact: AxisFact) -> list[str]:
    data = fact.data
    if fact.fact_type in {"composition_observation", "structure_observation"}:
        value = str(data.get("sample_id") or "").strip()
        return [value] if value else []
    if fact.fact_type == "material_identity":
        return [
            str(value).strip()
            for value in (data.get("designation_raw"), data.get("material_name_raw"))
            if str(value or "").strip()
        ]
    return []


def _owner_agnostic_fact_signature(fact: AxisFact) -> str:
    """Return a semantic signature that excludes copied owner presentation."""

    # The current cache carries enough condition/value provenance for property
    # aliases, but not enough table coordinates for composition, processing, or
    # structure. Keep those axes on the proven exact signature to avoid merging
    # distinct rows that merely look semantically alike.
    if _claim_quality_enabled() and isinstance(fact, PropertyFact):
        return semantic_fact_signature(fact)
    data = deepcopy(fact.data)
    for key in ("sample_id", "sample_id_raw", "material_name_raw", "designation_raw"):
        data.pop(key, None)
    return f"{fact.fact_type}:{_signature(data)}"


def _fact_primary_owners(index: _IdentityIndex, fact: AxisFact) -> set[str]:
    owners: set[str] = set()
    for label in [*_fact_identity_labels(fact), fact.sample_id_raw]:
        if _identity_key(label) in index.primary_aliases:
            owners.update(index.resolve_exact(label))
    return owners


def _fact_material_state_label(fact: AxisFact) -> str:
    """Return an observation-local material state, never a test condition."""

    if fact.fact_type not in {"composition_observation", "structure_observation"}:
        return ""
    value = str(fact.data.get("material_state") or "").strip()
    return "" if _is_unresolved_alias(value) else value


def _register_fact_local_states(
    index: _IdentityIndex, facts: Sequence[AxisFact]
) -> None:
    """Index uniquely owned material states copied inside observations.

    Projected tables can preserve a state in ``material_state`` even when no
    inventory row repeats that column header.  Register that state only against
    one already source-backed material family.  Raw numeric temperature/time
    labels are accepted here because the schema field itself declares material
    state; the same strings remain insufficient when they occur as bare headers.
    """

    candidates: dict[
        tuple[str, tuple[str, tuple[str, ...]]], list[tuple[AxisFact, str]]
    ] = {}
    for fact in facts:
        state = _fact_material_state_label(fact)
        descriptor = _state_descriptor(state)
        if descriptor is None:
            continue
        if re.search(
            r"(?i)\b(?:creep|fatigue|tensile|compression|strain|deform|fractur)\w*\b",
            state,
        ):
            # Post-test/deformation context remains on the observation itself;
            # it does not define another independently prepared material item.
            continue
        category, qualifiers = descriptor
        if category.startswith("raw:") and not qualifiers:
            continue
        owners = {
            target
            for label in [*_fact_identity_labels(fact), fact.sample_id_raw]
            for target in index.resolve_exact(label)
        }
        if len(owners) != 1:
            continue
        owner = next(iter(owners))
        base = index.state_family_base.get(owner, owner)
        candidates.setdefault((base, descriptor), []).append((fact, state))

    for (base, descriptor), rows in sorted(candidates.items()):
        existing = {
            target
            for target in index.state_descriptor_targets.get(descriptor, set())
            if index.state_family_base.get(target, target) == base
        }
        if len(existing) == 1:
            continue
        if existing:
            # Multiple pre-existing state items with one normalized descriptor
            # are ambiguous; an observation-local restatement cannot pick one.
            continue
        fact, state = min(
            rows,
            key=lambda row: (
                len(str(row[1])),
                str(row[1]).casefold(),
                -float(row[0].confidence),
            ),
        )
        base_anchors = index.anchors.get(base, [])
        if not base_anchors:
            continue
        parent = max(base_anchors, key=lambda anchor: anchor.confidence)
        display = f"{index.display_label(base)} [{state}]"
        canonical = index.add_primary(display)
        if canonical is None:
            continue
        index.add_anchor_as(
            InventoryAnchor(
                sample_id_raw=display,
                material_name_raw=parent.material_name_raw,
                state_raw=state,
                role=parent.role,
                data_nature=parent.data_nature,
                source_evidence=list(fact.source_evidence),
                confidence=fact.confidence,
            ),
            canonical,
        )
        index.add_state_alias(state, canonical)
        index.add_state_family(canonical, base)


def _build_identity_index(
    anchors: Sequence[InventoryAnchor], facts: Sequence[AxisFact]
) -> _IdentityIndex:
    index = _IdentityIndex()
    citation_aliases: list[tuple[str, str]] = []
    non_material_owner_aliases: list[InventoryAnchor] = []
    reassigned_anchors: list[InventoryAnchor] = []
    for anchor in anchors:
        reassigned, citation_label = _citation_owner(anchor)
        if reassigned is None:
            continue
        reassigned_anchors.append(reassigned)
        if citation_label:
            citation_aliases.append(
                (citation_label, str(reassigned.sample_id_raw or "").strip())
            )
    anchors = reassigned_anchors
    # Filter the provider's original label before state expansion. Otherwise a
    # forbidden identity such as ``FIB-sample-A`` can become superficially
    # plausible after ``[state]`` is appended. Precompute the forbidden keys so
    # a deterministic table anchor with the same label cannot resurrect a phase,
    # region, method, or test-piece identity rejected from another chunk.
    explicit_state_keys = {
        _identity_key(anchor.sample_id_raw)
        for anchor in anchors
        if _anchor_is_explicit_state_sample(anchor)
    }
    non_material_keys = {
        _identity_key(anchor.sample_id_raw)
        for anchor in anchors
        if (
            _is_non_material_label(anchor.sample_id_raw)
            and _identity_key(anchor.sample_id_raw) not in explicit_state_keys
        )
        or _anchor_is_structural_entity(anchor)
    }
    material_anchors: list[InventoryAnchor] = []
    for anchor in anchors:
        if _identity_key(anchor.sample_id_raw) in non_material_keys:
            non_material_owner_aliases.append(anchor)
            continue
        if is_plausible_material_identity(anchor.sample_id_raw):
            material_anchors.append(anchor)
    anchors = material_anchors
    anchors, state_base_aliases = _expand_distinct_state_anchors(anchors)
    expanded_base_keys = {
        _identity_key(base_label) for base_label in state_base_aliases
    }
    candidate_keys = {
        _identity_key(anchor.sample_id_raw)
        for anchor in anchors
        if is_plausible_material_identity(anchor.sample_id_raw)
    }
    candidate_roles: dict[str, set[str]] = {}
    for anchor in anchors:
        sample_key = _identity_key(anchor.sample_id_raw)
        role = str(anchor.role or "").strip().casefold()
        if sample_key and role and not _is_unresolved_alias(role):
            candidate_roles.setdefault(sample_key, set()).add(role)
    redirects: dict[str, str] = {}

    # Slash-qualified rows are sometimes explicit source specimen IDs rather
    # than prose orientation context.  Protect them only when the inventory
    # independently names at least two siblings under the same parent (for
    # example ``EPBF / X`` and ``EPBF / Z``).  A lone slash qualifier retains
    # the historical presentation-only merge behavior.
    orientation_siblings: dict[str, set[str]] = {}
    for anchor in anchors:
        match = _EXPLICIT_SLASH_ORIENTATION.fullmatch(
            str(anchor.sample_id_raw or "").strip()
        )
        if not match:
            continue
        parent_key = _identity_key(match.group(1))
        sample_key = _identity_key(anchor.sample_id_raw)
        if parent_key in candidate_keys and sample_key:
            orientation_siblings.setdefault(parent_key, set()).add(sample_key)
    independent_fact_keys = {
        _identity_key(label)
        for fact in facts
        if fact.fact_type != "material_identity"
        and not all(
            _ORIENTATION_CONTEXT_ONLY_EVIDENCE.search(evidence)
            for evidence in fact.source_evidence
        )
        for label in [fact.sample_id_raw, *_fact_identity_labels(fact)]
        if label
    }
    protected_orientation_keys = {
        sample_key
        for siblings in orientation_siblings.values()
        if len(siblings & independent_fact_keys) >= 2
        for sample_key in siblings
    }

    global_variants: dict[str, set[str]] = {}
    for anchor in anchors:
        sample_key = _identity_key(anchor.sample_id_raw)
        variant_key = _variant_presentation_key(anchor.sample_id_raw)
        if sample_key and variant_key:
            global_variants.setdefault(variant_key, set()).add(sample_key)
        parent_key = _existing_identity_parent(anchor.sample_id_raw)
        if (
            parent_key
            and parent_key in candidate_keys
            and sample_key != parent_key
            and sample_key not in protected_orientation_keys
        ):
            redirects[sample_key] = parent_key
    for variant_key, targets in global_variants.items():
        if variant_key not in targets or len(targets) < 2:
            continue
        for target in targets:
            if target != variant_key:
                redirects[target] = variant_key

    # Reconcile source presentation variants before primary aliases are
    # protected.  A merge requires the same explicit material descriptor, so a
    # coincidental short sample code cannot collapse an unrelated material.
    by_material: dict[str, list[InventoryAnchor]] = {}
    for anchor in anchors:
        descriptor = _identity_key(anchor.material_name_raw)
        if descriptor:
            by_material.setdefault(descriptor, []).append(anchor)
    for rows in by_material.values():
        variant_targets: dict[str, set[str]] = {}
        confusable_targets: dict[str, set[str]] = {}
        for anchor in rows:
            sample_key = _identity_key(anchor.sample_id_raw)
            variant_key = _variant_presentation_key(anchor.sample_id_raw)
            if sample_key and variant_key:
                variant_targets.setdefault(variant_key, set()).add(sample_key)
            parent_key = _existing_identity_parent(anchor.sample_id_raw) or sample_key
            if parent_key:
                confusable_targets.setdefault(
                    _ocr_confusable_key(parent_key), set()
                ).add(parent_key)
        for targets in variant_targets.values():
            if len(targets) < 2:
                continue
            canonical = min(targets, key=lambda key: (len(key), key))
            for target in targets:
                if target != canonical:
                    redirects[target] = canonical

        for targets in confusable_targets.values():
            if len(targets) < 2:
                continue
            # Prefer the source form containing a digit when it competes with
            # an OCR letter-O form (for example T0 versus TO).
            canonical = min(
                targets,
                key=lambda key: (not any(char.isdigit() for char in key), len(key), key),
            )
            for target in targets:
                if target != canonical:
                    redirects[target] = canonical

        labels = {
            _identity_key(anchor.sample_id_raw): str(anchor.sample_id_raw).strip()
            for anchor in rows
            if _identity_key(anchor.sample_id_raw)
        }
        compact_codes = {
            key
            for key, label in labels.items()
            if re.fullmatch(r"[A-Za-z]{2,6}", label)
        }
        for long_key, label in labels.items():
            initialism = _source_initialism(label)
            if not initialism or initialism not in compact_codes or long_key == initialism:
                continue
            redirects[long_key] = initialism

    # A parent such as ``TO`` may itself become resolvable only after the
    # shared-descriptor O/0 pass above. Link its measured/nominal children now.
    for anchor in anchors:
        sample_key = _identity_key(anchor.sample_id_raw)
        parent_key = _existing_identity_parent(anchor.sample_id_raw)
        if (
            sample_key
            and parent_key
            and sample_key != parent_key
            and (parent_key in candidate_keys or parent_key in redirects)
            and sample_key not in protected_orientation_keys
        ):
            redirects[sample_key] = parent_key
    for anchor in anchors:
        sample_key = _identity_key(anchor.sample_id_raw)
        if sample_key not in candidate_keys or not anchor.material_name_raw:
            continue
        for descriptor in _identity_alias_keys(anchor.material_name_raw):
            if not descriptor or descriptor == sample_key:
                continue
            residual = ""
            if sample_key.startswith(descriptor):
                residual = sample_key[len(descriptor) :]
            elif sample_key.endswith(descriptor):
                residual = sample_key[: -len(descriptor)]
            if residual in candidate_keys:
                sample_roles = candidate_roles.get(sample_key, set())
                residual_roles = candidate_roles.get(residual, set())
                if (
                    sample_roles
                    and residual_roles
                    and sample_roles.isdisjoint(residual_roles)
                ):
                    # Explicit Target/Reference disagreement is source evidence
                    # that these are different material owners.  For example,
                    # a reference process variant must not donate its process
                    # prefix and absorb the target base alloy merely because
                    # the remaining text matches that alloy's sample code.
                    continue
                redirects[sample_key] = residual
                break

    # A provider may first call the target by its bare alloy code and then use
    # a process-qualified source identity (for example ``X`` and ``WAAM X``).
    # Reconcile that pair only when the bare anchor's own copied evidence names
    # the extra qualifier, both anchors agree on role, and exactly one longer
    # candidate qualifies. State/feedstock prefixes remain independent owners.
    # This also keeps reference process variants from absorbing a target base.
    for base_key in sorted(candidate_keys):
        if len(base_key) < 3 or base_key in redirects:
            continue
        base_roles = candidate_roles.get(base_key, set())
        evidence_text = normalize_source_alias(
            " ".join(
                str(evidence)
                for anchor in anchors
                if _identity_key(anchor.sample_id_raw) == base_key
                for evidence in anchor.source_evidence
            )
        )
        if not evidence_text:
            continue
        qualified: set[str] = set()
        for candidate in candidate_keys:
            if candidate == base_key or redirects.get(candidate) == base_key:
                continue
            candidate_roles_for_key = candidate_roles.get(candidate, set())
            if (
                base_roles
                and candidate_roles_for_key
                and base_roles.isdisjoint(candidate_roles_for_key)
            ):
                continue
            extra = ""
            if candidate.endswith(base_key):
                extra = candidate[: -len(base_key)]
            elif candidate.startswith(base_key):
                extra = candidate[len(base_key) :]
            if len(extra) < 3 or extra not in evidence_text:
                continue
            descriptor = _state_descriptor(extra)
            if descriptor is not None and not descriptor[0].startswith("raw:"):
                continue
            process_markers = {
                f"{extra}{suffix}"
                for suffix in (
                    "process",
                    "deposition",
                    "deposited",
                    "fabrication",
                    "fabricated",
                    "manufacturing",
                    "manufactured",
                    "printing",
                    "printed",
                    "processing",
                    "processed",
                    "production",
                    "produced",
                )
            }
            process_markers.update(
                f"{verb}{article}{extra}"
                for verb in (
                    "depositedby",
                    "fabricatedby",
                    "manufacturedby",
                    "printedby",
                    "processedby",
                    "producedby",
                )
                for article in ("", "the")
            )
            if not any(marker in evidence_text for marker in process_markers):
                continue
            qualified.add(candidate)
        if len(qualified) == 1:
            redirects[base_key] = next(iter(qualified))

    qualified_by_base: dict[str, set[str]] = {}
    for anchor in anchors:
        sample_key = _identity_key(anchor.sample_id_raw)
        stripped = _SAMPLE_STATE_PREFIX.sub(
            "", _strip_identity_suffix(anchor.sample_id_raw), count=1
        ).strip()
        base_key = _identity_key(stripped)
        if base_key and base_key != sample_key and base_key in candidate_keys:
            qualified_by_base.setdefault(base_key, set()).add(sample_key)
    for base_key, qualified in qualified_by_base.items():
        if len(qualified) == 1:
            redirects[next(iter(qualified))] = base_key

    # A source may name one baseline by both its explicit state and its material
    # presentation (for example, "mill annealed" and "wrought X").  Merge only
    # when the state label itself is a sample anchor and exactly one other anchor
    # shares both that state and a material descriptor; broader state classes stay
    # separate so unrelated as-built samples cannot collapse.
    def redirected_key(key: str) -> str:
        seen: set[str] = set()
        while key in redirects and key not in seen:
            seen.add(key)
            key = redirects[key]
        return key

    # A long material descriptor may be emitted as a standalone anchor in one
    # chunk and as ``material_name_raw`` for its short source code in another.
    # Primary aliases are intentionally protected later, so reconcile this
    # explicit one-to-one source relationship before that protection applies.
    # A descriptor used by multiple samples/states remains ambiguous and is
    # never collapsed or broadcast.
    descriptor_owners: dict[str, set[str]] = {}
    for anchor in anchors:
        sample_key = redirected_key(_identity_key(anchor.sample_id_raw))
        if not sample_key or not anchor.material_name_raw:
            continue
        for descriptor in _identity_alias_keys(anchor.material_name_raw):
            if descriptor and descriptor != sample_key:
                descriptor_owners.setdefault(descriptor, set()).add(sample_key)
    for descriptor, owners in descriptor_owners.items():
        canonical_owners = {redirected_key(owner) for owner in owners}
        if (
            descriptor not in candidate_keys
            or descriptor in expanded_base_keys
            or len(canonical_owners) != 1
        ):
            continue
        owner = next(iter(canonical_owners))
        if redirected_key(descriptor) != owner:
            redirects[descriptor] = owner

    # State expansion runs before cross-chunk aliases are known. Reconcile the
    # generated ``base [state]`` identities again after their bases have been
    # normalized, otherwise T0 and an OCR/table form such as T0 (M) can each
    # produce a duplicate heat-treated state item.
    generated_states: dict[
        tuple[str, tuple[str, tuple[str, ...]]], set[str]
    ] = {}
    for anchor in anchors:
        label = str(anchor.sample_id_raw or "").strip()
        match = re.match(r"(?s)^(.+?)\s*\[([^\[\]]+)\]\s*$", label)
        if not match:
            continue
        base_text, state_text = match.groups()
        base_key = _existing_identity_parent(base_text) or _identity_key(base_text)
        descriptor = _state_descriptor(state_text)
        if not base_key or descriptor is None:
            continue
        generated_states.setdefault(
            (redirected_key(base_key), descriptor), set()
        ).add(_identity_key(label))
    for targets in generated_states.values():
        if len(targets) < 2:
            continue
        canonical = min(targets, key=lambda key: (len(key), key))
        for target in targets:
            if target != canonical:
                redirects[target] = canonical

    sample_states: dict[str, set[str]] = {}
    sample_descriptors: dict[str, set[str]] = {}
    for anchor in anchors:
        state_key = _identity_key(anchor.state_raw)
        sample_key = redirected_key(_identity_key(anchor.sample_id_raw))
        if state_key:
            sample_states.setdefault(sample_key, set()).add(state_key)
        if anchor.material_name_raw:
            sample_descriptors.setdefault(sample_key, set()).update(
                _identity_alias_keys(anchor.material_name_raw)
            )
    for state_sample in list(sample_states):
        state_aliases = sample_states.get(state_sample, set())
        if state_sample not in state_aliases:
            continue
        descriptors = sample_descriptors.get(state_sample, set())
        equivalents = {
            sample
            for sample, states in sample_states.items()
            if sample != state_sample
            and state_sample in states
            and descriptors & sample_descriptors.get(sample, set())
        }
        if len(equivalents) == 1:
            redirects[next(iter(equivalents))] = state_sample

    def canonical_key(value: Any) -> str:
        return redirected_key(_identity_key(value))

    descriptor_targets: dict[str, set[str]] = {}
    for anchor in anchors:
        if not anchor.material_name_raw:
            continue
        descriptors = _identity_alias_keys(anchor.material_name_raw)
        target = canonical_key(anchor.sample_id_raw)
        for descriptor in descriptors:
            if descriptor and target and descriptor != target:
                descriptor_targets.setdefault(descriptor, set()).add(target)
    shared_descriptors = {
        descriptor
        for descriptor, targets in descriptor_targets.items()
        if len(targets) > 1
    }
    for anchor in anchors:
        if (
            _identity_key(anchor.sample_id_raw) in shared_descriptors
            and _identity_key(anchor.sample_id_raw) not in expanded_base_keys
        ):
            continue
        index.add_anchor_as(anchor, canonical_key(anchor.sample_id_raw))
    for anchor in anchors:
        expected = canonical_key(anchor.sample_id_raw)
        index.add_alias(anchor.sample_id_raw, expected)
        canonical = index.resolve_exact(anchor.sample_id_raw)
        if len(canonical) == 1 and anchor.material_name_raw:
            index.add_alias(anchor.material_name_raw, canonical[0])
        if len(canonical) == 1 and anchor.state_raw:
            index.add_state_alias(anchor.state_raw, canonical[0])
    for citation_label, material_label in citation_aliases:
        targets = index.resolve_exact(material_label)
        for target in targets:
            index.add_alias(citation_label, target)
    # Regions, test pieces, methods, standards and structural entities are not
    # material identities. Their facts may still be retained when the provider
    # also supplied a material_name_raw that resolves to exactly one existing
    # source-backed material; otherwise the alias stays unresolved and is
    # surfaced as a review issue instead of creating or guessing an item.
    for anchor in non_material_owner_aliases:
        material_label = str(anchor.material_name_raw or "").strip()
        targets = index.resolve_exact(material_label)
        for target in targets:
            index.add_alias(anchor.sample_id_raw, target)

    for base_label, displays in state_base_aliases.items():
        for display in displays:
            for canonical in index.resolve_exact(display):
                index.add_alias(base_label, canonical)
                display_base = str(display).split(" [", 1)[0]
                base_targets = index.resolve_exact(display_base)
                if len(base_targets) == 1:
                    index.add_state_family(canonical, base_targets[0])

    # Providers can retain a contextual qualifier in an inventory chunk while
    # omitting it from a fact chunk (for example ``multi-spot melt sample``
    # versus ``multi-spot sample``).  Add the unqualified fact label as an alias
    # only when every source-backed qualified anchor with that base resolves to
    # one canonical identity.  Multiple candidates remain unresolved so this
    # convenience can never broadcast a fact across samples or states.
    qualified_base_targets: dict[str, set[str]] = {}
    for anchor in anchors:
        base_key = _qualified_sample_base_key(anchor.sample_id_raw)
        canonical = canonical_key(anchor.sample_id_raw)
        if base_key and canonical:
            qualified_base_targets.setdefault(base_key, set()).add(canonical)
    for fact in facts:
        for label in [*_fact_identity_labels(fact), fact.sample_id_raw]:
            if not label or len(index.resolve_exact(label)) == 1:
                continue
            targets = qualified_base_targets.get(_identity_key(label), set())
            if len(targets) == 1:
                index.bind_unique_alias(label, next(iter(targets)))

    # Material-identity facts provide another explicit source pairing. Resolve
    # every identity already connected to an inventory sample before creating a
    # new primary. This makes the result independent of cross-chunk fact order.
    identity_facts = [fact for fact in facts if fact.fact_type == "material_identity"]
    unresolved_facts: list[AxisFact] = []
    for fact in identity_facts:
        labels = _fact_identity_labels(fact)
        candidate_labels = [*labels, fact.sample_id_raw]
        known = {
            target
            for label in candidate_labels
            for target in index.resolve_exact(label)
        }
        if len(known) == 1:
            canonical = next(iter(known))
            for label in candidate_labels:
                index.add_alias(label, canonical)
        else:
            unresolved_facts.append(fact)

    for fact in unresolved_facts:
        labels = _fact_identity_labels(fact)
        candidate_labels = [*labels, fact.sample_id_raw]
        known = {
            target
            for label in candidate_labels
            for target in index.resolve_exact(label)
        }
        if len(known) == 1:
            canonical = next(iter(known))
        elif known:
            continue
        elif index.primary_aliases:
            # A paper-level inventory is authoritative.  Once it names usable
            # samples, an unanchored identity-only fact (often a literature alloy
            # or table standard) must not invent another target material.
            continue
        else:
            canonical = next(
                (
                    created
                    for label in candidate_labels
                    if (created := index.add_primary(label)) is not None
                ),
                None,
            )
        if canonical is None:
            continue
        for label in candidate_labels:
            index.add_alias(label, canonical)

    # Inventory can legitimately be empty for a short evidence unit. Only when
    # the entire paper has no usable primary anchor, preserve credible fact-level
    # sample labels as a last resort. Once inventory has named any samples, noisy
    # unanchored labels are never allowed to create additional material items.
    if not index.primary_aliases:
        for fact in facts:
            for label in [*_fact_identity_labels(fact), fact.sample_id_raw]:
                if index.add_primary(label) is not None:
                    break
    _register_fact_local_states(index, facts)
    return index


def _fact_local_state_context(fact: AxisFact) -> list[str]:
    values: list[str] = []
    for key in (
        "material_state",
        "state_raw",
        "test_specimen_raw",
    ):
        value = fact.data.get(key)
        if value not in (None, "", [], {}) and not _is_unresolved_alias(value):
            values.append(str(value))
    return values


def _fact_state_context(fact: AxisFact) -> list[str]:
    state_context = [*_fact_local_state_context(fact), *fact.source_evidence]
    condition = fact.data.get("test_condition_raw")
    if condition not in (None, "", [], {}):
        state_context.append(str(condition))
    return state_context


def _fact_declared_targets(
    index: _IdentityIndex, fact: AxisFact
) -> tuple[str, ...]:
    """Resolve the first explicit fact owner before state-evidence narrowing."""

    for label in [*_fact_identity_labels(fact), fact.sample_id_raw]:
        targets = index.resolve_label(label) or index.resolve_state_label(label)
        if targets:
            return targets
    return ()


def _group_route(index: _IdentityIndex, fact: AxisFact) -> tuple[str, ...]:
    state_context = _fact_state_context(fact)

    def narrow_state_family(targets: tuple[str, ...]) -> tuple[str, ...]:
        local_state_context = _fact_local_state_context(fact)
        local_state_targets = index.resolve_state_evidence(local_state_context)
        if local_state_targets:
            state_targets = local_state_targets
        elif any(
            fact.data.get(key) not in (None, "", [], {})
            and not _is_unresolved_alias(fact.data.get(key))
            for key in ("material_state", "state_raw")
        ):
            # An observation-local state is more specific than a copied table
            # spanning several columns. If the local value has no indexed state,
            # keep the declared material owner instead of borrowing a sibling
            # state merely mentioned elsewhere in that table.
            return targets
        else:
            state_targets = index.resolve_state_evidence(state_context)
        # Prefer a uniquely qualified state member of the resolved base before
        # accepting the base itself as a textual match.  State registration can
        # legitimately contain both entries because the source named the state
        # on a base anchor before deterministic expansion.
        family_members = tuple(
            target
            for target in state_targets
            if index.state_family_base.get(target) in targets
        )
        if len(family_members) == 1:
            return family_members
        narrowed = tuple(target for target in targets if target in state_targets)
        if narrowed:
            if len(narrowed) == 1:
                return narrowed
            # State registration can contain both the base identity and its
            # generated state member.  Explicit state evidence belongs to the
            # qualified member, not to both representations of the same
            # material lineage.
            qualified = tuple(
                target for target in narrowed if target in index.state_family_base
            )
            if len(qualified) == 1:
                return qualified
            return narrowed
        # When two material families share the same explicit state qualifier
        # (for example GA and WA both sintered at 1225 °C), the qualifier alone
        # resolves two state items. If the fact's sample label resolves to one
        # base family, retain only the state member belonging to that family.
        # This is a narrowing operation; multiple matches remain ambiguous and
        # therefore never broadcast one fact across several states.
        # A different sample mentioned in a comparison sentence is not a state
        # of the fact's explicit owner.  The related state-member and exact
        # intersection cases were already handled above; never replace the
        # owner merely because one unrelated state alias appears in evidence.
        base = index.resolve_state_family_base(targets)
        return base if base else targets

    def route_label(label: Any) -> tuple[str, ...]:
        """Resolve one fact owner without broadcasting a shared alias.

        A material family or designation may be a source-backed alias for many
        independently named samples/states.  Merely resolving that alias does
        not prove that the assertion applies to every one of them.  Preserve a
        genuinely source-enumerated combined label (``A and B``), but leave any
        other multi-target result unresolved so it becomes a visible review
        issue instead of duplicated candidate facts.
        """

        targets = index.resolve_label(label)
        if not targets:
            targets = index.resolve_state_label(label)
        if not targets:
            return ()
        narrowed = narrow_state_family(targets)
        if len(narrowed) > 1 and not _combined_parts(label):
            return ()
        return narrowed

    # The schema's observation-level sample_id is more specific than a noisy
    # outer envelope and therefore has first priority.
    for label in _fact_identity_labels(fact):
        targets = route_label(label)
        if targets:
            return targets
    targets = route_label(fact.sample_id_raw)
    if targets:
        return targets
    evidence_targets = index.resolve_evidence(fact.source_evidence)
    # An unresolved comparison span is not evidence that the same record
    # belongs to every mentioned material.  The provider must emit a separate
    # sample-qualified fact for each target; otherwise preserve the ambiguity
    # as a materialization issue instead of manufacturing duplicates.
    return evidence_targets if len(evidence_targets) == 1 else ()


def _group_role_and_nature(
    anchors: Sequence[InventoryAnchor],
) -> tuple[str, str]:
    if not anchors:
        return "Target", "Experimental"
    counts = Counter((anchor.role, anchor.data_nature) for anchor in anchors)
    confidence = Counter()
    for anchor in anchors:
        confidence[(anchor.role, anchor.data_nature)] += anchor.confidence
    return min(
        counts,
        key=lambda pair: (
            -counts[pair],
            -confidence[pair],
            pair != ("Target", "Experimental"),
            pair,
        ),
    )


def _group_material_identities(group: dict[str, Any]) -> list[dict[str, Any]]:
    identities = _deduplicate(
        _fact_data(fact)
        for fact in group["facts"]
        if fact.fact_type == "material_identity"
    )
    for anchor in group["anchors"]:
        if anchor.material_name_raw:
            identities.append(
                {
                    "material_family": None,
                    "material_name_raw": anchor.material_name_raw,
                    "designation_raw": None,
                    "feedstock_form": None,
                }
            )
    return _deduplicate(identities)


def _morphology_only_material_identity(row: dict[str, Any]) -> bool:
    """Return whether a material-name slot contains only shape/morphology prose."""

    name = str(row.get("material_name_raw") or "").strip()
    if not name or not _MORPHOLOGY_IDENTITY_DESCRIPTOR.fullmatch(name):
        return False
    other = " ".join(
        str(row.get(key) or "").strip()
        for key in ("material_family", "designation_raw")
    )
    return not _MATERIAL_IDENTITY_TERM.search(other) and not (
        _looks_like_composition_designation(other)
    )


def _material_identity_rank(
    row: dict[str, Any], *, sample_id: str
) -> tuple[int, int, int, int, int, int]:
    name = str(row.get("material_name_raw") or "").strip()
    designation = str(row.get("designation_raw") or "").strip()
    family = str(row.get("material_family") or "").strip()
    feedstock = str(row.get("feedstock_form") or "").strip()
    combined = " ".join(
        value for value in (name, designation, family, feedstock) if value
    )
    sample_key = normalize_source_alias(sample_id)
    combined_key = normalize_source_alias(combined)
    designation_like = bool(
        _looks_like_composition_designation(combined)
        or re.search(r"[A-Za-z].*\d|\d.*[A-Za-z]", combined)
    )
    material_named = bool(_MATERIAL_IDENTITY_TERM.search(combined))
    sample_linked = bool(sample_key and sample_key in combined_key)
    populated = sum(bool(value) for value in (name, designation, family, feedstock))
    return (
        int(bool(name) and material_named),
        int(designation_like),
        int(material_named),
        int(sample_linked),
        populated,
        min(len(re.findall(r"[A-Za-z0-9]+", combined)), 12),
    )


def _select_material_identity(
    identities: Sequence[dict[str, Any]], *, sample_id: str
) -> tuple[dict[str, Any] | None, bool]:
    """Replace a morphology-only first identity with a fuller grounded candidate."""

    if not identities:
        return None, False
    first = identities[0]
    if not _morphology_only_material_identity(first):
        return first, False
    candidates = [
        row for row in identities[1:] if not _morphology_only_material_identity(row)
    ]
    if not candidates:
        return first, False
    selected = max(
        candidates,
        key=lambda row: _material_identity_rank(row, sample_id=sample_id),
    )
    if not any(
        str(selected.get(key) or "").strip()
        for key in ("material_name_raw", "designation_raw", "material_family")
    ):
        return first, False
    return selected, selected != first


def _comparison_only_property_fact(fact: AxisFact) -> bool:
    if fact.fact_type != "property":
        return False
    value = str(fact.data.get("value_raw") or "").strip()
    has_number = bool(re.search(r"[+-]?(?:\d+(?:\.\d*)?|\.\d+)", value))
    has_absolute_measurement = bool(
        has_number
        and (
            str(fact.data.get("unit_raw") or "").strip()
            or re.fullmatch(
                r"\s*[+-]?(?:\d+(?:\.\d*)?|\.\d+)"
                r"(?:\s*(?:±|\+/-)\s*\d+(?:\.\d*)?)?\s*",
                value,
            )
        )
    )
    if has_absolute_measurement:
        return False
    context = " | ".join([value, *fact.source_evidence])
    return bool(_COMPARISON_ONLY_VALUE.search(context))


def _reference_has_independent_fact(facts: Sequence[AxisFact]) -> bool:
    for fact in facts:
        if fact.fact_type in {"material_identity", "process_edge"}:
            continue
        if _comparison_only_property_fact(fact):
            continue
        if fact.fact_type == "process_text":
            continue
        return True
    return False


def _item_has_substantive_data(item: dict[str, Any]) -> bool:
    extracted = item.get("Extracted_Data") or {}
    composition = extracted.get("Composition") or {}
    processing = extracted.get("Processing") or {}
    structure = extracted.get("Structure") or {}
    process_route = processing.get("Process_Route") or {}
    structure_text = structure.get("Structure_Text") or {}
    return bool(
        composition.get("Composition_Observations")
        or process_route.get("candidate_stages")
        or structure.get("Structure_Observations")
        or structure.get("Characterization")
        or extracted.get("Properties")
        or str(structure_text.get("original") or "").strip()
        not in {"", "not_reported"}
    )


def _chart_quarantine_issues_from_text(source_text: str | None) -> list[MaterializeIssue]:
    issues: list[MaterializeIssue] = []
    if not source_text:
        return issues
    seen: set[str] = set()
    for raw_line in source_text.splitlines():
        line = raw_line.strip()
        if not line.startswith("quality_quarantine:"):
            continue
        payload_text = line.split(":", 1)[1].strip()
        try:
            payload = json.loads(payload_text)
        except json.JSONDecodeError:
            continue
        if not isinstance(payload, dict) or payload.get("code") != "curve_series_quarantined":
            continue
        signature = json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str)
        if signature in seen:
            continue
        seen.add(signature)
        series = [
            str(value).strip()
            for value in payload.get("series", []) or []
            if str(value).strip()
        ]
        label = ", ".join(series) or "chart series"
        issues.append(
            MaterializeIssue(
                code="curve_series_quarantined",
                sample_id_raw=label,
                path="chart_context",
                message=(
                    "One or more chart series failed the upstream deterministic "
                    "quality gate and were excluded from extraction context."
                ),
                evidence=line,
                expected={"chart_series": "finite coordinates consistent with axis semantics"},
                actual=payload,
                suggested_action="Review the preserved chart CSV and axis calibration.",
            )
        )
    return issues


def _cited_nominal_composition_row(fact: AxisFact, label: str) -> bool:
    """Return whether a fact is a literal multi-element nominal table row."""

    if not isinstance(fact, CompositionFact) or fact.fact_type != "composition_observation":
        return False
    data = fact.data
    if str(data.get("data_source") or "").strip().casefold() != "table":
        return False
    components = [
        row for row in data.get("components") or [] if isinstance(row, dict)
    ]
    reported = [
        row
        for row in components
        if str(row.get("name_raw") or "").strip()
        and str(row.get("value_raw") or "").strip()
        and re.search(r"\d", str(row.get("value_raw") or ""))
    ]
    if len(reported) < 2:
        return False
    folded_label = unicodedata.normalize("NFKC", label).casefold()
    return any(
        folded_label in unicodedata.normalize("NFKC", evidence).casefold()
        for evidence in fact.source_evidence
    )


def _recover_cited_nominal_composition_owners(
    anchors: Sequence[InventoryAnchor], facts: Sequence[AxisFact]
) -> tuple[list[InventoryAnchor], list[AxisFact], list[MaterializeIssue]]:
    """Give an explicit cited nominal-composition row its own reference owner.

    The global inventory is authoritative for target materials, but a provider
    can legitimately extract a multi-element literature row without emitting a
    separate inventory anchor for that reference.  Recover only the narrow case
    where the row label carries a citation, at least one row fragment declares
    nominal composition, and every promoted fragment copies that exact row label
    from a table.  Bare headers and analysis-point numbers remain unresolved.
    """

    anchor_rows = list(anchors)
    fact_rows = list(facts)
    grouped: dict[str, list[tuple[int, AxisFact]]] = {}
    labels: dict[str, str] = {}
    for index, fact in enumerate(fact_rows):
        label = str(fact.sample_id_raw or "").strip()
        if not _CITED_NOMINAL_COMPOSITION_LABEL.fullmatch(label):
            continue
        key = _identity_key(label)
        grouped.setdefault(key, []).append((index, fact))
        labels.setdefault(key, label)

    issues: list[MaterializeIssue] = []
    for key, rows in grouped.items():
        label = labels[key]
        eligible = [
            (index, fact)
            for index, fact in rows
            if _cited_nominal_composition_row(fact, label)
        ]
        if not eligible or not any(
            str(fact.data.get("source_type") or "").strip().casefold()
            == "nominal"
            for _, fact in eligible
        ):
            continue
        reference_anchors = [
            anchor
            for anchor in anchor_rows
            if _identity_key(anchor.sample_id_raw) == key
            and anchor.role == "Reference"
            and str(anchor.material_name_raw or "").strip()
            and is_plausible_material_identity(anchor.material_name_raw)
        ]
        reference_anchor = (
            max(reference_anchors, key=lambda anchor: anchor.confidence)
            if reference_anchors
            else None
        )
        material_name = (
            str(reference_anchor.material_name_raw).strip()
            if reference_anchor is not None
            else ""
        )
        citation = re.search(r"\[[0-9,;\s-]+\]", label)
        display = (
            f"{material_name} {citation.group(0)} [reference]"
            if material_name and citation is not None
            else f"{label} [reference]"
        )
        related = [
            (index, fact)
            for index, fact in rows
            if (
                fact.fact_type == "material_identity"
                and any(
                    unicodedata.normalize("NFKC", label).casefold()
                    in unicodedata.normalize("NFKC", source).casefold()
                    for source in fact.source_evidence
                )
            )
        ]
        promoted = sorted([*eligible, *related], key=lambda row: row[0])
        evidence = list(
            dict.fromkeys(
                source
                for _, fact in promoted
                for source in fact.source_evidence
                if str(source).strip()
            )
        )
        anchor_rows.append(
            InventoryAnchor(
                sample_id_raw=display,
                material_name_raw=material_name or display,
                state_raw="nominal composition",
                role="Reference",
                data_nature="Literature_Experimental",
                source_evidence=evidence,
                confidence=max(fact.confidence for _, fact in promoted),
            )
        )
        recovered_facts: list[dict[str, Any]] = []
        for index, fact in promoted:
            data = deepcopy(fact.data)
            if _identity_key(data.get("sample_id")) == key:
                data["sample_id"] = display
            if (
                fact.fact_type == "composition_observation"
                and _is_unresolved_alias(data.get("material_state"))
            ):
                data["material_state"] = "nominal composition"
            recovered = fact.model_copy(
                update={"sample_id_raw": display, "data": data}
            )
            fact_rows[index] = recovered
            recovered_facts.append(fact.model_dump())
        issues.append(
            MaterializeIssue(
                code="reference_composition_owner_recovered",
                sample_id_raw=display,
                path=f"items.{display}",
                message=(
                    "A cited multi-element nominal-composition table row was "
                    "materialized as an independent literature reference owner."
                ),
                evidence=evidence,
                expected={
                    "owner": "independent cited nominal-composition reference"
                },
                actual={
                    "before_owner": label,
                    "after_owner": display,
                    "facts": recovered_facts,
                },
                suggested_action=(
                    "Review only if the cited row is not a standalone reference "
                    "composition."
                ),
            )
        )
    return anchor_rows, fact_rows, issues


def _microanalysis_location_label(fact: AxisFact) -> str:
    """Return a literal observation location without treating it as material."""

    for value in (fact.sample_id_raw, fact.data.get("sample_id")):
        label = str(value or "").strip()
        if _MICROANALYSIS_LOCATION.fullmatch(label):
            return label
    return ""


def _microanalysis_location_key(value: Any) -> str:
    match = _MICROANALYSIS_LOCATION_SEARCH.fullmatch(str(value or "").strip())
    if match is None:
        return ""
    identifier = match.group(2).strip("._-").casefold()
    return f"{match.group(1).casefold()}:{identifier}" if identifier else ""


def _source_microanalysis_state_map(
    source_text: str,
) -> dict[str, tuple[str, list[str]]]:
    """Recover Point/Spot-to-sintering-state links stated in nearby prose.

    A single-temperature paragraph owns every analysis location it names.  A
    multi-temperature paragraph is accepted only when it presents parallel
    location groups of the same cardinality (for example two temperatures and
    repeated ``points A and B`` pairs).  Ambiguous or conflicting prose yields
    no mapping; task-response state guesses never break the tie.
    """

    candidates: dict[str, dict[str, list[str]]] = {}
    for raw_line in (source_text or "").splitlines():
        line = raw_line.strip()
        if not line or not re.search(r"(?i)\bsinter(?:ed|ing)?\b", line):
            continue
        temperatures = list(
            dict.fromkeys(
                number
                for match in _CELSIUS_SERIES.finditer(line)
                for number in re.findall(r"[-+]?\d{2,4}(?:\.\d+)?", match.group(1))
            )
        )
        if not temperatures:
            continue
        locations = [
            (match.group(1), match.group(2))
            for match in _MICROANALYSIS_LOCATION_SEARCH.finditer(line)
            if re.search(r"\d", match.group(2))
        ]
        assignments: list[tuple[str, str, str]] = []
        if len(temperatures) == 1:
            assignments.extend(
                (kind, identifier, temperatures[0])
                for kind, identifier in locations
            )
        else:
            for group in _MICROANALYSIS_LOCATION_GROUP.finditer(line):
                kind = group.group(1)
                identifiers = [group.group(2)]
                identifiers.extend(
                    match.group(1)
                    for match in re.finditer(
                        r"(?i)(?:,|and|&)\s*"
                        r"(?:(?:point|spot|area|location)s?\s*)?"
                        r"#?\s*([A-Za-z0-9._-]+)",
                        group.group(3),
                    )
                )
                if len(identifiers) == len(temperatures):
                    assignments.extend(
                        (kind, identifier, temperature)
                        for identifier, temperature in zip(
                            identifiers, temperatures, strict=True
                        )
                    )
        for kind, identifier, temperature in assignments:
            key = _microanalysis_location_key(f"{kind} {identifier}")
            state = f"sintered at {temperature} °C"
            if key:
                candidates.setdefault(key, {}).setdefault(state, []).append(line)

    resolved: dict[str, tuple[str, list[str]]] = {}
    for key, states in candidates.items():
        if len(states) != 1:
            continue
        state, evidence = next(iter(states.items()))
        resolved[key] = (state, list(dict.fromkeys(evidence)))
    return resolved


def _state_supported_by_fact_evidence(fact: AxisFact, state: str) -> bool:
    descriptor = _state_descriptor(state)
    if descriptor is None:
        return False
    category, qualifiers = descriptor
    return any(
        (candidate := _state_descriptor(evidence)) is not None
        and candidate[0] == category
        and set(qualifiers) <= set(candidate[1])
        for evidence in fact.source_evidence
    )


def _microanalysis_composition_row(fact: AxisFact) -> bool:
    """Return whether a fact is a grounded multi-element Point/Spot table row."""

    if not isinstance(fact, CompositionFact) or fact.fact_type != "composition_observation":
        return False
    label = _microanalysis_location_label(fact)
    if not label:
        return False
    data = fact.data
    if (
        str(data.get("source_type") or "").strip().casefold() != "measured"
        or str(data.get("data_source") or "").strip().casefold() != "table"
    ):
        return False
    components = [
        row for row in data.get("components") or [] if isinstance(row, dict)
    ]
    reported = [
        row
        for row in components
        if str(row.get("name_raw") or "").strip()
        and str(row.get("value_raw") or "").strip()
        and re.search(r"\d", str(row.get("value_raw") or ""))
    ]
    if len(reported) < 2:
        return False
    folded_label = unicodedata.normalize("NFKC", label).casefold()
    return any(
        folded_label in unicodedata.normalize("NFKC", evidence).casefold()
        for evidence in fact.source_evidence
    )


def _microanalysis_state_owner(
    index: _IdentityIndex, fact: AxisFact
) -> str | None:
    """Resolve a point row only to one explicit, numerically matching state."""

    state = str(fact.data.get("material_state") or "").strip()
    state_descriptor = _state_descriptor(state)
    if state_descriptor is None:
        return None
    state_category, state_qualifiers = state_descriptor
    state_numbers = set(re.findall(r"\d+(?:\.\d+)?", state))
    if not state_numbers:
        return None
    candidates = set(index.resolve_state_evidence([state]))
    # A directly named inventory sample may carry a more specific state than
    # the table header (for example ``sintered at 1280 °C for 4 h`` versus the
    # EDS column's ``sintered at 1280 °C``).  Exact descriptor lookup excludes
    # that legitimate owner, so include source primaries whose target-anchor
    # state has the same category and a superset of the table qualifiers.  The
    # numeric sample-label check below prevents a generic alloy owner from
    # winning merely because it shares a process category.
    for target in index.primary_aliases:
        for anchor in index.anchors.get(target, []):
            descriptor = _state_descriptor(anchor.state_raw)
            if descriptor is None:
                continue
            category, qualifiers = descriptor
            if (
                anchor.role == "Target"
                and category == state_category
                and set(state_qualifiers) <= set(qualifiers)
            ):
                candidates.add(target)
                break

    ranked: list[tuple[tuple[int, int], str]] = []
    for target in candidates:
        display = index.display_label(target)
        display_numbers = set(re.findall(r"\d+(?:\.\d+)?", display))
        if not state_numbers <= display_numbers:
            continue
        target_anchors = index.anchors.get(target, [])
        if not target_anchors:
            continue
        target_role = any(anchor.role == "Target" for anchor in target_anchors)
        generated_state_presentation = bool("[" in display and "]" in display)
        rank = (
            int(not target_role),
            int(generated_state_presentation),
        )
        ranked.append((rank, target))
    if not ranked:
        return None
    best_rank = min(rank for rank, _ in ranked)
    best = [target for rank, target in ranked if rank == best_rank]
    return best[0] if len(best) == 1 else None


def _microanalysis_complete_owner_state(
    index: _IdentityIndex, target: str, source_state: str
) -> tuple[str, list[str]]:
    """Return one more-specific state already proven for the selected owner."""

    source_descriptor = _state_descriptor(source_state)
    if source_descriptor is None:
        return source_state, []
    source_category, source_qualifiers = source_descriptor
    compatible: dict[tuple[str, tuple[str, ...]], list[InventoryAnchor]] = {}
    for anchor in index.anchors.get(target, []):
        descriptor = _state_descriptor(anchor.state_raw)
        if (
            anchor.role != "Target"
            or descriptor is None
            or descriptor[0] != source_category
            or not set(source_qualifiers) <= set(descriptor[1])
        ):
            continue
        compatible.setdefault(descriptor, []).append(anchor)
    if not compatible:
        return source_state, []
    specificity = max(len(descriptor[1]) for descriptor in compatible)
    best = [
        (descriptor, anchors)
        for descriptor, anchors in compatible.items()
        if len(descriptor[1]) == specificity
    ]
    if len(best) != 1:
        return source_state, []
    _, anchors = best[0]
    anchor = min(
        anchors,
        key=lambda row: (
            len(str(row.state_raw or "")),
            str(row.state_raw or "").casefold(),
            -float(row.confidence),
        ),
    )
    return str(anchor.state_raw).strip() or source_state, list(anchor.source_evidence)


def _recover_microanalysis_location_owners(
    anchors: Sequence[InventoryAnchor], facts: Sequence[AxisFact], source_text: str
) -> tuple[list[AxisFact], list[MaterializeIssue]]:
    """Attach explicit Point/Spot composition rows to one known state owner."""

    fact_rows = list(facts)
    index = _build_identity_index(anchors, fact_rows)
    source_states = _source_microanalysis_state_map(source_text)
    recovered: dict[str, dict[str, Any]] = {}
    for fact_index, fact in enumerate(fact_rows):
        if not _microanalysis_composition_row(fact):
            continue
        location = _microanalysis_location_label(fact)
        source_state = source_states.get(_microanalysis_location_key(location))
        before_state = str(fact.data.get("material_state") or "").strip()
        if source_state is not None:
            state, state_evidence = source_state
        elif before_state and _state_supported_by_fact_evidence(fact, before_state):
            state, state_evidence = before_state, []
        else:
            continue
        data = deepcopy(fact.data)
        data["material_state"] = state
        data["sample_id"] = location
        data["source_evidence"] = list(
            dict.fromkeys([*_evidence(data.get("source_evidence")), *state_evidence])
        )
        grounded_fact = fact.model_copy(
            update={
                "data": data,
                "source_evidence": list(
                    dict.fromkeys([*fact.source_evidence, *state_evidence])
                ),
            }
        )
        target = _microanalysis_state_owner(index, grounded_fact)
        if target is None:
            continue
        owner_state, owner_state_evidence = _microanalysis_complete_owner_state(
            index, target, state
        )
        routed_data = deepcopy(grounded_fact.data)
        routed_data["material_state"] = owner_state
        routed_data["_microanalysis_owner_recovered"] = True
        routed_data["source_evidence"] = list(
            dict.fromkeys(
                [
                    *_evidence(routed_data.get("source_evidence")),
                    *owner_state_evidence,
                ]
            )
        )
        routed_fact = grounded_fact.model_copy(
            update={
                "data": routed_data,
                "source_evidence": list(
                    dict.fromkeys(
                        [*grounded_fact.source_evidence, *owner_state_evidence]
                    )
                ),
            }
        )
        before_owner = str(fact.sample_id_raw or "").strip()
        after_owner = index.display_label(target)
        fact_rows[fact_index] = routed_fact.model_copy(
            update={"sample_id_raw": after_owner}
        )
        audit = recovered.setdefault(
            target,
            {
                "after_owner": after_owner,
                "facts": [],
                "evidence": [],
                "locations": [],
                "before_owners": [],
                "state_corrections": [],
            },
        )
        audit["facts"].append(fact.model_dump())
        audit["locations"].append(location)
        audit["before_owners"].append(before_owner)
        audit["evidence"].extend(routed_fact.source_evidence)
        if before_state != owner_state:
            audit["state_corrections"].append(
                {
                    "location": location,
                    "before_state": before_state,
                    "after_state": owner_state,
                    "source_evidence": list(
                        dict.fromkeys([*state_evidence, *owner_state_evidence])
                    ),
                }
            )

    issues: list[MaterializeIssue] = []
    for audit in recovered.values():
        locations = list(dict.fromkeys(audit["locations"]))
        before_owners = list(dict.fromkeys(audit["before_owners"]))
        evidence = list(dict.fromkeys(audit["evidence"]))
        issues.append(
            MaterializeIssue(
                code="microanalysis_location_owner_recovered",
                sample_id_raw=audit["after_owner"],
                path=f"items.{audit['after_owner']}.Composition_Observations",
                message=(
                    "Measured microanalysis point rows were attached to the "
                    "only explicit material state matching source-backed prose."
                ),
                evidence=evidence,
                expected={
                    "owner": "one explicit target sample with the same state",
                    "observation_location": "preserved Point/Spot label",
                },
                actual={
                    "before_owner": before_owners[0]
                    if len(before_owners) == 1
                    else before_owners,
                    "after_owner": audit["after_owner"],
                    "observation_location": locations[0]
                    if len(locations) == 1
                    else locations,
                    "state_corrections": audit["state_corrections"],
                    "facts": audit["facts"],
                },
                suggested_action=(
                    "Review only if the table state names more than one target "
                    "material."
                ),
            )
        )
    return fact_rows, issues


@dataclass(frozen=True)
class _NumericMicroanalysisOwner:
    target: str
    state: str
    binding_evidence: tuple[str, ...]
    owner_evidence: tuple[str, ...]


def _numeric_microanalysis_location(fact: AxisFact) -> str:
    """Return one bare positive-integer observation label from a fact."""

    labels = {
        str(int(label))
        for value in (fact.sample_id_raw, fact.data.get("sample_id"))
        if (label := str(value or "").strip())
        and _NUMERIC_MICROANALYSIS_LOCATION.fullmatch(label)
    }
    return next(iter(labels)) if len(labels) == 1 else ""


def _table_cells(line: str) -> list[str]:
    """Return presentation-stripped cells for one Markdown or HTML row."""

    stripped = line.strip()
    if stripped.startswith("|") and stripped.count("|") >= 2:
        return [cell.strip() for cell in stripped.strip("|").split("|")]
    if "<tr" not in stripped.casefold():
        return []
    cells = re.findall(
        r"(?is)<t[dh]\b[^>]*>(.*?)</t[dh]>",
        stripped,
    )
    return [
        re.sub(r"(?is)<[^>]+>", "", cell)
        .replace("&nbsp;", " ")
        .strip()
        for cell in cells
    ]


def _source_numeric_eds_table_locations(source_text: str) -> set[str]:
    """Collect numeric headers from source tables explicitly labelled EDS/EDX."""

    lines = (source_text or "").splitlines()
    locations: set[str] = set()
    for line_index, line in enumerate(lines):
        cells = _table_cells(line)
        if not cells:
            continue
        first = unicodedata.normalize("NFKC", cells[0]).strip()
        header_cells = cells[1:] if (
            not first
            or re.search(r"(?i)\b(?:point|spot|area|location)s?\b", first)
        ) else []
        nonempty = [cell.strip() for cell in header_cells if cell.strip()]
        if not nonempty or not all(
            _NUMERIC_MICROANALYSIS_LOCATION.fullmatch(cell) for cell in nonempty
        ):
            continue
        window = "\n".join(lines[max(0, line_index - 4) : line_index + 2])
        if not _MICROANALYSIS_METHOD.search(window) or not re.search(
            r"(?i)\b(?:point|spot|area|location)s?\b", window
        ):
            continue
        locations.update(str(int(cell)) for cell in nonempty)
    return locations


def _numeric_microanalysis_composition_row(
    fact: AxisFact, *, source_locations: set[str]
) -> bool:
    """Return whether a bare number is a grounded multi-element EDS location."""

    if (
        not isinstance(fact, CompositionFact)
        or fact.fact_type != "composition_observation"
    ):
        return False
    location = _numeric_microanalysis_location(fact)
    if not location or location not in source_locations:
        return False
    data = fact.data
    if (
        str(data.get("source_type") or "").strip().casefold() != "measured"
        or str(data.get("data_source") or "").strip().casefold() != "table"
    ):
        return False
    context = "\n".join(
        [
            str(data.get("measurement") or ""),
            str(data.get("raw_expression") or ""),
            *fact.source_evidence,
        ]
    )
    explicit_header = any(
        location
        in {
            str(int(cell))
            for cell in _table_cells(line)[1:]
            if _NUMERIC_MICROANALYSIS_LOCATION.fullmatch(cell.strip())
        }
        for evidence in fact.source_evidence
        for line in evidence.splitlines()
        if _table_cells(line)
    )
    method_context = bool(
        _MICROANALYSIS_METHOD.search(context)
        and re.search(r"(?i)\b(?:point|spot|area|location)s?\b", context)
    )
    if not (method_context or explicit_header):
        return False
    components = [
        row for row in data.get("components") or [] if isinstance(row, dict)
    ]
    reported = [
        row
        for row in components
        if str(row.get("name_raw") or "").strip()
        and str(row.get("value_raw") or "").strip()
        and re.search(r"\d", str(row.get("value_raw") or ""))
    ]
    return len(reported) >= 2


def _source_discourse_sentences(paragraph: str) -> list[str]:
    """Split prose without breaking common figure/reference abbreviations."""

    protected = re.sub(
        r"(?i)\b(figs?|refs?|eqs?)\.",
        lambda match: match.group(0).replace(".", "\u2024"),
        paragraph,
    )
    protected = protected.replace("e.g.", "e\u2024g\u2024").replace(
        "i.e.", "i\u2024e\u2024"
    )
    sentences = re.split(r"(?<=[.!?])\s+(?=[A-Z0-9(])", protected)
    return [sentence.replace("\u2024", ".").strip() for sentence in sentences if sentence.strip()]


def _numeric_microanalysis_mentions(text: str) -> tuple[str, ...]:
    """Return all numeric Point/Spot/Area/Location identifiers in source order."""

    found: list[tuple[int, str]] = []
    covered: list[tuple[int, int]] = []
    for group in _MICROANALYSIS_LOCATION_GROUP.finditer(text):
        identifiers = [group.group(2)]
        identifiers.extend(
            match.group(1)
            for match in re.finditer(
                r"(?i)(?:,|and|&)\s*"
                r"(?:(?:point|spot|area|location)s?\s*)?"
                r"#?\s*([A-Za-z0-9._-]+)",
                group.group(3),
            )
        )
        for offset, identifier in enumerate(identifiers):
            if _NUMERIC_MICROANALYSIS_LOCATION.fullmatch(identifier):
                found.append((group.start() + offset, str(int(identifier))))
        covered.append(group.span())
    for match in _MICROANALYSIS_LOCATION_SEARCH.finditer(text):
        if any(start <= match.start() < end for start, end in covered):
            continue
        identifier = match.group(2)
        if _NUMERIC_MICROANALYSIS_LOCATION.fullmatch(identifier):
            found.append((match.start(), str(int(identifier))))
    return tuple(dict.fromkeys(value for _, value in sorted(found)))


def _target_family(index: _IdentityIndex, target: str) -> str:
    return index.state_family_base.get(target, target)


def _target_is_production_sample(index: _IdentityIndex, target: str) -> bool:
    return any(anchor.role == "Target" for anchor in index.anchors.get(target, []))


def _explicit_sample_families(
    index: _IdentityIndex, sentence: str
) -> set[str]:
    """Resolve source-named identities occurring near a material/sample noun."""

    candidates: list[tuple[int, int, set[str]]] = []
    words = list(re.finditer(r"[A-Za-z0-9_.+/-]+", sentence))
    for noun in _SOURCE_SAMPLE_NOUN.finditer(sentence):
        before = [match for match in words if match.end() <= noun.start()][-10:]
        for start in range(len(before)):
            for end in range(start + 1, len(before) + 1):
                phrase = sentence[before[start].start() : before[end - 1].end()]
                targets = {
                    target
                    for target in index.resolve_exact(phrase)
                    if _target_is_production_sample(index, target)
                }
                families = {_target_family(index, target) for target in targets}
                if families:
                    candidates.append(
                        (len(families), -(end - start), families)
                    )
    # OCR/layout extraction can split a noun phrase immediately after a short
    # source code (for example ``... aged GA`` / ``samples with ...``).  Accept
    # a terminal identity only in a microscopy/state sentence; ordinary bare
    # acronyms remain ineligible evidence.
    if not candidates and re.search(
        r"(?i)\b(?:eds|edx|sem|micrographs?|microscopy)\b", sentence
    ):
        trailing = words[-8:]
        for start in range(len(trailing)):
            phrase = sentence[trailing[start].start() : trailing[-1].end()]
            targets = {
                target
                for target in index.resolve_exact(phrase)
                if _target_is_production_sample(index, target)
            }
            families = {_target_family(index, target) for target in targets}
            if families:
                candidates.append((len(families), -(len(trailing) - start), families))
    if not candidates:
        return set()
    best_cardinality = min(row[0] for row in candidates)
    best_length = min(
        row[1] for row in candidates if row[0] == best_cardinality
    )
    best = [
        families
        for cardinality, length, families in candidates
        if cardinality == best_cardinality and length == best_length
    ]
    merged = set().union(*best)
    return merged if len(merged) == best_cardinality else set()


def _source_state_descriptor(
    sentence: str,
) -> tuple[str, tuple[str, ...]] | None:
    """Read a state category plus only unit-qualified process numbers."""

    normalized = re.sub(
        r"\^?\s*\\circ\s*(?:\{\s*C\s*\}|C)",
        "°C",
        unicodedata.normalize("NFKC", sentence),
        flags=re.IGNORECASE,
    )
    category = next(
        (
            name
            for name, pattern in _STATE_CATEGORY_PATTERNS
            if pattern.search(normalized)
        ),
        "",
    )
    qualifiers: list[str] = []
    for match in _SOURCE_STATE_QUALIFIER.finditer(normalized):
        number = match.group(1)
        unit = re.sub(r"\s+", "", match.group(2).casefold())
        unit = {
            "degreec": "°c",
            "degreesc": "°c",
            "hr": "h",
            "hrs": "h",
            "hour": "h",
            "hours": "h",
            "mins": "min",
            "minute": "min",
            "minutes": "min",
            "sec": "s",
            "seconds": "s",
        }.get(unit, unit)
        qualifiers.append(number + unit)
    if not category and qualifiers:
        category = "qualified"
    if not category:
        return None
    return category, tuple(dict.fromkeys(qualifiers))


def _target_state_candidates(
    index: _IdentityIndex,
    *,
    families: set[str],
    descriptor: tuple[str, tuple[str, ...]],
) -> dict[str, list[InventoryAnchor]]:
    """Find state owners in named families compatible with one source span."""

    category, qualifiers = descriptor
    compatible: dict[str, list[tuple[tuple[int, int], InventoryAnchor]]] = {}
    for target, anchors in index.anchors.items():
        if families and _target_family(index, target) not in families:
            continue
        for anchor in anchors:
            candidate = _state_descriptor(anchor.state_raw)
            if anchor.role != "Target" or candidate is None:
                continue
            candidate_category, candidate_qualifiers = candidate
            if category != "qualified" and candidate_category != category:
                continue
            if not set(qualifiers) <= set(candidate_qualifiers):
                continue
            extra = len(set(candidate_qualifiers) - set(qualifiers))
            rank = (int(set(candidate_qualifiers) != set(qualifiers)), extra)
            compatible.setdefault(target, []).append((rank, anchor))
    if not compatible:
        return {}
    best_rank = min(
        rank for rows in compatible.values() for rank, _ in rows
    )
    compatible_anchors = {
        target: [anchor for rank, anchor in rows if rank == best_rank]
        for target, rows in compatible.items()
        if any(rank == best_rank for rank, _ in rows)
    }
    qualified = {
        target: anchors
        for target, anchors in compatible_anchors.items()
        if target in index.state_family_base
    }
    return qualified or compatible_anchors


def _select_source_span_owner(
    index: _IdentityIndex,
    sentence: str,
    active: _NumericMicroanalysisOwner | None,
) -> tuple[_NumericMicroanalysisOwner | None, bool]:
    """Update one paragraph's active owner from explicit source grammar."""

    families = _explicit_sample_families(index, sentence)
    descriptor = _source_state_descriptor(sentence)
    context_changed = bool(families)
    if not families:
        if active is None:
            return None, False
        if descriptor is None:
            return active, False
        active_family = {_target_family(index, active.target)}
        candidates = _target_state_candidates(
            index, families=active_family, descriptor=descriptor
        )
        if len(candidates) != 1:
            return active, False
        selected_target = next(iter(candidates))
        if selected_target != active.target:
            return active, False
        return active, False
    if descriptor is None:
        if active is not None and (
            not families
            or _target_family(index, active.target) in families
        ):
            return active, context_changed
        return None, context_changed
    if not families:
        return None, context_changed
    candidates = _target_state_candidates(
        index, families=families, descriptor=descriptor
    )
    if len(candidates) != 1:
        return None, context_changed
    target, anchors = next(iter(candidates.items()))
    described = [
        (anchor, _state_descriptor(anchor.state_raw)) for anchor in anchors
    ]
    explicit = [
        row
        for row in described
        if row[1] is not None and not row[1][0].startswith("raw:")
    ]
    if explicit:
        anchors = [anchor for anchor, _ in explicit]
    states = {
        str(anchor.state_raw).strip()
        for anchor in anchors
        if str(anchor.state_raw or "").strip()
    }
    state_descriptors = {_state_descriptor(state) for state in states}
    if len(state_descriptors) != 1 or not states:
        return None, context_changed
    state = min(states, key=lambda value: (len(value), value.casefold()))
    state, complete_state_evidence = _microanalysis_complete_owner_state(
        index, target, state
    )
    owner_evidence = tuple(
        dict.fromkeys(
            [
                *(
                    evidence
                    for anchor in anchors
                    for evidence in anchor.source_evidence
                    if str(evidence).strip()
                ),
                *complete_state_evidence,
            ]
        )
    )
    return (
        _NumericMicroanalysisOwner(
            target=target,
            state=state,
            binding_evidence=(sentence,),
            owner_evidence=owner_evidence,
        ),
        context_changed,
    )


def _source_numeric_microanalysis_owner_map(
    index: _IdentityIndex, source_text: str
) -> dict[str, _NumericMicroanalysisOwner]:
    """Map numeric EDS locations to one source-backed sample/state owner."""

    candidates: dict[str, dict[str, _NumericMicroanalysisOwner]] = {}
    active: _NumericMicroanalysisOwner | None = None
    for raw_paragraph in (source_text or "").splitlines():
        paragraph = raw_paragraph.strip()
        if not paragraph:
            continue
        if paragraph.startswith("#"):
            active = None
            continue
        paragraph_has_eds = bool(_MICROANALYSIS_METHOD.search(paragraph))
        for sentence in _source_discourse_sentences(paragraph):
            selected, context_changed = _select_source_span_owner(
                index, sentence, active
            )
            if selected is not None:
                if active is not None and active.target == selected.target:
                    selected = _NumericMicroanalysisOwner(
                        target=selected.target,
                        state=selected.state,
                        binding_evidence=tuple(
                            dict.fromkeys(
                                [*active.binding_evidence, *selected.binding_evidence]
                            )
                        ),
                        owner_evidence=tuple(
                            dict.fromkeys(
                                [*active.owner_evidence, *selected.owner_evidence]
                            )
                        ),
                    )
                active = selected
            elif context_changed and paragraph_has_eds:
                active = None
            if active is None or not paragraph_has_eds:
                continue
            for location in _numeric_microanalysis_mentions(sentence):
                located = _NumericMicroanalysisOwner(
                    target=active.target,
                    state=active.state,
                    binding_evidence=tuple(
                        dict.fromkeys([*active.binding_evidence, sentence])
                    ),
                    owner_evidence=active.owner_evidence,
                )
                existing = candidates.setdefault(location, {}).get(active.target)
                if existing is None:
                    candidates[location][active.target] = located
                else:
                    candidates[location][active.target] = _NumericMicroanalysisOwner(
                        target=active.target,
                        state=active.state,
                        binding_evidence=tuple(
                            dict.fromkeys(
                                [
                                    *existing.binding_evidence,
                                    *located.binding_evidence,
                                ]
                            )
                        ),
                        owner_evidence=tuple(
                            dict.fromkeys(
                                [*existing.owner_evidence, *active.owner_evidence]
                            )
                        ),
                    )
    return {
        location: next(iter(owners.values()))
        for location, owners in candidates.items()
        if len(owners) == 1
    }


def _recover_numeric_microanalysis_location_owners(
    anchors: Sequence[InventoryAnchor], facts: Sequence[AxisFact], source_text: str
) -> tuple[list[AxisFact], list[MaterializeIssue]]:
    """Attach bare numeric EDS rows to one source-proven target owner."""

    fact_rows = list(facts)
    index = _build_identity_index(anchors, fact_rows)
    source_locations = _source_numeric_eds_table_locations(source_text)
    source_owners = _source_numeric_microanalysis_owner_map(index, source_text)
    recovered: dict[str, dict[str, Any]] = {}
    for fact_index, fact in enumerate(fact_rows):
        if not _numeric_microanalysis_composition_row(
            fact, source_locations=source_locations
        ):
            continue
        location_id = _numeric_microanalysis_location(fact)
        selected = source_owners.get(location_id)
        if selected is None:
            continue
        observation_location = f"Point {location_id}"
        data = deepcopy(fact.data)
        before_state = str(data.get("material_state") or "").strip()
        data["sample_id"] = observation_location
        data["material_state"] = selected.state
        data["_microanalysis_owner_recovered"] = True
        data["source_evidence"] = list(
            dict.fromkeys(
                [
                    *_evidence(data.get("source_evidence")),
                    *selected.binding_evidence,
                    *selected.owner_evidence,
                ]
            )
        )
        routed = fact.model_copy(
            update={
                "sample_id_raw": index.display_label(selected.target),
                "data": data,
                "source_evidence": list(
                    dict.fromkeys(
                        [
                            *fact.source_evidence,
                            *selected.binding_evidence,
                            *selected.owner_evidence,
                        ]
                    )
                ),
            }
        )
        fact_rows[fact_index] = routed
        audit = recovered.setdefault(
            selected.target,
            {
                "after_owner": index.display_label(selected.target),
                "before_owners": [],
                "locations": [],
                "facts": [],
                "binding_evidence": [],
                "owner_evidence": [],
                "state_corrections": [],
            },
        )
        audit["before_owners"].append(str(fact.sample_id_raw or "").strip())
        audit["locations"].append(observation_location)
        audit["facts"].append(fact.model_dump())
        audit["binding_evidence"].extend(selected.binding_evidence)
        audit["owner_evidence"].extend(selected.owner_evidence)
        if before_state != selected.state:
            audit["state_corrections"].append(
                {
                    "location": observation_location,
                    "before_state": before_state,
                    "after_state": selected.state,
                    "source_evidence": list(selected.binding_evidence),
                }
            )

    issues: list[MaterializeIssue] = []
    for audit in recovered.values():
        before_owners = list(dict.fromkeys(audit["before_owners"]))
        locations = list(dict.fromkeys(audit["locations"]))
        binding_evidence = list(dict.fromkeys(audit["binding_evidence"]))
        owner_evidence = list(dict.fromkeys(audit["owner_evidence"]))
        issues.append(
            MaterializeIssue(
                code="numeric_microanalysis_owner_recovered",
                sample_id_raw=audit["after_owner"],
                path=f"items.{audit['after_owner']}.Composition_Observations",
                message=(
                    "Numeric measured microanalysis rows were attached to the "
                    "only source-backed material state owning those locations."
                ),
                evidence=[*binding_evidence, *owner_evidence],
                expected={
                    "owner": "one explicit target sample and state",
                    "observation_location": "preserved Point label",
                },
                actual={
                    "before_owner": before_owners[0]
                    if len(before_owners) == 1
                    else before_owners,
                    "after_owner": audit["after_owner"],
                    "observation_location": locations[0]
                    if len(locations) == 1
                    else locations,
                    "binding_evidence": binding_evidence,
                    "owner_evidence": owner_evidence,
                    "state_corrections": audit["state_corrections"],
                    "facts": audit["facts"],
                },
                suggested_action=(
                    "Review only if the numbered EDS location belongs to a "
                    "different source sample."
                ),
            )
        )
    return fact_rows, issues


def materialize_candidate(
    anchors: Iterable[InventoryAnchor],
    facts: Iterable[AxisFact],
    *,
    paper_metadata: dict[str, Any] | None = None,
    paper_routing: dict[str, Any] | None = None,
    source_text: str | None = None,
) -> MaterializationResult:
    """Reconcile grounded fragments without paper- or material-specific rules."""

    routing = dict(paper_routing or {})
    anchor_rows = list(anchors)
    quality_mode = _claim_quality_mode()
    quality_gate = (
        filter_axis_facts(facts, mode=quality_mode)
        if quality_mode != "off"
        else None
    )
    fact_rows = quality_gate.accepted if quality_gate is not None else list(facts)
    anchor_rows, fact_rows, reference_owner_issues = (
        _recover_cited_nominal_composition_owners(anchor_rows, fact_rows)
    )
    fact_rows, microanalysis_owner_issues = (
        _recover_microanalysis_location_owners(
            anchor_rows, fact_rows, source_text
        )
    )
    fact_rows, numeric_microanalysis_owner_issues = (
        _recover_numeric_microanalysis_location_owners(
            anchor_rows, fact_rows, source_text or ""
        )
    )
    issues = _chart_quarantine_issues_from_text(source_text)
    issues.extend(reference_owner_issues)
    issues.extend(microanalysis_owner_issues)
    issues.extend(numeric_microanalysis_owner_issues)
    property_context_index = PropertyContextIndex(source_text)
    if quality_gate is not None:
        issues.extend(
            MaterializeIssue(
                code=issue.code,
                sample_id_raw=issue.sample_id_raw,
                path=issue.path,
                message=issue.message,
                evidence=issue.evidence,
                expected=issue.expected,
                actual=issue.actual,
                suggested_action=issue.suggested_action,
            )
            for issue in quality_gate.issues
        )
    chart_csv_references = _chart_series_csv_references(source_text)
    audited_non_material: set[str] = set()
    for anchor in anchor_rows:
        reassigned, _ = _citation_owner(anchor)
        is_removed = (
            reassigned is None
            or _is_non_material_label(anchor.sample_id_raw)
            or _anchor_is_structural_entity(anchor)
            or not is_plausible_material_identity(anchor.sample_id_raw)
        )
        audit_key = _identity_key(anchor.sample_id_raw)
        if not is_removed or not audit_key or audit_key in audited_non_material:
            continue
        audited_non_material.add(audit_key)
        issues.append(
            MaterializeIssue(
                code="non_material_item_removed",
                sample_id_raw=anchor.sample_id_raw,
                path=f"items.{anchor.sample_id_raw}",
                message=(
                    "The source label was excluded because it does not satisfy the "
                    "material-item identity contract."
                ),
                evidence=list(anchor.source_evidence),
                expected={"identity": "explicit material or independent source sample"},
                actual=anchor.model_dump(),
                suggested_action="Review the source label only if it is an independent material sample.",
            )
        )
    identity_index = _build_identity_index(anchor_rows, fact_rows)
    descriptor_owners: dict[str, set[str]] = {}
    for canonical, indexed_anchors in identity_index.anchors.items():
        for anchor in indexed_anchors:
            for descriptor in _identity_alias_keys(anchor.material_name_raw):
                if descriptor:
                    descriptor_owners.setdefault(descriptor, set()).add(canonical)
    exact_fact_owners: dict[str, set[str]] = {}
    for fact in fact_rows:
        primary_owners = _fact_primary_owners(identity_index, fact)
        if primary_owners:
            exact_fact_owners.setdefault(
                _owner_agnostic_fact_signature(fact), set()
            ).update(primary_owners)
    groups: dict[str, dict[str, Any]] = {}
    owner_state_audits: dict[
        tuple[str, str, str], dict[str, list[Any]]
    ] = {}
    for fact in fact_rows:
        declared_targets = _fact_declared_targets(identity_index, fact)
        targets = _group_route(identity_index, fact)
        if not targets:
            labels = [*_fact_identity_labels(fact), fact.sample_id_raw]
            is_element = any(_is_element_symbol(label) for label in labels)
            issues.append(
                MaterializeIssue(
                    code=(
                        "unresolved_element_sample"
                        if is_element
                        else "unresolved_sample_alias"
                    ),
                    sample_id_raw=fact.sample_id_raw,
                    message=(
                        "The fact was not materialized because no evidence-derived "
                        "sample identity could be resolved."
                    ),
                    evidence=list(fact.source_evidence),
                    expected={"owner": "one evidence-derived material identity"},
                    actual=fact.model_dump(),
                    suggested_action="Review the source sample attribution.",
                )
            )
            continue
        if len(declared_targets) == 1 and len(targets) == 1:
            previous = declared_targets[0]
            selected = targets[0]
            previous_base = identity_index.state_family_base.get(previous, previous)
            selected_base = identity_index.state_family_base.get(selected, selected)
            if selected != previous and selected_base == previous_base:
                before_owner = identity_index.display_label(previous)
                after_owner = identity_index.display_label(selected)
                local_state = _fact_material_state_label(fact)
                rule = (
                    "observation_local_material_state"
                    if local_state
                    else "unique_state_evidence"
                )
                audit = owner_state_audits.setdefault(
                    (before_owner, after_owner, rule),
                    {"facts": [], "evidence": []},
                )
                audit["facts"].append(fact.model_dump())
                audit["evidence"].append(
                    {
                        "fact_index": len(audit["facts"]) - 1,
                        "source_evidence": list(fact.source_evidence),
                        "material_state": local_state or None,
                    }
                )
        if not _fact_primary_owners(identity_index, fact):
            related_specific_owners = {
                owner
                for label in [*_fact_identity_labels(fact), fact.sample_id_raw]
                for owner in descriptor_owners.get(_identity_key(label), set())
            }
            duplicate_owners = exact_fact_owners.get(
                _owner_agnostic_fact_signature(fact), set()
            )
            if related_specific_owners & duplicate_owners:
                # A generic cross-chunk label may coexist with a source sample
                # code such as L70.  When the complete semantic fact is already
                # owned by that related primary sample, retain the more
                # specific attribution instead of duplicating it on the generic
                # material family.  Non-duplicate facts remain eligible for the
                # unique qualified-base alias above.
                continue
        if len(targets) > 1:
            issues.append(
                MaterializeIssue(
                    code="shared_fact_routed",
                    sample_id_raw=fact.sample_id_raw,
                    message=(
                        "A comparison/shared fact named multiple known samples and was "
                        "attached to each without creating a combined material item."
                    ),
                )
            )
        for canonical in targets:
            group = groups.setdefault(
                canonical,
                {
                    "canonical": canonical,
                    "anchors": identity_index.anchors.get(canonical, []),
                    "facts": [],
                },
            )
            group["facts"].append(fact)

    for (before_owner, after_owner, rule), audit in sorted(
        owner_state_audits.items()
    ):
        fact_count = len(audit["facts"])
        issues.append(
            MaterializeIssue(
                code="fact_owner_state_reconciled",
                sample_id_raw=after_owner,
                path=f"items.{after_owner}",
                message=(
                    f"{fact_count} fact{'s' if fact_count != 1 else ''} declared on "
                    "a material family were narrowed to the only state in that "
                    "family supported by local evidence."
                ),
                evidence=audit["evidence"],
                expected={
                    "binding": "one source-backed state in the declared material family",
                    "broadcast": False,
                },
                actual={
                    "before_owner": before_owner,
                    "after_owner": after_owner,
                    "rule": rule,
                    "facts": audit["facts"],
                },
                suggested_action=(
                    "Review the copied state label if the source uses the same "
                    "qualifier for multiple material states."
                ),
            )
        )

    items: list[dict[str, Any]] = []
    sorted_groups = sorted(
        (
            group
            for group in groups.values()
            if any(fact.fact_type != "material_identity" for fact in group["facts"])
        ),
        key=lambda row: row["canonical"],
    )
    for item_index, group in enumerate(sorted_groups, start=1):
        sample_id = identity_index.display_label(group["canonical"])
        role, data_nature = _group_role_and_nature(group["anchors"])
        if role == "Reference" and not _reference_has_independent_fact(group["facts"]):
            issues.append(
                MaterializeIssue(
                    code="reference_without_independent_fact_removed",
                    sample_id_raw=sample_id,
                    path=f"items.{sample_id}",
                    message=(
                        "The reference item was removed because it carried only "
                        "identity or relational comparison assertions."
                    ),
                    evidence=[
                        evidence
                        for fact in group["facts"]
                        for evidence in fact.source_evidence
                    ],
                    expected={"reference": "at least one independently owned fact"},
                    actual=[fact.model_dump() for fact in group["facts"]],
                    suggested_action="Retain only if the reference owns a standalone reported fact.",
                )
            )
            continue
        grouped_facts: dict[str, list[dict[str, Any]]] = {}
        if quality_mode != "off":
            deduplicated = deduplicate_axis_facts_with_audit(
                group["facts"], mode=quality_mode
            )
            group_facts = deduplicated.accepted
            issues.extend(
                MaterializeIssue(
                    code=issue.code,
                    sample_id_raw=issue.sample_id_raw,
                    path=issue.path,
                    message=issue.message,
                    evidence=issue.evidence,
                    expected=issue.expected,
                    actual=issue.actual,
                    suggested_action=issue.suggested_action,
                )
                for issue in deduplicated.issues
            )
        else:
            group_facts = group["facts"]
        for fact in group_facts:
            grouped_facts.setdefault(fact.fact_type, []).append(_fact_data(fact))

        identities = _group_material_identities(group)
        material_identity, identity_replaced = _select_material_identity(
            identities, sample_id=sample_id
        )
        if identity_replaced:
            issues.append(
                MaterializeIssue(
                    code="material_identity_descriptor_replaced",
                    sample_id_raw=sample_id,
                    path=f"items.{sample_id}.Composition.Material_Identity",
                    message=(
                        "A morphology-only material name was replaced by a fuller "
                        "source-grounded identity from the same reconciled owner."
                    ),
                    evidence=[
                        evidence
                        for fact in group["facts"]
                        for evidence in fact.source_evidence
                    ],
                    expected={
                        "material_identity": (
                            "material family, designation, or explicit material name"
                        )
                    },
                    actual={
                        "before": deepcopy(identities[0]),
                        "after": deepcopy(material_identity),
                        "candidates": deepcopy(identities),
                    },
                    suggested_action=(
                        "Review only if the morphology phrase is itself the source's "
                        "formal material designation."
                    ),
                )
            )
        if len(identities) > 1:
            issues.append(
                MaterializeIssue(
                    code="conflicting_material_identity",
                    sample_id_raw=sample_id,
                    message="Multiple grounded material identities were preserved for review.",
                )
            )

        stages = _deduplicate(grouped_facts.get("process_stage", []))
        stage_id_map: dict[str, str] = {}
        for stage_index, stage in enumerate(stages, start=1):
            old_id = str(stage.get("candidate_stage_id") or "")
            new_id = f"cand_{stage_index:03d}"
            if old_id:
                stage_id_map[old_id] = new_id
            stage["candidate_stage_id"] = new_id
            stage["stage_index_candidate"] = stage_index
            # No frozen process-code allowlist enters an axis task. Preserve the
            # raw name and let alpha25 resolve it deterministically.
            stage["process_code_candidate"] = None
            stage.setdefault("process_role_candidate", "unspecified")
            stage["parameters_raw"] = _sanitize_parameters(
                stage.get("parameters_raw"), _evidence(stage.get("source_evidence"))
            )

        edges = _deduplicate(grouped_facts.get("process_edge", []))
        sanitized_edges: list[dict[str, Any]] = []
        valid_stage_ids = {stage["candidate_stage_id"] for stage in stages}
        for edge in edges:
            for key in ("source_candidate_stage_id", "target_candidate_stage_id"):
                if edge.get(key) in stage_id_map:
                    edge[key] = stage_id_map[edge[key]]
            edge_type = str(edge.get("edge_type") or "").strip().casefold()
            if edge_type in {"linear", "sequential", "sequence"}:
                edge_type = "next"
            edge["edge_type"] = edge_type
            if (
                edge_type not in _PROCESS_EDGE_TYPES
                or edge.get("source_candidate_stage_id") not in valid_stage_ids
                or edge.get("target_candidate_stage_id") not in valid_stage_ids
                or edge.get("source_candidate_stage_id")
                == edge.get("target_candidate_stage_id")
            ):
                continue
            sanitized_edges.append(edge)
        edges = _deduplicate(sanitized_edges)
        has_explicit_non_linear_edge = any(
            edge.get("edge_type") in {"branch", "merge", "parallel"}
            for edge in edges
        )
        if not has_explicit_non_linear_edge or not _explicit_process_graph_is_valid(
            valid_stage_ids, edges
        ):
            # An isolated branch/merge/parallel label is not a graph. Let the
            # official runner use the already explicit stage order as its
            # conservative linear fallback. Redundant next edges are omitted
            # too, because a rejected stage could otherwise leave a fatal
            # dangling endpoint after ontology normalization.
            edges = []

        sanitized_composition_observations: list[dict[str, Any]] = []
        reclassified_structure_observations: list[dict[str, Any]] = []
        for observation in grouped_facts.get("composition_observation", []):
            eligible, quarantined_components = (
                _partition_wrong_axis_composition_components(observation)
            )
            residual_quarantine: list[dict[str, Any]] = []
            for component in quarantined_components:
                structural = _composition_component_to_structure_observation(
                    component, observation, sample_id
                )
                if structural is None:
                    residual_quarantine.append(component)
                    continue
                reclassified_structure_observations.append(structural)
                issues.append(
                    MaterializeIssue(
                        code="fact_axis_reclassified",
                        sample_id_raw=sample_id,
                        path=f"items.{sample_id}.Structure",
                        message=(
                            "An explicit structural component measurement was moved "
                            "from Composition to Structure."
                        ),
                        evidence=_evidence(observation.get("source_evidence")),
                        expected={"axis": "Structure"},
                        actual={
                            "previous_axis": "Composition",
                            "component": deepcopy(component),
                            "raw_expression": observation.get("raw_expression"),
                        },
                        suggested_action="Review the deterministic axis migration.",
                    )
                )
            if residual_quarantine:
                issues.append(
                    MaterializeIssue(
                        code="fact_quarantined_wrong_axis",
                        sample_id_raw=sample_id,
                        path=f"items.{sample_id}.Composition",
                        message=(
                            "Numeric component values with non-composition units "
                            "were quarantined from Composition."
                        ),
                        evidence=_evidence(observation.get("source_evidence")),
                        expected={"axis": "Composition", "unit_family": "composition amount"},
                        actual={
                            "raw_expression": observation.get("raw_expression"),
                            "components": residual_quarantine,
                        },
                        suggested_action="Review whether the values belong to another semantic axis.",
                    )
                )
            sanitized = (
                _sanitize_composition_observation(eligible)
                if eligible is not None
                else None
            )
            if sanitized is not None:
                sanitized_composition_observations.extend(
                    _split_mixed_composition_observation(sanitized)
                )
        composition_observations = _deduplicate(
            sanitized_composition_observations
        )
        for obs_index, observation in enumerate(composition_observations, start=1):
            observation["observation_id"] = f"comp_obs_{obs_index:03d}"
            recovered_location = bool(
                observation.pop("_microanalysis_owner_recovered", False)
            )
            if not recovered_location:
                observation["sample_id"] = sample_id

        raw_structure_observations = list(
            grouped_facts.get("structure_observation", [])
        ) + reclassified_structure_observations
        sanitized_properties: list[dict[str, Any]] = []
        for prop in grouped_facts.get("property", []):
            structural = _property_to_structure_observation(prop, sample_id)
            if structural is not None:
                raw_structure_observations.append(structural)
                issues.append(
                    MaterializeIssue(
                        code="fact_axis_reclassified",
                        sample_id_raw=sample_id,
                        path=f"items.{sample_id}.Structure",
                        message=(
                            "An explicit structural measurement was moved from "
                            "Properties to Structure."
                        ),
                        evidence=_evidence(prop.get("source_evidence")),
                        expected={"axis": "Structure"},
                        actual={"previous_axis": "Properties", "fact": deepcopy(prop)},
                        suggested_action="Review the deterministic axis migration.",
                    )
                )
                continue
            context_decision = property_context_index.recover(prop, owner_role=role)
            if context_decision.status == "recovered":
                original_prop = deepcopy(prop)
                prop = deepcopy(prop)
                prop["test_condition_raw"] = context_decision.condition_raw
                issues.append(
                    MaterializeIssue(
                        code="property_test_context_recovered",
                        sample_id_raw=sample_id,
                        path=f"items.{sample_id}.Properties",
                        message=(
                            "An empty Property test condition was restored from the "
                            "unique compatible tensile procedure in the complete source text."
                        ),
                        evidence=[
                            candidate.audit_dict()
                            for candidate in context_decision.selected
                        ],
                        expected={
                            "binding": "one source-verbatim compatible test context",
                            "overwrite_existing_condition": False,
                        },
                        actual={
                            "before": original_prop,
                            "after": deepcopy(prop),
                            "reason": context_decision.reason,
                        },
                        suggested_action=(
                            "Review the source line spans if this paper uses multiple "
                            "tensile protocols for the same property family."
                        ),
                    )
                )
            elif context_decision.status == "reference":
                issues.append(
                    MaterializeIssue(
                        code="property_test_context_not_applied_to_reference",
                        sample_id_raw=sample_id,
                        path=f"items.{sample_id}.Properties",
                        message=(
                            "The Property was preserved without inheriting the current "
                            "paper's tensile procedure because its provenance is reference-like."
                        ),
                        evidence=_evidence(prop.get("source_evidence")),
                        expected={
                            "binding": "current-paper results only",
                            "action": "preserve the original empty condition for reference facts",
                        },
                        actual={
                            "fact": deepcopy(prop),
                            "owner_role": role,
                            "reason": context_decision.reason,
                        },
                        suggested_action=(
                            "Bind a test condition only if property-local source evidence "
                            "identifies the protocol used for this cited value."
                        ),
                    )
                )
            elif context_decision.status == "ambiguous":
                issues.append(
                    MaterializeIssue(
                        code="ambiguous_property_test_context",
                        sample_id_raw=sample_id,
                        path=f"items.{sample_id}.Properties",
                        message=(
                            "The Property condition remained unchanged because multiple "
                            "incompatible tensile procedures could not be resolved from "
                            "property-local evidence."
                        ),
                        evidence=[
                            candidate.audit_dict()
                            for candidate in context_decision.candidates
                        ],
                        expected={
                            "binding": "one uniquely supported test context",
                            "action": "preserve the original empty condition when ambiguous",
                        },
                        actual={
                            "fact": deepcopy(prop),
                            "reason": context_decision.reason,
                        },
                        suggested_action=(
                            "Manually bind the condition only when the source identifies "
                            "which protocol produced this value."
                        ),
                    )
                )
            invalid_series = _invalid_nonnegative_chart_series(
                prop,
                chart_csv_references=chart_csv_references,
            )
            if invalid_series is not None:
                issues.append(
                    MaterializeIssue(
                        code="curve_series_quarantined",
                        sample_id_raw=sample_id,
                        path=f"items.{sample_id}.Properties",
                        message=(
                            "A chart series contradicted its explicitly non-negative "
                            "tensile axis and was quarantined."
                        ),
                        evidence=_evidence(prop.get("source_evidence")),
                        expected={"axis_minimum": 0, "quantity": "tensile stress/strength"},
                        actual=invalid_series,
                        suggested_action="Review the preserved chart CSV and axis calibration.",
                    )
                )
                continue
            sanitized = _sanitize_property(prop)
            if sanitized is not None:
                sanitized_properties.append(sanitized)

        structure_observations = _deduplicate(
            sanitized
            for observation in raw_structure_observations
            if (sanitized := _sanitize_structure_observation(observation)) is not None
        )
        for obs_index, observation in enumerate(structure_observations, start=1):
            observation["observation_id"] = f"str_obs_{obs_index:03d}"
            observation["sample_id"] = sample_id

        characterizations = _deduplicate(grouped_facts.get("characterization", []))
        for char_index, characterization in enumerate(characterizations, start=1):
            characterization["characterization_id"] = f"char_{char_index:03d}"

        properties = _deduplicate(sanitized_properties)
        for property_index, prop in enumerate(properties, start=1):
            prop["property_id_candidate"] = f"prop_{property_index:03d}"

        composition = {
            "Composition_Text": _text_pair([], nullable=False),
            "Composition_Observations": composition_observations,
        }
        if material_identity:
            composition["Material_Identity"] = material_identity
        process_text_records = grouped_facts.get("process_text", [])
        if process_text_records and not stages:
            # A prose-only processing assertion cannot satisfy alpha25's
            # evidence-first route contract. Keep the cached raw fact for a
            # later repair pass, but do not promote it into a contradictory
            # item that claims a state-changing process with an empty route.
            issues.append(
                MaterializeIssue(
                    code="process_text_without_stage_discarded",
                    sample_id_raw=sample_id,
                    message=(
                        "Process text was not promoted because no grounded process "
                        "stage for this material item was extracted."
                    ),
                )
            )
            process_text_records = []
        process_text = _text_pair(process_text_records, nullable=False)
        structure_text = _text_pair(
            grouped_facts.get("structure_text", []), nullable=not structure_observations
        )
        structure = {
            "Structure_Text": structure_text,
            "structure_status": "reported" if structure_observations else "not_reported",
            "Structure_Observations": structure_observations,
        }
        if characterizations:
            structure["Characterization"] = characterizations

        item = {
                "Item_ID": f"item_{item_index:03d}",
                "Sample_ID": sample_id,
                "Role": role,
                "Data_Nature": data_nature,
                "base_material": _route_value(routing, "base_material", "Metals"),
                "application": _route_value(routing, "application", "Structural"),
                "research_paradigm": _route_value(
                    routing, "research_paradigm", "Experimental"
                ),
                "Extracted_Data": {
                    "Composition": composition,
                    "Processing": {
                        "Process_Text": process_text,
                        "Process_Route": {
                            "candidate_stages": stages,
                            "candidate_edges": edges,
                        },
                    },
                    "Structure": structure,
                    "Properties": properties,
                },
            }
        if _item_has_substantive_data(item) or grouped_facts.get("process_text"):
            items.append(item)
        else:
            issues.append(
                MaterializeIssue(
                    code="empty_item_removed",
                    sample_id_raw=sample_id,
                    path=f"items.{sample_id}",
                    message=(
                        "The material item was removed after all ineligible facts "
                        "were quarantined or discarded."
                    ),
                    evidence=[
                        evidence
                        for fact in group["facts"]
                        for evidence in fact.source_evidence
                    ],
                    expected={"item": "at least one substantive eligible fact"},
                    actual=[fact.model_dump() for fact in group["facts"]],
                    suggested_action="Review the associated quarantine issues.",
                )
            )

    for item_index, item in enumerate(items, start=1):
        item["Item_ID"] = f"item_{item_index:03d}"
    return MaterializationResult(
        document={
            "Paper_Metadata": dict(paper_metadata or {}),
            "Paper_Routing": {
                "base_material": _route_value(routing, "base_material", "Metals"),
                "application": _route_value(routing, "application", "Structural"),
                "research_paradigm": _route_value(
                    routing, "research_paradigm", "Experimental"
                ),
            },
            "items": items,
        },
        issues=issues,
    )


def reconcile_candidate_documents(candidates: Iterable[dict[str, Any]]) -> dict[str, Any]:
    """Merge full candidates only by exact normalized source identity."""

    rows = [deepcopy(row) for row in candidates if isinstance(row, dict)]
    if not rows:
        return {"Paper_Metadata": {}, "Paper_Routing": {}, "items": []}
    metadata = next((row.get("Paper_Metadata") for row in rows if row.get("Paper_Metadata")), {})
    routing = next((row.get("Paper_Routing") for row in rows if row.get("Paper_Routing")), {})
    grouped: dict[tuple[str, str, str], list[dict[str, Any]]] = {}
    order: list[tuple[str, str, str]] = []
    for document in rows:
        for item in document.get("items", []) or []:
            if not isinstance(item, dict):
                continue
            key = (
                normalize_source_alias(item.get("Sample_ID") or item.get("Item_ID")),
                str(item.get("Role") or "Target"),
                str(item.get("Data_Nature") or "Experimental"),
            )
            if key not in grouped:
                grouped[key] = []
                order.append(key)
            grouped[key].append(item)

    merged_items: list[dict[str, Any]] = []
    for item_index, key in enumerate(order, start=1):
        source_items = grouped[key]
        merged = deepcopy(source_items[0])
        merged["Item_ID"] = f"item_{item_index:03d}"
        extracted = merged.setdefault("Extracted_Data", {})
        for incoming in source_items[1:]:
            incoming_data = incoming.get("Extracted_Data") or {}
            for axis, list_keys in {
                "Composition": ("Composition_Observations",),
                "Processing": (),
                "Structure": ("Structure_Observations", "Characterization"),
            }.items():
                target_axis = extracted.setdefault(axis, {})
                source_axis = incoming_data.get(axis) or {}
                _merge_record(target_axis, source_axis)
                for list_key in list_keys:
                    target_axis[list_key] = _deduplicate(
                        [*(target_axis.get(list_key) or []), *(source_axis.get(list_key) or [])]
                    )
            extracted["Properties"] = _deduplicate(
                [
                    *(extracted.get("Properties") or []),
                    *(incoming_data.get("Properties") or []),
                ]
            )
            target_route = extracted.setdefault("Processing", {}).setdefault(
                "Process_Route", {}
            )
            source_route = (incoming_data.get("Processing") or {}).get("Process_Route") or {}
            for route_key in ("candidate_stages", "candidate_edges"):
                target_route[route_key] = _deduplicate(
                    [*(target_route.get(route_key) or []), *(source_route.get(route_key) or [])]
                )
        merged_items.append(merged)
    return {"Paper_Metadata": metadata, "Paper_Routing": routing, "items": merged_items}
