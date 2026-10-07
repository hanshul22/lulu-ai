"""settings_manager.py

Settings are stored in LOCALAPPDATA/LuluApp/settings.json (Windows) or
~/.config/LuluApp/settings.json (macOS/Linux).

This means the app works from ANY directory — no project folder required.
First-time users just run `lulu start`, the settings panel opens automatically,
they enter their API keys once, and lulu start works from anywhere forever.
"""
import copy
import json
import os
import sys
import tempfile
import shutil


# ---------------------------------------------------------------------------
# App data directory — platform aware, always the same location
# ---------------------------------------------------------------------------

def _get_app_data_dir() -> str:
    if sys.platform == "win32":
        base = os.getenv("LOCALAPPDATA", os.path.expanduser("~"))
    elif sys.platform == "darwin":
        base = os.path.expanduser("~/Library/Application Support")
    else:
        base = os.path.expanduser("~/.config")
    app_dir = os.path.join(base, "LuluApp")
    os.makedirs(app_dir, exist_ok=True)
    return app_dir


APP_DATA_DIR         = _get_app_data_dir()
SETTINGS_FILE        = os.path.join(APP_DATA_DIR, "settings.json")
SETTINGS_BACKUP_FILE = os.path.join(APP_DATA_DIR, "settings.backup.json")

# BASE_DIR for screenshots and other data files — all go into app-data
# so nothing is written to the project/install folder
if getattr(sys, "frozen", False):
    BASE_DIR = os.path.dirname(sys.executable)
else:
    BASE_DIR = APP_DATA_DIR


# ---------------------------------------------------------------------------
# Default settings — API keys are empty, filled via settings panel
# ---------------------------------------------------------------------------

DEFAULT_SETTINGS = {
    # Gemini API keys — dynamic list, user can add as many as they want.
    # Each key is tried in order; on failure the next key is used automatically.
    # Backward-compat: old fixed fields (api_key, api_key_secondary,
    # api_key_tertiary) are migrated into this list on first load.
    "gemini_api_keys":   [],    # ["key1", "key2", ...] — dynamic length
    "groq_api_key":      "",    # Groq
    "openrouter_api_key": "",   # OpenRouter
    "model_name": "gemini-2.5-flash",
    "hotkeys": {
        "capture_context":       "<ctrl>+<alt>+c",
        "capture_question":      "<ctrl>+<alt>+p",
        "clear_context":         "<ctrl>+<alt>+r",
        "exit":                  "<ctrl>+<alt>+e",
        "capture_subjective":    "<ctrl>+<alt>+s",
        "generate_response":     "<ctrl>+<alt>+g",
        "type_response":         "<ctrl>+<alt>+t",
        "resume_typing":         "<ctrl>+<alt>+z",
        "retry_subjective":      "<ctrl>+<alt>+k",
        "toggle_notes":          "<ctrl>+<alt>+n",
        "toggle_explanation":    "<ctrl>+<alt>+a",
        "explain_code":          "<ctrl>+<alt>+j",
        "control_panel":         "<ctrl>+<alt>+m",
        "step_by_step_solution": "<ctrl>+<alt>+o",
        "move_notes_up":         "<ctrl>+<alt>+<up>",
        "move_notes_down":       "<ctrl>+<alt>+<down>",
        "move_notes_left":       "<ctrl>+<alt>+<left>",
        "move_notes_right":      "<ctrl>+<alt>+<right>",
    },
    "features": {
        "notes_enabled":       True,
        "explanation_enabled": True,
    },
    "typing": {
        "min_delay": 0.03,
        "max_delay": 0.08,
    },
    "window_size": {
        "notes_width":        400,
        "notes_height":       300,
        "explanation_width":  500,
        "explanation_height": 400,
    },
    "first_run": True,
}


# ---------------------------------------------------------------------------
# Load
# ---------------------------------------------------------------------------

def load_settings() -> dict:
    """Load settings from app-data, falling back to backup then defaults."""
    settings = _try_load_file(SETTINGS_FILE)

    if settings is None and os.path.exists(SETTINGS_BACKUP_FILE):
        print("⚠️ settings.json unreadable — attempting backup restore...")
        settings = _try_load_file(SETTINGS_BACKUP_FILE)
        if settings is not None:
            print("✅ Settings restored from backup.")
            save_settings(settings)

    if settings is None:
        settings = copy.deepcopy(DEFAULT_SETTINGS)
        save_settings(settings)
        return settings

    # Deep merge so new keys added in updates always exist even in older
    # settings.json files that predate the new fields.
    merged = copy.deepcopy(DEFAULT_SETTINGS)
    for key, value in settings.items():
        if isinstance(value, dict) and key in merged and isinstance(merged[key], dict):
            merged[key].update(value)
        else:
            merged[key] = value

    # ── Migration: old fixed keys → dynamic gemini_api_keys list ──────────
    # If the settings file still has the old api_key / api_key_secondary /
    # api_key_tertiary fields but no gemini_api_keys list (or an empty one),
    # migrate them into the new list automatically.
    merged = _migrate_legacy_keys(merged)

    return merged


def _clean_key(raw: str) -> str:
    """Strip whitespace and any accidental surrounding quotes from a key."""
    return raw.strip().strip('"\'')


def _migrate_legacy_keys(settings: dict) -> dict:
    """Move old fixed api_key / api_key_secondary / api_key_tertiary into
    the new gemini_api_keys list.  Only runs when the list is empty AND at
    least one legacy field is populated.  After migration the legacy fields
    are removed so they don't conflict going forward."""
    current_list = settings.get("gemini_api_keys", [])
    if current_list:
        # Already migrated — nothing to do
        return settings

    legacy_fields = ["api_key", "api_key_secondary", "api_key_tertiary"]
    migrated: list[str] = []
    for field in legacy_fields:
        raw = settings.get(field, "")
        cleaned = _clean_key(raw) if raw else ""
        if cleaned and cleaned not in migrated:
            migrated.append(cleaned)

    if migrated:
        settings["gemini_api_keys"] = migrated
        # Remove legacy fields to keep settings.json clean
        for field in legacy_fields:
            settings.pop(field, None)
        print(f"✅ Migrated {len(migrated)} Gemini key(s) to new dynamic list.")

    return settings


def _try_load_file(path: str) -> dict | None:
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else None
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Save — atomic write, crash-safe
# ---------------------------------------------------------------------------

def save_settings(settings: dict) -> None:
    try:
        dir_name = os.path.dirname(SETTINGS_FILE) or "."
        fd, tmp_path = tempfile.mkstemp(dir=dir_name, suffix=".tmp", prefix="settings_")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(settings, f, indent=4)
        except Exception:
            os.unlink(tmp_path)
            raise
        if os.path.exists(SETTINGS_FILE) and _try_load_file(SETTINGS_FILE) is not None:
            shutil.copy2(SETTINGS_FILE, SETTINGS_BACKUP_FILE)
        shutil.move(tmp_path, SETTINGS_FILE)
    except Exception as e:
        print(f"Error saving settings: {e}")


# ---------------------------------------------------------------------------
# Global instance + helpers
# ---------------------------------------------------------------------------

current_settings = load_settings()


# ---------------------------------------------------------------------------
# Keyring migration — move plain-text API keys to OS credential store
# ---------------------------------------------------------------------------

def _migrate_keys_to_keyring() -> None:
    """One-time migration: if API keys are in settings.json AND the OS
    keyring is available, move them into the keyring and strip them from
    the JSON file.  Subsequent loads will read from the keyring instead.
    """
    try:
        from secure_keys import (
            is_available, store_gemini_keys, store_key, load_gemini_keys,
            GROQ_KEY_ENTRY, OPENROUTER_KEY_ENTRY,
        )
    except ImportError:
        return   # secure_keys or keyring not installed — skip silently

    if not is_available():
        return

    # Already migrated? Check if keyring already has Gemini keys.
    if load_gemini_keys():
        # Keys are already in keyring. Make sure settings.json is clean.
        _strip_keys_from_settings()
        return

    # Collect plain-text Gemini keys from settings
    gemini_keys: list[str] = []
    seen: set[str] = set()

    for raw in current_settings.get("gemini_api_keys", []):
        cleaned = _clean_key(raw) if raw else ""
        if cleaned and cleaned not in seen:
            gemini_keys.append(cleaned)
            seen.add(cleaned)

    for field in ("api_key", "api_key_secondary", "api_key_tertiary"):
        raw = current_settings.get(field, "")
        cleaned = _clean_key(raw) if raw else ""
        if cleaned and cleaned not in seen:
            gemini_keys.append(cleaned)
            seen.add(cleaned)

    groq_key = _clean_key(current_settings.get("groq_api_key", "") or "")
    openrouter_key = _clean_key(current_settings.get("openrouter_api_key", "") or "")

    if not gemini_keys and not groq_key and not openrouter_key:
        return   # Nothing to migrate

    # Store in keyring
    migrated = False
    if gemini_keys and store_gemini_keys(gemini_keys):
        migrated = True
    if groq_key and store_key(GROQ_KEY_ENTRY, groq_key):
        migrated = True
    if openrouter_key and store_key(OPENROUTER_KEY_ENTRY, openrouter_key):
        migrated = True

    if migrated:
        _strip_keys_from_settings()
        print(f"🔐 Migrated API keys to OS keyring (Credential Manager).")
        print(f"   Keys have been removed from settings.json for security.")


def _strip_keys_from_settings() -> None:
    """Remove all plain-text API key values from settings.json."""
    changed = False

    # Clear Gemini key list
    if current_settings.get("gemini_api_keys"):
        current_settings["gemini_api_keys"] = []
        changed = True

    # Clear legacy fields
    for field in ("api_key", "api_key_secondary", "api_key_tertiary"):
        if current_settings.get(field):
            current_settings.pop(field, None)
            changed = True

    # Clear provider keys
    for field in ("groq_api_key", "openrouter_api_key"):
        if current_settings.get(field):
            current_settings[field] = ""
            changed = True

    if changed:
        save_settings(current_settings)


# Run migration at startup
_migrate_keys_to_keyring()


def get_setting(key, default=None):
    return current_settings.get(key, default)


def update_setting(key, value):
    current_settings[key] = value
    save_settings(current_settings)


def is_first_run() -> bool:
    """True if no Gemini API key has been set yet."""
    keys = current_settings.get("gemini_api_keys", [])
    return not any(k.strip() for k in keys if k)


def mark_setup_complete() -> None:
    """Call this after the user saves their API keys."""
    current_settings["first_run"] = False
    save_settings(current_settings)