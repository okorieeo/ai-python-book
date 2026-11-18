import hashlib
import hmac
import time


def sign(secret: str, body: bytes, timestamp: int | None = None) -> str:
    """Build the header value: t=<unix time>,v1=<HMAC of 'time.body'>."""
    timestamp = int(time.time()) if timestamp is None else timestamp
    message = f"{timestamp}.".encode() + body
    digest = hmac.new(secret.encode(), message, hashlib.sha256).hexdigest()
    return f"t={timestamp},v1={digest}"


def verify(secret: str, body: bytes, header: str, tolerance: int) -> bool:
    """True only for a correct signature on a recent message."""
    try:
        parts = dict(item.split("=", 1) for item in header.split(","))
        timestamp = int(parts["t"])
        given = parts["v1"]
    except (KeyError, ValueError):
        return False
    if (
        abs(time.time() - timestamp) > tolerance
    ):  # stops replays of old requests
        return False
    expected = sign(secret, body, timestamp).split("v1=")[1]
    return hmac.compare_digest(expected, given)  # constant-time comparison
