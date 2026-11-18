from django.urls import path

from .views import MessageFeedbackView

urlpatterns = [path("messages/<int:message_id>/feedback/", MessageFeedbackView.as_view(), name="message-feedback")]
