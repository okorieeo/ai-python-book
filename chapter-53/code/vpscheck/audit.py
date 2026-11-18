"""Run the server checks.

On the server (needs sudo to read sshd settings, firewall rules and process names):
    sudo python3 -m vpscheck.audit
    sudo python3 -m vpscheck.audit --dns app.example.com api.example.com --ip 203.0.113.10
    python3 -m vpscheck.audit --certs app.example.com        # needs no sudo

On your laptop, against saved command output (used by the tests and the examples):
    python3 -m vpscheck.audit --fixtures tests/fixtures/good
"""
import argparse
import json
import os
import subprocess
import sys

from .certcheck import check_cert
from .dnscheck import check_dns
from .findings import FAIL, PASS, WARN, worst_status
from .ports import check_listeners, parse_ss
from .sshd import check_sshd, parse_sshd_t
from .ufw import check_ufw, parse_ufw_status
from .updates import check_updates, parse_apt_periodic

COMMANDS = {
    "sshd_T.txt": ["sshd", "-T"],
    "ufw_status.txt": ["ufw", "status", "verbose"],
    "ss.txt": ["ss", "-H", "-tulpn"],
}


def _run(cmd) -> str:
    try:
        return subprocess.run(cmd, capture_output=True, text=True, timeout=20, check=False).stdout
    except (OSError, subprocess.TimeoutExpired):
        return ""


def _read(path: str) -> str:
    try:
        with open(path, encoding="utf-8") as handle:
            return handle.read()
    except OSError:
        return ""


def collect(fixtures=None) -> dict:
    """Gather raw text for each check, from the live system or from a fixtures directory."""
    if fixtures:
        data = {name: _read(os.path.join(fixtures, name)) for name in COMMANDS}
        data["20auto-upgrades"] = _read(os.path.join(fixtures, "20auto-upgrades"))
        data["reboot_required"] = os.path.exists(os.path.join(fixtures, "reboot-required"))
        return data
    data = {name: _run(cmd) for name, cmd in COMMANDS.items()}
    data["20auto-upgrades"] = _read("/etc/apt/apt.conf.d/20auto-upgrades")
    data["reboot_required"] = os.path.exists("/var/run/reboot-required")
    return data


def run_checks(data: dict) -> list:
    findings = []
    findings += check_sshd(parse_sshd_t(data["sshd_T.txt"])) if data["sshd_T.txt"] else \
        [_missing("ssh settings", "sshd -T returned nothing: run with sudo")]
    findings += check_ufw(parse_ufw_status(data["ufw_status.txt"])) if data["ufw_status.txt"] else \
        [_missing("ufw", "ufw status returned nothing: run with sudo")]
    findings += check_listeners(parse_ss(data["ss.txt"])) if data["ss.txt"] else \
        [_missing("listening ports", "ss returned nothing: run with sudo")]
    findings += check_updates(parse_apt_periodic(data["20auto-upgrades"]), data["reboot_required"])
    return findings


def _missing(name, detail):
    from .findings import Finding
    return Finding(name, WARN, detail)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Audit a freshly prepared Ubuntu VPS.")
    parser.add_argument("--fixtures", help="read saved command output from this directory instead of the live system")
    parser.add_argument("--dns", nargs="*", default=[], metavar="HOST", help="hostnames that should point at --ip")
    parser.add_argument("--ip", help="the server's public IPv4 address (needed with --dns)")
    parser.add_argument("--certs", nargs="*", default=[], metavar="HOST", help="hostnames whose HTTPS certificate to check")
    parser.add_argument("--json", action="store_true", help="print JSON instead of text")
    args = parser.parse_args(argv)

    if args.dns and not args.ip:
        parser.error("--dns needs --ip")

    findings = run_checks(collect(args.fixtures))
    if args.dns:
        findings += check_dns(args.dns, args.ip)
    for host in args.certs:
        findings.append(check_cert(host))

    overall = worst_status(findings)
    if args.json:
        print(json.dumps({"overall": overall, "findings": [f.__dict__ for f in findings]}, indent=2))
    else:
        for finding in findings:
            print(finding.line())
        counts = {s: sum(f.status == s for f in findings) for s in (PASS, WARN, FAIL)}
        print(f"\n{counts[PASS]} passed, {counts[WARN]} warnings, {counts[FAIL]} failures")
    return 1 if overall == FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
