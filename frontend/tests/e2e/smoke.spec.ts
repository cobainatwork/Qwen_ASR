import { expect, test } from '@playwright/test';

const TOKEN = process.env.E2E_API_TOKEN ?? 'please-change-me-to-strong-token';

test.describe('Frontend smoke (browser flow)', () => {
  test.beforeEach(async ({ context }) => {
    // 預先注入 token，免去點 /keys 設定（M6 AuthProvider 從 localStorage 讀 'qwen-asr-token'）
    await context.addInitScript((token: string) => {
      localStorage.setItem('qwen-asr-token', token);
    }, TOKEN);
  });

  test('辨識首頁 renders language selector + 上傳按鈕', async ({ page }) => {
    await page.goto('/');
    await expect(page.getByRole('heading', { name: '上傳音檔' })).toBeVisible();
    await expect(page.getByLabel('選擇辨識語言')).toBeVisible();
    await expect(page.getByRole('button', { name: '開始辨識' })).toBeDisabled();
  });

  test('/youtube 渲染 URL 輸入 + 語言選單', async ({ page }) => {
    await page.goto('/youtube');
    await expect(page.getByRole('heading', { name: 'YouTube 音檔下載' })).toBeVisible();
    await expect(page.getByLabel('YouTube URL')).toBeVisible();
    await expect(page.getByLabel('YouTube 辨識語言')).toBeVisible();
    await expect(page.getByRole('button', { name: '下載' })).toBeDisabled();
  });

  test('nav header 含 4 個 route 連結', async ({ page }) => {
    await page.goto('/');
    await expect(page.getByRole('link', { name: '辨識' })).toBeVisible();
    await expect(page.getByRole('link', { name: 'YouTube' })).toBeVisible();
    await expect(page.getByRole('link', { name: '歷史' })).toBeVisible();
    await expect(page.getByRole('link', { name: '金鑰' })).toBeVisible();
  });

  test('/youtube 列表初次載入呼叫 backend（驗證 proxy 通）', async ({ page }) => {
    // 攔截 fetch，驗證 client 對 /api/v1/dataset/youtube/downloads 發出請求
    // 並且 proxy 回 200（backend 真實回應、非 Next.js 自己的 500）
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
});
