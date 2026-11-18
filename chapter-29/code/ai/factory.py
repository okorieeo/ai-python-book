from functools import lru_cache

from django.conf import settings

from .anthropic_client import AnthropicLLM
from .budget import check_budget
from .prompts import PROMPT_VERSION, SYSTEM_PROMPT
from .resilience import ConcurrencyLimiter
from .service import AISettings, ChatService
from .store import DjangoConversationStore


@lru_cache(maxsize=1)
def get_client() -> AnthropicLLM:
    return AnthropicLLM(api_key=settings.ANTHROPIC_API_KEY, timeout=settings.AI_SDK_TIMEOUT,
                        max_retries=settings.AI_SDK_MAX_RETRIES)


@lru_cache(maxsize=1)
def get_chat_service() -> ChatService:
    """One service per process, so circuit breakers and the concurrency limiter are shared by all requests."""
    return ChatService(
        client=get_client(),
        store=DjangoConversationStore(),
        budget_check=check_budget,
        limiter=ConcurrencyLimiter(settings.AI_MAX_CONCURRENT_STREAMS, wait=2.0),
        settings=AISettings(
            primary_model=settings.AI_PRIMARY_MODEL,
            fallback_model=settings.AI_FALLBACK_MODEL or None,
            system_prompt=SYSTEM_PROMPT,
            prompt_version=PROMPT_VERSION,
            max_output_tokens=settings.AI_MAX_OUTPUT_TOKENS,
            max_input_tokens=settings.AI_MAX_INPUT_TOKENS,
            first_token_timeout=settings.AI_FIRST_TOKEN_TIMEOUT,
        ),
    )
