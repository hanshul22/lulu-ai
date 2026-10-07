"""lulu_cli.py — entry point for the `lulu` global command."""
from __future__ import annotations

import argparse
import importlib.metadata
import os
import platform
import sys
import time


# ---------------------------------------------------------------------------
# Version
# ---------------------------------------------------------------------------

def _get_version() -> str:
    try:
        return importlib.metadata.version("lulu-ai")
    except importlib.metadata.PackageNotFoundError:
        return "dev"


# ---------------------------------------------------------------------------
# Output helpers
# ---------------------------------------------------------------------------

GREEN  = "\033[92m"
YELLOW = "\033[93m"
RED    = "\033[91m"
CYAN   = "\033[96m"
RESET  = "\033[0m"

if sys.platform == "win32":
    try:
        import ctypes
        ctypes.windll.kernel32.SetConsoleMode(
            ctypes.windll.kernel32.GetStdHandle(-11), 7
        )
    except Exception:
        GREEN = YELLOW = RED = CYAN = RESET = ""


def _ok(msg: str)   -> None: print(f"{GREEN}✅ {msg}{RESET}")
def _warn(msg: str) -> None: print(f"{YELLOW}⚠️  {msg}{RESET}")
def _err(msg: str)  -> None: print(f"{RED}❌ {msg}{RESET}")
def _info(msg: str) -> None: print(f"{CYAN}ℹ️  {msg}{RESET}")


# ---------------------------------------------------------------------------
# Find actual lulu.exe location
# ---------------------------------------------------------------------------

def _find_lulu_scripts_dir() -> str | None:
    """Search all common Python install locations for the folder containing lulu.exe."""
    exe_name = "lulu.exe" if platform.system() == "Windows" else "lulu"

    candidates = []

    # 1. Next to current python executable and its Scripts subfolder
    py_dir = os.path.dirname(sys.executable)
    candidates.append(py_dir)
    candidates.append(os.path.join(py_dir, "Scripts"))

    # 2. Common Windows Python install locations
    if platform.system() == "Windows":
        local_app = os.environ.get("LOCALAPPDATA", "")
        app_data  = os.environ.get("APPDATA", "")
        home      = os.path.expanduser("~")

        for base in [local_app, app_data, home]:
            for sub in ["Programs\\Python", "Python", "Programs"]:
                for ver in [
                    "Python314", "Python313", "Python312",
                    "Python311", "Python310", "Python39",
                ]:
                    candidates.append(os.path.join(base, sub, ver, "Scripts"))
                    candidates.append(os.path.join(base, sub, ver))

        # 3. pip user install location
        candidates.append(os.path.join(app_data, "Python", "Scripts"))
        candidates.append(os.path.join(local_app, "Python", "Scripts"))

        # 4. Windows Store Python — scripts go into LocalCache packages
        packages_dir = os.path.join(local_app, "Packages")
        if os.path.isdir(packages_dir):
            for entry in os.listdir(packages_dir):
                if "PythonSoftwareFoundation" in entry or "python" in entry.lower():
                    for ver in ["Python311", "Python312", "Python313", "Python314", "Python310", "Python39"]:
                        store_scripts = os.path.join(
                            packages_dir, entry,
                            "LocalCache", "local-packages", ver, "Scripts"
                        )
                        candidates.append(store_scripts)

    else:
        # macOS / Linux
        candidates.append(os.path.expanduser("~/.local/bin"))
        candidates.append("/usr/local/bin")
        candidates.append("/usr/bin")

    # 4. Try importlib to find where lulu_cli itself is installed
    try:
        import importlib.util
        spec = importlib.util.find_spec("lulu_cli")
        if spec and spec.origin:
            pkg_dir = os.path.dirname(spec.origin)
            candidates.append(pkg_dir)
            candidates.append(os.path.join(os.path.dirname(pkg_dir), "Scripts"))
            candidates.append(os.path.join(os.path.dirname(pkg_dir), "bin"))
    except Exception:
        pass

    # Check each candidate
    for d in candidates:
        if d and os.path.isfile(os.path.join(d, exe_name)):
            return d

    return None


# ---------------------------------------------------------------------------
# Command implementations
# ---------------------------------------------------------------------------

def cmd_start(args) -> int:
    from lifecycle import start
    cwd = os.getcwd()
    _info(f"Starting Lulu AI assistant from: {cwd}")
    result = start(cwd=cwd)

    if result["status"] == "started":
        _ok(result["message"])
        _info("You can close this terminal — Lulu will keep running in the background.")
        _info("Run  lulu status  to check, or  lulu stop  to quit.")
        return 0
    elif result["status"] == "already_running":
        _warn(result["message"])
        return 0
    else:
        _err(result["message"])
        return 1


def cmd_stop(args) -> int:
    from lifecycle import stop
    _info("Stopping Lulu AI assistant...")
    result = stop()

    if result["status"] == "stopped":
        _ok(result["message"])
        return 0
    elif result["status"] == "not_running":
        _warn(result["message"])
        return 0
    else:
        _err(result["message"])
        return 1


def cmd_status(args) -> int:
    from lifecycle import status
    result = status()

    if result["status"] == "running":
        _ok(result["message"])
        if result.get("cwd"):
            _info(f"Working directory: {result['cwd']}")
    else:
        _warn(result["message"])
        _info("Run  lulu start  to launch the assistant.")

    return 0


def cmd_logs(args) -> int:
    from lifecycle import tail_logs, LOG_FILE

    if args.follow:
        _info(f"Streaming logs from {LOG_FILE}  (Ctrl+C to stop)\n")
        try:
            with open(LOG_FILE, "r", encoding="utf-8", errors="replace") as f:
                f.seek(0, 2)
                while True:
                    line = f.readline()
                    if line:
                        print(line, end="")
                    else:
                        time.sleep(0.2)
        except FileNotFoundError:
            _err(f"Log file not found: {LOG_FILE}")
            _info("Start Lulu first with  lulu start")
            return 1
        except KeyboardInterrupt:
            print()
            return 0
    else:
        lines = args.lines if hasattr(args, "lines") and args.lines else 50
        output = tail_logs(lines=lines)
        print(output)
        return 0


def cmd_doctor(args) -> int:
    from lifecycle import doctor
    _info("Running diagnostics...\n")
    results = doctor()

    all_ok = True
    for r in results:
        if r["status"] == "ok":
            _ok(f"{r['check']}: {r['message']}")
        elif r["status"] == "warning":
            _warn(f"{r['check']}: {r['message']}")
            all_ok = False
        else:
            _err(f"{r['check']}: {r['message']}")
            all_ok = False

    print()
    if all_ok:
        _ok("All checks passed. Lulu is ready to run.")
    else:
        _warn("Some checks need attention. Fix the issues above, then run  lulu start")

    return 0 if all_ok else 1


def cmd_fix_path(args) -> int:
    """Add the correct Scripts folder to PATH so lulu works from any terminal."""

    _info("Searching for lulu installation...")
    scripts_dir = _find_lulu_scripts_dir()

    if not scripts_dir:
        _err("Could not find lulu.exe on this system.")
        _info("Make sure lulu-ai is installed:  pip install lulu-ai")
        _info("Then run:  python -m lulu_cli fix-path")
        return 1

    _info(f"Found lulu at: {scripts_dir}")

    if platform.system() == "Windows":
        try:
            import winreg

            key = winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                r"Environment",
                0,
                winreg.KEY_READ | winreg.KEY_WRITE,
            )
            try:
                current_path, _ = winreg.QueryValueEx(key, "PATH")
            except FileNotFoundError:
                current_path = ""

            # Check all entries in PATH — not just substring match
            path_entries = [p.lower() for p in current_path.split(";")]
            if scripts_dir.lower() in path_entries:
                _ok(f"PATH already contains {scripts_dir}")
                _warn("Close and reopen your terminal for it to take effect.")
                return 0

            new_path = current_path.rstrip(";") + ";" + scripts_dir
            winreg.SetValueEx(key, "PATH", 0, winreg.REG_EXPAND_SZ, new_path)
            winreg.CloseKey(key)

            # Update current session too
            os.environ["PATH"] = os.environ.get("PATH", "") + ";" + scripts_dir

            _ok(f"Added to PATH permanently: {scripts_dir}")
            _warn("Close and reopen your terminal, then run:  lulu --help")
            return 0

        except Exception as exc:
            _err(f"Could not update PATH automatically: {exc}")
            _info("Run this manually in PowerShell:")
            print(f'\n  [System.Environment]::SetEnvironmentVariable("PATH", '
                  f'[System.Environment]::GetEnvironmentVariable("PATH", "User") + ";{scripts_dir}", "User")\n')
            return 1

    else:
        # macOS / Linux
        shell_rc = os.path.expanduser("~/.bashrc")
        if os.environ.get("SHELL", "").endswith("zsh"):
            shell_rc = os.path.expanduser("~/.zshrc")

        export_line = f'\nexport PATH="{scripts_dir}:$PATH"\n'

        try:
            with open(shell_rc, "a") as f:
                f.write(export_line)
            _ok(f"Added {scripts_dir} to {shell_rc}")
            _info(f"Run:  source {shell_rc}  or open a new terminal.")
            return 0
        except Exception as exc:
            _err(f"Could not update {shell_rc}: {exc}")
            _info(f"Add this line manually to {shell_rc}:")
            print(f'\n  export PATH="{scripts_dir}:$PATH"\n')
            return 1


# ---------------------------------------------------------------------------
# Argument parser
# ---------------------------------------------------------------------------

def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="lulu",
        description="Lulu AI Assistant — global hotkey-driven AI for MCQs and coding.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  lulu start              Start the assistant in the background
  lulu stop               Stop the assistant
  lulu status             Check if it's running
  lulu logs               Show last 50 log lines
  lulu logs --follow      Stream logs live
  lulu doctor             Diagnose your environment
  lulu fix-path           Fix PATH so lulu works from any terminal
        """,
    )

    parser.add_argument("--version", "-v", action="version",
                        version=f"lulu-ai {_get_version()}")

    sub = parser.add_subparsers(dest="command", metavar="COMMAND")
    sub.required = True

    sub.add_parser("start",    help="Start the Lulu assistant in the background")
    sub.add_parser("stop",     help="Stop the running assistant")
    sub.add_parser("status",   help="Check if the assistant is running")
    sub.add_parser("fix-path", help="Fix PATH so lulu works from any terminal")

    logs_p = sub.add_parser("logs", help="View log output")
    logs_p.add_argument("--follow", "-f", action="store_true",
                        help="Stream log output live")
    logs_p.add_argument("--lines", "-n", type=int, default=50, metavar="N",
                        help="Number of lines to show (default: 50)")

    sub.add_parser("doctor", help="Check environment, dependencies, and permissions")

    return parser


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    parser  = _build_parser()
    args    = parser.parse_args()
    dispatch = {
        "start":    cmd_start,
        "stop":     cmd_stop,
        "status":   cmd_status,
        "logs":     cmd_logs,
        "doctor":   cmd_doctor,
        "fix-path": cmd_fix_path,
    }
    handler = dispatch.get(args.command)
    if handler is None:
        parser.print_help()
        sys.exit(1)
    sys.exit(handler(args))


if __name__ == "__main__":
    main()