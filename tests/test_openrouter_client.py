"""Tests for src/openrouter_client.py."""
import unittest
from unittest.mock import MagicMock, patch
import sys
import os

# Add src to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'src')))

from openrouter_client import generate_code_from_openrouter, OpenRouterError


def _mock_ok_response(text: str) -> MagicMock:
    """Return a mock requests.Response with a valid OpenRouter JSON payload."""
    response = MagicMock()
    response.ok = True
    response.status_code = 200
    response.json.return_value = {
        "choices": [
            {"message": {"content": text}}
        ]
    }
    return response


def _mock_error_response(status_code: int, body: str = "error") -> MagicMock:
    response = MagicMock()
    response.ok = False
    response.status_code = status_code
    response.text = body
    return response


class TestGenerateCodeFromOpenRouter(unittest.TestCase):

    # ------------------------------------------------------------------
    # Happy-path tests
    # ------------------------------------------------------------------

    @patch('openrouter_client.requests.post')
    @patch('openrouter_client.config.OPENROUTER_API_KEY', 'test-key')
    @patch('openrouter_client.config.OPENROUTER_CODE_MODEL', 'mistral/devstral-2-2501:free')
    @patch('openrouter_client.config.OPENROUTER_BASE_URL', 'https://openrouter.ai/api/v1')
    def test_happy_path_returns_assistant_text(self, mock_post):
        mock_post.return_value = _mock_ok_response("def binary_search(): pass")

        result = generate_code_from_openrouter("Write binary search in Python")

        self.assertEqual(result, "def binary_search(): pass")
        mock_post.assert_called_once()
        call_kwargs = mock_post.call_args
        # Verify endpoint
        self.assertIn("/chat/completions", call_kwargs.args[0])
        # Verify Authorization header
        headers = call_kwargs.kwargs.get('headers') or call_kwargs[1].get('headers', {})
        self.assertIn("Bearer test-key", headers.get("Authorization", ""))

    @patch('openrouter_client.requests.post')
    @patch('openrouter_client.config.OPENROUTER_API_KEY', 'test-key')
    @patch('openrouter_client.config.OPENROUTER_CODE_MODEL', 'mistral/devstral-2-2501:free')
    @patch('openrouter_client.config.OPENROUTER_BASE_URL', 'https://openrouter.ai/api/v1')
    def test_custom_model_is_forwarded(self, mock_post):
        mock_post.return_value = _mock_ok_response("SELECT 1;")

        generate_code_from_openrouter("Write SQL", model="qwen/qwen-2.5-coder-32b-instruct:free")

        payload = mock_post.call_args.kwargs.get('json') or mock_post.call_args[1].get('json', {})
        self.assertEqual(payload["model"], "qwen/qwen-2.5-coder-32b-instruct:free")

    # ------------------------------------------------------------------
    # Error-path tests
    # ------------------------------------------------------------------

    @patch('openrouter_client.config.OPENROUTER_API_KEY', '')
    def test_raises_when_no_api_key(self):
        with self.assertRaises(OpenRouterError) as ctx:
            generate_code_from_openrouter("prompt")
        self.assertIn("OPENROUTER_API_KEY", str(ctx.exception))

    @patch('openrouter_client.requests.post')
    @patch('openrouter_client.config.OPENROUTER_API_KEY', 'test-key')
    @patch('openrouter_client.config.OPENROUTER_CODE_MODEL', 'model')
    @patch('openrouter_client.config.OPENROUTER_BASE_URL', 'https://openrouter.ai/api/v1')
    def test_http_error_raises_openrouter_error(self, mock_post):
        mock_post.return_value = _mock_error_response(429, "rate limit exceeded")

        with self.assertRaises(OpenRouterError) as ctx:
            generate_code_from_openrouter("prompt")
        self.assertIn("429", str(ctx.exception))

    @patch('openrouter_client.requests.post')
    @patch('openrouter_client.config.OPENROUTER_API_KEY', 'test-key')
    @patch('openrouter_client.config.OPENROUTER_CODE_MODEL', 'model')
    @patch('openrouter_client.config.OPENROUTER_BASE_URL', 'https://openrouter.ai/api/v1')
    def test_malformed_json_raises_openrouter_error(self, mock_post):
        bad_response = MagicMock()
        bad_response.ok = True
        bad_response.status_code = 200
        bad_response.json.return_value = {"unexpected": "structure"}
        bad_response.text = '{"unexpected": "structure"}'
        mock_post.return_value = bad_response

        with self.assertRaises(OpenRouterError) as ctx:
            generate_code_from_openrouter("prompt")
        self.assertIn("Malformed", str(ctx.exception))

    @patch('openrouter_client.requests.post')
    @patch('openrouter_client.config.OPENROUTER_API_KEY', 'test-key')
    @patch('openrouter_client.config.OPENROUTER_CODE_MODEL', 'model')
    @patch('openrouter_client.config.OPENROUTER_BASE_URL', 'https://openrouter.ai/api/v1')
    def test_connection_error_raises_openrouter_error(self, mock_post):
        import requests as req
        mock_post.side_effect = req.ConnectionError("connection refused")

        with self.assertRaises(OpenRouterError) as ctx:
            generate_code_from_openrouter("prompt")
        self.assertIn("Request failed", str(ctx.exception))


if __name__ == '__main__':
    unittest.main()
