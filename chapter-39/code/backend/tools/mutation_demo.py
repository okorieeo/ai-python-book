"""
Do the tests actually test anything? This script breaks the code on purpose, one small change at a time
(a "mutant"), runs the test suite against each broken copy, and reports whether the suite NOTICED.

  killed    the suite failed: good, it would catch that bug
  SURVIVED  the suite still passed with the code broken: a gap, or an "equivalent mutant" that behaves identically

It works on a temporary copy; your files are never touched. Real tools (mutmut, cosmic-ray) automate this for
whole projects; this is the idea in 100 lines.

    python tools/mutation_demo.py                                   # uses python -m pytest -q
    python tools/mutation_demo.py --runner "python /path/to/mini_pytest.py tests"
"""
from __future__ import annotations

import argparse
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent


@dataclass
class Mutant:
    id: str
    file: str
    old: str
    new: str
    why: str
    drop_tests: list[str] = field(default_factory=list)   # tests to delete first (to show what a missing test costs)
    expect_survive: bool = False


MUTANTS = [
    Mutant("M01", "billing/webhooks.py", "abs(now - timestamp) > tolerance", "(now - timestamp) > tolerance", "future timestamps accepted"),
    Mutant("M02", "billing/webhooks.py", "abs(now - timestamp) > tolerance", "abs(now - timestamp) >= tolerance", "off-by-one at the tolerance boundary"),
    Mutant("M03", "billing/webhooks.py", "if abs(now - timestamp) > tolerance:", "if False:", "replay protection removed"),
    Mutant("M04", "billing/webhooks.py", "hmac.compare_digest(expected, candidate)", "expected == candidate", "timing-unsafe comparison (same results!)"),
    Mutant("M05", "billing/webhooks.py", "signed = str(timestamp).encode() + b\".\" + payload", "signed = payload", "timestamp no longer part of what is signed"),
    Mutant("M06", "billing/webhooks.py", 'elif key == "v1" and value:', 'elif key in ("v1", "v0") and value:', "accepts the fake v0 scheme"),
    Mutant("M07", "billing/webhooks.py", "hashlib.sha512", "hashlib.sha256", "Paystack signature downgraded to SHA-256"),
    Mutant("M08", "billing/webhooks.py", "        store.release(key)\n        raise", "        pass\n        raise", "a failed handler keeps its claim, so the retry is skipped"),
    Mutant("M09", "billing/webhooks.py", "if not store.claim(key):\n        return \"duplicate\"", "store.claim(key)", "duplicates are processed again"),
    Mutant("M10", "billing/endpoint.py", 'return 400, {"error": "invalid signature"}', 'return 200, {"error": "invalid signature"}', "bad signatures answered with success"),
    Mutant("M11", "billing/endpoint.py", 'return 400, {"error": "invalid signature"}', 'return 400, {"error": str(exc)}', "the reason for rejection leaks to the caller"),
    Mutant("M12", "billing/endpoint.py", "if len(body) > config.max_body_bytes:", "if False:", "no body size limit"),
    Mutant("M13", "billing/handlers.py", 'data.get("amount") != order.amount_minor or data.get("currency") != order.currency', "False", "amounts and currencies are trusted"),
    Mutant("M14", "billing/handlers.py", "if order.status == \"paid\":", "if False:", "no business-level double-credit guard"),
    Mutant("M15", "billing/handlers.py", "if created < self.plan_stamp.get(user_id, 0):", "if created > self.plan_stamp.get(user_id, 0):", "older events overwrite newer ones"),
    Mutant("M04b", "billing/webhooks.py", "hmac.compare_digest(expected, candidate)", "expected == candidate",
           "same as M04, but with the spy test deleted", drop_tests=["test_the_comparison_is_constant_time"], expect_survive=True),
]


def drop_test(source: str, name: str) -> str:
    lines, out, skipping = source.split("\n"), [], False
    for line in lines:
        if re.match(rf"\s*def {re.escape(name)}\(", line):
            skipping, indent = True, len(line) - len(line.lstrip())
            continue
        if skipping:
            stripped = line.strip()
            if stripped and (len(line) - len(line.lstrip())) <= indent and not stripped.startswith("@"):
                skipping = False
            elif stripped.startswith("@") and (len(line) - len(line.lstrip())) <= indent:
                skipping = False
            else:
                continue
        out.append(line)
    return "\n".join(out)


def run_suite(workdir: Path, runner: str) -> bool:
    proc = subprocess.run(shlex.split(runner), cwd=workdir, capture_output=True, text=True, timeout=120)
    return proc.returncode == 0


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--runner", default="python -m pytest -q tests")
    args = ap.parse_args(argv)

    with tempfile.TemporaryDirectory() as tmp:
        base = Path(tmp) / "baseline"
        shutil.copytree(BACKEND, base, ignore=shutil.ignore_patterns("__pycache__", "tools"))
        if not run_suite(base, args.runner):
            print("The suite must pass on the UNMODIFIED code first.")
            return 2
        print(f"{'id':5} {'result':9} what was broken")
        unexpected, survived = 0, 0
        for m in MUTANTS:
            work = Path(tmp) / m.id
            shutil.copytree(base, work)
            target = work / m.file
            text = target.read_text()
            if m.old not in text:
                print(f"{m.id:5} {'BAD MUTANT':9} pattern not found in {m.file}: {m.old!r}")
                unexpected += 1
                continue
            target.write_text(text.replace(m.old, m.new, 1))
            for t in m.drop_tests:
                for f in (work / "tests").glob("test_*.py"):
                    f.write_text(drop_test(f.read_text(), t))
            alive = run_suite(work, args.runner)
            survived += alive
            if alive != m.expect_survive:
                unexpected += 1
            label = "SURVIVED" if alive else "killed"
            note = "" if alive == m.expect_survive else "   <-- NOT EXPECTED"
            print(f"{m.id:5} {label:9} {m.why}{note}")
        killed = len(MUTANTS) - survived
        print(f"\n{killed} of {len(MUTANTS)} mutants killed; {survived} survived.")
        return 1 if unexpected else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
