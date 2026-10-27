'use client';
import { Area, CartesianGrid, ComposedChart, Line, LineChart, ReferenceArea, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';
import { site } from '@/lib/data';
import { addDays, fixed, HOUR_TICKS, hourTick, monthYear, slotTime } from '@/lib/format';
import { axisProps, ChartCard, gridProps, Icon, SectionHeader, Swatch, tooltipStyle } from './ui';
import { CountUp } from './useCountUp';

const avg = site.average_day;
const avgRows = avg.solar_kw.map((v, i) => ({ h: i * 0.25 + 0.125, solar: v, demand: avg.demand_kw[i] }));
const priceRows = [...avg.price_inr_per_kwh.map((v, i) => ({ h: i * 0.25, price: v })), { h: 24, price: avg.price_inr_per_kwh[95] }];

const ds = site.daily_solar;
const dailyRows = ds.date.map((d, i) => ({ i, date: d, actual: ds.actual_kwh[i], forecast: ds.forecast_kwh[i] }));
// Monsoon = June–September of each year, as index ranges.
const monsoon: [number, number][] = [];
ds.date.forEach((d, i) => {
  const m = parseInt(d.slice(5, 7), 10);
  const inM = m >= 6 && m <= 9;
  const last = monsoon[monsoon.length - 1];
  if (inM) { if (last && last[1] === i - 1) last[1] = i; else monsoon.push([i, i]); }
});
const yearTicks = ds.date.map((d, i) => (d.endsWith('-01-01') || i === 0 || i === ds.date.length - 1 ? i : -1)).filter((i) => i >= 0);

export default function Problem() {
  const hd = site.headline;
  const stats = [
    { v: hd.solar_kwh_per_day, d: 1, unit: ' kWh', label: 'solar per day, on average', color: '#B45309' },
    { v: hd.base_demand_kwh_per_day, d: 1, unit: ' kWh', label: 'base house demand per day', color: '#1D4ED8' },
    { v: hd.forecast_error_pct, d: 1, unit: '%', label: 'day-ahead forecast error (daily sunlight)', color: '#0B1220' },
    { v: hd.days_of_data, d: 0, unit: '', label: 'days of real weather data', color: '#0B1220' },
  ];
  return (
    <section id="problem" className="flex flex-col gap-7 border-t border-line py-[72px]">
      <SectionHeader eyebrow="The problem" title="The sun peaks at noon, when nobody is home">
        People need power in the evening. Monsoon clouds make solar drop suddenly, and the weather forecast misses some of it.
      </SectionHeader>

      <div className="grid grid-cols-[repeat(auto-fit,minmax(min(220px,100%),1fr))] gap-3.5">
        {stats.map((s) => (
          <div key={s.label} className="flex flex-col gap-1 rounded-[18px] border border-line bg-white p-[22px]">
            <span className="font-display text-[44px] font-bold leading-[1.05]" style={{ color: s.color }}>
              <CountUp value={s.v} decimals={s.d} />
              <span className="text-xl font-semibold text-ink-muted">{s.unit}</span>
            </span>
            <span className="text-[15px] text-ink-2">{s.label}</span>
          </div>
        ))}
      </div>

      <div className="grid gap-[18px] lg:grid-cols-2">
        <ChartCard
          title="Solar arrives at the wrong time"
          legend={<><Swatch color="#FCD38A" label="Solar (kW)" /><Swatch color="#2563EB" kind="line" label="House demand (kW)" /><span className="text-ink-muted">Average day, 15-min steps</span></>}
        >
          <div className="h-[280px] w-full">
            <ResponsiveContainer>
              <ComposedChart data={avgRows} margin={{ top: 8, right: 12, bottom: 0, left: 0 }}>
                <CartesianGrid {...gridProps} />
                <XAxis dataKey="h" type="number" domain={[0, 24]} ticks={HOUR_TICKS} tickFormatter={hourTick} {...axisProps} />
                <YAxis width={60} domain={[0, 3.5]} ticks={[0, 1, 2, 3]} unit=" kW" {...axisProps} />
                <Tooltip {...tooltipStyle} labelFormatter={(h) => slotTime(Number(h) * 4 - 0.5)} formatter={(v: number, n) => [`${fixed(v, 2)} kW`, n === 'solar' ? 'Solar' : 'House demand']} />
                <Area type="monotone" dataKey="solar" stroke="#D97706" strokeWidth={2.5} fill="#FCD38A" fillOpacity={0.6} isAnimationActive={false} />
                <Line type="monotone" dataKey="demand" stroke="#2563EB" strokeWidth={3} dot={false} isAnimationActive={false} />
              </ComposedChart>
            </ResponsiveContainer>
          </div>
          <div className="flex flex-col gap-1 border-t border-line-soft pt-2">
            <span className="text-sm font-semibold text-ink-2">Electricity price (₹/kWh, time-of-day tariff, placeholder values)</span>
            <div className="h-[130px] w-full">
              <ResponsiveContainer>
                <LineChart data={priceRows} margin={{ top: 8, right: 12, bottom: 0, left: 0 }}>
                  <CartesianGrid {...gridProps} />
                  <XAxis dataKey="h" type="number" domain={[0, 24]} ticks={HOUR_TICKS} tickFormatter={hourTick} {...axisProps} />
                  <YAxis width={44} domain={[0, 10]} ticks={[0, 5, 10]} tickFormatter={(v) => `₹${v}`} {...axisProps} />
                  <Tooltip {...tooltipStyle} labelFormatter={(h) => slotTime(Number(h) * 4)} formatter={(v: number) => [`₹${v}/kWh`, 'Price']} />
                  <Line type="stepAfter" dataKey="price" stroke="#334155" strokeWidth={2} dot={false} isAnimationActive={false} />
                </LineChart>
              </ResponsiveContainer>
            </div>
          </div>
        </ChartCard>

        <ChartCard
          title="…and varies day to day"
          legend={<><Swatch color="#D97706" kind="line" label="Actual solar (kWh/day)" /><Swatch color="#475569" kind="line" label="Forecast made the day before" /><Swatch color="#DCE7F7" label="Monsoon (Jun–Sep)" /></>}
          note="Daily kWh for the 5 kW system. Actual = ERA5 reanalysis; forecast = the weather model's day-ahead run."
        >
          <div className="h-[420px] w-full">
            <ResponsiveContainer>
              <LineChart data={dailyRows} margin={{ top: 8, right: 12, bottom: 0, left: 0 }}>
                {monsoon.map(([a, b]) => (
                  <ReferenceArea key={a} x1={a} x2={b} fill="#DCE7F7" fillOpacity={0.9} ifOverflow="extendDomain" label={{ value: 'monsoon', position: 'insideTop', fill: '#3B5A85', fontSize: 12, fontWeight: 600 }} />
                ))}
                <CartesianGrid {...gridProps} />
                {yearTicks.slice(1, -1).map((i) => <ReferenceLine key={i} x={i} stroke="#C3CCD8" strokeDasharray="3 4" />)}
                <XAxis dataKey="i" type="number" domain={[0, dailyRows.length - 1]} ticks={yearTicks} tickFormatter={(i) => monthYear(ds.date[i])} {...axisProps} />
                <YAxis width={44} domain={[0, 32]} ticks={[0, 10, 20, 30]} unit="" {...axisProps} label={{ value: 'kWh', angle: -90, position: 'insideLeft', fill: '#5B6577', fontSize: 12 }} />
                <Tooltip {...tooltipStyle} labelFormatter={(i) => ds.date[Number(i)] ?? addDays(ds.date[0], Number(i))} formatter={(v: number, n) => [`${fixed(v, 1)} kWh`, n === 'actual' ? 'Actual' : 'Forecast']} />
                <Line type="linear" dataKey="forecast" stroke="#475569" strokeOpacity={0.6} strokeWidth={1} dot={false} isAnimationActive={false} />
                <Line type="linear" dataKey="actual" stroke="#D97706" strokeWidth={1.5} dot={false} isAnimationActive={false} />
              </LineChart>
            </ResponsiveContainer>
          </div>
        </ChartCard>
      </div>

      <div className="flex items-start gap-[18px] rounded-[20px] border border-[#F7DDA8] bg-solar-tint px-7 py-[26px]">
        <Icon name="bulb" size={34} color="#B45309" className="mt-0.5 flex-none" />
        <p className="font-display text-[clamp(19px,2vw,24px)] font-medium leading-[1.4] text-[#3B2A06] text-pretty">
          <strong className="font-bold">The idea:</strong> shift flexible loads to good hours. Charge the car and battery from solar, and pre-cool the house while nobody is home.
        </p>
      </div>
    </section>
  );
}
