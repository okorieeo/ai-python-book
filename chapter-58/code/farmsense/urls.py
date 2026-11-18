from django.urls import path

from . import ingest_view, views

urlpatterns = [
    path("api/ingest/", ingest_view.ingest),                                              # devices
    path("api/alerts/<int:alert_id>/ack/", views.AlertAckView.as_view()),                 # people
    path("api/sensors/<int:sensor_id>/readings/", views.ReadingsView.as_view()),
    path("api/farms/<int:farm_id>/members/<int:member_id>/", views.MemberRoleView.as_view()),
    path("api/farms/<int:farm_id>/insights/<str:day>/", views.InsightView.as_view()),
    path("api/push-tokens/", views.PushTokenView.as_view()),
]
