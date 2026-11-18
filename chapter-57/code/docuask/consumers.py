"""WebSocket consumer that streams an answer token by token (Channels, Chapter 14). NOT executed in the book's test environment.

Messages from the browser:  {"type": "ask", "question": "...", "conversation_id": 12, "document_ids": [1, 2]}  or  {"type": "stop"}
Messages to the browser:    {"type": "token", "text": "..."}  then  {"type": "done", "answer": ..., "citations": [...], "grounded": bool}
                            or  {"type": "error", "code": "limit_exceeded" | "busy" | "failed", "message": "..."}"""
import asyncio

from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncJsonWebsocketConsumer

from docuask_core.citations import NO_ANSWER_TEXT
from docuask_core.limits import LimitExceeded
from docuask_core.retrieval import should_answer

from . import usage
from .llm import ANSWER_MODEL, rewrite_question, stream_answer
from .models import Conversation, Message
from .search import hybrid_search
from .tasks import get_embedder
from .views import NO_ANSWER_THRESHOLD, plan_of


class AskConsumer(AsyncJsonWebsocketConsumer):
    task = None

    async def connect(self):
        if not self.scope["user"].is_authenticated:
            await self.close(code=4401)                       # never accept first and check later
            return
        await self.accept()

    async def disconnect(self, code):
        if self.task:
            self.task.cancel()

    async def receive_json(self, content):
        if content.get("type") == "stop":
            if self.task:
                self.task.cancel()
        elif content.get("type") == "ask":
            if self.task and not self.task.done():
                await self.send_json({"type": "error", "code": "busy", "message": "Wait for the current answer to finish."})
                return
            self.task = asyncio.create_task(self.handle_ask(content))

    async def handle_ask(self, content):
        user = self.scope["user"]
        question = str(content.get("question", "")).strip()
        if not (3 <= len(question) <= 2000):
            await self.send_json({"type": "error", "code": "failed", "message": "Ask a question between 3 and 2000 characters."})
            return
        try:
            await database_sync_to_async(usage.consume)(user, plan_of(user), "questions", 1)
        except LimitExceeded as exc:
            await self.send_json({"type": "error", "code": "limit_exceeded", "message": str(exc)})
            return
        try:
            convo, history, doc_ids = await database_sync_to_async(self._conversation)(user, content, question)
            standalone = await database_sync_to_async(rewrite_question)(history, question)
            vec = await database_sync_to_async(lambda: get_embedder().embed_query(standalone))()
            chunks, best = await database_sync_to_async(hybrid_search)(user, standalone, vec, doc_ids)
            if not chunks or not should_answer(best, NO_ANSWER_THRESHOLD):
                await self.send_json({"type": "token", "text": NO_ANSWER_TEXT})
                await self._finish(convo, question, NO_ANSWER_TEXT, [], False, 0, 0)
                return
            async for event in stream_answer(standalone, chunks, history):
                if event["type"] == "token":
                    await self.send_json(event)
                else:
                    p = event["parsed"]
                    await self._finish(convo, question, p.text, [c.__dict__ for c in p.citations], p.grounded,
                                       event["input_tokens"], event["output_tokens"])
        except asyncio.CancelledError:
            raise                                             # the user pressed Stop: the quota stays used, the work was done
        except Exception:
            await database_sync_to_async(usage.refund)(user, "questions", 1)
            await self.send_json({"type": "error", "code": "failed", "message": "Something went wrong. Your question was not counted."})

    def _conversation(self, user, content, question):
        convo = (Conversation.objects.filter(owner=user, pk=content.get("conversation_id")).first()
                 or Conversation.objects.create(owner=user, title=question[:120]))
        history = [{"role": m.role, "content": m.content} for m in convo.messages.all()[:12]]
        return convo, history, content.get("document_ids") or None

    async def _finish(self, convo, question, text, citations, grounded, tin, tout):
        await database_sync_to_async(self._save)(convo, question, text, citations, grounded, tin, tout)
        await self.send_json({"type": "done", "conversation_id": convo.id, "answer": text, "citations": citations, "grounded": grounded})

    def _save(self, convo, question, text, citations, grounded, tin, tout):
        Message.objects.create(conversation=convo, role="user", content=question)
        Message.objects.create(conversation=convo, role="assistant", content=text, citations=citations,
                               grounded=grounded, model=ANSWER_MODEL, input_tokens=tin, output_tokens=tout)
