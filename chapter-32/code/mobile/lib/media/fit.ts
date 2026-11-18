export interface Size {
  width: number;
  height: number;
}

/** The size that fits inside `maxEdge` on the long side, same shape, never larger than the original. */
export function fitWithin(width: number, height: number, maxEdge: number): Size {
  if (width <= 0 || height <= 0) throw new Error('an image needs a positive size');
  const longest = Math.max(width, height);
  if (longest <= maxEdge) return { width, height };
  const scale = maxEdge / longest;
  return { width: Math.max(1, Math.round(width * scale)), height: Math.max(1, Math.round(height * scale)) };
}
