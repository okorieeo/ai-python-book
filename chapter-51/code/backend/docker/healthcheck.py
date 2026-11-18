"""Container health check: exit 0 if the app answers 200, else exit 1.

The slim image has no curl, so we use Python. Settings (all optional):
  PORT              port the app listens on          (default 8000)
  HEALTHCHECK_PATH  URL path to request              (default /healthz/)
  HEALTHCHECK_HOST  Host header to send              (default localhost)

Django rejects unknown Host headers, so HEALTHCHECK_HOST (default "localhost") must be
in DJANGO_ALLOWED_HOSTS. We also send X-Forwarded-Proto: https so an HTTPS-redirect
setting does not answer our plain-HTTP probe with a 301. Redirects are NOT followed:
a 301 means "not healthy", and the message says so.
"""
import os
import sys
import urllib.error
import urllib.request


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


def check(url: str, host: str = "localhost", timeout: float = 3.0) -> tuple[bool, str]:
    request = urllib.request.Request(
        url, headers={"Host": host, "X-Forwarded-Proto": "https"}
    )
    opener = urllib.request.build_opener(_NoRedirect)
    try:
        with opener.open(request, timeout=timeout) as response:
            if response.status == 200:
                return True, "healthy"
            return False, f"unexpected status {response.status}"
    except urllib.error.HTTPError as exc:  # 3xx (not followed), 4xx and 5xx land here
        return False, f"HTTP {exc.code}"
    except (urllib.error.URLError, OSError) as exc:
        return False, f"cannot connect: {exc}"


def main() -> int:
    port = os.environ.get("PORT", "8000")
    path = os.environ.get("HEALTHCHECK_PATH", "/healthz/")
    host = os.environ.get("HEALTHCHECK_HOST", "localhost")
    ok, message = check(f"http://127.0.0.1:{port}{path}", host=host)
    print(message)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
