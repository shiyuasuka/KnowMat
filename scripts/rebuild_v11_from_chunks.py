#!/usr/bin/env python3
"""Rebuild V11 normalized outputs from cached chunk candidates without LLM calls."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

from knowmat.nodes.extraction import _coerce_v11_candidate, _merge_v11_candidates  # noqa: E402
from knowmat.nodes.v11_normalize import normalize_v11  # noqa: E402


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _paper_text_path(paper_root: Path) -> Path | None:
    candidates = sorted((paper_root / "txt_parse").glob("*_final_output.md"))
    return candidates[0] if candidates else None


def rebuild_paper(paper_root: Path, output_root: Path) -> dict[str, Any]:
    chunk_paths = sorted((paper_root / "v11" / "02_chunks").glob("*.json"))
    if not chunk_paths:
        raise FileNotFoundError(f"No cached V11 chunks under {paper_root}")
    candidates = []
    for path in chunk_paths:
        raw = _read_json(path)
        if raw.get("items"):
            candidates.append(_coerce_v11_candidate(raw))
    if not candidates:
        raise ValueError(f"All cached V11 chunks are empty under {paper_root}")
    source_items = sum(len(candidate.get("items", []) or []) for candidate in candidates)
    merged = _merge_v11_candidates(candidates)
    paper_output = output_root / paper_root.name
    state = {
        "final_data": merged,
        "output_dir": str(paper_output),
        "paper_text_path": str(_paper_text_path(paper_root) or ""),
    }
    normalized = normalize_v11(state)
    validation = normalized.get("v11_validation") or {}
    return {
        "paper": paper_root.name,
        "chunks": len(chunk_paths),
        "source_items": source_items,
        "reconciled_items": len(merged.get("items", []) or []),
        "normalized_items": len((normalized.get("final_data") or {}).get("items", []) or []),
        "validation_state": validation.get("state"),
        "fatal_count": validation.get("fatal_count", 0),
        "review_count": validation.get("review_count", 0),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runs-root", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    args = parser.parse_args()
    paper_roots = sorted(
        path.parent.parent
        for path in args.runs_root.glob("*/v11/02_chunks")
        if path.is_dir()
    )
    if not paper_roots:
        parser.error(f"No paper chunk caches found under {args.runs_root}")
    args.output_root.mkdir(parents=True, exist_ok=True)
    rows = [rebuild_paper(path, args.output_root) for path in paper_roots]
    summary_path = args.output_root / "rebuild_summary.json"
    summary_path.write_text(
        json.dumps({"papers": rows}, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    for row in rows:
        print(
            f"{row['paper']}: source={row['source_items']} "
            f"reconciled={row['reconciled_items']} normalized={row['normalized_items']} "
            f"fatal/review={row['fatal_count']}/{row['review_count']}"
        )
    print(f"Saved summary to {summary_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
