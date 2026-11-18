"""The streaming door into the assistant. Built on the Chapter 14 consumer pattern."""
from asgiref.sync import async_to_sync, sync_to_async
from channels.generic.websocket import AsyncJsonWebsocketConsumer
from django.db import close_old_connections

from chat.services import DailyBudgetExceeded

from . import services
from .agent import AgentEvent, ModelUnavailable
from .models import PendingAction
from .prompt import MAX_USER_MESSAGE_CHARS


class AssistantConsumer(AsyncJsonWebsocketConsumer):
    async def connect(self):
        user = self.scope["user"]
        if not user.is_authenticated:
            await self.close(code=4401)
            return
        await self.accept()

    async def receive_json(self, content, **kwargs):
        kind = content.get("type")
        if kind == "message" and isinstance(content.get("text"), str) and len(content["text"]) <= MAX_USER_MESSAGE_CHARS:
            await self._run(lambda emit: services.send_message(user=self.scope["user"], text=content["text"], on_event=emit))
        elif kind == "decision" and isinstance(content.get("action_id"), str) and isinstance(content.get("approve"), bool):
            await self._run(lambda emit: services.decide(
                user=self.scope["user"], action_id=content["action_id"], approve=content["approve"], on_event=emit))
        else:
            await self.send_json({"type": "assistant.error", "code": "bad_message", "message": "Unrecognised message."})

    async def _run(self, work):
        def emit(event: AgentEvent) -> None:
            # We are in a worker thread; async_to_sync hands the send back to this
            # connection's event loop, in order.
            async_to_sync(self.send_json)({"type": f"assistant.{event.type}", **event.data})

        def blocking():
            # a long-lived thread must not keep a stale database connection
            close_old_connections()
            try:
                return work(emit)
            finally:
                close_old_connections()

        try:
            # thread_sensitive=False: a model call takes seconds and must not queue
            # every other user behind it.
            outcome = await sync_to_async(blocking, thread_sensitive=False)()
        except services.AssistantBusy:
            await self._error("awaiting_confirmation", "Answer the open question first.")
        except services.ActionNotPending:
            await self._error("not_pending", "That question was already answered or has expired.")
        except DailyBudgetExceeded:
            await self._error("daily_budget", "Today's assistant allowance is used up.")
        except ModelUnavailable:
            await self._error("model_unavailable", "The assistant is unavailable right now. Try again in a minute.")
        except (PendingAction.DoesNotExist, ValueError):
            await self._error("invalid_request", "That request was not valid.")
        else:
            await self.send_json({"type": "assistant.done", "status": outcome.status, "text": outcome.text, "pending": outcome.pending})

    async def _error(self, code: str, message: str):
        await self.send_json({"type": "assistant.error", "code": code, "message": message})
