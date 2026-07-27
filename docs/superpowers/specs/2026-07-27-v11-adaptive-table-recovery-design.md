# V11 Adaptive Table Recovery and Runtime Repair Design

## Decision

Implement the approved **方案 3** for the alpha.6/GLM-5.2 extraction path:

1. detect and slice wide Markdown tables before a doomed multi-item request;
2. switch a still-dense leaf to target discovery plus exact one-item extraction;
3. coerce only known schema-safe aliases;
4. merge cross-chunk semantic aliases deterministically;
5. stop repeated VLM empty-response delays with a small retry budget and a
   content-addressed negative cache.

The repair keeps one extraction run, GLM-5.2, the alpha.6 schema and base prompt,
and deterministic reconciliation. It does not use GT at runtime, hard-code paper
titles, add an LLM reconciliation pass, or enable three-run confidence voting.

## Evidence and Success Criteria

The latest eight-paper run completed only five papers. A 1,710-character retry
leaf in the Variant paper still generated 8,192 tokens because its six sample
columns required multiple full V11 items. Text bisection reduced characters but
did not reduce output cardinality. Interlayer output contained 12 aliases for
three physical conditions, while H230 split one physical material state across
`H230` and `H230_HT`. Two otherwise useful papers failed on harmless response
shape variations: `structure_status="qualitative_only"` and
`Structure_Text=null`.

The same run also showed two independent latency multipliers: repeated
8,192-token extraction failures and up to four empty VLM attempts per figure.
The implementation is accepted when:

- all eight regression papers finish without incomplete-coverage or schema-shape
  failures;
- the six-column Variant table is covered without repeated text-only recursion;
- Inconel retains its recovered three GT materials and complete major axes;
- Interlayer resolves to its three delay conditions rather than delay/label
  aliases, and H230 does not retain a state-only duplicate;
- no distinct samples are merged merely because they share an alloy family;
- a normal provider run returns to approximately 7–9 minutes per paper, measured
  as the median of the eight-paper run, with dense-paper regressions called out
  separately;
- focused and full local test suites retain their current pass level, excluding
  the two documented environment/pre-existing failures.

## Considered Approaches

### 1. Continue recursive text splitting

This preserves the current scheduler but cannot solve a small, structurally wide
table: every child still asks for all sample columns and can emit the same large
JSON. It also spends several long calls before discovering that character count
was not the controlling variable.

### 2. Use discover-then-single-item for every chunk

This bounds every response and is robust, but it adds one discovery call and N
item calls to ordinary chunks that already succeed. It would trade the current
truncation problem for unnecessary latency and request volume.

### 3. Adaptive structural slicing with targeted fallback (selected)

Use the cheap multi-item path for ordinary prose, proactively slice wide tables
by sample column, and fan out to exact items only after structural slicing is
insufficient. This directly reduces response cardinality while keeping the common
case inexpensive.

## Extraction Work Planner

The existing paragraph chunk planner remains the outer coverage boundary. Before
an outer chunk is submitted, a deterministic table planner scans consecutive
pipe-delimited Markdown rows and validates a table only when it has a separator
row and a stable column count. A table is considered wide when it has one
descriptor column plus at least three data/sample columns.

For each wide table, the planner creates subtables containing:

- the original descriptor column;
- one or two adjacent sample columns, two by default;
- the original header and separator rows;
- caption, nearest section heading, and immediately attached footnotes;
- a bounded surrounding context window needed to interpret units and conditions.

The original wide table is not also sent as a multi-item task. Non-table prose is
submitted once as its own evidence task; bounded context repeated around table
slices is tolerated because the deterministic merger removes identical records.
Every task gets a stable identity derived from outer root, table ordinal, and
column range so coverage accounting and caches remain reproducible.

Ragged rows, escaped pipes, and cells containing inline markup are normalized
only for parsing and are reproduced verbatim in the sliced table. If the parser
cannot prove a stable table shape, it leaves the text unchanged and uses the
normal recovery path. It must never silently discard a row or column.

## Adaptive Failure Recovery

Recovery distinguishes output-density failures from provider failures.

For a two-sample table slice that truncates, the planner replaces it with two
one-sample slices. A one-sample slice that still truncates switches to the existing
target-discovery and exact-single-item machinery. Discovery runs on that slice,
uses at most the existing 512-token budget, and the subsequent calls reuse the
existing alpha.6 compact execution prompt with an exact identity. If a slice has
an explicit sample header, discovery must return that identity; an empty or
unrelated discovery result is a retryable coverage failure, not silent success.

For dense non-table evidence, one normal paragraph-aware split is allowed. If a
child still truncates, or an already-small leaf truncates, recovery switches to
discover-then-single-item rather than continuing character-only recursion. A
discovery response with no targets is valid only when the original multi-item
response was empty; it cannot cover a leaf that previously emitted truncated
material content.

Transient 429/500/502/503, timeout, and connection failures continue to retry the
same task before any structural transformation. Quota exhaustion remains fatal.
All recovery work remains subject to the existing per-root and per-paper budgets.
Successful table slices, discovery responses, and exact-item responses use
content-addressed cache keys and are never called twice when a valid cache entry
exists.

## Coverage and Concurrency

An outer chunk is covered only when all of its planned prose/table tasks are
covered. A table slice is covered by either one successful multi-item result or
all of its narrower/exact-item descendants. The paper-level hard gate remains:
one uncovered leaf fails the paper and no partial `final.json` is promoted.

Use a single shared extraction-call concurrency limiter with a default capacity
of four. Outer chunks, target discovery, and exact-item calls all consume the
same limiter; nested fallback therefore cannot multiply concurrency to eight or
more. Fair, round-robin scheduling across outer roots remains in force. Rate-limit
tests must demonstrate that four workers rotate/retry without starving later
roots; the capacity remains configurable for constrained providers.

Each task log records its task kind, root/table/column identity, strategy,
attempt, elapsed time, finish reason, token usage when available, and cache hit.
The paper summary records multi-item calls, table slices, one-item fallbacks,
retries, cached calls, and complete coverage.

## Safe Schema Coercions

Coercion happens before V11 candidate validation and may repair containers or
controlled-vocabulary aliases only; it may not invent a scientific value.

- `structure_status="qualitative_only"` maps to `"reported"`.
- `Composition_Text`, `Process_Text`, or `Structure_Text` equal to `null` maps to
  an empty object.
- Existing `relative_change -> categorical` behavior remains unchanged.

Non-null scalar text, observations, values, units, methods, and evidence are not
rewritten. Other unknown enum values remain validation failures so this repair
does not become a general error suppressor.

## Cross-Chunk Semantic Reconciliation

Reconciliation remains deterministic and paper-local. It builds a graph of item
candidates, then merges only connected candidates that agree on material and
process family and have no conflicting explicit discriminator such as delay,
wall number, sample number, build orientation, or state.

Edges are added using the following evidence, from strongest to weakest:

1. exact normalized sample identity;
2. the same explicit condition value, such as `0 s`, `120 s`, or `300 s`, after
   stripping generic tokens such as alloy, wall, delay, and process names;
3. a quantitative record signature that is unique within the paper and matches
   name, raw value, unit, and test condition/method where present;
4. a base identity plus a removable state suffix when the suffixed candidate is
   a state-only fragment and introduces no contradictory process/property fact.

Rule 2 unifies forms such as `TI64_LHW_DED_DELAY_0S`, `wall_0s_delay`, and
`Ti64_wall_0s_delay`. Rule 3 can attach generic labels such as `condition_A` to
the one delay item whose reported property signature it exactly matches. A
signature shared by multiple items is ambiguous and creates no edge. Rule 4
attaches a fragment such as a bare-material `_HT` alias to its base candidate
only when records are complementary or overlapping; two explicitly different
material states remain separate.

Connected components are merged in stable source order. Record signatures remove
duplicate stages, parameters, structures, compositions, and properties while
unioning evidence and keeping the higher confidence. When an alias marked
`Computed` is bound by exact experimental records to an experimental condition,
the merged item's nature follows the directly evidenced experimental candidate;
the source record and evidence are preserved. No mapping uses filenames, titles,
GT counts, or expected sample names.

## VLM Empty-Response Circuit Breaker

Empty content is handled separately from rate limits and transport errors. An
identical figure request receives at most two total empty-content attempts: the
initial call and one retry, using the next available key when a key pool exists.
It does not enter four rounds of exponential backoff.

After the second empty response, write a negative cache entry keyed by image-byte
digest, model, endpoint identity, and normalized prompt/context digest. Store no
API key or image content. The default negative-cache lifetime is 24 hours and is
configurable; an expired entry permits a fresh attempt. Re-running into a new
output directory therefore skips a recently identical known-empty request while
a changed image, model, prompt, or context gets a new key.

Rate-limit rotation, non-empty transient-error retries, permanent rejection, and
quota circuit-breaking retain their current classifications. Valid VLM responses
continue through sanitization and figure injection unchanged. Logs distinguish a
negative-cache hit from an API attempt so skipped descriptions are observable.

## Tests

Focused extraction tests cover:

1. a six-sample Markdown table becomes three two-sample slices, each preserving
   its descriptor column, header, rows, caption, and footnotes;
2. ragged or non-table pipe text is left intact without lost content;
3. a wide table bypasses the original all-column multi-item call;
4. a truncated two-column slice narrows to one column, then uses exact-item
   fallback if it still truncates;
5. a repeatedly truncated dense prose leaf switches to discovery rather than
   consuming the full recursive split depth;
6. empty or mismatched discovery cannot mark a known-material leaf covered;
7. successful descendants cover the parent exactly once and cache hits make no
   provider call;
8. the shared four-call limiter also bounds nested exact-item work and preserves
   fair retry scheduling;
9. incomplete descendants still fail the paper-level coverage gate.

Schema and reconciliation tests cover:

10. `qualitative_only` and null axis-text objects receive only the specified safe
    coercions;
11. all three Interlayer delay alias forms collapse per delay;
12. generic condition labels bind through unique exact property signatures;
13. a state-only base/suffix fragment merges while conflicting explicit states do
    not;
14. equal alloy family alone, ambiguous shared properties, or different delays do
    not merge;
15. merged record order, evidence union, nature resolution, and item IDs are
    deterministic across candidate order permutations.

Figure tests cover:

16. empty content makes two total attempts and creates a negative entry;
17. the same image/model/endpoint/prompt hits the negative cache without a call;
18. changing any key component or expiring the entry permits another call;
19. rate limits, quota exhaustion, permanent rejection, and valid descriptions
    retain their current behavior.

After local tests, the user runs the same eight-paper alpha.6/GLM-5.2 command once.
The result is compared to the frozen GT with the existing report tooling, and
per-paper phase timings and provider call counts are included in the review.

## Rollback

The adaptive planner, shared limiter, semantic edges, and VLM empty cache are
localized changes with configurable limits. Reverting them restores the existing
lossless recursive scheduler. Cache entries are additive and content-addressed;
older successful extraction caches remain valid, and negative VLM entries can be
ignored or deleted without affecting extracted data.
