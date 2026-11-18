from django.urls import path

from .api import MyBillingView, PlanListView

urlpatterns = [
    path("plans/", PlanListView.as_view(), name="billing-plans"),
    path("me/", MyBillingView.as_view(), name="billing-me"),
]
