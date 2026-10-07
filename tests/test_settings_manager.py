import unittest
from unittest.mock import mock_open, patch
import sys
import os
import json

# Add src to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'src')))

import settings_manager

class TestSettingsManager(unittest.TestCase):
    def setUp(self):
        self.default_settings = {
            "api_key": "test-api-key",
            "api_key_secondary": "",
            "model_name": "gemini-2.5-flash",
            "hotkeys": {
                "capture_context": "<ctrl>+<alt>+c",
                "capture_question": "<ctrl>+<alt>+p",
                "clear_context": "<ctrl>+<alt>+r",
                "exit": "<ctrl>+<alt>+e",
                "capture_subjective": "<ctrl>+<alt>+s",
                "generate_response": "<ctrl>+<alt>+g",
                "type_response": "<ctrl>+<alt>+t",
                "resume_typing": "<ctrl>+<alt>+z",
                "retry_subjective": "<ctrl>+<alt>+k",
                "toggle_notes": "<ctrl>+<alt>+n",
                "toggle_explanation": "<ctrl>+<alt>+a",
                "explain_code": "<ctrl>+<alt>+j",
                "control_panel": "<ctrl>+<alt>+m",
                "step_by_step_solution": "<ctrl>+<alt>+o"
            },
            "features": {
                "notes_enabled": True,
                "explanation_enabled": True
            },
            "typing": {
                "min_delay": 0.03,
                "max_delay": 0.08
            },
            "window_size": {
                "notes_width": 400,
                "notes_height": 300,
                "explanation_width": 500,
                "explanation_height": 400
            }
        }

    @patch('builtins.open', new_callable=mock_open, read_data='{"api_key": "test_key"}')
    @patch('os.path.exists')
    def test_load_settings_existing(self, mock_exists, mock_file):
        mock_exists.return_value = True
        
        settings = settings_manager.load_settings()
        
        self.assertEqual(settings['api_key'], "test_key")
        # Should merge with defaults
        self.assertEqual(settings['model_name'], "gemini-2.5-flash")

    @patch('builtins.open', new_callable=mock_open)
    @patch('os.path.exists')
    def test_load_settings_not_existing(self, mock_exists, mock_file):
        mock_exists.return_value = False
        
        settings = settings_manager.load_settings()
        
        self.assertEqual(settings, self.default_settings)
        # Should create the file
        mock_file.assert_called_with(settings_manager.SETTINGS_FILE, 'w')

    @patch('json.dump')
    @patch('builtins.open', new_callable=mock_open)
    def test_save_settings(self, mock_file, mock_json_dump):
        new_settings = self.default_settings.copy()
        new_settings['api_key'] = "new_key"
        
        settings_manager.save_settings(new_settings)
        
        mock_file.assert_called_with(settings_manager.SETTINGS_FILE, 'w')
        # Verify json.dump was called with correct arguments
        mock_json_dump.assert_called_with(new_settings, mock_file(), indent=4)

if __name__ == '__main__':
    unittest.main()
