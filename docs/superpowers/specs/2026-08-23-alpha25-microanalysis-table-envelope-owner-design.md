# Alpha25 microanalysis table-envelope owner recovery

## Goal

Improve GLM Alpha25 precision by restoring the material owner, processing
state, and observation location of source-grounded EDS/EDX composition rows.
The change targets rows that are already numerically correct but were attached
to a generic material item after chunk extraction lost the table caption or
the observation location.

The implementation must preserve the professionally reviewed extraction
prompt, Alpha25 schema, and public `final.json` structure. It must be independent
of model and provider, make no OCR/VLM/LLM/API request, preserve core-tensile
claims, and record every migration in `quality_audit.json` and the existing
issues artifacts. GPT expert GT and business GT are offline evaluation sources
only and must never participate in runtime routing.

## Observed failure

The v194 30-paper output retains numerically correct fracture-surface EDS rows,
but two rows are attached to the generic owner `alloy 625 [sintered]`. The
source contains all coordinates needed for a precise owner:

- the figure caption identifies a sintered sample at `1280 °C for 4 h`;
- the table title and nearby prose identify fracture-surface EDS;
- the table has explicit `Point 1` and `Point 2` rows; and
- the prose identifies Point 1 as matrix-like and Point 2 as precipitate-rich.

The current microanalysis resolver only reads a Point/Spot label from the outer
fact owner or the observation `sample_id`. It therefore misses rows whose model
output preserved the location in `measurement`, `raw_expression`, or the first
table cell. A separately extracted oxygen cell for Point 1 has the same loss.

## Considered approaches

1. **Source table-envelope recovery (selected).** Rejoin a cropped fact row to
   one source table using headers and component values, recover its explicit
   table state, and route it to one existing Target owner while retaining the
   Point/Spot label as an observation location.
2. **Create one material item per EDS point.** This confuses measurement
   locations with physical specimens, inflates the item inventory, and makes
   cross-point comparisons harder. It is rejected.
3. **Quarantine every generically owned EDS row.** This can raise nominal
   precision by removing correct measurements, but reduces recall and loses
   useful source-grounded facts. It is rejected.

## Design

### 1. Location recognition

A candidate must be a measured, table-sourced Composition observation. Its
location is recovered in the following order:

1. an existing exact Point/Spot/Area/Location label in the outer or nested
   sample identity;
2. an exact leading Point/Spot/Area/Location cell in cited table-row evidence;
3. one unambiguous Point/Spot/Area/Location label in `measurement`; or
4. one unambiguous label in `raw_expression`, only when the cited table row
   carries the same label.

Presentation text such as `fracture surface Point 1` is normalized to the
observation location `Point 1`. The presentation text remains in `measurement`
and audit evidence. A generic phrase such as `point EDS`, a measured numeric
value, or two competing Point labels does not establish a location.

### 2. Table-envelope reconstruction

The materializer scans the complete source Markdown and builds paper-local EDS
table envelopes. An eligible envelope requires:

- an explicit EDS, EDX, or energy-dispersive-analysis marker in the table
  title, figure caption, or immediately adjacent prose;
- a composition header with named components;
- one or more explicit Point/Spot/Area/Location rows; and
- an explicit source state near that table, such as `sintered at 1280 °C for
  4 h`.

The context window stops at section boundaries, another table/figure envelope,
or an unrelated paragraph. A state from a distant table, preceding experimental
series, bibliography entry, or GT record cannot cross the boundary.

Each fact must rejoin exactly one envelope. Component names, reported values,
and the location label are compared against the source header and row. Every
reported fact component must match the corresponding source cell exactly after
presentation normalization. Cropped prefixes and split trailing columns are
allowed because the source header supplies their coordinate; fuzzy numeric
matching, inferred columns, and row-order guessing are not.

A one-component split row is eligible only when the full source row contains at
least two reported composition components and another accepted fact or the
same exact source envelope proves the location and column. This recovers a
split oxygen cell without permitting arbitrary single-value prose to become a
microanalysis row.

### 3. Owner and condition selection

The source state is resolved only against existing Target inventory owners.
Selection reuses the current state-descriptor and identity-index logic:

- category and every explicit numeric qualifier must agree;
- a more complete existing state may add a source-proven qualifier such as
  `4 h`;
- exactly one best owner must remain after ranking; and
- a Point/Spot/Area/Location is never created as a material item.

The routed Composition observation is placed under that material item, retains
`Point N` as its nested observation `sample_id`, and receives the complete
source-backed `material_state`. Component names, values, units, source type,
measurement text, and raw expression are unchanged.

If the table envelope, location, state, row mapping, or owner is ambiguous, the
fact follows the existing behavior unchanged. The resolver does not use a
generic material-name similarity fallback.

### 4. Audit and public output

Every successful migration emits the issue code
`microanalysis_table_envelope_owner_recovered`. Its complete record contains:

- the original fact payload;
- previous and selected material owner;
- recovered observation location;
- previous and completed material state;
- table title/caption and state-binding evidence;
- the matching source header and complete source row; and
- the exact component-to-column matches used for the decision.

The existing report flow copies this record into `quality_audit.json` and emits
the short code in `issues.json` and `issues.md`. Internal routing markers are
removed before serialization. Public `final.json` retains the top-level keys
`Paper_Metadata`, `Paper_Routing`, `Rule_Metadata`, and `items`; no public field
or schema version is added.

## Error handling and invariants

- No prompt, schema, model/provider setting, API request, or figure extraction
  behavior changes.
- No paper title, alloy name, expected value, point range, model name, or GT
  value appears in production branching logic.
- No accepted numerical fact is deleted by this recovery.
- No unrelated Composition, Processing, Structure, Properties,
  Characterization, or core-tensile record changes.
- Competing table envelopes or owners leave the fact unresolved rather than
  guessing.
- Runtime work is linear or near-linear in source lines, table cells, facts,
  and inventory anchors.

## Verification

Focused tests must cover:

- a fracture-surface EDS table whose caption uniquely supplies temperature and
  time;
- locations present only in measurement or a cropped leading table cell;
- a split one-component trailing column rejoined through the source header;
- preservation of measurement text and all component values;
- ambiguous owners, conflicting states, duplicate Point labels, mismatched
  values, missing EDS markers, and non-composition Point tables remaining
  unchanged;
- no Point material item and no internal-marker leakage;
- complete audit payloads and unchanged `final.json` envelope; and
- model/provider-independent production code.

Rollout first rematerializes the highest-signal paper from the frozen Alpha25
task cache with zero API calls. It then rematerializes all 30 papers and
regenerates comparisons against both the adjudicated GPT expert GT and business
GT.

Acceptance requires:

- 30/30 successful papers, zero fatal validation issues, and zero API calls;
- unchanged prompt digest, Alpha25 schema, and public `final.json` structure;
- every changed fact to have one complete audit record;
- no decrease in raw or unique loose/strict matched counts or recall;
- no decrease in Composition, Processing, Structure, Properties, or
  core-tensile matched counts and recall;
- a strict owner/condition improvement for the audited microanalysis rows; and
- overall raw and unique precision/F1 to be non-regressing against v194.
