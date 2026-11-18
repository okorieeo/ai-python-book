import pytest

from ai_lab import lab


def test_models_command_lists_the_catalog(capsys):
    assert lab.main(["models"]) == 0
    out = capsys.readouterr().out
    for model_id in ("claude-fable-5-1", "claude-opus-5-5", "claude-sonnet-5-5", "claude-haiku-5-5"):
        assert model_id in out


def test_chatcost_shows_that_history_multiplies_the_input(capsys):
    assert lab.main(["chatcost", "--turns", "10", "--system", "800", "--user", "150", "--reply", "400"]) == 0
    out = capsys.readouterr().out
    assert "34,250" in out  # input tokens actually sent
    assert "1,500" in out  # what the user typed


def test_demo_vectors_runs_offline(capsys):
    assert lab.main(["demo-vectors"]) == 0
    out = capsys.readouterr().out
    assert "cat vs kitten" in out and "cat vs invoice" in out


def test_count_estimate_runs_offline(capsys):
    assert lab.main(["count", "--text", "x" * 300]) == 0
    assert "100" in capsys.readouterr().out


def test_missing_api_key_gives_a_friendly_error_not_a_traceback(monkeypatch, capsys):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    assert lab.main(["ask", "hi"]) == 2
    assert "ANTHROPIC_API_KEY" in capsys.readouterr().err


# ---- commands that normally call the network, run against fakes ----
from types import SimpleNamespace

from ai_lab.cost import TokenUsage
from ai_lab.providers import Chunk, Completion


class FakeProvider:
    name = "fake"

    def complete(self, request):
        return Completion(text="Four.", model=request.model, provider="fake", stop_reason="end_turn",
                          usage=TokenUsage(input_tokens=1000, output_tokens=500), latency_ms=123)

    def stream(self, request):
        yield Chunk(text="Fo")
        yield Chunk(text="ur.")
        yield Chunk(completion=self.complete(request))


def test_ask_prints_answer_tokens_and_cost(monkeypatch, capsys):
    monkeypatch.setattr(lab, "build_provider", lambda kind: FakeProvider())
    assert lab.main(["ask", "2+2?", "--model", "claude-sonnet-5-5"]) == 0
    out = capsys.readouterr().out
    assert "Four." in out
    assert "in=1,000 out=500" in out
    assert "$0.007000" in out  # 1000 x $2/M + 500 x $10/M


def test_ask_stream_prints_chunks(monkeypatch, capsys):
    monkeypatch.setattr(lab, "build_provider", lambda kind: FakeProvider())
    assert lab.main(["ask", "2+2?", "--stream", "--model", "claude-sonnet-5-5"]) == 0
    assert "Four." in capsys.readouterr().out


def test_ask_warns_when_the_reply_was_cut_off(monkeypatch, capsys):
    class Cut(FakeProvider):
        def complete(self, request):
            c = super().complete(request)
            return Completion(c.text, c.model, c.provider, "max_tokens", c.usage, c.latency_ms)

    monkeypatch.setattr(lab, "build_provider", lambda kind: Cut())
    lab.main(["ask", "hi", "--model", "claude-sonnet-5-5"])
    assert "WARNING" in capsys.readouterr().out


def test_compare_prints_one_row_per_model(monkeypatch, capsys):
    monkeypatch.setattr(lab, "build_provider", lambda kind: FakeProvider())
    assert lab.main(["compare", "hi", "--models", "anthropic:claude-haiku-5-5",
                     "anthropic:claude-sonnet-5-5"]) == 0
    out = capsys.readouterr().out
    assert "claude-haiku-5-5" in out and "claude-sonnet-5-5" in out


def test_unknown_local_model_is_priced_at_zero(monkeypatch, capsys):
    monkeypatch.setattr(lab, "build_provider", lambda kind: FakeProvider())
    assert lab.main(["ask", "hi", "--provider", "local", "--model", "my-local-llm"]) == 0
    assert "$0.000000" in capsys.readouterr().out


def test_similar_ranks_sentences_with_a_fake_embedding_server(monkeypatch, capsys):
    import openai

    def vector_for(text):
        t = text.lower()
        return [1.0 if ("password" in t) else 0.0, 1.0 if ("egg" in t or "chicken" in t) else 0.0,
                1.0 if "refund" in t else 0.0]

    class FakeEmbeddings:
        def create(self, model, input):
            data = [SimpleNamespace(index=i, embedding=vector_for(t)) for i, t in enumerate(input)]
            return SimpleNamespace(data=data)

    monkeypatch.setattr(openai, "OpenAI", lambda **kw: SimpleNamespace(embeddings=FakeEmbeddings()))
    assert lab.main(["similar", "forgot my password", "--embed-model", "fake-embed"]) == 0
    out = capsys.readouterr().out
    assert "dimensions: 3" in out
    first_ranked = [line for line in out.splitlines() if line.strip().startswith("1.000")]
    assert any("password" in line.lower() for line in first_ranked)
