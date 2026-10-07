"""lifecycle.py — shared helpers for starting, stopping and querying the Lulu worker."""
from __future__ import annotations

import json
import os
import platform
import signal
import subprocess
import sys
import time

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

APP_DATA_DIR = os.path.join(os.getenv("LOCALAPPDATA", os.path.expanduser("~")), "LuluApp")
os.makedirs(APP_DATA_DIR, exist_ok=True)

PID_FILE  = os.path.join(APP_DATA_DIR, "lulu.pid")
META_FILE = os.path.join(APP_DATA_DIR, "lulu.meta.json")   # stores working dir
LOG_FILE  = os.path.join(APP_DATA_DIR, "logs", "app.log")

IPC_HOST    = "127.0.0.1"
IPC_PORT    = 65432
IPC_TIMEOUT = 2


# ---------------------------------------------------------------------------
# Meta file — stores the working directory used at start time
# ---------------------------------------------------------------------------

def _write_meta(pid: int, cwd: str) -> None:
    with open(META_FILE, "w") as f:
        json.dump({"pid": pid, "cwd": cwd}, f)


def _read_meta() -> dict:
    try:
        with open(META_FILE, "r") as f:
            return json.load(f)
    except Exception:
        return {}


def _clear_meta() -> None:
    for path in (PID_FILE, META_FILE):
        try:
            os.remove(path)
        except FileNotFoundError:
            pass


# ---------------------------------------------------------------------------
# PID helpers
# ---------------------------------------------------------------------------

def _write_pid(pid: int) -> None:
    with open(PID_FILE, "w") as f:
        json.dump({"pid": pid}, f)


def _read_pid() -> int | None:
    try:
        with open(PID_FILE, "r") as f:
            return json.load(f).get("pid")
    except Exception:
        return None


def _pid_is_alive(pid: int) -> bool:
    try:
        if platform.system() == "Windows":
            import ctypes
            SYNCHRONIZE = 0x00100000
            handle = ctypes.windll.kernel32.OpenProcess(SYNCHRONIZE, False, pid)
            if handle:
                ctypes.windll.kernel32.CloseHandle(handle)
                return True
            return False
        else:
            os.kill(pid, 0)
            return True
    except (ProcessLookupError, PermissionError, OSError):
        return False


# ---------------------------------------------------------------------------
# IPC helpers
# ---------------------------------------------------------------------------

def _get_token() -> str:
    token_file = os.path.join(APP_DATA_DIR, "token.json")
    try:
        with open(token_file, "r") as f:
            return json.load(f).get("token", "")
    except Exception:
        return ""


def _ipc_ping() -> bool:
    import socket
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(IPC_TIMEOUT)
            s.connect((IPC_HOST, IPC_PORT))
            msg = json.dumps({"token": _get_token(), "command": "PING", "payload": {}})
            s.sendall(msg.encode("utf-8"))
            resp = s.recv(4096)
            data = json.loads(resp.decode("utf-8"))
            return data.get("status") == "ok"
    except Exception:
        return False


# ---------------------------------------------------------------------------
# Worker locator
# ---------------------------------------------------------------------------

def _find_worker_script() -> str | None:
    """Search for src/worker.py in common locations."""
    candidates = [
        # Installed package — src/ is next to lifecycle.py
        os.path.join(os.path.dirname(os.path.abspath(__file__)), "src", "worker.py"),
        # Running from cloned repo
        os.path.join(os.getcwd(), "src", "worker.py"),
        # Inside site-packages
        os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src", "worker.py"),
    ]
    for path in candidates:
        norm = os.path.normpath(path)
        if os.path.exists(norm):
            return norm
    return None


def _find_worker_cwd() -> str:
    """Return the best working directory for the worker process.

    Priority:
    1. Last used working directory (stored in meta file)
    2. Directory containing src/worker.py
    3. Current working directory
    """
    meta = _read_meta()
    last_cwd = meta.get("cwd")
    if last_cwd and os.path.isdir(last_cwd) and os.path.exists(os.path.join(last_cwd, "src", "worker.py")):
        return last_cwd

    worker = _find_worker_script()
    if worker:
        # worker is at <project_root>/src/worker.py — go up one level
        return os.path.dirname(os.path.dirname(worker))

    return os.getcwd()


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def start(cwd: str | None = None) -> dict:
    """Start the Lulu worker as a detached background process.

    Parameters
    ----------
    cwd:
        Working directory for the worker. If None, auto-detected from the
        location of src/worker.py so .env and settings.json are found correctly.
    """
    if _ipc_ping():
        return {"status": "already_running", "message": "Lulu is already running."}

    pid = _read_pid()
    if pid and _pid_is_alive(pid):
        return {"status": "already_running", "message": f"Lulu is already running (PID {pid})."}

    worker = _find_worker_script()
    if not worker:
        return {
            "status": "error",
            "message": (
                "Could not locate src/worker.py.\n"
                "Run  lulu start  from your project folder, or reinstall with:\n"
                "  pip install lulu-ai"
            ),
        }

    # Use provided cwd or auto-detect from worker script location
    working_dir = cwd or _find_worker_cwd()

    try:
        if platform.system() == "Windows":
            DETACHED_PROCESS         = 0x00000008
            CREATE_NEW_PROCESS_GROUP = 0x00000200
            # CREATE_BREAKAWAY_FROM_JOB is required because Windows Terminal
            # (and VS Code's integrated terminal) puts every process it spawns
            # into a Job Object. When that terminal window is closed, Windows
            # kills every process still in the job — including our "detached"
            # worker, since DETACHED_PROCESS alone only detaches the console,
            # not the job. Breaking away from the job is what actually lets
            # the worker keep running after the terminal closes.
            CREATE_BREAKAWAY_FROM_JOB = 0x01000000
            try:
                proc = subprocess.Popen(
                    [sys.executable, worker],
                    cwd=working_dir,           # ← worker runs from project root
                    creationflags=(
                        DETACHED_PROCESS
                        | CREATE_NEW_PROCESS_GROUP
                        | CREATE_BREAKAWAY_FROM_JOB
                    ),
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    stdin=subprocess.DEVNULL,
                    close_fds=True,
                )
            except OSError:
                # Some restricted job objects (rare — certain sandboxed
                # terminals/CI runners) disallow breakaway and CreateProcess
                # fails outright. Fall back to launching without the flag so
                # `lulu start` still works, even though in that specific
                # edge case the worker may still die with its parent job.
                proc = subprocess.Popen(
                    [sys.executable, worker],
                    cwd=working_dir,
                    creationflags=DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    stdin=subprocess.DEVNULL,
                    close_fds=True,
                )
        else:
            proc = subprocess.Popen(
                [sys.executable, worker],
                cwd=working_dir,           # ← worker runs from project root
                start_new_session=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                stdin=subprocess.DEVNULL,
                close_fds=True,
            )

        _write_pid(proc.pid)
        _write_meta(proc.pid, working_dir)

        # Wait up to 3 seconds for the IPC server to become reachable
        for _ in range(10):
            time.sleep(0.3)
            if _ipc_ping():
                break

        return {
            "status": "started",
            "message": f"Lulu started successfully (PID {proc.pid}).",
            "pid": proc.pid,
        }

    except Exception as exc:
        return {"status": "error", "message": f"Failed to start Lulu: {exc}"}


def stop() -> dict:
    """Stop the Lulu worker gracefully via IPC, falling back to kill."""
    if _ipc_ping():
        import socket
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.settimeout(IPC_TIMEOUT)
                s.connect((IPC_HOST, IPC_PORT))
                msg = json.dumps({"token": _get_token(), "command": "STOP", "payload": {}})
                s.sendall(msg.encode("utf-8"))
                s.recv(4096)
            _clear_meta()
            return {"status": "stopped", "message": "Lulu stopped gracefully."}
        except Exception:
            pass

    pid = _read_pid()
    if pid and _pid_is_alive(pid):
        try:
            if platform.system() == "Windows":
                subprocess.call(["taskkill", "/F", "/PID", str(pid)], stdout=subprocess.DEVNULL)
            else:
                os.kill(pid, signal.SIGTERM)
            _clear_meta()
            return {"status": "stopped", "message": f"Lulu process (PID {pid}) terminated."}
        except Exception as exc:
            return {"status": "error", "message": f"Could not terminate PID {pid}: {exc}"}

    _clear_meta()
    return {"status": "not_running", "message": "Lulu is not running."}


def status() -> dict:
    """Check whether the Lulu worker is running."""
    pid = _read_pid()
    ipc_alive = _ipc_ping()
    pid_alive  = pid is not None and _pid_is_alive(pid)

    if ipc_alive or pid_alive:
        meta = _read_meta()
        cwd  = meta.get("cwd", "unknown")
        return {
            "status":  "running",
            "message": f"Lulu is running (PID {pid}).",
            "pid":     pid,
            "cwd":     cwd,
        }

    if pid:
        _clear_meta()

    return {"status": "stopped", "message": "Lulu is not running.", "pid": None}


def tail_logs(lines: int = 50) -> str:
    try:
        with open(LOG_FILE, "r", encoding="utf-8", errors="replace") as f:
            all_lines = f.readlines()
        return "".join(all_lines[-lines:])
    except FileNotFoundError:
        return f"Log file not found at: {LOG_FILE}\nStart Lulu first with: lulu start"
    except Exception as exc:
        return f"Error reading log file: {exc}"


def doctor() -> list[dict]:
    """Run environment checks and return results."""
    results = []

    # Python version
    major, minor = sys.version_info[:2]
    if (major, minor) >= (3, 9):
        results.append({"check": "Python version", "status": "ok", "message": f"Python {major}.{minor}"})
    else:
        results.append({"check": "Python version", "status": "error",
                        "message": f"Python {major}.{minor} — lulu-ai requires Python 3.9+"})

    # Dependencies
    required = {
        "pynput":        "pynput",
        "google.genai":  "google-genai",
        "PIL":           "Pillow",
        "pyautogui":     "pyautogui",
        "requests":      "requests",
        "dotenv":        "python-dotenv",
        "customtkinter": "customtkinter",
    }
    for module, package in required.items():
        try:
            __import__(module)
            results.append({"check": f"Package: {package}", "status": "ok", "message": "Installed"})
        except ImportError:
            results.append({"check": f"Package: {package}", "status": "error",
                            "message": f"Not installed — run: pip install {package}"})

    # worker.py locatable
    worker = _find_worker_script()
    if worker:
        results.append({"check": "src/worker.py", "status": "ok", "message": worker})
    else:
        results.append({"check": "src/worker.py", "status": "error",
                        "message": "Not found — run lulu start from your project folder"})

    # Gemini API keys — read directly from settings.json in app-data
    try:
        import json as _json
        _settings_file = os.path.join(APP_DATA_DIR, "settings.json")
        if os.path.exists(_settings_file):
            with open(_settings_file, "r", encoding="utf-8") as _f:
                _s = _json.load(_f)
            # Check new dynamic list first, fall back to legacy field
            gemini_keys = [k.strip().strip('"\'') for k in _s.get("gemini_api_keys", []) if k and k.strip().strip('"\'')]
            if not gemini_keys:
                legacy = _s.get("api_key", "").strip().strip('"\'')
                if legacy:
                    gemini_keys = [legacy]
            if gemini_keys:
                masked = gemini_keys[0][:4] + "..." + gemini_keys[0][-4:]
                results.append({"check": "Gemini API keys", "status": "ok",
                                "message": f"{len(gemini_keys)} key(s) configured [primary: {masked}]"})
            else:
                results.append({"check": "Gemini API keys", "status": "warning",
                                "message": (
                                    "Not set — run  lulu start  and enter your key "
                                    "in the settings panel (Ctrl+Alt+M)"
                                )})
        else:
            results.append({"check": "Gemini API keys", "status": "warning",
                            "message": "No settings found — run  lulu start  to configure"})
    except Exception:
        results.append({"check": "Gemini API keys", "status": "warning",
                        "message": "Could not read settings — run  lulu start  to configure"})

    # macOS accessibility
    if platform.system() == "Darwin":
        try:
            result = subprocess.run(
                ["osascript", "-e", 'tell application "System Events" to keystroke ""'],
                capture_output=True, timeout=3
            )
            if result.returncode == 0:
                results.append({"check": "macOS Accessibility", "status": "ok", "message": "Granted"})
            else:
                results.append({"check": "macOS Accessibility", "status": "warning",
                                "message": "Open System Settings → Privacy → Accessibility and add Terminal"})
        except Exception:
            results.append({"check": "macOS Accessibility", "status": "warning", "message": "Could not verify"})

    # Log directory writable
    log_dir = os.path.dirname(LOG_FILE)
    os.makedirs(log_dir, exist_ok=True)
    if os.access(log_dir, os.W_OK):
        results.append({"check": "Log directory", "status": "ok", "message": log_dir})
    else:
        results.append({"check": "Log directory", "status": "error",
                        "message": f"Not writable: {log_dir}"})

    return results