"""Command line.   python -m ai_verify --help"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import bugreport, hallucination, mutation, packages, smells


def cmd_imports(args) -> int:
    hallucination.prepare_environment(args.root, args.django_settings)
    findings = hallucination.check_source(Path(args.file).read_text(encoding="utf-8"))
    for f in findings:
        print(f)
    errors = [f for f in findings if f.severity == "error"]
    print(f"\n{len(errors)} error(s), {len(findings) - len(errors)} warning(s) in {args.file}")
    return 1 if errors else 0


def cmd_smells(args) -> int:
    targets = None
    if args.target:
        import ast
        tree = ast.parse(Path(args.target).read_text(encoding="utf-8"))
        targets = {n.name for n in tree.body if isinstance(n, ast.FunctionDef) and not n.name.startswith("_")}
    found = smells.analyze_tests(Path(args.file).read_text(encoding="utf-8"), target_names=targets)
    for s in found:
        print(s)
    print(f"\n{len(found)} smell(s) in {args.file}")
    return 1 if found else 0


def cmd_mutate(args) -> int:
    try:
        report = mutation.run_mutation(args.project, args.module, args.cmd, timeout=args.timeout, max_mutants=args.max)
    except mutation.BaselineFailed as exc:
        print(exc, file=sys.stderr)
        return 2
    print(mutation.format_report(report))
    return 0 if report.score >= args.min_score else 1


def cmd_bugreport(args) -> int:
    tb = Path(args.traceback).read_text(encoding="utf-8") if args.traceback else ""
    code = Path(args.code).read_text(encoding="utf-8") if args.code else ""
    print(bugreport.build_bug_report(
        title=args.title, expected=args.expected, actual=args.actual, steps=args.steps or "", traceback=tb,
        code=code, tried=args.tried or "", constraints=args.constraints or "", packages=tuple(args.package or ())))
    return 0


def cmd_package(args) -> int:
    for name in args.names:
        print(packages.format_package(packages.check_package(name)))
    return 0


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="ai_verify", description=__doc__)
    sub = p.add_subparsers(dest="cmd", required=True)
    a = sub.add_parser("imports", help="do the imports, attributes and keywords in this file exist?")
    a.add_argument("file")
    a.add_argument("--root", default=".", help="your project root, so your own imports resolve (default: here)")
    a.add_argument("--django-settings", help="e.g. config.settings, so Django modules can be imported")
    a.set_defaults(fn=cmd_imports)
    s = sub.add_parser("smells", help="find weak tests")
    s.add_argument("file"); s.add_argument("--target", help="the module the tests are for"); s.set_defaults(fn=cmd_smells)
    m = sub.add_parser("mutate", help="break the code on purpose and see whether tests notice")
    m.add_argument("--project", required=True); m.add_argument("--module", required=True, help="path inside the project")
    m.add_argument("--cmd", help="test command (default: python -m pytest -x -q)")
    m.add_argument("--timeout", type=float, default=60); m.add_argument("--max", type=int)
    m.add_argument("--min-score", type=float, default=0.0); m.set_defaults(fn=cmd_mutate)
    b = sub.add_parser("bugreport", help="build a redacted report to paste into an assistant")
    b.add_argument("--title", required=True); b.add_argument("--expected", required=True); b.add_argument("--actual", required=True)
    b.add_argument("--steps"); b.add_argument("--traceback"); b.add_argument("--code"); b.add_argument("--tried")
    b.add_argument("--constraints"); b.add_argument("--package", action="append"); b.set_defaults(fn=cmd_bugreport)
    k = sub.add_parser("package", help="check package names on PyPI")
    k.add_argument("names", nargs="+"); k.set_defaults(fn=cmd_package)
    args = p.parse_args(argv)
    return args.fn(args)


if __name__ == "__main__":
    raise SystemExit(main())
