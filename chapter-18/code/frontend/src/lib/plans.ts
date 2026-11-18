import type { Plan } from "./types";

// The same plans as the `plans` table of Chapter 7. Chapter 20 loads them from the API.
export const plans: Plan[] = [
  {
    code: "free",
    name: "Free",
    priceCents: 0,
    monthlyTokenLimit: 50_000,
    features: ["50K tokens per month", "1 workspace", "Community support"],
  },
  {
    code: "pro",
    name: "Pro",
    priceCents: 1900,
    monthlyTokenLimit: 1_000_000,
    features: [
      "1M tokens per month",
      "Unlimited documents",
      "Priority support",
    ],
    popular: true,
  },
  {
    code: "team",
    name: "Team",
    priceCents: 4900,
    monthlyTokenLimit: 5_000_000,
    features: [
      "5M tokens per month",
      "Shared workspaces",
      "Roles and permissions",
    ],
  },
];

/** Yearly billing: pay for 10 months, get 12. */
export function yearlyPriceCents(monthlyCents: number): number {
  return monthlyCents * 10;
}
