"""A living data map. A test fails when personal data has no owner, rule or eraser."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class DataItem:
    key: str                  # "app.Model.field"
    category: str             # identity | content | usage | payment | technical
    purpose: str
    lawful_basis: str         # contract | consent | legitimate_interest | legal_obligation
    sent_to_ai_provider: bool
    retention: str | None     # key into retention.RULES, or None for "until deleted"
    eraser: str | None        # name registered in the EraserRegistry
    sensitive: bool = False   # users may type health, money or other sensitive facts here


INVENTORY: tuple[DataItem, ...] = (
    DataItem("users.User.email", "identity", "Log in, send receipts", "contract", False, None, "account"),
    DataItem("users.User.display_name", "identity", "Show the user's name", "contract", False, None, "account"),
    DataItem("chat.Message.content", "content", "Provide the chat service", "contract", True, None,
             "conversations", sensitive=True),
    DataItem("chat.Conversation.title", "content", "Show history", "contract", True, None, "conversations"),
    DataItem("privacy.ConsentEvent", "usage", "Prove consent choices", "legal_obligation", False,
             "deletion_requests", "consents"),
    DataItem("billing.Payment", "payment", "Receipts, accounting", "legal_obligation", False, "invoices",
             "billing_anonymize"),
    DataItem("audit.AuditEvent", "technical", "Security accountability (ids only)", "legitimate_interest",
             False, "audit_events", None),
    DataItem("chat.AIRequestLog", "technical", "Cost tracking and debugging (counts only)",
             "legitimate_interest", False, "ai_request_logs", "ai_logs"),
    DataItem("chat.FlaggedMessage", "content", "Safety review", "legitimate_interest", False,
             "flagged_for_review", "flagged", sensitive=True),
    DataItem("rag.DocumentChunk.embedding", "content", "Answer questions about the user's files",
             "contract", True, None, "vectors", sensitive=True),
)


def validate_inventory(inventory, *, registered_erasers: set[str], retention_rules: set[str]) -> list[str]:
    """Return a list of problems. An empty list means the map is consistent."""
    problems, seen = [], set()
    for item in inventory:
        if item.key in seen:
            problems.append(f"{item.key}: listed twice")
        seen.add(item.key)
        if item.retention is not None and item.retention not in retention_rules:
            problems.append(f"{item.key}: unknown retention rule {item.retention!r}")
        if item.eraser is None and item.retention is None:
            problems.append(f"{item.key}: no eraser and no retention rule, so it would live forever")
        if item.eraser is not None and item.eraser not in registered_erasers:
            problems.append(f"{item.key}: eraser {item.eraser!r} is not registered")
        if item.sent_to_ai_provider and item.lawful_basis not in ("contract", "consent"):
            problems.append(f"{item.key}: sent to the AI provider without contract or consent as the basis")
        if not item.purpose.strip():
            problems.append(f"{item.key}: no purpose written down")
    return problems
