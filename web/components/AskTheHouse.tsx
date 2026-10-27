'use client';
import { useEffect, useMemo, useRef, useState } from 'react';
import { savingVsRules } from '@/lib/data';
import { constraintGroups, parseAnswer, stepView, verifierWarnings, type AnswerTag, type StepView } from '@/lib/derive';
import { degC, fixed, rupees } from '@/lib/format';
import type { Example } from '@/lib/types';
import DayCharts from './DayCharts';
import { ExampleCards } from './ExamplePicker';
import LiveRequest from './LiveRequest';
import { Icon, SectionHeader } from './ui';

const STEP_TONE: Record<StepView['tone'], { dot: string; card: string; title: string }> = {
  forecast: { dot: '#B45309', card: 'border-line-soft bg-white', title: 'text-ink' },
  calendar: { dot: '#475569', card: 'border-line-soft bg-white', title: 'text-ink' },
  ev: { dot: '#0D9488', card: 'border-line-soft bg-white', title: 'text-ink' },
  battery: { dot: '#A16207', card: 'border-line-soft bg-white', title: 'text-ink' },
  precool: { dot: '#C2410C', card: 'border-line-soft bg-white', title: 'text-ink' },
  solver: { dot: '#2563EB', card: 'border-line-soft bg-white', title: 'text-ink' },
  pass: { dot: '#15803D', card: 'border-green-200 bg-green-50', title: 'text-green-800' },
  fail: { dot: '#B45309', card: 'border-amber-200 bg-amber-50', title: 'text-amber-800' },
  finish: { dot: '#0B1220', card: 'border-line-soft bg-white', title: 'text-ink' },
};
const FACT_TONE = { plain: 'bg-[#F1F4F8] text-ink', ok: 'bg-green-100 text-green-900', warn: 'bg-orange-50 text-orange-900', error: 'bg-amber-100 text-amber-900' };
const GROUP_STYLE = {
  ev: { dot: '#0D9488', text: '#0F766E', bg: '#E9F7F5' },
  battery: { dot: '#CA8A04', text: '#854D0E', bg: '#FBF6E6' },
  precool: { dot: '#EA580C', text: '#9A3412', bg: '#FFF1E8' },
};
const ANSWER_TAG: Record<AnswerTag, [string, string]> = {
  car: ['Car', '#0F766E'], battery: ['Battery', '#A16207'], ac: ['Cooling', '#C2410C'],
  money: ['Cost', '#1D4ED8'], warn: ['Note', '#92400E'], grid: ['Grid', '#334155'], '': ['', '#334155'],
};

type Props = { items: Example[]; selected: number; onSelect: (i: number) => void; onLive: (e: Example) => void };

export default function AskTheHouse({ items, selected, onSelect, onLive }: Props) {
  const e = items[selected];
  const steps = useMemo(() => e.trace.map(stepView), [e]);
  const groups = useMemo(() => constraintGroups(e), [e]);
  const answer = useMemo(() => parseAnswer(e.answer), [e]);
  const warnings = verifierWarnings(e);

  const [shown, setShown] = useState(0);
  const [playing, setPlaying] = useState(false);
  const timer = useRef<ReturnType<typeof setInterval> | null>(null);
  const stop = () => { if (timer.current) clearInterval(timer.current); timer.current = null; };

  // A fresh live result plays back on its own; picking an example waits for Run.
  const autoplay = useRef(false);
  useEffect(() => { stop(); setShown(0); setPlaying(false); if (autoplay.current) { autoplay.current = false; run(); } }, [selected]); // eslint-disable-line react-hooks/exhaustive-deps
  const live = (x: Example) => { autoplay.current = true; onLive(x); };
  useEffect(() => stop, []);

  const run = () => {
    stop();
    setShown(1);
    setPlaying(steps.length > 1);
    timer.current = setInterval(() => {
      setShown((s) => {
        if (s + 1 >= steps.length) { stop(); setPlaying(false); return steps.length; }
        return s + 1;
      });
    }, 900);
  };
  const showAll = () => { stop(); setPlaying(false); setShown(steps.length); };

  const ps = e.plan_summary;
  const s4 = e.comparison['S4 our system'];
  const s1 = e.comparison['S1 simple rules'];
  const noTrip = ps.ev.departure === 'no trip';
  const warmest = ps.room.max_temp_when_home_c;   // null if nobody is home all day
  const hot = warmest != null && warmest > ps.room.comfort_band_c[1];
  const outcomes = [
    noTrip
      ? { label: 'Car at departure', value: 'no trip', sub: 'car stays home', status: 'nothing to do', tone: 'neutral' }
      : { label: 'Car at departure', value: `${fixed(ps.ev.kwh_at_departure)} / ${fixed(ps.ev.target_kwh)} kWh`, sub: `leaves at ${ps.ev.departure}`, status: ps.ev.target_met ? 'target met' : 'short of target', tone: ps.ev.target_met ? 'good' : 'warn' },
    { label: 'Warmest while home', value: warmest != null ? `${fixed(warmest)} °C` : 'nobody home', sub: `wish: at most ${fixed(ps.room.comfort_band_c[1], 0)} °C`, status: hot ? 'above the wish' : 'within the wish', tone: hot ? 'warn' : 'good' },
    { label: 'Electricity on the real day', value: rupees(s4.electricity_cost), sub: `simple rules: ${rupees(s1.electricity_cost)}`, status: `${Math.round(savingVsRules(e))}% cheaper`, tone: 'brand' },
    { label: 'Verifier', value: e.verification.passed ? 'Passed' : 'Failed', sub: `${warnings.length} ${warnings.length === 1 ? 'warning' : 'warnings'} to tell the person`, status: e.replans ? `${e.replans} replan needed` : 'no replans', tone: e.replans ? 'warn' : 'neutral' },
  ];
  const toneClass: Record<string, string> = { good: 'bg-green-100 text-green-900', warn: 'bg-amber-100 text-amber-900', brand: 'bg-[#EAF0FF] text-blue-900', neutral: 'bg-[#F1F4F8] text-ink-2' };

  return (
    <section id="ask" className="flex flex-col gap-7 border-t border-line py-[72px]">
      <SectionHeader eyebrow="Ask the house" title="From a sentence to a verified plan">
        Four requests, run in advance on real days. Pick one and press Run to replay what the agents did, or type your own.
      </SectionHeader>

      <ExampleCards items={items} selected={selected} onSelect={onSelect} />

      <div className="grid items-start gap-[18px] xl:grid-cols-2">
        {/* Chat + trace */}
        <div className="flex flex-col gap-[18px] rounded-[20px] border border-line bg-white p-5 sm:p-6">
          <div className="flex justify-end">
            <div className="max-w-[88%] rounded-[18px_18px_4px_18px] bg-brand px-[18px] py-4 text-lg leading-[1.45] text-white">{degC(e.request)}</div>
          </div>
          <div className="flex flex-wrap items-center justify-between gap-2.5">
            <span className="text-sm text-ink-muted" aria-live="polite">{shown === 0 ? `${steps.length} steps recorded` : `Step ${shown} of ${steps.length}`}</span>
            <div className="flex gap-2">
              <button type="button" onClick={run} className="inline-flex min-h-11 items-center gap-2 rounded-xl bg-ink px-[18px] py-3 font-semibold text-white transition hover:bg-slate-800">
                <svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true"><path d="M6 4l14 8-14 8z" /></svg>
                {shown > 0 && !playing ? 'Run again' : 'Run'}
              </button>
              <button type="button" onClick={showAll} className="min-h-11 rounded-xl border border-[#D5DCE6] bg-white px-4 py-3 font-semibold transition hover:border-ink-muted">Show all</button>
            </div>
          </div>
          {shown === 0 && (
            <div className="rounded-[14px] border border-dashed border-[#D5DCE6] p-7 text-center text-[15px] text-ink-muted">
              Press Run to watch the orchestrator call its tools and agents, step by step.
            </div>
          )}
          <ol className="m-0 flex list-none flex-col gap-2.5 p-0">
            {steps.slice(0, shown).map((t) => {
              const tone = STEP_TONE[t.tone];
              return (
                <li key={`${selected}-${t.n}`} className={`grid animate-rise grid-cols-[34px_minmax(0,1fr)] gap-3 rounded-[14px] border p-3.5 ${tone.card}`}>
                  <span className="flex h-[34px] w-[34px] items-center justify-center rounded-[10px] font-display text-[15px] font-bold text-white" style={{ background: tone.dot }}>{t.n}</span>
                  <div className="flex min-w-0 flex-col gap-[7px]">
                    <div className="flex flex-wrap items-baseline gap-x-2.5 gap-y-1">
                      <span className={`text-base font-bold ${tone.title}`}>{t.label}</span>
                      <span className="font-mono text-xs text-ink-muted">{t.action}</span>
                    </div>
                    <p className="text-[15px] italic text-ink-2">“{t.thought}”</p>
                    {t.reasoning && <p className="text-sm">{t.reasoning}</p>}
                    {t.facts.length > 0 && (
                      <div className="flex flex-wrap gap-1.5">
                        {t.facts.map((f, i) => (
                          <span key={i} className={`rounded-lg px-2 py-1 font-mono text-[12.5px] leading-[1.4] ${FACT_TONE[f.tone]}`}>
                            <span className="opacity-75">{f.k}:</span> {f.v}
                          </span>
                        ))}
                      </div>
                    )}
                  </div>
                </li>
              );
            })}
          </ol>
          {playing && <div className="animate-pulseSoft pl-[46px] text-sm text-ink-muted">thinking…</div>}
          <LiveRequest onResult={live} />
        </div>

        {/* Understood + outcomes */}
        <div className="flex flex-col gap-[18px]">
          <div className="flex flex-col gap-4 rounded-[20px] border border-line bg-white p-5 sm:p-6">
            <h3 className="font-display text-xl font-semibold">What the AI understood</h3>
            {groups.map((g) => {
              const st = GROUP_STYLE[g.key];
              return (
                <div key={g.key} className="flex flex-col gap-2">
                  <div className="flex items-center gap-2">
                    <span className="h-2.5 w-2.5 rounded-[3px]" style={{ background: st.dot }} />
                    <span className="text-[13px] font-bold uppercase tracking-[0.06em]" style={{ color: st.text }}>{g.name}</span>
                  </div>
                  <div className="flex flex-wrap gap-2">
                    {g.chips.length === 0 && <span className="rounded-[10px] border border-dashed border-[#D5DCE6] px-3 py-2 text-sm text-ink-muted">Usual routine</span>}
                    {g.chips.map((c) => (
                      <span key={c.label} className="inline-flex items-baseline gap-2 rounded-[10px] px-3 py-2 text-[15px]" style={{ background: st.bg }}>
                        <span className="text-ink-2">{c.label}</span>
                        <strong className="font-display text-[17px]" style={{ color: st.text }}>{c.value}</strong>
                      </span>
                    ))}
                  </div>
                  {g.why && <p className="text-sm text-ink-muted">{g.why}</p>}
                </div>
              );
            })}
          </div>
          <div className="grid grid-cols-[repeat(auto-fit,minmax(min(200px,100%),1fr))] gap-3">
            {outcomes.map((o) => (
              <div key={o.label} className="flex flex-col gap-1.5 rounded-[18px] border border-line bg-white p-[18px]">
                <span className="text-sm text-ink-muted">{o.label}</span>
                <span className="font-display text-[30px] font-bold leading-[1.1]">{o.value}</span>
                <span className="text-sm text-ink-2">{o.sub}</span>
                <span className={`self-start rounded-full px-2.5 py-1 text-[13px] font-semibold ${toneClass[o.tone]}`}>{o.status}</span>
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* The AI's answer */}
      <div className="flex flex-col gap-4 rounded-[20px] border border-line bg-white p-[clamp(20px,3vw,32px)]">
        <div className="flex flex-wrap items-center justify-between gap-2.5">
          <div className="flex items-center gap-3">
            <span className="flex h-10 w-10 items-center justify-center rounded-xl bg-ink"><Icon name="home" size={22} color="#fff" /></span>
            <h3 className="font-display text-xl font-semibold">The house replies</h3>
          </div>
          <div className="flex flex-wrap gap-2">
            <span className={`inline-flex items-center gap-1.5 rounded-full px-3 py-1.5 text-sm font-semibold ${e.verification.passed ? 'bg-green-100 text-green-900' : 'bg-amber-100 text-amber-900'}`}>
              <Icon name="check" size={14} stroke={2.6} />{e.verification.passed ? 'Verified' : 'Not verified'}
            </span>
            {e.replans > 0 && <span className="rounded-full bg-amber-100 px-3 py-1.5 text-sm font-semibold text-amber-800">{e.replans} replan after a failed check</span>}
          </div>
        </div>
        <div className="flex max-w-[900px] flex-col gap-3">
          {answer.map((p, i) => {
            const [tag, color] = ANSWER_TAG[p.tag];
            return (
              <div key={i} className="grid grid-cols-[72px_minmax(0,1fr)] items-baseline gap-3 sm:grid-cols-[92px_minmax(0,1fr)]">
                <span className="text-xs font-bold uppercase tracking-[0.06em]" style={{ color }}>{tag}</span>
                <p className="text-[17px] text-pretty">
                  {p.segments.map((s, j) => (s.bold ? <strong key={j}>{s.text}</strong> : <span key={j}>{s.text}</span>))}
                </p>
              </div>
            );
          })}
        </div>
        {warnings.length > 0 && (
          <div className="flex flex-col gap-2 rounded-[14px] border border-amber-200 bg-amber-50 px-4 py-3.5">
            <span className="text-[13px] font-bold uppercase tracking-[0.06em] text-amber-800">Verifier warning, told to the person</span>
            {warnings.map((w) => <span key={w} className="text-[15px] text-[#3B2A06]">{w}</span>)}
          </div>
        )}
      </div>

      <DayCharts e={e} />
    </section>
  );
}
