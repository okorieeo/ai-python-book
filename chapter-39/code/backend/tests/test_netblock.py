import socket

import pytest

from testsupport.netblock import NetworkBlocked, block_network


def test_the_autouse_fixture_blocks_the_real_internet():
    with pytest.raises(NetworkBlocked, match="api.stripe.com"):
        socket.create_connection(("api.stripe.com", 443), timeout=1)


def test_name_lookups_are_blocked_too():
    with pytest.raises(NetworkBlocked, match="api.anthropic.com"):
        socket.getaddrinfo("api.anthropic.com", 443)


def test_loopback_stays_open_so_tests_can_talk_to_their_own_server():
    server = socket.socket()
    server.bind(("127.0.0.1", 0))
    server.listen(1)
    client = socket.create_connection(server.getsockname(), timeout=1)
    client.close()
    server.close()


def test_the_patch_is_removed_when_the_block_ends():
    inside = socket.socket.connect
    with block_network():
        pass
    assert socket.socket.connect is inside               # nested block restored exactly what it found


def test_an_explicit_allow_list_can_open_one_host():
    with block_network(allowed={"127.0.0.1", "sandbox.example"}):
        with pytest.raises(NetworkBlocked, match="live.example"):
            socket.create_connection(("live.example", 80), timeout=1)
