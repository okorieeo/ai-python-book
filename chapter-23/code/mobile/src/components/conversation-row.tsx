import { Pressable, StyleSheet, View } from 'react-native';

import { ThemedText } from '@/components/themed-text';
import { Spacing } from '@/constants/theme';
import { useTheme } from '@/hooks/use-theme';
import type { Conversation } from '@/lib/types';

interface ConversationRowProps {
  conversation: Conversation;
  onPress: (id: string) => void;
}

export function ConversationRow({ conversation, onPress }: ConversationRowProps) {
  const theme = useTheme();
  return (
    <Pressable
      onPress={() => onPress(conversation.id)}
      accessibilityRole="button"
      accessibilityLabel={conversation.title}
      accessibilityHint="Opens the conversation"
      // `pressed` is true while the finger is down: the feedback every touch needs.
      style={({ pressed }) => [
        styles.row,
        { backgroundColor: pressed ? theme.backgroundSelected : theme.backgroundElement },
      ]}>
      <View style={styles.texts}>
        <ThemedText type="smallBold" numberOfLines={1}>
          {conversation.title}
        </ThemedText>
        <ThemedText type="small" themeColor="textSecondary" numberOfLines={1}>
          {conversation.lastMessage ?? 'No messages yet'}
        </ThemedText>
      </View>
    </Pressable>
  );
}

const styles = StyleSheet.create({
  row: {
    minHeight: 64,
    justifyContent: 'center',
    borderRadius: Spacing.three,
    paddingHorizontal: Spacing.three,
    paddingVertical: Spacing.two,
  },
  texts: { gap: Spacing.half },
});
