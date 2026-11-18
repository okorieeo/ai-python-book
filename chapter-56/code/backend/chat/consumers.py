"""The streaming chat WebSocket (Chapter 14's consumer, Chapter 29's service layer, Chapter 56's glue).

Protocol (JSON text frames)
  client -> server   chat.send {conversation_id|null, content, client_id?}   chat.stop   ping
  server -> client   ready  chat.started  chat.delta  chat.done  chat.error  plan.updated  pong
"""
import asyncio
import json
import logging
from urllib.parse import parse_qs

from asgiref.sync import sync_to_async
from channels.generic.websocket import AsyncJsonWebsocketConsumer
from django.conf import settings
from django.contrib.auth import get_user_model

from accounts.views import redeem_ticket
from ai.memory import build_context
from ai.providers import Delta, Done, ProviderError, get_provider
from billing.entitlements import current_plan
from billing.notify import plan_payload, user_group

from . import services, usage
from .models import Message

logger = logging.getLogger(__name__)
User = get_user_model()
UNAUTHORIZED = 4401


class ChatConsumer(AsyncJsonWebsocketConsumer):
    task: asyncio.Task | None = None
    user = None

    # ---- connection lifecycle ------------------------------------------------------------------
    async def connect(self):
        ticket = (parse_qs(self.scope.get("query_string", b"").decode()).get("ticket") or [""])[0]
        user_id = await sync_to_async(redeem_ticket)(ticket)
        await self.accept()  # accept first, then close with a code the browser can actually read
        user = await User.objects.filter(pk=user_id, is_active=True).afirst() if user_id else None
        if user is None:
            await self.close(code=UNAUTHORIZED)
            return
        self.user = user
        self.provider = get_provider()
        self.group = user_group(user.pk)
        await self.channel_layer.group_add(self.group, self.channel_name)
        await self.send_json({"type": "ready", **(await self._snapshot())})

    async def disconnect(self, code):
        if self.task and not self.task.done():
            self.task.cancel()  # _generate saves whatever text was produced before we return
            await asyncio.gather(self.task, return_exceptions=True)
        if self.user is not None:
            await self.channel_layer.group_discard(self.group, self.channel_name)

    # ---- incoming frames ---------------------------------------------------------------------
    async def receive(self, text_data=None, bytes_data=None, **kwargs):
        if self.user is None:
            return
        try:
            content = json.loads(text_data or "")
        except ValueError:
            return await self._error("invalid_message", "Messages must be valid JSON.")
        if not isinstance(content, dict):
            return await self._error("invalid_message", "Messages must be JSON objects.")
        kind = content.get("type")
        if kind == "chat.send":
            await self._on_send(content)
        elif kind == "chat.stop":
            if self.task and not self.task.done():
                self.task.cancel()
        elif kind == "ping":
            await self.send_json({"type": "pong"})
        else:
            await self._error("invalid_message", "Unknown message type.")

    async def _on_send(self, content: dict):
        client_id = str(content.get("client_id") or "")[:64]
        if self.task and not self.task.done():
            return await self._error("busy", "Wait for the current answer to finish, or press Stop.", client_id)
        plan = await sync_to_async(current_plan)(self.user)
        try:
            turn = await sync_to_async(services.start_turn)(
                user=self.user, conversation_public_id=content.get("conversation_id"),
                content=content.get("content"), daily_limit=plan.daily_message_limit)
        except services.ChatError as exc:
            return await self._error(exc.code, exc.message, client_id)
        await self.send_json({
            "type": "chat.started", "client_id": client_id,
            "conversation_id": str(turn.conversation.public_id), "title": turn.conversation.title,
            "user_message_id": turn.user_message.pk, "assistant_message_id": turn.assistant_message.pk})
        self.task = asyncio.create_task(self._generate(turn))  # return now so a Stop frame can be read

    # ---- generation ------------------------------------------------------------------------------
    async def _generate(self, turn: services.Turn):
        message_id = turn.assistant_message.pk
        parts: list[str] = []
        usage_info: Done | None = None
        status, error = Message.Status.COMPLETE, None
        try:
            context = await sync_to_async(build_context)(turn.conversation)
            async for event in self.provider.stream(system=context.system, messages=context.messages,
                                                    max_tokens=settings.AI_MAX_OUTPUT_TOKENS):
                if isinstance(event, Delta):
                    parts.append(event.text)
                    await self.send_json({"type": "chat.delta", "assistant_message_id": message_id,
                                          "text": event.text})
                elif isinstance(event, Done):
                    usage_info = event
        except asyncio.CancelledError:  # Stop button, or the browser went away
            status = Message.Status.STOPPED
        except ProviderError as exc:
            status, error = Message.Status.ERROR, str(exc)
        except Exception:  # never leave the user staring at a spinner
            logger.exception("unexpected failure while generating")
            status, error = Message.Status.ERROR, "Something went wrong on our side."

        text = "".join(parts)
        if status == Message.Status.ERROR and not text:
            await sync_to_async(services.fail_turn)(turn)
        else:
            await sync_to_async(services.finish_turn)(
                turn, text=text, status=status,
                input_tokens=usage_info.input_tokens if usage_info else 0,
                output_tokens=usage_info.output_tokens if usage_info else 0)

        if status == Message.Status.ERROR:
            await self._safe_send({"type": "chat.error", "code": "provider_error", "message": error,
                                   "assistant_message_id": message_id})
        else:
            plan = await sync_to_async(current_plan)(self.user)
            quota = await sync_to_async(usage.get_quota)(self.user, plan.daily_message_limit)
            await self._safe_send({
                "type": "chat.done", "assistant_message_id": message_id, "status": status,
                "usage": {"input_tokens": usage_info.input_tokens if usage_info else 0,
                          "output_tokens": usage_info.output_tokens if usage_info else 0},
                "remaining": quota.remaining})

    # ---- group events (sent by billing webhooks) --------------------------------------------------------
    async def plan_updated(self, event):
        await self.send_json({"type": "plan.updated", "plan": event["plan"]})

    # ---- helpers ---------------------------------------------------------------------------------------
    async def _snapshot(self) -> dict:
        def load():
            plan = current_plan(self.user)
            quota = usage.get_quota(self.user, plan.daily_message_limit)
            return {"plan": plan_payload(self.user), "usage": {"used": quota.used, "limit": quota.limit}}
        return await sync_to_async(load)()

    async def _error(self, code: str, message: str, client_id: str = ""):
        await self.send_json({"type": "chat.error", "code": code, "message": message, "client_id": client_id})

    async def _safe_send(self, payload: dict):
        try:
            await self.send_json(payload)
        except Exception:  # the socket may already be closed (we are saving a partial reply after a disconnect)
            logger.debug("socket closed before the final frame could be sent")
