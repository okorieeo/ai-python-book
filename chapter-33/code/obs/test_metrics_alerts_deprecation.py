import io
import unittest
from contextlib import redirect_stdout
from datetime import date

from . import deprecation
from .alerts import AlertState, Rule, default_rules, evaluate
from .metrics import WindowMetrics, summarize_window


def row(**kw):
    base = dict(status="complete", first_token_ms=800, total_ms=4000, input_tokens=1000, cache_read_tokens=0,
                cache_write_tokens=0, cost_micro_usd=500, rating=None)
    base.update(kw)
    return base


class MetricsTests(unittest.TestCase):
    def test_empty_window(self):
        self.assertEqual(summarize_window([]).n, 0)

    def test_rates(self):
        rows = [row()] * 6 + [row(status="failed")] + [row(status="interrupted")] + [row(status="refused")] + [row(status="truncated")]
        m = summarize_window(rows)
        self.assertEqual(m.n, 10)
        self.assertAlmostEqual(m.error_rate, 0.2)
        self.assertEqual((round(m.interrupted_rate, 2), round(m.refusal_rate, 2), round(m.truncation_rate, 2)), (0.1, 0.1, 0.1))

    def test_latency_percentiles_ignore_missing_first_tokens(self):
        rows = [row(first_token_ms=v) for v in (100, 200, 300, 400)] + [row(first_token_ms=None, status="failed")]
        m = summarize_window(rows)
        self.assertEqual(m.p50_first_token_ms, 250.0)

    def test_cache_hit_rate_counts_all_three_input_fields(self):
        m = summarize_window([row(input_tokens=100, cache_read_tokens=800, cache_write_tokens=100)])
        self.assertAlmostEqual(m.cache_hit_rate, 0.8)
        self.assertIsNone(summarize_window([row(input_tokens=0)]).cache_hit_rate)

    def test_unpriced_calls_are_counted_not_summed_as_zero(self):
        m = summarize_window([row(cost_micro_usd=100), row(cost_micro_usd=None), row(cost_micro_usd=50)])
        self.assertEqual((m.cost_micro_usd, m.unpriced_calls), (150, 1))

    def test_thumbs_down_rate_is_among_rated_turns_only(self):
        m = summarize_window([row(rating=-1), row(rating=1), row(rating=1), row(rating=None), row(rating=None)])
        self.assertAlmostEqual(m.thumbs_down_rate, 1 / 3)
        self.assertIsNone(summarize_window([row()]).thumbs_down_rate)


class AlertTests(unittest.TestCase):
    def metrics(self, **kw):
        m = WindowMetrics(n=100)
        for k, v in kw.items():
            setattr(m, k, v)
        return m

    def test_threshold_and_direction(self):
        rules = [Rule("err", "error_rate", ">", 0.05), Rule("cache", "cache_hit_rate", "<", 0.3)]
        b = evaluate(rules, self.metrics(error_rate=0.10, cache_hit_rate=0.5))
        self.assertEqual([x.rule.name for x in b], ["err"])
        b = evaluate(rules, self.metrics(error_rate=0.01, cache_hit_rate=0.1))
        self.assertEqual([x.rule.name for x in b], ["cache"])

    def test_too_few_samples_or_no_data_never_breaches(self):
        rule = Rule("err", "error_rate", ">", 0.05, min_samples=30)
        self.assertEqual(evaluate([rule], WindowMetrics(n=10, error_rate=1.0)), [])
        self.assertEqual(evaluate([Rule("c", "cache_hit_rate", "<", 0.3, min_samples=1)], WindowMetrics(n=50, cache_hit_rate=None)), [])

    def test_a_rule_must_be_breached_several_windows_in_a_row(self):
        rule = Rule("err", "error_rate", ">", 0.05, for_windows=3)
        state, bad = AlertState(), self.metrics(error_rate=0.5)
        fired = [state.update([rule], evaluate([rule], bad))[0] for _ in range(4)]
        self.assertEqual([len(f) for f in fired], [0, 0, 1, 0])        # fires once, on the third, not again

    def test_a_good_window_resets_the_streak_and_resolves(self):
        rule = Rule("err", "error_rate", ">", 0.05, for_windows=2)
        state = AlertState()
        bad, good = self.metrics(error_rate=0.5), self.metrics(error_rate=0.0)
        state.update([rule], evaluate([rule], bad))
        state.update([rule], evaluate([rule], good))                    # streak broken before firing
        self.assertEqual(state.update([rule], evaluate([rule], bad))[0], [])
        fired, _ = state.update([rule], evaluate([rule], bad))
        self.assertEqual(len(fired), 1)
        _, resolved = state.update([rule], evaluate([rule], good))
        self.assertEqual(resolved, ["err"])

    def test_bad_rules_are_rejected_at_creation(self):
        with self.assertRaises(ValueError):
            Rule("x", "error_rate", "~", 1)
        with self.assertRaises(ValueError):
            Rule("x", "no_such_metric", ">", 1)

    def test_defaults_page_on_unpriced_models_immediately(self):
        rules = {r.name: r for r in default_rules(hourly_budget_micro_usd=5_000_000)}
        self.assertEqual((rules["unpriced-model"].for_windows, rules["unpriced-model"].severity), (1, "page"))
        self.assertIn("hourly-spend", rules)
        self.assertNotIn("hourly-spend", {r.name for r in default_rules()})
        b = evaluate(list(rules.values()), WindowMetrics(n=5, unpriced_calls=2))
        self.assertEqual([x.rule.name for x in b], ["unpriced-model"])


class DeprecationTests(unittest.TestCase):
    L = deprecation.load_lifecycle()

    def sev(self, model, today):
        return [(f.severity) for f in deprecation.check_models([model], self.L, today)]

    def test_the_shipped_file_is_valid_and_has_the_models_used_in_this_book(self):
        for m in ("claude-sonnet-5-5", "claude-haiku-5-5", "claude-sonnet-4-5-20250929"):
            self.assertIn(m, self.L)

    def test_sonnet_4_5_is_an_error_in_its_last_30_days_and_after(self):
        self.assertEqual(self.sev("claude-sonnet-4-5-20250929", date(2026, 11, 5)), ["error"])    # 25 days left
        self.assertEqual(self.sev("claude-sonnet-4-5-20250929", date(2026, 12, 1)), ["error"])    # already retired
        msg = deprecation.check_models(["claude-sonnet-4-5-20250929"], self.L, date(2026, 11, 5))[0].message
        self.assertIn("25 days", msg)
        self.assertIn("claude-sonnet-5-5", msg)

    def test_warning_window_then_info(self):
        self.assertEqual(self.sev("claude-sonnet-4-5-20250929", date(2026, 10, 15)), ["warn"])   # 46 days
        self.assertEqual(self.sev("claude-sonnet-4-5-20250929", date(2026, 8, 1)), ["info"])

    def test_healthy_and_unknown_models(self):
        self.assertEqual(self.sev("claude-sonnet-5-5", date(2026, 11, 5)), [])
        self.assertEqual(self.sev("claude-sonet-5-5", date(2026, 11, 5)), ["warn"])              # typo is noticed

    def test_the_guaranteed_until_date_passing_is_a_warning(self):
        self.assertEqual(self.sev("claude-haiku-5-5", date(2027, 10, 8)), ["warn"])

    def test_cli_exit_codes(self):
        buf = io.StringIO()
        with redirect_stdout(buf):
            self.assertEqual(deprecation.main(["claude-sonnet-5-5", "claude-haiku-5-5"], date(2026, 11, 5)), 0)
            self.assertEqual(deprecation.main(["claude-sonnet-4-5-20250929"], date(2026, 11, 5)), 1)
            self.assertEqual(deprecation.main([], date(2026, 11, 5)), 2)
        self.assertIn("healthy", buf.getvalue())


if __name__ == "__main__":
    unittest.main()
