from types import SimpleNamespace

import pytest

from ai_lab.catalog import CATALOG, get_model, local_model, register
from ai_lab.cost import CostLedger, TokenUsage, conversation_usage, cost_usd


def test_known_prices_match_the_pricing_page():
    assert (get_model("claude-sonnet-5-5").price.input, get_model("claude-sonnet-5-5").price.output) == (2.0, 10.0)
    assert (get_model("claude-opus-5-5").price.input, get_model("claude-opus-5-5").price.output) == (4.0, 20.0)
    assert (get_model("claude-fable-5-1").price.input, get_model("claude-fable-5-1").price.output) == (10.0, 50.0)
    assert (get_model("claude-haiku-5-5").price.input, get_model("claude-haiku-5-5").price.output) == (0.10, 0.50)


def test_unknown_model_gives_a_helpful_error():
    with pytest.raises(KeyError) as err:
        get_model("claude-made-up")
    assert "claude-sonnet-5-5" in str(err.value)


def test_basic_cost():
    sonnet = get_model("claude-sonnet-5-5")
    # 1,000 in x $2/M + 500 out x $10/M = 0.002 + 0.005
    assert cost_usd(sonnet, TokenUsage(input_tokens=1000, output_tokens=500)) == pytest.approx(0.007)


def test_cache_reads_are_much_cheaper_than_fresh_input():
    sonnet = get_model("claude-sonnet-5-5")
    fresh = cost_usd(sonnet, TokenUsage(input_tokens=100_000))
    cached = cost_usd(sonnet, TokenUsage(cache_read_tokens=100_000))
    assert fresh == pytest.approx(0.20)
    assert cached == pytest.approx(0.01)


def test_cache_writes_cost_more_than_plain_input():
    sonnet = get_model("claude-sonnet-5-5")
    assert cost_usd(sonnet, TokenUsage(cache_write_5m_tokens=1_000_000)) == pytest.approx(2.50)
    assert cost_usd(sonnet, TokenUsage(cache_write_1h_tokens=1_000_000)) == pytest.approx(4.00)


def test_haiku_long_prompt_uses_the_higher_price_list():
    haiku = get_model("claude-haiku-5-5")
    short = TokenUsage(input_tokens=100_000, output_tokens=1_000)
    long = TokenUsage(input_tokens=100_001, output_tokens=1_000)
    assert cost_usd(haiku, short) == pytest.approx(100_000 * 0.10 / 1e6 + 1_000 * 0.50 / 1e6)
    assert cost_usd(haiku, long) == pytest.approx(100_001 * 0.50 / 1e6 + 1_000 * 2.50 / 1e6)


def test_haiku_long_threshold_counts_cached_tokens_too():
    haiku = get_model("claude-haiku-5-5")
    usage = TokenUsage(input_tokens=10, cache_read_tokens=120_000)
    assert usage.prompt_tokens == 120_010
    assert cost_usd(haiku, usage) == pytest.approx(10 * 0.50 / 1e6 + 120_000 * 0.05 / 1e6)


def test_batch_and_us_only_multipliers():
    sonnet = get_model("claude-sonnet-5-5")
    usage = TokenUsage(input_tokens=1_000_000, output_tokens=1_000_000)
    base = cost_usd(sonnet, usage)
    assert base == pytest.approx(12.0)
    assert cost_usd(sonnet, usage, batch=True) == pytest.approx(6.0)
    assert cost_usd(sonnet, usage, us_only=True) == pytest.approx(13.2)
    assert cost_usd(sonnet, usage, batch=True, us_only=True) == pytest.approx(6.6)


def test_local_models_cost_nothing_per_token():
    m = local_model("my-local-model")
    assert cost_usd(m, TokenUsage(input_tokens=10**9, output_tokens=10**9)) == 0.0


def test_register_adds_a_model():
    m = register(local_model("temp-model-for-test"))
    assert get_model("temp-model-for-test") is m
    del CATALOG["temp-model-for-test"]


def test_from_anthropic_with_cache_breakdown():
    usage = SimpleNamespace(
        input_tokens=20, output_tokens=7, cache_read_input_tokens=1000,
        cache_creation_input_tokens=300,
        cache_creation=SimpleNamespace(ephemeral_5m_input_tokens=100, ephemeral_1h_input_tokens=200),
    )
    t = TokenUsage.from_anthropic(usage)
    assert (t.input_tokens, t.output_tokens, t.cache_read_tokens) == (20, 7, 1000)
    assert (t.cache_write_5m_tokens, t.cache_write_1h_tokens) == (100, 200)
    assert t.prompt_tokens == 1320


def test_from_anthropic_without_breakdown_assumes_five_minutes():
    usage = SimpleNamespace(input_tokens=1, output_tokens=1, cache_read_input_tokens=0,
                            cache_creation_input_tokens=50, cache_creation=None)
    assert TokenUsage.from_anthropic(usage).cache_write_5m_tokens == 50


def test_from_openai_treats_cached_tokens_as_a_subset_of_the_prompt():
    usage = SimpleNamespace(prompt_tokens=1000, completion_tokens=40,
                            prompt_tokens_details=SimpleNamespace(cached_tokens=800))
    t = TokenUsage.from_openai(usage)
    assert (t.input_tokens, t.cache_read_tokens, t.output_tokens) == (200, 800, 40)


def test_missing_usage_is_zero():
    assert TokenUsage.from_anthropic(None) == TokenUsage()
    assert TokenUsage.from_openai(None) == TokenUsage()


def test_chat_history_is_resent_every_turn():
    turns = conversation_usage(3, system_tokens=100, user_tokens=10, reply_tokens=20)
    assert [t.input_tokens for t in turns] == [110, 140, 170]
    assert all(t.output_tokens == 20 for t in turns)


def test_ledger_adds_per_model():
    ledger = CostLedger()
    ledger.add(get_model("claude-sonnet-5-5"), TokenUsage(input_tokens=1_000_000))
    ledger.add(get_model("claude-sonnet-5-5"), TokenUsage(output_tokens=1_000_000))
    ledger.add(get_model("claude-haiku-5-5"), TokenUsage(input_tokens=50_000))
    assert ledger.total_usd == pytest.approx(2.0 + 10.0 + 50_000 * 0.10 / 1e6)
    assert ledger.usage["claude-sonnet-5-5"].input_tokens == 1_000_000


def test_ledger_prices_each_request_not_the_sum():
    """Many short Haiku requests must not trigger the long-prompt rate just because they add up."""
    haiku = get_model("claude-haiku-5-5")
    ledger = CostLedger()
    for _ in range(10):
        ledger.add(haiku, TokenUsage(input_tokens=50_000))  # each one is under 100K
    assert ledger.total_usd == pytest.approx(10 * 50_000 * 0.10 / 1e6)
    # The wrong way (price the total) would have used the higher rate:
    wrong = cost_usd(haiku, TokenUsage(input_tokens=500_000))
    assert wrong > ledger.total_usd * 4
