import logging
import sys
import os
from logging.handlers import RotatingFileHandler


# ---------------------------------------------------------------------------
# FIX #4 — Platform-aware app-data directory
#
# The original code used os.getenv('LOCALAPPDATA') directly. On macOS and
# Linux this env var doesn't exist, getenv() returns None, and
# os.path.join(None, ...) raises TypeError at import time — crashing the
# entire app before a single line of user code runs.
#
# This mirrors the same platform detection already used in settings_manager.py.
# ---------------------------------------------------------------------------

def _get_log_dir() -> str:
    if sys.platform == "win32":
        base = os.getenv("LOCALAPPDATA") or os.path.expanduser("~")
    elif sys.platform == "darwin":
        base = os.path.expanduser("~/Library/Application Support")
    else:
        base = os.path.expanduser("~/.config")
    log_dir = os.path.join(base, "LuluApp", "logs")
    os.makedirs(log_dir, exist_ok=True)
    return log_dir


APP_DATA_DIR  = _get_log_dir()
log_file_path = os.path.join(APP_DATA_DIR, "app.log")

# Clear existing handlers to avoid duplicate output when the module is
# reloaded (e.g. during a hot-restart).
for handler in logging.root.handlers[:]:
    logging.root.removeHandler(handler)

# ---------------------------------------------------------------------------
# Rotating file handler
#
# Keeps at most 3 log files (app.log, app.log.1, app.log.2),
# each capped at 5 MB. Total max disk usage: 15 MB.
# ---------------------------------------------------------------------------

_file_handler = RotatingFileHandler(
    log_file_path,
    maxBytes=5 * 1024 * 1024,   # 5 MB per file
    backupCount=3,               # keep 3 rotated files
    encoding="utf-8",
)

_log_format = logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")
_file_handler.setFormatter(_log_format)

_console_handler = logging.StreamHandler(sys.stdout)
_console_handler.setFormatter(_log_format)

# Configure root logger
logging.root.setLevel(logging.INFO)
logging.root.addHandler(_file_handler)
logging.root.addHandler(_console_handler)

logger = logging.getLogger(__name__)
logger.propagate = True


# ---------------------------------------------------------------------------
# Uncaught exception hook — logs crash tracebacks to the rotating file
# ---------------------------------------------------------------------------

def handle_exception(exc_type, exc_value, exc_traceback):
    if issubclass(exc_type, KeyboardInterrupt):
        sys.__excepthook__(exc_type, exc_value, exc_traceback)
        return
    logger.error("Uncaught exception", exc_info=(exc_type, exc_value, exc_traceback))

sys.excepthook = handle_exception