import { Accelerometer } from 'expo-sensors';
import { useEffect } from 'react';
import { ShakeDetector } from '../lib/cv/sensors';

/**
 * Calls `onShake` when the phone is shaken. Sensors cost battery, so we listen only while the screen that
 * wants shakes is mounted and ask for 10 readings a second, which is plenty for a human movement.
 */
export function useShake(onShake: () => void, enabled = true): void {
  useEffect(() => {
    if (!enabled) return;
    let subscription: { remove: () => void } | null = null;
    let cancelled = false;
    const detector = new ShakeDetector();

    void Accelerometer.isAvailableAsync().then((available) => {
      if (!available || cancelled) return;
      Accelerometer.setUpdateInterval(100);
      subscription = Accelerometer.addListener((reading) => {
        if (detector.push(reading, Date.now())) onShake();
      });
    });
    return () => {
      cancelled = true;
      subscription?.remove();
    };
  }, [onShake, enabled]);
}
