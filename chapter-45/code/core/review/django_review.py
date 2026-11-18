"""A fast, offline reviewer for AI-generated Django code. It reads Python source with `ast` and flags the
mistakes that AI assistants (and tired humans) make most often. It finds smells, it does not prove code is safe.

Run:  python -m core.review.django_review backend/            (exit status 1 if any error is found)
"""
from __future__ import annotations

import ast
import re
import sys
from dataclasses import dataclass
from pathlib import Path

WRITE_METHODS = {"save", "create", "update", "delete", "bulk_create", "bulk_update", "update_or_create", "get_or_create"}
QUERY_METHODS = {"get", "filter", "all", "count", "exists", "first", "last", "aggregate", "values", "values_list"}
REQUESTS_METHODS = {"get", "post", "put", "patch", "delete", "head", "request"}
RANDOM_METHODS = {"choice", "choices", "randint", "random", "randrange", "getrandbits", "sample"}
SENSITIVE_FUNCTION = re.compile(r"(token|otp|passw|secret|api_?key|code|nonce|salt)", re.I)
SECRET_NAME = re.compile(r"(secret|passw(or)?d|api_?key|private_key|auth_token|access_token|webhook_secret)", re.I)
MONEY_NAME = re.compile(r"(price|amount|balance|total|cost|fee|subtotal|credit)", re.I)
VIEW_BASES = ("APIView", "ViewSet", "ModelViewSet", "GenericAPIView", "ReadOnlyModelViewSet", "GenericViewSet",
              "ListAPIView", "RetrieveAPIView", "CreateAPIView", "ListCreateAPIView", "RetrieveUpdateDestroyAPIView",
              "RetrieveUpdateAPIView", "DestroyAPIView", "UpdateAPIView", "ListModelMixin")


@dataclass(frozen=True)
class Finding:
    level: str      # error | warn | info
    code: str
    line: int
    message: str

    def __str__(self) -> str:
        return f"line {self.line:<4} {self.level.upper():5} {self.code}  {self.message}"


def _name(node: ast.AST) -> str:
    """Dotted name of a Name/Attribute chain, '' for anything else."""
    parts = []
    while isinstance(node, ast.Attribute):
        parts.append(node.attr)
        node = node.value
    if isinstance(node, ast.Name):
        parts.append(node.id)
        return ".".join(reversed(parts))
    return ""


def _is_dynamic_sql(node: ast.AST) -> bool:
    if isinstance(node, ast.JoinedStr):
        return any(isinstance(v, ast.FormattedValue) for v in node.values)
    if isinstance(node, ast.BinOp) and isinstance(node.op, (ast.Add, ast.Mod)):
        return not (isinstance(node.left, ast.Constant) and isinstance(node.right, ast.Constant))
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == "format":
        return True
    return False


class _Reviewer(ast.NodeVisitor):
    def __init__(self, filename: str):
        self.filename = filename
        self.findings: list[Finding] = []
        self.is_test = bool(re.search(r"(^|/)(tests?|test_[^/]*|[^/]*_tests?)\.py$|/tests?/", filename.replace("\\", "/")))
        self.is_dev_settings = bool(re.search(r"(dev|local|test)", filename.lower()))
        self.func_stack: list[ast.AST] = []
        self.class_stack: list[ast.ClassDef] = []
        self.loop_depth = 0

    def add(self, level: str, code: str, node: ast.AST, message: str) -> None:
        self.findings.append(Finding(level, code, getattr(node, "lineno", 0), message))

    # ---------------------------------------------------------------- classes
    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        bases = [_name(b).split(".")[-1] for b in node.bases]
        assigns = {t.id: s for s in node.body if isinstance(s, ast.Assign) for t in s.targets if isinstance(t, ast.Name)}
        if any(b in VIEW_BASES or b.endswith(("ViewSet", "APIView")) for b in bases) and not self.is_test:
            if "permission_classes" not in assigns and "get_permissions" not in {f.name for f in node.body if isinstance(f, ast.FunctionDef)}:
                self.add("warn", "DJ015", node, f"{node.name} sets no permission_classes: confirm the global default is deny-by-default")
        if "permission_classes" in assigns and "AllowAny" in ast.dump(assigns["permission_classes"].value):
            self.add("warn", "DJ016", node, f"{node.name} is public (AllowAny): confirm that is intended and rate limited")
        if any(isinstance(n, ast.ClassDef) and n.name == "Meta" for n in node.body):
            meta = next(n for n in node.body if isinstance(n, ast.ClassDef) and n.name == "Meta")
            for stmt in meta.body:
                if isinstance(stmt, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "fields" for t in stmt.targets):
                    if isinstance(stmt.value, ast.Constant) and stmt.value.value == "__all__":
                        self.add("error", "DJ001", stmt, "fields = '__all__' exposes (and accepts) every column; list the fields explicitly")
                if isinstance(stmt, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "exclude" for t in stmt.targets):
                    self.add("warn", "DJ002", stmt, "serializer exclude = ... leaks new columns by default; use an explicit fields list")
        self.class_stack.append(node)
        self.generic_visit(node)
        self.class_stack.pop()

    # -------------------------------------------------------------- functions
    def _visit_function(self, node) -> None:
        for default in [*node.args.defaults, *[d for d in node.args.kw_defaults if d is not None]]:
            if isinstance(default, (ast.List, ast.Dict, ast.Set)) or (isinstance(default, ast.Call) and _name(default.func) in ("list", "dict", "set")):
                self.add("error", "DJ007", default, "mutable default argument is shared between calls; default to None")
        writes = [n for n in ast.walk(node) if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
                  and n.func.attr in WRITE_METHODS
                  and (n.func.attr in ("save", "delete") or ".objects" in "." + _name(n.func.value))]
        has_atomic = any("atomic" in ast.dump(n) for n in (*node.decorator_list, *[i for w in ast.walk(node) if isinstance(w, ast.With) for i in w.items]))
        if len(writes) >= 2 and not has_atomic and not self.is_test:
            self.add("warn", "DJ020", node, f"{node.name} makes {len(writes)} database writes without transaction.atomic")
        in_view_class = bool(self.class_stack) and any(
            _name(b).split(".")[-1] in VIEW_BASES or _name(b).endswith(("ViewSet", "APIView")) for b in self.class_stack[-1].bases)
        if in_view_class and not self.is_test:
            for call in (n for n in ast.walk(node) if isinstance(n, ast.Call)):
                f = call.func
                if isinstance(f, ast.Attribute) and f.attr == "all" and _name(f.value).endswith(".objects"):
                    scoped = any(isinstance(n, ast.Attribute) and n.attr in ("user", "owner") for n in ast.walk(node)) or any(
                        isinstance(k, ast.keyword) and k.arg in ("user", "owner", "user_id") for n in ast.walk(node)
                        if isinstance(n, ast.Call) for k in n.keywords)
                    if not scoped:
                        self.add("warn", "DJ003", call, f"{node.name}: .objects.all() in a view with no user scoping; filter by request.user")
        self.func_stack.append(node)
        self.generic_visit(node)
        self.func_stack.pop()

    visit_FunctionDef = _visit_function
    visit_AsyncFunctionDef = _visit_function

    # ------------------------------------------------------------------ loops
    def _visit_loop(self, node) -> None:
        if not self.is_test:
            for call in (n for n in ast.walk(node) if isinstance(n, ast.Call)):
                f = call.func
                if isinstance(f, ast.Attribute) and f.attr in QUERY_METHODS | {"create"} and ".objects" in "." + _name(f.value):
                    self.add("warn", "DJ024", call, "database query inside a loop: possible N+1; use select_related, prefetch_related or one query")
                    break
        self.generic_visit(node)

    visit_For = visit_AsyncFor = _visit_loop

    # ------------------------------------------------------------------ calls
    def visit_Call(self, node: ast.Call) -> None:
        full = _name(node.func)
        short = full.split(".")[-1]
        if isinstance(node.func, ast.Name) and node.func.id in ("eval", "exec"):
            self.add("error", "DJ011", node, f"{node.func.id}() runs arbitrary code")
        if full in ("pickle.loads", "pickle.load", "marshal.loads"):
            self.add("error", "DJ011", node, f"{full} on untrusted data executes code")
        if full == "print" and not self.is_test:
            self.add("warn", "DJ009", node, "print() in application code: use logging (and never log secrets or message text)")
        if short in ("raw", "extra", "execute", "executemany") and node.args and _is_dynamic_sql(node.args[0]):
            self.add("error", "DJ005", node, f"{short}() with an interpolated string: SQL injection. Pass parameters separately")
        if full in ("datetime.now", "datetime.utcnow", "datetime.today", "date.today", "datetime.datetime.now",
                    "datetime.datetime.utcnow", "datetime.datetime.today") and not self.is_test:
            if not any(kw.arg == "tz" for kw in node.keywords) and not node.args:
                self.add("warn", "DJ008", node, f"{full}() is naive: use django.utils.timezone.now() (time zone aware)")
        if full.startswith("requests.") and short in REQUESTS_METHODS and not any(k.arg == "timeout" for k in node.keywords):
            self.add("warn", "DJ012", node, f"{full}() has no timeout: a slow server would hang a worker")
        if full.startswith("subprocess.") and any(k.arg == "shell" and isinstance(k.value, ast.Constant) and k.value.value is True for k in node.keywords):
            self.add("error", "DJ027", node, "subprocess with shell=True: command injection risk")
        if any(k.arg == "verify" and isinstance(k.value, ast.Constant) and k.value.value is False for k in node.keywords):
            self.add("error", "DJ028", node, "verify=False disables TLS certificate checks")
        if full.startswith("random.") and short in RANDOM_METHODS and self.func_stack:
            fn = self.func_stack[-1].name
            if SENSITIVE_FUNCTION.search(fn):
                self.add("error", "DJ010", node, f"random.{short} is predictable; use the secrets module for tokens and codes (in {fn})")
        self.generic_visit(node)

    def visit_Try(self, node: ast.Try) -> None:
        for h in node.handlers:
            if h.type is None:
                self.add("error", "DJ006", h, "bare except: catches KeyboardInterrupt and hides every bug")
            elif _name(h.type) in ("Exception", "BaseException") and all(isinstance(s, (ast.Pass, ast.Continue)) for s in h.body):
                self.add("warn", "DJ006", h, "except Exception: pass swallows every error; catch a specific one and log it")
        self.generic_visit(node)

    def visit_Assign(self, node: ast.Assign) -> None:
        for target in node.targets:
            tname = target.id if isinstance(target, ast.Name) else (target.attr if isinstance(target, ast.Attribute) else "")
            if not tname:
                continue
            if tname == "DEBUG" and isinstance(node.value, ast.Constant) and node.value.value is True and not self.is_dev_settings:
                self.add("warn", "DJ017", node, "DEBUG = True outside a dev settings file")
            if tname == "ALLOWED_HOSTS" and "'*'" in ast.dump(node.value).replace('"', "'"):
                self.add("error", "DJ018", node, "ALLOWED_HOSTS contains '*'")
            if (SECRET_NAME.search(tname) and isinstance(node.value, ast.Constant) and isinstance(node.value.value, str)
                    and len(node.value.value) >= 8 and not self.is_test and not node.value.value.startswith(("$", "<", "env:"))):
                self.add("error", "DJ013", node, f"{tname} is assigned a string literal: read secrets from the environment")
            if isinstance(node.value, ast.Call) and _name(node.value.func).endswith("FloatField") and MONEY_NAME.search(tname):
                self.add("error", "DJ014", node, f"{tname} is a FloatField: store money as integer minor units (kobo, cents)")
        self.generic_visit(node)


def _decorators_csrf(tree: ast.AST, rev: _Reviewer) -> None:
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            for d in node.decorator_list:
                n = _name(d.func if isinstance(d, ast.Call) else d)
                if n.endswith("csrf_exempt"):
                    rev.add("info", "DJ004", node, f"{node.name} is csrf_exempt: correct for webhooks that verify a signature, wrong otherwise")


def review_source(source: str, filename: str = "<string>") -> list[Finding]:
    try:
        tree = ast.parse(source, filename)
    except SyntaxError as exc:
        return [Finding("error", "DJ000", exc.lineno or 0, f"syntax error: {exc.msg}")]
    reviewer = _Reviewer(filename)
    reviewer.visit(tree)
    _decorators_csrf(tree, reviewer)
    seen, unique = set(), []
    for f in sorted(reviewer.findings, key=lambda f: (f.line, f.code)):
        if (f.line, f.code) not in seen:
            seen.add((f.line, f.code))
            unique.append(f)
    return unique


def review_path(root: Path) -> dict[str, list[Finding]]:
    files = [root] if root.is_file() else [p for p in root.rglob("*.py")
                                          if not any(part in ("migrations", ".venv", "venv", "node_modules", "__pycache__") for part in p.parts)]
    out = {}
    for path in sorted(files):
        found = review_source(path.read_text(encoding="utf-8"), str(path))
        if found:
            out[str(path)] = found
    return out


def main(argv: list[str] | None = None) -> int:
    root = Path((argv or sys.argv[1:] or ["."])[0])
    results = review_path(root)
    errors = warns = 0
    for path, findings in results.items():
        print(path)
        for f in findings:
            print("  " + str(f))
            errors += f.level == "error"
            warns += f.level == "warn"
    print(f"\n{errors} error(s), {warns} warning(s) in {len(results)} file(s)")
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
