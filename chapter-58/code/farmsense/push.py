"""Push notifications through Expo's push service. NOT executed in the book's test environment (no devices, no network).

How it works: the mobile app asks Expo for a push token and sends it to our API. To notify, WE call Expo's HTTP endpoint with
that token, and Expo forwards the message to Apple's or Google's service. Sending is a request; DELIVERY is reported later:
Expo returns a ticket id, and a receipt (fetched a while afterwards) says whether the platform accepted it.
Details from Expo's documentation: send to https://exp.host/--/api/v2/push/send, receipts from .../getReceipts, send in batches of up
to 100 messages, and use an access token if you enabled "enhanced push security" for your project."""
import logging
import os
from typing import Dict, Iterable, List

import requests

log = logging.getLogger(__name__)
SEND_URL = "https://exp.host/--/api/v2/push/send"
RECEIPTS_URL = "https://exp.host/--/api/v2/push/getReceipts"
CHUNK = 100


def _headers() -> Dict[str, str]:
    h = {"Accept": "application/json", "Content-Type": "application/json"}
    if os.environ.get("EXPO_ACCESS_TOKEN"):
        h["Authorization"] = f"Bearer {os.environ['EXPO_ACCESS_TOKEN']}"
    return h


def send_push(tokens: Iterable[str], title: str, body: str, data: dict, critical: bool = False) -> List[str]:
    """Returns the tokens that Expo says are dead (the app was uninstalled): delete them so we stop sending to nobody."""
    tokens = list(tokens)
    dead: List[str] = []
    for i in range(0, len(tokens), CHUNK):
        batch = tokens[i:i + CHUNK]
        messages = [{"to": t, "title": title, "body": body, "data": data, "sound": "default",
                     "priority": "high" if critical else "default", "channelId": "alerts"} for t in batch]
        try:
            resp = requests.post(SEND_URL, json=messages, headers=_headers(), timeout=10)
            resp.raise_for_status()
            tickets = resp.json().get("data", [])
        except (requests.RequestException, ValueError):
            log.exception("push send failed")             # the caller falls back to e-mail; never lose a critical alert silently
            raise
        for token, ticket in zip(batch, tickets):
            if ticket.get("status") == "error" and (ticket.get("details") or {}).get("error") == "DeviceNotRegistered":
                dead.append(token)
    return dead
