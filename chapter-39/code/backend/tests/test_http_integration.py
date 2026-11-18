"""A REAL HTTP round trip: a server on a random local port, a signed request over a socket, the real endpoint logic."""
import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from billing.endpoint import handle_webhook_request
from billing.handlers import Order
from scripts.send_webhook import build_request, send
from testsupport.signing import paystack_event, stripe_event

STRIPE_SECRET, PAYSTACK_SECRET = "whsec_test_secret_for_unit_tests", "sk_test_paystack_secret_for_unit_tests"
CHECKOUT = stripe_event("evt_http_1", "checkout.session.completed", {"client_reference_id": "7", "metadata": {"credits": "100"}})


@pytest.fixture
def server(config, store, handlers):
    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            provider = self.path.rstrip("/").rsplit("/", 1)[-1]
            body = self.rfile.read(int(self.headers.get("Content-Length", 0)))   # the RAW bytes, untouched
            status, payload = handle_webhook_request(provider, dict(self.headers), body, config=config, store=store,
                                                     handlers=handlers, now=time.time())
            out = json.dumps(payload).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(out)))
            self.end_headers()
            self.wfile.write(out)

        def log_message(self, *args):       # keep test output quiet
            pass

    httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{httpd.server_address[1]}/api/v1/webhooks"
    httpd.shutdown()
    httpd.server_close()


def post(url, provider, event, secret, **kw):
    headers, body = build_request(provider, event, secret, **kw)
    return send(f"{url}/{provider}/", headers, body)


def test_a_signed_stripe_event_over_real_http_is_processed_once(server, state):
    status, text = post(server, "stripe", CHECKOUT, STRIPE_SECRET)
    assert (status, json.loads(text)) == (200, {"status": "processed"})
    status, text = post(server, "stripe", CHECKOUT, STRIPE_SECRET)
    assert json.loads(text) == {"status": "duplicate"}
    assert state.credits == {7: 100}


def test_tampering_after_signing_is_caught_over_the_wire(server, state):
    status, _ = post(server, "stripe", CHECKOUT, STRIPE_SECRET, tamper=True)
    assert status == 400
    assert state.credits == {}


def test_a_stale_timestamp_is_caught_over_the_wire(server, state):
    assert post(server, "stripe", CHECKOUT, STRIPE_SECRET, age=3600)[0] == 400
    assert state.credits == {}


def test_a_signature_made_with_the_wrong_secret_is_caught(server):
    assert post(server, "stripe", CHECKOUT, "whsec_attacker")[0] == 400


def test_paystack_over_real_http_including_a_replay(server, state):
    state.orders["ref-9"] = Order("ref-9", 7, 250_000, "NGN", credits=40)
    event = paystack_event("charge.success", {"id": 9, "reference": "ref-9", "amount": 250_000, "currency": "NGN"})
    assert post(server, "paystack", event, PAYSTACK_SECRET)[0] == 200
    assert post(server, "paystack", event, PAYSTACK_SECRET)[0] == 200
    assert state.credits == {7: 40}                       # twice delivered, paid once
    assert post(server, "paystack", event, PAYSTACK_SECRET, tamper=True)[0] == 400


def test_an_unknown_path_is_a_404(server):
    headers, body = build_request("stripe", CHECKOUT, STRIPE_SECRET)
    assert send(f"{server}/paypal/", headers, body)[0] == 404
