import pytest

from billing.endpoint import WebhookConfig, handle_webhook_request
from billing.handlers import BillingState, build_handlers
from billing.webhooks import MemoryIdempotencyStore
from testsupport.clock import FakeClock
from testsupport.netblock import block_network
from testsupport.signing import paystack_headers, stripe_headers, to_bytes

STRIPE_SECRET = "whsec_test_secret_for_unit_tests"
PAYSTACK_SECRET = "sk_test_paystack_secret_for_unit_tests"


@pytest.fixture(autouse=True)
def no_network():
    """Every test runs with the internet switched off. Loopback stays open for tests that start a server."""
    with block_network():
        yield


@pytest.fixture
def clock():
    return FakeClock()


@pytest.fixture
def state():
    return BillingState()


@pytest.fixture
def store():
    return MemoryIdempotencyStore()


@pytest.fixture
def handlers(state):
    return build_handlers(state)


@pytest.fixture
def config():
    return WebhookConfig(stripe_secrets=(STRIPE_SECRET,), paystack_secret=PAYSTACK_SECRET)


@pytest.fixture
def deliver(config, store, handlers, clock):
    """Sign an event like the provider would and hand it to the endpoint. Returns (status, body)."""
    def _deliver(provider, event, *, secret=None, age=0, body=None, headers=None, cfg=None):
        payload = body if body is not None else to_bytes(event)
        if headers is None:
            if provider == "stripe":
                headers = stripe_headers(payload, secret or STRIPE_SECRET, int(clock() - age))
            else:
                headers = paystack_headers(payload, secret or PAYSTACK_SECRET)
        return handle_webhook_request(provider, headers, payload, config=cfg or config, store=store,
                                      handlers=handlers, now=clock())
    return _deliver
