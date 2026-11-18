"""A small mutation tester.

The question: if I break the code on purpose, do the tests notice?

Each "mutant" is the original code with ONE small change: a `<` turned into `<=`, a `+` into
a `-`, a number moved by one, a return value replaced with None. The tests are run against it.
If they fail, the mutant is "killed" (good: the tests noticed). If they all pass, it
"survived" (bad: a real bug like that would ship). The share killed is the mutation score.

Coverage tells you which lines ran. Mutation testing tells you whether the tests would
notice if those lines were wrong. This is a teaching tool. For serious use in a large
project, look at established mutation testing tools (mutmut and Cosmic Ray for Python,
Stryker for JavaScript).

Some survivors are "equivalent mutants": a change that does not alter behavior (for example
clamping a value that can never go out of range). Read each survivor and decide.
"""
from __future__ import annotations

import ast
import difflib
import os
import shlex
import shutil
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

COMPARE_SWAPS = {ast.Eq: ast.NotEq, ast.NotEq: ast.Eq, ast.Lt: ast.LtE, ast.LtE: ast.Lt, ast.Gt: ast.GtE,
                 ast.GtE: ast.Gt, ast.Is: ast.IsNot, ast.IsNot: ast.Is, ast.In: ast.NotIn, ast.NotIn: ast.In}
BINOP_SWAPS = {ast.Add: ast.Sub, ast.Sub: ast.Add, ast.Mult: ast.FloorDiv, ast.FloorDiv: ast.Mult, ast.Mod: ast.Mult}
SYMBOL = {ast.Eq: "==", ast.NotEq: "!=", ast.Lt: "<", ast.LtE: "<=", ast.Gt: ">", ast.GtE: ">=", ast.Is: "is",
          ast.IsNot: "is not", ast.In: "in", ast.NotIn: "not in", ast.Add: "+", ast.Sub: "-", ast.Mult: "*",
          ast.FloorDiv: "//", ast.Mod: "%", ast.And: "and", ast.Or: "or"}
IGNORE_DIRS = {".git", "__pycache__", ".pytest_cache", "node_modules", ".venv", "venv", ".mypy_cache"}


@dataclass(frozen=True)
class Mutant:
    index: int
    line: int
    description: str


class _Mutator(ast.NodeTransformer):
    """Walks the tree in a fixed order. With target=None it only lists the possible mutations;
    with a target index it applies exactly that one."""

    def __init__(self, skip_lines: set[int], target: Optional[int] = None):
        self.skip, self.target, self.count = skip_lines, target, 0
        self.found: list[Mutant] = []

    def _hit(self, node: ast.AST, description: str) -> bool:
        if getattr(node, "lineno", 0) in self.skip:
            return False
        idx = self.count
        self.count += 1
        if self.target is None:
            self.found.append(Mutant(idx, node.lineno, description))
        return idx == self.target

    def visit_Expr(self, node):  # leave docstrings and bare strings alone
        if isinstance(node.value, ast.Constant) and isinstance(node.value.value, str):
            return node
        return self.generic_visit(node)

    def visit_arg(self, node):
        return node

    def visit_AnnAssign(self, node):
        if node.value is not None:
            node.value = self.visit(node.value)
        return node

    def visit_FunctionDef(self, node):
        node.body = [self.visit(s) for s in node.body]
        node.decorator_list = [self.visit(d) for d in node.decorator_list]
        return node  # signature annotations and defaults are left alone

    visit_AsyncFunctionDef = visit_FunctionDef

    def visit_Compare(self, node):
        self.generic_visit(node)
        for i, op in enumerate(node.ops):
            new = COMPARE_SWAPS.get(type(op))
            if new and self._hit(node, f"{SYMBOL[type(op)]} -> {SYMBOL[new]}"):
                node.ops[i] = new()
        return node

    def visit_BinOp(self, node):
        self.generic_visit(node)
        new = BINOP_SWAPS.get(type(node.op))
        if new and self._hit(node, f"{SYMBOL[type(node.op)]} -> {SYMBOL[new]}"):
            node.op = new()
        return node

    def visit_BoolOp(self, node):
        self.generic_visit(node)
        new = ast.Or if isinstance(node.op, ast.And) else ast.And
        if self._hit(node, f"{SYMBOL[type(node.op)]} -> {SYMBOL[new]}"):
            node.op = new()
        return node

    def visit_UnaryOp(self, node):
        self.generic_visit(node)
        if isinstance(node.op, (ast.Not, ast.USub)) and self._hit(node, "remove unary operator"):
            return node.operand
        return node

    def visit_Constant(self, node):
        if isinstance(node.value, bool):
            if self._hit(node, f"{node.value} -> {not node.value}"):
                return ast.copy_location(ast.Constant(value=not node.value), node)
        elif isinstance(node.value, int):
            if self._hit(node, f"{node.value} -> {node.value + 1}"):
                return ast.copy_location(ast.Constant(value=node.value + 1), node)
        return node

    def _wrap_not(self, node, what):
        node.test = self.visit(node.test)
        if self._hit(node, f"negate the {what} condition"):
            node.test = ast.copy_location(ast.UnaryOp(op=ast.Not(), operand=node.test), node.test)
        return node

    def visit_If(self, node):
        self._wrap_not(node, "if")
        node.body = [self.visit(s) for s in node.body]
        node.orelse = [self.visit(s) for s in node.orelse]
        return node

    def visit_While(self, node):
        self._wrap_not(node, "while")
        node.body = [self.visit(s) for s in node.body]
        node.orelse = [self.visit(s) for s in node.orelse]
        return node

    def visit_IfExp(self, node):
        node.body, node.orelse = self.visit(node.body), self.visit(node.orelse)
        return self._wrap_not(node, "conditional-expression")

    def visit_Return(self, node):
        if node.value is not None:
            node.value = self.visit(node.value)
            if not (isinstance(node.value, ast.Constant) and node.value.value is None):
                if self._hit(node, "return None instead of the value"):
                    node.value = ast.copy_location(ast.Constant(value=None), node.value)
        return node

    def visit_AugAssign(self, node):
        node.value = self.visit(node.value)
        swap = {ast.Add: ast.Sub, ast.Sub: ast.Add}.get(type(node.op))
        if swap and self._hit(node, f"{SYMBOL[type(node.op)]}= -> {SYMBOL[swap]}="):
            node.op = swap()
        return node


def _skip_lines(source: str) -> set[int]:
    return {i for i, line in enumerate(source.splitlines(), 1) if "nomutate" in line}


def list_mutants(source: str) -> list[Mutant]:
    m = _Mutator(_skip_lines(source))
    m.visit(ast.parse(source))
    return m.found


def make_mutant(source: str, index: int) -> str:
    tree = ast.parse(source)
    m = _Mutator(_skip_lines(source), target=index)
    tree = m.visit(tree)
    ast.fix_missing_locations(tree)
    return ast.unparse(tree) + "\n"


@dataclass
class MutationReport:
    module: str
    total: int = 0
    killed: int = 0
    survivors: list[tuple[Mutant, str]] = field(default_factory=list)  # (mutant, diff)
    timed_out: int = 0  # mutants that made the tests hang: counted as killed
    seconds: float = 0.0

    @property
    def score(self) -> float:
        return self.killed / self.total if self.total else 1.0


class BaselineFailed(RuntimeError):
    pass


def _copy_project(src: Path, dst: Path) -> None:
    def ignore(_dir, names):
        return [n for n in names if n in IGNORE_DIRS or n.endswith(".pyc") or n.endswith(".sqlite3")]
    shutil.copytree(src, dst, ignore=ignore, dirs_exist_ok=True)


def _run(cmd: list[str], cwd: Path, timeout: float) -> tuple[Optional[int], str]:
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")
    try:
        p = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, timeout=timeout, env=env)
        return p.returncode, (p.stdout + p.stderr)
    except subprocess.TimeoutExpired:
        return None, "timed out"


def run_mutation(project_dir: str | Path, module: str, cmd: Optional[str] = None, *, timeout: float = 60,
                 max_mutants: Optional[int] = None) -> MutationReport:
    """Mutate `module` (a path relative to project_dir) and run `cmd` for each mutant.

    The project is copied to a temporary folder first, so your files are never touched.
    """
    project_dir = Path(project_dir).resolve()
    command = shlex.split(cmd) if cmd else [sys.executable, "-m", "pytest", "-x", "-q", "-p", "no:cacheprovider"]
    command = [sys.executable if c == "python" else c for c in command]
    original = (project_dir / module).read_text(encoding="utf-8")
    started = time.time()
    with tempfile.TemporaryDirectory(prefix="mutation-") as tmp:
        work = Path(tmp) / "project"
        _copy_project(project_dir, work)
        target = work / module
        code, output = _run(command, work, timeout)
        if code != 0:
            raise BaselineFailed("The tests fail before any mutation, so the result would mean nothing:\n"
                                 + "\n".join(output.strip().splitlines()[-12:]))
        mutants = list_mutants(original)
        if max_mutants:
            mutants = mutants[:max_mutants]
        report = MutationReport(module=module, total=len(mutants))
        for m in mutants:
            mutated = make_mutant(original, m.index)
            target.write_text(mutated, encoding="utf-8")
            code, _ = _run(command, work, timeout)
            if code == 0:
                diff = "\n".join(difflib.unified_diff(
                    ast.unparse(ast.parse(original)).splitlines(), mutated.splitlines(), lineterm="", n=0))
                report.survivors.append((m, "\n".join(l for l in diff.splitlines() if l[:1] in "+-" and l[:3] not in ("+++", "---"))))
            else:
                report.killed += 1  # failed or timed out: either way the tests noticed
                if code is None:
                    report.timed_out += 1
        report.seconds = time.time() - started
    return report


def format_report(report: MutationReport) -> str:
    lines = [f"Mutation testing: {report.module}",
             f"  mutants: {report.total}   killed: {report.killed}   survived: {len(report.survivors)}   "
             f"score: {report.score * 100:.0f}%   ({report.seconds:.0f}s)"
             + (f"   ({report.timed_out} timed out)" if report.timed_out else "")]
    if report.survivors:
        lines.append("  Survivors (a bug like this would pass your tests):")
        for m, diff in report.survivors:
            lines.append(f"    line {m.line:>3}: {m.description}")
    return "\n".join(lines)
