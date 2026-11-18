from dataclasses import dataclass

PASS, WARN, FAIL = "PASS", "WARN", "FAIL"
_ORDER = {PASS: 0, WARN: 1, FAIL: 2}


@dataclass(frozen=True)
class Finding:
    name: str
    status: str
    detail: str

    def line(self) -> str:
        return f"[{self.status}] {self.name}: {self.detail}"


def worst_status(findings) -> str:
    return max((f.status for f in findings), key=_ORDER.__getitem__, default=PASS)
