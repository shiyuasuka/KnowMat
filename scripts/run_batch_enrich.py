"""Batch OCR + CLIP/VLM Enrichment Pipeline.

Combines async batch OCR (PaddleOCR cloud API) with streaming CLIP+VLM enrichment.
As each paper's OCR completes, enrichment starts immediately.

Usage:
  python scripts/run_batch_enrich.py --input-folder path/to/papers --max-ocr-concurrent 30 --max-enrich-concurrent 4
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import signal
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any, Dict, Optional

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from dotenv import load_dotenv
load_dotenv(Path(__file__).resolve().parent.parent / ".env")

from knowmat.batch.key_pool import KeyPool
from knowmat.batch.models import TaskRecord, TaskStatus
from knowmat.batch.ocr_dispatcher import OCRDispatcher
from knowmat.batch.task_store import TaskStore

logger = logging.getLogger(__name__)

_PROGRESS_INTERVAL = 30.0
_RETRY_INTERVAL = 60.0


class BatchEnrichRunner:
    """Batch OCR → Enrich pipeline.

    [Discovery] → [OCR Submit] → [OCR Poll] → [Enrich Consumer] → [DONE]
    """

    def __init__(
        self,
        input_folder: Path,
        output_dir: Path,
        vendor: str = "paddleocr",
        db_path: Optional[Path] = None,
        max_ocr_concurrent: int = 20,
        max_enrich_concurrent: int = 4,
        vlm_workers: int = 2,
        max_retries: int = 3,
        poll_interval: float = 10.0,
        ocr_timeout: float = 600.0,
        skip_existing: bool = False,
    ):
        self.input_folder = input_folder
        self.output_dir = output_dir
        self.vendor = vendor
        self.max_ocr_concurrent = max_ocr_concurrent
        self.max_enrich_concurrent = max_enrich_concurrent
        self.vlm_workers = vlm_workers
        self.max_retries = max_retries
        self.poll_interval = poll_interval
        self.ocr_timeout = ocr_timeout
        self.skip_existing = skip_existing

        self._db_path = db_path or (input_folder / ".knowmat_batch_enrich.db")
        self._store: Optional[TaskStore] = None
        self._key_pool: Optional[KeyPool] = None
        self._enrich_pool: Optional[ThreadPoolExecutor] = None
        self._shutdown_event = asyncio.Event()
        self._start_time = 0.0
        self._enrich_done_count = 0

    async def run(self) -> Dict[str, Any]:
        self._start_time = time.time()
        self._store = TaskStore(self._db_path)
        self._key_pool = KeyPool.from_env(self.vendor)
        self._enrich_pool = ThreadPoolExecutor(
            max_workers=self.max_enrich_concurrent,
            thread_name_prefix="enrich-worker",
        )

        loop = asyncio.get_event_loop()
        if sys.platform != "win32":
            for sig in (signal.SIGINT, signal.SIGTERM):
                loop.add_signal_handler(sig, self._request_shutdown)

        try:
            new_count = self._discover_tasks()
            self._mark_already_done()

            stats = self._store.get_statistics()
            total = stats["total"]
            done = stats.get(TaskStatus.DONE.value, 0) + stats.get(TaskStatus.SKIPPED.value, 0)
            pending = stats.get(TaskStatus.PENDING.value, 0)
            submitted = stats.get(TaskStatus.OCR_SUBMITTED.value, 0)
            ocr_done = stats.get(TaskStatus.OCR_DONE.value, 0)

            print(f"\n[BATCH-ENRICH] Database: {self._db_path}")
            print(f"[BATCH-ENRICH] Total: {total} | New: {new_count} | Done: {done}")
            print(f"[BATCH-ENRICH] To process: {pending} pending + {submitted} submitted + {ocr_done} ocr_done")
            print(f"[BATCH-ENRICH] Keys: {self._key_pool.size} ({self._key_pool.get_status_summary()})")
            print(f"[BATCH-ENRICH] Concurrency: OCR={self.max_ocr_concurrent} Enrich={self.max_enrich_concurrent} VLM/paper={self.vlm_workers}")
            print()

            if pending == 0 and submitted == 0 and ocr_done == 0:
                print("[BATCH-ENRICH] Nothing to process.")
                return self._store.get_statistics()

            dispatcher = OCRDispatcher(
                store=self._store,
                key_pool=self._key_pool,
                vendor=self.vendor,
                input_folder=self.input_folder,
                max_concurrent_submit=self.max_ocr_concurrent,
                poll_interval=self.poll_interval,
                ocr_timeout=self.ocr_timeout,
            )

            ocr_completion_queue: asyncio.Queue[TaskRecord] = asyncio.Queue()

            await asyncio.gather(
                self._ocr_submit_loop(dispatcher),
                dispatcher.poll_all_submitted(ocr_completion_queue, self._shutdown_event),
                self._enrich_consumer(ocr_completion_queue),
                self._retry_loop(),
                self._progress_reporter(),
                return_exceptions=True,
            )
        except asyncio.CancelledError:
            logger.info("Batch enrich runner cancelled")
        finally:
            if self._enrich_pool:
                self._enrich_pool.shutdown(wait=True)
            if self._store:
                final_stats = self._store.get_statistics()
                self._store.close()
                self._print_final_summary(final_stats)
                return final_stats
        return {}

    # ------------------------------------------------------------------
    # Discovery
    # ------------------------------------------------------------------

    def _discover_tasks(self) -> int:
        pdf_files = sorted(self.input_folder.glob("*.pdf"), key=lambda p: p.name.lower())
        if not pdf_files:
            print(f"[BATCH-ENRICH] No PDF files found in {self.input_folder}")
            return 0
        new_count = self._store.bulk_insert_pending(pdf_files, max_retries=self.max_retries)
        return new_count

    def _mark_already_done(self) -> None:
        if not self.skip_existing:
            return
        pending = self._store.get_tasks_by_status(TaskStatus.PENDING, limit=50000)
        skipped = 0
        for task in pending:
            stem = Path(task.pdf_path).stem
            final_md = self.output_dir / stem / f"{stem}_final.md"
            if final_md.exists():
                self._store.update_status(task.task_id, TaskStatus.SKIPPED)
                skipped += 1
        if skipped:
            print(f"[BATCH-ENRICH] Skipped {skipped} papers with existing _final.md")

    # ------------------------------------------------------------------
    # OCR Submit Loop
    # ------------------------------------------------------------------

    async def _ocr_submit_loop(self, dispatcher: OCRDispatcher) -> None:
        while not self._shutdown_event.is_set():
            tasks = self._store.get_tasks_by_status(TaskStatus.PENDING, limit=50)
            if not tasks:
                await asyncio.sleep(5)
                if self._all_ocr_done():
                    break
                continue
            for task in tasks:
                if self._shutdown_event.is_set():
                    return
                try:
                    await dispatcher.submit_one(task, self._shutdown_event)
                except Exception as exc:
                    logger.error("Submit failed for %s: %s", task.task_id, exc)
                    self._store.mark_failed(task.task_id, str(exc))

    def _all_ocr_done(self) -> bool:
        stats = self._store.get_statistics()
        return (
            stats.get(TaskStatus.PENDING.value, 0) == 0
            and stats.get(TaskStatus.OCR_SUBMITTED.value, 0) == 0
        )

    # ------------------------------------------------------------------
    # Enrich Consumer
    # ------------------------------------------------------------------

    async def _enrich_consumer(self, queue: asyncio.Queue[TaskRecord]) -> None:
        loop = asyncio.get_event_loop()
        sem = asyncio.Semaphore(self.max_enrich_concurrent)

        async def _process(task: TaskRecord):
            async with sem:
                try:
                    self._store.update_status(task.task_id, TaskStatus.LLM_PROCESSING)
                    await loop.run_in_executor(
                        self._enrich_pool, self._enrich_one, task
                    )
                    self._store.update_status(task.task_id, TaskStatus.DONE)
                    self._enrich_done_count += 1
                except Exception as exc:
                    logger.error("Enrich failed for %s: %s", task.task_id, exc)
                    self._store.mark_failed(task.task_id, str(exc))

        tasks_spawned = []
        while not self._shutdown_event.is_set():
            try:
                task = await asyncio.wait_for(queue.get(), timeout=5.0)
                t = asyncio.create_task(_process(task))
                tasks_spawned.append(t)
            except asyncio.TimeoutError:
                if self._all_ocr_done() and queue.empty():
                    break
                continue

        if tasks_spawned:
            await asyncio.gather(*tasks_spawned, return_exceptions=True)

    def _enrich_one(self, task: TaskRecord) -> None:
        from run_pipeline_c import enrich_paper_text

        stem = Path(task.pdf_path).stem
        raw_dir = self.input_folder
        out_dir = self.output_dir / stem
        final_md_path = out_dir / f"{stem}_final.md"

        if self.skip_existing and final_md_path.exists():
            return

        enriched_text = enrich_paper_text(stem, raw_dir, vlm_workers=self.vlm_workers)
        if enriched_text:
            out_dir.mkdir(parents=True, exist_ok=True)
            final_md_path.write_text(enriched_text, encoding="utf-8")
        else:
            raise RuntimeError(f"enrich_paper_text returned None for {stem}")

    # ------------------------------------------------------------------
    # Retry & Progress
    # ------------------------------------------------------------------

    async def _retry_loop(self) -> None:
        while not self._shutdown_event.is_set():
            await asyncio.sleep(_RETRY_INTERVAL)
            failed = self._store.get_tasks_by_status(TaskStatus.FAILED, limit=100)
            retried = 0
            for task in failed:
                if self._store.increment_retry(task.task_id):
                    retried += 1
            if retried:
                logger.info("Retried %d failed tasks", retried)

    async def _progress_reporter(self) -> None:
        while not self._shutdown_event.is_set():
            await asyncio.sleep(_PROGRESS_INTERVAL)
            stats = self._store.get_statistics()
            elapsed = time.time() - self._start_time
            total = stats["total"]
            done = stats.get(TaskStatus.DONE.value, 0)
            skipped = stats.get(TaskStatus.SKIPPED.value, 0)
            failed = stats.get(TaskStatus.FAILED.value, 0)
            pending = stats.get(TaskStatus.PENDING.value, 0)
            submitted = stats.get(TaskStatus.OCR_SUBMITTED.value, 0)
            ocr_done = stats.get(TaskStatus.OCR_DONE.value, 0)
            enriching = stats.get(TaskStatus.LLM_PROCESSING.value, 0)
            print(
                f"[{elapsed:.0f}s] "
                f"done={done} enriching={enriching} ocr_done={ocr_done} "
                f"submitted={submitted} pending={pending} "
                f"failed={failed} skipped={skipped} total={total}"
            )
            if done + skipped + failed >= total:
                break

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _request_shutdown(self) -> None:
        print("\n[BATCH-ENRICH] Shutdown requested, finishing in-flight tasks...")
        self._shutdown_event.set()

    def _print_final_summary(self, stats: Dict[str, Any]) -> None:
        elapsed = time.time() - self._start_time
        done = stats.get(TaskStatus.DONE.value, 0)
        failed = stats.get(TaskStatus.FAILED.value, 0)
        skipped = stats.get(TaskStatus.SKIPPED.value, 0)
        total = stats["total"]
        print(f"\n{'='*60}")
        print(f"[BATCH-ENRICH] Complete in {elapsed:.1f}s")
        print(f"  Done: {done} | Failed: {failed} | Skipped: {skipped} | Total: {total}")
        if failed:
            print(f"  Re-run to retry failed tasks (state persisted in DB)")
        print(f"{'='*60}")


# ======================================================================
# CLI
# ======================================================================

def main():
    parser = argparse.ArgumentParser(
        description="Batch OCR + CLIP/VLM Enrichment Pipeline",
        epilog="""
Examples:
  python scripts/run_batch_enrich.py --input-folder data/raw --max-ocr-concurrent 30 --max-enrich-concurrent 4
  python scripts/run_batch_enrich.py --input-folder data/raw --skip-existing
""",
    )
    parser.add_argument("--input-folder", required=True, help="Folder containing PDF files")
    parser.add_argument("--output-dir", default=None, help="Output directory for _final.md (default: data/extraction_output)")
    parser.add_argument("--max-ocr-concurrent", type=int, default=20, help="Max concurrent OCR API submissions")
    parser.add_argument("--max-enrich-concurrent", type=int, default=4, help="Max concurrent enrichment workers")
    parser.add_argument("--vlm-workers", type=int, default=2, help="VLM concurrency per paper")
    parser.add_argument("--skip-existing", action="store_true", help="Skip papers with existing _final.md")
    parser.add_argument("--batch-db", default=None, help="SQLite state DB path")
    parser.add_argument("--ocr-poll-interval", type=float, default=10.0, help="OCR poll interval (seconds)")
    parser.add_argument("--ocr-timeout", type=float, default=600.0, help="OCR job timeout (seconds)")
    parser.add_argument("--max-retries", type=int, default=3, help="Max retries for failed tasks")
    parser.add_argument("--vendor", default="paddleocr", choices=["paddleocr", "mineru"], help="OCR vendor")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

    input_folder = Path(args.input_folder)
    output_dir = Path(args.output_dir) if args.output_dir else Path("data/extraction_output")
    output_dir.mkdir(parents=True, exist_ok=True)
    db_path = Path(args.batch_db) if args.batch_db else None

    runner = BatchEnrichRunner(
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
    )

    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

    asyncio.run(runner.run())


if __name__ == "__main__":
    main()
