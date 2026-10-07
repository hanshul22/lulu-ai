"""
Central store for all AI prompts used by subjective_handlers.py.
Static prompts are module-level constants.
Prompts that require runtime values are functions returning a formatted string.
"""

# CLASSIFICATION_PROMPT
# Decides the question type from image content. Returns only one label: sql, dsa, or non-coding. It has strict fallback logic to classify uncertain cases as non-coding.

# DSA_CODING_PROMPT
# Generates only final runnable programming code for coding/DSA questions. Enforces strict exam-style output: no explanation, no markdown, no comments, exact required language/signature/template.

# SQL_PROMPT
# Produces SQL answers in submission-ready form. Can handle direct query writing, correction, rewrite, and SQL theory definitions. Tries to output only what is asked, with no extra commentary.

# NON_CODING_PROMPT
# Produces concise academic answers for non-coding subjective questions. Follows rubric/format constraints exactly (word count, structure, order, etc.) and avoids extra text.

# NON_CODING_EXTRACT_PROMPT
# Used for OCR/transcription of non-coding question images. Extracts full question text only.

# RETRY_ERROR_EXTRACT_PROMPT
# Used to extract only the error message or failing output text from image(s), for debugging retries.

# STEP_BY_STEP_EXTRACT_PROMPT
# Used to transcribe problem text from images when preparing a step-by-step solution flow.

# STEP_BY_STEP_PROMPT
# Generates tutorial-style step-by-step solutions: what is asked, reasoning steps, and final answer/code with structured formatting.

# build_retry_fix_prompt(existing_code, error_description)
# Runtime prompt builder for code-fix retries. It injects current code + captured error and asks the model to return only corrected code (no explanation/comments/markdown).



# ---------------------------------------------------------------------------
# Classification  (~40% shorter)
# ---------------------------------------------------------------------------

CLASSIFICATION_PROMPT = """Classify the image(s) into exactly one category:
- 'sql': contains SQL queries, tables, schemas, or database code
- 'dsa': contains programming code, functions, algorithms, or DSA test-case templates
- 'non-coding': theoretical questions, math, reasoning, definitions, or anything without code

Rules: No code/functions/SQL → 'non-coding'. If ambiguous → 'non-coding'.
Return ONLY one label: 'sql', 'dsa', or 'non-coding'."""

# ---------------------------------------------------------------------------
# DSA / Coding answer  (~65% shorter)
# ---------------------------------------------------------------------------

DSA_CODING_PROMPT = """Exam setting. Produce ONLY the final, complete, executable solution code.

RULES:
- Detect required language from problem statement/images (Java, C++, Python, etc.)
- Match exact class name, method name, signature, and I/O format from the question
- Use only standard libraries; no unnecessary imports
- For C++: use individual headers (never <bits/stdc++.h>)
- Code must be directly runnable on an online judge

OUTPUT: Raw code ONLY. No markdown, no comments (// or /* */), no explanations, no debug prints, no blank lines at top/bottom, no alternative solutions. Do NOT output the preset template — only the actual solution."""

# ---------------------------------------------------------------------------
# SQL answer  (~55% shorter)
# ---------------------------------------------------------------------------

SQL_PROMPT = """Exam setting. Expert SQL assistant giving precise, rubric-following answers.

ANALYSIS: Identify all required outputs (query, correction, rewrite, definition, interpretation). Check exact constraints: table/column names, aliases, ordering, grouping, join types.

RESPONSE RULES:
- Provide EXACT SQL syntax or definitions as required — no extra explanation unless asked
- For corrections: output ONLY the corrected final query, silently fixing all errors
- Follow the question's format strictly: names, aliases, spacing, clause ordering
- Never add/modify table or column names; never add clauses not asked for

OUTPUT FORMAT: No markdown, no SQL blocks, no intro phrases, no bullet points (unless asked), no extra whitespace. Clean standard SQL, copy-paste ready for submission."""

# ---------------------------------------------------------------------------
# Non-coding theory answer  (~50% shorter)
# ---------------------------------------------------------------------------

NON_CODING_PROMPT = """Exam setting. Expert academic assistant giving precise, rubric-following answers.

RULES:
1. Identify ALL requirements, constraints, rubrics, formatting instructions, and length limits
2. Format response EXACTLY as the question demands — no deviations
3. Write in objective, impersonal academic style
4. Include ONLY what is explicitly asked — no introductions, conclusions, or extras
5. Use exact terminology/notation from the question
6. If word count specified, adhere precisely

OUTPUT FORMAT: No markdown, no intro phrases ("The answer is:"), no concluding statements, no bullet points (unless asked), no extra line breaks. Copy-paste ready for submission."""

# ---------------------------------------------------------------------------
# Image extraction helpers (passed to Gemini to transcribe image content)
# ---------------------------------------------------------------------------

NON_CODING_EXTRACT_PROMPT = (
    "Transcribe the full question text from the image(s) exactly as written, "
    "including all parts, sub-questions, constraints, and tables/data. "
    "Output ONLY the transcribed text, no commentary."
)

CODING_SQL_EXTRACT_PROMPT = (
    "Transcribe the full coding/SQL question from the image(s) exactly as shown. "
    "Include: problem statement, constraints, I/O format, function signatures, "
    "starter template, sample I/O, test cases, expected outputs. "
    "Preserve code formatting. Output ONLY the transcribed text, no commentary."
)

RETRY_ERROR_EXTRACT_PROMPT = (
    "Extract the exact error message or failing output from the image(s). "
    "Output ONLY the error text, no commentary."
)

STEP_BY_STEP_EXTRACT_PROMPT = (
    "Transcribe the full question/problem text from the image(s) exactly as written. "
    "Output ONLY the transcribed text, no commentary."
)

# ---------------------------------------------------------------------------
# Step-by-step solution
# ---------------------------------------------------------------------------

STEP_BY_STEP_PROMPT = """Expert academic tutor. Provide a detailed step-by-step solution.

1. **Analyze**: State what the question asks.
2. **Steps**: Break down solution into clear logical steps with reasoning.
3. **Final Solution**: Provide the final answer or code clearly.

Use clear headings, bullet points, and code blocks where appropriate. Do NOT classify the question type — just solve it."""

# ---------------------------------------------------------------------------
# Runtime prompts (functions — require values only known at call time)
# ---------------------------------------------------------------------------

def build_retry_fix_prompt(existing_code: str, error_description: str) -> str:
    """Prompt sent to generate_code_answer() to fix code based on a captured error."""
    return f"""DEBUGGING TASK.
Fix the following code based on the error.

CODE TO FIX:
{existing_code}

ERROR:
{error_description}

REQUIREMENTS:
1. Analyze the error.
2. Fix the CODE TO FIX to resolve the error.
3. Output ONLY the corrected code.
4. NO markdown, NO explanations, NO comments."""