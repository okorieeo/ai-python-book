"""Tests for schedule.recurrence. Plain unittest, no Django needed."""
from datetime import date, datetime, timedelta
from unittest import TestCase

from core.timeutils import UTC, get_zone, to_local
from schedule.recurrence import RuleError, expand, parse_rule

NY = get_zone("America/New_York")
LAGOS = get_zone("Africa/Lagos")
HOUR = timedelta(hours=1)


def utc(*args):
    return datetime(*args, tzinfo=UTC)


def run(rule, first_start, *, tz=LAGOS, duration=HOUR, start=utc(2026, 1, 1), end=utc(2027, 1, 1), **kw):
    return expand(parse_rule(rule), first_start=first_start, duration=duration, tz=tz,
                  window_start=start, window_end=end, **kw)


def local_dates(occurrences):
    return [o.local_date for o in occurrences]


class ParseRuleTests(TestCase):
    def test_valid_rule(self):
        rule = parse_rule({"freq": "weekly", "interval": 2, "by_weekday": ["WE", "MO"], "until": "2026-12-31",
                           "exclude": ["2026-11-25"]})
        self.assertEqual(rule.by_weekday, ("MO", "WE"))  # normalised to week order
        self.assertEqual(rule.until, date(2026, 12, 31))
        self.assertEqual(rule.exclude, frozenset({date(2026, 11, 25)}))

    def test_rejects_bad_input(self):
        bad_rules = [
            "daily", {}, {"freq": "hourly"}, {"freq": "daily", "interval": 0}, {"freq": "daily", "interval": True},
            {"freq": "daily", "interval": 1.5}, {"freq": "daily", "interval": 400},
            {"freq": "daily", "by_weekday": ["MO"]}, {"freq": "weekly", "by_weekday": ["XX"]},
            {"freq": "daily", "until": "2026-12-31", "count": 3}, {"freq": "daily", "count": 0},
            {"freq": "daily", "count": 5000}, {"freq": "daily", "until": "31/12/2026"},
            {"freq": "daily", "exclude": ["nope"]}, {"freq": "daily", "exclude": ["2026-01-01"] * 201},
            {"freq": "daily", "surprise": 1},
        ]
        for bad in bad_rules:
            with self.assertRaises(RuleError, msg=repr(bad)):
                parse_rule(bad)


class ExpansionTests(TestCase):
    def test_daily(self):
        occ = run({"freq": "daily"}, datetime(2026, 11, 1, 9, 0), start=utc(2026, 11, 3), end=utc(2026, 11, 6))
        self.assertEqual(local_dates(occ), [date(2026, 11, 3), date(2026, 11, 4), date(2026, 11, 5)])
        self.assertEqual(occ[0].start, utc(2026, 11, 3, 8, 0))  # 09:00 in Lagos is 08:00 UTC

    def test_interval(self):
        occ = run({"freq": "daily", "interval": 3}, datetime(2026, 11, 1, 9, 0), end=utc(2026, 11, 12))
        self.assertEqual([d.day for d in local_dates(occ)], [1, 4, 7, 10])

    def test_weekly_defaults_to_the_start_weekday(self):
        occ = run({"freq": "weekly"}, datetime(2026, 11, 12, 9, 0), end=utc(2026, 12, 4))  # a Thursday
        self.assertEqual([d.day for d in local_dates(occ)], [12, 19, 26, 3])
        self.assertTrue(all(d.weekday() == 3 for d in local_dates(occ)))

    def test_weekly_several_days_never_before_the_start(self):
        # Start on Wednesday 11 Nov: the Monday of that week (9 Nov) must not appear.
        occ = run({"freq": "weekly", "by_weekday": ["MO", "WE", "FR"]}, datetime(2026, 11, 11, 9, 0),
                  end=utc(2026, 11, 20))
        self.assertEqual([d.day for d in local_dates(occ)], [11, 13, 16, 18])

    def test_weekly_every_second_week(self):
        occ = run({"freq": "weekly", "interval": 2, "by_weekday": ["MO"]}, datetime(2026, 11, 2, 9, 0),
                  end=utc(2026, 12, 8))
        self.assertEqual([d.day for d in local_dates(occ)], [2, 16, 30])

    def test_monthly_skips_months_without_that_day(self):
        occ = run({"freq": "monthly"}, datetime(2026, 1, 31, 9, 0), end=utc(2026, 8, 1))
        self.assertEqual([d.month for d in local_dates(occ)], [1, 3, 5, 7])  # not Feb, Apr, Jun

    def test_yearly_leap_day(self):
        occ = run({"freq": "yearly"}, datetime(2024, 2, 29, 9, 0), start=utc(2024, 1, 1), end=utc(2033, 1, 1))
        self.assertEqual([d.year for d in local_dates(occ)], [2024, 2028, 2032])

    def test_count_and_until(self):
        occ = run({"freq": "daily", "count": 3}, datetime(2026, 11, 1, 9, 0))
        self.assertEqual(len(occ), 3)
        occ = run({"freq": "daily", "until": "2026-11-03"}, datetime(2026, 11, 1, 9, 0))
        self.assertEqual([d.day for d in local_dates(occ)], [1, 2, 3])  # until is inclusive

    def test_exclude_removes_a_day_but_count_still_counts_it(self):
        rule = {"freq": "daily", "count": 4, "exclude": ["2026-11-02"]}
        occ = run(rule, datetime(2026, 11, 1, 9, 0))
        self.assertEqual([d.day for d in local_dates(occ)], [1, 3, 4])

    def test_window_includes_occurrences_that_overlap_it(self):
        # 23:30 to 00:30 across the window start still counts as inside the window.
        occ = run({"freq": "daily"}, datetime(2026, 11, 1, 23, 30), tz=LAGOS, duration=HOUR,
                  start=utc(2026, 11, 3, 22, 45), end=utc(2026, 11, 4, 12, 0))
        self.assertEqual(local_dates(occ)[0], date(2026, 11, 3))

    def test_window_end_is_exclusive_and_over_events_are_skipped(self):
        occ = run({"freq": "daily"}, datetime(2026, 11, 1, 9, 0), start=utc(2026, 11, 2, 8, 0), end=utc(2026, 11, 3, 8, 0))
        # the 2 Nov event ends at 09:00 UTC, after the window starts; the 3 Nov event starts exactly at the end
        self.assertEqual([d.day for d in local_dates(occ)], [2])

    def test_end_before_start_is_rejected(self):
        with self.assertRaises(RuleError):
            run({"freq": "daily"}, datetime(2026, 11, 1, 9, 0), start=utc(2026, 11, 2), end=utc(2026, 11, 1))


class DaylightSavingTests(TestCase):
    def test_wall_clock_time_is_kept_across_the_spring_change(self):
        # A weekly 09:00 meeting in New York. Clocks go forward on Sunday 8 March 2026.
        occ = run({"freq": "weekly", "by_weekday": ["MO"]}, datetime(2026, 3, 2, 9, 0), tz=NY,
                  start=utc(2026, 3, 1), end=utc(2026, 3, 20))
        self.assertEqual([o.start.hour for o in occ], [14, 13, 13])  # 14:00Z before the change, 13:00Z after
        self.assertTrue(all(to_local(o.start, NY).hour == 9 for o in occ))

    def test_a_time_inside_the_gap_moves_forward(self):
        occ = run({"freq": "daily"}, datetime(2026, 3, 7, 2, 30), tz=NY, start=utc(2026, 3, 7), end=utc(2026, 3, 10))
        local = [to_local(o.start, NY).strftime("%d %H:%M") for o in occ]
        self.assertEqual(local, ["07 02:30", "08 03:30", "09 02:30"])  # only 8 March moved

    def test_lagos_never_changes(self):
        occ = run({"freq": "weekly"}, datetime(2026, 1, 5, 9, 0), tz=LAGOS, end=utc(2026, 12, 31))
        self.assertEqual({o.start.hour for o in occ}, {8})


class SafetyTests(TestCase):
    def test_scan_limit_protects_against_expensive_rules(self):
        with self.assertRaises(RuleError):
            # Day 31 in a window far in the future with a tiny scan limit.
            run({"freq": "monthly"}, datetime(2026, 1, 31, 9, 0), start=utc(2030, 1, 1), end=utc(2030, 2, 1), max_scan=10)

    def test_occurrence_limit(self):
        with self.assertRaises(RuleError):
            run({"freq": "daily"}, datetime(2026, 1, 1, 9, 0), limit=5)

    def test_unbounded_rule_is_fine_when_the_window_is_small(self):
        occ = run({"freq": "daily"}, datetime(2020, 1, 1, 9, 0), start=utc(2026, 11, 1), end=utc(2026, 11, 8))
        self.assertEqual(len(occ), 7)
