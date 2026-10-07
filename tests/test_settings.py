import unittest
import os
import json
import sys

# Add src to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'src')))

import settings_manager

class TestSettingsManager(unittest.TestCase):
    def setUp(self):
        # Backup existing settings if any
        self.original_settings_file = settings_manager.SETTINGS_FILE
        self.test_settings_file = "test_settings.json"
        settings_manager.SETTINGS_FILE = self.test_settings_file
        
        if os.path.exists(self.test_settings_file):
            os.remove(self.test_settings_file)

    def tearDown(self):
        # Clean up test file
        if os.path.exists(self.test_settings_file):
            os.remove(self.test_settings_file)
        
        # Restore original file path
        settings_manager.SETTINGS_FILE = self.original_settings_file

    def test_load_defaults(self):
        """Test that default settings are loaded when no file exists."""
        settings = settings_manager.load_settings()
        self.assertEqual(settings['api_key'], "test-api-key")
        self.assertTrue(settings['features']['notes_enabled'])
        self.assertTrue(os.path.exists(self.test_settings_file))

    def test_save_and_load(self):
        """Test saving settings and loading them back."""
        settings = settings_manager.load_settings()
        settings['api_key'] = "TEST_KEY_123"
        settings['features']['notes_enabled'] = False
        settings['window_size']['notes_width'] = 800
        
        settings_manager.save_settings(settings)
        
        new_settings = settings_manager.load_settings()
        self.assertEqual(new_settings['api_key'], "TEST_KEY_123")
        self.assertFalse(new_settings['features']['notes_enabled'])
        self.assertEqual(new_settings['window_size']['notes_width'], 800)

    def test_partial_update(self):
        """Test that loading merges with defaults if keys are missing."""
        # Create a partial settings file
        partial_settings = {"api_key": "PARTIAL_KEY"}
        with open(self.test_settings_file, 'w') as f:
            json.dump(partial_settings, f)
            
        settings = settings_manager.load_settings()
        self.assertEqual(settings['api_key'], "PARTIAL_KEY")
        self.assertTrue('hotkeys' in settings) # Should have merged defaults

if __name__ == '__main__':
    unittest.main()
