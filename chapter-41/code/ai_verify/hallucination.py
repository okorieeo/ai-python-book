"""Check that the names in a piece of Python code really exist.

AI assistants sometimes write code that looks right but calls a function that does not
exist (a habit carried over from another language or an older library version), or passes
a keyword argument the installed version no longer accepts. This checker imports the
modules the code uses, and verifies imports, attribute chains and keyword arguments
against what is actually installed. It never runs the code being checked.

It is a static check with limits: it cannot see attributes of objects that only exist at
run time (the result of a function call, a Django model instance). Treat "no findings" as
"no obvious invention", not as "correct".
"""
from __future__ import annotations

import ast
import importlib
import inspect
from dataclasses import dataclass
from types import ModuleType
from typing import Any


@dataclass(frozen=True)
class Finding:
    severity: str  # "error": certainly wrong here. "warning": could not verify.
    line: int
    code: str      # missing-module, missing-name, missing-attribute, bad-keyword, too-many-args, unverified
    message: str

    def __str__(self) -> str:
        return f"line {self.line}: {self.severity}: {self.message}  [{self.code}]"


def _dotted(node: ast.AST) -> list[str] | None:
    """['os', 'path', 'exists'] for the expression os.path.exists, else None."""
    parts: list[str] = []
    while isinstance(node, ast.Attribute):
        parts.append(node.attr)
        node = node.value
    if isinstance(node, ast.Name):
        parts.append(node.id)
        return list(reversed(parts))
    return None


def _try_import(name: str) -> tuple[ModuleType | None, Exception | None]:
    try:
        return importlib.import_module(name), None
    except ModuleNotFoundError as exc:
        return None, exc
    except Exception as exc:  # e.g. a framework that needs settings configured
        return None, exc


def _checkable_container(obj: Any) -> bool:
    """Only report a missing attribute where Python itself can be trusted about it."""
    if isinstance(obj, ModuleType):
        return True
    # A plain class. Classes built by a metaclass (Django models, enums, ORMs) get
    # attributes at run time, so a missing one proves nothing.
    return inspect.isclass(obj) and type(obj) is type


def prepare_environment(root: str | None = None, django_settings: str | None = None) -> None:
    """Make your own project importable, and (optionally) set Django up, before checking.

    Run the checker from your project root, or pass its folder here. Without this, your own
    absolute imports (`from myapp.models import X`) look like missing modules.
    """
    import os
    import sys
    if root and root not in sys.path:
        sys.path.insert(0, root)
    if django_settings:
        os.environ["DJANGO_SETTINGS_MODULE"] = django_settings
        import django
        django.setup()


def check_source(code: str) -> list[Finding]:
    tree = ast.parse(code)
    findings: list[Finding] = []
    names: dict[str, Any] = {}  # local name -> the real object it refers to

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                module, err = _try_import(alias.name)
                if module is None:
                    kind = "missing-module" if isinstance(err, ModuleNotFoundError) else "unverified"
                    sev = "error" if kind == "missing-module" else "warning"
                    findings.append(Finding(sev, node.lineno, kind, f"cannot import {alias.name!r}: {err}"))
                    continue
                if alias.asname:
                    names[alias.asname] = module
                else:  # `import a.b.c` binds the top-level name `a`
                    names[alias.name.split(".")[0]] = importlib.import_module(alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom):
            if node.level:  # relative imports belong to your own project
                continue
            module, err = _try_import(node.module or "")
            if module is None:
                kind = "missing-module" if isinstance(err, ModuleNotFoundError) else "unverified"
                sev = "error" if kind == "missing-module" else "warning"
                findings.append(Finding(sev, node.lineno, kind, f"cannot import module {node.module!r}: {err}"))
                continue
            for alias in node.names:
                if alias.name == "*":
                    continue
                try:
                    names[alias.asname or alias.name] = getattr(module, alias.name)
                    continue
                except AttributeError:
                    pass  # not an attribute: it may be a submodule, checked next
                except Exception as exc:  # a lazy attribute that needs configuration (Django settings)
                    findings.append(Finding("warning", node.lineno, "unverified",
                                            f"could not look up {node.module}.{alias.name}: {exc}"))
                    continue
                sub, _ = _try_import(f"{node.module}.{alias.name}")  # a submodule, as in `from django.db import models`
                if sub is not None:
                    names[alias.asname or alias.name] = sub
                else:
                    findings.append(Finding(
                        "error", node.lineno, "missing-name",
                        f"{node.module!r} has no name {alias.name!r}"))

    seen_chains: set[tuple[int, str]] = set()

    def resolve(chain: list[str], line: int) -> Any | None:
        obj = names.get(chain[0])
        if obj is None:
            return None
        walked = chain[0]
        for part in chain[1:]:
            if not _checkable_container(obj):
                return None  # stop quietly: we cannot know what this object has
            try:
                obj = getattr(obj, part)
            except AttributeError:
                key = (line, ".".join(chain[: chain.index(part, 1) + 1]))
                if key not in seen_chains:
                    seen_chains.add(key)
                    findings.append(Finding("error", line, "missing-attribute",
                                            f"{walked!r} has no attribute {part!r}"))
                return None
            except Exception as exc:
                findings.append(Finding("warning", line, "unverified", f"could not look up {walked}.{part}: {exc}"))
                return None
            walked += "." + part
        return obj

    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute):
            chain = _dotted(node)
            if chain and chain[0] in names:
                resolve(chain, node.lineno)
        if isinstance(node, ast.Call):
            chain = _dotted(node.func)
            func = resolve(chain, node.lineno) if chain and chain[0] in names else None
            if func is None or not callable(func):
                continue
            try:
                sig = inspect.signature(func)
            except (TypeError, ValueError):
                continue
            params = sig.parameters
            takes_kwargs = any(p.kind is p.VAR_KEYWORD for p in params.values())
            takes_args = any(p.kind is p.VAR_POSITIONAL for p in params.values())
            label = ".".join(chain)
            if not takes_kwargs:
                for kw in node.keywords:
                    if kw.arg is not None and kw.arg not in params:
                        findings.append(Finding(
                            "error", node.lineno, "bad-keyword",
                            f"{label}() does not accept the keyword {kw.arg!r} in the installed version"))
            positional = [p for p in params.values() if p.kind in (p.POSITIONAL_ONLY, p.POSITIONAL_OR_KEYWORD)]
            has_star = any(isinstance(a, ast.Starred) for a in node.args)
            if not takes_args and not has_star and len(node.args) > len(positional):
                findings.append(Finding("error", node.lineno, "too-many-args",
                                        f"{label}() takes at most {len(positional)} positional arguments, got {len(node.args)}"))

    unique = {(f.line, f.code, f.message): f for f in findings}
    return sorted(unique.values(), key=lambda f: (f.line, f.code))
