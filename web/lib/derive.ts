import type { Example, TraceStep } from './types';
import { cleanCheck, degC, pct } from './format';

/* ---------- "What the AI understood" ---------- */

export type Chip = { label: string; value: string };
export type ChipGroup = { key: 'ev' | 'battery' | 'precool'; name: string; chips: Chip[]; why: string };

export function constraintGroups(e: Example): ChipGroup[] {
  const { ev, battery: b, precool: p } = e.constraints;
  const evChips: Chip[] = [];
  if (ev.departure_time != null) evChips.push({ label: 'Car leaves at', value: String(ev.departure_time) });
  if (ev.arrival_time != null) evChips.push({ label: 'Car back at', value: String(ev.arrival_time) });
  if (ev.target_soc != null) evChips.push({ label: 'Car charge needed', value: pct(Number(ev.target_soc)) });
  if (ev.max_power_kw != null) evChips.push({ label: 'Max charging power', value: `${ev.max_power_kw} kW` });
  if (ev.skip_charging === true) evChips.push({ label: 'Charging', value: 'skipped' });

  const batChips: Chip[] = [];
  if (b.reserve_soc != null) batChips.push({ label: 'Battery backup reserve', value: pct(Number(b.reserve_soc)) });
  if (b.allow_grid_charging === false) batChips.push({ label: 'Battery charges', value: 'only from solar' });

  const pcChips: Chip[] = [];
  if (p.comfort_max_c != null) pcChips.push({ label: 'Max room temperature', value: `${Number(p.comfort_max_c)} °C` });
  if (p.comfort_min_c != null) pcChips.push({ label: 'Min room temperature', value: `${Number(p.comfort_min_c)} °C` });
  if (p.away_from != null) pcChips.push({ label: 'House empty from', value: String(p.away_from) });
  if (p.away_until != null) pcChips.push({ label: 'Someone home again at', value: String(p.away_until) });
  if (p.home_all_day === true) pcChips.push({ label: 'Someone home', value: 'all day' });

  return [
    { key: 'ev', name: 'Car', chips: evChips, why: degC(e.agent_reasoning.ev || '') },
    { key: 'battery', name: 'Home battery', chips: batChips, why: degC(e.agent_reasoning.battery || '') },
    { key: 'precool', name: 'Cooling', chips: pcChips, why: degC(e.agent_reasoning.precool || '') },
  ];
}

/* ---------- The AI's answer (light markdown) ---------- */

export type AnswerTag = 'car' | 'battery' | 'ac' | 'money' | 'warn' | 'grid' | '';
export type AnswerPara = { tag: AnswerTag; segments: { text: string; bold: boolean }[] };

const EMOJI_TAG: [string, AnswerTag][] = [
  ['🚗', 'car'], ['🔋', 'battery'], ['❄️', 'ac'], ['❄', 'ac'], ['💰', 'money'], ['⚠️', 'warn'], ['⚠', 'warn'], ['⚡', 'grid'],
];

export function parseAnswer(md: string): AnswerPara[] {
  return md
    .split(/\n\s*\n/)
    .map((raw) => {
      let text = raw.trim();
      let tag: AnswerTag = '';
      for (const [emo, t] of EMOJI_TAG) {
        if (text.startsWith(emo)) { tag = t; text = text.slice(emo.length).trim(); break; }
      }
      text = degC(text).replace(/\s*\(charged_from: \w+\)/g, '');
      const segments = text
        .split('**')
        .map((t, i) => ({ text: t, bold: i % 2 === 1 }))
        .filter((s) => s.text.length > 0);
      return { tag, segments };
    })
    .filter((p) => p.segments.length > 0);
}

/* ---------- Agent trace ---------- */

export type Fact = { k: string; v: string; tone: 'plain' | 'ok' | 'warn' | 'error' };
export type StepView = {
  n: number;
  action: string;
  agent?: string;
  label: string;
  tone: 'forecast' | 'calendar' | 'ev' | 'battery' | 'precool' | 'solver' | 'pass' | 'fail' | 'finish';
  thought: string;
  reasoning: string;
  facts: Fact[];
};

const AGENT_NAMES: Record<string, string> = { ev_agent: 'EV agent', battery_agent: 'Battery agent', precool_agent: 'Pre-cooling agent' };

function safeJson(s?: string): Record<string, any> | null {
  if (!s) return null;
  try { return JSON.parse(s); } catch { return null; }
}

export function stepView(t: TraceStep): StepView {
  const o = safeJson(t.observation);
  const base = { n: t.step, action: t.action, agent: t.agent, thought: degC(t.thought), reasoning: '', facts: [] as Fact[] };
  switch (t.action) {
    case 'GET_FORECAST':
      return {
        ...base, label: 'Get tomorrow’s forecast', tone: 'forecast',
        facts: o ? [
          { k: 'solar forecast', v: `${o.pv_forecast_kwh} kWh`, tone: 'plain' },
          { k: 'strong sun', v: o.pv_strong_hours, tone: 'plain' },
          { k: 'outdoor max', v: `${o.outdoor_temp_c?.max} °C at ${o.outdoor_temp_c?.hottest_at}`, tone: 'plain' },
          { k: 'house demand', v: `${o.base_load_forecast_kwh} kWh`, tone: 'plain' },
        ] : [],
      };
    case 'GET_CALENDAR': {
      const ev = o?.ev, c = o?.comfort;
      return {
        ...base, label: 'Check the usual routine', tone: 'calendar',
        facts: o ? [
          { k: 'car away', v: ev?.trip_today ? `${ev.departure_time}–${ev.arrival_time}` : 'no trip', tone: 'plain' },
          { k: 'car target', v: pct(ev?.target_soc ?? 0), tone: 'plain' },
          { k: 'comfort', v: `${c?.comfort_min_c}–${c?.comfort_max_c} °C`, tone: 'plain' },
          { k: 'someone home', v: c?.someone_home, tone: 'plain' },
        ] : [],
      };
    }
    case 'CALL_AGENT': {
      const answer = (o?.constraints ?? t.agent_answer ?? {}) as Record<string, unknown>;
      const key = (t.agent || String(t.params?.agent_name || '')) as string;
      const tone = key.startsWith('ev') ? 'ev' : key.startsWith('battery') ? 'battery' : 'precool';
      return {
        ...base, agent: key, label: `Ask the ${AGENT_NAMES[key] ?? key}`, tone,
        reasoning: degC(String(answer.reasoning ?? '')),
        facts: Object.entries(answer).filter(([k]) => k !== 'reasoning').map(([k, v]) => ({ k, v: String(v), tone: 'plain' as const })),
      };
    }
    case 'RUN_SOLVER':
      return {
        ...base, label: 'Run the optimizer', tone: 'solver',
        facts: o ? [
          { k: 'status', v: o.solver_status, tone: 'plain' },
          { k: 'est. cost', v: `₹${o.estimated_electricity_cost}`, tone: 'plain' },
          { k: 'comfort band', v: `${o.room?.comfort_band_c?.[0]}–${o.room?.comfort_band_c?.[1]} °C`, tone: 'plain' },
          { k: 'peak import', v: `${o.grid?.peak_import_kw} kW`, tone: 'plain' },
        ] : [],
      };
    case 'VERIFY': {
      const passed = !!o?.passed;
      const facts: Fact[] = [{ k: 'result', v: passed ? 'passed' : 'failed', tone: passed ? 'ok' : 'error' }];
      (o?.errors ?? []).forEach((x: string) => facts.push({ k: 'error', v: cleanCheck(x), tone: 'error' }));
      (o?.warnings_to_tell_the_person ?? []).forEach((x: string) => facts.push({ k: 'warning', v: cleanCheck(x), tone: 'warn' }));
      return { ...base, label: passed ? 'Verify — passed' : 'Verify — failed, replan', tone: passed ? 'pass' : 'fail', facts };
    }
    default:
      return { ...base, label: 'Finish and explain', tone: 'finish' };
  }
}

/* ---------- Day chart rows ---------- */

export type PowerRow = { h: number; base: number; ac: number; ev: number; charge: number; pv: number; grid: number };
export type TempRow = { h: number; room: number; outdoor: number };
export type EnergyRow = { h: number; bat: number; car: number };

export function powerRows(e: Example): PowerRow[] {
  const s = e.series;
  // Step charts: repeat the last value at 24:00 so the final slot is drawn.
  const rows: PowerRow[] = s.pv.map((_, i) => ({
    h: i * 0.25, base: s.base[i], ac: s.ac[i], ev: s.ev[i], charge: s.charge[i], pv: s.pv[i], grid: s.grid_import[i],
  }));
  rows.push({ ...rows[rows.length - 1], h: 24 });
  return rows;
}
export function tempRows(e: Example): TempRow[] {
  const s = e.series;
  // temps: 97 boundary states (end of each slot); t_out: 96 slot values, held to 24:00.
  return s.temps.map((v, i) => ({ h: i * 0.25, room: v, outdoor: s.t_out[Math.min(i, s.t_out.length - 1)] }));
}
export function energyRows(e: Example): EnergyRow[] {
  return e.series.e_bat.map((v, i) => ({ h: i * 0.25, bat: v, car: e.series.e_ev[i] }));
}
/** Runs of slots where nobody is home, as [startHour, endHour]. */
export function awayRanges(occ: boolean[]): [number, number][] {
  const out: [number, number][] = [];
  let i = 0;
  while (i < occ.length) {
    if (!occ[i]) { let j = i; while (j < occ.length && !occ[j]) j++; out.push([i * 0.25, j * 0.25]); i = j; } else i++;
  }
  return out;
}

export const verifierWarnings = (e: Example) => e.verification.warnings_to_tell_the_person.map(cleanCheck);
