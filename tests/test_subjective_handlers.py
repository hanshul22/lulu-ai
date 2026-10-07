"""Tests for routing logic in src/subjective_handlers.generate_ai_response()."""
import sys
import os
import unittest
from unittest.mock import MagicMock, patch, call
import threading

# ---------------------------------------------------------------------------
# Add src to path and stub out GUI/system modules before any src imports
# ---------------------------------------------------------------------------
SRC = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'src'))
sys.path.insert(0, SRC)

# Stub heavy / GUI dependencies so they don't crash in headless test env
for _mod in ('pyautogui', 'explanation_window', 'pynput', 'pynput.keyboard',
             'pynput.mouse', 'tkinter', 'win32gui', 'win32con', 'win32api'):
    sys.modules.setdefault(_mod, MagicMock())

import state  # real state module

# Now safe to import subjective_handlers
from subjective_handlers import (
    generate_ai_response,
    retry_ai_response,
    generate_code_explanation,
    generate_step_by_step_response,
)


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def _make_text_response(text: str) -> MagicMock:
    r = MagicMock()
    r.text = text
    return r


def _run_synchronously(target_fn):
    """Run target_fn synchronously in the current thread (no daemon thread)."""
    target_fn()


class TestGenerateAiResponseRouting(unittest.TestCase):
    """Verify that generate_ai_response routes SQL/DSA to generate_code_answer
    and Non-Coding to generate_content_with_fallback."""

    def setUp(self):
        # Give the handler a fake screenshot so it doesn't bail out early
        state.subjective_screenshots = ["fake/1.png"]
        state.screenshots_count_at_generation = 0
        state.ai_response_text = None
        state.ai_response_ready_subjective.clear()

    def _run_and_wait(self) -> None:
        """Start generate_ai_response synchronously by making Thread.start() run inline."""
        generate_ai_response()
        # The background thread is patched to run synchronously, so by the time
        # generate_ai_response() returns, the worker has already completed.

    # ------------------------------------------------------------------
    # SQL classification → generate_code_answer() is called
    # ------------------------------------------------------------------

    @patch('ai_core.generate_code_answer', return_value="SELECT * FROM t;")
    @patch('subjective_handlers.generate_content_with_fallback')
    @patch('subjective_handlers.Image.open')
    @patch('subjective_handlers.threading.Thread')
    def test_sql_classification_calls_generate_code_answer(
        self, mock_thread_cls, mock_img_open, mock_fallback, mock_code_answer
    ):
        # Make Thread.start() run the target synchronously
        def run_sync(**kwargs):
            t = MagicMock()
            t.start.side_effect = lambda: kwargs.get('target', lambda: None)()
            return t
        mock_thread_cls.side_effect = lambda target, daemon=True: (
            type('T', (), {'start': lambda self: target()})()
        )

        mock_fallback.return_value = _make_text_response("sql")
        mock_img_open.return_value = MagicMock()

        generate_ai_response()

        mock_code_answer.assert_called_once()
        # generate_content_with_fallback called ONLY ONCE (for classification)
        self.assertEqual(mock_fallback.call_count, 1)
        self.assertEqual(state.ai_response_text, "SELECT * FROM t;")

    # ------------------------------------------------------------------
    # DSA classification → generate_code_answer() is called
    # ------------------------------------------------------------------

    @patch('ai_core.generate_code_answer', return_value="def solve(): pass")
    @patch('subjective_handlers.generate_content_with_fallback')
    @patch('subjective_handlers.Image.open')
    @patch('subjective_handlers.threading.Thread')
    def test_dsa_classification_calls_generate_code_answer(
        self, mock_thread_cls, mock_img_open, mock_fallback, mock_code_answer
    ):
        mock_thread_cls.side_effect = lambda target, daemon=True: (
            type('T', (), {'start': lambda self: target()})()
        )
        mock_fallback.return_value = _make_text_response("dsa")
        mock_img_open.return_value = MagicMock()

        generate_ai_response()

        mock_code_answer.assert_called_once()
        self.assertEqual(mock_fallback.call_count, 1)
        self.assertEqual(state.ai_response_text, "def solve(): pass")

    # ------------------------------------------------------------------
    # Non-Coding classification → generate_code_answer() is NOT called
    # ------------------------------------------------------------------

    @patch('ai_core.generate_code_answer')
    @patch('ai_core.generate_theory_answer', return_value="Photosynthesis is the process...")
    @patch('subjective_handlers.generate_content_with_fallback')
    @patch('subjective_handlers.Image.open')
    @patch('subjective_handlers.threading.Thread')
    def test_non_coding_does_not_call_generate_code_answer(
        self, mock_thread_cls, mock_img_open, mock_fallback, mock_theory_answer, mock_code_answer
    ):
        mock_thread_cls.side_effect = lambda target, daemon=True: (
            type('T', (), {'start': lambda self: target()})()
        )
        # Two Gemini calls: classification → "non-coding", then text extraction
        mock_fallback.side_effect = [
            _make_text_response("non-coding"),
            _make_text_response("What is photosynthesis?"),  # extracted question text
        ]
        mock_img_open.return_value = MagicMock()

        generate_ai_response()

        mock_code_answer.assert_not_called()
        # generate_content_with_fallback called twice (classify + extract)
        self.assertEqual(mock_fallback.call_count, 2)
        # Groq-backed theory answer is called with the combined prompt + question
        mock_theory_answer.assert_called_once()
        self.assertIn("What is photosynthesis?", mock_theory_answer.call_args[0][0])
        self.assertEqual(state.ai_response_text, "Photosynthesis is the process...")

    # ------------------------------------------------------------------
    # Error in generate_code_answer → state text is None, no crash
    # ------------------------------------------------------------------

    @patch('ai_core.generate_code_answer', side_effect=Exception("OpenRouter down"))
    @patch('subjective_handlers.generate_content_with_fallback')
    @patch('subjective_handlers.Image.open')
    @patch('subjective_handlers.threading.Thread')
    def test_code_answer_error_sets_state_none(
        self, mock_thread_cls, mock_img_open, mock_fallback, mock_code_answer
    ):
        mock_thread_cls.side_effect = lambda target, daemon=True: (
            type('T', (), {'start': lambda self: target()})()
        )
        mock_fallback.return_value = _make_text_response("sql")
        mock_img_open.return_value = MagicMock()

        generate_ai_response()

        self.assertIsNone(state.ai_response_text)

    # ------------------------------------------------------------------
    # No screenshots → returns early without calling anything
    # ------------------------------------------------------------------

    @patch('ai_core.generate_code_answer')
    @patch('subjective_handlers.generate_content_with_fallback')
    def test_no_screenshots_returns_early(self, mock_fallback, mock_code_answer):
        state.subjective_screenshots = []

        generate_ai_response()

        mock_code_answer.assert_not_called()
        mock_fallback.assert_not_called()


# ---------------------------------------------------------------------------
# Tests for retry_ai_response
# ---------------------------------------------------------------------------

class TestRetryAiResponse(unittest.TestCase):

    def setUp(self):
        state.subjective_screenshots = ["fake/1.png"]
        state.screenshots_count_at_generation = 0
        state.ai_response_text = "def broken(): pass"
        state.ai_response_ready_subjective.clear()

    @patch('ai_core.generate_code_answer', return_value="def fixed(): pass")
    @patch('subjective_handlers.generate_content_with_fallback')
    @patch('subjective_handlers.Image.open')
    @patch('subjective_handlers.threading.Thread')
    def test_happy_path_calls_gemini_extract_then_code_answer(
        self, mock_thread_cls, mock_img_open, mock_fallback, mock_code_answer
    ):
        mock_thread_cls.side_effect = lambda target, daemon=True: (
            type('T', (), {'start': lambda self: target()})()
        )
        mock_fallback.return_value = _make_text_response("NameError: name 'x' is not defined")
        mock_img_open.return_value = MagicMock()

        retry_ai_response()

        # Gemini called once for extraction step
        self.assertEqual(mock_fallback.call_count, 1)
        # generate_code_answer called once with a prompt mentioning the extracted error
        mock_code_answer.assert_called_once()
        prompt_used = mock_code_answer.call_args[0][0]
        self.assertIn("NameError", prompt_used)
        self.assertIn("def broken(): pass", prompt_used)
        # State updated with the fix
        self.assertEqual(state.ai_response_text, "def fixed(): pass")

    @patch('ai_core.generate_code_answer')
    @patch('subjective_handlers.generate_content_with_fallback')
    def test_no_previous_response_returns_early(self, mock_fallback, mock_code_answer):
        state.ai_response_text = None

        retry_ai_response()

        mock_code_answer.assert_not_called()
        mock_fallback.assert_not_called()

    @patch('ai_core.generate_code_answer')
    @patch('subjective_handlers.generate_content_with_fallback')
    def test_no_screenshots_returns_early(self, mock_fallback, mock_code_answer):
        state.subjective_screenshots = []

        retry_ai_response()

        mock_code_answer.assert_not_called()
        mock_fallback.assert_not_called()


# ---------------------------------------------------------------------------
# Tests for generate_code_explanation
# ---------------------------------------------------------------------------

class TestGenerateCodeExplanation(unittest.TestCase):

    def setUp(self):
        state.ai_response_text = "def foo(): return 42"

    @patch('ai_core.explain_code', return_value="This function returns 42.")
    @patch('subjective_handlers.threading.Thread')
    def test_routes_to_ai_core_explain_code(self, mock_thread_cls, mock_explain):
        mock_thread_cls.side_effect = lambda target, daemon=True: (
            type('T', (), {'start': lambda self: target()})()
        )

        generate_code_explanation()

        mock_explain.assert_called_once_with(state.ai_response_text, extra_context=None)


# ---------------------------------------------------------------------------
# Tests for generate_step_by_step_response
# ---------------------------------------------------------------------------

class TestGenerateStepByStep(unittest.TestCase):

    def setUp(self):
        state.subjective_screenshots = ["fake/q.png"]
        state.ai_response_ready_subjective.clear()

    @patch('ai_core.generate_theory_answer', return_value="Step 1: ...")
    @patch('subjective_handlers.generate_content_with_fallback')
    @patch('subjective_handlers.Image.open')
    @patch('subjective_handlers.threading.Thread')
    @patch('subjective_handlers.config.USE_GROQ_FOR_EXPLANATION', True)
    @patch('subjective_handlers.config.GROQ_API_KEY', 'groq-key')
    def test_groq_enabled_uses_two_step_extract_then_theory(
        self, mock_thread_cls, mock_img_open, mock_fallback, mock_theory
    ):
        mock_thread_cls.side_effect = lambda target, daemon=True: (
            type('T', (), {'start': lambda self: target()})()
        )
        mock_fallback.return_value = _make_text_response("What is recursion?")
        mock_img_open.return_value = MagicMock()

        generate_step_by_step_response()

        # Gemini called once for extraction
        self.assertEqual(mock_fallback.call_count, 1)
        # generate_theory_answer called with combined prompt containing extracted question
        mock_theory.assert_called_once()
        combined = mock_theory.call_args[0][0]
        self.assertIn("What is recursion?", combined)

    @patch('ai_core.generate_theory_answer')
    @patch('subjective_handlers.generate_content_with_fallback')
    @patch('subjective_handlers.Image.open')
    @patch('subjective_handlers.threading.Thread')
    @patch('subjective_handlers.config.USE_GROQ_FOR_EXPLANATION', False)
    @patch('subjective_handlers.config.GROQ_API_KEY', 'groq-key')
    def test_groq_disabled_falls_back_to_gemini_with_images(
        self, mock_thread_cls, mock_img_open, mock_fallback, mock_theory
    ):
        mock_thread_cls.side_effect = lambda target, daemon=True: (
            type('T', (), {'start': lambda self: target()})()
        )
        mock_fallback.return_value = _make_text_response("Step-by-step answer from Gemini.")
        mock_img_open.return_value = MagicMock()

        generate_step_by_step_response()

        # Gemini called once (single direct call with images)
        self.assertEqual(mock_fallback.call_count, 1)
        # generate_theory_answer NOT called
        mock_theory.assert_not_called()

    @patch('ai_core.generate_theory_answer')
    @patch('subjective_handlers.generate_content_with_fallback')
    def test_no_screenshots_returns_early(self, mock_fallback, mock_theory):
        state.subjective_screenshots = []

        generate_step_by_step_response()

        mock_fallback.assert_not_called()
        mock_theory.assert_not_called()


if __name__ == '__main__':
    unittest.main()

