"""The Django implementation of ConversationStore. Plain sync ORM code wrapped for async callers."""
from __future__ import annotations

from asgiref.sync import sync_to_async
from django.db import transaction

from chat.models import Conversation, Message

from .dto import ChatMessage
from .models import UsageRecord
from .service import ConversationNotFound, History, Turn, TurnResult

USABLE = ("complete", "truncated", "interrupted")   # statuses whose text is worth sending back to the model


class DjangoConversationStore:
    async def get_history(self, *, user_id, conversation_id):
        return await sync_to_async(self._get_history)(user_id, conversation_id)

    async def begin_turn(self, *, user_id, conversation_id, user_text):
        return await sync_to_async(self._begin_turn)(user_id, conversation_id, user_text)

    async def finish_turn(self, *, user_id, conversation_id, turn, result):
        await sync_to_async(self._finish_turn)(user_id, conversation_id, turn, result)

    async def schedule_summary(self, *, user_id, conversation_id):
        from .tasks import refresh_summary
        await sync_to_async(refresh_summary.delay)(conversation_id)

    # ---- sync internals ---------------------------------------------------------
    def _owned(self, user_id, conversation_id) -> Conversation:
        try:
            return Conversation.objects.get(pk=conversation_id, user_id=user_id)   # owner in the query, Chapter 17
        except Conversation.DoesNotExist:
            raise ConversationNotFound() from None

    def _get_history(self, user_id, conversation_id) -> History:
        conv = self._owned(user_id, conversation_id)
        rows = conv.messages.filter(status__in=USABLE).order_by("created_at", "id").values_list("role", "content")
        return History(tuple(ChatMessage(role, content) for role, content in rows), conv.summary or None)

    def _begin_turn(self, user_id, conversation_id, user_text) -> Turn:
        conv = self._owned(user_id, conversation_id)
        with transaction.atomic():
            user_msg = Message.objects.create(conversation=conv, role="user", content=user_text, status="complete")
            bot_msg = Message.objects.create(conversation=conv, role="assistant", content="", status="streaming")
        return Turn(user_msg.pk, bot_msg.pk)

    def _finish_turn(self, user_id, conversation_id, turn: Turn, result: TurnResult) -> None:
        with transaction.atomic():      # the answer and its ledger row are saved together, or not at all
            Message.objects.filter(pk=turn.assistant_message_id, conversation_id=conversation_id).update(
                content=result.text, status=result.status, stop_reason=result.stop_reason, model=result.model)
            UsageRecord.objects.create(
                user_id=user_id, conversation_id=conversation_id, message_id=turn.assistant_message_id,
                model=result.model, prompt_version=result.prompt_version, status=result.status,
                input_tokens=result.usage.input_tokens, output_tokens=result.usage.output_tokens,
                cache_write_tokens=result.usage.cache_write_tokens, cache_read_tokens=result.usage.cache_read_tokens,
                usage_estimated=result.usage_estimated, cost_micro_usd=result.cost_micro_usd,
                request_id=result.request_id or "")
