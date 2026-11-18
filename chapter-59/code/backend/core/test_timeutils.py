"""Tests for core.timeutils. Plain unittest, no Django needed."""
from datetime import date, datetime, timedelta
from unittest import TestCase

from core.timeutils import (
    UTC, TimeInputError, describe_local, format_local, get_zone, local_day_bounds,
    parse_local_date, parse_local_datetime, resolve_local, to_local,
)

NY = get_zone("America/New_York")
LAGOS = get_zone("Africa/Lagos")


class ParsingTests(TestCase):
    def test_accepts_local_datetime_with_and_without_seconds(self):
        self.assertEqual(parse_local_datetime("2026-11-12T15:00"), datetime(2026, 11, 12, 15, 0))
        self.assertEqual(parse_local_datetime(" 2026-11-12T15:00:30 "), datetime(2026, 11, 12, 15, 0, 30))

    def test_rejects_offsets_and_z(self):
        for bad in ("2026-11-12T15:00Z", "2026-11-12T15:00+01:00", "2026-11-12 15:00", "tomorrow 3pm", ""):
            with self.assertRaises(TimeInputError, msg=bad):
                parse_local_datetime(bad)

    def test_rejects_impossible_dates(self):
        with self.assertRaises(TimeInputError):
            parse_local_datetime("2026-13-40T25:61")
        with self.assertRaises(TimeInputError):
            parse_local_date("2026-02-30")

    def test_rejects_non_strings(self):
        with self.assertRaises(TimeInputError):
            parse_local_datetime(None)  # type: ignore[arg-type]

    def test_parse_local_date(self):
        self.assertEqual(parse_local_date("2026-11-12"), date(2026, 11, 12))
        with self.assertRaises(TimeInputError):
            parse_local_date("12/11/2026")

    def test_get_zone(self):
        self.assertEqual(str(get_zone("Africa/Lagos")), "Africa/Lagos")
        for bad in ("Mars/Olympus", "", "../etc/passwd", "x" * 100, None):
            with self.assertRaises(TimeInputError, msg=repr(bad)):
                get_zone(bad)  # type: ignore[arg-type]


class ResolveLocalTests(TestCase):
    def test_normal_time(self):
        result = resolve_local(datetime(2026, 11, 12, 15, 0), LAGOS)  # Lagos is UTC+1 all year
        self.assertEqual(result.utc, datetime(2026, 11, 12, 14, 0, tzinfo=UTC))
        self.assertFalse(result.shifted or result.ambiguous)

    def test_same_wall_time_has_different_utc_in_winter_and_summer(self):
        winter = resolve_local(datetime(2026, 1, 15, 9, 0), NY).utc
        summer = resolve_local(datetime(2026, 7, 15, 9, 0), NY).utc
        self.assertEqual(winter.hour, 14)  # UTC-5
        self.assertEqual(summer.hour, 13)  # UTC-4

    def test_spring_forward_gap_is_shifted_not_rejected(self):
        # 2026-03-08 02:30 does not exist in New York: clocks jump from 02:00 to 03:00.
        result = resolve_local(datetime(2026, 3, 8, 2, 30), NY)
        self.assertTrue(result.shifted)
        self.assertFalse(result.ambiguous)
        self.assertEqual(to_local(result.utc, NY).replace(tzinfo=None), datetime(2026, 3, 8, 3, 30))

    def test_fall_back_fold_uses_first_occurrence(self):
        # 2026-11-01 01:30 happens twice in New York.
        result = resolve_local(datetime(2026, 11, 1, 1, 30), NY)
        self.assertTrue(result.ambiguous)
        self.assertFalse(result.shifted)
        self.assertEqual(result.utc, datetime(2026, 11, 1, 5, 30, tzinfo=UTC))  # EDT, UTC-4: the first one

    def test_times_next_to_the_transition_are_normal(self):
        for naive in (datetime(2026, 3, 8, 1, 59), datetime(2026, 3, 8, 3, 0), datetime(2026, 11, 1, 2, 0)):
            result = resolve_local(naive, NY)
            self.assertFalse(result.shifted or result.ambiguous, msg=str(naive))

    def test_rejects_aware_input(self):
        with self.assertRaises(TimeInputError):
            resolve_local(datetime(2026, 1, 1, tzinfo=UTC), NY)


class DayBoundsTests(TestCase):
    def test_normal_day_is_24_hours(self):
        start, end = local_day_bounds(date(2026, 11, 12), LAGOS)
        self.assertEqual(end - start, timedelta(hours=24))
        self.assertEqual(start, datetime(2026, 11, 11, 23, 0, tzinfo=UTC))

    def test_dst_days_are_23_and_25_hours(self):
        spring = local_day_bounds(date(2026, 3, 8), NY)
        autumn = local_day_bounds(date(2026, 11, 1), NY)
        self.assertEqual(spring[1] - spring[0], timedelta(hours=23))
        self.assertEqual(autumn[1] - autumn[0], timedelta(hours=25))


class FormattingTests(TestCase):
    def test_format_round_trips_through_parse(self):
        moment = datetime(2026, 11, 12, 14, 0, tzinfo=UTC)
        text = format_local(moment, LAGOS)
        self.assertEqual(text, "2026-11-12T15:00")
        self.assertEqual(resolve_local(parse_local_datetime(text), LAGOS).utc, moment)

    def test_describe_local(self):
        self.assertEqual(describe_local(datetime(2026, 11, 12, 14, 0, tzinfo=UTC), LAGOS), "Thu 12 Nov 2026, 15:00")

    def test_to_local_rejects_naive(self):
        with self.assertRaises(TimeInputError):
            to_local(datetime(2026, 1, 1), NY)
