"""Check what is LISTENING, from `sudo ss -H -tulpn`.

Limits to remember: this shows host sockets, not Docker's firewall rules. Always confirm with a scan
from ANOTHER machine (the hands-on section shows how).
"""
import re
from dataclasses import dataclass

from .findings import Finding, PASS, WARN, FAIL
from .ufw import DANGEROUS_PORTS

_PUBLIC_ADDRS = {"0.0.0.0", "::", "[::]", "*"}


@dataclass(frozen=True)
class Listener:
    proto: str
    address: str
    port: int
    process: str

    @property
    def is_public(self) -> bool:
        return self.address in _PUBLIC_ADDRS


def parse_ss(text: str) -> list:
    listeners = []
    for line in text.splitlines():
        parts = line.split()
        if len(parts) < 5 or parts[0] not in ("tcp", "udp"):
            continue
        if parts[0] == "tcp" and parts[1] != "LISTEN":
            continue
        local = parts[4]
        address, _, port = local.rpartition(":")
        address = address.split("%")[0]  # 127.0.0.53%lo -> 127.0.0.53
        if not port.isdigit():
            continue
        proc = re.search(r'users:\(\("([^"]+)"', line)
        listeners.append(Listener(parts[0], address, int(port), proc.group(1) if proc else "?"))
    return listeners


def check_listeners(listeners, expected_public=frozenset({22, 80, 443, 3000})) -> list:
    findings = []
    public = sorted({(l.port, l.process) for l in listeners if l.is_public and l.proto == "tcp"})
    if not public:
        findings.append(Finding("listening ports", WARN, "no public TCP listener found (is this the right server, and did you use sudo?)"))
    for port, process in public:
        if port in DANGEROUS_PORTS:
            findings.append(Finding(f"listening {port}", FAIL, f"{DANGEROUS_PORTS[port]} ({process}) listens on a public address: bind it to 127.0.0.1 or keep it on a private Docker network"))
        elif port not in expected_public:
            findings.append(Finding(f"listening {port}", WARN, f"{process} listens on a public address and {port} is not in the expected list"))
        else:
            findings.append(Finding(f"listening {port}", PASS, f"{process}"))
    return findings
