import sys
import textwrap

from ai_verify.hallucination import check_source, prepare_environment


def codes(src):
    return [(f.code, f.severity) for f in check_source(textwrap.dedent(src))]


def test_valid_code_has_no_findings():
    assert codes("""
        import json
        import os.path
        from datetime import datetime, timezone
        from os import path
        print(json.dumps({}), os.path.exists("x"), path.join("a", "b"), datetime.now(timezone.utc))
    """) == []


def test_a_module_that_does_not_exist_is_an_error():
    assert ("missing-module", "error") in codes("import definitely_not_a_real_module_xyz")
    assert ("missing-module", "error") in codes("from definitely_not_real_pkg import thing")


def test_a_name_that_does_not_exist_in_a_module_is_an_error():
    assert codes("from os.path import exists_file") == [("missing-name", "error")]


def test_submodules_imported_with_from_are_found():
    assert codes("from os import path") == []
    assert codes("from xml import etree") == []


def test_a_missing_attribute_is_found_through_aliases_too():
    assert codes("import json\njson.parse('{}')") == [("missing-attribute", "error")]
    assert codes("import json as j\nj.parse('{}')") == [("missing-attribute", "error")]
    assert codes("import os.path\nos.path.exists_file('x')") == [("missing-attribute", "error")]


def test_identical_findings_on_one_line_are_reported_once():
    found = check_source("import json\nx = json.parse('a') + json.parse('b')")
    assert len(found) == 1 and found[0].line == 2
    assert len(check_source("import json\njson.parse('a')\njson.parse('b')")) == 2  # different lines: both reported


def test_an_unexpected_keyword_argument_is_an_error():
    assert codes("import os.path\nos.path.exists('x', nope=True)") == [("bad-keyword", "error")]
    assert codes("import json\njson.dumps({}, indent=2)") == []


def test_functions_that_take_kwargs_accept_any_keyword():
    # json.loads declares **kw, so any keyword name is plausible and nothing is reported
    assert codes("import json\njson.loads('1', anything_at_all=1)") == []


def test_too_many_positional_arguments_is_an_error():
    assert ("too-many-args", "error") in codes("import os.path\nos.path.exists('a', 'b')")


def test_attributes_of_run_time_objects_are_not_guessed():
    assert codes("from datetime import datetime\ndatetime.now().anything_at_all()") == []


def test_classes_made_by_a_metaclass_are_not_judged():
    assert codes("from enum import Enum\nEnum.NOT_THERE") == []


def test_a_module_that_fails_to_import_for_another_reason_is_only_a_warning(tmp_path, monkeypatch):
    (tmp_path / "explodes.py").write_text("raise RuntimeError('needs configuration')\n")
    monkeypatch.syspath_prepend(str(tmp_path))
    sys.modules.pop("explodes", None)
    assert codes("import explodes") == [("unverified", "warning")]


def test_prepare_environment_makes_your_own_project_importable(tmp_path):
    pkg = tmp_path / "myproj_for_test"
    pkg.mkdir()
    (pkg / "__init__.py").write_text("")
    (pkg / "tools.py").write_text("def helper(a): return a\n")
    assert ("missing-module", "error") in codes("from myproj_for_test import tools")
    prepare_environment(str(tmp_path))
    try:
        assert codes("from myproj_for_test import tools\ntools.helper(1)") == []
        assert codes("from myproj_for_test import tools\ntools.nope(1)") == [("missing-attribute", "error")]
    finally:
        sys.path.remove(str(tmp_path))


def test_relative_imports_and_star_imports_are_left_alone():
    assert codes("from . import sibling\nfrom .models import Thing\nfrom os import *") == []


def test_findings_are_sorted_and_printable():
    found = check_source("import json\nimport nope_nope_nope\njson.parse(1)")
    assert [f.line for f in found] == sorted(f.line for f in found)
    assert "line 2" in str(found[0]) and "missing-module" in str(found[0])


def test_the_example_snippet_has_exactly_the_four_planted_problems():
    from pathlib import Path
    root = Path(__file__).resolve().parents[2]
    prepare_environment(None, None)
    bad = check_source((root / "examples" / "ai_snippet.py").read_text())
    assert sorted(f.code for f in bad) == ["bad-keyword", "missing-attribute", "missing-attribute", "missing-name"]
    assert check_source((root / "examples" / "valid_snippet.py").read_text()) == []
