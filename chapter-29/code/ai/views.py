import json

from django.http import JsonResponse, StreamingHttpResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from core.async_auth import authenticate, check_burst

from .errors import AIError
from .factory import get_chat_service
from .service import ConversationNotFound
from .sse import to_sse, with_heartbeat


def _json_error(status: int, code: str, message: str, retry_after: int | None = None) -> JsonResponse:
    response = JsonResponse({"code": code, "detail": message}, status=status)
    if retry_after:
        response["Retry-After"] = str(retry_after)
    return response


# csrf_exempt is correct ONLY because auth is a token in the Authorization header, which browsers
# never attach by themselves. If you switch to cookie auth, remove it (Chapter 17).
@csrf_exempt
@require_POST
async def chat_stream(request, conversation_id: int):
    user, drf_request = await authenticate(request)
    if user is None:
        return _json_error(401, "auth_required", "Authentication required.")

    allowed, wait = await check_burst(drf_request)
    if not allowed:
        return _json_error(429, "too_many_requests", "You are sending messages too quickly.", wait)

    try:
        text = json.loads(request.body or b"{}").get("text")
    except (ValueError, AttributeError):
        text = None
    if not isinstance(text, str):
        return _json_error(400, "invalid_input", 'Send JSON like {"text": "..."}.')

    stream = get_chat_service().stream_reply(user_id=user.pk, conversation_id=conversation_id, text=text).__aiter__()

    # Everything that can be refused (input, ownership, budget, context size) happens before the first
    # event, so asking for the first event BEFORE we start the response lets us send a real HTTP status.
    # After the first byte the status is 200 forever, and failures have to travel inside the stream.
    try:
        first = await stream.__anext__()
    except ConversationNotFound:
        return _json_error(404, "not_found", "Conversation not found.")
    except AIError as exc:
        return _json_error(exc.http_status, exc.code, exc.user_message, exc.retry_after)

    async def body():
        yield to_sse(first)
        async for event in stream:
            yield to_sse(event)

    response = StreamingHttpResponse(with_heartbeat(body(), interval=15), content_type="text/event-stream")
    response["Cache-Control"] = "no-cache"
    response["X-Accel-Buffering"] = "no"      # tell nginx-style proxies not to hold the stream back
    return response
