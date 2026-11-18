from django.urls import path

from . import views

urlpatterns = [
    path("plans/", views.PlanListView.as_view()),
    path("subscription/", views.SubscriptionView.as_view()),
    path("checkout/", views.CheckoutView.as_view()),
    path("portal/", views.PortalView.as_view()),
    path("webhooks/<str:provider>/", views.webhook),
]
