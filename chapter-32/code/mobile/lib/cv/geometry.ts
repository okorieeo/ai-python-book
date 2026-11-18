export interface Box {
  /** Top-left corner, in pixels. */
  x: number;
  y: number;
  width: number;
  height: number;
}

export interface Detection {
  box: Box;
  /** 0 to 1: how sure the model is. It is NOT a probability you can trust blindly (see section 32.13). */
  score: number;
  label: string;
}

export interface Size {
  width: number;
  height: number;
}

export interface Point {
  x: number;
  y: number;
}

/** Intersection over union: 0 = the boxes do not touch, 1 = identical. The standard way to ask "same object?". */
export function iou(a: Box, b: Box): number {
  const overlapWidth = Math.min(a.x + a.width, b.x + b.width) - Math.max(a.x, b.x);
  const overlapHeight = Math.min(a.y + a.height, b.y + b.height) - Math.max(a.y, b.y);
  if (overlapWidth <= 0 || overlapHeight <= 0) return 0;
  const intersection = overlapWidth * overlapHeight;
  const union = a.width * a.height + b.width * b.height - intersection;
  return union > 0 ? intersection / union : 0;
}

export interface NmsOptions {
  /** Drop detections below this score first. */
  scoreThreshold?: number;
  /** Two boxes of the same label overlapping more than this are the same object: keep the better one. */
  iouThreshold?: number;
  maxDetections?: number;
}

/**
 * Non-maximum suppression. A detector usually reports the same object several times with slightly different
 * boxes. Keep the highest score, drop its near-duplicates, repeat. Only boxes with the SAME label compete:
 * a "cup" box overlapping a "table" box is not a duplicate.
 */
export function nms(detections: Detection[], { scoreThreshold = 0.3, iouThreshold = 0.5, maxDetections = 20 }: NmsOptions = {}): Detection[] {
  const candidates = detections.filter((d) => d.score >= scoreThreshold).sort((a, b) => b.score - a.score);
  const kept: Detection[] = [];
  for (const candidate of candidates) {
    if (kept.length >= maxDetections) break;
    const duplicate = kept.some((k) => k.label === candidate.label && iou(k.box, candidate.box) > iouThreshold);
    if (!duplicate) kept.push(candidate);
  }
  return kept;
}

/**
 * Where does a box found in the CAMERA FRAME appear on the SCREEN? The preview is scaled to fill the view
 * ("cover": the frame is cropped) or to fit inside it ("contain": there are bars). Drawing an overlay
 * without this is the classic bug: the boxes are right in the logs and wrong on screen.
 * `frame` must be the size of the image in DISPLAY orientation (after rotation).
 */
export function mapBoxToView(box: Box, frame: Size, view: Size, fit: 'cover' | 'contain', mirrored = false): Box {
  const scale = fit === 'cover' ? Math.max(view.width / frame.width, view.height / frame.height) : Math.min(view.width / frame.width, view.height / frame.height);
  const offsetX = (view.width - frame.width * scale) / 2;
  const offsetY = (view.height - frame.height * scale) / 2;
  const mapped = { x: box.x * scale + offsetX, y: box.y * scale + offsetY, width: box.width * scale, height: box.height * scale };
  return mirrored ? { ...mapped, x: view.width - (mapped.x + mapped.width) } : mapped; // a selfie camera is mirrored
}

/** Cut a box to the visible area; returns null when nothing of it is visible. */
export function clampBox(box: Box, view: Size): Box | null {
  const left = Math.max(0, box.x);
  const top = Math.max(0, box.y);
  const right = Math.min(view.width, box.x + box.width);
  const bottom = Math.min(view.height, box.y + box.height);
  return right > left && bottom > top ? { x: left, y: top, width: right - left, height: bottom - top } : null;
}

/**
 * expo-camera lists a barcode's corners in a different order on each platform (see its documentation):
 * Android and web: top-left, top-right, bottom-right, bottom-left.
 * iOS: bottom-left, bottom-right, top-left, top-right.
 * Return them in ONE order (top-left, top-right, bottom-right, bottom-left) so the rest of the code does not care.
 */
export function orderCorners(points: Point[], platform: 'ios' | 'android' | 'web'): Point[] {
  if (points.length !== 4) return points; // not available for every code type
  return platform === 'ios' ? [points[2], points[3], points[1], points[0]] : points;
}

/**
 * A detector flickers: a code appears for one frame, vanishes, appears again. Act only when the SAME value has
 * been seen in `framesRequired` frames in a row, and then not again for the same value until `cooldownMs`
 * has passed or it has left the view.
 */
export class StableDetector {
  private candidate: string | null = null;
  private seen = 0;
  private lastFired: string | null = null;
  private lastFiredAt = -Infinity;
  private emptyFrames = 0;

  constructor(
    private readonly options: { framesRequired?: number; cooldownMs?: number; clearAfterEmptyFrames?: number } = {},
  ) {}

  /** Call once per frame with what was seen (or null). Returns the value when it is time to act. */
  update(value: string | null, nowMs: number): string | null {
    const { framesRequired = 3, cooldownMs = 3000, clearAfterEmptyFrames = 5 } = this.options;
    if (value === null) {
      this.candidate = null;
      this.seen = 0;
      if (++this.emptyFrames >= clearAfterEmptyFrames) this.lastFired = null; // it left the view: allow it again
      return null;
    }
    this.emptyFrames = 0;
    this.seen = value === this.candidate ? this.seen + 1 : 1;
    this.candidate = value;
    if (this.seen < framesRequired) return null;
    if (value === this.lastFired && nowMs - this.lastFiredAt < cooldownMs) return null;
    this.lastFired = value;
    this.lastFiredAt = nowMs;
    return value;
  }
}
