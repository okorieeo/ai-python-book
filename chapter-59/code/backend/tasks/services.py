"""Business rules for tasks. Views, the assistant's tools and Celery all call these,
never the ORM directly."""
from datetime import datetime

from django.db import transaction
from django.utils import timezone

from audit.services import Action, record
from core.security.sanitize import clean_text

from .models import Task


class TaskValidationError(ValueError):
    """A field is not acceptable. The message names the field, so a model or a form can
    fix it."""


def _clean(fields: dict) -> dict:
    out = {}
    try:
        if "title" in fields:
            out["title"] = clean_text(fields["title"], max_length=200, single_line=True)
            if not out["title"]:
                raise TaskValidationError("title: must not be empty")
        if "notes" in fields:
            out["notes"] = clean_text(fields["notes"] or "", max_length=4000)
    except TaskValidationError:
        raise
    except ValueError as exc:  # clean_text: too long
        raise TaskValidationError(f"text field: {exc}") from exc
    if "priority" in fields:
        if isinstance(fields["priority"], bool) or fields["priority"] not in (1, 2, 3, 4):
            raise TaskValidationError("priority: must be 1, 2, 3 or 4")
        out["priority"] = fields["priority"]
    if "estimate_minutes" in fields:
        value = fields["estimate_minutes"]
        if value is not None and (isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= 1440):
            raise TaskValidationError("estimate_minutes: must be 1 to 1440")
        out["estimate_minutes"] = value
    for key in ("due_at", "remind_at"):
        if key in fields:
            value = fields[key]
            if value is not None and (not isinstance(value, datetime) or value.tzinfo is None):
                raise TaskValidationError(f"{key}: must be a timezone-aware datetime")
            out[key] = value
    if "status" in fields:
        if fields["status"] not in Task.Status.values:
            raise TaskValidationError("status: must be todo, doing or done")
        out["status"] = fields["status"]
    return out


def _owned(user, task: Task) -> None:
    if task.user_id != user.id:
        # services never trust the caller to have checked ownership
        raise Task.DoesNotExist


def get_task_for_user(*, user, public_id) -> Task:
    # someone else's task simply does not exist
    return Task.objects.get(user=user, public_id=public_id)


def create_task(*, user, **fields) -> Task:
    data = _clean(fields)
    if "title" not in data:
        raise TaskValidationError("title: is required")
    return Task.objects.create(user=user, **data)


def update_task(*, user, task: Task, **fields) -> Task:
    _owned(user, task)
    data = _clean(fields)
    for key, value in data.items():
        setattr(task, key, value)
    if "status" in data:
        task.completed_at = timezone.now() if data["status"] == Task.Status.DONE else None
    task.save()
    return task


def complete_task(*, user, task: Task) -> Task:
    return update_task(user=user, task=task, status=Task.Status.DONE)


def delete_task(*, user, task: Task, request=None) -> None:
    _owned(user, task)
    with transaction.atomic():
        record(Action.TASK_DELETED, request=request, actor=user, target=task, metadata={"title_length": len(task.title)})
        task.delete()


def list_tasks(*, user, status: str = "open", due_before: datetime | None = None, search: str = "", limit: int = 20):
    qs = Task.objects.filter(user=user)
    if status == "open":
        qs = qs.exclude(status=Task.Status.DONE)
    elif status in Task.Status.values:
        qs = qs.filter(status=status)
    if due_before is not None:
        qs = qs.filter(due_at__isnull=False, due_at__lt=due_before)
    if search:
        qs = qs.filter(title__icontains=search[:100])
    return qs.order_by("due_at", "-priority", "id")[: min(limit, 50)]
