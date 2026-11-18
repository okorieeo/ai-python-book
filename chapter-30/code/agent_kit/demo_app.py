"""A tiny in-memory stand-in for the AI Chat SaaS, with five tools on top of it.

In your real project the ChatStore is your service layer over the Django models
from Chapters 11 and 12. The rule that matters is already here: every method
takes the user id, and a user can only ever see or change their own rows.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from .policy import Policy
from .tools import Tool, ToolContext, ToolError, ToolRegistry


@dataclass
class Conversation:
    id: int
    owner_id: int
    title: str
    messages: list[str] = field(default_factory=list)


class ChatStore:
    def __init__(self) -> None:
        self._rows: dict[int, Conversation] = {}
        self._next = 1

    def add(self, owner_id: int, title: str, messages: Optional[list[str]] = None) -> Conversation:
        row = Conversation(self._next, owner_id, title, list(messages or []))
        self._rows[row.id] = row
        self._next += 1
        return row

    def get_for(self, user_id: int, conversation_id: int) -> Conversation:
        row = self._rows.get(conversation_id)
        if row is None or row.owner_id != user_id:
            # Same message whether it does not exist or belongs to someone else (Chapter 17).
            raise ToolError(f"Conversation {conversation_id} was not found.")
        return row

    def list_for(self, user_id: int, limit: int) -> list[Conversation]:
        return [r for r in self._rows.values() if r.owner_id == user_id][:limit]

    def delete_for(self, user_id: int, conversation_id: int) -> None:
        self.get_for(user_id, conversation_id)
        del self._rows[conversation_id]

    def exists(self, conversation_id: int) -> bool:
        return conversation_id in self._rows


def _list(args: dict, ctx: ToolContext):
    rows = ctx.services.list_for(ctx.user_id, args.get("limit", 10))
    return [{"id": r.id, "title": r.title, "messages": len(r.messages)} for r in rows]


def _search(args: dict, ctx: ToolContext):
    q = args["query"].lower()
    hits = []
    for row in ctx.services.list_for(ctx.user_id, 1000):
        for text in row.messages:
            if q in text.lower():
                hits.append({"conversation_id": row.id, "title": row.title, "snippet": text[:120]})
    return hits[: args.get("limit", 5)]


def _rename(args: dict, ctx: ToolContext):
    row = ctx.services.get_for(ctx.user_id, args["conversation_id"])
    row.title = args["new_title"]
    return f"Conversation {row.id} is now titled {row.title!r}."


def _delete(args: dict, ctx: ToolContext):
    ctx.services.delete_for(ctx.user_id, args["conversation_id"])
    return f"Conversation {args['conversation_id']} was deleted."


def _usage(args: dict, ctx: ToolContext):
    return {"messages_this_month": 120, "plan": "free", "note": "demo numbers"}


def build_registry() -> ToolRegistry:
    no_args = {"type": "object", "properties": {}, "additionalProperties": False}
    return ToolRegistry(
        [
            Tool(
                name="list_conversations",
                description=(
                    "Lists the current user's most recent conversations with their ids, titles and "
                    "message counts. Use it to find a conversation id before renaming or deleting "
                    "one. It never returns message text; use search_messages for that."
                ),
                input_schema={
                    "type": "object",
                    "properties": {
                        "limit": {"type": "integer", "minimum": 1, "maximum": 50,
                                  "description": "How many conversations to return. Default 10."}
                    },
                    "additionalProperties": False,
                },
                handler=_list,
                risk="read",
            ),
            Tool(
                name="search_messages",
                description=(
                    "Searches the text of the current user's own messages for a word or phrase and "
                    "returns matching snippets with the conversation id and title. Use it when the "
                    "user asks which chat mentioned something. It only searches this user's data."
                ),
                input_schema={
                    "type": "object",
                    "properties": {
                        "query": {"type": "string", "minLength": 2, "maxLength": 200,
                                  "description": "The word or phrase to look for."},
                        "limit": {"type": "integer", "minimum": 1, "maximum": 20,
                                  "description": "Maximum matches to return. Default 5."},
                    },
                    "required": ["query"],
                    "additionalProperties": False,
                },
                handler=_search,
                risk="read",
            ),
            Tool(
                name="rename_conversation",
                description=(
                    "Changes the title of one of the current user's conversations. Use it only when "
                    "the user clearly asks for a rename, and get the conversation id from "
                    "list_conversations first. The change is easy to undo, so it does not need approval."
                ),
                input_schema={
                    "type": "object",
                    "properties": {
                        "conversation_id": {"type": "integer", "description": "The conversation's id."},
                        "new_title": {"type": "string", "minLength": 1, "maxLength": 80,
                                      "description": "The new title, 80 characters at most."},
                    },
                    "required": ["conversation_id", "new_title"],
                    "additionalProperties": False,
                },
                handler=_rename,
                risk="write",
            ),
            Tool(
                name="delete_conversation",
                description=(
                    "Permanently deletes one of the current user's conversations and all its "
                    "messages. This cannot be undone, so the user is asked to confirm before it "
                    "runs. Use it only when the user explicitly asks to delete a specific conversation."
                ),
                input_schema={
                    "type": "object",
                    "properties": {
                        "conversation_id": {"type": "integer", "description": "The conversation's id."}
                    },
                    "required": ["conversation_id"],
                    "additionalProperties": False,
                },
                handler=_delete,
                risk="destructive",
            ),
            Tool(
                name="get_usage_summary",
                description=(
                    "Returns the current user's message count and plan for this month. Use it when "
                    "the user asks how much they have used or what plan they are on. It takes no "
                    "arguments and does not change anything."
                ),
                input_schema=no_args,
                handler=_usage,
                risk="read",
            ),
        ]
    )


# Role-based policy: viewers can look but not change anything (Chapter 13 roles).
READ_ONLY_TOOLS = frozenset({"list_conversations", "search_messages", "get_usage_summary"})


def policy_for_role(role: str) -> Policy:
    if role == "viewer":
        return Policy(allowed_tools=READ_ONLY_TOOLS)
    return Policy()  # members get every tool, destructive ones still need approval
