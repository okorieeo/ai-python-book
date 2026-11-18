interface User {
  id: number;
  name: string;
  email?: string;               // optional property (may be missing)
  readonly createdAt: string;   // cannot be changed after creation
}

const user: User = { id: 1, name: "Ada", createdAt: "2026-11-01" };
// user.createdAt = "x";        // Error: read-only
// const bad: User = { id: 1 }; // Error: 'name' is missing

type Plan = "free" | "pro" | "enterprise";   // union of literal values
let currentPlan: Plan = "pro";
// currentPlan = "gold";                     // Error

type ID = number | string;                   // either type
