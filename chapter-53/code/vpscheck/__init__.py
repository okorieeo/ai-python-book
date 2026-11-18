"""vpscheck: small, dependency-free checks for a freshly prepared Ubuntu VPS (Chapter 53)."""
from .findings import Finding, PASS, WARN, FAIL, worst_status

__all__ = ["Finding", "PASS", "WARN", "FAIL", "worst_status"]
