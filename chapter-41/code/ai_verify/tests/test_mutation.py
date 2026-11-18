import ast
import textwrap

import pytest

from ai_verify.mutation import BaselineFailed, list_mutants, make_mutant, run_mutation


def src(text):
    return textwrap.dedent(text).lstrip("\n")


def test_each_kind_of_change_is_listed():
    code = src('''
        def f(a, b):
            """Docstring with 100 and < in it."""
            if a < b and not a:
                return a + b * 2
            return None
    ''')
    described = [m.description for m in list_mutants(code)]
    for expected in ("< -> <=", "and -> or", "remove unary operator", "+ -> -", "* -> //", "2 -> 3",
                     "negate the if condition", "return None instead of the value"):
        assert expected in described, expected
    assert not any("100" in d for d in described)  # the docstring is left alone


def test_annotations_and_defaults_are_left_alone():
    code = src('''
        def f(a: int = 5) -> int:
            x: int = 3
            return a
    ''')
    described = [m.description for m in list_mutants(code)]
    assert "5 -> 6" not in described
    assert "3 -> 4" in described  # the value being assigned is real code


def test_nomutate_marks_lines_to_skip():
    code = src('''
        def f(a):
            return a + 1  # nomutate
    ''')
    assert list_mutants(code) == []


def test_mutants_are_valid_python_and_differ_from_the_original():
    code = src('''
        def f(a, b):
            if a < b:
                return a - b
            return b % 3
    ''')
    for m in list_mutants(code):
        mutated = make_mutant(code, m.index)
        ast.parse(mutated)
        assert mutated != ast.unparse(ast.parse(code)) + "\n"


def test_applying_one_mutant_changes_exactly_that_site():
    code = "def f(a, b):\n    return a < b\n"
    ns = {}
    exec(make_mutant(code, [m.index for m in list_mutants(code) if m.description == "< -> <="][0]), ns)
    assert ns["f"](2, 2) is True and ns["f"](3, 2) is False


@pytest.fixture
def project(tmp_path):
    (tmp_path / "lt.py").write_text("def lt(a, b):\n    return a < b\n")
    return tmp_path


def run(project, tests):
    (project / "test_lt.py").write_text(tests)
    return run_mutation(project, "lt.py", "python -m pytest -x -q -p no:cacheprovider test_lt.py", timeout=30)


def test_weak_tests_let_mutants_survive(project):
    report = run(project, "from lt import lt\n\ndef test_one():\n    assert lt(1, 2)\n")
    assert report.total == 2 and report.killed == 1
    assert [m.description for m, _ in report.survivors] == ["< -> <="]
    assert report.score == 0.5


def test_strong_tests_kill_every_mutant(project):
    report = run(project, "from lt import lt\n\ndef test_edges():\n    assert lt(1, 2) is True\n"
                          "    assert lt(2, 2) is False\n    assert lt(3, 2) is False\n")
    assert (report.total, report.killed, report.survivors) == (2, 2, [])
    assert report.score == 1.0


def test_the_original_project_is_never_touched(project):
    before = (project / "lt.py").read_text()
    run(project, "from lt import lt\n\ndef test_one():\n    assert lt(1, 2)\n")
    assert (project / "lt.py").read_text() == before


def test_failing_baseline_tests_are_refused(project):
    with pytest.raises(BaselineFailed):
        run(project, "from lt import lt\n\ndef test_wrong():\n    assert lt(2, 1)\n")


def test_an_infinite_loop_mutant_counts_as_killed(tmp_path):
    (tmp_path / "loop.py").write_text("def count(n):\n    i = 0\n    while i < n:\n        i += 1\n    return i\n")
    (tmp_path / "test_loop.py").write_text("from loop import count\n\ndef test_c():\n    assert count(3) == 3\n")
    report = run_mutation(tmp_path, "loop.py", "python -m pytest -x -q -p no:cacheprovider test_loop.py", timeout=3)
    assert report.timed_out >= 1  # `i += 1` turned into `i -= 1` never finishes
    # the only survivor starts the counter at 1, which gives the same answer for count(3): a weak test
    assert [m.description for m, _ in report.survivors] == ["0 -> 1"]
