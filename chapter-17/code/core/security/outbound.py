"""Guard for server-side requests to URLs a user, document or model supplied (SSRF)."""
import ipaddress
import socket
from urllib.parse import urlsplit


class UnsafeURL(ValueError):
    """The URL points somewhere our server must not connect to."""


def validate_outbound_url(
    url: str, *, allowed_schemes=("https",), resolver=socket.getaddrinfo
) -> str:
    """Return the URL if it is safe to fetch from our servers; else raise UnsafeURL.

    Resolves the host name and refuses anything that is not a public internet
    address: private networks (10.x, 192.168.x), loopback (127.x), link-local
    (169.254.x, the cloud metadata service) and so on.
    """
    parts = urlsplit(url)
    if parts.scheme not in allowed_schemes:
        raise UnsafeURL(f"Only {', '.join(allowed_schemes)} URLs are allowed.")
    if not parts.hostname:
        raise UnsafeURL("The URL has no host name.")
    if parts.username or parts.password:
        raise UnsafeURL("URLs with embedded credentials are not allowed.")
    port = parts.port or (443 if parts.scheme == "https" else 80)
    try:
        infos = resolver(parts.hostname, port, type=socket.SOCK_STREAM)
    except socket.gaierror as exc:
        raise UnsafeURL("The host name could not be resolved.") from exc
    for info in infos:
        address = ipaddress.ip_address(info[4][0].split("%")[0])
        if isinstance(address, ipaddress.IPv6Address) and address.ipv4_mapped:
            address = address.ipv4_mapped  # ::ffff:127.0.0.1 is really 127.0.0.1
        if not address.is_global:
            raise UnsafeURL("The URL resolves to a non-public address.")
    return url
