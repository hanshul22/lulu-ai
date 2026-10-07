"""secure_keys.py — Secure API key storage using OS keyring.

Stores API keys in the OS native credential manager:
  • Windows  →  Credential Manager
  • macOS    →  Keychain
  • Linux    →  Secret Service (GNOME Keyring / KWallet)

Falls back gracefully if keyring is unavailable — callers should check
``is_available()`` and decide whether to use plain-text settings.json.

Usage::

    from secure_keys import (
        is_available, store_gemini_keys, load_gemini_keys,
        store_key, load_key,
    )

    if is_available():
        store_gemini_keys(["AIza...", "AIza..."])
        groq = load_key("groq_api_key")
"""
from __future__ import annotations

import json

try:
    from logger_setup import logger
except ImportError:
    import logging
    logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

SERVICE_NAME = "LuluApp"

# Entry names inside the keyring
GEMINI_KEYS_ENTRY    = "gemini_api_keys"
GROQ_KEY_ENTRY       = "groq_api_key"
OPENROUTER_KEY_ENTRY = "openrouter_api_key"

# ---------------------------------------------------------------------------
# Keyring availability check
# ---------------------------------------------------------------------------

_keyring_available: bool = False

try:
    import keyring
    import keyring.errors

    # Verify the backend is actually functional — on some headless Linux
    # boxes keyring imports fine but has no usable backend.
    _backend = keyring.get_keyring()
    # The "fail" backend (keyring.backends.fail) means no real backend exists.
    _backend_name = type(_backend).__name__.lower()
    if "fail" in _backend_name or "null" in _backend_name:
        raise RuntimeError("No usable keyring backend")

    _keyring_available = True
    logger.info(f"🔐 OS keyring available — using {type(_backend).__name__} for API key storage.")

except Exception as _init_err:
    _keyring_available = False
    logger.warning(
        f"⚠️ OS keyring not available ({_init_err}). "
        "API keys will be stored in plain-text settings.json."
    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def is_available() -> bool:
    """Return True if the OS keyring backend is functional."""
    return _keyring_available


# ── Gemini keys (stored as JSON list) ─────────────────────────────────────

def store_gemini_keys(keys: list[str]) -> bool:
    """Store the list of Gemini API keys in the OS keyring.

    Returns True on success, False on failure.
    """
    if not _keyring_available:
        return False
    try:
        keyring.set_password(SERVICE_NAME, GEMINI_KEYS_ENTRY, json.dumps(keys))
        logger.info(f"🔐 Stored {len(keys)} Gemini key(s) in OS keyring.")
        return True
    except Exception as exc:
        logger.error(f"Failed to store Gemini keys in keyring: {exc}")
        return False


def load_gemini_keys() -> list[str]:
    """Load the list of Gemini API keys from the OS keyring.

    Returns an empty list if keyring is unavailable or no keys are stored.
    """
    if not _keyring_available:
        return []
    try:
        raw = keyring.get_password(SERVICE_NAME, GEMINI_KEYS_ENTRY)
        if raw:
            keys = json.loads(raw)
            if isinstance(keys, list):
                return [k for k in keys if isinstance(k, str) and k.strip()]
    except Exception as exc:
        logger.error(f"Failed to load Gemini keys from keyring: {exc}")
    return []


# ── Single-value keys (Groq, OpenRouter, etc.) ───────────────────────────

def store_key(entry_name: str, value: str) -> bool:
    """Store a single API key string in the OS keyring.

    If *value* is empty, the existing entry is deleted.
    Returns True on success, False on failure.
    """
    if not _keyring_available:
        return False
    try:
        if value:
            keyring.set_password(SERVICE_NAME, entry_name, value)
        else:
            # Remove entry when key is cleared
            try:
                keyring.delete_password(SERVICE_NAME, entry_name)
            except keyring.errors.PasswordDeleteError:
                pass  # Entry didn't exist — that's fine
        return True
    except Exception as exc:
        logger.error(f"Failed to store '{entry_name}' in keyring: {exc}")
        return False


def load_key(entry_name: str) -> str:
    """Load a single API key string from the OS keyring.

    Returns an empty string if keyring is unavailable or key doesn't exist.
    """
    if not _keyring_available:
        return ""
    try:
        return keyring.get_password(SERVICE_NAME, entry_name) or ""
    except Exception as exc:
        logger.error(f"Failed to load '{entry_name}' from keyring: {exc}")
        return ""


# ── Cleanup ───────────────────────────────────────────────────────────────

def delete_all_keys() -> None:
    """Remove all LuluApp entries from the OS keyring."""
    if not _keyring_available:
        return
    for entry in (GEMINI_KEYS_ENTRY, GROQ_KEY_ENTRY, OPENROUTER_KEY_ENTRY):
        try:
            keyring.delete_password(SERVICE_NAME, entry)
        except Exception:
            pass
    logger.info("🔐 All API keys removed from OS keyring.")