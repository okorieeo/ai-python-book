"""A fake sensor device for trying the whole platform without hardware.

    python scripts/simulate_device.py --url http://localhost:8000/api/ingest/ --key fsk_xxxx_yyyy --sensor barn1-temp --minutes 120

It sends one batch of simulated temperature readings (the last N minutes), then keeps sending one reading a minute until stopped.
--heat adds a heat wave so you can watch an alert fire. Standard library only."""
import argparse
import json
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone

sys.path.insert(0, __file__.rsplit("/scripts/", 1)[0])
from farmsense_core.simulator import simulate_temperature          # noqa: E402


def build_batches(sensor: str, now: datetime, minutes: int, heat: bool = False, batch_size: int = 200, seed: int = 1):
    start = now - timedelta(minutes=minutes)
    waves = [(start + timedelta(minutes=minutes // 2), now + timedelta(hours=3), 9.0)] if heat else []
    points = simulate_temperature(start, now, 60, seed=seed, heat_waves=waves)
    readings = [{"sensor": sensor, "ts": ts.isoformat(), "value": v} for ts, v in points]
    return [{"readings": readings[i:i + batch_size]} for i in range(0, len(readings), batch_size)]


def post(url: str, key: str, payload: dict) -> dict:
    req = urllib.request.Request(url, json.dumps(payload).encode(), {"Content-Type": "application/json", "Authorization": f"Bearer {key}"})
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return json.load(resp)
    except urllib.error.HTTPError as exc:
        return {"error": exc.code, "body": exc.read().decode()[:200]}


def main(argv=None) -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--url", required=True)
    p.add_argument("--key", required=True)
    p.add_argument("--sensor", required=True)
    p.add_argument("--minutes", type=int, default=120)
    p.add_argument("--heat", action="store_true")
    a = p.parse_args(argv)
    now = datetime.now(timezone.utc).replace(second=0, microsecond=0)
    for batch in build_batches(a.sensor, now, a.minutes, a.heat):
        print(post(a.url, a.key, batch))
    while True:                                                      # then live: one reading per minute
        time.sleep(60)
        now = datetime.now(timezone.utc).replace(second=0, microsecond=0)
        print(post(a.url, a.key, build_batches(a.sensor, now, 1, a.heat, seed=int(now.timestamp()))[0]))


if __name__ == "__main__":
    raise SystemExit(main())
