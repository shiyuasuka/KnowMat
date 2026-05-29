"""Batch OCR → _final.md pipeline (thin CLI wrapper).

The core logic lives in knowmat.batch.finalmd_pipeline.
This script is kept for backward compatibility.

Usage:
  python scripts/batch_ocr_to_finalmd.py --input-folder data/raw
  # Preferred: use the integrated CLI instead:
  python -m knowmat --final-md --paddleocr-api --input-folder data/raw
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

_SCRIPTS_DIR = Path(__file__).resolve().parent
_PROJECT_ROOT = _SCRIPTS_DIR.parent
sys.path.insert(0, str(_PROJECT_ROOT / "src"))

from dotenv import load_dotenv
load_dotenv(_PROJECT_ROOT / ".env")

from knowmat.batch.finalmd_pipeline import run_phase1, run_repair_loop, print_summary


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Batch OCR → CLIP+VLM → _final.md. Guarantees every figure with a valid image has an AI description.",
        epilog="Preferred: python -m knowmat --final-md --paddleocr-api --input-folder data/raw",
    )
    parser.add_argument("--input-folder", default="data/raw")
    parser.add_argument("--output-dir", default="data/extraction_output")
    parser.add_argument("--max-ocr-concurrent", type=int, default=30)
    parser.add_argument("--max-enrich-concurrent", type=int, default=2)
    parser.add_argument("--vlm-workers", type=int, default=4)
    parser.add_argument("--skip-existing", action="store_true")
    parser.add_argument("--repair-only", action="store_true")
    parser.add_argument("--vendor", default="paddleocr", choices=["paddleocr", "mineru"])
    parser.add_argument("--batch-db", default=None)
    parser.add_argument("--ocr-poll-interval", type=float, default=10.0)
    parser.add_argument("--ocr-timeout", type=float, default=600.0)
    parser.add_argument("--max-retries", type=int, default=3)
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

    raw_dir = (_PROJECT_ROOT / args.input_folder).resolve()
    output_dir = (_PROJECT_ROOT / args.output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    db_path = Path(args.batch_db) if args.batch_db else None

    if not raw_dir.exists():
        logging.error("Input folder does not exist: %s", raw_dir)
        sys.exit(1)

    if not args.repair_only:
        run_phase1(
            raw_dir=raw_dir,
            output_dir=output_dir,
            vendor=args.vendor,
            max_ocr_concurrent=args.max_ocr_concurrent,
            max_enrich_concurrent=args.max_enrich_concurrent,
            vlm_workers=args.vlm_workers,
            skip_existing=args.skip_existing,
            db_path=db_path,
            max_retries=args.max_retries,
            poll_interval=args.ocr_poll_interval,
            ocr_timeout=args.ocr_timeout,
        )

    run_repair_loop(
        raw_dir=raw_dir,
        output_dir=output_dir,
        vlm_workers=args.vlm_workers,
        max_workers=args.max_enrich_concurrent,
    )

    print_summary(raw_dir, output_dir)


if __name__ == "__main__":
    main()
