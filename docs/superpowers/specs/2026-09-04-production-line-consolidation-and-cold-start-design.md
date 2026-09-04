# Production-line consolidation and cold-start documentation design

## Goal

Consolidate the validated Alpha25 extraction capabilities into the production
module layout and make a new checkout reproducible with one documented setup
path. Preserve the existing CLI, `final.json` schema, OCR backends, and
provider-neutral GLM reasoning configuration.

## Scope and retention policy

- Stable runtime code already imported by the main pipeline remains under
  `src/knowmat`; no behavior change is introduced solely by moving files.
- Offline evaluation, replay, capability-probe, and chart-evaluation tools
  remain under `scripts/` and are documented as non-production utilities.
- Results and audit artifacts from experiments `v200` and later remain
  available under their existing data/report locations. They are not copied
  into the production package and are not added to normal commits.
- Older duplicate experiment outputs are not referenced by the new README and
  may remain locally for historical recovery; cleanup is limited to explicit
  generated artifacts and stale entry-point documentation.

## Canonical cold-start paths

The README will present one venv path for all platforms:

```bash
python -m venv venv
source venv/bin/activate          # Windows: venv\\Scripts\\activate
python -m pip install --upgrade pip
python -m pip install -e .
```

The base install supports LLM extraction and cloud OCR. Users select exactly
one OCR backend for a run:

1. Cloud PaddleOCR: configure `PADDLEOCR_API_TOKEN` and use
   `--paddleocr-api`.
2. Local PaddleOCR: install the documented GPU runtime, configure the model
   directory, and run the single maintained model-preload script. The default
   local model is PaddleOCR-VL 1.5.

MinerU remains a compatibility backend in a short optional section. Conda and
PowerShell-specific setup duplication is removed from the primary path.

## Environment configuration

README examples will distinguish required variables (`LLM_API_KEY`,
`LLM_BASE_URL`, `LLM_MODEL`) from OCR-backend variables and optional tracing/
performance settings. The docs will state that KnowMat loads `.env` itself;
users should not `source .env`, which is unsafe for CRLF-formatted files.

For GLM-5.3 and other reasoning models, the documented default is:

```text
KNOWMAT2_EXTRACTION_THINKING=provider_default
KNOWMAT2_EXTRACTION_REASONING_EFFORT=low
```

No model-name-specific branch is documented or added.

## Embedding model setup

Embedding support is optional and only needed for attribute standardization or
alignment workflows. The README will use the package extra as the canonical
installation path:

```bash
python -m pip install -e ".[standardization]"
```

It will provide one small preflight command that initializes/downloads the
configured sentence-transformers model into the user cache and reports the
resolved model path. Model weights remain outside git.

## Repository organization and ignore rules

The README will document:

- `src/knowmat/`: production runtime;
- `scripts/`: reproducible operational and offline evaluation commands;
- `tests/`: regression tests;
- `data/`, `reports/`, `tmp/`: generated local artifacts.

`.gitignore` will ignore generated OCR caches, Alpha25 output trees,
experiment/evaluation directories, reports, temporary logs, and local model
weights while leaving source, tests, and the retained `v200+` history
available locally.

## Compatibility and validation

- Existing CLI flags remain valid; no new required flag is introduced.
- The maintained PaddleOCR preload command is the only documented local model
  download entry point; the obsolete 1.0-only helper is removed or clearly
  marked as historical if still needed by a legacy test.
- Validate README command snippets, environment loading, packaging metadata,
  and focused Alpha25/OCR tests before committing implementation changes.

