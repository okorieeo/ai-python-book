"""Check the EFFECTIVE SSH server settings, i.e. the output of `sudo sshd -T`.

Why not read /etc/ssh/sshd_config? Because files in /etc/ssh/sshd_config.d/ (for example the
one cloud-init writes) are read first and the first value wins. Only `sshd -T` shows what the
server will really do.
"""
from .findings import Finding, PASS, WARN, FAIL


def parse_sshd_t(text: str) -> dict:
    """Turn `sshd -T` output into {key: [values]}. Keys are lower-case; repeated keys keep every value."""
    settings: dict = {}
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        key, _, value = line.partition(" ")
        settings.setdefault(key.lower(), []).append(value.strip())
    return settings


def _one(settings: dict, key: str) -> str:
    values = settings.get(key)
    return values[0].lower() if values else ""


def check_sshd(settings: dict) -> list:
    findings = []

    def want(key: str, expected: str, why: str, level: str = FAIL):
        actual = _one(settings, key)
        if actual == expected:
            findings.append(Finding(f"ssh {key}", PASS, actual))
        elif not actual:
            findings.append(Finding(f"ssh {key}", WARN, "not reported by sshd -T (was the output complete?)"))
        else:
            findings.append(Finding(f"ssh {key}", level, f"is '{actual}', want '{expected}': {why}"))

    want("passwordauthentication", "no", "anyone can guess passwords")
    want("kbdinteractiveauthentication", "no", "keyboard-interactive can bring passwords back")
    want("pubkeyauthentication", "yes", "key login must stay enabled")
    want("permitemptypasswords", "no", "empty passwords must never work")

    root = _one(settings, "permitrootlogin")
    if root == "no":
        findings.append(Finding("ssh permitrootlogin", PASS, "no"))
    elif root == "prohibit-password":
        findings.append(Finding("ssh permitrootlogin", WARN, "root may log in with a key; 'no' is stricter"))
    elif not root:
        findings.append(Finding("ssh permitrootlogin", WARN, "not reported by sshd -T"))
    else:
        findings.append(Finding("ssh permitrootlogin", FAIL, f"is '{root}', root must not log in with a password"))

    tries = _one(settings, "maxauthtries")
    if tries.isdigit() and int(tries) <= 4:
        findings.append(Finding("ssh maxauthtries", PASS, tries))
    elif tries.isdigit():
        findings.append(Finding("ssh maxauthtries", WARN, f"{tries} attempts per connection; 3 or 4 is plenty"))
    return findings
