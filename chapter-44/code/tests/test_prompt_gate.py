import unittest

from hookutil import run_hook

import prompt_gate

# Fake values assembled from pieces so this file itself contains nothing a secret scanner would flag.
FAKE = {
    "anthropic": "sk-" + "ant-api03-" + "A" * 40,
    "openai": "sk-" + "B" * 40,
    "stripe_live": "sk_" + "live_" + "C" * 24,
    "stripe_restricted": "rk_" + "live_" + "D" * 24,
    "webhook": "whsec_" + "E" * 32,
    "aws": "AKIA" + "F" * 16,
    "github": "ghp_" + "G" * 36,
    "private_key": "-----BEGIN " + "RSA PRIVATE KEY-----",
    "db_url": "postgres://app:" + "hunter22" + "@db.internal:5432/chat",
}


class Detection(unittest.TestCase):
    def test_each_kind_is_found(self):
        for name, value in FAKE.items():
            with self.subTest(kind=name):
                self.assertTrue(prompt_gate.find_secrets(f"why does this fail? {value} is in my config"), name)

    def test_test_mode_keys_and_normal_text_are_allowed(self):
        for text in ["use sk_test_abc123 in the sandbox", "ask-me-anything about the ask-ant farm", "postgres://app@db/chat has no password",
                     "set STRIPE_WEBHOOK_SECRET in .env", "whsec_ is the prefix of webhook secrets", "AKIA is a prefix", "the key sk- was removed",
                     "please add a /health endpoint", ""]:
            with self.subTest(text=text):
                self.assertEqual(prompt_gate.find_secrets(text), [], text)

    def test_names_describe_what_was_found(self):
        self.assertEqual(prompt_gate.find_secrets(FAKE["stripe_live"]), ["a live Stripe or Paystack secret key"])

    def test_several_secrets_are_all_reported(self):
        self.assertEqual(len(prompt_gate.find_secrets(FAKE["aws"] + " " + FAKE["github"])), 2)


class Protocol(unittest.TestCase):
    def test_a_secret_blocks_the_prompt_with_exit_2_and_a_message_for_the_person(self):
        code, out, err = run_hook("prompt_gate.py", {"hook_event_name": "UserPromptSubmit", "prompt": f"debug this: {FAKE['stripe_live']}"})
        self.assertEqual(code, 2)
        self.assertIn("Prompt blocked", err)
        self.assertIn("by NAME", err)
        self.assertNotIn(FAKE["stripe_live"], err)               # the message must not repeat the secret

    def test_a_clean_prompt_passes(self):
        self.assertEqual(run_hook("prompt_gate.py", {"prompt": "add a rename endpoint"})[:2], (0, None))

    def test_a_missing_prompt_field_passes(self):
        self.assertEqual(run_hook("prompt_gate.py", {})[:2], (0, None))


if __name__ == "__main__":
    unittest.main()
