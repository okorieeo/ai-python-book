import logging

from .models import TurnTraceRow
from .tracing import TurnTrace

logger = logging.getLogger("ai.trace")


def db_sink(trace: TurnTrace) -> None:
    """Called when a turn ends. Must never raise: losing a trace is better than breaking a reply."""
    try:
        TurnTraceRow.objects.create(
            user_id=trace.user_id, conversation_id=trace.conversation_id, assistant_message_id=trace.assistant_message_id,
            outcome=trace.outcome, error_code=trace.error_code, first_token_ms=trace.first_token_ms,
            total_ms=trace.total_ms, chunks=trace.chunks, output_chars=trace.output_chars, prompt_version=trace.prompt_version)
        logger.info("ai_trace", extra=trace.as_log())
    except Exception:       # noqa: BLE001
        logger.exception("could not record a turn trace")
