"""Tests for assistant.prompt and assistant.briefing. Plain unittest."""
from datetime import date, datetime, time, timedelta
from unittest import TestCase

from core.timeutils import UTC, get_zone
from assistant.briefing import ReminderCandidate, due_reminders, is_briefing_due, render_briefing
from assistant.prompt import MAX_USER_MESSAGE_CHARS, RULES, build_system_prompt, stamp_user_message
from tasks.planning import PlannableTask, rank_tasks

LAGOS = get_zone("Africa/Lagos")
NY = get_zone("America/New_York")


class PromptTests(TestCase):
    def test_system_prompt_ends_with_the_changing_part(self):
        prompt = build_system_prompt(tz_name="Africa/Lagos", today=date(2026, 11, 11))
        self.assertTrue(prompt.startswith(RULES))  # identical prefix every request: cache friendly
        self.assertTrue(prompt.endswith("Today's date there is Wednesday 11 November 2026."))

    def test_rules_mention_the_important_things(self):
        for phrase in ("<untrusted>", "YYYY-MM-DDTHH:MM", "do not ask for confirmation yourself"):
            self.assertIn(phrase, RULES)

    def test_stamp_uses_the_persons_local_date_and_weekday(self):
        now = datetime(2026, 11, 11, 23, 30, tzinfo=UTC)  # already Thursday 12 Nov in Lagos
        stamped = stamp_user_message("Lunch with Bo", now=now, tz=LAGOS)
        self.assertEqual(stamped, "[Sent 2026-11-12T00:30 Thursday, Africa/Lagos]\nLunch with Bo")

    def test_stamp_cleans_and_limits_the_text(self):
        now = datetime(2026, 11, 11, 10, 0, tzinfo=UTC)
        self.assertTrue(stamp_user_message("a\x00b", now=now, tz=LAGOS).endswith("\nab"))
        with self.assertRaises(ValueError):
            stamp_user_message("x" * (MAX_USER_MESSAGE_CHARS + 1), now=now, tz=LAGOS)
        with self.assertRaises(ValueError):
            stamp_user_message("   ", now=now, tz=LAGOS)


class BriefingDueTests(TestCase):
    def due(self, hour, minute=0, **kw):
        # Wednesday 11 Nov 2026, Lagos (UTC+1)
        now = datetime(2026, 11, 11, hour, minute, tzinfo=UTC)
        defaults = dict(now=now, tz=LAGOS, send_at=time(7, 30), last_sent=None)
        defaults.update(kw)
        return is_briefing_due(**defaults)

    def test_not_before_the_time(self):
        self.assertFalse(self.due(6, 29))   # 07:29 local

    def test_due_from_the_time_until_the_cutoff(self):
        self.assertTrue(self.due(6, 30))    # 07:30 local exactly
        self.assertTrue(self.due(8, 0))     # a missed tick: still sent
        self.assertTrue(self.due(9, 29))
        self.assertFalse(self.due(9, 30))   # three hours late: too late to be useful

    def test_only_once_per_local_day(self):
        self.assertFalse(self.due(7, 0, last_sent=date(2026, 11, 11)))
        self.assertTrue(self.due(7, 0, last_sent=date(2026, 11, 10)))

    def test_uses_the_persons_day_not_utc(self):
        # 23:45 UTC on the 11th is 00:45 on the 12th in Lagos: yesterday's briefing does not count as today's.
        now = datetime(2026, 11, 11, 23, 45, tzinfo=UTC)
        self.assertFalse(is_briefing_due(now=now, tz=LAGOS, send_at=time(0, 30), last_sent=date(2026, 11, 12)))
        self.assertTrue(is_briefing_due(now=now, tz=LAGOS, send_at=time(0, 30), last_sent=date(2026, 11, 11)))

    def test_daylight_saving_day_still_sends_at_local_time(self):
        # Sunday 8 March 2026, New York: 07:30 local is 11:30 UTC (clocks already moved).
        before = datetime(2026, 3, 8, 11, 29, tzinfo=UTC)
        after = datetime(2026, 3, 8, 11, 31, tzinfo=UTC)
        self.assertFalse(is_briefing_due(now=before, tz=NY, send_at=time(7, 30), last_sent=None))
        self.assertTrue(is_briefing_due(now=after, tz=NY, send_at=time(7, 30), last_sent=None))


class ReminderTests(TestCase):
    NOW = datetime(2026, 11, 11, 10, 0, tzinfo=UTC)

    def candidate(self, start_in_minutes, minutes_before=15, id="e1"):
        return ReminderCandidate(id, "Standup", self.NOW + timedelta(minutes=start_in_minutes), minutes_before)

    def test_due_when_the_reminder_time_has_arrived(self):
        due = due_reminders([self.candidate(10)], now=self.NOW)  # starts in 10, reminds 15 before: 5 minutes ago
        self.assertEqual(len(due), 1)

    def test_not_yet_due(self):
        self.assertEqual(due_reminders([self.candidate(30)], now=self.NOW), [])  # fires in 15 minutes

    def test_old_reminders_are_not_replayed_after_downtime(self):
        self.assertEqual(due_reminders([self.candidate(-5)], now=self.NOW), [])   # already started
        self.assertEqual(due_reminders([self.candidate(1, minutes_before=60)], now=self.NOW), [])  # fired 59 minutes ago

    def test_key_identifies_the_occurrence(self):
        one = due_reminders([self.candidate(10)], now=self.NOW)[0]
        again = due_reminders([self.candidate(10)], now=self.NOW + timedelta(minutes=1))[0]
        other_day = due_reminders([self.candidate(10 + 24 * 60 - 1 + 1)], now=self.NOW + timedelta(days=1))[0]
        self.assertEqual(one.key, again.key)        # same occurrence: the database will refuse a second send
        self.assertNotEqual(one.key, other_day.key)  # the next occurrence of a repeating event is a new key


class RenderBriefingTests(TestCase):
    def test_empty_day(self):
        self.assertEqual(render_briefing(events=[], ranked=[], tz=LAGOS), ("Good morning", "Nothing scheduled today. A clear day."))

    def test_events_and_top_tasks(self):
        now = datetime(2026, 11, 11, 6, 0, tzinfo=UTC)
        tasks = [PlannableTask("a", "Pay rent", 4), PlannableTask("b", "Email Bo", 2), PlannableTask("c", "Read", 1),
                 PlannableTask("d", "Water plants", 1)]
        ranked = rank_tasks(tasks, now=now, tz=LAGOS)
        events = [(datetime(2026, 11, 11, 13, 0, tzinfo=UTC), datetime(2026, 11, 11, 14, 0, tzinfo=UTC), "Design review"),
                  (datetime(2026, 11, 11, 8, 0, tzinfo=UTC), datetime(2026, 11, 11, 8, 15, tzinfo=UTC), "Standup")]
        title, body = render_briefing(events=events, ranked=ranked, tz=LAGOS)
        self.assertEqual(title, "Today: 2 events, 4 open tasks")
        self.assertEqual(body, "09:00 Standup; 14:00 Design review. First: Pay rent, Email Bo, Read")

    def test_singular_nouns(self):
        ranked = rank_tasks([PlannableTask("a", "Pay rent", 4)], now=datetime(2026, 11, 11, tzinfo=UTC), tz=LAGOS)
        title, _ = render_briefing(events=[(datetime(2026, 11, 11, 8, tzinfo=UTC), datetime(2026, 11, 11, 9, tzinfo=UTC), "Call")],
                                   ranked=ranked, tz=LAGOS)
        self.assertEqual(title, "Today: 1 event, 1 open task")

    def test_long_bodies_are_shortened(self):
        ranked = rank_tasks([PlannableTask("a", "x" * 400, 4)], now=datetime(2026, 11, 11, tzinfo=UTC), tz=LAGOS)
        _, body = render_briefing(events=[], ranked=ranked, tz=LAGOS)
        self.assertLessEqual(len(body), 240)
        self.assertTrue(body.endswith("…"))
