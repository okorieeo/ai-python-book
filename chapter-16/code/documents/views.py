from botocore.exceptions import ClientError
from django.conf import settings
from django.core import signing
from django.core.files.base import ContentFile
from django.db import IntegrityError
from django.db.models import Sum
from django.http import FileResponse, HttpResponseRedirect
from rest_framework import generics, status
from rest_framework.exceptions import ValidationError
from rest_framework.parsers import MultiPartParser
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

from accounts.exceptions import InvalidLink
from accounts.serializers import UserSerializer

from . import storage as store
from . import validation
from .images import process_avatar
from .models import Document
from .serializers import DocumentSerializer, UploadUrlSerializer

EXTENSIONS = {
    "application/pdf": ".pdf",
    "image/png": ".png",
    "image/jpeg": ".jpg",
    "text/plain": ".txt",
}


def check_quota(user, new_bytes):
    used = user.documents.aggregate(total=Sum("size_bytes"))["total"] or 0
    if used + new_bytes > settings.UPLOAD_QUOTA_BYTES:
        raise validation.QuotaExceeded()


def register_document(user, *, filename, key, content_type, size, digest):
    """Record an uploaded file. A repeat of the same file returns the first."""
    existing = user.documents.filter(sha256=digest).first()
    if existing:
        store.get_storage().delete(
            key
        )  # the copy we just stored is redundant
        return existing, False
    check_quota(user, size)
    try:
        doc = Document.objects.create(
            user=user,
            filename=validation.clean_filename(filename),
            storage_key=key,
            content_type=content_type,
            size_bytes=size,
            sha256=digest,
        )
    except IntegrityError:  # two identical uploads raced: keep the winner
        store.get_storage().delete(key)
        return user.documents.get(sha256=digest), False
    return doc, True


class DocumentList(generics.ListCreateAPIView):
    serializer_class = DocumentSerializer
    parser_classes = [MultiPartParser]

    def get_queryset(self):
        return self.request.user.documents.order_by("-created_at", "-id")

    def get_throttles(self):
        if self.request.method == "POST":
            self.throttle_scope = "upload"
            return [ScopedRateThrottle()]
        return []

    def create(self, request, *args, **kwargs):
        upload = request.FILES.get("file")
        if upload is None:
            raise ValidationError({"file": ["No file was sent."]})
        validation.check_size(upload.size)
        kind = validation.sniff(
            upload.read(8192)
        )  # judge by content, not name
        upload.seek(0)
        if kind is None:
            raise validation.UnsupportedFile()
        digest = store.sha256_of(upload.chunks())
        upload.seek(0)
        existing = request.user.documents.filter(sha256=digest).first()
        if existing:  # same bytes again: answer idempotently, store nothing
            return Response(DocumentSerializer(existing).data)
        check_quota(request.user, upload.size)
        key = store.get_storage().save(
            store.new_key(request.user, kind[1]), upload
        )
        doc, created = register_document(
            request.user,
            filename=upload.name,
            key=key,
            content_type=kind[0],
            size=upload.size,
            digest=digest,
        )
        return Response(
            DocumentSerializer(doc).data,
            status=(
                status.HTTP_202_ACCEPTED if created else status.HTTP_200_OK
            ),
        )


class DocumentDetail(generics.RetrieveDestroyAPIView):
    serializer_class = DocumentSerializer
    lookup_field = "public_id"

    def get_queryset(self):
        return self.request.user.documents.all()

    def perform_destroy(self, doc):
        store.get_storage().delete(doc.storage_key)  # the file, then the row
        doc.delete()


class DocumentDownload(APIView):
    def get(self, request, public_id):
        doc = generics.get_object_or_404(
            request.user.documents, public_id=public_id
        )
        storage = store.get_storage()
        if store.is_local(storage):  # development: stream it ourselves
            response = FileResponse(
                storage.open(doc.storage_key, "rb"),
                as_attachment=True,
                filename=doc.filename,
                content_type=doc.content_type,
            )
            response["X-Content-Type-Options"] = "nosniff"
            return response
        url = (
            storage.url(  # production: a link that stops working in 5 minutes
                doc.storage_key,
                parameters={"ResponseContentDisposition": "attachment"},
            )
        )
        return HttpResponseRedirect(url)


class AvatarView(APIView):
    parser_classes = [MultiPartParser]

    def put(self, request):
        upload = request.FILES.get("file")
        if upload is None:
            raise ValidationError({"file": ["No file was sent."]})
        validation.check_size(upload.size)
        image_bytes = process_avatar(upload)
        storage, user = store.get_storage(), request.user
        if user.avatar_key:
            storage.delete(
                user.avatar_key
            )  # so the new file gets the same name
        user.avatar_key = storage.save(
            f"avatars/{user.public_id}.webp", ContentFile(image_bytes)
        )
        user.save(update_fields=["avatar_key", "updated_at"])
        return Response(UserSerializer(user).data)

    def delete(self, request):
        user = request.user
        if user.avatar_key:
            store.get_storage().delete(user.avatar_key)
            user.avatar_key = ""
            user.save(update_fields=["avatar_key", "updated_at"])
        return Response(status=status.HTTP_204_NO_CONTENT)


UPLOAD_SALT = "direct-upload"


class UploadUrlView(APIView):
    """Step 1 of a direct upload: hand the client a short-lived signed URL."""

    def post(self, request):
        serializer = UploadUrlSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        validation.check_size(data["size_bytes"])
        key = store.new_key(request.user, EXTENSIONS[data["content_type"]])
        url = store.s3_client().generate_presigned_url(
            "put_object",
            ExpiresIn=300,
            Params={
                "Bucket": settings.S3["bucket_name"],
                "Key": key,
                "ContentType": data["content_type"],
            },
        )
        token = signing.dumps(
            {"key": key, "uid": request.user.pk, "name": data["filename"]},
            salt=UPLOAD_SALT,
        )
        return Response(
            {
                "upload_url": url,
                "method": "PUT",
                "expires_in": 300,
                "headers": {"Content-Type": data["content_type"]},
                "upload_token": token,
            },
            status=status.HTTP_201_CREATED,
        )


class CompleteUploadView(APIView):
    """Step 3: the client says "done". We do not believe it; we check."""

    def post(self, request):
        try:
            claims = signing.loads(
                request.data.get("upload_token", ""),
                salt=UPLOAD_SALT,
                max_age=900,
            )
        except signing.BadSignature:
            raise InvalidLink()
        if claims["uid"] != request.user.pk:
            raise InvalidLink()
        s3, bucket, key = (
            store.s3_client(),
            settings.S3["bucket_name"],
            claims["key"],
        )
        try:
            size = s3.head_object(Bucket=bucket, Key=key)["ContentLength"]
        except ClientError:
            raise ValidationError(
                {"upload_token": ["No uploaded file was found."]}
            )
        try:
            validation.check_size(size)
            head = s3.get_object(Bucket=bucket, Key=key, Range="bytes=0-8191")
            kind = validation.sniff(head["Body"].read())
            if kind is None:
                raise validation.UnsupportedFile()
            body = s3.get_object(Bucket=bucket, Key=key)["Body"]
            digest = store.sha256_of(body.iter_chunks(65536))
        except Exception:
            s3.delete_object(
                Bucket=bucket, Key=key
            )  # never keep a rejected file
            raise
        doc, created = register_document(
            request.user,
            filename=claims["name"],
            key=key,
            content_type=kind[0],
            size=size,
            digest=digest,
        )
        return Response(
            DocumentSerializer(doc).data,
            status=(
                status.HTTP_202_ACCEPTED if created else status.HTTP_200_OK
            ),
        )
