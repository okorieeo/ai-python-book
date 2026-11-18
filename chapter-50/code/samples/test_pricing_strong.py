"""The same function, tested at the boundaries where bugs live."""
import unittest

from samples import pricing


class StrongTests(unittest.TestCase):
    def test_coupon_values(self):
        for cents, pct, want in ((1000, 0, 1000), (1000, 10, 900), (1000, 100, 0), (999, 50, 500)):
            self.assertEqual(pricing.apply_coupon(cents, pct), want, (cents, pct))

    def test_coupon_range_is_enforced_at_both_ends(self):
        for bad in (-1, 101):
            with self.assertRaises(ValueError):
                pricing.apply_coupon(1000, bad)
        pricing.apply_coupon(1000, 0)
        pricing.apply_coupon(1000, 100)

    def test_free_shipping_boundary(self):
        self.assertEqual(pricing.shipping(4999), 499)
        self.assertEqual(pricing.shipping(5000), 0)
        self.assertEqual(pricing.shipping(5001), 0)

    def test_order_total_adds_shipping_to_the_discounted_price(self):
        self.assertEqual(pricing.order_total(10000, 10), 9000)      # 9000 qualifies for free shipping
        self.assertEqual(pricing.order_total(5000, 10), 4500 + 499)  # 4500 does not


if __name__ == "__main__":
    unittest.main()
