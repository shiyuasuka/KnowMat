# Alpha25 fresh OCR and LLM-only runbook

The first command must regenerate OCR for every PDF and ignore the OCR cache. A
baseline is frozen only when every PDF in `data/raw` completed in this command.

```bash
source venv/bin/activate
python -m knowmat \
  --input-folder data/raw \
  --ocr-only \
  --force-rerun \
  --skip-cached-ocr \
  --new-ocr-baseline alpha25-fresh-20260810 \
  --ocr-workers 1
```

On a machine that intentionally uses the configured PaddleOCR API, add
`--paddleocr-api`; this still regenerates OCR from all source PDFs and never
imports supplied/GT OCR, while the manifest records the API backend explicitly.

Verify without running OCR or LLM:

```bash
python -m knowmat \
  --input-folder data/raw \
  --verify-ocr-baseline alpha25-fresh-20260810
```

Run LLM extraction again while preserving the frozen OCR:

The CLI loads `LLM_API_KEY`, `LLM_BASE_URL`, and `LLM_MODEL` from the project
`.env` automatically. Do not `source .env` in zsh: this file may contain CRLF
line endings, which can leave a trailing `\r` in boolean settings. Set only
the run-specific overrides below (or omit them when the `.env` values already
match).

```bash
KNOWMAT2_EXTRACTION_THINKING=provider_default \
KNOWMAT2_EXTRACTION_REASONING_EFFORT=low \
KNOWMAT2_EXTRACTION_RESPONSE_FORMAT=json_object \
KNOWMAT2_ALPHA25_GLOBAL_CONCURRENCY=12 \
KNOWMAT2_ALPHA25_WORKERS=6 \
python -m knowmat \
  --input-folder data/raw \
  --output-dir data/output-alpha25 \
  --use-ocr-baseline alpha25-fresh-20260810 \
  --rerun-extraction \
  --workers 6 \
  --max-runs 1
```

The production planner defaults to `KNOWMAT2_ALPHA25_TASK_STRATEGY=combined_axes`
and `KNOWMAT2_ALPHA25_UNIFIED_INVENTORY=1`: one bounded evidence group produces
source-copied material anchors together with composition, processing, structure,
and property facts. Every anchor and fact passes the same literal evidence gate.
This removes the duplicate inventory request family. Set unified inventory to
`0`, or select `axis_scoped`, only for rollback/provider comparison.

Combined evidence is bounded to 6,000 characters per initial request. Longer
semantic units are split before the provider call; this avoids spending a full
12,288-token completion before discovering that a fact-dense 8K block must be
split anyway.

Short combined tasks retain an 8,192-token output budget. Tasks at or above
`KNOWMAT2_ALPHA25_LONG_TASK_CHARS=4000` and tables above 16 projected data cells
start at 12,288 tokens,
so a long response does not first exhaust 8,192 tokens and regenerate the same
evidence. Table prompts extract body-cell facts while using adjacent captions and
prose only for disambiguation; those adjacent facts are covered by prose tasks and
are not duplicated into table responses. Structure-metric tables are additionally
bounded to 16 projected data cells per initial task because their observation wire
format is substantially longer than composition/property rows.
`KNOWMAT2_ALPHA25_GLOBAL_CONCURRENCY` caps all Alpha25 provider calls in one
process. By default, all admitted papers submit evidence tasks to one shared,
work-conserving executor of that width. The example therefore admits six papers
without multiplying endpoint concurrency: whichever paper has ready work uses an
idle slot, and a short paper cannot strand a fixed six-slot partition.

`KNOWMAT2_ALPHA25_WORKERS` remains the local-pool width only when
`KNOWMAT2_ALPHA25_SHARED_TASK_POOL=0` is selected for rollback. With the shared
pool enabled, the CLI caps `--workers` only at the global provider limit. This
calculation is endpoint-configuration based and does not inspect the model name.
Set `KNOWMAT2_ALPHA25_AUTO_BALANCE_FILE_WORKERS=0` only for a deliberate
paper-admission experiment.

For deterministic rematerialization, set `KNOWMAT2_ALPHA25_CACHE_ONLY=1` and
rerun against an output tree containing the matching `v11/02_alpha25_tasks`
files. A missing cache entry fails immediately and never falls through to the
provider.

For the currently configured Volcano endpoint (`https://ark.cn-beijing.volces.com/api/plan/v3`), use the provider-neutral
`KNOWMAT2_EXTRACTION_THINKING=provider_default` together with
`KNOWMAT2_EXTRACTION_REASONING_EFFORT=low`. GLM-5.3 always reasons and rejects
an explicit disabled-thinking request; the low effort setting is therefore the
precision/latency compromise. This is an endpoint setting, not a model-name
rule: when changing providers, probe capabilities first and keep the request
shape provider-neutral.

Initial plus recovery work is bounded by `KNOWMAT2_ALPHA25_MAX_TASKS=64` and
`KNOWMAT2_ALPHA25_MAX_RETRY_TASKS=32`. Truncation retries the same evidence with
a larger output budget before splitting. Timeouts, 429 responses, quota resets,
connection failures, and 5xx responses never split evidence.

`--full-pipeline` is optional. The alpha25 v11 path uses deterministic evaluation
and does not repeat a successful extraction to select a higher confidence result.

After extraction, run the offline comparison. This is the only command allowed to
read GT:

```bash
python scripts/evaluate_alpha25_gt.py \
  --manifest data/raw/.knowmat_ocr_baselines/alpha25-fresh-20260810.json \
  --results data/output-alpha25 \
  --gt data/gt/papers-native-ids-with-pdf-ocr-images-20260809 \
  --output data/output-alpha25/alpha25_gt_report.json
```
