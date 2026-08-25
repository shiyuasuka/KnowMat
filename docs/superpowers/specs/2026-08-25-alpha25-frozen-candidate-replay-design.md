# Alpha25 Frozen Candidate Replay Design

## Purpose

Measure and improve the hierarchical verifier independently from stochastic
GLM candidate extraction. The same immutable task-response set must produce a
no-verification control and one or more verified arms. Any difference between
those arms must therefore come from deterministic post-processing or the
verifier, not a fresh candidate draw.

This design is an approved refinement of the hierarchical-verification design.
It does not change the professionally reviewed Alpha25 extraction prompt or
schema, `final.json`, Composition behavior, OCR/VLM/chart inputs, or GT
isolation.

## Considered Approaches

### Selected: exact online cache replay

Stage the complete `v11/02_alpha25_tasks` cache from one frozen source run into
an empty arm, enable extraction cache-only mode, and execute the normal online
planner, evidence gate, promotion, optional verifier, materializer, and
normalizer. Cache identity must match every planned task; a miss is fatal and
never falls through to a provider call.

This preserves the original task responses while rebuilding source scopes with
the exact online planner. It avoids the known offline-rematerializer drift in
task IDs, evidence units, evidence gates, and promotion inputs.

### Rejected: approximate offline rematerialization

Reading every task JSON against the entire paper is fast, but it changes the
evidence scope and task lineage. The existing rematerializer therefore cannot
serve as a same-candidate scientific control.

### Rejected: fresh extraction with a fixed seed

The endpoint does not provide a sufficient determinism guarantee. Matching
settings or temperature does not prove identical candidate responses.

## Replay Contract

The runner accepts a candidate-replay root containing one paper directory per
selected frozen paper. Before work begins it:

1. resolves the source directory by the already selected output name;
2. requires each task response to have a matching identity sidecar;
3. verifies the response SHA-256 recorded in the sidecar;
4. writes an ordered, content-addressed replay manifest without credentials;
5. copies the task cache into the otherwise empty destination arm; and
6. enables cache-only extraction before any paper worker starts.

After extraction it requires every terminal task to be reported as `cached`,
zero extraction-provider time, the same ordered response hashes as the replay
manifest, and no unused or newly written task response. Failure of any check
invalidates the arm.

The run manifest records the replay source, per-paper content manifest, source
and destination hashes, cache-only status, and verifier-provider calls
separately. The source run is never mutated.

## Future-Proof Task Audit

New live task identity sidecars additionally save the exact task source scope
and its SHA-256 outside the cache-key payload. This does not invalidate older
task cache paths. It makes future reconstruction directly auditable even if
planner defaults later change.

The saved scope is scientific source material already permitted by the current
audit contract. Credentials, headers, credential-bearing URLs, GT, paper
titles/IDs, expected values, and expected counts are excluded from cache
identity and production decisions.

## Experimental Flow

For the fixed five-paper pilot:

1. use the precision-fix run's task-response cache as the frozen candidate
   source;
2. replay once with hierarchical verification disabled;
3. prove the replayed no-verification output is reproducible from 100% cache
   hits and record its post-promotion counts;
4. compare the existing verified output to this same-response control against
   business GT and GPT expert GT;
5. if the verifier-only arm misses any precision, recall, core-tensile, or
   runtime gate, do not run 30 papers; and
6. make further verifier changes only through general source-risk rules and
   rerun from the same task-response cache.

GT is read only after both arms are frozen and only by evaluation code.

## Speed Refinement Boundary

If the same-candidate comparison confirms that broad verification is too slow
or deletes useful assertions, a later verified arm may route only
deterministically high-risk Processing and Structure assertions. Literal
low-risk assertions, Composition, and Properties bypass the verifier unchanged.
Risk selection may use source locality, missing or ambiguous owner/state/
condition evidence, duplicate scientific payload, collective-to-individual
fan-out, and conflicting candidate coordinates. It may not use GT, paper
identity/title, expected quantities, or model-name branches.

This refinement is evaluated against the same frozen candidate manifest; it is
not allowed to change the candidate source between iterations.

## Tests and Acceptance

Unit and integration tests cover hash validation, missing sidecars, corrupted
responses, non-empty destinations, cache-only misses, zero extraction-provider
calls, complete cached-task coverage, deterministic manifests, unchanged
public schema, and no model/paper/GT-specific production behavior.

The existing five-paper gates remain authoritative: at least +5 percentage
points global loose precision against each reference, no more than 2 points of
recall loss, at least +3 points F1, core-tensile precision at least 0.93 with
bounded recall loss, complete audit contracts, and median total runtime no more
than 10 minutes. No 30-paper call is permitted until one same-candidate arm
passes every gate.
