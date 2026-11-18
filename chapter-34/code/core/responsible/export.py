"""Build the 'download my data' package from an allow-list, never from model internals."""
from __future__ import annotations

import io
import json
import zipfile
from datetime import datetime

SCHEMA_VERSION = 1
USER_FIELDS = ("public_id", "email", "display_name", "date_joined", "role")
CONSENT_FIELDS = ("purpose", "granted", "document_version", "created_at")
CONVERSATION_FIELDS = ("public_id", "title", "created_at")
MESSAGE_FIELDS = ("role", "content", "created_at", "model", "ai_generated")
BILLING_FIELDS = ("provider", "amount", "currency", "status", "created_at")


def _pick(row: dict, allowed: tuple[str, ...]) -> dict:
    return {key: row[key] for key in allowed if key in row}


def build_export(*, user: dict, consents: list[dict], conversations: list[dict],
                 billing: list[dict], generated_at: datetime) -> dict:
    """Only allow-listed fields leave. A new column (or a password hash) is never exported by accident."""
    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at": generated_at.isoformat(),
        "account": _pick(user, USER_FIELDS),
        "consents": [_pick(c, CONSENT_FIELDS) for c in consents],
        "conversations": [
            {**_pick(c, CONVERSATION_FIELDS),
             "messages": [_pick(m, MESSAGE_FIELDS) for m in c.get("messages", [])]}
            for c in conversations
        ],
        "billing": [_pick(b, BILLING_FIELDS) for b in billing],
    }


def to_json_bytes(export: dict) -> bytes:
    return json.dumps(export, indent=2, ensure_ascii=False, default=str).encode("utf-8")


_README = (
    "This archive is a copy of the personal data we hold about your account.\n"
    "data.json holds everything in a machine-readable format (you may give it to another service).\n"
    "conversations/ holds each conversation as a readable text file.\n"
)


def _conversation_text(conv: dict) -> str:
    lines = [f"# {conv.get('title') or 'Untitled'}", ""]
    for m in conv.get("messages", []):
        label = "AI" if m.get("role") == "assistant" else "You"
        lines += [f"{label} ({m.get('created_at', '')}):", str(m.get("content", "")), ""]
    return "\n".join(lines)


def to_zip_bytes(export: dict) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("README.txt", _README)
        archive.writestr("data.json", to_json_bytes(export))
        for conv in export["conversations"]:
            safe_id = "".join(ch for ch in str(conv.get("public_id", "x")) if ch.isalnum() or ch == "-")
            archive.writestr(f"conversations/{safe_id}.txt", _conversation_text(conv))
    return buffer.getvalue()
