import collections
import json
import logging
import time
import uuid

from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncWebsocketConsumer
from django.conf import settings

from . import services
from .models import Conversation
from .protocol import ProtocolError, error_message, parse_client_message, server_message
from .providers import get_provider
from .streaming import GenerationBusy, GenerationManager

logger = logging.getLogger(__name__)

MESSAGES_PER_MINUTE = 20

class ChatConsumer(AsyncWebsocketConsumer):
    """One instance per connected browser tab or phone. A thin adapter: the rules live in
    protocol.py (what is valid), streaming.py (how answers stream) and services.py (business rules)."""

    # ------------------------------------------------------------ lifecycle
    async def connect(self):
        await self.accept()                              # accept first so the client can read our close code
        user = self.scope.get("user")
        if user is None or not user.is_authenticated:
            await self.close(code=4401)
            return
        self.user = user
        self.user_group = f"user_{user.pk}"
        await self.channel_layer.group_add(self.user_group, self.channel_name)
        self.provider = get_provider()
        self.manager = GenerationManager(self.provider, self.send_json, self.save_reply,
                                         timeout=settings.AI_GENERATION_TIMEOUT)
        self.recent_sends = collections.deque()

    async def disconnect(self, code):
        manager = getattr(self, "manager", None)
        if manager:
            await manager.cancel_all()                   # stop paying for answers nobody will read
        group = getattr(self, "user_group", None)
        if group:
            await self.channel_layer.group_discard(group, self.channel_name)

    # ------------------------------------------------------------ sending helpers
    async def send_json(self, message: dict) -> None:
        await self.send(text_data=json.dumps(message))

    # ------------------------------------------------------------ receiving
    async def receive(self, text_data=None, bytes_data=None):
        if not hasattr(self, "manager"):                 # not authenticated
            return
        if text_data is None:
            await self.send_json(error_message(ProtocolError("unsupported_data", "Send text frames only.")))
            return
        try:
            envelope = parse_client_message(text_data)
            if envelope.type == "ping":
                await self.send_json(server_message("pong", ref=envelope.id))
            elif envelope.type == "message.send":
                await self.handle_message_send(envelope)
            elif envelope.type == "generation.cancel":
                await self.handle_cancel(envelope)
        except ProtocolError as error:
            await self.send_json(error_message(error))
        except Exception:
            logger.exception("Unexpected error while handling a WebSocket message")
            await self.send_json(error_message(ProtocolError("internal_error", "Something went wrong.")))

    def _check_rate_limit(self, ref):
        now = time.monotonic()
        while self.recent_sends and now - self.recent_sends[0] > 60:
            self.recent_sends.popleft()
        if len(self.recent_sends) >= MESSAGES_PER_MINUTE:
            raise ProtocolError("rate_limited", "You are sending messages too quickly.", ref)
        self.recent_sends.append(now)

    def _usage_and_limit(self):
        return services.tokens_used_this_month(user=self.user), services.monthly_token_limit(self.user)

    async def handle_message_send(self, envelope):
        data, ref = envelope.data, envelope.id
        self._check_rate_limit(ref)

        try:
            conversation = await database_sync_to_async(services.get_conversation_for_user)(
                user=self.user, public_id=uuid.UUID(data["conversation_id"]))
        except (ValueError, Conversation.DoesNotExist):
            raise ProtocolError("not_found", "Conversation not found.", ref) from None

        used, limit = await database_sync_to_async(self._usage_and_limit)()
        if used >= limit:
            raise ProtocolError("quota_exceeded", "Your monthly token limit has been reached.", ref,
                                {"used": [str(used)], "limit": [str(limit)]})

        try:
            generation_id = self.manager.reserve()
        except GenerationBusy:
            raise ProtocolError("generation_in_progress",
                                "Wait for the current answer to finish, or stop it first.", ref) from None
        try:
            message = await database_sync_to_async(services.add_user_message)(
                conversation=conversation, content=data["content"])
            history = await database_sync_to_async(services.get_recent_history)(conversation)
            await self.send_json(server_message(
                "message.accepted", {"message_id": f"msg_{message.pk}", "generation_id": generation_id}, ref))
        except BaseException:
            self.manager.release(generation_id)
            raise
        self.manager.run(generation_id, conversation=conversation, messages=history)

    async def handle_cancel(self, envelope):
        if not await self.manager.cancel(envelope.data["generation_id"]):
            raise ProtocolError("not_found", "No such generation is running.", envelope.id)

    async def save_reply(self, conversation, text, usage, status):
        message = await database_sync_to_async(services.save_assistant_reply)(
            conversation=conversation, text=text, input_tokens=usage.input_tokens,
            output_tokens=usage.output_tokens, model_name=self.provider.name)
        return f"msg_{message.pk}"

    # ------------------------------------------------------------ messages from other parts of the system
    async def notify(self, event):
        """Called for group_send({"type": "notify", "data": {...}}) to this user's group."""
        await self.send_json(server_message("notification", event["data"]))
