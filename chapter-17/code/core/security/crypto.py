"""Encryption, token and signature helpers. Well-tested libraries only."""
import hashlib
import hmac
import secrets

from cryptography.fernet import Fernet, InvalidToken, MultiFernet


class DecryptionError(Exception):
    """The data could not be decrypted: wrong key, or the stored value was changed."""


class SecretBox:
    """Encrypts short strings (such as a user's own provider API key) before storage.

    Fernet is authenticated encryption (AES plus an HMAC), so tampering is detected.
    The FIRST key encrypts; ALL keys can decrypt. That makes key rotation possible:
    put the new key first, re-encrypt with rotate(), then retire the old key.
    """

    def __init__(self, keys: list[str]):
        if not keys:
            raise ValueError("At least one encryption key is required.")
        self._fernet = MultiFernet([Fernet(key) for key in keys])

    def encrypt(self, plaintext: str) -> str:
        return self._fernet.encrypt(plaintext.encode()).decode()

    def decrypt(self, token: str) -> str:
        try:
            return self._fernet.decrypt(token.encode()).decode()
        except InvalidToken as exc:
            raise DecryptionError("Could not decrypt: wrong key or bad data.") from exc

    def rotate(self, token: str) -> str:
        """Re-encrypt a stored value with the newest key."""
        try:
            return self._fernet.rotate(token.encode()).decode()
        except InvalidToken as exc:
            raise DecryptionError("Could not rotate: wrong key or bad data.") from exc


def new_api_token(prefix: str = "aca") -> tuple[str, str]:
    """Create an API token. Returns (token_to_show_once, sha256_to_store).

    The token is long and random, so a fast hash is enough (unlike passwords, which
    need slow hashes). Store only the hash: a database leak then reveals no usable
    tokens.
    """
    token = f"{prefix}_{secrets.token_urlsafe(32)}"
    return token, hash_api_token(token)


def hash_api_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def verify_hmac(
    secret: bytes, body: bytes, signature: str, *, algorithm: str = "sha256"
) -> bool:
    """Check a webhook signature: HMAC of the RAW body, compared in constant time."""
    expected = hmac.new(secret, body, getattr(hashlib, algorithm)).hexdigest()
    return hmac.compare_digest(expected, signature.strip().lower())
