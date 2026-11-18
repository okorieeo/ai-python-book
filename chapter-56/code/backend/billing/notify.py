"""Tell a user's open chat sockets that their plan changed, so the UI updates without a refresh."""
import logging

from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer

logger = logging.getLogger(__name__)


def user_group(user_id: int) -> str:
    return f"user.{user_id}"


def plan_payload(user) -> dict:
    from billing.entitlements import current_plan

    plan = current_plan(user)
    return {"code": plan.code, "name": plan.name, "daily_message_limit": plan.daily_message_limit}


def notify_plan_changed(user) -> None:
    layer = get_channel_layer()
    if layer is None:
        return
    try:
        async_to_sync(layer.group_send)(user_group(user.pk), {"type": "plan.updated", "plan": plan_payload(user)})
    except Exception:  # a notification must never fail the webhook that caused it
        logger.exception("could not push plan.updated for user %s", user.pk)
