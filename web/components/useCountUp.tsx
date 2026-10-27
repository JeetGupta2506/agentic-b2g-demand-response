'use client';
import { useEffect, useRef, useState } from 'react';

/** Counts from 0 to `target` once the element scrolls into view. */
export function useCountUp(target: number, ms = 1100) {
  const ref = useRef<HTMLSpanElement | null>(null);
  // Start at the real value so the static HTML (and any no-JS view) is correct.
  const [value, setValue] = useState(target);
  useEffect(() => {
    const el = ref.current;
    if (!el || typeof IntersectionObserver === 'undefined') return;
    const reduce = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    if (reduce) { setValue(target); return; }
    setValue(0);
    let raf = 0;
    const io = new IntersectionObserver(([entry]) => {
      if (!entry.isIntersecting) return;
      io.disconnect();
      const t0 = performance.now();
      const tick = (t: number) => {
        const k = Math.min(1, (t - t0) / ms);
        setValue(target * (1 - Math.pow(1 - k, 3)));
        if (k < 1) raf = requestAnimationFrame(tick);
      };
      raf = requestAnimationFrame(tick);
    }, { threshold: 0.4 });
    io.observe(el);
    return () => { io.disconnect(); cancelAnimationFrame(raf); };
  }, [target, ms]);
  return { ref, value };
}

export function CountUp({ value, decimals = 0, prefix = '', suffix = '' }: { value: number; decimals?: number; prefix?: string; suffix?: string }) {
  const { ref, value: v } = useCountUp(value);
  return <span ref={ref}>{prefix}{v.toFixed(decimals)}{suffix}</span>;
}
