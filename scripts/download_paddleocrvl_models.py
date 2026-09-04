#!/usr/bin/env python3
"""Pre-download PaddleOCR/PaddleOCR-VL models into a project-local directory."""

import argparse
import os
from pathlib import Path


def default_model_dir() -> Path:
    repo_root = Path(__file__).resolve().parents[1]
    return repo_root / "models" / "paddleocrvl1_6"


def main() -> None:
    parser = argparse.ArgumentParser(description="Download PaddleOCR-VL related model files to local directory.")
    parser.add_argument(
        "--model-dir",
        default=None,
        help="Target model cache directory (default: ./models/paddleocrvl1_6)",
    )
    args = parser.parse_args()

    model_dir = Path(args.model_dir).expanduser().resolve() if args.model_dir else default_model_dir().resolve()
    model_dir.mkdir(parents=True, exist_ok=True)

    os.environ["PADDLEOCR_HOME"] = str(model_dir)
    os.environ.setdefault("PADDLE_PDX_CACHE_HOME", str(model_dir))
    print(f"PADDLEOCR_HOME={model_dir}")
    print(f"PADDLE_PDX_CACHE_HOME={os.environ.get('PADDLE_PDX_CACHE_HOME')}")

    try:
        from paddleocr import PaddleOCRVL  # type: ignore

        try:
            PaddleOCRVL(model_dir=str(model_dir))
        except TypeError:
            PaddleOCRVL()
        print("PaddleOCRVL initialized successfully. Model files should be cached locally.")
        return
    except Exception:
        pass

    try:
        from paddleocr import PaddleOCR  # type: ignore

        try:
            PaddleOCR(use_angle_cls=True, lang="en")
        except TypeError:
            PaddleOCR(lang="en")
        print("PaddleOCR initialized successfully. Model files should be cached locally.")
        return
    except Exception as exc:
        raise RuntimeError(
            "Failed to initialize PaddleOCR/PaddleOCRVL. Install `paddleocr` and `paddlepaddle` first."
        ) from exc


if __name__ == "__main__":
    main()



