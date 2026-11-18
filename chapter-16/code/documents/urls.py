from django.urls import path

from . import views

urlpatterns = [
    path("documents", views.DocumentList.as_view()),
    path("documents/upload-url", views.UploadUrlView.as_view()),
    path("documents/complete", views.CompleteUploadView.as_view()),
    path("documents/<uuid:public_id>", views.DocumentDetail.as_view()),
    path(
        "documents/<uuid:public_id>/download",
        views.DocumentDownload.as_view(),
    ),
    path("me/avatar", views.AvatarView.as_view()),
]
