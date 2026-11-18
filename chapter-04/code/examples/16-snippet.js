const base = { theme: "dark", lang: "en" };
const updated = { ...base, lang: "fr" };       // copy + override -> { theme: "dark", lang: "fr" }

const list = [1, 2, 3];
const bigger = [...list, 4];                    // [1, 2, 3, 4]
const without2 = list.filter((n) => n !== 2);   // [1, 3]

// Update one item in an array of objects, immutably
const tasks = [{ id: 1, done: false }, { id: 2, done: false }];
const nextTasks = tasks.map((t) => (t.id === 1 ? { ...t, done: true } : t));
