const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];

export const rupees = (v: number) => '₹' + Math.round(v).toLocaleString('en-IN');
export const fixed = (v: number, d = 1) => Number(v).toFixed(d);
export const pct = (frac: number) => `${Math.round(frac * 100)}%`;

export function longDate(iso: string) {
  const [y, m, d] = iso.split('-');
  return `${parseInt(d, 10)} ${MONTHS[parseInt(m, 10) - 1]} ${y}`;
}
export function monthYear(iso: string) {
  const [y, m] = iso.split('-');
  return `${MONTHS[parseInt(m, 10) - 1]} ${y}`;
}
export function shortMonth(yyyyMm: string) {
  return MONTHS[parseInt(yyyyMm.split('-')[1], 10) - 1];
}
export function addDays(iso: string, n: number) {
  const d = new Date(iso + 'T00:00:00Z');
  d.setUTCDate(d.getUTCDate() + n);
  return d.toISOString().slice(0, 10);
}

/** "degC" → "°C", "degC*h" → "°C·h" (the pipeline writes ASCII units). */
export const degC = (s: string) => s.replace(/degC\*h/g, '°C·h').replace(/degC/g, '°C');

/** Verifier messages without the internal tags: "[wish] … (ask precool_agent)". */
export const cleanCheck = (s: string) =>
  degC(s.replace(/^\[(wish|request|physics|explanation)\]\s*/, '').replace(/\s*\(ask \w+\)\s*$/, ''));

/** 15-minute slot index → "HH:MM". */
export function slotTime(i: number) {
  const mins = Math.round(i * 15);
  const h = Math.floor(mins / 60) % 25;
  return `${String(h).padStart(2, '0')}:${String(mins % 60).padStart(2, '0')}`;
}
/** Hour value (0–24) → "HH:00" axis label. */
export const hourTick = (h: number) => `${String(Math.round(h)).padStart(2, '0')}:00`;
export const HOUR_TICKS = [0, 3, 6, 9, 12, 15, 18, 21, 24];
