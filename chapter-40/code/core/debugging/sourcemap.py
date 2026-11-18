"""Turn a position in minified code back into the original file, line and column (source map v3)."""
from __future__ import annotations

import bisect
import json
import re
from dataclasses import dataclass

_B64 = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/"
_B64_INDEX = {c: i for i, c in enumerate(_B64)}


def decode_vlq(segment: str) -> list[int]:
    values, shift, value = [], 0, 0
    for char in segment:
        digit = _B64_INDEX[char]
        value += (digit & 31) << shift
        if digit & 32:                      # continuation bit
            shift += 5
        else:
            values.append(-(value >> 1) if value & 1 else value >> 1)
            shift = value = 0
    return values


@dataclass(frozen=True)
class Position:
    source: str
    line: int          # 1-based, like an editor
    column: int        # 0-based
    name: str | None = None


class SourceMap:
    def __init__(self, raw: dict):
        if raw.get("version") != 3:
            raise ValueError("only source map version 3 is supported")
        self.sources = raw["sources"]
        self.names = raw.get("names", [])
        self._lines: list[list[tuple[int, int, int, int, int | None]]] = []
        src = line = col = name = 0
        for generated_line in raw["mappings"].split(";"):
            segments, gen_col = [], 0
            for seg in filter(None, generated_line.split(",")):
                f = decode_vlq(seg)
                gen_col += f[0]
                if len(f) >= 4:
                    src += f[1]; line += f[2]; col += f[3]
                    if len(f) >= 5:
                        name += f[4]
                    segments.append((gen_col, src, line, col, name if len(f) >= 5 else None))
            self._lines.append(segments)

    @classmethod
    def loads(cls, text: str) -> "SourceMap":
        return cls(json.loads(text))

    def lookup(self, line: int, column: int) -> Position | None:
        """line is 1-based, column 0-based, as in a minified stack trace."""
        if not 1 <= line <= len(self._lines):
            return None
        segments = self._lines[line - 1]
        if not segments:
            return None
        idx = bisect.bisect_right([s[0] for s in segments], column) - 1
        if idx < 0:
            return None
        _, src, orig_line, orig_col, name = segments[idx]
        return Position(self.sources[src], orig_line + 1, orig_col, self.names[name] if name is not None else None)


_JS_FUNC = re.compile(r"^\s*at\s+([^\s(]+)")
_JS_LOC = re.compile(r"(?P<file>[^\s()]+?):(?P<line>\d+):(?P<col>\d+)\)?\s*$")


def symbolicate(stack: str, maps: dict[str, SourceMap]) -> list[str]:
    """Rewrite each 'at fn (bundle.js:1:2345)' line using the map for that bundle. Unknown frames are kept."""
    out = []
    for raw in stack.splitlines():
        loc = _JS_LOC.search(raw)
        if not loc:
            out.append(raw)
            continue
        bundle = loc["file"].rsplit("/", 1)[-1].split("?")[0]
        smap = maps.get(bundle)
        pos = smap.lookup(int(loc["line"]), int(loc["col"])) if smap else None
        if pos is None:
            out.append(raw)
            continue
        func_match = _JS_FUNC.match(raw)
        func = pos.name or (func_match.group(1) if func_match else "") or "<anonymous>"
        out.append(f"at {func} ({pos.source}:{pos.line}:{pos.column})")
    return out
