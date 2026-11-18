"""Sending a push notification through Expo. The only place that talks to Expo."""
import logging

import requests

from .models import PushDevice

log = logging.getLogger(__name__)
# a fixed address we chose, never one a user supplied (Chapter 17)
EXPO_PUSH_URL = "https://exp.host/--/api/v2/push/send"


def send_push(user, *, title: str, body: str, data: dict | None = None) -> int:
    """Returns how many devices we sent to. Raises requests.RequestException if Expo
    cannot be reached."""
    tokens = list(PushDevice.objects.filter(user=user).values_list("token", flat=True))
    if not tokens:
        return 0
    messages = [{"to": t, "title": title[:100], "body": body[:240], "data": data or {}, "sound": "default"} for t in tokens]
    response = requests.post(EXPO_PUSH_URL, json=messages, timeout=10)
    response.raise_for_status()
    return len(tokens)
