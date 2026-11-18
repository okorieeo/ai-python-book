"""A fake AI provider for development and tests: streams a canned answer word by word. No API key needed."""
import asyncio

from .streaming import Delta, Usage, estimate_tokens

class FakeProvider:
    name = "fake-model"

    def __init__(self, delay: float = 0.03, reply: str | None = None):
        self.delay = delay
        self.reply = reply

    async def stream(self, messages: list[dict]):
        last_user = next((m["content"] for m in reversed(messages) if m["role"] == "user"), "")
        reply = self.reply or (
            f"You said: {last_user[:60]}. This is a simulated streaming answer, delivered word by word "
            "exactly like a real model would, so you can build and test the whole pipeline without an API key."
        )
        for word in reply.split(" "):
            await asyncio.sleep(self.delay)
            yield Delta(word + " ")
        prompt_text = " ".join(m["content"] for m in messages)
        yield Usage(estimate_tokens(prompt_text), estimate_tokens(reply))
