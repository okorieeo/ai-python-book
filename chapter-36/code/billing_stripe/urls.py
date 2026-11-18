from django.urls import path

from . import views

urlpatterns = [
    path("checkout/", views.CheckoutView.as_view()),
    path("sync/", views.SyncView.as_view()),
    path("portal/", views.PortalView.as_view()),
    path("status/", views.StatusView.as_view()),
    path("change-plan/", views.ChangePlanView.as_view()),
    path("cancel/", views.CancelView.as_view()),
    path("resume/", views.ResumeView.as_view()),
    path("payment-sheet/", views.PaymentSheetView.as_view()),
    path("stripe/webhook/", views.stripe_webhook),
]
