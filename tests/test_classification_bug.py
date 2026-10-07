import unittest
from unittest.mock import MagicMock, patch
import sys
import os

# Add src to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'src')))

import subjective_handlers
import state

class TestSubjectiveClassification(unittest.TestCase):
    def setUp(self):
        state.subjective_screenshots = ["dummy.png"]
        state.ai_response_ready_subjective = MagicMock()

    @patch('subjective_handlers.ai_core.generate_theory_answer', return_value="Final Answer")
    @patch('subjective_handlers.generate_content_with_fallback')
    @patch('subjective_handlers.Image.open')
    def test_classification_non_coding_bug(self, mock_image_open, mock_generate, mock_theory):
        # Setup mocks
        mock_image_open.return_value = MagicMock()
        
        # Mock response for classification (First call)
        mock_response_classification = MagicMock()
        mock_response_classification.text = "non-coding"
        
        # Mock response for text extraction (Second call)
        mock_response_extract = MagicMock()
        mock_response_extract.text = "Extracted question text"
        
        mock_generate.side_effect = [mock_response_classification, mock_response_extract]
        
        # Run the worker function directly by patching threading.Thread
        with patch('threading.Thread') as mock_thread:
            def run_target(target, daemon):
                target()
                return MagicMock()
            
            mock_thread.side_effect = run_target
            
            subjective_handlers.generate_ai_response()
            
            # Two Gemini calls: classify + extract
            self.assertEqual(mock_generate.call_count, 2)

            # First call is classification — check it does NOT use the DSA prompt
            args_classify, _ = mock_generate.call_args_list[0]
            classify_prompt = args_classify[0][0]
            self.assertIn("Classify the question", classify_prompt,
                          "First call should be the classification prompt")

            # Second call is extraction — must NOT be the DSA programming prompt
            args_extract, _ = mock_generate.call_args_list[1]
            extract_prompt = args_extract[0][0]
            if "You are solving a programming problem" in extract_prompt:
                self.fail("Bug detected: 'non-coding' classified as DSA because 'coding' is in 'non-coding'!")
            self.assertIn("Transcribe", extract_prompt,
                          "Second call should be the question-extraction prompt")

            # Final answer must come from generate_theory_answer (Groq path)
            mock_theory.assert_called_once()
            self.assertIn("Extracted question text", mock_theory.call_args[0][0])

if __name__ == '__main__':
    unittest.main()
