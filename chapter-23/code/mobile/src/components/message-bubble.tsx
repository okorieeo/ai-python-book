import { StyleSheet, Text, View } from 'react-native';

import { Spacing } from '@/constants/theme';
import { useTheme } from '@/hooks/use-theme';
import type { Message } from '@/lib/types';

interface MessageBubbleProps {
  message: Pick<Message, 'role' | 'content'>;
  /** true while the message is on its way to the server */
  pending?: boolean;
}

export function MessageBubble({ message, pending = false }: MessageBubbleProps) {
  const theme = useTheme();
  const isUser = message.role === 'user';
  return (
    <View style={[styles.row, isUser ? styles.rowUser : styles.rowAssistant]}>
      <View
        // One element for a screen reader: "You: Hello" instead of two stops.
        accessible
        accessibilityLabel={`${isUser ? 'You' : 'Assistant'}: ${message.content}`}
        style={[
          styles.bubble,
          { backgroundColor: isUser ? theme.primary : theme.backgroundElement },
          pending && styles.pending,
        ]}>
        <Text style={[styles.text, { color: isUser ? theme.onPrimary : theme.text }]}>{message.content}</Text>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  row: { flexDirection: 'row' },
  rowUser: { justifyContent: 'flex-end' },
  rowAssistant: { justifyContent: 'flex-start' },
  bubble: {
    maxWidth: '85%',
    borderRadius: Spacing.three,
    paddingHorizontal: Spacing.three,
    paddingVertical: Spacing.two,
  },
  pending: { opacity: 0.6 },
  text: { fontSize: 16, lineHeight: 22 },
});
