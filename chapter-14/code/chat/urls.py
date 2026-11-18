# add chat/urls.py:
from django.urls import path
from . import views

urlpatterns = [
    path("ws-ticket", views.ws_ticket, name="ws-ticket"),
]
