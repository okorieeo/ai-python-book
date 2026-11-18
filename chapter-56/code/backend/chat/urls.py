from django.urls import path

from . import views

urlpatterns = [
    path("conversations/", views.ConversationListView.as_view()),
    path("conversations/<uuid:public_id>/", views.ConversationDetailView.as_view()),
    path("conversations/<uuid:public_id>/messages/", views.MessageListView.as_view()),
]
