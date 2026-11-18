"""The only file that talks to Paystack. Everything else works with plain dictionaries.

Uses the `requests` package. Paystack has no official Python SDK to depend on, and the API is small:
every call is a JSON request with the secret key as a Bearer token, and every answer has the shape
{"status": true or false, "message": "...", "data": {...}}.
Not run against the real service in this chapter (no network, no keys); the tests pass a stand-in session.
"""
from typing import Optional

from .errors import PaystackApiError, PaystackNetworkError

BASE_URL = "https://api.paystack.co"


class PaystackGateway:
    def __init__(self, secret_key: str, *, session=None, timeout=(5, 30)):
        if not secret_key.startswith(("sk_test_", "sk_live_")):
            raise ValueError("Use the secret key (sk_test_... or sk_live_...) on the server. Never the public key.")
        if session is None:
            import requests  # imported here so the rest of the package needs nothing installed

            session = requests.Session()
        self._key, self.session, self.timeout = secret_key, session, timeout

    def _request(self, method: str, path: str, *, json: Optional[dict] = None, params: Optional[dict] = None):
        """One call. Network failures and 5xx answers are retryable; anything else Paystack refused is not."""
        try:
            response = self.session.request(
                method, BASE_URL + path, json=json, params=params, timeout=self.timeout,
                headers={"Authorization": f"Bearer {self._key}", "Content-Type": "application/json"})
        except Exception as error:
            raise PaystackNetworkError(f"Could not reach Paystack ({type(error).__name__})") from None
        if response.status_code >= 500:
            raise PaystackNetworkError(f"Paystack answered HTTP {response.status_code}")
        try:
            body = response.json()
        except ValueError:
            raise PaystackApiError(f"Paystack sent a non-JSON answer (HTTP {response.status_code})", response.status_code) from None
        if not body.get("status"):
            raise PaystackApiError(body.get("message") or "Paystack refused the request", response.status_code)
        return body.get("data")

    # ---- payments --------------------------------------------------------------------------------
    def initialize_transaction(self, params: dict) -> dict:
        return self._request("POST", "/transaction/initialize", json=params)

    def verify_transaction(self, reference: str) -> dict:
        return self._request("GET", f"/transaction/verify/{reference}")

    # ---- customers, plans and subscriptions -------------------------------------------------------
    def fetch_customer(self, email_or_code: str) -> dict:
        return self._request("GET", f"/customer/{email_or_code}")

    def create_plan(self, params: dict) -> dict:
        return self._request("POST", "/plan", json=params)

    def create_subscription(self, params: dict) -> dict:
        return self._request("POST", "/subscription", json=params)

    def fetch_subscription(self, code: str) -> dict:
        return self._request("GET", f"/subscription/{code}")

    def disable_subscription(self, code: str, token: str) -> dict:
        return self._request("POST", "/subscription/disable", json={"code": code, "token": token})

    def enable_subscription(self, code: str, token: str) -> dict:
        return self._request("POST", "/subscription/enable", json={"code": code, "token": token})

    def manage_link(self, code: str) -> str:
        return self._request("GET", f"/subscription/{code}/manage/link")["link"]
