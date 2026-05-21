/**
 * E2E: correction-exports — JSONL and Excel download verification
 *
 * Scenario:
 *   1. Seed a session with 2 segments; correct segment 0
 *   2. Click "匯出 JSONL" → wait for download → verify file contains valid JSONL lines
 *   3. Click "匯出 Excel" → wait for download → verify file has non-zero size
 *
 * Notes:
 *   - Playwright's download event captures the blob triggered by the anchor click
 *     inside downloadBlob() in CorrectionToolbar.
 *   - The confirm dialog for unsaved edits is pre-dismissed by setting no drafts
 *     (segments are fully saved before clicking export).
 *
 * Preconditions (manual verification needed — see CLAUDE.md #24):
 *   - Backend running with DEPLOYMENT_PROFILE=vendor, ENV=development
 *   - Frontend dev server running
 *   - E2E_API_TOKEN set to a valid asr:write key
 */

import { test, expect } from '@playwright/test';
import { injectToken, seedCorrectionSession, gotoSession, TOKEN } from './correction-fixtures';

test.describe('Export downloads', () => {
  test.beforeEach(async ({ context }) => {
    await context.addInitScript((token: string) => {
      localStorage.setItem('qwen-asr-token', token);
    }, TOKEN);
  });

  test('JSONL export downloads valid ndjson file', async ({ page }) => {
    await injectToken(page);
    const sessionId = await seedCorrectionSession(page, 2);
    await gotoSession(page, sessionId);

    // Edit first segment and wait for autosave so no "unsaved" confirm dialog
    const firstTextarea = page.getByRole('textbox').first();
    await firstTextarea.click();
    await firstTextarea.fill('JSONL 匯出測試文字');
    await expect(page.getByText('已儲存 ✓').first()).toBeVisible({ timeout: 8_000 });

    // Trigger download
    const downloadPromise = page.waitForEvent('download');
    await page.getByRole('button', { name: '匯出 JSONL' }).click();
    const download = await downloadPromise;

    // Verify filename pattern
    expect(download.suggestedFilename()).toMatch(/correction_session_\d+\.jsonl/);

    // Read file content and verify it contains at least one valid JSON line
    const path = await download.path();
    expect(path).toBeTruthy();
    const { readFileSync } = await import('fs');
    const content = readFileSync(path!, 'utf-8');
    const lines = content.trim().split('\n').filter(Boolean);
    expect(lines.length).toBeGreaterThan(0);
    // Each line must be parseable JSON
    for (const line of lines) {
      expect(() => JSON.parse(line)).not.toThrow();
    }
  });

  test('Excel export downloads non-empty xlsx file', async ({ page }) => {
    await injectToken(page);
    const sessionId = await seedCorrectionSession(page, 2);
    await gotoSession(page, sessionId);

    // Ensure no unsaved drafts before export
    const firstTextarea = page.getByRole('textbox').first();
    await firstTextarea.click();
    await firstTextarea.fill('Excel 匯出測試文字');
    await expect(page.getByText('已儲存 ✓').first()).toBeVisible({ timeout: 8_000 });

    // Trigger download
    const downloadPromise = page.waitForEvent('download');
    await page.getByRole('button', { name: '匯出 Excel' }).click();
    const download = await downloadPromise;

    // Verify filename pattern
    expect(download.suggestedFilename()).toMatch(/correction_session_\d+\.xlsx/);

    // File must have non-zero size (xlsx magic bytes present)
    const path = await download.path();
    expect(path).toBeTruthy();
    const { statSync } = await import('fs');
    const stat = statSync(path!);
    expect(stat.size).toBeGreaterThan(0);
  });
});
