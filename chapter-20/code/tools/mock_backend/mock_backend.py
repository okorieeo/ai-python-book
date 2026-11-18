"""A stand-in for the Django backend, implementing the auth and API contract from Chapters 8 and 13.

Standard library only. Use it to build and test the Next.js app before (or without) the real backend.

    python mock_backend.py                 # http://localhost:8000
    PORT=8100 ACCESS_TTL=3 python mock_backend.py       # short-lived access tokens, to watch refreshes happen
"""
import base64
import hashlib
import hmac
import json
import os
import re
import threading
import time
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

PORT = int(os.environ.get("PORT", "8000"))
ACCESS_TTL = int(os.environ.get("ACCESS_TTL", "900"))              # seconds
REFRESH_TTL = int(os.environ.get("REFRESH_TTL", str(30 * 24 * 3600)))
SECRET = os.environ.get("MOCK_SECRET", "dev-only-secret").encode()
PREFIX = "/api/v1"
MAX_LIMIT = 50

USERS = {
    "ada@example.com": {"id": "usr_ada", "name": "Ada", "password": "correct-horse-battery"},
    "bo@example.com": {"id": "usr_bo", "name": "Bo", "password": "another-long-password"},
}
LOCK = threading.Lock()
STATS = {"login_calls": 0, "refresh_calls": 0}
REFRESH_TOKENS: dict[str, dict] = {}                                # jti -> {user, family, used}
REVOKED_FAMILIES: set[str] = set()
CONVERSATIONS: dict[str, list] = {}
IDEMPOTENT: dict[tuple, tuple] = {}

def seed():
    CONVERSATIONS.clear()
    CONVERSATIONS["usr_ada"] = [
        {"id": f"cnv_{i:03d}", "title": f"Conversation {i}", "created_at": f"2026-11-01T09:{i:02d}:00Z"}
        for i in range(7, 0, -1)
    ]
    CONVERSATIONS["usr_bo"] = []

# ----------------------------------------------------------------------------- tokens (HS256 JWT)
def b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()

def unb64(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))

def make_token(user_id: str, kind: str, ttl: int, family: str | None = None) -> tuple[str, str]:
    jti = uuid.uuid4().hex
    now = int(time.time())
    payload = {"sub": user_id, "type": kind, "jti": jti, "iat": now, "exp": now + ttl}
    if family:
        payload["fam"] = family
    head = b64(json.dumps({"alg": "HS256", "typ": "JWT"}).encode())
    body = b64(json.dumps(payload).encode())
    sig = b64(hmac.new(SECRET, f"{head}.{body}".encode(), hashlib.sha256).digest())
    return f"{head}.{body}.{sig}", jti

class TokenError(Exception):
    def __init__(self, code: str):
        self.code = code

def read_token(token: str, kind: str) -> dict:
    try:
        head, body, sig = token.split(".")
        expected = b64(hmac.new(SECRET, f"{head}.{body}".encode(), hashlib.sha256).digest())
        if not hmac.compare_digest(sig, expected):
            raise TokenError("token_invalid")
        payload = json.loads(unb64(body))
    except TokenError:
        raise
    except Exception:
        raise TokenError("token_invalid") from None
    if payload.get("type") != kind:
        raise TokenError("token_invalid")
    if payload["exp"] <= time.time():
        raise TokenError("token_expired")
    return payload

def issue_pair(user_id: str, family: str | None = None) -> dict:
    family = family or uuid.uuid4().hex
    access, _ = make_token(user_id, "access", ACCESS_TTL)
    refresh, jti = make_token(user_id, "refresh", REFRESH_TTL, family)
    REFRESH_TOKENS[jti] = {"user": user_id, "family": family, "used": False}
    return {"access": access, "refresh": refresh}

def encode_cursor(last_id: str) -> str:
    return base64.urlsafe_b64encode(json.dumps({"after": last_id}).encode()).decode()

class Handler(BaseHTTPRequestHandler):
    # ---------------------------------------------------------------- helpers
    def _send(self, status, payload=None, headers=None):
        body = b"" if payload is None else json.dumps(payload).encode()
        self.send_response(status)
        self.send_header("X-Request-ID", self.request_id)
        if payload is not None:
            self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        for key, value in (headers or {}).items():
            self.send_header(key, value)
        self.end_headers()
        self.wfile.write(body)

    def _error(self, status, code, message, details=None, headers=None):
        error = {"code": code, "message": message}
        if details:
            error["details"] = details
        self._send(status, {"error": error, "request_id": self.request_id}, headers)

    def _body(self):
        if "application/json" not in self.headers.get("Content-Type", ""):
            self._error(415, "unsupported_media_type", "Send the body as application/json.")
            return None
        try:
            data = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))) or b"{}")
        except json.JSONDecodeError:
            self._error(400, "invalid_json", "The request body is not valid JSON.")
            return None
        if not isinstance(data, dict):
            self._error(400, "invalid_json", "The request body must be a JSON object.")
            return None
        return data

    def _user(self):
        header = self.headers.get("Authorization", "")
        if not header.startswith("Bearer "):
            self._error(401, "not_authenticated", "Missing or invalid credentials.", headers={"WWW-Authenticate": "Bearer"})
            return None
        try:
            return read_token(header[7:], "access")["sub"]
        except TokenError as error:
            self._error(401, error.code, "Your access token is not valid.", headers={"WWW-Authenticate": "Bearer"})
            return None

    # ---------------------------------------------------------------- routing
    def _route(self, method):
        self.request_id = self.headers.get("X-Request-ID") or "req_" + uuid.uuid4().hex[:12]
        url = urlparse(self.path)
        path, query = url.path.rstrip("/"), parse_qs(url.query)
        public = {
            ("POST", f"{PREFIX}/auth/login"): self.login,
            ("POST", f"{PREFIX}/auth/refresh"): self.refresh,
            ("POST", f"{PREFIX}/auth/logout"): self.logout,
            ("POST", f"{PREFIX}/auth/register"): self.register,
            ("GET", f"{PREFIX}/health"): lambda q: self._send(200, {"status": "ok"}),
            ("GET", f"{PREFIX}/_debug/stats"): lambda q: self._send(200, STATS),
            ("POST", f"{PREFIX}/_debug/reset"): self.reset,
            ("GET", f"{PREFIX}/_debug/slow"): self.slow,
        }
        handler = public.get((method, path))
        if handler:
            return handler(query)
        if not path.startswith(PREFIX):
            return self._error(404, "not_found", "Unknown path.")

        user_id = self._user()
        if user_id is None:
            return
        self.user_id = user_id
        routes = [
            ("GET", rf"^{PREFIX}/me$", self.me),
            ("GET", rf"^{PREFIX}/conversations$", self.list_conversations),
            ("POST", rf"^{PREFIX}/conversations$", self.create_conversation),
            ("GET", rf"^{PREFIX}/conversations/(?P<cid>[a-z0-9_]+)$", self.get_conversation),
            ("POST", rf"^{PREFIX}/ws-ticket$", self.ws_ticket),
            ("GET", rf"^{PREFIX}/_debug/headers$", self.echo_headers),
            ("GET", rf"^{PREFIX}/_debug/boom$", self.boom),
            ("GET", rf"^{PREFIX}/_debug/stream$", self.stream),
        ]
        allowed = []
        for route_method, pattern, func in routes:
            match = re.match(pattern, path)
            if match:
                if route_method == method:
                    return func(query, **match.groupdict())
                allowed.append(route_method)
        if allowed:
            return self._error(405, "method_not_allowed", f"{method} is not allowed here.", headers={"Allow": ", ".join(allowed)})
        self._error(404, "not_found", "Unknown path.")

    def do_GET(self): self._route("GET")
    def do_POST(self): self._route("POST")
    def do_PUT(self): self._route("PUT")
    def do_PATCH(self): self._route("PATCH")
    def do_DELETE(self): self._route("DELETE")
    def log_message(self, format, *args): pass

    # ---------------------------------------------------------------- auth
    def login(self, query):
        data = self._body()
        if data is None:
            return
        email, password = data.get("email"), data.get("password")
        problems = {}
        if not isinstance(email, str) or not email.strip():
            problems["email"] = ["This field is required."]
        if not isinstance(password, str) or not password:
            problems["password"] = ["This field is required."]
        if problems:
            return self._error(400, "validation_error", "The request data is invalid.", problems)
        user = USERS.get(email.strip().lower())
        with LOCK:
            STATS["login_calls"] += 1
        if not user or not hmac.compare_digest(user["password"], password):
            return self._error(401, "authentication_failed", "Incorrect email or password.")
        with LOCK:
            pair = issue_pair(user["id"])
        self._send(200, {**pair, "user": {"id": user["id"], "email": email.strip().lower(), "name": user["name"]}})

    def refresh(self, query):
        data = self._body()
        if data is None:
            return
        with LOCK:
            STATS["refresh_calls"] += 1
            try:
                payload = read_token(str(data.get("refresh", "")), "refresh")
            except TokenError as error:
                return self._error(401, error.code, "Your session has expired. Please log in again.")
            entry = REFRESH_TOKENS.get(payload["jti"])
            if entry is None or entry["family"] in REVOKED_FAMILIES:
                return self._error(401, "token_invalid", "Your session is no longer valid.")
            if entry["used"]:                                  # reuse of a rotated token: assume theft, revoke the family
                REVOKED_FAMILIES.add(entry["family"])
                return self._error(401, "token_reused", "This session was revoked for your safety.")
            entry["used"] = True
            pair = issue_pair(entry["user"], entry["family"])
        self._send(200, pair)

    def logout(self, query):
        data = self._body()
        if data is not None:
            try:
                payload = read_token(str(data.get("refresh", "")), "refresh")
                REVOKED_FAMILIES.add(payload["fam"])
            except TokenError:
                pass
        self._send(204)

    def register(self, query):
        data = self._body()
        if data is None:
            return
        email, password, name = data.get("email"), data.get("password"), data.get("name")
        problems = {}
        if not isinstance(email, str) or "@" not in email:
            problems["email"] = ["Enter a valid email address."]
        elif email.strip().lower() in USERS:
            problems["email"] = ["A user with this email already exists."]
        if not isinstance(password, str) or len(password) < 8:
            problems["password"] = ["This password is too short. It must contain at least 8 characters."]
        if not isinstance(name, str) or not name.strip():
            problems["name"] = ["This field is required."]
        if problems:
            return self._error(400, "validation_error", "The request data is invalid.", problems)
        USERS[email.strip().lower()] = {"id": "usr_" + uuid.uuid4().hex[:6], "name": name.strip(), "password": password}
        self._send(201, {"detail": "Account created. Check your email to verify your address."})

    def reset(self, query):
        with LOCK:
            STATS.update(login_calls=0, refresh_calls=0)
            REFRESH_TOKENS.clear()
            REVOKED_FAMILIES.clear()
            IDEMPOTENT.clear()
            seed()
            for key in [k for k in USERS if k not in ("ada@example.com", "bo@example.com")]:
                del USERS[key]
        self._send(200, {"reset": True})

    # ---------------------------------------------------------------- API
    def me(self, query):
        user = next(u for u in USERS.items() if u[1]["id"] == self.user_id)
        self._send(200, {"id": self.user_id, "email": user[0], "name": user[1]["name"]})

    def list_conversations(self, query):
        raw = query.get("limit", ["20"])[0]
        if not raw.isdigit() or not 1 <= int(raw) <= MAX_LIMIT:
            return self._error(400, "validation_error", "Invalid query parameters.", {"limit": [f"Must be an integer between 1 and {MAX_LIMIT}."]})
        limit, items = int(raw), CONVERSATIONS.get(self.user_id, [])
        if "cursor" in query:
            try:
                after = json.loads(base64.urlsafe_b64decode(query["cursor"][0]))["after"]
            except Exception:
                return self._error(400, "validation_error", "Invalid query parameters.", {"cursor": ["Invalid cursor."]})
            ids = [c["id"] for c in items]
            items = items[ids.index(after) + 1:] if after in ids else []
        page = items[:limit]
        self._send(200, {"results": page, "next": encode_cursor(page[-1]["id"]) if len(items) > limit else None})

    def get_conversation(self, query, cid):
        for conversation in CONVERSATIONS.get(self.user_id, []):
            if conversation["id"] == cid:
                return self._send(200, conversation)
        self._error(404, "not_found", "Conversation not found.")

    def create_conversation(self, query):
        key = self.headers.get("Idempotency-Key")
        with LOCK:
            if key and (self.user_id, key) in IDEMPOTENT:
                status, payload = IDEMPOTENT[(self.user_id, key)]
                return self._send(status, payload, {"Idempotent-Replayed": "true"})
        data = self._body()
        if data is None:
            return
        title = data.get("title")
        if not isinstance(title, str) or not 1 <= len(title.strip()) <= 200:
            return self._error(400, "validation_error", "The request data is invalid.", {"title": ["This field is required and must be 1 to 200 characters."]})
        with LOCK:
            items = CONVERSATIONS.setdefault(self.user_id, [])
            conversation = {"id": f"cnv_{uuid.uuid4().hex[:6]}", "title": title.strip(), "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
            items.insert(0, conversation)
            if key:
                IDEMPOTENT[(self.user_id, key)] = (201, conversation)
        self._send(201, conversation, {"Location": f"{PREFIX}/conversations/{conversation['id']}"})

    def ws_ticket(self, query):
        self._send(200, {"ticket": "tkt_" + uuid.uuid4().hex, "expires_in": 30})

    # ---------------------------------------------------------------- test helpers
    def echo_headers(self, query):
        self._send(200, {k.lower(): v for k, v in self.headers.items()})

    def boom(self, query):
        self._error(500, "internal_error", "Something went wrong on our side.")

    def slow(self, query):
        time.sleep(int(query.get("ms", ["100"])[0]) / 1000)
        self.request_id = "req_slow"
        self._send(200, {"ok": True})

    def stream(self, query):
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("X-Request-ID", self.request_id)
        self.end_headers()
        for i in range(3):
            self.wfile.write(f"event: tick\ndata: {json.dumps({'n': i})}\n\n".encode())
            self.wfile.flush()
            time.sleep(0.25)

if __name__ == "__main__":
    seed()
    server = ThreadingHTTPServer(("127.0.0.1", PORT), Handler)
    print(f"Mock backend on http://localhost:{PORT}{PREFIX}  (login: ada@example.com / correct-horse-battery, access token lifetime {ACCESS_TTL}s)", flush=True)
    server.serve_forever()
