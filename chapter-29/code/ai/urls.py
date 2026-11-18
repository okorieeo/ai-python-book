from django.urls import path

from .views import chat_stream

urlpatterns = [
    path("conversations/<int:conversation_id>/stream/", chat_stream, name="chat-stream"),
]
