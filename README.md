# KnowMat: Agentic Pipeline for Materials Science Data Extraction

[切换到中文 README](README_zh.md)

KnowMat extracts auditable composition, processing, structure, characterization,
and property data from scientific papers (`.pdf`, `.txt`, or `.md`). The pipeline
uses an OpenAI-compatible language model, evidence-bound extraction, OCR, chart
processing, and quality/audit records while preserving the existing `final.json`
output format.

## Quick start

Requirements: Python 3.11+, an OpenAI-compatible LLM endpoint, and one OCR
backend described below.

```bash
git clone https://github.com/shiyuasuka/KnowMat.git
cd KnowMat
# macOS/Linux (zsh or bash)
python3 -m venv venv
source venv/bin/activate
# Windows PowerShell (use these two lines instead):
# py -3 -m venv venv
# .\\venv\\Scripts\\Activate.ps1
# Windows cmd.exe activation: venv\\Scripts\\activate.bat
python -m pip install --upgrade pip
python -m pip install -e .
python -m pip install -r requirements.txt
cp .env.example .env
```

KnowMat loads `.env` automatically. Do not run `source .env`; this avoids shell
problems with CRLF-formatted files.

## Configure the LLM

Set the provider credentials in `.env`:

```dotenv
LLM_API_KEY=your_api_key
LLM_BASE_URL=https://your-openai-compatible-endpoint/v1
LLM_MODEL=your_model_name
```

The model name and endpoint are intentionally not hard-coded. Provider-specific
reasoning or response-format options can be left at their defaults or copied
from `.env.example` when supported by the selected endpoint.

## OCR backends (choose one)

### Cloud PaddleOCR (recommended for most users)

Add the token to `.env`:

```dotenv
PADDLEOCR_API_TOKEN=your_paddleocr_token
PADDLEOCR_API_URL=https://paddleocr.aistudio-app.com/api/v2/ocr/jobs
```

Run OCR and freeze its manifest, then run extraction:

```bash
python -m knowmat --input-folder data/raw --ocr-only --paddleocr-api \
  --force-rerun --skip-cached-ocr --new-ocr-baseline fresh
python -m knowmat --input-folder data/raw --output-dir data/output \
  --use-ocr-baseline fresh --rerun-extraction --full-pipeline \
  --workers 6 --max-runs 1
```

### Local OCR on NVIDIA Linux/Windows

Local inference requires an NVIDIA GPU and CUDA. After the base installation:

```bash
python -m pip uninstall -y paddlepaddle paddlepaddle-gpu
python -m pip install -r requirements-gpu.txt \
  -i https://www.paddlepaddle.org.cn/packages/stable/cu129/
python scripts/download_paddleocrvl_models.py
python -m knowmat --input-folder data/raw --output-dir data/output \
  --full-pipeline --force-rerun --workers 1
```

The model preload command downloads PaddleOCR-VL 1.5 into `models/`. Model
weights are local-only and are not committed.

### macOS

The production local PaddleOCR path requires NVIDIA CUDA and is not available
on macOS. On Apple Silicon or Intel Macs, use the cloud PaddleOCR path above;
the LLM extraction stage itself works normally in the venv.

MinerU remains an optional compatibility OCR backend: set `MINERU_API_KEY` and
add `--mineru-api` when required by an existing deployment.

## Optional embedding model

Only property standardization and image-text alignment need embeddings:

```bash
python -m pip install -e ".[standardization]"
python scripts/download_embedding_model.py
```

This warms the default CLIP model in the user Transformers cache. Override the
model or device with `KNOWMAT_EMBEDDING_MODEL` and `KNOWMAT_EMBEDDING_DEVICE`.

## Common commands

```bash
# Re-run extraction against an existing frozen OCR baseline
python -m knowmat --input-folder data/raw --output-dir data/output \
  --use-ocr-baseline fresh --rerun-extraction --workers 6 --max-runs 1

# Process selected papers
python -m knowmat --input-folder data/raw --only paper_001 paper_002

# Validate endpoint capabilities before a batch run
python scripts/probe_extraction_capabilities.py --model "your_model_name" \
  --output data/capability_probe.json
```

Successful extraction is not repeated three times by default. Use `--max-runs`
greater than one only when an explicit multi-round comparison is needed.

## Repository layout

```text
src/knowmat/       production runtime
scripts/            operational, replay, evaluation, and model warm-up commands
tests/              regression tests
prompts/            prompt configuration
data/raw/           input PDFs and OCR intermediates
data/output-*/      generated extraction outputs
data/experiments/   generated experiment caches and replays
reports/            generated evaluation reports
models/             downloaded local model weights
```

Experiment outputs and audit reports from `v200` onward remain in local history
directories and are intentionally excluded from source commits.

## Tests

```bash
python -m pytest -o addopts='' -q
```

For the full Alpha25 frozen-OCR procedure, see
[`docs/alpha25-ocr-llm-runbook.md`](docs/alpha25-ocr-llm-runbook.md).
