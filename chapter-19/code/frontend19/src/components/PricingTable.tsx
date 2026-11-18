"use client";

import { useId, useState } from "react";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import type { Plan } from "@/lib/types";
import { PlanCard } from "./PlanCard";

export function PricingTable({ plans }: { plans: Plan[] }) {
  const [yearly, setYearly] = useState(false);
  const switchId = useId(); // a unique id so the label and the switch are linked
  return (
    <div className="flex flex-col gap-6">
      <div className="flex items-center gap-3">
        <Switch id={switchId} checked={yearly} onCheckedChange={setYearly} />
        <Label htmlFor={switchId}>Bill yearly (2 months free)</Label>
      </div>
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {plans.map((plan) => (
          <PlanCard key={plan.code} plan={plan} yearly={yearly} />
        ))}
      </div>
    </div>
  );
}
