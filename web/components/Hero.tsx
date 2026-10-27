'use client';
import { heroStats, site } from '@/lib/data';
import { monthYear } from '@/lib/format';
import { Icon } from './ui';
import { CountUp } from './useCountUp';

export default function Hero() {
  const h = site.house;
  const specs = [
    { icon: 'solar', value: `${h.pv_kwp} kWp`, label: 'rooftop solar', bg: '#FFF8EB', fg: '#B45309' },
    { icon: 'battery', value: `${h.battery_kwh} kWh`, label: 'home battery', bg: '#FBF6E6', fg: '#A16207' },
    { icon: 'car', value: `${h.ev_kwh} kWh`, label: `car, ${h.ev_charger_kw} kW charger`, bg: '#E9F7F5', fg: '#0F766E' },
    { icon: 'ac', value: `${h.ac_kw} kW`, label: 'air conditioner', bg: '#FFF1E8', fg: '#C2410C' },
    { icon: 'bolt', value: `${h.grid_limit_kw} kW`, label: 'grid import limit', bg: '#EEF3FF', fg: '#1D4ED8' },
    { icon: 'thermo', value: `${h.comfort_c[0]}–${h.comfort_c[1]} °C`, label: 'comfort band', bg: '#F1F4F8', fg: '#334155' },
  ];
  return (
    <section className="grid items-center gap-12 pb-10 pt-[clamp(40px,7vw,88px)] lg:grid-cols-2">
      <div className="flex flex-col gap-5">
        <div className="flex flex-wrap gap-2">
          <span className="rounded-full bg-[#EAF0FF] px-3 py-1.5 text-[13px] font-semibold uppercase tracking-[0.06em] text-brand-dark">B.Tech research demo</span>
          <span className="rounded-full bg-line-soft px-3 py-1.5 text-[13px] font-semibold uppercase tracking-[0.06em] text-ink-2">SVNIT Surat</span>
        </div>
        <h1 className="font-display text-[clamp(40px,5.6vw,72px)] font-bold leading-[1.02] tracking-[-0.035em] text-balance">
          Smart Home Energy Planner <span className="text-brand">— Surat</span>
        </h1>
        <p className="text-[19px] italic text-ink-2">Forecast-aware hybrid agentic AI for Building-to-Grid demand response.</p>
        <p className="max-w-[34ch] text-[22px] leading-[1.45] text-pretty">
          Tell the house what you need in plain English. The AI understands it, an optimizer does the maths, and a verifier checks every number.
        </p>
        <div className="flex flex-wrap gap-3 pt-1.5">
          <a href="#ask" className="inline-flex min-h-12 items-center gap-2.5 rounded-xl bg-brand px-[22px] py-3.5 font-semibold text-white no-underline transition hover:bg-brand-dark">
            Ask the house <Icon name="arrow" size={18} stroke={2} />
          </a>
          <a href="#compare" className="inline-flex min-h-12 items-center rounded-xl border border-[#D5DCE6] bg-white px-[22px] py-3.5 font-semibold text-ink no-underline transition hover:border-ink-muted">
            See the results
          </a>
        </div>
      </div>

      <div className="flex flex-col gap-4">
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
          <Stat color="#93B4FF" label="less electricity than simple rules">
            <CountUp value={heroStats.saveMin} />–<CountUp value={heroStats.saveMax} suffix="%" />
          </Stat>
          <Stat color="#86EFAC" label="of perfect knowledge on electricity">
            within <CountUp value={heroStats.gapMax} suffix="%" />
          </Stat>
          <Stat color="#FCA5A5" label="physical rules broken by a pure LLM">
            <CountUp value={heroStats.s3Errors} />
          </Stat>
        </div>
        <div className="flex flex-col gap-4 rounded-[20px] border border-line bg-white p-6 shadow-[0_1px_2px_rgba(11,18,32,0.04),0_12px_32px_-16px_rgba(11,18,32,0.12)]">
          <div className="flex flex-wrap items-baseline justify-between gap-3">
            <h2 className="font-display text-xl font-semibold">The house</h2>
            <span className="text-sm text-ink-muted">{h.city}, India · one household</span>
          </div>
          <div className="grid grid-cols-[repeat(auto-fit,minmax(min(150px,100%),1fr))] gap-2.5">
            {specs.map((s) => (
              <div key={s.label} className="flex items-center gap-3 rounded-xl p-3" style={{ background: s.bg }}>
                <Icon name={s.icon} size={28} color={s.fg} />
                <div className="flex flex-col">
                  <span className="font-display text-[22px] font-bold leading-[1.1]">{s.value}</span>
                  <span className="text-[13px] text-ink-muted">{s.label}</span>
                </div>
              </div>
            ))}
          </div>
          <p className="text-sm text-ink-muted">
            On weekdays the family is away {h.weekday_away[0]}–{h.weekday_away[1]}. Weather data {monthYear(h.data_range[0])} – {monthYear(h.data_range[1])}.
          </p>
        </div>
      </div>
    </section>
  );
}

function Stat({ color, label, children }: { color: string; label: string; children: React.ReactNode }) {
  return (
    <div className="flex flex-col gap-1.5 rounded-[18px] bg-ink p-5 text-white">
      <span className="whitespace-nowrap font-display text-[clamp(26px,2.4vw,34px)] font-bold leading-none" style={{ color }}>{children}</span>
      <span className="text-sm leading-[1.35] text-slate-300">{label}</span>
    </div>
  );
}
