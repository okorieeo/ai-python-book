path("conversations/<uuid:public_id>", views.detail, name="conversation-detail")
path("users/<int:pk>", views.user_detail)
path("pages/<slug:slug>", views.page)

# in Python: build URLs from names instead of hard-coding them
from django.urls import reverse
reverse("health")                                                    # "/api/v1/health"
reverse("conversation-detail", kwargs={"public_id": conversation.public_id})
