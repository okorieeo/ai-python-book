import * as Sentry from '@sentry/react-native';
import { scrubEvent } from './scrub';

/** Chapter 55 covers the full setup (source maps, releases, alerts). This is the privacy-safe core. */
export function initCrashReporting(): void {
  const dsn = process.env.EXPO_PUBLIC_SENTRY_DSN;
  if (!dsn) return; // development builds without a DSN simply report nothing
  Sentry.init({
    dsn,
    sendDefaultPii: false,
    tracesSampleRate: 0,
    beforeSend: (event) => scrubEvent(event),
  });
}

export const reportError = (error: unknown): void => {
  Sentry.captureException(error);
};
