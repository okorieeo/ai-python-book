import { ApiError, apiFetch } from "./apiClient.js";
import { TaskStore } from "./taskStore.js";
import type { Todo } from "./types.js";

async function main(): Promise<void> {
  // 1. Local store
  const store = new TaskStore();
  store.add("Learn TypeScript", "high");
  const second = store.add("Build the API client");
  store.complete(second.id);
  console.log("Pending:", store.list({ done: false }).map((t) => t.title));

  // 2. Real HTTP call with a typed result
  try {
    const todos = await apiFetch<Todo[]>(
      "https://jsonplaceholder.typicode.com/todos?_limit=5",
    );
    const open = todos.filter((todo) => !todo.completed);
    console.log(`Fetched ${todos.length} todos, ${open.length} still open`);
    for (const todo of open) {
      console.log(` - #${todo.id} ${todo.title}`);
    }
  } catch (error) {
    if (error instanceof ApiError) {
      console.error("Server said no:", error.status);
    } else {
      console.error("Network or other error:", error);
    }
  }

  // 3. Typed error handling for a missing task
  try {
    store.get(999);
  } catch (error) {
    console.log((error as Error).message);
  }
}

main();
