import Constants from 'expo-constants';
import { Link } from 'expo-router';
import { useState } from 'react';
import { StyleSheet, Switch, View } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';

import { ThemedText } from '@/components/themed-text';
import { ThemedView } from '@/components/themed-view';
import { BottomTabInset, Spacing } from '@/constants/theme';
import { useTheme } from '@/hooks/use-theme';

export default function SettingsScreen() {
  const theme = useTheme();
  const [notifications, setNotifications] = useState(true);

  return (
    <ThemedView style={styles.screen}>
      <SafeAreaView style={styles.safeArea} edges={['top', 'left', 'right']}>
        <ThemedText type="subtitle" accessibilityRole="header" style={styles.title}>
          Settings
        </ThemedText>

        <ThemedView type="backgroundElement" style={styles.card}>
          <View style={styles.row}>
            <ThemedText nativeID="notifications-label">Notifications</ThemedText>
            <Switch
              value={notifications}
              onValueChange={setNotifications}
              accessibilityLabel="Notifications"
              trackColor={{ true: theme.primary }}
            />
          </View>
          <View style={styles.row}>
            <ThemedText>Appearance</ThemedText>
            <ThemedText themeColor="textSecondary">Follows your device</ThemedText>
          </View>
        </ThemedView>

        <View style={styles.footer}>
          <Link href="https://example.com/privacy" accessibilityRole="link">
            <ThemedText type="linkPrimary">Privacy policy</ThemedText>
          </Link>
          <ThemedText type="small" themeColor="textSecondary">
            Version {Constants.expoConfig?.version ?? '1.0.0'}
          </ThemedText>
        </View>
      </SafeAreaView>
    </ThemedView>
  );
}

const styles = StyleSheet.create({
  screen: { flex: 1 },
  safeArea: { flex: 1, paddingHorizontal: Spacing.three, paddingBottom: BottomTabInset },
  title: { paddingVertical: Spacing.three },
  card: { borderRadius: Spacing.three, paddingHorizontal: Spacing.three },
  row: {
    minHeight: 56,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
  },
  footer: { marginTop: Spacing.four, gap: Spacing.two },
});
