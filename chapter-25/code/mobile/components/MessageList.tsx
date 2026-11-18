import { FlashList } from '@shopify/flash-list';
import { memo } from 'react';
import { StyleSheet, Text, View } from 'react-native';
import type { ChatMessage } from '../lib/offline/messages';
import { MessageStatus } from './MessageStatus';

const MessageRow = memo(function MessageRow({ message }: { message: ChatMessage }) {
  const mine = message.role === 'user';
  return (
    <View style={[styles.row, mine ? styles.mine : styles.theirs]}>
      <View style={[styles.bubble, mine ? styles.mineBubble : styles.theirsBubble, message.status === 'sending' && styles.dim]}>
        <Text style={mine ? styles.mineText : styles.theirsText}>{message.content}</Text>
      </View>
      <MessageStatus message={message} />
    </View>
  );
});

export function MessageList({ messages }: { messages: ChatMessage[] }) {
  return (
    <FlashList
      data={messages}
      keyExtractor={(m) => m.key}
      renderItem={({ item }) => <MessageRow message={item} />}
      maintainVisibleContentPosition={{ startRenderingFromBottom: true, autoscrollToBottomThreshold: 0.2 }}
      keyboardShouldPersistTaps="handled"
    />
  );
}

const styles = StyleSheet.create({
  row: { paddingHorizontal: 12, paddingVertical: 4 },
  mine: { alignItems: 'flex-end' },
  theirs: { alignItems: 'flex-start' },
  bubble: { maxWidth: '85%', borderRadius: 16, paddingVertical: 8, paddingHorizontal: 12 },
  mineBubble: { backgroundColor: '#1D4ED8' },
  theirsBubble: { backgroundColor: '#E5E7EB' },
  dim: { opacity: 0.6 },
  mineText: { color: '#FFFFFF', fontSize: 16 },
  theirsText: { color: '#111827', fontSize: 16 },
});
