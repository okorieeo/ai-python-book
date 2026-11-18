from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/v1/", include("accounts.urls")),
    path("api/v1/", include("documents.urls")),
    path("api/v1/", include("notifications.urls")),
]
if settings.DEBUG:  # development only: serve uploaded files from MEDIA_ROOT
    urlpatterns += static(
        settings.MEDIA_URL, document_root=settings.MEDIA_ROOT
    )
