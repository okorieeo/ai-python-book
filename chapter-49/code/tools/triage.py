"""Turn a messy error into an evidence pack Claude Code can work from.

Usage:
  python -m tools.triage --symptom "..." --expected "..." --repro "step 1; step 2" \
      --log backend.log [--tried "restarted docker; cleared cache"] [--out docs/debug/bug-123.md]

What it does:
  * redacts secrets (tokens, passwords, keys, emails, credentials in URLs) BEFORE anything is shown
  * finds the exception in a Python traceback or a Node/Next.js stack and picks the frames that are
    YOUR code (not site-packages, node_modules or node:internal)
  * keeps only the tail of a long log
  * prints one markdown report: Symptom, Expected, Actual, Steps, Environment, Evidence, Already tried
It reads files you give it. It never contacts anything.
"""
from __future__ import annotations

import argparse
import platform
import re
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

REDACTIONS = [
    (re.compile(r"(?i)(authorization:\s*bearer\s+)[A-Za-z0-9._~+/=-]+"), r"\1[REDACTED]"),
    (re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._~+/=-]{16,}"), "Bearer [REDACTED]"),
    (re.compile(r"\beyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}"), "[REDACTED_JWT]"),
    (re.compile(r"\b(sk|pk|rk)[-_](live|test|ant)?[-_]?[A-Za-z0-9]{16,}"), "[REDACTED_KEY]"),
    (re.compile(r"(?i)\b([A-Za-z0-9_]*(?:password|passwd|secret|api[_-]?key|token|access[_-]?key)[A-Za-z0-9_]*)(\s*[=:]\s*)(\"[^\"]*\"|'[^']*'|[^\s,;&]+)"),
     r"\1\2[REDACTED]"),
    (re.compile(r"(://[^/\s:@]+:)[^@\s/]+@"), r"\1[REDACTED]@"),
    (re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.-]+\b"), "[REDACTED_EMAIL]"),
]
LIBRARY_MARKERS = ("site-packages", "dist-packages", "/lib/python", "node_modules", "node:", "<frozen")
PY_EXC = re.compile(r"^(?P<type>[A-Za-z_][\w.]*(?:Error|Exception|Exit|Interrupt|Warning|DoesNotExist|Invalid)\w*)(?::\s?(?P<msg>.*))?$")
PY_FRAME = re.compile(r'^\s*File "(?P<file>[^"]+)", line (?P<line>\d+), in (?P<func>.+)$')
JS_ERR = re.compile(r"^(?P<type>(?:[A-Z]\w*)?(?:Error|Exception))(?::\s?(?P<msg>.*))?$")
JS_FRAME = re.compile(r"^\s*at (?P<head>.*?):(?P<line>\d+):(?P<col>\d+)\)?\s*$")


def redact(text: str) -> str:
    for pattern, repl in REDACTIONS:
        text = pattern.sub(repl, text)
    return text


@dataclass
class Frame:
    file: str
    line: int
    func: str
    code: str = ""

    @property
    def is_library(self) -> bool:
        return any(m in self.file for m in LIBRARY_MARKERS)


@dataclass
class ParsedError:
    language: str = ""
    exc_type: str = ""
    message: str = ""
    frames: list[Frame] = field(default_factory=list)

    @property
    def app_frames(self) -> list[Frame]:
        return [f for f in self.frames if not f.is_library]

    @property
    def found(self) -> bool:
        return bool(self.exc_type)


def parse_python(lines: list[str]) -> ParsedError | None:
    """Use the LAST traceback in the text: the most recent failure is the one that matters."""
    starts = [i for i, l in enumerate(lines) if l.startswith("Traceback (most recent call last)")]
    if not starts:
        return None
    chunk = lines[starts[-1] + 1:]
    err = ParsedError(language="python")
    i = 0
    while i < len(chunk):
        m = PY_FRAME.match(chunk[i])
        if m:
            code = chunk[i + 1].strip() if i + 1 < len(chunk) and not PY_FRAME.match(chunk[i + 1]) else ""
            err.frames.append(Frame(m["file"], int(m["line"]), m["func"], code))
            i += 2 if code else 1
            continue
        stripped = chunk[i].strip()
        if stripped and not chunk[i].startswith((" ", "\t")):
            em = PY_EXC.match(stripped)
            if em:
                err.exc_type, err.message = em["type"], (em["msg"] or "")
                break
        i += 1
    return err if err.exc_type else None


def parse_node(lines: list[str]) -> ParsedError | None:
    for idx in range(len(lines) - 1, -1, -1):
        em = JS_ERR.match(lines[idx].strip().removeprefix("⨯ ").removeprefix("Uncaught "))
        if em and any(l.lstrip().startswith("at ") for l in lines[idx + 1: idx + 4]):
            err = ParsedError(language="javascript", exc_type=em["type"], message=em["msg"] or "")
            for l in lines[idx + 1:]:
                fm = JS_FRAME.match(l)
                if fm:
                    func, _, file = fm["head"].partition(" (") if " (" in fm["head"] else ("", "", fm["head"])
                    err.frames.append(Frame(file, int(fm["line"]), func or "<anonymous>"))
                elif l.strip() and not l.lstrip().startswith("at "):
                    break
            return err
    return None


def parse_error(text: str) -> ParsedError:
    lines = text.splitlines()
    return parse_python(lines) or parse_node(lines) or ParsedError()


def tail(text: str, max_lines: int = 40) -> str:
    lines = text.splitlines()
    if len(lines) <= max_lines:
        return text.strip("\n")
    return f"[... {len(lines) - max_lines} earlier lines omitted ...]\n" + "\n".join(lines[-max_lines:])


def git_head(cwd: str | None = None) -> str:
    try:
        out = subprocess.run(["git", "log", "-1", "--format=%h %s"], capture_output=True, text=True, cwd=cwd, timeout=5)
        return out.stdout.strip() if out.returncode == 0 else ""
    except (OSError, subprocess.SubprocessError):
        return ""


def build_report(*, symptom: str, expected: str, repro: list[str], log_text: str = "", tried: list[str] | None = None,
                 environment: dict[str, str] | None = None, max_log_lines: int = 40) -> str:
    log_text = redact(log_text)
    err = parse_error(log_text)
    out = ["# Bug report", "", "## Symptom", symptom.strip() or "(missing: say what you saw)", "",
           "## Expected", expected.strip() or "(missing: say what should have happened)", "", "## Steps to reproduce"]
    out += [f"{n}. {step}" for n, step in enumerate(repro, 1)] or ["(missing: how can someone else see it?)"]
    out += ["", "## Environment"]
    out += [f"- {k}: {v}" for k, v in (environment or {}).items() if v] or ["- (not given)"]
    out += ["", "## Evidence"]
    if err.found:
        out.append(f"**{err.exc_type}**: {err.message}".rstrip(": "))
        shown = err.app_frames[-3:] or err.frames[-3:]
        out.append("")
        out.append("Your code, innermost last:" if err.app_frames else "Only library frames found:")
        out += [f"- `{f.file}:{f.line}` in `{f.func}`" + (f": `{f.code}`" if f.code else "") for f in shown]
    else:
        out.append("No exception found in the log (a silent failure, or the log is not the right one).")
    if log_text.strip():
        out += ["", "Log tail (secrets removed):", "```", tail(log_text, max_log_lines), "```"]
    out += ["", "## Already tried"]
    out += [f"- {t}" for t in (tried or [])] or ["- nothing yet"]
    return "\n".join(out) + "\n"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--symptom", required=True)
    ap.add_argument("--expected", required=True)
    ap.add_argument("--repro", default="", help="steps separated by semicolons")
    ap.add_argument("--log", help="path to a log or pasted traceback")
    ap.add_argument("--tried", default="", help="things already tried, separated by semicolons")
    ap.add_argument("--out")
    a = ap.parse_args(argv)
    log = Path(a.log).read_text(encoding="utf-8", errors="replace") if a.log else ""
    split = lambda s: [p.strip() for p in s.split(";") if p.strip()]
    report = build_report(
        symptom=a.symptom, expected=a.expected, repro=split(a.repro), log_text=log, tried=split(a.tried),
        environment={"python": platform.python_version(), "os": platform.platform(), "git": git_head()},
    )
    if a.out:
        Path(a.out).write_text(report, encoding="utf-8")
        print(f"wrote {a.out}")
    else:
        print(report)
    return 0


if __name__ == "__main__":
    sys.exit(main())
