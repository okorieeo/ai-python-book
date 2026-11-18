from django.contrib.auth import get_user_model
from django.db import IntegrityError, transaction
from django.test import TestCase

User = get_user_model()

class UserManagerTests(TestCase):
    def test_create_user_normalizes_email_and_hashes_password(self):
        user = User.objects.create_user(email="Ada@Example.COM", password="a-long-test-password")
        self.assertEqual(user.email, "ada@example.com")
        self.assertNotEqual(user.password, "a-long-test-password")      # stored as a hash
        self.assertTrue(user.check_password("a-long-test-password"))
        self.assertFalse(user.is_staff)

    def test_email_must_be_unique_ignoring_case(self):
        User.objects.create_user(email="ada@example.com", password="a-long-test-password")
        with self.assertRaises(IntegrityError), transaction.atomic():
            User.objects.create_user(email="ADA@example.com", password="another-long-password")

    def test_email_is_required(self):
        with self.assertRaises(ValueError):
            User.objects.create_user(email="", password="a-long-test-password")

    def test_create_superuser_sets_flags(self):
        admin_user = User.objects.create_superuser(email="root@example.com", password="a-long-test-password")
        self.assertTrue(admin_user.is_staff)
        self.assertTrue(admin_user.is_superuser)
