/** @type {import('tailwindcss').Config} */
const token = (name) => `rgb(var(--${name}) / <alpha-value>)`

module.exports = {
  content: ['./src/renderer/index.html', './src/renderer/src/**/*.{ts,tsx}'],
  darkMode: ['class'],
  theme: {
    extend: {
      colors: {
        bg: token('bg'),
        panel: token('panel'),
        raised: token('raised'),
        line: token('line'),
        ink: token('ink'),
        muted: token('muted'),
        faint: token('faint'),
        accent: token('accent'),
        'accent-ink': token('accent-ink'),
        ok: token('ok'),
        warn: token('warn'),
        bad: token('bad'),
        'c-button': token('c-button'),
        'c-input': token('c-input'),
        'c-text': token('c-text'),
        'c-icon': token('c-icon'),
        'c-container': token('c-container')
      },
      fontFamily: {
        sans: ['"Segoe UI Variable"', '"Segoe UI"', 'Inter', 'system-ui', 'sans-serif'],
        mono: ['"Cascadia Code"', '"JetBrains Mono"', 'Consolas', 'monospace']
      },
      boxShadow: {
        pop: '0 8px 30px -8px rgb(0 0 0 / 0.35), 0 0 0 1px rgb(var(--line) / 1)'
      },
      keyframes: {
        'slide-in': { from: { transform: 'translateY(8px)', opacity: 0 }, to: { transform: 'none', opacity: 1 } },
        'fade-in': { from: { opacity: 0 }, to: { opacity: 1 } },
        indeterminate: { '0%': { transform: 'translateX(-100%)' }, '100%': { transform: 'translateX(300%)' } }
      },
      animation: {
        'slide-in': 'slide-in 160ms ease-out',
        'fade-in': 'fade-in 120ms ease-out',
        indeterminate: 'indeterminate 1.2s ease-in-out infinite'
      }
    }
  },
  plugins: []
}
