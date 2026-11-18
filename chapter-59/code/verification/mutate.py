import subprocess, shutil, sys, pathlib
RUN = pathlib.Path("/home/claude/ch59/run/backend")
mutations = [
  ("agent: CONFIRM gate removed", "assistant/agent.py", "if tool is not None and tool.risk is Risk.CONFIRM:", "if False:"),
  ("agent: truncated reply acted on", "assistant/agent.py", 'if turn.stop_reason == "max_tokens":', 'if False:'),
  ("agent: step limit ignored", "assistant/agent.py", "if steps >= limits.max_steps:", "if False:"),
  ("tools: unknown fields allowed", "assistant/tools.py", 'problems.append(f"{name}: unknown field")', 'pass'),
  ("tools: bool accepted as integer", "assistant/tools.py", '"integer": lambda v: isinstance(v, int) and not isinstance(v, bool)', '"integer": lambda v: isinstance(v, int)'),
  ("tools: crash text leaked", "assistant/tools.py", 'return _fail("internal_error", "The tool failed. Tell the user something went wrong; do not retry.")', 'return _fail("internal_error", "failed")\n        raise'),
  ("availability: touching counts as overlap", "schedule/availability.py", "return a.start < b.end and b.start < a.end", "return a.start <= b.end and b.start <= a.end"),
  ("availability: buffer ignored", "schedule/availability.py", "Interval(b.start - buffer, b.end + buffer)", "Interval(b.start, b.end)"),
  ("timeutils: gap flag swapped", "core/timeutils.py", "shifted=before < after,", "shifted=before > after,"),
  ("recurrence: weekly includes days before start", "schedule/recurrence.py", "if day >= start:", "if True:"),
  ("recurrence: count ignores excluded dates (counts kept ones)", "schedule/recurrence.py", "if rule.count is not None and scanned > rule.count:", "if rule.count is not None and len(found) >= rule.count:"),
  ("planning: age ignored", "tasks/planning.py", "score += age_days * w[\"age_per_day\"]", "pass"),
  ("untrusted: marker regex weakened", "assistant/untrusted.py", r'r"<\s*/?\s*untrusted"', r'r"</?untrusted"'),
  ("briefing: no once-per-day guard", "assistant/briefing.py", "if last_sent is not None and last_sent >= today:", "if False:"),
  ("briefing: no lateness cutoff", "assistant/briefing.py", "scheduled <= now < scheduled + max_late", "scheduled <= now"),
]
killed = 0
for name, rel, old, new in mutations:
    subprocess.run(["/home/claude/ch59/sync.sh"], check=True)
    p = RUN / rel
    src = p.read_text()
    assert old in src, f"pattern not found for {name}"
    p.write_text(src.replace(old, new, 1))
    r = subprocess.run([sys.executable, "-m", "unittest", "core.test_timeutils", "schedule.test_recurrence", "schedule.test_availability", "tasks.test_planning", "assistant.test_untrusted", "assistant.test_tools", "assistant.test_agent", "assistant.test_prompt_briefing"],
                       cwd=RUN, capture_output=True, text=True)
    caught = r.returncode != 0
    killed += caught
    print(("CAUGHT  " if caught else "MISSED  ") + name)
print(f"\n{killed}/{len(mutations)} mutations caught")
subprocess.run(["/home/claude/ch59/sync.sh"], check=True)
