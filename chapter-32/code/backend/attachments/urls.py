from django.urls import path

from . import views

urlpatterns = [
    path("attachments/", views.AttachmentUploadView.as_view(), name="attachment-upload"),
    path("attachments/<uuid:attachment_id>/", views.AttachmentDetailView.as_view(), name="attachment-detail"),
    path("dictation/", views.DictationView.as_view(), name="dictation"),
    path("messages/<uuid:message_id>/speech/", views.SpeakMessageView.as_view(), name="message-speech"),
]
