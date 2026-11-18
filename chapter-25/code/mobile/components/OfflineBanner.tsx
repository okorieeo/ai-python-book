import { useEffect, useState } from 'react';
import { StyleSheet, Text, View } from 'react-native';
import { useConnectivity } from '../hooks/useConnectivity';

/** Wait before changing, so a half-second signal flicker does not make the banner blink. */
function useDelayed(value: boolean, delayOnMs: number, delayOffMs: number): boolean {
  const [shown, setShown] = useState(value);
  useEffect(() => {
    const timer = setTimeout(() => setShown(value), value ? delayOnMs : delayOffMs);
    return () => clearTimeout(timer);
  }, [value, delayOnMs, delayOffMs]);
  return shown;
}

export function OfflineBanner({ pendingCount = 0 }: { pendingCount?: number }) {
  const { online, quality } = useConnectivity();
  const offline = useDelayed(!online, 1500, 0);
  const slow = useDelayed(online && quality === 'poor', 1500, 0);
  if (!offline && !slow) return null;

  const text = offline
    ? pendingCount > 0
      ? `You are offline. ${pendingCount} message${pendingCount === 1 ? '' : 's'} will send when you are back online.`
      : 'You are offline. You can still read your conversations.'
    : 'Your connection is slow. Things may take a little longer.';

  return (
    <View style={[styles.bar, offline ? styles.offline : styles.slow]} accessibilityRole="alert" accessibilityLiveRegion="polite">
      <Text style={styles.text}>{text}</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  bar: { paddingVertical: 8, paddingHorizontal: 16 },
  offline: { backgroundColor: '#92400E' },
  slow: { backgroundColor: '#1E3A8A' },
  text: { color: '#FFFFFF', fontSize: 14, textAlign: 'center' },
});
