DAYS = OpenApiParameter("days", int, description="1 to 365 (default 30)")

def parse_int(request, name, default, low, high):
    raw = request.query_params.get(name, default)
    try:
        value = int(raw)
    except (TypeError, ValueError):
        value = low - 1
    if not low <= value <= high:
        raise ValidationError(
            {name: [f"Enter a whole number from {low} to {high}."]})
    return value

class AnalyticsView(APIView):
    permission_classes = [IsAuthenticated, has_permission("view_analytics")]

# ----------------------------------------------------------------- numbers
class OverviewView(AnalyticsView):
    @extend_schema(summary="Headline numbers", responses=ok(OverviewSerializer))
    def get(self, request):
        today = timezone.localdate()
        week_ago = timezone.now() - timedelta(days=7)
        users = User.objects.aggregate(
            total=Count("id"),
            new=Count("id", filter=Q(date_joined__gte=week_ago)))
        tokens = UsageRecord.objects.filter(created_at__date=today).aggregate(
            i=Sum("input_tokens"), o=Sum("output_tokens"))
        data = {
            "users_total": users["total"],
            "users_new_7d": users["new"],
            "tokens_today": (tokens["i"] or 0) + (tokens["o"] or 0),
            "messages_today": Message.objects.filter(
                created_at__date=today).count(),
            "documents_total": Document.objects.count(),
        }
        return Response(OverviewSerializer(data).data)

class UsageSeriesView(AnalyticsView):
    @extend_schema(summary="Tokens per day, one point for every day",
                   parameters=[DAYS], responses=ok(UsageSeriesSerializer))
    def get(self, request):
        days = parse_int(request, "days", 30, 1, 365)
        today = timezone.localdate()
        start = today - timedelta(days=days - 1)
        rows = (UsageRecord.objects.filter(created_at__date__gte=start)
                .annotate(day=TruncDate("created_at")).values("day")
                .annotate(i=Sum("input_tokens"), o=Sum("output_tokens"),
                          calls=Count("id")))
        by_day = {row["day"]: row for row in rows}
        series = []
        for n in range(days):                     # zero-fill: charts hate gaps
            day = start + timedelta(days=n)
            row = by_day.get(day, {})
            series.append({"date": day, "input_tokens": row.get("i", 0),
                           "output_tokens": row.get("o", 0),
                           "calls": row.get("calls", 0)})
        payload = {"days": days, "series": series}
        return Response(UsageSeriesSerializer(payload).data)

class TopUsersView(AnalyticsView):
    @extend_schema(summary="Heaviest users", parameters=[DAYS],
                   responses=ok(TopUserSerializer(many=True)))
    def get(self, request):
        days = parse_int(request, "days", 30, 1, 365)
        limit = parse_int(request, "limit", 5, 1, 20)
        since = timezone.now() - timedelta(days=days)
        rows = (UsageRecord.objects.filter(created_at__gte=since)
                .values("user__username")
                .annotate(tokens=Sum(F("input_tokens") + F("output_tokens")))
                .order_by("-tokens", "user__username")[:limit])
        data = [{"username": r["user__username"], "tokens": r["tokens"]}
                for r in rows]
        return Response(TopUserSerializer(data, many=True).data)

class DocumentStatusView(AnalyticsView):
    @extend_schema(summary="Documents per status",
                   responses=ok(StatusCountSerializer(many=True)))
    def get(self, request):
        counts = dict(Document.objects.values_list("status")
                      .annotate(n=Count("id")))
        data = [{"status": s, "count": counts.get(s, 0)}
                for s in Document.Status.values]
        return Response(StatusCountSerializer(data, many=True).data)
# ----- next listing from the chapter -----
# ------------------------------------------------------------------ users
class AdminPagination(PageNumberPagination):
    """Admins want page numbers and totals, so this table uses a count."""

    page_size = 20
    page_size_query_param = "page_size"
    max_page_size = 100

DANGEROUS_START = ("=", "+", "-", "@", "\t", "\r")

def safe_cell(value):
    """Stop spreadsheets from running a username like =HYPERLINK(...)."""
    if value is None:
        return ""
    text = str(value)
    return "'" + text if text.startswith(DANGEROUS_START) else text

class AdminUserViewSet(mixins.ListModelMixin, viewsets.GenericViewSet):
    serializer_class = AdminUserSerializer
    permission_classes = [IsAuthenticated, has_permission("view_users")]
    pagination_class = AdminPagination
    filterset_class = AdminUserFilter
    search_fields = ["username", "email"]
    ordering_fields = ["username", "date_joined", "last_login",
                       "conversation_count", "tokens_30d"]
    ordering = ["-date_joined"]
    queryset = User.objects.none()                 # for the docs generator

    def get_queryset(self):
        since = timezone.now() - timedelta(days=30)
        tokens = (UsageRecord.objects
                  .filter(user=OuterRef("pk"), created_at__gte=since)
                  .values("user")
                  .annotate(total=Sum(F("input_tokens") + F("output_tokens")))
                  .values("total"))
        return User.objects.annotate(
            conversation_count=Count(
                "conversations", distinct=True,
                filter=Q(conversations__deleted_at__isnull=True)),
            tokens_30d=Coalesce(Subquery(tokens), Value(0)),
        )

    def filter_queryset(self, queryset):
        queryset = super().filter_queryset(queryset)
        return queryset.order_by(*queryset.query.order_by, "pk")   # stable pages

    def get_throttles(self):
        if self.action == "export":
            self.throttle_scope = "export"            # exports are expensive
        return super().get_throttles()
# ----- next listing from the chapter -----
    @extend_schema(summary="Download the filtered users as CSV",
                   responses={(200, "text/csv"): OpenApiTypes.STR})
    @action(detail=False, url_path="export",
            permission_classes=[IsAuthenticated, has_permission("export_users")])
    def export(self, request):
        columns = ["username", "email", "role", "is_active", "date_joined",
                   "last_login", "conversation_count", "tokens_30d"]
        rows = self.filter_queryset(self.get_queryset())

        def lines():
            buffer = io.StringIO()
            writer = csv.writer(buffer)
            writer.writerow(columns)
            for user in rows.iterator(chunk_size=500):    # never load all rows
                writer.writerow([safe_cell(getattr(user, c)) for c in columns])
                yield buffer.getvalue()
                buffer.seek(0)
                buffer.truncate(0)

        response = StreamingHttpResponse(lines(), content_type="text/csv")
        response["Content-Disposition"] = 'attachment; filename="users.csv"'
        return response
