from django.conf import settings
from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.parsers import MultiPartParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from chat.models import Message

from . import services, speech_service
from .errors import MediaRejected, ProviderConfigError, ProviderUnavailable
from .models import Attachment
from .serializers import AttachmentSerializer

# What each refusal means for the HTTP status. The app shows its own wording for the `code`.
STATUS_FOR_CODE = {"file_too_large": 413, "unsupported_type": 415, "heic_not_supported": 415,
                   "daily_upload_limit": 429, "storage_quota_exceeded": 413}


def refusal(exc: MediaRejected) -> Response:
    return Response({"code": exc.code, "detail": exc.message}, status=STATUS_FOR_CODE.get(exc.code, 422))


class AttachmentUploadView(APIView):
    """POST /attachments/  (multipart, field "file")  ->  202 and the attachment, still being processed.
    Add your Chapter 17 throttle classes here."""

    permission_classes = [IsAuthenticated]
    parser_classes = [MultiPartParser]

    def post(self, request):
        upload = request.FILES.get("file")
        if upload is None:
            return Response({"code": "no_file", "detail": "Send the file in a field named file."}, status=400)
        try:
            attachment = services.create_attachment(user=request.user, upload=upload)
        except MediaRejected as exc:
            return refusal(exc)
        return Response(AttachmentSerializer(attachment).data, status=status.HTTP_202_ACCEPTED)


class AttachmentDetailView(APIView):
    permission_classes = [IsAuthenticated]

    def _get(self, request, attachment_id) -> Attachment:
        return get_object_or_404(Attachment, public_id=attachment_id, user=request.user)  # someone else's: 404

    def get(self, request, attachment_id):
        return Response(AttachmentSerializer(self._get(request, attachment_id)).data)

    def delete(self, request, attachment_id):
        attachment = self._get(request, attachment_id)
        for field in (attachment.original, attachment.processed):
            if field:
                field.delete(save=False)
        attachment.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class DictationView(APIView):
    """POST /dictation/ (multipart, field "file", optional "language")  ->  {"text": "..."}"""

    permission_classes = [IsAuthenticated]
    parser_classes = [MultiPartParser]

    def post(self, request):
        from .tasks import get_transcriber

        upload = request.FILES.get("file")
        if upload is None:
            return Response({"code": "no_file", "detail": "Send the recording in a field named file."}, status=400)
        try:
            text = speech_service.dictate(
                upload=upload, transcriber=get_transcriber(), language=request.data.get("language") or None
            )
        except MediaRejected as exc:
            return refusal(exc)
        except ProviderUnavailable:
            return Response({"code": "speech_unavailable", "detail": "Speech recognition is busy. Try again."}, status=503)
        except ProviderConfigError:
            return Response({"code": "speech_unavailable", "detail": "Speech recognition is not available."}, status=503)
        return Response({"text": text})


def get_speaker():
    from .providers import OpenAICompatibleSpeaker, make_client

    return OpenAICompatibleSpeaker(
        make_client(api_key=settings.SPEECH_API_KEY, base_url=getattr(settings, "SPEECH_BASE_URL", None)),
        model=settings.SPEECH_MODEL,
    )


class SpeakMessageView(APIView):
    """GET /messages/<id>/speech/?info=1  ->  {"parts": n}   (no audio is made, nothing is billed)
    GET /messages/<id>/speech/?part=0   ->  audio bytes; header X-Speech-Parts repeats the number of parts."""

    permission_classes = [IsAuthenticated]

    def get(self, request, message_id):
        if request.query_params.get("info"):
            message = get_object_or_404(Message, public_id=message_id, conversation__user=request.user, role="assistant")
            return Response({"parts": len(speech_service.speech_parts(message))})
        try:
            part = int(request.query_params.get("part", 0))
        except ValueError:
            return Response({"code": "bad_part", "detail": "part must be a number."}, status=400)
        try:
            audio, parts = speech_service.speak_message(
                user=request.user, message_id=message_id, part=part, speaker=get_speaker(),
                model=settings.SPEECH_MODEL, voice=settings.SPEECH_VOICE,
            )
        except Message.DoesNotExist:
            return Response(status=404)
        except MediaRejected as exc:
            return refusal(exc)
        except (ProviderUnavailable, ProviderConfigError):
            return Response({"code": "speech_unavailable", "detail": "Reading aloud is not available right now."}, status=503)
        response = HttpResponse(audio, content_type="audio/mpeg")
        response["X-Speech-Parts"] = str(parts)
        response["Cache-Control"] = "private, max-age=86400"
        return response
