import { useEffect, useRef, useState } from "react";

const DEFAULT_DURATION_MS = 1000;

const easeOutCubic = (t: number) => 1 - Math.pow(1 - t, 3);

// Tweens the displayed integer from its previous value to `target` whenever
// `target` changes. Drives the per-DMA marker tick on the live activity map —
// when poll deltas land (e.g. +5 plays in one tick) the badge counts up
// "...87 → 88 → 89 → 90 → 91 → 92" instead of jumping.
export function useCountUp(target: number, durationMs: number = DEFAULT_DURATION_MS): number {
  const [display, setDisplay] = useState(target);
  const fromRef = useRef(target);
  const rafRef = useRef<number | null>(null);

  useEffect(() => {
    if (target === display) return;
    const from = fromRef.current;
    const start = performance.now();

    const tick = (now: number) => {
      const elapsed = now - start;
      const t = Math.min(1, elapsed / durationMs);
      const v = from + (target - from) * easeOutCubic(t);
      setDisplay(t >= 1 ? target : Math.round(v));
      if (t < 1) rafRef.current = requestAnimationFrame(tick);
    };
    rafRef.current = requestAnimationFrame(tick);

    return () => {
      if (rafRef.current !== null) cancelAnimationFrame(rafRef.current);
      fromRef.current = target;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [target, durationMs]);

  return display;
}
