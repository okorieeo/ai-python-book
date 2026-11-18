const compact = new Intl.NumberFormat("en", {
  notation: "compact",
  maximumFractionDigits: 1,
});
const whole = new Intl.NumberFormat("en");

export const formatCompact = (n: number) => compact.format(n); // 12400 -> 12.4K
export const formatNumber = (n: number) => whole.format(n); // 12400 -> 12,400

/** "2026-11-03" -> "Nov 3". A calendar day has no time zone, so read it as UTC;
 *  new Date("2026-11-03") shown in a US time zone would say Nov 2. */
export function formatDay(isoDate: string): string {
  return new Date(`${isoDate}T00:00:00Z`).toLocaleDateString("en", {
    month: "short",
    day: "numeric",
    timeZone: "UTC",
  });
}

/** A moment in time, shown in the viewer's own time zone. */
export function formatDateTime(iso: string | null): string {
  if (!iso) return "Never";
  return new Date(iso).toLocaleString("en", {
    dateStyle: "medium",
    timeStyle: "short",
  });
}

export const formatDate = (iso: string) =>
  new Date(iso).toLocaleDateString("en", { dateStyle: "medium" });
