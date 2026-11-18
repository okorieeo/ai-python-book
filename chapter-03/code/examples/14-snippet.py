tasks = [
    {"title": "Write docs", "priority": 2},
    {"title": "Fix bug", "priority": 1},
]
tasks_sorted = sorted(tasks, key=lambda t: t["priority"])
print([t["title"] for t in tasks_sorted])     # ['Fix bug', 'Write docs']
