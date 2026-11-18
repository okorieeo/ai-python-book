from django.urls import path

from . import health_views, views

urlpatterns = [
    path("api/documents/", views.DocumentListCreateView.as_view()),
    path("api/documents/<int:pk>/", views.DocumentDetailView.as_view()),
    path("api/ask/", views.AskView.as_view()),
    path("api/usage/", views.UsageView.as_view()),
    path("health/live", health_views.live),
    path("health/ready", health_views.ready),
]
