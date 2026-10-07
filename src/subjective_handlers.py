import hashlib
import threading
import os
import re
import pyautogui
from PIL import Image
import config
import state
from logger_setup import logger
from utils import capture_single_click, compress_for_api, compress_for_classification
from ai_core import generate_content_with_fallback, generate_content_with_model
import ai_core
import explanation_window
import prompts


# ---------------------------------------------------------------------------
# Image cache — avoids re-opening the same files from disk on every AI call
# ---------------------------------------------------------------------------

_cached_image_paths: list[str] = []
_cached_images: list[Image.Image] = []


def _get_images(paths: list[str]) -> list[Image.Image]:
    """Return compressed PIL Image objects for *paths*, re-using the cache when unchanged.

    Token optimisation: compress_for_api() resizes to 1280 px wide and
    re-encodes as JPEG — typically 60–80% smaller than raw PNG screenshots,
    which directly reduces Gemini vision token cost.
    """
    global _cached_image_paths, _cached_images
    if paths != _cached_image_paths:
        _cached_images = [compress_for_api(Image.open(p)) for p in paths]
        _cached_image_paths = list(paths)
    return _cached_images


# Lower-quality image cache used ONLY for classification (Opt #5).
# Classification just needs to tell code from text — fine details don't matter.
_cached_cls_image_paths: list[str] = []
_cached_cls_images: list[Image.Image] = []


def _get_classification_images(paths: list[str]) -> list[Image.Image]:
    """Return aggressively compressed images for the classification step only.

    Uses 800 px / quality 50 — roughly 85-90% smaller than raw PNGs.
    """
    global _cached_cls_image_paths, _cached_cls_images
    if paths != _cached_cls_image_paths:
        _cached_cls_images = [compress_for_classification(Image.open(p)) for p in paths]
        _cached_cls_image_paths = list(paths)
    return _cached_cls_images


def _compute_response_hash(paths: list[str]) -> str:
    """Compute a stable hash over screenshot file sizes + modification times.

    This is used for Opt #4 (response caching): if the user presses
    Ctrl+Alt+G again on the exact same screenshots, we serve the cached
    response instantly (zero API calls).

    We hash (path, size, mtime) tuples — fast and avoids reading multi-MB
    files into memory just for the hash. A screenshot that changes on disk
    gets a new mtime, so the hash changes and the cache misses correctly.
    """
    h = hashlib.sha256()
    h.update(config.MODEL_NAME.encode())
    h.update(config.CLASSIFICATION_MODEL.encode())
    for p in sorted(paths):
        try:
            st = os.stat(p)
            h.update(f"{p}|{st.st_size}|{st.st_mtime_ns}".encode())
        except OSError:
            h.update(p.encode())
    return h.hexdigest()[:16]


def clear_image_cache() -> None:
    """Clear all in-memory image caches.

    Must be called whenever the user clears context (Ctrl+Alt+R) so that
    new screenshots for the next question are always re-loaded from disk.
    """
    global _cached_image_paths, _cached_images
    global _cached_cls_image_paths, _cached_cls_images
    _cached_image_paths = []
    _cached_images = []
    _cached_cls_image_paths = []
    _cached_cls_images = []
    logger.info("🧹 Image cache cleared.")


# ---------------------------------------------------------------------------
# FIX #6 — Concurrent generate guard
#
# Without this lock, pressing Ctrl+Alt+G twice quickly spawns two ai_worker
# threads simultaneously. The second thread overwrites state.ai_response_text
# and all caches while the first thread is still using them, producing a
# corrupted or double-generated response.
# ---------------------------------------------------------------------------

_generate_lock = threading.Lock()
_is_generating  = False


# ---------------------------------------------------------------------------
# Screenshot capture
# ---------------------------------------------------------------------------

# Maximum number of screenshots allowed in a single session.
MAX_SCREENSHOTS = 20


def capture_subjective_screenshot() -> None:
    """
    Captures a screenshot for coding/subjective question.
    Triggered by Ctrl+Alt+S.
    Can be called multiple times — stores screenshots in order.
    Capped at MAX_SCREENSHOTS per session to prevent unbounded memory growth.
    """
    if len(state.subjective_screenshots) >= MAX_SCREENSHOTS:
        logger.warning(
            f"⚠️ Maximum of {MAX_SCREENSHOTS} screenshots reached for this session. "
            f"Press Ctrl+Alt+R to clear and start a new session."
        )
        return

    logger.info("🖼️  CAPTURE SUBJECTIVE SCREENSHOT: Please click TOP-LEFT...")
    top_left = capture_single_click()
    if not top_left:
        logger.error("❌ Capture cancelled.")
        return

    logger.info("MouseClicked Please click BOTTOM-RIGHT...")
    bottom_right = capture_single_click()
    if not bottom_right:
        logger.error("❌ Capture cancelled.")
        return

    x1, y1 = top_left
    x2, y2 = bottom_right
    width  = x2 - x1
    height = y2 - y1

    if width <= 0 or height <= 0:
        logger.error("❌ Invalid region.")
        return

    try:
        idx      = len(state.subjective_screenshots) + 1
        filename = f"{idx}.png"
        filepath = os.path.join(config.SUBJECTIVE_SCREENSHOT_DIR, filename)

        screenshot = pyautogui.screenshot(region=(x1, y1, width, height))
        screenshot.save(filepath)
        state.subjective_screenshots.append(filepath)

        logger.info(f"✅ Saved screenshot {idx} to {filepath}")
        logger.info(f"📊 Total screenshots captured: {len(state.subjective_screenshots)}")
    except Exception as e:
        logger.error(f"❌ Failed to save screenshot: {e}")


# ---------------------------------------------------------------------------
# AI response generation
# ---------------------------------------------------------------------------

def generate_ai_response() -> None:
    """
    Sends all captured subjective screenshots to the AI and stores the response.
    Runs in background — doesn't block the hotkey system.
    """
    global _is_generating

    if not state.subjective_screenshots:
        logger.error("❌ No screenshots captured. Press Ctrl+Alt+S first.")
        return

    # FIX #6 — Block a second concurrent generation.
    # Use a non-blocking acquire so the hotkey thread never hangs.
    with _generate_lock:
        if _is_generating:
            logger.warning("⚠️ AI is already generating a response. Please wait.")
            return
        _is_generating = True

    # Record how many screenshots exist now so any future ones are treated as errors.
    state.screenshots_count_at_generation = len(state.subjective_screenshots)
    logger.info(f"🧠 Sending {len(state.subjective_screenshots)} screenshots to AI...")

    state.ai_response_ready_subjective.clear()

    def ai_worker():
        global _is_generating
        try:
            images        = _get_images(state.subjective_screenshots)
            current_count = len(state.subjective_screenshots)

            # ── OPT #4: Response hash cache ───────────────────────────────
            # If user presses Ctrl+Alt+G again on identical screenshots,
            # serve the cached response instantly (zero API calls).
            response_hash = _compute_response_hash(state.subjective_screenshots)
            if (state.cached_response_hash == response_hash
                    and state.cached_response_text is not None):
                logger.info(f"♻️ Identical screenshots detected (hash={response_hash}). Serving cached response.")
                state.set_ai_response(state.cached_response_text)
                logger.info(f"✅ Cached response ({len(state.cached_response_text)} chars). Press Ctrl+Alt+T to type.")
                return

            # ── STEP 1: Classify Question Type ────────────────────────────
            # OPT #1: Reuse cached classification when screenshot count unchanged
            if state.cached_question_type and state.cached_question_type_count == current_count:
                question_type = state.cached_question_type
                logger.info(f"♻️ Reusing cached question type: {question_type.upper()}")
            else:
                logger.info("🔍 Classifying question type...")
                try:
                    # OPT #5: Use aggressively compressed images for classification
                    cls_images = _get_classification_images(state.subjective_screenshots)
                    # OPT #3: Use cheaper model for classification
                    classification_response = generate_content_with_model(
                        [prompts.CLASSIFICATION_PROMPT] + cls_images,
                        model=config.CLASSIFICATION_MODEL,
                    )
                    question_type = classification_response.text.strip().lower()
                except Exception as cls_err:
                    logger.warning(
                        f"⚠️ Classification failed ({type(cls_err).__name__}: {cls_err}). "
                        f"Defaulting to 'non-coding'."
                    )
                    question_type = "non-coding"

            if 'sql' in question_type:
                question_type = 'sql'
            elif 'non-coding' in question_type:
                question_type = 'non-coding'
            elif 'dsa' in question_type or 'coding' in question_type:
                question_type = 'dsa'
            else:
                question_type = 'non-coding'

            logger.info(f"✅ Question classified as: {question_type.upper()}")
            state.cached_question_type       = question_type
            state.cached_question_type_count = current_count

            # ── STEP 2: Select prompt ─────────────────────────────────────
            if question_type == 'dsa':
                prompt = prompts.DSA_CODING_PROMPT
            elif question_type == 'sql':
                prompt = prompts.SQL_PROMPT
            else:
                prompt = prompts.NON_CODING_PROMPT

            # ── STEP 3: Generate response ─────────────────────────────────
            logger.info(f"🧠 Generating answer using {question_type.upper()} prompt...")

            # ── OPT #2: Detect Gemini-only path ──────────────────────────
            # When neither Groq nor OpenRouter is configured, the current
            # flow does: Gemini-extract-text → Gemini-generate-answer (2 calls).
            # In Gemini-only mode we skip the extraction and send images +
            # prompt directly to Gemini in a SINGLE call — halving the cost.
            gemini_only_for_code = not (config.USE_GROQ_FOR_CODE and config.GROQ_API_KEY) and \
                                   not (config.USE_OPENROUTER_FOR_CODE and config.OPENROUTER_API_KEY)
            gemini_only_for_theory = not (config.USE_GROQ_FOR_EXPLANATION and config.GROQ_API_KEY)

            if question_type in ('dsa', 'sql'):
                if gemini_only_for_code:
                    # SINGLE-CALL: send images + prompt directly to Gemini
                    logger.info("⚡ Gemini-only mode: single-call with images (skipping extraction)")
                    response = generate_content_with_fallback([prompt] + images)
                    raw_response = response.text
                else:
                    # MULTI-CALL: extract text → route to Groq/OpenRouter
                    if (state.cached_coding_sql_question_text
                            and state.cached_coding_sql_question_text_count == current_count):
                        question_text = state.cached_coding_sql_question_text
                        logger.info(f"♻️ Reusing cached coding/SQL extraction ({len(question_text)} chars).")
                    else:
                        logger.info("📷 Extracting coding/SQL question text from screenshots (Gemini)...")
                        extracted     = generate_content_with_fallback(
                            [prompts.CODING_SQL_EXTRACT_PROMPT] + images
                        )
                        question_text = extracted.text.strip()
                        state.cached_coding_sql_question_text       = question_text
                        state.cached_coding_sql_question_text_count = current_count

                    if question_text:
                        logger.info(f"📝 Extracted ({len(question_text)} chars), routing to code generator...")
                        full_prompt  = prompt + "\n\nQuestion/Template:\n" + question_text
                        raw_response = ai_core.generate_code_answer(full_prompt)
                    else:
                        logger.warning("⚠️ Extraction returned empty text. Using instruction-only prompt.")
                        raw_response = ai_core.generate_code_answer(prompt)

            else:
                # non-coding
                if gemini_only_for_theory:
                    # SINGLE-CALL: send images + prompt directly to Gemini
                    logger.info("⚡ Gemini-only mode: single-call with images (skipping extraction)")
                    response = generate_content_with_fallback([prompt] + images)
                    raw_response = response.text
                else:
                    # MULTI-CALL: extract text → route to Groq
                    if (state.cached_non_coding_question_text
                            and state.cached_non_coding_question_text_count == current_count):
                        question_text = state.cached_non_coding_question_text
                        logger.info(f"♻️ Reusing cached non-coding extraction ({len(question_text)} chars).")
                    else:
                        logger.info("📷 Extracting question text from screenshots (Gemini)...")
                        extracted     = generate_content_with_fallback(
                            [prompts.NON_CODING_EXTRACT_PROMPT] + images
                        )
                        question_text = extracted.text.strip()
                        state.cached_non_coding_question_text       = question_text
                        state.cached_non_coding_question_text_count = current_count

                    logger.info(f"📝 Extracted ({len(question_text)} chars), routing to theory generator...")
                    full_prompt  = prompt + "\n\nQuestion:\n" + question_text
                    raw_response = ai_core.generate_theory_answer(full_prompt)

            raw_response = raw_response.strip()

            # Clean trailing whitespace and collapse excessive blank lines.
            cleaned_response = re.sub(r'\s+$', '', raw_response, flags=re.MULTILINE)
            cleaned_response = re.sub(r'\n{2,}', '\n', cleaned_response)

            state.set_ai_response(cleaned_response)

            # ── OPT #4: Store in response hash cache ─────────────────────
            state.cached_response_hash = response_hash
            state.cached_response_text = cleaned_response

            logger.info("✅ AI Response Received:")
            logger.info("=" * 50)
            logger.info("FULL AI RESPONSE:")
            logger.info("-" * 50)
            logger.info(cleaned_response)
            logger.info("-" * 50)
            logger.info(f"Response length: {len(cleaned_response)} characters")
            logger.info("=" * 50)
            logger.info("✅ Press Ctrl+Alt+T to auto-type this response.")

        except Exception as e:
            logger.error(f"❌ Error generating AI response: {e}")
            state.set_ai_response(None)
        finally:
            state.subjective_question_answered = True
            state.ai_response_ready_subjective.set()
            # FIX #6 — Always release the guard so the next call can proceed.
            with _generate_lock:
                _is_generating = False

    threading.Thread(target=ai_worker, daemon=True).start()
    logger.info("⏳ AI is working... You can press Ctrl+Alt+T later when ready.")


# ---------------------------------------------------------------------------
# Retry
# ---------------------------------------------------------------------------

def retry_ai_response() -> None:
    """
    Retries the AI response by sending the previous answer + latest error screenshot(s).
    """
    if not state.ai_response_text:
        logger.error("❌ No previous AI response found to retry.")
        return

    if not state.subjective_screenshots:
        logger.error("❌ No screenshots found. Capture the error using Ctrl+Alt+S.")
        return

    # Identify error screenshots: anything captured AFTER the last generation
    if len(state.subjective_screenshots) > state.screenshots_count_at_generation:
        error_paths = state.subjective_screenshots[state.screenshots_count_at_generation:]
        logger.info(f"🔄 Detected {len(error_paths)} new error screenshot(s).")
    else:
        error_paths = [state.subjective_screenshots[-1]]
        logger.info("🔄 No new screenshots since generation. Using the last one as error.")

    logger.info(f"📤 Sending previous response + {len(error_paths)} error screenshot(s) to AI...")

    state.ai_response_ready_subjective.clear()

    def ai_worker():
        try:
            # Compress error images for token savings
            error_images = [compress_for_api(Image.open(p)) for p in error_paths]

            logger.info("📷 Extracting error from screenshots (Gemini)...")
            extracted         = generate_content_with_fallback(
                [prompts.RETRY_ERROR_EXTRACT_PROMPT] + error_images
            )
            error_description = extracted.text.strip()
            logger.info(f"📝 Extracted error ({len(error_description)} chars), routing fix to code generator...")

            fix_prompt   = prompts.build_retry_fix_prompt(state.ai_response_text, error_description)
            raw_response = ai_core.generate_code_answer(fix_prompt)
            raw_response = raw_response.strip()

            cleaned_response = re.sub(r'\s+$', '', raw_response, flags=re.MULTILINE)
            cleaned_response = re.sub(r'\n{2,}', '\n', cleaned_response)

            state.set_ai_response(cleaned_response)

            # FIX #7 — Update the generation count so a SECOND retry correctly
            # identifies only the screenshots captured after THIS retry, not
            # all screenshots since the original generation.
            state.screenshots_count_at_generation = len(state.subjective_screenshots)

            # Invalidate response hash cache — the code changed, so
            # pressing Ctrl+Alt+G next time must NOT serve old cache.
            state.cached_response_hash = None
            state.cached_response_text = None

            logger.info("✅ AI Retry Response Received:")
            logger.info("=" * 50)
            logger.info(cleaned_response)
            logger.info("=" * 50)
            logger.info("✅ Press Ctrl+Alt+T to auto-type this corrected response.")

        except Exception as e:
            logger.error(f"❌ Error with Retry: {e}")
        finally:
            state.subjective_question_answered = True
            state.ai_response_ready_subjective.set()

    threading.Thread(target=ai_worker, daemon=True).start()
    logger.info("⏳ AI is fixing the solution...")


# ---------------------------------------------------------------------------
# Code explanation
# ---------------------------------------------------------------------------

def generate_code_explanation() -> None:
    """
    Generates a summary, step-by-step approach, dry run, and complexity analysis.
    Triggered by Ctrl+Alt+J.
    """
    if not state.ai_response_text:
        logger.warning("⚠️ No code solution found to explain. Please generate a solution first.")
        # FIX #2 — show_explanation() already calls show_window() internally via
        # set_text(). Calling toggle_explanation() right after would see
        # is_visible=True and immediately hide the window. Use show_window() directly.
        explanation_window.show_explanation(
            "No code solution found to explain.\n"
            "Please generate a solution first using Ctrl+Alt+G."
        )
        explanation_window.show_window_direct()
        return

    logger.info("🧠 Generating code explanation...")
    explanation_window.show_explanation("Generating explanation... Please wait.")
    explanation_window.show_window_direct()

    def ai_worker():
        try:
            explanation_text = ai_core.explain_code(state.ai_response_text, extra_context=None)
            logger.info("✅ Explanation generated.")
            explanation_window.show_explanation(explanation_text)
        except Exception as e:
            logger.error(f"❌ Error generating explanation: {e}")
            explanation_window.show_explanation(f"Error generating explanation:\n{e}")

    threading.Thread(target=ai_worker, daemon=True).start()


# ---------------------------------------------------------------------------
# Step-by-step solution
# ---------------------------------------------------------------------------

def generate_step_by_step_response() -> None:
    """
    Generates a step-by-step solution for captured screenshots.
    Triggered by Ctrl+Alt+O.
    """
    if not state.subjective_screenshots:
        logger.error("❌ No screenshots captured. Press Ctrl+Alt+S first.")
        # FIX #2 — same toggle bug; use show_window_direct() instead.
        explanation_window.show_explanation(
            "No screenshots captured.\n"
            "Please capture the question first using Ctrl+Alt+S."
        )
        explanation_window.show_window_direct()
        return

    logger.info(f"🧠 Generating step-by-step solution for {len(state.subjective_screenshots)} screenshots...")
    explanation_window.show_explanation("Generating step-by-step solution... Please wait.")
    explanation_window.show_window_direct()

    def ai_worker():
        try:
            images = _get_images(state.subjective_screenshots)

            if config.USE_GROQ_FOR_EXPLANATION and config.GROQ_API_KEY:
                logger.info("📷 Extracting question text from screenshots (Gemini)...")
                extracted     = generate_content_with_fallback(
                    [prompts.STEP_BY_STEP_EXTRACT_PROMPT] + images
                )
                question_text = extracted.text.strip()
                logger.info(f"📝 Extracted question ({len(question_text)} chars), routing to theory generator...")
                full_prompt      = prompts.STEP_BY_STEP_PROMPT + "\n\nQuestion/Problem:\n" + question_text
                explanation_text = ai_core.generate_theory_answer(full_prompt)
            else:
                response         = generate_content_with_fallback([prompts.STEP_BY_STEP_PROMPT] + images)
                explanation_text = response.text.strip()

            logger.info("✅ Step-by-step solution generated.")
            explanation_window.show_explanation(explanation_text)

        except Exception as e:
            logger.error(f"❌ Error generating step-by-step solution: {e}")
            explanation_window.show_explanation(f"Error generating solution:\n{e}")
        finally:
            state.subjective_question_answered = True

    threading.Thread(target=ai_worker, daemon=True).start()