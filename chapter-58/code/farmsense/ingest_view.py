"""The door the devices knock on. NOT executed in the book's test environment."""
import json
from datetime import datetime, timezone

from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from django.db import transaction
from django.http import JsonResponse
from django.utils import timezone as djtz
from django.views.decorators.csrf import csrf_exempt                 # devices have no cookies: they authenticate with a key
from django.views.decorators.http import require_POST

from farmsense_core.devices import verify_device_key
from farmsense_core.ingest import parse_batch

from .models import Device, Sensor
from .readings_sql import insert_readings


def _authenticate(request):
    header = request.headers.get("Authorization", "")
    key = header[7:] if header.startswith("Bearer ") else ""
    device = {}

    def lookup(key_id):
        d = Device.objects.filter(key_id=key_id, revoked_at__isnull=True).first()
        device["obj"] = d
        return d.key_hash if d else None

    return device.get("obj") if verify_device_key(key, lookup) else None


@csrf_exempt
@require_POST
def ingest(request):
    device = _authenticate(request)
    if device is None:
        return JsonResponse({"error": "invalid_key"}, status=401)           # the same answer for unknown, revoked and wrong keys
    if len(request.body) > 512 * 1024:
        return JsonResponse({"error": "too_large"}, status=413)
    try:
        payload = json.loads(request.body)
        sensors = {s.key: s for s in Sensor.objects.filter(device=device)}
        result = parse_batch(payload, {k: s.type for k, s in sensors.items()})
    except ValueError as exc:
        return JsonResponse({"error": str(exc)}, status=400)

    with transaction.atomic():
        insert_readings({k: s.id for k, s in sensors.items()}, result.accepted)
        Device.objects.filter(pk=device.pk).update(last_seen_at=djtz.now())
        live = {}
        for r in result.accepted:
            if not r.late and (r.sensor_key not in live or r.ts > live[r.sensor_key].ts):
                live[r.sensor_key] = r                                       # only the newest reading per sensor goes to dashboards
        transaction.on_commit(lambda: _publish(device.farm_id, sensors, live))
    return JsonResponse({**result.summary(), "server_time": datetime.now(timezone.utc).isoformat()})


def _publish(farm_id, sensors, live):
    layer = get_channel_layer()
    for key, r in live.items():
        s = sensors[key]
        async_to_sync(layer.group_send)(f"farm.{farm_id}", {
            "type": "reading.update", "site_id": s.site_id, "sensor_id": s.id, "ts": r.ts.isoformat(), "value": r.value})
