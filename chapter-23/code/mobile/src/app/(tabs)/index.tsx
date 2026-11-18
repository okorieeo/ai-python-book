import { router } from 'expo-router';
import { useState } from 'react';
import { ActivityIndicator, FlatList, Pressable, RefreshControl, StyleSheet, View } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';

import { ConversationRow } from '@/components/conversation-row';
import { ThemedText } from '@/components/themed-text';
import { ThemedView } from '@/components/themed-view';
import { BottomTabInset, Spacing } from '@/constants/theme';
import { useConversations } from '@/hooks/use-conversations';
import { useTheme } from '@/hooks/use-theme';
import { createConversation } from '@/lib/data';

export default function ChatsScreen() {
  const theme = useTheme();
  const { conversations, loading, refreshing, error, refresh, retry } = useConversations();
  const [creating, setCreating] = useState(false);

  async function startNewChat() {
    setCreating(true);
    try {
      const { id } = await createConversation();
      router.push({ pathname: '/chat/[id]', params: { id } });
    } finally {
      setCreating(false);
    }
  }

  return (
    <ThemedView style={styles.screen}>
      <SafeAreaView style={styles.safeArea} edges={['top', 'left', 'right']}>
        <View style={styles.header}>
          <ThemedText type="subtitle" accessibilityRole="header">
            Chats
          </ThemedText>
          <Pressable
            onPress={startNewChat}
            disabled={creating}
            accessibilityRole="button"
            accessibilityLabel="New chat"
            style={[styles.newButton, { backgroundColor: theme.primary }, creating && styles.disabled]}>
            <ThemedText type="smallBold" themeColor="onPrimary">
              {creating ? 'Opening…' : 'New'}
            </ThemedText>
          </Pressable>
        </View>

        {loading ? (
          <ActivityIndicator accessibilityLabel="Loading conversations" style={styles.centered} />
        ) : error ? (
          <View style={styles.centered}>
            <ThemedText themeColor="danger">{error}</ThemedText>
            <Pressable onPress={retry} accessibilityRole="button" style={styles.retry}>
              <ThemedText type="linkPrimary">Try again</ThemedText>
            </Pressable>
          </View>
        ) : (
          <FlatList
            data={conversations}
            keyExtractor={(conversation) => conversation.id}
            renderItem={({ item }) => (
              <ConversationRow
                conversation={item}
                onPress={(id) => router.push({ pathname: '/chat/[id]', params: { id } })}
              />
            )}
            ItemSeparatorComponent={() => <View style={styles.separator} />}
            ListEmptyComponent={
              <ThemedText themeColor="textSecondary" style={styles.empty}>
                No conversations yet. Tap New to start one.
              </ThemedText>
            }
            refreshControl={<RefreshControl refreshing={refreshing} onRefresh={refresh} />}
            contentContainerStyle={styles.list}
          />
        )}
      </SafeAreaView>
    </ThemedView>
  );
}

const styles = StyleSheet.create({
  screen: { flex: 1 },
  safeArea: { flex: 1, paddingHorizontal: Spacing.three },
  header: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    paddingVertical: Spacing.three,
  },
  newButton: {
    minHeight: 44,
    minWidth: 64,
    alignItems: 'center',
    justifyContent: 'center',
    borderRadius: Spacing.two,
    paddingHorizontal: Spacing.three,
  },
  disabled: { opacity: 0.5 },
  list: { paddingBottom: BottomTabInset + Spacing.three },
  separator: { height: Spacing.two },
  centered: { flex: 1, alignItems: 'center', justifyContent: 'center', gap: Spacing.two },
  retry: { minHeight: 44, justifyContent: 'center' },
  empty: { textAlign: 'center', paddingTop: Spacing.five },
});
