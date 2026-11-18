# ======================== config/urls.py after Chapter 14 ========================
from django.conf import settings
from django.contrib import admin
from django.urls import include, path

from chat import views as chat_views

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/v1/", include("core.urls")),
    path("api/v1/", include("chat.urls")),
]

if settings.DEBUG:
    urlpatterns += [path("chat-demo/", chat_views.chat_demo)]          # the hand-testing page (development only)
    if "debug_toolbar" in settings.INSTALLED_APPS:
        urlpatterns += [path("__debug__/", include("debug_toolbar.urls"))]
