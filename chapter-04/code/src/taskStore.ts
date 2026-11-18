import type { Priority, Task } from "./types.js";

export class TaskNotFoundError extends Error {
  constructor(id: number) {
    super(`No task with id ${id}`);
    this.name = "TaskNotFoundError";
  }
}

export class TaskStore {
  private tasks: Task[] = [];
  private nextId = 1;

  add(title: string, priority: Priority = "medium"): Task {
    const cleanTitle = title.trim();
    if (!cleanTitle) {
      throw new Error("Title cannot be empty");
    }
    const task: Task = {
      id: this.nextId++,
      title: cleanTitle,
      priority,
      done: false,
      createdAt: new Date().toISOString(),
    };
    this.tasks.push(task);
    return task;
  }

  get(id: number): Task {
    const task = this.tasks.find((t) => t.id === id);
    if (!task) throw new TaskNotFoundError(id);
    return task;
  }

  complete(id: number): Task {
    const task = this.get(id);
    task.done = true;
    return task;
  }

  remove(id: number): void {
    this.get(id);                                   // throws if missing
    this.tasks = this.tasks.filter((t) => t.id !== id);
  }

  list(filter?: { done?: boolean }): Task[] {
    if (filter?.done === undefined) return [...this.tasks];
    return this.tasks.filter((t) => t.done === filter.done);
  }
}
