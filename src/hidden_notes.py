import tkinter as tk
from tkinter import scrolledtext
import ctypes
import os
import config
from logger_setup import logger
import settings_manager

class HiddenNotesWindow:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("Hidden Notes")
        
        # Load size from settings
        settings = settings_manager.load_settings()
        width = settings['window_size']['notes_width']
        height = settings['window_size']['notes_height']
        self.root.geometry(f"{width}x{height}")
        
        self.root.configure(bg='#1e1e1e') # Dark mode background
        self.root.attributes("-topmost", True)
        self.root.attributes("-alpha", 0.85) # Set opacity (0.0 to 1.0)
        self.root.overrideredirect(True) # Remove title bar and borders
        
        # Create text area with dark mode styling
        # Using tk.Text instead of ScrolledText to remove scrollbar
        self.text_area = tk.Text(
            self.root, 
            wrap=tk.WORD, 
            font=("Arial", 16),
            bg="#2d2d2d", # Dark grey text area
            fg="#e0e0e0", # Light grey text
            insertbackground='white', # White cursor
            selectbackground='#404040', # Selection color
            highlightthickness=0,
            borderwidth=0,
            padx=15, # Internal horizontal padding
            pady=15  # Internal vertical padding
        )
        self.text_area.pack(expand=True, fill='both', padx=5, pady=5) # External padding
        
        self.load_notes()
        
        # Apply hidden affinity (Windows only)
        self.apply_hidden_affinity()
        self.hide_from_taskbar()
        
        self.root.withdraw() # Start hidden
        self.is_visible = False

    def hide_from_taskbar(self):
        """
        Removes the window from the taskbar by setting the WS_EX_TOOLWINDOW style.
        """
        try:
            self.root.update() # Ensure window handle exists
            hwnd = ctypes.windll.user32.GetParent(self.root.winfo_id())
            if hwnd == 0:
                hwnd = self.root.winfo_id()
            
            GWL_EXSTYLE = -20
            WS_EX_TOOLWINDOW = 0x00000080
            WS_EX_APPWINDOW = 0x00040000

            # Get current extended style
            style = ctypes.windll.user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
            
            # Add ToolWindow style, remove AppWindow style
            style = style | WS_EX_TOOLWINDOW
            style = style & ~WS_EX_APPWINDOW
            
            ctypes.windll.user32.SetWindowLongW(hwnd, GWL_EXSTYLE, style)
            logger.info("✅ Notes window hidden from taskbar.")
        except Exception as e:
            logger.error(f"❌ Error hiding from taskbar: {e}")

    def apply_hidden_affinity(self):
        try:
            # Constant for WDA_EXCLUDEFROMCAPTURE
            WDA_EXCLUDEFROMCAPTURE = 0x00000011
            
            self.root.update() # Ensure window is created
            
            # Get HWND
            hwnd = ctypes.windll.user32.GetParent(self.root.winfo_id())
            if hwnd == 0:
                hwnd = self.root.winfo_id()
                
            res = ctypes.windll.user32.SetWindowDisplayAffinity(hwnd, WDA_EXCLUDEFROMCAPTURE)
            if res:
                logger.info("✅ Notes window hidden from screen capture.")
            else:
                logger.warning("⚠️ Failed to set window affinity.")
        except Exception as e:
            logger.error(f"❌ Error setting window affinity: {e}")

    def toggle(self):
        if self.is_visible:
            self.hide_window()
        else:
            self.show_window()

    def show_window(self):
        self.root.deiconify()
        self.is_visible = True
        self.root.attributes("-topmost", True) # Ensure it stays on top when shown
        self.text_area.focus_set()

    def hide_window(self):
        self.save_notes()
        self.root.withdraw()
        self.is_visible = False

    def save_notes(self):
        try:
            content = self.text_area.get("1.0", tk.END)
            with open(config.NOTES_FILE, "w", encoding="utf-8") as f:
                f.write(content)
        except Exception as e:
            logger.error(f"❌ Failed to save notes: {e}")

    def load_notes(self):
        if os.path.exists(config.NOTES_FILE):
            try:
                with open(config.NOTES_FILE, "r", encoding="utf-8") as f:
                    content = f.read()
                    self.text_area.delete("1.0", tk.END)
                    self.text_area.insert("1.0", content)
            except Exception as e:
                logger.error(f"❌ Failed to load notes: {e}")

    def move(self, dx, dy):
        """Moves the window by dx, dy pixels."""
        if not self.is_visible:
            return
        try:
            x = self.root.winfo_x()
            y = self.root.winfo_y()
            new_x = x + dx
            new_y = y + dy
            # We must preserve width and height. 
            # geometry() returns "WxH+X+Y" usually.
            # But winfo_width/height are safer.
            w = self.root.winfo_width()
            h = self.root.winfo_height()
            self.root.geometry(f"{w}x{h}+{new_x}+{new_y}")
        except Exception as e:
            logger.error(f"Error moving window: {e}")

    def run(self):
        self.root.mainloop()

# Global instance
notes_app = None

def toggle_notes():
    if notes_app:
        # Schedule the toggle in the main thread
        notes_app.root.after(0, notes_app.toggle)

def move_notes(dx, dy):
    if notes_app:
        notes_app.root.after(0, lambda: notes_app.move(dx, dy))

if __name__ == "__main__":
    # Test the window independently
    app = HiddenNotesWindow()
    notes_app = app
    # Bind a test key to toggle, e.g., just show it initially
    app.show_window()
    app.run()
