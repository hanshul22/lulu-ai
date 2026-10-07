"""key_manager.py — Smart Gemini API key state tracking with cooldowns.

Tracks which Gemini API keys are temporarily unavailable (rate-limited or
experiencing server errors) so the system skips them instead of wasting
time retrying exhausted keys on every request.

Cooldown durations are error-aware:
  • Rate-limit / quota errors  →  24 hours  (daily quota reset)
  • Server / transient errors  →   5 minutes (brief hiccup)

Usage (inside ai_core.py)::

    from key_manager import gemini_key_tracker

    available = gemini_key_tracker.get_available_keys(all_keys)
    ...
    except Exception as error:
        gemini_key_tracker.mark_failed(api_key, error)
"""
from __future__ import annotations

import threading
import time
from logger_setup import logger

# ---------------------------------------------------------------------------
# Cooldown durations (seconds)
# ---------------------------------------------------------------------------

RATE_LIMIT_COOLDOWN:  float = 24 * 60 * 60   # 24 hours
SERVER_ERROR_COOLDOWN: float = 5 * 60          # 5 minutes


# ---------------------------------------------------------------------------
# Key state tracker
# ---------------------------------------------------------------------------

def _mask_key(key: str) -> str:
    """Mask an API key for safe logging."""
    return "****" if len(key) <= 8 else key[:4] + "..." + key[-4:]


class KeyStateTracker:
    """Thread-safe tracker that records which API keys are on cooldown.

    After ``mark_failed(key, error)`` is called the key will be skipped by
    ``get_available_keys()`` until its cooldown expires.  Expiry is checked
    lazily — no background thread is needed.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        # {api_key: (failed_at_timestamp, cooldown_seconds)}
        self._failed_keys: dict[str, tuple[float, float]] = {}

    # ----- public API -----

    def mark_failed(self, key: str, error: Exception) -> None:
        """Record *key* as failed with a cooldown determined by *error* type.

        If the error is not cooldown-worthy (e.g. a transient network
        timeout), this is a no-op — the key stays in rotation.
        """
        cooldown = self._classify_cooldown(error)
        if cooldown is None:
            return                        # not worth tracking

        with self._lock:
            self._failed_keys[key] = (time.time(), cooldown)

        if cooldown >= RATE_LIMIT_COOLDOWN:
            human = f"{cooldown / 3600:.0f}h"
        else:
            human = f"{cooldown / 60:.0f}min"

        logger.warning(
            f"🔑 Key [{_mask_key(key)}] marked unavailable for {human} "
            f"— {type(error).__name__}: {str(error)[:120]}"
        )

    def is_available(self, key: str) -> bool:
        """Return *True* if *key* is NOT on cooldown (or cooldown expired)."""
        with self._lock:
            if key not in self._failed_keys:
                return True
            failed_at, cooldown = self._failed_keys[key]
            if time.time() >= failed_at + cooldown:
                del self._failed_keys[key]
                logger.info(
                    f"🔑 Key [{_mask_key(key)}] cooldown expired — back in rotation."
                )
                return True
            return False

    def get_available_keys(self, all_keys: list[str]) -> list[str]:
        """Return only those keys from *all_keys* not currently on cooldown."""
        return [k for k in all_keys if self.is_available(k)]

    def reset(self, key: str | None = None) -> None:
        """Clear cooldown for one key, or all keys if *key* is ``None``."""
        with self._lock:
            if key is None:
                self._failed_keys.clear()
                logger.info("🔑 All key cooldowns cleared.")
            elif key in self._failed_keys:
                del self._failed_keys[key]
                logger.info(f"🔑 Key [{_mask_key(key)}] cooldown cleared.")

    def status_summary(self) -> dict[str, str]:
        """Return a snapshot ``{masked_key: status_string}`` for diagnostics."""
        with self._lock:
            now = time.time()
            summary: dict[str, str] = {}
            for key, (failed_at, cooldown) in self._failed_keys.items():
                remaining = (failed_at + cooldown) - now
                if remaining > 0:
                    if remaining >= 3600:
                        human = f"{remaining / 3600:.1f}h remaining"
                    else:
                        human = f"{remaining / 60:.0f}min remaining"
                    summary[_mask_key(key)] = f"unavailable ({human})"
                else:
                    summary[_mask_key(key)] = "cooldown expired (will clear on next use)"
            return summary

    # ----- internal -----

    @staticmethod
    def _classify_cooldown(error: Exception) -> float | None:
        """Determine cooldown duration from *error*.  ``None`` = don't track."""
        msg = str(error).lower()

        # Invalid / expired / revoked API key → long cooldown (24 h)
        # These keys won't magically fix themselves; cooldown is cleared
        # automatically when the user saves new keys (clear_client_cache).
        if any(s in msg for s in (
            "api_key_invalid", "api key expired", "invalid api key",
            "api key not valid", "invalid_argument",
            "permission_denied", "forbidden", "401", "403",
        )):
            return RATE_LIMIT_COOLDOWN

        # Rate-limit / quota exhaustion → long cooldown (24 h)
        if any(s in msg for s in (
            "429", "rate limit", "too many requests",
            "quota", "resource_exhausted", "limit exceeded",
        )):
            return RATE_LIMIT_COOLDOWN

        # Transient server errors → short cooldown (5 min)
        if any(s in msg for s in (
            "503", "server_error", "overloaded",
            "temporarily unavailable",
        )):
            return SERVER_ERROR_COOLDOWN

        # Everything else (network timeout, malformed JSON, auth error …)
        # → not cooldown-worthy; the key stays available.
        return None


# ---------------------------------------------------------------------------
# Module-level singleton used by ai_core
# ---------------------------------------------------------------------------

gemini_key_tracker = KeyStateTracker()