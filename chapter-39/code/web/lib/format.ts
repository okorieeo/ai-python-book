/**
 * Money and counts as people read them. Amounts travel as integers in the currency's MINOR unit
 * (kobo, cents), exactly as Paystack and Stripe send them; floats never carry money.
 */
export function formatMoney(amountMinor: number, currency: string, locale = "en-US"): string {
  if (!Number.isInteger(amountMinor)) {
    throw new Error("amountMinor must be an integer number of minor units");
  }
  const nf = new Intl.NumberFormat(locale, { style: "currency", currency });
  const digits = nf.resolvedOptions().maximumFractionDigits;      // 2 for NGN and USD, 0 for JPY
  if (digits === undefined) throw new Error(`cannot determine the minor unit of ${currency}`);
  return nf.format(amountMinor / 10 ** digits);
}

export function formatTokens(n: number): string {
  if (!Number.isFinite(n) || n < 0) throw new Error("token count must be a non-negative number");
  if (n < 1_000) return String(Math.round(n));
  if (n < 1_000_000) return `${(n / 1_000).toFixed(1).replace(/\.0$/, "")}K`;
  return `${(n / 1_000_000).toFixed(1).replace(/\.0$/, "")}M`;
}
