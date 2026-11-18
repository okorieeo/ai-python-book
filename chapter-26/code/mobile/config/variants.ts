/**
 * App variants: the same code, installed side by side with different identities.
 * Pure TypeScript (no Expo imports) so it can be tested without a device.
 */
export type VariantName = "development" | "preview" | "production";

export interface Variant {
  name: VariantName;
  appName: string;
  /** iOS bundle identifier AND Android application id. */
  bundleId: string;
  /** Deep-link scheme, unique per variant so links open the right build. */
  scheme: string;
}

// REPLACE with a reverse-domain name you own. It can never change after release.
export const BASE_BUNDLE_ID = "com.example.aichat";

export const VARIANTS: Record<VariantName, Variant> = {
  development: {
    name: "development",
    appName: "AI Chat (Dev)",
    bundleId: `${BASE_BUNDLE_ID}.dev`,
    scheme: "aichat-dev",
  },
  preview: {
    name: "preview",
    appName: "AI Chat (Preview)",
    bundleId: `${BASE_BUNDLE_ID}.preview`,
    scheme: "aichat-preview",
  },
  production: {
    name: "production",
    appName: "AI Chat",
    bundleId: BASE_BUNDLE_ID,
    scheme: "aichat",
  },
};

/**
 * Turn the APP_VARIANT environment variable into a variant.
 * Unset means "development" (what you want on your laptop). A value we do not
 * recognise is a typo, and a typo must stop the build, not quietly ship the
 * wrong identity.
 */
export function resolveVariant(raw: string | undefined): Variant {
  if (raw === undefined || raw === "") return VARIANTS.development;
  if (Object.prototype.hasOwnProperty.call(VARIANTS, raw)) {
    return VARIANTS[raw as VariantName];
  }
  throw new Error(
    `Unknown APP_VARIANT "${raw}". Use one of: ${Object.keys(VARIANTS).join(", ")}.`,
  );
}
