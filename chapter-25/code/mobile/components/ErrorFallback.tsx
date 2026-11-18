import { Pressable, StyleSheet, Text, View } from 'react-native';
import type { FallbackProps } from 'react-error-boundary';

/** What the user sees instead of a blank screen or a crash. No error text: it is for developers, not users. */
export function ErrorFallback({ resetErrorBoundary }: FallbackProps) {
  return (
    <View style={styles.box} accessibilityRole="alert">
      <Text style={styles.title}>Something went wrong on this screen</Text>
      <Text style={styles.body}>The rest of the app is fine. Your messages are safe.</Text>
      <Pressable accessibilityRole="button" onPress={resetErrorBoundary} style={styles.button}>
        <Text style={styles.buttonText}>Try again</Text>
      </Pressable>
    </View>
  );
}

const styles = StyleSheet.create({
  box: { flex: 1, alignItems: 'center', justifyContent: 'center', padding: 24, gap: 12 },
  title: { fontSize: 18, fontWeight: '700', textAlign: 'center' },
  body: { fontSize: 14, color: '#4B5563', textAlign: 'center' },
  button: { backgroundColor: '#1D4ED8', paddingVertical: 10, paddingHorizontal: 20, borderRadius: 8 },
  buttonText: { color: '#FFFFFF', fontWeight: '600' },
});
