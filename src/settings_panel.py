import tkinter as tk
import customtkinter as ctk
from tkinter import messagebox
import os
import sys

try:
    import settings_manager
except ImportError:
    settings_manager = None

try:
    import config
except ImportError:
    config = None

try:
    import ctypes
    CTYPES_AVAILABLE = True
except ImportError:
    CTYPES_AVAILABLE = False

try:
    from logger_setup import logger
except ImportError:
    import logging
    logger = logging.getLogger(__name__)


_panel_instance = None


# ── Palette ───────────────────────────────────────────────────────────────────
BG_ROOT      = "#0d0d0f"
BG_SIDEBAR   = "#111113"
BG_CARD      = "#181820"
BG_FIELD     = "#1c1c24"
BG_HOVER     = "#1e1e28"
BORDER       = "#252530"
BORDER_SOFT  = "#1a1a22"
TEXT_PRIMARY = "#e2e2e8"
TEXT_MUTED   = "#6b6b80"
TEXT_DIM     = "#3a3a50"
TEXT_FAINT   = "#2e2e3a"
GREEN        = "#4ade80"
GREEN_DIM    = "#162d20"
ACCENT_BAR   = "#4ade80"
RED          = "#f87171"
RED_DIM      = "#2e1515"

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("dark-blue")

SANS = "DM Sans"        if sys.platform != "win32" else "Segoe UI"
MONO = "JetBrains Mono" if sys.platform != "win32" else "Consolas"

# ── Window geometry ───────────────────────────────────────────────────────────
WIN_W      = 660
WIN_H      = 580   # slightly taller to fit the extra tertiary key field
TOP_LEFT_X = 10
TOP_LEFT_Y = 10

# ── Hotkey → config attribute map ─────────────────────────────────────────────
HOTKEY_CONFIG_MAP = [
    ("CAPTURE_CONTEXT_HOTKEY",       "capture_context"),
    ("CAPTURE_QUESTION_HOTKEY",      "capture_question"),
    ("CLEAR_CONTEXT_HOTKEY",         "clear_context"),
    ("EXIT_HOTKEY",                  "exit"),
    ("CAPTURE_SUBJECTIVE_HOTKEY",    "capture_subjective"),
    ("GENERATE_RESPONSE_HOTKEY",     "generate_response"),
    ("TYPE_RESPONSE_HOTKEY",         "type_response"),
    ("RESUME_TYPING_HOTKEY",         "resume_typing"),
    ("RETRY_SUBJECTIVE_HOTKEY",      "retry_subjective"),
    ("TOGGLE_NOTES_HOTKEY",          "toggle_notes"),
    ("TOGGLE_EXPLANATION_HOTKEY",    "toggle_explanation"),
    ("EXPLAIN_CODE_HOTKEY",          "explain_code"),
    ("CONTROL_PANEL_HOTKEY",         "control_panel"),
    ("STEP_BY_STEP_SOLUTION_HOTKEY", "step_by_step_solution"),
    ("MOVE_NOTES_UP_HOTKEY",         "move_notes_up"),
    ("MOVE_NOTES_DOWN_HOTKEY",       "move_notes_down"),
    ("MOVE_NOTES_LEFT_HOTKEY",       "move_notes_left"),
    ("MOVE_NOTES_RIGHT_HOTKEY",      "move_notes_right"),
]


# ── Helpers ───────────────────────────────────────────────────────────────────
def _env_path():
    return os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".env"))


def _read_env(path):
    data = {}
    if not os.path.exists(path):
        return data
    try:
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, v = line.split("=", 1)
                data[k.strip()] = v.strip()
    except Exception as e:
        logger.error(f"Error reading .env: {e}")
    return data



def _card(parent, **kw):
    return ctk.CTkFrame(
        parent, fg_color=BG_CARD,
        corner_radius=8, border_width=1, border_color=BORDER, **kw)


def _section(parent, text):
    ctk.CTkLabel(
        parent, text="  ".join(text.upper()),
        font=(SANS, 8), text_color=TEXT_DIM,
    ).pack(anchor="w", pady=(0, 6))


def _field_lbl(parent, text, tag=None):
    row = ctk.CTkFrame(parent, fg_color="transparent")
    row.pack(anchor="w", pady=(8, 2))
    ctk.CTkLabel(row, text=text, font=(SANS, 11),
                 text_color=TEXT_MUTED).pack(side="left")
    if tag:
        ctk.CTkLabel(
            row, text=tag, font=(SANS, 9),
            fg_color=GREEN_DIM, corner_radius=20,
            text_color=GREEN, padx=6, pady=1,
        ).pack(side="left", padx=(6, 0))


def _entry(parent, var, show=None, mono=False, placeholder_text=None):
    kw = {}
    if placeholder_text:
        kw["placeholder_text"] = placeholder_text
    e = ctk.CTkEntry(
        parent, textvariable=var, height=32,
        fg_color=BG_FIELD, border_color=BORDER, border_width=1,
        text_color=TEXT_PRIMARY, placeholder_text_color=TEXT_DIM,
        font=(MONO if mono else SANS, 10 if mono else 12),
        show=show or "", corner_radius=7, **kw)
    e.pack(fill="x")
    return e


def _divider(parent):
    ctk.CTkFrame(parent, fg_color=BORDER_SOFT,
                 height=1, corner_radius=0).pack(fill="x")


# ── Main window ───────────────────────────────────────────────────────────────
class SettingsPanel(ctk.CTkToplevel):
    def __init__(self, master=None, restart_callback=None):
        super().__init__(master)
        self.restart_callback = restart_callback

        self.overrideredirect(True)
        self.title("")
        self.geometry(f"{WIN_W}x{WIN_H}+{TOP_LEFT_X}+{TOP_LEFT_Y}")
        self.resizable(False, False)
        self.configure(fg_color=BG_ROOT)

        self.settings = settings_manager.load_settings() if settings_manager else {}
        self.env_map  = _read_env(_env_path())

        # Drag state
        self._drag_x   = 0
        self._drag_y   = 0
        self._dragging = False

        self._hide_taskbar()
        self._build_shell()
        self._build_action_bar()

        self.after(30, self._snap_top_left)
        self.attributes("-topmost", True)
        self.lift()
        self.focus_force()
        self.protocol("WM_DELETE_WINDOW", self._on_close)

    # ── Placement ─────────────────────────────────────────────────────────────
    def _snap_top_left(self):
        try:
            if not self.winfo_exists():
                return
            self.update_idletasks()
            self.geometry(f"{WIN_W}x{WIN_H}+{TOP_LEFT_X}+{TOP_LEFT_Y}")
        except Exception:
            pass

    # ── Hide from taskbar (Windows) ───────────────────────────────────────────
    def _hide_taskbar(self):
        if not CTYPES_AVAILABLE or sys.platform != "win32":
            return
        try:
            self.update()
            hwnd = ctypes.windll.user32.GetParent(self.winfo_id()) or self.winfo_id()
            style = ctypes.windll.user32.GetWindowLongW(hwnd, -20)
            ctypes.windll.user32.SetWindowLongW(
                hwnd, -20, (style | 0x80) & ~0x40000)
        except Exception as e:
            logger.error(f"Taskbar hide error: {e}")

    # ── Drag ──────────────────────────────────────────────────────────────────
    def _start_drag(self, event):
        self._drag_x   = event.x_root - self.winfo_x()
        self._drag_y   = event.y_root - self.winfo_y()
        self._dragging = False

    def _do_drag(self, event):
        self._dragging = True
        self.geometry(f"+{event.x_root - self._drag_x}+{event.y_root - self._drag_y}")

    # ── Shell ─────────────────────────────────────────────────────────────────
    def _build_shell(self):
        shell = ctk.CTkFrame(self, fg_color="transparent")
        shell.pack(fill="both", expand=True)

        sidebar = ctk.CTkFrame(shell, fg_color=BG_SIDEBAR,
                               corner_radius=0, width=150)
        sidebar.pack(side="left", fill="y")
        sidebar.pack_propagate(False)
        sidebar.bind("<ButtonPress-1>", self._start_drag)
        sidebar.bind("<B1-Motion>",     self._do_drag)

        ctk.CTkFrame(shell, fg_color=BORDER, width=1,
                     corner_radius=0).pack(side="left", fill="y")

        ctk.CTkLabel(sidebar, text="LULU", font=(SANS, 13, "bold"),
                     text_color=GREEN).pack(anchor="w", padx=14, pady=(14, 1))
        ctk.CTkLabel(sidebar, text="Control Panel",
                     font=(SANS, 9), text_color=TEXT_DIM
                     ).pack(anchor="w", padx=14, pady=(0, 8))
        ctk.CTkFrame(sidebar, fg_color=BORDER, height=1,
                     corner_radius=0).pack(fill="x", padx=10, pady=(0, 6))

        NAV = [
            ("General",  "✦", "general"),
            ("Settings", "⚙", "settings"),
            ("Hotkeys",  "⊞", "hotkeys"),
        ]
        self._nav_btns       = {}
        self._nav_indicators = {}

        for name, icon, key in NAV:
            row = ctk.CTkFrame(sidebar, fg_color="transparent", height=38)
            row.pack(fill="x")
            row.pack_propagate(False)

            indicator = ctk.CTkFrame(row, fg_color=ACCENT_BAR,
                                     width=3, height=28, corner_radius=0)
            self._nav_indicators[key] = indicator

            btn = ctk.CTkButton(
                row,
                text=f"  {icon}  {name}",
                fg_color="transparent",
                hover_color=BG_HOVER,
                text_color=TEXT_MUTED,
                anchor="w",
                corner_radius=0,
                height=38,
                font=(SANS, 12),
                command=lambda k=key: self._nav_clicked(k),
            )
            btn.place(x=0, y=0, relwidth=1, relheight=1)
            self._nav_btns[key] = btn

            btn.bind("<ButtonPress-1>", self._start_drag)
            btn.bind("<B1-Motion>",     self._do_drag)

        ctk.CTkLabel(sidebar, text="v1.0.0",
                     font=(SANS, 9), text_color="#2a2a38"
                     ).pack(side="bottom", pady=10)

        self._content_host = ctk.CTkFrame(shell, fg_color="transparent")
        self._content_host.pack(side="left", fill="both", expand=True)
        self._content_host.grid_rowconfigure(0, weight=1)
        self._content_host.grid_columnconfigure(0, weight=1)

        self._tabs        = {}
        self._current_tab = None
        self._build_general()
        self._build_settings_tab()
        self._build_hotkeys()
        self._switch("general")

    def _nav_clicked(self, key):
        if self._dragging:
            self._dragging = False
            return
        self._switch(key)

    def _switch(self, key):
        if self._current_tab == key:
            return
        for k, frame in self._tabs.items():
            frame.grid_remove()
            self._nav_btns[k].configure(
                text_color=TEXT_MUTED, fg_color="transparent")
            self._nav_indicators[k].place_forget()

        self._tabs[key].grid(row=0, column=0, sticky="nsew")
        self._tabs[key].update_idletasks()
        self._nav_btns[key].configure(
            text_color=TEXT_PRIMARY, fg_color=BG_HOVER)
        self._nav_indicators[key].place(x=0, y=5)
        self._current_tab = key

    def _scrollable(self, key):
        f = ctk.CTkScrollableFrame(
            self._content_host,
            fg_color="transparent",
            scrollbar_button_color=BORDER,
            scrollbar_button_hover_color=BG_HOVER,
        )
        f.grid(row=0, column=0, sticky="nsew")
        f.grid_remove()
        self._tabs[key] = f
        return f

    # ── General tab ───────────────────────────────────────────────────────────
    def _build_general(self):
        tab = self._scrollable("general")
        PAD = dict(padx=16, pady=(12, 0))

        # ── Dynamic Gemini API Keys card ──────────────────────────────────
        w = ctk.CTkFrame(tab, fg_color="transparent")
        w.pack(fill="x", **PAD)

        # Section header row with show/hide toggle
        header_row = ctk.CTkFrame(w, fg_color="transparent")
        header_row.pack(fill="x", pady=(0, 6))
        ctk.CTkLabel(
            header_row, text="  ".join("GEMINI API KEYS".upper()),
            font=(SANS, 8), text_color=TEXT_DIM,
        ).pack(side="left")
        self._show_keys_btn = ctk.CTkButton(
            header_row, text="Show Keys",
            fg_color="transparent", hover_color=BG_HOVER,
            text_color=TEXT_DIM, border_width=1, border_color=BORDER,
            corner_radius=6, height=24, width=100,
            font=(SANS, 10),
            command=self._toggle_key_visibility,
        )
        self._show_keys_btn.pack(side="right")

        c = _card(w)
        c.pack(fill="x")
        self._gemini_keys_card = c
        self._gemini_keys_inner = ctk.CTkFrame(c, fg_color="transparent")
        self._gemini_keys_inner.pack(fill="x", padx=14, pady=(6, 4))

        # List of (StringVar, row_frame) tuples — one per key
        self._gemini_key_rows: list[tuple[tk.StringVar, ctk.CTkFrame]] = []

        # Track all key entry widgets for show/hide toggle
        self._all_key_entries: list[ctk.CTkEntry] = []
        self._keys_visible: bool = False

        # Load existing keys
        existing_keys = list(self.settings.get("gemini_api_keys", []))
        # Backward compat: also pull from legacy fixed fields if list is empty
        if not existing_keys:
            for field in ("api_key", "api_key_secondary", "api_key_tertiary"):
                raw = self.settings.get(field, "")
                cleaned = self._clean_key(raw) if raw else ""
                if cleaned and cleaned not in existing_keys:
                    existing_keys.append(cleaned)
        # Also check env vars as fallback
        if not existing_keys:
            for env_var in ("GEMINI_API_KEY_PRIMARY", "GEMINI_API_KEY",
                            "GEMINI_API_KEY_SECONDARY", "GEMINI_API_KEY_TERTIARY"):
                val = self.env_map.get(env_var, "")
                if val and val not in existing_keys:
                    existing_keys.append(val)

        # Ensure at least one empty row so the UI isn't blank on first run
        if not existing_keys:
            existing_keys = [""]

        for key_val in existing_keys:
            self._add_gemini_key_row(key_val)

        # "+ Add Key" button
        self._gemini_add_btn_frame = ctk.CTkFrame(c, fg_color="transparent")
        self._gemini_add_btn_frame.pack(fill="x", padx=14, pady=(2, 10))
        ctk.CTkButton(
            self._gemini_add_btn_frame,
            text="＋  Add Gemini Key",
            fg_color="transparent",
            hover_color=GREEN_DIM,
            text_color=GREEN,
            border_width=1,
            border_color=BORDER,
            corner_radius=7,
            height=30,
            font=(SANS, 11),
            command=self._on_add_gemini_key,
        ).pack(fill="x")

        # Key count label
        self._gemini_count_lbl = ctk.CTkLabel(
            self._gemini_add_btn_frame,
            text="",
            font=(SANS, 9),
            text_color=TEXT_DIM,
        )
        self._gemini_count_lbl.pack(anchor="w", pady=(3, 0))
        self._update_gemini_count_label()

        # ── Other provider keys ───────────────────────────────────────────
        w2 = ctk.CTkFrame(tab, fg_color="transparent")
        w2.pack(fill="x", **PAD)
        _section(w2, "Other Providers")
        c2 = _card(w2)
        c2.pack(fill="x")
        inn2 = ctk.CTkFrame(c2, fg_color="transparent")
        inn2.pack(fill="x", padx=14, pady=(6, 12))

        _field_lbl(inn2, "OpenRouter Key")
        self.openrouter_api_var = tk.StringVar(
            value=self.settings.get("openrouter_api_key",
                                   self.env_map.get("OPENROUTER_API_KEY", "")))
        self._openrouter_entry = _entry(inn2, self.openrouter_api_var, show="*", placeholder_text="Optional")
        self._all_key_entries.append(self._openrouter_entry)

        _field_lbl(inn2, "Groq Key")
        self.groq_api_var = tk.StringVar(
            value=self.settings.get("groq_api_key",
                                   self.env_map.get("GROQ_API_KEY", "")))
        self._groq_entry = _entry(inn2, self.groq_api_var, show="*", placeholder_text="Optional")
        self._all_key_entries.append(self._groq_entry)

        # Model + Features row
        row2 = ctk.CTkFrame(tab, fg_color="transparent")
        row2.pack(fill="x", **PAD)
        row2.columnconfigure((0, 1), weight=1)

        wm = ctk.CTkFrame(row2, fg_color="transparent")
        wm.grid(row=0, column=0, sticky="ew", padx=(0, 5))
        _section(wm, "Model")
        cm = _card(wm)
        cm.pack(fill="x")
        inm = ctk.CTkFrame(cm, fg_color="transparent")
        inm.pack(fill="x", padx=14, pady=(8, 12))
        self.model_var = tk.StringVar(
            value=self.settings.get("model_name", "gemini-2.5-flash"))
        ctk.CTkComboBox(
            inm, variable=self.model_var,
            values=["gemini-3-flash-preview", "gemini-3.7-flash", "gemini-3.6-flash","gemini-3.5-flash", "gemini-2.5-pro", "gemini-3.5-flash-lite"],
            state="readonly", height=32, corner_radius=7,
            fg_color=BG_FIELD, border_color=BORDER, border_width=1,
            text_color=TEXT_PRIMARY, button_color=BORDER,
            button_hover_color=BG_HOVER, dropdown_fg_color=BG_CARD,
            dropdown_text_color=TEXT_PRIMARY, dropdown_hover_color=BG_HOVER,
            font=(SANS, 12),
        ).pack(fill="x")

        wf = ctk.CTkFrame(row2, fg_color="transparent")
        wf.grid(row=0, column=1, sticky="ew", padx=(5, 0))
        _section(wf, "Features")
        cf = _card(wf)
        cf.pack(fill="x")
        inf = ctk.CTkFrame(cf, fg_color="transparent")
        inf.pack(fill="x", padx=14, pady=(8, 12))
        feats = self.settings.get("features", {})
        self.notes_var   = tk.BooleanVar(value=feats.get("notes_enabled", True))
        self.explain_var = tk.BooleanVar(value=feats.get("explanation_enabled", True))
        for text, var in [("Hidden Notes", self.notes_var),
                          ("Code Explain",  self.explain_var)]:
            ctk.CTkCheckBox(
                inf, text=text, variable=var,
                font=(SANS, 11), text_color=TEXT_PRIMARY,
                fg_color=GREEN_DIM, checkmark_color=GREEN,
                hover_color=BG_HOVER, border_color="#333344", corner_radius=4,
            ).pack(anchor="w", pady=3)

        # Window Dimensions
        w4 = ctk.CTkFrame(tab, fg_color="transparent")
        w4.pack(fill="x", padx=16, pady=(12, 14))
        _section(w4, "Window Dimensions")
        c4 = _card(w4)
        c4.pack(fill="x")
        inn4 = ctk.CTkFrame(c4, fg_color="transparent")
        inn4.pack(fill="x", padx=14, pady=(8, 12))
        ws = self.settings.get("window_size", {})
        self.nw_var = tk.IntVar(value=ws.get("notes_width",        400))
        self.nh_var = tk.IntVar(value=ws.get("notes_height",       300))
        self.ew_var = tk.IntVar(value=ws.get("explanation_width",  500))
        self.eh_var = tk.IntVar(value=ws.get("explanation_height", 400))
        grid4 = ctk.CTkFrame(inn4, fg_color="transparent")
        grid4.pack(fill="x")
        grid4.columnconfigure((0, 1, 2, 3), weight=1)
        for col, (lbl, var) in enumerate([
            ("Notes W", self.nw_var), ("Notes H", self.nh_var),
            ("Exp W",   self.ew_var), ("Exp H",   self.eh_var),
        ]):
            ctk.CTkLabel(grid4, text=lbl, font=(SANS, 10),
                         text_color=TEXT_MUTED).grid(
                row=0, column=col, padx=4, pady=(0, 2), sticky="w")
            ctk.CTkEntry(grid4, textvariable=var, height=30,
                         fg_color=BG_FIELD, border_color=BORDER,
                         text_color=TEXT_PRIMARY, corner_radius=7,
                         font=(MONO, 11)).grid(
                row=1, column=col, padx=4, sticky="ew")

    # ── Dynamic Gemini key row helpers ───────────────────────────────────────
    def _add_gemini_key_row(self, value: str = "") -> None:
        """Add one Gemini API key entry row with a label and remove button."""
        idx = len(self._gemini_key_rows) + 1
        row = ctk.CTkFrame(self._gemini_keys_inner, fg_color="transparent")
        row.pack(fill="x", pady=(4, 0))
        row.columnconfigure(1, weight=1)

        # Label: "Key 1", "Key 2", ...
        tag = None
        if idx == 1:
            tag = "Primary"
        elif idx > 1:
            tag = f"Failover {idx - 1}"
        lbl_row = ctk.CTkFrame(row, fg_color="transparent")
        lbl_row.grid(row=0, column=0, columnspan=2, sticky="w", pady=(2, 1))
        ctk.CTkLabel(lbl_row, text=f"Key {idx}",
                     font=(SANS, 11), text_color=TEXT_MUTED).pack(side="left")
        if tag:
            ctk.CTkLabel(
                lbl_row, text=tag, font=(SANS, 9),
                fg_color=GREEN_DIM, corner_radius=20,
                text_color=GREEN, padx=6, pady=1,
            ).pack(side="left", padx=(6, 0))

        # Entry + remove button row
        entry_row = ctk.CTkFrame(row, fg_color="transparent")
        entry_row.grid(row=1, column=0, columnspan=2, sticky="ew")
        entry_row.columnconfigure(0, weight=1)

        var = tk.StringVar(value=value)
        entry_widget = ctk.CTkEntry(
            entry_row, textvariable=var, height=32,
            fg_color=BG_FIELD, border_color=BORDER, border_width=1,
            text_color=TEXT_PRIMARY, placeholder_text_color=TEXT_DIM,
            font=(MONO, 10), show="*", corner_radius=7,
            placeholder_text="Paste your Gemini API key here",
        )
        entry_widget.grid(row=0, column=0, sticky="ew", padx=(0, 4))
        self._all_key_entries.append(entry_widget)

        # Remove button — only show if more than 1 key exists
        remove_btn = ctk.CTkButton(
            entry_row, text="✕", width=32, height=32,
            fg_color=RED_DIM, hover_color="#3d1a1a",
            text_color=RED, border_width=1, border_color="#5a2020",
            corner_radius=7, font=(SANS, 12),
            command=lambda r=row, v=var: self._remove_gemini_key_row(r, v),
        )
        remove_btn.grid(row=0, column=1)

        self._gemini_key_rows.append((var, row))
        self._refresh_remove_buttons()
        self._update_gemini_count_label()

    def _remove_gemini_key_row(self, row_frame: ctk.CTkFrame, var: tk.StringVar) -> None:
        """Remove a Gemini key row from the UI."""
        if len(self._gemini_key_rows) <= 1:
            return   # Must always have at least one row
        # Remove entry widget from tracking list before destroying
        for widget in row_frame.winfo_children():
            if isinstance(widget, ctk.CTkFrame):
                for child in widget.winfo_children():
                    if isinstance(child, ctk.CTkEntry) and child in self._all_key_entries:
                        self._all_key_entries.remove(child)
        self._gemini_key_rows = [
            (v, r) for v, r in self._gemini_key_rows if r is not row_frame
        ]
        row_frame.destroy()
        # Re-label remaining rows
        self._relabel_gemini_rows()
        self._refresh_remove_buttons()
        self._update_gemini_count_label()

    def _relabel_gemini_rows(self) -> None:
        """After a removal, rebuild row labels so numbering stays sequential."""
        for new_idx, (_var, row_frame) in enumerate(self._gemini_key_rows, start=1):
            # The first child of row_frame is the lbl_row (CTkFrame with labels)
            for child in row_frame.winfo_children():
                if isinstance(child, ctk.CTkFrame):
                    # Check if this is the label row (contains CTkLabel, no CTkEntry)
                    children = child.winfo_children()
                    if children and all(not isinstance(c, ctk.CTkEntry) for c in children):
                        # Destroy all label widgets and recreate
                        for c in children:
                            c.destroy()
                        ctk.CTkLabel(child, text=f"Key {new_idx}",
                                     font=(SANS, 11), text_color=TEXT_MUTED).pack(side="left")
                        tag = "Primary" if new_idx == 1 else f"Failover {new_idx - 1}"
                        ctk.CTkLabel(
                            child, text=tag, font=(SANS, 9),
                            fg_color=GREEN_DIM, corner_radius=20,
                            text_color=GREEN, padx=6, pady=1,
                        ).pack(side="left", padx=(6, 0))
                        break

    def _refresh_remove_buttons(self) -> None:
        """Show or hide remove buttons based on row count.

        If only 1 row exists, hide its remove button so the user can't
        delete the last key field.
        """
        for _var, row_frame in self._gemini_key_rows:
            for widget in row_frame.winfo_children():
                if isinstance(widget, ctk.CTkFrame):
                    for child in widget.winfo_children():
                        if isinstance(child, ctk.CTkButton) and child.cget("text") == "✕":
                            if len(self._gemini_key_rows) <= 1:
                                child.grid_remove()
                            else:
                                child.grid()

    def _on_add_gemini_key(self) -> None:
        """Handler for the '+ Add Key' button."""
        self._add_gemini_key_row("")

    def _update_gemini_count_label(self) -> None:
        """Update the count label below the add button."""
        n = len(self._gemini_key_rows)
        if hasattr(self, '_gemini_count_lbl'):
            self._gemini_count_lbl.configure(
                text=f"{n} key{'s' if n != 1 else ''} configured  •  Keys are tried in order on failure"
            )

    def _toggle_key_visibility(self) -> None:
        """Toggle show/hide for ALL API key entry fields."""
        self._keys_visible = not self._keys_visible
        show_char = "" if self._keys_visible else "*"

        for entry in self._all_key_entries:
            try:
                if entry.winfo_exists():
                    entry.configure(show=show_char)
            except Exception:
                pass

        if self._keys_visible:
            self._show_keys_btn.configure(
                text="Hide Keys",
                text_color=GREEN,
                border_color=GREEN,
            )
        else:
            self._show_keys_btn.configure(
                text="Show Keys",
                text_color=TEXT_DIM,
                border_color=BORDER,
            )

    def _collect_gemini_keys(self) -> list[str]:
        """Read all Gemini key StringVars, clean them, and return non-empty unique keys."""
        keys: list[str] = []
        for var, _row in self._gemini_key_rows:
            cleaned = self._clean_key(var.get())
            if cleaned and cleaned not in keys:
                keys.append(cleaned)
        return keys

    # ── Settings tab ──────────────────────────────────────────────────────────
    def _build_settings_tab(self):
        tab = self._scrollable("settings")
        w = ctk.CTkFrame(tab, fg_color="transparent")
        w.pack(fill="x", padx=16, pady=(12, 14))
        _section(w, "Typing Configuration")
        c = _card(w)
        c.pack(fill="x")
        inn = ctk.CTkFrame(c, fg_color="transparent")
        inn.pack(fill="x", padx=14, pady=(8, 12))
        typing = self.settings.get("typing", {})
        self.tmin_var = tk.DoubleVar(value=typing.get("min_delay", 0.03))
        self.tmax_var = tk.DoubleVar(value=typing.get("max_delay", 0.08))
        grid = ctk.CTkFrame(inn, fg_color="transparent")
        grid.pack(fill="x")
        grid.columnconfigure((0, 1), weight=1)
        for col, (lbl, var) in enumerate([
            ("Min Delay (sec)", self.tmin_var),
            ("Max Delay (sec)", self.tmax_var),
        ]):
            ctk.CTkLabel(grid, text=lbl, font=(SANS, 11),
                         text_color=TEXT_MUTED).grid(
                row=0, column=col, padx=6, pady=(0, 3), sticky="w")
            ctk.CTkEntry(grid, textvariable=var, height=32,
                         fg_color=BG_FIELD, border_color=BORDER,
                         text_color=TEXT_PRIMARY, corner_radius=7,
                         font=(MONO, 11)).grid(
                row=1, column=col, padx=6, sticky="ew")
        ctk.CTkLabel(
            inn, text="Lower = faster typing.  Higher = more human-like.",
            font=(SANS, 10), text_color=TEXT_FAINT,
        ).pack(anchor="w", pady=(10, 0))

    # ── Hotkeys tab ───────────────────────────────────────────────────────────
    def _build_hotkeys(self):
        tab = self._scrollable("hotkeys")
        w = ctk.CTkFrame(tab, fg_color="transparent")
        w.pack(fill="x", padx=16, pady=(12, 14))
        _section(w, "Hotkey Bindings")
        c = _card(w)
        c.pack(fill="x")
        self.hotkey_vars = {}
        hotkeys = self.settings.get("hotkeys", {})
        items   = list(hotkeys.items())
        for i, (key, value) in enumerate(items):
            row = ctk.CTkFrame(c, fg_color="transparent")
            row.pack(fill="x", padx=14)
            inner = ctk.CTkFrame(row, fg_color="transparent")
            inner.pack(fill="x", pady=5)
            inner.columnconfigure(1, weight=1)
            ctk.CTkLabel(
                inner,
                text=key.replace("_", " ").title(),
                font=(SANS, 11), text_color=TEXT_MUTED,
                width=190, anchor="w",
            ).grid(row=0, column=0, sticky="w", padx=(0, 12))
            var = tk.StringVar(value=value)
            self.hotkey_vars[key] = var
            ctk.CTkEntry(
                inner, textvariable=var, height=28,
                fg_color=BG_FIELD, border_color=BORDER,
                text_color=TEXT_PRIMARY, corner_radius=6,
                font=(MONO, 10),
            ).grid(row=0, column=1, sticky="ew")
            if i < len(items) - 1:
                _divider(row)
        ctk.CTkFrame(c, height=6, fg_color="transparent").pack()

    # ── Action bar ────────────────────────────────────────────────────────────
    def _build_action_bar(self):
        ctk.CTkFrame(self, fg_color=BORDER, height=1, corner_radius=0).pack(fill="x")
        bar = ctk.CTkFrame(self, fg_color=BG_ROOT, corner_radius=0, height=54)
        bar.pack(fill="x")
        bar.pack_propagate(False)
        inn = ctk.CTkFrame(bar, fg_color="transparent")
        inn.pack(fill="both", expand=True, padx=14, pady=10)
        inn.columnconfigure((0, 1, 2), weight=1)
        btn_cfg = dict(
            fg_color="transparent", hover_color=BG_HOVER,
            text_color=TEXT_PRIMARY, border_width=1, border_color=BORDER,
            corner_radius=8, height=34, font=(SANS, 12),
        )
        ctk.CTkButton(inn, text="Save",
                      command=self._save, **btn_cfg
                      ).grid(row=0, column=0, padx=(0, 5), sticky="ew")
        ctk.CTkButton(inn, text="Restart AI",
                      command=self._restart, **btn_cfg
                      ).grid(row=0, column=1, padx=5, sticky="ew")
        ctk.CTkButton(
            inn, text="Stop AI", command=self._stop,
            fg_color=RED_DIM, hover_color="#3d1a1a",
            border_color="#5a2020", text_color=RED,
            border_width=1, corner_radius=8, height=34, font=(SANS, 12),
        ).grid(row=0, column=2, padx=(5, 0), sticky="ew")

    # ── Save ──────────────────────────────────────────────────────────────────
    @staticmethod
    def _clean_key(raw: str) -> str:
        """Strip whitespace and accidental surrounding quotes from an API key."""
        return raw.strip().strip(chr(34) + chr(39))

    def _save(self):
        if not settings_manager:
            messagebox.showwarning("Unavailable", "settings_manager not found.")
            return

        ns = self.settings.copy()

        # ── Gemini keys: collect from dynamic rows ────────────────────────
        gemini_keys = self._collect_gemini_keys()
        if not gemini_keys:
            messagebox.showerror("Error", "At least one Gemini API key is required.")
            return
        ns["gemini_api_keys"] = gemini_keys

        # Remove legacy fixed fields if they exist (fully migrated)
        for legacy in ("api_key", "api_key_secondary", "api_key_tertiary"):
            ns.pop(legacy, None)

        ns["model_name"]        = self.model_var.get()
        ns["openrouter_api_key"] = self._clean_key(self.openrouter_api_var.get())
        ns["groq_api_key"]       = self._clean_key(self.groq_api_var.get())
        ns.setdefault("features", {})
        ns["features"]["notes_enabled"]       = self.notes_var.get()
        ns["features"]["explanation_enabled"] = self.explain_var.get()
        ns.setdefault("typing", {})
        ns.setdefault("window_size", {})
        try:
            ns["window_size"]["notes_width"]        = self.nw_var.get()
            ns["window_size"]["notes_height"]       = self.nh_var.get()
            ns["window_size"]["explanation_width"]  = self.ew_var.get()
            ns["window_size"]["explanation_height"] = self.eh_var.get()
            ns["typing"]["min_delay"] = self.tmin_var.get()
            ns["typing"]["max_delay"] = self.tmax_var.get()
        except (ValueError, tk.TclError):
            messagebox.showerror("Error", "Numeric fields must contain valid numbers.")
            return

        seen = []
        for key, var in self.hotkey_vars.items():
            val = var.get()
            if val in seen:
                messagebox.showerror("Error", f"Duplicate hotkey: {val}")
                return
            seen.append(val)
            ns["hotkeys"][key] = val

        settings_manager.save_settings(ns)

        # ── Sync in-memory current_settings so any module that reads
        #    from settings_manager.current_settings sees fresh data ─────────
        settings_manager.current_settings.update(ns)

        # ── Hot-update config module in-memory ────────────────────────────
        if config:
            config.GEMINI_API_KEYS = gemini_keys
            config.API_KEY           = gemini_keys[0] if len(gemini_keys) > 0 else ""
            config.API_KEY_SECONDARY = gemini_keys[1] if len(gemini_keys) > 1 else ""
            config.API_KEY_TERTIARY  = gemini_keys[2] if len(gemini_keys) > 2 else ""
            config.MODEL_NAME        = ns["model_name"]
            # Keep classification model in sync — it reads from settings too
            if hasattr(config, "CLASSIFICATION_MODEL"):
                config.CLASSIFICATION_MODEL = ns.get(
                    "classification_model",
                    getattr(config, "CLASSIFICATION_MODEL", "gemini-2.5-flash-lite"),
                )
            if hasattr(config, "OPENROUTER_API_KEY"):
                config.OPENROUTER_API_KEY = self._clean_key(self.openrouter_api_var.get())
            if hasattr(config, "GROQ_API_KEY"):
                config.GROQ_API_KEY = self._clean_key(self.groq_api_var.get())
            config.TYPING_DELAY_MIN = ns["typing"]["min_delay"]
            config.TYPING_DELAY_MAX = ns["typing"]["max_delay"]
            hk = ns.get("hotkeys", {})
            for attr, key in HOTKEY_CONFIG_MAP:
                if key in hk and hasattr(config, attr):
                    setattr(config, attr, hk[key])

        messagebox.showinfo("Saved", f"Settings saved — {len(gemini_keys)} Gemini key(s).\nRestart AI to apply all changes.")

        # Clear cached Gemini clients so new keys take effect immediately
        try:
            from ai_core import clear_client_cache
            clear_client_cache()
        except Exception:
            pass  # Module may not be loaded in standalone panel mode

        # Clear subjective caches — stale responses generated with old
        # keys/models must not be served after a settings change.
        try:
            import state
            state.reset_subjective_caches()
            from subjective_handlers import clear_image_cache
            clear_image_cache()
        except Exception:
            pass

    def _restart(self):
        if self.restart_callback:
            self.destroy()
            self.restart_callback()
        else:
            messagebox.showinfo("Info", "Restart not linked.")

    def _stop(self):
        if messagebox.askyesno("Confirm", "Stop the AI Assistant completely?"):
            self.destroy()
            os._exit(0)

    def _on_close(self):
        self.destroy()

    def destroy(self):
        global _panel_instance
        _panel_instance = None
        try:
            super().destroy()
        except Exception:
            pass


# ── Entry point ───────────────────────────────────────────────────────────────
def show_control_panel(restart_callback=None, master=None):
    global _panel_instance
    if _panel_instance is not None:
        try:
            if _panel_instance.winfo_exists():
                _panel_instance.destroy()
                return None
        except Exception:
            pass
        _panel_instance = None
    panel = SettingsPanel(master=master, restart_callback=restart_callback)
    _panel_instance = panel
    if master is None:
        panel.mainloop()
    return panel


if __name__ == "__main__":
    show_control_panel()