import type { ReactNode } from 'react';

export function SectionHeader({ eyebrow, title, children }: { eyebrow: string; title: string; children?: ReactNode }) {
  return (
    <div className="flex max-w-3xl flex-col gap-2.5">
      <span className="text-sm font-semibold uppercase tracking-[0.08em] text-brand">{eyebrow}</span>
      <h2 className="font-display text-[clamp(30px,3.6vw,44px)] font-bold leading-[1.1] tracking-[-0.025em] text-balance">{title}</h2>
      {children && <p className="text-lg text-ink-2">{children}</p>}
    </div>
  );
}

export function Card({ className = '', children }: { className?: string; children: ReactNode }) {
  return <div className={`rounded-[20px] border border-line bg-white p-6 ${className}`}>{children}</div>;
}

export function ChartCard({ title, legend, note, className = '', children }: { title: ReactNode; legend?: ReactNode; note?: ReactNode; className?: string; children: ReactNode }) {
  return (
    <figure className={`m-0 flex min-w-0 flex-col gap-3 rounded-[20px] border border-line bg-white p-5 sm:p-6 ${className}`}>
      <figcaption className="flex flex-col gap-2">
        <h3 className="font-display text-xl font-semibold sm:text-[22px]">{title}</h3>
        {legend && <div className="flex flex-wrap gap-x-[18px] gap-y-1.5 text-sm text-ink-2">{legend}</div>}
      </figcaption>
      {children}
      {note && <p className="text-sm text-ink-muted">{note}</p>}
    </figure>
  );
}

export function Swatch({ color, label, kind = 'box', dashed = false, dotted = false }: { color: string; label: string; kind?: 'box' | 'line'; dashed?: boolean; dotted?: boolean }) {
  return (
    <span className="inline-flex items-center gap-2">
      {kind === 'box' ? (
        <span className="h-2.5 w-3.5 rounded-[3px]" style={{ background: color }} />
      ) : (
        <span className="h-0 w-4" style={{ borderTop: `${dashed || dotted ? 2 : 3}px ${dotted ? 'dotted' : dashed ? 'dashed' : 'solid'} ${color}` }} />
      )}
      {label}
    </span>
  );
}

const ICONS: Record<string, string> = {
  solar: 'M3 20h18M5 16l2-8h10l2 8H5zM9 8l-1 8M15 8l1 8M6 12h12',
  battery: 'M5 7h12a2 2 0 012 2v6a2 2 0 01-2 2H5a2 2 0 01-2-2V9a2 2 0 012-2zM21 10v4M7 10v4M10 10v4M13 10v4',
  car: 'M5 16V11l2-4h10l2 4v5M3 16h18v2H3zM7 11h10M6 19a1.5 1.5 0 103 0M15 19a1.5 1.5 0 103 0',
  ac: 'M12 3v18M4.2 7.5l15.6 9M19.8 7.5l-15.6 9M9.5 4.5L12 7l2.5-2.5M9.5 19.5L12 17l2.5 2.5',
  bolt: 'M13 2L5 13h6l-1 9 8-11h-6l1-9z',
  thermo: 'M14 14.8V5a2 2 0 10-4 0v9.8a4 4 0 104 0z',
  forecast: 'M9 5.5a3.5 3.5 0 110 7 3.5 3.5 0 010-7zM9 2.5v1.5M2.5 9H4M4.4 4.4l1 1M13.6 4.4l-1 1M8 20h9a4 4 0 000-8 5 5 0 00-9.6 1.6A3.2 3.2 0 008 20z',
  chat: 'M4 5h16v10H9l-5 4V5zM8 9h8M8 12h5',
  grid: 'M6 3h12a3 3 0 013 3v12a3 3 0 01-3 3H6a3 3 0 01-3-3V6a3 3 0 013-3zM3 9h18M9 9v12M13 13h4M13 17h4',
  shield: 'M12 3l7 3v6c0 4.5-3 7.5-7 9-4-1.5-7-4.5-7-9V6l7-3zM8.5 12l2.5 2.5 4.5-5',
  chart: 'M4 20V10M10 20V4M16 20v-7M22 20H2',
  home: 'M3 11l9-7 9 7v9a1 1 0 01-1 1h-5v-6h-6v6H4a1 1 0 01-1-1v-9z',
  bulb: 'M9 18h6M10 21h4M12 3a6 6 0 00-3.5 10.9c.6.4 1 1.1 1 1.9V16h5v-.2c0-.8.4-1.5 1-1.9A6 6 0 0012 3z',
  alert: 'M12 3l10 18H2L12 3zM12 10v5M12 18v.5',
  replay: 'M3 12a9 9 0 0115.5-6.2L21 8M21 3v5h-5',
  check: 'M5 12.5l4.5 4.5L19 7.5',
  arrow: 'M5 12h14M13 6l6 6-6 6',
};

export function Icon({ name, size = 24, color = 'currentColor', stroke = 1.8, className = '' }: { name: keyof typeof ICONS | string; size?: number; color?: string; stroke?: number; className?: string }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke={color} strokeWidth={stroke} strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" className={className}>
      <path d={ICONS[name]} />
    </svg>
  );
}

/** Shared Recharts styling. */
export const axisProps = {
  tick: { fontSize: 12, fill: '#5B6577' },
  tickLine: false,
  axisLine: { stroke: '#E3E8EF' },
} as const;
export const gridProps = { stroke: '#EEF1F5', vertical: false } as const;
export const tooltipStyle = {
  contentStyle: { borderRadius: 12, border: '1px solid #E3E8EF', boxShadow: '0 8px 24px -12px rgba(11,18,32,.25)', fontSize: 13 },
  labelStyle: { fontWeight: 600, color: '#0B1220' },
  itemStyle: { color: '#0B1220' },
} as const;
