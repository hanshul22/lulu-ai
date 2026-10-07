# 🤖 Lulu AI Assistant

An AI-powered screen assistant that solves MCQs, generates code/theory answers, and auto-types responses — all controlled by global hotkeys. Powered by Google Gemini, Groq, and OpenRouter.

---

## ⚡ Install

```bash
pip install lulu-ai
```

If `lulu` is not recognized after installing, run this once to fix it:

```bash
python -m lulu_cli fix-path
```

Then **close and reopen your terminal**. The `lulu` command will work from anywhere permanently.

---

## 🔑 First Time Setup

After installing, run:

```bash
lulu start
```

The settings panel opens automatically. Enter your API keys:

| Key | Where to get it | Required |
|---|---|---|
| Gemini API key | https://aistudio.google.com/app/apikey | ✅ Required |
| Groq API key | https://console.groq.com/keys | Recommended |
| OpenRouter API key | https://openrouter.ai/keys | Recommended |

Click **Save** — done. From now on `lulu start` works from any folder, any terminal, forever.

---

## 🖥️ CLI Commands

```bash
lulu start              # Start the assistant in the background
lulu stop               # Stop the assistant
lulu status             # Check if it's running
lulu logs               # Show last 50 log lines
lulu logs --follow      # Stream logs live
lulu logs --lines 100   # Show last 100 lines
lulu doctor             # Diagnose your environment
lulu fix-path           # Fix PATH so lulu works from any terminal
lulu --version          # Show installed version
```

---

## ✨ Features

### MCQ Mode
- Captures a question and any number of options from the screen
- Optionally uses a context screenshot for reading comprehension questions
- Automatically identifies the correct option and clicks it

### Subjective / Coding Mode
- Captures one or more screenshots of a question
- Classifies question type (DSA, SQL, theory) automatically
- Generates a detailed code or text answer
- Auto-types the response with human-like delays
- Supports pausing and resuming auto-typing

### Step-by-Step Solution
- Generates a detailed step-by-step breakdown
- Shown in a dedicated explanation window

### Stealth Tools
- Hidden notes window — invisible to screen sharing (Zoom, Teams, OBS)
- Code explanation window with summary, dry run, and complexity analysis
- Both windows movable with hotkeys

### Control Panel
- Change API keys, hotkeys, typing speed, and window sizes live
- Press `Ctrl+Alt+M` to open

---

## ⌨️ Hotkey Reference

| Hotkey | Action |
|---|---|
| `Ctrl+Alt+C` | Capture context passage for an MCQ |
| `Ctrl+Alt+P` | Capture question and options for an MCQ |
| `Ctrl+Alt+S` | Capture screenshot for a subjective question |
| `Ctrl+Alt+G` | Generate AI response from screenshots |
| `Ctrl+Alt+T` | Auto-type the generated response |
| `Ctrl+Alt+Z` | Resume a paused auto-typing session |
| `Ctrl+Alt+K` | Retry with error screenshot |
| `Ctrl+Alt+J` | Explain code (summary, dry run, complexity) |
| `Ctrl+Alt+O` | Step-by-step solution |
| `Ctrl+Alt+N` | Toggle hidden notes window |
| `Ctrl+Alt+A` | Toggle explanation window |
| `Ctrl+Alt+M` | Open control panel |
| `Ctrl+Alt+Arrows` | Move the active stealth window |
| `Ctrl+Alt+R` | Clear all captured context and screenshots |
| `Ctrl+Alt+E` | Exit |

---

## 🔄 AI Provider Routing

| Task | Primary | Fallback |
|---|---|---|
| MCQ solving | Gemini | Gemini (secondary key) |
| Code generation | Groq | OpenRouter → Gemini |
| Theory answers | Groq | Gemini |
| Code explanation | Groq | Gemini |

All providers retry automatically on rate limits before failing over.

---

## 🛠️ Troubleshooting

**`lulu` not recognized after install**
```bash
python -m lulu_cli fix-path
```
Then close and reopen your terminal.

**Settings panel doesn't open**
→ Run `lulu doctor` to check your environment
→ Check logs with `lulu logs`

**Gemini quota exceeded**
→ Open control panel (`Ctrl+Alt+M`) and switch model to `gemini-2.5-flash`
→ Add a secondary Gemini key for automatic failover

**Garbled text when auto-typing resumes**
→ Wait 0.4 seconds after pressing `Ctrl+Alt+Z` before typing starts

**macOS: hotkeys not working**
→ System Settings → Privacy & Security → Accessibility → add Terminal

---

## 📋 Requirements

- Python 3.9+
- Windows / macOS / Linux
- Google Gemini API key (required)
- Groq API key (recommended)
- OpenRouter API key (recommended)

---

## 📄 License

MIT License