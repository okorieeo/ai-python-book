from django.urls import path

from .views import AppConfigView

urlpatterns = [path("app-config/", AppConfigView.as_view(), name="app-config")]
