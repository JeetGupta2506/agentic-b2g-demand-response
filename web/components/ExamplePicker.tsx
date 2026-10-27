'use client';
import { SHORT_TITLES } from '@/lib/data';
import { longDate } from '@/lib/format';
import type { Example } from '@/lib/types';

type PickerProps = { items: Example[]; selected: number; onSelect: (i: number) => void };

export function ExampleCards({ items, selected, onSelect }: PickerProps) {
  return (
    <div role="group" aria-label="Example requests" className="grid grid-cols-[repeat(auto-fit,minmax(min(240px,100%),1fr))] gap-3">
      {items.map((e, i) => {
        const sel = i === selected;
        const tag = e.live ? 'Live request' : e.replans ? `Verifier forced ${e.replans} replan` : e.s3 ? 'Includes the pure-LLM test' : '';
        const tagClass = e.live ? 'bg-[#EAF0FF] text-blue-900' : e.replans ? 'bg-amber-100 text-amber-800' : 'bg-red-100 text-red-800';
        return (
          <button
            key={i}
            type="button"
            aria-pressed={sel}
            onClick={() => onSelect(i)}
            className={`flex min-h-24 flex-col gap-1.5 rounded-2xl border-2 px-[18px] py-4 text-left transition ${sel ? 'border-brand bg-brand-tint' : 'border-line bg-white hover:border-[#C3CCD8]'}`}
          >
            <span className="font-display text-lg font-semibold leading-tight">{e.title}</span>
            <span className="text-sm text-ink-muted">{e.weekday} · {longDate(e.date)}</span>
            {tag && (
              <span className={`self-start rounded-full px-2.5 py-0.5 text-xs font-semibold ${tagClass}`}>{tag}</span>
            )}
          </button>
        );
      })}
    </div>
  );
}

export function ExampleTabs({ items, selected, onSelect }: PickerProps) {
  return (
    <div role="group" aria-label="Choose example" className="flex flex-wrap gap-1.5 rounded-[14px] bg-line-soft p-[5px]">
      {items.map((e, i) => {
        const sel = i === selected;
        return (
          <button
            key={i}
            type="button"
            aria-pressed={sel}
            onClick={() => onSelect(i)}
            className={`min-h-11 rounded-[10px] px-3.5 py-2.5 text-sm font-semibold transition ${sel ? 'bg-white text-brand-dark shadow-[0_1px_3px_rgba(11,18,32,0.12)]' : 'text-ink-2 hover:text-ink'}`}
          >
            {e.live ? e.title : SHORT_TITLES[i] ?? e.title}
          </button>
        );
      })}
    </div>
  );
}
