from django.core.exceptions import ValidationError  # noqa: F401
from django.test import override_settings
from rest_framework.response import Response
from rest_framework.test import APIClient, APIRequestFactory
from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated

from billing.ai import check_before_model_call, pick_model, record_ai_message
from billing.models import EntitlementOverride, UsageEvent, WebhookEvent
from billing.permissions import FeatureNotInPlan, entitlement_required
from billing.seed import seed_default_plans
from billing.subscriptions import start_subscription
from billing.usage import LimitExceeded, record_usage
from billing.webhooks import process_once, record_webhook

from .base import BillingTestCase, at


class WebhookTests(BillingTestCase):
    def test_the_same_event_is_stored_once(self):
        e1, c1 = record_webhook("stripe", "evt_1", "invoice.paid", {"a": 1})
        e2, c2 = record_webhook("stripe", "evt_1", "invoice.paid", {"a": 1})
        self.assertEqual((c1, c2, e1.pk == e2.pk), (True, False, True))
        self.assertEqual(WebhookEvent.objects.count(), 1)

    def test_a_handler_runs_once_even_if_the_event_arrives_twice(self):
        calls = []
        event, _ = record_webhook("stripe", "evt_2", "x", {})
        self.assertTrue(process_once(event, lambda e: calls.append(e.event_id)))
        again, _ = record_webhook("stripe", "evt_2", "x", {})
        self.assertFalse(process_once(again, lambda e: calls.append("second run")))
        self.assertEqual(calls, ["evt_2"])
        self.assertEqual(WebhookEvent.objects.get(event_id="evt_2").status, "processed")

    def test_a_failing_handler_keeps_nothing_and_can_be_retried(self):
        event, _ = record_webhook("stripe", "evt_3", "x", {})

        def broken(e):
            record_usage(self.alice, "ai.message", 1, "inside-handler")
            raise RuntimeError("database hiccup")

        self.assertFalse(process_once(event, broken))
        event.refresh_from_db()
        self.assertEqual(event.status, "failed")
        self.assertIn("database hiccup", event.error)
        self.assertFalse(UsageEvent.objects.filter(idempotency_key="inside-handler").exists())  # rolled back
        self.assertTrue(process_once(event, lambda e: None))  # a retry works
        event.refresh_from_db()
        self.assertEqual((event.status, event.error), ("processed", ""))


class ApiTests(BillingTestCase):
    def test_the_plan_list_is_public_and_hides_inactive_plans(self):
        from billing.models import Plan
        Plan.objects.filter(code="starter").update(is_active=False)
        data = APIClient().get("/api/v1/billing/plans/").json()
        self.assertEqual([p["code"] for p in data], ["free", "pro"])
        pro = data[1]
        self.assertIn({"currency": "NGN", "interval": "month", "amount_minor": 4_500_000}, pro["prices"])

    def test_my_billing_needs_a_login(self):
        self.assertIn(APIClient().get("/api/v1/billing/me/").status_code, (401, 403))

    def test_my_billing_shows_only_my_own_plan_and_usage(self):
        start_subscription(self.alice, self.price("pro"))  # starts now, so it is current
        record_usage(self.alice, "ai.message", 7, "a1")
        c = APIClient()
        c.force_authenticate(self.alice)
        mine = c.get("/api/v1/billing/me/").json()
        self.assertEqual(mine["plan"]["code"], "pro")
        self.assertEqual(mine["usage"]["ai.messages_per_month"]["used"], 7)
        c.force_authenticate(self.bob)
        theirs = c.get("/api/v1/billing/me/").json()
        self.assertEqual(theirs["plan"]["code"], "free")
        self.assertEqual(theirs["usage"]["ai.messages_per_month"]["used"], 0)
        self.assertIsNone(theirs["subscription"])

    def test_the_entitlement_permission_blocks_users_without_the_feature(self):
        class AgentView(APIView):
            permission_classes = [IsAuthenticated, entitlement_required("ai.agent_tools")]

            def get(self, request):
                return Response({"ok": True})

        view = AgentView.as_view()
        factory = APIRequestFactory()
        free_req = factory.get("/x")
        free_req.user = self.alice
        from rest_framework.test import force_authenticate
        force_authenticate(free_req, self.alice)
        response = view(free_req)
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.data["detail"].code, "feature_not_in_plan")

        start_subscription(self.bob, self.price("starter"))
        paid_req = factory.get("/x")
        force_authenticate(paid_req, self.bob)
        self.assertEqual(view(paid_req).status_code, 200)

    def test_limit_exceeded_becomes_a_403_with_real_numbers(self):
        class ChatView(APIView):
            def post(self, request):
                raise LimitExceeded("ai.messages_per_month", 30, 30, 1)

        from rest_framework.test import force_authenticate
        req = APIRequestFactory().post("/x")
        force_authenticate(req, self.alice)
        response = ChatView.as_view()(req)
        response.render()
        self.assertEqual(response.status_code, 403)
        body = response.data
        self.assertEqual((body["code"], body["limit"], body["used"]), ("limit_reached", 30, 30))
        self.assertIsInstance(body["limit"], int)  # a number, not the text "30"
        self.assertIn(b'"limit":30', response.content.replace(b" ", b""))


class AiIntegrationTests(BillingTestCase):
    def test_the_plan_picks_the_model(self):
        self.assertEqual(pick_model(self.alice), "claude-haiku-5-5")
        start_subscription(self.bob, self.price("pro"))
        self.assertEqual(pick_model(self.bob), "claude-sonnet-5-5")

    @override_settings(BILLING_MODEL_PREMIUM="some-future-model")
    def test_model_ids_come_from_settings(self):
        start_subscription(self.bob, self.price("pro"))
        self.assertEqual(pick_model(self.bob), "some-future-model")

    def test_check_then_record_then_limit(self):
        for i in range(30):
            check_before_model_call(self.alice)
            record_ai_message(self.alice, request_id=f"r{i}", model_id="claude-haiku-5-5",
                              input_tokens=950, output_tokens=400, cost_usd=0.00054)
        with self.assertRaises(LimitExceeded):
            check_before_model_call(self.alice)
        total = sum(UsageEvent.objects.filter(user=self.alice).values_list("cost_micro_usd", flat=True))
        self.assertEqual(total, 30 * 540)

    def test_recording_the_same_request_twice_counts_once(self):
        for _ in range(2):
            record_ai_message(self.alice, request_id="same", model_id="m", input_tokens=1, output_tokens=1,
                              cost_usd=0.01)
        self.assertEqual(UsageEvent.objects.filter(user=self.alice).count(), 1)

    def test_a_heavier_request_can_count_as_several_messages(self):
        record_ai_message(self.alice, request_id="agent-run", model_id="m", input_tokens=1, output_tokens=1,
                          cost_usd=0.06, conversation_id=1, weight=6)
        from billing.usage import usage_summary
        self.assertEqual(usage_summary(self.alice)["ai.messages_per_month"]["used"], 6)

    def test_users_without_the_chat_feature_are_refused(self):
        EntitlementOverride.objects.create(user=self.alice, key="ai.chat", enabled=False, reason="suspended")
        with self.assertRaises(FeatureNotInPlan):
            check_before_model_call(self.alice)

    def test_stored_metadata_has_ids_and_counts_but_no_text(self):
        e, _ = record_ai_message(self.alice, request_id="m1", model_id="claude-haiku-5-5", input_tokens=10,
                                 output_tokens=5, cost_usd=0.001, conversation_id=42)
        self.assertEqual(set(e.meta), {"model", "in", "out", "conversation"})


class SeedTests(BillingTestCase):
    def test_seeding_twice_changes_nothing(self):
        from billing.models import Plan, PlanEntitlement, Price
        before = (Plan.objects.count(), Price.objects.count(), PlanEntitlement.objects.count())
        seed_default_plans()
        self.assertEqual((Plan.objects.count(), Price.objects.count(), PlanEntitlement.objects.count()), before)
        self.assertEqual(before, (3, 4, 15))


class ReportTests(BillingTestCase):
    def test_cost_by_user_ranks_the_heaviest_users_first(self):
        from billing.reports import cost_by_user
        now = at(2026, 1, 10)
        record_usage(self.alice, "ai.message", 1, "a1", cost_micro_usd=10_850, now=now)
        record_usage(self.alice, "ai.message", 1, "a2", cost_micro_usd=10_850, now=now)
        record_usage(self.bob, "ai.message", 1, "b1", cost_micro_usd=540, now=now)
        record_usage(self.bob, "ai.message", 1, "b0", cost_micro_usd=999_999, now=at(2025, 12, 1))  # outside the range
        rows = cost_by_user(at(2026, 1, 1), at(2026, 2, 1))
        self.assertEqual([(r["user_id"], r["cost_micro_usd"], r["messages"]) for r in rows],
                         [(self.alice.pk, 21_700, 2), (self.bob.pk, 540, 1)])
