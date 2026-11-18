from django.urls import path

from billing.views import webhook

urlpatterns = [path("api/v1/webhooks/<str:provider>/", webhook, name="webhook")]
