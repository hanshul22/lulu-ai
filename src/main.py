import threading
import os
import time
import sys
from pynput import keyboard
from pynput.keyboard import Controller as KeyboardController
import config
import state
from logger_setup import logger
from mcq_handlers import capture_context, solve_current_mcq
from subjective_handlers import capture_subjective_screenshot, generate_ai_response, retry_ai_response, generate_code_explanation, generate_step_by_step_response, clear_image_cache
from typing_handler import auto_type_response
import hidden_notes
import explanation_window
import settings_panel
import settings_manager
from settings_manager import current_settings

# ── Thread-safe debounce for control panel hotkey ─────────────────────────────
_panel_open_lock      = threading.Lock()
_last_panel_open_time = 0.0


# ---------------------------------------------------------------------------
# Startup config validation
# ---------------------------------------------------------------------------

def _validate_config() -> bool:
    """Check all required configuration is present before starting."""
    errors   = []
    warnings = []

    gemini_keys = getattr(config, "GEMINI_API_KEYS", [])
    if not gemini_keys:
        errors.append(
            "No Gemini API key configured. "
            "The settings panel will open automatically — please enter your key there."
        )
    else:
        logger.info(f"🔑 {len(gemini_keys)} Gemini API key(s) configured.")
        if len(gemini_keys) < 2:
            warnings.append("Only 1 Gemini key — no automatic failover on rate limits. Add more in settings.")

    if not config.GROQ_API_KEY:
        warnings.append("GROQ API key not set — theory answers will fall back to Gemini.")
    if not config.OPENROUTER_API_KEY:
        warnings.append("OpenRouter API key not set — code generation will fall back to Gemini.")

    for w in warnings:
        logger.warning(f"⚠️  Config warning: {w}")
    for e in errors:
        logger.error(f"❌ Config error: {e}")

    return len(errors) == 0


# ---------------------------------------------------------------------------
# Hotkey callbacks
# ---------------------------------------------------------------------------

def on_activate_context() -> None:
    logger.info("[📖 CONTEXT CAPTURE HOTKEY PRESSED!]")
    threading.Thread(target=capture_context).start()

def on_activate_question() -> None:
    logger.info("[❓ QUESTION CAPTURE HOTKEY PRESSED!]")
    threading.Thread(target=solve_current_mcq).start()

def on_capture_subjective() -> None:
    logger.info("[🖼️  SUBJECTIVE CAPTURE HOTKEY PRESSED!]")
    threading.Thread(target=capture_subjective_screenshot).start()

def on_generate_response() -> None:
    logger.info("[🧠 GENERATE RESPONSE HOTKEY PRESSED!]")
    threading.Thread(target=generate_ai_response, daemon=True).start()

def on_type_response() -> None:
    logger.info("[⌨️  TYPE RESPONSE HOTKEY PRESSED!]")
    threading.Thread(target=auto_type_response).start()

def on_retry_subjective() -> None:
    logger.info("[🔄 RETRY HOTKEY PRESSED!]")
    threading.Thread(target=retry_ai_response, daemon=True).start()

def on_toggle_notes() -> None:
    if not current_settings['features']['notes_enabled']:
        logger.info("🚫 Notes feature is disabled in settings.")
        return
    logger.info("[📝 TOGGLE NOTES HOTKEY PRESSED!]")
    hidden_notes.toggle_notes()

def on_explain_code() -> None:
    if not current_settings['features']['explanation_enabled']:
        logger.info("🚫 Explanation feature is disabled in settings.")
        return
    logger.info("[🧠 EXPLAIN CODE HOTKEY PRESSED!]")
    threading.Thread(target=generate_code_explanation, daemon=True).start()

def on_toggle_explanation() -> None:
    if not current_settings['features']['explanation_enabled']:
        logger.info("🚫 Explanation feature is disabled in settings.")
        return
    logger.info("[📝 TOGGLE EXPLANATION HOTKEY PRESSED!]")
    explanation_window.toggle_explanation()

def on_open_control_panel() -> None:
    global _last_panel_open_time
    with _panel_open_lock:
        now = time.time()
        if now - _last_panel_open_time < 0.6:
            logger.debug("⚙️ Control panel hotkey debounced.")
            return
        _last_panel_open_time = now

    logger.info("[⚙️ CONTROL PANEL HOTKEY PRESSED!]")
    if hidden_notes.notes_app and hidden_notes.notes_app.root:
        hidden_notes.notes_app.root.after(
            0,
            lambda: settings_panel.show_control_panel(
                restart_callback=restart_program,
                master=hidden_notes.notes_app.root
            )
        )
    else:
        logger.error("❌ Cannot open control panel: Main application window not found.")

def restart_program() -> None:
    logger.info("🔄 Restarting application...")
    python = sys.executable
    os.execl(python, python, *sys.argv)

def on_move_notes_up()    -> None:
    hidden_notes.move_notes(0, -20);    explanation_window.move_explanation(0, -20)
def on_move_notes_down()  -> None:
    hidden_notes.move_notes(0, 20);     explanation_window.move_explanation(0, 20)
def on_move_notes_left()  -> None:
    hidden_notes.move_notes(-20, 0);    explanation_window.move_explanation(-20, 0)
def on_move_notes_right() -> None:
    hidden_notes.move_notes(20, 0);     explanation_window.move_explanation(20, 0)

def on_resume_typing() -> None:
    if state.is_typing_paused and state.is_typing_active:
        # Release all modifiers held during Ctrl+Alt+Z, not just three —
        # the full set is needed to prevent garbled first characters on resume.
        # The 0.4s grace period inside auto_type_response handles the OS delay,
        # so no sleep is needed here.
        kc = KeyboardController()
        for key in [
            keyboard.Key.ctrl,   keyboard.Key.ctrl_l,  keyboard.Key.ctrl_r,
            keyboard.Key.alt,    keyboard.Key.alt_l,   keyboard.Key.alt_gr,
            keyboard.Key.shift,  keyboard.Key.shift_l, keyboard.Key.shift_r,
            keyboard.Key.cmd,    keyboard.Key.cmd_l,   keyboard.Key.cmd_r,
        ]:
            try:
                kc.release(key)
            except Exception:
                pass
        state.resume_typing_event.set()
        logger.info(f"⏯️ Resuming from position {state.current_typing_position}...")
    elif not state.is_typing_active:
        # Drain any stale event so it can't accidentally unblock a future session
        state.resume_typing_event.clear()
        logger.info("⏯️ No active typing session to resume.")
    else:
        logger.info("⏯️ Typing is not currently paused.")

def on_clear_context() -> None:
    state.context_captured = False
    state.subjective_screenshots = []
    state.reset_subjective_caches()
    clear_image_cache()
    if os.path.exists(config.SUBJECTIVE_SCREENSHOT_DIR):
        for file in os.listdir(config.SUBJECTIVE_SCREENSHOT_DIR):
            try:
                os.remove(os.path.join(config.SUBJECTIVE_SCREENSHOT_DIR, file))
            except Exception as e:
                logger.error(f"Failed to delete {file}: {e}")
    logger.info("🧹 Context & subjective mode cleared.")

def on_exit() -> None:
    logger.info("🛑 Exiting...")
    os._exit(0)

def on_step_by_step_solution() -> None:
    logger.info("[🧠 STEP-BY-STEP SOLUTION HOTKEY PRESSED!]")
    threading.Thread(target=generate_step_by_step_response, daemon=True).start()


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def run_app():
    # Initialize GUI first so we can show the settings panel if needed
    app = hidden_notes.HiddenNotesWindow()
    hidden_notes.notes_app = app

    exp_app = explanation_window.ExplanationWindow(master=app.root)
    explanation_window.explanation_app = exp_app

    # ---------------------------------------------------------------------------
    # First-run check — open settings panel automatically if no API key set
    # ---------------------------------------------------------------------------
    config_ok = _validate_config()

    if not config_ok or settings_manager.is_first_run():
        logger.info("👋 First run detected — opening settings panel for API key setup.")
        # Schedule settings panel to open after GUI is ready
        app.root.after(
            500,  # small delay so window is fully rendered first
            lambda: settings_panel.show_control_panel(
                restart_callback=restart_program,
                master=app.root
            )
        )
    else:
        logger.info("✅ Config valid — Lulu AI Assistant Ready!")
        _log_hotkey_reference()

    # Hotkey conflict check
    if config.CONTROL_PANEL_HOTKEY == config.TOGGLE_NOTES_HOTKEY:
        logger.warning(
            f"⚠️ Hotkey conflict: Control Panel and Toggle Notes share "
            f"({config.CONTROL_PANEL_HOTKEY}). Resetting to <ctrl>+<alt>+m"
        )
        config.CONTROL_PANEL_HOTKEY = "<ctrl>+<alt>+m"

    # Register global hotkeys
    h = keyboard.GlobalHotKeys({
        config.CAPTURE_CONTEXT_HOTKEY:       on_activate_context,
        config.CAPTURE_QUESTION_HOTKEY:      on_activate_question,
        config.CAPTURE_SUBJECTIVE_HOTKEY:    on_capture_subjective,
        config.GENERATE_RESPONSE_HOTKEY:     on_generate_response,
        config.TYPE_RESPONSE_HOTKEY:         on_type_response,
        config.RESUME_TYPING_HOTKEY:         on_resume_typing,
        config.RETRY_SUBJECTIVE_HOTKEY:      on_retry_subjective,
        config.TOGGLE_NOTES_HOTKEY:          on_toggle_notes,
        config.EXPLAIN_CODE_HOTKEY:          on_explain_code,
        config.TOGGLE_EXPLANATION_HOTKEY:    on_toggle_explanation,
        config.STEP_BY_STEP_SOLUTION_HOTKEY: on_step_by_step_solution,
        config.CONTROL_PANEL_HOTKEY:         on_open_control_panel,
        config.MOVE_NOTES_UP_HOTKEY:         on_move_notes_up,
        config.MOVE_NOTES_DOWN_HOTKEY:       on_move_notes_down,
        config.MOVE_NOTES_LEFT_HOTKEY:       on_move_notes_left,
        config.MOVE_NOTES_RIGHT_HOTKEY:      on_move_notes_right,
        config.CLEAR_CONTEXT_HOTKEY:         on_clear_context,
        config.EXIT_HOTKEY:                  on_exit,
    })
    h.start()

    try:
        app.run()
    except KeyboardInterrupt:
        pass
    finally:
        h.stop()


def _log_hotkey_reference():
    logger.info(f"📖 {config.CAPTURE_CONTEXT_HOTKEY.upper()} — Capture context (MCQ)")
    logger.info(f"❓ {config.CAPTURE_QUESTION_HOTKEY.upper()} — Capture question (MCQ)")
    logger.info(f"🖼️  {config.CAPTURE_SUBJECTIVE_HOTKEY.upper()} — Capture screenshot (coding)")
    logger.info(f"🧠 {config.GENERATE_RESPONSE_HOTKEY.upper()} — Generate AI response")
    logger.info(f"⌨️  {config.TYPE_RESPONSE_HOTKEY.upper()} — Auto-type response")
    logger.info(f"⏯️  {config.RESUME_TYPING_HOTKEY.upper()} — Resume typing")
    logger.info(f"🔄 {config.RETRY_SUBJECTIVE_HOTKEY.upper()} — Retry with error screenshot")
    logger.info(f"📝 {config.TOGGLE_NOTES_HOTKEY.upper()} — Toggle hidden notes")
    logger.info(f"⚙️  {config.CONTROL_PANEL_HOTKEY.upper()} — Open control panel")
    logger.info(f"🧹 {config.CLEAR_CONTEXT_HOTKEY.upper()} — Clear everything")
    logger.info(f"🚪 {config.EXIT_HOTKEY.upper()} — Exit")
    logger.info("⚠️  During auto-typing: DO NOT CLICK (click will pause typing)")


if __name__ == "__main__":
    run_app()