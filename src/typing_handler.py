import threading
import time
import random
import collections
from pynput import mouse, keyboard
from pynput.keyboard import Controller as KeyboardController
import state
import config
from logger_setup import logger


# ---------------------------------------------------------------------------
# Pre-generated delay buffer
# ---------------------------------------------------------------------------

_DELAY_BATCH = 200
_delay_buffer: collections.deque[float] = collections.deque()


def _next_delay() -> float:
    """Return the next pre-generated typing delay, refilling the buffer as needed."""
    if not _delay_buffer:
        _delay_buffer.extend(
            random.uniform(config.TYPING_DELAY_MIN, config.TYPING_DELAY_MAX)
            for _ in range(_DELAY_BATCH)
        )
    return _delay_buffer.popleft()


def _next_rhythm_delay() -> float:
    """Return the next pre-generated rhythm pause (every 15 characters)."""
    return random.uniform(0.05, 0.15)


def _flush_delay_buffer() -> None:
    """Discard all pre-generated delays.

    Called on resume so the first characters after a pause don't inherit
    stale delays that were generated at a different speed context.
    """
    _delay_buffer.clear()


# ---------------------------------------------------------------------------
# Key release helper
# ---------------------------------------------------------------------------

_ALL_MODIFIERS = [
    keyboard.Key.ctrl,
    keyboard.Key.ctrl_l,
    keyboard.Key.ctrl_r,
    keyboard.Key.alt,
    keyboard.Key.alt_l,
    keyboard.Key.alt_gr,
    keyboard.Key.shift,
    keyboard.Key.shift_l,
    keyboard.Key.shift_r,
    keyboard.Key.cmd,
    keyboard.Key.cmd_l,
    keyboard.Key.cmd_r,
]


def _release_all_modifiers(kbd: KeyboardController) -> None:
    """Force-release every modifier key the OS might still think is held down.

    When the user presses Ctrl+Alt+Z to resume typing, those keys are
    physically held for a moment. pynput's Controller.release() sends a
    synthetic key-up event for each one so the OS no longer treats them
    as held — preventing garbled output like 'ṭeuowamo'.
    """
    for key in _ALL_MODIFIERS:
        try:
            kbd.release(key)
        except Exception:
            pass   # Some keys may not be held — ignore the error


# ---------------------------------------------------------------------------
# Auto-type
# ---------------------------------------------------------------------------

# How long to wait after releasing modifier keys before resuming typing.
# This gives the OS time to process the synthetic key-up events so they
# don't bleed into the first typed characters.
_RESUME_GRACE_PERIOD = 0.4   # seconds


def auto_type_response() -> None:
    """
    Types the stored AI response with intelligent editor-aware indentation handling.
    Specifically handles code blocks to prevent double indentation.
    """
    # Reset typing state
    state.is_typing_active = True
    state.is_typing_paused = False
    state.current_typing_position = 0

    # Snapshot response text into a local variable — faster loop access and
    # protects against another thread clearing it mid-session.
    response_text = state.get_ai_response()

    if response_text is None:
        logger.info("⏳ AI response not ready yet. Waiting...")
        state.ai_response_ready_subjective.wait(timeout=60)
        response_text = state.get_ai_response()
        if response_text is None:
            logger.error("❌ AI response still not available after waiting.")
            state.is_typing_active = False
            return

    logger.info("⚠️ DO NOT TYPE OR CLICK DURING AUTO-TYPING! (Click will PAUSE typing)")
    logger.info("⌨️  Starting auto-type in 3 seconds. Click target field now...")
    time.sleep(3)

    # State tracking for code context
    brace_stack: list[int] = []
    i = 0
    kbd = KeyboardController()

    # Release any modifiers that might be held from the hotkey that triggered
    # auto-type (e.g. Ctrl+Alt+T) before we start typing.
    _release_all_modifiers(kbd)
    time.sleep(_RESUME_GRACE_PERIOD)

    # ---------------------------------------------------------------------------
    # Mouse listener — single long-lived listener gated by a flag.
    # IMPORTANT: The listener is created and started AFTER the 3-second countdown
    # and modifier-release grace period. Starting it earlier meant that the click
    # the user makes to focus the target text field (during the countdown) was
    # caught by the listener and immediately paused typing before a single
    # character was typed — causing the "typing never starts" bug.
    # ---------------------------------------------------------------------------
    _listener_active = threading.Event()
    _listener_active.set()

    # Record the exact moment typing begins. We ignore any click that arrives
    # within the first 0.5 s — this absorbs any residual click event from the
    # user focusing the field just before typing starts.
    _typing_start_time = time.time()
    _CLICK_DEAF_PERIOD = 0.5  # seconds to ignore clicks at the very start

    def on_mouse_click(x, y, button, pressed):
        if (
            pressed
            and button == mouse.Button.left
            and state.is_typing_active
            and _listener_active.is_set()
            and (time.time() - _typing_start_time) > _CLICK_DEAF_PERIOD
        ):
            state.is_typing_paused = True
            _listener_active.clear()
            logger.info("⏸️ Mouse click detected. Pausing typing (focus loss).")
        return True  # Keep listener alive — we gate with the flag

    mouse_listener = mouse.Listener(on_click=on_mouse_click)

    try:
        mouse_listener.start()
        response_len = len(response_text)

        while i < response_len and state.is_typing_active:

            # ── Handle pause ──────────────────────────────────────────────
            if state.is_typing_paused:
                logger.info(
                    f"⏸️ Typing paused at position {i}/{response_len}. "
                    f"Press Ctrl+Alt+Z to resume..."
                )

                # Block until the resume hotkey fires
                state.resume_typing_event.wait()
                state.resume_typing_event.clear()
                state.is_typing_paused = False

                # ── CRITICAL: release ALL modifier keys ───────────────────
                # The user just held Ctrl+Alt+Z. We must send synthetic
                # key-up events for every modifier before typing resumes,
                # otherwise the first characters come out garbled.
                _release_all_modifiers(kbd)

                # Flush stale pre-generated delays so the first characters
                # after resume use fresh delays at the correct speed.
                _flush_delay_buffer()

                # Grace period — give the OS time to process the key-up
                # events before we start sending key-down events for text.
                # 0.4s is enough for all tested editors (VS Code, IntelliJ,
                # Notepad++, browser text fields).
                logger.info(f"⏯️ Resuming in {_RESUME_GRACE_PERIOD}s...")
                time.sleep(_RESUME_GRACE_PERIOD)

                # Re-arm mouse listener for the next potential pause
                _listener_active.set()
                continue

            # ── Type next character ───────────────────────────────────────
            try:
                char = response_text[i]

                # Track brace depth for indentation logic
                if char == '{':
                    brace_stack.append(i)
                elif char == '}' and brace_stack:
                    brace_stack.pop()

                # Newline handling
                if char in ['\n', '\r']:
                    kbd.tap(keyboard.Key.enter)
                    time.sleep(0.05)  # Let editor apply auto-indent

                    in_code_block = bool(brace_stack)

                    if in_code_block:
                        j = i + 1
                        ai_indent = 0
                        while j < response_len and response_text[j] == ' ':
                            ai_indent += 1
                            j += 1
                        if ai_indent > 0:
                            logger.debug(f"⏭️ Skipping {ai_indent} auto-indent spaces")
                            i = j - 1
                    else:
                        j = i + 1
                        while j < response_len and response_text[j] == ' ':
                            j += 1
                        i = j - 1

                    i += 1
                    continue

                # Regular character
                kbd.type(char)
                time.sleep(_next_delay())
                i += 1
                state.current_typing_position = i

                # Natural rhythm pause every 15 characters
                if i % 15 == 0:
                    time.sleep(_next_rhythm_delay())

            except Exception as e:
                logger.error(f"⚠️ Error typing char at position {i}: {e}")
                time.sleep(0.1)
                i += 1   # Skip the problematic character and continue
                continue

        logger.info("✅ Finished typing AI response.")

    except Exception as e:
        logger.error(f"❌ Typing failed: {e}")
    finally:
        state.is_typing_active = False
        if mouse_listener.is_alive():
            mouse_listener.stop()