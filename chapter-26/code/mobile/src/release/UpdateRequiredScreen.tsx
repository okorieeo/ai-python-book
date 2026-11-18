import { Linking, Pressable, StyleSheet, Text, View } from "react-native";

import type { GateState } from "./versionGate";

type Blocked = Extract<GateState, { kind: "blocked" }>;

export function UpdateRequiredScreen({ gate }: { gate: Blocked }) {
  const outdated = gate.reason === "outdated";
  return (
    <View style={styles.wrap} accessibilityRole="alert">
      <Text style={styles.title}>{outdated ? "Update required" : "Back soon"}</Text>
      <Text style={styles.body}>{gate.message}</Text>
      {outdated && gate.storeUrl ? (
        <Pressable
          style={styles.button}
          accessibilityRole="button"
          onPress={() => Linking.openURL(gate.storeUrl)}
        >
          <Text style={styles.buttonText}>Open the store</Text>
        </Pressable>
      ) : null}
    </View>
  );
}

const styles = StyleSheet.create({
  wrap: { flex: 1, alignItems: "center", justifyContent: "center", padding: 32, gap: 16 },
  title: { fontSize: 24, fontWeight: "700" },
  body: { fontSize: 16, textAlign: "center" },
  button: { backgroundColor: "#1D4ED8", paddingVertical: 14, paddingHorizontal: 28, borderRadius: 12 },
  buttonText: { color: "#fff", fontSize: 16, fontWeight: "600" },
});
