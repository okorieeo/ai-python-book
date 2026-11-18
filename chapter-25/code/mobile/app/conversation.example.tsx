// Adapt to your Chapter 24 conversation screen, for example app/conversations/[id].tsx.
import { useLocalSearchParams } from 'expo-router';
import { ActivityIndicator, KeyboardAvoidingView, Platform, Pressable, StyleSheet, Text, TextInput, View } from 'react-native';
import { MessageList } from '../components/MessageList';
import { ScreenErrorBoundary } from '../components/ScreenErrorBoundary';
import { useDraft } from '../hooks/useDraft';
import { useMessages } from '../hooks/useMessages';
import { useSendMessage } from '../hooks/useSendMessage';
import { userMessage } from '../lib/net/errors';

function ConversationScreen() {
  const { id } = useLocalSearchParams<{ id: string }>();
  const conversationId = String(id);
  const { messages, isLoading, isShowingSavedData, error, lastUpdatedAt, refetch } = useMessages(conversationId);
  const send = useSendMessage(conversationId);
  const draft = useDraft(conversationId);

  const onSend = async () => {
    const text = draft.text;
    draft.clear(); // the message is saved in the outbox first, so clearing the box is safe
    try {
      await send(text);
    } catch {
      draft.update(text); // the outbox itself could not save it (storage full): give the text back
    }
  };

  if (isLoading) return <ActivityIndicator style={styles.center} accessibilityLabel="Loading messages" />;
  if (error) {
    return (
      <View style={styles.center}>
        <Text style={styles.error}>{userMessage(error)}</Text>
        <Pressable accessibilityRole="button" onPress={() => void refetch()}>
          <Text style={styles.link}>Try again</Text>
        </Pressable>
      </View>
    );
  }

  return (
    <KeyboardAvoidingView style={styles.flex} behavior={Platform.OS === 'ios' ? 'padding' : undefined}>
      {isShowingSavedData && lastUpdatedAt ? (
        <Text style={styles.stale}>Saved copy from {new Date(lastUpdatedAt).toLocaleTimeString()}</Text>
      ) : null}
      <View style={styles.flex}>
        <MessageList messages={messages} />
      </View>
      <View style={styles.composer}>
        <TextInput
          style={styles.input}
          value={draft.text}
          onChangeText={draft.update}
          placeholder="Message"
          multiline
          accessibilityLabel="Message"
        />
        <Pressable accessibilityRole="button" onPress={() => void onSend()} disabled={!draft.text.trim()} style={styles.send}>
          <Text style={styles.sendText}>Send</Text>
        </Pressable>
      </View>
    </KeyboardAvoidingView>
  );
}

export default function Screen() {
  return (
    <ScreenErrorBoundary>
      <ConversationScreen />
    </ScreenErrorBoundary>
  );
}

const styles = StyleSheet.create({
  flex: { flex: 1 },
  center: { flex: 1, alignItems: 'center', justifyContent: 'center', gap: 12, padding: 24 },
  error: { fontSize: 16, textAlign: 'center' },
  link: { color: '#1D4ED8', fontWeight: '600' },
  stale: { textAlign: 'center', color: '#6B7280', fontSize: 12, paddingVertical: 4 },
  composer: { flexDirection: 'row', alignItems: 'flex-end', gap: 8, padding: 8, borderTopWidth: StyleSheet.hairlineWidth },
  input: { flex: 1, minHeight: 44, maxHeight: 140, borderRadius: 12, borderWidth: 1, borderColor: '#D1D5DB', paddingHorizontal: 12, paddingVertical: 8 },
  send: { minHeight: 44, minWidth: 64, alignItems: 'center', justifyContent: 'center', borderRadius: 12, backgroundColor: '#1D4ED8' },
  sendText: { color: '#FFFFFF', fontWeight: '600' },
});
