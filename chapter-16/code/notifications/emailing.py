import logging

from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.db import transaction
from django.template.loader import render_to_string

from .models import EmailSuppression

log = logging.getLogger(__name__)


def send_templated_email(template, to, context, subject):
    """Send one transactional email as text + HTML. Returns False if skipped."""
    if EmailSuppression.objects.filter(email=to.lower()).exists():
        log.info("skipped email to suppressed address (%s)", template)
        return False
    context = {"subject": subject, "app_name": "Chat App", **context}
    text = render_to_string(f"emails/{template}.txt", context)
    html = render_to_string(f"emails/{template}.html", context)
    message = EmailMultiAlternatives(
        subject, text, settings.DEFAULT_FROM_EMAIL, [to]
    )
    message.attach_alternative(html, "text/html")
    # Send only if the database transaction that triggered this succeeds.
    transaction.on_commit(message.send)
    return True
