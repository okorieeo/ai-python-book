"""The most important tests in the project: one customer must NEVER see another customer's documents.
Run with:  python manage.py test docuask      (needs PostgreSQL with pgvector; NOT run in the book's test environment)"""
from django.contrib.auth import get_user_model
from django.core.files.base import ContentFile
from rest_framework.test import APIClient
from django.test import TestCase

from docuask_core.embeddings import HashingEmbedder
from .models import Chunk, Document, EMBEDDING_DIMENSIONS
from .search import hybrid_search

User = get_user_model()
EMB = HashingEmbedder(EMBEDDING_DIMENSIONS)   # the hashing embedder is fine for isolation tests: they check WHO, not meaning


def make_doc(owner, title, text):
    doc = Document.objects.create(owner=owner, title=title, original_filename=f"{title}.txt", size_bytes=len(text),
                                  sha256=title.ljust(64, "0"), status=Document.Status.READY, file=ContentFile(text.encode(), f"{title}.txt"))
    Chunk.objects.create(document=doc, owner=owner, index=0, page_start=1, page_end=1, text=text, tokens=20,
                         sha256=title.ljust(64, "1"), embedding=EMB.embed_documents([text])[0])
    return doc


class TenantIsolationTests(TestCase):
    def setUp(self):
        self.alice = User.objects.create_user("alice", password="x")
        self.bob = User.objects.create_user("bob", password="x")
        self.alice_doc = make_doc(self.alice, "alice-salary", "Alice's salary is 90000 dollars per year.")
        self.bob_doc = make_doc(self.bob, "bob-notes", "Bob's salary is 70000 dollars per year.")

    def test_search_never_returns_another_users_chunks(self):
        chunks, _ = hybrid_search(self.alice, "salary per year", EMB.embed_query("salary per year"))
        self.assertEqual({c.document_id for c in chunks}, {self.alice_doc.id})

    def test_search_cannot_be_widened_by_passing_someone_elses_document_id(self):
        chunks, _ = hybrid_search(self.alice, "salary", EMB.embed_query("salary"), document_ids=[self.bob_doc.id])
        self.assertEqual(chunks, [])

    def test_api_treats_other_users_documents_as_missing(self):
        client = APIClient()
        client.force_authenticate(self.alice)
        self.assertEqual(client.get(f"/api/documents/{self.bob_doc.id}/").status_code, 404)
        self.assertEqual(client.delete(f"/api/documents/{self.bob_doc.id}/").status_code, 404)
        self.assertTrue(Document.objects.filter(pk=self.bob_doc.id).exists())
        listed = {d["id"] for d in client.get("/api/documents/").json()}
        self.assertEqual(listed, {self.alice_doc.id})

    def test_deleting_a_document_removes_its_vectors(self):
        client = APIClient()
        client.force_authenticate(self.alice)
        self.assertEqual(client.delete(f"/api/documents/{self.alice_doc.id}/").status_code, 204)
        self.assertFalse(Chunk.objects.filter(document_id=self.alice_doc.id).exists())
