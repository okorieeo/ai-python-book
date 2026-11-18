import { useNetInfo } from "@react-native-community/netinfo";
import { StyleSheet, Text, View } from "react-native";

import { queue } from "@/lib/api";
import { useEffect, useState } from "react";

export function OfflineBanner() {
  const { isConnected, isInternetReachable } = useNetInfo();
  const [waiting, setWaiting] = useState(0);
  useEffect(() => {
    const update = () => setWaiting(queue.pending().length);
    update();
    return queue.subscribe(update);
  }, []);

  const offline = isConnected === false || isInternetReachable === false;
  if (!offline && waiting === 0) return null;
  return (
    <View style={styles.bar} accessibilityRole="alert">
      <Text style={styles.text}>
        {offline ? "You are offline. " : ""}
        {waiting > 0 ? `${waiting} change${waiting === 1 ? "" : "s"} will be sent when you are back online.` : ""}
      </Text>
    </View>
  );
}

const styles = StyleSheet.create({
  bar: { backgroundColor: "#fef3c7", padding: 8 },
  text: { color: "#92400e", textAlign: "center" },
});
