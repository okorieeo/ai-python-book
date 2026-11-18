# Chapter 3 — Programming Fundamentals with Python: extended material

The printed edition of *Building AI-Powered Apps* keeps each chapter short. This file holds the longer material that was moved here so that nothing is lost: the full hands-on lab, troubleshooting tables, checklists, further exercises, and sections that were condensed for print.


---

# Sections condensed for print


## Error Handling › Rules for good error handling

- Catch **specific** exceptions (`ValueError`), not a bare `except:`, which hides real bugs.
- Handle an error only if you can do something useful about it: retry, show a friendly message, use a fallback. Otherwise let it propagate.
- Never silently ignore errors (`except: pass`). At least log them.
- Common exceptions: `ValueError`, `TypeError`, `KeyError`, `IndexError`, `FileNotFoundError`, `ZeroDivisionError`.
> **Reading a traceback**
>
> When a program crashes, Python prints a **traceback**. Read it **from the bottom**: the last line names the error type and message; the lines above show which file and line number triggered it, from the outermost call to the innermost.


## Project: Task Manager › Step 4: Add an AI feature (optional)

Reuse the `ask()` function from Chapter 1 (keep `hello_ai.py` in the same folder) to let AI suggest a priority. Notice the pattern: **ask the model for a constrained answer, validate it, and fall back to a safe default.** Never trust AI output blindly.

**add to task_manager.py**

```
from hello_ai import ask

def suggest_priority(title: str) -> str:
    """Ask the AI model to rate urgency. Falls back to 'medium' on any problem."""
    prompt = (
        "Reply with exactly one word: low, medium or high. "
        "How urgent is this task?\n\n" + title
    )
    try:
        answer = ask(prompt).strip().lower()
    except Exception:          # network problem, missing key, rate limit...
        return "medium"
    return answer if answer in VALID_PRIORITIES else "medium"
```

In the `add` command, call `suggest_priority(title)` when the user leaves the priority empty. Your program now works with or without the AI, which is exactly how robust AI features should behave.


## Project: Task Manager › Commit your work

**terminal**

```bash
git init
printf ".venv/\n__pycache__/\ntasks.json\n.env\n" > .gitignore
git add .
git commit -m "Add task manager CLI with JSON storage and tests"
```
