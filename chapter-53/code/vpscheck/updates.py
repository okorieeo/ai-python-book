"""Check automatic security updates (the contents of /etc/apt/apt.conf.d/20auto-upgrades)."""
import re

from .findings import Finding, PASS, WARN, FAIL


def parse_apt_periodic(text: str) -> dict:
    values = {}
    for m in re.finditer(r'^\s*APT::Periodic::([\w-]+)\s+"([^"]*)"\s*;', text, re.M):
        values[m.group(1)] = m.group(2)
    return values


def check_updates(periodic: dict, reboot_required: bool) -> list:
    findings = []
    if periodic.get("Unattended-Upgrade", "0") not in ("0", "") and periodic.get("Update-Package-Lists", "0") not in ("0", ""):
        findings.append(Finding("automatic updates", PASS, "package lists and unattended upgrades are on"))
    else:
        findings.append(Finding("automatic updates", FAIL, "turn on APT::Periodic::Update-Package-Lists and Unattended-Upgrade"))
    if reboot_required:
        findings.append(Finding("reboot", WARN, "/var/run/reboot-required exists: schedule a reboot (a new kernel or library is waiting)"))
    else:
        findings.append(Finding("reboot", PASS, "no reboot pending"))
    return findings
