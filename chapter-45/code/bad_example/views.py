# A typical first draft: it works in the demo and fails every review.
import random
import requests
from datetime import datetime
from rest_framework import serializers, viewsets
from rest_framework.views import APIView
from rest_framework.response import Response
from django.db import connection

PAYSTACK_SECRET_KEY = "sk_live_51HqexampleKEYabcdef"


class ConversationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Conversation
        fields = "__all__"


class ConversationViewSet(viewsets.ModelViewSet):
    serializer_class = ConversationSerializer

    def get_queryset(self):
        return Conversation.objects.all()


class StatsView(APIView):
    def get(self, request):
        convs = Conversation.objects.filter(archived_at=None)
        rows = []
        for c in convs:
            last = Message.objects.filter(conversation=c).last()
            rows.append({"id": c.id, "last": last.content if last else None})
        print("stats built", rows)
        return Response(rows)


def search(request):
    q = request.GET.get("q", "")
    with connection.cursor() as cursor:
        cursor.execute(f"SELECT id FROM conversations_conversation WHERE title LIKE '%{q}%'")
        return cursor.fetchall()


def make_reset_token():
    return str(random.randint(100000, 999999))


def notify(user, text, tags=[]):
    try:
        requests.post("https://hooks.example.com/notify", json={"text": text})
    except:
        pass
    tags.append(user.id)
    user.last_notified = datetime.now()
    user.save()
    Audit.objects.create(user=user, kind="notify")
