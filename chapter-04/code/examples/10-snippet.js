const tasks = [
  { id: 1, title: "Write docs", done: true,  priority: 2 },
  { id: 2, title: "Fix bug",    done: false, priority: 1 },
  { id: 3, title: "Deploy",     done: false, priority: 3 },
];

// map: transform every item -> new array
const titles = tasks.map((task) => task.title);
// ["Write docs", "Fix bug", "Deploy"]

// filter: keep items that pass a test
const pending = tasks.filter((task) => !task.done);

// find: first matching item (or undefined)
const bug = tasks.find((task) => task.id === 2);

// some / every: does any / do all items pass?
const hasPending = tasks.some((task) => !task.done);   // true
const allDone = tasks.every((task) => task.done);      // false

// reduce: combine into one value
const totalPriority = tasks.reduce((sum, task) => sum + task.priority, 0); // 6

// sort: ORDER CHANGES THE ORIGINAL - copy first
const byPriority = [...tasks].sort((a, b) => a.priority - b.priority);

// forEach: do something for each (no return value)
tasks.forEach((task) => console.log(task.title));

// chaining
const urgentTitles = tasks
  .filter((t) => !t.done)
  .sort((a, b) => a.priority - b.priority)
  .map((t) => t.title);
