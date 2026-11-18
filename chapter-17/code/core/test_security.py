"""Tests for the framework-independent security helpers. Plain unittest: Django's runner finds them too."""
import json
import logging
import socket
import tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest import TestCase

from cryptography.fernet import Fernet

from core.security.client_ip import get_client_ip
from core.security.config_checks import find_config_problems
from core.security.crypto import DecryptionError, SecretBox, hash_api_token, new_api_token, verify_hmac
from core.security.env import MissingSecret, Secret, env_or_file, require_secret
from core.security.outbound import UnsafeURL, validate_outbound_url
from core.security.ratelimit import RateLimiter
from core.security.redaction import JsonFormatter, RedactionFilter, redact, redact_data
from core.security.sanitize import build_filters, clean_text, safe_filename


class FakeCache:
    """Behaves like Django's cache for the two methods the limiter uses."""

    def __init__(self):
        self.data = {}

    def add(self, key, value, timeout=None):
        if key in self.data:
            return False
        self.data[key] = value
        return True

    def incr(self, key, delta=1):
        if key not in self.data:
            raise ValueError(f"Key '{key}' not found.")
        self.data[key] += delta
        return self.data[key]


class ClientIPTests(TestCase):
    def test_header_is_ignored_without_trusted_proxies(self):
        meta = {"REMOTE_ADDR": "203.0.113.9", "HTTP_X_FORWARDED_FOR": "1.2.3.4"}
        self.assertEqual(get_client_ip(meta, trusted_proxies=0), "203.0.113.9")

    def test_one_proxy_uses_last_entry_and_ignores_forged_ones(self):
        meta = {"REMOTE_ADDR": "172.18.0.5", "HTTP_X_FORWARDED_FOR": "6.6.6.6, 198.51.100.7"}
        self.assertEqual(get_client_ip(meta, trusted_proxies=1), "198.51.100.7")

    def test_two_proxies_use_second_from_right(self):
        meta = {"REMOTE_ADDR": "172.18.0.5", "HTTP_X_FORWARDED_FOR": "198.51.100.7, 104.16.0.1"}
        self.assertEqual(get_client_ip(meta, trusted_proxies=2), "198.51.100.7")

    def test_too_few_hops_falls_back_to_remote_addr(self):
        meta = {"REMOTE_ADDR": "203.0.113.9", "HTTP_X_FORWARDED_FOR": "198.51.100.7"}
        self.assertEqual(get_client_ip(meta, trusted_proxies=2), "203.0.113.9")

    def test_garbage_is_rejected(self):
        meta = {"REMOTE_ADDR": "172.18.0.5", "HTTP_X_FORWARDED_FOR": "not-an-ip"}
        self.assertIsNone(get_client_ip(meta, trusted_proxies=1))

    def test_ipv6_is_normalized(self):
        meta = {"REMOTE_ADDR": "2001:DB8:0:0:0:0:0:1"}
        self.assertEqual(get_client_ip(meta), "2001:db8::1")


class RateLimiterTests(TestCase):
    def setUp(self):
        self.now = 1_000_000.0
        self.limiter = RateLimiter(FakeCache(), clock=lambda: self.now)

    def hit(self, identity="u1", **kw):
        return self.limiter.hit("chat", identity, limit=3, window=60, **kw)

    def test_allows_up_to_the_limit_then_blocks(self):
        results = [self.hit() for _ in range(4)]
        self.assertEqual([r.allowed for r in results], [True, True, True, False])
        self.assertEqual([r.remaining for r in results], [2, 1, 0, 0])

    def test_blocked_result_says_when_to_retry(self):
        for _ in range(3):
            self.hit()
        blocked = self.hit()
        self.assertFalse(blocked.allowed)
        self.assertEqual(blocked.retry_after, 60 - (int(self.now) % 60))
        self.assertGreater(blocked.retry_after, 0)

    def test_a_new_window_starts_fresh(self):
        for _ in range(4):
            self.hit()
        self.now += 60
        self.assertTrue(self.hit().allowed)

    def test_identities_are_counted_separately(self):
        for _ in range(4):
            self.hit("alice")
        self.assertTrue(self.hit("bob").allowed)

    def test_cost_counts_several_units_at_once(self):
        self.assertTrue(self.hit(cost=3).allowed)
        self.assertFalse(self.hit(cost=1).allowed)

    def test_recovers_if_the_key_expires_between_add_and_incr(self):
        class FlakyCache(FakeCache):
            expired_once = False

            def incr(self, key, delta=1):
                if not self.expired_once:
                    self.expired_once = True
                    self.data.pop(key, None)  # simulate expiry right after add()
                return super().incr(key, delta)

        limiter = RateLimiter(FlakyCache(), clock=lambda: 1_000_000.0)
        result = limiter.hit("chat", "u1", limit=3, window=60)
        self.assertTrue(result.allowed)
        self.assertEqual(result.remaining, 2)


class SanitizeTests(TestCase):
    def test_clean_text_removes_control_and_bidi_characters(self):
        self.assertEqual(clean_text("hel\x00lo\x1b[31m \u202eworld", max_length=50), "hello[31m world")

    def test_clean_text_keeps_newlines_unless_single_line(self):
        self.assertEqual(clean_text("a\nb", max_length=10), "a\nb")
        self.assertEqual(clean_text("a\n  b", max_length=10, single_line=True), "a b")

    def test_clean_text_normalizes_unicode(self):
        self.assertEqual(clean_text("e\u0301", max_length=10), "\u00e9")

    def test_clean_text_rejects_too_long(self):
        with self.assertRaises(ValueError):
            clean_text("x" * 11, max_length=10)

    def test_safe_filename_blocks_path_traversal(self):
        self.assertEqual(safe_filename("../../etc/passwd"), "passwd")
        self.assertEqual(safe_filename("..\\..\\evil.sh"), "evil.sh")

    def test_safe_filename_cleans_awkward_names(self):
        self.assertEqual(safe_filename("my report (final).pdf"), "my_report_final_.pdf")
        self.assertEqual(safe_filename(".htaccess"), "htaccess")
        self.assertEqual(safe_filename("///"), "file")
        self.assertEqual(safe_filename(""), "file")

    def test_safe_filename_keeps_extension_when_shortening(self):
        name = safe_filename("a" * 300 + ".pdf", max_length=20)
        self.assertEqual(len(name), 20)
        self.assertTrue(name.endswith(".pdf"))

    def test_build_filters_only_uses_allowed_parameters(self):
        allowed = {"q": "title__icontains", "after": "created_at__gte"}
        params = {"q": "trip", "user__password__startswith": "pbkdf2", "is_staff": "true", "after": ""}
        self.assertEqual(build_filters(params, allowed), {"title__icontains": "trip"})


class OutboundURLTests(TestCase):
    @staticmethod
    def resolver_for(ip):
        family = socket.AF_INET6 if ":" in ip else socket.AF_INET
        return lambda host, port, **kw: [(family, socket.SOCK_STREAM, 6, "", (ip, port))]

    def test_public_https_url_is_allowed(self):
        url = "https://example.com/doc.pdf"
        self.assertEqual(validate_outbound_url(url, resolver=self.resolver_for("93.184.216.34")), url)

    def test_private_and_internal_addresses_are_blocked(self):
        for ip in ["127.0.0.1", "10.0.0.5", "192.168.1.10", "172.16.0.1", "169.254.169.254", "::1", "::ffff:127.0.0.1"]:
            with self.subTest(ip=ip), self.assertRaises(UnsafeURL):
                validate_outbound_url("https://evil.example/x", resolver=self.resolver_for(ip))

    def test_any_private_answer_blocks_the_url(self):
        def mixed(host, port, **kw):
            return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", port)),
                    (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("10.0.0.5", port))]

        with self.assertRaises(UnsafeURL):
            validate_outbound_url("https://evil.example/x", resolver=mixed)

    def test_bad_schemes_and_credentials_are_blocked(self):
        resolver = self.resolver_for("93.184.216.34")
        for url in ["http://example.com", "file:///etc/passwd", "ftp://example.com/x", "https://user:pw@example.com/",
                    "https:///nohost"]:
            with self.subTest(url=url), self.assertRaises(UnsafeURL):
                validate_outbound_url(url, resolver=resolver)

    def test_unresolvable_host_is_blocked(self):
        def failing(host, port, **kw):
            raise socket.gaierror("no such host")

        with self.assertRaises(UnsafeURL):
            validate_outbound_url("https://nope.invalid/", resolver=failing)


class CryptoTests(TestCase):
    def test_round_trip_and_ciphertext_is_not_plaintext(self):
        box = SecretBox([Fernet.generate_key().decode()])
        token = box.encrypt("sk-user-provider-key")
        self.assertNotIn("sk-user", token)
        self.assertEqual(box.decrypt(token), "sk-user-provider-key")

    def test_wrong_key_or_tampering_raises(self):
        token = SecretBox([Fernet.generate_key().decode()]).encrypt("secret")
        with self.assertRaises(DecryptionError):
            SecretBox([Fernet.generate_key().decode()]).decrypt(token)
        box = SecretBox([Fernet.generate_key().decode()])
        good = box.encrypt("secret")
        with self.assertRaises(DecryptionError):
            box.decrypt(good[:-4] + "AAAA")

    def test_key_rotation(self):
        old, new = Fernet.generate_key().decode(), Fernet.generate_key().decode()
        stored = SecretBox([old]).encrypt("secret")
        rotating = SecretBox([new, old])            # new key first: encrypts with new, still reads old
        self.assertEqual(rotating.decrypt(stored), "secret")
        rotated = rotating.rotate(stored)
        self.assertEqual(SecretBox([new]).decrypt(rotated), "secret")   # old key no longer needed

    def test_no_keys_is_an_error(self):
        with self.assertRaises(ValueError):
            SecretBox([])

    def test_api_tokens_are_random_and_only_the_hash_is_stored(self):
        token, stored = new_api_token()
        other, _ = new_api_token()
        self.assertTrue(token.startswith("aca_"))
        self.assertNotEqual(token, other)
        self.assertEqual(stored, hash_api_token(token))
        self.assertNotIn(token, stored)

    def test_hmac_signature_verification(self):
        import hashlib
        import hmac

        secret, body = b"whsec_test", b'{"event":"charge.success"}'
        good = hmac.new(secret, body, hashlib.sha256).hexdigest()
        self.assertTrue(verify_hmac(secret, body, good))
        self.assertFalse(verify_hmac(secret, body + b" ", good))      # body changed
        self.assertFalse(verify_hmac(b"other-secret", body, good))     # wrong secret
        good512 = hmac.new(secret, body, hashlib.sha512).hexdigest()
        self.assertTrue(verify_hmac(secret, body, good512, algorithm="sha512"))


class EnvTests(TestCase):
    def test_plain_variable(self):
        self.assertEqual(env_or_file("X", environ={"X": "abc"}), "abc")
        self.assertIsNone(env_or_file("X", environ={}))
        self.assertEqual(env_or_file("X", "fallback", environ={}), "fallback")

    def test_file_variable_wins_and_is_stripped(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "secret.txt"
            path.write_text("from-file\n", encoding="utf-8")
            self.assertEqual(env_or_file("X", environ={"X": "from-env", "X_FILE": str(path)}), "from-file")

    def test_require_secret(self):
        self.assertEqual(require_secret("X", environ={"X": "v"}), "v")
        with self.assertRaises(MissingSecret):
            require_secret("X", environ={})

    def test_secret_wrapper_hides_value(self):
        secret = Secret("sk-live-abcdef")
        self.assertNotIn("abcdef", repr(secret))
        self.assertNotIn("abcdef", f"{secret}")
        self.assertEqual(secret.reveal(), "sk-live-abcdef")


class RedactionTests(TestCase):
    def test_redacts_common_secret_shapes(self):
        cases = {
            "retrying with Bearer abcdefghijklmnop": "Bearer [REDACTED]",
            "Authorization: Bearer abcdefghijklmnop": "Authorization: [REDACTED]",
            "Authorization: Token 9f8e7d6c5b4a": "Authorization: [REDACTED]",
            "key is sk_live_abcdefgh12345678": "[KEY REDACTED]",
            "stripe whsec_abcdefgh12345678": "[KEY REDACTED]",
            "using sk-ant-api03-abcdefghijklmnopqrstuvwx": "[KEY REDACTED]",
            "password=hunter2&next=/": "password=[REDACTED]",
            '{"api_key": "abc123xyz"}': '"api_key": "[REDACTED]',
            "token eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxIn0.abc_def-123": "[JWT REDACTED]",
        }
        for original, expected_fragment in cases.items():
            with self.subTest(original=original):
                out = redact(original)
                self.assertIn(expected_fragment, out)
                for leaked in ["hunter2", "abcdefgh12345678", "abc123xyz", "abcdefghijklmnop", "eyJhbGci", "9f8e7d6c5b4a"]:
                    self.assertNotIn(leaked, out)

    def test_redact_data_masks_secret_fields_but_not_counters(self):
        data = {"user": "u1", "api_key": "abc", "input_tokens": 12, "nested": [{"access_token": "xyz"}]}
        out = redact_data(data)
        self.assertEqual(out["api_key"], "[REDACTED]")
        self.assertEqual(out["nested"][0]["access_token"], "[REDACTED]")
        self.assertEqual(out["input_tokens"], 12)
        self.assertEqual(out["user"], "u1")

    def test_normal_text_is_untouched(self):
        text = "GET /api/v1/conversations -> 200 (12 ms)"
        self.assertEqual(redact(text), text)

    def _logger(self, formatter):
        logger = logging.getLogger(f"test.redaction.{id(formatter)}")
        logger.handlers.clear()
        logger.propagate = False
        logger.setLevel(logging.INFO)
        self.records = []

        class Capture(logging.Handler):
            def emit(handler, record):
                self.records.append(handler.format(record))

        handler = Capture()
        handler.setFormatter(formatter)
        handler.addFilter(RedactionFilter())
        logger.addHandler(handler)
        return logger

    def test_filter_redacts_args_and_blocks_log_forging(self):
        logger = self._logger(logging.Formatter("%(levelname)s %(message)s"))
        logger.info("login failed for %s password=%s", "evil\nINFO fake line", "hunter2")
        self.assertEqual(len(self.records), 1)
        self.assertNotIn("\n", self.records[0])
        self.assertNotIn("hunter2", self.records[0])
        self.assertIn("evil\\nINFO fake line", self.records[0])

    def test_json_formatter_outputs_valid_json_with_request_id(self):
        logger = self._logger(JsonFormatter())
        logger.info("hello %s", "world", extra={"request_id": "req_abc", "event": "demo"})
        data = json.loads(self.records[0])
        self.assertEqual(data["message"], "hello world")
        self.assertEqual(data["request_id"], "req_abc")
        self.assertEqual(data["event"], "demo")
        self.assertEqual(data["level"], "INFO")

    def test_json_formatter_redacts_extra_fields_and_tracebacks(self):
        logger = self._logger(JsonFormatter())
        try:
            raise RuntimeError("boom token=abcd1234efgh")
        except RuntimeError:
            logger.exception("failed", extra={"fields": {"api_key": "sk_live_abcdefgh12345678"}})
        self.assertNotIn("abcdefgh12345678", self.records[0])
        self.assertNotIn("abcd1234efgh", self.records[0])
        json.loads(self.records[0])  # still valid JSON after redaction


class ConfigCheckTests(TestCase):
    def good(self, **overrides):
        base = dict(
            ALLOWED_HOSTS=["api.example.com"], CORS_ALLOW_ALL_ORIGINS=False,
            CORS_ALLOWED_ORIGINS=["https://app.example.com"], CSRF_TRUSTED_ORIGINS=["https://api.example.com"],
            INSTALLED_APPS=["core", "chat"],
        )
        base.update(overrides)
        return SimpleNamespace(**base)

    def test_good_configuration_has_no_problems(self):
        self.assertEqual(find_config_problems(self.good()), [])

    def test_localhost_http_origin_is_fine_for_development(self):
        self.assertEqual(find_config_problems(self.good(CORS_ALLOWED_ORIGINS=["http://localhost:3000"])), [])

    def test_each_problem_is_reported(self):
        bad = self.good(
            ALLOWED_HOSTS=["*"], CORS_ALLOW_ALL_ORIGINS=True, CORS_ALLOWED_ORIGINS=["http://app.example.com"],
            CSRF_TRUSTED_ORIGINS=["http://api.example.com"], INSTALLED_APPS=["core", "debug_toolbar"],
        )
        self.assertEqual(len(find_config_problems(bad)), 5)
