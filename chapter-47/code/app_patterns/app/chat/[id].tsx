import { useLocalSearchParams } from "expo-router";
import { useCallback, useEffect, useState } from "react";
import { FlatList, KeyboardAvoidingView, Platform, Pressable, StyleSheet, Text, TextInput, View } from "react-native";

import { OfflineBanner } from "@/components/OfflineBanner";
import { api, queue, socket } from "@/lib/api";

interface Message {
  id: string;
  text: string;
  pending?: boolean;
}

export default function ChatScreen() {
  const { id } = useLocalSearchParams<{ id: string }>();
  const [messages, setMessages] = useState<Message[]>([]);
  const [draft, setDraft] = useState("");

  useEffect(() => {
    let cancelled = false;
    api
      .get<{ results: Message[] }>(`/api/v1/conversations/${id}/messages/`)
      .then((page) => !cancelled && setMessages(page.results))
      .catch(() => undefined); // offline: keep what we have (a cache would go here)
    socket.connect();
    const off = socket.onMessage((m) => {
      const msg = m as { type?: string; message?: Message };
      if (msg.type === "chat.message" && msg.message) setMessages((prev) => [...prev, msg.message as Message]);
    });
    return () => {
      cancelled = true;
      off();
    };
  }, [id]);

  const send = useCallback(async () => {
    const text = draft.trim();
    if (!text) return;
    setDraft("");
    setMessages((prev) => [...prev, { id: `local-${Date.now()}`, text, pending: true }]);
    await queue.enqueue({ method: "POST", path: `/api/v1/conversations/${id}/messages/`, body: { text } });
    void queue.flush(); // sends now if online; stays queued if not
  }, [draft, id]);

  return (
    <KeyboardAvoidingView style={styles.container} behavior={Platform.OS === "ios" ? "padding" : undefined}>
      <OfflineBanner />
      <FlatList
        data={messages}
        keyExtractor={(m) => m.id}
        renderItem={({ item }) => (
          <Text style={[styles.message, item.pending && styles.pending]}>{item.text}</Text>
        )}
      />
      <View style={styles.row}>
        <TextInput style={styles.input} value={draft} onChangeText={setDraft} placeholder="Message" />
        <Pressable accessibilityRole="button" onPress={send} style={styles.send}>
          <Text style={styles.sendText}>Send</Text>
        </Pressable>
      </View>
    </KeyboardAvoidingView>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1 },
  message: { padding: 12 },
  pending: { opacity: 0.5 },
  row: { flexDirection: "row", padding: 8, gap: 8 },
  input: { flex: 1, borderWidth: 1, borderColor: "#cbd5e1", borderRadius: 8, padding: 10 },
  send: { backgroundColor: "#1e3a8a", borderRadius: 8, paddingHorizontal: 16, justifyContent: "center" },
  sendText: { color: "#fff", fontWeight: "600" },
});
