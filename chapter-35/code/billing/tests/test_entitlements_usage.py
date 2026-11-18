from unittest import mock

from django.core.exceptions import ValidationError  # noqa: F401
from django.test import override_settings

from billing.entitlements import effective_plan, get_entitlements, has_feature, limit_for
from billing.models import EntitlementOverride, Subscription, UsageEvent
from billing.registry import UnknownEntitlement
from billing.subscriptions import mark_past_due, start_subscription
from billing.usage import (LimitExceeded, check_can_use, check_stock_limit, record_usage, usage_summary)

from .base import BillingTestCase, at


class EntitlementTests(BillingTestCase):
    def test_a_user_with_no_subscription_gets_the_free_plan(self):
        plan, sub = effective_plan(self.alice, at(2026, 1, 1))
        self.assertEqual((plan.code, sub), ("free", None))
        self.assertTrue(has_feature(self.alice, "ai.chat"))
        self.assertFalse(has_feature(self.alice, "ai.agent_tools"))
        self.assertEqual(limit_for(self.alice, "ai.messages_per_month"), 30)

    def test_a_paid_plan_unlocks_its_entitlements(self):
        start_subscription(self.alice, self.price("pro"), now=at(2026, 1, 1))
        now = at(2026, 1, 10)
        self.assertTrue(has_feature(self.alice, "ai.premium_models", now))
        self.assertEqual(limit_for(self.alice, "ai.messages_per_month", now), 1500)
        self.assertIsNone(limit_for(self.alice, "chat.max_conversations", now))  # unlimited
        self.assertFalse(has_feature(self.bob, "ai.premium_models", now))  # other users are unaffected

    def test_unknown_keys_raise_instead_of_quietly_denying(self):
        with self.assertRaises(UnknownEntitlement):
            has_feature(self.alice, "ai.teleport")

    def test_access_survives_a_late_renewal_message_but_not_forever(self):
        start_subscription(self.alice, self.price("pro"), now=at(2026, 1, 1))  # period ends 1 Feb 12:00
        self.assertEqual(effective_plan(self.alice, at(2026, 2, 3))[0].code, "pro")   # 2 days late: grace
        self.assertEqual(effective_plan(self.alice, at(2026, 2, 5))[0].code, "free")  # 4 days late: over

    def test_past_due_keeps_access_for_the_grace_days_then_drops_to_free(self):
        sub = start_subscription(self.alice, self.price("pro"), now=at(2026, 1, 1))
        mark_past_due(sub)
        self.assertEqual(effective_plan(self.alice, at(2026, 2, 7))[0].code, "pro")   # 6 days after end
        self.assertEqual(effective_plan(self.alice, at(2026, 2, 9))[0].code, "free")  # 8 days after end

    @override_settings(BILLING_PAST_DUE_GRACE_DAYS=0, BILLING_RENEWAL_GRACE_DAYS=0)
    def test_grace_days_come_from_settings(self):
        sub = start_subscription(self.alice, self.price("pro"), now=at(2026, 1, 1))
        mark_past_due(sub)
        self.assertEqual(effective_plan(self.alice, at(2026, 2, 1, 13))[0].code, "free")

    def test_ended_subscriptions_give_no_access(self):
        sub = start_subscription(self.alice, self.price("pro"), now=at(2026, 1, 1))
        sub.status = Subscription.Status.CANCELED
        sub.save()
        self.assertEqual(effective_plan(self.alice, at(2026, 1, 10))[0].code, "free")

    def test_overrides_grant_restrict_and_expire(self):
        now = at(2026, 1, 10)
        EntitlementOverride.objects.create(user=self.alice, key="ai.agent_tools", enabled=True,
                                           reason="beta tester", expires_at=at(2026, 1, 20))
        EntitlementOverride.objects.create(user=self.alice, key="ai.messages_per_month", limit=100,
                                           reason="support gesture")
        self.assertTrue(has_feature(self.alice, "ai.agent_tools", now))
        self.assertEqual(limit_for(self.alice, "ai.messages_per_month", now), 100)
        self.assertEqual(get_entitlements(self.alice, now)["ai.agent_tools"].source, "override")
        self.assertFalse(has_feature(self.alice, "ai.agent_tools", at(2026, 1, 21)))  # expired
        self.assertFalse(has_feature(self.bob, "ai.agent_tools", now))

    def test_the_newest_override_wins_and_a_disabled_limit_means_zero(self):
        EntitlementOverride.objects.create(user=self.alice, key="ai.chat", enabled=True, reason="a")
        EntitlementOverride.objects.create(user=self.alice, key="ai.chat", enabled=False, reason="abuse")
        EntitlementOverride.objects.create(user=self.alice, key="ai.messages_per_month", enabled=False, reason="x")
        self.assertFalse(has_feature(self.alice, "ai.chat", at(2026, 1, 1)))
        self.assertEqual(limit_for(self.alice, "ai.messages_per_month", at(2026, 1, 1)), 0)


class UsageTests(BillingTestCase):
    def test_recording_is_idempotent(self):
        now = at(2026, 1, 5)
        e1, created1 = record_usage(self.alice, "ai.message", 1, "req-1", now=now)
        e2, created2 = record_usage(self.alice, "ai.message", 1, "req-1", now=now)
        self.assertEqual((created1, created2, e1.pk == e2.pk), (True, False, True))
        self.assertEqual(UsageEvent.objects.filter(user=self.alice).count(), 1)

    def test_a_lost_race_returns_the_existing_event(self):
        now = at(2026, 1, 5)
        first, _ = record_usage(self.alice, "ai.message", 1, "req-race", now=now)
        with mock.patch("billing.usage.UsageEvent.objects.filter") as fake_filter:
            fake_filter.return_value.first.return_value = None  # we "did not see" it, so we try to insert
            event, created = record_usage(self.alice, "ai.message", 1, "req-race", now=now)
        self.assertFalse(created)
        self.assertEqual(event.pk, first.pk)
        self.assertEqual(UsageEvent.objects.count(), 1)

    def test_the_free_limit_is_enforced(self):
        now = at(2026, 1, 5)
        for i in range(30):
            record_usage(self.alice, "ai.message", 1, f"r{i}", enforce=True, now=now)
        with self.assertRaises(LimitExceeded) as ctx:
            record_usage(self.alice, "ai.message", 1, "r30", enforce=True, now=now)
        self.assertEqual((ctx.exception.limit, ctx.exception.used), (30, 30))
        self.assertEqual(UsageEvent.objects.filter(user=self.alice).count(), 30)

    def test_check_does_not_record_and_recording_after_the_fact_never_refuses(self):
        now = at(2026, 1, 5)
        record_usage(self.alice, "ai.message", 30, "bulk", now=now)
        with self.assertRaises(LimitExceeded):
            check_can_use(self.alice, "ai.message", 1, now)
        record_usage(self.alice, "ai.message", 1, "already-happened", now=now)  # enforce defaults to False
        self.assertEqual(usage_summary(self.alice, now)["ai.messages_per_month"]["used"], 31)

    def test_one_users_usage_never_counts_against_another(self):
        now = at(2026, 1, 5)
        record_usage(self.alice, "ai.message", 30, "a", now=now)
        check_can_use(self.bob, "ai.message", 1, now)  # no error

    def test_free_users_reset_each_calendar_month(self):
        record_usage(self.alice, "ai.message", 30, "jan", now=at(2026, 1, 31, 23))
        check_can_use(self.alice, "ai.message", 1, at(2026, 2, 1, 1))  # a new month: room again
        with self.assertRaises(LimitExceeded):
            check_can_use(self.alice, "ai.message", 1, at(2026, 1, 31, 23))

    def test_paid_users_reset_on_their_billing_date_not_the_calendar(self):
        start_subscription(self.alice, self.price("starter"), now=at(2026, 1, 14))  # period 14 Jan - 14 Feb
        record_usage(self.alice, "ai.message", 300, "p1", now=at(2026, 1, 20))
        with self.assertRaises(LimitExceeded):
            check_can_use(self.alice, "ai.message", 1, at(2026, 2, 3))   # still the same billing period
        summary = usage_summary(self.alice, at(2026, 2, 3))["ai.messages_per_month"]
        self.assertEqual((summary["used"], summary["remaining"]), (300, 0))

    def test_unlimited_and_unmetered_things_are_never_refused(self):
        check_can_use(self.alice, "something.else", 10**9)  # no limit is registered for it
        EntitlementOverride.objects.create(user=self.alice, key="ai.messages_per_month", limit=None, reason="vip")
        record_usage(self.alice, "ai.message", 5000, "big", enforce=True, now=at(2026, 1, 5))

    def test_stock_limits_use_the_count_you_pass_in(self):
        check_stock_limit(self.alice, "chat.max_conversations", current_count=4)  # free: 5
        with self.assertRaises(LimitExceeded):
            check_stock_limit(self.alice, "chat.max_conversations", current_count=5)

    def test_quantity_must_be_positive(self):
        with self.assertRaises(ValueError):
            record_usage(self.alice, "ai.message", 0, "zero")

    def test_cost_and_metadata_are_stored(self):
        e, _ = record_usage(self.alice, "ai.message", 1, "c1", cost_micro_usd=10_850, meta={"model": "m"})
        e.refresh_from_db()
        self.assertEqual((e.cost_micro_usd, e.meta), (10_850, {"model": "m"}))
