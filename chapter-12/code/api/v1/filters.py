import django_filters

from chat.models import Document

class DocumentFilter(django_filters.FilterSet):
    created_after = django_filters.IsoDateTimeFilter(
        field_name="created_at", lookup_expr="gte")
    created_before = django_filters.IsoDateTimeFilter(
        field_name="created_at", lookup_expr="lte")

    class Meta:
        model = Document
        fields = ["status"]                        # exact match on status only
