import io
import shutil
import tempfile

import boto3
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.cache import cache
from django.test import override_settings
from moto import mock_aws
from PIL import Image
from rest_framework.test import APITestCase

from accounts.models import User

from .models import Document

API = "/api/v1"
PDF = b"%PDF-1.4\n1 0 obj\n<< /Type /Catalog >>\nendobj\n%%EOF\n"
EXE = b"MZ\x90\x00\x03\x00\x00\x00 this is not a pdf"


def upload_file(name, data):
    return SimpleUploadedFile(name, data)


class FileTestCase(APITestCase):
    def setUp(self):
        cache.clear()
        self.media = tempfile.mkdtemp()
        self.override = override_settings(MEDIA_ROOT=self.media)
        self.override.enable()
        self.user = User.objects.create_user(
            "ada@example.com", "correct-horse-battery-staple", name="Ada"
        )
        self.client.force_authenticate(self.user)

    def tearDown(self):
        self.override.disable()
        shutil.rmtree(self.media, ignore_errors=True)

    def post_file(self, name="notes.pdf", data=PDF, path="/documents"):
        return self.client.post(
            API + path, {"file": upload_file(name, data)}, format="multipart"
        )


class UploadTests(FileTestCase):
    def test_a_pdf_is_stored_under_a_key_we_choose(self):
        r = self.post_file("../../etc/Quarterly report.pdf")
        self.assertEqual(r.status_code, 202)
        self.assertEqual(r.data["status"], "uploaded")
        self.assertEqual(
            r.data["filename"], "Quarterly report.pdf"
        )  # path removed
        doc = Document.objects.get()
        self.assertTrue(
            doc.storage_key.startswith(f"documents/{self.user.public_id}/")
        )
        self.assertNotIn(
            "Quarterly", doc.storage_key
        )  # the name is not in the path
        self.assertNotIn("storage_key", r.data)

    def test_the_content_decides_the_type_not_the_filename(self):
        r = self.post_file(
            "invoice.pdf", EXE
        )  # an executable renamed to .pdf
        self.assertEqual(
            (r.status_code, r.data["error"]["code"]),
            (415, "unsupported_file_type"),
        )
        self.assertEqual(Document.objects.count(), 0)
        png = io.BytesIO()
        Image.new("RGB", (4, 4)).save(png, "PNG")
        r = self.post_file("photo.txt", png.getvalue())  # a PNG named .txt
        self.assertEqual(Document.objects.get().content_type, "image/png")

    def test_empty_and_oversized_files_are_refused(self):
        self.assertEqual(self.post_file(data=b"").status_code, 422)
        with override_settings(UPLOAD_MAX_BYTES=1000):
            r = self.post_file(data=PDF + b"x" * 2000)
        self.assertEqual(
            (r.status_code, r.data["error"]["code"]), (413, "file_too_large")
        )

    def test_missing_file_field_returns_validation_error(self):
        r = self.client.post(API + "/documents", {}, format="multipart")
        self.assertEqual(r.status_code, 422)

    def test_uploading_the_same_file_twice_stores_it_once(self):
        first = self.post_file("a.pdf")
        second = self.post_file("copy-of-a.pdf")
        self.assertEqual((first.status_code, second.status_code), (202, 200))
        self.assertEqual(first.data["id"], second.data["id"])
        self.assertEqual(Document.objects.count(), 1)

    def test_storage_quota_is_enforced(self):
        with override_settings(UPLOAD_QUOTA_BYTES=len(PDF) + 5):
            self.assertEqual(self.post_file("a.pdf").status_code, 202)
            r = self.post_file("b.pdf", PDF + b"different")
        self.assertEqual(
            (r.status_code, r.data["error"]["code"]),
            (403, "storage_quota_exceeded"),
        )

    def test_uploads_are_throttled(self):
        for i in range(60):
            self.post_file(data=PDF + str(i).encode())
        r = self.post_file(data=PDF + b"one-too-many")
        self.assertEqual(r.status_code, 429)


class AccessTests(FileTestCase):
    def test_files_belong_to_their_owner(self):
        doc_id = self.post_file().data["id"]
        other = User.objects.create_user(
            "bo@example.com", "correct-horse-battery-staple", name="Bo"
        )
        self.client.force_authenticate(other)
        for method, url in [
            ("get", f"/documents/{doc_id}"),
            ("get", f"/documents/{doc_id}/download"),
            ("delete", f"/documents/{doc_id}"),
        ]:
            self.assertEqual(
                getattr(self.client, method)(API + url).status_code, 404, url
            )
        self.assertEqual(self.client.get(API + "/documents").data["count"], 0)

    def test_download_streams_the_file_as_an_attachment(self):
        doc_id = self.post_file("notes.pdf").data["id"]
        r = self.client.get(f"{API}/documents/{doc_id}/download")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(b"".join(r.streaming_content), PDF)
        self.assertIn("attachment", r["Content-Disposition"])
        self.assertEqual(r["X-Content-Type-Options"], "nosniff")

    def test_delete_removes_the_file_and_the_row(self):
        doc_id = self.post_file().data["id"]
        key = Document.objects.get().storage_key
        self.assertEqual(
            self.client.delete(f"{API}/documents/{doc_id}").status_code, 204
        )
        from django.core.files.storage import storages

        self.assertFalse(storages["default"].exists(key))
        self.assertEqual(Document.objects.count(), 0)

    def test_login_is_required(self):
        self.client.force_authenticate(None)
        self.assertEqual(self.client.get(API + "/documents").status_code, 401)


def make_image(size=(1200, 800), fmt="JPEG", exif=False):
    img = Image.new("RGB", size, "teal")
    out = io.BytesIO()
    if exif:  # embed GPS-style metadata, as a phone camera would
        data = Image.Exif()
        data[0x010F] = "SecretPhone"
        data[0x8825] = {1: "N", 2: (6.0, 27.0, 0.0)}
        img.save(out, fmt, exif=data)
    else:
        img.save(out, fmt)
    return out.getvalue()


class AvatarTests(FileTestCase):
    def put_avatar(self, data, name="me.jpg"):
        return self.client.put(
            API + "/me/avatar",
            {"file": upload_file(name, data)},
            format="multipart",
        )

    def test_avatar_is_resized_reencoded_and_stripped_of_metadata(self):
        r = self.put_avatar(make_image(exif=True))
        self.assertEqual(r.status_code, 200)
        self.assertTrue(
            r.data["avatar_url"].endswith(f"{self.user.public_id}.webp")
        )
        self.user.refresh_from_db()
        from django.core.files.storage import storages

        with storages["default"].open(self.user.avatar_key, "rb") as f:
            img = Image.open(f)
            self.assertEqual(img.format, "WEBP")
            self.assertLessEqual(max(img.size), 512)
            self.assertFalse(img.getexif())  # no camera model, no GPS

    def test_replacing_an_avatar_leaves_one_file(self):
        self.put_avatar(make_image())
        self.put_avatar(make_image(size=(900, 900)))
        import os

        self.assertEqual(
            len(os.listdir(os.path.join(self.media, "avatars"))), 1
        )

    def test_non_images_and_huge_images_are_refused(self):
        self.assertEqual(self.put_avatar(PDF, "me.jpg").status_code, 422)
        bomb = io.BytesIO()
        Image.new("1", (20000, 20000)).save(
            bomb, "PNG"
        )  # tiny file, 400 MP image
        self.assertLess(len(bomb.getvalue()), 1_000_000)
        self.assertEqual(
            self.put_avatar(bomb.getvalue(), "me.png").status_code, 422
        )

    def test_avatar_can_be_removed(self):
        self.put_avatar(make_image())
        self.assertEqual(
            self.client.delete(API + "/me/avatar").status_code, 204
        )
        self.assertIsNone(self.client.get(API + "/me").data["avatar_url"])


S3_SETTINGS = {
    "bucket_name": "test-bucket",
    "endpoint_url": None,
    "region_name": "us-east-1",
    "access_key": "testing",
    "secret_key": "testing",
}
S3_STORAGES = {
    "default": {
        "BACKEND": "storages.backends.s3.S3Storage",
        "OPTIONS": {
            **S3_SETTINGS,
            "signature_version": "s3v4",
            "querystring_auth": True,
            "querystring_expire": 300,
            "file_overwrite": False,
        },
    },
    "staticfiles": {
        "BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"
    },
}


@override_settings(S3=S3_SETTINGS, STORAGES=S3_STORAGES)
class S3Tests(FileTestCase):
    def setUp(self):
        super().setUp()
        self.mock = mock_aws()
        self.mock.start()
        self.s3 = boto3.client("s3", region_name="us-east-1")
        self.s3.create_bucket(Bucket="test-bucket")

    def tearDown(self):
        self.mock.stop()
        super().tearDown()

    def test_upload_through_the_api_lands_in_the_bucket(self):
        r = self.post_file()
        self.assertEqual(r.status_code, 202)
        key = Document.objects.get().storage_key
        self.assertEqual(
            self.s3.get_object(Bucket="test-bucket", Key=key)["Body"].read(),
            PDF,
        )

    def test_download_redirects_to_a_signed_expiring_url(self):
        doc_id = self.post_file().data["id"]
        r = self.client.get(f"{API}/documents/{doc_id}/download")
        self.assertEqual(r.status_code, 302)
        self.assertIn("X-Amz-Signature", r["Location"])
        self.assertIn("X-Amz-Expires=300", r["Location"])

    def start_direct(self, **extra):
        body = {
            "filename": "big.pdf",
            "content_type": "application/pdf",
            "size_bytes": len(PDF),
        }
        return self.client.post(
            API + "/documents/upload-url", {**body, **extra}, format="json"
        )

    def test_direct_upload_flow(self):
        step1 = self.start_direct()
        self.assertEqual(step1.status_code, 201)
        self.assertIn("X-Amz-Signature", step1.data["upload_url"])
        from django.core import signing

        key = signing.loads(step1.data["upload_token"], salt="direct-upload")[
            "key"
        ]
        self.s3.put_object(
            Bucket="test-bucket", Key=key, Body=PDF
        )  # the browser's PUT
        done = self.client.post(
            API + "/documents/complete",
            {"upload_token": step1.data["upload_token"]},
            format="json",
        )
        self.assertEqual(
            (done.status_code, done.data["status"]), (202, "uploaded")
        )
        self.assertEqual(Document.objects.get().size_bytes, len(PDF))

    def test_a_lying_client_is_caught_at_completion(self):
        step1 = self.start_direct()
        from django.core import signing

        key = signing.loads(step1.data["upload_token"], salt="direct-upload")[
            "key"
        ]
        self.s3.put_object(
            Bucket="test-bucket", Key=key, Body=EXE
        )  # not a PDF at all
        done = self.client.post(
            API + "/documents/complete",
            {"upload_token": step1.data["upload_token"]},
            format="json",
        )
        self.assertEqual(done.status_code, 415)
        self.assertEqual(Document.objects.count(), 0)
        keys = self.s3.list_objects_v2(Bucket="test-bucket").get(
            "Contents", []
        )
        self.assertEqual(keys, [])  # the rejected object was deleted

    def test_completion_without_an_upload_and_with_bad_tokens(self):
        step1 = self.start_direct()
        token = step1.data["upload_token"]
        r = self.client.post(
            API + "/documents/complete",
            {"upload_token": token},
            format="json",
        )
        self.assertEqual(r.status_code, 422)  # nothing was uploaded yet
        r = self.client.post(
            API + "/documents/complete",
            {"upload_token": token + "x"},
            format="json",
        )
        self.assertEqual(
            (r.status_code, r.data["error"]["code"]), (400, "invalid_token")
        )
        other = User.objects.create_user(
            "bo@example.com", "correct-horse-battery-staple", name="Bo"
        )
        self.client.force_authenticate(other)
        r = self.client.post(
            API + "/documents/complete",
            {"upload_token": token},
            format="json",
        )
        self.assertEqual(
            r.status_code, 400
        )  # a token only works for its owner

    def test_upload_url_refuses_bad_declarations(self):
        self.assertEqual(
            self.start_direct(size_bytes=50 * 1024 * 1024).status_code, 413
        )
        self.assertEqual(
            self.start_direct(
                content_type="application/x-msdownload"
            ).status_code,
            422,
        )
