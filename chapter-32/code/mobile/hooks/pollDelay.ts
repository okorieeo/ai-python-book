/** Wait a little longer each time we ask: 1 s, 1.5 s, 2 s ... up to 5 s. Work usually finishes in a few seconds. */
export const nextPollDelay = (attempt: number): number => Math.min(5000, 1000 + attempt * 500);
