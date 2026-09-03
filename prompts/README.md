# Prompt Templates Guide

This directory stores editable prompt templates used by KnowMat nodes.

## Files

- The production v11 path validates the checked-in
  `material-extractor-alpha25-20260804/material-extractor` package, pins its
  source prompt hashes, and compiles compact axis-scoped execution prompts in
  `src/knowmat/alpha25/prompt_compiler.py`.
- `extraction_system_template.txt` and `extraction_user_template.txt` are
  retained only as legacy reference files; the v11 LangGraph path does not
  load them.
- `subfield_detection.yaml`: sub-field detection prompt template.
- `evaluation.yaml`: evaluation prompt templates.
- `validator.yaml`: validation prompt templates.
- `flagging.yaml`: final quality flagging prompt templates.

## Conventions

- Keep templates as plain text/YAML with UTF-8 encoding.
- Use explicit placeholders like `{paper_text}` or `<<RUN_ID>>`.
- Avoid embedding runtime-only values in template files.
- If adding a new YAML template, update loader call sites to validate required keys.

## Safe Editing Workflow

1. Update the alpha25 package or compact compiler. Do not edit prompts using GT,
   a paper title, filename, DOI, or sample-specific instruction.
2. Update pinned source hashes only after reviewing alpha25 contract changes.
3. Run `pytest -o addopts='' -q tests/test_prompt_templates.py
   tests/test_alpha25_package.py tests/test_alpha25_production_safety.py`.
4. Run a frozen-OCR LLM regression; GT comparison remains a separate offline command.
