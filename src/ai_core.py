"""ai_core.py — AI provider routing with Gemini, Groq, and OpenRouter.

Uses the new google-genai SDK (replaces deprecated google-generativeai).
"""
from __future__ import annotations

import io
import time
import threading
from typing import Optional, Any, List
from PIL import Image

import config
from logger_setup import logger
from openrouter_client import generate_code_from_openrouter, OpenRouterError
from groq_client import chat_with_groq, explain_code_with_groq, GroqError
from key_manager import gemini_key_tracker

# ---------------------------------------------------------------------------
# New google-genai SDK client cache
#
# The new SDK uses a Client object per API key instead of a global configure()
# call. We cache one Client per key so we never recreate it on each request.
# The lock only covers client construction — not the actual API call — so
# concurrent threads are never serialised during the network round-trip.
# ---------------------------------------------------------------------------

from google import genai
from google.genai import types as genai_types

_client_lock: threading.Lock = threading.Lock()
_client_cache: dict[str, genai.Client] = {}


def _get_client(api_key: str) -> genai.Client:
    """Return a cached genai.Client for *api_key*, creating if needed."""
    if api_key in _client_cache:
        return _client_cache[api_key]
    with _client_lock:
        if api_key not in _client_cache:
            _client_cache[api_key] = genai.Client(api_key=api_key)
    return _client_cache[api_key]


def clear_client_cache() -> None:
    """Discard all cached genai.Client objects and reset key cooldowns.

    Called after the settings panel saves new API keys so the next
    generate_content_with_fallback() call picks up the fresh key list
    without requiring a full app restart.
    """
    with _client_lock:
        _client_cache.clear()
    gemini_key_tracker.reset()
    logger.info("🔄 Gemini client cache cleared — new keys will be used on next call.")


# ---------------------------------------------------------------------------
# Custom exceptions
# ---------------------------------------------------------------------------

class AIProviderError(Exception):
    """Base exception for all AI-provider failures."""


class GeminiError(AIProviderError):
    """Raised specifically for Google Gemini API failures."""


AIError = AIProviderError   # backward-compatible alias


# ---------------------------------------------------------------------------
# Retry with exponential backoff
# ---------------------------------------------------------------------------

_MAX_RETRIES = 3
_BASE_DELAY  = 1.0


def _with_backoff(fn, *args, provider: str = "API", **kwargs):
    """Call fn retrying up to _MAX_RETRIES times on rate-limit errors."""
    last_error = None
    for attempt in range(1, _MAX_RETRIES + 1):
        try:
            return fn(*args, **kwargs)
        except Exception as exc:
            last_error = exc
            if not _is_rate_limit_error(exc):
                raise
            if attempt == _MAX_RETRIES:
                logger.error(f"❌ {provider} rate limit — all {_MAX_RETRIES} retries exhausted.")
                raise
            wait = _BASE_DELAY * (2 ** (attempt - 1))
            logger.warning(f"⚠️ {provider} rate limit (attempt {attempt}/{_MAX_RETRIES}). Retrying in {wait:.0f}s...")
            time.sleep(wait)
    if last_error:
        raise last_error


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------

def _get_configured_api_keys() -> List[str]:
    """Return all configured Gemini API keys in priority order.

    Reads from config.GEMINI_API_KEYS which is a dynamic-length list built
    from settings.json + environment variables. Duplicate keys are already
    stripped by config._build_gemini_key_list().
    """
    return list(getattr(config, "GEMINI_API_KEYS", []) or [])


def _is_rate_limit_error(error: Exception) -> bool:
    msg = str(error).lower()
    return any(m in msg for m in ["429", "rate limit", "too many requests",
                                   "quota", "resource_exhausted", "limit exceeded",
                                   "503", "server_error", "overloaded",
                                   "internal", "temporarily unavailable"])


def _is_model_unavailable_error(error: Exception) -> bool:
    """Detect errors caused by deprecated, removed, or invalid model names."""
    msg = str(error).lower()
    return any(m in msg for m in ["deprecated", "not found", "does not exist",
                                   "model not available", "unsupported model",
                                   "invalid model", "404"])


def _mask_key(key: str) -> str:
    return "****" if len(key) <= 8 else key[:4] + "..." + key[-4:]


def _pil_to_part(img: Image.Image) -> genai_types.Part:
    """Convert a PIL Image to a genai Part for inline image input.

    If the image is already JPEG-backed (e.g. from compress_for_api()),
    extract the raw bytes directly to avoid lossy double-compression.
    """
    # Check if image was opened from a JPEG BytesIO (set by compress_for_api)
    if getattr(img, "format", None) == "JPEG" and img.fp is not None:
        try:
            img.fp.seek(0)
            raw = img.fp.read()
            if raw:
                return genai_types.Part.from_bytes(data=raw, mime_type="image/jpeg")
        except Exception:
            pass  # Fall through to re-encode below

    buf = io.BytesIO()
    # Convert to RGB if needed (JPEG doesn't support RGBA/P)
    if img.mode in ("RGBA", "P", "LA"):
        img = img.convert("RGB")
    elif img.mode != "RGB":
        img = img.convert("RGB")
    img.save(buf, format="JPEG", quality=85, optimize=True)
    return genai_types.Part.from_bytes(data=buf.getvalue(), mime_type="image/jpeg")


def _build_contents(parts: list) -> list:
    """Convert a mixed list of strings and PIL Images into genai content parts."""
    content_parts = []
    for part in parts:
        if isinstance(part, str):
            content_parts.append(part)
        elif isinstance(part, Image.Image):
            content_parts.append(_pil_to_part(part))
        else:
            content_parts.append(part)
    return content_parts


# ---------------------------------------------------------------------------
# Core Gemini generation helper
# ---------------------------------------------------------------------------

def generate_content_with_fallback(content: Any):
    """Call Gemini with per-key retry + automatic fallback across all keys.

    Keys that are on cooldown (rate-limited or server-errored) are skipped
    automatically so subsequent questions don't waste time retrying exhausted
    keys.  If ALL keys are on cooldown the system falls back to the full list
    (graceful degradation — never completely blocks the user).
    """
    api_keys = _get_configured_api_keys()
    if not api_keys:
        raise ValueError("No Gemini API key configured. Open settings panel (Ctrl+Alt+M) to add your key.")

    # Convert mixed list to genai-compatible format
    if isinstance(content, list):
        content = _build_contents(content)

    # ── Smart key selection: skip keys on cooldown ──
    available_keys = gemini_key_tracker.get_available_keys(api_keys)
    if not available_keys:
        logger.warning(
            "⚠️ All Gemini keys are on cooldown — trying full key list as fallback."
        )
        available_keys = api_keys

    last_error = None

    for idx, api_key in enumerate(available_keys):
        # Use position in the *original* list for consistent labelling
        original_idx = api_keys.index(api_key) if api_key in api_keys else idx
        label = {0: "primary", 1: "secondary", 2: "tertiary"}.get(
            original_idx, f"key-{original_idx + 1}"
        )
        try:
            client = _get_client(api_key)

            # Capture client and content in local variables so the closure
            # inside _with_backoff always refers to THIS iteration's values.
            _client  = client
            _content = content

            def _call(_c=_client, _ct=_content):
                return _c.models.generate_content(
                    model=config.MODEL_NAME,
                    contents=_ct,
                )

            result = _with_backoff(_call, provider=f"Gemini {label} key")
            logger.info(
                f"✅ Answer generated by model [{config.MODEL_NAME}] "
                f"via {label} key [{_mask_key(api_key)}]"
            )
            return result

        except Exception as error:
            last_error = error
            # Record the failure so future calls skip this key
            gemini_key_tracker.mark_failed(api_key, error)

            is_last_key = idx == len(available_keys) - 1
            if not is_last_key:
                logger.warning(
                    f"⚠️ API key {original_idx + 1} ({label}) failed for model [{config.MODEL_NAME}]: "
                    f"{type(error).__name__}: {error}. Switching to next key..."
                )
                continue
            raise

    if last_error:
        raise last_error
    raise RuntimeError("Failed to generate content with Gemini")


def generate_content_with_model(content: Any, model: str | None = None):
    """Like generate_content_with_fallback but accepts an explicit *model* override.

    Used by the classification step to route to a cheaper/faster model
    (e.g. gemini-2.5-flash-lite) while the main answer generation continues
    to use the user's chosen MODEL_NAME (e.g. gemini-2.5-flash or 2.5-pro).

    If the requested model is deprecated/unavailable, automatically falls back
    to config.MODEL_NAME rather than exhausting all keys on a dead model.

    If *model* is None, falls through to config.MODEL_NAME (same as the
    regular fallback function).
    """
    resolved_model = model or config.MODEL_NAME
    api_keys = _get_configured_api_keys()
    if not api_keys:
        raise ValueError("No Gemini API key configured.")

    if isinstance(content, list):
        content = _build_contents(content)

    # ── Smart key selection: skip keys on cooldown ──
    available_keys = gemini_key_tracker.get_available_keys(api_keys)
    if not available_keys:
        logger.warning(
            "⚠️ All Gemini keys are on cooldown — trying full key list as fallback."
        )
        available_keys = api_keys

    last_error = None
    for idx, api_key in enumerate(available_keys):
        original_idx = api_keys.index(api_key) if api_key in api_keys else idx
        label = {0: "primary", 1: "secondary", 2: "tertiary"}.get(
            original_idx, f"key-{original_idx + 1}"
        )
        try:
            client = _get_client(api_key)
            _client, _content, _model = client, content, resolved_model

            def _call(_c=_client, _ct=_content, _m=_model):
                return _c.models.generate_content(model=_m, contents=_ct)

            result = _with_backoff(_call, provider=f"Gemini [{resolved_model}] {label} key")
            logger.info(
                f"✅ Answer generated by model [{resolved_model}] "
                f"via {label} key [{_mask_key(api_key)}]"
            )
            return result
        except Exception as error:
            last_error = error

            # If the MODEL itself is deprecated/gone, don't waste remaining
            # keys on a dead model — fall back to the user's main model.
            if _is_model_unavailable_error(error) and resolved_model != config.MODEL_NAME:
                logger.warning(
                    f"⚠️ Model [{resolved_model}] appears unavailable "
                    f"({type(error).__name__}: {error}). "
                    f"Falling back to [{config.MODEL_NAME}]..."
                )
                return generate_content_with_fallback(content)

            # Record the failure so future calls skip this key
            gemini_key_tracker.mark_failed(api_key, error)

            if idx < len(available_keys) - 1:
                logger.warning(
                    f"⚠️ Key {original_idx + 1} ({label}) failed for model [{resolved_model}]: "
                    f"{type(error).__name__}: {error}. Switching..."
                )
                continue
            raise

    if last_error:
        raise last_error
    raise RuntimeError("Failed to generate content with Gemini")


# ---------------------------------------------------------------------------
# Provider-agnostic public API
# ---------------------------------------------------------------------------

def solve_mcq_with_vision(
    question_image: bytes,
    options_images: list[bytes],
    context_image: bytes | None = None,
) -> int:
    """Solve a multiple-choice question from raw image bytes."""
    try:
        num_options  = len(options_images)
        question_img = Image.open(io.BytesIO(question_image))
        option_imgs  = [Image.open(io.BytesIO(b)) for b in options_images]

        context_note = "The first image provides context/passage for the question. " if context_image else ""
        prompt = (
            f"{context_note}"
            "Analyze the multiple-choice question carefully. "
            f"There are {num_options} answer options provided as separate images after the question. "
            f"Your task is to return ONLY the index number (1, 2, ..., {num_options}) "
            "corresponding to the correct option. "
            "Output format: Just the integer number. No text, no explanation, no punctuation."
        )

        parts: list = [prompt]
        if context_image:
            parts.append(Image.open(io.BytesIO(context_image)))
        parts.append(question_img)
        parts.extend(option_imgs)

        response    = generate_content_with_fallback(parts)
        answer_text = response.text.strip()
        logger.info(f"🤖 Gemini says: {answer_text}")

        index = int(answer_text)
        if 1 <= index <= num_options:
            return index
        raise GeminiError(f"Option index {index} out of range [1, {num_options}]")

    except GeminiError:
        raise
    except Exception as exc:
        raise GeminiError(f"solve_mcq_with_vision failed: {exc}") from exc


def generate_code_answer(prompt: str) -> str:
    """Generate a coding answer — Groq → OpenRouter → Gemini fallback."""
    logger.info(f"generate_code_answer: GROQ_API_KEY set={bool(config.GROQ_API_KEY)}, USE_GROQ_FOR_CODE={config.USE_GROQ_FOR_CODE}")

    if config.USE_GROQ_FOR_CODE and config.GROQ_API_KEY:
        try:
            logger.info("🔀 Routing code generation to Groq")
            result = _with_backoff(chat_with_groq, prompt, model=config.GROQ_DEFAULT_MODEL, provider="Groq")
            logger.info(f"✅ Answer generated by model [{config.GROQ_DEFAULT_MODEL}] (Groq)")
            return result
        except GroqError as exc:
            logger.warning(f"⚠️ Groq failed, falling through to OpenRouter: {exc}")

    if config.USE_OPENROUTER_FOR_CODE and config.OPENROUTER_API_KEY:
        try:
            logger.info("🔀 Routing code generation to OpenRouter")
            result = _with_backoff(generate_code_from_openrouter, prompt, provider="OpenRouter")
            logger.info(f"✅ Answer generated via OpenRouter")
            return result
        except OpenRouterError as exc:
            logger.warning(f"⚠️ OpenRouter failed, falling through to Gemini: {exc}")

    try:
        logger.info("🔀 Routing code generation to Gemini (final fallback)")
        response = generate_content_with_fallback([prompt])
        return response.text
    except Exception as exc:
        raise GeminiError(f"generate_code_answer failed: {exc}") from exc


def generate_theory_answer(prompt: str) -> str:
    """Generate a theory/essay answer — Groq → Gemini fallback.

    FIX #3 — previously a GroqError immediately raised AIProviderError,
    completely skipping the Gemini fallback. Now Groq failure logs a warning
    and falls through to Gemini, matching generate_code_answer's behaviour.
    """
    if config.USE_GROQ_FOR_EXPLANATION and config.GROQ_API_KEY:
        try:
            logger.info("🔀 Routing theory answer to Groq")
            result = _with_backoff(chat_with_groq, prompt, model=config.GROQ_DEFAULT_MODEL, provider="Groq")
            logger.info(f"✅ Answer generated by model [{config.GROQ_DEFAULT_MODEL}] (Groq)")
            return result
        except GroqError as exc:
            # FIX #3 — was: raise AIProviderError(...) — no Gemini fallback.
            # Now: log the warning and fall through so Gemini gets a chance.
            logger.warning(f"⚠️ Groq failed for theory answer, falling through to Gemini: {exc}")

    try:
        logger.info("🔀 Routing theory answer to Gemini (fallback)")
        response = generate_content_with_fallback([prompt])
        return response.text
    except Exception as exc:
        raise GeminiError(f"generate_theory_answer failed: {exc}") from exc


def explain_code(code: str, extra_context: str | None = None) -> str:
    """Return a natural-language explanation of code — Groq → Gemini fallback."""
    if config.USE_GROQ_FOR_EXPLANATION and config.GROQ_API_KEY:
        try:
            logger.info("🔀 Routing code explanation to Groq")
            result = _with_backoff(
                explain_code_with_groq, code, extra_context=extra_context, provider="Groq"
            )
            logger.info(f"✅ Answer generated by model [{config.GROQ_DEFAULT_MODEL}] (Groq)")
            return result
        except GroqError as exc:
            logger.warning(f"⚠️ Groq failed for code explanation, falling through to Gemini: {exc}")

    try:
        logger.info("🔀 Routing code explanation to Gemini (fallback)")
        full_prompt = f"Explain the following code:\n\n{code}"
        if extra_context:
            full_prompt += f"\n\nAdditional context:\n{extra_context}"
        response = generate_content_with_fallback([full_prompt])
        return response.text
    except Exception as exc:
        raise GeminiError(f"explain_code failed: {exc}") from exc


# ---------------------------------------------------------------------------
# Legacy path-based helpers (backward compatibility)
# ---------------------------------------------------------------------------

def get_correct_option_index(image_path: str, num_options: int = 4) -> Optional[int]:
    """Single-image mode — for standalone MCQs."""
    try:
        from utils import compress_for_api
        image  = compress_for_api(Image.open(image_path))
        prompt = (
            f"Analyze the multiple-choice question in the image carefully.\n"
            f"There are {num_options} options listed.\n"
            "Identify the correct answer based on your knowledge.\n"
            f"Return ONLY the index number (1–{num_options}). Just the integer, nothing else."
        )
        response    = generate_content_with_fallback([prompt, image])
        answer_text = response.text.strip()
        logger.info(f"🤖 Gemini says: {answer_text}")
        index = int(answer_text)
        if 1 <= index <= num_options:
            return index
        logger.error(f"❌ Invalid option index: {index}")
        return None
    except Exception as e:
        logger.error(f"❌ Gemini error: {e}")
        return None


def get_correct_option_index_with_context(
    context_image_path: str,
    question_image_path: str,
    num_options: int = 4,
) -> Optional[int]:
    """Two-image mode — for comprehension-based MCQs."""
    try:
        from utils import compress_for_api
        context_img  = compress_for_api(Image.open(context_image_path))
        question_img = compress_for_api(Image.open(question_image_path))
        prompt = (
            "Analyze the context (first image) and question (second image) carefully.\n"
            f"There are {num_options} options listed in the question image.\n"
            "Identify the correct answer based on the context.\n"
            f"Return ONLY the index number (1–{num_options}). Just the integer, nothing else."
        )
        response    = generate_content_with_fallback([prompt, context_img, question_img])
        answer_text = response.text.strip()
        logger.info(f"🤖 Gemini says: {answer_text}")
        index = int(answer_text)
        if 1 <= index <= num_options:
            return index
        logger.error(f"❌ Invalid option index: {index}")
        return None
    except Exception as e:
        logger.error(f"❌ Gemini error: {e}")
        return None