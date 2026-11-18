import csv
import io
from datetime import timedelta

from django.core.cache import cache
from django.test import override_settings
from django.utils import timezone
from rest_framework.test import APITestCase

from accounts.models import User
from chat.models import Conversation, Document, UsageRecord

BASE = "/api/v1"
FAST = ["django.contrib.auth.hashers.MD5PasswordHasher"]

def put_at(queryset, **delta):
    """created_at is auto_now_add, so move rows in time with update()."""
    queryset.update(created_at=timezone.now() - timedelta(**delta))

@override_settings(PASSWORD_HASHERS=FAST)
class AdminApiTestCase(APITestCase):
    def setUp(self):
        cache.clear()
        make = User.objects.create_user
        self.admin = make("root", "root@example.com", "pw-1", role="admin")
        self.support = make("sam", "sam@example.com", "pw-1", role="support")
        self.ada = make("ada", "ada@example.com", "pw-1")

    def as_user(self, user):
        reply = self.client.post(f"{BASE}/auth/login",
                                 {"username": user.username, "password": "pw-1"})
        token = reply.data["access"]
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")

class RoleTests(AdminApiTestCase):
    ANALYTICS = ["/admin/overview", "/admin/usage", "/admin/usage/top-users",
                 "/admin/documents/status"]

    def statuses(self, paths):
        return [self.client.get(BASE + p).status_code for p in paths]

    def test_members_are_locked_out_of_everything(self):
        self.as_user(self.ada)
        paths = self.ANALYTICS + ["/admin/users", "/admin/users/export"]
        self.assertEqual(set(self.statuses(paths)), {403})
        error = self.client.get(f"{BASE}/admin/users").json()["error"]
        self.assertEqual(error["code"], "permission_denied")

    def test_support_can_see_users_but_nothing_else(self):
        self.as_user(self.support)
        self.assertEqual(self.client.get(f"{BASE}/admin/users").status_code, 200)
        self.assertEqual(set(self.statuses(self.ANALYTICS)), {403})
        export = self.client.get(f"{BASE}/admin/users/export")
        self.assertEqual(export.status_code, 403)

    def test_admins_can_do_everything(self):
        self.as_user(self.admin)
        paths = self.ANALYTICS + ["/admin/users", "/admin/users/export"]
        self.assertEqual(set(self.statuses(paths)), {200})

    def test_anonymous_callers_get_401(self):
        self.assertEqual(self.client.get(f"{BASE}/admin/users").status_code, 401)

    def test_me_tells_the_ui_the_role_and_permissions(self):
        self.as_user(self.support)
        me = self.client.get(f"{BASE}/me").json()
        self.assertEqual(me["role"], "support")
        self.assertEqual(me["permissions"], ["view_users"])
        self.as_user(self.admin)
        me = self.client.get(f"{BASE}/me").json()
        self.assertIn("view_analytics", me["permissions"])

    def test_logging_in_records_the_last_login(self):
        self.assertIsNone(self.ada.last_login)
        self.as_user(self.ada)
        self.ada.refresh_from_db()
        self.assertIsNotNone(self.ada.last_login)

    def test_a_role_cannot_be_changed_through_the_api(self):
        self.as_user(self.ada)
        reply = self.client.patch(f"{BASE}/me", {"role": "admin"})
        self.assertEqual(reply.status_code, 405)
        self.ada.refresh_from_db()
        self.assertEqual(self.ada.role, "member")

class AnalyticsTests(AdminApiTestCase):
    def setUp(self):
        super().setUp()
        self.as_user(self.admin)

    def test_usage_series_has_one_point_for_every_day_even_empty_ones(self):
        record = UsageRecord.objects.create(user=self.ada, input_tokens=100,
                                            output_tokens=40)
        put_at(UsageRecord.objects.filter(pk=record.pk), days=2)
        UsageRecord.objects.create(user=self.ada, input_tokens=10,
                                   output_tokens=5)
        data = self.client.get(f"{BASE}/admin/usage?days=7").json()
        series = data["series"]
        self.assertEqual((data["days"], len(series)), (7, 7))
        dates = [point["date"] for point in series]
        self.assertEqual(dates, sorted(dates))                 # oldest first
        self.assertEqual(dates[-1], str(timezone.localdate()))
        by_date = {p["date"]: p for p in series}
        day_before_yesterday = str(timezone.localdate() - timedelta(days=2))
        self.assertEqual(by_date[day_before_yesterday]["input_tokens"], 100)
        self.assertEqual(sum(p["calls"] for p in series), 2)
        self.assertEqual(series[0]["calls"], 0)                # a gap, filled

    def test_bad_days_is_a_field_error(self):
        for bad in ("0", "400", "abc"):
            reply = self.client.get(f"{BASE}/admin/usage?days={bad}")
            self.assertEqual(reply.status_code, 400)
            self.assertIn("days", reply.json()["error"]["fields"])

    def test_overview_counts(self):
        chat = Conversation.objects.create(user=self.ada, title="x")
        UsageRecord.objects.create(user=self.ada, input_tokens=300,
                                   output_tokens=200)
        Document.objects.create(user=self.ada, filename="a.pdf")
        data = self.client.get(f"{BASE}/admin/overview").json()
        self.assertEqual((data["users_total"], data["users_new_7d"]), (3, 3))
        self.assertEqual(data["tokens_today"], 500)
        self.assertEqual(data["documents_total"], 1)
        self.assertTrue(chat.pk)

    def test_top_users_ranks_by_tokens(self):
        UsageRecord.objects.create(user=self.ada, input_tokens=900,
                                   output_tokens=0)
        UsageRecord.objects.create(user=self.support, input_tokens=100,
                                   output_tokens=0)
        rows = self.client.get(f"{BASE}/admin/usage/top-users?limit=1").json()
        self.assertEqual(rows, [{"username": "ada", "tokens": 900}])

    def test_document_status_lists_every_status_even_with_zero(self):
        Document.objects.create(user=self.ada, filename="a.pdf", status="ready")
        rows = self.client.get(f"{BASE}/admin/documents/status").json()
        self.assertEqual({r["status"]: r["count"] for r in rows},
                         {"uploaded": 0, "processing": 0, "ready": 1,
                          "failed": 0})

class UserTableTests(AdminApiTestCase):
    def setUp(self):
        super().setUp()
        for n in range(25):
            User.objects.create_user(f"user{n:02d}", f"u{n:02d}@example.com",
                                     "pw-1")
        self.as_user(self.admin)

    def test_pages_have_a_count_and_stable_content(self):
        first = self.client.get(f"{BASE}/admin/users?page_size=10").json()
        self.assertEqual((first["count"], len(first["results"])), (28, 10))
        seen = []
        url = f"{BASE}/admin/users?page_size=10&ordering=role"     # many ties
        while url:
            page = self.client.get(url).json()
            seen += [u["id"] for u in page["results"]]
            url = page["next"]
        self.assertEqual((len(seen), len(set(seen))), (28, 28))

    def test_the_list_costs_three_queries_however_long_it_is(self):
        with self.assertNumQueries(3):                 # the caller, count, page
            self.client.get(f"{BASE}/admin/users?page_size=25")

    def test_filters_search_and_ordering_whitelist(self):
        by_role = self.client.get(f"{BASE}/admin/users?role=support").json()
        self.assertEqual([u["username"] for u in by_role["results"]], ["sam"])
        found = self.client.get(f"{BASE}/admin/users?search=user07").json()
        self.assertEqual([u["username"] for u in found["results"]], ["user07"])
        self.ada.is_active = False
        self.ada.save()
        inactive = self.client.get(f"{BASE}/admin/users?is_active=false").json()
        self.assertEqual([u["username"] for u in inactive["results"]], ["ada"])
        ordered = self.client.get(f"{BASE}/admin/users?ordering=username").json()
        names = [u["username"] for u in ordered["results"]]
        self.assertEqual(names, sorted(names))
        odd = self.client.get(f"{BASE}/admin/users?ordering=password")
        self.assertEqual(odd.status_code, 200)             # ignored, not obeyed

    def test_the_numbers_per_user_are_right(self):
        Conversation.objects.create(user=self.ada, title="kept")
        Conversation.objects.create(user=self.ada, title="gone",
                                    deleted_at=timezone.now())
        recent = UsageRecord.objects.create(user=self.ada, input_tokens=100,
                                            output_tokens=50)
        old = UsageRecord.objects.create(user=self.ada, input_tokens=9000,
                                         output_tokens=0)
        put_at(UsageRecord.objects.filter(pk=old.pk), days=45)      # too old
        found = self.client.get(f"{BASE}/admin/users?search=ada").json()
        row = found["results"][0]
        self.assertEqual(row["conversation_count"], 1)      # not the deleted one
        self.assertEqual(row["tokens_30d"], 150)                    # not 9,150
        self.assertTrue(recent.pk)

    def test_the_password_hash_is_never_in_the_response(self):
        found = self.client.get(f"{BASE}/admin/users?search=ada").json()
        row = found["results"][0]
        self.assertNotIn("password", row)
        self.assertEqual(sorted(row), sorted(
            ["id", "username", "email", "role", "is_active", "date_joined",
             "last_login", "conversation_count", "tokens_30d"]))

class CsvExportTests(AdminApiTestCase):
    def rows(self, query=""):
        reply = self.client.get(f"{BASE}/admin/users/export{query}")
        self.assertEqual(reply.status_code, 200)
        self.assertEqual(reply["Content-Type"], "text/csv")
        self.assertIn("attachment", reply["Content-Disposition"])
        text = b"".join(reply.streaming_content).decode()
        return list(csv.DictReader(io.StringIO(text)))

    def test_export_follows_the_same_filters_as_the_table(self):
        self.as_user(self.admin)
        rows = self.rows("?role=support")
        self.assertEqual([r["username"] for r in rows], ["sam"])

    def test_spreadsheet_formulas_are_defused(self):
        evil = '=HYPERLINK("http://evil")'
        User.objects.create_user(evil, "x@example.com", "pw-1")
        self.as_user(self.admin)
        names = [r["username"] for r in self.rows()]
        self.assertIn("'=HYPERLINK(\"http://evil\")", names)
        self.assertFalse(any(n.startswith("=") for n in names))

    def test_exports_are_rate_limited(self):
        self.as_user(self.admin)
        codes = [self.client.get(f"{BASE}/admin/users/export").status_code
                 for _ in range(6)]
        self.assertEqual(codes, [200, 200, 200, 200, 200, 429])
