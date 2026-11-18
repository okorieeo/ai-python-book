#!/usr/bin/env python3
"""
A checklist for a coding prompt, made executable. It looks for the four parts of the anatomy from Chapter 44:

  GOAL         what to build or fix, as an action
  CONTEXT      where: files, an existing pattern to copy, a doc
  CONSTRAINTS  what must not change, what to reuse, what is out of scope
  ACCEPTANCE   how Claude (and you) will know it worked: a test, a command, an observable result

and flags the habits that make prompts fail: too short, too many tasks at once, and vague words like "better".

HONEST LIMITS: this is keyword matching, not understanding. A prompt can pass and still be poor, and a good prompt
phrased unusually can fail. Use it as a checklist you do not have to remember, never as proof of quality.

    python tools/promptlint.py prompts/weak_vs_strong/*.md
"""
from __future__ import annotations

import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

ACTION_WORDS = ("add|build|create|fix|implement|refactor|replace|remove|migrate|write|update|extend|rename|split|move|convert|reduce|"
                "investigate|make|show|wire|port|delete|introduce|support|handle|display|connect")
ACTION = re.compile(rf"^(?:{ACTION_WORDS})\b", re.IGNORECASE)
PATH = re.compile(r"(?:@?[\w.\-]+/)+[\w.\-]+|\b[\w\-]+\.(?:py|ts|tsx|js|jsx|mjs|json|md|ya?ml|toml|sql|html|css|kt|swift|sh|ini|cfg)\b|https?://\S+")
CONSTRAINT = re.compile(r"\b(?:do not|don't|dont|must not|must|never|only|without|avoid|keep|follow|reuse|use the existing|no new|"
                        r"out of scope|not touch|leave\b.*\balone|stay within|same as|match the)\b", re.IGNORECASE)
ACCEPT_LABEL = re.compile(r"^\s*(?:done when|acceptance|verify|verification|definition of done|success)\b", re.IGNORECASE | re.MULTILINE)
ACCEPT_CUES = [re.compile(p, re.IGNORECASE) for p in (
    r"\btests?\b", r"\bpytest\b", r"\bjest\b", r"\bplaywright\b", r"\bmaestro\b", r"\bmake check\b", r"\bnpm (?:run )?\w+", r"\bnpx \w+",
    r"\blint\b", r"\btsc\b", r"\btypecheck\b", r"\b[1-5]\d{2}\b(?! ?(?:ms|px|words|chars|characters|lines))", r"\bexpected\b", r"\bpasses|passing\b",
    r"\bassert", r"\bscreenshot\b", r"\bshould (?:return|show|display|fail|pass|be)\b", r"\bresponds? with\b", r"\breturns?\b")]
VAGUE = re.compile(r"\b(?:better|nicer|cleaner|improve[ds]?|properly|good|nice|modern|robust|best practices?|optimi[sz]e[ds]?|faster|"
                   r"clean(?:ed)? up|make it work|polish|production[- ]ready|scalable|elegant|simple)\b", re.IGNORECASE)
# A list item counts as a TASK only if it starts with an action verb. Bullets that state constraints or checks
# ("Do not change the model", "Only the owner may rename") are not tasks, however many there are.
TASK_ITEM = re.compile(rf"^\s*(?:\d+[.)]|[-*])\s+(?:{ACTION_WORDS})\b", re.MULTILINE | re.IGNORECASE)


@dataclass
class Finding:
    id: str
    severity: str          # error | warn
    message: str


@dataclass
class LintResult:
    elements: dict[str, bool]
    findings: list[Finding] = field(default_factory=list)

    @property
    def score(self) -> int:
        return sum(self.elements.values())

    @property
    def ok(self) -> bool:
        return all(self.elements.values()) and not any(f.severity == "error" for f in self.findings)


def _sentences(text: str) -> list[str]:
    cleaned = re.sub(r"\s+", " ", text.strip())
    return [s for s in re.split(r"(?<=[.!?])\s+", cleaned) if s]


def _goal_text(text: str) -> str:
    for line in text.splitlines():
        stripped = re.sub(r"^\s*(?:\[?goal\]?\s*:?|#+)\s*", "", line, flags=re.IGNORECASE).strip()
        if stripped:
            return stripped
    return ""


def lint(prompt: str) -> LintResult:
    text = re.sub(r"<!--.*?-->", "", prompt, flags=re.DOTALL).strip()      # notes to the author are not part of the prompt
    words = len(text.split())
    goal = _goal_text(text)
    first_sentences = _sentences(goal)[:2] or [goal]
    has_goal = any(ACTION.match(s) for s in first_sentences)
    has_context = bool(PATH.search(text))
    has_constraints = bool(CONSTRAINT.search(text))
    cues = {i for i, c in enumerate(ACCEPT_CUES) if c.search(text)}
    has_acceptance = bool(ACCEPT_LABEL.search(text)) or len(cues) >= 2
    result = LintResult({"goal": has_goal, "context": has_context, "constraints": has_constraints, "acceptance": has_acceptance})
    add = lambda i, sev, msg: result.findings.append(Finding(i, sev, msg))

    if words < 12:
        add("too-short", "error", f"{words} words is too little to act on without guessing.")
    if not has_goal:
        add("no-goal", "error", "Open with the outcome as an action: 'Add ...', 'Fix ...', 'Replace ...'.")
    if not has_context:
        add("no-context", "error", "Point at the files, the existing pattern to copy, or the doc to read (for example @backend/chat/views.py).")
    if not has_constraints:
        add("no-constraints", "error", "Say what must not change, what to reuse, and what is out of scope.")
    if not has_acceptance:
        add("no-acceptance", "error", "Say how success is checked: a test to write or run, a command that must pass, an observable result.")
    for sentence in _sentences(text):
        m = VAGUE.search(sentence)
        if m and not re.search(r"\d", sentence):
            add("vague-word", "warn", f"'{m.group(0)}' cannot be checked. Replace it with something measurable: {sentence[:70]!r}")
            break
    items = TASK_ITEM.findall(text)
    if len(items) > 6 or words > 400 or len(re.findall(r"\b(?:and also|as well as|plus also)\b", text, re.IGNORECASE)) >= 2:
        add("too-big", "warn", "This asks for several things at once. Split it into steps: one prompt, one result, one commit.")
    return result


def main(argv: list[str]) -> int:
    failed = 0
    for name in argv:
        res = lint(Path(name).read_text(encoding="utf-8"))
        marks = " ".join(f"{k}:{'yes' if v else 'NO '}" for k, v in res.elements.items())
        print(f"{'PASS' if res.ok else 'FAIL'}  {res.score}/4  {marks}  {name}")
        for f in res.findings:
            print(f"      {f.severity:5} {f.id}: {f.message}")
        failed += not res.ok
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
