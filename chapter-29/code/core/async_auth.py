"""Authenticate and throttle inside a plain async Django view, using the same classes DRF uses."""
from asgiref.sync import sync_to_async
from rest_framework.exceptions import APIException
from rest_framework.request import Request
from rest_framework.settings import api_settings

from core.throttles import ChatBurstThrottle


def _authenticate(request):
    drf_request = Request(request)
    for auth_class in api_settings.DEFAULT_AUTHENTICATION_CLASSES:
        try:
            result = auth_class().authenticate(drf_request)
        except APIException:
            return None, drf_request            # a bad or expired token is "not logged in"
        if result is not None:
            drf_request.user, drf_request.auth = result
            return result[0], drf_request
    return None, drf_request


def _throttle(drf_request):
    throttle = ChatBurstThrottle()
    return throttle.allow_request(drf_request, None), throttle.wait()


async def authenticate(request):
    """Returns (user_or_None, drf_request)."""
    return await sync_to_async(_authenticate)(request)


async def check_burst(drf_request):
    """Returns (allowed, retry_after_seconds)."""
    return await sync_to_async(_throttle)(drf_request)
