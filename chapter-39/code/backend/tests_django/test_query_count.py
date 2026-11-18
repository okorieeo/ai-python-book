import pytest

from chat.models import Conversation, Message


@pytest.mark.django_db
def test_listing_conversations_does_not_run_a_query_per_row(alice, client_for, django_assert_max_num_queries):
    for _ in range(25):
        c = Conversation.objects.create(user=alice)
        Message.objects.create(conversation=c, role="user", content="hello", status="complete")
    client = client_for(alice)
    with django_assert_max_num_queries(6):          # a fixed budget, however many rows: an N+1 would blow straight through it
        assert client.get("/api/v1/conversations/").status_code == 200
