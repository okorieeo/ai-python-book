from unittest import mock

from django.test import override_settings
from rest_framework.test import APITestCase


@override_settings(REST_FRAMEWORK={"DEFAULT_THROTTLE_CLASSES": [], "DEFAULT_THROTTLE_RATES": {"app_config": "1000/min"}})
class AppConfigViewTests(APITestCase):
    url = "/api/v1/app-config/"

    def test_works_without_login(self):
        res = self.client.get(self.url, {"platform": "ios"})
        self.assertEqual(res.status_code, 200)
        self.assertIn("min_version", res.json())

    def test_bad_platform_is_400(self):
        self.assertEqual(self.client.get(self.url, {"platform": "pc"}).status_code, 400)
        self.assertEqual(self.client.get(self.url).status_code, 400)

    def test_policy_comes_from_environment(self):
        with mock.patch.dict("os.environ", {"MOBILE_MIN_VERSION": "2.0.0", "MOBILE_RECOMMENDED_VERSION": "2.1.0"}):
            body = self.client.get(self.url, {"platform": "android"}).json()
        self.assertEqual((body["min_version"], body["recommended_version"]), ("2.0.0", "2.1.0"))

    def test_broken_policy_fails_open(self):
        with mock.patch.dict("os.environ", {"MOBILE_MIN_VERSION": "banana"}):
            res = self.client.get(self.url, {"platform": "ios"})
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()["min_version"], "1.0.0")

    def test_cacheable_for_a_minute(self):
        res = self.client.get(self.url, {"platform": "ios"})
        self.assertEqual(res["Cache-Control"], "public, max-age=60")
