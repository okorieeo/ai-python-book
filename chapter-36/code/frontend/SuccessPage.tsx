// app/billing/success/page.tsx: where Stripe sends the customer after paying.
// The page never trusts the URL: it asks OUR server, which asks Stripe. Not executed here.
"use client";

import { useSearchParams } from "next/navigation";
import { useEffect, useState } from "react";
import { getStatus, syncCheckout } from "@/lib/billing";

export default function SuccessPage() {
  const sessionId = useSearchParams().get("session_id");
  const [state, setState] = useState<"checking" | "ready" | "pending" | "error">("checking");

  useEffect(() => {
    if (!sessionId) { setState("error"); return; }
    let cancelled = false;
    (async () => {
      try {
        const first = await syncCheckout(sessionId);            // reads the session from Stripe, server side
        if (first.paid || first.credits > 0) { if (!cancelled) setState("ready"); return; }
        for (let i = 0; i < 8 && !cancelled; i++) {             // a delayed payment method: poll the status
          await new Promise((r) => setTimeout(r, 2000));
          if ((await getStatus()).paid) { setState("ready"); return; }
        }
        if (!cancelled) setState("pending");
      } catch { if (!cancelled) setState("error"); }
    })();
    return () => { cancelled = true; };
  }, [sessionId]);

  if (state === "ready") return <p>Thank you! Your plan is active.</p>;
  if (state === "pending") return <p>Your payment is still being confirmed. We will email you when it is done.</p>;
  if (state === "error") return <p role="alert">We could not confirm your payment. If you were charged, contact support.</p>;
  return <p>Confirming your payment…</p>;
}
