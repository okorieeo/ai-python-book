from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import AskView, DocumentViewSet

router = DefaultRouter()
router.register("documents", DocumentViewSet, basename="knowledge-document")

urlpatterns = [path("", include(router.urls)), path("ask/", AskView.as_view(), name="knowledge-ask")]
