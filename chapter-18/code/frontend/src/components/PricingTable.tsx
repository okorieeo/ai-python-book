"use client";

import { useState } from "react";
import type { Plan } from "@/lib/types";
import { PlanCard } from "./PlanCard";

// The toggle and the cards share one piece of state, so it lives in their
// closest common parent: this component ("lifting state up").
export function PricingTable({ plans }: { plans: Plan[] }) {
  const [yearly, setYearly] = useState(false);
  return (
    <div className="flex flex-col gap-6">
      <label className="flex items-center gap-2 text-sm">
        <input
          type="checkbox"
          checked={yearly}
          onChange={(event) => setYearly(event.target.checked)}
        />
        Bill yearly (2 months free)
      </label>
      <div className="grid gap-4 md:grid-cols-3">
        {plans.map((plan) => (
          <PlanCard key={plan.code} plan={plan} yearly={yearly} />
        ))}
      </div>
    </div>
  );
}
