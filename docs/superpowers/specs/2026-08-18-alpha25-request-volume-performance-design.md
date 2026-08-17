# Alpha25 Request-Volume Performance Repair

## Goal

Remove the current Alpha25 request-count regression without rerunning OCR,
weakening literal evidence gating, changing the V11 schema, or specializing the
planner for a paper, material, or model. The existing unified inventory and
paper-level reconciliation design remains authoritative.

Acceptance criteria:

- the frozen 30-paper OCR baseline plans materially fewer than the current 522
  initial requests;
- every evidence unit is assigned exactly once and no table cell is discarded;
- a task remains bounded to 8,000 evidence characters;
- dense tables retain the 12,288-token response budget;
- the largest zero-cache paper remains below 240 seconds with six provider
  slots, absent a provider quota or transport retry;
- runtime telemetry separates scheduler queue time from provider call time.

## Evidence and Root Cause

The completed 30-paper run produced 418 successful task-cache responses over
2,799 seconds, or one response every 6.7 seconds. The repaired zero-cache pilot
produced 21 responses over 129 seconds, or one every 6.1 seconds. Provider
throughput therefore did not materially regress.

The current frozen OCR corpus instead plans 522 initial requests. Of these, 171
are table projections. Two conservative planner bounds multiply otherwise safe
requests:

1. prose groups stop after four semantic units even when well below the
   character and density ceilings;
2. tables use four data columns per projection and every projection is an
   isolated request, even when a wider slice is still below the context and
   output budgets.

Figure enrichment is not the primary cause: the completed full run reached its
first task response within seconds of the first enriched Markdown artifacts,
and did not create a new burst of VLM cache entries during extraction.

## Considered Approaches

### 1. Raise provider concurrency only

This may shorten wall time but preserves excess calls and token cost. It can
also turn a planner regression into rate-limit retries. The default process-wide
provider limit therefore remains six.

### 2. Disable table or figure extraction

This would be fast but would silently reduce evidence coverage and violate the
quality boundary. It is rejected.

### 3. Bounded adaptive packing

Pack up to eight prose semantic units while preserving the existing 8,000-char
and fact-density limits. Project tables with up to eight data columns, but also
enforce a 96-cell ceiling and the same evidence-character bound. Very tall,
wide, or text-heavy tables automatically use narrower slices. This is selected
because it removes redundant request envelopes without dropping source.

Offline on the frozen corpus, an eight-unit prose cap plus eight-column table
projection reduces the plan from 522 to approximately 428 tasks (18%).

## Data Flow and Safety

1. Build prose and table evidence units from the frozen Markdown.
2. For prose, coalesce source-ordered units until any of the following is hit:
   8,000 evidence characters, eight semantic units, or the existing adaptive
   density capacity.
3. For tables, compute a per-projection data-column width from the configured
   column ceiling, row count, 96-cell ceiling, and evidence-character ceiling.
   Preserve the row/sample key column in every projection as today.
4. Keep each resulting table projection isolated so sample headers cannot bleed
   into another table.
5. Gate every returned anchor and fact against the exact task evidence, then run
   the existing paper-level reconciliation.

No paper title, GT value, material name, or model name participates in packing.

## Observability

Each provider task records:

- time waiting for the process-wide provider slot;
- actual provider-call duration;
- total task duration and cache status;
- response bytes.

Paper-level coverage reports p50, p95, and maximum provider-call duration plus
aggregate queue wait. Queue contention can then be distinguished from endpoint
latency and model generation time.

## Verification

- planner tests cover eight-unit prose grouping, adaptive table width, cell and
  character ceilings, and lossless unit assignment;
- extraction tests cover queue/provider timing without changing response data;
- the full Alpha25/V11 focused suite passes;
- a zero-cache LLM-only pilot uses the frozen OCR manifest and a new output
  directory, with no OCR call;
- candidate coverage and source-support counts are compared with the existing
  pilot before any full 30-paper rerun.

## Rollback

The prose-unit cap, table-column ceiling, and table-cell ceiling are environment
settings. Restoring four prose units and four table columns reproduces the
previous conservative plan without reverting code.
