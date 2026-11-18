import { useState } from "react";
import {
  FlatList, KeyboardAvoidingView, Platform, Pressable, StyleSheet, Text, TextInput, View,
} from "react-native";
import { describeTool, type ChatItem } from "@app/shared/assistant-protocol";
import { useAssistant } from "@app/shared/useAssistant";

// The same WebSocket address and sign-in as your Chapter 24 screens.
const SOCKET_URL = process.env.EXPO_PUBLIC_WS_URL ?? "";

function Bubble({ item }: { item: ChatItem }) {
  const mine = item.role === "user";
  return (
    <View style={[styles.row, mine ? styles.rowMine : styles.rowTheirs]}>
      {item.tools.map((t, n) => (
        <Text key={n} style={styles.chip}>
          {describeTool(t.tool)}
          {t.state === "running" ? "…" : " ✓"}
        </Text>
      ))}
      <Text style={[styles.bubble, mine ? styles.bubbleMine : styles.bubbleTheirs]}>{item.text}</Text>
    </View>
  );
}

export default function AssistantScreen() {
  const { state, connected, sendMessage, decide } = useAssistant(SOCKET_URL);
  const [text, setText] = useState("");
  const waiting = state.pending.length > 0; // the server refuses new messages until it is answered
  const canSend = connected && !state.busy && !waiting && text.trim().length > 0;

  const send = () => {
    sendMessage(text.trim());
    setText("");
  };

  return (
    <KeyboardAvoidingView behavior={Platform.OS === "ios" ? "padding" : undefined} style={styles.fill}>
      <FlatList
        data={state.items}
        keyExtractor={(item) => String(item.id)}
        contentContainerStyle={styles.list}
        renderItem={({ item }) => <Bubble item={item} />}
        ListFooterComponent={
          <View style={styles.footer}>
            {state.pending.map((p) => (
              <View key={p.action_id} accessibilityRole="alert" style={styles.card}>
                <Text style={styles.cardTitle}>Please confirm</Text>
                <Text>{p.summary}</Text>
                <View style={styles.buttons}>
                  <Pressable accessibilityRole="button" disabled={p.sending}
                    onPress={() => decide(p.action_id, true)} style={[styles.button, styles.danger]}>
                    <Text style={styles.white}>Yes, do it</Text>
                  </Pressable>
                  <Pressable accessibilityRole="button" disabled={p.sending}
                    onPress={() => decide(p.action_id, false)} style={[styles.button, styles.outline]}>
                    <Text>No, keep it</Text>
                  </Pressable>
                </View>
              </View>
            ))}
            {state.error ? <Text accessibilityRole="alert" style={styles.error}>{state.error}</Text> : null}
          </View>
        }
      />
      <View style={styles.composer}>
        <TextInput
          value={text}
          onChangeText={setText}
          maxLength={4000}
          editable={!waiting}
          placeholder={waiting ? "Answer the question first" : "Ask me anything"}
          accessibilityLabel="Message"
          style={styles.input}
        />
        <Pressable accessibilityRole="button" disabled={!canSend} onPress={send}
          style={[styles.send, canSend ? styles.sendOn : styles.sendOff]}>
          <Text style={styles.white}>Send</Text>
        </Pressable>
      </View>
    </KeyboardAvoidingView>
  );
}

const styles = StyleSheet.create({
  fill: { flex: 1 },
  list: { padding: 16, gap: 8 },
  row: { maxWidth: "85%" },
  rowMine: { alignSelf: "flex-end" },
  rowTheirs: { alignSelf: "flex-start" },
  chip: { fontSize: 12, opacity: 0.6 },
  bubble: { padding: 10, borderRadius: 14 },
  bubbleMine: { backgroundColor: "#2563eb", color: "white" },
  bubbleTheirs: { backgroundColor: "#f3f4f6", color: "black" },
  footer: { gap: 8 },
  card: { padding: 12, borderRadius: 10, backgroundColor: "#fffbeb", borderWidth: 1, borderColor: "#fcd34d" },
  cardTitle: { fontWeight: "600" },
  buttons: { flexDirection: "row", gap: 8, marginTop: 8 },
  button: { padding: 10, borderRadius: 8, minHeight: 44, justifyContent: "center" }, // 44pt: easy to tap
  danger: { backgroundColor: "#dc2626" },
  outline: { borderWidth: 1 },
  white: { color: "white" },
  error: { color: "#dc2626" },
  composer: { flexDirection: "row", gap: 8, padding: 12 },
  input: { flex: 1, borderWidth: 1, borderRadius: 8, padding: 10 },
  send: { padding: 12, borderRadius: 8, minHeight: 44, justifyContent: "center" },
  sendOn: { backgroundColor: "#2563eb" },
  sendOff: { backgroundColor: "#9ca3af" },
});
