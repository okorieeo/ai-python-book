"""
Send a correctly SIGNED webhook to a URL, for testing an endpoint by hand or in a test.
Works for both providers and needs only the standard library.

    python -m scripts.send_webhook --provider stripe   --url http://localhost:8000/api/v1/webhooks/stripe/ \
        --secret whsec_test --event fixtures/checkout_completed.json
    python -m scripts.send_webhook --provider paystack --url http://localhost:8000/api/v1/webhooks/paystack/ \
        --secret sk_test_xxx --event fixtures/charge_success.json --repeat 2     # also tests idempotency

--tamper changes the body AFTER signing (expect 400). --age SECONDS back-dates a Stripe timestamp (expect 400
beyond the tolerance). Use the secret of the MODE you are testing: test and live differ.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.error
import urllib.request

from testsupport.signing import paystack_headers, stripe_headers, to_bytes


def build_request(provider: str, event: dict, secret: str, *, now: float | None = None, age: int = 0,
                  tamper: bool = False) -> tuple[dict[str, str], bytes]:
    body = to_bytes(event)
    if provider == "stripe":
        headers = stripe_headers(body, secret, int((now if now is not None else time.time()) - age))
    elif provider == "paystack":
        headers = paystack_headers(body, secret)
    else:
        raise ValueError("provider must be stripe or paystack")
    if tamper:
        body = body.replace(b"}", b" }", 1)               # one extra space is enough to invalidate a signature
    return headers, body


def send(url: str, headers: dict[str, str], body: bytes, timeout: float = 10.0) -> tuple[int, str]:
    req = urllib.request.Request(url, data=body, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, resp.read().decode()
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read().decode()


def main(argv: list[str]) -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--provider", required=True, choices=["stripe", "paystack"])
    p.add_argument("--url", required=True)
    p.add_argument("--secret", required=True)
    p.add_argument("--event", required=True, help="path to a JSON file with the event")
    p.add_argument("--repeat", type=int, default=1)
    p.add_argument("--tamper", action="store_true")
    p.add_argument("--age", type=int, default=0)
    a = p.parse_args(argv)
    event = json.load(open(a.event, encoding="utf-8"))
    worst = 0
    for i in range(a.repeat):
        headers, body = build_request(a.provider, event, a.secret, age=a.age, tamper=a.tamper)
        status, text = send(a.url, headers, body)
        print(f"delivery {i + 1}: HTTP {status} {text}")
        worst = max(worst, status)
    return 0 if worst < 400 else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
