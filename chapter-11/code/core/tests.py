from django.test import TestCase

class HealthTests(TestCase):
    def test_health_returns_ok_and_request_id(self):
        response = self.client.get("/api/v1/health")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "ok", "database": "ok"})
        self.assertTrue(response["X-Request-ID"].startswith("req_"))

    def test_valid_incoming_request_id_is_kept(self):
        response = self.client.get("/api/v1/health", headers={"X-Request-ID": "abc-12345678"})
        self.assertEqual(response["X-Request-ID"], "abc-12345678")

    def test_invalid_incoming_request_id_is_replaced(self):
        response = self.client.get("/api/v1/health", headers={"X-Request-ID": "bad id with spaces!"})
        self.assertTrue(response["X-Request-ID"].startswith("req_"))

    def test_health_only_allows_get(self):
        response = self.client.post("/api/v1/health")
        self.assertEqual(response.status_code, 405)
