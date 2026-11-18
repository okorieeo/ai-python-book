"""receiver.py - a tiny webhook receiver that verifies our signature.

Run:  python receiver.py   (listens on http://127.0.0.1:9000)
This is what YOUR CUSTOMERS write on their side.
"""

import hashlib
import hmac
import json
import sys
import time
from http.server import BaseHTTPRequestHandler, HTTPServer

# The whsec_... value shown when the endpoint was created:
SECRET = sys.argv[1]


class Receiver(BaseHTTPRequestHandler):
    def do_POST(self):
        body = self.rfile.read(int(self.headers["Content-Length"]))
        parts = dict(
            p.split("=", 1)
            for p in self.headers["X-Webhook-Signature"].split(",")
        )
        expected = hmac.new(
            SECRET.encode(), f"{parts['t']}.".encode() + body, hashlib.sha256
        ).hexdigest()
        fresh = abs(time.time() - int(parts["t"])) < 300
        valid = hmac.compare_digest(expected, parts["v1"]) and fresh
        event = json.loads(body)
        kind, event_id = event["type"], event["id"]
        print("signature valid:", valid, "| event:", kind, "| id:", event_id)
        self.send_response(200 if valid else 400)
        self.end_headers()

    def log_message(self, *args):
        pass


HTTPServer(("127.0.0.1", 9000), Receiver).serve_forever()
