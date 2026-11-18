async function loadDashboard() {
  // Sequential (slow): total time = A + B + C
  // const a = await fetchA(); const b = await fetchB();

  // Parallel (fast): total time = the slowest one
  const [profile, tasks, stats] = await Promise.all([
    fetch("/api/profile").then((r) => r.json()),
    fetch("/api/tasks").then((r) => r.json()),
    fetch("/api/stats").then((r) => r.json()),
  ]);
  return { profile, tasks, stats };
}
