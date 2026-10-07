import tkinter as tk
from tkinter import scrolledtext
import ctypes
import threading
from logger_setup import logger
import settings_manager


class ExplanationWindow:
    def __init__(self, master=None):
        if master:
            self.root = tk.Toplevel(master)
        else:
            self.root = tk.Tk()

        self.root.title("Code Explanation")

        # Load size from settings
        settings = settings_manager.load_settings()
        width  = settings['window_size']['explanation_width']
        height = settings['window_size']['explanation_height']
        self.root.geometry(f"{width}x{height}")

        self.root.configure(bg='#1e1e1e')
        self.root.attributes("-topmost", True)
        self.root.attributes("-alpha", 0.85)
        self.root.overrideredirect(True)

        self.text_area = tk.Text(
            self.root,
            wrap=tk.WORD,
            font=("Arial", 14),
            bg="#2d2d2d",
            fg="#e0e0e0",
            insertbackground='white',
            selectbackground='#404040',
            highlightthickness=0,
            borderwidth=0,
            padx=15,
            pady=15,
        )
        self.text_area.pack(expand=True, fill='both', padx=5, pady=5)

        self.apply_hidden_affinity()
        self.hide_from_taskbar()

        self.root.withdraw()
        self.is_visible = False

    # -----------------------------------------------------------------------
    # Content
    # -----------------------------------------------------------------------

    def set_text(self, text):
        """Replace window content and ensure the window is visible."""
        self.text_area.delete("1.0", tk.END)
        self.text_area.insert("1.0", text)
        # set_text always shows — callers must NOT also call toggle() after
        # this, because toggle() would see is_visible=True and immediately
        # hide the window again (Fix #2).
        self.show_window()

    # -----------------------------------------------------------------------
    # Visibility
    # -----------------------------------------------------------------------

    def toggle(self):
        """Flip visibility — used by the Ctrl+Alt+A hotkey only."""
        if self.is_visible:
            self.hide_window()
        else:
            self.show_window()

    def show_window(self):
        self.root.deiconify()
        self.is_visible = True
        self.root.attributes("-topmost", True)
        self.text_area.focus_set()

    def hide_window(self):
        self.root.withdraw()
        self.is_visible = False

    # -----------------------------------------------------------------------
    # Stealth / taskbar helpers
    # -----------------------------------------------------------------------

    def hide_from_taskbar(self):
        try:
            self.root.update()
            hwnd = ctypes.windll.user32.GetParent(self.root.winfo_id())
            if hwnd == 0:
                hwnd = self.root.winfo_id()

            GWL_EXSTYLE      = -20
            WS_EX_TOOLWINDOW = 0x00000080
            WS_EX_APPWINDOW  = 0x00040000

            style = ctypes.windll.user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
            style = (style | WS_EX_TOOLWINDOW) & ~WS_EX_APPWINDOW
            ctypes.windll.user32.SetWindowLongW(hwnd, GWL_EXSTYLE, style)
        except Exception as e:
            logger.error(f"❌ Error hiding explanation from taskbar: {e}")

    def apply_hidden_affinity(self):
        try:
            WDA_EXCLUDEFROMCAPTURE = 0x00000011
            self.root.update()
            hwnd = ctypes.windll.user32.GetParent(self.root.winfo_id())
            if hwnd == 0:
                hwnd = self.root.winfo_id()
            ctypes.windll.user32.SetWindowDisplayAffinity(hwnd, WDA_EXCLUDEFROMCAPTURE)
        except Exception as e:
            logger.error(f"❌ Error setting explanation window affinity: {e}")

    # -----------------------------------------------------------------------
    # Movement
    # -----------------------------------------------------------------------

    def move(self, dx, dy):
        if not self.is_visible:
            return
        try:
            x, y = self.root.winfo_x(), self.root.winfo_y()
            w, h = self.root.winfo_width(), self.root.winfo_height()
            self.root.geometry(f"{w}x{h}+{x + dx}+{y + dy}")
        except Exception as e:
            logger.error(f"Error moving explanation window: {e}")

    def run(self):
        self.root.mainloop()


# ---------------------------------------------------------------------------
# Global instance + public helpers
# ---------------------------------------------------------------------------

explanation_app = None


def show_explanation(text: str) -> None:
    """Schedule a text update on the Tk main thread.

    set_text() always calls show_window() internally, so the window will
    become visible automatically.  Do NOT call toggle_explanation() or
    show_window_direct() after this in the same code path — that would
    create a double-show or, worse, immediately hide the window (Fix #2).
    """
    if explanation_app:
        explanation_app.root.after(0, lambda: explanation_app.set_text(text))


def show_window_direct() -> None:
    """Unconditionally show the explanation window without toggling.

    Use this instead of toggle_explanation() when you want the window to
    always be visible after a show_explanation() call.  toggle_explanation()
    is only appropriate for the Ctrl+Alt+A hotkey where the intent is to
    flip the current visibility state.

    Fix #2: subjective_handlers.py uses this so that show_explanation(...)
    followed by show_window_direct() never accidentally hides the window.
    """
    if explanation_app:
        explanation_app.root.after(0, explanation_app.show_window)


def toggle_explanation() -> None:
    """Flip window visibility — used by the Ctrl+Alt+A hotkey only."""
    if explanation_app:
        explanation_app.root.after(0, explanation_app.toggle)


def move_explanation(dx: int, dy: int) -> None:
    if explanation_app:
        explanation_app.root.after(0, lambda: explanation_app.move(dx, dy))