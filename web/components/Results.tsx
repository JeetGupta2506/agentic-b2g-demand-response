'use client';
import { CartesianGrid, Line, LineChart, ReferenceArea, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';
import { results } from '@/lib/data';
import { addDays, fixed, longDate, monthYear, rupees, shortMonth } from '@/lib/format';
import { axisProps, ChartCard, gridProps, SectionHeader, Swatch, tooltipStyle } from './ui';

const MODEL_COLORS = ['#64748B', '#7C3AED', '#2563EB'];
const fm = results.forecast_error_by_month;
const split = results.validation_test_split;
const valEndMonth = split.val_end.slice(0, 7);
const splitIdx = fm.month.indexOf(valEndMonth) + 0.5;
const monsoonIdx: [number, number][] = [];
fm.month.forEach((m, i) => {
  const mm = parseInt(m.slice(5, 7), 10);
  if (mm >= 6 && mm <= 9) {
    const last = monsoonIdx[monsoonIdx.length - 1];
    if (last && last[1] === i - 0.5) last[1] = i + 0.5; else monsoonIdx.push([i - 0.5, i + 0.5]);
  }
});
// Keep the shading inside the axis (Recharts drops areas that overflow the domain).
const lastIdx = fm.month.length - 1;
monsoonIdx.forEach((r) => { r[0] = Math.max(0, r[0]); r[1] = Math.min(lastIdx, r[1]); });

function monthRows(series: Record<string, number[]>) {
  return fm.month.map((m, i) => {
    const row: Record<string, number | string> = { i, month: m };
    Object.keys(series).forEach((k) => { row[k] = series[k][i]; });
    return row;
  });
}

const WEEK_COLORS: Record<string, string> = { 'S1 rules': '#94A3B8', 'S5 oracle': '#16A34A' };

export default function Results() {
  const testStart = addDays(split.val_end, 1);
  const groups = ['Solar', 'House demand'].map((target) => {
    const rows = results.forecast_accuracy_test.filter((r) => r.target === target);
    const best = Math.min(...rows.map((r) => r.nmae_pct));
    const max = Math.max(...results.forecast_accuracy_test.map((r) => r.nmae_pct));
    return { target, rows, best, max };
  });
  const wk = results.week_comparison;

  return (
    <section id="results" className="flex flex-col gap-7 border-t border-line py-[72px]">
      <SectionHeader eyebrow="Results" title="How good are the forecasts, and what do they buy?">
        Test period {monthYear(testStart)} – {monthYear(split.test_end)}. Error is nMAE: lower is better.
      </SectionHeader>

      <div className="grid gap-[18px] lg:grid-cols-2">
        {groups.map((g) => (
          <div key={g.target} className="flex flex-col gap-3.5 rounded-[20px] border border-line bg-white p-6">
            <h3 className="font-display text-xl font-semibold">{g.target} forecast error</h3>
            {g.rows.map((r) => {
              const best = r.nmae_pct === g.best;
              return (
                <div key={r.model} className="grid grid-cols-[minmax(120px,190px)_minmax(0,1fr)_64px] items-center gap-3">
                  <span className={`text-[15px] ${best ? 'font-bold' : 'font-medium'}`}>{r.model}</span>
                  <div className="h-6 overflow-hidden rounded-[7px] bg-[#F1F4F8]">
                    <div className="h-full rounded-[7px] transition-[width] duration-700" style={{ width: `${(r.nmae_pct / (g.max * 1.07)) * 100}%`, background: best ? '#2563EB' : '#B6C2D3' }} />
                  </div>
                  <span className="text-right font-display text-[17px] font-bold">{fixed(r.nmae_pct)}%</span>
                </div>
              );
            })}
            <p className="text-sm text-ink-muted">
              {g.target === 'Solar'
                ? 'On the test months the weather-forecast physics model beat LightGBM; on validation LightGBM was best by far.'
                : 'LightGBM wins clearly over both simple baselines.'}
            </p>
          </div>
        ))}
      </div>

      <div className="grid gap-[18px] lg:grid-cols-2">
        <MonthChart
          title="Solar forecast error by month (%)"
          series={fm.pv}
          max={40}
          monsoon
          note="Shaded = monsoon months, the hard ones. The weather model's monsoon bias disappeared in 2026, so the ML model trained on older years lost its edge."
        />
        <MonthChart
          title="House demand forecast error by month (%)"
          series={fm.load}
          max={25}
          note="House demand is synthetic (a daily shape plus noise), so about 12% is close to the noise floor."
        />
      </div>

      <div className="flex flex-col gap-3.5 rounded-[20px] border border-line bg-white p-6">
        <div className="flex flex-col gap-1">
          <h3 className="font-display text-xl font-semibold">One week without the LLM, {longDate(wk.dates[0]).replace(/ \d{4}$/, '')}–{longDate(wk.dates[1])}</h3>
          <p className="text-[15px] text-ink-muted">Daily averages. S2 = forecast + optimizer, no LLM; it isolates what the forecast and optimizer alone achieve.</p>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full min-w-[640px] border-collapse text-base">
            <thead>
              <tr className="text-left text-sm text-ink-muted">
                {['System', 'Total ₹/day', 'Electricity ₹/day', 'Discomfort °C·h', 'Peak kW', 'Solar used'].map((h, i) => (
                  <th key={h} scope="col" className={`border-b border-line px-3 py-2.5 font-semibold ${i ? 'text-right' : ''}`}>{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {wk.rows.map((r) => (
                <tr key={r.system}>
                  <th scope="row" className="border-b border-line-soft p-3 text-left font-semibold">
                    <span className="inline-flex items-center gap-2"><span className="h-2.5 w-2.5 rounded-[3px]" style={{ background: WEEK_COLORS[r.system] ?? '#7C9CC9' }} />{r.system}</span>
                  </th>
                  <td className="border-b border-line-soft p-3 text-right tabular-nums">{rupees(r.total_inr)}</td>
                  <td className="border-b border-line-soft p-3 text-right tabular-nums">{rupees(r.electricity_inr)}</td>
                  <td className="border-b border-line-soft p-3 text-right tabular-nums">{fixed(r.discomfort_degc_h, 2)}</td>
                  <td className="border-b border-line-soft p-3 text-right tabular-nums">{fixed(r.peak_kw, 2)}</td>
                  <td className="border-b border-line-soft p-3 text-right tabular-nums">{fixed(r.solar_used_pct, 0)}%</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      <div className="flex flex-col gap-4 rounded-[22px] bg-ink p-[clamp(22px,3vw,36px)] text-slate-200">
        <h3 className="font-display text-2xl font-bold text-white">Honest limitations</h3>
        <ul className="m-0 grid list-none grid-cols-[repeat(auto-fit,minmax(min(280px,100%),1fr))] gap-3.5 p-0">
          <li className="rounded-[14px] bg-[#162033] p-4 text-base leading-normal">Device sizes, the tariff and the house heat model are placeholders.</li>
          <li className="rounded-[14px] bg-[#162033] p-4 text-base leading-normal">House base demand is synthetic, and the &ldquo;actual&rdquo; weather is ERA5 reanalysis, not a rooftop meter.</li>
          <li className="rounded-[14px] bg-[#162033] p-4 text-base leading-normal">Results come from a few example days and one LLM (Qwen 3.8 27B on Groq&rsquo;s free tier), not a large study.</li>
        </ul>
      </div>
    </section>
  );
}

function MonthChart({ title, series, max, note, monsoon = false }: { title: string; series: Record<string, number[]>; max: number; note: string; monsoon?: boolean }) {
  const keys = Object.keys(series);
  const data = monthRows(series);
  const ticks = Array.from({ length: max / 5 + 1 }, (_, i) => i * 5).filter((v) => max <= 25 || v % 10 === 0);
  return (
    <ChartCard
      title={title}
      legend={<>{keys.map((k, i) => <Swatch key={k} color={MODEL_COLORS[i]} kind="line" label={k} />)}</>}
      note={note}
    >
      <div className="h-[280px] w-full">
        <ResponsiveContainer>
          <LineChart data={data} margin={{ top: 20, right: 12, bottom: 0, left: 0 }}>
            {monsoon && monsoonIdx.map(([a, b]) => <ReferenceArea key={a} x1={a} x2={b} fill="#DCE7F7" fillOpacity={0.9} />)}
            <CartesianGrid {...gridProps} />
            <XAxis dataKey="i" type="number" domain={[0, lastIdx]} ticks={fm.month.map((_, i) => i)} tickFormatter={(i) => shortMonth(fm.month[i])} {...axisProps} interval={0} tick={{ fontSize: 11, fill: '#5B6577' }} />
            <YAxis width={44} domain={[0, max]} ticks={ticks} unit="%" {...axisProps} />
            <ReferenceLine x={splitIdx} stroke="#0B1220" strokeWidth={1.5} strokeDasharray="4 4" label={{ value: `validation ${fm.month[0].slice(0, 4)} | test ${fm.month[lastIdx].slice(0, 4)}`, position: 'top', fill: '#334155', fontSize: 11, fontWeight: 600 }} />
            <Tooltip {...tooltipStyle} labelFormatter={(i) => monthYear(fm.month[Number(i)] + '-01')} formatter={(v: number, n: string) => [`${fixed(v)}%`, n]} />
            {keys.map((k, i) => (
              <Line key={k} type="monotone" dataKey={k} stroke={MODEL_COLORS[i]} strokeWidth={i === 2 ? 3 : 2.2} dot={{ r: 2.5 }} isAnimationActive={false} />
            ))}
          </LineChart>
        </ResponsiveContainer>
      </div>
    </ChartCard>
  );
}
