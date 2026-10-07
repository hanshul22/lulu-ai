import socket
import json
import os
import secrets
import sys


# ---------------------------------------------------------------------------
# FIX #4 — Platform-aware app-data directory
#
# The original code used os.getenv('LOCALAPPDATA') directly. On macOS and
# Linux this env var doesn't exist, getenv() returns None, and
# os.path.join(None, ...) raises TypeError at import time — crashing the
# entire app before the IPC server can even start.
#
# This mirrors the same platform detection in settings_manager.py and
# the newly fixed logger_setup.py.
# ---------------------------------------------------------------------------

def _get_app_data_dir() -> str:
    if sys.platform == "win32":
        base = os.getenv("LOCALAPPDATA") or os.path.expanduser("~")
    elif sys.platform == "darwin":
        base = os.path.expanduser("~/Library/Application Support")
    else:
        base = os.path.expanduser("~/.config")
    app_dir = os.path.join(base, "LuluApp")
    os.makedirs(app_dir, exist_ok=True)
    return app_dir


# Define paths
if getattr(sys, 'frozen', False):
    BASE_DIR = os.path.dirname(sys.executable)
else:
    BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))

APP_DATA_DIR = _get_app_data_dir()
TOKEN_FILE   = os.path.join(APP_DATA_DIR, 'token.json')
PORT         = 65432  # Localhost port


# ---------------------------------------------------------------------------
# Token cache — read from disk once, reuse for the lifetime of the process
# ---------------------------------------------------------------------------

_token: str | None = None


def get_or_create_token() -> str:
    """Return the IPC auth token, reading from disk only on first call."""
    global _token
    if _token is not None:
        return _token

    if os.path.exists(TOKEN_FILE):
        try:
            with open(TOKEN_FILE, 'r') as f:
                data   = json.load(f)
                _token = data.get('token')
                if _token:
                    return _token
        except Exception:
            pass

    # Generate and persist a new token
    _token = secrets.token_hex(16)
    with open(TOKEN_FILE, 'w') as f:
        json.dump({'token': _token}, f)
    return _token


# ---------------------------------------------------------------------------
# Safe receive helper — reads until the connection closes or goes quiet
# ---------------------------------------------------------------------------

def _recv_all(sock: socket.socket, chunk_size: int = 4096) -> bytes:
    """Read all available bytes from *sock*, handling responses larger than one chunk."""
    chunks = []
    while True:
        chunk = sock.recv(chunk_size)
        if not chunk:
            break
        chunks.append(chunk)
        if len(chunk) < chunk_size:
            # Last chunk — nothing more to read right now
            break
    return b"".join(chunks)


# ---------------------------------------------------------------------------
# Client
# ---------------------------------------------------------------------------

def send_command(command, payload=None):
    """Send a command to the worker process and return the response dict."""
    token   = get_or_create_token()
    message = {
        'token':   token,
        'command': command,
        'payload': payload or {},
    }

    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(2)
            s.connect(('127.0.0.1', PORT))
            s.sendall(json.dumps(message).encode('utf-8'))
            response = _recv_all(s)
            return json.loads(response.decode('utf-8'))
    except ConnectionRefusedError:
        return {'status': 'error', 'message': 'Worker not running'}
    except Exception as e:
        return {'status': 'error', 'message': str(e)}


# ---------------------------------------------------------------------------
# Server
# ---------------------------------------------------------------------------

def start_server(handler_func, stop_event):
    """Start the IPC server, blocking until stop_event is set."""
    token = get_or_create_token()

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        # SO_REUSEADDR lets the server bind immediately after a crash instead
        # of waiting ~60 seconds for the OS TIME_WAIT state to expire.
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        s.bind(('127.0.0.1', PORT))
        s.listen()
        s.settimeout(1.0)   # allows the stop_event check every second

        while not stop_event.is_set():
            try:
                conn, addr = s.accept()
                with conn:
                    data = _recv_all(conn)
                    if not data:
                        continue

                    try:
                        req = json.loads(data.decode('utf-8'))
                        if req.get('token') != token:
                            resp = {'status': 'error', 'message': 'Invalid token'}
                        else:
                            resp = handler_func(req['command'], req.get('payload'))
                    except Exception as e:
                        resp = {'status': 'error', 'message': str(e)}

                    conn.sendall(json.dumps(resp).encode('utf-8'))

            except socket.timeout:
                continue
            except Exception as e:
                print(f"IPC Server Error: {e}")