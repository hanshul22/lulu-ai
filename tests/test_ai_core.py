import unittest
from unittest.mock import MagicMock, patch
import sys
import os

# Add src to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'src')))

import ai_core
import config
from ai_core import AIProviderError, GeminiError

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

# Minimal valid PNG bytes (1x1 white pixel) – Image.open is mocked so the
# actual content does not matter; we just need non-empty bytes.
FAKE_IMAGE_BYTES = b'\x89PNG\r\n\x1a\n' + b'\x00' * 32


def _make_response(text: str) -> MagicMock:
    r = MagicMock()
    r.text = text
    return r


# ---------------------------------------------------------------------------
# Tests for solve_mcq_with_vision
# ---------------------------------------------------------------------------

class TestSolveMcqWithVision(unittest.TestCase):

    @patch('ai_core.generate_content_with_fallback')
    @patch('ai_core.Image.open')
    def test_happy_path_returns_correct_index(self, mock_image_open, mock_generate):
        mock_image_open.return_value = MagicMock()
        mock_generate.return_value = _make_response("3")

        result = ai_core.solve_mcq_with_vision(
            question_image=FAKE_IMAGE_BYTES,
            options_images=[FAKE_IMAGE_BYTES] * 4,
        )

        self.assertEqual(result, 3)
        mock_generate.assert_called_once()

    @patch('ai_core.generate_content_with_fallback')
    @patch('ai_core.Image.open')
    def test_with_context_image_included_in_parts(self, mock_image_open, mock_generate):
        mock_image_open.return_value = MagicMock()
        mock_generate.return_value = _make_response("1")

        result = ai_core.solve_mcq_with_vision(
            question_image=FAKE_IMAGE_BYTES,
            options_images=[FAKE_IMAGE_BYTES] * 3,
            context_image=FAKE_IMAGE_BYTES,
        )

        self.assertEqual(result, 1)
        # Image.open should have been called for context + question + 3 options = 5
        self.assertEqual(mock_image_open.call_count, 5)

    @patch('ai_core.generate_content_with_fallback')
    @patch('ai_core.Image.open')
    def test_out_of_range_index_raises_ai_error(self, mock_image_open, mock_generate):
        mock_image_open.return_value = MagicMock()
        mock_generate.return_value = _make_response("9")

        with self.assertRaises(AIProviderError):
            ai_core.solve_mcq_with_vision(
                question_image=FAKE_IMAGE_BYTES,
                options_images=[FAKE_IMAGE_BYTES] * 4,
            )

    @patch('ai_core.generate_content_with_fallback')
    @patch('ai_core.Image.open')
    def test_api_error_raises_ai_error(self, mock_image_open, mock_generate):
        mock_image_open.return_value = MagicMock()
        mock_generate.side_effect = Exception("503 Service Unavailable")

        with self.assertRaises(AIProviderError):
            ai_core.solve_mcq_with_vision(
                question_image=FAKE_IMAGE_BYTES,
                options_images=[FAKE_IMAGE_BYTES] * 4,
            )

    @patch('ai_core.generate_content_with_fallback')
    @patch('ai_core.Image.open')
    def test_non_integer_response_raises_ai_error(self, mock_image_open, mock_generate):
        mock_image_open.return_value = MagicMock()
        mock_generate.return_value = _make_response("option B")

        with self.assertRaises(AIProviderError):
            ai_core.solve_mcq_with_vision(
                question_image=FAKE_IMAGE_BYTES,
                options_images=[FAKE_IMAGE_BYTES] * 4,
            )


# ---------------------------------------------------------------------------
# Tests for generate_code_answer
# ---------------------------------------------------------------------------

class TestGenerateCodeAnswer(unittest.TestCase):

    @patch('ai_core.config.GROQ_API_KEY', '')        # disable Groq
    @patch('ai_core.config.OPENROUTER_API_KEY', '')  # force Gemini fallback path
    @patch('ai_core.generate_content_with_fallback')
    def test_happy_path_returns_text(self, mock_generate, *_):
        mock_generate.return_value = _make_response("def foo(): pass")

        result = ai_core.generate_code_answer("Write a foo function in Python")

        self.assertEqual(result, "def foo(): pass")
        mock_generate.assert_called_once()
        args, _ = mock_generate.call_args
        self.assertIn("Write a foo function in Python", args[0])

    @patch('ai_core.config.GROQ_API_KEY', '')        # disable Groq
    @patch('ai_core.config.OPENROUTER_API_KEY', '')  # force Gemini fallback path
    @patch('ai_core.generate_content_with_fallback')
    def test_api_error_raises_ai_error(self, mock_generate, *_):
        mock_generate.side_effect = Exception("quota exceeded")

        with self.assertRaises(AIProviderError) as ctx:
            ai_core.generate_code_answer("some prompt")

        self.assertIn("generate_code_answer failed", str(ctx.exception))


# ---------------------------------------------------------------------------
# Tests for generate_theory_answer
# ---------------------------------------------------------------------------

class TestGenerateTheoryAnswer(unittest.TestCase):

    @patch('ai_core.config.GROQ_API_KEY', '')  # force Gemini fallback path
    @patch('ai_core.generate_content_with_fallback')
    def test_happy_path_returns_text(self, mock_generate, *_):
        mock_generate.return_value = _make_response("Photosynthesis is the process...")

        result = ai_core.generate_theory_answer("Explain photosynthesis")

        self.assertEqual(result, "Photosynthesis is the process...")
        mock_generate.assert_called_once()

    @patch('ai_core.config.GROQ_API_KEY', '')  # force Gemini fallback path
    @patch('ai_core.generate_content_with_fallback')
    def test_api_error_raises_ai_error(self, mock_generate, *_):
        mock_generate.side_effect = RuntimeError("network error")

        with self.assertRaises(AIProviderError) as ctx:
            ai_core.generate_theory_answer("Explain something")

        self.assertIn("generate_theory_answer failed", str(ctx.exception))


# ---------------------------------------------------------------------------
# Tests for explain_code
# ---------------------------------------------------------------------------

class TestExplainCode(unittest.TestCase):

    @patch('ai_core.config.GROQ_API_KEY', '')  # force Gemini fallback path
    @patch('ai_core.generate_content_with_fallback')
    def test_happy_path_returns_explanation(self, mock_generate, *_):
        mock_generate.return_value = _make_response("This function sorts a list.")

        result = ai_core.explain_code("def sort(lst): return sorted(lst)")

        self.assertEqual(result, "This function sorts a list.")
        mock_generate.assert_called_once()
        args, _ = mock_generate.call_args
        self.assertIn("def sort(lst): return sorted(lst)", args[0][0])

    @patch('ai_core.config.GROQ_API_KEY', '')  # force Gemini fallback path
    @patch('ai_core.generate_content_with_fallback')
    def test_extra_context_included_in_prompt(self, mock_generate, *_):
        mock_generate.return_value = _make_response("Explanation with context.")

        ai_core.explain_code("x = 1", extra_context="This is a global counter.")

        args, _ = mock_generate.call_args
        prompt_text = args[0][0]
        self.assertIn("x = 1", prompt_text)
        self.assertIn("This is a global counter.", prompt_text)

    @patch('ai_core.config.GROQ_API_KEY', '')  # force Gemini fallback path
    @patch('ai_core.generate_content_with_fallback')
    def test_no_extra_context_omits_section(self, mock_generate, *_):
        mock_generate.return_value = _make_response("Simple explanation.")

        ai_core.explain_code("pass")

        args, _ = mock_generate.call_args
        prompt_text = args[0][0]
        self.assertNotIn("Additional context", prompt_text)

    @patch('ai_core.config.GROQ_API_KEY', '')  # force Gemini fallback path
    @patch('ai_core.generate_content_with_fallback')
    def test_api_error_raises_ai_error(self, mock_generate, *_):
        mock_generate.side_effect = Exception("rate limit 429")

        with self.assertRaises(AIProviderError) as ctx:
            ai_core.explain_code("import os")

        self.assertIn("explain_code failed", str(ctx.exception))


# ---------------------------------------------------------------------------
# Tests for _get_gemini_client helper
# ---------------------------------------------------------------------------

class TestGetGeminiClient(unittest.TestCase):

    @patch('ai_core.genai.GenerativeModel')
    @patch('ai_core.genai.configure')
    @patch('ai_core.config.API_KEY', 'test_key')
    @patch('ai_core.config.API_KEY_SECONDARY', '')
    @patch('ai_core.config.MODEL_NAME', 'gemini-2.5-flash')
    def test_returns_model_instance(self, mock_configure, mock_model_cls):
        fake_model = MagicMock()
        mock_model_cls.return_value = fake_model

        client = ai_core._get_gemini_client()

        self.assertIs(client, fake_model)
        mock_configure.assert_called_once_with(api_key='test_key')

    @patch('ai_core.config.API_KEY', '')
    @patch('ai_core.config.API_KEY_SECONDARY', '')
    def test_raises_ai_error_when_no_keys(self):
        with self.assertRaises(AIProviderError):
            ai_core._get_gemini_client()


# ---------------------------------------------------------------------------
# Legacy tests (backward compatibility – unchanged behaviour)
# ---------------------------------------------------------------------------

class TestLegacyGetCorrectOptionIndex(unittest.TestCase):

    @patch('ai_core.generate_content_with_fallback')
    @patch('ai_core.Image.open')
    def test_success(self, mock_image_open, mock_generate):
        mock_response = MagicMock()
        mock_response.text = "2"
        mock_generate.return_value = mock_response
        mock_image = MagicMock()
        mock_image_open.return_value = mock_image

        index = ai_core.get_correct_option_index("dummy_path.png")

        self.assertEqual(index, 2)
        mock_generate.assert_called()
        args, _ = mock_generate.call_args
        self.assertIn(mock_image, args[0])

    @patch('ai_core.generate_content_with_fallback')
    @patch('ai_core.Image.open')
    def test_invalid_response_returns_none(self, mock_image_open, mock_generate):
        mock_response = MagicMock()
        mock_response.text = "Not a number"
        mock_generate.return_value = mock_response
        mock_image_open.return_value = MagicMock()

        self.assertIsNone(ai_core.get_correct_option_index("dummy_path.png"))

    @patch('ai_core.generate_content_with_fallback')
    @patch('ai_core.Image.open')
    def test_out_of_range_returns_none(self, mock_image_open, mock_generate):
        mock_response = MagicMock()
        mock_response.text = "5"
        mock_generate.return_value = mock_response
        mock_image_open.return_value = MagicMock()

        self.assertIsNone(ai_core.get_correct_option_index("dummy_path.png"))

    @patch('ai_core.generate_content_with_fallback')
    @patch('ai_core.Image.open')
    def test_exception_returns_none(self, mock_image_open, mock_generate):
        mock_generate.side_effect = Exception("API Error")
        mock_image_open.return_value = MagicMock()

        self.assertIsNone(ai_core.get_correct_option_index("dummy_path.png"))


class TestGenerateContentWithFallback(unittest.TestCase):

    @patch('ai_core.genai.GenerativeModel')
    @patch('ai_core.genai.configure')
    @patch('ai_core.config.MODEL_NAME', 'gemini-2.5-flash')
    @patch('ai_core.config.API_KEY', 'primary_key')
    @patch('ai_core.config.API_KEY_SECONDARY', 'backup_key')
    def test_falls_back_on_rate_limit(self, mock_configure, mock_model_cls):
        first_model = MagicMock()
        second_model = MagicMock()
        mock_model_cls.side_effect = [first_model, second_model]

        first_model.generate_content.side_effect = Exception("429 rate limit exceeded")
        expected_response = MagicMock()
        second_model.generate_content.return_value = expected_response

        response = ai_core.generate_content_with_fallback(["prompt"])

        self.assertEqual(response, expected_response)
        self.assertEqual(mock_model_cls.call_count, 2)
        self.assertEqual(mock_configure.call_count, 2)

    @patch('ai_core.genai.GenerativeModel')
    @patch('ai_core.genai.configure')
    @patch('ai_core.config.MODEL_NAME', 'gemini-2.5-flash')
    @patch('ai_core.config.API_KEY', 'primary_key')
    @patch('ai_core.config.API_KEY_SECONDARY', 'backup_key')
    def test_falls_back_for_non_rate_limit_error(self, mock_configure, mock_model_cls):
        first_model = MagicMock()
        second_model = MagicMock()
        mock_model_cls.side_effect = [first_model, second_model]

        first_model.generate_content.side_effect = Exception("invalid api key")
        expected_response = MagicMock()
        second_model.generate_content.return_value = expected_response

        response = ai_core.generate_content_with_fallback(["prompt"])

        self.assertEqual(response, expected_response)
        self.assertEqual(mock_model_cls.call_count, 2)
        self.assertEqual(mock_configure.call_count, 2)


# ---------------------------------------------------------------------------
# Tests for generate_theory_answer – Groq routing
# ---------------------------------------------------------------------------

class TestGenerateTheoryAnswerGroqRouting(unittest.TestCase):

    @patch('ai_core.chat_with_groq', return_value="Theory answer from Groq.")
    @patch('ai_core.config.USE_GROQ_FOR_EXPLANATION', True)
    @patch('ai_core.config.GROQ_API_KEY', 'groq-key')
    @patch('ai_core.config.GROQ_DEFAULT_MODEL', 'llama-3.3-70b-versatile')
    def test_uses_groq_when_enabled(self, mock_chat):
        result = ai_core.generate_theory_answer("Explain Newton's laws")

        self.assertEqual(result, "Theory answer from Groq.")
        mock_chat.assert_called_once_with(
            "Explain Newton's laws",
            model='llama-3.3-70b-versatile',
        )

    @patch('ai_core.generate_content_with_fallback')
    @patch('ai_core.config.USE_GROQ_FOR_EXPLANATION', False)
    @patch('ai_core.config.GROQ_API_KEY', 'groq-key')
    def test_falls_back_to_gemini_when_groq_disabled(self, mock_fallback):
        mock_fallback.return_value = _make_response("Gemini theory answer.")

        result = ai_core.generate_theory_answer("Explain photosynthesis")

        self.assertEqual(result, "Gemini theory answer.")
        mock_fallback.assert_called_once()

    @patch('ai_core.generate_content_with_fallback')
    @patch('ai_core.config.USE_GROQ_FOR_EXPLANATION', True)
    @patch('ai_core.config.GROQ_API_KEY', '')
    def test_falls_back_to_gemini_when_no_groq_key(self, mock_fallback):
        mock_fallback.return_value = _make_response("Gemini answer no key.")

        result = ai_core.generate_theory_answer("Some question")

        self.assertEqual(result, "Gemini answer no key.")
        mock_fallback.assert_called_once()

    @patch('ai_core.chat_with_groq')
    @patch('ai_core.config.USE_GROQ_FOR_EXPLANATION', True)
    @patch('ai_core.config.GROQ_API_KEY', 'groq-key')
    @patch('ai_core.config.GROQ_DEFAULT_MODEL', 'llama-3.3-70b-versatile')
    def test_groq_error_raises_ai_provider_error(self, mock_chat):
        from groq_client import GroqError
        mock_chat.side_effect = GroqError("service unavailable")

        with self.assertRaises(AIProviderError) as ctx:
            ai_core.generate_theory_answer("prompt")
        self.assertIn("generate_theory_answer (Groq) failed", str(ctx.exception))


# ---------------------------------------------------------------------------
# Tests for explain_code – Groq routing
# ---------------------------------------------------------------------------

class TestExplainCodeGroqRouting(unittest.TestCase):

    @patch('ai_core.explain_code_with_groq', return_value="Groq explanation.")
    @patch('ai_core.config.USE_GROQ_FOR_EXPLANATION', True)
    @patch('ai_core.config.GROQ_API_KEY', 'groq-key')
    def test_uses_groq_when_enabled(self, mock_explain):
        result = ai_core.explain_code("def foo(): pass")

        self.assertEqual(result, "Groq explanation.")
        mock_explain.assert_called_once_with("def foo(): pass", extra_context=None)

    @patch('ai_core.explain_code_with_groq', return_value="Groq with context.")
    @patch('ai_core.config.USE_GROQ_FOR_EXPLANATION', True)
    @patch('ai_core.config.GROQ_API_KEY', 'groq-key')
    def test_extra_context_forwarded_to_groq(self, mock_explain):
        ai_core.explain_code("x = 1", extra_context="global counter")

        mock_explain.assert_called_once_with("x = 1", extra_context="global counter")

    @patch('ai_core.generate_content_with_fallback')
    @patch('ai_core.config.USE_GROQ_FOR_EXPLANATION', False)
    @patch('ai_core.config.GROQ_API_KEY', 'groq-key')
    def test_falls_back_to_gemini_when_groq_disabled(self, mock_fallback):
        mock_fallback.return_value = _make_response("Gemini explains.")

        result = ai_core.explain_code("pass")

        self.assertEqual(result, "Gemini explains.")
        mock_fallback.assert_called_once()

    @patch('ai_core.generate_content_with_fallback')
    @patch('ai_core.config.USE_GROQ_FOR_EXPLANATION', True)
    @patch('ai_core.config.GROQ_API_KEY', '')
    def test_falls_back_to_gemini_when_no_groq_key(self, mock_fallback):
        mock_fallback.return_value = _make_response("Gemini fallback no key.")

        result = ai_core.explain_code("pass")

        self.assertEqual(result, "Gemini fallback no key.")

    @patch('ai_core.explain_code_with_groq')
    @patch('ai_core.config.USE_GROQ_FOR_EXPLANATION', True)
    @patch('ai_core.config.GROQ_API_KEY', 'groq-key')
    def test_groq_error_raises_ai_provider_error(self, mock_explain):
        from groq_client import GroqError
        mock_explain.side_effect = GroqError("timeout")

        with self.assertRaises(AIProviderError) as ctx:
            ai_core.explain_code("import os")
        self.assertIn("explain_code (Groq) failed", str(ctx.exception))


# ---------------------------------------------------------------------------
# Tests for generate_code_answer – OpenRouter routing
# ---------------------------------------------------------------------------

class TestGenerateCodeAnswerGroqRouting(unittest.TestCase):
    """Verify that generate_code_answer tries Groq first."""

    @patch('ai_core.chat_with_groq', return_value="# groq answer")
    @patch('ai_core.config.USE_GROQ_FOR_CODE', True)
    @patch('ai_core.config.GROQ_API_KEY', 'groq-key')
    def test_uses_groq_when_enabled(self, mock_groq):
        result = ai_core.generate_code_answer("sort a list")

        self.assertEqual(result, "# groq answer")
        mock_groq.assert_called_once_with("sort a list", model=config.GROQ_DEFAULT_MODEL)

    @patch('ai_core.generate_code_from_openrouter', return_value="# openrouter answer")
    @patch('ai_core.chat_with_groq')
    @patch('ai_core.config.USE_GROQ_FOR_CODE', True)
    @patch('ai_core.config.GROQ_API_KEY', 'groq-key')
    @patch('ai_core.config.USE_OPENROUTER_FOR_CODE', True)
    @patch('ai_core.config.OPENROUTER_API_KEY', 'or-key')
    def test_groq_failure_falls_through_to_openrouter(self, mock_groq, mock_or):
        from groq_client import GroqError
        mock_groq.side_effect = GroqError("timeout")

        result = ai_core.generate_code_answer("sort a list")

        self.assertEqual(result, "# openrouter answer")
        mock_or.assert_called_once_with("sort a list")

    @patch('ai_core.generate_content_with_fallback')
    @patch('ai_core.config.USE_GROQ_FOR_CODE', False)
    @patch('ai_core.config.GROQ_API_KEY', 'groq-key')
    @patch('ai_core.config.USE_OPENROUTER_FOR_CODE', False)
    @patch('ai_core.config.OPENROUTER_API_KEY', 'or-key')
    def test_groq_disabled_skips_to_gemini(self, mock_fallback):
        mock_fallback.return_value = _make_response("Gemini code")

        result = ai_core.generate_code_answer("sort a list")

        self.assertEqual(result, "Gemini code")
        mock_fallback.assert_called_once()

    @patch('ai_core.generate_content_with_fallback')
    @patch('ai_core.config.USE_GROQ_FOR_CODE', True)
    @patch('ai_core.config.GROQ_API_KEY', '')   # no key → skip Groq
    @patch('ai_core.config.USE_OPENROUTER_FOR_CODE', False)
    @patch('ai_core.config.OPENROUTER_API_KEY', '')
    def test_no_groq_key_falls_through_to_gemini(self, mock_fallback):
        mock_fallback.return_value = _make_response("Gemini fallback")

        result = ai_core.generate_code_answer("sort a list")

        self.assertEqual(result, "Gemini fallback")
        mock_fallback.assert_called_once()


class TestGenerateCodeAnswerOpenRouterRouting(unittest.TestCase):
    """Verify that generate_code_answer routes to OpenRouter when Groq is disabled."""

    @patch('ai_core.generate_code_from_openrouter', return_value="# openrouter answer")
    @patch('ai_core.config.USE_GROQ_FOR_CODE', False)   # Groq disabled
    @patch('ai_core.config.GROQ_API_KEY', '')
    @patch('ai_core.config.USE_OPENROUTER_FOR_CODE', True)
    @patch('ai_core.config.OPENROUTER_API_KEY', 'or-test-key')
    def test_uses_openrouter_when_groq_disabled(self, mock_or):
        result = ai_core.generate_code_answer("sort a list in Python")

        self.assertEqual(result, "# openrouter answer")
        mock_or.assert_called_once_with("sort a list in Python")

    @patch('ai_core.generate_content_with_fallback')
    @patch('ai_core.config.USE_GROQ_FOR_CODE', False)
    @patch('ai_core.config.GROQ_API_KEY', '')
    @patch('ai_core.config.USE_OPENROUTER_FOR_CODE', False)
    @patch('ai_core.config.OPENROUTER_API_KEY', 'or-test-key')
    def test_falls_back_to_gemini_when_openrouter_disabled(self, mock_fallback):
        mock_fallback.return_value = _make_response("Gemini code")

        result = ai_core.generate_code_answer("sort a list in Python")

        self.assertEqual(result, "Gemini code")
        mock_fallback.assert_called_once()

    @patch('ai_core.generate_content_with_fallback')
    @patch('ai_core.config.USE_GROQ_FOR_CODE', False)
    @patch('ai_core.config.GROQ_API_KEY', '')
    @patch('ai_core.config.USE_OPENROUTER_FOR_CODE', True)
    @patch('ai_core.config.OPENROUTER_API_KEY', '')
    def test_falls_back_to_gemini_when_no_openrouter_key(self, mock_fallback):
        mock_fallback.return_value = _make_response("Gemini fallback no key")

        result = ai_core.generate_code_answer("sort a list in Python")

        self.assertEqual(result, "Gemini fallback no key")
        mock_fallback.assert_called_once()

    @patch('ai_core.generate_code_from_openrouter')
    @patch('ai_core.config.USE_GROQ_FOR_CODE', False)
    @patch('ai_core.config.GROQ_API_KEY', '')
    @patch('ai_core.config.USE_OPENROUTER_FOR_CODE', True)
    @patch('ai_core.config.OPENROUTER_API_KEY', 'or-test-key')
    def test_openrouter_error_raises_ai_provider_error(self, mock_or):
        from openrouter_client import OpenRouterError
        mock_or.side_effect = OpenRouterError("rate limited")

        with self.assertRaises(AIProviderError) as ctx:
            ai_core.generate_code_answer("generate code")
        self.assertIn("generate_code_answer (OpenRouter) failed", str(ctx.exception))


if __name__ == '__main__':
    unittest.main()
