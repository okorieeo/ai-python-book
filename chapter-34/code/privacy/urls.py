from django.urls import path

from . import views

urlpatterns = [
    path("consent/", views.ConsentView.as_view()),
    path("consent/accept/", views.AcceptDocumentsView.as_view()),
    path("export/", views.ExportView.as_view()),
    path("delete/", views.DeleteAccountView.as_view()),
]
