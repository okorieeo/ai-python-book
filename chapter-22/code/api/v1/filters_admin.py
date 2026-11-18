import django_filters

from accounts.models import User

class AdminUserFilter(django_filters.FilterSet):
    class Meta:
        model = User
        fields = ["role", "is_active"]            # nothing else is filterable
