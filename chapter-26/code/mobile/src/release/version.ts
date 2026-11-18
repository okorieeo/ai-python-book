/**
 * Tiny semantic-version helpers for the store-facing version ("1.4.2").
 * Strict on purpose: three numbers, nothing else. The build number / version
 * code is a different thing and never goes through here.
 */
export type Version = readonly [major: number, minor: number, patch: number];

const VERSION_RE = /^(\d{1,6})\.(\d{1,6})\.(\d{1,6})$/;

export function parseVersion(text: string): Version {
  const match = VERSION_RE.exec(text.trim());
  if (!match) {
    throw new Error(`Not a valid x.y.z version: "${text}"`);
  }
  return [Number(match[1]), Number(match[2]), Number(match[3])];
}

/** Returns -1 if a < b, 0 if equal, 1 if a > b. */
export function compareVersions(a: string, b: string): -1 | 0 | 1 {
  const left = parseVersion(a);
  const right = parseVersion(b);
  for (let i = 0; i < 3; i += 1) {
    if (left[i] < right[i]) return -1;
    if (left[i] > right[i]) return 1;
  }
  return 0;
}

export function isOlderThan(version: string, minimum: string): boolean {
  return compareVersions(version, minimum) === -1;
}
