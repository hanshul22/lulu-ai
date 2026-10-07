"""config.py

Key resolution order (each setting tries the next if empty):
  1. settings.json (set via the settings panel — primary source)
  2. Environment variable / .env file (optional, for power users)

Fresh install works with zero files — user opens settings panel
(Ctrl+Alt+M) and enters their keys once. Done.
"""
import os
import sys

# Load .env as optional fallback — won't fail if file doesn't exist
try:
    from dotenv import load_dotenv
    from settings_manager import APP_DATA_DIR as _APP_DATA_DIR
    for _env_path in [
        os.path.join(_APP_DATA_DIR, ".env"),
        os.path.join(os.path.dirname(__file__), "..", ".env"),
        os.path.join(os.getcwd(), ".env"),
    ]:
        if os.path.exists(_env_path):
            load_dotenv(dotenv_path=_env_path)
            break
except Exception:
    pass

from settings_manager import current_settings, APP_DATA_DIR

# ---------------------------------------------------------------------------
# Directories — all inside app-data
# ---------------------------------------------------------------------------

SCREENSHOT_DIR = os.path.join(APP_DATA_DIR, "screenshots")
os.makedirs(SCREENSHOT_DIR, exist_ok=True)

SUBJECTIVE_SCREENSHOT_DIR = os.path.join(SCREENSHOT_DIR, "subjective")
os.makedirs(SUBJECTIVE_SCREENSHOT_DIR, exist_ok=True)

QUESTION_IMAGE_PATH = os.path.join(SCREENSHOT_DIR, "question.png")
CONTEXT_IMAGE_PATH  = os.path.join(SCREENSHOT_DIR, "context.png")
QUESTION_IMAGE_NAME = "question.png"
CONTEXT_IMAGE_NAME  = "context.png"
NOTES_FILE          = os.path.join(APP_DATA_DIR, "hidden_notes.txt")

# ---------------------------------------------------------------------------
# Gemini — keyring first, then settings.json, then .env fallback
# ---------------------------------------------------------------------------

def _clean_key(raw: str) -> str:
    """Strip whitespace and any accidental surrounding quotes from an API key.

    The settings panel has historically saved keys as '"AIzaSy..."' (with
    literal quote characters) when the user pastes a key that already had
    quotes around it. This helper normalises them at read-time so the key
    sent to Google is always the bare token.
    """
    return raw.strip().strip('"\'')


def _build_gemini_key_list() -> list[str]:
    """Return all configured Gemini API keys in priority order.

    Sources (in order):
    1. OS keyring  →  secure credential store (preferred)
    2. settings.json  →  gemini_api_keys  (fallback / pre-migration)
    3. Environment variables (.env) as last resort

    Duplicate keys are silently dropped so the same key is never tried twice.
    """
    keys: list[str] = []
    seen: set[str] = set()

    # 1. OS keyring (secure storage — preferred source)
    try:
        from secure_keys import load_gemini_keys
        for k in load_gemini_keys():
            cleaned = _clean_key(k)
            if cleaned and cleaned not in seen:
                keys.append(cleaned)
                seen.add(cleaned)
    except ImportError:
        pass  # secure_keys / keyring not installed

    # 2. settings.json — dynamic list (fallback before migration)
    if not keys:
        for raw in current_settings.get("gemini_api_keys", []):
            cleaned = _clean_key(raw) if raw else ""
            if cleaned and cleaned not in seen:
                keys.append(cleaned)
                seen.add(cleaned)

        # Legacy fixed fields (in case migration hasn't run yet)
        for field in ("api_key", "api_key_secondary", "api_key_tertiary"):
            raw = current_settings.get(field, "")
            cleaned = _clean_key(raw) if raw else ""
            if cleaned and cleaned not in seen:
                keys.append(cleaned)
                seen.add(cleaned)

    # 3. Environment variable fallbacks
    if not keys:
        for env_var in (
            "GEMINI_API_KEY_PRIMARY",
            "GEMINI_API_KEY",
            "GEMINI_API_KEY_SECONDARY",
            "GEMINI_API_KEY_TERTIARY",
        ):
            raw = os.environ.get(env_var, "")
            cleaned = _clean_key(raw) if raw else ""
            if cleaned and cleaned not in seen:
                keys.append(cleaned)
                seen.add(cleaned)

    return keys


# The canonical list of Gemini API keys — used by ai_core.py
GEMINI_API_KEYS: list[str] = _build_gemini_key_list()

# Backward-compatible aliases so old code that references API_KEY still works
API_KEY           = GEMINI_API_KEYS[0] if len(GEMINI_API_KEYS) > 0 else ""
API_KEY_SECONDARY = GEMINI_API_KEYS[1] if len(GEMINI_API_KEYS) > 1 else ""
API_KEY_TERTIARY  = GEMINI_API_KEYS[2] if len(GEMINI_API_KEYS) > 2 else ""

MODEL_NAME = current_settings.get("model_name", "gemini-2.5-flash")

# Cheaper / faster model used ONLY for the classification step (sql vs dsa
# vs non-coding).  Classification returns a single word so the premium model
# is overkill.  This saves ~40-60% of tokens on that call.
# NOTE: gemini-2.0-flash is deprecated (shutdown June 2026).
#       gemini-2.5-flash-lite is the cheapest non-deprecated alternative.
CLASSIFICATION_MODEL: str = current_settings.get(
    "classification_model", "gemini-2.5-flash-lite"
)

# ---------------------------------------------------------------------------
# Groq — keyring first, then settings panel, then env fallback
# ---------------------------------------------------------------------------

def _load_groq_key() -> str:
    """Load Groq API key: keyring → settings.json → env."""
    try:
        from secure_keys import load_key, GROQ_KEY_ENTRY
        key = load_key(GROQ_KEY_ENTRY).strip()
        if key:
            return key
    except ImportError:
        pass
    return (
        current_settings.get("groq_api_key", "").strip()
        or os.environ.get("GROQ_API_KEY", "").strip()
    )

GROQ_API_KEY: str = _load_groq_key()
GROQ_BASE_URL:             str  = "https://api.groq.com/openai/v1"
USE_GROQ_FOR_EXPLANATION:  bool = False
USE_GROQ_FOR_CODE:         bool = False
GROQ_DEFAULT_MODEL:        str  = "llama-3.3-70b-versatile"
GROQ_EXPLANATION_FALLBACK: str  = "deepseek-r1-distill-llama-70b"

# ---------------------------------------------------------------------------
# OpenRouter — keyring first, then settings panel, then env fallback
# ---------------------------------------------------------------------------

def _load_openrouter_key() -> str:
    """Load OpenRouter API key: keyring → settings.json → env."""
    try:
        from secure_keys import load_key, OPENROUTER_KEY_ENTRY
        key = load_key(OPENROUTER_KEY_ENTRY).strip()
        if key:
            return key
    except ImportError:
        pass
    return (
        current_settings.get("openrouter_api_key", "").strip()
        or os.environ.get("OPENROUTER_API_KEY", "").strip()
    )

OPENROUTER_API_KEY: str = _load_openrouter_key()
OPENROUTER_BASE_URL:     str  = "https://openrouter.ai/api/v1"
USE_OPENROUTER_FOR_CODE: bool = False
OPENROUTER_CODE_MODEL:   str  = os.environ.get(
    "OPENROUTER_CODE_MODEL", "meta-llama/llama-3.3-70b-instruct:free"
)
OPENROUTER_CODE_FALLBACKS: list[str] = [
    "mistralai/devstral-2512:free",
    "xiaomi/mimo-v2-flash-309b:free",
]

# ---------------------------------------------------------------------------
# Hotkeys
# ---------------------------------------------------------------------------

CAPTURE_CONTEXT_HOTKEY       = current_settings["hotkeys"]["capture_context"]
CAPTURE_QUESTION_HOTKEY      = current_settings["hotkeys"]["capture_question"]
CLEAR_CONTEXT_HOTKEY         = current_settings["hotkeys"]["clear_context"]
EXIT_HOTKEY                  = current_settings["hotkeys"]["exit"]
CAPTURE_SUBJECTIVE_HOTKEY    = current_settings["hotkeys"]["capture_subjective"]
GENERATE_RESPONSE_HOTKEY     = current_settings["hotkeys"]["generate_response"]
TYPE_RESPONSE_HOTKEY         = current_settings["hotkeys"]["type_response"]
RESUME_TYPING_HOTKEY         = current_settings["hotkeys"]["resume_typing"]
RETRY_SUBJECTIVE_HOTKEY      = current_settings["hotkeys"]["retry_subjective"]
TOGGLE_NOTES_HOTKEY          = current_settings["hotkeys"]["toggle_notes"]
TOGGLE_EXPLANATION_HOTKEY    = current_settings["hotkeys"]["toggle_explanation"]
CONTROL_PANEL_HOTKEY         = current_settings["hotkeys"]["control_panel"]
STEP_BY_STEP_SOLUTION_HOTKEY = current_settings["hotkeys"]["step_by_step_solution"]
EXPLAIN_CODE_HOTKEY          = current_settings["hotkeys"]["explain_code"]
MOVE_NOTES_UP_HOTKEY    = current_settings["hotkeys"].get("move_notes_up",    "<ctrl>+<alt>+<up>")
MOVE_NOTES_DOWN_HOTKEY  = current_settings["hotkeys"].get("move_notes_down",  "<ctrl>+<alt>+<down>")
MOVE_NOTES_LEFT_HOTKEY  = current_settings["hotkeys"].get("move_notes_left",  "<ctrl>+<alt>+<left>")
MOVE_NOTES_RIGHT_HOTKEY = current_settings["hotkeys"].get("move_notes_right", "<ctrl>+<alt>+<right>")

# ---------------------------------------------------------------------------
# Typing
# ---------------------------------------------------------------------------

TYPING_DELAY_MIN = current_settings.get("typing", {}).get("min_delay", 0.03)
TYPING_DELAY_MAX = current_settings.get("typing", {}).get("max_delay", 0.08)