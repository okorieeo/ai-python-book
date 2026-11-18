import json
import logging

import requests
from django.conf import settings

from .models import PushDevice

log = logging.getLogger(__name__)

BATCH_SIZE = 100  # Expo accepts at most 100 messages per request
MAX_DATA_BYTES = 3000  # Expo's whole message limit is 4096 bytes
TIMEOUT_SECONDS = 10

class PushError(Exception):
    """Expo could not be reached or refused the request. Safe to retry later."""

def _chunks(items, size):
    for i in range(0, len(items), size):
        yield items[i : i + size]

def send_push(user, title: str, body: str, data: dict | None = None) -> dict:
    """Send one notification to every active phone of `user`.

    Put ids in `data`, never secrets: the title and body show on a locked screen.
    Returns {"sent": n, "deactivated": n}.
    """
    data = data or {}
    if len(json.dumps(data).encode()) > MAX_DATA_BYTES:
        raise ValueError("The notification data is too large.")

    devices = list(user.push_devices.filter(is_active=True))
    messages = [
        {
            "to": d.token,
            "title": title,
            "body": body,
            "data": data,
            "sound": "default",
            "channelId": "default",  # the channel the app creates (Section 24.8)
            "priority": "high",
        }
        for d in devices
    ]
    headers = {"Accept": "application/json", "Content-Type": "application/json"}
    if settings.EXPO_PUSH_ACCESS_TOKEN:  # only needed if you turn on "enhanced push security"
        headers["Authorization"] = f"Bearer {settings.EXPO_PUSH_ACCESS_TOKEN}"

    sent = deactivated = 0
    for batch in _chunks(messages, BATCH_SIZE):
        try:
            response = requests.post(
                settings.EXPO_PUSH_URL,
                json=batch,
                headers=headers,
                timeout=TIMEOUT_SECONDS,
            )
            response.raise_for_status()
            tickets = response.json()["data"]
        except (requests.RequestException, ValueError, KeyError) as exc:
            raise PushError(str(exc)) from exc

        # One ticket per message, in the same order. A ticket only says Expo ACCEPTED
        # the message. Whether the phone got it is reported later, in a receipt.
        for message, ticket in zip(batch, tickets):
            if ticket.get("status") == "ok":
                sent += 1
            elif ticket.get("details", {}).get("error") == "DeviceNotRegistered":
                # The app was uninstalled or notifications were revoked: stop trying.
                PushDevice.objects.filter(token=message["to"]).update(is_active=False)
                deactivated += 1
            else:
                log.warning("push rejected: %s", ticket.get("message"))
    return {"sent": sent, "deactivated": deactivated}
