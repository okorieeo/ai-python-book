# config/urls.py (inside urlpatterns)
from django.urls import path
from rest_framework.routers import DefaultRouter

from assistant import views as assistant_views
from schedule import views as schedule_views
from tasks.views import TaskViewSet

router = DefaultRouter()
router.register("tasks", TaskViewSet, basename="task")

urlpatterns += [
    path("api/v1/", include(router.urls)),
    path("api/v1/events/", schedule_views.EventListView.as_view()),
    path("api/v1/events/<uuid:public_id>/", schedule_views.EventDetailView.as_view()),
    path("api/v1/preferences/", schedule_views.PreferencesView.as_view()),
    path("api/v1/assistant/messages/", assistant_views.MessageView.as_view()),
    path("api/v1/assistant/actions/<uuid:action_id>/", assistant_views.DecisionView.as_view()),
    path("api/v1/assistant/new/", assistant_views.NewChatView.as_view()),
    path("api/v1/devices/", assistant_views.PushDeviceView.as_view()),
]

# config/asgi.py or routing.py (next to your chat route from Chapter 14)
from django.urls import re_path
from assistant.consumers import AssistantConsumer

websocket_urlpatterns += [re_path(r"^ws/assistant/$", AssistantConsumer.as_asgi())]
