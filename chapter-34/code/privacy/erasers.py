"""Every place we keep personal data registers an eraser here. Chapters 31, 32 and 36 add theirs."""
from django.apps import apps

from core.responsible.erasure import EraserRegistry

registry = EraserRegistry()


def _delete_conversations(public_id: str) -> int:
    Conversation = apps.get_model("chat", "Conversation")
    deleted, _ = Conversation.objects.filter(user__public_id=public_id).delete()   # messages cascade
    return deleted


def _delete_ai_logs(public_id: str) -> int:
    AIRequestLog = apps.get_model("chat", "AIRequestLog")
    deleted, _ = AIRequestLog.objects.filter(user__public_id=public_id).delete()
    return deleted


def _delete_flagged(public_id: str) -> int:
    Flagged = apps.get_model("chat", "FlaggedMessage")
    deleted, _ = Flagged.objects.filter(user_public_id=public_id).delete()
    return deleted


def _delete_consents(public_id: str) -> int:
    ConsentEvent = apps.get_model("privacy", "ConsentEvent")
    deleted, _ = ConsentEvent.objects.filter(user__public_id=public_id).delete()
    return deleted


def _anonymize_billing(public_id: str) -> int:
    """Invoices must be kept for tax law, so keep the amounts and drop the person."""
    Payment = apps.get_model("billing", "Payment")
    return Payment.objects.filter(user__public_id=public_id).update(
        billing_name="", billing_email="", billing_address="")


def _delete_vectors(public_id: str) -> int:
    DocumentChunk = apps.get_model("rag", "DocumentChunk")           # Chapter 31
    deleted, _ = DocumentChunk.objects.filter(document__owner__public_id=public_id).delete()
    return deleted


def _delete_account(public_id: str) -> int:
    """Last: the account row. Audit events keep only the public id, so history survives (Chapter 17)."""
    User = apps.get_model("users", "User")
    deleted, _ = User.objects.filter(public_id=public_id).delete()
    return deleted


registry.register("conversations", _delete_conversations)
registry.register("ai_logs", _delete_ai_logs)
registry.register("flagged", _delete_flagged)
registry.register("consents", _delete_consents)
registry.register("billing_anonymize", _anonymize_billing)
registry.register("vectors", _delete_vectors)
registry.register("account", _delete_account)        # keep last: other erasers look the user up
