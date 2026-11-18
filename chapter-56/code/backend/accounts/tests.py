from django.core.cache import cache
from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from testing import PASSWORD, make_user

from .views import redeem_ticket


class AuthTests(TestCase):
    def setUp(self):
        self.api = APIClient()

    def test_register_login_and_me(self):
        r = self.api.post("/api/v1/auth/register/", {"email": "Bo@Example.com", "password": PASSWORD}, format="json")
        self.assertEqual(r.status_code, 201)
        self.assertNotIn("password", r.json())
        login = self.api.post("/api/v1/auth/login/", {"email": "bo@example.com", "password": PASSWORD}, format="json")
        self.assertEqual(login.status_code, 200)
        self.api.credentials(HTTP_AUTHORIZATION=f"Bearer {login.json()['access']}")
        me = self.api.get("/api/v1/auth/me/")
        self.assertEqual(me.json()["email"], "bo@example.com")
        self.assertNotIn("is_staff", me.json())

    def test_duplicate_email_is_rejected_case_insensitively(self):
        make_user("ada@example.com")
        r = self.api.post("/api/v1/auth/register/", {"email": "ADA@example.com", "password": PASSWORD}, format="json")
        self.assertEqual(r.status_code, 400)

    def test_weak_password_is_rejected(self):
        r = self.api.post("/api/v1/auth/register/", {"email": "x@example.com", "password": "12345678"}, format="json")
        self.assertEqual(r.status_code, 400)

    def test_me_requires_login(self):
        self.assertEqual(self.api.get("/api/v1/auth/me/").status_code, 401)

    def test_client_cannot_make_itself_staff(self):
        r = self.api.post("/api/v1/auth/register/",
                          {"email": "x@example.com", "password": PASSWORD, "is_staff": True}, format="json")
        self.assertEqual(r.status_code, 201)
        from django.contrib.auth import get_user_model
        self.assertFalse(get_user_model().objects.get(email="x@example.com").is_staff)


class TicketTests(TestCase):
    def setUp(self):
        cache.clear()
        self.user = make_user()
        self.api = APIClient()
        self.api.force_authenticate(self.user)

    def test_ticket_is_single_use(self):
        ticket = self.api.post("/api/v1/auth/ws-ticket/").json()["ticket"]
        self.assertEqual(redeem_ticket(ticket), self.user.pk)
        self.assertIsNone(redeem_ticket(ticket))

    def test_unknown_and_empty_tickets_fail(self):
        self.assertIsNone(redeem_ticket("nope"))
        self.assertIsNone(redeem_ticket(""))

    def test_ticket_requires_login(self):
        self.assertEqual(APIClient().post("/api/v1/auth/ws-ticket/").status_code, 401)
