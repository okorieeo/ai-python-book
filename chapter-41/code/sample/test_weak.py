"""The kind of test file an assistant often produces when asked to "write tests for billing_math.py".

Every test passes and every line of the module is covered. Read it as a reviewer would.
"""
from datetime import datetime

import pytest

from billing_math import apply_discount, is_trial_active, overage_blocks, prorate_credit, split_evenly


def test_apply_discount_returns_int():
    assert isinstance(apply_discount(1000, 10), int)


def test_apply_discount_reduces_price():
    assert apply_discount(1000, 10) < 1000


def test_apply_discount_formula():
    price = 2000
    percent = 25
    assert apply_discount(price, percent) == price - price * percent / 100


def test_apply_discount_invalid_percent():
    with pytest.raises(ValueError):
        apply_discount(1000, 150)


def test_apply_discount_runs():
    apply_discount(100, 0)


def test_split_evenly_adds_up():
    assert sum(split_evenly(100, 3)) == 100


def test_split_evenly_length():
    assert len(split_evenly(100, 3)) == 3


def test_overage_blocks_positive_when_over():
    assert overage_blocks(150, 100, 10) > 0


def test_overage_blocks_zero_when_under():
    assert overage_blocks(50, 100, 10) == 0


def test_trial_active():
    assert is_trial_active(datetime(2026, 1, 1), datetime(2026, 2, 1))


def test_trial_without_end():
    assert not is_trial_active(datetime(2026, 1, 1), None)


def test_prorate_credit_is_int():
    assert isinstance(prorate_credit(500, 50, 100), int)


def test_prorate_credit_not_negative():
    assert prorate_credit(500, 50, 100) >= 0


# Added after asking the assistant to "get coverage to 100%": each error path is hit, loosely.
def test_apply_discount_negative_price():
    with pytest.raises(ValueError):
        apply_discount(-100, 10)


def test_split_evenly_zero_parts():
    with pytest.raises(ValueError):
        split_evenly(100, 0)


def test_split_evenly_negative_total():
    with pytest.raises(ValueError):
        split_evenly(-5, 2)


def test_overage_blocks_zero_block_size():
    with pytest.raises(ValueError):
        overage_blocks(10, 5, 0)


def test_prorate_credit_zero_total():
    with pytest.raises(ValueError):
        prorate_credit(500, 1, 0)
