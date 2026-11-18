// mobile/PaystackCheckout.tsx: opens Paystack's hosted checkout in a WebView and catches the callback URL.
// npm install react-native-webview. Not executed here. Read section 37.10 (app store rules) before using it.
import { useRef } from "react";
import { ActivityIndicator, Modal, SafeAreaView } from "react-native";
import { WebView } from "react-native-webview";
import { apiFetch } from "./api";

const CALLBACK_PREFIX = "https://app.example.com/billing/callback";   // must match PAYSTACK_CALLBACK_URL on the server

type Props = { authorizationUrl: string; visible: boolean; onDone: (paid: boolean) => void };

export default function PaystackCheckout({ authorizationUrl, visible, onDone }: Props) {
  const handled = useRef(false);

  async function finish(url: string) {
    if (handled.current) return;                 // the redirect can fire more than once
    handled.current = true;
    const reference = new URL(url).searchParams.get("reference");
    if (!reference) return onDone(false);
    try {
      // The app never decides. The server asks Paystack and compares the amount.
      const result = await apiFetch<{ status: string }>("/api/billing/paystack/verify/", { method: "POST", body: { reference } });
      onDone(result.status === "paid");
    } catch { onDone(false); }
  }

  return (
    <Modal visible={visible} animationType="slide" onRequestClose={() => onDone(false)}>
      <SafeAreaView style={{ flex: 1 }}>
        <WebView
          source={{ uri: authorizationUrl }}
          startInLoadingState
          renderLoading={() => <ActivityIndicator style={{ flex: 1 }} />}
          // Stop at our callback URL instead of loading it inside the app.
          onShouldStartLoadWithRequest={(request) => {
            if (request.url.startsWith(CALLBACK_PREFIX)) { void finish(request.url); return false; }
            return true;
          }}
        />
      </SafeAreaView>
    </Modal>
  );
}
