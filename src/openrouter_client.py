"""OpenRouter API client for coding / SQL tasks.

Usage::

    from openrouter_client import generate_code_from_openrouter
    answer = generate_code_from_openrouter("Write a binary search in Python")
"""
from __future__ import annotations

import requests
import config
from logger_setup import logger


class OpenRouterError(Exception):
    """Raised when the OpenRouter API call fails."""


# ---------------------------------------------------------------------------
# Persistent session — reuses TCP/TLS connection across calls
# ---------------------------------------------------------------------------

_openrouter_session: requests.Session | None = None


def _get_openrouter_session() -> requests.Session:
    """Return (creating if needed) the module-level persistent requests Session."""
    global _openrouter_session
    if _openrouter_session is None:
        _openrouter_session = requests.Session()
        _openrouter_session.headers.update({"Content-Type": "application/json"})
    return _openrouter_session


# ---------------------------------------------------------------------------
# Main client function
# ---------------------------------------------------------------------------

def generate_code_from_openrouter(
    prompt: str,
    model: str | None = None,
) -> str:
    """Call OpenRouter chat/completions for coding/SQL tasks and return the assistant text.

    Parameters
    ----------
    prompt:
        The user message / coding question to send.
    model:
        OpenRouter model identifier. Defaults to ``config.OPENROUTER_CODE_MODEL``
        (a free coding model).

    Returns
    -------
    str
        The assistant's reply text.

    Raises
    ------
    OpenRouterError
        On HTTP error, connection failure, or malformed JSON response.
    """
    api_key = config.OPENROUTER_API_KEY
    if not api_key:
        raise OpenRouterError("OPENROUTER_API_KEY is not set")

    resolved_model = model or config.OPENROUTER_CODE_MODEL
    url = config.OPENROUTER_BASE_URL.rstrip("/") + "/chat/completions"

    session = _get_openrouter_session()
    session.headers["Authorization"] = f"Bearer {api_key}"

    payload = {
        "model": resolved_model,
        "messages": [{"role": "user", "content": prompt}],
    }

    masked = api_key[:4] + "..." + api_key[-4:] if len(api_key) > 8 else "****"
    logger.info(f"🌐 Calling OpenRouter model={resolved_model!r} key=[{masked}]")
    try:
        response = session.post(url, json=payload, timeout=60)
    except requests.RequestException as exc:
        raise OpenRouterError(f"Request failed: {exc}") from exc

    if not response.ok:
        raise OpenRouterError(
            f"OpenRouter returned HTTP {response.status_code}: {response.text[:300]}"
        )

    try:
        data = response.json()
        text: str = data["choices"][0]["message"]["content"]
    except (ValueError, KeyError, IndexError) as exc:
        raise OpenRouterError(f"Malformed JSON response: {exc}\nRaw: {response.text[:300]}") from exc

    logger.info(f"✅ OpenRouter response received via key=[{masked}]")
    return text