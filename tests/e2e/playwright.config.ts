import { defineConfig } from '@playwright/test';

export default defineConfig({
  testDir: '.',
  testMatch: '*.spec.ts',
  timeout: 30_000,
  use: {
    baseURL: 'http://127.0.0.1:4173',
  },
  webServer: {
    command: process.env.CI ? 'npx vite preview --port 4173 --strictPort' : 'npm run dev',
    cwd: '../../frontend/app',
    url: 'http://127.0.0.1:4173',
    reuseExistingServer: !process.env.CI,
    timeout: 60_000,
  },
});
