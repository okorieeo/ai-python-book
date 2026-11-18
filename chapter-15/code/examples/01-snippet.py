# WRONG: the job may start before the row is committed (a race),
# and it still runs if the transaction later rolls back.
document = Document.objects.create(...)
ingest_document.delay(document.pk)

# RIGHT: queue the job only after the commit has succeeded.
transaction.on_commit(lambda: ingest_document.delay(document.pk))
