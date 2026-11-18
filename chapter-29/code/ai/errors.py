"""
The errors the rest of the app sees. The provider adapter translates SDK exceptions into
these, so nothing outside ai/anthropic_client.py ever imports `anthropic`.
"""
from __future__ import annotations


class AIError(Exception):
    code = "ai_error"
    http_status = 502
    #: A different model might succeed (the problem is the provider, not the request).
    fallback_ok = False
    user_message = "The assistant ran into a problem. Please try again."

    def __init__(self, message: str = "", *, retry_after: int | None = None, request_id: str | None = None):
        super().__init__(message or self.user_message)
        self.retry_after = retry_after
        self.request_id = request_id


class AIRateLimited(AIError):
    code, http_status, fallback_ok = "provider_rate_limited", 503, True
    user_message = "The assistant is very busy right now. Please try again in a moment."


class AIOverloaded(AIError):
    code, http_status, fallback_ok = "provider_overloaded", 503, True
    user_message = "The assistant is very busy right now. Please try again in a moment."


class AITimeout(AIError):
    code, http_status, fallback_ok = "provider_timeout", 504, True
    user_message = "The assistant took too long to answer. Please try again."


class AIConnectionFailed(AIError):
    code, http_status, fallback_ok = "provider_unreachable", 503, True
    user_message = "We could not reach the assistant. Please try again."


class AIServerError(AIError):
    code, http_status, fallback_ok = "provider_error", 502, True


class AIBadRequest(AIError):
    """Our request was invalid. A bug on our side: another model will not help."""
    code, http_status = "bad_request", 500


class AIAuthError(AIError):
    """The API key is wrong or lacks permission. Page someone; do not retry."""
    code, http_status = "provider_auth", 500


class AIBillingError(AIError):
    """The provider account is out of credit or at its spend limit. Page someone."""
    code, http_status = "provider_billing", 503
    user_message = "The assistant is temporarily unavailable."


class AIContextTooLong(AIError):
    code, http_status = "context_too_long", 413
    user_message = "That message is too long for the assistant to read."


class AIBudgetExceeded(AIError):
    code, http_status = "budget_exceeded", 429
    user_message = "You have used today's assistant allowance. It resets automatically."


class AIBusy(AIError):
    code, http_status = "busy", 503
    user_message = "The assistant is very busy right now. Please try again in a moment."


class AIInputError(AIError):
    code, http_status = "invalid_input", 400
    user_message = "That message cannot be sent."


class AIUnavailable(AIError):
    """Every model we are willing to use has failed or is shut off by its circuit breaker."""
    code, http_status = "unavailable", 503
    user_message = "The assistant is temporarily unavailable. Please try again soon."


class AIStreamInterrupted(AIError):
    """The provider failed AFTER some text had already been shown. Cannot be retried silently."""
    code, http_status = "interrupted", 502
    user_message = "The reply was interrupted."

    def __init__(self, partial: str, cause: AIError):
        super().__init__(str(cause), retry_after=cause.retry_after, request_id=cause.request_id)
        self.partial = partial
        self.cause = cause
