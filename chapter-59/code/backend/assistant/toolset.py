"""Binds the pure tool machinery to our services. Each handler is thin: parse, call a
service, shape the answer."""
import uuid
from datetime import datetime, time, timedelta

from core.timeutils import (
    TimeInputError, format_local, local_day_bounds, parse_local_date, parse_local_datetime, resolve_local,
)
from schedule import services as calendar
from schedule.availability import free_slots
from schedule.recurrence import RuleError
from tasks import services as todo
from tasks.models import Task
from tasks.planning import PlannableTask, build_day_plan, rank_tasks

from .tools import Risk, Tool, ToolContext, ToolError, ToolRegistry

# Result fields that hold text written by people. The registry wraps them as untrusted
# data automatically.
FREE_TEXT = {"title": 200, "notes": 500, "description": 500, "location": 100}

DATE = r"\d{4}-\d{2}-\d{2}"
DATETIME = r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}"
UUID = r"[0-9a-fA-F-]{36}"
LOCAL_TIME_HELP = (
    "Local time in the person's time zone as YYYY-MM-DDTHH:MM, with no offset and no Z."
)


# ---- helpers
# -------------------------------------------------------------------------------------

def _guard(fn):
    """Turn service-layer problems into messages the model can act on."""

    def wrapper(ctx: ToolContext, args: dict) -> dict:
        try:
            return fn(ctx, args)
        except (Task.DoesNotExist, calendar.Event.DoesNotExist) as exc:
            raise ToolError("No item with that id. Look it up again with a list tool.", code="not_found") from exc
        except (todo.TaskValidationError, calendar.EventValidationError, TimeInputError, RuleError) as exc:
            raise ToolError(str(exc), code="invalid") from exc

    wrapper.__name__ = fn.__name__
    return wrapper


def _uuid(text: str) -> uuid.UUID:
    try:
        return uuid.UUID(text)
    except ValueError as exc:
        raise ToolError("id: not a valid id", code="invalid") from exc


def _local_dt(text: str, ctx: ToolContext, *, date_means_end_of_day=False) -> datetime:
    """Accept a date or a date and time; return aware UTC."""
    if "T" in text:
        return resolve_local(parse_local_datetime(text), ctx.tz).utc
    day = parse_local_date(text)
    wall = datetime.combine(day, time(23, 59) if date_means_end_of_day else time(9, 0))
    return resolve_local(wall, ctx.tz).utc


def _task_dict(task: Task, ctx: ToolContext) -> dict:
    return {
        "id": str(task.public_id), "title": task.title, "notes": task.notes[:500], "status": task.status,
        "priority": task.priority, "estimate_minutes": task.estimate_minutes,
        "due": format_local(task.due_at, ctx.tz) if task.due_at else None,
    }


def _occurrence_dict(o, ctx: ToolContext) -> dict:
    return {"event_id": str(o.event.public_id), "title": o.event.title, "start": format_local(o.start, ctx.tz),
            "end": format_local(o.end, ctx.tz), "recurring": o.recurring}


def _day_range(ctx: ToolContext, first: str, last: str) -> tuple[datetime, datetime]:
    start = local_day_bounds(parse_local_date(first), ctx.tz)[0]
    end = local_day_bounds(parse_local_date(last), ctx.tz)[1]
    if end <= start or end - start > timedelta(days=31):
        raise ToolError("Choose a range of 1 to 31 days, with the end on or after the start.", code="invalid")
    return start, end


# ---- read tools
# ----------------------------------------------------------------------------------

@_guard
def list_tasks(ctx, args):
    before = _local_dt(args["due_before"], ctx, date_means_end_of_day=True) if "due_before" in args else None
    rows = list(todo.list_tasks(user=ctx.user, status=args["status"], due_before=before,
                                search=args.get("search", ""), limit=args["limit"] + 1))
    shown = rows[: args["limit"]]
    return {"tasks": [_task_dict(t, ctx) for t in shown], "more": len(rows) > len(shown)}


@_guard
def list_events(ctx, args):
    start, end = _day_range(ctx, args["start_date"], args["end_date"])
    found = calendar.occurrences_between(user=ctx.user, start=start, end=end)
    return {"events": [_occurrence_dict(o, ctx) for o in found[:60]], "more": len(found) > 60}


@_guard
def find_free_slots(ctx, args):
    start, end = _day_range(ctx, args["start_date"], args["end_date"])
    start = max(start, ctx.now)  # never offer the past
    if end <= start:
        return {"slots": []}
    prefs = calendar.get_preferences(ctx.user)
    busy = calendar.busy_intervals(user=ctx.user, start=start - timedelta(days=1), end=end + timedelta(days=1))
    slots = free_slots(busy, window_start=start, window_end=end, duration=timedelta(minutes=args["duration_minutes"]),
                       tz=ctx.tz, hours=calendar.working_hours(prefs), buffer=timedelta(minutes=args["buffer_minutes"]))
    return {"slots": [{"start": format_local(s.start, ctx.tz), "end": format_local(s.end, ctx.tz)} for s in slots[:10]]}


@_guard
def plan_my_day(ctx, args):
    day = parse_local_date(args["date"]) if "date" in args else ctx.now.astimezone(ctx.tz).date()
    start, end = local_day_bounds(day, ctx.tz)
    start = max(start, ctx.now)
    prefs = calendar.get_preferences(ctx.user)
    busy = calendar.busy_intervals(user=ctx.user, start=start - timedelta(days=1), end=end + timedelta(days=1))
    slots = free_slots(busy, window_start=start, window_end=end, duration=timedelta(minutes=15),
                       tz=ctx.tz, hours=calendar.working_hours(prefs)) if end > start else []
    open_tasks = list(todo.list_tasks(user=ctx.user, status="open", limit=50))
    by_id = {str(t.public_id): t for t in open_tasks}
    ranked = rank_tasks([PlannableTask(str(t.public_id), t.title, t.priority, t.due_at, t.estimate_minutes, t.created_at)
                         for t in open_tasks], now=ctx.now, tz=ctx.tz)
    plan = build_day_plan(ranked, slots)
    return {
        "date": day.isoformat(),
        "plan": [{"task_id": i.task_id, "title": i.title, "start": format_local(i.start, ctx.tz),
                  "end": format_local(i.end, ctx.tz), "why": ", ".join(i.reasons)} for i in plan.items],
        "did_not_fit": [{"task_id": tid, "title": by_id[tid].title} for tid in plan.unscheduled[:10]],
    }


# ---- write tools
# ---------------------------------------------------------------------------------

@_guard
def create_task(ctx, args):
    fields = {k: args[k] for k in ("title", "notes", "priority", "estimate_minutes") if k in args}
    if "due" in args:
        fields["due_at"] = _local_dt(args["due"], ctx, date_means_end_of_day=True)
    if "remind_at" in args:
        fields["remind_at"] = _local_dt(args["remind_at"], ctx)
    return {"task": _task_dict(todo.create_task(user=ctx.user, **fields), ctx)}


@_guard
def update_task(ctx, args):
    task = todo.get_task_for_user(user=ctx.user, public_id=_uuid(args["id"]))
    fields = {k: args[k] for k in ("title", "notes", "priority", "estimate_minutes", "status") if k in args}
    if "due" in args:
        fields["due_at"] = _local_dt(args["due"], ctx, date_means_end_of_day=True)
    if args.get("clear_due"):
        fields["due_at"] = None
    return {"task": _task_dict(todo.update_task(user=ctx.user, task=task, **fields), ctx)}


@_guard
def complete_task(ctx, args):
    task = todo.get_task_for_user(user=ctx.user, public_id=_uuid(args["id"]))
    return {"task": _task_dict(todo.complete_task(user=ctx.user, task=task), ctx)}


@_guard
def create_event(ctx, args):
    event, clashes = calendar.create_event(
        user=ctx.user, tz=ctx.tz, title=args["title"], start_local=parse_local_datetime(args["start"]),
        end_local=parse_local_datetime(args["end"]), description=args.get("description", ""),
        location=args.get("location", ""), recurrence=args.get("repeat"),
        remind_minutes_before=args.get("remind_minutes_before"),
    )
    out = {"event": {"id": str(event.public_id), "title": event.title, "start": args["start"], "end": args["end"],
                     "repeats": event.recurrence is not None}}
    if clashes:
        out["warning"] = f"This overlaps {len(clashes)} other event(s). Tell the person."
        out["overlaps"] = [_occurrence_dict(o, ctx) for o in clashes[:5]]
    return out


@_guard
def reschedule_event(ctx, args):
    event = calendar.get_event_for_user(user=ctx.user, public_id=_uuid(args["id"]))
    end = parse_local_datetime(args["end"]) if "end" in args else None
    event, clashes = calendar.reschedule_event(user=ctx.user, tz=ctx.tz, event=event,
                                               start_local=parse_local_datetime(args["start"]), end_local=end)
    out = {"event": {"id": str(event.public_id), "title": event.title,
                     "start": format_local(event.start_at, ctx.tz), "end": format_local(event.end_at, ctx.tz)}}
    if clashes:
        out["warning"] = f"This now overlaps {len(clashes)} other event(s). Tell the person."
    return out


# ---- confirm tools: what the person is shown, written by us from validated arguments
# --------------

@_guard
def delete_task(ctx, args):
    todo.delete_task(user=ctx.user, task=todo.get_task_for_user(user=ctx.user, public_id=_uuid(args["id"])), request=ctx.request)
    return {"deleted": True}


@_guard
def delete_event(ctx, args):
    calendar.delete_event(user=ctx.user, event=calendar.get_event_for_user(user=ctx.user, public_id=_uuid(args["id"])),
                          request=ctx.request)
    return {"deleted": True}


@_guard
def _summarize_delete_task(ctx, args) -> str:
    task = todo.get_task_for_user(user=ctx.user, public_id=_uuid(args["id"]))
    return f"Delete the task “{task.title}”"


@_guard
def _summarize_delete_event(ctx, args) -> str:
    event = calendar.get_event_for_user(user=ctx.user, public_id=_uuid(args["id"]))
    when = format_local(event.start_at, ctx.tz).replace("T", " at ")
    return f"Delete the event “{event.title}” ({when})" + (" and ALL of its repeats" if event.recurrence else "")


# ---- the catalogue
# -------------------------------------------------------------------------------

def _obj(properties: dict, required: list[str] | None = None) -> dict:
    return {"type": "object", "properties": properties, "required": required or []}


def _text(max_length: int, **extra) -> dict:
    return {"type": "string", "maxLength": max_length, **extra}


def _number(low: int, high: int, **extra) -> dict:
    return {"type": "integer", "minimum": low, "maximum": high, **extra}


def _pattern(regex: str, **extra) -> dict:
    return {"type": "string", "pattern": regex, **extra}


ID = _pattern(UUID, description="The id returned by a list tool. Never invent one.")
DAY = _pattern(DATE)
DAY_OR_TIME = _pattern(DATE + "(T\\d{2}:\\d{2})?")
LOCAL_TIME = _pattern(DATETIME, description=LOCAL_TIME_HELP)
TITLE = {"type": "string", "minLength": 1, "maxLength": 200}
PRIORITY_HELP = "1 low, 2 normal, 3 high, 4 urgent."

REPEAT = {
    "type": "object",
    "description": (
        "Optional repeat rule. Example: "
        '{"freq": "weekly", "by_weekday": ["MO", "WE"], "until": "2026-12-31"}. '
        "freq is daily, weekly, monthly or yearly; interval is every N; "
        "give either until or count, not both."
    ),
}


def build_registry() -> ToolRegistry:
    return ToolRegistry(
        [
            Tool(
                name="list_tasks",
                description=(
                    "List the person's tasks, most urgent first. Use this before changing or "
                    "deleting a task to find its id."
                ),
                input_schema=_obj({
                    "status": {"type": "string", "enum": ["open", "done", "all"], "default": "open"},
                    "due_before": _pattern(DATE + "(T\\d{2}:\\d{2})?",
                                           description="Only tasks due before the end of this date."),
                    "search": _text(100, description="Words from the title."),
                    "limit": _number(1, 50, default=20),
                }),
                handler=list_tasks,
            ),
            Tool(
                name="list_events",
                description=(
                    "List calendar events between two dates, both included. Use this before "
                    "changing or deleting an event to find its id."
                ),
                input_schema=_obj({"start_date": DAY, "end_date": DAY}, ["start_date", "end_date"]),
                handler=list_events,
            ),
            Tool(
                name="find_free_slots",
                description=(
                    "Find free time inside the person's working hours. Slots are never in the past."
                ),
                input_schema=_obj(
                    {
                        "start_date": DAY,
                        "end_date": DAY,
                        "duration_minutes": _number(5, 480),
                        "buffer_minutes": _number(0, 60, default=0,
                                                  description="Margin to keep around existing events."),
                    },
                    ["start_date", "end_date", "duration_minutes"],
                ),
                handler=find_free_slots,
            ),
            Tool(
                name="plan_my_day",
                description=(
                    "Suggest when to work on open tasks today (or on a given date), based on "
                    "priority, due dates and free time. Only a suggestion: nothing is created."
                ),
                input_schema=_obj({"date": DAY}),
                handler=plan_my_day,
            ),
            Tool(
                name="create_task",
                description="Create a task. A due value with only a date means the end of that day.",
                input_schema=_obj(
                    {
                        "title": TITLE,
                        "notes": _text(4000),
                        "due": DAY_OR_TIME,
                        "priority": _number(1, 4, default=2, description=PRIORITY_HELP),
                        "estimate_minutes": _number(1, 1440),
                        "remind_at": LOCAL_TIME,
                    },
                    ["title"],
                ),
                handler=create_task,
                risk=Risk.WRITE,
            ),
            Tool(
                name="update_task",
                description="Change fields of an existing task. Only send the fields that change.",
                input_schema=_obj(
                    {
                        "id": ID,
                        "title": TITLE,
                        "notes": _text(4000),
                        "due": DAY_OR_TIME,
                        "clear_due": {"type": "boolean"},
                        "priority": _number(1, 4),
                        "estimate_minutes": _number(1, 1440),
                        "status": {"type": "string", "enum": ["todo", "doing", "done"]},
                    },
                    ["id"],
                ),
                handler=update_task,
                risk=Risk.WRITE,
            ),
            Tool(
                name="complete_task",
                description="Mark a task as done. Use list_tasks first to find its id.",
                input_schema=_obj({"id": ID}, ["id"]),
                handler=complete_task,
                risk=Risk.WRITE,
            ),
            Tool(
                name="create_event",
                description=(
                    "Create a calendar event. If it overlaps another event the result includes "
                    "a warning: tell the person."
                ),
                input_schema=_obj(
                    {
                        "title": TITLE,
                        "start": LOCAL_TIME,
                        "end": LOCAL_TIME,
                        "description": _text(4000),
                        "location": _text(200),
                        "repeat": REPEAT,
                        "remind_minutes_before": _number(0, 1440),
                    },
                    ["title", "start", "end"],
                ),
                handler=create_event,
                risk=Risk.WRITE,
            ),
            Tool(
                name="reschedule_event",
                description=(
                    "Move a one-off event to a new time. If end is omitted the length stays the "
                    "same. Events that repeat cannot be moved with this tool."
                ),
                input_schema=_obj({"id": ID, "start": LOCAL_TIME, "end": _pattern(DATETIME)},
                                  ["id", "start"]),
                handler=reschedule_event,
                risk=Risk.WRITE,
            ),
            Tool(
                name="delete_task",
                description=(
                    "Delete a task for good. The app asks the person to confirm before it happens."
                ),
                input_schema=_obj({"id": ID}, ["id"]),
                handler=delete_task,
                risk=Risk.CONFIRM,
                summarize=_summarize_delete_task,
            ),
            Tool(
                name="delete_event",
                description=(
                    "Delete an event (all repeats of a repeating event). The app asks the "
                    "person to confirm before it happens."
                ),
                input_schema=_obj({"id": ID}, ["id"]),
                handler=delete_event,
                risk=Risk.CONFIRM,
                summarize=_summarize_delete_event,
            ),
        ],
        free_text=FREE_TEXT,
    )
