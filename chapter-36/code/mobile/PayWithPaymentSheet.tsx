// mobile/PayWithPaymentSheet.tsx: Stripe's native Payment Sheet for REAL-WORLD goods and services only.
// Digital features and subscriptions inside the app are governed by the store rules (section 36.9).
// npm install @stripe/stripe-react-native. Not executed here.
import { StripeProvider, useStripe } from "@stripe/stripe-react-native";
import { useState } from "react";
import { Alert, Button } from "react-native";
import { apiFetch } from "./api";

function BuyButton({ item }: { item: string }) {
  const { initPaymentSheet, presentPaymentSheet } = useStripe();
  const [busy, setBusy] = useState(false);

  async function pay() {
    setBusy(true);
    try {
      // 1. Our server decides the amount and creates the PaymentIntent, the customer key and the customer.
      const s = await apiFetch<{ paymentIntent: string; ephemeralKey: string; customer: string }>(
        "/api/billing/payment-sheet/", { method: "POST", body: { item } });
      // 2. Prepare the sheet.
      const init = await initPaymentSheet({
        merchantDisplayName: "AI Chat",
        customerId: s.customer,
        customerEphemeralKeySecret: s.ephemeralKey,
        paymentIntentClientSecret: s.paymentIntent,
        allowsDelayedPaymentMethods: false,
        returnURL: "aichat://stripe-redirect",      // for payment methods that leave the app and come back
      });
      if (init.error) throw new Error(init.error.message);
      // 3. Show it. The card details go from the sheet straight to Stripe, never through our app code.
      const result = await presentPaymentSheet();
      if (result.error) {
        if (result.error.code !== "Canceled") Alert.alert("Payment failed", result.error.message);
        return;
      }
      Alert.alert("Thank you!", "Your payment was received."); // the webhook, not this line, records it
    } catch (e) {
      Alert.alert("Something went wrong", e instanceof Error ? e.message : "Try again.");
    } finally {
      setBusy(false);
    }
  }
  return <Button title={busy ? "Please wait…" : "Pay"} disabled={busy} onPress={pay} />;
}

export default function Screen({ publishableKey }: { publishableKey: string }) {
  return (
    <StripeProvider publishableKey={publishableKey} urlScheme="aichat">
      <BuyButton item="consulting_hour" />
    </StripeProvider>
  );
}
