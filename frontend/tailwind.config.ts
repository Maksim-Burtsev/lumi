import type { Config } from 'tailwindcss';

export default {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  darkMode: 'class',
  theme: {
    extend: {
      colors: {
        bg: 'var(--bg)',
        surface: 'var(--surface)',
        'surface-strong': 'var(--surface-strong)',
        ink: 'var(--ink)',
        hint: 'var(--hint)',
        hairline: 'var(--hairline)',
        accent: 'var(--accent)',
        'accent-text': 'var(--accent-text)',
        success: 'var(--success)',
        danger: 'var(--danger)',
      },
      fontFamily: {
        sans: ['"Golos Text Variable"', 'system-ui', '-apple-system', 'sans-serif'],
        display: ['"Unbounded Variable"', '"Golos Text Variable"', 'sans-serif'],
      },
      borderRadius: {
        card: '22px',
      },
      boxShadow: {
        card: '0 1px 2px rgba(27,24,19,.04), 0 12px 32px rgba(27,24,19,.07)',
        nav: '0 2px 6px rgba(27,24,19,.05), 0 16px 40px rgba(27,24,19,.12)',
      },
      maxWidth: {
        content: '860px',
      },
    },
  },
  plugins: [],
} satisfies Config;
