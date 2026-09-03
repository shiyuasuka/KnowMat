#!/usr/bin/env python3
"""Run offline source-aware alpha25/GT evaluation."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from knowmat.evaluation.alpha25_gt import evaluate_corpus, render_markdown


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--results", required=True, type=Path)
    parser.add_argument("--gt", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    report = evaluate_corpus(
        manifest_path=args.manifest,
        results_root=args.results,
        gt_root=args.gt,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    args.output.with_suffix(".md").write_text(
        render_markdown(report), encoding="utf-8"
    )
    print(render_markdown(report))
    return 0 if not report["missing"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
