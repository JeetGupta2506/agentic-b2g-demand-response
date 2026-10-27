# Smart Home Energy Planner — Surat (static demo site)

Next.js 14 (App Router) + TypeScript + Tailwind CSS + Recharts. Static export, no backend, works offline.

## Run it

With live requests (preferred): from the repo root run `python -m b2g.demo.server` and open
http://localhost:3000. The Python server serves `out/` and answers `POST /api/plan` (agents + optimizer + verifier).
Without it, the site still works with the pre-run examples; the request box then explains how to start the server.

Static only:

```bash
npm install          # once, needs internet
npm run build        # writes the static site to out/
npm start            # serves out/ on http://localhost:3000
```

Already built: `out/` is included, so on the demo laptop you can also just run
`npx serve out` or `python -m http.server 3000 -d out` without building.
Fonts are bundled (@fontsource), so nothing loads from the internet at demo time.

For development: `npm run dev`.

## Data

All values come from `public/data/` (copied from `results/web_data/`):
`site.json`, `examples.json`, `results.json`. They are imported at build time
(`lib/data.ts`). To refresh numbers after a new `python -m b2g.demo.precompute`,
copy the three files into `public/data/` and run `npm run build` again.

## Layout

- `app/page.tsx` — the single page; holds the example selection shared by
  "Ask the house" and "Smart vs simple".
- `components/` — one file per section (Hero, HowItWorks, Problem, AskTheHouse,
  DayCharts, SmartVsSimple, Results) plus small UI helpers.
- `lib/derive.ts` — turns the raw JSON into what the UI shows (constraint chips,
  agent-trace steps, the answer text, chart rows). `lib/format.ts` — units, dates, ₹.

## Colours

S1 grey, S4 blue (#2563EB), S5 green, S3 red. Solar amber, house demand blue,
AC orange, car teal, home battery gold.
