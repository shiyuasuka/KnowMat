#!/usr/bin/env python3
"""Probe optional extraction request capabilities without scientific input."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

from knowmat.extraction_capabilities import (  # noqa: E402
    probe_extraction_capabilities,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    try:
        result = probe_extraction_capabilities(model=args.model)
    except Exception as exc:
        # Do not print the provider message: compatible SDK errors may echo
        # request bodies or endpoint query data.
        print(
            json.dumps(
                {
                    "status": "failed",
                    "model": args.model,
                    "error_class": exc.__class__.__name__,
                },
                ensure_ascii=False,
            ),
            file=sys.stderr,
        )
        return 2
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
