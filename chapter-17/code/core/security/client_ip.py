"""Find the real client IP address when the app sits behind one or more proxies."""
import ipaddress


def _valid(value: str) -> str | None:
    try:
        return str(ipaddress.ip_address(value.strip()))
    except ValueError:
        return None


def get_client_ip(meta: dict, *, trusted_proxies: int = 0) -> str | None:
    """Return the client's IP address from request.META, or None if unknown.

    X-Forwarded-For looks like "client, proxy1, proxy2". Every proxy APPENDS the
    address it received the connection from, so the entries on the right were
    written by our own infrastructure, while the entries on the left can be forged
    by the client. With N trusted proxies the real client is the Nth entry counted
    from the right. With 0 trusted proxies the header is ignored completely.
    """
    remote = meta.get("REMOTE_ADDR", "")
    forwarded = meta.get("HTTP_X_FORWARDED_FOR", "")
    if trusted_proxies <= 0 or not forwarded:
        return _valid(remote)
    hops = [part.strip() for part in forwarded.split(",") if part.strip()]
    if len(hops) < trusted_proxies:
        # fewer hops than expected: the request did not come through our proxies
        return _valid(remote)
    return _valid(hops[-trusted_proxies])
