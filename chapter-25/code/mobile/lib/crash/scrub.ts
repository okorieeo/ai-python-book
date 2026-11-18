/** The few parts of a crash report we clean before it leaves the phone. Sentry's event type satisfies this. */
export interface ScrubbableEvent {
  message?: string;
  user?: { email?: string; username?: string; ip_address?: string | null };
  request?: { data?: unknown; cookies?: unknown; headers?: Record<string, unknown> };
  breadcrumbs?: Array<{ message?: string; data?: Record<string, unknown> }>;
}

const BEARER = /Bearer\s+[A-Za-z0-9._~+/-]+=*/g;

export const scrubText = (text: string): string => text.replace(BEARER, 'Bearer [REDACTED]');

/**
 * Crash reports must not become a second copy of the user's conversations (Chapter 17, section 17.12).
 * Keep the user's id, drop everything personal: request bodies, cookies, auth headers, e-mail, address.
 */
export function scrubEvent<T extends ScrubbableEvent>(event: T): T {
  if (event.message) event.message = scrubText(event.message);
  if (event.user) {
    delete event.user.email;
    delete event.user.username;
    delete event.user.ip_address;
  }
  if (event.request) {
    delete event.request.data;
    delete event.request.cookies;
    if (event.request.headers) {
      for (const name of Object.keys(event.request.headers)) {
        if (/^(authorization|cookie|set-cookie)$/i.test(name)) delete event.request.headers[name];
      }
    }
  }
  for (const crumb of event.breadcrumbs ?? []) {
    if (crumb.message) crumb.message = scrubText(crumb.message);
    if (crumb.data) delete crumb.data.request_body;
  }
  return event;
}
