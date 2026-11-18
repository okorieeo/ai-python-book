// POST JSON to an API
async function createTask(title) {
  const response = await fetch("https://api.example.com/tasks/", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Authorization: "Bearer YOUR_TOKEN",
    },
    body: JSON.stringify({ title }),
  });
  if (!response.ok) throw new Error(`HTTP ${response.status}`);
  return response.json();
}
