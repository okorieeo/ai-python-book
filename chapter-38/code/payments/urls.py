from django.urls import path

from . import views

urlpatterns = [
    path("webhooks/stripe/", views.StripeWebhookView.as_view()),
    path("webhooks/paystack/", views.PaystackWebhookView.as_view()),
    path("checkout/", views.CheckoutView.as_view()),
    path("<str:reference>/", views.PaymentStatusView.as_view()),
]
