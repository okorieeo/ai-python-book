"""
VERIFICATION ONLY. NOT FOR YOUR PROJECT. Use the real pytest there.

The sandbox this chapter was written in had no network, so pytest could not be installed. To still run the
chapter's Python tests, this ~200-line stand-in implements ONLY the pytest features those tests use:
plain `assert`, function and class tests, fixtures (including yield, autouse and conftest.py), parametrize,
raises, approx, monkeypatch, tmp_path, skipif, and async tests. It proves the logic of the tests; it does not
prove they behave identically under real pytest. Run them there (step 1 of the hands-on) to confirm.

    python verification_only/mini_pytest.py backend/tests [-k text]
"""
from __future__ import annotations

import asyncio
import contextlib
import importlib.util
import inspect
import itertools
import os
import pathlib
import shutil
import sys
import tempfile
import logging
import traceback
import types

# ------------------------------------------------------------------ the fake `pytest` module
pytest = types.ModuleType("pytest")


class Skipped(Exception):
    pass


class _Param:
    def __init__(self, values, id=None):
        self.values, self.id = values, id


def _fixture(func=None, *, autouse=False, scope="function", params=None):
    def deco(f):
        f._fixture = {"autouse": autouse}
        return f
    return deco(func) if func is not None else deco


def _parametrize(argnames, argvalues, ids=None):
    names = [n.strip() for n in argnames.split(",")] if isinstance(argnames, str) else list(argnames)

    def deco(f):
        rows = []
        for i, v in enumerate(argvalues):
            if isinstance(v, _Param):
                vals, pid = v.values, v.id
            else:
                vals, pid = (v if len(names) > 1 else (v,)), None
            label = pid or (ids[i] if ids else "-".join(str(x)[:20] for x in vals))
            rows.append((dict(zip(names, vals)), label))
        f.__dict__.setdefault("_parametrize", []).append(rows)
        return f
    return deco


def _skipif(cond, reason=""):
    def deco(f):
        f._skip = reason if cond else None
        return f
    return deco


class _Mark:
    parametrize = staticmethod(_parametrize)
    skipif = staticmethod(_skipif)

    def __getattr__(self, name):          # django_db, asyncio, slow ... : accepted and ignored
        return lambda *a, **k: (lambda f: f) if not (len(a) == 1 and callable(a[0]) and not k) else a[0]


class _ExcInfo:
    value = None
    type = None


@contextlib.contextmanager
def _raises(exc, match=None):
    info = _ExcInfo()
    try:
        yield info
    except exc as e:
        info.value, info.type = e, type(e)
        if match is not None:
            import re
            assert re.search(match, str(e)), f"{str(e)!r} does not match {match!r}"
    else:
        raise AssertionError(f"DID NOT RAISE {exc}")


class _Approx:
    def __init__(self, expected, rel=1e-6, abs=1e-12):
        self.e, self.rel, self.abs = expected, rel, abs

    def __eq__(self, other):
        return abs(other - self.e) <= max(self.abs, self.rel * abs(self.e))

    def __repr__(self):
        return f"approx({self.e})"


def _skip(reason=""):
    raise Skipped(reason)


def _fail(msg=""):
    raise AssertionError(msg)


pytest.fixture, pytest.mark, pytest.raises, pytest.approx = _fixture, _Mark(), _raises, _Approx
pytest.param, pytest.skip, pytest.fail = (lambda *v, id=None: _Param(v, id)), _skip, _fail
sys.modules["pytest"] = pytest


# ------------------------------------------------------------------ built-in fixtures
class MonkeyPatch:
    def __init__(self):
        self._undo = []

    def setattr(self, target, name, value=None, raising=True):
        if isinstance(target, str):                      # "package.module.attr", value
            value, name = name, target.rsplit(".", 1)[1]
            mod_path = target.rsplit(".", 1)[0]
            target = importlib.import_module(mod_path)
        old = getattr(target, name)
        self._undo.append(lambda t=target, n=name, o=old: setattr(t, n, o))
        setattr(target, name, value)

    def setenv(self, name, value):
        old = os.environ.get(name)
        self._undo.append(lambda: os.environ.__setitem__(name, old) if old is not None else os.environ.pop(name, None))
        os.environ[name] = str(value)

    def delenv(self, name, raising=True):
        old = os.environ.get(name)
        if old is None and raising:
            raise KeyError(name)
        self._undo.append(lambda: os.environ.__setitem__(name, old) if old is not None else None)
        os.environ.pop(name, None)

    def setitem(self, mapping, key, value):
        had, old = key in mapping, mapping.get(key)
        self._undo.append(lambda: mapping.__setitem__(key, old) if had else mapping.pop(key, None))
        mapping[key] = value

    def undo(self):
        while self._undo:
            self._undo.pop()()


def _builtin(name):
    if name == "monkeypatch":
        mp = MonkeyPatch()
        yield mp
        mp.undo()
    elif name == "tmp_path":
        d = tempfile.mkdtemp(prefix="minipytest-")
        yield pathlib.Path(d)
        shutil.rmtree(d, ignore_errors=True)
    else:
        raise LookupError(name)


# ------------------------------------------------------------------ collection and running
def _load(path: pathlib.Path):
    spec = importlib.util.spec_from_file_location(f"mp_{abs(hash(str(path)))}_{path.stem}", path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


def _fixtures_of(mod):
    return {n: f for n, f in vars(mod).items() if callable(f) and hasattr(f, "_fixture")}


class Runner:
    def __init__(self, root: pathlib.Path, keyword: str | None):
        self.root, self.keyword = root.resolve(), keyword
        self.passed = self.failed = self.skipped = 0
        self.failures: list[tuple[str, str]] = []

    def conftests(self, file: pathlib.Path):
        out, d = [], file.parent
        while True:
            c = d / "conftest.py"
            if c.exists():
                out.append(c)
            if d == self.root or d == d.parent:
                break
            d = d.parent
        return list(reversed(out))

    def run(self):
        sys.path.insert(0, str(self.root.parent))
        sys.path.insert(0, str(self.root))
        files = sorted(self.root.rglob("test_*.py")) if self.root.is_dir() else [self.root]
        for f in files:
            fixtures = {}
            for c in self.conftests(f):
                fixtures.update(_fixtures_of(_load(c)))
            mod = _load(f)
            fixtures.update(_fixtures_of(mod))
            for name, obj in vars(mod).items():
                if name.startswith("test_") and callable(obj):
                    self.run_test(f"{f.name}::{name}", obj, None, fixtures)
                elif name.startswith("Test") and inspect.isclass(obj):
                    for m in dir(obj):
                        if m.startswith("test_"):
                            self.run_test(f"{f.name}::{name}::{m}", getattr(obj, m), obj, fixtures)
        print(f"\n{self.passed} passed, {self.failed} failed, {self.skipped} skipped")
        for tid, tb in self.failures:
            print(f"\n--- FAILED {tid}\n{tb}")
        return 1 if self.failed else 0

    def run_test(self, tid, fn, cls, fixtures):
        target = fn.__func__ if hasattr(fn, "__func__") else fn
        combos = [dict()]
        raw = getattr(target, "_parametrize", [])
        if raw:
            combos = []
            for chosen in itertools.product(*raw):
                params, labels = {}, []
                for p, l in chosen:
                    params.update(p); labels.append(l)
                combos.append({"_p": params, "_l": "-".join(labels)})
        for combo in combos:
            full = tid + (f"[{combo['_l']}]" if "_l" in combo else "")
            if self.keyword and self.keyword not in full:
                continue
            if getattr(target, "_skip", None):
                self.skipped += 1
                continue
            self.execute(full, target, cls, combo.get("_p", {}), fixtures)

    def execute(self, tid, target, cls, params, fixtures):
        teardowns, cache = [], {}

        def resolve(name, stack=()):
            if name in params:
                return params[name]
            if name in cache:
                return cache[name]
            if name in fixtures:
                f = fixtures[name]
                args = {a: resolve(a, stack + (name,)) for a in inspect.signature(f).parameters}
                result = f(**args)
                if inspect.isgenerator(result):
                    teardowns.append(result)
                    result = next(result)
                cache[name] = result
                return result
            gen = _builtin(name)
            teardowns.append(gen)
            cache[name] = next(gen)
            return cache[name]

        try:
            instance = cls() if cls else None
            if cls:                                          # fixtures defined inside the test class
                fixtures = dict(fixtures)
                for n in dir(cls):
                    if hasattr(getattr(cls, n, None), "_fixture"):
                        fixtures[n] = getattr(instance, n)
            for name, f in fixtures.items():                 # autouse fixtures first
                if f._fixture["autouse"]:
                    resolve(name)
            sig = [p for p in inspect.signature(target).parameters if p != "self"]
            kwargs = {a: resolve(a) for a in sig}
            call = (lambda: target(instance, **kwargs)) if cls else (lambda: target(**kwargs))
            if inspect.iscoroutinefunction(target):
                asyncio.run(call())
            else:
                call()
            self.passed += 1
            print(".", end="", flush=True)
        except Skipped:
            self.skipped += 1
        except BaseException:
            self.failed += 1
            self.failures.append((tid, traceback.format_exc(limit=6)))
            print("F", end="", flush=True)
        finally:
            for g in reversed(teardowns):
                with contextlib.suppress(StopIteration):
                    next(g)


if __name__ == "__main__":
    logging.disable(logging.CRITICAL)      # real pytest captures log output; keep this stand-in quiet
    args = sys.argv[1:]
    kw = None
    if "-k" in args:
        i = args.index("-k"); kw = args[i + 1]; del args[i:i + 2]
    sys.exit(Runner(pathlib.Path(args[0] if args else "."), kw).run())
