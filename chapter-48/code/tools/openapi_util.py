"""Tiny helpers for reading an OpenAPI 3 document (JSON) with only the standard library."""
from __future__ import annotations

import json
from pathlib import Path

METHODS = ("get", "post", "put", "patch", "delete")


def load(path: str | Path) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def resolve(doc: dict, node: dict, _seen: frozenset = frozenset()) -> dict:
    """Follow a local $ref such as '#/components/schemas/ShareLink'."""
    while isinstance(node, dict) and "$ref" in node:
        ref = node["$ref"]
        if ref in _seen:
            return {}
        _seen = _seen | {ref}
        target = doc
        for part in ref.lstrip("#/").split("/"):
            target = target[part]
        node = target
    return node


def operations(doc: dict):
    """Yield (path, method, operation) for every operation in the document."""
    for path, item in doc.get("paths", {}).items():
        for method in METHODS:
            if method in item:
                yield path, method, item[method]


def json_schema_of(doc: dict, container: dict | None) -> dict:
    """The JSON schema of a requestBody or response object, with $refs resolved one level."""
    if not container:
        return {}
    container = resolve(doc, container)
    schema = container.get("content", {}).get("application/json", {}).get("schema", {})
    return resolve(doc, schema)
