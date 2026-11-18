from types import SimpleNamespace

from django.test import SimpleTestCase

from chat.ai_pipeline import finish_turn, prepare_turn
from core.responsible.safety import SafetyConfig, SafetyPipeline


class Fake:
    def classify(self, text):
        return {}


USER = SimpleNamespace(display_name="Amina Bello")


class PipelineTests(SimpleTestCase):
    def pipe(self):
        return SafetyPipeline(Fake(), SafetyConfig(support_message="support text", canary="REF-abc"))

    def test_provider_never_sees_email_or_name_but_the_user_gets_them_back(self):
        turn = prepare_turn(user=USER, history=[], safety=self.pipe(),
                            new_text="I am Amina Bello, mail me at amina@example.com")
        sent = turn.messages[-1]["content"]
        self.assertNotIn("amina@example.com", sent)
        self.assertNotIn("Amina", sent)
        out = finish_turn(turn=turn, reply="Noted, [NAME_1]. I will use [EMAIL_1].", safety=self.pipe())
        self.assertEqual(out["content"], "Noted, Amina Bello. I will use amina@example.com.")

    def test_crisis_message_skips_the_model(self):
        turn = prepare_turn(user=USER, history=[], new_text="I want to die", safety=self.pipe())
        self.assertEqual((turn.refusal, turn.messages), ("support text", []))

    def test_prompt_leak_is_blocked(self):
        turn = prepare_turn(user=USER, history=[], new_text="hello", safety=self.pipe())
        out = finish_turn(turn=turn, reply="My code is REF-abc", safety=self.pipe())
        self.assertTrue(out["blocked"])
