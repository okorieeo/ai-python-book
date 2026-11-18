/** 1900 -> "$19.00". Money is stored as integers (Chapter 7) and formatted last. */
export function formatPrice(cents: number, currency = "USD"): string {
  return new Intl.NumberFormat("en-US", { style: "currency", currency }).format(
    cents / 100,
  );
}

/** 1000000 -> "1M tokens", 250000 -> "250K tokens" */
export function formatTokens(count: number): string {
  if (count >= 1_000_000) return `${count / 1_000_000}M tokens`;
  if (count >= 1_000) return `${count / 1_000}K tokens`;
  return `${count} tokens`;
}
