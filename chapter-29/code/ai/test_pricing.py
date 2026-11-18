import unittest

from .pricing import DEFAULT_PRICES, cost_micro_usd, cost_or_none, format_usd
from .dto import Usage

SONNET = DEFAULT_PRICES["claude-sonnet-5-5"]
HAIKU = DEFAULT_PRICES["claude-haiku-5-5"]


class CostTests(unittest.TestCase):
    def test_one_million_tokens_each_way(self):
        # $2 in + $10 out
        self.assertEqual(cost_micro_usd(Usage(1_000_000, 1_000_000), SONNET), 12_000_000)

    def test_small_call_is_rounded_up_never_down(self):
        # 1 input token at $2/MTok is 0.000002 USD = exactly 2 micro-dollars
        self.assertEqual(cost_micro_usd(Usage(input_tokens=1), SONNET), 2)
        # 1 cache-read token at $0.10/MTok is 0.1 micro-dollar: rounds UP to 1
        self.assertEqual(cost_micro_usd(Usage(cache_read_tokens=1), SONNET), 1)

    def test_zero_usage_costs_nothing(self):
        self.assertEqual(cost_micro_usd(Usage(), SONNET), 0)

    def test_cache_read_is_far_cheaper_than_fresh_input(self):
        fresh = cost_micro_usd(Usage(input_tokens=100_000), SONNET)
        cached = cost_micro_usd(Usage(cache_read_tokens=100_000), SONNET)
        self.assertEqual(fresh, 200_000)
        self.assertEqual(cached, 10_000)

    def test_cache_write_costs_more_than_fresh_input(self):
        self.assertGreater(cost_micro_usd(Usage(cache_write_tokens=1000), SONNET),
                           cost_micro_usd(Usage(input_tokens=1000), SONNET))

    def test_total_input_adds_all_three_input_fields(self):
        self.assertEqual(Usage(10, 5, 20, 30).total_input, 60)

    def test_haiku_switches_to_long_prompt_rates(self):
        short = cost_micro_usd(Usage(input_tokens=100_000, output_tokens=1_000_000), HAIKU)
        long = cost_micro_usd(Usage(input_tokens=100_001, output_tokens=1_000_000), HAIKU)
        self.assertEqual(short, 10_000 + 500_000)
        self.assertEqual(long, 50_001 + 2_500_000)

    def test_long_prompt_counts_cached_tokens_too(self):
        # 150K tokens, all from cache: the PROMPT is long, so the long cache-read rate applies
        self.assertEqual(cost_micro_usd(Usage(cache_read_tokens=150_000), HAIKU), 7_500)

    def test_unknown_model_is_none_not_an_error(self):
        self.assertIsNone(cost_or_none(Usage(10, 10), "claude-mystery-9"))
        self.assertEqual(cost_or_none(Usage(1_000_000), "claude-sonnet-5-5"), 2_000_000)

    def test_an_empty_price_table_means_no_prices_not_defaults(self):
        self.assertIsNone(cost_or_none(Usage(10, 10), "claude-sonnet-5-5", {}))

    def test_usage_addition(self):
        self.assertEqual(Usage(1, 2, 3, 4) + Usage(10, 20, 30, 40), Usage(11, 22, 33, 44))

    def test_format(self):
        self.assertEqual(format_usd(12_345), "$0.0123")


if __name__ == "__main__":
    unittest.main()
