"""Batch OCR + CLIP/VLM Enrichment Pipeline (thin CLI wrapper).

The core logic lives in knowmat.batch.enrich_runner (EnrichRunner).
This script is kept for backward compatibility.

Usage:
  python scripts/run_batch_enrich.py --input-folder data/raw --max-ocr-concurrent 30
  # Preferred: use the integrated CLI instead:
  python -m knowmat --final-md --paddleocr-api --input-folder data/raw
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from dotenv import load_dotenv
load_dotenv(Path(__file__).resolve().parent.parent / ".env")

from knowmat.batch.enrich_runner import EnrichRunner


def main():
    parser = argparse.ArgumentParser(
        description="Batch OCR + CLIP/VLM Enrichment Pipeline",
        epilog="Preferred: python -m knowmat --final-md --paddleocr-api --input-folder data/raw",
    )
    parser.add_argument("--input-folder", required=True)
    parser.add_argument("--output-dir", default=None)
    parser.add_argument("--max-ocr-concurrent", type=int, default=20)
    parser.add_argument("--max-enrich-concurrent", type=int, default=2)
    parser.add_argument("--vlm-workers", type=int, default=4)
    parser.add_argument("--skip-existing", action="store_true")
    parser.add_argument("--retry-incomplete", action="store_true")
    parser.add_argument("--batch-db", default=None)
    parser.add_argument("--ocr-poll-interval", type=float, default=10.0)
    parser.add_argument("--ocr-timeout", type=float, default=600.0)
    parser.add_argument("--max-retries", type=int, default=3)
    parser.add_argument("--vendor", default="paddleocr", choices=["paddleocr", "mineru"])
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

    input_folder = Path(args.input_folder)
    output_dir = Path(args.output_dir) if args.output_dir else Path("data/extraction_output")
    output_dir.mkdir(parents=True, exist_ok=True)
    db_path = Path(args.batch_db) if args.batch_db else None

    runner = EnrichRunner(
        input_folder=input_folder,
        output_dir=output_dir,
        vendor=args.vendor,
        db_path=db_path,
        max_ocr_concurrent=args.max_ocr_concurrent,
        max_enrich_concurrent=args.max_enrich_concurrent,
        vlm_workers=args.vlm_workers,
        max_retries=args.max_retries,
        poll_interval=args.ocr_poll_interval,
        ocr_timeout=args.ocr_timeout,
        skip_existing=args.skip_existing,
        retry_incomplete=args.retry_incomplete,
    )

    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

    asyncio.run(runner.run())


if __name__ == "__main__":
    main()
