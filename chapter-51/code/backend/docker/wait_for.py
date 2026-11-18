"""Wait until TCP services accept connections: python wait_for.py db:5432 redis:6379

Uses only the standard library, so it runs in the slim image. This is a convenience
for start-up order. It does not prove the service is READY (a database can accept a
connection before it accepts queries); health checks (Chapter 52) cover that.
"""
import argparse
import socket
import sys
import time


def parse_target(text: str) -> tuple[str, int]:
    host, sep, port = text.rpartition(":")
    if not sep or not host or not port.isdigit():
        raise ValueError(f"Expected host:port, got {text!r}")
    return host, int(port)


def can_connect(host: str, port: int, timeout: float = 1.0) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def wait_for(targets, timeout: float = 60.0, interval: float = 1.0, out=sys.stdout) -> bool:
    """Return True when every target accepts a connection, False on timeout."""
    deadline = time.monotonic() + timeout
    for host, port in targets:
        while not can_connect(host, port):
            if time.monotonic() >= deadline:
                print(f"Gave up waiting for {host}:{port}", file=out)
                return False
            print(f"Waiting for {host}:{port} ...", file=out)
            time.sleep(interval)
        print(f"{host}:{port} is accepting connections", file=out)
    return True


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("targets", nargs="+", help="host:port")
    parser.add_argument("--timeout", type=float, default=60.0)
    parser.add_argument("--interval", type=float, default=1.0)
    args = parser.parse_args(argv)
    try:
        targets = [parse_target(t) for t in args.targets]
    except ValueError as exc:
        parser.error(str(exc))
    return 0 if wait_for(targets, args.timeout, args.interval) else 1


if __name__ == "__main__":
    sys.exit(main())
