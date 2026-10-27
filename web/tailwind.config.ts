import type { Config } from 'tailwindcss';

const config: Config = {
  content: ['./app/**/*.{ts,tsx}', './components/**/*.{ts,tsx}'],
  theme: {
    extend: {
      colors: {
        ink: { DEFAULT: '#0B1220', 2: '#334155', muted: '#5B6577' },
        line: { DEFAULT: '#E3E8EF', soft: '#EEF1F5' },
        ground: '#F7F8FA',
        brand: { DEFAULT: '#2563EB', dark: '#1D4ED8', tint: '#EEF3FF' },
        solar: { DEFAULT: '#F59E0B', line: '#D97706', tint: '#FFF8EB', text: '#B45309' },
        demand: { DEFAULT: '#93C5FD', line: '#2563EB' },
        ac: { DEFAULT: '#FB923C', line: '#EA580C', tint: '#FFF1E8', text: '#9A3412' },
        car: { DEFAULT: '#2DD4BF', line: '#0D9488', tint: '#E9F7F5', text: '#0F766E' },
        battery: { DEFAULT: '#CA8A04', line: '#A16207', tint: '#FBF6E6', text: '#854D0E' },
      },
      fontFamily: {
        sans: ['Inter', 'system-ui', '-apple-system', 'Segoe UI', 'sans-serif'],
        display: ['"Space Grotesk"', 'system-ui', 'sans-serif'],
        mono: ['"JetBrains Mono"', 'ui-monospace', 'monospace'],
      },
      keyframes: {
        rise: { from: { opacity: '0', transform: 'translateY(10px)' }, to: { opacity: '1', transform: 'none' } },
        pulseSoft: { '0%,100%': { opacity: '1' }, '50%': { opacity: '0.35' } },
      },
      animation: { rise: 'rise .45s ease both', pulseSoft: 'pulseSoft 1.2s ease-in-out infinite' },
    },
  },
  plugins: [],
};
export default config;
