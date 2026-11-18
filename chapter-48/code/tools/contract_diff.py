"""Compare two versions of an OpenAPI 3 contract (JSON) and classify every change.

Usage:  python -m tools.contract_diff old.json new.json [--strict]
Exit code 1 when a BREAKING change is found, so CI can block the merge.
With --strict, ANY difference fails (use it to prove the committed contract equals the
contract generated from the code).

BREAKING (old web or mobile clients can fail):
  - an endpoint (path + method) was removed
  - a response property was removed, or its type changed
  - a response enum lost a value or gained one (clients with exhaustive switches break) -> WARNING
  - a request property became required, or a new required request property / parameter appeared
  - a request property changed type
SAFE (additive):
  - new endpoint, new optional request property, new response property
"""
from __future__ import annotations

import sys
from dataclasses import dataclass

from .openapi_util import json_schema_of, load, operations, resolve


@dataclass(frozen=True)
class Change:
    level: str      # BREAKING, WARNING or SAFE
    where: str
    what: str

    def __str__(self) -> str:
        return f"{self.level:<8} {self.where}: {self.what}"


def _props(doc: dict, schema: dict) -> dict[str, dict]:
    schema = resolve(doc, schema)
    if schema.get("type") == "array":
        schema = resolve(doc, schema.get("items", {}))
    return {name: resolve(doc, s) for name, s in schema.get("properties", {}).items()}


def _required(doc: dict, schema: dict) -> set[str]:
    schema = resolve(doc, schema)
    if schema.get("type") == "array":
        schema = resolve(doc, schema.get("items", {}))
    return set(schema.get("required", []))


def _compare_props(old_doc, new_doc, old_schema, new_schema, where, *, is_request, out: list[Change]):
    old_p, new_p = _props(old_doc, old_schema), _props(new_doc, new_schema)
    old_req, new_req = _required(old_doc, old_schema), _required(new_doc, new_schema)
    for name, old in old_p.items():
        if name not in new_p:
            if not is_request:
                out.append(Change("BREAKING", where, f"response property '{name}' was removed"))
            else:
                out.append(Change("SAFE", where, f"request property '{name}' is no longer accepted"))
            continue
        new = new_p[name]
        if old.get("type") != new.get("type"):
            out.append(Change("BREAKING", where, f"property '{name}' changed type {old.get('type')} -> {new.get('type')}"))
        if "enum" in old and "enum" in new and set(old["enum"]) != set(new["enum"]):
            removed, added = set(old["enum"]) - set(new["enum"]), set(new["enum"]) - set(old["enum"])
            if is_request and removed:
                out.append(Change("BREAKING", where, f"'{name}' no longer accepts {sorted(removed)}"))
            elif not is_request:
                out.append(Change("WARNING", where, f"'{name}' enum changed (removed {sorted(removed)}, added {sorted(added)})"))
    for name in new_p.keys() - old_p.keys():
        if is_request and name in new_req:
            out.append(Change("BREAKING", where, f"new REQUIRED request property '{name}'"))
        else:
            kind = "request" if is_request else "response"
            out.append(Change("SAFE", where, f"new {kind} property '{name}'"))
    if is_request:
        for name in (new_req - old_req) & old_p.keys():
            out.append(Change("BREAKING", where, f"request property '{name}' became required"))


def diff(old: dict, new: dict) -> list[Change]:
    out: list[Change] = []
    old_ops = {(p, m): op for p, m, op in operations(old)}
    new_ops = {(p, m): op for p, m, op in operations(new)}
    for key in old_ops.keys() - new_ops.keys():
        out.append(Change("BREAKING", f"{key[1].upper()} {key[0]}", "endpoint was removed"))
    for key in new_ops.keys() - old_ops.keys():
        out.append(Change("SAFE", f"{key[1].upper()} {key[0]}", "new endpoint"))
    for key in sorted(old_ops.keys() & new_ops.keys()):
        where = f"{key[1].upper()} {key[0]}"
        o, n = old_ops[key], new_ops[key]
        _compare_props(old, new, json_schema_of(old, o.get("requestBody")), json_schema_of(new, n.get("requestBody")),
                       where + " request", is_request=True, out=out)
        for code, resp in o.get("responses", {}).items():
            if not code.startswith("2"):
                continue
            if code not in n.get("responses", {}):
                out.append(Change("BREAKING", where, f"success response {code} was removed"))
                continue
            _compare_props(old, new, json_schema_of(old, resp), json_schema_of(new, n["responses"][code]),
                           f"{where} {code}", is_request=False, out=out)
        old_params = {(resolve(old, p).get("name"), resolve(old, p).get("in")) for p in o.get("parameters", [])}
        for p in n.get("parameters", []):
            p = resolve(new, p)
            if p.get("required") and (p.get("name"), p.get("in")) not in old_params:
                out.append(Change("BREAKING", where, f"new required {p.get('in')} parameter '{p.get('name')}'"))
    order = {"BREAKING": 0, "WARNING": 1, "SAFE": 2}
    return sorted(out, key=lambda c: (order[c.level], c.where, c.what))


def main(argv: list[str]) -> int:
    strict = "--strict" in argv
    argv = [a for a in argv if a != "--strict"]
    if len(argv) != 3:
        print(__doc__)
        return 2
    changes = diff(load(argv[1]), load(argv[2]))
    if not changes:
        print("no contract changes")
        return 0
    for c in changes:
        print(c)
    breaking = sum(c.level == "BREAKING" for c in changes)
    print(f"\n{breaking} breaking, {sum(c.level == 'WARNING' for c in changes)} warning, "
          f"{sum(c.level == 'SAFE' for c in changes)} safe")
    return 1 if breaking or (strict and changes) else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
