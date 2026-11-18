import { Pressable, StyleSheet, Text, View } from 'react-native';
import type { ChatMessage } from '../lib/offline/messages';
import { outbox } from '../lib/offline/outboxInstance';

/** Small line under a message: nothing when sent, "Sending…" while queued, actions when it failed. */
export function MessageStatus({ message }: { message: ChatMessage }) {
  if (message.status === 'sent') return null;
  if (message.status === 'sending') return <Text style={styles.note}>Sending…</Text>;

  const id = message.clientId;
  return (
    <View accessibilityRole="alert">
      <Text style={styles.error}>{message.error ?? 'Not sent.'}</Text>
      <View style={styles.row}>
        <Pressable
          accessibilityRole="button"
          onPress={() => id && outbox.retry(id).then(() => outbox.flush({ force: true }))}
          hitSlop={8}
        >
          <Text style={styles.action}>Try again</Text>
        </Pressable>
        <Pressable accessibilityRole="button" onPress={() => id && outbox.discard(id)} hitSlop={8}>
          <Text style={styles.action}>Delete</Text>
        </Pressable>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  note: { fontSize: 12, color: '#6B7280', marginTop: 2 },
  error: { fontSize: 12, color: '#B91C1C', marginTop: 2 },
  row: { flexDirection: 'row', gap: 16, marginTop: 4 },
  action: { fontSize: 13, fontWeight: '600', color: '#1D4ED8' },
});
