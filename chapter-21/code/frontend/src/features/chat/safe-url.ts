const ALLOWED_PROTOCOLS = new Set(["http:", "https:", "mailto:"]);

/**
 * Model output is untrusted, so a link may only use a protocol we expect. This blocks
 * javascript:, data:, vbscript: and the tricks used to hide them ("java\tscript:").
 * Returns "" for anything unsafe, which react-markdown renders as a link with no target.
 */
export function safeUrl(url: string): string {
  try {
    // The URL parser strips tabs and newlines and lower-cases the scheme, like browsers do.
    const parsed = new URL(url.trim(), "https://placeholder.invalid");
    return ALLOWED_PROTOCOLS.has(parsed.protocol) ? url : "";
  } catch {
    return "";
  }
}
