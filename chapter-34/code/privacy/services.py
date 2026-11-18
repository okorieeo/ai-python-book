from datetime import timedelta

from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import transaction
from django.utils import timezone

from audit.services import Action, record
from core.responsible import export as export_lib
from core.responsible.consent_logic import ConsentEvent as ConsentValue
from core.responsible.consent_logic import Purpose, has_consent, missing_required

from .erasers import registry
from .models import ConsentEvent, DeletionRequest, LegalDocument

User = get_user_model()
GRACE_DAYS = 14


def _values(user) -> list[ConsentValue]:
    rows = ConsentEvent.objects.filter(user=user).order_by("created_at", "id")
    return [ConsentValue(Purpose(r.purpose), r.granted, r.document_version, r.created_at) for r in rows]


def current_versions() -> dict[Purpose, str]:
    latest = {}
    for doc in LegalDocument.objects.order_by("effective_at"):
        latest[doc.kind] = doc.version
    return {Purpose.TERMS: latest.get("terms", "none"), Purpose.PRIVACY_NOTICE: latest.get("privacy", "none")}


def record_consent(*, user, purpose: Purpose, granted: bool, version: str, request=None) -> ConsentEvent:
    if purpose in (Purpose.TERMS, Purpose.PRIVACY_NOTICE) and not granted:
        raise ValueError("Terms and privacy notice cannot be withdrawn here; delete the account instead.")
    return ConsentEvent.objects.create(
        user=user, purpose=purpose.value, granted=granted, document_version=version,
        request_id=getattr(request, "request_id", "") if request else "")


def user_has_consent(user, purpose: Purpose, *, version: str | None = None) -> bool:
    return has_consent(_values(user), purpose, required_version=version)


def documents_to_accept(user) -> list[Purpose]:
    return missing_required(_values(user), current_versions())


def export_user_data(*, user, request=None) -> bytes:
    conversations = [
        {"public_id": str(c.public_id), "title": c.title, "created_at": c.created_at.isoformat(),
         "messages": [{"role": m.role, "content": m.content, "created_at": m.created_at.isoformat(),
                       "model": m.model, "ai_generated": m.role == "assistant"} for m in c.messages.all()]}
        for c in user.conversations.prefetch_related("messages")        # owner-scoped, as always
    ]
    payload = export_lib.build_export(
        user={"public_id": str(user.public_id), "email": user.email, "display_name": user.display_name,
              "date_joined": user.date_joined.isoformat(), "role": user.role},
        consents=[{"purpose": e.purpose, "granted": e.granted, "document_version": e.document_version,
                   "created_at": e.created_at.isoformat()} for e in user.consent_events.all()],
        conversations=conversations,
        billing=[],   # Chapter 35 fills this from the Payment model
        generated_at=timezone.now())
    record(Action.DATA_EXPORTED, request=request, actor=user,
           metadata={"conversations": len(conversations)})
    return export_lib.to_zip_bytes(payload)


@transaction.atomic
def request_account_deletion(*, user, request=None) -> DeletionRequest:
    existing = DeletionRequest.objects.filter(
        user_public_id=user.public_id, status=DeletionRequest.Status.SCHEDULED).first()
    if existing:
        return existing
    user.is_active = False                      # sign-in stops now; data stays during the grace period
    user.save(update_fields=["is_active"])
    return DeletionRequest.objects.create(
        user_public_id=user.public_id, scheduled_for=timezone.now() + timedelta(days=GRACE_DAYS),
        request_id=getattr(request, "request_id", "") if request else "")


@transaction.atomic
def cancel_account_deletion(*, user) -> bool:
    count = DeletionRequest.objects.filter(
        user_public_id=user.public_id, status=DeletionRequest.Status.SCHEDULED
    ).update(status=DeletionRequest.Status.CANCELLED)
    if count:
        user.is_active = True
        user.save(update_fields=["is_active"])
    return bool(count)


def execute_deletion(deletion: DeletionRequest) -> DeletionRequest:
    """Run every eraser that has not succeeded yet. Safe to call again after a failure."""
    deletion.status = DeletionRequest.Status.RUNNING
    deletion.save(update_fields=["status"])
    subject = str(deletion.user_public_id)
    done = set(deletion.done_stores)
    results = registry.run_all(subject, already_done=frozenset(done))
    done |= {r.store for r in results if r.ok}
    deletion.done_stores = sorted(done)
    deletion.failed_stores = sorted(r.store for r in results if not r.ok)
    if registry.is_complete(done):
        deletion.status, deletion.completed_at = DeletionRequest.Status.COMPLETE, timezone.now()
        record(Action.ACCOUNT_DELETED, actor=None, metadata={"stores": len(done)})
    else:
        deletion.status = DeletionRequest.Status.PARTIAL
    deletion.save()
    return deletion
