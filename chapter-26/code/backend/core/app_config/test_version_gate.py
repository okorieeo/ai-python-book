import unittest

from .version_gate import (GatePolicy, PolicyError, build_response, parse_version, policy_from_env)


class ParseVersionTests(unittest.TestCase):
    def test_parses(self):
        self.assertEqual(parse_version("1.20.3"), (1, 20, 3))

    def test_numeric_not_text_order(self):
        self.assertGreater(parse_version("1.10.0"), parse_version("1.9.0"))

    def test_rejects_garbage(self):
        for bad in ["", "1.2", "1.2.3.4", "v1.2.3", "1.2.3-beta", "a.b.c", None]:
            with self.subTest(bad=bad), self.assertRaises(PolicyError):
                parse_version(bad)


class BuildResponseTests(unittest.TestCase):
    def policy(self, **kw):
        base = dict(min_version="1.2.0", recommended_version="1.4.0", store_url_ios="https://apps.apple.com/app/id1",
                    store_url_android="https://play.google.com/store/apps/details?id=x")
        base.update(kw)
        return GatePolicy(**base)

    def test_picks_store_url_by_platform(self):
        self.assertTrue(build_response(self.policy(), "ios")["store_url"].startswith("https://apps.apple.com"))
        self.assertTrue(build_response(self.policy(), "android")["store_url"].startswith("https://play.google.com"))

    def test_unknown_platform_rejected(self):
        for bad in ["windows", "", "IOS", "ios; drop"]:
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                build_response(self.policy(), bad)

    def test_minimum_above_recommended_is_an_error(self):
        with self.assertRaises(PolicyError):
            build_response(self.policy(min_version="2.0.0"), "ios")

    def test_message_is_capped(self):
        self.assertEqual(len(build_response(self.policy(message="x" * 1000), "ios")["message"]), 300)

    def test_shape_matches_what_the_app_expects(self):
        keys = {"min_version", "recommended_version", "store_url", "maintenance", "message"}
        self.assertEqual(set(build_response(self.policy(), "ios")), keys)


class PolicyFromEnvTests(unittest.TestCase):
    def test_defaults_mean_no_restriction(self):
        p = policy_from_env({})
        self.assertEqual((p.min_version, p.recommended_version, p.maintenance), ("1.0.0", "1.0.0", False))

    def test_recommended_defaults_to_minimum(self):
        self.assertEqual(policy_from_env({"MOBILE_MIN_VERSION": "1.3.0"}).recommended_version, "1.3.0")

    def test_maintenance_flag_spellings(self):
        for yes in ["1", "true", "TRUE", " yes ", "on"]:
            self.assertTrue(policy_from_env({"MOBILE_MAINTENANCE": yes}).maintenance, yes)
        for no in ["", "0", "false", "no", "off", "maybe"]:
            self.assertFalse(policy_from_env({"MOBILE_MAINTENANCE": no}).maintenance, no)


if __name__ == "__main__":
    unittest.main()
