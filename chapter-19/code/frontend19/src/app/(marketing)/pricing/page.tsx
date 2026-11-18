import type { Metadata } from "next";
import { PricingTable } from "@/components/PricingTable";
import { plans } from "@/lib/plans";

export const metadata: Metadata = { title: "Pricing" };

export default function PricingPage() {
  return (
    <div className="flex flex-col gap-8">
      <h1 className="text-3xl font-bold">Pricing</h1>
      <PricingTable plans={plans} />
    </div>
  );
}
