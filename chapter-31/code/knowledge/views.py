from django.conf import settings
from django.db import transaction
from rest_framework import mixins, status, viewsets
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import KnowledgeDocument
from .serializers import AnswerSerializer, AskSerializer, DocumentSerializer
from .services import ask, get_retriever
from .store import PgVectorStore
from .tasks import ingest_document_task


class DocumentViewSet(mixins.CreateModelMixin, mixins.ListModelMixin, mixins.RetrieveModelMixin,
                      mixins.DestroyModelMixin, viewsets.GenericViewSet):
    serializer_class = DocumentSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return KnowledgeDocument.objects.filter(owner=self.request.user)      # owner-scoped, as in Chapter 17

    def create(self, request, *args, **kwargs):
        if self.get_queryset().count() >= settings.KNOWLEDGE_MAX_DOCUMENTS:
            return Response({"detail": "Document limit reached."}, status=status.HTTP_409_CONFLICT)
        return super().create(request, *args, **kwargs)

    def perform_create(self, serializer):
        document = serializer.save(owner=self.request.user, content_type=serializer.validated_data["file"].content_type)
        transaction.on_commit(lambda: ingest_document_task.delay(document.pk))   # only after the row is committed

    def perform_destroy(self, instance):
        PgVectorStore().delete_document(str(instance.pk))
        instance.file.delete(save=False)
        instance.delete()


class AskView(APIView):
    permission_classes = [IsAuthenticated]
    throttle_scope = "ask"          # add "ask" to DEFAULT_THROTTLE_RATES (Chapter 17, section 17.8)

    def post(self, request):
        data = AskSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        result = ask(request.user, data.validated_data["question"])
        return Response(AnswerSerializer(result).data)
