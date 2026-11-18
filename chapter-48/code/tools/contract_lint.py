"""Lint an OpenAPI 3 contract (JSON) against the house rules of this book.

Usage:  python -m tools.contract_lint contracts/openapi.json

Rules:
  C1  every operation has an operationId (generated clients use it as the function name)
  C2  operationIds are unique and camelCase
  C3  every operation has at least one tag and a summary
  C4  every operation either declares security or is explicitly public (security: [])
  C5  every operation documents at least one error response (4xx) or a default
  C6  path parameters in the URL are declared on the operation
  C7  no response schema is an untyped object (it would become `any` in TypeScript)
"""
from __future__ import annotations

import re
import sys

from .openapi_util import json_schema_of, load, operations, resolve

CAMEL = re.compile(r"^[a-z][A-Za-z0-9]*$")
PATH_PARAM = re.compile(r"{([^}]+)}")


def lint(doc: dict) -> list[str]:
    problems: list[str] = []
    seen_ids: dict[str, str] = {}
    default_security = doc.get("security")
    for path, method, op in operations(doc):
        where = f"{method.upper()} {path}"
        op_id = op.get("operationId")
        if not op_id:
            problems.append(f"C1 {where}: missing operationId")
        else:
            if not CAMEL.match(op_id):
                problems.append(f"C2 {where}: operationId '{op_id}' is not camelCase")
            if op_id in seen_ids:
                problems.append(f"C2 {where}: operationId '{op_id}' also used by {seen_ids[op_id]}")
            seen_ids[op_id] = where
        if not op.get("tags") or not op.get("summary"):
            problems.append(f"C3 {where}: needs tags and a summary")
        if "security" not in op and not default_security:
            problems.append(f"C4 {where}: no security declared (use security: [] for a public endpoint)")
        responses = op.get("responses", {})
        if not any(code.startswith("4") or code == "default" for code in responses):
            problems.append(f"C5 {where}: no error response documented")
        declared = {resolve(doc, p).get("name") for p in op.get("parameters", [])}
        declared |= {resolve(doc, p).get("name") for p in doc["paths"][path].get("parameters", [])}
        for name in PATH_PARAM.findall(path):
            if name not in declared:
                problems.append(f"C6 {where}: path parameter '{name}' is not declared")
        for code, response in responses.items():
            if not code.startswith("2"):
                continue
            schema = json_schema_of(doc, response)
            if schema and schema.get("type") == "object" and not schema.get("properties") \
                    and "allOf" not in schema and "oneOf" not in schema:
                problems.append(f"C7 {where}: {code} response is an untyped object")
    return problems


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print(__doc__)
        return 2
    problems = lint(load(argv[1]))
    if problems:
        print(f"{argv[1]}: {len(problems)} problem(s)")
        for p in problems:
            print("  -", p)
        return 1
    print(f"{argv[1]}: contract looks good")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
