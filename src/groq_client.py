"""Groq API client for text-only reasoning tasks (explanations, theory, step-by-step).

Usage::

    from groq_client import explain_code_with_groq, chat_with_groq
    text = explain_code_with_groq("def foo(): pass")
"""
from __future__ import annotations

import requests
import config
from logger_setup import logger


class GroqError(Exception):
    """Raised when a Groq API call fails."""


# ---------------------------------------------------------------------------
# Persistent session — reuses TCP/TLS connection across calls
# ---------------------------------------------------------------------------

_groq_session: requests.Session | None = None


def _get_groq_session() -> requests.Session:
    """Return (creating if needed) the module-level persistent requests Session."""
    global _groq_session
    if _groq_session is None:
        _groq_session = requests.Session()
        _groq_session.headers.update({"Content-Type": "application/json"})
    return _groq_session


# ---------------------------------------------------------------------------
# Low-level chat wrapper
# ---------------------------------------------------------------------------

def chat_with_groq(prompt: str, model: str) -> str:
    """Generic wrapper for Groq chat/completions.

    Parameters
    ----------
    prompt:
        User message content.
    model:
        Groq model identifier (e.g. ``"llama-3.3-70b-versatile"``).

    Returns
    -------
    str
        The assistant's reply text.

    Raises
    ------
    GroqError
        On missing API key, HTTP error, connection failure, or malformed JSON.
    """
    api_key = config.GROQ_API_KEY
    if not api_key:
        raise GroqError("GROQ_API_KEY is not set")

    url = config.GROQ_BASE_URL.rstrip("/") + "/chat/completions"

    session = _get_groq_session()
    session.headers["Authorization"] = f"Bearer {api_key}"

    payload = {
        "model": model,
        "messages": [
            {
                "role": "system",
                "content": (
                    "You are an expert software engineer and computer science tutor. "
                    "Provide clear, precise, and well-structured answers."
                ),
            },
            {"role": "user", "content": prompt},
        ],
    }

    masked = api_key[:4] + "..." + api_key[-4:] if len(api_key) > 8 else "****"
    logger.info(f"🌐 Calling Groq model={model!r} key=[{masked}]")
    try:
        response = session.post(url, json=payload, timeout=60)
    except requests.RequestException as exc:
        raise GroqError(f"Request failed: {exc}") from exc

    if not response.ok:
        raise GroqError(
            f"Groq returned HTTP {response.status_code}: {response.text[:300]}"
        )

    try:
        data = response.json()
        text: str = data["choices"][0]["message"]["content"]
    except (ValueError, KeyError, IndexError) as exc:
        raise GroqError(
            f"Malformed JSON response: {exc}\nRaw: {response.text[:300]}"
        ) from exc

    logger.info(f"✅ Groq response received via key=[{masked}]")
    return text


# ---------------------------------------------------------------------------
# High-level explanation helper
# ---------------------------------------------------------------------------

def explain_code_with_groq(
    code: str,
    extra_context: str | None = None,
    model: str | None = None,
) -> str:
    """Ask Groq to produce a structured explanation of *code*.

    The explanation includes:
    - High-level summary
    - Step-by-step walkthrough
    - Time and space complexity analysis

    Parameters
    ----------
    code:
        Source code to explain.
    extra_context:
        Optional additional instructions or surrounding context.
    model:
        Groq model to use; defaults to ``config.GROQ_DEFAULT_MODEL``.

    Returns
    -------
    str
        Explanation text from Groq.

    Raises
    ------
    GroqError
        On any provider error.
    """
    resolved_model = model or config.GROQ_DEFAULT_MODEL

    context_section = f"\n\nAdditional context:\n{extra_context}" if extra_context else ""

    full_prompt = (
        "Analyze the following code and provide a structured explanation covering:\n"
        "1. **High-level summary** – What does this code do overall?\n"
        "2. **Step-by-step explanation** – Walk through the logic line by line or block by block.\n"
        "3. **Time complexity** – State and justify Big-O time complexity.\n"
        "4. **Space complexity** – State and justify Big-O space complexity.\n\n"
        f"CODE:\n```\n{code}\n```"
        f"{context_section}"
    )

    return chat_with_groq(full_prompt, model=resolved_model)