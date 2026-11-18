"""
Celery: keep tasks THIN (load, call a service, save) and test the service directly. A few tests then run the
task itself, in eager mode, to prove the wiring. Eager mode runs the task in the calling process: it does not
test serialisation, routing, acks or real retries, so it can never replace one test against a real worker.
"""
import pytest

from ai import tasks as ai_tasks


@pytest.fixture(autouse=True)
def eager(settings):
    settings.CELERY_TASK_ALWAYS_EAGER = True
    settings.CELERY_TASK_EAGER_PROPAGATES = True          # a failing task raises in the test instead of vanishing


@pytest.mark.django_db
def test_refresh_summary_writes_the_summary(alice, monkeypatch):
    from chat.models import Conversation, Message
    conv = Conversation.objects.create(user=alice)
    for i in range(14):
        Message.objects.create(conversation=conv, role="user" if i % 2 == 0 else "assistant", content=f"m{i}", status="complete")

    async def fake_summarize(**kwargs):
        return "They are planning a trip."

    monkeypatch.setattr(ai_tasks, "summarize", fake_summarize)
    monkeypatch.setattr(ai_tasks, "get_client", lambda: object())
    ai_tasks.refresh_summary.apply(args=[conv.pk]).get()
    conv.refresh_from_db()
    assert conv.summary == "They are planning a trip."


@pytest.mark.django_db
def test_a_missing_conversation_raises_instead_of_failing_silently(monkeypatch):
    with pytest.raises(Exception):
        ai_tasks.refresh_summary.apply(args=[999_999]).get()
