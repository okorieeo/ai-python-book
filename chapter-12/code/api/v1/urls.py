from django.urls import include, path
from rest_framework.routers import SimpleRouter

from . import views

router = SimpleRouter(trailing_slash=False)
router.register("conversations", views.ConversationViewSet, basename="conversation")
router.register("documents", views.DocumentViewSet, basename="document")

urlpatterns = [
    path("auth/login", views.LoginView.as_view(), name="login"),
    path("auth/refresh", views.RefreshView.as_view(), name="refresh"),
    path("auth/logout", views.LogoutView.as_view(), name="logout"),
    path("me", views.MeView.as_view(), name="me"),
    path("me/usage", views.UsageView.as_view(), name="usage"),
    path("meta/client-config", views.ClientConfigView.as_view()),
    path("health", views.HealthView.as_view()),
    path(
        "conversations/<uuid:conversation_id>/messages",
        views.MessageViewSet.as_view({"get": "list", "post": "create"}),
        name="messages",
    ),
    path("", include(router.urls)),
]
