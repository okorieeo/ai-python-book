"""Daily reports: what happened on the farm yesterday, in the farm's own time zone, as text and as a PDF.

The two traps are time zones and daylight saving: "yesterday" for a farm is a local calendar day, which is not 24 hours long
twice a year, and the report must be correct, repeatable (same data, same report) and safe to run twice."""
import io
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta, timezone
from typing import Dict, List, Optional, Sequence, Tuple
from zoneinfo import ZoneInfo

Point = Tuple[datetime, float]


def local_day_bounds(day: date, tz_name: str) -> Tuple[datetime, datetime]:
    """The UTC start (inclusive) and end (exclusive) of a local calendar day. 23, 24 or 25 hours long."""
    tz = ZoneInfo(tz_name)
    start = datetime.combine(day, time.min, tzinfo=tz)
    end = datetime.combine(day + timedelta(days=1), time.min, tzinfo=tz)
    return start.astimezone(timezone.utc), end.astimezone(timezone.utc)


@dataclass(frozen=True)
class SensorMeta:
    key: str
    name: str
    unit: str
    interval_s: int
    high_limit: Optional[float] = None
    low_limit: Optional[float] = None


@dataclass
class SensorSummary:
    meta: SensorMeta
    count: int
    expected: int
    minimum: Optional[float]
    average: Optional[float]
    maximum: Optional[float]
    maximum_at: Optional[datetime]
    minutes_above_limit: int
    minutes_below_limit: int

    @property
    def uptime_pct(self) -> float:
        return round(min(100.0, 100.0 * self.count / self.expected), 1) if self.expected else 0.0


@dataclass
class DailyReport:
    farm: str
    day: date
    tz: str
    day_hours: float
    sensors: List[SensorSummary] = field(default_factory=list)
    alerts_by_severity: Dict[str, int] = field(default_factory=dict)


def build_daily_report(farm: str, day: date, tz_name: str, metas: Sequence[SensorMeta],
                       readings: Dict[str, Sequence[Point]], alerts: Sequence[dict] = ()) -> DailyReport:
    start, end = local_day_bounds(day, tz_name)
    hours = (end - start).total_seconds() / 3600
    report = DailyReport(farm, day, tz_name, hours)
    for meta in metas:
        pts = sorted((ts, v) for ts, v in readings.get(meta.key, []) if start <= ts < end)
        expected = int((end - start).total_seconds() // meta.interval_s)
        if pts:
            values = [v for _, v in pts]
            peak = max(pts, key=lambda p: p[1])
            above = sum(1 for _, v in pts if meta.high_limit is not None and v > meta.high_limit)
            below = sum(1 for _, v in pts if meta.low_limit is not None and v < meta.low_limit)
            per = meta.interval_s / 60.0
            s = SensorSummary(meta, len(pts), expected, min(values), sum(values) / len(values), peak[1],
                              peak[0].astimezone(ZoneInfo(tz_name)), round(above * per), round(below * per))
        else:
            s = SensorSummary(meta, 0, expected, None, None, None, None, 0, 0)
        report.sensors.append(s)
    for a in alerts:
        sev = a.get("severity", "warning")
        report.alerts_by_severity[sev] = report.alerts_by_severity.get(sev, 0) + 1
    return report


def render_text(r: DailyReport) -> str:
    lines = [f"{r.farm}: daily report for {r.day:%A %d %B %Y} ({r.tz}, a {r.day_hours:g}-hour day)", ""]
    for s in r.sensors:
        if s.count == 0:
            lines.append(f"- {s.meta.name}: NO DATA received (expected about {s.expected} readings).")
            continue
        line = (f"- {s.meta.name}: min {s.minimum:.1f}, avg {s.average:.1f}, max {s.maximum:.1f} {s.meta.unit} "
                f"(peak at {s.maximum_at:%H:%M}); data received {s.uptime_pct:g}%")
        if s.minutes_above_limit:
            line += f"; {s.minutes_above_limit} min above {s.meta.high_limit:g}"
        if s.minutes_below_limit:
            line += f"; {s.minutes_below_limit} min below {s.meta.low_limit:g}"
        lines.append(line + ".")
    total = sum(r.alerts_by_severity.values())
    lines += ["", "Alerts: " + (", ".join(f"{n} {sev}" for sev, n in sorted(r.alerts_by_severity.items())) if total else "none") + "."]
    return "\n".join(lines)


def render_pdf(r: DailyReport) -> bytes:
    """A simple, readable PDF (ReportLab). Layout is deliberately plain: it prints well and it can be tested."""
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, title=f"{r.farm} daily report {r.day}")
    styles = getSampleStyleSheet()
    story = [Paragraph(f"{r.farm}: daily report", styles["Title"]),
             Paragraph(f"{r.day:%A %d %B %Y} ({r.tz}, a {r.day_hours:g}-hour day)", styles["Normal"]), Spacer(1, 12)]
    rows = [["Sensor", "Min", "Avg", "Max", "Peak", "Data %", "Over limit"]]
    for s in r.sensors:
        if s.count == 0:
            rows.append([s.meta.name, "-", "-", "-", "-", "0", "NO DATA"])
        else:
            rows.append([s.meta.name, f"{s.minimum:.1f}", f"{s.average:.1f}", f"{s.maximum:.1f} {s.meta.unit}",
                         f"{s.maximum_at:%H:%M}", f"{s.uptime_pct:g}", f"{s.minutes_above_limit} min"])
    table = Table(rows, repeatRows=1)
    table.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1E3A8A")), ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                               ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#D1D5DB")), ("FONTSIZE", (0, 0), (-1, -1), 9)]))
    total = sum(r.alerts_by_severity.values())
    story += [table, Spacer(1, 12), Paragraph("Alerts: " + (", ".join(f"{n} {sev}" for sev, n in sorted(r.alerts_by_severity.items())) if total else "none"), styles["Normal"])]
    doc.build(story)
    return buf.getvalue()
