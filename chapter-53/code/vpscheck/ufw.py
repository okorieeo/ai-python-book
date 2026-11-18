"""Check `sudo ufw status verbose`."""
import re
from dataclasses import dataclass, field

from .findings import Finding, PASS, WARN, FAIL

# Services that must never be reachable from the internet.
DANGEROUS_PORTS = {3306: "MySQL", 5432: "PostgreSQL", 6379: "Redis", 27017: "MongoDB", 9200: "Elasticsearch"}


@dataclass
class UfwStatus:
    active: bool = False
    default_incoming: str = ""
    default_outgoing: str = ""
    allowed_ports: set = field(default_factory=set)


def parse_ufw_status(text: str) -> UfwStatus:
    status = UfwStatus()
    if re.search(r"^Status:\s+active", text, re.M):
        status.active = True
    m = re.search(r"^Default:\s+(\w+)\s+\(incoming\),\s+(\w+)\s+\(outgoing\)", text, re.M)
    if m:
        status.default_incoming, status.default_outgoing = m.group(1), m.group(2)
    in_rules = False
    for line in text.splitlines():
        if line.startswith("--"):
            in_rules = True
            continue
        if not in_rules or not line.strip():
            continue
        columns = re.split(r"\s{2,}", line.strip())
        if len(columns) < 2:
            continue
        target, action = columns[0], columns[1]
        if not re.match(r"(ALLOW|LIMIT)", action):
            continue
        port = re.match(r"^(\d+)(?:/(?:tcp|udp))?(?:\s+\(v6\))?$", target)
        if port:
            status.allowed_ports.add(int(port.group(1)))
        elif target.lower().startswith(("openssh", "ssh")):
            status.allowed_ports.add(22)
    return status


def check_ufw(status: UfwStatus, expected=frozenset({22, 80, 443}), temporary=frozenset({3000})) -> list:
    findings = []
    if not status.active:
        return [Finding("ufw active", FAIL, "the firewall is not enabled: run 'sudo ufw enable' (allow SSH first!)")]
    findings.append(Finding("ufw active", PASS, "enabled"))

    if status.default_incoming == "deny":
        findings.append(Finding("ufw default incoming", PASS, "deny"))
    else:
        findings.append(Finding("ufw default incoming", FAIL, f"is '{status.default_incoming}', want 'deny'"))

    if 22 in status.allowed_ports:
        findings.append(Finding("ufw ssh rule", PASS, "port 22 is allowed"))
    else:
        findings.append(Finding("ufw ssh rule", WARN, "no rule for port 22: fine only if you moved SSH to another port"))

    for port in sorted(status.allowed_ports):
        if port in DANGEROUS_PORTS:
            findings.append(Finding(f"ufw port {port}", FAIL, f"{DANGEROUS_PORTS[port]} is open to the internet"))
        elif port in temporary:
            findings.append(Finding(f"ufw port {port}", WARN, "Dokploy panel port: close it once the panel has a domain with HTTPS (Chapter 54)"))
        elif port not in expected:
            findings.append(Finding(f"ufw port {port}", WARN, "not in the expected list (22, 80, 443): is it needed?"))
    return findings
