"""Django tests for the assistant service. NOT run while writing Chapter 59 (see the chapter): run them in your project.

They use the scripted fake model from test_agent.py, so no network and no API key are needed.
Adapt make_user() to the required fields of your own user model (Chapter 13).
"""
import json
from unittest import mock

from django.contrib.auth import get_user_model
from django.test import TestCase

from assistant import services
from assistant.models import AssistantUsage, PendingAction
from assistant.test_agent import ScriptedModel, text, use
from audit.models import AuditEvent
from tasks.models import Task


def make_user(n: int):
    return get_user_model().objects.create_user(email=f"user{n}@example.com", password="x" * 20)


class AssistantServiceTests(TestCase):
    def setUp(self):
        self.ada, self.bo = make_user(1), make_user(2)
        budget = mock.patch("assistant.services.check_daily_token_budget")
        budget.start()
        self.addCleanup(budget.stop)

    def run_with(self, user, *turns, message="do it"):
        model = ScriptedModel(*turns)
        with mock.patch("assistant.services.get_model_client", return_value=model):
            return services.send_message(user=user, text=message)

    def test_a_write_tool_runs_and_the_conversation_is_saved(self):
        outcome = self.run_with(self.ada, use(("a", "create_task", {"title": "Pay rent", "priority": 3})), text("Added."))
        self.assertEqual((outcome.status, outcome.text), ("done", "Added."))
        self.assertEqual(Task.objects.get(user=self.ada).title, "Pay rent")
        self.assertEqual(AssistantUsage.objects.filter(user=self.ada).count(), 1)

    def test_delete_waits_for_the_person_and_runs_once(self):
        task = Task.objects.create(user=self.ada, title="Old")
        outcome = self.run_with(self.ada, use(("a", "delete_task", {"id": str(task.public_id)})))
        self.assertEqual(outcome.status, "needs_confirmation")
        self.assertTrue(Task.objects.filter(pk=task.pk).exists())          # nothing deleted yet
        self.assertIn("Old", outcome.pending[0]["summary"])
        action_id = outcome.pending[0]["action_id"]

        with mock.patch("assistant.services.get_model_client", return_value=ScriptedModel(text("Deleted it."))):
            done = services.decide(user=self.ada, action_id=action_id, approve=True)
        self.assertEqual(done.status, "done")
        self.assertFalse(Task.objects.filter(pk=task.pk).exists())
        self.assertTrue(AuditEvent.objects.filter(action="assistant.action_confirmed").exists())
        with self.assertRaises(PendingAction.DoesNotExist):                 # the row is gone after the decision
            services.decide(user=self.ada, action_id=action_id, approve=True)

    def test_declining_keeps_the_task(self):
        task = Task.objects.create(user=self.ada, title="Keep me")
        outcome = self.run_with(self.ada, use(("a", "delete_task", {"id": str(task.public_id)})))
        with mock.patch("assistant.services.get_model_client", return_value=ScriptedModel(text("Okay."))):
            services.decide(user=self.ada, action_id=outcome.pending[0]["action_id"], approve=False)
        self.assertTrue(Task.objects.filter(pk=task.pk).exists())

    def test_a_new_message_is_refused_while_a_question_is_open(self):
        task = Task.objects.create(user=self.ada, title="x")
        self.run_with(self.ada, use(("a", "delete_task", {"id": str(task.public_id)})))
        with self.assertRaises(services.AssistantBusy):
            self.run_with(self.ada, text("hello"))

    def test_someone_elses_action_does_not_exist(self):
        task = Task.objects.create(user=self.ada, title="x")
        outcome = self.run_with(self.ada, use(("a", "delete_task", {"id": str(task.public_id)})))
        with self.assertRaises(PendingAction.DoesNotExist):
            services.decide(user=self.bo, action_id=outcome.pending[0]["action_id"], approve=True)

    def test_the_model_cannot_touch_another_users_data(self):
        theirs = Task.objects.create(user=self.bo, title="Bo's private task")
        model = ScriptedModel(use(("a", "update_task", {"id": str(theirs.public_id), "title": "hacked"})), text("Sorry."))
        with mock.patch("assistant.services.get_model_client", return_value=model):
            services.send_message(user=self.ada, text="rename that task")
        theirs.refresh_from_db()
        self.assertEqual(theirs.title, "Bo's private task")
        first_result = json.loads(model.seen[1][-1]["content"][0]["content"])
        self.assertEqual(first_result["error"], "not_found")               # same answer as for an id that never existed
