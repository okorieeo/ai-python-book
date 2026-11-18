"""Chapter 17's rule as a test: someone else's object looks exactly like one that does not exist."""
import pytest

from chat.models import Conversation, Message

ENDPOINTS = [
    ("get", "/api/v1/conversations/{conv}/"),
    ("post", "/api/v1/conversations/{conv}/stream/"),
    ("delete", "/api/v1/conversations/{conv}/"),
]


@pytest.fixture
def conversation(alice):
    return Conversation.objects.create(user=alice)


@pytest.mark.django_db
@pytest.mark.parametrize("method,template", ENDPOINTS, ids=[f"{m}-{t.split('/')[-2] or 'detail'}" for m, t in ENDPOINTS])
def test_bob_cannot_reach_alices_conversation_and_cannot_tell_it_exists(method, template, conversation, bob, client_for):
    real = getattr(client_for(bob), method)(template.format(conv=conversation.pk), data={"text": "hi"}, format="json")
    missing = getattr(client_for(bob), method)(template.format(conv=999_999), data={"text": "hi"}, format="json")
    assert real.status_code == 404
    assert real.status_code == missing.status_code        # identical: a 403 would confirm the object exists


@pytest.mark.django_db
def test_anonymous_users_get_401_everywhere(conversation, client):
    for method, template in ENDPOINTS:
        assert getattr(client, method)(template.format(conv=conversation.pk)).status_code == 401


@pytest.mark.django_db
def test_alice_still_gets_her_own(conversation, alice, client_for):
    assert client_for(alice).get(f"/api/v1/conversations/{conversation.pk}/").status_code == 200
