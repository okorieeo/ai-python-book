"""Turn a verified BillingEvent into a change in our database. Gateway-agnostic."""
from __future__ import annotations

import logging
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.db import IntegrityError, transaction
from django.utils import timezone

from .gateways.base import BillingEvent
from .models import Plan, Subscription, WebhookEvent
from .notify import notify_plan_changed

logger = logging.getLogger(__name__)
User = get_user_model()

APPLIED, DUPLICATE, STALE, UNMATCHED, REJECTED = "applied", "duplicate", "stale", "unmatched_user", "rejected"


def _resolve_user(ev: BillingEvent):
    """Find our user for an event. The id we put in the checkout metadata is the most trustworthy."""
    if ev.user_public_id:
        user = User.objects.filter(public_id=ev.user_public_id).first()
        if user:
            return user
    for field, value in (("external_subscription_id", ev.external_subscription_id),
                         ("external_customer_id", ev.external_customer_id)):
        if value:
            sub = Subscription.objects.filter(gateway=ev.provider, **{field: value}).select_related("user").first()
            if sub:
                return sub.user
    if ev.customer_email:  # last resort: the email we sent to the gateway at checkout
        return User.objects.filter(email__iexact=ev.customer_email).first()
    return None


def _resolve_plan(ev: BillingEvent) -> Plan | None:
    qs = Plan.objects.all()
    if ev.plan_code and (plan := qs.filter(code=ev.plan_code).first()):
        return plan
    if ev.price_ref:
        field = "stripe_price_id" if ev.provider == "stripe" else "paystack_plan_code"
        return qs.filter(**{field: ev.price_ref}).first()
    return None


def apply_event(ev: BillingEvent) -> str:
    """Apply one gateway event exactly once. Returns an outcome string; raises only on real failures
    (so the gateway retries). Everything happens in ONE transaction: an error rolls back the
    'seen' marker too, which is what lets the retry succeed."""
    with transaction.atomic():
        try:
            with transaction.atomic():  # savepoint, so the IntegrityError does not poison the outer transaction
                record = WebhookEvent.objects.create(provider=ev.provider, event_id=ev.event_id,
                                                     event_type=ev.event_type)
        except IntegrityError:
            return DUPLICATE

        outcome = _apply(ev)
        record.outcome = outcome
        record.save(update_fields=["outcome"])
        return outcome


def _apply(ev: BillingEvent) -> str:
    user = _resolve_user(ev)
    if user is None:
        logger.error("billing event %s/%s matches no user", ev.provider, ev.event_id)
        return UNMATCHED

    sub = Subscription.objects.select_for_update().filter(user=user).first()
    plan = _resolve_plan(ev) or (sub.plan if sub else None)
    if plan is None or not plan.is_paid:
        logger.error("billing event %s/%s matches no paid plan", ev.provider, ev.event_id)
        return REJECTED

    # Never grant value for the wrong amount (Paystack lets the client influence the charge).
    expected = plan.expected_amount(ev.provider)
    if ev.kind == "ACTIVE" and ev.amount_minor is not None and expected is not None and (
            ev.amount_minor != expected):
        logger.error("amount mismatch for %s/%s: got %s expected %s", ev.provider, ev.event_id,
                     ev.amount_minor, expected)
        return REJECTED

    if sub and sub.last_event_at and ev.occurred_at and ev.occurred_at < sub.last_event_at:
        return STALE  # an older event arrived after a newer one; ignoring it keeps the newer state

    if sub is None:
        sub = Subscription(user=user, plan=plan)
    sub.plan = plan if ev.kind == "ACTIVE" else sub.plan
    sub.gateway = ev.provider
    sub.external_customer_id = ev.external_customer_id or sub.external_customer_id
    sub.external_subscription_id = ev.external_subscription_id or sub.external_subscription_id

    if ev.kind == "ACTIVE":
        sub.status = Subscription.Status.ACTIVE
        sub.cancel_at_period_end = ev.cancel_at_period_end
        if ev.period_end:
            sub.current_period_end = ev.period_end
        elif not ev.cancel_at_period_end:  # a payment without an explicit period: extend by one billing period
            base = max(timezone.now(), sub.current_period_end or timezone.now())
            sub.current_period_end = base + timedelta(days=plan.period_days)
    elif ev.kind == "PAST_DUE":
        sub.status = Subscription.Status.PAST_DUE
    else:  # CANCELED
        sub.status = Subscription.Status.CANCELED
        sub.cancel_at_period_end = False

    if ev.occurred_at:
        sub.last_event_at = ev.occurred_at
    sub.save()
    transaction.on_commit(lambda: notify_plan_changed(user))  # only tell the browser once the data is committed
    return APPLIED
