import { Icon, SectionHeader } from './ui';

const STEPS = [
  { icon: 'forecast', bg: '#FFF8EB', fg: '#B45309', title: 'Forecast', text: "A LightGBM model predicts tomorrow's solar and house demand from weather forecasts." },
  { icon: 'chat', bg: '#EEF3FF', fg: '#1D4ED8', title: 'LLM agents', text: 'An orchestrator and three specialists (EV, battery, pre-cooling) turn your plain-English request into precise rules.' },
  { icon: 'grid', bg: '#EEF3FF', fg: '#1D4ED8', title: 'Optimizer', text: 'A MILP solver finds the cheapest 24-hour plan in 15-minute steps for car, battery and AC, within the 8 kW grid limit.' },
  { icon: 'shield', bg: '#EAF7EE', fg: '#15803D', title: 'Verifier', text: "Plain code checks the physics, your wishes, and that the AI's explanation only states true numbers.", loop: true },
  { icon: 'chart', bg: '#F1F4F8', fg: '#334155', title: 'Score on reality', text: 'The plan is replayed on the real weather of that day and compared with other systems.' },
];

export default function HowItWorks() {
  return (
    <section id="how" className="flex flex-col gap-7 pb-[72px] pt-12">
      <SectionHeader eyebrow="How it works" title="Our system (S4) in five steps">
        Each part does the job it is good at. The language model never does arithmetic.
      </SectionHeader>
      <ol className="m-0 grid list-none grid-cols-[repeat(auto-fit,minmax(min(210px,100%),1fr))] gap-3.5 p-0">
        {STEPS.map((s, i) => (
          <li key={s.title} className="relative flex flex-col gap-3 rounded-[18px] border border-line bg-white p-[22px]">
            <div className="flex items-center justify-between">
              <span className="flex h-12 w-12 items-center justify-center rounded-[14px]" style={{ background: s.bg }}>
                <Icon name={s.icon} size={26} color={s.fg} />
              </span>
              <span className="font-display text-[15px] font-bold text-slate-400">0{i + 1}</span>
            </div>
            <h3 className="font-display text-xl font-semibold">{s.title}</h3>
            <p className="text-[15px] text-ink-2">{s.text}</p>
            {s.loop && (
              <span className="inline-flex items-center gap-1.5 self-start rounded-full bg-amber-100 px-2.5 py-1 text-[13px] font-semibold text-amber-800">
                <Icon name="replay" size={14} stroke={2.2} /> fails → replan (max 3)
              </span>
            )}
          </li>
        ))}
      </ol>
      <div className="flex flex-wrap items-center gap-x-[18px] gap-y-2.5 rounded-2xl bg-ink px-[22px] py-[18px] text-base text-slate-200">
        <span className="font-semibold text-white">The design rule:</span>
        <span>the <strong className="text-[#93B4FF]">LLM understands</strong> the request</span>
        <span className="text-slate-500" aria-hidden="true">→</span>
        <span>the <strong className="text-[#93B4FF]">optimizer does the maths</strong></span>
        <span className="text-slate-500" aria-hidden="true">→</span>
        <span>the <strong className="text-green-300">verifier checks</strong> the result</span>
      </div>
    </section>
  );
}
