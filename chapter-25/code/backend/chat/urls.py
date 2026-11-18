# ADD to your chat/urls.py (or your Chapter 12 router setup):
from django.urls import path

from .views import MessageCreateView

urlpatterns = [
    path("conversations/<uuid:conversation_id>/messages/", MessageCreateView.as_view(), name="message-create"),
]
