import threading
import io
import pyautogui
from PIL import Image
from pynput import mouse, keyboard
import config
import state
from logger_setup import logger
from utils import capture_single_click, compress_for_api
from ai_core import generate_content_with_fallback, GeminiError


# ---------------------------------------------------------------------------
# Internal AI helpers that accept in-memory PIL Images
# (avoids saving to disk then re-opening for every MCQ solve)
# ---------------------------------------------------------------------------

def _solve_mcq_from_image(question_img: Image.Image, num_options: int) -> int | None:
    """Send *question_img* directly to Gemini — no disk round-trip."""
    try:
        prompt = (
            f"Analyze the multiple-choice question in the image carefully.\n"
            f"There are {num_options} options listed.\n"
            "Identify the correct answer based on your knowledge.\n"
            f"Your task is to return ONLY the index number (1, 2, ..., {num_options}) "
            "corresponding to the correct option.\n"
            "Output format: Just the integer number. No text, no explanation, no punctuation."
        )
        response = generate_content_with_fallback([prompt, question_img])
        index = int(response.text.strip())
        if 1 <= index <= num_options:
            return index
        logger.error(f"❌ Invalid option index from Gemini: {index}")
        return None
    except Exception as e:
        logger.error(f"❌ Gemini error (no-context MCQ): {e}")
        return None


def _solve_mcq_with_context_from_image(
    context_img: Image.Image,
    question_img: Image.Image,
    num_options: int,
) -> int | None:
    """Send context + question images directly to Gemini — no disk round-trip."""
    try:
        prompt = (
            "Analyze the provided context (first image) and the multiple-choice question "
            "(second image) carefully.\n"
            f"There are {num_options} options listed in the question image.\n"
            "Identify the correct answer based on the context provided.\n"
            f"Your task is to return ONLY the index number (1, 2, ..., {num_options}) "
            "corresponding to the correct option.\n"
            "Output format: Just the integer number. No text, no explanation, no punctuation."
        )
        response = generate_content_with_fallback([prompt, context_img, question_img])
        index = int(response.text.strip())
        if 1 <= index <= num_options:
            return index
        logger.error(f"❌ Invalid option index from Gemini: {index}")
        return None
    except Exception as e:
        logger.error(f"❌ Gemini error (with-context MCQ): {e}")
        return None


# ---------------------------------------------------------------------------
# Context capture
# ---------------------------------------------------------------------------

def capture_context() -> None:
    """
    Captures context passage region and saves it.
    Triggered by Ctrl+Alt+C.
    """
    logger.info("📖 CAPTURE CONTEXT: Please click TOP-LEFT of context region...")
    top_left = capture_single_click()
    if not top_left:
        logger.error("❌ Context capture cancelled.")
        return

    logger.info("MouseClicked Please click BOTTOM-RIGHT of context region...")
    bottom_right = capture_single_click()
    if not bottom_right:
        logger.error("❌ Context capture cancelled.")
        return

    x1, y1 = top_left
    x2, y2 = bottom_right
    width = x2 - x1
    height = y2 - y1

    if width <= 0 or height <= 0:
        logger.error("❌ Invalid context region.")
        return

    try:
        screenshot = pyautogui.screenshot(region=(x1, y1, width, height))
        screenshot.save(config.CONTEXT_IMAGE_PATH)
        logger.info(f"✅ Context saved to {config.CONTEXT_IMAGE_PATH}")
        state.context_captured = True
        logger.info("✅ Context is now ACTIVE. Next MCQ will include it.")
    except Exception as e:
        logger.error(f"❌ Failed to save context: {e}")


# ---------------------------------------------------------------------------
# MCQ solve
# ---------------------------------------------------------------------------

def solve_current_mcq() -> None:
    """
    Captures MCQ question, sends to AI in background, and immediately starts capturing option positions.
    Auto-clicks once both AI response and option positions are ready.
    Works with any number of options.
    """
    # Reset events and globals
    state.ai_response_ready.clear()
    state.option_positions_ready.clear()
    state.set_mcq_result(None, None)

    # --- Capture Question Region ---
    logger.info("❓ CAPTURE QUESTION: Please click TOP-LEFT of question region...")
    top_left = capture_single_click()
    if not top_left:
        logger.error("❌ Question capture cancelled.")
        return

    logger.info("MouseClicked Please click BOTTOM-RIGHT of question region...")
    bottom_right = capture_single_click()
    if not bottom_right:
        logger.error("❌ Question capture cancelled.")
        return

    x1, y1 = top_left
    x2, y2 = bottom_right
    width = x2 - x1
    height = y2 - y1

    if width <= 0 or height <= 0:
        logger.error("❌ Invalid question region.")
        return

    try:
        # Keep the screenshot in memory — save to disk only for persistence/debugging,
        # but pass the PIL object directly to Gemini (no re-open from disk needed).
        question_screenshot = pyautogui.screenshot(region=(x1, y1, width, height))
        question_screenshot.save(config.QUESTION_IMAGE_PATH)
        # Compress for Gemini — reduces token cost by 60-80%
        question_screenshot = compress_for_api(question_screenshot)
        logger.info(f"✅ Question saved to {config.QUESTION_IMAGE_PATH}")
    except Exception as e:
        logger.error(f"❌ Failed to save question: {e}")
        return

    # --- Capture ALL Option Positions (any number) ---
    logger.info("\n" + "🟩" * 50)
    logger.info("MouseClicked Now click each option in order (click ALL options, then press Enter when done)")
    logger.info("🟩" * 50)

    option_positions = []
    done = threading.Event()

    def on_click(x, y, button, pressed):
        if pressed and button == mouse.Button.left:
            option_positions.append((x, y))
            logger.info(f"✅ Option {len(option_positions)} position recorded at ({x}, {y})")
        return True

    def on_key_press(key):
        if key == keyboard.Key.enter:
            done.set()
            return False  # Stop listener
        return True

    # Start mouse and keyboard listeners
    mouse_listener = mouse.Listener(on_click=on_click)
    keyboard_listener = keyboard.Listener(on_press=on_key_press)

    mouse_listener.start()
    keyboard_listener.start()

    logger.info("MouseClicked Click all options, then press Enter to continue...")
    done.wait(timeout=120)  # Wait up to 120 seconds

    # Clean up listeners
    mouse_listener.stop()
    keyboard_listener.stop()

    num_options = len(option_positions)
    if num_options < 2:
        logger.error(f"❌ Only {num_options} options captured. Need at least 2 options.")
        return

    logger.info(f"✅ Captured {num_options} options total")

    # Store option positions atomically via the thread-safe helper
    with state.mcq_result_lock:
        state.option_positions_global = option_positions
    state.option_positions_ready.set()

    # --- Start AI Request in Background Thread ---
    # Capture context image in-memory now (if needed) so the AI thread
    # doesn't need to open any files from disk at all.
    context_img: Image.Image | None = None
    if state.context_captured:
        try:
            context_img = compress_for_api(Image.open(config.CONTEXT_IMAGE_PATH))
        except Exception as e:
            logger.error(f"❌ Failed to load context image: {e}")

    def ai_worker():
        logger.info(f"🧠 Sending to Gemini (MCQ has {num_options} options)...")
        try:
            if context_img is not None:
                logger.info(f"📎 Including context... (MCQ has {num_options} options)")
                result = _solve_mcq_with_context_from_image(
                    context_img,
                    question_screenshot,   # in-memory PIL Image — no disk read
                    num_options,
                )
            else:
                logger.info(f"📎 NO context — sending question only... (MCQ has {num_options} options)")
                result = _solve_mcq_from_image(
                    question_screenshot,   # in-memory PIL Image — no disk read
                    num_options,
                )

            # Write result atomically
            with state.mcq_result_lock:
                state.correct_index_global = result

            if result is None:
                logger.error("❌ Failed to get answer from Gemini.")
            else:
                logger.info(f"✅ AI says correct option is: {result}")
        except Exception as e:
            logger.error(f"❌ Error with Gemini: {e}")
        finally:
            state.ai_response_ready.set()

    threading.Thread(target=ai_worker, daemon=True).start()

    # --- Wait for AI response ---
    logger.info("⏳ Waiting for AI response...")
    state.ai_response_ready.wait()

    # --- Read result atomically then validate ---
    correct_index, positions = state.get_mcq_result()

    if correct_index is None:
        logger.error("❌ No valid AI response received.")
        return

    if correct_index < 1 or correct_index > num_options:
        logger.error(f"❌ Invalid option index: {correct_index} (should be between 1 and {num_options})")
        return

    # --- Click Correct Option ---
    logger.info("MouseClicked clicking correct option...")
    try:
        screen_x, screen_y = positions[correct_index - 1]
        pyautogui.moveTo(screen_x, screen_y, duration=0.3)
        pyautogui.click()
        logger.info(f"✅ Clicked option {correct_index} at ({screen_x}, {screen_y})")
        logger.info("🎉 Done! Question answered.")
    except Exception as e:
        logger.error(f"❌ Click failed: {e}")