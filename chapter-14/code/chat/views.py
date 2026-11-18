from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import render
from django.views.decorators.http import require_POST

from . import services
from .models import Conversation
from .ws_auth import TICKET_MAX_AGE_SECONDS, make_ticket

@require_POST
def ws_ticket(request):
    """POST /api/v1/ws-ticket: a logged-in user receives a 30-second, single-use WebSocket ticket."""
    if not request.user.is_authenticated:
        return JsonResponse({"error": {"code": "not_authenticated", "message": "Log in first."},
                             "request_id": getattr(request, "request_id", None)}, status=401)
    return JsonResponse({"ticket": make_ticket(request.user), "expires_in": TICKET_MAX_AGE_SECONDS})

@login_required(login_url="/admin/login/")
def chat_demo(request):
    """Development-only page to try the WebSocket by hand. Log in through /admin/ first."""
    conversation = (Conversation.objects.filter(user=request.user, title="WebSocket demo").first()
                    or services.create_conversation(user=request.user, title="WebSocket demo"))
    return render(request, "chat/demo.html", {"conversation": conversation})
