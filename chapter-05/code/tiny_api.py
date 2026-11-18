# tiny_api.py - a minimal JSON API using only the standard library
import json
from http.server import BaseHTTPRequestHandler, HTTPServer

# Set this to your frontend origin (for example "http://localhost:5500") to enable CORS.
ALLOWED_ORIGIN = None

TASKS = [{"id": 1, "title": "Learn HTTP", "done": False}]

class Handler(BaseHTTPRequestHandler):
    # ---------- helpers ----------
    def _cors_headers(self) -> None:
        if ALLOWED_ORIGIN:
            self.send_header("Access-Control-Allow-Origin", ALLOWED_ORIGIN)
            self.send_header("Access-Control-Allow-Methods", "GET, POST, DELETE, OPTIONS")
            self.send_header("Access-Control-Allow-Headers", "Content-Type")

    def _send_json(self, status: int, payload) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self._cors_headers()
        self.end_headers()
        self.wfile.write(body)

    def _task_id(self):
        """Return the id from /tasks/<id> or None if the path has no valid id."""
        parts = self.path.strip("/").split("/")
        if len(parts) == 2 and parts[0] == "tasks" and parts[1].isdigit():
            return int(parts[1])
        return None

    # ---------- HTTP methods ----------
    def do_OPTIONS(self) -> None:             # CORS preflight
        self.send_response(204)
        self._cors_headers()
        self.end_headers()

    def do_GET(self) -> None:
        if self.path == "/tasks":
            self._send_json(200, TASKS)
            return
        task_id = self._task_id()
        if task_id is not None:
            for task in TASKS:
                if task["id"] == task_id:
                    self._send_json(200, task)
                    return
            self._send_json(404, {"detail": "Not found."})
            return
        self._send_json(404, {"detail": "Unknown path."})

    def do_POST(self) -> None:
        if self.path != "/tasks":
            self._send_json(404, {"detail": "Unknown path."})
            return
        length = int(self.headers.get("Content-Length", 0))
        try:
            data = json.loads(self.rfile.read(length) or b"{}")
        except json.JSONDecodeError:
            self._send_json(400, {"detail": "Body must be valid JSON."})
            return
        title = str(data.get("title", "")).strip()
        if not title:
            self._send_json(400, {"title": ["This field is required."]})
            return
        new_id = max((t["id"] for t in TASKS), default=0) + 1
        task = {"id": new_id, "title": title, "done": False}
        TASKS.append(task)
        self._send_json(201, task)

    def do_DELETE(self) -> None:
        task_id = self._task_id()
        for task in TASKS:
            if task["id"] == task_id:
                TASKS.remove(task)
                self.send_response(204)           # success, no body
                self._cors_headers()
                self.end_headers()
                return
        self._send_json(404, {"detail": "Not found."})

if __name__ == "__main__":
    server = HTTPServer(("localhost", 8000), Handler)
    print("API running on http://localhost:8000  (Ctrl+C to stop)")
    server.serve_forever()
# ----- next listing from the chapter -----
ALLOWED_ORIGIN = "http://localhost:5500"
