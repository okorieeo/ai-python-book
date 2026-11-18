"""api_mock.py - a tiny in-memory version of our chat API contract.

Run:  python api_mock.py   (serves http://127.0.0.1:8000/api/v1/...)
Only the Python standard library is used.
"""

import base64, json, re, uuid
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

TOKEN = "demo-token"  # stands in for a real JWT access token
MESSAGE_LIMIT = 30  # the "free plan": user messages allowed
CONVS, SEEN_KEYS, STATE = {}, {}, {"next_id": 1, "sent": 0}
UUID = r"([0-9a-f]{8}-(?:[0-9a-f]{4}-){3}[0-9a-f]{12})"

def now():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")

def conv_json(cid):
    c = CONVS[cid]
    return {
        "id": cid,
        "title": c["title"],
        "created_at": c["created_at"],
        "updated_at": c["updated_at"],
    }

def add_message(cid, role, content, tokens_in=None, tokens_out=None):
    msg = {
        "id": STATE["next_id"],
        "role": role,
        "content": content,
        "input_tokens": tokens_in,
        "output_tokens": tokens_out,
        "created_at": now(),
    }
    STATE["next_id"] += 1
    CONVS[cid]["messages"].append(msg)
    CONVS[cid]["updated_at"] = msg["created_at"]
    return msg

class Api(BaseHTTPRequestHandler):
    def log_message(self, *args):  # keep the console quiet
        pass

    def reply(self, status, body=None, headers=None):
        data = b"" if body is None else json.dumps(body).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Expose-Headers", "Retry-After")
        for key, value in (headers or {}).items():
            self.send_header(key, value)
        self.end_headers()
        self.wfile.write(data)

    def error(self, status, code, message, details=None, headers=None):
        err = {
            "code": code,
            "message": message,
            "request_id": "req_" + uuid.uuid4().hex[:6],
        }
        if details:
            err["details"] = details
        self.reply(status, {"error": err}, headers)

    def body(self):
        size = int(self.headers.get("Content-Length") or 0)
        try:
            data = json.loads(self.rfile.read(size) or b"{}")
        except ValueError:
            data = None
        return data if isinstance(data, dict) else {}

    def invalid(self, field, text):
        self.error(
            422,
            "validation_error",
            "The request contains invalid fields.",
            {field: [text]},
        )

    def limit(self, query):
        raw = query.get("limit", ["20"])[0]  # default 20, maximum 100
        if raw.isdigit() and int(raw) >= 1:
            return min(int(raw), 100)
        self.error(
            400, "invalid_parameter", "limit must be a positive integer."
        )

    def dispatch(self, method):
        if self.headers.get("Authorization") != "Bearer " + TOKEN:
            return self.error(
                401, "not_authenticated", "Missing or invalid token."
            )
        url = urlparse(self.path)
        path, query = url.path.rstrip("/"), parse_qs(url.query)
        match = re.fullmatch(
            r"/api/v1/conversations(?:/" + UUID + r")?(/messages)?", path
        )
        if not match:
            return self.error(404, "not_found", "No such endpoint.")
        cid, messages = match.group(1), match.group(2)
        if cid and cid not in CONVS:
            return self.error(404, "not_found", "Conversation not found.")
        name = {
            "GET": "get",
            "POST": "post",
            "PATCH": "patch",
            "DELETE": "delete",
        }[method]
        kind = "messages" if messages else "conv" if cid else "convs"
        handler = getattr(self, "%s_%s" % (name, kind), None)
        if handler is None:
            return self.error(
                405, "method_not_allowed", "Method not allowed."
            )
        handler(cid, query)

    def do_OPTIONS(self):  # CORS preflight: browsers ask before sending
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header(
            "Access-Control-Allow-Methods", "GET, POST, PATCH, DELETE"
        )
        self.send_header(
            "Access-Control-Allow-Headers",
            "Authorization, Content-Type, Idempotency-Key",
        )
        self.end_headers()

    do_GET = lambda self: self.dispatch("GET")
    do_POST = lambda self: self.dispatch("POST")
    do_PATCH = lambda self: self.dispatch("PATCH")
    do_DELETE = lambda self: self.dispatch("DELETE")

    # ---- /conversations ----------------------------------------------
    def get_convs(self, cid, query):
        limit, offset = self.limit(query), query.get("offset", ["0"])[0]
        if limit is None:
            return
        ids = sorted(
            CONVS, key=lambda c: CONVS[c]["updated_at"], reverse=True
        )
        page = (
            ids[int(offset) : int(offset) + limit] if offset.isdigit() else []
        )
        self.reply(
            200, {"count": len(ids), "results": [conv_json(c) for c in page]}
        )

    def post_convs(self, cid, query):
        new_id, stamp = str(uuid.uuid4()), now()
        CONVS[new_id] = {
            "title": self.body().get("title") or "New conversation",
            "created_at": stamp,
            "updated_at": stamp,
            "messages": [],
        }
        self.reply(201, conv_json(new_id))

    def get_conv(self, cid, query):
        self.reply(200, conv_json(cid))

    def patch_conv(self, cid, query):
        title = self.body().get("title")
        if not isinstance(title, str) or not 1 <= len(title.strip()) <= 200:
            return self.invalid("title", "Enter 1 to 200 characters.")
        CONVS[cid]["title"] = title.strip()
        self.reply(200, conv_json(cid))

    def delete_conv(self, cid, query):
        del CONVS[cid]
        self.reply(204)

    # ---- /conversations/{id}/messages ----------------------------------
    def get_messages(self, cid, query):
        limit = self.limit(query)
        if limit is None:
            return
        newest_first = CONVS[cid]["messages"][::-1]
        if "cursor" in query:  # cursor means: only rows older than this id
            try:
                last = json.loads(
                    base64.urlsafe_b64decode(query["cursor"][0])
                )["id"]
            except (ValueError, KeyError, TypeError):
                return self.error(
                    400, "invalid_cursor", "The cursor is not valid."
                )
            newest_first = [m for m in newest_first if m["id"] < last]
        page, cursor = newest_first[:limit], None
        if len(newest_first) > limit:
            token = json.dumps({"id": page[-1]["id"]}).encode()
            cursor = base64.urlsafe_b64encode(token).decode()
        self.reply(200, {"results": page, "next_cursor": cursor})

    def post_messages(self, cid, query):
        key = self.headers.get("Idempotency-Key")
        if key in SEEN_KEYS:  # same key again: replay, do no new work
            return self.reply(
                201, SEEN_KEYS[key], {"Idempotent-Replayed": "true"}
            )
        content = self.body().get("content")
        if (
            not isinstance(content, str)
            or not 1 <= len(content.strip()) <= 8000
        ):
            return self.invalid("content", "Enter 1 to 8000 characters.")
        if STATE["sent"] >= MESSAGE_LIMIT:
            return self.error(
                429,
                "plan_limit_reached",
                "Message limit reached.",
                headers={"Retry-After": "3600"},
            )
        message = add_message(cid, "user", content)
        words = len(content.split())
        add_message(cid, "assistant", "Echo: " + content, words, words + 1)
        STATE["sent"] += 1
        if key:
            SEEN_KEYS[key] = message
        self.reply(201, message)

def make_server(port=8000):
    return ThreadingHTTPServer(("127.0.0.1", port), Api)

if __name__ == "__main__":
    print("Serving on http://127.0.0.1:8000 (token: %s)" % TOKEN)
    make_server().serve_forever()
