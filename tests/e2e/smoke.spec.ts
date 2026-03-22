import { test, expect } from '@playwright/test';

test.beforeEach(async ({ page }) => {
  await page.addInitScript(() => {
    (window as any).__TAURI_INTERNALS__ = {
      invoke: async () => [],
      transformCallback: () => 0,
    };
  });
});

test('app shell renders without crash', async ({ page }) => {
  await page.goto('/');
  await page.waitForLoadState('networkidle');

  // Verify no error overlay is present
  const errorOverlay = page.locator('vite-error-overlay');
  await expect(errorOverlay).toHaveCount(0);

  // Verify the app renders something
  const body = page.locator('body');
  await expect(body).toBeVisible();
});
