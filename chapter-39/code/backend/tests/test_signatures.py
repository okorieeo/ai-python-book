import pytest

from billing import webhooks
from billing.webhooks import (SignatureError, compute_paystack_signature, compute_stripe_signature,
                              verify_paystack_signature, verify_stripe_signature)

SECRET = "whsec_unit"
PAYLOAD = b'{"id":"evt_1","type":"invoice.paid"}'
NOW = 1_700_000_000


def header(payload=PAYLOAD, secret=SECRET, t=NOW):
    return f"t={t},v1={compute_stripe_signature(secret, t, payload)}"


class TestStripe:
    def test_a_correct_signature_is_accepted_and_returns_the_timestamp(self):
        assert verify_stripe_signature(PAYLOAD, header(), [SECRET], now=NOW) == NOW

    @pytest.mark.parametrize("payload", [
        b'{"id":"evt_1","type":"invoice.paid" }',          # one extra space
        b'{"id":"evt_2","type":"invoice.paid"}',           # a different id
        b"",                                               # emptied
    ], ids=["extra-space", "other-id", "empty"])
    def test_any_change_to_the_body_is_rejected(self, payload):
        with pytest.raises(SignatureError, match="no matching signature"):
            verify_stripe_signature(payload, header(), [SECRET], now=NOW)

    def test_the_wrong_secret_is_rejected(self):
        with pytest.raises(SignatureError):
            verify_stripe_signature(PAYLOAD, header(secret="whsec_other"), [SECRET], now=NOW)

    def test_changing_the_timestamp_in_the_header_breaks_the_signature(self):
        sig = compute_stripe_signature(SECRET, NOW, PAYLOAD)
        with pytest.raises(SignatureError, match="no matching signature"):
            verify_stripe_signature(PAYLOAD, f"t={NOW + 1},v1={sig}", [SECRET], now=NOW)

    @pytest.mark.parametrize("age,ok", [(0, True), (299, True), (300, True), (301, False), (-299, True), (-301, False), (86_400, False)],
                             ids=["now", "299s-old", "300s-old", "301s-old", "299s-future", "301s-future", "a-day-old"])
    def test_the_tolerance_window_in_both_directions(self, age, ok):
        h = header(t=NOW - age)
        if ok:
            assert verify_stripe_signature(PAYLOAD, h, [SECRET], now=NOW) == NOW - age
        else:
            with pytest.raises(SignatureError, match="tolerance"):
                verify_stripe_signature(PAYLOAD, h, [SECRET], now=NOW)

    def test_a_custom_tolerance_is_honoured(self):
        with pytest.raises(SignatureError):
            verify_stripe_signature(PAYLOAD, header(t=NOW - 61), [SECRET], now=NOW, tolerance=60)

    @pytest.mark.parametrize("bad,why", [
        (None, "missing"), ("", "missing"), ("garbage", "no timestamp"), ("v1=abc", "no timestamp"),
        ("t=123", "no v1"), ("t=abc,v1=def", "not a number"), ("t=,v1=def", "not a number"),
    ])
    def test_malformed_headers_are_rejected_with_a_reason(self, bad, why):
        with pytest.raises(SignatureError, match=why):
            verify_stripe_signature(PAYLOAD, bad, [SECRET], now=NOW)

    def test_secret_rotation_either_signature_or_either_secret_will_do(self):
        good = compute_stripe_signature(SECRET, NOW, PAYLOAD)
        two_v1 = f"t={NOW},v1={'0' * 64},v1={good}"
        assert verify_stripe_signature(PAYLOAD, two_v1, [SECRET], now=NOW) == NOW
        old = compute_stripe_signature("whsec_old", NOW, PAYLOAD)
        assert verify_stripe_signature(PAYLOAD, f"t={NOW},v1={old}", ["whsec_new", "whsec_old"], now=NOW) == NOW

    def test_only_the_v1_scheme_counts(self):
        good = compute_stripe_signature(SECRET, NOW, PAYLOAD)
        with pytest.raises(SignatureError, match="no v1"):
            verify_stripe_signature(PAYLOAD, f"t={NOW},v0={good}", [SECRET], now=NOW)

    def test_spaces_after_commas_are_tolerated(self):
        good = compute_stripe_signature(SECRET, NOW, PAYLOAD)
        assert verify_stripe_signature(PAYLOAD, f"t={NOW}, v1={good}", [SECRET], now=NOW) == NOW

    def test_no_secrets_configured_accepts_nothing(self):
        with pytest.raises(SignatureError):
            verify_stripe_signature(PAYLOAD, header(), [], now=NOW)

    def test_the_comparison_is_constant_time(self, monkeypatch):
        """A timing property cannot be seen from outside, so pin it: the check must go through compare_digest."""
        calls = []
        real = webhooks.hmac.compare_digest
        monkeypatch.setattr(webhooks.hmac, "compare_digest", lambda a, b: calls.append(1) or real(a, b))
        verify_stripe_signature(PAYLOAD, header(), [SECRET], now=NOW)
        assert calls

    def test_the_signed_string_is_timestamp_dot_body(self):
        """Pins the scheme itself, so a refactor cannot quietly change what is signed."""
        import hashlib, hmac as h
        expected = h.new(SECRET.encode(), f"{NOW}.".encode() + PAYLOAD, hashlib.sha256).hexdigest()
        assert compute_stripe_signature(SECRET, NOW, PAYLOAD) == expected


class TestPaystack:
    SK = "sk_test_unit"

    def test_a_correct_signature_is_accepted(self):
        verify_paystack_signature(PAYLOAD, compute_paystack_signature(self.SK, PAYLOAD), self.SK)

    def test_the_signature_is_sha512_hex(self):
        assert len(compute_paystack_signature(self.SK, PAYLOAD)) == 128

    @pytest.mark.parametrize("payload", [PAYLOAD + b" ", b"{}", b""], ids=["trailing-space", "other-body", "empty"])
    def test_a_changed_body_is_rejected(self, payload):
        with pytest.raises(SignatureError):
            verify_paystack_signature(payload, compute_paystack_signature(self.SK, PAYLOAD), self.SK)

    def test_the_wrong_key_and_missing_header_are_rejected(self):
        with pytest.raises(SignatureError):
            verify_paystack_signature(PAYLOAD, compute_paystack_signature("sk_other", PAYLOAD), self.SK)
        for missing in (None, ""):
            with pytest.raises(SignatureError, match="missing"):
                verify_paystack_signature(PAYLOAD, missing, self.SK)

    def test_a_stripe_style_sha256_signature_is_not_accepted(self):
        import hashlib, hmac as h
        weaker = h.new(self.SK.encode(), PAYLOAD, hashlib.sha256).hexdigest()
        with pytest.raises(SignatureError):
            verify_paystack_signature(PAYLOAD, weaker, self.SK)

    def test_surrounding_whitespace_in_the_header_is_trimmed(self):
        verify_paystack_signature(PAYLOAD, "  " + compute_paystack_signature(self.SK, PAYLOAD) + "\n", self.SK)
