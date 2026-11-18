from django.urls import path

from . import views

urlpatterns = [
    path("conversations/<uuid:conversation_id>/share/", views.ShareLinkListCreateView.as_view()),
    path("conversations/<uuid:conversation_id>/share/<uuid:link_id>/", views.ShareLinkDetailView.as_view()),
    path("public/shared/<str:token>/", views.PublicSharedConversationView.as_view()),
]
# config/urls.py:  path("api/v1/", include("sharing.urls")),
