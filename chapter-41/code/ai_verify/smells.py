"""Spot tests that look like tests but check very little.

AI-written tests often pass, cover every line, and still protect nothing. These checks find
the common patterns by reading the test code. They are hints for a human reviewer, not
a verdict: a flagged test may be fine, and an unflagged one may still be weak. Mutation
testing (mutation.py) is the stronger check.
"""
from __future__ import annotations

import ast
from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class Smell:
    test: str
    line: int
    code: str
    message: str

    def __str__(self) -> str:
        return f"line {self.line}: {self.test}: {self.message}  [{self.code}]"


def _is_test(node: ast.AST) -> bool:
    return isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name.startswith("test")


def _calls(node: ast.AST) -> set[str]:
    out = set()
    for n in ast.walk(node):
        if isinstance(n, ast.Call):
            f = n.func
            out.add(f.id if isinstance(f, ast.Name) else f.attr if isinstance(f, ast.Attribute) else "")
    return out - {""}


def _numbers(node: ast.AST) -> set:
    return {n.value for n in ast.walk(node)
            if isinstance(n, ast.Constant) and isinstance(n.value, (int, float)) and not isinstance(n.value, bool)}


def _names(node: ast.AST) -> set:
    return {n.id for n in ast.walk(node) if isinstance(n, ast.Name)}


def _is_trivial(test: ast.expr) -> Optional[str]:
    """Return why an assert's condition proves little, or None if it looks meaningful."""
    if isinstance(test, ast.Constant):
        return "asserts a constant"
    if isinstance(test, (ast.Name, ast.Attribute, ast.Call)):
        if isinstance(test, ast.Call) and isinstance(test.func, ast.Name) and test.func.id == "isinstance":
            return "only checks the type"
        return "only checks truthiness"
    if isinstance(test, ast.UnaryOp) and isinstance(test.op, ast.Not) and isinstance(test.operand, (ast.Name, ast.Call, ast.Attribute)):
        return "only checks falsiness"
    if isinstance(test, ast.Compare) and len(test.ops) == 1:
        op, right = test.ops[0], test.comparators[0]
        if isinstance(op, (ast.Is, ast.IsNot)) and isinstance(right, ast.Constant) and right.value is None:
            return "only checks for None"
        if isinstance(op, (ast.Gt, ast.GtE, ast.Lt, ast.LtE, ast.NotEq)) and isinstance(right, ast.Constant) \
                and isinstance(right.value, (int, float)) and right.value == 0:
            return "only compares with zero"
    return None


def analyze_tests(source: str, *, target_names: Optional[set[str]] = None) -> list[Smell]:
    tree = ast.parse(source)
    smells: list[Smell] = []
    tests = [n for n in ast.walk(tree) if _is_test(n)]
    calls_per_target: dict[str, int] = {}

    for fn in tests:
        asserts = [n for n in ast.walk(fn) if isinstance(n, ast.Assert)]
        method_asserts = [n for n in ast.walk(fn) if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
                          and n.func.attr.startswith("assert")]
        raises = [n for n in ast.walk(fn) if isinstance(n, ast.With) and any(
            isinstance(i.context_expr, ast.Call) and getattr(i.context_expr.func, "attr", getattr(i.context_expr.func, "id", ""))
            in ("raises", "assertRaises", "warns") for i in n.items)]
        total = len(asserts) + len(method_asserts) + len(raises)
        called = _calls(fn)
        if target_names:
            for t in target_names & called:
                calls_per_target[t] = calls_per_target.get(t, 0) + 1

        if total == 0:
            smells.append(Smell(fn.name, fn.lineno, "no-assertion", "has no assertions: it passes unless the code crashes"))
            continue

        reasons = []
        for a in asserts:
            if isinstance(a.test, ast.Constant) or _is_trivial(a.test):
                reasons.append(_is_trivial(a.test) or "asserts a constant")
        only_trivial = len(asserts) == total and len(reasons) == len(asserts) and not raises
        if only_trivial:
            smells.append(Smell(fn.name, fn.lineno, "trivial-assertions",
                                f"every assertion is weak ({'; '.join(sorted(set(reasons)))})"))
        mock_only = method_asserts and not asserts and not raises and all(
            m.func.attr.startswith("assert_called") or m.func.attr in ("assert_not_called", "assert_any_call")
            for m in method_asserts)
        if mock_only:
            smells.append(Smell(fn.name, fn.lineno, "mock-only", "only checks that a mock was called, not what the code produced"))

        for a in asserts:
            t = a.test
            if isinstance(t, ast.Compare) and len(t.ops) == 1 and isinstance(t.ops[0], ast.Eq):
                left, right = t.left, t.comparators[0]
                if isinstance(left, ast.Call) and isinstance(right, (ast.BinOp, ast.Call)):
                    shared = _numbers(left) & _numbers(right)
                    shared_names = _names(left) & _names(right)  # the same variables feed both sides
                    same_fn = _calls(left) & _calls(right)
                    if (isinstance(right, ast.BinOp) and (shared or shared_names) and not _calls(right)) or same_fn:
                        smells.append(Smell(fn.name, a.lineno, "mirror-expected",
                                            "the expected value is computed from the same inputs, so a wrong formula "
                                            "would be copied into the test. Write the expected number by hand"))
        for n in ast.walk(fn):
            if isinstance(n, ast.Try):
                for h in n.handlers:
                    if all(isinstance(s, ast.Pass) for s in h.body) or (
                            h.type is not None and getattr(h.type, "id", "") in ("Exception", "BaseException")
                            and not any(isinstance(s, (ast.Raise, ast.Assert)) for s in ast.walk(h))):
                        smells.append(Smell(fn.name, n.lineno, "swallowed-exception",
                                            "catches an exception and carries on, so failures can pass silently"))

    for name, count in sorted(calls_per_target.items()):
        if count == 1:
            line = next((fn.lineno for fn in tests if name in _calls(fn)), 1)
            smells.append(Smell(name, line, "one-example",
                                f"{name}() is exercised by only one test: add boundaries and error cases"))
    if target_names:
        for name in sorted(target_names - set(calls_per_target)):
            smells.append(Smell(name, 1, "untested", f"{name}() is never called by a test"))
    return sorted(smells, key=lambda s: (s.line, s.code))
