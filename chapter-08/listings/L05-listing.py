"""api_check.py - proves the contract rules against api_mock.py.

Run:  python api_check.py
"""

import json, sys, threading, urllib.error, urllib.request
from api_mock import make_server

BASE, failures = "http://127.0.0.1:8099/api/v1", []

def call(method, path, body=None, token="demo-token", **headers):
    """Send one request; return (status, headers, parsed JSON or None)."""
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(BASE + path, data=data, method=method)
    if token:
        req.add_header("Authorization", "Bearer " + token)
    for name, value in headers.items():
        req.add_header(name.replace("_", "-"), value)
    try:
        resp = urllib.request.urlopen(req)
    except urllib.error.HTTPError as err:
        resp = err
    raw = resp.read()
    return resp.status, resp.headers, (json.loads(raw) if raw else None)

def check(name, ok):
    print(("PASS  " if ok else "FAIL  ") + name)
    if not ok:
        failures.append(name)

server = make_server(8099)
threading.Thread(target=server.serve_forever, daemon=True).start()

# Rule 1: no token -> 401 in the standard error shape
status, _, body = call("GET", "/conversations", token=None)
check(
    "missing token returns 401",
    status == 401 and body["error"]["code"] == "not_authenticated",
)

# Rule 2: create a conversation -> 201 and a UUID id
status, _, conv = call("POST", "/conversations", {})
cid = conv["id"]
msgs = "/conversations/%s/messages" % cid
check("creating a conversation returns 201", status == 201 and len(cid) == 36)

# Rule 3: invalid input -> 422 with per-field details
status, _, body = call("POST", msgs, {"content": "  "})
check(
    "blank message returns 422 + details",
    status == 422 and "content" in body["error"]["details"],
)

# Rule 4: a message creates the question and the assistant's answer
status, _, msg = call("POST", msgs, {"content": "Hello"})
_, _, page = call("GET", msgs)
check(
    "sending a message returns 201", status == 201 and msg["role"] == "user"
)
check("history holds question + answer", len(page["results"]) == 2)

# Rule 5: the same Idempotency-Key is processed once
key = "7c9e6679-7425-40de-944b-e07fc1f90ae7"
s1, _, first = call("POST", msgs, {"content": "Pay"}, Idempotency_Key=key)
s2, hdr, again = call("POST", msgs, {"content": "Pay"}, Idempotency_Key=key)
_, _, page = call("GET", msgs)
check(
    "a retry returns the same message",
    s1 == s2 == 201 and first["id"] == again["id"],
)
check(
    "the retry is flagged as a replay", hdr["Idempotent-Replayed"] == "true"
)
check("no duplicate was created (4 messages)", len(page["results"]) == 4)

# Rule 6: cursor pagination visits every message once, newest first
for i in range(10):
    call("POST", msgs, {"content": "Message %d" % i})
seen, sizes, cursor = [], [], None
while True:
    _, _, page = call(
        "GET", msgs + "?limit=8" + ("&cursor=" + cursor if cursor else "")
    )
    sizes.append(len(page["results"]))
    seen += [m["id"] for m in page["results"]]
    cursor = page["next_cursor"]
    if not cursor:
        break
check("pages of 8 cover 24 messages: %s" % sizes, sizes == [8, 8, 8])
check(
    "no duplicates, newest first",
    len(set(seen)) == 24 and seen == sorted(seen)[::-1],
)
status, _, body = call("GET", msgs + "?limit=abc")
check(
    "bad limit returns 400",
    status == 400 and body["error"]["code"] == "invalid_parameter",
)

# Rule 7: the plan limit returns 429 plus Retry-After
status = 201
while status == 201:
    status, hdr, body = call("POST", msgs, {"content": "x"})
check(
    "plan limit returns 429 + Retry-After",
    status == 429 and hdr["Retry-After"] == "3600",
)
check(
    "error code is plan_limit_reached",
    body["error"]["code"] == "plan_limit_reached",
)

# Rule 8: rename, delete, and honest 404s
status, _, body = call(
    "PATCH", "/conversations/" + cid, {"title": "Invoices"}
)
check("rename returns 200", status == 200 and body["title"] == "Invoices")
check("delete returns 204", call("DELETE", "/conversations/" + cid)[0] == 204)
status, _, body = call("GET", "/conversations/" + cid)
check(
    "deleted conversation returns 404",
    status == 404 and body["error"]["code"] == "not_found",
)

server.shutdown()
print("\n%d problem(s)" % len(failures) if failures else "\nAll rules hold.")
sys.exit(1 if failures else 0)
