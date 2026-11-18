class AgentRun(models.Model):
    class Status(models.TextChoices):
        PAUSED = "paused"
        RESUMING = "resuming"      # claimed by one request; stops double clicks
        FINISHED = "finished"

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    status = models.CharField(max_length=20, choices=Status.choices)
    state = models.JSONField()     # RunState.to_json(), stored as JSON
    expires_at = models.DateTimeField()

class RunDecisionView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, run_id):
        with transaction.atomic():
            run = get_object_or_404(
                AgentRun.objects.select_for_update().filter(
                    user=request.user,                   # only your own runs
                    status=AgentRun.Status.PAUSED,
                    expires_at__gt=timezone.now(),
                ),
                pk=run_id,
            )
            run.status = AgentRun.Status.RESUMING        # claim it
            run.save(update_fields=["status"])

        # The slow part (a model call) happens outside the transaction.
        decisions = {str(k): v is True for k, v in request.data.get("decisions", {}).items()}
        ctx = ToolContext(user_id=request.user.id, role=role_of(request.user),
                          services=ChatService(request.user))
        try:
            result = build_agent().resume(RunState.from_json(json.dumps(run.state)), decisions, ctx)
        except ValueError:
            return Response({"detail": "Invalid decision."}, status=400)
        save_result(run, result)       # FINISHED, or PAUSED again with new state
        return Response(serialize(result))
