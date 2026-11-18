import * as SecureStore from "expo-secure-store";
import { type ReactNode, useEffect, useState } from "react";
import { Linking, Pressable, StyleSheet, Text, View } from "react-native";

const KEY = "ai-consent-v1"; // bump the number when the wording or the provider changes
const PRIVACY_URL = "https://example.com/privacy"; // REPLACE with your real policy URL

/**
 * Apple guideline 5.1.2(i): tell people what is sent, who receives it, and get a
 * clear yes BEFORE any message leaves the phone. "Who": the AI provider your
 * backend calls (Anthropic in this book). Refusing must leave the app usable.
 */
export function AiConsentGate({ children, onDecline }: { children: ReactNode; onDecline: () => void }) {
  const [status, setStatus] = useState<"loading" | "needed" | "granted">("loading");

  useEffect(() => {
    SecureStore.getItemAsync(KEY)
      .then((v) => setStatus(v === "yes" ? "granted" : "needed"))
      .catch(() => setStatus("needed"));
  }, []);

  if (status === "loading") return null;
  if (status === "granted") return <>{children}</>;

  return (
    <View style={styles.wrap}>
      <Text style={styles.title}>Before you chat</Text>
      <Text style={styles.body}>
        To reply, AI Chat sends your messages and any images you attach to our servers, which pass them to
        Anthropic, the company that runs the AI model. They are used only to produce your reply. See the
        privacy policy for how long we keep them and how to delete them.
      </Text>
      <Pressable accessibilityRole="link" onPress={() => Linking.openURL(PRIVACY_URL)}>
        <Text style={styles.link}>Read the privacy policy</Text>
      </Pressable>
      <Pressable
        style={styles.primary}
        accessibilityRole="button"
        onPress={async () => {
          await SecureStore.setItemAsync(KEY, "yes");
          setStatus("granted");
        }}
      >
        <Text style={styles.primaryText}>I agree</Text>
      </Pressable>
      <Pressable accessibilityRole="button" onPress={onDecline}>
        <Text style={styles.link}>Not now</Text>
      </Pressable>
    </View>
  );
}

const styles = StyleSheet.create({
  wrap: { flex: 1, justifyContent: "center", padding: 28, gap: 16 },
  title: { fontSize: 24, fontWeight: "700" },
  body: { fontSize: 16, lineHeight: 24 },
  link: { color: "#1D4ED8", fontSize: 16, textAlign: "center" },
  primary: { backgroundColor: "#1D4ED8", padding: 14, borderRadius: 12, alignItems: "center" },
  primaryText: { color: "#fff", fontSize: 16, fontWeight: "600" },
});
