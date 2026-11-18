from types import SimpleNamespace

import pytest

from ai_lab.catalog import get_model, local_model
from ai_lab.embeddings import OpenAICompatEmbedder, cosine_similarity, top_k
from ai_lab.router import Job, NoModelFits, choose_model
from ai_lab.tokens import count_tokens_anthropic, estimate_tokens, fits_in_context


# ---- tokens ----
def test_estimate_tokens_is_a_rough_ceiling_division():
    assert estimate_tokens("") == 0
    assert estimate_tokens("abc") == 1
    assert estimate_tokens("abcd") == 2  # 4 characters / 3 per token, rounded up
    assert estimate_tokens("x" * 300) == 100


def test_fits_in_context_counts_the_reply_too():
    model = local_model("tiny", context_window=1000, max_output=500)
    assert fits_in_context(model, prompt_tokens=600, max_output=400)
    assert not fits_in_context(model, prompt_tokens=601, max_output=400)


def test_count_tokens_wrapper_passes_system_and_messages():
    seen = {}

    class FakeMessages:
        def count_tokens(self, **kwargs):
            seen.update(kwargs)
            return SimpleNamespace(input_tokens=42)

    client = SimpleNamespace(messages=FakeMessages())
    n = count_tokens_anthropic(client, model="claude-sonnet-5-5",
                               messages=[{"role": "user", "content": "hi"}], system="Be brief.")
    assert n == 42
    assert seen["system"] == "Be brief."
    assert seen["model"] == "claude-sonnet-5-5"


# ---- router ----
def test_router_picks_the_cheapest_model_that_meets_the_tier():
    assert choose_model(Job("classify", min_tier="fast")).model_id == "claude-haiku-5-5"
    assert choose_model(Job("chat", min_tier="balanced")).model_id == "claude-sonnet-5-5"
    assert choose_model(Job("agent", min_tier="strong")).model_id == "claude-opus-5-5"
    assert choose_model(Job("hardest", min_tier="frontier")).model_id == "claude-fable-5-1"


def test_router_respects_context_and_output_limits():
    small = local_model("small", context_window=8_000, max_output=2_000)
    with pytest.raises(NoModelFits):
        choose_model(Job("big", min_tier="local", prompt_tokens=50_000), models=[small])
    assert choose_model(Job("ok", min_tier="local", prompt_tokens=1_000), models=[small]) is small


def test_router_can_stay_with_one_provider():
    local = local_model("mine")
    job = Job("x", min_tier="local", providers=("local",))
    assert choose_model(job, models=[get_model("claude-haiku-5-5"), local]) is local


# ---- embeddings ----
def test_cosine_similarity_basics():
    assert cosine_similarity([1, 0], [1, 0]) == pytest.approx(1.0)
    assert cosine_similarity([1, 0], [0, 1]) == pytest.approx(0.0)
    assert cosine_similarity([1, 0], [-1, 0]) == pytest.approx(-1.0)
    assert cosine_similarity([1, 2], [2, 4]) == pytest.approx(1.0)  # length does not matter


def test_cosine_similarity_rejects_mixed_models_and_zero_vectors():
    with pytest.raises(ValueError, match="same length"):
        cosine_similarity([1, 2, 3], [1, 2])
    with pytest.raises(ValueError, match="zero vector"):
        cosine_similarity([0, 0], [1, 1])


def test_top_k_orders_by_similarity():
    texts = ["cat", "kitten", "invoice"]
    vectors = [[0.9, 0.8, 0.1], [0.85, 0.75, 0.15], [0.1, 0.2, 0.95]]
    hits = top_k([0.88, 0.79, 0.12], vectors, texts, k=2)
    assert [h.text for h in hits] == ["kitten", "cat"] or [h.text for h in hits] == ["cat", "kitten"]
    assert hits[0].score >= hits[1].score
    assert "invoice" not in [h.text for h in hits]


def test_embedder_returns_vectors_in_input_order_even_if_api_shuffles():
    class FakeEmbeddings:
        def create(self, model, input):
            data = [SimpleNamespace(index=1, embedding=[2.0]), SimpleNamespace(index=0, embedding=[1.0])]
            return SimpleNamespace(data=data)

    client = SimpleNamespace(embeddings=FakeEmbeddings())
    assert OpenAICompatEmbedder(client, "m").embed(["a", "b"]) == [[1.0], [2.0]]
    assert OpenAICompatEmbedder(client, "m").embed([]) == []
