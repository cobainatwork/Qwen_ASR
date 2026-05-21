/**
 * E2E: correction-flow — full happy path
 *
 * Scenario: open session → edit 3 segments → autosave "已儲存" → reload → data persists.
 *
 * Preconditions (manual verification needed — see CLAUDE.md #24):
 *   - Backend running with DEPLOYMENT_PROFILE=vendor, ENV=development
 *   - Frontend dev server running
 *   - E2E_API_TOKEN set to a valid asr:write key
 */

import { test, expect } from '@playwright/test';
import { injectToken, seedCorrectionSession, gotoSession, TOKEN } from './correction-fixtures';

test.describe('Correction full flow', () => {
  test.beforeEach(async ({ context }) => {
    await context.addInitScript((token: string) => {
      localStorage.setItem('qwen-asr-token', token);
    }, TOKEN);
  });

  test('edit 3 segments → autosave saved → reload persists', async ({ page }) => {
    // 1. Seed a session with 3 segments
    await injectToken(page);
    const sessionId = await seedCorrectionSession(page, 3);
    await gotoSession(page, sessionId);

    // 2. Locate all textareas (one per segment)
    const textareas = page.getByRole('textbox');
    await expect(textareas).toHaveCount(3, { timeout: 10_000 });

    // 3. Edit each segment
    const corrections = ['校正後的文字 1', '校正後的文字 2', '校正後的文字 3'];
    for (let i = 0; i < 3; i++) {
      const ta = textareas.nth(i);
      await ta.click();
      await ta.fill(corrections[i]);
    }

    // 4. Wait for debounce (2 s) + network round-trip buffer
    await page.waitForTimeout(3_500);

    // 5. All three cards should show "已儲存"
    const savedBadges = page.getByText('已儲存 ✓');
    await expect(savedBadges.first()).toBeVisible({ timeout: 5_000 });

    // 6. Reload → corrected text still present (persisted in backend)
    await page.reload();
    await page.getByLabel('文字編輯區').waitFor({ state: 'visible', timeout: 15_000 });
    const refreshedTextareas = page.getByRole('textbox');
    await expect(refreshedTextareas.nth(0)).toHaveValue(corrections[0], { timeout: 8_000 });
    await expect(refreshedTextareas.nth(1)).toHaveValue(corrections[1]);
    await expect(refreshedTextareas.nth(2)).toHaveValue(corrections[2]);
  });
});
