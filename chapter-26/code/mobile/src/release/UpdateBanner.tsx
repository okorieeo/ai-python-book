import * as Updates from "expo-updates";
import { useEffect } from "react";
import { Pressable, StyleSheet, Text, View } from "react-native";

/**
 * Downloads an over-the-air update in the background and offers a restart.
 * Never restarts on its own: reloading in the middle of a chat loses the draft.
 * Disabled in development builds, where expo-updates is not active.
 */
export function UpdateBanner() {
  const { isUpdateAvailable, isUpdatePending } = Updates.useUpdates();

  useEffect(() => {
    if (isUpdateAvailable && !isUpdatePending) {
      Updates.fetchUpdateAsync().catch(() => {
        /* offline or server hiccup: try again next launch */
      });
    }
  }, [isUpdateAvailable, isUpdatePending]);

  if (!isUpdatePending) return null;

  return (
    <View style={styles.bar} accessibilityRole="alert">
      <Text style={styles.text}>An update is ready.</Text>
      <Pressable accessibilityRole="button" onPress={() => Updates.reloadAsync()}>
        <Text style={styles.action}>Restart to apply</Text>
      </Pressable>
    </View>
  );
}

const styles = StyleSheet.create({
  bar: { flexDirection: "row", justifyContent: "space-between", padding: 12, backgroundColor: "#DBEAFE" },
  text: { color: "#1E3A8A" },
  action: { color: "#1D4ED8", fontWeight: "700" },
});
