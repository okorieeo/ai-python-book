"""REST endpoints (Django REST Framework). NOT executed in the book's test environment."""
import hashlib

from django.db import transaction
from rest_framework import serializers, status
from rest_framework.parsers import MultiPartParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

from docuask_core.citations import NO_ANSWER_TEXT, ParsedAnswer
from docuask_core.extract import ExtractionError, sniff_type
from docuask_core.limits import LimitExceeded, PLANS, check_upload
from docuask_core.retrieval import should_answer

from . import usage
from .llm import ANSWER_MODEL, answer, rewrite_question
from .models import Conversation, Document, Message
from .search import hybrid_search
from .tasks import get_embedder, ingest_document

NO_ANSWER_THRESHOLD = 0.30      # tune with the evaluation harness on YOUR documents and YOUR embedding model (section 57.16)


def plan_of(user):
    return PLANS[user.profile.plan]


class DocumentSerializer(serializers.ModelSerializer):
    class Meta:
        model = Document
        fields = ["id", "title", "original_filename", "size_bytes", "status", "error_message", "page_count", "chunk_count", "created_at"]


def limit_response(exc: LimitExceeded) -> Response:
    return Response({"code": "limit_exceeded", "metric": exc.metric, "limit": exc.limit, "message": str(exc),
                     "resets_at": exc.resets_at.isoformat() if exc.resets_at else None}, status=status.HTTP_429_TOO_MANY_REQUESTS)


class DocumentListCreateView(APIView):
    permission_classes = [IsAuthenticated]
    parser_classes = [MultiPartParser]

    def get(self, request):
        return Response(DocumentSerializer(Document.objects.filter(owner=request.user), many=True).data)

    def post(self, request):
        upload = request.FILES.get("file")
        if upload is None:
            return Response({"message": "No file was uploaded."}, status=400)
        plan = plan_of(request.user)
        try:
            check_upload(plan, upload.size, Document.objects.filter(owner=request.user).count())
            data = upload.read()
            sniff_type(data, upload.name)                       # reject wrong types before storing anything
        except LimitExceeded as exc:
            return limit_response(exc)
        except ExtractionError as exc:
            return Response({"message": str(exc)}, status=400)

        digest = hashlib.sha256(data).hexdigest()
        existing = Document.objects.filter(owner=request.user, sha256=digest).first()
        if existing:
            return Response(DocumentSerializer(existing).data, status=200)   # same file again: no new work, no new charge
        upload.seek(0)
        with transaction.atomic():
            doc = Document.objects.create(owner=request.user, title=upload.name.rsplit(".", 1)[0][:255],
                                          original_filename=upload.name[:255], file=upload, size_bytes=len(data), sha256=digest)
            transaction.on_commit(lambda: ingest_document.delay(doc.id))     # only after the row is visible to the worker
        return Response(DocumentSerializer(doc).data, status=202)


class DocumentDetailView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, pk):
        doc = Document.objects.filter(owner=request.user, pk=pk).first()      # someone else's id looks exactly like a missing one
        return Response(DocumentSerializer(doc).data) if doc else Response(status=404)

    def delete(self, request, pk):
        doc = Document.objects.filter(owner=request.user, pk=pk).first()
        if not doc:
            return Response(status=404)
        doc.file.delete(save=False)                            # remove the stored file as well as the rows
        doc.delete()                                           # chunks (and their vectors) cascade
        return Response(status=204)


class AskView(APIView):
    permission_classes = [IsAuthenticated]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "ask"

    def post(self, request):
        question = str(request.data.get("question", "")).strip()
        if not (3 <= len(question) <= 2000):
            return Response({"message": "Ask a question between 3 and 2000 characters."}, status=400)
        convo = (Conversation.objects.filter(owner=request.user, pk=request.data.get("conversation_id")).first()
                 or Conversation.objects.create(owner=request.user, title=question[:120]))
        doc_ids = list(convo.documents.values_list("id", flat=True)) or request.data.get("document_ids") or None
        history = [{"role": m.role, "content": m.content} for m in convo.messages.all()[:12]]

        try:
            usage.consume(request.user, plan_of(request.user), "questions", 1)   # reserve BEFORE the expensive calls
        except LimitExceeded as exc:
            return limit_response(exc)
        try:
            standalone = rewrite_question(history, question)
            chunks, best = hybrid_search(request.user, standalone, get_embedder().embed_query(standalone), doc_ids)
            if not chunks or not should_answer(best, NO_ANSWER_THRESHOLD):
                parsed, tin, tout = ParsedAnswer(NO_ANSWER_TEXT, [], refused=True), 0, 0   # the model is never called
            else:
                parsed, tin, tout = answer(standalone, chunks, history)
        except Exception:
            usage.refund(request.user, "questions", 1)          # a failure on our side must not cost the user a question
            raise
        citations = [c.__dict__ for c in parsed.citations]
        Message.objects.create(conversation=convo, role="user", content=question)
        Message.objects.create(conversation=convo, role="assistant", content=parsed.text, citations=citations,
                               grounded=parsed.grounded, model=ANSWER_MODEL, input_tokens=tin, output_tokens=tout)
        return Response({"conversation_id": convo.id, "answer": parsed.text, "citations": citations,
                         "grounded": parsed.grounded, "refused": parsed.refused})


class UsageView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        return Response(usage.snapshot(request.user, plan_of(request.user)))
