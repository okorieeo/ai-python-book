import AsyncStorage from '@react-native-async-storage/async-storage';
import { createAsyncStoragePersister } from '@tanstack/query-async-storage-persister';
import { QueryClient } from '@tanstack/react-query';
import type { PersistQueryClientProviderProps } from '@tanstack/react-query-persist-client';
import Constants from 'expo-constants';
import { CACHE_MAX_AGE_MS, cacheBuster, queryRetry, queryRetryDelay, shouldPersistQuery } from './policy';

export const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 30_000, // fresh for 30 s: no refetch when you hop between screens
      gcTime: CACHE_MAX_AGE_MS, // must be >= the persister's maxAge, or restored data is thrown away
      networkMode: 'offlineFirst', // try once even if NetInfo says offline; pause the retries
      retry: queryRetry,
      retryDelay: queryRetryDelay,
      refetchOnReconnect: true,
    },
  },
});

export const persister = createAsyncStoragePersister({
  storage: AsyncStorage,
  key: 'rq-cache',
  throttleTime: 2_000, // write at most every 2 s, not on every change
});

export const persistOptions: PersistQueryClientProviderProps['persistOptions'] = {
  persister,
  maxAge: CACHE_MAX_AGE_MS,
  buster: cacheBuster(Constants.expoConfig?.version ?? '0'),
  dehydrateOptions: {
    shouldDehydrateQuery: (query) => shouldPersistQuery(query.queryKey, query.state.status),
  },
};
