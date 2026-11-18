"""
Mobile version gate: the server side of "please update" and "down for maintenance".

Pure Python (no Django imports) so it is easy to test. The view in views.py is a
thin wrapper. The policy comes from environment variables, so you can raise the
minimum version without a code change (a redeploy of the same image is enough).
"""
from __future__ import annotations

import re
from dataclasses import dataclass

PLATFORMS = ("ios", "android")  # allow-list: anything else is a 400
_VERSION_RE = re.compile(r"^(\d{1,6})\.(\d{1,6})\.(\d{1,6})$")


class PolicyError(ValueError):
    """The configured policy is not usable (bad version text, minimum > recommended)."""


def parse_version(text: str) -> tuple[int, int, int]:
    match = _VERSION_RE.match((text or "").strip())
    if not match:
        raise PolicyError(f"Not a valid x.y.z version: {text!r}")
    return int(match[1]), int(match[2]), int(match[3])


@dataclass(frozen=True)
class GatePolicy:
    min_version: str = "1.0.0"
    recommended_version: str = "1.0.0"
    maintenance: bool = False
    message: str = ""
    store_url_ios: str = ""
    store_url_android: str = ""

    def validate(self) -> "GatePolicy":
        low = parse_version(self.min_version)
        high = parse_version(self.recommended_version)
        if low > high:
            raise PolicyError("min_version is higher than recommended_version")
        return self


def build_response(policy: GatePolicy, platform: str) -> dict:
    """The JSON body for GET /api/v1/app-config/?platform=ios|android."""
    if platform not in PLATFORMS:
        raise ValueError(f"platform must be one of {PLATFORMS}")
    policy.validate()
    return {
        "min_version": policy.min_version,
        "recommended_version": policy.recommended_version,
        "store_url": policy.store_url_ios if platform == "ios" else policy.store_url_android,
        "maintenance": bool(policy.maintenance),
        "message": policy.message[:300],  # a message is a sentence, not a document
    }


def _truthy(value: str | None) -> bool:
    return (value or "").strip().lower() in {"1", "true", "yes", "on"}


def policy_from_env(env: dict) -> GatePolicy:
    """Read MOBILE_* variables. Missing values mean 'no restriction'."""
    return GatePolicy(
        min_version=env.get("MOBILE_MIN_VERSION", "1.0.0"),
        recommended_version=env.get("MOBILE_RECOMMENDED_VERSION", env.get("MOBILE_MIN_VERSION", "1.0.0")),
        maintenance=_truthy(env.get("MOBILE_MAINTENANCE")),
        message=env.get("MOBILE_MESSAGE", ""),
        store_url_ios=env.get("MOBILE_STORE_URL_IOS", ""),
        store_url_android=env.get("MOBILE_STORE_URL_ANDROID", ""),
    )
