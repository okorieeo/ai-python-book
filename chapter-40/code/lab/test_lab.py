"""The bug-hunt lab. Run against the buggy code:   python -m unittest lab.test_lab -v
Run against the solutions (to check yours):      LAB_PACKAGE=lab.solutions python -m unittest lab.test_lab -v"""
import asyncio
import importlib
import os
import threading
import unittest
from datetime import datetime, timedelta, timezone

PKG = os.environ.get("LAB_PACKAGE", "lab.bugs")


def load(name):
    return importlib.import_module(f"{PKG}.{name}")


class Bug1ForgottenAwait(unittest.TestCase):
    def test_message_is_stored(self):
        m, store = load("bug1_forgotten_await"), []
        count = asyncio.run(m.handle(store, "hello"))
        self.assertEqual(store, ["hello"])
        self.assertEqual(count, 1)


class Bug2SharedDefault(unittest.TestCase):
    def test_requests_do_not_share_tags(self):
        m = load("bug2_shared_default")
        self.assertEqual(m.add_tag("a"), ["a"])
        self.assertEqual(m.add_tag("b"), ["b"])
        mine = ["x"]
        self.assertEqual(m.add_tag("y", mine), ["x", "y"])


class Bug3NaiveTime(unittest.TestCase):
    def test_active_and_expired_with_aware_datetimes(self):
        m = load("bug3_naive_time")
        now = datetime(2026, 11, 6, 12, 0, tzinfo=timezone.utc)
        self.assertTrue(m.is_trial_active(now - timedelta(days=13), now))
        self.assertFalse(m.is_trial_active(now - timedelta(days=14), now))

    def test_default_now_works_with_aware_start(self):
        m = load("bug3_naive_time")
        self.assertTrue(m.is_trial_active(datetime.now(timezone.utc) - timedelta(days=1)))


class Bug4NPlusOne(unittest.TestCase):
    def test_correct_and_few_queries(self):
        m = load("bug4_n_plus_one")
        from lab.bugs.bug4_n_plus_one import FakeDB
        convs = [{"id": i} for i in range(1, 51)]
        msgs = [{"conversation_id": i, "text": f"first {i}"} for i in range(1, 51)] + [{"conversation_id": 7, "text": "last 7"}]
        db = FakeDB(convs, msgs)
        result = m.last_message_per_conversation(db)
        self.assertEqual(result[7], "last 7")
        self.assertEqual(result[8], "first 8")
        self.assertLessEqual(len(db.queries), 2, f"{len(db.queries)} queries for 50 conversations")


class Bug5Race(unittest.TestCase):
    def test_two_simultaneous_spends_cannot_overdraw(self):
        m = load("bug5_race")
        barrier = threading.Barrier(2)

        def pause():
            try:
                barrier.wait(timeout=0.3)
            except threading.BrokenBarrierError:
                pass

        wallet, results = m.Wallet(100, pause), []
        threads = [threading.Thread(target=lambda: results.append(wallet.spend(80))) for _ in range(2)]
        [t.start() for t in threads]
        [t.join() for t in threads]
        self.assertGreaterEqual(wallet.balance, 0, f"balance went to {wallet.balance}")
        self.assertEqual(sorted(results), [False, True])


if __name__ == "__main__":
    unittest.main()
