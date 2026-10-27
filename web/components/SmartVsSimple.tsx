'use client';
import { Bar, BarChart, CartesianGrid, Cell, LabelList, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';
import { gapToOracle, savingVsRules, SYSTEM_KEYS, SYSTEMS } from '@/lib/data';
import { cleanCheck, fixed, longDate, rupees } from '@/lib/format';
import type { Example } from '@/lib/types';
import { ExampleTabs } from './ExamplePicker';
import { axisProps, Icon, SectionHeader, tooltipStyle } from './ui';

export default function SmartVsSimple({ items, selected, onSelect }: { items: Example[]; selected: number; onSelect: (i: number) => void }) {
  const e = items[selected];
  const rows = SYSTEM_KEYS.filter((k) => e.comparison[k]).map((k) => ({ key: k, ...SYSTEMS[k], r: e.comparison[k] }));
  const s4 = e.comparison['S4 our system'];
  const s5 = e.comparison['S5 perfect knowledge'];
  const save = Math.round(savingVsRules(e));
  const gap = gapToOracle(e);
  const gapText = gap >= 0
    ? `Only ${fixed(gap)}% more than perfect knowledge, which knew the real weather in advance.`
    : `${fixed(-gap)}% below perfect knowledge on electricity alone; perfect knowledge still wins on total cost (${rupees(s5.total_cost)} vs ${rupees(s4.total_cost)}).`;
  const bars = rows.map((x) => ({ name: `${x.short} ${x.name}`, color: x.color, elec: x.r.electricity_cost, dis: x.r.comfort_dh }));
  const barH = 56 * bars.length + 20;

  const s3 = e.s3;
  const s3r = e.comparison['S3 pure LLM'];
  const s3Temp = s3?.warnings.map((w) => /reaches ([\d.]+) degC/.exec(w)?.[1]).find(Boolean);
  const reasoning = s3 ? (s3.reasoning.length > 430 ? s3.reasoning.slice(0, 430).replace(/\s+\S*$/, '') + ' …' : s3.reasoning) : '';

  return (
    <section id="compare" className="flex flex-col gap-7 border-t border-line py-[72px]">
      <div className="flex flex-wrap items-end justify-between gap-[18px]">
        <SectionHeader eyebrow="Smart vs simple" title="Same day, same wishes, four ways to run the house">
          Every system is scored on the real weather of {e.weekday} {longDate(e.date)}.
        </SectionHeader>
        <ExampleTabs items={items} selected={selected} onSelect={onSelect} />
      </div>

      <div className="flex flex-wrap items-baseline gap-x-6 gap-y-2 rounded-[20px] bg-brand-tint px-[26px] py-[22px]">
        <span className="font-display text-[clamp(36px,4.4vw,56px)] font-bold leading-none text-brand-dark">{save}%</span>
        <span className="max-w-[46ch] text-[19px]">less electricity than simple rules. {gapText}</span>
      </div>

      <div className="grid grid-cols-[repeat(auto-fit,minmax(min(250px,100%),1fr))] gap-3.5">
        {rows.map((x) => {
          const mine = x.key === 'S4 our system';
          const metrics: [string, string, boolean][] = [
            ['Total incl. penalties', rupees(x.r.total_cost), false],
            ['Discomfort', `${fixed(x.r.comfort_dh, 2)} °C·h`, false],
            ['Car short', x.r.ev_unmet_kwh > 0 ? `${fixed(x.r.ev_unmet_kwh)} kWh` : 'none', x.r.ev_unmet_kwh > 0],
            ['Peak grid', `${fixed(x.r.peak_import_kw, 2)} kW`, false],
            ['Solar self-use', `${fixed(x.r.self_consumption_pct, 0)}%`, false],
            ['Violations', x.r.violation ? `yes (${x.r.violations.length || 1})` : 'none', x.r.violation],
          ];
          return (
            <div key={x.key} className={`flex flex-col gap-3.5 rounded-[18px] border bg-white p-5 ${mine ? 'border-brand shadow-[0_0_0_3px_#DBE6FF]' : 'border-line'}`}>
              <div className="flex items-center gap-2.5">
                <span className="rounded-lg px-2 py-1 font-display text-sm font-bold text-white" style={{ background: x.color === '#94A3B8' ? '#64748B' : x.color }}>{x.short}</span>
                <span className="font-display text-[19px] font-semibold">{x.name}</span>
              </div>
              <div className="flex flex-col gap-0.5">
                <span className="font-display text-4xl font-bold leading-[1.05]">{rupees(x.r.electricity_cost)}</span>
                <span className="text-sm text-ink-muted">electricity on the real day</span>
              </div>
              <dl className="m-0 grid grid-cols-[minmax(0,1fr)_auto] gap-x-3 gap-y-[7px] text-[15px]">
                {metrics.map(([k, v, bad]) => (
                  <div key={k} className="contents">
                    <dt className="text-ink-muted">{k}</dt>
                    <dd className={`m-0 text-right font-semibold ${bad ? 'text-red-700' : ''}`}>{v}</dd>
                  </div>
                ))}
              </dl>
              {x.r.violation && x.r.violations.length > 0 && (
                <p className="text-sm font-medium text-red-700">{x.r.violations.join('; ')}</p>
              )}
            </div>
          );
        })}
      </div>

      <div className="grid gap-[18px] lg:grid-cols-2">
        <BarCard title="Electricity bill (₹)" data={bars} dataKey="elec" height={barH} fmt={(v) => rupees(v)} />
        <BarCard title="Discomfort (°C·h)" data={bars} dataKey="dis" height={barH} fmt={(v) => fixed(v, 1)} />
      </div>

      {s3 && s3r && (
        <div className="flex flex-col gap-[22px] rounded-[22px] border border-red-200 bg-red-50 p-[clamp(22px,3vw,36px)]">
          <div className="flex items-start gap-3.5">
            <Icon name="alert" size={34} color="#B91C1C" stroke={1.9} className="flex-none" />
            <div className="flex flex-col gap-1.5">
              <h3 className="font-display text-[clamp(24px,2.6vw,32px)] font-bold leading-[1.15] text-red-900">Why not let the LLM do the maths itself?</h3>
              <p className="text-[17px] text-red-950">S3 got the same request and forecast, and wrote the whole schedule on its own. Its bill looks cheap only because it did not do the job.</p>
            </div>
          </div>
          <div className="grid grid-cols-[repeat(auto-fit,minmax(min(200px,100%),1fr))] gap-3">
            {[
              [String(s3.errors), 'physical rules broken'],
              [`${fixed(s3r.ev_unmet_kwh, 0)} kWh`, 'car short at departure'],
              [`${s3Temp ?? '–'} °C`, 'room temperature while home'],
            ].map(([v, l]) => (
              <div key={l} className="flex flex-col gap-1 rounded-2xl bg-white p-[18px]">
                <span className="font-display text-[44px] font-bold leading-none text-red-700">{v}</span>
                <span className="text-[15px] text-red-950">{l}</span>
              </div>
            ))}
          </div>
          <div className="grid gap-[18px] lg:grid-cols-2">
            <div className="flex flex-col gap-2.5">
              <span className="text-[13px] font-bold uppercase tracking-[0.06em] text-red-800">What the verifier caught</span>
              {s3.error_examples.slice(0, 3).map((x) => (
                <span key={x} className="rounded-[10px] bg-white px-3 py-2 font-mono text-[13.5px] text-red-900">{x}</span>
              ))}
              <span className="text-sm text-red-900">…and {s3.errors - 3} more.</span>
              <span className="pt-1.5 text-[13px] font-bold uppercase tracking-[0.06em] text-red-800">Wishes it missed</span>
              {s3.warnings.map((w) => <span key={w} className="text-[15px] text-red-950">{cleanCheck(w)}</span>)}
            </div>
            <figure className="m-0 flex flex-col gap-3 rounded-2xl bg-white p-5">
              <span className="text-[13px] font-bold uppercase tracking-[0.06em] text-red-800">Its own reasoning</span>
              <blockquote className="m-0 text-[15px] italic leading-[1.55] text-ink-2">“{reasoning}”</blockquote>
              <figcaption className="font-display text-[19px] font-bold text-red-900">Its reasoning said one thing; its schedule did another.</figcaption>
            </figure>
          </div>
        </div>
      )}
    </section>
  );
}

type BarRow = { name: string; color: string; elec: number; dis: number };
function BarCard({ title, data, dataKey, height, fmt }: { title: string; data: BarRow[]; dataKey: 'elec' | 'dis'; height: number; fmt: (v: number) => string }) {
  return (
    <div className="flex min-w-0 flex-col gap-3 rounded-[20px] border border-line bg-white p-6">
      <h3 className="font-display text-xl font-semibold">{title} <span className="text-[15px] font-medium text-ink-muted">lower is better</span></h3>
      <div className="w-full" style={{ height }}>
        <ResponsiveContainer>
          <BarChart data={data} layout="vertical" margin={{ top: 0, right: 64, bottom: 0, left: 0 }} barCategoryGap={12}>
            <CartesianGrid stroke="#EEF1F5" horizontal={false} />
            <XAxis type="number" hide domain={[0, 'dataMax']} />
            <YAxis type="category" dataKey="name" width={170} {...axisProps} axisLine={false} tick={{ fontSize: 14, fill: '#0B1220', fontWeight: 600 }} />
            <Tooltip {...tooltipStyle} cursor={{ fill: '#F1F4F8' }} formatter={(v: number) => [fmt(v), title]} />
            <Bar dataKey={dataKey} radius={[0, 7, 7, 0]} isAnimationActive>
              {data.map((d) => <Cell key={d.name} fill={d.color} />)}
              <LabelList dataKey={dataKey} position="right" formatter={(v: number) => fmt(v)} style={{ fontFamily: '"Space Grotesk", sans-serif', fontWeight: 700, fontSize: 15, fill: '#0B1220' }} />
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}
