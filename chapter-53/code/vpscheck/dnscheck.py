"""Check that names point at your server.

Uses the system resolver, which may answer from a cache. For the authoritative answer from a public
resolver use:  dig +short A app.example.com @1.1.1.1
"""
import socket

from .findings import Finding, PASS, WARN, FAIL


def resolve(host: str, family=socket.AF_INET) -> set:
    try:
        infos = socket.getaddrinfo(host, None, family, socket.SOCK_STREAM)
    except socket.gaierror:
        return set()
    return {info[4][0] for info in infos}


def check_dns(hosts, expected_ip: str, resolver=resolve) -> list:
    findings = []
    for host in hosts:
        found = resolver(host)
        if not found:
            findings.append(Finding(f"dns {host}", FAIL, "does not resolve yet (missing record, typo, or still propagating)"))
        elif found == {expected_ip}:
            findings.append(Finding(f"dns {host}", PASS, expected_ip))
        elif expected_ip in found:
            findings.append(Finding(f"dns {host}", WARN, f"points at {sorted(found)}; remove the records you do not control"))
        else:
            findings.append(Finding(f"dns {host}", FAIL, f"points at {sorted(found)}, expected {expected_ip}"))
    return findings
