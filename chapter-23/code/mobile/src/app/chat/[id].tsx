import { Stack, useLocalSearchParams } from 'expo-router';
import { useEffect, useRef, useState } from 'react';
import { ActivityIndicator, FlatList, KeyboardAvoidingView, Platform, StyleSheet, View } from 'react-native';

import { Composer } from '@/components/composer';
import { MessageBubble } from '@/components/message-bubble';
import { ThemedText } from '@/components/themed-text';
import { ThemedView } from '@/components/themed-view';
import { Spacing } from '@/constants/theme';
import { getConversation, sendMessage } from '@/lib/data';
import type { ConversationWithMessages, Message } from '@/lib/types';

export default function ChatScreen() {
  // The [id] in the file name becomes a parameter.
  const { id } = useLocalSearchParams<{ id: string }>();
  // undefined = still loading, null = no such conversation
  const [conversation, setConversation] = useState<ConversationWithMessages | null | undefined>(undefined);

  useEffect(() => {
    let active = true; // ignore the answer if we left the screen meanwhile
    getConversation(id)
      .then((result) => active && setConversation(result))
      .catch(() => active && setConversation(null));
    return () => {
      active = false;
    };
  }, [id]);

  if (conversation === undefined) {
    return (
      <ThemedView style={styles.centered}>
        <ActivityIndicator accessibilityLabel="Loading conversation" />
      </ThemedView>
    );
  }
  if (conversation === null) {
    return (
      <ThemedView style={styles.centered}>
        <Stack.Screen options={{ title: 'Not found' }} />
        <ThemedText type="subtitle">Conversation not found</ThemedText>
      </ThemedView>
    );
  }
  return (
    <>
      {/* Set the native header's title from inside the screen. */}
      <Stack.Screen options={{ title: conversation.title }} />
      <ChatView key={conversation.id} conversationId={conversation.id} initialMessages={conversation.messages} />
    </>
  );
}

function ChatView({ conversationId, initialMessages }: { conversationId: string; initialMessages: Message[] }) {
  const [messages, setMessages] = useState<Message[]>(initialMessages);
  const [draft, setDraft] = useState('');
  const [sending, setSending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const listRef = useRef<FlatList<Message>>(null);

  async function handleSend() {
    const content = draft.trim();
    if (!content || sending) return;
    setError(null);
    setSending(true);
    setDraft('');
    // Optimistic update, exactly as in the web chat: show it now, undo if it fails.
    const optimistic: Message = { id: -Date.now(), role: 'user', content, createdAt: new Date().toISOString() };
    setMessages((current) => [...current, optimistic]);
    try {
      const { userMessage, assistantMessage } = await sendMessage(conversationId, content);
      setMessages((current) => [...current.filter((m) => m.id !== optimistic.id), userMessage, assistantMessage]);
    } catch {
      setMessages((current) => current.filter((m) => m.id !== optimistic.id));
      setDraft(content);
      setError('Your message was not sent. Please try again.');
    } finally {
      setSending(false);
    }
  }

  return (
    <ThemedView style={styles.screen}>
      <KeyboardAvoidingView
        style={styles.screen}
        behavior={Platform.OS === 'ios' ? 'padding' : 'height'}
        keyboardVerticalOffset={Platform.OS === 'ios' ? 96 : 0}>
        <FlatList
          ref={listRef}
          data={messages}
          keyExtractor={(message) => String(message.id)}
          renderItem={({ item }) => <MessageBubble message={item} pending={item.id < 0} />}
          ItemSeparatorComponent={() => <View style={styles.separator} />}
          ListEmptyComponent={
            <ThemedText themeColor="textSecondary" style={styles.empty}>
              No messages yet. Say hello!
            </ThemedText>
          }
          onContentSizeChange={() => listRef.current?.scrollToEnd({ animated: true })}
          keyboardShouldPersistTaps="handled"
          contentContainerStyle={styles.list}
          style={styles.screen}
        />
        {sending && (
          <ThemedText type="small" themeColor="textSecondary" style={styles.status} accessibilityLiveRegion="polite">
            The assistant is typing…
          </ThemedText>
        )}
        {error && (
          <ThemedText type="small" themeColor="danger" style={styles.status} accessibilityRole="alert">
            {error}
          </ThemedText>
        )}
        <Composer value={draft} onChangeText={setDraft} onSubmit={handleSend} busy={sending} />
      </KeyboardAvoidingView>
    </ThemedView>
  );
}

const styles = StyleSheet.create({
  screen: { flex: 1 },
  centered: { flex: 1, alignItems: 'center', justifyContent: 'center', padding: Spacing.four },
  list: { padding: Spacing.three, flexGrow: 1 },
  separator: { height: Spacing.two },
  empty: { textAlign: 'center', paddingTop: Spacing.five },
  status: { paddingHorizontal: Spacing.three, paddingBottom: Spacing.two },
});
