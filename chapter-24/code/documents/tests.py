class LinkTests(FileTestCase):
    def test_link_returns_a_url_for_the_owner_only(self):
        doc_id = self.post_file().data["id"]
        r = self.client.get(f"{API}/documents/{doc_id}/link")
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.data["url"].startswith("http://testserver/media/documents/"))
        other = User.objects.create_user(
            "bo@example.com", "correct-horse-battery-staple", name="Bo"
        )
        self.client.force_authenticate(other)
        self.assertEqual(self.client.get(f"{API}/documents/{doc_id}/link").status_code, 404)
