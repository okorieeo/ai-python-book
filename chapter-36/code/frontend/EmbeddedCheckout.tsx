// components/EmbeddedCheckout.tsx: Checkout inside your own page (ui_mode "embedded_page"). Not executed here.
// npm install @stripe/stripe-js @stripe/react-stripe-js
"use client";

import { EmbeddedCheckout, EmbeddedCheckoutProvider } from "@stripe/react-stripe-js";
import { loadStripe } from "@stripe/stripe-js";
import { apiFetch } from "@/lib/api";
import type { PlanKey } from "@/lib/billing";

// Load Stripe.js once, at module level, never inside a component that re-renders.
const stripePromise = loadStripe(process.env.NEXT_PUBLIC_STRIPE_PUBLISHABLE_KEY!);

export default function CheckoutInPage({ plan }: { plan: PlanKey }) {
  const fetchClientSecret = async () => {
    const { client_secret } = await apiFetch<{ client_secret: string }>("/api/billing/checkout/", {
      method: "POST",
      body: { plan, embedded: true },
    });
    return client_secret;
  };
  return (
    <EmbeddedCheckoutProvider stripe={stripePromise} options={{ fetchClientSecret }}>
      <EmbeddedCheckout />
    </EmbeddedCheckoutProvider>
  );
}
