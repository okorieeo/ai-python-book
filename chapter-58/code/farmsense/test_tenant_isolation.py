"""One farm must never see, change or hear another farm's data. Run: python manage.py test farmsense
(needs PostgreSQL; NOT run in the book's test environment)."""
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient
from django.test import TestCase

from farmsense_core.devices import generate_device_key
from .models import Alert, AlertRule, Device, Farm, Membership, Sensor, Site

User = get_user_model()


def make_farm(owner, name):
    farm = Farm.objects.create(name=name)
    site = Site.objects.create(farm=farm, name=f"{name} barn")
    key_id, key_hash, full_key = generate_device_key()
    device = Device.objects.create(farm=farm, site=site, name="d1", key_id=key_id, key_hash=key_hash)
    sensor = Sensor.objects.create(device=device, site=site, key=f"{name}-temp", name="Temp", type="temperature")
    rule = AlertRule.objects.create(sensor=sensor, name="hot", kind="above", threshold=30)
    alert = Alert.objects.create(rule=rule, started_at="2026-11-10T12:00:00Z")
    Membership.objects.create(user=owner, farm=farm, role="owner")
    return farm, site, sensor, alert, full_key


class IsolationTests(TestCase):
    def setUp(self):
        self.a, self.b = User.objects.create_user("a", password="x"), User.objects.create_user("b", password="x")
        self.fa, self.sa, self.sensor_a, self.alert_a, self.key_a = make_farm(self.a, "alpha")
        self.fb, self.sb, self.sensor_b, self.alert_b, self.key_b = make_farm(self.b, "beta")

    def test_a_user_cannot_acknowledge_or_read_another_farms_data(self):
        c = APIClient(); c.force_authenticate(self.a)
        self.assertEqual(c.post(f"/api/alerts/{self.alert_b.id}/ack/").status_code, 404)
        self.assertEqual(c.get(f"/api/sensors/{self.sensor_b.id}/readings/", {"start": "2026-11-10T00:00:00+00:00", "end": "2026-11-11T00:00:00+00:00"}).status_code, 404)

    def test_a_worker_limited_to_one_site_cannot_see_the_other(self):
        w = User.objects.create_user("w", password="x")
        second = Site.objects.create(farm=self.fa, name="second barn")
        m = Membership.objects.create(user=w, farm=self.fa, role="worker", all_sites=False)
        m.sites.add(second)
        c = APIClient(); c.force_authenticate(w)
        self.assertEqual(c.post(f"/api/alerts/{self.alert_a.id}/ack/").status_code, 403)   # a member, but not of that site

    def test_a_device_key_works_only_for_its_own_sensors(self):
        c = APIClient()
        body = {"readings": [{"sensor": self.sensor_b.key, "ts": "2026-11-11T12:00:00Z", "value": 22.0}]}
        r = c.post("/api/ingest/", body, format="json", HTTP_AUTHORIZATION=f"Bearer {self.key_a}")
        self.assertEqual(r.json()["accepted"], 0)                                           # alpha's key cannot write to beta's sensor
        self.assertEqual(c.post("/api/ingest/", body, format="json", HTTP_AUTHORIZATION="Bearer fsk_nope_nope").status_code, 401)

    def test_managers_cannot_promote_or_remove_owners(self):
        m = User.objects.create_user("m", password="x")
        Membership.objects.create(user=m, farm=self.fa, role="manager")
        owner_membership = Membership.objects.get(user=self.a, farm=self.fa)
        c = APIClient(); c.force_authenticate(m)
        self.assertEqual(c.delete(f"/api/farms/{self.fa.id}/members/{owner_membership.id}/").status_code, 403)
        self.assertEqual(c.patch(f"/api/farms/{self.fa.id}/members/{owner_membership.id}/", {"role": "viewer"}, format="json").status_code, 403)
