"""Rank open tasks and fit them into free time. Pure Python, no Django.

The score is deliberately simple and explainable: every point comes with a reason a
person can read,
so "why is this first?" always has an answer. Tune the numbers in WEIGHTS, not the
logic.
"""
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Sequence
from zoneinfo import ZoneInfo

from core.timeutils import to_local
from schedule.availability import Interval

# Task.priority values: bigger means more important
LOW, NORMAL, HIGH, URGENT = 1, 2, 3, 4
DEFAULT_ESTIMATE_MINUTES = 30

WEIGHTS = {
    "per_priority_level": 10,
    "overdue_base": 40, "overdue_per_day": 2, "overdue_max_days": 14,
    "due_today": 35, "due_tomorrow": 25, "due_within_3_days": 15, "due_within_7_days": 8, "due_later": 2,
    "quick_win_minutes": 15, "quick_win_bonus": 3,
    "age_per_day": 0.1, "age_max_days": 30,
}


@dataclass(frozen=True)
class PlannableTask:
    id: str
    title: str
    priority: int = NORMAL
    due_at: datetime | None = None          # aware UTC
    estimate_minutes: int | None = None
    created_at: datetime | None = None      # aware UTC


@dataclass(frozen=True)
class RankedTask:
    task: PlannableTask
    score: float
    reasons: tuple[str, ...]


@dataclass(frozen=True)
class PlanItem:
    task_id: str
    title: str
    start: datetime
    end: datetime
    reasons: tuple[str, ...]


@dataclass(frozen=True)
class DayPlan:
    items: list[PlanItem] = field(default_factory=list)
    unscheduled: list[str] = field(default_factory=list)  # task ids that did not fit


def _score(task: PlannableTask, now: datetime, tz: ZoneInfo) -> RankedTask:
    w = WEIGHTS
    score = task.priority * w["per_priority_level"]
    reasons = [f"priority {task.priority} of 4"]

    if task.due_at is not None:
        days_left = (to_local(task.due_at, tz).date() - to_local(now, tz).date()).days
        if task.due_at < now and days_left < 0:
            days_over = min(-days_left, w["overdue_max_days"])
            score += w["overdue_base"] + days_over * w["overdue_per_day"]
            reasons.append(f"overdue by {-days_left} day{'s' if -days_left != 1 else ''}")
        elif task.due_at < now:  # earlier today, still open
            score += w["overdue_base"]
            reasons.append("was due earlier today")
        elif days_left == 0:
            score += w["due_today"]
            reasons.append("due today")
        elif days_left == 1:
            score += w["due_tomorrow"]
            reasons.append("due tomorrow")
        elif days_left <= 3:
            score += w["due_within_3_days"]
            reasons.append(f"due in {days_left} days")
        elif days_left <= 7:
            score += w["due_within_7_days"]
            reasons.append(f"due in {days_left} days")
        else:
            score += w["due_later"]

    if task.estimate_minutes is not None and task.estimate_minutes <= w["quick_win_minutes"]:
        score += w["quick_win_bonus"]
        reasons.append("quick win")

    if task.created_at is not None:
        age_days = min(max((now - task.created_at).days, 0), w["age_max_days"])
        score += age_days * w["age_per_day"]  # stops old tasks from starving

    return RankedTask(task, round(score, 2), tuple(reasons))


def rank_tasks(tasks: Sequence[PlannableTask], *, now: datetime, tz: ZoneInfo) -> list[RankedTask]:
    """Highest score first. Ties break on earlier due date, then older task, then id:
    always the same order."""
    far_future = datetime.max.replace(tzinfo=now.tzinfo)
    scored = [_score(t, now, tz) for t in tasks]
    return sorted(
        scored,
        key=lambda r: (-r.score, r.task.due_at or far_future, r.task.created_at or far_future, r.task.id),
    )


def build_day_plan(
    ranked: Sequence[RankedTask],
    slots: Sequence[Interval],
    *,
    break_minutes: int = 5,
) -> DayPlan:
    """Put the most important tasks into the earliest slots where they fit (first fit,
    no splitting)."""
    remaining = [Interval(s.start, s.end) for s in slots]
    gap = timedelta(minutes=break_minutes)
    plan = DayPlan()
    for item in ranked:
        need = timedelta(minutes=item.task.estimate_minutes or DEFAULT_ESTIMATE_MINUTES)
        for index, slot in enumerate(remaining):
            if slot.duration >= need:
                end = slot.start + need
                plan.items.append(PlanItem(item.task.id, item.task.title, slot.start, end, item.reasons))
                rest_start = end + gap
                if slot.end - rest_start > timedelta(0):
                    remaining[index] = Interval(rest_start, slot.end)
                else:
                    del remaining[index]
                break
        else:
            plan.unscheduled.append(item.task.id)
    plan.items.sort(key=lambda p: p.start)
    return plan
