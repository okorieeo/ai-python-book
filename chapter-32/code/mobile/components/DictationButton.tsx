import { ActivityIndicator, Pressable, StyleSheet, Text, View } from 'react-native';
import { Linking } from 'react-native';
import { useDictation } from '../hooks/useDictation';

/** A microphone button for the composer. Tap to talk, tap again to stop; the words land in the text box. */
export function DictationButton({ onText }: { onText: (text: string) => void }) {
  const { state, press, cancel } = useDictation(onText);
  const busy = state.phase === 'asking' || state.phase === 'uploading';
  const label = state.phase === 'recording' ? `Stop recording, ${state.seconds} seconds` : 'Dictate a message';

  return (
    <View>
      <View style={styles.row}>
        <Pressable accessibilityRole="button" accessibilityLabel={label} disabled={busy} onPress={press} style={[styles.button, state.phase === 'recording' && styles.recording]}>
          {busy ? <ActivityIndicator color="#FFFFFF" /> : <Text style={styles.icon}>{state.phase === 'recording' ? '■' : '🎤'}</Text>}
        </Pressable>
        {state.phase === 'recording' ? (
          <>
            <Text accessibilityLiveRegion="polite" style={styles.timer}>{`0:${String(state.seconds).padStart(2, '0')}`}</Text>
            <Pressable accessibilityRole="button" onPress={cancel} hitSlop={8}>
              <Text style={styles.cancel}>Cancel</Text>
            </Pressable>
          </>
        ) : null}
      </View>
      {state.phase === 'error' && state.error ? (
        <View accessibilityRole="alert">
          <Text style={styles.error}>{state.error.message}</Text>
          {state.error.needsSettings ? (
            <Pressable accessibilityRole="button" onPress={() => void Linking.openSettings()}>
              <Text style={styles.cancel}>Open Settings</Text>
            </Pressable>
          ) : null}
        </View>
      ) : null}
    </View>
  );
}

const styles = StyleSheet.create({
  row: { flexDirection: 'row', alignItems: 'center', gap: 12 },
  button: { width: 48, height: 48, borderRadius: 24, alignItems: 'center', justifyContent: 'center', backgroundColor: '#1D4ED8' },
  recording: { backgroundColor: '#B91C1C' },
  icon: { fontSize: 20, color: '#FFFFFF' },
  timer: { fontVariant: ['tabular-nums'], fontSize: 16 },
  cancel: { color: '#1D4ED8', fontWeight: '600' },
  error: { color: '#B91C1C', fontSize: 13, marginTop: 4 },
});
