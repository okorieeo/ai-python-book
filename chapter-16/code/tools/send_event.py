"""send_event.py - pretend to be the email provider and post a signed event.

Run:  python send_event.py email.bounced someone@example.com
"""

import hashlib
import hmac
import json
import sys
import time
import urllib.request
import uuid

SECRET = "dev-secret"  # must match MAILER_WEBHOOK_SECRET on the server
event = {
    "id": "evt_" + uuid.uuid4().hex[:8],
    "type": sys.argv[1],
    "data": {"email": sys.argv[2]},
}
body = json.dumps(event).encode()
stamp = int(time.time())
digest = hmac.new(
    SECRET.encode(), f"{stamp}.".encode() + body, hashlib.sha256
).hexdigest()
request = urllib.request.Request(
    "http://127.0.0.1:8000/api/v1/webhooks/mailer",
    data=body,
    headers={
        "Content-Type": "application/json",
        "X-Webhook-Signature": f"t={stamp},v1={digest}",
    },
)
print(urllib.request.urlopen(request).read().decode())
