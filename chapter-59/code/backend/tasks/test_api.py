"""Two-user tests for the REST API (Chapter 17's habit). NOT run while writing Chapter 59: run them in your project.

Adapt make_user() to the required fields of your own user model (Chapter 13).
"""
from django.contrib.auth import get_user_model
from rest_framework.test import APITestCase

from schedule.models import Event
from tasks.models import Task


def make_user(n: int):
    return get_user_model().objects.create_user(email=f"user{n}@example.com", password="x" * 20)


class TwoUserTaskTests(APITestCase):
    def setUp(self):
        self.ada, self.bo = make_user(1), make_user(2)
        self.task = Task.objects.create(user=self.ada, title="Ada's task")
        self.client.force_authenticate(self.bo)  # every request below is made by Bo

    def test_list_shows_only_my_tasks(self):
        Task.objects.create(user=self.bo, title="Bo's task")
        titles = [t["title"] for t in self.client.get("/api/v1/tasks/").json()["results"]]
        self.assertEqual(titles, ["Bo's task"])

    def test_another_users_task_does_not_exist(self):
        url = f"/api/v1/tasks/{self.task.public_id}/"
        self.assertEqual(self.client.get(url).status_code, 404)
        self.assertEqual(self.client.patch(url, {"title": "hacked"}, format="json").status_code, 404)
        self.assertEqual(self.client.delete(url).status_code, 404)
        self.assertEqual(self.client.post(url + "complete/").status_code, 404)
        self.task.refresh_from_db()
        self.assertEqual((self.task.title, self.task.status), ("Ada's task", "todo"))

    def test_clients_cannot_set_the_owner_or_timestamps(self):
        response = self.client.post(
            "/api/v1/tasks/",
            {"title": "Mine", "user": self.ada.id, "completed_at": "2020-01-01T00:00:00Z"},
            format="json",
        )
        self.assertEqual(response.status_code, 201)
        task = Task.objects.get(public_id=response.json()["id"])
        self.assertEqual(task.user_id, self.bo.id)
        self.assertIsNone(task.completed_at)

    def test_a_filter_that_was_not_offered_is_ignored(self):
        response = self.client.get("/api/v1/tasks/?user__password__startswith=a")
        self.assertEqual(response.status_code, 200)


class TwoUserEventTests(APITestCase):
    def setUp(self):
        self.ada, self.bo = make_user(1), make_user(2)
        self.client.force_authenticate(self.ada)
        created = self.client.post(
            "/api/v1/events/",
            {"title": "Ada's private meeting", "start": "2026-11-12T10:00", "end": "2026-11-12T11:00"},
            format="json",
        )
        self.assertEqual(created.status_code, 201)
        self.event_id = created.json()["id"]

    def test_another_users_event_does_not_exist_and_is_not_listed(self):
        self.client.force_authenticate(self.bo)
        self.assertEqual(self.client.get(f"/api/v1/events/{self.event_id}/").status_code, 404)
        self.assertEqual(self.client.delete(f"/api/v1/events/{self.event_id}/").status_code, 404)
        listing = self.client.get("/api/v1/events/?start=2026-11-12&end=2026-11-12").json()["results"]
        self.assertEqual(listing, [])
        self.assertTrue(Event.objects.filter(public_id=self.event_id).exists())

    def test_times_must_be_local_without_an_offset(self):
        bad = self.client.post(
            "/api/v1/events/",
            {"title": "x", "start": "2026-11-12T10:00Z", "end": "2026-11-12T11:00Z"},
            format="json",
        )
        self.assertEqual(bad.status_code, 400)

    def test_a_wide_range_is_refused(self):
        response = self.client.get("/api/v1/events/?start=2026-01-01&end=2028-01-01")
        self.assertEqual(response.status_code, 400)
