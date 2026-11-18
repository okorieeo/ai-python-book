"""
Make any attempt to reach the real internet fail loudly during tests. A test that quietly calls Stripe or
Anthropic is slow, flaky, costs money and can charge a card. Loopback stays open so a test can talk to a
server it started itself.
"""
from __future__ import annotations

import contextlib
import socket

ALLOWED = {"127.0.0.1", "::1", "localhost"}


class NetworkBlocked(RuntimeError):
    pass


def _host_of(address) -> str:
    return address[0] if isinstance(address, tuple) else str(address)


@contextlib.contextmanager
def block_network(allowed: set[str] | frozenset[str] = frozenset(ALLOWED)):
    real_connect, real_create, real_getaddrinfo = socket.socket.connect, socket.create_connection, socket.getaddrinfo

    def guarded_connect(self, address):
        host = _host_of(address)
        if host not in allowed:
            raise NetworkBlocked(f"test tried to connect to {host}; use a fake instead")
        return real_connect(self, address)

    def guarded_create(address, *a, **k):
        host = _host_of(address)
        if host not in allowed:
            raise NetworkBlocked(f"test tried to connect to {host}; use a fake instead")
        return real_create(address, *a, **k)

    def guarded_getaddrinfo(host, *a, **k):
        if host not in allowed and not str(host).replace(".", "").isdigit():
            raise NetworkBlocked(f"test tried to resolve {host}; use a fake instead")
        return real_getaddrinfo(host, *a, **k)

    socket.socket.connect, socket.create_connection, socket.getaddrinfo = guarded_connect, guarded_create, guarded_getaddrinfo
    try:
        yield
    finally:
        socket.socket.connect, socket.create_connection, socket.getaddrinfo = real_connect, real_create, real_getaddrinfo
