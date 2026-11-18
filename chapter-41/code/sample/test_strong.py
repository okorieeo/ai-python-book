"""The same module, tested by someone who worked out the expected values by hand.

Notice what changed: exact numbers written out, the edges of every range, every error path,
and one property that must hold for all inputs.
"""
from datetime import datetime, timedelta

import pytest

from billing_math import apply_discount, is_trial_active, overage_blocks, prorate_credit, split_evenly


@pytest.mark.parametrize("price, percent, expected", [
    (1000, 10, 900),      # a whole discount: 100
    (2000, 25, 1500),     # 500
    (1005, 10, 904),      # 100.5 rounds half UP to 101
    (999, 50, 499),       # 499.5 rounds up to 500
    (1000, 0, 1000),      # no discount
    (1000, 100, 0),       # free
    (0, 50, 0),           # nothing to discount
    (1, 50, 0),           # 0.5 rounds up to 1
])
def test_apply_discount_exact_values(price, percent, expected):
    assert apply_discount(price, percent) == expected


@pytest.mark.parametrize("percent", [-1, 101, 150])
def test_apply_discount_rejects_percent_outside_0_to_100(percent):
    with pytest.raises(ValueError, match="percent"):
        apply_discount(1000, percent)


def test_apply_discount_rejects_negative_price():
    with pytest.raises(ValueError, match="negative"):
        apply_discount(-1, 10)


def test_apply_discount_accepts_the_edges_of_the_range():
    assert apply_discount(500, 0) == 500
    assert apply_discount(500, 100) == 0


@pytest.mark.parametrize("total, parts, expected", [
    (100, 3, [34, 33, 33]),
    (100, 1, [100]),
    (0, 3, [0, 0, 0]),
    (10, 5, [2, 2, 2, 2, 2]),
    (2, 5, [1, 1, 0, 0, 0]),
])
def test_split_evenly_exact_values(total, parts, expected):
    assert split_evenly(total, parts) == expected


@pytest.mark.parametrize("total", range(0, 40))
@pytest.mark.parametrize("parts", range(1, 8))
def test_split_evenly_never_loses_money_and_is_fair(total, parts):
    shares = split_evenly(total, parts)
    assert sum(shares) == total
    assert len(shares) == parts
    assert max(shares) - min(shares) <= 1
    assert shares == sorted(shares, reverse=True)


def test_split_evenly_rejects_bad_input():
    with pytest.raises(ValueError, match="parts"):
        split_evenly(100, 0)
    with pytest.raises(ValueError, match="total"):
        split_evenly(-1, 3)


@pytest.mark.parametrize("used, included, block, expected", [
    (1650, 1500, 100, 2),
    (1501, 1500, 100, 1),   # one message over starts a block
    (1600, 1500, 100, 1),   # exactly one full block
    (1500, 1500, 100, 0),   # exactly at the allowance: nothing extra
    (1499, 1500, 100, 0),
    (0, 0, 1, 0),
    (5, 0, 1, 5),
])
def test_overage_blocks_exact_values(used, included, block, expected):
    assert overage_blocks(used, included, block) == expected


def test_overage_blocks_rejects_a_block_size_below_one():
    with pytest.raises(ValueError, match="block_size"):
        overage_blocks(10, 5, 0)
    assert overage_blocks(10, 5, 1) == 5  # one is allowed


def test_trial_is_active_before_the_end_and_not_at_or_after_it():
    end = datetime(2026, 2, 1, 12)
    assert is_trial_active(end - timedelta(seconds=1), end) is True
    assert is_trial_active(end, end) is False
    assert is_trial_active(end + timedelta(seconds=1), end) is False


def test_no_trial_end_means_no_trial():
    assert is_trial_active(datetime(2026, 1, 1), None) is False


@pytest.mark.parametrize("amount, left, total, expected", [
    (500, 50, 100, 250),
    (500, 100, 100, 500),
    (500, 0, 100, 0),
    (100, 2, 3, 67),      # 66.67 rounds half up
    (1, 1, 2, 1),         # 0.5 rounds up to 1
    (500, 150, 100, 500), # more left than the whole period is clamped
    (500, -5, 100, 0),    # negative time left is clamped
    (500, 1, 1, 500),     # the smallest period that is allowed
    (500, 0, 1, 0),
])
def test_prorate_credit_exact_values(amount, left, total, expected):
    assert prorate_credit(amount, left, total) == expected


def test_prorate_credit_rejects_a_period_with_no_length():
    with pytest.raises(ValueError, match="seconds_total"):
        prorate_credit(500, 1, 0)
    with pytest.raises(ValueError):
        prorate_credit(500, 1, -10)
