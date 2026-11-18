"""The chat use case, with no Django in it: validate, scope to the owner, deduplicate, call the provider, save."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Protocol

from .history import Message, trim_history


class ChatError(Exception):
    status = 400


class NotFound(ChatError):
    status = 404           # also used for "this belongs to someone else": never reveal that it exists


class Invalid(ChatError):
    status = 400


class ServiceUnavailable(ChatError):
    status = 503


class ProviderError(Exception):
    pass


class ProviderRejected(ProviderError):
    """The provider refused the request (bad input, content policy). Retrying will not help."""


class ProviderTimeout(ProviderError):
    """No answer in time. The caller may retry with the same idempotency key."""


class ChatProvider(Protocol):
    def complete(self, messages: list[dict], *, timeout: float) -> str: ...


@dataclass
class StoredMessage:
    id: int
    conversation_id: str
    role: str
    content: str
    status: str = "ok"                  # ok | pending | failed | blocked
    idempotency_key: str | None = None


class ChatRepo(Protocol):
    def get_conversation(self, user_id: str, public_id: str) -> str | None: ...
    def find_by_key(self, conversation_id: str, key: str) -> StoredMessage | None: ...
    def add(self, conversation_id: str, role: str, content: str, *, status: str = "ok", key: str | None = None) -> StoredMessage: ...
    def history(self, conversation_id: str) -> list[StoredMessage]: ...
    def reply_to(self, user_message_id: int) -> StoredMessage | None: ...
    def set_status(self, message_id: int, status: str) -> None: ...


@dataclass(frozen=True)
class SendResult:
    user_message: StoredMessage
    assistant_message: StoredMessage
    deduplicated: bool = False


@dataclass
class ChatService:
    repo: ChatRepo
    provider: ChatProvider
    max_context_tokens: int = 8000
    reserve_reply_tokens: int = 1000
    max_message_chars: int = 8000
    timeout_seconds: float = 30.0
    blocked_reply: str = "I can't help with that request."
    # hooks that Chapters 34 (privacy and safety) plug in; they default to doing nothing
    check_input: Callable[[str], bool] = lambda text: True            # False = blocked
    prepare: Callable[[list[dict]], tuple[list[dict], Callable[[str], str]]] = field(default=lambda msgs: (msgs, lambda t: t))

    def send(self, *, user_id: str, conversation_id: str, text: str, idempotency_key: str) -> SendResult:
        text = (text or "").strip()
        if not text:
            raise Invalid("message is empty")
        if len(text) > self.max_message_chars:
            raise Invalid(f"message is longer than {self.max_message_chars} characters")
        if not idempotency_key or len(idempotency_key) > 80:
            raise Invalid("an Idempotency-Key of 1 to 80 characters is required")

        conv = self.repo.get_conversation(user_id, conversation_id)
        if conv is None:
            raise NotFound("conversation not found")

        existing = self.repo.find_by_key(conv, idempotency_key)
        if existing is not None:                                   # a retry or a double click: return what we already have
            reply = self.repo.reply_to(existing.id)
            if reply is not None and existing.status in ("ok", "blocked"):
                return SendResult(existing, reply, deduplicated=True)
            if existing.status == "failed":
                self.repo.set_status(existing.id, "pending")       # a retry after a failure runs again
                user_message = existing
            else:
                raise ServiceUnavailable("this message is still being processed")
        else:
            user_message = self.repo.add(conv, "user", text, status="pending", key=idempotency_key)   # save BEFORE calling anyone

        if not self.check_input(text):
            self.repo.set_status(user_message.id, "blocked")
            reply = self.repo.add(conv, "assistant", self.blocked_reply, status="blocked")
            return SendResult(user_message, reply)

        history = [Message(m.role, m.content) for m in self.repo.history(conv) if m.status in ("ok", "pending") and m.id != user_message.id]
        history.append(Message("user", text))
        kept, _dropped = trim_history(history, max_tokens=self.max_context_tokens, reserve_reply=self.reserve_reply_tokens)
        payload, restore = self.prepare([{"role": m.role, "content": m.content} for m in kept])
        try:
            answer = self.provider.complete(payload, timeout=self.timeout_seconds)
        except ProviderTimeout as exc:
            self.repo.set_status(user_message.id, "failed")
            raise ServiceUnavailable("the AI provider did not answer in time; retry with the same Idempotency-Key") from exc
        except ProviderRejected as exc:
            self.repo.set_status(user_message.id, "blocked")
            raise Invalid("the request was refused by the AI provider") from exc
        self.repo.set_status(user_message.id, "ok")
        reply = self.repo.add(conv, "assistant", restore(answer), status="ok")
        return SendResult(self.repo.find_by_key(conv, idempotency_key) or user_message, reply)
