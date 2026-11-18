"""
Cost in integer micro-dollars (1 USD = 1_000_000). No floats near money.

Prices are quoted per MILLION tokens, also in micro-dollars, so $2.00 per MTok is 2_000_000.
Cost = ceil(tokens * price / 1_000_000). Rounding UP means the ledger never under-reports.
"""
from __future__ import annotations

from dataclasses import dataclass

from .dto import Usage

MICRO = 1_000_000


@dataclass(frozen=True)
class ModelPrice:
    input: int
    output: int
    cache_write: int
    cache_read: int
    # Some models charge more once the PROMPT (all input tokens) passes a size.
    long_threshold: int | None = None
    long_input: int = 0
    long_output: int = 0
    long_cache_write: int = 0
    long_cache_read: int = 0


def _ceil_div(a: int, b: int) -> int:
    return -(-a // b)


def cost_micro_usd(usage: Usage, price: ModelPrice) -> int:
    long = price.long_threshold is not None and usage.total_input > price.long_threshold
    rate_in = price.long_input if long else price.input
    rate_out = price.long_output if long else price.output
    rate_cw = price.long_cache_write if long else price.cache_write
    rate_cr = price.long_cache_read if long else price.cache_read
    return (
        _ceil_div(usage.input_tokens * rate_in, MICRO)
        + _ceil_div(usage.output_tokens * rate_out, MICRO)
        + _ceil_div(usage.cache_write_tokens * rate_cw, MICRO)
        + _ceil_div(usage.cache_read_tokens * rate_cr, MICRO)
    )


# Checked against Anthropic's model pages in November 2026. PRICES CHANGE: keep this table
# in settings or the database in a real project, and re-check it every quarter.
DEFAULT_PRICES: dict[str, ModelPrice] = {
    # $2 in / $10 out / $2.50 five-minute cache write / $0.10 cache read, per MTok
    "claude-sonnet-5-5": ModelPrice(2_000_000, 10_000_000, 2_500_000, 100_000),
    # $0.10 in / $0.50 out up to 100K-token prompts; $0.50 / $2.50 above that.
    # Cache rates below are ASSUMED from standard multipliers: confirm on the pricing page.
    "claude-haiku-5-5": ModelPrice(
        100_000, 500_000, 125_000, 10_000,
        long_threshold=100_000, long_input=500_000, long_output=2_500_000,
        long_cache_write=625_000, long_cache_read=50_000,
    ),
}


def price_for(model: str, prices: dict[str, ModelPrice] | None = None) -> ModelPrice | None:
    """None for an unknown model. Callers must record 'cost unknown', never crash a chat."""
    table = DEFAULT_PRICES if prices is None else prices   # an EMPTY table is a choice, not "use defaults"
    return table.get(model)


def cost_or_none(usage: Usage, model: str, prices: dict[str, ModelPrice] | None = None) -> int | None:
    price = price_for(model, prices)
    return None if price is None else cost_micro_usd(usage, price)


def format_usd(micro: int) -> str:
    return f"${micro / MICRO:,.4f}"
