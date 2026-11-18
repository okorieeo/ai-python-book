"""Collect the who-and-where facts about a request for an audit event."""
from core.request_context import request_id_var
from core.security.client_ip import get_client_ip
from core.security.sanitize import clean_text


def request_context(request, *, trusted_proxies: int) -> dict:
    request_id = request_id_var.get()
    agent = request.META.get("HTTP_USER_AGENT", "")[:300]
    return {
        "ip_address": get_client_ip(request.META, trusted_proxies=trusted_proxies),
        "user_agent": clean_text(agent, max_length=300, single_line=True),
        "request_id": "" if request_id == "-" else request_id,
    }
