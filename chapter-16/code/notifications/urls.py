from django.urls import path

from . import inbound, views

urlpatterns = [
    path("webhooks/mailer", inbound.MailerWebhook.as_view()),
    path("webhook-endpoints", views.EndpointList.as_view()),
    path(
        "webhook-endpoints/<uuid:public_id>", views.EndpointDetail.as_view()
    ),
]
