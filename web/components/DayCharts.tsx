'use client';
import { useMemo } from 'react';
import { Area, CartesianGrid, ComposedChart, Line, LineChart, ReferenceArea, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';
import { awayRanges, energyRows, powerRows, tempRows } from '@/lib/derive';
import { fixed, HOUR_TICKS, hourTick, slotTime } from '@/lib/format';
import type { Example } from '@/lib/types';
import { axisProps, ChartCard, gridProps, Swatch, tooltipStyle } from './ui';

const LABELS: Record<string, string> = {
  base: 'House demand', ac: 'AC', ev: 'Car charging', charge: 'Battery charging', pv: 'Solar', grid: 'Grid import',
  room: 'Room', outdoor: 'Outdoor', bat: 'Home battery', car: 'Car',
};
const xAxis = <XAxis dataKey="h" type="number" domain={[0, 24]} ticks={HOUR_TICKS} tickFormatter={hourTick} {...axisProps} />;

export default function DayCharts({ e }: { e: Example }) {
  const power = useMemo(() => powerRows(e), [e]);
  const temps = useMemo(() => tempRows(e), [e]);
  const energy = useMemo(() => energyRows(e), [e]);
  const away = useMemo(() => awayRanges(e.series.occupied), [e]);
  const s = e.series;

  return (
    <div className="grid gap-[18px] lg:grid-cols-2">
      <ChartCard
        className="lg:col-span-2"
        title="Power through the day"
        legend={<>
          <Swatch color="#93C5FD" label="House demand" /><Swatch color="#FB923C" label="AC" /><Swatch color="#2DD4BF" label="Car charging" />
          <Swatch color="#CA8A04" label="Battery charging" /><Swatch color="#D97706" kind="line" label="Solar" />
          <Swatch color="#0B1220" kind="line" dashed label="Grid import" /><Swatch color="#64748B" kind="line" dotted label={`Grid limit ${s.import_limit_kw} kW`} />
        </>}
        note={`Total use can exceed ${s.import_limit_kw} kW when the home battery or solar supplies part of it; the grid import always stays under the limit.`}
      >
        <div className="h-[clamp(260px,32vw,400px)] w-full">
          <ResponsiveContainer>
            <ComposedChart data={power} margin={{ top: 8, right: 12, bottom: 0, left: 0 }}>
              <CartesianGrid {...gridProps} />
              {xAxis}
              <YAxis width={60} domain={[0, 10]} ticks={[0, 2, 4, 6, 8, 10]} unit=" kW" {...axisProps} />
              <Tooltip {...tooltipStyle} labelFormatter={(h) => slotTime(Number(h) * 4)} formatter={(v: number, n: string) => [`${fixed(v, 2)} kW`, LABELS[n] ?? n]} />
              <Area type="stepAfter" dataKey="base" stackId="p" stroke="none" fill="#93C5FD" fillOpacity={1} isAnimationActive={false} />
              <Area type="stepAfter" dataKey="ac" stackId="p" stroke="none" fill="#FB923C" fillOpacity={1} isAnimationActive={false} />
              <Area type="stepAfter" dataKey="ev" stackId="p" stroke="none" fill="#2DD4BF" fillOpacity={1} isAnimationActive={false} />
              <Area type="stepAfter" dataKey="charge" stackId="p" stroke="none" fill="#CA8A04" fillOpacity={1} isAnimationActive={false} />
              <Line type="stepAfter" dataKey="pv" stroke="#D97706" strokeWidth={2.5} dot={false} isAnimationActive={false} />
              <ReferenceLine y={s.import_limit_kw} stroke="#64748B" strokeWidth={1.5} strokeDasharray="2 4" label={{ value: `Grid limit ${s.import_limit_kw} kW (applies to grid import)`, position: 'insideTopRight', fill: '#334155', fontSize: 12, fontWeight: 600 }} />
              <Line type="stepAfter" dataKey="grid" stroke="#FFFFFF" strokeWidth={5} strokeOpacity={0.85} dot={false} legendType="none" tooltipType="none" isAnimationActive={false} />
              <Line type="stepAfter" dataKey="grid" stroke="#0B1220" strokeWidth={2.5} strokeDasharray="7 4" dot={false} isAnimationActive={false} />
            </ComposedChart>
          </ResponsiveContainer>
        </div>
      </ChartCard>

      <ChartCard
        title="Room temperature"
        legend={<><Swatch color="#EA580C" kind="line" label="Room" /><Swatch color="#64748B" kind="line" label="Outdoor" /><Swatch color="#BBF7D0" label="Comfort band" /><Swatch color="#E9EDF2" label="Nobody home" /></>}
      >
        <div className="h-[280px] w-full">
          <ResponsiveContainer>
            <LineChart data={temps} margin={{ top: 8, right: 12, bottom: 0, left: 0 }}>
              {away.map(([a, b]) => <ReferenceArea key={a} x1={a} x2={b} fill="#E9EDF2" fillOpacity={1} />)}
              <ReferenceArea y1={s.comfort[0]} y2={s.comfort[1]} fill="#BBF7D0" fillOpacity={0.6} />
              <CartesianGrid {...gridProps} />
              {xAxis}
              <YAxis width={60} domain={[22, 42]} ticks={[22, 27, 32, 37, 42]} unit=" °C" {...axisProps} />
              <Tooltip {...tooltipStyle} labelFormatter={(h) => slotTime(Number(h) * 4)} formatter={(v: number, n: string) => [`${fixed(v, 1)} °C`, LABELS[n] ?? n]} />
              <Line type="monotone" dataKey="outdoor" stroke="#64748B" strokeWidth={2} dot={false} isAnimationActive={false} />
              <Line type="monotone" dataKey="room" stroke="#EA580C" strokeWidth={3} dot={false} isAnimationActive={false} />
            </LineChart>
          </ResponsiveContainer>
        </div>
      </ChartCard>

      <ChartCard
        title="Stored energy"
        legend={<><Swatch color="#0D9488" kind="line" label="Car" /><Swatch color="#A16207" kind="line" label="Home battery" /><Swatch color="#0D9488" kind="line" dashed label="Car target" /><Swatch color="#A16207" kind="line" dashed label="Battery reserve" /></>}
      >
        <div className="h-[280px] w-full">
          <ResponsiveContainer>
            <LineChart data={energy} margin={{ top: 8, right: 12, bottom: 0, left: 0 }}>
              <CartesianGrid {...gridProps} />
              {xAxis}
              <YAxis width={70} domain={[0, 40]} ticks={[0, 10, 20, 30, 40]} unit=" kWh" {...axisProps} />
              <Tooltip {...tooltipStyle} labelFormatter={(h) => slotTime(Number(h) * 4)} formatter={(v: number, n: string) => [`${fixed(v, 1)} kWh`, LABELS[n] ?? n]} />
              <ReferenceLine y={s.ev_target_kwh} stroke="#0D9488" strokeWidth={1.5} strokeDasharray="6 5" />
              <ReferenceLine y={s.battery_min_kwh} stroke="#A16207" strokeWidth={1.5} strokeDasharray="6 5" />
              <Line type="linear" dataKey="car" stroke="#0D9488" strokeWidth={3} dot={false} isAnimationActive={false} />
              <Line type="linear" dataKey="bat" stroke="#A16207" strokeWidth={3} dot={false} isAnimationActive={false} />
            </LineChart>
          </ResponsiveContainer>
        </div>
      </ChartCard>
    </div>
  );
}
