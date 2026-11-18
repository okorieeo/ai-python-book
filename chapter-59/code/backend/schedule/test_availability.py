"""Tests for schedule.availability. Plain unittest, no Django needed."""
from datetime import datetime, time, timedelta
from unittest import TestCase

from core.timeutils import UTC, get_zone
from schedule.availability import (
    Interval, WorkingHours, find_conflicts, free_slots, merge_intervals, overlaps,
)

LAGOS = get_zone("Africa/Lagos")  # UTC+1 all year, so 09:00 local is 08:00 UTC
NY = get_zone("America/New_York")
MIN = timedelta(minutes=1)


def at(day, hour, minute=0):
    """A UTC moment on 2026-11-<day>."""
    return datetime(2026, 11, day, hour, minute, tzinfo=UTC)


def iv(day, h1, h2, m1=0, m2=0):
    return Interval(at(day, h1, m1), at(day, h2, m2))


def hhmm(slot):
    return (slot.start.strftime("%d %H:%M"), slot.end.strftime("%d %H:%M"))


class IntervalTests(TestCase):
    def test_invalid_intervals(self):
        with self.assertRaises(ValueError):
            Interval(at(1, 10), at(1, 10))
        with self.assertRaises(ValueError):
            Interval(datetime(2026, 1, 1), datetime(2026, 1, 2))

    def test_touching_is_not_overlapping(self):
        self.assertFalse(overlaps(iv(2, 9, 10), iv(2, 10, 11)))
        self.assertTrue(overlaps(iv(2, 9, 10, 0, 1), iv(2, 10, 11)))

    def test_containment_and_identical(self):
        self.assertTrue(overlaps(iv(2, 9, 17), iv(2, 12, 13)))
        self.assertTrue(overlaps(iv(2, 9, 10), iv(2, 9, 10)))

    def test_find_conflicts_sorted(self):
        busy = [iv(2, 14, 15), iv(2, 9, 10), iv(2, 20, 21)]
        found = find_conflicts(iv(2, 9, 15), busy)
        self.assertEqual([hhmm(f)[0] for f in found], ["02 09:00", "02 14:00"])

    def test_merge(self):
        merged = merge_intervals([iv(2, 9, 11), iv(2, 10, 12), iv(2, 12, 13), iv(2, 15, 16)])
        self.assertEqual([hhmm(m) for m in merged], [("02 09:00", "02 13:00"), ("02 15:00", "02 16:00")])


class WorkingHoursTests(TestCase):
    def test_rejects_backwards_hours(self):
        with self.assertRaises(ValueError):
            WorkingHours(time(17, 0), time(9, 0))


class FreeSlotTests(TestCase):
    # Monday 2 Nov 2026 in Lagos: working hours 09:00 to 17:00 local = 08:00 to 16:00 UTC
    def slots(self, busy, **kw):
        defaults = dict(window_start=at(2, 0), window_end=at(3, 0), duration=timedelta(minutes=30), tz=LAGOS)
        defaults.update(kw)
        return free_slots(busy, **defaults)

    def test_empty_day_is_the_whole_working_window(self):
        self.assertEqual([hhmm(s) for s in self.slots([])], [("02 08:00", "02 16:00")])

    def test_busy_block_splits_the_day(self):
        result = self.slots([iv(2, 10, 11)])
        self.assertEqual([hhmm(s) for s in result], [("02 08:00", "02 10:00"), ("02 11:00", "02 16:00")])

    def test_back_to_back_meetings_leave_no_gap(self):
        result = self.slots([iv(2, 8, 12), iv(2, 12, 16)])
        self.assertEqual(result, [])

    def test_gap_shorter_than_duration_is_not_offered(self):
        result = self.slots([iv(2, 8, 10), iv(2, 10, 15, 20, 0)], duration=timedelta(minutes=30))
        self.assertEqual([hhmm(s) for s in result], [("02 15:00", "02 16:00")])

    def test_overlapping_busy_blocks_are_merged(self):
        result = self.slots([iv(2, 9, 11), iv(2, 10, 12)])
        self.assertEqual([hhmm(s) for s in result], [("02 08:00", "02 09:00"), ("02 12:00", "02 16:00")])

    def test_buffer_keeps_a_margin(self):
        result = self.slots([iv(2, 10, 11)], buffer=timedelta(minutes=15))
        self.assertEqual([hhmm(s) for s in result], [("02 08:00", "02 09:45"), ("02 11:15", "02 16:00")])

    def test_window_start_hides_the_past(self):
        result = self.slots([], window_start=at(2, 11, 20))
        self.assertEqual([hhmm(s) for s in result], [("02 11:20", "02 16:00")])

    def test_weekends_are_skipped(self):
        # Saturday 7 Nov to Monday 9 Nov
        result = self.slots([], window_start=at(7, 0), window_end=at(10, 0))
        self.assertEqual([hhmm(s)[0] for s in result], ["09 08:00"])

    def test_custom_working_days_and_hours(self):
        hours = WorkingHours(time(10, 0), time(12, 0), frozenset({5}))  # Saturdays 10:00-12:00
        result = self.slots([], window_start=at(7, 0), window_end=at(8, 0), hours=hours)
        self.assertEqual([hhmm(s) for s in result], [("07 09:00", "07 11:00")])

    def test_duration_longer_than_any_gap(self):
        self.assertEqual(self.slots([iv(2, 12, 13)], duration=timedelta(hours=5)), [])

    def test_busy_block_spilling_over_working_hours(self):
        result = self.slots([Interval(at(2, 15), at(3, 3))])
        self.assertEqual([hhmm(s) for s in result], [("02 08:00", "02 15:00")])

    def test_multi_day_search(self):
        result = self.slots([iv(2, 8, 16)], window_end=at(4, 0))
        self.assertEqual([hhmm(s) for s in result], [("03 08:00", "03 16:00")])

    def test_dst_day_in_new_york(self):
        # Sunday 8 March 2026 is the spring change; use Monday 9 March: 09:00 local = 13:00 UTC (EDT).
        result = free_slots([], window_start=datetime(2026, 3, 9, 0, 0, tzinfo=UTC),
                            window_end=datetime(2026, 3, 10, 0, 0, tzinfo=UTC),
                            duration=timedelta(hours=1), tz=NY)
        self.assertEqual(result[0].start, datetime(2026, 3, 9, 13, 0, tzinfo=UTC))

    def test_bad_arguments(self):
        with self.assertRaises(ValueError):
            self.slots([], duration=timedelta(0))
        with self.assertRaises(ValueError):
            self.slots([], window_end=at(1, 0))
        with self.assertRaises(ValueError):
            free_slots([], window_start=at(1, 0), window_end=at(1, 0) + timedelta(days=90),
                       duration=timedelta(hours=1), tz=LAGOS)
