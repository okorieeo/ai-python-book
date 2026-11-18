// app/billing/callback/page.tsx: where Paystack sends the customer after paying.
// The URL carries ?reference=...&trxref=...; the page asks OUR server, which asks Paystack. Not executed here.
"use client";

import { useSearchParams } from "next/navigation";
import { useEffect, useState } from "react";
import { getStatus, verify } from "@/lib/paystack";

type State = "checking" | "paid" | "pending" | "failed" | "mismatch" | "error";

export default function CallbackPage() {
  const params = useSearchParams();
  const reference = params.get("reference") ?? params.get("trxref");
  const [state, setState] = useState<State>("checking");

  useEffect(() => {
    if (!reference) { setState("error"); return; }
    let cancelled = false;
    (async () => {
      try {
        for (let attempt = 0; attempt < 6 && !cancelled; attempt++) {
          const result = await verify(reference);              // the server asks Paystack
          if (result.status === "paid") { setState("paid"); return; }
          if (result.status === "mismatch") { setState("mismatch"); return; }
          if (result.status === "failed") { setState("failed"); return; }
          await new Promise((r) => setTimeout(r, 2000));       // still pending (a bank transfer, for example)
        }
        if (!cancelled) setState((await getStatus()).paid ? "paid" : "pending");
      } catch { if (!cancelled) setState("error"); }
    })();
    return () => { cancelled = true; };
  }, [reference]);

  const messages: Record<State, string> = {
    checking: "Confirming your payment…",
    paid: "Thank you! Your payment was received.",
    pending: "Your payment is still being confirmed. We will email you when it is done.",
    failed: "The payment did not go through. You have not been charged. You can try again.",
    mismatch: "The amount paid did not match the price, so nothing was activated. Please contact support.",
    error: "We could not confirm your payment. If you were charged, contact support with your reference.",
  };
  return <p role={state === "paid" || state === "checking" ? "status" : "alert"}>{messages[state]}</p>;
}
