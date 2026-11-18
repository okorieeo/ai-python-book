function formatId(id: number | string): string {
  if (typeof id === "number") {
    return id.toFixed(0);      // here TS knows id is a number
  }
  return id.toUpperCase();     // here it knows id is a string
}

// Discriminated union: very useful for API results and UI state
type Result =
  | { status: "success"; data: string[] }
  | { status: "error"; message: string }
  | { status: "loading" };

function render(result: Result) {
  switch (result.status) {
    case "success": return result.data.join(", ");
    case "error":   return result.message;
    case "loading": return "Loading...";
  }
}
