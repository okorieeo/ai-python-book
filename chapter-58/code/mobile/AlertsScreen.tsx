import { useCallback, useEffect, useState } from "react";
import { Alert as RNAlert, FlatList, Pressable, RefreshControl, Text, View } from "react-native";
import * as Notifications from "expo-notifications";

type AlertItem = { id: number; rule_name: string; severity: "warning" | "critical"; site_name: string; started_at: string; resolved_at: string | null; acknowledged_at: string | null };

export function AlertsScreen({ load, acknowledge }: { load: () => Promise<AlertItem[]>; acknowledge: (id: number) => Promise<void> }) {
  const [items, setItems] = useState<AlertItem[]>([]);
  const [refreshing, setRefreshing] = useState(false);

  const refresh = useCallback(async () => {
    setRefreshing(true);
    try { setItems(await load()); } finally { setRefreshing(false); }
  }, [load]);

  useEffect(() => {
    refresh();
    // tapping a notification opens the app on the list, freshly loaded: the notification is a pointer, the server is the truth
    const tap = Notifications.addNotificationResponseReceivedListener(() => refresh());
    const arrive = Notifications.addNotificationReceivedListener(() => refresh());
    return () => { tap.remove(); arrive.remove(); };
  }, [refresh]);

  async function onAck(id: number) {
    try { await acknowledge(id); await refresh(); }
    catch { RNAlert.alert("Could not acknowledge", "Check your connection and try again."); }
  }

  return (
    <FlatList
      data={items}
      keyExtractor={(a) => String(a.id)}
      refreshControl={<RefreshControl refreshing={refreshing} onRefresh={refresh} />}
      ListEmptyComponent={<Text style={{ padding: 16 }}>No alerts. Everything is within limits.</Text>}
      renderItem={({ item }) => (
        <View style={{ padding: 12, borderLeftWidth: 4, borderLeftColor: item.severity === "critical" ? "#dc2626" : "#f59e0b", marginBottom: 8 }}>
          <Text style={{ fontWeight: "600" }}>{item.severity === "critical" ? "Critical" : "Warning"}: {item.rule_name}</Text>
          <Text>{item.site_name}, {new Date(item.started_at).toLocaleString()}{item.resolved_at ? " (resolved)" : ""}</Text>
          {!item.resolved_at && !item.acknowledged_at && (
            <Pressable accessibilityRole="button" onPress={() => onAck(item.id)} style={{ marginTop: 8, padding: 10, borderWidth: 1, borderRadius: 6 }}>
              <Text>Acknowledge</Text>
            </Pressable>
          )}
        </View>
      )}
    />
  );
}
