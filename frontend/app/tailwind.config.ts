import type { Config } from 'tailwindcss';

const config: Config = {
  content: ['./src/**/*.{html,js,svelte,ts}'],
  theme: {
    extend: {
      colors: {
        ink: '#08111f',
        mist: '#edf4ff',
        sea: '#0d9488',
        flare: '#fb923c'
      },
      boxShadow: {
        glow: '0 0 0 1px rgba(148, 163, 184, 0.12), 0 24px 80px rgba(8, 17, 31, 0.25)'
      }
    }
  },
  plugins: []
};

export default config;
