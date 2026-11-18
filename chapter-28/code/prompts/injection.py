"""Prompt injection defences that are NOT the model's job: scanning, canaries, output checks."""
import re
import secrets
from dataclasses import dataclass
from urllib.parse import urlparse

# Weak signals. Attackers rephrase, so use these to log and alert, never as the only defence.
_PATTERNS = [
    ("override", re.compile(r"\b(ignore|disregard|forget|override)\b.{0,40}\b(previous|prior|above|earlier|all|your)\b.{0,30}\b(instructions?|rules?|prompts?|guidelines?)\b", re.I | re.S)),
    ("role_swap", re.compile(r"\b(you are now|from now on you are|act as|pretend (to be|you are))\b", re.I)),
    ("prompt_leak", re.compile(r"\b(reveal|show|print|repeat|output)\b.{0,40}\b(system prompt|your instructions|hidden instructions|initial prompt)\b", re.I | re.S)),
    ("fake_role_marker", re.compile(r"(^|\n)\s*(system|assistant)\s*:|<\|im_start\|>|\[/?INST\]|<\s*/?system\s*>", re.I)),
    ("exfiltration", re.compile(r"\b(send|email|post|upload|forward)\b.{0,60}\b(to|at)\b.{0,40}(https?://|@)", re.I | re.S)),
]


@dataclass(frozen=True)
class Finding:
    kind: str
    excerpt: str


def scan_for_injection(text: str) -> list:
    """Return the suspicious patterns found in text (possibly none)."""
    findings = []
    for kind, pattern in _PATTERNS:
        match = pattern.search(text)
        if match:
            findings.append(Finding(kind, match.group(0).strip()[:80]))
    return findings


def risk_level(findings: list) -> str:
    """'none', 'low' or 'high'. Use it to decide on logging, alerts or a human check."""
    if not findings:
        return "none"
    return "high" if len(findings) >= 2 or findings[0].kind in {"exfiltration", "prompt_leak"} else "low"


# ---- canary tokens: detect that hidden instructions leaked ----------------------------------

def make_canary() -> str:
    """A random marker. Put it in the system prompt and tell the model never to print it."""
    return "CANARY-" + secrets.token_hex(6)


# ---- output checks: treat what the model wrote as untrusted too -----------------------------

_URL = re.compile(r"https?://[^\s)\]>\"']+", re.I)
_MD_IMAGE = re.compile(r"!\[[^\]]*\]\((https?://[^)\s]+)[^)]*\)", re.I)


def check_output(text: str, *, canary: str = "", allowed_hosts=frozenset()) -> list:
    """Return problems found in a model reply before it reaches the user or another system."""
    problems = []
    if canary and canary in text:
        problems.append("canary token leaked: the system prompt was exposed")
    image_hosts = set()
    for url in _MD_IMAGE.findall(text):
        host = (urlparse(url).hostname or "").lower()
        if host not in allowed_hosts:
            image_hosts.add(host)
            problems.append(f"markdown image from non-allowed host {host or '?'} (can leak data in the URL)")
    for url in _URL.findall(text):
        host = (urlparse(url).hostname or "").lower()
        if host not in allowed_hosts and host not in image_hosts:
            problems.append(f"link to non-allowed host {host or '?'}")
    return problems
