from unittest import mock

from django.core.cache import cache
from django.core.management import call_command
from django.test import override_settings
from rest_framework.test import APITestCase
from rest_framework.throttling import ScopedRateThrottle

from accounts.models import User
from chat import services
from chat.models import Conversation, Document, Message, UsageRecord

BASE = "/api/v1"

FAST_HASHER = ["django.contrib.auth.hashers.MD5PasswordHasher"]   # tests only

@override_settings(PASSWORD_HASHERS=FAST_HASHER)
class ApiTestCase(APITestCase):
    def setUp(self):
        cache.clear()                                  # throttle counters live here
        self.ada = User.objects.create_user("ada", "ada@example.com", "pw-ada-1")
        self.bo = User.objects.create_user("bo", "bo@example.com", "pw-bo-1")

    def login(self, username="ada", password="pw-ada-1"):
        reply = self.client.post(f"{BASE}/auth/login",
                                 {"username": username, "password": password})
        self.assertEqual(reply.status_code, 200, reply.content)
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {reply.data['access']}")
        return reply.data

    def make_chat(self, user=None, title="Trip plan"):
        return Conversation.objects.create(user=user or self.ada, title=title)

class AuthTests(ApiTestCase):
    def test_no_token_is_401_with_one_error_shape(self):
        reply = self.client.get(f"{BASE}/conversations")
        self.assertEqual(reply.status_code, 401)
        error = reply.json()["error"]
        self.assertEqual(error["code"], "not_authenticated")
        self.assertTrue(error["request_id"].startswith("req_"))
        self.assertEqual(reply["X-Request-ID"], error["request_id"])

    def test_wrong_password_never_says_which_part_was_wrong(self):
        reply = self.client.post(f"{BASE}/auth/login",
                                 {"username": "ada", "password": "nope"})
        self.assertEqual(reply.status_code, 401)
        self.assertEqual(reply.json()["error"]["code"], "invalid_credentials")

    def test_refresh_rotates_and_the_old_refresh_token_dies(self):
        tokens = self.login()
        again = self.client.post(f"{BASE}/auth/refresh",
                                 {"refresh": tokens["refresh"]})
        self.assertEqual(again.status_code, 200)
        self.assertNotEqual(again.data["refresh"], tokens["refresh"])
        stolen = self.client.post(f"{BASE}/auth/refresh",
                                  {"refresh": tokens["refresh"]})
        self.assertEqual(stolen.status_code, 401)

    def test_me_returns_a_whitelist(self):
        self.login()
        data = self.client.get(f"{BASE}/me").json()
        self.assertEqual(sorted(data), ["date_joined", "email", "id", "username"])
        self.assertEqual(data["id"], str(self.ada.public_id))

class ConversationTests(ApiTestCase):
    def test_create_ignores_fields_the_client_must_not_set(self):
        self.login()
        reply = self.client.post(f"{BASE}/conversations", {
            "title": "  Trip plan  ", "user": self.bo.id,
            "message_count": 99, "deleted_at": "2020-01-01T00:00:00Z"})
        self.assertEqual(reply.status_code, 201)
        self.assertEqual(reply.data["title"], "Trip plan")        # trimmed
        self.assertEqual(reply.data["message_count"], 0)
        self.assertNotIn("user", reply.data)
        chat = Conversation.objects.get(public_id=reply.data["id"])
        self.assertEqual(chat.user, self.ada)                     # from the token
        self.assertIsNone(chat.deleted_at)

    def test_validation_errors_name_the_field(self):
        self.login()
        reply = self.client.post(f"{BASE}/conversations", {"title": "   "})
        self.assertEqual(reply.status_code, 400)
        error = reply.json()["error"]
        self.assertEqual(error["code"], "validation_error")
        self.assertIn("title", error["fields"])

    def test_other_peoples_conversations_are_404_not_403(self):
        theirs = self.make_chat(self.bo)
        self.login()
        url = f"{BASE}/conversations/{theirs.public_id}"
        for method in (self.client.get, self.client.patch, self.client.delete):
            self.assertEqual(method(url).status_code, 404)
        self.assertEqual(self.client.get(f"{url}/messages").status_code, 404)

    def test_delete_is_soft_and_put_is_not_allowed(self):
        chat = self.make_chat()
        self.login()
        url = f"{BASE}/conversations/{chat.public_id}"
        self.assertEqual(self.client.put(url, {"title": "x"}).status_code, 405)
        self.assertEqual(self.client.delete(url).status_code, 204)
        chat.refresh_from_db()
        self.assertIsNotNone(chat.deleted_at)                     # the row survives
        self.assertEqual(self.client.get(f"{BASE}/conversations").json()["results"], [])

    def test_latest_activity_comes_first_and_queries_stay_constant(self):
        older = self.make_chat(title="Older chat")
        for n in range(14):
            self.make_chat(title=f"Chat {n}")
        services.add_message(older, "user", "bump")           # new activity
        self.login()
        with self.assertNumQueries(2):                        # the user + the page
            page = self.client.get(f"{BASE}/conversations").json()
        self.assertEqual(page["results"][0]["title"], "Older chat")
        self.assertEqual(len(page["results"]), 15)

    def test_search_and_ordering_whitelist(self):
        self.make_chat(title="Trip plan")
        self.make_chat(title="Invoice help")
        self.login()
        found = self.client.get(f"{BASE}/conversations?search=invoice").json()
        self.assertEqual([c["title"] for c in found["results"]], ["Invoice help"])
        # ordering by a field that is not whitelisted is ignored, not an error
        reply = self.client.get(f"{BASE}/conversations?ordering=user__password")
        self.assertEqual(reply.status_code, 200)

class MessageTests(ApiTestCase):
    def setUp(self):
        super().setUp()
        self.chat = self.make_chat()
        self.url = f"{BASE}/conversations/{self.chat.public_id}/messages"

    def test_role_is_set_by_the_server(self):
        self.login()
        reply = self.client.post(self.url, {"content": "Hi", "role": "assistant",
                                            "input_tokens": 999999})
        self.assertEqual(reply.status_code, 201)
        self.assertEqual(reply.data["role"], "user")
        self.assertEqual(reply.data["input_tokens"], 0)
        self.chat.refresh_from_db()
        self.assertEqual(self.chat.message_count, 1)

    def test_cursor_pagination_has_no_duplicates_when_rows_arrive(self):
        for n in range(25):
            services.add_message(self.chat, "user", f"message {n}")
        self.login()
        seen, url, pages = [], f"{self.url}?page_size=10", 0
        while url:
            page = self.client.get(url).json()
            seen += [m["content"] for m in page["results"]]
            pages += 1
            if pages == 1:                       # a new message arrives mid-scroll
                services.add_message(self.chat, "user", "arrived mid-scroll")
            url = page["next"]
        self.assertEqual((pages, len(seen), len(set(seen))), (3, 25, 25))

    def test_page_size_is_capped(self):
        Message.objects.bulk_create(
            Message(conversation=self.chat, role="user", content=str(n))
            for n in range(120))
        self.login()
        page = self.client.get(f"{self.url}?page_size=1000").json()
        self.assertEqual(len(page["results"]), 100)

    def test_same_idempotency_key_creates_one_message(self):
        self.login()
        headers = {"HTTP_IDEMPOTENCY_KEY": "abc-123"}
        first = self.client.post(self.url, {"content": "Pay once"}, **headers)
        again = self.client.post(self.url, {"content": "Pay once"}, **headers)
        self.assertEqual((first.status_code, again.status_code), (201, 201))
        self.assertEqual(first.json(), again.json())
        self.assertEqual(again["Idempotent-Replay"], "true")
        self.assertEqual(Message.objects.filter(content="Pay once").count(), 1)
        other = self.client.post(self.url, {"content": "Different"}, **headers)
        self.assertEqual(other.status_code, 409)                  # key reused wrongly

    def test_quota_exhausted_is_402_not_429(self):
        UsageRecord.objects.create(user=self.ada, input_tokens=40_000,
                                   output_tokens=20_000)
        self.login()
        reply = self.client.post(self.url, {"content": "Hello"})
        self.assertEqual(reply.status_code, 402)
        self.assertEqual(reply.json()["error"]["code"], "quota_exceeded")
        usage = self.client.get(f"{BASE}/me/usage").json()
        self.assertEqual(usage["remaining"], 0)

    def test_rate_limit_is_429_with_retry_after(self):
        self.login()
        with mock.patch.dict(ScopedRateThrottle.THROTTLE_RATES, {"ai_chat": "2/min"}):
            codes = [self.client.post(self.url, {"content": str(n)}).status_code
                     for n in range(3)]
            blocked = self.client.post(self.url, {"content": "again"})
        self.assertEqual(codes, [201, 201, 429])
        self.assertEqual(blocked.json()["error"]["code"], "rate_limited")
        self.assertIn("Retry-After", blocked)

class DocumentTests(ApiTestCase):
    def test_create_answers_202_and_a_status_resource(self):
        self.login()
        reply = self.client.post(f"{BASE}/documents", {"filename": "contract.pdf"})
        self.assertEqual(reply.status_code, 202)
        self.assertEqual(reply.data["status"], "processing")
        self.assertTrue(reply["Location"].endswith(reply.data["id"]))

    def test_unsupported_file_type_is_a_field_error(self):
        self.login()
        reply = self.client.post(f"{BASE}/documents", {"filename": "virus.exe"})
        self.assertEqual(reply.status_code, 400)
        self.assertIn("filename", reply.json()["error"]["fields"])

    def test_filter_by_status_and_reindex(self):
        ready = Document.objects.create(user=self.ada, filename="a.pdf", status="ready")
        Document.objects.create(user=self.ada, filename="b.pdf", status="failed")
        self.login()
        found = self.client.get(f"{BASE}/documents?status=ready").json()["results"]
        self.assertEqual([d["id"] for d in found], [str(ready.public_id)])
        cutoff = "2999-01-01T00:00:00Z"
        none = self.client.get(f"{BASE}/documents?created_after={cutoff}").json()
        self.assertEqual(none["results"], [])
        again = self.client.post(f"{BASE}/documents/{ready.public_id}/reindex")
        self.assertEqual((again.status_code, again.data["status"]), (202, "processing"))

class ContractTests(ApiTestCase):
    def test_public_endpoints_need_no_token(self):
        self.assertEqual(self.client.get(f"{BASE}/health").status_code, 200)
        config = self.client.get(f"{BASE}/meta/client-config").json()
        self.assertIn("min_supported_version", config)

    def test_unknown_paths_are_json_404s(self):
        for path in ("/api/v2/conversations", f"{BASE}/nope", f"{BASE}/conversations/x"):
            reply = self.client.get(path)
            self.assertEqual(reply.status_code, 404)
            self.assertEqual(reply["Content-Type"], "application/json")
            self.assertEqual(reply.json()["error"]["code"], "not_found")

    def test_the_openapi_schema_is_valid_and_complete(self):
        call_command("spectacular", "--validate", "--fail-on-warn",
                     "--file", "/dev/null")
        schema = self.client.get("/api/schema/").content.decode()
        for path in ("/api/v1/conversations", "/api/v1/documents/{public_id}/reindex",
                     "/api/v1/conversations/{conversation_id}/messages"):
            self.assertIn(path, schema)
