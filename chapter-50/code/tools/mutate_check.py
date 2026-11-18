"""A tiny mutation tester: does your test suite notice when the code is quietly broken?

Usage:
  python -m tools.mutate_check samples/pricing.py --tests samples.test_pricing_weak [--root .] [--lines 1-40]

How it works: it makes small changes ("mutants") to ONE source file: < becomes <=, + becomes -, and becomes or,
True becomes False, a number goes up by one. For each mutant it copies the project to a temporary folder, runs
your unittest module there, and records whether the tests FAILED (mutant killed: good) or still PASSED
(mutant survived: your tests would not notice that bug).

Why it matters with AI: AI-written tests often pass for the wrong reason (they assert a mock, or only the easy
case). Surviving mutants show exactly which behaviour no test protects. Your own files are never modified.
"""
from __future__ import annotations

import ast
import copy
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

COMPARE_SWAP = {ast.Lt: ast.LtE, ast.LtE: ast.Lt, ast.Gt: ast.GtE, ast.GtE: ast.Gt, ast.Eq: ast.NotEq, ast.NotEq: ast.Eq}
ARITH_SWAP = {ast.Add: ast.Sub, ast.Sub: ast.Add, ast.Mult: ast.FloorDiv, ast.FloorDiv: ast.Mult}
BOOL_SWAP = {ast.And: ast.Or, ast.Or: ast.And}
IGNORE = shutil.ignore_patterns(".git", "node_modules", "__pycache__", ".venv", "venv", ".next", "dist", "build", ".expo", "*.pyc")


@dataclass(frozen=True)
class Mutant:
    index: int
    lineno: int
    description: str


def _candidates(tree: ast.AST, line_range: tuple[int, int] | None):
    """Yield (node, field, position, new_value, description) for every possible single change, in a stable order."""
    for node in ast.walk(tree):
        line = getattr(node, "lineno", None)
        if line is None or (line_range and not line_range[0] <= line <= line_range[1]):
            continue
        if isinstance(node, ast.Compare):
            for i, op in enumerate(node.ops):
                if type(op) in COMPARE_SWAP:
                    new = COMPARE_SWAP[type(op)]
                    yield node, "ops", i, new(), f"{type(op).__name__} -> {new.__name__}"
        elif isinstance(node, ast.BinOp) and type(node.op) in ARITH_SWAP:
            new = ARITH_SWAP[type(node.op)]
            yield node, "op", None, new(), f"{type(node.op).__name__} -> {new.__name__}"
        elif isinstance(node, ast.BoolOp) and type(node.op) in BOOL_SWAP:
            new = BOOL_SWAP[type(node.op)]
            yield node, "op", None, new(), f"{type(node.op).__name__} -> {new.__name__}"
        elif isinstance(node, ast.Constant):
            if isinstance(node.value, bool):
                yield node, "value", None, (not node.value), f"{node.value} -> {not node.value}"
            elif isinstance(node.value, int):
                yield node, "value", None, node.value + 1, f"{node.value} -> {node.value + 1}"
        elif isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.Not):
            yield node, "NOT", None, None, "removed 'not'"


def list_mutants(source: str, line_range: tuple[int, int] | None = None) -> list[Mutant]:
    tree = ast.parse(source)
    return [Mutant(i, getattr(c[0], "lineno", 0), c[4]) for i, c in enumerate(_candidates(tree, line_range))]


def apply_mutant(source: str, index: int, line_range: tuple[int, int] | None = None) -> str:
    tree = ast.parse(source)
    node, field, pos, new, _ = list(_candidates(tree, line_range))[index]
    if field == "NOT":
        # replace the UnaryOp(Not, x) by x, by mutating it in place
        operand = node.operand
        node.__class__ = operand.__class__
        node.__dict__ = copy.copy(operand.__dict__)
    elif pos is not None:
        getattr(node, field)[pos] = new
    else:
        setattr(node, field, new)
    return ast.unparse(ast.fix_missing_locations(tree)) + "\n"


def run_tests(workdir: Path, test_module: str, timeout: int = 60) -> bool:
    """True when the tests PASS."""
    try:
        r = subprocess.run([sys.executable, "-m", "unittest", test_module], cwd=workdir, capture_output=True, timeout=timeout)
        return r.returncode == 0
    except subprocess.TimeoutExpired:
        return False  # an endless loop is a failure too: the mutant was noticed


def mutation_test(root: Path, source_rel: str, test_module: str, line_range=None) -> tuple[list[Mutant], list[Mutant]]:
    """Return (killed, survived). Raises if the tests do not pass on the original code."""
    source = (root / source_rel).read_text(encoding="utf-8")
    killed, survived = [], []
    with tempfile.TemporaryDirectory() as tmp:
        work = Path(tmp) / "project"
        shutil.copytree(root, work, ignore=IGNORE)
        if not run_tests(work, test_module):
            raise RuntimeError("the tests do not pass on the ORIGINAL code; fix that first")
        for m in list_mutants(source, line_range):
            (work / source_rel).write_text(apply_mutant(source, m.index, line_range), encoding="utf-8")
            (survived if run_tests(work, test_module) else killed).append(m)
        (work / source_rel).write_text(source, encoding="utf-8")
    return killed, survived


def main(argv: list[str]) -> int:
    import argparse
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("source")
    ap.add_argument("--tests", required=True, help="unittest module name, e.g. samples.test_pricing")
    ap.add_argument("--root", default=".")
    ap.add_argument("--lines", help="only mutate lines A-B")
    a = ap.parse_args(argv[1:])
    lr = tuple(int(x) for x in a.lines.split("-")) if a.lines else None
    try:
        killed, survived = mutation_test(Path(a.root), a.source, a.tests, lr)
    except RuntimeError as e:
        print(f"error: {e}")
        return 2
    total = len(killed) + len(survived)
    print(f"{total} mutants: {len(killed)} killed, {len(survived)} SURVIVED")
    for m in sorted(survived, key=lambda m: (m.lineno, m.description)):
        print(f"  survived  {a.source}:{m.lineno}  {m.description}")
    if total:
        print(f"mutation score: {100 * len(killed) // total}%")
    return 1 if survived else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
