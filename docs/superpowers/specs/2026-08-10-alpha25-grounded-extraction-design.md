# Alpha25 Grounded Extraction and 30-Paper Regression Design

## Goal

Upgrade KnowMat's material extraction path to the
`material-extractor-alpha25-20260804` contract, run one fresh local OCR pass for
the 30 supplied PDFs, and then iterate only the LLM extraction until the results
are close to the AI-generated ground truth in
`data/gt/papers-native-ids-with-pdf-ocr-images-20260809`.

The final system must generalize across materials papers. Production extraction
must never read GT, branch on a paper filename or title, or contain a repair for a
reviewed paper or sample. Every promoted fact must be supported by the newly
generated OCR or by a traceable PDF-derived artifact. GT is an offline recall and
structure reference, not an authority that can override source evidence.

## Non-Negotiable Requirements

1. Run all 30 PDFs through KnowMat's configured local OCR path once, even though
   the supplied bundle already contains OCR. Do not reuse the supplied OCR.
2. Freeze the successful OCR artifacts. Prompt iterations and performance runs
   rerun only LLM extraction and deterministic post-processing.
3. Use alpha25's `material_extraction_v11.3.3` contract, normalization rules,
   validation rules, and ruleset digest as the single extraction standard.
4. Do not use GT, filenames, paper titles, DOI values, or known sample identifiers
   to influence runtime item discovery, task planning, extraction, reconciliation,
   normalization, or filtering. Paper title and DOI may still be extracted as
   output metadata from the OCR evidence.
5. Do not retain paper-specific repairs. The current Inconel 625, Ti-6Al-4V,
   H230, CCIMA, wall-delay, and named-process sample branches must be removed from
   the production candidate reconciliation and normalization path.
6. Do not silently drop an OCR task, truncated response, invalid candidate, or
   evidence-rejected fact. A paper with unrecovered coverage is failed or flagged,
   never reported as a complete success.
7. Do not run the whole extraction three times and select the highest confidence.
   Use one normal pass and targeted bounded retries only for objective failures.

## Current-State Findings

The attached Inconel regression used 14 outer OCR chunks expanded into 30 evidence
tasks. Four initial responses hit the 8,192-token output limit and caused nine
recovery calls. LLM extraction took 637 seconds. Before normalization, the merged
candidate contained only three items but 62 properties, 100 composition
observations, and 119 structure observations. This is the signature of repeated
full-item generation across overlapping chunks rather than useful evidence growth.

The current prompt loader points at the missing directory
`material-extracor-v11.0.0-alpha.6`, so the current branch cannot load its declared
prompt package. The current `v11_normalize.py` and `v11_reconcile.py` also contain
paper- and sample-specific transformations. Some paths cap structure observations
at three or synthesize experiment matrices for known samples. These behaviors
explain both item collapse and misleadingly large intermediate candidates, and they
violate the generalization requirement.

The 30 GT files use `material_extraction_v11.3.3` and alpha23 metadata. Alpha25
uses the same final schema and ruleset digest, so alpha25 is a compatible rules and
runtime upgrade rather than a new result shape. The GT corpus contains 171 items,
212 composition observations, 354 normalized process stages, 337 structure
observations, 319 characterization records, and 436 properties. It also contains
169 review issues. A strict normalized-substring audit found that only 1,854 of
4,552 GT `source_evidence` strings were literal OCR substrings. This strict metric
is lowered by OCR formatting differences, but it confirms that GT cannot be used as
a truth oracle and that runtime evidence validation is necessary.

## Considered Approaches

### 1. Axis-scoped extraction with alpha25 deterministic normalization

Build a generic item registry from source evidence, plan bounded Composition,
Processing, Structure, and Properties tasks, and let each LLM call return only the
facts in its assigned scope. Reconcile facts deterministically, validate their
evidence, materialize full candidate items, and run alpha25 normalization.

This is the selected approach. It removes the repeated full-schema response that
causes output truncation while preserving complete source coverage.

### 2. Replace alpha6 with alpha25 but retain full-item chunk extraction

This is a smaller code change, but every table slice and overlap still emits all
four axes. Dense papers continue to risk large duplicate responses, truncation, and
post-hoc item collapse. It does not address the demonstrated performance failure.

### 3. Whole-paper extraction repeated three times

This reduces cross-chunk reconciliation but makes output limits and provider latency
worse. Choosing the highest self-reported confidence does not prove truthfulness and
multiplies model cost. It is rejected.

## Architecture

### 1. Fresh Local OCR Run and Freeze Manifest

`data/raw` remains the input root. Each PDF is processed once through KnowMat's
configured OCR backend, producing:

- `data/raw/<paper-stem>/<paper-stem>.md`;
- the parser/OCR JSON required by the existing PDF enrichment path;
- newly recovered or generated figure assets under the paper directory.

The OCR phase runs separately from extraction. It records a manifest containing
the 30 PDF SHA-256 hashes, OCR Markdown SHA-256 hashes, parser JSON hashes, backend
identity, completion status, and creation time. Phase 2 may start only when the
manifest contains 30 successful, non-empty OCR records and every PDF maps to one
Markdown file.

All later LLM commands omit `--force-rerun`. The LLM runner verifies the frozen OCR
manifest before starting and refuses to treat a changed or missing OCR file as the
same baseline. If OCR legitimately must be regenerated, that is a new explicitly
named OCR baseline, not an implicit extraction retry.

### 2. Alpha25 Package Adapter

The prompt, schema, and normalizer loader resolves
`material-extractor-alpha25-20260804/material-extractor` from one configurable
package-root setting with that workspace path as the default. The adapter validates
`deployment_metadata.json`, the compatible schema identifier, and the ruleset
manifest before extraction.

The checked-in alpha25 package is not modified. KnowMat supplies a thin adapter for:

- loading the candidate system and user rules;
- loading only applicable base/application/paradigm/domain overlays;
- invoking alpha25's generic `run_v11.py` normalizer and validator;
- reading normalized output, issues, metadata, and promotability.

The current 3,400-line paper-specific pre-normalizer is replaced by a small generic
candidate preparation and alpha25 invocation layer. Candidate cleanup may repair
only structural provider variations that are unambiguous and evidence-neutral, such
as converting a string evidence field to a one-element list. It may not create a
sample, value, process stage, property, structure observation, or evidence quote.

### 3. Compiled Alpha25 Execution Prompt

Alpha25's top-level v11.3.3 candidate contract is binding. Some later narrative
sections retain legacy normalized-output examples such as `Processing.Equipment`
and `Key_Params`; these conflict with the binding candidate contract. KnowMat uses a
versioned compiled execution prompt that retains alpha25's evidence, item splitting,
four-axis, origin-isolation, range/inequality, table-completeness, and commercial-
alloy constraints while excluding deprecated output examples.

The compiled prompt contains:

- the alpha25 version, schema ID, and ruleset digest;
- the exact candidate envelope and required nullable fields;
- the relevant direction overlays selected from OCR content;
- a compact task contract identifying one axis, one evidence span, and zero or more
  source-derived sample anchors;
- a strict instruction to copy short evidence spans and return JSON only.

Tests pin the source alpha25 prompt hashes and required rule clauses. A package
upgrade that changes the source hash fails fast until the compiled prompt is
reviewed, preventing silent drift.

### 4. Evidence Units and Task Planning

The planner processes OCR content, not filenames or GT. It assigns stable line IDs
to Markdown and creates bounded evidence units:

- prose sections split at headings and paragraph boundaries;
- Markdown tables split by sample columns and bounded row groups while retaining
  table title, headers, units, footnotes, and nearby explanatory text;
- figure captions and deterministic OCR/VLM-derived text kept as explicitly typed
  evidence units.

A lightweight source-driven inventory pass emits only material/sample anchors,
roles, data nature, state labels, and the exact evidence that names them. It does not
emit four-axis facts. The deterministic registry unifies exact and normalized source
aliases only when material identity and state discriminators are compatible.
Ambiguous aliases stay separate and receive a review issue.

Axis tasks then emit compact fact fragments:

- Composition observations and material identity;
- process stages, parameters, equipment, and explicit edges;
- structure observations, entities, features, and characterization;
- raw properties with method, condition, specimen, source type, and origin.

One evidence unit can produce more than one axis task, but no task returns complete
items for unrelated axes. A task coverage ledger records every planned unit, attempt,
response, validation result, retry, and merge result.

### 5. Evidence Gate

Every candidate fact carries one or more non-empty evidence strings plus its source
unit ID. Before reconciliation, the evidence gate checks the strings against only
that unit and its explicitly attached shared context.

Allowed normalization is limited to Unicode compatibility normalization, line-break
joining, whitespace collapse, soft-hyphen removal, and consistent dash/micro-symbol
representation. Semantic similarity, paraphrase matching, title matching, and GT
matching are forbidden. A table fact may use a deterministic rendering of its table
title, headers, row label, selected cells, units, and footnote; that rendered evidence
must be produced by code from the OCR table, not invented by the model.

An ungrounded fact is quarantined with a machine-readable issue and does not enter
the promoted candidate. If removing it leaves a task with no accepted output despite
clear quantitative signals, that task is incomplete and triggers a bounded retry.

### 6. Generic Reconciliation and Materialization

Reconciliation operates on evidence-backed facts. It never knows the paper title or
a reviewed sample name. Identity grouping uses source sample aliases, material
identity, role, data nature, processing state, composition discriminator, and
orientation/state evidence.

Fact deduplication uses axis-specific signatures:

- composition: sample, state, basis, component, raw value, raw unit, and evidence;
- process: sample, stage role/name, raw parameter, raw value/unit, and condition;
- structure: sample, structure kind, entity/feature, raw expression/value, region,
  state, and evidence;
- property: sample, raw property name, raw value/unit, method, condition, specimen,
  origin, and evidence.

Duplicate facts union evidence and keep the highest supported confidence. Conflicting
facts remain separate with review issues unless the source explicitly identifies one
as a correction or alternative condition. Stable IDs are assigned only after merge.
All required empty four-axis containers are then materialized without inventing
facts, and the candidate is passed to alpha25.

### 7. Cache and Performance Controls

OCR artifacts and LLM artifacts use separate cache namespaces. An extraction task
cache key contains the OCR manifest ID, exact evidence-unit hash, task scope, sample
anchors, compiled prompt hash, alpha25 schema/ruleset identity, model endpoint,
response mode, output budget, and thinking mode.

The planner pre-splits dense tables before the first LLM call. Output budgets are
bounded by task type and planned record capacity rather than granting every task an
8,192-token response. Initial extraction uses four concurrent task workers unless
the provider limit requires a lower value.

Retries are objective and local:

1. invalid/empty/truncated JSON or an evidence-rejected task is split once by rows,
   columns, or paragraph boundary;
2. each child is attempted once;
3. a remaining failed leaf is reported as incomplete coverage.

The default path never performs target discovery followed by one full extraction per
target and never repeats a successful task merely to obtain a higher confidence.

## Offline GT Evaluation

GT evaluation runs in a separate command after final JSON files exist. Production
modules do not import the evaluator, accept a GT path, or include GT content in cache
keys. The evaluator first audits GT evidence against the frozen OCR and labels each
GT fact `supported`, `format_mismatch`, `unsupported`, or `ambiguous`.

Comparison matches items semantically using evidence-supported material identity,
composition, process state, and role rather than requiring identical generated
`Sample_ID` strings. It reports per paper and corpus-wide:

- item counts and matched/unmatched items;
- Composition, Processing, Structure, Characterization, and Properties fact counts;
- evidence-supported precision, recall, and F1 by axis;
- core UTS/YS/elongation precision, recall, and F1;
- unsupported GT facts and supported extracted facts absent from GT;
- schema, validation, coverage, retry, token, call-count, and elapsed-time metrics.

The 30 papers are deterministically split by PDF hash into a 20-paper development
set and a 10-paper frozen validation set. Prompt and planner changes may inspect
development reports. The validation report is run only after a candidate change is
frozen. The final accepted version is then run once over all 30 OCR files.

## Acceptance Criteria

### Hard truth and correctness gates

- 30 of 30 PDFs have successful fresh OCR records in one frozen manifest.
- 30 of 30 final outputs are valid `material_extraction_v11.3.3` documents.
- Every promoted raw fact has evidence accepted by the strict OCR evidence gate.
- No paper completes with an unprocessed or unrecovered evidence task.
- No production extraction, reconciliation, or normalization path reads GT.
- No production path branches on a paper title, filename, DOI, or reviewed sample ID.
- Alpha25 reports no fatal validation issue for a promoted final result.

### GT similarity goals

- Evidence-supported core UTS/YS/elongation F1 is at least 0.90.
- Macro-average recall over evidence-supported Composition, Processing, Structure,
  and Properties GT facts is at least 0.85.
- At least 24 of 30 papers have an extracted item count within
  `max(2, 30% of supported GT item count)` of supported GT.
- Corpus item count is within 15% of the evidence-supported GT corpus count.
- Every disagreement report distinguishes extraction misses, extra source-supported
  facts, semantic matching ambiguity, and suspected GT defects.

Truth gates take precedence over similarity goals. An unsupported fact may not be
kept to improve GT score. A supported fact may not be deleted solely because GT
omits it.

### Performance goals

Measured with GLM-5.2, one paper scheduled at a time, four task workers, and a warm
OCR baseline:

- median LLM-only extraction time is at most five minutes per paper;
- P90 LLM-only extraction time is at most eight minutes per paper;
- normal accepted runs contain no output-limit truncations;
- recovery calls are at most 10% of initial extraction task calls;
- logs report task counts, completion tokens, retries, cache hits, rejected evidence,
  coverage state, and wall-clock timings.

Provider outages and quota errors are reported separately from extraction latency
and do not count as successful performance samples.

## Testing

Unit tests cover:

- alpha25 package identity and source hash checks;
- prompt compilation excluding legacy conflicting output shapes;
- fresh OCR manifest completeness and mutation detection;
- paragraph and table evidence-unit construction;
- task coverage ledger state transitions;
- compact axis response validation;
- strict evidence normalization and rejection of paraphrases;
- generic alias grouping and preservation of ambiguous samples;
- axis-specific fact deduplication and conflict preservation;
- deterministic candidate materialization and stable IDs;
- cache invalidation for prompt, model, OCR, schema, and task changes;
- retry bounds and failure on unrecovered coverage;
- production-code scans for GT dependencies and reviewed paper/sample literals.

Integration tests run synthetic and repository fixtures through planning, extraction
stubs, evidence validation, reconciliation, alpha25 normalization, and final schema
validation. They include dense tables, repeated sample aliases, ranges,
inequalities, standard deviations, explicit and absent equipment, reference data,
and conflicting states.

Live verification proceeds in four phases:

1. run and freeze fresh OCR for all 30 PDFs;
2. establish a no-GT extraction baseline on a small development subset;
3. iterate LLM-only on the 20-paper development set, then run the 10-paper frozen
   validation set;
4. run all 30 papers with the frozen implementation and publish the final GT and
   performance report.

## Operational Safety and Rollback

All new outputs use versioned directories. Existing user outputs and the supplied
paper/GT bundles are never overwritten. The alpha25 adapter is selected explicitly;
rollback changes the selected runtime package/version and output directory without
deleting the new OCR baseline or extraction cache. A rollback may restore service,
but the old paper-specific normalizer is not an acceptable final implementation for
this objective.
