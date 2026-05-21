'use client';

import { useEffect, useRef, useState } from 'react';

/**
 * Leading + trailing edge throttle for a frequently-changing value.
 *
 * Use case: wavesurfer `audioprocess` fires ~60Hz, driving `currentTime` updates
 * downstream. TranscriptViewer recomputes `activeIdx` (O(N) findIndex) on every
 * value change. Long transcripts × 60Hz = wasted CPU + janky smooth-scroll.
 * Throttling the value upstream to ~10Hz keeps the UI responsive without
 * sacrificing perceptible highlight precision.
 *
 * Behaviour:
 *   - leading edge: emit the first value immediately
 *   - within `intervalMs`: subsequent updates are coalesced; the most recent
 *     value is emitted via a trailing timer aligned to the window boundary
 *   - cleanup on unmount: pending timer is cleared, no setState on unmounted hook
 */
export function useThrottledValue<T>(value: T, intervalMs: number): T {
  const [throttled, setThrottled] = useState<T>(value);
  const lastEmitTsRef = useRef<number>(Date.now());
  const pendingTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const latestValueRef = useRef<T>(value);

  latestValueRef.current = value;

  useEffect(() => {
    const now = Date.now();
    const elapsed = now - lastEmitTsRef.current;

    if (elapsed >= intervalMs) {
      lastEmitTsRef.current = now;
      setThrottled(value);
      return;
    }

    if (pendingTimerRef.current !== null) {
      clearTimeout(pendingTimerRef.current);
    }
    pendingTimerRef.current = setTimeout(() => {
      lastEmitTsRef.current = Date.now();
      setThrottled(latestValueRef.current);
      pendingTimerRef.current = null;
    }, intervalMs - elapsed);
  }, [value, intervalMs]);

  useEffect(() => {
    return () => {
      if (pendingTimerRef.current !== null) {
        clearTimeout(pendingTimerRef.current);
        pendingTimerRef.current = null;
      }
    };
  }, []);

  return throttled;
}
