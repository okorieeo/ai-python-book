from django.urls import path

from . import views

urlpatterns = [
    path("pay/", views.PayView.as_view()),
    path("subscribe/", views.SubscribeView.as_view()),
    path("verify/", views.VerifyView.as_view()),
    path("status/", views.StatusView.as_view()),
    path("cancel/", views.CancelView.as_view()),
    path("resume/", views.ResumeView.as_view()),
    path("change-plan/", views.ChangePlanView.as_view()),
    path("card-link/", views.CardLinkView.as_view()),
    path("webhook/", views.paystack_webhook),
]
