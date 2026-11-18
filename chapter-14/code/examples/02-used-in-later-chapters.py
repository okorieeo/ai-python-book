# a Celery task (Chapter 15) finishing a document:
notify_user(document.user_id, kind="document_ready", title="Your document is ready", body=document.filename)

# a payment webhook handler (Chapters 36 and 37):
notify_user(user.pk, kind="payment_succeeded", title="Payment received", body="Your Pro plan is active")
