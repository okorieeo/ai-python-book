# ---------------------------------------------------------- conversations
@extend_schema_view(
    list=extend_schema(summary="List my conversations"),
    create=extend_schema(summary="Start a conversation",
                         responses=ok(ConversationSerializer, 201)),
    retrieve=extend_schema(summary="Get one conversation",
                           responses=ok(ConversationSerializer)),
    partial_update=extend_schema(summary="Rename a conversation",
                                 responses=ok(ConversationSerializer)),
    destroy=extend_schema(summary="Delete a conversation",
                          responses={204: None, **ERRORS}),
)
class ConversationViewSet(viewsets.ModelViewSet):
    serializer_class = ConversationSerializer
    permission_classes = [IsAuthenticated, IsOwner]
    lookup_field = "public_id"
    lookup_value_regex = "[0-9a-fA-F-]{36}"
    http_method_names = ["get", "post", "patch", "delete", "head", "options"]
    pagination_class = ActivityCursorPagination
    search_fields = ["title"]
    ordering_fields = ["created_at", "updated_at"]
    queryset = Conversation.objects.none()         # lets the schema tool see the model

    def get_queryset(self):
        # someone else's conversation is simply not in this queryset: a 404
        return Conversation.objects.filter(
            user=self.request.user, deleted_at__isnull=True)

    def perform_create(self, serializer):
        serializer.save(user=self.request.user)   # the owner comes from the token

    def perform_destroy(self, instance):           # a soft delete (Chapter 7)
        instance.deleted_at = timezone.now()
        instance.save(update_fields=["deleted_at"])
# ----- next listing from the chapter -----
# --------------------------------------------------------------- messages
@extend_schema_view(
    list=extend_schema(summary="List messages, newest first",
                       responses=ok(MessageSerializer)),
    create=extend_schema(summary="Send a message",
                         request=MessageCreateSerializer,
                         responses={201: MessageSerializer, 402: ErrorSerializer,
                                    **ERRORS}),
)
class MessageViewSet(mixins.ListModelMixin, mixins.CreateModelMixin,
                     viewsets.GenericViewSet):
    permission_classes = [IsAuthenticated]
    filter_backends = []                           # a plain, ordered history

    def get_serializer_class(self):
        if self.action == "create":
            return MessageCreateSerializer
        return MessageSerializer

    def get_throttles(self):
        if self.action == "create":
            self.throttle_scope = "ai_chat"        # sending costs money
        return super().get_throttles()

    def get_conversation(self):
        return get_object_or_404(
            Conversation, public_id=self.kwargs["conversation_id"],
            user=self.request.user, deleted_at__isnull=True)

    def get_queryset(self):
        return Message.objects.filter(conversation=self.get_conversation())

    @idempotent
    def create(self, request, *args, **kwargs):
        conversation = self.get_conversation()
        check_quota(request.user)                  # 402 when the plan is used up
        serializer = MessageCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        message = services.add_message(
            conversation, Message.Role.USER, serializer.validated_data["content"])
        # Chapters 14 and 29: queue the AI reply and stream it here.
        return Response(MessageSerializer(message).data, status=201)
# ----- next listing from the chapter -----
# -------------------------------------------------------------- documents
@extend_schema_view(
    list=extend_schema(summary="List my documents",
                       responses=ok(DocumentSerializer)),
    create=extend_schema(summary="Register a document (processed in background)",
                         responses=ok(DocumentSerializer, 202)),
    retrieve=extend_schema(summary="Get one document",
                           responses=ok(DocumentSerializer)),
    destroy=extend_schema(summary="Delete a document",
                          responses={204: None, **ERRORS}),
    reindex=extend_schema(summary="Process a document again", request=None,
                          responses=ok(DocumentSerializer, 202)),
)
class DocumentViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin,
                      mixins.CreateModelMixin, mixins.DestroyModelMixin,
                      viewsets.GenericViewSet):
    serializer_class = DocumentSerializer
    permission_classes = [IsAuthenticated, IsOwner]
    lookup_field = "public_id"
    lookup_value_regex = "[0-9a-fA-F-]{36}"
    filterset_class = DocumentFilter               # an explicit whitelist
    ordering_fields = ["created_at", "filename"]
    search_fields = ["filename"]
    queryset = Document.objects.none()

    def get_queryset(self):
        return Document.objects.filter(user=self.request.user)

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        document = serializer.save(user=request.user)
        services.start_ingestion(document)
        location = f"/api/v1/documents/{document.public_id}"
        return Response(DocumentSerializer(document).data, status=202,
                        headers={"Location": location})

    @action(detail=True, methods=["post"])
    def reindex(self, request, public_id=None):
        document = self.get_object()
        services.start_ingestion(document)
        return Response(DocumentSerializer(document).data, status=202)
# ----- next listing from the chapter -----
# -------------------------------------------------------- account and meta
class MeView(APIView):
    @extend_schema(summary="The current user", responses=ok(UserSerializer))
    def get(self, request):
        return Response(UserSerializer(request.user).data)

class UsageView(APIView):
    @extend_schema(summary="Today's AI usage", responses=ok(UsageSerializer))
    def get(self, request):
        used = tokens_used_today(request.user)
        limit = settings.CHAT_DAILY_TOKEN_LIMIT
        data = {"tokens_used_today": used, "daily_limit": limit,
                "remaining": max(limit - used, 0)}
        return Response(UsageSerializer(data).data)

class ClientConfigView(APIView):
    permission_classes = [AllowAny]

    @extend_schema(summary="Minimum supported app version",
                   responses=ClientConfigSerializer)
    def get(self, request):
        return Response(ClientConfigSerializer(settings.CLIENT_CONFIG).data)

class HealthView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []

    @extend_schema(summary="Liveness check", responses={200: dict})
    def get(self, request):
        return Response({"status": "ok"})
# ----- next listing from the chapter -----
# ------------------------------------------------------------------- auth
class LoginView(TokenObtainPairView):
    throttle_scope = "auth"

class RefreshView(TokenRefreshView):
    throttle_scope = "auth"

class LogoutView(TokenBlacklistView):
    throttle_scope = "auth"
