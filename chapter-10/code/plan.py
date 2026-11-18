"""Turn tasks with durations and dependencies into a schedule and find the critical path."""
from collections import defaultdict

# task: (duration in working days, [tasks that must finish first])
TASKS = {
    "design":        (5,  []),
    "schema":        (2,  ["design"]),
    "auth-api":      (4,  ["schema"]),
    "chat-api":      (5,  ["schema"]),
    "ai-service":    (4,  ["chat-api"]),
    "websocket":     (4,  ["ai-service"]),
    "web-ui":        (8,  ["design", "auth-api"]),
    "mobile-ui":     (8,  ["design", "auth-api"]),
    "billing":       (6,  ["auth-api"]),
    "deploy":        (3,  ["websocket", "web-ui", "billing"]),
    "beta-testing":  (5,  ["deploy", "mobile-ui"]),
}

def schedule(tasks):
    start, finish = {}, {}

    def finish_of(name):
        if name not in finish:
            duration, deps = tasks[name]
            start[name] = max((finish_of(d) for d in deps), default=0)
            finish[name] = start[name] + duration
        return finish[name]

    for name in tasks:
        finish_of(name)
    return start, finish

start, finish = schedule(TASKS)
total = max(finish.values())

# Walk backwards from the last task along the dependency that finishes latest = critical path
current = max(finish, key=finish.get)
critical = [current]
while TASKS[current][1]:
    current = max(TASKS[current][1], key=lambda d: finish[d])
    critical.append(current)
critical.reverse()

print(f"{'Task':<14} {'Start':>5} {'End':>4}  Timeline (each # = 1 day)")
for name in sorted(TASKS, key=lambda n: (start[n], finish[n])):
    bar = " " * start[name] + "#" * TASKS[name][0]
    mark = "*" if name in critical else " "
    print(f"{name:<13}{mark} {start[name]:>5} {finish[name]:>4}  {bar}")
print(f"\nTotal: {total} working days (about {total / 5:.1f} weeks) with unlimited parallel help")
print("Critical path (*): " + " -> ".join(critical))
print(f"Sum of all task days: {sum(d for d, _ in TASKS.values())} (one person working alone)")
