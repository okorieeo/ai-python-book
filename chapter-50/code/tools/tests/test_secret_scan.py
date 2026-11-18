import tempfile
import unittest
from pathlib import Path

from tools import secret_scan as ss

# Fake secrets are assembled at run time so this file does not itself look like a leak.
AWS = "AKIA" + "ABCDEFGHIJKLMNOP"
GH = "ghp_" + "a1B2c3D4e5F6g7H8i9J0k1L2m3N4o5P6q7R8"
STRIPE = "sk_" + "live_" + "4eC39HqLyjWDarjtT1zdp7dc"
ANTHROPIC = "sk-" + "ant-" + "api03-AbCdEfGhIjKlMnOpQrStUv"
JWT = "eyJhbGciOiJIUzI1NiJ9" + ".eyJzdWIiOiIxMjM0NTY3ODkwIn0" + ".dBjftJeZ4CVPmB92K27uhbUJU1p1r"
PRIV = "-----BEGIN " + "RSA PRIVATE KEY-----"


def rules(line):
    return [r for r, _ in ss.scan_line(line)]


class LineTests(unittest.TestCase):
    def test_known_formats(self):
        self.assertIn("aws-access-key", rules(f'key = "{AWS}"'))
        self.assertIn("github-token", rules(f"token: {GH}"))
        self.assertIn("stripe-or-paystack-live-key", rules(f"STRIPE={STRIPE}"))
        self.assertIn("anthropic-key", rules(f"ANTHROPIC_API_KEY={ANTHROPIC}"))
        self.assertIn("jwt", rules(f"Authorization: Bearer {JWT}"))
        self.assertIn("private-key", rules(PRIV))

    def test_password_in_connection_string(self):
        self.assertIn("password-in-url", rules("DATABASE_URL=postgres://app:Zq8vK2mXw9@db.internal:5432/app"))  # secretscan:allow (fake value for a test)

    def test_generic_assignment_needs_entropy_and_no_placeholder(self):
        self.assertTrue(rules('API_KEY = "Zq8vK2mXw9Lp4TnB7sRd"'))  # secretscan:allow (fake value for a test)
        self.assertFalse(rules('API_KEY = "your-api-key-goes-here-please"'))
        self.assertFalse(rules('SECRET_KEY = os.environ["SECRET_KEY"]'))
        self.assertFalse(rules('password = "aaaaaaaaaaaaaaaaaaaa"'))

    def test_placeholders_and_normal_code_are_quiet(self):
        for line in ("DATABASE_URL=postgres://aichat:${POSTGRES_PASSWORD}@db:5432/aichat",
                     "url = 'postgres://user:password@localhost/db'",
                     "def make_token(): return secrets.token_urlsafe(32)",
                     "const token = await getToken();"):
            self.assertEqual(rules(line), [], line)

    def test_allow_marker(self):
        self.assertEqual(rules(f'x = "{AWS}"  # secretscan:allow'), [])

    def test_preview_never_shows_the_secret(self):
        for _, value in ss.scan_line(f"k = {GH}"):
            self.assertNotIn(GH[8:], ss.preview(value))
            self.assertEqual(len(ss.preview(value)), 10)


class DiffTests(unittest.TestCase):
    DIFF = ("diff --git a/app/settings.py b/app/settings.py\n--- a/app/settings.py\n+++ b/app/settings.py\n@@ -10,2 +10,4 @@\n"
            " DEBUG = False\n+STRIPE_KEY = \"" + STRIPE + "\"\n+NAME = 'x'\n OTHER = 1\n"
            "diff --git a/.env.example b/.env.example\n--- a/.env.example\n+++ b/.env.example\n@@ -0,0 +1 @@\n+STRIPE_KEY=" + STRIPE + "\n")

    def test_reports_file_and_new_line_number(self):
        found = ss.scan_diff(self.DIFF)
        self.assertEqual(len(found), 1)
        self.assertEqual((found[0].file, found[0].line), ("app/settings.py", 11))

    def test_removed_lines_are_ignored(self):
        diff = "+++ b/a.py\n@@ -1 +1 @@\n-k = \"" + STRIPE + "\"\n+k = os.environ['K']\n"
        self.assertEqual(ss.scan_diff(diff), [])


class PathTests(unittest.TestCase):
    def test_scans_files_and_skips_vendor_folders(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            (root / "a.py").write_text(f'x = "{AWS}"\n')
            (root / "node_modules").mkdir()
            (root / "node_modules" / "b.js").write_text(f'x = "{AWS}"\n')
            (root / ".env").write_text(f"STRIPE={STRIPE}\n")
            found = ss.scan_paths([root])
            self.assertEqual(sorted(Path(f.file).name for f in found), [".env", "a.py"])


if __name__ == "__main__":
    unittest.main()
