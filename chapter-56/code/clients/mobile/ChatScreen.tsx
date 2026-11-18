import { useRef, useState } from "react";
import { ActivityIndicator, FlatList, KeyboardAvoidingView, Linking, Platform, Pressable, StyleSheet, Text, TextInput, View } from "react-native";

import { useChat, type UseChatOptions } from "../shared/use-chat";

export default function ChatScreen(props: UseChatOptions & { upgradeUrl: string }) {
  const { state, send, stop } = useChat(props);
  const [draft, setDraft] = useState("");
  const list = useRef<FlatList>(null);
  const canSend = state.connection === "open" && !state.busy && !state.limitReached && draft.trim().length > 0;

  return (
    <KeyboardAvoidingView style={styles.screen} behavior={Platform.OS === "ios" ? "padding" : undefined}>
      <View style={styles.header}>
        <Text>{state.plan?.name ?? "…"}</Text>
        <Text>{state.usage ? `${state.usage.used}/${state.usage.limit} today` : ""}</Text>
        {state.connection !== "open" && <ActivityIndicator />}
      </View>

      <FlatList ref={list} data={state.messages} keyExtractor={(m) => m.key} contentContainerStyle={{ padding: 12 }}
        onContentSizeChange={() => list.current?.scrollToEnd({ animated: true })}
        renderItem={({ item }) => (
          <View style={[styles.bubble, item.role === "user" ? styles.mine : styles.theirs]}>
            <Text style={item.role === "user" ? styles.mineText : undefined}>{item.content || (item.status === "streaming" ? "…" : "")}</Text>
            {item.status === "stopped" && <Text style={styles.note}>Stopped</Text>}
            {item.status === "error" && <Text style={[styles.note, { color: "#b91c1c" }]}>This answer did not finish.</Text>}
          </View>
        )} />

      {state.error && (
        <View style={styles.error}>
          <Text>{state.error.message}</Text>
          {state.limitReached && <Pressable onPress={() => Linking.openURL(props.upgradeUrl)}><Text style={styles.link}>Upgrade</Text></Pressable>}
        </View>
      )}

      <View style={styles.composer}>
        <TextInput style={styles.input} value={draft} onChangeText={setDraft} multiline placeholder="Ask anything…" maxLength={8000} />
        {state.busy
          ? <Pressable style={[styles.button, { backgroundColor: "#1f2937" }]} onPress={stop}><Text style={styles.buttonText}>Stop</Text></Pressable>
          : <Pressable style={[styles.button, !canSend && { opacity: 0.5 }]} disabled={!canSend}
              onPress={() => { if (send(draft)) setDraft(""); }}><Text style={styles.buttonText}>Send</Text></Pressable>}
      </View>
    </KeyboardAvoidingView>
  );
}

const styles = StyleSheet.create({
  screen: { flex: 1 },
  header: { flexDirection: "row", justifyContent: "space-between", padding: 10, borderBottomWidth: StyleSheet.hairlineWidth },
  bubble: { maxWidth: "80%", padding: 10, borderRadius: 12, marginBottom: 8 },
  mine: { alignSelf: "flex-end", backgroundColor: "#2563eb" },
  mineText: { color: "white" },
  theirs: { alignSelf: "flex-start", backgroundColor: "#f3f4f6" },
  note: { fontSize: 11, opacity: 0.7, marginTop: 4 },
  error: { padding: 10, backgroundColor: "#fffbeb", flexDirection: "row", justifyContent: "space-between" },
  link: { fontWeight: "600", textDecorationLine: "underline" },
  composer: { flexDirection: "row", gap: 8, padding: 10, borderTopWidth: StyleSheet.hairlineWidth },
  input: { flex: 1, borderWidth: 1, borderColor: "#d1d5db", borderRadius: 8, padding: 8, maxHeight: 120 },
  button: { justifyContent: "center", paddingHorizontal: 16, borderRadius: 8, backgroundColor: "#2563eb" },
  buttonText: { color: "white", fontWeight: "600" },
});
