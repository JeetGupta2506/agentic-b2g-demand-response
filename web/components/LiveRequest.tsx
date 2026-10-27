'use client';
import { useEffect, useRef, useState } from 'react';
import type { Example } from '@/lib/types';

// Live requests go to the local Python server (python -m b2g.demo.server), which also serves this site.
type Health = { live: boolean; model: string; first_day: string; last_day: string };
type Status = { kind: 'checking' } | { kind: 'offline' } | { kind: 'ready'; h: Health };

const EXAMPLE_TEXT = "I'm leaving at 6:30 tomorrow and need the car at 100%. Keep the room under 26 °C.";

export default function LiveRequest({ onResult }: { onResult: (e: Example) => void }) {
  const [status, setStatus] = useState<Status>({ kind: 'checking' });
  const [day, setDay] = useState('2026-05-06');
  const [text, setText] = useState(EXAMPLE_TEXT);
  const [running, setRunning] = useState(false);
  const [elapsed, setElapsed] = useState(0);
  const [error, setError] = useState('');
  const timer = useRef<ReturnType<typeof setInterval> | null>(null);

  useEffect(() => {
    fetch('/api/health')
      .then((r) => (r.ok ? r.json() : Promise.reject()))
      .then((h: Health) => setStatus({ kind: 'ready', h }))
      .catch(() => setStatus({ kind: 'offline' }));
    return () => { if (timer.current) clearInterval(timer.current); };
  }, []);

  const submit = async (ev: React.FormEvent) => {
    ev.preventDefault();
    setError('');
    setRunning(true);
    setElapsed(0);
    timer.current = setInterval(() => setElapsed((s) => s + 1), 1000);
    try {
      const r = await fetch('/api/plan', {
        method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ date: day, request: text }),
      });
      const data = await r.json().catch(() => ({ error: `The server answered ${r.status}.` }));
      if (!r.ok) setError(data.error ?? `The server answered ${r.status}.`);
      else if (!data.ok) setError(`The agents did not finish: ${data.error ?? 'no plan'}. Try rephrasing the request.`);
      else onResult(data as Example);
    } catch {
      setError('The live server stopped responding. The pre-run examples still work.');
    } finally {
      if (timer.current) clearInterval(timer.current);
      setRunning(false);
    }
  };

  const label = <span className="text-[13px] font-semibold text-ink-muted">Type your own request</span>;
  if (status.kind !== 'ready' || !status.h.live) {
    const hint = status.kind === 'checking' ? 'Checking for the live server…'
      : status.kind === 'offline' ? 'Live mode needs the Python server: run  python -m b2g.demo.server  and open http://localhost:3000'
      : 'Live mode needs an LLM API key in .env.';
    return (
      <div className="flex flex-col gap-1.5 border-t border-line-soft pt-3.5">
        {label}
        <input type="text" disabled aria-label="Type your own request" placeholder={hint}
          className="min-h-11 rounded-xl border border-line bg-ground px-3.5 py-3 text-[15px] text-ink-muted placeholder:text-ink-muted" />
      </div>
    );
  }

  const { h } = status;
  return (
    <form onSubmit={submit} className="flex flex-col gap-2.5 border-t border-line-soft pt-3.5">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        {label}
        <span className="inline-flex items-center gap-1.5 rounded-full bg-green-100 px-2.5 py-0.5 text-xs font-semibold text-green-900">
          <span className="h-1.5 w-1.5 rounded-full bg-green-600" />live · {h.model}
        </span>
      </div>
      <textarea value={text} onChange={(e) => setText(e.target.value)} disabled={running} rows={3} maxLength={600} required minLength={3}
        aria-label="Your request"
        className="rounded-xl border border-line bg-white px-3.5 py-3 text-[15px] leading-[1.45] focus:border-brand focus:outline-none disabled:bg-ground" />
      <div className="flex flex-wrap items-center gap-2.5">
        <label className="flex items-center gap-2 text-sm text-ink-2">
          Day
          <input type="date" value={day} min={h.first_day} max={h.last_day} required disabled={running}
            onChange={(e) => setDay(e.target.value)}
            className="min-h-11 rounded-xl border border-line bg-white px-3 text-[15px] focus:border-brand focus:outline-none" />
        </label>
        <button type="submit" disabled={running}
          className="ml-auto inline-flex min-h-11 items-center gap-2 rounded-xl bg-brand px-[18px] py-3 font-semibold text-white transition hover:bg-brand-dark disabled:opacity-70">
          {running ? 'Planning…' : 'Plan my day'}
        </button>
      </div>
      {running && (
        <p className="animate-pulseSoft text-sm text-ink-muted" aria-live="polite">
          Agents at work: forecast, specialist agents, optimizer, verifier · {elapsed} s (usually 20–60 s)
        </p>
      )}
      {error && <p role="alert" className="rounded-xl bg-amber-50 px-3.5 py-2.5 text-sm text-amber-900">{error}</p>}
    </form>
  );
}
