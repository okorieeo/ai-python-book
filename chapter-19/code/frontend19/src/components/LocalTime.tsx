"use client";

import { useHydrated } from "@/hooks/useHydrated";

interface LocalTimeProps {
  iso: string; // an ISO 8601 timestamp in UTC, as sent by the API
  timeZone?: string; // defaults to the viewer's own time zone
  className?: string;
}

/**
 * Shows a UTC timestamp in the viewer's time zone without hydration errors:
 * the server (and the first browser render) show a stable UTC time, then the
 * browser switches to local time.
 */
export function LocalTime({ iso, timeZone, className }: LocalTimeProps) {
  const hydrated = useHydrated();
  const date = new Date(iso);
  const text = new Intl.DateTimeFormat("en", {
    hour: "numeric",
    minute: "2-digit",
    timeZone: hydrated ? timeZone : "UTC",
    timeZoneName: hydrated ? undefined : "short",
  }).format(date);
  return (
    <time dateTime={iso} className={className}>
      {text}
    </time>
  );
}
