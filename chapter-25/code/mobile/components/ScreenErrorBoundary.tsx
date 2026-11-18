import type { ReactNode } from 'react';
import { ErrorBoundary } from 'react-error-boundary';
import { reportError } from '../lib/crash/sentry';
import { ErrorFallback } from './ErrorFallback';

/**
 * Wrap each screen (and the whole app) in one. A crash while rendering then replaces only that
 * screen with a fallback. Error boundaries catch errors in rendering, not in event handlers or
 * async code: those need try/catch and the global handler.
 */
export function ScreenErrorBoundary({ children, resetKeys }: { children: ReactNode; resetKeys?: unknown[] }) {
  return (
    <ErrorBoundary FallbackComponent={ErrorFallback} onError={(error) => reportError(error)} resetKeys={resetKeys}>
      {children}
    </ErrorBoundary>
  );
}
