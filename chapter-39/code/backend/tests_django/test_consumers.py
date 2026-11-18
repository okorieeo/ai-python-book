"""Channels: drive the consumer with a communicator, no browser and no network. Needs pytest-asyncio."""
import pytest
from channels.routing import URLRouter
from channels.testing import WebsocketCommunicator
from django.urls import path

from chat.consumers import ChatConsumer          # the consumer from Chapter 14


def application():
    return URLRouter([path("ws/chat/<int:conversation_id>/", ChatConsumer.as_asgi())])


@pytest.mark.asyncio
@pytest.mark.django_db(transaction=True)      # async code runs in another thread: it cannot see an uncommitted test transaction
async def test_an_anonymous_socket_is_refused():
    comm = WebsocketCommunicator(application(), "/ws/chat/1/")
    connected, _ = await comm.connect()
    assert connected is False


@pytest.mark.asyncio
@pytest.mark.django_db(transaction=True)
async def test_a_message_gets_streamed_events_back(alice, monkeypatch):
    comm = WebsocketCommunicator(application(), "/ws/chat/1/")
    comm.scope["user"] = alice
    connected, _ = await comm.connect()
    assert connected
    await comm.send_json_to({"text": "hello"})
    first = await comm.receive_json_from(timeout=2)       # always pass a timeout: a hung test is worse than a failed one
    assert first["type"] in {"start", "error"}
    await comm.disconnect()
