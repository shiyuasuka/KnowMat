# V11 Lossless Chunk Coverage Repair Design

## Goal

Prevent the V11 extraction pipeline from silently producing a partial paper when
one or more LLM chunks fail. The repair keeps GLM-5.2, the alpha.6 prompt/schema,
the bounded multi-item architecture, one extraction run, deterministic
cross-chunk reconciliation, and the existing successful-chunk cache.

The primary acceptance case is the eight-paper regression set. In particular,
the Inconel and Active Learning papers must no longer lose entire samples or all
properties merely because dense responses reached the 8,192-token output limit.

## Scope

This change is limited to chunk planning, failed-chunk recovery, coverage
accounting, provider-error classification, configuration defaults, and focused
tests in the V11 extraction path. It does not change prompts, the output schema,
normalization rules, OCR, the model, or introduce an LLM reconciliation pass.

The independent `relative_change` normalization defect observed in the
Process-Structure-Property paper is included because it prevents promotion after
otherwise complete extraction. The fix is deterministic and limited to mapping
that qualitative composition alias into the existing controlled vocabulary.

## Considered Approaches

### 1. Raise the output token limit only

Increasing the budget to 12,288 or 16,384 tokens would reduce some truncations,
but it depends on provider limits, increases latency, and still cannot guarantee
complete coverage for unusually dense chunks. This is useful as an operator
override, not as the correctness mechanism.

### 2. Increase the initial chunk count only

Keeping chunks near 6,000 characters and allowing more than twelve initial
chunks reduces response size. It does not handle transient HTTP failures, invalid
JSON, or a dense subchunk that still truncates. It improves prevention but not
recovery.

### 3. Bounded lossless coverage with recursive recovery (selected)

Keep initial chunks near the requested size, use a higher bounded initial-chunk
ceiling, recursively split only failed chunks, allocate retry work fairly per
original chunk, and require complete leaf coverage before returning a paper.
This addresses prevention, recovery, and silent partial success while reusing
successful cached responses.

## Chunk Planning

The requested chunk size is a maximum target rather than a value that may be
inflated to satisfy a small chunk-count limit. With the regression command's
6,000-character setting, the planner keeps the effective size at or below that
target and permits up to 24 initial chunks by default.

The maximum remains configurable. If the input would exceed the configured
ceiling, the pipeline raises a clear configuration error rather than silently
enlarging chunks into a known output-truncation regime. Operators may choose a
higher ceiling explicitly for longer papers.

Overlap remains paragraph-aware and is clamped below one third of the effective
chunk size. Initial chunks retain stable ordinal identities so cache entries and
coverage accounting remain deterministic.

## Recursive Failed-Chunk Recovery

Each original chunk is a coverage root. A root is covered when either its initial
request succeeds or all of its retry leaves succeed.

Retryable failures include:

- classified output truncation;
- empty content;
- invalid JSON;
- missing targeted item in the opt-in single-item strategy;
- HTTP 500, 502, and 503 responses;
- timeouts, connection failures, rate limits, and HTTP 429 responses.

For an output/content failure, the failed text is split near a paragraph boundary
into two overlapping children. A child that fails for the same reason may split
again until one of these bounds is reached:

- maximum retry depth: 3 by default;
- minimum retry chunk size: 800 characters by default;
- maximum retry requests per original root: 8 by default;
- maximum retry requests per paper: 64 by default.

Transient provider failures retry the same leaf once before it is split, so a
temporary 500 does not unnecessarily duplicate evidence. Quota exhaustion remains
immediately fatal and cancels pending work.

Retry scheduling is breadth-first and round-robin by original chunk. One early
failure cannot consume the entire paper budget while later failed chunks receive
no attempt. Successful leaves are cached with their stable root/depth/path
identity and are not requested again.

## Coverage Gate

The extractor maintains a coverage tree for every original chunk. It may merge
candidates only after every root is fully covered. A root with an unsuccessful
leaf after exhausting its configured bounds makes the paper fail with an
actionable `incomplete_v11_chunk_coverage` error containing the root and leaf
identities.

The pipeline must not merge successful fragments and report a partial paper as
successful. The CLI therefore distinguishes provider processing completion from
schema promotion: a paper with incomplete coverage is failed and does not produce
a new `final.json`.

## Request and Runtime Bounds

The design stays bounded but no longer assumes that four retry calls are enough
for every paper. Smaller initial chunks replace many expensive, doomed 8,192-token
responses. With three concurrent chunk workers, the expected wall-clock target
remains approximately 7–9 minutes per paper for the regression set, although a
paper suffering repeated provider failures may take longer and fail explicitly.

No three-run confidence selection is added. No new target-discovery call is added
to the default multi-item strategy. No successful chunk is called twice when its
cache entry is available.

## Qualitative Composition Alias Repair

`value_kind="relative_change"` represents a qualitative comparison rather than a
numeric composition value. Before candidate validation, it is deterministically
mapped to `categorical`; the original comparative phrase remains in `value_raw`,
and no numeric value is invented. This removes the three observed fatal errors
without changing facts or the frozen schema.

## Observability

Each paper logs:

- requested and effective chunk size, overlap, and root count;
- successful and failed initial roots;
- retry root, depth, path, reason, and attempt number;
- covered roots versus total roots;
- retry calls used versus per-root and paper bounds;
- explicit complete or incomplete coverage status;
- final merged candidate counts only after coverage succeeds.

The existing elapsed-time and candidate-count logs remain.

## Testing

Focused tests must verify:

1. The planner never inflates chunks above the requested target.
2. Inputs exceeding the configured root ceiling fail clearly.
3. Five or more failed roots all receive retry work fairly.
4. A truncated retry child recursively splits and can complete its root.
5. HTTP 500 is retryable; deterministic validation errors are not.
6. A remaining failed leaf raises incomplete coverage instead of returning a
   partial merge.
7. Fully covered retry leaves merge exactly once in stable source order.
8. Successful cached leaves avoid repeated LLM calls.
9. Quota exhaustion remains immediately fatal.
10. `relative_change` becomes `categorical` while preserving `value_raw`.

The focused V11 compatibility and reconciliation suites must pass together. A
live eight-paper run is performed by the user after local tests; its output is
then compared with the frozen alpha.6 GT using the existing validation script.

## Rollback

The repair is localized to the extraction scheduler and safe alias coercion.
Reverting the implementation restores the previous bounded partial-merge
behavior. Existing cache files remain valid because successful response content
and cache identity are unchanged; retry leaf cache names are additive.
