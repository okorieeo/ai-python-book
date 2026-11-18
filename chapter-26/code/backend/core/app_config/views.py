import os

from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from core.throttles import BurstThrottle

from .version_gate import PLATFORMS, PolicyError, build_response, policy_from_env


class AppConfigThrottle(BurstThrottle):
    scope = "app_config"  # add "app_config": "60/min" to DEFAULT_THROTTLE_RATES


class AppConfigView(APIView):
    """
    Public on purpose: the app must be able to ask "am I too old?" BEFORE anyone
    logs in. Nothing here is secret: a version number and a store link.
    """

    authentication_classes: list = []
    permission_classes = [AllowAny]  # an explicit exception to deny-by-default (Chapter 17)
    throttle_classes = [AppConfigThrottle]

    def get(self, request):
        platform = request.query_params.get("platform", "")
        if platform not in PLATFORMS:
            return Response({"detail": "platform must be ios or android."}, status=status.HTTP_400_BAD_REQUEST)
        try:
            body = build_response(policy_from_env(os.environ), platform)
        except PolicyError:
            # A broken policy must not break the app: say "no restriction" and let ops fix it.
            body = {"min_version": "1.0.0", "recommended_version": "1.0.0",
                    "store_url": "", "maintenance": False, "message": ""}
        response = Response(body)
        response["Cache-Control"] = "public, max-age=60"
        return response
