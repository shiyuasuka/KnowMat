"""Compile compact, non-conflicting execution prompts from alpha25 semantics."""

from __future__ import annotations

import hashlib
import json
from typing import Any, Iterable, Literal, Mapping

from knowmat.alpha25.package import Alpha25Package, load_alpha25_package


Axis = Literal[
    "inventory",
    "composition",
    "processing",
    "structure",
    "properties",
    "combined",
    "all",
]

_BASE_CONTRACT = """You are a conservative materials-science evidence extraction engine.
Contract: material_extraction_v11.3.3 evidence-first candidate facts, derived from
material-extractor 11.0.0-alpha.25. Return exactly one legal JSON object and no prose.

Truth and scope:
- OCR evidence in the current task is the only factual source. Never use world knowledge,
  alloy-database memory, the filename, a paper title, or a benchmark/GT answer.
- Copy short source_evidence verbatim from the assigned evidence. Do not paraphrase it.
- Emit only facts directly supported in this task. Missing facts stay absent/null/empty.
- Preserve raw value, unit, method, standard, condition, specimen, state, region, role,
  origin, range, inequality, standard deviation, and source type. Never turn a range or
  inequality into a scalar. Never estimate a value from a plotted curve.
- Commercial designations do not license standard composition lookup or completion.
- Separate Target from Reference, experiment from simulation/ML/literature/derived facts,
  process temperature from test temperature, and process equipment from characterization
  or property-test equipment.

Identity and splitting:
- One item anchor is one source-named material, composition, batch, or genuinely independent
  material state. Split explicitly different compositions, batches, source-labelled independent
  material states, or literature materials. Keep different test conditions on an unchanged
  sample together.
- Region/location, orientation, specimen geometry, test coupons, characterization sub-samples,
  post-test observations, and process-stage mentions are fact context, not separate item anchors.
  Preserve them in condition/specimen/region/orientation/material_state/process fields. Create a
  state anchor only when the source names it as an independently compared material state and
  assigns material facts to that state; a state-changing process mention alone is insufficient.
- An author-year citation or citation number is provenance, never sample_id_raw. For a literature
  item use the cited material name or source code when the evidence states one; otherwise do not
  invent an identity from the author name.
- Use source sample labels when present. Do not append chunk/task numbers to identifiers.
- Tables must retain every directly reported row/cell in scope and its header/unit/condition.

Alpha25 candidate semantics:
- Composition uses Composition_Text, Material_Identity, and Composition_Observations.
  measured is allowed only with an explicit measurement method and sample context;
  otherwise use nominal/provided/calculated/inferred/unknown as supported by evidence.
- Processing uses only Process_Text and Process_Route.candidate_stages/candidate_edges.
  State-changing stages carry raw parameters/equipment and evidence. Testing and specimen
  machining are not process stages. Linear routes use candidate_edges=[].
- Structure uses Structure_Text, structure_status, Structure_Observations, and
  Characterization. Entities/features/characterization each carry their own evidence.
- Properties preserve property_id_candidate, property_name_raw, value_raw, unit_raw,
  test_method_raw, test_standard_raw, test_condition_raw, test_specimen_raw, raw_note,
  data_source, origin clues, source_evidence, and confidence. No fact means an empty list.
- Candidate output never contains final canonical process parameter values, final tensile
  normalization, normalization_rule_id, parameter_profile, Rule_Metadata, or GT metadata.

Every returned fact must include a non-empty source_evidence list and a confidence in [0,1].
Confidence measures evidence clarity; it never substitutes for evidence."""

_AXIS_INSTRUCTIONS: dict[Axis, str] = {
    "inventory": (
        "Return {\"anchors\":[...]}. Each anchor contains sample_id_raw, material_name_raw, "
        "state_raw, role, data_nature, source_evidence, confidence. Emit at most 32 anchors and "
        "use only these exact enum strings: role is Target|Reference and data_nature is "
        "Experimental|Computed|Literature_Experimental|Literature_Computed. Simulation, ML, "
        "prediction, calculation, or other model-generated rows are Computed rather than a new "
        "enum value. sample_anchors in Task context are identities already accepted from a "
        "deterministic source table; do not emit them again unless this evidence explicitly "
        "introduces a distinct source-labelled independent state. Emit only new anchors. "
        "Scan every table row, sample column, legend series, and explicitly contrasted condition "
        "for facts, but create anchors only for explicit material identities. Preserve compact "
        "source labels such as numbered/hash codes; a "
        "label is not invalid merely because it contains only numbers and separators. One anchor "
        "represents one explicit material, composition, batch, source-labelled independent material "
        "state, or cited comparison material. When the same base sample occurs in multiple "
        "state-changing conditions, emit separate anchors only when the source names those states "
        "as independently compared material objects and reports material facts for each; otherwise "
        "retain one base anchor and put the distinguishing context on the facts. Consolidate "
        "synonymous mentions of the same state. Do not split an unchanged sample for test "
        "temperature, measurement repetition, region/location, orientation, specimen geometry, "
        "test coupons, characterization sub-samples, post-test observations, or a process-stage "
        "mention. Mark "
        "Reference only when the source assigns cited/comparison facts to that material. Never "
        "create anchors for chemical elements, phases, precipitates, generic alloy families, "
        "methods, instruments, process names alone, test metrics, authors, author-year citations, "
        "citation numbers, figure labels, or ordinary prose words. For literature facts use an "
        "explicit cited material name/code as sample_id_raw; never use the author/citation label. "
        "Each anchor carries only the shortest exact quote needed to prove its identity/state, not "
        "all facts about it. If no explicit item/state identifier occurs, return anchors:[]. "
        "Do not emit four-axis facts."
    ),
    "composition": (
        "Return {\"axis\":\"composition\",\"facts\":[...]}. Emit only alpha25 raw "
        "Material_Identity or Composition_Observation facts for the supplied sample anchors. "
        "Exhaust every material/sample row and every component cell in a composition table; keep "
        "distinct compositions, feedstocks, material states, and cited comparison materials on "
        "their own source labels. "
        "A phase, precipitate, oxide, or chemical element is not a material item and must not "
        "be emitted as Material_Identity or sample Composition_Observation."
    ),
    "processing": (
        "Return {\"axis\":\"processing\",\"facts\":[...]}. Emit only raw process-stage, "
        "parameter, process-equipment, and explicit-edge facts. Exhaust every explicitly labelled "
        "parameter combination and heat-treatment/sintering/hold variant in tables. Use the exact "
        "source item label for sample_id_raw. Keep route/stage/condition distinctions in process "
        "fact data unless the source itself names the resulting material state as an independent "
        "item. A process-stage mention alone never creates or expands an item label. Do not emit "
        "test steps."
    ),
    "structure": (
        "Return {\"axis\":\"structure\",\"facts\":[...]}. Emit only raw structure "
        "observation/entity/feature or characterization facts. Emit at most one structure_text "
        "per sample/state in this task; consolidate related entities/features into one observation "
        "instead of repeating the same sentence as many facts. When a structured observation is "
        "emitted, omit structure_text for the same evidence; structure_text is only a compact "
        "fallback when no structured observation can be formed. Preserve distinct regions, "
        "locations, orientations, methods, and specimen contexts in observation/characterization "
        "fields; they are not separate item identities. Keep independently source-labelled material "
        "states and cited comparison materials attributable to their explicit material labels. A "
        "qualitative entities/features must be directly supported by the cited source span; do not "
        "invent or project a feature from an adjacent sentence. Multiple distinct atomic features "
        "explicitly stated in one span may coexist, but merge exact duplicates and never use generic "
        "words such as microstructure, sample, region, image, or map as standalone entities. "
        "reported SEM/TEM/EBSD/"
        "A characterization fact requires an explicit performed acquisition or method/setup record: "
        "for example, the source says a specimen was examined/characterized/analyzed using "
        "SEM/TEM/EBSD/XRD/EDS/CT/optical methods, names an instrument, or reports voltage, "
        "current, step size, resolution, standard, or specimen preparation. Extract that record "
        "with method_raw/method_class and the shortest exact evidence, even when no numeric "
        "structure feature is reported. A result-only caption or sentence such as 'Fig. ... shows "
        "EBSD maps' or 'SEM images reveal ...' is a structure observation, not a new "
        "characterization record; do not emit it as characterization unless the same evidence also "
        "contains a direct performed-acquisition/setup assertion. Never silently relabel a valid "
        "method/setup record as processing. For a directly observed qualitative feature (for "
        "example a named phase, grain morphology, precipitate shape, or lamellar/columnar "
        "arrangement), preserve one atomic feature row even when no number is reported; copy the "
        "shortest span containing the owner and direct observation/change verb. Do not output that "
        "feature when the span is comparative-only, inferential, procedural, or owner-ambiguous."
    ),
    "properties": (
        "Return {\"axis\":\"properties\",\"facts\":[...]}. Emit only complete raw "
        "Property candidate facts with method/condition/specimen/origin evidence. Emit one fact "
        "per distinct property and test condition; exhaust every sample/condition cell in a result "
        "table and preserve uncertainty/range/inequality text. Use source sample labels and keep "
        "cited comparison values separate from author experiments. Do not duplicate a value under "
        "synonyms."
    ),
    "combined": (
        "Return {\"axis\":\"combined\",\"anchors\":[...],\"facts\":[...]} with source "
        "item identities and all directly supported "
        "composition, processing, structure, and properties facts in one mixed list. "
        "Each anchors[] row uses the inventory fields sample_id_raw, material_name_raw, "
        "state_raw, role, data_nature, source_evidence, confidence and the exact enums "
        "Target|Reference and Experimental|Computed|Literature_Experimental|"
        "Literature_Computed. Anchors represent only explicit materials, compositions, "
        "batches, or source-labelled independent material states. sample_anchors in Task "
        "context are already accepted deterministic identities: do not return them again; "
        "only emit a genuinely new identity introduced by the current evidence. Return the "
        "shortest source label for each material/state and consolidate synonymous mentions. "
        "When the source explicitly pairs a "
        "long descriptive material/state phrase with a short code or abbreviation, always "
        "use the short code as sample_id_raw, retain the long phrase in material_name_raw "
        "or state_raw as appropriate, and emit one anchor rather than splitting the two "
        "source aliases into separate anchors. Results attributed to another study, cited "
        "authors, or a literature/reference-table row must use role Reference together "
        "with Literature_Experimental or Literature_Computed; they are never Target facts "
        "of the current study. An author-year name or citation number is provenance, never "
        "sample_id_raw; use an explicit cited material name/code or omit the ambiguous item. "
        "Never create anchors for test coupons "
        "or specimens that only identify geometry/orientation, FIB/TEM/APT sub-samples, "
        "phases, precipitates, structure regions, methods, instruments, table metrics, "
        "units, row/figure labels, fitted coefficients, or bare numeric values. Put a "
        "processing state in fact data instead of inventing a synonymous item label. Only "
        "put it in anchor state_raw when the source treats that state as an independently "
        "named comparison material; a process, test, or post-test mention alone is not an item. "
        "Do not also emit a material_identity fact when the same evidence adds no identity "
        "field beyond its anchor. Within this task emit each source assertion once: merge "
        "parameters of the same process stage, repeated mentions of the same characterization "
        "method/condition, and exact duplicate property values. Never merge distinct raw "
        "values, states, regions, methods, specimens, or test conditions. "
        "Every fact must name one uniquely attributable source sample/state. A shared alloy "
        "family or designation is not a fact owner when multiple anchors use it. Never copy an "
        "unqualified assertion to every compatible anchor or state. When the source explicitly "
        "attributes one assertion to multiple named samples, emit separate sample-qualified "
        "facts only for the targets literally supported by that evidence; otherwise omit the "
        "ambiguous fact. Do not create an anchor or expand sample_id_raw merely to force unique "
        "attribution: never append a characterization method, structure region, test wording, "
        "build strategy, or other description that the source does not use as an item label. In "
        "particular, do not create labels such as 'A [LPBF]', 'A [X]', or 'A [after 500 h]' when "
        "the source labels only 'A'; preserve the qualifier on the fact condition/state. "
        "Reuse the shortest literal source label already present in the evidence. Each anchor "
        "uses only the minimum exact identity/state quote. Each fact uses only the shortest "
        "complete quote or quotes needed to prove that fact and its owner; do not attach unrelated "
        "sentences merely because they mention the same sample. "
        "Each fact's axis is its actual four-axis name, never combined. Scan the assigned "
        "evidence once and do not duplicate the same fact across axes. Exhaust explicit "
        "table rows/cells and source-labelled states. Composition emits only raw material "
        "identity or quantitative composition observations; processing emits state-changing "
        "stages/parameters/equipment, not tests; structure consolidates related entities and "
        "features into at most one observation per sample/state/evidence span; properties "
        "preserve every distinct value and test condition. For characterization recall, scan "
        "every performed SEM/TEM/EBSD/XRD/EDS/CT/optical or other measurement setup and emit "
        "one characterization fact only when the evidence explicitly states a performed "
        "acquisition/measurement or gives its instrument/setup values (such as voltage, current, "
        "step size, resolution, standard, or specimen), even when no numeric structure feature is "
        "reported. Treat result-only figure/caption mentions as structure observations and do not "
        "emit mere reference/protocol mentions without a performed measurement. Return facts:[] when none are "
        "directly supported. For qualitative Structure, retain explicitly observed atomic entities "
        "and features alongside numeric features; never expand one direct assertion into one row "
        "per compatible owner. Return anchors:[] and facts:[] when neither is supported. "
        "Do not return a full candidate document, Paper_Metadata, Paper_Routing, items, "
        "or Rule_Metadata."
    ),
    "all": (
        "Return one full alpha25 evidence-first candidate document with Paper_Metadata, "
        "Paper_Routing, and items containing all four required axes."
    ),
}

_FACT_ENVELOPE = """Axis fact wire format:
- Every facts[] row is exactly
  {"axis":"<actual four-axis name>","fact_type":"<allowed type>",
   "sample_id_raw":"<source label or not_reported>",
   "data":{...},"source_evidence":["short literal OCR quote"],"confidence":0.0}.
- Keep source_evidence and confidence only in this outer fact envelope. Do not duplicate
  them inside data; the deterministic runner copies them into alpha25 fragments that require
  those fields. Keep JSON compact and never repeat the same quote in sibling fields. Use the
  shortest complete literal span that proves the fact, its owner, and required context; do not
  copy an entire paragraph when one sentence suffices. Multiple quotes are allowed only when
  separate source spans are jointly required. Table facts still follow the full header/body rule.
- The runner deterministically assigns candidate IDs and final per-item order after all
  source leaves are reconciled. In combined tasks omit observation_id, characterization_id,
  property_id_candidate, candidate_stage_id, and stage_index_candidate. Also omit a nullable
  or empty metadata field when the evidence does not report it; the runner restores only the
  schema-defined null/empty value. Never omit a reported raw value, unit, condition, method,
  specimen, state, region, data origin, component, entity, feature, or parameter.
- composition fact_type is material_identity or composition_observation.
  material_identity data keys are material_family/material_name_raw/designation_raw/
  feedstock_form. composition_observation data must include source_type, basis,
  component_type, components, raw_expression and data_source. Include material_state,
  sample_id, measurement and note only when reported; otherwise the runner supplies
  not_reported/null from the fact envelope.
  source_type is exactly nominal|measured|provided|calculated|inferred|unknown;
  basis is exactly wt%|at%|vol%|mol%|mass_fraction|volume_fraction|
  atomic_fraction|formula_ratio|mass_trace|atomic_trace|unknown; component_type is
  exactly elemental|phase|constituent|formula|ratio|unknown; data_source is exactly
  text|table|image|figure|supplement|abstract|external_reference|unknown.
  Every components[] row uses name_raw, value_kind, value_raw, unit_raw and data_nature;
  omit canonical_name/value/canonical_unit because the deterministic runner owns them.
  source_evidence is optional when identical to the outer fact evidence.
  value_kind is scalar|range|inequality|balance|categorical|
  formula|unknown and data_nature is reported|derived|inferred. Never use old keys
  element/amount_raw/amount_value/amount_unit. Do not emit a component without an
  explicit value_raw; qualitative mentions without an amount are not composition.
- processing fact_type is process_text, process_stage, or process_edge.
  process_text data is {original,simplified}. process_stage data must include
  process_name_raw and parameters_raw. Omit candidate IDs, stage index, process code and
  role; the runner assigns IDs/order and keeps unsupported code/role empty.
  parameters_raw is always a JSON list; each row contains only
  parameter_name_raw, value_raw, unit_raw, source_evidence (a nonempty string),
  plus optional confidence/condition_label_raw. Never return a string or object map
  for parameters_raw. A normal linear route uses process_edge facts:[]. Only an
  explicit non-linear route may emit an edge with source_candidate_stage_id,
  target_candidate_stage_id, edge_type and source_evidence; edge_type is exactly
  next|branch|merge|parallel|repeat, never linear/sequential.
- structure fact_type is structure_text, structure_observation, or characterization.
  structure_text data is {original,simplified}. structure_observation data must include
  structure_kind, source_type, entities and features; include material_state, original and
  simplified when evidence explicitly distinguishes them. The runner binds sample_id and
  supplies source_evidence as original when omitted. characterization data must include
  method_raw and method_class.
  structure_kind is exactly phase_assemblage|grain_structure|precipitate|texture|
  defect|porosity|interface|morphology|transformation|surface_or_layer|
  configuration|other. source_type is exactly reported|calculated|inferred|
  simulated|cited|unknown. Every entities[] row contains name_raw and any reported
  entity_type/role/features/raw_expression; omit entity_id because the runner assigns it.
  Entity source_evidence may be omitted when identical to the outer fact evidence. Use name_raw, never
  phase_name_raw/entity_name/entity_name_raw. Every features[] row contains
  feature_name_raw, value_kind, value_raw and data_nature; feature source_evidence may
  be omitted when identical to the outer fact evidence;
  value_kind is scalar|range|inequality|categorical|text and data_nature is
  reported|derived|calculated|inferred|simulated|unknown. Never use feature_name,
  feature_type or feature_value_raw. If no explicit raw value/description exists,
  omit that feature rather than returning an incomplete object.
- properties fact_type is property and data must contain property_name_raw and value_raw.
  Include unit/method/standard/condition/specimen/note/data_source whenever reported; omit
  only genuinely absent metadata, which the runner restores as the schema-defined empty value.
- data contains only the named alpha25 candidate fragment, not Composition,
  Processing, Structure, Extracted_Data, items, or a whole document.
- A valid task with no directly supported fact returns facts:[]."""

# This wrapper is deliberately separate from the reviewed alpha25 domain
# contract above.  It is a small, provider-neutral protocol for noisy chunk
# boundaries: it makes the source-of-truth and fail-closed behaviour salient
# without changing any axis semantics or the public final.json schema.
_PRECISION_CHUNK_WRAPPER = """Chunk precision protocol (applies to this task only):
- The OCR EVIDENCE block is the complete factual scope for this chunk. The routing and
  sample_anchors are identity hints only; never use them to fill an owner, state, condition,
  value, method, or result that is absent from this chunk.
- Copy every source_evidence string as a short, literal substring of this chunk. If a sentence,
  table row, owner, or condition is cut at the boundary, keep the fact incomplete/omitted rather
  than guessing or completing it from adjacent context. Never expand one assertion into multiple owner-specific facts unless the evidence explicitly names each owner (for example, "A and B,
  respectively").
- Emit each source assertion once in this chunk. Do not repeat it with synonyms, alternate units,
  paraphrases, or one row per compatible sample. Cross-chunk deduplication is deterministic; a
  repeated assertion may set continuation_of only when an earlier fact identifier is explicitly
  supplied in Task context. Otherwise omit the duplicate and keep the local fact only once.
- A table header, unit row, metric name, method name, or column label is not a scientific fact by
  itself. Do not emit a Property/Structure/Characterization row unless the same evidence contains
  a body value or an explicit performed observation tied to one owner. Never turn a multi-level
  header into a new owner, state, or result. If a row is visibly cropped or its owner/value column
  is missing, return it in unresolved_spans (or omit it) instead of completing it from another
  chunk.
- Precision does not mean dropping supported cells: when one physical body row in this chunk
  contains an explicit owner and a reported value, emit every distinct property cell from that
  row, preserving its column condition/orientation/unit. A header may be copied only as context
  for that body row; never emit the header as a standalone fact. For characterization, emit the
  performed method/setup whenever the same evidence names the owner or specimen and the
  acquisition/instrument/setup, even if no numeric result is present.
- Optional per-fact protocol fields are allowed: chunk_id (use evidence_unit_id), source_span
  (shortest literal span), incomplete (true only when the source visibly cuts the assertion), and
  continuation_of (prior fact identifier). Omit these fields when not needed; they are audit
  metadata and never scientific output.
- Always return a compact top-level coverage object:
  {"status":"complete|none|partial","unresolved_spans":["short literal span"]}.
  Use complete when all directly supported assertions in this chunk were emitted, none when no
  extractable assertion exists, and partial only when the OCR boundary or malformed source makes
  a directly supported assertion incomplete. Never mark complete by inventing missing facts.
"""

_TABLE_PROJECTION_SCOPE = (
    "This evidence unit is a deterministic table projection. Emit anchors and facts "
    "represented by the table headers and body cells. Use adjacent caption or prose "
    "only to resolve sample identity, state, basis, units, or cell meaning. Do not emit "
    "standalone facts found only in that adjacent context because it is assigned to a "
    "separate prose task. Never turn a metric, method, unit, or component heading into "
    "a material anchor. Every source_evidence entry must be an exact contiguous substring "
    "of the OCR evidence. For a multi-column table fact, copy the complete literal header "
    "row or rows and the complete literal body row as separate source_evidence entries. "
    "Never fabricate a shorter quote by deleting intervening columns or by concatenating "
    "a row label with a non-adjacent target cell. Treatment, duration, temperature, "
    "orientation, or other context carried by a column header must be preserved in the fact "
    "condition/specimen/region/orientation/material_state field as applicable. Preserve it in "
    "anchor state_raw only when the header explicitly names an independently compared material "
    "state; a test or location header alone is not an item. A header-only row, units-only row, "
    "metric/method label, or synthetic multi-level header is never sufficient evidence for a fact; "
    "each emitted Property must include one body value cell and one uniquely attributable owner "
    "coordinate from the same physical table row. If that coordinate cannot be proven, omit the "
    "candidate and record the unresolved span rather than projecting it across columns or chunks.\n"
)


def _clean_sections(values: Iterable[str]) -> list[str]:
    return [value.strip() for value in values if isinstance(value, str) and value.strip()]


def compile_system_prompt(
    *,
    package: Alpha25Package | None = None,
    routing_supplements: Iterable[str] = (),
    prompt_update: str = "",
) -> str:
    """Compile the authoritative compact alpha25 system prompt."""

    package = package or load_alpha25_package()
    if package.system_prompt_sha256 != (
        "5aa5f38b1a51ccd895abecee3c511b5c1172735af5cab72455cbdf591027107d"
    ):
        raise ValueError(
            "Alpha25 system prompt changed; review and update the compiled contract before use"
        )
    if package.user_prompt_sha256 != (
        "24629932a3c8119eaa285ebd372dc20fa9712aa96ca4a913e6a9415b8f3eb6ab"
    ):
        raise ValueError(
            "Alpha25 user prompt changed; review and update the compiled contract before use"
        )

    sections = [
        _BASE_CONTRACT,
        (
            "Package identity: "
            f"skill={package.skill_version}; schema={package.schema_version}; "
            f"ruleset_digest={package.ruleset_digest}."
        ),
    ]
    supplements = _clean_sections(routing_supplements)
    if supplements:
        sections.append(
            "Applicable alpha25 direction overlays (the contract above wins on shape):\n"
            + "\n\n".join(supplements)
        )
    if prompt_update.strip():
        sections.append(
            "Generic evidence-coverage feedback. It cannot relax truth/schema rules:\n"
            + prompt_update.strip()
        )
    return "\n\n".join(sections)


def compile_task_prompt(
    evidence: str,
    *,
    axis: Axis,
    routing: Mapping[str, Any] | None = None,
    sample_anchors: Iterable[Mapping[str, Any]] = (),
    unit_id: str = "",
    evidence_kind: str = "prose",
) -> str:
    """Build one compact, source-only alpha25 task request."""

    if axis not in _AXIS_INSTRUCTIONS:
        raise ValueError(f"Unsupported alpha25 extraction axis: {axis!r}")
    payload = {
        "evidence_unit_id": unit_id,
        "paper_routing": dict(routing or {}),
        "sample_anchors": [dict(anchor) for anchor in sample_anchors],
    }
    parts = [f"Task scope: {axis}. {_AXIS_INSTRUCTIONS[axis]}\n"]
    if evidence_kind == "table":
        parts.append(_TABLE_PROJECTION_SCOPE)
    if axis not in {"inventory", "all"}:
        parts.append(_FACT_ENVELOPE + "\n")
    parts.append(_PRECISION_CHUNK_WRAPPER + "\n")
    parts.extend(
        [
            "The routing and anchors below are source-derived context, not additional facts.\n",
            f"Task context: {json.dumps(payload, ensure_ascii=False, sort_keys=True)}\n\n",
            "=== OCR EVIDENCE START ===\n",
            f"{evidence.strip()}\n",
            "=== OCR EVIDENCE END ===",
        ]
    )
    return "".join(parts)


def prompt_hash(system_prompt: str, user_prompt: str) -> str:
    digest = hashlib.sha256()
    digest.update(system_prompt.encode("utf-8"))
    digest.update(b"\0")
    digest.update(user_prompt.encode("utf-8"))
    return digest.hexdigest()
