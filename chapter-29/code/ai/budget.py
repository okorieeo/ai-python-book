from types import SimpleNamespace

from asgiref.sync import sync_to_async

from chat.services import DailyBudgetExceeded, check_daily_token_budget   # Chapter 17

from .errors import AIBudgetExceeded


async def check_budget(user_id: int, estimated_tokens: int) -> None:
    """Chapter 17's daily allowance, adapted to the async service and to our own error type."""
    try:
        await sync_to_async(check_daily_token_budget)(user=SimpleNamespace(pk=user_id), estimated_tokens=estimated_tokens)
    except DailyBudgetExceeded as exc:
        raise AIBudgetExceeded(retry_after=exc.retry_after) from exc
