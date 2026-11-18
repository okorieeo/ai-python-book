"""Read PostgreSQL EXPLAIN (ANALYZE) text and point at the usual suspects."""
from __future__ import annotations

import re
from dataclasses import dataclass

_NODE = re.compile(r"^(?P<indent>\s*)(?:->\s*)?(?P<node>[A-Z][A-Za-z ]+?)(?: using (?P<index>\S+))?(?: on (?P<table>\S+))?\s+\(cost=[\d.]+\.\.(?P<cost>[\d.]+) rows=(?P<est>\d+) width=\d+\)(?: \(actual time=(?P<t0>[\d.]+)\.\.(?P<t1>[\d.]+) rows=(?P<act>\d+) loops=(?P<loops>\d+)\))?")


@dataclass(frozen=True)
class Finding:
    severity: str      # "high" | "medium" | "info"
    node: str
    message: str


def analyze(plan: str, *, seq_scan_rows: int = 10_000, misestimate_factor: float = 10.0) -> list[Finding]:
    findings: list[Finding] = []
    for line in plan.splitlines():
        m = _NODE.match(line)
        if m and m["act"] is not None:
            node, table = m["node"].strip(), m["table"] or ""
            est, act, loops = int(m["est"]), int(m["act"]), int(m["loops"])
            total_rows = act * loops
            if node == "Seq Scan" and total_rows >= seq_scan_rows:
                findings.append(Finding("high", f"Seq Scan on {table}",
                                        f"read {total_rows:,} rows with no index; check the WHERE columns and add an index"))
            if node == "Seq Scan" and "Rows Removed by Filter" in plan and total_rows < 100:
                findings.append(Finding("high", f"Seq Scan on {table}", "scans the table to return a few rows: a missing index"))
            if max(est, 1) / max(act, 1) >= misestimate_factor or max(act, 1) / max(est, 1) >= misestimate_factor:
                findings.append(Finding("medium", f"{node} {table}".strip(),
                                        f"planner expected {est:,} rows but got {act:,}: run ANALYZE, check statistics"))
            if node == "Nested Loop" and loops == 1 and act >= 100_000:
                findings.append(Finding("medium", "Nested Loop", f"produced {act:,} rows; a hash or merge join may suit better"))
            if loops >= 1000:
                findings.append(Finding("high", f"{node} {table}".strip(), f"executed {loops:,} times: an N+1 inside the database"))
        if "Sort Method: external" in line:
            findings.append(Finding("medium", "Sort", "spilled to disk: raise work_mem for this query or add an index that gives the order"))
        if re.search(r"Rows Removed by Filter: (\d+)", line):
            removed = int(re.search(r"Rows Removed by Filter: (\d+)", line).group(1))
            if removed >= 100_000:
                findings.append(Finding("medium", "Filter", f"threw away {removed:,} rows after reading them: an index on the filter column would avoid that"))
    t = re.search(r"Execution Time: ([\d.]+) ms", plan)
    if t and float(t.group(1)) >= 1000:
        findings.append(Finding("info", "Total", f"execution took {float(t.group(1)):,.0f} ms"))
    return findings
