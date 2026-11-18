import os
import time
import unittest
from datetime import datetime, timedelta, timezone

from museum.impl import load

impl = load("museum.bug1_timezone")


class ExpiryTests(unittest.TestCase):
    def setUp(self):
        self._tz = os.environ.get("TZ")

    def tearDown(self):
        if self._tz is None:
            os.environ.pop("TZ", None)
        else:
            os.environ["TZ"] = self._tz
        time.tzset()

    def in_zone(self, zone):
        os.environ["TZ"] = zone
        time.tzset()

    def test_future_link_is_active_on_a_utc_server(self):
        self.in_zone("UTC")
        self.assertFalse(impl.is_expired(datetime.now(timezone.utc) + timedelta(hours=1)))

    def test_future_link_is_active_on_a_laptop_in_tokyo(self):      # the regression test
        self.in_zone("Asia/Tokyo")
        self.assertFalse(impl.is_expired(datetime.now(timezone.utc) + timedelta(hours=1)))

    def test_past_link_is_expired_in_new_york(self):
        self.in_zone("America/New_York")
        self.assertTrue(impl.is_expired(datetime.now(timezone.utc) - timedelta(hours=1)))

    def test_a_naive_datetime_is_rejected_loudly(self):
        if impl.__name__.endswith("fixed"):
            with self.assertRaises(ValueError):
                impl.is_expired(datetime(2026, 1, 1))


if __name__ == "__main__":
    unittest.main()
