"""Multimodal LLM figure description for KnowMat.

Uses the same OpenAI-compatible endpoint configured in .env (LLM_API_KEY,
LLM_BASE_URL, LLM_MODEL) to generate a concise textual description of a
figure image cropped from a scientific paper.

This module is intentionally dependency-light: it only requires ``openai``
(already a transitive dependency via langchain-openai) and the standard
library.  It never raises — failures are logged and an empty string is
returned so the main pipeline is never blocked.
"""

from __future__ import annotations

import base64
import hashlib
import json
import logging
import os
import re
import threading
import time
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from knowmat.pdf.figure_items import iter_resolved_figure_items, normalize_figure_ocr_items

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = (
    "You are a materials science figure analyst. "
    "Describe the key information shown in this figure from a scientific paper. "
    "Focus on: microstructure features, scale bars, phase labels, measurement values, trends, "
    "axis labels, data points, and any quantitative information visible. "
    "Be thorough — extract ALL numerical values, labels, and data visible in the figure. "
    "For multi-panel figures, describe each panel. "
    "Target length: 200-500 words. Do not repeat the caption verbatim. "
    "Return only the final description text. Do not include reasoning, analysis, or <think> tags."
)

_THINK_BLOCK_RE = re.compile(r"<think>.*?</think>", re.IGNORECASE | re.DOTALL)
_THINK_TAG_RE = re.compile(r"</?think>", re.IGNORECASE)

_VLM_MAX_RETRIES = 4
_VLM_EMPTY_MAX_ATTEMPTS = 2
_VLM_RETRY_BACKOFF = 3.0

# Process-global circuit breaker: once the provider reports the account-level
# quota/balance is exhausted (not a transient per-request rate limit), EVERY
# subsequent VLM call in this run will fail the same way.  Retrying each of the
# dozens of figures 4× just burns ~10 min for nothing, so the first such error
# trips this flag and all later calls short-circuit immediately.
_vlm_quota_exhausted = False


def _is_quota_exhausted_error(exc: Exception) -> bool:
    """True for permanent account-level quota/balance exhaustion (not transient).

    MiniMax returns HTTP 429 with code 2056 / "已达到 Token Plan 用量上限" when
    the plan is used up — identical on every retry and for every image, so it
    must be distinguished from an ordinary "too frequent" rate limit.
    """
    msg = str(exc).lower()
    return (
        "2056" in msg
        or "token plan" in msg
        or "用量上限" in msg
        or "insufficient balance" in msg
        or "insufficient_quota" in msg
        or "购买积分" in msg
    )


def _is_rate_limit_error(exc: Exception) -> bool:
    """Check if the exception is a rate limit / too-frequent error."""
    msg = str(exc).lower()
    return "429" in msg or "频繁" in msg or "rate" in msg or "too many" in msg


def _is_non_retryable_error(exc: Exception) -> bool:
    """Check if the error will never succeed on retry (so skip immediately).

    Two permanent classes:
      - content-moderation rejection: some scientific micrographs are flagged
        "image is sensitive" (HTTP 422 / unprocessable), returning the same 422
        on every retry.
      - account quota/balance exhausted (see :func:`_is_quota_exhausted_error`).
    """
    msg = str(exc).lower()
    if _is_quota_exhausted_error(exc):
        return True
    return (
        "422" in msg
        or "unprocessable" in msg
        or "sensitive" in msg
        or "new_sensitive" in msg
    )


class _VlmKeyPool:
    """Thread-safe round-robin pool for VLM API keys.

    Reads keys from (in priority order):
      VLM_API_KEYS=key1,key2,key3       comma-separated list
      VLM_API_KEY_1, VLM_API_KEY_2, …  numbered env vars
      VLM_API_KEY / LLM_API_KEY         single-key fallback

    On a rate-limit hit the caller should call next_key() to get the
    next key immediately instead of sleeping on the same exhausted key.
    Only when all keys have been tried in one round does the pool back off.
    """

    def __init__(self) -> None:
        self._keys: list[str] = []
        self._idx: int = 0
        self._lock = threading.Lock()
        self._load()

    def _load(self) -> None:
        keys: list[str] = []
        multi = os.getenv("VLM_API_KEYS", "")
        if multi:
            keys.extend(k.strip() for k in multi.split(",") if k.strip())
        for i in range(1, 50):
            k = os.getenv(f"VLM_API_KEY_{i}", "")
            if k:
                keys.append(k)
            else:
                break
        single = (
            os.getenv("VLM_API_KEY")
            or os.getenv("LLM_API_KEY")
            or os.getenv("OPENAI_API_KEY", "")
        )
        if single and single not in keys:
            keys.append(single)
        self._keys = keys
        if keys:
            logger.info("VlmKeyPool loaded %d key(s)", len(keys))

    @property
    def size(self) -> int:
        return len(self._keys)

    def all_keys(self) -> list[str]:
        return list(self._keys)

    def next_key(self) -> str:
        with self._lock:
            if not self._keys:
                return ""
            key = self._keys[self._idx % len(self._keys)]
            self._idx += 1
            return key


# Module-level singleton — shared across all threads in the process.
_VLM_POOL: _VlmKeyPool | None = None
_VLM_POOL_LOCK = threading.Lock()


def _get_vlm_pool() -> _VlmKeyPool:
    global _VLM_POOL
    if _VLM_POOL is None:
        with _VLM_POOL_LOCK:
            if _VLM_POOL is None:
                _VLM_POOL = _VlmKeyPool()
    return _VLM_POOL


def _model_uses_responses_api(model: str) -> bool:
    """True if the model must be called via the OpenAI Responses API.

    GPT-5.x on the bilibili gateway is served ONLY at /v1/responses;
    /v1/chat/completions returns "no cluster found".  Mirrors the LLM-side
    routing in ``knowmat.extractors.get_llm``.
    """
    m = str(model or "").lower()
    return any(v in m for v in ("gpt-5", "gpt-5-mini", "gpt-5-nano"))


def _chat_kwargs_to_responses(create_kwargs: dict) -> dict:
    """Convert chat.completions-style kwargs into responses.create kwargs.

    Callers build a single chat-style payload (``messages`` with ``image_url``/
    ``text`` content blocks).  The Responses API instead wants ``input`` with
    ``input_image``/``input_text`` blocks, system text moved to ``instructions``,
    and ``max_tokens`` renamed to ``max_output_tokens``.  ``temperature`` is
    dropped (GPT-5.x rejects non-default values).
    """
    out: dict = {"model": create_kwargs["model"]}
    if "max_tokens" in create_kwargs:
        out["max_output_tokens"] = create_kwargs["max_tokens"]

    instructions: list[str] = []
    rinput: list[dict] = []
    for msg in create_kwargs.get("messages", []):
        role = msg.get("role")
        content = msg.get("content")
        if role == "system":
            if isinstance(content, str):
                instructions.append(content)
            continue
        blocks: list[dict] = []
        if isinstance(content, str):
            blocks.append({"type": "input_text", "text": content})
        else:
            for b in content or []:
                btype = b.get("type")
                if btype == "image_url":
                    url = b.get("image_url", {}).get("url", "")
                    blocks.append({"type": "input_image", "image_url": url})
                elif btype == "text":
                    blocks.append({"type": "input_text", "text": b.get("text", "")})
        rinput.append({"role": role, "content": blocks})

    if instructions:
        out["instructions"] = "\n".join(i for i in instructions if i)
    out["input"] = rinput
    return out


def _vlm_call_with_pool(
    base_url: str | None,
    create_kwargs: dict,
    image_path,
) -> str:
    """Call VLM API with multi-key rotation and exponential backoff.

    Routes by model: GPT-5.x goes through the Responses API (the only endpoint
    that serves it on the bilibili gateway); everything else uses
    chat.completions.  Callers always build chat-style ``create_kwargs`` —
    conversion to the Responses shape happens here so call sites stay uniform.

    Strategy:
      - Cycle through all configured keys on rate-limit errors (immediate,
        no sleep) — only sleep once every key in the pool has been tried.
      - For non-rate-limit errors, apply per-attempt backoff as before.
    """
    try:
        from openai import OpenAI  # type: ignore
    except ImportError:
        logger.warning("openai package not available; skipping figure description.")
        return ""

    pool = _get_vlm_pool()
    keys = pool.all_keys()
    if not keys:
        logger.warning("No VLM API keys configured.")
        return ""

    n = len(keys)
    max_attempts = n * _VLM_MAX_RETRIES
    last_exc: Exception | None = None
    empty_attempts = 0

    # Circuit breaker: account quota already known to be exhausted this run.
    global _vlm_quota_exhausted
    if _vlm_quota_exhausted:
        logger.debug("VLM quota exhausted earlier this run; skipping %s.", image_path)
        return ""

    # Decide endpoint once: GPT-5.x → Responses API, else chat.completions.
    use_responses = _model_uses_responses_api(create_kwargs.get("model", ""))
    responses_kwargs = _chat_kwargs_to_responses(create_kwargs) if use_responses else None

    for attempt in range(max_attempts):
        key = keys[attempt % n]
        client_kwargs: dict = {"api_key": key}
        if base_url:
            client_kwargs["base_url"] = base_url

        try:
            client = OpenAI(**client_kwargs)
            if use_responses:
                response = client.responses.create(**responses_kwargs)
                content = (getattr(response, "output_text", "") or "").strip()
            else:
                response = client.chat.completions.create(**create_kwargs)
                content = (response.choices[0].message.content or "").strip()
            if content:
                return content
            empty_attempts += 1
            logger.warning(
                "VLM empty response for %s (key %d/%d, attempt %d/%d)",
                image_path, attempt % n + 1, n, attempt + 1, max_attempts,
            )
            if empty_attempts >= _VLM_EMPTY_MAX_ATTEMPTS:
                logger.warning(
                    "VLM empty-response budget exhausted for %s after %d attempts",
                    image_path,
                    empty_attempts,
                )
                return ""
        except Exception as exc:
            last_exc = exc
            # Account quota/balance exhausted: permanent for the whole run. Trip
            # the global breaker so the remaining figures don't each retry 4×.
            if _is_quota_exhausted_error(exc):
                if not _vlm_quota_exhausted:
                    _vlm_quota_exhausted = True
                    logger.error(
                        "VLM account quota/balance exhausted (%s). Disabling all "
                        "further VLM calls this run; figures will be skipped.",
                        exc,
                    )
                raise
            if _is_non_retryable_error(exc):
                # e.g. content-moderation "image is sensitive" (422): same result
                # every retry → give up now so the pipeline moves on.
                logger.warning(
                    "VLM permanently rejected %s (non-retryable): %s",
                    image_path, exc,
                )
                raise
            is_rate = _is_rate_limit_error(exc)
            logger.warning(
                "VLM %s for %s (key %d/%d, attempt %d/%d): %s",
                "rate-limited" if is_rate else "failed",
                image_path, attempt % n + 1, n, attempt + 1, max_attempts, exc,
            )
            if is_rate:
                # Rotate to the next key immediately (no sleep within a round).
                # If this was the last key in the round, all keys are exhausted —
                # back off before starting the next round.
                if (attempt + 1) % n == 0:
                    round_num = (attempt + 1) // n
                    wait = _VLM_RETRY_BACKOFF * (2 ** (round_num - 1))  # 3, 6, 12 …
                    logger.info(
                        "All %d VLM key(s) rate-limited (round %d), "
                        "waiting %.1fs before next round…",
                        n, round_num, wait,
                    )
                    time.sleep(wait)
                continue  # try next key / next round immediately

            # Non-rate-limit error: standard per-attempt backoff
            if attempt < max_attempts - 1:
                wait = _VLM_RETRY_BACKOFF * (2 ** (attempt % _VLM_MAX_RETRIES))
                time.sleep(wait)

    if last_exc:
        raise last_exc
    return ""


def _vlm_call_with_retry(
    client,
    create_kwargs: dict,
    image_path,
    max_retries: int = _VLM_MAX_RETRIES,
) -> str:
    """Call VLM API with exponential backoff retry on transient failures."""
    last_exc: Exception | None = None
    empty_attempts = 0
    for attempt in range(max_retries):
        empty_response = False
        try:
            response = client.chat.completions.create(**create_kwargs)
            content = response.choices[0].message.content or ""
            if content.strip():
                return content
            empty_response = True
            empty_attempts += 1
            logger.warning(
                "VLM returned empty content for %s (attempt %d/%d)",
                image_path,
                attempt + 1,
                max_retries,
            )
            if empty_attempts >= _VLM_EMPTY_MAX_ATTEMPTS:
                return ""
        except Exception as exc:
            last_exc = exc
            logger.warning(
                "VLM call failed for %s (attempt %d/%d): %s",
                image_path, attempt + 1, max_retries, exc,
            )
        if empty_response:
            continue
        if attempt < max_retries - 1:
            base_wait = _VLM_RETRY_BACKOFF * (2 ** attempt)
            if last_exc and _is_rate_limit_error(last_exc):
                base_wait = max(base_wait, 8.0 * (attempt + 1))
            time.sleep(base_wait)
    if last_exc:
        raise last_exc
    return ""


def _cache_safe_vlm_payload(value: Any) -> Any:
    """Remove image bytes from a request before hashing its prompt/settings."""
    if isinstance(value, dict):
        cleaned: dict[str, Any] = {}
        for key, row in sorted(value.items()):
            if key == "url" and isinstance(row, str) and row.startswith("data:image/"):
                cleaned[key] = "<image-bytes>"
            else:
                cleaned[key] = _cache_safe_vlm_payload(row)
        return cleaned
    if isinstance(value, list):
        return [_cache_safe_vlm_payload(row) for row in value]
    return value


def _vlm_negative_cache_path(
    base_url: str | None,
    create_kwargs: dict,
    image_path: Path,
) -> Path:
    image_digest = hashlib.sha256(image_path.read_bytes()).hexdigest()
    request_digest = hashlib.sha256(
        json.dumps(
            {
                "image": image_digest,
                "endpoint": str(base_url or "").strip(),
                "request": _cache_safe_vlm_payload(create_kwargs),
            },
            ensure_ascii=False,
            sort_keys=True,
            default=str,
        ).encode("utf-8")
    ).hexdigest()
    configured = os.getenv("KNOWMAT2_VLM_NEGATIVE_CACHE_DIR", "").strip()
    cache_dir = (
        Path(configured)
        if configured
        else Path("data/interim/vlm_negative_cache")
    )
    return cache_dir / f"{request_digest}.json"


def _call_vlm_with_negative_cache(
    base_url: str | None,
    create_kwargs: dict,
    image_path: Path,
    *,
    positive_validator: Callable[[str], bool] | None = None,
) -> str:
    """Reuse validated chart responses and suppress repeated empty requests.

    Positive caching is opt-in twice: callers must provide a validator and
    ``KNOWMAT2_VLM_POSITIVE_CACHE_TTL_SECONDS`` must be greater than zero.  The
    chart pipeline uses this only for parseable JSON classification/calibration
    responses; free-form figure prose therefore keeps its existing behaviour.
    """
    cache_path = _vlm_negative_cache_path(base_url, create_kwargs, Path(image_path))
    now = time.time()
    negative_ttl_seconds = max(
        0,
        int(os.getenv("KNOWMAT2_VLM_NEGATIVE_CACHE_TTL_SECONDS", "86400")),
    )
    positive_ttl_seconds = max(
        0,
        int(os.getenv("KNOWMAT2_VLM_POSITIVE_CACHE_TTL_SECONDS", "0")),
    )
    try:
        if cache_path.is_file():
            entry = json.loads(cache_path.read_text(encoding="utf-8"))
            if float(entry.get("expires_at") or 0) > now:
                status = str(entry.get("status") or "")
                if status == "empty_content":
                    logger.info("VLM negative cache hit for %s", image_path)
                    return ""
                if status == "success" and positive_validator is not None:
                    content = str(entry.get("content") or "")
                    if content and positive_validator(content):
                        logger.info("VLM positive cache hit for %s", image_path)
                        return content
    except (OSError, ValueError, TypeError) as exc:
        logger.debug("Ignoring unreadable VLM cache %s: %s", cache_path, exc)

    content = _vlm_call_with_pool(base_url, create_kwargs, image_path)
    status = "empty_content"
    ttl_seconds = negative_ttl_seconds
    entry: dict[str, Any] = {
        "status": status,
        "created_at": now,
    }
    if content:
        if positive_validator is None or positive_ttl_seconds <= 0:
            return content
        try:
            valid_positive = bool(positive_validator(content))
        except Exception as exc:
            logger.debug("VLM positive-cache validator failed: %s", exc)
            valid_positive = False
        if not valid_positive:
            return content
        status = "success"
        ttl_seconds = positive_ttl_seconds
        entry.update({"status": status, "content": content})
    if ttl_seconds <= 0:
        return content
    try:
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        temporary = cache_path.with_name(
            f"{cache_path.name}.tmp.{os.getpid()}.{threading.get_ident()}"
        )
        entry["expires_at"] = now + ttl_seconds
        temporary.write_text(
            json.dumps(entry, ensure_ascii=False, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        temporary.replace(cache_path)
    except OSError as exc:
        logger.debug("Could not persist VLM cache %s: %s", cache_path, exc)
    return content


def _sanitize_figure_description(text: str) -> str:
    """Strip reasoning tags and keep only the user-facing description."""
    cleaned = str(text or "").strip()
    if not cleaned:
        return ""
    cleaned = _THINK_BLOCK_RE.sub("", cleaned)
    cleaned = _THINK_TAG_RE.sub("", cleaned)
    cleaned = re.sub(r"^\s*final answer:\s*", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned).strip()
    return cleaned


def _encode_image_base64(image_path: Path) -> Optional[str]:
    """Read an image file and return its base64-encoded content."""
    try:
        with open(image_path, "rb") as f:
            return base64.b64encode(f.read()).decode("utf-8")
    except OSError as exc:
        logger.warning("Cannot read figure image %s: %s", image_path, exc)
        return None


def _image_media_type(image_path: Path) -> str:
    suffix = image_path.suffix.lower()
    return {
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".png": "image/png",
        ".gif": "image/gif",
        ".webp": "image/webp",
    }.get(suffix, "image/jpeg")


def describe_figure_image(
    image_path: Path,
    caption: str = "",
    *,
    model: Optional[str] = None,
    api_key: Optional[str] = None,
    base_url: Optional[str] = None,
) -> str:
    """Generate a textual description of a figure image using a multimodal LLM.

    Parameters
    ----------
    image_path:
        Absolute or relative path to the figure image (JPEG/PNG).
    caption:
        Optional figure caption text for context (e.g. "Fig. 1. SEM image of...").
    model:
        Model ID to use.  Defaults to ``LLM_MODEL`` env var.
    api_key:
        API key.  Defaults to ``LLM_API_KEY`` env var.
    base_url:
        Base URL for OpenAI-compatible endpoint.  Defaults to ``LLM_BASE_URL`` env var.

    Returns
    -------
    str
        A concise description of the figure, or empty string on failure.
    """
    resolved_path = Path(image_path)
    if not resolved_path.is_file():
        logger.debug("Figure image not found, skipping description: %s", image_path)
        return ""

    b64 = _encode_image_base64(resolved_path)
    if b64 is None:
        return ""

    _api_key = api_key or _get_vlm_pool().next_key()
    _base_url = base_url or os.getenv("VLM_BASE_URL") or os.getenv("LLM_BASE_URL") or os.getenv("OPENAI_BASE_URL")
    _model = model or os.getenv("VLM_MODEL") or os.getenv("LLM_MODEL", "")

    if not _api_key:
        logger.warning("No VLM_API_KEY/LLM_API_KEY configured; skipping figure description.")
        return ""

    try:
        from openai import OpenAI  # type: ignore
    except ImportError:
        logger.warning("openai package not available; skipping figure description.")
        return ""

    user_text = "Please describe this scientific figure."
    if caption:
        user_text = f"Caption context: {caption}\n\n{user_text}"
    user_text += "\nReturn only the final description. Do not include <think> tags or hidden reasoning."

    media_type = _image_media_type(resolved_path)

    messages = [
        {"role": "system", "content": _SYSTEM_PROMPT},
        {
            "role": "user",
            "content": [
                {
                    "type": "image_url",
                    "image_url": {
                        "url": f"data:{media_type};base64,{b64}",
                    },
                },
                {"type": "text", "text": user_text},
            ],
        },
    ]

    create_kwargs: dict = {
        "model": _model,
        "messages": messages,
        "max_tokens": 2048,
        "temperature": 0.2,
    }

    try:
        content = _call_vlm_with_negative_cache(
            _base_url, create_kwargs, resolved_path
        )
        content = _sanitize_figure_description(content)
        logger.debug("Figure description generated (%d chars) for %s", len(content), image_path)
        return content
    except Exception as exc:
        logger.warning("Figure description LLM call failed for %s: %s", image_path, exc)
        return ""


def describe_figure_image_with_context(
    image_path: Path,
    caption: str = "",
    related_sentences: Optional[List[str]] = None,
    *,
    model: Optional[str] = None,
    api_key: Optional[str] = None,
    base_url: Optional[str] = None,
) -> str:
    """Generate a figure description using VLM with additional paper context.

    Like :func:`describe_figure_image` but includes related sentences from the
    paper body as extra context so the VLM can produce a more precise,
    paper-specific description.
    """
    resolved_path = Path(image_path)
    if not resolved_path.is_file():
        logger.debug("Figure image not found, skipping description: %s", image_path)
        return ""

    b64 = _encode_image_base64(resolved_path)
    if b64 is None:
        return ""

    _api_key = api_key or _get_vlm_pool().next_key()
    _base_url = base_url or os.getenv("VLM_BASE_URL") or os.getenv("LLM_BASE_URL") or os.getenv("OPENAI_BASE_URL")
    _model = model or os.getenv("VLM_MODEL") or os.getenv("LLM_MODEL", "")

    if not _api_key:
        logger.warning("No VLM_API_KEY/LLM_API_KEY configured; skipping figure description.")
        return ""

    try:
        from openai import OpenAI  # type: ignore
    except ImportError:
        logger.warning("openai package not available; skipping figure description.")
        return ""

    user_text = ""
    if caption:
        user_text += f"Caption context: {caption}\n\n"
    if related_sentences:
        user_text += "Related text from the paper body (ranked by relevance to this figure):\n"
        for i, sent in enumerate(related_sentences[:5], 1):
            user_text += f"{i}. {sent}\n"
        user_text += "\n"
    user_text += (
        "Using the image, caption, and related text above as context, "
        "describe the key scientific information shown in this figure. "
        "Be concise (2-4 sentences).\n"
        "Return only the final description. Do not include <think> tags or hidden reasoning."
    )

    media_type = _image_media_type(resolved_path)
    messages = [
        {"role": "system", "content": _SYSTEM_PROMPT},
        {
            "role": "user",
            "content": [
                {
                    "type": "image_url",
                    "image_url": {
                        "url": f"data:{media_type};base64,{b64}",
                    },
                },
                {"type": "text", "text": user_text},
            ],
        },
    ]

    create_kwargs: dict = {
        "model": _model,
        "messages": messages,
        "max_tokens": 2048,
        "temperature": 0.2,
    }

    try:
        content = _call_vlm_with_negative_cache(
            _base_url, create_kwargs, resolved_path
        )
        content = _sanitize_figure_description(content)
        logger.debug("Figure description (with context) generated (%d chars) for %s", len(content), image_path)
        return content
    except Exception as exc:
        logger.warning("Figure description (with context) LLM call failed for %s: %s", image_path, exc)
        return ""


def _fit_chart_block_to_paper_budget(block: str, max_chars: int) -> str:
    """Degrade one chart block to a reference without exceeding ``max_chars``."""
    try:
        limit = max(0, int(max_chars))
    except (TypeError, ValueError):
        limit = 0
    text = str(block or "").strip()
    if not text or limit <= 0:
        return ""
    if len(text) <= limit:
        return text

    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if not lines:
        return ""
    prefixes = (
        "x_axis:",
        "y_axis:",
        "series_total:",
        "context_omitted_series:",
        "total_points:",
        "data_csv:",
        "full_data_externalized:",
    )
    essential = [lines[0]]
    essential.extend(
        line for line in lines[1:] if any(line.startswith(prefix) for prefix in prefixes)
    )
    essential.append("context_truncated: paper_chart_context_budget")
    bounded = "\n".join(dict.fromkeys(essential))
    if len(bounded) <= limit:
        return bounded

    data_line = next((line for line in lines if line.startswith("data_csv:")), "")
    total_line = next((line for line in lines if line.startswith("total_points:")), "")
    minimal = "\n".join(
        line
        for line in (
            lines[0],
            total_line,
            data_line,
            "context_truncated: paper_chart_context_budget",
        )
        if line
    )
    if len(minimal) <= limit:
        return minimal
    if data_line and len(data_line) <= limit:
        return data_line
    return ""


def _existing_chart_context_chars(text: str) -> int:
    """Count already-injected chart blocks for idempotent budget enforcement."""
    pattern = re.compile(
        r"(?ms)^> \[Figure[^\n]*VLM-digitized[^\n]*\]:\n.*?(?=\n{2,}|\Z)"
    )
    return sum(len(match.group(0)) + 2 for match in pattern.finditer(text))


def _has_ambiguous_multi_panel_axes(result: Any) -> bool:
    """True when one proposed calibration explicitly spans multiple panels."""

    if not isinstance(result, dict):
        return False
    summary = result.get("line_summary")
    if not isinstance(summary, dict):
        return False
    axes = " ".join(
        str(summary.get(key) or "") for key in ("x_axis", "y_axis")
    ).casefold()
    if not re.search(r"\b(?:panels?|rows?|columns?)\b", axes):
        return False
    return bool(
        re.search(r"\bother\s+(?:panels?|rows?|columns?)\b", axes)
        or len(re.findall(r"\b(?:panels?|rows?|columns?)\b", axes)) >= 2
        or re.search(
            r"\b(?:top|bottom|left|right)[-\s]+(?:panel|row|column)\b",
            axes,
        )
    )


def inject_figure_descriptions(
    text: str,
    ocr_items: List[Dict[str, Any]],
    *,
    max_workers: int = 2,
    paper_id: str = "",
    output_dir: Optional[str] = None,
    csv_dir: Optional[str] = None,
    source_pdf: Optional[str] = None,
    include_prose_fallback: bool = True,
) -> str:
    """Insert multimodal LLM descriptions above each figure caption in *text*.

    Uses Approach C (CLIP alignment + VLM with context) when possible: CLIP
    finds the most relevant body sentences for each figure, then the VLM
    generates a description using both the image and those sentences as context.
    Falls back to Approach A (VLM-only) if CLIP alignment is unavailable.

    Called from the extraction stage (not OCR), so every LLM call here is
    intentional and gated by ``settings.figure_description_enabled``.

    LLM calls for individual figures run in parallel (up to *max_workers*
    threads) to reduce wall-clock time.
    """
    from concurrent.futures import ThreadPoolExecutor, as_completed

    normalize_figure_ocr_items(ocr_items)
    image_items = iter_resolved_figure_items(ocr_items)
    if not image_items:
        return text

    # --- CLIP alignment (Approach C) ---
    # Chart-only alpha25 runs do not consume generic prose descriptions, so
    # loading CLIP and aligning every micrograph would add latency with no output.
    alignment_by_fig: Dict[str, List[str]] = {}
    if include_prose_fallback:
        try:
            from knowmat.image_text_alignment.aligner import ImageTextAligner

            _output_dir = output_dir
            if not _output_dir and image_items:
                first_img = image_items[0].get("data", {}).get("image_path", "")
                if first_img:
                    _output_dir = str(Path(first_img).parent)
            _paper_id = paper_id or "unknown"

            aligner = ImageTextAligner(
                model="clip", device="cpu", top_k=5,
                min_score=0.0, batch_size=32, caption_blend=0.0,
            )
            alignments = aligner.align(ocr_items, paper_id=_paper_id, output_dir=_output_dir)
            for alignment in alignments:
                fig_num = alignment.figure_num
                if fig_num:
                    sentences = [s.text for s in alignment.related_sentences[:5]]
                    alignment_by_fig[fig_num] = sentences
            if alignment_by_fig:
                logger.info("CLIP alignment completed: %d figures aligned.", len(alignment_by_fig))
        except Exception as exc:
            logger.warning("CLIP alignment unavailable, using VLM-only fallback: %s", exc)

    # Collect valid items to describe, routing each to a processing mode:
    #   "chart" → pure-code line extraction first, optional VLM semantics;
    #             bar/unsupported fallback keeps the existing VLM route.
    #   "prose" → existing VLM prose description → '> [Figure N AI Description]:'
    # Routing key: PaddleOCR-VL crop filename (chart_box vs image_box).
    from knowmat.pdf.chart_digitizer import is_chart_crop
    from knowmat.app_config import settings as _settings

    _chart_enabled = getattr(_settings, "chart_digitization_enabled", True)

    to_describe: List[Dict[str, Any]] = []
    for item in image_items:
        data = item.get("data", {})
        raw_path = data.get("image_path", "")
        img_path = Path(raw_path)
        if not img_path.is_file():
            logger.debug("Figure image not found, skipping description injection: %s", img_path)
            continue
        figure_num = data.get("figure_num", "")
        has_pdf_region = bool(
            source_pdf
            and Path(source_pdf).is_file()
            and isinstance(item.get("bbox"), (list, tuple))
            and len(item.get("bbox")) == 4
        )
        # Local OCR persists crops under generic ``pageNNNN-figureN.jpg``
        # names, which removes the legacy chart_box routing token.  A resolved
        # PDF region is therefore also a safe pure-code chart candidate: the
        # vector digitizer itself must find calibrated axes/curves or return
        # None, after which normal prose handling continues.
        mode = (
            "chart"
            if _chart_enabled and (is_chart_crop(raw_path) or has_pdf_region)
            else "prose"
        )
        # Skip if this figure already has the corresponding injected block.
        if figure_num:
            if mode == "chart" and f"[Figure {figure_num} VLM-digitized" in text:
                continue
            if mode == "prose" and f"> [Figure {figure_num} AI Description]:" in text:
                continue
        item["_describe_mode"] = mode
        to_describe.append(item)

    if not to_describe:
        return text

    # Parallel LLM calls.  chart items → digitize_chart_image + format_digitized_block;
    # prose items → existing VLM prose (Approach C: VLM + CLIP context when available).
    descriptions: Dict[int, str] = {}

    def _describe(idx: int, item: Dict[str, Any]) -> tuple:
        data = item.get("data", {})
        img_path = Path(data.get("image_path", ""))
        caption = data.get("caption", "")
        figure_num = data.get("figure_num", "")
        mode = item.get("_describe_mode", "prose")

        if mode == "chart":
            from knowmat.pdf.chart_digitizer import (
                digitize_chart_image,
                digitize_line_chart_multi,
                digitize_line_chart_region,
                format_digitized_block,
                merge_line_semantics,
            )
            from knowmat.app_config import settings as _cfg

            try:
                line_confidence_threshold = float(
                    getattr(
                        _cfg,
                        "line_chart_classification_min_confidence",
                        0.7,
                    )
                )
            except (TypeError, ValueError):
                line_confidence_threshold = 0.7
            line_confidence_threshold = min(
                1.0, max(0.0, line_confidence_threshold)
            )

            def _confident_line(result: Any) -> bool:
                if not isinstance(result, dict) or result.get("type") != "line":
                    return False
                try:
                    confidence = float(result.get("confidence"))
                except (TypeError, ValueError):
                    return False
                return confidence >= line_confidence_threshold

            # Coordinate truth is always produced by deterministic code.  The
            # source PDF keeps the vector paths that were lost in the JPG crop.
            code_result = None
            if source_pdf and getattr(_cfg, "line_chart_split_enabled", True):
                code_result = digitize_line_chart_region(
                    source_pdf,
                    item.get("page", 0),
                    item.get("bbox"),
                    legacy_image_path=img_path,
                    max_series=getattr(_cfg, "line_chart_max_series", 6),
                )

            # This optional call reads chart class/legend/axis semantics.  Its
            # numeric CSV or key points are never accepted for a code-extracted
            # line chart; merge_line_semantics enforces that invariant.
            if code_result:
                semantic_result = digitize_chart_image(img_path, caption=caption)
                if _has_ambiguous_multi_panel_axes(semantic_result):
                    logger.info(
                        "Rejected Figure %s line digitization: one calibration spans multiple panels",
                        figure_num,
                    )
                    return idx, ("prose", "") if not include_prose_fallback else (
                        "prose",
                        _sanitize_figure_description(
                            describe_figure_image(img_path, caption=caption)
                        ),
                    )
                merged = merge_line_semantics(
                    code_result,
                    semantic_result if _confident_line(semantic_result) else None,
                )
                block = format_digitized_block(
                    merged,
                    figure_num=figure_num,
                    csv_dir=csv_dir,
                    context_max_chars=getattr(
                        _cfg, "chart_context_max_chars_per_figure", 2400
                    ),
                    context_max_series=getattr(
                        _cfg, "chart_context_max_series", 12
                    ),
                )
                if block:
                    return idx, ("chart", block)

            # Pure-code line extraction was inconclusive.  Bar CSV remains a
            # supported discrete VLM contract; a VLM line summary/CSV is not a
            # coordinate fallback and is intentionally ignored here.
            semantic_result = None
            if is_chart_crop(str(img_path)):
                semantic_result = digitize_chart_image(img_path, caption=caption)
            if (
                _confident_line(semantic_result)
                and not _has_ambiguous_multi_panel_axes(semantic_result)
                and getattr(_cfg, "line_chart_split_enabled", True)
            ):
                line_summary = semantic_result.get("line_summary")
                calibration = semantic_result.get("axis_calibration")
                if isinstance(calibration, dict) and isinstance(line_summary, dict):
                    calibration = dict(calibration)
                    calibration.setdefault("x_axis", line_summary.get("x_axis"))
                    calibration.setdefault("y_axis", line_summary.get("y_axis"))
                raster_result = digitize_line_chart_multi(
                    img_path,
                    caption=caption,
                    max_series=getattr(_cfg, "line_chart_max_series", 6),
                    axis_calibration=calibration
                    if isinstance(calibration, dict)
                    else None,
                    allow_axis_calibration_vlm=False,
                )
                if raster_result:
                    merged = merge_line_semantics(raster_result, semantic_result)
                    block = format_digitized_block(
                        merged,
                        figure_num=figure_num,
                        csv_dir=csv_dir,
                        context_max_chars=getattr(
                            _cfg, "chart_context_max_chars_per_figure", 2400
                        ),
                        context_max_series=getattr(
                            _cfg, "chart_context_max_series", 12
                        ),
                    )
                    if block:
                        return idx, ("chart", block)
            if semantic_result and semantic_result.get("type") == "bar":
                block = format_digitized_block(
                    semantic_result,
                    figure_num=figure_num,
                    csv_dir=csv_dir,
                    context_max_chars=getattr(
                        _cfg, "chart_context_max_chars_per_figure", 2400
                    ),
                    context_max_series=getattr(
                        _cfg, "chart_context_max_series", 12
                    ),
                )
                if block:
                    return idx, ("chart", block)
            # Non-digitizable chart (xrd/micrograph/other) may fall back to prose
            # in the general pipeline. Frozen alpha25 chart-only runs disable it
            # so unrelated 200-500 word descriptions cannot inflate task input.

        if not include_prose_fallback:
            return idx, ("prose", "")

        related = alignment_by_fig.get(figure_num, []) if figure_num else []
        if related:
            desc = describe_figure_image_with_context(
                img_path, caption=caption, related_sentences=related
            )
        else:
            desc = describe_figure_image(img_path, caption=caption)
        desc = _sanitize_figure_description(desc)
        return idx, ("prose", desc)

    workers = min(max_workers, len(to_describe))
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(_describe, i, item): i for i, item in enumerate(to_describe)}
        for future in as_completed(futures):
            try:
                idx, payload = future.result()
                if payload and payload[1]:
                    descriptions[idx] = payload
            except Exception as exc:
                logger.warning("Figure description failed: %s", exc)

    # Insert descriptions into text (sequential to keep positions correct).
    try:
        chart_context_budget = max(
            0, int(getattr(_settings, "chart_context_max_chars_per_paper", 12000))
        )
    except (TypeError, ValueError):
        chart_context_budget = 12000
    chart_context_used = min(
        chart_context_budget, _existing_chart_context_chars(text)
    )
    for idx in sorted(descriptions.keys()):
        item = to_describe[idx]
        data = item.get("data", {})
        figure_num = data.get("figure_num", "")
        kind, content = descriptions[idx]

        if kind == "chart":
            # content is already a fully-formed '> [Figure N VLM-digitized ...]:' block
            remaining = max(0, chart_context_budget - chart_context_used)
            bounded = _fit_chart_block_to_paper_budget(
                content, max(0, remaining - 2)
            )
            if not bounded:
                logger.info(
                    "Skipped Figure %s chart context after reaching the %d-char paper budget",
                    figure_num,
                    chart_context_budget,
                )
                continue
            description_block = bounded.rstrip() + "\n\n"
            chart_context_used += len(description_block)
        else:
            label = f"Figure {figure_num}" if figure_num else "Figure"
            description_block = f"> [{label} AI Description]: {content}\n\n"

        if description_block.strip() in text:
            continue

        if figure_num:
            pattern = re.compile(
                r"((?:Fig\.?\s*|Figure\s*)" + re.escape(str(figure_num)) + r"[\s\.\:])",
                re.IGNORECASE,
            )
            match = pattern.search(text)
            if match:
                line_start = text.rfind("\n", 0, match.start()) + 1
                insert_pos = line_start if line_start < match.start() else match.start()
                text = text[:insert_pos] + description_block + text[insert_pos:]
                logger.debug(
                    "Injected %s for Figure %s at position %d", kind, figure_num, insert_pos
                )
                continue

        text = text + "\n\n" + description_block

    return text
