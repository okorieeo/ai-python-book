export type QueryValue = string | number | boolean | null | undefined | Array<string | number>;

/** Build "?a=1&b=x,y" from an object, skipping empty values. Returns "" when nothing is left. */
export function buildQuery(params: Record<string, QueryValue> = {}): string {
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value === undefined || value === null || value === "") continue;
    if (Array.isArray(value)) {
      if (value.length > 0) search.set(key, value.join(","));
    } else {
      search.set(key, String(value));
    }
  }
  const text = search.toString();
  return text ? `?${text}` : "";
}

export function newIdempotencyKey(): string {
  return globalThis.crypto.randomUUID();
}
