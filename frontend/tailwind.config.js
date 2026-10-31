/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  theme: {
    extend: {
      colors: {
        brand: { 50: '#FFF5F5', 100: '#FDECEC', 200: '#F9CFCF', 300: '#F29B9B', 400: '#EF5350', 500: '#D63333',
                 600: '#C62828', 700: '#A82020', 800: '#8E1B1B', 900: '#5E1212' },
        ink: { DEFAULT: '#202124', soft: '#6B7280', faint: '#9CA3AF' },
        canvas: '#F8F9FB',
        line: '#E5E7EB',
        ok: { DEFAULT: '#16845B', soft: '#E7F5EF' },
        warn: { DEFAULT: '#D97706', soft: '#FEF3E2' },
        bad: { DEFAULT: '#C62828', soft: '#FDECEC' },
        info: { DEFAULT: '#2563EB', soft: '#EAF1FE' },
      },
      fontFamily: {
        sans: ['Inter', 'system-ui', 'sans-serif'],
        display: ['"Plus Jakarta Sans"', 'Inter', 'sans-serif'],
        mono: ['"JetBrains Mono"', 'ui-monospace', 'monospace'],
      },
      boxShadow: {
        card: '0 1px 2px rgba(16,24,40,.04), 0 1px 3px rgba(16,24,40,.06)',
        pop: '0 12px 32px -8px rgba(16,24,40,.18), 0 2px 6px rgba(16,24,40,.06)',
      },
      keyframes: {
        'fade-in': { from: { opacity: 0, transform: 'translateY(4px)' }, to: { opacity: 1, transform: 'none' } },
        shimmer: { '100%': { transform: 'translateX(100%)' } },
      },
      animation: { 'fade-in': 'fade-in .18s ease-out' },
    },
  },
  plugins: [],
}
