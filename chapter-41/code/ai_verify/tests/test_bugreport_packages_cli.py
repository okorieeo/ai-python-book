from datetime import datetime, timedelta, timezone

import pytest

from ai_verify import bugreport, cli, packages


# ----------------------------------------------------------------- redaction
@pytest.mark.parametrize("secret", [
    "sk-ant-api03-AbCdEf1234567890abcdef",
    "sk-proj1234567890abcdefghij",
    "AKIAIOSFODNN7EXAMPLE",
    "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0In0.SflKxwRJSMeKKF2QT4fwpM",
    "ada.lovelace@example.com",
    "+234 803 123 4567",
    "08031234567",
    "4111 1111 1111 1111",
])
def test_secrets_and_personal_data_are_removed(secret):
    out = bugreport.redact(f"before {secret} after")
    assert secret not in out and "REDACTED" in out and out.startswith("before") and out.endswith("after")


def test_assignments_headers_and_urls_keep_their_names_but_lose_the_value():
    assert "hunter2" not in bugreport.redact("password = hunter2")
    assert "password" in bugreport.redact("password = hunter2")
    assert "abc123" not in bugreport.redact('API_KEY="abc123"')
    assert "tok_live" not in bugreport.redact("Authorization: Bearer tok_live_999")
    redacted = bugreport.redact("postgres://dbuser:s3cret@db.internal:5432/app")
    assert "s3cret" not in redacted and "dbuser" in redacted


def test_home_folders_lose_the_username():
    out = bugreport.redact('File "/home/okorie/app/x.py" and C:\\Users\\Ada\\app\\y.py and /Users/ada/z.py')
    assert "okorie" not in out and "Ada" not in out and "/Users/ada" not in out


def test_ordinary_text_is_left_alone():
    text = "TypeError: unsupported operand at line 42, total 1500 messages"
    assert bugreport.redact(text) == text


# ----------------------------------------------------------------- traceback
def make_tb(n_library):
    lines = ["Traceback (most recent call last):",
             '  File "/app/views.py", line 10, in handler', "    return charge(user)"]
    for i in range(n_library):
        lines += [f'  File "/venv/lib/python3.12/site-packages/lib/mod{i}.py", line {i}, in inner{i}', "    call()"]
    lines += ['  File "/app/billing.py", line 99, in charge', "    raise ValueError(x)", "ValueError: bad value"]
    return "\n".join(lines)


def test_library_frames_in_the_middle_are_folded_but_your_frames_and_the_error_stay():
    out = bugreport.trim_traceback(make_tb(12))
    assert "/app/views.py" in out and "/app/billing.py" in out
    assert out.rstrip().endswith("ValueError: bad value")
    assert "library frames not shown" in out
    assert out.count("site-packages") < 12


def test_short_tracebacks_are_unchanged_and_empty_is_fine():
    tb = make_tb(2)
    assert bugreport.trim_traceback(tb) == tb
    assert bugreport.trim_traceback("") == ""


# -------------------------------------------------------------------- report
def report(**kw):
    base = dict(title="Charge fails", expected="a receipt", actual="a crash")
    base.update(kw)
    return bugreport.build_bug_report(**base)


def test_the_report_has_the_sections_that_get_useful_answers():
    r = report(steps="call charge()", traceback=make_tb(1), code="def charge(): ...", tried="restarted",
               constraints="keep the API")
    for heading in ("# Charge fails", "## Environment", "## What I expected", "## What happened instead",
                    "## Smallest way to reproduce", "## Error (trimmed)", "## Relevant code",
                    "## What I already tried", "## Constraints", "## What I would like from you"):
        assert heading in r, heading
    assert "failing test" in r and "could not verify" in r
    assert f"Python {bugreport.platform.python_version()}" in r


def test_optional_sections_are_left_out_when_empty():
    r = report()
    assert "Smallest way to reproduce" not in r and "Relevant code" not in r


def test_everything_in_the_report_is_redacted():
    r = report(actual="key sk-ant-api03-AbCdEf1234567890abcdef failed for ada@example.com",
               code="API_KEY = 'abc12345'", traceback='File "/home/ada/x.py", line 1, in f\nValueError: x')
    for leaked in ("sk-ant-api03", "ada@example.com", "abc12345", "/home/ada"):
        assert leaked not in r


def test_the_report_is_bounded_in_size():
    r = report(code="x = 1\n" * 10_000, max_chars=2_000)
    assert len(r) <= 2_000 and "report cut to fit" in r


def test_package_versions_appear_in_the_environment_line():
    env = bugreport.environment_summary(("pytest", "no-such-package-zzz"))
    assert "pytest " in env and "no-such-package-zzz (not installed)" in env


# ------------------------------------------------------------------ packages
NOW = datetime(2026, 11, 1, tzinfo=timezone.utc)


def pkg(first, latest, n=10, urls=True):
    releases = {f"1.{i}": [{"upload_time_iso_8601": (first + (latest - first) * i / max(n - 1, 1)).isoformat().replace("+00:00", "Z")}]
                for i in range(n)}
    info = {"summary": "A package", "project_urls": {"Source": "https://example.com"} if urls else None, "home_page": ""}
    return {"info": info, "releases": releases}


def test_a_missing_package_is_flagged_as_possibly_invented():
    r = packages.check_package("nope", fetch=lambda url: None, now=NOW)
    assert not r.exists and "NOT FOUND" in r.flags[0]
    assert "Do not install" in packages.format_package(r)


def test_a_new_package_with_few_releases_and_no_links_raises_flags():
    data = pkg(NOW - timedelta(days=10), NOW - timedelta(days=5), n=1, urls=False)
    r = packages.check_package("fresh", fetch=lambda url: data, now=NOW)
    assert r.exists and len(r.flags) == 3
    assert any("Very new" in f for f in r.flags) and any("Few releases" in f for f in r.flags)
    assert any("No project links" in f for f in r.flags)


def test_an_established_package_raises_no_flags():
    data = pkg(NOW - timedelta(days=2000), NOW - timedelta(days=20), n=40)
    r = packages.check_package("solid", fetch=lambda url: data, now=NOW)
    assert r.flags == [] and r.releases == 40
    assert "no flags raised" in packages.format_package(r)


def test_a_package_nobody_has_updated_for_years_is_flagged():
    data = pkg(NOW - timedelta(days=4000), NOW - timedelta(days=1000), n=12)
    assert any("two years" in f for f in packages.check_package("old", fetch=lambda u: data, now=NOW).flags)


def test_the_pypi_url_is_built_from_the_name():
    seen = []
    packages.check_package("some-pkg", fetch=lambda url: seen.append(url) or None, now=NOW)
    assert seen == ["https://pypi.org/pypi/some-pkg/json"]


# ----------------------------------------------------------------------- cli
def test_cli_imports_exit_codes(capsys, tmp_path):
    bad = tmp_path / "bad.py"
    bad.write_text("import json\njson.parse('x')\n")
    good = tmp_path / "good.py"
    good.write_text("import json\njson.loads('1')\n")
    assert cli.main(["imports", str(bad)]) == 1
    assert "missing-attribute" in capsys.readouterr().out
    assert cli.main(["imports", str(good)]) == 0


def test_cli_smells_and_bugreport(capsys, tmp_path):
    t = tmp_path / "test_x.py"
    t.write_text("def test_a():\n    f(1)\n")
    assert cli.main(["smells", str(t)]) == 1
    assert "no-assertion" in capsys.readouterr().out
    assert cli.main(["bugreport", "--title", "T", "--expected", "e", "--actual", "a key sk-ant-api03-AbCdEf1234567890"]) == 0
    out = capsys.readouterr().out
    assert "# T" in out and "sk-ant" not in out


def test_cli_package_uses_the_checker(capsys, monkeypatch):
    monkeypatch.setattr(packages, "default_fetch", lambda url: None)
    monkeypatch.setattr(packages, "check_package",
                        lambda name, **kw: packages.PackageReport(name, False, flags=["NOT FOUND on PyPI"]))
    assert cli.main(["package", "ghost"]) == 0
    assert "NOT FOUND" in capsys.readouterr().out
