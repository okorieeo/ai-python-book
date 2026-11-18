import subprocess, pathlib, shutil
SRC = pathlib.Path("/home/claude/ch59/code/packages/shared/src")
muts = [
 ("layout: touching events treated as overlap", "calendar-layout.ts", "span.start >= clusterEnd", "span.start > clusterEnd"),
 ("layout: lanes never reused", "calendar-layout.ts", "laneEnds.findIndex((end) => end <= span.start)", "-1"),
 ("layout: no minimum height", "calendar-layout.ts", "start + MIN_VISIBLE_MINUTES", "start"),
 ("reducer: final text ignored", "assistant-protocol.ts", "const finalText = event.text || current?.text || \"\";", "const finalText = current?.text || event.text || \"\";"),
 ("reducer: error leaves spinner on", "assistant-protocol.ts", "return { ...state, items, busy: false, error: event.message };", "return { ...state, items, busy: true, error: event.message };"),
 ("reducer: pending not cleared on done", "assistant-protocol.ts", "pending: event.pending.map((p) => ({ ...p, sending: false })) };", "pending: [...state.pending, ...event.pending.map((p) => ({ ...p, sending: false }))] };"),
 ("labels: raw tool name shown", "assistant-protocol.ts", 'TOOL_LABELS[tool] ?? "Working"', "TOOL_LABELS[tool] ?? tool"),
]
caught = 0
for name, f, old, new in muts:
    p = SRC / f; orig = p.read_text(); assert old in orig, name
    p.write_text(orig.replace(old, new, 1))
    r = subprocess.run(["node", "--test", "src/*.test.ts"], cwd=SRC.parent, capture_output=True, text=True, shell=False) if False else subprocess.run("node --test 'src/*.test.ts'", cwd=SRC.parent, capture_output=True, text=True, shell=True)
    p.write_text(orig)
    ok = r.returncode != 0
    caught += ok
    print(("CAUGHT  " if ok else "MISSED  ") + name)
print(f"{caught}/{len(muts)} caught")
