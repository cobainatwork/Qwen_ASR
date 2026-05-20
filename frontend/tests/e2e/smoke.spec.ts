import { expect, test } from '@playwright/test';

const TOKEN = process.env.E2E_API_TOKEN ?? 'please-change-me-to-strong-token';

test.describe('Frontend smoke (shell + nav)', () => {
  test.beforeEach(async ({ context }) => {
    await context.addInitScript((token: string) => {
      localStorage.setItem('qwen-asr-token', token);
    }, TOKEN);
  });

  test('shell renders banner, sidebar nav, main landmark', async ({ page }) => {
    await page.goto('/');
    await expect(page.getByRole('banner')).toBeVisible();
    await expect(page.getByRole('navigation', { name: '主選單' })).toBeVisible();
    await expect(page.getByRole('main')).toBeVisible();
  });

  test('Header reports GPU and 佇列 placeholders', async ({ page }) => {
    await page.goto('/');
    await expect(page.getByLabel('GPU 狀態')).toBeVisible();
    await expect(page.getByLabel('佇列狀態')).toBeVisible();
  });

  test('Sidebar always-visible items render with correct hrefs', async ({ page }) => {
    await page.goto('/');
    await expect(page.getByRole('link', { name: /離線辨識/ })).toHaveAttribute('href', '/');
    await expect(page.getByRole('link', { name: /辨識歷史/ })).toHaveAttribute('href', '/history');
    await expect(page.getByRole('link', { name: /質檢管理/ })).toHaveAttribute('href', '/quality');
    await expect(page.getByRole('link', { name: /API 金鑰/ })).toHaveAttribute('href', '/keys');
  });

  test('辨識 page renders inside main', async ({ page }) => {
    await page.goto('/');
    const main = page.getByRole('main');
    await expect(main.getByRole('heading', { name: '上傳音檔' })).toBeVisible();
  });

  test('/youtube proxy reaches backend (200 envelope)', async ({ page }) => {
    const responsePromise = page.waitForResponse(
      (resp) => resp.url().includes('/api/v1/dataset/youtube/downloads') && resp.request().method() === 'GET',
      { timeout: 10_000 },
    );
    await page.goto('/youtube');
    const resp = await responsePromise;
    expect(resp.status()).toBe(200);
    const body = await resp.json();
    expect(body.success).toBe(true);
    expect(Array.isArray(body.data)).toBe(true);
  });

  test('ASR workspace shows upload + waveform placeholder + transcript placeholder', async ({ page }) => {
    await page.goto('/');
    // 三段都應該在 DOM
    await expect(page.locator('.asr-page')).toBeVisible();
    await expect(page.locator('.asr-upload-area')).toBeVisible();
    await expect(page.locator('.asr-waveform-area')).toBeVisible();
    await expect(page.locator('.asr-transcript-area')).toBeVisible();
    // 未上傳時 waveform 區顯示提示
    await expect(page.locator('.asr-waveform-area')).toContainText('上傳音檔');
  });
});
