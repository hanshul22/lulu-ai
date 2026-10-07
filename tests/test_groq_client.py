"""Tests for src/groq_client.py."""
import unittest
from unittest.mock import MagicMock, patch
import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'src')))

from groq_client import chat_with_groq, explain_code_with_groq, GroqError


def _ok_response(text: str) -> MagicMock:
    r = MagicMock()
    r.ok = True
    r.status_code = 200
    r.json.return_value = {"choices": [{"message": {"content": text}}]}
    return r


def _err_response(code: int, body: str = "error") -> MagicMock:
    r = MagicMock()
    r.ok = False
    r.status_code = code
    r.text = body
    return r


# ---------------------------------------------------------------------------
# chat_with_groq
# ---------------------------------------------------------------------------

class TestChatWithGroq(unittest.TestCase):

    @patch('groq_client.requests.post')
    @patch('groq_client.config.GROQ_API_KEY', 'test-key')
    @patch('groq_client.config.GROQ_BASE_URL', 'https://api.groq.com/openai/v1')
    def test_happy_path_returns_text(self, mock_post):
        mock_post.return_value = _ok_response("Photosynthesis converts light into energy.")

        result = chat_with_groq("Explain photosynthesis", model="llama-3.3-70b-versatile")

        self.assertEqual(result, "Photosynthesis converts light into energy.")
        mock_post.assert_called_once()
        call_args = mock_post.call_args
        self.assertIn("/chat/completions", call_args.args[0])
        headers = call_args.kwargs.get('headers') or call_args[1].get('headers', {})
        self.assertIn("Bearer test-key", headers.get("Authorization", ""))

    @patch('groq_client.requests.post')
    @patch('groq_client.config.GROQ_API_KEY', 'test-key')
    @patch('groq_client.config.GROQ_BASE_URL', 'https://api.groq.com/openai/v1')
    def test_model_forwarded_in_payload(self, mock_post):
        mock_post.return_value = _ok_response("answer")

        chat_with_groq("prompt", model="my-custom-model")

        payload = mock_post.call_args.kwargs.get('json') or mock_post.call_args[1].get('json', {})
        self.assertEqual(payload["model"], "my-custom-model")

    @patch('groq_client.requests.post')
    @patch('groq_client.config.GROQ_API_KEY', 'test-key')
    @patch('groq_client.config.GROQ_BASE_URL', 'https://api.groq.com/openai/v1')
    def test_system_message_included(self, mock_post):
        mock_post.return_value = _ok_response("answer")

        chat_with_groq("user prompt", model="llama-3.3-70b-versatile")

        payload = mock_post.call_args.kwargs.get('json') or mock_post.call_args[1].get('json', {})
        roles = [m["role"] for m in payload["messages"]]
        self.assertIn("system", roles)
        self.assertIn("user", roles)

    @patch('groq_client.config.GROQ_API_KEY', '')
    def test_raises_when_no_api_key(self):
        with self.assertRaises(GroqError) as ctx:
            chat_with_groq("prompt", model="llama-3.3-70b-versatile")
        self.assertIn("GROQ_API_KEY", str(ctx.exception))

    @patch('groq_client.requests.post')
    @patch('groq_client.config.GROQ_API_KEY', 'test-key')
    @patch('groq_client.config.GROQ_BASE_URL', 'https://api.groq.com/openai/v1')
    def test_http_error_raises_groq_error(self, mock_post):
        mock_post.return_value = _err_response(429, "rate limit exceeded")

        with self.assertRaises(GroqError) as ctx:
            chat_with_groq("prompt", model="llama-3.3-70b-versatile")
        self.assertIn("429", str(ctx.exception))

    @patch('groq_client.requests.post')
    @patch('groq_client.config.GROQ_API_KEY', 'test-key')
    @patch('groq_client.config.GROQ_BASE_URL', 'https://api.groq.com/openai/v1')
    def test_malformed_json_raises_groq_error(self, mock_post):
        bad = MagicMock()
        bad.ok = True
        bad.status_code = 200
        bad.json.return_value = {"unexpected": "structure"}
        bad.text = '{"unexpected": "structure"}'
        mock_post.return_value = bad

        with self.assertRaises(GroqError) as ctx:
            chat_with_groq("prompt", model="llama-3.3-70b-versatile")
        self.assertIn("Malformed", str(ctx.exception))

    @patch('groq_client.requests.post')
    @patch('groq_client.config.GROQ_API_KEY', 'test-key')
    @patch('groq_client.config.GROQ_BASE_URL', 'https://api.groq.com/openai/v1')
    def test_connection_error_raises_groq_error(self, mock_post):
        import requests as req
        mock_post.side_effect = req.ConnectionError("refused")

        with self.assertRaises(GroqError) as ctx:
            chat_with_groq("prompt", model="llama-3.3-70b-versatile")
        self.assertIn("Request failed", str(ctx.exception))


# ---------------------------------------------------------------------------
# explain_code_with_groq
# ---------------------------------------------------------------------------

class TestExplainCodeWithGroq(unittest.TestCase):

    @patch('groq_client.requests.post')
    @patch('groq_client.config.GROQ_API_KEY', 'test-key')
    @patch('groq_client.config.GROQ_BASE_URL', 'https://api.groq.com/openai/v1')
    @patch('groq_client.config.GROQ_DEFAULT_MODEL', 'llama-3.3-70b-versatile')
    def test_happy_path_returns_explanation(self, mock_post):
        mock_post.return_value = _ok_response("This function sorts a list.")

        result = explain_code_with_groq("def sort(lst): return sorted(lst)")

        self.assertEqual(result, "This function sorts a list.")
        # Verify code snippet is in the user message
        payload = mock_post.call_args.kwargs.get('json') or mock_post.call_args[1].get('json', {})
        user_msg = next(m for m in payload["messages"] if m["role"] == "user")
        self.assertIn("def sort(lst)", user_msg["content"])

    @patch('groq_client.requests.post')
    @patch('groq_client.config.GROQ_API_KEY', 'test-key')
    @patch('groq_client.config.GROQ_BASE_URL', 'https://api.groq.com/openai/v1')
    @patch('groq_client.config.GROQ_DEFAULT_MODEL', 'llama-3.3-70b-versatile')
    def test_extra_context_included_in_prompt(self, mock_post):
        mock_post.return_value = _ok_response("explanation")

        explain_code_with_groq("x = 1", extra_context="Global counter variable.")

        payload = mock_post.call_args.kwargs.get('json') or mock_post.call_args[1].get('json', {})
        user_msg = next(m for m in payload["messages"] if m["role"] == "user")
        self.assertIn("Global counter variable.", user_msg["content"])

    @patch('groq_client.requests.post')
    @patch('groq_client.config.GROQ_API_KEY', 'test-key')
    @patch('groq_client.config.GROQ_BASE_URL', 'https://api.groq.com/openai/v1')
    @patch('groq_client.config.GROQ_DEFAULT_MODEL', 'llama-3.3-70b-versatile')
    def test_api_error_raises_groq_error(self, mock_post):
        mock_post.return_value = _err_response(503, "service unavailable")

        with self.assertRaises(GroqError):
            explain_code_with_groq("pass")


if __name__ == '__main__':
    unittest.main()
