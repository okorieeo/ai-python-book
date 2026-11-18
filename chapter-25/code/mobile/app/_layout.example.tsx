// Merge into your root app/_layout.tsx from Chapter 23/24. Shown whole so the order is clear.
import { useIsRestoring } from '@tanstack/react-query';
import { PersistQueryClientProvider } from '@tanstack/react-query-persist-client';
import { Stack } from 'expo-router';
import * as SplashScreen from 'expo-splash-screen';
import { useEffect } from 'react';
import { View } from 'react-native';
import { OfflineBanner } from '../components/OfflineBanner';
import { ScreenErrorBoundary } from '../components/ScreenErrorBoundary';
import { useOutboxFlusher } from '../hooks/useOutboxFlusher';
import { useOutboxItems } from '../hooks/useOutbox';
import { configureApi } from '../lib/api/client';
import { installGlobalErrorHandler } from '../lib/crash/globalHandler';
import { initCrashReporting, reportError } from '../lib/crash/sentry';
import { setupNetworkManagers } from '../lib/net/setupManagers';
import { persistOptions, queryClient } from '../lib/query/client';

const API_URL = process.env.EXPO_PUBLIC_API_URL ?? 'http://localhost:8000/api/v1';

// Module scope: runs once, before the first render.
initCrashReporting();
installGlobalErrorHandler((error) => reportError(error));
configureApi({ baseUrl: API_URL, getToken: async () => null /* your Chapter 24 token store */ });
setupNetworkManagers(API_URL);
void SplashScreen.preventAutoHideAsync(); // keep the splash up until the saved cache is loaded

function AppShell() {
  const isRestoring = useIsRestoring();
  const queued = useOutboxItems();
  useOutboxFlusher();

  useEffect(() => {
    if (!isRestoring) SplashScreen.hide(); // saved conversations are ready: no empty flash
  }, [isRestoring]);

  if (isRestoring) return null;
  return (
    <View style={{ flex: 1 }}>
      <OfflineBanner pendingCount={queued.filter((i) => i.status === 'pending').length} />
      <Stack />
    </View>
  );
}

export default function RootLayout() {
  return (
    <ScreenErrorBoundary>
      <PersistQueryClientProvider client={queryClient} persistOptions={persistOptions}>
        <AppShell />
      </PersistQueryClientProvider>
    </ScreenErrorBoundary>
  );
}
