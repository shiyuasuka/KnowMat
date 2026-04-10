from pathlib import Path

import pytest

from knowmat.env_loader import validate_dotenv_file


def test_validate_dotenv_file_accepts_balanced_quotes(tmp_path: Path):
    env_path = tmp_path / ".env"
    env_path.write_text(
        'LLM_MODEL="gpt-5"\nOCR_RENDER_DPI="300"\nKNOWMAT_OCR_DEVICE="gpu:0"\n',
        encoding="utf-8",
    )

    validate_dotenv_file(str(env_path))


def test_validate_dotenv_file_rejects_missing_closing_quote(tmp_path: Path):
    env_path = tmp_path / ".env"
    env_path.write_text('LLM_MODEL="gpt-5"\nOCR_BATCH_SIZE="4\n', encoding="utf-8")

    with pytest.raises(RuntimeError, match=r"line 2: missing closing \" quote"):
        validate_dotenv_file(str(env_path))
