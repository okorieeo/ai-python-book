python3 - <<'PY'
from datetime import date
from farmsense_core.reports import SensorMeta, build_daily_report, local_day_bounds, render_pdf, render_text
from farmsense_core.simulator import simulate_temperature
start, end = local_day_bounds(date(2026, 11, 10), "Africa/Lagos")
points = simulate_temperature(start, end, 60, seed=5, mean=29, amplitude=5)
report = build_daily_report("Green Acres", date(2026, 11, 10), "Africa/Lagos",
                            [SensorMeta("t", "Barn 1 temperature", "C", 60, high_limit=30.0)], {"t": points}, [{"severity": "warning"}])
open("report.pdf", "wb").write(render_pdf(report))
print(render_text(report))
PY
