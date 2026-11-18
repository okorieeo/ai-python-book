"""Check a live TLS certificate: who issued it, when it ends, and whether renewal looks healthy.

Let's Encrypt stopped sending expiry reminder emails in 2025, so you must watch certificates yourself.
"""
import socket
import ssl
import time
from dataclasses import dataclass

from .findings import Finding, PASS, WARN, FAIL


@dataclass(frozen=True)
class CertInfo:
    host: str
    issuer: str
    not_before: float
    not_after: float
    names: tuple

    @property
    def lifetime_days(self) -> float:
        return (self.not_after - self.not_before) / 86400

    def days_left(self, now=None) -> float:
        return (self.not_after - (time.time() if now is None else now)) / 86400


def _org(rdns) -> str:
    flat = {k: v for rdn in rdns for k, v in rdn}
    return flat.get("organizationName") or flat.get("commonName") or "?"


def fetch_cert(host: str, port: int = 443, timeout: float = 5.0, cafile=None) -> CertInfo:
    context = ssl.create_default_context(cafile=cafile)
    with socket.create_connection((host, port), timeout=timeout) as sock:
        with context.wrap_socket(sock, server_hostname=host) as tls:
            cert = tls.getpeercert()
    names = tuple(v for k, v in cert.get("subjectAltName", ()) if k == "DNS")
    return CertInfo(host, _org(cert["issuer"]), ssl.cert_time_to_seconds(cert["notBefore"]),
                    ssl.cert_time_to_seconds(cert["notAfter"]), names)


def evaluate(info: CertInfo, now=None) -> Finding:
    """Healthy renewal happens with about a third of the lifetime left, so under a quarter left means
    renewal has been failing for a while. Under 7 days left is an emergency."""
    left = info.days_left(now)
    quarter = info.lifetime_days / 4
    if left < 0:
        return Finding(f"cert {info.host}", FAIL, f"EXPIRED {abs(left):.0f} days ago")
    if left < 7:
        return Finding(f"cert {info.host}", FAIL, f"expires in {left:.1f} days: renew now")
    if left < quarter:
        return Finding(f"cert {info.host}", WARN, f"{left:.0f} days left of a {info.lifetime_days:.0f}-day certificate: renewal looks stuck")
    return Finding(f"cert {info.host}", PASS, f"{left:.0f} days left (issuer: {info.issuer})")


def check_cert(host: str, port: int = 443, cafile=None) -> Finding:
    try:
        return evaluate(fetch_cert(host, port, cafile=cafile))
    except ssl.SSLCertVerificationError as exc:
        return Finding(f"cert {host}", FAIL, f"certificate not trusted: {exc.verify_message}")
    except (OSError, ssl.SSLError) as exc:
        return Finding(f"cert {host}", FAIL, f"cannot connect on port {port}: {exc}")
