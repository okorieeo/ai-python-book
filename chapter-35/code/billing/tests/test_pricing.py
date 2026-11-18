from datetime import datetime, timezone

from django.test import SimpleTestCase

from billing.pricing import (add_months, format_money, graduated_price, overage_charge, prorate,
                             unit_economics)

UTC = timezone.utc


def d(y, m, day, h=0):
    return datetime(y, m, day, h, tzinfo=UTC)


class MoneyTests(SimpleTestCase):
    def test_format_money(self):
        self.assertEqual(format_money(2900, "USD"), "$29.00")
        self.assertEqual(format_money(750_000, "NGN"), "₦7,500.00")
        self.assertEqual(format_money(5, "USD"), "$0.05")
        self.assertEqual(format_money(-1250, "USD"), "-$12.50")
        self.assertEqual(format_money(123_456_789, "USD"), "$1,234,567.89")

    def test_add_months_clamps_to_the_end_of_the_month(self):
        self.assertEqual(add_months(d(2026, 1, 31), 1), d(2026, 2, 28))
        self.assertEqual(add_months(d(2028, 1, 31), 1), d(2028, 2, 29))  # leap year
        self.assertEqual(add_months(d(2026, 11, 30), 3), d(2027, 2, 28))
        self.assertEqual(add_months(d(2026, 12, 15), 1), d(2027, 1, 15))
        self.assertEqual(add_months(d(2026, 1, 31), 12), d(2027, 1, 31))


class ProrationTests(SimpleTestCase):
    def test_halfway_through_the_period(self):
        start, end = d(2026, 1, 1), d(2026, 1, 31)  # 30 days
        p = prorate(500, 2900, start, end, d(2026, 1, 16))  # exactly half left
        self.assertEqual((p.credit_minor, p.charge_minor, p.net_minor), (250, 1450, 1200))

    def test_change_at_the_start_and_at_the_end(self):
        start, end = d(2026, 1, 1), d(2026, 1, 31)
        full = prorate(500, 2900, start, end, start)
        self.assertEqual((full.credit_minor, full.charge_minor), (500, 2900))
        nothing = prorate(500, 2900, start, end, end)
        self.assertEqual((nothing.credit_minor, nothing.charge_minor, nothing.net_minor), (0, 0, 0))

    def test_rounding_is_half_up_in_integers(self):
        start, end = d(2026, 1, 1), d(2026, 1, 4)  # 3 days
        p = prorate(100, 100, start, end, d(2026, 1, 2))  # 2/3 left: 66.67 -> 67
        self.assertEqual(p.credit_minor, 67)

    def test_a_bad_period_is_refused(self):
        with self.assertRaises(ValueError):
            prorate(1, 1, d(2026, 1, 2), d(2026, 1, 2), d(2026, 1, 2))


class UsagePricingTests(SimpleTestCase):
    def test_overage_charges_per_started_block(self):
        self.assertEqual(overage_charge(1500, 1500, 100, 150), (0, 0))
        self.assertEqual(overage_charge(1501, 1500, 100, 150), (1, 150))
        self.assertEqual(overage_charge(1600, 1500, 100, 150), (1, 150))
        self.assertEqual(overage_charge(1650, 1500, 100, 150), (2, 300))

    def test_no_allowance_or_no_price_means_no_overage(self):
        self.assertEqual(overage_charge(99999, None, 100, 150), (0, 0))
        self.assertEqual(overage_charge(99999, 10, None, None), (0, 0))

    def test_graduated_tiers(self):
        tiers = [(1000, 10), (9000, 8), (None, 5)]  # first 1,000 at 10; next 9,000 at 8; the rest at 5
        self.assertEqual(graduated_price(500, tiers), 5_000)
        self.assertEqual(graduated_price(1000, tiers), 10_000)
        self.assertEqual(graduated_price(2000, tiers), 10_000 + 1000 * 8)
        self.assertEqual(graduated_price(12_000, tiers), 10_000 + 9000 * 8 + 2000 * 5)
        self.assertEqual(graduated_price(0, tiers), 0)


class EconomicsTests(SimpleTestCase):
    def test_margin_after_fees_and_ai_cost(self):
        # $29.00 plan, 2.9% + 30 cents in fees (example numbers), $16.275 of AI cost
        e = unit_economics(price_minor=2900, cost_micro_usd=16_275_000, fee_bps=290, fixed_fee_minor=30)
        self.assertEqual(e["revenue_micro"], 29_000_000)
        self.assertEqual(e["fees_micro"], (2900 * 290 // 10_000 + 30) * 10_000)
        self.assertEqual(e["profit_micro"], e["revenue_micro"] - e["fees_micro"] - 16_275_000)
        self.assertAlmostEqual(e["margin"], e["profit_micro"] / 29_000_000)

    def test_free_plan_has_no_margin_to_divide(self):
        e = unit_economics(price_minor=0, cost_micro_usd=16_000)
        self.assertEqual(e["margin"], 0.0)
        self.assertEqual(e["profit_micro"], -16_000)
