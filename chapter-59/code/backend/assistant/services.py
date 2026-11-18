"""Runs the agent for a person: loads the thread, calls the loop, saves what happened,
handles yes/no."""
import logging
from dataclasses import dataclass, field
from datetime import timedelta
from typing import Callable

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from audit.services import Action, record
# raises chat.services.DailyBudgetExceeded (Chapter 17)
from chat.services import check_daily_token_budget
from schedule.services import user_zone

from .agent import (
    AgentEvent, AgentResult, Limits, PendingCall, ResumeError, Status, resolve_pending, resume_agent, run_agent,
)
from .history import history_problems, trim_history
from .models import AssistantThread, AssistantUsage, PendingAction, ToolCallLog
from .prompt import build_system_prompt, stamp_user_message
from .tools import ToolContext
from .toolset import build_registry

log = logging.getLogger(__name__)

CONFIRMATION_TTL = timedelta(minutes=15)
# what we reserve against the daily budget before the real usage is known
ESTIMATED_RUN_TOKENS = 4000
LIMITS = Limits(max_steps=8, max_tool_calls=16, max_total_tokens=60_000)

# Only these events are streamed to the browser. Confirmations travel in the final
# message, with their ids.
STREAMED = {"text_delta", "tool_started", "tool_finished"}

EXPIRED_RESULT = (
    '{"status":"expired","message":"The person did not answer in time. Nothing was changed."}'
)


class AssistantBusy(Exception):
    """The previous request is still waiting for the person's yes or no."""


class ActionNotPending(Exception):
    """Already decided, or expired. Raised for a second click, a stale tab, or a
    replayed request."""


@dataclass
class Outcome:
    status: str
    text: str
    # [{"action_id", "tool", "summary"}]
    pending: list[dict] = field(default_factory=list)


def get_model_client():
    # imported late so tests never need the SDK or a key
    from .anthropic_client import AnthropicClient
    return AnthropicClient()


def get_thread(user) -> AssistantThread:
    thread = AssistantThread.objects.filter(user=user, archived=False).order_by("-updated_at").first()
    return thread or AssistantThread.objects.create(user=user)


def archive_thread(user) -> None:
    AssistantThread.objects.filter(user=user, archived=False).update(archived=True)


def _context(user, request) -> ToolContext:
    return ToolContext(user=user, now=timezone.now(), tz=user_zone(user), request=request)


def _forward(user, on_event: Callable[[AgentEvent], None] | None):
    def handle(event: AgentEvent) -> None:
        if event.type == "tool_finished":
            ToolCallLog.objects.create(user=user, tool=event.data["tool"], ok=event.data["ok"], code=event.data.get("code", ""))
        if on_event and event.type in STREAMED:
            on_event(event)
    return handle


def _expire_stale(thread: AssistantThread, now) -> None:
    """Close open questions that nobody answered, so the history is valid again. No
    model call, no cost."""
    stale = thread.pending_actions.filter(status=PendingAction.Status.PENDING, expires_at__lte=now)
    if not stale.exists() or thread.pending_actions.filter(status=PendingAction.Status.PENDING, expires_at__gt=now).exists():
        return
    blocks = list(thread.paused_results)
    for action in stale:
        blocks.append({"type": "tool_result", "tool_use_id": action.tool_use_id, "is_error": False,
                       "content": EXPIRED_RESULT})
    ids = [b["id"] for b in thread.messages[-1]["content"] if b.get("type") == "tool_use"]
    order = {tool_use_id: i for i, tool_use_id in enumerate(ids)}
    blocks.sort(key=lambda b: order.get(b["tool_use_id"], 0))
    thread.messages += [
        {"role": "user", "content": blocks},
        {"role": "assistant", "content": [{"type": "text", "text": "That request timed out and nothing was changed."}]},
    ]
    stale.update(status=PendingAction.Status.EXPIRED)
    thread.paused_results = []
    thread.save(update_fields=["messages", "paused_results", "updated_at"])


def _save(thread: AssistantThread, result: AgentResult, user, model_name: str, ctx: ToolContext) -> Outcome:
    problems = history_problems(result.messages[:-1] if result.status == Status.NEEDS_CONFIRMATION else result.messages)
    if problems:  # a bad history would make every later message fail: refuse to save it
        log.error("assistant_history_invalid", extra={"problems": problems})
        raise RuntimeError("Invalid conversation history")
    with transaction.atomic():
        thread.messages = result.messages
        thread.paused_results = result.results if result.status == Status.NEEDS_CONFIRMATION else []
        thread.save(update_fields=["messages", "paused_results", "updated_at"])
        AssistantUsage.objects.create(user=user, thread=thread, model=model_name,
                                      input_tokens=result.usage.input_tokens, output_tokens=result.usage.output_tokens)
        pending = [
            PendingAction.objects.create(thread=thread, tool_use_id=p.tool_use_id, tool=p.tool, arguments=p.arguments,
                                         summary=p.summary[:500], expires_at=ctx.now + CONFIRMATION_TTL)
            for p in result.pending
        ]
    return Outcome(result.status.value, result.text,
                   [{"action_id": str(a.public_id), "tool": a.tool, "summary": a.summary} for a in pending])


def send_message(*, user, text: str, request=None, on_event=None) -> Outcome:
    ctx = _context(user, request)
    thread = get_thread(user)
    _expire_stale(thread, ctx.now)
    if thread.pending_actions.filter(status=PendingAction.Status.PENDING).exists():
        raise AssistantBusy()
    # raises DailyBudgetExceeded
    check_daily_token_budget(user=user, estimated_tokens=ESTIMATED_RUN_TOKENS)

    # raises ValueError if empty or too long
    stamped = stamp_user_message(text, now=ctx.now, tz=ctx.tz)
    history = trim_history(thread.messages) + [{"role": "user", "content": stamped}]
    model = get_model_client()
    result = run_agent(
        model, build_registry(), ctx, system=build_system_prompt(tz_name=ctx.tz.key, today=ctx.now.astimezone(ctx.tz).date()),
        messages=history, limits=LIMITS, on_event=_forward(user, on_event),
    )
    return _save(thread, result, user, getattr(model, "model", settings.ASSISTANT_MODEL), ctx)


def decide(*, user, action_id, approve: bool, request=None, on_event=None) -> Outcome:
    ctx = _context(user, request)
    with transaction.atomic():
        # The row lock makes a double click, or two open tabs, decide exactly once.
        action = PendingAction.objects.select_for_update().select_related("thread").get(
            # someone else's action simply does not exist
            public_id=action_id, thread__user=user)
        if action.status != PendingAction.Status.PENDING:
            raise ActionNotPending()
        if action.expires_at <= ctx.now:
            action.status = PendingAction.Status.EXPIRED
            action.save(update_fields=["status"])
            expired = True
        else:
            expired = False
            chosen = PendingAction.Status.APPROVED if approve else PendingAction.Status.DECLINED
            action.status = chosen
            action.decided_at = ctx.now
            action.save(update_fields=["status", "decided_at"])
            record(Action.ASSISTANT_ACTION_CONFIRMED if approve else Action.ASSISTANT_ACTION_DECLINED,
                   request=request, actor=user, metadata={"tool": action.tool})
    if expired:
        raise ActionNotPending()

    thread = action.thread
    waiting = thread.pending_actions.filter(status=PendingAction.Status.PENDING)
    if waiting.exists():
        return Outcome("needs_confirmation", "", [
            {"action_id": str(a.public_id), "tool": a.tool, "summary": a.summary} for a in waiting])

    # Everything is decided. The tools that were approved run now, with the arguments we
    # stored.
    batch = thread.pending_actions.exclude(status=PendingAction.Status.EXPIRED).order_by("id")
    calls = [PendingCall(a.tool_use_id, a.tool, a.arguments, a.summary) for a in batch]
    approvals = {a.tool_use_id: a.status == PendingAction.Status.APPROVED for a in batch}
    registry = build_registry()
    decided = resolve_pending(registry, ctx, calls, approvals)
    model = get_model_client()
    result = resume_agent(
        model, registry, ctx, system=build_system_prompt(tz_name=ctx.tz.key, today=ctx.now.astimezone(ctx.tz).date()),
        messages=thread.messages, results=list(thread.paused_results) + decided, limits=LIMITS,
        on_event=_forward(user, on_event),
    )
    # the decisions are in the history and the audit log now
    thread.pending_actions.all().delete()
    return _save(thread, result, user, getattr(model, "model", settings.ASSISTANT_MODEL), ctx)
