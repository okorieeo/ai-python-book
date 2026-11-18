# task_manager.py
from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import date
from pathlib import Path

DATA_FILE = Path("tasks.json")
VALID_PRIORITIES = ("low", "medium", "high")

class TaskNotFoundError(Exception):
    """Raised when a task id does not exist."""

@dataclass
class Task:
    id: int
    title: str
    priority: str = "medium"
    done: bool = False
    created: str = ""

    def __post_init__(self) -> None:
        # Runs automatically after the dataclass sets its fields: validate here.
        self.title = self.title.strip()
        if not self.title:
            raise ValueError("Title cannot be empty")
        if self.priority not in VALID_PRIORITIES:
            raise ValueError(f"Priority must be one of {VALID_PRIORITIES}")
        if not self.created:
            self.created = date.today().isoformat()
# ----- next listing from the chapter -----
class TaskStore:
    def __init__(self, path: Path = DATA_FILE) -> None:
        self.path = path
        self.tasks: list[Task] = []
        self.load()

    def load(self) -> None:
        if not self.path.exists():
            self.tasks = []
            return
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
            self.tasks = [Task(**item) for item in raw]
        except (json.JSONDecodeError, TypeError, ValueError):
            print("Warning: tasks file is unreadable. Starting with an empty list.")
            self.tasks = []

    def save(self) -> None:
        data = [asdict(task) for task in self.tasks]
        self.path.write_text(json.dumps(data, indent=2), encoding="utf-8")

    def get(self, task_id: int) -> Task:
        for task in self.tasks:
            if task.id == task_id:
                return task
        raise TaskNotFoundError(f"No task with id {task_id}")

    def add(self, title: str, priority: str = "medium") -> Task:
        next_id = max((task.id for task in self.tasks), default=0) + 1
        task = Task(id=next_id, title=title, priority=priority)
        self.tasks.append(task)
        self.save()
        return task

    def complete(self, task_id: int) -> Task:
        task = self.get(task_id)
        task.done = True
        self.save()
        return task

    def delete(self, task_id: int) -> None:
        task = self.get(task_id)
        self.tasks.remove(task)
        self.save()
# ----- next listing from the chapter -----
def print_tasks(tasks: list[Task]) -> None:
    if not tasks:
        print("No tasks yet.")
        return
    for task in tasks:
        mark = "x" if task.done else " "
        print(f"[{mark}] {task.id:>3}  {task.priority:<6}  {task.title}")

def main() -> None:
    store = TaskStore()
    print("Task Manager. Commands: add, list, done, delete, quit")

    while True:
        command = input("> ").strip().lower()
        try:
            if command == "add":
                title = input("Title: ")
                priority = input("Priority (low/medium/high) [medium]: ").strip().lower() or "medium"
                task = store.add(title, priority)
                print(f"Added task {task.id}")
            elif command == "list":
                print_tasks(store.tasks)
            elif command == "done":
                store.complete(int(input("Task id: ")))
                print("Marked as done")
            elif command == "delete":
                store.delete(int(input("Task id: ")))
                print("Deleted")
            elif command == "quit":
                print("Goodbye!")
                break
            else:
                print("Unknown command")
        except ValueError as error:
            print(f"Invalid input: {error}")
        except TaskNotFoundError as error:
            print(error)

if __name__ == "__main__":
    main()
# ----- next listing from the chapter -----
from hello_ai import ask

def suggest_priority(title: str) -> str:
    """Ask the AI model to rate urgency. Falls back to 'medium' on any problem."""
    prompt = (
        "Reply with exactly one word: low, medium or high. "
        "How urgent is this task?\n\n" + title
    )
    try:
        answer = ask(prompt).strip().lower()
    except Exception:          # network problem, missing key, rate limit...
        return "medium"
    return answer if answer in VALID_PRIORITIES else "medium"
