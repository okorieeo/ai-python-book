"""Device credentials. A device is a tiny computer in a field: it cannot type a password and it can be stolen.
So each device gets its own long random key, we store only a hash, and a stolen key is revoked for that one device."""
import hashlib
import hmac
import secrets
from typing import Callable, Optional, Tuple

PREFIX = "fsk"


def generate_device_key() -> Tuple[str, str, str]:
    """Returns (key_id, secret_hash, full_key). The full key is shown ONCE; store key_id and secret_hash."""
    key_id = secrets.token_hex(6)
    secret = secrets.token_urlsafe(32)
    return key_id, hash_secret(secret), f"{PREFIX}_{key_id}_{secret}"


def hash_secret(secret: str) -> str:
    # The secret is 256 bits of randomness, so a fast hash is fine (unlike a human password, it cannot be guessed).
    return hashlib.sha256(secret.encode()).hexdigest()


def split_key(presented: str) -> Optional[Tuple[str, str]]:
    parts = (presented or "").split("_", 2)
    if len(parts) != 3 or parts[0] != PREFIX or not parts[1] or not parts[2]:
        return None
    return parts[1], parts[2]


def verify_device_key(presented: str, lookup_hash: Callable[[str], Optional[str]]) -> Optional[str]:
    """Returns the key_id if the key is valid, else None. Always does the same work, valid key or not (constant time compare)."""
    parts = split_key(presented)
    key_id, secret = parts if parts else ("", "")
    stored = lookup_hash(key_id)                                    # one database lookup
    reference = stored or hash_secret("x" * 43)                     # compare against a dummy when the id is unknown
    ok = hmac.compare_digest(reference, hash_secret(secret))
    return key_id if (ok and parts and stored) else None


def sign_body(shared_secret: str, timestamp: int, body: bytes) -> str:
    """Optional extra layer for devices on networks you do not control: an HMAC over the time and the body.
    The server needs the raw shared secret for this (so it must be stored encrypted), which is why it is optional."""
    return hmac.new(shared_secret.encode(), f"{timestamp}.".encode() + body, hashlib.sha256).hexdigest()


def verify_signature(shared_secret: str, timestamp: int, body: bytes, signature: str, now: int, tolerance: int = 300) -> bool:
    if abs(now - timestamp) > tolerance:
        return False                                                # a captured request cannot be replayed later
    return hmac.compare_digest(sign_body(shared_secret, timestamp, body), signature)
