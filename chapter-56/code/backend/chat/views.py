from rest_framework import generics, serializers

from .models import Conversation, Message


class ConversationSerializer(serializers.ModelSerializer):
    id = serializers.UUIDField(source="public_id", read_only=True)

    class Meta:
        model = Conversation
        fields = ["id", "title", "updated_at"]
        read_only_fields = fields


class MessageSerializer(serializers.ModelSerializer):
    class Meta:
        model = Message
        fields = ["id", "role", "content", "status", "created_at"]
        read_only_fields = fields


class ConversationListView(generics.ListAPIView):
    serializer_class = ConversationSerializer

    def get_queryset(self):  # every query starts from the owner
        return Conversation.objects.filter(user=self.request.user)[:100]


class ConversationDetailView(generics.RetrieveDestroyAPIView):
    serializer_class = ConversationSerializer
    lookup_field = "public_id"

    def get_queryset(self):
        return Conversation.objects.filter(user=self.request.user)  # another user's id is a 404, not a 403


class MessageListView(generics.ListAPIView):
    serializer_class = MessageSerializer

    def get_queryset(self):
        return Message.objects.filter(conversation__user=self.request.user,
                                      conversation__public_id=self.kwargs["public_id"]
                                      ).exclude(status=Message.Status.ERROR, content="")
