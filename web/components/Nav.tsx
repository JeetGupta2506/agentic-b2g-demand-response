const LINKS = [
  ['#how', 'How it works'],
  ['#problem', 'The problem'],
  ['#ask', 'Ask the house'],
  ['#compare', 'Smart vs simple'],
  ['#results', 'Results'],
];

export function Logo() {
  return (
    <svg width="30" height="30" viewBox="0 0 30 30" aria-hidden="true">
      <rect width="30" height="30" rx="8" fill="#0B1220" />
      <circle cx="15" cy="13" r="4.5" fill="#F59E0B" />
      <path d="M15 4.5v2M15 19.5v2M6.5 13h2M21.5 13h2M9 7l1.4 1.4M19.6 17.6L21 19M21 7l-1.4 1.4M10.4 17.6L9 19" stroke="#F59E0B" strokeWidth="1.6" strokeLinecap="round" />
      <path d="M8 25h14" stroke="#60A5FA" strokeWidth="2" strokeLinecap="round" />
    </svg>
  );
}

export default function Nav() {
  return (
    <header className="relative z-20 md:sticky md:top-0 border-b border-line bg-ground/90 backdrop-blur-md">
      <nav aria-label="Sections" className="mx-auto flex max-w-[1240px] flex-wrap items-center justify-between gap-x-6 gap-y-2 px-4 py-3.5 sm:px-10">
        <a href="#top" className="flex items-center gap-2.5 text-ink no-underline">
          <Logo />
          <span className="font-display text-[17px] font-bold tracking-[-0.01em]">Smart Home Energy Planner</span>
        </a>
        <div className="flex flex-wrap gap-1 text-[15px] font-medium">
          {LINKS.map(([href, label]) => (
            <a key={href} href={href} className="rounded-lg px-3 py-2 text-ink-2 no-underline transition-colors hover:bg-line-soft hover:text-ink">
              {label}
            </a>
          ))}
        </div>
      </nav>
    </header>
  );
}
