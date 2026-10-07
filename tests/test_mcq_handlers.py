import unittest
from unittest.mock import MagicMock, patch
import sys
import os

# Add src to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'src')))

import mcq_handlers
import state
import config

class TestMCQHandlers(unittest.TestCase):
    def setUp(self):
        # Reset state
        state.context_captured = False
        state.processing_mcq = False
        state.option_positions = []
        state.ai_result_index = None

    @patch('mcq_handlers.capture_single_click')
    @patch('mcq_handlers.pyautogui.screenshot')
    def test_capture_context_success(self, mock_screenshot, mock_click):
        # Mock clicks
        mock_click.side_effect = [(100, 100), (300, 300)]
        
        # Mock screenshot save
        mock_img = MagicMock()
        mock_screenshot.return_value = mock_img
        
        mcq_handlers.capture_context()
        
        self.assertTrue(state.context_captured)
        mock_screenshot.assert_called_with(region=(100, 100, 200, 200))
        mock_img.save.assert_called_with(config.CONTEXT_IMAGE_PATH)

    @patch('mcq_handlers.capture_single_click')
    def test_capture_context_cancel(self, mock_click):
        # Mock cancel on first click
        mock_click.return_value = None
        
        mcq_handlers.capture_context()
        
        self.assertFalse(state.context_captured)

    @patch('mcq_handlers.capture_single_click')
    def test_capture_context_invalid_region(self, mock_click):
        # Mock invalid region (width <= 0)
        mock_click.side_effect = [(300, 300), (100, 100)]
        
        mcq_handlers.capture_context()
        
        self.assertFalse(state.context_captured)


# ---------------------------------------------------------------------------
# Helper: build listener mocks that inject fake events immediately on start()
# ---------------------------------------------------------------------------

def _make_listener_mocks(mock_mouse_cls, mock_kbd_cls):
    """Wire up mouse and keyboard Listener mocks to inject 2 option-clicks
    and an Enter key-press synchronously when start() is called, so that
    the ``done`` threading.Event is set before done.wait() is reached."""
    from pynput import mouse as real_mouse, keyboard as real_kbd

    def mouse_factory(on_click):
        ml = MagicMock()

        def fake_start():
            on_click(200, 200, real_mouse.Button.left, True)
            on_click(300, 300, real_mouse.Button.left, True)

        ml.start = fake_start
        ml.stop = MagicMock()
        return ml

    def kbd_factory(on_press):
        kl = MagicMock()

        def fake_start():
            on_press(real_kbd.Key.enter)

        kl.start = fake_start
        kl.stop = MagicMock()
        return kl

    mock_mouse_cls.side_effect = mouse_factory
    mock_kbd_cls.side_effect = kbd_factory


class TestSolveCurrentMCQWiring(unittest.TestCase):
    """Verify that solve_current_mcq routes to the correct AI helper."""

    def setUp(self):
        state.context_captured = False
        state.correct_index_global = None
        state.ai_response_ready.clear()
        state.option_positions_ready.clear()

    @patch('mcq_handlers.get_correct_option_index', return_value=2)
    @patch('mcq_handlers.threading.Thread')
    @patch('mcq_handlers.keyboard.Listener')
    @patch('mcq_handlers.mouse.Listener')
    @patch('mcq_handlers.pyautogui')
    @patch('mcq_handlers.capture_single_click', side_effect=[(100, 100), (300, 300)])
    def test_without_context_calls_get_correct_option_index(
        self, mock_click, mock_pag, mock_mouse_cls, mock_kbd_cls,
        mock_thread_cls, mock_goi
    ):
        _make_listener_mocks(mock_mouse_cls, mock_kbd_cls)
        mock_thread_cls.side_effect = lambda target, daemon=True: (
            type('T', (), {'start': lambda self: target()})()
        )
        mock_img = MagicMock()
        mock_pag.screenshot.return_value = mock_img

        state.context_captured = False
        mcq_handlers.solve_current_mcq()

        mock_goi.assert_called_once_with(config.QUESTION_IMAGE_PATH, 2)
        self.assertEqual(state.correct_index_global, 2)

    @patch('mcq_handlers.get_correct_option_index_with_context', return_value=3)
    @patch('mcq_handlers.threading.Thread')
    @patch('mcq_handlers.keyboard.Listener')
    @patch('mcq_handlers.mouse.Listener')
    @patch('mcq_handlers.pyautogui')
    @patch('mcq_handlers.capture_single_click', side_effect=[(100, 100), (300, 300)])
    def test_with_context_calls_get_correct_option_index_with_context(
        self, mock_click, mock_pag, mock_mouse_cls, mock_kbd_cls,
        mock_thread_cls, mock_goi_ctx
    ):
        _make_listener_mocks(mock_mouse_cls, mock_kbd_cls)
        mock_thread_cls.side_effect = lambda target, daemon=True: (
            type('T', (), {'start': lambda self: target()})()
        )
        mock_img = MagicMock()
        mock_pag.screenshot.return_value = mock_img

        state.context_captured = True
        mcq_handlers.solve_current_mcq()

        mock_goi_ctx.assert_called_once_with(
            config.CONTEXT_IMAGE_PATH, config.QUESTION_IMAGE_PATH, 2
        )
        self.assertEqual(state.correct_index_global, 3)

    @patch('mcq_handlers.get_correct_option_index', return_value=None)
    @patch('mcq_handlers.threading.Thread')
    @patch('mcq_handlers.keyboard.Listener')
    @patch('mcq_handlers.mouse.Listener')
    @patch('mcq_handlers.pyautogui')
    @patch('mcq_handlers.capture_single_click', side_effect=[(100, 100), (300, 300)])
    def test_ai_returns_none_leaves_correct_index_none(
        self, mock_click, mock_pag, mock_mouse_cls, mock_kbd_cls,
        mock_thread_cls, mock_goi
    ):
        _make_listener_mocks(mock_mouse_cls, mock_kbd_cls)
        mock_thread_cls.side_effect = lambda target, daemon=True: (
            type('T', (), {'start': lambda self: target()})()
        )
        mock_img = MagicMock()
        mock_pag.screenshot.return_value = mock_img

        state.context_captured = False
        mcq_handlers.solve_current_mcq()

        self.assertIsNone(state.correct_index_global)


if __name__ == '__main__':
    unittest.main()
