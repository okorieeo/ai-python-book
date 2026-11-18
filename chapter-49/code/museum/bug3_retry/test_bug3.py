import unittest

from museum.bug3_retry.support import FakeMailer, FlakyStore, run_with_retries
from museum.impl import load

impl = load("museum.bug3_retry", ("buggy", "fixed"))


class ReceiptTests(unittest.TestCase):
    def test_a_retried_task_sends_exactly_one_email(self):     # regression test
        mailer, store = FakeMailer(), FlakyStore()
        run_with_retries(impl.send_receipt, 1001, mailer, store)
        self.assertEqual(mailer.deliveries, [1001])

    def test_running_the_task_again_later_sends_nothing_more(self):
        mailer, store = FakeMailer(), FlakyStore()
        run_with_retries(impl.send_receipt, 1001, mailer, store)
        run_with_retries(impl.send_receipt, 1001, mailer, store)
        self.assertEqual(mailer.deliveries, [1001])


if __name__ == "__main__":
    unittest.main()
