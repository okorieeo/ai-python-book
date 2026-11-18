# Chapter 13 — Authentication, Authorization and Roles: extended material

The printed edition of *Building AI-Powered Apps* keeps each chapter short. This file holds the longer material that was moved here so that nothing is lost: the full hands-on lab, troubleshooting tables, checklists, further exercises, and sections that were condensed for print.


---

# Sections condensed for print


## The Custom User Model › Register the model

Add the app, the model and the libraries to `config/settings.py`. These are the settings for the whole chapter; we explain each group where it is used.

**config/settings.py (added at the end)**

```
# ---- Chapter 13: authentication ---------------------------------------
from datetime import timedelta

AUTH_USER_MODEL = "accounts.User"
FRONTEND_URL = "http://localhost:3000"
DEFAULT_FROM_EMAIL = "Chat App <no-reply@example.com>"
GOOGLE_CLIENT_ID = os.environ.get("GOOGLE_CLIENT_ID", "")
EMAIL_VERIFY_MAX_AGE = 2 * 24 * 3600  # seconds

REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "rest_framework_simplejwt.authentication.JWTAuthentication",
    ],
    "DEFAULT_PERMISSION_CLASSES": [
        "rest_framework.permissions.IsAuthenticated"
    ],
    "EXCEPTION_HANDLER": "accounts.exceptions.api_exception_handler",
    "DEFAULT_THROTTLE_RATES": {"login": "5/min", "password_reset": "5/hour"},
    "DEFAULT_PAGINATION_CLASS": "rest_framework.pagination.LimitOffsetPagination",
    "PAGE_SIZE": 20,
}

SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(minutes=15),
    "REFRESH_TOKEN_LIFETIME": timedelta(days=30),
    "ROTATE_REFRESH_TOKENS": True,
    "BLACKLIST_AFTER_ROTATION": True,
    "USER_ID_FIELD": "public_id",
    "USER_ID_CLAIM": "sub",
}
```

The `INSTALLED_APPS` list also needs `"rest_framework"`, `"rest_framework_simplejwt.token_blacklist"` (the table that remembers revoked refresh tokens) and `"accounts"`. Then create and apply the migrations:

**terminal**

```bash
python manage.py makemigrations accounts
python manage.py migrate
```

> **Django 6.1 and email settings**
>
> Recent Django versions configure email through a `MAILERS` setting, and a new project already uses the console backend (emails are printed in your terminal). Older versions use `EMAIL_BACKEND` instead. Do not set both: Django 6.1 refuses to start if it finds the old and new style together. Real email delivery arrives in Chapter 16.


## Registration and Login › Prove it with tests

Write the tests next to the code. The first block holds the imports and a small base class; the later sections of this chapter add more test classes to the same file. Read each test name as a sentence: it states a rule of the system.

**accounts/tests.py**

```
import re
from datetime import timedelta
from unittest import mock

from django.core import mail
from django.core.cache import cache
from rest_framework.test import APITestCase
from rest_framework_simplejwt.tokens import AccessToken

from .models import Farm, FarmMember, SocialAccount, User

API = "/api/v1"
GOOD = "correct-horse-battery-staple"

class AuthTestCase(APITestCase):
    def setUp(self):
        cache.clear()  # the login throttle counts attempts in the cache

    def make_user(self, email="ada@example.com", password=GOOD, **extra):
        extra.setdefault("name", "Ada")
        return User.objects.create_user(email, password, **extra)

    def login(self, email="ada@example.com", password=GOOD):
        return self.client.post(
            f"{API}/auth/login", {"email": email, "password": password}
        )

    def sign_in(self, user, password=GOOD):
        tokens = self.login(user.email, password).data
        self.client.credentials(
            HTTP_AUTHORIZATION="Bearer " + tokens["access"]
        )
        return tokens

    def code(self, response):
        return response.data["error"]["code"]

class RegistrationTests(AuthTestCase):
    def test_register_creates_user_and_sends_verification_email(self):
        r = self.client.post(
            f"{API}/auth/register",
            {"email": "Ada@Example.com", "name": "Ada", "password": GOOD},
        )
        self.assertEqual(r.status_code, 201)
        user = User.objects.get()
        self.assertEqual(user.email, "ada@example.com")  # stored in lowercase
        self.assertFalse(user.email_verified)
        self.assertNotEqual(user.password, GOOD)  # only a hash is stored
        self.assertEqual(len(mail.outbox), 1)

    def test_weak_password_is_rejected_with_details(self):
        r = self.client.post(
            f"{API}/auth/register",
            {"email": "a@example.com", "name": "A", "password": "12345678"},
        )
        self.assertEqual(r.status_code, 422)
        self.assertEqual(self.code(r), "validation_error")
        self.assertIn("password", r.data["error"]["details"])

    def test_duplicate_email_is_rejected_even_with_different_case(self):
        self.make_user()
        r = self.client.post(
            f"{API}/auth/register",
            {"email": "ADA@example.com", "name": "X", "password": GOOD},
        )
        self.assertEqual(r.status_code, 422)
        self.assertIn("email", r.data["error"]["details"])

class LoginTests(AuthTestCase):
    def test_login_returns_tokens_with_role_and_sub_claims(self):
        user = self.make_user()
        r = self.login()
        self.assertEqual(r.status_code, 200)

        claims = AccessToken(r.data["access"])
        self.assertEqual(claims["sub"], str(user.public_id))
        self.assertEqual(claims["role"], "member")
        self.assertNotIn("password", claims.payload)

    def test_wrong_password_and_unknown_email_look_identical(self):
        self.make_user()
        a = self.login(password="wrong-password")
        b = self.login(email="nobody@example.com")
        self.assertEqual(
            (a.status_code, self.code(a)), (401, "not_authenticated")
        )
        self.assertEqual(
            a.data["error"]["message"], b.data["error"]["message"]
        )

    def test_login_is_throttled_after_five_attempts(self):
        self.make_user()
        for _ in range(5):
            self.assertEqual(
                self.login(password="nope-nope-nope").status_code, 401
            )
        r = self.login()  # even the right password is refused now
        self.assertEqual((r.status_code, self.code(r)), (429, "rate_limited"))
        self.assertIn("Retry-After", r.headers)

    def test_me_requires_a_token_and_returns_the_profile(self):
        user = self.make_user()
        self.assertEqual(self.client.get(f"{API}/me").status_code, 401)
        self.sign_in(user)
        r = self.client.get(f"{API}/me")
        self.assertEqual(r.data["email"], "ada@example.com")
        self.assertEqual(r.data["id"], str(user.public_id))

    def test_a_deactivated_account_cannot_use_its_token(self):
        user = self.make_user()
        self.sign_in(user)
        user.is_active = False
        user.save()
        self.assertEqual(self.client.get(f"{API}/me").status_code, 401)

    def test_me_cannot_change_role(self):
        user = self.make_user()
        self.sign_in(user)
        self.client.patch(f"{API}/me", {"role": "admin", "name": "New"})
        user.refresh_from_db()
        self.assertEqual((user.role, user.name), ("member", "New"))
```

Run them with `python manage.py test accounts`. Two details are worth studying. `setUp` clears the cache because the login throttle counts attempts there; without it, tests would affect each other. And `test_login_is_throttled_after_five_attempts` proves that *even the correct password* is refused once the limit is hit, which is the point of a throttle.


## Refresh Tokens, Rotation and Logout › Tests

**accounts/tests.py (add)**

```
class TokenTests(AuthTestCase):
    def test_refresh_rotates_and_the_old_token_stops_working(self):
        self.make_user()
        first = self.login().data["refresh"]
        r = self.client.post(f"{API}/auth/token/refresh", {"refresh": first})
        self.assertEqual(r.status_code, 200)
        self.assertNotEqual(r.data["refresh"], first)
        again = self.client.post(
            f"{API}/auth/token/refresh", {"refresh": first}
        )
        self.assertEqual(
            (again.status_code, self.code(again)), (401, "not_authenticated")
        )

    def test_logout_blacklists_the_refresh_token(self):
        self.make_user()
        refresh = self.login().data["refresh"]
        self.assertEqual(
            self.client.post(
                f"{API}/auth/logout", {"refresh": refresh}
            ).status_code,
            204,
        )
        r = self.client.post(
            f"{API}/auth/token/refresh", {"refresh": refresh}
        )
        self.assertEqual(r.status_code, 401)

    def test_an_expired_access_token_returns_token_expired(self):
        self.make_user()
        with mock.patch.object(
            AccessToken, "lifetime", timedelta(seconds=-1)
        ):
            access = self.login().data[
                "access"
            ]  # issued, but dead on arrival
        r = self.client.get(
            f"{API}/me", HTTP_AUTHORIZATION="Bearer " + access
        )
        self.assertEqual(
            (r.status_code, self.code(r)), (401, "token_expired")
        )
```

The last test is a good example of testing a time-based rule without waiting: we temporarily set the access token lifetime to minus one second, so a token issued at login is already expired. The test proves the client receives the specific `token_expired` code it needs to trigger a silent refresh.


## Email Verification and Password Reset › Tests

**accounts/tests.py (add)**

```
class EmailTests(AuthTestCase):
    def emailed_token(self):
        return re.search(r"token=(\S+)", mail.outbox[-1].body).group(1)

    def test_verification_link_marks_the_email_verified(self):
        self.client.post(
            f"{API}/auth/register",
            {"email": "a@example.com", "name": "A", "password": GOOD},
        )
        r = self.client.post(
            f"{API}/auth/verify-email", {"token": self.emailed_token()}
        )
        self.assertEqual(r.status_code, 204)
        self.assertTrue(User.objects.get().email_verified)

    def test_tampered_and_expired_links_are_rejected(self):
        self.client.post(
            f"{API}/auth/register",
            {"email": "a@example.com", "name": "A", "password": GOOD},
        )
        token = self.emailed_token()
        bad = self.client.post(
            f"{API}/auth/verify-email", {"token": token + "x"}
        )
        self.assertEqual(
            (bad.status_code, self.code(bad)), (400, "invalid_token")
        )
        three_days = __import__("time").time() + 3 * 24 * 3600
        with mock.patch("time.time", return_value=three_days):
            old = self.client.post(
                f"{API}/auth/verify-email", {"token": token}
            )
        self.assertEqual(old.status_code, 400)

    def test_password_reset_request_never_reveals_whether_the_email_exists(
        self,
    ):
        self.make_user()
        known = self.client.post(
            f"{API}/auth/password-reset", {"email": "ada@example.com"}
        )
        unknown = self.client.post(
            f"{API}/auth/password-reset", {"email": "no@example.com"}
        )
        self.assertEqual((known.status_code, unknown.status_code), (202, 202))
        self.assertEqual(
            len(mail.outbox), 1
        )  # only the real account got an email

    def test_reset_changes_the_password_signs_out_devices_and_works_once(
        self,
    ):
        user = self.make_user()
        refresh = self.login().data["refresh"]
        self.client.post(
            f"{API}/auth/password-reset", {"email": "ada@example.com"}
        )
        uid, token = re.search(
            r"uid=(\S+)&token=(\S+)", mail.outbox[-1].body
        ).groups()
        body = {
            "uid": uid,
            "token": token,
            "new_password": "a-brand-new-passphrase",
        }
        self.assertEqual(
            self.client.post(
                f"{API}/auth/password-reset/confirm", body
            ).status_code,
            204,
        )
        self.assertTrue(
            User.objects.get(pk=user.pk).check_password(
                "a-brand-new-passphrase"
            )
        )
        old = self.client.post(
            f"{API}/auth/token/refresh", {"refresh": refresh}
        )
        self.assertEqual(old.status_code, 401)  # the old session is gone
        reuse = self.client.post(f"{API}/auth/password-reset/confirm", body)
        self.assertEqual(
            (reuse.status_code, self.code(reuse)), (400, "invalid_token")
        )

    def test_reset_rejects_a_weak_new_password(self):
        self.make_user()
        self.client.post(
            f"{API}/auth/password-reset", {"email": "ada@example.com"}
        )
        uid, token = re.search(
            r"uid=(\S+)&token=(\S+)", mail.outbox[-1].body
        ).groups()
        r = self.client.post(
            f"{API}/auth/password-reset/confirm",
            {"uid": uid, "token": token, "new_password": "password"},
        )
        self.assertEqual(r.status_code, 422)
```

`test_tampered_and_expired_links_are_rejected` fakes the passage of three days by patching `time.time` for a moment. `test_reset_changes_the_password_signs_out_devices_and_works_once` is the most valuable test in the chapter: it walks the whole recovery story and proves the four properties we just listed.


## Social Login with Google › Tests

We cannot call Google from tests, so we replace the one function that talks to it with a fake using `mock.patch`. This is a standard technique: isolate the single boundary with the outside world, and test everything on your side of it.

**accounts/tests.py (add)**

```
class GoogleLoginTests(AuthTestCase):
    def google(self, **claims):
        base = {
            "sub": "g-123",
            "email": "ada@example.com",
            "email_verified": True,
            "name": "Ada",
        }
        return mock.patch(
            "accounts.social.verify_google_token",
            return_value={**base, **claims},
        )

    def test_first_google_sign_in_creates_a_verified_user_without_a_password(
        self,
    ):
        with self.google():
            r = self.client.post(f"{API}/auth/google", {"id_token": "fake"})
        self.assertEqual(r.status_code, 200)
        user = User.objects.get()
        self.assertTrue(user.email_verified)
        self.assertFalse(user.has_usable_password())
        self.assertTrue(
            SocialAccount.objects.filter(user=user, uid="g-123").exists()
        )

    def test_second_sign_in_reuses_the_same_user(self):
        with self.google():
            self.client.post(f"{API}/auth/google", {"id_token": "fake"})
            self.client.post(f"{API}/auth/google", {"id_token": "fake"})
        self.assertEqual(User.objects.count(), 1)

    def test_an_unverified_google_email_is_refused(self):
        with self.google(email_verified=False):
            r = self.client.post(f"{API}/auth/google", {"id_token": "fake"})
        self.assertEqual(r.status_code, 422)
        self.assertEqual(User.objects.count(), 0)

    def test_linking_to_an_unverified_account_discards_its_password(self):
        squatter = self.make_user(password="attacker-chosen-password")
        with self.google():
            self.client.post(f"{API}/auth/google", {"id_token": "fake"})
        squatter.refresh_from_db()
        self.assertTrue(squatter.email_verified)
        self.assertFalse(squatter.check_password("attacker-chosen-password"))
```


## Authorization: Roles and Permissions (RBAC) › Tests

**accounts/tests.py (add)**

```
class RoleTests(AuthTestCase):
    def test_admin_endpoint_needs_the_admin_role(self):
        member, admin = self.make_user(), self.make_user(
            "boss@example.com", role="admin"
        )
        self.sign_in(member)
        r = self.client.get(f"{API}/admin/users")
        self.assertEqual(
            (r.status_code, self.code(r)), (403, "permission_denied")
        )
        self.sign_in(admin)
        self.assertEqual(
            self.client.get(f"{API}/admin/users").status_code, 200
        )

    def test_unverified_users_cannot_create_farms(self):
        user = self.make_user()
        self.sign_in(user)
        r = self.client.post(f"{API}/farms", {"name": "Green Acres"})
        self.assertEqual(
            (r.status_code, self.code(r)), (403, "permission_denied")
        )
        user.email_verified = True
        user.save()
        self.assertEqual(
            self.client.post(
                f"{API}/farms", {"name": "Green Acres"}
            ).status_code,
            201,
        )

    def farm_with_roles(self):
        farm = Farm.objects.create(name="Green Acres")
        people = {}
        for role in ("owner", "manager", "worker"):
            people[role] = self.make_user(
                f"{role}@example.com", email_verified=True
            )
            FarmMember.objects.create(farm=farm, user=people[role], role=role)
        people["outsider"] = self.make_user(
            "out@example.com", email_verified=True
        )
        return farm, people

    def test_farm_permissions_follow_the_member_role(self):
        farm, people = self.farm_with_roles()
        url = f"{API}/farms/{farm.public_id}"
        expected = {  # who gets which status for GET, PATCH, DELETE
            "worker": (200, 403, 403),
            "manager": (200, 200, 403),
            "outsider": (
                404,
                404,
                404,
            ),  # not a member: the farm "does not exist"
        }
        for who, codes in expected.items():
            self.sign_in(people[who])
            got = (
                self.client.get(url).status_code,
                self.client.patch(url, {"name": "Renamed"}).status_code,
                self.client.delete(url).status_code,
            )
            self.assertEqual(got, codes, who)
        self.sign_in(people["owner"])
        self.assertEqual(self.client.delete(url).status_code, 204)
```

The farm test loops over a small table of expected status codes, one row per kind of person. A table like this is the best documentation an authorization rule can have: when someone changes the policy, exactly one row of the test fails and tells them what they broke.
