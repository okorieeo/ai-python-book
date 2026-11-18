import unittest

from core.app_version import BadVersion, needs_update, parse_version


class AppVersionTests(unittest.TestCase):
    def test_parse(self):
        self.assertEqual(parse_version("1.4"), (1, 4, 0))
        self.assertEqual(parse_version("1.4.2"), (1, 4, 2))
        self.assertEqual(parse_version(" 2.0.1-beta.3 "), (2, 0, 1))

    def test_parse_rejects_junk(self):
        for bad in ("", "x", "1", "1.2.3.4", "1.a.3", None):
            with self.assertRaises(BadVersion):
                parse_version(bad)

    def test_numbers_compare_as_numbers_not_text(self):
        self.assertTrue(needs_update("1.9.0", "1.10.0"))   # as text, "1.9.0" > "1.10.0"
        self.assertFalse(needs_update("1.10.0", "1.9.0"))

    def test_equal_and_newer_are_fine(self):
        self.assertFalse(needs_update("1.4.0", "1.4"))
        self.assertFalse(needs_update("2.0.0", "1.4.0"))

    def test_old_client_is_told_to_update(self):
        self.assertTrue(needs_update("1.3.9", "1.4.0"))

    def test_missing_or_unreadable_header_does_not_block(self):
        self.assertFalse(needs_update(None, "1.4.0"))
        self.assertFalse(needs_update("", "1.4.0"))
        self.assertFalse(needs_update("garbage", "1.4.0"))


if __name__ == "__main__":
    unittest.main()
