import threading
import sys
import os
import time
import ipc_utils
import main
import hidden_notes

# Add src to path
sys.path.append(os.path.dirname(__file__))

stop_event = threading.Event()


# ---------------------------------------------------------------------------
# Graceful shutdown helper
# ---------------------------------------------------------------------------

def _graceful_shutdown(delay: float = 0.3) -> None:
    """Signal the application to stop, then exit cleanly after *delay* seconds.

    Tries to shut down via Tkinter's event loop first (safe, runs on the main
    thread). Falls back to a timed thread exit only if the GUI root is gone.
    Using os._exit(0) as a hard kill is kept as the last resort but is no
    longer the *first* thing called — this avoids cutting off any in-flight
    file writes or socket flushes.
    """
    stop_event.set()

    if hidden_notes.notes_app and hidden_notes.notes_app.root:
        try:
            # after() schedules the call on the Tkinter main thread — safe way
            # to trigger shutdown without calling os._exit from a foreign thread.
            hidden_notes.notes_app.root.after(
                int(delay * 1000),
                hidden_notes.notes_app.root.destroy,
            )
            return
        except Exception:
            pass  # Root may have already been destroyed — fall through

    # GUI root unavailable: give in-flight threads a moment to finish then exit.
    def _deferred_exit():
        time.sleep(delay)
        os._exit(0)

    t = threading.Thread(target=_deferred_exit, daemon=True)
    t.start()


# ---------------------------------------------------------------------------
# IPC command handler
# ---------------------------------------------------------------------------

def handle_command(command: str, payload: dict) -> dict:
    if command == 'PING':
        return {'status': 'ok', 'message': 'Pong'}

    elif command == 'STOP':
        _graceful_shutdown(delay=0.3)
        return {'status': 'ok', 'message': 'Stopping...'}

    elif command == 'STATUS':
        return {'status': 'ok', 'state': 'running'}

    return {'status': 'error', 'message': f'Unknown command: {command!r}'}


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def run_worker() -> None:
    # Start IPC server on a daemon thread — it will be killed automatically
    # when the main thread exits, so no explicit cleanup is needed here.
    ipc_thread = threading.Thread(
        target=ipc_utils.start_server,
        args=(handle_command, stop_event),
        daemon=True,
        name="ipc-server",
    )
    ipc_thread.start()

    print("Worker started. Listening for commands...")

    # Run the main application (blocking — returns when the GUI closes)
    try:
        main.run_app()
    except KeyboardInterrupt:
        pass
    finally:
        # Signal the IPC server to stop its accept loop cleanly
        stop_event.set()


if __name__ == "__main__":
    run_worker()