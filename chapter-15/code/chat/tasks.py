def _fail(document, reason):
    document.status = Document.Status.FAILED
    document.error = reason[:500]
    document.save(update_fields=["status", "error"])
    logger.warning("document %s failed: %s", document.pk, reason)

@shared_task(
    bind=True,
    autoretry_for=(TransientError,),   # retry these, and only these
    retry_backoff=2,                   # wait about 2s, 4s, 8s, 16s ...
    retry_backoff_max=60,
    retry_jitter=True,                 # randomise, so retries do not stampede
    max_retries=4,
    acks_late=True,                    # acknowledge after the work, not before
    soft_time_limit=100,
    time_limit=120,
)
def ingest_document(self, document_id):
    document = Document.objects.filter(pk=document_id).first()
    if document is None or document.status != Document.Status.PROCESSING:
        return "skipped"               # deleted, or already handled
    try:
        chunks = extract_chunks(document, attempt=self.request.retries)
    except PermanentError as exc:
        _fail(document, str(exc))
        return "failed"
    except TransientError:
        if self.request.retries >= self.max_retries:
            _fail(document, "Gave up after several attempts. Try again later.")
            return "failed"
        raise                          # autoretry_for schedules the retry
    document.chunk_count = len(chunks)
    document.status = Document.Status.READY
    document.save(update_fields=["chunk_count", "status"])
    return f"ready:{len(chunks)}"
# ----- next listing from the chapter -----
# ------------------------------------------------------------ scheduled jobs
@shared_task
def purge_idempotency_keys(hours=24):
    cutoff = timezone.now() - timedelta(hours=hours)
    deleted, _ = IdempotencyKey.objects.filter(created_at__lt=cutoff).delete()
    return deleted

@shared_task
def purge_deleted_conversations(days=30):
    cutoff = timezone.now() - timedelta(days=days)
    _, per_model = Conversation.objects.filter(deleted_at__lt=cutoff).delete()
    return per_model.get("chat.Conversation", 0)

@shared_task
def fail_stuck_documents(minutes=30):
    cutoff = timezone.now() - timedelta(minutes=minutes)
    return Document.objects.filter(
        status=Document.Status.PROCESSING, created_at__lt=cutoff
    ).update(status=Document.Status.FAILED, error="Timed out while processing.")

@shared_task
def daily_usage_report():
    yesterday = timezone.localdate() - timedelta(days=1)
    rows = list(
        UsageRecord.objects.filter(created_at__date=yesterday)
        .values("user__username")
        .annotate(tokens=Sum("input_tokens") + Sum("output_tokens"))
        .order_by("-tokens")
    )
    total = sum(row["tokens"] for row in rows)
    logger.info("usage %s: %s users, %s tokens", yesterday, len(rows), total)
    return {"date": str(yesterday), "users": len(rows), "tokens": total}
