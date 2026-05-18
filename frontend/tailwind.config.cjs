module.exports = {
  content: ['./index.html', './src/**/*.{svelte,ts,js}'],
  darkMode: 'class',
  theme: {
    extend: {
      colors: {
        bg: { DEFAULT: '#0f172a', soft: '#0b1220', panel: '#1e293b' },
        border: { DEFAULT: '#334155', soft: '#1e293b' },
        accent: { DEFAULT: '#60a5fa', soft: '#1e40af' },
        ok: '#10b981',
        warn: '#fbbf24',
        err: '#f87171',
      },
    },
  },
  plugins: [],
};
