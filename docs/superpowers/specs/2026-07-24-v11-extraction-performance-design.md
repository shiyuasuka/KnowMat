# V11 Extraction Performance Repair Design

## Goal

Restore the normal end-to-end runtime for one paper to approximately 10 minutes,
with 15 minutes as the normal upper bound, while preserving the complete V11
candidate schema. The repair may sacrifice a small amount of long-tail evidence
coverage, but it must not mix sample identities or silently emit invalid V11 data.

The motivating regression processed a roughly 54,000-character paper as 46 initial
chunks. The GLM path then performed target discovery followed by one full extraction
per target. Twenty-one failed chunks expanded into 41 retry chunks, and many calls
consumed 16,384 completion tokens before returning truncated or empty JSON. This
turned a workflow that previously took 7–8 minutes into a run lasting multiple hours.

## Scope

This change covers the V11 LLM extraction path in `src/knowmat/nodes/extraction.py`,
the extraction-model construction in `src/knowmat/extractors.py`, and focused tests.
It does not change OCR, deterministic V11 normalization, the public CLI, or the V11
output schema.

## Selected Approach

Use bounded multi-item extraction for GLM by default. Each evidence chunk produces
all directly supported V11 items in one response. The existing discover-then-single-
item path remains available behind an environment setting for rollback and provider
comparison.

This approach is preferred over configuration-only tuning because tuning does not
remove the multiplicative request pattern. It is preferred over one whole-paper call
because bounded chunks reduce truncation risk and preserve useful concurrency.

## Architecture and Data Flow

1. Trim the terminal bibliography using the existing extraction preparation logic.
2. Split the remaining paper into paragraph-aware chunks near the configured size.
3. Enforce a paper-level maximum chunk count. If the first split exceeds that limit,
   recompute a larger effective chunk size so the paper stays within the bound.
4. Submit chunks concurrently using the existing chunk worker pool.
5. For the default `multi_item` strategy, send one compact V11 extraction request per
   chunk and allow multiple items in the returned candidate.
6. Repair safe provider variations locally, validate each candidate, and merge all
   successful candidates with the existing V11 merge logic.
7. Preserve `discover_then_single_item` as an explicit opt-in strategy.

Default operational bounds:

- Target chunk size: 8,000 characters.
- Maximum initial chunks per paper: 12.
- Chunk workers: 3.
- Formal extraction output budget: 4,096 tokens.
- Target-discovery output budget when the legacy strategy is selected: 512 tokens.
- Retry depth: one split retry stage.
- Retry task cap: four per paper by default.
- Maximum formal extraction requests: 16 per paper with the default bounds.

These values remain configurable, but invalid or dangerous combinations are clamped
or rejected with a clear log message. In particular, overlap must remain smaller than
the effective chunk size.

## Model Configuration

The extraction output budget must use one authoritative setting:
`KNOWMAT2_EXTRACTION_MAX_TOKENS`. The target-discovery setting must not be mistaken
for the formal extraction budget.

For GLM extraction requests, reasoning/thinking is disabled by default through the
provider-compatible request body. A dedicated environment switch allows re-enabling
it if a future endpoint requires reasoning. Other agents and non-GLM models retain
their current behavior.

The cache identity includes the item strategy, output budget, and GLM thinking mode,
so results generated with materially different settings are not reused incorrectly.

## Failure Handling

Provider output-limit failures are handled only at the affected chunk. Failed chunks
may be split once, subject to the paper-level retry task cap. Retry chunks use the same
multi-item strategy and are never recursively split.

No LLM retry is performed for locally repairable schema aliases. In particular,
`structure_status="observed"` is normalized to `reported` before literal validation.
Aliases whose meaning is ambiguous continue to fail validation rather than being
silently guessed.

If the retry-task budget is exhausted, the extractor merges successful chunks, records
incomplete coverage in logs, and returns only when at least one valid material item
exists. The 15-minute target is an operational success criterion rather than a hard
deadline: an in-flight provider request is allowed to reach its configured timeout.
Complete failure still raises an actionable error.

## Observability

Each paper logs:

- effective chunk size, overlap, chunk count, and maximum chunk count;
- selected item strategy, model output budget, and thinking mode;
- initial request count, successful chunk count, failed chunk count, and retry count;
- elapsed time per chunk and total extraction elapsed time;
- final item/property/composition-observation/structure-observation counts.

Logs must distinguish target discovery from formal extraction so a 512-token discovery
failure cannot be confused with a 4,096-token extraction failure.

## Testing

Focused unit tests will verify:

- GLM defaults to multi-item extraction and does not call target discovery;
- the legacy single-item strategy remains selectable;
- a paper comparable to the regression fixture never exceeds 12 initial chunks;
- extraction and discovery use their correct token settings;
- GLM thinking mode is included in model configuration and cache identity;
- `observed` normalizes to `reported`;
- retry fan-out respects depth and task caps;
- merged multi-item candidates retain distinct sample identities.

The focused tests must pass together with the existing V11 compatibility and prompt
template tests. A live one-paper performance run is a separate, explicitly reported
verification because it consumes model quota. Its success criteria are:

- LLM extraction finishes in approximately 10 minutes and normally under 15 minutes;
- initial chunk count is at most 12;
- total formal extraction requests, including retries, remain bounded;
- the final candidate validates against the V11 model and contains meaningful
  properties as well as material items.

## Rollback

Set the item strategy to `discover_then_single_item` to restore the current GLM
behavior without reverting code. GLM thinking can also be re-enabled independently.
The cache identity prevents cross-strategy cache contamination.
