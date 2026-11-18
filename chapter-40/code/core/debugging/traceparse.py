"""Read a Python traceback the way an experienced engineer does: bottom first, your code before libraries."""
from __future__ import annotations

import re
from dataclasses import dataclass, field

_FRAME = re.compile(r'^\s*File "(?P<file>[^"]+)", line (?P<line>\d+), in (?P<func>.+)$')
_CAUSE = "The above exception was the direct cause of the following exception:"
_CONTEXT = "During handling of the above exception, another exception occurred:"
_LIBRARY_MARKERS = ("site-packages", "dist-packages", "/lib/python", "\\lib\\python", "<frozen ")


@dataclass(frozen=True)
class Frame:
    file: str
    line: int
    func: str
    code: str = ""

    @property
    def is_library(self) -> bool:
        return any(marker in self.file for marker in _LIBRARY_MARKERS)


@dataclass
class ParsedException:
    frames: list[Frame] = field(default_factory=list)
    exc_type: str = ""
    message: str = ""
    link_to_next: str = ""          # "cause" | "context" | "" (this is the final exception)


@dataclass
class Traceback:
    chain: list[ParsedException]    # oldest first; the LAST one is what was finally raised

    @property
    def final(self) -> ParsedException:
        return self.chain[-1]

    @property
    def root(self) -> ParsedException:
        """The first exception in the chain is usually where the real problem started."""
        return self.chain[0]

    def last_app_frame(self, exc: ParsedException | None = None) -> Frame | None:
        """The deepest frame that is YOUR code. This is where to put the first breakpoint."""
        exc = exc or self.final
        return next((f for f in reversed(exc.frames) if not f.is_library), None)

    def summary(self) -> str:
        lines = [f"raised:   {self.final.exc_type}: {self.final.message}"]
        app = self.last_app_frame()
        if app:
            lines.append(f"your code: {app.file}:{app.line} in {app.func}")
            if app.code:
                lines.append(f"           {app.code}")
        if len(self.chain) > 1:
            root_app = self.last_app_frame(self.root)
            lines.append(f"started as: {self.root.exc_type}: {self.root.message}")
            if root_app:
                lines.append(f"            at {root_app.file}:{root_app.line} in {root_app.func}")
        return "\n".join(lines)


def parse_traceback(text: str) -> Traceback:
    chain: list[ParsedException] = []
    current = ParsedException()
    pending_link = ""
    lines = text.splitlines()
    i = 0
    while i < len(lines):
        raw = lines[i]
        stripped = raw.strip()
        m = _FRAME.match(raw)
        if m:
            code = ""
            if i + 1 < len(lines) and lines[i + 1].startswith("    ") and not _FRAME.match(lines[i + 1]):
                nxt = lines[i + 1].strip()
                if not set(nxt) <= set("^~ "):
                    code = nxt
                    i += 1
            current.frames.append(Frame(m["file"], int(m["line"]), m["func"], code))
        elif stripped in (_CAUSE, _CONTEXT):
            current.link_to_next = "cause" if stripped == _CAUSE else "context"
            chain.append(current)
            current = ParsedException()
        elif stripped.startswith("Traceback (most recent call last):") or not stripped:
            pass
        elif not raw.startswith((" ", "\t")) and current.frames and not current.exc_type:
            name, _, message = raw.partition(":")
            current.exc_type, current.message = name.strip(), message.strip()
        i += 1
    chain.append(current)
    return Traceback([e for e in chain if e.frames or e.exc_type])
