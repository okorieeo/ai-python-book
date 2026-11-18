import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardFooter,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { formatPrice } from "@/lib/format";
import { yearlyPriceCents } from "@/lib/plans";
import type { Plan } from "@/lib/types";
import { cn } from "@/lib/utils";
import Link from "next/link";
import { Check } from "lucide-react";

interface PlanCardProps {
  plan: Plan;
  yearly: boolean;
}

export function PlanCard({ plan, yearly }: PlanCardProps) {
  const price = yearly ? yearlyPriceCents(plan.priceCents) : plan.priceCents;
  return (
    <Card
      className={cn(plan.popular && "border-primary shadow-md")}
      role="article"
    >
      <CardHeader>
        {plan.popular && <Badge>Most popular</Badge>}
        <CardTitle>{plan.name}</CardTitle>
        <p className="text-3xl font-bold">
          {formatPrice(price)}
          <span className="text-muted-foreground text-sm font-normal">
            {price === 0 ? "" : yearly ? " / year" : " / month"}
          </span>
        </p>
      </CardHeader>
      <CardContent>
        <ul className="flex flex-col gap-2 text-sm">
          {plan.features.map((feature) => (
            <li key={feature} className="flex items-center gap-2">
              <Check className="text-primary size-4" aria-hidden="true" />
              {feature}
            </li>
          ))}
        </ul>
      </CardContent>
      <CardFooter>
        <Button
          asChild
          variant={plan.popular ? "default" : "outline"}
          className="w-full"
        >
          <Link href="/chat">Choose {plan.name}</Link>
        </Button>
      </CardFooter>
    </Card>
  );
}
