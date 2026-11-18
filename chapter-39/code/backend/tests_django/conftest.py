import pytest
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient

from testsupport.netblock import block_network


@pytest.fixture(autouse=True)
def no_network():
    with block_network():
        yield


@pytest.fixture(autouse=True)
def webhook_secrets(settings):
    settings.STRIPE_WEBHOOK_SECRETS = ["whsec_test_secret_for_unit_tests"]
    settings.PAYSTACK_SECRET_KEY = "sk_test_paystack_secret_for_unit_tests"


@pytest.fixture
def make_user(db):
    User = get_user_model()
    counter = iter(range(1, 10_000))

    def _make(**extra):
        n = next(counter)
        return User.objects.create_user(username=f"user{n}", email=f"user{n}@example.com", password="pw-for-tests-only", **extra)
    return _make


@pytest.fixture
def alice(make_user):
    return make_user()


@pytest.fixture
def bob(make_user):
    return make_user()


@pytest.fixture
def client_for():
    def _client(user):
        c = APIClient()
        c.force_authenticate(user)         # skips the login flow: that has its own tests
        return c
    return _client
