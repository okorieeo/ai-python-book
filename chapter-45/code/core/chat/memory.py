"""An in-memory repository and fake providers for tests and exercises."""
from __future__ import annotations

from .service import ProviderRejected, ProviderTimeout, StoredMessage


class MemoryRepo:
    def __init__(self):
        self.owners: dict[str, str] = {}              # conversation public id -> owner user id
        self.messages: list[StoredMessage] = []
        self.replies: dict[int, int] = {}              # user message id -> assistant message id
        self._next = 1
        self._last_user: int | None = None

    def create_conversation(self, user_id: str, public_id: str) -> str:
        self.owners[public_id] = user_id
        return public_id

    def get_conversation(self, user_id: str, public_id: str):
        return public_id if self.owners.get(public_id) == user_id else None      # scoped to the owner

    def find_by_key(self, conversation_id: str, key: str):
        return next((m for m in self.messages if m.conversation_id == conversation_id and m.idempotency_key == key), None)

    def add(self, conversation_id, role, content, *, status="ok", key=None):
        m = StoredMessage(self._next, conversation_id, role, content, status, key)
        self._next += 1
        self.messages.append(m)
        if role == "user":
            self._last_user = m.id
        elif self._last_user is not None:
            self.replies[self._last_user] = m.id
        return m

    def history(self, conversation_id):
        return [m for m in self.messages if m.conversation_id == conversation_id]

    def reply_to(self, user_message_id):
        rid = self.replies.get(user_message_id)
        return next((m for m in self.messages if m.id == rid), None)

    def set_status(self, message_id, status):
        next(m for m in self.messages if m.id == message_id).status = status


class EchoProvider:
    def __init__(self):
        self.calls: list[list[dict]] = []

    def complete(self, messages, *, timeout):
        self.calls.append(messages)
        return "echo: " + messages[-1]["content"]


class FlakyProvider(EchoProvider):
    def __init__(self, fail_times=1, error=ProviderTimeout):
        super().__init__()
        self.fail_times, self.error = fail_times, error

    def complete(self, messages, *, timeout):
        if self.fail_times > 0:
            self.fail_times -= 1
            self.calls.append(messages)
            raise self.error("fake failure")
        return super().complete(messages, timeout=timeout)


class RefusingProvider(EchoProvider):
    def complete(self, messages, *, timeout):
        raise ProviderRejected("policy")
