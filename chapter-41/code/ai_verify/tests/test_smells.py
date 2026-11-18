import textwrap
from pathlib import Path

from ai_verify.smells import analyze_tests

ROOT = Path(__file__).resolve().parents[2]


def smell_codes(src, **kw):
    return sorted(s.code for s in analyze_tests(textwrap.dedent(src), **kw))


def test_a_test_with_no_assertion():
    assert smell_codes("def test_x():\n    f(1)\n") == ["no-assertion"]


def test_pytest_raises_and_unittest_asserts_count_as_assertions():
    assert smell_codes("""
        import pytest
        def test_a():
            with pytest.raises(ValueError):
                f(1)
        class T:
            def test_b(self):
                self.assertEqual(f(1), 2)
    """) == []


def test_trivial_assertions_are_flagged():
    for body in ("assert isinstance(f(1), int)", "assert f(1)", "assert f(1) is not None", "assert f(1) > 0",
                 "assert True", "assert not f(1)"):
        assert smell_codes(f"def test_x():\n    {body}\n") == ["trivial-assertions"], body


def test_one_meaningful_assertion_saves_the_test():
    assert smell_codes("def test_x():\n    assert f(1) is not None\n    assert f(1) == 7\n") == []


def test_mirror_expected_values_are_flagged():
    src = """
        def test_discount():
            price = 2000
            pct = 25
            assert apply(price, pct) == price - price * pct / 100
    """
    assert "mirror-expected" in smell_codes(src)
    assert smell_codes("def test_ok():\n    assert apply(2000, 25) == 1500\n") == []
    assert "mirror-expected" in smell_codes("def test_same():\n    assert f(3) == f(3)\n")


def test_mock_only_tests_are_flagged():
    assert smell_codes("def test_x(mock_send):\n    run()\n    mock_send.assert_called_once()\n") == ["mock-only"]


def test_swallowed_exceptions_are_flagged():
    assert "swallowed-exception" in smell_codes("""
        def test_x():
            try:
                f(1)
            except Exception:
                pass
            assert f(2) == 3
    """)


def test_targets_tested_once_or_never_are_reported():
    src = "def test_a():\n    assert f(1) == 2\n"
    assert smell_codes(src, target_names={"f", "g"}) == ["one-example", "untested"]
    two = src + "def test_b():\n    assert f(2) == 3\n"
    assert smell_codes(two, target_names={"f"}) == []


def test_the_sample_weak_suite_is_flagged_and_the_strong_one_is_clean():
    import ast
    names = {n.name for n in ast.parse((ROOT / "sample/billing_math.py").read_text()).body
             if isinstance(n, ast.FunctionDef)}
    weak = analyze_tests((ROOT / "sample/test_weak.py").read_text(), target_names=names)
    codes = {s.code for s in weak}
    assert {"no-assertion", "trivial-assertions", "mirror-expected"} <= codes
    assert analyze_tests((ROOT / "sample/test_strong.py").read_text(), target_names=names) == []
