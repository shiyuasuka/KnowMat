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
and fact-density limits. Project short, sparse tables with up to eight data
columns. Expansion beyond the proven four-column baseline is allowed only while
the projection stays within 36 data cells; tall or dense tables therefore fall
back to four columns. Every projection also keeps the same evidence-character
bound. This is selected because it removes redundant request envelopes without
dropping source or widening high-output tables.

Offline on the frozen corpus, an eight-unit prose cap plus density-bounded table
projection reduces the plan from 522 to 447 tasks (14.4%), including a reduction
from 171 to 131 table tasks.

## Data Flow and Safety

1. Build prose and table evidence units from the frozen Markdown.
2. For prose, coalesce source-ordered units until any of the following is hit:
   8,000 evidence characters, eight semantic units, or the existing adaptive
   density capacity.
3. For tables, compute a per-projection data-column width from the configured
   column ceiling, row count, 36-cell expansion budget, four-column safety
   floor, and evidence-character ceiling. Preserve the row/sample key column in
   every projection as today.
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

## Row-local contract adjudication

A syntactically complete combined response may contain many valid facts and one
or more malformed optional rows. A malformed row must not invalidate and
regenerate its valid siblings. The response parser therefore validates anchors
and facts independently, preserves every contract-valid row for the existing
literal evidence gate, and records each invalid row as a visible
`invalid_fact_contract` rejection. Missing required factual fields such as a
property `value_raw` are never synthesized.

These rejections are stored with the sanitized task cache so a cache replay has
the same rejected-fact count and review evidence as the live call. A response
that cannot be decoded as JSON, has no legal response envelope, or is truncated
still follows the existing bounded recovery path. Row-local adjudication only
prevents a complete response from multiplying requests because an independent
row failed its schema contract.

## Verification

- planner tests cover eight-unit prose grouping, adaptive table width, cell and
  character ceilings, and lossless unit assignment;
- extraction tests cover queue/provider timing without changing response data;
- contract tests cover preserving valid siblings, rejecting an incomplete row,
  and retaining the rejection across sanitized cache replay;
- the full Alpha25/V11 focused suite passes;
- a zero-cache LLM-only pilot uses the frozen OCR manifest and a new output
  directory, with no OCR call;
- candidate coverage and source-support counts are compared with the existing
  pilot before any full 30-paper rerun.

## Rollback

The prose-unit cap, table-column ceiling, and table-cell ceiling are environment
settings. Restoring four prose units and four table columns reproduces the
previous conservative plan without reverting code.
