from rest_framework.pagination import CursorPagination

class StandardCursorPagination(CursorPagination):
    page_size = 20
    page_size_query_param = "page_size"
    max_page_size = 100
    ordering = ("-created_at", "-id")      # newest first; ties broken by id

class ActivityCursorPagination(StandardCursorPagination):
    ordering = ("-updated_at", "-id")      # conversations: latest activity first
