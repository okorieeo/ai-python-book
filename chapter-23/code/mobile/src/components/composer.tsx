import { Pressable, StyleSheet, Text, TextInput, View } from 'react-native';

import { Spacing } from '@/constants/theme';
import { useTheme } from '@/hooks/use-theme';

interface ComposerProps {
  value: string;
  onChangeText: (text: string) => void;
  onSubmit: () => void;
  /** true while a message is being sent */
  busy?: boolean;
}

export function Composer({ value, onChangeText, onSubmit, busy = false }: ComposerProps) {
  const theme = useTheme();
  const canSend = value.trim() !== '' && !busy;
  return (
    <View style={[styles.bar, { borderTopColor: theme.border, backgroundColor: theme.background }]}>
      <TextInput
        value={value}
        onChangeText={onChangeText}
        placeholder="Write a message…"
        placeholderTextColor={theme.textSecondary}
        accessibilityLabel="Message"
        multiline
        style={[styles.input, { color: theme.text, borderColor: theme.inputBorder }]}
      />
      <Pressable
        onPress={onSubmit}
        disabled={!canSend}
        accessibilityRole="button"
        accessibilityLabel="Send"
        accessibilityState={{ disabled: !canSend }}
        hitSlop={8}
        style={({ pressed }) => [
          styles.send,
          { backgroundColor: theme.primary },
          !canSend && styles.sendDisabled,
          pressed && styles.sendPressed,
        ]}>
        <Text style={[styles.sendText, { color: theme.onPrimary }]}>Send</Text>
      </Pressable>
    </View>
  );
}

const styles = StyleSheet.create({
  bar: {
    flexDirection: 'row',
    alignItems: 'flex-end',
    gap: Spacing.two,
    padding: Spacing.three,
    borderTopWidth: StyleSheet.hairlineWidth,
  },
  input: {
    flex: 1,
    maxHeight: 120,
    minHeight: 44,
    borderWidth: 1,
    borderRadius: Spacing.two,
    paddingHorizontal: Spacing.three,
    paddingVertical: Spacing.two,
    fontSize: 16,
  },
  send: {
    minHeight: 44, // a comfortable touch target
    minWidth: 64,
    alignItems: 'center',
    justifyContent: 'center',
    borderRadius: Spacing.two,
    paddingHorizontal: Spacing.three,
  },
  sendDisabled: { opacity: 0.4 },
  sendPressed: { opacity: 0.8 },
  sendText: { fontSize: 16, fontWeight: '600' },
});
