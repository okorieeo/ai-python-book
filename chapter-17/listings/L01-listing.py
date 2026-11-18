class ConversationViewSet(OwnedQuerysetMixin, viewsets.ModelViewSet):
    queryset = Conversation.objects.all()
    serializer_class = ConversationSerializer
    permission_classes = [IsAuthenticated, IsOwner]
    lookup_field = "public_id"

    def perform_create(self, serializer):
        # the owner comes from the session, never from the request body
        serializer.save(user=self.request.user)
