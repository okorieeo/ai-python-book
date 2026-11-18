"""Tests for the request-context helper (no database needed)."""
from types import SimpleNamespace
from unittest import TestCase

from audit.context import request_context
from core.request_context import request_id_var


class RequestContextTests(TestCase):
    def test_collects_ip_user_agent_and_request_id(self):
        request = SimpleNamespace(META={
            "REMOTE_ADDR": "172.18.0.5", "HTTP_X_FORWARDED_FOR": "6.6.6.6, 198.51.100.7",
            "HTTP_USER_AGENT": "Mozilla/5.0\x00 (X11)\nInjected: header",
        })
        token = request_id_var.set("req_abc123456789")
        try:
            ctx = request_context(request, trusted_proxies=1)
        finally:
            request_id_var.reset(token)
        self.assertEqual(ctx["ip_address"], "198.51.100.7")
        self.assertEqual(ctx["request_id"], "req_abc123456789")
        self.assertNotIn("\n", ctx["user_agent"])
        self.assertNotIn("\x00", ctx["user_agent"])

    def test_outside_a_request_the_id_is_empty(self):
        ctx = request_context(SimpleNamespace(META={"REMOTE_ADDR": "203.0.113.9"}), trusted_proxies=0)
        self.assertEqual(ctx["request_id"], "")
        self.assertEqual(ctx["ip_address"], "203.0.113.9")
