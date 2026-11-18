import { formatPrice } from "@/lib/format";
import { yearlyPriceCents } from "@/lib/plans";
import type { Plan } from "@/lib/types";

interface PlanCardProps {
  plan: Plan;
  yearly: boolean;
}

export function PlanCard({ plan, yearly }: PlanCardProps) {
  const price = yearly ? yearlyPriceCents(plan.priceCents) : plan.priceCents;
  return (
    <article
      className={`flex flex-col gap-3 rounded-xl border p-6 ${
        plan.popular ? "border-blue-600 shadow-md" : ""
      }`}
    >
      {plan.popular && (
        <span className="w-fit rounded-full bg-blue-600 px-2 py-0.5 text-xs font-medium text-white">
          Most popular
        </span>
      )}
      <h2 className="text-lg font-semibold">{plan.name}</h2>
      <p className="text-3xl font-bold">
        {formatPrice(price)}
        <span className="text-sm font-normal text-zinc-500">
          {price === 0 ? "" : yearly ? " / year" : " / month"}
        </span>
      </p>
      <ul className="flex flex-col gap-1 text-sm">
        {plan.features.map((feature) => (
          <li key={feature}>✓ {feature}</li>
        ))}
      </ul>
    </article>
  );
}
