export type ScanResult = { ok: true; url: string } | { ok: false; reason: string };

/**
 * A QR code is text that a stranger chose. Treat it like any other untrusted input: only open web addresses
 * on HTTPS that belong to a host you list, with no hidden user name and no surprises. (We parse by hand because
 * React Native's built-in URL class does not implement everything browsers do.)
 */
export function parseScannedUrl(data: string, allowedHosts: string[]): ScanResult {
  const text = data.trim();
  if (text.length === 0 || text.length > 2048) return { ok: false, reason: 'empty or too long' };
  if (/[\u0000-\u001f\u007f\s]/.test(text)) return { ok: false, reason: 'contains control characters or spaces' };

  const match = /^https:\/\/([^/?#]*)([/?#].*)?$/i.exec(text);
  if (!match) return { ok: false, reason: 'not an https address' };

  const authority = match[1];
  if (authority.includes('@')) return { ok: false, reason: 'contains a user name' };
  const [host, port, ...extra] = authority.toLowerCase().split(':');
  if (extra.length > 0 || (port !== undefined && port !== '443')) return { ok: false, reason: 'unusual port' };
  if (!/^[a-z0-9]([a-z0-9-]*[a-z0-9])?(\.[a-z0-9]([a-z0-9-]*[a-z0-9])?)+$/.test(host)) return { ok: false, reason: 'not a plain host name' };

  const allowed = allowedHosts.some((h) => host === h.toLowerCase() || host.endsWith(`.${h.toLowerCase()}`));
  return allowed ? { ok: true, url: text } : { ok: false, reason: 'host is not on the allow-list' };
}
