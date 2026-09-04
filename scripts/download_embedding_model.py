#!/usr/bin/env python3
"""Download and validate the CLIP embedding model used by image alignment.

The model is cached by Hugging Face/Transformers outside the repository.  This
command intentionally performs one tiny text embedding so model and tokenizer
weights are both resolved before a long alignment job starts.
"""

from __future__ import annotations

import argparse
import os
import sys


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Download and warm up KnowMat's CLIP embedding model."
    )
    parser.add_argument(
        "--model",
        default=os.getenv("KNOWMAT_EMBEDDING_MODEL", "openai/clip-vit-base-patch32"),
        help="Hugging Face CLIP model id (default: openai/clip-vit-base-patch32)",
    )
    parser.add_argument(
        "--device",
        default=os.getenv("KNOWMAT_EMBEDDING_DEVICE", "cpu"),
        help="Torch device used for the warm-up (default: cpu)",
    )
    args = parser.parse_args()

    try:
        from knowmat.image_text_alignment.embeddings import get_embedding

        encoder = get_embedding("clip", model_name=args.model, device=args.device)
        vectors = encoder.embed_text(["KnowMat embedding model warm-up"])
    except Exception as exc:  # pragma: no cover - depends on optional runtime/network
        print(
            "Embedding model setup failed. Install the optional dependency with "
            '`python -m pip install -e ".[standardization]"` and retry.',
            file=sys.stderr,
        )
        print(f"Reason: {exc}", file=sys.stderr)
        return 1

    print(f"Embedding backend: {encoder.backend_name}")
    print(f"Embedding model: {getattr(encoder, 'model_name', args.model)}")
    print(f"Embedding device: {args.device}")
    print(f"Embedding dimension: {vectors.shape[-1]}")
    print("Embedding model is ready in the local Transformers cache.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
