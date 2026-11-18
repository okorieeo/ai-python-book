from django.http import HttpResponse
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle as _Throttle   # rates live in settings
from rest_framework.views import APIView

from core.responsible.consent_logic import Purpose, current_state

from . import services
from .serializers import (AcceptDocumentsSerializer, ConfirmPasswordSerializer,
                          ConsentChoiceSerializer, DeleteAccountSerializer)


class ConsentView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        state = current_state(services._values(request.user))
        return Response({
            "must_accept": [p.value for p in services.documents_to_accept(request.user)],
            "choices": {p.value: e.granted for p, e in state.items()},
        })

    def post(self, request):
        data = ConsentChoiceSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        services.record_consent(user=request.user, purpose=Purpose(data.validated_data["purpose"]),
                                granted=data.validated_data["granted"], version="v1", request=request)
        return Response(status=status.HTTP_204_NO_CONTENT)


class AcceptDocumentsView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        data = AcceptDocumentsSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        versions = services.current_versions()
        if (data.validated_data["terms_version"] != versions[Purpose.TERMS]
                or data.validated_data["privacy_version"] != versions[Purpose.PRIVACY_NOTICE]):
            return Response({"detail": "These documents were updated. Please read the new versions."},
                            status=status.HTTP_409_CONFLICT)
        for purpose in (Purpose.TERMS, Purpose.PRIVACY_NOTICE):
            services.record_consent(user=request.user, purpose=purpose, granted=True,
                                    version=versions[purpose], request=request)
        return Response(status=status.HTTP_204_NO_CONTENT)


class ExportView(APIView):
    """Re-ask for the password: a stolen session must not be able to download a whole life's chats."""
    permission_classes = [IsAuthenticated]
    throttle_classes = [_Throttle]
    throttle_scope = "privacy_export"          # e.g. 3/hour in settings

    def post(self, request):
        data = ConfirmPasswordSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        if not request.user.check_password(data.validated_data["password"]):
            return Response({"detail": "Wrong password."}, status=status.HTTP_403_FORBIDDEN)
        archive = services.export_user_data(user=request.user, request=request)
        response = HttpResponse(archive, content_type="application/zip")
        response["Content-Disposition"] = 'attachment; filename="my-data.zip"'
        response["Cache-Control"] = "no-store"
        return response


class DeleteAccountView(APIView):
    permission_classes = [IsAuthenticated]
    throttle_classes = [_Throttle]
    throttle_scope = "privacy_delete"

    def post(self, request):
        data = DeleteAccountSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        if not request.user.check_password(data.validated_data["password"]):
            return Response({"detail": "Wrong password."}, status=status.HTTP_403_FORBIDDEN)
        deletion = services.request_account_deletion(user=request.user, request=request)
        return Response({"scheduled_for": deletion.scheduled_for}, status=status.HTTP_202_ACCEPTED)
