import unittest
import sys
import os
import threading

# Add src to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'src')))

import state

class TestState(unittest.TestCase):
    def setUp(self):
        # Reset state before each test
        state.context_captured = False
        state.subjective_screenshots = []
        state.ai_response_text = None
        state.screenshots_count_at_generation = 0
        state.is_typing_active = False
        state.is_typing_paused = False
        state.current_typing_position = 0
        state.correct_index_global = None
        state.option_positions_global = None
        
        # Clear events
        state.resume_typing_event.clear()
        state.ai_response_ready.clear()
        state.option_positions_ready.clear()
        state.ai_response_ready_subjective.clear()

    def test_initial_state(self):
        self.assertFalse(state.context_captured)
        self.assertEqual(state.subjective_screenshots, [])
        self.assertIsNone(state.ai_response_text)
        self.assertFalse(state.is_typing_active)
        self.assertIsNone(state.correct_index_global)

    def test_state_modification(self):
        state.context_captured = True
        state.subjective_screenshots.append("test.png")
        state.ai_response_text = "Test Response"
        
        self.assertTrue(state.context_captured)
        self.assertEqual(state.subjective_screenshots, ["test.png"])
        self.assertEqual(state.ai_response_text, "Test Response")

    def test_events(self):
        self.assertFalse(state.ai_response_ready.is_set())
        state.ai_response_ready.set()
        self.assertTrue(state.ai_response_ready.is_set())

if __name__ == '__main__':
    unittest.main()
