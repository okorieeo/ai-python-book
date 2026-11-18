export interface Reading {
  x: number;
  y: number;
  z: number;
}

/** Strength of the acceleration in g. A phone lying still reads about 1 g: gravity is part of the measurement. */
export const magnitude = ({ x, y, z }: Reading): number => Math.sqrt(x * x + y * y + z * z);

/** Smooths noisy readings: each new value moves the output a fraction `alpha` of the way. Small alpha = smoother, slower. */
export class LowPassFilter {
  private value: number | null = null;
  constructor(private readonly alpha: number) {
    if (!(alpha > 0 && alpha <= 1)) throw new Error('alpha must be greater than 0 and at most 1');
  }
  next(sample: number): number {
    this.value = this.value === null ? sample : this.value + this.alpha * (sample - this.value);
    return this.value;
  }
}

export interface ShakeOptions {
  /** How far from 1 g counts as a hard movement. */
  deltaG?: number;
  /** Hard movements needed inside the window. */
  spikesRequired?: number;
  windowMs?: number;
  cooldownMs?: number;
}

/**
 * "Shake to report a problem". A shake is several hard movements in a short time: one bump in a pocket is
 * not enough, and slowly tilting the phone never changes the strength of the acceleration at all.
 */
export class ShakeDetector {
  private spikes: number[] = [];
  private wasHard = false;
  private lastShakeAt = -Infinity;

  constructor(private readonly options: ShakeOptions = {}) {}

  /** Feed every reading with the time it was taken. Returns true at the moment a shake is recognised. */
  push(reading: Reading, nowMs: number): boolean {
    const { deltaG = 0.8, spikesRequired = 3, windowMs = 700, cooldownMs = 1500 } = this.options;
    const hard = Math.abs(magnitude(reading) - 1) >= deltaG;
    const rising = hard && !this.wasHard; // count each movement once, not every reading inside it
    this.wasHard = hard;
    if (!rising) return false;

    this.spikes = [...this.spikes.filter((t) => nowMs - t <= windowMs), nowMs];
    if (this.spikes.length >= spikesRequired && nowMs - this.lastShakeAt >= cooldownMs) {
      this.lastShakeAt = nowMs;
      this.spikes = [];
      return true;
    }
    return false;
  }
}
