import unittest
from unittest.mock import MagicMock, patch
import sys
import os
import threading

# Add src to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'src')))

import utils
from pynput import mouse

class TestUtils(unittest.TestCase):
    @patch('pynput.mouse.Listener')
    def test_capture_single_click_success(self, mock_listener_cls):
        # Setup mock listener
        mock_listener_instance = MagicMock()
        mock_listener_cls.return_value = mock_listener_instance
        mock_listener_instance.__enter__.return_value = mock_listener_instance
        
        # We need to simulate the callback being called.
        # Since capture_single_click waits for an event that is set in the callback,
        # we need to trigger the callback from a separate thread or modify the test to handle the wait.
        
        # However, capture_single_click blocks on clicked.wait().
        # We can mock threading.Event.wait to trigger the callback side-effect.
        
        # Let's try a different approach: Mock the Listener to call the on_click callback immediately when __enter__ is called?
        # No, the callback is passed to __init__.
        
        # We can capture the on_click callback passed to Listener
        
        result_position = (100, 200)
        
        def side_effect_listener(on_click=None, **kwargs):
            # Create a thread to call the callback to simulate user interaction
            def trigger_click():
                if on_click:
                    # Simulate left click press
                    on_click(100, 200, mouse.Button.left, True)
            
            t = threading.Thread(target=trigger_click)
            t.start()
            return mock_listener_instance

        mock_listener_cls.side_effect = side_effect_listener
        
        pos = utils.capture_single_click()
        self.assertEqual(pos, result_position)

    @patch('pynput.mouse.Listener')
    def test_capture_single_click_ignore_release(self, mock_listener_cls):
        # Test that it ignores button release (pressed=False)
        
        def side_effect_listener(on_click=None, **kwargs):
            def trigger_click():
                if on_click:
                    # Simulate release (should be ignored)
                    on_click(100, 200, mouse.Button.left, False)
                    # Simulate right click (should be ignored)
                    on_click(100, 200, mouse.Button.right, True)
                    # Simulate left click press (should be accepted)
                    on_click(300, 400, mouse.Button.left, True)
            
            t = threading.Thread(target=trigger_click)
            t.start()
            return MagicMock() # Return a dummy mock for the context manager

        mock_listener_cls.side_effect = side_effect_listener
        
        pos = utils.capture_single_click()
        self.assertEqual(pos, (300, 400))

if __name__ == '__main__':
    unittest.main()
