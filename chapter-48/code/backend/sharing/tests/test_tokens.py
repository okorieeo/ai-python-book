import unittest
from datetime import datetime, timedelta, timezone

from sharing import tokens

NOW = datetime(2026, 11, 8, 12, 0, tzinfo=timezone.utc)


class TokenTests(unittest.TestCase):
    def test_token_is_long_and_url_safe(self):
        t = tokens.generate_token()
        self.assertGreaterEqual(len(t.raw), 43)
        self.assertRegex(t.raw, r"^[A-Za-z0-9_-]+$")

    def test_two_tokens_differ(self):
        self.assertNotEqual(tokens.generate_token().raw, tokens.generate_token().raw)

    def test_digest_is_hex_sha256_and_not_the_token(self):
        t = tokens.generate_token()
        self.assertEqual(len(t.digest), 64)
        self.assertNotIn(t.raw, t.digest)
        self.assertEqual(t.digest, tokens.hash_token(t.raw))

    def test_matching(self):
        t = tokens.generate_token()
        self.assertTrue(tokens.token_matches(t.raw, t.digest))
        self.assertFalse(tokens.token_matches(t.raw + "x", t.digest))
        self.assertFalse(tokens.token_matches("", t.digest))

    def test_default_expiry_is_seven_days(self):
        self.assertEqual(tokens.expiry_from_choice(None, now=NOW), NOW + timedelta(days=7))

    def test_each_choice(self):
        self.assertEqual(tokens.expiry_from_choice("1d", now=NOW), NOW + timedelta(days=1))
        self.assertEqual(tokens.expiry_from_choice("30d", now=NOW), NOW + timedelta(days=30))
        self.assertIsNone(tokens.expiry_from_choice("never", now=NOW))

    def test_unknown_expiry_rejected(self):
        with self.assertRaises(tokens.InvalidExpiry):
            tokens.expiry_from_choice("forever", now=NOW)

    def test_states(self):
        self.assertEqual(tokens.link_state(expires_at=None, revoked_at=None, now=NOW), "active")
        self.assertEqual(
            tokens.link_state(expires_at=NOW + timedelta(seconds=1), revoked_at=None, now=NOW), "active"
        )
        self.assertEqual(tokens.link_state(expires_at=NOW, revoked_at=None, now=NOW), "expired")
        self.assertEqual(
            tokens.link_state(expires_at=NOW - timedelta(days=1), revoked_at=NOW, now=NOW), "revoked"
        )

    def test_public_url_puts_token_in_path(self):
        url = tokens.public_url("https://app.example.com/", "abc")
        self.assertEqual(url, "https://app.example.com/s/abc")
        self.assertNotIn("?", url)


if __name__ == "__main__":
    unittest.main()
