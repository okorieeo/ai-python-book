"""Tests for tasks.planning. Plain unittest, no Django needed."""
from datetime import datetime, timedelta
from unittest import TestCase

from core.timeutils import UTC, get_zone
from schedule.availability import Interval
from tasks.planning import HIGH, LOW, NORMAL, URGENT, PlannableTask, build_day_plan, rank_tasks

LAGOS = get_zone("Africa/Lagos")
NOW = datetime(2026, 11, 11, 10, 0, tzinfo=UTC)  # 11:00 on Wednesday 11 Nov in Lagos


def task(id, **kw):
    return PlannableTask(id=id, title=f"Task {id}", **kw)


def order(tasks):
    return [r.task.id for r in rank_tasks(tasks, now=NOW, tz=LAGOS)]


class RankingTests(TestCase):
    def test_priority_orders_tasks_without_dates(self):
        self.assertEqual(order([task("a", priority=LOW), task("b", priority=URGENT), task("c", priority=NORMAL)]),
                         ["b", "c", "a"])

    def test_overdue_beats_everything_of_the_same_priority(self):
        tasks = [task("later", due_at=NOW + timedelta(days=10)), task("late", due_at=NOW - timedelta(days=2)),
                 task("none")]
        self.assertEqual(order(tasks), ["late", "later", "none"])

    def test_due_today_vs_tomorrow_vs_next_week(self):
        tasks = [task("week", due_at=NOW + timedelta(days=6)), task("tom", due_at=NOW + timedelta(days=1)),
                 task("today", due_at=NOW + timedelta(hours=3))]
        self.assertEqual(order(tasks), ["today", "tom", "week"])

    def test_high_priority_without_a_date_can_beat_normal_priority_due_soon(self):
        # 3*10 = 30 versus 2*10 + 8 (due in 5 days) = 28
        tasks = [task("soon", priority=NORMAL, due_at=NOW + timedelta(days=5)), task("big", priority=HIGH)]
        self.assertEqual(order(tasks), ["big", "soon"])

    def test_reasons_explain_the_score(self):
        ranked = rank_tasks([task("a", priority=URGENT, due_at=NOW - timedelta(days=3), estimate_minutes=10)],
                            now=NOW, tz=LAGOS)
        self.assertEqual(ranked[0].reasons, ("priority 4 of 4", "overdue by 3 days", "quick win"))

    def test_due_earlier_today_counts_as_overdue_but_not_a_whole_day(self):
        ranked = rank_tasks([task("a", due_at=NOW - timedelta(hours=1))], now=NOW, tz=LAGOS)
        self.assertIn("was due earlier today", ranked[0].reasons)

    def test_age_stops_old_tasks_from_starving(self):
        # Without the age bonus "new" would win (20 + 2 for being due in 10 days = 22 against 20).
        tasks = [task("new", created_at=NOW, due_at=NOW + timedelta(days=10)), task("old", created_at=NOW - timedelta(days=30))]
        ranked = rank_tasks(tasks, now=NOW, tz=LAGOS)
        self.assertEqual([r.task.id for r in ranked], ["old", "new"])
        self.assertEqual([r.score for r in ranked], [23.0, 22.0])

    def test_age_bonus_is_capped(self):
        ranked = rank_tasks([task("ancient", created_at=NOW - timedelta(days=900))], now=NOW, tz=LAGOS)
        self.assertEqual(ranked[0].score, 23.0)  # 20 + 30 days * 0.1, not 900 days * 0.1

    def test_ties_are_broken_the_same_way_every_time(self):
        tasks = [task("b"), task("a"), task("c")]
        self.assertEqual(order(tasks), ["a", "b", "c"])
        self.assertEqual(order(list(reversed(tasks))), ["a", "b", "c"])

    def test_due_date_uses_the_users_local_day(self):
        # 23:30 UTC on the 11th is 00:30 on the 12th in Lagos, so it is "tomorrow" for this user.
        ranked = rank_tasks([task("a", due_at=datetime(2026, 11, 11, 23, 30, tzinfo=UTC))], now=NOW, tz=LAGOS)
        self.assertIn("due tomorrow", ranked[0].reasons)

    def test_empty(self):
        self.assertEqual(order([]), [])


class DayPlanTests(TestCase):
    def slot(self, h1, h2, m1=0, m2=0):
        return Interval(datetime(2026, 11, 11, h1, m1, tzinfo=UTC), datetime(2026, 11, 11, h2, m2, tzinfo=UTC))

    def plan(self, tasks, slots, **kw):
        return build_day_plan(rank_tasks(tasks, now=NOW, tz=LAGOS), slots, **kw)

    def test_most_important_task_gets_the_earliest_slot(self):
        plan = self.plan([task("low", priority=LOW, estimate_minutes=60), task("top", priority=URGENT, estimate_minutes=60)],
                         [self.slot(11, 14)])
        self.assertEqual([(i.task_id, i.start.hour) for i in plan.items], [("top", 11), ("low", 12)])

    def test_break_is_left_between_tasks(self):
        plan = self.plan([task("a", priority=URGENT, estimate_minutes=30), task("b", estimate_minutes=30)],
                         [self.slot(11, 13)], break_minutes=10)
        self.assertEqual(plan.items[1].start, datetime(2026, 11, 11, 11, 40, tzinfo=UTC))

    def test_task_too_long_for_every_slot_is_unscheduled(self):
        plan = self.plan([task("long", estimate_minutes=240)], [self.slot(11, 13)])
        self.assertEqual((plan.items, plan.unscheduled), ([], ["long"]))

    def test_task_moves_to_a_later_slot_when_the_first_is_too_small(self):
        tasks = [task("big", priority=URGENT, estimate_minutes=90), task("small", estimate_minutes=20)]
        plan = self.plan(tasks, [self.slot(11, 12, 0, 40), self.slot(15, 16)])
        self.assertEqual([(i.task_id, i.start.hour) for i in plan.items], [("big", 11), ("small", 15)])

    def test_default_estimate_is_30_minutes(self):
        plan = self.plan([task("a")], [self.slot(11, 12)])
        self.assertEqual(plan.items[0].end - plan.items[0].start, timedelta(minutes=30))

    def test_no_slots(self):
        plan = self.plan([task("a"), task("b")], [])
        self.assertEqual(plan.unscheduled, ["a", "b"])

    def test_plan_never_overlaps_itself(self):
        tasks = [task(str(n), estimate_minutes=25, priority=1 + n % 4) for n in range(12)]
        plan = self.plan(tasks, [self.slot(9, 12), self.slot(14, 17)])
        for left, right in zip(plan.items, plan.items[1:]):
            self.assertLessEqual(left.end, right.start)
        self.assertEqual(len(plan.items) + len(plan.unscheduled), 12)
