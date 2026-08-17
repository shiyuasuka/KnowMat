# Alpha25 Unified Inventory and Performance Design

## Goal

Reduce the latency and material-item noise of the Alpha25 extraction path
without weakening source grounding, specializing behavior for one paper, or
depending on a model name. The frozen PaddleOCR baseline remains the source
boundary and is not regenerated during this repair.

The acceptance target is:

- every emitted fact remains backed by literal source evidence or an explicitly
  classified deterministic table/figure projection;
- no measurement header, test specimen, microscopy sub-sample, structure entity,
  or bare numeric cell can create a material item;
- prose and table sample identities remain recoverable across chunk boundaries;
- the largest current zero-cache paper finishes its LLM stage in less than 240
  seconds with six provider slots, unless a documented provider-side quota or
  transport retry occurs;
- the 30-paper result remains complete and is evaluated against GT without
  copying unsupported GT facts into prompts or output.

## Evidence and Root Causes

The verified 30-paper corpus currently has complete coverage and no fatal V11
validation failures, but only 15 of 30 papers are within the GT item-count
tolerance. The most visible excess items come from two sources:

1. table orientation heuristics promote ambiguous metric headers such as
   `Material property`, `E_corr`, `d [A]`, composition component headings, and
   bare fitted coefficients into authoritative material anchors;
2. a separate inventory LLM pass discovers sample identities from substantially
   the same evidence later sent to combined four-axis extraction. On the largest
   paper this produces 12 inventory requests plus 19 combined requests before
   recovery.

The six-worker zero-cache run of that paper completed in 299.8 seconds with 31
initial tasks and four recovery tasks. Two long prose tasks exhausted 8,192
completion tokens and were regenerated at 12,288 tokens. The extra recovery
phase accounted for roughly the last 70 seconds.

## Considered Approaches

### 1. Configuration-only concurrency increase

Raising per-paper workers reduces the number of request waves. It does not remove
duplicate inventory/fact requests, and outer paper concurrency can multiply the
provider load. The observed improvement from three to six workers was real, but
the largest paper still required 299.8 seconds.

### 2. Deterministic anchor filtering while retaining inventory passes

Stricter table-anchor rules remove many false material items with a small code
change. Separate inventory and combined passes would remain, and identity role
classification for ambiguous tables would still be disconnected from the facts
that use those identities.

### 3. Unified anchor-and-fact extraction with global reconciliation

Each combined evidence task returns source-copied inventory anchors and typed
facts in one response. All anchors and facts are evidence-gated, then reconciled
once at paper scope. Deterministic anchors are retained only where table structure
explicitly identifies a sample/material/condition dimension. This removes the
duplicated inventory request family and gives cross-chunk reconciliation one
authoritative input set.

Approach 3 is selected. It directly addresses latency and item quality while
preserving the bounded evidence units and source-only contract.

## Contract and Prompt Design

The combined response accepts this backward-compatible shape:

```json
{
  "axis": "combined",
  "anchors": [],
  "facts": []
}
```

`anchors` uses the existing `InventoryAnchor` contract. It is optional when
reading old cache entries, so existing valid cached facts remain parseable. New
prompt and cache identities change together, preventing incompatible reuse.

The combined prompt must require the model to:

- copy the shortest source label that uniquely denotes a material, processing
  state, or comparison material;
- classify `Target` versus `Reference` and experimental versus literature data;
- place processing state in `state_raw` instead of creating synonymous sample
  labels;
- exclude test coupons/specimens when they only describe geometry or orientation,
  FIB/TEM/APT sub-samples, phase/feature names, measurement headers, units, row
  numbers, figure labels, and bare values;
- emit literal `source_evidence` for every anchor and fact;
- keep distinct source-declared samples distinct even when they share a material
  designation.

No prompt contains a paper title, benchmark answer, GT alias list, or model name.

## Deterministic Table Anchors

Table labels have two confidence classes:

- **authoritative**: labels from a row or column dimension explicitly headed by
  Sample, Specimen, Material, Alloy, Condition, State, Batch, Group, Designation,
  Label, or Code, after non-material filtering;
- **hints only**: labels inferred solely because they are not in the first column.

Only authoritative labels enter materialization without LLM classification.
Hints remain in the bounded table evidence and may be returned as evidence-backed
anchors by the combined response.

Generic filtering rejects pure numbers, measurement names/units, composition
component headings, generic schema words, test-property labels, microscopy
sub-samples, and phase/feature entities. Compact source codes such as `1-1`, `#1`,
`HT1`, `WAAM`, and explicit state labels such as `120 s Delay` remain eligible
when their table dimension is authoritative or the combined response classifies
them from source evidence.

## Paper-level Reconciliation

All accepted anchors are collected before facts are routed. Reconciliation is
order-independent and uses only source-derived relationships:

1. normalize presentation variants without erasing meaningful numeric/state
   qualifiers;
2. merge generic suffix variants such as `AF` and `AF sample`;
3. merge synonymous state expressions only when their normalized state category
   and explicit numeric qualifiers agree;
4. keep distinct compact sample codes and distinct treatment qualifiers separate;
5. reject unanchored material identities once a trustworthy paper inventory
   exists;
6. route a test specimen fact back to one uniquely named owning material, but do
   not create a specimen item;
7. preserve ambiguity as a review issue rather than broadcasting facts across
   multiple materials.

## Scheduling and Token Budgets

The default unified strategy does not plan separate inventory tasks. The legacy
separate-inventory path remains available behind an environment switch for
comparison and rollback.

Combined tasks at or above a configurable long-evidence threshold start with the
same 12,288-token ceiling currently used by truncation recovery. Dense tables
continue to use their cell-capacity rule. Short tasks keep the 8,192-token ceiling.
A genuine 12,288-token truncation proceeds to bounded content splitting; it is not
regenerated with the same evidence at another intermediate budget.

A process-wide provider semaphore enforces a configurable total Alpha25 request
budget, defaulting to six. A single paper may use all idle slots. Multiple outer
paper workers share the same six slots, so `outer_workers * inner_workers` cannot
accidentally overload the endpoint. The scheduler and request shape depend on
explicit endpoint configuration, never on a model-name prefix.

## Compatibility and Failure Handling

- Old combined cache payloads without `anchors` parse as an empty anchor list.
- Cache identity includes the prompt digest, response contract, output budget,
  thinking mode, response mode, and OCR baseline.
- Provider option rejection retains the existing capability-based fallback.
- Transport and quota failures never cause evidence fan-out.
- Only malformed/truncated content can create bounded retry/split tasks.
- Coverage remains incomplete if any source leaf is unrecovered.
- Source-gate rejection filters the rejected row and records a review issue; it
  never silently accepts paraphrased evidence.

## Verification

Focused tests must cover:

- combined responses with and without anchors;
- one combined call family and no separate inventory calls in unified mode;
- authoritative versus hint-only table anchors;
- rejection of metric headers, pure numbers, phase/location labels, and
  microscopy/test sub-samples;
- retention of real compact table sample IDs and distinct treatment states;
- cross-chunk identity reconciliation and unique-owner specimen routing;
- long combined tasks starting at 12,288 tokens;
- a process-wide concurrency ceiling shared by simultaneous papers;
- model-name-independent thinking and response-mode behavior;
- complete Alpha25/V11 regression.

Live verification reuses the frozen `alpha25-fresh-20260810` OCR baseline. It runs
the current largest zero-cache paper first, then rematerializes all 30 papers from
cached/new LLM task results. The final report compares item counts, four-axis
recall, core tensile F1, source-support categories, retries, task counts, and
per-paper latency against the current formal baseline. Unsupported GT facts are
reported as benchmark/source disagreement and are never injected into extraction.

## Rollback

An environment setting restores separate inventory tasks. Existing formal output
directories are never overwritten during live comparison, and the frozen OCR
manifest prevents accidental OCR regeneration.
