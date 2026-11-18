"""Compare a plain-text ERD with the Django models that were generated from it.

The ERD is the source of truth you give Claude Code; this tool tells you where the generated models differ.

ERD format (one model per block, two-space indent):
    model Conversation
      public_id uuid unique
      user fk User cascade
      title char(200)
      archived_at datetime null
      index (user, -updated_at)
      unique (user, slug)

Run:  python -m core.review.erd_check docs/erd.txt backend/conversations/models.py
"""
from __future__ import annotations

import ast
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

DJANGO_FOR = {
    "uuid": {"UUIDField"}, "char": {"CharField"}, "text": {"TextField"}, "int": {"IntegerField", "PositiveIntegerField", "SmallIntegerField", "PositiveSmallIntegerField"},
    "bigint": {"BigIntegerField", "PositiveBigIntegerField"}, "bool": {"BooleanField"}, "datetime": {"DateTimeField"},
    "date": {"DateField"}, "json": {"JSONField"}, "email": {"EmailField"}, "url": {"URLField"}, "slug": {"SlugField"},
    "fk": {"ForeignKey"}, "one2one": {"OneToOneField"}, "decimal": {"DecimalField"},
}


@dataclass
class ErdField:
    name: str
    kind: str
    length: int | None = None
    target: str | None = None
    on_delete: str | None = None
    unique: bool = False
    index: bool = False
    null: bool = False


@dataclass
class ErdModel:
    name: str
    fields: dict[str, ErdField] = field(default_factory=dict)
    indexes: list[tuple[str, ...]] = field(default_factory=list)
    uniques: list[tuple[str, ...]] = field(default_factory=list)


@dataclass(frozen=True)
class Difference:
    level: str   # error | warn | info
    model: str
    message: str

    def __str__(self) -> str:
        return f"{self.level.upper():5} {self.model:18} {self.message}"


class ErdSyntaxError(ValueError):
    pass


def parse_erd(text: str) -> dict[str, ErdModel]:
    models: dict[str, ErdModel] = {}
    current: ErdModel | None = None
    for n, raw in enumerate(text.splitlines(), 1):
        line = raw.split("#", 1)[0].rstrip()
        if not line.strip():
            continue
        if not raw.startswith(" "):
            m = re.fullmatch(r"model\s+(\w+)", line.strip())
            if not m:
                raise ErdSyntaxError(f"line {n}: expected 'model Name', got {line.strip()!r}")
            current = models.setdefault(m.group(1), ErdModel(m.group(1)))
            continue
        if current is None:
            raise ErdSyntaxError(f"line {n}: field outside a model")
        parts = line.split()
        if parts[0] in ("index", "unique"):
            cols = tuple(c.strip() for c in re.fullmatch(r"(?:index|unique)\s*\((.*)\)", line.strip()).group(1).split(","))
            (current.indexes if parts[0] == "index" else current.uniques).append(cols)
            continue
        if len(parts) < 2:
            raise ErdSyntaxError(f"line {n}: a field needs a name and a type")
        name, kind = parts[0], parts[1]
        f = ErdField(name, kind)
        length = re.fullmatch(r"char\((\d+)\)", kind)
        if length:
            f.kind, f.length = "char", int(length.group(1))
        rest = parts[2:]
        if f.kind in ("fk", "one2one"):
            if not rest:
                raise ErdSyntaxError(f"line {n}: {f.kind} needs a target model")
            f.target, rest = rest[0], rest[1:]
            if rest and rest[0] in ("cascade", "protect", "set_null", "set_default", "do_nothing"):
                f.on_delete, rest = rest[0], rest[1:]
        if f.kind not in DJANGO_FOR and f.kind != "char":
            raise ErdSyntaxError(f"line {n}: unknown type {f.kind!r}")
        for opt in rest:
            if opt not in ("unique", "index", "null"):
                raise ErdSyntaxError(f"line {n}: unknown option {opt!r}")
            setattr(f, opt, True)
        current.fields[name] = f
    return models


@dataclass
class DjangoField:
    cls: str
    kwargs: dict
    target: str | None = None
    on_delete: str | None = None


@dataclass
class DjangoModel:
    name: str
    fields: dict[str, DjangoField] = field(default_factory=dict)
    indexes: list[tuple[str, ...]] = field(default_factory=list)
    uniques: list[tuple[str, ...]] = field(default_factory=list)


def _const(node: ast.AST):
    return node.value if isinstance(node, ast.Constant) else None


def _target_name(node: ast.AST) -> str | None:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value.rsplit(".", 1)[-1]
    if isinstance(node, ast.Attribute):
        return "User" if node.attr == "AUTH_USER_MODEL" else node.attr
    if isinstance(node, ast.Name):
        return node.id
    return None


def _field_names(node: ast.AST) -> tuple[str, ...]:
    if isinstance(node, (ast.List, ast.Tuple)):
        return tuple(_const(e) for e in node.elts if isinstance(_const(e), str))
    return ()


def parse_django_models(source: str) -> dict[str, DjangoModel]:
    tree = ast.parse(source)
    models: dict[str, DjangoModel] = {}
    for cls in (n for n in tree.body if isinstance(n, ast.ClassDef)):
        dm = DjangoModel(cls.name)
        is_model = False
        for stmt in cls.body:
            if isinstance(stmt, ast.Assign) and isinstance(stmt.value, ast.Call) and isinstance(stmt.targets[0], ast.Name):
                func = stmt.value.func
                fname = func.attr if isinstance(func, ast.Attribute) else getattr(func, "id", "")
                if fname.endswith("Field") or fname in ("ForeignKey", "OneToOneField", "ManyToManyField"):
                    is_model = True
                    kwargs = {k.arg: _const(k.value) for k in stmt.value.keywords if k.arg}
                    df = DjangoField(fname, kwargs)
                    if fname in ("ForeignKey", "OneToOneField") and stmt.value.args:
                        df.target = _target_name(stmt.value.args[0])
                    for k in stmt.value.keywords:
                        if k.arg == "on_delete":
                            df.on_delete = (k.value.attr if isinstance(k.value, ast.Attribute) else getattr(k.value, "id", "")).lower()
                        if k.arg == "to":
                            df.target = _target_name(k.value)
                    dm.fields[stmt.targets[0].id] = df
            if isinstance(stmt, ast.ClassDef) and stmt.name == "Meta":
                for item in stmt.body:
                    if not (isinstance(item, ast.Assign) and isinstance(item.targets[0], ast.Name) and isinstance(item.value, (ast.List, ast.Tuple))):
                        continue
                    for entry in item.value.elts:
                        if not isinstance(entry, ast.Call):
                            continue
                        kind = entry.func.attr if isinstance(entry.func, ast.Attribute) else getattr(entry.func, "id", "")
                        fields_kw = next((k.value for k in entry.keywords if k.arg == "fields"), None)
                        cols = _field_names(fields_kw) if fields_kw is not None else ()
                        if kind == "Index" and cols:
                            dm.indexes.append(cols)
                        if kind == "UniqueConstraint" and cols:
                            dm.uniques.append(cols)
                    if item.targets[0].id == "unique_together":
                        pass
        if is_model:
            models[cls.name] = dm
    return models


def _norm_cols(cols) -> tuple[str, ...]:
    return tuple(c.strip() for c in cols)


def compare(erd: dict[str, ErdModel], django: dict[str, DjangoModel]) -> list[Difference]:
    out: list[Difference] = []
    for name, em in erd.items():
        dm = django.get(name)
        if dm is None:
            out.append(Difference("error", name, "model is in the ERD but not in models.py"))
            continue
        for fname, ef in em.fields.items():
            df = dm.fields.get(fname)
            if df is None:
                out.append(Difference("error", name, f"field {fname} is missing"))
                continue
            if df.cls not in DJANGO_FOR[ef.kind]:
                out.append(Difference("error", name, f"{fname}: ERD says {ef.kind}, model has {df.cls}"))
                continue
            if ef.kind == "char" and ef.length and df.kwargs.get("max_length") != ef.length:
                out.append(Difference("error", name, f"{fname}: max_length is {df.kwargs.get('max_length')}, ERD says {ef.length}"))
            if ef.kind in ("fk", "one2one"):
                if ef.target and df.target and ef.target != df.target:
                    out.append(Difference("error", name, f"{fname}: points at {df.target}, ERD says {ef.target}"))
                if ef.on_delete and df.on_delete != ef.on_delete:
                    out.append(Difference("error", name, f"{fname}: on_delete is {df.on_delete or 'missing'}, ERD says {ef.on_delete}"))
                if ef.kind == "one2one" and df.cls != "OneToOneField":
                    out.append(Difference("error", name, f"{fname}: should be a OneToOneField"))
            if ef.unique and not (df.kwargs.get("unique") or df.cls == "OneToOneField"):
                out.append(Difference("error", name, f"{fname}: ERD says unique but the model allows duplicates"))
            fk_indexed = ef.kind in ("fk", "one2one") and df.kwargs.get("db_index", True) is not False
            if ef.index and not (df.kwargs.get("db_index") or df.kwargs.get("unique") or fk_indexed or any(c and c[0] == fname for c in dm.indexes)):
                out.append(Difference("warn", name, f"{fname}: ERD says indexed but there is no index"))
            if bool(df.kwargs.get("null")) != ef.null:
                out.append(Difference("error" if not ef.null else "warn", name,
                                      f"{fname}: null={bool(df.kwargs.get('null'))} but the ERD says {'nullable' if ef.null else 'required'}"))
        for cols in em.indexes:
            if _norm_cols(cols) not in {_norm_cols(c) for c in dm.indexes}:
                out.append(Difference("warn", name, f"missing index on ({', '.join(cols)})"))
        for cols in em.uniques:
            if _norm_cols(cols) not in {_norm_cols(c) for c in dm.uniques}:
                out.append(Difference("error", name, f"missing unique constraint on ({', '.join(cols)})"))
        for extra in sorted(set(dm.fields) - set(em.fields) - {"id"}):
            out.append(Difference("info", name, f"field {extra} is in the model but not in the ERD"))
    for extra in sorted(set(django) - set(erd)):
        out.append(Difference("info", extra, "model is in models.py but not in the ERD"))
    return out


def main(argv: list[str] | None = None) -> int:
    args = argv or sys.argv[1:]
    if len(args) != 2:
        print("usage: python -m core.review.erd_check erd.txt models.py")
        return 2
    diffs = compare(parse_erd(Path(args[0]).read_text(encoding="utf-8")), parse_django_models(Path(args[1]).read_text(encoding="utf-8")))
    for d in diffs:
        print(d)
    errors = sum(1 for d in diffs if d.level == "error")
    print(f"\n{errors} error(s), {sum(1 for d in diffs if d.level == 'warn')} warning(s), {sum(1 for d in diffs if d.level == 'info')} note(s)")
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
