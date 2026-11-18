"""The kind of test an AI writes when asked to "add tests": plausible, passes, protects very little."""
import unittest

from samples import pricing


class WeakTests(unittest.TestCase):
    def test_coupon_reduces_price(self):
        self.assertEqual(pricing.apply_coupon(1000, 10), 900)

    def test_shipping_is_charged_on_small_orders(self):
        self.assertEqual(pricing.shipping(1000), 499)

    def test_order_total_runs(self):
        self.assertTrue(pricing.order_total(10000, 10) > 0)


if __name__ == "__main__":
    unittest.main()
