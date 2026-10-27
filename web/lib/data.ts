import siteJson from '@/public/data/site.json';
import examplesJson from '@/public/data/examples.json';
import resultsJson from '@/public/data/results.json';
import type { Example, Results, Site, SystemResult } from './types';

// All numbers on the site come from these three files (results/web_data/).
export const site = siteJson as unknown as Site;
export const examples = examplesJson as unknown as Example[];
export const results = resultsJson as unknown as Results;

export const SYSTEM_KEYS = ['S1 simple rules', 'S4 our system', 'S5 perfect knowledge', 'S3 pure LLM'] as const;
export type SystemKey = (typeof SYSTEM_KEYS)[number];

export const SYSTEMS: Record<SystemKey, { short: string; name: string; color: string }> = {
  'S1 simple rules': { short: 'S1', name: 'Simple rules', color: '#94A3B8' },
  'S4 our system': { short: 'S4', name: 'Our system', color: '#2563EB' },
  'S5 perfect knowledge': { short: 'S5', name: 'Perfect knowledge', color: '#16A34A' },
  'S3 pure LLM': { short: 'S3', name: 'Pure LLM', color: '#DC2626' },
};

export const SHORT_TITLES = ['Early start', 'Home all day', 'Weekend trip', 'Monsoon day'];

export function cmp(e: Example, k: SystemKey): SystemResult | undefined {
  return e.comparison[k];
}

/** Electricity saved by S4 versus S1, in percent. */
export function savingVsRules(e: Example): number {
  const s1 = cmp(e, 'S1 simple rules')!;
  const s4 = cmp(e, 'S4 our system')!;
  return (1 - s4.electricity_cost / s1.electricity_cost) * 100;
}

/** S4 electricity relative to S5 (perfect knowledge), in percent (negative = cheaper). */
export function gapToOracle(e: Example): number {
  const s4 = cmp(e, 'S4 our system')!;
  const s5 = cmp(e, 'S5 perfect knowledge')!;
  return (s4.electricity_cost / s5.electricity_cost - 1) * 100;
}

export const heroStats = (() => {
  const saves = examples.map(savingVsRules);
  const gaps = examples.map((e) => Math.abs(gapToOracle(e)));
  const s3 = examples.find((e) => e.s3)?.s3;
  return {
    saveMin: Math.round(Math.min(...saves)),
    saveMax: Math.round(Math.max(...saves)),
    gapMax: Math.ceil(Math.max(...gaps)),
    s3Errors: s3?.errors ?? 0,
  };
})();
