"""Explain where the time went in one HTTP request, from `curl -w` timing values."""
from __future__ import annotations

from dataclasses import dataclass

CURL_FORMAT = ("dns=%{time_namelookup} connect=%{time_connect} tls=%{time_appconnect} "
               "ttfb=%{time_starttransfer} total=%{time_total} code=%{http_code} size=%{size_download}\\n")


@dataclass(frozen=True)
class Timing:
    dns: float
    connect: float       # cumulative, as curl reports it
    tls: float
    ttfb: float
    total: float
    code: int
    size: int

    @classmethod
    def parse(cls, line: str) -> "Timing":
        kv = dict(part.split("=", 1) for part in line.split())
        return cls(float(kv["dns"]), float(kv["connect"]), float(kv["tls"]), float(kv["ttfb"]),
                   float(kv["total"]), int(kv["code"]), int(float(kv["size"])))

    def phases(self) -> dict[str, float]:
        """curl reports cumulative times; subtract to get the time spent IN each phase (seconds)."""
        tls_start = max(self.connect, 0.0)
        return {
            "dns": self.dns,
            "tcp_connect": max(self.connect - self.dns, 0.0),
            "tls_handshake": max(self.tls - self.connect, 0.0) if self.tls else 0.0,
            "server_wait": max(self.ttfb - (self.tls or tls_start), 0.0),
            "download": max(self.total - self.ttfb, 0.0),
        }


def diagnose(t: Timing, *, slow: float = 1.0) -> list[str]:
    p = t.phases()
    notes = []
    if t.code == 0:
        notes.append("no HTTP response: DNS, connection or TLS failed before the server answered")
    if p["dns"] > 0.2:
        notes.append(f"DNS took {p['dns']:.2f}s: resolver or record problem")
    if p["tcp_connect"] > 0.5:
        notes.append(f"TCP connect took {p['tcp_connect']:.2f}s: firewall, wrong region or overloaded host")
    if p["tls_handshake"] > 0.5:
        notes.append(f"TLS handshake took {p['tls_handshake']:.2f}s: certificate chain or CPU-starved proxy")
    if p["server_wait"] > slow:
        notes.append(f"server_wait {p['server_wait']:.2f}s: the app or database is slow, not the network (look at logs and queries)")
    if p["download"] > slow and t.size > 0:
        notes.append(f"download took {p['download']:.2f}s for {t.size:,} bytes: payload too large or slow link; try compression or pagination")
    if t.code >= 500:
        notes.append(f"HTTP {t.code}: a server error; find the request id in the logs")
    elif t.code in (401, 403):
        notes.append(f"HTTP {t.code}: authentication or permission, not a network problem")
    return notes or ["no obvious problem in the timings"]
