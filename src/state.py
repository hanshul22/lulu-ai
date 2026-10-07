import threading

# ---------------------------------------------------------------------------
# Locks for compound read-then-act operations
#
# Python's GIL protects single bytecode operations (simple reads/writes of
# basic types), but NOT compound check-then-act patterns like:
#
#   if state.correct_index_global is not None:
#       # thread switch can happen HERE
#       click(state.correct_index_global)   # value may have changed
#
# The locks below guard the two groups of state that are both written by
# background AI worker threads and read by the hotkey/UI threads.
# ---------------------------------------------------------------------------

# Protects: correct_index_global, option_positions_global
mcq_result_lock = threading.Lock()

# Protects: ai_response_text, subjective_question_answered,
#           screenshots_count_at_generation, subjective_screenshots,
#           all cached_* fields
subjective_lock = threading.Lock()

# ---------------------------------------------------------------------------
# Global state
# ---------------------------------------------------------------------------

context_captured = False
subjective_screenshots: list[str] = []   # List of paths: ['1.png', '2.png', ...]
ai_response_text: str | None = None      # Stores AI response for typing
screenshots_count_at_generation = 0      # Tracks how many screenshots existed when AI generated answer

# Typing state variables
is_typing_active = False
is_typing_paused = False
current_typing_position = 0
resume_typing_event = threading.Event()

# Shared state for MCQ coordination
ai_response_ready = threading.Event()
option_positions_ready = threading.Event()
correct_index_global: int | None = None
option_positions_global: list | None = None

# Flag to indicate if a subjective response was generated
subjective_question_answered = False

# Shared state for subjective mode
ai_response_ready_subjective = threading.Event()

# Caches to reduce repeated AI calls when screenshots are unchanged
cached_question_type: str | None = None
cached_question_type_count = 0
cached_coding_sql_question_text: str | None = None
cached_coding_sql_question_text_count = 0
cached_non_coding_question_text: str | None = None
cached_non_coding_question_text_count = 0

# Response-level cache — keyed by hash(screenshot_bytes + prompt_type).
# If the user presses Ctrl+Alt+G again on the exact same screenshots
# the cached response is returned instantly (zero API calls).
cached_response_hash: str | None = None
cached_response_text: str | None = None


# ---------------------------------------------------------------------------
# Thread-safe helpers for MCQ result
# ---------------------------------------------------------------------------

def set_mcq_result(index: int, positions: list) -> None:
    """Atomically store the AI answer index and option positions together."""
    global correct_index_global, option_positions_global
    with mcq_result_lock:
        correct_index_global = index
        option_positions_global = positions


def get_mcq_result() -> tuple[int | None, list | None]:
    """Atomically read the AI answer index and option positions together."""
    with mcq_result_lock:
        return correct_index_global, option_positions_global


# ---------------------------------------------------------------------------
# Thread-safe helper for AI response text
# ---------------------------------------------------------------------------

def set_ai_response(text: str | None) -> None:
    """Store the AI response text under the subjective lock."""
    global ai_response_text
    with subjective_lock:
        ai_response_text = text


def get_ai_response() -> str | None:
    """Read the AI response text under the subjective lock."""
    with subjective_lock:
        return ai_response_text


# ---------------------------------------------------------------------------
# Cache reset
# ---------------------------------------------------------------------------

def reset_subjective_caches() -> None:
    """Reset all subjective caches to prevent old question data from being reused."""
    global cached_question_type, cached_question_type_count
    global cached_coding_sql_question_text, cached_coding_sql_question_text_count
    global cached_non_coding_question_text, cached_non_coding_question_text_count
    global cached_response_hash, cached_response_text
    global ai_response_text, subjective_question_answered
    global screenshots_count_at_generation, subjective_screenshots
    global is_typing_active, is_typing_paused, current_typing_position

    with subjective_lock:
        cached_question_type = None
        cached_question_type_count = 0
        cached_coding_sql_question_text = None
        cached_coding_sql_question_text_count = 0
        cached_non_coding_question_text = None
        cached_non_coding_question_text_count = 0
        cached_response_hash = None
        cached_response_text = None
        ai_response_text = None
        subjective_question_answered = False
        screenshots_count_at_generation = 0
        subjective_screenshots = []

    # Reset typing session so Ctrl+Alt+Z cannot resume a cleared/old session.
    # resume_typing_event is cleared so a stale .set() from a previous session
    # cannot unblock a new typing thread that hasn't paused yet.
    is_typing_active = False
    is_typing_paused = False
    current_typing_position = 0
    resume_typing_event.clear()
    ai_response_ready_subjective.clear()