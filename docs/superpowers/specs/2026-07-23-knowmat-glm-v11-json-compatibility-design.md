# KnowMat GLM 5.2 v11 JSON Compatibility Design

## Context

KnowMat's v11 extraction path sends the official `material-extracor-v11.0.0-alpha.6` system and user prompts to an OpenAI-compatible endpoint and parses one raw JSON candidate per OCR chunk. The current `glm-5.2` endpoint passes a minimal JSON probe, but the first full paper failed on every initial chunk with `Could not locate a valid JSON object in fallback response`. The run used an approximately 25k-token extraction input and a 3,200-token generation limit. The current parser discards the response metadata and raises the same error for an empty response, prose-only response, and JSON truncated by the output limit.

The eight papers already have fresh PaddleOCR Markdown and JSON under `data/raw`. This change must not repeat OCR, call the VLM, weaken the alpha.6 prompt, alter the v11 output contract, or inject benchmark example answers into prompts.

## Decision

Add a provider-compatible raw-JSON invocation layer for v11 extraction, with GLM 5.2 as the validated target. The layer will request JSON Object output when the configured model supports it, preserve the existing alpha.6 system and user messages, retain response termination metadata, and classify malformed output before deciding whether to retry.

The implementation will prefer deterministic recovery over repairing arbitrary invalid JSON. A response that ends because of the output limit, has no complete JSON object, or contains no usable content will cause the source chunk to be split into smaller evidence-preserving subchunks. Schema-valid candidates continue through the existing deterministic merge and normalization path.

## Components

### Model capability selection

`get_llm` remains the single source of model, endpoint, timeout, and token configuration. The v11 raw invocation will add JSON Object mode for GLM-compatible chat-completions calls. Capability selection must be explicit and narrowly scoped so GPT Responses API and providers that reject `response_format` keep their current behavior.

The generation limit remains configurable. The GLM validation command will use a higher limit than 3,200 tokens, while smaller retry chunks bound the amount of JSON each call must emit.

### Response diagnostics

The raw invocation will collect:

- configured model identity;
- `finish_reason`;
- response content length;
- token-usage counts when supplied;
- a bounded, sanitized beginning and end of malformed content.

No API keys or full paper text will be logged. Errors will distinguish empty content, output-limit truncation, invalid/non-JSON content, and schema validation failure. This makes quota use and recovery behavior observable without persisting sensitive request headers.

### Retry behavior

The existing two-level extraction flow remains in place. Initial chunks run concurrently. A failed chunk is retried as smaller overlapping subchunks. Retry splitting will be triggered by the classified raw-response failures, and a retry cannot silently turn malformed output into an empty successful candidate.

If all initial and retry chunks fail, the paper fails explicitly. Successful chunks are merged in source order. No facts are deleted merely to match the reviewed examples.

### Cache isolation

Each chunk-cache digest will include at least:

- model name;
- endpoint identity without credentials;
- JSON response mode;
- generation token limit;
- system prompt, user prompt, and routing data already included today.

This prevents candidates from `gpt-5.5`, `deepseek-v4-pro`, `glm-5.2`, or different generation settings from being mixed in one validation directory. Existing cache files without the new identity fields will not be considered valid hits for the GLM run.

## Data Flow

1. Load an existing OCR Markdown file from `data/raw`.
2. Run the existing LangGraph routing node.
3. Build the unchanged official alpha.6 system and user prompts.
4. Split the paper into bounded OCR chunks and attach shared methods/test context.
5. Invoke GLM 5.2 in JSON Object mode.
6. Classify the response using content, `finish_reason`, and schema validation.
7. Cache valid candidates; split and retry only failed chunks.
8. Merge candidates, run v11 deterministic normalization and QA, and write `final.json`.
9. Compare all eight finals with the reviewed example package using `scripts/validate_v11_examples.py`.

## Verification

Verification is incremental to limit API consumption:

1. Unit tests cover JSON-mode selection, response classification, model-aware cache digests, and retry behavior.
2. A minimal GLM JSON probe must return a complete object.
3. One real OCR chunk must return schema-valid v11 candidate JSON without exposing request secrets.
4. One full paper must produce `final.json` with schema `material_extraction_v11.3.0` and no fatal QA errors.
5. The remaining seven papers run using the same configuration.
6. The final validation report must account for eight papers, report every semantic/count difference, and show `fatal_count=0` for each completed paper.

Source-supported differences from the example package are reported rather than overwritten. In particular, benchmark inconsistencies must remain visible in the validation report.

## Operational Configuration

The validation run uses `glm-5.2` for all text agents, disables figure description, reuses existing OCR intermediates, and writes to a GLM-specific output directory. The exact token and chunk limits will be fixed after the single-chunk probe, with the starting target being an 8,192-token generation limit and smaller retry chunks than the failed 5,000-character configuration.
