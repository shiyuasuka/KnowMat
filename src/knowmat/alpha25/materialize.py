"""Generic reconciliation and candidate materialization for alpha25 facts."""

from __future__ import annotations

import json
import os
import re
import unicodedata
from collections import Counter
from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

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
    core_tensile_subtype,
    deduplicate_axis_facts_with_audit,
    filter_axis_facts,
    is_core_tensile_property_name,
    semantic_fact_signature,
)
from knowmat.alpha25.evidence import (
    table_projection_supports_record,
    unique_ordered_table_row_projection,
)
from knowmat.alpha25.property_context import (
    PropertyContextDecision,
    PropertyContextIndex,
    TensileProtocolLedger,
    has_explicit_global_tensile_scope,
)
from knowmat.alpha25.source_coordinates import (
    DenseTensileCell,
    dense_tensile_table_decisions,
    discrete_tensile_sidecars,
    logical_tables,
    resolve_structured_table_record,
)


_ID_FIELDS = {
    "candidate_stage_id",
    "stage_index_candidate",
    "property_id_candidate",
    "observation_id",
    "characterization_id",
    "entity_id",
}
_EVIDENCE_FIELDS = {"source_evidence", "confidence"}


def global_tensile_scope_v201_enabled() -> bool:
    """Return whether the v201 global tensile exception is enabled.

    The default is production-on.  Disabling it restores the conservative
    current-code shadow behavior in which a shared protocol is never projected
    solely from a unique table owner plus a paper-global tensile statement.
    """

    raw = os.getenv("KNOWMAT2_ALPHA25_GLOBAL_TENSILE_SCOPE_V201", "1")
    return raw.strip().casefold() not in {
        "0",
        "false",
        "no",
        "off",
        "disabled",
    }


def discrete_chart_sidecar_v202_enabled() -> bool:
    """Return whether bounded categorical chart sidecars may be promoted."""

    raw = os.getenv("KNOWMAT2_ALPHA25_DISCRETE_CHART_SIDECAR_V202", "1")
    return raw.strip().casefold() not in {
        "0",
        "false",
        "no",
        "off",
        "disabled",
    }


def owner_state_condition_v202_enabled() -> bool:
    """Return whether source-literal state/condition attribution is enabled."""

    raw = os.getenv("KNOWMAT2_ALPHA25_OWNER_STATE_CONDITION_V202", "1")
    return raw.strip().casefold() not in {
        "0",
        "false",
        "no",
        "off",
        "disabled",
    }


def source_coordinate_precision_v202_enabled() -> bool:
    """Return whether one-source-coordinate precision gates are enabled."""

    raw = os.getenv("KNOWMAT2_ALPHA25_SOURCE_COORDINATE_PRECISION_V202", "1")
    return raw.strip().casefold() not in {
        "0",
        "false",
        "no",
        "off",
        "disabled",
    }


def dense_tensile_table_completion_v203_enabled() -> bool:
    """Return whether explicit Target tensile table cells may be completed."""

    raw = os.getenv(
        "KNOWMAT2_ALPHA25_DENSE_TENSILE_TABLE_COMPLETION_V203", "1"
    )
    return raw.strip().casefold() not in {
        "0",
        "false",
        "no",
        "off",
        "disabled",
    }


def property_coordinate_quarantine_v203_enabled() -> bool:
    """Return whether source-proven v203 Property quarantine is enabled."""

    raw = os.getenv(
        "KNOWMAT2_ALPHA25_PROPERTY_COORDINATE_QUARANTINE_V203", "1"
    )
    return raw.strip().casefold() not in {
        "0",
        "false",
        "no",
        "off",
        "disabled",
    }


_CHARACTERIZATION_METHOD_ALIASES = (
    (
        "ebsd",
        re.compile(r"\b(?:ebsd|electron backscatter(?:ed)? diffraction)\b", re.I),
        re.compile(
            r"^(?:ebsd|electron backscatter(?:ed)? diffraction(?: ebsd)?)$", re.I
        ),
    ),
    (
        "eds",
        re.compile(
            r"\b(?:eds|edx|energy dispersive(?: x ray)? "
            r"(?:spectroscopy|spectrometer))\b",
            re.I,
        ),
        re.compile(
            r"^(?:eds|edx|energy dispersive(?: x ray)? "
            r"(?:spectroscopy|spectrometer)(?: eds| edx)?)$",
            re.I,
        ),
    ),
    (
        "xrd",
        re.compile(r"\b(?:xrd|x ray diffraction)\b", re.I),
        re.compile(r"^(?:xrd|x ray diffraction(?: xrd)?)$", re.I),
    ),
    (
        "apt",
        re.compile(r"\b(?:apt|atom probe tomography)\b", re.I),
        re.compile(r"^(?:3d )?(?:apt|atom probe tomography(?: apt)?)$", re.I),
    ),
    (
        "hrtem",
        re.compile(
            r"\b(?:hrtem|high resolution (?:tem|transmission electron microscopy))\b",
            re.I,
        ),
        re.compile(
            r"^(?:hrtem|high resolution (?:tem|transmission electron "
            r"microscopy)(?: hrtem)?)$",
            re.I,
        ),
    ),
    (
        "stem",
        re.compile(
            r"\b(?:(?:haadf|adf|abf|bf|df) )?"
            r"(?:stem|scanning transmission electron microscopy)\b",
            re.I,
        ),
        re.compile(
            r"^(?:stem|scanning transmission electron microscopy(?: stem)?)$",
            re.I,
        ),
    ),
    (
        "tem",
        re.compile(r"\b(?:tem|transmission electron microscopy)\b", re.I),
        re.compile(r"^(?:tem|transmission electron microscopy(?: tem)?)$", re.I),
    ),
    (
        "sem",
        re.compile(
            r"\b(?:(?:fe|bse|se) )?"
            r"(?:sem|scanning electron microscop(?:y|e))\b",
            re.I,
        ),
        re.compile(
            r"^(?:sem|scanning electron microscop(?:y|e)(?: sem)?)$",
            re.I,
        ),
    ),
    (
        "optical_microscopy",
        re.compile(
            r"\b(?:om|lom|light optical microscopy|optical microscop(?:y|e))\b",
            re.I,
        ),
        re.compile(
            r"^(?:om|lom|light optical microscopy(?: lom)?|"
            r"optical microscop(?:y|e)(?: om)?)$",
            re.I,
        ),
    ),
    (
        "xray_tomography",
        re.compile(
            r"\b(?:micro ct|microct|xct|x ray (?:computed )?tomography|"
            r"computed tomography|ct)\b",
            re.I,
        ),
        re.compile(
            r"^(?:micro ct|microct|xct|x ray (?:computed )?tomography|"
            r"computed tomography(?: ct)?|ct)$",
            re.I,
        ),
    ),
)
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
_REFERENCE_NUMERIC_CITATION = re.compile(r"\[\s*(\d+)\s*\]")
_REFERENCE_STANDARD_MARKER = re.compile(
    r"(?i)\b(?:ASTM|AMS|ISO|DIN|EN)\s*[A-Z]?\s*[-/]?\s*\d+"
    r"(?:[A-Z0-9./:-]*\d|[A-Z])?\b"
)
_REFERENCE_AUTHOR_YEAR = re.compile(
    r"(?<![A-Za-z])(?:[A-Z][A-Za-z'’.-]{2,})"
    r"(?:\s+et\s+al\.?)?\s*,?\s*\(?(?:19|20)\d{2}[a-z]?\)?"
)
_REFERENCE_CURRENT_STUDY = re.compile(
    r"(?i)\b(?:this|current|present)\s+(?:work|study)|\bour\s+(?:work|study)\b"
)
_REFERENCE_TABLE_CAPTION = re.compile(
    r"(?i)^\s*(?P<scope>Table\s+\d+[A-Za-z]?)"
    r"(?=\s|[.:])(?P<caption>.*)\s*$"
)
_REFERENCE_PROSE_AUTHOR = re.compile(
    r"(?<![A-Za-z])(?P<author>[A-Z][A-Za-zÀ-ÖØ-öø-ÿ'’.-]{1,}"
    r"\s+et\s+al\.?)"
)
_REFERENCE_PROSE_REPORTING_VERB = re.compile(
    r"(?i)\b(?:report(?:ed|s|ing)?|show(?:ed|s|ing)?|"
    r"demonstrat(?:e|ed|es|ing)|describe(?:d|s|ing)?|find|finds|found)\b"
)
_REFERENCE_PROSE_REPORTED_CONTINUATION = re.compile(
    r"(?is)\bthe\s+reported\b.{0,160}?\b(?:value|values|result|results|"
    r"propert(?:y|ies))\b"
)
_REFERENCE_PROSE_PRONOUN_CONTINUATION = re.compile(
    r"(?i)^\s*They\s+(?:report(?:ed|s)?|show(?:ed|s)?|"
    r"demonstrat(?:e|ed|es)|describe(?:d|s)?|find|finds|found)\b"
)
_REFERENCE_PROSE_SAME_STUDY = re.compile(
    r"(?i)\bby\s+the\s+same\s+(?:study|work)\b"
)
_REFERENCE_PROSE_PREVIOUS_WORK = re.compile(
    r"(?i)\b(?:our\s+)?(?:previous|prior|earlier)\s+(?:work|study)\b"
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
_PROCESS_ENVIRONMENT_MENTION = re.compile(
    r"(?ix)\b(?P<phrase>"
    r"(?:\d+(?:\.\d+)?\s*%\s*)?"
    r"(?:high[\s-]*purity\s+)?(?:inert\s+)?"
    r"(?:argon|nitrogen|helium|hydrogen)"
    r"(?:\s+(?:gas|atmosphere|environment))?"
    r"|(?:high[\s-]*|ultra[\s-]*high\s+)?vacuum"
    r"|(?:ambient\s+)?air"
    r"|inert\s+(?:gas|atmosphere|environment)"
    r")\b"
)
_PROCESS_ENVIRONMENT_CUE = re.compile(
    r"(?ix)\b(?:atmosphere|environment|vacuum|shield(?:ing|ed)?|purge[sd]?|"
    r"chamber|glovebox|performed\s+in|conducted\s+in|carried\s+out\s+in|"
    r"processed\s+in|fabricated\s+in|printed\s+in|deposited\s+in|"
    r"built\s+in|under)\b"
)
_PROCESS_FAMILY_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    (
        "additive_manufacturing",
        re.compile(
            r"(?ix)\b(?:additive(?:ly)?|3d[\s-]*print(?:ed|ing)?|print(?:ed|ing)|"
            r"fabricat(?:e|ed|ion)|manufactur(?:e|ed|ing)|depos(?:it|ited|ition)|"
            r"build|cladd?ing|melt(?:ed|ing)|ded|pbf|lpbf|ebm|slm|waam|lmd)\b"
        ),
    ),
    (
        "thermal_treatment",
        re.compile(
            r"(?ix)\b(?:heat[\s-]*treat(?:ed|ment|ing)?|anneal(?:ed|ing)?|"
            r"ag(?:e|ed|ing)|solution(?:ized|ising|izing|\s+treat(?:ed|ment)?)|"
            r"sinter(?:ed|ing)?|homogeni[sz](?:ed|ing|ation)|"
            r"hot\s+isostatic(?:ally)?\s+press(?:ed|ing)?|hip)\b"
        ),
    ),
    (
        "casting",
        re.compile(r"(?ix)\b(?:cast(?:ing)?|solidif(?:y|ied|ication))\b"),
    ),
    (
        "powder_preparation",
        re.compile(
            r"(?ix)\b(?:atomiz(?:e|ed|ation)|ball[\s-]*mill(?:ed|ing)?|"
            r"mechanical\s+alloy(?:ed|ing)|powder\s+prepar(?:ed|ation))\b"
        ),
    ),
    (
        "mechanical_processing",
        re.compile(
            r"(?ix)\b(?:roll(?:ed|ing)?|forg(?:ed|ing)|extrud(?:ed|ing)|"
            r"machin(?:ed|ing)|grind(?:ing)?|polish(?:ed|ing)?)\b"
        ),
    ),
    (
        "mechanical_test",
        re.compile(
            r"(?ix)\b(?:tensile|fatigue|creep|compression|hardness)\s+"
            r"(?:test(?:ed|ing|s)?|experiment(?:s|al)?)\b"
        ),
    ),
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
_TABLE_COLUMN_ID = re.compile(
    r"(?ix)^\s*(?:"
    r"\#\s*(?P<number>\d+)"
    r"|(?:point|spot|sample|specimen)\s*\#?\s*(?P<named_number>\d+)"
    r"|(?:no\.?|number)\s*\#?\s*(?P<no_number>\d+)"
    r")\s*$"
)
_TABLE_COLUMN_EXPLICIT_SAMPLE = re.compile(
    r"(?ix)(?<![A-Za-z0-9])(?:"
    r"(?:sample|specimen)\s*(?:\#\s*\d+|(?:number|no\.?)\s*\d+)"
    r"\s*(?:was|is|denotes?|corresponds?|represents?|refers?|"
    r"label(?:led|ed)?|designated)"
    r"|(?:\#\s*\d+|(?:point|spot|sample|specimen)\s*\#?\s*\d+)"
    r"\s+(?:sample|specimen)\s*(?:was|is|denotes?|corresponds?|"
    r"represents?|refers?|label(?:led|ed)?|designated)"
    r")\b"
)
_TABLE_COLUMN_SPECIMEN_CONTEXT = re.compile(
    r"(?i)\b(?:cuboid|coupon|replicate|specimen|sample)s?\b"
)
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
    # Source tables frequently use compact treatment codes (``HIP2``/``HT2``)
    # without a separator.  The trailing optional code must be part of the
    # category match; otherwise the whole composite state is treated as an
    # unclassified ``raw:...`` label and is dropped during state expansion.
    (
        "hip",
        re.compile(
            r"(?i)\b(?:hip\s*[-_]?\s*\d+|hip|hot\s+isostatic(?:ally)?\s+press(?:ed|ing)?)\b"
        ),
    ),
    ("thermal_exposure", re.compile(r"(?i)\b(?:thermal(?:ly)?\s+expos(?:ed|ure)|expos(?:ed|ure))\b")),
    ("laser_region", re.compile(r"(?i)\b(?:laser\s+glaz(?:ed|ing)|melt(?:ed|ing)?\s+region)\b")),
    ("cast_region", re.compile(r"(?i)\b(?:cast(?:ing)?\s+region|as[\s-]*cast)\b")),
    ("solution_treated", re.compile(r"(?i)\bsolution(?:ized|ising|izing|\s+treat(?:ed|ment)?)\b")),
    (
        "heat_treated",
        re.compile(
            r"(?i)\b(?:ht\s*[-_]?\s*\d+|ht|heat[\s-]*treat(?:ed|ment)?|"
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


def _normalize_state_markup(value: Any) -> str:
    """Normalize common OCR/LaTeX temperature markup without changing meaning."""

    text = unicodedata.normalize("NFKC", str(value or ""))
    text = re.sub(r"\\(?=\s)", "", text)
    return re.sub(
        r"\^?\s*\{?\s*\\circ\s*\}?\s*(?:\{\s*C\s*\}|C)",
        "°C",
        text,
        flags=re.IGNORECASE,
    )


def _state_descriptor(value: Any) -> tuple[str, tuple[str, ...]] | None:
    """Return a generic state category plus explicit numeric qualifiers."""

    text = _normalize_state_markup(value).strip()
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


_COMPOSITE_STATE_CODE = re.compile(r"(?i)\b(?:hip|ht)\s*[-_]?\s*\d+\b")
_COMPOSITE_STATE_PREFIXES = (
    ("as_sintered", re.compile(r"(?i)\bas[\s-]*sinter(?:ed|ing)?\b")),
    ("as_built", re.compile(r"(?i)\bas[\s-]*(?:built|printed|fabricated|deposited|produced)\b")),
    ("as_cast", re.compile(r"(?i)\bas[\s-]*cast\b")),
)


def _state_composite_discriminator(value: Any) -> tuple[str, ...]:
    """Return only explicit multi-component preparation markers.

    ``_state_descriptor`` intentionally collapses presentation variants and
    lets an unqualified state mention cover qualified siblings.  That is safe
    for ordinary prose, but it loses a real coordinate when a table writes
    ``HIP1`` beside ``HIP2`` or ``HIP2 + HT2`` beside
    ``as-sintered + HIP2 + HT2``: all rows can share one coarse HIP descriptor.
    This discriminator is used only by inventory state expansion, and
    therefore does not change the broader state-evidence matching rules.
    Durations/temperatures are deliberately excluded so harmless OCR/prose
    variants such as an omitted soak time still coalesce.
    """

    text = unicodedata.normalize("NFKC", str(value or ""))
    codes = tuple(
        sorted(
            {
                re.sub(r"\s+", "", match.group(0)).casefold().replace("_", "-")
                for match in _COMPOSITE_STATE_CODE.finditer(text)
            }
        )
    )
    prefixes = tuple(
        name for name, pattern in _COMPOSITE_STATE_PREFIXES if pattern.search(text)
    )
    if not codes:
        return ()
    # A range such as ``HT1-4`` is a family/context statement, not one
    # independently identified state.  Likewise, ``HIP and HT2`` names a
    # generic HIP context plus one heat-treatment code; the code must not turn
    # that broad phrase into a synthetic state item.  A compact code whose
    # category agrees with the surrounding state (``HIP1``, ``after HIP1``,
    # ``HT2 after sintering``) is identity-bearing even when it is the only
    # code in the label.
    if re.search(
        r"(?i)\b(?:hip|ht)\s*[-_]?\s*\d+\s*[-–]\s*\d+\b", text
    ):
        return ()
    if len(codes) == 1 and not prefixes:
        code_prefix = re.match(r"[a-z]+", codes[0])
        descriptor = _state_descriptor(text)
        category_prefix = {
            "hip": "hip",
            "heat_treated": "ht",
        }.get(descriptor[0] if descriptor else "")
        if not code_prefix or code_prefix.group(0) != category_prefix:
            return ()
    return tuple(dict.fromkeys([*prefixes, *codes]))


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
            composite = _state_composite_discriminator(anchor.state_raw)
            if qualifiers:
                # An exact coordinate is authoritative.  Only fall back to a
                # qualifier superset when the source omitted a detail and the
                # exact sibling is genuinely absent.  Without this ordering,
                # a broad composite state can steal a narrower numbered state
                # (for example HIP1/HIP2 rows in one shared inventory family).
                exact = (
                    qualifiers
                    if composite and qualifiers in qualified
                    else None
                )
                supersets = [
                    candidate
                    for candidate in qualified
                    if set(qualifiers) <= set(candidate)
                ]
                effective = (
                    exact
                    if exact is not None
                    else max(supersets, key=lambda value: (len(value), value))
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
            if composite:
                # Keep the existing descriptor/qualifier coalescing behavior,
                # but split genuinely different composite preparation bundles
                # that otherwise share one coarse category (e.g. HIP2 + HT2
                # versus as-sintered + HIP2 + HT2).
                buckets = [bucket + "|components:" + "+".join(composite) for bucket in buckets]
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


def _composition_atom_key(component: dict[str, Any]) -> tuple[Any, ...] | None:
    """Return one presentation-neutral key for an already sanitized component."""

    name = normalize_source_alias(
        component.get("canonical_name") or component.get("name_raw")
    )
    if not name:
        return None
    kind = str(component.get("value_kind") or "").strip().casefold()
    raw_value = component.get("value_raw")
    if kind == "balance" or str(raw_value or "").strip().casefold() in {
        "bal",
        "bal.",
        "balance",
        "remainder",
    }:
        value_key: tuple[Any, ...] = ("balance",)
    else:
        numbers = _numeric_cell_signature(raw_value)
        value_key = (
            ("numeric", *numbers)
            if numbers
            else ("text", normalize_source_alias(raw_value))
        )
    unit = re.sub(
        r"[^a-z0-9%]+",
        "",
        unicodedata.normalize(
            "NFKC",
            str(component.get("canonical_unit") or component.get("unit_raw") or ""),
        ).casefold(),
    )
    return name, kind, value_key, unit


def _composition_observation_atom_keys(
    observation: dict[str, Any],
) -> frozenset[tuple[Any, ...]]:
    return frozenset(
        key
        for component in observation.get("components") or []
        if isinstance(component, dict)
        if (key := _composition_atom_key(component)) is not None
    )


def _merge_cross_source_exact_composition_observations(
    records: Sequence[dict[str, Any]],
    *,
    sample_id: str,
) -> tuple[list[dict[str, Any]], list[MaterializeIssue]]:
    """Merge one text projection into one uniquely matching table observation.

    Chunked extraction can emit the same nominal composition twice: once from
    the literal table and once from an alloy designation or a prose statement
    such as ``0.5 wt.% Ti was added``.  The two observations have different
    presentation metadata, so ordinary dictionary deduplication cannot merge
    them.  This pass is deliberately asymmetric and conservative: the text
    atom set must be a non-empty subset of exactly one same-context table atom
    set.  Measured/microanalysis observations and ambiguous multiple-table
    matches remain untouched.
    """

    rows = [deepcopy(record) for record in records]
    issues: list[MaterializeIssue] = []
    removed_indices: set[int] = set()

    def compatible_state(left: Any, right: Any) -> bool:
        left_key = normalize_source_alias(left)
        right_key = normalize_source_alias(right)
        unspecified = {"", "notreported", "unknown", "unspecified"}
        return left_key == right_key or left_key in unspecified or right_key in unspecified

    def compatible_context(left: dict[str, Any], right: dict[str, Any]) -> bool:
        return bool(
            left.get("data_source") == "table"
            and right.get("data_source") == "text"
            and not left.get("measurement")
            and not right.get("measurement")
            and not left.get("note")
            and not right.get("note")
            and not left.get("_microanalysis_owner_recovered")
            and not right.get("_microanalysis_owner_recovered")
            and left.get("source_type") == right.get("source_type")
            and left.get("basis") == right.get("basis")
            and left.get("basis") not in {None, "", "unknown"}
            and left.get("component_type") == right.get("component_type")
            # Records reaching this helper have already been grouped under the
            # same reconciled item owner.  The nested sample label is often a
            # clipped alias, while ``not_reported`` state on one chunk may be
            # completed by the table chunk.  A conflicting pair of explicit
            # states still remains separate.
            and compatible_state(
                left.get("material_state"), right.get("material_state")
            )
        )

    for text_index, text_observation in enumerate(rows):
        if text_index in removed_indices or text_observation.get("data_source") != "text":
            continue
        text_atoms = _composition_observation_atom_keys(text_observation)
        if not text_atoms:
            continue
        matches = [
            table_index
            for table_index, table_observation in enumerate(rows)
            if table_index not in removed_indices
            and table_index != text_index
            and compatible_context(table_observation, text_observation)
            and text_atoms
            <= _composition_observation_atom_keys(table_observation)
        ]
        if len(matches) != 1:
            continue
        table_index = matches[0]
        before = deepcopy(rows[table_index])
        removed = deepcopy(text_observation)
        _union_evidence(rows[table_index], text_observation)
        removed_indices.add(text_index)
        issues.append(
            MaterializeIssue(
                code="composition_cross_source_exact_duplicate_merged",
                sample_id_raw=sample_id,
                path=f"items.{sample_id}.Composition.Composition_Observations",
                message=(
                    "A text/designation composition projection exactly repeated "
                    "atoms already present in one source table and was merged "
                    "without losing either evidence span."
                ),
                evidence=_evidence(rows[table_index].get("source_evidence")),
                expected={
                    "same_owner": True,
                    "same_basis_and_source_type": True,
                    "unique_table_superset": True,
                    "duplicate_public_atoms": False,
                    "audit_preserved": True,
                },
                actual={
                    "survivor_before": before,
                    "removed": removed,
                    "survivor_after": deepcopy(rows[table_index]),
                    "matched_atoms": [
                        list(atom)
                        for atom in sorted(text_atoms, key=lambda atom: repr(atom))
                    ],
                },
                suggested_action=(
                    "Review only if the prose and table intentionally describe "
                    "different composition measurements with identical values."
                ),
            )
        )

    return (
        [row for index, row in enumerate(rows) if index not in removed_indices],
        issues,
    )


def _characterization_method_text(value: Any) -> str:
    text = unicodedata.normalize("NFKC", str(value or "")).casefold()
    return re.sub(r"[^a-z0-9]+", " ", text).strip()


def _characterization_method_family(row: dict[str, Any]) -> str | None:
    """Return one explicit scientific technique family, never a generic method."""

    for value in (row.get("method_raw"), row.get("method_class")):
        text = _characterization_method_text(value)
        for family, detector, _ in _CHARACTERIZATION_METHOD_ALIASES:
            if detector.search(text):
                return family
    return None


def _characterization_class_family(row: dict[str, Any]) -> str | None:
    return _characterization_method_family({"method_raw": row.get("method_class")})


def _bare_characterization_alias(row: dict[str, Any], family: str) -> bool:
    text = _characterization_method_text(row.get("method_raw"))
    return any(
        candidate_family == family and bare.fullmatch(text)
        for candidate_family, _, bare in _CHARACTERIZATION_METHOD_ALIASES
    )


def _characterization_context_signature(row: dict[str, Any]) -> str:
    context = {
        key: child
        for key, child in row.items()
        if key
        not in {
            "characterization_id",
            "source_evidence",
            "confidence",
            "method_raw",
            "method_class",
        }
        and child not in (None, "", [], {})
    }
    return _signature(context)


def _characterization_survivor_rank(
    row: dict[str, Any], family: str, index: int
) -> tuple[int, int, int]:
    class_family = _characterization_method_family(
        {"method_raw": row.get("method_class")}
    )
    return (
        len(_characterization_method_text(row.get("method_raw"))),
        int(class_family == family),
        -index,
    )


def _coalesce_characterization_aliases(
    rows: Sequence[dict[str, Any]], sample_id: str
) -> tuple[list[dict[str, Any]], list[MaterializeIssue]]:
    """Merge only presentation aliases for one unambiguous technique record."""

    records = [deepcopy(row) for row in rows]
    groups: dict[tuple[str, str], list[int]] = {}
    for index, row in enumerate(records):
        family = _characterization_method_family(row)
        if family is None or _characterization_class_family(row) != family:
            # A generic or conflicting provider class can carry a distinct
            # downstream interpretation even when method_raw contains an
            # explicit acronym. Preserve it unless both fields agree.
            continue
        key = (family, _characterization_context_signature(row))
        groups.setdefault(key, []).append(index)

    replacements: dict[int, dict[str, Any]] = {}
    consumed_indices: set[int] = set()
    issues: list[MaterializeIssue] = []
    for (family, _), indices in groups.items():
        if len(indices) < 2:
            continue
        bare_indices = [
            index
            for index in indices
            if _bare_characterization_alias(records[index], family)
        ]
        detailed_indices = [index for index in indices if index not in bare_indices]
        if detailed_indices or len(bare_indices) < 2:
            # Acquisition modes and instrument-bearing records remain separate
            # from their umbrella method even if exactly one detailed row exists.
            continue
        survivor_index = max(
            bare_indices,
            key=lambda index: _characterization_survivor_rank(
                records[index], family, index
            ),
        )
        removed = [index for index in bare_indices if index != survivor_index]
        if not removed:
            continue

        survivor_before = deepcopy(records[survivor_index])
        survivor_after = deepcopy(survivor_before)
        for index in removed:
            _merge_record(survivor_after, records[index])
        output_index = min([survivor_index, *removed])
        replacements[output_index] = survivor_after
        consumed_indices.update([survivor_index, *removed])

        for index in removed:
            issues.append(
                MaterializeIssue(
                    code="characterization_method_alias_merged",
                    sample_id_raw=sample_id,
                    path=f"items.{sample_id}.Structure.Characterization",
                    message=(
                        "A presentation-only characterization method alias was "
                        "merged into one technique record."
                    ),
                    evidence=_evidence(records[index].get("source_evidence")),
                    expected={
                        "technique_family": family,
                        "same_owner": True,
                        "compatible_secondary_metadata": True,
                    },
                    actual={
                        "removed_alias": deepcopy(records[index]),
                        "survivor_before_merge": deepcopy(survivor_before),
                        "survivor_after_merge": deepcopy(survivor_after),
                    },
                    suggested_action=(
                        "Review only if the aliases denote different instruments "
                        "or acquisition modes for the same material state."
                    ),
                )
            )

    output: list[dict[str, Any]] = []
    for index, row in enumerate(records):
        if index in replacements:
            output.append(replacements[index])
        elif index not in consumed_indices:
            output.append(row)
    return output, issues


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


def _property_unique_table_projection(
    prop: Mapping[str, Any],
    *,
    owner_labels: Sequence[str],
    source_text: str,
) -> dict[str, Any] | None:
    """Return one owner/value-proven table projection for protocol binding."""

    value = prop.get("value_raw")
    evidence_rows = _evidence(prop.get("source_evidence"))
    candidates: list[str] = []
    for evidence in evidence_rows:
        candidates.append(evidence)
        candidates.extend(
            line.strip()
            for line in evidence.splitlines()
            if line.strip().startswith("|") and line.strip().endswith("|")
        )
    decisions: dict[str, dict[str, Any]] = {}
    for evidence in dict.fromkeys(candidates):
        decision = unique_ordered_table_row_projection(evidence, source_text)
        if decision.status != "matched":
            continue
        for owner in dict.fromkeys(str(row).strip() for row in owner_labels):
            if not owner:
                continue
            payload = {
                "sample_id_raw": owner,
                "data": {"value_raw": value},
            }
            if not table_projection_supports_record(payload, decision):
                continue
            serialized = decision.to_dict()
            key = json.dumps(serialized, ensure_ascii=False, sort_keys=True)
            decisions.setdefault(key, serialized)
    if len(decisions) != 1:
        return None
    return next(iter(decisions.values()))


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
    # A structure feature is not grounded merely because its surrounding
    # observation is grounded.  Providers sometimes copy a numeric value from
    # a nearby table row and attach the current sentence as evidence.  Keep the
    # observation's other supported features, but reject this value unless all
    # of its literal numeric tokens occur in its own evidence envelope.
    if not _structure_feature_numeric_evidence_supported(raw_value, evidence, row):
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


def _structure_feature_numeric_evidence_supported(
    value: Any,
    evidence: Sequence[str],
    row: dict[str, Any] | None = None,
) -> bool:
    """Check that a numeric structure value occurs in its source evidence."""

    text = unicodedata.normalize("NFKC", str(value or ""))
    row = row or {}
    kind = str(row.get("value_kind") or "").strip().casefold()
    has_measurement_unit = bool(str(row.get("unit_raw") or "").strip())
    has_numeric_measurement_cue = bool(
        re.search(
            r"\d\s*(?:%|pct|nm|μm|um|mm|cm|m\b|gpa|mpa|pa\b|k\b|°c|"
            r"x\s*10|×|e[+-]?\d)",
            text,
            flags=re.IGNORECASE,
        )
    )
    if kind not in {"scalar", "range", "inequality"} and not (
        has_measurement_unit or has_numeric_measurement_cue
    ):
        # Digits inside an alloy designation (for example Al0.6TiFe0.4) are
        # identity text, not a numeric measurement that needs coordinate
        # validation.
        return True
    text = text.replace("−", "-").replace("–", "-").replace("—", "-")
    numbers = re.findall(
        r"(?<![A-Za-z])[-+]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?",
        text,
    )
    if not numbers:
        return True
    evidence_text = " ".join(str(row or "") for row in evidence)
    evidence_text = unicodedata.normalize("NFKC", evidence_text)
    evidence_text = evidence_text.replace("−", "-").replace("–", "-").replace("—", "-")
    evidence_numbers = {
        token.casefold()
        for token in re.findall(
            r"(?<![A-Za-z])[-+]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?",
            evidence_text,
        )
    }
    return all(number.casefold() in evidence_numbers for number in numbers)


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
    canonical_name = row.get("canonical_name")
    if normalize_source_alias(canonical_name) in {
        "unknown",
        "unknownentity",
        "notreported",
        "unspecified",
    }:
        canonical_name = None
    return {
        "entity_id": str(
            _first_present(row, "entity_id", "entity_id_candidate")
            or f"entity_{entity_index:03d}"
        ),
        "entity_type": entity_type,
        "role": str(_first_present(row, "role", "role_raw") or "reported"),
        "name_raw": str(name).strip(),
        "canonical_name": canonical_name,
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
        # Keep both the parameter-local quote and the stage/table envelope.
        # Chunked table extraction commonly stores only the header cell on the
        # parameter (for example ``Power (W)``) while the stage evidence carries
        # the corresponding value row.  Replacing the stage evidence with the
        # short header makes the final audit look ungrounded and loses the
        # owner/column coordinate needed by downstream review.  Union the two
        # envelopes without inventing any text.
        evidence_rows = [
            *_evidence(raw.get("source_evidence")),
            *[row for row in stage_evidence if str(row).strip()],
        ]
        evidence = " | ".join(dict.fromkeys(evidence_rows))
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
    if re.search(r"(?i)\[reference\]\s*$", sample):
        # Deterministic fact-level recovery uses this suffix to distinguish one
        # independently cited owner from a same-material Target.  Reapplying the
        # broad citation rewrite would immediately collapse that proven split.
        return anchor, ""
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
                category_pattern = next(
                    (
                        pattern
                        for candidate, pattern in _STATE_CATEGORY_PATTERNS
                        if candidate == category
                    ),
                    None,
                )
                qualifier_keys = [normalize_source_alias(value) for value in qualifiers]
                if (
                    qualifiers
                    and (
                        (category_key and category_key in normalized)
                        or (category_pattern is not None and category_pattern.search(row))
                    )
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
    if fact.data.get("_microanalysis_owner_recovered") is True:
        # The deterministic resolver has already selected one existing material
        # owner.  A more complete source condition belongs on that observation;
        # it must not synthesize a second ``base [state]`` material item.
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
    # A measured composition/structure row may use an analytical object as
    # its own sample identity (for example ``binder jetting fracture surface``)
    # while another chunk also emits the broader ``binder jetting`` sample.
    # The generic presentation-parent rule intentionally folds labels such as
    # ``... fracture surface`` into their base for ordinary prose, but doing
    # that here would attach a measured sub-object to the wrong material and
    # create cross-chunk projections.  Protect only an exact, state-backed
    # observation owner; a bare prose mention (or a property/test condition)
    # still follows the historical merge behavior.
    protected_observation_keys = {
        _identity_key(anchor.sample_id_raw)
        for anchor in anchors
        if _identity_key(anchor.sample_id_raw)
        and str(anchor.state_raw or "").strip()
        and any(
            _identity_key(fact.sample_id_raw)
            == _identity_key(anchor.sample_id_raw)
            and fact.fact_type in {"composition_observation", "structure_observation"}
            and normalize_source_alias(fact.data.get("material_state"))
            == normalize_source_alias(anchor.state_raw)
            for fact in facts
        )
    }
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
            and sample_key not in protected_observation_keys
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
            and sample_key not in protected_observation_keys
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
    canonical_roles: dict[str, set[str]] = {}
    for sample_key, roles in candidate_roles.items():
        canonical_roles.setdefault(redirected_key(sample_key), set()).update(roles)
    for descriptor, owners in descriptor_owners.items():
        canonical_owners = {redirected_key(owner) for owner in owners}
        if (
            descriptor not in candidate_keys
            or descriptor in expanded_base_keys
            or len(canonical_owners) != 1
        ):
            continue
        owner = next(iter(canonical_owners))
        descriptor_owner = redirected_key(descriptor)
        if descriptor in independent_fact_keys:
            owner_rows = [
                anchor
                for anchor in anchors
                if redirected_key(_identity_key(anchor.sample_id_raw)) == owner
                and descriptor in _identity_alias_keys(anchor.material_name_raw)
            ]
            explicit_short_code = any(
                bool(
                    re.fullmatch(
                        r"[A-Za-z][A-Za-z0-9_.+-]{1,7}",
                        str(anchor.sample_id_raw or "").strip(),
                    )
                )
                for anchor in owner_rows
            )
            explicit_initialism = any(
                _source_initialism(anchor.material_name_raw)
                == _identity_key(anchor.sample_id_raw)
                for anchor in owner_rows
            )
            aligned_identity = any(
                _anchor_identity_aligns_with_material(anchor)
                for anchor in owner_rows
            )
            if not (
                explicit_short_code
                or explicit_initialism
                or aligned_identity
            ):
                # A table metric can carry the material in parentheses and use
                # that material again as ``material_name_raw``.  When the
                # descriptor itself already owns independent facts, that
                # parenthetical mention is not an alias declaration.  Preserve
                # both owners unless the candidate is an explicit source code
                # or otherwise names the descriptor itself.
                continue
        descriptor_roles = canonical_roles.get(descriptor_owner, set())
        owner_roles = canonical_roles.get(owner, set())
        if (
            descriptor_roles
            and owner_roles
            and descriptor_roles.isdisjoint(owner_roles)
        ):
            # A recovered literature owner can legitimately use the original
            # row label as its material descriptor.  That one-to-one textual
            # relationship must not collapse an explicit Target/Reference
            # split back into one item.
            continue
        if descriptor_owner != owner:
            redirects[descriptor] = owner

    # State expansion runs before cross-chunk aliases are known. Reconcile the
    # generated ``base [state]`` identities again after their bases have been
    # normalized, otherwise T0 and an OCR/table form such as T0 (M) can each
    # produce a duplicate heat-treated state item.
    generated_states: dict[tuple[str, Any], set[str]] = {}
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
        state_key: Any = (
            descriptor,
            _state_composite_discriminator(state_text),
        )
        generated_states.setdefault(
            (redirected_key(base_key), state_key), set()
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
    # Test temperature, rate, orientation and protocol are measurement
    # conditions, not preparation states.  The literal evidence remains useful
    # for explicit material/state labels, but the structured condition field
    # must never select an owner state.
    local_context = _fact_local_state_context(fact)
    if not isinstance(fact, PropertyFact):
        return [*local_context, *fact.source_evidence]

    # A property bundle can contain a value row, a table caption naming the
    # owner, and a separate footnote listing several specimen states.  Those
    # rows are useful provenance, but they do not prove that one listed state
    # owns this particular value.  Only a physical evidence line that names
    # both the property owner and the state may narrow a PropertyFact.  An
    # explicit local specimen/state field remains authoritative above.
    owner_labels = [
        label
        for label in [*_fact_identity_labels(fact), fact.sample_id_raw]
        if str(label or "").strip() and not _is_unresolved_alias(label)
    ]
    owner_bound_evidence = [
        line.strip()
        for evidence in fact.source_evidence
        for line in str(evidence or "").splitlines()
        if line.strip()
        and any(_source_label_occurs_in_row(label, line) for label in owner_labels)
    ]
    return [*local_context, *owner_bound_evidence]


def _fact_declared_targets(
    index: _IdentityIndex, fact: AxisFact
) -> tuple[str, ...]:
    """Resolve the first explicit fact owner before state-evidence narrowing."""

    for label in [*_fact_identity_labels(fact), fact.sample_id_raw]:
        targets = index.resolve_label(label) or index.resolve_state_label(label)
        if targets:
            return targets
    return ()


def _fact_evidence_owner_targets(
    index: _IdentityIndex, fact: AxisFact
) -> tuple[str, ...]:
    """Return a uniquely source-named owner, without treating context as proof.

    This is deliberately narrower than ordinary routing.  It only reports a
    result when the fact evidence contains exactly one known source identity;
    a comparison/table row mentioning two owners therefore remains ambiguous.
    The caller uses this as a reconciliation signal, never as a broadcast
    fallback.
    """

    # Do not use ``resolve_evidence`` here: its longest-alias rule is correct
    # for normal routing but intentionally hides a shorter owner inside a
    # qualified label (``N1`` inside ``N1-LAG``).  For reconciliation we need
    # to see every literal source owner so a comparison such as ``GA and WA``
    # remains ambiguous instead of looking like one owner.
    targets = _fact_explicit_evidence_targets(index, fact)
    return targets if len(targets) == 1 else ()


def _fact_explicit_evidence_targets(
    index: _IdentityIndex, fact: AxisFact
) -> tuple[str, ...]:
    """Return every source-backed sample label explicitly named by evidence."""

    targets: set[str] = set()
    for canonical in index.anchors:
        presentations = {
            index.display_label(canonical),
            *(
                str(anchor.sample_id_raw or "").strip()
                for anchor in index.anchors.get(canonical, [])
            ),
        }
        if any(
            _strict_source_owner_occurs(label, row)
            for label in presentations
            if label
            for row in fact.source_evidence
        ):
            targets.add(canonical)
    return tuple(sorted(targets))


def _strict_source_owner_occurs(label: Any, row: Any) -> bool:
    """Match a literal owner without treating a qualified code as its base."""

    presentation = unicodedata.normalize("NFKC", str(label or "")).strip()
    text = unicodedata.normalize("NFKC", str(row or ""))
    if not presentation or _is_element_symbol(presentation):
        return False
    # Hyphen/underscore are part of compact source IDs for this pass.  This is
    # deliberately stricter than the general token matcher, which treats the
    # hyphen as a boundary for ordinary prose.
    if re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{1,15}", presentation):
        pattern = re.compile(
            rf"(?i)(?<![A-Za-z0-9_-]){re.escape(presentation)}(?![A-Za-z0-9_-])"
        )
        if pattern.search(text):
            return True
        tex_text = re.sub(r"[_^]\{([^{}]*)\}", r"\1", text)
        tex_text = re.sub(r"[{}$\\]", "", tex_text)
        if pattern.search(tex_text):
            return True
        # TeX/OCR can split a compact code (``N_{1}-LAG``).  Normalize the
        # complete code and still require both sides of the normalized match
        # to be non-alphanumeric, so ``N1`` cannot match the prefix of
        # ``N1-LAG``.
        alias = normalize_source_alias(presentation)
        normalized_row = normalize_source_alias(text)
        if alias and normalized_row:
            return bool(
                re.search(
                    rf"(?<![a-z0-9]){re.escape(alias)}(?![a-z0-9])",
                    normalized_row,
                )
            )
        return False
    return _source_label_occurs_in_row(presentation, text)


def _fact_evidence_owner_is_explicit(
    index: _IdentityIndex, fact: AxisFact, target: str
) -> bool:
    """Require the selected owner to occur as a literal source identity."""

    presentations = {
        index.display_label(target),
        *(
            str(anchor.sample_id_raw or "").strip()
            for anchor in index.anchors.get(target, [])
        ),
    }
    return any(
        _strict_source_owner_occurs(label, row)
        for label in presentations
        if label
        for row in fact.source_evidence
    )


def _fact_owner_roles_compatible(
    index: _IdentityIndex, declared: str, evidence: str
) -> bool:
    """Reject evidence-owner moves across Target/Reference role boundaries."""

    declared_roles = {
        str(anchor.role or "").strip().casefold()
        for anchor in index.anchors.get(declared, [])
        if str(anchor.role or "").strip()
    }
    evidence_roles = {
        str(anchor.role or "").strip().casefold()
        for anchor in index.anchors.get(evidence, [])
        if str(anchor.role or "").strip()
    }
    return not declared_roles or not evidence_roles or bool(
        declared_roles & evidence_roles
    )


_DIRECT_OWNER_COMPARISON = re.compile(
    r"(?ix)\b(?:respectively|versus|vs\.?|compared\s+(?:with|to)|"
    r"relative\s+to|than)\b"
)
_DIRECT_OWNER_ASSERTION_VERB = re.compile(
    r"(?ix)\b(?:contain(?:s|ed)?|consist(?:s|ed)?|exhibit(?:s|ed)?|"
    r"show(?:s|ed)?|observ(?:e|ed|ation)|measur(?:e|ed|ement)|"
    r"characteri[sz](?:e|ed|ation)|determin(?:e|ed)|"
    r"perform(?:ed|ed\s+using)?|conduct(?:ed)?|test(?:ed|ing)?|"
    r"fabricat(?:e|ed|ion)|manufactur(?:e|ed|ing)|process(?:ed|ing)?|"
    r"print(?:ed|ing)?|deposit(?:ed|ion)?|build(?:s|ing)?|use(?:d|s)?|"
    r"appl(?:y|ied|ication)|heat[-\s]*treat(?:ed|ment)?|sinter(?:ed|ing)?|"
    r"age(?:d|ing)?|anneal(?:ed|ing)?)\b"
)
_DIRECT_MULTI_OWNER_CONTEXT = re.compile(
    r"(?ix)\b(?:both|either|each)\b.{0,120}\b(?:and|or)\b"
    r"|\b[A-Za-z0-9][A-Za-z0-9_+\-/(){}.,]*\s+and\s+"
    r"[A-Za-z0-9][A-Za-z0-9_+\-/(){}.,]*\s+(?:samples?|specimens?|materials?)\b"
)
_DIRECT_POWDER_SAMPLE_CONTEXT = re.compile(
    r"(?ix)\b(?:powder|feedstock)\b.{0,100}\b(?:sample|specimen)\b"
    r"|\b(?:sample|specimen)\b.{0,100}\b(?:powder|feedstock)\b"
)


def _fact_evidence_units(fact: AxisFact) -> tuple[str, ...]:
    """Return sentence-sized evidence units for direct owner binding.

    The provider often copies a complete paragraph into ``source_evidence``.
    A paragraph-level owner/value co-occurrence is too weak for reassignment:
    it can join an owner from one sentence to a measurement from the next.
    Keep line boundaries (the usual OCR/table projection unit) and split only
    on sentence terminators. Markdown rows are handled by the caller and are
    intentionally not interpreted as prose assertions here.
    """

    units: list[str] = []
    for evidence in fact.source_evidence:
        for line in str(evidence or "").splitlines():
            line = line.strip()
            if not line or (line.startswith("|") and line.endswith("|")):
                continue
            units.extend(
                sentence.strip()
                for sentence in re.split(r"(?<=[.!?。！？])\s+", line)
                if sentence.strip()
            )
    return tuple(dict.fromkeys(units))


def _evidence_value_literal(value: Any, text: str) -> bool:
    """Match one extracted value in a local source assertion.

    Exact compact matching handles ranges and ``±`` expressions.  Numeric
    fallback is deliberately restricted to a number present in the value so
    OCR whitespace or a unit written outside ``value_raw`` does not prevent a
    valid match.  The caller must also bind a property/component/method label.
    """

    raw = unicodedata.normalize("NFKC", str(value or "")).strip()
    source = unicodedata.normalize("NFKC", str(text or ""))
    if not raw or _is_unresolved_alias(raw):
        return False
    compact_raw = re.sub(r"\s+", "", raw).replace("−", "-").replace("–", "-").replace("—", "-")
    compact_source = re.sub(r"\s+", "", source).replace("−", "-").replace("–", "-").replace("—", "-")
    if compact_raw and compact_raw.casefold() in compact_source.casefold():
        return True
    numbers = re.findall(
        r"(?<![A-Za-z])[-+]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?",
        raw,
    )
    return any(
        re.search(
            rf"(?<![A-Za-z0-9]){re.escape(number)}(?![A-Za-z0-9])",
            source,
            flags=re.IGNORECASE,
        )
        for number in numbers
    )


def _evidence_label_literal(label: Any, text: str) -> bool:
    value = str(label or "").strip()
    return bool(value) and (
        _source_label_occurs_in_row(value, text)
        or normalize_source_alias(value) in normalize_source_alias(text)
    )


def _owner_is_structural_entity(label: Any, text: str) -> bool:
    """Return whether an owner label itself is grammatically a phase/entity."""

    value = str(label or "").strip()
    if not value:
        return False
    escaped = re.escape(value)
    noun = (
        r"(?:phase|precipitate|carbide|boride|oxide|inclusion|particle|"
        r"region|surface|layer)s?"
    )
    if re.search(rf"(?i)\b{noun}\s+(?:of\s+)?{escaped}\b", text):
        return True
    if re.search(rf"(?i)\b{escaped}\s+{noun}\b", text):
        return True
    # Formula owners are sometimes TeX/OCR-normalized.  Keep the fallback
    # narrow: only an owner immediately adjacent to a structural noun counts.
    owner_key = normalize_source_alias(value)
    text_key = normalize_source_alias(text)
    if owner_key:
        return bool(
            re.search(
                rf"(?:phase|precipitate|carbide|boride|oxide|inclusion|particle|region|surface|layer)s?{owner_key}"
                rf"|{owner_key}(?:phase|precipitate|carbide|boride|oxide|inclusion|particle|region|surface|layer)s?",
                text_key,
            )
        )
    return False


def _direct_evidence_binding_kind(fact: AxisFact, target: str, index: _IdentityIndex) -> str | None:
    """Return a narrow axis-specific direct-binding reason, if proven.

    This is intentionally stricter than ``_fact_evidence_owner_targets``.  A
    unique owner anywhere in a copied paragraph is not enough; the same local
    sentence must contain the result, component, structure entity, method, or
    process execution that the fact represents.  The helper is used only for
    non-tensile owner correction, leaving the established tensile gate intact.
    """

    if fact.fact_type == "material_identity" or _fact_markdown_table_rows(fact):
        return None
    owner_labels = {
        index.display_label(target),
        *(
            str(anchor.sample_id_raw or "").strip()
            for anchor in index.anchors.get(target, [])
        ),
    }
    units = _fact_evidence_units(fact)
    if not units:
        return None
    for unit in units:
        if not any(_strict_source_owner_occurs(label, unit) for label in owner_labels if label):
            continue
        # ``respectively`` and comparison syntax are exactly where one source
        # assertion is commonly projected onto several owners.  Do not move a
        # fact across owners from those spans even if the second owner was not
        # resolved by the identity index.
        if _DIRECT_OWNER_COMPARISON.search(unit):
            continue
        if _DIRECT_MULTI_OWNER_CONTEXT.search(unit):
            continue

        if isinstance(fact, CompositionFact) and fact.fact_type == "composition_observation":
            # A powder/feedstock sentence commonly reports both the input and
            # the processed sample.  Even when only one of those labels is
            # indexed, moving the row to that label would silently swap the
            # material lineage.
            if _DIRECT_POWDER_SAMPLE_CONTEXT.search(unit):
                continue
            components = fact.data.get("components") or []
            for component in components:
                if not isinstance(component, dict):
                    continue
                name = component.get("name_raw") or component.get("canonical_name")
                value = component.get("value_raw")
                unit_raw = component.get("unit_raw") or fact.data.get("basis")
                if (
                    _evidence_label_literal(name, unit)
                    and _evidence_value_literal(value, unit)
                    and (
                        _evidence_label_literal(unit_raw, unit)
                        or re.search(r"(?i)\b(?:composition|content|at\.?%|wt\.?%|ppm|mass|atomic)\b", unit)
                    )
                ):
                    return "composition_component_direct_assertion"
            continue

        if isinstance(fact, StructureFact) and fact.fact_type == "structure_observation":
            # A phase/precipitate name is an observed entity, not automatically
            # the material owner.  Reject owner labels used in that grammatical
            # position; the normal axis-specific structural routing can retain
            # the observation without inventing a phase material.
            owner_is_entity = any(
                _strict_source_owner_occurs(label, unit)
                and _owner_is_structural_entity(label, unit)
                for label in owner_labels
                if label
            )
            if owner_is_entity:
                continue
            literals: list[tuple[Any, Any]] = []
            for key in ("entities", "features"):
                values = fact.data.get(key) or []
                if isinstance(values, dict):
                    values = [values]
                for value in values:
                    if not isinstance(value, dict):
                        continue
                    literals.append(
                        (
                            value.get("name_raw") or value.get("canonical_name"),
                            value.get("value_raw") or value.get("feature_value_raw"),
                        )
                    )
                    for feature in value.get("features") or []:
                        if isinstance(feature, dict):
                            literals.append(
                                (
                                    feature.get("name_raw") or feature.get("canonical_name"),
                                    feature.get("value_raw") or feature.get("feature_value_raw"),
                                )
                            )
            for name, value in literals:
                if not _evidence_label_literal(name, unit):
                    continue
                if value and _evidence_value_literal(value, unit):
                    return "structure_measured_observation"
                if _DIRECT_OWNER_ASSERTION_VERB.search(unit):
                    return "structure_entity_observation"
            continue

        if isinstance(fact, StructureFact) and fact.fact_type == "characterization":
            method = fact.data.get("method_raw") or fact.data.get("method_class")
            if _evidence_label_literal(method, unit) and (
                _DIRECT_OWNER_ASSERTION_VERB.search(unit)
                or re.search(r"(?i)\b(?:analysis|microscopy|diffraction|measurement|image|images)\b", unit)
            ):
                return "characterization_method_direct_assertion"
            continue

        if isinstance(fact, ProcessingFact) and fact.fact_type == "process_stage":
            process_name = fact.data.get("process_name_raw")
            parameters = fact.data.get("parameters_raw") or []
            process_bound = _evidence_label_literal(process_name, unit)
            parameter_bound = False
            for parameter in parameters:
                if not isinstance(parameter, dict):
                    continue
                name = parameter.get("parameter_name_raw")
                value = parameter.get("value_raw")
                parameter_unit = str(parameter.get("unit_raw") or "").strip()
                if (
                    _evidence_label_literal(name, unit)
                    and _evidence_value_literal(value, unit)
                    and (
                        _evidence_label_literal(parameter_unit, unit)
                        or (
                            not parameter_unit
                            and not re.fullmatch(r"\s*[-+]?\d+(?:\.\d*)?\s*", str(value or ""))
                        )
                    )
                ):
                    parameter_bound = True
                    break
            if process_bound and parameter_bound:
                return "processing_stage_direct_assertion"
            continue

    return None


def _fact_owner_reassignment_kind(
    index: _IdentityIndex,
    fact: AxisFact,
    declared: str,
    evidence: str,
) -> str | None:
    """Return the audit rule permitting a unique evidence-owner correction."""

    if not _fact_owner_roles_compatible(index, declared, evidence):
        return None
    if not _fact_evidence_owner_is_explicit(index, fact, evidence):
        return None
    if _numeric_core_tensile_fact(fact):
        return "numeric_core_tensile_explicit_owner"
    return _direct_evidence_binding_kind(fact, evidence, index)


_PROCESS_CONTEXT_OWNER_LABEL = re.compile(
    r"(?ix)^(?:binder\s+jet(?:ting|ted)|laser\s+powder\s+bed(?:\s+fusion)?|"
    r"powder\s+bed\s+fusion|directed\s+energy\s+deposition|"
    r"wire\s*(?:\+|and)?\s*arc|waam|ebam|ebm|lpbf|pbf(?:[-_ ]?(?:lb|eb))?|"
    r"l[- ]?(?:pbf|hw[- ]?ded)|ded|am)$"
)


def _owner_is_process_context_only(index: _IdentityIndex, owner: str) -> bool:
    """Return whether an inventory label is a process context, not a material."""

    for anchor in index.anchors.get(owner, []):
        sample = str(anchor.sample_id_raw or "").strip()
        if _PROCESS_CONTEXT_OWNER_LABEL.fullmatch(sample) or _process_family(sample):
            return True
    return False


def _preferred_evidence_material_owner(
    index: _IdentityIndex,
    fact: AxisFact,
    declared: str,
) -> tuple[str, str] | None:
    """Choose one material over a process-context alias in one direct sentence.

    A common cross-chunk projection has two inventory owners such as
    a process alias and a specific alloy owner.  The source sentence reports a
    characterization/property *of the alloy processed by* the process, but
    the provider emits the same fact once under each label.  Only collapse
    this exact process-vs-material ambiguity when the sentence names both
    labels, contains a material noun, and the axis-specific direct-binding gate
    accepts the material owner.  Processing facts never use this preference.
    """

    if fact.axis != "structure" or _fact_markdown_table_rows(fact):
        return None
    if _DIRECT_MULTI_OWNER_CONTEXT.search("\n".join(fact.source_evidence)):
        return None
    candidates = _fact_explicit_evidence_targets(index, fact)
    if len(candidates) < 2:
        return None
    process_contexts = {
        owner for owner in candidates if _owner_is_process_context_only(index, owner)
    }
    material_candidates = tuple(owner for owner in candidates if owner not in process_contexts)
    if len(process_contexts) != 1 or len(material_candidates) != 1:
        return None
    material_owner = material_candidates[0]

    def owner_present(owner: str, unit: str) -> bool:
        presentations = {
            index.display_label(owner),
            *(
                str(anchor.sample_id_raw or "").strip()
                for anchor in index.anchors.get(owner, [])
            ),
        }
        return any(
            _strict_source_owner_occurs(label, unit)
            for label in presentations
            if label
        )

    for unit in _fact_evidence_units(fact):
        if not all(owner_present(owner, unit) for owner in candidates):
            continue
        if not re.search(
            r"(?i)\b(?:alloy|material|composite|superalloy|sample|specimen)\b",
            unit,
        ):
            continue
        if _DIRECT_OWNER_COMPARISON.search(unit):
            continue
        if _numeric_core_tensile_fact(fact):
            kind = "numeric_core_tensile_process_material_preference"
        else:
            kind = _direct_evidence_binding_kind(fact, material_owner, index)
        if kind:
            return material_owner, kind
    return None


def _group_route(index: _IdentityIndex, fact: AxisFact) -> tuple[str, ...]:
    state_context = _fact_state_context(fact)

    def narrow_state_family(targets: tuple[str, ...]) -> tuple[str, ...]:
        if (
            len(targets) == 1
            and targets[0] in index.state_family_base
            and index.resolve_exact(fact.sample_id_raw) == targets
        ):
            # An exact qualified owner label is already stronger than generic
            # state context. Do not collapse it back to the family merely
            # because the copied property quote omits the preparation phrase.
            return targets
        local_state_context = _fact_local_state_context(fact)
        # A structured local state is stronger than the coarse descriptor
        # index.  Composite labels such as ``HIP2 + HT2`` and
        # ``as-sintered + HIP2 + HT2`` intentionally share the generic HIP
        # descriptor, but their normalized source aliases are one-to-one.  Use
        # that exact alias first so a value is not routed to both siblings.
        exact_local_targets: set[str] = set()
        for state in local_state_context:
            alias = normalize_source_alias(state)
            exact_local_targets.update(index.state_alias_targets.get(alias, set()))
        local_state_targets = (
            tuple(sorted(exact_local_targets))
            if len(exact_local_targets) == 1
            else index.resolve_state_evidence(local_state_context)
        )
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

    # Providers occasionally emit a short/base owner in the structured field
    # while copying a source sentence whose only literal owner is a qualified
    # sample (for example ``sample_id_raw=N1`` for a sentence naming
    # ``N1-LAG``).  A single evidence owner is stronger than that conflicting
    # short label, but only when the evidence does not mention any competing
    # owner.  This guard is intentionally before the normal declared-owner
    # route and never activates for a multi-owner comparison/table span.
    declared_targets = _fact_declared_targets(index, fact)
    if (
        source_coordinate_precision_v202_enabled()
        and isinstance(fact, PropertyFact)
        and str(fact.data.get("data_source") or "").casefold()
        in {"chart_csv", "image_digitized"}
        and str(fact.data.get("property_id_candidate") or "").startswith(
            "sidecar-cell:"
        )
    ):
        # A sidecar fact already carries an immutable, audited cell coordinate
        # and an explicitly constructed state-qualified owner. Tokens such as
        # ``HT2`` inside its literal row are preparation labels, not competing
        # standalone material owners. Preserve the exact coordinate owner
        # before generic evidence-proximity reconciliation can reinterpret it.
        exact_targets = index.resolve_exact(fact.sample_id_raw)
        if len(exact_targets) == 1:
            return exact_targets
    evidence_targets = _fact_evidence_owner_targets(index, fact)
    if len(declared_targets) == 1:
        preferred = _preferred_evidence_material_owner(
            index, fact, declared_targets[0]
        )
        if preferred is not None:
            preferred_owner, _ = preferred
            if preferred_owner != declared_targets[0] and _fact_owner_roles_compatible(
                index, declared_targets[0], preferred_owner
            ):
                return (preferred_owner,)
    declared_base = (
        index.state_family_base.get(declared_targets[0], declared_targets[0])
        if len(declared_targets) == 1
        else None
    )
    evidence_base = (
        index.state_family_base.get(evidence_targets[0], evidence_targets[0])
        if len(evidence_targets) == 1
        else None
    )
    if (
        len(declared_targets) == 1
        and len(evidence_targets) == 1
        and evidence_targets[0] != declared_targets[0]
        and declared_base != evidence_base
        and not re.search(r"(?i)\[reference\]\s*$", str(fact.sample_id_raw or ""))
        # Table/column ownership has dedicated coordinate-aware recovery and
        # precision-merging passes.  A merged fact may intentionally carry a
        # richer table row whose owner differs from its final presentation
        # (for example ``Binder Jetting`` + ``Binder Jetting / X``); do not
        # reinterpret that table coordinate as a cross-owner correction here.
        and not _fact_markdown_table_rows(fact)
        and _fact_owner_reassignment_kind(
            index, fact, declared_targets[0], evidence_targets[0]
        )
    ):
        narrowed = narrow_state_family(evidence_targets)
        if len(narrowed) == 1:
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


_REPORTED_RESULT_BLOCKER = re.compile(
    r"(?ix)\b(?:"
    r"(?:minimum|maximum|required|requirement|specified|specification|limit|threshold)"
    r"|(?:astm|iso|din|en|ams)\s*[-A-Z0-9]"
    r"|fatigue|creep|compression|hardness"
    r")\b"
)


def _complete_markdown_table_rows(fact: AxisFact) -> list[str]:
    """Return complete source rows that literally contain the fact owner label."""

    owner = str(fact.sample_id_raw or "").strip()
    owner_key = normalize_source_alias(owner)
    if not owner_key:
        return []
    rows: list[str] = []
    for evidence in fact.source_evidence:
        for raw_row in str(evidence or "").splitlines():
            row = raw_row.strip()
            if not (row.startswith("|") and row.endswith("|") and row.count("|") >= 3):
                continue
            if owner_key not in normalize_source_alias(row):
                continue
            rows.append(row)
    return list(dict.fromkeys(rows))


def _markdown_table_cells(row: str) -> list[str]:
    """Split one complete projected Markdown row into literal cells."""

    text = str(row or "").strip()
    if not (text.startswith("|") and text.endswith("|") and text.count("|") >= 3):
        return []
    return [cell.strip() for cell in text[1:-1].split("|")]


def _fact_markdown_table_rows(fact: AxisFact) -> list[tuple[str, list[str]]]:
    """Return unique complete Markdown rows copied into one fact's evidence."""

    rows: list[tuple[str, list[str]]] = []
    seen: set[str] = set()
    for evidence in fact.source_evidence:
        for raw_row in str(evidence or "").splitlines():
            row = raw_row.strip()
            cells = _markdown_table_cells(row)
            if not cells or row in seen:
                continue
            seen.add(row)
            rows.append((row, cells))
    return rows


def _table_column_label(value: Any) -> str | None:
    """Return a normalized replicate/point column label, if one is explicit."""

    text = unicodedata.normalize("NFKC", str(value or "")).strip()
    match = _TABLE_COLUMN_ID.fullmatch(text)
    if match is None:
        return None
    number = next(
        (
            value
            for value in (
                match.group("number"),
                match.group("named_number"),
                match.group("no_number"),
            )
            if value is not None
        ),
        "",
    )
    if not number:
        return None
    prefix = "#"
    lowered = text.casefold()
    if lowered.startswith("point"):
        prefix = "point"
    elif lowered.startswith("spot"):
        prefix = "spot"
    elif lowered.startswith("sample"):
        prefix = "sample"
    elif lowered.startswith("specimen"):
        prefix = "specimen"
    elif lowered.startswith("no") or lowered.startswith("number"):
        prefix = "no"
    return f"{prefix} {number}"


def _table_column_number(value: Any) -> int | None:
    label = _table_column_label(value)
    if not label:
        return None
    match = re.search(r"\d+", label)
    return int(match.group(0)) if match else None


def _table_column_source_context(
    source_text: str, rows: Sequence[tuple[str, list[str]]]
) -> str:
    """Return bounded source context around one projected Markdown table."""

    text = str(source_text or "")
    if not text:
        return "\n".join(row for row, _ in rows)
    snippets: list[str] = []
    for row, _ in rows:
        position = text.find(row)
        if position < 0:
            # OCR/Markdown normalization can alter spaces around TeX cells;
            # fall back to the first distinctive non-empty cell.
            cells = _markdown_table_cells(row)
            needle = next(
                (
                    str(cell).strip()
                    for cell in cells
                    if len(str(cell).strip()) >= 8
                    and str(cell).strip() in text
                ),
                "",
            )
            position = text.find(needle) if needle else -1
        if position < 0:
            continue
        snippets.append(text[max(0, position - 3000) : position + 3000])
    if not snippets:
        return "\n".join(row for row, _ in rows)
    return "\n".join(dict.fromkeys(snippets))


def _table_column_projection_binding(
    fact: AxisFact, *, source_text: str = ""
) -> dict[str, Any] | None:
    """Recognize a table replicate column without treating it as a material.

    The binding is deliberately limited to a complete header containing at
    least two numbered/point labels and a fact owner that is one of those
    labels.  A single ``#1`` in prose is never enough.  Explicit source prose
    saying that ``#1`` is an independently named sample remains authoritative.
    """

    owner_label = _table_column_label(fact.sample_id_raw)
    if owner_label is None:
        return None
    rows = _fact_markdown_table_rows(fact)
    for header_row, header_cells in rows:
        columns = {
            column: _table_column_label(cell)
            for column, cell in enumerate(header_cells)
        }
        columns = {
            column: label for column, label in columns.items() if label is not None
        }
        if len(columns) < 2 or owner_label not in columns.values():
            continue
        numbers = [
            number
            for number in (_table_column_number(label) for label in columns.values())
            if number is not None
        ]
        # Require a genuinely repeated coordinate set, not two coincidental
        # labels from unrelated cells.  Ordered/adjacent labels are strongest;
        # repeated labels with a named prefix are accepted as a compact table.
        ordered = sorted(set(numbers))
        adjacent = len(ordered) >= 2 and all(
            right - left == 1 for left, right in zip(ordered, ordered[1:])
        )
        prefixes = {
            str(label).split(" ", 1)[0] for label in columns.values()
        }
        if not adjacent and len(prefixes) != 1:
            continue
        context = _table_column_source_context(source_text, rows)
        if _TABLE_COLUMN_EXPLICIT_SAMPLE.search(context):
            continue
        return {
            "header_row": header_row,
            "header_cells": header_cells,
            "rows": rows,
            "columns": columns,
            "column_label": owner_label,
            "column_index": next(
                column for column, label in columns.items() if label == owner_label
            ),
            "context": context,
        }
    return None


def _anchor_is_explicit_table_column_sample(anchor: InventoryAnchor) -> bool:
    """Return true only when a numbered column is explicitly a sample."""

    label = _table_column_label(anchor.sample_id_raw)
    if label is None:
        return False
    return bool(
        _TABLE_COLUMN_EXPLICIT_SAMPLE.search(
            "\n".join(str(row or "") for row in anchor.source_evidence)
        )
    )


def _table_column_state(fact: AxisFact, binding: dict[str, Any]) -> str | None:
    """Resolve the one preparation-state row governing a projected value."""

    data_state = str(fact.data.get("material_state") or "").strip()
    if data_state and not _is_unresolved_alias(data_state):
        return data_state

    value_raw = fact.data.get("value_raw")
    candidates: list[str] = []
    for row, cells in binding["rows"]:
        if row == binding["header_row"] or not cells:
            continue
        first = str(cells[0]).strip()
        if not first or re.fullmatch(r"(?i)(?:std\.?|average|mean|value|unit|---+)", first):
            continue
        expected = _numeric_cell_signature(value_raw)
        selected = binding["column_index"]
        if selected >= len(cells):
            continue
        observed = _numeric_cell_signature(cells[selected])
        if not expected or not observed:
            continue
        if expected == observed or expected[:1] == observed[:1]:
            if _state_descriptor(first) is not None:
                candidates.append(first)
    unique = list(dict.fromkeys(candidates))
    return unique[0] if len(unique) == 1 else None


def _table_state_match_key(value: Any) -> tuple[Any, ...] | None:
    """Return a conservative preparation-state key for table reconciliation.

    ``_state_descriptor`` intentionally treats compact HIP/HT labels as one
    broad category in ordinary routing.  A table coordinate, however, must
    distinguish explicit codes such as ``HIP1`` and ``HIP2``.  Preserve the
    coarse descriptor for prose variants while adding any literal compact
    treatment codes that are present in the state label.
    """

    descriptor = _state_descriptor(value)
    if descriptor is None:
        return None
    codes = tuple(
        sorted(
            {
                re.sub(r"\s+", "", match.group(0)).casefold().replace("_", "-")
                for match in _COMPOSITE_STATE_CODE.finditer(
                    unicodedata.normalize("NFKC", str(value or ""))
                )
            }
        )
    )
    return (*descriptor, codes)


def _filter_table_column_anchors(
    anchors: Sequence[InventoryAnchor],
    facts: Sequence[AxisFact],
    *,
    source_text: str = "",
) -> tuple[list[InventoryAnchor], list[MaterializeIssue]]:
    """Keep numbered table columns out of the material primary inventory."""

    column_keys: set[str] = set()
    bindings: dict[str, dict[str, Any]] = {}
    for fact in facts:
        binding = _table_column_projection_binding(fact, source_text=source_text)
        if binding is None:
            continue
        for label in binding["columns"].values():
            key = _identity_key(label)
            if key:
                column_keys.add(key)
        owner_key = _identity_key(fact.sample_id_raw)
        if owner_key:
            bindings.setdefault(owner_key, binding)
    if not column_keys:
        return list(anchors), []

    kept: list[InventoryAnchor] = []
    issues: list[MaterializeIssue] = []
    for anchor in anchors:
        key = _identity_key(anchor.sample_id_raw)
        if key not in column_keys or _table_column_label(anchor.sample_id_raw) is None:
            kept.append(anchor)
            continue
        # An independently named sample with a non-empty material descriptor
        # is retained.  The projection detector already rejects explicit
        # ``#1 was ...`` source prose; this second guard protects provider
        # inventory rows that carry a richer owner than the table header.
        if str(anchor.material_name_raw or "").strip() and not _is_unresolved_alias(
            anchor.material_name_raw
        ):
            kept.append(anchor)
            continue
        binding = bindings.get(key)
        issues.append(
            MaterializeIssue(
                code="table_column_label_not_material",
                sample_id_raw=anchor.sample_id_raw,
                path=f"items.{anchor.sample_id_raw}",
                message=(
                    "A numbered/point table column was excluded from the material "
                    "inventory because the source does not define it as an "
                    "independent material owner."
                ),
                evidence=(binding or {}).get("rows") or list(anchor.source_evidence),
                expected={
                    "identity": "source-named material or explicit independent sample",
                    "column_label": True,
                },
                actual={"anchor": anchor.model_dump(), "table_binding": binding},
                suggested_action=(
                    "Restore only when the source explicitly defines this numbered "
                    "label as an independent material sample."
                ),
            )
        )
    return kept, issues


def _table_base_candidates(
    index: _IdentityIndex, binding: dict[str, Any]
) -> tuple[str, ...]:
    """Return source-backed base owners named near one table coordinate."""

    context = str(binding.get("context") or "")
    normalized_context = normalize_source_alias(context)
    target_bases: set[str] = set()
    all_bases: set[str] = set()
    descriptor_bases: set[str] = set()
    aligned_descriptor_bases: set[str] = set()
    scores: dict[str, int] = {}
    for canonical, rows in index.anchors.items():
        base = index.state_family_base.get(canonical, canonical)
        if base != canonical:
            continue
        if any(
            _table_column_label(anchor.sample_id_raw) is not None
            for anchor in rows
        ):
            continue
        presentations = {
            index.display_label(canonical),
            *(str(anchor.sample_id_raw or "").strip() for anchor in rows),
            *(str(anchor.material_name_raw or "").strip() for anchor in rows),
        }
        if any(
            str(anchor.material_name_raw or "").strip()
            and is_plausible_material_identity(anchor.material_name_raw)
            for anchor in rows
        ):
            descriptor_bases.add(base)
        # A provider sometimes emits a short process label as the sample ID
        # while copying the real alloy into ``material_name_raw`` (for example
        # ``BJ`` / ``MAR-M247``).  That row is useful context, but it must not
        # compete with the material identity when a numbered table column is
        # being routed.  Prefer a candidate whose source sample ID is itself
        # contained in (or equal to) its material descriptor.  The minimum
        # length keeps two-letter process codes and axis abbreviations from
        # accidentally winning this conservative tie-break.
        if any(_anchor_identity_aligns_with_material(anchor) for anchor in rows):
            aligned_descriptor_bases.add(base)
        presentations = {
            value
            for value in presentations
            if value and is_plausible_material_identity(value)
        }
        if not presentations:
            continue
        occurrences = [
            normalized_context.count(normalize_source_alias(value))
            for value in presentations
            if normalize_source_alias(value)
        ]
        matched = any(count > 0 for count in occurrences) or any(
            _source_label_occurs_in_row(value, context) for value in presentations
        )
        if not matched:
            continue
        all_bases.add(base)
        scores[base] = max(occurrences, default=0)
        if any(str(anchor.role or "").casefold() == "target" for anchor in rows):
            target_bases.add(base)
    candidates = target_bases or all_bases
    if descriptor_bases & candidates:
        candidates = descriptor_bases & candidates
    if aligned_descriptor_bases & candidates:
        candidates = aligned_descriptor_bases & candidates
    if len(candidates) <= 1:
        return tuple(sorted(candidates))
    # A short process/state code (for example ``BJ`` or ``HIP2``) can appear
    # in the same context as the real alloy name. Prefer the owner whose
    # presentation is repeated in the local source block. Equal occurrence
    # counts remain ambiguous even if one label happens to be longer; that
    # prevents arbitrary selection between two genuinely named materials.
    best_score = max(scores.get(candidate, 0) for candidate in candidates)
    best = {candidate for candidate in candidates if scores.get(candidate, 0) == best_score}
    return tuple(sorted(best))


def _anchor_identity_aligns_with_material(anchor: InventoryAnchor) -> bool:
    """Return whether an anchor's sample ID names its material identity.

    Extraction providers occasionally use a short manufacturing/process code
    (``BJ``, ``WA``, ``LPBF``) as ``sample_id_raw`` while putting the alloy name
    in ``material_name_raw``.  Such an anchor is not a competing material base
    for table-column routing.  This rule is intentionally presentation-only:
    it requires a non-trivial sample key to occur in the material descriptor
    (or exact equality), and therefore leaves genuinely distinct material
    candidates ambiguous and isolated.
    """

    sample = _identity_key(anchor.sample_id_raw)
    material = _identity_key(anchor.material_name_raw)
    if not sample or not material:
        return False
    if sample == material:
        return True
    if len(sample) < 4 or len(material) < 4:
        return False
    # A process-family code such as LPBF can itself be contained in a richer
    # alloy descriptor without naming a material.  Keep those
    # labels out of the material-owner tie-break.
    if _process_family(anchor.sample_id_raw) is not None:
        return False
    return sample in material


def _table_state_owner(
    index: _IdentityIndex,
    base: str,
    state: str,
    fact: AxisFact,
    binding: dict[str, Any],
) -> str | None:
    """Resolve or register one state owner under a proven material family."""

    descriptor = _state_descriptor(state)
    if descriptor is None:
        return None
    state_match_key = _table_state_match_key(state)
    existing: set[str] = set()
    for canonical in index.anchors:
        if index.state_family_base.get(canonical, canonical) != base:
            continue
        if canonical == base:
            # Unqualified base anchors may repeat ``state_raw`` as context,
            # but they are not a state-qualified material identity.
            continue
        for anchor in index.anchors.get(canonical, []):
            anchor_descriptor = _table_state_match_key(anchor.state_raw)
            if anchor_descriptor == state_match_key:
                existing.add(canonical)
                break
    if len(existing) > 1:
        return None
    if existing:
        return next(iter(existing))

    parent_rows = index.anchors.get(base, [])
    if not parent_rows:
        return None
    parent = max(parent_rows, key=lambda anchor: anchor.confidence)
    display = f"{index.display_label(base)} [{state}]"
    canonical = _identity_key(display)
    if not canonical or not is_plausible_material_identity(display):
        return None
    if canonical not in index.anchors:
        index.add_primary(display)
        index.add_anchor_as(
            parent.model_copy(
                update={
                    "sample_id_raw": display,
                    "state_raw": state,
                    "source_evidence": list(fact.source_evidence),
                    "confidence": fact.confidence,
                }
            ),
            canonical,
        )
        index.add_state_alias(state, canonical)
        index.add_state_family(canonical, base)
    return canonical


def _reconcile_table_column_facts(
    index: _IdentityIndex,
    facts: Sequence[AxisFact],
    *,
    source_text: str = "",
) -> tuple[list[AxisFact], list[MaterializeIssue]]:
    """Bind table replicate facts to one material/state coordinate or isolate."""

    reconciled: list[AxisFact] = []
    issues: list[MaterializeIssue] = []
    for fact in facts:
        binding = _table_column_projection_binding(fact, source_text=source_text)
        if binding is None:
            reconciled.append(fact)
            continue
        bases = _table_base_candidates(index, binding)
        state = _table_column_state(fact, binding)
        selected_owner: str | None = None
        if len(bases) == 1 and state is not None:
            selected_owner = _table_state_owner(index, bases[0], state, fact, binding)
        if selected_owner is None:
            issues.append(
                MaterializeIssue(
                    code="table_column_owner_ambiguous",
                    sample_id_raw=fact.sample_id_raw,
                    path=f"items.{fact.sample_id_raw}.Extracted_Data",
                    message=(
                        "A table-column fact was isolated because its material/state "
                        "coordinate was not uniquely recoverable."
                    ),
                    evidence=list(fact.source_evidence),
                    expected={
                        "owner": "one source-backed base material",
                        "state": "one explicit preparation state",
                        "broadcast": False,
                    },
                    actual={
                        "fact": fact.model_dump(),
                        "column": binding,
                        "base_candidates": [index.display_label(base) for base in bases],
                        "state": state,
                    },
                    suggested_action=(
                        "Review the table caption/row and restore only when one "
                        "material and one preparation state are explicit."
                    ),
                )
            )
            continue

        data = deepcopy(fact.data)
        column_detail = f"table column: {binding['column_label']}"
        existing_note = str(data.get("raw_note") or "").strip()
        data["raw_note"] = (
            f"{existing_note}; {column_detail}" if existing_note else column_detail
        )
        context = str(binding.get("context") or "")
        if (
            not str(data.get("test_specimen_raw") or "").strip()
            and re.search(r"(?i)\bcuboids?\b", context)
        ):
            data["test_specimen_raw"] = "cuboid"
        updated = fact.model_copy(
            update={
                "sample_id_raw": index.display_label(selected_owner),
                "data": data,
            }
        )
        reconciled.append(updated)
        issues.append(
            MaterializeIssue(
                code="table_column_owner_reconciled",
                sample_id_raw=index.display_label(selected_owner),
                path=(
                    f"items.{index.display_label(selected_owner)}.Extracted_Data"
                ),
                message=(
                    "A numbered/point table column was retained as a coordinate "
                    "under the unique material/state owner instead of becoming "
                    "a separate material item."
                ),
                evidence={
                    "table_rows": binding["rows"],
                    "column": binding["column_label"],
                },
                expected={
                    "owner": "one source-backed material/state",
                    "column_as_material": False,
                    "replicate_detail_retained": True,
                },
                actual={
                    "before_owner": fact.sample_id_raw,
                    "after_owner": index.display_label(selected_owner),
                    "base_candidates": [index.display_label(base) for base in bases],
                    "state": _table_column_state(fact, binding),
                    "fact": fact.model_dump(),
                },
                suggested_action=(
                    "Review only if the numbered column is explicitly declared "
                    "to be an independent material identity."
                ),
            )
        )
    return reconciled, issues


def _fact_has_table_coordinate(fact: AxisFact) -> bool:
    """Return whether a fact carries a resolved table-column coordinate."""

    return bool(
        re.search(
            r"(?i)(?:^|[;|])\s*table\s+column\s*:",
            str(fact.data.get("raw_note") or ""),
        )
    )


_TENSILE_DIRECTION_AGGREGATE = re.compile(
    r"(?is)(?:"
    r"(?:independent|regardless|irrespective)\s+of\s+(?:the\s+)?"
    r"(?:build|test)\s*[- ]?direction"
    r"|(?:build|test)\s*[- ]?direction\s+aggregate"
    r"|no\s+significant\s+anisotropy"
    r").{0,180}\b(?:average|mean)\b"
    r"|\b(?:average|mean)\b.{0,180}(?:"
    r"(?:independent|regardless|irrespective)\s+of\s+(?:the\s+)?"
    r"(?:build|test)\s*[- ]?direction"
    r"|(?:build|test)\s*[- ]?direction\s+aggregate"
    r"|no\s+significant\s+anisotropy"
    r")"
)


def _fact_source_context(source_text: str, fact: AxisFact) -> str:
    text = str(source_text or "")
    if not text:
        return "\n".join(str(row or "") for row in fact.source_evidence)
    snippets: list[str] = []
    for raw in fact.source_evidence:
        row = str(raw or "").strip()
        if not row:
            continue
        # OCR/markdown normalization can change whitespace or case between
        # the provider quote and the source corpus.  Try progressively looser
        # literal lookups before falling back to a property-name anchor below.
        position = text.find(row)
        if position < 0:
            position = text.casefold().find(row.casefold())
        if position < 0:
            compact_text = re.sub(r"\s+", " ", text).casefold()
            compact_row = re.sub(r"\s+", " ", row).strip().casefold()
            compact_position = compact_text.find(compact_row)
            if compact_position >= 0:
                # Compact offsets do not map exactly to source offsets.  A
                # broad window around the corresponding ratio is sufficient
                # for orientation/context detection and keeps this helper
                # independent of any OCR-specific tokenization.
                ratio = compact_position / max(len(compact_text), 1)
                position = int(ratio * len(text))
        if position < 0:
            continue
        snippets.append(text[max(0, position - 1200) : position + len(row) + 1200])
    if not snippets:
        # When the quote is only the value-bearing tail of a sentence (for
        # example ``the average yield strength ...``), the aggregate marker can
        # live immediately before it in the source.  Use the property label as
        # a conservative secondary anchor; do not use bare numeric values,
        # which are commonly repeated in unrelated treatment tables.
        property_name = str(fact.data.get("property_name_raw") or "").strip()
        if len(property_name) >= 4:
            position = text.casefold().find(property_name.casefold())
            if position >= 0:
                snippets.append(text[max(0, position - 1200) : position + 1600])
    return "\n".join(dict.fromkeys(snippets)) or "\n".join(fact.source_evidence)


def _quarantine_unoriented_tensile_averages(
    index: _IdentityIndex,
    facts: Sequence[AxisFact],
    *,
    source_text: str = "",
) -> tuple[list[AxisFact], list[MaterializeIssue]]:
    """Keep prose averages out of directional tensile coordinates."""

    kept: list[AxisFact] = []
    issues: list[MaterializeIssue] = []
    for fact in facts:
        if not _numeric_core_tensile_fact(fact):
            kept.append(fact)
            continue
        data_source = str(fact.data.get("data_source") or "").strip().casefold()
        if data_source in {"table", "chart", "figure", "image"}:
            kept.append(fact)
            continue
        fact_context = "\n".join(
            [
                str(fact.data.get("test_condition_raw") or ""),
                str(fact.data.get("test_specimen_raw") or ""),
                *fact.source_evidence,
            ]
        )
        if _tensile_orientation_tokens(fact_context, owner_label=True):
            kept.append(fact)
            continue
        source_context = _fact_source_context(source_text, fact)
        # The provider often quotes only the value sentence while the phrase
        # establishing that it is an orientation-independent average appears
        # in the preceding source sentence.  Evaluate the aggregate gate on
        # both the fact and its grounded source window; otherwise these values
        # bypass quarantine and are later treated as directional properties.
        aggregate_context = f"{fact_context}\n{source_context}"
        if not _TENSILE_DIRECTION_AGGREGATE.search(aggregate_context):
            kept.append(fact)
            continue
        orientation_tokens = _tensile_orientation_tokens(source_context)
        if len(orientation_tokens) < 2:
            kept.append(fact)
            continue
        owners = _group_route(index, fact)
        owner_label = (
            index.display_label(owners[0]) if len(owners) == 1 else fact.sample_id_raw
        )
        issues.append(
            MaterializeIssue(
                code="tensile_average_without_orientation",
                sample_id_raw=owner_label,
                path=f"items.{owner_label}.Extracted_Data.Properties",
                message=(
                    "A prose tensile average was isolated because the same source "
                    "block reports distinct orientation-specific results."
                ),
                evidence=list(fact.source_evidence),
                expected={
                    "orientation": "explicit unique direction or aggregate-only source",
                    "core_properties": "no unqualified average mixed with directional values",
                },
                actual={
                    "fact": fact.model_dump(),
                    "source_context": source_context,
                    "orientation_tokens": sorted(orientation_tokens),
                },
                suggested_action=(
                    "Review the original chart/table; restore only when this average "
                    "is the intended aggregate coordinate rather than a directional projection."
                ),
            )
        )
    return kept, issues


def _reference_marker_candidates(value: Any) -> list[dict[str, str]]:
    """Return explicit literature/standard markers in one owner or value cell."""

    text = unicodedata.normalize("NFKC", str(value or "")).strip()
    if not text:
        return []
    normalized_tex = re.sub(r"[${}\\_]", "", text)
    candidates: list[dict[str, str]] = []
    for match in _REFERENCE_NUMERIC_CITATION.finditer(normalized_tex):
        candidates.append(
            {
                "kind": "numeric_citation",
                "raw": match.group(0),
                "label": f"[{match.group(1)}]",
            }
        )
    for match in _REFERENCE_STANDARD_MARKER.finditer(normalized_tex):
        label = re.sub(r"\s+", " ", match.group(0)).strip()
        candidates.append(
            {"kind": "external_standard", "raw": match.group(0), "label": label}
        )
    for match in _REFERENCE_AUTHOR_YEAR.finditer(normalized_tex):
        label = match.group(0).strip(" ()")
        if re.match(r"(?i)^(?:alloy|current|figure|material|present|sample|table|this)\b", label):
            continue
        candidates.append(
            {"kind": "author_year", "raw": match.group(0), "label": label}
        )

    unique: dict[str, dict[str, str]] = {}
    for candidate in candidates:
        key = normalize_source_alias(candidate["label"])
        if key:
            unique.setdefault(key, candidate)
    return list(unique.values())


def _reference_author_keys(value: Any) -> set[str]:
    """Return explicit ``Author et al.`` identities from one local string."""

    return {
        normalize_source_alias(match.group("author"))
        for match in _REFERENCE_PROSE_AUTHOR.finditer(str(value or ""))
        if normalize_source_alias(match.group("author"))
    }


def _reference_marker_matches_text(value: Any, marker: Any) -> bool:
    """Match a citation marker without requiring a rich owner to equal it."""

    marker_text = str(marker or "").strip()
    marker_key = normalize_source_alias(marker_text)
    if not marker_key:
        return False
    explicit_markers = {
        normalize_source_alias(candidate["label"])
        for candidate in _reference_marker_candidates(value)
        if normalize_source_alias(candidate["label"])
    }
    if marker_key in explicit_markers:
        return True
    marker_authors = _reference_author_keys(marker_text)
    value_authors = _reference_author_keys(value)
    return bool(
        len(marker_authors) == 1
        and len(value_authors) == 1
        and marker_authors == value_authors
    )


def _reference_anchor_matches_binding(
    anchor: InventoryAnchor, binding: Mapping[str, Any]
) -> bool:
    """Require a prose binding to select one already-existing Reference."""

    if not (
        anchor.role == "Reference"
        and str(anchor.data_nature or "").startswith("Literature_")
    ):
        return False
    # The citation must be part of the declared Reference identity. Merely
    # mentioning an author in anchor evidence is insufficient: otherwise an
    # ordinary label such as ``Published LPBF`` can be rewritten even though
    # it already has a stable independent owner.
    return _reference_marker_matches_text(
        anchor.sample_id_raw, binding.get("author_marker")
    )


def _reference_parent_display_base(
    anchor: InventoryAnchor, marker: Any
) -> str:
    """Keep a rich Reference owner; expand citation-only parents by material."""

    owner = re.sub(
        r"\s*\[\s*reference\s*\]\s*$",
        "",
        str(anchor.sample_id_raw or "").strip(),
        flags=re.I,
    )
    residual = owner
    for match in reversed(list(_REFERENCE_PROSE_AUTHOR.finditer(residual))):
        residual = residual[: match.start()] + " " + residual[match.end() :]
    residual = re.sub(r"\[\s*\d+\s*\]", " ", residual)
    residual = re.sub(r"\b(?:19|20)\d{2}[a-z]?\b", " ", residual, flags=re.I)
    residual_tokens = set(re.findall(r"[a-z0-9]+", normalize_source_alias(residual)))
    residual_tokens -= {"al", "et", "reference"}
    if residual_tokens:
        return owner
    material = str(anchor.material_name_raw or "").strip()
    if material:
        return material
    return owner or str(marker or "").strip()


def _one_reference_marker(*cells: tuple[str, str]) -> dict[str, str] | None:
    """Return one unique marker and its binding cell, never competing markers."""

    found: dict[str, dict[str, str]] = {}
    for source, cell in cells:
        for candidate in _reference_marker_candidates(cell):
            key = normalize_source_alias(candidate["label"])
            record = {**candidate, "source": source}
            previous = found.get(key)
            if previous is not None and previous["source"] != source:
                previous["source"] = "multiple_cells"
            else:
                found.setdefault(key, record)
    if len(found) != 1:
        return None
    return next(iter(found.values()))


def _cell_without_reference_markers(value: Any) -> str:
    """Remove marker presentation so owner/value literals can be compared."""

    text = unicodedata.normalize("NFKC", str(value or ""))
    normalized_tex = re.sub(r"[${}\\_]", "", text)
    for candidate in _reference_marker_candidates(normalized_tex):
        normalized_tex = normalized_tex.replace(candidate["raw"], " ")
    return normalized_tex.strip(" ()[]")


def _table_owner_cell_matches(owner: Any, cell: Any) -> bool:
    owner_key = normalize_source_alias(owner)
    cell_key = normalize_source_alias(cell)
    if not owner_key or not cell_key:
        return False
    if owner_key == cell_key:
        return True
    return owner_key == normalize_source_alias(_cell_without_reference_markers(cell))


def _numeric_cell_signature(value: Any) -> tuple[float, ...]:
    """Return literal numeric tokens for a table value after citation removal."""

    text = _cell_without_reference_markers(value)
    text = text.replace("−", "-").replace("–", "-").replace("—", "-")
    numbers = re.findall(
        r"(?<![A-Za-z])[-+]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?",
        text,
    )
    parsed: list[float] = []
    for number in numbers:
        try:
            parsed.append(float(number))
        except ValueError:
            return ()
    return tuple(parsed)


def _table_value_cell_matches(value_raw: Any, cell: Any) -> bool:
    expected = _numeric_cell_signature(value_raw)
    return bool(expected and expected == _numeric_cell_signature(cell))


def _cited_tensile_table_binding(fact: AxisFact) -> dict[str, Any] | None:
    """Bind one tensile value to one cited table column or cited row owner."""

    if not _numeric_core_tensile_fact(fact):
        return None
    data_source = str(fact.data.get("data_source") or "").strip().casefold()
    if data_source not in {"table", "unknown", ""}:
        return None
    rows = _fact_markdown_table_rows(fact)
    if len(rows) < 2:
        return None

    owner = str(fact.sample_id_raw or "").strip()
    decisions: list[dict[str, Any]] = []

    # Column-oriented table: one header cell names the owner and the value is
    # copied from exactly that column in a second complete row.
    for header_row, header_cells in rows:
        owner_columns = [
            index
            for index, cell in enumerate(header_cells)
            if _table_owner_cell_matches(owner, cell)
        ]
        if len(owner_columns) != 1:
            continue
        selected_column = owner_columns[0]
        header_cell = header_cells[selected_column]
        for value_row, value_cells in rows:
            if value_row == header_row or len(value_cells) != len(header_cells):
                continue
            value_cell = value_cells[selected_column]
            if not _table_value_cell_matches(fact.data.get("value_raw"), value_cell):
                continue
            marker = _one_reference_marker(
                ("value_cell", value_cell), ("header_cell", header_cell)
            )
            if marker is None or _REFERENCE_CURRENT_STUDY.search(
                f"{header_cell} {value_cell}"
            ):
                continue
            decisions.append(
                {
                    "binding": "column_value_cell",
                    "header_row": header_row,
                    "value_row": value_row,
                    "owner_cell": header_cell,
                    "value_cell": value_cell,
                    "owner_column": selected_column,
                    "selected_column": selected_column,
                    "marker": marker,
                }
            )

    # Row-oriented table: the owner label and citation occupy one cell and the
    # tensile value occupies one unique sibling cell in that same row.
    for value_row, value_cells in rows:
        owner_columns = [
            index
            for index, cell in enumerate(value_cells)
            if _table_owner_cell_matches(owner, cell)
        ]
        if len(owner_columns) != 1:
            continue
        owner_column = owner_columns[0]
        owner_cell = value_cells[owner_column]
        value_columns = [
            index
            for index, cell in enumerate(value_cells)
            if index != owner_column
            and _table_value_cell_matches(fact.data.get("value_raw"), cell)
        ]
        if len(value_columns) != 1:
            continue
        selected_column = value_columns[0]
        value_cell = value_cells[selected_column]
        marker = _one_reference_marker(
            ("owner_cell", owner_cell), ("value_cell", value_cell)
        )
        if marker is None or _REFERENCE_CURRENT_STUDY.search(
            f"{owner_cell} {value_cell}"
        ):
            continue
        header_rows = [
            row
            for row, cells in rows
            if row != value_row and len(cells) == len(value_cells)
        ]
        if not header_rows:
            continue
        decisions.append(
            {
                "binding": "row_owner_value_cell",
                "header_row": header_rows[0],
                "value_row": value_row,
                "owner_cell": owner_cell,
                "value_cell": value_cell,
                "owner_column": owner_column,
                "selected_column": selected_column,
                "marker": marker,
            }
        )

    unique: dict[str, dict[str, Any]] = {}
    for decision in decisions:
        signature = json.dumps(decision, ensure_ascii=False, sort_keys=True)
        unique.setdefault(signature, decision)
    if len(unique) != 1:
        return None
    return next(iter(unique.values()))


def _cited_property_table_binding(fact: AxisFact) -> dict[str, Any] | None:
    """Bind any numeric Property table cell to one cited owner coordinate.

    Tensile facts have a long-standing reference-owner recovery path.  The
    same table grammar is also used for hardness, density, modulus, and other
    numeric Properties.  Keep this extension deliberately numeric and
    one-to-one: a single owner column/row, one value cell, and one unique
    citation/standard marker.  Non-table, qualitative, multi-value, or
    ambiguous candidates remain unchanged.
    """

    if not isinstance(fact, PropertyFact) or _numeric_core_tensile_fact(fact):
        return None
    data_source = str(fact.data.get("data_source") or "").strip().casefold()
    if data_source not in {"table", "unknown", ""}:
        return None
    if not _numeric_cell_signature(fact.data.get("value_raw")):
        return None
    rows = _fact_markdown_table_rows(fact)
    if len(rows) < 2:
        return None

    owner = str(fact.sample_id_raw or "").strip()
    decisions: list[dict[str, Any]] = []
    for header_row, header_cells in rows:
        owner_columns = [
            index
            for index, cell in enumerate(header_cells)
            if _table_owner_cell_matches(owner, cell)
        ]
        if len(owner_columns) != 1:
            continue
        selected_column = owner_columns[0]
        header_cell = header_cells[selected_column]
        for value_row, value_cells in rows:
            if value_row == header_row or len(value_cells) != len(header_cells):
                continue
            value_cell = value_cells[selected_column]
            if not _table_value_cell_matches(
                fact.data.get("value_raw"), value_cell
            ):
                continue
            marker = _one_reference_marker(
                ("value_cell", value_cell), ("header_cell", header_cell)
            )
            if marker is None or _REFERENCE_CURRENT_STUDY.search(
                f"{header_cell} {value_cell}"
            ) or marker["kind"] not in {"external_standard", "numeric_citation"}:
                continue
            decisions.append(
                {
                    "binding": "column_value_cell",
                    "header_row": header_row,
                    "value_row": value_row,
                    "owner_cell": header_cell,
                    "value_cell": value_cell,
                    "owner_column": selected_column,
                    "selected_column": selected_column,
                    "marker": marker,
                }
            )

    for value_row, value_cells in rows:
        owner_columns = [
            index
            for index, cell in enumerate(value_cells)
            if _table_owner_cell_matches(owner, cell)
        ]
        if len(owner_columns) != 1:
            continue
        owner_column = owner_columns[0]
        owner_cell = value_cells[owner_column]
        value_columns = [
            index
            for index, cell in enumerate(value_cells)
            if index != owner_column
            and _table_value_cell_matches(fact.data.get("value_raw"), cell)
        ]
        if len(value_columns) != 1:
            continue
        selected_column = value_columns[0]
        value_cell = value_cells[selected_column]
        marker = _one_reference_marker(
            ("owner_cell", owner_cell), ("value_cell", value_cell)
        )
        if marker is None or _REFERENCE_CURRENT_STUDY.search(
            f"{owner_cell} {value_cell}"
        ) or marker["kind"] not in {"external_standard", "numeric_citation"}:
            continue
        header_rows = [
            row
            for row, cells in rows
            if row != value_row and len(cells) == len(value_cells)
        ]
        if not header_rows:
            continue
        decisions.append(
            {
                "binding": "row_owner_value_cell",
                "header_row": header_rows[0],
                "value_row": value_row,
                "owner_cell": owner_cell,
                "value_cell": value_cell,
                "owner_column": owner_column,
                "selected_column": selected_column,
                "marker": marker,
            }
        )

    unique: dict[str, dict[str, Any]] = {}
    for decision in decisions:
        signature = json.dumps(decision, ensure_ascii=False, sort_keys=True)
        unique.setdefault(signature, decision)
    if len(unique) != 1:
        return None
    return next(iter(unique.values()))


def _reference_tensile_display(owner: str, marker: str) -> str:
    qualified = owner if _reference_marker_matches_text(owner, marker) else f"{owner} {marker}"
    return f"{qualified.strip()} [reference]"


def _dense_reference_table_scope(
    fact: AxisFact,
    source_text: str,
    tables: Sequence[Any],
) -> dict[str, Any] | None:
    """Return one literal comparison-table scope for an unconditioned fact.

    The scope is deliberately weaker than a tensile protocol: it records only
    the table coordinate (for example ``Table 3``).  It never imports the
    current study's test temperature, rate, standard, or specimen geometry
    into literature Reference values.
    """

    if str(fact.data.get("test_condition_raw") or "").strip():
        return None
    if not source_text or not (
        owner_state_condition_v202_enabled()
        and source_coordinate_precision_v202_enabled()
    ):
        return None

    coordinate = resolve_structured_table_record(fact, source_text)
    if coordinate.status != "matched":
        return None
    matched_tables = [
        table
        for table in tables
        if table.kind == coordinate.table_kind
        and table.block_index == coordinate.block_index
    ]
    if len(matched_tables) != 1:
        return None
    table = matched_tables[0]

    marker_rows: dict[str, dict[str, str]] = {}
    seen_cells: set[tuple[int, int]] = set()
    for row in table.rows:
        for cell in row:
            if cell is None or cell.origin in seen_cells:
                continue
            seen_cells.add(cell.origin)
            if _REFERENCE_CURRENT_STUDY.search(cell.raw_text):
                continue
            for marker in _reference_marker_candidates(cell.raw_text):
                if marker["kind"] not in {
                    "numeric_citation",
                    "external_standard",
                }:
                    continue
                key = normalize_source_alias(marker["label"])
                if key:
                    marker_rows.setdefault(key, marker)
    if len(marker_rows) < 3:
        return None

    positions: list[int] = []
    cursor = 0
    while len(positions) < 2:
        position = source_text.find(table.raw, cursor)
        if position < 0:
            break
        positions.append(position)
        cursor = position + max(len(table.raw), 1)
    if len(positions) != 1:
        return None

    nearby_lines = [
        line.strip()
        for line in source_text[: positions[0]].splitlines()
        if line.strip()
    ][-4:]
    caption_matches = [
        (index, match, line)
        for index, line in enumerate(nearby_lines)
        if (match := _REFERENCE_TABLE_CAPTION.fullmatch(line)) is not None
    ]
    # The caption must be the sole nearby Table-N declaration and the nearest
    # non-empty source line.  Split captions, repeated captions, and detached
    # mentions fail closed.
    if (
        len(caption_matches) != 1
        or caption_matches[0][0] != len(nearby_lines) - 1
    ):
        return None
    _, caption_match, caption_raw = caption_matches[0]
    scope = re.sub(r"\s+", " ", caption_match.group("scope")).strip()
    return {
        "scope": scope,
        "caption_raw": caption_raw,
        "reference_markers": [
            marker_rows[key]["label"] for key in sorted(marker_rows)
        ],
        "coordinate": coordinate.to_dict(),
        "decision_key": f"reference-table-scope:{coordinate.decision_key}:{scope.casefold()}",
    }


def _reference_owner_base(value: Any) -> str:
    """Normalize a generated/reference display to its comparison base label."""

    text = str(value or "").strip()
    text = re.sub(r"\s*\[\s*reference\s*\]\s*$", "", text, flags=re.I)
    text = re.sub(r"\s*\[\s*\d{1,4}\s*\]\s*$", "", text)
    return normalize_source_alias(text)


def _recover_cited_tensile_reference_owners(
    anchors: Sequence[InventoryAnchor],
    facts: Sequence[AxisFact],
    source_text: str = "",
) -> tuple[list[InventoryAnchor], list[AxisFact], list[MaterializeIssue]]:
    """Split source-bound cited tensile facts into independent Reference items."""

    anchor_rows = list(anchors)
    fact_rows = list(facts)
    tables = logical_tables(source_text) if source_text else ()
    exact_anchors: dict[str, list[InventoryAnchor]] = {}
    for anchor in anchor_rows:
        exact_anchors.setdefault(_identity_key(anchor.sample_id_raw), []).append(anchor)
    reference_anchors: dict[str, InventoryAnchor] = {
        _identity_key(anchor.sample_id_raw): anchor
        for anchor in anchor_rows
        if anchor.role == "Reference"
        and str(anchor.data_nature or "").startswith("Literature_")
    }

    issues: list[MaterializeIssue] = []
    for index, fact in enumerate(fact_rows):
        binding = _cited_tensile_table_binding(fact)
        if binding is None:
            continue
        table_scope = _dense_reference_table_scope(fact, source_text, tables)
        marker = binding["marker"]
        before_owner = str(fact.sample_id_raw or "").strip()
        display = _reference_tensile_display(before_owner, marker["label"])
        display_key = _identity_key(display)
        if not display_key or not is_plausible_material_identity(display):
            continue

        parent_candidates = exact_anchors.get(_identity_key(before_owner), [])
        parent = (
            max(parent_candidates, key=lambda row: row.confidence)
            if parent_candidates
            else None
        )
        material_name = str(
            (parent.material_name_raw if parent is not None else None)
            or before_owner
        ).strip()
        evidence = list(dict.fromkeys(fact.source_evidence))
        if display_key not in reference_anchors:
            reference_anchor = InventoryAnchor(
                sample_id_raw=display,
                material_name_raw=material_name,
                # The cited table proves a separate owner and source role, but
                # not a preparation-state equivalence with the current-study
                # item.  Leaving state empty also prevents cross-role collapse
                # through a shared generic state alias such as ``wrought``.
                state_raw=None,
                role="Reference",
                data_nature="Literature_Experimental",
                source_evidence=evidence,
                confidence=fact.confidence,
            )
            anchor_rows.append(reference_anchor)
            reference_anchors[display_key] = reference_anchor

        updated_data = deepcopy(fact.data)
        if table_scope is not None:
            updated_data["test_condition_raw"] = table_scope["scope"]
        updated_fact = fact.model_copy(
            update={"sample_id_raw": display, "data": updated_data}
        )
        fact_rows[index] = updated_fact
        issues.append(
            MaterializeIssue(
                code="reference_tensile_owner_recovered",
                sample_id_raw=display,
                path=f"items.{display}.Extracted_Data.Properties",
                message=(
                    "A numeric core-tensile table fact was moved to the "
                    "independent literature/standard owner bound to its exact cell."
                ),
                evidence={
                    "header_row": binding["header_row"],
                    "value_row": binding["value_row"],
                    "owner_cell": binding["owner_cell"],
                    "value_cell": binding["value_cell"],
                },
                expected={
                    "binding": "one owner column/row, one numeric value cell, one reference marker",
                    "fact_level_split": True,
                    "shared_item_role_changed": False,
                },
                actual={
                    "before_owner": before_owner,
                    "after_owner": display,
                    "marker": marker["label"],
                    "marker_kind": marker["kind"],
                    "marker_source": marker["source"],
                    "binding": binding["binding"],
                    "owner_column": binding["owner_column"],
                    "selected_column": binding["selected_column"],
                    "fact": fact.model_dump(),
                },
                suggested_action=(
                    "Review only if the cited cell describes the current study "
                    "rather than an independent comparison source."
                ),
            )
        )
        if table_scope is not None:
            issues.append(
                MaterializeIssue(
                    code="reference_table_scope_recovered",
                    sample_id_raw=display,
                    path=f"items.{display}.Extracted_Data.Properties",
                    message=(
                        "An empty cited Reference condition was assigned only "
                        "the literal scope of its dense comparison table."
                    ),
                    evidence={
                        "caption_raw": table_scope["caption_raw"],
                        "source_coordinate": table_scope["coordinate"],
                    },
                    expected={
                        "minimum_distinct_reference_markers": 3,
                        "scope_source": "one unique adjacent Table-N caption",
                        "target_tensile_protocol_inherited": False,
                        "overwrite_existing_condition": False,
                    },
                    actual={
                        "before": fact.model_dump(),
                        "after": updated_fact.model_dump(),
                        "scope": table_scope["scope"],
                        "caption_raw": table_scope["caption_raw"],
                        "reference_markers": table_scope[
                            "reference_markers"
                        ],
                        "decision_key": table_scope["decision_key"],
                        "owner_invented": False,
                    },
                    suggested_action=(
                        "Review only if the cited value belongs outside the "
                        "identified comparison table."
                    ),
                )
            )
    return anchor_rows, fact_rows, issues


def _recover_cited_property_reference_owners(
    anchors: Sequence[InventoryAnchor], facts: Sequence[AxisFact]
) -> tuple[list[InventoryAnchor], list[AxisFact], list[MaterializeIssue]]:
    """Split cited non-tensile table Properties into independent References.

    This is the non-tensile counterpart of
    ``_recover_cited_tensile_reference_owners``.  It never reclassifies a
    prose value or a table with competing coordinates; only a unique numeric
    cell carrying one citation/standard marker is moved.
    """

    anchor_rows = list(anchors)
    fact_rows = list(facts)
    reference_anchors: dict[str, InventoryAnchor] = {
        _identity_key(anchor.sample_id_raw): anchor
        for anchor in anchor_rows
        if anchor.role == "Reference"
        and str(anchor.data_nature or "").startswith("Literature_")
    }
    issues: list[MaterializeIssue] = []
    for index, fact in enumerate(fact_rows):
        binding = _cited_property_table_binding(fact)
        if binding is None:
            continue
        before_owner = str(fact.sample_id_raw or "").strip()
        marker = binding["marker"]
        reference_siblings = [
            anchor
            for anchor in reference_anchors.values()
            if _reference_owner_base(anchor.sample_id_raw)
            == _reference_owner_base(before_owner)
        ]
        parent_candidates = [
            anchor
            for anchor in anchor_rows
            if _identity_key(anchor.sample_id_raw)
            == _identity_key(before_owner)
        ]
        parent_roles = {
            str(anchor.role or "").strip().casefold()
            for anchor in parent_candidates
            if str(anchor.role or "").strip()
        }
        # A numeric citation in a comparison table is source evidence for a
        # literature owner, but only when the declared owner is a current
        # Target.  Never reclassify a fact already attached to a Reference.
        if parent_roles and parent_roles != {"target"}:
            continue
        # Numeric tensile recovery may already have created the paper-local
        # Reference item for this same comparison column.  Reuse it only when
        # the role coordinate is explicit; a lone standard-marked hardness
        # value must not manufacture a Reference owner from the citation alone.
        # For a numeric citation, an existing sibling with a *different*
        # citation is not the same source coordinate (for example WEBAM [44]
        # and WEBAM [45]); create the exact source-backed sibling below rather
        # than silently attaching the value to the wrong reference.
        if marker["kind"] == "numeric_citation":
            exact_siblings = [
                anchor
                for anchor in reference_siblings
                if normalize_source_alias(marker["label"])
                in {
                    normalize_source_alias(candidate["label"])
                    for candidate in _reference_marker_candidates(
                        anchor.sample_id_raw
                    )
                }
            ]
            if len(exact_siblings) == 1:
                # Preserve the historical target behavior when the same
                # citation already belongs to the tensile/reference bundle;
                # a non-tensile row alone does not prove that it shares the
                # same independent owner.  The mismatch case below is the
                # safe repair for a concrete source coordinate such as
                # WEBAM [45] alongside an existing WEBAM [44] sibling.
                continue
            elif len(reference_siblings) >= 1:
                display = _reference_tensile_display(
                    before_owner, marker["label"]
                )
            else:
                continue
        elif len(reference_siblings) == 1:
            display = reference_siblings[0].sample_id_raw
        else:
            continue
        display_key = _identity_key(display)
        if not display_key or not is_plausible_material_identity(display):
            continue
        parent = (
            max(parent_candidates, key=lambda row: row.confidence)
            if parent_candidates
            else None
        )
        material_name = str(
            (parent.material_name_raw if parent is not None else None)
            or before_owner
        ).strip()
        evidence = list(dict.fromkeys(fact.source_evidence))
        if display_key not in reference_anchors:
            reference_anchor = InventoryAnchor(
                sample_id_raw=display,
                material_name_raw=material_name,
                state_raw=None,
                role="Reference",
                data_nature="Literature_Experimental",
                source_evidence=evidence,
                confidence=fact.confidence,
            )
            anchor_rows.append(reference_anchor)
            reference_anchors[display_key] = reference_anchor

        fact_rows[index] = fact.model_copy(update={"sample_id_raw": display})
        issues.append(
            MaterializeIssue(
                code="reference_property_owner_recovered",
                sample_id_raw=display,
                path=f"items.{display}.Extracted_Data.Properties",
                message=(
                    "A numeric non-tensile table Property was moved from a "
                    "duplicate current Target label to the independent "
                    "literature/standard owner bound to its exact cell."
                ),
                evidence={
                    "header_row": binding["header_row"],
                    "value_row": binding["value_row"],
                    "owner_cell": binding["owner_cell"],
                    "value_cell": binding["value_cell"],
                },
                expected={
                    "binding": "one owner column/row, one numeric value cell, one reference marker",
                    "independent_reference_owner": True,
                    "shared_item_role_changed": False,
                },
                actual={
                    "before_owner": before_owner,
                    "after_owner": display,
                    "marker": marker["label"],
                    "marker_kind": marker["kind"],
                    "marker_source": marker["source"],
                    "binding": binding["binding"],
                    "owner_column": binding["owner_column"],
                    "selected_column": binding["selected_column"],
                    "fact": fact.model_dump(),
                },
                suggested_action=(
                    "Review only if the cited cell describes the current study "
                    "rather than an independent comparison source."
                ),
            )
        )
    return anchor_rows, fact_rows, issues


def _prose_reference_author_markers(sentence: str) -> tuple[str, ...]:
    """Return explicit reporting authors without reading the bibliography."""

    if not _REFERENCE_PROSE_REPORTING_VERB.search(sentence):
        return ()
    return tuple(
        dict.fromkeys(
            re.sub(r"\s+", " ", match.group("author")).strip()
            for match in _REFERENCE_PROSE_AUTHOR.finditer(sentence)
        )
    )


def _prose_reference_sentence_bindings(source_text: str) -> list[dict[str, Any]]:
    """Resolve direct and strictly adjacent cited-result discourse chains."""

    bindings: list[dict[str, Any]] = []
    paragraphs = [
        block.strip()
        for block in re.split(r"\n\s*\n+", source_text or "")
        if block.strip() and not block.lstrip().startswith("#")
    ]
    for paragraph_index, paragraph in enumerate(paragraphs):
        if "|" in paragraph and any(
            _markdown_table_cells(row)
            for row in paragraph.splitlines()
        ):
            continue
        sentences = _source_discourse_sentences(paragraph)
        paragraph_bindings: dict[int, dict[str, Any]] = {}
        for sentence_index, sentence in enumerate(sentences):
            chain_type = ""
            chain_sentences: list[str] = []
            author_marker = ""
            direct_markers = _prose_reference_author_markers(sentence)
            if _REFERENCE_PROSE_PRONOUN_CONTINUATION.search(sentence):
                # A later named author does not become the antecedent of a
                # sentence that starts with ``They``.  Let the strict adjacent
                # continuation branch below resolve it, or fail closed.
                direct_markers = ()
            direct_marker_keys = {
                normalize_source_alias(marker)
                for marker in direct_markers
                if normalize_source_alias(marker)
            }
            if len(direct_marker_keys) == 1:
                reporting = _REFERENCE_PROSE_REPORTING_VERB.search(sentence)
                author_position = sentence.casefold().find(
                    direct_markers[0].casefold()
                )
                if (
                    reporting is not None
                    and author_position >= 0
                    and author_position < reporting.start()
                ):
                    author_marker = direct_markers[0]
                    chain_sentences = [sentence]
                    chain_type = "direct_author_attribution"
            if not chain_type:
                citation_markers = [
                    marker
                    for marker in _reference_marker_candidates(sentence)
                    if marker["kind"] in {"author_year", "numeric_citation"}
                ]
                if len(citation_markers) == 1:
                    candidate_marker = citation_markers[0]
                    if (
                        candidate_marker["kind"] != "author_year"
                        or len(_reference_author_keys(candidate_marker["label"]))
                        == 1
                    ):
                        author_marker = candidate_marker["label"]
                        chain_sentences = [sentence]
                        chain_type = (
                            "literal_owner_citation"
                            if candidate_marker["kind"] == "numeric_citation"
                            else "literal_author_year_citation"
                        )

            if not chain_type and sentence_index > 0:
                previous = sentences[sentence_index - 1]
                if _REFERENCE_PROSE_REPORTED_CONTINUATION.search(sentence):
                    markers = _prose_reference_author_markers(previous)
                    chain_sentences = [previous, sentence]
                    if len(markers) == 1:
                        author_marker = markers[0]
                        chain_type = "reported_values_continuation"
                elif _REFERENCE_PROSE_PRONOUN_CONTINUATION.search(sentence):
                    inherited = paragraph_bindings.get(sentence_index - 1)
                    if (
                        inherited is not None
                        and re.search(
                            r"(?i)\bet\s+al\.?$",
                            str(inherited["author_marker"]),
                        )
                        and not _prose_reference_author_markers(sentence)
                    ):
                        chain_sentences = [
                            *inherited["chain_sentences"],
                            sentence,
                        ]
                        author_marker = str(inherited["author_marker"])
                        chain_type = "pronoun_continuation"
                elif _REFERENCE_PROSE_PREVIOUS_WORK.search(previous):
                    marker = _one_reference_marker(("antecedent_sentence", previous))
                    chain_sentences = [previous, sentence]
                    if marker is not None:
                        author_marker = marker["label"]
                        chain_type = "previous_work_continuation"
                elif _REFERENCE_PROSE_SAME_STUDY.search(sentence):
                    inherited = paragraph_bindings.get(sentence_index - 1)
                    if inherited is not None:
                        chain_sentences = [
                            *inherited["chain_sentences"],
                            sentence,
                        ]
                        author_marker = str(inherited["author_marker"])
                        chain_type = "same_study_continuation"

            if not chain_type or not author_marker:
                continue
            if chain_type in {
                "previous_work_continuation",
                "literal_owner_citation",
                "literal_author_year_citation",
            }:
                unique_authors: set[str] = set()
            else:
                unique_authors = {
                    normalize_source_alias(marker)
                    for chain_sentence in chain_sentences
                    for marker in _prose_reference_author_markers(chain_sentence)
                    if normalize_source_alias(marker)
                }
                if unique_authors != {normalize_source_alias(author_marker)}:
                    continue
            chain_text = " ".join(chain_sentences)
            current_study_text = (
                _REFERENCE_PROSE_PREVIOUS_WORK.sub("", chain_text)
                if chain_type == "previous_work_continuation"
                else chain_text
            )
            current_study_guard = bool(
                _REFERENCE_CURRENT_STUDY.search(current_study_text)
            )
            if current_study_guard and chain_type != "literal_author_year_citation":
                continue
            binding = {
                "paragraph_index": paragraph_index,
                "sentence_index": sentence_index,
                "source_paragraph": paragraph,
                "sentence": sentence,
                "antecedent_sentence": chain_sentences[0],
                "chain_sentences": tuple(chain_sentences),
                "chain_type": chain_type,
                "author_marker": author_marker,
                "unique_author_count": (
                    None
                    if chain_type in {
                        "previous_work_continuation",
                        "literal_owner_citation",
                        "literal_author_year_citation",
                    }
                    else len(unique_authors)
                ),
                "current_study_guard": current_study_guard,
            }
            paragraph_bindings[sentence_index] = binding
            bindings.append(binding)
    return bindings


def _prose_reference_fact_binding(
    fact: AxisFact, bindings: Sequence[dict[str, Any]]
) -> dict[str, Any] | None:
    """Locate all fact evidence at one uniquely resolved continuation sentence."""

    if not _numeric_core_tensile_fact(fact):
        return None
    if str(fact.data.get("data_source") or "").strip().casefold() != "text":
        return None
    if _fact_markdown_table_rows(fact):
        return None
    evidence_rows = [str(row).strip() for row in fact.source_evidence if str(row).strip()]
    if not evidence_rows:
        return None

    selected: dict[tuple[int, int], dict[str, Any]] = {}
    for evidence in evidence_rows:
        needle = _normalized_literal(evidence)
        compact_needle = _literal_match_key(evidence)
        if len(needle) < 24 and len(compact_needle) < 12:
            return None
        matches: dict[tuple[int, int], dict[str, Any]] = {}
        for binding in bindings:
            sentence = str(binding["sentence"])
            normalized_sentence = _normalized_literal(sentence)
            compact_sentence = _literal_match_key(sentence)
            literal_match = needle == normalized_sentence or needle in normalized_sentence
            compact_match = (
                len(compact_needle) >= 12
                and (
                    compact_needle == compact_sentence
                    or compact_needle in compact_sentence
                )
            )
            if literal_match or compact_match:
                key = (
                    int(binding["paragraph_index"]),
                    int(binding["sentence_index"]),
                )
                matches[key] = binding
        if len(matches) != 1:
            return None
        if len(needle) < 24 and any(
            match["chain_type"] != "literal_author_year_citation"
            for match in matches.values()
        ):
            return None
        selected.update(matches)
    if len(selected) != 1:
        return None
    binding = next(iter(selected.values()))
    if binding["chain_type"] == "literal_owner_citation":
        sentence = str(binding["sentence"])
        owner = str(fact.sample_id_raw or "").strip()
        marker = str(binding["author_marker"])
        owner_matches = list(
            re.finditer(
                rf"(?i)(?<![A-Za-z0-9]){re.escape(owner)}(?![A-Za-z0-9])",
                sentence,
            )
        )
        if len(owner_matches) != 1:
            return None
        tail = sentence[owner_matches[0].end() : owner_matches[0].end() + 24]
        if not re.match(rf"\s*{re.escape(marker)}", tail):
            return None
    if binding["chain_type"] == "previous_work_continuation":
        raw_note = str(fact.data.get("raw_note") or "")
        if not _REFERENCE_PROSE_PREVIOUS_WORK.search(raw_note):
            return None
        note_markers = _reference_marker_candidates(raw_note)
        if {
            normalize_source_alias(marker["label"])
            for marker in note_markers
            if normalize_source_alias(marker["label"])
        } != {normalize_source_alias(binding["author_marker"])}:
            return None
    return binding


def _reference_fact_context_cleanup(
    fact: AxisFact, binding: Mapping[str, Any]
) -> tuple[AxisFact, dict[str, Any]]:
    """Remove current-paper Property context absent from the cited sentence chain."""

    if not isinstance(fact, PropertyFact):
        return fact, {}
    source = normalize_source_alias(
        " ".join(
            [
                *(str(row) for row in binding.get("chain_sentences", ())),
                *(str(row) for row in fact.source_evidence),
            ]
        )
    )
    data = dict(fact.data)
    cleared: dict[str, Any] = {}
    for key in ("test_condition_raw", "test_specimen_raw"):
        value = str(data.get(key) or "").strip()
        value_key = normalize_source_alias(value)
        if value and value_key and value_key not in source:
            cleared[key] = value
            data[key] = ""
    if not cleared:
        return fact, {}
    return fact.model_copy(update={"data": data}), cleared


def _prose_reference_parent_signature(
    anchor: InventoryAnchor,
) -> tuple[str, str, str, str]:
    role = str(anchor.role or "").strip().casefold()
    # Target anchors with one source label are often duplicated by the
    # deterministic table planner; cited Reference anchors may intentionally
    # reuse an author label for different materials (for example LPBF and EPBF
    # rows under ``Amato et al.``), so retain their material discriminator.
    identity = (
        _identity_key(anchor.sample_id_raw)
        if role == "target"
        else _identity_key(anchor.material_name_raw) or _identity_key(anchor.sample_id_raw)
    )
    return (
        # The same source item can arrive twice: once from the inventory task
        # with a material name and once from a deterministic table anchor with
        # only ``sample_id_raw``.  Those are two representations of one
        # parent, not two independent literature candidates.  Treating the
        # material-name difference as identity made citation continuations
        # (``previous work [22]. ... 1.34 GPa``) remain attached to the target
        # whenever both anchor representations were present.  The sample label
        # is the source identity here; material/state/role/nature still keep
        # genuinely different parent coordinates separate.
        identity,
        _normalized_literal(anchor.state_raw),
        role,
        str(anchor.data_nature or "").strip().casefold(),
    )


def _prose_reference_material_tokens(value: Any) -> set[str]:
    tokens = set(re.findall(r"[a-z0-9]+", _normalized_literal(value)))
    return tokens - {
        "alloy",
        "fabricated",
        "material",
        "printed",
        "processed",
        "sample",
        "samples",
        "specimen",
        "specimens",
    }


def _select_prose_reference_parent(
    parents: Sequence[InventoryAnchor],
    fact: AxisFact,
    binding: dict[str, Any],
) -> tuple[InventoryAnchor, str] | None:
    """Choose one same-author literature sample using only local source text."""

    unique: dict[tuple[str, str, str, str], InventoryAnchor] = {}
    for parent in parents:
        signature = _prose_reference_parent_signature(parent)
        previous = unique.get(signature)
        if previous is None or parent.confidence > previous.confidence:
            unique[signature] = parent
    candidates = list(unique.values())
    if len(candidates) == 1:
        return candidates[0], "single_owner_anchor"

    fact_evidence = {
        _normalized_literal(row)
        for row in fact.source_evidence
        if _normalized_literal(row)
    }
    exact_evidence = [
        parent
        for parent in candidates
        if fact_evidence
        and any(
            _normalized_literal(row) in fact_evidence
            for row in parent.source_evidence
            if _normalized_literal(row)
        )
    ]
    if len(exact_evidence) == 1:
        return exact_evidence[0], "exact_anchor_evidence"

    token_sets = [
        _prose_reference_material_tokens(parent.material_name_raw)
        for parent in candidates
    ]
    if not token_sets or any(not tokens for tokens in token_sets):
        return None
    shared = set.intersection(*token_sets)
    sentence_tokens = _prose_reference_material_tokens(binding["sentence"])
    ranked = [
        (len((tokens - shared) & sentence_tokens), parent)
        for parent, tokens in zip(candidates, token_sets)
    ]
    best_score = max((score for score, _ in ranked), default=0)
    winners = [parent for score, parent in ranked if score == best_score]
    if best_score <= 0 or len(winners) != 1:
        return None
    return winners[0], "unique_material_discriminator"


def _recover_prose_citation_tensile_reference_owners(
    anchors: Sequence[InventoryAnchor],
    facts: Sequence[AxisFact],
    source_text: str,
) -> tuple[list[InventoryAnchor], list[AxisFact], list[MaterializeIssue]]:
    """Split uniquely resolved cited-prose tensile continuations as Reference."""

    anchor_rows = list(anchors)
    fact_rows = list(facts)
    bindings = _prose_reference_sentence_bindings(source_text)
    if not bindings:
        return anchor_rows, fact_rows, []

    exact_anchors: dict[str, list[InventoryAnchor]] = {}
    for anchor in anchor_rows:
        exact_anchors.setdefault(_identity_key(anchor.sample_id_raw), []).append(anchor)
    reference_anchors: dict[str, InventoryAnchor] = {
        _identity_key(anchor.sample_id_raw): anchor
        for anchor in anchor_rows
        if anchor.role == "Reference"
        and str(anchor.data_nature or "").startswith("Literature_")
    }

    issues: list[MaterializeIssue] = []
    for index, fact in enumerate(fact_rows):
        binding = _prose_reference_fact_binding(fact, bindings)
        if binding is None:
            continue
        before_owner = str(fact.sample_id_raw or "").strip()
        if re.search(r"(?i)\[reference\]\s*$", before_owner):
            continue
        owner_key = _identity_key(before_owner)
        parents = exact_anchors.get(owner_key, [])
        parent_roles = {
            str(parent.role or "").strip().casefold()
            for parent in parents
            if str(parent.role or "").strip()
        }
        if not parents or parent_roles not in ({"target"}, {"reference"}):
            continue
        if binding["current_study_guard"] and parent_roles != {"reference"}:
            # A source phrase such as ``reported as strain by this study`` is
            # ambiguous in isolation. It is usable only when the fact already
            # points at the exact existing Reference identity carrying the
            # same author-year marker; it may never reclassify a Target.
            continue
        if parent_roles == {"reference"}:
            reference_parents = [
                parent
                for parent in parents
                if _reference_anchor_matches_binding(parent, binding)
            ]
        else:
            reference_parents = [
                parent
                for parent in reference_anchors.values()
                if _reference_anchor_matches_binding(parent, binding)
            ]
        if not reference_parents:
            continue
        selected_parent = _select_prose_reference_parent(
            reference_parents, fact, binding
        )
        if selected_parent is None:
            continue
        parent, parent_selection_rule = selected_parent
        author_marker = str(binding["author_marker"])
        display_base = _reference_parent_display_base(parent, author_marker)
        display = _reference_tensile_display(display_base or before_owner, author_marker)
        display_key = _identity_key(display)
        if not display_key or not is_plausible_material_identity(display):
            continue

        material_name = str(parent.material_name_raw or before_owner).strip()
        anchor_evidence = list(
            dict.fromkeys(
                [
                    *(str(row) for row in binding["chain_sentences"]),
                    *parent.source_evidence,
                    *fact.source_evidence,
                ]
            )
        )
        if display_key not in reference_anchors:
            reference_anchor = InventoryAnchor(
                sample_id_raw=display,
                material_name_raw=material_name,
                state_raw=parent.state_raw,
                role="Reference",
                data_nature="Literature_Experimental",
                source_evidence=anchor_evidence,
                confidence=fact.confidence,
            )
            anchor_rows.append(reference_anchor)
            exact_anchors.setdefault(display_key, []).append(reference_anchor)
            reference_anchors[display_key] = reference_anchor

        routed_fact = fact.model_copy(update={"sample_id_raw": display})
        routed_fact, cleared_context = _reference_fact_context_cleanup(
            routed_fact, binding
        )
        fact_rows[index] = routed_fact
        issue_code = {
            "direct_author_attribution": (
                "reference_tensile_direct_author_owner_recovered"
            ),
            "pronoun_continuation": (
                "reference_tensile_pronoun_continuation_owner_recovered"
            ),
            "literal_owner_citation": (
                "reference_tensile_literal_citation_owner_recovered"
            ),
            "literal_author_year_citation": (
                "reference_tensile_literal_citation_owner_recovered"
            ),
        }.get(
            str(binding["chain_type"]),
            "reference_tensile_prose_owner_recovered",
        )
        issues.append(
            MaterializeIssue(
                code=issue_code,
                sample_id_raw=display,
                path=f"items.{display}.Extracted_Data.Properties",
                message=(
                    "A numeric core-tensile prose fact was moved to the unique "
                    "literature owner resolved by an adjacent citation continuation."
                ),
                evidence={
                    "antecedent_sentence": binding["antecedent_sentence"],
                    "continuation_sentence": binding["sentence"],
                    "chain_sentences": list(binding["chain_sentences"]),
                },
                expected={
                    "binding": "one adjacent author-attributed continuation chain",
                    "unique_source_paragraph": True,
                    "unique_source_sentence": True,
                    "unique_author_count": binding["unique_author_count"],
                    "unique_reference_marker_count": (
                        1
                        if binding["chain_type"] == "previous_work_continuation"
                        else None
                    ),
                    "current_study_guard": binding["current_study_guard"],
                    "unique_parent_anchor": True,
                    "existing_reference_anchor": True,
                    "fact_level_split": True,
                },
                actual={
                    "before_owner": before_owner,
                    "after_owner": display,
                    "author_marker": author_marker,
                    "chain_type": binding["chain_type"],
                    "antecedent_sentence": binding["antecedent_sentence"],
                    "continuation_sentence": binding["sentence"],
                    "chain_sentences": list(binding["chain_sentences"]),
                    "source_paragraph": binding["source_paragraph"],
                    "paragraph_index": binding["paragraph_index"],
                    "sentence_index": binding["sentence_index"],
                    "unique_author_count": binding["unique_author_count"],
                    "current_study_guard": binding["current_study_guard"],
                    "before_owner_role": next(iter(parent_roles)),
                    "selected_parent": parent.model_dump(),
                    "parent_selection_rule": parent_selection_rule,
                    "fact": fact.model_dump(),
                    "routed_fact": routed_fact.model_dump(),
                    "cleared_unproven_context": cleared_context,
                },
                suggested_action=(
                    "Review only if the adjacent author attribution does not "
                    "govern this reported-values continuation."
                ),
            )
        )
    return anchor_rows, fact_rows, issues


def _source_label_occurs_in_row(label: str, row: str) -> bool:
    """Match one source identity as a token, including short upper-case codes."""

    presentation = unicodedata.normalize("NFKC", str(label or "")).strip()
    if not presentation or _is_element_symbol(presentation):
        return False
    if re.fullmatch(r"[A-Z]{2,6}", presentation):
        pattern = re.compile(
            rf"(?<![A-Za-z0-9]){re.escape(presentation)}(?![A-Za-z0-9])"
        )
    else:
        pattern = re.compile(
            rf"(?i)(?<![A-Za-z0-9]){re.escape(presentation)}(?![A-Za-z0-9])"
        )
    normalized_row = unicodedata.normalize("NFKC", row)
    if pattern.search(normalized_row):
        return True

    # Source OCR/Markdown frequently writes a formula owner with TeX braces
    # (``Al_{0}.6``) while the inventory anchor uses the compact form
    # (``Al0.6``).  Presentation normalization already makes those strings
    # identical, but the literal regex above intentionally does not.  Permit
    # normalized containment only for identity-like labels (a digit or a
    # sufficiently specific multi-token label) so a short owner such as
    # ``CoCrNi`` cannot spuriously match ``CoCrNiAl...``.
    owner_key = normalize_source_alias(presentation)
    row_key = normalize_source_alias(normalized_row)
    if not owner_key or owner_key not in row_key:
        return False
    has_tex_presentation = bool(re.search(r"(?:\\|\$_|\^|\{[^{}]*\})", normalized_row))
    if has_tex_presentation and re.search(r"[A-Za-z]", presentation) and re.search(
        r"\d", presentation
    ):
        return True
    return False


def _row_material_family_candidates(
    index: _IdentityIndex, row: str
) -> dict[str, list[str]]:
    """Return source-named material families in one complete table row."""

    candidates: dict[str, list[str]] = {}
    for canonical in index.anchors:
        base = index.state_family_base.get(canonical, canonical)
        if canonical != base:
            continue
        presentations = {
            index.display_label(canonical),
            *(
                str(anchor.sample_id_raw or "").strip()
                for anchor in index.anchors.get(canonical, [])
            ),
        }
        matched = sorted(
            {
                label
                for label in presentations
                if label and _source_label_occurs_in_row(label, row)
            },
            key=lambda value: (len(value), value.casefold()),
        )
        if matched:
            candidates.setdefault(base, []).extend(matched)
    return {
        base: list(dict.fromkeys(labels))
        for base, labels in candidates.items()
    }


def _unique_row_state_member(
    index: _IdentityIndex,
    base: str,
    row: str,
    *,
    allow_terminal_preparation: bool = False,
) -> str | None:
    """Return or register the only source state named for one material family."""

    compatible = {
        target
        for target in index.resolve_state_evidence([row])
        if index.state_family_base.get(target, target) == base
        and target != base
    }
    if allow_terminal_preparation:
        for (category, qualifiers), targets in index.state_descriptor_targets.items():
            if qualifiers:
                continue
            category_pattern = next(
                (
                    pattern
                    for candidate, pattern in _STATE_CATEGORY_PATTERNS
                    if candidate == category
                ),
                None,
            )
            if category_pattern is None or not category_pattern.search(row):
                continue
            compatible.update(
                target
                for target in targets
                if index.state_family_base.get(target, target) == base
                and target != base
            )
    if len(compatible) == 1:
        return next(iter(compatible))
    if compatible:
        if not allow_terminal_preparation:
            return None
        ranked: list[tuple[int, str]] = []
        for target in compatible:
            positions: list[int] = []
            for anchor in index.anchors.get(target, []):
                descriptor = _state_descriptor(anchor.state_raw)
                if descriptor is None:
                    continue
                category = descriptor[0]
                pattern = next(
                    (
                        candidate_pattern
                        for candidate, candidate_pattern in _STATE_CATEGORY_PATTERNS
                        if candidate == category
                    ),
                    None,
                )
                if pattern is not None:
                    positions.extend(match.start() for match in pattern.finditer(row))
            if positions:
                ranked.append((max(positions), target))
        if ranked:
            best_position = max(position for position, _ in ranked)
            best = {target for position, target in ranked if position == best_position}
            if len(best) == 1:
                return next(iter(best))
        return None

    normalized_row = normalize_source_alias(row)
    state_anchors: dict[tuple[str, tuple[str, tuple[str, ...]]], InventoryAnchor] = {}
    for anchor in index.anchors.get(base, []):
        state = str(anchor.state_raw or "").strip()
        descriptor = _state_descriptor(state)
        state_key = normalize_source_alias(state)
        if not state_key or descriptor is None or state_key not in normalized_row:
            continue
        state_anchors.setdefault((state, descriptor), anchor)
    if len(state_anchors) != 1:
        return None

    (state, _), anchor = next(iter(state_anchors.items()))
    display = f"{index.display_label(base)} [{state}]"
    canonical = _identity_key(display)
    if canonical not in index.anchors:
        qualified_anchor = anchor.model_copy(update={"sample_id_raw": display})
        index.add_anchor_as(qualified_anchor, canonical)
        if canonical not in index.anchors:
            # A source state can itself contain a conjunction (for example
            # ``solution annealed and double aged``). The public identity
            # plausibility gate correctly rejects arbitrary combined labels,
            # but this generated bracket form is already constrained to one
            # proven base owner and one literal state, so register it directly.
            index.labels.setdefault(canonical, Counter())[display] += 1
            index.anchors.setdefault(canonical, []).append(qualified_anchor)
        index.add_state_alias(state, canonical)
        index.add_state_family(canonical, base)
    return canonical


def _recover_numeric_tensile_table_row_owners(
    index: _IdentityIndex,
    facts: Sequence[AxisFact],
) -> tuple[list[AxisFact], list[MaterializeIssue]]:
    """Recover a numeric tensile owner from one complete, unambiguous table row."""

    recovered: list[AxisFact] = []
    issues: list[MaterializeIssue] = []
    for fact in facts:
        if not isinstance(fact, PropertyFact):
            recovered.append(fact)
            continue
        data = fact.data
        if (
            not is_core_tensile_property_name(data.get("property_name_raw"))
            or not re.search(r"\d", str(data.get("value_raw") or ""))
            or str(data.get("data_source") or "").strip().casefold() != "table"
            or _group_route(index, fact)
        ):
            recovered.append(fact)
            continue
        combined_evidence = "\n".join(str(row) for row in fact.source_evidence)
        if _REPORTED_RESULT_BLOCKER.search(
            "\n".join(
                [
                    combined_evidence,
                    str(data.get("test_method_raw") or ""),
                    str(data.get("test_standard_raw") or ""),
                ]
            )
        ):
            recovered.append(fact)
            continue

        decisions: list[dict[str, Any]] = []
        for row in _complete_markdown_table_rows(fact):
            family_candidates = _row_material_family_candidates(index, row)
            if len(family_candidates) != 1:
                decisions.append(
                    {
                        "row": row,
                        "family_candidates": {
                            index.display_label(base): labels
                            for base, labels in family_candidates.items()
                        },
                        "selected": None,
                        "reason": "owner_family_not_unique",
                    }
                )
                continue
            base = next(iter(family_candidates))
            selected = _unique_row_state_member(index, base, row)
            if selected is None:
                state_candidates = {
                    target
                    for target in index.resolve_state_evidence([row])
                    if index.state_family_base.get(target, target) == base
                }
                decisions.append(
                    {
                        "row": row,
                        "family_candidates": {
                            index.display_label(base): family_candidates[base]
                        },
                        "state_candidates": [
                            index.display_label(target)
                            for target in sorted(state_candidates)
                        ],
                        "selected": None,
                        "reason": "owner_state_not_unique",
                    }
                )
                continue
            decisions.append(
                {
                    "row": row,
                    "family_candidates": {
                        index.display_label(base): family_candidates[base]
                    },
                    "state_candidates": [index.display_label(selected)],
                    "selected": selected,
                    "reason": "complete_table_row_owner_state",
                }
            )

        selected_decisions = [row for row in decisions if row.get("selected")]
        selected_targets = {row["selected"] for row in selected_decisions}
        if len(selected_targets) != 1:
            recovered.append(fact)
            continue
        selected = next(iter(selected_targets))
        selected_rows = [
            row for row in selected_decisions if row["selected"] == selected
        ]
        before = fact.model_dump()
        after_owner = index.display_label(selected)
        cleaned = fact.model_copy(update={"sample_id_raw": after_owner})
        recovered.append(cleaned)
        issues.append(
            MaterializeIssue(
                code="numeric_tensile_owner_recovered",
                sample_id_raw=after_owner,
                path=f"items.{after_owner}.Extracted_Data.Properties",
                message=(
                    "A numeric core-tensile result was assigned to the only "
                    "material/state owner explicitly named by its complete table row."
                ),
                evidence={
                    "table_rows": [row["row"] for row in selected_rows],
                    "decisions": decisions,
                },
                expected={
                    "owner": "one source-named material family and one compatible state",
                    "rule": "complete_table_row_owner_state",
                },
                actual={
                    "before_owner": fact.sample_id_raw,
                    "after_owner": after_owner,
                    "rule": "complete_table_row_owner_state",
                    "candidate_owner_states": [
                        index.display_label(target) for target in sorted(selected_targets)
                    ],
                    "fact": before,
                },
                suggested_action=(
                    "Review only if the projected row combines more than one source "
                    "sample or preparation state."
                ),
            )
        )
    return recovered, issues


def _core_tensile_semantic(fact: AxisFact) -> str:
    if not isinstance(fact, PropertyFact):
        return ""
    name = normalize_source_alias(fact.data.get("property_name_raw"))
    symbol_name = re.sub(r"(?:mpa|gpa|percent)$", "", name)
    if any(
        token in name
        for token in (
            "retention",
            "relative",
            "ratio",
            "delta",
            "difference",
            "change",
            "increase",
            "decrease",
            "increment",
            "decrement",
            "improvement",
            "enhancement",
            "contribution",
            "reduction",
        )
    ):
        return ""
    if name in {"el", "te", "eab"} or any(
        token in name for token in ("elongation", "ductility")
    ):
        return "elongation"
    if (
        "yieldstrength" in name
        or "yieldstress" in name
        or symbol_name in {"ys", "avgys", "averageys"}
    ):
        return "yield_strength"
    if (
        "ultimatetensilestrength" in name
        or "ultimatetensilestress" in name
        or "tensilestrength" in name
        or symbol_name in {"uts", "avguts", "averageuts"}
    ):
        return "ultimate_tensile_strength"
    return ""


def _numeric_core_tensile_fact(fact: AxisFact) -> bool:
    return bool(
        isinstance(fact, PropertyFact)
        and _core_tensile_semantic(fact)
        and re.search(r"\d", str(fact.data.get("value_raw") or ""))
    )


_TENSILE_LITERAL_NUMBER = r"[-+]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?"
_TENSILE_LITERAL_UNIT_EXPRESSION = re.compile(
    rf"(?ix)^\s*"
    rf"(?P<central>{_TENSILE_LITERAL_NUMBER})\s*"
    rf"(?P<unit1>MPa|GPa|%|percent)?\s*"
    rf"(?:\s*(?:±|\+/-|plus\s*/?\s*minus)\s*"
    rf"(?P<uncertainty>{_TENSILE_LITERAL_NUMBER})\s*"
    rf"(?P<unit2>MPa|GPa|%|percent)?\s*)?$"
)
_TENSILE_EXTERNAL_COMPARATOR_RELATION = re.compile(
    r"(?ix)(?:"
    r"\b(?:comparable|similar)\s+to\s+(?:those|that)\s+of\b|"
    r"\b(?:compared|relative)\s+(?:to|with|against)\b|"
    r"\b(?:higher|lower|greater|less)\s+than\b"
    r")"
)
_TENSILE_EXTERNAL_COMPARATOR_MATERIAL = re.compile(
    r"(?ix)\b(?:"
    r"alloys?|materials?|samples?|specimens?|parts?|rods?|walls?|"
    r"conditions?|states?|cast|wrought|forged|rolled|conventional(?:ly)?|"
    r"literature|reference"
    r")\b"
)


def _numeric_tensile_external_comparator_scope(
    fact: AxisFact,
) -> dict[str, str] | None:
    """Return one value-local comparator binding for an unresolved fact.

    This is a materialization backstop. Promotion normally isolates these
    records first, but a generic plural Reference anchor can be visible during
    promotion and later fail the public material-identity contract. Without a
    backstop, the current-study protocol fallback can then reassign the orphaned
    comparator value to the Target.
    """

    if not _numeric_core_tensile_fact(fact):
        return None

    def number_matches(value: Any) -> tuple[str, tuple[re.Match[str], ...]]:
        normalized = unicodedata.normalize(
            "NFKC", str(value or "")
        ).casefold()
        normalized = re.sub(r"(?<=\d)[-–—~](?=\d)", " ", normalized)
        return normalized, tuple(
            re.finditer(
                rf"(?<![a-z0-9]){_TENSILE_LITERAL_NUMBER}",
                normalized,
            )
        )

    _, expected_matches = number_matches(fact.data.get("value_raw"))
    expected = tuple(match.group(0).lstrip("+") for match in expected_matches)
    if not expected:
        return None
    decisions: list[dict[str, str]] = []
    for evidence_row in fact.source_evidence:
        normalized, matches = number_matches(evidence_row)
        tokens = tuple(match.group(0).lstrip("+") for match in matches)
        width = len(expected)
        starts = [
            matches[index].start()
            for index in range(0, len(tokens) - width + 1)
            if tokens[index : index + width] == expected
        ]
        if len(starts) != 1:
            continue
        value_start = starts[0]
        cues = [
            match
            for match in _TENSILE_EXTERNAL_COMPARATOR_RELATION.finditer(
                normalized
            )
            if match.end() <= value_start
        ]
        if not cues:
            continue
        cue = cues[-1]
        subject = normalized[cue.end() : value_start].strip(" \t(:;,-")
        if not _TENSILE_EXTERNAL_COMPARATOR_MATERIAL.search(subject):
            continue
        decisions.append(
            {
                "value_local_evidence": str(evidence_row).strip(),
                "comparator_cue": cue.group(0),
                "comparator_subject": subject,
            }
        )
    unique = {
        (
            row["value_local_evidence"],
            row["comparator_cue"],
            row["comparator_subject"],
        ): row
        for row in decisions
    }
    return next(iter(unique.values())) if len(unique) == 1 else None


def _literal_tensile_unit(fact: AxisFact) -> str | None:
    """Recover only a unit written inside one complete numeric value literal."""

    if not isinstance(fact, PropertyFact):
        return None
    existing = str(fact.data.get("unit_raw") or "").strip()
    if existing and not _is_unresolved_alias(existing):
        return None
    semantic = _core_tensile_semantic(fact)
    if semantic not in {"yield_strength", "ultimate_tensile_strength", "elongation"}:
        return None
    value = unicodedata.normalize(
        "NFKC", str(fact.data.get("value_raw") or "")
    ).strip()
    value = value.replace(r"\%", "%").replace(r"\pm", "±").replace("$", "")
    value = re.sub(r"\\[,;:! ]", " ", value)
    match = _TENSILE_LITERAL_UNIT_EXPRESSION.fullmatch(value)
    if match is None:
        return None

    def canonical(raw: str | None) -> str | None:
        key = str(raw or "").strip().casefold()
        if key in {"%", "percent"}:
            return "%"
        if key == "mpa":
            return "MPa"
        if key == "gpa":
            return "GPa"
        return None

    units = {
        unit
        for raw in (match.group("unit1"), match.group("unit2"))
        if (unit := canonical(raw)) is not None
    }
    if len(units) != 1:
        return None
    unit = next(iter(units))
    if semantic == "elongation":
        return unit if unit == "%" else None
    return unit if unit in {"MPa", "GPa"} else None


def _recover_literal_tensile_units(
    facts: Sequence[AxisFact],
) -> tuple[list[AxisFact], list[MaterializeIssue]]:
    """Fill an empty tensile unit only when ``value_raw`` states it verbatim."""

    recovered: list[AxisFact] = []
    issues: list[MaterializeIssue] = []
    for fact in facts:
        unit = _literal_tensile_unit(fact)
        if unit is None:
            recovered.append(fact)
            continue
        before = fact.model_dump()
        updated = fact.model_copy(
            update={"data": {**fact.data, "unit_raw": unit}}
        )
        recovered.append(updated)
        issues.append(
            MaterializeIssue(
                code="literal_tensile_unit_recovered",
                sample_id_raw=fact.sample_id_raw,
                path=f"items.{fact.sample_id_raw}.Extracted_Data.Properties",
                message=(
                    "A missing core-tensile unit was recovered from the exact "
                    "numeric value literal."
                ),
                evidence=list(fact.source_evidence),
                expected={
                    "rule": "unit_literal_inside_complete_numeric_expression",
                    "semantic": _core_tensile_semantic(fact),
                    "overwrite_existing_unit": False,
                },
                actual={
                    "value_raw": fact.data.get("value_raw"),
                    "recovered_unit": unit,
                    "before": before,
                    "after": updated.model_dump(),
                },
                suggested_action=(
                    "Review only if the unit token belongs to a different "
                    "quantity than the reported tensile value."
                ),
            )
        )
    return recovered, issues


def _fact_is_blocked_tensile_result(fact: AxisFact) -> bool:
    if not isinstance(fact, PropertyFact):
        return True
    return bool(
        _REPORTED_RESULT_BLOCKER.search(
            "\n".join(
                [
                    *(str(row) for row in fact.source_evidence),
                    str(fact.data.get("test_method_raw") or ""),
                    str(fact.data.get("test_standard_raw") or ""),
                ]
            )
        )
    )


def _normalized_literal(value: Any) -> str:
    text = unicodedata.normalize("NFKC", str(value or "")).casefold()
    return " ".join(text.split())


def _literal_match_key(value: Any) -> str:
    """Fold harmless OCR/LaTeX presentation differences for quote location."""

    text = unicodedata.normalize("NFKC", str(value or ""))
    text = re.sub(r"\\(?:pm|times|cdot)\b", " ", text, flags=re.IGNORECASE)
    text = text.replace("±", " ").replace("×", " ").replace("·", " ")
    return normalize_source_alias(text)


def _facts_share_evidence_bundle(left: AxisFact, right: AxisFact) -> bool:
    if (
        left.evidence_unit_id
        and right.evidence_unit_id
        and left.evidence_unit_id == right.evidence_unit_id
    ):
        return True
    left_rows = [_normalized_literal(row) for row in left.source_evidence]
    right_rows = [_normalized_literal(row) for row in right.source_evidence]
    for left_row in left_rows:
        if len(left_row) < 24:
            continue
        for right_row in right_rows:
            if len(right_row) < 24:
                continue
            if left_row == right_row or left_row in right_row or right_row in left_row:
                return True
    return False


def _owner_roles(index: _IdentityIndex, canonical: str) -> set[str]:
    base = index.state_family_base.get(canonical, canonical)
    rows = [
        *index.anchors.get(canonical, []),
        *([] if base == canonical else index.anchors.get(base, [])),
    ]
    return {
        str(anchor.role or "").strip().casefold()
        for anchor in rows
        if str(anchor.role or "").strip()
    }


def _source_context_blocks_before_evidence(
    source_text: str, fact: AxisFact
) -> list[list[str]]:
    """Return minimal source blocks ending at a copied fact quote.

    Only preceding paragraphs in the same section are included. This lets a
    material/preparation paragraph support the immediately following tensile
    result without borrowing a later fatigue or creep protocol.
    """

    blocks = [
        block.strip()
        for block in re.split(r"\n\s*\n+", source_text or "")
        if block.strip()
    ]
    contexts: list[list[str]] = []
    for evidence in fact.source_evidence:
        needle = _normalized_literal(evidence)
        if len(needle) < 24:
            continue
        for index, block in enumerate(blocks):
            compact_needle = _literal_match_key(evidence)
            if (
                needle not in _normalized_literal(block)
                and (
                    len(compact_needle) < 16
                    or compact_needle not in _literal_match_key(block)
                )
            ):
                continue
            selected = [block]
            cursor = index - 1
            while cursor >= 0 and len(selected) < 3:
                previous = blocks[cursor]
                if re.match(r"^#{1,6}\s+", previous):
                    break
                selected.insert(0, previous)
                cursor -= 1
            if selected not in contexts:
                contexts.append(selected)
    return contexts


def _source_named_material_families(
    index: _IdentityIndex, text: str
) -> dict[str, list[str]]:
    resolved = index.resolve_evidence([text])
    candidates: dict[str, list[str]] = {}
    for target in resolved:
        base = index.state_family_base.get(target, target)
        candidates.setdefault(base, []).append(index.display_label(target))
    if not candidates:
        candidates = _row_material_family_candidates(index, text)
    return {
        base: list(dict.fromkeys(labels))
        for base, labels in candidates.items()
    }


def _property_assertion_occurs_in_text(fact: AxisFact, text: str) -> bool:
    semantic = _core_tensile_semantic(fact)
    if not semantic or not isinstance(fact, PropertyFact):
        return False
    cues = {
        "yield_strength": re.compile(r"(?i)\byield\s+(?:strength|stress)|\bYS\b"),
        "ultimate_tensile_strength": re.compile(
            r"(?i)\b(?:ultimate\s+)?tensile\s+strength|\bUTS\b"
        ),
        "elongation": re.compile(r"(?i)\belongation|\bductility\b"),
    }
    if not cues[semantic].search(text):
        return False
    value_numbers = re.findall(
        r"(?<![A-Za-z0-9])[-+]?\d+(?:\.\d+)?",
        unicodedata.normalize("NFKC", str(fact.data.get("value_raw") or "")),
    )
    text_numbers = set(
        re.findall(
            r"(?<![A-Za-z0-9])[-+]?\d+(?:\.\d+)?",
            unicodedata.normalize("NFKC", text),
        )
    )
    return bool(value_numbers) and all(number in text_numbers for number in value_numbers)


def _facts_share_source_assertion_block(
    source_text: str, unresolved: AxisFact, sibling: AxisFact
) -> tuple[bool, list[str]]:
    for blocks in _source_context_blocks_before_evidence(source_text, unresolved):
        context = "\n\n".join(blocks)
        if _property_assertion_occurs_in_text(unresolved, context) and (
            _property_assertion_occurs_in_text(sibling, context)
        ):
            return True, blocks
    return False, []


def _unique_static_tensile_owner_context(
    index: _IdentityIndex, source_text: str
) -> tuple[str, list[str], dict[str, list[str]]] | None:
    """Return the only Target material/state named by a static tensile protocol."""

    blocks = [
        block.strip()
        for block in re.split(r"\n\s*\n+", source_text or "")
        if block.strip()
    ]
    decisions: list[tuple[str, list[str], dict[str, list[str]]]] = []
    for position, block in enumerate(blocks):
        if not re.search(r"(?i)\btensile\b", block):
            continue
        if not re.search(
            r"(?i)\b(?:quasi[\s-]*static|strain\s+rate|room\s+temperature|"
            r"standard\s+tensile\s+specimens?|tensile\s+properties)\b",
            block,
        ):
            continue
        if re.search(r"(?i)\bultrasonic\s+fatigue|\bfatigue\s+strength\b", block):
            continue
        context_blocks = [block]
        if position > 0 and not re.match(r"^#{1,6}\s+", blocks[position - 1]):
            context_blocks.insert(0, blocks[position - 1])
        context = "\n\n".join(context_blocks)
        families = {
            base: labels
            for base, labels in _source_named_material_families(index, context).items()
            if _owner_roles(index, base) == {"target"}
        }
        if len(families) != 1:
            continue
        base = next(iter(families))
        selected = _unique_row_state_member(
            index,
            base,
            context,
            allow_terminal_preparation=True,
        )
        if selected is not None:
            decisions.append((selected, context_blocks, families))
    selected_targets = {selected for selected, _, _ in decisions}
    if len(selected_targets) != 1:
        return None
    selected = next(iter(selected_targets))
    matching = [row for row in decisions if row[0] == selected]
    shortest = min(matching, key=lambda row: sum(len(block) for block in row[1]))
    return shortest


def _core_tensile_value_key(fact: AxisFact) -> tuple[str, tuple[str, ...], str]:
    if not isinstance(fact, PropertyFact):
        return "", (), ""
    numbers = tuple(
        re.findall(
            r"(?<![A-Za-z0-9])[-+]?\d+(?:\.\d+)?",
            unicodedata.normalize("NFKC", str(fact.data.get("value_raw") or "")),
        )
    )
    unit = normalize_source_alias(fact.data.get("unit_raw"))
    return _core_tensile_semantic(fact), numbers, unit


_TENSILE_PRECISION_RANGE = re.compile(
    r"(?<![A-Za-z0-9])[-+]?(?:\d+(?:\.\d*)?|\.\d+)\s*(?:–|—|-|to)\s*"
    r"[-+]?(?:\d+(?:\.\d*)?|\.\d+)(?![A-Za-z0-9])",
    re.IGNORECASE,
)
_TENSILE_PRECISION_RELATIVE = re.compile(
    r"(?i)(?:%\s*(?:increase|decrease|change|up|down)|"
    r"(?:increase|decrease|change|improv(?:e|ed|ement)|reduc(?:e|ed|tion))\s+by|"
    r"\b(?:higher|lower|greater|less)\b)"
)
_TENSILE_PRECISION_APPROXIMATE = re.compile(
    r"(?i)(?:[~≈]|\b(?:approximately|approx\.?|about|around|roughly)\b)"
)
_TENSILE_PRECISION_BOUND_QUALIFIER = re.compile(
    r"(?i)\b(?:at least|at most|more than|less than|greater than|up to|"
    r"minimum|maximum|threshold|required|required\s+by)\b"
)


def _tensile_precision_numbers(value: Any) -> tuple[str, ...]:
    """Return literal numeric tokens without interpreting prose qualifiers."""

    text = unicodedata.normalize("NFKC", str(value or ""))
    text = re.sub(r"\\(?:pm|times|cdot)\b", " ", text, flags=re.IGNORECASE)
    return tuple(
        re.findall(
            r"(?<![A-Za-z0-9])[-+]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?",
            text.replace("−", "-").replace("–", "-").replace("—", "-"),
        )
    )


def _tensile_precision_number_decimal_places(value: Any) -> int:
    raw = str(value or "").lstrip("+-")
    if not raw:
        return -1
    mantissa = re.split(r"[eE]", raw, maxsplit=1)[0]
    return len(mantissa.partition(".")[2])


def _tensile_precision_decimal_places(value: Any) -> int:
    """Return central-value precision without borrowing uncertainty digits."""

    text = unicodedata.normalize("NFKC", str(value or ""))
    numbers = _tensile_precision_numbers(text)
    return (
        _tensile_precision_number_decimal_places(numbers[0])
        if numbers
        else -1
    )


def _tensile_precision_exact_parenthetical_comparator(
    fact: AxisFact, value: str
) -> bool:
    """Recognize an exact comparator value despite an outer relative clause.

    ``more than twice that of Sample A (358 MPa)`` is relative with respect to
    the sentence subject, but the parenthetical is still an exact absolute
    projection for Sample A.  Keep this exception deliberately narrow so a
    genuine threshold such as ``Sample A exceeded 358 MPa`` stays protected.
    """

    if not isinstance(fact, PropertyFact):
        return False
    value_numbers = _tensile_precision_numbers(value)
    if (
        len(value_numbers) != 1
        or _TENSILE_PRECISION_RANGE.search(value)
        or _TENSILE_PRECISION_RELATIVE.search(value)
        or _TENSILE_PRECISION_APPROXIMATE.search(value)
        or _TENSILE_PRECISION_BOUND_QUALIFIER.search(value)
    ):
        return False
    try:
        central = float(value_numbers[0])
    except ValueError:
        return False
    owner_key = normalize_source_alias(fact.sample_id_raw)
    # Do not use a one-letter/element-like token as comparator-owner evidence.
    if len(owner_key) < 4:
        return False
    fact_unit = _tensile_precision_unit_key(
        fact.data.get("unit_raw"), central=central
    )
    if fact_unit is None or fact_unit[0] not in {"mpa", "percent"}:
        return False
    unit_pattern = (
        re.compile(r"(?i)(?<![A-Za-z])(?:gpa|mpa|gigapascals?|megapascals?)(?![A-Za-z])")
        if fact_unit[0] == "mpa"
        else re.compile(r"(?i)(?:%|percent)")
    )
    relation = re.compile(
        r"(?i)\bthat\s+of\b(?P<owner>[^()]*)\((?P<value>[^()]*)\)"
    )
    for evidence in fact.source_evidence:
        row = unicodedata.normalize("NFKC", str(evidence or "")).strip()
        if not row or row.startswith("|"):
            continue
        for match in relation.finditer(row):
            if owner_key not in normalize_source_alias(match.group("owner")):
                continue
            parenthetical = match.group("value")
            if (
                _TENSILE_PRECISION_RANGE.search(parenthetical)
                or _TENSILE_PRECISION_RELATIVE.search(parenthetical)
                or _TENSILE_PRECISION_APPROXIMATE.search(parenthetical)
                or _TENSILE_PRECISION_BOUND_QUALIFIER.search(parenthetical)
                or not unit_pattern.search(parenthetical)
            ):
                continue
            parenthetical_numbers = _tensile_precision_numbers(parenthetical)
            if len(parenthetical_numbers) != 1:
                continue
            try:
                parenthetical_value = float(parenthetical_numbers[0])
            except ValueError:
                continue
            parenthetical_unit = _tensile_precision_unit_key(
                unit_pattern.search(parenthetical).group(0),
                central=parenthetical_value,
            )
            if (
                parenthetical_unit is not None
                and parenthetical_unit[0] == fact_unit[0]
                and abs(
                    parenthetical_value * parenthetical_unit[1]
                    - central * fact_unit[1]
                )
                <= 1e-9
            ):
                return True
    return False


def _tensile_precision_value_shape(fact: AxisFact) -> dict[str, Any] | None:
    if not isinstance(fact, PropertyFact) or not _numeric_core_tensile_fact(fact):
        return None
    value = str(fact.data.get("value_raw") or "").strip()
    if not value:
        return None
    numbers = _tensile_precision_numbers(value)
    if not numbers or _TENSILE_PRECISION_RANGE.search(value):
        return None
    relative_payload = " ".join(
        [
            value,
            str(fact.data.get("raw_note") or ""),
            str(fact.data.get("property_name_raw") or ""),
        ]
    )
    qualifier_payload = " ".join(
        [relative_payload, *(str(row) for row in fact.source_evidence)]
    )
    if (
        _TENSILE_PRECISION_RELATIVE.search(relative_payload)
        or _TENSILE_PRECISION_BOUND_QUALIFIER.search(qualifier_payload)
    ) and not _tensile_precision_exact_parenthetical_comparator(fact, value):
        return None
    try:
        central = float(numbers[0])
    except ValueError:
        return None
    uncertainty = None
    if len(numbers) == 2 and re.search(r"(?:±|\\pm|plus\s*/?\s*minus)", value, re.I):
        try:
            uncertainty = float(numbers[1])
        except ValueError:
            return None
    elif len(numbers) != 1:
        return None
    return {
        "central": central,
        "uncertainty": uncertainty,
        "has_uncertainty": uncertainty is not None,
        "decimal_places": _tensile_precision_decimal_places(value),
        "uncertainty_decimal_places": (
            _tensile_precision_number_decimal_places(numbers[1])
            if uncertainty is not None
            else -1
        ),
        "approximate": bool(
            _TENSILE_PRECISION_APPROXIMATE.search(qualifier_payload)
        ),
        "numbers": numbers,
    }


def _tensile_precision_unit_key(value: Any, *, central: float | None = None) -> tuple[str, float] | None:
    raw = unicodedata.normalize("NFKC", str(value or "")).strip()
    key = re.sub(r"\s+", "", raw.casefold())
    key = key.replace("μ", "µ")
    aliases = {
        "mpa": ("mpa", 1.0),
        "megapascal": ("mpa", 1.0),
        "megapascals": ("mpa", 1.0),
        "gpa": ("mpa", 1000.0),
        "gigapascal": ("mpa", 1000.0),
        "gigapascals": ("mpa", 1000.0),
        "%": ("percent", 1.0),
        "％": ("percent", 1.0),
        "percent": ("percent", 1.0),
    }
    if key in aliases:
        return aliases[key]
    if not key:
        return None
    return key, 1.0


def _tensile_precision_subtype(fact: AxisFact) -> str:
    if not isinstance(fact, PropertyFact):
        return ""
    return core_tensile_subtype(fact.data.get("property_name_raw"))


def _tensile_precision_condition(fact: AxisFact) -> str:
    if not isinstance(fact, PropertyFact):
        return ""
    return _normalized_literal(fact.data.get("test_condition_raw"))


def _tensile_precision_condition_values(fact: AxisFact) -> tuple[str, ...]:
    """Return explicit test/state conditions without inventing missing context."""

    if not isinstance(fact, PropertyFact):
        return ()
    values: list[str] = []
    for key in ("test_condition_raw", "condition_label_raw"):
        value = str(fact.data.get(key) or "").strip()
        if not value:
            continue
        try:
            wrapper = json.loads(value)
        except (TypeError, ValueError, json.JSONDecodeError):
            wrapper = None
        if isinstance(wrapper, dict):
            nonempty = {
                str(name).strip().casefold()
                for name, child in wrapper.items()
                if child not in (None, "", [], {})
            }
            if nonempty and nonempty <= {
                "method",
                "test_method",
                "test_method_raw",
            }:
                # Some provider rows duplicate the method field as a JSON
                # condition. It carries no temperature, state, orientation, or
                # specimen distinction and must not block a source-proven merge.
                continue
        values.append(value)
    return tuple(dict.fromkeys(value for value in values if value))


def _tensile_precision_condition_key(value: Any) -> str:
    """Fold harmless degree/LaTeX presentation differences in conditions."""

    text = unicodedata.normalize("NFKC", str(value or ""))
    text = re.sub(
        r"\^?\s*\\circ\s*(?:\{\s*C\s*\}|C)",
        "°C",
        text,
        flags=re.IGNORECASE,
    )
    return normalize_source_alias(text)


def _tensile_precision_conditions_compatible(left: Any, right: Any) -> bool:
    left_key = _tensile_precision_condition_key(left)
    right_key = _tensile_precision_condition_key(right)
    if bool(
        left_key
        and right_key
        and (
            left_key == right_key
            or left_key in right_key
            or right_key in left_key
        )
    ):
        return True
    left_descriptor = _state_descriptor(left)
    right_descriptor = _state_descriptor(right)
    if (
        left_descriptor is None
        or right_descriptor is None
        or left_descriptor[0].startswith("raw:")
        or right_descriptor[0].startswith("raw:")
        or left_descriptor[0] != right_descriptor[0]
    ):
        return False
    left_qualifiers = set(left_descriptor[1])
    right_qualifiers = set(right_descriptor[1])
    return bool(
        left_qualifiers
        and right_qualifiers
        and (
            left_qualifiers.issubset(right_qualifiers)
            or right_qualifiers.issubset(left_qualifiers)
        )
    )


_TENSILE_OWNER_CONDITION = re.compile(
    r"(?i)\b(?:sinter(?:ed|ing)?|ag(?:e|ed|eing|ing)|solution(?:ized|ising|izing|\s+treat(?:ed|ment)?)|"
    r"heat[\s-]*treat(?:ed|ment)?|as[\s-]*(?:built|printed|fabricated|deposited|produced)|"
    r"inter(?:layer|pass)\s+delay|delay)\b"
)


def _tensile_precision_owner_covers_condition(
    index: _IdentityIndex, owner: str, condition: Any
) -> bool:
    """Return whether a state-defining condition is encoded by one owner.

    Measurement conditions such as room temperature are deliberately ignored:
    they belong to the property record, not to material identity.  Preparation
    state and delay conditions must be entailed by the selected owner whenever
    precision deduplication changes owners.
    """

    condition_text = str(condition or "").strip()
    if not condition_text or not _TENSILE_OWNER_CONDITION.search(condition_text):
        return True
    contexts = [index.display_label(owner)]
    for anchor in index.anchors.get(owner, []):
        contexts.extend(
            str(value or "")
            for value in (
                anchor.sample_id_raw,
                anchor.material_name_raw,
                anchor.state_raw,
            )
            if str(value or "").strip()
        )
    condition_key = _tensile_precision_condition_key(condition_text)
    if any(
        condition_key
        and condition_key in _tensile_precision_condition_key(context)
        for context in contexts
    ):
        return True

    condition_descriptor = _state_descriptor(condition_text)
    if (
        condition_descriptor is not None
        and not condition_descriptor[0].startswith("raw:")
        and condition_descriptor[1]
    ):
        condition_category, condition_qualifiers = condition_descriptor
        for context in contexts:
            context_descriptor = _state_descriptor(context)
            if (
                context_descriptor is not None
                and context_descriptor[0] == condition_category
                and set(condition_qualifiers).issubset(context_descriptor[1])
            ):
                return True

    # Short source sample labels often reverse the phrase order, for example
    # ``interlayer delay: 0 s`` versus ``0 s Delay``.  Accept that presentation
    # only when the numeric+unit qualifiers agree and both sides name delay.
    condition_qualifiers = (
        set(condition_descriptor[1]) if condition_descriptor is not None else set()
    )
    if not condition_qualifiers or not re.search(r"(?i)\bdelay\b", condition_text):
        return False
    for context in contexts:
        descriptor = _state_descriptor(context)
        if (
            descriptor is not None
            and condition_qualifiers == set(descriptor[1])
            and re.search(r"(?i)\bdelay\b", context)
        ):
            return True
    return False


def _tensile_precision_source_role(index: _IdentityIndex, owner: str) -> tuple[str, str]:
    anchors = [*index.anchors.get(owner, [])]
    base = index.state_family_base.get(owner, owner)
    if base != owner:
        anchors.extend(index.anchors.get(base, []))
    roles = sorted({str(row.role or "").casefold() for row in anchors if row.role})
    natures = sorted({str(row.data_nature or "").casefold() for row in anchors if row.data_nature})
    return (roles[0] if len(roles) == 1 else "", natures[0] if len(natures) == 1 else "")


def _tensile_precision_owner_lineage(index: _IdentityIndex, owner: str) -> set[str]:
    keys = set(_owner_descriptor_keys(index, owner))
    base = index.state_family_base.get(owner, owner)
    keys.update(_owner_descriptor_keys(index, base))
    return keys


def _tensile_precision_evidence_names_owner(
    index: _IdentityIndex, owner: str, evidence: Sequence[str]
) -> bool:
    """Match literal owner/sample labels without broad material-family aliases."""

    labels = {index.display_label(owner)}
    labels.update(
        str(anchor.sample_id_raw or "").strip()
        for anchor in index.anchors.get(owner, [])
        if str(anchor.sample_id_raw or "").strip()
    )
    return any(
        _source_label_occurs_in_row(label, row)
        for label in labels
        for row in evidence
    )


def _tensile_precision_complete_table(fact: AxisFact) -> dict[str, Any] | None:
    """Return one unique owner/value table binding for a complete fact quote."""

    if not isinstance(fact, PropertyFact):
        return None
    source = str(fact.data.get("data_source") or "").strip().casefold()
    if source not in {"table", "unknown", ""}:
        return None
    rows = _fact_markdown_table_rows(fact)
    if len(rows) < 2:
        return None
    owner = str(fact.sample_id_raw or "").strip()

    def owner_cell_matches(cell: Any) -> bool:
        if _table_owner_cell_matches(owner, cell):
            return True
        owner_key = normalize_source_alias(owner)
        cell_key = normalize_source_alias(
            _tensile_precision_condition_key(
                _cell_without_reference_markers(cell)
            )
        )
        if not owner_key or not cell_key.startswith(owner_key):
            return False
        qualifier = cell_key[len(owner_key) :]
        if not qualifier:
            return False
        condition_keys = {
            normalize_source_alias(_tensile_precision_condition_key(value))
            for value in _tensile_precision_condition_values(fact)
        }
        condition_keys.discard("")
        return any(
            qualifier == condition
            or qualifier in condition
            or condition in qualifier
            for condition in condition_keys
        )

    value = fact.data.get("value_raw")
    candidates: list[dict[str, Any]] = []
    for header_row, header_cells in rows:
        owner_columns = [
            i for i, cell in enumerate(header_cells)
            if owner_cell_matches(cell)
        ]
        if len(owner_columns) != 1:
            continue
        owner_column = owner_columns[0]
        for value_row, value_cells in rows:
            if value_row == header_row or len(value_cells) != len(header_cells):
                continue
            cell = value_cells[owner_column]
            if not _table_value_cell_matches(value, cell):
                continue
            candidates.append(
                {
                    "binding": "column_value_cell",
                    "header_row": header_row,
                    "value_row": value_row,
                    "owner_cell": header_cells[owner_column],
                    "value_cell": cell,
                    "owner_column": owner_column,
                    "selected_column": owner_column,
                    "owner_condition_qualified": not _table_owner_cell_matches(
                        owner, header_cells[owner_column]
                    ),
                }
            )
    for value_row, value_cells in rows:
        owner_columns = [
            i for i, cell in enumerate(value_cells)
            if owner_cell_matches(cell)
        ]
        if len(owner_columns) != 1:
            continue
        owner_column = owner_columns[0]
        value_columns = [
            i for i, cell in enumerate(value_cells)
            if i != owner_column and _table_value_cell_matches(value, cell)
        ]
        if len(value_columns) != 1:
            continue
        selected_column = value_columns[0]
        header_rows = [
            row for row, cells in rows
            if row != value_row and len(cells) == len(value_cells)
        ]
        if header_rows:
            candidates.append(
                {
                    "binding": "row_owner_value_cell",
                    "header_row": header_rows[0],
                    "value_row": value_row,
                    "owner_cell": value_cells[owner_column],
                    "value_cell": value_cells[selected_column],
                    "owner_column": owner_column,
                    "selected_column": selected_column,
                    "owner_condition_qualified": not _table_owner_cell_matches(
                        owner, value_cells[owner_column]
                    ),
                }
            )
    unique: dict[str, dict[str, Any]] = {}
    for candidate in candidates:
        signature = json.dumps(candidate, ensure_ascii=False, sort_keys=True)
        unique.setdefault(signature, candidate)
    if len(unique) != 1:
        return None
    binding = next(iter(unique.values()))
    binding["table_complete"] = True
    return binding


def _tensile_precision_evidence_score(
    fact: AxisFact, *, table_binding: dict[str, Any] | None = None
) -> tuple[int, int, int, int, int, int]:
    shape = _tensile_precision_value_shape(fact)
    if shape is None:
        return (-1, -1, -1, -1, -1, -1)
    table = int(table_binding is not None)
    uncertainty = int(shape["has_uncertainty"])
    return (
        int(not shape["approximate"]),
        uncertainty,
        shape["decimal_places"],
        shape["uncertainty_decimal_places"],
        table,
        len(fact.source_evidence),
    )


def _tensile_precision_owner_specificity(index: _IdentityIndex, owner: str) -> int:
    base = index.state_family_base.get(owner, owner)
    score = 0
    if owner != base:
        score += 2
    labels = [index.display_label(owner)]
    state_labels: list[Any] = []
    for row in index.anchors.get(owner, []):
        labels.extend((row.sample_id_raw, row.material_name_raw, row.state_raw))
        state_labels.append(row.state_raw)
    text = " ".join(str(row or "") for row in labels)
    score += int(bool(re.search(r"(?i)\b(?:sintered|aged|heat[- ]treated|as[- ]built|wrought|delay|state)\b", text)))
    descriptors = [
        descriptor
        for value in state_labels
        if (descriptor := _state_descriptor(value)) is not None
        and not descriptor[0].startswith("raw:")
    ]
    score += max((len(descriptor[1]) for descriptor in descriptors), default=0)
    return score


def _tensile_precision_explicit_prose_binding(
    index: _IdentityIndex, fact: AxisFact, owner: str
) -> dict[str, Any] | None:
    """Bind one numeric tensile assertion to its literal prose owner."""

    if not isinstance(fact, PropertyFact):
        return None
    data_source = str(fact.data.get("data_source") or "").strip().casefold()
    if data_source in {"chart", "figure", "image"}:
        return None
    rows = []
    for evidence in fact.source_evidence:
        row = str(evidence or "").strip()
        if not row or row.startswith("|"):
            continue
        if not _tensile_precision_evidence_names_owner(index, owner, [row]):
            continue
        if not _property_assertion_occurs_in_text(fact, row):
            continue
        rows.append(row)
    rows = list(dict.fromkeys(rows))
    if not rows:
        return None
    return {
        "binding": "explicit_prose_owner_value",
        "owner": index.display_label(owner),
        "evidence": rows,
    }


_TENSILE_ORIENTATION_WORD = re.compile(
    r"(?i)\b(?:horizontal(?:ly)?|vertical(?:ly)?|longitudinal(?:ly)?|"
    r"transverse(?:ly)?)\b"
)
_TENSILE_AXIS_ORIENTATION = re.compile(
    r"(?i)\b(?P<axis>[xyz])\s*(?:axis|orientation|direction)\b"
)
_TENSILE_OWNER_AXIS_SUFFIX = re.compile(
    r"(?i)(?:\s*/\s*|\s+)(?P<axis>[xyz])(?:\s+(?:axis|orientation|direction))?\s*$"
)


def _tensile_orientation_tokens(value: Any, *, owner_label: bool = False) -> set[str]:
    text = unicodedata.normalize("NFKC", str(value or "")).strip()
    tokens = {
        match.group(0).casefold()
        for match in _TENSILE_ORIENTATION_WORD.finditer(text)
    }
    tokens.update(
        match.group("axis").casefold()
        for match in _TENSILE_AXIS_ORIENTATION.finditer(text)
    )
    if owner_label and (match := _TENSILE_OWNER_AXIS_SUFFIX.search(text)):
        tokens.add(match.group("axis").casefold())
    return tokens


def _tensile_owner_base_labels(index: _IdentityIndex, owner: str) -> set[str]:
    values = [index.display_label(owner)]
    values.extend(
        value
        for anchor in index.anchors.get(owner, [])
        for value in (anchor.sample_id_raw, anchor.material_name_raw)
        if str(value or "").strip()
    )
    labels: set[str] = set()
    for value in values:
        text = unicodedata.normalize("NFKC", str(value or "")).strip()
        text = _TENSILE_OWNER_AXIS_SUFFIX.sub("", text)
        text = re.sub(
            r"(?i)\s+(?:horizontal|vertical|longitudinal|transverse)"
            r"(?:\s+(?:orientation|direction))?\s*$",
            "",
            text,
        )
        normalized = normalize_source_alias(text)
        if normalized:
            labels.add(normalized)
    return labels


def _orientation_qualified_tensile_owner(
    index: _IdentityIndex,
    *,
    loser_owner: str,
    winner_owner: str,
    loser: AxisFact,
) -> bool:
    """Prove that one table owner is the oriented form of a coarse owner."""

    if not isinstance(loser, PropertyFact):
        return False
    winner_labels = [index.display_label(winner_owner)]
    winner_labels.extend(
        anchor.sample_id_raw for anchor in index.anchors.get(winner_owner, [])
    )
    winner_orientations = {
        token
        for label in winner_labels
        for token in _tensile_orientation_tokens(label, owner_label=True)
    }
    if len(winner_orientations) != 1:
        return False
    loser_context = "\n".join(
        [
            str(loser.data.get("test_condition_raw") or ""),
            str(loser.data.get("test_specimen_raw") or ""),
            *loser.source_evidence,
        ]
    )
    if _tensile_orientation_tokens(loser_context) != winner_orientations:
        return False
    return bool(
        _tensile_owner_base_labels(index, loser_owner)
        & _tensile_owner_base_labels(index, winner_owner)
    )


def _truncated_tensile_owner_prefix(
    index: _IdentityIndex, *, loser_owner: str, winner_owner: str
) -> bool:
    """Recognize an OCR-truncated owner only for one richer matching result."""

    loser_label = str(index.display_label(loser_owner) or "").strip()
    if not re.search(r"[-/]\s*$", loser_label):
        return False
    loser_prefix = normalize_source_alias(loser_label)
    winner_label = normalize_source_alias(index.display_label(winner_owner))
    return bool(loser_prefix and winner_label.startswith(loser_prefix))


def _tensile_precision_rounded_values_compatible(
    loser_shape: dict[str, Any],
    winner_shape: dict[str, Any],
    loser_unit: tuple[str, float],
    winner_unit: tuple[str, float],
) -> bool:
    """Return whether a richer value is the loser's literal rounding envelope."""

    loser_decimals = int(loser_shape["decimal_places"])
    winner_decimals = int(winner_shape["decimal_places"])
    if winner_decimals <= loser_decimals:
        return False
    winner_in_loser_units = (
        float(winner_shape["central"]) * winner_unit[1] / loser_unit[1]
    )
    loser_central = float(loser_shape["central"])
    tolerance = max(1e-12, 10.0 ** (-(loser_decimals + 8)))
    if abs(
        round(winner_in_loser_units, loser_decimals)
        - round(loser_central, loser_decimals)
    ) > tolerance:
        return False

    loser_uncertainty = loser_shape["uncertainty"]
    winner_uncertainty = winner_shape["uncertainty"]
    if loser_uncertainty is not None and winner_uncertainty is None:
        return False
    if loser_uncertainty is None or winner_uncertainty is None:
        return True

    winner_uncertainty_in_loser_units = (
        float(winner_uncertainty) * winner_unit[1] / loser_unit[1]
    )
    loser_low = loser_central - float(loser_uncertainty)
    loser_high = loser_central + float(loser_uncertainty)
    winner_low = winner_in_loser_units - winner_uncertainty_in_loser_units
    winner_high = winner_in_loser_units + winner_uncertainty_in_loser_units
    return max(loser_low, winner_low) <= min(loser_high, winner_high) + tolerance


def _tensile_precision_pair_relation(
    index: _IdentityIndex,
    loser: AxisFact,
    winner: AxisFact,
    loser_owner: str,
    winner_owner: str,
    loser_binding: dict[str, Any] | None,
    winner_binding: dict[str, Any] | None,
    loser_prose_binding: dict[str, Any] | None,
    winner_prose_binding: dict[str, Any] | None,
) -> str:
    loser_shape = _tensile_precision_value_shape(loser)
    winner_shape = _tensile_precision_value_shape(winner)
    if loser_shape is None or winner_shape is None:
        return ""
    # An approximate presentation may be absorbed by a source-backed exact
    # record, but it must never dominate that exact record merely because a
    # converted unit happens to contain more decimal places (for example,
    # ``2.2 GPa`` versus ``2200 MPa``).
    if winner_shape["approximate"] and not loser_shape["approximate"]:
        return ""
    loser_unit = _tensile_precision_unit_key(loser.data.get("unit_raw"), central=loser_shape["central"])
    winner_unit = _tensile_precision_unit_key(winner.data.get("unit_raw"), central=winner_shape["central"])
    if loser_unit is None or winner_unit is None or loser_unit[0] != winner_unit[0]:
        return ""
    exact_central = (
        abs(
            loser_shape["central"] * loser_unit[1]
            - winner_shape["central"] * winner_unit[1]
        )
        <= 1e-9
    )
    rounded_central = _tensile_precision_rounded_values_compatible(
        loser_shape, winner_shape, loser_unit, winner_unit
    )
    if (
        not exact_central
        and not rounded_central
        and winner_binding is not None
        and _rounded_table_value_matches(
            loser.data.get("value_raw"), winner_binding.get("value_cell")
        )
    ):
        # A prose headline often rounds a table mean to an integer (859 MPa
        # versus 859.7 ± 9.17 MPa).  The generic precision comparator is
        # intentionally stricter for unrelated facts; here the complete table
        # binding has already proved the same owner, semantic row, unit, and
        # unique value coordinate, so the source-table rounding rule is safe.
        rounded_central = True
    if not exact_central and not rounded_central:
        return ""
    if _core_tensile_semantic(loser) != _core_tensile_semantic(winner):
        return ""
    loser_subtype = _tensile_precision_subtype(loser)
    winner_subtype = _tensile_precision_subtype(winner)
    if loser_subtype != winner_subtype and "unspecified" not in {loser_subtype, winner_subtype}:
        return ""
    loser_conditions = _tensile_precision_condition_values(loser)
    winner_conditions = _tensile_precision_condition_values(winner)
    if loser_conditions and winner_conditions:
        if not any(
            _tensile_precision_conditions_compatible(left, right)
            for left in loser_conditions
            for right in winner_conditions
        ):
            return ""
    elif loser_conditions or winner_conditions:
        # A preparation condition carried by only one projection is safe only
        # when the selected owner explicitly encodes that same state.  This is
        # what distinguishes a base alloy with ``delay: 0 s`` from an
        # unrelated scalar carrying no source-backed state relation.
        one_sided = (*loser_conditions, *winner_conditions)
        if not all(
            _tensile_precision_owner_covers_condition(index, winner_owner, value)
            for value in one_sided
        ):
            return ""
    if _tensile_precision_source_role(index, loser_owner) != _tensile_precision_source_role(index, winner_owner):
        return ""
    if loser_owner != winner_owner:
        relation = _cross_item_dominance_relation(
            index,
            loser_owner=loser_owner,
            winner_owner=winner_owner,
            loser_fact=loser,
        )
        if not relation:
            loser_lineage = _tensile_precision_owner_lineage(index, loser_owner)
            winner_lineage = _tensile_precision_owner_lineage(index, winner_owner)
            if (
                _tensile_precision_owner_specificity(index, winner_owner)
                > _tensile_precision_owner_specificity(index, loser_owner)
                and loser_lineage & winner_lineage
                and not _tensile_precision_evidence_names_owner(
                    index, loser_owner, loser.source_evidence
                )
            ):
                relation = "explicit_state_owner_over_generic_projection"
        if (
            not relation
            and winner_binding is not None
            and loser_lineage & winner_lineage
            and not _tensile_precision_evidence_names_owner(
                index, loser_owner, loser.source_evidence
            )
        ):
            # A provider can assign every value in an owner-free summary tuple
            # to one arbitrary sample. A complete table row/column is the
            # stronger owner binding, but only precision improvement below may
            # activate the merge; equal-information presentations stay protected.
            relation = "complete_table_owner_over_source_unnamed_projection"
        if (
            not relation
            and winner_prose_binding is not None
            and loser_lineage & winner_lineage
            and _tensile_precision_owner_specificity(index, winner_owner)
            > _tensile_precision_owner_specificity(index, loser_owner)
            and not _explicit_primary_owner_mentions(
                index, loser.source_evidence, set(index.anchors)
            )
        ):
            relation = "explicit_prose_owner_over_unnamed_summary"
        if (
            not relation
            and winner_binding is not None
            and _tensile_precision_owner_specificity(index, winner_owner)
            > _tensile_precision_owner_specificity(index, loser_owner)
            and any(
                _TENSILE_OWNER_CONDITION.search(str(value))
                for value in (*loser_conditions, *winner_conditions)
            )
            and all(
                _tensile_precision_owner_covers_condition(
                    index, winner_owner, value
                )
                for value in (*loser_conditions, *winner_conditions)
                if _TENSILE_OWNER_CONDITION.search(str(value))
            )
        ):
            relation = "condition_qualified_owner_over_generic_projection"
        if (
            not relation
            and winner_binding is not None
            and _orientation_qualified_tensile_owner(
                index,
                loser_owner=loser_owner,
                winner_owner=winner_owner,
                loser=loser,
            )
        ):
            relation = "orientation_condition_owner_with_table_precision"
        if (
            not relation
            and winner_binding is not None
            and _truncated_tensile_owner_prefix(
                index,
                loser_owner=loser_owner,
                winner_owner=winner_owner,
            )
        ):
            relation = "completed_owner_label_over_truncated_projection"
        if not relation:
            return ""
    central_precision_gain = bool(
        winner_shape["decimal_places"] > loser_shape["decimal_places"]
    )
    uncertainty_precision_gain = bool(
        winner_shape["has_uncertainty"]
        and loser_shape["has_uncertainty"]
        and winner_shape["uncertainty_decimal_places"]
        > loser_shape["uncertainty_decimal_places"]
    )
    precision_gain = bool(
        (winner_shape["has_uncertainty"] and not loser_shape["has_uncertainty"])
        or central_precision_gain
        or uncertainty_precision_gain
        or (loser_shape["approximate"] and not winner_shape["approximate"])
    )
    measurement_improvement = bool(winner_binding is not None and precision_gain)
    measurement_not_worse = bool(
        (winner_shape["has_uncertainty"] or not loser_shape["has_uncertainty"])
        and winner_shape["decimal_places"] >= loser_shape["decimal_places"]
        and (
            not loser_shape["has_uncertainty"]
            or winner_shape["uncertainty_decimal_places"]
            >= loser_shape["uncertainty_decimal_places"]
        )
    )
    if loser_owner == winner_owner:
        if (
            winner_binding is not None
            and winner_binding.get("owner_condition_qualified")
            and exact_central
            and not loser_shape["approximate"]
        ):
            # A condition-qualified table statistic and an exact headline from
            # the same owner can be independently reportable claims. The
            # qualified owner cell is still valid evidence for repairing an
            # OCR-truncated *different* owner, but must not erase the same-owner
            # headline and reduce recall.
            return ""
        if measurement_improvement:
            return "table_precision_over_projection"
        if winner_prose_binding is not None and precision_gain:
            return "explicit_prose_precision_over_projection"
        if (
            precision_gain
            and len(loser.source_evidence) == 1
            and len(winner.source_evidence) == 1
        ):
            # Exact same-owner repetitions frequently omit the owner in the
            # local evidence fragment (for example a result sentence following
            # an owner-bearing sentence). Conditions, subtype, role, units, and
            # value compatibility have already passed above, and candidate
            # selection still requires one unambiguous richer survivor.
            return "same_owner_richer_precision_over_projection"
        return ""
    if measurement_improvement and relation:
        if relation == "orientation_condition_owner_with_table_precision":
            return relation
        return "unique_table_record_over_rounded_projection"
    if (winner_binding is not None or winner_prose_binding is not None) and relation in {
        "qualified_state_over_base",
        "explicit_state_owner_over_generic_projection",
        "condition_qualified_owner_over_generic_projection",
        "explicit_prose_owner_over_unnamed_summary",
        "orientation_condition_owner_with_table_precision",
        "completed_owner_label_over_truncated_projection",
    } and measurement_not_worse:
        return relation
    return ""


def _merge_tensile_precision_envelope(survivor: AxisFact, removed: AxisFact) -> AxisFact:
    merged = _merge_fact_envelope_evidence(survivor, removed)
    if isinstance(merged, PropertyFact) and isinstance(removed, PropertyFact):
        updates: dict[str, Any] = {}
        if not str(merged.data.get("test_condition_raw") or "").strip() and str(removed.data.get("test_condition_raw") or "").strip():
            updates["test_condition_raw"] = removed.data["test_condition_raw"]
        if not str(merged.data.get("test_standard_raw") or "").strip() and str(removed.data.get("test_standard_raw") or "").strip():
            updates["test_standard_raw"] = removed.data["test_standard_raw"]
        if updates:
            merged = merged.model_copy(update={"data": {**merged.data, **updates}})
    return merged


def _deduplicate_tensile_precision_evidence(
    index: _IdentityIndex,
    facts: Sequence[AxisFact],
    source_text: str = "",
) -> tuple[list[AxisFact], list[MaterializeIssue]]:
    """Merge only a uniquely richer numeric tensile projection."""

    routed = {id(fact): _group_route(index, fact) for fact in facts}
    bindings = {id(fact): _tensile_precision_complete_table(fact) for fact in facts}
    protected_bundle_members = {
        position
        for bundle in _same_owner_complete_tensile_bundles(
            index, facts, source_text
        )
        for _, position in bundle.members
    }
    prose_bindings: dict[int, dict[str, Any] | None] = {}
    for fact in facts:
        owners = routed[id(fact)]
        prose_bindings[id(fact)] = (
            _tensile_precision_explicit_prose_binding(index, fact, owners[0])
            if len(owners) == 1 and bindings[id(fact)] is None
            else None
        )
    candidates: dict[int, list[tuple[int, str, str]]] = {}
    for loser_position, loser in enumerate(facts):
        if _tensile_precision_value_shape(loser) is None:
            continue
        loser_owners = routed[id(loser)]
        if len(loser_owners) != 1:
            continue
        for winner_position, winner in enumerate(facts):
            if loser_position == winner_position:
                continue
            winner_owners = routed[id(winner)]
            if len(winner_owners) != 1:
                continue
            relation = _tensile_precision_pair_relation(
                index,
                loser,
                winner,
                loser_owners[0],
                winner_owners[0],
                bindings[id(loser)],
                bindings[id(winner)],
                prose_bindings[id(loser)],
                prose_bindings[id(winner)],
            )
            if (
                relation == "same_owner_richer_precision_over_projection"
                and winner_position in protected_bundle_members
            ):
                # Let the source-block bundle pass enforce its stricter
                # single-assertion and complete-YS/UTS/elongation protections
                # and emit the more specific bundle audit.
                continue
            if relation:
                candidates.setdefault(loser_position, []).append(
                    (winner_position, relation, winner_owners[0])
                )
    selected: dict[int, tuple[int, str, str]] = {}
    for loser_position, options in candidates.items():
        winner_owners = {option[2] for option in options}
        if len(winner_owners) != 1:
            continue

        # A prose projection may carry the exact preparation condition while
        # the richer table statistic omits it because the owner is encoded by
        # the table column.  Once the table owner is uniquely resolved, that
        # one-sided condition is not an ambiguity: the selected owner itself
        # covers it.  Filter competing options individually so an unbound
        # rounded table shadow cannot block the genuinely complete table
        # survivor.
        compatible_options: list[tuple[int, str, str]] = []
        loser_conditions = _tensile_precision_condition_values(
            facts[loser_position]
        )
        for option in options:
            winner_position = option[0]
            winner = facts[winner_position]
            winner_conditions = _tensile_precision_condition_values(winner)
            if bool(loser_conditions) != bool(winner_conditions):
                winner_binding = bindings[id(winner)]
                if winner_binding is None or not all(
                    _tensile_precision_owner_covers_condition(
                        index, option[2], value
                    )
                    for value in (*loser_conditions, *winner_conditions)
                ):
                    continue
            elif loser_conditions and winner_conditions and not any(
                _tensile_precision_conditions_compatible(left, right)
                for left in loser_conditions
                for right in winner_conditions
            ):
                continue
            compatible_options.append(option)
        options = compatible_options
        if not options:
            continue
        option_facts = [facts[option[0]] for option in options]
        option_subtypes = {
            _tensile_precision_subtype(fact) for fact in option_facts
        }
        if len(option_subtypes) != 1:
            # An unspecified projection cannot choose between independent
            # uniform/fracture elongation records merely because their owner
            # and scalar happen to be the same.
            continue
        option_conditions = [
            _tensile_precision_condition_values(fact) for fact in option_facts
        ]
        if any(
            left
            and right
            and not any(
                _tensile_precision_conditions_compatible(
                    left_value, right_value
                )
                for left_value in left
                for right_value in right
            )
            for position, left in enumerate(option_conditions)
            for right in option_conditions[position + 1 :]
        ):
            # A coarse/approximate claim with several condition-specific exact
            # candidates has no unique scientific survivor. Preserve it for
            # review instead of assigning it to one arbitrary condition.
            continue
        # Multiple cached projections can already route to the same survivor
        # owner. Prefer its uniquely complete/precise record; a competing owner,
        # not a duplicate presentation of one owner, is the scientific ambiguity.
        selected[loser_position] = max(
            options,
            key=lambda option: (
                _tensile_precision_evidence_score(
                    facts[option[0]],
                    table_binding=bindings[id(facts[option[0]])],
                ),
                _signature(facts[option[0]].model_dump()),
            ),
        )
    # A winner that is itself dominated is still valid only if the final choice
    # is a single strict maximum; this prevents order-dependent transitive chains.
    for loser_position, option in list(selected.items()):
        winner_position = option[0]
        if winner_position in selected and selected[winner_position][0] != winner_position:
            selected.pop(loser_position, None)

    replacements: dict[int, AxisFact] = {}
    removed_positions: set[int] = set()
    issues: list[MaterializeIssue] = []
    for loser_position, (winner_position, relation, winner_owner) in sorted(selected.items()):
        if loser_position in removed_positions or winner_position in removed_positions:
            continue
        survivor = replacements.get(winner_position, facts[winner_position])
        removed = facts[loser_position]
        winner_source_shape = _tensile_precision_value_shape(survivor)
        before = survivor.model_dump()
        survivor = _merge_tensile_precision_envelope(survivor, removed)
        survivor_owner = winner_owner
        if relation == "orientation_condition_owner_with_table_precision":
            # ``LPBF / X`` is a convenient table-column label, not necessarily
            # a distinct material identity. The prose projection proves the
            # base owner and carries X/Y/Z as a test condition, while the table
            # proves the richer measurement. Combine those two independent
            # strengths instead of converting orientation into a new owner.
            removed_condition = str(
                removed.data.get("test_condition_raw") or ""
            ).strip()
            data = dict(survivor.data)
            if removed_condition:
                data["test_condition_raw"] = removed_condition
            survivor = survivor.model_copy(
                update={
                    "sample_id_raw": removed.sample_id_raw,
                    "data": data,
                }
            )
            survivor_owner = routed[id(removed)][0]
        replacements[winner_position] = survivor
        removed_positions.add(loser_position)
        removed_shape = _tensile_precision_value_shape(removed)
        survivor_shape = _tensile_precision_value_shape(survivor)
        approximate_shadow = bool(
            removed_shape
            and winner_source_shape
            and removed_shape["approximate"]
            and not winner_source_shape["approximate"]
        )
        issues.append(
            MaterializeIssue(
                code=(
                    "core_tensile_approximate_shadow_quarantined"
                    if approximate_shadow
                    else "tensile_precision_duplicate_merged"
                ),
                sample_id_raw=index.display_label(survivor_owner),
                path=f"items.{index.display_label(survivor_owner)}.Extracted_Data.Properties",
                message=(
                    "An approximate core-tensile presentation was isolated behind "
                    "one exact source record at the same scientific coordinate."
                    if approximate_shadow
                    else "A less precise numeric core-tensile projection was merged into one uniquely dominant source record."
                ),
                evidence={
                    "loser_evidence": list(removed.source_evidence),
                    "winner_evidence": list(survivor.source_evidence),
                    "winner_table_binding": bindings[id(facts[winner_position])],
                    "winner_prose_binding": prose_bindings[
                        id(facts[winner_position])
                    ],
                    "loser_table_binding": bindings[id(removed)],
                    "loser_prose_binding": prose_bindings[id(removed)],
                },
                expected={
                    "rule": relation,
                    "unique_survivor": True,
                    "same_semantic_value_unit_role": True,
                },
                actual={
                    "before_owner": removed.sample_id_raw,
                    "winner_source_owner": index.display_label(winner_owner),
                    "after_owner": index.display_label(survivor_owner),
                    "normalized_semantic": _core_tensile_semantic(removed),
                    "loser_value_shape": _tensile_precision_value_shape(removed),
                    "winner_value_shape": _tensile_precision_value_shape(survivor),
                    "loser_conditions": list(
                        _tensile_precision_condition_values(removed)
                    ),
                    "winner_conditions": list(
                        _tensile_precision_condition_values(survivor)
                    ),
                    "removed_fact": removed.model_dump(),
                    "reason": (
                        "same_coordinate_exact_value_dominates_approximate_shadow"
                        if approximate_shadow
                        else relation
                    ),
                    "survivor_before_merge": before,
                    "survivor_after_merge": survivor.model_dump(),
                    "winner_owner_candidates": [winner_owner],
                    "protection_gates": {
                        "condition_conflict": False,
                        "role_nature_conflict": False,
                        "elongation_subtype_conflict": False,
                        "range_relative_threshold": False,
                    },
                },
                suggested_action="Review only if the two literal records describe independent specimens rather than one precision projection.",
            )
        )
    return [
        replacements.get(position, fact)
        for position, fact in enumerate(facts)
        if position not in removed_positions
    ], issues


_TENSILE_BUNDLE_SEMANTICS = (
    "yield_strength",
    "ultimate_tensile_strength",
    "elongation",
)
_TENSILE_BUNDLE_APPROXIMATE = re.compile(
    r"(?i)(?:[~≈]|\b(?:approximately|approx\.?|about|around|roughly)\b)"
)
_TENSILE_BUNDLE_BLOCKED_VALUE = re.compile(
    r"(?i)(?:[<>≤≥]|\b(?:at least|at most|more than|less than|greater than|"
    r"up to|minimum|maximum|threshold|required|required\s+by)\b|"
    r"(?:increase|decrease|change|improv(?:e|ed|ement)|reduc(?:e|ed|tion))\s+by|"
    r"%\s*(?:increase|decrease|change|up|down)|"
    r"\b(?:higher|lower|greater|less)\b)"
)


@dataclass(frozen=True)
class _SameOwnerTensileBundle:
    owner: str
    members: tuple[tuple[str, int], ...]
    evidence_key: str
    evidence_text: str
    evidence_unit_ids: tuple[str, ...]
    condition_values: tuple[str, ...]
    elongation_subtype: str
    role_nature: tuple[str, str]
    binding_kind: str
    stable_key: str


@dataclass(frozen=True)
class _TensileSourceBlock:
    key: str
    text: str
    kind: str
    ordinal: int


def _tensile_source_blocks(source_text: str) -> list[_TensileSourceBlock]:
    """Parse stable table/paragraph blocks once for the member-level pass."""

    lines = str(source_text or "").splitlines()
    blocks: list[_TensileSourceBlock] = []
    position = 0
    ordinal = 0
    while position < len(lines):
        line = lines[position].strip()
        if not line:
            position += 1
            continue
        if line.startswith("|") and line.endswith("|") and line.count("|") >= 3:
            table: list[str] = []
            while position < len(lines):
                candidate = lines[position].strip()
                if not (
                    candidate.startswith("|")
                    and candidate.endswith("|")
                    and candidate.count("|") >= 3
                ):
                    break
                table.append(candidate)
                position += 1
            text = "\n".join(table).strip()
            if text:
                key = f"table:{ordinal:06d}:{_normalized_literal(text)}"
                blocks.append(
                    _TensileSourceBlock(key, text, "markdown_table", ordinal)
                )
                ordinal += 1
            continue
        paragraph: list[str] = []
        while position < len(lines):
            candidate = lines[position].strip()
            if not candidate:
                break
            if (
                paragraph
                and candidate.startswith("|")
                and candidate.endswith("|")
                and candidate.count("|") >= 3
            ):
                break
            paragraph.append(candidate)
            position += 1
        text = "\n".join(paragraph).strip()
        if text:
            key = f"source_assertion:{ordinal:06d}:{_normalized_literal(text)}"
            blocks.append(
                _TensileSourceBlock(key, text, "source_assertion", ordinal)
            )
            ordinal += 1
        if position < len(lines) and not lines[position].strip():
            position += 1
    return blocks


def _tensile_fact_source_blocks(
    fact: AxisFact, blocks: Sequence[_TensileSourceBlock]
) -> list[_TensileSourceBlock]:
    """Locate blocks that contain one fact's copied evidence/assertion."""

    located: list[_TensileSourceBlock] = []
    evidence_keys = [
        _literal_match_key(row)
        for row in fact.source_evidence
        if str(row or "").strip()
    ]
    for block in blocks:
        block_key = _literal_match_key(block.text)
        evidence_match = any(
            len(key) >= 8 and (key in block_key or block_key in key)
            for key in evidence_keys
        )
        if not evidence_match:
            continue
        if not _tensile_bundle_assertion_occurs_in_text(fact, block.text):
            continue
        located.append(block)
    return located


def _tensile_bundle_value_shape(fact: AxisFact) -> dict[str, Any] | None:
    """Parse an exact or explicitly approximate scalar for bundle-only use."""

    if not isinstance(fact, PropertyFact) or not _numeric_core_tensile_fact(fact):
        return None
    raw_payload = " ".join(
        [
            str(fact.data.get("value_raw") or ""),
            str(fact.data.get("raw_note") or ""),
            str(fact.data.get("property_name_raw") or ""),
        ]
    )
    if _TENSILE_BUNDLE_BLOCKED_VALUE.search(raw_payload):
        return None
    ordinary = _tensile_precision_value_shape(fact)
    if ordinary is not None:
        # The general parser now admits approximate projections so they can be
        # merged into a uniquely richer source record. Preserve that marker;
        # treating an approximate scalar as exact would erase the audit reason
        # and could let it dominate an exact bundle member.
        return ordinary
    value = unicodedata.normalize(
        "NFKC", str(fact.data.get("value_raw") or "")
    ).strip()
    if not value or _TENSILE_PRECISION_RANGE.search(value):
        return None
    payload = " ".join(
        [
            value,
            str(fact.data.get("raw_note") or ""),
            str(fact.data.get("property_name_raw") or ""),
            *(str(row) for row in fact.source_evidence),
        ]
    )
    if not _TENSILE_BUNDLE_APPROXIMATE.search(payload):
        return None
    numbers = _tensile_precision_numbers(value)
    if not numbers:
        return None
    try:
        central = float(numbers[0])
    except ValueError:
        return None
    uncertainty = None
    if len(numbers) == 2 and re.search(
        r"(?:±|\\pm|plus\s*/?\s*minus)", value, re.I
    ):
        try:
            uncertainty = float(numbers[1])
        except ValueError:
            return None
    elif len(numbers) != 1:
        return None
    return {
        "central": central,
        "uncertainty": uncertainty,
        "has_uncertainty": uncertainty is not None,
        "decimal_places": _tensile_precision_decimal_places(value),
        "uncertainty_decimal_places": (
            _tensile_precision_number_decimal_places(numbers[1])
            if uncertainty is not None
            else -1
        ),
        "numbers": numbers,
        "approximate": True,
    }


def _tensile_bundle_assertion_occurs_in_text(
    fact: AxisFact, text: str
) -> bool:
    if _property_assertion_occurs_in_text(fact, text):
        return True
    semantic = _core_tensile_semantic(fact)
    if not semantic or not isinstance(fact, PropertyFact):
        return False
    cues = {
        "yield_strength": re.compile(
            r"(?i)\byield\s+(?:strength|stress)|\bYS\b"
        ),
        "ultimate_tensile_strength": re.compile(
            r"(?i)\b(?:ultimate\s+)?tensile\s+(?:strength|stress)|\bUTS\b"
        ),
        "elongation": re.compile(
            r"(?i)\belongation|\bductility\b|\b(?:EL|TE|EAB)\b"
        ),
    }
    if not cues[semantic].search(text):
        return False
    value_numbers = _tensile_precision_numbers(fact.data.get("value_raw"))
    text_numbers = set(_tensile_precision_numbers(text))
    return bool(value_numbers) and all(
        number in text_numbers for number in value_numbers
    )


def _tensile_bundle_conditions_internally_compatible(
    values: Sequence[str],
) -> bool:
    return all(
        _tensile_precision_conditions_compatible(left, right)
        for position, left in enumerate(values)
        for right in values[position + 1 :]
    )


def _same_owner_complete_tensile_bundles(
    index: _IdentityIndex,
    facts: Sequence[AxisFact],
    source_text: str,
) -> list[_SameOwnerTensileBundle]:
    """Build complete survivor bundles from one source block only."""

    blocks = _tensile_source_blocks(source_text)
    routed = {id(fact): _group_route(index, fact) for fact in facts}
    block_members: dict[tuple[str, str, str], dict[str, list[int]]] = {}
    block_rows: dict[str, _TensileSourceBlock] = {
        block.key: block for block in blocks
    }
    for position, fact in enumerate(facts):
        shape = _tensile_bundle_value_shape(fact)
        semantic = _core_tensile_semantic(fact)
        owners = routed[id(fact)]
        if (
            shape is None
            or semantic not in _TENSILE_BUNDLE_SEMANTICS
            or len(owners) != 1
        ):
            continue
        owner = owners[0]
        for block in _tensile_fact_source_blocks(fact, blocks):
            condition_key = tuple(
                sorted(
                    _tensile_precision_condition_key(value)
                    for value in _tensile_precision_condition_values(fact)
                )
            )
            key = (owner, block.key, json.dumps(condition_key, ensure_ascii=False))
            block_members.setdefault(key, {}).setdefault(semantic, []).append(position)

    bundles: list[_SameOwnerTensileBundle] = []
    for (owner, block_key, _), semantic_positions in sorted(block_members.items()):
        if any(
            len(semantic_positions.get(semantic, [])) != 1
            for semantic in _TENSILE_BUNDLE_SEMANTICS
        ):
            continue
        members = tuple(
            (semantic, semantic_positions[semantic][0])
            for semantic in _TENSILE_BUNDLE_SEMANTICS
        )
        block = block_rows[block_key]
        if not all(
            _tensile_bundle_assertion_occurs_in_text(facts[position], block.text)
            for _, position in members
        ):
            continue
        condition_values = tuple(
            dict.fromkeys(
                value
                for _, position in members
                for value in _tensile_precision_condition_values(facts[position])
            )
        )
        if not _tensile_bundle_conditions_internally_compatible(
            condition_values
        ):
            continue
        elongation_position = dict(members)["elongation"]
        evidence_unit_ids = tuple(
            sorted(
                {
                    str(facts[position].evidence_unit_id)
                    for _, position in members
                    if str(facts[position].evidence_unit_id or "").strip()
                }
            )
        )
        member_signatures = [
            _signature(facts[position].model_dump()) for _, position in members
        ]
        stable_key = json.dumps(
            {
                "owner": owner,
                "source_block": block.key,
                "members": member_signatures,
            },
            ensure_ascii=False,
            sort_keys=True,
        )
        bundles.append(
            _SameOwnerTensileBundle(
                owner=owner,
                members=members,
                evidence_key=block.key,
                evidence_text=block.text,
                evidence_unit_ids=evidence_unit_ids,
                condition_values=condition_values,
                elongation_subtype=_tensile_precision_subtype(
                    facts[elongation_position]
                ),
                role_nature=_tensile_precision_source_role(index, owner),
                binding_kind=block.kind,
                stable_key=stable_key,
            )
        )
    return sorted(bundles, key=lambda bundle: bundle.stable_key)


def _tensile_bundle_member_relation(
    loser: AxisFact,
    winner: AxisFact,
) -> dict[str, Any] | None:
    loser_shape = _tensile_bundle_value_shape(loser)
    winner_shape = _tensile_bundle_value_shape(winner)
    if loser_shape is None or winner_shape is None:
        return None
    loser_unit = _tensile_precision_unit_key(
        loser.data.get("unit_raw"), central=loser_shape["central"]
    )
    winner_unit = _tensile_precision_unit_key(
        winner.data.get("unit_raw"), central=winner_shape["central"]
    )
    if (
        loser_unit is None
        or winner_unit is None
        or loser_unit[0] != winner_unit[0]
    ):
        return None
    loser_central = float(loser_shape["central"]) * loser_unit[1]
    winner_central = float(winner_shape["central"]) * winner_unit[1]
    exact_central = abs(loser_central - winner_central) <= 1e-9
    rounded_central = _tensile_precision_rounded_values_compatible(
        loser_shape, winner_shape, loser_unit, winner_unit
    )
    if not exact_central and not rounded_central:
        return None
    if int(winner_shape["decimal_places"]) < int(
        loser_shape["decimal_places"]
    ):
        return None
    if bool(winner_shape["approximate"]) and not bool(
        loser_shape["approximate"]
    ):
        return None
    loser_uncertainty = loser_shape["uncertainty"]
    winner_uncertainty = winner_shape["uncertainty"]
    if loser_uncertainty is not None and winner_uncertainty is None:
        return None
    intervals_overlap = True
    if loser_uncertainty is not None and winner_uncertainty is not None:
        loser_uncertainty_canonical = float(loser_uncertainty) * loser_unit[1]
        winner_uncertainty_canonical = (
            float(winner_uncertainty) * winner_unit[1]
        )
        tolerance = max(
            1e-12,
            10.0 ** (-(int(loser_shape["decimal_places"]) + 8)),
        )
        intervals_overlap = max(
            loser_central - loser_uncertainty_canonical,
            winner_central - winner_uncertainty_canonical,
        ) <= min(
            loser_central + loser_uncertainty_canonical,
            winner_central + winner_uncertainty_canonical,
        ) + tolerance
        if not intervals_overlap:
            return None
        if int(winner_shape["uncertainty_decimal_places"]) < int(
            loser_shape["uncertainty_decimal_places"]
        ):
            return None
    precision_gains = {
        "approximation_removed": bool(
            loser_shape["approximate"] and not winner_shape["approximate"]
        ),
        "central_precision_added": bool(
            int(winner_shape["decimal_places"])
            > int(loser_shape["decimal_places"])
        ),
        "uncertainty_added": bool(
            winner_uncertainty is not None and loser_uncertainty is None
        ),
        "uncertainty_precision_added": bool(
            winner_uncertainty is not None
            and loser_uncertainty is not None
            and int(winner_shape["uncertainty_decimal_places"])
            > int(loser_shape["uncertainty_decimal_places"])
        ),
    }
    return {
        "compatible": True,
        "exact_central": exact_central,
        "literal_rounding": rounded_central,
        "canonical_unit": loser_unit[0],
        "loser_shape": loser_shape,
        "winner_shape": winner_shape,
        "uncertainty_intervals_overlap": intervals_overlap,
        "precision_gains": precision_gains,
        "strictly_better": any(precision_gains.values()),
    }


def _bundle_fact_dump(
    bundle: _SameOwnerTensileBundle,
    facts: Sequence[AxisFact],
    replacements: dict[int, AxisFact] | None = None,
) -> list[dict[str, Any]]:
    replacements = replacements or {}
    return [
        replacements.get(position, facts[position]).model_dump()
        for _, position in bundle.members
    ]


def _tensile_bundle_member_conditions_compatible(
    loser: AxisFact,
    winner: AxisFact,
    bundle: _SameOwnerTensileBundle,
) -> tuple[bool, dict[str, Any]]:
    loser_values = _tensile_precision_condition_values(loser)
    winner_values = tuple(
        dict.fromkeys(
            [
                *_tensile_precision_condition_values(winner),
                *bundle.condition_values,
            ]
        )
    )
    if loser_values and winner_values:
        compatible = bool(
            all(
                any(
                    _tensile_precision_conditions_compatible(left, right)
                    for right in winner_values
                )
                for left in loser_values
            )
            and all(
                any(
                    _tensile_precision_conditions_compatible(left, right)
                    for left in loser_values
                )
                for right in winner_values
            )
        )
        return compatible, {
            "rule": "explicit_condition_equivalence",
            "loser": list(loser_values),
            "survivor": list(winner_values),
        }
    if not loser_values and not winner_values:
        return True, {
            "rule": "both_conditions_absent",
            "loser": [],
            "survivor": [],
        }
    loser_evidence = {
        _literal_match_key(row)
        for row in loser.source_evidence
        if len(_literal_match_key(row)) >= 16
    }
    winner_evidence = {
        _literal_match_key(row)
        for row in winner.source_evidence
        if len(_literal_match_key(row)) >= 16
    }
    block_key = _literal_match_key(bundle.evidence_text)
    source_link = bool(
        loser.evidence_unit_id
        and winner.evidence_unit_id
        and loser.evidence_unit_id == winner.evidence_unit_id
    ) or bool(
        any(
            key in block_key or block_key in key for key in loser_evidence
        )
        and any(
            key in block_key or block_key in key for key in winner_evidence
        )
    )
    return source_link, {
        "rule": (
            "one_sided_condition_with_same_source_block"
            if source_link
            else "one_sided_condition_without_source_link"
        ),
        "loser": list(loser_values),
        "survivor": list(winner_values),
    }


def _same_owner_tensile_bundle_member_relation(
    index: _IdentityIndex,
    loser: AxisFact,
    loser_owner: str,
    winner: AxisFact,
    bundle: _SameOwnerTensileBundle,
) -> dict[str, Any] | None:
    semantic = _core_tensile_semantic(loser)
    if (
        semantic not in _TENSILE_BUNDLE_SEMANTICS
        or loser_owner != bundle.owner
    ):
        return None
    if _core_tensile_semantic(winner) != semantic:
        return None
    if _tensile_precision_source_role(index, loser_owner) != bundle.role_nature:
        return None
    if semantic == "elongation" and (
        _tensile_precision_subtype(loser)
        != _tensile_precision_subtype(winner)
    ):
        return None
    conditions_compatible, condition_decision = (
        _tensile_bundle_member_conditions_compatible(loser, winner, bundle)
    )
    if not conditions_compatible:
        return None
    relation = _tensile_bundle_member_relation(loser, winner)
    if relation is None or not relation["strictly_better"]:
        return None
    return {
        "rule": "source_block_complete_bundle_member_precision_dominance",
        "condition_decision": condition_decision,
        "member_relation": relation,
    }


def _deduplicate_same_owner_complete_tensile_bundles(
    index: _IdentityIndex,
    facts: Sequence[AxisFact],
    source_text: str,
) -> tuple[list[AxisFact], list[MaterializeIssue]]:
    """Merge a single projection into one complete source-block survivor."""

    bundles = _same_owner_complete_tensile_bundles(index, facts, source_text)
    if not bundles:
        return list(facts), []
    routed = {id(fact): _group_route(index, fact) for fact in facts}
    survivor_positions = {
        position for bundle in bundles for _, position in bundle.members
    }
    projection_counts: Counter[tuple[Any, ...]] = Counter()
    projection_keys: dict[int, tuple[Any, ...]] = {}
    for position, fact in enumerate(facts):
        owners = routed[id(fact)]
        if position in survivor_positions or len(owners) != 1:
            continue
        key = _tensile_exact_duplicate_key(index, fact, owners[0])
        if key is not None:
            projection_keys[position] = key
            projection_counts[key] += 1
    selected: dict[int, tuple[int, int, dict[str, Any]]] = {}
    for loser_position, loser in enumerate(facts):
        if loser_position in survivor_positions:
            continue
        loser_evidence = {
            _normalized_literal(row)
            for row in loser.source_evidence
            if _normalized_literal(row)
        }
        # A record already consolidating several distinct source assertions is
        # no longer one member-level projection.  Preserve that multi-assertion
        # envelope: A1 can prove dominance for one copied assertion, but cannot
        # prove that every separately reported headline occurrence is merely
        # presentation noise.
        if (
            len(loser_evidence) != 1
            or projection_counts[projection_keys.get(loser_position, ())] > 1
        ):
            continue
        owners = routed[id(loser)]
        semantic = _core_tensile_semantic(loser)
        if (
            len(owners) != 1
            or semantic not in _TENSILE_BUNDLE_SEMANTICS
            or _tensile_bundle_value_shape(loser) is None
        ):
            continue
        options: list[tuple[int, int, dict[str, Any]]] = []
        for bundle_position, bundle in enumerate(bundles):
            winner_position = dict(bundle.members).get(semantic)
            if winner_position is None:
                continue
            relation = _same_owner_tensile_bundle_member_relation(
                index,
                loser,
                owners[0],
                facts[winner_position],
                bundle,
            )
            if relation is not None:
                options.append((bundle_position, winner_position, relation))
        unique_options: dict[str, tuple[int, int, dict[str, Any]]] = {}
        for option in options:
            bundle = bundles[option[0]]
            key = json.dumps(
                {
                    "bundle": bundle.stable_key,
                    "winner": _signature(facts[option[1]].model_dump()),
                },
                ensure_ascii=False,
                sort_keys=True,
            )
            unique_options.setdefault(key, option)
        if len(unique_options) == 1:
            selected[loser_position] = next(iter(unique_options.values()))

    replacements: dict[int, AxisFact] = {}
    removed_positions: set[int] = set()
    issues: list[MaterializeIssue] = []
    ordered_selected = sorted(
        selected.items(),
        key=lambda row: json.dumps(
            facts[row[0]].model_dump(), ensure_ascii=False, sort_keys=True
        ),
    )
    for loser_position, (
        winner_bundle_position,
        winner_position,
        relation,
    ) in ordered_selected:
        winner_bundle = bundles[winner_bundle_position]
        if (
            loser_position in removed_positions
            or winner_position in removed_positions
        ):
            continue
        survivor_before = _bundle_fact_dump(winner_bundle, facts, replacements)
        removed = facts[loser_position]
        survivor = replacements.get(winner_position, facts[winner_position])
        replacements[winner_position] = _merge_tensile_precision_envelope(
            survivor, removed
        )
        removed_positions.add(loser_position)
        survivor_after = _bundle_fact_dump(winner_bundle, facts, replacements)
        owner_label = index.display_label(winner_bundle.owner)
        selected_semantic = _core_tensile_semantic(removed)
        issues.append(
            MaterializeIssue(
                code="tensile_same_owner_bundle_member_duplicate_merged",
                sample_id_raw=owner_label,
                path=f"items.{owner_label}.Extracted_Data.Properties",
                message=(
                    "A single same-owner core-tensile projection was merged "
                    "into one uniquely richer member of a source-proven "
                    "complete YS/UTS/elongation bundle."
                ),
                evidence={
                    "loser_source_evidence": list(removed.source_evidence),
                    "survivor_source_binding": {
                        "kind": winner_bundle.binding_kind,
                        "source_block_key": winner_bundle.evidence_key,
                        "evidence": winner_bundle.evidence_text,
                        "evidence_unit_ids": list(winner_bundle.evidence_unit_ids),
                    },
                },
                expected={
                    "rule": relation["rule"],
                    "same_unique_canonical_owner": True,
                    "complete_semantics": list(_TENSILE_BUNDLE_SEMANTICS),
                    "single_member_removal": True,
                    "unique_complete_survivor": True,
                },
                actual={
                    "canonical_owner": owner_label,
                    "role_nature": list(winner_bundle.role_nature),
                    "elongation_subtype": winner_bundle.elongation_subtype,
                    "bundle_conditions": list(winner_bundle.condition_values),
                    "selected_semantic": selected_semantic,
                    "condition_decision": relation["condition_decision"],
                    "member_relation": relation["member_relation"],
                    "removed_fact": removed.model_dump(),
                    "survivor_bundle_before_merge": survivor_before,
                    "survivor_bundle_after_merge": survivor_after,
                    "deterministic_survivor_key": winner_bundle.stable_key,
                    "deterministic_loser_key": json.dumps(
                        removed.model_dump(), ensure_ascii=False, sort_keys=True
                    ),
                    "protection_gates": {
                        "cross_owner": False,
                        "condition_conflict": False,
                        "role_nature_conflict": False,
                        "elongation_subtype_conflict": False,
                        "range_relative_threshold": False,
                        "non_unique_survivor": False,
                    },
                },
                suggested_action=(
                    "Review the preserved source block and removed projection "
                    "if they represent independent tests rather than one result."
                ),
            )
        )
    return [
        replacements.get(position, fact)
        for position, fact in enumerate(facts)
        if position not in removed_positions
    ], issues


def _tensile_exact_duplicate_key(
    index: _IdentityIndex, fact: AxisFact, owner: str
) -> tuple[Any, ...] | None:
    """Return one exact scientific tensile identity without presentation fields."""

    shape = _tensile_precision_value_shape(fact)
    if shape is None or shape["approximate"]:
        return None
    unit = _tensile_precision_unit_key(
        fact.data.get("unit_raw"), central=shape["central"]
    )
    if unit is None:
        return None
    uncertainty = shape["uncertainty"]
    return (
        owner,
        _core_tensile_semantic(fact),
        round(shape["central"] * unit[1], 12),
        (
            None
            if uncertainty is None
            else round(float(uncertainty) * unit[1], 12)
        ),
        unit[0],
        _tensile_precision_subtype(fact),
        _tensile_precision_source_role(index, owner),
    )


def _tensile_exact_conditions_compatible(
    left: AxisFact, right: AxisFact
) -> bool:
    left_conditions = _tensile_precision_condition_values(left)
    right_conditions = _tensile_precision_condition_values(right)
    if not left_conditions or not right_conditions:
        return True
    return any(
        _tensile_precision_conditions_compatible(left_value, right_value)
        for left_value in left_conditions
        for right_value in right_conditions
    )


def _tensile_exact_survivor_rank(fact: AxisFact) -> tuple[Any, ...]:
    source = str(fact.data.get("data_source") or "").strip().casefold()
    source_rank = {"table": 3, "text": 2, "unknown": 1, "": 0}.get(
        source, 0
    )
    conditions = _tensile_precision_condition_values(fact)
    return (
        int(_tensile_precision_complete_table(fact) is not None),
        max((len(_tensile_precision_condition_key(row)) for row in conditions), default=0),
        source_rank,
        len(fact.source_evidence),
        _signature(fact.model_dump()),
    )


def _deduplicate_exact_tensile_projections(
    index: _IdentityIndex,
    facts: Sequence[AxisFact],
) -> tuple[list[AxisFact], list[MaterializeIssue]]:
    """Merge exact same-owner tensile claims emitted with different wording."""

    routed = {id(fact): _group_route(index, fact) for fact in facts}
    keys: dict[int, tuple[Any, ...] | None] = {}
    ranks: dict[int, tuple[Any, ...]] = {}
    for position, fact in enumerate(facts):
        owners = routed[id(fact)]
        keys[position] = (
            _tensile_exact_duplicate_key(index, fact, owners[0])
            if len(owners) == 1
            else None
        )
        ranks[position] = _tensile_exact_survivor_rank(fact)

    selected: dict[int, int] = {}
    for loser_position, loser in enumerate(facts):
        key = keys[loser_position]
        if key is None:
            continue
        options = [
            winner_position
            for winner_position, winner in enumerate(facts)
            if winner_position != loser_position
            and keys[winner_position] == key
            and _tensile_exact_conditions_compatible(loser, winner)
            and ranks[winner_position] > ranks[loser_position]
        ]
        if options:
            selected[loser_position] = max(
                options, key=lambda position: ranks[position]
            )

    # Do not follow a transitive chain through a record that is itself removed.
    for loser_position, winner_position in list(selected.items()):
        if winner_position in selected:
            selected.pop(loser_position, None)

    replacements: dict[int, AxisFact] = {}
    removed_positions: set[int] = set()
    issues: list[MaterializeIssue] = []
    for loser_position, winner_position in sorted(selected.items()):
        if loser_position in removed_positions or winner_position in removed_positions:
            continue
        removed = facts[loser_position]
        survivor = replacements.get(winner_position, facts[winner_position])
        before = survivor.model_dump()
        survivor = _merge_tensile_precision_envelope(survivor, removed)
        replacements[winner_position] = survivor
        removed_positions.add(loser_position)
        winner_owner = routed[id(facts[winner_position])][0]
        issues.append(
            MaterializeIssue(
                code="tensile_exact_duplicate_merged",
                sample_id_raw=index.display_label(winner_owner),
                path=(
                    f"items.{index.display_label(winner_owner)}."
                    "Extracted_Data.Properties"
                ),
                message=(
                    "An exact same-owner core-tensile claim was merged while "
                    "preserving all distinct evidence."
                ),
                evidence={
                    "loser_evidence": list(removed.source_evidence),
                    "winner_evidence": list(survivor.source_evidence),
                },
                expected={
                    "rule": "exact_semantic_value_unit_uncertainty_owner",
                    "compatible_conditions": True,
                    "same_subtype": True,
                },
                actual={
                    "exact_key": list(keys[loser_position] or ()),
                    "loser_conditions": list(
                        _tensile_precision_condition_values(removed)
                    ),
                    "winner_conditions": list(
                        _tensile_precision_condition_values(survivor)
                    ),
                    "removed_fact": removed.model_dump(),
                    "survivor_before_merge": before,
                    "survivor_after_merge": survivor.model_dump(),
                },
                suggested_action=(
                    "Review only if the identical claims represent separate "
                    "replicates that must remain independently enumerated."
                ),
            )
        )
    return [
        replacements.get(position, fact)
        for position, fact in enumerate(facts)
        if position not in removed_positions
    ], issues


def _deduplicate_unresolved_tensile_bundle_projections(
    index: _IdentityIndex,
    facts: Sequence[AxisFact],
    source_text: str,
) -> tuple[list[AxisFact], list[MaterializeIssue]]:
    """Drop a generic tensile projection already owned by one resolved sibling."""

    routed = {id(fact): _group_route(index, fact) for fact in facts}
    replacements: dict[int, AxisFact] = {}
    removed: set[int] = set()
    issues: list[MaterializeIssue] = []
    for loser_position, loser in enumerate(facts):
        if (
            not _numeric_core_tensile_fact(loser)
            or routed[id(loser)]
            or _fact_is_blocked_tensile_result(loser)
        ):
            continue
        loser_condition = str(loser.data.get("test_condition_raw") or "").strip()
        candidates: list[tuple[int, AxisFact, str]] = []
        for winner_position, winner in enumerate(facts):
            if winner is loser or len(routed[id(winner)]) != 1:
                continue
            if _core_tensile_value_key(winner) != _core_tensile_value_key(loser):
                continue
            if loser_condition and (
                _normalized_literal(loser_condition)
                != _normalized_literal(winner.data.get("test_condition_raw"))
            ):
                continue
            shares_block, _ = _facts_share_source_assertion_block(
                source_text, loser, winner
            )
            if not _facts_share_evidence_bundle(loser, winner) and not shares_block:
                continue
            candidates.append((winner_position, winner, routed[id(winner)][0]))
        owners = {owner for _, _, owner in candidates}
        if len(owners) != 1 or not candidates:
            continue
        winner_position, winner, winner_owner = candidates[0]
        survivor = replacements.get(winner_position, winner)
        survivor_before = survivor.model_dump()
        survivor = _merge_fact_envelope_evidence(survivor, loser)
        replacements[winner_position] = survivor
        removed.add(loser_position)
        fingerprint = json.dumps(
            _core_tensile_value_key(loser), ensure_ascii=False, default=str
        )
        issues.append(
            MaterializeIssue(
                code="cross_item_duplicate_merged",
                sample_id_raw=index.display_label(winner_owner),
                path=(
                    f"items.{index.display_label(winner_owner)}.Extracted_Data.Properties"
                ),
                message=(
                    "A generic tensile projection was merged into the same source "
                    "claim already owned by one resolved material/state."
                ),
                evidence={
                    "generic_evidence": list(loser.source_evidence),
                    "owner_evidence": list(winner.source_evidence),
                },
                expected={
                    "duplicate_fingerprint": fingerprint,
                    "resolved_owner_count": 1,
                },
                actual={
                    "before_owner": loser.sample_id_raw,
                    "after_owner": index.display_label(winner_owner),
                    "rule": "resolved_owner_over_generic_bundle_projection",
                    "fingerprint": fingerprint,
                    "removed_fact": loser.model_dump(),
                    "survivor_before_merge": survivor_before,
                    "survivor_after_merge": survivor.model_dump(),
                },
                suggested_action=(
                    "Review only if the generic quote reports a distinct test "
                    "condition or material owner."
                ),
            )
        )
    return [
        replacements.get(position, fact)
        for position, fact in enumerate(facts)
        if position not in removed
    ], issues


def _source_markdown_table_blocks(
    source_text: str,
) -> tuple[tuple[str, tuple[str, ...]], ...]:
    """Return contiguous source Markdown table rows with literal cells."""

    blocks: list[list[tuple[str, tuple[str, ...]]]] = []
    current: list[tuple[str, tuple[str, ...]]] = []
    for raw_line in str(source_text or "").splitlines():
        line = raw_line.strip()
        cells = _markdown_table_cells(line)
        if cells and line.count("|") >= 3:
            current.append((line, tuple(cells)))
            continue
        if current:
            blocks.append(current)
            current = []
    if current:
        blocks.append(current)
    return tuple(row for block in blocks for row in block)


def _source_table_owner_targets(
    index: _IdentityIndex, cell: str
) -> tuple[str, ...]:
    """Resolve one table header cell to existing inventory owners only."""

    key = normalize_source_alias(cell)
    if not key or re.fullmatch(r"[-: ]+", key):
        return ()
    targets: set[str] = set()
    for canonical in index.anchors:
        for label in _owner_presentation_variants(index, canonical):
            if normalize_source_alias(label) == key:
                targets.add(canonical)
                break
    return tuple(sorted(targets))


def _source_table_core_semantic(cell: str) -> str | None:
    folded = unicodedata.normalize("NFKC", str(cell or "")).casefold()
    if re.search(r"(?i)\b(?:yield\s+(?:strength|stress)|YS(?:\b|[_.]))", folded):
        return "yield_strength"
    if re.search(
        r"(?i)\b(?:ultimate\s+tensile\s+strength|tensile\s+strength|UTS)\b",
        folded,
    ):
        return "ultimate_tensile_strength"
    if re.search(r"(?i)\b(?:elongation|ductility)\b", folded):
        return "elongation"
    return None


def _rounded_table_value_matches(value_raw: Any, cell: Any) -> bool:
    """Accept one source-reported integer rounded from a precise table mean."""

    if _table_value_cell_matches(value_raw, cell):
        return True
    raw = unicodedata.normalize("NFKC", str(value_raw or "")).strip()
    expected = _numeric_cell_signature(raw)
    observed = _numeric_cell_signature(cell)
    if len(expected) != 1 or not observed or any(token in raw for token in ("±", "+/-", "–", "-")):
        return False
    if not re.fullmatch(r"[-+]?\d+(?:\.0+)?", raw):
        return False
    # A rounded prose headline should be within one displayed unit of the
    # table mean and the table must show a decimal/uncertainty presentation.
    observed_text = str(cell or "")
    if not ("±" in observed_text or "+/-" in observed_text or "." in observed_text):
        return False
    return abs(expected[0] - observed[0]) <= 1.0


def _source_table_value_owner(
    index: _IdentityIndex,
    fact: AxisFact,
    source_text: str,
) -> tuple[str, dict[str, Any]] | None:
    """Bind an unowned tensile value to one unique source table owner column.

    This is intentionally separate from the candidate's copied table rows:
    prose summaries often round a value and omit the owner, while the complete
    source table still carries the exact owner/value coordinate.  The rule
    accepts only one semantic row, one matching cell, and one existing owner.
    """

    if not isinstance(fact, PropertyFact):
        return None
    semantic = _core_tensile_semantic(fact)
    if not semantic:
        return None
    blocks: list[list[tuple[str, tuple[str, ...]]]] = []
    current: list[tuple[str, tuple[str, ...]]] = []
    for raw_line in str(source_text or "").splitlines():
        line = raw_line.strip()
        cells = _markdown_table_cells(line)
        if cells and line.count("|") >= 3:
            current.append((line, tuple(cells)))
            continue
        if current:
            blocks.append(current)
            current = []
    if current:
        blocks.append(current)

    matches: list[tuple[str, dict[str, Any]]] = []
    for rows in blocks:
        header_candidates: list[tuple[str, tuple[str, ...], dict[int, str]]] = []
        for header_row, header_cells in rows:
            owner_columns: dict[int, str] = {}
            for column, cell in enumerate(header_cells):
                targets = _source_table_owner_targets(index, cell)
                if len(targets) == 1:
                    owner_columns[column] = targets[0]
            if len(set(owner_columns.values())) >= 2:
                header_candidates.append((header_row, header_cells, owner_columns))
        for header_row, header_cells, owner_columns in header_candidates:
            for value_row, value_cells in rows:
                if value_row == header_row or len(value_cells) != len(header_cells):
                    continue
                row_semantic = _source_table_core_semantic(value_cells[0])
                if row_semantic != semantic:
                    continue
                for column, owner in owner_columns.items():
                    if column >= len(value_cells) or not _rounded_table_value_matches(
                        fact.data.get("value_raw"), value_cells[column]
                    ):
                        continue
                    matches.append(
                        (
                            owner,
                            {
                                "header_row": header_row,
                                "value_row": value_row,
                                "owner_cell": header_cells[column],
                                "value_cell": value_cells[column],
                                "owner_column": column,
                                "semantic": semantic,
                            },
                        )
                    )
    unique = {(owner, json.dumps(detail, ensure_ascii=False, sort_keys=True)) for owner, detail in matches}
    if len({owner for owner, _ in unique}) != 1 or len(unique) != 1:
        return None
    owner, detail_json = next(iter(unique))
    return owner, json.loads(detail_json)


_TABLE_LABEL_STOPWORDS = {
    "a",
    "an",
    "and",
    "at",
    "by",
    "for",
    "of",
    "the",
    "to",
    "value",
    "values",
    "property",
    "properties",
    "parameter",
    "parameters",
    "mpa",
    "gpa",
    "pa",
    "ksi",
    "percent",
    "pct",
    "wt",
    "at",
    "vol",
    "mol",
}


def _table_label_tokens(value: Any) -> set[str]:
    """Return presentation-neutral tokens for one table/property label."""

    text = unicodedata.normalize("NFKC", str(value or "")).casefold()
    text = re.sub(
        r"\\(?:mathrm|text|operatorname|mathbf|mathit)\s*\{([^{}]*)\}",
        r"\1",
        text,
        flags=re.IGNORECASE,
    )
    text = text.replace("\\", " ")
    text = text.replace("δ", "delta").replace("Δ", "delta")
    tokens = {
        token
        for token in re.findall(r"[a-z0-9]+", text)
        if token not in _TABLE_LABEL_STOPWORDS
    }
    return tokens


def _table_property_label_matches(property_name: Any, row_label: Any) -> bool:
    """Match a property label to a source-table row without ontology guesses."""

    left = _table_label_tokens(property_name)
    right = _table_label_tokens(row_label)
    if not left or not right:
        return False
    if left <= right or right <= left:
        return True
    overlap = len(left & right)
    return overlap >= 2 and overlap / max(len(left), len(right)) >= 0.6


def _source_table_generic_property_binding(
    index: _IdentityIndex, fact: AxisFact
) -> dict[str, Any] | None:
    """Bind one table property to a unique owner/value coordinate.

    Unlike the tensile-only binding, this helper deliberately does not infer a
    canonical property ontology.  It only uses the candidate's raw property
    label, one complete table row, one owner column, and one literal value cell.
    """

    if not isinstance(fact, PropertyFact):
        return None
    source = str(fact.data.get("data_source") or "").strip().casefold()
    if source not in {"table", "unknown", ""}:
        return None
    property_name = fact.data.get("property_name_raw")
    rows = _fact_markdown_table_rows(fact)
    if len(rows) < 2 or not _table_label_tokens(property_name):
        return None
    candidates: list[dict[str, Any]] = []
    value_raw = fact.data.get("value_raw")
    for header_row, header_cells in rows:
        owner_columns: dict[int, str] = {}
        for column, cell in enumerate(header_cells):
            targets = _source_table_owner_targets(index, cell)
            if len(targets) == 1:
                owner_columns[column] = targets[0]
        if len(set(owner_columns.values())) < 2:
            continue
        for value_row, value_cells in rows:
            if value_row == header_row or len(value_cells) != len(header_cells):
                continue
            row_labels = [
                cell
                for column, cell in enumerate(value_cells)
                if column not in owner_columns
            ]
            if not any(
                _table_property_label_matches(property_name, label)
                for label in row_labels
            ):
                continue
            for column, owner in owner_columns.items():
                cell = value_cells[column]
                numeric_match = _table_value_cell_matches(value_raw, cell)
                textual_match = (
                    not _numeric_cell_signature(value_raw)
                    and normalize_source_alias(value_raw)
                    == normalize_source_alias(_cell_without_reference_markers(cell))
                )
                if not (numeric_match or textual_match):
                    continue
                candidates.append(
                    {
                        "owner": owner,
                        "header_row": header_row,
                        "value_row": value_row,
                        "owner_cell": header_cells[column],
                        "value_cell": cell,
                        "owner_column": column,
                        "property_name_raw": property_name,
                    }
                )
    unique: dict[str, dict[str, Any]] = {}
    for candidate in candidates:
        signature = json.dumps(candidate, ensure_ascii=False, sort_keys=True)
        unique.setdefault(signature, candidate)
    if len(unique) != 1:
        return None
    return next(iter(unique.values()))


def _fact_is_reference_owned(
    index: _IdentityIndex,
    fact: AxisFact,
    owners: Sequence[str],
) -> bool:
    """Return whether a fact is already bound to an independent Reference item.

    The generic table-owner recovery pass works from the literal table header
    (``Wrought``) and therefore cannot distinguish a cited comparison column
    from the current-study Target with the same base label.  Once an earlier
    citation pass has moved the fact to an explicit ``[reference]`` owner, or
    when its routed owner is already marked ``Reference``, that fact is a
    stronger coordinate than the generic header.  Do not route it back to the
    Target; doing so creates the exact target/reference duplicate this pass is
    meant to prevent.
    """

    if re.search(r"(?i)\[\s*reference\s*\]\s*$", str(fact.sample_id_raw or "")):
        return True
    for owner in owners:
        if any(
            str(anchor.role or "").strip().casefold() == "reference"
            for anchor in index.anchors.get(owner, [])
        ):
            return True
    return False


def _fact_is_reference_table_coordinate(
    index: _IdentityIndex,
    fact: AxisFact,
    owners: Sequence[str],
) -> bool:
    """Return whether a cited table Property is already reference-bound.

    The shared-owner projection pass is intentionally conservative for prose,
    but a fact that has both an explicit Reference owner and a unique cited
    table coordinate is already source-bound.  Applying the prose projection
    quarantine to it would discard a valid reference fact because the table
    row necessarily names the base header (for example ``Wrought``) instead
    of the generated ``Wrought [37] [reference]`` presentation.
    """

    if not _fact_is_reference_owned(index, fact, owners):
        return False
    if _cited_property_table_binding(fact) is not None:
        return True
    # After the fact-level recovery the generated ``[reference]`` suffix no
    # longer literally matches the base table header, so the tensile/property
    # citation binders cannot always rediscover the coordinate.  Reuse the
    # generic value-cell match and require its own citation/standard marker;
    # this remains one-to-one and does not turn arbitrary reference prose into
    # an exempt fact.
    binding = _source_table_generic_property_binding(index, fact)
    if binding is None:
        return False
    marker = _one_reference_marker(
        ("value_cell", binding["value_cell"]),
        ("owner_cell", binding["owner_cell"]),
    )
    return marker is not None and not _REFERENCE_CURRENT_STUDY.search(
        f"{binding['owner_cell']} {binding['value_cell']}"
    )


def _evidence_names_owner(
    index: _IdentityIndex, owner: str, evidence: Sequence[str]
) -> bool:
    """Return whether one copied evidence span literally names an owner."""

    labels = _owner_presentation_variants(index, owner)
    return any(
        _source_label_occurs_in_row(label, row)
        for label in labels
        for row in evidence
    )


def _evidence_rows_share_assertion(left: Any, right: Any) -> bool:
    """Return whether two copied evidence rows are the same assertion.

    Chunk projections are not guaranteed to preserve the exact quote envelope:
    one response may contain a sentence, while another contains that sentence
    plus a short continuation (or a line-break variant).  Exact evidence keys
    therefore miss a common cross-chunk projection.  This helper is deliberately
    conservative: short rows are ignored, and a high token overlap or literal
    containment is required before treating two rows as one assertion.
    """

    left_text = " ".join(str(left or "").split()).strip()
    right_text = " ".join(str(right or "").split()).strip()
    if not left_text or not right_text:
        return False
    left_key = _normalized_literal(left_text)
    right_key = _normalized_literal(right_text)
    if min(len(left_key), len(right_key)) < 32:
        return False
    if left_key in right_key or right_key in left_key:
        return True
    left_tokens = set(re.findall(r"[a-z0-9]+", left_key))
    right_tokens = set(re.findall(r"[a-z0-9]+", right_key))
    if len(left_tokens) < 6 or len(right_tokens) < 6:
        return False
    overlap = len(left_tokens & right_tokens)
    return overlap >= 6 and overlap / min(len(left_tokens), len(right_tokens)) >= 0.90


def _shared_projection_evidence_key(fact: AxisFact) -> tuple[str, ...]:
    return tuple(
        sorted(
            {
                _normalized_literal(row)
                for row in fact.source_evidence
                if _normalized_literal(row)
            }
        )
    )


def _processing_table_coordinate_signature(fact: AxisFact) -> dict[str, set[str]]:
    """Return parameter/value coordinates carried by one processing fact.

    Alpha25 task chunks often copy only the body rows of a Markdown table into
    ``source_evidence`` while retaining the table column owner in
    ``sample_id_raw``.  The generic cross-owner projection gate cannot see the
    omitted header, but the structured parameter payload still contains a
    deterministic coordinate: one owner has (for example) 1000 bar/1120 °C
    and its sibling has 1500 bar/1180 °C.  Keep that coordinate available for
    the narrow table-owner exemption below.
    """

    if fact.fact_type != "process_stage":
        return {}
    evidence = [str(row or "").strip() for row in fact.source_evidence]
    if not any(row.startswith("|") and row.count("|") >= 3 for row in evidence):
        return {}
    parameters = fact.data.get("parameters_raw") or []
    signature: dict[str, set[str]] = {}
    for parameter in parameters:
        if not isinstance(parameter, dict):
            continue
        name = normalize_source_alias(parameter.get("parameter_name_raw"))
        value = normalize_source_alias(parameter.get("value_raw"))
        if not name or not value or _is_unresolved_alias(value):
            continue
        signature.setdefault(name, set()).add(value)
    return signature


def _processing_table_coordinate_group(
    rows: Sequence[tuple[int, AxisFact, tuple[str, ...]]]
) -> bool:
    """Return whether a shared processing-table group has distinct owner values."""

    owner_signatures: dict[str, dict[str, set[str]]] = {}
    for _, fact, owners in rows:
        if len(owners) != 1:
            continue
        signature = _processing_table_coordinate_signature(fact)
        if signature:
            owner_signatures[owners[0]] = signature
    if len(owner_signatures) < 2:
        return False
    parameter_names = set().union(
        *(signature.keys() for signature in owner_signatures.values())
    )
    # At least one parameter must differ by owner.  This avoids exempting two
    # copied prose rows that happen to be typed as process stages, while still
    # retaining the full row bundle (including equal values such as 4 h) once
    # one column value proves the owner coordinate.
    return any(
        len(
            {
                tuple(sorted(owner_signatures[owner].get(name, set())))
                for owner in owner_signatures
            }
        ) > 1
        for name in parameter_names
    )


_MULTI_OWNER_EXPLICIT_MAPPING = re.compile(
    r"(?i)\b(?:respectively|both|each|all|either|corresponding|"
    r"same\s+(?:for|in)|one\s+for\s+each)\b"
)
_COMPARATIVE_OWNER_PROSE = re.compile(
    r"(?i)\b(?:compared\s+(?:with|to)|than|higher|lower|greater|less|"
    r"more|fewer|similar|different|whereas|while|versus|vs\.?|relative\s+to)\b"
)


def _fact_is_qualitative_structure_or_characterization(fact: AxisFact) -> bool:
    """Return whether a fact has no value coordinate beyond a prose assertion."""

    if fact.fact_type == "characterization":
        return True
    if fact.fact_type != "structure_observation":
        return False
    data = fact.data
    features = [
        feature
        for feature in data.get("features") or []
        if isinstance(feature, dict)
    ]
    for entity in data.get("entities") or []:
        if not isinstance(entity, dict):
            continue
        features.extend(
            feature
            for feature in entity.get("features") or []
            if isinstance(feature, dict)
        )
    # Presence-only entities and text-only features are especially prone to
    # being copied from comparison sentences. Numeric/range values have a
    # stronger source coordinate and are handled by the table/evidence gates.
    return not any(
        str(feature.get("value_kind") or "").casefold()
        in {"scalar", "range", "inequality"}
        or bool(re.search(r"(?<![A-Za-z])[-+]?\d+(?:\.\d+)?\s*(?:%|nm|μm|um|mm|gpa|mpa|pa|°c)", str(feature.get("value_raw") or ""), re.I))
        for feature in features
    )


def _multi_owner_projection_is_ambiguous(
    index: _IdentityIndex,
    fact: AxisFact,
    owner: str,
    evidence: Sequence[str],
) -> bool:
    """Reject qualitative facts copied from a multi-owner comparison sentence.

    A quote can mention two samples while reporting an observation for only one
    of them (``X ... than Y``).  The previous owner gate treated the mere
    presence of the owner token as sufficient and therefore projected the same
    prose observation onto both items.  Keep explicit table rows and
    ``respectively``/``both`` mappings; isolate the remaining qualitative
    multi-owner assertions for review.
    """

    if not _fact_is_qualitative_structure_or_characterization(fact):
        return False
    text = "\n".join(str(row or "") for row in evidence)
    if _MULTI_OWNER_EXPLICIT_MAPPING.search(text):
        return False
    # A Markdown row with one literal owner cell is a deterministic coordinate,
    # even when the surrounding header or caption names other samples.
    for row in evidence:
        if not (str(row).strip().startswith("|") and str(row).count("|") >= 3):
            continue
        cells = _markdown_table_cells(row)
        if sum(_table_owner_cell_matches(index.display_label(owner), cell) for cell in cells) == 1:
            return False
    named = {
        canonical
        for canonical in index.anchors
        if any(
            _source_label_occurs_in_row(index.display_label(canonical), row)
            for row in evidence
        )
    }
    if len(named) < 2:
        return False
    # A comparison cue is a strong signal that the sentence is relational, not
    # an owner-specific observation.  Without that cue, multiple owners may
    # still be jointly asserted by a sentence; preserve it conservatively.
    return bool(_COMPARATIVE_OWNER_PROSE.search(text))


def _quarantine_shared_owner_projections(
    index: _IdentityIndex,
    facts: Sequence[AxisFact],
) -> tuple[list[AxisFact], list[MaterializeIssue]]:
    """Isolate generic prose copied to several owners without a coordinate.

    Exact owner-bearing table cells and explicit ``respectively`` mappings are
    retained.  The conservative quarantine applies only when the same evidence
    envelope is copied to multiple owners and the envelope does not name the
    current owner; this prevents cross-chunk context sentences from becoming
    owner-specific scientific facts.
    """

    routed = {id(fact): _group_route(index, fact) for fact in facts}
    replacements: dict[int, AxisFact] = {}
    issues: list[MaterializeIssue] = []

    # First repair generic table properties when one value has one unique owner
    # column.  Existing tensile-specific recovery remains authoritative for core
    # tensile rows and is intentionally not replaced here.
    for position, fact in enumerate(facts):
        owners = routed[id(fact)]
        if (
            len(owners) != 1
            or _core_tensile_semantic(fact)
            or _fact_is_reference_owned(index, fact, owners)
        ):
            continue
        binding = _source_table_generic_property_binding(index, fact)
        if binding is None or binding["owner"] == owners[0]:
            continue
        before = fact.model_dump()
        after_owner = binding["owner"]
        repaired = fact.model_copy(update={"sample_id_raw": index.display_label(after_owner)})
        replacements[position] = repaired
        routed[id(repaired)] = (after_owner,)
        issues.append(
            MaterializeIssue(
                code="source_table_generic_owner_recovered",
                sample_id_raw=index.display_label(after_owner),
                path=f"items.{index.display_label(after_owner)}.Extracted_Data.Properties",
                message=(
                    "A non-tensile table property was moved to the only owner "
                    "column containing its literal value cell."
                ),
                evidence={"source_table_binding": binding, "fact_evidence": list(fact.source_evidence)},
                expected={"owner": "one unique source-table owner/value coordinate"},
                actual={"before_owner": fact.sample_id_raw, "after_owner": index.display_label(after_owner), "fact": before},
                suggested_action="Review only if the table uses a non-literal multi-level header.",
            )
        )

    effective = [replacements.get(position, fact) for position, fact in enumerate(facts)]
    routed = {id(fact): _group_route(index, fact) for fact in effective}
    groups: dict[tuple[str, ...], list[tuple[int, AxisFact, tuple[str, ...]]]] = {}
    for position, fact in enumerate(effective):
        owners = routed[id(fact)]
        if (
            len(owners) != 1
            or _fact_has_table_coordinate(fact)
            or _fact_is_reference_table_coordinate(index, fact, owners)
        ):
            continue
        key = _shared_projection_evidence_key(fact)
        if key:
            groups.setdefault(key, []).append((position, fact, owners))

    removed: set[int] = set()
    # Apply the comparison-owner gate even when the two chunks contain slightly
    # different evidence envelopes.  Waiting for an exact shared-envelope key
    # would miss the common case where one chunk includes the caption and the
    # other includes the sentence continuation.
    for position, fact in enumerate(effective):
        owners = routed[id(fact)]
        if (
            len(owners) != 1
            or _core_tensile_semantic(fact)
            or _fact_has_table_coordinate(fact)
            or _fact_is_reference_table_coordinate(index, fact, owners)
        ):
            continue
        owner = owners[0]
        evidence = list(fact.source_evidence)
        if not _multi_owner_projection_is_ambiguous(index, fact, owner, evidence):
            continue
        removed.add(position)
        issues.append(
            MaterializeIssue(
                code="multi_owner_qualitative_projection_quarantined",
                sample_id_raw=index.display_label(owner),
                path=f"items.{index.display_label(owner)}.Extracted_Data",
                message=(
                    "A qualitative structure/characterization assertion was "
                    "isolated because its evidence compares multiple owners "
                    "without an explicit owner mapping."
                ),
                evidence={
                    "shared_evidence": evidence,
                    "owners": [
                        index.display_label(canonical)
                        for canonical in index.anchors
                        if any(
                            _source_label_occurs_in_row(
                                index.display_label(canonical), row
                            )
                            for row in evidence
                        )
                    ],
                },
                expected={
                    "owner_binding": (
                        "one owner, explicit respectively/both mapping, or "
                        "unique table row"
                    )
                },
                actual={"fact": fact.model_dump(), "owner": index.display_label(owner)},
                suggested_action=(
                    "Restore only when the source explicitly states that the "
                    "observation applies to this owner."
                ),
            )
        )
    for key, rows in groups.items():
        owner_keys = {owners[0] for _, _, owners in rows}
        if len(owner_keys) < 2:
            continue
        if _processing_table_coordinate_group(rows):
            # The evidence envelope contains table body rows, while each
            # structured process fact carries a distinct owner/value column.
            # This is a valid source coordinate, not a copied prose projection.
            continue
        evidence = list(key)
        if any("respectively" in row.casefold() for row in evidence):
            # Ordered owner/value prose is a source coordinate when the scalar
            # value is explicit; do not destroy valid list-to-owner mappings.
            continue
        for position, fact, owners in rows:
            if position in removed:
                continue
            owner = owners[0]
            if _multi_owner_projection_is_ambiguous(
                index, fact, owner, evidence
            ):
                removed.add(position)
                issues.append(
                    MaterializeIssue(
                        code="multi_owner_qualitative_projection_quarantined",
                        sample_id_raw=index.display_label(owner),
                        path=f"items.{index.display_label(owner)}.Extracted_Data",
                        message=(
                            "A qualitative structure/characterization assertion was "
                            "isolated because its evidence compares multiple owners "
                            "without an explicit owner mapping."
                        ),
                        evidence={
                            "shared_evidence": evidence,
                            "owners": [
                                index.display_label(row_owner)
                                for row_owner in sorted(owner_keys)
                            ],
                        },
                        expected={
                            "owner_binding": (
                                "one owner, explicit respectively/both mapping, "
                                "or unique table row"
                            )
                        },
                        actual={
                            "fact": fact.model_dump(),
                            "owner": index.display_label(owner),
                        },
                        suggested_action=(
                            "Restore only when the source explicitly states that "
                            "the observation applies to this owner."
                        ),
                    )
                )
                continue
            if _evidence_names_owner(index, owner, evidence):
                continue
            if _core_tensile_semantic(fact):
                # Existing tensile bundle/relation rules protect explicit
                # multi-owner assertions and should remain the sole authority.
                continue
            removed.add(position)
            issues.append(
                MaterializeIssue(
                    code="shared_owner_projection_quarantined",
                    sample_id_raw=index.display_label(owner),
                    path=f"items.{index.display_label(owner)}.Extracted_Data",
                    message=(
                        "A fact copied from one shared evidence span was isolated "
                        "because that span does not name this owner or provide a "
                        "unique source coordinate."
                    ),
                    evidence={"shared_evidence": evidence, "owners": [index.display_label(row_owner) for row_owner in sorted(owner_keys)]},
                    expected={"owner_binding": "literal owner mention or unique table/respectively coordinate"},
                    actual={"fact": fact.model_dump(), "owner": index.display_label(owner)},
                    suggested_action=(
                        "Review the source span and restore only when it explicitly "
                        "reports an owner-specific value or observation."
                    ),
                )
            )

    # A second pass catches the same projection when chunk boundaries changed
    # the copied evidence envelope slightly.  Only facts of the same type are
    # compared; explicit owner-bearing and ``respectively`` evidence remains
    # authoritative and is never quarantined here.
    for left_position, left_fact in enumerate(effective):
        if left_position in removed:
            continue
        left_owners = routed[id(left_fact)]
        if (
            len(left_owners) != 1
            or _core_tensile_semantic(left_fact)
            or _fact_has_table_coordinate(left_fact)
            or _fact_is_reference_table_coordinate(index, left_fact, left_owners)
        ):
            continue
        left_owner = left_owners[0]
        left_evidence = list(left_fact.source_evidence)
        if not left_evidence:
            continue
        if any("respectively" in row.casefold() for row in left_evidence):
            continue
        left_ambiguous = _multi_owner_projection_is_ambiguous(
            index, left_fact, left_owner, left_evidence
        )
        if not left_ambiguous and _evidence_names_owner(
            index, left_owner, left_evidence
        ):
            continue
        for right_position in range(left_position + 1, len(effective)):
            if right_position in removed:
                continue
            right_fact = effective[right_position]
            if right_fact.fact_type != left_fact.fact_type:
                continue
            right_owners = routed[id(right_fact)]
            if len(right_owners) != 1 or right_owners[0] == left_owner:
                continue
            if _fact_has_table_coordinate(right_fact) or _fact_is_reference_table_coordinate(
                index, right_fact, right_owners
            ):
                continue
            if _core_tensile_semantic(right_fact):
                continue
            right_owner = right_owners[0]
            if _processing_table_coordinate_group(
                [
                    (left_position, left_fact, left_owners),
                    (right_position, right_fact, right_owners),
                ]
            ):
                # Distinct structured parameter values prove separate table
                # columns even when chunk boundaries changed the evidence
                # envelope and sent the pair to this near-duplicate pass.
                continue
            right_evidence = list(right_fact.source_evidence)
            if not right_evidence:
                continue
            if any("respectively" in row.casefold() for row in right_evidence):
                continue
            right_ambiguous = _multi_owner_projection_is_ambiguous(
                index, right_fact, right_owner, right_evidence
            )
            if not right_ambiguous and _evidence_names_owner(
                index, right_owner, right_evidence
            ):
                continue
            if (left_ambiguous or right_ambiguous) and any(
                _evidence_rows_share_assertion(left_row, right_row)
                for left_row in left_evidence
                for right_row in right_evidence
            ):
                for position, fact, owner in (
                    (left_position, left_fact, left_owner),
                    (right_position, right_fact, right_owner),
                ):
                    if position in removed:
                        continue
                    removed.add(position)
                    issues.append(
                        MaterializeIssue(
                            code="multi_owner_qualitative_projection_quarantined",
                            sample_id_raw=index.display_label(owner),
                            path=f"items.{index.display_label(owner)}.Extracted_Data",
                            message=(
                                "A qualitative fact copied from near-identical "
                                "multi-owner comparison evidence was isolated."
                            ),
                            evidence={
                                "shared_evidence": [*left_evidence, *right_evidence],
                                "near_duplicate_evidence": True,
                                "owners": [
                                    index.display_label(left_owner),
                                    index.display_label(right_owner),
                                ],
                            },
                            expected={
                                "owner_binding": (
                                    "one owner or explicit source coordinate"
                                )
                            },
                            actual={
                                "fact": fact.model_dump(),
                                "owner": index.display_label(owner),
                            },
                            suggested_action=(
                                "Restore only when the source explicitly binds the "
                                "qualitative observation to this owner."
                            ),
                        )
                    )
                continue
            if not any(
                _evidence_rows_share_assertion(left_row, right_row)
                for left_row in left_evidence
                for right_row in right_evidence
            ):
                continue
            for position, fact, owner in (
                (left_position, left_fact, left_owner),
                (right_position, right_fact, right_owner),
            ):
                if position in removed:
                    continue
                removed.add(position)
                issues.append(
                    MaterializeIssue(
                        code="shared_owner_projection_quarantined",
                        sample_id_raw=index.display_label(owner),
                        path=f"items.{index.display_label(owner)}.Extracted_Data",
                        message=(
                            "A fact copied from near-identical chunk evidence was "
                            "isolated because the evidence does not name this owner "
                            "or provide a unique source coordinate."
                        ),
                        evidence={
                            "shared_evidence": [
                                *left_evidence,
                                *right_evidence,
                            ],
                            "near_duplicate_evidence": True,
                            "owners": [
                                index.display_label(left_owner),
                                index.display_label(right_owner),
                            ],
                        },
                        expected={
                            "owner_binding": (
                                "literal owner mention or unique table/"
                                "respectively coordinate"
                            )
                        },
                        actual={
                            "fact": fact.model_dump(),
                            "owner": index.display_label(owner),
                        },
                        suggested_action=(
                            "Review the source span and restore only when it "
                            "explicitly reports an owner-specific observation."
                        ),
                    )
                )
    return [fact for position, fact in enumerate(effective) if position not in removed], issues


_CHARACTERIZATION_INSTRUMENT_CUE = re.compile(
    r"(?i)\b(?:instrument|device|system|microscope|spectrometer|"
    r"analy[sz]er|database|software|employ(?:ed|ing)?|utili[sz](?:ed|ing)?|"
    r"conducted\s+(?:using|with)|performed\s+(?:using|with)|"
    r"carried\s+out\s+(?:using|with)|using\s+(?:a|an)?|with\s+(?:a|an)?)\b"
)
_CHARACTERIZATION_FIGURE_CUE = re.compile(
    r"(?i)\b(?:fig(?:ure)?\.?\s*[A-Z0-9]|results?|graph|"
    r"mapping|patterns?|analysis|findings?|illustrated|depicted|shown)\b"
)

_STRUCTURE_CHARACTERIZATION_PROXY_NAME = re.compile(
    r"(?i)^\s*(?:characteri[sz]ation|analysis method|measurement method|"
    r"characteri[sz]ation method|technique)\s*$"
)
_STRUCTURE_CHARACTERIZATION_PROXY_VALUE = re.compile(
    r"(?i)\b(?:pole figures?|micrographs?|images?|maps?|mapping|patterns?|"
    r"microscopy|diffraction|spectroscopy|xrd|ebsd|sem|tem|stem|eds|edx)\b"
)


def _quarantine_structure_characterization_proxies(
    index: _IdentityIndex,
    facts: Sequence[AxisFact],
) -> tuple[list[AxisFact], list[MaterializeIssue]]:
    """Isolate method-only records incorrectly emitted as structure facts."""

    kept: list[AxisFact] = []
    issues: list[MaterializeIssue] = []
    for fact in facts:
        if fact.fact_type != "structure_observation":
            kept.append(fact)
            continue
        features = [
            row for row in fact.data.get("features") or [] if isinstance(row, dict)
        ]
        if not features or not all(
            _STRUCTURE_CHARACTERIZATION_PROXY_NAME.fullmatch(
                str(row.get("feature_name_raw") or "")
            )
            and _STRUCTURE_CHARACTERIZATION_PROXY_VALUE.search(
                str(row.get("value_raw") or "")
            )
            and not re.search(r"\d", str(row.get("value_raw") or ""))
            for row in features
        ):
            kept.append(fact)
            continue
        owners = _group_route(index, fact)
        owner_label = (
            index.display_label(owners[0])
            if len(owners) == 1
            else str(fact.sample_id_raw or "not_reported")
        )
        issues.append(
            MaterializeIssue(
                code="structure_characterization_proxy_quarantined",
                sample_id_raw=owner_label,
                path=f"items.{owner_label}.Structure.Structure_Observations",
                message=(
                    "A method or plot label emitted as a structure feature was "
                    "isolated because it reports no material structure result."
                ),
                evidence=list(fact.source_evidence),
                expected={
                    "structure_observation": (
                        "phase, morphology, texture, defect, interface, or a "
                        "measured structural feature"
                    ),
                    "characterization_proxy": False,
                },
                actual={"fact": fact.model_dump()},
                suggested_action=(
                    "Restore as Characterization only when the source provides "
                    "an instrument, acquisition, or analysis record."
                ),
            )
        )
    return kept, issues


def _reference_owner_material_keys(
    index: _IdentityIndex, owner: str
) -> set[str]:
    keys: set[str] = set()
    values = [index.display_label(owner)]
    for anchor in index.anchors.get(owner, []):
        values.extend((anchor.sample_id_raw, anchor.material_name_raw))
    for value in values:
        text = re.sub(
            r"(?i)\s*(?:\[\s*reference\s*\]|reference)\s*$",
            "",
            str(value or "").strip(),
        ).strip()
        key = normalize_source_alias(text)
        if key:
            keys.add(key)
    return keys


def _quarantine_reference_owner_entity_projections(
    index: _IdentityIndex,
    facts: Sequence[AxisFact],
) -> tuple[list[AxisFact], list[MaterializeIssue]]:
    """Remove a table row label re-emitted as an independent phase presence."""

    recovered: list[AxisFact] = []
    issues: list[MaterializeIssue] = []
    for fact in facts:
        if fact.fact_type != "structure_observation":
            recovered.append(fact)
            continue
        owners = _group_route(index, fact)
        if len(owners) != 1:
            recovered.append(fact)
            continue
        owner = owners[0]
        if not any(
            str(anchor.role or "").casefold() == "reference"
            for anchor in index.anchors.get(owner, [])
        ):
            recovered.append(fact)
            continue
        features = [
            row for row in fact.data.get("features") or [] if isinstance(row, dict)
        ]
        if not features or not any(
            re.search(r"\d", str(row.get("value_raw") or "")) for row in features
        ):
            recovered.append(fact)
            continue
        owner_keys = _reference_owner_material_keys(index, owner)
        entities = [
            row for row in fact.data.get("entities") or [] if isinstance(row, dict)
        ]
        removed = [
            row
            for row in entities
            if normalize_source_alias(
                row.get("name_raw") or row.get("canonical_name")
            )
            in owner_keys
        ]
        if not removed:
            recovered.append(fact)
            continue
        before = deepcopy(fact.data)
        data = deepcopy(fact.data)
        data["entities"] = [row for row in entities if row not in removed]
        updated = fact.model_copy(update={"data": data})
        recovered.append(updated)
        owner_label = index.display_label(owner)
        issues.append(
            MaterializeIssue(
                code="reference_owner_entity_projection_quarantined",
                sample_id_raw=owner_label,
                path=f"items.{owner_label}.Structure.Structure_Observations.entities",
                message=(
                    "A reference table row label was removed from entities because "
                    "the same observation already uses it as the material owner."
                ),
                evidence=list(fact.source_evidence),
                expected={
                    "reference_row_label": "material owner only",
                    "independent_phase_presence": "requires a separate assertion",
                },
                actual={
                    "removed_entities": deepcopy(removed),
                    "before": before,
                    "after": deepcopy(data),
                    "fact": fact.model_dump(),
                },
                suggested_action=(
                    "Restore the entity only when another source assertion "
                    "independently reports phase presence."
                ),
            )
        )
    return recovered, issues


def _quarantine_figure_characterizations(
    index: _IdentityIndex,
    facts: Sequence[AxisFact],
) -> tuple[list[AxisFact], list[MaterializeIssue]]:
    """Keep instrument metadata; isolate bare figure/result method mentions."""

    kept: list[AxisFact] = []
    issues: list[MaterializeIssue] = []
    for fact in facts:
        if fact.fact_type != "characterization":
            kept.append(fact)
            continue
        data = fact.data
        evidence = list(fact.source_evidence)
        text = " ".join(evidence)
        method = str(data.get("method_raw") or "").strip()
        method_class = str(data.get("method_class") or "").strip()
        family = _characterization_method_family(
            {"method_raw": method, "method_class": method_class}
        )
        if (
            _CHARACTERIZATION_INSTRUMENT_CUE.search(text)
            or not _CHARACTERIZATION_FIGURE_CUE.search(text)
        ):
            kept.append(fact)
            continue
        owner = _group_route(index, fact)
        owner_label = (
            index.display_label(owner[0])
            if len(owner) == 1
            else str(fact.sample_id_raw or "not_reported")
        )
        issues.append(
            MaterializeIssue(
                code="characterization_figure_observation_quarantined",
                sample_id_raw=owner_label,
                path=f"items.{owner_label}.Structure.Characterization",
                message=(
                    "A bare characterization method from a figure/result sentence "
                    "was isolated because no instrument, device, or acquisition "
                    "metadata was reported."
                ),
                evidence=evidence,
                expected={
                    "characterization": (
                        "instrument/device/software metadata or an explicit "
                        "acquisition record"
                    )
                },
                actual={"method_raw": method, "method_class": method_class, "fact": fact.model_dump()},
                suggested_action=(
                    "Restore only when the source sentence reports the instrument "
                    "or a method-specific acquisition setting rather than a figure "
                    "observation."
                ),
            )
        )
    return kept, issues


def _recover_numeric_tensile_context_owners(
    index: _IdentityIndex,
    facts: Sequence[AxisFact],
    source_text: str,
) -> tuple[list[AxisFact], list[MaterializeIssue]]:
    """Recover only consensus- or current-study-proven numeric tensile owners."""

    routed = {id(fact): _group_route(index, fact) for fact in facts}
    recovered: list[AxisFact] = []
    issues: list[MaterializeIssue] = []
    for fact in facts:
        route = routed[id(fact)]
        generic_base_route = bool(
            len(route) == 1
            and any(
                index.state_family_base.get(target) == route[0]
                for target in index.state_family_base
            )
        )
        comparator_scope = (
            _numeric_tensile_external_comparator_scope(fact)
            if not route
            else None
        )
        if comparator_scope is not None:
            issues.append(
                MaterializeIssue(
                    code="numeric_tensile_external_comparator_quarantined",
                    sample_id_raw=str(fact.sample_id_raw or "").strip(),
                    path=(
                        f"items.{fact.sample_id_raw}.Extracted_Data.Properties"
                    ),
                    message=(
                        "An unresolved numeric tensile value belonged to a "
                        "comparison material and was isolated before the "
                        "current-study protocol fallback could reassign it."
                    ),
                    evidence=comparator_scope,
                    expected={
                        "owner": "one materializable Reference coordinate",
                        "current_protocol_recovery": False,
                        "audit_preserved": True,
                    },
                    actual={
                        "removed": fact.model_dump(),
                        "reason": (
                            "unresolved_comparator_not_eligible_for_current_"
                            "protocol_recovery"
                        ),
                        "owner_invented": False,
                    },
                    suggested_action=(
                        "Restore only if the comparator can be bound to one "
                        "materializable source-declared Reference item."
                    ),
                )
            )
            continue
        table_binding = (
            _source_table_value_owner(index, fact, source_text)
            if source_text
            and _numeric_core_tensile_fact(fact)
            and (not route or generic_base_route)
            else None
        )
        if (
            not _numeric_core_tensile_fact(fact)
            or (route and not generic_base_route)
            or (_fact_is_blocked_tensile_result(fact) and table_binding is None)
        ):
            recovered.append(fact)
            continue

        selected: str | None = None
        rule = ""
        sibling_facts: list[AxisFact] = []
        source_blocks: list[str] = []
        decision_evidence: dict[str, Any] = {}

        source_sibling_blocks: list[str] = []
        siblings: list[AxisFact] = []
        for other in facts:
            if (
                other is fact
                or not _numeric_core_tensile_fact(other)
                or _fact_is_blocked_tensile_result(other)
                or len(routed[id(other)]) != 1
            ):
                continue
            shares_source_block, shared_blocks = _facts_share_source_assertion_block(
                source_text, fact, other
            )
            if not _facts_share_evidence_bundle(fact, other) and not shares_source_block:
                continue
            siblings.append(other)
            for block in shared_blocks:
                if block not in source_sibling_blocks:
                    source_sibling_blocks.append(block)
        sibling_owners = {routed[id(other)][0] for other in siblings}
        sibling_semantics = {_core_tensile_semantic(other) for other in siblings}
        # A complete source table gives a stronger owner coordinate than a
        # same-block sibling consensus.  The latter only proves that several
        # values belong to one *generic* owner; it cannot override an
        # unambiguous row/column match which identifies the exact state/sample
        # for this value.  In particular, a prose sentence may emit YS and UTS
        # siblings under one generic alloy label while a table binds the YS
        # value to a specific delay/state column.  Letting sibling consensus
        # win here silently drops
        # the state owner and recreates the precision residual we are fixing.
        if (
            table_binding is None
            and len(sibling_owners) == 1
            and len(sibling_semantics) >= 2
        ):
            candidate = next(iter(sibling_owners))
            state_targets = set(index.resolve_state_evidence(fact.source_evidence))
            candidate_base = index.state_family_base.get(candidate, candidate)
            conflicting_states = {
                target
                for target in state_targets
                if index.state_family_base.get(target, target) != candidate_base
            }
            if not conflicting_states:
                selected = candidate
                rule = "evidence_bundle_sibling_consensus"
                sibling_facts = siblings
                decision_evidence = {
                    "evidence_bundle": list(fact.source_evidence),
                    "source_assertion_blocks": source_sibling_blocks,
                    "sibling_semantics": sorted(sibling_semantics),
                }

        if selected is None and table_binding is not None:
            selected, binding = table_binding
            rule = "source_table_value_owner"
            decision_evidence = {
                "source_table_binding": binding,
                "owner_label": index.display_label(selected),
            }

        if selected is None and source_text:
            for blocks in _source_context_blocks_before_evidence(source_text, fact):
                context = "\n\n".join(blocks)
                if _CITATION_MARKER.search(context):
                    continue
                families = {
                    base: labels
                    for base, labels in _source_named_material_families(
                        index, context
                    ).items()
                    if _owner_roles(index, base) == {"target"}
                }
                if len(families) != 1:
                    continue
                base = next(iter(families))
                candidate = _unique_row_state_member(index, base, context)
                if candidate is None:
                    continue
                selected = candidate
                rule = "unique_current_study_prepared_state"
                source_blocks = blocks
                decision_evidence = {
                    "source_blocks": blocks,
                    "owner_family": index.display_label(base),
                    "owner_labels": families[base],
                }
                break

        if selected is None and source_text:
            result_contexts = _source_context_blocks_before_evidence(
                source_text, fact
            )
            compatible_result_contexts = [
                blocks
                for blocks in result_contexts
                if re.search(
                    r"(?is)\btensile\b.{0,120}\b(?:tests?|results?|curves?)\b|"
                    r"\b(?:tests?|results?|curves?)\b.{0,120}\btensile\b",
                    "\n\n".join(blocks),
                )
                and not _CITATION_MARKER.search("\n\n".join(blocks))
                and not re.search(
                    r"(?i)\bultrasonic\s+fatigue|\bfatigue\s+strength\b",
                    "\n\n".join(blocks),
                )
            ]
            static_context = _unique_static_tensile_owner_context(
                index, source_text
            )
            if len(compatible_result_contexts) == 1 and static_context is not None:
                selected, protocol_blocks, families = static_context
                base = index.state_family_base.get(selected, selected)
                rule = "unique_current_study_static_tensile_protocol"
                source_blocks = [*protocol_blocks, *compatible_result_contexts[0]]
                decision_evidence = {
                    "source_blocks": source_blocks,
                    "owner_family": index.display_label(base),
                    "owner_labels": families[base],
                    "protocol_kind": "static_tensile",
                }

        if selected is None:
            recovered.append(fact)
            continue

        before = fact.model_dump()
        after_owner = index.display_label(selected)
        cleaned = fact.model_copy(update={"sample_id_raw": after_owner})
        recovered.append(cleaned)
        issues.append(
            MaterializeIssue(
                code="numeric_tensile_owner_recovered",
                sample_id_raw=after_owner,
                path=f"items.{after_owner}.Extracted_Data.Properties",
                message=(
                    "A numeric core-tensile result was assigned to one source-proven "
                    "material/state owner."
                ),
                evidence={
                    **decision_evidence,
                    "source_blocks": source_blocks,
                },
                expected={
                    "owner": "one source-proven compatible material/state",
                    "rule": rule,
                },
                actual={
                    "before_owner": fact.sample_id_raw,
                    "after_owner": after_owner,
                    "rule": rule,
                    "fact": before,
                    "sibling_facts": [row.model_dump() for row in sibling_facts],
                },
                suggested_action=(
                    "Review the preserved owner evidence if the source block spans "
                    "multiple materials or test protocols."
                ),
            )
        )
    return recovered, issues


def _owner_presentation_variants(
    index: _IdentityIndex, canonical: str
) -> set[str]:
    labels = set(index.labels.get(canonical, Counter()))
    labels.add(index.display_label(canonical))
    labels.update(
        str(anchor.sample_id_raw or "").strip()
        for anchor in index.anchors.get(canonical, [])
    )
    variants = {label for label in labels if label}
    for label in list(variants):
        stripped = _FEEDSTOCK_PRESENTATION_SUFFIX.sub("", label).strip()
        stripped = _IDENTITY_SUFFIX.sub("", stripped).strip()
        if stripped:
            variants.add(stripped)
    return variants


def _explicit_primary_owner_mentions(
    index: _IdentityIndex,
    evidence: Sequence[str],
    candidate_owners: set[str],
) -> set[str]:
    mentions: set[str] = set()
    for target in index.resolve_evidence(evidence):
        if target in candidate_owners:
            mentions.add(target)
    joined = "\n".join(str(row) for row in evidence)
    for owner in candidate_owners:
        if any(
            _source_label_occurs_in_row(label, joined)
            for label in _owner_presentation_variants(index, owner)
        ):
            mentions.add(owner)
    # Prefer a qualified state/sample mention over its overlapping base owner.
    for owner in list(mentions):
        base = index.state_family_base.get(owner)
        if base and base in mentions:
            mentions.discard(base)
    return mentions


def _owner_descriptor_keys(index: _IdentityIndex, canonical: str) -> set[str]:
    return {
        key
        for anchor in index.anchors.get(canonical, [])
        for value in (anchor.sample_id_raw, anchor.material_name_raw)
        for key in _identity_alias_keys(value)
        if key
    }


_OWNER_LINEAGE_STOP_TOKENS = {
    "alloy",
    "alloys",
    "composite",
    "composites",
    "condition",
    "fabricated",
    "material",
    "materials",
    "melt",
    "nanocomposite",
    "nanocomposites",
    "powder",
    "powders",
    "printed",
    "processed",
    "sample",
    "samples",
    "specimen",
    "specimens",
}


def _owner_lineage_tokens(index: _IdentityIndex, canonical: str) -> set[str]:
    """Return distinctive literal tokens from one inventory owner.

    This is deliberately weaker than identity resolution and is used only after
    a complete three-property tensile bundle has already matched exactly.  It
    cannot route a fact by itself.
    """

    values = [index.display_label(canonical)]
    for anchor in index.anchors.get(canonical, []):
        values.extend((anchor.sample_id_raw, anchor.material_name_raw))
    tokens: set[str] = set()
    for value in values:
        text = unicodedata.normalize("NFKC", str(value or "")).casefold()
        tokens.update(
            token
            for token in re.findall(r"[a-z]+\d*|\d+[a-z]+", text)
            if token not in _OWNER_LINEAGE_STOP_TOKENS
        )
    return tokens


def _owner_sample_code_tokens(index: _IdentityIndex, canonical: str) -> set[str]:
    """Return source sample-code tokens such as ``L70`` or ``A230``."""

    values = [index.display_label(canonical)]
    values.extend(
        anchor.sample_id_raw for anchor in index.anchors.get(canonical, [])
    )
    codes: set[str] = set()
    for value in values:
        text = unicodedata.normalize("NFKC", str(value or "")).casefold()
        codes.update(
            token
            for token in re.findall(r"[a-z0-9]+", text)
            if re.search(r"[a-z]", token) and re.search(r"\d", token)
        )
    return codes


def _complete_tensile_bundle_dominance(
    index: _IdentityIndex,
    facts: Sequence[AxisFact],
    routed: dict[int, tuple[str, ...]],
) -> dict[tuple[str, str], str]:
    """Identify an exact three-property generic projection of one coded sample.

    A provider can emit the same YS/UTS/elongation bundle once under a generic
    process-family owner and once under the source sample code.  Individual
    equal values are insufficient evidence because two real samples can
    coincide.  This rule activates only when all three core tensile semantics,
    conditions, units, and values match, one coded owner is unique, and the
    inventory supplies at least two shared distinctive lineage tokens.
    """

    fingerprints: dict[str, set[str]] = {}
    semantics: dict[str, set[str]] = {}
    for fact in facts:
        if not _numeric_core_tensile_fact(fact):
            continue
        targets = routed[id(fact)]
        if len(targets) != 1:
            continue
        owner = targets[0]
        fingerprints.setdefault(owner, set()).add(
            _owner_agnostic_fact_signature(fact)
        )
        semantics.setdefault(owner, set()).add(_core_tensile_semantic(fact))

    required = {"yield_strength", "ultimate_tensile_strength", "elongation"}
    result: dict[tuple[str, str], str] = {}
    for loser_owner, loser_fingerprints in fingerprints.items():
        if semantics.get(loser_owner) != required:
            continue
        if _owner_sample_code_tokens(index, loser_owner):
            continue
        loser_tokens = _owner_lineage_tokens(index, loser_owner)
        candidates: list[str] = []
        for winner_owner, winner_fingerprints in fingerprints.items():
            if winner_owner == loser_owner:
                continue
            if _owner_roles(index, loser_owner) != _owner_roles(index, winner_owner):
                continue
            if not loser_fingerprints.issubset(winner_fingerprints):
                continue
            if not _owner_sample_code_tokens(index, winner_owner):
                continue
            shared_tokens = loser_tokens & _owner_lineage_tokens(index, winner_owner)
            if len(shared_tokens) < 2:
                continue
            candidates.append(winner_owner)
        if len(candidates) == 1:
            result[(loser_owner, candidates[0])] = (
                "specific_sample_bundle_over_generic_projection"
            )
    return result


def _cross_item_dominance_relation(
    index: _IdentityIndex,
    *,
    loser_owner: str,
    winner_owner: str,
    loser_fact: AxisFact,
) -> str:
    """Return the source-backed specificity relation, or an empty string."""

    if _owner_roles(index, loser_owner) != _owner_roles(index, winner_owner):
        return ""
    loser_base = index.state_family_base.get(loser_owner, loser_owner)
    winner_base = index.state_family_base.get(winner_owner, winner_owner)
    if loser_owner == winner_base and winner_owner != winner_base:
        return "qualified_state_over_base"
    if loser_base == winner_base:
        return ""
    # A generic projected owner may resolve through a presentation alias while
    # a sibling chunk assigns the same claim to a source sample code. Require
    # the winning sample inventory to repeat that exact generic descriptor.
    if _fact_primary_owners(index, loser_fact):
        return ""
    loser_labels = {
        key
        for value in [*_fact_identity_labels(loser_fact), loser_fact.sample_id_raw]
        for key in _identity_alias_keys(value)
        if key
    }
    winner_descriptors = {
        key
        for anchor in index.anchors.get(winner_owner, [])
        for key in _identity_alias_keys(anchor.material_name_raw)
        if key
    }
    if loser_labels & winner_descriptors:
        return "specific_sample_over_generic_projection"
    return ""


def _merge_fact_envelope_evidence(
    survivor: AxisFact, removed: AxisFact
) -> AxisFact:
    evidence = list(survivor.source_evidence)
    for row in removed.source_evidence:
        if row not in evidence:
            evidence.append(row)
    return survivor.model_copy(
        update={
            "source_evidence": evidence,
            "confidence": max(survivor.confidence, removed.confidence),
        }
    )


def _deduplicate_cross_item_dominance(
    index: _IdentityIndex,
    facts: Sequence[AxisFact],
) -> tuple[list[AxisFact], list[MaterializeIssue]]:
    """Merge only evidence-dominated generic/base projections across owners."""

    routed = {id(fact): _group_route(index, fact) for fact in facts}
    tensile_bundle_dominance = _complete_tensile_bundle_dominance(
        index, facts, routed
    )
    by_fingerprint: dict[str, list[tuple[int, AxisFact, str]]] = {}
    for position, fact in enumerate(facts):
        if fact.fact_type == "material_identity":
            # Material names/designations are scientific identity payload, not
            # owner-neutral duplicate fields. Per-item identity selection may
            # reconcile them later, but a paper-level pass must never merge
            # GA/WA or other explicitly enumerated feedstocks through a shared
            # generic material-family signature.
            continue
        targets = routed[id(fact)]
        if len(targets) != 1:
            continue
        by_fingerprint.setdefault(_owner_agnostic_fact_signature(fact), []).append(
            (position, fact, targets[0])
        )

    replacements: dict[int, AxisFact] = {}
    removed_positions: set[int] = set()
    issues: list[MaterializeIssue] = []
    for fingerprint, entries in by_fingerprint.items():
        candidate_owners = {owner for _, _, owner in entries}
        if len(candidate_owners) < 2:
            continue
        evidence = [
            row
            for _, fact, _ in entries
            for row in fact.source_evidence
        ]
        all_mentions = _explicit_primary_owner_mentions(
            index, evidence, set(index.anchors)
        )
        mentioned_families = {
            index.state_family_base.get(owner, owner) for owner in all_mentions
        }
        if len(mentioned_families) > 1:
            # Explicit conjunction/plural assertions remain attached to every
            # source-named owner even when only a subset happens to share this
            # exact scientific fingerprint.
            continue
        named_owners = _explicit_primary_owner_mentions(
            index, evidence, candidate_owners
        )
        if len(named_owners) == 1:
            winner_owner = next(iter(named_owners))
            winner_selected_by_bundle = False
        else:
            bundle_winners = {
                winner
                for loser, winner in tensile_bundle_dominance
                if loser in candidate_owners and winner in candidate_owners
            }
            if len(bundle_winners) != 1:
                continue
            winner_owner = next(iter(bundle_winners))
            winner_selected_by_bundle = True
        winner_entries = [entry for entry in entries if entry[2] == winner_owner]
        if not winner_entries:
            continue
        survivor_position, survivor, _ = winner_entries[0]
        survivor = replacements.get(survivor_position, survivor)

        for loser_position, loser, loser_owner in entries:
            if loser_owner == winner_owner or loser_position in removed_positions:
                continue
            relation = (
                tensile_bundle_dominance.get((loser_owner, winner_owner), "")
                if winner_selected_by_bundle
                else _cross_item_dominance_relation(
                    index,
                    loser_owner=loser_owner,
                    winner_owner=winner_owner,
                    loser_fact=loser,
                )
            )
            if not relation and not winner_selected_by_bundle:
                relation = tensile_bundle_dominance.get(
                    (loser_owner, winner_owner), ""
                )
            if not relation:
                continue
            survivor_before = survivor.model_dump()
            survivor = _merge_fact_envelope_evidence(survivor, loser)
            removed_positions.add(loser_position)
            issues.append(
                MaterializeIssue(
                    code="cross_item_duplicate_merged",
                    sample_id_raw=index.display_label(winner_owner),
                    path=(
                        f"items.{index.display_label(winner_owner)}.Extracted_Data"
                    ),
                    message=(
                        "An evidence-dominated generic/base duplicate was merged "
                        "into the uniquely named, more-specific material owner."
                    ),
                    evidence={
                        "dominance_evidence": evidence,
                        "explicit_owner_mentions": [
                            index.display_label(owner)
                            for owner in sorted(named_owners)
                        ],
                    },
                    expected={
                        "duplicate_fingerprint": fingerprint,
                        "dominant_owner_count": 1,
                    },
                    actual={
                        "before_owner": index.display_label(loser_owner),
                        "after_owner": index.display_label(winner_owner),
                        "rule": relation,
                        "fingerprint": fingerprint,
                        "removed_fact": loser.model_dump(),
                        "survivor_before_merge": survivor_before,
                        "survivor_after_merge": survivor.model_dump(),
                    },
                    suggested_action=(
                        "Review only if the generic/base owner is independently "
                        "asserted by the source evidence."
                    ),
                )
            )
        replacements[survivor_position] = survivor

    return [
        replacements.get(position, fact)
        for position, fact in enumerate(facts)
        if position not in removed_positions
    ], issues


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


_POWDER_COORDINATE = re.compile(
    r"(?i)\b(?:powders?|feedstocks?|as[\s-]*received|"
    r"(?:gas|water|argon)[\s-]*atomized|atomized)\b"
)
_SOURCE_ANALYSIS_LABEL = re.compile(
    r"(?i)\b(?:eds|edx|manufacturer|provided)\b"
)
_QUALIFIED_POWDER_ANALYSIS_LABEL = re.compile(
    r"(?i)^\s*(?P<prefix>.+?)\s+(?:powders?|feedstocks?)\s*"
    r"\(\s*(?P<kind>eds|edx|provided|manufacturer)\s*\)\s*$"
)
_COMPACT_FEEDSTOCK_CODE = re.compile(r"^[A-Z][A-Z0-9_.+-]{1,5}$")


def _reported_composition_components(fact: AxisFact) -> list[dict[str, Any]]:
    if not (
        isinstance(fact, CompositionFact)
        and fact.fact_type == "composition_observation"
    ):
        return []
    return [
        component
        for component in fact.data.get("components") or []
        if isinstance(component, dict)
        and str(component.get("name_raw") or "").strip()
        and str(component.get("value_raw") or "").strip()
        and not _is_unresolved_alias(component.get("value_raw"))
    ]


def _table_analysis_kind(fact: AxisFact, label: str) -> str:
    """Return a source-analysis coordinate proven by one local table row."""

    data = fact.data
    if str(data.get("data_source") or "").strip().casefold() != "table":
        return ""
    components = _reported_composition_components(fact)
    if len(components) < 2:
        return ""
    evidence = "\n".join(fact.source_evidence)
    if not _evidence_label_literal(label, evidence) or not all(
        _evidence_value_literal(component.get("value_raw"), evidence)
        for component in components
    ):
        return ""
    source_type = str(data.get("source_type") or "").strip().casefold()
    analysis_text = " ".join(
        str(value or "")
        for value in (label, data.get("measurement"), data.get("raw_expression"))
    )
    if source_type == "measured" and re.search(r"(?i)\b(?:eds|edx)\b", analysis_text):
        return "EDS"
    if source_type == "provided" and re.search(
        r"(?i)\b(?:manufacturer|provided)\b", analysis_text
    ):
        return (
            "Manufacturer"
            if re.search(r"(?i)\bmanufacturer\b", analysis_text)
            else "provided"
        )
    return ""


def _singular_powder_descriptor(value: Any) -> str:
    text = unicodedata.normalize("NFKC", str(value or "")).strip()
    text = re.sub(r"(?i)\b(powder|feedstock)s\s*$", r"\1", text)
    if not re.search(r"(?i)\b(?:powder|feedstock)\b", text):
        text = f"{text} powder".strip()
    return text


def _material_lineage_keys(value: Any) -> set[str]:
    text = unicodedata.normalize("NFKC", str(value or ""))
    keys = {
        normalize_source_alias(match.group(0))
        for match in re.finditer(
            r"(?i)\b(?:alloy\s*[- ]?\s*\d+[A-Za-z0-9-]*|"
            r"[A-Za-z]{2,}\s*[- ]?\s*\d+[A-Za-z0-9-]*)\b",
            text,
        )
    }
    return {key for key in keys if key}


def _analysis_material_descriptor(
    anchors: Sequence[InventoryAnchor], label: str
) -> tuple[str, list[InventoryAnchor]]:
    key = _identity_key(label)
    rows = [
        anchor
        for anchor in anchors
        if _identity_key(anchor.sample_id_raw) == key
        and str(anchor.material_name_raw or "").strip()
        and is_plausible_material_identity(anchor.material_name_raw)
    ]
    if not rows:
        return "", []
    presentations = Counter(
        _singular_powder_descriptor(anchor.material_name_raw) for anchor in rows
    )
    lineages = {
        lineage
        for presentation in presentations
        for lineage in _material_lineage_keys(presentation)
    }
    if len(lineages) > 1:
        return "", []
    descriptor = min(
        presentations,
        key=lambda value: (
            -presentations[value],
            -int(bool(_material_lineage_keys(value))),
            len(value),
            value.casefold(),
        ),
    )
    return descriptor, rows


def _analysis_prefix(label: str) -> str:
    match = _QUALIFIED_POWDER_ANALYSIS_LABEL.fullmatch(label)
    return str(match.group("prefix") or "").strip() if match else ""


def _best_feedstock_state_anchor(
    anchors: Sequence[InventoryAnchor],
    *,
    descriptor: str,
    prefix: str = "",
) -> InventoryAnchor | None:
    lineage = _material_lineage_keys(descriptor)
    candidates: list[InventoryAnchor] = []
    for anchor in anchors:
        if str(anchor.role or "").casefold() != "target":
            continue
        presentation = " ".join(
            str(value or "")
            for value in (
                anchor.sample_id_raw,
                anchor.material_name_raw,
                anchor.state_raw,
            )
        )
        if not _POWDER_COORDINATE.search(presentation):
            continue
        candidate_lineage = _material_lineage_keys(presentation)
        if lineage and not (lineage & candidate_lineage):
            continue
        if prefix and not _source_label_occurs_in_row(
            prefix, str(anchor.sample_id_raw or "")
        ):
            continue
        state = str(anchor.state_raw or "").strip()
        if not state or not _POWDER_COORDINATE.search(state):
            continue
        candidates.append(anchor)
    if not candidates:
        return None

    def rank(anchor: InventoryAnchor) -> tuple[int, int, float, int, str]:
        state = str(anchor.state_raw or "").strip()
        specificity = sum(
            bool(pattern.search(state))
            for pattern in (
                re.compile(r"(?i)\batomized\b"),
                re.compile(r"(?i)\bas[\s-]*received\b"),
                re.compile(r"(?i)\b(?:argon|gas|water)\b"),
                re.compile(r"(?i)\b(?:powder|feedstock)\b"),
            )
        )
        return (
            specificity,
            len(_state_descriptor(state)[1]) if _state_descriptor(state) else 0,
            float(anchor.confidence),
            len(state),
            state.casefold(),
        )

    return max(candidates, key=rank)


def _analysis_owner_display(label: str, descriptor: str, kind: str) -> str:
    qualified = _QUALIFIED_POWDER_ANALYSIS_LABEL.fullmatch(label)
    if qualified:
        prefix = str(qualified.group("prefix") or "").strip()
        descriptor_without_powder = re.sub(
            r"(?i)\s+(?:powder|feedstock)\s*$", "", descriptor
        ).strip()
        suffix = "EDS" if kind == "EDS" else "provided"
        return f"{prefix} {descriptor_without_powder} powder ({suffix})"
    if kind == "EDS":
        return f"EDS powder analysis for {descriptor}"
    if kind == "Manufacturer":
        return f"Manufacturer analysis for {descriptor}"
    return f"Provided powder analysis for {descriptor}"


def _recover_analysis_source_composition_owners(
    anchors: Sequence[InventoryAnchor], facts: Sequence[AxisFact]
) -> tuple[list[InventoryAnchor], list[AxisFact], list[MaterializeIssue]]:
    """Keep measured and supplier table coordinates as independent owners."""

    anchor_rows = list(anchors)
    fact_rows = list(facts)
    created: dict[str, InventoryAnchor] = {}
    issues: list[MaterializeIssue] = []
    for position, fact in enumerate(fact_rows):
        labels = list(
            dict.fromkeys(
                str(value or "").strip()
                for value in (fact.sample_id_raw, fact.data.get("sample_id"))
                if str(value or "").strip()
            )
        )
        if len(labels) != 1:
            continue
        label = labels[0]
        kind = _table_analysis_kind(fact, label)
        if not kind or not _SOURCE_ANALYSIS_LABEL.search(label):
            continue
        descriptor, source_anchors = _analysis_material_descriptor(anchor_rows, label)
        if not descriptor or not _POWDER_COORDINATE.search(
            f"{label} {descriptor} "
            + " ".join(str(anchor.state_raw or "") for anchor in source_anchors)
        ):
            continue
        prefix = _analysis_prefix(label)
        state_anchor = _best_feedstock_state_anchor(
            anchor_rows, descriptor=descriptor, prefix=prefix
        )
        state = (
            str(state_anchor.state_raw or "").strip()
            if state_anchor is not None
            else min(
                (
                    str(anchor.state_raw or "").strip()
                    for anchor in source_anchors
                    if str(anchor.state_raw or "").strip()
                ),
                key=lambda value: (len(value), value.casefold()),
                default="powder",
            )
        )
        display = _analysis_owner_display(label, descriptor, kind)
        role = "Target" if kind == "EDS" else "Reference"
        source_evidence = list(
            dict.fromkeys(
                [
                    *fact.source_evidence,
                    *(
                        evidence
                        for anchor in source_anchors
                        for evidence in anchor.source_evidence
                    ),
                    *(
                        list(state_anchor.source_evidence)
                        if state_anchor is not None
                        else []
                    ),
                ]
            )
        )
        recovered_anchor = InventoryAnchor(
            sample_id_raw=display,
            material_name_raw=descriptor,
            state_raw=state,
            role=role,
            data_nature=(
                state_anchor.data_nature
                if state_anchor is not None
                else max(source_anchors, key=lambda row: row.confidence).data_nature
            ),
            source_evidence=source_evidence,
            confidence=max(
                [fact.confidence, *(anchor.confidence for anchor in source_anchors)]
            ),
        )
        created.setdefault(display, recovered_anchor)

        before = fact.model_dump()
        data = deepcopy(fact.data)
        data["sample_id"] = display
        current_state = str(data.get("material_state") or "").strip()
        if (
            not current_state
            or _is_unresolved_alias(current_state)
            or normalize_source_alias(current_state) in {"powder", "asreceivedpowder"}
        ):
            data["material_state"] = state
        recovered_fact = fact.model_copy(
            update={"sample_id_raw": display, "data": data}
        )
        fact_rows[position] = recovered_fact
        issues.append(
            MaterializeIssue(
                code="analysis_source_owner_recovered",
                sample_id_raw=display,
                path=f"items.{display}.Composition.Composition_Observations",
                message=(
                    "A source-labelled powder analysis row was preserved as an "
                    "independent measured or supplier composition coordinate."
                ),
                evidence=source_evidence,
                expected={
                    "table_label": label,
                    "component_count_min": 2,
                    "source_type": fact.data.get("source_type"),
                    "owner_role": role,
                },
                actual={
                    "before_owner": label,
                    "after_owner": display,
                    "before_role": [anchor.role for anchor in source_anchors],
                    "after_role": role,
                    "before": before,
                    "after": recovered_fact.model_dump(),
                    "selected_state_anchor": (
                        state_anchor.model_dump() if state_anchor is not None else None
                    ),
                },
                suggested_action=(
                    "Review only if the table label does not distinguish the "
                    "measured row from the supplier-provided row."
                ),
            )
        )
    anchor_rows.extend(created.values())
    return anchor_rows, fact_rows, issues


def _feedstock_code(value: Any) -> str:
    text = unicodedata.normalize("NFKC", str(value or "")).strip()
    text = re.sub(r"(?i)\s+(?:powder|feedstock)s?\s*$", "", text).strip()
    return text if _COMPACT_FEEDSTOCK_CODE.fullmatch(text) else ""


def _feedstock_material_descriptor(
    anchors: Sequence[InventoryAnchor], code: str
) -> tuple[str, InventoryAnchor | None]:
    candidates: list[InventoryAnchor] = []
    presentations: Counter[str] = Counter()
    for anchor in anchors:
        if str(anchor.role or "").casefold() != "target":
            continue
        if _feedstock_code(anchor.sample_id_raw) != code:
            continue
        local = " ".join(
            str(value or "")
            for value in (anchor.sample_id_raw, anchor.material_name_raw, anchor.state_raw)
        )
        if not _POWDER_COORDINATE.search(local):
            continue
        material = str(anchor.material_name_raw or "").strip()
        if not material or not is_plausible_material_identity(material):
            continue
        material = re.sub(
            rf"(?i)^\s*{re.escape(code)}\s+(?:powder|feedstock)s?\s+",
            "",
            material,
        ).strip()
        material = re.sub(
            r"(?i)^\s*(?:(?:air[\s-]*melted|gas|water|argon|vacuum[\s-]*melted)\s+)*"
            r"(?:atomized\s+)?",
            "",
            material,
        ).strip()
        descriptor = re.sub(
            r"(?i)\s+(?:powder|feedstock)s?\s*$", "", material
        ).strip()
        if not descriptor:
            continue
        candidates.append(anchor)
        presentations[descriptor] += 1
    lineages = {
        lineage
        for descriptor in presentations
        for lineage in _material_lineage_keys(descriptor)
    }
    if not presentations or len(lineages) > 1:
        return "", None
    descriptor = min(
        presentations,
        key=lambda value: (
            -presentations[value],
            -len(re.findall(r"[A-Za-z0-9]+", value)),
            len(value),
            value.casefold(),
        ),
    )
    state_anchor = _best_feedstock_state_anchor(
        candidates, descriptor=descriptor, prefix=code
    )
    return descriptor, state_anchor


def _recover_feedstock_owner_descriptors(
    anchors: Sequence[InventoryAnchor], facts: Sequence[AxisFact]
) -> tuple[list[InventoryAnchor], list[AxisFact], list[MaterializeIssue]]:
    """Enrich a compact feedstock code only on its explicit powder state."""

    anchor_rows = list(anchors)
    fact_rows = list(facts)
    created: dict[str, InventoryAnchor] = {}
    issues: list[MaterializeIssue] = []
    for position, fact in enumerate(fact_rows):
        if fact.fact_type == "material_identity":
            # Identity rows already carry their material name/designation and
            # are ranked by the existing identity selector.  Feedstock owner
            # enrichment applies only to observations/results; rewriting an
            # identity row would hide that selector's audit trail.
            continue
        label = str(fact.sample_id_raw or "").strip()
        if _SOURCE_ANALYSIS_LABEL.search(label):
            continue
        code = _feedstock_code(label)
        if not code:
            continue
        local_state = str(fact.data.get("material_state") or "").strip()
        local_evidence = " ".join(fact.source_evidence)
        if not (
            _POWDER_COORDINATE.search(local_state)
            or re.search(
                rf"(?i)(?<![A-Za-z0-9]){re.escape(code)}(?![A-Za-z0-9])"
                r".{0,80}\b(?:powder|feedstock)\b",
                local_evidence,
            )
        ):
            continue
        descriptor, state_anchor = _feedstock_material_descriptor(anchor_rows, code)
        if not descriptor:
            continue
        display = f"{code} {descriptor} powder"
        state = (
            str(state_anchor.state_raw or "").strip()
            if state_anchor is not None
            else local_state or "powder"
        )
        source_evidence = list(
            dict.fromkeys(
                [
                    *fact.source_evidence,
                    *(
                        list(state_anchor.source_evidence)
                        if state_anchor is not None
                        else []
                    ),
                ]
            )
        )
        created.setdefault(
            display,
            InventoryAnchor(
                sample_id_raw=display,
                material_name_raw=descriptor,
                state_raw=state,
                role="Target",
                data_nature=(
                    state_anchor.data_nature
                    if state_anchor is not None
                    else "Experimental"
                ),
                source_evidence=source_evidence,
                confidence=max(
                    fact.confidence,
                    state_anchor.confidence if state_anchor is not None else 0.0,
                ),
            ),
        )
        before = fact.model_dump()
        data = deepcopy(fact.data)
        if "sample_id" in data:
            data["sample_id"] = display
        if local_state and (
            normalize_source_alias(local_state) in {"powder", "asreceivedpowder"}
            or _is_unresolved_alias(local_state)
        ):
            data["material_state"] = state
        recovered_fact = fact.model_copy(
            update={"sample_id_raw": display, "data": data}
        )
        fact_rows[position] = recovered_fact
        issues.append(
            MaterializeIssue(
                code="feedstock_owner_descriptor_recovered",
                sample_id_raw=display,
                path=f"items.{display}.Extracted_Data",
                message=(
                    "A compact feedstock code was enriched with its one "
                    "source-backed material descriptor on the powder state only."
                ),
                evidence=source_evidence,
                expected={
                    "owner_code": code,
                    "coordinate": "powder/feedstock",
                    "material_lineage_count": 1,
                },
                actual={
                    "before_owner": label,
                    "after_owner": display,
                    "before": before,
                    "after": recovered_fact.model_dump(),
                    "selected_state_anchor": (
                        state_anchor.model_dump() if state_anchor is not None else None
                    ),
                },
                suggested_action=(
                    "Review only if the compact code names more than one powder "
                    "material in this paper."
                ),
            )
        )
    anchor_rows.extend(created.values())
    return anchor_rows, fact_rows, issues


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


_MICROANALYSIS_GENERIC_IDENTIFIERS = frozenset(
    {"analysis", "analyses", "eds", "edx", "mapping", "measurement", "measurements"}
)
_TABLE_HEADER_LABEL = re.compile(
    r"(?i)^(?:elements?|components?|composition(?:\s+in\s+.+)?|constituents?)$"
)
_TABLE_SEPARATOR_CELL = re.compile(r"^:?-{2,}:?$")


@dataclass(frozen=True)
class _MicroanalysisTableEnvelope:
    location: str
    state: str
    table_header: tuple[str, ...]
    source_row: tuple[str, ...]
    context_evidence: tuple[str, ...]


def _canonical_microanalysis_location(kind: str, identifier: str) -> str:
    identifier = str(identifier or "").strip().strip("._-")
    if not identifier or identifier.casefold() in _MICROANALYSIS_GENERIC_IDENTIFIERS:
        return ""
    singular = {
        "point": "Point",
        "spot": "Spot",
        "area": "Area",
        "location": "Location",
    }.get(str(kind or "").casefold(), "")
    return f"{singular} {identifier}" if singular else ""


def _microanalysis_locations_in_text(value: Any) -> tuple[str, ...]:
    locations = [
        location
        for match in _MICROANALYSIS_LOCATION_SEARCH.finditer(str(value or ""))
        if (
            location := _canonical_microanalysis_location(
                match.group(1), match.group(2)
            )
        )
    ]
    return tuple(dict.fromkeys(locations))


def _loose_projected_table_cells(value: Any) -> tuple[str, ...]:
    """Read a cropped table row without treating prose separators as a table."""

    text = str(value or "").strip()
    if not text or "|" not in text:
        return ()
    cells = tuple(cell.strip() for cell in text.strip("|").split("|"))
    if len(cells) < 2 or not _microanalysis_locations_in_text(cells[0]):
        return ()
    return cells


def _leading_microanalysis_evidence_location(fact: AxisFact) -> str:
    locations = {
        location
        for evidence in fact.source_evidence
        for line in str(evidence or "").splitlines()
        if (cells := _loose_projected_table_cells(line))
        for location in _microanalysis_locations_in_text(cells[0])
    }
    return next(iter(locations)) if len(locations) == 1 else ""


def _microanalysis_table_fact_location(fact: AxisFact) -> str:
    """Recover one observation location from a cropped composition fact."""

    direct = _microanalysis_location_label(fact)
    if direct:
        locations = _microanalysis_locations_in_text(direct)
        return locations[0] if len(locations) == 1 else ""

    evidence_location = _leading_microanalysis_evidence_location(fact)
    if evidence_location:
        return evidence_location

    measurement_locations = _microanalysis_locations_in_text(
        fact.data.get("measurement")
    )
    if len(measurement_locations) == 1:
        return measurement_locations[0]

    raw_locations = _microanalysis_locations_in_text(
        fact.data.get("raw_expression")
    )
    evidence_locations = _microanalysis_locations_in_text(
        "\n".join(fact.source_evidence)
    )
    if (
        len(raw_locations) == 1
        and len(evidence_locations) == 1
        and _microanalysis_location_key(raw_locations[0])
        == _microanalysis_location_key(evidence_locations[0])
    ):
        return raw_locations[0]
    return ""


def _markdown_table_blocks(
    source_text: str,
) -> list[tuple[int, int, list[list[str]]]]:
    """Return consecutive Markdown table rows with their source line bounds."""

    lines = (source_text or "").splitlines()
    blocks: list[tuple[int, int, list[list[str]]]] = []
    index = 0
    while index < len(lines):
        line = lines[index]
        cells = _table_cells(line) if "<" not in line else []
        if not cells:
            index += 1
            continue
        start = index
        rows: list[list[str]] = []
        while index < len(lines):
            candidate = lines[index]
            candidate_cells = _table_cells(candidate) if "<" not in candidate else []
            if not candidate_cells:
                break
            rows.append(candidate_cells)
            index += 1
        if len(rows) >= 2:
            blocks.append((start, index - 1, rows))
        if index == start:
            index += 1
    return blocks


def _html_table_blocks(
    source_text: str,
) -> list[tuple[int, int, list[list[str]]]]:
    """Return HTML table rows without depending on presentation attributes."""

    text = source_text or ""
    blocks: list[tuple[int, int, list[list[str]]]] = []
    for table in re.finditer(r"(?is)<table\b[^>]*>(.*?)</table>", text):
        rows = [
            _table_cells(f"<tr>{row.group(1)}</tr>")
            for row in re.finditer(r"(?is)<tr\b[^>]*>(.*?)</tr>", table.group(1))
        ]
        rows = [row for row in rows if row]
        if len(rows) < 2:
            continue
        start_line = text.count("\n", 0, table.start())
        end_line = text.count("\n", 0, table.end())
        blocks.append((start_line, end_line, rows))
    return blocks


def _bounded_table_context(
    source_lines: Sequence[str], start: int, end: int
) -> tuple[str, ...]:
    """Return preceding prose/captions without crossing another source table."""

    before: list[str] = []
    index = start - 1
    while index >= 0 and len(before) < 6:
        line = source_lines[index].strip()
        index -= 1
        if not line:
            continue
        if line.startswith("|") or "<table" in line.casefold():
            break
        if line.startswith("#"):
            break
        before.append(line)

    return tuple(reversed(before))


def _source_descriptor_state_text(
    descriptor: tuple[str, tuple[str, ...]]
) -> str:
    """Render a source descriptor into a state string understood by the index."""

    category, qualifiers = descriptor
    label = category.replace("_", " ")
    temperatures: list[str] = []
    durations: list[str] = []
    other: list[str] = []
    for qualifier in qualifiers:
        match = re.fullmatch(r"([-+]?\d+(?:\.\d+)?)(°c|k|h|min|s)", qualifier)
        if match is None:
            other.append(qualifier)
            continue
        number, unit = match.groups()
        rendered_unit = "°C" if unit == "°c" else unit
        rendered = f"{number} {rendered_unit}"
        if unit in {"°c", "k"}:
            temperatures.append(rendered)
        elif unit in {"h", "min", "s"}:
            durations.append(rendered)
        else:
            other.append(rendered)
    if temperatures:
        label += " at " + " and ".join(temperatures)
    if durations:
        label += " for " + " and ".join(durations)
    if other:
        label += " " + " ".join(other)
    return label.strip()


def _unique_table_context_state(
    context: Sequence[str],
) -> tuple[str, tuple[str, ...]] | None:
    """Select the one most-specific compatible state in a table envelope."""

    candidates = [
        (descriptor, line)
        for line in context
        if (descriptor := _source_state_descriptor(line)) is not None
        and descriptor[1]
    ]
    if not candidates:
        return None
    specificity = max(len(descriptor[1]) for descriptor, _ in candidates)
    strongest = [
        (descriptor, line)
        for descriptor, line in candidates
        if len(descriptor[1]) == specificity
    ]
    descriptors = {descriptor for descriptor, _ in strongest}
    if len(descriptors) != 1:
        return None
    descriptor = next(iter(descriptors))
    evidence = tuple(
        dict.fromkeys(line for candidate, line in candidates if candidate == descriptor)
    )
    return _source_descriptor_state_text(descriptor), evidence


def _table_is_separator(row: Sequence[str]) -> bool:
    nonempty = [str(cell or "").strip() for cell in row if str(cell or "").strip()]
    return bool(nonempty) and all(_TABLE_SEPARATOR_CELL.fullmatch(cell) for cell in nonempty)


def _source_microanalysis_table_envelopes(
    source_text: str,
) -> tuple[_MicroanalysisTableEnvelope, ...]:
    """Reconstruct EDS/EDX point rows together with their source state."""

    source_lines = (source_text or "").splitlines()
    blocks = [
        *_markdown_table_blocks(source_text),
        *_html_table_blocks(source_text),
    ]
    envelopes: list[_MicroanalysisTableEnvelope] = []
    for start, end, raw_rows in blocks:
        context = _bounded_table_context(source_lines, start, end)
        context_text = "\n".join(context)
        if not _MICROANALYSIS_METHOD.search(context_text):
            continue
        selected_state = _unique_table_context_state(context)
        if selected_state is None:
            continue
        state, state_evidence = selected_state
        rows = [row for row in raw_rows if not _table_is_separator(row)]
        header_index = next(
            (
                index
                for index, row in enumerate(rows)
                if len(row) >= 3
                and _TABLE_HEADER_LABEL.fullmatch(str(row[0] or "").strip())
                and len([cell for cell in row[1:] if str(cell or "").strip()]) >= 2
            ),
            None,
        )
        if header_index is None:
            continue
        header = tuple(str(cell or "").strip() for cell in rows[header_index])
        normalized_headers = [normalize_source_alias(cell) for cell in header[1:]]
        if not all(normalized_headers) or len(set(normalized_headers)) != len(normalized_headers):
            continue
        for row in rows[header_index + 1 :]:
            if len(row) < 2:
                continue
            locations = _microanalysis_locations_in_text(row[0])
            if len(locations) != 1:
                continue
            source_row = tuple(str(cell or "").strip() for cell in row)
            envelopes.append(
                _MicroanalysisTableEnvelope(
                    location=locations[0],
                    state=state,
                    table_header=header,
                    source_row=source_row,
                    context_evidence=tuple(
                        dict.fromkeys([*context, *state_evidence])
                    ),
                )
            )
    return tuple(envelopes)


def _microanalysis_cell_key(value: Any) -> str:
    text = _normalize_state_markup(value).casefold()
    text = (
        text.replace("&lt;", "<")
        .replace("&gt;", ">")
        .replace("−", "-")
        .replace("–", "-")
        .replace("—", "-")
    )
    return re.sub(r"[\s${}\\]+", "", text)


def _microanalysis_envelope_component_matches(
    fact: AxisFact, envelope: _MicroanalysisTableEnvelope
) -> tuple[dict[str, Any], ...]:
    """Return exact component-column matches or an empty unsafe result."""

    if (
        not isinstance(fact, CompositionFact)
        or fact.fact_type != "composition_observation"
        or str(fact.data.get("source_type") or "").strip().casefold() != "measured"
        or str(fact.data.get("data_source") or "").strip().casefold() != "table"
    ):
        return ()
    location = _microanalysis_table_fact_location(fact)
    if not location or _microanalysis_location_key(location) != _microanalysis_location_key(
        envelope.location
    ):
        return ()
    headers = [normalize_source_alias(cell) for cell in envelope.table_header[1:]]
    components = [
        component
        for component in fact.data.get("components") or []
        if isinstance(component, dict)
        and str(component.get("name_raw") or "").strip()
        and str(component.get("value_raw") or "").strip()
    ]
    if not components:
        return ()
    source_values = list(envelope.source_row[1:])
    reported_source_values = [
        value
        for value in source_values
        if _microanalysis_cell_key(value) not in {"", "-", "notreported", "na"}
    ]
    if len(reported_source_values) < 2:
        return ()
    matches: list[dict[str, Any]] = []
    for component in components:
        key = normalize_source_alias(
            component.get("canonical_name") or component.get("name_raw")
        )
        indices = [index for index, header in enumerate(headers) if header == key]
        if len(indices) != 1:
            return ()
        column_index = indices[0]
        if column_index >= len(source_values):
            return ()
        source_value = source_values[column_index]
        if _microanalysis_cell_key(component.get("value_raw")) != _microanalysis_cell_key(
            source_value
        ):
            return ()
        matches.append(
            {
                "component": str(
                    component.get("canonical_name") or component.get("name_raw")
                ).strip(),
                "column": envelope.table_header[column_index + 1],
                "fact_value": str(component.get("value_raw") or "").strip(),
                "source_value": source_value,
            }
        )
    return tuple(matches)


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
        target_anchors = index.anchors.get(target, [])
        if not target_anchors:
            continue
        declared_numbers = set(re.findall(r"\d+(?:\.\d+)?", display))
        declared_numbers.update(
            number
            for anchor in target_anchors
            for number in re.findall(
                r"\d+(?:\.\d+)?",
                " ".join(
                    [
                        str(anchor.sample_id_raw or ""),
                        str(anchor.state_raw or ""),
                    ]
                ),
            )
        )
        if not state_numbers <= declared_numbers:
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


def _microanalysis_table_state_owner(
    index: _IdentityIndex, source_state: str
) -> str | None:
    """Select one declared owner compatible with a more-complete table state."""

    descriptor = _state_descriptor(source_state)
    if descriptor is None:
        return None
    source_category, source_qualifiers = descriptor
    source_set = set(source_qualifiers)
    if not source_set:
        return None
    ranked: list[tuple[tuple[int, int, int], str]] = []
    for target, anchors in index.anchors.items():
        target_ranks: list[tuple[int, int, int]] = []
        for anchor in anchors:
            candidate = _state_descriptor(anchor.state_raw)
            if anchor.role != "Target" or candidate is None:
                continue
            candidate_category, candidate_qualifiers = candidate
            candidate_set = set(candidate_qualifiers)
            if (
                candidate_category != source_category
                or not candidate_set
                or not (candidate_set <= source_set or source_set <= candidate_set)
                or not candidate_set & source_set
            ):
                continue
            display = index.display_label(target)
            target_ranks.append(
                (
                    len(source_set.symmetric_difference(candidate_set)),
                    int("[" in display and "]" in display),
                    -len(candidate_set & source_set),
                )
            )
        if target_ranks:
            ranked.append((min(target_ranks), target))
    if not ranked:
        return None
    best_rank = min(rank for rank, _ in ranked)
    best = [target for rank, target in ranked if rank == best_rank]
    return best[0] if len(best) == 1 else None


def _recover_microanalysis_table_envelope_owners(
    anchors: Sequence[InventoryAnchor], facts: Sequence[AxisFact], source_text: str
) -> tuple[list[AxisFact], list[MaterializeIssue]]:
    """Restore lost EDS row locations and route them to one source-state owner."""

    fact_rows = list(facts)
    envelopes = _source_microanalysis_table_envelopes(source_text)
    if not envelopes:
        return fact_rows, []
    index = _build_identity_index(anchors, fact_rows)
    recovered: dict[tuple[Any, ...], dict[str, Any]] = {}
    for fact_index, fact in enumerate(fact_rows):
        # Existing explicit Point/Spot observations are handled by the older
        # source-state resolver.  This pass is only for locations lost into a
        # generic material label during cropped-table extraction.
        if _microanalysis_location_label(fact):
            continue
        location = _microanalysis_table_fact_location(fact)
        if not location:
            continue
        matches = [
            (envelope, component_matches)
            for envelope in envelopes
            if (
                component_matches := _microanalysis_envelope_component_matches(
                    fact, envelope
                )
            )
        ]
        if len(matches) != 1:
            continue
        envelope, component_matches = matches[0]
        data = deepcopy(fact.data)
        before_state = str(data.get("material_state") or "").strip()
        data["sample_id"] = envelope.location
        data["material_state"] = envelope.state
        data["source_evidence"] = list(
            dict.fromkeys(
                [
                    *_evidence(data.get("source_evidence")),
                    *envelope.context_evidence,
                    " | ".join(envelope.table_header),
                    " | ".join(envelope.source_row),
                ]
            )
        )
        grounded = fact.model_copy(
            update={
                "data": data,
                "source_evidence": list(
                    dict.fromkeys(
                        [
                            *fact.source_evidence,
                            *envelope.context_evidence,
                            " | ".join(envelope.table_header),
                            " | ".join(envelope.source_row),
                        ]
                    )
                ),
            }
        )
        target = _microanalysis_table_state_owner(index, envelope.state)
        if target is None:
            continue
        owner_state, owner_state_evidence = _microanalysis_complete_owner_state(
            index, target, envelope.state
        )
        routed_data = deepcopy(grounded.data)
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
        after_owner = index.display_label(target)
        routed = grounded.model_copy(
            update={
                "sample_id_raw": after_owner,
                "data": routed_data,
                "source_evidence": list(
                    dict.fromkeys(
                        [*grounded.source_evidence, *owner_state_evidence]
                    )
                ),
            }
        )
        fact_rows[fact_index] = routed
        audit_key = (
            target,
            _microanalysis_location_key(envelope.location),
            envelope.state,
            envelope.table_header,
            envelope.source_row,
        )
        audit = recovered.setdefault(
            audit_key,
            {
                "before_owners": [],
                "after_owner": after_owner,
                "locations": [],
                "before_states": [],
                "after_states": [],
                "facts": [],
                "context_evidence": [],
                "owner_evidence": [],
                "table_header": list(envelope.table_header),
                "source_row": list(envelope.source_row),
                "component_matches": [],
            },
        )
        audit["before_owners"].append(str(fact.sample_id_raw or "").strip())
        audit["locations"].append(envelope.location)
        audit["before_states"].append(before_state)
        audit["after_states"].append(owner_state)
        audit["facts"].append(fact.model_dump())
        audit["context_evidence"].extend(envelope.context_evidence)
        audit["owner_evidence"].extend(owner_state_evidence)
        audit["component_matches"].extend(component_matches)

    issues: list[MaterializeIssue] = []
    for audit in recovered.values():
        before_owners = list(dict.fromkeys(audit["before_owners"]))
        locations = list(dict.fromkeys(audit["locations"]))
        before_states = list(dict.fromkeys(audit["before_states"]))
        after_states = list(dict.fromkeys(audit["after_states"]))
        context_evidence = list(dict.fromkeys(audit["context_evidence"]))
        owner_evidence = list(dict.fromkeys(audit["owner_evidence"]))
        component_matches = list(
            {
                (
                    row["component"],
                    row["column"],
                    row["fact_value"],
                    row["source_value"],
                ): row
                for row in audit["component_matches"]
            }.values()
        )
        issues.append(
            MaterializeIssue(
                code="microanalysis_table_envelope_owner_recovered",
                sample_id_raw=audit["after_owner"],
                path=(
                    f"items.{audit['after_owner']}.Composition."
                    "Composition_Observations"
                ),
                message=(
                    "A cropped EDS/EDX table row was restored to the only "
                    "source-backed material state while preserving its "
                    "observation location."
                ),
                evidence=[*context_evidence, *owner_evidence],
                expected={
                    "table_envelope": "one exact EDS/EDX component row",
                    "owner": "one existing Target with the same source state",
                    "observation_location": "preserved Point/Spot/Area label",
                },
                actual={
                    "before_owner": before_owners[0]
                    if len(before_owners) == 1
                    else before_owners,
                    "after_owner": audit["after_owner"],
                    "observation_location": locations[0]
                    if len(locations) == 1
                    else locations,
                    "before_state": before_states[0]
                    if len(before_states) == 1
                    else before_states,
                    "after_state": after_states[0]
                    if len(after_states) == 1
                    else after_states,
                    "table_header": audit["table_header"],
                    "source_row": audit["source_row"],
                    "component_matches": component_matches,
                    "binding_evidence": context_evidence,
                    "owner_evidence": owner_evidence,
                    "facts": audit["facts"],
                },
                suggested_action=(
                    "Review only if the cited microanalysis row belongs to a "
                    "different material state."
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

    normalized = _normalize_state_markup(sentence)
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


@dataclass(frozen=True)
class _ProcessEnvironmentContext:
    family: str
    environment_key: str
    phrase: str
    evidence: str


def _process_family(value: Any) -> str | None:
    """Classify a process event coarsely enough to prevent context broadcast."""

    text = unicodedata.normalize("NFKC", str(value or "")).strip()
    if not text:
        return None
    families = [
        family for family, pattern in _PROCESS_FAMILY_PATTERNS if pattern.search(text)
    ]
    return families[0] if len(families) == 1 else None


def _environment_key(value: Any) -> str | None:
    text = str(value or "").casefold()
    for key in ("argon", "nitrogen", "helium", "hydrogen", "vacuum", "air"):
        if re.search(rf"\b{key}\b", text):
            return key
    if re.search(r"\binert\s+(?:gas|atmosphere|environment)\b", text):
        return "inert_unspecified"
    return None


def _source_process_environment_contexts(
    source_text: str | None,
) -> dict[str, _ProcessEnvironmentContext]:
    """Return one unambiguous source-reported environment per process family."""

    if not source_text:
        return {}
    segments = [
        row.strip()
        for row in re.split(r"(?<=[.!?])\s+|\n+", source_text)
        if row.strip() and not row.lstrip().startswith("|")
    ]
    candidates: dict[str, dict[str, list[_ProcessEnvironmentContext]]] = {}
    for segment in segments:
        family = _process_family(segment)
        if family is None:
            continue
        for match in _PROCESS_ENVIRONMENT_MENTION.finditer(segment):
            phrase = re.sub(r"\s+", " ", match.group("phrase")).strip()
            key = _environment_key(phrase)
            if key is None:
                continue
            window = segment[max(0, match.start() - 80) : match.end() + 80]
            if not _PROCESS_ENVIRONMENT_CUE.search(window):
                # Element/composition mentions such as "argon content" are not
                # processing environments and must never become conditions.
                continue
            context = _ProcessEnvironmentContext(
                family=family,
                environment_key=key,
                phrase=phrase,
                evidence=segment,
            )
            candidates.setdefault(family, {}).setdefault(key, []).append(context)

    resolved: dict[str, _ProcessEnvironmentContext] = {}
    for family, by_environment in candidates.items():
        if len(by_environment) != 1:
            # More than one reported atmosphere for the same process family is
            # a real experimental distinction. A paper-level rule cannot bind
            # either one safely without event-local evidence.
            continue
        rows = next(iter(by_environment.values()))
        resolved[family] = min(
            rows,
            key=lambda row: (
                "inert" not in row.phrase.casefold(),
                len(row.phrase),
                len(row.evidence),
            ),
        )
    return resolved


def _condition_has_environment(value: Any) -> bool:
    text = str(value or "").strip()
    return bool(text and _environment_key(text) is not None)


def _process_energy_source(value: Any) -> str | None:
    text = re.sub(r"[_-]+", " ", str(value or "")).casefold()
    text = re.sub(r"\s+", " ", text).strip()
    if not re.search(r"\bpower\b", text):
        return None
    for source, pattern in (
        ("hot_wire", r"\bhot\s+wire\b"),
        ("electron_beam", r"\b(?:electron\s+beam|e\s+beam)\b"),
        ("laser", r"\blaser\b"),
        ("wire", r"\bwire\b"),
        ("arc", r"\barc\b"),
    ):
        if re.search(pattern, text):
            return source
    return None


def _recover_process_environment_conditions(
    facts: Sequence[AxisFact], source_text: str | None
) -> tuple[list[AxisFact], list[MaterializeIssue]]:
    """Bind a unique source environment only to parameters of the same event family."""

    contexts = _source_process_environment_contexts(source_text)
    if not contexts:
        return list(facts), []

    recovered: list[AxisFact] = []
    issues: list[MaterializeIssue] = []
    for fact in facts:
        if fact.fact_type != "process_stage":
            recovered.append(fact)
            continue
        data = deepcopy(fact.data)
        process_name = str(data.get("process_name_raw") or "").strip()
        family = _process_family(process_name)
        context = contexts.get(family or "")
        parameters = data.get("parameters_raw")
        if context is None or not isinstance(parameters, list):
            recovered.append(fact)
            continue
        energy_sources = {
            source
            for parameter in parameters
            if isinstance(parameter, dict)
            if (
                source := _process_energy_source(
                    parameter.get("parameter_name_raw")
                )
            )
            is not None
        }
        if len(energy_sources) < 2:
            # Broadcasting one paper-level atmosphere over every parameter of
            # an ordinary single-energy or thermal stage is too broad. The
            # guarded case is a coupled-energy event (for example laser plus
            # hot wire) whose source table explicitly stores both power inputs
            # in the same stage.
            recovered.append(fact)
            continue
        if any(
            isinstance(parameter, dict)
            and _condition_has_environment(parameter.get("condition_label_raw"))
            for parameter in parameters
        ):
            # One event-local environment on any parameter is authoritative
            # for this stage. Do not partially mix it with a paper-level value.
            recovered.append(fact)
            continue

        condition = f"{process_name} in {context.phrase}".strip()
        before = deepcopy(parameters)
        changed = 0
        for parameter in parameters:
            if not isinstance(parameter, dict):
                continue
            existing = str(parameter.get("condition_label_raw") or "").strip()
            if _condition_has_environment(existing):
                # Preserve provider-local atmosphere distinctions; even a
                # paper-level unique context must not overwrite them.
                continue
            parameter["condition_label_raw"] = (
                f"{existing} | {condition}" if existing else condition
            )
            changed += 1
        if not changed:
            recovered.append(fact)
            continue

        updated = fact.model_copy(update={"data": data})
        recovered.append(updated)
        issues.append(
            MaterializeIssue(
                code="process_environment_context_recovered",
                sample_id_raw=fact.sample_id_raw,
                path=f"items.{fact.sample_id_raw}.Processing",
                message=(
                    "A unique source-reported process environment was bound to "
                    "parameters of the same process family."
                ),
                evidence=[context.evidence],
                expected={
                    "binding": "one environment within one process family",
                    "coupled_energy_sources": sorted(energy_sources),
                    "cross_family_broadcast": False,
                    "overwrite_existing_environment": False,
                },
                actual={
                    "process_name_raw": process_name,
                    "process_family": family,
                    "environment_key": context.environment_key,
                    "coupled_energy_sources": sorted(energy_sources),
                    "condition_label_raw": condition,
                    "before": before,
                    "after": deepcopy(parameters),
                    "fact": updated.model_dump(),
                },
                suggested_action=(
                    "Review only if the paper applies multiple atmospheres to "
                    "this same process family without event-local labels."
                ),
            )
        )
    return recovered, issues


def _unique_discrete_sidecar_target_base(
    anchors: Sequence[InventoryAnchor],
) -> tuple[InventoryAnchor | None, list[dict[str, Any]]]:
    """Return one source-backed Target material family for chart result rows."""

    def material_family_key(value: Any) -> str:
        text = unicodedata.normalize("NFKC", str(value or "")).strip()
        text = re.sub(
            r"(?i)\s+(?:(?:super)?alloys?|materials?|specimens?)\s*$", "", text
        ).strip()
        return _identity_key(text)

    target_rows = [
        anchor
        for anchor in anchors
        if str(anchor.role or "").casefold() == "target"
    ]
    strong_families: set[str] = set()
    for anchor in target_rows:
        sample_name = str(anchor.sample_id_raw or "").strip()
        material_name = str(anchor.material_name_raw or "").strip()
        sample_family = material_family_key(sample_name)
        material_family = material_family_key(material_name)
        descriptor = _state_descriptor(sample_name)
        if _table_column_label(sample_name) is not None:
            continue
        if descriptor is not None and not descriptor[0].startswith("raw:"):
            continue
        if material_family and sample_family == material_family:
            strong_families.add(material_family)
        elif not material_name and sample_family:
            strong_families.add(sample_family)

    candidates: list[tuple[str, InventoryAnchor]] = []
    audit_rows: list[dict[str, Any]] = []
    for anchor in target_rows:
        material_name = str(anchor.material_name_raw or "").strip()
        sample_name = str(anchor.sample_id_raw or "").strip()
        family_key = material_family_key(material_name) or material_family_key(
            sample_name
        )
        if family_key not in strong_families:
            continue
        candidates.append((family_key, anchor))
        audit_rows.append(
            {
                "family_key": family_key,
                "sample_id_raw": anchor.sample_id_raw,
                "material_name_raw": anchor.material_name_raw,
                "state_raw": anchor.state_raw,
                "role": anchor.role,
            }
        )
    if len(strong_families) != 1:
        return None, audit_rows
    family = next(iter(strong_families))
    rows = [anchor for key, anchor in candidates if key == family]
    representative = min(
        rows,
        key=lambda anchor: (
            _identity_key(anchor.sample_id_raw)
            != _identity_key(anchor.material_name_raw),
            not _is_unresolved_alias(anchor.state_raw),
            "[" in str(anchor.sample_id_raw),
            len(str(anchor.sample_id_raw)),
            str(anchor.sample_id_raw).casefold(),
        ),
    )
    return representative, audit_rows


def _sidecar_tensile_test_condition(source_text: str, reference: str) -> str:
    """Return one literal tensile temperature in the sidecar's bounded block."""

    marker = f"data_csv: {reference}"
    position = source_text.find(marker)
    if position < 0 or source_text.find(marker, position + len(marker)) >= 0:
        return ""
    # Chart enrichment places the result prose immediately around the marker.
    # Keep the window short and stop at the next enriched figure so another
    # experiment's temperature cannot leak into this coordinate.
    start = max(0, source_text.rfind("> [Figure", 0, position))
    end_candidates = [
        value
        for value in (
            source_text.find("\n> [Figure", position + len(marker)),
            source_text.find("\n## ", position + len(marker)),
            position + 1800,
        )
        if value >= 0
    ]
    end = min(end_candidates) if end_candidates else min(len(source_text), position + 1800)
    window = source_text[start : min(end, len(source_text))]
    candidates = {
        match.group(0)
        for match in re.finditer(r"(?i)\broom[\s-]+temperature\b", window)
        if re.search(
            r"(?is)\b(?:tensile|yield|elongation|strength)\b.{0,180}"
            + re.escape(match.group(0))
            + r"|"
            + re.escape(match.group(0))
            + r".{0,180}\b(?:tensile|yield|elongation|strength)\b",
            window,
        )
    }
    normalized = {normalize_source_alias(value): value for value in candidates}
    return next(iter(normalized.values())) if len(normalized) == 1 else ""


_SOURCE_TENSILE_SPECIMEN_DESCRIPTOR = re.compile(
    r"(?i)\b(?P<descriptor>(?:hexagonal|dog[- ]?bone(?:[- ]shaped)?|"
    r"cylindrical|flat|round|miniature|subsize|standard)\s+"
    r"tensile\s+specimens?)\b"
)


def _sidecar_state_owner_base_label(base_label: str, source_text: str) -> str:
    """Preserve one literal tensile-specimen geometry in a sidecar owner.

    A categorical chart row describes tested specimens, not a new alloy.  When
    the paper names exactly one bounded specimen geometry, retain that literal
    descriptor in the state-qualified child owner.  Ambiguous or absent
    descriptors leave the proven base label unchanged.
    """

    descriptors: dict[str, str] = {}
    for match in _SOURCE_TENSILE_SPECIMEN_DESCRIPTOR.finditer(source_text):
        literal = re.sub(r"(?i)specimens$", "specimen", match.group("descriptor"))
        descriptors.setdefault(normalize_source_alias(literal), literal)
    if len(descriptors) != 1:
        return base_label
    descriptor = next(iter(descriptors.values()))
    if normalize_source_alias(descriptor) in normalize_source_alias(base_label):
        return base_label
    return f"{base_label} {descriptor}"


def _promote_discrete_tensile_sidecars_v202(
    anchors: Sequence[InventoryAnchor],
    facts: Sequence[AxisFact],
    *,
    source_text: str,
    source_dir: Path | str | None,
) -> tuple[list[InventoryAnchor], list[AxisFact], list[MaterializeIssue]]:
    """Create Properties only from bounded literal categorical chart cells."""

    anchor_rows = list(anchors)
    fact_rows = list(facts)
    if (
        not discrete_chart_sidecar_v202_enabled()
        or not source_text
        or source_dir is None
    ):
        return anchor_rows, fact_rows, []

    decisions = discrete_tensile_sidecars(source_text, source_dir)
    issues: list[MaterializeIssue] = []
    eligible = [decision for decision in decisions if decision.status == "eligible"]
    for decision in decisions:
        if decision.status == "continuous":
            issues.append(
                MaterializeIssue(
                    code="continuous_curve_sidecar_not_promoted",
                    severity="info",
                    sample_id_raw="paper",
                    path="source_sidecars",
                    message=(
                        "A continuous or oversized chart sidecar remained external "
                        "and produced no Property rows."
                    ),
                    evidence=[f"data_csv: {decision.reference}"],
                    expected={
                        "continuous_curve_points_promoted": 0,
                        "full_csv_in_model_context": False,
                    },
                    actual={"decision": decision.to_dict()},
                    suggested_action=(
                        "Use the preserved CSV for curve-specific analysis; do not "
                        "materialize sampled points as scalar Properties."
                    ),
                )
            )
        elif decision.status == "rejected":
            issues.append(
                MaterializeIssue(
                    code="discrete_chart_sidecar_rejected",
                    sample_id_raw="paper",
                    path="source_sidecars",
                    message=(
                        "A source-referenced sidecar failed the bounded categorical "
                        "or filesystem-safety contract and produced no facts."
                    ),
                    evidence=[f"data_csv: {decision.reference}"],
                    expected={
                        "path": "one regular file below the paper source directory",
                        "shape": "bounded categorical result table",
                    },
                    actual={"decision": decision.to_dict()},
                    suggested_action="Review the preserved sidecar and source reference.",
                )
            )
    if not eligible:
        return anchor_rows, fact_rows, issues

    base, owner_candidates = _unique_discrete_sidecar_target_base(anchor_rows)
    if base is None or not owner_state_condition_v202_enabled():
        for decision in eligible:
            issues.append(
                MaterializeIssue(
                    code="discrete_chart_sidecar_rejected",
                    sample_id_raw="paper",
                    path="source_sidecars",
                    message=(
                        "An eligible categorical tensile sidecar was not promoted "
                        "because one Target base owner was not uniquely provable."
                    ),
                    evidence=[f"data_csv: {decision.reference}"],
                    expected={
                        "target_base_owner_count": 1,
                        "owner_state_condition_gate": True,
                    },
                    actual={
                        "decision": decision.to_dict(),
                        "candidate_owners": owner_candidates,
                        "owner_state_condition_gate": (
                            owner_state_condition_v202_enabled()
                        ),
                    },
                    suggested_action=(
                        "Promote only after the inventory names one Target material "
                        "family for the categorical result rows."
                    ),
                )
            )
        return anchor_rows, fact_rows, issues

    base_label = str(base.sample_id_raw).strip()
    state_owner_base_label = _sidecar_state_owner_base_label(
        base_label, source_text
    )
    base_family = _identity_key(base.material_name_raw or base_label)
    existing_state_owners: dict[str, set[str]] = {}
    for anchor in anchor_rows:
        family = _identity_key(anchor.material_name_raw or anchor.sample_id_raw)
        state_alias = normalize_source_alias(anchor.state_raw)
        if family == base_family and state_alias:
            existing_state_owners.setdefault(state_alias, set()).add(
                str(anchor.sample_id_raw).strip()
            )
    for decision in eligible:
        test_condition = _sidecar_tensile_test_condition(
            source_text, decision.reference
        )
        for row in decision.rows:
            evidence = [
                f"data_csv: {decision.reference}",
                row.raw_row,
            ]
            state_alias = normalize_source_alias(row.condition)
            row_owner_candidates = existing_state_owners.get(state_alias, set())
            if len(row_owner_candidates) > 1:
                issues.append(
                    MaterializeIssue(
                        code="discrete_chart_sidecar_rejected",
                        sample_id_raw=base_label,
                        path="source_sidecars",
                        message=(
                            "A categorical sidecar row matched more than one existing "
                            "state-qualified Target owner and was not promoted."
                        ),
                        evidence=evidence,
                        expected={"state_owner_count": 1},
                        actual={
                            "literal_sidecar_row": row.to_dict(),
                            "candidate_owners": sorted(row_owner_candidates),
                            "sidecar_hash": decision.content_sha256,
                        },
                        suggested_action="Review the duplicate state owner inventory.",
                    )
                )
                continue
            owner_created = not row_owner_candidates
            row_owner = (
                next(iter(row_owner_candidates))
                if row_owner_candidates
                else f"{state_owner_base_label} [{row.condition}]"
            )
            state_anchor: InventoryAnchor | None = None
            if owner_created:
                state_anchor = InventoryAnchor(
                    sample_id_raw=row_owner,
                    material_name_raw=base.material_name_raw or base_label,
                    state_raw=row.condition,
                    role=base.role,
                    data_nature=base.data_nature,
                    source_evidence=evidence,
                    confidence=0.95,
                )
                anchor_rows.append(state_anchor)
                existing_state_owners.setdefault(state_alias, set()).add(row_owner)
                issues.append(
                    MaterializeIssue(
                        code="source_literal_owner_state_recovered",
                        severity="info",
                        sample_id_raw=row_owner,
                        path=f"items.{row_owner}",
                        message=(
                            "A categorical sidecar row created one state-qualified "
                            "child of the unique Target base owner."
                        ),
                        evidence=evidence,
                        expected={
                            "base_owner_count": 1,
                            "owner_invented": False,
                            "orientation_as_material_state": False,
                        },
                        actual={
                            "base_owner": base.model_dump(),
                            "created_anchor": state_anchor.model_dump(),
                            "literal_sidecar_row": row.to_dict(),
                            "sidecar_hash": decision.content_sha256,
                            "owner_invented": False,
                            "owner_created_from_source_literal": True,
                        },
                        suggested_action=(
                            "Review only if the CSV condition is not a preparation "
                            "state of the reported Target material."
                        ),
                    )
                )
            for cell in row.properties:
                property_evidence = [
                    f"data_csv: {decision.reference}",
                    cell.header_raw,
                    row.raw_row,
                ]
                fact = PropertyFact(
                    sample_id_raw=row_owner,
                    fact_type="property",
                    data={
                        "property_id_candidate": cell.decision_key,
                        "property_name_raw": cell.property_name,
                        "value_raw": cell.value_raw,
                        "unit_raw": cell.unit_raw,
                        "test_method_raw": "tensile test",
                        "test_standard_raw": "",
                        "test_condition_raw": test_condition,
                        "test_specimen_raw": row.orientation,
                        "raw_note": row.raw_row,
                        # Keep digitized provenance distinct inside Alpha25 so
                        # generic image-owner routing cannot reinterpret a
                        # state label as a material owner.  The public-schema
                        # converter maps this to its existing ``image`` enum.
                        "data_source": "image_digitized",
                        "source_evidence": property_evidence,
                        "confidence": 0.95,
                    },
                    source_evidence=property_evidence,
                    confidence=0.95,
                )
                fact_rows.append(fact)
                issues.append(
                    MaterializeIssue(
                        code="discrete_chart_property_recovered",
                        severity="info",
                        sample_id_raw=row_owner,
                        path=f"items.{row_owner}.Properties",
                        message=(
                            "One literal numeric cell from a bounded categorical "
                            "sidecar was materialized as a Property."
                        ),
                        evidence=property_evidence,
                        expected={
                            "source_cell_count": 1,
                            "owner_count": 1,
                            "cross_row_or_owner_broadcast": False,
                            "continuous_curve_point": False,
                        },
                        actual={
                            "literal_sidecar_row": row.to_dict(),
                            "property_cell": cell.to_dict(),
                            "sidecar_path": decision.reference,
                            "sidecar_hash": decision.content_sha256,
                            "source_kind": "image_digitized",
                            "test_condition_raw": test_condition,
                            "base_owner": base.model_dump(),
                            "owner_candidates": owner_candidates,
                            "owner_invented": False,
                            "owner_created_from_source_literal": owner_created,
                            "fact": fact.model_dump(),
                            "decision_key": cell.decision_key,
                        },
                        suggested_action=(
                            "Review the preserved CSV row if the chart digitization "
                            "or categorical label is disputed."
                        ),
                    )
                )
    return anchor_rows, fact_rows, issues


def _dense_target_owner_aliases(
    anchors: Sequence[InventoryAnchor],
) -> dict[str, tuple[str, ...]]:
    aliases: dict[str, tuple[str, ...]] = {}
    for anchor in sorted(
        anchors,
        key=lambda row: (
            str(row.sample_id_raw).casefold(),
            str(row.state_raw or "").casefold(),
        ),
    ):
        if str(anchor.role or "").strip().casefold() != "target":
            continue
        owner = str(anchor.sample_id_raw).strip()
        material = str(anchor.material_name_raw or "").strip()
        state = str(anchor.state_raw or "").strip()
        candidates = [owner, material, state]
        if state:
            candidates.extend(
                f"{base} {state}" for base in (owner, material) if base
            )
        aliases[owner] = tuple(
            dict.fromkeys(value for value in candidates if value)
        )
    return aliases


def _fact_owns_dense_cell(fact: AxisFact, cell: DenseTensileCell) -> bool:
    if not isinstance(fact, PropertyFact):
        return False
    data = fact.data
    if _identity_key(fact.sample_id_raw) != _identity_key(cell.owner):
        return False
    if core_tensile_subtype(data.get("property_name_raw")) != core_tensile_subtype(
        cell.property_name
    ):
        return False
    if normalize_source_alias(data.get("value_raw")) != normalize_source_alias(
        cell.value_raw
    ):
        return False
    if normalize_source_alias(data.get("unit_raw")) != normalize_source_alias(
        cell.unit_raw
    ):
        return False
    evidence_rows = [
        normalize_source_alias(line)
        for raw in fact.source_evidence
        for line in str(raw or "").splitlines()
        if "|" in line
    ]
    evidence = normalize_source_alias("\n".join(fact.source_evidence))
    value = normalize_source_alias(cell.value_raw)
    owner = normalize_source_alias(cell.owner_literal)
    headers = {
        normalize_source_alias(header)
        for header in cell.header_path
        if normalize_source_alias(header)
    }
    property_headers = {header for header in headers if header != owner}
    # Exact owner/property/value/unit equality was established above.  The
    # ordinary column-oriented form still requires owner, header, and value
    # somewhere in the fact evidence.  A row-oriented ``Property | Sample``
    # table can instead prove the cell with one literal property/value row,
    # because the exact fact owner already identifies the selected column.
    # Do not accept a sample/value row alone: that weaker shape is precisely
    # the alias case that v203 must migrate and reconcile.
    return bool(
        value
        and (
            (
                evidence
                and owner in evidence
                and value in evidence
                and any(header in evidence for header in property_headers)
            )
            or any(
                value in row
                and any(header in row for header in property_headers)
                for row in evidence_rows
            )
        )
    )


def _fact_matches_dense_scientific_coordinate(
    fact: AxisFact, cell: DenseTensileCell
) -> bool:
    """Match a literal property/value/unit coordinate without guessing owner.

    This is used only when both the existing fact and the table each expose a
    single occurrence of the same scientific coordinate.  It prevents a prose
    alias such as ``WA`` and a table state label such as ``WA sample sintered
    at ...`` from materializing the same tensile value twice.
    """

    if not isinstance(fact, PropertyFact):
        return False
    return bool(
        core_tensile_subtype(fact.data.get("property_name_raw"))
        == core_tensile_subtype(cell.property_name)
        and normalize_source_alias(fact.data.get("value_raw"))
        == normalize_source_alias(cell.value_raw)
        and normalize_source_alias(fact.data.get("unit_raw"))
        == normalize_source_alias(cell.unit_raw)
    )


def _dense_owner_compatible(existing_owner: Any, cell_owner: str) -> bool:
    """Return whether a short source alias belongs to the explicit table owner."""

    if _identity_key(existing_owner) == _identity_key(cell_owner):
        return True
    existing_text = _normalize_state_markup(existing_owner).casefold()
    cell_text = _normalize_state_markup(cell_owner).casefold()
    existing_tokens = [
        token
        for token in re.findall(r"[a-z0-9]+", existing_text)
        if token not in {"sample", "samples", "specimen", "specimens"}
    ]
    cell_tokens = [
        token
        for token in re.findall(r"[a-z0-9]+", cell_text)
        if token not in {"sample", "samples", "specimen", "specimens"}
    ]
    # A bare material code can qualify a state-bearing table row only when it
    # is the literal leading token.  This does not equate prefix variants such
    # as PBF and PBF-EB.
    return bool(
        len(existing_tokens) == 1
        and len(existing_tokens[0]) >= 2
        and cell_tokens
        and existing_tokens[0] == cell_tokens[0]
        and len(cell_tokens) >= 3
    )


def _dense_condition_is_owner_state(condition: Any, cell_owner: str) -> bool:
    """Identify a process-state phrase misfiled as a tensile test condition."""

    condition_key = normalize_source_alias(_normalize_state_markup(condition))
    owner_key = normalize_source_alias(_normalize_state_markup(cell_owner))
    return bool(condition_key and len(condition_key) >= 4 and condition_key in owner_key)


def _promote_dense_tensile_tables_v203(
    anchors: Sequence[InventoryAnchor],
    facts: Sequence[AxisFact],
    *,
    source_text: str,
) -> tuple[list[AxisFact], list[MaterializeIssue]]:
    """Create Properties only from unique explicit Target tensile cells."""

    fact_rows = list(facts)
    if not dense_tensile_table_completion_v203_enabled() or not source_text:
        return fact_rows, []
    owner_aliases = _dense_target_owner_aliases(anchors)
    if not owner_aliases:
        return fact_rows, []

    decisions = dense_tensile_table_decisions(source_text, owner_aliases)
    issues: list[MaterializeIssue] = []
    for decision in decisions:
        if decision.status == "rejected":
            issues.append(
                MaterializeIssue(
                    code="dense_tensile_table_cell_rejected",
                    sample_id_raw="paper",
                    path="source_tables",
                    message=(
                        "An explicit-looking tensile table failed the unique Target "
                        "cell coordinate contract and produced no Property."
                    ),
                    evidence=[],
                    expected={
                        "target_owner_count": 1,
                        "property_unit_value_coordinate_count": 1,
                    },
                    actual={"decision": decision.to_dict()},
                    suggested_action=(
                        "Review the table owner/header coordinates; do not restore "
                        "a cell while the ambiguity remains."
                    ),
                )
            )
            continue
        if decision.status != "eligible":
            continue
        for cell in decision.cells:
            scientific_matches = [
                fact
                for fact in fact_rows
                if _fact_matches_dense_scientific_coordinate(fact, cell)
            ]
            table_coordinate_matches = [
                peer
                for peer in decision.cells
                if (
                    core_tensile_subtype(peer.property_name),
                    normalize_source_alias(peer.value_raw),
                    normalize_source_alias(peer.unit_raw),
                )
                == (
                    core_tensile_subtype(cell.property_name),
                    normalize_source_alias(cell.value_raw),
                    normalize_source_alias(cell.unit_raw),
                )
            ]
            exact_owner_matches = [
                fact
                for fact in scientific_matches
                if _identity_key(fact.sample_id_raw) == _identity_key(cell.owner)
            ]
            existing = next(
                (
                    fact
                    for fact in exact_owner_matches
                    if _fact_owns_dense_cell(fact, cell)
                ),
                None,
            )
            if existing is not None:
                issues.append(
                    MaterializeIssue(
                        code="dense_tensile_table_cell_rejected",
                        severity="info",
                        sample_id_raw=cell.owner,
                        path=f"items.{cell.owner}.Properties",
                        message=(
                            "The dense table cell was not completed because an "
                            "existing Property already owns the same source coordinate."
                        ),
                        evidence=list(cell.source_rows),
                        expected={"one_coordinate_one_fact": True},
                        actual={
                            "reason": "existing_coordinate_owned",
                            "cell": cell.to_dict(),
                            "existing_fact": existing.model_dump(),
                        },
                        suggested_action=(
                            "Keep the existing grounded fact unless its coordinate "
                            "audit proves a conflict."
                        ),
                    )
                )
                continue
            compatible_existing = (
                [
                    fact
                    for fact in scientific_matches
                    if _dense_owner_compatible(fact.sample_id_raw, cell.owner)
                ]
                if len(table_coordinate_matches) == 1 and exact_owner_matches
                else []
            )
            scientific_existing = max(
                compatible_existing,
                default=None,
                key=lambda fact: (
                    _identity_key(fact.sample_id_raw) == _identity_key(cell.owner),
                    sum(value not in (None, "", [], {}) for value in fact.data.values()),
                    float(fact.confidence or 0.0),
                ),
            )
            if scientific_existing is not None:
                fact_rows = [
                    fact for fact in fact_rows if fact not in compatible_existing
                ]
            evidence = list(
                dict.fromkeys(
                    [
                        *cell.source_rows,
                        *(
                            row
                            for existing_fact in compatible_existing
                            for row in existing_fact.source_evidence
                        ),
                    ]
                )
            )
            existing_data = (
                dict(scientific_existing.data)
                if scientific_existing is not None
                else {}
            )
            existing_condition = existing_data.get("test_condition_raw") or ""
            if _dense_condition_is_owner_state(existing_condition, cell.owner):
                existing_condition = ""
            fact = PropertyFact(
                sample_id_raw=cell.owner,
                fact_type="property",
                data={
                    **existing_data,
                    "property_id_candidate": cell.decision_key,
                    "property_name_raw": cell.property_name,
                    "value_raw": cell.value_raw,
                    "unit_raw": cell.unit_raw,
                    "test_method_raw": existing_data.get("test_method_raw")
                    or "tensile test",
                    "test_standard_raw": existing_data.get("test_standard_raw")
                    or "",
                    "test_condition_raw": existing_condition,
                    "test_specimen_raw": cell.orientation
                    or existing_data.get("test_specimen_raw")
                    or "",
                    "raw_note": cell.owner_literal,
                    "data_source": "table",
                    "source_evidence": evidence,
                    "confidence": max(
                        0.99,
                        float(
                            getattr(scientific_existing, "confidence", 0.0) or 0.0
                        ),
                    ),
                },
                source_evidence=evidence,
                confidence=max(
                    0.99,
                    float(getattr(scientific_existing, "confidence", 0.0) or 0.0),
                ),
            )
            fact_rows.append(fact)
            issues.append(
                MaterializeIssue(
                    code="dense_tensile_table_cell_recovered",
                    severity="info",
                    sample_id_raw=cell.owner,
                    path=f"items.{cell.owner}.Properties",
                    message=(
                        "One explicit numeric Target tensile table cell was "
                        "completed as an ordinary Property."
                    ),
                    evidence=evidence,
                    expected={
                        "source_cell_count": 1,
                        "owner_count": 1,
                        "caption_inference": False,
                        "continuous_curve_point": False,
                    },
                    actual={
                        "before": (
                            scientific_existing.model_dump()
                            if scientific_existing is not None
                            else None
                        ),
                        "after": fact.model_dump(),
                        "cell": cell.to_dict(),
                        "decision": decision.to_dict(),
                    },
                    suggested_action=(
                        "Review the preserved logical table coordinate if the "
                        "source cell is disputed."
                    ),
                )
            )
    return fact_rows, issues


def _source_coordinate_fact_signature(
    fact: PropertyFact,
    owner_roles: Mapping[str, tuple[tuple[str, str], ...]],
) -> tuple[Any, ...]:
    data = fact.data
    return (
        _identity_key(fact.sample_id_raw),
        owner_roles.get(_identity_key(fact.sample_id_raw), ()),
        normalize_source_alias(data.get("property_name_raw")),
        normalize_source_alias(data.get("value_raw")),
        normalize_source_alias(data.get("unit_raw")),
        normalize_source_alias(
            data.get("material_state")
            or data.get("material_state_raw")
            or data.get("state_raw")
        ),
        normalize_source_alias(data.get("test_condition_raw")),
        normalize_source_alias(data.get("test_specimen_raw")),
    )


def _merge_coordinate_duplicate_facts(
    rows: Sequence[PropertyFact],
) -> PropertyFact:
    """Return one deterministic, evidence-rich survivor for exact duplicates."""

    ordered = sorted(
        rows,
        key=lambda fact: (
            sum(
                fact.data.get(key) not in (None, "", [], {})
                for key in (
                    "property_name_raw",
                    "value_raw",
                    "unit_raw",
                    "test_method_raw",
                    "test_standard_raw",
                    "test_condition_raw",
                    "test_specimen_raw",
                    "raw_note",
                )
            ),
            len(fact.source_evidence),
            float(fact.confidence or 0.0),
            json.dumps(
                fact.model_dump(),
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            ),
        ),
    )
    survivor = ordered[-1]
    evidence = list(
        dict.fromkeys(
            row
            for fact in ordered
            for row in fact.source_evidence
            if str(row or "").strip()
        )
    )
    data = dict(survivor.data)
    if "source_evidence" in data:
        data["source_evidence"] = list(evidence)
    return survivor.model_copy(
        deep=True,
        update={
            "data": data,
            "source_evidence": evidence,
            "confidence": max(float(fact.confidence or 0.0) for fact in rows),
        },
    )


def _v203_coordinate_conflict_code(rows: Sequence[PropertyFact]) -> str:
    owners = {_identity_key(fact.sample_id_raw) for fact in rows}
    if len(owners) > 1:
        return "property_cross_owner_projection_quarantined"
    scientific_coordinates = {
        (
            core_tensile_subtype(fact.data.get("property_name_raw"))
            or normalize_source_alias(fact.data.get("property_name_raw")),
            normalize_source_alias(fact.data.get("value_raw")),
            normalize_source_alias(fact.data.get("unit_raw")),
        )
        for fact in rows
    }
    if len(scientific_coordinates) > 1:
        return "property_cross_cell_projection_quarantined"
    provenance = {
        normalize_source_alias(fact.data.get("data_source")) for fact in rows
    }
    conditions = {
        normalize_source_alias(fact.data.get("test_condition_raw")) for fact in rows
    }
    if len(provenance) > 1 and len(conditions) > 1:
        return "property_role_protocol_leakage_quarantined"
    return "property_coordinate_conflict_quarantined"


def _gate_v202_source_coordinate_facts(
    anchors: Sequence[InventoryAnchor], facts: Sequence[AxisFact]
) -> tuple[list[AxisFact], list[MaterializeIssue]]:
    """Enforce one compatible Property per immutable structured coordinate."""

    v202_enabled = source_coordinate_precision_v202_enabled()
    v203_enabled = property_coordinate_quarantine_v203_enabled()
    if not v202_enabled and not v203_enabled:
        return list(facts), []
    owner_roles: dict[str, tuple[tuple[str, str], ...]] = {}
    for anchor in anchors:
        key = _identity_key(anchor.sample_id_raw)
        if not key:
            continue
        roles = set(owner_roles.get(key, ()))
        roles.add(
            (
                str(anchor.role or "").strip(),
                str(anchor.data_nature or "").strip(),
            )
        )
        owner_roles[key] = tuple(sorted(roles))

    groups: dict[str, list[PropertyFact]] = {}
    for fact in facts:
        if not isinstance(fact, PropertyFact):
            continue
        decision_key = str(fact.data.get("property_id_candidate") or "").strip()
        eligible = (
            v202_enabled and decision_key.startswith("sidecar-cell:")
        ) or (
            v203_enabled and decision_key.startswith("dense-table-cell:")
        )
        if not eligible:
            continue
        groups.setdefault(decision_key, []).append(fact)

    replacements: dict[int, PropertyFact] = {}
    removed: set[int] = set()
    issues: list[MaterializeIssue] = []
    for decision_key, rows in sorted(groups.items()):
        if len(rows) < 2:
            continue
        signatures = {
            _source_coordinate_fact_signature(fact, owner_roles) for fact in rows
        }
        if len(signatures) != 1:
            conflict_code = (
                _v203_coordinate_conflict_code(rows)
                if decision_key.startswith("dense-table-cell:") and v203_enabled
                else "source_coordinate_conflict_quarantined"
            )
            conflict_set = [
                fact.model_dump()
                for fact in sorted(
                    rows,
                    key=lambda fact: json.dumps(
                        fact.model_dump(), ensure_ascii=False, sort_keys=True
                    ),
                )
            ]
            for fact in rows:
                removed.add(id(fact))
                issues.append(
                    MaterializeIssue(
                        code=conflict_code,
                        sample_id_raw=fact.sample_id_raw,
                        path=f"items.{fact.sample_id_raw}.Extracted_Data.Properties",
                        message=(
                            "Incompatible owner/property/value/unit/state records shared "
                            "one immutable sidecar cell coordinate and were isolated."
                        ),
                        evidence=list(fact.source_evidence),
                        expected={
                            "one_coordinate_one_compatible_fact": True,
                            "broadcast": False,
                        },
                        actual={
                            "decision_key": decision_key,
                            "removed": fact.model_dump(),
                            "conflict_set": conflict_set,
                        },
                        suggested_action=(
                            "Review the preserved sidecar cell; restore only after the "
                            "owner and scientific value conflict is resolved."
                        ),
                    )
                )
            continue

        survivor = _merge_coordinate_duplicate_facts(rows)
        survivor_source = max(
            rows,
            key=lambda fact: (
                fact.model_dump() == survivor.model_dump(),
                json.dumps(fact.model_dump(), ensure_ascii=False, sort_keys=True),
            ),
        )
        replacements[id(survivor_source)] = survivor
        for fact in rows:
            if fact is survivor_source:
                continue
            removed.add(id(fact))
            issues.append(
                MaterializeIssue(
                    code=(
                        "property_same_coordinate_duplicate_merged"
                        if decision_key.startswith("dense-table-cell:")
                        and v203_enabled
                        else "source_coordinate_duplicate_quarantined"
                    ),
                    sample_id_raw=survivor.sample_id_raw,
                    path=f"items.{survivor.sample_id_raw}.Extracted_Data.Properties",
                    message=(
                        "An exact duplicate of one immutable sidecar cell was merged "
                        "into a single evidence-rich Property."
                    ),
                    evidence={
                        "removed": list(fact.source_evidence),
                        "survivor": list(survivor.source_evidence),
                    },
                    expected={
                        "one_coordinate_one_compatible_fact": True,
                        "unique_survivor": True,
                    },
                    actual={
                        "decision_key": decision_key,
                        "removed": fact.model_dump(),
                        "survivor_before": survivor_source.model_dump(),
                        "survivor_after": survivor.model_dump(),
                    },
                    suggested_action=(
                        "Review only if the two records represent distinct physical "
                        "measurements despite sharing one literal cell."
                    ),
                )
            )
    return [
        replacements.get(id(fact), fact)
        for fact in facts
        if id(fact) not in removed
    ], issues


_QUALITATIVE_TENSILE_COMPARISON = re.compile(
    r"(?ix)\b(?:higher|lower|stronger|weaker|superior|inferior|similar|"
    r"comparable|approximately\s+equal|nearly\s+the\s+same)\b"
    r"[^.;\n]{0,100}\b(?:tensile\s+strength|yield\s+(?:strength|stress)|"
    r"elongation|ductility)\b|"
    r"\b(?:tensile\s+strength|yield\s+(?:strength|stress)|elongation|ductility)\b"
    r"[^.;\n]{0,100}\b(?:higher|lower|stronger|weaker|superior|inferior|"
    r"similar|comparable|approximately\s+equal|nearly\s+the\s+same)\b"
)


def _numeric_tokens(value: Any) -> set[str]:
    tokens: set[str] = set()
    for raw in re.findall(r"[-+]?\d+(?:\.\d+)?", str(value or "")):
        try:
            number = float(raw)
        except ValueError:
            continue
        tokens.add(f"{number:.12g}")
    return tokens


def _quarantine_v203_semantic_property_projections(
    facts: Sequence[AxisFact],
) -> tuple[list[AxisFact], list[MaterializeIssue]]:
    """Remove only numeric tensile scalars disproven by their own evidence."""

    if not property_coordinate_quarantine_v203_enabled():
        return list(facts), []
    accepted: list[AxisFact] = []
    issues: list[MaterializeIssue] = []
    for fact in facts:
        if not isinstance(fact, PropertyFact) or not core_tensile_subtype(
            fact.data.get("property_name_raw")
        ):
            accepted.append(fact)
            continue
        value_numbers = _numeric_tokens(fact.data.get("value_raw"))
        evidence_text = "\n".join(fact.source_evidence)
        evidence_numbers = _numeric_tokens(evidence_text)
        if (
            not value_numbers
            or value_numbers & evidence_numbers
            or _QUALITATIVE_TENSILE_COMPARISON.search(evidence_text) is None
        ):
            accepted.append(fact)
            continue
        issues.append(
            MaterializeIssue(
                code="property_semantic_projection_quarantined",
                sample_id_raw=fact.sample_id_raw,
                path=f"items.{fact.sample_id_raw}.Properties",
                message=(
                    "A qualitative tensile comparison was projected into a numeric "
                    "scalar that does not occur in its own evidence and was isolated."
                ),
                evidence=list(fact.source_evidence),
                expected={
                    "numeric_scalar": "literal in the local source evidence",
                    "qualitative_comparison_as_scalar": False,
                },
                actual={
                    "removed": fact.model_dump(),
                    "value_numeric_tokens": sorted(value_numbers),
                    "evidence_numeric_tokens": sorted(evidence_numbers),
                    "reason": "qualitative_comparison_without_literal_scalar",
                },
                suggested_action=(
                    "Retain the comparative source statement in audit; restore a "
                    "formal Property only when a numeric value is literal."
                ),
            )
        )
    return accepted, issues


def materialize_candidate(
    anchors: Iterable[InventoryAnchor],
    facts: Iterable[AxisFact],
    *,
    paper_metadata: dict[str, Any] | None = None,
    paper_routing: dict[str, Any] | None = None,
    source_text: str | None = None,
    source_dir: Path | str | None = None,
) -> MaterializationResult:
    """Reconcile grounded fragments without paper- or material-specific rules."""

    routing = dict(paper_routing or {})
    anchor_rows = list(anchors)
    input_fact_rows = list(facts)
    input_fact_rows, dense_tensile_table_issues = (
        _promote_dense_tensile_tables_v203(
            anchor_rows,
            input_fact_rows,
            source_text=source_text or "",
        )
    )
    input_fact_rows, input_source_coordinate_issues = (
        _gate_v202_source_coordinate_facts(anchor_rows, input_fact_rows)
    )
    quality_mode = _claim_quality_mode()
    quality_gate = (
        filter_axis_facts(input_fact_rows, mode=quality_mode)
        if quality_mode != "off"
        else None
    )
    fact_rows = quality_gate.accepted if quality_gate is not None else input_fact_rows
    fact_rows, semantic_projection_issues = (
        _quarantine_v203_semantic_property_projections(fact_rows)
    )
    anchor_rows, fact_rows, discrete_sidecar_issues = (
        _promote_discrete_tensile_sidecars_v202(
            anchor_rows,
            fact_rows,
            source_text=source_text or "",
            source_dir=source_dir,
        )
    )
    fact_rows, source_coordinate_issues = _gate_v202_source_coordinate_facts(
        anchor_rows, fact_rows
    )
    source_coordinate_issues = [
        *input_source_coordinate_issues,
        *source_coordinate_issues,
    ]
    fact_rows, literal_tensile_unit_issues = _recover_literal_tensile_units(
        fact_rows
    )
    fact_rows, process_environment_issues = (
        _recover_process_environment_conditions(fact_rows, source_text)
    )
    anchor_rows, fact_rows, reference_owner_issues = (
        _recover_cited_nominal_composition_owners(anchor_rows, fact_rows)
    )
    anchor_rows, fact_rows, reference_tensile_owner_issues = (
        _recover_cited_tensile_reference_owners(
            anchor_rows, fact_rows, source_text or ""
        )
    )
    anchor_rows, fact_rows, reference_property_owner_issues = (
        _recover_cited_property_reference_owners(anchor_rows, fact_rows)
    )
    anchor_rows, fact_rows, reference_tensile_prose_owner_issues = (
        _recover_prose_citation_tensile_reference_owners(
            anchor_rows, fact_rows, source_text or ""
        )
    )
    anchor_rows, fact_rows, analysis_source_owner_issues = (
        _recover_analysis_source_composition_owners(anchor_rows, fact_rows)
    )
    anchor_rows, fact_rows, feedstock_owner_issues = (
        _recover_feedstock_owner_descriptors(anchor_rows, fact_rows)
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
    fact_rows, table_envelope_microanalysis_owner_issues = (
        _recover_microanalysis_table_envelope_owners(
            anchor_rows, fact_rows, source_text or ""
        )
    )
    issues = _chart_quarantine_issues_from_text(source_text)
    issues.extend(dense_tensile_table_issues)
    issues.extend(discrete_sidecar_issues)
    issues.extend(source_coordinate_issues)
    issues.extend(semantic_projection_issues)
    issues.extend(literal_tensile_unit_issues)
    issues.extend(process_environment_issues)
    issues.extend(reference_owner_issues)
    issues.extend(reference_tensile_owner_issues)
    issues.extend(reference_property_owner_issues)
    issues.extend(reference_tensile_prose_owner_issues)
    issues.extend(analysis_source_owner_issues)
    issues.extend(feedstock_owner_issues)
    issues.extend(microanalysis_owner_issues)
    issues.extend(numeric_microanalysis_owner_issues)
    issues.extend(table_envelope_microanalysis_owner_issues)
    property_context_index = PropertyContextIndex(source_text)
    tensile_protocol_ledger = TensileProtocolLedger(source_text)
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
    anchor_rows, table_column_anchor_issues = _filter_table_column_anchors(
        anchor_rows,
        fact_rows,
        source_text=source_text or "",
    )
    issues.extend(table_column_anchor_issues)
    identity_index = _build_identity_index(anchor_rows, fact_rows)
    fact_rows, table_column_issues = _reconcile_table_column_facts(
        identity_index,
        fact_rows,
        source_text=source_text or "",
    )
    issues.extend(table_column_issues)
    fact_rows, numeric_tensile_owner_issues = (
        _recover_numeric_tensile_table_row_owners(identity_index, fact_rows)
    )
    issues.extend(numeric_tensile_owner_issues)
    fact_rows, tensile_bundle_duplicate_issues = (
        _deduplicate_unresolved_tensile_bundle_projections(
            identity_index, fact_rows, source_text or ""
        )
    )
    issues.extend(tensile_bundle_duplicate_issues)
    fact_rows, numeric_tensile_context_issues = (
        _recover_numeric_tensile_context_owners(
            identity_index, fact_rows, source_text or ""
        )
    )
    issues.extend(numeric_tensile_context_issues)
    fact_rows, shared_owner_projection_issues = (
        _quarantine_shared_owner_projections(identity_index, fact_rows)
    )
    issues.extend(shared_owner_projection_issues)
    fact_rows, tensile_average_orientation_issues = (
        _quarantine_unoriented_tensile_averages(
            identity_index,
            fact_rows,
            source_text=source_text or "",
        )
    )
    issues.extend(tensile_average_orientation_issues)
    fact_rows, structure_proxy_issues = (
        _quarantine_structure_characterization_proxies(
            identity_index, fact_rows
        )
    )
    issues.extend(structure_proxy_issues)
    fact_rows, figure_characterization_issues = (
        _quarantine_figure_characterizations(identity_index, fact_rows)
    )
    issues.extend(figure_characterization_issues)
    fact_rows, reference_owner_entity_issues = (
        _quarantine_reference_owner_entity_projections(
            identity_index, fact_rows
        )
    )
    issues.extend(reference_owner_entity_issues)
    fact_rows, tensile_precision_issues = _deduplicate_tensile_precision_evidence(
        identity_index, fact_rows, source_text or ""
    )
    issues.extend(tensile_precision_issues)
    fact_rows, cross_item_duplicate_issues = _deduplicate_cross_item_dominance(
        identity_index, fact_rows
    )
    issues.extend(cross_item_duplicate_issues)
    # Preserve the complete bundle used by cross-owner dominance before folding
    # same-owner aliases. Removing one bundle member first can hide otherwise
    # decisive YS/UTS/EL owner evidence and reintroduce generic projections.
    fact_rows, tensile_exact_duplicate_issues = (
        _deduplicate_exact_tensile_projections(identity_index, fact_rows)
    )
    issues.extend(tensile_exact_duplicate_issues)
    # Exact aliases are folded first so a record carrying multiple independently
    # copied source assertions remains protected.  The source-block pass below
    # accepts only one single-assertion loser beside a complete survivor bundle.
    fact_rows, same_owner_bundle_issues = (
        _deduplicate_same_owner_complete_tensile_bundles(
            identity_index, fact_rows, source_text or ""
        )
    )
    issues.extend(same_owner_bundle_issues)
    # A short material descriptor is often repeated in several chunks while a
    # more specific sample code is emitted in another chunk.  When the generic
    # row is semantically identical to an already primary-owned fact, routing it
    # to both owners creates the exact cross-chunk projection that the
    # evidence-envelope pass cannot always recognize (the chunks may carry
    # different snippets of the same sentence).  Build this index before
    # grouping and quarantine only the generic duplicate; distinct facts keep
    # their normal route.
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
    owner_evidence_audits: dict[tuple[str, str], dict[str, list[Any]]] = {}
    owner_explicit_audits: dict[tuple[str, str, str], dict[str, list[Any]]] = {}
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
        explicit_evidence_targets = _fact_explicit_evidence_targets(
            identity_index, fact
        )
        if (
            len(declared_targets) == 1
            and len(explicit_evidence_targets) > 1
            and _numeric_core_tensile_fact(fact)
            and not _fact_markdown_table_rows(fact)
        ):
            issues.append(
                MaterializeIssue(
                    code="fact_owner_evidence_ambiguous",
                    sample_id_raw=identity_index.display_label(declared_targets[0]),
                    path=(
                        f"items.{identity_index.display_label(declared_targets[0])}"
                        ".Extracted_Data.Properties"
                    ),
                    message=(
                        "A numeric tensile fact's evidence names multiple source "
                        "owners; the declared owner was preserved without automatic "
                        "selection or broadcast."
                    ),
                    evidence=list(fact.source_evidence),
                    expected={
                        "binding": "one unique source-named material owner",
                        "broadcast": False,
                        "action": "review",
                    },
                    actual={
                        "declared_owner": identity_index.display_label(
                            declared_targets[0]
                        ),
                        "evidence_owner_candidates": [
                            identity_index.display_label(target)
                            for target in explicit_evidence_targets
                        ],
                        "fact": fact.model_dump(),
                    },
                    suggested_action=(
                        "Review the owner binding; split the comparison into "
                        "sample-qualified facts only when the source maps each value."
                    ),
                )
            )
        if len(declared_targets) == 1 and len(targets) == 1:
            previous = declared_targets[0]
            selected = targets[0]
            previous_base = identity_index.state_family_base.get(previous, previous)
            selected_base = identity_index.state_family_base.get(selected, selected)
            evidence_targets = _fact_evidence_owner_targets(identity_index, fact)
            evidence_owner_is_explicit = (
                len(evidence_targets) == 1
                and _fact_evidence_owner_is_explicit(
                    identity_index, fact, evidence_targets[0]
                )
            )
            evidence_reassignment_kind = (
                _fact_owner_reassignment_kind(
                    identity_index, fact, previous, evidence_targets[0]
                )
                if len(evidence_targets) == 1
                else None
            )
            preferred_material = _preferred_evidence_material_owner(
                identity_index, fact, previous
            )
            preferred_material_reconciled = (
                selected != previous
                and preferred_material is not None
                and preferred_material[0] == selected
            )
            evidence_reconciled = (
                selected != previous
                and len(evidence_targets) == 1
                and evidence_targets[0] == selected
                and previous_base != selected_base
                and not re.search(
                    r"(?i)\[reference\]\s*$", str(fact.sample_id_raw or "")
                )
                and not _fact_markdown_table_rows(fact)
                and evidence_owner_is_explicit
                and evidence_reassignment_kind is not None
            )
            if preferred_material_reconciled:
                before_owner = identity_index.display_label(previous)
                after_owner = identity_index.display_label(selected)
                binding_kind = str(preferred_material[1])
                audit = owner_explicit_audits.setdefault(
                    (before_owner, after_owner, binding_kind),
                    {"facts": [], "evidence": []},
                )
                audit["facts"].append(fact.model_dump())
                audit["evidence"].append(
                    {
                        "fact_index": len(audit["facts"]) - 1,
                        "source_evidence": list(fact.source_evidence),
                        "evidence_owner_targets": [
                            identity_index.display_label(target)
                            for target in _fact_explicit_evidence_targets(
                                identity_index, fact
                            )
                        ],
                        "binding_kind": binding_kind,
                        "process_context_preference": True,
                    }
                )
            elif evidence_reconciled:
                before_owner = identity_index.display_label(previous)
                after_owner = identity_index.display_label(selected)
                if evidence_reassignment_kind == "numeric_core_tensile_explicit_owner":
                    audit = owner_evidence_audits.setdefault(
                        (before_owner, after_owner),
                        {"facts": [], "evidence": []},
                    )
                else:
                    audit = owner_explicit_audits.setdefault(
                        (before_owner, after_owner, evidence_reassignment_kind),
                        {"facts": [], "evidence": []},
                    )
                audit["facts"].append(fact.model_dump())
                audit["evidence"].append(
                    {
                        "fact_index": len(audit["facts"]) - 1,
                        "source_evidence": list(fact.source_evidence),
                        "evidence_owner_targets": [
                            identity_index.display_label(target)
                            for target in evidence_targets
                        ],
                        "binding_kind": evidence_reassignment_kind,
                    }
                )
            elif selected != previous and selected_base == previous_base:
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
                # Keep the complete audit payload: this is a quarantine of a
                # generic alias projection, not an invisible deletion.
                issues.append(
                    MaterializeIssue(
                        code="shared_alias_duplicate_quarantined",
                        sample_id_raw=fact.sample_id_raw,
                        path=f"items.{fact.sample_id_raw}.Extracted_Data",
                        message=(
                            "A generic cross-chunk alias fact was isolated because "
                            "the same semantic fact is already owned by a more "
                            "specific source-backed sample."
                        ),
                        evidence=list(fact.source_evidence),
                        expected={
                            "owner": "specific source-backed sample",
                            "broadcast": False,
                        },
                        actual={
                            "fact": fact.model_dump(),
                            "specific_owners": [
                                identity_index.display_label(owner)
                                for owner in sorted(related_specific_owners & duplicate_owners)
                            ],
                        },
                        suggested_action=(
                            "Restore only if the generic alias denotes a distinct "
                            "independently reported material row."
                        ),
                    )
                )
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

    for (before_owner, after_owner), audit in sorted(owner_evidence_audits.items()):
        fact_count = len(audit["facts"])
        issues.append(
            MaterializeIssue(
                code="fact_owner_evidence_reconciled",
                sample_id_raw=after_owner,
                path=f"items.{after_owner}",
                message=(
                    f"{fact_count} fact{'s' if fact_count != 1 else ''} declared on "
                    "one owner were moved to the only different source owner "
                    "named in the fact evidence."
                ),
                evidence=audit["evidence"],
                expected={
                    "binding": "one unique source-named material owner",
                    "broadcast": False,
                    "comparison_owner_count": 1,
                },
                actual={
                    "before_owner": before_owner,
                    "after_owner": after_owner,
                    "facts": audit["facts"],
                },
                suggested_action=(
                    "Review only if the structured owner intentionally differs "
                    "from the literal owner of the cited evidence."
                ),
            )
        )

    for (before_owner, after_owner, binding_kind), audit in sorted(
        owner_explicit_audits.items()
    ):
        fact_count = len(audit["facts"])
        issues.append(
            MaterializeIssue(
                code="promotion_explicit_evidence_owner_reassigned",
                sample_id_raw=after_owner,
                path=f"items.{after_owner}",
                message=(
                    f"{fact_count} fact{'s' if fact_count != 1 else ''} declared on "
                    "one owner were reassigned only because the same local source "
                    "assertion explicitly binds the fact to one different owner."
                ),
                evidence=audit["evidence"],
                expected={
                    "binding": "one unique source-named owner and one direct axis assertion",
                    "broadcast": False,
                    "comparison_owner_count": 1,
                },
                actual={
                    "before_owner": before_owner,
                    "after_owner": after_owner,
                    "binding_kind": binding_kind,
                    "facts": audit["facts"],
                },
                suggested_action=(
                    "Review only if the structured owner intentionally differs from "
                    "the literal owner of this direct source assertion."
                ),
            )
        )

    items: list[dict[str, Any]] = []
    context_label_owners: dict[str, set[str]] = {}
    context_label_presentations: dict[str, str] = {}
    for canonical, indexed_anchors in identity_index.anchors.items():
        labels = [identity_index.display_label(canonical)]
        for anchor in indexed_anchors:
            labels.extend(
                str(value or "").strip()
                for value in (anchor.sample_id_raw, anchor.material_name_raw)
            )
        for label in labels:
            key = _identity_key(label)
            if not key:
                continue
            context_label_owners.setdefault(key, set()).add(canonical)
            context_label_presentations.setdefault(key, label)
    owner_context_labels: dict[str, tuple[str, ...]] = {
        canonical: tuple(
            sorted(
                {
                    context_label_presentations[key]
                    for key, owners in context_label_owners.items()
                    if owners == {canonical}
                },
                key=lambda value: (len(value), value.casefold()),
            )
        )
        for canonical in identity_index.anchors
    }
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
        (
            sanitized_composition_observations,
            composition_cross_source_issues,
        ) = _merge_cross_source_exact_composition_observations(
            sanitized_composition_observations,
            sample_id=sample_id,
        )
        issues.extend(composition_cross_source_issues)
        composition_observations = _deduplicate(sanitized_composition_observations)
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
        selected_context_canonicals = {group["canonical"]}
        selected_context_base = identity_index.state_family_base.get(
            group["canonical"]
        )
        if selected_context_base:
            selected_context_canonicals.add(selected_context_base)
        selected_context_labels = tuple(
            dict.fromkeys(
                label
                for canonical in sorted(selected_context_canonicals)
                for label in owner_context_labels.get(canonical, ())
            )
        )
        other_context_labels = tuple(
            dict.fromkeys(
                label
                for canonical in sorted(owner_context_labels)
                if canonical not in selected_context_canonicals
                for label in owner_context_labels[canonical]
            )
        )
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
            raw_prop_before_context = deepcopy(prop)
            context_decision = property_context_index.recover(
                prop,
                owner_role=role,
                owner_labels=selected_context_labels,
                other_owner_labels=other_context_labels,
            )
            table_projection_binding = (
                _property_unique_table_projection(
                    prop,
                    owner_labels=selected_context_labels,
                    source_text=source_text,
                )
                if (
                    context_decision.status in {"recovered", "augmented"}
                    and context_decision.shared_scope_risk
                    and is_core_tensile_property_name(
                        prop.get("property_name_raw")
                    )
                )
                else None
            )
            safe_global_table_protocol = bool(
                global_tensile_scope_v201_enabled()
                and table_projection_binding is not None
                and has_explicit_global_tensile_scope(context_decision)
                and role != "Reference"
            )
            coordinate_decision_key = str(
                prop.get("property_id_candidate") or ""
            ).strip()
            safe_source_coordinate_protocol = bool(
                source_coordinate_precision_v202_enabled()
                and owner_state_condition_v202_enabled()
                and discrete_chart_sidecar_v202_enabled()
                and role != "Reference"
                and coordinate_decision_key.startswith("sidecar-cell:")
                and str(prop.get("data_source") or "").strip().casefold()
                == "image_digitized"
            )
            if (
                context_decision.status in {"recovered", "augmented"}
                and is_core_tensile_property_name(
                    prop.get("property_name_raw")
                )
                and context_decision.shared_scope_risk
                and not safe_global_table_protocol
                and not safe_source_coordinate_protocol
            ):
                # A paper-level tensile method is useful recovery evidence, but
                # it is not a condition coordinate for a value quote that did
                # not identify the owner/state locally.  Keep the candidate's
                # own condition unchanged (possibly empty) and retain the
                # selected protocol in the audit for review.  This is the
                # precision-first boundary that prevents a rate/orientation
                # from a neighboring chunk from becoming a formal condition.
                issues.append(
                    MaterializeIssue(
                        code="property_test_context_shared_scope_quarantined",
                        sample_id_raw=sample_id,
                        path=f"items.{sample_id}.Properties",
                        message=(
                            "A paper-level tensile protocol was not copied into a "
                            "core-tensile condition because the value evidence "
                            "lacked a unique local owner/state coordinate."
                        ),
                        evidence=[
                            candidate.audit_dict()
                            for candidate in context_decision.selected
                        ],
                        expected={
                            "condition_binding": "property-local source assertion",
                            "neighbor_protocol_projection": False,
                            "audit_preserved": True,
                        },
                        actual={
                            "before": deepcopy(prop),
                            "after": deepcopy(prop),
                            "reason": context_decision.reason,
                            "selected_owner": sample_id,
                            "owner_labels": list(selected_context_labels),
                            "owner_evidence_in_property": False,
                            "accepted_fragments": list(
                                context_decision.accepted_fragments
                            ),
                        },
                        suggested_action=(
                            "Restore protocol details only after the source quote "
                            "provides an explicit owner/state coordinate."
                        ),
                    )
                )
                # Precision isolation applies to the inherited condition, not
                # to the source-grounded tensile value itself.  Keep the
                # Property in the public ledger with its original condition
                # (normally empty) and retain the rejected Methods protocol in
                # the audit above.  Dropping the whole fact would turn a
                # condition-binding problem into a false omission.
                prop = deepcopy(prop)
                prop["test_condition_raw"] = prop.get("test_condition_raw") or None
                context_decision = PropertyContextDecision(
                    "existing",
                    "paper-level tensile protocol isolated; value preserved",
                    condition_raw=prop.get("test_condition_raw"),
                    selected=context_decision.selected,
                    candidates=context_decision.candidates,
                    rejected=context_decision.rejected,
                    accepted_fragments=context_decision.accepted_fragments,
                )
            if context_decision.status in {"recovered", "augmented"}:
                original_prop = deepcopy(prop)
                prop = deepcopy(prop)
                prop["test_condition_raw"] = context_decision.condition_raw
                augmented = context_decision.status == "augmented"
                issues.append(
                    MaterializeIssue(
                        code=(
                            "tensile_protocol_coordinate_recovered"
                            if safe_source_coordinate_protocol
                            else
                            "property_test_context_table_owner_recovered"
                            if safe_global_table_protocol
                            else "property_test_context_augmented"
                            if augmented
                            else "property_test_context_recovered"
                        ),
                        sample_id_raw=sample_id,
                        path=f"items.{sample_id}.Properties",
                        message=(
                            (
                                "A partial Property test condition was completed without "
                                "overwriting it, using compact source-literal condition "
                                "fragments from the unique compatible tensile procedure."
                            )
                            if augmented
                            else (
                                "An empty Property test condition was restored from "
                                "compact source-literal fragments in the unique compatible "
                                "tensile procedure."
                            )
                        ),
                        evidence=[
                            candidate.audit_dict()
                            for candidate in context_decision.selected
                        ],
                        expected={
                            "binding": (
                                "one discrete sidecar cell plus one compatible bounded tensile protocol"
                                if safe_source_coordinate_protocol
                                else
                                "one unique owner/value table row plus one explicitly global tensile protocol"
                                if safe_global_table_protocol
                                else "one source-literal compatible condition fragment set"
                            ),
                            "overwrite_existing_condition": False,
                        },
                        actual={
                            "before": original_prop,
                            "after": deepcopy(prop),
                            "reason": context_decision.reason,
                            "selected_owner": sample_id,
                            "owner_labels": list(selected_context_labels),
                            "owner_qualifier": context_decision.owner_qualifier,
                            "accepted_source_fragments": list(
                                context_decision.accepted_fragments
                            ),
                            "unique_table_projection": table_projection_binding,
                            "explicit_global_tensile_scope": (
                                safe_global_table_protocol
                            ),
                            "global_scope_evidence": [
                                candidate.global_scope_evidence
                                for candidate in context_decision.selected
                                if candidate.global_scope_evidence
                            ],
                            "bounded_tensile_events": [
                                candidate.text
                                for candidate in context_decision.selected
                            ],
                            "owner_role": role,
                            "owner_invented": False,
                            "decision_key": (
                                coordinate_decision_key
                                if safe_source_coordinate_protocol
                                else None
                            ),
                            "rejected_candidates": [
                                candidate.audit_dict()
                                for candidate in context_decision.rejected
                            ],
                        },
                        suggested_action=(
                            "Review the source line spans if this paper uses multiple "
                            "tensile protocols for the same property family."
                        ),
                    )
                )
                if (
                    context_decision.shared_scope_risk
                    and not safe_global_table_protocol
                ):
                    # Keep the public condition unchanged for compatibility:
                    # a paper-wide tensile protocol can be scientifically
                    # shared even when the value chunk lost its owner.  Make
                    # that boundary explicit in the audit stream so a later
                    # strict run can isolate it without changing the frozen
                    # extraction or silently deleting a core tensile result.
                    issues.append(
                        MaterializeIssue(
                            code="property_test_context_shared_scope_audit",
                            sample_id_raw=sample_id,
                            path=f"items.{sample_id}.Properties",
                            message=(
                                "A core-tensile condition was recovered from a "
                                "paper-level protocol although the value quote "
                                "did not carry a local owner or condition "
                                "coordinate; the condition was retained and "
                                "flagged for strict owner review."
                            ),
                            evidence=[
                                candidate.audit_dict()
                                for candidate in context_decision.selected
                            ],
                            expected={
                                "local_owner_or_protocol_coordinate": True,
                                "public_condition": "preserved_for_compatibility",
                                "audit_preserved": True,
                            },
                            actual={
                                "before": original_prop,
                                "after": deepcopy(prop),
                                "reason": context_decision.reason,
                                "selected_owner": sample_id,
                                "owner_labels": list(selected_context_labels),
                                "owner_evidence_in_property": False,
                                "accepted_source_fragments": list(
                                    context_decision.accepted_fragments
                                ),
                            },
                            suggested_action=(
                                "Review the source table/prose before enabling a "
                                "strict owner-local condition policy."
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
                            "or conflicting tensile procedures could not be resolved from "
                            "the reported condition and property-local evidence."
                        ),
                        evidence=[
                            candidate.audit_dict()
                            for candidate in context_decision.candidates
                        ],
                        expected={
                            "binding": "one uniquely supported test context",
                            "action": "preserve the original condition when ambiguous",
                        },
                        actual={
                            "fact": deepcopy(prop),
                            "reason": context_decision.reason,
                            "selected_owner": sample_id,
                            "owner_labels": list(selected_context_labels),
                            "rejected_candidates": [
                                candidate.audit_dict()
                                for candidate in context_decision.rejected
                            ],
                        },
                        suggested_action=(
                            "Manually bind the condition only when the source identifies "
                            "which protocol produced this value."
                        ),
                    )
                )
            ledger_decision = tensile_protocol_ledger.bind(
                prop,
                owner_role=role,
                owner_labels=selected_context_labels,
                other_owner_labels=other_context_labels,
            )
            if ledger_decision.status == "bound":
                ledger_before = deepcopy(prop)
                prop = deepcopy(prop)
                prop["test_condition_raw"] = ledger_decision.condition_raw
                issues.append(
                    MaterializeIssue(
                        code="tensile_protocol_ledger_bound",
                        severity="info",
                        sample_id_raw=sample_id,
                        path=f"items.{sample_id}.Properties",
                        message=(
                            "Missing tensile-condition dimensions were bound from "
                            "one source-proven owner-compatible protocol event."
                        ),
                        evidence=[
                            event.to_dict()
                            for event in ledger_decision.selected_events
                        ],
                        expected={
                            "event_count": 1,
                            "owner_compatible": True,
                            "overwrite_existing_literal": False,
                            "reference_target_leakage": False,
                        },
                        actual={
                            "before": raw_prop_before_context,
                            "materialization_before_ledger": ledger_before,
                            "after": deepcopy(prop),
                            "selected_owner": sample_id,
                            "owner_role": role,
                            "owner_labels": list(selected_context_labels),
                            "decision": ledger_decision.audit_dict(),
                        },
                        suggested_action=(
                            "Review the event source span if this material uses more "
                            "than one tensile protocol."
                        ),
                    )
                )
            elif (
                ledger_decision.status in {"ambiguous", "conflict"}
                and is_core_tensile_property_name(prop.get("property_name_raw"))
                and ledger_decision.candidate_events
            ):
                issues.append(
                    MaterializeIssue(
                        code="tensile_protocol_ledger_ambiguous",
                        sample_id_raw=sample_id,
                        path=f"items.{sample_id}.Properties",
                        message=(
                            "The v203 tensile ledger preserved the Property condition "
                            "because no unique compatible protocol event was proven."
                        ),
                        evidence=[
                            event.to_dict()
                            for event in ledger_decision.candidate_events
                        ],
                        expected={
                            "binding": "one owner-compatible source event",
                            "condition_overwrite": False,
                        },
                        actual={
                            "fact": deepcopy(prop),
                            "selected_owner": sample_id,
                            "owner_role": role,
                            "owner_labels": list(selected_context_labels),
                            "decision": ledger_decision.audit_dict(),
                        },
                        suggested_action=(
                            "Bind only after a local owner, state, orientation, or "
                            "explicit global coordinate resolves the event."
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

        # Keep an audit record for numeric structure features removed by the
        # evidence-coordinate check in ``_sanitize_structure_feature``.
        for observation in raw_structure_observations:
            observation_evidence = _evidence(observation.get("source_evidence"))
            feature_rows = [
                row
                for row in observation.get("features") or []
                if isinstance(row, dict)
            ]
            for entity in observation.get("entities") or []:
                if isinstance(entity, dict):
                    feature_rows.extend(
                        row
                        for row in entity.get("features") or []
                        if isinstance(row, dict)
                    )
            for feature in feature_rows:
                raw_value = _first_present(
                    feature,
                    "value_raw",
                    "feature_value_raw",
                    "description_raw",
                    "raw_note",
                )
                feature_evidence = _evidence(feature.get("source_evidence")) or observation_evidence
                if raw_value in (None, "") or _structure_feature_numeric_evidence_supported(
                    raw_value, feature_evidence, feature
                ):
                    continue
                issues.append(
                    MaterializeIssue(
                        code="structure_feature_without_literal_evidence",
                        sample_id_raw=sample_id,
                        path=f"items.{sample_id}.Structure.Structure_Observations",
                        message=(
                            "A numeric structure feature was isolated because its "
                            "literal value does not occur in the cited evidence "
                            "envelope."
                        ),
                        evidence=feature_evidence,
                        expected={
                            "value": "all numeric tokens present in source evidence"
                        },
                        actual={"feature": deepcopy(feature), "value_raw": raw_value},
                        suggested_action=(
                            "Restore only when the source coordinate is expanded to "
                            "the table row or sentence that reports this value."
                        ),
                    )
                )

        structure_observations = _deduplicate(
            sanitized
            for observation in raw_structure_observations
            if (sanitized := _sanitize_structure_observation(observation)) is not None
        )
        for obs_index, observation in enumerate(structure_observations, start=1):
            observation["observation_id"] = f"str_obs_{obs_index:03d}"
            observation["sample_id"] = sample_id

        characterizations = _deduplicate(grouped_facts.get("characterization", []))
        characterizations, characterization_alias_issues = (
            _coalesce_characterization_aliases(characterizations, sample_id)
        )
        issues.extend(characterization_alias_issues)
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
