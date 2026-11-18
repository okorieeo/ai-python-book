import unittest

from .errors import (AIAuthError, AIBadRequest, AIBillingError, AIContextTooLong, AIOverloaded, AIRateLimited,
                     AIServerError, AITimeout)
from .provider_errors import error_for_status, parse_retry_after


class StatusMappingTests(unittest.TestCase):
    def test_each_documented_status(self):
        expected = {429: AIRateLimited, 529: AIOverloaded, 504: AITimeout, 413: AIContextTooLong, 402: AIBillingError,
                    401: AIAuthError, 403: AIAuthError, 500: AIServerError, 502: AIServerError, 400: AIBadRequest,
                    404: AIBadRequest}
        for status, cls in expected.items():
            self.assertIsInstance(error_for_status(status), cls, status)

    def test_only_provider_side_problems_allow_fallback(self):
        for status in (429, 529, 504, 500, 502):
            self.assertTrue(error_for_status(status).fallback_ok, status)
        for status in (400, 401, 402, 403, 404, 413):
            self.assertFalse(error_for_status(status).fallback_ok, status)

    def test_request_id_and_retry_after_travel_with_the_error(self):
        err = error_for_status(429, retry_after=12, request_id="req_abc")
        self.assertEqual((err.retry_after, err.request_id), (12, "req_abc"))

    def test_retry_after_parsing(self):
        self.assertEqual(parse_retry_after("30"), 30)
        self.assertEqual(parse_retry_after("2.7"), 2)
        for bad in (None, "", "soon", "-5"):
            self.assertIsNone(parse_retry_after(bad), bad)

    def test_user_messages_never_mention_the_provider_or_keys(self):
        for status in (400, 401, 402, 403, 413, 429, 500, 504, 529):
            msg = error_for_status(status).user_message.lower()
            for word in ("anthropic", "api key", "claude", "billing", "credit"):
                self.assertNotIn(word, msg, (status, word))


if __name__ == "__main__":
    unittest.main()
