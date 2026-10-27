'use client';
import { useState } from 'react';
import AskTheHouse from '@/components/AskTheHouse';
import Hero from '@/components/Hero';
import HowItWorks from '@/components/HowItWorks';
import Nav from '@/components/Nav';
import Problem from '@/components/Problem';
import Results from '@/components/Results';
import SmartVsSimple from '@/components/SmartVsSimple';
import { examples } from '@/lib/data';
import type { Example } from '@/lib/types';

export default function Page() {
  // One selection shared by "Ask the house" and "Smart vs simple"; live requests are appended to the pre-run examples.
  const [items, setItems] = useState<Example[]>(examples);
  const [selected, setSelected] = useState(0);
  const addLive = (e: Example) => {
    const n = items.filter((x) => x.live).length + 1;
    setItems([...items, { ...e, live: true, title: n > 1 ? `Your request ${n}` : 'Your request' }]);
    setSelected(items.length);
  };
  return (
    <>
      <Nav />
      <main id="top" className="mx-auto max-w-[1240px] px-4 sm:px-10">
        <Hero />
        <HowItWorks />
        <Problem />
        <AskTheHouse items={items} selected={selected} onSelect={setSelected} onLive={addLive} />
        <SmartVsSimple items={items} selected={selected} onSelect={setSelected} />
        <Results />
      </main>
      <footer className="border-t border-line bg-white">
        <div className="mx-auto grid max-w-[1240px] gap-6 px-4 py-9 text-[15px] text-ink-2 sm:px-10 md:grid-cols-2">
          <div className="flex flex-col gap-1.5">
            <span className="font-display text-[17px] font-bold text-ink">Smart Home Energy Planner — Surat</span>
            <span>3 B.Tech students, SVNIT Surat</span>
          </div>
          <div className="flex flex-col gap-1.5">
            <span>
              Based on El Makroum et al. (2025), <em>Agentic AI Home Energy Management System</em>,{' '}
              <a className="text-brand-dark underline" href="https://arxiv.org/abs/2510.26603">arXiv:2510.26603</a>.
            </span>
            <span>Built on the open-source agentic-ai-hems (MIT).</span>
          </div>
        </div>
      </footer>
    </>
  );
}
